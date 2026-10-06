"""The dashboard loader's overview fast path must equal per-file loading."""

import json
import math
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

import pytest

from axiom_oracles.conformance.unexplained import assess_unexplained

DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard"


@pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node runtime not available",
)
def test_loader_equivalence() -> None:
    proc = subprocess.run(
        ["node", "scripts/test-loader-equivalence.mjs"],
        cwd=DASHBOARD,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "EQUIVALENT: true" in proc.stdout
    assert "UNFILTERED UNEXPLAINED ASSESSMENT: true" in proc.stdout


@pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node runtime not available",
)
def test_dashboard_case_agreement_is_tristate_at_exact_boundary() -> None:
    proc = subprocess.run(
        ["node", "scripts/test-case-agreement.mjs"],
        cwd=DASHBOARD,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "CASE AGREEMENT SEMANTICS: true" in proc.stdout


def _json_safe_nonfinite(value):
    """Transport deliberate NaN/Infinity mutants through otherwise strict JSON."""
    if isinstance(value, float) and not math.isfinite(value):
        return {"$nonfinite": repr(value)}
    if isinstance(value, dict):
        return {key: _json_safe_nonfinite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_nonfinite(item) for item in value]
    return value


@pytest.mark.skipif(shutil.which("node") is None, reason="node runtime not available")
def test_unexplained_python_javascript_parity() -> None:
    """Every field agrees for every committed report and the definition mutants."""
    from test_unexplained_definition import parity_cases

    data = DASHBOARD / "public" / "data"
    known_causes = json.loads((data / "known_causes.json").read_text())["entries"]
    tracked = subprocess.run(
        ["git", "ls-files", "dashboard/public/data/*.json"],
        cwd=DASHBOARD.parent,
        check=True,
        capture_output=True,
        text=True,
    )
    cases = []
    for name in tracked.stdout.splitlines():
        path = DASHBOARD.parent / name
        if path.parent != data:
            continue
        report = json.loads(path.read_text())
        if not isinstance(report, dict) or not {
            "suite", "summary", "mismatches"
        }.issubset(report):
            continue
        cases.append({
            "name": name,
            "report": report,
            "options": {"known_causes": known_causes},
        })
    assert cases, "No committed dashboard comparison reports were checked"
    for index, case in enumerate(parity_cases()):
        cases.append({"name": f"synthetic mutant {index}", **case})
    for case in cases:
        case["expected"] = asdict(assess_unexplained(case["report"], **case["options"]))
    proc = subprocess.run(
        ["node", "scripts/test-unexplained-parity.mjs"],
        cwd=DASHBOARD,
        input=json.dumps(_json_safe_nonfinite(cases), allow_nan=False),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert f"UNEXPLAINED PARITY: {len(cases)} complete assessments agree" in proc.stdout


def _load_ratchet_module():
    import importlib.util

    path = DASHBOARD.parent / "scripts" / "unexplained_ratchet.py"
    spec = importlib.util.spec_from_file_location("_parity_unexplained_ratchet", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(shutil.which("node") is None, reason="node runtime not available")
def test_unexplained_gate_domain_and_total_parity(monkeypatch) -> None:
    """The dashboard assessment agrees with the gate on committed valid evidence.

    Same domain (grid-shaped named-engine reports included, typed diagnostics
    excluded), same per-suite maximum over duplicates, same counts, for every
    committed dashboard document plus synthetic grid and duplicate reports.
    """
    ratchet = _load_ratchet_module()
    data = DASHBOARD / "public" / "data"
    tracked = subprocess.run(
        ["git", "ls-files", "dashboard/public/data/*.json"],
        cwd=DASHBOARD.parent,
        check=True,
        capture_output=True,
        text=True,
    )
    documents = []
    for name in tracked.stdout.splitlines():
        path = DASHBOARD.parent / name
        if path.parent == data:
            documents.append(json.loads(path.read_text()))
    grid = {
        "suite": "zz-parity-grid",
        "engines": {"axiom": "a", "policyengine": "p", "taxsim": "t"},
        "summary": {"mismatch_count": 5},
        "mismatches": [],
    }
    duplicate_low = {
        "suite": "zz-parity-duplicate",
        "engines": {"left": "axiom", "right": "oracle"},
        "summary": {"mismatch_count": 2},
        "mismatches": [],
    }
    duplicate_high = {**duplicate_low, "summary": {"mismatch_count": 7}}
    understated = {
        "suite": "zz-parity-understated",
        "engines": {"left": "oracle", "right": "axiom"},
        "summary": {"mismatch_count": 0},
        "mismatches": [{"concept": "c", "kind": "amount_difference"}],
    }
    summary_only = {
        "suite": "zz-parity-summary-only",
        "engines": {"left": "axiom", "right": "oracle"},
        "summary": {"mismatch_count": 500},
    }
    malformed_engines = [
        {**grid, "suite": f"zz-parity-engines-{index}", "engines": engines}
        for index, engines in enumerate((["axiom", "oracle"], "axiom", 1, True))
    ]
    forged_assessment = {
        **duplicate_low, "suite": "zz-parity-forged-assessment",
        "summary": {"mismatch_count": 5}, "unexplained_assessment": {"count": 0},
    }
    synthetic = [grid, duplicate_low, duplicate_high, understated, summary_only,
                 forged_assessment, *malformed_engines]
    documents.extend(synthetic)
    reports = [
        {**doc, "_file": f"doc-{index}.json"}
        for index, doc in enumerate(documents)
        if isinstance(doc, dict) and doc.get("suite") and doc.get("engines")
    ]
    monkeypatch.setattr(ratchet, "load_dashboard_reports", lambda _directory: reports)
    expected, _problems = ratchet.live_assessments()
    assert expected["zz-parity-grid"] == 5
    assert expected["zz-parity-duplicate"] == 7
    assert expected["zz-parity-understated"] == 1
    assert expected["zz-parity-summary-only"] == 500
    assert expected["zz-parity-forged-assessment"] == 5
    assert not any(suite.startswith("zz-parity-engines-") for suite in expected)
    payload = {
        "documents": documents,
        "known_causes": json.loads((data / "known_causes.json").read_text())["entries"],
        "expected": expected,
    }
    proc = subprocess.run(
        ["node", "scripts/test-unexplained-gate-total.mjs"],
        cwd=DASHBOARD,
        input=json.dumps(payload, allow_nan=False),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert f"UNEXPLAINED GATE PARITY: {len(expected)} suites" in proc.stdout



@pytest.mark.skipif(shutil.which("node") is None, reason="node runtime not available")
def test_diagnostic_exemptions_ignore_javascript_comments(tmp_path, monkeypatch):
    ratchet = _load_ratchet_module()
    utility = tmp_path / "dashboard/src/utils"
    utility.mkdir(parents=True)
    source = (DASHBOARD / "src/utils/suites.js").read_text()
    # The review's exact injected comment must have no gate authority.
    source += '\n// "fl-snap-ecps": { kind: "diagnostic" } (a comment)\n'
    (utility / "suites.mjs").write_text(source)
    (utility / "suites.js").write_text(source)
    shutil.copy(DASHBOARD / "src/utils/diagnostic-suites.json", utility)
    monkeypatch.setattr(ratchet, "REPO_ROOT", tmp_path)
    python_diagnostics = ratchet.diagnostic_suites()
    assert "fl-snap-ecps" not in python_diagnostics
    doc = json.loads((utility / "diagnostic-suites.json").read_text())
    names = [*doc, "fl-snap-ecps", "unregistered-diagnostic"]
    proc = subprocess.run(
        ["node", "--input-type=module", "-e",
         f"import {{ suiteMeta }} from {json.dumps((utility / 'suites.mjs').as_uri())};"
         "const names=JSON.parse(process.argv[1]);"
         "console.log(JSON.stringify(names.filter(suite => suiteMeta(suite).kind === 'diagnostic')));",
         json.dumps(names)],
        capture_output=True, text=True, check=True,
    )
    assert set(json.loads(proc.stdout)) == python_diagnostics == set(doc)


@pytest.mark.parametrize("payload", [[], {"sample": {}}, {"sample": {"kind": "household"}}, {"": {"kind": "diagnostic"}}])
def test_diagnostic_source_requires_typed_entries(payload, tmp_path, monkeypatch):
    ratchet = _load_ratchet_module()
    table = tmp_path / "dashboard/src/utils/diagnostic-suites.json"
    table.parent.mkdir(parents=True)
    table.write_text(json.dumps(payload))
    monkeypatch.setattr(ratchet, "REPO_ROOT", tmp_path)
    with pytest.raises(ValueError, match="expected suite metadata"):
        ratchet.diagnostic_suites()


@pytest.mark.parametrize("engines", [["axiom", "oracle"], "axiom", 1, True, None])
def test_nonobject_engines_are_outside_gate(engines, monkeypatch):
    ratchet = _load_ratchet_module()
    report = {"suite": "sample", "engines": engines,
              "summary": {"mismatch_count": 1}, "mismatches": []}
    monkeypatch.setattr(ratchet, "load_dashboard_reports", lambda _: [report])
    assert ratchet._gated_report_rows() == []


def test_summary_only_report_is_in_gate(monkeypatch):
    ratchet = _load_ratchet_module()
    report = {"suite": "sample", "engines": {"left": "axiom", "right": "oracle"},
              "summary": {"mismatch_count": 500}}
    monkeypatch.setattr(ratchet, "load_dashboard_reports", lambda _: [report])
    assert ratchet._gated_report_rows() == [report]
    assert ratchet.count_unexplained(report, []) == 500


@pytest.mark.skipif(shutil.which("node") is None, reason="node runtime not available")
def test_gated_helper_reassesses_report_carried_assessment():
    module = (DASHBOARD / "src/utils/unexplained.js").as_uri()
    report = {"suite": "sample", "engines": {"left": "axiom", "right": "oracle"},
              "summary": {"mismatch_count": 5}, "mismatches": [],
              "unexplained_assessment": {"count": 0}}
    proc = subprocess.run(
        ["node", "--input-type=module", "-e",
         f"import {{ gatedUnexplainedBySuite }} from {json.dumps(module)};"
         "console.log(JSON.stringify(gatedUnexplainedBySuite([JSON.parse(process.argv[1])])));",
         json.dumps(report)],
        capture_output=True, text=True, check=True,
    )
    assert json.loads(proc.stdout) == {"sample": 5}
