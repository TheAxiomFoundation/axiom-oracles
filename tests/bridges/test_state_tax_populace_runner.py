from __future__ import annotations

import pandas as pd
import pytest

from axiom_oracles.bridges.state_tax_populace_runner import (
    DISPOSITION_BLOCKED,
    DISPOSITION_NO_BROAD_PIT,
    DISPOSITION_NONPOSITIVE_WEIGHT,
    DISPOSITION_READY,
    StateTaxPopulationRoutingError,
    TaxUnitRoute,
    _is_official_github_remote,
    calculate_policyengine_targets,
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


def test_ready_comparison_rejects_a_different_policy_year(tmp_path) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match="must be 2026"):
        compare_ready_state_tax_units(
            routes=(),
            policyengine_targets={},
            year=2025,
            rulespec_root=tmp_path,
            axiom_rules_path=tmp_path,
        )
