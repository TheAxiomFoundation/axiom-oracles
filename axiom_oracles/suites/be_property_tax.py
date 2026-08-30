from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .be_worker import BE_METADATA


CADASTRAL_INCOME_INDEXATION_MODULE = (
    "be:statutes/property_tax/cadastral_income_indexation"
)

EUROMOD_REGION_FLANDERS = 2


def be_cadastral_income_indexation_cases() -> list[Case]:
    """Belgium indexed cadastral-income cases for EUROMOD BE_2025."""

    return [
        _cadastral_income_indexation_case(
            "be-cadastral-income-indexation-2025-rounding",
            cadastral_income=1_000.0,
        ),
        _cadastral_income_indexation_case(
            "be-cadastral-income-indexation-2025-exact-multiple",
            cadastral_income=5_000.0,
        ),
    ]


def _cadastral_income_indexation_case(
    case_id: str,
    *,
    cadastral_income: float,
) -> Case:
    return Case(
        case_id=case_id,
        period="2025",
        metadata={
            **BE_METADATA,
            "axiom_entity": "Property",
            "axiom_entity_id": "property",
            "scenario": "cadastral-income-indexation",
            "cadastral_income": cadastral_income,
            "axiom_inputs": {
                _cadastral_income_indexation_input(
                    "belgium_cadastral_income_non_indexed"
                ): cadastral_income,
            },
            "euromod_inputs": [
                _euromod_property_owner_input(
                    cadastral_income=cadastral_income,
                    region=EUROMOD_REGION_FLANDERS,
                )
            ],
        },
        entities=(
            Entity(
                entity_id="property",
                kind="property",
                facts={},
            ),
        ),
        outputs=(Concepts.BE_CADASTRAL_INCOME_INDEXED,),
    )


def _euromod_property_owner_input(
    *,
    cadastral_income: float,
    region: int,
) -> dict[str, float | int]:
    return {
        "idperson": 101,
        "idpartner": 0,
        "idmother": 0,
        "idfather": 0,
        "dag": 35,
        "dgn": 1,
        "dms": 1,
        "drgn1": region,
        "les": 0,
        "lfs": 0,
        "lhw": 0,
        "liwmy": 0,
        "liwwh": 0,
        "loc": 5,
        "khooo": cadastral_income,
        "amrtn": 3,
        "yem": 0,
        "yemmy": 0,
        "yse": 0,
        "yiy": 0,
        "poa": 0,
    }


def _cadastral_income_indexation_input(name: str) -> str:
    return f"{CADASTRAL_INCOME_INDEXATION_MODULE}#input.{name}"
