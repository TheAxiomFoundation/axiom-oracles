"""Household Winter Fuel Payment suite for the UKMOD ``boaht_s`` oracle.

The Winter Fuel Payment is a pensioner heating allowance: a benefit-unit amount
paid when the unit contains at least one member of state pension age, subject
since 2024/25 to an income-recovery means test. This suite builds a hypothetical
England-and-Wales pensioner grid — single and couple, the under-80 and 80+ tiers,
and an assessable-income sweep crossing the recovery threshold — and runs it
against CeMPA's UKMOD Winter Fuel output ``boaht_s`` on the registration-free
public model (UKMOD_PUBLIC_B2026.03, system UK_2026, dataset training_data).

Verified UKMOD conventions (executed against UKMOD_PUBLIC_B2026.03, UK_2026):

- The Winter Fuel column is ``boaht_s`` (UKMOD ``boaht_uk``, "BEN: Pensioner's
  annual heating allowance"). UKMOD reports it as a monthly *per-member* amount
  allocated across the pension-age members of the unit; the euromod adapter sums
  it across the benefit unit and annualizes (× 12), so the compared value is the
  annual household award. The composed pilot output ``wfp_pilot_award_amount``
  is an annual household amount, so the comparison is annual-to-annual.

- The award is a HOUSEHOLD amount and does not scale with the number of
  pension-age members (verified: a single pensioner and a couple who are both of
  pension age and both under 80 each receive a household £200 — UKMOD allocates
  £100 to each member of the couple, summing to £200, not £400). The 80+ tier
  applies to the whole unit when ANY member is 80 or over (verified: a couple
  where one member is 80 receives the household £300, allocated £150/£150).

- The England-and-Wales amounts are £200 where nobody in the unit is aged 80 or
  over and £300 where any member is 80 or over (verified exact: single 67 → £200,
  single 80 → £300, couple both 67 → £200, couple 67+80 → £300). These match the
  Social Fund Winter Fuel Payment Regulations 2025 (SI 2025/969) regulation 3(1)
  and 3(4) amounts encoded in the composed pilot. Scotland (``drgn1=12``) runs a
  higher devolved instrument (£211 / £317 — Pension Age Winter Heating Payment,
  not SI 2025/969), which is not encoded in Axiom; this suite is England-and-Wales
  only (``drgn1`` set to an English region) and does not place Scottish cases.

- The award is withdrawn above the income-recovery threshold: UKMOD gates every
  BenCalc component on ``il_toty < $WFCBThresh`` (the £35,000 annual claw-back
  threshold; UKMOD's ``il_toty`` is monthly, so the gate is monthly income <
  £35,000 / 12 = £2,916.67). Verified strict ``<``: a single pensioner with
  ``il_toty`` 2,916.66/month is paid £200 and one with 2,916.67/month is paid
  nil. The cases run assessable income (employment income ``yem``) clear of the
  boundary — £30,000/year (£2,500/month, below) pays and £42,000/year
  (£3,500/month, above) is withdrawn — so the float boundary is not exercised.
  The recovery-threshold gate is supplied to the pilot as the
  ``wfp_pilot_income_below_recovery_threshold`` input (true below £35,000/year,
  false above).

- The award requires a member of state pension age: a single claimant aged 60
  (below the UK_2026 pension age of 66) receives nil (verified: ``boaht_s`` 0).
  The pilot's ``wfp_pilot_has_pension_age_member`` input carries this gate.

- Winter Fuel does NOT draw UKMOD's stochastic take-up correction (unlike
  Universal Credit and Pension Credit): the payment is deterministic on these
  cases (verified — the award is unchanged with ``BTA_uk`` / ``random_uk`` off),
  so no take-up disposition is required. The take-up overrides are still
  requested so the intent to compare the statutory award is explicit and
  recorded on every case.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity


UK_SCOPE = {"type": "country", "geoid": "UK"}
UK_WFP_METADATA = {
    "locale": "UK",
    "scope": UK_SCOPE,
    "axiom_entity": "Family",
    "axiom_entity_id": "benefit_unit",
}

# The composed Winter Fuel Payment pilot pipeline (rulespec-uk). Its award output
# is ``wfp_pilot_award_amount`` and its Family-level judgment inputs are supplied
# as ``<module>#input.<name>``.
WFP_MODULE = "uk:policies/winter_fuel_payment_composed_award_pipeline"

# SI 2025/969 reg 3 amounts are 2025/26; the composed pipeline is effective from
# 2025-09-15. The 2026-27 fiscal-year evaluation reads the same amounts. The
# cases start on the 6 April 2026 fiscal boundary (the engine selects parameter
# versions by period.start; the #194 guard requires UK suites to start on/after
# 6 April 2026). UKMOD resolves the policy year from euromod_system (UK_2026) and
# ignores the case period.
UK_WFP_PERIOD = "2026-04-06"

# The UKMOD income-recovery threshold: £35,000/year annual income (WFCBThresh).
_RECOVERY_THRESHOLD_ANNUAL = 35_000.0

# EUROMOD demographic / labour codes.
_DMS_SINGLE = 1
_DMS_COUPLE = 2
_LES_PENSIONER = 5
_LES_EMPLOYED = 3
_AMRTN_OWNER = 1
_DCT = 15
# An English working-age region (Scotland is drgn1=12 and runs a different
# instrument, so it is excluded from this England-and-Wales suite).
_DRGN_ENGLAND = 2

# State-pension-age boundary (UKMOD UK_2026 uses 66; 67 is above it, 60 below).
_AGE_REACHED_PENSION = 67
_AGE_PARTNER_REACHED_PENSION = 66
_AGE_80 = 82
_AGE_BELOW_PENSION = 60

# UKMOD's take-up correction; requested off (verified ineffective on Winter Fuel,
# which does not draw take-up) so the intent to compare the statutory award is
# explicit on every case.
_TAKEUP_OVERRIDES = (("BTA_uk", False), ("random_uk", False))


def uk_winter_fuel_cases() -> list[Case]:
    """Household Winter Fuel Payment cases for the UKMOD UK_2026 oracle."""

    return [
        *_age_tier_cases(),
        *_income_means_test_cases(),
        *_pension_age_boundary_cases(),
    ]


# --- Case families ---------------------------------------------------------


def _age_tier_cases() -> list[Case]:
    """Single and couple, under-80 and 80+ tiers, income below the threshold.

    Exercises the £200 under-80 and £300 at-80 England-and-Wales amounts and the
    household (non-per-member) allocation: a couple both under 80 receives £200
    (not £400), and a couple with one member 80+ receives £300 (the whole unit
    takes the 80+ tier).
    """

    return [
        _wfp_case("uk-wfp-single-under80", couple=False, any_80=False),
        _wfp_case("uk-wfp-single-age80", couple=False, any_80=True),
        _wfp_case("uk-wfp-couple-under80", couple=True, any_80=False),
        _wfp_case("uk-wfp-couple-one-age80", couple=True, any_80=True),
    ]


def _income_means_test_cases() -> list[Case]:
    """Single pensioner, assessable income below and above the recovery threshold.

    Below £35,000/year the award is paid; above it the payment is withdrawn. The
    income points sit clear of the £35,000 boundary (£30,000 below, £42,000 above)
    so the strict-inequality float boundary is not exercised.
    """

    return [
        _wfp_case(
            "uk-wfp-single-income30000-below-threshold",
            couple=False,
            any_80=False,
            annual_income=30_000.0,
        ),
        _wfp_case(
            "uk-wfp-single-income42000-above-threshold",
            couple=False,
            any_80=False,
            annual_income=42_000.0,
        ),
    ]


def _pension_age_boundary_cases() -> list[Case]:
    """Single claimant below state pension age — no Winter Fuel Payment."""

    return [
        _wfp_case(
            "uk-wfp-single-below-pension-age",
            couple=False,
            any_80=False,
            head_age=_AGE_BELOW_PENSION,
            has_pension_age_member=False,
        ),
    ]


# --- Case + row construction ----------------------------------------------


def _wfp_case(
    case_id: str,
    *,
    couple: bool,
    any_80: bool,
    annual_income: float = 0.0,
    head_age: int | None = None,
    has_pension_age_member: bool = True,
) -> Case:
    if head_age is None:
        head_age = _AGE_80 if any_80 else _AGE_REACHED_PENSION
    income_below_threshold = annual_income < _RECOVERY_THRESHOLD_ANNUAL
    rows = _euromod_household_rows(
        couple=couple,
        head_age=head_age,
        annual_income=annual_income,
    )
    entities = _entities(couple=couple, head_age=head_age, annual_income=annual_income)
    axiom_inputs = _axiom_pipeline_inputs(
        has_pension_age_member=has_pension_age_member,
        any_80=any_80,
        income_below_threshold=income_below_threshold,
    )
    return Case(
        case_id=case_id,
        period=UK_WFP_PERIOD,
        facts={
            Concepts.PERSON_AGE: head_age,
            Concepts.YEARLY_EARNED_INCOME: annual_income,
        },
        metadata={
            **UK_WFP_METADATA,
            "scenario": "household-winter-fuel-payment",
            "couple": couple,
            "any_80": any_80,
            "annual_income": annual_income,
            "head_age": head_age,
            "has_pension_age_member": has_pension_age_member,
            "income_below_threshold": income_below_threshold,
            "axiom_inputs": axiom_inputs,
            "euromod_inputs": rows,
            "euromod_policy_switch_overrides": [
                list(pair) for pair in _TAKEUP_OVERRIDES
            ],
        },
        entities=entities,
        outputs=(Concepts.UK_HOUSEHOLD_WINTER_FUEL_PAYMENT_AWARD,),
    )


def _pipeline_input(name: str) -> str:
    return f"{WFP_MODULE}#input.{name}"


def _axiom_pipeline_inputs(
    *,
    has_pension_age_member: bool,
    any_80: bool,
    income_below_threshold: bool,
) -> dict[str, bool]:
    """Map the pensioner household to the composed-pipeline judgment inputs.

    The pilot is a benefit-unit amount driven by three judgments: whether the
    unit contains a state-pension-age member, whether any member is 80+, and
    whether income is below the recovery threshold. UKMOD determines these from
    the household rows (age, ``il_toty``); the same facts are supplied here so
    both engines test the identical unit.
    """

    return {
        _pipeline_input("wfp_pilot_has_pension_age_member"): has_pension_age_member,
        _pipeline_input("wfp_pilot_any_member_aged_80_or_over"): any_80,
        _pipeline_input(
            "wfp_pilot_income_below_recovery_threshold"
        ): income_below_threshold,
    }


def _entities(
    *, couple: bool, head_age: int, annual_income: float
) -> tuple[Entity, ...]:
    """Concept-keyed entities mirroring the explicit UKMOD rows."""

    people: list[Entity] = [
        Entity(
            entity_id="head",
            kind="person",
            facts={
                Concepts.PERSON_AGE: head_age,
                Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                Concepts.YEARLY_EARNED_INCOME: annual_income,
            },
        )
    ]
    if couple:
        people.append(
            Entity(
                entity_id="partner",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: _AGE_PARTNER_REACHED_PENSION,
                    Concepts.HOUSEHOLD_RELATION: "Spouse",
                    Concepts.YEARLY_EARNED_INCOME: 0.0,
                },
            )
        )
    return tuple(people)


def _euromod_household_rows(
    *,
    couple: bool,
    head_age: int,
    annual_income: float,
) -> list[dict[str, float | int]]:
    head_id = 101
    partner_id = 102 if couple else 0
    rows: list[dict[str, float | int]] = [
        _adult_row(
            idperson=head_id,
            age=head_age,
            gender=1,
            is_head=True,
            partner_id=partner_id,
            couple=couple,
            annual_income=annual_income,
        )
    ]
    if couple:
        rows.append(
            _adult_row(
                idperson=partner_id,
                age=_AGE_PARTNER_REACHED_PENSION,
                gender=0,
                is_head=False,
                partner_id=head_id,
                couple=True,
                annual_income=0.0,
            )
        )
    return rows


def _adult_row(
    *,
    idperson: int,
    age: int,
    gender: int,
    is_head: bool,
    partner_id: int,
    couple: bool,
    annual_income: float,
) -> dict[str, float | int]:
    employed = annual_income > 0
    return {
        "idhh": 1,
        "idperson": idperson,
        "idpartner": partner_id,
        "idmother": 0,
        "idfather": 0,
        "idmotherbio": 0,
        "idfatherbio": 0,
        "drgn1": _DRGN_ENGLAND,
        "dct": _DCT,
        "dwt": 1_000.0,
        "dag": age,
        "dgn": gender,
        "dms": _DMS_COUPLE if couple else _DMS_SINGLE,
        "dhr": 1 if is_head else 0,
        "dec": 0,
        "ddi": 0,
        # Income above the recovery threshold is supplied as employment income so
        # UKMOD's il_toty crosses the £35,000/year (£2,916.67/month) gate; a
        # pensioner with no income carries the pensioner labour status.
        "les": _LES_EMPLOYED if employed else _LES_PENSIONER,
        "lhw": 40 if employed else 0,
        "loc": 5,
        "amrtn": _AMRTN_OWNER,
        "yem": annual_income / 12.0,
        "yse": 0.0,
        "yiy": 0.0,
        "boact00": 0.0,
        "boactcm": 0.0,
        "poa": 0.0,
        "boa": 0.0,
        "poa00": 0.0,
        "xhcrt": 0.0,
        "xhcmomi": 0.0,
        "afc": 0.0,
    }
