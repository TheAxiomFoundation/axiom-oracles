"""Per-suite runnable-program compositions behind conformance coverage.

A conformance-covered policy points at an Axiom comparison *suite*, but the
committed universe records only the suite *name* — not the runnable Axiom
program the harness executes to produce the covered comparison report. That
program is assembled implicitly at run time from the suite's output concepts
(``axiom_oracles.cli`` derives the RuleSpec import-set from the ``module#name``
prefixes of each case's requested outputs). Nothing consumable records it, so
the conformance verdict cannot be reproduced outside the harness and a
population run cannot reuse the identical program without re-deriving it.

This module makes that composition an explicit, machine-readable artifact.
:func:`composition_for_suite` derives the same import-set the CLI runner builds
(:func:`rulespec_imports_for_concepts` is the single shared source both use),
plus the query entity and the supplied-input surface, straight from the suite
definition. :mod:`scripts.generate_conformance_compositions` serialises the set
into ``conformance/compositions/<jur>.yaml`` and a CI ``--check`` fails if the
committed record drifts from the suites — so the record cannot silently diverge
from what actually runs.

The composition for every committed EUROMOD-lane BE suite is a **single**
top-level RuleSpec module (which transitively imports its own stages); the one
exception is ``be-worker-ssc``, whose three outputs span two modules
(``employee_contributions`` + ``work_bonus``). Notably the marital-quotient
slice is *not* front-chained with the SSC/forfait stages — it runs the lone
``couple_pit_oracle_pipeline`` module and its residual against EUROMOD ``tin_s``
is carried by dispositions, not by a wider program (see
``conformance/README.md`` § "Recorded program compositions").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping
import re

import yaml

from axiom_oracles.bridges.repo_routing import (
    RULESPEC_ATOMIC_ROOTS,
    jurisdiction_country,
)
from axiom_oracles.bridges.rulespec_paths import require_rulespec_checkout


COMPOSITIONS_SCHEMA_VERSION = "axiom_oracles.compositions.v1"

# The metadata keys the suites use to carry the Axiom projection facts. Kept in
# sync with axiom_oracles.suites and the AxiomRulesRunner.
_AXIOM_ENTITY_KEY = "axiom_entity"
_AXIOM_ENTITY_ID_KEY = "axiom_entity_id"
_AXIOM_INPUTS_KEY = "axiom_inputs"
_INPUT_BRIDGE_KEY = "euromod_to_axiom_input_bridge"


def rulespec_imports_for_concepts(concept_ids: tuple[str, ...]) -> tuple[str, ...]:
    """Distinct RuleSpec module refs backing a set of ``module#name`` concepts.

    This is the exact derivation ``axiom_oracles.cli._build_runner`` uses to
    build the Axiom runner's ``program_imports`` when ``--axiom-program`` is not
    supplied: the ordered, de-duplicated set of ``<prefix>:<path>`` module
    prefixes across the requested output concepts. Keeping it here makes the CLI
    runner and the recorded composition share one source of truth, so the record
    is a faithful description of what the harness actually compiles.
    """

    imports: list[str] = []
    for concept_id in concept_ids:
        module_ref = str(concept_id).split("#", maxsplit=1)[0]
        if ":" not in module_ref or not module_ref:
            continue
        if module_ref not in imports:
            imports.append(module_ref)
    return tuple(imports)


def repo_relative_program_path(module_ref: str) -> str:
    """Repo-relative path a ``<prefix>:<path>`` module resolves to.

    Uses the monorepo layout the oracle bridge resolves against:
    ``rulespec-<country>/<prefix>/<path>.yaml`` (``be-vlg:...`` →
    ``rulespec-be/be-vlg/...``). The country is the prefix up to its first ``-``.
    """

    if ":" not in module_ref:
        raise ValueError(f"module ref must be '<prefix>:<path>', got {module_ref!r}")
    prefix, relative = module_ref.split(":", maxsplit=1)
    relative = relative.strip("/")
    if not prefix or not relative:
        raise ValueError(f"module ref must be '<prefix>:<path>', got {module_ref!r}")
    country = jurisdiction_country(prefix)
    first = relative.split("/", maxsplit=1)[0]
    if first not in RULESPEC_ATOMIC_ROOTS:
        raise ValueError(
            f"module ref must use one of the four atomic roots, got {module_ref!r}"
        )
    if re.fullmatch(rf"{re.escape(country)}(?:-[a-z0-9]+)*", prefix) is None:
        raise ValueError(f"invalid jurisdiction prefix in module ref {module_ref!r}")
    return f"{prefix}/{relative}.yaml"


@dataclass
class SuiteComposition:
    """The runnable Axiom program behind one conformance-covered suite.

    * ``imports`` — the RuleSpec module import-set the harness composes (the
      ``program_imports`` of the generated program); ``target`` is the primary
      one (``imports[0]``, the ``generated_program_target``).
    * ``paths`` — the repo-relative file each import resolves to inside the
      rulespec checkout, so the program is reproducible as concrete files.
    * ``entity`` / ``entity_id`` — the query entity the suite pins for every
      case (``TaxUnit`` for the marital-quotient couple, ``Person`` for a
      single worker, ``Household`` / ``Family`` / ``Property`` elsewhere).
    * ``supplied_input_boundaries`` — the ``module#input.name`` refs the suite
      supplies as case inputs (the program's expected supplied surface).
    * ``input_bridge`` — the engine-output → supplied-input map the harness
      applies on top of the static case inputs (the supplied defaults *beyond*
      the suite's own ``axiom_inputs``; e.g. EUROMOD ``yem`` overriding the
      Article-89 professional-income boundary).
    """

    suite: str
    entity: str
    entity_id: str
    target: str
    imports: tuple[str, ...]
    paths: tuple[str, ...]
    outputs: tuple[str, ...]
    supplied_input_boundaries: tuple[str, ...]
    input_bridge: dict[str, tuple[str, ...]]
    policy: str | None = None

    def to_row(self) -> dict:
        row: dict = {"suite": self.suite}
        if self.policy:
            row["policy"] = self.policy
        row["entity"] = self.entity
        row["entity_id"] = self.entity_id
        row["program"] = {
            "target": self.target,
            "imports": list(self.imports),
            "paths": list(self.paths),
        }
        row["outputs"] = list(self.outputs)
        if self.supplied_input_boundaries:
            row["supplied_input_boundaries"] = list(self.supplied_input_boundaries)
        if self.input_bridge:
            row["input_bridge"] = {
                engine_var: list(refs)
                for engine_var, refs in sorted(self.input_bridge.items())
            }
        return row

    @classmethod
    def from_row(cls, row: Mapping) -> "SuiteComposition":
        program = row.get("program") or {}
        bridge_raw = row.get("input_bridge") or {}
        return cls(
            suite=row["suite"],
            policy=row.get("policy"),
            entity=row["entity"],
            entity_id=row["entity_id"],
            target=program["target"],
            imports=tuple(program.get("imports") or ()),
            paths=tuple(program.get("paths") or ()),
            outputs=tuple(row.get("outputs") or ()),
            supplied_input_boundaries=tuple(row.get("supplied_input_boundaries") or ()),
            input_bridge={str(k): tuple(v) for k, v in bridge_raw.items()},
        )

    def resolve(self, rulespec_root: str | Path) -> "ResolvedComposition":
        """Bind ``paths`` to absolute files under a rulespec checkout root."""
        countries = {jurisdiction_country(ref.split(":", 1)[0]) for ref in self.imports}
        if len(countries) != 1:
            raise ValueError("a composition must import exactly one RuleSpec country")
        country = countries.pop()
        root = normalize_rulespec_root(rulespec_root, country=country)
        expected_paths = tuple(repo_relative_program_path(ref) for ref in self.imports)
        if self.paths != expected_paths:
            raise ValueError(
                f"composition {self.suite!r} paths do not match its canonical imports"
            )
        return ResolvedComposition(
            composition=self,
            root=root,
            program_paths=tuple(root / rel for rel in self.paths),
        )


@dataclass
class ResolvedComposition:
    """A :class:`SuiteComposition` with its module files bound to a checkout."""

    composition: SuiteComposition
    root: Path
    program_paths: tuple[Path, ...]

    @property
    def single_program_path(self) -> Path | None:
        """The lone concrete program file, when the composition is one module.

        Multi-module compositions (only ``be-worker-ssc`` today) have no single
        file — callers fall back to the import-set the harness composes.
        """
        if len(self.program_paths) == 1:
            return self.program_paths[0]
        return None

    def missing_paths(self) -> tuple[Path, ...]:
        return tuple(p for p in self.program_paths if not p.exists())


def normalize_rulespec_root(
    rulespec_root: str | Path,
    *,
    country: str | None = None,
) -> Path:
    """Require one explicit canonical country checkout.

    Workspace parents, flat jurisdiction checkouts, aliases, and environment
    fallbacks are intentionally unsupported.
    """

    return require_rulespec_checkout(Path(rulespec_root), country=country)


def _single_metadata_value(cases, key: str, suite: str) -> str:
    values = {str(case.metadata.get(key)) for case in cases if case.metadata.get(key)}
    if not values:
        raise ValueError(f"suite {suite!r} sets no {key!r} on its cases")
    if len(values) != 1:
        raise ValueError(
            f"suite {suite!r} mixes {key!r} across cases ({sorted(values)}); "
            "a covered suite must pin one query entity"
        )
    return next(iter(values))


def composition_for_suite(suite: str) -> SuiteComposition:
    """Derive the runnable composition a suite's cases request.

    Loads the suite's cases (pure data — no engine) and reads off the same
    facts the CLI runner uses: the output concepts, the import-set
    (:func:`rulespec_imports_for_concepts`), the pinned query entity, the
    supplied-input surface, and the engine→input bridge. Import-only; safe to
    call in tests and generators.
    """

    from axiom_oracles.suites import load_suite

    cases = load_suite(suite)
    if not cases:
        raise ValueError(f"suite {suite!r} loaded no cases")

    outputs: list[str] = []
    for case in cases:
        for output in case.outputs:
            if output not in outputs:
                outputs.append(output)
    outputs.sort()

    imports = rulespec_imports_for_concepts(tuple(outputs))
    if not imports:
        raise ValueError(
            f"suite {suite!r} outputs derive no RuleSpec imports ({outputs})"
        )

    supplied: set[str] = set()
    bridge: dict[str, set[str]] = {}
    for case in cases:
        for name in case.metadata.get(_AXIOM_INPUTS_KEY) or {}:
            supplied.add(str(name))
        for engine_var, refs in (case.metadata.get(_INPUT_BRIDGE_KEY) or {}).items():
            bridge.setdefault(str(engine_var), set()).update(str(r) for r in refs)

    return SuiteComposition(
        suite=suite,
        entity=_single_metadata_value(cases, _AXIOM_ENTITY_KEY, suite),
        entity_id=_single_metadata_value(cases, _AXIOM_ENTITY_ID_KEY, suite),
        target=imports[0],
        imports=imports,
        paths=tuple(repo_relative_program_path(ref) for ref in imports),
        outputs=tuple(outputs),
        supplied_input_boundaries=tuple(sorted(supplied)),
        input_bridge={var: tuple(sorted(refs)) for var, refs in bridge.items()},
    )


# ---------------------------------------------------------------------------
# Document (per-jurisdiction record) load / build / serialise
# ---------------------------------------------------------------------------


@dataclass
class CompositionsDocument:
    """A parsed ``conformance/compositions/<jur>.yaml`` record."""

    jurisdiction: str
    oracle: dict
    compositions: list[SuiteComposition] = field(default_factory=list)

    def by_suite(self) -> dict[str, SuiteComposition]:
        return {c.suite: c for c in self.compositions}


def build_compositions_document(jurisdiction: str) -> CompositionsDocument:
    """Assemble the record for every covered suite in a committed universe.

    Reads ``conformance/<jur>.yaml`` for the covered (in-scope + suite-named)
    policies and the oracle identity header, then derives each suite's
    composition from the suites code. Covered suites appear once even if two
    universe rows name the same suite (none do today).
    """

    from axiom_oracles.conformance.loader import parse as parse_universe

    universe_path = _conformance_dir() / f"{jurisdiction}.yaml"
    universe = parse_universe(universe_path)

    suite_to_policy: dict[str, str] = {}
    for policy in universe.in_scope():
        if policy.suite and policy.suite not in suite_to_policy:
            suite_to_policy[policy.suite] = policy.id

    compositions: list[SuiteComposition] = []
    for suite in sorted(suite_to_policy):
        comp = composition_for_suite(suite)
        comp.policy = suite_to_policy[suite]
        compositions.append(comp)

    return CompositionsDocument(
        jurisdiction=universe.jurisdiction,
        oracle=universe.oracle.to_header(),
        compositions=compositions,
    )


def _represent_ordered(dumper: yaml.Dumper, data: dict) -> yaml.nodes.MappingNode:
    return dumper.represent_mapping("tag:yaml.org,2002:map", data.items())


class _CompositionsDumper(yaml.Dumper):
    """Ordered-mapping, indented-sequence dumper (mirrors the universe dumper)."""

    def increase_indent(self, flow: bool = False, indentless: bool = False):
        return super().increase_indent(flow, False)


_CompositionsDumper.add_representer(dict, _represent_ordered)


_HEADER = (
    f"# {COMPOSITIONS_SCHEMA_VERSION} — GENERATED, do NOT hand-edit.\n"
    "# The runnable Axiom program behind each conformance-covered suite: the\n"
    "# RuleSpec import-set the harness composes (identical to what\n"
    "# axiom_oracles.cli builds when --axiom-program is omitted), its\n"
    "# repo-relative files, the query entity, the supplied-input surface, and\n"
    "# the engine->input bridge. Regenerate with\n"
    "# `uv run scripts/generate_conformance_compositions.py <jur>`; CI fails if\n"
    "# this drifts from the suites (scripts/generate_conformance_compositions.py --check).\n"
)


def serialize(document: CompositionsDocument) -> str:
    """Deterministic YAML for the record (compositions sorted by suite)."""

    body = {
        "schema": COMPOSITIONS_SCHEMA_VERSION,
        "jurisdiction": document.jurisdiction,
        "oracle": document.oracle,
        "compositions": [
            comp.to_row()
            for comp in sorted(document.compositions, key=lambda c: c.suite)
        ],
    }
    text = yaml.dump(
        body,
        Dumper=_CompositionsDumper,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=100,
    )
    return _HEADER + text


def parse(path: str | Path) -> CompositionsDocument:
    """Load a committed compositions record."""

    path = Path(path)
    document = yaml.safe_load(path.read_text()) or {}
    schema = document.get("schema")
    if schema != COMPOSITIONS_SCHEMA_VERSION:
        raise ValueError(
            f"{path}: expected schema {COMPOSITIONS_SCHEMA_VERSION!r}, got {schema!r}"
        )
    return CompositionsDocument(
        jurisdiction=document["jurisdiction"],
        oracle=document.get("oracle") or {},
        compositions=[
            SuiteComposition.from_row(row) for row in document.get("compositions", [])
        ],
    )


def parse_if_exists(path: str | Path) -> CompositionsDocument | None:
    path = Path(path)
    return parse(path) if path.exists() else None


def _conformance_dir() -> Path:
    # axiom_oracles/conformance/compositions.py -> repo root is three parents up.
    return Path(__file__).resolve().parents[2] / "conformance"


def compositions_path(jurisdiction: str) -> Path:
    return _conformance_dir() / "compositions" / f"{jurisdiction}.yaml"


def load_composition(
    suite: str,
    jurisdiction: str = "be",
) -> SuiteComposition | None:
    """Look up one covered suite's composition from its committed record."""

    document = parse_if_exists(compositions_path(jurisdiction))
    if document is None:
        return None
    return document.by_suite().get(suite)


def resolve_suite_program(
    suite: str,
    *,
    rulespec_root: str | Path,
    jurisdiction: str = "be",
) -> ResolvedComposition | None:
    """Resolve a covered suite's recorded program against a rulespec checkout.

    Returns ``None`` only when the suite has no committed record. The caller
    must supply the exact canonical country checkout.
    """

    composition = load_composition(suite, jurisdiction=jurisdiction)
    if composition is None:
        return None
    return composition.resolve(rulespec_root)
