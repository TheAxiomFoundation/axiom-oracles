"""Ethiopia core tax oracle suites (ETMOD).

Five suites covering rulespec-et instruments 1-6 (rulespec-et#1)
against ETMOD, the SOUTHMOD tax-benefit model for Ethiopia
(UNU-WIDER), run on the EUROMOD engine (SOUTHMOD A4.0, country ET,
system ET_2025 = EFY2025/26, dataset et_2022_a2; employment uprating
index 1.7035555555555557, probed). ET_2025 carries the Income Tax
(Amendment) Proclamation No. 1395/2025 schedules effective July 2025.

Period basis: the Article 11 schedule and the pension shares are
Month-period modules, so ``et-paye-rate-schedule`` and
``et-pension-contributions`` (and ``et-dispy``) run with
``euromod_annualize_outputs: false`` - ETMOD's monthly outputs and the
bridged monthly ``yem`` are compared and fed as-is (no x12 on the
outputs, no /12 on the bridge). The business, presumptive and VAT
suites are annual: the runner annualizes ETMOD's monthly outputs and
bridged inputs onto the modules' Year-period basis.

``et-paye-rate-schedule`` — the Article 11 monthly employment schedule
(0% to 2,000; 15/20/25/30% bands; 35% above 14,000) against ``tin01_s``
on the FULL grid: the statutory base is gross employment income
(Proclamation 979/2016 Articles 10(3) and 65(1)(c) verified - no
employee deduction exists), and ETMOD taxes gross - run live exact at
eight incomes, so there is no shared-nil restriction.

``et-presumptive`` — the Article 50 gross-receipts schedule (marginal
2/3/5/7/9% to 2,000,000) against ``ttn_s`` - run live exact at
interior and band-edge receipts. "Marginal" is how both engines read
the Article 50 table (the table itself lists only receipts bands and
percentages).

``et-business-mat`` — the annual business schedule against ``tin02_s``.
Three Category A cases sit in the agreement zone (scheduled tax above
the 2.5%-of-turnover floor, so the Article 23 minimum tax is dormant in
both engines). Two more cases, one per ETMOD finding in
``axiom_oracles/data/etmod_issues.json`` (rulespec-et#1 findings 1-2,
adjudicated against the Article 23 text), are expected mismatches with
dispositions in ``dispositions/et-business-mat.yaml``: (1) ETMOD ADDS
the full 2.5% of turnover to the scheduled tax where sub-article 3
reduces the minimum by the tax paid - a floor (81,000 vs the statutory
75,000 at 3,000,000 receipts / 60,000 income); (2) ETMOD levies the
minimum tax on Article 49 gross-revenue-regime (Category B) taxpayers
whom sub-article 4 excludes (1,250 at 50,000 receipts / 20,000 income,
where the statutory business income tax is 0). The finding-2 case keeps
income in the 0-24,000 nil band on purpose: the encoded
``business_income_tax_payable`` has no Category B gate (Article 19(2)
applies the schedule to individuals "with the exception of Category B
taxpayers"), so above that band it would also tax a Category B
taxpayer (probed 2026-10-04: 325,400 at 1,900,000 receipts / 1,000,000
income, where ETMOD returns 47,500, the minimum tax alone). That is an
Axiom encoding gap, reported for an encoder repair round and not
compared here.

``et-pension-contributions`` — the Proclamation 715/2011 private
shares (employee 7%, employer 11%) and the Proclamation 714/2011
Article 11 military-and-police office rate (25%) against
``tscee_s``/``tscer_s`` - run live exact. ETMOD keys the employer rate
on ``loc`` (probed: loc=0 gave 25%, the military/police class; loc=1
gave 11%).
The runner queries both proclamations' outputs on every case; both
modules read an input named ``monthly_salary``, which the Axiom side
resolves by that bare name, so the one bridged salary covers both and
only the applicable sector's outputs are compared.

``et-vat`` — the VAT Proclamation No. 1341/2024 standard rate (15%)
and the Directive No. 1021/2024 domestic electricity (200 kWh) and
water (15 cubic meters) monthly thresholds against ``tva_s``.
Consumption x-vars carry their own per-group uprating indices
(probed: 1.4959 fuel/utilities, 1.4427 water), so expenditure cases
bridge the engine's own post-uprating values; threshold quantities
(q-vars) pass unuprated. ETMOD echoes these utility x-vars in its
output frame, so the x-var bridge applies (unlike RWAMOD's detailed
COICOP food items). Convention adopted for parity: ETMOD treats household
spending on electricity and water as the VAT-exclusive taxable value, and
Axiom is given that same value, so the cases test the 15% rate and the
thresholds on the model's base, not the statutory taxable value. Each
arm runs well above, at, and one unit above
the threshold: both engines exempt the whole expenditure at 200 kWh /
15 m3 and tax the whole expenditure at 201 kWh / 16 m3 (a cliff). That
is the reading the rulespec-et VAT module encodes, and ETMOD shares it.
It is not the only reading: rulespec-et's separately encoded Directive
1021/2024 module computes the exempt quantity as min(consumption,
limit), under which the first 200 kWh (15 m3) stay exempt for heavier
users, and the directive's "consumption up to 200 kWh" wording
supports either. Which reading is right is an open methodology
question; this suite compares the VAT module only and says nothing
about it. Each case zero-fills the other arm's inputs because the
runner queries both VAT concepts on every case.

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
            # Placeholder; the engine's post-uprating yem overwrites it via
            # the bridge. euromod_annualize_outputs is off for this suite
            # (monthly module), so the bridged yem is already monthly.
            "axiom_inputs": {income_input: monthly_target},
            "euromod_inputs": [_et_formal_earner(101, monthly_target)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"yem": [income_input]},
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
# et-business-mat (tin02_s: the MAT-dormant agreement zone plus one case
# per ETMOD minimum-tax finding)
# ---------------------------------------------------------------------------

_BUSINESS_GRID = (
    # (label, annual receipts target, annual business income target) -
    # scheduled tax comfortably above the 2.5%-of-receipts floor, so
    # the minimum tax is dormant in both engines.
    ("2500000-high-margin", 2_500_000.0, 1_000_000.0),
    ("3000000-mid-margin", 3_000_000.0, 1_200_000.0),
    ("4000000-comfortable", 4_000_000.0, 2_000_000.0),
)

# One case per ETMOD finding in etmod_issues.json; each is an expected,
# dispositioned mismatch (dispositions/et-business-mat.yaml).
_BUSINESS_FINDING_GRID = (
    # Finding 1: Category A, minimum tax active. Statutory payable is the
    # 2.5% floor (75,000); ETMOD adds the full 2.5% to the scheduled 6,000.
    ("mat-active-3000000-60000-finding1", 3_000_000.0, 60_000.0,
     "category-a-minimum-tax-active"),
    # Finding 2: Category B (Article 49 regime), excluded from the minimum
    # tax by Article 23(4). Income sits in the 0-24,000 nil band, so the
    # encoded schedule returns 0 here even though the module has no
    # Category B gate (see the module docstring).
    ("article-49-regime-50000-20000-finding2", 50_000.0, 20_000.0,
     "category-b-gross-revenue-regime"),
)


def et_business_mat_cases() -> list[Case]:
    """Business-income cases for tin02_s (agreement zone + finding cases)."""
    return [
        _business_case(f"et-business-{label}", receipts, income)
        for label, receipts, income in _BUSINESS_GRID
    ] + [
        _business_case(f"et-business-{label}", receipts, income, scenario=scenario)
        for label, receipts, income, scenario in _BUSINESS_FINDING_GRID
    ]


def _business_case(
    case_id: str,
    receipts_target: float,
    income_target: float,
    *,
    scenario: str = "category-a-business-income-tax",
) -> Case:
    income_input = f"{TAX_MODULE}#input.taxable_business_income"
    receipts_input = f"{TAX_MODULE}#input.annual_gross_receipts"
    return Case(
        case_id=case_id,
        period=ET_PERIOD,
        metadata={
            **ET_METADATA,
            "scenario": scenario,
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
    """Formal-employee pension cases for the tscee_s/tscer_s oracles.

    The Axiom runner queries every concept the suite declares (both
    proclamations' outputs) on every case. Both modules name their input
    ``monthly_salary`` and the Axiom side resolves inputs per entity by
    that bare name, so the one bridged value satisfies both modules (only
    the applicable sector's outputs are compared). Supplying the other
    module's ``monthly_salary`` as zero fails with "ambiguous input
    `monthly_salary` ... conflicting values" (observed 2026-10-04).
    """
    private_salary = f"{PRIVATE_PENSION_MODULE}#input.monthly_salary"
    public_salary = f"{PUBLIC_PENSION_MODULE}#input.monthly_salary"
    cases = []
    for label, monthly, loc in (
        ("private-10000", 10_000.0, 1),
        ("private-3000", 3_000.0, 1),
    ):
        income_input = private_salary
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
                    # euromod_annualize_outputs is off for this suite
                    # (monthly modules), so the bridged yem is monthly.
                    EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"yem": [income_input]},
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
    income_input = public_salary
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
                EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"yem": [income_input]},
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

#: Every VAT-arm input, zero-filled on each case: the Axiom runner queries
#: every concept the suite declares (electricity_vat AND water_vat) on
#: every case in one batched request, so each case must supply both arms'
#: inputs. The unused arm is zero in both engines (no x/q column set on the
#: ETMOD row; zero quantity and expenditure on the Axiom side), and the
#: per-case declared output keeps only the exercised arm in the comparison.
_VAT_ZERO_INPUTS = {
    f"{VAT_MODULE}#input.electricity_expenditure": 0.0,
    f"{VAT_MODULE}#input.monthly_electricity_kwh": 0.0,
    f"{VAT_MODULE}#input.water_expenditure": 0.0,
    f"{VAT_MODULE}#input.monthly_water_cubic_meters": 0.0,
}


#: (label, ETMOD x-var, q-var, monthly quantity, Axiom expenditure input,
#: Axiom quantity input). Each arm has a case well above the monthly
#: threshold, one at it (exempt) and one a unit above it (taxed), so the
#: suite pins the threshold reading both engines use (see the module
#: docstring: a cliff on the whole expenditure).
_VAT_GRID = (
    ("electricity-above-threshold", "x0451", "q0451", 300.0,
     "electricity_expenditure", "monthly_electricity_kwh"),
    ("electricity-at-threshold-200kwh", "x0451", "q0451", 200.0,
     "electricity_expenditure", "monthly_electricity_kwh"),
    ("electricity-just-above-201kwh", "x0451", "q0451", 201.0,
     "electricity_expenditure", "monthly_electricity_kwh"),
    ("water-above-threshold", "x044", "q044", 20.0,
     "water_expenditure", "monthly_water_cubic_meters"),
    ("water-at-threshold-15m3", "x044", "q044", 15.0,
     "water_expenditure", "monthly_water_cubic_meters"),
    ("water-just-above-16m3", "x044", "q044", 16.0,
     "water_expenditure", "monthly_water_cubic_meters"),
)


def et_vat_cases() -> list[Case]:
    """VAT cases: electricity and water threshold arms for tva_s."""
    cases = []
    for label, xvar, qvar, q_monthly, exp_input, q_input in _VAT_GRID:
        expenditure = f"{VAT_MODULE}#input.{exp_input}"
        quantity = f"{VAT_MODULE}#input.{q_input}"
        row = _et_base_row(1, 101)
        row.update({xvar: 100.0, qvar: q_monthly})
        axiom_inputs = dict(_VAT_ZERO_INPUTS)
        axiom_inputs[expenditure] = 1_200.0
        axiom_inputs[quantity] = q_monthly
        cases.append(
            Case(
                case_id=f"et-vat-{label}",
                period=ET_PERIOD,
                metadata={
                    **ET_METADATA,
                    "scenario": "household-vat-utility-thresholds",
                    "axiom_inputs": axiom_inputs,
                    "euromod_inputs": [row],
                    # The engine's post-uprating expenditure overwrites the
                    # placeholder (ETMOD echoes the utility x-vars in its
                    # output frame, so this bridge applies - unlike RWAMOD's
                    # detailed COICOP food items); the runner annualizes it
                    # onto the module's annual expenditure input. The
                    # quantity passes unuprated.
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
