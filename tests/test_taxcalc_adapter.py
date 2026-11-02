"""TaxCalc (PSL Tax-Calculator) adapter unit + live-when-installed tests.

The projection tests drive a fake runner so they assert the Case → Tax-Calculator
input projection and concept → variable mapping without importing ``taxcalc``.
The final test is gated on the package being importable and checks a real
Tax-Calculator EITC entitlement so a broken projection or credit-claiming
override is caught end to end.
"""

from __future__ import annotations

import pytest

from axiom_oracles.adapters.taxcalc import TaxCalcPackageRunner
from axiom_oracles.core.case import Case, Concepts, Entity


def test_taxcalc_package_runner_wraps_taxcalc_rows_and_maps_concepts() -> None:
    captured_inputs: list[dict] = []
    captured_variables: list[str] = []

    class FakeTaxCalcRunner:
        def __init__(self, input_rows):
            captured_inputs.extend(input_rows)

        def run(self, variables=None):
            captured_variables.extend(variables or [])
            return [{"RECID": "case-1", "iitax": 100, "c00100": 50_000}]

    case = Case(
        case_id="case-1",
        period="2026",
        metadata={
            "taxcalc_input": {
                "FLPDYR": 2026,
                "MARS": 1,
                "age_head": 40,
                "e00200": 50_000,
            }
        },
    )

    results = TaxCalcPackageRunner(runner_factory=FakeTaxCalcRunner).run_cases(
        [case],
        variables=[Concepts.FEDERAL_INCOME_TAX, Concepts.AGI],
    )

    assert captured_inputs[0]["RECID"] == "case-1"
    assert captured_inputs[0]["FLPDYR"] == 2026
    assert captured_variables == ["iitax", "c00100"]
    assert results[0].engine == "taxcalc"
    assert results[0].household_id == "case-1"
    assert results[0].values == {"iitax": 100, "c00100": 50_000}


def test_taxcalc_package_runner_projects_thin_case_inputs() -> None:
    captured_inputs: list[dict] = []

    class FakeTaxCalcRunner:
        def __init__(self, input_rows):
            captured_inputs.extend(input_rows)

        def run(self, variables=None):
            del variables
            return [{"RECID": 1, "iitax": 100}]

    case = Case(
        case_id="case-1",
        period="2026",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 40,
                    Concepts.YEARLY_EARNED_INCOME: 50_000,
                },
            ),
        ),
    )

    results = TaxCalcPackageRunner(runner_factory=FakeTaxCalcRunner).run_cases(
        [case],
        variables=[Concepts.FEDERAL_INCOME_TAX],
    )

    assert captured_inputs[0]["FLPDYR"] == 2026
    assert captured_inputs[0]["MARS"] == 1
    assert captured_inputs[0]["e00200"] == 50_000
    assert results[0].household_id == "case-1"
    assert results[0].values == {"iitax": 100}


def test_taxcalc_package_runner_projects_dependent_credit_counts() -> None:
    captured_inputs: list[dict] = []

    class FakeTaxCalcRunner:
        def __init__(self, input_rows):
            captured_inputs.extend(input_rows)

        def run(self, variables=None):
            del variables
            return [{"RECID": 1, "iitax": 100}]

    case = Case(
        case_id="case-1",
        period="2026",
        entities=(
            Entity(
                "head",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 30,
                    Concepts.YEARLY_EARNED_INCOME: 50_000,
                },
            ),
            Entity(
                "child-5",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.PERSON_AGE: 5,
                },
            ),
            Entity(
                "child-17",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.PERSON_AGE: 17,
                },
            ),
            Entity(
                "disabled-dependent",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.PERSON_AGE: 40,
                    Concepts.DISABLED: True,
                },
            ),
        ),
    )

    TaxCalcPackageRunner(runner_factory=FakeTaxCalcRunner).run_cases(
        [case],
        variables=[Concepts.FEDERAL_INCOME_TAX],
    )

    input_row = captured_inputs[0]
    assert input_row["MARS"] == 4
    assert input_row["EIC"] == 3
    assert input_row["n24"] == 1
    assert input_row["nu18"] == 2
    assert input_row["nu13"] == 1
    assert input_row["nu06"] == 1


def test_taxcalc_package_runner_limits_head_of_household_to_qualifying_dependents() -> None:
    captured_inputs: list[dict] = []

    class FakeTaxCalcRunner:
        def __init__(self, input_rows):
            captured_inputs.extend(input_rows)

        def run(self, variables=None):
            del variables
            return [{"RECID": 1, "iitax": 100}]

    case = Case(
        case_id="case-1",
        period="2026",
        entities=(
            Entity(
                "head",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 66,
                },
            ),
            Entity(
                "adult-dependent",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Dependent",
                    Concepts.PERSON_AGE: 34,
                    Concepts.DISABLED: True,
                    Concepts.YEARLY_EARNED_INCOME: 21_866,
                    Concepts.SELF_EMPLOYMENT_INCOME: 5_010,
                },
            ),
        ),
    )

    TaxCalcPackageRunner(runner_factory=FakeTaxCalcRunner).run_cases(
        [case],
        variables=[Concepts.FEDERAL_INCOME_TAX],
    )

    assert captured_inputs[0]["MARS"] == 1


def test_taxcalc_package_runner_caps_qualified_dividends_at_total_dividends() -> None:
    captured_inputs: list[dict] = []

    class FakeTaxCalcRunner:
        def __init__(self, input_rows):
            captured_inputs.extend(input_rows)

        def run(self, variables=None):
            del variables
            return [{"RECID": 1, "iitax": 100}]

    case = Case(
        case_id="case-1",
        period="2026",
        entities=(
            Entity(
                "head",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 40,
                    Concepts.DIVIDEND_INCOME: 100,
                    Concepts.QUALIFIED_DIVIDEND_INCOME: 250,
                    Concepts.PENSION_INCOME: 1_000,
                    Concepts.RENTAL_INCOME: 500,
                },
            ),
        ),
    )

    TaxCalcPackageRunner(runner_factory=FakeTaxCalcRunner).run_cases(
        [case],
        variables=[Concepts.FEDERAL_INCOME_TAX],
    )

    assert captured_inputs[0]["e00600"] == 100
    assert captured_inputs[0]["e00650"] == 100
    assert captured_inputs[0]["e01500"] == 1_000
    assert captured_inputs[0]["e01700"] == 1_000
    assert captured_inputs[0]["e02000"] == 500


def test_taxcalc_projection_maps_tax_exempt_interest_to_e00400() -> None:
    """records_variables.json: e00400 is "Tax-exempt interest income", a
    filing-unit input: the head's 4,000 plus the spouse's 1,500 (a child's
    900 is not on the filers' Form 1040 line 2a)."""
    captured_inputs: list[dict] = []

    class FakeTaxCalcRunner:
        def __init__(self, input_rows):
            captured_inputs.extend(input_rows)

        def run(self, variables=None):
            del variables
            return [{"RECID": 1, "iitax": 0}]

    case = Case(
        case_id="case-1",
        period="2026",
        entities=(
            Entity(
                "head",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 70,
                    Concepts.INTEREST_INCOME: 2_000,
                    Concepts.TAX_EXEMPT_INTEREST_INCOME: 4_000,
                },
            ),
            Entity(
                "spouse",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Spouse",
                    Concepts.PERSON_AGE: 68,
                    Concepts.TAX_EXEMPT_INTEREST_INCOME: 1_500,
                },
            ),
            Entity(
                "child",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.PERSON_AGE: 15,
                    Concepts.TAX_EXEMPT_INTEREST_INCOME: 900,
                },
            ),
        ),
    )

    TaxCalcPackageRunner(runner_factory=FakeTaxCalcRunner).run_cases(
        [case],
        variables=[Concepts.FEDERAL_INCOME_TAX],
    )

    assert captured_inputs[0]["e00400"] == 5_500
    assert captured_inputs[0]["e00300"] == 2_000


def test_taxcalc_prices_tax_exempt_interest_when_installed() -> None:
    """Live Tax-Calculator on two IRS-worksheet cases.

    Social Security (Form 1040 Instructions (2025) p. 32 worksheet, "4. Enter
    the amount, if any, from Form 1040 or 1040-SR, line 2a"): single, SS
    20,000, wages 10,000, taxable interest 8,000. Line 3 = 18,000. With
    10,000 of line 2a: line 5 = 10,000 + 18,000 + 10,000 = 38,000, line 9 =
    13,000, line 11 = 4,000, line 13 = 4,500, taxable benefits = 4,500 +
    3,400 = 7,900, so AGI = 18,000 + 7,900 = 25,900. Without it: line 5 =
    28,000, line 9 = 3,000, taxable benefits = 1,500, AGI = 19,500.

    EITC (Pub. 596 (2025) Worksheet 1 line 2 is Form 1040 line 2a; Rev. Proc.
    2025-32: no 2026 credit if investment income "exceeds $12,200"): a
    childless 30-year-old with 8,000 of wages keeps the same credit with
    12,200 of tax-exempt interest (line 2a is not in AGI) and loses it at
    12,201.
    """
    pytest.importorskip("taxcalc")

    def single(age, **facts):
        return (
            Entity(
                "head",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: age,
                    **facts,
                },
            ),
        )

    social_security = {
        Concepts.YEARLY_EARNED_INCOME: 10_000,
        Concepts.INTEREST_INCOME: 8_000,
        Concepts.SOCIAL_SECURITY_BENEFITS: 20_000,
    }
    cases = [
        Case(
            case_id="ss-with-2a",
            period="2026",
            entities=single(
                67, **social_security, **{Concepts.TAX_EXEMPT_INTEREST_INCOME: 10_000}
            ),
        ),
        Case(
            case_id="ss-without-2a",
            period="2026",
            entities=single(67, **social_security),
        ),
    ] + [
        Case(
            case_id=f"eitc-{interest}",
            period="2026",
            entities=single(
                30,
                **{
                    Concepts.YEARLY_EARNED_INCOME: 8_000,
                    Concepts.TAX_EXEMPT_INTEREST_INCOME: interest,
                },
            ),
        )
        for interest in (0, 12_200, 12_201)
    ]

    results = {
        result.household_id: result.values
        for result in TaxCalcPackageRunner().run_cases(
            cases, variables=[Concepts.AGI, Concepts.EITC]
        )
    }

    assert results["ss-with-2a"]["c00100"] == pytest.approx(25_900)
    assert results["ss-without-2a"]["c00100"] == pytest.approx(19_500)
    assert results["eitc-0"]["eitc"] > 0
    assert results["eitc-12200"]["eitc"] == pytest.approx(results["eitc-0"]["eitc"])
    assert results["eitc-12201"]["eitc"] == 0
    for interest in (0, 12_200, 12_201):
        assert results[f"eitc-{interest}"]["c00100"] == pytest.approx(8_000)


def test_taxcalc_package_runner_reports_legal_eitc_entitlement_when_installed() -> None:
    pytest.importorskip("taxcalc")

    variables = [Concepts.EITC]
    cases = [
        Case(
            case_id=f"age-{age}",
            period="2024",
            entities=(
                Entity(
                    "head",
                    "person",
                    facts={
                        Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                        Concepts.PERSON_AGE: age,
                        Concepts.YEARLY_EARNED_INCOME: 15_000,
                    },
                ),
            ),
            outputs=tuple(variables),
        )
        for age in (64, 65)
    ]

    results = TaxCalcPackageRunner().run_cases(cases, variables=variables)

    assert round(results[0].values["eitc"], 2) == 274.75
    assert results[1].values["eitc"] == 0
