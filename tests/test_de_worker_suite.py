from __future__ import annotations

import pytest

from axiom_oracles.comparison.mappings import comparable_mappings
from axiom_oracles.core.case import Concepts
from axiom_oracles.core.geography import GeographyScope
from axiom_oracles.suites.de_worker import (
    DE_INPUT_UPRATING_FACTOR,
    DE_WORKER_OUTPUTS,
    de_worker_dual_oracle_cases,
    reduce_gettsim_household_values,
)


EXPECTED_CASE_IDS = [
    "single-w-500",
    "single-w-1200",
    "single-w-2500",
    "single-w-4000",
    "single-w-5500",
    "single-w-7500",
    "single-w-9000",
    "single-w-12000",
    "single-e-4000",
    "couple-8000-0",
    "couple-4000-2000",
    "parent-1child-4000",
    "parent-2children-4000",
]


def _case(case_id: str):
    return next(
        case for case in de_worker_dual_oracle_cases() if case.case_id == case_id
    )


def test_de_worker_grid_order_scope_period_and_outputs() -> None:
    cases = de_worker_dual_oracle_cases()

    assert [case.case_id for case in cases] == EXPECTED_CASE_IDS
    assert {case.period for case in cases} == {"2025"}
    assert {case.locale for case in cases} == {"DE"}
    assert {case.scope for case in cases} == {
        GeographyScope(type="country", geoid="DE")
    }
    assert all(case.outputs == DE_WORKER_OUTPUTS for case in cases)


def test_worker_rows_pin_month_count_hours_and_region() -> None:
    west = _case("single-w-4000").metadata["euromod_inputs"][0]
    east = _case("single-e-4000").metadata["euromod_inputs"][0]

    assert west["yem"] == 4000.0
    assert {key: west[key] for key in ("yemmy", "liwmy", "lhw", "liwwh")} == {
        "yemmy": 12,
        "liwmy": 12,
        "lhw": 40,
        "liwwh": 40,
    }
    assert west["drgn1"] == 9
    assert east["drgn1"] == 4


def test_gettsim_mirror_uses_exact_dataset_uprating() -> None:
    case = _case("single-w-4000")
    [person] = case.metadata["gettsim_case"]["persons"]

    assert DE_INPUT_UPRATING_FACTOR == 61 / 56
    assert person["einnahmen__bruttolohn_m"] == pytest.approx(4000 * 61 / 56)


def test_couple_and_single_parent_engine_projections() -> None:
    couple = _case("couple-4000-2000")
    couple_gt = couple.metadata["gettsim_case"]
    assert couple_gt["spouse_pairs"] == [[0, 1]]
    assert all(
        person["einkommensteuer__gemeinsam_veranlagt"]
        for person in couple_gt["persons"]
    )
    assert [row["idpartner"] for row in couple.metadata["euromod_inputs"]] == [
        102,
        101,
    ]

    parent = _case("parent-2children-4000")
    parent_gt = parent.metadata["gettsim_case"]
    assert parent_gt["persons"][0]["familie__alleinerziehend"] is True
    assert (
        parent_gt["persons"][0]["sozialversicherung__pflege__beitrag__hat_kinder"]
        is True
    )
    assert parent_gt["parents"] == {1: [0, None], 2: [0, None]}
    assert parent_gt["kindergeld_recipients"] == {1: 0, 2: 0}


def test_gettsim_sn_targets_reduce_with_max_and_person_targets_sum() -> None:
    reduced = reduce_gettsim_household_values(
        {
            "einkommensteuer.betrag_y_sn": [6241, 6241, 0],
            "solidaritätszuschlag.betrag_y_sn": [10, 10, 0],
            "kindergeld.betrag_m": [510, 0, 0],
            "sozialversicherung.rente.beitrag.betrag_versicherter_m": [
                405.214285714,
                202.607142857,
            ],
        }
    )

    assert reduced["einkommensteuer.betrag_y_sn"] == 6241
    assert reduced["solidaritätszuschlag.betrag_y_sn"] == 10
    assert reduced["kindergeld.betrag_m"] == 510
    assert reduced[
        "sozialversicherung.rente.beitrag.betrag_versicherter_m"
    ] == pytest.approx(607.821428571)


def test_de_concept_mappings_pin_targets_and_cent_tolerance() -> None:
    mappings = comparable_mappings(
        "euromod",
        "gettsim",
        locales={"DE"},
        scope={"type": "country", "geoid": "DE"},
        concepts=set(DE_WORKER_OUTPUTS),
    )

    assert [mapping.concept_id for mapping in mappings] == list(DE_WORKER_OUTPUTS)
    assert all(mapping.comparison == "amount" for mapping in mappings)
    assert all(mapping.tolerance == 0.01 for mapping in mappings)
    by_concept = {mapping.concept_id: mapping for mapping in mappings}
    tax = by_concept[Concepts.DE_INCOME_TAX_INCLUDING_SOLIDARITY_SURCHARGE_ANNUAL]
    assert tax.target_for_engine("euromod") == "tin_s"
    assert tax.target_for_engine("gettsim") == [
        "einkommensteuer.betrag_y_sn",
        "solidaritätszuschlag.betrag_y_sn",
    ]
