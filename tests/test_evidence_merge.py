"""Cross-layer mutants for evidence behavior joined by the main merge."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

from axiom_oracles.comparison.dispositions import (
    apply_dispositions,
    assignment_digest,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(
        f"evidence_merge_{name}", REPO_ROOT / "scripts" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_preserved_versioned_skip_cannot_rebind_to_fresh_partial_source(
    monkeypatch, tmp_path
):
    """A no-execution slim re-emission cannot become its own full source."""

    run_comparison = _load_script("run_comparison")
    apply_dispositions_script = _load_script("apply_dispositions")
    repo = tmp_path / "repo"
    dashboard = repo / "dashboard" / "public" / "data"
    reports = repo / "reports"
    suite = "preserved-skip"
    suite_dir = dashboard / "cases" / suite
    suite_dir.mkdir(parents=True)
    reports.mkdir()
    monkeypatch.setattr(run_comparison, "REPO_ROOT", repo)
    monkeypatch.setattr(run_comparison, "DASHBOARD_DATA_DIR", dashboard)
    monkeypatch.setattr(run_comparison, "_merge_dispositions", lambda report: report)
    apply_dispositions_script.REPO_ROOT = repo
    apply_dispositions_script.DASHBOARD_DATA_DIR = dashboard

    mismatch_count = run_comparison._DASHBOARD_MAX_MISMATCHES + 1
    full = {
        "schema_version": "axiom.comparison_report.v2",
        "suite": suite,
        "case_count": mismatch_count,
        "cases": [],
        "mismatches": [
            {
                "case_id": f"case-{index}",
                "concept": "benefit",
                "kind": "amount_difference",
                "left": 0,
                "right": 1,
                "difference": -1,
            }
            for index in range(mismatch_count)
        ],
        "summary": {
            "comparison_count": mismatch_count,
            "match_count": 0,
            "mismatch_count": mismatch_count,
        },
    }
    dispositions = {"entries": []}
    dispositions_label = f"dispositions/{suite}.yaml"
    merged = apply_dispositions(
        full, dispositions, dispositions_file=dispositions_label
    )

    old_full_path = reports / "old-full.json"
    old_full_path.write_text(json.dumps(full, indent=2))
    preserved = copy.deepcopy(merged)
    preserved["mismatches"] = preserved["mismatches"][
        : run_comparison._DASHBOARD_MAX_MISMATCHES
    ]
    preserved["summary"]["stored_mismatch_example_count"] = len(
        preserved["mismatches"]
    )
    preserved_block = preserved["summary"]["dispositioned"]
    preserved_block["source_report"] = {
        "path": "reports/old-full.json",
        "sha256": hashlib.sha256(old_full_path.read_bytes()).hexdigest(),
    }
    preserved_block["assignment_sha256"] = assignment_digest(merged)
    target = dashboard / "preserved-skip.json"
    target.write_text(json.dumps(preserved, indent=2))
    index_path = suite_dir / "index.json"
    index_path.write_text(
        json.dumps({"schema_version": "axiom_oracles.chunk_index.v1"})
    )

    # The current skip artifact was copied from the slim dashboard view. It is
    # deliberately not FULL, even though this run can publish it under reports/.
    fresh_skip = copy.deepcopy(preserved)
    fresh_skip["provenance"] = {"generated_at": "future skip"}
    fresh_skip_path = reports / "fresh-skip.json"
    fresh_skip_path.write_text(json.dumps(fresh_skip, indent=2))
    before = (target.read_bytes(), index_path.read_bytes())

    run_comparison._write_dashboard_report(
        fresh_skip,
        target.name,
        full_report_path=fresh_skip_path,
        preserve_existing_versioned=True,
    )

    assert (target.read_bytes(), index_path.read_bytes()) == before
    assert run_comparison._preserved_versioned_source_is_output(
        target.name, old_full_path
    )
    problems, _, changed = apply_dispositions_script._merge_reports(
        {suite: dispositions}, check=True
    )
    assert problems == []
    assert changed is False

    # Mutant: bind the preserved dashboard copy to the new skip artifact and
    # its honest byte digest. --check must still fail closed because the
    # re-emitted dashboard sample cannot serve as a FULL report.
    rebound = json.loads(target.read_text())
    rebound["summary"]["dispositioned"]["source_report"] = {
        "path": "reports/fresh-skip.json",
        "sha256": hashlib.sha256(fresh_skip_path.read_bytes()).hexdigest(),
    }
    target.write_text(json.dumps(rebound, indent=2))
    problems, _, changed = apply_dispositions_script._merge_reports(
        {suite: dispositions}, check=True
    )

    assert changed is False
    assert any("is not a FULL report" in problem for problem in problems)
