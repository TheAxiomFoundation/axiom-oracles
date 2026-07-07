"""Ghana capital-income withholding oracle suite (GHAMOD).

``gh-capital-income`` compares the Axiom Act 896 First Schedule paragraph
8(1)(b) rent withholding against GHAMOD (SOUTHMOD A4.0, country GH, system
GH_2025): ``individual_residential_rent_final_withholding`` (8% of rent
paid to a resident individual for residential property, final under
s.119(1)(b)) against GHAMOD ``tinrt_s`` (8% of ``ypr``) — probed live:
tinrt_s/ypr = 0.080000 exactly.

GHAMOD's other capital-income component, ``tiniy_s`` = 15% of investment
income ``yiy``, has NO live cases: no in-force paragraph 8(1)(b) rate
supports a flat 15% for investment income proper (dividends are 8% under
row (i); interest paid to an individual by a resident financial
institution or on Government of Ghana bonds is exempt under Act 907
s.7(1)(p)/(q), with a 1% residual row (ii); other interest is 8% under
row (iii) — the supersession chain 2015-2026 is closed, none of these
rows was ever amended). Every ``yiy`` case would therefore diverge; the
observation is recorded in ``axiom_oracles/data/ghamod_issues.json``
(``ghamod-tiniy-15pct-rate-unsupported-by-para-8``) following the tinta04
pattern, and the Axiom dividend/interest branches are exercised by the
rulespec-gh companion tests.

Input convention and license discipline follow ``gh_income_tax``: monetary
inputs pre-divide by the GH_2025 employment-income uprating index, the
post-uprating bridge keeps both engines on an identical base (bridged on
``ypr`` here), and no SOUTHMOD model XML, dataset row, or DRD text is
committed — expected values are values GHAMOD itself produced.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .gh_income_tax import (
    EUROMOD_TO_AXIOM_INPUT_BRIDGE,
    GH_METADATA,
    GH_PERIOD,
    GH_UPRATE_2017_TO_2025,
    _gh_base_row,
)

CAPITAL_MODULE = (
    "gh:statutes/act-896/income-tax-2015/"
    "first-schedule-8-rates-of-withholding-tax"
)


def _capital_input(name: str) -> str:
    return f"{CAPITAL_MODULE}#{name}"


# Annual residential rent sweep (nominal GHS). The rate is flat so any
# positive rent validates it; the sweep spans modest to high rents to pin
# scale-independence. Expected annual amounts (GHAMOD-produced, probed
# live): 8% of rent — 960 · 1,920 · 4,800.
_RENT_INCOME_GRID: tuple[tuple[str, float], ...] = (
    ("12k", 12_000.0),
    ("24k", 24_000.0),
    ("60k", 60_000.0),
)


def gh_capital_income_cases() -> list[Case]:
    """Residential-rent withholding cases for the GHAMOD tinrt_s oracle."""
    return [
        _rent_case(f"gh-rent-{label}", rent)
        for label, rent in _RENT_INCOME_GRID
    ]


def _gh_rentier(idperson: int, annual_rent: float) -> dict[str, float | int]:
    """A household head whose only income is residential rent (ypr)."""
    monthly = (annual_rent / GH_UPRATE_2017_TO_2025) / 12.0
    row = _gh_base_row(1, idperson)
    row.update({"dag": 45, "dhh": 1, "ypr": monthly})
    return row


def _rent_case(case_id: str, annual_rent: float) -> Case:
    rent_input = _capital_input("input.residential_rent_received")
    return Case(
        case_id=case_id,
        period=GH_PERIOD,
        metadata={
            **GH_METADATA,
            "scenario": "single-individual-residential-rent-withholding",
            "annual_residential_rent": annual_rent,
            # Placeholder; the post-uprating euromod ypr overwrites it via the
            # bridge so both engines price the identical rent base.
            "axiom_inputs": {
                rent_input: annual_rent,
                _capital_input("input.dividends_from_resident_companies"): 0.0,
                _capital_input(
                    "input.non_exempt_interest_paid_to_individual"
                ): 0.0,
                _capital_input("input.nonresidential_rent_received"): 0.0,
            },
            "euromod_inputs": [_gh_rentier(101, annual_rent)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"ypr": [rent_input]},
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 45,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.RENTAL_INCOME: annual_rent,
                },
            ),
        ),
        outputs=(Concepts.GH_INDIVIDUAL_RESIDENTIAL_RENT_WITHHOLDING,),
    )
