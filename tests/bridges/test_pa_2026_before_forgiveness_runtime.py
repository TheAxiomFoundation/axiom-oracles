from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from axiom_oracles.bridges.state_tax_populace_runner import (
    DISPOSITION_READY,
    StateTaxPopulationRoutingError,
    TaxUnitRoute,
    _validate_pennsylvania_runtime_contract,
    calculate_policyengine_projection_inputs,
    calculate_policyengine_targets,
)


def _formula(tax_unit, period, parameters):
    taxable_income = tax_unit("pa_adjusted_taxable_income", period)
    rate = parameters(period).gov.states.pa.tax.income.rate
    return taxable_income * rate


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
        formulas={} if upstream else {"0001-01-01": formula},
        get_formula=lambda _year: None if upstream else formula,
    )


class _Parameters:
    def __init__(self, rate: float) -> None:
        self._rate = rate

    def __call__(self, _period):
        return self

    @property
    def gov(self):
        return self

    @property
    def states(self):
        return self

    @property
    def pa(self):
        return self

    @property
    def tax(self):
        return self

    @property
    def income(self):
        return self

    @property
    def rate(self):
        return self._rate


def _simulation(
    *,
    ids=(1, 2, 3),
    taxable=(0.0, 0.0, 10_000.0),
    tax=(0.0, 0.0, 307.0),
    rate=0.0307,
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
                    "pa_income_tax_before_forgiveness": (
                        target_definition
                        or _definition(formula=formula)
                    ),
                    "pa_adjusted_taxable_income": (
                        upstream_definition
                        or _definition(upstream=True)
                    ),
                },
                parameters=_Parameters(rate),
            )

        def calculate(self, variable, period):
            assert period == 2026
            self.calls.append((variable, period))
            return {
                "tax_unit_id": ids,
                "pa_adjusted_taxable_income": taxable,
                "pa_income_tax_before_forgiveness": tax,
            }[variable]

    FakeSimulation.calls = calls
    return FakeSimulation


def _routes(ids):
    return tuple(
        TaxUnitRoute(item, item, "PA", "42", 1, DISPOSITION_READY)
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


def test_pennsylvania_target_reads_only_ids_taxable_income_and_exact_tax() -> None:
    simulation = _simulation()

    assert _targets(simulation) == {
        "PA": {1: 0.0, 2: 0.0, 3: 307.0}
    }
    assert simulation.calls == [
        ("tax_unit_id", 2026),
        ("pa_adjusted_taxable_income", 2026),
        ("pa_income_tax_before_forgiveness", 2026),
    ]


def test_pennsylvania_target_preserves_all_2457_routed_tax_units() -> None:
    ids = tuple(range(1, 2_458))
    taxable = tuple(float(max(0, item - 700) * 100) for item in ids)
    tax = tuple(value * 0.0307 for value in taxable)

    result = _targets(
        _simulation(ids=ids, taxable=taxable, tax=tax),
        source_ids=ids,
    )

    assert len(result["PA"]) == 2_457
    assert tuple(result["PA"]) == ids
    assert sum(value == 0 for value in result["PA"].values()) == 700
    assert sum(value > 0 for value in result["PA"].values()) == 1_757


@pytest.mark.parametrize(
    ("ids", "taxable", "tax", "message"),
    [
        ((1, 2), (0.0, 0.0, 10_000.0), (0.0, 0.0, 307.0), "2, 3, 3"),
        ((1, 2, 3), (0.0, 10_000.0), (0.0, 0.0, 307.0), "3, 2, 3"),
        ((1, 2, 3), (0.0, 0.0, 10_000.0), (0.0, 307.0), "3, 3, 2"),
        ((2, 1, 3), (0.0, 0.0, 10_000.0), (0.0, 0.0, 307.0), "order"),
        ((1, 1, 3), (0.0, 0.0, 10_000.0), (0.0, 0.0, 307.0), "duplicate"),
    ],
)
def test_pennsylvania_target_rejects_cardinality_and_identity_drift(
    ids,
    taxable,
    tax,
    message,
) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _targets(_simulation(ids=ids, taxable=taxable, tax=tax))


def test_pennsylvania_target_rejects_duplicate_source_ids() -> None:
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="duplicate PA source tax_unit_id",
    ):
        _targets(
            _simulation(ids=(1, 1, 3)),
            source_ids=(1, 1, 3),
        )


@pytest.mark.parametrize(
    ("taxable", "tax", "message"),
    [
        (
            (float("nan"), 0.0, 10_000.0),
            (0.0, 0.0, 307.0),
            "non-finite",
        ),
        (
            (0.0, 0.0, 10_000.0),
            (float("inf"), 0.0, 307.0),
            "non-finite",
        ),
        ((-1.0, 0.0, 10_000.0), (-0.0307, 0.0, 307.0), "nonnegative"),
        ((0.0, 0.0, 10_000.0), (-1.0, 0.0, 307.0), "nonnegative"),
        ((0.0, 0.0, 10_000.0), (1.0, 0.0, 307.0), "exactly zero"),
        ((0.0, 0.0, 10_000.0), (0.0, 0.0, 0.0), "must produce positive"),
        ((1.0, 2.0, 3.0), (0.0307, 0.0614, 0.0921), "zero and positive"),
        ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), "zero and positive"),
    ],
)
def test_pennsylvania_target_rejects_invalid_selected_values(
    taxable,
    tax,
    message,
) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _targets(_simulation(taxable=taxable, tax=tax))


def test_pennsylvania_negative_unselected_value_does_not_expand_scope() -> None:
    result = _targets(
        _simulation(
            taxable=(-1.0, 0.0, 10_000.0),
            tax=(-0.0307, 0.0, 307.0),
        ),
        route_ids=(2, 3),
    )

    assert result["PA"] == {1: -0.0307, 2: 0.0, 3: 307.0}


@pytest.mark.parametrize(
    "variable",
    ["pa_income_tax_before_forgiveness", "pa_adjusted_taxable_income"],
)
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("entity", "person"),
        ("period", "month"),
        ("value_type", int),
        ("unit", "USD"),
    ],
)
def test_pennsylvania_rejects_target_and_upstream_schema_drift(
    variable,
    field,
    value,
) -> None:
    kwargs = {
        "entity": "tax_unit",
        "period": "year",
        "value_type": float,
        "unit": "currency-USD",
        "upstream": variable == "pa_adjusted_taxable_income",
    }
    kwargs[field] = value
    definition = _definition(**kwargs)
    simulation = _simulation(
        **{
            (
                "target_definition"
                if variable == "pa_income_tax_before_forgiveness"
                else "upstream_definition"
            ): definition
        }
    )

    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="TaxUnit/year/currency-USD float schema",
    ):
        _targets(simulation)


def test_pennsylvania_rejects_active_rate_drift() -> None:
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="rate must be exactly 0.0307",
    ):
        _targets(_simulation(rate=0.031))


def test_pennsylvania_rejects_active_dependency_drift() -> None:
    def drifted_formula(tax_unit, period, parameters):
        rate = parameters(period).gov.states.pa.tax.income.rate
        return tax_unit("pa_total_taxable_income", period) * rate

    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="dependency path drifted",
    ):
        _targets(_simulation(formula=drifted_formula))


def test_pennsylvania_projection_uses_only_reviewed_upstream_boundary() -> None:
    simulation = _simulation()

    assert _projections(simulation) == {
        "PA": {
            (
                "us-pa:policies/income_tax/pilot_liability_pipeline#input."
                "pa_pit_pilot_state_taxable_income"
            ): {1: 0.0, 2: 0.0, 3: 10_000.0}
        }
    }
    assert simulation.calls == [
        ("tax_unit_id", 2026),
        ("pa_adjusted_taxable_income", 2026),
    ]


def test_pennsylvania_projection_rejects_negative_selected_boundary() -> None:
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="every selected pa_adjusted_taxable_income boundary",
    ):
        _projections(
            _simulation(
                taxable=(-1.0, 0.0, 10_000.0),
                tax=(-0.0307, 0.0, 307.0),
            )
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "policyengine_target",
            "pa_income_tax",
            "exact pa_income_tax_before_forgiveness target",
        ),
        (
            "program",
            "us-pa:policies/income_tax/other",
            "exact canonical",
        ),
        (
            "output",
            "us-pa:policies/income_tax/pilot_liability_pipeline#other",
            "exact canonical",
        ),
        ("inputs", (), "exactly the completed Pennsylvania"),
        ("relations", (object(),), "no relations"),
    ],
)
def test_pennsylvania_contract_drift_fails_closed(field, value, message) -> None:
    slot = SimpleNamespace(
        slot=(
            "us-pa:policies/income_tax/pilot_liability_pipeline#input."
            "pa_pit_pilot_state_taxable_income"
        ),
        source_kind="pe_upstream_boundary",
        status="ready",
        policyengine_variable="pa_adjusted_taxable_income",
        policyengine_variables=(),
        policyengine_relationship="upstream",
        policyengine_transform=None,
        constant_value=None,
    )
    jurisdiction = SimpleNamespace(
        policyengine_target="pa_income_tax_before_forgiveness",
        program="us-pa:policies/income_tax/pilot_liability_pipeline",
        output=(
            "us-pa:policies/income_tax/pilot_liability_pipeline#"
            "pa_pit_pilot_income_tax_liability"
        ),
        inputs=(slot,),
        relations=(),
    )
    setattr(jurisdiction, field, value)

    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _validate_pennsylvania_runtime_contract(jurisdiction)
