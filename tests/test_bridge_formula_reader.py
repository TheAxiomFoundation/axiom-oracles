"""The test-only bridge formula reader reads the bridge as written.

``tests/bridge_formula.py`` evaluates the oracle bridge's formula strings so
bridge-rule tests can check arithmetic without the engine. These tests pin the
reader itself: the grammar the bridge uses, that every bridge rule parses, that
unknown names raise, and two bridge chains worked by hand from the statute.
"""

from __future__ import annotations

import pytest

from bridge_formula import (
    STATUTORY_SECA_VALUES,
    BridgeReader,
    FormulaError,
    parse,
    reader_for_case,
)

from axiom_oracles.adapters.axiom.tax_projection import (
    US_TAX_ORACLE_PROGRAM_RULES,
    attach_axiom_tax_inputs_to_case,
)
from axiom_oracles.core.case import Case, Concepts, Entity


def _rule(name, formula, *, entity="TaxUnit", kind="derived"):
    rule = {"name": name, "kind": kind, "versions": [{"formula": formula}]}
    if kind == "derived":
        rule["entity"] = entity
    return rule


def _reader(*rules, **values):
    return BridgeReader(rules, values=values)


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("max(0, 2 - 5)", 0),
        ("min(3, 4) * 2 + 1", 7),
        ("-3 + 10 / 4", -0.5),
        ("if 1 > 0: 2 else: 3", 2),
        ("if 1 > 2: 2 else: if 3 >= 3: 4 else: 5", 4),
        ("(if 1 == 1: 1 else: 0) + (if 2 <= 1: 1 else: 0)", 1),
        ("not 1 > 2 and (0 < 1 or 1 < 0)", True),
        ("ceil(4001 / 2000)", 3),
        ("if True: 1 else: 0", 1),
    ],
)
def test_reader_grammar(formula, expected) -> None:
    assert _reader(_rule("x", formula)).value("x") == expected


def test_every_bridge_formula_parses() -> None:
    for rule in US_TAX_ORACLE_PROGRAM_RULES:
        for version in rule.get("versions", []):
            parse(version["formula"])


def test_unknown_names_raise_instead_of_reading_as_zero() -> None:
    with pytest.raises(FormulaError, match="not a bridge rule"):
        _reader(_rule("x", "1 + misspelled_name")).value("x")


def test_rules_are_read_on_their_own_entity() -> None:
    reader = BridgeReader(
        [_rule("person_value", "1", entity="Person")],
        input_records=[
            {"name": "a#input.x", "entity": "TaxUnit", "entity_id": "tax_unit", "value": 0}
        ],
    )
    with pytest.raises(FormulaError, match="is a Person rule"):
        reader.value("person_value", "tax_unit")


def _case(*people):
    return attach_axiom_tax_inputs_to_case(
        Case(case_id="reader", period="2026", entities=tuple(people))
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


@pytest.mark.parametrize(
    ("wages", "oasdi", "ald"),
    [
        # 20,000 x 0.9235 = 18,470 of net earnings; 12.4% = 2,290.28,
        # 2.9% = 535.63; 164(f) deducts half: 1,412.955.
        pytest.param(0, 2_290.28, 1_412.955, id="below-base"),
        # 1401(a) reaches 184,500 - 180,000 = 4,500: 12.4% = 558.00;
        # half of 558.00 + 535.63 = 546.815.
        pytest.param(180_000, 558.00, 546.815, id="wage-base-binds"),
    ],
)
def test_reader_reproduces_the_bridge_seca_chain(wages, oasdi, ald) -> None:
    projected = _case(
        _person("person-1", "HeadOfHousehold", 40, **{
            Concepts.YEARLY_EARNED_INCOME: wages,
            Concepts.SELF_EMPLOYMENT_INCOME: 20_000,
        })
    )
    reader = reader_for_case(
        projected, US_TAX_ORACLE_PROGRAM_RULES, values=STATUTORY_SECA_VALUES
    )

    assert reader.value("person_self_employment_oasdi_tax", "person-1") == (
        pytest.approx(oasdi)
    )
    assert reader.value("person_self_employment_tax_ald_for_qbid", "person-1") == (
        pytest.approx(ald)
    )
    assert reader.value("self_employment_tax_ald_for_agi") == pytest.approx(ald)


def test_reader_reproduces_the_senior_deduction_phaseout() -> None:
    """H.R.1 section 70103: 6,000 less 6% of AGI over 75,000 (single)."""
    projected = _case(_person("person-1", "HeadOfHousehold", 70))
    reader = reader_for_case(
        projected,
        US_TAX_ORACLE_PROGRAM_RULES,
        values={"adjusted_gross_income": 80_000},
    )

    assert reader.value("additional_senior_deduction") == pytest.approx(5_700)
