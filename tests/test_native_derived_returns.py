"""Derived native UK oracle outputs cannot erase invalid returned operands."""

import math

import pytest
from hypothesis import example, given, settings, strategies as st

from axiom_oracles.bridges import efrs_uk

INVALID = [pytest.param(None, id="missing"), pytest.param(math.nan, id="nan"),
           pytest.param(math.inf, id="infinity"), pytest.param(-math.inf, id="negative-infinity")]


@pytest.mark.parametrize("invalid", INVALID)
@pytest.mark.parametrize("operand", ["uc_maximum_amount", "uc_income_reduction"])
def test_derived_uc_return_preserves_invalid_operand(invalid, operand):
    row = {"uc_maximum_amount": 0, "uc_income_reduction": 0, operand: invalid}
    spec = efrs_uk.UNIVERSAL_CREDIT_AWARD_OUTPUTS["universal_credit_award_amount"]
    assert not math.isfinite(efrs_uk.policyengine_output_value(spec, row))


@pytest.mark.parametrize("operand", ["uc_maximum_amount", "uc_income_reduction"])
def test_derived_uc_return_preserves_absent_operand(operand):
    row = {"uc_maximum_amount": 0, "uc_income_reduction": 0}
    row.pop(operand)
    spec = efrs_uk.UNIVERSAL_CREDIT_AWARD_OUTPUTS["universal_credit_award_amount"]
    assert not math.isfinite(efrs_uk.policyengine_output_value(spec, row))


@pytest.mark.parametrize("invalid", INVALID)
def test_per_carer_transform_preserves_invalid_denominator(invalid):
    spec = efrs_uk.PENSION_CREDIT_OUTPUTS["carer_additional_amount"]
    row = {spec["pe"]: 0, "num_carers": invalid}
    assert not math.isfinite(efrs_uk.policyengine_output_value(spec, row))


def test_per_carer_transform_preserves_absent_denominator():
    spec = efrs_uk.PENSION_CREDIT_OUTPUTS["carer_additional_amount"]
    assert not math.isfinite(efrs_uk.policyengine_output_value(spec, {spec["pe"]: 0}))


@settings(max_examples=24, deadline=None, database=None, derandomize=True)
@example(maximum=0, reduction=0, carers=False)
@example(maximum=50, reduction=100, carers=0)
@given(maximum=st.integers(0, 100_000), reduction=st.integers(0, 100_000),
       carers=st.one_of(st.booleans(), st.integers(0, 10)))
def test_finite_derived_returns_keep_clamping_and_zero_carer_contract(maximum, reduction, carers):
    award = efrs_uk.UNIVERSAL_CREDIT_AWARD_OUTPUTS["universal_credit_award_amount"]
    row = {"uc_maximum_amount": maximum, "uc_income_reduction": reduction}
    assert efrs_uk.policyengine_output_value(award, row) == max(0, maximum - reduction) / 12
    carer = efrs_uk.PENSION_CREDIT_OUTPUTS["carer_additional_amount"]
    row = {carer["pe"]: maximum, "num_carers": carers}
    assert efrs_uk.policyengine_output_value(carer, row) == maximum / 52 / max(1, int(carers))


@settings(max_examples=24, deadline=None, database=None, derandomize=True)
@example(maximum=None, reduction=0, carers=0)
@example(maximum=0, reduction=math.nan, carers=None)
@given(maximum=st.one_of(st.integers(0, 100_000), st.sampled_from([None, math.nan, math.inf, -math.inf])),
       reduction=st.one_of(st.integers(0, 100_000), st.sampled_from([None, math.nan, math.inf, -math.inf])),
       carers=st.one_of(st.booleans(), st.integers(0, 10), st.sampled_from([None, math.nan, math.inf, -math.inf])))
def test_derived_outputs_require_finite_operands(maximum, reduction, carers):
    award = efrs_uk.UNIVERSAL_CREDIT_AWARD_OUTPUTS["universal_credit_award_amount"]
    result = efrs_uk.policyengine_output_value(award, {
        "uc_maximum_amount": maximum, "uc_income_reduction": reduction,
    })
    finite_operands = all(value is not None and math.isfinite(value) for value in (maximum, reduction))
    if finite_operands:
        assert result == max(0, maximum - reduction) / 12
    else:
        assert math.isnan(result)
    carer = efrs_uk.PENSION_CREDIT_OUTPUTS["carer_additional_amount"]
    result = efrs_uk.policyengine_output_value(carer, {carer["pe"]: 0, "num_carers": carers})
    if carers is not None and math.isfinite(carers):
        assert result == 0
    else:
        assert math.isnan(result)
