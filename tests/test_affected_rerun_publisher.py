"""Structure of .github/workflows/affected-rerun.yml's single publisher.

Matrix legs used to commit and push their own refresh, racing ~47 siblings
for main; run 36239293795 (2026-09-26) lost 7 legs, and run 35958364304 lost
11, to the 90-minute timeout inside that push loop. Legs now pack a vetted
bundle and upload it as ``refreshed-<suite>``; one ``publish`` job downloads
every bundle and is the only writer. These tests pin that wiring, so a later
edit cannot quietly hand a leg its push back.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
SCRIPT = "scripts/commit_refreshed_report.sh"


def _workflow(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text())


def _jobs() -> dict:
    return _workflow("affected-rerun.yml")["jobs"]


def _runs(job: dict) -> list[str]:
    return [step["run"] for step in job.get("steps", []) if "run" in step]


def test_legs_pack_and_never_publish_or_push():
    rerun = _jobs()["rerun"]
    runs = _runs(rerun)
    invocations = [run for run in runs if SCRIPT in run]
    assert len(invocations) == 1, "a leg calls the commit script exactly once"
    assert "--pack" in invocations[0]
    for run in runs:
        assert "--publish" not in run
        assert "git push" not in run
        assert "git commit" not in run


def test_only_the_publish_job_can_write():
    workflow = _workflow("affected-rerun.yml")
    assert workflow["permissions"] == {"contents": "read"}
    writers = [
        name
        for name, job in workflow["jobs"].items()
        if (job.get("permissions") or {}).get("contents") == "write"
    ]
    assert writers == ["publish"]
    assert _jobs()["rerun"]["permissions"] == {"contents": "read"}


def test_legs_upload_their_bundle_as_refreshed_suite():
    steps = _jobs()["rerun"]["steps"]
    pack = next(step for step in steps if SCRIPT in step.get("run", ""))
    assert '"$RUNNER_TEMP/refreshed" "${{ matrix.name }}"' in pack["run"]
    # Only a leg that produced a bundle uploads one.
    assert 'echo "bundle=true" >> "$GITHUB_OUTPUT"' in pack["run"]
    uploads = [
        step
        for step in steps
        if step.get("uses", "").startswith("actions/upload-artifact@")
    ]
    assert len(uploads) == 1
    upload = uploads[0]
    assert upload["if"] == f"steps.{pack['id']}.outputs.bundle == 'true'"
    assert upload["with"]["name"] == "refreshed-${{ matrix.name }}"
    assert upload["with"]["path"] == "${{ runner.temp }}/refreshed/${{ matrix.name }}/"
    assert steps.index(pack) < steps.index(upload)


def test_publish_job_downloads_every_bundle_and_publishes_once():
    job = _jobs()["publish"]
    assert job["needs"] == ["select", "rerun"]
    # Runs after a partly failed matrix (the passing legs' bundles still
    # publish, and the run stays red for the failed legs), never after a
    # cancellation, and not at all when nothing was selected.
    assert "!cancelled()" in job["if"]
    assert "needs.select.outputs.count != '0'" in job["if"]
    assert job["timeout-minutes"] <= 60
    steps = job["steps"]
    download = steps[0]
    assert download["uses"].startswith("actions/download-artifact@")
    assert download["with"]["pattern"] == "refreshed-*"
    assert download["with"]["merge-multiple"] is False
    assert download["with"]["path"] == "${{ runner.temp }}/refreshed"
    publishes = [run for run in _runs(job) if SCRIPT in run]
    assert len(publishes) == 1
    assert "--publish" in publishes[0]
    assert '"$RUNNER_TEMP/refreshed"' in publishes[0]
    assert "${{ github.event.repository.default_branch }}" in publishes[0]
    checkout = next(
        step for step in steps if step.get("uses", "").startswith("actions/checkout@")
    )
    assert checkout["with"]["ref"] == "${{ github.event.repository.default_branch }}"


def test_publish_job_mirrors_the_legs_interpreter():
    """regenerate_derived runs in publish with the interpreter and package set
    the legs vetted with."""

    def setup(job: dict) -> tuple:
        steps = job["steps"]
        python = next(
            s["with"]["python-version"]
            for s in steps
            if s.get("uses", "").startswith("actions/setup-python@")
        )
        install = next(
            s["run"].strip() for s in steps if "uv pip install" in s.get("run", "")
        )
        return python, install

    assert setup(_jobs()["publish"]) == setup(_jobs()["rerun"])


def test_weekly_matrix_skips_every_ci_manual_suite(tmp_path):
    """Execute comparisons.yml's discover step as written: no ci: manual suite
    (the SPSD/M suite included) reaches the weekly matrix."""
    discover = _workflow("comparisons.yml")["jobs"]["discover"]
    run = next(step["run"] for step in discover["steps"] if step.get("id") == "list")
    code = textwrap.dedent(run.split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0])
    output = tmp_path / "github-output"
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        env={**os.environ, "ONLY": "", "GITHUB_OUTPUT": str(output)},
        check=True,
        capture_output=True,
        text=True,
    )
    line = output.read_text().strip()
    names = {leg["name"] for leg in json.loads(line.split("=", 1)[1])["include"]}
    manual = set()
    for path in (REPO_ROOT / "comparisons").glob("*.yaml"):
        config = yaml.safe_load(path.read_text())
        if isinstance(config, dict) and config.get("ci") == "manual":
            manual.add(path.stem)
    assert "ca-federal-schedule-tax-spsm" in manual
    assert names and not names & manual
