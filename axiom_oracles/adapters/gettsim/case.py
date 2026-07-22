"""The oracle-side GETTSIM case schema and its projection into engine inputs.

Everything in this module is pure Python: it turns a :class:`GettsimCase`
(persons + a relationship spec) plus a *flattened input template* (the paths and
dtypes GETTSIM discovers for a policy date) into the two objects GETTSIM's
``InputData.df_and_mapper`` wants — a column-oriented ``data`` dict (one value
per person, in ``p_id`` order) and a nested ``mapper`` tree whose leaves are the
flat column names. No GETTSIM import happens here, so the projection, the
defaulting rules, and the input-path guard are all unit-testable against a
hand-built template without the heavy optional dependency.

Why a full template plus defaults (not per-target templates)
------------------------------------------------------------
The adapter always discovers the *full* input template
(``MainTarget.templates.input_data_dtypes.tree``) and defaults every column,
then overlays the case: one uniform route that closes over every dependency of
every target, so target choice can never change which inputs exist. The
defaulting rules below are dtype-first, with a small set of value guards that
GETTSIM's table lookups require:

- bool columns default ``False``; float columns default ``0.0``;
- ``p_id`` is the person's 0-based index (reserved — cases cannot set it);
- every *other* ``p_id...`` link column defaults ``-1`` (no link);
- the age/birth demographics (``alter``, ``alter_monate``, ``geburtsjahr``,
  ``geburtsmonat``) are derived **coherently** from whichever of them the case
  supplies plus the policy date — see below;
- ``alter_beginn_*`` columns are **ages**, not years — a year there overruns the
  §22 Ertragsanteil table (size 121), so they default to
  :data:`DEFAULT_ALTER_BEGINN` (65);
- ``jahr_renteneintritt`` is a **year** — ``0`` underruns the Besteuerungsanteil
  table (indexed ``year - 1940``), so it defaults to
  :data:`DEFAULT_RENTENEINTRITT_JAHR` (2020);
- ``steuerklasse`` defaults to 1 and ``mietstufe_hh`` to 3 (valid lookup keys);
- grouping ``*_id`` columns default ``0`` (one household / one group).

Coherent demographics
---------------------
``alter``, ``alter_monate``, ``geburtsjahr``, and ``geburtsmonat`` describe one
fact — when the person was born — so independent per-column defaults can invent
a contradictory person (an ``alter=40`` adult whose defaulted
``alter_monate=0`` is a benefit-establishing newborn). The projection instead
resolves the four columns jointly against the policy date:

- a supplied ``geburtsjahr`` fixes the birth date (month from ``geburtsmonat``
  or January); otherwise a supplied ``alter_monate`` fixes it exactly;
  otherwise a supplied ``alter`` (or :data:`DEFAULT_ALTER`) back-derives it,
  combined with the supplied ``geburtsmonat`` where present or with the
  birthday-in-the-policy-month convention where not (which keeps
  ``alter_monate == alter * 12`` for age-only cases);
- the remaining columns are computed from the birth date at month precision
  (the template carries no day-of-birth input; the birthday counts as passed
  in the birth month itself);
- any supplied value that contradicts the derived birth date raises
  :class:`GettsimInputError` instead of silently running a chimera household.

Grouping ids
------------
At the 2025 policy dates only ``hh_id`` is an *input* column; GETTSIM derives the
finer ``wthh_id``/``bg_id``/``eg_id``/``fg_id``/``sn_id`` from ``hh_id`` and the
family links. Its own guidance is that this derivation is correct only when there
is exactly one Familien-/Bedarfsgemeinschaft per household; complex households
(multiple families, self-supporting children) must supply the finer ids
directly. The case therefore accepts an optional ``grouping_ids`` override for
any of :data:`KNOWN_GROUPING_IDS`, which the projection adds as explicit input
columns even though they are absent from the default template. Grouping ids are
set through that field only — a grouping id inside a person mapping is rejected
so the two channels cannot silently overwrite each other.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .errors import GettsimInputError

#: Default adult age when a case supplies no demographics at all.
DEFAULT_ALTER = 40
#: Default birth month (January) when only a year-grained fact is supplied.
DEFAULT_GEBURTSMONAT = 1
#: ``alter_beginn_*`` columns are ages; a year overruns the §22 Ertragsanteil
#: table (size 121, indexed by age).
DEFAULT_ALTER_BEGINN = 65
#: Year-of-retirement default; ``0`` underruns the Besteuerungsanteil table
#: (size 151, indexed ``year - 1940``).
DEFAULT_RENTENEINTRITT_JAHR = 2020
DEFAULT_RENTENEINTRITT_MONAT = 1
DEFAULT_STEUERKLASSE = 1
DEFAULT_MIETSTUFE = 3
#: The "no link" sentinel GETTSIM uses for ``p_id`` link columns.
NO_LINK = -1

#: Grouping-id columns GETTSIM recognises as inputs even when they are absent
#: from the default template (the complex-household escape hatch).
KNOWN_GROUPING_IDS: frozenset[str] = frozenset(
    {"hh_id", "wthh_id", "bg_id", "eg_id", "fg_id", "sn_id"}
)

#: Link columns owned by the structured relationship fields; supplying them raw
#: would bypass the graph validation (one-sided or self links run silently).
STRUCTURED_LINK_COLUMNS: frozenset[str] = frozenset(
    {
        "familie__p_id_ehepartner",
        "familie__p_id_elternteil_1",
        "familie__p_id_elternteil_2",
        "kindergeld__p_id_empfänger",
    }
)

#: Partnership link leaves: both directions must agree (a one-sided link
#: silently changes GETTSIM's Bedarfsgemeinschaft derivation). Parent, payer,
#: and recipient links are directional and carry no symmetry requirement.
SYMMETRIC_LINK_LEAVES: frozenset[str] = frozenset(
    {"p_id_ehepartner", "p_id_einstandspartner"}
)

#: The jointly-derived demographic leaves (one birth-date fact, four columns).
DEMOGRAPHIC_LEAVES: frozenset[str] = frozenset(
    {"alter", "alter_monate", "geburtsjahr", "geburtsmonat"}
)

#: The case-schema fields :meth:`GettsimCase.from_mapping` accepts.
CASE_FIELDS: frozenset[str] = frozenset(
    {"persons", "spouse_pairs", "parents", "kindergeld_recipients", "grouping_ids"}
)


@dataclass(frozen=True)
class GettsimCase:
    """A hypothetical German household in the GETTSIM oracle's input language.

    Args:
        persons: One mapping per person, each holding that person's GETTSIM
            input overrides. Keys may be qualified column names
            (``"einnahmen__bruttolohn_m"``) or nested dicts
            (``{"einnahmen": {"bruttolohn_m": 4000.0}}``); the two forms mix
            freely but may not name the same column twice. Person order defines
            ``p_id`` (person ``i`` has ``p_id`` i); ``p_id`` itself is reserved
            and cannot appear as an input.
        spouse_pairs: ``(i, j)`` index pairs joined by
            ``familie__p_id_ehepartner`` (set symmetrically). Pairs must be
            disjoint (monogamous links) and never self-referential. Joint
            assessment itself is a separate input
            (``einkommensteuer__gemeinsam_veranlagt``) the persons carry, so a
            pair links the spouses without presuming how they file.
        parents: Child index → ``(parent_1_index, parent_2_index)``; either
            parent may be ``None``. Sets ``familie__p_id_elternteil_1/2``. A
            child cannot be its own parent and the two parents must differ.
        kindergeld_recipients: Child index → recipient index, setting
            ``kindergeld__p_id_empfänger`` (who is paid the child's Kindergeld).
        grouping_ids: Optional per-person id overrides for any of
            :data:`KNOWN_GROUPING_IDS`, for complex households where GETTSIM's
            derivation from ``hh_id`` is not valid. Each value is a list with one
            entry per person. This field is the only channel for grouping ids —
            they are rejected inside ``persons``.
    """

    persons: Sequence[Mapping[str, Any]]
    spouse_pairs: Sequence[tuple[int, int]] = ()
    parents: Mapping[int, tuple[int | None, int | None]] = field(default_factory=dict)
    kindergeld_recipients: Mapping[int, int] = field(default_factory=dict)
    grouping_ids: Mapping[str, Sequence[int]] = field(default_factory=dict)

    @property
    def n_persons(self) -> int:
        return len(self.persons)

    @classmethod
    def single_person(cls, inputs: Mapping[str, Any] | None = None) -> "GettsimCase":
        """A one-person household — the common single-earner oracle shape."""
        return cls(persons=[dict(inputs or {})])

    @classmethod
    def from_mapping(cls, spec: Mapping[str, Any]) -> "GettsimCase":
        """Build a case from a plain nested-path dict.

        Accepts exactly the constructor's fields (``persons`` required); any
        other key is rejected so a typo (``spouse_pair``) cannot silently drop
        a relationship. Person indices must be real integers — booleans,
        floats, and ``None`` raise instead of being coerced (``False`` would
        silently alias person 0, ``1.9`` would truncate to person 1).
        """
        unknown = set(map(str, spec)) - CASE_FIELDS
        if unknown:
            raise GettsimInputError(
                f"unknown GETTSIM case field(s) {sorted(unknown)}; expected a "
                f"subset of {sorted(CASE_FIELDS)}"
            )
        if "persons" not in spec:
            raise GettsimInputError(
                "a GETTSIM case mapping must contain a 'persons' list"
            )
        for field_name in ("persons", "spouse_pairs"):
            value = spec.get(field_name, ())
            if isinstance(value, (str, bytes, bytearray, Mapping)) or not isinstance(
                value, Sequence
            ):
                raise GettsimInputError(
                    f"{field_name} must be a sequence, got {value!r}"
                )
        for field_name in ("parents", "kindergeld_recipients", "grouping_ids"):
            value = spec.get(field_name, {})
            if not isinstance(value, Mapping):
                raise GettsimInputError(
                    f"{field_name} must be a mapping, got {value!r}"
                )
        return cls(
            persons=list(spec["persons"]),
            spouse_pairs=[
                (
                    _strict_index(pair[0], "spouse_pairs"),
                    _strict_index(pair[1], "spouse_pairs"),
                )
                for pair in _pairs(spec.get("spouse_pairs", ()), "spouse_pairs")
            ],
            parents={
                _strict_index(k, "parents"): (
                    None if v[0] is None else _strict_index(v[0], "parents"),
                    None if v[1] is None else _strict_index(v[1], "parents"),
                )
                for k, v in _pair_items(spec.get("parents", {}), "parents")
            },
            kindergeld_recipients={
                _strict_index(k, "kindergeld_recipients"): _strict_index(
                    v, "kindergeld_recipients"
                )
                for k, v in spec.get("kindergeld_recipients", {}).items()
            },
            grouping_ids={
                str(k): list(v) for k, v in spec.get("grouping_ids", {}).items()
            },
        )


def _strict_index(value: Any, field_name: str) -> int:
    """A person index must be a real int — no bool/float/None coercion."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise GettsimInputError(
            f"{field_name} person index must be an integer, got {value!r}"
        )
    return value


def _pairs(entries: Any, field_name: str) -> list[Sequence[Any]]:
    """Each entry must be a two-element non-string sequence."""
    validated: list[Sequence[Any]] = []
    for entry in entries:
        if (
            isinstance(entry, (str, bytes, bytearray))
            or not isinstance(entry, Sequence)
            or len(entry) != 2
        ):
            raise GettsimInputError(
                f"{field_name} entries must be two-element index pairs, "
                f"got {entry!r}"
            )
        validated.append(entry)
    return validated


def _pair_items(
    entries: Mapping[Any, Any], field_name: str
) -> list[tuple[Any, Sequence[Any]]]:
    """Each mapping value must be a two-element non-string sequence."""
    validated: list[tuple[Any, Sequence[Any]]] = []
    for key, value in entries.items():
        if (
            isinstance(value, (str, bytes, bytearray))
            or not isinstance(value, Sequence)
            or len(value) != 2
        ):
            raise GettsimInputError(
                f"{field_name} entries must be two-element pairs, "
                f"got {value!r} for {key!r}"
            )
        validated.append((key, value))
    return validated


@dataclass(frozen=True)
class ProjectedInputs:
    """The column-oriented ``data`` and nested ``mapper`` GETTSIM consumes."""

    data: dict[str, list[Any]]
    mapper: dict[str, Any]
    n_persons: int


def flatten_tree(tree: Mapping[str, Any]) -> dict[tuple[str, ...], Any]:
    """Flatten a nested tree to ``{path_tuple: leaf}`` (template or targets).

    Every mapping key on the walk must already be a string — coercing
    non-string keys would invent path names no caller wrote.
    """
    out: dict[tuple[str, ...], Any] = {}

    def _walk(node: Mapping[str, Any], prefix: tuple[str, ...]) -> None:
        for key, value in node.items():
            if not isinstance(key, str):
                raise GettsimInputError(
                    f"tree key {key!r} under {'/'.join(prefix) or '<root>'} must "
                    f"be a string"
                )
            path = prefix + (key,)
            if isinstance(value, Mapping):
                _walk(value, path)
            else:
                out[path] = value

    _walk(tree, ())
    return out


def normalize_person_inputs(person: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten one person's inputs to ``{qualified_name: value}``.

    Nested dicts collapse to ``__``-joined names; already-qualified keys pass
    through (a ``__``-joined key is kept verbatim, not re-split). If the two
    spellings name the same column, the collision raises instead of silently
    keeping whichever was written last.
    """
    flat: dict[str, Any] = {}

    def _set(qname: str, value: Any) -> None:
        if qname in flat:
            raise GettsimInputError(
                f"input column {qname!r} is set twice in one person mapping "
                f"(nested and qualified spellings collide)"
            )
        flat[qname] = value

    for key, value in person.items():
        if not isinstance(key, str):
            raise GettsimInputError(f"person input key {key!r} must be a string")
        if isinstance(value, Mapping):
            for sub_path, sub_value in flatten_tree({key: value}).items():
                _set("__".join(sub_path), sub_value)
        else:
            _set(key, value)
    return flat


def default_value(qualified_name: str, dtype: str) -> Any:
    """The template default for one input column, dtype-first with guards.

    The demographic quartet (``alter``, ``alter_monate``, ``geburtsjahr``,
    ``geburtsmonat``) is *not* defaulted here — those columns are resolved
    jointly against the policy date by :func:`resolve_demographics`.
    """
    leaf = qualified_name.rsplit("__", 1)[-1]
    text = str(dtype)
    if "Bool" in text:
        return False
    if "Float" in text:
        return 0.0
    # Integer columns: apply the value guards, else default 0.
    if qualified_name == "p_id":
        return 0  # overwritten with the person index by the projection
    if "p_id" in leaf:
        return NO_LINK
    if "alter_beginn" in leaf:
        return DEFAULT_ALTER_BEGINN
    if leaf == "jahr_renteneintritt":
        return DEFAULT_RENTENEINTRITT_JAHR
    if leaf == "monat_renteneintritt":
        return DEFAULT_RENTENEINTRITT_MONAT
    if leaf == "steuerklasse":
        return DEFAULT_STEUERKLASSE
    if leaf.endswith("mietstufe_hh"):
        return DEFAULT_MIETSTUFE
    if leaf.endswith("_id"):  # grouping ids: hh_id, wthh_id, bg_id, ...
        return 0
    return 0


def resolve_demographics(
    supplied: Mapping[str, Any],
    policy_date: date,
    *,
    person_index: int,
) -> dict[str, int]:
    """Resolve ``alter``/``alter_monate``/``geburtsjahr``/``geburtsmonat`` jointly.

    One birth date explains all four columns, so the rules are:

    1. A supplied ``geburtsjahr`` fixes the birth date (month from
       ``geburtsmonat``, defaulting to January).
    2. Otherwise a supplied ``alter_monate`` fixes the birth date exactly;
       otherwise a supplied ``alter`` — or :data:`DEFAULT_ALTER` — back-derives
       it, honouring a supplied ``geburtsmonat`` and otherwise placing the
       birthday in the policy month (so ``alter_monate == alter * 12`` for
       age-only cases).
    3. All four columns are then computed from that birth date at month
       precision (the template has no day-of-birth input; the birthday counts
       as passed in the birth month itself).
    4. Any supplied value that disagrees with the computed one raises
       :class:`GettsimInputError` — a contradictory person must never run.

    Returns the resolved ``{leaf: value}`` for the four leaves.
    """
    for leaf in DEMOGRAPHIC_LEAVES:
        if leaf not in supplied:
            continue
        value = supplied[leaf]
        if isinstance(value, bool) or not isinstance(value, int):
            raise GettsimInputError(
                f"person {person_index}: {leaf} must be an integer, got {value!r}"
            )

    if "geburtsmonat" in supplied and not 1 <= supplied["geburtsmonat"] <= 12:
        raise GettsimInputError(
            f"person {person_index}: geburtsmonat {supplied['geburtsmonat']} is "
            f"not in 1..12"
        )

    # Work in total-month indices (year*12 + month-1): one birth index explains
    # every column, and each supply pattern determines it exactly.
    policy_index = policy_date.year * 12 + (policy_date.month - 1)
    if "geburtsjahr" in supplied:
        month = supplied.get("geburtsmonat", DEFAULT_GEBURTSMONAT)
        birth_index = supplied["geburtsjahr"] * 12 + (month - 1)
    elif "alter_monate" in supplied:
        birth_index = policy_index - supplied["alter_monate"]
    elif "alter" in supplied:
        if "geburtsmonat" in supplied:
            month = supplied["geburtsmonat"]
            year = (
                policy_date.year
                - supplied["alter"]
                - (1 if policy_date.month < month else 0)
            )
            birth_index = year * 12 + (month - 1)
        else:
            # Birthday-in-policy-month convention: a supplied age A resolves to
            # exactly A*12 months, so alter and alter_monate stay in lockstep.
            birth_index = policy_index - supplied["alter"] * 12
    elif "geburtsmonat" in supplied:
        # A lone birth month combines with the default age: the default adult
        # born in that month, with the birthday-passed convention deciding the
        # year.
        month = supplied["geburtsmonat"]
        year = (
            policy_date.year
            - DEFAULT_ALTER
            - (1 if policy_date.month < month else 0)
        )
        birth_index = year * 12 + (month - 1)
    else:
        birth_index = policy_index - DEFAULT_ALTER * 12

    alter_monate = policy_index - birth_index
    if alter_monate < 0:
        raise GettsimInputError(
            f"person {person_index}: the supplied demographics place the birth "
            f"after the policy date {policy_date.isoformat()}"
        )
    resolved = {
        "alter": alter_monate // 12,
        "alter_monate": alter_monate,
        "geburtsjahr": birth_index // 12,
        "geburtsmonat": birth_index % 12 + 1,
    }
    for leaf in sorted(DEMOGRAPHIC_LEAVES):
        if leaf in supplied and supplied[leaf] != resolved[leaf]:
            raise GettsimInputError(
                f"person {person_index}: {leaf}={supplied[leaf]} contradicts the "
                f"birth date {resolved['geburtsjahr']}-"
                f"{resolved['geburtsmonat']:02d} at policy date "
                f"{policy_date.isoformat()} (which implies {leaf}="
                f"{resolved[leaf]}). Supply consistent demographics or omit "
                f"the derived ones."
            )
    return resolved


def project_case(
    case: GettsimCase,
    template: Mapping[tuple[str, ...], Any],
    *,
    policy_date: date,
) -> ProjectedInputs:
    """Project a case onto GETTSIM inputs against a flattened template.

    Args:
        case: The household to run.
        template: ``{path_tuple: dtype}`` from
            ``MainTarget.templates.input_data_dtypes.tree`` (flattened).
        policy_date: The policy date the demographics are resolved against.

    Returns:
        A :class:`ProjectedInputs` with per-person ``data`` columns and the
        nested ``mapper``.

    Raises:
        GettsimInputError: If the case has no persons, supplies an input path
            that is neither in the template nor a known grouping id, supplies a
            reserved column (``p_id``, grouping ids inside ``persons``),
            carries contradictory demographics, or declares an invalid
            relationship graph.
    """
    n = case.n_persons
    if n == 0:
        raise GettsimInputError("a GETTSIM case must contain at least one person")

    template_qnames = {"__".join(path): path for path in template}
    demographic_qnames = {
        qname: path[-1]
        for qname, path in (
            ("__".join(path), path) for path in template
        )
        if path[-1] in DEMOGRAPHIC_LEAVES
    }

    # 1. Full template, defaulted per person, with p_id = index. Demographic
    #    columns are placeholder-zeroed here and resolved jointly in step 2.
    data: dict[str, list[Any]] = {}
    for path, dtype in template.items():
        qname = "__".join(path)
        if qname == "p_id":
            data[qname] = list(range(n))
        elif qname in demographic_qnames:
            data[qname] = [0] * n
        else:
            data[qname] = [default_value(qname, dtype) for _ in range(n)]

    # 2. Overlay each person's inputs, validating every path, then resolve the
    #    demographic quartet coherently against the policy date.
    for index, person in enumerate(case.persons):
        flat = normalize_person_inputs(person)
        for qname, value in flat.items():
            if qname == "p_id":
                raise GettsimInputError(
                    f"person {index}: 'p_id' is reserved — person order defines "
                    f"p_id (person i has p_id i)"
                )
            if qname in KNOWN_GROUPING_IDS:
                raise GettsimInputError(
                    f"person {index}: grouping id {qname!r} must be supplied "
                    f"via the case's grouping_ids field, not per person (one "
                    f"channel, no silent overwrites)"
                )
            if qname in STRUCTURED_LINK_COLUMNS:
                raise GettsimInputError(
                    f"person {index}: link column {qname!r} must be set via "
                    f"the structured relationship fields (spouse_pairs / "
                    f"parents / kindergeld_recipients), which validate the "
                    f"graph — raw links can be one-sided or self-referential "
                    f"without error"
                )
            if qname not in template_qnames:
                raise GettsimInputError(
                    f"person {index}: unknown GETTSIM input path {qname!r} "
                    f"(not in the policy-date template; GETTSIM would ignore it "
                    f"silently). Check the spelling against "
                    f"MainTarget.templates.input_data_dtypes.tree."
                )
            if qname not in demographic_qnames:
                data[qname][index] = value
        supplied_demographics = {
            demographic_qnames[qname]: value
            for qname, value in flat.items()
            if qname in demographic_qnames
        }
        resolved = resolve_demographics(
            supplied_demographics, policy_date, person_index=index
        )
        for qname, leaf in demographic_qnames.items():
            data[qname][index] = resolved[leaf]

    # 3. Relationship links (index i has p_id i, so links are the indices).
    _apply_links(case, data, n)

    # 4. Optional explicit grouping ids (complex households; the only channel).
    for gid, per_person in case.grouping_ids.items():
        if gid not in KNOWN_GROUPING_IDS:
            raise GettsimInputError(
                f"unknown grouping id {gid!r}; expected one of "
                f"{sorted(KNOWN_GROUPING_IDS)}"
            )
        if len(per_person) != n:
            raise GettsimInputError(
                f"grouping id {gid!r} has {len(per_person)} values for "
                f"{n} persons"
            )
        data[gid] = list(per_person)

    # 5. Validate the final projected link graph — including link columns that
    #    have no structured channel and were set per person.
    _validate_link_columns(data, n)

    # 6. Build the nested mapper (leaves are the flat column names).
    mapper = _build_mapper(data.keys(), template_qnames)
    return ProjectedInputs(data=data, mapper=mapper, n_persons=n)


def _validate_link_columns(data: Mapping[str, list[Any]], n: int) -> None:
    """Check every projected ``p_id...`` link column against the final graph.

    Applies to raw per-person links (columns without a structured channel,
    e.g. ``bürgergeld__p_id_einstandspartner``) as much as to the structured
    ones: values are ints in ``{-1} ∪ 0..n-1``, never self-referential, and
    every partnership column (:data:`SYMMETRIC_LINK_LEAVES`) must be
    symmetric.
    """
    for qname, column in data.items():
        leaf = qname.rsplit("__", 1)[-1]
        if qname == "p_id" or "p_id" not in leaf:
            continue
        for index, value in enumerate(column):
            if isinstance(value, bool) or not isinstance(value, int):
                raise GettsimInputError(
                    f"link column {qname!r} for person {index} must be an "
                    f"integer person index or {NO_LINK}, got {value!r}"
                )
            if value == NO_LINK:
                continue
            if value < 0 or value >= n:
                raise GettsimInputError(
                    f"link column {qname!r} for person {index} references "
                    f"person index {value}, outside 0..{n - 1}"
                )
            if value == index:
                raise GettsimInputError(
                    f"link column {qname!r} links person {index} to itself"
                )
    for qname, column in data.items():
        if qname.rsplit("__", 1)[-1] not in SYMMETRIC_LINK_LEAVES:
            continue
        for index, partner in enumerate(column):
            if partner != NO_LINK and column[partner] != index:
                raise GettsimInputError(
                    f"{qname} is asymmetric: person {index} links to "
                    f"{partner}, but person {partner} links to "
                    f"{column[partner]}"
                )


def _apply_links(case: GettsimCase, data: dict[str, list[Any]], n: int) -> None:
    def link_column(qname: str) -> list[Any]:
        return data.setdefault(qname, [NO_LINK] * n)

    linked: set[int] = set()
    for pair in case.spouse_pairs:
        if (
            isinstance(pair, (str, bytes, bytearray))
            or not isinstance(pair, Sequence)
            or len(pair) != 2
        ):
            raise GettsimInputError(
                f"spouse_pairs entries must be (left, right) index pairs, "
                f"got {pair!r}"
            )
        left, right = pair
        _check_index(left, n, "spouse_pairs")
        _check_index(right, n, "spouse_pairs")
        if left == right:
            raise GettsimInputError(
                f"spouse_pairs pairs person {left} with itself"
            )
        for person in (left, right):
            if person in linked:
                raise GettsimInputError(
                    f"spouse_pairs links person {person} more than once — "
                    f"ehepartner links are monogamous"
                )
            linked.add(person)
        column = link_column("familie__p_id_ehepartner")
        column[left] = right
        column[right] = left

    for child, parent_pair in case.parents.items():
        if (
            isinstance(parent_pair, (str, bytes, bytearray))
            or not isinstance(parent_pair, Sequence)
            or len(parent_pair) != 2
        ):
            raise GettsimInputError(
                f"parents entries must be (parent_1, parent_2) pairs "
                f"(either may be None), got {parent_pair!r} for child {child!r}"
            )
        parent_1, parent_2 = parent_pair
        _check_index(child, n, "parents")
        for parent in (parent_1, parent_2):
            if parent is None:
                continue
            _check_index(parent, n, "parents")
            if parent == child:
                raise GettsimInputError(
                    f"parents makes person {child} its own parent"
                )
        if parent_1 is not None and parent_1 == parent_2:
            raise GettsimInputError(
                f"parents lists person {parent_1} as both parents of "
                f"person {child}"
            )
        if parent_1 is not None:
            link_column("familie__p_id_elternteil_1")[child] = parent_1
        if parent_2 is not None:
            link_column("familie__p_id_elternteil_2")[child] = parent_2

    for child, recipient in case.kindergeld_recipients.items():
        _check_index(child, n, "kindergeld_recipients")
        _check_index(recipient, n, "kindergeld_recipients")
        link_column("kindergeld__p_id_empfänger")[child] = recipient


def _build_mapper(
    columns: Any,
    template_qnames: Mapping[str, tuple[str, ...]],
) -> dict[str, Any]:
    mapper: dict[str, Any] = {}
    for qname in columns:
        path = template_qnames.get(qname, (qname,))  # grouping ids are top-level
        node = mapper
        for segment in path[:-1]:
            node = node.setdefault(segment, {})
        node[path[-1]] = qname
    return mapper


def _check_index(index: Any, n: int, field_name: str) -> None:
    if (
        isinstance(index, bool)
        or not isinstance(index, int)
        or index < 0
        or index >= n
    ):
        raise GettsimInputError(
            f"{field_name} references person index {index!r}, outside 0..{n - 1}"
        )
