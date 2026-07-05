"""UK savings and dividend income-tax oracle cases for the UKMOD UK_2026 oracle.

The composed ``savings_dividend_oracle_pipeline`` (rulespec-uk) stacks savings
and dividend income on top of earned income per the Income Tax Act 2007
section 16 highest-part ordering, so an end-to-end income-tax liability is
queryable from three gross income inputs. UKMOD reads taxable savings interest
through ``yiytx`` and taxable dividends through ``ydvtx`` (its generic
projector sums both into ``yiy``, which the UK ``training_data`` configuration
does not load, so these suites carry explicit rows). Every case keeps earned
income at or above the £5,000 starting-rate limit for savings.

Savings-only and dividend-only cases reproduce UKMOD ``tin_s`` to the penny.
Mixed savings-and-dividend cases are covered separately in
``uk_income_tax_mixed`` and are dispositioned against a UKMOD platform bug that
zeroes savings tax when dividend income is present (see
``dispositions/uk-income-tax-mixed.yaml`` and
``axiom_oracles/data/euromod_issues.json``).
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity


UK_SCOPE = {"type": "country", "geoid": "UK"}
UK_METADATA = {
    "locale": "UK",
    "scope": UK_SCOPE,
    "axiom_entity": "Person",
    "axiom_entity_id": "head",
}
SVDV_MODULE = "uk:statutes/income_tax/individual/savings_dividend_oracle_pipeline"
SCOT_MODULE = "uk:statutes/income_tax/individual/scottish_income_tax_oracle_pipeline"
EUROMOD_TO_AXIOM_INPUT_BRIDGE = "euromod_to_axiom_input_bridge"

# UKMOD region code (``drgn1``) that routes a household to Scotland, so
# UK_2026 applies the Scottish income tax bands. Verified against the UK.xml
# ``Factor_Condition`` named "Scotland" with value ``(drgn1 = 12)`` and by a
# live UKMOD sweep whose tin_s reproduces the RuleSpec Scottish liability to
# the penny (a drgn1=8 England control returns the different rest-of-UK tax).
_DRGN1_SCOTLAND = 12

# The composed pipeline is effective from the 2026-27 tax year. 2025-26 and
# 2026-27 share frozen thresholds and rates, so UKMOD UK_2025 and UK_2026
# return identical values for these cases.
UK_IT_PERIOD = "2026"

# Savings earnings sweep: earned income straddles basic/higher/additional
# bands, savings straddles the personal savings allowance and the band edges.
_SAVINGS_GRID: tuple[tuple[str, float, float], ...] = (
    ("e20k-s2k", 20_000.0, 2_000.0),
    ("e30k-s3k", 30_000.0, 3_000.0),
    ("e45k-s6k", 45_000.0, 6_000.0),
    ("e80k-s5k", 80_000.0, 5_000.0),
    ("e150k-s10k", 150_000.0, 10_000.0),
)

# Dividend sweep: dividends straddle the dividend allowance and the ordinary/
# upper/additional dividend-rate band edges.
_DIVIDEND_GRID: tuple[tuple[str, float, float], ...] = (
    ("e20k-d2k", 20_000.0, 2_000.0),
    ("e30k-d4k", 30_000.0, 4_000.0),
    ("e45k-d6k", 45_000.0, 6_000.0),
    ("e130k-d10k", 130_000.0, 10_000.0),
    ("e200k-d20k", 200_000.0, 20_000.0),
)

# Mixed savings-and-dividend cases straddling both allowances. These exercise
# the section 16 ordering where savings and dividends together form the highest
# part; UKMOD mis-taxes them (savings tax zeroed when dividends are present), so
# they are dispositioned rather than expected to match.
_MIXED_GRID: tuple[tuple[str, float, float, float], ...] = (
    ("e30k-s3k-d4k", 30_000.0, 3_000.0, 4_000.0),
    ("e60k-s5k-d3k", 60_000.0, 5_000.0, 3_000.0),
    ("e150k-s10k-d20k", 150_000.0, 10_000.0, 20_000.0),
)


# Scottish non-savings non-dividend earnings sweep. Earned income crosses
# every Scottish band boundary, including £45,000 which straddles the £43,662
# Scottish higher-rate threshold (a Scotland-only boundary: rest-of-UK has no
# intermediate band there), and £130,000/£160,000 which reach the top rate
# after the personal allowance has fully tapered. Savings and dividends are
# zero (they stay at UK rates); the region is routed to Scotland via drgn1=12.
_SCOTTISH_GRID: tuple[tuple[str, float], ...] = (
    ("e14k", 14_000.0),
    ("e20k", 20_000.0),
    ("e30k", 30_000.0),
    ("e45k", 45_000.0),
    ("e50k", 50_000.0),
    ("e75k", 75_000.0),
    ("e100k", 100_000.0),
    ("e130k", 130_000.0),
    ("e160k", 160_000.0),
)


def uk_income_tax_scottish_cases() -> list[Case]:
    """Scottish taxpayer non-savings income-tax cases for the UKMOD UK_2026 oracle."""

    return [
        _scottish_case(f"uk-it-scottish-{label}", earned)
        for label, earned in _SCOTTISH_GRID
    ]


def uk_income_tax_savings_cases() -> list[Case]:
    """Savings-income UK income-tax cases for the UKMOD UK_2026 oracle."""

    return [
        _savings_dividend_case(f"uk-it-savings-{label}", earned, savings, 0.0)
        for label, earned, savings in _SAVINGS_GRID
    ]


def uk_income_tax_dividend_cases() -> list[Case]:
    """Dividend-income UK income-tax cases for the UKMOD UK_2026 oracle."""

    return [
        _savings_dividend_case(f"uk-it-dividend-{label}", earned, 0.0, dividend)
        for label, earned, dividend in _DIVIDEND_GRID
    ]


def uk_income_tax_mixed_cases() -> list[Case]:
    """Mixed savings-and-dividend UK income-tax cases (dispositioned)."""

    return [
        _savings_dividend_case(f"uk-it-mixed-{label}", earned, savings, dividend)
        for label, earned, savings, dividend in _MIXED_GRID
    ]


def _savings_dividend_case(
    case_id: str,
    earned: float,
    savings: float,
    dividend: float,
) -> Case:
    earned_input = _svdv_input("uk_svdv_annual_earned_income")
    savings_input = _svdv_input("uk_svdv_annual_savings_income")
    dividend_input = _svdv_input("uk_svdv_annual_dividend_income")
    return Case(
        case_id=case_id,
        period=UK_IT_PERIOD,
        metadata={
            **UK_METADATA,
            "scenario": "single-person-savings-dividend",
            "yearly_earned_income": earned,
            "yearly_savings_income": savings,
            "yearly_dividend_income": dividend,
            "axiom_inputs": {
                earned_input: earned,
                savings_input: savings,
                dividend_input: dividend,
            },
            "euromod_inputs": [_euromod_input(earned, savings, dividend)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yem": [earned_input],
                "yiytx": [savings_input],
                "ydvtx": [dividend_input],
            },
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 40,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.YEARLY_EARNED_INCOME: earned,
                    Concepts.INTEREST_INCOME: savings,
                    Concepts.DIVIDEND_INCOME: dividend,
                },
            ),
        ),
        outputs=(Concepts.UK_SAVINGS_DIVIDEND_INCOME_TAX_LIABILITY,),
    )


def _scottish_case(case_id: str, earned: float) -> Case:
    earned_input = f"{SCOT_MODULE}#input.uk_scotpit_annual_earned_income"
    return Case(
        case_id=case_id,
        period=UK_IT_PERIOD,
        metadata={
            **UK_METADATA,
            "scenario": "single-person-scottish-earned",
            "yearly_earned_income": earned,
            "axiom_inputs": {earned_input: earned},
            "euromod_inputs": [_scottish_euromod_input(earned)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"yem": [earned_input]},
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 40,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.YEARLY_EARNED_INCOME: earned,
                },
            ),
        ),
        outputs=(Concepts.UK_SCOTTISH_INCOME_TAX_LIABILITY,),
    )


def _svdv_input(name: str) -> str:
    return f"{SVDV_MODULE}#input.{name}"


def _euromod_input(
    earned: float,
    savings: float,
    dividend: float,
) -> dict[str, float | int]:
    # UKMOD demo data is monthly; the runner reads the annual value back from
    # ``yem``. Taxable savings interest is ``yiytx`` and taxable dividends are
    # ``ydvtx``; the ``yiy``/``yiynt`` aggregates are left at zero so the
    # engine taxes exactly the supplied taxable amounts.
    employed = earned > 0
    return {
        "idperson": 101,
        "idpartner": 0,
        "idmother": 0,
        "idfather": 0,
        "dct": 15,
        "dwt": 1.0,
        "dag": 40,
        "dgn": 1,
        "dms": 1,
        "dec": 0,
        "les": 3 if employed else 0,
        "lfs": 15 if employed else 0,
        "lhw": 40 if employed else 0,
        "loc": 5,
        "liwmy": 12 if employed else 0,
        "liwwh": 120 if employed else 0,
        "yem": earned / 12,
        "yemmy": 12 if employed else 0,
        "yiytx": savings / 12,
        "ydvtx": dividend / 12,
    }


def _scottish_euromod_input(earned: float) -> dict[str, float | int]:
    # A Scottish taxpayer with earned income only: same single-employee row as
    # the earned-income pilot, but routed to Scotland via ``drgn1`` so UKMOD
    # UK_2026 applies the Scottish rate bands to ``tin_s``. Savings and dividend
    # taxable amounts are zero.
    employed = earned > 0
    return {
        "idperson": 101,
        "idpartner": 0,
        "idmother": 0,
        "idfather": 0,
        "dct": 15,
        "dwt": 1.0,
        "dag": 40,
        "dgn": 1,
        "dms": 1,
        "dec": 0,
        "les": 3 if employed else 0,
        "lfs": 15 if employed else 0,
        "lhw": 40 if employed else 0,
        "loc": 5,
        "liwmy": 12 if employed else 0,
        "liwwh": 120 if employed else 0,
        "yem": earned / 12,
        "yemmy": 12 if employed else 0,
        "yiytx": 0.0,
        "ydvtx": 0.0,
        "drgn1": _DRGN1_SCOTLAND,
    }
