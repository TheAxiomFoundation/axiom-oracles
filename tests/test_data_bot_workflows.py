"""Pin the publication boundary and readers for generated oracle data."""

from pathlib import Path
import re

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"
PUBLISHERS = {
    ("affected-rerun.yml", "publish"),
    ("comparisons.yml", "rule-coverage"),
}


def workflow(name):
    return yaml.safe_load((WORKFLOWS / name).read_text())


def runs(job):
    return "\n".join(step.get("run", "") for step in job.get("steps", []))


def assert_safe_publication(name, doc):
    if name == "api-parity-corpus.yml":
        # This existing writer creates release tags/assets, not branch commits.
        assert doc["permissions"] == {"contents": "write"}
        assert set(doc["jobs"]) == {"release"}
        assert "gh release create" in runs(doc["jobs"]["release"])
    else:
        assert doc.get("permissions", {}).get("contents") != "write"
    for job_name, job in doc["jobs"].items():
        shell = runs(job)
        # Raw pushes include implicit defaults, variables and explicit refs.
        # Writers must use the guarded publishers below instead.
        assert not re.search(r"\bgit\s+(?:-[^\s]+\s+)*push\b", shell)
        if job.get("permissions", {}).get("contents") != "write":
            continue
        assert (name, job_name) in PUBLISHERS
        if job_name == "publish":
            calls = [step["run"] for step in job["steps"]
                     if "commit_refreshed_report.sh" in step.get("run", "")]
            assert len(calls) == 1
            assert re.search(r'--publish\s+\\?\s*"\$RUNNER_TEMP/refreshed"\s+"oracle-data"', calls[0])
            assert "github.event.repository.default_branch" not in calls[0]
        else:
            assert "scripts/oracle_data.py prepare" in shell
            assert "scripts/oracle_data.py publish --group kpi" in shell


def test_no_workflow_can_push_to_main():
    files = sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
    assert files
    writers = set()
    for path in files:
        doc = workflow(path.name)
        assert_safe_publication(path.name, doc)
        writers.update((path.name, job_name) for job_name, job in doc["jobs"].items()
                       if job.get("permissions", {}).get("contents") == "write")
    assert writers == PUBLISHERS


@pytest.mark.parametrize("push", [
    "git push", "git push origin main", "git push origin HEAD:refs/heads/main",
    'git push origin "HEAD:$TARGET"', "git -c push.default=current push origin",
])
def test_workflow_scan_rejects_direct_and_implicit_pushes(push):
    with pytest.raises(AssertionError):
        assert_safe_publication("unsafe.yml", {
            "jobs": {"bot": {"steps": [{"run": push}]}}
        })


def test_workflow_scan_rejects_new_indirect_writers():
    with pytest.raises(AssertionError):
        assert_safe_publication("unsafe.yml", {
            "jobs": {"bot": {"permissions": {"contents": "write"},
                             "steps": [{"run": "scripts/new-publisher.sh"}]}}
        })


def test_workflow_scan_rejects_default_branch_publisher_target():
    doc = workflow("affected-rerun.yml")
    step = next(s for s in doc["jobs"]["publish"]["steps"]
                if "--publish" in s.get("run", ""))
    step["run"] = step["run"].replace('"oracle-data"', '"${{ github.event.repository.default_branch }}"')
    with pytest.raises(AssertionError):
        assert_safe_publication("affected-rerun.yml", doc)


def test_readers_load_data_before_selection_and_computation():
    affected = workflow("affected-rerun.yml")["jobs"]
    select = affected["select"]["steps"]
    load = next(i for i, s in enumerate(select) if "materialize --baseline" in s.get("run", ""))
    resolve = next(i for i, s in enumerate(select) if s.get("id") == "heads")
    choose = next(i for i, s in enumerate(select) if s.get("id") == "select")
    assert load < resolve < choose
    for job in [affected["rerun"], workflow("comparisons.yml")["jobs"]["compare"]]:
        steps = job["steps"]
        load = next(i for i, s in enumerate(steps) if "materialize --baseline" in s.get("run", ""))
        compare = next(i for i, s in enumerate(steps) if "scripts/run_comparison.py" in s.get("run", ""))
        assert load < compare
        checkout = next(s for s in steps if s.get("uses", "").startswith("actions/checkout@"))
        assert checkout["with"]["ref"] == "main"
        assert checkout["with"]["fetch-depth"] == 0


def test_kpi_prepares_before_generation_and_preserves_manual_dry_run():
    job = workflow("comparisons.yml")["jobs"]["rule-coverage"]
    steps = job["steps"]
    prepare = next(i for i, s in enumerate(steps) if "oracle_data.py prepare" in s.get("run", ""))
    generate = next(i for i, s in enumerate(steps) if "scripts/rule_verification.py" in s.get("run", ""))
    publish = next(i for i, s in enumerate(steps) if "oracle_data.py publish" in s.get("run", ""))
    assert prepare < generate < publish
    assert steps[publish]["if"] == "github.event_name == 'schedule'"


def test_dashboard_reads_publication_and_ci_validates_reviewed_snapshot():
    import json

    scripts = json.loads((ROOT / "dashboard/package.json").read_text())["scripts"]
    for command in ("dev", "build"):
        assert scripts[command].startswith("node scripts/materialize-data.mjs && ")
    ci = workflow("ci.yml")
    assert ci["jobs"]["dashboard"]["env"]["AXIOM_ORACLES_DATA_SOURCE"] == "checkout"
    triggers = ci.get("on", ci.get(True))
    assert "pull_request" in triggers
    assert triggers["pull_request"] is None
    assert set(ci["jobs"]) == {"test", "gettsim-live", "policyengine-live", "dashboard"}
    for job in ci["jobs"].values():
        assert "if" not in job and "needs" not in job and "strategy" not in job


@pytest.mark.parametrize("path", ["scripts/regenerate_all.sh", "dashboard/scripts/regenerate_all.sh"])
def test_unattended_publishers_use_guarded_data_branch(path):
    script = (ROOT / path).read_text()
    assert "git push" not in script
    prepare = script.index("scripts/oracle_data.py prepare")
    compute = script.index("./scripts/sync_rulespec_roots.sh")
    publish = script.index("scripts/oracle_data.py publish --group dashboard")
    deploy = script.index("vercel --prod")
    assert prepare < compute < publish < deploy
    assert "git switch -C oracle-data" in script
    assert "AXIOM_ORACLES_DATA_SOURCE=checkout bun run build" in script


def test_workflow_publications_are_serialized_on_the_data_branch():
    for file, job_name in PUBLISHERS:
        assert workflow(file)["jobs"][job_name]["concurrency"] == {
            "group": "oracle-data-publication", "cancel-in-progress": False,
        }


@pytest.mark.parametrize("scenario", [
    "checkout", "project-python", "ci", "missing-git", "missing-helper", "failed-read",
])
def test_dashboard_wrapper_runs_in_checkouts_and_uploaded_projects(tmp_path, scenario):
    import os
    import shutil
    import subprocess

    root = tmp_path / "source"
    dashboard = root / "dashboard"
    scripts = dashboard / "scripts"
    scripts.mkdir(parents=True)
    wrapper = scripts / "materialize-data.mjs"
    shutil.copy2(ROOT / "dashboard/scripts/materialize-data.mjs", wrapper)
    helper = root / "scripts/oracle_data.py"
    if scenario != "missing-helper":
        helper.parent.mkdir()
        helper.write_text("# The fixture interpreter records this invocation.\n")
    if scenario != "missing-git":
        (root / ".git").write_text("fixture git marker\n")
    bin_dir = root / "bin"
    bin_dir.mkdir()
    interpreter = (root / ".venv/bin/python") if scenario == "project-python" else bin_dir / "python3"
    interpreter.parent.mkdir(parents=True, exist_ok=True)
    interpreter.write_text(
        '#!/bin/sh\n'
        'printf "%s\\n" "$PWD" "$1" "$2" > "$CALL_LOG"\n'
        'exit "${HELPER_STATUS:-0}"\n'
    )
    interpreter.chmod(0o755)
    log = root / "python-call"
    env = {**os.environ, "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
           "CALL_LOG": str(log), "HELPER_STATUS": "17" if scenario == "failed-read" else "0"}
    env.pop("AXIOM_ORACLES_DATA_SOURCE", None)
    if scenario == "ci":
        env["AXIOM_ORACLES_DATA_SOURCE"] = "checkout"
    result = subprocess.run(
        ["node", str(wrapper)], cwd=dashboard, env=env,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == (17 if scenario == "failed-read" else 0), result.stderr
    if scenario in {"checkout", "project-python", "failed-read"}:
        assert log.read_text().splitlines() == [str(root), str(helper), "materialize"]
    else:
        assert not log.exists(), "CI and uploaded builds must not need Python or Git"
