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
plus the query entity, flat/record supplied-input surface, relations, and bridge
targets, straight from the suite definition.
:mod:`scripts.generate_conformance_compositions` serialises the set
into ``conformance/compositions/<jur>.yaml`` and a CI ``--check`` fails if the
committed record drifts from the suites — so the record cannot silently diverge
from what actually runs.

The composition for every committed EUROMOD-lane BE suite is a direct
documentary RuleSpec surface. Comparator-shaped pipelines, generated annual
aggregates, aggregate income lists, and region routers are composed outside RuleSpec (see
``conformance/README.md`` § "Recorded program compositions").
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

import yaml

from axiom_oracles.bridges.repo_routing import jurisdiction_country


COMPOSITIONS_SCHEMA_VERSION = "axiom_oracles.compositions.v2"

#: Single env var naming one rulespec checkout (or the workspace holding the
#: ``rulespec-<country>`` checkouts). Distinct from the harness's existing
#: ``AXIOM_RULESPEC_REPO_ROOTS`` (an os.pathsep list); this is the convenience
#: knob issue #185 asks the CLI to honour when ``--axiom-program`` is omitted.
AXIOM_RULESPEC_ROOT_ENV = "AXIOM_RULESPEC_ROOT"

# The metadata keys the suites use to carry the Axiom projection facts. Kept in
# sync with axiom_oracles.suites and the AxiomRulesRunner.
_AXIOM_ENTITY_KEY = "axiom_entity"
_AXIOM_ENTITY_ID_KEY = "axiom_entity_id"
_AXIOM_INPUTS_KEY = "axiom_inputs"
_AXIOM_INPUT_RECORDS_KEY = "axiom_input_records"
_AXIOM_RELATIONS_KEY = "axiom_relations"
_INPUT_BRIDGE_KEY = "euromod_to_axiom_input_bridge"
_BRIDGE_TRANSFORM_KEYS = ("divide_by", "multiply_by", "add")


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
    return f"rulespec-{country}/{prefix}/{relative}.yaml"


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
      supplies as flat inputs or input records (the program's expected supplied
      surface).
    * ``axiom_input_records`` — value-free ``name`` / ``entity`` / ``entity_id``
      targets from the suite's explicit input records. Values remain in the case
      definitions because a suite-level composition records structure, not each
      case's data.
    * ``axiom_relations`` — normalized relation records (``name`` + ordered
      ``tuple``) from either metadata's mapping or list representation.
    * ``input_bridge`` — the engine-output → supplied-input map the harness
      applies on top of static case inputs. It preserves flat targets, record
      targets, and the runner's ``divide_by`` / ``multiply_by`` / ``add``
      transforms.
    """

    suite: str
    entity: str
    entity_id: str
    target: str
    imports: tuple[str, ...]
    paths: tuple[str, ...]
    outputs: tuple[str, ...]
    supplied_input_boundaries: tuple[str, ...]
    axiom_input_records: tuple[dict[str, object], ...]
    axiom_relations: tuple[dict[str, object], ...]
    input_bridge: dict[str, dict[str, object]]
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
        if self.axiom_input_records:
            row["axiom_input_records"] = [
                _mapping_to_row(record) for record in self.axiom_input_records
            ]
        if self.axiom_relations:
            row["axiom_relations"] = [
                _mapping_to_row(relation) for relation in self.axiom_relations
            ]
        if self.input_bridge:
            row["input_bridge"] = {
                engine_var: _bridge_spec_to_row(spec)
                for engine_var, spec in sorted(self.input_bridge.items())
            }
        return row

    @classmethod
    def from_row(cls, row: Mapping) -> "SuiteComposition":
        program = row.get("program") or {}
        bridge_raw = row.get("input_bridge") or {}
        input_records = _normalize_input_record_targets(
            row.get("axiom_input_records") or (),
            label="composition axiom_input_records",
        )
        relations = _normalize_relation_records(
            row.get("axiom_relations") or (),
            label="composition axiom_relations",
        )
        return cls(
            suite=row["suite"],
            policy=row.get("policy"),
            entity=row["entity"],
            entity_id=row["entity_id"],
            target=program["target"],
            imports=tuple(program.get("imports") or ()),
            paths=tuple(program.get("paths") or ()),
            outputs=tuple(row.get("outputs") or ()),
            supplied_input_boundaries=tuple(
                row.get("supplied_input_boundaries") or ()
            ),
            axiom_input_records=input_records,
            axiom_relations=relations,
            input_bridge=_normalize_input_bridge(
                bridge_raw,
                label="composition input_bridge",
            ),
        )

    def resolve(self, rulespec_root: str | Path) -> "ResolvedComposition":
        """Bind ``paths`` to absolute files under a rulespec checkout root."""
        root = normalize_rulespec_root(rulespec_root)
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

        Multi-module compositions have no single file — callers fall back to
        the import-set the harness composes.
        """
        if len(self.program_paths) == 1:
            return self.program_paths[0]
        return None

    def missing_paths(self) -> tuple[Path, ...]:
        return tuple(p for p in self.program_paths if not p.exists())


def normalize_rulespec_root(rulespec_root: str | Path) -> Path:
    """Resolve a checkout/workspace path to the root modules resolve against.

    Module refs resolve as ``<root>/rulespec-<country>/<prefix>/<path>.yaml``,
    so ``root`` must be the directory that *holds* the ``rulespec-*`` checkout.
    A path pointing straight at a ``rulespec-*`` checkout is lifted to its
    parent; a workspace/org directory is used as-is.
    """

    root = Path(rulespec_root).expanduser()
    if root.name.startswith("rulespec-"):
        return root.parent
    return root


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


def _stable_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _dedupe_sorted_mappings(
    records: list[dict[str, object]],
) -> tuple[dict[str, object], ...]:
    by_key = {_stable_json(record): record for record in records}
    return tuple(by_key[key] for key in sorted(by_key))


def _mapping_to_row(record: Mapping[str, object]) -> dict[str, object]:
    """Convert internal tuple containers to deterministic YAML-safe lists."""

    row: dict[str, object] = {}
    for key, value in record.items():
        if isinstance(value, tuple):
            row[str(key)] = [
                _mapping_to_row(item) if isinstance(item, Mapping) else item
                for item in value
            ]
        elif isinstance(value, Mapping):
            row[str(key)] = _mapping_to_row(value)
        else:
            row[str(key)] = value
    return row


def _normalize_input_record_target(
    raw_record: object,
    *,
    label: str,
) -> dict[str, object]:
    if not isinstance(raw_record, Mapping):
        raise ValueError(f"{label} records must be mappings")
    missing = {"name", "entity", "entity_id"} - set(raw_record)
    if missing:
        raise ValueError(f"{label} record is missing {sorted(missing)}")
    record: dict[str, object] = {
        "name": str(raw_record["name"]),
        "entity": str(raw_record["entity"]),
        "entity_id": str(raw_record["entity_id"]),
    }
    if "interval" in raw_record:
        interval = raw_record["interval"]
        if not isinstance(interval, Mapping):
            raise ValueError(f"{label} record interval must be a mapping")
        record["interval"] = {
            str(key): value for key, value in sorted(interval.items())
        }
    return record


def _normalize_input_record_targets(
    raw_records: object,
    *,
    label: str,
) -> tuple[dict[str, object], ...]:
    if raw_records is None:
        return ()
    if not isinstance(raw_records, list | tuple):
        raise ValueError(f"{label} must be a list")
    return _dedupe_sorted_mappings(
        [
            _normalize_input_record_target(record, label=label)
            for record in raw_records
        ]
    )


def _relation_tuples(value: object) -> list[object]:
    if isinstance(value, list | tuple):
        if not value:
            return []
        if all(isinstance(item, list | tuple) for item in value):
            return list(value)
        return [value]
    return [[value]]


def _normalize_relation_records(
    raw_relations: object,
    *,
    label: str,
) -> tuple[dict[str, object], ...]:
    if raw_relations is None:
        return ()
    relation_rows: list[object]
    if isinstance(raw_relations, Mapping):
        relation_rows = [
            {"name": name, "tuple": tuple_value}
            for name, tuples in raw_relations.items()
            for tuple_value in _relation_tuples(tuples)
        ]
    elif isinstance(raw_relations, list | tuple):
        relation_rows = list(raw_relations)
    else:
        raise ValueError(f"{label} must be a list or mapping")

    normalized: list[dict[str, object]] = []
    for raw_relation in relation_rows:
        if not isinstance(raw_relation, Mapping):
            raise ValueError(f"{label} records must be mappings")
        missing = {"name", "tuple"} - set(raw_relation)
        if missing:
            raise ValueError(f"{label} record is missing {sorted(missing)}")
        tuple_value = raw_relation["tuple"]
        if not isinstance(tuple_value, list | tuple):
            raise ValueError(f"{label} record tuple must be a list")
        normalized.append(
            {
                "name": str(raw_relation["name"]),
                "tuple": tuple(str(value) for value in tuple_value),
            }
        )
    return _dedupe_sorted_mappings(normalized)


def _normalize_bridge_inputs(raw_inputs: object, *, label: str) -> tuple[str, ...]:
    if raw_inputs is None:
        return ()
    if isinstance(raw_inputs, str):
        return (raw_inputs,)
    if not isinstance(raw_inputs, list | tuple):
        raise ValueError(f"{label} inputs must be a string or list")
    return tuple(sorted({str(input_name) for input_name in raw_inputs}))


def _normalize_bridge_spec(raw_spec: object, *, label: str) -> dict[str, object]:
    if isinstance(raw_spec, str | list | tuple):
        inputs = _normalize_bridge_inputs(raw_spec, label=label)
        if not inputs:
            raise ValueError(f"{label} must target at least one input or record")
        return {"inputs": inputs}
    if not isinstance(raw_spec, Mapping):
        raise ValueError(f"{label} must be a string, list, or mapping")

    allowed = {
        "input",
        "inputs",
        "input_records",
        "records",
        *_BRIDGE_TRANSFORM_KEYS,
    }
    unknown = set(raw_spec) - allowed
    if unknown:
        raise ValueError(f"{label} has unknown keys {sorted(unknown)}")
    if "input" in raw_spec and "inputs" in raw_spec:
        raise ValueError(f"{label} cannot set both input and inputs")
    if "input_records" in raw_spec and "records" in raw_spec:
        raise ValueError(f"{label} cannot set both input_records and records")

    inputs = _normalize_bridge_inputs(
        raw_spec.get("inputs", raw_spec.get("input")),
        label=label,
    )
    raw_records = raw_spec.get("records", raw_spec.get("input_records"))
    records = _normalize_input_record_targets(raw_records, label=f"{label} records")
    if not inputs and not records:
        raise ValueError(f"{label} must target at least one input or record")

    spec: dict[str, object] = {}
    if inputs:
        spec["inputs"] = inputs
    if records:
        spec["records"] = records
    for key in _BRIDGE_TRANSFORM_KEYS:
        if key in raw_spec:
            spec[key] = raw_spec[key]
    return spec


def _normalize_input_bridge(
    raw_bridge: object,
    *,
    label: str,
) -> dict[str, dict[str, object]]:
    if raw_bridge is None:
        return {}
    if not isinstance(raw_bridge, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return {
        str(engine_var): _normalize_bridge_spec(
            raw_spec,
            label=f"{label}[{engine_var!r}]",
        )
        for engine_var, raw_spec in sorted(raw_bridge.items(), key=lambda item: str(item[0]))
    }


def _merge_bridge_spec(
    current: dict[str, object],
    incoming: dict[str, object],
    *,
    label: str,
) -> dict[str, object]:
    current_transforms = {
        key: current[key] for key in _BRIDGE_TRANSFORM_KEYS if key in current
    }
    incoming_transforms = {
        key: incoming[key] for key in _BRIDGE_TRANSFORM_KEYS if key in incoming
    }
    if current_transforms != incoming_transforms:
        raise ValueError(
            f"{label} mixes incompatible bridge transforms across cases: "
            f"{current_transforms!r} != {incoming_transforms!r}"
        )

    merged: dict[str, object] = {}
    inputs = {
        *current.get("inputs", ()),
        *incoming.get("inputs", ()),
    }
    if inputs:
        merged["inputs"] = tuple(sorted(str(value) for value in inputs))
    record_values = [
        *current.get("records", ()),
        *incoming.get("records", ()),
    ]
    if record_values:
        merged["records"] = _dedupe_sorted_mappings(
            [dict(record) for record in record_values]
        )
    merged.update(current_transforms)
    return merged


def _bridge_spec_to_row(spec: Mapping[str, object]) -> object:
    """Use the old list shorthand only for an untransformed flat bridge."""

    if set(spec) == {"inputs"}:
        return list(spec["inputs"])
    row: dict[str, object] = {}
    if spec.get("inputs"):
        row["inputs"] = list(spec["inputs"])
    if spec.get("records"):
        row["records"] = [
            _mapping_to_row(record) for record in spec["records"]
        ]
    for key in _BRIDGE_TRANSFORM_KEYS:
        if key in spec:
            row[key] = spec[key]
    return row


def composition_for_suite(suite: str) -> SuiteComposition:
    """Derive the runnable composition a suite's cases request.

    Loads the suite's cases (pure data — no engine) and reads off the same
    facts the CLI runner uses: the output concepts, the import-set
    (:func:`rulespec_imports_for_concepts`), the pinned query entity, the
    flat and record-targeted supplied-input surface, relations, and the
    engine→input bridge. Import-only; safe to call in tests and generators.
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
    input_records: list[dict[str, object]] = []
    relations: list[dict[str, object]] = []
    bridge: dict[str, dict[str, object]] = {}
    for case in cases:
        raw_inputs = case.metadata.get(_AXIOM_INPUTS_KEY) or {}
        if not isinstance(raw_inputs, Mapping):
            raise ValueError(
                f"suite {suite!r} case {case.case_id!r} metadata "
                f"{_AXIOM_INPUTS_KEY!r} must be a mapping"
            )
        for name in raw_inputs:
            supplied.add(str(name))

        case_records = _normalize_input_record_targets(
            case.metadata.get(_AXIOM_INPUT_RECORDS_KEY) or (),
            label=(
                f"suite {suite!r} case {case.case_id!r} "
                f"metadata[{_AXIOM_INPUT_RECORDS_KEY!r}]"
            ),
        )
        input_records.extend(case_records)
        supplied.update(str(record["name"]) for record in case_records)

        case_relations = _normalize_relation_records(
            case.metadata.get(_AXIOM_RELATIONS_KEY) or (),
            label=(
                f"suite {suite!r} case {case.case_id!r} "
                f"metadata[{_AXIOM_RELATIONS_KEY!r}]"
            ),
        )
        relations.extend(case_relations)

        case_bridge = _normalize_input_bridge(
            case.metadata.get(_INPUT_BRIDGE_KEY) or {},
            label=(
                f"suite {suite!r} case {case.case_id!r} "
                f"metadata[{_INPUT_BRIDGE_KEY!r}]"
            ),
        )
        for engine_var, spec in case_bridge.items():
            if engine_var in bridge:
                bridge[engine_var] = _merge_bridge_spec(
                    bridge[engine_var],
                    spec,
                    label=f"suite {suite!r} bridge {engine_var!r}",
                )
            else:
                bridge[engine_var] = spec
            supplied.update(str(name) for name in spec.get("inputs", ()))
            supplied.update(
                str(record["name"])
                for record in spec.get("records", ())
            )

    return SuiteComposition(
        suite=suite,
        entity=_single_metadata_value(cases, _AXIOM_ENTITY_KEY, suite),
        entity_id=_single_metadata_value(cases, _AXIOM_ENTITY_ID_KEY, suite),
        target=imports[0],
        imports=imports,
        paths=tuple(repo_relative_program_path(ref) for ref in imports),
        outputs=tuple(outputs),
        supplied_input_boundaries=tuple(sorted(supplied)),
        axiom_input_records=_dedupe_sorted_mappings(input_records),
        axiom_relations=_dedupe_sorted_mappings(relations),
        input_bridge=bridge,
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
    "# repo-relative files, query entity, supplied flat/record inputs,\n"
    "# relations, and flat/record-target engine bridges. Regenerate with\n"
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
            SuiteComposition.from_row(row)
            for row in document.get("compositions", [])
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
    jurisdiction: str = "be",
    rulespec_root: str | Path | None = None,
) -> ResolvedComposition | None:
    """Resolve a covered suite's recorded program against a rulespec checkout.

    ``rulespec_root`` defaults to the ``AXIOM_RULESPEC_ROOT`` env var. Returns
    ``None`` when the suite has no committed record (the caller then falls back
    to the harness's live concept-derivation), or when no root is available.
    """

    import os

    composition = load_composition(suite, jurisdiction=jurisdiction)
    if composition is None:
        return None
    root = rulespec_root or os.environ.get(AXIOM_RULESPEC_ROOT_ENV)
    if not root:
        return None
    return composition.resolve(root)
