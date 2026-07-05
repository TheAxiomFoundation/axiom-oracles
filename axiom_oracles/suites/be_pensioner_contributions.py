from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .be_worker import BE_METADATA


NON_LABOUR_MODULE = "be:statutes/social_security/non_labour_income_contributions"


def be_pensioner_contributions_cases() -> list[Case]:
    """Belgium pensioner health/disability + solidarity contribution cases.

    Sweeps a single old-age pensioner's annual gross legal pension across the
    EUROMOD BE_2025 ``tscpe_be`` thresholds: the article 191 health-insurance
    floor (``$tscpe_lim1`` = 2037.73/m ≈ 24,452.76/yr, ``$tscpe_lim2`` =
    2112.71/m ≈ 25,352.52/yr) and the article 68 solidarity brackets (isolated
    ``$tscpe_SolDepChild_lim1..4`` = 3225.74/3325.48/3572.77/3610 per month ≈
    38,708.88 / 39,905.76 / 42,873.24 / 43,320 per year).

    Single-pensioner, old-age-only households neutralize the two structural
    scope differences between EUROMOD and the rulespec module (EUROMOD computes
    ``tscpe_s`` at the individual level and its ``il_pension`` = poa + psu only;
    the rulespec outputs are Family-level and add complementary/capital pension
    components). What remains isolates the two genuine encoding divergences the
    comparison is meant to surface: (1) EUROMOD exempts pensions below the ~2112/m
    health floor and phase-caps the 2037.73-2112.71 band, whereas rulespec article
    191 withholds 3.55% on the whole pension; (2) EUROMOD's 2025-indexed solidarity
    thresholds and the rulespec article 68 base table (indexed here at factor 1)
    are different base tables that no single index factor reconciles.
    """

    # annual gross legal pension test points, chosen to straddle each threshold
    return [
        _case("be-pensioner-tscpe-below-health-18k", 18_000.0),
        _case("be-pensioner-tscpe-health-phase-in-24k9", 24_900.0),
        _case("be-pensioner-tscpe-above-health-30k", 30_000.0),
        _case("be-pensioner-tscpe-solidarity-phase-in-39k", 39_000.0),
        _case("be-pensioner-tscpe-solidarity-mid-41k", 41_000.0),
        _case("be-pensioner-tscpe-solidarity-top-48k", 48_000.0),
    ]


def _case(case_id: str, annual_pension: float) -> Case:
    monthly_pension = annual_pension / 12.0
    axiom_inputs = {
        _input("belgium_pension_solidarity_article_68_index_factor"): 1,
        _input("belgium_pension_solidarity_beneficiary_has_family_charge"): False,
        _input("belgium_pension_solidarity_monthly_gross_legal_pensions"): (
            monthly_pension
        ),
        _input("belgium_pension_solidarity_monthly_gross_complementary_pensions"): 0,
        _input(
            "belgium_pension_solidarity_nonmonthly_periodic_pensions_monthly_equivalent"
        ): 0,
        _input("belgium_pension_solidarity_capital_pensions_fictive_monthly_rent"): 0,
    }
    return Case(
        case_id=case_id,
        period="2025",
        metadata={
            **BE_METADATA,
            "axiom_entity": "Family",
            "axiom_entity_id": "family",
            "scenario": "isolated-old-age-pensioner-tscpe",
            "yearly_pension_income": annual_pension,
            "axiom_inputs": axiom_inputs,
            "euromod_inputs": [_euromod_input(monthly_pension)],
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 70,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PENSION_INCOME: annual_pension,
                },
            ),
        ),
        outputs=(Concepts.BE_PENSIONER_HEALTH_AND_SOLIDARITY_CONTRIBUTION,),
    )


def _euromod_input(monthly_pension: float) -> dict[str, float | int]:
    # EUROMOD carries pension income at face value (poa is not uprated in
    # BE_2025), so no yem-style post-uprating bridge is needed for tscpe: the
    # supplied poa is the base tscpe_be computes on.
    return {
        "idperson": 101,
        "idpartner": 0,
        "idmother": 0,
        "idfather": 0,
        "dag": 70,
        "dgn": 1,
        "dms": 1,
        "les": 5,
        "lfs": 0,
        "lhw": 0,
        "liwmy": 0,
        "liwwh": 0,
        "loc": 5,
        "yem": 0,
        "yemmy": 0,
        "yse": 0,
        "yiy": 0,
        "poa": monthly_pension,
    }


def _input(name: str) -> str:
    return f"{NON_LABOUR_MODULE}#input.{name}"
