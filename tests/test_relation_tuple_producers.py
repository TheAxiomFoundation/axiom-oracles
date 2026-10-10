"""Producers put explicit owner/member roles in the executable slots."""

import json
import os
import subprocess
from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest

from axiom_oracles.adapters.axiom import generic_inputs, runner, snap_co_projection
from axiom_oracles.bridges import efrs_uk, snap_populace, tax_populace
from axiom_oracles.core.case import Case, Entity
from axiom_oracles.suites import be_worker


_NATIVE_RUN = subprocess.run


def _artifact(names, owner_kind, member_kind, current_slot, typed):
    slots = [member_kind, owner_kind] if current_slot else [owner_kind, member_kind]
    return {"program": {
        "relations": [
            {"name": name, "arity": 2, **({"slot_entities": slots} if typed else {})}
            for name in names
        ],
        "derived": [
            {"name": f"count-{index}", "entity": owner_kind, "expr": {
                "kind": "count_related", "relation": name,
                "current_slot": current_slot, "related_slot": 1 - current_slot,
            }}
            for index, name in enumerate(names)
        ],
    }}


def _assert_count(records, owner_id, member_ids, current_slot):
    names = sorted({record["name"] for record in records})
    for name in names:
        tuples = [record["tuple"] for record in records if record["name"] == name]
        assert len(tuples) == len(member_ids)
        # The count_related operation joins the owner against current_slot.
        assert sum(tup[current_slot] == owner_id for tup in tuples) == len(member_ids)
        assert {tup[1 - current_slot] for tup in tuples} == set(member_ids)
    binary = os.environ.get("AXIOM_STRICT_RELATION_ENGINE_BIN")
    if not binary or not Path(binary).is_file():
        if os.environ.get("AXIOM_REQUIRE_RELATION_ENGINE_TESTS") == "1":
            pytest.fail("AXIOM_STRICT_RELATION_ENGINE_BIN must exist for native producer counts")
        return
    starts = [row.get("interval", {}).get("start", "2026-01-01") for row in records]
    ends = [row.get("interval", {}).get("end", "2026-12-31") for row in records]
    interval = {"start": min(starts), "end": max(ends)}
    period_kind = "month" if interval["start"][:7] == interval["end"][:7] else "tax_year"
    outputs = [f"producer_count_{index}" for index in range(len(names))]
    native_request = {
        "mode": "fast",
        "program": {
            "relations": [{"name": name, "arity": 2} for name in names],
            "derived": [{
                "name": output, "entity": "Owner", "dtype": "integer", "semantics": "scalar",
                "expr": {"kind": "count_related", "relation": name,
                         "current_slot": current_slot, "related_slot": 1 - current_slot},
            } for name, output in zip(names, outputs, strict=True)],
        },
        "dataset": {"inputs": [], "relations": [
            {key: value for key, value in record.items() if key != "roles"}
            | {"interval": record.get("interval", interval)}
            for record in records
        ]},
        "queries": [{"entity_id": owner_id, "period": {"period_kind": period_kind, **interval},
                     "outputs": outputs}],
    }
    result = _NATIVE_RUN([binary, "run"], input=json.dumps(native_request),
                         text=True, capture_output=True, check=False, timeout=60)
    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    assert response["metadata"]["relation_binding"] == "strict"
    assert [int(response["results"][0]["outputs"][name]["value"]["value"])
            for name in outputs] == [len(member_ids)] * len(names)


@pytest.mark.parametrize("current_slot", [0, 1])
@pytest.mark.parametrize("typed", [False, True])
@pytest.mark.parametrize("owner_kind", ["Household", "SnapUnit", "TaxUnit", "Person"])
def test_generic_producer_orders_explicit_roles(tmp_path, current_slot, typed, owner_kind):
    relation = "us:statutes/7/2012/j#relation.member_of_household"
    artifact = _artifact([relation], owner_kind, "Person", current_slot, typed)
    path = tmp_path / "generic.compiled.json"
    path.write_text(json.dumps(artifact))
    [case] = generic_inputs.attach_generic_inputs(
        [Case("case", "2026-01", entities=(Entity("alice", "Person"),))],
        compiled_program_path=path, load_default_mapping=False,
        **({"household_entity": "Person"} if owner_kind == "Person" else {}),
    )
    _assert_count(case.metadata["axiom_relations"], "household", ["member-0"], current_slot)
    _assert_adapter_case(case, artifact, path, "household", ["member-0"], current_slot)


@pytest.mark.parametrize("current_slot", [0, 1])
@pytest.mark.parametrize("typed", [False, True])
def test_co_snap_producer_orders_explicit_roles(monkeypatch, tmp_path, current_slot, typed):
    names = [snap_co_projection._MEMBER_RELATION, snap_co_projection._MEMBER_RELATION_RUNTIME]
    artifact = _artifact(names, "Household", "Person", current_slot, typed)
    path = tmp_path / "snap.compiled.json"
    path.write_text(json.dumps(artifact))
    monkeypatch.setattr(snap_co_projection, "US_SNAP_CO_COMPILED_ARTIFACT_PATH", path)
    monkeypatch.setattr(snap_co_projection, "_supported_input_records", lambda records: records)
    [case] = snap_co_projection.attach_axiom_snap_co_inputs(
        [Case("case", "2026-01", entities=(Entity("alice", "Person"),))]
    )
    _assert_count(case.metadata["axiom_relations"], "household", ["snap-member-0"], current_slot)
    _assert_adapter_case(case, artifact, path, "household", ["snap-member-0"], current_slot)


def _assert_adapter_case(case, artifact, path, owner_id, member_ids, current_slot):
    before = deepcopy(case.metadata)
    def fake_run(cmd, **kwargs):
        request = json.loads(kwargs["input"])
        _assert_count(request["dataset"]["relations"], f"case-0::{owner_id}",
                      [f"case-0::{member}" for member in member_ids], current_slot)
        assert all("roles" not in row for row in request["dataset"]["relations"])
        return subprocess.CompletedProcess(cmd, 0, stdout='{"results": [{"outputs": {}}]}', stderr="")

    adapter = runner.AxiomRulesRunner(binary_path=path.parent / "engine", subprocess_run=fake_run)
    adapter._run_case_batch_once([case], ["count"], path)
    assert case.metadata == before


@pytest.mark.parametrize("current_slot", [0, 1])
@pytest.mark.parametrize("typed", [False, True])
def test_snap_bridge_constructs_order_before_binding(monkeypatch, tmp_path, current_slot, typed):
    config = snap_populace.JURISDICTION_CONFIGS["us-ca"]
    names = [config.relation_id, *config.additional_relation_ids]
    artifact = _artifact(names, "Household", "Person", current_slot, typed)
    path = tmp_path / "snap.compiled.json"
    path.write_text(json.dumps(artifact))

    def no_inference(request, artifact):
        _assert_count(request["dataset"]["relations"], "spm-42", ["spm-42-member-1"], current_slot)
        return request

    def fake_run(cmd, **kwargs):
        request = json.loads(kwargs["input"])
        _assert_count(request["dataset"]["relations"], "spm-42", ["spm-42-member-1"], current_slot)
        return subprocess.CompletedProcess(cmd, 0, stdout='{"results": []}', stderr="")

    monkeypatch.setattr(snap_populace, "bind_request_relations", no_inference)
    monkeypatch.setattr(snap_populace.subprocess, "run", fake_run)
    snap_populace.run_axiom_cases(
        binary=tmp_path / "engine", artifact=path,
        cases=[snap_populace.ProjectedCase(
            spm_unit_id=42, household_id=420, inputs={}, member_inputs=[{}], pe_outputs={},
        )],
        period=snap_populace.Period(
            label="2026-01", year=2026, month=1,
            start=date(2026, 1, 1), end=date(2026, 1, 31),
        ),
        output_ids=["count"], relation_id=config.relation_id,
        additional_relation_ids=config.additional_relation_ids,
        member_entity_type="Person", env={},
    )


@pytest.mark.parametrize("current_slot", [0, 1])
@pytest.mark.parametrize("typed", [False, True])
def test_efrs_producer_orders_roles_after_compilation(monkeypatch, tmp_path, current_slot, typed):
    relation = f"{efrs_uk.INCOME_TAX_SECTION_23_BASE}#relation.income_component_of_taxpayer"
    artifact = _artifact([relation], "Person", "Payment", current_slot, typed)
    request = efrs_uk.build_income_tax_income_base_request(
        pe_data={"persons": [{"person_id": 7, "employment_income": 30000}], "person_ids": [7]},
        year=2026,
    )

    def no_inference(request, artifact):
        _assert_count(request["dataset"]["relations"], "person_7", ["person_7_income_employment_income"], current_slot)
        assert all("roles" not in row for row in request["dataset"]["relations"])
        return request

    monkeypatch.setattr(tax_populace, "bind_request_relations", no_inference)
    runtime, _ = tax_populace._runtime_axiom_request(
        request, artifact_payload=artifact, rulespec_root=tmp_path / "rulespec-uk",
    )
    _assert_count(runtime["dataset"]["relations"], "person_7", ["person_7_income_employment_income"], current_slot)


@pytest.mark.parametrize("current_slot", [0, 1])
@pytest.mark.parametrize("batch", [False, True])
def test_adapter_materializes_explicit_roles(monkeypatch, tmp_path, current_slot, batch):
    relation = "us:statutes/26/63#relation.tax_unit_member"
    artifact = _artifact([relation], "TaxUnit", "Person", current_slot, False)
    path = tmp_path / "adapter.compiled.json"
    path.write_text(json.dumps(artifact))
    case = Case("case", "2026-01", metadata={
        "axiom_entity": "TaxUnit", "axiom_entity_id": "owner",
        "axiom_relations": [{"name": relation, "tuple": ["member", "owner"], "roles": {
            "owner_id": "owner", "owner_kind": "TaxUnit",
            "related_id": "member", "related_kind": "Person", "legacy_owner_slot": 1,
        }}],
    })
    owner = "case-0::owner" if batch else "owner"
    member = "case-0::member" if batch else "member"

    def no_inference(request, artifact):
        _assert_count(request["dataset"]["relations"], owner, [member], current_slot)
        assert all("roles" not in row for row in request["dataset"]["relations"])
        return request

    def fake_run(cmd, **kwargs):
        no_inference(json.loads(kwargs["input"]), artifact)
        return subprocess.CompletedProcess(cmd, 0, stdout='{"results": [{"outputs": {}}]}', stderr="")

    monkeypatch.setattr(runner, "bind_request_relations", no_inference)
    adapter = runner.AxiomRulesRunner(binary_path=tmp_path / "engine", subprocess_run=fake_run)
    if batch:
        adapter._run_case_batch_once([case], ["count"], path)
    else:
        adapter._run_case_once(case, ["count"], path)


@pytest.mark.parametrize("current_slot", [0, 1])
@pytest.mark.parametrize("typed", [False, True])
def test_belgium_couple_producer_orders_explicit_roles(monkeypatch, tmp_path, current_slot, typed):
    artifact = _artifact([be_worker.COUPLE_SPOUSE_RELATION], "TaxUnit", "Person", current_slot, typed)
    path = tmp_path / "belgium.compiled.json"
    path.write_text(json.dumps(artifact))
    case = be_worker._single_earner_couple_pit_case("couple", 30000)

    def no_inference(request, artifact):
        _assert_count(request["dataset"]["relations"], "case-0::taxunit", ["case-0::head", "case-0::spouse"], current_slot)
        assert all("roles" not in row for row in request["dataset"]["relations"])
        return request

    def fake_run(cmd, **kwargs):
        no_inference(json.loads(kwargs["input"]), artifact)
        return subprocess.CompletedProcess(cmd, 0, stdout='{"results": [{"outputs": {}}]}', stderr="")

    monkeypatch.setattr(runner, "bind_request_relations", no_inference)
    adapter = runner.AxiomRulesRunner(binary_path=tmp_path / "engine", subprocess_run=fake_run)
    adapter._run_case_batch_once([case], ["count"], path)
