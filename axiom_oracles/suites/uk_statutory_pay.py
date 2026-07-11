"""Statutory-pay and maternity suite for the UKMOD ``bmact_s`` / ``bmanc_s`` /
``bpact_s`` oracles.

Where ``uk_worker`` runs single-employee tax/NIC cases and ``uk_child_benefit``
a non-means-tested family transfer, this suite covers the UK statutory-pay and
maternity stack: Statutory Maternity Pay (``bmact_uk``), Maternity Allowance
(``bmanc_uk``), and Statutory Paternity Pay (``bpact_uk``). All three are
switch-on in UKMOD UK_2026 and compute from ordinary demographic/earnings inputs
on synthetic hypothetical households, so — contrary to the Country-Report "not
simulated in the baseline" note (the FRS baseline does not populate maternity
spells) — they are directly comparable on HHoT cases. Verified live against
UKMOD_PUBLIC_B2026.03 (system UK_2026, dataset training_data).

Verified UKMOD conventions (executed against UKMOD_PUBLIC_B2026.03, UK_2026):

- ``bmact_s`` (SMP) is the monthly Statutory Maternity Pay, annualised by the
  adapter. For a synthetic maternity case UKMOD pays the earnings-related rate
  (90% of normal weekly earnings, ``$SMPrr`` 0.9) across the full 39-week
  maternity pay period, so the annual amount is ``0.9 x weekly x 39`` where the
  weekly figure is UKMOD's ``yem/30.5*7`` monthly-to-weekly proxy. Verified: a
  lone mother at annual gross £25,000 (weekly £478.14) returns £16,782.79, at
  £8,000 (weekly £153.01) £5,370.49. Below the £130 lower earnings limit
  (``$SMPlel``) SMP is zero. UKMOD applies the earnings-related rate over the
  whole period rather than switching to the flat prescribed rate for weeks 7+
  (the flat rate binds only where 90% of weekly earnings falls below it, which is
  below the LEL floor).

- ``bmanc_s`` (Maternity Allowance) is payable only where SMP is not
  (``bmact_s = 0``), so the case is a self-employed mother (``yse`` > 0, ``yem``
  = 0, hence no SMP): UKMOD pays ``0.9 x average weekly earnings x 39`` from the
  self-employment earnings above the ``$SMAThresh1`` £30 threshold. Verified: a
  self-employed mother at annual self-employment £15,000 (weekly £286.89)
  returns £10,069.67, at £9,000 (weekly £172.13) £6,041.80.

- ``bpact_s`` (Statutory Paternity Pay) pays the earnings-related rate across the
  2-week paternity pay period: ``0.9 x weekly x 2``. Verified: a lone father at
  annual gross £25,000 returns £860.66, at £8,000 £275.41.

- These three benefits do NOT consume UKMOD's stochastic take-up draw
  ``i_rand_tu`` (that gate affects the means-tested passported grants
  ``bmascmt_uk`` / ``bmascmt01_uk``, not the statutory-pay policies), so the
  take-up correction cannot zero a hypothetical recipient's award. The suite
  still requests the take-up policy switch overrides on every case for parity
  with the household Universal Credit and Child Benefit suites; toggling them
  leaves ``bmact_s`` / ``bmanc_s`` / ``bpact_s`` unchanged.

Each case is a single-earner household (a lone mother for SMP/MA, a lone father
for SPP) so the household-summed ``yem`` (or ``yse``) the input bridge reads is
the recipient's own earnings. The bridge converts UKMOD's annualised monthly
gross to the weekly earnings the composed pilot consumes
(``supplied_normal_weekly_earnings`` = annual gross / (12 x 30.5 / 7)), so the
Axiom pipeline is fed the same earnings UKMOD used and reconstructs the oracle.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity


UK_SCOPE = {"type": "country", "geoid": "UK"}
UK_STATPAY_METADATA = {
    "locale": "UK",
    "scope": UK_SCOPE,
    "axiom_entity": "Person",
    "axiom_entity_id": "head",
}

SMP_MODULE = (
    "uk:statutes/statutory_maternity_pay/pilot_statutory_maternity_pay_oracle_pipeline"
)
MA_MODULE = "uk:statutes/maternity_allowance/pilot_maternity_allowance_oracle_pipeline"
SPP_MODULE = (
    "uk:statutes/statutory_paternity_pay/pilot_statutory_paternity_pay_oracle_pipeline"
)
EUROMOD_TO_AXIOM_INPUT_BRIDGE = "euromod_to_axiom_input_bridge"

# The composed pilots are effective from the 2026-27 tax year. 2025-26 and
# 2026-27 share the frozen rate structure, so UKMOD UK_2025 and UK_2026 return
# the same amounts for these cases; this suite pins UK_2026.
UK_STATPAY_PERIOD = "2026"

# UKMOD's monthly-gross-to-weekly proxy is yem/30.5*7. The bridge reads the
# adapter's annualised yem (= monthly x 12), so the annual-gross-to-weekly divisor
# is 12 x 30.5 / 7.
_ANNUAL_GROSS_TO_WEEKLY_DIVISOR = 12.0 * 30.5 / 7.0

# UKMOD UK_2026 in-force parameters (UK.xml UK_2026 system block), supplied to the
# composed pilots so the delegated cash amounts match the oracle exactly. The
# prescribed weekly rate is UKMOD's $SMPwsr forecast (£196.16); the published
# statutory 2026-27 rate is £194.32, and it does not bind (the 90% limb
# dominates). $SMPlel £130, $SMAThresh1 £30.
_SMP_PRESCRIBED_WEEKLY_RATE = 196.16
_LOWER_EARNINGS_LIMIT_WEEKLY = 130.0
_MA_EARNINGS_THRESHOLD_WEEKLY = 30.0
_EARNINGS_RELATED_RATE = 0.9
_MATERNITY_PAY_PERIOD_WEEKS = 39.0
_PATERNITY_PAY_PERIOD_WEEKS = 2.0

# UKMOD's take-up correction policies. The statutory-pay benefits do not consume
# the take-up draw (verified no-op); the overrides are requested on every case so
# the intent to compare the statutory entitlement is explicit and recorded,
# matching the Child Benefit and household Universal Credit suites.
_TAKEUP_OVERRIDES = (("BTA_uk", False), ("random_uk", False))

# Single-earner gross-income grid. £25k / £40k exercise the ordinary
# earnings-related band; £8k / £12k are low earners still above the LEL; £6k is
# below the LEL (no SMP/SPP). Maternity Allowance uses a self-employment grid.
_EARNED_INCOME_GRID: tuple[tuple[str, float], ...] = (
    ("6k", 6_000.0),
    ("8k", 8_000.0),
    ("12k", 12_000.0),
    ("25k", 25_000.0),
    ("40k", 40_000.0),
)
_SELF_EMPLOYMENT_GRID: tuple[tuple[str, float], ...] = (
    ("9k", 9_000.0),
    ("15k", 15_000.0),
    ("25k", 25_000.0),
)


def uk_statutory_maternity_pay_cases() -> list[Case]:
    """Lone-mother Statutory Maternity Pay cases for the UKMOD UK_2026 oracle."""

    return [
        _smp_case(f"uk-smp-{label}", annual_income=income)
        for label, income in _EARNED_INCOME_GRID
    ]


def uk_maternity_allowance_cases() -> list[Case]:
    """Self-employed lone-mother Maternity Allowance cases for UKMOD UK_2026."""

    return [
        _ma_case(f"uk-ma-{label}", annual_self_employment=income)
        for label, income in _SELF_EMPLOYMENT_GRID
    ]


def uk_statutory_paternity_pay_cases() -> list[Case]:
    """Lone-father Statutory Paternity Pay cases for the UKMOD UK_2026 oracle."""

    return [
        _spp_case(f"uk-spp-{label}", annual_income=income)
        for label, income in _EARNED_INCOME_GRID
    ]


def _smp_case(case_id: str, *, annual_income: float) -> Case:
    return Case(
        case_id=case_id,
        period=UK_STATPAY_PERIOD,
        metadata={
            **UK_STATPAY_METADATA,
            "scenario": "lone-mother-statutory-maternity-pay",
            "yearly_earned_income": annual_income,
            "axiom_inputs": {
                _smp_input("uk_smp_pilot_supplied_prescribed_weekly_standard_rate"): (
                    _SMP_PRESCRIBED_WEEKLY_RATE
                ),
                _smp_input("uk_smp_pilot_supplied_lower_earnings_limit_weekly"): (
                    _LOWER_EARNINGS_LIMIT_WEEKLY
                ),
                _smp_input("uk_smp_pilot_supplied_maternity_pay_period_weeks"): (
                    _MATERNITY_PAY_PERIOD_WEEKS
                ),
            },
            "euromod_inputs": _lone_parent_newborn_rows(
                mother_gender=0, annual_employment=annual_income
            ),
            "euromod_policy_switch_overrides": [
                list(pair) for pair in _TAKEUP_OVERRIDES
            ],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yem": {
                    "inputs": [
                        _smp_input("uk_smp_pilot_supplied_normal_weekly_earnings")
                    ],
                    "divide_by": _ANNUAL_GROSS_TO_WEEKLY_DIVISOR,
                },
            },
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 30,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.YEARLY_EARNED_INCOME: annual_income,
                },
            ),
        ),
        outputs=(Concepts.UK_STATUTORY_MATERNITY_PAY,),
    )


def _ma_case(case_id: str, *, annual_self_employment: float) -> Case:
    return Case(
        case_id=case_id,
        period=UK_STATPAY_PERIOD,
        metadata={
            **UK_STATPAY_METADATA,
            "scenario": "self-employed-lone-mother-maternity-allowance",
            "yearly_self_employment_income": annual_self_employment,
            "axiom_inputs": {
                _ma_input("uk_ma_pilot_supplied_earnings_threshold_weekly"): (
                    _MA_EARNINGS_THRESHOLD_WEEKLY
                ),
                _ma_input("uk_ma_pilot_supplied_maternity_allowance_period_weeks"): (
                    _MATERNITY_PAY_PERIOD_WEEKS
                ),
            },
            "euromod_inputs": _lone_parent_newborn_rows(
                mother_gender=0, annual_self_employment=annual_self_employment
            ),
            "euromod_policy_switch_overrides": [
                list(pair) for pair in _TAKEUP_OVERRIDES
            ],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yse": {
                    "inputs": [
                        _ma_input("uk_ma_pilot_supplied_average_weekly_earnings")
                    ],
                    "divide_by": _ANNUAL_GROSS_TO_WEEKLY_DIVISOR,
                },
            },
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 30,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                },
            ),
        ),
        outputs=(Concepts.UK_MATERNITY_ALLOWANCE,),
    )


def _spp_case(case_id: str, *, annual_income: float) -> Case:
    return Case(
        case_id=case_id,
        period=UK_STATPAY_PERIOD,
        metadata={
            **UK_STATPAY_METADATA,
            "scenario": "lone-father-statutory-paternity-pay",
            "yearly_earned_income": annual_income,
            "axiom_inputs": {
                _spp_input("uk_spp_pilot_supplied_earnings_related_rate"): (
                    _EARNINGS_RELATED_RATE
                ),
                _spp_input("uk_spp_pilot_supplied_lower_earnings_limit_weekly"): (
                    _LOWER_EARNINGS_LIMIT_WEEKLY
                ),
                _spp_input("uk_spp_pilot_supplied_paternity_pay_period_weeks"): (
                    _PATERNITY_PAY_PERIOD_WEEKS
                ),
            },
            "euromod_inputs": _lone_parent_newborn_rows(
                mother_gender=1, annual_employment=annual_income
            ),
            "euromod_policy_switch_overrides": [
                list(pair) for pair in _TAKEUP_OVERRIDES
            ],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yem": {
                    "inputs": [
                        _spp_input("uk_spp_pilot_supplied_normal_weekly_earnings")
                    ],
                    "divide_by": _ANNUAL_GROSS_TO_WEEKLY_DIVISOR,
                },
            },
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 32,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.YEARLY_EARNED_INCOME: annual_income,
                },
            ),
        ),
        outputs=(Concepts.UK_STATUTORY_PATERNITY_PAY,),
    )


def _lone_parent_newborn_rows(
    *,
    mother_gender: int,
    annual_employment: float = 0.0,
    annual_self_employment: float = 0.0,
) -> list[dict[str, float | int]]:
    """One working parent (the head) and a newborn, no second adult.

    A single-earner household so the household-summed ``yem`` / ``yse`` equals
    the parent's own earnings. ``dgn`` 0 marks the mother (SMP/MA), 1 the father
    (SPP); ``dmb`` 1 on the newborn drives the maternity duration. ``les`` 1
    (self-employed) is used for the Maternity Allowance case so no Statutory
    Maternity Pay is payable.
    """
    parent_id, child_id = 101, 103
    monthly_employment = annual_employment / 12.0
    monthly_self_employment = annual_self_employment / 12.0
    self_employed = annual_self_employment > 0
    employed = annual_employment > 0
    parent = {
        "idhh": 1,
        "idperson": parent_id,
        "idpartner": 0,
        "idmother": 0,
        "idfather": 0,
        "dag": 30 if mother_gender == 0 else 32,
        "dgn": mother_gender,
        "dms": 1,
        "dmb": 0,
        "drgn1": 1,
        "dhr": 1,
        "les": 1 if self_employed else (3 if employed else 0),
        "lfs": 15 if (employed or self_employed) else 0,
        "lhw": 40 if (employed or self_employed) else 0,
        "liwmy": 12 if (employed or self_employed) else 0,
        "liwwh": 40 if (employed or self_employed) else 0,
        "yem": monthly_employment,
        "yemmy": 12 if employed else 0,
        "yse": monthly_self_employment,
        "ysemy": 12 if self_employed else 0,
        "dec": 0,
        "dwt": 1_000.0,
    }
    child = {
        "idhh": 1,
        "idperson": child_id,
        "idpartner": 0,
        "idmother": parent_id if mother_gender == 0 else 0,
        "idfather": parent_id if mother_gender == 1 else 0,
        "dag": 0,
        "dgn": 1,
        "dms": 1,
        "dmb": 1,
        "drgn1": 1,
        "dhr": 0,
        "les": 0,
        "lfs": 0,
        "lhw": 0,
        "liwmy": 0,
        "liwwh": 0,
        "yem": 0.0,
        "yemmy": 0,
        "yse": 0.0,
        "ysemy": 0,
        "dec": 2,
        "dwt": 1_000.0,
    }
    return [parent, child]


def _smp_input(name: str) -> str:
    return f"{SMP_MODULE}#input.{name}"


def _ma_input(name: str) -> str:
    return f"{MA_MODULE}#input.{name}"


def _spp_input(name: str) -> str:
    return f"{SPP_MODULE}#input.{name}"
