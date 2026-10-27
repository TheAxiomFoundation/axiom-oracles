from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from axiom_oracles.bridges.state_tax_populace_runner import (
    DISPOSITION_READY,
    StateTaxPopulationRoutingError,
    TaxUnitRoute,
    _validate_indiana_runtime_contract,
    calculate_policyengine_projection_inputs,
    calculate_policyengine_targets,
)


def _formula(tax_unit, period, parameters):
    p = parameters(period).gov.states["in"].tax.income
    agi = tax_unit("in_agi", period)
    return max(0, agi * p.agi_rate)


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

    def __getitem__(self, key):
        assert key == "in"
        return self

    @property
    def tax(self):
        return self

    @property
    def income(self):
        return self

    @property
    def agi_rate(self):
        return self._rate


def _simulation(
    *,
    ids=(1, 2, 3),
    agi=(-100.0, 0.0, 10_000.0),
    tax=(0.0, 0.0, 295.0),
    rate=0.0295,
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
                    "in_agi_tax": (
                        target_definition
                        or _definition(formula=formula)
                    ),
                    "in_agi": (
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
                "in_agi": agi,
                "in_agi_tax": tax,
            }[variable]

    FakeSimulation.calls = calls
    return FakeSimulation


def _targets(simulation, *, source_ids=(1, 2, 3)):
    return calculate_policyengine_targets(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": source_ids}),
        routes=tuple(
            TaxUnitRoute(item, item, "IN", "18", 1, DISPOSITION_READY)
            for item in source_ids
        ),
        year=2026,
        microsimulation_factory=simulation,
    )


def _projections(simulation, *, source_ids=(1, 2, 3)):
    return calculate_policyengine_projection_inputs(
        dataset="dataset",
        raw_tax_units=pd.DataFrame({"tax_unit_id": source_ids}),
        routes=tuple(
            TaxUnitRoute(item, item, "IN", "18", 1, DISPOSITION_READY)
            for item in source_ids
        ),
        year=2026,
        microsimulation_factory=simulation,
    )


def test_indiana_target_reads_only_ids_agi_and_exact_agi_tax() -> None:
    simulation = _simulation()

    assert _targets(simulation) == {
        "IN": {1: 0.0, 2: 0.0, 3: 295.0}
    }
    assert simulation.calls == [
        ("tax_unit_id", 2026),
        ("in_agi", 2026),
        ("in_agi_tax", 2026),
    ]


def test_indiana_target_preserves_all_1292_routed_tax_units() -> None:
    ids = tuple(range(1, 1_293))
    agi = tuple(float((item - 100) * 1_000) for item in ids)
    tax = tuple(max(0.0, value * 0.0295) for value in agi)

    result = _targets(
        _simulation(ids=ids, agi=agi, tax=tax),
        source_ids=ids,
    )

    assert len(result["IN"]) == 1_292
    assert tuple(result["IN"]) == ids
    assert sum(value == 0 for value in result["IN"].values()) == 100
    assert sum(value > 0 for value in result["IN"].values()) == 1_192


@pytest.mark.parametrize(
    ("ids", "agi", "tax", "message"),
    [
        ((1, 2), (-100.0, 0.0, 10_000.0), (0.0, 0.0, 295.0), "2, 3, 3"),
        ((1, 2, 3), (-100.0, 0.0), (0.0, 0.0, 295.0), "3, 2, 3"),
        ((1, 2, 3), (-100.0, 0.0, 10_000.0), (0.0, 0.0), "3, 3, 2"),
        ((2, 1, 3), (-100.0, 0.0, 10_000.0), (0.0, 0.0, 295.0), "order"),
        ((1, 1, 3), (-100.0, 0.0, 10_000.0), (0.0, 0.0, 295.0), "duplicate"),
    ],
)
def test_indiana_target_rejects_cardinality_and_identity_drift(
    ids,
    agi,
    tax,
    message,
) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _targets(_simulation(ids=ids, agi=agi, tax=tax))


def test_indiana_target_rejects_duplicate_source_ids() -> None:
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="duplicate IN source tax_unit_id",
    ):
        _targets(
            _simulation(ids=(1, 1, 3)),
            source_ids=(1, 1, 3),
        )


@pytest.mark.parametrize(
    ("agi", "tax", "message"),
    [
        ((float("nan"), 0.0, 10_000.0), (0.0, 0.0, 295.0), "non-finite"),
        ((-100.0, 0.0, 10_000.0), (float("inf"), 0.0, 295.0), "non-finite"),
        ((-100.0, 0.0, 10_000.0), (-1.0, 0.0, 295.0), "nonnegative"),
        ((-100.0, 0.0, 10_000.0), (1.0, 0.0, 295.0), "exactly zero"),
        ((-100.0, 0.0, 10_000.0), (0.0, 0.0, 0.0), "must produce positive"),
    ],
)
def test_indiana_target_rejects_invalid_agi_tax_values(
    agi,
    tax,
    message,
) -> None:
    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _targets(_simulation(agi=agi, tax=tax))


@pytest.mark.parametrize("variable", ["in_agi_tax", "in_agi"])
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("entity", "person"),
        ("period", "month"),
        ("value_type", int),
        ("unit", "USD"),
    ],
)
def test_indiana_rejects_target_and_upstream_schema_drift(
    variable,
    field,
    value,
) -> None:
    kwargs = {
        "entity": "tax_unit",
        "period": "year",
        "value_type": float,
        "unit": "currency-USD",
        "upstream": variable == "in_agi",
    }
    kwargs[field] = value
    definition = _definition(**kwargs)
    simulation = _simulation(
        **{
            (
                "target_definition"
                if variable == "in_agi_tax"
                else "upstream_definition"
            ): definition
        }
    )

    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="TaxUnit/year/currency-USD float schema",
    ):
        _targets(simulation)


def test_indiana_rejects_active_rate_drift() -> None:
    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="rate must be exactly 0.0295",
    ):
        _targets(_simulation(rate=0.03))


def test_indiana_rejects_active_dependency_drift() -> None:
    def drifted_formula(tax_unit, period, parameters):
        parameters(period).gov.states["in"].tax.income.agi_rate
        return max(0, tax_unit("in_taxable_income", period) * 0.0295)

    with pytest.raises(
        StateTaxPopulationRoutingError,
        match="dependency path drifted",
    ):
        _targets(_simulation(formula=drifted_formula))


def test_indiana_projection_uses_only_the_reviewed_upstream_boundary() -> None:
    simulation = _simulation()

    assert _projections(simulation) == {
        "IN": {
            (
                "us-in:policies/income_tax/pilot_liability_pipeline#input."
                "in_pit_pilot_indiana_adjusted_gross_income"
            ): {1: -100.0, 2: 0.0, 3: 10_000.0}
        }
    }
    assert simulation.calls == [
        ("tax_unit_id", 2026),
        ("in_agi", 2026),
    ]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("policyengine_target", "in_income_tax", "exact in_agi_tax target"),
        ("program", "us-in:policies/income_tax/other", "exact canonical"),
        (
            "output",
            "us-in:policies/income_tax/pilot_liability_pipeline#other",
            "exact canonical",
        ),
        ("inputs", (), "exactly the completed Indiana"),
        ("relations", (object(),), "no relations"),
    ],
)
def test_indiana_contract_drift_fails_closed(field, value, message) -> None:
    slot = SimpleNamespace(
        slot=(
            "us-in:policies/income_tax/pilot_liability_pipeline#input."
            "in_pit_pilot_indiana_adjusted_gross_income"
        ),
        source_kind="pe_upstream_boundary",
        status="ready",
        policyengine_variable="in_agi",
        policyengine_variables=(),
        policyengine_relationship="upstream",
        policyengine_transform=None,
        constant_value=None,
    )
    jurisdiction = SimpleNamespace(
        policyengine_target="in_agi_tax",
        program="us-in:policies/income_tax/pilot_liability_pipeline",
        output=(
            "us-in:policies/income_tax/pilot_liability_pipeline#"
            "in_pit_pilot_income_tax_liability"
        ),
        inputs=(slot,),
        relations=(),
    )
    setattr(jurisdiction, field, value)

    with pytest.raises(StateTaxPopulationRoutingError, match=message):
        _validate_indiana_runtime_contract(jurisdiction)
