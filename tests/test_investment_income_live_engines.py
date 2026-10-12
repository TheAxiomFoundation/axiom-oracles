"""One household, four live engines: dividends and Form 1040 line 7a.

Each engine prices the same Case through its own projection: PolicyEngine-US
(the installed release), PSL Tax-Calculator, the pinned TAXSIM-35 binary, and
the Axiom engine and rulespec-us roots that comparisons/fiit-taxsim-ecps.yaml
pins (skipped when that checkout is absent, as on CI). The expected values
are worked by hand from the 2025 worksheets at the 2026 amounts below; they
are not copied from any engine.

2026 amounts, Rev. Proc. 2025-32:

- .14(1): "the standard deduction amounts under § 63(c)(2) are ... Unmarried
  Individuals (other than Surviving Spouses and Heads of Households) ...
  $16,100".
- Table 3 (unmarried individuals): "Not over $12,400: 10% of the taxable
  income; Over $12,400 but not over $50,400: $1,240 plus 12% of the excess
  over $12,400; Over $50,400 but not over $105,700: $5,800 plus 22% of the
  excess over $50,400".
- .03: "the maximum zero rate amounts and maximum 15 percent rate amounts
  ... All Other Individuals $49,450 $545,500".
- .06(2): "the earned income tax credit is not allowed under § 32(i) if the
  aggregate amount of certain investment income exceeds $12,200."

Single filer, age 40, wages 60,000, ordinary dividends 5,000 (line 3b) of
which 3,000 qualified (line 3a), capital gain distributions 2,000 reported
on line 7a without Schedule D:

    AGI = 60,000 + 5,000 + 2,000 = 67,000 (line 3a is inside line 3b)
    taxable income = 67,000 - 16,100 = 50,900
    Qualified Dividends and Capital Gain Tax Worksheet:
     1. 50,900    2. 3,000 (line 3a)    3. 2,000 (line 7a, no Schedule D)
     4. 5,000     5. 45,900             6. 49,450
     7. 49,450    8. 45,900             9. 3,550 (taxed at 0%)
    10. 5,000    11. 3,550             12. 1,450
    13. 545,500  14. 50,900            15. 49,450
    16. 1,450    17. 1,450             18. 217.50 (15%)
    22. tax on line 5: 1,240 + 12% x (45,900 - 12,400) = 5,260
    23. 5,477.50  24. tax on line 1: 5,800 + 22% x 500 = 5,910
    25. 5,477.50

26 USC 852(b)(3)(B) makes the same 2,000 a long-term gain, so reporting it
on Schedule D instead (line 15 = line 16 = 2,000, worksheet line 3 = 2,000)
gives the same return: this is the metamorphic check every engine must pass.

Without line 7a: AGI 65,000, taxable income 48,900; line 4 = 3,000, line 5
= 45,900, all 3,000 falls under 49,450 and is taxed at 0%; tax = 5,260.
With all 5,000 qualified: line 5 = 43,900; tax = 1,240 + 12% x 31,500 =
5,020. With none qualified: tax = 1,240 + 12% x 36,500 = 5,620. Line 3b is
5,000 in all three, so AGI and taxable income never move with the split.

Known engine differences this module records rather than hides:

- TAXSIM-35 at law year 2026 gives 5,410.10 on the line 7a return, 67.40
  below the worksheet, and the same on the Schedule D version, so only its
  AGI, taxable income and that equivalence are asserted for those two.
- TAXSIM-35 has no child EITC at law year 2026. Its investment-income test
  is exercised at 2024 instead: every column the projection uses counts,
  but the credit falls dollar for dollar above the limit rather than to zero.
- Tax-Calculator 6.7.1 leaves e01100 out of its EITC investment income
  (calcfunctions.py: ``invinc = (e00400 + e00300 + e00600 + max(0., c01000)
  + max(0., (e02000 - e26270)))``), although Pub. 596 Worksheet 1 line 5 is
  Form 1040 line 7a. The EITC test marks that leg as an expected failure.
- PolicyEngine-US before PolicyEngine/policyengine-us#8839 (issue #8828)
  left non_sch_d_capital_gains out of gross income; the comparison suites
  pin 1.752.2, which predates the fix. These tests need the fixed release
  and skip otherwise.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

from axiom_oracles.cli import _build_runner, _prepare_cases_for_engines
from axiom_oracles.comparison.mappings import mappings_by_concept
from axiom_oracles.core.case import Case, Concepts, Entity

REPO_ROOT = Path(__file__).resolve().parents[1]
# CI's investment-income-live job installs PolicyEngine-US and Tax-Calculator
# and sets this, so those two engines cannot ride in on a skip. TAXSIM and
# the pinned Axiom engine still skip there.
REQUIRE_LIVE = os.environ.get("AXIOM_ORACLES_REQUIRE_INVESTMENT_INCOME_LIVE") == "1"
PIN_SUITE = REPO_ROOT / "comparisons" / "fiit-taxsim-ecps.yaml"
COLORADO = {"state": "CO", "scope": {"type": "census_state", "geoid": "08"}}

DIV = Concepts.DIVIDEND_INCOME
QDIV = Concepts.QUALIFIED_DIVIDEND_INCOME
CGD = Concepts.NON_SCHEDULE_D_CAPITAL_GAIN_DISTRIBUTIONS
LTCG = Concepts.LONG_TERM_CAPITAL_GAINS
WAGES = Concepts.YEARLY_EARNED_INCOME

OUTPUTS = (
    Concepts.AGI,
    Concepts.TAXABLE_INCOME,
    Concepts.TAX_BEFORE_CREDITS,
    Concepts.EITC,
)
# The Axiom AGI and capital gains worksheet are bridge rules with no concept
# mapping; they are requested by their rule ids.
BRIDGE = "us:tax/oracle-bridge#"
AXIOM_AGI = BRIDGE + "adjusted_gross_income"
AXIOM_WORKSHEET_LINE_9 = BRIDGE + "capital_gains_worksheet_line_9"
AXIOM_WORKSHEET_LINE_10 = BRIDGE + "capital_gains_worksheet_line_10"
AXIOM_NET_CAPITAL_GAIN = "us:statutes/26/1/h#net_capital_gain"
AXIOM_RULE_OUTPUTS = (
    AXIOM_AGI,
    AXIOM_WORKSHEET_LINE_9,
    AXIOM_WORKSHEET_LINE_10,
    AXIOM_NET_CAPITAL_GAIN,
)


def _person(entity_id, relation, age, **facts):
    return Entity(
        entity_id,
        "person",
        facts={
            Concepts.HOUSEHOLD_RELATION: relation,
            Concepts.PERSON_AGE: age,
            **facts,
        },
    )


def _single(**facts):
    return (_person("person-1", "HeadOfHousehold", 40, **{WAGES: 60_000, **facts}),)


def _parent(**facts):
    return (
        _person("person-1", "HeadOfHousehold", 35, **{WAGES: 20_000, **facts}),
        _person("person-2", "Child", 8),
    )


HOUSEHOLDS = {
    "line-7a": _single(**{DIV: 5_000, QDIV: 3_000, CGD: 2_000}),
    "schedule-d": _single(**{DIV: 5_000, QDIV: 3_000, LTCG: 2_000}),
    "no-gain": _single(**{DIV: 5_000, QDIV: 3_000}),
    "all-qualified": _single(**{DIV: 5_000, QDIV: 5_000}),
    "none-qualified": _single(**{DIV: 5_000}),
    "eitc-7a-at-limit": _parent(**{CGD: 12_200}),
    "eitc-7a-over-limit": _parent(**{CGD: 12_201}),
    "eitc-3b-at-limit": _parent(**{DIV: 12_200, QDIV: 6_000}),
    "eitc-3b-over-limit": _parent(**{DIV: 12_201, QDIV: 6_000}),
}

# (taxable income, tax before credits), worked in the module docstring.
WORKED = {
    "line-7a": (50_900, 5_477.50),
    "schedule-d": (50_900, 5_477.50),
    "no-gain": (48_900, 5_260),
    "all-qualified": (48_900, 5_020),
    "none-qualified": (48_900, 5_620),
}
# AGI: wages 60,000 + line 3b 5,000 (+ the 2,000 of line 7a or Schedule D gain).
WORKED_AGI = {
    "line-7a": 67_000,
    "schedule-d": 67_000,
    "no-gain": 65_000,
    "all-qualified": 65_000,
    "none-qualified": 65_000,
}


def _cases():
    return [
        Case(
            case_id=case_id,
            period="2026",
            entities=people,
            outputs=OUTPUTS,
            metadata=dict(COLORADO),
        )
        for case_id, people in HOUSEHOLDS.items()
    ]


def _by_concept(runner, results):
    """{case_id: {concept: value}} with list-valued targets summed."""

    mappings = mappings_by_concept()
    values = {}
    for result in results:
        assert not result.errors, result.errors
        row = {}
        for concept in OUTPUTS:
            target = mappings[concept].target_for_engine(runner.name)
            targets = target if isinstance(target, list | tuple) else [target]
            if all(name in result.values for name in targets):
                row[concept] = sum(float(result.values[name]) for name in targets)
        values[result.household_id] = row
    return values


def _runner_and_cases(engine, cases=None, **runner_kwargs):
    runner = _build_runner(
        engine, "api", None, None, (Concepts.FEDERAL_INCOME_TAX,), **runner_kwargs
    )
    prepared = _prepare_cases_for_engines(
        _cases() if cases is None else cases,
        {engine, "taxsim"} if engine == "axiom" else {engine},
        OUTPUTS,
    )
    return runner, prepared


def _run(engine, **runner_kwargs):
    runner, cases = _runner_and_cases(engine, **runner_kwargs)
    return _by_concept(runner, runner.run_cases(cases, list(OUTPUTS)))


def _import_or_skip(module: str, *, required: bool = False):
    try:
        return __import__(module)
    except ImportError:
        if required and REQUIRE_LIVE:
            pytest.fail(f"{module} must be installed when live tests are required")
        pytest.skip(f"{module} is not installed")


@pytest.fixture(scope="module")
def taxcalc_values():
    _import_or_skip("taxcalc", required=True)
    return _run("taxcalc")


@pytest.fixture(scope="module")
def taxsim_values():
    _import_or_skip("policyengine_taxsim")
    return _run("taxsim")


@pytest.fixture(scope="module")
def policyengine_values():
    policyengine_us = _import_or_skip("policyengine_us", required=True)
    sources = policyengine_us.system.system.parameters.gov.irs.gross_income.sources(
        "2026-01-01"
    )
    if "non_sch_d_capital_gains" not in sources:
        message = (
            "installed PolicyEngine-US predates policyengine-us#8839 "
            "(non_sch_d_capital_gains is not in gross income)"
        )
        if REQUIRE_LIVE:
            pytest.fail(message)
        pytest.skip(message)
    return _run("policyengine")


def _checkout_at(path: Path, revision: str) -> bool:
    try:
        head = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return False
    return head.startswith(revision)


@pytest.fixture(scope="module")
def pinned_axiom():
    """The engine binary and rulespec roots comparisons/fiit-taxsim-ecps.yaml
    pins, or a skip when that checkout is absent (as on CI)."""
    runner = yaml.safe_load(PIN_SUITE.read_text())["runner"]
    parameters = runner["parameters"]
    engine_repo = Path(os.path.expandvars(runner["axiom_rules_repo"])).expanduser()
    binary = engine_repo / "target" / "release" / "axiom-rules-engine"
    roots = Path(
        os.path.expandvars(parameters["axiom_rulespec_repo_roots"])
    ).expanduser()
    if not binary.is_file():
        pytest.skip(f"pinned Axiom engine binary not built: {binary}")
    if not _checkout_at(engine_repo, str(runner["axiom_rules_repo_revision"])):
        pytest.skip(f"{engine_repo} is not at the pinned engine revision")
    if not _checkout_at(
        roots / "rulespec-us", str(parameters["axiom_rulespec_repo_roots_revision"])
    ):
        pytest.skip(f"{roots}/rulespec-us is not at the pinned revision")
    return binary, roots


@pytest.fixture(scope="module")
def axiom_values(pinned_axiom):
    binary, roots = pinned_axiom
    with pytest.MonkeyPatch.context() as env:
        # The suite pin is authoritative, as in scripts/run_comparison.py.
        env.setenv("AXIOM_RULESPEC_REPO_ROOTS", str(roots))
        env.delenv("AXIOM_RULESPEC_ROOT", raising=False)
        return _run("axiom", axiom_engine_binary=binary)


@pytest.fixture(scope="module")
def axiom_rule_values(pinned_axiom):
    binary, roots = pinned_axiom
    with pytest.MonkeyPatch.context() as env:
        env.setenv("AXIOM_RULESPEC_REPO_ROOTS", str(roots))
        env.delenv("AXIOM_RULESPEC_ROOT", raising=False)
        runner, cases = _runner_and_cases("axiom", axiom_engine_binary=binary)
        results = runner.run_cases(cases, list(AXIOM_RULE_OUTPUTS))
    values = {}
    for result in results:
        assert not result.errors, result.errors
        values[result.household_id] = result.values
    return values


ENGINES_WITH_RATE_PARITY = ("axiom_values", "policyengine_values", "taxcalc_values")


@pytest.mark.parametrize("engine", ENGINES_WITH_RATE_PARITY)
@pytest.mark.parametrize("case_id", sorted(WORKED))
def test_engine_reproduces_the_worksheet(engine, case_id, request) -> None:
    values = request.getfixturevalue(engine)[case_id]
    taxable_income, tax = WORKED[case_id]
    assert values[Concepts.TAXABLE_INCOME] == pytest.approx(taxable_income, abs=0.01)
    assert values[Concepts.TAX_BEFORE_CREDITS] == pytest.approx(tax, abs=0.01)


@pytest.mark.parametrize(
    "engine", ["policyengine_values", "taxcalc_values", "taxsim_values"]
)
@pytest.mark.parametrize("case_id", sorted(WORKED_AGI))
def test_engine_agi_counts_line_3b_once_and_line_7a(engine, case_id, request) -> None:
    values = request.getfixturevalue(engine)[case_id]
    assert values[Concepts.AGI] == pytest.approx(WORKED_AGI[case_id], abs=0.01)


@pytest.mark.parametrize("case_id", sorted(WORKED_AGI))
def test_axiom_agi_counts_line_3b_once_and_line_7a(axiom_rule_values, case_id) -> None:
    assert axiom_rule_values[case_id][AXIOM_AGI] == pytest.approx(
        WORKED_AGI[case_id], abs=0.01
    )


@pytest.mark.parametrize(
    ("case_id", "line_9", "line_10", "net_capital_gain"),
    [
        # Line 9 is the gain taxed at the preferential rates other than
        # qualified dividends; line 10 adds the 3,000 of line 3a.
        ("line-7a", 2_000, 5_000, 5_000),
        ("schedule-d", 2_000, 5_000, 5_000),
        ("no-gain", 0, 3_000, 3_000),
    ],
)
def test_axiom_worksheet_counts_line_7a_once(
    axiom_rule_values, case_id, line_9, line_10, net_capital_gain
) -> None:
    values = axiom_rule_values[case_id]
    assert values[AXIOM_WORKSHEET_LINE_9] == pytest.approx(line_9)
    assert values[AXIOM_WORKSHEET_LINE_10] == pytest.approx(line_10)
    assert values[AXIOM_NET_CAPITAL_GAIN] == pytest.approx(net_capital_gain)


@pytest.mark.parametrize("case_id", sorted(WORKED))
def test_taxsim_sees_the_same_taxable_income(taxsim_values, case_id) -> None:
    assert taxsim_values[case_id][Concepts.TAXABLE_INCOME] == pytest.approx(
        WORKED[case_id][0], abs=0.01
    )


@pytest.mark.parametrize("case_id", ["no-gain", "all-qualified", "none-qualified"])
def test_taxsim_reproduces_the_dividend_worksheets(taxsim_values, case_id) -> None:
    assert taxsim_values[case_id][Concepts.TAX_BEFORE_CREDITS] == pytest.approx(
        WORKED[case_id][1], abs=0.01
    )


@pytest.mark.parametrize("engine", [*ENGINES_WITH_RATE_PARITY, "taxsim_values"])
def test_line_7a_is_taxed_like_the_same_schedule_d_gain(engine, request) -> None:
    """26 USC 852(b)(3)(B): the distribution is a long-term capital gain."""
    values = request.getfixturevalue(engine)
    line_7a, schedule_d, no_gain = (
        values["line-7a"],
        values["schedule-d"],
        values["no-gain"],
    )
    assert line_7a[Concepts.TAXABLE_INCOME] == pytest.approx(
        schedule_d[Concepts.TAXABLE_INCOME], abs=0.01
    )
    assert line_7a[Concepts.TAX_BEFORE_CREDITS] == pytest.approx(
        schedule_d[Concepts.TAX_BEFORE_CREDITS], abs=0.01
    )
    # And it is income: 2,000 more than the household without it.
    assert line_7a[Concepts.TAXABLE_INCOME] - no_gain[
        Concepts.TAXABLE_INCOME
    ] == pytest.approx(2_000, abs=0.01)


@pytest.mark.parametrize("engine", [*ENGINES_WITH_RATE_PARITY, "taxsim_values"])
def test_qualified_share_moves_tax_but_not_taxable_income(engine, request) -> None:
    values = request.getfixturevalue(engine)
    taxable = {
        case_id: values[case_id][Concepts.TAXABLE_INCOME]
        for case_id in ("no-gain", "all-qualified", "none-qualified")
    }
    assert len({round(value, 2) for value in taxable.values()}) == 1
    assert (
        values["all-qualified"][Concepts.TAX_BEFORE_CREDITS]
        < values["no-gain"][Concepts.TAX_BEFORE_CREDITS]
        < values["none-qualified"][Concepts.TAX_BEFORE_CREDITS]
    )


@pytest.mark.parametrize(
    ("engine", "source"),
    [
        pytest.param("axiom_values", "7a", id="axiom-line-7a"),
        pytest.param("policyengine_values", "7a", id="policyengine-line-7a"),
        pytest.param(
            "taxcalc_values",
            "7a",
            id="taxcalc-line-7a",
            marks=pytest.mark.xfail(
                strict=True,
                reason=(
                    "Tax-Calculator 6.7.1 leaves e01100 out of its EITC "
                    "investment income; Pub. 596 Worksheet 1 line 5 is "
                    "Form 1040 line 7a"
                ),
            ),
        ),
        pytest.param("axiom_values", "3b", id="axiom-line-3b"),
        pytest.param("policyengine_values", "3b", id="policyengine-line-3b"),
        pytest.param("taxcalc_values", "3b", id="taxcalc-line-3b"),
    ],
)
def test_eitc_investment_income_gate_counts_the_line(engine, source, request) -> None:
    """Pub. 596 Worksheet 1 lines 3 and 5; Rev. Proc. 2025-32 .06(2)."""
    values = request.getfixturevalue(engine)
    at_limit = values[f"eitc-{source}-at-limit"][Concepts.EITC]
    over_limit = values[f"eitc-{source}-over-limit"][Concepts.EITC]
    assert at_limit > 0
    assert over_limit == 0


# ---------------------------------------------------------------------------
# TAXSIM's own EITC investment-income test, by input column.
# ---------------------------------------------------------------------------
#
# The pinned binary has no child EITC at law year 2026, so its test is
# exercised at 2024, when the limit was $11,600 (Pub. 596 (2024), Rule 6:
# "Your Investment Income Must Be $11,600 or Less"). Parent with one child,
# wages 5,000, so AGI stays below the phase-out and only the investment-income
# rule can move the credit.

TAXSIM_2024_LIMIT = 11_600
TAXSIM_INVESTMENT_COLUMNS = {
    "intrec": lambda amount: {Concepts.INTEREST_INCOME: amount},
    "dividends": lambda amount: {DIV: amount, QDIV: amount},
    "otherprop": lambda amount: {DIV: amount},  # non-qualified dividends
    "ltcg": lambda amount: {CGD: amount},  # line 7a
}


@pytest.fixture(scope="module")
def taxsim_2024_eitc():
    _import_or_skip("policyengine_taxsim")
    cases = [
        Case(
            case_id=f"{column}:{amount}",
            period="2024",
            entities=(
                _person(
                    "person-1",
                    "HeadOfHousehold",
                    35,
                    **{WAGES: 5_000, **facts(amount)},
                ),
                _person("person-2", "Child", 8),
            ),
            outputs=(Concepts.EITC,),
            metadata=dict(COLORADO),
        )
        for column, facts in TAXSIM_INVESTMENT_COLUMNS.items()
        for amount in (0, TAXSIM_2024_LIMIT, TAXSIM_2024_LIMIT + 100)
    ]
    runner, prepared = _runner_and_cases("taxsim", cases)
    values = _by_concept(runner, runner.run_cases(prepared, [Concepts.EITC]))
    return {case_id: row[Concepts.EITC] for case_id, row in values.items()}


def test_taxsim_counts_every_case_line_in_its_investment_income_test(
    taxsim_2024_eitc,
) -> None:
    """Interest, line 3a (``dividends``), the rest of line 3b (``otherprop``)
    and line 7a (``ltcg``) all count, identically.

    The binary applies 26 USC 32(i) as a dollar-for-dollar reduction above
    the limit, not as the disallowance the statute and Pub. 596 state: 100
    over the limit costs 100 of credit instead of all of it. That is TAXSIM's
    model, recorded here; what this change needs is that every column the
    projection uses is inside the test.
    """
    for column in TAXSIM_INVESTMENT_COLUMNS:
        without = taxsim_2024_eitc[f"{column}:0"]
        at_limit = taxsim_2024_eitc[f"{column}:{TAXSIM_2024_LIMIT}"]
        over_limit = taxsim_2024_eitc[f"{column}:{TAXSIM_2024_LIMIT + 100}"]
        assert without > 0
        assert at_limit == pytest.approx(without)
        assert over_limit == pytest.approx(at_limit - 100)
