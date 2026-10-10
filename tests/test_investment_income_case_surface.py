"""Dividends and Form 1040 line 7a on the Case: one household for every engine.

Ground truth, Form 1040 (2025) and its instructions (i1040gi.pdf, IRS
revision posted 2026-02-27, sha256 482e9c48...; f1040.pdf sha256 3d31c226...):

Form 1040 (2025), lines 3a-3b and 7a-7b:

    3a Qualified dividends . . . 3a        b Ordinary dividends . . . 3b
    7a Capital gain or (loss). Attach Schedule D if required . . . 7a
     b Check if: [ ] Schedule D not required [ ] Includes child's capital
       gain or (loss)

Instructions, "Line 3a, Qualified Dividends" (p. 25):

    Enter your total qualified dividends on line 3a. Qualified dividends are
    also included in the ordinary dividend total required to be shown on
    line 3b. Qualified dividends are eligible for a lower tax rate than other
    ordinary income. Generally, these dividends are shown in box 1b of
    Form(s) 1099-DIV.

Instructions, "Line 3b, Ordinary Dividends" (p. 26):

    Each payer should send you a Form 1099-DIV. Enter your total ordinary
    dividends on line 3b. This amount should be shown in box 1a of Form(s)
    1099-DIV.

Instructions, "Line 7a, Capital Gain or (Loss)" (pp. 31, 33):

    Exception 1. You don't have to file Form 8949 or Schedule D if you aren't
    deferring any capital gain by investing in a qualified opportunity fund
    and both of the following apply.
    1. You have no capital losses, and your only capital gains are capital
    gain distributions from Form(s) 1099-DIV, box 2a (or substitute
    statements); and
    2. None of the Form(s) 1099-DIV (or substitute statements) have an amount
    in box 2b (unrecaptured section 1250 gain), box 2c (section 1202 gain),
    or box 2d (collectibles (28%) gain).
    Exception 2. You must file Schedule D but generally don't have to file
    Form 8949 if Exception 1 doesn't apply, ... and your only capital gains
    and losses are:
    • Capital gain distributions; ...
    If Exception 1 applies, enter your total capital gain distributions (from
    box 2a of Form(s) 1099-DIV) on line 7a and check the box "Schedule D not
    required" on line 7b.

Where the lines flow:

- Social Security Benefits Worksheet, line 3 (p. 32): "Combine the amounts
  from Form 1040 or 1040-SR, lines 1z, 2b, 3b, 4b, 5b, 7a, and 8": line 3b and
  line 7a are total income; line 3a is not added again.
- Qualified Dividends and Capital Gain Tax Worksheet (p. 38): line 2 "Enter
  the amount from Form 1040 or 1040-SR, line 3a"; line 3 "Are you filing
  Schedule D? ... No. Enter the amount from Form 1040 or 1040-SR, line 7a."
- Pub. 596 (2025) Worksheet 1, Investment Income (p. 7): line 3 "Enter any
  amount from Form 1040 or 1040-SR, line 3b"; line 5 "Enter the amount from
  Form 1040 or 1040-SR, line 7a. If the amount on that line is a loss, enter
  -0-".
- Instructions for Form 8960 (2024), line 5a: combine "Form 1040 or 1040-SR,
  line 7, and Schedule 1 (Form 1040), line 4" (net investment income).
- 26 USC 852(b)(3)(B): "A capital gain dividend shall be treated by the
  shareholders as a gain from the sale or exchange of a capital asset held
  for more than 1 year."

So on the Case: DIVIDEND_INCOME is line 3b and includes QUALIFIED_DIVIDEND_INCOME
(line 3a); NON_SCHEDULE_D_CAPITAL_GAIN_DISTRIBUTIONS is line 7a on the
no-Schedule-D path, a long-term gain disjoint from the Schedule D concepts.

Invariants (property-tested, derandomized):

1. Every engine projection sees the same filer line 3b, line 3a and line 7a,
   decoded from its own input representation (PolicyEngine person inputs,
   TAXSIM dividends/otherprop/ltcg, Tax-Calculator e00600/e00650/e01100, the
   Axiom bridge inputs, the Axiom benefit mapping), on any Case, including
   ones that violate line 3a <= line 3b or carry negative amounts.
2. In every view: 0 <= qualified <= ordinary; PolicyEngine's dividend_income
   alias equals qualified + non-qualified for every person.
3. Raising line 7a by d moves exactly the line 7a inputs, each by d.
4. Moving d from non-qualified to qualified at fixed line 3b moves only the
   qualified inputs (+d) and their non-qualified complements (-d); nothing
   that feeds AGI moves.
5. A dependent's dividends and line 7a never reach the filers' TAXSIM row,
   Tax-Calculator row, or the Axiom filer sums.
6. The producer fold conserves each tax unit's long-term gain plus line 7a,
   is idempotent, and leaves no tax unit with both line 7a and Schedule D
   amounts.
7. No benefit income list sums QUALIFIED_DIVIDEND_INCOME beside
   DIVIDEND_INCOME (that would count line 3a twice).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.adapters.axiom.generic_inputs import attach_generic_inputs
from axiom_oracles.adapters.axiom.tax_projection import (
    US_TAX_ORACLE_BRIDGE_TARGET,
    attach_axiom_tax_inputs_to_case,
)
from axiom_oracles.adapters.policyengine.runner import (
    PolicyEngineRunner,
    _person_income_inputs,
)
from axiom_oracles.adapters.taxcalc.projection import taxcalc_input_for_case
from axiom_oracles.adapters.taxsim.projection import taxsim_input_for_case
from axiom_oracles.core.case import Case, Concepts, Entity
from axiom_oracles.core.investment_income import (
    Dividends,
    fold_capital_gain_distributions_into_schedule_d,
    normalized_investment_income_facts,
    person_dividends,
    person_non_schedule_d_capital_gain_distributions,
    sum_dividends,
)

PROPERTY_SETTINGS = settings(max_examples=300, deadline=None, derandomize=True)
REPO_ROOT = Path(__file__).resolve().parents[1]
MAPPING_YAML = REPO_ROOT / "axiom_oracles" / "data" / "populace_input_mapping.yaml"

DIV = Concepts.DIVIDEND_INCOME
QDIV = Concepts.QUALIFIED_DIVIDEND_INCOME
CGD = Concepts.NON_SCHEDULE_D_CAPITAL_GAIN_DISTRIBUTIONS
STCG = Concepts.SHORT_TERM_CAPITAL_GAINS
LTCG = Concepts.LONG_TERM_CAPITAL_GAINS
RENT = Concepts.RENTAL_INCOME
BRIDGE = US_TAX_ORACLE_BRIDGE_TARGET


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


def _case(*people, case_id="investment-income"):
    return Case(
        case_id=case_id,
        period="2026",
        entities=tuple(people),
        metadata={"state": "CO"},
    )


# ---------------------------------------------------------------------------
# The shared semantics.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        pytest.param({DIV: 5_000, QDIV: 3_000}, Dividends(5_000, 3_000), id="3a-in-3b"),
        pytest.param({DIV: 5_000}, Dividends(5_000, 0), id="ordinary-only"),
        # A qualified-only row is all-qualified ordinary dividends.
        pytest.param({QDIV: 2_000}, Dividends(2_000, 2_000), id="qualified-only"),
        # Line 3a above line 3b is impossible on a return; read as 3b = 3a.
        pytest.param({DIV: 100, QDIV: 250}, Dividends(250, 250), id="3a-above-3b"),
        pytest.param({DIV: -400, QDIV: -50}, Dividends(0, 0), id="negatives"),
        pytest.param({DIV: None, QDIV: ""}, Dividends(0, 0), id="blank"),
        pytest.param({}, Dividends(0, 0), id="absent"),
    ],
)
def test_person_dividends_reads_lines_3b_and_3a(facts, expected) -> None:
    assert person_dividends(facts) == expected
    assert person_dividends(Entity("p", "person", facts=facts)) == expected


def test_dividends_reject_non_finite_facts() -> None:
    with pytest.raises(ValueError, match="finite"):
        person_dividends({DIV: float("nan")})
    with pytest.raises(ValueError, match="finite"):
        person_non_schedule_d_capital_gain_distributions({CGD: float("inf")})


def test_line_7a_distributions_are_never_negative() -> None:
    assert person_non_schedule_d_capital_gain_distributions({CGD: 1_250}) == 1_250
    assert person_non_schedule_d_capital_gain_distributions({CGD: -10}) == 0
    assert person_non_schedule_d_capital_gain_distributions({}) == 0


def test_normalized_facts_keep_absent_facts_absent() -> None:
    assert normalized_investment_income_facts({RENT: 10}) == {RENT: 10}
    assert normalized_investment_income_facts({QDIV: 300, CGD: -5}) == {
        DIV: 300,
        QDIV: 300,
        CGD: 0,
    }


@pytest.mark.parametrize(
    ("members", "folded", "expected"),
    [
        pytest.param(
            [{CGD: 2_000}],
            0,
            [{CGD: 2_000}],
            id="exception-1-holds",
        ),
        pytest.param(
            [{CGD: 2_000, LTCG: 5_000}],
            1,
            [{LTCG: 7_000}],
            id="schedule-d-required",
        ),
        pytest.param(
            [{CGD: 2_000, STCG: -1_000}],
            1,
            [{STCG: -1_000, LTCG: 2_000}],
            id="a-capital-loss-requires-schedule-d",
        ),
        # A joint return files one Schedule D: the spouse's gain moves the
        # head's distributions onto it.
        pytest.param(
            [{CGD: 2_000}, {LTCG: 500}],
            1,
            [{LTCG: 2_000}, {LTCG: 500}],
            id="joint-return",
        ),
        # Zero-valued Schedule D facts are not Schedule D amounts.
        pytest.param(
            [{CGD: 2_000, LTCG: 0, STCG: 0}],
            0,
            [{CGD: 2_000, LTCG: 0, STCG: 0}],
            id="zero-schedule-d-facts",
        ),
    ],
)
def test_fold_applies_form_1040_line_7_exception_1(members, folded, expected) -> None:
    assert fold_capital_gain_distributions_into_schedule_d(members) == folded
    assert members == expected


# ---------------------------------------------------------------------------
# Decoders: each engine's input representation back to the Form 1040 lines.
# ---------------------------------------------------------------------------


def _relation(entity):
    return entity.fact(Concepts.HOUSEHOLD_RELATION)


def _filers(case):
    return [
        person
        for person in case.entities
        if _relation(person) in {"HeadOfHousehold", "Spouse"}
    ]


def _policyengine_view(case, people):
    inputs = [_person_income_inputs(person) for person in people]
    return {
        "ordinary": sum(row["dividend_income"] for row in inputs),
        "qualified": sum(row["qualified_dividend_income"] for row in inputs),
        "non_qualified": sum(row["non_qualified_dividend_income"] for row in inputs),
        "line_7a": sum(row["non_sch_d_capital_gains"] for row in inputs),
    }


def _taxsim_view(case):
    row = taxsim_input_for_case(case)
    rental = sum(float(p.fact(RENT, 0) or 0) for p in _filers(case))
    long_term = sum(float(p.fact(LTCG, 0) or 0) for p in _filers(case))
    return {
        "ordinary": row["dividends"] + (row["otherprop"] - rental),
        "qualified": row["dividends"],
        "non_qualified": row["otherprop"] - rental,
        "line_7a": row["ltcg"] - long_term,
    }


def _taxcalc_view(case):
    row = taxcalc_input_for_case(case)
    return {
        "ordinary": row["e00600"],
        "qualified": row["e00650"],
        "non_qualified": row["e00600"] - row["e00650"],
        "line_7a": row["e01100"],
    }


def _axiom_records(case):
    projected = attach_axiom_tax_inputs_to_case(case)
    return {
        (record["entity_id"], record["name"]): record["value"]
        for record in projected.metadata["axiom_input_records"]
    }


def _axiom_filer_view(case):
    records = _axiom_records(case)
    return {
        "ordinary": records[("tax_unit", f"{BRIDGE}#input.filer_dividend_income")],
        "line_7a": records[
            ("tax_unit", f"{BRIDGE}#input.filer_non_sch_d_capital_gains")
        ],
    }


def _reference(people):
    """Form 1040 lines read straight off the facts: an independent statement
    of the normalization the module docstring gives."""

    def number(person, concept):
        value = person.fact(concept, 0)
        return float(value) if value not in (None, "") else 0.0

    qualified = sum(max(0.0, number(p, QDIV)) for p in people)
    ordinary = sum(max(0.0, number(p, DIV), number(p, QDIV)) for p in people)
    return {
        "ordinary": ordinary,
        "qualified": qualified,
        "non_qualified": ordinary - qualified,
        "line_7a": sum(max(0.0, number(p, CGD)) for p in people),
    }


# ---------------------------------------------------------------------------
# A worked household through every projection.
# ---------------------------------------------------------------------------

WORKED = _case(
    _person(
        "person-1",
        "HeadOfHousehold",
        40,
        **{
            Concepts.YEARLY_EARNED_INCOME: 60_000,
            DIV: 5_000,
            QDIV: 3_000,
            CGD: 2_000,
            RENT: 1_000,
        },
    ),
    # The child's dividends are hers, not the filer's (no Form 8814 here).
    _person("person-2", "Child", 10, **{DIV: 700, QDIV: 700, CGD: 300}),
)


def test_worked_household_policyengine_inputs() -> None:
    head = _person_income_inputs(WORKED.entities[0])
    assert head["dividend_income"] == 5_000
    assert head["qualified_dividend_income"] == 3_000
    assert head["non_qualified_dividend_income"] == 2_000
    assert head["non_sch_d_capital_gains"] == 2_000
    situation = PolicyEngineRunner()._build_situation_from_case(WORKED)
    person = situation["people"]["person-1"]
    assert person["dividend_income"] == {2026: 5_000}
    assert person["non_qualified_dividend_income"] == {2026: 2_000}
    assert person["non_sch_d_capital_gains"] == {2026: 2_000}


def test_worked_household_taxsim_row() -> None:
    row = taxsim_input_for_case(WORKED)
    assert row["dividends"] == 3_000  # line 3a
    assert row["otherprop"] == 1_000 + 2_000  # rent + non-qualified
    assert row["ltcg"] == 2_000  # line 7a, long-term (852(b)(3)(B))
    assert row["stcg"] == 0


def test_worked_household_taxcalc_row() -> None:
    row = taxcalc_input_for_case(WORKED)
    assert row["e00600"] == 5_000
    assert row["e00650"] == 3_000
    assert row["e01100"] == 2_000
    assert row["p23250"] == 0


def test_worked_household_axiom_inputs() -> None:
    records = _axiom_records(WORKED)
    assert records[("tax_unit", f"{BRIDGE}#input.filer_dividend_income")] == 5_000
    assert (
        records[("tax_unit", f"{BRIDGE}#input.filer_non_sch_d_capital_gains")] == 2_000
    )
    # The worksheet leaves sum every member, as PolicyEngine's
    # add(tax_unit, ...) does.
    assert records[("tax_unit", f"{BRIDGE}#input.non_sch_d_capital_gains")] == 2_300
    assert (
        records[
            ("tax_unit", f"{BRIDGE}#input.capital_gains_tax_qualified_dividend_income")
        ]
        == 3_700
    )
    assert (
        records[("tax_unit", "us:statutes/26/1/h#input.long_term_capital_gains")]
        == 2_300
    )
    assert (
        records[("tax_unit", "us:statutes/26/1/h#input.qualified_dividend_income")]
        == 3_700
    )
    assert records[("person-1", f"{BRIDGE}#input.person_dividend_income")] == 5_000
    assert (
        records[("person-1", f"{BRIDGE}#input.person_non_sch_d_capital_gains")] == 2_000
    )
    assert (
        records[("person-2", f"{BRIDGE}#input.person_non_sch_d_capital_gains")] == 300
    )
    # Pub. 596 Worksheet 1: line 3 (3b) 5,000 + line 5 (7a) 2,000 + passive
    # rent 1,000; the child's amounts are not the filer's.
    assert (
        records[
            (
                "tax_unit",
                "us:tax/federal-income-tax#input.eitc_relevant_investment_income",
            )
        ]
        == 8_000
    )


def test_worked_household_benefit_mapping_reads_line_3b_once(tmp_path) -> None:
    compiled = {
        "program": {
            "derived": [
                {
                    "name": "gross_income_test",
                    "entity": "Household",
                    "expr": {
                        "kind": "add",
                        "items": [
                            {
                                "kind": "input",
                                "name": "us:test/benefit#input.snap_gross_monthly_income",
                            }
                        ],
                    },
                }
            ]
        }
    }
    compiled_path = tmp_path / "benefit.compiled.json"
    compiled_path.write_text(json.dumps(compiled))
    [projected] = attach_generic_inputs([WORKED], compiled_program_path=compiled_path)
    [record] = [
        item
        for item in projected.metadata["axiom_input_records"]
        if item["name"].endswith("#input.snap_gross_monthly_income")
    ]
    # Earned 60,000 + rent 1,000 + line 3b (5,000 + the child's 700), counted
    # once (not 5,000 + 3,000 + 700 + 700), monthly.
    assert float(record["value"]["value"]) == pytest.approx(66_700 / 12, abs=0.01)


# ---------------------------------------------------------------------------
# Properties.
# ---------------------------------------------------------------------------

AMOUNT = st.integers(min_value=-2_000, max_value=80_000)
NON_NEGATIVE = st.integers(min_value=0, max_value=80_000)
OPTIONAL = st.none() | AMOUNT


@st.composite
def _income_facts(draw):
    facts = {}
    for concept, strategy in (
        (DIV, OPTIONAL),
        (QDIV, OPTIONAL),
        (CGD, OPTIONAL),
        (STCG, st.none() | st.integers(-30_000, 30_000)),
        (LTCG, st.none() | st.integers(-30_000, 80_000)),
        (RENT, st.none() | st.integers(-10_000, 30_000)),
        (Concepts.YEARLY_EARNED_INCOME, st.none() | NON_NEGATIVE),
    ):
        value = draw(strategy)
        if value is not None:
            facts[concept] = value
    return facts


@st.composite
def _tax_unit_cases(draw):
    people = [_person("person-1", "HeadOfHousehold", 45, **draw(_income_facts()))]
    if draw(st.booleans()):
        people.append(_person("person-2", "Spouse", 43, **draw(_income_facts())))
    for index in range(draw(st.integers(0, 2))):
        people.append(
            _person(f"child-{index}", "Child", 7 + index, **draw(_income_facts()))
        )
    return _case(*people)


def _approx(view):
    return {key: pytest.approx(value, abs=1e-6) for key, value in view.items()}


@PROPERTY_SETTINGS
@given(case=_tax_unit_cases())
def test_property_every_engine_sees_the_same_filer_lines(case) -> None:
    filers = _filers(case)
    reference = _reference(filers)
    assert _policyengine_view(case, filers) == _approx(reference)
    assert _taxsim_view(case) == _approx(reference)
    assert _taxcalc_view(case) == _approx(reference)
    axiom = _axiom_filer_view(case)
    assert axiom == _approx({k: reference[k] for k in axiom})


@PROPERTY_SETTINGS
@given(case=_tax_unit_cases())
def test_property_member_sums_agree_where_engines_sum_every_member(case) -> None:
    people = list(case.entities)
    reference = _reference(people)
    pe = _policyengine_view(case, people)
    records = _axiom_records(case)
    assert records[
        ("tax_unit", f"{BRIDGE}#input.non_sch_d_capital_gains")
    ] == pytest.approx(pe["line_7a"])
    assert records[
        ("tax_unit", f"{BRIDGE}#input.capital_gains_tax_qualified_dividend_income")
    ] == pytest.approx(pe["qualified"])
    assert records[
        ("tax_unit", "us:statutes/26/1411#input.dividend_income")
    ] == pytest.approx(reference["ordinary"])
    long_term = sum(float(p.fact(LTCG, 0) or 0) for p in people)
    assert records[
        ("tax_unit", "us:statutes/26/1/h#input.long_term_capital_gains")
    ] == pytest.approx(long_term + reference["line_7a"])
    for person in people:
        assert records[
            (person.entity_id, f"{BRIDGE}#input.person_dividend_income")
        ] == pytest.approx(_reference([person])["ordinary"])


@PROPERTY_SETTINGS
@given(case=_tax_unit_cases())
def test_property_policyengine_alias_equals_its_parts(case) -> None:
    for person in case.entities:
        row = _person_income_inputs(person)
        assert 0 <= row["qualified_dividend_income"] <= row["dividend_income"]
        assert row["non_qualified_dividend_income"] >= 0
        assert row["dividend_income"] == pytest.approx(
            row["qualified_dividend_income"] + row["non_qualified_dividend_income"]
        )
        assert row["non_sch_d_capital_gains"] >= 0


def _with_fact(case, entity_id, concept, value):
    return _case(
        *(
            Entity(p.entity_id, p.kind, facts={**p.facts, concept: value})
            if p.entity_id == entity_id
            else p
            for p in case.entities
        )
    )


def _changed(before, after):
    return {
        key: (before.get(key), after.get(key))
        for key in set(before) | set(after)
        if before.get(key) != after.get(key)
    }


@PROPERTY_SETTINGS
@given(
    case=_tax_unit_cases(),
    bump=st.integers(min_value=1, max_value=40_000),
    spouse=st.booleans(),
)
def test_property_line_7a_moves_exactly_its_inputs(case, bump, spouse) -> None:
    filers = _filers(case)
    person = filers[-1] if spouse else filers[0]
    current = person_non_schedule_d_capital_gain_distributions(person)
    bumped = _with_fact(case, person.entity_id, CGD, current + bump)

    taxsim = _changed(taxsim_input_for_case(case), taxsim_input_for_case(bumped))
    assert set(taxsim) == {"ltcg"}
    assert taxsim["ltcg"][1] - taxsim["ltcg"][0] == pytest.approx(bump)

    taxcalc = _changed(taxcalc_input_for_case(case), taxcalc_input_for_case(bumped))
    assert set(taxcalc) == {"e01100"}
    assert taxcalc["e01100"][1] - taxcalc["e01100"][0] == pytest.approx(bump)

    pe = _changed(
        _person_income_inputs(person),
        _person_income_inputs(bumped.entities[case.entities.index(person)]),
    )
    assert set(pe) == {"non_sch_d_capital_gains"}

    axiom = _changed(_axiom_records(case), _axiom_records(bumped))
    exact = {
        ("tax_unit", f"{BRIDGE}#input.non_sch_d_capital_gains"),
        ("tax_unit", f"{BRIDGE}#input.filer_non_sch_d_capital_gains"),
        ("tax_unit", "us:statutes/26/1/h#input.long_term_capital_gains"),
        ("tax_unit", "us:tax/federal-income-tax#input.long_term_capital_gains"),
        (person.entity_id, f"{BRIDGE}#input.person_non_sch_d_capital_gains"),
    }
    eitc = (
        "tax_unit",
        "us:tax/federal-income-tax#input.eitc_relevant_investment_income",
    )
    assert exact <= set(axiom) <= exact | {eitc}
    for key in exact:
        assert axiom[key][1] - axiom[key][0] == pytest.approx(bump)
    if eitc in axiom:
        # Worksheet 1 line 5 floors a loss at zero, so line 7a can raise
        # line 14 by less than the bump, never by more.
        assert 0 < axiom[eitc][1] - axiom[eitc][0] <= bump + 1e-6


@PROPERTY_SETTINGS
@given(case=_tax_unit_cases(), share=st.floats(min_value=0, max_value=1))
def test_property_qualified_share_never_moves_agi_inputs(case, share) -> None:
    head = _filers(case)[0]
    dividends = person_dividends(head)
    shift = round(dividends.non_qualified * share, 2)
    if shift <= 0:
        return
    shifted = _with_fact(
        _with_fact(case, head.entity_id, DIV, dividends.ordinary),
        head.entity_id,
        QDIV,
        dividends.qualified + shift,
    )
    base = _with_fact(
        _with_fact(case, head.entity_id, DIV, dividends.ordinary),
        head.entity_id,
        QDIV,
        dividends.qualified,
    )

    taxsim = _changed(taxsim_input_for_case(base), taxsim_input_for_case(shifted))
    assert set(taxsim) == {"dividends", "otherprop"}
    assert taxsim["dividends"][1] - taxsim["dividends"][0] == pytest.approx(shift)
    assert taxsim["otherprop"][1] - taxsim["otherprop"][0] == pytest.approx(-shift)

    taxcalc = _changed(taxcalc_input_for_case(base), taxcalc_input_for_case(shifted))
    assert set(taxcalc) == {"e00650"}

    pe = _changed(
        _person_income_inputs(base.entities[0]),
        _person_income_inputs(shifted.entities[0]),
    )
    assert set(pe) == {"qualified_dividend_income", "non_qualified_dividend_income"}

    axiom = _changed(_axiom_records(base), _axiom_records(shifted))
    assert set(axiom) == {
        ("tax_unit", f"{BRIDGE}#input.capital_gains_tax_qualified_dividend_income"),
        ("tax_unit", "us:tax/federal-income-tax#input.qualified_dividend_income"),
        ("tax_unit", "us:statutes/26/1/h#input.qualified_dividend_income"),
    }


@PROPERTY_SETTINGS
@given(case=_tax_unit_cases(), child=_income_facts())
def test_property_dependent_income_never_reaches_filer_rows(case, child) -> None:
    # Children under 19 so the head-of-household dependent test cannot move.
    child_facts = {k: v for k, v in child.items() if k != Concepts.YEARLY_EARNED_INCOME}
    with_child = _case(
        *case.entities, _person("extra-child", "Child", 12, **child_facts)
    )
    without_child = _case(*case.entities, _person("extra-child", "Child", 12))

    taxsim = _changed(
        taxsim_input_for_case(without_child), taxsim_input_for_case(with_child)
    )
    assert not taxsim
    taxcalc = _changed(
        taxcalc_input_for_case(without_child), taxcalc_input_for_case(with_child)
    )
    assert not taxcalc
    assert _axiom_filer_view(without_child) == _axiom_filer_view(with_child)


@PROPERTY_SETTINGS
@given(case=_tax_unit_cases())
def test_property_benefit_mapping_reads_what_policyengine_reads(case) -> None:
    for person in case.entities:
        normalized = normalized_investment_income_facts(person.facts)
        pe = _person_income_inputs(person)
        assert float(normalized.get(DIV, 0)) == pytest.approx(pe["dividend_income"])
        assert float(normalized.get(QDIV, 0)) == pytest.approx(
            pe["qualified_dividend_income"]
        )


MEMBER = st.fixed_dictionaries(
    {},
    optional={
        CGD: st.integers(0, 40_000),
        STCG: st.integers(-20_000, 20_000),
        LTCG: st.integers(-20_000, 60_000),
    },
)


@PROPERTY_SETTINGS
@given(members=st.lists(MEMBER, min_size=1, max_size=4))
def test_property_fold_conserves_and_is_idempotent(members) -> None:
    members = [dict(member) for member in members]

    def long_term_plus_7a(rows):
        return sum(row.get(LTCG, 0) + row.get(CGD, 0) for row in rows)

    before = long_term_plus_7a(members)
    files_schedule_d = any(row.get(STCG) or row.get(LTCG) for row in members)
    original = [dict(row) for row in members]
    fold_capital_gain_distributions_into_schedule_d(members)

    assert long_term_plus_7a(members) == before
    if files_schedule_d:
        assert not any(CGD in row for row in members)
    else:
        assert members == original
    once = [dict(row) for row in members]
    assert fold_capital_gain_distributions_into_schedule_d(members) == 0
    assert members == once


def test_sum_dividends_adds_people() -> None:
    assert sum_dividends([{DIV: 5_000, QDIV: 3_000}, {QDIV: 200}]) == Dividends(
        5_200, 3_200
    )


# ---------------------------------------------------------------------------
# The benefit mapping counts line 3a once.
# ---------------------------------------------------------------------------


def _from_facts_lists(node):
    if isinstance(node, dict):
        source = node.get("source")
        if isinstance(source, dict) and "from_facts" in source:
            yield (
                node.get("match"),
                [
                    entry["fact"] if isinstance(entry, dict) else entry
                    for entry in source["from_facts"]
                ],
            )
        for value in node.values():
            yield from _from_facts_lists(value)
    elif isinstance(node, list):
        for item in node:
            yield from _from_facts_lists(item)


def test_no_benefit_income_list_counts_qualified_dividends_twice() -> None:
    table = yaml.safe_load(MAPPING_YAML.read_text())
    lists = list(_from_facts_lists(table))
    assert any("DIVIDEND_INCOME" in facts for _, facts in lists)
    offenders = [
        match
        for match, facts in lists
        if "QUALIFIED_DIVIDEND_INCOME" in facts and "DIVIDEND_INCOME" in facts
    ]
    assert not offenders, offenders
