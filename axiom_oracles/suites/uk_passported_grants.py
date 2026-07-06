"""Passported-grant suites for the UKMOD ``bmamt_s`` (Sure Start Maternity
Grant), ``bmamt01_s`` (Healthy Start), and ``bmascmt01_s`` (Best Start Foods)
oracles.

Where ``uk_universal_credit`` compares the Universal Credit award itself and
``uk_statutory_pay`` the earnings-related maternity/paternity pay, this suite
covers the three deterministic passported grants that gate on a qualifying
means-tested benefit being in payment. Each grant's UKMOD ``Elig_Cond`` requires
a qualifying award (``bsa_s>0 | bunmt_s>0 | boamt_s>0 | bsauc_s>0 ...``); the
cases here are zero-earnings lone-parent-plus-newborn households that passport
onto Universal Credit (``bsauc_s>0``), so the grant condition is satisfied
through UC receipt. Verified live against UKMOD_PUBLIC_B2026.03 (system UK_2026,
dataset training_data).

Passport pinning (the take-up draw)
-----------------------------------
UKMOD's Universal Credit output ``bsauc_s`` carries a STOCHASTIC per-benefit-unit
take-up draw (``i_rand_tu``, gated in ``bsauc_uk`` on the ``$ISTUNoChild`` /
``$ISTUChild`` take-up-rate constants); for a hypothetical benefit unit a
non-taking solo draw returns a zero UC award, which would in turn switch the
passport off and zero the grant (documented in
``axiom_oracles/data/euromod_issues.json`` as
``ukmod-uc-bsauc-takeup-correction``). To make the passporting benefit
deterministically in payment, the comparison configs pin the UC take-up-rate
constants ``$ISTUNoChild`` and ``$ISTUChild`` to 1.0 through
``euromod_constant_overrides`` (the DefConst-overlay mechanism from
axiom-oracles#168: the adapter patches the constant values into the system XML
on the model overlay, since the connector's ``constantsToOverwrite`` kwarg
silently ignores DefConst constants). With take-up pinned on, ``bsauc_s>0`` for
every case and the grants compute their statutory passported amounts.

Unlike the excluded Best Start Grant (``bmascmt_uk``), none of the three grants
here consumes ``i_rand_tu`` itself, so pinning the UC take-up is sufficient — the
grant amount, once passported, is a deterministic per-household statutory result.

Verified UKMOD conventions (executed against UKMOD_PUBLIC_B2026.03, UK_2026,
take-up pinned):

- ``bmamt_s`` (Sure Start Maternity Grant, rest of UK) is the £500 lump sum
  (``$BSurMaG`` 500#y) for a passported family with a child under one and no
  other dependent children. The adapter reports it as the annual £500.00.
- ``bmamt01_s`` (Healthy Start, rest of UK) is the weekly Healthy Start voucher
  value (``$HSFood``: £4.25/week, doubled to £8.50/week for a child under one),
  which UKMOD annualises over its 365/7 calendar-week convention. For a newborn
  the annual amount is £8.50 x 365/7 = £443.21.
- ``bmascmt01_s`` (Best Start Foods, Scotland, ``drgn1=12``) is the weekly Best
  Start Foods value (``$BScBSF0`` £11.20/week under one, ``$BScBSF1to2``
  £5.60/week ages one to three), annualised the same way. For a newborn the
  annual amount is £11.20 x 365/7 = £584.00.

Each rulespec-uk pilot annualises the same weekly rate over 52 benefit weeks,
about 0.27% below the UKMOD 365/7 figure; the concept mappings carry a 0.3%
relative tolerance so both sides recover the same statutory weekly rate. The
Sure Start Maternity Grant is an already-annual lump sum, so it matches to the
penny.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity


UK_SCOPE = {"type": "country", "geoid": "UK"}

# UKMOD demo country code (``dct``); rest-of-UK and Scotland working-age regions
# (``drgn1``). Best Start Foods requires Scottish residence (drgn1=12).
_DCT = 15
_DRGN_REST_OF_UK = 2
_DRGN_SCOTLAND = 12
# EUROMOD marital-status (``dms``) and tenure (``amrtn``) codes.
_DMS_SINGLE = 1
_AMRTN_SOCIAL_RENTER = 5
# EUROMOD dependent-child education code (``dec``); non-zero marks a dependant.
_DEC_CHILD = 2

SSMG_MODULE = (
    "uk:regulations/uksi/2005/3061/pilot_sure_start_maternity_grant_oracle_pipeline"
)
HS_MODULE = "uk:regulations/uksi/2005/3262/pilot_healthy_start_oracle_pipeline"
BSF_MODULE = "uk:regulations/ssi/2019/193/pilot_best_start_foods_oracle_pipeline"

# The composed passported-grant pilots are effective from the 2026-27 tax year
# (Best Start Foods from 2026-04-01 on the SSI 2026/170 uprating). UKMOD UK_2026
# uses the same frozen 2026-27 rates; the cases run in the April 2026 window.
UK_GRANTS_PERIOD = "2026-04"

# UKMOD's weekly-value determinations for the UK_2026 slice, supplied to the
# rulespec Healthy Start pilot so the delegated cash amount matches the oracle.
# £8.50/week for a child under one (double the £4.25 individual rate). The Best
# Start Foods rates are statutory literals encoded in the pilot, so only the
# child's age is supplied there.
_HS_WEEKLY_VALUE_UNDER_ONE = 8.50
_HS_WEEKLY_VALUE_INDIVIDUAL = 4.25

_UK_GRANTS_METADATA = {
    "locale": "UK",
    "scope": UK_SCOPE,
    "axiom_entity": "Person",
    "axiom_entity_id": "head",
}


def uk_sure_start_maternity_grant_cases() -> list[Case]:
    """Passported lone-parent-plus-newborn Sure Start Maternity Grant case."""

    return [
        _ssmg_case("uk-ssmg-passported-newborn"),
    ]


def uk_healthy_start_cases() -> list[Case]:
    """Passported Healthy Start cases (rest of UK): newborn and a 1-4 child."""

    return [
        _hs_case(
            "uk-healthy-start-passported-newborn",
            child_age=0,
            weekly_value=_HS_WEEKLY_VALUE_UNDER_ONE,
        ),
        _hs_case(
            "uk-healthy-start-passported-toddler",
            child_age=2,
            weekly_value=_HS_WEEKLY_VALUE_INDIVIDUAL,
        ),
    ]


def uk_best_start_foods_cases() -> list[Case]:
    """Passported Scottish Best Start Foods cases: newborn and a 1-3 child."""

    return [
        _bsf_case("uk-best-start-foods-passported-newborn", child_age=0),
        _bsf_case("uk-best-start-foods-passported-toddler", child_age=2),
    ]


def _ssmg_case(case_id: str) -> Case:
    return Case(
        case_id=case_id,
        period=UK_GRANTS_PERIOD,
        metadata={
            **_UK_GRANTS_METADATA,
            "scenario": "passported-lone-parent-sure-start-maternity-grant",
            "euromod_inputs": _passported_lone_parent_newborn_rows(
                drgn1=_DRGN_REST_OF_UK, child_age=0
            ),
        },
        entities=_passported_entities(child_age=0),
        outputs=(Concepts.UK_SURE_START_MATERNITY_GRANT,),
    )


def _hs_case(case_id: str, *, child_age: int, weekly_value: float) -> Case:
    return Case(
        case_id=case_id,
        period=UK_GRANTS_PERIOD,
        metadata={
            **_UK_GRANTS_METADATA,
            "scenario": "passported-healthy-start",
            "child_age": child_age,
            "axiom_inputs": {
                _hs_input("uk_hs_pilot_supplied_determined_weekly_value"): weekly_value,
            },
            "euromod_inputs": _passported_lone_parent_newborn_rows(
                drgn1=_DRGN_REST_OF_UK, child_age=child_age
            ),
        },
        entities=_passported_entities(child_age=child_age),
        outputs=(Concepts.UK_HEALTHY_START,),
    )


def _bsf_case(case_id: str, *, child_age: int) -> Case:
    return Case(
        case_id=case_id,
        period=UK_GRANTS_PERIOD,
        metadata={
            **_UK_GRANTS_METADATA,
            "scenario": "passported-best-start-foods",
            "child_age": child_age,
            "axiom_inputs": {
                _bsf_input("uk_bsf_pilot_supplied_child_age_years"): child_age,
            },
            "euromod_inputs": _passported_lone_parent_newborn_rows(
                drgn1=_DRGN_SCOTLAND, child_age=child_age
            ),
        },
        entities=_passported_entities(child_age=child_age),
        outputs=(Concepts.UK_BEST_START_FOODS,),
    )


def _passported_lone_parent_newborn_rows(
    *, drgn1: int, child_age: int
) -> list[dict[str, float | int]]:
    """A zero-earnings lone parent (the head) responsible for one child, renting.

    A single benefit unit with no earnings, no capital, and social-rented
    housing, so Universal Credit is in payment (``bsauc_s>0`` with take-up pinned
    on) and the grant passports off it. ``dmb`` 1 on a child under one drives the
    maternity months; the child's ``dag`` sets its age for the age-banded
    Healthy Start and Best Start Foods rates.
    """
    parent_id, child_id = 101, 103
    parent = {
        "idhh": 1,
        "idperson": parent_id,
        "idpartner": 0,
        "idmother": 0,
        "idfather": 0,
        "idmotherbio": 0,
        "idfatherbio": 0,
        "drgn1": drgn1,
        "dct": _DCT,
        "dwt": 1_000.0,
        "dag": 30,
        "dgn": 0,
        "dms": _DMS_SINGLE,
        "dhr": 1,
        "dec": 0,
        "ddi": 0,
        "les": 0,
        "lhw": 0,
        "loc": 5,
        "amrtn": _AMRTN_SOCIAL_RENTER,
        "yem": 0.0,
        "yse": 0.0,
        "yiy": 0.0,
        "poa": 0.0,
        "xhcrt": 600.0,
        "afc": 0.0,
        "dmb": 0,
    }
    child = {
        "idhh": 1,
        "idperson": child_id,
        "idpartner": 0,
        "idmother": parent_id,
        "idfather": 0,
        "idmotherbio": parent_id,
        "idfatherbio": 0,
        "drgn1": drgn1,
        "dct": _DCT,
        "dwt": 1_000.0,
        "dag": child_age,
        "dgn": 1,
        "dms": _DMS_SINGLE,
        "dhr": 0,
        "dec": _DEC_CHILD,
        "ddi": 0,
        "les": 0,
        "lhw": 0,
        "loc": 5,
        "amrtn": _AMRTN_SOCIAL_RENTER,
        "yem": 0.0,
        "yse": 0.0,
        "yiy": 0.0,
        "poa": 0.0,
        "xhcrt": 0.0,
        "afc": 0.0,
        "dmb": 1 if child_age < 1 else 0,
    }
    return [parent, child]


def _passported_entities(*, child_age: int) -> tuple[Entity, ...]:
    """Concept-keyed entities mirroring the passported lone-parent household."""

    return (
        Entity(
            entity_id="head",
            kind="person",
            facts={
                Concepts.PERSON_AGE: 30,
                Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                Concepts.YEARLY_EARNED_INCOME: 0.0,
            },
        ),
        Entity(
            entity_id="child1",
            kind="person",
            facts={
                Concepts.PERSON_AGE: child_age,
                Concepts.HOUSEHOLD_RELATION: "Child",
            },
        ),
    )


def _hs_input(name: str) -> str:
    return f"{HS_MODULE}#input.{name}"


def _bsf_input(name: str) -> str:
    return f"{BSF_MODULE}#input.{name}"
