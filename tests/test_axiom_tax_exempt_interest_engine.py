"""Tax-exempt interest through the real Axiom engine (26 USC 86, 32(i)).

Runs the composed federal oracle-bridge program on the engine and rulespec-us
roots that comparisons/fiit-taxsim-ecps.yaml pins (axiom-rules-engine
0c39023e, rulespec-us ca2d424f). It skips when that checkout is absent, as on
CI.

Ground truth: Form 1040 Instructions (2025), p. 32, "Social Security Benefits
Worksheet—Lines 6a and 6b" (Pub. 915 (2025) Worksheet 1, p. 16, has the same
steps one line lower from its line 5 on):

     1. Enter the total amount from box 5 of all your Forms SSA-1099 and
        RRB-1099. ...
     2. Multiply line 1 by 50% (0.50)
     3. Combine the amounts from Form 1040 or 1040-SR, lines 1z, 2b, 3b, 4b,
        5b, 7a, and 8
     4. Enter the amount, if any, from Form 1040 or 1040-SR, line 2a
     5. Combine lines 2, 3, and 4
     6. Enter the total of the amounts from Schedule 1, lines 11 through 20,
        and 23 and 25
     7. Is the amount on line 6 less than the amount on line 5? ... Yes.
        Subtract line 6 from line 5
     8. If you are: • Married filing jointly, enter $32,000 • Single, head of
        household, qualifying surviving spouse, or married filing separately
        and you lived apart from your spouse for all of 2025, enter $25,000
     9. Is the amount on line 8 less than the amount on line 7? ... Yes.
        Subtract line 8 from line 7
    10. Enter $12,000 if married filing jointly; $9,000 if single, head of
        household, qualifying surviving spouse, or married filing separately
        and you lived apart from your spouse for all of 2025
    11. Subtract line 10 from line 9. If zero or less, enter -0-
    12. Enter the smaller of line 9 or line 10
    13. Enter one-half of line 12
    14. Enter the smaller of line 2 or line 13
    15. Multiply line 11 by 85% (0.85). If line 11 is zero, enter -0-
    16. Add lines 14 and 15
    17. Multiply line 1 by 85% (0.85)
    18. Taxable social security benefits. Enter the smaller of line 16 or
        line 17.

Those amounts come from 26 USC 86(c) ($25,000 / $32,000 base amounts,
$34,000 / $44,000 adjusted base amounts), which carries no inflation
adjustment, so the 2025 worksheet also states the 2026 law the Case runs at.
Form 1040 (2025) line 9 ("Add lines 1z, 2b, 3b, 4b, 5b, 6b, 7a, and 8") never
adds line 2a, so AGI = line 3 + taxable benefits here (no Schedule 1
adjustments).

Example 1, single: SS 20,000; wages 10,000; taxable interest 8,000;
tax-exempt interest 10,000 (0 in the contrast column).
    line 2 = 10,000; line 3 = 18,000; line 4 = 10,000 (0)
    line 5 = 38,000 (28,000); line 7 = 38,000 (28,000)
    line 9 = 38,000 - 25,000 = 13,000 (3,000)
    line 11 = 13,000 - 9,000 = 4,000 (0)
    line 12 = min(13,000, 9,000) = 9,000 (3,000); line 13 = 4,500 (1,500)
    line 14 = min(10,000, 4,500) = 4,500 (1,500); line 15 = 3,400 (0)
    line 16 = 7,900 (1,500); line 17 = 17,000
    line 18 = 7,900 (1,500); AGI = 18,000 + 7,900 = 25,900 (19,500)

Example 2, married filing jointly: SS 30,000; taxable pension 25,000;
tax-exempt interest 12,000 (0).
    line 2 = 15,000; line 3 = 25,000; line 4 = 12,000 (0)
    line 5 = 52,000 (40,000); line 7 = 52,000 (40,000)
    line 9 = 52,000 - 32,000 = 20,000 (8,000)
    line 11 = 20,000 - 12,000 = 8,000 (0)
    line 12 = min(20,000, 12,000) = 12,000 (8,000); line 13 = 6,000 (4,000)
    line 14 = min(15,000, 6,000) = 6,000 (4,000); line 15 = 6,800 (0)
    line 16 = 12,800 (4,000); line 17 = 25,500
    line 18 = 12,800 (4,000); AGI = 25,000 + 12,800 = 37,800 (29,000)

EITC gate: Rev. Proc. 2025-32 section .06(2): "For taxable years beginning
in 2026, the earned income tax credit is not allowed under § 32(i) if the
aggregate amount of certain investment income exceeds $12,200." Pub. 596
(2025) Worksheet 1 line 2 is "any amount from Form 1040 or 1040-SR, line 2a",
so 12,200 of tax-exempt interest alone leaves a childless worker's credit
where it was without it (line 2a is not in AGI), and 12,201 removes it.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

from axiom_oracles.adapters.axiom.tax_projection import attach_axiom_tax_inputs_to_case
from axiom_oracles.cli import _build_runner
from axiom_oracles.core.case import Case, Concepts, Entity

REPO_ROOT = Path(__file__).resolve().parents[1]
PIN_SUITE = REPO_ROOT / "comparisons" / "fiit-taxsim-ecps.yaml"
TAXABLE_SOCIAL_SECURITY = (
    "us:statutes/26/86#social_security_benefits_included_in_gross_income"
)
AGI = "adjusted_gross_income"
# The axiom target of us:tax/federal-income-tax#eitc in
# axiom_oracles/config/concept_mappings.yaml, requested directly so the raw
# rule names above are not dropped by concept-id resolution.
EITC = "us:statutes/26/32#eitc"


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


def _single_social_security(tax_exempt_interest):
    return (
        _person(
            "person-1",
            "HeadOfHousehold",
            67,
            **{
                Concepts.YEARLY_EARNED_INCOME: 10_000,
                Concepts.INTEREST_INCOME: 8_000,
                Concepts.SOCIAL_SECURITY_BENEFITS: 20_000,
                Concepts.TAX_EXEMPT_INTEREST_INCOME: tax_exempt_interest,
            },
        ),
    )


def _joint_social_security(head_interest, spouse_interest, child_interest=None):
    people = [
        _person(
            "person-1",
            "HeadOfHousehold",
            70,
            **{
                Concepts.SOCIAL_SECURITY_BENEFITS: 18_000,
                Concepts.PENSION_INCOME: 25_000,
                Concepts.TAX_EXEMPT_INTEREST_INCOME: head_interest,
            },
        ),
        _person(
            "person-2",
            "Spouse",
            68,
            **{
                Concepts.SOCIAL_SECURITY_BENEFITS: 12_000,
                Concepts.TAX_EXEMPT_INTEREST_INCOME: spouse_interest,
            },
        ),
    ]
    if child_interest is not None:
        # 86(b)(2)(B) counts interest "received or accrued by the
        # taxpayer": a dependent's line 2a is not on the filers' worksheet.
        people.append(
            _person(
                "person-3",
                "Child",
                15,
                **{Concepts.TAX_EXEMPT_INTEREST_INCOME: child_interest},
            )
        )
    return tuple(people)


def _childless_worker(tax_exempt_interest):
    return (
        _person(
            "person-1",
            "HeadOfHousehold",
            30,
            **{
                Concepts.YEARLY_EARNED_INCOME: 8_000,
                Concepts.TAX_EXEMPT_INTEREST_INCOME: tax_exempt_interest,
            },
        ),
    )


CASES = {
    "single-tei-10000": _single_social_security(10_000),
    "single-tei-0": _single_social_security(0),
    "joint-tei-12000": _joint_social_security(7_000, 5_000),
    "joint-tei-12000-child-3000": _joint_social_security(7_000, 5_000, 3_000),
    "joint-tei-0": _joint_social_security(0, 0),
    "eitc-tei-0": _childless_worker(0),
    "eitc-tei-12200": _childless_worker(12_200),
    "eitc-tei-12201": _childless_worker(12_201),
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
        cases = [
            attach_axiom_tax_inputs_to_case(
                Case(case_id=case_id, period="2026", entities=people)
            )
            for case_id, people in CASES.items()
        ]
        results = runner.run_cases(cases, [TAXABLE_SOCIAL_SECURITY, AGI, EITC])
    values = {}
    for result in results:
        assert not result.errors, result.errors
        values[result.household_id] = result.values
    return values


@pytest.mark.parametrize(
    ("case_id", "taxable_social_security", "agi"),
    [
        pytest.param("single-tei-10000", 7_900, 25_900, id="example-1"),
        pytest.param("single-tei-0", 1_500, 19_500, id="example-1-without-2a"),
        pytest.param("joint-tei-12000", 12_800, 37_800, id="example-2"),
        pytest.param(
            "joint-tei-12000-child-3000",
            12_800,
            37_800,
            id="example-2-child-interest-is-not-the-filers",
        ),
        pytest.param("joint-tei-0", 4_000, 29_000, id="example-2-without-2a"),
    ],
)
def test_engine_taxable_social_security_matches_the_worksheet(
    engine_values, case_id, taxable_social_security, agi
) -> None:
    values = engine_values[case_id]
    assert values[TAXABLE_SOCIAL_SECURITY] == pytest.approx(taxable_social_security)
    assert values[AGI] == pytest.approx(agi)


def test_engine_eitc_investment_income_gate_reads_line_2a(engine_values) -> None:
    without = engine_values["eitc-tei-0"]
    at_limit = engine_values["eitc-tei-12200"]
    over_limit = engine_values["eitc-tei-12201"]

    # Line 2a never enters AGI (Form 1040 line 9).
    assert without[AGI] == at_limit[AGI] == over_limit[AGI] == pytest.approx(8_000)
    assert without[EITC] > 0
    assert at_limit[EITC] == pytest.approx(without[EITC])
    assert over_limit[EITC] == 0
