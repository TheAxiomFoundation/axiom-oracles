from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

import axiom_oracles.bridges.state_tax_populace_runner as state_tax_runner
from axiom_oracles.bridges.state_tax_populace_runner import (
    DISPOSITION_BLOCKED,
    DISPOSITION_NO_BROAD_PIT,
    DISPOSITION_NONPOSITIVE_WEIGHT,
    DISPOSITION_READY,
    StateTaxPopulationRoutingError,
    TaxUnitRoute,
    _is_official_github_remote,
    calculate_policyengine_targets,
    calculate_policyengine_projection_inputs,
    compare_ready_state_tax_units,
    population_routing_report,
    route_tax_units,
    select_ready_tax_units,
    validate_campaign_dataset_identity,
)


def _frames():
    tax_units = pd.DataFrame(
        {
            "tax_unit_id": [40, 10, 30, 20],
            "tax_unit_weight": [0, 2.5, 4, 3],
        }
    )
    persons = pd.DataFrame(
        {
            "person_id": [1, 2, 3, 4, 5],
            "person_tax_unit_id": [10, 10, 20, 30, 40],
            "person_household_id": [1, 1, 2, 3, 4],
        }
    )
    households = pd.DataFrame(
        {
            "household_id": [1, 2, 3, 4],
            "state_fips": [33, 6, 48, 36],
            "household_weight": [12, 13, 14, 15],
        }
    )
    return tax_units, persons, households


def test_routes_every_tax_unit_after_person_household_geography_join() -> None:
    tax_units, persons, households = _frames()
    routes = route_tax_units(
        raw_tax_units=tax_units,
        raw_persons=persons,
        raw_households=households,
    )

    by_id = {route.tax_unit_id: route for route in routes}
    assert by_id[10].state == "NH"
    assert by_id[10].weight == 2.5
    assert by_id[10].disposition == DISPOSITION_READY
    assert by_id[20].disposition == DISPOSITION_BLOCKED
    assert by_id[30].disposition == DISPOSITION_NO_BROAD_PIT
    assert by_id[40].disposition == DISPOSITION_NONPOSITIVE_WEIGHT


def test_falls_back_to_household_weight_when_tax_unit_weight_is_absent() -> None:
    tax_units, persons, households = _frames()
    routes = route_tax_units(
        raw_tax_units=tax_units.drop(columns="tax_unit_weight"),
        raw_persons=persons,
        raw_households=households,
    )

    assert {route.tax_unit_id: route.weight for route in routes} == {
        40: 15,
        10: 12,
        30: 14,
        20: 13,
    }


def test_conflicting_or_missing_entity_links_fail_closed() -> None:
    tax_units, persons, households = _frames()
    conflicting = pd.concat(
        [
            persons,
            pd.DataFrame(
                [{"person_id": 6, "person_tax_unit_id": 10, "person_household_id": 2}]
            ),
        ],
        ignore_index=True,
    )
    with pytest.raises(StateTaxPopulationRoutingError, match="multiple households"):
        route_tax_units(
            raw_tax_units=tax_units,
            raw_persons=conflicting,
            raw_households=households,
        )

    with pytest.raises(StateTaxPopulationRoutingError, match="missing household_id"):
        route_tax_units(
            raw_tax_units=tax_units,
            raw_persons=persons.assign(
                person_household_id=lambda frame: frame["person_household_id"].replace(4, 99)
            ),
            raw_households=households,
        )


@pytest.mark.parametrize("weight", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_population_weights_fail_closed(weight: float) -> None:
    tax_units, persons, households = _frames()
    tax_units.loc[0, "tax_unit_weight"] = weight

    with pytest.raises(StateTaxPopulationRoutingError, match="must be finite"):
        route_tax_units(
            raw_tax_units=tax_units,
            raw_persons=persons,
            raw_households=households,
        )

def test_sampling_occurs_per_state_after_readiness_filtering() -> None:
    routes = (
        TaxUnitRoute(9, 1, "NH", "33", 1, DISPOSITION_READY),
        TaxUnitRoute(2, 2, "NH", "33", 1, DISPOSITION_READY),
        TaxUnitRoute(7, 3, "CA", "06", 1, DISPOSITION_READY),
        TaxUnitRoute(1, 4, "CA", "06", 1, DISPOSITION_BLOCKED),
        TaxUnitRoute(3, 5, "TX", "48", 1, DISPOSITION_NO_BROAD_PIT),
    )

    selected = select_ready_tax_units(routes, sample_size_per_state=1)

    assert [(route.state, route.tax_unit_id) for route in selected] == [
        ("CA", 7),
        ("NH", 2),
    ]


def test_report_accounts_for_all_51_jurisdictions_and_every_unit() -> None:
    tax_units, persons, households = _frames()
    routes = route_tax_units(
        raw_tax_units=tax_units,
        raw_persons=persons,
        raw_households=households,
    )

    report = population_routing_report(routes)

    assert report["state_count"] == 51
    assert report["population_scope"] == {
        "unit": "tax_unit",
        "geography_source": "household_state_fips",
        "residency_model": "household_state_as_full_year_residence",
        "inclusion": "all_positive_weight_routed_tax_units",
        "filtered_slices_allowed": False,
    }
    assert report["tax_unit_count"] == 4
    assert report["positive_weight_count"] == 3
    assert report["selected_ready_count"] == 1
    assert report["eligible_ready_count"] == 1
    assert report["excluded_count"] == 3
    assert report["weighted_eligible_ready_tax_units"] == 2.5
    assert report["weighted_excluded_tax_units"] == 7
    assert report["weighted_dispositions"] == {
        DISPOSITION_READY: 2.5,
        DISPOSITION_BLOCKED: 3,
        DISPOSITION_NO_BROAD_PIT: 4,
        DISPOSITION_NONPOSITIVE_WEIGHT: 0,
    }
    assert report["errored_count"] == 0
    assert report["states"]["NH"]["selected_count"] == 1
    assert report["states"]["CA"]["dispositions"] == {
        DISPOSITION_BLOCKED: 1
    }
    assert report["states"]["TX"]["dispositions"] == {
        DISPOSITION_NO_BROAD_PIT: 1
    }
    assert report["unknown_geography"]["tax_unit_count"] == 0


def test_ready_comparison_runs_one_compiled_state_batch(tmp_path) -> None:
    routes = (
        TaxUnitRoute(2, 1, "NH", "33", 2.5, DISPOSITION_READY),
        TaxUnitRoute(5, 2, "NH", "33", 3.5, DISPOSITION_READY),
        TaxUnitRoute(7, 3, "CA", "06", 4, DISPOSITION_BLOCKED),
    )
    calls = []

    def fake_axiom_runner(**kwargs):
        calls.append(kwargs)
        output = kwargs["request"]["queries"][0]["outputs"][0]
        return [
            {
                "entity_id": query["entity_id"],
                "outputs": {output: {"value": {"value": "0"}}},
            }
            for query in kwargs["request"]["queries"]
        ]

    report = compare_ready_state_tax_units(
        routes=routes,
        policyengine_targets={"NH": {2: 0.0, 5: 0.0}},
        year=2026,
        rulespec_root=tmp_path / "rulespec-us",
        axiom_rules_path=tmp_path / "axiom-rules",
        axiom_runner=fake_axiom_runner,
    )

    assert report["ready_state_count"] == 1
    assert report["compared_count"] == 2
    assert report["mismatch_count"] == 0
    assert report["states"]["NH"]["weighted_compared_tax_units"] == 6
    assert len(calls) == 1
    assert len(calls[0]["request"]["queries"]) == 2


def test_policyengine_target_calculation_is_limited_to_ready_states() -> None:
    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"
            self.calls = []

        def calculate(self, variable, period):
            self.calls.append((variable, period))
            return [0, 0]

    routes = (
        TaxUnitRoute(1, 1, "NH", "33", 1, DISPOSITION_READY),
        TaxUnitRoute(2, 2, "CA", "06", 1, DISPOSITION_BLOCKED),
    )
    raw_tax_units = pd.DataFrame({"tax_unit_id": [1, 2]})

    targets = calculate_policyengine_targets(
        dataset="dataset",
        raw_tax_units=raw_tax_units,
        routes=routes,
        year=2026,
        microsimulation_factory=FakeSimulation,
    )

    assert targets == {"NH": {1: 0.0, 2: 0.0}}


def test_policyengine_projection_calculation_uses_only_reviewed_boundaries() -> None:
    calls = []

    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"

        def calculate(self, variable, period):
            calls.append((variable, period))
            return [-100, 25000]

    routes = (
        TaxUnitRoute(1, 1, "UT", "49", 1, DISPOSITION_READY),
        TaxUnitRoute(2, 2, "CA", "06", 1, DISPOSITION_BLOCKED),
    )
    raw_tax_units = pd.DataFrame({"tax_unit_id": [1, 2]})

    projections = calculate_policyengine_projection_inputs(
        dataset="dataset",
        raw_tax_units=raw_tax_units,
        routes=routes,
        year=2026,
        microsimulation_factory=FakeSimulation,
    )

    slot = (
        "us-ut:policies/income_tax/pilot_liability_pipeline#input."
        "ut_pit_pilot_state_taxable_income"
    )
    assert calls == [("ut_taxable_income", 2026)]
    assert projections == {"UT": {slot: {1: -100.0, 2: 25000.0}}}


def test_reviewed_iowa_and_kansas_projection_types_and_transforms() -> None:
    calls = []
    values = {
        "ia_taxable_income_consolidated": [10_000, 20_000],
        "ia_modified_income": [12_000, 40_000],
        "ia_alternate_tax_eligible": [False, True],
        "greater_age_head_spouse": [64, 65],
        "ks_taxable_income": [15_000, 50_000],
        "tax_unit_is_joint": [False, True],
    }

    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"

        def calculate(self, variable, period):
            calls.append((variable, period))
            return values[variable]

    routes = (
        TaxUnitRoute(1, 1, "IA", "19", 1, DISPOSITION_READY),
        TaxUnitRoute(2, 2, "KS", "20", 1, DISPOSITION_READY),
    )
    projections = calculate_policyengine_projection_inputs(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": [1, 2]}),
        routes=routes,
        year=2026,
        microsimulation_factory=FakeSimulation,
    )

    ia_prefix = "us-ia:policies/income_tax/pilot_liability_pipeline#input."
    ks_prefix = "us-ks:policies/income_tax/pilot_liability_pipeline#input."
    assert projections["IA"][f"{ia_prefix}ia_pit_pilot_supplied_regular_tax_rate"] == {
        1: 0.038,
        2: 0.038,
    }
    assert projections["IA"][f"{ia_prefix}ia_pit_pilot_supplied_alternate_tax_rate"] == {
        1: 0.043,
        2: 0.043,
    }
    assert projections["IA"][f"{ia_prefix}ia_pit_pilot_alternate_tax_eligible"] == {
        1: False,
        2: True,
    }
    assert projections["IA"][
        f"{ia_prefix}ia_pit_pilot_head_or_spouse_age_65_or_older"
    ] == {1: False, 2: True}
    assert projections["KS"][f"{ks_prefix}ks_pit_pilot_filing_status_joint"] == {
        1: False,
        2: True,
    }
    assert calls == [
        ("ia_taxable_income_consolidated", 2026),
        ("ia_modified_income", 2026),
        ("ia_alternate_tax_eligible", 2026),
        ("greater_age_head_spouse", 2026),
        ("ks_taxable_income", 2026),
        ("tax_unit_is_joint", 2026),
    ]


def test_reviewed_virginia_zero_one_boundary_becomes_boolean() -> None:
    calls = []
    values = {
        "va_taxable_income": [0.0, 25_000.0],
        "va_must_file": [0.0, 1.0],
    }

    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"

        def calculate(self, variable, period):
            calls.append((variable, period))
            return values[variable]

    routes = (
        TaxUnitRoute(1, 1, "VA", "51", 1, DISPOSITION_READY),
        TaxUnitRoute(2, 2, "VA", "51", 1, DISPOSITION_READY),
    )
    projections = calculate_policyengine_projection_inputs(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": [1, 2]}),
        routes=routes,
        year=2026,
        microsimulation_factory=FakeSimulation,
    )

    prefix = "us-va:policies/income_tax/pilot_liability_pipeline#input."
    assert projections["VA"][f"{prefix}va_pit_pilot_must_file"] == {
        1: False,
        2: True,
    }
    assert calls == [("va_taxable_income", 2026), ("va_must_file", 2026)]


def test_reviewed_oklahoma_filing_status_projection_selects_wide_schedule() -> None:
    calls = []
    values = {
        "ok_taxable_income": [10_000, 20_000, 30_000, 40_000, 50_000],
        "filing_status": [
            "SINGLE",
            "JOINT",
            "SEPARATE",
            "HEAD_OF_HOUSEHOLD",
            "SURVIVING_SPOUSE",
        ],
    }

    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"

        def calculate(self, variable, period):
            calls.append((variable, period))
            return values[variable]

    routes = tuple(
        TaxUnitRoute(index, index, "OK", "40", 1, DISPOSITION_READY)
        for index in range(1, 6)
    )
    projections = calculate_policyengine_projection_inputs(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": list(range(1, 6))}),
        routes=routes,
        year=2026,
        microsimulation_factory=FakeSimulation,
    )

    prefix = "us-ok:policies/income_tax/pilot_liability_pipeline#input."
    assert projections["OK"][f"{prefix}ok_pit_pilot_filing_status_uses_wide_schedule"] == {
        1: False,
        2: True,
        3: False,
        4: True,
        5: True,
    }
    assert calls == [("ok_taxable_income", 2026), ("filing_status", 2026)]


def test_reviewed_alabama_filing_status_projection_selects_joint_schedule() -> None:
    calls = []
    values = {
        "al_taxable_income": [10_000, 20_000, 30_000, 40_000, 50_000],
        "filing_status": [
            "SINGLE",
            "JOINT",
            "SEPARATE",
            "HEAD_OF_HOUSEHOLD",
            "SURVIVING_SPOUSE",
        ],
    }

    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"

        def calculate(self, variable, period):
            calls.append((variable, period))
            return values[variable]

    routes = tuple(
        TaxUnitRoute(index, index, "AL", "01", 1, DISPOSITION_READY)
        for index in range(1, 6)
    )
    projections = calculate_policyengine_projection_inputs(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": list(range(1, 6))}),
        routes=routes,
        year=2026,
        microsimulation_factory=FakeSimulation,
    )

    prefix = "us-al:policies/income_tax/pilot_liability_pipeline#input."
    assert projections["AL"][f"{prefix}al_pit_pilot_joint_schedule_applies"] == {
        1: False,
        2: True,
        3: False,
        4: False,
        5: True,
    }
    assert calls == [("al_taxable_income", 2026), ("filing_status", 2026)]


def test_reviewed_connecticut_projection_covers_all_filing_statuses() -> None:
    values = {
        "ct_taxable_income": [1, 2, 3, 4, 5],
        "ct_agi": [11, 12, 13, 14, 15],
        "filing_status": [
            "SINGLE",
            "JOINT",
            "SEPARATE",
            "HEAD_OF_HOUSEHOLD",
            "SURVIVING_SPOUSE",
        ],
        "ct_personal_credit_rate": [0, 0.01, 0.02, 0.03, 0.04],
        "ct_amt": [0, 20, 0, 40, 0],
        "ct_property_tax_credit_potential": [1, 2, 3, 4, 5],
        "ct_stillborn_credit": [0, 0, 750, 0, 0],
    }

    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"

        def calculate(self, variable, period):
            assert period == 2026
            return values[variable]

    projections = calculate_policyengine_projection_inputs(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": [1, 2, 3, 4, 5]}),
        routes=tuple(
            TaxUnitRoute(index, index, "CT", "09", 1, DISPOSITION_READY)
            for index in range(1, 6)
        ),
        year=2026,
        microsimulation_factory=FakeSimulation,
    )["CT"]

    prefix = "us-ct:policies/income_tax/pilot_liability_pipeline#input."
    assert projections[
        f"{prefix}ct_pit_pilot_filing_status_joint_or_surviving_spouse"
    ] == {1: False, 2: True, 3: False, 4: False, 5: True}
    assert projections[f"{prefix}ct_pit_pilot_filing_status_head_of_household"] == {
        1: False,
        2: False,
        3: False,
        4: True,
        5: False,
    }
    assert projections[f"{prefix}ct_pit_pilot_filing_status_separate"] == {
        1: False,
        2: False,
        3: True,
        4: False,
        5: False,
    }


def test_vermont_projection_proves_zero_interest_scope_without_relations() -> None:
    values = {
        "us_govt_interest": [0.0, float("nan")],
        "vt_normal_income_tax": [1_000.0, 2_000.0],
        "adjusted_gross_income": [100_000.0, 200_000.0],
    }

    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"

        def calculate(self, variable, period):
            assert period == 2026
            return values[variable]

    projections = calculate_policyengine_projection_inputs(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": [1, 2]}),
        raw_persons=None,
        routes=(TaxUnitRoute(1, 1, "VT", "50", 1, DISPOSITION_READY),),
        year=2026,
        microsimulation_factory=FakeSimulation,
    )["VT"]

    prefix = "us-vt:policies/income_tax/pilot_liability_pipeline#input."
    assert projections[f"{prefix}vt_pit_pilot_supplied_normal_income_tax"] == {
        1: 1_000.0,
        2: 2_000.0,
    }
    assert projections[f"{prefix}vt_pit_pilot_federal_adjusted_gross_income"] == {
        1: 100_000.0,
        2: 200_000.0,
    }


@pytest.mark.parametrize(
    ("values", "selected", "error"),
    [
        ([1.0, 0.0], {1}, "1 selected tax unit.*nonzero"),
        ([float("nan"), 0.0], {1}, "non-finite"),
        ([0.0], {1}, "returned 1 rows for 2 tax units"),
        ([0.0, 0.0], {99}, "unknown tax_unit_id"),
    ],
)
def test_vermont_zero_interest_scope_fails_closed(values, selected, error) -> None:
    class FakeSimulation:
        def calculate(self, variable, period):
            assert variable == "us_govt_interest"
            assert period == 2026
            return values

    with pytest.raises(StateTaxPopulationRoutingError, match=error):
        state_tax_runner._validate_reviewed_pe_zero_assumptions(
            state="VT",
            sim=FakeSimulation(),
            tax_unit_ids=[1, 2],
            selected_tax_unit_ids=selected,
            year=2026,
        )


def test_new_jersey_projection_proves_nonresident_alien_branch_absent() -> None:
    calls = []
    values = {
        "nj_taxable_income": [10_000, 80_000],
        "filing_status": ["SINGLE", "JOINT"],
    }

    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"

        def calculate(self, variable, period):
            calls.append((variable, period))
            return values[variable]

    routes = (
        TaxUnitRoute(1, 1, "NJ", "34", 1, DISPOSITION_READY),
        TaxUnitRoute(2, 2, "NJ", "34", 1, DISPOSITION_READY),
    )
    projections = calculate_policyengine_projection_inputs(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": [1, 2]}),
        raw_persons=pd.DataFrame(
            {
                "person_tax_unit_id": [1, 1, 2],
                "immigration_status_str": ["CITIZEN", "CITIZEN", "CITIZEN"],
            }
        ),
        routes=routes,
        year=2026,
        microsimulation_factory=FakeSimulation,
    )

    prefix = "us-nj:policies/income_tax/pilot_liability_pipeline#input."
    assert projections["NJ"][f"{prefix}nj_pit_pilot_state_taxable_income"] == {
        1: 10_000.0,
        2: 80_000.0,
    }
    assert projections["NJ"][
        f"{prefix}nj_pit_pilot_filing_status_joint_head_or_surviving"
    ] == {1: False, 2: True}
    assert calls == [("nj_taxable_income", 2026), ("filing_status", 2026)]


@pytest.mark.parametrize(
    ("persons", "error"),
    [
        (
            pd.DataFrame({"person_tax_unit_id": [1]}),
            "missing required columns: immigration_status_str",
        ),
        (
            pd.DataFrame(
                {
                    "person_tax_unit_id": [1],
                    "immigration_status_str": ["NON_CITIZEN"],
                }
            ),
            "reviewed population assumption failed",
        ),
        (
            pd.DataFrame(
                {
                    "person_tax_unit_id": [2],
                    "immigration_status_str": ["CITIZEN"],
                }
            ),
            "selected tax unit.*no linked person",
        ),
    ],
)
def test_new_jersey_population_assumption_fails_closed(
    persons: pd.DataFrame, error: str
) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=error):
        state_tax_runner._validate_reviewed_population_assumptions(
            state="NJ",
            raw_persons=persons,
            selected_tax_unit_ids={1},
        )


def test_hawaii_completed_capital_gains_worksheet_projection() -> None:
    calls = []
    values = {
        "person_id": [11, 12, 21],
        "tax_unit_id": [1, 1, 2],
        "long_term_capital_gains": [30_000.0, -5_000.0, -2_000.0],
        "net_capital_gain": [40_000.0, 10_000.0],
        "hi_taxable_income": [100_000.0, 50_000.0],
        "filing_status": ["JOINT", "HEAD_OF_HOUSEHOLD"],
    }

    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"

        def calculate(self, variable, period, map_to=None):
            calls.append((variable, period))
            if variable == "tax_unit_id":
                assert map_to == "person"
            else:
                assert map_to is None
            return values[variable]

    projections = calculate_policyengine_projection_inputs(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": [1, 2]}),
        raw_persons=pd.DataFrame(
            {
                "person_id": [11, 12, 21],
                "person_tax_unit_id": [1, 1, 2],
            }
        ),
        routes=(
            TaxUnitRoute(1, 1, "HI", "15", 1, DISPOSITION_READY),
            TaxUnitRoute(2, 2, "HI", "15", 1, DISPOSITION_READY),
        ),
        year=2026,
        microsimulation_factory=FakeSimulation,
    )

    prefix = "us-hi:policies/income_tax/pilot_liability_pipeline#input."
    assert projections["HI"] == {
        f"{prefix}hi_pit_pilot_state_taxable_income": {
            1: 100_000.0,
            2: 50_000.0,
        },
        f"{prefix}hi_pit_pilot_filing_status_joint_or_surviving_spouse": {
            1: True,
            2: False,
        },
        f"{prefix}hi_pit_pilot_filing_status_head_of_household": {
            1: False,
            2: True,
        },
        f"{prefix}hi_pit_pilot_capital_gains_worksheet_line_10": {
            1: 25_000.0,
            2: 0.0,
        },
    }
    assert calls == [
        ("person_id", 2026),
        ("tax_unit_id", 2026),
        ("long_term_capital_gains", 2026),
        ("hi_taxable_income", 2026),
        ("filing_status", 2026),
        ("filing_status", 2026),
        ("net_capital_gain", 2026),
    ]


def test_reviewed_montana_person_sums_and_capital_gain_transform() -> None:
    calls = []
    values = {
        "person_id": [11, 12, 21],
        "tax_unit_id": [1, 1, 2],
        "mt_taxable_income_joint": [60_000.0, 40_000.0, 50_000.0],
        "long_term_capital_gains": [80_000.0, 20_000.0, 20_000.0],
        "short_term_capital_gains": [-30_000.0, 10_000.0, -25_000.0],
        "filing_status": ["JOINT", "HEAD_OF_HOUSEHOLD"],
    }

    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"

        def calculate(self, variable, period, map_to=None):
            calls.append((variable, period))
            if variable == "tax_unit_id":
                assert map_to == "person"
            else:
                assert map_to is None
            return values[variable]

    projections = calculate_policyengine_projection_inputs(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": [1, 2]}),
        raw_persons=pd.DataFrame(
            {
                "person_id": [11, 12, 21],
                "person_tax_unit_id": [1, 1, 2],
            }
        ),
        routes=(
            TaxUnitRoute(1, 1, "MT", "30", 1, DISPOSITION_READY),
            TaxUnitRoute(2, 2, "MT", "30", 1, DISPOSITION_READY),
        ),
        year=2026,
        microsimulation_factory=FakeSimulation,
    )

    prefix = "us-mt:policies/income_tax/pilot_liability_pipeline#input."
    assert projections["MT"] == {
        f"{prefix}mt_pit_pilot_state_taxable_income": {1: 100_000.0, 2: 50_000.0},
        f"{prefix}mt_pit_pilot_section_1222_net_long_term_capital_gain": {
            1: 80_000.0,
            2: 0.0,
        },
        f"{prefix}mt_pit_pilot_filing_status_joint_or_surviving_spouse": {
            1: True,
            2: False,
        },
        f"{prefix}mt_pit_pilot_filing_status_head_of_household": {
            1: False,
            2: True,
        },
    }
    assert calls == [
        ("person_id", 2026),
        ("tax_unit_id", 2026),
        ("long_term_capital_gains", 2026),
        ("mt_taxable_income_joint", 2026),
        ("short_term_capital_gains", 2026),
        ("filing_status", 2026),
        ("filing_status", 2026),
    ]


def test_montana_person_aggregation_rejects_identity_order_drift() -> None:
    class FakeSimulation:
        def __init__(self, dataset):
            pass

        def calculate(self, variable, period):
            assert variable == "person_id"
            return [12, 11]

    with pytest.raises(
        StateTaxPopulationRoutingError, match="Person identity/order"
    ):
        state_tax_runner._reviewed_person_sums(
            state="MT",
            sim=FakeSimulation("dataset"),
            variables={"mt_taxable_income_joint"},
            raw_persons=pd.DataFrame(
                {"person_id": [11, 12], "person_tax_unit_id": [1, 2]}
            ),
            tax_unit_ids=[1, 2],
            year=2026,
        )


def test_montana_person_aggregation_rejects_unknown_tax_unit_link() -> None:
    class FakeSimulation:
        def __init__(self, dataset):
            pass

        def calculate(self, variable, period):
            assert variable == "person_id"
            return [11, 12]

    with pytest.raises(StateTaxPopulationRoutingError, match="unknown tax_unit_id"):
        state_tax_runner._reviewed_person_sums(
            state="MT",
            sim=FakeSimulation("dataset"),
            variables={"mt_taxable_income_joint"},
            raw_persons=pd.DataFrame(
                {"person_id": [11, 12], "person_tax_unit_id": [1, 99]}
            ),
            tax_unit_ids=[1, 2],
            year=2026,
        )


def test_hawaii_uses_the_shared_reviewed_person_sum_projector() -> None:
    class FakeSimulation:
        def calculate(self, variable, period, map_to=None):
            assert period == 2026
            return {
                "person_id": [11, 12, 21],
                "tax_unit_id": [1, 1, 2],
                "long_term_capital_gains": [8_000.0, -1_000.0, 2_500.0],
            }[variable]

    sums = state_tax_runner._reviewed_person_sums(
        state="HI",
        sim=FakeSimulation(),
        variables={"long_term_capital_gains"},
        raw_persons=pd.DataFrame(
            {
                "person_id": [11, 12, 21],
                "person_tax_unit_id": [1, 1, 2],
            }
        ),
        tax_unit_ids=[1, 2],
        year=2026,
    )

    assert sums == {"long_term_capital_gains": [7_000.0, 2_500.0]}


def test_reviewed_person_values_reject_identity_and_cardinality_drift() -> None:
    class FakeSimulation:
        def __init__(self, person_ids):
            self.person_ids = person_ids

        def calculate(self, variable, period, map_to=None):
            assert variable == "person_id"
            assert map_to is None
            assert period == 2026
            return self.person_ids

    raw_persons = pd.DataFrame(
        {"person_id": [11, 12], "person_tax_unit_id": [1, 2]}
    )
    with pytest.raises(
        StateTaxPopulationRoutingError, match="DE: PolicyEngine Person identity/order"
    ):
        state_tax_runner._reviewed_person_values(
            state="DE",
            sim=FakeSimulation([12, 11]),
            variables=set(),
            raw_persons=raw_persons,
            tax_unit_ids=[1, 2],
            year=2026,
        )
    with pytest.raises(
        StateTaxPopulationRoutingError, match="DE: PolicyEngine Person cardinality"
    ):
        state_tax_runner._reviewed_person_values(
            state="DE",
            sim=FakeSimulation([11]),
            variables=set(),
            raw_persons=raw_persons,
            tax_unit_ids=[1, 2],
            year=2026,
        )


def test_reviewed_person_values_reject_remapped_tax_unit_membership() -> None:
    class FakeSimulation:
        def calculate(self, variable, period, map_to=None):
            assert period == 2026
            if variable == "person_id":
                assert map_to is None
                return [11, 12, 21]
            assert variable == "tax_unit_id"
            assert map_to == "person"
            return [1, 2, 1]

    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="DE: PolicyEngine Person-to-TaxUnit mapping/order",
    ):
        state_tax_runner._reviewed_person_values(
            state="DE",
            sim=FakeSimulation(),
            variables=set(),
            raw_persons=pd.DataFrame(
                {
                    "person_id": [11, 12, 21],
                    "person_tax_unit_id": [1, 1, 2],
                }
            ),
            tax_unit_ids=[1, 2],
            year=2026,
        )


def test_delaware_person_projection_preserves_person_grain(monkeypatch) -> None:
    prefix = "us-de:policies/income_tax/pilot_liability_pipeline#input."
    separate_slot = f"{prefix}de_pit_pilot_supplied_separate_taxable_income"
    included_slot = f"{prefix}de_pit_pilot_taxpayer_is_included"
    combined_slot = f"{prefix}de_pit_pilot_supplied_combined_taxable_income"
    files_separately_slot = f"{prefix}de_pit_pilot_files_separately"
    inputs = (
        SimpleNamespace(
            slot=separate_slot,
            source_kind="pe_upstream_boundary",
            policyengine_variable="de_taxable_income_indv",
            policyengine_variables=(),
            policyengine_transform=None,
            constant_value=None,
        ),
        SimpleNamespace(
            slot=included_slot,
            source_kind="derived",
            policyengine_variable=None,
            policyengine_variables=("is_tax_unit_head", "is_tax_unit_spouse"),
            policyengine_relationship="upstream",
            policyengine_transform="person_filer_role_or",
            constant_value=None,
        ),
        SimpleNamespace(
            slot=combined_slot,
            source_kind="derived",
            policyengine_variable="de_taxable_income_joint",
            policyengine_variables=(),
            policyengine_transform="person_sum_to_tax_unit",
            constant_value=None,
        ),
        SimpleNamespace(
            slot=files_separately_slot,
            source_kind="pe_upstream_boundary",
            policyengine_variable="de_files_separately",
            policyengine_variables=(),
            policyengine_transform=None,
            constant_value=None,
        ),
    )
    jurisdiction = SimpleNamespace(inputs=inputs, relations=())
    contract = SimpleNamespace(
        validation_year=2026,
        by_state=lambda: {"DE": jurisdiction},
    )
    monkeypatch.setattr(
        state_tax_runner, "validate_state_tax_populace_contract", lambda value: value
    )

    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"

        def calculate(self, variable, period, map_to=None):
            assert period == 2026
            return {
                "person_id": [11, 12, 13, 21],
                "tax_unit_id": [1, 1, 1, 2],
                # Unit 2 deliberately has no modeled PE filer; zero-filer units
                # remain valid and their sum_where aggregate is zero.
                "is_tax_unit_head": [True, False, False, False],
                "is_tax_unit_spouse": [False, True, False, False],
                "de_taxable_income_indv": [10_000.0, 20_000.0, 500.0, 30_000.0],
                "de_taxable_income_joint": [30_000.0, 0.0, 0.0, 30_000.0],
                "de_files_separately": [True, False],
            }[variable]

    projections = calculate_policyengine_projection_inputs(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": [1, 2]}),
        raw_persons=pd.DataFrame(
            {
                "person_id": [11, 12, 13, 21],
                "person_tax_unit_id": [1, 1, 1, 2],
            }
        ),
        routes=(
            TaxUnitRoute(1, 1, "DE", "10", 1, DISPOSITION_READY),
            TaxUnitRoute(2, 2, "DE", "10", 1, DISPOSITION_READY),
        ),
        year=2026,
        contract=contract,
        microsimulation_factory=FakeSimulation,
    )

    assert projections == {
        "DE": {
            separate_slot: {
                11: 10_000.0,
                12: 20_000.0,
                13: 500.0,
                21: 30_000.0,
            },
            included_slot: {11: True, 12: True, 13: False, 21: False},
            combined_slot: {1: 30_000.0, 2: 30_000.0},
            files_separately_slot: {1: True, 2: False},
        }
    }


def test_delaware_filer_inclusion_rejects_ambiguous_policyengine_roles() -> None:
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="person_id 11 is both TaxUnit head and spouse",
    ):
        state_tax_runner._reviewed_filer_inclusions(
            state="DE",
            person_ids=[11],
            person_tax_unit_ids=[1],
            tax_unit_ids=[1],
            selected_tax_unit_ids={1},
            head_values=[True],
            spouse_values=[True],
        )

    with pytest.raises(
        StateTaxPopulationRoutingError,
        match=r"invalid PolicyEngine TaxUnit filer roles: 1 \(heads=2, spouses=0\)",
    ):
        state_tax_runner._reviewed_filer_inclusions(
            state="DE",
            person_ids=[11, 12],
            person_tax_unit_ids=[1, 1],
            tax_unit_ids=[1],
            selected_tax_unit_ids={1},
            head_values=[True, True],
            spouse_values=[False, False],
        )


def test_delaware_person_inputs_and_raw_relation_cover_all_selected_members() -> None:
    prefix = "us-de:policies/income_tax/pilot_liability_pipeline"
    separate_slot = f"{prefix}#input.de_pit_pilot_supplied_separate_taxable_income"
    included_slot = f"{prefix}#input.de_pit_pilot_taxpayer_is_included"
    combined_slot = f"{prefix}#input.de_pit_pilot_supplied_combined_taxable_income"
    files_separately_slot = f"{prefix}#input.de_pit_pilot_files_separately"
    relation = f"{prefix}#relation.de_pit_pilot_taxpayer_of_tax_unit"
    interval = {
        "period_kind": "tax_year",
        "start": "2026-01-01",
        "end": "2026-12-31",
    }

    request = state_tax_runner._state_request(
        state="DE",
        routes=(TaxUnitRoute(2, 2, "DE", "10", 1, DISPOSITION_READY),),
        year=2026,
        output=f"{prefix}#de_pit_pilot_income_tax_liability",
        projected_inputs={
            separate_slot: {11: 1_000.0, 21: 20_000.0, 22: 30_000.0, 31: 4_000.0},
            included_slot: {11: True, 21: True, 22: False, 31: True},
            combined_slot: {1: 1_000.0, 2: 50_000.0, 3: 4_000.0},
            files_separately_slot: {1: False, 2: True, 3: False},
        },
        declared_relations=(relation,),
        raw_persons=pd.DataFrame(
            {
                "person_id": [11, 21, 22, 31],
                "person_tax_unit_id": [1, 2, 2, 3],
            }
        ),
        all_tax_unit_ids={1, 2, 3},
    )

    assert request["dataset"]["inputs"] == [
        {
            "name": files_separately_slot,
            "entity": "Entity",
            "entity_id": "state-tax-unit-2",
            "interval": interval,
            "value": {"kind": "bool", "value": True},
        },
        {
            "name": combined_slot,
            "entity": "Entity",
            "entity_id": "state-tax-unit-2",
            "interval": interval,
            "value": {"kind": "decimal", "value": "50000.0"},
        },
        {
            "name": separate_slot,
            "entity": "Entity",
            "entity_id": "state-tax-person-21",
            "interval": interval,
            "value": {"kind": "decimal", "value": "20000.0"},
        },
        {
            "name": included_slot,
            "entity": "Entity",
            "entity_id": "state-tax-person-21",
            "interval": interval,
            "value": {"kind": "bool", "value": True},
        },
        {
            "name": separate_slot,
            "entity": "Entity",
            "entity_id": "state-tax-person-22",
            "interval": interval,
            "value": {"kind": "decimal", "value": "30000.0"},
        },
        {
            "name": included_slot,
            "entity": "Entity",
            "entity_id": "state-tax-person-22",
            "interval": interval,
            "value": {"kind": "bool", "value": False},
        },
    ]
    assert request["dataset"]["relations"] == [
        {
            "name": relation,
            "tuple": ["state-tax-person-21", "state-tax-unit-2"],
            "interval": interval,
        },
        {
            "name": relation,
            "tuple": ["state-tax-person-22", "state-tax-unit-2"],
            "interval": interval,
        },
    ]


def test_filtered_delaware_comparison_preserves_national_tax_unit_universe(
    monkeypatch, tmp_path
) -> None:
    prefix = "us-de:policies/income_tax/pilot_liability_pipeline"
    separate_slot = f"{prefix}#input.de_pit_pilot_supplied_separate_taxable_income"
    included_slot = f"{prefix}#input.de_pit_pilot_taxpayer_is_included"
    combined_slot = f"{prefix}#input.de_pit_pilot_supplied_combined_taxable_income"
    files_separately_slot = f"{prefix}#input.de_pit_pilot_files_separately"
    relation_slot = f"{prefix}#relation.de_pit_pilot_taxpayer_of_tax_unit"
    relation = SimpleNamespace(
        slot=relation_slot,
        source_kind="raw_populace",
        status="ready",
        policyengine_variable=None,
        policyengine_variables=(),
        policyengine_relationship=None,
        policyengine_transform=None,
        constant_value=None,
    )
    jurisdiction = SimpleNamespace(
        inputs=tuple(
            SimpleNamespace(slot=slot)
            for slot in (
                separate_slot,
                included_slot,
                combined_slot,
                files_separately_slot,
            )
        ),
        relations=(relation,),
        output=f"{prefix}#de_pit_pilot_income_tax_liability",
        program="us-de:policies/income_tax/pilot_liability_pipeline",
        tolerance=0.01,
        relative_tolerance=1e-7,
        policyengine_target="de_income_tax_before_non_refundable_credits_unit",
    )
    contract = SimpleNamespace(
        validation_year=2026,
        by_state=lambda: {"DE": jurisdiction},
    )
    monkeypatch.setattr(
        state_tax_runner, "validate_state_tax_populace_contract", lambda value: value
    )
    calls = []

    def fake_axiom_runner(**kwargs):
        calls.append(kwargs["request"])
        return [
            {
                "entity_id": "state-tax-unit-1",
                "outputs": {
                    jurisdiction.output: {"value": {"value": "0"}}
                },
            }
        ]

    common = {
        "routes": (TaxUnitRoute(1, 1, "DE", "10", 1, DISPOSITION_READY),),
        "raw_persons": pd.DataFrame(
            {
                "person_id": [11, 21],
                "person_tax_unit_id": [1, 2],
            }
        ),
        "known_tax_unit_ids": {1, 2},
        "policyengine_targets": {"DE": {1: 0.0}},
        "policyengine_projection_inputs": {
            "DE": {
                separate_slot: {11: 0.0, 21: 0.0},
                included_slot: {11: True, 21: True},
                combined_slot: {1: 0.0, 2: 0.0},
                files_separately_slot: {1: False, 2: False},
            }
        },
        "year": 2026,
        "rulespec_root": tmp_path / "rulespec-us",
        "axiom_rules_path": tmp_path / "axiom-rules-engine",
        "contract": contract,
        "axiom_runner": fake_axiom_runner,
    }
    report = compare_ready_state_tax_units(**common)

    assert report["compared_count"] == 1
    assert calls[0]["dataset"]["relations"] == [
        {
            "name": relation_slot,
            "tuple": ["state-tax-person-11", "state-tax-unit-1"],
            "interval": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
        }
    ]

    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="DE: Populace people link to unknown tax_unit_id values: 99",
    ):
        compare_ready_state_tax_units(
            **{
                **common,
                "raw_persons": pd.DataFrame(
                    {
                        "person_id": [11, 21, 99],
                        "person_tax_unit_id": [1, 2, 99],
                    }
                ),
            }
        )


def test_person_request_rejects_unknown_tax_unit_links_with_state() -> None:
    prefix = "us-de:policies/income_tax/pilot_liability_pipeline"
    slot = f"{prefix}#input.de_pit_pilot_supplied_separate_taxable_income"
    relation = f"{prefix}#relation.de_pit_pilot_taxpayer_of_tax_unit"
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="DE: Populace people link to unknown tax_unit_id values: 99",
    ):
        state_tax_runner._state_request(
            state="DE",
            routes=(TaxUnitRoute(2, 2, "DE", "10", 1, DISPOSITION_READY),),
            year=2026,
            output=f"{prefix}#de_pit_pilot_income_tax_liability",
            projected_inputs={slot: {21: 10_000.0}},
            declared_relations=(relation,),
            raw_persons=pd.DataFrame(
                {"person_id": [21, 99], "person_tax_unit_id": [2, 99]}
            ),
            all_tax_unit_ids={1, 2, 3},
        )


def test_person_inputs_never_create_an_implicit_generic_relation() -> None:
    prefix = "us-de:policies/income_tax/pilot_liability_pipeline"
    slot = f"{prefix}#input.de_pit_pilot_supplied_separate_taxable_income"
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="DE: reviewed Person inputs require an explicitly declared",
    ):
        state_tax_runner._state_request(
            state="DE",
            routes=(TaxUnitRoute(2, 2, "DE", "10", 1, DISPOSITION_READY),),
            year=2026,
            output=f"{prefix}#de_pit_pilot_income_tax_liability",
            projected_inputs={slot: {21: 10_000.0}},
            raw_persons=pd.DataFrame(
                {"person_id": [21], "person_tax_unit_id": [2]}
            ),
            all_tax_unit_ids={2},
        )


def test_runtime_relations_require_exact_state_allowlist() -> None:
    class Relation:
        slot = "us-de:policies/income_tax/pilot_liability_pipeline#relation.other"
        source_kind = "raw_populace"
        status = "ready"
        policyengine_variable = None
        policyengine_variables = ()
        policyengine_relationship = None
        policyengine_transform = None
        constant_value = None

    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="DE: declared relation inventory contains no exact runtime projector",
    ):
        state_tax_runner._validate_runtime_relations(
            state="DE", relations=(Relation(),)
        )


@pytest.mark.parametrize("value", ["WIDOW", "joint", 1, None])
def test_oklahoma_filing_status_projection_rejects_unknown_values(value) -> None:
    slot = (
        "us-ok:policies/income_tax/pilot_liability_pipeline#input."
        "ok_pit_pilot_filing_status_uses_wide_schedule"
    )
    with pytest.raises(StateTaxPopulationRoutingError, match="unsupported value"):
        state_tax_runner._apply_projection_transform(
            value,
            transform="filing_status_joint_surviving_spouse_or_head",
            label=slot,
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("SINGLE", False),
        ("JOINT", False),
        ("SEPARATE", True),
        ("HEAD_OF_HOUSEHOLD", False),
        ("SURVIVING_SPOUSE", False),
    ],
)
def test_married_separate_filing_status_projection(value, expected) -> None:
    assert (
        state_tax_runner._apply_projection_transform(
            value,
            transform="filing_status_is_separate",
            label="filing status",
        )
        is expected
    )


@pytest.mark.parametrize("value", [-1.0, 0.5, 2.0])
def test_virginia_boolean_projection_rejects_non_binary_values(value) -> None:
    slot = (
        "us-va:policies/income_tax/pilot_liability_pipeline#input."
        "va_pit_pilot_must_file"
    )
    with pytest.raises(StateTaxPopulationRoutingError, match="exactly zero or one"):
        state_tax_runner._apply_projection_transform(
            value,
            transform="zero_one_to_boolean",
            label=slot,
        )


def test_ready_ut_comparison_projects_exact_declared_input(tmp_path) -> None:
    slot = (
        "us-ut:policies/income_tax/pilot_liability_pipeline#input."
        "ut_pit_pilot_state_taxable_income"
    )
    routes = (TaxUnitRoute(9, 1, "UT", "49", 3.0, DISPOSITION_READY),)
    calls = []

    def fake_axiom_runner(**kwargs):
        calls.append(kwargs)
        query = kwargs["request"]["queries"][0]
        output = query["outputs"][0]
        return [
            {
                "entity_id": query["entity_id"],
                "outputs": {output: {"value": {"value": "445"}}},
            }
        ]

    report = compare_ready_state_tax_units(
        routes=routes,
        policyengine_targets={"UT": {9: 445.0}},
        policyengine_projection_inputs={"UT": {slot: {9: 10000.0}}},
        year=2026,
        rulespec_root=tmp_path / "rulespec-us",
        axiom_rules_path=tmp_path / "axiom-rules",
        axiom_runner=fake_axiom_runner,
    )

    assert report["mismatch_count"] == 0
    assert calls[0]["request"]["dataset"]["inputs"] == [
        {
            "name": slot,
            "entity": "Entity",
            "entity_id": "state-tax-unit-9",
            "interval": {
                "period_kind": "tax_year",
                "start": "2026-01-01",
                "end": "2026-12-31",
            },
            "value": {"kind": "decimal", "value": "10000.0"},
        }
    ]


def test_ready_kansas_comparison_preserves_boolean_input_kind(tmp_path) -> None:
    prefix = "us-ks:policies/income_tax/pilot_liability_pipeline#input."
    taxable_slot = f"{prefix}ks_pit_pilot_state_taxable_income"
    joint_slot = f"{prefix}ks_pit_pilot_filing_status_joint"
    routes = (TaxUnitRoute(9, 1, "KS", "20", 3.0, DISPOSITION_READY),)
    calls = []

    def fake_axiom_runner(**kwargs):
        calls.append(kwargs)
        query = kwargs["request"]["queries"][0]
        output = query["outputs"][0]
        return [
            {
                "entity_id": query["entity_id"],
                "outputs": {output: {"value": {"value": "0"}}},
            }
        ]

    report = compare_ready_state_tax_units(
        routes=routes,
        policyengine_targets={"KS": {9: 0.0}},
        policyengine_projection_inputs={
            "KS": {taxable_slot: {9: 0.0}, joint_slot: {9: True}}
        },
        year=2026,
        rulespec_root=tmp_path / "rulespec-us",
        axiom_rules_path=tmp_path / "axiom-rules",
        axiom_runner=fake_axiom_runner,
    )

    assert report["mismatch_count"] == 0
    inputs = calls[0]["request"]["dataset"]["inputs"]
    assert next(item for item in inputs if item["name"] == joint_slot)["value"] == {
        "kind": "bool",
        "value": True,
    }


def test_ready_ut_comparison_rejects_missing_projection_input(tmp_path) -> None:
    routes = (TaxUnitRoute(9, 1, "UT", "49", 3.0, DISPOSITION_READY),)

    with pytest.raises(
        StateTaxPopulationRoutingError, match="projected input inventory mismatch"
    ):
        compare_ready_state_tax_units(
            routes=routes,
            policyengine_targets={"UT": {9: 445.0}},
            policyengine_projection_inputs={"UT": {}},
            year=2026,
            rulespec_root=tmp_path / "rulespec-us",
            axiom_rules_path=tmp_path / "axiom-rules",
            axiom_runner=lambda **_: [],
        )


def test_ready_ut_comparison_rejects_extra_projection_input(tmp_path) -> None:
    slot = (
        "us-ut:policies/income_tax/pilot_liability_pipeline#input."
        "ut_pit_pilot_state_taxable_income"
    )
    routes = (TaxUnitRoute(9, 1, "UT", "49", 3.0, DISPOSITION_READY),)

    with pytest.raises(
        StateTaxPopulationRoutingError,
        match=r"UT: projected input inventory mismatch; missing=\[\], extra=",
    ):
        compare_ready_state_tax_units(
            routes=routes,
            policyengine_targets={"UT": {9: 445.0}},
            policyengine_projection_inputs={
                "UT": {slot: {9: 10_000.0}, f"{slot}_unexpected": {9: 0.0}}
            },
            year=2026,
            rulespec_root=tmp_path / "rulespec-us",
            axiom_rules_path=tmp_path / "axiom-rules",
            axiom_runner=lambda **_: [],
        )


def test_ready_comparison_attributes_axiom_failures_to_state(tmp_path) -> None:
    slot = (
        "us-ut:policies/income_tax/pilot_liability_pipeline#input."
        "ut_pit_pilot_state_taxable_income"
    )
    routes = (TaxUnitRoute(9, 1, "UT", "49", 3.0, DISPOSITION_READY),)

    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="UT: Axiom execution failed: bad input type",
    ):
        compare_ready_state_tax_units(
            routes=routes,
            policyengine_targets={"UT": {9: 445.0}},
            policyengine_projection_inputs={"UT": {slot: {9: 10_000.0}}},
            year=2026,
            rulespec_root=tmp_path / "rulespec-us",
            axiom_rules_path=tmp_path / "axiom-rules-engine",
            axiom_runner=lambda **_: (_ for _ in ()).throw(
                SystemExit("bad input type")
            ),
        )


def test_campaign_dataset_identity_requires_the_certified_pin() -> None:
    identity = {
        "source": "pinned",
        "country": "us",
        "revision": "populace-us-2024-f0af251-703bd81a565c-20260620T201958Z",
        "sha256": "16be6338f9d0",
        "built_with": "1.729.0",
    }
    validate_campaign_dataset_identity(identity)

    with pytest.raises(StateTaxPopulationRoutingError, match="not certified"):
        validate_campaign_dataset_identity({**identity, "source": "local-override"})


@pytest.mark.parametrize(
    "remote",
    [
        "https://github.com/TheAxiomFoundation/rulespec-us.git",
        "git@github.com:TheAxiomFoundation/rulespec-us.git",
        "ssh://git@github.com/TheAxiomFoundation/rulespec-us.git",
    ],
)
def test_official_github_remote_accepts_exact_https_and_ssh(remote: str) -> None:
    assert _is_official_github_remote(
        remote, "TheAxiomFoundation/rulespec-us"
    )


@pytest.mark.parametrize(
    "remote",
    [
        "https://attacker.example/TheAxiomFoundation/rulespec-us.git",
        "/tmp/TheAxiomFoundation/rulespec-us.git",
        "https://github.com/attacker/rulespec-us.git",
    ],
)
def test_official_github_remote_rejects_lookalikes(remote: str) -> None:
    assert not _is_official_github_remote(
        remote, "TheAxiomFoundation/rulespec-us"
    )


def test_runtime_provenance_uses_canonical_engine_repository(
    tmp_path, monkeypatch
) -> None:
    rulespec_root = tmp_path / "rulespec-us"
    engine_root = tmp_path / "axiom-rules-engine"
    binary = engine_root / "target" / "release" / "axiom-rules-engine"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"engine")
    calls = []

    def fake_clean_git_commit(path, *, expected_github_repository):
        calls.append((path, expected_github_repository))
        return "a" * 40

    monkeypatch.setattr(
        state_tax_runner, "_clean_git_commit", fake_clean_git_commit
    )
    monkeypatch.setattr(state_tax_runner, "_file_sha256", lambda _: "b" * 64)
    monkeypatch.setattr(state_tax_runner, "_package_version", lambda _: "1.0")

    provenance = state_tax_runner.runtime_provenance(
        rulespec_root=rulespec_root,
        axiom_rules_path=engine_root,
    )

    assert calls == [
        (rulespec_root, "TheAxiomFoundation/rulespec-us"),
        (engine_root, "TheAxiomFoundation/axiom-rules-engine"),
    ]
    assert provenance["axiom_engine"]["repository"] == (
        "TheAxiomFoundation/axiom-rules-engine"
    )


def test_ready_comparison_rejects_a_different_policy_year(tmp_path) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match="must be 2026"):
        compare_ready_state_tax_units(
            routes=(),
            policyengine_targets={},
            year=2025,
            rulespec_root=tmp_path,
            axiom_rules_path=tmp_path,
        )
