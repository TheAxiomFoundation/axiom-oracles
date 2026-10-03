import math

import pytest

from axiom_oracles.adapters.taxsim.projection import (
    attach_taxsim_inputs,
    taxsim_input_for_case,
    validate_taxsim_row,
)
from axiom_oracles.core.case import Case, Concepts, Entity


def test_taxsim_projection_maps_family_wages_dependents_and_scope_state() -> None:
    case = Case(
        case_id="nyc-family",
        period="2024-05",
        metadata={"scope": {"type": "census_place", "geoid": "3651000"}},
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 40,
                    Concepts.YEARLY_EARNED_INCOME: 50_000,
                    Concepts.SELF_EMPLOYMENT_INCOME: 3_000,
                },
            ),
            Entity(
                "person-2",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Spouse",
                    Concepts.PERSON_AGE: 38,
                    Concepts.YEARLY_EARNED_INCOME: 20_000,
                    Concepts.SELF_EMPLOYMENT_INCOME: 2_000,
                },
            ),
            Entity(
                "person-3",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.PERSON_AGE: 5,
                },
            ),
            Entity(
                "person-4",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.PERSON_AGE: 17,
                },
            ),
        ),
    )

    row = taxsim_input_for_case(case, taxsimid=7)

    assert row["taxsimid"] == 7
    assert row["year"] == 2024
    assert row["state"] == 33
    assert row["mstat"] == 2
    assert row["page"] == 40
    assert row["sage"] == 38
    assert row["pwages"] == 50_000
    assert row["swages"] == 20_000
    assert row["psemp"] == 3_000
    assert row["ssemp"] == 2_000
    assert row["depx"] == 2
    assert row["age1"] == 5
    assert row["age2"] == 17
    assert row["dep13"] == 1
    assert row["dep17"] == 1
    assert row["dep18"] == 2
    # idtl=2 requests TAXSIM's decomposed credit columns (v10..v41) used for
    # component-level comparisons.
    assert row["idtl"] == 2


def test_taxsim_projection_uses_state_code_fact_without_scope() -> None:
    case = Case(
        case_id="ca",
        period="2024",
        facts={Concepts.STATE_CODE: "CA"},
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 30,
                    Concepts.YEARLY_EARNED_INCOME: 10_000,
                },
            ),
        ),
    )

    row = taxsim_input_for_case(case)

    assert row["state"] == 5
    assert row["mstat"] == 1
    assert row["depx"] == 0


def test_attach_taxsim_inputs_preserves_existing_projection() -> None:
    existing = {
        "taxsimid": "custom-id",
        "year": 2026,
        "state": 36,
        "mstat": 1,
        "page": 40,
    }
    case = Case(
        case_id="case-1",
        period="2026",
        metadata={"taxsim_input": existing},
    )

    [projected] = attach_taxsim_inputs([case])

    assert projected.metadata["taxsim_input"] == existing


def test_taxsim_projection_requires_state() -> None:
    case = Case(
        case_id="missing-state",
        period="2024",
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 30,
                },
            ),
        ),
    )

    with pytest.raises(RuntimeError, match="state"):
        taxsim_input_for_case(case)


def test_taxsim_projection_rejects_years_after_bundled_taxsim_support() -> None:
    case = Case(
        case_id="future-year",
        period="2027",
        facts={Concepts.STATE_CODE: "NY"},
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 30,
                },
            ),
        ),
    )

    with pytest.raises(RuntimeError, match="through 2026"):
        taxsim_input_for_case(case)


def test_taxsim_projection_splits_dividends_by_qualification() -> None:
    case = Case(
        case_id="dividend-split",
        period="2026",
        facts={Concepts.STATE_CODE: "CO"},
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 40,
                    Concepts.DIVIDEND_INCOME: 5_000,
                    Concepts.QUALIFIED_DIVIDEND_INCOME: 3_000,
                    Concepts.RENTAL_INCOME: 1_000,
                },
            ),
        ),
    )

    row = taxsim_input_for_case(case)

    # TAXSIM's dividends column is qualified-only; the non-qualified
    # remainder rides in otherprop so AGI stays whole.
    assert row["dividends"] == 3_000
    assert row["otherprop"] == 3_000  # 1,000 rental + 2,000 non-qualified


def test_taxsim_projection_keeps_qualified_only_dividend_rows_whole() -> None:
    case = Case(
        case_id="dividend-qualified-only",
        period="2026",
        facts={Concepts.STATE_CODE: "CO"},
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 40,
                    Concepts.QUALIFIED_DIVIDEND_INCOME: 4_000,
                },
            ),
        ),
    )

    row = taxsim_input_for_case(case)

    assert row["dividends"] == 4_000
    assert row["otherprop"] == 0


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


def test_taxsim_projection_maps_childless_separate_return_to_mstat_6() -> None:
    case = Case(
        case_id="mfs-wages-40000",
        period="2026",
        facts={
            Concepts.STATE_CODE: "CO",
            Concepts.MARRIED_FILING_SEPARATELY: True,
        },
        entities=(
            _person(
                "filer",
                "HeadOfHousehold",
                40,
                **{
                    Concepts.YEARLY_EARNED_INCOME: 40_000,
                    Concepts.INTEREST_INCOME: 250,
                    Concepts.PENSION_INCOME: 1_000,
                    Concepts.SOCIAL_SECURITY_BENEFITS: 2_000,
                    Concepts.UNEMPLOYMENT_INSURANCE_INCOME: 500,
                },
            ),
        ),
    )

    row = taxsim_input_for_case(case, taxsimid=3)

    assert row["mstat"] == 6
    assert row["page"] == 40
    assert row["pwages"] == 40_000
    assert row["pui"] == 500
    assert row["depx"] == 0
    # No spouse entity on a separate return: every secondary-taxpayer column
    # is 0 (TAXSIM aborts the batch otherwise) and the household sums carry
    # the filer's own amounts only.
    assert row["sage"] == 0
    assert row["swages"] == 0
    assert row["ssemp"] == 0
    assert row["sui"] == 0
    assert row["intrec"] == 250
    assert row["pensions"] == 1_000
    assert row["gssi"] == 2_000


def test_taxsim_projection_keeps_separate_filer_child_as_dependent() -> None:
    case = Case(
        case_id="mfs-child-wages-15000",
        period="2026",
        facts={
            Concepts.STATE_CODE: "CO",
            Concepts.MARRIED_FILING_SEPARATELY: True,
            Concepts.LIVED_APART_FROM_SPOUSE_ALL_YEAR: True,
        },
        entities=(
            _person(
                "filer",
                "HeadOfHousehold",
                35,
                **{Concepts.YEARLY_EARNED_INCOME: 15_000},
            ),
            _person("child", "Child", 8),
        ),
    )

    row = taxsim_input_for_case(case)

    assert row["mstat"] == 6
    assert row["depx"] == 1
    assert row["age1"] == 8
    assert row["dep13"] == 1
    assert row["dep17"] == 1
    assert row["dep18"] == 1
    assert row["sage"] == 0
    assert row["swages"] == 0


def test_taxsim_projection_rejects_separate_return_with_spouse_entity() -> None:
    case = Case(
        case_id="mfs-with-spouse",
        period="2026",
        facts={
            Concepts.STATE_CODE: "CO",
            Concepts.MARRIED_FILING_SEPARATELY: True,
        },
        entities=(
            _person("filer", "HeadOfHousehold", 40),
            _person("other-spouse", "Spouse", 38),
        ),
    )

    with pytest.raises(RuntimeError, match="'mfs-with-spouse'.*'other-spouse'"):
        taxsim_input_for_case(case)


def test_taxsim_projection_treats_explicit_false_separate_flag_as_single() -> None:
    case = Case(
        case_id="not-mfs",
        period="2026",
        facts={
            Concepts.STATE_CODE: "CO",
            Concepts.MARRIED_FILING_SEPARATELY: False,
        },
        entities=(_person("filer", "HeadOfHousehold", 40),),
    )

    assert taxsim_input_for_case(case)["mstat"] == 1


def test_taxsim_projection_surfaces_separate_filing_fact_errors() -> None:
    # The projection reads the facts through core.filing.separate_filing, so
    # a residence fact without the separate-return flag fails there too.
    case = Case(
        case_id="lived-apart-without-mfs",
        period="2026",
        facts={
            Concepts.STATE_CODE: "CO",
            Concepts.LIVED_APART_FROM_SPOUSE_ALL_YEAR: True,
        },
        entities=(_person("filer", "HeadOfHousehold", 40),),
    )

    with pytest.raises(ValueError, match="lived-apart-without-mfs"):
        taxsim_input_for_case(case)


# Rows the projection produced for these cases at commit 5420b1923, before the
# married-filing-separately change. Non-MFS rows must stay identical, column
# order included (the TAXSIM frame's columns follow it).
_BASE_SINGLE_ROW = {
    "taxsimid": 1,
    "year": 2026,
    "state": 6,
    "mstat": 1,
    "page": 67,
    "sage": 0,
    "depx": 0,
    "dep13": 0,
    "dep17": 0,
    "dep18": 0,
    "pwages": 30000.0,
    "swages": 0,
    "psemp": 0.0,
    "ssemp": 0,
    "dividends": 0.0,
    "intrec": 400.0,
    "stcg": 0.0,
    "ltcg": 0.0,
    "pensions": 5000.0,
    "otherprop": 0.0,
    "gssi": 18000.0,
    "pui": 0.0,
    "sui": 0,
    "proptax": 0.0,
    "mortgage": 0.0,
    "otheritem": 0.0,
    "rentpaid": 0.0,
    "childcare": 0.0,
    "idtl": 2,
    "nonprop": 0,
    "transfers": 0,
    "scorp": 0,
}

_BASE_JOINT_ROW = {
    "taxsimid": 1,
    "year": 2026,
    "state": 6,
    "mstat": 2,
    "page": 45,
    "sage": 43,
    "depx": 2,
    "dep13": 1,
    "dep17": 2,
    "dep18": 2,
    "pwages": 90000.0,
    "swages": 35000.0,
    "psemp": 4000.0,
    "ssemp": 1500.0,
    "dividends": 600.0,
    "intrec": 500.0,
    "stcg": 0.0,
    "ltcg": 0.0,
    "pensions": 0.0,
    "otherprop": 400.0,
    "gssi": 0.0,
    "pui": 1000.0,
    "sui": 2500.0,
    "proptax": 3000.0,
    "mortgage": 0.0,
    "otheritem": 0.0,
    "rentpaid": 0.0,
    "childcare": 0.0,
    "idtl": 2,
    "age1": 8,
    "age2": 15,
    "nonprop": 0,
    "transfers": 0,
    "scorp": 0,
}

_BASE_HEAD_OF_HOUSEHOLD_ROW = {
    "taxsimid": 1,
    "year": 2026,
    "state": 6,
    "mstat": 1,
    "page": 35,
    "sage": 0,
    "depx": 1,
    "dep13": 1,
    "dep17": 1,
    "dep18": 1,
    "pwages": 45000.0,
    "swages": 0,
    "psemp": 0.0,
    "ssemp": 0,
    "dividends": 0.0,
    "intrec": 0.0,
    "stcg": 0.0,
    "ltcg": 0.0,
    "pensions": 0.0,
    "otherprop": 0.0,
    "gssi": 0.0,
    "pui": 0.0,
    "sui": 0,
    "proptax": 0.0,
    "mortgage": 0.0,
    "otheritem": 0.0,
    "rentpaid": 0.0,
    "childcare": 0.0,
    "idtl": 2,
    "age1": 8,
    "nonprop": 0,
    "transfers": 0,
    "scorp": 0,
}


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        (
            Case(
                case_id="single-regression",
                period="2026",
                facts={Concepts.STATE_CODE: "CO"},
                entities=(
                    _person(
                        "p1",
                        "HeadOfHousehold",
                        67,
                        **{
                            Concepts.YEARLY_EARNED_INCOME: 30_000,
                            Concepts.SOCIAL_SECURITY_BENEFITS: 18_000,
                            Concepts.INTEREST_INCOME: 400,
                            Concepts.PENSION_INCOME: 5_000,
                        },
                    ),
                ),
            ),
            _BASE_SINGLE_ROW,
        ),
        (
            Case(
                case_id="joint-regression",
                period="2026",
                facts={
                    Concepts.STATE_CODE: "CO",
                    Concepts.PROPERTY_TAX_PAID: 3_000,
                },
                entities=(
                    _person(
                        "p1",
                        "HeadOfHousehold",
                        45,
                        **{
                            Concepts.YEARLY_EARNED_INCOME: 90_000,
                            Concepts.SELF_EMPLOYMENT_INCOME: 4_000,
                            Concepts.INTEREST_INCOME: 300,
                            Concepts.UNEMPLOYMENT_INSURANCE_INCOME: 1_000,
                        },
                    ),
                    _person(
                        "p2",
                        "Spouse",
                        43,
                        **{
                            Concepts.YEARLY_EARNED_INCOME: 35_000,
                            Concepts.SELF_EMPLOYMENT_INCOME: 1_500,
                            Concepts.INTEREST_INCOME: 200,
                            Concepts.UNEMPLOYMENT_INSURANCE_INCOME: 2_500,
                            Concepts.DIVIDEND_INCOME: 1_000,
                            Concepts.QUALIFIED_DIVIDEND_INCOME: 600,
                        },
                    ),
                    _person("p3", "Child", 8),
                    _person("p4", "Child", 15),
                ),
            ),
            _BASE_JOINT_ROW,
        ),
        (
            Case(
                case_id="hoh-regression",
                period="2026",
                facts={Concepts.STATE_CODE: "CO"},
                entities=(
                    _person(
                        "p1",
                        "HeadOfHousehold",
                        35,
                        **{Concepts.YEARLY_EARNED_INCOME: 45_000},
                    ),
                    _person("p2", "Child", 8),
                ),
            ),
            _BASE_HEAD_OF_HOUSEHOLD_ROW,
        ),
    ],
    ids=["single", "joint", "head-of-household"],
)
def test_taxsim_projection_leaves_non_separate_rows_unchanged(
    case: Case, expected: dict
) -> None:
    row = taxsim_input_for_case(case, taxsimid=1)

    assert list(row.items()) == list(expected.items())


def _row(mstat, **columns) -> dict:
    return {"taxsimid": 1, "year": 2026, "state": 6, "mstat": mstat, **columns}


def test_validate_taxsim_row_rejects_spouse_age_on_single_return() -> None:
    with pytest.raises(ValueError, match=r"'case-a'.*sage=40"):
        validate_taxsim_row(_row(1, page=40, sage=40), case_id="case-a")


@pytest.mark.parametrize(
    "column", ["sage", "swages", "ssemp", "sui", "sbusinc", "sprofinc"]
)
@pytest.mark.parametrize("mstat", [1, 6, 8])
def test_validate_taxsim_row_rejects_spouse_columns_off_joint_returns(
    mstat: int, column: str
) -> None:
    with pytest.raises(ValueError, match=rf"'case-b'.*mstat {mstat}.*{column}=1000"):
        validate_taxsim_row(_row(mstat, **{column: 1000}), case_id="case-b")


def test_validate_taxsim_row_names_every_offending_column() -> None:
    with pytest.raises(ValueError) as error:
        validate_taxsim_row(
            _row(6, swages=1, ssemp=2, sui=3, sbusinc=4, sprofinc=5),
            case_id="case-c",
        )

    message = str(error.value)
    for listed in ("swages=1", "ssemp=2", "sui=3", "sbusinc=4", "sprofinc=5"):
        assert listed in message


def test_validate_taxsim_row_allows_spouse_columns_on_joint_returns() -> None:
    validate_taxsim_row(
        _row(2, sage=40, swages=1, ssemp=2, sui=3, sbusinc=4, sprofinc=5),
        case_id="joint",
    )


@pytest.mark.parametrize(
    "row",
    [
        _row(6),
        _row(6, sage=0, swages=0.0, ssemp=None, sui="", sprofinc=math.nan),
        _row(6.0, swages=0),
        _row("6"),
        _row(1),
        _row(8),
    ],
    ids=["missing", "zero-like", "float-mstat", "string-mstat", "single", "dependent"],
)
def test_validate_taxsim_row_accepts_zero_or_missing_spouse_columns(row) -> None:
    validate_taxsim_row(row, case_id="ok")


@pytest.mark.parametrize(
    "mstat",
    [None, 0, 3, 4, 5, 7, 9, 6.5, "separate", True, math.nan],
    ids=lambda value: repr(value),
)
def test_validate_taxsim_row_rejects_undocumented_mstat(mstat) -> None:
    row = _row(mstat)
    if mstat is None:
        del row["mstat"]
    with pytest.raises(ValueError, match="'case-d'.*documented codes"):
        validate_taxsim_row(row, case_id="case-d")


def test_validate_taxsim_row_rejects_non_numeric_spouse_column() -> None:
    with pytest.raises(ValueError, match="'case-e'.*swages"):
        validate_taxsim_row(_row(6, swages="n/a"), case_id="case-e")
