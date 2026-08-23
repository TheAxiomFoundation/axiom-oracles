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

_UT_PREFIX = (
    "us-ut:policies/income_tax/"
    "2026_full_year_resident_before_credit_schedule#input."
)
_UT_TAXABLE_SLOT = f"{_UT_PREFIX}ut_pit_2026_state_taxable_income"
_UT_RESIDENT_SLOT = (
    f"{_UT_PREFIX}ut_pit_2026_is_full_year_utah_resident_return"
)
_UT_ALIGNED_SLOT = (
    f"{_UT_PREFIX}ut_pit_2026_federal_and_utah_filing_units_are_aligned"
)
_UT_EXEMPT_SLOT = (
    f"{_UT_PREFIX}ut_pit_2026_is_exempt_under_section_59_10_104_1"
)


def _ut_inputs(
    taxable: dict,
    *,
    resident: dict | None = None,
    aligned: dict | None = None,
    exempt: dict | None = None,
) -> dict:
    ids = taxable.keys()
    return {
        _UT_TAXABLE_SLOT: taxable,
        _UT_RESIDENT_SLOT: resident or {item: True for item in ids},
        _UT_ALIGNED_SLOT: aligned or {item: True for item in ids},
        _UT_EXEMPT_SLOT: exempt or {item: False for item in ids},
    }


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
            "state_fips": [17, 6, 48, 36],
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
    assert by_id[10].state == "IL"
    assert by_id[10].weight == 2.5
    assert by_id[10].disposition == DISPOSITION_READY
    assert by_id[20].disposition == DISPOSITION_READY
    assert by_id[30].disposition == DISPOSITION_NO_BROAD_PIT
    assert by_id[40].disposition == DISPOSITION_NONPOSITIVE_WEIGHT


def test_new_hampshire_routes_as_no_current_broad_pit() -> None:
    tax_units, persons, households = _frames()
    households.loc[households["household_id"] == 1, "state_fips"] = 33

    routes = route_tax_units(
        raw_tax_units=tax_units,
        raw_persons=persons,
        raw_households=households,
    )

    nh_route = next(route for route in routes if route.tax_unit_id == 10)
    assert nh_route.state == "NH"
    assert nh_route.disposition == DISPOSITION_NO_BROAD_PIT


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
        TaxUnitRoute(9, 1, "IL", "17", 1, DISPOSITION_READY),
        TaxUnitRoute(2, 2, "IL", "17", 1, DISPOSITION_READY),
        TaxUnitRoute(7, 3, "CA", "06", 1, DISPOSITION_READY),
        TaxUnitRoute(1, 4, "CA", "06", 1, DISPOSITION_BLOCKED),
        TaxUnitRoute(3, 5, "TX", "48", 1, DISPOSITION_NO_BROAD_PIT),
    )

    selected = select_ready_tax_units(routes, sample_size_per_state=1)

    assert [(route.state, route.tax_unit_id) for route in selected] == [
        ("CA", 7),
        ("IL", 2),
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
    assert report["selected_ready_count"] == 2
    assert report["eligible_ready_count"] == 2
    assert report["excluded_count"] == 2
    assert report["weighted_eligible_ready_tax_units"] == 5.5
    assert report["weighted_excluded_tax_units"] == 4
    assert report["weighted_dispositions"] == {
        DISPOSITION_READY: 5.5,
        DISPOSITION_NO_BROAD_PIT: 4,
        DISPOSITION_NONPOSITIVE_WEIGHT: 0,
    }
    assert report["errored_count"] == 0
    assert report["states"]["IL"]["selected_count"] == 1
    assert report["states"]["CA"]["dispositions"] == {DISPOSITION_READY: 1}
    assert report["states"]["TX"]["dispositions"] == {
        DISPOSITION_NO_BROAD_PIT: 1
    }
    assert report["unknown_geography"]["tax_unit_count"] == 0


def test_ready_comparison_runs_one_compiled_state_batch(tmp_path) -> None:
    routes = (
        TaxUnitRoute(2, 1, "UT", "49", 2.5, DISPOSITION_READY),
        TaxUnitRoute(5, 2, "UT", "49", 3.5, DISPOSITION_READY),
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
        policyengine_targets={"UT": {2: 0.0, 5: 0.0}},
        policyengine_projection_inputs={
            "UT": _ut_inputs({2: 0.0, 5: 0.0})
        },
        year=2026,
        rulespec_root=tmp_path / "rulespec-us",
        axiom_rules_path=tmp_path / "axiom-rules",
        axiom_runner=fake_axiom_runner,
    )

    assert report["ready_state_count"] == 1
    assert report["compared_count"] == 2
    assert report["mismatch_count"] == 0
    assert report["states"]["UT"]["weighted_compared_tax_units"] == 6
    assert len(calls) == 1
    assert len(calls[0]["request"]["queries"]) == 2


def test_policyengine_target_calculation_is_limited_to_ready_states() -> None:
    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"
            self.calls = []

        def calculate(self, variable, period):
            self.calls.append((variable, period))
            if variable == "ut_income_tax_exempt":
                return [False, True]
            return [100, 200]

    routes = (
        TaxUnitRoute(1, 1, "UT", "49", 1, DISPOSITION_READY),
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

    assert targets == {"UT": {1: 100.0, 2: 0.0}}


def test_utah_target_rejects_non_boolean_exemption() -> None:
    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"

        def calculate(self, variable, period):
            return (
                [100.0]
                if variable == "ut_income_tax_before_credits"
                else [1.0]
            )

    routes = (TaxUnitRoute(1, 1, "UT", "49", 1, DISPOSITION_READY),)
    raw_tax_units = pd.DataFrame({"tax_unit_id": [1]})
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="ut_income_tax_exempt: expected a PolicyEngine boolean",
    ):
        calculate_policyengine_targets(
            dataset="dataset",
            raw_tax_units=raw_tax_units,
            routes=routes,
            year=2026,
            microsimulation_factory=FakeSimulation,
        )


def test_utah_target_rejects_mismatched_component_cardinality() -> None:
    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"

        def calculate(self, variable, period):
            return (
                [100.0, 200.0]
                if variable == "ut_income_tax_before_credits"
                else [False]
            )

    routes = (TaxUnitRoute(1, 1, "UT", "49", 1, DISPOSITION_READY),)
    raw_tax_units = pd.DataFrame({"tax_unit_id": [1, 2]})
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="UT: PolicyEngine exemption-aware target inputs returned 2 and 1",
    ):
        calculate_policyengine_targets(
            dataset="dataset",
            raw_tax_units=raw_tax_units,
            routes=routes,
            year=2026,
            microsimulation_factory=FakeSimulation,
        )


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (float("nan"), "returned non-finite"),
        (float("inf"), "returned non-finite"),
        (-0.01, "must be nonnegative"),
    ],
)
def test_utah_target_rejects_invalid_before_credit_amount(value, message) -> None:
    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"

        def calculate(self, variable, period):
            return (
                [value]
                if variable == "ut_income_tax_before_credits"
                else [False]
            )

    routes = (TaxUnitRoute(1, 1, "UT", "49", 1, DISPOSITION_READY),)
    raw_tax_units = pd.DataFrame({"tax_unit_id": [1]})
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        calculate_policyengine_targets(
            dataset="dataset",
            raw_tax_units=raw_tax_units,
            routes=routes,
            year=2026,
            microsimulation_factory=FakeSimulation,
        )


def _ca_simulation(
    *,
    ids=(1, 2, 3),
    tax=(0.0, 0.01, 10_000.0),
):
    calls = []

    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"

        def calculate(self, variable, period):
            assert period == 2026
            self.calls.append((variable, period))
            return {
                "tax_unit_id": ids,
                "ca_mental_health_services_tax": tax,
            }[variable]

    FakeSimulation.calls = calls
    return FakeSimulation


def _ca_targets(
    microsimulation_factory,
    *,
    source_ids=(1, 2, 3),
) -> dict[str, dict[int, float]]:
    return calculate_policyengine_targets(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": source_ids}),
        routes=tuple(
            TaxUnitRoute(index, index, "CA", "06", 1, DISPOSITION_READY)
            for index in source_ids
        ),
        year=2026,
        microsimulation_factory=microsimulation_factory,
    )


def test_california_target_preserves_direct_bhst_values_only() -> None:
    simulation = _ca_simulation()

    assert _ca_targets(simulation) == {
        "CA": {1: 0.0, 2: 0.01, 3: 10_000.0}
    }
    assert simulation.calls == [
        ("tax_unit_id", 2026),
        ("ca_mental_health_services_tax", 2026),
    ]
    assert all(
        variable != "ca_income_tax_before_refundable_credits"
        for variable, _ in simulation.calls
    )


def test_california_target_preserves_all_8883_routed_tax_units() -> None:
    ids = tuple(range(1, 8_884))
    tax = tuple(0.0 if index <= 7_677 else float(index) for index in ids)

    targets = _ca_targets(
        _ca_simulation(ids=ids, tax=tax),
        source_ids=ids,
    )

    assert len(targets["CA"]) == 8_883
    assert tuple(targets["CA"]) == ids
    assert sum(value == 0 for value in targets["CA"].values()) == 7_677
    assert sum(value > 0 for value in targets["CA"].values()) == 1_206


@pytest.mark.parametrize(
    ("ids", "tax", "message"),
    [
        ((1, 2), (0.0, 0.01, 10_000.0), "returned 2 IDs and 3 values"),
        ((1, 2, 3), (0.0, 0.01), "returned 3 IDs and 2 values"),
        ((2, 1, 3), (0.0, 0.01, 10_000.0), "order does not match"),
        ((1, 1, 3), (0.0, 0.01, 10_000.0), "duplicate CA PolicyEngine"),
    ],
)
def test_california_target_rejects_entity_identity_and_cardinality_defects(
    ids,
    tax,
    message,
) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _ca_targets(_ca_simulation(ids=ids, tax=tax))


def test_california_target_rejects_duplicate_source_entity_ids() -> None:
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="duplicate CA source tax_unit_id",
    ):
        _ca_targets(
            _ca_simulation(ids=(1, 1, 3)),
            source_ids=(1, 1, 3),
        )


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (float("nan"), "non-finite"),
        (float("inf"), "non-finite"),
        (-0.01, "must be nonnegative"),
    ],
)
def test_california_target_rejects_invalid_bhst_amount(value, message) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _ca_targets(_ca_simulation(tax=(0.0, value, 10_000.0)))


def _ny_simulation(
    *,
    ids=(1, 2, 3),
    tax=(0.0, 1_000.0, 250_000.0),
):
    calls = []

    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"

        def calculate(self, variable, period):
            assert period == 2026
            self.calls.append((variable, period))
            return {
                "tax_unit_id": ids,
                "ny_main_income_tax": tax,
            }[variable]

    FakeSimulation.calls = calls
    return FakeSimulation


def _ny_targets(
    microsimulation_factory,
    *,
    source_ids=(1, 2, 3),
) -> dict[str, dict[int, float]]:
    return calculate_policyengine_targets(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": source_ids}),
        routes=tuple(
            TaxUnitRoute(index, index, "NY", "36", 1, DISPOSITION_READY)
            for index in source_ids
        ),
        year=2026,
        microsimulation_factory=microsimulation_factory,
    )


def test_new_york_target_preserves_only_exact_main_schedule_values() -> None:
    simulation = _ny_simulation()

    assert _ny_targets(simulation) == {
        "NY": {1: 0.0, 2: 1_000.0, 3: 250_000.0}
    }
    assert simulation.calls == [
        ("tax_unit_id", 2026),
        ("ny_main_income_tax", 2026),
    ]
    assert all(
        variable not in {"ny_income_tax", "ny_state_income_tax"}
        for variable, _ in simulation.calls
    )


def test_new_york_target_preserves_all_3741_routed_tax_units() -> None:
    ids = tuple(range(1, 3_742))
    tax = tuple(0.0 if index <= 1_000 else float(index) for index in ids)

    targets = _ny_targets(
        _ny_simulation(ids=ids, tax=tax),
        source_ids=ids,
    )

    assert len(targets["NY"]) == 3_741
    assert tuple(targets["NY"]) == ids
    assert sum(value == 0 for value in targets["NY"].values()) == 1_000
    assert sum(value > 0 for value in targets["NY"].values()) == 2_741


@pytest.mark.parametrize(
    ("ids", "tax", "message"),
    [
        ((1, 2), (0.0, 1_000.0, 250_000.0), "returned 2 IDs and 3 values"),
        ((1, 2, 3), (0.0, 1_000.0), "returned 3 IDs and 2 values"),
        ((2, 1, 3), (0.0, 1_000.0, 250_000.0), "order does not match"),
        (
            (1, 1, 3),
            (0.0, 1_000.0, 250_000.0),
            "duplicate NY PolicyEngine",
        ),
    ],
)
def test_new_york_target_rejects_entity_identity_and_cardinality_defects(
    ids,
    tax,
    message,
) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _ny_targets(_ny_simulation(ids=ids, tax=tax))


def test_new_york_target_rejects_duplicate_source_entity_ids() -> None:
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="duplicate NY source tax_unit_id",
    ):
        _ny_targets(
            _ny_simulation(ids=(1, 1, 3)),
            source_ids=(1, 1, 3),
        )


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (float("nan"), "non-finite"),
        (float("inf"), "non-finite"),
        (-0.01, "must be nonnegative"),
    ],
)
def test_new_york_target_rejects_invalid_main_schedule_amount(
    value,
    message,
) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _ny_targets(_ny_simulation(tax=(0.0, value, 250_000.0)))


def test_new_york_target_rejects_broad_liability_contract_drift(
    monkeypatch,
) -> None:
    drifted_contract = SimpleNamespace(
        validation_year=2026,
        by_state=lambda: {
            "NY": SimpleNamespace(policyengine_target="ny_income_tax")
        },
    )
    monkeypatch.setattr(
        state_tax_runner,
        "validate_state_tax_populace_contract",
        lambda _contract: drifted_contract,
    )

    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="requires the exact ny_main_income_tax target",
    ):
        calculate_policyengine_targets(
            dataset="dataset",
            raw_tax_units=pd.DataFrame({"tax_unit_id": [1]}),
            routes=(
                TaxUnitRoute(1, 1, "NY", "36", 1, DISPOSITION_READY),
            ),
            year=2026,
            contract=drifted_contract,
            microsimulation_factory=_ny_simulation(
                ids=(1,),
                tax=(0.0,),
            ),
        )


def _reviewed_money_schema(*variables: str):
    return SimpleNamespace(
        variables={
            variable: SimpleNamespace(
                entity=SimpleNamespace(key="tax_unit"),
                definition_period="year",
                value_type=float,
                unit="currency-USD",
            )
            for variable in variables
        }
    )


def _il_simulation(
    *,
    ids=(1, 2, 3),
    tax=(0.0, 1_000.0, 250_000.0),
    schema=None,
):
    calls = []

    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"
            self.tax_benefit_system = schema or _reviewed_money_schema(
                "il_income_tax_before_non_refundable_credits"
            )

        def calculate(self, variable, period):
            assert period == 2026
            self.calls.append((variable, period))
            return {
                "tax_unit_id": ids,
                "il_income_tax_before_non_refundable_credits": tax,
            }[variable]

    FakeSimulation.calls = calls
    return FakeSimulation


def _il_targets(
    microsimulation_factory,
    *,
    source_ids=(1, 2, 3),
) -> dict[str, dict[int, float]]:
    return calculate_policyengine_targets(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": source_ids}),
        routes=tuple(
            TaxUnitRoute(index, index, "IL", "17", 1, DISPOSITION_READY)
            for index in source_ids
        ),
        year=2026,
        microsimulation_factory=microsimulation_factory,
    )


def test_illinois_target_preserves_only_exact_before_credit_values() -> None:
    simulation = _il_simulation()

    assert _il_targets(simulation) == {
        "IL": {1: 0.0, 2: 1_000.0, 3: 250_000.0}
    }
    assert simulation.calls == [
        ("tax_unit_id", 2026),
        ("il_income_tax_before_non_refundable_credits", 2026),
    ]
    assert all(
        variable not in {"il_income_tax", "il_tax_before_refundable_credits"}
        for variable, _ in simulation.calls
    )


def test_illinois_target_preserves_all_2332_routed_tax_units() -> None:
    ids = tuple(range(1, 2_333))
    tax = tuple(0.0 if index <= 500 else float(index) for index in ids)

    targets = _il_targets(
        _il_simulation(ids=ids, tax=tax),
        source_ids=ids,
    )

    assert len(targets["IL"]) == 2_332
    assert tuple(targets["IL"]) == ids
    assert sum(value == 0 for value in targets["IL"].values()) == 500
    assert sum(value > 0 for value in targets["IL"].values()) == 1_832


@pytest.mark.parametrize(
    ("ids", "tax", "message"),
    [
        ((1, 2), (0.0, 1_000.0, 250_000.0), "returned 2 IDs and 3 values"),
        ((1, 2, 3), (0.0, 1_000.0), "returned 3 IDs and 2 values"),
        ((2, 1, 3), (0.0, 1_000.0, 250_000.0), "order does not match"),
        (
            (1, 1, 3),
            (0.0, 1_000.0, 250_000.0),
            "duplicate IL PolicyEngine",
        ),
    ],
)
def test_illinois_target_rejects_identity_and_cardinality_defects(
    ids,
    tax,
    message,
) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _il_targets(_il_simulation(ids=ids, tax=tax))


def test_illinois_target_rejects_duplicate_source_entity_ids() -> None:
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="duplicate IL source tax_unit_id",
    ):
        _il_targets(
            _il_simulation(ids=(1, 1, 3)),
            source_ids=(1, 1, 3),
        )


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (float("nan"), "non-finite"),
        (float("inf"), "non-finite"),
        (-0.01, "must be nonnegative"),
    ],
)
def test_illinois_target_rejects_invalid_before_credit_amount(
    value,
    message,
) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _il_targets(_il_simulation(tax=(0.0, value, 250_000.0)))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("entity", SimpleNamespace(key="person")),
        ("definition_period", "month"),
        ("value_type", int),
        ("unit", "USD"),
    ],
)
def test_illinois_target_rejects_schema_drift(field, value) -> None:
    definition = SimpleNamespace(
        entity=SimpleNamespace(key="tax_unit"),
        definition_period="year",
        value_type=float,
        unit="currency-USD",
    )
    setattr(definition, field, value)
    schema = SimpleNamespace(
        variables={
            "il_income_tax_before_non_refundable_credits": definition
        }
    )

    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="TaxUnit/year/currency-USD float schema",
    ):
        _il_targets(_il_simulation(schema=schema))


def test_illinois_target_rejects_broader_contract_drift(monkeypatch) -> None:
    drifted_contract = SimpleNamespace(
        validation_year=2026,
        by_state=lambda: {
            "IL": SimpleNamespace(
                policyengine_target="il_income_tax",
            )
        },
    )
    monkeypatch.setattr(
        state_tax_runner,
        "validate_state_tax_populace_contract",
        lambda _contract: drifted_contract,
    )

    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="requires the exact il_income_tax_before_non_refundable_credits",
    ):
        calculate_policyengine_targets(
            dataset="dataset",
            raw_tax_units=pd.DataFrame({"tax_unit_id": [1]}),
            routes=(
                TaxUnitRoute(1, 1, "IL", "17", 1, DISPOSITION_READY),
            ),
            year=2026,
            contract=drifted_contract,
            microsimulation_factory=_il_simulation(
                ids=(1,),
                tax=(0.0,),
            ),
        )


def _mn_simulation(
    *,
    ids=(1, 2, 3),
    tax=(0.0, 1_100.0, 7_400.0),
    taxable_income=(0.0, 20_000.0, 100_000.0),
    filing_status=("SINGLE", "JOINT", "HEAD_OF_HOUSEHOLD"),
    scale_thresholds=(0.0, 10_000.0, 20_000.0, 30_000.0),
    scale_rates=(0.05, 0.06, 0.07, 0.08),
    variable_name="mn_basic_tax",
    variable_entity="tax_unit",
    variable_period="year",
    variable_value_type=float,
):
    calls = []

    scale = SimpleNamespace(
        thresholds=scale_thresholds,
        rates=scale_rates,
    )
    rates_node = SimpleNamespace(
        single=scale,
        separate=scale,
        joint=scale,
        surviving_spouse=scale,
        head_of_household=scale,
    )
    variable = SimpleNamespace(
        name=variable_name,
        entity=SimpleNamespace(key=variable_entity),
        definition_period=variable_period,
        value_type=variable_value_type,
        formulas={"0001-01-01": object()},
    )

    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"
            self.tax_benefit_system = SimpleNamespace(
                variables={"mn_basic_tax": variable},
                parameters=lambda year: SimpleNamespace(
                    gov=SimpleNamespace(
                        states=SimpleNamespace(
                            mn=SimpleNamespace(
                                tax=SimpleNamespace(
                                    income=SimpleNamespace(rates=rates_node)
                                )
                            )
                        )
                    )
                ),
            )

        def calculate(self, variable, period):
            assert period == 2026
            calls.append((variable, period))
            return {
                "tax_unit_id": ids,
                "mn_basic_tax": tax,
                "mn_taxable_income": taxable_income,
                "filing_status": filing_status,
            }[variable]

    FakeSimulation.calls = calls
    return FakeSimulation


def _mn_targets(
    microsimulation_factory,
    *,
    source_ids=(1, 2, 3),
) -> dict[str, dict[int, float]]:
    return calculate_policyengine_targets(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": source_ids}),
        routes=tuple(
            TaxUnitRoute(index, index, "MN", "27", 1, DISPOSITION_READY)
            for index in source_ids
        ),
        year=2026,
        microsimulation_factory=microsimulation_factory,
    )


def test_minnesota_target_preserves_exact_basic_tax_values_only() -> None:
    simulation = _mn_simulation()

    assert _mn_targets(simulation) == {
        "MN": {1: 0.0, 2: 1_100.0, 3: 7_400.0}
    }
    assert simulation.calls == [
        ("tax_unit_id", 2026),
        ("mn_basic_tax", 2026),
        ("mn_taxable_income", 2026),
        ("filing_status", 2026),
    ]
    assert all(
        variable != "mn_income_tax_before_refundable_credits"
        for variable, _ in simulation.calls
    )


@pytest.mark.parametrize(
    ("ids", "tax", "message"),
    [
        ((1, 2), (0.0, 1_100.0, 7_400.0), "returned 2 IDs"),
        (
            (2, 1, 3),
            (0.0, 1_100.0, 7_400.0),
            "order does not match",
        ),
        (
            (1, 1, 3),
            (0.0, 1_100.0, 7_400.0),
            "duplicate MN PolicyEngine",
        ),
    ],
)
def test_minnesota_target_rejects_entity_identity_and_cardinality_defects(
    ids,
    tax,
    message,
) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _mn_targets(_mn_simulation(ids=ids, tax=tax))


def test_minnesota_target_rejects_duplicate_source_entity_ids() -> None:
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="duplicate MN source tax_unit_id",
    ):
        _mn_targets(
            _mn_simulation(ids=(1, 1, 3)),
            source_ids=(1, 1, 3),
        )


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (float("nan"), "non-finite"),
        (float("inf"), "non-finite"),
        (-0.01, "must be nonnegative"),
    ],
)
def test_minnesota_target_rejects_invalid_basic_tax(value, message) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _mn_targets(_mn_simulation(tax=(0.0, value, 7_400.0)))


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {"taxable_income": (0.0, float("nan"), 100_000.0)},
            "mn_taxable_income.*non-finite",
        ),
        (
            {"filing_status": ("SINGLE", "UNKNOWN", "JOINT")},
            "unsupported value",
        ),
        (
            {"scale_thresholds": (0.0, 10_000.0, 20_000.0)},
            "scale schema drifted",
        ),
        (
            {"scale_rates": (0.05, 0.06, float("nan"), 0.08)},
            "scale schema drifted",
        ),
        (
            {"variable_entity": "person"},
            "class metadata or active formula schema drifted",
        ),
    ],
)
def test_minnesota_precision_stable_target_fails_closed_on_schema_and_input_drift(
    kwargs,
    message,
) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _mn_targets(_mn_simulation(**kwargs))


def test_minnesota_precision_stable_target_requires_exact_binary32_roundtrip() -> None:
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="does not equal the correctly rounded IEEE-754 binary32 result",
    ):
        _mn_targets(_mn_simulation(tax=(0.0, 1_100.1, 7_400.0)))


def test_minnesota_precision_stable_target_rejects_lower_binade_neighbor() -> None:
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="does not equal the correctly rounded IEEE-754 binary32 result",
    ):
        _mn_targets(
            _mn_simulation(
                tax=(0.0, 1.0, float(2**24 - 1)),
                taxable_income=(0.0, 1.0, float(2**24)),
                scale_rates=(1.0, 1.0, 1.0, 1.0),
            )
        )


@pytest.mark.parametrize(
    ("recovered", "raw"),
    [
        (float(2**24), float(2**24)),
        (float(2**24 + 1), float(2**24)),
        (float(2**24 - 1), float(2**24 - 1)),
    ],
)
def test_minnesota_precision_stable_target_accepts_exact_binary32_roundtrip(
    recovered,
    raw,
) -> None:
    assert _mn_targets(
        _mn_simulation(
            tax=(0.0, 1.0, raw),
            taxable_income=(0.0, 1.0, recovered),
            scale_rates=(1.0, 1.0, 1.0, 1.0),
        )
    ) == {"MN": {1: 0.0, 2: 1.0, 3: recovered}}


def test_minnesota_precision_stable_target_rejects_binary32_overflow() -> None:
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="cannot be represented as finite IEEE-754 binary32",
    ):
        _mn_targets(
            _mn_simulation(
                tax=(0.0, 1.0, 3.4e38),
                taxable_income=(0.0, 1.0, 3.5e38),
                scale_rates=(1.0, 1.0, 1.0, 1.0),
            )
        )


def _dc_simulation(
    *,
    ids=(1, 2, 3),
    taxable=(0.0, 10_000.0, 1_000_001.0),
    tax=(0.0, 400.0, 91_525.1075),
):
    calls = []

    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"

        def calculate(self, variable, period):
            assert period == 2026
            self.calls.append((variable, period))
            return {
                "tax_unit_id": ids,
                "dc_taxable_income_joint": taxable,
                "dc_income_tax_before_credits_joint": tax,
            }[variable]

    FakeSimulation.calls = calls
    return FakeSimulation


def _dc_targets(
    microsimulation_factory,
    *,
    source_ids=(1, 2, 3),
    route_ids=None,
) -> dict[str, dict[int, float]]:
    selected_route_ids = source_ids if route_ids is None else route_ids
    return calculate_policyengine_targets(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": source_ids}),
        routes=tuple(
            TaxUnitRoute(index, index, "DC", "11", 1, DISPOSITION_READY)
            for index in selected_route_ids
        ),
        year=2026,
        microsimulation_factory=microsimulation_factory,
    )


def test_dc_target_preserves_exact_joint_method_values_only() -> None:
    simulation = _dc_simulation()

    assert _dc_targets(simulation) == {
        "DC": {1: 0.0, 2: 400.0, 3: 91_525.1075}
    }
    assert simulation.calls == [
        ("tax_unit_id", 2026),
        ("dc_taxable_income_joint", 2026),
        ("dc_income_tax_before_credits_joint", 2026),
    ]
    assert all(
        variable != "dc_income_tax_before_credits"
        for variable, _ in simulation.calls
    )


def test_dc_target_preserves_all_1362_routed_tax_units() -> None:
    ids = tuple(range(1, 1_363))
    taxable = tuple(float(index * 100) for index in ids)
    tax = tuple(value * 0.04 for value in taxable)

    targets = _dc_targets(
        _dc_simulation(ids=ids, taxable=taxable, tax=tax),
        source_ids=ids,
    )

    assert len(targets["DC"]) == 1_362
    assert tuple(targets["DC"]) == ids
    assert targets["DC"][1] == 4.0
    assert targets["DC"][1_362] == 5_448.0


def test_dc_target_accepts_negative_boundary_that_both_schedules_floor() -> None:
    simulation = _dc_simulation(
        taxable=(-500.0, 10_000.0, 1_000_001.0),
        tax=(0.0, 400.0, 91_525.1075),
    )

    assert _dc_targets(simulation) == {
        "DC": {1: 0.0, 2: 400.0, 3: 91_525.1075}
    }


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {"ids": (1, 2)},
            "joint-method schedule inputs returned 2, 3, 3 rows",
        ),
        (
            {"taxable": (0.0, 10_000.0)},
            "joint-method schedule inputs returned 3, 2, 3 rows",
        ),
        (
            {"tax": (0.0, 400.0)},
            "joint-method schedule inputs returned 3, 3, 2 rows",
        ),
    ],
)
def test_dc_target_rejects_component_cardinality(kwargs, message) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _dc_targets(_dc_simulation(**kwargs))


@pytest.mark.parametrize(
    ("ids", "message"),
    [
        ((2, 1, 3), "order does not match"),
        ((1, 1, 3), "duplicate DC PolicyEngine tax_unit_id"),
    ],
)
def test_dc_target_rejects_entity_identity_defects(ids, message) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _dc_targets(_dc_simulation(ids=ids))


def test_dc_target_rejects_duplicate_source_entity_ids() -> None:
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="duplicate DC source tax_unit_id",
    ):
        _dc_targets(
            _dc_simulation(ids=(1, 1, 3)),
            source_ids=(1, 1, 3),
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {"taxable": (float("nan"), 10_000.0, 1_000_001.0)},
            "non-finite",
        ),
        ({"tax": (0.0, float("inf"), 91_525.1075)}, "non-finite"),
        ({"tax": (0.0, -1.0, 91_525.1075)}, "nonnegative"),
    ],
)
def test_dc_target_rejects_invalid_reviewed_values(kwargs, message) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _dc_targets(_dc_simulation(**kwargs))


def test_dc_target_rejects_broad_filing_method_target(monkeypatch) -> None:
    drifted_contract = SimpleNamespace(
        validation_year=2026,
        by_state=lambda: {
            "DC": SimpleNamespace(
                policyengine_target="dc_income_tax_before_credits",
            )
        },
    )
    monkeypatch.setattr(
        state_tax_runner,
        "validate_state_tax_populace_contract",
        lambda _contract: drifted_contract,
    )

    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="requires the exact dc_income_tax_before_credits_joint target",
    ):
        calculate_policyengine_targets(
            dataset="dataset",
            raw_tax_units=pd.DataFrame({"tax_unit_id": [1]}),
            routes=(
                TaxUnitRoute(1, 1, "DC", "11", 1, DISPOSITION_READY),
            ),
            year=2026,
            contract=drifted_contract,
            microsimulation_factory=_dc_simulation(
                ids=(1,),
                taxable=(0.0,),
                tax=(0.0,),
            ),
        )


def _ks_simulation(
    *,
    ids=(1, 2, 3),
    taxable=(0.0, 23_000.0, 46_001.0),
    joint=(False, False, True),
    agi=(0.0, 22_000.0, 45_000.0),
    tax=(0.0, 1_196.0, 2_392.0558),
):
    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"

        def calculate(self, variable, period):
            assert period == 2026
            return {
                "tax_unit_id": ids,
                "ks_taxable_income": taxable,
                "tax_unit_is_joint": joint,
                "ks_agi": agi,
                "ks_income_tax_before_credits": tax,
            }[variable]

    return FakeSimulation


def _ks_targets(
    microsimulation_factory,
    *,
    source_ids=(1, 2, 3),
) -> dict[str, dict[int, float]]:
    return calculate_policyengine_targets(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": source_ids}),
        routes=tuple(
            TaxUnitRoute(index, index, "KS", "20", 1, DISPOSITION_READY)
            for index in source_ids
        ),
        year=2026,
        microsimulation_factory=microsimulation_factory,
    )


def test_kansas_target_preserves_reviewed_before_credit_values() -> None:
    assert _ks_targets(_ks_simulation(agi=(0.0, -1.0, 45_000.0))) == {
        "KS": {1: 0.0, 2: 1_196.0, 3: 2_392.0558}
    }


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {"ids": (1, 2)},
            "K-40ES target inputs returned 2, 3, 3, 3, 3 rows",
        ),
        (
            {"taxable": (0.0, 23_000.0)},
            "K-40ES target inputs returned 3, 2, 3, 3, 3 rows",
        ),
        (
            {"joint": (False, True)},
            "K-40ES target inputs returned 3, 3, 2, 3, 3 rows",
        ),
        (
            {"agi": (0.0, 22_000.0)},
            "K-40ES target inputs returned 3, 3, 3, 2, 3 rows",
        ),
        (
            {"tax": (0.0, 1_196.0)},
            "K-40ES target inputs returned 3, 3, 3, 3, 2 rows",
        ),
    ],
)
def test_kansas_target_rejects_component_cardinality(kwargs, message) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _ks_targets(_ks_simulation(**kwargs))


@pytest.mark.parametrize(
    ("ids", "message"),
    [
        ((2, 1, 3), "order does not match"),
        ((1, 1, 3), "duplicate KS PolicyEngine tax_unit_id"),
    ],
)
def test_kansas_target_rejects_entity_identity_defects(ids, message) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _ks_targets(_ks_simulation(ids=ids))


def test_kansas_target_rejects_duplicate_source_entity_ids() -> None:
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="duplicate KS source tax_unit_id",
    ):
        _ks_targets(
            _ks_simulation(ids=(1, 1, 3)),
            source_ids=(1, 1, 3),
        )


def test_kansas_target_requires_strict_joint_boolean() -> None:
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="tax_unit_is_joint: expected a PolicyEngine boolean",
    ):
        _ks_targets(_ks_simulation(joint=(False, 1.0, True)))


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"taxable": (float("nan"), 23_000.0, 46_001.0)}, "non-finite"),
        ({"taxable": (-1.0, 23_000.0, 46_001.0)}, "nonnegative"),
        ({"agi": (0.0, float("inf"), 45_000.0)}, "non-finite"),
        ({"tax": (0.0, float("inf"), 2_392.0558)}, "non-finite"),
        ({"tax": (0.0, -1.0, 2_392.0558)}, "nonnegative"),
    ],
)
def test_kansas_target_rejects_invalid_reviewed_values(kwargs, message) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _ks_targets(_ks_simulation(**kwargs))


def test_kansas_target_rejects_agi_gate_suppression() -> None:
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="separate AGI gate suppressed a positive K-40ES schedule domain",
    ):
        _ks_targets(
            _ks_simulation(
                taxable=(0.0, 1.0, 46_001.0),
                tax=(0.0, 0.0, 2_392.0558),
            )
        )


def _oh_simulation(
    *,
    ids=(1, 2, 3),
    taxable=(26_049.0, 26_050.0, 26_051.0),
    tax=(0.0, 332.0020446777344, 332.029541015625),
    threshold=26_050.0,
):
    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"
            self.tax_benefit_system = SimpleNamespace(
                parameters=lambda period: SimpleNamespace(
                    gov=SimpleNamespace(
                        states=SimpleNamespace(
                            oh=SimpleNamespace(
                                tax=SimpleNamespace(
                                    income=SimpleNamespace(
                                        agi_threshold=threshold
                                    )
                                )
                            )
                        )
                    )
                )
            )

        def calculate(self, variable, period):
            assert period == 2026
            return {
                "tax_unit_id": ids,
                "oh_taxable_income": taxable,
                "oh_income_tax_before_non_refundable_credits": tax,
            }[variable]

    return FakeSimulation


def _oh_targets(microsimulation_factory) -> dict[str, dict[int, float]]:
    return calculate_policyengine_targets(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": [1, 2, 3]}),
        routes=tuple(
            TaxUnitRoute(index, index, "OH", "39", 1, DISPOSITION_READY)
            for index in range(1, 4)
        ),
        year=2026,
        microsimulation_factory=microsimulation_factory,
    )


def test_ohio_target_honors_inclusive_no_tax_threshold() -> None:
    assert _oh_targets(_oh_simulation()) == {
        "OH": {1: 0.0, 2: 0.0, 3: 332.029541015625}
    }


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {"ids": (1, 2)},
            "threshold-corrected target inputs returned 2, 3, and 3 rows",
        ),
        (
            {"taxable": (26_049.0, 26_050.0)},
            "threshold-corrected target inputs returned 3, 2, and 3 rows",
        ),
        (
            {"tax": (0.0, 332.0)},
            "threshold-corrected target inputs returned 3, 3, and 2 rows",
        ),
    ],
)
def test_ohio_target_rejects_component_cardinality(kwargs, message) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _oh_targets(_oh_simulation(**kwargs))


@pytest.mark.parametrize(
    ("ids", "message"),
    [
        ((2, 1, 3), "order does not match"),
        ((1, 1, 3), "duplicate OH PolicyEngine tax_unit_id"),
    ],
)
def test_ohio_target_rejects_entity_identity_defects(ids, message) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _oh_targets(_oh_simulation(ids=ids))


def test_ohio_target_rejects_duplicate_source_entity_ids() -> None:
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="duplicate OH source tax_unit_id",
    ):
        calculate_policyengine_targets(
            dataset="dataset",
            raw_tax_units=pd.DataFrame({"tax_unit_id": [1, 1, 3]}),
            routes=(
                TaxUnitRoute(1, 1, "OH", "39", 1, DISPOSITION_READY),
            ),
            year=2026,
            microsimulation_factory=_oh_simulation(ids=(1, 1, 3)),
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"taxable": (float("nan"), 26_050.0, 26_051.0)}, "non-finite"),
        ({"taxable": (-1.0, 26_050.0, 26_051.0)}, "nonnegative"),
        ({"tax": (0.0, float("inf"), 332.03)}, "non-finite"),
        ({"tax": (0.0, -1.0, 332.03)}, "nonnegative"),
        ({"threshold": float("nan")}, "non-finite"),
        ({"threshold": -1.0}, "must be nonnegative"),
    ],
)
def test_ohio_target_rejects_invalid_derived_values(kwargs, message) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _oh_targets(_oh_simulation(**kwargs))


def test_connecticut_target_recovers_policyengine_pre_credit_total_exactly() -> None:
    calls = []

    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"

        def calculate(self, variable, period):
            calls.append((variable, period))
            return {
                "ct_income_tax_after_personal_credits": [250.0, 1_000.0, 0.0],
                "ct_personal_credit_rate": [0.75, 0.5, 0.0],
            }[variable]

    targets = calculate_policyengine_targets(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": [1, 2, 3]}),
        routes=tuple(
            TaxUnitRoute(index, index, "CT", "09", 1, DISPOSITION_READY)
            for index in range(1, 4)
        ),
        year=2026,
        microsimulation_factory=FakeSimulation,
    )

    assert targets == {"CT": {1: 1_000.0, 2: 2_000.0, 3: 0.0}}
    assert calls == [
        ("ct_income_tax_after_personal_credits", 2026),
        ("ct_personal_credit_rate", 2026),
    ]


def test_connecticut_target_recovery_fails_closed_on_unit_credit_rate() -> None:
    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"

        def calculate(self, variable, period):
            return {
                "ct_income_tax_after_personal_credits": [0.0],
                "ct_personal_credit_rate": [1.0],
            }[variable]

    with pytest.raises(
        StateTaxPopulationRoutingError,
        match=r"personal-credit rate in \[0, 1\)",
    ):
        calculate_policyengine_targets(
            dataset="dataset",
            raw_tax_units=pd.DataFrame({"tax_unit_id": [1]}),
            routes=(
                TaxUnitRoute(1, 1, "CT", "09", 1, DISPOSITION_READY),
            ),
            year=2026,
            microsimulation_factory=FakeSimulation,
        )


def test_arkansas_person_target_is_validated_and_summed_to_tax_units() -> None:
    calls = []

    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"

        def calculate(self, variable, period, map_to=None):
            calls.append((variable, period, map_to))
            return {
                "person_id": [11, 12, 21],
                "tax_unit_id": [1, 1, 2],
                "ar_income_tax_before_non_refundable_credits_indiv": [
                    100.0,
                    200.0,
                    50.0,
                ],
            }[variable]

    targets = calculate_policyengine_targets(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": [1, 2]}),
        raw_persons=pd.DataFrame(
            {
                "person_id": [11, 12, 21],
                "person_tax_unit_id": [1, 1, 2],
            }
        ),
        routes=(
            TaxUnitRoute(1, 1, "AR", "05", 1, DISPOSITION_READY),
            TaxUnitRoute(2, 2, "AR", "05", 1, DISPOSITION_READY),
        ),
        year=2026,
        microsimulation_factory=FakeSimulation,
    )

    assert targets == {"AR": {1: 300.0, 2: 50.0}}
    assert calls == [
        ("person_id", 2026, None),
        ("tax_unit_id", 2026, "person"),
        ("ar_income_tax_before_non_refundable_credits_indiv", 2026, None),
    ]


def test_arkansas_person_outputs_are_summed_before_tax_unit_comparison(
    tmp_path,
) -> None:
    prefix = "us-ar:policies/income_tax/pilot_liability_pipeline"
    slot = f"{prefix}#input.ar_pit_pilot_individual_taxable_income"
    output = f"{prefix}#ar_pit_pilot_income_tax_before_non_refundable_credits_indiv"
    raw_persons = pd.DataFrame(
        {
            "person_id": [11, 12, 21],
            "person_tax_unit_id": [1, 1, 2],
        }
    )
    routes = (
        TaxUnitRoute(1, 1, "AR", "05", 2, DISPOSITION_READY),
        TaxUnitRoute(2, 2, "AR", "05", 3, DISPOSITION_READY),
    )
    calls = []

    def fake_axiom_runner(**kwargs):
        calls.append(kwargs["request"])
        values = [100.0, 200.0, 50.0]
        return [
            {
                "entity_id": query["entity_id"],
                "outputs": {output: {"value": {"value": str(value)}}},
            }
            for query, value in zip(
                kwargs["request"]["queries"], values, strict=True
            )
        ]

    report = compare_ready_state_tax_units(
        routes=routes,
        raw_persons=raw_persons,
        known_tax_unit_ids={1, 2},
        policyengine_targets={"AR": {1: 300.0, 2: 50.0}},
        policyengine_projection_inputs={
            "AR": {slot: {11: 10_000.0, 12: 20_000.0, 21: 5_000.0}}
        },
        year=2026,
        rulespec_root=tmp_path / "rulespec-us",
        axiom_rules_path=tmp_path / "axiom-rules",
        axiom_runner=fake_axiom_runner,
    )

    assert report["mismatch_count"] == 0
    assert report["compared_count"] == 2
    assert report["states"]["AR"]["comparison_aggregation"] == (
        "person_sum_to_tax_unit"
    )
    assert [query["entity_id"] for query in calls[0]["queries"]] == [
        "state-tax-person-11",
        "state-tax-person-12",
        "state-tax-person-21",
    ]
    assert calls[0]["dataset"]["relations"] == []


def test_policyengine_projection_calculation_uses_only_reviewed_boundaries() -> None:
    calls = []

    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"

        def calculate(self, variable, period):
            calls.append((variable, period))
            values = {
                "ut_taxable_income": [-100, 25000],
                "ut_income_tax_exempt": [False, True],
            }
            return values[variable]

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

    assert calls == [
        ("ut_taxable_income", 2026),
        ("ut_income_tax_exempt", 2026),
    ]
    assert projections == {
        "UT": _ut_inputs(
            {1: -100.0, 2: 25000.0},
            resident={1: True, 2: False},
            aligned={1: True, 2: False},
            exempt={1: False, 2: True},
        )
    }


def test_reviewed_dc_projection_uses_only_joint_method_taxable_income() -> None:
    calls = []

    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"

        def calculate(self, variable, period):
            calls.append((variable, period))
            assert variable == "dc_taxable_income_joint"
            return [0.0, 50_000.0]

    routes = (
        TaxUnitRoute(1, 1, "DC", "11", 1, DISPOSITION_READY),
        TaxUnitRoute(2, 2, "CA", "06", 1, DISPOSITION_BLOCKED),
    )
    projections = calculate_policyengine_projection_inputs(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": [1, 2]}),
        routes=routes,
        year=2026,
        microsimulation_factory=FakeSimulation,
    )
    slot = (
        "us-dc:policies/income_tax/"
        "2026_section_47_1806_03_schedule_before_credits#input."
        "dc_pit_2026_section_47_1806_03_completed_joint_method_taxable_income"
    )

    assert calls == [("dc_taxable_income_joint", 2026)]
    assert projections == {"DC": {slot: {1: 0.0, 2: 50_000.0}}}


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
    ks_prefix = (
        "us-ks:policies/income_tax/"
        "2026_k40es_schedule_before_credits#input."
    )
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
    assert projections["KS"][
        f"{ks_prefix}ks_pit_2026_k40es_married_joint_schedule_applies"
    ] == {
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

    prefix = (
        "us-al:policies/income_tax/"
        "2026_section_40_18_5_schedule_before_credits#input."
    )
    assert projections["AL"][
        f"{prefix}al_pit_2026_section_40_18_5_married_joint_schedule_applies"
    ] == {
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

    prefix = (
        "us-ct:policies/income_tax/"
        "2026_resident_ordinary_tax_before_personal_credit#input."
    )
    assert projections[f"{prefix}ct_pit_2026_connecticut_taxable_income"] == {
        1: 1,
        2: 2,
        3: 3,
        4: 4,
        5: 5,
    }
    assert projections[f"{prefix}ct_pit_2026_connecticut_adjusted_gross_income"] == {
        1: 11,
        2: 12,
        3: 13,
        4: 14,
        5: 15,
    }
    assert projections[
        f"{prefix}ct_pit_2026_is_full_year_connecticut_resident_return"
    ] == {1: True, 2: True, 3: True, 4: True, 5: True}
    assert projections[
        f"{prefix}ct_pit_2026_ordinary_tax_filing_status_single"
    ] == {1: True, 2: False, 3: False, 4: False, 5: False}
    assert projections[
        f"{prefix}ct_pit_2026_ordinary_tax_filing_status_joint_or_surviving_spouse"
    ] == {1: False, 2: True, 3: False, 4: False, 5: True}
    assert projections[
        f"{prefix}ct_pit_2026_ordinary_tax_filing_status_head_of_household"
    ] == {1: False, 2: False, 3: False, 4: True, 5: False}
    assert projections[
        f"{prefix}ct_pit_2026_ordinary_tax_filing_status_married_separate"
    ] == {1: False, 2: False, 3: True, 4: False, 5: False}


def test_reviewed_new_york_projection_covers_all_filing_statuses() -> None:
    calls = []
    values = {
        "tax_unit_id": [1, 2, 3, 4, 5],
        "ny_taxable_income": [10_000, 20_000, 30_000, 40_000, 50_000],
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
            assert period == 2026
            return values[variable]

    projections = calculate_policyengine_projection_inputs(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": [1, 2, 3, 4, 5]}),
        routes=tuple(
            TaxUnitRoute(index, index, "NY", "36", 1, DISPOSITION_READY)
            for index in range(1, 6)
        ),
        year=2026,
        microsimulation_factory=FakeSimulation,
    )["NY"]

    prefix = "us-ny:policies/income_tax/pilot_liability_pipeline#input."
    assert projections[f"{prefix}ny_pit_pilot_state_taxable_income"] == {
        1: 10_000.0,
        2: 20_000.0,
        3: 30_000.0,
        4: 40_000.0,
        5: 50_000.0,
    }
    assert projections[
        f"{prefix}ny_pit_pilot_filing_status_joint_or_surviving_spouse"
    ] == {1: False, 2: True, 3: False, 4: False, 5: True}
    assert projections[f"{prefix}ny_pit_pilot_filing_status_head_of_household"] == {
        1: False,
        2: False,
        3: False,
        4: True,
        5: False,
    }
    assert calls == [
        ("tax_unit_id", 2026),
        ("ny_taxable_income", 2026),
        ("filing_status", 2026),
        ("filing_status", 2026),
    ]


@pytest.mark.parametrize(
    ("modeled_ids", "message"),
    [
        ([1, 2], "returned 2 IDs for 3 tax units"),
        ([2, 1, 3], "order does not match"),
        ([1, 1, 3], "duplicate NY PolicyEngine projection"),
    ],
)
def test_reviewed_new_york_projection_rejects_identity_defects(
    modeled_ids,
    message,
) -> None:
    values = {
        "tax_unit_id": modeled_ids,
        "ny_taxable_income": [10_000, 20_000, 30_000],
        "filing_status": ["SINGLE", "JOINT", "HEAD_OF_HOUSEHOLD"],
    }

    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"

        def calculate(self, variable, period):
            assert period == 2026
            return values[variable]

    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        calculate_policyengine_projection_inputs(
            dataset="dataset",
            raw_tax_units=pd.DataFrame({"tax_unit_id": [1, 2, 3]}),
            routes=tuple(
                TaxUnitRoute(index, index, "NY", "36", 1, DISPOSITION_READY)
                for index in range(1, 4)
            ),
            year=2026,
            microsimulation_factory=FakeSimulation,
        )


def _il_projection_simulation(
    *,
    ids=(1, 2, 3),
    taxable=(0.0, 20_000.0, 100_000.0),
    recapture=(0.0, 0.0, 125.0),
    schema=None,
):
    calls = []

    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"
            self.tax_benefit_system = schema or _reviewed_money_schema(
                "il_taxable_income",
                "recapture_of_investment_credit",
            )

        def calculate(self, variable, period):
            calls.append((variable, period))
            assert period == 2026
            return {
                "tax_unit_id": ids,
                "il_taxable_income": taxable,
                "recapture_of_investment_credit": recapture,
            }[variable]

    FakeSimulation.calls = calls
    return FakeSimulation


def _il_projection(
    microsimulation_factory,
    *,
    source_ids=(1, 2, 3),
):
    return calculate_policyengine_projection_inputs(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": source_ids}),
        routes=tuple(
            TaxUnitRoute(index, index, "IL", "17", 1, DISPOSITION_READY)
            for index in source_ids
        ),
        year=2026,
        microsimulation_factory=microsimulation_factory,
    )["IL"]


def test_reviewed_illinois_projection_uses_only_completed_boundaries() -> None:
    simulation = _il_projection_simulation()

    projection = _il_projection(simulation)

    prefix = "us-il:policies/income_tax/pilot_liability_pipeline#input."
    assert projection[f"{prefix}il_pit_pilot_state_taxable_income"] == {
        1: 0.0,
        2: 20_000.0,
        3: 100_000.0,
    }
    assert projection[
        f"{prefix}il_pit_pilot_recapture_of_investment_credit"
    ] == {
        1: 0.0,
        2: 0.0,
        3: 125.0,
    }
    assert simulation.calls == [
        ("tax_unit_id", 2026),
        ("il_taxable_income", 2026),
        ("recapture_of_investment_credit", 2026),
    ]


@pytest.mark.parametrize(
    ("modeled_ids", "message"),
    [
        ([1, 2], "returned 2 IDs for 3 tax units"),
        ([2, 1, 3], "order does not match"),
        ([1, 1, 3], "duplicate IL PolicyEngine projection"),
    ],
)
def test_reviewed_illinois_projection_rejects_identity_defects(
    modeled_ids,
    message,
) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _il_projection(_il_projection_simulation(ids=modeled_ids))


@pytest.mark.parametrize(
    ("taxable", "recapture", "message"),
    [
        ((0.0, float("nan"), 100_000.0), (0.0, 0.0, 125.0), "non-finite"),
        ((0.0, float("inf"), 100_000.0), (0.0, 0.0, 125.0), "non-finite"),
        ((0.0, -0.01, 100_000.0), (0.0, 0.0, 125.0), "must be nonnegative"),
        ((0.0, 20_000.0, 100_000.0), (0.0, -0.01, 125.0), "must be nonnegative"),
    ],
)
def test_reviewed_illinois_projection_rejects_invalid_boundaries(
    taxable,
    recapture,
    message,
) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _il_projection(
            _il_projection_simulation(
                taxable=taxable,
                recapture=recapture,
            )
        )


def test_reviewed_minnesota_projection_covers_all_filing_statuses() -> None:
    calls = []
    values = {
        "mn_taxable_income": [10_000, 20_000, 30_000, 40_000, 50_000],
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
            assert period == 2026
            return values[variable]

    projections = calculate_policyengine_projection_inputs(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": [1, 2, 3, 4, 5]}),
        routes=tuple(
            TaxUnitRoute(index, index, "MN", "27", 1, DISPOSITION_READY)
            for index in range(1, 6)
        ),
        year=2026,
        microsimulation_factory=FakeSimulation,
    )["MN"]

    prefix = "us-mn:policies/income_tax/pilot_liability_pipeline#input."
    assert projections[f"{prefix}mn_pit_pilot_state_taxable_income"] == {
        1: 10_000.0,
        2: 20_000.0,
        3: 30_000.0,
        4: 40_000.0,
        5: 50_000.0,
    }
    assert projections[
        f"{prefix}mn_pit_pilot_filing_status_joint_or_surviving_spouse"
    ] == {1: False, 2: True, 3: False, 4: False, 5: True}
    assert projections[f"{prefix}mn_pit_pilot_filing_status_separate"] == {
        1: False,
        2: False,
        3: True,
        4: False,
        5: False,
    }
    assert projections[
        f"{prefix}mn_pit_pilot_filing_status_head_of_household"
    ] == {1: False, 2: False, 3: False, 4: True, 5: False}
    assert calls == [
        ("mn_taxable_income", 2026),
        ("filing_status", 2026),
        ("filing_status", 2026),
        ("filing_status", 2026),
    ]


def test_reviewed_colorado_projection_uses_completed_taxable_income() -> None:
    calls = []

    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"

        def calculate(self, variable, period):
            calls.append((variable, period))
            return [0.0, 12_345.67]

    projections = calculate_policyengine_projection_inputs(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": [11, 22]}),
        routes=(
            TaxUnitRoute(11, 1, "CO", "08", 1, DISPOSITION_READY),
            TaxUnitRoute(22, 2, "CO", "08", 1, DISPOSITION_READY),
        ),
        year=2026,
        microsimulation_factory=FakeSimulation,
    )["CO"]

    slot = (
        "us-co:policies/income_tax/pilot_liability_pipeline#input."
        "co_pit_pilot_state_taxable_income"
    )
    assert projections[slot] == {11: 0.0, 22: 12_345.67}
    assert calls == [("co_taxable_income", 2026)]


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


def test_kentucky_completed_net_income_projection_follows_filing_method() -> None:
    calls = []
    values = {
        "person_id": [11, 12, 21],
        "tax_unit_id": [1, 1, 2],
        "ky_taxable_income_indiv": [40_000.0, 20_000.0, 35_000.0],
        "ky_taxable_income_joint": [55_000.0, 0.0, 42_000.0],
        "ky_files_separately": [True, False],
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
            TaxUnitRoute(1, 1, "KY", "21", 1, DISPOSITION_READY),
            TaxUnitRoute(2, 2, "KY", "21", 1, DISPOSITION_READY),
        ),
        year=2026,
        microsimulation_factory=FakeSimulation,
    )

    slot = (
        "us-ky:policies/income_tax/"
        "2026_krs_141_020_schedule_before_credits#input."
        "ky_pit_2026_krs_141_020_completed_net_income"
    )
    assert projections["KY"] == {slot: {1: 60_000.0, 2: 42_000.0}}
    assert calls == [
        ("person_id", 2026),
        ("tax_unit_id", 2026),
        ("ky_taxable_income_indiv", 2026),
        ("ky_taxable_income_joint", 2026),
        ("ky_files_separately", 2026),
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
    inputs = (
        SimpleNamespace(
            slot=separate_slot,
            source_kind="pe_upstream_boundary",
            policyengine_variable="de_taxable_income_indv",
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
                "de_taxable_income_indv": [10_000.0, 20_000.0, 500.0, 30_000.0],
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
        }
    }


def test_mississippi_canonical_schedule_projection_preserves_person_grain(
    monkeypatch,
) -> None:
    slot = (
        "us-ms:policies/income_tax/2026_section_27_7_5_schedule#input."
        "ms_pit_2026_supplied_taxable_income"
    )
    inputs = (
        SimpleNamespace(
            slot=slot,
            source_kind="pe_upstream_boundary",
            policyengine_variable="ms_taxable_income_joint",
            policyengine_variables=(),
            policyengine_transform=None,
            constant_value=None,
        ),
    )
    jurisdiction = SimpleNamespace(inputs=inputs, relations=())
    contract = SimpleNamespace(
        validation_year=2026,
        by_state=lambda: {"MS": jurisdiction},
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
                "person_id": [11, 12, 21],
                "tax_unit_id": [1, 1, 2],
                "ms_taxable_income_joint": [30_000.0, 20_000.0, 40_000.0],
            }[variable]

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
            TaxUnitRoute(1, 1, "MS", "28", 1, DISPOSITION_READY),
            TaxUnitRoute(2, 2, "MS", "28", 1, DISPOSITION_READY),
        ),
        year=2026,
        contract=contract,
        microsimulation_factory=FakeSimulation,
    )

    assert projections == {
        "MS": {
            slot: {11: 30_000.0, 12: 20_000.0, 21: 40_000.0},
        }
    }


def test_mississippi_request_emits_canonical_person_schedule_without_relation() -> None:
    prefix = "us-ms:policies/income_tax/2026_section_27_7_5_schedule"
    slot = f"{prefix}#input.ms_pit_2026_supplied_taxable_income"
    interval = {
        "period_kind": "tax_year",
        "start": "2026-01-01",
        "end": "2026-12-31",
    }

    request = state_tax_runner._state_request(
        state="MS",
        routes=(TaxUnitRoute(1, 1, "MS", "28", 1, DISPOSITION_READY),),
        year=2026,
        output=f"{prefix}#ms_pit_2026_section_27_7_5_schedule_tax",
        projected_inputs={
            slot: {11: 30_000.0, 12: 20_000.0, 21: 40_000.0},
        },
        raw_persons=pd.DataFrame(
            {
                "person_id": [11, 12, 21],
                "person_tax_unit_id": [1, 1, 2],
            }
        ),
        all_tax_unit_ids={1, 2},
        comparison_aggregation="person_sum_to_tax_unit",
    )

    assert request["dataset"]["inputs"] == [
        {
            "name": slot,
            "entity": "Entity",
            "entity_id": "state-tax-person-11",
            "interval": interval,
            "value": {"kind": "decimal", "value": "30000.0"},
        },
        {
            "name": slot,
            "entity": "Entity",
            "entity_id": "state-tax-person-12",
            "interval": interval,
            "value": {"kind": "decimal", "value": "20000.0"},
        },
    ]
    assert request["dataset"]["relations"] == []


def test_dc_filer_inclusion_rejects_ambiguous_policyengine_roles() -> None:
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="person_id 11 is both TaxUnit head and spouse",
    ):
        state_tax_runner._reviewed_filer_inclusions(
            state="DC",
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
            state="DC",
            person_ids=[11, 12],
            person_tax_unit_ids=[1, 1],
            tax_unit_ids=[1],
            selected_tax_unit_ids={1},
            head_values=[True, True],
            spouse_values=[False, False],
        )


def test_delaware_request_emits_canonical_person_schedule_without_relation() -> None:
    prefix = "us-de:policies/income_tax/pilot_liability_pipeline"
    separate_slot = f"{prefix}#input.de_pit_pilot_supplied_separate_taxable_income"
    interval = {
        "period_kind": "tax_year",
        "start": "2026-01-01",
        "end": "2026-12-31",
    }

    request = state_tax_runner._state_request(
        state="DE",
        routes=(TaxUnitRoute(2, 2, "DE", "10", 1, DISPOSITION_READY),),
        year=2026,
        output=f"{prefix}#de_pit_pilot_separate_schedule_tax",
        projected_inputs={
            separate_slot: {11: 1_000.0, 21: 20_000.0, 22: 30_000.0, 31: 4_000.0},
        },
        raw_persons=pd.DataFrame(
            {
                "person_id": [11, 21, 22, 31],
                "person_tax_unit_id": [1, 2, 2, 3],
            }
        ),
        all_tax_unit_ids={1, 2, 3},
        comparison_aggregation="person_sum_to_tax_unit",
    )

    assert request["dataset"]["inputs"] == [
        {
            "name": separate_slot,
            "entity": "Entity",
            "entity_id": "state-tax-person-21",
            "interval": interval,
            "value": {"kind": "decimal", "value": "20000.0"},
        },
        {
            "name": separate_slot,
            "entity": "Entity",
            "entity_id": "state-tax-person-22",
            "interval": interval,
            "value": {"kind": "decimal", "value": "30000.0"},
        },
    ]
    assert request["dataset"]["relations"] == []


def test_filtered_delaware_person_comparison_preserves_national_tax_unit_universe(
    monkeypatch, tmp_path
) -> None:
    prefix = "us-de:policies/income_tax/pilot_liability_pipeline"
    separate_slot = f"{prefix}#input.de_pit_pilot_supplied_separate_taxable_income"
    jurisdiction = SimpleNamespace(
        inputs=(SimpleNamespace(slot=separate_slot),),
        relations=(),
        output=f"{prefix}#de_pit_pilot_separate_schedule_tax",
        program="us-de:policies/income_tax/pilot_liability_pipeline",
        tolerance=0.01,
        relative_tolerance=1e-7,
        policyengine_target="de_income_tax_before_non_refundable_credits_indv",
        comparison_aggregation="person_sum_to_tax_unit",
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
                "entity_id": "state-tax-person-11",
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
    assert calls[0]["dataset"]["relations"] == []

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
        policyengine_projection_inputs={"UT": _ut_inputs({9: 10000.0})},
        year=2026,
        rulespec_root=tmp_path / "rulespec-us",
        axiom_rules_path=tmp_path / "axiom-rules",
        axiom_runner=fake_axiom_runner,
    )

    assert report["mismatch_count"] == 0
    inputs = calls[0]["request"]["dataset"]["inputs"]
    assert {item["name"] for item in inputs} == {
        _UT_TAXABLE_SLOT,
        _UT_RESIDENT_SLOT,
        _UT_ALIGNED_SLOT,
        _UT_EXEMPT_SLOT,
    }
    assert next(item for item in inputs if item["name"] == _UT_TAXABLE_SLOT)[
        "value"
    ] == {"kind": "decimal", "value": "10000.0"}
    assert all(
        next(item for item in inputs if item["name"] == slot)["value"]
        == {"kind": "bool", "value": expected}
        for slot, expected in {
            _UT_RESIDENT_SLOT: True,
            _UT_ALIGNED_SLOT: True,
            _UT_EXEMPT_SLOT: False,
        }.items()
    )


def test_ready_kansas_comparison_preserves_boolean_input_kind(tmp_path) -> None:
    prefix = (
        "us-ks:policies/income_tax/"
        "2026_k40es_schedule_before_credits#input."
    )
    taxable_slot = f"{prefix}ks_pit_2026_k40es_completed_taxable_income"
    joint_slot = (
        f"{prefix}ks_pit_2026_k40es_married_joint_schedule_applies"
    )
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
    routes = (TaxUnitRoute(9, 1, "UT", "49", 3.0, DISPOSITION_READY),)

    with pytest.raises(
        StateTaxPopulationRoutingError,
        match=r"UT: projected input inventory mismatch; missing=\[\], extra=",
    ):
        compare_ready_state_tax_units(
            routes=routes,
            policyengine_targets={"UT": {9: 445.0}},
            policyengine_projection_inputs={
                "UT": {
                    **_ut_inputs({9: 10_000.0}),
                    f"{_UT_TAXABLE_SLOT}_unexpected": {9: 0.0},
                }
            },
            year=2026,
            rulespec_root=tmp_path / "rulespec-us",
            axiom_rules_path=tmp_path / "axiom-rules",
            axiom_runner=lambda **_: [],
        )


def test_ready_comparison_attributes_axiom_failures_to_state(tmp_path) -> None:
    routes = (TaxUnitRoute(9, 1, "UT", "49", 3.0, DISPOSITION_READY),)

    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="UT: Axiom execution failed: bad input type",
    ):
        compare_ready_state_tax_units(
            routes=routes,
            policyengine_targets={"UT": {9: 445.0}},
            policyengine_projection_inputs={"UT": _ut_inputs({9: 10_000.0})},
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


# ---------------------------------------------------------------------------
# TAXSIM oracle leg


def _fake_axiom_zero_runner(**kwargs):
    output = kwargs["request"]["queries"][0]["outputs"][0]
    return [
        {
            "entity_id": query["entity_id"],
            "outputs": {output: {"value": {"value": "0"}}},
        }
        for query in kwargs["request"]["queries"]
    ]


def test_compare_grades_taxsim_leg_and_reports_mismatches(tmp_path) -> None:
    routes = (
        TaxUnitRoute(2, 1, "UT", "49", 2.5, DISPOSITION_READY),
        TaxUnitRoute(5, 2, "UT", "49", 3.5, DISPOSITION_READY),
    )

    report = compare_ready_state_tax_units(
        routes=routes,
        policyengine_targets={"UT": {2: 0.0, 5: 0.0}},
        policyengine_projection_inputs={"UT": _ut_inputs({2: 0.0, 5: 0.0})},
        taxsim_targets={"UT": {2: 0.0, 5: 123.0}},
        year=2026,
        rulespec_root=tmp_path / "rulespec-us",
        axiom_rules_path=tmp_path / "axiom-rules",
        axiom_runner=_fake_axiom_zero_runner,
    )

    ut = report["states"]["UT"]
    # UT's populace concept is a pre-credit schedule; the graded TAXSIM
    # column must resolve to staxbc via the concept mapping.
    assert ut["taxsim_target"] == "staxbc"
    assert ut["taxsim_mismatch_count"] == 1
    assert ut["taxsim_mismatches"][0]["tax_unit_id"] == 5
    assert ut["taxsim_mismatches"][0]["taxsim"] == 123.0
    by_id = {row["tax_unit_id"]: row for row in ut["cases"]}
    assert by_id[2]["taxsim"] == 0.0 and by_id[2]["taxsim_matched"] is True
    assert by_id[5]["taxsim"] == 123.0 and by_id[5]["taxsim_matched"] is False
    # PolicyEngine grading is untouched by the second leg.
    assert ut["mismatch_count"] == 0
    assert report["taxsim_state_count"] == 1
    assert report["taxsim_mismatch_count"] == 1
    assert report["taxsim_skipped_states"] == []


def test_compare_without_taxsim_targets_keeps_prior_shape(tmp_path) -> None:
    routes = (TaxUnitRoute(2, 1, "UT", "49", 2.5, DISPOSITION_READY),)

    report = compare_ready_state_tax_units(
        routes=routes,
        policyengine_targets={"UT": {2: 0.0}},
        policyengine_projection_inputs={"UT": _ut_inputs({2: 0.0})},
        year=2026,
        rulespec_root=tmp_path / "rulespec-us",
        axiom_rules_path=tmp_path / "axiom-rules",
        axiom_runner=_fake_axiom_zero_runner,
    )

    assert "taxsim_state_count" not in report
    assert "taxsim_target" not in report["states"]["UT"]
    assert "taxsim" not in report["states"]["UT"]["cases"][0]


def test_compare_fails_closed_when_taxsim_leg_omits_a_selected_unit(
    tmp_path,
) -> None:
    routes = (
        TaxUnitRoute(2, 1, "UT", "49", 2.5, DISPOSITION_READY),
        TaxUnitRoute(5, 2, "UT", "49", 3.5, DISPOSITION_READY),
    )

    with pytest.raises(
        StateTaxPopulationRoutingError, match="TAXSIM target omitted"
    ):
        compare_ready_state_tax_units(
            routes=routes,
            policyengine_targets={"UT": {2: 0.0, 5: 0.0}},
            policyengine_projection_inputs={
                "UT": _ut_inputs({2: 0.0, 5: 0.0})
            },
            taxsim_targets={"UT": {2: 0.0}},
            year=2026,
            rulespec_root=tmp_path / "rulespec-us",
            axiom_rules_path=tmp_path / "axiom-rules",
            axiom_runner=_fake_axiom_zero_runner,
        )


def test_compare_reports_states_skipped_by_the_taxsim_leg(tmp_path) -> None:
    routes = (TaxUnitRoute(2, 1, "UT", "49", 2.5, DISPOSITION_READY),)

    report = compare_ready_state_tax_units(
        routes=routes,
        policyengine_targets={"UT": {2: 0.0}},
        policyengine_projection_inputs={"UT": _ut_inputs({2: 0.0})},
        taxsim_targets={},
        year=2026,
        rulespec_root=tmp_path / "rulespec-us",
        axiom_rules_path=tmp_path / "axiom-rules",
        axiom_runner=_fake_axiom_zero_runner,
    )

    assert report["taxsim_state_count"] == 0
    assert report["taxsim_skipped_states"] == ["UT"]
    assert "taxsim" not in report["states"]["UT"]["cases"][0]


def test_taxsim_target_column_is_mapping_declared_or_none() -> None:
    from axiom_oracles.bridges.state_tax_populace import (
        load_state_tax_populace_contract,
    )
    from axiom_oracles.bridges.state_tax_populace_runner import (
        taxsim_target_column,
    )

    contract = load_state_tax_populace_contract()
    by_state = contract.by_state()
    # Pre-credit schedule concepts grade staxbc.
    assert taxsim_target_column(by_state["UT"].output) == "staxbc"
    # Final-liability pipelines grade siitax.
    assert taxsim_target_column(by_state["IL"].output) == "siitax"
    # CA's Behavioral Health Services Tax has no truthful TAXSIM surface:
    # the leg must skip it, never guess a column.
    assert taxsim_target_column(by_state["CA"].output) is None


def test_calculate_taxsim_targets_projects_and_grades_ready_units() -> None:
    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"

        def calculate(self, variable, period, map_to=None):
            person_values = {
                "person_id": [1, 2, 3],
                "age": [40, 38, 10],
                "is_tax_unit_head": [True, False, False],
                "is_tax_unit_spouse": [False, True, False],
                "employment_income": [60000.0, 15000.0, 0.0],
            }
            if variable == "tax_unit_id" and map_to == "person":
                return [7, 7, 7]
            if variable in person_values:
                return person_values[variable]
            # Every non-wage income variable defaults to zero.
            return [0.0, 0.0, 0.0]

    captured: dict = {}

    class FakeResult:
        def to_dict(self, orient):
            assert orient == "records"
            return [{"taxsimid": 7, "staxbc": 2700.0, "siitax": 2270.13}]

    class FakeRunner:
        def __init__(self, frame):
            captured["frame"] = frame

        def run(self, show_progress=False):
            return FakeResult()

    routes = (TaxUnitRoute(7, 1, "UT", "49", 2.5, DISPOSITION_READY),)
    raw_tax_units = pd.DataFrame({"tax_unit_id": [7]})
    raw_persons = pd.DataFrame(
        {"person_id": [1, 2, 3], "person_tax_unit_id": [7, 7, 7]}
    )

    targets = state_tax_runner.calculate_taxsim_targets(
        dataset="dataset",
        raw_tax_units=raw_tax_units,
        raw_persons=raw_persons,
        routes=routes,
        year=2026,
        microsimulation_factory=FakeSimulation,
        taxsim_runner_factory=FakeRunner,
    )

    # UT's concept maps staxbc — the pre-credit value, not siitax.
    assert targets == {"UT": {7: 2700.0}}
    row = captured["frame"].to_dict(orient="records")[0]
    # The projected row carries the contract's SOI state code and the
    # head/spouse wage split from the certified person links.
    assert row["state"] == 45
    assert row["mstat"] == 2
    assert row["pwages"] == 60000.0
    assert row["swages"] == 15000.0
    assert row["depx"] == 1
    assert row["page"] == 40 and row["sage"] == 38
    assert row["idtl"] == 2


def test_calculate_taxsim_targets_skips_unmapped_jurisdictions() -> None:
    class FakeSimulation:
        def __init__(self, dataset):
            pass

        def calculate(self, variable, period, map_to=None):
            if variable == "person_id":
                return [1]
            if variable == "tax_unit_id" and map_to == "person":
                return [7]
            if variable == "age":
                return [40]
            if variable == "is_tax_unit_head":
                return [True]
            if variable == "is_tax_unit_spouse":
                return [False]
            return [0.0]

    def forbidden_runner(frame):
        raise AssertionError("TAXSIM must not run for unmapped CA")

    routes = (TaxUnitRoute(7, 1, "CA", "06", 2.5, DISPOSITION_READY),)

    targets = state_tax_runner.calculate_taxsim_targets(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": [7]}),
        raw_persons=pd.DataFrame(
            {"person_id": [1], "person_tax_unit_id": [7]}
        ),
        routes=routes,
        year=2026,
        microsimulation_factory=FakeSimulation,
        taxsim_runner_factory=forbidden_runner,
    )

    assert targets == {}
