"""Household Pension Credit suite for the UKMOD ``boamt_s`` oracle.

Where ``uk_universal_credit`` runs working-age means-tested transfers, Pension
Credit is the pensioner guarantee credit: it tops a benefit unit's assessable
income up to the standard minimum guarantee for a claimant who has reached the
qualifying age. This suite builds a hypothetical pensioner grid — single and
couple, an assessable-income sweep crossing the guarantee level, and the
state-pension-age boundary — and runs it against CeMPA's UKMOD Pension Credit
output ``boamt_s`` on the registration-free public model (UKMOD_PUBLIC_B2026.03,
system UK_2026, dataset training_data).

Verified UKMOD conventions (executed against UKMOD_PUBLIC_B2026.03, UK_2026):

- Pension Credit is *simulated*: the total ``boamt_s`` (guarantee credit
  ``boamtmm_s`` + savings credit ``boamtxp_s``) is computed inside the ``bsa_uk``
  social-assistance policy. The state pension is *not* simulated — the policy
  ``boact_uk`` only uprates the ``boact00`` state-pension data input
  (``boact_s = boact00 * $boactFactor``), with no entitlement logic — so the
  state pension enters this comparison as a data input, not an encoded output.

- The Pension Credit income test assesses the state pension the benefit unit
  receives (the ``boact_s`` output, uprated from the ``boact00`` input); a
  private/occupational pension supplied through ``poa`` is not assessed on the
  demo data. So assessable income is supplied as the ``boact00`` state-pension
  input and read back through ``boact_s``. The guarantee credit is the standard
  minimum guarantee less that assessed income, floored at zero (verified exact:
  state pension 166.67/month reduces the single guarantee from 1034.17 to
  867.50, 666.67/month to 367.50, 1000.00/month to 34.17).

- ``boamt_s`` is a monthly Pension Credit amount; the composed pilot pipeline
  (rulespec-uk ``pension_credit_composed_award_pipeline``) is expressed weekly
  (the native period of the State Pension Credit Regulations 2002 amounts, so
  every value is a grounded weekly statutory rate with no period-conversion
  arithmetic). The adapter converts the monthly ``boamt_s`` to weekly with
  UKMOD's own weekly-to-monthly convention (monthly = weekly * 365 / 7 / 12) so
  the comparison is weekly-to-weekly (verified: UKMOD single full guarantee
  1034.17/month = 238.00/week). The assessed state pension ``boact_s`` (monthly)
  is bridged into the pipeline's ``pc_pilot_state_pension_income_weekly`` with
  the same divisor so both engines test the identical assessable income.

- The standard minimum guarantee amounts match to the penny: 238.00/week single
  (1034.17/month) and 363.25/week couple (1578.41/month). These are the
  regulation 6(1) amounts encoded in the pipeline and the UKMOD UK_2026
  constants ``$PCGCSing`` / ``$PCGCCoup``.

- ``boamt_s`` embeds UKMOD's Pension Credit take-up and Universal-Credit-
  transition correction (take-up estimates ``$PCGCSCTU`` = 0.69, ``$PCSCTU`` =
  0.37, applied through the ``i_rand_tu`` draw and the ``i_bsa_noUC`` /
  ``i_bsa_yesUC`` transition split). For hypothetical benefit units this
  deterministic draw (seed 3) marks some units as transitioned to Universal
  Credit and returns a zero Pension Credit award that is not the statutory
  entitlement. This is a EUROMOD-platform modelling behaviour, not an Axiom
  encoding gap; it is recorded in ``axiom_oracles/data/euromod_issues.json``
  (``ukmod-pc-boamt-takeup-transition``) and dispositioned per case. Switching
  the ``random_uk`` policy off does not suppress the draw (verified — results
  are identical), the same behaviour the merged Universal Credit suite found;
  the suite requests the take-up overrides so the intent to compare the
  statutory entitlement is explicit and recorded on every case.

- Savings credit (``boamtxp_s``) is simulated but returns nil across the
  groundable pensioner income range on the demo data (the guarantee credit
  already tops income to the minimum and the savings-credit population is
  closed to pre-6-April-2016 pension-age reachers), so the compared total
  ``boamt_s`` equals its guarantee-credit component ``boamtmm_s`` here. This is
  a data-exercisability limit recorded in ``euromod_issues.json``
  (``ukmod-pc-savings-credit-nil-on-demo-data``), not an Axiom encoding gap.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity


UK_SCOPE = {"type": "country", "geoid": "UK"}
UK_PC_METADATA = {
    "locale": "UK",
    "scope": UK_SCOPE,
    "axiom_entity": "Family",
    "axiom_entity_id": "benefit_unit",
}

# The composed Pension Credit pilot pipeline (rulespec-uk). Its award output is
# ``pc_pilot_award_amount`` and its Family-level weekly inputs are supplied as
# ``<module>#input.<name>``.
PC_MODULE = "uk:policies/pension_credit_composed_award_pipeline"

# State Pension Credit Act 2002 amounts are 2026-27; the composed pipeline is
# effective from 2026-04-01. UKMOD UK_2026 uses the same frozen 2026-27 rates.
UK_PC_PERIOD = "2026-04"

# UKMOD converts its weekly Pension Credit constants to the monthly ``boamt_s``
# with a 365-day-year convention (monthly = weekly * 365 / 7 / 12). The euromod
# adapter converts ``boamt_s`` and the assessed state pension ``boact_s`` back to
# weekly with this factor (they are in the adapter's WEEKLY_OUTPUTS set) so the
# comparison and the bridged assessable income are weekly-to-weekly.

# UKMOD's take-up / UC-transition correction; the suite requests these overrides
# so the intent to compare the statutory entitlement is explicit and recorded on
# every case (verified ineffective at suppressing the draw, so mismatches are
# dispositioned per case).
_TAKEUP_OVERRIDES = (("BTA_uk", False), ("random_uk", False))

# EUROMOD demographic / labour codes.
_DMS_SINGLE = 1
_DMS_COUPLE = 2
_LES_PENSIONER = 5
_AMRTN_OWNER = 1
_DCT = 15
_DRGN = 2

# State-pension-age boundary (UKMOD UK_2026 uses 66 for the standard pension
# age; 67 is safely above it and 60 safely below).
_AGE_REACHED_PENSION = 67
_AGE_PARTNER_REACHED_PENSION = 66
_AGE_BELOW_PENSION = 60


def uk_pension_credit_cases() -> list[Case]:
    """Household Pension Credit cases for the UKMOD UK_2026 oracle."""

    return [
        *_single_income_sweep_cases(),
        *_pension_age_boundary_cases(),
        *_couple_income_sweep_cases(),
    ]


# --- Case families ---------------------------------------------------------


def _single_income_sweep_cases() -> list[Case]:
    """Single pensioner, assessable state pension crossing the single guarantee.

    The single standard minimum guarantee is 238.00/week (1034.17/month). Below
    it the guarantee credit tops income up to the minimum; above it Pension
    Credit is nil.
    """

    grid = (0.0, 2_000.0, 6_000.0, 8_000.0, 10_000.0, 12_000.0, 14_000.0)
    return [
        _pc_case(
            f"uk-pc-single-income{int(annual)}",
            couple=False,
            state_pension_annual=annual,
        )
        for annual in grid
    ]


def _pension_age_boundary_cases() -> list[Case]:
    """Single claimant below state pension age — no Pension Credit."""

    return [
        _pc_case(
            "uk-pc-single-below-pension-age",
            couple=False,
            state_pension_annual=0.0,
            head_age=_AGE_BELOW_PENSION,
            has_reached_pension_age=False,
        ),
    ]


def _couple_income_sweep_cases() -> list[Case]:
    """Couple pensioners, assessable state pension below the couple guarantee.

    The couple standard minimum guarantee is 363.25/week (1578.41/month). The
    sweep stays below the guarantee (where the income test is exact) plus a
    clearly-above-guarantee nil case.
    """

    grid = (0.0, 6_000.0, 12_000.0, 22_000.0)
    return [
        _pc_case(
            f"uk-pc-couple-income{int(annual)}",
            couple=True,
            state_pension_annual=annual,
        )
        for annual in grid
    ]


# --- Case + row construction ----------------------------------------------


def _pc_case(
    case_id: str,
    *,
    couple: bool,
    state_pension_annual: float,
    head_age: int = _AGE_REACHED_PENSION,
    has_reached_pension_age: bool = True,
) -> Case:
    rows = _euromod_household_rows(
        couple=couple,
        state_pension_annual=state_pension_annual,
        head_age=head_age,
    )
    entities = _entities(
        couple=couple,
        state_pension_annual=state_pension_annual,
        head_age=head_age,
    )
    axiom_inputs = _axiom_pipeline_inputs(
        couple=couple,
        has_reached_pension_age=has_reached_pension_age,
    )
    return Case(
        case_id=case_id,
        period=UK_PC_PERIOD,
        facts={
            Concepts.PENSION_INCOME: state_pension_annual,
        },
        metadata={
            **UK_PC_METADATA,
            "scenario": "household-pension-credit",
            "couple": couple,
            "state_pension_annual": state_pension_annual,
            "head_age": head_age,
            "has_reached_pension_age": has_reached_pension_age,
            "axiom_inputs": axiom_inputs,
            "euromod_inputs": rows,
            "euromod_policy_switch_overrides": [
                list(pair) for pair in _TAKEUP_OVERRIDES
            ],
            # Bridge UKMOD's assessed state pension (``boact_s``) into the
            # composed pipeline's weekly assessable-income input so both engines
            # test the identical income. The euromod adapter already converts
            # ``boact_s`` from UKMOD's monthly amount to weekly (it is in the
            # adapter's WEEKLY_OUTPUTS set), so the bridged value is weekly and
            # needs no further scaling here.
            "euromod_to_axiom_input_bridge": {
                "boact_s": [_pipeline_input("pc_pilot_state_pension_income_weekly")],
            },
        },
        entities=entities,
        outputs=(Concepts.UK_HOUSEHOLD_PENSION_CREDIT_AWARD,),
    )


def _pipeline_input(name: str) -> str:
    return f"{PC_MODULE}#input.{name}"


def _axiom_pipeline_inputs(
    *,
    couple: bool,
    has_reached_pension_age: bool,
) -> dict[str, float | int | bool]:
    """Map the pensioner household to the composed-pipeline inputs.

    The assessable state pension income arrives through the
    ``euromod_to_axiom_input_bridge`` (UKMOD's ``boact_s``), so it is not set
    here. The severe-disability and carer additional-amount counts are held at
    zero: on the demo data UKMOD applies the severe-disability premium only when
    a disability benefit is present in the data (``bdisc``/``bdimb``/... > 0),
    which the hypothetical rows do not carry, so the compared award isolates the
    standard-minimum-guarantee income test.
    """

    return {
        _pipeline_input("pc_pilot_is_couple"): couple,
        _pipeline_input("pc_pilot_has_reached_pension_age"): has_reached_pension_age,
        _pipeline_input("pc_pilot_state_pension_income_weekly"): 0.0,
        _pipeline_input("pc_pilot_number_of_severe_disability_additions"): 0,
        _pipeline_input("pc_pilot_number_of_carer_additions"): 0,
    }


def _entities(
    *,
    couple: bool,
    state_pension_annual: float,
    head_age: int,
) -> tuple[Entity, ...]:
    """Concept-keyed entities mirroring the explicit UKMOD rows."""

    people: list[Entity] = [
        Entity(
            entity_id="head",
            kind="person",
            facts={
                Concepts.PERSON_AGE: head_age,
                Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                Concepts.PENSION_INCOME: state_pension_annual,
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
                    Concepts.PENSION_INCOME: 0.0,
                },
            )
        )
    return tuple(people)


def _euromod_household_rows(
    *,
    couple: bool,
    state_pension_annual: float,
    head_age: int,
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
            state_pension_annual=state_pension_annual,
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
                state_pension_annual=0.0,
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
    state_pension_annual: float,
) -> dict[str, float | int]:
    return {
        "idhh": 1,
        "idperson": idperson,
        "idpartner": partner_id,
        "idmother": 0,
        "idfather": 0,
        "idmotherbio": 0,
        "idfatherbio": 0,
        "drgn1": _DRGN,
        "dct": _DCT,
        "dwt": 1_000.0,
        "dag": age,
        "dgn": gender,
        "dms": _DMS_COUPLE if couple else _DMS_SINGLE,
        "dhr": 1 if is_head else 0,
        "dec": 0,
        "ddi": 0,
        "les": _LES_PENSIONER,
        "lhw": 0,
        "loc": 5,
        "amrtn": _AMRTN_OWNER,
        "yem": 0.0,
        "yse": 0.0,
        "yiy": 0.0,
        # State pension enters Pension Credit as a data input (``boact00``), the
        # column UKMOD's income test assesses through ``boact_s``. Monthly demo
        # convention, so the annual case fact divides by twelve.
        "boact00": state_pension_annual / 12.0,
        "boactcm": 0.0,
        "poa": 0.0,
        "boa": 0.0,
        "poa00": 0.0,
        "xhcrt": 0.0,
        "xhcmomi": 0.0,
        "afc": 0.0,
    }
