"""Uganda PAYE income-tax oracle suite (UGAMOD ``tin_s``).

``ug-paye-rate-schedule`` compares the rulespec-ug resident individual
income-tax schedule — the Income Tax Act (Cap. 340) Third Schedule
Part I as substituted by Act 4 of 2012 (nil to 2,820,000; 10% to
4,020,000; 20% to 4,920,000; 30% above; an additional 10% on chargeable
income exceeding 120,000,000 per year) — against UGAMOD ``tin_s`` on a
band-boundary and interior income sweep, including the additional-rate
region, which UGAMOD implements (probed live: monthly chargeable income
10,375,626.04 returns 3,052,250.38 = 25,000 + 30% x excess-over-410,000
+ 10% x excess-over-10,000,000 — in contrast to GHAMOD's missing Act
1111 top band).

UGAMOD is the SOUTHMOD tax-benefit model for Uganda (UNU-WIDER / the
Ministry of Finance, Planning and Economic Development), run on the
EUROMOD engine (SOUTHMOD A4.0, country UG, system UG_2025, dataset
ug_2024_a1). UGAMOD's tax base for a plain formal employee is gross
employment income (probed: ``ttb_s`` = ``yem``), so both engines apply
the schedule to the identical base: each case pre-divides the euromod
input by the UG_2025 employment-income uprating index and bridges
Axiom's ``chargeable_income`` on the engine's own post-uprating ``yem``.

License discipline as in ``gh_income_tax``: the bundle is referenced by
path only; expected values are values UGAMOD itself produced; no bundle
content is committed.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .gh_income_tax import EUROMOD_TO_AXIOM_INPUT_BRIDGE

RATE_MODULE = (
    "ug:statutes/act-2012-4/income-tax-amendment-2012/"
    "third-schedule-rates-of-tax-substituted"
)

# Ugandan year of income FY2025/26 (the rulespec-ug validation year).
# UGAMOD resolves its policy year from the system name (UG_2025 =
# FY2025/26) and ignores the case period; the substituted Third Schedule
# is unchanged from 1 July 2012 through FY2025/26, so the Axiom-side
# calendar query period reads the identical amounts.
UG_PERIOD = "2026"

# Employment-income uprating index applied by UGAMOD UG_2025 to the
# 2024-vintage ug_2024_a1 dataset, probed live (input yem 100,000/month
# -> engine yem 103,756.26). Rows pre-divide by this so the engine
# prices the intended nominal gross; the post-uprating bridge keeps
# parity exact even if a future release re-indexes.
UG_UPRATE_2024_TO_2025 = 1.0375626043405675

UG_SCOPE = {"type": "country", "geoid": "UG"}
UG_METADATA = {
    "locale": "UG",
    "scope": UG_SCOPE,
    "axiom_entity": "Person",
    "axiom_entity_id": "head",
}

# Annual gross incomes (post-uprating UGX): every band boundary, an
# interior point per band, the live-probe income (6,225,375.60 ->
# statutory 691,612.68 = 12 x the probed monthly tin_s 57,634.37), and
# the additional-rate boundary and interior.
_RATE_INCOME_GRID = (
    ("2m-nil-interior", 2_000_000.0),
    ("2820000-nil-band-top", 2_820_000.0),
    ("3420000-10pct-interior", 3_420_000.0),
    ("4020000-10pct-band-top", 4_020_000.0),
    ("4500000-20pct-interior", 4_500_000.0),
    ("4920000-20pct-band-top", 4_920_000.0),
    ("6m-30pct-interior", 6_000_000.0),
    ("probe-income-30pct", 6_225_375.60),
    ("120m-additional-rate-boundary", 120_000_000.0),
    ("150m-additional-rate-interior", 150_000_000.0),
)


def _em_monthly(annual: float) -> float:
    return (annual / UG_UPRATE_2024_TO_2025) / 12.0


def _ug_base_row(idhh: int, idperson: int) -> dict[str, float | int]:
    return {
        "idhh": idhh,
        "idperson": idperson,
        "idpartner": 0,
        "idmother": 0,
        "idfather": 0,
        "dwt": 1.0,
        "dag": 35,
        "dgn": 1,
        "dms": 1,
        "dhh": 1,
        "les": 0,
        "lfo": 0,
        "ddi": 0,
        "deh": 0,
        "yem": 0.0,
        "yem00": 0.0,
    }


def _ug_formal_earner(idperson: int, annual_income: float) -> dict[str, float | int]:
    monthly = _em_monthly(annual_income)
    row = _ug_base_row(1, idperson)
    row.update({"les": 3, "lfo": 1, "yem": monthly, "yem00": monthly})
    return row


def ug_paye_rate_schedule_cases() -> list[Case]:
    """Single formal-sector employee PAYE cases for the UGAMOD tin_s oracle."""
    return [
        _rate_schedule_case(f"ug-paye-{label}", income)
        for label, income in _RATE_INCOME_GRID
    ]


def _rate_schedule_case(case_id: str, annual_income: float) -> Case:
    chargeable_income = f"{RATE_MODULE}#input.chargeable_income"
    return Case(
        case_id=case_id,
        period=UG_PERIOD,
        metadata={
            **UG_METADATA,
            "scenario": "single-formal-employee-paye-schedule",
            "yearly_earned_income": annual_income,
            # Placeholder; the post-uprating euromod yem overwrites it via the
            # bridge so both engines price the identical schedule base.
            "axiom_inputs": {chargeable_income: annual_income},
            "euromod_inputs": [_ug_formal_earner(101, annual_income)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"yem": [chargeable_income]},
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 35,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.YEARLY_EARNED_INCOME: annual_income,
                },
            ),
        ),
        outputs=(Concepts.UG_RESIDENT_INCOME_TAX,),
    )
