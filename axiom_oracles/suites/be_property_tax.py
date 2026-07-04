from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .be_worker import BE_METADATA, EUROMOD_TO_AXIOM_INPUT_BRIDGE


PROPERTY_TAX_MODULE = "be:statutes/property_tax/gross_withholding_and_supplied_centimes"
BE_PROPERTY_TAX_MODULE = "be:statutes/property_tax/immovable_withholding"
FLANDERS_PROPERTY_TAX_MODULE = "be-vlg:statutes/property_tax/immovable_withholding"
ADDITIONAL_CENTIMES_MODULE = "be:statutes/property_tax/additional_centimes"
CADASTRAL_INCOME_INDEXATION_MODULE = (
    "be:statutes/property_tax/cadastral_income_indexation"
)

REGION_FLANDERS = 0
REGION_BRUSSELS = 1
REGION_WALLONIA = 2

EUROMOD_REGION_BRUSSELS = 1
EUROMOD_REGION_FLANDERS = 2
EUROMOD_REGION_WALLONIA = 3


def be_property_tax_cases() -> list[Case]:
    """Belgium immovable-withholding cases for EUROMOD BE_2025."""

    return [
        _property_tax_case(
            "be-property-tax-flanders-high-cadastral-income",
            region=REGION_FLANDERS,
            euromod_region=EUROMOD_REGION_FLANDERS,
            communal_centimes=1068,
        ),
        _property_tax_case(
            "be-property-tax-brussels-high-cadastral-income",
            region=REGION_BRUSSELS,
            euromod_region=EUROMOD_REGION_BRUSSELS,
            communal_centimes=4328,
        ),
        _property_tax_case(
            "be-property-tax-wallonia-high-cadastral-income",
            region=REGION_WALLONIA,
            euromod_region=EUROMOD_REGION_WALLONIA,
            communal_centimes=4220,
        ),
    ]


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


def _property_tax_case(
    case_id: str,
    *,
    region: int,
    euromod_region: int,
    communal_centimes: int,
    cadastral_income: float = 1_000.0,
) -> Case:
    flanders_taxable_income_input = _flanders_property_tax_input(
        "flanders_immovable_withholding_taxable_cadastral_income"
    )
    belgium_taxable_income_input = _belgium_property_tax_input(
        "belgium_immovable_withholding_taxable_cadastral_income"
    )
    return Case(
        case_id=case_id,
        period="2025",
        metadata={
            **BE_METADATA,
            "axiom_entity": "Property",
            "axiom_entity_id": "property",
            "scenario": "immovable-withholding-high-cadastral-income-no-reductions",
            "cadastral_income": cadastral_income,
            "supplied_communal_centimes": communal_centimes,
            "axiom_inputs": {
                _property_tax_input(
                    "belgium_immovable_withholding_supplied_centimes_region"
                ): region,
                flanders_taxable_income_input: cadastral_income,
                belgium_taxable_income_input: cadastral_income,
                _additional_centimes_input(
                    "belgium_immovable_withholding_provincial_additional_centimes"
                ): 0,
                _additional_centimes_input(
                    "belgium_immovable_withholding_agglomeration_additional_centimes"
                ): 0,
                _additional_centimes_input(
                    "belgium_immovable_withholding_communal_additional_centimes"
                ): communal_centimes,
            },
            "euromod_inputs": [
                _euromod_property_owner_input(
                    cadastral_income=cadastral_income,
                    region=euromod_region,
                )
            ],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "khooo_s": [
                    flanders_taxable_income_input,
                    belgium_taxable_income_input,
                ],
            },
        },
        entities=(
            Entity(
                entity_id="property",
                kind="property",
                facts={},
            ),
        ),
        outputs=(Concepts.BE_IMMOVABLE_WITHHOLDING_GROSS_WITH_SUPPLIED_CENTIMES,),
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


def _property_tax_input(name: str) -> str:
    return f"{PROPERTY_TAX_MODULE}#input.{name}"


def _belgium_property_tax_input(name: str) -> str:
    return f"{BE_PROPERTY_TAX_MODULE}#input.{name}"


def _flanders_property_tax_input(name: str) -> str:
    return f"{FLANDERS_PROPERTY_TAX_MODULE}#input.{name}"


def _additional_centimes_input(name: str) -> str:
    return f"{ADDITIONAL_CENTIMES_MODULE}#input.{name}"


def _cadastral_income_indexation_input(name: str) -> str:
    return f"{CADASTRAL_INCOME_INDEXATION_MODULE}#input.{name}"
