"""Route the pinned US Populace into state income-tax comparison scopes.

This module performs population accounting only.  It does not execute a
blocked RuleSpec program and it does not substitute PolicyEngine outputs for
unresolved Axiom inputs.  That separation lets the campaign audit the entire
national denominator before individual state projection contracts become
runnable.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
import hashlib
from importlib.metadata import PackageNotFoundError, version
import math
from pathlib import Path
import subprocess
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlparse

from .state_tax_populace import (
    EXPECTED_STATE_FIPS,
    StateTaxPopulaceContract,
    load_state_tax_populace_contract,
    validate_state_tax_populace_contract,
)


NO_BROAD_PIT_FIPS = {
    "AK": "02",
    "FL": "12",
    "NV": "32",
    "SD": "46",
    "TN": "47",
    "TX": "48",
    "WY": "56",
}
ALL_STATE_FIPS = {**EXPECTED_STATE_FIPS, **NO_BROAD_PIT_FIPS}
STATE_BY_FIPS = {fips: state for state, fips in ALL_STATE_FIPS.items()}

DISPOSITION_READY = "ready"
DISPOSITION_BLOCKED = "blocked_projection"
DISPOSITION_NO_BROAD_PIT = "not_applicable_no_broad_pit"
DISPOSITION_NONPOSITIVE_WEIGHT = "excluded_nonpositive_weight"
DISPOSITION_UNKNOWN_GEOGRAPHY = "excluded_unknown_geography"


class StateTaxPopulationRoutingError(ValueError):
    """Raised when entity links cannot support deterministic state routing."""


@dataclass(frozen=True)
class TaxUnitRoute:
    """One tax unit's deterministic geography and campaign disposition."""

    tax_unit_id: int | str
    household_id: int | str
    state: str | None
    fips: str | None
    weight: float
    disposition: str


def route_tax_units(
    *,
    raw_tax_units: Any,
    raw_persons: Any,
    raw_households: Any,
    contract: StateTaxPopulaceContract | Mapping[str, Any] | None = None,
) -> tuple[TaxUnitRoute, ...]:
    """Join tax units through people to household state and classify each one.

    A tax unit linked to multiple households is an integrity error, even when
    both households are in the same state.  Picking one would make results
    depend on row order and could silently attach the wrong population weight.
    """

    resolved_contract = (
        load_state_tax_populace_contract()
        if contract is None
        else validate_state_tax_populace_contract(contract)
    )
    by_state = resolved_contract.by_state()

    _require_columns(raw_tax_units, {"tax_unit_id"}, "tax_unit")
    _require_columns(
        raw_persons,
        {"person_tax_unit_id", "person_household_id"},
        "person",
    )
    _require_columns(
        raw_households,
        {"household_id", "state_fips", "household_weight"},
        "household",
    )

    tax_unit_ids = [_clean_id(value) for value in raw_tax_units["tax_unit_id"]]
    _reject_duplicate_ids(tax_unit_ids, "tax_unit_id")

    household_rows: dict[int | str, tuple[str | None, float]] = {}
    for row in raw_households.to_dict("records"):
        household_id = _clean_id(row["household_id"])
        if household_id in household_rows:
            raise StateTaxPopulationRoutingError(
                f"duplicate household_id in Populace: {household_id}"
            )
        household_rows[household_id] = (
            _normalize_fips(row["state_fips"]),
            _clean_weight(row["household_weight"]),
        )

    households_by_tax_unit: dict[int | str, set[int | str]] = defaultdict(set)
    for row in raw_persons.to_dict("records"):
        tax_unit_id = _clean_id(row["person_tax_unit_id"])
        household_id = _clean_id(row["person_household_id"])
        households_by_tax_unit[tax_unit_id].add(household_id)

    explicit_weights = None
    if "tax_unit_weight" in raw_tax_units.columns:
        explicit_weights = {
            _clean_id(row["tax_unit_id"]): _clean_weight(row["tax_unit_weight"])
            for row in raw_tax_units.to_dict("records")
        }

    routes: list[TaxUnitRoute] = []
    for tax_unit_id in tax_unit_ids:
        household_ids = households_by_tax_unit.get(tax_unit_id, set())
        if not household_ids:
            raise StateTaxPopulationRoutingError(
                f"tax_unit_id {tax_unit_id} has no person-to-household link"
            )
        if len(household_ids) != 1:
            rendered = ", ".join(str(value) for value in sorted(household_ids, key=str))
            raise StateTaxPopulationRoutingError(
                f"tax_unit_id {tax_unit_id} links to multiple households: {rendered}"
            )
        household_id = next(iter(household_ids))
        if household_id not in household_rows:
            raise StateTaxPopulationRoutingError(
                f"tax_unit_id {tax_unit_id} links to missing household_id "
                f"{household_id}"
            )
        fips, household_weight = household_rows[household_id]
        weight = (
            explicit_weights[tax_unit_id]
            if explicit_weights is not None
            else household_weight
        )
        state = STATE_BY_FIPS.get(fips or "")
        disposition = _disposition(
            state=state,
            weight=weight,
            contract_by_state=by_state,
        )
        routes.append(
            TaxUnitRoute(
                tax_unit_id=tax_unit_id,
                household_id=household_id,
                state=state,
                fips=fips,
                weight=weight,
                disposition=disposition,
            )
        )
    return tuple(routes)


def select_ready_tax_units(
    routes: Iterable[TaxUnitRoute], *, sample_size_per_state: int = 0
) -> tuple[TaxUnitRoute, ...]:
    """Select runnable units after routing and readiness filtering.

    ``sample_size_per_state=0`` means every ready positive-weight unit.  A
    positive limit is applied independently inside each state so a national
    diagnostic cannot consume its sample in the first state alphabetically.
    """

    if sample_size_per_state < 0:
        raise ValueError("sample_size_per_state must be zero or positive")
    ready_by_state: dict[str, list[TaxUnitRoute]] = defaultdict(list)
    for route in routes:
        if route.disposition == DISPOSITION_READY and route.state is not None:
            ready_by_state[route.state].append(route)

    selected: list[TaxUnitRoute] = []
    for state in sorted(ready_by_state):
        state_routes = sorted(
            ready_by_state[state], key=lambda item: _sortable_id(item.tax_unit_id)
        )
        if sample_size_per_state:
            state_routes = state_routes[:sample_size_per_state]
        selected.extend(state_routes)
    return tuple(selected)


def population_routing_report(
    routes: Iterable[TaxUnitRoute],
    *,
    sample_size_per_state: int = 0,
    dataset_identity: Mapping[str, Any] | None = None,
    contract: StateTaxPopulaceContract | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return complete national and per-state routing/readiness accounting."""

    resolved_contract = (
        load_state_tax_populace_contract()
        if contract is None
        else validate_state_tax_populace_contract(contract)
    )
    route_rows = tuple(routes)
    selected = select_ready_tax_units(
        route_rows, sample_size_per_state=sample_size_per_state
    )
    selected_ids = {item.tax_unit_id for item in selected}
    ledger: dict[str, dict[str, Any]] = {
        state: {
            "fips": fips,
            "tax_unit_count": 0,
            "positive_weight_count": 0,
            "weighted_tax_units": 0.0,
            "selected_count": 0,
            "dispositions": {},
            "weighted_dispositions": {},
        }
        for state, fips in sorted(ALL_STATE_FIPS.items())
    }
    unknown = {
        "fips": None,
        "tax_unit_count": 0,
        "positive_weight_count": 0,
        "weighted_tax_units": 0.0,
        "selected_count": 0,
        "dispositions": {},
        "weighted_dispositions": {},
    }
    for route in route_rows:
        bucket = ledger.get(route.state or "", unknown)
        bucket["tax_unit_count"] += 1
        if route.weight > 0:
            bucket["positive_weight_count"] += 1
            bucket["weighted_tax_units"] += route.weight
        if route.tax_unit_id in selected_ids:
            bucket["selected_count"] += 1
        dispositions = bucket["dispositions"]
        dispositions[route.disposition] = dispositions.get(route.disposition, 0) + 1
        weighted_dispositions = bucket["weighted_dispositions"]
        weighted_dispositions[route.disposition] = weighted_dispositions.get(
            route.disposition, 0.0
        ) + max(route.weight, 0.0)

    weighted_by_disposition = {
        disposition: sum(
            max(item.weight, 0.0)
            for item in route_rows
            if item.disposition == disposition
        )
        for disposition in sorted({item.disposition for item in route_rows})
    }

    report = {
        "schema_version": "axiom.state_tax_populace_routing_report.v1",
        "sample_size_per_state": sample_size_per_state,
        "tax_unit_count": len(route_rows),
        "positive_weight_count": sum(item.weight > 0 for item in route_rows),
        "weighted_tax_units": sum(item.weight for item in route_rows if item.weight > 0),
        "weighted_dispositions": weighted_by_disposition,
        "eligible_ready_count": sum(
            item.disposition == DISPOSITION_READY for item in route_rows
        ),
        "blocked_projection_count": sum(
            item.disposition == DISPOSITION_BLOCKED for item in route_rows
        ),
        "non_applicable_count": sum(
            item.disposition == DISPOSITION_NO_BROAD_PIT for item in route_rows
        ),
        "excluded_count": sum(
            item.disposition != DISPOSITION_READY for item in route_rows
        ),
        "weighted_eligible_ready_tax_units": weighted_by_disposition.get(
            DISPOSITION_READY, 0.0
        ),
        "weighted_excluded_tax_units": sum(
            weight
            for disposition, weight in weighted_by_disposition.items()
            if disposition != DISPOSITION_READY
        ),
        "errored_count": 0,
        "selected_ready_count": len(selected),
        "state_count": len(ledger),
        "population_scope": {
            "unit": resolved_contract.scope_unit,
            "geography_source": resolved_contract.scope_geography_source,
            "residency_model": resolved_contract.scope_residency_model,
            "inclusion": resolved_contract.scope_inclusion,
            "filtered_slices_allowed": (
                resolved_contract.scope_filtered_slices_allowed
            ),
        },
        "states": ledger,
        "unknown_geography": unknown,
    }
    if dataset_identity is not None:
        report["dataset_identity"] = dict(dataset_identity)
    return report


def runtime_provenance(*, rulespec_root: Path, axiom_rules_path: Path) -> dict[str, Any]:
    """Record source revisions and installed engine package versions."""

    rulespec_commit = _clean_git_commit(
        rulespec_root,
        expected_github_repository="TheAxiomFoundation/rulespec-us",
    )
    axiom_commit = _clean_git_commit(
        axiom_rules_path,
        expected_github_repository="TheAxiomFoundation/axiom-rules",
    )
    binary = Path(axiom_rules_path) / "target" / "release" / "axiom-rules-engine"
    if not binary.is_file():
        raise StateTaxPopulationRoutingError(
            f"axiom-rules-engine binary not found: {binary}"
        )
    return {
        "rulespec": {
            "repository": "TheAxiomFoundation/rulespec-us",
            "commit": rulespec_commit,
            "working_tree": "clean",
        },
        "axiom_engine": {
            "repository": "TheAxiomFoundation/axiom-rules",
            "commit": axiom_commit,
            "working_tree": "clean",
            "executable_sha256": _file_sha256(binary),
        },
        "packages": {
            package: _package_version(package)
            for package in ("policyengine", "policyengine-us")
        },
    }


def validate_campaign_dataset_identity(
    identity: Mapping[str, Any],
    *,
    contract: StateTaxPopulaceContract | Mapping[str, Any] | None = None,
) -> None:
    """Fail unless provenance identifies the contract's certified artifact."""

    resolved_contract = (
        load_state_tax_populace_contract()
        if contract is None
        else validate_state_tax_populace_contract(contract)
    )
    expected = {
        "source": "pinned",
        "country": resolved_contract.populace_country,
        "revision": resolved_contract.populace_revision,
        "built_with": resolved_contract.populace_built_with,
    }
    errors = [
        f"{key} must be {value!r}; got {identity.get(key)!r}"
        for key, value in expected.items()
        if identity.get(key) != value
    ]
    reported_sha = str(identity.get("sha256") or "")
    if len(reported_sha) < 12 or not resolved_contract.populace_sha256.startswith(
        reported_sha
    ):
        errors.append(
            "sha256 does not identify the contract's certified Populace artifact"
        )
    if errors:
        raise StateTaxPopulationRoutingError(
            "state-tax campaign dataset identity is not certified: "
            + "; ".join(errors)
        )


def route_rows(routes: Iterable[TaxUnitRoute]) -> list[dict[str, Any]]:
    """Serialize routes for diagnostics without exposing source microdata."""

    return [asdict(route) for route in routes]


def calculate_policyengine_targets(
    *,
    dataset: Any,
    raw_tax_units: Any,
    routes: Iterable[TaxUnitRoute],
    year: int,
    contract: StateTaxPopulaceContract | Mapping[str, Any] | None = None,
    microsimulation_factory: Callable[[Any], Any] | None = None,
) -> dict[str, dict[int | str, float]]:
    """Calculate only the declared comparison target for each ready state."""

    resolved_contract = (
        load_state_tax_populace_contract()
        if contract is None
        else validate_state_tax_populace_contract(contract)
    )
    if year != resolved_contract.validation_year:
        raise StateTaxPopulationRoutingError(
            f"comparison year must be {resolved_contract.validation_year}; got {year}"
        )
    _require_columns(raw_tax_units, {"tax_unit_id"}, "tax_unit")
    tax_unit_ids = [_clean_id(value) for value in raw_tax_units["tax_unit_id"]]
    selected_states = {
        route.state
        for route in routes
        if route.disposition == DISPOSITION_READY and route.state is not None
    }
    if microsimulation_factory is None:
        try:
            from policyengine_us import Microsimulation
        except ImportError as exc:  # pragma: no cover - optional runtime dependency
            raise RuntimeError(
                "Install the PolicyEngine extra to calculate state-tax targets."
            ) from exc
        def microsimulation_factory(source: Any) -> Any:
            return Microsimulation(dataset=source)
    sim = microsimulation_factory(dataset)

    targets: dict[str, dict[int | str, float]] = {}
    for state in sorted(selected_states):
        jurisdiction = resolved_contract.by_state()[state]
        values = _array_values(
            sim.calculate(jurisdiction.policyengine_target, period=year)
        )
        if len(values) != len(tax_unit_ids):
            raise StateTaxPopulationRoutingError(
                f"{state}: PolicyEngine target {jurisdiction.policyengine_target!r} "
                f"returned {len(values)} rows for {len(tax_unit_ids)} tax units"
            )
        targets[state] = {
            tax_unit_id: _finite_number(value, label=jurisdiction.policyengine_target)
            for tax_unit_id, value in zip(tax_unit_ids, values, strict=True)
        }
    return targets


def compare_ready_state_tax_units(
    *,
    routes: Iterable[TaxUnitRoute],
    policyengine_targets: Mapping[str, Mapping[int | str, float]],
    year: int,
    rulespec_root: Path,
    axiom_rules_path: Path,
    sample_size_per_state: int = 0,
    contract: StateTaxPopulaceContract | Mapping[str, Any] | None = None,
    axiom_runner: Callable[..., list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Execute every ready state once and compare all selected tax units.

    The current contract makes only New Hampshire runnable.  Future states are
    accepted automatically only after every declared input/relation becomes
    ready; until projection code is added for those source kinds this function
    fails closed rather than treating their inputs as zero.
    """

    resolved_contract = (
        load_state_tax_populace_contract()
        if contract is None
        else validate_state_tax_populace_contract(contract)
    )
    if year != resolved_contract.validation_year:
        raise StateTaxPopulationRoutingError(
            f"comparison year must be {resolved_contract.validation_year}; got {year}"
        )
    selected = select_ready_tax_units(
        routes, sample_size_per_state=sample_size_per_state
    )
    selected_by_state: dict[str, list[TaxUnitRoute]] = defaultdict(list)
    for route in selected:
        if route.state is not None:
            selected_by_state[route.state].append(route)

    if axiom_runner is None:
        from .tax_populace import run_axiom_program

        axiom_runner = run_axiom_program

    comparisons: dict[str, dict[str, Any]] = {}
    all_mismatches: list[dict[str, Any]] = []
    for state, state_routes in sorted(selected_by_state.items()):
        jurisdiction = resolved_contract.by_state()[state]
        if jurisdiction.inputs or jurisdiction.relations:
            raise StateTaxPopulationRoutingError(
                f"{state}: ready projection slots require a runtime projector; "
                "refusing implicit values"
            )
        state_targets = policyengine_targets.get(state)
        if state_targets is None:
            raise StateTaxPopulationRoutingError(
                f"{state}: missing PolicyEngine target results"
            )
        request = _constant_state_request(
            routes=state_routes,
            year=year,
            output=jurisdiction.output,
        )
        program = _program_path(rulespec_root, jurisdiction.program)
        results = axiom_runner(
            program=program,
            request=request,
            rulespec_root=rulespec_root,
            axiom_rules_path=axiom_rules_path,
        )
        if len(results) != len(state_routes):
            raise StateTaxPopulationRoutingError(
                f"{state}: Axiom returned {len(results)} results for "
                f"{len(state_routes)} selected tax units"
            )

        mismatches: list[dict[str, Any]] = []
        max_abs_diff = 0.0
        max_relative_diff = 0.0
        weighted_mismatch_tax_units = 0.0
        for route, result in zip(state_routes, results, strict=True):
            expected_entity = _tax_unit_entity_id(route.tax_unit_id)
            if result.get("entity_id") != expected_entity:
                raise StateTaxPopulationRoutingError(
                    f"{state}: Axiom result order/entity mismatch; expected "
                    f"{expected_entity!r}, got {result.get('entity_id')!r}"
                )
            outputs = result.get("outputs") or {}
            if jurisdiction.output not in outputs:
                raise StateTaxPopulationRoutingError(
                    f"{state}: Axiom result omitted {jurisdiction.output!r}"
                )
            axiom_value = _output_number(outputs[jurisdiction.output])
            if route.tax_unit_id not in state_targets:
                raise StateTaxPopulationRoutingError(
                    f"{state}: target omitted tax_unit_id {route.tax_unit_id}"
                )
            pe_value = _finite_number(
                state_targets[route.tax_unit_id],
                label=jurisdiction.policyengine_target,
            )
            abs_diff = abs(axiom_value - pe_value)
            relative_diff = abs_diff / max(abs(pe_value), 1.0)
            max_abs_diff = max(max_abs_diff, abs_diff)
            max_relative_diff = max(max_relative_diff, relative_diff)
            matched = (
                abs_diff <= jurisdiction.tolerance
                or relative_diff <= jurisdiction.relative_tolerance
            )
            if not matched:
                mismatch = {
                    "state": state,
                    "tax_unit_id": route.tax_unit_id,
                    "weight": route.weight,
                    "axiom": axiom_value,
                    "policyengine": pe_value,
                    "absolute_difference": abs_diff,
                    "relative_difference": relative_diff,
                }
                mismatches.append(mismatch)
                all_mismatches.append(mismatch)
                weighted_mismatch_tax_units += route.weight

        comparisons[state] = {
            "program": jurisdiction.program,
            "output": jurisdiction.output,
            "policyengine_target": jurisdiction.policyengine_target,
            "tolerance": jurisdiction.tolerance,
            "relative_tolerance": jurisdiction.relative_tolerance,
            "compared_count": len(state_routes),
            "weighted_compared_tax_units": sum(route.weight for route in state_routes),
            "mismatch_count": len(mismatches),
            "weighted_mismatch_tax_units": weighted_mismatch_tax_units,
            "max_absolute_difference": max_abs_diff,
            "max_relative_difference": max_relative_diff,
            "mismatches": mismatches,
        }

    return {
        "schema_version": "axiom.state_tax_populace_ready_comparison.v1",
        "validation_year": year,
        "sample_size_per_state": sample_size_per_state,
        "ready_state_count": len(comparisons),
        "compared_count": sum(
            item["compared_count"] for item in comparisons.values()
        ),
        "mismatch_count": len(all_mismatches),
        "states": comparisons,
        "mismatches": all_mismatches,
    }


def _constant_state_request(
    *, routes: Iterable[TaxUnitRoute], year: int, output: str
) -> dict[str, Any]:
    interval = {
        "period_kind": "tax_year",
        "start": f"{year:04d}-01-01",
        "end": f"{year:04d}-12-31",
    }
    return {
        "mode": "explain",
        "dataset": {"inputs": [], "relations": []},
        "queries": [
            {
                "entity_id": _tax_unit_entity_id(route.tax_unit_id),
                "period": interval,
                "outputs": [output],
            }
            for route in routes
        ],
    }


def _program_path(rulespec_root: Path, program: str) -> Path:
    jurisdiction, relative = program.split(":", 1)
    return Path(rulespec_root) / jurisdiction / f"{relative}.yaml"


def _tax_unit_entity_id(tax_unit_id: int | str) -> str:
    return f"state-tax-unit-{tax_unit_id}"


def _array_values(value: Any) -> list[Any]:
    raw = value.values if hasattr(value, "values") else value
    return list(raw)


def _finite_number(value: Any, *, label: str) -> float:
    if hasattr(value, "item"):
        value = value.item()
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise StateTaxPopulationRoutingError(
            f"{label} returned non-numeric value {value!r}"
        ) from exc
    if number != number or number in {float("inf"), float("-inf")}:
        raise StateTaxPopulationRoutingError(
            f"{label} returned non-finite value {number!r}"
        )
    return number


def _output_number(output: Any) -> float:
    value = output
    if isinstance(value, Mapping):
        value = value.get("value", value)
    if isinstance(value, Mapping):
        value = value.get("value", value)
    return _finite_number(value, label="Axiom output")


def _disposition(
    *,
    state: str | None,
    weight: float,
    contract_by_state: Mapping[str, Any],
) -> str:
    if weight <= 0:
        return DISPOSITION_NONPOSITIVE_WEIGHT
    if state is None:
        return DISPOSITION_UNKNOWN_GEOGRAPHY
    if state in NO_BROAD_PIT_FIPS:
        return DISPOSITION_NO_BROAD_PIT
    jurisdiction = contract_by_state[state]
    if jurisdiction.status == "ready":
        return DISPOSITION_READY
    return DISPOSITION_BLOCKED


def _require_columns(frame: Any, required: set[str], label: str) -> None:
    columns = set(getattr(frame, "columns", ()))
    missing = sorted(required - columns)
    if missing:
        raise StateTaxPopulationRoutingError(
            f"Populace {label} table is missing required columns: "
            + ", ".join(missing)
        )


def _reject_duplicate_ids(values: list[int | str], label: str) -> None:
    seen: set[int | str] = set()
    duplicates: set[int | str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if duplicates:
        rendered = ", ".join(str(value) for value in sorted(duplicates, key=str))
        raise StateTaxPopulationRoutingError(f"duplicate {label}: {rendered}")


def _clean_id(value: Any) -> int | str:
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, bytes):
        value = value.decode()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _normalize_fips(value: Any) -> str | None:
    value = _clean_id(value)
    if value is None or str(value).strip() in {"", "0", "0.0", "UNKNOWN", "nan"}:
        return None
    return str(value).strip().zfill(2)


def _clean_weight(value: Any) -> float:
    value = _clean_id(value)
    try:
        weight = float(value)
    except (TypeError, ValueError) as exc:
        raise StateTaxPopulationRoutingError(
            f"invalid Populace population weight: {value!r}"
        ) from exc
    if not math.isfinite(weight):
        raise StateTaxPopulationRoutingError(
            "Populace population weight must be finite"
        )
    return weight


def _clean_git_commit(path: Path, *, expected_github_repository: str) -> str:
    status = _git_output(
        path,
        "status",
        "--porcelain",
        "--untracked-files=all",
    )
    if status:
        raise StateTaxPopulationRoutingError(
            f"canonical state-tax run requires a clean checkout: {Path(path)}"
        )
    remote = _git_output(path, "remote", "get-url", "origin")
    if not _is_official_github_remote(remote, expected_github_repository):
        raise StateTaxPopulationRoutingError(
            f"unexpected git origin for canonical state-tax run: {Path(path)}"
        )
    commit = _git_output(path, "rev-parse", "HEAD")
    if len(commit) != 40:
        raise StateTaxPopulationRoutingError(
            f"invalid git commit provenance for {Path(path)}: {commit!r}"
        )
    return commit


def _is_official_github_remote(remote: str, expected_repository: str) -> bool:
    """Accept only exact github.com HTTPS/SSH remotes for ``owner/repo``."""

    remote = remote.strip()
    repository: str | None = None
    if remote.startswith("git@github.com:"):
        repository = remote.removeprefix("git@github.com:")
    else:
        parsed = urlparse(remote)
        if parsed.scheme in {"https", "ssh", "git"} and parsed.hostname == "github.com":
            repository = parsed.path.lstrip("/")
    if repository is None:
        return False
    return repository.removesuffix(".git").rstrip("/") == expected_repository


def _git_output(path: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=Path(path),
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise StateTaxPopulationRoutingError(
            f"cannot record git provenance for {Path(path)}: {exc}"
        ) from exc
    return result.stdout.strip()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError as exc:
        raise StateTaxPopulationRoutingError(
            f"cannot record required package version for {package}"
        ) from exc


def _sortable_id(value: int | str) -> tuple[int, int | str]:
    if isinstance(value, int):
        return (0, value)
    return (1, str(value))
