"""Household Universal Credit suite for the UKMOD ``bsauc_s`` oracle.

Where ``uk_worker`` runs single-employee tax/NIC cases, Universal Credit is a
household means-tested transfer: its award composes a standard allowance, child
and disability elements, a housing-cost element, a work allowance, an earnings
taper, and a capital/tariff-income test over the whole benefit unit. This suite
builds a hypothetical-household grid — single/couple crossed with 0-3 children,
owner/renter, an earnings sweep across the taper, and capital cases straddling
the £6,000 and £16,000 thresholds — and runs it against CeMPA's UKMOD UC output
``bsauc_s`` on the registration-free public model (UKMOD_PUBLIC_B2026.03, system
UK_2026, dataset training_data).

Household composition is expressed as explicit UKMOD ``euromod_inputs`` rows so
the benefit-unit linkage the award depends on is exact: the responsible adult
carries ``dhr`` and the household housing costs (``xhcrt``) and financial
capital (``afc``); partners cross-reference through ``idpartner`` and share
``dms``; dependent children link to the mother through ``idmother`` and carry
the in-education labour status (``les``) and dependent-child education code
(``dec``). Monetary case facts are annual (the Axiom concept convention);
UKMOD's demo dataset is monthly, so income and housing-cost inputs are divided
by twelve while the capital stock (``afc``) is a level. The award output is
monthly and the adapter annualizes it.

Verified UKMOD conventions (executed against UKMOD_PUBLIC_B2026.03, UK_2026):
- The UC output column is ``bsauc_s`` (UKMOD policy ``bsauc_uk``, "BEN:
  Universal Credit"). It is a monthly assessment-period amount and the Axiom
  award is also monthly, so the adapter keeps ``bsauc_s`` un-annualized (it is
  in ``NON_ANNUALIZED_OUTPUTS``) and the comparison is monthly-to-monthly.
- ``bsauc_s`` embeds UKMOD's benefit take-up correction (policies ``BTA_uk`` and
  ``random_uk`` seed a per-benefit-unit take-up draw, gated in ``bsauc_uk`` on
  ``i_rand_tu``). For hypothetical households the draw can mark a benefit unit
  as a non-taker and return a zero award that is not the statutory entitlement.
  This is a EUROMOD-platform modelling behaviour, not an Axiom encoding gap; it
  is recorded in ``axiom_oracles/data/euromod_issues.json``
  (``ukmod-uc-bsauc-takeup-correction``) and dispositioned as an upstream
  engine gap. Expected outputs are only ever the executed ``bsauc_s`` values
  from the regenerate run, so the recorded numbers stay self-consistent with
  whatever take-up the model applies to each case.
- Below the benefit cap the statutory award matches to the penny: single
  424.90/month, couple 666.97, couple + private-rent 750 = 1,416.97, single +
  one child + rent 750 = 1,526.78 (first child element 351.88, subsequent
  303.94). UKMOD does not apply the regulation 80A benefit cap to these
  hypothetical benefit units, so larger awards diverge from the capped Axiom
  award; that divergence is dispositioned as an upstream engine gap.
- Universal Credit tapers net earned income; UKMOD nets tax and NIC before the
  taper, so the earner cases supply net-of-tax-and-NIC monthly earnings to the
  pipeline (see ``_net_monthly_earnings``).
- The financial-capital variable is ``afc`` ("value of financial capital"); the
  capital upper limit is £16,000 (``$UCcaplimsing``/``$Uccaplimcoup``) and the
  tariff income above £6,000 is £4.35 per month per £250 (verified: £6,250 of
  capital reduces the monthly award by £4.35). At exactly £16,000 UKMOD still
  pays a reduced award (its limit is a strict ``> 16,000``) while the Axiom
  pipeline treats ``>= 16,000`` as nil; that boundary case is dispositioned.
- Renting attaches the UC housing-cost element through the social-renter tenure
  code ``amrtn=5`` (the private-renter path runs through a Local Housing
  Allowance rate lookup the demo data does not exercise directly); owner cases
  use ``amrtn=1`` and receive no housing element.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity


UK_SCOPE = {"type": "country", "geoid": "UK"}
UK_UC_METADATA = {
    "locale": "UK",
    "scope": UK_SCOPE,
    "axiom_entity": "Family",
    "axiom_entity_id": "benefit_unit",
}

# The merged composed UC pilot pipeline (rulespec-uk#72). Its award output is
# ``uc_pilot_award_amount`` and its Family-level monthly inputs are supplied as
# ``<module>#input.<name>``.
UC_MODULE = "uk:policies/universal_credit_composed_award_pipeline"

# UKMOD applies UC on a monthly assessment period; the composed pilot pipeline
# (rulespec-uk#72) is effective from 2026-04-01 for assessment periods
# commencing on/after 6 April 2026, so the cases run in the April 2026
# assessment period. UKMOD UK_2026 uses the same frozen 2026-27 UC rates.
UK_UC_PERIOD = "2026-04"

# EUROMOD tenure codes (``amrtn``).
_AMRTN_OWNER = 1
_AMRTN_SOCIAL_RENTER = 5
# EUROMOD labour-status codes (``les``): employee, child in education.
_LES_EMPLOYED = 3
_LES_CHILD = 6
# EUROMOD marital-status codes (``dms``).
_DMS_SINGLE = 1
_DMS_COUPLE = 2
# EUROMOD dependent-child education code (``dec``); non-zero marks a dependant.
_DEC_CHILD = 2
# UKMOD demo country code (``dct``) and a working-age region (``drgn1``).
_DCT = 15
_DRGN = 2

# UKMOD's take-up correction; the suite requests these overrides so the intent
# to compare the statutory entitlement is explicit and recorded on every case.
_TAKEUP_OVERRIDES = (("BTA_uk", False), ("random_uk", False))


def uk_universal_credit_cases() -> list[Case]:
    """Household Universal Credit cases for the UKMOD UK_2026 oracle."""

    return [
        *_composition_cases(),
        *_earnings_sweep_cases(),
        *_capital_cases(),
    ]


# --- Case families ---------------------------------------------------------


def _composition_cases() -> list[Case]:
    """Single/couple x 0-3 children x owner/renter, no earnings.

    The three-child renter case straddles the two-child limit: the third child
    (born after the April 2017 policy start, modelled here by age) does not add
    a child element, so the couple three-child award exceeds the two-child
    award by the housing difference only, not by a third child element.
    """

    return [
        _uc_case(
            "uk-uc-single-owner",
            renting=False,
            adults=1,
            children=0,
        ),
        _uc_case(
            "uk-uc-single-renter",
            renting=True,
            monthly_rent=600.0,
            adults=1,
            children=0,
        ),
        _uc_case(
            "uk-uc-couple-owner",
            renting=False,
            adults=2,
            children=0,
        ),
        _uc_case(
            "uk-uc-couple-renter",
            renting=True,
            monthly_rent=750.0,
            adults=2,
            children=0,
        ),
        _uc_case(
            "uk-uc-single-1child-renter",
            renting=True,
            monthly_rent=750.0,
            adults=1,
            children=1,
        ),
        _uc_case(
            "uk-uc-single-2child-renter",
            renting=True,
            monthly_rent=850.0,
            adults=1,
            children=2,
        ),
        _uc_case(
            "uk-uc-couple-2child-owner",
            renting=False,
            adults=2,
            children=2,
        ),
        _uc_case(
            "uk-uc-couple-2child-renter",
            renting=True,
            monthly_rent=900.0,
            adults=2,
            children=2,
        ),
        _uc_case(
            "uk-uc-couple-3child-renter",
            renting=True,
            monthly_rent=1_000.0,
            adults=2,
            children=3,
        ),
    ]


def _earnings_sweep_cases() -> list[Case]:
    """Couple + two children, social renter, earnings crossing the taper.

    The award falls as earnings rise past the work allowance and through the
    55% taper. UKMOD's take-up correction can zero individual points on this
    sweep for hypothetical benefit units; those points are classified against
    the recorded UKMOD output as take-up artefacts, not encoding mismatches.
    """

    grid = (0.0, 15_000.0, 30_000.0, 45_000.0)
    return [
        _uc_case(
            f"uk-uc-couple-2child-renter-earn{int(annual)}",
            renting=True,
            monthly_rent=900.0,
            adults=2,
            children=2,
            head_annual_earnings=annual,
        )
        for annual in grid
    ]


def _capital_cases() -> list[Case]:
    """Single owner, capital straddling the £6,000 floor and £16,000 limit.

    Below £6,000 there is no tariff income; from £6,000 to £16,000 tariff
    income of £4.35 per month per £250 reduces the award; above £16,000 the
    capital limit ends entitlement.
    """

    grid = (0.0, 6_000.0, 6_250.0, 10_000.0, 16_000.0, 20_000.0)
    return [
        _uc_case(
            f"uk-uc-single-owner-capital{int(capital)}",
            renting=False,
            adults=1,
            children=0,
            capital=capital,
        )
        for capital in grid
    ]


# --- Case + row construction ----------------------------------------------


def _uc_case(
    case_id: str,
    *,
    renting: bool,
    adults: int,
    children: int,
    monthly_rent: float = 0.0,
    head_annual_earnings: float = 0.0,
    capital: float = 0.0,
) -> Case:
    tenure = _AMRTN_SOCIAL_RENTER if renting else _AMRTN_OWNER
    rows = _euromod_household_rows(
        adults=adults,
        children=children,
        tenure=tenure,
        monthly_rent=monthly_rent,
        head_annual_earnings=head_annual_earnings,
        capital=capital,
    )
    entities = _entities(adults=adults, children=children, head_annual_earnings=head_annual_earnings)
    axiom_inputs = _axiom_pipeline_inputs(
        adults=adults,
        children=children,
        renting=renting,
        monthly_rent=monthly_rent,
        head_annual_earnings=head_annual_earnings,
        capital=capital,
    )
    return Case(
        case_id=case_id,
        period=UK_UC_PERIOD,
        facts={
            (Concepts.LIVING_RENTING if renting else Concepts.LIVING_OWNER): True,
            Concepts.RENT_PAID: monthly_rent * 12.0,
            Concepts.CASH_ON_HAND: capital,
        },
        metadata={
            **UK_UC_METADATA,
            "scenario": "household-universal-credit",
            "adults": adults,
            "children": children,
            "tenure": "renter" if renting else "owner",
            "monthly_rent": monthly_rent,
            "head_annual_earnings": head_annual_earnings,
            "capital": capital,
            "axiom_inputs": axiom_inputs,
            "euromod_inputs": rows,
            "euromod_policy_switch_overrides": [list(pair) for pair in _TAKEUP_OVERRIDES],
        },
        entities=entities,
        outputs=(Concepts.UK_HOUSEHOLD_UNIVERSAL_CREDIT_AWARD,),
    )


def _pipeline_input(name: str) -> str:
    return f"{UC_MODULE}#input.{name}"


# 2026-27 UK income-tax and Class 1 employee-NIC parameters (frozen from
# 2025-26), used only to net the head's earnings to the UC taper base. These
# match the values UKMOD applies through tin_uk and tscee_tscse_uk.
_INCOME_TAX_PERSONAL_ALLOWANCE = 12_570.0
_INCOME_TAX_BASIC_RATE_LIMIT = 37_700.0
_INCOME_TAX_BASIC_RATE = 0.20
_INCOME_TAX_HIGHER_RATE = 0.40
_NIC_PRIMARY_THRESHOLD = 12_570.0
_NIC_UPPER_EARNINGS_LIMIT = 50_270.0
_NIC_MAIN_RATE = 0.08
_NIC_ADDITIONAL_RATE = 0.02


def _net_monthly_earnings(annual_gross: float) -> float:
    """Gross annual employment income net of income tax and employee NIC,
    expressed monthly. Universal Credit tapers net earnings, so this is the
    taper base the composed pipeline consumes."""

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
    renting: bool,
    monthly_rent: float,
    head_annual_earnings: float,
    capital: float,
) -> dict[str, float | int | bool]:
    """Map the household composition to the 16 composed-pipeline inputs.

    The composed UC pilot (rulespec-uk#72) is Family-level and monthly: rent
    and earned income are monthly amounts, capital is a stock, and the element
    counts are benefit-unit totals. This grid exercises the standard-allowance,
    child, housing, work-allowance/taper, and capital/tariff paths; the
    disability, carer, childcare, non-dependant, unearned-income, London, and
    benefit-cap-exemption inputs are held at zero/false so the compared award
    isolates those exercised elements. All adults here are 34-35, so the
    25-or-over standard-allowance branch always applies.

    Universal Credit tapers *net* earned income (earnings after income tax and
    Class 1 employee NIC), which is what UKMOD does through its own tax/NIC
    policies before the UC taper. The composed pilot takes the already-netted
    ``uc_pilot_earned_income_monthly`` (the interface documents it as combined
    earned income), so the head's gross annual earnings are reduced by 2026-27
    income tax and employee NIC before being supplied monthly, matching the
    engine's net-earnings taper base.
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
        _pipeline_input("uc_pilot_rent_monthly"): monthly_rent if renting else 0.0,
        _pipeline_input("uc_pilot_number_of_non_dependants"): 0,
        _pipeline_input("uc_pilot_capital"): capital,
        _pipeline_input("uc_pilot_earned_income_monthly"): (
            _net_monthly_earnings(head_annual_earnings)
        ),
        _pipeline_input("uc_pilot_unearned_income_monthly"): 0.0,
        _pipeline_input("uc_pilot_resident_in_greater_london"): False,
        _pipeline_input("uc_pilot_exempt_from_benefit_cap"): False,
    }


def _entities(
    *, adults: int, children: int, head_annual_earnings: float
) -> tuple[Entity, ...]:
    """Concept-keyed entities mirroring the explicit UKMOD rows.

    The suite drives UKMOD from the explicit ``euromod_inputs`` rows; these
    entities describe the same household in Axiom concepts so the rulespec-uk
    side of the comparison projects the identical benefit unit.
    """

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
    tenure: int,
    monthly_rent: float,
    head_annual_earnings: float,
    capital: float,
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
            tenure=tenure,
            monthly_rent=monthly_rent,
            capital=capital,
            annual_earnings=head_annual_earnings,
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
                tenure=tenure,
                monthly_rent=0.0,
                capital=0.0,
                annual_earnings=0.0,
            )
        )
    for index in range(children):
        rows.append(
            _child_row(
                idperson=103 + index,
                age=_child_age(index),
                mother_id=head_id,
                tenure=tenure,
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
    tenure: int,
    monthly_rent: float,
    capital: float,
    annual_earnings: float,
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
        "drgn1": _DRGN,
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
        "amrtn": tenure,
        "yem": annual_earnings / 12.0,
        "yse": 0.0,
        "yiy": 0.0,
        "poa": 0.0,
        "xhcrt": monthly_rent,
        "afc": capital,
    }


def _child_row(
    *, idperson: int, age: int, mother_id: int, tenure: int
) -> dict[str, float | int]:
    return {
        "idhh": 1,
        "idperson": idperson,
        "idpartner": 0,
        "idmother": mother_id,
        "idfather": 0,
        "idmotherbio": mother_id,
        "idfatherbio": 0,
        "drgn1": _DRGN,
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
        "amrtn": tenure,
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
