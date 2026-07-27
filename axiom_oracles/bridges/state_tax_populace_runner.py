"""Route and execute reviewed state income-tax Populace comparisons.

Population accounting remains independent of execution.  Runnable projections
are limited to exact sources admitted by the declarative contract; unresolved
slots remain blocked, and values may enter Axiom only through exact reviewed
upstream, statutory-constant, or derived-transform allowlists.
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
    DEFAULT_COMPARISON_AGGREGATION,
    EXPECTED_STATE_FIPS,
    StateTaxPopulaceContract,
    load_state_tax_populace_contract,
    validate_state_tax_populace_contract,
)


NO_BROAD_PIT_FIPS = {
    "AK": "02",
    "FL": "12",
    "NH": "33",
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

CT_ORDINARY_TAX_DERIVED_TARGET = (
    "ct_resident_ordinary_tax_before_personal_credit_derived"
)
DC_JOINT_SCHEDULE_BEFORE_CREDITS_TARGET = (
    "dc_income_tax_before_credits_joint"
)
KS_K40ES_SCHEDULE_BEFORE_CREDITS_REVIEWED_TARGET = (
    "ks_k40es_schedule_before_credits_reviewed"
)
OH_NONBUSINESS_BEFORE_CREDITS_DERIVED_TARGET = (
    "oh_nonbusiness_income_tax_before_non_refundable_credits_derived"
)
NY_MAIN_INCOME_TAX_TARGET = "ny_main_income_tax"
UT_RESIDENT_BEFORE_CREDITS_DERIVED_TARGET = (
    "ut_resident_income_tax_before_credits_derived"
)
_REVIEWED_ROUTE_BOOLEAN_INPUTS_BY_STATE = {
    "CT": frozenset(
        {
            "us-ct:policies/income_tax/"
            "2026_resident_ordinary_tax_before_personal_credit#input."
            "ct_pit_2026_is_full_year_connecticut_resident_return",
        }
    ),
    "UT": frozenset(
        {
            "us-ut:policies/income_tax/"
            "2026_full_year_resident_before_credit_schedule#input."
            "ut_pit_2026_is_full_year_utah_resident_return",
            "us-ut:policies/income_tax/"
            "2026_full_year_resident_before_credit_schedule#input."
            "ut_pit_2026_federal_and_utah_filing_units_are_aligned",
        }
    ),
}

_REVIEWED_PERSON_SUM_VARIABLES_BY_STATE = {
    "DE": frozenset({"de_taxable_income_joint"}),
    "HI": frozenset({"long_term_capital_gains"}),
    "KY": frozenset({"ky_taxable_income_indiv", "ky_taxable_income_joint"}),
    "MT": frozenset(
        {
            "long_term_capital_gains",
            "mt_taxable_income_joint",
            "short_term_capital_gains",
        }
    ),
}

# Exact Person-grain comparison targets permitted to be summed to the
# campaign's TaxUnit accounting grain.  These are outputs, not RuleSpec input
# sources, and therefore remain separate from the upstream-boundary allowlist.
_REVIEWED_PERSON_TARGETS_BY_STATE = {
    "AR": frozenset({"ar_income_tax_before_non_refundable_credits_indiv"}),
    "MS": frozenset({"ms_income_tax_before_credits_joint"}),
}

# Exact categorical facts used to establish that a legally distinct branch is
# absent from the selected certified population. These assertions are separate
# from RuleSpec input projection: they may only narrow the comparison scope by
# failing closed, never synthesize an input or choose a tax result.
_REVIEWED_RAW_PERSON_VALUE_ASSUMPTIONS_BY_STATE = {
    "NJ": {"immigration_status_str": "CITIZEN"},
}

# Exact upstream PolicyEngine values used only to prove that a modeled branch
# absent from the source-backed RuleSpec is not present in selected tax units.
# These assertions never supply an input or select an output branch.
_REVIEWED_PE_ZERO_ASSUMPTIONS_BY_STATE = {
    "VT": frozenset({"us_govt_interest"}),
}

# RuleSpec inputs are TaxUnit-grain unless their complete legal ID is listed
# here.  Keeping this state-and-slot allowlist beside the runtime projector
# prevents a newly declared input from silently changing entity grain.  These
# slots are intentionally staged before the DE/DC contract entries themselves.
_REVIEWED_PERSON_INPUT_SLOTS_BY_STATE = {
    "AR": frozenset(
        {
            "us-ar:policies/income_tax/pilot_liability_pipeline#input."
            "ar_pit_pilot_individual_taxable_income",
        }
    ),
    "DC": frozenset(
        {
            "us-dc:policies/income_tax/pilot_liability_pipeline#input."
            "dc_pit_pilot_supplied_separate_taxable_income",
            "us-dc:policies/income_tax/pilot_liability_pipeline#input."
            "dc_pit_pilot_taxpayer_is_included",
        }
    ),
    "DE": frozenset(
        {
            "us-de:policies/income_tax/pilot_liability_pipeline#input."
            "de_pit_pilot_supplied_separate_taxable_income",
            "us-de:policies/income_tax/pilot_liability_pipeline#input."
            "de_pit_pilot_taxpayer_is_included",
        }
    ),
    "MS": frozenset(
        {
            "us-ms:policies/income_tax/2026_section_27_7_5_schedule#input."
            "ms_pit_2026_supplied_taxable_income",
        }
    ),
}

# A relation is emitted only when its complete state/legal ID is declared and
# reviewed here. Runtime tuple order is explicit because the pinned engine's
# aggregation lowering currently uses slot 1 as the current TaxUnit and slot 0
# as the related Person; it does not preserve RuleSpec argument labels.
_REVIEWED_PERSON_TAX_UNIT_RELATIONS_BY_STATE = {
    "DC": {
        "us-dc:policies/income_tax/pilot_liability_pipeline#relation."
        "dc_pit_pilot_taxpayer_of_tax_unit": ("TaxUnit", "Person"),
    },
    "DE": {
        "us-de:policies/income_tax/pilot_liability_pipeline#relation."
        "de_pit_pilot_taxpayer_of_tax_unit": ("Person", "TaxUnit"),
    },
}

_REVIEWED_ALL_PERSON_RELATION_STATES = frozenset()

# Exact upstream PolicyEngine Person roles used to identify filers for the
# staged DE/DC separate-return candidates. Raw Person-to-TaxUnit links remain
# the source of relation tuples; these modeled roles only supply the explicit
# inclusion predicate consumed by sum_where.
_REVIEWED_PERSON_FILER_ROLE_VARIABLES = {
    (
        "DC",
        "us-dc:policies/income_tax/pilot_liability_pipeline#input."
        "dc_pit_pilot_taxpayer_is_included",
    ): ("is_tax_unit_head", "is_tax_unit_spouse"),
    (
        "DE",
        "us-de:policies/income_tax/pilot_liability_pipeline#input."
        "de_pit_pilot_taxpayer_is_included",
    ): ("is_tax_unit_head", "is_tax_unit_spouse"),
}

_REVIEWED_PERSON_FILER_SLOT_BY_STATE = {
    state: slot
    for state, slot in _REVIEWED_PERSON_FILER_ROLE_VARIABLES
}


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
        expected_github_repository="TheAxiomFoundation/axiom-rules-engine",
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
            "repository": "TheAxiomFoundation/axiom-rules-engine",
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
    raw_persons: Any | None = None,
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
        if (
            state == "CA"
            and jurisdiction.policyengine_target
            == "ca_mental_health_services_tax"
        ):
            modeled_ids = [
                _clean_id(value)
                for value in _array_values(
                    sim.calculate("tax_unit_id", period=year)
                )
            ]
            values = _array_values(
                sim.calculate(
                    jurisdiction.policyengine_target,
                    period=year,
                )
            )
            if (
                len(modeled_ids) != len(tax_unit_ids)
                or len(values) != len(tax_unit_ids)
            ):
                raise StateTaxPopulationRoutingError(
                    "CA: PolicyEngine Behavioral Health Services Tax target "
                    f"returned {len(modeled_ids)} IDs and {len(values)} values "
                    f"for {len(tax_unit_ids)} tax units"
                )
            _reject_duplicate_ids(tax_unit_ids, "CA source tax_unit_id")
            _reject_duplicate_ids(
                modeled_ids, "CA PolicyEngine tax_unit_id"
            )
            if modeled_ids != tax_unit_ids:
                raise StateTaxPopulationRoutingError(
                    "CA: PolicyEngine tax_unit_id order does not match the "
                    "certified source tax-unit order"
                )
            reviewed = [
                _finite_number(
                    value,
                    label=jurisdiction.policyengine_target,
                )
                for value in values
            ]
            if any(value < 0 for value in reviewed):
                raise StateTaxPopulationRoutingError(
                    "CA: ca_mental_health_services_tax must be nonnegative"
                )
            targets[state] = dict(
                zip(tax_unit_ids, reviewed, strict=True)
            )
            continue
        if (
            state == "CT"
            and jurisdiction.policyengine_target == CT_ORDINARY_TAX_DERIVED_TARGET
        ):
            after_credit = _array_values(
                sim.calculate("ct_income_tax_after_personal_credits", period=year)
            )
            credit_rate = _array_values(
                sim.calculate("ct_personal_credit_rate", period=year)
            )
            if len(after_credit) != len(tax_unit_ids) or len(credit_rate) != len(
                tax_unit_ids
            ):
                raise StateTaxPopulationRoutingError(
                    "CT: PolicyEngine ordinary-tax recovery inputs returned "
                    f"{len(after_credit)} and {len(credit_rate)} rows for "
                    f"{len(tax_unit_ids)} tax units"
                )
            recovered: list[float] = []
            for after_value, rate_value in zip(
                after_credit, credit_rate, strict=True
            ):
                after = _finite_number(
                    after_value, label="ct_income_tax_after_personal_credits"
                )
                rate = _finite_number(
                    rate_value, label="ct_personal_credit_rate"
                )
                if after < 0 or not 0 <= rate < 1:
                    raise StateTaxPopulationRoutingError(
                        "CT: ordinary-tax recovery requires nonnegative "
                        "after-credit tax and a personal-credit rate in [0, 1)"
                    )
                recovered.append(after / (1 - rate))
            targets[state] = dict(
                zip(tax_unit_ids, recovered, strict=True)
            )
            continue
        if state == "DC":
            if (
                jurisdiction.policyengine_target
                != DC_JOINT_SCHEDULE_BEFORE_CREDITS_TARGET
            ):
                raise StateTaxPopulationRoutingError(
                    "DC: reviewed schedule runner requires the exact "
                    "dc_income_tax_before_credits_joint target"
                )
            modeled_ids = [
                _clean_id(value)
                for value in _array_values(
                    sim.calculate("tax_unit_id", period=year)
                )
            ]
            taxable_income = _array_values(
                sim.calculate("dc_taxable_income_joint", period=year)
            )
            before_credits = _array_values(
                sim.calculate(
                    DC_JOINT_SCHEDULE_BEFORE_CREDITS_TARGET,
                    period=year,
                )
            )
            cardinalities = (
                len(modeled_ids),
                len(taxable_income),
                len(before_credits),
            )
            if any(length != len(tax_unit_ids) for length in cardinalities):
                raise StateTaxPopulationRoutingError(
                    "DC: PolicyEngine joint-method schedule inputs returned "
                    f"{', '.join(str(length) for length in cardinalities)} rows "
                    f"for {len(tax_unit_ids)} tax units"
                )
            _reject_duplicate_ids(tax_unit_ids, "DC source tax_unit_id")
            _reject_duplicate_ids(
                modeled_ids, "DC PolicyEngine tax_unit_id"
            )
            if modeled_ids != tax_unit_ids:
                raise StateTaxPopulationRoutingError(
                    "DC: PolicyEngine tax_unit_id order does not match the "
                    "certified source tax-unit order"
                )
            reviewed: list[float] = []
            for taxable_value, tax_value in zip(
                taxable_income,
                before_credits,
                strict=True,
            ):
                taxable = _finite_number(
                    taxable_value, label="dc_taxable_income_joint"
                )
                tax = _finite_number(
                    tax_value,
                    label=DC_JOINT_SCHEDULE_BEFORE_CREDITS_TARGET,
                )
                if tax < 0:
                    raise StateTaxPopulationRoutingError(
                        "DC: reviewed joint-method schedule requires "
                        "nonnegative before-credit tax"
                    )
                reviewed.append(tax)
            targets[state] = dict(
                zip(tax_unit_ids, reviewed, strict=True)
            )
            continue
        if (
            state == "KS"
            and jurisdiction.policyengine_target
            == KS_K40ES_SCHEDULE_BEFORE_CREDITS_REVIEWED_TARGET
        ):
            modeled_ids = [
                _clean_id(value)
                for value in _array_values(
                    sim.calculate("tax_unit_id", period=year)
                )
            ]
            taxable_income = _array_values(
                sim.calculate("ks_taxable_income", period=year)
            )
            joint_schedule = _array_values(
                sim.calculate("tax_unit_is_joint", period=year)
            )
            adjusted_gross_income = _array_values(
                sim.calculate("ks_agi", period=year)
            )
            before_credits = _array_values(
                sim.calculate("ks_income_tax_before_credits", period=year)
            )
            cardinalities = (
                len(modeled_ids),
                len(taxable_income),
                len(joint_schedule),
                len(adjusted_gross_income),
                len(before_credits),
            )
            if any(length != len(tax_unit_ids) for length in cardinalities):
                raise StateTaxPopulationRoutingError(
                    "KS: PolicyEngine K-40ES target inputs returned "
                    f"{', '.join(str(length) for length in cardinalities)} rows "
                    f"for {len(tax_unit_ids)} tax units"
                )
            _reject_duplicate_ids(tax_unit_ids, "KS source tax_unit_id")
            _reject_duplicate_ids(
                modeled_ids, "KS PolicyEngine tax_unit_id"
            )
            if modeled_ids != tax_unit_ids:
                raise StateTaxPopulationRoutingError(
                    "KS: PolicyEngine tax_unit_id order does not match the "
                    "certified source tax-unit order"
                )
            reviewed: list[float] = []
            for taxable_value, joint_value, agi_value, tax_value in zip(
                taxable_income,
                joint_schedule,
                adjusted_gross_income,
                before_credits,
                strict=True,
            ):
                taxable = _finite_number(
                    taxable_value, label="ks_taxable_income"
                )
                _strict_boolean(
                    joint_value, label="tax_unit_is_joint"
                )
                _finite_number(agi_value, label="ks_agi")
                tax = _finite_number(
                    tax_value, label="ks_income_tax_before_credits"
                )
                if taxable < 0 or tax < 0:
                    raise StateTaxPopulationRoutingError(
                        "KS: reviewed K-40ES target requires nonnegative "
                        "taxable income and before-credit tax"
                    )
                if taxable > 0 and tax == 0:
                    raise StateTaxPopulationRoutingError(
                        "KS: PolicyEngine's separate AGI gate suppressed a "
                        "positive K-40ES schedule domain"
                    )
                reviewed.append(tax)
            targets[state] = dict(
                zip(tax_unit_ids, reviewed, strict=True)
            )
            continue
        if (
            state == "OH"
            and jurisdiction.policyengine_target
            == OH_NONBUSINESS_BEFORE_CREDITS_DERIVED_TARGET
        ):
            modeled_ids = [
                _clean_id(value)
                for value in _array_values(
                    sim.calculate("tax_unit_id", period=year)
                )
            ]
            taxable_income = _array_values(
                sim.calculate("oh_taxable_income", period=year)
            )
            before_credits = _array_values(
                sim.calculate(
                    "oh_income_tax_before_non_refundable_credits",
                    period=year,
                )
            )
            if not (
                len(modeled_ids)
                == len(taxable_income)
                == len(before_credits)
                == len(tax_unit_ids)
            ):
                raise StateTaxPopulationRoutingError(
                    "OH: PolicyEngine threshold-corrected target inputs returned "
                    f"{len(modeled_ids)}, {len(taxable_income)}, and "
                    f"{len(before_credits)} rows for {len(tax_unit_ids)} tax units"
                )
            _reject_duplicate_ids(tax_unit_ids, "OH source tax_unit_id")
            _reject_duplicate_ids(modeled_ids, "OH PolicyEngine tax_unit_id")
            if modeled_ids != tax_unit_ids:
                raise StateTaxPopulationRoutingError(
                    "OH: PolicyEngine tax_unit_id order does not match the "
                    "certified source tax-unit order"
                )
            try:
                threshold_value = (
                    sim.tax_benefit_system.parameters(year)
                    .gov.states.oh.tax.income.agi_threshold
                )
            except (AttributeError, KeyError) as exc:
                raise StateTaxPopulationRoutingError(
                    "OH: PolicyEngine does not expose the reviewed Ohio "
                    "no-tax threshold parameter"
                ) from exc
            threshold = _finite_number(
                threshold_value,
                label="gov.states.oh.tax.income.agi_threshold",
            )
            if threshold < 0:
                raise StateTaxPopulationRoutingError(
                    "OH: gov.states.oh.tax.income.agi_threshold must be "
                    "nonnegative"
                )
            derived: list[float] = []
            for taxable_value, tax_value in zip(
                taxable_income, before_credits, strict=True
            ):
                taxable = _finite_number(
                    taxable_value, label="oh_taxable_income"
                )
                tax = _finite_number(
                    tax_value,
                    label="oh_income_tax_before_non_refundable_credits",
                )
                if taxable < 0 or tax < 0:
                    raise StateTaxPopulationRoutingError(
                        "OH: threshold-corrected target requires nonnegative "
                        "taxable income and before-credit tax"
                    )
                # Ohio Rev. Code section 5747.02(A)(3)(c) imposes no tax when
                # the nonbusiness-income balance is equal to or below this
                # threshold. PolicyEngine-US 1.752.2 uses a strict comparison
                # in oh_income_tax_exempt, so gate its otherwise published
                # schedule result with the authoritative parameter boundary.
                derived.append(0.0 if taxable <= threshold else tax)
            targets[state] = dict(
                zip(tax_unit_ids, derived, strict=True)
            )
            continue
        if state == "NY":
            if jurisdiction.policyengine_target != NY_MAIN_INCOME_TAX_TARGET:
                raise StateTaxPopulationRoutingError(
                    "NY: reviewed section 601 main-schedule runner requires "
                    "the exact ny_main_income_tax target"
                )
            modeled_ids = [
                _clean_id(value)
                for value in _array_values(
                    sim.calculate("tax_unit_id", period=year)
                )
            ]
            values = _array_values(
                sim.calculate(NY_MAIN_INCOME_TAX_TARGET, period=year)
            )
            if (
                len(modeled_ids) != len(tax_unit_ids)
                or len(values) != len(tax_unit_ids)
            ):
                raise StateTaxPopulationRoutingError(
                    "NY: PolicyEngine section 601 main-schedule target "
                    f"returned {len(modeled_ids)} IDs and {len(values)} values "
                    f"for {len(tax_unit_ids)} tax units"
                )
            _reject_duplicate_ids(tax_unit_ids, "NY source tax_unit_id")
            _reject_duplicate_ids(
                modeled_ids, "NY PolicyEngine tax_unit_id"
            )
            if modeled_ids != tax_unit_ids:
                raise StateTaxPopulationRoutingError(
                    "NY: PolicyEngine tax_unit_id order does not match the "
                    "certified source tax-unit order"
                )
            reviewed = [
                _finite_number(value, label=NY_MAIN_INCOME_TAX_TARGET)
                for value in values
            ]
            if any(value < 0 for value in reviewed):
                raise StateTaxPopulationRoutingError(
                    "NY: ny_main_income_tax must be nonnegative"
                )
            targets[state] = dict(
                zip(tax_unit_ids, reviewed, strict=True)
            )
            continue
        if (
            state == "UT"
            and jurisdiction.policyengine_target
            == UT_RESIDENT_BEFORE_CREDITS_DERIVED_TARGET
        ):
            before_credits = _array_values(
                sim.calculate("ut_income_tax_before_credits", period=year)
            )
            exemptions = _array_values(
                sim.calculate("ut_income_tax_exempt", period=year)
            )
            if len(before_credits) != len(tax_unit_ids) or len(exemptions) != len(
                tax_unit_ids
            ):
                raise StateTaxPopulationRoutingError(
                    "UT: PolicyEngine exemption-aware target inputs returned "
                    f"{len(before_credits)} and {len(exemptions)} rows for "
                    f"{len(tax_unit_ids)} tax units"
                )
            derived: list[float] = []
            for tax_value, exemption_value in zip(
                before_credits, exemptions, strict=True
            ):
                tax = _finite_number(
                    tax_value, label="ut_income_tax_before_credits"
                )
                if tax < 0:
                    raise StateTaxPopulationRoutingError(
                        "UT: ut_income_tax_before_credits must be nonnegative"
                    )
                exempt = _strict_boolean(
                    exemption_value, label="ut_income_tax_exempt"
                )
                derived.append(0.0 if exempt else tax)
            targets[state] = dict(zip(tax_unit_ids, derived, strict=True))
            continue
        comparison_aggregation = getattr(
            jurisdiction,
            "comparison_aggregation",
            DEFAULT_COMPARISON_AGGREGATION,
        )
        if comparison_aggregation == "person_sum_to_tax_unit":
            targets[state] = _reviewed_person_target_sums(
                state=state,
                sim=sim,
                variable=jurisdiction.policyengine_target,
                raw_persons=raw_persons,
                tax_unit_ids=tax_unit_ids,
                year=year,
            )
            continue
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


def calculate_policyengine_projection_inputs(
    *,
    dataset: Any,
    raw_tax_units: Any,
    raw_persons: Any | None = None,
    routes: Iterable[TaxUnitRoute],
    year: int,
    contract: StateTaxPopulaceContract | Mapping[str, Any] | None = None,
    microsimulation_factory: Callable[[Any], Any] | None = None,
) -> dict[str, dict[str, dict[int | str, float | bool]]]:
    """Calculate reviewed upstream, derived, and constant ready-state inputs."""

    resolved_contract = (
        load_state_tax_populace_contract()
        if contract is None
        else validate_state_tax_populace_contract(contract)
    )
    if year != resolved_contract.validation_year:
        raise StateTaxPopulationRoutingError(
            f"projection year must be {resolved_contract.validation_year}; got {year}"
        )
    _require_columns(raw_tax_units, {"tax_unit_id"}, "tax_unit")
    tax_unit_ids = [_clean_id(value) for value in raw_tax_units["tax_unit_id"]]
    _reject_duplicate_ids(tax_unit_ids, "tax_unit_id")
    route_rows = tuple(routes)
    selected_states = {
        route.state
        for route in route_rows
        if route.disposition == DISPOSITION_READY and route.state is not None
    }
    for state in sorted(selected_states):
        _validate_reviewed_population_assumptions(
            state=state,
            raw_persons=raw_persons,
            selected_tax_unit_ids={
                route.tax_unit_id
                for route in route_rows
                if route.state == state and route.disposition == DISPOSITION_READY
            },
        )
    if microsimulation_factory is None:
        try:
            from policyengine_us import Microsimulation
        except ImportError as exc:  # pragma: no cover - optional runtime dependency
            raise RuntimeError(
                "Install the PolicyEngine extra to calculate state-tax inputs."
            ) from exc

        def microsimulation_factory(source: Any) -> Any:
            return Microsimulation(dataset=source)

    sim = microsimulation_factory(dataset)
    for state in sorted(selected_states):
        _validate_reviewed_pe_zero_assumptions(
            state=state,
            sim=sim,
            tax_unit_ids=tax_unit_ids,
            selected_tax_unit_ids={
                route.tax_unit_id
                for route in route_rows
                if route.state == state and route.disposition == DISPOSITION_READY
            },
            year=year,
        )
    projections: dict[str, dict[str, dict[int | str, float | bool]]] = {}
    for state in sorted(selected_states):
        jurisdiction = resolved_contract.by_state()[state]
        if state == "NY":
            modeled_ids = [
                _clean_id(value)
                for value in _array_values(
                    sim.calculate("tax_unit_id", period=year)
                )
            ]
            if len(modeled_ids) != len(tax_unit_ids):
                raise StateTaxPopulationRoutingError(
                    "NY: PolicyEngine projection identity returned "
                    f"{len(modeled_ids)} IDs for {len(tax_unit_ids)} tax units"
                )
            _reject_duplicate_ids(
                modeled_ids, "NY PolicyEngine projection tax_unit_id"
            )
            if modeled_ids != tax_unit_ids:
                raise StateTaxPopulationRoutingError(
                    "NY: PolicyEngine projection tax_unit_id order does not "
                    "match the certified source tax-unit order"
                )
        _validate_runtime_relations(
            state=state,
            relations=jurisdiction.relations,
        )
        state_inputs: dict[str, dict[int | str, float | bool]] = {}
        person_input_slots = {
            slot.slot
            for slot in jurisdiction.inputs
            if _is_reviewed_person_input_slot(state=state, slot=slot.slot)
        }
        person_input_variables = {
            variable
            for slot in jurisdiction.inputs
            if slot.slot in person_input_slots
            for variable in (
                slot.policyengine_variables
                or ((slot.policyengine_variable,) if slot.policyengine_variable else ())
            )
        }
        person_ids: list[int | str] = []
        person_values: dict[str, list[Any]] = {}
        if person_input_slots:
            person_ids, person_values = _reviewed_person_values(
                state=state,
                sim=sim,
                variables=person_input_variables,
                raw_persons=raw_persons,
                tax_unit_ids=tax_unit_ids,
                year=year,
            )
        person_variables = {
            variable
            for slot in jurisdiction.inputs
            if slot.policyengine_transform
            in {
                "person_sum_to_tax_unit",
                "person_sums_to_net_long_term_capital_gain",
            }
            for variable in (
                slot.policyengine_variables
                or ((slot.policyengine_variable,) if slot.policyengine_variable else ())
            )
        }
        person_variables.update(
            variable
            for slot in jurisdiction.inputs
            if slot.policyengine_transform
            == "filing_method_selected_person_summed_taxable_income"
            for variable in slot.policyengine_variables[:2]
        )
        person_variables.update(
            variable
            for slot in jurisdiction.inputs
            if slot.policyengine_transform
            == "tax_unit_net_and_person_sum_to_capital_gains_worksheet_line_10"
            for variable in slot.policyengine_variables[1:]
        )
        person_sums: dict[str, list[float]] = {}
        if person_variables:
            person_sums = _reviewed_person_sums(
                state=state,
                sim=sim,
                variables=person_variables,
                raw_persons=raw_persons,
                tax_unit_ids=tax_unit_ids,
                year=year,
            )
        for slot in jurisdiction.inputs:
            if slot.slot in person_input_slots:
                filer_role_variables = _REVIEWED_PERSON_FILER_ROLE_VARIABLES.get(
                    (state, slot.slot)
                )
                if filer_role_variables:
                    if (
                        slot.source_kind != "derived"
                        or slot.policyengine_variable
                        or slot.policyengine_variables != filer_role_variables
                        or slot.policyengine_relationship != "upstream"
                        or slot.policyengine_transform != "person_filer_role_or"
                    ):
                        raise StateTaxPopulationRoutingError(
                            f"{state}: structural Person input {slot.slot!r} has "
                            "incompatible projection metadata"
                        )
                    state_inputs[slot.slot] = _reviewed_filer_inclusions(
                        state=state,
                        person_ids=person_ids,
                        person_tax_unit_ids=[
                            _clean_id(value)
                            for value in raw_persons["person_tax_unit_id"]
                        ],
                        tax_unit_ids=tax_unit_ids,
                        selected_tax_unit_ids={
                            route.tax_unit_id
                            for route in route_rows
                            if route.state == state
                            and route.disposition == DISPOSITION_READY
                        },
                        head_values=person_values[filer_role_variables[0]],
                        spouse_values=person_values[filer_role_variables[1]],
                    )
                    continue
                source_variables = slot.policyengine_variables or (
                    (slot.policyengine_variable,) if slot.policyengine_variable else ()
                )
                if len(source_variables) != 1 or slot.source_kind not in {
                    "pe_upstream_boundary",
                    "derived",
                }:
                    raise StateTaxPopulationRoutingError(
                        f"{state}: reviewed Person input {slot.slot!r} requires "
                        "one explicit PolicyEngine source variable"
                    )
                variable = source_variables[0]
                values = person_values[variable]
                projected = [
                    _apply_projection_transform(
                        value,
                        transform=slot.policyengine_transform,
                        label=slot.slot,
                    )
                    if slot.source_kind == "derived"
                    else _projection_scalar(value, label=f"{state}:{variable}")
                    for value in values
                ]
                state_inputs[slot.slot] = dict(
                    zip(person_ids, projected, strict=True)
                )
                continue
            if slot.source_kind == "statutory_constant":
                if slot.constant_value is None:
                    raise StateTaxPopulationRoutingError(
                        f"{state}: statutory constant omitted its reviewed value "
                        f"for {slot.slot}"
                    )
                state_inputs[slot.slot] = {
                    tax_unit_id: slot.constant_value for tax_unit_id in tax_unit_ids
                }
                continue
            if slot.source_kind == "raw_populace":
                reviewed_slots = _REVIEWED_ROUTE_BOOLEAN_INPUTS_BY_STATE.get(
                    state, frozenset()
                )
                if slot.slot not in reviewed_slots:
                    raise StateTaxPopulationRoutingError(
                        f"{state}: runtime projector does not support raw "
                        f"Populace source for {slot.slot}"
                    )
                ready_state_ids = {
                    route.tax_unit_id
                    for route in route_rows
                    if route.state == state
                    and route.disposition == DISPOSITION_READY
                }
                state_inputs[slot.slot] = {
                    tax_unit_id: tax_unit_id in ready_state_ids
                    for tax_unit_id in tax_unit_ids
                }
                continue
            source_variables = slot.policyengine_variables or (
                (slot.policyengine_variable,) if slot.policyengine_variable else ()
            )
            if slot.source_kind not in {"pe_upstream_boundary", "derived"} or not (
                source_variables
            ):
                raise StateTaxPopulationRoutingError(
                    f"{state}: runtime projector does not support ready source "
                    f"{slot.source_kind!r} for {slot.slot}"
                )
            if slot.policyengine_transform == "person_sum_to_tax_unit":
                projected = person_sums[source_variables[0]]
            elif (
                slot.policyengine_transform
                == "filing_method_selected_person_summed_taxable_income"
            ):
                if len(source_variables) != 3:
                    raise StateTaxPopulationRoutingError(
                        f"{state}: completed Kentucky net-income transform "
                        "requires separate-return and joint taxable-income sums "
                        "plus the filing-method branch"
                    )
                separate_values, joint_values = (
                    person_sums[variable] for variable in source_variables[:2]
                )
                filing_separately_values = _array_values(
                    sim.calculate(source_variables[2], period=year)
                )
                if len(filing_separately_values) != len(tax_unit_ids):
                    raise StateTaxPopulationRoutingError(
                        f"{state}: PolicyEngine boundary {source_variables[2]!r} "
                        f"returned {len(filing_separately_values)} rows for "
                        f"{len(tax_unit_ids)} tax units"
                    )
                projected = [
                    _apply_projection_transform(
                        (separate_value, joint_value, filing_separately),
                        transform=slot.policyengine_transform,
                        label=slot.slot,
                    )
                    for separate_value, joint_value, filing_separately in zip(
                        separate_values,
                        joint_values,
                        filing_separately_values,
                        strict=True,
                    )
                ]
            elif (
                slot.policyengine_transform
                == "person_sums_to_net_long_term_capital_gain"
            ):
                long_term, short_term = (
                    person_sums[variable] for variable in source_variables
                )
                projected = [
                    _apply_projection_transform(
                        (long_value, short_value),
                        transform=slot.policyengine_transform,
                        label=slot.slot,
                    )
                    for long_value, short_value in zip(
                        long_term, short_term, strict=True
                    )
                ]
            elif (
                slot.policyengine_transform
                == "tax_unit_net_and_person_sum_to_capital_gains_worksheet_line_10"
            ):
                if len(source_variables) != 2:
                    raise StateTaxPopulationRoutingError(
                        f"{state}: completed capital-gains worksheet transform "
                        "requires TaxUnit net gain and Person long-term gain"
                    )
                net_values = _array_values(
                    sim.calculate(source_variables[0], period=year)
                )
                long_term_values = person_sums[source_variables[1]]
                if len(net_values) != len(tax_unit_ids):
                    raise StateTaxPopulationRoutingError(
                        f"{state}: PolicyEngine boundary {source_variables[0]!r} "
                        f"returned {len(net_values)} rows for {len(tax_unit_ids)} "
                        "tax units"
                    )
                projected = [
                    _apply_projection_transform(
                        (net_value, long_term_value),
                        transform=slot.policyengine_transform,
                        label=slot.slot,
                    )
                    for net_value, long_term_value in zip(
                        net_values, long_term_values, strict=True
                    )
                ]
            else:
                variable = source_variables[0]
                values = _array_values(sim.calculate(variable, period=year))
                if len(values) != len(tax_unit_ids):
                    raise StateTaxPopulationRoutingError(
                        f"{state}: PolicyEngine boundary {variable!r} returned "
                        f"{len(values)} rows for {len(tax_unit_ids)} tax units"
                    )
                if slot.source_kind == "derived":
                    projected = [
                        _apply_projection_transform(
                            value,
                            transform=slot.policyengine_transform,
                            label=slot.slot,
                        )
                        for value in values
                    ]
                else:
                    projected = [
                        _projection_scalar(value, label=variable) for value in values
                    ]
            state_inputs[slot.slot] = dict(
                zip(tax_unit_ids, projected, strict=True)
            )
        projections[state] = state_inputs
    return projections


def _validate_reviewed_population_assumptions(
    *,
    state: str,
    raw_persons: Any | None,
    selected_tax_unit_ids: set[int | str],
) -> None:
    """Fail closed when a certified-population branch assertion is unproved."""

    assumptions = _REVIEWED_RAW_PERSON_VALUE_ASSUMPTIONS_BY_STATE.get(state)
    if assumptions is None:
        return
    if raw_persons is None:
        raise StateTaxPopulationRoutingError(
            f"{state}: reviewed population assumptions require the Populace "
            "person table"
        )
    _require_columns(
        raw_persons,
        {"person_tax_unit_id", *assumptions},
        "person",
        state=state,
    )

    normalized_tax_unit_ids = {_clean_id(value) for value in selected_tax_unit_ids}
    linked_tax_unit_ids: set[int | str] = set()
    unexpected: dict[str, set[str]] = defaultdict(set)
    unexpected_count: dict[str, int] = defaultdict(int)
    for row in raw_persons.to_dict("records"):
        tax_unit_id = _clean_id(row["person_tax_unit_id"])
        if tax_unit_id not in normalized_tax_unit_ids:
            continue
        linked_tax_unit_ids.add(tax_unit_id)
        for field, expected in assumptions.items():
            value = _clean_id(row[field])
            if value != expected:
                unexpected[field].add(repr(value))
                unexpected_count[field] += 1

    missing_links = normalized_tax_unit_ids - linked_tax_unit_ids
    if missing_links:
        raise StateTaxPopulationRoutingError(
            f"{state}: reviewed population assumptions cannot be proved because "
            f"{len(missing_links)} selected tax unit(s) have no linked person"
        )
    if unexpected:
        details = "; ".join(
            f"{field} expected {assumptions[field]!r}, found "
            f"{unexpected_count[field]} unexpected row(s) with value(s) "
            + ", ".join(sorted(values))
            for field, values in sorted(unexpected.items())
        )
        raise StateTaxPopulationRoutingError(
            f"{state}: reviewed population assumption failed: {details}"
        )


def _validate_reviewed_pe_zero_assumptions(
    *,
    state: str,
    sim: Any,
    tax_unit_ids: list[int | str],
    selected_tax_unit_ids: set[int | str],
    year: int,
) -> None:
    """Prove exact zero-valued upstream facts for selected TaxUnits."""

    variables = _REVIEWED_PE_ZERO_ASSUMPTIONS_BY_STATE.get(state)
    if variables is None:
        return
    selected_ids = {_clean_id(value) for value in selected_tax_unit_ids}
    known_ids = set(tax_unit_ids)
    unknown = sorted(selected_ids - known_ids, key=str)
    if unknown:
        raise StateTaxPopulationRoutingError(
            f"{state}: reviewed zero assumption references unknown tax_unit_id "
            "values: " + ", ".join(str(value) for value in unknown)
        )
    for variable in sorted(variables):
        values = _array_values(sim.calculate(variable, period=year))
        if len(values) != len(tax_unit_ids):
            raise StateTaxPopulationRoutingError(
                f"{state}: reviewed zero-assumption variable {variable!r} returned "
                f"{len(values)} rows for {len(tax_unit_ids)} tax units"
            )
        nonzero: list[int | str] = []
        for tax_unit_id, value in zip(tax_unit_ids, values, strict=True):
            if tax_unit_id not in selected_ids:
                continue
            number = _finite_number(value, label=f"{state}:{variable}")
            if number != 0:
                nonzero.append(tax_unit_id)
        if nonzero:
            raise StateTaxPopulationRoutingError(
                f"{state}: reviewed zero assumption failed for {variable!r}: "
                f"{len(nonzero)} selected tax unit(s) are nonzero"
            )


def compare_ready_state_tax_units(
    *,
    routes: Iterable[TaxUnitRoute],
    raw_persons: Any | None = None,
    known_tax_unit_ids: Iterable[int | str] | None = None,
    policyengine_targets: Mapping[str, Mapping[int | str, float]],
    policyengine_projection_inputs: Mapping[
        str, Mapping[str, Mapping[int | str, float | bool]]
    ]
    | None = None,
    year: int,
    rulespec_root: Path,
    axiom_rules_path: Path,
    sample_size_per_state: int = 0,
    contract: StateTaxPopulaceContract | Mapping[str, Any] | None = None,
    axiom_runner: Callable[..., list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Execute every ready state once and compare all selected tax units.

    Ready inputs must be supplied by the exact runtime projection surface and
    match the contract slot-for-slot.  Relations and unsupported source kinds
    fail closed rather than receiving implicit values.
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
    route_rows = tuple(routes)
    selected = select_ready_tax_units(
        route_rows, sample_size_per_state=sample_size_per_state
    )
    route_tax_unit_ids = {route.tax_unit_id for route in route_rows}
    all_tax_unit_ids = (
        {_clean_id(value) for value in known_tax_unit_ids}
        if known_tax_unit_ids is not None
        else route_tax_unit_ids
    )
    missing_route_ids = sorted(route_tax_unit_ids - all_tax_unit_ids, key=str)
    if missing_route_ids:
        raise StateTaxPopulationRoutingError(
            "comparison routes contain tax units outside the declared national "
            "TaxUnit-ID universe: "
            + ", ".join(str(value) for value in missing_route_ids)
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
        _validate_runtime_relations(
            state=state,
            relations=jurisdiction.relations,
        )
        declared_slots = {slot.slot for slot in jurisdiction.inputs}
        state_projection_inputs = dict(
            (policyengine_projection_inputs or {}).get(state, {})
        )
        supplied_slots = set(state_projection_inputs)
        if supplied_slots != declared_slots:
            missing = sorted(declared_slots - supplied_slots)
            extra = sorted(supplied_slots - declared_slots)
            raise StateTaxPopulationRoutingError(
                f"{state}: projected input inventory mismatch; "
                f"missing={missing}, extra={extra}"
            )
        state_targets = policyengine_targets.get(state)
        if state_targets is None:
            raise StateTaxPopulationRoutingError(
                f"{state}: missing PolicyEngine target results"
            )
        request = _state_request(
            state=state,
            routes=state_routes,
            year=year,
            output=jurisdiction.output,
            projected_inputs=state_projection_inputs,
            declared_relations=tuple(slot.slot for slot in jurisdiction.relations),
            raw_persons=raw_persons,
            all_tax_unit_ids=all_tax_unit_ids,
            comparison_aggregation=getattr(
                jurisdiction,
                "comparison_aggregation",
                DEFAULT_COMPARISON_AGGREGATION,
            ),
        )
        program = _program_path(rulespec_root, jurisdiction.program)
        try:
            results = axiom_runner(
                program=program,
                request=request,
                rulespec_root=rulespec_root,
                axiom_rules_path=axiom_rules_path,
            )
        except (OSError, RuntimeError, SystemExit, ValueError) as exc:
            raise StateTaxPopulationRoutingError(
                f"{state}: Axiom execution failed: {exc}"
            ) from exc
        comparison_aggregation = getattr(
            jurisdiction,
            "comparison_aggregation",
            DEFAULT_COMPARISON_AGGREGATION,
        )
        persons_by_tax_unit: dict[int | str, list[int | str]] = {}
        if comparison_aggregation == "person_sum_to_tax_unit":
            persons_by_tax_unit = _selected_person_members(
                state=state,
                raw_persons=raw_persons,
                all_tax_unit_ids=all_tax_unit_ids,
                selected_tax_unit_ids={route.tax_unit_id for route in state_routes},
            )
            expected_result_count = sum(map(len, persons_by_tax_unit.values()))
        else:
            expected_result_count = len(state_routes)
        if len(results) != expected_result_count:
            raise StateTaxPopulationRoutingError(
                f"{state}: Axiom returned {len(results)} results for "
                f"{expected_result_count} selected comparison entities"
            )

        axiom_values: dict[int | str, float] = {}
        if comparison_aggregation == "person_sum_to_tax_unit":
            result_index = 0
            for route in state_routes:
                total = 0.0
                for person_id in persons_by_tax_unit[route.tax_unit_id]:
                    result = results[result_index]
                    result_index += 1
                    expected_entity = _person_entity_id(person_id)
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
                    total += _output_number(outputs[jurisdiction.output])
                axiom_values[route.tax_unit_id] = total
        else:
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
                axiom_values[route.tax_unit_id] = _output_number(
                    outputs[jurisdiction.output]
                )

        mismatches: list[dict[str, Any]] = []
        case_rows: list[dict[str, Any]] = []
        max_abs_diff = 0.0
        max_relative_diff = 0.0
        weighted_mismatch_tax_units = 0.0
        for route in state_routes:
            axiom_value = axiom_values[route.tax_unit_id]
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
            # Every compared tax unit persists both engines' values so the
            # dashboard's case explorer can show matched households too,
            # not only the disagreements.
            case_rows.append(
                {
                    "tax_unit_id": route.tax_unit_id,
                    "weight": route.weight,
                    "axiom": round(axiom_value, 2),
                    "policyengine": round(pe_value, 2),
                    "matched": matched,
                }
            )

        comparisons[state] = {
            "program": jurisdiction.program,
            "output": jurisdiction.output,
            "policyengine_target": jurisdiction.policyengine_target,
            "tolerance": jurisdiction.tolerance,
            "relative_tolerance": jurisdiction.relative_tolerance,
            "comparison_aggregation": comparison_aggregation,
            "compared_count": len(state_routes),
            "weighted_compared_tax_units": sum(route.weight for route in state_routes),
            "mismatch_count": len(mismatches),
            "weighted_mismatch_tax_units": weighted_mismatch_tax_units,
            "max_absolute_difference": max_abs_diff,
            "max_relative_difference": max_relative_diff,
            "mismatches": mismatches,
            "cases": case_rows,
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


def _state_request(
    *,
    state: str,
    routes: Iterable[TaxUnitRoute],
    year: int,
    output: str,
    projected_inputs: Mapping[str, Mapping[int | str, float | bool]],
    declared_relations: tuple[str, ...] = (),
    raw_persons: Any | None = None,
    all_tax_unit_ids: set[int | str] | None = None,
    comparison_aggregation: str = DEFAULT_COMPARISON_AGGREGATION,
) -> dict[str, Any]:
    interval = {
        "period_kind": "tax_year",
        "start": f"{year:04d}-01-01",
        "end": f"{year:04d}-12-31",
    }
    route_rows = tuple(routes)
    selected_tax_unit_ids = {route.tax_unit_id for route in route_rows}
    person_slots = {
        slot
        for slot in projected_inputs
        if _is_reviewed_person_input_slot(state=state, slot=slot)
    }
    person_output = comparison_aggregation == "person_sum_to_tax_unit"
    if person_slots and not declared_relations and not person_output:
        raise StateTaxPopulationRoutingError(
            f"{state}: reviewed Person inputs require an explicitly declared "
            "state-allowlisted relation"
        )
    needs_people = bool(person_slots or declared_relations or person_output)
    persons_by_tax_unit: dict[int | str, list[int | str]] = {}
    if needs_people:
        persons_by_tax_unit = _selected_person_members(
            state=state,
            raw_persons=raw_persons,
            all_tax_unit_ids=(all_tax_unit_ids or selected_tax_unit_ids),
            selected_tax_unit_ids=selected_tax_unit_ids,
        )
        if declared_relations:
            filer_slot = _REVIEWED_PERSON_FILER_SLOT_BY_STATE.get(state)
            if (
                filer_slot is None
                and state not in _REVIEWED_ALL_PERSON_RELATION_STATES
            ):
                raise StateTaxPopulationRoutingError(
                    f"{state}: declared Person inputs/relations require the exact "
                    "reviewed taxpayer-inclusion input"
                )
            if filer_slot is not None:
                if filer_slot not in projected_inputs:
                    raise StateTaxPopulationRoutingError(
                        f"{state}: declared Person inputs/relations require the exact "
                        "reviewed taxpayer-inclusion input"
                    )
                inclusion_values = projected_inputs[filer_slot]
                for tax_unit_id, person_ids in persons_by_tax_unit.items():
                    for person_id in person_ids:
                        if person_id not in inclusion_values:
                            raise StateTaxPopulationRoutingError(
                                f"{state}: projected Person input {filer_slot!r} "
                                f"omitted person_id {person_id}"
                            )
                        _strict_boolean(
                            inclusion_values[person_id],
                            label=f"{state}:{filer_slot}",
                        )
    inputs: list[dict[str, Any]] = []
    if projected_inputs:
        from .tax_populace import input_record

        for route in route_rows:
            for slot, values in sorted(projected_inputs.items()):
                if slot in person_slots:
                    continue
                if route.tax_unit_id not in values:
                    raise StateTaxPopulationRoutingError(
                        f"{state}: projected input {slot!r} omitted tax_unit_id "
                        f"{route.tax_unit_id}"
                    )
                value = _projection_scalar(
                    values[route.tax_unit_id], label=f"{state}:{slot}"
                )
                inputs.append(
                    input_record(
                        slot,
                        _tax_unit_entity_id(route.tax_unit_id),
                        interval,
                        value,
                    )
                )
            for person_id in persons_by_tax_unit.get(route.tax_unit_id, ()):
                for slot in sorted(person_slots):
                    values = projected_inputs[slot]
                    if person_id not in values:
                        raise StateTaxPopulationRoutingError(
                            f"{state}: projected Person input {slot!r} omitted "
                            f"person_id {person_id}"
                        )
                    value = _projection_scalar(
                        values[person_id], label=f"{state}:{slot}"
                    )
                    inputs.append(
                        input_record(
                            slot,
                            _person_entity_id(person_id),
                            interval,
                            value,
                        )
                    )

    relations: list[dict[str, Any]] = []
    relation_orders = _REVIEWED_PERSON_TAX_UNIT_RELATIONS_BY_STATE.get(state, {})
    for route in route_rows:
        tax_unit_entity_id = _tax_unit_entity_id(route.tax_unit_id)
        for person_id in persons_by_tax_unit.get(route.tax_unit_id, ()):
            person_entity_id = _person_entity_id(person_id)
            entities = {
                "TaxUnit": tax_unit_entity_id,
                "Person": person_entity_id,
            }
            for relation in declared_relations:
                argument_order = relation_orders[relation]
                relations.append(
                    {
                        "name": relation,
                        "tuple": [entities[entity] for entity in argument_order],
                        "interval": interval,
                    }
                )
    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": relations},
        "queries": [
            {
                "entity_id": (
                    _person_entity_id(entity_id)
                    if person_output
                    else _tax_unit_entity_id(entity_id)
                ),
                "period": interval,
                "outputs": [output],
            }
            for entity_id in (
                [
                    person_id
                    for route in route_rows
                    for person_id in persons_by_tax_unit[route.tax_unit_id]
                ]
                if person_output
                else [route.tax_unit_id for route in route_rows]
            )
        ],
    }


def _validate_runtime_relations(*, state: str, relations: Iterable[Any]) -> None:
    declared = tuple(slot.slot for slot in relations)
    allowed = _REVIEWED_PERSON_TAX_UNIT_RELATIONS_BY_STATE.get(state, {})
    unsupported = sorted(set(declared) - set(allowed))
    if unsupported:
        raise StateTaxPopulationRoutingError(
            f"{state}: declared relation inventory contains no exact runtime "
            "projector: "
            + ", ".join(unsupported)
        )
    for slot in relations:
        if (
            slot.source_kind != "raw_populace"
            or slot.status != "ready"
            or slot.policyengine_variable
            or slot.policyengine_variables
            or slot.policyengine_relationship
            or slot.policyengine_transform
            or slot.constant_value is not None
        ):
            raise StateTaxPopulationRoutingError(
                f"{state}: relation {slot.slot!r} must be an explicit ready "
                "raw_populace relation without projection metadata"
            )


def _selected_person_members(
    *,
    state: str,
    raw_persons: Any | None,
    all_tax_unit_ids: set[int | str],
    selected_tax_unit_ids: set[int | str],
) -> dict[int | str, list[int | str]]:
    """Validate Person links and retain members of selected TaxUnits in row order."""

    if raw_persons is None:
        raise StateTaxPopulationRoutingError(
            f"{state}: declared Person inputs/relations require the Populace "
            "person table"
        )
    columns = set(getattr(raw_persons, "columns", ()))
    missing_columns = sorted({"person_id", "person_tax_unit_id"} - columns)
    if missing_columns:
        raise StateTaxPopulationRoutingError(
            f"{state}: Populace person table is missing required columns: "
            + ", ".join(missing_columns)
        )
    rows = raw_persons.to_dict("records")
    person_ids = [_clean_id(row["person_id"]) for row in rows]
    _reject_duplicate_ids(person_ids, "person_id", state=state)
    members: dict[int | str, list[int | str]] = {
        tax_unit_id: [] for tax_unit_id in selected_tax_unit_ids
    }
    unknown: set[int | str] = set()
    for row, person_id in zip(rows, person_ids, strict=True):
        tax_unit_id = _clean_id(row["person_tax_unit_id"])
        if tax_unit_id not in all_tax_unit_ids:
            unknown.add(tax_unit_id)
            continue
        if tax_unit_id in selected_tax_unit_ids:
            members[tax_unit_id].append(person_id)
    if unknown:
        raise StateTaxPopulationRoutingError(
            f"{state}: Populace people link to unknown tax_unit_id values: "
            + ", ".join(str(value) for value in sorted(unknown, key=str))
        )
    missing_members = sorted(
        (tax_unit_id for tax_unit_id, ids in members.items() if not ids), key=str
    )
    if missing_members:
        raise StateTaxPopulationRoutingError(
            f"{state}: selected tax units have no Person members: "
            + ", ".join(str(value) for value in missing_members)
        )
    return members


def _program_path(rulespec_root: Path, program: str) -> Path:
    jurisdiction, relative = program.split(":", 1)
    return Path(rulespec_root) / jurisdiction / f"{relative}.yaml"


def _tax_unit_entity_id(tax_unit_id: int | str) -> str:
    return f"state-tax-unit-{tax_unit_id}"


def _person_entity_id(person_id: int | str) -> str:
    return f"state-tax-person-{person_id}"


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


def _projection_scalar(value: Any, *, label: str) -> float | bool:
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, bool):
        return value
    return _finite_number(value, label=label)


def _apply_projection_transform(
    value: Any, *, transform: str | None, label: str
) -> float | bool:
    if hasattr(value, "item"):
        value = value.item()
    if transform == "greater_than_or_equal_65":
        value = _projection_scalar(value, label=label)
        if isinstance(value, bool):
            raise StateTaxPopulationRoutingError(
                f"{label}: age-threshold source returned boolean value"
            )
        return value >= 65
    if transform == "zero_one_to_boolean":
        value = _projection_scalar(value, label=label)
        if isinstance(value, bool):
            return value
        if value not in {0.0, 1.0}:
            raise StateTaxPopulationRoutingError(
                f"{label}: Boolean boundary must be exactly zero or one; got {value}"
            )
        return bool(value)
    if transform == "person_sums_to_net_long_term_capital_gain":
        if not isinstance(value, tuple) or len(value) != 2:
            raise StateTaxPopulationRoutingError(
                f"{label}: net-long-term-capital-gain transform requires exact "
                "(long-term, short-term) person sums"
            )
        long_term = _finite_number(value[0], label=f"{label}:long_term")
        short_term = _finite_number(value[1], label=f"{label}:short_term")
        return max(0.0, min(long_term, long_term + short_term))
    if transform == "filing_method_selected_person_summed_taxable_income":
        if not isinstance(value, tuple) or len(value) != 3:
            raise StateTaxPopulationRoutingError(
                f"{label}: completed Kentucky net-income transform requires exact "
                "(separate-return, joint) Person sums and filing-method branch"
            )
        separate = _finite_number(value[0], label=f"{label}:separate_return")
        joint = _finite_number(value[1], label=f"{label}:joint")
        filing_separately = _projection_scalar(
            value[2], label=f"{label}:filing_separately"
        )
        if not isinstance(filing_separately, bool):
            if filing_separately not in {0.0, 1.0}:
                raise StateTaxPopulationRoutingError(
                    f"{label}: filing-method branch must be boolean; "
                    f"got {filing_separately}"
                )
            filing_separately = bool(filing_separately)
        return max(0.0, separate if filing_separately else joint)
    if (
        transform
        == "tax_unit_net_and_person_sum_to_capital_gains_worksheet_line_10"
    ):
        if not isinstance(value, tuple) or len(value) != 2:
            raise StateTaxPopulationRoutingError(
                f"{label}: completed capital-gains worksheet transform requires "
                "exact (TaxUnit net gain, Person-summed long-term gain) values"
            )
        net_gain = _finite_number(value[0], label=f"{label}:net_capital_gain")
        long_term = _finite_number(
            value[1], label=f"{label}:long_term_capital_gains"
        )
        # PolicyEngine does not model the intervening Hawaii adjustments or
        # Form N-158 subtraction.  Clamp its modeled line-8 proxy to the
        # completed-return line-10 boundary's fail-closed nonnegative domain.
        return max(0.0, min(net_gain, long_term))
    if transform in {
        "filing_status_is_single",
        "filing_status_is_separate",
        "filing_status_joint_or_surviving_spouse",
        "filing_status_joint_surviving_spouse_or_head",
        "filing_status_is_head_of_household",
    }:
        allowed = {
            "SINGLE",
            "JOINT",
            "SEPARATE",
            "HEAD_OF_HOUSEHOLD",
            "SURVIVING_SPOUSE",
        }
        if not isinstance(value, str) or value not in allowed:
            raise StateTaxPopulationRoutingError(
                f"{label}: filing-status boundary has unsupported value {value!r}"
            )
        if transform == "filing_status_joint_or_surviving_spouse":
            return value in {"JOINT", "SURVIVING_SPOUSE"}
        if transform == "filing_status_is_single":
            return value == "SINGLE"
        if transform == "filing_status_is_separate":
            return value == "SEPARATE"
        if transform == "filing_status_is_head_of_household":
            return value == "HEAD_OF_HOUSEHOLD"
        return value in {"JOINT", "HEAD_OF_HOUSEHOLD", "SURVIVING_SPOUSE"}
    raise StateTaxPopulationRoutingError(
        f"{label}: unsupported reviewed projection transform {transform!r}"
    )


def _is_reviewed_person_input_slot(*, state: str, slot: str) -> bool:
    return slot in _REVIEWED_PERSON_INPUT_SLOTS_BY_STATE.get(state, frozenset())


def _strict_boolean(value: Any, *, label: str) -> bool:
    if hasattr(value, "item"):
        value = value.item()
    if not isinstance(value, bool):
        raise StateTaxPopulationRoutingError(
            f"{label}: expected a PolicyEngine boolean; got {value!r}"
        )
    return value


def _reviewed_filer_inclusions(
    *,
    state: str,
    person_ids: list[int | str],
    person_tax_unit_ids: list[int | str],
    tax_unit_ids: list[int | str],
    selected_tax_unit_ids: set[int | str],
    head_values: list[Any],
    spouse_values: list[Any],
) -> dict[int | str, bool]:
    """Project the exact modeled PE head-or-spouse inclusion predicate."""

    if not (
        len(person_ids)
        == len(person_tax_unit_ids)
        == len(head_values)
        == len(spouse_values)
    ):
        raise StateTaxPopulationRoutingError(
            f"{state}: PolicyEngine filer-role cardinality does not match the "
            "certified Populace person table"
        )
    heads_by_tax_unit: dict[int | str, int] = {
        tax_unit_id: 0 for tax_unit_id in tax_unit_ids
    }
    spouses_by_tax_unit: dict[int | str, int] = {
        tax_unit_id: 0 for tax_unit_id in tax_unit_ids
    }
    included: dict[int | str, bool] = {}
    for person_id, tax_unit_id, raw_head, raw_spouse in zip(
        person_ids,
        person_tax_unit_ids,
        head_values,
        spouse_values,
        strict=True,
    ):
        is_head = _strict_boolean(
            raw_head, label=f"{state}:is_tax_unit_head person_id {person_id}"
        )
        is_spouse = _strict_boolean(
            raw_spouse, label=f"{state}:is_tax_unit_spouse person_id {person_id}"
        )
        if is_head and is_spouse:
            raise StateTaxPopulationRoutingError(
                f"{state}: person_id {person_id} is both TaxUnit head and spouse"
            )
        heads_by_tax_unit[tax_unit_id] += int(is_head)
        spouses_by_tax_unit[tax_unit_id] += int(is_spouse)
        included[person_id] = is_head or is_spouse

    invalid = [
        tax_unit_id
        for tax_unit_id in tax_unit_ids
        if tax_unit_id in selected_tax_unit_ids
        and (
            heads_by_tax_unit[tax_unit_id] > 1
            or spouses_by_tax_unit[tax_unit_id] > 1
        )
    ]
    if invalid:
        details = ", ".join(
            f"{tax_unit_id} (heads={heads_by_tax_unit[tax_unit_id]}, "
            f"spouses={spouses_by_tax_unit[tax_unit_id]})"
            for tax_unit_id in invalid
        )
        raise StateTaxPopulationRoutingError(
            f"{state}: invalid PolicyEngine TaxUnit filer roles: {details}"
        )
    return included


def _reviewed_person_values(
    *,
    state: str,
    sim: Any,
    variables: set[str],
    raw_persons: Any | None,
    tax_unit_ids: list[int | str],
    year: int,
) -> tuple[list[int | str], dict[str, list[Any]]]:
    """Return Person-grain values after certified identity/link validation."""

    if raw_persons is None:
        raise StateTaxPopulationRoutingError(
            f"{state}: reviewed Person projections require the Populace person table"
        )
    _require_columns(
        raw_persons,
        {"person_id", "person_tax_unit_id"},
        "person",
        state=state,
    )
    person_ids = [_clean_id(value) for value in raw_persons["person_id"]]
    _reject_duplicate_ids(person_ids, "person_id", state=state)
    policyengine_person_ids = [
        _clean_id(value)
        for value in _array_values(sim.calculate("person_id", period=year))
    ]
    if len(policyengine_person_ids) != len(person_ids):
        raise StateTaxPopulationRoutingError(
            f"{state}: PolicyEngine Person cardinality does not match the certified "
            f"Populace person table ({len(policyengine_person_ids)} != "
            f"{len(person_ids)})"
        )
    if policyengine_person_ids != person_ids:
        raise StateTaxPopulationRoutingError(
            f"{state}: PolicyEngine Person identity/order does not match the certified "
            "Populace person table"
        )

    tax_unit_id_set = set(tax_unit_ids)
    person_tax_unit_ids = [
        _clean_id(value) for value in raw_persons["person_tax_unit_id"]
    ]
    unknown = sorted(set(person_tax_unit_ids) - tax_unit_id_set, key=str)
    if unknown:
        raise StateTaxPopulationRoutingError(
            f"{state}: Populace people link to unknown tax_unit_id values: "
            + ", ".join(str(value) for value in unknown)
        )
    missing = sorted(tax_unit_id_set - set(person_tax_unit_ids), key=str)
    if missing:
        raise StateTaxPopulationRoutingError(
            f"{state}: Populace tax units have no Person members: "
            + ", ".join(str(value) for value in missing)
        )
    policyengine_person_tax_unit_ids = [
        _clean_id(value)
        for value in _array_values(
            sim.calculate("tax_unit_id", period=year, map_to="person")
        )
    ]
    if len(policyengine_person_tax_unit_ids) != len(person_tax_unit_ids):
        raise StateTaxPopulationRoutingError(
            f"{state}: PolicyEngine Person-to-TaxUnit mapping cardinality does not "
            "match the certified Populace person table "
            f"({len(policyengine_person_tax_unit_ids)} != "
            f"{len(person_tax_unit_ids)})"
        )
    if policyengine_person_tax_unit_ids != person_tax_unit_ids:
        raise StateTaxPopulationRoutingError(
            f"{state}: PolicyEngine Person-to-TaxUnit mapping/order does not match "
            "certified person_tax_unit_id"
        )

    values_by_variable: dict[str, list[Any]] = {}
    for variable in sorted(variables):
        values = _array_values(sim.calculate(variable, period=year))
        if len(values) != len(person_ids):
            raise StateTaxPopulationRoutingError(
                f"{state}: PolicyEngine Person boundary {variable!r} returned "
                f"{len(values)} rows for {len(person_ids)} people"
            )
        values_by_variable[variable] = values
    return person_ids, values_by_variable


def _reviewed_person_sums(
    *,
    state: str,
    sim: Any,
    variables: set[str],
    raw_persons: Any | None,
    tax_unit_ids: list[int | str],
    year: int,
) -> dict[str, list[float]]:
    """Sum exact state-allowlisted Person boundaries to tax units.

    The aggregation mechanic is shared, but its accepted variables remain a
    narrow per-state allowlist. Person identity, order, cardinality, and every
    TaxUnit link are verified before any PolicyEngine values are used.
    """

    allowed = _REVIEWED_PERSON_SUM_VARIABLES_BY_STATE.get(state, frozenset())
    if not variables or not variables <= allowed:
        raise StateTaxPopulationRoutingError(
            f"{state}: unsupported Person-to-TaxUnit projection variables: "
            + ", ".join(sorted(variables))
        )
    person_ids, person_values = _reviewed_person_values(
        state=state,
        sim=sim,
        variables=variables,
        raw_persons=raw_persons,
        tax_unit_ids=tax_unit_ids,
        year=year,
    )
    person_tax_unit_ids = [
        _clean_id(value) for value in raw_persons["person_tax_unit_id"]
    ]

    sums: dict[str, list[float]] = {}
    for variable in sorted(variables):
        values = person_values[variable]
        by_tax_unit = {tax_unit_id: 0.0 for tax_unit_id in tax_unit_ids}
        for tax_unit_id, value in zip(person_tax_unit_ids, values, strict=True):
            by_tax_unit[tax_unit_id] += _finite_number(value, label=variable)
        sums[variable] = [by_tax_unit[tax_unit_id] for tax_unit_id in tax_unit_ids]
    return sums


def _reviewed_person_target_sums(
    *,
    state: str,
    sim: Any,
    variable: str,
    raw_persons: Any | None,
    tax_unit_ids: list[int | str],
    year: int,
) -> dict[int | str, float]:
    """Sum one exact allowlisted Person comparison target to TaxUnit grain."""

    if variable not in _REVIEWED_PERSON_TARGETS_BY_STATE.get(state, frozenset()):
        raise StateTaxPopulationRoutingError(
            f"{state}: unsupported Person comparison target {variable!r}"
        )
    _, person_values = _reviewed_person_values(
        state=state,
        sim=sim,
        variables={variable},
        raw_persons=raw_persons,
        tax_unit_ids=tax_unit_ids,
        year=year,
    )
    person_tax_unit_ids = [
        _clean_id(value) for value in raw_persons["person_tax_unit_id"]
    ]
    totals = {tax_unit_id: 0.0 for tax_unit_id in tax_unit_ids}
    for tax_unit_id, value in zip(
        person_tax_unit_ids, person_values[variable], strict=True
    ):
        totals[tax_unit_id] += _finite_number(value, label=variable)
    return totals


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


def _require_columns(
    frame: Any, required: set[str], label: str, *, state: str | None = None
) -> None:
    columns = set(getattr(frame, "columns", ()))
    missing = sorted(required - columns)
    if missing:
        prefix = f"{state}: " if state else ""
        raise StateTaxPopulationRoutingError(
            f"{prefix}Populace {label} table is missing required columns: "
            + ", ".join(missing)
        )


def _reject_duplicate_ids(
    values: list[int | str], label: str, *, state: str | None = None
) -> None:
    seen: set[int | str] = set()
    duplicates: set[int | str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if duplicates:
        rendered = ", ".join(str(value) for value in sorted(duplicates, key=str))
        prefix = f"{state}: " if state else ""
        raise StateTaxPopulationRoutingError(
            f"{prefix}duplicate {label}: {rendered}"
        )


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
