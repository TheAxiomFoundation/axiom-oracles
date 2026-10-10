"""Tax producers use known endpoint roles, even without identity inference."""

from __future__ import annotations

from copy import deepcopy
from collections import Counter
import json
import os
from pathlib import Path
import subprocess

import pandas as pd
import pytest

from axiom_oracles.adapters.axiom import tax_projection
from axiom_oracles.bridges import state_tax_populace_runner, tax_populace
from axiom_oracles.core.case import Case, Concepts, Entity


def _artifact(names: set[str], current_slot: int) -> dict:
    return {
        "program": {
            "relations": [{"name": name, "arity": 2} for name in sorted(names)],
            "derived": [
                {
                    "name": f"count_{index}",
                    "entity": "TaxUnit",
                    "dtype": "integer",
                    "semantics": "scalar",
                    "expr": {
                        "kind": "count_related",
                        "relation": name,
                        "current_slot": current_slot,
                        "related_slot": 1 - current_slot,
                    },
                }
                for index, name in enumerate(sorted(names))
            ],
        }
    }


def _assert_native_counts(runtime: dict, artifact: dict, owner_id: str) -> None:
    """Replay the real tuples through strict count semantics when configured."""
    configured = os.environ.get("AXIOM_STRICT_RELATION_ENGINE_BIN")
    if not configured:
        if os.environ.get("AXIOM_REQUIRE_RELATION_ENGINE_TESTS") == "1":
            pytest.fail("Pinned strict relation engine is required")
        return
    assert Path(configured).is_file(), "Configured strict relation engine is missing"
    records = deepcopy(runtime["dataset"]["relations"])
    counts = Counter(record["name"] for record in records)
    interval = {
        "period_kind": "tax_year", "start": "2026-01-01", "end": "2026-12-31",
    }
    for record in records:
        # Case metadata deliberately delegates the execution period to its
        # adapter; other producer records already carry this same interval.
        record.setdefault("interval", interval)
        assert record["interval"] == interval
    expected = {
        rule["name"]: counts[rule["expr"]["relation"]]
        for rule in artifact["program"]["derived"]
    }
    native_request = {
        "mode": "explain",
        "program": artifact["program"],
        "dataset": {"inputs": [], "relations": records},
        "queries": [{
            "entity_id": owner_id, "period": interval, "outputs": list(expected),
        }],
    }
    result = subprocess.run(
        [configured, "run"], input=json.dumps(native_request),
        text=True, capture_output=True, check=False, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    assert response["metadata"]["relation_binding"] == "strict"
    outputs = response["results"][0]["outputs"]
    assert {name: int(value["value"]["value"]) for name, value in outputs.items()} == expected


def _population() -> dict:
    return {
        "tax_units": pd.DataFrame([
            {
                "tax_unit_id": 1,
                "filing_status": "SINGLE",
                "adjusted_gross_income": 15_000,
                "min_head_spouse_earned": 10_000,
                "tax_unit_childcare_expenses": 5_000,
                "cdcc_credit_limit": 5_000,
                "income_tax_before_credits": 5_000,
            }
        ]),
        "persons": pd.DataFrame([
            {
                "person_id": 7,
                "person_tax_unit_id": 1,
                "age": 38,
                "ssn_card_type": "CITIZEN",
                "is_tax_unit_head": True,
                "is_tax_unit_spouse": False,
            },
            {
                "person_id": 8,
                "person_tax_unit_id": 1,
                "age": 8,
                "ssn_card_type": "CITIZEN",
                "is_tax_unit_head": False,
                "is_tax_unit_spouse": False,
            },
        ]),
        "tax_unit_ids": [1],
    }


def _tax_request(surface: str, artifact: dict | None = None) -> dict:
    return tax_populace.build_axiom_request(
        pe_data=_population(), year=2026, surface=surface,
        contribution_base=186_000, artifact=artifact,
    )


@pytest.mark.parametrize("surface", ["ctc", "cdcc", "aotc", "eitc"])
@pytest.mark.parametrize("current_slot", [0, 1])
@pytest.mark.parametrize("compiled_before_projection", [False, True])
def test_federal_producers_follow_executable_roles_without_binder_inference(
    monkeypatch, tmp_path, surface, current_slot, compiled_before_projection,
):
    # Producers must work when the binder has no evidence with which to repair
    # their wire. Explicit construction is independently checked against slots.
    monkeypatch.setattr(tax_populace, "bind_request_relations", lambda request, _: request)
    original = _tax_request(surface)
    names = {record["name"] for record in original["dataset"]["relations"]}
    assert names
    artifact = _artifact(names, current_slot)
    request = _tax_request(surface, artifact if compiled_before_projection else None)
    original_request = deepcopy(request)
    runtime, _ = tax_populace._runtime_axiom_request(
        request, artifact_payload=artifact, rulespec_root=tmp_path / "rulespec-us",
    )
    assert request == original_request
    assert {record["name"] for record in runtime["dataset"]["relations"]} == names
    for record in runtime["dataset"]["relations"]:
        assert record["tuple"][current_slot] == "tax_unit_1"
        assert record["tuple"][1 - current_slot].startswith("tax_unit_1_person_")
        assert "roles" not in record
    assert {record["entity"] for record in runtime["dataset"]["inputs"]} == {
        "TaxUnit", "Person",
    }
    _assert_native_counts(runtime, artifact, "tax_unit_1")


def _state_request(artifact: dict | None = None) -> dict:
    runner = state_tax_populace_runner
    prefix = "us-dc:policies/income_tax/pilot_liability_pipeline"
    return runner._state_request(
        state="DC",
        routes=(runner.TaxUnitRoute(1, 1, "DC", "11", 1, runner.DISPOSITION_READY),),
        year=2026,
        output=f"{prefix}#tax",
        projected_inputs={
            f"{prefix}#input.dc_pit_pilot_supplied_separate_taxable_income": {11: 30_000.0},
            f"{prefix}#input.dc_pit_pilot_taxpayer_is_included": {11: True},
            f"{prefix}#input.dc_pit_pilot_supplied_joint_taxable_income": {1: 30_000.0},
        },
        declared_relations=(f"{prefix}#relation.dc_pit_pilot_taxpayer_of_tax_unit",),
        raw_persons=pd.DataFrame({"person_id": [11], "person_tax_unit_id": [1]}),
        **({"artifact": artifact} if artifact is not None else {}),
    )


@pytest.mark.parametrize("current_slot", [0, 1])
@pytest.mark.parametrize("compiled_before_projection", [False, True])
def test_state_producer_follows_executable_roles_without_binder_inference(
    monkeypatch, tmp_path, current_slot, compiled_before_projection,
):
    monkeypatch.setattr(tax_populace, "bind_request_relations", lambda request, _: request)
    source = _state_request()
    names = {record["name"] for record in source["dataset"]["relations"]}
    artifact = _artifact(names, current_slot)
    request = _state_request(artifact if compiled_before_projection else None)
    runtime, _ = tax_populace._runtime_axiom_request(
        request, artifact_payload=artifact, rulespec_root=tmp_path / "rulespec-us-dc",
    )
    assert len(runtime["dataset"]["relations"]) == 1
    record = runtime["dataset"]["relations"][0]
    assert record["tuple"][current_slot] == "state-tax-unit-1"
    assert record["tuple"][1 - current_slot] == "state-tax-person-11"
    assert "roles" not in record
    _assert_native_counts(runtime, artifact, "state-tax-unit-1")


def _case() -> Case:
    return Case(
        case_id="tax-role-family", period="2026",
        entities=tuple(
            Entity(
                entity_id, "person",
                facts={Concepts.HOUSEHOLD_RELATION: relation, Concepts.PERSON_AGE: age},
            )
            for entity_id, relation, age in (
                ("person-1", "HeadOfHousehold", 40),
                ("person-2", "Spouse", 38),
                ("person-3", "Child", 8),
            )
        ),
    )


@pytest.mark.parametrize("current_slot", [0, 1])
def test_tax_case_projection_carries_roles_for_every_relation_family(
    monkeypatch, tmp_path, current_slot,
):
    monkeypatch.setattr(tax_populace, "bind_request_relations", lambda request, _: request)
    projected = tax_projection.attach_axiom_tax_inputs_to_case(_case())
    records = projected.metadata["axiom_relations"]
    names = {record["name"] for record in records}
    assert names == set(tax_projection._RELATION_REFS)
    assert len(records) == 29
    request = {
        "dataset": {"inputs": projected.metadata["axiom_input_records"], "relations": records},
        "queries": [],
    }
    original = deepcopy(request)
    artifact = _artifact(names, current_slot)
    runtime, _ = tax_populace._runtime_axiom_request(
        request, artifact_payload=artifact,
        rulespec_root=tmp_path / "rulespec-us",
    )
    assert request == original
    assert len(runtime["dataset"]["relations"]) == len(records)
    for record in runtime["dataset"]["relations"]:
        assert record["tuple"][current_slot] == "tax_unit"
        assert record["tuple"][1 - current_slot] in {"person-1", "person-2", "person-3"}
        assert "roles" not in record
    _assert_native_counts(runtime, artifact, "tax_unit")
