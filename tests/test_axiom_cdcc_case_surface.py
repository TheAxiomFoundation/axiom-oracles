"""The child and dependent care credit on the Case surface (#609).

``attach_axiom_tax_inputs`` could never produce a nonzero
``us:statutes/26/21#cdcc``: three gates each forced it to zero.

1. The claim requirements defaulted False: 26 USC 21(e)(9) ("No credit shall
   be allowed under subsection (a) for any amount paid to any person unless--
   (A) the name, address, and taxpayer identification number of such person
   are included on the return claiming the credit") and 21(e)(10) ("No credit
   shall be allowed under this section with respect to any qualifying
   individual unless the TIN of such individual is included on the return
   claiming the credit").
2. Twelve inputs the pinned 26 USC 21 module reads were never projected.
3. The liability limit ``tax_imposed_by_chapter_before_cdcc`` was a numeric
   default of 0. Section 21(a)(1) allows the credit "against the tax imposed
   by this chapter", and 26 USC 26(a) caps subpart A credits at "the
   taxpayer's regular tax liability for the taxable year reduced by the
   foreign tax credit allowable under section 27" plus "the tax imposed by
   section 55(a)". The CDCC is the first subpart A credit after the foreign
   tax credit, so its limit is the tax before credits less that credit.

The Case records none of the claim facts, so the projection assumes a
compliant filer, as the Populace bridge does
(``project_cdcc_tax_unit_inputs``): identifying information on the return, no
payment to a related individual (21(e)(6)), no legal separation (21(e)(3)) or
married-living-apart test (21(e)(4)), no noncustodial-parent rule (21(e)(5)),
and none of the 2021-only rules (21(g), 21(h)(3)). It records no self-care
fact, so only dependents under 13 qualify (21(b)(1)(A)).

Worked example (the issue's family): married filing jointly, wages 50,000 and
20,000, an 8-year-old, 4,000 of childcare. AGI 70,000 exceeds 15,000 by 28
steps of 2,000, so the applicable percentage bottoms at 35% (21(a)(2)(A)); the
21(c)(1) limit for one qualifying individual is 3,000, below both spouses'
earned income (21(d)(1)(B)), so the credit is 0.35 x 3,000 = 1,050. Taxable
income is 70,000 - 32,200 = 37,800 (Rev. Proc. 2025-32 section 4.14(1)), with
tax 2,480 + 0.12 x 13,000 = 4,040 (section 4.01 Table 1), so the limit does
not bind; with the 2,200 child tax credit (section 4.05(1)), the federal
income tax is 4,040 - 1,050 - 2,200 = 790.
"""

from __future__ import annotations

import pytest
from bridge_formula import BridgeReader, reader_for_case
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.adapters.axiom.tax_projection import (
    US_TAX_ORACLE_PROGRAM_RULES,
    attach_axiom_tax_inputs_to_case,
    attach_axiom_tax_itemization_choice_to_case,
)
from axiom_oracles.cli import _build_runner
from axiom_oracles.core.case import Case, Concepts, Entity

PROPERTY_SETTINGS = settings(max_examples=200, deadline=None, derandomize=True)
CDCC = "us:statutes/26/21#input."
TAX_UNIT_INPUTS = {
    "service_provider_identifying_information_requirement_satisfied": True,
    "qualifying_individual_tin_included_on_return": True,
    "paid_to_disallowed_related_individual": False,
    "possession_credit_or_payment_bars_united_states_credit": False,
    "cdcc_temporary_expansion_applies": False,
    "legally_separated_under_decree": False,
    "furnishes_over_half_cost_of_household": False,
    "maintains_household_principal_abode_of_qualifying_individual_more_than_half_year": False,
}
PERSON_INPUTS = (
    "is_cdcc_child_dependent",
    "is_cdcc_dependent_disregarding_listed_subsections",
    "physically_or_mentally_incapable_of_self_care",
    "same_principal_place_of_abode_more_than_half_year",
    "noncustodial_parent_exception_applies",
)
LIMIT = "tax_imposed_by_chapter_before_cdcc"


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


def _family(childcare=4_000):
    return Case(
        case_id="cdcc-family",
        period="2026",
        facts={Concepts.CHILDCARE_EXPENSES: childcare},
        entities=(
            _person("person-1", "HeadOfHousehold", 40, **{
                Concepts.YEARLY_EARNED_INCOME: 50_000,
            }),
            _person("person-2", "Spouse", 38, **{
                Concepts.YEARLY_EARNED_INCOME: 20_000,
            }),
            _person("person-3", "Child", 8),
        ),
    )


def _records(case: Case) -> dict[tuple[str, str], object]:
    projected = attach_axiom_tax_inputs_to_case(case)
    return {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }


@pytest.mark.xfail(strict=True, reason="#609: the CDCC gates zero the credit")
def test_family_gets_every_section_21_input() -> None:
    records = _records(_family())

    for name, value in TAX_UNIT_INPUTS.items():
        assert records[("tax_unit", f"{CDCC}{name}")] is value, name
    assert records[
        ("tax_unit", f"{CDCC}employment_related_expense_requirements_satisfied")
    ] is True
    assert records[("tax_unit", f"{CDCC}employment_related_expenses_paid")] == 4_000
    assert records[("tax_unit", f"{CDCC}taxpayer_earned_income_for_cdcc")] == 50_000
    assert records[("tax_unit", f"{CDCC}spouse_earned_income_for_cdcc")] == 20_000
    for person, dependent in (
        ("person-1", False),
        ("person-2", False),
        ("person-3", True),
    ):
        assert records[(person, f"{CDCC}is_cdcc_child_dependent")] is dependent
        assert records[
            (person, f"{CDCC}is_cdcc_dependent_disregarding_listed_subsections")
        ] is dependent
        assert records[
            (person, f"{CDCC}same_principal_place_of_abode_more_than_half_year")
        ] is dependent
        assert records[
            (person, f"{CDCC}physically_or_mentally_incapable_of_self_care")
        ] is False
        assert records[
            (person, f"{CDCC}noncustodial_parent_exception_applies")
        ] is False


@pytest.mark.xfail(strict=True, reason="#609: the CDCC gates zero the credit")
def test_the_liability_limit_is_computed_not_projected() -> None:
    records = _records(_family())
    assert not any(name.endswith(f"#input.{LIMIT}") for _, name in records)

    [rule] = [rule for rule in US_TAX_ORACLE_PROGRAM_RULES if rule["name"] == LIMIT]
    assert rule["kind"] == "derived" and rule["entity"] == "TaxUnit"


@pytest.mark.xfail(strict=True, reason="#609: the CDCC gates zero the credit")
@pytest.mark.parametrize(
    ("tax_before_credits", "foreign_tax_credit", "limit"),
    [
        pytest.param(4_040, 0, 4_040, id="family"),
        pytest.param(4_040, 500, 3_540, id="less-foreign-tax-credit"),
        pytest.param(300, 500, 0, id="never-negative"),
    ],
)
def test_section_26_a_limit_on_the_cdcc(
    tax_before_credits, foreign_tax_credit, limit
) -> None:
    reader = BridgeReader(
        US_TAX_ORACLE_PROGRAM_RULES,
        values={
            "income_tax_before_credits": tax_before_credits,
            "foreign_tax_credit": foreign_tax_credit,
        },
    )

    assert reader.value(LIMIT) == pytest.approx(limit)


@pytest.mark.xfail(strict=True, reason="#609: the CDCC gates zero the credit")
def test_single_parents_limit_is_their_own_earned_income() -> None:
    """21(d)(1)(A): an unmarried individual's own earned income. The spouse
    slot carries the same amount, as the Populace bridge passes it, so the
    lesser of the two slots is the taxpayer's earned income."""
    case = Case(
        case_id="cdcc-single-parent",
        period="2026",
        facts={Concepts.CHILDCARE_EXPENSES: 5_000},
        entities=(
            _person("person-1", "HeadOfHousehold", 30, **{
                Concepts.YEARLY_EARNED_INCOME: 28_000,
            }),
            _person("person-2", "Child", 4),
        ),
    )
    records = _records(case)

    assert records[("tax_unit", f"{CDCC}taxpayer_earned_income_for_cdcc")] == 28_000
    assert records[("tax_unit", f"{CDCC}spouse_earned_income_for_cdcc")] == 28_000
    assert records[
        ("tax_unit", f"{CDCC}employment_related_expense_requirements_satisfied")
    ] is True


@pytest.mark.xfail(strict=True, reason="#609: the CDCC gates zero the credit")
@PROPERTY_SETTINGS
@given(
    head_wages=st.floats(min_value=0, max_value=150_000, allow_nan=False),
    spouse_wages=st.one_of(
        st.none(), st.floats(min_value=0, max_value=150_000, allow_nan=False)
    ),
    childcare=st.one_of(
        st.just(0.0), st.floats(min_value=0, max_value=20_000, allow_nan=False)
    ),
    dependent_ages=st.lists(st.integers(min_value=0, max_value=30), max_size=3),
)
def test_section_21_inputs_for_any_household(
    head_wages, spouse_wages, childcare, dependent_ages
) -> None:
    people = [
        _person("head", "HeadOfHousehold", 40, **{
            Concepts.YEARLY_EARNED_INCOME: head_wages,
        })
    ]
    if spouse_wages is not None:
        people.append(
            _person("spouse", "Spouse", 39, **{
                Concepts.YEARLY_EARNED_INCOME: spouse_wages,
            })
        )
    for index, age in enumerate(dependent_ages):
        people.append(_person(f"child-{index}", "Child", age))
    records = _records(
        Case(
            case_id="cdcc-property",
            period="2026",
            facts={Concepts.CHILDCARE_EXPENSES: childcare},
            entities=tuple(people),
        )
    )
    earned_limit = min(
        head_wages, spouse_wages if spouse_wages is not None else head_wages
    )

    for name, value in TAX_UNIT_INPUTS.items():
        assert records[("tax_unit", f"{CDCC}{name}")] is value, name
    assert records[
        ("tax_unit", f"{CDCC}employment_related_expense_requirements_satisfied")
    ] is (childcare > 0 and earned_limit > 0)
    for person in people:
        dependent = person.entity_id.startswith("child-")
        for name in PERSON_INPUTS:
            assert (person.entity_id, f"{CDCC}{name}") in records, name
        assert records[(person.entity_id, f"{CDCC}is_cdcc_child_dependent")] is (
            dependent
        )
    assert not any(name.endswith(f"#input.{LIMIT}") for _, name in records)


@pytest.mark.xfail(strict=True, reason="#609: the CDCC gates zero the credit")
def test_case_supplied_cdcc_limit_is_rejected() -> None:
    case = Case(
        case_id="cdcc-limit-input",
        period="2026",
        metadata={"axiom_tax_unit_inputs": {LIMIT: 2_000}},
        entities=(_person("person-1", "HeadOfHousehold", 40),),
    )

    with pytest.raises(RuntimeError, match="calculator-derived aggregate inputs"):
        attach_axiom_tax_inputs_to_case(case)


def test_engine_allows_the_family_a_nonzero_credit() -> None:
    from test_axiom_tax_exempt_interest_engine import _pinned_engine

    binary, roots = _pinned_engine()
    outputs = ["us:statutes/26/21#cdcc", "us:statutes/26/6401#income_tax"]
    with pytest.MonkeyPatch.context() as env:
        env.setenv("AXIOM_RULESPEC_REPO_ROOTS", str(roots))
        env.delenv("AXIOM_RULESPEC_ROOT", raising=False)
        runner = _build_runner(
            "axiom",
            "api",
            None,
            None,
            (Concepts.CDCC, Concepts.FEDERAL_INCOME_TAX),
            axiom_engine_binary=binary,
        )
        projected = attach_axiom_tax_itemization_choice_to_case(
            attach_axiom_tax_inputs_to_case(_family())
        )
        [result] = runner.run_cases([projected], outputs)

    assert not result.errors, result.errors
    assert result.values["us:statutes/26/21#cdcc"] == pytest.approx(1_050, abs=0.01)
    assert result.values["us:statutes/26/6401#income_tax"] == pytest.approx(
        790, abs=0.01
    )


@pytest.mark.xfail(strict=True, reason="#609: the CDCC gates zero the credit")
def test_reader_reads_the_limit_from_the_projected_case() -> None:
    """On a projected Case the limit is the imported tax before credits less
    the projected foreign tax credit (0), not a projected 0."""
    projected = attach_axiom_tax_inputs_to_case(_family())
    reader = reader_for_case(
        projected,
        US_TAX_ORACLE_PROGRAM_RULES,
        values={"income_tax_before_credits": 4_040},
    )

    assert reader.value(LIMIT) == pytest.approx(4_040)
