"""Projection contracts for state income-tax Populace comparisons.

This module deliberately owns no execution logic.  It loads and validates the
declarative contract that a future runner will use to project the pinned US
Populace dataset into the 44 merged state/DC pilot liability pipelines.

The validator is intentionally fail-closed: a pipeline is runnable only when
every explicit input and relation has a documented, non-circular source.  An
unresolved boundary remains ``blocked`` instead of silently becoming zero or a
PolicyEngine-derived alignment value.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import yaml


STATE_TAX_POPULACE_CONTRACT_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "state_income_tax_populace.yaml"
)
CONTRACT_SCHEMA_VERSION = "axiom.state_tax_populace_contract.v1"
CONTRACT_VALIDATION_YEAR = 2026
CONTRACT_POPULACE_COUNTRY = "us"
CONTRACT_POPULACE_YEAR = 2024
CONTRACT_POPULACE_REPO_ID = "policyengine/populace-us"
CONTRACT_POPULACE_FILENAME = "populace_us_2024.h5"
CONTRACT_POPULACE_REVISION = (
    "populace-us-2024-f0af251-703bd81a565c-20260620T201958Z"
)
CONTRACT_POPULACE_SHA256 = (
    "16be6338f9d0b3c339883dae59949e995663b64cf145de6728b3dd0f916c5d5f"
)
CONTRACT_POPULACE_BUILT_WITH = "1.729.0"
CONTRACT_REGISTRY_SOURCE = "scripts/generate_state_income_tax_liability.py"
CONTRACT_SCOPE_UNIT = "tax_unit"
CONTRACT_SCOPE_GEOGRAPHY_SOURCE = "household_state_fips"
CONTRACT_SCOPE_RESIDENCY_MODEL = "household_state_as_full_year_residence"
CONTRACT_SCOPE_INCLUSION = "all_positive_weight_routed_tax_units"

ALLOWED_SOURCE_KINDS = frozenset(
    {
        "raw_populace",
        "derived",
        "statutory_constant",
        "rulespec_import",
        "pe_upstream_boundary",
        "blocked",
    }
)
ALLOWED_STATUSES = frozenset({"ready", "blocked"})

# The personal-income-tax campaign covers the 43 states with a modeled PIT
# surface plus DC.  States without an applicable broad PIT surface are absent.
EXPECTED_STATE_FIPS = {
    "AL": "01",
    "AR": "05",
    "AZ": "04",
    "CA": "06",
    "CO": "08",
    "CT": "09",
    "DC": "11",
    "DE": "10",
    "GA": "13",
    "HI": "15",
    "IA": "19",
    "ID": "16",
    "IL": "17",
    "IN": "18",
    "KS": "20",
    "KY": "21",
    "LA": "22",
    "MA": "25",
    "MD": "24",
    "ME": "23",
    "MI": "26",
    "MN": "27",
    "MO": "29",
    "MS": "28",
    "MT": "30",
    "NC": "37",
    "ND": "38",
    "NE": "31",
    "NH": "33",
    "NJ": "34",
    "NM": "35",
    "NY": "36",
    "OH": "39",
    "OK": "40",
    "OR": "41",
    "PA": "42",
    "RI": "44",
    "SC": "45",
    "UT": "49",
    "VA": "51",
    "VT": "50",
    "WA": "53",
    "WI": "55",
    "WV": "54",
}
EXPECTED_STATE_CODES = frozenset(EXPECTED_STATE_FIPS)
EXPECTED_EXPLICIT_INPUT_COUNT = 257
EXPECTED_EXPLICIT_RELATION_COUNT = 1
EXPECTED_SLOT_INVENTORY_SHA256 = (
    "c11918d1dc03e80f60fc1a321c3f61ec961eac5fd4a51e1fa2f99864d3f25a20"
)
EXPECTED_JURISDICTION_REGISTRY_SHA256 = (
    "af96f31eb1164c77a10807579f4d72bbc09f0082deefee4341378476d30e492d"
)
EXPECTED_SOURCE_METADATA_SHA256 = (
    "cfae6977195932346f5e8dea1d2a6e64118524ef8e1973ddbed8380f06e82b45"
)
# No PolicyEngine-derived projection boundary has completed independent legal
# and dependency-graph review yet.  Add exact (state, slot, variable) tuples
# here only through the review-fix cycle that makes the corresponding state
# population-ready.
ALLOWED_PE_UPSTREAM_BOUNDARIES: frozenset[tuple[str, str, str]] = frozenset()

_FORBIDDEN_ALIGNMENT_KEYS = frozenset(
    {
        "align_to_policyengine",
        "alignment",
        "candidate_selection",
        "dynamic_residual_adjustment",
        "residual_adjustment",
        "result_selection",
        "selection_strategy",
    }
)


class StateTaxPopulaceContractError(ValueError):
    """Raised when a state-tax Populace contract is unsafe or incomplete."""


@dataclass(frozen=True)
class ProjectionSource:
    """One explicit runtime slot and the evidence for its intended source."""

    slot: str
    source_kind: str
    status: str
    evidence: str
    policyengine_variable: str | None = None
    policyengine_relationship: str | None = None


@dataclass(frozen=True)
class StateTaxJurisdictionContract:
    """Projection contract for one state/DC pilot liability pipeline."""

    state: str
    fips: str
    taxsim_state_code: int
    jurisdiction: str
    program: str
    output: str
    policyengine_target: str
    tolerance: float
    relative_tolerance: float
    status: str
    evidence: str
    inputs: tuple[ProjectionSource, ...]
    relations: tuple[ProjectionSource, ...]


@dataclass(frozen=True)
class StateTaxPopulaceContract:
    """Validated all-state projection contract."""

    schema_version: str
    validation_year: int
    populace_country: str
    populace_year: int
    populace_repo_id: str
    populace_filename: str
    populace_revision: str
    populace_sha256: str
    populace_built_with: str
    scope_unit: str
    scope_geography_source: str
    scope_residency_model: str
    scope_inclusion: str
    scope_filtered_slices_allowed: bool
    scope_evidence: str
    registry_source: str
    jurisdictions: tuple[StateTaxJurisdictionContract, ...]

    def by_state(self) -> dict[str, StateTaxJurisdictionContract]:
        return {item.state: item for item in self.jurisdictions}


def load_state_tax_populace_contract(
    path: str | Path | None = None,
) -> StateTaxPopulaceContract:
    """Load and validate the packaged projection contract or an override path."""

    contract_path = Path(path) if path is not None else STATE_TAX_POPULACE_CONTRACT_PATH
    document = yaml.safe_load(contract_path.read_text())
    return validate_state_tax_populace_contract(document)


def validate_state_tax_populace_contract(
    document: Mapping[str, Any] | StateTaxPopulaceContract,
) -> StateTaxPopulaceContract:
    """Validate *document* and return its immutable typed representation."""

    if isinstance(document, StateTaxPopulaceContract):
        document = _contract_to_document(document)
    if not isinstance(document, Mapping):
        raise StateTaxPopulaceContractError("contract document must be a mapping")

    errors: list[str] = []
    _reject_alignment_controls(document, errors=errors)
    _reject_unknown_keys(
        document,
        {
            "schema_version",
            "validation_year",
            "population",
            "population_scope",
            "registry_source",
            "jurisdictions",
        },
        "contract",
        errors,
    )

    schema_version = _required_text(document, "schema_version", "contract", errors)
    validation_year = _required_int(document, "validation_year", "contract", errors)
    population = document.get("population")
    if not isinstance(population, Mapping):
        errors.append("contract.population must be a mapping")
        population = {}
    _reject_unknown_keys(
        population,
        {
            "country",
            "year",
            "repo_id",
            "filename",
            "revision",
            "sha256",
            "built_with",
        },
        "population",
        errors,
    )
    populace_country = _required_text(population, "country", "population", errors)
    populace_year = _required_int(population, "year", "population", errors)
    populace_repo_id = _required_text(population, "repo_id", "population", errors)
    populace_filename = _required_text(population, "filename", "population", errors)
    populace_revision = _required_text(population, "revision", "population", errors)
    populace_sha256 = _required_text(population, "sha256", "population", errors)
    populace_built_with = _required_text(
        population, "built_with", "population", errors
    )
    population_scope = document.get("population_scope")
    if not isinstance(population_scope, Mapping):
        errors.append("contract.population_scope must be a mapping")
        population_scope = {}
    _reject_unknown_keys(
        population_scope,
        {
            "unit",
            "geography_source",
            "residency_model",
            "inclusion",
            "filtered_slices_allowed",
            "evidence",
        },
        "population_scope",
        errors,
    )
    scope_unit = _required_text(population_scope, "unit", "population_scope", errors)
    scope_geography_source = _required_text(
        population_scope, "geography_source", "population_scope", errors
    )
    scope_residency_model = _required_text(
        population_scope, "residency_model", "population_scope", errors
    )
    scope_inclusion = _required_text(
        population_scope, "inclusion", "population_scope", errors
    )
    scope_evidence = _required_text(
        population_scope, "evidence", "population_scope", errors
    )
    scope_filtered_slices_allowed = population_scope.get("filtered_slices_allowed")
    if not isinstance(scope_filtered_slices_allowed, bool):
        errors.append("population_scope.filtered_slices_allowed must be a boolean")
        scope_filtered_slices_allowed = True
    registry_source = _required_text(
        document, "registry_source", "contract", errors
    )

    pinned_metadata = (
        ("schema_version", schema_version, CONTRACT_SCHEMA_VERSION),
        ("validation_year", validation_year, CONTRACT_VALIDATION_YEAR),
        ("population.country", populace_country, CONTRACT_POPULACE_COUNTRY),
        ("population.year", populace_year, CONTRACT_POPULACE_YEAR),
        ("population.repo_id", populace_repo_id, CONTRACT_POPULACE_REPO_ID),
        ("population.filename", populace_filename, CONTRACT_POPULACE_FILENAME),
        ("population.revision", populace_revision, CONTRACT_POPULACE_REVISION),
        ("population.sha256", populace_sha256, CONTRACT_POPULACE_SHA256),
        (
            "population.built_with",
            populace_built_with,
            CONTRACT_POPULACE_BUILT_WITH,
        ),
        ("population_scope.unit", scope_unit, CONTRACT_SCOPE_UNIT),
        (
            "population_scope.geography_source",
            scope_geography_source,
            CONTRACT_SCOPE_GEOGRAPHY_SOURCE,
        ),
        (
            "population_scope.residency_model",
            scope_residency_model,
            CONTRACT_SCOPE_RESIDENCY_MODEL,
        ),
        (
            "population_scope.inclusion",
            scope_inclusion,
            CONTRACT_SCOPE_INCLUSION,
        ),
        ("registry_source", registry_source, CONTRACT_REGISTRY_SOURCE),
    )
    for label, actual, expected in pinned_metadata:
        if actual != expected:
            errors.append(f"contract.{label} must be {expected!r}; got {actual!r}")
    if scope_filtered_slices_allowed:
        errors.append(
            "contract.population_scope.filtered_slices_allowed must be False "
            "until stable exclusion predicates are implemented"
        )

    raw_jurisdictions = document.get("jurisdictions")
    if not isinstance(raw_jurisdictions, list):
        errors.append("contract.jurisdictions must be a list")
        raw_jurisdictions = []

    jurisdictions = tuple(
        _parse_jurisdiction(raw, index=index, errors=errors)
        for index, raw in enumerate(raw_jurisdictions)
        if isinstance(raw, Mapping)
    )
    if len(jurisdictions) != len(raw_jurisdictions):
        errors.append("every jurisdiction entry must be a mapping")

    states = [item.state for item in jurisdictions]
    state_set = set(states)
    missing_states = sorted(EXPECTED_STATE_CODES - state_set)
    extra_states = sorted(state_set - EXPECTED_STATE_CODES)
    if len(jurisdictions) != len(EXPECTED_STATE_CODES):
        errors.append(
            "contract must declare exactly 44 PIT/DC jurisdictions; "
            f"found {len(jurisdictions)}"
        )
    if missing_states:
        errors.append("missing PIT/DC jurisdictions: " + ", ".join(missing_states))
    if extra_states:
        errors.append("unexpected PIT/DC jurisdictions: " + ", ".join(extra_states))
    _reject_duplicates(states, "state", errors)
    _reject_duplicates(
        [str(item.taxsim_state_code) for item in jurisdictions],
        "TAXSIM state code",
        errors,
    )
    _reject_duplicates([item.program for item in jurisdictions], "program", errors)
    _reject_duplicates([item.output for item in jurisdictions], "output", errors)
    _reject_duplicates(
        [item.policyengine_target for item in jurisdictions],
        "PolicyEngine target",
        errors,
    )

    for item in jurisdictions:
        expected_fips = EXPECTED_STATE_FIPS.get(item.state)
        if expected_fips is not None and item.fips != expected_fips:
            errors.append(
                f"{item.state}: expected census FIPS {expected_fips}, got {item.fips}"
            )
        _validate_jurisdiction(item, errors=errors)

    input_count = sum(len(item.inputs) for item in jurisdictions)
    relation_count = sum(len(item.relations) for item in jurisdictions)
    if input_count != EXPECTED_EXPLICIT_INPUT_COUNT:
        errors.append(
            "contract must inventory exactly "
            f"{EXPECTED_EXPLICIT_INPUT_COUNT} explicit inputs; found {input_count}"
        )
    if relation_count != EXPECTED_EXPLICIT_RELATION_COUNT:
        errors.append(
            "contract must inventory exactly "
            f"{EXPECTED_EXPLICIT_RELATION_COUNT} explicit relation; "
            f"found {relation_count}"
        )
    inventory_digest = _slot_inventory_sha256(jurisdictions)
    if inventory_digest != EXPECTED_SLOT_INVENTORY_SHA256:
        errors.append(
            "contract explicit slot inventory does not match the merged RuleSpec "
            f"fixtures: expected {EXPECTED_SLOT_INVENTORY_SHA256}, got "
            f"{inventory_digest}"
        )
    source_metadata_digest = _source_metadata_sha256(jurisdictions)
    if source_metadata_digest != EXPECTED_SOURCE_METADATA_SHA256:
        errors.append(
            "contract projection source metadata does not match the reviewed "
            f"registry: expected {EXPECTED_SOURCE_METADATA_SHA256}, got "
            f"{source_metadata_digest}"
        )
    registry_digest = _jurisdiction_registry_sha256(jurisdictions)
    if registry_digest != EXPECTED_JURISDICTION_REGISTRY_SHA256:
        errors.append(
            "contract jurisdiction registry does not match the generated campaign "
            f"registry: expected {EXPECTED_JURISDICTION_REGISTRY_SHA256}, got "
            f"{registry_digest}"
        )

    if errors:
        raise StateTaxPopulaceContractError("\n".join(errors))
    return StateTaxPopulaceContract(
        schema_version=schema_version,
        validation_year=validation_year,
        populace_country=populace_country,
        populace_year=populace_year,
        populace_repo_id=populace_repo_id,
        populace_filename=populace_filename,
        populace_revision=populace_revision,
        populace_sha256=populace_sha256,
        populace_built_with=populace_built_with,
        scope_unit=scope_unit,
        scope_geography_source=scope_geography_source,
        scope_residency_model=scope_residency_model,
        scope_inclusion=scope_inclusion,
        scope_filtered_slices_allowed=scope_filtered_slices_allowed,
        scope_evidence=scope_evidence,
        registry_source=registry_source,
        jurisdictions=jurisdictions,
    )


def readiness_summary(
    document: Mapping[str, Any] | StateTaxPopulaceContract,
) -> dict[str, Any]:
    """Return deterministic readiness counts for a validated contract."""

    contract = validate_state_tax_populace_contract(document)
    ready = sorted(item.state for item in contract.jurisdictions if item.status == "ready")
    blocked = sorted(
        item.state for item in contract.jurisdictions if item.status == "blocked"
    )
    inputs = [slot for item in contract.jurisdictions for slot in item.inputs]
    relations = [slot for item in contract.jurisdictions for slot in item.relations]
    return {
        "jurisdiction_count": len(contract.jurisdictions),
        "ready_count": len(ready),
        "blocked_count": len(blocked),
        "ready_states": ready,
        "blocked_states": blocked,
        "explicit_input_count": len(inputs),
        "explicit_relation_count": len(relations),
        "blocked_input_count": sum(slot.status == "blocked" for slot in inputs),
        "blocked_relation_count": sum(
            slot.status == "blocked" for slot in relations
        ),
    }


def _parse_jurisdiction(
    raw: Mapping[str, Any], *, index: int, errors: list[str]
) -> StateTaxJurisdictionContract:
    label = f"jurisdictions[{index}]"
    policyengine = raw.get("policyengine")
    if not isinstance(policyengine, Mapping):
        errors.append(f"{label}.policyengine must be a mapping")
        policyengine = {}
    _reject_unknown_keys(
        policyengine,
        {"target", "tolerance", "relative_tolerance"},
        f"{label}.policyengine",
        errors,
    )
    _reject_unknown_keys(
        raw,
        {
            "state",
            "fips",
            "taxsim_state_code",
            "jurisdiction",
            "program",
            "output",
            "policyengine",
            "status",
            "evidence",
            "inputs",
            "relations",
        },
        label,
        errors,
    )
    tolerance = policyengine.get("tolerance")
    relative_tolerance = policyengine.get("relative_tolerance")
    if not isinstance(tolerance, int | float) or isinstance(tolerance, bool):
        errors.append(f"{label}.policyengine.tolerance must be numeric")
        tolerance = 0
    if not isinstance(relative_tolerance, int | float) or isinstance(
        relative_tolerance, bool
    ):
        errors.append(f"{label}.policyengine.relative_tolerance must be numeric")
        relative_tolerance = 0

    inputs = _parse_slots(raw.get("inputs"), label=f"{label}.inputs", errors=errors)
    relations = _parse_slots(
        raw.get("relations"), label=f"{label}.relations", errors=errors
    )
    taxsim_state_code = raw.get("taxsim_state_code")
    if not isinstance(taxsim_state_code, int) or isinstance(taxsim_state_code, bool):
        errors.append(f"{label}.taxsim_state_code must be an integer")
        taxsim_state_code = 0
    return StateTaxJurisdictionContract(
        state=_required_text(raw, "state", label, errors),
        fips=_required_text(raw, "fips", label, errors),
        taxsim_state_code=taxsim_state_code,
        jurisdiction=_required_text(raw, "jurisdiction", label, errors),
        program=_required_text(raw, "program", label, errors),
        output=_required_text(raw, "output", label, errors),
        policyengine_target=_required_text(
            policyengine, "target", f"{label}.policyengine", errors
        ),
        tolerance=float(tolerance),
        relative_tolerance=float(relative_tolerance),
        status=_required_text(raw, "status", label, errors),
        evidence=_required_text(raw, "evidence", label, errors),
        inputs=inputs,
        relations=relations,
    )


def _parse_slots(
    raw_slots: Any, *, label: str, errors: list[str]
) -> tuple[ProjectionSource, ...]:
    if not isinstance(raw_slots, list):
        errors.append(f"{label} must be an explicit list")
        return ()
    slots: list[ProjectionSource] = []
    for index, raw in enumerate(raw_slots):
        item_label = f"{label}[{index}]"
        if not isinstance(raw, Mapping):
            errors.append(f"{item_label} must be a mapping")
            continue
        _reject_unknown_keys(
            raw,
            {
                "slot",
                "source_kind",
                "status",
                "evidence",
                "policyengine_variable",
                "policyengine_relationship",
            },
            item_label,
            errors,
        )
        slots.append(
            ProjectionSource(
                slot=_required_text(raw, "slot", item_label, errors),
                source_kind=_required_text(raw, "source_kind", item_label, errors),
                status=_required_text(raw, "status", item_label, errors),
                evidence=_required_text(raw, "evidence", item_label, errors),
                policyengine_variable=_optional_text(
                    raw, "policyengine_variable", item_label, errors
                ),
                policyengine_relationship=_optional_text(
                    raw, "policyengine_relationship", item_label, errors
                ),
            )
        )
    _reject_duplicates([slot.slot for slot in slots], f"{label} slot", errors)
    return tuple(slots)


def _validate_jurisdiction(
    item: StateTaxJurisdictionContract, *, errors: list[str]
) -> None:
    if item.status not in ALLOWED_STATUSES:
        errors.append(f"{item.state}: unsupported status {item.status!r}")
    if item.jurisdiction != f"us-{item.state.lower()}":
        errors.append(
            f"{item.state}: jurisdiction must be us-{item.state.lower()}"
        )
    expected_program = (
        f"{item.jurisdiction}:policies/income_tax/pilot_liability_pipeline"
    )
    if item.program != expected_program:
        errors.append(f"{item.state}: unexpected program {item.program!r}")
    expected_output = (
        f"{expected_program}#{item.state.lower()}_pit_pilot_income_tax_liability"
    )
    if item.output != expected_output:
        errors.append(f"{item.state}: unexpected output {item.output!r}")

    for slot in (*item.inputs, *item.relations):
        _validate_slot(slot, jurisdiction=item, errors=errors)
    for slot in item.inputs:
        if not slot.slot.startswith(f"{item.program}#input."):
            errors.append(
                f"{item.state}:{slot.slot}: input slot must be an explicit "
                f"{item.program}#input.* reference"
            )
    for slot in item.relations:
        if not slot.slot.startswith(f"{item.program}#relation."):
            errors.append(
                f"{item.state}:{slot.slot}: relation slot must be an explicit "
                f"{item.program}#relation.* reference"
            )

    all_slots = (*item.inputs, *item.relations)
    derived_status = (
        "blocked" if any(slot.status == "blocked" for slot in all_slots) else "ready"
    )
    if item.status != derived_status:
        errors.append(
            f"{item.state}: declared status {item.status!r} does not match "
            f"slot-derived status {derived_status!r}"
        )


def _validate_slot(
    slot: ProjectionSource,
    *,
    jurisdiction: StateTaxJurisdictionContract,
    errors: list[str],
) -> None:
    label = f"{jurisdiction.state}:{slot.slot}"
    if slot.source_kind not in ALLOWED_SOURCE_KINDS:
        errors.append(f"{label}: unsupported source_kind {slot.source_kind!r}")
    if slot.status not in ALLOWED_STATUSES:
        errors.append(f"{label}: unsupported status {slot.status!r}")
    if slot.source_kind == "blocked" and slot.status != "blocked":
        errors.append(f"{label}: blocked source_kind must have blocked status")
    if slot.source_kind != "blocked" and slot.status == "blocked":
        errors.append(
            f"{label}: unresolved slots must use source_kind 'blocked' explicitly"
        )
    if slot.source_kind == "pe_upstream_boundary":
        if not slot.policyengine_variable:
            errors.append(f"{label}: PE boundary requires policyengine_variable")
        if slot.policyengine_relationship != "upstream":
            errors.append(
                f"{label}: PE boundary relationship must be 'upstream', not "
                f"{slot.policyengine_relationship!r}"
            )
        if slot.policyengine_variable == jurisdiction.policyengine_target:
            errors.append(
                f"{label}: PE boundary may not reuse comparison target "
                f"{jurisdiction.policyengine_target!r}"
            )
        boundary = (
            jurisdiction.state,
            slot.slot,
            slot.policyengine_variable or "",
        )
        if boundary not in ALLOWED_PE_UPSTREAM_BOUNDARIES:
            errors.append(
                f"{label}: PE boundary is not in the independently reviewed "
                "upstream allowlist"
            )
    elif slot.policyengine_variable or slot.policyengine_relationship:
        errors.append(
            f"{label}: PolicyEngine boundary metadata requires "
            "source_kind 'pe_upstream_boundary'"
        )


def _required_text(
    mapping: Mapping[str, Any], key: str, label: str, errors: list[str]
) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label}.{key} must be a non-empty string")
        return ""
    return value.strip()


def _optional_text(
    mapping: Mapping[str, Any], key: str, label: str, errors: list[str]
) -> str | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label}.{key} must be a non-empty string when provided")
        return None
    return value.strip()


def _required_int(
    mapping: Mapping[str, Any], key: str, label: str, errors: list[str]
) -> int:
    value = mapping.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        errors.append(f"{label}.{key} must be an integer")
        return 0
    return value


def _reject_duplicates(values: list[str], label: str, errors: list[str]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if duplicates:
        errors.append(f"duplicate {label}: " + ", ".join(sorted(duplicates)))


def _reject_unknown_keys(
    mapping: Mapping[str, Any],
    allowed: set[str],
    label: str,
    errors: list[str],
) -> None:
    unknown = sorted(str(key) for key in set(mapping) - allowed)
    if unknown:
        errors.append(f"{label}: unknown keys: " + ", ".join(unknown))


def _slot_inventory_sha256(
    jurisdictions: tuple[StateTaxJurisdictionContract, ...],
) -> str:
    rows = [
        (item.state, kind, slot.slot)
        for item in jurisdictions
        for kind, slots in (("inputs", item.inputs), ("relations", item.relations))
        for slot in slots
    ]
    payload = json.dumps(sorted(rows), separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _jurisdiction_registry_sha256(
    jurisdictions: tuple[StateTaxJurisdictionContract, ...],
) -> str:
    rows = [
        (
            item.state,
            item.fips,
            item.taxsim_state_code,
            item.jurisdiction,
            item.program,
            item.output,
            item.policyengine_target,
            item.tolerance,
            item.relative_tolerance,
        )
        for item in jurisdictions
    ]
    payload = json.dumps(sorted(rows), separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _source_metadata_sha256(
    jurisdictions: tuple[StateTaxJurisdictionContract, ...],
) -> str:
    rows = [
        (
            item.state,
            kind,
            slot.slot,
            slot.source_kind,
            slot.status,
            slot.evidence,
            slot.policyengine_variable,
            slot.policyengine_relationship,
        )
        for item in jurisdictions
        for kind, slots in (("inputs", item.inputs), ("relations", item.relations))
        for slot in slots
    ]
    payload = json.dumps(sorted(rows), separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _reject_alignment_controls(value: Any, *, errors: list[str], path: str = "contract") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized_key = str(key).strip().lower().replace("-", "_")
            child_path = f"{path}.{key}"
            if normalized_key in _FORBIDDEN_ALIGNMENT_KEYS:
                errors.append(
                    f"{child_path}: dynamic residual alignment/candidate selection "
                    "is forbidden"
                )
            if normalized_key == "strategy" and str(child).lower() in {"min", "max"}:
                errors.append(
                    f"{child_path}: candidate min/max selection is forbidden"
                )
            _reject_alignment_controls(child, errors=errors, path=child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_alignment_controls(
                child, errors=errors, path=f"{path}[{index}]"
            )


def _contract_to_document(contract: StateTaxPopulaceContract) -> dict[str, Any]:
    return {
        "schema_version": contract.schema_version,
        "validation_year": contract.validation_year,
        "population": {
            "country": contract.populace_country,
            "year": contract.populace_year,
            "repo_id": contract.populace_repo_id,
            "filename": contract.populace_filename,
            "revision": contract.populace_revision,
            "sha256": contract.populace_sha256,
            "built_with": contract.populace_built_with,
        },
        "population_scope": {
            "unit": contract.scope_unit,
            "geography_source": contract.scope_geography_source,
            "residency_model": contract.scope_residency_model,
            "inclusion": contract.scope_inclusion,
            "filtered_slices_allowed": contract.scope_filtered_slices_allowed,
            "evidence": contract.scope_evidence,
        },
        "registry_source": contract.registry_source,
        "jurisdictions": [
            {
                "state": item.state,
                "fips": item.fips,
                "taxsim_state_code": item.taxsim_state_code,
                "jurisdiction": item.jurisdiction,
                "program": item.program,
                "output": item.output,
                "policyengine": {
                    "target": item.policyengine_target,
                    "tolerance": item.tolerance,
                    "relative_tolerance": item.relative_tolerance,
                },
                "status": item.status,
                "evidence": item.evidence,
                "inputs": [_slot_to_document(slot) for slot in item.inputs],
                "relations": [_slot_to_document(slot) for slot in item.relations],
            }
            for item in contract.jurisdictions
        ],
    }


def _slot_to_document(slot: ProjectionSource) -> dict[str, Any]:
    document = {
        "slot": slot.slot,
        "source_kind": slot.source_kind,
        "status": slot.status,
        "evidence": slot.evidence,
    }
    if slot.policyengine_variable:
        document["policyengine_variable"] = slot.policyengine_variable
    if slot.policyengine_relationship:
        document["policyengine_relationship"] = slot.policyengine_relationship
    return document
