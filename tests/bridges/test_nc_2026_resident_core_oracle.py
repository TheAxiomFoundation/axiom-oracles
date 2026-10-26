"""NC TY2026 resident-core Populace projection: contract, runtime pins, transforms."""

from __future__ import annotations

from dataclasses import replace
import math
from types import SimpleNamespace

from hypothesis import given, settings, strategies as st
import pandas as pd
import pytest
import yaml

from axiom_oracles.bridges.registry import load_policyengine_registry
from axiom_oracles.bridges.state_tax_populace import (
    ALLOWED_DERIVED_PE_BOUNDARIES,
    ALLOWED_MULTI_SOURCE_DERIVED_PE_BOUNDARIES,
    ALLOWED_PE_UPSTREAM_BOUNDARIES,
    ALLOWED_PROJECTION_CONSTANTS,
    STATE_TAX_POPULACE_CONTRACT_PATH,
    StateTaxPopulaceContractError,
    load_state_tax_populace_contract,
    validate_state_tax_populace_contract,
)
from axiom_oracles.bridges.state_tax_populace_runner import (
    DISPOSITION_READY,
    NC_REVIEWED_POLICYENGINE_DEDUCTIONS,
    StateTaxPopulationRoutingError,
    TaxUnitRoute,
    _apply_projection_transform,
    _validate_north_carolina_policyengine_runtime,
    _validate_north_carolina_runtime_contract,
    calculate_policyengine_projection_inputs,
)


MODULE = "us-nc:policies/income_tax/resident_core_liability_pipeline"
OUTPUT = f"{MODULE}#nc_pit_2026_income_tax_before_credits"
PREFIX = f"{MODULE}#input."

# The resident-core module's input inventory, in its declared order.
MODULE_INPUTS = (
    "nc_pit_2026_federal_adjusted_gross_income",
    "nc_pit_2026_filing_status_joint_or_surviving_spouse",
    "nc_pit_2026_filing_status_head_of_household",
    "nc_pit_2026_filing_status_married_separately",
    "nc_pit_2026_eligible_for_federal_standard_deduction",
    "nc_pit_2026_charitable_contributions",
    "nc_pit_2026_section_170_deduction_attributable_to_credit_backed_donation",
    "nc_pit_2026_qualified_residence_interest",
    "nc_pit_2026_real_estate_property_taxes",
    "nc_pit_2026_mfs_combined_mortgage_interest_and_property_taxes",
    "nc_pit_2026_mfs_cap_allocation_share",
    "nc_pit_2026_medical_and_dental_expenses",
    "nc_pit_2026_claim_of_right_repayment_deduction",
    "nc_pit_2026_wagering_loss_deduction_not_in_federal_agi",
    "nc_pit_2026_federal_child_tax_credit_qualifying_children",
    "nc_pit_2026_other_state_obligation_interest",
    "nc_pit_2026_s_corporation_built_in_gains_reduction",
    "nc_pit_2026_federal_basis_excess",
    "nc_pit_2026_accelerated_depreciation_and_expensing_addback",
    "nc_pit_2026_federal_net_operating_loss_deduction",
    "nc_pit_2026_nonqualified_education_withdrawal",
    "nc_pit_2026_opportunity_fund_deferred_gain",
    "nc_pit_2026_opportunity_fund_step_up_gain",
    "nc_pit_2026_exempt_income_allocated_expenses",
    "nc_pit_2026_excess_federal_nol_carryforward_deduction",
    "nc_pit_2026_taxed_pass_through_loss_addition",
    "nc_pit_2026_eligible_obligation_interest",
    "nc_pit_2026_exempt_obligation_gain",
    "nc_pit_2026_taxable_social_security_and_railroad_retirement",
    "nc_pit_2026_income_tax_refunds",
    "nc_pit_2026_bailey_retirement_benefits",
    "nc_pit_2026_eligible_uniformed_services_retirement",
    "nc_pit_2026_eligible_tribal_income",
    "nc_pit_2026_north_carolina_basis_excess",
    "nc_pit_2026_accelerated_depreciation_recovery",
    "nc_pit_2026_federal_credit_disallowed_business_expense",
    "nc_pit_2026_employee_retention_credit_disallowed_expense",
    "nc_pit_2026_personal_education_student_account_deposit",
    "nc_pit_2026_disaster_relief_payment",
    "nc_pit_2026_economic_incentive_and_recovery_grants",
    "nc_pit_2026_state_net_operating_loss",
    "nc_pit_2026_previously_taxed_opportunity_fund_gain",
    "nc_pit_2026_taxed_pass_through_income_deduction",
)

# PolicyEngine values that already embed North Carolina's own deduction,
# taxable-income, or tax arithmetic.  None may enter the resident core.
COMPLETED_NC_BOUNDARIES = frozenset(
    {
        "nc_income_tax",
        "nc_income_tax_before_credits",
        "nc_taxable_income",
        "nc_deductions",
        "nc_standard_or_itemized_deductions",
        "nc_itemized_deductions",
        "nc_standard_deduction",
        "nc_child_deduction",
        "mortgage_interest",
    }
)


def _nc():
    return load_state_tax_populace_contract().by_state()["NC"]


def _sources(slot) -> tuple[str, ...]:
    return slot.policyengine_variables or (
        (slot.policyengine_variable,) if slot.policyengine_variable else ()
    )


def test_nc_row_compares_resident_core_against_the_pilot_target_and_tolerance() -> None:
    nc = _nc()

    assert nc.program == MODULE
    assert nc.output == OUTPUT
    assert nc.policyengine_target == "nc_income_tax_before_credits"
    assert (nc.tolerance, nc.relative_tolerance) == (1.0, 0.0)
    assert nc.comparison_aggregation == "tax_unit"
    assert nc.status == "ready"
    assert nc.relations == ()
    assert [slot.slot for slot in nc.inputs] == [
        f"{PREFIX}{name}" for name in MODULE_INPUTS
    ]


def test_nc_row_supplies_only_leaf_inputs_never_a_completed_nc_boundary() -> None:
    nc = _nc()
    kinds = [slot.source_kind for slot in nc.inputs]

    assert kinds.count("pe_upstream_boundary") == 6
    assert kinds.count("derived") == 8
    assert kinds.count("projection_constant") == 29
    used = {variable for slot in nc.inputs for variable in _sources(slot)}
    assert used.isdisjoint(COMPLETED_NC_BOUNDARIES)
    assert used == {
        "adjusted_gross_income",
        "filing_status",
        "separate_filer_itemizes",
        "charitable_deduction",
        "deductible_mortgage_interest",
        "real_estate_taxes",
        "medical_expense_deduction",
        "ctc_qualifying_children",
        "us_govt_interest",
        "taxable_social_security",
        "nc_military_retirement_deduction",
    }
    agi = nc.inputs[0]
    assert (agi.source_kind, agi.policyengine_variable) == (
        "pe_upstream_boundary",
        "adjusted_gross_income",
    )


def test_nc_projection_constants_are_the_reviewed_zero_and_share_values() -> None:
    constants = {
        slot.slot.removeprefix(PREFIX): slot.constant_value
        for slot in _nc().inputs
        if slot.source_kind == "projection_constant"
    }

    assert constants.pop("nc_pit_2026_mfs_cap_allocation_share") == 1.0
    assert set(constants.values()) == {0.0}
    assert len(constants) == 28


def test_nc_slots_partition_exactly_across_the_reviewed_allowlists() -> None:
    by_allowlist = [
        {slot for state, slot, *_ in allowlist if state == "NC"}
        for allowlist in (
            ALLOWED_PE_UPSTREAM_BOUNDARIES,
            ALLOWED_DERIVED_PE_BOUNDARIES,
            ALLOWED_MULTI_SOURCE_DERIVED_PE_BOUNDARIES,
            ALLOWED_PROJECTION_CONSTANTS,
        )
    ]

    assert sum(len(item) for item in by_allowlist) == len(MODULE_INPUTS)
    assert set().union(*by_allowlist) == {
        f"{PREFIX}{name}" for name in MODULE_INPUTS
    }


def _document() -> dict:
    return yaml.safe_load(STATE_TAX_POPULACE_CONTRACT_PATH.read_text())


def _nc_slot(document: dict, name: str) -> dict:
    nc = next(item for item in document["jurisdictions"] if item["state"] == "NC")
    return next(item for item in nc["inputs"] if item["slot"] == f"{PREFIX}{name}")


@pytest.mark.parametrize(
    ("name", "edit", "message"),
    [
        (
            "nc_pit_2026_income_tax_refunds",
            {"constant_value": 1.0},
            "constant allowlist",
        ),
        (
            "nc_pit_2026_mfs_cap_allocation_share",
            {"constant_value": 0.5},
            "constant allowlist",
        ),
        (
            "nc_pit_2026_income_tax_refunds",
            {"constant_value": True},
            "projection constant must be numeric",
        ),
        (
            "nc_pit_2026_income_tax_refunds",
            {"constant_value": None},
            "projection constant requires constant_value",
        ),
        (
            "nc_pit_2026_income_tax_refunds",
            {"policyengine_variable": "salt_refund_income"},
            "projection constant may not declare PE metadata",
        ),
    ],
)
def test_contract_rejects_unreviewed_projection_constant(name, edit, message) -> None:
    document = _document()
    slot = _nc_slot(document, name)
    for key, value in edit.items():
        if value is None:
            slot.pop(key)
        else:
            slot[key] = value

    with pytest.raises(StateTaxPopulaceContractError, match=message):
        validate_state_tax_populace_contract(document)


def test_contract_rejects_projection_constant_for_a_modeled_upstream_slot() -> None:
    document = _document()
    slot = _nc_slot(document, "nc_pit_2026_federal_adjusted_gross_income")
    for key in ("policyengine_variable", "policyengine_relationship"):
        slot.pop(key)
    slot["source_kind"] = "projection_constant"
    slot["constant_value"] = 0.0

    with pytest.raises(StateTaxPopulaceContractError, match="constant allowlist"):
        validate_state_tax_populace_contract(document)


def test_contract_rejects_the_completed_nc_taxable_income_boundary() -> None:
    document = _document()
    slot = _nc_slot(document, "nc_pit_2026_federal_adjusted_gross_income")
    slot["policyengine_variable"] = "nc_taxable_income"

    with pytest.raises(StateTaxPopulaceContractError, match="upstream allowlist"):
        validate_state_tax_populace_contract(document)


def test_runtime_contract_accepts_the_packaged_row() -> None:
    _validate_north_carolina_runtime_contract(_nc())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda nc: replace(nc, policyengine_target="nc_income_tax"),
        lambda nc: replace(nc, output=f"{MODULE}#nc_pit_2026_taxable_income"),
        lambda nc: replace(
            nc, program="us-nc:policies/income_tax/pilot_liability_pipeline"
        ),
        lambda nc: replace(nc, inputs=nc.inputs[:-1]),
        lambda nc: replace(
            nc,
            inputs=tuple(
                replace(slot, constant_value=1.0)
                if slot.slot.endswith("nc_pit_2026_income_tax_refunds")
                else slot
                for slot in nc.inputs
            ),
        ),
        lambda nc: replace(
            nc,
            inputs=tuple(
                replace(slot, policyengine_transform="person_sum_to_tax_unit")
                if slot.slot.endswith("nc_pit_2026_eligible_for_federal_standard_deduction")
                else slot
                for slot in nc.inputs
            ),
        ),
        lambda nc: replace(nc, relations=nc.inputs[:1]),
    ],
)
def test_runtime_contract_fails_closed_on_drift(mutate) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match="NC:"):
        _validate_north_carolina_runtime_contract(mutate(_nc()))


def _money(**extra):
    return SimpleNamespace(
        entity=SimpleNamespace(key="tax_unit"),
        definition_period="year",
        value_type=float,
        unit="currency-USD",
        get_formula=lambda period: None,
        **extra,
    )


def _nc_system(
    *,
    deductions=NC_REVIEWED_POLICYENGINE_DEDUCTIONS,
    gross_income_sources=("employment_income", "taxable_social_security"),
    taxable_adds=("adjusted_gross_income", "nc_additions"),
    taxable_subtracts=("nc_deductions",),
    mortgage_adds=("non_deductible_mortgage_interest", "deductible_mortgage_interest"),
    deductions_adds="gov.states.nc.tax.income.deductions.deductions",
    taxable_formula=None,
):
    variables = {
        name: _money()
        for name in (
            "nc_income_tax_before_credits",
            "nc_additions",
            "adjusted_gross_income",
            "wagering_losses_deduction",
        )
    }
    variables["nc_taxable_income"] = _money(
        adds=list(taxable_adds), subtracts=list(taxable_subtracts)
    )
    if taxable_formula is not None:
        variables["nc_taxable_income"].get_formula = lambda period: taxable_formula
    variables["nc_deductions"] = _money(adds=deductions_adds)
    variables["mortgage_interest"] = SimpleNamespace(adds=list(mortgage_adds))
    parameters = SimpleNamespace(
        gov=SimpleNamespace(
            states=SimpleNamespace(
                nc=SimpleNamespace(
                    tax=SimpleNamespace(
                        income=SimpleNamespace(
                            deductions=SimpleNamespace(deductions=list(deductions))
                        )
                    )
                )
            ),
            irs=SimpleNamespace(
                gross_income=SimpleNamespace(sources=list(gross_income_sources))
            ),
        )
    )
    return SimpleNamespace(variables=variables, parameters=lambda period: parameters)


def test_policyengine_runtime_accepts_the_reviewed_structure() -> None:
    _validate_north_carolina_policyengine_runtime(
        sim=SimpleNamespace(tax_benefit_system=_nc_system()), year=2026
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {"deductions": (*NC_REVIEWED_POLICYENGINE_DEDUCTIONS, "nc_bailey_deduction")},
            "reviewed 2026 list",
        ),
        ({"deductions": NC_REVIEWED_POLICYENGINE_DEDUCTIONS[:-1]}, "reviewed 2026 list"),
        ({"deductions_adds": ["us_govt_interest"]}, "reviewed 2026 list"),
        (
            {"gross_income_sources": ("employment_income", "salt_refund_income")},
            "salt_refund_income",
        ),
        (
            {"taxable_adds": ("adjusted_gross_income", "nc_additions", "nc_other")},
            "federal AGI plus nc_additions",
        ),
        ({"taxable_subtracts": ()}, "federal AGI plus nc_additions"),
        ({"taxable_formula": lambda *args: 0.0}, "federal AGI plus nc_additions"),
        ({"mortgage_adds": ("deductible_mortgage_interest",)}, "mortgage_interest"),
    ],
)
def test_policyengine_runtime_fails_closed_on_structural_drift(kwargs, message) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _validate_north_carolina_policyengine_runtime(
            sim=SimpleNamespace(tax_benefit_system=_nc_system(**kwargs)), year=2026
        )


def test_policyengine_runtime_is_2026_only() -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match="2026 only"):
        _validate_north_carolina_policyengine_runtime(
            sim=SimpleNamespace(tax_benefit_system=_nc_system()), year=2025
        )


def test_policyengine_runtime_rejects_non_money_schema() -> None:
    system = _nc_system()
    system.variables["nc_additions"] = replace_namespace(
        system.variables["nc_additions"], value_type=int
    )

    with pytest.raises(StateTaxPopulationRoutingError, match="nc_additions"):
        _validate_north_carolina_policyengine_runtime(
            sim=SimpleNamespace(tax_benefit_system=system), year=2026
        )


def replace_namespace(namespace: SimpleNamespace, **changes) -> SimpleNamespace:
    return SimpleNamespace(**{**vars(namespace), **changes})


# Two TaxUnits: unit 1 is a joint return with two Person members whose
# Person-grain amounts must be summed; unit 2 is a one-person separate return.
_PERSON_IDS = [11, 12, 21]
_PERSON_TAX_UNITS = [1, 1, 2]


def _values(**overrides):
    values = {
        "person_id": _PERSON_IDS,
        "tax_unit_id": [1, 2],
        "adjusted_gross_income": [120_000.0, -500.0],
        "filing_status": ["JOINT", "SEPARATE"],
        "separate_filer_itemizes": [False, True],
        "charitable_deduction": [2_500.0, 0.0],
        "medical_expense_deduction": [0.0, 300.0],
        "ctc_qualifying_children": [2, 0],
        "us_govt_interest": [125.0, 0.0],
        "nc_military_retirement_deduction": [0.0, 0.0],
        "nc_additions": [0.0, 0.0],
        "wagering_losses_deduction": [0.0, 0.0],
        "deductible_mortgage_interest": [6_000.0, 4_000.0, 1_500.0],
        "real_estate_taxes": [2_000.0, 1_000.0, 800.0],
        "taxable_social_security": [0.0, 9_000.0, 0.0],
    }
    values.update(overrides)
    return values


def _simulation(values):
    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"
            self.tax_benefit_system = _nc_system()

        def calculate(self, variable, period, map_to=None):
            assert period == 2026
            if variable == "tax_unit_id" and map_to == "person":
                return _PERSON_TAX_UNITS
            assert map_to is None
            return values[variable]

    return FakeSimulation


def _project(values):
    return calculate_policyengine_projection_inputs(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": [1, 2]}),
        raw_persons=pd.DataFrame(
            {"person_id": _PERSON_IDS, "person_tax_unit_id": _PERSON_TAX_UNITS}
        ),
        routes=(
            TaxUnitRoute(1, 1, "NC", "37", 1, DISPOSITION_READY),
            TaxUnitRoute(2, 2, "NC", "37", 1, DISPOSITION_READY),
        ),
        year=2026,
        microsimulation_factory=_simulation(values),
    )["NC"]


def test_projection_builds_every_resident_core_input_from_leaf_values() -> None:
    projected = _project(_values())

    def slot(name):
        return projected[f"{PREFIX}{name}"]

    assert set(projected) == {f"{PREFIX}{name}" for name in MODULE_INPUTS}
    assert slot("nc_pit_2026_federal_adjusted_gross_income") == {
        1: 120_000.0,
        2: -500.0,
    }
    assert slot("nc_pit_2026_filing_status_joint_or_surviving_spouse") == {
        1: True,
        2: False,
    }
    assert slot("nc_pit_2026_filing_status_married_separately") == {
        1: False,
        2: True,
    }
    assert slot("nc_pit_2026_eligible_for_federal_standard_deduction") == {
        1: True,
        2: False,
    }
    assert slot("nc_pit_2026_qualified_residence_interest") == {
        1: 10_000.0,
        2: 1_500.0,
    }
    assert slot("nc_pit_2026_real_estate_property_taxes") == {1: 3_000.0, 2: 800.0}
    assert slot("nc_pit_2026_mfs_combined_mortgage_interest_and_property_taxes") == {
        1: 13_000.0,
        2: 2_300.0,
    }
    assert slot("nc_pit_2026_taxable_social_security_and_railroad_retirement") == {
        1: 9_000.0,
        2: 0.0,
    }
    assert slot("nc_pit_2026_federal_child_tax_credit_qualifying_children") == {
        1: 2.0,
        2: 0.0,
    }
    assert slot("nc_pit_2026_mfs_cap_allocation_share") == {1: 1.0, 2: 1.0}
    assert slot("nc_pit_2026_income_tax_refunds") == {1: 0.0, 2: 0.0}
    assert slot("nc_pit_2026_other_state_obligation_interest") == {1: 0.0, 2: 0.0}


@pytest.mark.parametrize("variable", ["nc_additions", "wagering_losses_deduction"])
def test_projection_fails_closed_when_a_zero_constant_is_unproved(variable) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=variable):
        _project(_values(**{variable: [0.0, 25.0]}))


@pytest.mark.parametrize("value", [0, 1, 0.0, "False", None])
def test_projection_rejects_a_non_boolean_separate_filer_flag(value) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match="Boolean negation"):
        _project(_values(separate_filer_itemizes=[False, value]))


def test_projection_rejects_a_noncanonical_filing_status() -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match="filing-status"):
        _project(_values(filing_status=["JOINT", "MARRIED"]))


def test_projection_rejects_a_nonfinite_person_amount() -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match="real_estate_taxes"):
        _project(_values(real_estate_taxes=[2_000.0, math.nan, 800.0]))


@given(st.booleans())
def test_boolean_negation_is_an_involution(value: bool) -> None:
    once = _apply_projection_transform(value, transform="boolean_negation", label="x")
    twice = _apply_projection_transform(once, transform="boolean_negation", label="x")

    assert once is (not value)
    assert twice is value


@given(st.one_of(st.integers(), st.floats(allow_nan=False), st.text(), st.none()))
def test_boolean_negation_rejects_every_non_boolean(value) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match="Boolean negation"):
        _apply_projection_transform(value, transform="boolean_negation", label="x")


_money_amounts = st.floats(
    min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False
)


@settings(max_examples=200)
@given(_money_amounts, _money_amounts, st.floats(min_value=0, max_value=1e9))
def test_combined_amount_is_the_commutative_monotone_sum(a, b, delta) -> None:
    def combine(*parts):
        return _apply_projection_transform(
            tuple(parts), transform="person_sums_to_combined_amount", label="x"
        )

    assert combine(a, b) == a + b
    assert combine(a, b) == combine(b, a)
    assert combine(a + delta, b) >= combine(a, b)


@given(
    st.lists(_money_amounts, min_size=1, max_size=4),
    st.sampled_from([math.nan, math.inf, -math.inf]),
)
def test_combined_amount_rejects_nonfinite_components(parts, bad) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match="non-finite"):
        _apply_projection_transform(
            (*parts, bad), transform="person_sums_to_combined_amount", label="x"
        )


@pytest.mark.parametrize("value", [5.0, (5.0,), [1.0, 2.0]])
def test_combined_amount_requires_at_least_two_component_tuple(value) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match="at least two"):
        _apply_projection_transform(
            value, transform="person_sums_to_combined_amount", label="x"
        )


def test_registry_maps_the_resident_core_output_exactly() -> None:
    mapping = load_policyengine_registry().mapping_for_legal_id(OUTPUT, country="us")

    assert mapping is not None
    assert mapping.match_type == "exact"
    assert mapping.mapping_type == "direct_variable"
    assert mapping.policyengine_variable == "nc_income_tax_before_credits"
    assert (mapping.entity, mapping.period, mapping.unit, mapping.comparison) == (
        "tax_unit",
        "year",
        "USD",
        "money",
    )
