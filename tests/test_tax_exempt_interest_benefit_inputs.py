"""Tax-exempt interest on the benefit-lane Axiom inputs (axiom-oracles#567).

Household Cases carry Concepts.TAX_EXEMPT_INTEREST_INCOME (Form 1040 line 2a)
beside the taxable Concepts.INTEREST_INCOME (line 2b). Whether a benefit
program counts it is a question of the program's own income definition, not
of 26 USC 103, which only excludes the interest from federal gross income.

Ground truth (verbatim; U.S. government works):

7 CFR 273.9(b)(2)(v) (eCFR, current 2026-10-01, fetched 2026-10-10), SNAP
unearned income: "Payments from Government-sponsored programs, dividends,
interest, royalties, and all other direct money payments from any source
which can be construed to be a gain or benefit."

42 CFR 435.603(e) (eCFR, current 2026-10-01): "MAGI-based income means income
calculated using the same financial methodologies used to determine modified
adjusted gross income as defined in section 36B(d)(2)(B) of the Code".
26 USC 36B(d)(2)(B) (govinfo, U.S. Code 2023 edition): "The term “modified
adjusted gross income” means adjusted gross income increased by— ... (ii) any
amount of interest received or accrued by the taxpayer during the taxable
year which is exempt from tax".

42 USC 1382a(b)(23) (govinfo, U.S. Code 2023 edition), SSI income
exclusions: "interest or dividend income from resources— (A) not excluded
under section 1382b(a) of this title, or (B) excluded pursuant to Federal law
other than section 1382b(a) of this title;". 20 CFR 416.1124(c)(22) (eCFR,
current 2026-10-01): "We do not count as unearned income— ... (22) Interest
and dividend income from a countable resource or from a resource excluded
under a Federal statute other than section 1613(a) of the Social Security
Act". 20 CFR 416.1124(c)(12) (same): "If you have less than $20 of unearned
income in a month and you have earned income in that month, we will use the
rest of the $20 exclusion to reduce the amount of your countable earned
income"; 20 CFR 416.1112(c) then excludes "(5) $65 of earned income in a
month" and "(7) One-half of remaining earned income in a month". Leaving
interest out of SSI unearned income makes that carry-over common, so both SSI
inputs now apply it.

Georgia TANF, PAMMS 1530 (pamms.dhs.ga.gov/dfcs/tanf/1530, effective February
2025, fetched 2026-10-10), Chart 1530.1 gives each income type a treatment,
"included (I) or excluded (E) in determining financial eligibility and benefit
amount": "Interest | UNEARNED – income received on investments. | E" and
"Dividend | UNEARNED – share of company profits received by a policyholder or
shareholder | I".

The other state rules behind the SNAP and TANF slots count interest without
regard to federal tax status; docs/tax-exempt-interest-benefit-lanes.md
quotes each with its source. No state distinguishes taxable from tax-exempt
interest.

So the invariants are:

* Every SNAP, Medicaid MAGI and TANF input (Georgia's aside) projects
  tax-exempt interest exactly as it projects the same amount of taxable
  interest.
* Georgia's TANF income input ignores interest, taxable or not, and still
  counts dividends.
* The SSI inputs ignore interest and dividends altogether, taxable or not,
  treating all of it as income from countable resources.
* SSI countable income follows the regulation's order: $240 a year off
  unearned income, the unused rest of it off earnings, then $780 and half the
  remainder; the individual and couple inputs agree.

The slot names are the income input slots of the 22 benefit programs as
compiled on 2026-10-10 (rulespec-us c13cdf7d, axiom-compose 9a514ac, engine
0c39023e; Kansas TANF has none). Each is resolved through the shipped mapping
table, first match winning, exactly as the projector does.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.adapters.axiom.populace_mapping_loader import (
    load_populace_mapping_for_program,
)
from axiom_oracles.core.case import Concepts

PROPERTY_SETTINGS = settings(max_examples=200, deadline=None, derandomize=True)

MAPPING_PATH = (
    Path(__file__).resolve().parent.parent
    / "axiom_oracles"
    / "data"
    / "populace_input_mapping.yaml"
)

# Household-scope slots where tax-exempt interest counts like taxable
# interest, with the suites whose compiled program reads them.
COUNTING_SLOTS = {
    "snap_total_monthly_unearned_income": "all ten snap-ecps suites",
    # Inputs only in compositions that do not derive them (none of the ten
    # today); kept in step with the slot above.
    "snap_gross_monthly_income": "federal-vocabulary SNAP compositions",
    "snap_monthly_household_income": "federal-vocabulary SNAP compositions",
    "countable_monthly_unearned_income": "az-snap-ecps (NA vocabulary)",
    "gross_monthly_income": "ca-snap-ecps wa-tanf-ecps",
    "gross_income": "az-snap-ecps de-tanf-ecps nc-snap-ecps",
    "ineligible_member_gross_countable_income": "nc-snap-ecps",
    "countable_unearned_income": "al-tanf-ecps co-tanf-ecps",
    "colorado_works_countable_unearned_income": "co-tanf-ecps",
    "countable_gross_unearned_income_after_disregards": "co-tanf-ecps",
    "countable_income_for_basic_cash_assistance": "co-tanf-ecps",
    "unearned_income_received_by_budgetary_unit_members": "co-tanf-ecps",
    "unearned_income_received_or_expected_by_assistance_unit_members_in_application_month": (
        "co-tanf-ecps"
    ),
    "unearned_income": "de-tanf-ecps ny-tanf-ecps",
    "countable_unearned_income_after_exclusions_and_disregards": "wa-tanf-ecps",
    "ca_countable_other_unearned_income": "ca-tanf-ecps",
    "unearned_income_in_budget_month": "mn-tanf-ecps",
    "unit_receives_no_income_other_than_mfip": "mn-tanf-ecps",
    "unit_receives_unearned_income_only": "mn-tanf-ecps",
    "unit_has_earned_income_only": "mn-tanf-ecps",
    "caretaker_relative_family_unearned_income": "az-tanf-ecps",
    "gross_countable_income": "az-tanf-ecps",
    "household_income_as_fraction_of_fpl": "medicaid-magi-co-ecps",
}

GA_TANF_SLOT = "assistance_unit_included_income"  # ga-tanf-ecps

SSI_INDIVIDUAL_SLOT = "annual_income_not_paid_on_basis_of_need"
SSI_EARNED_SLOT = "earned_income_not_excluded_by_preceding_paragraphs"
SSI_COUPLE_SLOT = (
    "individual_and_spouse_income_not_excluded_pursuant_to_section_1382a_b"
)
INTEREST_AND_DIVIDENDS = (
    Concepts.INTEREST_INCOME,
    Concepts.TAX_EXEMPT_INTEREST_INCOME,
    Concepts.DIVIDEND_INCOME,
    Concepts.QUALIFIED_DIVIDEND_INCOME,
)


def _program(inputs: list[str]) -> dict:
    return {
        "derived": [
            {
                "name": "out",
                "entity": "Household",
                "dtype": "judgment",
                "expr": {
                    "kind": "all_of",
                    "checks": [{"kind": "input", "name": name} for name in inputs],
                },
            }
        ]
    }


def _mapper(slot: str):
    mapping = load_populace_mapping_for_program(_program([slot]))
    assert slot in mapping, f"{slot} resolves to no mapping entry"
    return mapping[slot]


AMOUNT = st.integers(min_value=0, max_value=250_000)
PERSON = st.fixed_dictionaries(
    {
        Concepts.PERSON_AGE: st.integers(min_value=0, max_value=90),
        Concepts.YEARLY_EARNED_INCOME: AMOUNT,
        Concepts.SELF_EMPLOYMENT_INCOME: AMOUNT,
        Concepts.SOCIAL_SECURITY_BENEFITS: AMOUNT,
        Concepts.PENSION_INCOME: AMOUNT,
        Concepts.INTEREST_INCOME: AMOUNT,
        Concepts.DIVIDEND_INCOME: AMOUNT,
        Concepts.QUALIFIED_DIVIDEND_INCOME: AMOUNT,
        Concepts.RENTAL_INCOME: AMOUNT,
        Concepts.UNEMPLOYMENT_INSURANCE_INCOME: AMOUNT,
        Concepts.TANF_BENEFITS: AMOUNT,
        Concepts.SSI_BENEFITS: AMOUNT,
        Concepts.BLIND: st.booleans(),
        Concepts.DISABLED: st.booleans(),
    }
)
PEOPLE = st.lists(PERSON, min_size=1, max_size=5)


def _with(person: dict, **amounts) -> dict:
    return {**person, **amounts}


def _household(people: list[dict]) -> dict:
    return {"__people__": people}


@PROPERTY_SETTINGS
@given(
    slot=st.sampled_from(sorted(COUNTING_SLOTS)),
    people=PEOPLE,
    who=st.integers(min_value=0, max_value=4),
    amount=st.integers(min_value=1, max_value=900_000),
)
def test_property_tax_exempt_interest_projects_like_taxable_interest(
    slot, people, who, amount
) -> None:
    """Moving any amount of a person's interest from line 2b to line 2a
    leaves every SNAP, TANF and MAGI input unchanged: none of these programs
    looks at federal tax status, so the two must be interchangeable."""
    mapper = _mapper(slot)
    who %= len(people)
    taxable = list(people)
    taxable[who] = _with(
        people[who],
        **{Concepts.INTEREST_INCOME: people[who][Concepts.INTEREST_INCOME] + amount},
    )
    exempt = list(people)
    exempt[who] = _with(people[who], **{Concepts.TAX_EXEMPT_INTEREST_INCOME: amount})

    assert mapper(_household(exempt), None) == mapper(_household(taxable), None)


@pytest.mark.parametrize("slot", sorted(COUNTING_SLOTS))
def test_tax_exempt_interest_alone_reaches_every_counting_slot(slot) -> None:
    """A household whose only income is 12,000 a year of municipal-bond
    interest has income on every counting slot, and none on its earned
    side (the MN earned-only test fails, the unearned-only test passes)."""
    mapper = _mapper(slot)
    bonds_only = _household([{Concepts.TAX_EXEMPT_INTEREST_INCOME: 12_000}])
    nothing = _household([{}])

    expected = {
        # Monthly slots: 12,000 / 12.
        "snap_total_monthly_unearned_income": 1_000,
        "snap_gross_monthly_income": 1_000,
        "snap_monthly_household_income": 1_000,
        "countable_monthly_unearned_income": 1_000,
        "gross_monthly_income": 1_000,
        "gross_income": 1_000,
        "countable_unearned_income": 1_000,
        "colorado_works_countable_unearned_income": 1_000,
        "countable_gross_unearned_income_after_disregards": 1_000,
        "countable_income_for_basic_cash_assistance": 1_000,
        "unearned_income_received_by_budgetary_unit_members": 1_000,
        "unearned_income_received_or_expected_by_assistance_unit_members_in_application_month": 1_000,
        "unearned_income": 1_000,
        "countable_unearned_income_after_exclusions_and_disregards": 1_000,
        "ca_countable_other_unearned_income": 1_000,
        "unearned_income_in_budget_month": 1_000,
        # Annual slots (Arizona budgets in annual terms; the NC ineligible-
        # member slot resolves to the same annual entry).
        "caretaker_relative_family_unearned_income": 12_000,
        "gross_countable_income": 12_000,
        "ineligible_member_gross_countable_income": 12_000,
        # MN MFIP budgeting branches.
        "unit_receives_no_income_other_than_mfip": False,
        "unit_receives_unearned_income_only": True,
        "unit_has_earned_income_only": False,
        # 12,000 over the one-person guideline (base 15,960).
        "household_income_as_fraction_of_fpl": round(12_000 / 15_960, 6),
    }[slot]

    assert mapper(bonds_only, None) == expected
    if slot == "unit_receives_no_income_other_than_mfip":
        assert mapper(nothing, None) is True
    elif not isinstance(expected, bool):
        assert mapper(nothing, None) == 0


@PROPERTY_SETTINGS
@given(
    people=PEOPLE,
    who=st.integers(min_value=0, max_value=4),
    taxable=AMOUNT,
    exempt=AMOUNT,
)
def test_property_georgia_tanf_income_ignores_interest(
    people, who, taxable, exempt
) -> None:
    """PAMMS 1530 Chart 1530.1 excludes investment interest: no amount of
    taxable or tax-exempt interest moves Georgia's included-income input."""
    mapper = _mapper(GA_TANF_SLOT)
    who %= len(people)
    varied = list(people)
    varied[who] = _with(
        people[who],
        **{
            Concepts.INTEREST_INCOME: taxable,
            Concepts.TAX_EXEMPT_INTEREST_INCOME: exempt,
        },
    )

    assert mapper(_household(varied), None) == mapper(_household(people), None)


def test_georgia_tanf_income_still_counts_dividends_and_other_income() -> None:
    """The exclusion is the Interest row only: dividends (Chart 1530.1, I),
    earnings, Social Security and pensions still enter, 12,000 a year of
    each as 1,000 a month."""
    mapper = _mapper(GA_TANF_SLOT)
    for concept in (
        Concepts.DIVIDEND_INCOME,
        Concepts.YEARLY_EARNED_INCOME,
        Concepts.SOCIAL_SECURITY_BENEFITS,
        Concepts.PENSION_INCOME,
    ):
        assert mapper(_household([{concept: 12_000}]), None) == 1_000
    interest_only = _household(
        [
            {
                Concepts.INTEREST_INCOME: 12_000,
                Concepts.TAX_EXEMPT_INTEREST_INCOME: 12_000,
            }
        ]
    )
    assert mapper(interest_only, None) == 0


@PROPERTY_SETTINGS
@given(
    person=PERSON,
    partner=PERSON,
    changes=st.lists(
        st.tuples(st.sampled_from(INTEREST_AND_DIVIDENDS), AMOUNT),
        min_size=1,
        max_size=4,
    ),
)
def test_property_ssi_inputs_ignore_interest_and_dividends(
    person, partner, changes
) -> None:
    """42 USC 1382a(b)(23): no amount of interest or dividends, taxable or
    tax-exempt, moves either SSI income input, for an individual or for an
    eligible couple (this person plus one other aged/blind/disabled adult).
    The population cannot say which resource paid the income, so the
    projection treats all of it as coming from countable resources; income
    from a resource excluded under 1382b(a) has its own rules and is not
    modeled."""
    individual = _mapper(SSI_INDIVIDUAL_SLOT)
    couple = _mapper(SSI_COUPLE_SLOT)
    adult_partner = _with(partner, **{Concepts.PERSON_AGE: 70})
    varied = dict(person)
    for concept, amount in changes:
        varied[concept] = amount

    def couple_facts(facts):
        return {**facts, "__others__": [adult_partner]}

    assert individual({}, varied) == individual({}, person)
    assert couple({}, couple_facts(varied)) == couple({}, couple_facts(person))


def test_ssi_inputs_keep_the_unearned_income_the_law_counts() -> None:
    """The exclusion is narrow: Social Security, pensions, rent and
    unemployment compensation still reach the SSI unearned-income input
    (1382a(a)(2)), and the couple transform still applies the $240 annual
    general exclusion (1382a(b)(2)) to them."""
    individual = _mapper(SSI_INDIVIDUAL_SLOT)
    couple = _mapper(SSI_COUPLE_SLOT)
    facts = {
        Concepts.PERSON_AGE: 70,
        Concepts.SOCIAL_SECURITY_BENEFITS: 9_000,
        Concepts.PENSION_INCOME: 1_200,
        Concepts.RENTAL_INCOME: 600,
        Concepts.UNEMPLOYMENT_INSURANCE_INCOME: 0,
        Concepts.INTEREST_INCOME: 5_000,
        Concepts.TAX_EXEMPT_INTEREST_INCOME: 7_000,
        Concepts.DIVIDEND_INCOME: 3_000,
        Concepts.QUALIFIED_DIVIDEND_INCOME: 2_000,
    }
    spouse = {Concepts.PERSON_AGE: 68, Concepts.SOCIAL_SECURITY_BENEFITS: 4_000}

    assert individual({}, facts) == 9_000 + 1_200 + 600
    # Couple: (9,000 + 1,200 + 600 + 4,000) - 240, no earned income.
    assert couple({}, {**facts, "__others__": [spouse]}) == 14_800 - 240


def _ssi_countable_reference(unearned: float, earned: float) -> float:
    """Annual SSI countable income from the regulation alone (20 CFR
    416.1124(c)(12), 416.1112(c)(4), (5), (7)), with no other exclusion."""
    general = 240.0
    used_on_unearned = min(general, max(0.0, unearned))
    countable_unearned = max(0.0, unearned - used_on_unearned)
    earned_left = max(0.0, earned - (general - used_on_unearned) - 780.0)
    return countable_unearned + earned_left / 2


SSI_UNEARNED_SOURCES = (
    Concepts.SOCIAL_SECURITY_BENEFITS,
    Concepts.PENSION_INCOME,
    Concepts.RENTAL_INCOME,
    Concepts.UNEMPLOYMENT_INSURANCE_INCOME,
)


@PROPERTY_SETTINGS
@given(person=PERSON)
def test_property_ssi_inputs_apply_the_general_exclusion_in_order(person) -> None:
    """For one person, the couple input (with no eligible spouse) equals the
    regulation's countable income, and so do the individual inputs combined
    the way programs/us/ssi/fy-2026.yaml combines them: unearned less its
    share of the $240, plus the earned input less $780, halved."""
    individual_unearned = _mapper(SSI_INDIVIDUAL_SLOT)({}, person)
    individual_earned = _mapper(SSI_EARNED_SLOT)({}, person)
    couple = _mapper(SSI_COUPLE_SLOT)({}, {**person, "__others__": []})

    unearned = sum(float(person.get(c, 0)) for c in SSI_UNEARNED_SOURCES)
    earned = float(person[Concepts.YEARLY_EARNED_INCOME]) + float(
        person[Concepts.SELF_EMPLOYMENT_INCOME]
    )
    expected = _ssi_countable_reference(unearned, earned)
    program_assembly = max(
        0.0, individual_unearned - min(max(0.0, individual_unearned), 240.0)
    ) + max(0.0, individual_earned - 780.0) / 2

    assert couple == pytest.approx(expected, abs=0.01)
    assert program_assembly == pytest.approx(expected, abs=0.01)


def test_ssi_unused_general_exclusion_reduces_earnings() -> None:
    """An aged couple with 12,000 of earnings and only excluded interest:
    (12,000 - 240 - 780) / 2 = 5,490 countable. With 100 of countable
    unearned income, 140 of the exclusion is left for earnings."""
    couple = _mapper(SSI_COUPLE_SLOT)
    earned_input = _mapper(SSI_EARNED_SLOT)
    head = {
        Concepts.PERSON_AGE: 70,
        Concepts.YEARLY_EARNED_INCOME: 12_000,
        Concepts.INTEREST_INCOME: 1_200,
    }
    spouse = {Concepts.PERSON_AGE: 68}

    assert couple({}, {**head, "__others__": [spouse]}) == 5_490
    assert earned_input({}, head) == 12_000 - 240
    with_pension = {**head, Concepts.PENSION_INCOME: 100}
    assert earned_input({}, with_pension) == 12_000 - 140
    assert couple({}, {**with_pension, "__others__": [spouse]}) == (
        0 + (12_000 - 140 - 780) / 2
    )


def test_ssi_earned_input_lists_the_unearned_input_sources() -> None:
    """The carry-over reads the same unearned sources as the unearned input,
    so the two cannot drift apart."""
    by_value = {entry["match"].get("value"): entry for entry in _entries()}
    unearned_list = by_value[SSI_INDIVIDUAL_SLOT]["source"]["from_facts"]
    earned_source = by_value[SSI_EARNED_SLOT]["source"]

    assert earned_source["unearned_facts"] == unearned_list
    assert [getattr(Concepts, name) for name in unearned_list] == list(
        SSI_UNEARNED_SOURCES
    )


def _entries() -> list[dict]:
    return yaml.safe_load(MAPPING_PATH.read_text())["mappings"]


def _listed_facts(entry: dict) -> list[str]:
    source = entry.get("source") or {}
    listed = []
    for key in ("from_facts", "zero_facts"):
        for item in source.get(key) or []:
            listed.append(item if isinstance(item, str) else item.get("fact"))
    return listed


def test_every_interest_list_in_the_mapping_carries_both_lines() -> None:
    """No entry splits taxable from tax-exempt interest: a list naming one
    names the other, so a future entry cannot silently count only line 2b."""
    for entry in _entries():
        listed = set(_listed_facts(entry))
        has_taxable = "INTEREST_INCOME" in listed
        has_exempt = "TAX_EXEMPT_INTEREST_INCOME" in listed
        assert has_taxable == has_exempt, entry["match"]


def test_ssi_entry_lists_no_interest_or_dividends() -> None:
    (entry,) = [
        entry
        for entry in _entries()
        if entry["match"].get("value") == SSI_INDIVIDUAL_SLOT
    ]
    assert not {
        "INTEREST_INCOME",
        "TAX_EXEMPT_INTEREST_INCOME",
        "DIVIDEND_INCOME",
        "QUALIFIED_DIVIDEND_INCOME",
    } & set(_listed_facts(entry))
