"""Structure of .github/workflows/affected-rerun.yml's SNAP QC live path.

The affected rerun hands stale `ci: snap-qc-replay` suites to the live replay
lane (snap-qc-replay.yml, called with publish) and commits only what that lane
uploads. These tests pin the wiring between the three pieces: the selector's
lane output, the called workflow's inputs and artifact names, and the commit
job.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
LANE = "snap-qc-replay"


def _workflow(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text())


def _jobs() -> dict:
    return _workflow("affected-rerun.yml")["jobs"]


def _load(script: str):
    spec = importlib.util.spec_from_file_location(
        script, REPO_ROOT / "scripts" / f"{script}.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_select_exposes_the_lane_output_the_selector_writes():
    gam = _load("generate_affected_map")
    assert gam.CI_LANES[LANE] == "snap-qc-compare"
    key = "lane_" + LANE.replace("-", "_")
    outputs = _jobs()["select"]["outputs"]
    assert outputs["snap_qc"] == f"${{{{ steps.select.outputs.{key} }}}}"
    assert outputs["snap_qc_count"] == f"${{{{ steps.select.outputs.{key}_count }}}}"
    # The bare matrix still comes from the lane-free `matrix` output.
    rerun = _jobs()["rerun"]
    assert rerun["strategy"]["matrix"] == "${{ fromJson(needs.select.outputs.matrix) }}"


def test_lane_suites_are_replayed_live_with_publish_and_never_committed_there():
    job = _jobs()["snap-qc-replay"]
    assert job["uses"] == "./.github/workflows/snap-qc-replay.yml"
    assert job["needs"] == "select"
    assert "needs.select.outputs.snap_qc_count" in job["if"]
    assert job["permissions"] == {"contents": "read"}
    assert job["with"] == {
        "suites": "${{ join(fromJson(needs.select.outputs.snap_qc), ' ') }}",
        "run_kind": "affected-rerun",
        "publish": True,
    }
    called = _workflow("snap-qc-replay.yml")
    triggers = called.get("on", called.get(True))
    assert set(job["with"]) <= set(triggers["workflow_call"]["inputs"])
    text = (WORKFLOWS / "snap-qc-replay.yml").read_text()
    assert "git push" not in text and "contents: write" not in text


def test_commit_job_commits_only_uploaded_exact_reports():
    job = _jobs()["snap-qc-commit"]
    assert job["needs"] == ["select", "snap-qc-replay"]
    # Runs after a partly failed replay (the passing suites still commit),
    # never after a cancellation.
    assert "!cancelled()" in job["if"]
    assert job["permissions"] == {"contents": "write"}
    assert job["strategy"]["fail-fast"] is False
    assert job["strategy"]["matrix"]["suite"] == "${{ fromJson(needs.select.outputs.snap_qc) }}"
    steps = job["steps"]
    download = steps[0]
    assert download["uses"].startswith("actions/download-artifact@")
    assert download["continue-on-error"] is True
    # The name the replay lane uploads.
    uploaded = [
        step["with"]["name"]
        for step in _workflow("snap-qc-replay.yml")["jobs"]["replay"]["steps"]
        if step.get("uses", "").startswith("actions/upload-artifact@")
        and "publish" in step.get("if", "")
    ]
    assert uploaded == [download["with"]["name"]] == ["snap-qc-publish-${{ matrix.suite }}"]
    for step in steps[1:]:
        condition = step.get("if", "")
        if step.get("name", "").startswith("No live"):
            assert condition == "steps.bundle.outcome != 'success'"
        else:
            assert condition == "steps.bundle.outcome == 'success'", step
    checkout = next(s for s in steps if s.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["ref"] == "${{ github.event.repository.default_branch }}"
    commit = steps[-1]
    assert "scripts/commit_refreshed_report.sh" in commit["run"]
    assert commit["env"]["PYTHON"].endswith("/.venv/bin/python")
