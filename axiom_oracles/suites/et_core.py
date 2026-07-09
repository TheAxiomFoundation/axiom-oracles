"""Ethiopia core tax oracle suites (ETMOD).

Five suites covering rulespec-et instruments 1-6 (rulespec-et#1)
against ETMOD, the SOUTHMOD tax-benefit model for Ethiopia
(UNU-WIDER), run on the EUROMOD engine (SOUTHMOD A4.0, country ET,
system ET_2025 = EFY2025/26, dataset et_2022_a2; employment uprating
index 1.7035555555555557, probed). ET_2025 carries the Income Tax
(Amendment) Proclamation No. 1395/2025 schedules effective July 2025.

``et-paye-rate-schedule`` — the Article 11 monthly employment schedule
(0% to 2,000; 15/20/25/30% bands; 35% above 14,000) against ``tin01_s``
on the FULL grid: the statutory base is gross employment income
(Proclamation 979/2016 Articles 10(3) and 65(1)(c) verified - no
employee deduction exists), and ETMOD taxes gross - probed exact to
the birr at eight incomes, so there is no shared-nil restriction.

``et-presumptive`` — the Article 50 gross-receipts schedule (marginal
2/3/5/7/9% to 2,000,000) against ``ttn_s`` - probed exact at interior
and band-edge receipts.

``et-business-mat`` — the annual business schedule against ``tin02_s``
in the agreement zone (Category A taxpayers whose scheduled tax meets
the 2.5%-of-turnover floor, where the Article 23 minimum tax is
dormant in both engines). Dispositions (rulespec-et#1 findings 1-2,
probed live, adjudicated against the Article 23 verbatim text):
(1) ETMOD ADDS the full 2.5% of turnover to the scheduled tax where
sub-article 3 reduces the minimum by the tax paid - a floor (probed
81,000 vs statutory 75,000 at 3,000,000 receipts / 60,000 income);
(2) ETMOD levies the minimum tax on Article 49 gross-revenue-regime
taxpayers whom sub-article 4 excludes (probed 1,250 of tin02_s at
50,000 receipts alongside the presumptive 1,000).

``et-pension-contributions`` — the Proclamation 715/2011 private
shares (employee 7%, employer 11%) and the Proclamation 714/2011
Article 11 military-and-police office rate (25%) against
``tscee_s``/``tscer_s`` - probed exact. ETMOD keys the employer rate
on ``loc``: loc=0 pays 25% (military/police), any other loc pays 11%.

``et-vat`` — the VAT Proclamation No. 1341/2024 standard rate (15%)
and the Directive No. 1021/2024 domestic electricity (200 kWh) and
water (15 cubic meters) monthly thresholds against ``tva_s``.
Consumption x-vars carry their own per-group uprating indices
(probed: 1.4959 fuel/utilities, 1.4427 water), so expenditure cases
bridge the engine's own post-uprating values; threshold quantities
(q-vars) pass unuprated. Threshold semantics probed: the full
expenditure becomes taxable once monthly consumption exceeds the
threshold, matching the encoded reading of the directive.

License discipline as elsewhere: the SOUTHMOD bundle is referenced by
path only; expected values are values ETMOD itself produced; no
bundle content is committed.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .gh_income_tax import EUROMOD_TO_AXIOM_INPUT_BRIDGE

TAX_MODULE = "et:statutes/proc-1395-2025/income-tax-amendment-2025"
PRIVATE_PENSION_MODULE = "et:statutes/proc-715-2011/private-organization-employees-pension"
PUBLIC_PENSION_MODULE = "et:statutes/proc-714-2011/public-servants-pension"
VAT_MODULE = "et:statutes/proc-1341-2024/value-added-tax-proclamation"

# EFY2025/26; the Axiom-side query period (the module effective dates
# begin 2025-07-08).
ET_PERIOD = "2026"

# Employment uprating index applied by ET_2025 to the 2022-vintage
# et_2022_a2 dataset, probed live (yem 1,000/month -> 1,703.56).
ET_UPRATE_2022_TO_2025 = 1.7035555555555557

ET_SCOPE = {"type": "country", "geoid": "ET"}
ET_METADATA = {
    "locale": "ET",
    "scope": ET_SCOPE,
    "axiom_entity": "Person",
    "axiom_entity_id": "head",
}


def _et_base_row(idhh: int, idperson: int) -> dict[str, float | int]:
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
        "lfo": 1,
        "les": 3,
        "yem": 0.0,
    }


def _et_formal_earner(idperson: int, monthly_target: float, *, loc: int = 1) -> dict[str, float | int]:
    row = _et_base_row(1, idperson)
    row.update({"yem": monthly_target / ET_UPRATE_2022_TO_2025, "loc": loc})
    return row


def _et_business(idperson: int, receipts_target: float, income_target: float) -> dict[str, float | int]:
    row = _et_base_row(1, idperson)
    row.update({
        "ytn": (receipts_target / ET_UPRATE_2022_TO_2025) / 12.0,
        "yse": (income_target / ET_UPRATE_2022_TO_2025) / 12.0,
    })
    return row


# ---------------------------------------------------------------------------
# et-paye-rate-schedule (full grid; the statutory base is gross)
# ---------------------------------------------------------------------------

_PAYE_MONTHLY_GRID = (
    ("1000-nil-interior", 1_000.0),
    ("2000-exempt-bound", 2_000.0),
    ("3000-band2-interior", 3_000.0),
    ("4000-band2-top", 4_000.0),
    ("7000-band3-top", 7_000.0),
    ("10000-band4-top", 10_000.0),
    ("14000-band5-top", 14_000.0),
    ("20000-top-band-interior", 20_000.0),
)


def et_paye_rate_schedule_cases() -> list[Case]:
    """Single formal-sector employee PAYE cases for the tin01_s oracle."""
    return [
        _paye_case(f"et-paye-{label}", monthly)
        for label, monthly in _PAYE_MONTHLY_GRID
    ]


def _paye_case(case_id: str, monthly_target: float) -> Case:
    income_input = f"{TAX_MODULE}#input.monthly_employment_income"
    return Case(
        case_id=case_id,
        period=ET_PERIOD,
        metadata={
            **ET_METADATA,
            "scenario": "single-formal-employee-paye-schedule",
            "monthly_employment_income": monthly_target,
            # Placeholder; the engine's post-uprating yem (annualized by
            # the runner) overwrites it via the bridge, divided back to
            # the module's monthly basis.
            "axiom_inputs": {income_input: monthly_target},
            "euromod_inputs": [_et_formal_earner(101, monthly_target)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yem": {"inputs": [income_input], "divide_by": 12}
            },
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 35,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.YEARLY_EARNED_INCOME: monthly_target * 12.0,
                },
            ),
        ),
        outputs=(Concepts.ET_EMPLOYMENT_INCOME_TAX,),
    )


# ---------------------------------------------------------------------------
# et-presumptive (ttn_s, exact marginal schedule)
# ---------------------------------------------------------------------------

_PRESUMPTIVE_GRID = (
    ("50000-band1", 50_000.0),
    ("100000-band1-top", 100_000.0),
    ("400000-band2", 400_000.0),
    ("900000-band3", 900_000.0),
    ("1900000-band5", 1_900_000.0),
)


def et_presumptive_cases() -> list[Case]:
    """Small-business gross-receipts cases for the ttn_s oracle."""
    return [
        _presumptive_case(f"et-presumptive-{label}", receipts)
        for label, receipts in _PRESUMPTIVE_GRID
    ]


def _presumptive_case(case_id: str, receipts_target: float) -> Case:
    receipts_input = f"{TAX_MODULE}#input.annual_gross_receipts"
    return Case(
        case_id=case_id,
        period=ET_PERIOD,
        metadata={
            **ET_METADATA,
            "scenario": "small-business-presumptive-tax",
            "annual_gross_receipts": receipts_target,
            "axiom_inputs": {receipts_input: receipts_target},
            "euromod_inputs": [_et_business(101, receipts_target, receipts_target * 0.4)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"ytn": [receipts_input]},
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
        outputs=(Concepts.ET_PRESUMPTIVE_TAX,),
    )


# ---------------------------------------------------------------------------
# et-business-mat (tin02_s in the MAT-dormant agreement zone)
# ---------------------------------------------------------------------------

_BUSINESS_GRID = (
    # (label, annual receipts target, annual business income target) -
    # scheduled tax comfortably above the 2.5%-of-receipts floor, so
    # the minimum tax is dormant in both engines. ETMOD's tin02 base is
    # business income net of the employer pension (zero here: no yem).
    ("2500000-high-margin", 2_500_000.0, 1_000_000.0),
    ("3000000-mid-margin", 3_000_000.0, 1_200_000.0),
    ("4000000-comfortable", 4_000_000.0, 2_000_000.0),
)


def et_business_mat_cases() -> list[Case]:
    """Category A business-income cases (MAT dormant) for tin02_s."""
    return [
        _business_case(f"et-business-{label}", receipts, income)
        for label, receipts, income in _BUSINESS_GRID
    ]


def _business_case(case_id: str, receipts_target: float, income_target: float) -> Case:
    income_input = f"{TAX_MODULE}#input.taxable_business_income"
    receipts_input = f"{TAX_MODULE}#input.annual_gross_receipts"
    return Case(
        case_id=case_id,
        period=ET_PERIOD,
        metadata={
            **ET_METADATA,
            "scenario": "category-a-business-income-tax",
            "annual_gross_receipts": receipts_target,
            "annual_business_income": income_target,
            "axiom_inputs": {
                income_input: income_target,
                receipts_input: receipts_target,
            },
            "euromod_inputs": [_et_business(101, receipts_target, income_target)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yse": [income_input],
                "ytn": [receipts_input],
            },
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
        outputs=(Concepts.ET_BUSINESS_INCOME_TAX_PAYABLE,),
    )


# ---------------------------------------------------------------------------
# et-pension-contributions (7%/11% private; 25% military office)
# ---------------------------------------------------------------------------

def et_pension_contributions_cases() -> list[Case]:
    """Formal-employee pension cases for the tscee_s/tscer_s oracles."""
    cases = []
    for label, monthly, loc in (
        ("private-10000", 10_000.0, 1),
        ("private-3000", 3_000.0, 1),
    ):
        income_input = f"{PRIVATE_PENSION_MODULE}#input.monthly_salary"
        cases.append(
            Case(
                case_id=f"et-pension-{label}",
                period=ET_PERIOD,
                metadata={
                    **ET_METADATA,
                    "scenario": "private-organization-pension-contributions",
                    "monthly_salary": monthly,
                    "axiom_inputs": {income_input: monthly},
                    "euromod_inputs": [_et_formal_earner(101, monthly, loc=loc)],
                    EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                        "yem": {"inputs": [income_input], "divide_by": 12}
                    },
                },
                entities=(
                    Entity(
                        entity_id="head",
                        kind="person",
                        facts={
                            Concepts.PERSON_AGE: 35,
                            Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                            Concepts.YEARLY_EARNED_INCOME: monthly * 12.0,
                        },
                    ),
                ),
                outputs=(
                    Concepts.ET_PRIVATE_EMPLOYEE_PENSION,
                    Concepts.ET_PRIVATE_EMPLOYER_PENSION,
                ),
            )
        )
    # Military/police office rate (loc=0): the office pays 25%.
    income_input = f"{PUBLIC_PENSION_MODULE}#input.monthly_salary"
    cases.append(
        Case(
            case_id="et-pension-military-office-25pct",
            period=ET_PERIOD,
            metadata={
                **ET_METADATA,
                "scenario": "military-police-office-pension-contribution",
                "monthly_salary": 10_000.0,
                "axiom_inputs": {income_input: 10_000.0},
                "euromod_inputs": [_et_formal_earner(101, 10_000.0, loc=0)],
                EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                    "yem": {"inputs": [income_input], "divide_by": 12}
                },
            },
            entities=(
                Entity(
                    entity_id="head",
                    kind="person",
                    facts={
                        Concepts.PERSON_AGE: 35,
                        Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                        Concepts.YEARLY_EARNED_INCOME: 120_000.0,
                    },
                ),
            ),
            outputs=(Concepts.ET_MILITARY_OFFICE_PENSION,),
        )
    )
    return cases


# ---------------------------------------------------------------------------
# et-vat (15% + electricity/water thresholds)
# ---------------------------------------------------------------------------

def et_vat_cases() -> list[Case]:
    """VAT cases: electricity and water threshold arms for tva_s."""
    cases = []
    for label, xvar, qvar, q_monthly, exp_input, q_input in (
        ("electricity-above-threshold", "x0451", "q0451", 300.0,
         "electricity_expenditure", "monthly_electricity_kwh"),
        ("water-above-threshold", "x044", "q044", 20.0,
         "water_expenditure", "monthly_water_cubic_meters"),
    ):
        expenditure = f"{VAT_MODULE}#input.{exp_input}"
        quantity = f"{VAT_MODULE}#input.{q_input}"
        row = _et_base_row(1, 101)
        row.update({xvar: 100.0, qvar: q_monthly})
        cases.append(
            Case(
                case_id=f"et-vat-{label}",
                period=ET_PERIOD,
                metadata={
                    **ET_METADATA,
                    "scenario": "household-vat-utility-thresholds",
                    "axiom_inputs": {expenditure: 1_200.0, quantity: q_monthly},
                    "euromod_inputs": [row],
                    # The engine's post-uprating expenditure overwrites the
                    # placeholder; the quantity passes unuprated.
                    EUROMOD_TO_AXIOM_INPUT_BRIDGE: {xvar: [expenditure]},
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
                outputs=(
                    Concepts.ET_ELECTRICITY_VAT
                    if xvar == "x0451"
                    else Concepts.ET_WATER_VAT,
                ),
            )
        )
    return cases
