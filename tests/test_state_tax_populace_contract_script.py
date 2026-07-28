from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from axiom_oracles.bridges.state_tax_populace import (
    StateTaxPopulaceContractError,
    load_state_tax_populace_contract,
)
from scripts.check_state_tax_populace_contract import _validate_generator_registry, main


def test_contract_check_reports_readiness(capsys) -> None:
    assert main([]) == 0

    output = capsys.readouterr().out
    assert "43 jurisdictions" in output
    assert "32 ready" in output
    assert "11 blocked" in output
    assert "134 explicit inputs" in output
    assert "0 explicit relations" in output


def test_contract_check_json_is_machine_readable(capsys) -> None:
    assert main(["--json"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["ready_states"] == [
        "AL",
        "AR",
        "AZ",
        "CA",
        "CO",
        "CT",
        "DC",
        "DE",
        "GA",
        "HI",
        "IA",
        "IL",
        "IN",
        "KS",
        "KY",
        "LA",
        "MI",
        "MN",
        "MS",
        "MT",
        "NC",
        "NJ",
        "NM",
        "NY",
        "OH",
        "OK",
        "PA",
        "SC",
        "UT",
        "VA",
        "VT",
        "WV",
    ]
    assert len(output["blocked_states"]) == 11


def test_contract_check_fails_closed_for_missing_override(tmp_path, capsys) -> None:
    missing = tmp_path / "missing.yaml"

    assert main(["--contract", str(missing)]) == 1
    assert "contract invalid" in capsys.readouterr().err


def test_generator_registry_validation_fails_on_drift(monkeypatch) -> None:
    contract = load_state_tax_populace_contract()
    fake_spec = SimpleNamespace(
        name="fake_state_income_tax_generator",
        loader=SimpleNamespace(exec_module=lambda module: None)
    )
    monkeypatch.setattr(
        "scripts.check_state_tax_populace_contract.importlib.util.spec_from_file_location",
        lambda *args: fake_spec,
    )
    monkeypatch.setattr(
        "scripts.check_state_tax_populace_contract.importlib.util.module_from_spec",
        lambda spec: SimpleNamespace(
            _STATES=(),
            _POPULACE_STATES=tuple(
                item.state for item in contract.jurisdictions
            ),
            VALIDATION_YEAR=2026,
            _TAXSIM_STATE={item.state: item.taxsim_state_code for item in contract.jurisdictions},
            _MODULE={item.state: item.program for item in contract.jurisdictions},
            _LIABILITY_OUTPUT={item.state: item.output for item in contract.jurisdictions},
            _PE_VAR={
                item.state: (
                    "drifted_target"
                    if item.state == "NJ"
                    else item.policyengine_target
                )
                for item in contract.jurisdictions
            },
            _TOL={
                item.state: (item.tolerance, item.relative_tolerance)
                for item in contract.jurisdictions
            },
            _POPULACE_AGGREGATION={
                item.state: item.comparison_aggregation
                for item in contract.jurisdictions
            },
        ),
    )

    with pytest.raises(StateTaxPopulaceContractError, match="NJ registry metadata"):
        _validate_generator_registry(contract)
