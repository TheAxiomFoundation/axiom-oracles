"""Household Housing Benefit suite for the UKMOD ``bho_s`` oracle.

Where ``uk_universal_credit`` runs the working-age Universal Credit award and
``uk_pension_credit`` the pensioner guarantee credit, this suite compares the
legacy income-related Housing Benefit award: for a renter benefit unit it pays
the appropriate maximum housing benefit (100 per cent of eligible rent less
non-dependant deductions) reduced by 65 per cent of the excess of applicable
income over the applicable amount. It builds a hypothetical renter grid —
single and couple, working-age and pension-age, an earnings sweep crossing the
65 per cent taper, and a non-dependant-deduction case — and runs it against
CeMPA's UKMOD Housing Benefit output ``bho_s`` on the registration-free public
model (UKMOD_PUBLIC_B2026.03, system UK_2026, dataset training_data).

Verified UKMOD conventions (read from ``UKMOD_PUBLIC_B2026.03`` ``UK_2026``,
policy ``bho_uk`` — executed numbers are emitted only on the x64 runner):

- Housing Benefit is *simulated*: ``bho_uk`` (Switch=on) computes ``bho_s`` from
  statute. The award formula the ``BenCalc`` applies is
  ``i_bho_maxHousBen - 0.65 * (ymn01_s - i_bho_prelimAmt)`` — the maximum housing
  benefit less 65 per cent of the excess of the HB means (``ymn01_s``, "Means
  HB") over the preliminary applicable amount (``i_bho_prelimAmt``). This is the
  same structure as the composed pilot pipeline
  (rulespec-uk ``housing_benefit_composed_entitlement_pipeline``, #83):
  ``rent_after_taper = eligible_rent - 0.65 * (applicable_income - applicable_amount)``,
  ``entitlement = rent_after_taper - non_dependant_deductions``. So ``bho_s`` is
  the parity target for the pipeline's ``hb_pilot_entitlement``.

- The 65 per cent taper is the ``$HBUCTaper``-equivalent literal ``0.65`` in the
  ``bho_uk`` BenCalc, matching the pipeline's regulation 71 / regulation 51
  ``hb_pilot_taper_rate`` (0.65).

- ``i_bho_maxHousBen`` is the eligible rent ``xhcrt + xhcsc`` for social renters
  (``amrtn=5``) with no excess bedrooms, less the regulation 74 / regulation 55
  non-dependant deductions. For social renters with excess bedrooms the
  size-criteria (bedroom-tax) reduction applies (14 per cent of eligible rent
  for one excess room, 25 per cent for two or more); these cases hold the
  bedroom count at the entitled level (``i_excess_nRooms=0``) so the compared
  maximum is the full eligible rent and the size-criteria path — which the pilot
  pipeline does not model, and which the Scottish DHP row ``bhosc01_uk`` mitigates
  downstream — is out of scope here.

- The HB means ``ymn01_s`` is UKMOD's own assessable income for Housing Benefit,
  built internally with UKMOD's earnings disregards (``ydg03_s``, "Disregard
  HBCTB") and capital tariff income (``yiviy03_s``, "Tariff Income HBCTB"). The
  pipeline consumes a pre-computed ``hb_pilot_applicable_income`` (PolicyEngine's
  ``housing_benefit_applicable_income``, whose earnings disregards differ from
  the statute — flagged in the #83 pipeline summary). To isolate the taper /
  maximum-benefit / non-dependant mechanics from the disregard-build divergence,
  the suite bridges UKMOD's assessed ``ymn01_s`` into the pipeline's
  ``hb_pilot_applicable_income`` (as ``uk_pension_credit`` bridges ``boact_s``),
  so both engines taper the identical assessable income. ``ymn01_s`` is a monthly
  amount that annualizes ×12 to the pipeline's annual applicable-income input.

- ``bho_s`` is a monthly Housing Benefit amount; the composed pipeline is annual
  (``hb_pilot_entitlement`` is a Year-period Money output). The euromod adapter
  annualizes monthly UKMOD outputs (×12), so the comparison is annual-to-annual.

- ``bho_s`` embeds UKMOD's Housing Benefit take-up correction (the "fully random"
  function ``i_bho_probtu`` splits benefit units into take-up groups
  ``i_bho_grptu``: group 1 = on Income Support / Pension Credit, no correction
  and always paid; group 2 = working-age in work, paid when ``i_rand_tu <=
  $HBTUWAWork`` = 0.59; group 3 = working-age not in work, ``<= $HBTUWANowork`` =
  0.93; group 4 = pensioner, ``<= $HBTUPen`` = 0.85) and a Universal-Credit
  transition (``i_bho_noUC`` / ``i_bho_yesUC``) that can zero a would-be award
  away from the statutory entitlement; the clean pre-correction value is
  ``i_bho_noUC``. For a hypothetical benefit unit the stochastic ``i_rand_tu``
  draw marks some units as non-takers and returns a zero award that is not the
  statutory entitlement — the same EUROMOD-platform behaviour the merged
  ``uk-universal-credit`` and ``uk-pension-credit`` suites found (recorded in
  ``axiom_oracles/data/euromod_issues.json``). The suite requests the take-up
  overrides so the intent to compare the statutory entitlement is explicit and
  recorded on every case, and — per the or#168 constant-override "pinning" path
  — the comparison spec pins the three HB take-up rates to 1.0 through
  ``euromod_constant_overrides`` so a runner regeneration returns statutory
  entitlements to verify the income test against, disposing any residual zeros
  ``upstream_engine_gap`` (recharacterization per or#168 / or#170).

This suite runs where the x64 UKMOD runtime and model checkout are available and
is regenerated by ``scripts/regenerate_euromod_uk.sh``; on runners without them
it re-emits the committed dashboard report.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity


UK_SCOPE = {"type": "country", "geoid": "UK"}
UK_HB_METADATA = {
    "locale": "UK",
    "scope": UK_SCOPE,
    "axiom_entity": "Family",
    "axiom_entity_id": "benefit_unit",
}

# The composed Housing Benefit entitlement pipeline (rulespec-uk#83). Its award
# output is ``hb_pilot_entitlement`` and its Family-level inputs are supplied as
# ``<module>#input.<name>``.
HB_MODULE = "uk:policies/housing_benefit_composed_entitlement_pipeline"

# The Housing Benefit Regulations 2006 amounts are 2026-27; the composed pipeline
# is effective from 2026-04-01. UKMOD UK_2026 uses the same frozen 2026-27 rates.
UK_HB_PERIOD = "2026-04"

# UKMOD's Housing Benefit take-up correction and UC transition; the suite
# requests the "fully random"/"BTA" policy switches off so the intent to compare
# the statutory entitlement is explicit and recorded on every case. The
# comparison spec additionally pins the HB take-up rates to 1.0 via
# ``euromod_constant_overrides`` (or#168 pinning path) so a runner regeneration
# returns statutory entitlements; residual zeros are dispositioned per case.
_TAKEUP_OVERRIDES = (("BTA_uk", False), ("random_uk", False))

# EUROMOD demographic / labour codes (shared with the UC and PC suites).
_DMS_SINGLE = 1
_DMS_COUPLE = 2
_DEC_CHILD = 4
_LES_EMPLOYED = 3
_LES_CHILD = 6
_LES_INACTIVE = 0
_LES_PENSIONER = 5
# Tenure (``amrtn``): social renter, so the eligible rent ``xhcrt`` enters
# Housing Benefit and the size-criteria path is reachable (held at nil excess
# bedrooms here). Owner-occupiers (``amrtn=1``) receive no Housing Benefit.
_AMRTN_SOCIAL_RENTER = 5
_DCT = 15
_DRGN = 2

# Working-age and pension-age head ages (UKMOD UK_2026 uses 66 for the standard
# pension age; 70 is safely above it and 35/40 safely below).
_AGE_WORKING = 40
_AGE_WORKING_YOUNGER = 22
_AGE_PARTNER_WORKING = 38
_AGE_PENSION = 70
_AGE_PARTNER_PENSION = 68


def uk_housing_benefit_cases() -> list[Case]:
    """Household Housing Benefit cases for the UKMOD UK_2026 oracle."""

    return [
        *_composition_cases(),
        *_earnings_sweep_cases(),
        *_non_dependant_cases(),
        *_pension_age_cases(),
    ]


# --- Case families ---------------------------------------------------------


def _composition_cases() -> list[Case]:
    """Single/couple renter benefit units with no earnings.

    With no earnings the HB means ``ymn01_s`` is nil (no other assessable income
    in the rows), so the taper does not bite and the award is the full eligible
    rent — the cleanest maximum-housing-benefit comparison, free of the
    earnings-disregard divergence.
    """

    return [
        _hb_case(
            "uk-hb-single-under25-renter",
            couple=False,
            head_age=_AGE_WORKING_YOUNGER,
            monthly_rent=500.0,
        ),
        _hb_case(
            "uk-hb-single-renter",
            couple=False,
            head_age=_AGE_WORKING,
            monthly_rent=550.0,
        ),
        _hb_case(
            "uk-hb-couple-renter",
            couple=True,
            head_age=_AGE_WORKING,
            monthly_rent=650.0,
        ),
    ]


def _earnings_sweep_cases() -> list[Case]:
    """Single working-age renter, earnings crossing the 65 per cent taper.

    The single 25-or-over applicable amount is 95.55/week = 4,968.60/year. The
    sweep runs earnings from below to well above the applicable amount so the
    taper (65 per cent of the excess of the HB means over the applicable amount)
    engages and eventually exhausts the award. The HB means ``ymn01_s`` is
    bridged into the pipeline's applicable income, so both engines taper the
    identical assessed income and the sweep isolates the taper arithmetic.
    """

    grid = (0.0, 6_000.0, 10_000.0, 14_000.0, 18_000.0)
    return [
        _hb_case(
            f"uk-hb-single-renter-earn{int(annual)}",
            couple=False,
            head_age=_AGE_WORKING,
            monthly_rent=550.0,
            head_annual_earnings=annual,
        )
        for annual in grid
    ]


def _non_dependant_cases() -> list[Case]:
    """Couple renter with one non-dependant in a gross-income band.

    Regulation 74 deducts a per-non-dependant amount from the maximum housing
    benefit by the non-dependant's gross weekly income band. This case supplies
    one non-dependant at a band-representative gross income so the comparison
    exercises the regulation 74 deduction. The ``i_excess_nRooms`` size-criteria
    path is held at nil excess bedrooms, and the non-dependant=0 composition
    cases above give the clean no-deduction baseline (the #83 non-dependant
    filter precedent).
    """

    return [
        _hb_case(
            "uk-hb-couple-renter-1nondep",
            couple=True,
            head_age=_AGE_WORKING,
            monthly_rent=750.0,
            number_of_non_dependants=1,
            non_dependant_gross_weekly_income=300.0,
        ),
    ]


def _pension_age_cases() -> list[Case]:
    """Single and couple pension-age renters (SI 2006/214 personal allowances).

    Pension-age Housing Benefit uses the higher personal allowances
    (single 256.00/week, couple 383.35/week), so the applicable amount is larger
    and the award is the full eligible rent across the groundable income range on
    these no-earnings rows.
    """

    return [
        _hb_case(
            "uk-hb-single-pension-age-renter",
            couple=False,
            head_age=_AGE_PENSION,
            monthly_rent=550.0,
            pension_age=True,
        ),
        _hb_case(
            "uk-hb-couple-pension-age-renter",
            couple=True,
            head_age=_AGE_PENSION,
            monthly_rent=650.0,
            pension_age=True,
        ),
    ]


# --- Case + row construction ----------------------------------------------


def _hb_case(
    case_id: str,
    *,
    couple: bool,
    head_age: int,
    monthly_rent: float,
    head_annual_earnings: float = 0.0,
    number_of_non_dependants: int = 0,
    non_dependant_gross_weekly_income: float = 0.0,
    pension_age: bool = False,
) -> Case:
    rows = _euromod_household_rows(
        couple=couple,
        head_age=head_age,
        monthly_rent=monthly_rent,
        head_annual_earnings=head_annual_earnings,
        pension_age=pension_age,
    )
    entities = _entities(
        couple=couple,
        head_age=head_age,
        head_annual_earnings=head_annual_earnings,
        monthly_rent=monthly_rent,
    )
    axiom_inputs = _axiom_pipeline_inputs(
        couple=couple,
        head_age=head_age,
        monthly_rent=monthly_rent,
        number_of_non_dependants=number_of_non_dependants,
        non_dependant_gross_weekly_income=non_dependant_gross_weekly_income,
        pension_age=pension_age,
    )
    return Case(
        case_id=case_id,
        period=UK_HB_PERIOD,
        facts={
            Concepts.LIVING_RENTING: True,
            Concepts.RENT_PAID: monthly_rent * 12.0,
            Concepts.YEARLY_EARNED_INCOME: head_annual_earnings,
        },
        metadata={
            **UK_HB_METADATA,
            "scenario": "household-housing-benefit",
            "couple": couple,
            "head_age": head_age,
            "monthly_rent": monthly_rent,
            "head_annual_earnings": head_annual_earnings,
            "number_of_non_dependants": number_of_non_dependants,
            "non_dependant_gross_weekly_income": non_dependant_gross_weekly_income,
            "pension_age": pension_age,
            "axiom_inputs": axiom_inputs,
            "euromod_inputs": rows,
            "euromod_policy_switch_overrides": [list(pair) for pair in _TAKEUP_OVERRIDES],
            # Bridge UKMOD's assessed Housing Benefit means (``ymn01_s``, "Means
            # HB") into the composed pipeline's applicable-income input so both
            # engines taper the identical assessed income (isolating the taper /
            # maximum-benefit / non-dependant mechanics from UKMOD's internal
            # earnings-disregard build). ``ymn01_s`` is a monthly amount that the
            # euromod adapter annualizes (×12) to the pipeline's annual
            # applicable-income input.
            "euromod_to_axiom_input_bridge": {
                "ymn01_s": [_pipeline_input("hb_pilot_applicable_income")],
            },
        },
        entities=entities,
        outputs=(Concepts.UK_HOUSEHOLD_HOUSING_BENEFIT_AWARD,),
    )


def _pipeline_input(name: str) -> str:
    return f"{HB_MODULE}#input.{name}"


def _axiom_pipeline_inputs(
    *,
    couple: bool,
    head_age: int,
    monthly_rent: float,
    number_of_non_dependants: int,
    non_dependant_gross_weekly_income: float,
    pension_age: bool,
) -> dict[str, float | int | bool]:
    """Map the renter household to the composed-pipeline inputs.

    The assessable income arrives through the ``euromod_to_axiom_input_bridge``
    (UKMOD's ``ymn01_s``), so ``hb_pilot_applicable_income`` is seeded at zero
    here and overwritten by the bridge. Eligible rent is supplied as the annual
    rent (social-renter path, so no LHA cap). The premium amount is held at zero:
    on these hypothetical rows UKMOD applies the disability/carer/family premiums
    only when a disability benefit is present in the data, which the rows do not
    carry, so the compared award isolates the personal-allowance applicable
    amount, the taper, the maximum benefit, and the non-dependant deductions.
    """

    return {
        _pipeline_input("hb_pilot_is_couple"): couple,
        _pipeline_input("hb_pilot_any_member_pension_age"): pension_age,
        _pipeline_input("hb_pilot_eldest_adult_age"): head_age,
        _pipeline_input("hb_pilot_premium_amount"): 0.0,
        _pipeline_input("hb_pilot_number_of_non_dependants"): number_of_non_dependants,
        _pipeline_input(
            "hb_pilot_non_dependant_gross_weekly_income"
        ): non_dependant_gross_weekly_income,
        # Seeded at zero; the euromod_to_axiom_input_bridge overwrites it with
        # UKMOD's assessed ``ymn01_s`` (annualized).
        _pipeline_input("hb_pilot_applicable_income"): 0.0,
        _pipeline_input("hb_pilot_eligible_rent"): monthly_rent * 12.0,
        _pipeline_input("hb_pilot_lha_path_applies"): False,
        _pipeline_input("hb_pilot_maximum_rent"): 0.0,
    }


def _entities(
    *,
    couple: bool,
    head_age: int,
    head_annual_earnings: float,
    monthly_rent: float,
) -> tuple[Entity, ...]:
    """Concept-keyed entities mirroring the explicit UKMOD rows."""

    people: list[Entity] = [
        Entity(
            entity_id="head",
            kind="person",
            facts={
                Concepts.PERSON_AGE: head_age,
                Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                Concepts.YEARLY_EARNED_INCOME: head_annual_earnings,
            },
        )
    ]
    if couple:
        partner_age = _AGE_PARTNER_PENSION if head_age >= _AGE_PENSION else _AGE_PARTNER_WORKING
        people.append(
            Entity(
                entity_id="partner",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: partner_age,
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
    monthly_rent: float,
    head_annual_earnings: float,
    pension_age: bool,
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
            monthly_rent=monthly_rent,
            annual_earnings=head_annual_earnings,
            pension_age=pension_age,
        )
    ]
    if couple:
        partner_age = _AGE_PARTNER_PENSION if pension_age else _AGE_PARTNER_WORKING
        rows.append(
            _adult_row(
                idperson=partner_id,
                age=partner_age,
                gender=0,
                is_head=False,
                partner_id=head_id,
                couple=True,
                monthly_rent=0.0,
                annual_earnings=0.0,
                pension_age=pension_age,
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
    monthly_rent: float,
    annual_earnings: float,
    pension_age: bool,
) -> dict[str, float | int]:
    employed = annual_earnings > 0
    if pension_age:
        les = _LES_PENSIONER
    elif employed:
        les = _LES_EMPLOYED
    else:
        les = _LES_INACTIVE
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
        "les": les,
        "lhw": 40 if employed else 0,
        "loc": 5,
        # Social renter, so the eligible rent enters Housing Benefit. The head
        # carries the household rent ``xhcrt``.
        "amrtn": _AMRTN_SOCIAL_RENTER,
        "yem": annual_earnings / 12.0,
        "yse": 0.0,
        "yiy": 0.0,
        "poa": 0.0,
        "boact00": 0.0,
        "xhcrt": monthly_rent,
        "xhcsc": 0.0,
        "afc": 0.0,
    }
