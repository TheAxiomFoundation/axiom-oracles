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
import struct
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
IL_INCOME_TAX_BEFORE_NONREFUNDABLE_CREDITS_TARGET = (
    "il_income_tax_before_non_refundable_credits"
)
IL_ANNUAL_BEFORE_CREDIT_PROGRAM = (
    "us-il:policies/income_tax/pilot_liability_pipeline"
)
IL_ANNUAL_BEFORE_CREDIT_OUTPUT = (
    f"{IL_ANNUAL_BEFORE_CREDIT_PROGRAM}#il_pit_pilot_income_tax_liability"
)
IL_REVIEWED_INPUTS = {
    (
        f"{IL_ANNUAL_BEFORE_CREDIT_PROGRAM}#input."
        "il_pit_pilot_state_taxable_income"
    ): "il_taxable_income",
    (
        f"{IL_ANNUAL_BEFORE_CREDIT_PROGRAM}#input."
        "il_pit_pilot_recapture_of_investment_credit"
    ): "recapture_of_investment_credit",
}
MN_BASIC_TAX_RAW_TARGET = "mn_basic_tax"
MN_BASIC_TAX_PRECISION_STABLE_TARGET = "mn_basic_tax_precision_stable"
IN_AGI_TAX_TARGET = "in_agi_tax"
IN_AGI_TAX_PROGRAM = "us-in:policies/income_tax/pilot_liability_pipeline"
IN_AGI_TAX_OUTPUT = (
    f"{IN_AGI_TAX_PROGRAM}#in_pit_pilot_income_tax_liability"
)
IN_AGI_TAX_INPUT = (
    f"{IN_AGI_TAX_PROGRAM}#input."
    "in_pit_pilot_indiana_adjusted_gross_income"
)
IN_AGI_TAX_UPSTREAM = "in_agi"
IN_AGI_TAX_2026_RATE = 0.0295
PA_BEFORE_FORGIVENESS_TARGET = "pa_income_tax_before_forgiveness"
PA_BEFORE_FORGIVENESS_PROGRAM = (
    "us-pa:policies/income_tax/pilot_liability_pipeline"
)
PA_BEFORE_FORGIVENESS_OUTPUT = (
    f"{PA_BEFORE_FORGIVENESS_PROGRAM}#pa_pit_pilot_income_tax_liability"
)
PA_BEFORE_FORGIVENESS_INPUT = (
    f"{PA_BEFORE_FORGIVENESS_PROGRAM}#input."
    "pa_pit_pilot_state_taxable_income"
)
PA_ADJUSTED_TAXABLE_INCOME = "pa_adjusted_taxable_income"
PA_2026_RATE = 0.0307
SC_BEFORE_NONREFUNDABLE_CREDITS_TARGET = (
    "sc_income_tax_before_non_refundable_credits"
)
SC_BEFORE_NONREFUNDABLE_CREDITS_PROGRAM = (
    "us-sc:policies/income_tax/pilot_liability_pipeline"
)
SC_BEFORE_NONREFUNDABLE_CREDITS_OUTPUT = (
    f"{SC_BEFORE_NONREFUNDABLE_CREDITS_PROGRAM}"
    "#sc_pit_pilot_income_tax_liability"
)
SC_BEFORE_NONREFUNDABLE_CREDITS_INPUT = (
    f"{SC_BEFORE_NONREFUNDABLE_CREDITS_PROGRAM}#input."
    "sc_pit_pilot_state_taxable_income"
)
SC_TAXABLE_INCOME = "sc_taxable_income"
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
    "DE": frozenset({"de_income_tax_before_non_refundable_credits_indv"}),
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


def _mn_basic_tax_parameter_scales(
    *,
    sim: Any,
    year: int,
) -> dict[str, tuple[tuple[float, ...], tuple[float, ...]]]:
    """Read the exact active scales used by PolicyEngine's mn_basic_tax."""

    tax_benefit_system = getattr(sim, "tax_benefit_system", None)
    variables = getattr(tax_benefit_system, "variables", None)
    variable = (
        variables.get(MN_BASIC_TAX_RAW_TARGET)
        if isinstance(variables, Mapping)
        else None
    )
    if (
        variable is None
        or getattr(variable, "name", None) != MN_BASIC_TAX_RAW_TARGET
        or getattr(getattr(variable, "entity", None), "key", None) != "tax_unit"
        or str(getattr(variable, "definition_period", "")) != "year"
        or getattr(variable, "value_type", None) is not float
        or not getattr(variable, "formulas", None)
    ):
        raise StateTaxPopulationRoutingError(
            "MN: mn_basic_tax class metadata or active formula schema drifted"
        )

    try:
        rates_node = (
            tax_benefit_system.parameters(year)
            .gov.states.mn.tax.income.rates
        )
    except (AttributeError, KeyError, TypeError) as exc:
        raise StateTaxPopulationRoutingError(
            "MN: mn_basic_tax active marginal-rate parameter path is unavailable"
        ) from exc

    scale_names = {
        "SINGLE": "single",
        "SEPARATE": "separate",
        "JOINT": "joint",
        "SURVIVING_SPOUSE": "surviving_spouse",
        "HEAD_OF_HOUSEHOLD": "head_of_household",
    }
    scales: dict[str, tuple[tuple[float, ...], tuple[float, ...]]] = {}
    for status, scale_name in scale_names.items():
        scale = getattr(rates_node, scale_name, None)
        try:
            thresholds = tuple(float(value) for value in scale.thresholds)
            rates = tuple(float(value) for value in scale.rates)
        except (AttributeError, TypeError, ValueError) as exc:
            raise StateTaxPopulationRoutingError(
                f"MN: mn_basic_tax {scale_name} marginal-rate scale is unavailable"
            ) from exc
        if (
            len(thresholds) != 4
            or len(rates) != 4
            or thresholds[0] != 0
            or any(not math.isfinite(value) for value in (*thresholds, *rates))
            or any(
                upper <= lower
                for lower, upper in zip(
                    thresholds,
                    thresholds[1:],
                    strict=False,
                )
            )
            or any(rate < 0 for rate in rates)
        ):
            raise StateTaxPopulationRoutingError(
                f"MN: mn_basic_tax {scale_name} marginal-rate scale schema drifted"
            )
        scales[status] = (thresholds, rates)
    return scales


def _mn_scale_tax(
    taxable_income: float,
    *,
    thresholds: tuple[float, ...],
    rates: tuple[float, ...],
) -> float:
    taxable = max(0.0, taxable_income)
    result = 0.0
    for index, (threshold, rate) in enumerate(
        zip(thresholds, rates, strict=True)
    ):
        if index + 1 == len(thresholds):
            width = max(0.0, taxable - threshold)
        else:
            width = min(
                max(0.0, taxable - threshold),
                thresholds[index + 1] - threshold,
            )
        result += width * rate
    return result


def _precision_stable_mn_basic_tax(
    *,
    sim: Any,
    year: int,
    expected_count: int,
) -> list[float]:
    """Recover mn_basic_tax in float64 and prove equivalence to its raw output.

    PolicyEngine stores money variables as binary32. At the extreme synthetic
    values present in Populace, one-half binary32 ULP can exceed the campaign's
    $1 structural tolerance. This projection reads only mn_basic_tax's own
    active PolicyEngine class, upstreams, and marginal scales. It fails closed
    unless the published raw output is the correctly rounded binary32 result.
    """

    raw_values = _array_values(
        sim.calculate(MN_BASIC_TAX_RAW_TARGET, period=year)
    )
    taxable_values = _array_values(
        sim.calculate("mn_taxable_income", period=year)
    )
    filing_status_result = sim.calculate("filing_status", period=year)
    expected_statuses = {
        "SINGLE",
        "SEPARATE",
        "JOINT",
        "SURVIVING_SPOUSE",
        "HEAD_OF_HOUSEHOLD",
    }
    possible_values = getattr(filing_status_result, "possible_values", None)
    if possible_values is not None and {
        member.name for member in possible_values
    } != expected_statuses:
        raise StateTaxPopulationRoutingError(
            "MN: filing_status enum schema drifted"
        )
    filing_status_values = (
        list(filing_status_result.decode_to_str())
        if callable(getattr(filing_status_result, "decode_to_str", None))
        else _array_values(filing_status_result)
    )
    cardinalities = (
        len(raw_values),
        len(taxable_values),
        len(filing_status_values),
    )
    if any(length != expected_count for length in cardinalities):
        raise StateTaxPopulationRoutingError(
            "MN: precision-stable basic-tax inputs returned "
            f"{', '.join(str(length) for length in cardinalities)} rows for "
            f"{expected_count} tax units"
        )

    scales = _mn_basic_tax_parameter_scales(sim=sim, year=year)
    recovered_values: list[float] = []
    for raw_value, taxable_value, status_value in zip(
        raw_values,
        taxable_values,
        filing_status_values,
        strict=True,
    ):
        raw = _finite_number(raw_value, label=MN_BASIC_TAX_RAW_TARGET)
        taxable = _finite_number(taxable_value, label="mn_taxable_income")
        status = str(status_value)
        if status not in scales:
            raise StateTaxPopulationRoutingError(
                "MN: filing_status returned an unsupported value "
                f"{status!r} for mn_basic_tax"
            )
        if raw < 0:
            raise StateTaxPopulationRoutingError(
                "MN: mn_basic_tax must be nonnegative"
            )
        thresholds, rates = scales[status]
        recovered = _mn_scale_tax(
            taxable,
            thresholds=thresholds,
            rates=rates,
        )
        if not math.isfinite(recovered) or recovered < 0:
            raise StateTaxPopulationRoutingError(
                "MN: recovered mn_basic_tax must be finite and nonnegative"
            )

        try:
            correctly_rounded_binary32 = struct.unpack(
                ">f",
                struct.pack(">f", recovered),
            )[0]
        except (OverflowError, struct.error) as exc:
            raise StateTaxPopulationRoutingError(
                "MN: recovered mn_basic_tax cannot be represented as finite "
                "IEEE-754 binary32"
            ) from exc
        if not math.isfinite(correctly_rounded_binary32):
            raise StateTaxPopulationRoutingError(
                "MN: recovered mn_basic_tax cannot be represented as finite "
                "IEEE-754 binary32"
            )
        if raw != correctly_rounded_binary32:
            raise StateTaxPopulationRoutingError(
                "MN: raw mn_basic_tax does not equal the correctly rounded "
                "IEEE-754 binary32 result"
            )
        recovered_values.append(recovered)
    return recovered_values


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
    route_rows = tuple(routes)
    selected_states = {
        route.state
        for route in route_rows
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
        if state == "IN":
            _validate_indiana_runtime_contract(jurisdiction)
            _validate_indiana_policyengine_runtime(sim=sim, year=year)
        if state == "PA":
            _validate_pennsylvania_runtime_contract(jurisdiction)
            _validate_pennsylvania_policyengine_runtime(sim=sim, year=year)
        if state == "SC":
            _validate_south_carolina_runtime_contract(jurisdiction)
            _validate_south_carolina_policyengine_runtime(sim=sim, year=year)
        if state == "IL":
            _validate_illinois_runtime_contract(jurisdiction)
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
        if state == "MN":
            if (
                jurisdiction.policyengine_target
                != MN_BASIC_TAX_PRECISION_STABLE_TARGET
            ):
                raise StateTaxPopulationRoutingError(
                    "MN: reviewed 2026 schedule runner requires the exact "
                    "mn_basic_tax_precision_stable target"
                )
            modeled_ids = [
                _clean_id(value)
                for value in _array_values(
                    sim.calculate("tax_unit_id", period=year)
                )
            ]
            if len(modeled_ids) != len(tax_unit_ids):
                raise StateTaxPopulationRoutingError(
                    "MN: PolicyEngine basic-tax target returned "
                    f"{len(modeled_ids)} IDs for "
                    f"{len(tax_unit_ids)} tax units"
                )
            _reject_duplicate_ids(tax_unit_ids, "MN source tax_unit_id")
            _reject_duplicate_ids(
                modeled_ids, "MN PolicyEngine tax_unit_id"
            )
            if modeled_ids != tax_unit_ids:
                raise StateTaxPopulationRoutingError(
                    "MN: PolicyEngine tax_unit_id order does not match the "
                    "certified source tax-unit order"
                )
            reviewed = _precision_stable_mn_basic_tax(
                sim=sim,
                year=year,
                expected_count=len(tax_unit_ids),
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
        if state == "IL":
            _require_policyengine_tax_unit_year_money_variable(
                sim,
                state="IL",
                variable=IL_INCOME_TAX_BEFORE_NONREFUNDABLE_CREDITS_TARGET,
            )
            modeled_ids = [
                _clean_id(value)
                for value in _array_values(
                    sim.calculate("tax_unit_id", period=year)
                )
            ]
            values = _array_values(
                sim.calculate(
                    IL_INCOME_TAX_BEFORE_NONREFUNDABLE_CREDITS_TARGET,
                    period=year,
                )
            )
            if (
                len(modeled_ids) != len(tax_unit_ids)
                or len(values) != len(tax_unit_ids)
            ):
                raise StateTaxPopulationRoutingError(
                    "IL: PolicyEngine annual-before-credit target returned "
                    f"{len(modeled_ids)} IDs and {len(values)} values for "
                    f"{len(tax_unit_ids)} tax units"
                )
            _reject_duplicate_ids(tax_unit_ids, "IL source tax_unit_id")
            _reject_duplicate_ids(
                modeled_ids, "IL PolicyEngine tax_unit_id"
            )
            if modeled_ids != tax_unit_ids:
                raise StateTaxPopulationRoutingError(
                    "IL: PolicyEngine tax_unit_id order does not match the "
                    "certified source tax-unit order"
                )
            reviewed = [
                _finite_number(
                    value,
                    label=IL_INCOME_TAX_BEFORE_NONREFUNDABLE_CREDITS_TARGET,
                )
                for value in values
            ]
            if any(value < 0 for value in reviewed):
                raise StateTaxPopulationRoutingError(
                    "IL: il_income_tax_before_non_refundable_credits must be "
                    "nonnegative"
                )
            targets[state] = dict(
                zip(tax_unit_ids, reviewed, strict=True)
            )
            continue
        if state == "IN":
            modeled_ids = [
                _clean_id(value)
                for value in _array_values(
                    sim.calculate("tax_unit_id", period=year)
                )
            ]
            agi_values = _array_values(
                sim.calculate(IN_AGI_TAX_UPSTREAM, period=year)
            )
            tax_values = _array_values(
                sim.calculate(IN_AGI_TAX_TARGET, period=year)
            )
            cardinalities = (
                len(modeled_ids),
                len(agi_values),
                len(tax_values),
            )
            if any(length != len(tax_unit_ids) for length in cardinalities):
                raise StateTaxPopulationRoutingError(
                    "IN: PolicyEngine AGI-tax target inputs returned "
                    f"{', '.join(str(length) for length in cardinalities)} rows "
                    f"for {len(tax_unit_ids)} tax units"
                )
            _reject_duplicate_ids(tax_unit_ids, "IN source tax_unit_id")
            _reject_duplicate_ids(
                modeled_ids, "IN PolicyEngine tax_unit_id"
            )
            if modeled_ids != tax_unit_ids:
                raise StateTaxPopulationRoutingError(
                    "IN: PolicyEngine tax_unit_id order does not match the "
                    "certified source tax-unit order"
                )
            reviewed: list[float] = []
            for agi_value, tax_value in zip(
                agi_values, tax_values, strict=True
            ):
                agi = _finite_number(agi_value, label=IN_AGI_TAX_UPSTREAM)
                tax = _finite_number(tax_value, label=IN_AGI_TAX_TARGET)
                if tax < 0:
                    raise StateTaxPopulationRoutingError(
                        "IN: in_agi_tax must be nonnegative"
                    )
                if agi <= 0 and tax != 0:
                    raise StateTaxPopulationRoutingError(
                        "IN: nonpositive in_agi must produce exactly zero "
                        "in_agi_tax"
                    )
                if agi > 0 and tax <= 0:
                    raise StateTaxPopulationRoutingError(
                        "IN: positive in_agi must produce positive in_agi_tax"
                    )
                reviewed.append(tax)
            targets[state] = dict(
                zip(tax_unit_ids, reviewed, strict=True)
            )
            continue
        if state == "PA":
            modeled_ids = [
                _clean_id(value)
                for value in _array_values(
                    sim.calculate("tax_unit_id", period=year)
                )
            ]
            taxable_values = _array_values(
                sim.calculate(PA_ADJUSTED_TAXABLE_INCOME, period=year)
            )
            tax_values = _array_values(
                sim.calculate(PA_BEFORE_FORGIVENESS_TARGET, period=year)
            )
            cardinalities = (
                len(modeled_ids),
                len(taxable_values),
                len(tax_values),
            )
            if any(length != len(tax_unit_ids) for length in cardinalities):
                raise StateTaxPopulationRoutingError(
                    "PA: PolicyEngine before-forgiveness target inputs returned "
                    f"{', '.join(str(length) for length in cardinalities)} rows "
                    f"for {len(tax_unit_ids)} tax units"
                )
            _reject_duplicate_ids(tax_unit_ids, "PA source tax_unit_id")
            _reject_duplicate_ids(
                modeled_ids, "PA PolicyEngine tax_unit_id"
            )
            if modeled_ids != tax_unit_ids:
                raise StateTaxPopulationRoutingError(
                    "PA: PolicyEngine tax_unit_id order does not match the "
                    "certified source tax-unit order"
                )
            selected_ids = {
                route.tax_unit_id
                for route in route_rows
                if route.state == "PA"
                and route.disposition == DISPOSITION_READY
            }
            reviewed: list[float] = []
            selected_taxable: list[float] = []
            selected_tax: list[float] = []
            for tax_unit_id, taxable_value, tax_value in zip(
                tax_unit_ids,
                taxable_values,
                tax_values,
                strict=True,
            ):
                taxable = _finite_number(
                    taxable_value,
                    label=PA_ADJUSTED_TAXABLE_INCOME,
                )
                tax = _finite_number(
                    tax_value,
                    label=PA_BEFORE_FORGIVENESS_TARGET,
                )
                if tax_unit_id in selected_ids:
                    if taxable < 0:
                        raise StateTaxPopulationRoutingError(
                            "PA: every selected pa_adjusted_taxable_income "
                            "value must be nonnegative"
                        )
                    if tax < 0:
                        raise StateTaxPopulationRoutingError(
                            "PA: pa_income_tax_before_forgiveness must be "
                            "nonnegative for every selected tax unit"
                        )
                    if taxable == 0 and tax != 0:
                        raise StateTaxPopulationRoutingError(
                            "PA: zero pa_adjusted_taxable_income must produce "
                            "exactly zero pa_income_tax_before_forgiveness"
                        )
                    if taxable > 0 and tax <= 0:
                        raise StateTaxPopulationRoutingError(
                            "PA: positive pa_adjusted_taxable_income must "
                            "produce positive pa_income_tax_before_forgiveness"
                        )
                    selected_taxable.append(taxable)
                    selected_tax.append(tax)
                reviewed.append(tax)
            if not selected_taxable:
                raise StateTaxPopulationRoutingError(
                    "PA: before-forgiveness promotion requires selected tax "
                    "units"
                )
            if not any(value == 0 for value in selected_taxable) or not any(
                value > 0 for value in selected_taxable
            ):
                raise StateTaxPopulationRoutingError(
                    "PA: selected pa_adjusted_taxable_income must include both "
                    "zero and positive witnesses"
                )
            if not any(value == 0 for value in selected_tax) or not any(
                value > 0 for value in selected_tax
            ):
                raise StateTaxPopulationRoutingError(
                    "PA: selected pa_income_tax_before_forgiveness must include "
                    "both zero and positive witnesses"
                )
            targets[state] = dict(
                zip(tax_unit_ids, reviewed, strict=True)
            )
            continue
        if state == "SC":
            modeled_ids = [
                _clean_id(value)
                for value in _array_values(
                    sim.calculate("tax_unit_id", period=year)
                )
            ]
            taxable_values = _array_values(
                sim.calculate(SC_TAXABLE_INCOME, period=year)
            )
            tax_values = _array_values(
                sim.calculate(
                    SC_BEFORE_NONREFUNDABLE_CREDITS_TARGET,
                    period=year,
                )
            )
            cardinalities = (
                len(modeled_ids),
                len(taxable_values),
                len(tax_values),
            )
            if any(length != len(tax_unit_ids) for length in cardinalities):
                raise StateTaxPopulationRoutingError(
                    "SC: PolicyEngine before-nonrefundable-credits target "
                    "inputs returned "
                    f"{', '.join(str(length) for length in cardinalities)} rows "
                    f"for {len(tax_unit_ids)} tax units"
                )
            _reject_duplicate_ids(tax_unit_ids, "SC source tax_unit_id")
            _reject_duplicate_ids(
                modeled_ids, "SC PolicyEngine tax_unit_id"
            )
            if modeled_ids != tax_unit_ids:
                raise StateTaxPopulationRoutingError(
                    "SC: PolicyEngine tax_unit_id order does not match the "
                    "certified source tax-unit order"
                )
            selected_ids = {
                route.tax_unit_id
                for route in route_rows
                if route.state == "SC"
                and route.disposition == DISPOSITION_READY
            }
            reviewed: list[float] = []
            selected_taxable: list[float] = []
            selected_tax: list[float] = []
            for tax_unit_id, taxable_value, tax_value in zip(
                tax_unit_ids,
                taxable_values,
                tax_values,
                strict=True,
            ):
                taxable = _finite_number(
                    taxable_value,
                    label=SC_TAXABLE_INCOME,
                )
                tax = _finite_number(
                    tax_value,
                    label=SC_BEFORE_NONREFUNDABLE_CREDITS_TARGET,
                )
                if tax_unit_id in selected_ids:
                    if taxable < 0:
                        raise StateTaxPopulationRoutingError(
                            "SC: every selected sc_taxable_income value must "
                            "be nonnegative"
                        )
                    if tax < 0:
                        raise StateTaxPopulationRoutingError(
                            "SC: tax before nonrefundable credits must be "
                            "nonnegative for every selected tax unit"
                        )
                    if taxable == 0 and tax != 0:
                        raise StateTaxPopulationRoutingError(
                            "SC: zero sc_taxable_income must produce exactly "
                            "zero tax before nonrefundable credits"
                        )
                    if taxable > 0 and tax <= 0:
                        raise StateTaxPopulationRoutingError(
                            "SC: positive sc_taxable_income must produce "
                            "positive tax before nonrefundable credits"
                        )
                    selected_taxable.append(taxable)
                    selected_tax.append(tax)
                reviewed.append(tax)
            if not selected_taxable:
                raise StateTaxPopulationRoutingError(
                    "SC: before-nonrefundable-credits promotion requires "
                    "selected tax units"
                )
            if not any(value == 0 for value in selected_taxable) or not any(
                value > 0 for value in selected_taxable
            ):
                raise StateTaxPopulationRoutingError(
                    "SC: selected sc_taxable_income must include both zero "
                    "and positive witnesses"
                )
            if not any(value == 0 for value in selected_tax) or not any(
                value > 0 for value in selected_tax
            ):
                raise StateTaxPopulationRoutingError(
                    "SC: selected tax before nonrefundable credits must "
                    "include both zero and positive witnesses"
                )
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


# Person-level PolicyEngine variables projected into the per-tax-unit TAXSIM
# input row. Concept keys mirror populations/populace_us.py's person loader so
# the populace TAXSIM leg feeds the binary the same input surface as the
# Enhanced-CPS lanes (adapters/taxsim/projection.taxsim_input_for_case is the
# single row-assembly authority for both).
_TAXSIM_PERSON_NON_WAGE_VARIABLES: dict[str, str] = {
    "self_employment_income": "self_employment_income",
    "dividend_income": "dividend_income",
    "qualified_dividend_income": "qualified_dividend_income",
    "interest_income": "taxable_interest_income",
    "short_term_capital_gains": "short_term_capital_gains",
    "long_term_capital_gains": "long_term_capital_gains",
    "pension_income": "taxable_pension_income",
    "social_security_benefits": "social_security",
    "unemployment_insurance_income": "unemployment_compensation",
    "rental_income": "rental_income",
}


def taxsim_target_column(output_concept: str) -> str | None:
    """The TAXSIM output column graded for a jurisdiction's output concept.

    Resolved from the concept mapping so the graded surface is declared in
    one place: pre-credit schedule concepts map ``staxbc`` (state tax before
    credits; staxbc - v40 total credits = siitax on the pinned binary),
    final-liability concepts map ``siitax``. A concept with no ``taxsim``
    mapping returns None and its jurisdiction is *skipped* by the TAXSIM
    leg — never silently graded against a guessed column. (The audit that
    forced this: CT/DC/KS/MN/OH populace outputs are pre-credit schedules a
    ``siitax`` default would misgrade, and CA's Behavioral Health Services
    Tax has no truthful TAXSIM surface at all.)
    """
    from ..comparison.mappings import engine_targets_for_concepts

    targets = engine_targets_for_concepts([output_concept], "taxsim")
    return targets[0] if targets else None


def calculate_taxsim_targets(
    *,
    dataset: Any,
    raw_tax_units: Any,
    raw_persons: Any,
    routes: Iterable[TaxUnitRoute],
    year: int,
    contract: StateTaxPopulaceContract | Mapping[str, Any] | None = None,
    microsimulation_factory: Callable[[Any], Any] | None = None,
    taxsim_runner_factory: Callable[[Any], Any] | None = None,
) -> dict[str, dict[int | str, float]]:
    """Calculate the TAXSIM oracle value for every ready-routed tax unit.

    The second oracle leg beside :func:`calculate_policyengine_targets`: each
    ready state's selected tax units are projected into TAXSIM input rows
    (via the shared ``taxsim_input_for_case`` projection), executed once per
    state through the pinned policyengine-taxsim binary, and graded on the
    column :func:`taxsim_target_column` resolves for the jurisdiction's
    output concept. Person identity, order, and tax-unit links are verified
    against the certified Populace tables before any values are used —
    the same fail-closed discipline as the PolicyEngine legs.
    """

    from ..adapters.taxsim.projection import taxsim_input_for_case
    from ..core.case import Case, Concepts, Entity

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
    _reject_duplicate_ids(tax_unit_ids, "tax_unit_id")
    if raw_persons is None:
        raise StateTaxPopulationRoutingError(
            "TAXSIM targets require the Populace person table"
        )
    _require_columns(
        raw_persons, {"person_id", "person_tax_unit_id"}, "person"
    )
    person_ids = [_clean_id(value) for value in raw_persons["person_id"]]
    _reject_duplicate_ids(person_ids, "person_id")
    person_tax_unit_ids = [
        _clean_id(value) for value in raw_persons["person_tax_unit_id"]
    ]
    unknown = sorted(set(person_tax_unit_ids) - set(tax_unit_ids), key=str)
    if unknown:
        raise StateTaxPopulationRoutingError(
            "TAXSIM targets: Populace people link to unknown tax_unit_id "
            "values: " + ", ".join(str(value) for value in unknown)
        )

    route_rows = tuple(routes)
    ready_by_state: dict[str, list[TaxUnitRoute]] = defaultdict(list)
    for route in route_rows:
        if route.disposition == DISPOSITION_READY and route.state is not None:
            ready_by_state[route.state].append(route)
    if not ready_by_state:
        return {}

    if microsimulation_factory is None:
        try:
            from policyengine_us import Microsimulation
        except ImportError as exc:  # pragma: no cover - optional runtime dependency
            raise RuntimeError(
                "Install the PolicyEngine extra to calculate TAXSIM targets."
            ) from exc

        def microsimulation_factory(source: Any) -> Any:
            return Microsimulation(dataset=source)

    sim = microsimulation_factory(dataset)

    # Person identity and tax-unit links must match the certified tables
    # before any modeled person value is attributed to a tax unit.
    modeled_person_ids = [
        _clean_id(value)
        for value in _array_values(sim.calculate("person_id", period=year))
    ]
    if modeled_person_ids != person_ids:
        raise StateTaxPopulationRoutingError(
            "TAXSIM targets: PolicyEngine Person identity/order does not "
            "match the certified Populace person table"
        )
    modeled_person_tax_unit_ids = [
        _clean_id(value)
        for value in _array_values(
            sim.calculate("tax_unit_id", period=year, map_to="person")
        )
    ]
    if modeled_person_tax_unit_ids != person_tax_unit_ids:
        raise StateTaxPopulationRoutingError(
            "TAXSIM targets: PolicyEngine Person-to-TaxUnit mapping does not "
            "match certified person_tax_unit_id"
        )

    def _person_array(variable: str) -> list[Any]:
        # Fail closed: a variable that cannot be calculated (renamed or
        # removed on a policyengine-us upgrade, missing dataset input) must
        # stop the leg, not silently zero an input for the whole population.
        try:
            values = _array_values(sim.calculate(variable, period=year))
        except Exception as exc:
            raise StateTaxPopulationRoutingError(
                f"TAXSIM targets: PolicyEngine could not calculate "
                f"{variable!r} for {year}: {exc}"
            ) from exc
        if len(values) != len(person_ids):
            raise StateTaxPopulationRoutingError(
                f"TAXSIM targets: PolicyEngine {variable!r} returned "
                f"{len(values)} rows for {len(person_ids)} people"
            )
        return values

    ages = _person_array("age")
    heads = _person_array("is_tax_unit_head")
    spouses = _person_array("is_tax_unit_spouse")
    wages = _person_array("employment_income")
    non_wage = {
        concept_key: _person_array(pe_variable)
        for concept_key, pe_variable in _TAXSIM_PERSON_NON_WAGE_VARIABLES.items()
    }

    # Concept keys are Concepts member names lowercased, so the module-level
    # variable table stays the single place a new income source is added.
    concept_by_key = {
        key: getattr(Concepts, key.upper())
        for key in _TAXSIM_PERSON_NON_WAGE_VARIABLES
    }

    person_indices_by_tax_unit: dict[int | str, list[int]] = defaultdict(list)
    for index, tax_unit_id in enumerate(person_tax_unit_ids):
        person_indices_by_tax_unit[tax_unit_id].append(index)

    def _case_for_tax_unit(tax_unit_id: int | str, state: str) -> Case:
        entities = []
        for index in person_indices_by_tax_unit[tax_unit_id]:
            if bool(heads[index]):
                relation = "head"
            elif bool(spouses[index]):
                relation = "spouse"
            else:
                relation = "dependent"
            facts: dict[str, Any] = {
                Concepts.PERSON_AGE: int(_finite_number(ages[index], label="age")),
                Concepts.HOUSEHOLD_RELATION: relation,
                Concepts.YEARLY_EARNED_INCOME: _finite_number(
                    wages[index], label="employment_income"
                ),
            }
            # Non-wage income is attached to every member, but the shared
            # projection (taxsim_input_for_case) sums these columns over
            # head+spouse only — TAXSIM-35 has no dependent-income input.
            # A dependent's unearned income therefore reaches the PE/Axiom
            # tax-unit value but not the TAXSIM row: a known one-sided
            # projection gap shared with the ECPS lanes (see
            # docs/taxsim-oracle-playbook.md), not an oracle disagreement.
            for key, concept in concept_by_key.items():
                facts[concept] = _finite_number(
                    non_wage[key][index],
                    label=_TAXSIM_PERSON_NON_WAGE_VARIABLES[key],
                )
            entities.append(
                Entity(
                    entity_id=str(person_ids[index]),
                    kind="person",
                    facts=facts,
                )
            )
        return Case(
            case_id=tax_unit_id,
            period=str(year),
            entities=tuple(entities),
            # The projection converts USPS -> TAXSIM/SOI codes itself;
            # passing the code through metadata keeps that conversion in
            # one place (docs/policyengine-taxsim.md: FIPS != SOI).
            metadata={"state": state},
        )

    if taxsim_runner_factory is None:
        from policyengine_taxsim.runners.taxsim_runner import TaxsimRunner

        from ..adapters.taxsim.pins import installed_binary_path

        binary = installed_binary_path()

        def taxsim_runner_factory(frame: Any) -> Any:
            if binary is not None:
                return TaxsimRunner(frame, taxsim_path=binary)
            return TaxsimRunner(frame)

    import pandas as pd

    targets: dict[str, dict[int | str, float]] = {}
    for state in sorted(ready_by_state):
        jurisdiction = resolved_contract.by_state()[state]
        column = taxsim_target_column(jurisdiction.output)
        if column is None:
            # No declared TAXSIM surface for this jurisdiction's concept —
            # skip rather than guess. compare_ready_state_tax_units reports
            # the absent leg in taxsim_skipped_states.
            continue
        state_routes = ready_by_state[state]
        rows = []
        for route in state_routes:
            row = taxsim_input_for_case(
                _case_for_tax_unit(route.tax_unit_id, state),
                taxsimid=route.tax_unit_id,
            )
            if row["state"] != jurisdiction.taxsim_state_code:
                raise StateTaxPopulationRoutingError(
                    f"{state}: projected TAXSIM state code {row['state']} "
                    "does not match the contract's "
                    f"{jurisdiction.taxsim_state_code}"
                )
            rows.append(row)
        runner = taxsim_runner_factory(pd.DataFrame(rows))
        try:
            result = runner.run(show_progress=False)
        except TypeError:
            result = runner.run()
        records = result.to_dict(orient="records")
        if len(records) != len(state_routes):
            raise StateTaxPopulationRoutingError(
                f"{state}: TAXSIM returned {len(records)} rows for "
                f"{len(state_routes)} selected tax units"
            )
        state_targets: dict[int | str, float] = {}
        for route, record in zip(state_routes, records, strict=True):
            # Identity over order: the binary is expected to preserve row
            # order, but a reordered or dropped row must fail loudly, not
            # attribute one unit's tax to another. A result frame without
            # the taxsimid echo column would degrade every row to positional
            # trust, so its absence is itself a loud failure.
            if "taxsimid" not in record:
                raise StateTaxPopulationRoutingError(
                    f"{state}: TAXSIM output omitted the 'taxsimid' identity "
                    "column; refusing to attribute rows by position"
                )
            returned_id = record["taxsimid"]
            if _clean_id(returned_id) != _clean_id(route.tax_unit_id):
                raise StateTaxPopulationRoutingError(
                    f"{state}: TAXSIM row identity mismatch — expected "
                    f"taxsimid {route.tax_unit_id}, got {returned_id}"
                )
            if column not in record:
                raise StateTaxPopulationRoutingError(
                    f"{state}: TAXSIM output omitted {column!r}"
                )
            state_targets[route.tax_unit_id] = _finite_number(
                record[column], label=column
            )
        targets[state] = state_targets
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
        if state == "IN":
            _validate_indiana_runtime_contract(jurisdiction)
            _validate_indiana_policyengine_runtime(sim=sim, year=year)
        if state == "PA":
            _validate_pennsylvania_runtime_contract(jurisdiction)
            _validate_pennsylvania_policyengine_runtime(sim=sim, year=year)
        if state == "SC":
            _validate_south_carolina_runtime_contract(jurisdiction)
            _validate_south_carolina_policyengine_runtime(sim=sim, year=year)
        if state == "IL":
            _validate_illinois_runtime_contract(jurisdiction)
            for variable in IL_REVIEWED_INPUTS.values():
                _require_policyengine_tax_unit_year_money_variable(
                    sim,
                    state="IL",
                    variable=variable,
                )
        if state in {"IL", "IN", "NY", "PA", "SC"}:
            modeled_ids = [
                _clean_id(value)
                for value in _array_values(
                    sim.calculate("tax_unit_id", period=year)
                )
            ]
            if len(modeled_ids) != len(tax_unit_ids):
                raise StateTaxPopulationRoutingError(
                    f"{state}: PolicyEngine projection identity returned "
                    f"{len(modeled_ids)} IDs for {len(tax_unit_ids)} tax units"
                )
            _reject_duplicate_ids(
                modeled_ids,
                f"{state} PolicyEngine projection tax_unit_id",
            )
            if modeled_ids != tax_unit_ids:
                raise StateTaxPopulationRoutingError(
                    f"{state}: PolicyEngine projection tax_unit_id order does not "
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
                if (
                    state == "IL"
                    and variable in IL_REVIEWED_INPUTS.values()
                    and any(value < 0 for value in projected)
                ):
                    raise StateTaxPopulationRoutingError(
                        f"IL: reviewed boundary {variable!r} must be nonnegative"
                    )
                if (
                    state == "PA"
                    and variable == PA_ADJUSTED_TAXABLE_INCOME
                ):
                    selected_ids = {
                        route.tax_unit_id
                        for route in route_rows
                        if route.state == "PA"
                        and route.disposition == DISPOSITION_READY
                    }
                    selected_values = [
                        value
                        for tax_unit_id, value in zip(
                            tax_unit_ids,
                            projected,
                            strict=True,
                        )
                        if tax_unit_id in selected_ids
                    ]
                    if not selected_values:
                        raise StateTaxPopulationRoutingError(
                            "PA: projection requires selected tax units"
                        )
                    if any(value < 0 for value in selected_values):
                        raise StateTaxPopulationRoutingError(
                            "PA: every selected pa_adjusted_taxable_income "
                            "boundary must be nonnegative"
                        )
                if state == "SC" and variable == SC_TAXABLE_INCOME:
                    selected_ids = {
                        route.tax_unit_id
                        for route in route_rows
                        if route.state == "SC"
                        and route.disposition == DISPOSITION_READY
                    }
                    selected_values = [
                        value
                        for tax_unit_id, value in zip(
                            tax_unit_ids,
                            projected,
                            strict=True,
                        )
                        if tax_unit_id in selected_ids
                    ]
                    if not selected_values:
                        raise StateTaxPopulationRoutingError(
                            "SC: projection requires selected tax units"
                        )
                    if any(value < 0 for value in selected_values):
                        raise StateTaxPopulationRoutingError(
                            "SC: every selected sc_taxable_income boundary "
                            "must be nonnegative"
                        )
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
    taxsim_targets: Mapping[str, Mapping[int | str, float]] | None = None,
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

    ``taxsim_targets`` (from :func:`calculate_taxsim_targets`) adds the
    second oracle leg: states present in the mapping grade every selected
    tax unit against TAXSIM too, and a selected unit missing from its
    state's mapping fails closed. States absent from the mapping keep the
    PolicyEngine-only shape so partial TAXSIM rollout never silently drops
    a leg that was expected.
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
    all_taxsim_mismatches: list[dict[str, Any]] = []
    taxsim_state_count = 0
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

        state_taxsim_targets = (
            taxsim_targets.get(state) if taxsim_targets is not None else None
        )
        mismatches: list[dict[str, Any]] = []
        taxsim_mismatches: list[dict[str, Any]] = []
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
            case_row = {
                "tax_unit_id": route.tax_unit_id,
                "weight": route.weight,
                "axiom": round(axiom_value, 2),
                "policyengine": round(pe_value, 2),
                "matched": matched,
            }
            if state_taxsim_targets is not None:
                # A state carrying the TAXSIM leg fails closed on a missing
                # unit: a silently absent oracle value would read as a
                # narrower comparison, not as the defect it is.
                if route.tax_unit_id not in state_taxsim_targets:
                    raise StateTaxPopulationRoutingError(
                        f"{state}: TAXSIM target omitted tax_unit_id "
                        f"{route.tax_unit_id}"
                    )
                taxsim_value = _finite_number(
                    state_taxsim_targets[route.tax_unit_id],
                    label="taxsim",
                )
                taxsim_abs_diff = abs(axiom_value - taxsim_value)
                taxsim_relative_diff = taxsim_abs_diff / max(
                    abs(taxsim_value), 1.0
                )
                taxsim_matched = (
                    taxsim_abs_diff <= jurisdiction.tolerance
                    or taxsim_relative_diff <= jurisdiction.relative_tolerance
                )
                if not taxsim_matched:
                    taxsim_mismatches.append(
                        {
                            "state": state,
                            "tax_unit_id": route.tax_unit_id,
                            "weight": route.weight,
                            "axiom": axiom_value,
                            "taxsim": taxsim_value,
                            "absolute_difference": taxsim_abs_diff,
                            "relative_difference": taxsim_relative_diff,
                        }
                    )
                case_row["taxsim"] = round(taxsim_value, 2)
                case_row["taxsim_matched"] = taxsim_matched
            case_rows.append(case_row)

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
        if state_taxsim_targets is not None:
            comparisons[state]["taxsim_target"] = taxsim_target_column(
                jurisdiction.output
            )
            comparisons[state]["taxsim_mismatch_count"] = len(taxsim_mismatches)
            comparisons[state]["taxsim_mismatches"] = taxsim_mismatches
            all_taxsim_mismatches.extend(taxsim_mismatches)
            taxsim_state_count += 1

    report = {
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
    if taxsim_targets is not None:
        report["taxsim_state_count"] = taxsim_state_count
        report["taxsim_mismatch_count"] = len(all_taxsim_mismatches)
        report["taxsim_mismatches"] = all_taxsim_mismatches
        # States compared without a TAXSIM leg (no declared truthful
        # surface for their output concept) — visible, not silent. Only a
        # state whose concept mapping genuinely resolves no TAXSIM column
        # may be skipped: a mapped state absent from the targets means the
        # leg was lost (a producer regression or a stale/filtered mapping),
        # which must fail loudly rather than masquerade as an intended skip.
        skipped_states = sorted(
            state for state in comparisons if state not in taxsim_targets
        )
        by_state = resolved_contract.by_state()
        lost_states = [
            state
            for state in skipped_states
            if taxsim_target_column(by_state[state].output) is not None
        ]
        if lost_states:
            raise StateTaxPopulationRoutingError(
                "TAXSIM targets missing for states whose output concept "
                "declares a TAXSIM surface: " + ", ".join(lost_states)
            )
        report["taxsim_skipped_states"] = skipped_states
    return report


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


def _validate_illinois_runtime_contract(jurisdiction: Any) -> None:
    """Fail closed if the bounded Illinois annual-before-credit contract drifts."""

    if (
        jurisdiction.policyengine_target
        != IL_INCOME_TAX_BEFORE_NONREFUNDABLE_CREDITS_TARGET
    ):
        raise StateTaxPopulationRoutingError(
            "IL: reviewed annual-before-credit runner requires the exact "
            "il_income_tax_before_non_refundable_credits target"
        )
    if (
        jurisdiction.program != IL_ANNUAL_BEFORE_CREDIT_PROGRAM
        or jurisdiction.output != IL_ANNUAL_BEFORE_CREDIT_OUTPUT
    ):
        raise StateTaxPopulationRoutingError(
            "IL: reviewed annual-before-credit runner requires the exact "
            "canonical RuleSpec program and output"
        )
    actual_inputs = {
        slot.slot: (
            slot.policyengine_variable,
            slot.source_kind,
            slot.policyengine_relationship,
        )
        for slot in jurisdiction.inputs
    }
    expected_inputs = {
        slot: (variable, "pe_upstream_boundary", "upstream")
        for slot, variable in IL_REVIEWED_INPUTS.items()
    }
    if actual_inputs != expected_inputs or jurisdiction.relations:
        raise StateTaxPopulationRoutingError(
            "IL: reviewed annual-before-credit runner requires exactly the "
            "completed taxable-income and investment-credit-recapture "
            "upstream boundaries and no relations"
        )


def _validate_indiana_runtime_contract(jurisdiction: Any) -> None:
    """Fail closed if the canonical Indiana AGI-tax contract drifts."""

    if jurisdiction.policyengine_target != IN_AGI_TAX_TARGET:
        raise StateTaxPopulationRoutingError(
            "IN: reviewed AGI-tax runner requires the exact in_agi_tax target"
        )
    if (
        jurisdiction.program != IN_AGI_TAX_PROGRAM
        or jurisdiction.output != IN_AGI_TAX_OUTPUT
    ):
        raise StateTaxPopulationRoutingError(
            "IN: reviewed AGI-tax runner requires the exact canonical "
            "RuleSpec program and output"
        )
    actual_inputs = {
        slot.slot: (
            slot.source_kind,
            slot.status,
            slot.policyengine_variable,
            slot.policyengine_variables,
            slot.policyengine_relationship,
            slot.policyengine_transform,
            slot.constant_value,
        )
        for slot in jurisdiction.inputs
    }
    expected_inputs = {
        IN_AGI_TAX_INPUT: (
            "pe_upstream_boundary",
            "ready",
            IN_AGI_TAX_UPSTREAM,
            (),
            "upstream",
            None,
            None,
        )
    }
    if actual_inputs != expected_inputs or jurisdiction.relations:
        raise StateTaxPopulationRoutingError(
            "IN: reviewed AGI-tax runner requires exactly the completed "
            "Indiana adjusted-gross-income upstream boundary and no relations"
        )


def _validate_indiana_policyengine_runtime(*, sim: Any, year: int) -> None:
    """Prove the active PolicyEngine target retains its reviewed 2026 shape."""

    for variable in (IN_AGI_TAX_TARGET, IN_AGI_TAX_UPSTREAM):
        _require_policyengine_tax_unit_year_money_variable(
            sim,
            state="IN",
            variable=variable,
        )
    try:
        target_definition = sim.tax_benefit_system.variables[
            IN_AGI_TAX_TARGET
        ]
        upstream_definition = sim.tax_benefit_system.variables[
            IN_AGI_TAX_UPSTREAM
        ]
        formula = target_definition.get_formula(year)
        rate_value = (
            sim.tax_benefit_system.parameters(year)
            .gov.states["in"].tax.income.agi_rate
        )
    except (AttributeError, KeyError, TypeError) as exc:
        raise StateTaxPopulationRoutingError(
            "IN: active 2026 in_agi_tax formula, dependency, or rate schema "
            "drifted"
        ) from exc
    if formula is None or getattr(upstream_definition, "formulas", None):
        raise StateTaxPopulationRoutingError(
            "IN: active 2026 in_agi_tax formula must depend on the reviewed "
            "formula-free in_agi upstream boundary"
        )
    rate = _finite_number(
        rate_value,
        label="gov.states.in.tax.income.agi_rate",
    )
    if rate != IN_AGI_TAX_2026_RATE:
        raise StateTaxPopulationRoutingError(
            "IN: active 2026 Indiana AGI-tax rate must be exactly 0.0295; "
            f"got {rate!r}"
        )

    class FormulaParameters:
        def __init__(self) -> None:
            self.accesses: list[str] = []
            self.calls: list[int] = []

        def __call__(self, period: int) -> FormulaParameters:
            self.calls.append(period)
            return self

        @property
        def gov(self) -> FormulaParameters:
            self.accesses.append("gov")
            return self

        @property
        def states(self) -> FormulaParameters:
            self.accesses.append("states")
            return self

        def __getitem__(self, key: str) -> FormulaParameters:
            self.accesses.append(f"states[{key}]")
            if key != "in":
                raise KeyError(key)
            return self

        @property
        def tax(self) -> FormulaParameters:
            self.accesses.append("tax")
            return self

        @property
        def income(self) -> FormulaParameters:
            self.accesses.append("income")
            return self

        @property
        def agi_rate(self) -> float:
            self.accesses.append("agi_rate")
            return rate

    for agi, expected in (
        (-100.0, 0.0),
        (100.0, 100.0 * IN_AGI_TAX_2026_RATE),
    ):
        tax_unit_calls: list[tuple[str, int]] = []

        def tax_unit(variable: str, period: int) -> float:
            tax_unit_calls.append((variable, period))
            if variable != IN_AGI_TAX_UPSTREAM:
                raise KeyError(variable)
            return agi

        parameters = FormulaParameters()
        try:
            result = _finite_number(
                formula(tax_unit, year, parameters),
                label="IN active in_agi_tax formula probe",
            )
        except (AttributeError, KeyError, TypeError) as exc:
            raise StateTaxPopulationRoutingError(
                "IN: active 2026 in_agi_tax formula dependency path drifted"
            ) from exc
        if (
            result != expected
            or tax_unit_calls != [(IN_AGI_TAX_UPSTREAM, year)]
            or parameters.calls != [year]
            or parameters.accesses
            != [
                "gov",
                "states",
                "states[in]",
                "tax",
                "income",
                "agi_rate",
            ]
        ):
            raise StateTaxPopulationRoutingError(
                "IN: active 2026 in_agi_tax formula must read exactly in_agi "
                "and gov.states.in.tax.income.agi_rate and apply the "
                "nonnegative floor"
            )


def _validate_pennsylvania_runtime_contract(jurisdiction: Any) -> None:
    """Fail closed if the canonical Pennsylvania PIT contract drifts."""

    if jurisdiction.policyengine_target != PA_BEFORE_FORGIVENESS_TARGET:
        raise StateTaxPopulationRoutingError(
            "PA: reviewed before-forgiveness runner requires the exact "
            "pa_income_tax_before_forgiveness target"
        )
    if (
        jurisdiction.program != PA_BEFORE_FORGIVENESS_PROGRAM
        or jurisdiction.output != PA_BEFORE_FORGIVENESS_OUTPUT
    ):
        raise StateTaxPopulationRoutingError(
            "PA: reviewed before-forgiveness runner requires the exact "
            "canonical RuleSpec program and output"
        )
    actual_inputs = {
        slot.slot: (
            slot.source_kind,
            slot.status,
            slot.policyengine_variable,
            slot.policyengine_variables,
            slot.policyengine_relationship,
            slot.policyengine_transform,
            slot.constant_value,
        )
        for slot in jurisdiction.inputs
    }
    expected_inputs = {
        PA_BEFORE_FORGIVENESS_INPUT: (
            "pe_upstream_boundary",
            "ready",
            PA_ADJUSTED_TAXABLE_INCOME,
            (),
            "upstream",
            None,
            None,
        )
    }
    if actual_inputs != expected_inputs or jurisdiction.relations:
        raise StateTaxPopulationRoutingError(
            "PA: reviewed before-forgiveness runner requires exactly the "
            "completed Pennsylvania adjusted-taxable-income upstream boundary "
            "and no relations"
        )


def _validate_pennsylvania_policyengine_runtime(*, sim: Any, year: int) -> None:
    """Prove the active PolicyEngine target retains its reviewed 2026 shape."""

    for variable in (
        PA_BEFORE_FORGIVENESS_TARGET,
        PA_ADJUSTED_TAXABLE_INCOME,
    ):
        _require_policyengine_tax_unit_year_money_variable(
            sim,
            state="PA",
            variable=variable,
        )
    try:
        target_definition = sim.tax_benefit_system.variables[
            PA_BEFORE_FORGIVENESS_TARGET
        ]
        formula = target_definition.get_formula(year)
        rate_value = (
            sim.tax_benefit_system.parameters(year)
            .gov.states.pa.tax.income.rate
        )
    except (AttributeError, KeyError, TypeError) as exc:
        raise StateTaxPopulationRoutingError(
            "PA: active 2026 before-forgiveness formula, dependency, or rate "
            "schema drifted"
        ) from exc
    if formula is None:
        raise StateTaxPopulationRoutingError(
            "PA: active 2026 pa_income_tax_before_forgiveness formula is "
            "unavailable"
        )
    rate = _finite_number(
        rate_value,
        label="gov.states.pa.tax.income.rate",
    )
    if rate != PA_2026_RATE:
        raise StateTaxPopulationRoutingError(
            "PA: active 2026 Pennsylvania income-tax rate must be exactly "
            f"0.0307; got {rate!r}"
        )

    class FormulaParameters:
        def __init__(self) -> None:
            self.accesses: list[str] = []
            self.calls: list[int] = []

        def __call__(self, period: int) -> FormulaParameters:
            self.calls.append(period)
            return self

        @property
        def gov(self) -> FormulaParameters:
            self.accesses.append("gov")
            return self

        @property
        def states(self) -> FormulaParameters:
            self.accesses.append("states")
            return self

        @property
        def pa(self) -> FormulaParameters:
            self.accesses.append("pa")
            return self

        @property
        def tax(self) -> FormulaParameters:
            self.accesses.append("tax")
            return self

        @property
        def income(self) -> FormulaParameters:
            self.accesses.append("income")
            return self

        @property
        def rate(self) -> float:
            self.accesses.append("rate")
            return rate

    for taxable_income in (-100.0, 0.0, 100.0):
        tax_unit_calls: list[tuple[str, int]] = []

        def tax_unit(variable: str, period: int) -> float:
            tax_unit_calls.append((variable, period))
            if variable != PA_ADJUSTED_TAXABLE_INCOME:
                raise KeyError(variable)
            return taxable_income

        parameters = FormulaParameters()
        try:
            result = _finite_number(
                formula(tax_unit, year, parameters),
                label="PA active before-forgiveness formula probe",
            )
        except (AttributeError, KeyError, TypeError) as exc:
            raise StateTaxPopulationRoutingError(
                "PA: active 2026 before-forgiveness formula dependency path "
                "drifted"
            ) from exc
        expected = taxable_income * PA_2026_RATE
        if (
            result != expected
            or tax_unit_calls != [(PA_ADJUSTED_TAXABLE_INCOME, year)]
            or parameters.calls != [year]
            or parameters.accesses
            != [
                "gov",
                "states",
                "pa",
                "tax",
                "income",
                "rate",
            ]
        ):
            raise StateTaxPopulationRoutingError(
                "PA: active 2026 before-forgiveness formula must read exactly "
                "pa_adjusted_taxable_income and "
                "gov.states.pa.tax.income.rate"
            )


def _validate_south_carolina_runtime_contract(jurisdiction: Any) -> None:
    """Fail closed if the canonical South Carolina PIT contract drifts."""

    if (
        jurisdiction.policyengine_target
        != SC_BEFORE_NONREFUNDABLE_CREDITS_TARGET
    ):
        raise StateTaxPopulationRoutingError(
            "SC: reviewed runner requires the exact "
            "sc_income_tax_before_non_refundable_credits target"
        )
    if (
        jurisdiction.program != SC_BEFORE_NONREFUNDABLE_CREDITS_PROGRAM
        or jurisdiction.output != SC_BEFORE_NONREFUNDABLE_CREDITS_OUTPUT
    ):
        raise StateTaxPopulationRoutingError(
            "SC: reviewed runner requires the exact canonical RuleSpec "
            "program and before-nonrefundable-credits output"
        )
    actual_inputs = {
        slot.slot: (
            slot.source_kind,
            slot.status,
            slot.policyengine_variable,
            slot.policyengine_variables,
            slot.policyengine_relationship,
            slot.policyengine_transform,
            slot.constant_value,
        )
        for slot in jurisdiction.inputs
    }
    expected_inputs = {
        SC_BEFORE_NONREFUNDABLE_CREDITS_INPUT: (
            "pe_upstream_boundary",
            "ready",
            SC_TAXABLE_INCOME,
            (),
            "upstream",
            None,
            None,
        )
    }
    if actual_inputs != expected_inputs or jurisdiction.relations:
        raise StateTaxPopulationRoutingError(
            "SC: reviewed runner requires exactly the completed South "
            "Carolina taxable-income upstream boundary and no relations"
        )


def _south_carolina_2026_schedule(taxable_income: float) -> float:
    if taxable_income < 30_000:
        return taxable_income * 0.0199
    return taxable_income * 0.0521 - 966


# Sub-cent probe tolerance: the schedule arrives through PE-core's tax scale
# in float arithmetic; exact != rejected 597.0520999999999 against 597.0521
# (2026-08-24). Deliberately stricter than SC's graded tolerance — the probe
# checks the schedule's shape, not a household comparison.
_SC_SCHEDULE_PROBE_TOLERANCE = 0.005


def _validate_south_carolina_policyengine_runtime(
    *,
    sim: Any,
    year: int,
) -> None:
    """Prove the active PolicyEngine target retains its reviewed 2026 shape."""

    if year != 2026:
        raise StateTaxPopulationRoutingError(
            "SC: reviewed before-nonrefundable-credits schedule is 2026 only"
        )
    for variable in (
        SC_BEFORE_NONREFUNDABLE_CREDITS_TARGET,
        SC_TAXABLE_INCOME,
    ):
        _require_policyengine_tax_unit_year_money_variable(
            sim,
            state="SC",
            variable=variable,
        )
    try:
        target_definition = sim.tax_benefit_system.variables[
            SC_BEFORE_NONREFUNDABLE_CREDITS_TARGET
        ]
        formula = target_definition.get_formula(year)
        rates = (
            sim.tax_benefit_system.parameters(year)
            .gov.states.sc.tax.income.rates
        )
    except (AttributeError, KeyError, TypeError) as exc:
        raise StateTaxPopulationRoutingError(
            "SC: active 2026 formula, dependency, or rates schema drifted"
        ) from exc
    if formula is None or not callable(getattr(rates, "calc", None)):
        raise StateTaxPopulationRoutingError(
            "SC: active 2026 formula and marginal-rate schedule are required"
        )

    # PolicyEngine-core's MarginalRateTaxScale.calc takes an array, not
    # a scalar (len(tax_base) inside); a scalar probe crashes every
    # campaign run since this validator landed (2026-08-24).
    import numpy

    probes = (0.0, 1.0, 29_999.0, 30_000.0, 30_001.0, 100_000.0)
    for taxable_income in probes:
        (calc_value,) = rates.calc(numpy.array([taxable_income]))
        actual = _finite_number(
            calc_value,
            label="gov.states.sc.tax.income.rates",
        )
        expected = _south_carolina_2026_schedule(taxable_income)
        if abs(actual - expected) > _SC_SCHEDULE_PROBE_TOLERANCE:
            raise StateTaxPopulationRoutingError(
                "SC: active 2026 marginal-rate schedule must retain the "
                "reviewed 1.99% / 5.21%-minus-$966 boundary; "
                f"at {taxable_income!r}, got {actual!r}"
            )

    class FormulaRates:
        def __init__(self) -> None:
            self.calls: list[float] = []

        def calc(self, taxable_income: float) -> float:
            self.calls.append(taxable_income)
            return _south_carolina_2026_schedule(taxable_income)

    class FormulaParameters:
        def __init__(self) -> None:
            self.accesses: list[str] = []
            self.calls: list[int] = []
            self.reviewed_rates = FormulaRates()

        def __call__(self, period: int) -> FormulaParameters:
            self.calls.append(period)
            return self

        @property
        def gov(self) -> FormulaParameters:
            self.accesses.append("gov")
            return self

        @property
        def states(self) -> FormulaParameters:
            self.accesses.append("states")
            return self

        @property
        def sc(self) -> FormulaParameters:
            self.accesses.append("sc")
            return self

        @property
        def tax(self) -> FormulaParameters:
            self.accesses.append("tax")
            return self

        @property
        def income(self) -> FormulaParameters:
            self.accesses.append("income")
            return self

        @property
        def rates(self) -> FormulaRates:
            self.accesses.append("rates")
            return self.reviewed_rates

    for taxable_income in probes:
        tax_unit_calls: list[tuple[str, int]] = []

        def tax_unit(variable: str, period: int) -> float:
            tax_unit_calls.append((variable, period))
            if variable != SC_TAXABLE_INCOME:
                raise KeyError(variable)
            return taxable_income

        parameters = FormulaParameters()
        try:
            result = _finite_number(
                formula(tax_unit, year, parameters),
                label="SC active before-nonrefundable-credits formula probe",
            )
        except (AttributeError, KeyError, TypeError) as exc:
            raise StateTaxPopulationRoutingError(
                "SC: active 2026 formula dependency path drifted"
            ) from exc
        expected = _south_carolina_2026_schedule(taxable_income)
        if (
            result != expected
            or tax_unit_calls != [(SC_TAXABLE_INCOME, year)]
            or parameters.calls != [year]
            or parameters.accesses
            != ["gov", "states", "sc", "tax", "income", "rates"]
            or parameters.reviewed_rates.calls != [taxable_income]
        ):
            raise StateTaxPopulationRoutingError(
                "SC: active 2026 formula must read exactly sc_taxable_income "
                "and gov.states.sc.tax.income.rates.calc"
            )


def _require_policyengine_tax_unit_year_money_variable(
    sim: Any,
    *,
    state: str,
    variable: str,
) -> None:
    """Require the reviewed PolicyEngine variable's exact accounting schema."""

    try:
        definition = sim.tax_benefit_system.variables[variable]
    except (AttributeError, KeyError, TypeError) as exc:
        raise StateTaxPopulationRoutingError(
            f"{state}: PolicyEngine variable {variable!r} is missing reviewed "
            "schema metadata"
        ) from exc
    entity = getattr(getattr(definition, "entity", None), "key", None)
    period = str(getattr(definition, "definition_period", "")).lower()
    value_type = getattr(definition, "value_type", None)
    unit = getattr(definition, "unit", None)
    if (
        entity != "tax_unit"
        or period != "year"
        or value_type is not float
        or unit != "currency-USD"
    ):
        value_type_name = getattr(value_type, "__name__", repr(value_type))
        raise StateTaxPopulationRoutingError(
            f"{state}: PolicyEngine variable {variable!r} must use the reviewed "
            "TaxUnit/year/currency-USD float schema; got "
            f"entity={entity!r}, period={period!r}, "
            f"value_type={value_type_name!r}, unit={unit!r}"
        )


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
