"""Ghana excise and transfer oracle suites (GHAMOD).

Two suites close out the GHAMOD full-surface program's comparable rows:

``gh-excise`` compares the Act 1108 First Schedule beer excise —
``beer_excise_amount`` at under-50-per-cent local raw material (47.5 per
centum of the ex-factory value) — against GHAMOD ``tvl04_s``, the ONE
ad-valorem bucket that matches the statutory table exactly (probed live:
100/month of x021302 spend → 47.50). The other GHAMOD buckets (25% /
20% / 22.5% / 10% / 150% / 170.65%) match no Act 1108 row and are
dispositioned (``ghamod-excise-buckets-diverge-from-act-1108-table``);
the fuel-levy rows all diverge from the ESLA 2025 schedule and are
dispositioned too (``ghamod-fuel-levies-omit-road-and-energy-funds-and-
miswire-petrol-spl`` — including a petrol row that applies the ESRL
constant where the model defines a separate SPL constant).

``gh-transfers`` compares the Ghana School Feeding Programme grant —
``school_feeding_value_per_year`` (GH¢2.00 per child per day, 2025 Budget
paragraph 381) — against GHAMOD ``bed_s``. GHAMOD feeds every weekday
year-round (probed: 43.45/month = 2.00 x 260.71 days/year), so the cases
feed the same day count to both engines and the school-calendar
difference is a documented convention, not a divergence. LEAP has NO live
cases: GHAMOD pays the official bi-monthly amounts monthly — exactly 2x
on every band (``ghamod-leap-pays-bimonthly-amounts-monthly``) — and
Free SHS amounts have no official basis
(``ghamod-free-shs-amounts-have-no-official-basis``); both dispositioned
per the tinta04 pattern.

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

# GHAMOD feeds every weekday year-round: 365.0/7*5 = 260.714... days; the
# probe shows bed_s = 43.45/month = GH¢2.00 x 260.71/12. The cases feed
# the same count so both engines price the identical day base.
GHAMOD_FEEDING_DAYS_PER_YEAR = 260.714285714


def _excise_input(name: str) -> str:
    return f"{EXCISE_MODULE}#{name}"


def _feeding_input(name: str) -> str:
    return f"{FEEDING_MODULE}#{name}"


def gh_excise_cases() -> list[Case]:
    """Beer-excise cases for the GHAMOD tvl04_s oracle (the exact bucket)."""
    return [
        _beer_case("gh-excise-beer-1200", 1_200.0),
        _beer_case("gh-excise-beer-6000", 6_000.0),
    ]


def _beer_case(case_id: str, annual_spend: float) -> Case:
    value_input = _excise_input("input.beer_ex_factory_value")
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
                _excise_input("input.beer_local_raw_material_share"): 0.40,
                _excise_input("input.malt_drink_local_raw_material_share"): 0.0,
                _excise_input("input.malt_drink_ex_factory_value"): 0.0,
                _excise_input("input.wine_ex_factory_value"): 0.0,
                _excise_input("input.blended_spirits_ex_factory_value"): 0.0,
                _excise_input("input.akpeteshie_ex_factory_value"): 0.0,
                _excise_input("input.fruit_juice_ex_factory_value"): 0.0,
                _excise_input(
                    "input.other_non_alcoholic_drinks_ex_factory_value"
                ): 0.0,
                _excise_input("input.cigarette_ex_factory_value_ghp"): 0.0,
                _excise_input("input.cigarette_sticks"): 0.0,
                _excise_input("input.snuff_and_negrohead_kilogrammes"): 0.0,
                _excise_input("input.eliquid_ex_factory_value_ghp"): 0.0,
                _excise_input("input.eliquid_millilitres"): 0.0,
                _excise_input("input.plastics_ex_factory_value"): 0.0,
            },
            "euromod_inputs": [row],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"x021302": [value_input]},
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
    days_input = _feeding_input("input.school_days_fed")
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
                _feeding_input("input.is_public_basic_school_pupil"): True,
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
