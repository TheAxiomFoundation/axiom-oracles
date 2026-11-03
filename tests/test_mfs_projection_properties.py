"""Married-filing-separately invariants across the three tax projections.

* TAXSIM row validation: a row is accepted exactly when its ``mstat`` is one
  of the TAXSIM-35 codes the adapter accepts (1, 2, 6, 8) and, off a joint return, every
  secondary-taxpayer column is blank or zero (the pinned binary stops the
  whole batch with ``STOP 1`` otherwise).
* Differential: the TAXSIM, Axiom and PolicyEngine projections read one
  Case's separate-return facts through ``core.filing.separate_filing``, so
  they must agree on whether the Case is a separate return: TAXSIM ``mstat``
  6; on the Axiom side, the 26 USC 7703 separate-return input set, with a
  federal filing status of 2 or 3 (3 is also an unmarried head of
  household, so the status alone does not decide it); and a PolicyEngine
  tax-unit head marked ``is_separated``.
"""

from __future__ import annotations

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from axiom_oracles.adapters.axiom.tax_projection import attach_axiom_tax_inputs_to_case
from axiom_oracles.adapters.policyengine import PolicyEngineRunner
from axiom_oracles.adapters.taxsim.projection import (
    taxsim_input_for_case,
    validate_taxsim_row,
)
from axiom_oracles.core.case import Case, Concepts, Entity

SPOUSE_COLUMNS = ("sage", "swages", "ssemp", "sui", "sbusinc", "sprofinc")
DOCUMENTED_MSTAT = {1, 2, 6, 8}
YEAR = 2026
_FILING_STATUS = "us:tax/federal-income-tax#input.filing_status"
_FILES_SEPARATE = "us:statutes/26/7703#input.taxpayer_files_separate_return"

_BLANKS = (None, "", 0, 0.0, float("nan"))
_blank = st.sampled_from(_BLANKS)
_nonzero = st.one_of(
    st.integers(1, 200_000), st.floats(0.5, 2e5, allow_nan=False)
)

# The verdict for every sampled mstat value, written out rather than derived
# with the validator's own numeric coercion: the integral spellings of a
# documented code are accepted, and everything else is refused. Keyed by
# (type, value) because 1, 1.0 and True are one dict key otherwise.
_MSTAT_CODE = {
    (int, 1): 1, (int, 2): 2, (int, 6): 6, (int, 8): 8,
    (float, 1.0): 1, (float, 6.0): 6, (str, "6"): 6,
    (int, 0): None, (int, 3): None, (int, 4): None, (int, 7): None,
    (float, 2.5): None, (bool, True): None, (type(None), None): None,
}
_MSTAT_SAMPLES = [1, 2, 6, 8, 1.0, 6.0, "6", 0, 3, 4, 7, 2.5, True]


def _is_blank(value) -> bool:
    """A spouse cell TaxsimRunner writes as 0: missing, empty, NaN or zero."""
    return value is None or value == "" or value != value or value == 0


def _with_blank_spouse_examples(test):
    # Pin NaN, "" and None on every non-joint code so a validator that counts
    # one of them as a spouse value fails on every seed, not only when the
    # generator happens to draw it.
    for mstat in (1, 6, 8):
        for blank in (float("nan"), "", None):
            test = example(mstat=mstat, spouse={"sage": blank, "swages": blank})(test)
    return test


@_with_blank_spouse_examples
@settings(max_examples=400, deadline=None)
@given(
    mstat=st.one_of(st.sampled_from(_MSTAT_SAMPLES), st.none()),
    spouse=st.dictionaries(
        st.sampled_from(SPOUSE_COLUMNS), st.one_of(_blank, _nonzero), max_size=6
    ),
)
def test_validate_taxsim_row_accepts_exactly_the_documented_shapes(
    mstat, spouse
) -> None:
    row = {"taxsimid": 1, "year": YEAR, **spouse}
    if mstat is not None:
        row["mstat"] = mstat
    code = _MSTAT_CODE[(type(mstat), mstat)]
    has_spouse_value = not all(_is_blank(value) for value in spouse.values())
    accepted = code in DOCUMENTED_MSTAT and (code == 2 or not has_spouse_value)
    if accepted:
        validate_taxsim_row(row, case_id="generated")
    else:
        with pytest.raises(ValueError, match="generated"):
            validate_taxsim_row(row, case_id="generated")


def _person(entity_id: str, relation: str, age: int, **facts) -> Entity:
    return Entity(
        entity_id,
        "person",
        facts={
            Concepts.HOUSEHOLD_RELATION: relation,
            Concepts.PERSON_AGE: age,
            **facts,
        },
    )


@st.composite
def _cases(draw) -> Case:
    separate = draw(st.booleans())
    spouse = not separate and draw(st.booleans())
    children = draw(st.integers(0, 2))
    facts = {Concepts.STATE_CODE: "CO"}
    if separate:
        facts[Concepts.MARRIED_FILING_SEPARATELY] = True
        lived_apart = draw(st.booleans())
        facts[Concepts.LIVED_APART_FROM_SPOUSE_ALL_YEAR] = lived_apart
        if not lived_apart and draw(st.booleans()):
            facts[Concepts.SPOUSE_ABSENT_LAST_SIX_MONTHS] = draw(st.booleans())
    elif draw(st.booleans()):
        facts[Concepts.MARRIED_FILING_SEPARATELY] = False
    entities = [
        _person(
            "filer",
            "HeadOfHousehold",
            draw(st.integers(25, 80)),
            **{Concepts.YEARLY_EARNED_INCOME: draw(st.integers(0, 300_000))},
        )
    ]
    if spouse:
        entities.append(
            _person(
                "spouse",
                "Spouse",
                draw(st.integers(25, 80)),
                **{Concepts.YEARLY_EARNED_INCOME: draw(st.integers(0, 100_000))},
            )
        )
    entities.extend(
        _person(f"child-{index}", "Child", draw(st.integers(1, 16)))
        for index in range(children)
    )
    return Case(
        case_id="generated",
        period=str(YEAR),
        metadata={"scope": {"type": "census_state", "geoid": "08"}},
        facts=facts,
        entities=tuple(entities),
    )


def _axiom_values(case: Case, name: str) -> set:
    records = attach_axiom_tax_inputs_to_case(case).metadata["axiom_input_records"]
    return {record["value"] for record in records if record.get("name") == name}


def _policyengine_separated(case: Case) -> bool:
    situation = PolicyEngineRunner()._build_situation_from_case(
        case, variables=["income_tax"]
    )
    return situation["people"]["filer"].get("is_separated") == {YEAR: True}


@settings(max_examples=150, deadline=None)
@given(case=_cases())
def test_the_three_projections_agree_on_a_separate_return(case: Case) -> None:
    separate = bool(case.fact(Concepts.MARRIED_FILING_SEPARATELY))
    row = taxsim_input_for_case(case, taxsimid=1)
    validate_taxsim_row(row, case_id=case.case_id)
    assert (row["mstat"] == 6) is separate
    if separate:
        assert all(row.get(column, 0) == 0 for column in SPOUSE_COLUMNS)
    [status] = _axiom_values(case, _FILING_STATUS)
    assert (True in _axiom_values(case, _FILES_SEPARATE)) is separate
    if separate:
        assert status in (2, 3)
    else:
        assert status != 2
    assert _policyengine_separated(case) is separate
