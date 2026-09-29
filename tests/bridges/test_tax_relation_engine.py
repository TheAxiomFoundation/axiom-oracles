"""Optional real-engine regression for the federal relation producer.

Set AXIOM_STRICT_RELATION_ENGINE_BIN to a #190 strict-binding engine and
AXIOM_RULESPEC_ROOT to a rulespec-us checkout. AXIOM_LEGACY_RELATION_ENGINE_BIN
optionally reproduces the silent zero with the post-#179, pre-#190 engine.
The compiled law and the reference case come unchanged from rulespec-us.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess

import pandas as pd
import pytest
import yaml

from axiom_oracles.bridges.tax_populace import (
    CDCC_BASE,
    CTC_BASE,
    _runtime_axiom_request,
    build_cdcc_request,
    build_ctc_request,
    output_number,
    scalar_value,
)


_RELATION = f"{CDCC_BASE}#relation.qualifying_individual_of_tax_unit"
_OUTPUT = f"{CDCC_BASE}#cdcc"
_CTC_OUTPUT = f"{CTC_BASE}#ctc_before_advance_payments"


def _configured_path(variable: str) -> Path:
    value = os.environ.get(variable)
    if not value or not Path(value).exists():
        pytest.skip(f"{variable} must point to an existing live-test prerequisite")
    return Path(value).resolve()


@pytest.fixture(scope="module")
def live_cdcc(tmp_path_factory):
    binary = _configured_path("AXIOM_STRICT_RELATION_ENGINE_BIN")
    source_root = _configured_path("AXIOM_RULESPEC_ROOT")
    relative = Path("us/statutes/26/21.yaml")
    source = source_root / relative
    if not source.is_file():
        pytest.skip(f"The canonical CDCC RuleSpec is unavailable: {source}")
    examples = yaml.safe_load(source.with_suffix(".test.yaml").read_text())
    example = next(
        case for case in examples if case["name"] == "single_one_child_low_agi_credit"
    )
    directory = tmp_path_factory.mktemp("tax-relation-engine")
    rulespec_root = directory / "rulespec-us"
    program = rulespec_root / relative
    program.parent.mkdir(parents=True)
    # Use the existing encoded module verbatim in a clean canonical layout.
    # Some local checkouts retain root-level statutes/ rejected by new engines.
    shutil.copyfile(source, program)
    artifact_path = directory / "cdcc.compiled.json"
    compiled = subprocess.run(
        [
            str(binary), "compile", "--program", str(program),
            "--rulespec-root", str(rulespec_root), "--output", str(artifact_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert compiled.returncode == 0, compiled.stderr
    artifact = json.loads(artifact_path.read_text())
    assert artifact["program"]["relations"][0]["slot_entities"] == [
        "TaxUnit", "Person",
    ]
    return binary, artifact_path, artifact, rulespec_root, example


@pytest.fixture(scope="module")
def live_ctc(tmp_path_factory):
    binary = _configured_path("AXIOM_STRICT_RELATION_ENGINE_BIN")
    source_root = _configured_path("AXIOM_RULESPEC_ROOT")
    directory = tmp_path_factory.mktemp("ctc-relation-engine")
    rulespec_root = directory / "rulespec-us"
    for relative in ("us/statutes/26/24.yaml", "us/statutes/26/24/h.yaml"):
        source = source_root / relative
        if not source.is_file():
            pytest.skip(f"The canonical CTC RuleSpec is unavailable: {source}")
        target = rulespec_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    artifact_path = directory / "ctc.compiled.json"
    compiled = subprocess.run(
        [
            str(binary), "compile", "--program",
            str(rulespec_root / "us/statutes/26/24.yaml"),
            "--rulespec-root", str(rulespec_root), "--output", str(artifact_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert compiled.returncode == 0, compiled.stderr
    artifact = json.loads(artifact_path.read_text())
    return binary, artifact_path, artifact


def _one_child_data():
    return {
        "tax_units": pd.DataFrame([
            {
                "tax_unit_id": 1,
                "filing_status": "SINGLE",
                "adjusted_gross_income": 15_000,
                "min_head_spouse_earned": 10_000,
                "tax_unit_childcare_expenses": 5_000,
                "cdcc_credit_limit": 5_000,
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


def _run(binary, artifact_path, request):
    assert "relation_binding" not in request
    return subprocess.run(
        [str(binary), "run-compiled", "--artifact", str(artifact_path)],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def _credit(result, output=_OUTPUT):
    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    return output_number(response["results"][0]["outputs"][output])


def _owner_first_reference(example):
    """Turn the encoded module's existing companion case into a wire request."""
    interval = example["period"]
    inputs = []
    relations = []

    def append_inputs(values, entity_id, entity):
        for name, value in values.items():
            inputs.append({
                "name": name,
                "entity_id": entity_id,
                "entity": entity,
                "interval": interval,
                "value": scalar_value(value),
            })

    owner_inputs = dict(example["input"])
    for index, person in enumerate(owner_inputs.pop(_RELATION)):
        person_id = f"reference_person_{index}"
        append_inputs(person, person_id, "Person")
        relations.append({
            "name": _RELATION,
            "tuple": ["reference_tax_unit", person_id],
            "interval": interval,
        })
    append_inputs(owner_inputs, "reference_tax_unit", "TaxUnit")
    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": relations},
        "queries": [{
            "entity_id": "reference_tax_unit",
            "period": interval,
            "outputs": [_OUTPUT],
        }],
    }


@pytest.mark.parametrize("entrypoint", ["builder", "compiled_runtime"])
def test_cdcc_strict_binding_matches_encoded_owner_first_reference(
    live_cdcc, entrypoint,
):
    binary, artifact_path, artifact, rulespec_root, example = live_cdcc
    if entrypoint == "builder":
        request = build_cdcc_request(
            pe_data=_one_child_data(), year=2026, artifact=artifact,
        )
    else:
        legacy_request = build_cdcc_request(pe_data=_one_child_data(), year=2026)
        request, _ = _runtime_axiom_request(
            legacy_request, artifact_payload=artifact, rulespec_root=rulespec_root,
        )
    assert all(
        relation["tuple"][0] == "tax_unit_1"
        for relation in request["dataset"]["relations"]
    )
    assert {record["entity"] for record in request["dataset"]["inputs"]} == {
        "TaxUnit", "Person",
    }
    result = _run(binary, artifact_path, request)
    reference = _run(binary, artifact_path, _owner_first_reference(example))
    assert _credit(result) == _credit(reference) == example["output"][_OUTPUT] == 1500
    assert json.loads(result.stdout)["metadata"]["relation_binding"] == "strict"

    # The same real engine must reject both defects in the previous producer.
    reversed_request = copy.deepcopy(request)
    for relation in reversed_request["dataset"]["relations"]:
        relation["tuple"].reverse()
    reversed_result = _run(binary, artifact_path, reversed_request)
    assert reversed_result.returncode != 0
    assert "relation" in reversed_result.stderr.lower()

    generic_kinds = copy.deepcopy(request)
    for record in generic_kinds["dataset"]["inputs"]:
        record["entity"] = "Entity"
    generic_result = _run(binary, artifact_path, generic_kinds)
    assert generic_result.returncode != 0
    assert "Entity" in generic_result.stderr


def test_cdcc_pre_strict_engine_reproduces_silent_zero(live_cdcc):
    _, artifact_path, artifact, _, _ = live_cdcc
    binary = _configured_path("AXIOM_LEGACY_RELATION_ENGINE_BIN")
    corrected = build_cdcc_request(
        pe_data=_one_child_data(), year=2026, artifact=artifact,
    )
    legacy = copy.deepcopy(corrected)
    for relation in legacy["dataset"]["relations"]:
        relation["tuple"].reverse()
    for record in legacy["dataset"]["inputs"]:
        record["entity"] = "Entity"
    assert _credit(_run(binary, artifact_path, legacy)) == 0
    assert _credit(_run(binary, artifact_path, corrected)) == 1500


def test_ctc_strict_binding_counts_child_in_both_statutory_relations(live_ctc):
    binary, artifact_path, artifact = live_ctc
    request = build_ctc_request(
        pe_data=_one_child_data(), year=2026, artifact=artifact,
    )
    assert {record["entity"] for record in request["dataset"]["inputs"]} == {
        "TaxUnit", "Person",
    }
    assert len({relation["name"] for relation in request["dataset"]["relations"]}) == 2
    assert all(
        relation["tuple"][0] == "tax_unit_1"
        for relation in request["dataset"]["relations"]
    )
    result = _run(binary, artifact_path, request)
    assert _credit(result, f"{CTC_BASE}#ctc_qualifying_children_count") == 1
    assert _credit(result, f"{CTC_BASE}#ctc_maximum_before_phaseout") == 2200
    assert _credit(result, _CTC_OUTPUT) == 2200
    assert json.loads(result.stdout)["metadata"]["relation_binding"] == "strict"


def test_ctc_pre_strict_engine_reproduces_silent_zero(live_ctc):
    _, artifact_path, artifact = live_ctc
    binary = _configured_path("AXIOM_LEGACY_RELATION_ENGINE_BIN")
    corrected = build_ctc_request(
        pe_data=_one_child_data(), year=2026, artifact=artifact,
    )
    legacy = build_ctc_request(pe_data=_one_child_data(), year=2026)
    for record in legacy["dataset"]["inputs"]:
        record["entity"] = "Entity"
    assert _credit(_run(binary, artifact_path, legacy), _CTC_OUTPUT) == 0
    assert _credit(_run(binary, artifact_path, corrected), _CTC_OUTPUT) == 2200
