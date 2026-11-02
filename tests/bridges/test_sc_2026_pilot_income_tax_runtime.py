from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from axiom_oracles.bridges.state_tax_populace_runner import (
    DISPOSITION_READY,
    StateTaxPopulationRoutingError,
    TaxUnitRoute,
    _validate_south_carolina_runtime_contract,
    calculate_policyengine_projection_inputs,
    calculate_policyengine_targets,
)


def _schedule(taxable_income: float) -> float:
    if taxable_income < 30_000:
        return taxable_income * 0.0199
    return taxable_income * 0.0521 - 966


def _formula(tax_unit, period, parameters):
    taxable_income = tax_unit("sc_taxable_income", period)
    rates = parameters(period).gov.states.sc.tax.income.rates
    return rates.calc(taxable_income)


def _definition(
    *,
    formula=_formula,
    entity="tax_unit",
    period="year",
    value_type=float,
    unit="currency-USD",
    upstream=False,
):
    return SimpleNamespace(
        entity=SimpleNamespace(key=entity),
        definition_period=period,
        value_type=value_type,
        unit=unit,
        formulas={} if upstream else {"2026-01-01": formula},
        get_formula=lambda _year: None if upstream else formula,
    )


class _Rates:
    def __init__(self, calculator=_schedule) -> None:
        self.calculator = calculator

    def calc(self, taxable_income):
        return self.calculator(taxable_income)


class _Parameters:
    def __init__(self, calculator=_schedule) -> None:
        self._rates = _Rates(calculator)

    def __call__(self, _period):
        return self

    @property
    def gov(self):
        return self

    @property
    def states(self):
        return self

    @property
    def sc(self):
        return self

    @property
    def tax(self):
        return self

    @property
    def income(self):
        return self

    @property
    def rates(self):
        return self._rates


def _simulation(
    *,
    ids=(1, 2, 3),
    taxable=(0.0, 30_000.0, 100_000.0),
    tax=(0.0, 597.0, 4_244.0),
    schedule=_schedule,
    formula=_formula,
    target_definition=None,
    upstream_definition=None,
):
    calls = []

    class FakeSimulation:
        def __init__(self, dataset):
            assert dataset == "dataset"
            self.tax_benefit_system = SimpleNamespace(
                variables={
                    "sc_income_tax_before_non_refundable_credits": (
                        target_definition
                        or _definition(formula=formula)
                    ),
                    "sc_taxable_income": (
                        upstream_definition
                        or _definition(upstream=True)
                    ),
                },
                parameters=_Parameters(schedule),
            )

        def calculate(self, variable, period):
            assert period == 2026
            self.calls.append((variable, period))
            return {
                "tax_unit_id": ids,
                "sc_taxable_income": taxable,
                "sc_income_tax_before_non_refundable_credits": tax,
            }[variable]

    FakeSimulation.calls = calls
    return FakeSimulation


def _routes(ids):
    return tuple(
        TaxUnitRoute(item, item, "SC", "45", 1, DISPOSITION_READY)
        for item in ids
    )


def _targets(simulation, *, source_ids=(1, 2, 3), route_ids=None):
    return calculate_policyengine_targets(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": source_ids}),
        routes=_routes(source_ids if route_ids is None else route_ids),
        year=2026,
        microsimulation_factory=simulation,
    )


def _projections(simulation, *, source_ids=(1, 2, 3), route_ids=None):
    return calculate_policyengine_projection_inputs(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": source_ids}),
        routes=_routes(source_ids if route_ids is None else route_ids),
        year=2026,
        microsimulation_factory=simulation,
    )


def test_south_carolina_target_reads_only_ids_taxable_income_and_exact_tax() -> None:
    simulation = _simulation()

    assert _targets(simulation) == {
        "SC": {1: 0.0, 2: 597.0, 3: 4_244.0}
    }
    assert simulation.calls == [
        ("tax_unit_id", 2026),
        ("sc_taxable_income", 2026),
        ("sc_income_tax_before_non_refundable_credits", 2026),
    ]


def test_south_carolina_target_preserves_all_1457_routed_tax_units() -> None:
    ids = tuple(range(1, 1_458))
    taxable = tuple(float(max(0, item - 200) * 100) for item in ids)
    tax = tuple(_schedule(value) for value in taxable)

    result = _targets(
        _simulation(ids=ids, taxable=taxable, tax=tax),
        source_ids=ids,
    )

    assert len(result["SC"]) == 1_457
    assert tuple(result["SC"]) == ids
    assert sum(value == 0 for value in result["SC"].values()) == 200
    assert sum(value > 0 for value in result["SC"].values()) == 1_257


@pytest.mark.parametrize(
    ("ids", "taxable", "tax", "message"),
    [
        ((1, 2), (0.0, 30_000.0, 100_000.0), (0.0, 597.0, 4_244.0), "2, 3, 3"),
        ((1, 2, 3), (0.0, 30_000.0), (0.0, 597.0, 4_244.0), "3, 2, 3"),
        ((1, 2, 3), (0.0, 30_000.0, 100_000.0), (0.0, 597.0), "3, 3, 2"),
        ((2, 1, 3), (0.0, 30_000.0, 100_000.0), (0.0, 597.0, 4_244.0), "order"),
        ((1, 1, 3), (0.0, 30_000.0, 100_000.0), (0.0, 597.0, 4_244.0), "duplicate"),
    ],
)
def test_south_carolina_target_rejects_cardinality_and_identity_drift(
    ids,
    taxable,
    tax,
    message,
) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _targets(_simulation(ids=ids, taxable=taxable, tax=tax))


@pytest.mark.parametrize(
    ("taxable", "tax", "message"),
    [
        ((float("nan"), 30_000.0, 100_000.0), (0.0, 597.0, 4_244.0), "non-finite"),
        ((0.0, 30_000.0, 100_000.0), (float("inf"), 597.0, 4_244.0), "non-finite"),
        ((-1.0, 30_000.0, 100_000.0), (0.0, 597.0, 4_244.0), "nonnegative"),
        ((0.0, 30_000.0, 100_000.0), (-1.0, 597.0, 4_244.0), "nonnegative"),
        ((0.0, 30_000.0, 100_000.0), (1.0, 597.0, 4_244.0), "exactly zero"),
        ((0.0, 30_000.0, 100_000.0), (0.0, 0.0, 4_244.0), "must produce positive"),
    ],
)
def test_south_carolina_target_rejects_invalid_selected_values(
    taxable,
    tax,
    message,
) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _targets(_simulation(taxable=taxable, tax=tax))


@pytest.mark.parametrize(
    ("field", "value", "variable"),
    [
        ("entity", "person", "sc_income_tax_before_non_refundable_credits"),
        ("period", "month", "sc_taxable_income"),
        ("value_type", int, "sc_income_tax_before_non_refundable_credits"),
        ("unit", "USD", "sc_taxable_income"),
    ],
)
def test_south_carolina_rejects_target_and_upstream_schema_drift(
    field,
    value,
    variable,
) -> None:
    kwargs = {field: value}
    target = _definition(**kwargs) if variable.startswith("sc_income_tax") else None
    upstream = (
        _definition(upstream=True, **kwargs)
        if variable == "sc_taxable_income"
        else None
    )
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="TaxUnit/year/currency-USD float schema",
    ):
        _targets(
            _simulation(
                target_definition=target,
                upstream_definition=upstream,
            )
        )


def test_south_carolina_rejects_active_schedule_drift() -> None:
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="marginal-rate schedule",
    ):
        _targets(_simulation(schedule=lambda value: value * 0.05))


def test_south_carolina_rejects_active_dependency_drift() -> None:
    def drifted_formula(tax_unit, period, parameters):
        return tax_unit("sc_income_tax", period)

    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="dependency path",
    ):
        _targets(_simulation(formula=drifted_formula))


def test_south_carolina_projection_uses_only_reviewed_upstream_boundary() -> None:
    simulation = _simulation()
    projections = _projections(simulation)
    slot = (
        "us-sc:policies/income_tax/pilot_liability_pipeline#input."
        "sc_pit_pilot_state_taxable_income"
    )

    assert projections == {
        "SC": {slot: {1: 0.0, 2: 30_000.0, 3: 100_000.0}}
    }
    assert simulation.calls == [
        ("tax_unit_id", 2026),
        ("sc_taxable_income", 2026),
    ]


def test_south_carolina_projection_rejects_negative_selected_boundary() -> None:
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="sc_taxable_income boundary must be nonnegative",
    ):
        _projections(
            _simulation(taxable=(0.0, -1.0, 100_000.0)),
        )


def test_south_carolina_contract_requires_exact_inventory() -> None:
    jurisdiction = SimpleNamespace(
        policyengine_target="sc_income_tax",
        program="us-sc:policies/income_tax/pilot_liability_pipeline",
        output=(
            "us-sc:policies/income_tax/pilot_liability_pipeline"
            "#sc_pit_pilot_income_tax_liability"
        ),
        inputs=(),
        relations=(),
    )
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="exact sc_income_tax_before_non_refundable_credits target",
    ):
        _validate_south_carolina_runtime_contract(jurisdiction)
