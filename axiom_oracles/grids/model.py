"""Grid schema data structures and loader.

The on-disk shape of ``grids/<jurisdiction>.yaml``::

    schema_version: axiom-oracles/case-grid/v1
    jurisdiction: be
    generated_from:
      suites_module: axiom_oracles.suites
      extractor: scripts/extract_grids.py
    case_sets:
      be-employer-ssc:                   # a named case set (== a suite name)
        description: Single-worker Belgium employer-SSC cases ...
        locale: BE
        entity: Person                   # default Axiom query entity for the set
        entity_id: head
        outputs:                         # oracle-neutral output concept ids
          - be:regulations/.../employer_contributions#belgium_employer_...
        cases:
          - id: be-employer-ssc-30k
            period: "2025"
            scenario: single-worker-employer-ssc
            parameters:                  # typed, oracle-neutral scenario inputs
              yearly_earned_income: 30000
            entities:                    # optional; only when the set varies it
              - id: head
                kind: person
                age: 35
                relation: HeadOfHousehold
                yearly_earned_income: 30000

``parameters`` are the oracle-neutral scenario values a suite already keeps in
case metadata (income, child age, region, single-parent flag, ...). ``entities``
mirror the case entity tree using the neutral age/relation vocabulary, and are
only emitted when a set's households actually vary (so a fixed-shape set stays
compact). Everything an oracle needs beyond the skeleton — the RuleSpec
``#input.`` projection, the EUROMOD variable rows, the input bridge — is
re-derived by the suite factory, not stored here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Bump when the *file schema* changes shape (fields, nesting), independent of a
# grid's content revisions.
GRID_SCHEMA_VERSION = "axiom-oracles/case-grid/v1"

# Directory holding the checked-in grid files, at the repo root next to
# ``comparisons/``. Resolved relative to this module so it works from an
# editable install and a wheel alike.
DEFAULT_GRID_ROOT = Path(__file__).resolve().parents[2] / "grids"


@dataclass(frozen=True)
class EntitySpec:
    """One person (or other entity) in a case's household skeleton.

    ``extra`` carries any neutral per-entity facts beyond age/relation that a
    case sets (e.g. income on a non-head, a pregnancy flag), keyed by the short
    neutral name used in the grid file.
    """

    id: str
    kind: str = "person"
    age: int | None = None
    relation: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CaseSpec:
    """The oracle-neutral skeleton of one case."""

    id: str
    period: str
    scenario: str | None = None
    outputs: tuple[str, ...] = ()
    entity: str | None = None
    entity_id: str | None = None
    parameters: Mapping[str, Any] = field(default_factory=dict)
    entities: tuple[EntitySpec, ...] = ()
    facts: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CaseSet:
    """A named set of cases sharing an output surface and query entity.

    The set name is the durable handle a comparison config references (it is the
    same string as the suite name it was extracted from). Suite-specific one-off
    cases are not stored here: a config that needs extras references this
    canonical set and appends its own inline cases alongside it (see
    ``comparisons/README.md``), keeping the shared grid clean.
    """

    name: str
    description: str | None
    locale: str | None
    entity: str | None
    entity_id: str | None
    outputs: tuple[str, ...]
    cases: tuple[CaseSpec, ...]

    def case(self, case_id: str) -> CaseSpec | None:
        for case in self.cases:
            if case.id == case_id:
                return case
        return None


@dataclass(frozen=True)
class Grid:
    """The case sets + provenance from one jurisdiction grid file."""

    jurisdiction: str
    schema_version: str
    generated_from: Mapping[str, Any]
    case_sets: tuple[CaseSet, ...]
    source_file: Path | None = None

    def case_set(self, name: str) -> CaseSet | None:
        for case_set in self.case_sets:
            if case_set.name == name:
                return case_set
        return None

    @property
    def case_set_names(self) -> tuple[str, ...]:
        return tuple(case_set.name for case_set in self.case_sets)

    def validate(self) -> list[str]:
        """Structural checks. Returns human-readable issue strings."""
        issues: list[str] = []
        seen_sets: set[str] = set()
        for case_set in self.case_sets:
            if case_set.name in seen_sets:
                issues.append(f"duplicate case set {case_set.name!r}")
            seen_sets.add(case_set.name)
            seen_cases: set[str] = set()
            for case in case_set.cases:
                if case.id in seen_cases:
                    issues.append(
                        f"{case_set.name}: duplicate case id {case.id!r}"
                    )
                seen_cases.add(case.id)
                if not case.period:
                    issues.append(f"{case_set.name}/{case.id}: missing period")
                for entity in case.entities:
                    if not entity.id:
                        issues.append(
                            f"{case_set.name}/{case.id}: entity missing id"
                        )
        return issues


# Per-entity keys that map to a first-class EntitySpec field rather than into
# ``extra``. Everything else on an entity mapping is a neutral fact.
_ENTITY_RESERVED = frozenset({"id", "kind", "age", "relation"})


def load_grid_file(path: Path) -> Grid:
    """Parse one ``grids/<jurisdiction>.yaml`` file into a :class:`Grid`."""
    payload = yaml.safe_load(path.read_text()) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: grid file must be a mapping")

    schema_version = payload.get("schema_version")
    if schema_version != GRID_SCHEMA_VERSION:
        raise ValueError(
            f"{path}: unsupported schema_version {schema_version!r} "
            f"(expected {GRID_SCHEMA_VERSION!r})"
        )

    jurisdiction = str(payload.get("jurisdiction") or path.stem)
    generated_from = payload.get("generated_from") or {}
    if not isinstance(generated_from, dict):
        raise ValueError(f"{path}: generated_from must be a mapping")

    raw_case_sets = payload.get("case_sets") or {}
    if not isinstance(raw_case_sets, dict):
        raise ValueError(f"{path}: case_sets must be a mapping keyed by set name")

    case_sets = tuple(
        _case_set_from_payload(name, body, source_file=path)
        for name, body in raw_case_sets.items()
    )
    grid = Grid(
        jurisdiction=jurisdiction,
        schema_version=str(schema_version),
        generated_from=generated_from,
        case_sets=case_sets,
        source_file=path,
    )
    issues = grid.validate()
    if issues:
        raise ValueError(f"{path}: invalid grid: " + "; ".join(issues))
    return grid


def load_grid(jurisdiction: str, grid_root: Path | None = None) -> Grid:
    """Load a single jurisdiction grid by name (``us``, ``be``, ``uk``)."""
    root = grid_root or DEFAULT_GRID_ROOT
    path = root / f"{jurisdiction}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No grid file for jurisdiction {jurisdiction!r}: {path}")
    return load_grid_file(path)


def resolve_grid_case_set(
    reference: str,
    grid_root: Path | None = None,
) -> tuple[Grid, CaseSet]:
    """Resolve a ``<jurisdiction>:<case-set>`` (or bare ``<case-set>``) reference.

    This is the hook a comparison config or suite uses to say "my cases are the
    canonical grid set, not an inline copy". A bare name is resolved by scanning
    every grid for a case set of that name (case-set names are globally unique
    across jurisdictions, matching the suite-name namespace). Raises with a
    clear message if the reference does not resolve.
    """
    if ":" in reference:
        jurisdiction, _, set_name = reference.partition(":")
        grid = load_grid(jurisdiction.strip(), grid_root)
        case_set = grid.case_set(set_name.strip())
        if case_set is None:
            raise KeyError(
                f"grid {jurisdiction!r} has no case set {set_name!r}; "
                f"available: {list(grid.case_set_names)}"
            )
        return grid, case_set

    set_name = reference.strip()
    matches: list[tuple[Grid, CaseSet]] = []
    for grid in load_grids(grid_root):
        case_set = grid.case_set(set_name)
        if case_set is not None:
            matches.append((grid, case_set))
    if not matches:
        raise KeyError(f"no grid case set named {set_name!r}")
    if len(matches) > 1:
        raise KeyError(
            f"case set {set_name!r} is ambiguous across grids "
            f"{[g.jurisdiction for g, _ in matches]}; qualify as "
            "'<jurisdiction>:<case-set>'"
        )
    return matches[0]


def load_grids(grid_root: Path | None = None) -> tuple[Grid, ...]:
    """Load every ``*.yaml`` grid under ``grid_root`` (default packaged root).

    ``*.suggested.yaml`` files (the boundary-case generator output) are skipped
    — they are proposals for human adoption, not adopted grids.
    """
    root = grid_root or DEFAULT_GRID_ROOT
    grids: list[Grid] = []
    for path in sorted(root.glob("*.yaml")):
        if path.name.endswith(".suggested.yaml"):
            continue
        grids.append(load_grid_file(path))
    return tuple(grids)


def _case_set_from_payload(
    name: str,
    body: Any,
    *,
    source_file: Path,
) -> CaseSet:
    if not isinstance(body, dict):
        raise ValueError(f"{source_file}: case set {name!r} must be a mapping")
    raw_cases = body.get("cases") or []
    if not isinstance(raw_cases, list):
        raise ValueError(f"{source_file}: case set {name!r} cases must be a list")
    return CaseSet(
        name=str(name),
        description=_opt_str(body.get("description")),
        locale=_opt_str(body.get("locale")),
        entity=_opt_str(body.get("entity")),
        entity_id=_opt_str(body.get("entity_id")),
        outputs=_str_tuple(body.get("outputs")),
        cases=tuple(
            _case_from_payload(raw, set_name=name, source_file=source_file)
            for raw in raw_cases
        ),
    )


def _case_from_payload(payload: Any, *, set_name: str, source_file: Path) -> CaseSpec:
    if not isinstance(payload, dict):
        raise ValueError(f"{source_file}: {set_name}: each case must be a mapping")
    if "id" not in payload:
        raise ValueError(f"{source_file}: {set_name}: case missing 'id': {payload!r}")
    if "period" not in payload:
        raise ValueError(
            f"{source_file}: {set_name}: case {payload['id']!r} missing 'period'"
        )
    return CaseSpec(
        id=str(payload["id"]),
        period=str(payload["period"]),
        scenario=_opt_str(payload.get("scenario")),
        outputs=_str_tuple(payload.get("outputs")),
        entity=_opt_str(payload.get("entity")),
        entity_id=_opt_str(payload.get("entity_id")),
        parameters=dict(payload.get("parameters") or {}),
        entities=tuple(
            _entity_from_payload(raw, source_file=source_file)
            for raw in (payload.get("entities") or [])
        ),
        facts=dict(payload.get("facts") or {}),
    )


def _entity_from_payload(payload: Any, *, source_file: Path) -> EntitySpec:
    if not isinstance(payload, dict):
        raise ValueError(f"{source_file}: each entity must be a mapping")
    if "id" not in payload:
        raise ValueError(f"{source_file}: entity missing 'id': {payload!r}")
    extra = {
        key: value
        for key, value in payload.items()
        if key not in _ENTITY_RESERVED
    }
    age = payload.get("age")
    return EntitySpec(
        id=str(payload["id"]),
        kind=str(payload.get("kind") or "person"),
        age=int(age) if age is not None else None,
        relation=_opt_str(payload.get("relation")),
        extra=extra,
    )


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _str_tuple(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)
