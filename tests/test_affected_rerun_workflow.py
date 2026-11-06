"""Structure of .github/workflows/affected-rerun.yml's SNAP QC live path.

The affected rerun hands stale `ci: snap-qc-replay` suites to the live replay
lane (snap-qc-replay.yml, called with publish). Each leg the lane's `check`
accepts packs a `refreshed-<suite>` bundle, and the rerun's single `publish`
job applies it with the bare legs' bundles. These tests pin the wiring between
the pieces: the selector's lane output, the called workflow's inputs and
artifact names, and the publish job.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import textwrap
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
    # An absent count reads as zero, so fromJson never sees an empty list.
    assert job["if"] == "(needs.select.outputs.snap_qc_count || '0') != '0'"
    assert job["permissions"] == {"contents": "read"}
    # The lane runs on the default token alone: no repository secrets.
    assert "secrets" not in job
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


def test_publish_job_applies_the_lane_bundles_and_stays_the_only_writer():
    job = _jobs()["publish"]
    assert job["needs"] == ["select", "rerun", "snap-qc-replay"]
    # Runs when only lane suites are stale, after a partly failed replay (the
    # passing suites still publish), and never after a cancellation.
    assert "!cancelled()" in job["if"]
    assert "needs.select.outputs.count != '0'" in job["if"]
    assert "needs.select.outputs.snap_qc_count != '0'" in job["if"]
    pattern = job["steps"][0]["with"]["pattern"]
    assert pattern == "refreshed-*"
    # The lane uploads under the same name as a bare leg, so the one download
    # picks it up; it uploads nothing else a publish could mistake for one.
    uploads = [
        step["with"]["name"]
        for step in _workflow("snap-qc-replay.yml")["jobs"]["replay"]["steps"]
        if step.get("uses", "").startswith("actions/upload-artifact@")
    ]
    assert [n for n in uploads if n.startswith("refreshed-")] == [
        "refreshed-${{ matrix.suite }}"
    ]
    writers = [
        name
        for name, spec in _jobs().items()
        if (spec.get("permissions") or {}).get("contents") == "write"
    ]
    assert writers == ["publish"]


def _bundle_guard() -> dict:
    steps = _jobs()["publish"]["steps"]
    guard = [s for s in steps if s.get("name") == "Every passing SNAP QC replay left a bundle"]
    assert len(guard) == 1
    return guard[0]


def _run_bundle_guard(tmp_path: Path, suites: list[str], present: list[str]):
    guard = _bundle_guard()
    code = textwrap.dedent(guard["run"].split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0])
    for suite in present:
        (tmp_path / "refreshed" / f"refreshed-{suite}").mkdir(parents=True)
    return subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "RUNNER_TEMP": str(tmp_path), "SNAP_QC": json.dumps(suites)},
        capture_output=True,
        text=True,
    )


def test_publish_fails_when_a_passing_lane_suite_left_no_bundle():
    """If the called workflow's uploads never reach publish's download, every
    lane leg is green and publish applies only the bare bundles. This guard
    turns that silent partial publish red."""
    steps = _jobs()["publish"]["steps"]
    guard = _bundle_guard()
    download = next(
        i for i, s in enumerate(steps)
        if s.get("uses", "").startswith("actions/download-artifact@")
    )
    assert download < steps.index(guard)
    # Runs only when the whole lane passed (a failed leg is already red), and
    # still after a failed publish step, never after a cancellation.
    assert guard["if"] == (
        "${{ !cancelled() && needs.snap-qc-replay.result == 'success' }}"
    )
    assert guard["env"]["SNAP_QC"] == "${{ needs.select.outputs.snap_qc }}"
    # The directory name the download gives each bundle is the uploaded name.
    upload = next(
        s for s in _workflow("snap-qc-replay.yml")["jobs"]["replay"]["steps"]
        if s.get("name") == "Upload refreshed-report bundle"
    )
    assert upload["with"]["name"] == "refreshed-${{ matrix.suite }}"
    assert 'f"refreshed-{s}"' in guard["run"]


def test_bundle_guard_names_each_missing_suite(tmp_path):
    lane = ["az-snap-qc", "ca-snap-qc", "ny-snap-qc"]
    result = _run_bundle_guard(tmp_path, lane, ["ca-snap-qc"])
    assert result.returncode != 0
    assert "az-snap-qc, ny-snap-qc" in result.stderr


def test_bundle_guard_passes_when_every_suite_left_a_bundle(tmp_path):
    lane = ["az-snap-qc", "ca-snap-qc"]
    result = _run_bundle_guard(tmp_path, lane, lane)
    assert result.returncode == 0, result.stderr
    # A bundle for a bare suite does not stand in for a lane suite.
    assert _run_bundle_guard(tmp_path / "x", lane, ["az-snap-qc", "co-tax"]).returncode != 0


def test_snap_qc_rollback_stops_the_route_before_reverting_the_whole_publish():
    """Rollback must stop republishing and restore every output as one commit."""
    playbook = (REPO_ROOT / "docs" / "snap-qc-oracle-playbook.md").read_text()
    replay = playbook.split("## 10. The live CI replay\n", 1)[1].split("\n## ", 1)[0]
    assert "republishes" in replay  # Why a revert alone doesn't stick.
    steps = re.findall(r"(?m)^ *([12])\. (.+(?:\n {3,}.+)*)", replay)
    assert [number for number, _ in steps] == ["1", "2"]
    stop_route, revert_publish = (" ".join(step.split()) for _, step in steps)
    for required in (
        "`main`",
        "disable `affected-rerun.yml`",
        "`ci: manual`",
        "regenerate `comparisons/affected_map.json`",
    ):
        assert required in stop_route
    for required in (
        "Revert",
        "`data: refresh`",
        "`oracle-data`",
        "reports",
        "`dashboard/public/data/cases/co-snap-qc/`",
        "snapshot",
        "certificate",
        "together",
    ):
        assert required in revert_publish
