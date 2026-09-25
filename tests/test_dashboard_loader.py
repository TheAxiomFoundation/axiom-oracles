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
    """The dashboard headline counts exactly what the publication gate counts.

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
    synthetic = [grid, duplicate_low, duplicate_high, understated]
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
    payload = {
        "documents": documents,
        "known_causes": json.loads((data / "known_causes.json").read_text())["entries"],
        "diagnostics": sorted(ratchet.diagnostic_suites()),
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

