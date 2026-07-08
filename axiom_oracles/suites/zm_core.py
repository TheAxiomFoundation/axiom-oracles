"""Zambia core tax and social-insurance oracle suites (MicroZAMOD).

Four suites covering rulespec-zm instruments 1-6 (rulespec-zm#1)
against MicroZAMOD, the SOUTHMOD tax-benefit model for Zambia
(UNU-WIDER / Ministry of Finance and National Planning / ZIPAR), run
on the EUROMOD engine (SOUTHMOD A4.0, country ZM, dataset zm_2022_a2;
employment/turnover uprating index ZM_2025 = 1.4429509825568556,
probed). Zambia's charge year is the calendar year.

``zm-paye-rate-schedule`` (ZM_2025) — the Act 22 of 2023 Charging
Schedule paragraph 2(1) rates (0/61,200; 20%/85,200; 30%/110,400; 37%
above) against ``tin_s``. MicroZAMOD applies the identical schedule to
a base NET of employee NAPSA and NHIMA contributions (probed:
``ttb_s = yem - tsceepi_s - tsceehl_s``), which the CY2025 statute
does not support: Act 22 of 2024 s.4 substitutes s.37(1) with an
employer-only approved-fund deduction, s.2 deletes the approved-fund
definitions, and neither NHI instrument carries a deductibility
provision (rulespec-zm#1 candidate finding 1; probed magnitude:
PAYE understated 9,101.29/yr at 409,968 gross). The suite therefore
bridges the engine's own post-computation ``ttb_s`` onto the module's
``individual_income`` input so the live cases verify the SCHEDULE
arithmetic exactly; the base divergence is dispositioned with probed
values in the comparison description and the rulespec-zm#1 ledger.

``zm-turnover`` (ZM_2025) — the Act 22 of 2024 Ninth Schedule Part II
rows (0% at or below K12,000; 5% above K12,000 up to K5,000,000, slab
on the whole turnover) with the s.64A five-million-kwacha ceiling,
against ``ttn_s``. Live cases sit in the agreement zone (above 12,000,
below 5,000,000) where both engines return 5% x turnover exactly.
Probed divergences (candidate findings 2a/2b, dispositioned): the
model taxes from the first kwacha (ytn 10,000 -> 500.00 and ytn
12,000 -> 600.00 where the statutory row prescribes 0 percent) and
uses a strict bound at the ceiling (ytn exactly 5,000,000 -> 0 where
s.64A(2) reads "five million kwacha or less" -> 250,000).

``zm-napsa-contributions`` (ZM_2024) — the S.I. No. 9 of 2024 schedules
(5% employee + 5% employer of total pensionable earnings; monthly
social security ceiling K29,816) against ``tsceepi_s``/``tscerpi_s``
run on the ZM_2024 system, whose cap (K1,490.80/month each) equals the
SI value exactly. The ZM_2025 cap (K1,708.20 = 5% x 34,164 = 5% x 4 x
the ZamStats NAE of 8,541) matches the s.19(3) formula arithmetically
but has no dedicated statutory instrument (SIs published for 2021,
2024, 2026 only) — recorded as a documentation note, not a finding.

``zm-nhima-contributions`` (ZM_2025) — the S.I. No. 63 of 2019 Third
Schedule rates (employee 1% of basic salary; employer 1%; uncapped)
against ``tsceehl_s``/``tscerhl_s`` — probed exact at all incomes
including 144,295.10/month.

The euromod-side monthly convention: each case pre-divides the annual
target by the uprating index and by 12 so the engine prices the
intended nominal value; bridges map the engine's own post-uprating
outputs onto the Axiom inputs (with divide_by 12 where the Axiom
module is monthly), so parity stays exact even if a future release
re-indexes.

License discipline as in ``gh_income_tax``/``ug_income_tax``: the
SOUTHMOD bundle is referenced by path only; expected values are values
MicroZAMOD itself produced; no bundle content is committed.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .gh_income_tax import EUROMOD_TO_AXIOM_INPUT_BRIDGE

PAYE_MODULE = "zm:statutes/act-2023-22/income-tax-amendment-2023"
TURNOVER_MODULE = "zm:statutes/act-2024-22/income-tax-amendment-2024"
NAPSA_MODULE = "zm:regulations/si-2024-9/pensionable-earnings-amendment-2024"
NHIMA_MODULE = (
    "zm:regulations/si-2019-63/national-health-insurance-general-regulations-2019"
)

# Calendar charge years (the Axiom-side query periods).
ZM_PERIOD_2025 = "2025"
ZM_PERIOD_2024 = "2024"

# Employment/turnover uprating index applied by ZM_2025 to the
# 2022-vintage zm_2022_a2 dataset, probed live (yem 100,000/month ->
# engine 144,295.10). ZM_2024 applies a different index; the ZM_2024
# NAPSA suite relies on the post-uprating bridge rather than the
# pre-division landing exactly on a target.
ZM_UPRATE_2022_TO_2025 = 1.4429509825568556

ZM_SCOPE = {"type": "country", "geoid": "ZM"}
ZM_METADATA = {
    "locale": "ZM",
    "scope": ZM_SCOPE,
    "axiom_entity": "Person",
    "axiom_entity_id": "head",
}


def _zm_base_row(idhh: int, idperson: int) -> dict[str, float | int]:
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
        "yem": 0.0,
    }


def _zm_formal_earner(idperson: int, annual_income: float) -> dict[str, float | int]:
    monthly = (annual_income / ZM_UPRATE_2022_TO_2025) / 12.0
    row = _zm_base_row(1, idperson)
    row.update({"les": 3, "lfo": 1, "yem": monthly})
    return row


def _zm_turnover_earner(idperson: int, annual_turnover: float) -> dict[str, float | int]:
    monthly = (annual_turnover / ZM_UPRATE_2022_TO_2025) / 12.0
    row = _zm_base_row(1, idperson)
    row.update({"ytn": monthly})
    return row


# ---------------------------------------------------------------------------
# zm-paye-rate-schedule (ZM_2025, tin_s on the bridged ttb_s base)
# ---------------------------------------------------------------------------

# Annual gross employment incomes: every band boundary and an interior
# point per band on the GROSS side; the engine's own net ttb_s is
# bridged onto the module input, so the schedule is exercised at the
# post-deduction incomes these produce.
_PAYE_INCOME_GRID = (
    ("40000-nil-interior", 40_000.0),
    ("61200-exempt-bound-gross", 61_200.0),
    ("75000-band2-interior", 75_000.0),
    ("90000-band3-interior", 90_000.0),
    ("120000-band4-lower-region", 120_000.0),
    ("240000-band4-interior", 240_000.0),
    ("409968-napsa-cap-region", 409_968.0),
    ("600000-high-income", 600_000.0),
)


def zm_paye_rate_schedule_cases() -> list[Case]:
    """Single formal-sector employee PAYE cases for the tin_s oracle."""
    return [
        _paye_case(f"zm-paye-{label}", income)
        for label, income in _PAYE_INCOME_GRID
    ]


def _paye_case(case_id: str, annual_income: float) -> Case:
    individual_income = f"{PAYE_MODULE}#input.individual_income"
    return Case(
        case_id=case_id,
        period=ZM_PERIOD_2025,
        metadata={
            **ZM_METADATA,
            "scenario": "single-formal-employee-paye-schedule",
            "yearly_earned_income": annual_income,
            # Placeholder; the engine's own post-deduction taxable base
            # (ttb_s) overwrites it via the bridge so both engines price
            # the identical schedule base (the gross-vs-net base
            # divergence is candidate finding 1, dispositioned in the
            # comparison description).
            "axiom_inputs": {individual_income: annual_income},
            "euromod_inputs": [_zm_formal_earner(101, annual_income)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"ttb_s": [individual_income]},
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
        outputs=(Concepts.ZM_INDIVIDUAL_INCOME_TAX,),
    )


# ---------------------------------------------------------------------------
# zm-turnover (ZM_2025, ttn_s in the agreement zone)
# ---------------------------------------------------------------------------

# Annual turnover targets inside the agreement zone (above the 12,000
# free band, below the 5,000,000 ceiling) where both engines return
# 5% x turnover exactly. The boundary divergences (10,000 and 12,000
# -> statutory 0 vs model 500/600; exactly 5,000,000 -> statutory
# 250,000 vs model 0) are dispositioned, not live cases.
_TURNOVER_GRID = (
    ("20000-low-interior", 20_000.0),
    ("100000-interior", 100_000.0),
    ("800000-old-threshold", 800_000.0),
    ("2500000-mid-interior", 2_500_000.0),
    ("4999999-below-ceiling", 4_999_999.0),
)


def zm_turnover_cases() -> list[Case]:
    """Small-business turnover-tax cases for the ttn_s oracle."""
    return [
        _turnover_case(f"zm-turnover-{label}", turnover)
        for label, turnover in _TURNOVER_GRID
    ]


def _turnover_case(case_id: str, annual_turnover: float) -> Case:
    turnover_input = f"{TURNOVER_MODULE}#input.annual_turnover"
    return Case(
        case_id=case_id,
        period=ZM_PERIOD_2025,
        metadata={
            **ZM_METADATA,
            "scenario": "small-business-turnover-tax",
            "yearly_turnover": annual_turnover,
            # Placeholder; the engine's post-uprating ytn overwrites it
            # via the bridge so both engines price the identical base.
            "axiom_inputs": {turnover_input: annual_turnover},
            "euromod_inputs": [_zm_turnover_earner(101, annual_turnover)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"ytn": [turnover_input]},
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 35,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                },
            ),
        ),
        outputs=(Concepts.ZM_TURNOVER_TAX,),
    )


# ---------------------------------------------------------------------------
# zm-napsa-contributions (ZM_2024 — the SI 9/2024 statutory year)
# ---------------------------------------------------------------------------

# Monthly earnings targets around the CY2024 ceiling of K29,816
# (contribution cap K1,490.80 each side). Run on the ZM_2024 system so
# the oracle prices the same statutory year as the encoded SI; the
# bridge divides the annualized engine yem back to the module's
# monthly input.
_NAPSA_MONTHLY_GRID = (
    ("10000-below-ceiling", 10_000.0),
    ("29816-at-ceiling", 29_816.0),
    ("45000-above-ceiling", 45_000.0),
)


def zm_napsa_contributions_cases() -> list[Case]:
    """Formal-employee NAPSA cases for the tsceepi_s/tscerpi_s oracles."""
    return [
        _napsa_case(f"zm-napsa-{label}", monthly)
        for label, monthly in _NAPSA_MONTHLY_GRID
    ]


def _napsa_case(case_id: str, monthly_earnings: float) -> Case:
    earnings_input = f"{NAPSA_MODULE}#input.monthly_earnings"
    annual = monthly_earnings * 12.0
    return Case(
        case_id=case_id,
        period=ZM_PERIOD_2024,
        metadata={
            **ZM_METADATA,
            "scenario": "formal-employee-napsa-contributions",
            "monthly_earnings": monthly_earnings,
            # Placeholder; the engine's post-uprating yem (annualized by
            # the runner) overwrites it via the bridge, divided back to
            # the module's monthly basis.
            "axiom_inputs": {earnings_input: monthly_earnings},
            "euromod_inputs": [
                # ZM_2024 applies its own uprating index; the bridge
                # carries the engine's actual yem, so the pre-division
                # here only needs to land in the right region.
                {**_zm_base_row(1, 101), "les": 3, "lfo": 1,
                 "yem": monthly_earnings / ZM_UPRATE_2022_TO_2025},
            ],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yem": {"inputs": [earnings_input], "divide_by": 12}
            },
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 35,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.YEARLY_EARNED_INCOME: annual,
                },
            ),
        ),
        outputs=(
            Concepts.ZM_NAPSA_EMPLOYEE_CONTRIBUTION,
            Concepts.ZM_NAPSA_EMPLOYER_CONTRIBUTION,
        ),
    )


# ---------------------------------------------------------------------------
# zm-nhima-contributions (ZM_2025, uncapped 1% each side)
# ---------------------------------------------------------------------------

_NHIMA_MONTHLY_GRID = (
    ("5000-low", 5_000.0),
    ("34164-napsa-ceiling-region", 34_164.0),
    ("144295-high-income", 144_295.10),
)


def zm_nhima_contributions_cases() -> list[Case]:
    """Formal-employee NHIMA cases for the tsceehl_s/tscerhl_s oracles."""
    return [
        _nhima_case(f"zm-nhima-{label}", monthly)
        for label, monthly in _NHIMA_MONTHLY_GRID
    ]


def _nhima_case(case_id: str, monthly_salary: float) -> Case:
    salary_input = f"{NHIMA_MODULE}#input.basic_salary"
    annual = monthly_salary * 12.0
    return Case(
        case_id=case_id,
        period=ZM_PERIOD_2025,
        metadata={
            **ZM_METADATA,
            "scenario": "formal-employee-nhima-contributions",
            "monthly_basic_salary": monthly_salary,
            "axiom_inputs": {salary_input: monthly_salary},
            "euromod_inputs": [_zm_formal_earner(101, annual)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yem": {"inputs": [salary_input], "divide_by": 12}
            },
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 35,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.YEARLY_EARNED_INCOME: annual,
                },
            ),
        ),
        outputs=(
            Concepts.ZM_NHIMA_EMPLOYEE_CONTRIBUTION,
            Concepts.ZM_NHIMA_EMPLOYER_CONTRIBUTION,
        ),
    )
