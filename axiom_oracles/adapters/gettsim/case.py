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
GETTSIM's per-target input templates miss transitive dependencies, so the
reliable route is to discover the *full* template
(``MainTarget.templates.input_data_dtypes.tree``) once and default every column,
then overlay the case. The defaulting rules below are dtype-first, with a small
set of value guards that GETTSIM's table lookups require:

- bool columns default ``False``; float columns default ``0.0``;
- ``p_id`` is the person's 0-based index;
- every *other* ``p_id...`` link column defaults ``-1`` (no link);
- ``geburtsjahr`` and ``alter`` are case demographics (defaults
  :data:`DEFAULT_GEBURTSJAHR` / :data:`DEFAULT_ALTER`), overridable per person;
- ``alter_beginn_*`` columns are **ages**, not years — a year there overruns the
  §22 Ertragsanteil table (size 121), so they default to
  :data:`DEFAULT_ALTER_BEGINN` (65);
- ``jahr_renteneintritt`` is a **year** — ``0`` underruns the Besteuerungsanteil
  table (indexed ``year - 1940``), so it defaults to
  :data:`DEFAULT_RENTENEINTRITT_JAHR` (2020);
- ``steuerklasse`` defaults to 1 and ``mietstufe_hh`` to 3 (valid lookup keys);
- grouping ``*_id`` columns default ``0`` (one household / one group).

Note the substring ``"jahr"`` is *not* used to detect years: several template
columns carry it while being booleans (``bürgergeld__bezug_im_vorjahr``) or
money amounts (``...vorjahr_y``), so the rules key on exact leaf names and
dtype instead.

Grouping ids
------------
At the 2025 policy dates only ``hh_id`` is an *input* column; GETTSIM derives the
finer ``wthh_id``/``bg_id``/``eg_id``/``fg_id``/``sn_id`` from ``hh_id`` and the
family links. Its own guidance is that this derivation is correct only when there
is exactly one Familien-/Bedarfsgemeinschaft per household; complex households
(multiple families, self-supporting children) must supply the finer ids
directly. The case therefore accepts an optional ``grouping_ids`` override for
any of :data:`KNOWN_GROUPING_IDS`, which the projection adds as explicit input
columns even though they are absent from the default template.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .errors import GettsimInputError

#: Demographic defaults (Int columns that are really case facts).
DEFAULT_GEBURTSJAHR = 1980
DEFAULT_GEBURTSMONAT = 1
DEFAULT_ALTER = 40
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


@dataclass(frozen=True)
class GettsimCase:
    """A hypothetical German household in the GETTSIM oracle's input language.

    Args:
        persons: One mapping per person, each holding that person's GETTSIM
            input overrides. Keys may be qualified column names
            (``"einnahmen__bruttolohn_m"``) or nested dicts
            (``{"einnahmen": {"bruttolohn_m": 4000.0}}``); the two forms mix
            freely. Person order defines ``p_id`` (person ``i`` has ``p_id`` i).
        spouse_pairs: ``(i, j)`` index pairs joined by
            ``familie__p_id_ehepartner`` (set symmetrically). Joint assessment
            itself is a separate input (``einkommensteuer__gemeinsam_veranlagt``)
            the persons carry, so a pair links the spouses without presuming how
            they file.
        parents: Child index → ``(parent_1_index, parent_2_index)``; either
            parent may be ``None``. Sets ``familie__p_id_elternteil_1/2``.
        kindergeld_recipients: Child index → recipient index, setting
            ``kindergeld__p_id_empfänger`` (who is paid the child's Kindergeld).
        grouping_ids: Optional per-person id overrides for any of
            :data:`KNOWN_GROUPING_IDS`, for complex households where GETTSIM's
            derivation from ``hh_id`` is not valid. Each value is a list with one
            entry per person.
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

        Accepts the same fields as the constructor (``persons`` required) so a
        suite can carry a case as JSON-ish data and still get validation.
        """
        if "persons" not in spec:
            raise GettsimInputError(
                "a GETTSIM case mapping must contain a 'persons' list"
            )
        return cls(
            persons=list(spec["persons"]),
            spouse_pairs=[tuple(pair) for pair in spec.get("spouse_pairs", ())],
            parents={int(k): tuple(v) for k, v in spec.get("parents", {}).items()},
            kindergeld_recipients={
                int(k): int(v)
                for k, v in spec.get("kindergeld_recipients", {}).items()
            },
            grouping_ids={
                str(k): list(v) for k, v in spec.get("grouping_ids", {}).items()
            },
        )


@dataclass(frozen=True)
class ProjectedInputs:
    """The column-oriented ``data`` and nested ``mapper`` GETTSIM consumes."""

    data: dict[str, list[Any]]
    mapper: dict[str, Any]
    n_persons: int


def flatten_tree(tree: Mapping[str, Any]) -> dict[tuple[str, ...], Any]:
    """Flatten a nested tree to ``{path_tuple: leaf}`` (template or targets)."""
    out: dict[tuple[str, ...], Any] = {}

    def _walk(node: Mapping[str, Any], prefix: tuple[str, ...]) -> None:
        for key, value in node.items():
            path = prefix + (str(key),)
            if isinstance(value, Mapping):
                _walk(value, path)
            else:
                out[path] = value

    _walk(tree, ())
    return out


def normalize_person_inputs(person: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten one person's inputs to ``{qualified_name: value}``.

    Nested dicts collapse to ``__``-joined names; already-qualified keys pass
    through. A key that is itself a ``__``-joined name is kept verbatim (it is
    not re-split), so the two spellings never collide.
    """
    flat: dict[str, Any] = {}
    for key, value in person.items():
        if isinstance(value, Mapping):
            for sub_path, sub_value in flatten_tree({key: value}).items():
                flat["__".join(sub_path)] = sub_value
        else:
            flat[str(key)] = value
    return flat


def default_value(qualified_name: str, dtype: str) -> Any:
    """The template default for one input column, dtype-first with guards."""
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
    if qualified_name == "geburtsjahr":
        return DEFAULT_GEBURTSJAHR
    if leaf == "geburtsmonat":
        return DEFAULT_GEBURTSMONAT
    if qualified_name == "alter":
        return DEFAULT_ALTER
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


def project_case(
    case: GettsimCase,
    template: Mapping[tuple[str, ...], Any],
) -> ProjectedInputs:
    """Project a case onto GETTSIM inputs against a flattened template.

    Args:
        case: The household to run.
        template: ``{path_tuple: dtype}`` from
            ``MainTarget.templates.input_data_dtypes.tree`` (flattened).

    Returns:
        A :class:`ProjectedInputs` with per-person ``data`` columns and the
        nested ``mapper``.

    Raises:
        GettsimInputError: If the case has no persons, or supplies an input
            path that is neither in the template nor a known grouping id.
    """
    n = case.n_persons
    if n == 0:
        raise GettsimInputError("a GETTSIM case must contain at least one person")

    template_qnames = {"__".join(path): path for path in template}

    # 1. Full template, defaulted per person, with p_id = index.
    data: dict[str, list[Any]] = {}
    for path, dtype in template.items():
        qname = "__".join(path)
        if qname == "p_id":
            data[qname] = list(range(n))
        else:
            data[qname] = [default_value(qname, dtype) for _ in range(n)]

    # 2. Overlay each person's inputs, validating every path.
    for index, person in enumerate(case.persons):
        for qname, value in normalize_person_inputs(person).items():
            if qname not in template_qnames and qname not in KNOWN_GROUPING_IDS:
                raise GettsimInputError(
                    f"person {index}: unknown GETTSIM input path {qname!r} "
                    f"(not in the policy-date template; GETTSIM would ignore it "
                    f"silently). Check the spelling against "
                    f"MainTarget.templates.input_data_dtypes.tree."
                )
            column = data.setdefault(qname, [_zero_like(value)] * n)
            column[index] = value

    # 3. Relationship links (index i has p_id i, so links are the indices).
    _apply_links(case, data, n)

    # 4. Optional explicit grouping ids (complex households).
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

    # 5. Build the nested mapper (leaves are the flat column names).
    mapper = _build_mapper(data.keys(), template_qnames)
    return ProjectedInputs(data=data, mapper=mapper, n_persons=n)


def _apply_links(case: GettsimCase, data: dict[str, list[Any]], n: int) -> None:
    def link_column(qname: str) -> list[Any]:
        return data.setdefault(qname, [NO_LINK] * n)

    for left, right in case.spouse_pairs:
        _check_index(left, n, "spouse_pairs")
        _check_index(right, n, "spouse_pairs")
        column = link_column("familie__p_id_ehepartner")
        column[left] = right
        column[right] = left

    for child, (parent_1, parent_2) in case.parents.items():
        _check_index(child, n, "parents")
        if parent_1 is not None:
            _check_index(parent_1, n, "parents")
            link_column("familie__p_id_elternteil_1")[child] = parent_1
        if parent_2 is not None:
            _check_index(parent_2, n, "parents")
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


def _check_index(index: int, n: int, field_name: str) -> None:
    if not isinstance(index, int) or index < 0 or index >= n:
        raise GettsimInputError(
            f"{field_name} references person index {index!r}, outside 0..{n - 1}"
        )


def _zero_like(value: Any) -> Any:
    if isinstance(value, bool):
        return False
    if isinstance(value, float):
        return 0.0
    if isinstance(value, int):
        return 0
    return value
