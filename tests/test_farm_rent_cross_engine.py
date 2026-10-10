"""The same farm-rent households through Axiom, PolicyEngine, Tax-Calculator
and TAXSIM.

Each engine runs once per module on one batch of Cases and skips when it is
not installed (CI's test job installs none of them; the Axiom leg also needs
the pinned engine checkout, see tests/test_axiom_farm_rent_engine.py, whose
docstring derives every amount used here from the IRS forms).

Where an engine departs from the forms, the test pins the departure and names
its record instead of asserting agreement:

- PolicyEngine-US 1.764.6 leaves farm rent out of the 26 USC 32(i)
  investment-income test (PolicyEngine/policyengine-us#9635; Axiom side
  TheAxiomFoundation/rulespec-us#1416), so its credit survives one dollar
  over the limit. Marked strict xfail: it flips when PolicyEngine fixes it.
- TAXSIM takes farm rent in otherprop, "rent not eligible for QBI
  deduction", so it grants no QBID on it (docs/taxsim-oracle-playbook.md),
  and above the 2026 investment-income limit it reduces the childless credit
  instead of denying it (the taxsim-2026-eitc-investment-limit-vintage
  disposition class).
"""

from __future__ import annotations

import pytest

from axiom_oracles.adapters.axiom.tax_projection import attach_axiom_tax_inputs_to_case
from axiom_oracles.core.case import Case, Concepts, Entity
from tests.test_axiom_farm_rent_engine import BRIDGE_461L_THRESHOLD, _pinned_engine

W = Concepts.YEARLY_EARNED_INCOME
F = Concepts.FARM_RENT_INCOME
R = Concepts.RENTAL_INCOME
SE = Concepts.SELF_EMPLOYMENT_INCOME
STCG = Concepts.SHORT_TERM_CAPITAL_GAINS


def _single(age, **facts):
    return (
        Entity(
            "person-1",
            "person",
            facts={
                Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                Concepts.PERSON_AGE: age,
                **facts,
            },
        ),
    )


HOUSEHOLDS = {
    "gross-income-12000": _single(45, **{W: 30_000, F: 12_000}),
    "loss-8000": _single(45, **{W: 50_000, F: -8_000}),
    "qbi-farm-rent": _single(40, **{W: 60_000, F: 20_000}),
    "ebl-farm-rent-income": _single(55, **{W: 400_000, SE: -350_000, F: 50_000}),
    "ebl-farm-rent-loss": _single(55, **{W: 400_000, F: -350_000}),
    "eitc-12200": _single(30, **{W: 1_000, STCG: -3_000, F: 12_200}),
    "eitc-12201": _single(30, **{W: 1_000, STCG: -3_000, F: 12_201}),
    "eitc-netted-12200": _single(30, **{W: 1_000, STCG: -3_000, F: 13_201, R: -1_001}),
}


def _cases():
    return [
        Case(
            case_id=case_id,
            period="2026",
            entities=people,
            metadata={"state_code": "CO"},
        )
        for case_id, people in HOUSEHOLDS.items()
    ]


def _values(results, names):
    values = {}
    for result in results:
        assert not result.errors, result.errors
        values[result.household_id] = {
            alias: float(result.values[name]) for alias, name in names.items()
        }
    return values


@pytest.fixture(scope="module")
def axiom():
    binary, roots = _pinned_engine()
    from axiom_oracles.cli import _build_runner

    with pytest.MonkeyPatch.context() as env:
        env.setenv("AXIOM_RULESPEC_REPO_ROOTS", str(roots))
        env.delenv("AXIOM_RULESPEC_ROOT", raising=False)
        runner = _build_runner(
            "axiom",
            "api",
            None,
            None,
            (Concepts.FEDERAL_INCOME_TAX,),
            axiom_engine_binary=binary,
        )
        names = {
            "agi": "adjusted_gross_income",
            "qbid": "qualified_business_income_deduction",
            "eitc": "us:statutes/26/32#eitc",
        }
        results = runner.run_cases(
            [attach_axiom_tax_inputs_to_case(case) for case in _cases()],
            list(names.values()),
        )
    return _values(results, names)


@pytest.fixture(scope="module")
def policyengine():
    pytest.importorskip("policyengine_us")
    from axiom_oracles.adapters.policyengine import PolicyEngineRunner

    names = {
        "agi": "adjusted_gross_income",
        "qbid": "qualified_business_income_deduction",
        "eitc": "eitc",
    }
    return _values(PolicyEngineRunner().run_cases(_cases(), list(names.values())), names)


@pytest.fixture(scope="module")
def taxcalc():
    pytest.importorskip("taxcalc")
    from axiom_oracles.adapters.taxcalc.projection import attach_taxcalc_inputs
    from axiom_oracles.adapters.taxcalc.runner import TaxCalcPackageRunner

    names = {"agi": "c00100", "qbid": "qbided", "eitc": "eitc"}
    results = TaxCalcPackageRunner().run_cases(
        attach_taxcalc_inputs(_cases()), list(names.values())
    )
    return _values(results, names)


@pytest.fixture(scope="module")
def taxsim():
    pytest.importorskip("policyengine_taxsim")
    from axiom_oracles.adapters.taxsim.projection import attach_taxsim_inputs
    from axiom_oracles.adapters.taxsim.runner import TaxsimPackageRunner

    names = {"agi": "v10", "qbid": "qbid", "eitc": "v25"}
    results = TaxsimPackageRunner().run_cases(attach_taxsim_inputs(_cases()), None)
    return _values(results, names)


ENGINES = ("axiom", "policyengine", "taxcalc", "taxsim")


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize(
    ("case_id", "agi"),
    [
        pytest.param("gross-income-12000", 42_000, id="income"),
        pytest.param("loss-8000", 42_000, id="loss"),
        pytest.param("qbi-farm-rent", 80_000, id="qbi-household"),
        pytest.param("eitc-12200", 10_200, id="with-a-capital-loss"),
        pytest.param("eitc-netted-12200", 10_200, id="netted-with-part-i"),
    ],
)
def test_every_engine_puts_schedule_e_line_40_in_agi(
    request, engine, case_id, agi
) -> None:
    values = request.getfixturevalue(engine)
    assert values[case_id]["agi"] == pytest.approx(agi)


@pytest.mark.parametrize("engine", ("axiom", "policyengine", "taxcalc"))
def test_farm_rent_qbid_agrees_where_farm_rent_is_qbi(request, engine) -> None:
    values = request.getfixturevalue(engine)
    assert values["qbi-farm-rent"]["qbid"] == pytest.approx(0.20 * 20_000)


def test_taxsim_grants_no_qbid_on_otherprop(taxsim) -> None:
    assert taxsim["qbi-farm-rent"]["qbid"] == 0


@pytest.mark.parametrize("engine", ("axiom", "policyengine"))
def test_axiom_and_policyengine_apply_461l_to_farm_rent_alike(request, engine) -> None:
    """Both engines run the same 2026 threshold (the bridge parameter mirrors
    PolicyEngine's), so the allowance arithmetic must agree exactly."""
    values = request.getfixturevalue(engine)
    income_allowed = min(350_000, 50_000 + BRIDGE_461L_THRESHOLD)
    loss_allowed = min(350_000, BRIDGE_461L_THRESHOLD)
    assert values["ebl-farm-rent-income"]["agi"] == pytest.approx(
        400_000 + 50_000 - income_allowed
    )
    assert values["ebl-farm-rent-loss"]["agi"] == pytest.approx(400_000 - loss_allowed)


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("case_id", ("eitc-12200", "eitc-netted-12200"))
def test_every_engine_keeps_the_credit_at_the_limit(request, engine, case_id) -> None:
    values = request.getfixturevalue(engine)
    assert values[case_id]["eitc"] == pytest.approx(0.0765 * 1_000)


@pytest.mark.parametrize("engine", ("axiom", "taxcalc"))
def test_one_dollar_of_farm_rent_over_the_limit_denies_the_credit(
    request, engine
) -> None:
    values = request.getfixturevalue(engine)
    assert values["eitc-12201"]["eitc"] == 0


@pytest.mark.xfail(
    strict=True,
    reason=(
        "PolicyEngine-US leaves farm rent out of eitc_relevant_investment_income "
        "(PolicyEngine/policyengine-us#9635)"
    ),
)
def test_policyengine_denies_the_credit_one_dollar_over(policyengine) -> None:
    assert policyengine["eitc-12201"]["eitc"] == 0


def test_taxsim_reduces_rather_than_denies_over_the_limit(taxsim) -> None:
    """The pinned binary takes otherprop into investment income (the credit
    at 12,200 is whole) but reduces the credit dollar for dollar above the
    limit: 76.50 - 1 = 75.50."""
    assert taxsim["eitc-12201"]["eitc"] == pytest.approx(76.50 - 1)


# ---------------------------------------------------------------------------
# Differential: the bridge's AGI legs mirror PolicyEngine's (gross-income
# positive parts, 461(l) loss_ald at the same threshold), so on seeded random
# filer-only households mixing farm rent with Part I rents, Schedule C income
# and interest, AGI must agree. Wages stay at most 30,000 and Schedule C at
# most 150,000, so no person straddles the OASDI wage base, where the bridge's
# pinned 186,000 departs from PolicyEngine's 184,500 (an unrelated $93
# difference in the SE-tax deduction).
# ---------------------------------------------------------------------------


def _differential_cases(count=60, seed=566):
    import random

    rng = random.Random(seed)

    def amount(low, high, zero_share):
        return 0 if rng.random() < zero_share else rng.randint(low, high)

    cases = []
    for index in range(count):
        people = []
        for position in range(2 if rng.random() < 0.5 else 1):
            people.append(
                Entity(
                    f"person-{position + 1}",
                    "person",
                    facts={
                        Concepts.HOUSEHOLD_RELATION: (
                            "HeadOfHousehold" if position == 0 else "Spouse"
                        ),
                        Concepts.PERSON_AGE: rng.randint(25, 64),
                        W: amount(0, 30_000, 0.3),
                        F: amount(-200_000, 200_000, 0.1),
                        R: amount(-80_000, 80_000, 0.4),
                        SE: amount(-150_000, 150_000, 0.5),
                        Concepts.INTEREST_INCOME: amount(0, 30_000, 0.5),
                    },
                )
            )
        cases.append(
            Case(
                case_id=f"differential-{index}",
                period="2026",
                entities=tuple(people),
                metadata={"state_code": "TX"},
            )
        )
    return cases


def test_differential_axiom_and_policyengine_agi_agree_with_farm_rent() -> None:
    binary, roots = _pinned_engine()
    pytest.importorskip("policyengine_us")
    from axiom_oracles.adapters.policyengine import PolicyEngineRunner
    from axiom_oracles.cli import _build_runner

    cases = _differential_cases()
    assert sum(
        1
        for case in cases
        for person in case.entities
        if person.fact(F, 0) < 0
    ) >= 10  # losses are exercised, not only income
    with pytest.MonkeyPatch.context() as env:
        env.setenv("AXIOM_RULESPEC_REPO_ROOTS", str(roots))
        env.delenv("AXIOM_RULESPEC_ROOT", raising=False)
        runner = _build_runner(
            "axiom",
            "api",
            None,
            None,
            (Concepts.FEDERAL_INCOME_TAX,),
            axiom_engine_binary=binary,
        )
        axiom = _values(
            runner.run_cases(
                [attach_axiom_tax_inputs_to_case(case) for case in cases],
                ["adjusted_gross_income", "loss_ald"],
            ),
            {"agi": "adjusted_gross_income", "loss": "loss_ald"},
        )
    policyengine = _values(
        PolicyEngineRunner().run_cases(cases, ["adjusted_gross_income", "loss_ald"]),
        {"agi": "adjusted_gross_income", "loss": "loss_ald"},
    )

    for case in cases:
        assert axiom[case.case_id]["loss"] == pytest.approx(
            policyengine[case.case_id]["loss"], abs=0.05
        ), case.case_id
        assert axiom[case.case_id]["agi"] == pytest.approx(
            policyengine[case.case_id]["agi"], abs=0.05
        ), case.case_id
