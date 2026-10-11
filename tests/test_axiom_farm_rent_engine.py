"""Farm rental income through the real Axiom engine (26 USC 61, 461(l), 199A,
32(i)).

Runs the composed federal oracle-bridge program on the engine and rulespec-us
roots that comparisons/fiit-taxsim-ecps.yaml pins (axiom-rules-engine
0c39023e, rulespec-us ca2d424f). It skips when that checkout is absent, as on
CI.

Ground truth (verbatim):

Form 4835 (2025) line 32: "Net farm rental income or (loss). ... If the
result is income, enter it here and on Schedule E (Form 1040), line 40."
Schedule E (Form 1040) 2025, line 41: "Total income or (loss). Combine lines
26, 32, 37, 39, and 40. Enter the result here and on Schedule 1 (Form 1040),
line 5". Form 1040 (2025) line 8 takes Schedule 1 line 10, and line 9 is "Add
lines 1z, 2b, 3b, 4b, 5b, 6b, 7a, and 8. This is your total income".

Example 1, single: wages 30,000 (line 1z); Form 4835 line 32 = 12,000 (0 in
the contrast). Schedule 1 line 5 = 12,000; AGI = 30,000 + 12,000 = 42,000
(30,000).

Example 2, single: wages 50,000; Form 4835 net loss 8,000. The examples
assume Form 4835 line A "Yes" (active participation), so 26 USC 469(i) allows
up to $25,000 of rental real estate loss while modified AGI is at most
$100,000, and line 34c is -8,000 (the bridge does not model 469; these inputs
keep 469 from binding). AGI = 50,000 - 8,000 = 42,000.

Example 3, joint: head wages 60,000 and farm rent 5,000; spouse farm rent
-2,000; child farm rent 4,000. The child's Schedule E is on the child's own
return, so AGI = 60,000 + 5,000 - 2,000 = 63,000, and nothing on the filers'
return (AGI, the loss deduction, QBI, the QBI deduction, taxable income) may
differ from the same household without the child's farm rent. 26 USC
199A(c)(1) makes QBI "the net amount of qualified items of income, gain,
deduction, and loss with respect to any qualified trade or business of the
taxpayer", and a joint return is one taxpayer, so the filers' QBI is 5,000 -
2,000 = 3,000. The bridge floors each person's QBI at zero before summing (as
it does for Schedule C income and Part I rents) and reports 5,000; that
existing convention is tracked in axiom-oracles#618 and pinned here as a
strict xfail.

Example 3b, head of household: wages 60,000; a 10-year-old child with farm
rent 20,000 (or -20,000). Nothing reaches the filer's return: AGI 60,000, QBI
0, and taxable income 60,000 - 24,150 = 35,850 (Rev. Proc. 2025-32 section
.14: "Heads of Households ... $24,150").

Excess business loss, 26 USC 461(l)(3)(A): the excess of "the aggregate
deductions ... attributable to trades or businesses" over "the aggregate gross
income or gain ... attributable to such trades or businesses, plus" the
threshold, determined "without regard to any deductions, gross income, or
gains attributable to any trade or business of performing services as an
employee". Form 461 (2025): "2 Enter amount from Schedule 1 (Form 1040), line
3", "5 Enter amount from Schedule 1 (Form 1040), line 5", "15 Enter $313,000
(or $626,000 if married filing jointly)" for 2025. The bridge's 2026 threshold
is its own business_loss_limit_other_2026 parameter, read from the rule below.

Example 4, single: wages 400,000; Schedule C loss 350,000; farm rent +50,000.
Treated as a trade or business (the bridge's QBI convention), the farm rent is
461(l) gross income: line 9 = -350,000 + 50,000 = -300,000, and with
threshold T the allowed loss is min(350,000, 50,000 + T). AGI = 400,000 +
50,000 - that.

Example 5, single: wages 400,000; farm rent -350,000; no business income.
AGI = 400,000 - min(350,000, T).

QBI, 26 USC 199A(a): 20 percent of qualified business income, capped at 20
percent of taxable income less net capital gain. Example 6, single: wages
60,000; farm rent 20,000; QBID = 0.20 x 20,000 = 4,000 (the cap, 0.20 x
(80,000 - 16,100) = 12,780 under the standard deduction, does not bind). With
wages 80,000 and no farm rent there is no QBI and no deduction.

Minimum deduction, 26 USC 199A(i): the deduction is "the greater of" the
regular amount "or $400" for a taxpayer "whose aggregate qualified business
income with respect to all active qualified trades or businesses ... is at
least $1,000", where an active trade or business is one "in which the
taxpayer materially participates (within the meaning of section 469(h))".
Form 4835 is for a landowner who "did not materially participate (for
self-employment tax purposes) in the operation or management of the farm".

Example 6b, single: farm rent 17,500 and nothing else. Taxable income before
the QBI deduction is 17,500 - 16,100 = 1,400 (Rev. Proc. 2025-32 section .14:
"Unmarried Individuals ... $16,100"). QBID = 0.20 x min(17,500, 1,400) = 280,
with no minimum because the farm rent is not active QBI; taxable income is
1,120. Contrast, single: Schedule C income 19,000 and nothing else. The
deductible half of SE tax is 0.5 x 0.153 x 0.9235 x 19,000 = 1,342.31, so AGI
and QBI are 17,657.69, taxable income before the deduction is 1,557.69, and
20 percent of it is 311.54; the active QBI is over $1,000, so the deduction is
the $400 minimum.

EITC, Pub. 596 (2025) Worksheet 1: "11. Enter the total of any net income
from passive activities (such as income included on Schedule E, line 26, 29a
(col. (h)), 34a (col. (d)), or 40 ...)"; "13. Combine the amounts on lines 11
and 12 of this worksheet. (If the result is less than zero, enter -0-.)";
line 5 is Form 1040 line 7a and "If the amount on that line is a loss, enter
-0-". Rev. Proc. 2025-32 section .06(2): the 2026 credit "is not allowed
under § 32(i) if the aggregate amount of certain investment income exceeds
$12,200."

Example 7, a 30-year-old with no qualifying child: earned income 1,000,
short-term capital loss 3,000, farm rent F. AGI = 1,000 - 3,000 + F, which
stays below the $10,860 2026 phase-out threshold for F up to 12,859, so the
credit is the phase-in amount 7.65% x 1,000 = 76.50 (26 USC 32(b)(1)). Line
5 is -0-, so investment income = F: 12,200 keeps the credit and 12,201 loses
it. With farm rent 13,201 and a Part I rental loss of 1,001, line 13 = 12,200
and the credit stays.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

from axiom_oracles.adapters.axiom.tax_projection import (
    US_TAX_ORACLE_PROGRAM_RULES,
    attach_axiom_tax_inputs_to_case,
    attach_axiom_tax_itemization_choice_to_case,
)
from axiom_oracles.cli import _build_runner
from axiom_oracles.core.case import Case, Concepts, Entity

REPO_ROOT = Path(__file__).resolve().parents[1]
PIN_SUITE = REPO_ROOT / "comparisons" / "fiit-taxsim-ecps.yaml"
AGI = "adjusted_gross_income"
LOSS_ALD = "loss_ald"
QBID = "qualified_business_income_deduction"
QBI = "qualified_business_income"
TAXABLE_INCOME = "us:tax/oracle-bridge#taxable_income"
# The axiom target of us:tax/federal-income-tax#eitc in
# axiom_oracles/config/concept_mappings.yaml.
EITC = "us:statutes/26/32#eitc"
(THRESHOLD_RULE,) = [
    rule
    for rule in US_TAX_ORACLE_PROGRAM_RULES
    if rule["name"] == "business_loss_limit_other_2026"
]
BRIDGE_461L_THRESHOLD = float(THRESHOLD_RULE["versions"][0]["formula"])


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


def _pinned_engine() -> tuple[Path, Path]:
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
        roots / "rulespec-us",
        str(parameters["axiom_rulespec_repo_roots_revision"]),
    ):
        pytest.skip(f"{roots}/rulespec-us is not at the pinned revision")
    return binary, roots


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


def _single(age, **facts):
    return (_person("person-1", "HeadOfHousehold", age, **facts),)


def _childless_worker(farm_rent, rental=0):
    return _single(
        30,
        **{
            Concepts.YEARLY_EARNED_INCOME: 1_000,
            Concepts.SHORT_TERM_CAPITAL_GAINS: -3_000,
            Concepts.FARM_RENT_INCOME: farm_rent,
            Concepts.RENTAL_INCOME: rental,
        },
    )


W = Concepts.YEARLY_EARNED_INCOME
F = Concepts.FARM_RENT_INCOME
SE = Concepts.SELF_EMPLOYMENT_INCOME

CASES = {
    "gross-income-12000": _single(45, **{W: 30_000, F: 12_000}),
    "gross-income-0": _single(45, **{W: 30_000}),
    "loss-8000": _single(45, **{W: 50_000, F: -8_000}),
    "joint-with-child": (
        _person("person-1", "HeadOfHousehold", 50, **{W: 60_000, F: 5_000}),
        _person("person-2", "Spouse", 48, **{F: -2_000}),
        _person("person-3", "Child", 15, **{F: 4_000}),
    ),
    "joint-child-without-farm-rent": (
        _person("person-1", "HeadOfHousehold", 50, **{W: 60_000, F: 5_000}),
        _person("person-2", "Spouse", 48, **{F: -2_000}),
        _person("person-3", "Child", 15),
    ),
    "hoh-child-farm-rent": (
        _person("person-1", "HeadOfHousehold", 40, **{W: 60_000}),
        _person("person-2", "Child", 10, **{F: 20_000}),
    ),
    "hoh-child-farm-loss": (
        _person("person-1", "HeadOfHousehold", 40, **{W: 60_000}),
        _person("person-2", "Child", 10, **{F: -20_000}),
    ),
    "hoh-child-without-farm-rent": (
        _person("person-1", "HeadOfHousehold", 40, **{W: 60_000}),
        _person("person-2", "Child", 10),
    ),
    "minimum-farm-rent-only": _single(40, **{F: 17_500}),
    "minimum-schedule-c-only": _single(40, **{SE: 19_000}),
    "ebl-farm-rent-income": _single(55, **{W: 400_000, SE: -350_000, F: 50_000}),
    "ebl-farm-rent-loss": _single(55, **{W: 400_000, F: -350_000}),
    "qbi-farm-rent": _single(40, **{W: 60_000, F: 20_000}),
    "qbi-none": _single(40, **{W: 80_000}),
    "eitc-12200": _childless_worker(12_200),
    "eitc-12201": _childless_worker(12_201),
    "eitc-netted-12200": _childless_worker(13_201, rental=-1_001),
}


@pytest.fixture(scope="module")
def engine_values() -> dict[str, dict]:
    binary, roots = _pinned_engine()
    with pytest.MonkeyPatch.context() as env:
        # The suite pin is authoritative, as in scripts/run_comparison.py.
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
        # The itemization choice lets the engine pick the standard deduction,
        # as scripts/run_comparison.py does for the tax suites.
        cases = [
            attach_axiom_tax_itemization_choice_to_case(
                attach_axiom_tax_inputs_to_case(
                    Case(case_id=case_id, period="2026", entities=people)
                )
            )
            for case_id, people in CASES.items()
        ]
        results = runner.run_cases(
            cases, [AGI, LOSS_ALD, QBI, QBID, TAXABLE_INCOME, EITC]
        )
    values = {}
    for result in results:
        assert not result.errors, result.errors
        values[result.household_id] = result.values
    return values


@pytest.mark.parametrize(
    ("case_id", "agi"),
    [
        pytest.param("gross-income-12000", 42_000, id="example-1"),
        pytest.param("gross-income-0", 30_000, id="example-1-without-line-40"),
        pytest.param("loss-8000", 42_000, id="example-2-loss"),
        pytest.param("joint-with-child", 63_000, id="example-3-child-is-not-a-filer"),
    ],
)
def test_engine_agi_takes_schedule_e_line_40(engine_values, case_id, agi) -> None:
    assert engine_values[case_id][AGI] == pytest.approx(agi)


FILERS_RETURN = (AGI, LOSS_ALD, QBI, QBID, TAXABLE_INCOME, EITC)


@pytest.mark.parametrize(
    ("with_dependent_farm_rent", "without"),
    [
        pytest.param(
            "joint-with-child", "joint-child-without-farm-rent", id="example-3"
        ),
        pytest.param(
            "hoh-child-farm-rent", "hoh-child-without-farm-rent", id="example-3b"
        ),
        pytest.param(
            "hoh-child-farm-loss",
            "hoh-child-without-farm-rent",
            id="example-3b-loss",
        ),
    ],
)
def test_engine_dependents_farm_rent_reaches_nothing_on_the_filers_return(
    engine_values, with_dependent_farm_rent, without
) -> None:
    for output in FILERS_RETURN:
        assert engine_values[with_dependent_farm_rent][output] == pytest.approx(
            engine_values[without][output]
        ), output


def test_engine_head_of_household_with_a_childs_farm_rent(engine_values) -> None:
    values = engine_values["hoh-child-farm-rent"]

    assert values[AGI] == pytest.approx(60_000)
    assert values[QBI] == 0
    assert values[QBID] == 0
    assert values[TAXABLE_INCOME] == pytest.approx(60_000 - 24_150)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "the bridge floors each person's QBI before summing, so a spouse's "
        "loss does not reduce the other spouse's QBI (axiom-oracles#618)"
    ),
)
def test_engine_joint_qbi_nets_the_spouses_farm_rent(engine_values) -> None:
    assert engine_values["joint-with-child"][QBI] == pytest.approx(5_000 - 2_000)


def test_engine_farm_rent_alone_does_not_earn_the_199a_i_minimum(engine_values) -> None:
    farm_rent = engine_values["minimum-farm-rent-only"]
    schedule_c = engine_values["minimum-schedule-c-only"]

    assert farm_rent[AGI] == pytest.approx(17_500)
    assert farm_rent[QBI] == pytest.approx(17_500)
    assert farm_rent[QBID] == pytest.approx(0.20 * (17_500 - 16_100))
    assert farm_rent[TAXABLE_INCOME] == pytest.approx(1_120)

    assert schedule_c[AGI] == pytest.approx(17_657.69, abs=0.01)
    assert 0.20 * (schedule_c[AGI] - 16_100) < 400
    assert schedule_c[QBID] == pytest.approx(400)


def test_engine_positive_farm_rent_raises_the_461l_allowance(engine_values) -> None:
    allowed = min(350_000, 50_000 + BRIDGE_461L_THRESHOLD)
    values = engine_values["ebl-farm-rent-income"]

    assert values[LOSS_ALD] == pytest.approx(allowed)
    assert values[AGI] == pytest.approx(400_000 + 50_000 - allowed)


def test_engine_farm_rent_loss_is_a_461l_business_loss(engine_values) -> None:
    allowed = min(350_000, BRIDGE_461L_THRESHOLD)
    values = engine_values["ebl-farm-rent-loss"]

    assert allowed < 350_000  # the cap binds
    assert values[LOSS_ALD] == pytest.approx(allowed)
    assert values[AGI] == pytest.approx(400_000 - allowed)


def test_engine_farm_rent_is_qualified_business_income(engine_values) -> None:
    with_farm_rent = engine_values["qbi-farm-rent"]
    without = engine_values["qbi-none"]

    assert with_farm_rent[AGI] == without[AGI] == pytest.approx(80_000)
    assert with_farm_rent[QBI] == pytest.approx(20_000)
    assert with_farm_rent[QBID] == pytest.approx(0.20 * 20_000)
    assert with_farm_rent[TAXABLE_INCOME] == pytest.approx(80_000 - 16_100 - 4_000)
    assert without[QBI] == 0
    assert without[QBID] == 0


@pytest.mark.parametrize(
    ("case_id", "agi", "eitc"),
    [
        pytest.param("eitc-12200", 10_200, 76.50, id="at-the-limit"),
        pytest.param("eitc-12201", 10_201, 0, id="one-dollar-over"),
        pytest.param(
            "eitc-netted-12200",
            10_200,
            76.50,
            id="part-i-loss-nets-in-line-13",
        ),
    ],
)
def test_engine_eitc_investment_income_reads_schedule_e_line_40(
    engine_values, case_id, agi, eitc
) -> None:
    values = engine_values[case_id]
    assert values[AGI] == pytest.approx(agi)
    assert values[EITC] == pytest.approx(eitc)
