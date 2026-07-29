"""End-to-end tests for the generated AUTOGO certified-node list.

The fixtures deliberately exercise the public CLI and producer artifacts.  A
mutant is useful only when the exact rejected input is committed beside the
test, so the six launch-critical mutants live under ``fixtures/autogo``.
"""

from __future__ import annotations

import json
import hashlib
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "certify_nodes.py"
FIXTURES = Path(__file__).parent / "fixtures" / "autogo"
NODE = "us:statutes/26/3101/b/1#medicare_wage_tax"
DEPENDENCY = "us:statutes/26/3121/a#medicare_wage_base"

BASE_INPUTS = {
    "artifact": FIXTURES / "artifact.json",
    "node-index": FIXTURES / "node-index.json",
    "closure-summary": FIXTURES / "closure-summary.json",
    "comparisons": FIXTURES / "comparisons.json",
    "exercise-census": FIXTURES / "exercise-census.json",
    "executable": FIXTURES / "executable.json",
    "run-manifest": FIXTURES / "run-manifest.json",
    "governance": FIXTURES / "workflow-governance.json",
}

RUN_INPUT_KEYS = {
    "artifact": "compiled_artifact",
    "node-index": "node_index",
    "closure-summary": "closure_summary",
    "comparisons": "node_comparisons",
    "exercise-census": "exercise_census",
    "executable": "node_executable",
    "governance": "workflow_governance",
}


def _run(
    tmp_path: Path,
    *,
    overrides: dict[str, Path] | None = None,
    check: bool = False,
    output: Path | None = None,
    reasons_output: Path | None = None,
    repo_root: Path | None = None,
    nodes: tuple[str, ...] = (NODE,),
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    inputs = {**BASE_INPUTS, **(overrides or {})}
    output = output or tmp_path / "certified-nodes.yaml"
    reasons_output = reasons_output or tmp_path / "certify-reasons.json"
    repo_root = repo_root or FIXTURES
    command = [
        sys.executable,
        str(SCRIPT),
        *nodes,
        "--repo-root",
        str(repo_root),
    ]
    for option, path in inputs.items():
        command.extend((f"--{option}", str(path)))
    command.extend(("--output", str(output), "--reasons-output", str(reasons_output)))
    if check:
        command.append("--check")
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result, output, reasons_output


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _copy_fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "fixture-root"
    shutil.copytree(FIXTURES, root)
    return root


def _bind_run_manifest(
    tmp_path: Path,
    overrides: dict[str, Path],
) -> dict[str, Path]:
    inputs = {**BASE_INPUTS, **overrides}
    run = json.loads((FIXTURES / "run-manifest.json").read_text())
    for option, run_key in RUN_INPUT_KEYS.items():
        path = inputs[option]
        if path.exists():
            run["inputs"][run_key] = hashlib.sha256(path.read_bytes()).hexdigest()
    path = tmp_path / "bound-run-manifest.json"
    _write_json(path, run)
    return {**overrides, "run-manifest": path}


def _inputs_pinned_to_artifact(
    tmp_path: Path,
    artifact: Path,
) -> tuple[dict[str, Path], Path]:
    """Re-pin supporting producers so a provenance mutant tests only provenance."""
    fixture_root = tmp_path / "repinned-fixture"
    artifact_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()

    report_source = FIXTURES / "reports" / "us-medicare-wage-tax.json"
    report_target = fixture_root / "reports" / report_source.name
    report_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(report_source, report_target)

    receipt = json.loads(
        (FIXTURES / "receipts" / "us-medicare-wage-tax.json").read_text()
    )
    receipt["artifact"]["sha256"] = artifact_sha
    receipt_path = fixture_root / "receipts" / "us-medicare-wage-tax.json"
    _write_json(receipt_path, receipt)
    receipt_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest()

    output_bindings_source = (
        FIXTURES / "manifests" / "us-medicare-golden-outputs.json"
    )
    output_bindings_path = (
        fixture_root / "manifests" / "us-medicare-golden-outputs.json"
    )
    output_bindings_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(output_bindings_source, output_bindings_path)
    output_bindings_sha = hashlib.sha256(output_bindings_path.read_bytes()).hexdigest()

    manifest = json.loads(
        (FIXTURES / "manifests" / "us-medicare.json").read_text()
    )
    manifest["artifact"]["sha256"] = artifact_sha
    manifest["golden"]["outputs_sha256"] = output_bindings_sha
    manifest_path = fixture_root / "manifests" / "us-medicare.json"
    _write_json(manifest_path, manifest)
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    node_index = json.loads((FIXTURES / "node-index.json").read_text())
    node_index["artifact_sha256"] = artifact_sha
    node_index_path = fixture_root / "node-index.json"
    _write_json(node_index_path, node_index)

    comparisons = json.loads((FIXTURES / "comparisons.json").read_text())
    comparisons["artifact_sha256"] = artifact_sha
    comparisons["comparisons"]["us-medicare-wage-tax"]["pinned"][
        "artifact"
    ] = artifact_sha
    comparisons_path = fixture_root / "comparisons.json"
    _write_json(comparisons_path, comparisons)

    executable = json.loads((FIXTURES / "executable.json").read_text())
    executable["artifact_sha256"] = artifact_sha
    executable["nodes"][NODE]["pinned"]["artifact"] = artifact_sha
    executable["nodes"][NODE]["manifest"]["sha256"] = manifest_sha
    executable["nodes"][NODE]["receipt"]["sha256"] = receipt_sha
    executable_path = fixture_root / "executable.json"
    _write_json(executable_path, executable)

    run_manifest = json.loads((FIXTURES / "run-manifest.json").read_text())
    run_manifest["pinned"]["artifact"] = artifact_sha
    run_manifest["inputs"].update(
        {
            "compiled_artifact": artifact_sha,
            "node_index": hashlib.sha256(node_index_path.read_bytes()).hexdigest(),
            "closure_summary": hashlib.sha256(
                BASE_INPUTS["closure-summary"].read_bytes()
            ).hexdigest(),
            "node_comparisons": hashlib.sha256(
                comparisons_path.read_bytes()
            ).hexdigest(),
            "exercise_census": hashlib.sha256(
                BASE_INPUTS["exercise-census"].read_bytes()
            ).hexdigest(),
            "node_executable": hashlib.sha256(
                executable_path.read_bytes()
            ).hexdigest(),
            "workflow_governance": hashlib.sha256(
                BASE_INPUTS["governance"].read_bytes()
            ).hexdigest(),
        }
    )
    run_manifest_path = fixture_root / "run-manifest.json"
    _write_json(run_manifest_path, run_manifest)

    return (
        {
            "artifact": artifact,
            "node-index": node_index_path,
            "comparisons": comparisons_path,
            "executable": executable_path,
            "run-manifest": run_manifest_path,
        },
        fixture_root,
    )


def _stdout_json(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    assert result.stdout.strip(), f"expected JSON stdout; stderr={result.stderr!r}"
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        pytest.fail(f"stdout is not one JSON document: {error}\n{result.stdout}")
    assert isinstance(payload, dict)
    return payload


def _reason_rows(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if isinstance(value.get("code"), str):
            rows.append(value)
        for child in value.values():
            rows.extend(_reason_rows(child))
    elif isinstance(value, list):
        for child in value:
            rows.extend(_reason_rows(child))
    return rows


def _assert_reason(path: Path, *, code: str, criterion: str) -> None:
    assert path.exists(), f"missing machine-readable reasons artifact {path}"
    payload = json.loads(path.read_text())
    _assert_reason_payload(payload, code=code, criterion=criterion)


def _assert_reason_payload(payload: Any, *, code: str, criterion: str) -> None:
    rows = _reason_rows(payload)
    assert any(
        row.get("code") == code and row.get("criterion") == criterion for row in rows
    ), f"expected {criterion}/{code}, got {rows!r}"


def _assert_node_result(payload: dict[str, Any], *, certified: bool) -> None:
    certified_nodes = payload.get("certified")
    assert isinstance(certified_nodes, list)
    assert (NODE in certified_nodes) is certified
    rejected = payload.get("rejected")
    assert isinstance(rejected, list)
    assert any(row.get("node") == NODE for row in rejected) is not certified


def _yaml_nodes(path: Path) -> list[dict[str, Any]]:
    payload = yaml.safe_load(path.read_text())
    assert payload["schema"] == "axiom.certified_nodes.v1"
    assert payload["generated"] is True
    assert isinstance(payload["nodes"], list)
    return payload["nodes"]


def test_green_baseline_writes_exact_entry_and_checks_without_mutating(
    tmp_path: Path,
) -> None:
    result, output, reasons = _run(tmp_path)

    assert result.returncode == 0, result.stderr
    summary = _stdout_json(result)
    _assert_node_result(summary, certified=True)
    [entry] = _yaml_nodes(output)
    assert entry["node"] == NODE
    assert set(entry["criteria"]) == {
        "provision_rooted",
        "conformant",
        "exercised",
        "closed",
        "executable",
    }
    assert all(row["holds"] is True for row in entry["criteria"].values())
    assert set(entry["harness"]) == {"run", "certify_check"}
    assert set(entry["pinned"]) == {
        "rulespec_us",
        "corpus",
        "engine",
        "artifact",
    }
    rendered = output.read_text()
    assert all(f"#   {index}." in rendered for index in range(1, 7))
    executable_evidence = entry["criteria"]["executable"]["evidence"]
    assert executable_evidence["index_sha256"] != executable_evidence[
        "receipt_sha256"
    ]
    assert isinstance(yaml.safe_load(rendered)["nodes"][0]["certified_at"], str)
    assert reasons.exists()

    before = output.read_bytes()
    check_result, _, _ = _run(
        tmp_path,
        check=True,
        output=output,
        reasons_output=reasons,
    )
    assert check_result.returncode == 0, check_result.stderr
    check_summary = _stdout_json(check_result)
    _assert_node_result(check_summary, certified=True)
    assert check_summary["drift"] == {
        "certified_nodes": False,
        "reasons": False,
    }
    assert output.read_bytes() == before


@pytest.mark.parametrize(
    ("option", "mutant", "code", "criterion"),
    [
        (
            "artifact",
            "mutant-unverified-provenance.json",
            "provision_rooted.unverified",
            "provision_rooted",
        ),
        (
            "closure-summary",
            "mutant-closure-pending.json",
            "closed.pending",
            "closed",
        ),
        (
            "comparisons",
            "mutant-axiom-attributed-mismatch.json",
            "conformant.axiom_attributed",
            "conformant",
        ),
        (
            "exercise-census",
            "mutant-dimension-constant.json",
            "exercised.dimension_constant",
            "exercised",
        ),
    ],
)
def test_committed_mutants_fail_closed_with_machine_reason(
    tmp_path: Path,
    option: str,
    mutant: str,
    code: str,
    criterion: str,
) -> None:
    overrides = {option: FIXTURES / mutant}
    repo_root = FIXTURES
    if option == "artifact":
        overrides, repo_root = _inputs_pinned_to_artifact(
            tmp_path,
            FIXTURES / mutant,
        )
    result, output, reasons = _run(
        tmp_path,
        overrides=overrides,
        repo_root=repo_root,
    )

    assert result.returncode != 0
    summary = _stdout_json(result)
    _assert_node_result(summary, certified=False)
    _assert_reason(reasons, code=code, criterion=criterion)
    if output.exists():
        assert all(row["node"] != NODE for row in _yaml_nodes(output))


def test_bridged_required_dimension_contributes_zero_fidelity(tmp_path: Path) -> None:
    census = json.loads((FIXTURES / "exercise-census.json").read_text())
    bridged = deepcopy(census)
    bridged["suites"]["us-medicare-wage-tax"]["bridged_through"] = {
        "wages": "mutant bridge satisfies wages by construction"
    }
    mutant_path = tmp_path / "mutant-dimension-bridged.json"
    mutant_path.write_text(json.dumps(bridged, indent=2, sort_keys=True) + "\n")

    result, _, reasons = _run(
        tmp_path,
        overrides={"exercise-census": mutant_path},
    )

    assert result.returncode != 0
    _assert_node_result(_stdout_json(result), certified=False)
    _assert_reason(
        reasons,
        code="exercised.dimension_bridged",
        criterion="exercised",
    )


def test_unaudited_bridge_declaration_cannot_hide_a_bridge(tmp_path: Path) -> None:
    census = json.loads((FIXTURES / "exercise-census.json").read_text())
    census["suites"]["us-medicare-wage-tax"]["bridge_audited"] = False
    mutant_path = tmp_path / "mutant-bridge-unaudited.json"
    _write_json(mutant_path, census)

    result, _, reasons = _run(
        tmp_path,
        overrides={"exercise-census": mutant_path},
    )

    assert result.returncode != 0
    _assert_node_result(_stdout_json(result), certified=False)
    _assert_reason(
        reasons,
        code="exercised.bridge_unaudited",
        criterion="exercised",
    )


def test_comparison_error_is_not_evidence(tmp_path: Path) -> None:
    comparisons = json.loads((FIXTURES / "comparisons.json").read_text())
    comparisons["comparisons"]["us-medicare-wage-tax"]["error_count"] = 1
    mutant_path = tmp_path / "mutant-comparison-error.json"
    _write_json(mutant_path, comparisons)

    result, _, reasons = _run(
        tmp_path,
        overrides={"comparisons": mutant_path},
    )

    assert result.returncode != 0
    _assert_node_result(_stdout_json(result), certified=False)
    _assert_reason(reasons, code="conformant.errors", criterion="conformant")


def test_dependency_cycle_fails_closed(tmp_path: Path) -> None:
    artifact = json.loads((FIXTURES / "artifact.json").read_text())
    dependency = "us:statutes/26/3121/a#medicare_wage_base"
    artifact["metadata"]["dependency_graph"][dependency] = [NODE]
    mutant_path = tmp_path / "mutant-dependency-cycle.json"
    _write_json(mutant_path, artifact)
    overrides, fixture_root = _inputs_pinned_to_artifact(tmp_path, mutant_path)

    result, _, reasons = _run(
        tmp_path,
        overrides=overrides,
        repo_root=fixture_root,
    )

    assert result.returncode != 0
    _assert_node_result(_stdout_json(result), certified=False)
    _assert_reason(
        reasons,
        code="provision_rooted.graph_invalid",
        criterion="provision_rooted",
    )


@pytest.mark.parametrize(
    ("option", "criterion", "code"),
    [
        ("artifact", "provision_rooted", "provision_rooted.producer_missing"),
        ("closure-summary", "closed", "closed.producer_missing"),
        ("comparisons", "conformant", "conformant.producer_missing"),
        ("exercise-census", "exercised", "exercised.producer_missing"),
        ("executable", "executable", "executable.producer_missing"),
    ],
)
def test_missing_each_criterion_producer_fails_closed(
    tmp_path: Path,
    option: str,
    criterion: str,
    code: str,
) -> None:
    missing = tmp_path / f"missing-{option}.json"
    result, _, reasons = _run(tmp_path, overrides={option: missing})

    assert result.returncode != 0
    _assert_node_result(_stdout_json(result), certified=False)
    _assert_reason(
        reasons,
        code=code,
        criterion=criterion,
    )


def test_hand_added_entry_is_output_drift_and_check_does_not_mutate(
    tmp_path: Path,
) -> None:
    write_result, output, reasons = _run(tmp_path)
    assert write_result.returncode == 0, write_result.stderr
    baseline = output.read_text()
    mutant = (FIXTURES / "mutant-hand-added-entry.yaml").read_text().rstrip()
    list_item = "- " + mutant.replace("\n", "\n  ") + "\n"
    marker = "\n# Entry shape — written only by the harness."
    assert marker in baseline
    output.write_text(baseline.replace(marker, "\n" + list_item + marker, 1))
    assert output.read_text().startswith(baseline.split("schema:", 1)[0])
    before = output.read_bytes()
    reasons_before = reasons.read_bytes()

    result, _, _ = _run(
        tmp_path,
        check=True,
        output=output,
        reasons_output=reasons,
    )

    assert result.returncode != 0
    summary = _stdout_json(result)
    _assert_node_result(summary, certified=True)
    assert summary["drift"]["certified_nodes"] is True
    _assert_reason_payload(
        summary["output_reasons"],
        code="output.drift",
        criterion="output",
    )
    assert output.read_bytes() == before
    assert reasons.read_bytes() == reasons_before


def test_regressed_node_fails_check_then_write_removes_stale_green_entry(
    tmp_path: Path,
) -> None:
    write_result, output, reasons = _run(tmp_path)
    assert write_result.returncode == 0, write_result.stderr
    before = output.read_bytes()
    reasons_before = reasons.read_bytes()
    override = {
        "executable": FIXTURES / "mutant-regressed-executable.json",
    }

    check_result, _, _ = _run(
        tmp_path,
        overrides=override,
        check=True,
        output=output,
        reasons_output=reasons,
    )
    assert check_result.returncode != 0
    check_summary = _stdout_json(check_result)
    _assert_node_result(check_summary, certified=False)
    assert check_summary["drift"] == {
        "certified_nodes": True,
        "reasons": True,
    }
    _assert_reason_payload(
        check_summary["output_reasons"],
        code="output.drift",
        criterion="output",
    )
    _assert_reason_payload(
        check_summary,
        code="executable.unvalidated",
        criterion="executable",
    )
    assert output.read_bytes() == before
    assert reasons.read_bytes() == reasons_before

    rewrite_result, _, _ = _run(
        tmp_path,
        overrides=override,
        output=output,
        reasons_output=reasons,
    )
    assert rewrite_result.returncode != 0
    _assert_node_result(_stdout_json(rewrite_result), certified=False)
    assert all(row["node"] != NODE for row in _yaml_nodes(output))


def test_foreign_comparison_report_cannot_be_rekeyed_green(tmp_path: Path) -> None:
    root = _copy_fixture_root(tmp_path)
    report = json.loads(
        (root / "reports" / "us-medicare-wage-tax.json").read_text()
    )
    report["suite"] = "foreign-suite"
    foreign_path = root / "reports" / "foreign-suite.json"
    _write_json(foreign_path, report)
    report_sha = hashlib.sha256(foreign_path.read_bytes()).hexdigest()

    comparisons = json.loads((root / "comparisons.json").read_text())
    comparison = comparisons["comparisons"]["us-medicare-wage-tax"]
    comparison["report"] = {
        "path": "reports/foreign-suite.json",
        "sha256": report_sha,
    }
    comparisons_path = root / "foreign-comparisons.json"
    _write_json(comparisons_path, comparisons)

    census = json.loads((root / "exercise-census.json").read_text())
    census_row = census["suites"]["us-medicare-wage-tax"]
    census_row["report"] = "reports/foreign-suite.json"
    census_row["report_sha256"] = report_sha
    census_path = root / "foreign-census.json"
    _write_json(census_path, census)

    overrides = _bind_run_manifest(
        tmp_path,
        {
            "comparisons": comparisons_path,
            "exercise-census": census_path,
        },
    )
    result, _, reasons = _run(
        tmp_path,
        overrides=overrides,
        repo_root=root,
    )

    assert result.returncode != 0
    _assert_reason(
        reasons,
        code="conformant.report_invalid",
        criterion="conformant",
    )


def test_producer_report_path_cannot_escape_repository(tmp_path: Path) -> None:
    comparisons = json.loads((FIXTURES / "comparisons.json").read_text())
    comparisons["comparisons"]["us-medicare-wage-tax"]["report"]["path"] = (
        "../outside.json"
    )
    path = tmp_path / "path-escape-comparisons.json"
    _write_json(path, comparisons)
    overrides = _bind_run_manifest(tmp_path, {"comparisons": path})

    result, _, reasons = _run(tmp_path, overrides=overrides)

    assert result.returncode != 0
    _assert_reason(
        reasons,
        code="conformant.report_missing",
        criterion="conformant",
    )


def test_foreign_program_receipt_cannot_be_rekeyed_to_node(tmp_path: Path) -> None:
    root = _copy_fixture_root(tmp_path)
    receipt_path = root / "receipts" / "us-medicare-wage-tax.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["program"] = "foreign/program"
    _write_json(receipt_path, receipt)

    executable = json.loads((root / "executable.json").read_text())
    executable["nodes"][NODE]["receipt"]["sha256"] = hashlib.sha256(
        receipt_path.read_bytes()
    ).hexdigest()
    executable_path = root / "foreign-executable.json"
    _write_json(executable_path, executable)
    overrides = _bind_run_manifest(tmp_path, {"executable": executable_path})

    result, _, reasons = _run(
        tmp_path,
        overrides=overrides,
        repo_root=root,
    )

    assert result.returncode != 0
    _assert_reason(
        reasons,
        code="executable.receipt_invalid",
        criterion="executable",
    )


def test_workflow_sha_must_be_separately_governed(tmp_path: Path) -> None:
    governance = json.loads(
        (FIXTURES / "workflow-governance.json").read_text()
    )
    governance["allowed_workflow_shas"] = [
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    ]
    governance_path = tmp_path / "untrusted-governance.json"
    _write_json(governance_path, governance)
    overrides = _bind_run_manifest(tmp_path, {"governance": governance_path})

    result, _, reasons = _run(tmp_path, overrides=overrides)

    assert result.returncode != 0
    _assert_reason(
        reasons,
        code="harness.governance_mismatch",
        criterion="harness",
    )


@pytest.mark.parametrize("duplicate", [False, True])
def test_vacuous_or_duplicate_closure_root_is_not_closed(
    tmp_path: Path,
    duplicate: bool,
) -> None:
    closure = json.loads((FIXTURES / "closure-summary.json").read_text())
    if duplicate:
        closure["roots"].append(deepcopy(closure["roots"][0]))
    else:
        closure["roots"][0]["total"] = 0
        closure["roots"][0]["by_status"] = {
            "encoded": 0,
            "excluded": 0,
            "pending": 0,
        }
        closure["roots"][0]["by_reason"] = {}
    path = tmp_path / f"closure-{'duplicate' if duplicate else 'empty'}.json"
    _write_json(path, closure)
    overrides = _bind_run_manifest(tmp_path, {"closure-summary": path})

    result, _, reasons = _run(tmp_path, overrides=overrides)

    assert result.returncode != 0
    _assert_reason(
        reasons,
        code="closed.producer_invalid",
        criterion="closed",
    )


def test_impossible_exercise_cardinality_is_not_fidelity(tmp_path: Path) -> None:
    census = json.loads((FIXTURES / "exercise-census.json").read_text())
    row = census["suites"]["us-medicare-wage-tax"]
    row["cases_scanned"] = 1
    row["evidence_fields"]["wages"]["distinct"] = 4
    path = tmp_path / "impossible-census.json"
    _write_json(path, census)
    overrides = _bind_run_manifest(tmp_path, {"exercise-census": path})

    result, _, reasons = _run(tmp_path, overrides=overrides)

    assert result.returncode != 0
    _assert_reason(
        reasons,
        code="exercised.dimension_unvaried",
        criterion="exercised",
    )


def test_comparison_applicability_cannot_omit_target(tmp_path: Path) -> None:
    comparisons = json.loads((FIXTURES / "comparisons.json").read_text())
    row = comparisons["comparisons"]["us-medicare-wage-tax"]
    row["applicable_nodes"] = [DEPENDENCY]
    row["required_dimensions"] = {DEPENDENCY: ["wages"]}
    path = tmp_path / "omitted-applicability.json"
    _write_json(path, comparisons)
    overrides = _bind_run_manifest(tmp_path, {"comparisons": path})

    result, _, reasons = _run(tmp_path, overrides=overrides)

    assert result.returncode != 0
    _assert_reason(
        reasons,
        code="conformant.declaration_mismatch",
        criterion="conformant",
    )


def test_check_detects_crlf_byte_drift_without_mutating(tmp_path: Path) -> None:
    write_result, output, reasons = _run(tmp_path)
    assert write_result.returncode == 0, write_result.stderr
    output.write_bytes(output.read_bytes().replace(b"\n", b"\r\n"))
    before = output.read_bytes()

    result, _, _ = _run(
        tmp_path,
        check=True,
        output=output,
        reasons_output=reasons,
    )

    assert result.returncode != 0
    summary = _stdout_json(result)
    assert summary["drift"]["certified_nodes"] is True
    assert summary["drift"]["reasons"] is False
    assert output.read_bytes() == before


def test_output_and_reasons_alias_is_rejected_before_write(tmp_path: Path) -> None:
    target = tmp_path / "aliased-output"

    result, _, _ = _run(
        tmp_path,
        output=target,
        reasons_output=target,
    )

    assert result.returncode == 2
    assert "must be different files" in result.stderr
    assert not target.exists()


@pytest.mark.parametrize(
    ("option", "criterion", "code"),
    [
        ("node-index", "provision_rooted", "provision_rooted.producer_missing"),
        ("run-manifest", "harness", "harness.producer_missing"),
        ("governance", "harness", "harness.producer_missing"),
    ],
)
def test_missing_integration_or_governance_producer_fails_closed(
    tmp_path: Path,
    option: str,
    criterion: str,
    code: str,
) -> None:
    result, _, reasons = _run(
        tmp_path,
        overrides={option: tmp_path / f"missing-{option}.json"},
    )

    assert result.returncode != 0
    _assert_reason(reasons, code=code, criterion=criterion)


def test_partial_write_recomputes_and_preserves_existing_green_node(
    tmp_path: Path,
) -> None:
    root = _copy_fixture_root(tmp_path)

    closure = json.loads((root / "closure-summary.json").read_text())
    dependency_root = deepcopy(closure["roots"][0])
    dependency_root.update(
        {
            "root": "us:statutes/26/3121",
            "total": 1,
            "by_status": {"encoded": 1, "excluded": 0, "pending": 0},
            "by_reason": {},
        }
    )
    closure["roots"].append(dependency_root)
    closure_path = root / "two-node-closure.json"
    _write_json(closure_path, closure)

    node_index = json.loads((root / "node-index.json").read_text())
    node_index["nodes"][DEPENDENCY] = {
        "label": "Medicare wage base",
        "provision": "26 USC 3121(a)",
        "corpus_citation_path": "us/statute/26/3121",
        "closure_roots": ["us:statutes/26/3121"],
        "comparisons": [
            {
                "suite": "us-medicare-wage-tax",
                "required_dimensions": ["wages"],
            }
        ],
    }
    node_index_path = root / "two-node-index.json"
    _write_json(node_index_path, node_index)

    comparisons = json.loads((root / "comparisons.json").read_text())
    comparison = comparisons["comparisons"]["us-medicare-wage-tax"]
    comparison["applicable_nodes"].append(DEPENDENCY)
    comparison["required_dimensions"][DEPENDENCY] = ["wages"]
    comparisons_path = root / "two-node-comparisons.json"
    _write_json(comparisons_path, comparisons)

    bindings_path = root / "manifests" / "us-medicare-golden-outputs.json"
    bindings = json.loads(bindings_path.read_text())
    bindings["bindings"]["medicare_wage_base"] = DEPENDENCY
    bindings["expected"]["medicare_wage_base"] = 10000
    _write_json(bindings_path, bindings)
    bindings_sha = hashlib.sha256(bindings_path.read_bytes()).hexdigest()

    manifest_path = root / "manifests" / "us-medicare.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["golden"]["outputs_sha256"] = bindings_sha
    _write_json(manifest_path, manifest)
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    receipt_path = root / "receipts" / "us-medicare-wage-tax.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["golden"]["outputs"]["medicare_wage_base"] = 10000
    _write_json(receipt_path, receipt)
    receipt_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest()

    executable = json.loads((root / "executable.json").read_text())
    first = executable["nodes"][NODE]
    first["covered_nodes"] = [NODE, DEPENDENCY]
    first["manifest"]["sha256"] = manifest_sha
    first["receipt"]["sha256"] = receipt_sha
    executable["nodes"][DEPENDENCY] = deepcopy(first)
    executable_path = root / "two-node-executable.json"
    _write_json(executable_path, executable)

    overrides = _bind_run_manifest(
        tmp_path,
        {
            "node-index": node_index_path,
            "closure-summary": closure_path,
            "comparisons": comparisons_path,
            "executable": executable_path,
        },
    )
    output = tmp_path / "two-node-ledger.yaml"
    reasons = tmp_path / "two-node-reasons.json"
    first_result, _, _ = _run(
        tmp_path,
        overrides=overrides,
        repo_root=root,
        nodes=(NODE, DEPENDENCY),
        output=output,
        reasons_output=reasons,
    )
    assert first_result.returncode == 0, first_result.stderr
    assert {row["node"] for row in _yaml_nodes(output)} == {NODE, DEPENDENCY}

    partial_result, _, _ = _run(
        tmp_path,
        overrides=overrides,
        repo_root=root,
        nodes=(NODE,),
        output=output,
        reasons_output=reasons,
    )

    assert partial_result.returncode == 0, partial_result.stderr
    assert {row["node"] for row in _yaml_nodes(output)} == {NODE, DEPENDENCY}
