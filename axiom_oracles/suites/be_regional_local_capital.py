"""Belgium regional PIT surcharge, municipal centimes, and capital-income tax
suites for the EUROMOD BE_2025 oracle.

These decompose the three post-federal income-tax stages that EUROMOD BE_2025
layers on top of the federal reduced State tax (``tinna_s``):

- ``tinrg_be`` — the regional additional tax (``tinrg_s``), levied per region on
  the reduced State tax at the region's additional-tax percentage. EUROMOD uses
  a flat 33.257% for Flanders and Wallonia and 32.591% for Brussels-Capital,
  read from the model's ``$tinreg_*`` constants; the cases supply that same
  region rate to the encoded mechanism (as the property-tax suite supplies the
  region's communal centimes) and pin the reduced-State-tax base from the
  engine's ``tinna_s`` so both sides levy the identical rate on the identical
  base.
- ``tinmu_be`` — the municipal additional centimes (``tinmu_s``), levied on the
  cumulative State-plus-regional tax (``tin_s`` after ``tinrg``) at the region's
  average communal rate (Brussels 6.2%, Flanders 7.17%, Wallonia 7.92%). The
  base is pinned from the engine's ``tinna_s`` and ``tinrg_s``.
- ``tinkt_be`` — the separately-taxed capital-income tax (``tinkt_s``), the
  taxable movable income at the article 269 general 30% rate. The taxable
  movable income is pinned from the engine's ``yiy_s``.

The region indicator EUROMOD reads is ``drgn1`` (1 Brussels, 2 Flanders,
3 Wallonia); the cases set it explicitly in ``euromod_inputs`` because the
region branches (``drgn1=1/2/3 & tinna_s>0``) leave ``tinrg_s`` and ``tinmu_s``
at zero when it is unset.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .be_worker import BE_METADATA, EUROMOD_TO_AXIOM_INPUT_BRIDGE


REGIONAL_SURCHARGE_MODULE = "be:statutes/income_tax/individual/regional_surcharge"
MOVABLE_WITHHOLDING_MODULE = "be:statutes/income_tax/movable_withholding/rates"

# EUROMOD BE_2025 region indicator (drgn1).
EUROMOD_REGION_BRUSSELS = 1
EUROMOD_REGION_FLANDERS = 2
EUROMOD_REGION_WALLONIA = 3

# EUROMOD BE_2025 regional additional-tax rates ($tinreg_BXL_Rate,
# $tinreg_Wal_Rate, and the flat $tinreg_Rate1..5 for Flanders) read from
# XMLParam/Countries/BE/BE.xml, system BE_2025.
EUROMOD_REGIONAL_RATE_BRUSSELS = 0.32591
EUROMOD_REGIONAL_RATE_FLANDERS = 0.33257
EUROMOD_REGIONAL_RATE_WALLONIA = 0.33257

# EUROMOD BE_2025 average communal rates ($tinmu_Bxl_rate, $tinmu_FL_rate,
# $tinmu_Wal_rate) read from the same model.
EUROMOD_COMMUNAL_RATE_BRUSSELS = 0.062
EUROMOD_COMMUNAL_RATE_FLANDERS = 0.0717
EUROMOD_COMMUNAL_RATE_WALLONIA = 0.0792

_REGION_LABELS = {
    EUROMOD_REGION_BRUSSELS: "brussels",
    EUROMOD_REGION_FLANDERS: "flanders",
    EUROMOD_REGION_WALLONIA: "wallonia",
}
_REGIONAL_RATES = {
    EUROMOD_REGION_BRUSSELS: EUROMOD_REGIONAL_RATE_BRUSSELS,
    EUROMOD_REGION_FLANDERS: EUROMOD_REGIONAL_RATE_FLANDERS,
    EUROMOD_REGION_WALLONIA: EUROMOD_REGIONAL_RATE_WALLONIA,
}
_COMMUNAL_RATES = {
    EUROMOD_REGION_BRUSSELS: EUROMOD_COMMUNAL_RATE_BRUSSELS,
    EUROMOD_REGION_FLANDERS: EUROMOD_COMMUNAL_RATE_FLANDERS,
    EUROMOD_REGION_WALLONIA: EUROMOD_COMMUNAL_RATE_WALLONIA,
}


def be_regional_pit_surcharge_cases() -> list[Case]:
    """Belgium regional PIT additional-tax cases for the EUROMOD BE_2025 oracle.

    One case per region, each at a mid-range single-earner income so the reduced
    State tax is comfortably positive.
    """

    return [
        _regional_surcharge_case(EUROMOD_REGION_BRUSSELS, 40_000.0),
        _regional_surcharge_case(EUROMOD_REGION_FLANDERS, 40_000.0),
        _regional_surcharge_case(EUROMOD_REGION_WALLONIA, 40_000.0),
    ]


def be_local_municipal_pit_cases() -> list[Case]:
    """Belgium municipal centimes cases for the EUROMOD BE_2025 oracle.

    One case per region so the three average communal rates are exercised, each
    on the region's own cumulative State-plus-regional base.
    """

    return [
        _local_municipal_case(EUROMOD_REGION_BRUSSELS, 40_000.0),
        _local_municipal_case(EUROMOD_REGION_FLANDERS, 40_000.0),
        _local_municipal_case(EUROMOD_REGION_WALLONIA, 40_000.0),
    ]


def be_capital_income_tax_cases() -> list[Case]:
    """Belgium separately-taxed capital-income-tax cases for EUROMOD BE_2025.

    Movable income only (no employment), so the case isolates ``tinkt_s`` at the
    article 269 general 30% rate.
    """

    return [
        _capital_income_tax_case("be-capital-income-tax-2k", 2_000.0),
        _capital_income_tax_case("be-capital-income-tax-10k", 10_000.0),
        _capital_income_tax_case("be-capital-income-tax-50k", 50_000.0),
    ]


def _regional_surcharge_case(region: int, annual_income: float) -> Case:
    label = _REGION_LABELS[region]
    reduced_state_tax_input = _regional_input(
        "belgium_pit_regional_reduced_state_tax_supplied_amount"
    )
    return Case(
        case_id=f"be-regional-pit-{label}-40k",
        period="2025",
        metadata={
            **BE_METADATA,
            "scenario": "single-worker-regional-pit-surcharge",
            "euromod_region": region,
            "yearly_earned_income": annual_income,
            "supplied_regional_rate": _REGIONAL_RATES[region],
            "axiom_inputs": {
                reduced_state_tax_input: 0.0,
                _regional_input("belgium_pit_regional_additional_tax_rate"): (
                    _REGIONAL_RATES[region]
                ),
            },
            "euromod_inputs": [_euromod_worker_input(annual_income, region)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "tinna_s": [reduced_state_tax_input],
            },
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 35,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.YEARLY_EARNED_INCOME: annual_income,
                },
            ),
        ),
        outputs=(Concepts.BE_REGIONAL_ADDITIONAL_TAX,),
    )


def _local_municipal_case(region: int, annual_income: float) -> Case:
    label = _REGION_LABELS[region]
    reduced_state_tax_input = _regional_input(
        "belgium_pit_regional_reduced_state_tax_supplied_amount"
    )
    regional_tax_input = _regional_input(
        "belgium_pit_regional_supplied_additional_tax_amount"
    )
    work_bonus_reduction_input = _regional_input(
        "belgium_pit_local_supplied_low_wage_work_bonus_reduction_amount"
    )
    childcare_reduction_input = _regional_input(
        "belgium_pit_local_supplied_childcare_reduction_amount"
    )
    return Case(
        case_id=f"be-local-pit-{label}-40k",
        period="2025",
        metadata={
            **BE_METADATA,
            "scenario": "single-worker-local-municipal-pit",
            "euromod_region": region,
            "yearly_earned_income": annual_income,
            "supplied_communal_rate": _COMMUNAL_RATES[region],
            "axiom_inputs": {
                reduced_state_tax_input: 0.0,
                regional_tax_input: 0.0,
                work_bonus_reduction_input: 0.0,
                childcare_reduction_input: 0.0,
                _regional_input("belgium_pit_local_communal_additional_tax_rate"): (
                    _COMMUNAL_RATES[region]
                ),
            },
            "euromod_inputs": [_euromod_worker_input(annual_income, region)],
            # EUROMOD BE_2025 runs tinfe_be (PIT fiscal expenditures, order 45)
            # between tinrg (44) and tinmu (46); its ``tin_s -= tintcly_s +
            # tintcch_s`` reduces the municipal base by the low-wage work-bonus
            # tax reduction and the childcare reduction. Pin both from the engine
            # so the axiom base is reduced State tax plus regional tax net of
            # those reductions, exactly as EUROMOD levies tinmu.
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "tinna_s": [reduced_state_tax_input],
                "tinrg_s": [regional_tax_input],
                "tintcly_s": [work_bonus_reduction_input],
                "tintcch_s": [childcare_reduction_input],
            },
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 35,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.YEARLY_EARNED_INCOME: annual_income,
                },
            ),
        ),
        outputs=(Concepts.BE_LOCAL_COMMUNAL_ADDITIONAL_TAX,),
    )


def _capital_income_tax_case(case_id: str, annual_movable_income: float) -> Case:
    taxable_movable_income_input = _movable_input(
        "belgium_capital_income_taxable_movable_income"
    )
    return Case(
        case_id=case_id,
        period="2025",
        metadata={
            **BE_METADATA,
            "scenario": "capital-income-separate-tax",
            "euromod_region": EUROMOD_REGION_FLANDERS,
            "yearly_movable_income": annual_movable_income,
            "axiom_inputs": {
                taxable_movable_income_input: 0.0,
            },
            "euromod_inputs": [
                _euromod_movable_income_input(annual_movable_income)
            ],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "yiy_s": [taxable_movable_income_input],
            },
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 35,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.INTEREST_INCOME: annual_movable_income,
                },
            ),
        ),
        outputs=(Concepts.BE_CAPITAL_INCOME_SEPARATE_TAX,),
    )


def _euromod_worker_input(annual_income: float, region: int) -> dict[str, float | int]:
    employed = annual_income > 0
    return {
        "idperson": 101,
        "idpartner": 0,
        "idmother": 0,
        "idfather": 0,
        "dag": 35,
        "dgn": 1,
        "dms": 1,
        "drgn1": region,
        "les": 3 if employed else 0,
        "lfs": 15 if employed else 0,
        "lhw": 38 if employed else 0,
        "liwmy": 12 if employed else 0,
        "liwwh": 120 if employed else 0,
        "loc": 5,
        "yem": annual_income / 12,
        "yemmy": 12 if employed else 0,
        "yse": 0,
        "yiy": 0,
        "poa": 0,
    }


def _euromod_movable_income_input(
    annual_movable_income: float,
) -> dict[str, float | int]:
    return {
        "idperson": 101,
        "idpartner": 0,
        "idmother": 0,
        "idfather": 0,
        "dag": 35,
        "dgn": 1,
        "dms": 1,
        "drgn1": EUROMOD_REGION_FLANDERS,
        "les": 0,
        "lfs": 0,
        "lhw": 0,
        "liwmy": 0,
        "liwwh": 0,
        "loc": 5,
        "yem": 0,
        "yemmy": 0,
        "yse": 0,
        "yiy": annual_movable_income / 12,
        "poa": 0,
    }


def _regional_input(name: str) -> str:
    return f"{REGIONAL_SURCHARGE_MODULE}#input.{name}"


def _movable_input(name: str) -> str:
    return f"{MOVABLE_WITHHOLDING_MODULE}#input.{name}"
