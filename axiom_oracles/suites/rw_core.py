"""Rwanda core tax and contribution oracle suites (RWAMOD).

Six suites covering the eleven rulespec-rw instruments (rulespec-rw#1)
against RWAMOD, the SOUTHMOD tax-benefit model for Rwanda (UNU-WIDER),
run on the EUROMOD engine (SOUTHMOD A4.0, country RW, system RW_2025 =
CY2025). RWAMOD ships no Rwandan input microdata (the registered
dataset names carry no data files), so per-case probes run an external
synthetic DataFrame under the registered ``rw_2024_a1`` dataset name
against a 450-variable input schema assembled by seeding from a sister
SOUTHMOD dataset header and adding engine-reported unknowns until a
clean run. Monetary-input uprating factor 1.0715284612 (probed;
consumption x-vars carry per-group indices - alcohol/tobacco 1.1104,
food details 1.1382 - so every consumption case bridges the engine's
own post-uprating value, the Ghana/Uganda/Zambia/Ethiopia convention).

``rw-paye-rate-schedule`` — the Law 027/2022 Article 56 Table 2
monthly schedule (0% to 60,000 FRW; 10% to 100,000; 20% to 200,000;
30% above) against ``tin_s`` on the employment-only grid (the model's
``ttb`` sums agriculture-above-exemption, investment and employment
bases; these cases feed employment only, so ttb equals the employment
base). The engine's own post-uprating gross ``yem`` is bridged onto
the module's monthly input, so the live cases verify the schedule
arithmetic exactly. Banding note: EUROMOD's band lower limits start at
60,001/100,001/200,001 exactly, pricing totals about 0.3 FRW below the
statutory bracket reading at high incomes - inside the 1-FRW
tolerance.

``rw-lump-sum`` — the Law 027/2022 micro-enterprise flat amounts
(60,000/120,000/210,000/300,000 FRW by annual-turnover band) and the
small-enterprise 3 percent arm (12m-20m) against ``ttn_s``. RWAMOD
reads ``ytn01`` as monthly turnover and pays the flat amounts as
annual twelfths (probed 5,000/10,000/17,500/25,000 FRW per month
inside the four bands, 3 percent inside the small band, and zero above
the 20m bound where the person leaves the lump-sum regime) - the
bridge annualizes the engine's uprated turnover onto the module's
annual input.

``rw-rental`` — the Law 048/2023 Article 43 base (gross rental income
less 50 percent deemed expenses) and Article 42 bands (0/20/30 percent
at 180,000/1,000,000 FRW annual) against ``tpr_s`` - probed exact
(2,357.63 and 20,812.50 FRW per month at uprated monthly gross
53,576.42 and 214,305.69).

``rw-contributions`` — the RSSB contribution stack by employment
sector against the ``tsc*`` arms: pension 6% + 6% (Presidential Order
086/01 twelve percent from 1 January 2025, halved by the Law 05/2015
equal-sharing rule); maternity 0.3% + 0.3% (Law 003/2016 Article 7);
RAMA 7.5% + 7.5% for formal public-sector employees (Law 24/2001
Article 44; RWAMOD keys the scheme on lfo=1 & loc!=0 & lindi 9-11);
MMI insured 5% + government 17.5% (Law 23/2005 Article 30; loc=0
keys the military/police class); and the CBHI employee levy of 0.5%
of net salary (PM Order 105/03 of 30/09/2020 Article 5). The levy's
statutory base ("net salary") is undefined beyond the order; RWAMOD
operationalizes it as gross employment income less employment PAYE,
employee pension, employee maternity and the employee medical-scheme
contribution - the suite bridges the engine's own levy back to its
base so the live cases verify the 0.5 percent arithmetic exactly,
and the base operationalization is recorded here rather than
adjudicated. Occupational-hazards disposition (rulespec-rw#1): RWAMOD
applies a 2 percent employer contribution (probed 2,143.06 at uprated
107,152.85); Law 06/2003 Article 10 makes the branch employer-only
and Article 9 delegates the rates to a Presidential Decree that is
not publicly digitized (the RSSB scheme page documents benefits, not
the rate), so the 2 percent has no encodable primary carrier and
stays a documented gap, not a live case.

``rw-vat`` — the Law 049/2023 Article 4 standard rate (18 percent)
against ``tva_s`` on a VAT-base food-detail expenditure item
(x0111211, probed 2,048.77 on 10,000 FRW per month raw = 18 percent
of the engine's post-uprating value exactly). RWAMOD also charges VAT
on the excise-inclusive value of excisable purchases inside the
excise policy; those arms are exercised by the excise suite bridges.

``rw-excise`` — the Law 011/2025 Annex rows against the ``tex*``
arms: premium fuel FRW 183 per litre and gas oil FRW 150 per litre on
unuprated litre quantities (probed exact: 3,660 on 20 litres, 1,500
on 10), and the cigarette compound duty (36 percent of retail value
plus FRW 230 per pack of 20 rods; probed 10,295.12 on uprated
22,208.66 retail plus 10 packs). Dispositions (rulespec-rw#1,
probed live, adjudicated against the 2025 print): (1) RWAMOD taxes
bottled-water expenditure at 10 percent (tex11 arm) where the Law
011/2025 Annex carries NO water row - the row existed in the repealed
Law 050/2023 (in force through 28 May 2025), so the model applies a
repealed row alongside the 2025 rates for the same year; (2) the
model taxes its whole juice basket at the 10 percent local-content
rate where the Annex prices only at-least-30-percent-local juices at
10 percent and other juices at 39 percent; (3) the model's beer
basket spans four expenditure vars at the 40 percent local rate where
the Annex prices other-fermented beverages at 65 percent and
other-local-content alcoholic beverages at 30 percent - basket-level
simplifications recorded with the ledger, no agreement zone.

``rw-cbhi-tiers`` — the Ministerial Order 002/26/10/TC member premium
schedule by IMIBEREHO Dynamic Social Registry level against
``tsceehl02_s``. TIMING FINDING (rulespec-rw#1): RWAMOD RW_2025
applies the member amounts (3,000/5,000/8,000/20,000 FRW per year,
paid as twelfths - probed 250/416.67/666.67/1,666.67 per month by
monthly-income tier) for CY2025, where the first gazetted carrier of
the schedule is the Order of 16/02/2026 (in force on publication,
23/02/2026; the prior PM Order 105/03 of 30/09/2020 carries the
funding schedule and the 0.5 percent employee levy but no
income-tier member premiums). The amounts agree exactly; the
validation-year grounding does not - the module correctly starts
2026-02-23 and the live cases run the Axiom side at 2027 against the
oracle's RW_2025 values, verifying the schedule arithmetic while the
timing gap stays a recorded finding. RWAMOD keys tiers on
``ils_earns`` monthly-income bounds (30,000/60,000/120,000 FRW) per
the RSSB administration of the registry levels.

License discipline as elsewhere: the SOUTHMOD bundle is referenced by
path only; expected values are values RWAMOD itself produced; no
bundle content is committed.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .gh_income_tax import EUROMOD_TO_AXIOM_INPUT_BRIDGE

PAYE_MODULE = "rw:statutes/law-2022-027/employment-income-tax"
LUMP_SUM_MODULE = "rw:statutes/law-2022-027/lump-sum-regime"
RENTAL_MODULE = "rw:statutes/law-2023-048/rental-income-tax"
VAT_MODULE = "rw:statutes/law-2023-049/value-added-tax"
EXCISE_MODULE = "rw:statutes/law-2025-011/excise-duty"
PENSION_MODULE = "rw:regulations/po-2024-086-01/pension-contribution-rate"
MATERNITY_MODULE = "rw:statutes/law-2016-003/maternity-leave-contributions"
RAMA_MODULE = "rw:statutes/law-2001-24/rama-contributions"
MMI_MODULE = "rw:statutes/law-2005-23/mmi-contributions"
CBHI_LEVY_MODULE = "rw:regulations/pmo-2020-105-03/cbhi-employee-contribution"
CBHI_PREMIUMS_MODULE = "rw:regulations/mo-2026-002-26-10-tc/cbhi-member-premiums"

RW_SCOPE = {"type": "country", "geoid": "RW"}
RW_METADATA = {
    "locale": "RW",
    "scope": RW_SCOPE,
    "axiom_entity": "Person",
    "axiom_entity_id": "head",
}
# Axiom evaluation period: inside every module's effective window
# (Table 2 from 2024; excise from 29 May 2025; pension 12% through
# 2026). The oracle side always runs RW_2025 (= CY2025); every
# compared schedule is value-identical across 2025/2026 except the
# phased telephone rate, which no case exercises.
RW_PERIOD = "2026"
# CBHI member premiums are first gazetted effective 23/02/2026, so the
# tier cases evaluate the Axiom side at 2027 (fully inside the window)
# against the oracle's RW_2025 values - the timing finding is recorded
# in the rw-cbhi-tiers description.
RW_PERIOD_TIERS = "2027"
# Monetary-input uprating factor for the synthetic rw_2024_a1 rows,
# probed live (yem 1,000,000/month -> 1,071,528.4612). Aim-only:
# bridges feed the engine's own post-uprating values onto the Axiom
# inputs, so parity does not depend on this constant's precision.
RW_UPRATE_2024_TO_2025 = 1.0715284612


def _rw_base_row(idhh: int, idperson: int) -> dict[str, float | int]:
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
        "loc": 3,
        "lindi": 5,
        "ddi": 0,
        "dec": 0,
        "yem": 0.0,
    }


def _rw_formal_earner(
    idperson: int, monthly_target: float, *, loc: int = 3, lindi: int = 5
) -> dict[str, float | int]:
    row = _rw_base_row(1, idperson)
    row.update(
        {
            "les": 3,
            "lfo": 1,
            "loc": loc,
            "lindi": lindi,
            "yem": monthly_target / RW_UPRATE_2024_TO_2025,
        }
    )
    return row


def _rw_informal(idperson: int) -> dict[str, float | int]:
    row = _rw_base_row(1, idperson)
    row.update({"les": 2, "lfo": 0})
    return row


def _head_entity(**extra_facts) -> tuple[Entity, ...]:
    facts = {
        Concepts.PERSON_AGE: 35,
        Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
    }
    facts.update(extra_facts)
    return (Entity(entity_id="head", kind="person", facts=facts),)


# ---------------------------------------------------------------------------
# rw-paye-rate-schedule (tin_s, employment-only grid, exact)
# ---------------------------------------------------------------------------

# Monthly gross targets: every Table 2 band bound and an interior point
# per band (the engine's own uprated yem lands here and is bridged back
# to the module's monthly input).
_PAYE_MONTHLY_GRID = (
    ("30000-nil-interior", 30_000.0),
    ("60000-exempt-bound", 60_000.0),
    ("80000-band2-interior", 80_000.0),
    ("100000-band2-bound", 100_000.0),
    ("150000-band3-interior", 150_000.0),
    ("200000-band3-bound", 200_000.0),
    ("400000-band4-interior", 400_000.0),
    ("1000000-high-income", 1_000_000.0),
)


def rw_paye_rate_schedule_cases() -> list[Case]:
    """Single formal-sector employee PAYE cases for the tin_s oracle."""
    return [
        _paye_case(f"rw-paye-{label}", monthly)
        for label, monthly in _PAYE_MONTHLY_GRID
    ]


def _paye_case(case_id: str, monthly_target: float) -> Case:
    income_input = f"{PAYE_MODULE}#input.monthly_taxable_employment_income"
    return Case(
        case_id=case_id,
        period=RW_PERIOD,
        metadata={
            **RW_METADATA,
            "scenario": "single-formal-employee-paye-schedule",
            "monthly_employment_income": monthly_target,
            # Placeholder; the engine's post-uprating yem (annualized by
            # the runner) overwrites it via the bridge, divided back to
            # the module's monthly basis.
            "axiom_inputs": {income_input: monthly_target},
            "euromod_inputs": [_rw_formal_earner(101, monthly_target)],
            # euromod_annualize_outputs is off for this suite (monthly
            # module), so the bridged yem is already monthly.
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"yem": [income_input]},
        },
        entities=_head_entity(
            **{Concepts.YEARLY_EARNED_INCOME: monthly_target * 12.0}
        ),
        outputs=(Concepts.RW_EMPLOYMENT_INCOME_TAX,),
    )


# ---------------------------------------------------------------------------
# rw-lump-sum (ttn_s, flat bands + 3% arm, exact)
# ---------------------------------------------------------------------------

# Annual turnover targets: an interior point in each flat band, the 3%
# small-enterprise arm, and one above-regime point (both engines nil).
_LUMP_SUM_GRID = (
    ("3m-band1", 3_000_000.0),
    ("5m-band2", 5_000_000.0),
    ("8m-band3", 8_000_000.0),
    ("11m-band4", 11_000_000.0),
    ("15m-small-3pct", 15_000_000.0),
    ("19m-small-3pct", 19_000_000.0),
    ("25m-above-regime", 25_000_000.0),
)


def rw_lump_sum_cases() -> list[Case]:
    """Micro/small-enterprise lump-sum cases for the ttn_s oracle."""
    return [
        _lump_sum_case(f"rw-lump-sum-{label}", annual)
        for label, annual in _LUMP_SUM_GRID
    ]


def _lump_sum_case(case_id: str, annual_turnover: float) -> Case:
    turnover_input = f"{LUMP_SUM_MODULE}#input.annual_turnover"
    row = _rw_informal(101)
    # ytn01 is monthly turnover in RWAMOD; aim the engine's uprated
    # annualized turnover at the target band.
    row["ytn01"] = (annual_turnover / RW_UPRATE_2024_TO_2025) / 12.0
    return Case(
        case_id=case_id,
        period=RW_PERIOD,
        metadata={
            **RW_METADATA,
            "scenario": "small-business-lump-sum",
            "yearly_turnover": annual_turnover,
            "axiom_inputs": {
                turnover_input: annual_turnover,
                f"{LUMP_SUM_MODULE}#input.small_enterprise_operator_opted_for_real_regime": False,
            },
            "euromod_inputs": [row],
            # The runner annualizes the engine's uprated monthly ytn01,
            # which lands directly on the module's annual input.
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"ytn01": [turnover_input]},
        },
        entities=_head_entity(),
        outputs=(Concepts.RW_LUMP_SUM_TAX,),
    )


# ---------------------------------------------------------------------------
# rw-rental (tpr_s, 50% base + 0/20/30 bands, exact)
# ---------------------------------------------------------------------------

_RENTAL_GRID = (
    ("120000-nil", 120_000.0),
    ("360000-zero-bound", 360_000.0),
    ("800000-band2", 800_000.0),
    ("2400000-band3", 2_400_000.0),
)


def rw_rental_cases() -> list[Case]:
    """Rental income tax cases for the tpr_s oracle."""
    return [
        _rental_case(f"rw-rental-{label}", annual)
        for label, annual in _RENTAL_GRID
    ]


def _rental_case(case_id: str, annual_gross_rental: float) -> Case:
    rental_input = f"{RENTAL_MODULE}#input.gross_rental_income"
    row = _rw_base_row(1, 101)
    row.update({"les": 1, "ypr": (annual_gross_rental / RW_UPRATE_2024_TO_2025) / 12.0})
    return Case(
        case_id=case_id,
        period=RW_PERIOD,
        metadata={
            **RW_METADATA,
            "scenario": "individual-rental-income-tax",
            "yearly_gross_rental": annual_gross_rental,
            "axiom_inputs": {rental_input: annual_gross_rental},
            "euromod_inputs": [row],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"ypr": [rental_input]},
        },
        entities=_head_entity(),
        outputs=(Concepts.RW_RENTAL_INCOME_TAX,),
    )


# ---------------------------------------------------------------------------
# rw-contributions (tsc* arms by sector, exact)
# ---------------------------------------------------------------------------

# (label, monthly gross target, loc, lindi, extra output concepts).
# Every sector case carries the pension, maternity and CBHI-levy
# outputs; the public-servant case adds RAMA and the military case
# adds MMI (RWAMOD keys the scheme on loc/lindi).
_CONTRIBUTION_SECTORS = (
    ("private-100000", 100_000.0, 3, 5, ()),
    ("private-400000", 400_000.0, 3, 5, ()),
    (
        "public-servant-100000",
        100_000.0,
        1,
        10,
        ("RW_EMPLOYEE_RAMA_CONTRIBUTION", "RW_EMPLOYER_RAMA_CONTRIBUTION"),
    ),
    (
        "military-100000",
        100_000.0,
        0,
        5,
        ("RW_INSURED_MMI_CONTRIBUTION", "RW_GOVERNMENT_MMI_CONTRIBUTION"),
    ),
)


def rw_contributions_cases() -> list[Case]:
    """Sectoral contribution-stack cases for the tsc* oracles."""
    return [
        _contributions_case(f"rw-contributions-{label}", monthly, loc, lindi, extra)
        for label, monthly, loc, lindi, extra in _CONTRIBUTION_SECTORS
    ]


def _contributions_case(
    case_id: str,
    monthly_target: float,
    loc: int,
    lindi: int,
    extra_concepts: tuple[str, ...],
) -> Case:
    pension_input = f"{PENSION_MODULE}#input.covered_remuneration"
    maternity_input = f"{MATERNITY_MODULE}#input.contributory_salary"
    rama_input = f"{RAMA_MODULE}#input.employee_basic_salary"
    mmi_input = f"{MMI_MODULE}#input.basic_salary"
    levy_input = f"{CBHI_LEVY_MODULE}#input.employee_net_salary"
    is_public = loc != 0 and 9 <= lindi <= 11
    is_military = loc == 0
    outputs = [
        Concepts.RW_EMPLOYEE_PENSION_CONTRIBUTION,
        Concepts.RW_EMPLOYER_PENSION_CONTRIBUTION,
        Concepts.RW_EMPLOYEE_MATERNITY_CONTRIBUTION,
        Concepts.RW_EMPLOYER_MATERNITY_CONTRIBUTION,
        Concepts.RW_CBHI_EMPLOYEE_CONTRIBUTION,
    ]
    outputs.extend(getattr(Concepts, name) for name in extra_concepts)
    # euromod_annualize_outputs is off for this suite (monthly
    # modules), so bridged values arrive on their monthly basis. The
    # scheme-specific salary inputs are bridged in their applicable
    # sector only (zero elsewhere), matching the oracle's eligibility
    # keying.
    yem_targets = [pension_input, maternity_input]
    if is_public:
        yem_targets.append(rama_input)
    if is_military:
        yem_targets.append(mmi_input)
    bridge = {
        "yem": {
            "inputs": yem_targets,
        },
        # The levy base ("net salary") is RWAMOD's own operationalization;
        # bridging the engine's monthly levy back to its base (levy /
        # 0.005) verifies the module's 0.5% arithmetic exactly.
        "tsceehl03_s": {"inputs": [levy_input], "divide_by": 0.005},
    }
    return Case(
        case_id=case_id,
        period=RW_PERIOD,
        metadata={
            **RW_METADATA,
            "scenario": "formal-employee-contribution-stack",
            "monthly_employment_income": monthly_target,
            # RWAMOD keys RAMA on the public-service industry codes and
            # MMI on loc=0; the Axiom modules price any salary they are
            # fed, so scheme inputs feed the applicable sector only and
            # zero elsewhere (both engines nil by construction).
            "axiom_inputs": {
                pension_input: monthly_target,
                maternity_input: monthly_target,
                rama_input: monthly_target if is_public else 0,
                mmi_input: monthly_target if is_military else 0,
                levy_input: monthly_target,
            },
            "euromod_inputs": [
                _rw_formal_earner(101, monthly_target, loc=loc, lindi=lindi)
            ],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: bridge,
        },
        entities=_head_entity(
            **{Concepts.YEARLY_EARNED_INCOME: monthly_target * 12.0}
        ),
        outputs=tuple(outputs),
    )


# ---------------------------------------------------------------------------
# rw-vat (tva_s on a VAT-base food-detail item, exact)
# ---------------------------------------------------------------------------

_VAT_GRID = (
    ("10000-monthly", 120_000.0),
    ("50000-monthly", 600_000.0),
    ("200000-monthly", 2_400_000.0),
)


def rw_vat_cases() -> list[Case]:
    """VAT-base expenditure cases for the tva_s oracle."""
    return [_vat_case(f"rw-vat-{label}", annual) for label, annual in _VAT_GRID]


def _vat_case(case_id: str, annual_raw: float) -> Case:
    taxable_value = f"{VAT_MODULE}#input.taxable_value"
    row = _rw_informal(101)
    # x0111211 is a VAT-base food-detail item (il_exp_vat01 member,
    # probed: tva = 18% of the engine's post-uprating value exactly).
    # Detailed COICOP inputs are not echoed in the engine's output
    # frame, so the engine's own VAT charge is bridged back to its
    # base (tva_s / 0.18) - the case verifies the module's 18%
    # arithmetic on the engine's post-uprating base exactly.
    row["x0111211"] = annual_raw / 12.0
    return Case(
        case_id=case_id,
        period=RW_PERIOD,
        metadata={
            **RW_METADATA,
            "scenario": "household-vat-standard-rate",
            "yearly_expenditure_raw": annual_raw,
            "axiom_inputs": {taxable_value: annual_raw},
            "euromod_inputs": [row],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "tva_s": {"inputs": [taxable_value], "divide_by": 0.18}
            },
        },
        entities=_head_entity(),
        outputs=(Concepts.RW_VAT_AMOUNT,),
    )


# ---------------------------------------------------------------------------
# rw-excise (tex arms: fuels per litre + cigarette compound, exact)
# ---------------------------------------------------------------------------


_EXCISE_ZERO_INPUTS = {
    f"{EXCISE_MODULE}#input.premium_fuel_litres": 0,
    f"{EXCISE_MODULE}#input.gas_oil_litres": 0,
    f"{EXCISE_MODULE}#input.cigarette_retail_value": 0,
    f"{EXCISE_MODULE}#input.cigarette_packs": 0,
    f"{EXCISE_MODULE}#input.cigar_value": 0,
}


def rw_excise_cases() -> list[Case]:
    """Fuel per-litre and cigarette compound-duty cases for tex arms."""
    cases = [
        _fuel_case("rw-excise-premium-fuel-20l", "q0722201", 20.0, "premium"),
        _fuel_case("rw-excise-premium-fuel-100l", "q0722201", 100.0, "premium"),
        _fuel_case("rw-excise-gas-oil-10l", "q0722101", 10.0, "gas-oil"),
        _fuel_case("rw-excise-gas-oil-80l", "q0722101", 80.0, "gas-oil"),
        _cigarette_case("rw-excise-cigarettes-10-packs", 20_000.0, 10.0),
        _cigarette_case("rw-excise-cigarettes-40-packs", 90_000.0, 40.0),
    ]
    return cases


def _fuel_case(case_id: str, quantity_var: str, monthly_litres: float, kind: str) -> Case:
    if kind == "premium":
        litres_input = f"{EXCISE_MODULE}#input.premium_fuel_litres"
        concept = Concepts.RW_PREMIUM_FUEL_EXCISE_DUTY
    else:
        litres_input = f"{EXCISE_MODULE}#input.gas_oil_litres"
        concept = Concepts.RW_GAS_OIL_EXCISE_DUTY
    row = _rw_informal(101)
    row[quantity_var] = monthly_litres
    axiom_inputs = dict(_EXCISE_ZERO_INPUTS)
    axiom_inputs[litres_input] = monthly_litres * 12.0
    return Case(
        case_id=case_id,
        period=RW_PERIOD,
        metadata={
            **RW_METADATA,
            "scenario": "household-fuel-specific-excise",
            "monthly_litres": monthly_litres,
            # Litre quantities are unuprated in RWAMOD (probed: 20 l ->
            # 3,660 = 20 x 183 exactly), so the annual litres feed the
            # Axiom side directly - no bridge needed; the other excise
            # inputs are zero-filled because the suite queries every
            # excise concept on every case.
            "axiom_inputs": axiom_inputs,
            "euromod_inputs": [row],
        },
        entities=_head_entity(),
        outputs=(concept,),
    )


def _cigarette_case(case_id: str, monthly_retail_raw: float, monthly_packs: float) -> Case:
    retail_input = f"{EXCISE_MODULE}#input.cigarette_retail_value"
    packs_input = f"{EXCISE_MODULE}#input.cigarette_packs"
    row = _rw_informal(101)
    row.update({"x02301": monthly_retail_raw, "q02301": monthly_packs})
    annual_packs = monthly_packs * 12.0
    axiom_inputs = dict(_EXCISE_ZERO_INPUTS)
    axiom_inputs[retail_input] = monthly_retail_raw * 12.0
    axiom_inputs[packs_input] = annual_packs
    return Case(
        case_id=case_id,
        period=RW_PERIOD,
        metadata={
            **RW_METADATA,
            "scenario": "household-cigarette-compound-excise",
            "monthly_retail_raw": monthly_retail_raw,
            "monthly_packs": monthly_packs,
            # Retail expenditure is uprated (alcohol/tobacco group index,
            # probed 1.1104) and detailed COICOP inputs are not echoed in
            # the engine's output frame, so the engine's own compound duty
            # is inverted back to its retail base ((tex01 - 230 x packs) /
            # 0.36; the transform applies divide-then-add, so the pack
            # term is pre-divided); pack counts are unuprated and feed
            # directly. The case verifies the module's 36% + 230/pack
            # arithmetic on the engine's post-uprating base exactly.
            "axiom_inputs": axiom_inputs,
            "euromod_inputs": [row],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "tex01_s": {
                    "inputs": [retail_input],
                    "divide_by": 0.36,
                    "add": -(230.0 * annual_packs) / 0.36,
                }
            },
        },
        entities=_head_entity(),
        outputs=(Concepts.RW_CIGARETTE_EXCISE_DUTY,),
    )


# ---------------------------------------------------------------------------
# rw-cbhi-tiers (tsceehl02_s, schedule arithmetic; timing finding)
# ---------------------------------------------------------------------------

# (label, monthly informal earnings target, IMIBEREHO level the RSSB
# income bands assign). RWAMOD keys the tier on ils_earns monthly
# bounds 30,000/60,000/120,000 FRW.
_TIER_GRID = (
    ("20000-level2", 20_000.0, 2),
    ("45000-level3", 45_000.0, 3),
    ("90000-level4", 90_000.0, 4),
    ("200000-level5", 200_000.0, 5),
)


def rw_cbhi_tiers_cases() -> list[Case]:
    """Informal-sector CBHI member premium cases for tsceehl02_s."""
    return [
        _tier_case(f"rw-cbhi-tier-{label}", monthly, level)
        for label, monthly, level in _TIER_GRID
    ]


def _tier_case(case_id: str, monthly_earnings: float, level: int) -> Case:
    level_input = f"{CBHI_PREMIUMS_MODULE}#input.imibereho_dynamic_social_registry_level"
    row = _rw_informal(101)
    row["yse"] = monthly_earnings / RW_UPRATE_2024_TO_2025
    return Case(
        case_id=case_id,
        period=RW_PERIOD_TIERS,
        metadata={
            **RW_METADATA,
            "scenario": "informal-cbhi-member-premium",
            "monthly_earnings": monthly_earnings,
            "imibereho_level": level,
            "axiom_inputs": {level_input: level},
            "euromod_inputs": [row],
        },
        entities=_head_entity(),
        outputs=(Concepts.RW_CBHI_MEMBER_PAID_PREMIUM,),
    )
