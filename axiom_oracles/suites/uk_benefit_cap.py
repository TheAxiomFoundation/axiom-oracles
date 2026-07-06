"""Household benefit-cap suite for the UKMOD ``brduc_s`` oracle.

Where ``uk_universal_credit`` compares the composed Universal Credit *award*
(``bsauc_s``), this suite compares the regulation-80A/81 benefit-cap *reduction*
of that award. UKMOD does not write the cap into ``bsauc_s`` — it reports the
uncapped award and carries the cap effect in a separate output ``brduc_s``
(verified against UKMOD_PUBLIC_B2026.03: no ``bcap_uk`` function writes back into
``bsauc_s``). The composed UC pilot (rulespec-uk
``universal_credit_composed_award_pipeline``) computes the same reduction as
``uc_pilot_benefit_cap_reduction`` and applies it inside the section-8(1) award,
so the reduction is compared on its own on a shared capped-household grid.

Verified UKMOD conventions (executed against UKMOD_PUBLIC_B2026.03, UK_2026):

- The UC benefit-cap reduction column is ``brduc_s`` (UKMOD ``bcap_uk``,
  ``BenCalc comp_cond=(bsauc_s>0)``, ``comp_perTU = i_bcap_AmtCap - i_wtcchild``,
  ``lowlim=0``). It is a monthly assessment-period amount; the Axiom
  ``uc_pilot_benefit_cap_reduction`` is also monthly, so the comparison is
  monthly-to-monthly (``brduc_s`` is in the adapter's ``NON_ANNUALIZED_OUTPUTS``).

- UKMOD's UC cap applies only to two benefit-unit shapes (function
  ``i_bcap_AmtCap``): (a) a couple or lone parent *with* a dependent child
  (``$BcapUCwkids`` / London ``$BcapUCLon``), and (b) a single claimant with *no*
  dependent child (``$BcapUCnokid`` / London ``$BcapUCLonSing``). A couple with no
  children matches neither branch, so UKMOD applies no cap to it even when the UC
  award exceeds the limit (verified: couple, no children, £1,500/month rent —
  ``bsauc_s`` 2,166.97 > the £1,835.00 monthly couple limit, yet ``brduc_s`` 0).
  This grid therefore uses single-no-child cases (the clean parity shape) and
  couple/lone-parent-with-children cases (which carry the cap-base divergence
  below), and does not place a couple-no-child capped case.

- UKMOD's cap base ``il_bencap`` is the *total* welfare benefits of the unit —
  it sums ``bsauc_s`` (UC) *and* ``bch_s`` (Child Benefit) and the other
  legacy/means-tested benefits (verified from the UK_2026 ``il_bencap`` DefIl).
  The composed UC pilot's cap excess is ``max(0, uc_pilot_award_before_cap -
  monthly_limit)`` over the UC award only (it is a single-benefit UC household
  model). On single-no-child units the two bases coincide (``bch_s`` = 0, so
  ``il_bencap`` = ``bsauc_s``) and the reduction matches to a small
  weekly-rounding residual — the shape this grid compares. A unit with children
  would diverge by exactly the monthly child benefit UKMOD adds to the base; that
  is a known Axiom cap-base scope boundary (the UC-only pilot does not add non-UC
  welfare to the reg-81 excess), documented on the ``bcap_uk`` conformance row and
  left out of the grid rather than shipped as a failing case, because it exposes
  only that scope limit, not a defect in the reg-80A/81 reduction the pilot does
  encode.

- The regulation-80A relevant amount is UKMOD's cap limit. UKMOD stores its cap
  constants weekly and converts weekly * 52 / 12 to the monthly limit; the pilot
  divides the annual regulation-80A limit by 12. These agree to the penny on the
  couple-with-children national limit (£22,020 / 12 = £1,835.00) and differ by a
  ≤ £0.17/month convention residual on the single-no-child limits (£14,753 / 12 =
  £1,229.42 versus UKMOD's £1,229.58; London £16,967 / 12 = £1,413.92 versus
  £1,413.75). An absolute tolerance of £1 absorbs that residual on the clean
  cases; it is far below the child-benefit-base gap.

- Greater London raises the cap: UKMOD's London region code is ``drgn1=8``
  (verified: switching a capped couple-with-children household to ``drgn1=8``
  lowered ``brduc_s`` by £275.42/month, the £3,306/year London-uplift on the
  couple limit ÷ 12). London cases set ``drgn1=8`` and the pilot input
  ``uc_pilot_resident_in_greater_london`` true.

- The earnings exemption applies: a claimant earning above the cap-exemption
  threshold is not capped. Verified: a single renter with £12,000/year earnings
  returns ``brduc_s`` 0 (and here ``bsauc_s`` 0, tapered out). The pilot's
  ``uc_pilot_exempt_from_benefit_cap`` input carries this exemption; the earnings
  case sets it true so both engines return a nil reduction.

- The take-up correction is requested off (``BTA_uk`` / ``random_uk``) so the
  intent to compare the statutory reduction is explicit; the reduction itself is
  a deterministic cap computation, not a take-up draw.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity


UK_SCOPE = {"type": "country", "geoid": "UK"}
UK_BCAP_METADATA = {
    "locale": "UK",
    "scope": UK_SCOPE,
    "axiom_entity": "Family",
    "axiom_entity_id": "benefit_unit",
}

# The composed UC pilot pipeline (rulespec-uk). Its benefit-cap reduction output
# is ``uc_pilot_benefit_cap_reduction`` and its Family-level monthly inputs are
# supplied as ``<module>#input.<name>``.
UC_MODULE = "uk:policies/universal_credit_composed_award_pipeline"

# UKMOD applies the benefit cap on the monthly UC assessment period; the composed
# pilot is effective from 2026-04-01 for periods commencing on/after 6 April 2026,
# so the cases run in the April 2026 assessment period. UKMOD UK_2026 uses the
# same frozen 2026-27 cap constants.
UK_BCAP_PERIOD = "2026-04"

# EUROMOD tenure codes (``amrtn``): owner, social renter.
_AMRTN_OWNER = 1
_AMRTN_SOCIAL_RENTER = 5
# EUROMOD labour-status codes (``les``): employee, child in education.
_LES_EMPLOYED = 3
_LES_CHILD = 6
# EUROMOD marital-status codes (``dms``): single, couple.
_DMS_SINGLE = 1
_DMS_COUPLE = 2
# EUROMOD dependent-child education code (``dec``); non-zero marks a dependant.
_DEC_CHILD = 2
# UKMOD demo country code (``dct``) and a working-age English region (``drgn1``).
_DCT = 15
_DRGN_ENGLAND = 2
# UKMOD's Greater-London region code (verified: the £-uplift branch of the cap).
_DRGN_LONDON = 8

# UKMOD's take-up correction; requested off so the compared surface is the
# deterministic statutory reduction.
_TAKEUP_OVERRIDES = (("BTA_uk", False), ("random_uk", False))

# 2026-27 income tax and Class 1 employee-NIC parameters (frozen from 2025-26),
# used only to net the head's earnings to the UC taper base for the earnings-
# exempt case, matching the ``uk_universal_credit`` suite convention.
_INCOME_TAX_PERSONAL_ALLOWANCE = 12_570.0
_INCOME_TAX_BASIC_RATE_LIMIT = 37_700.0
_INCOME_TAX_BASIC_RATE = 0.20
_INCOME_TAX_HIGHER_RATE = 0.40
_NIC_PRIMARY_THRESHOLD = 12_570.0
_NIC_UPPER_EARNINGS_LIMIT = 50_270.0
_NIC_MAIN_RATE = 0.08
_NIC_ADDITIONAL_RATE = 0.02


def uk_benefit_cap_cases() -> list[Case]:
    """Household benefit-cap reduction cases for the UKMOD UK_2026 oracle.

    The grid is single-no-child and nil-reduction cases, the shapes where UKMOD's
    cap base ``il_bencap`` equals the UC award ``bsauc_s`` (child benefit is nil)
    so the reg-80A/81 reduction is compared like-for-like against the single-
    benefit UC pilot. With-children cases are deliberately excluded: UKMOD's cap
    base sums child benefit (and other welfare) that the UC-only pilot base omits,
    a known Axiom cap-base scope boundary documented on the ``bcap_uk`` conformance
    row rather than compared here (comparing it would surface only that scope
    limit, not an encoding defect in the reg-80A/81 reduction itself).
    """

    return [
        *_single_no_child_cases(),
        *_exemption_and_below_cap_cases(),
    ]


# --- Case families ---------------------------------------------------------


def _single_no_child_cases() -> list[Case]:
    """Single claimant, no children, social rent crossing the single cap.

    The single-no-child branch (``$BcapUCnokid``) is the clean parity shape:
    UKMOD's cap base ``il_bencap`` equals ``bsauc_s`` (no child benefit), so the
    reduction matches the UC-only pilot base to a ≤ £0.17/month weekly-rounding
    residual. The £600 rent case sits below the cap (nil reduction); £900/£1,100/
    £1,300 cross it. A London £1,300 case exercises the higher London limit.
    """

    return [
        _bcap_case(
            "uk-bcap-single-rent600",
            adults=1,
            children=0,
            monthly_rent=600.0,
        ),
        _bcap_case(
            "uk-bcap-single-rent900",
            adults=1,
            children=0,
            monthly_rent=900.0,
        ),
        _bcap_case(
            "uk-bcap-single-rent1100",
            adults=1,
            children=0,
            monthly_rent=1_100.0,
        ),
        _bcap_case(
            "uk-bcap-single-rent1300",
            adults=1,
            children=0,
            monthly_rent=1_300.0,
        ),
        _bcap_case(
            "uk-bcap-single-rent1300-london",
            adults=1,
            children=0,
            monthly_rent=1_300.0,
            london=True,
        ),
    ]


def _exemption_and_below_cap_cases() -> list[Case]:
    """Earnings-exempt and below-cap cases — both engines return a nil reduction.

    The earnings-exempt single renter earns above the cap-exemption threshold, so
    UKMOD applies no cap and the pilot's ``uc_pilot_exempt_from_benefit_cap`` is
    set true, so both engines return a nil reduction. The couple-no-child
    high-rent case has a UC award above the couple limit but matches no UKMOD
    UC-cap branch (``i_bcap_AmtCap`` covers only couple/lone-parent-with-child and
    single-no-child), so UKMOD returns a nil reduction; the pilot is told this
    unit is not capped (a documented UKMOD structural exclusion), so both engines
    agree at nil.
    """

    return [
        _bcap_case(
            "uk-bcap-single-rent1300-earn12000-exempt",
            adults=1,
            children=0,
            monthly_rent=1_300.0,
            head_annual_earnings=12_000.0,
            earnings_exempt=True,
        ),
        _bcap_case(
            "uk-bcap-couple-no-child-rent1500-uncapped",
            adults=2,
            children=0,
            monthly_rent=1_500.0,
            uc_cap_branch_absent=True,
        ),
    ]


# --- Case + row construction ----------------------------------------------


def _bcap_case(
    case_id: str,
    *,
    adults: int,
    children: int,
    monthly_rent: float,
    london: bool = False,
    head_annual_earnings: float = 0.0,
    earnings_exempt: bool = False,
    uc_cap_branch_absent: bool = False,
) -> Case:
    region = _DRGN_LONDON if london else _DRGN_ENGLAND
    rows = _euromod_household_rows(
        adults=adults,
        children=children,
        monthly_rent=monthly_rent,
        head_annual_earnings=head_annual_earnings,
        region=region,
    )
    entities = _entities(
        adults=adults, children=children, head_annual_earnings=head_annual_earnings
    )
    axiom_inputs = _axiom_pipeline_inputs(
        adults=adults,
        children=children,
        monthly_rent=monthly_rent,
        head_annual_earnings=head_annual_earnings,
        london=london,
        exempt=earnings_exempt or uc_cap_branch_absent,
    )
    return Case(
        case_id=case_id,
        period=UK_BCAP_PERIOD,
        facts={
            Concepts.LIVING_RENTING: True,
            Concepts.RENT_PAID: monthly_rent * 12.0,
        },
        metadata={
            **UK_BCAP_METADATA,
            "scenario": "household-benefit-cap",
            "adults": adults,
            "children": children,
            "monthly_rent": monthly_rent,
            "london": london,
            "head_annual_earnings": head_annual_earnings,
            "earnings_exempt": earnings_exempt,
            "uc_cap_branch_absent": uc_cap_branch_absent,
            "axiom_inputs": axiom_inputs,
            "euromod_inputs": rows,
            "euromod_policy_switch_overrides": [
                list(pair) for pair in _TAKEUP_OVERRIDES
            ],
        },
        entities=entities,
        outputs=(Concepts.UK_HOUSEHOLD_BENEFIT_CAP_UC_REDUCTION,),
    )


def _pipeline_input(name: str) -> str:
    return f"{UC_MODULE}#input.{name}"


def _net_monthly_earnings(annual_gross: float) -> float:
    """Gross annual employment income net of income tax and employee NIC, monthly.

    Universal Credit tapers net earnings, so this is the taper base the composed
    pipeline consumes (matching ``uk_universal_credit``)."""

    if annual_gross <= 0:
        return 0.0
    taxable = max(0.0, annual_gross - _INCOME_TAX_PERSONAL_ALLOWANCE)
    income_tax = (
        min(taxable, _INCOME_TAX_BASIC_RATE_LIMIT) * _INCOME_TAX_BASIC_RATE
        + max(0.0, taxable - _INCOME_TAX_BASIC_RATE_LIMIT) * _INCOME_TAX_HIGHER_RATE
    )
    nic = (
        max(0.0, min(annual_gross, _NIC_UPPER_EARNINGS_LIMIT) - _NIC_PRIMARY_THRESHOLD)
        * _NIC_MAIN_RATE
        + max(0.0, annual_gross - _NIC_UPPER_EARNINGS_LIMIT) * _NIC_ADDITIONAL_RATE
    )
    return (annual_gross - income_tax - nic) / 12.0


def _axiom_pipeline_inputs(
    *,
    adults: int,
    children: int,
    monthly_rent: float,
    head_annual_earnings: float,
    london: bool,
    exempt: bool,
) -> dict[str, float | int | bool]:
    """Map the household to the composed-pipeline inputs for the cap reduction.

    The disability, carer, childcare, non-dependant, unearned-income, and capital
    inputs are held at zero/false so the compared reduction isolates the
    standard-allowance + child + housing maximum amount against the cap. All
    adults are 25-or-over. ``uc_pilot_exempt_from_benefit_cap`` is set true for
    the earnings-exempt case and for the couple-no-child unit that UKMOD's UC-cap
    branches do not cover, so both engines return a nil reduction there.
    """

    return {
        _pipeline_input("uc_pilot_is_couple"): adults > 1,
        _pipeline_input("uc_pilot_either_aged_25_or_over"): True,
        _pipeline_input("uc_pilot_number_of_responsible_children"): children,
        _pipeline_input("uc_pilot_number_of_disabled_children_lower_rate"): 0,
        _pipeline_input("uc_pilot_number_of_disabled_children_higher_rate"): 0,
        _pipeline_input("uc_pilot_has_lcwra"): False,
        _pipeline_input("uc_pilot_number_of_carer_elements"): 0,
        _pipeline_input("uc_pilot_number_of_children_in_childcare"): 0,
        _pipeline_input("uc_pilot_childcare_charges_monthly"): 0.0,
        _pipeline_input("uc_pilot_rent_monthly"): monthly_rent,
        _pipeline_input("uc_pilot_number_of_non_dependants"): 0,
        _pipeline_input("uc_pilot_capital"): 0.0,
        _pipeline_input("uc_pilot_earned_income_monthly"): (
            _net_monthly_earnings(head_annual_earnings)
        ),
        _pipeline_input("uc_pilot_unearned_income_monthly"): 0.0,
        _pipeline_input("uc_pilot_resident_in_greater_london"): london,
        _pipeline_input("uc_pilot_exempt_from_benefit_cap"): exempt,
        # None of these cases are in gainful self-employment, so the minimum-
        # income floor does not apply and its notional tax/NI deduction is nil.
        _pipeline_input("uc_pilot_is_gainfully_self_employed"): False,
        _pipeline_input(
            "uc_pilot_minimum_income_floor_notional_deduction_monthly"
        ): 0.0,
    }


def _entities(
    *, adults: int, children: int, head_annual_earnings: float
) -> tuple[Entity, ...]:
    """Concept-keyed entities mirroring the explicit UKMOD rows."""

    people: list[Entity] = [
        Entity(
            entity_id="head",
            kind="person",
            facts={
                Concepts.PERSON_AGE: 35,
                Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                Concepts.YEARLY_EARNED_INCOME: head_annual_earnings,
            },
        )
    ]
    if adults > 1:
        people.append(
            Entity(
                entity_id="partner",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 34,
                    Concepts.HOUSEHOLD_RELATION: "Spouse",
                    Concepts.YEARLY_EARNED_INCOME: 0.0,
                },
            )
        )
    for index in range(children):
        people.append(
            Entity(
                entity_id=f"child{index + 1}",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: _child_age(index),
                    Concepts.HOUSEHOLD_RELATION: "Child",
                },
            )
        )
    return tuple(people)


def _euromod_household_rows(
    *,
    adults: int,
    children: int,
    monthly_rent: float,
    head_annual_earnings: float,
    region: int,
) -> list[dict[str, float | int]]:
    head_id = 101
    partner_id = 102 if adults > 1 else 0
    rows: list[dict[str, float | int]] = [
        _adult_row(
            idperson=head_id,
            age=35,
            gender=1,
            is_head=True,
            partner_id=partner_id,
            couple=adults > 1,
            monthly_rent=monthly_rent,
            annual_earnings=head_annual_earnings,
            region=region,
        )
    ]
    if adults > 1:
        rows.append(
            _adult_row(
                idperson=partner_id,
                age=34,
                gender=0,
                is_head=False,
                partner_id=head_id,
                couple=True,
                monthly_rent=0.0,
                annual_earnings=0.0,
                region=region,
            )
        )
    for index in range(children):
        rows.append(
            _child_row(
                idperson=103 + index,
                age=_child_age(index),
                mother_id=head_id,
                region=region,
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
    region: int,
) -> dict[str, float | int]:
    employed = annual_earnings > 0
    return {
        "idhh": 1,
        "idperson": idperson,
        "idpartner": partner_id,
        "idmother": 0,
        "idfather": 0,
        "idmotherbio": 0,
        "idfatherbio": 0,
        "drgn1": region,
        "dct": _DCT,
        "dwt": 1_000.0,
        "dag": age,
        "dgn": gender,
        "dms": _DMS_COUPLE if couple else _DMS_SINGLE,
        "dhr": 1 if is_head else 0,
        "dec": 0,
        "ddi": 0,
        "les": _LES_EMPLOYED if employed else 0,
        "lhw": 40 if employed else 0,
        "loc": 5,
        "amrtn": _AMRTN_SOCIAL_RENTER,
        "yem": annual_earnings / 12.0,
        "yse": 0.0,
        "yiy": 0.0,
        "poa": 0.0,
        "xhcrt": monthly_rent,
        "afc": 0.0,
    }


def _child_row(
    *, idperson: int, age: int, mother_id: int, region: int
) -> dict[str, float | int]:
    return {
        "idhh": 1,
        "idperson": idperson,
        "idpartner": 0,
        "idmother": mother_id,
        "idfather": 0,
        "idmotherbio": mother_id,
        "idfatherbio": 0,
        "drgn1": region,
        "dct": _DCT,
        "dwt": 1_000.0,
        "dag": age,
        "dgn": 1,
        "dms": _DMS_SINGLE,
        "dhr": 0,
        "dec": _DEC_CHILD,
        "ddi": 0,
        "les": _LES_CHILD,
        "lhw": 0,
        "loc": 5,
        "amrtn": _AMRTN_SOCIAL_RENTER,
        "yem": 0.0,
        "yse": 0.0,
        "yiy": 0.0,
        "poa": 0.0,
        "xhcrt": 0.0,
        "afc": 0.0,
    }


def _child_age(index: int) -> int:
    """Descending child ages so the eldest anchors the first-child element."""

    return (10, 7, 4, 2)[index] if index < 4 else 1
