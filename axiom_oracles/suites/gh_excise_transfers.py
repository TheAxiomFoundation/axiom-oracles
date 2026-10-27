"""Ghana excise and transfer oracle suites (GHAMOD).

Two suites close out the GHAMOD full-surface program's comparable rows:

``gh-excise`` compares the Act 1108 First Schedule beer excise,
``beer_excise_amount`` at under 50 per cent local raw material (47.5 per
centum of the ex-factory price), against GHAMOD ``tvl04_s``, the one
ad-valorem excise output whose rate matches the statutory table (live run
2026-10-04: 1,200 -> 570.00 and 6,000 -> 2,850.00 a year on both engines).
GHAMOD charges that rate on household beer expenditure, so each case gives
the euromod side one beer item (``x021302``) and gives Axiom the same amount
as the ex-factory value. The comparison therefore tests the 47.5% rate on an
identical base, not the retail-versus-ex-factory base definition; that
divergence is recorded in ``ghamod_issues.json``
(``ghamod-beer-excise-charged-on-household-expenditure``). Detailed COICOP
inputs such as ``x021302`` are not columns of the engine's output frame, so
the case bridges the engine's post-uprating ``ils_coicop02`` (its COICOP
division 02 expenditure list; these cases put spend on no other division 02
item, so the list holds exactly the uprated beer spend) onto the Axiom value.
The bridge carries the base, not the tax, so it cannot make the comparison
agree by construction. GHAMOD's other ad-valorem excise outputs match no Act
1108 rate (``ghamod-excise-buckets-diverge-from-act-1108-table``), and its
fuel-levy outputs diverge from the Energy Sector Levies Act 2025 schedule
(``ghamod-fuel-levies-diverge-from-esla-2025-schedule``); both have no live
cases.

``gh-transfers`` compares the Ghana School Feeding Programme grant,
``school_feeding_value_per_year`` (GH¢2.00 per child per day, 2025 Budget
paragraph 381), against GHAMOD ``bed_s``. GHAMOD pays the grant for every
weekday of the year (probed: 43.45 a month = 2.00 x 260.71 days / 12; live
run 2026-10-04: 521.43 a year on both engines). The case gives Axiom that
every-weekday calendar (365 x 5/7 days), which was inferred from GHAMOD's own
output, so it is a regression check that GHAMOD's annual value stays at
GH¢2.00 over every weekday of the year. It cannot separate a rate error from
an offsetting calendar error. The calendar is a recorded divergence from the
school year (``ghamod-school-feeding-every-weekday-of-the-year``). LEAP has no live
cases: GHAMOD pays the official bi-monthly amounts every month, exactly 2x on
every band (``ghamod-leap-pays-bimonthly-amounts-monthly``). Free SHS has
none either, because its amounts have no official basis
(``ghamod-free-shs-amounts-have-no-official-basis``). Both follow the tinta04
pattern.

License discipline as in ``gh_income_tax``: expected values are values
GHAMOD itself produced; no bundle content is committed.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .gh_income_tax import (
    EUROMOD_TO_AXIOM_INPUT_BRIDGE,
    GH_METADATA,
    GH_PERIOD,
    GH_UPRATE_2017_TO_2025,
    _gh_base_row,
)

EXCISE_MODULE = (
    "gh:statutes/act-1108/excise-duty-amendment-no2-2023/"
    "first-schedule-goods-liable-to-excise-duty"
)
FEEDING_MODULE = "gh:policies/gsfp/feeding-grant"

# GHAMOD feeds every weekday year-round (probed: bed_s = 43.45/month =
# GH¢2.00 x 260.71 days / 12). The calendar was inferred from that output, so
# giving Axiom the same 365 x 5/7 days makes the case a regression check of
# GHAMOD's annual value, not an independent test of the daily rate: a rate
# error offset by a calendar error would still match. The calendar is an
# oracle convention recorded in ghamod_issues.json; the rulespec-gh companion
# fixture uses a 190-day school year.
GHAMOD_FEEDING_DAYS_PER_YEAR = 365 * 5 / 7


def _excise_input(name: str) -> str:
    return f"{EXCISE_MODULE}#input.{name}"


def _feeding_input(name: str) -> str:
    return f"{FEEDING_MODULE}#input.{name}"


def gh_excise_cases() -> list[Case]:
    """Beer-excise cases for the GHAMOD tvl04_s oracle (the exact bucket)."""
    return [
        _beer_case("gh-excise-beer-1200", 1_200.0),
        _beer_case("gh-excise-beer-6000", 6_000.0),
    ]


def _beer_case(case_id: str, annual_spend: float) -> Case:
    value_input = _excise_input("beer_ex_factory_value")
    # Only the beer item (x021302) carries spend, so the engine's
    # post-uprating ils_coicop02 (its COICOP division 02 expenditure list)
    # equals the uprated beer spend and is bridged onto the Axiom ex-factory
    # value. xhh must be positive: GH_2025 returns zero excise for a household
    # with no recorded total expenditure (probed).
    row = _gh_base_row(1, 101)
    monthly = (annual_spend / GH_UPRATE_2017_TO_2025) / 12.0
    row.update({"dag": 40, "dhh": 1, "x021302": monthly,
                "xhh": (12_000.0 / GH_UPRATE_2017_TO_2025) / 12.0})
    return Case(
        case_id=case_id,
        period=GH_PERIOD,
        metadata={
            **GH_METADATA,
            "scenario": "single-consumer-beer-excise",
            "annual_beer_spend": annual_spend,
            "axiom_inputs": {
                value_input: annual_spend,
                _excise_input("beer_local_raw_material_share"): 0.40,
                _excise_input("malt_drink_local_raw_material_share"): 0.0,
                _excise_input("malt_drink_ex_factory_value"): 0.0,
                _excise_input("wine_ex_factory_value"): 0.0,
                _excise_input("blended_spirits_ex_factory_value"): 0.0,
                _excise_input("akpeteshie_ex_factory_value"): 0.0,
                _excise_input("fruit_juice_ex_factory_value"): 0.0,
                _excise_input(
                    "other_non_alcoholic_drinks_ex_factory_value"
                ): 0.0,
                _excise_input("cigarette_ex_factory_value_ghp"): 0.0,
                _excise_input("cigarette_sticks"): 0.0,
                _excise_input("snuff_and_negrohead_kilogrammes"): 0.0,
                _excise_input("eliquid_ex_factory_value_ghp"): 0.0,
                _excise_input("eliquid_millilitres"): 0.0,
                _excise_input("plastics_ex_factory_value"): 0.0,
            },
            "euromod_inputs": [row],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"ils_coicop02": [value_input]},
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 40,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                },
            ),
        ),
        outputs=(Concepts.GH_BEER_EXCISE_AMOUNT,),
    )


def gh_transfers_cases() -> list[Case]:
    """School-feeding cases for the GHAMOD bed_s oracle."""
    return [_feeding_case("gh-feeding-pupil")]


def _feeding_case(case_id: str) -> Case:
    days_input = _feeding_input("school_days_fed")
    head = _gh_base_row(1, 101)
    head.update({"dag": 40, "dhh": 1})
    pupil = _gh_base_row(1, 102)
    pupil.update({"dag": 8, "les": 6, "deh": 2, "dpp": 1, "dgn": 0})
    return Case(
        case_id=case_id,
        period=GH_PERIOD,
        metadata={
            **GH_METADATA,
            "scenario": "public-basic-pupil-school-feeding",
            "axiom_entity_id": "pupil",
            "axiom_inputs": {
                _feeding_input("is_public_basic_school_pupil"): True,
                days_input: GHAMOD_FEEDING_DAYS_PER_YEAR,
            },
            "euromod_inputs": [head, pupil],
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 40,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                },
            ),
            Entity(
                entity_id="pupil",
                kind="person",
                facts={Concepts.PERSON_AGE: 8},
            ),
        ),
        outputs=(Concepts.GH_SCHOOL_FEEDING_VALUE,),
    )
