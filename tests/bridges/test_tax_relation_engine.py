"""Optional real-engine regression for the federal relation producer.

Set AXIOM_STRICT_RELATION_ENGINE_BIN to the pinned mandatory-typing engine and
AXIOM_RULESPEC_ROOT to a rulespec-us checkout. AXIOM_LEGACY_RELATION_ENGINE_BIN
optionally reproduces the silent zero with the post-#179, pre-#190 engine.
AXIOM_REQUIRE_RELATION_ENGINE_TESTS=1 makes missing prerequisites fail in CI.
The compiled law and the reference case come unchanged from rulespec-us.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import warnings

import pandas as pd
import pytest
import yaml

from axiom_oracles.adapters.axiom import runner, tax_projection
from axiom_oracles.bridges.relation_binding import (
    RelationBindingAmbiguityWarning,
    bind_request_relations,
)
from axiom_oracles.core.case import Case, Concepts, Entity
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


def _missing_prerequisite(message: str) -> None:
    if os.environ.get("AXIOM_REQUIRE_RELATION_ENGINE_TESTS") == "1":
        pytest.fail(message, pytrace=False)
    pytest.skip(message)


def _configured_path(variable: str) -> Path:
    value = os.environ.get(variable)
    if not value or not Path(value).exists():
        _missing_prerequisite(
            f"{variable} must point to an existing live-test prerequisite"
        )
    return Path(value).resolve()


@pytest.mark.parametrize("variable", [
    "AXIOM_STRICT_RELATION_ENGINE_BIN",
    "AXIOM_LEGACY_RELATION_ENGINE_BIN",
    "AXIOM_RULESPEC_ROOT",
])
@pytest.mark.parametrize("configured", [False, True])
def test_required_native_prerequisites_fail_instead_of_skip(
    monkeypatch, tmp_path, variable, configured,
):
    monkeypatch.setenv("AXIOM_REQUIRE_RELATION_ENGINE_TESTS", "1")
    if configured:
        monkeypatch.setenv(variable, str(tmp_path / "missing"))
    else:
        monkeypatch.delenv(variable, raising=False)
    with pytest.raises(pytest.fail.Exception, match=variable):
        try:
            _configured_path(variable)
        except pytest.skip.Exception as error:
            raise AssertionError("Required native tests must not skip") from error


@pytest.fixture(scope="module")
def live_cdcc(tmp_path_factory):
    binary = _configured_path("AXIOM_STRICT_RELATION_ENGINE_BIN")
    source_root = _configured_path("AXIOM_RULESPEC_ROOT")
    relative = Path("us/statutes/26/21.yaml")
    source = source_root / relative
    if not source.is_file():
        _missing_prerequisite(f"The canonical CDCC RuleSpec is unavailable: {source}")
    companion = source.with_suffix(".test.yaml")
    if not companion.is_file():
        _missing_prerequisite(f"The canonical CDCC companion is unavailable: {companion}")
    examples = yaml.safe_load(companion.read_text())
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
            _missing_prerequisite(f"The canonical CTC RuleSpec is unavailable: {source}")
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


def test_real_ctc_tax_case_batch_warns_for_executed_untyped_relations(live_ctc, tmp_path):
    """Pre-typing bridge relations preserve legacy roles and warn when used."""
    binary, _, compiled = live_ctc
    artifact = copy.deepcopy(compiled)
    bridge_relations = [
        name for name in tax_projection._RELATION_REFS
        if name.startswith("us:tax/oracle-bridge#")
    ]
    assert len(bridge_relations) == 5
    for index, name in enumerate(bridge_relations):
        # These are the generated bridge's five untyped data declarations.
        artifact["program"]["relations"].append({"name": name, "arity": 2})
        if "co_withheld_income_tax_member_of_tax_unit" not in name:
            artifact["program"]["derived"].append({
                "name": f"bridge_count_{index}", "entity": "TaxUnit",
                "dtype": "integer", "semantics": "scalar",
                "expr": {"kind": "count_related", "relation": name,
                         "current_slot": 1, "related_slot": 0},
            })
    artifact_path = tmp_path / "ctc-with-bridge-data.compiled.json"
    artifact_path.write_text(json.dumps(artifact))
    cases = [
        tax_projection.attach_axiom_tax_inputs_to_case(Case(
            case_id=f"tax-{index}", period="2026", entities=(
                Entity(f"head-{index}", "Person", facts={
                    Concepts.PERSON_AGE: 38,
                    Concepts.YEARLY_EARNED_INCOME: 30_000,
                    Concepts.HOUSEHOLD_RELATION: "head",
                }),
                Entity(f"child-{index}", "Person", facts={
                    Concepts.PERSON_AGE: 8, Concepts.HOUSEHOLD_RELATION: "child",
                }),
            ), metadata={"state": "CO"},
        ))
        for index in range(3)
    ]

    def fake_run(command, **kwargs):
        request = json.loads(kwargs["input"])
        assert all("roles" not in row for row in request["dataset"]["relations"])
        assert all(
            row["tuple"][1].endswith("::tax_unit")
            for row in request["dataset"]["relations"]
            if row["name"] in bridge_relations
        )
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps({"results": [{"outputs": {}}] * 3}),
            stderr="",
        )

    adapter = runner.AxiomRulesRunner(binary_path=binary, subprocess_run=fake_run)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", RelationBindingAmbiguityWarning)
        results = adapter._run_case_batch_once(cases, ["unused_output"], artifact_path)
    assert len(results) == 3
    assert not caught
    expected_counts = {
        "us:tax/oracle-bridge#relation.business_income_of_tax_unit": 2,
        "us:tax/oracle-bridge#relation.co_dependent_of_tax_unit": 1,
        "us:tax/oracle-bridge#relation.filer_adjusted_earnings_of_tax_unit": 1,
        "us:tax/oracle-bridge#relation.payroll_member_of_tax_unit": 2,
    }
    for result in results:
        diagnostics = result.raw["relation_binding_diagnostics"]
        assert diagnostics["count"] == 6
        assert diagnostics["by_relation"] == expected_counts
        assert all(
            sample["tuple"][1].endswith("::tax_unit")
            for sample in diagnostics["samples"]
        )


@pytest.mark.parametrize("mode", ["explain", "fast"])
def test_public_relation_alias_ignores_unrelated_same_fragment(mode):
    """Public references resolve by the engine's bare key, without a name scan."""
    binary = _configured_path("AXIOM_STRICT_RELATION_ENGINE_BIN")
    fixture = Path(__file__).parents[1] / "fixtures/relation_binding/typed-relation-binding.json"
    request = json.loads(fixture.read_text())
    request["mode"] = mode
    request["program"]["derived"][-1]["id"] = "us:statutes/26/21#credit"
    request["queries"][0]["outputs"] = [
        "qualifying_person_count", "us:statutes/26/21#credit",
    ]
    request["dataset"]["relations"][0]["name"] = (
        "us:statutes/26/21#relation.qualifying_person_of_tax_unit"
    )
    extended = copy.deepcopy(request)
    extended["program"]["relations"].append({
        "name": "us:statutes/26/999#relation.qualifying_person_of_tax_unit",
        "arity": 2, "slot_entities": ["Household", "Payment"],
    })
    for candidate in (request, extended):
        native = subprocess.run(
            [str(binary), "run"], input=json.dumps(candidate),
            capture_output=True, text=True, check=False, timeout=60,
        )
        assert native.returncode == 0, native.stderr
        output = json.loads(native.stdout)["results"][0]["outputs"]
        assert output_number(output["us:statutes/26/21#credit"]) == 1500
        assert bind_request_relations(candidate, {"program": candidate["program"]}) == candidate
