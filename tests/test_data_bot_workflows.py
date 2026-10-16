"""Pin the publication boundary and readers for generated oracle data."""

from pathlib import Path
import ast
import re

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"
PUBLISHERS = {
    ("affected-rerun.yml", "publish"),
    ("comparisons.yml", "rule-coverage"),
    ("oracle-data-reconcile.yml", "reconcile"),
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
            calls = [
                step["run"]
                for step in job["steps"]
                if "commit_refreshed_report.sh" in step.get("run", "")
            ]
            assert len(calls) == 1
            assert re.search(
                r'--publish\s+\\?\s*"\$RUNNER_TEMP/refreshed"\s+"oracle-data"', calls[0]
            )
            assert "github.event.repository.default_branch" not in calls[0]
        elif job_name == "rule-coverage":
            assert "scripts/oracle_data.py prepare" in shell
            assert "scripts/oracle_data.py publish --group kpi" in shell
        else:
            assert "scripts/oracle_data.py prepare" in shell
            assert "scripts/oracle_data.py publish --group all" in shell


def test_no_workflow_can_push_to_main():
    files = sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
    assert files
    writers = set()
    for path in files:
        doc = workflow(path.name)
        assert_safe_publication(path.name, doc)
        writers.update(
            (path.name, job_name)
            for job_name, job in doc["jobs"].items()
            if job.get("permissions", {}).get("contents") == "write"
        )
    assert writers == PUBLISHERS


@pytest.mark.parametrize(
    "push",
    [
        "git push",
        "git push origin main",
        "git push origin HEAD:refs/heads/main",
        'git push origin "HEAD:$TARGET"',
        "git -c push.default=current push origin",
    ],
)
def test_workflow_scan_rejects_direct_and_implicit_pushes(push):
    with pytest.raises(AssertionError):
        assert_safe_publication(
            "unsafe.yml", {"jobs": {"bot": {"steps": [{"run": push}]}}}
        )


def test_workflow_scan_rejects_new_indirect_writers():
    with pytest.raises(AssertionError):
        assert_safe_publication(
            "unsafe.yml",
            {
                "jobs": {
                    "bot": {
                        "permissions": {"contents": "write"},
                        "steps": [{"run": "scripts/new-publisher.sh"}],
                    }
                }
            },
        )


def test_workflow_scan_rejects_default_branch_publisher_target():
    doc = workflow("affected-rerun.yml")
    step = next(
        s for s in doc["jobs"]["publish"]["steps"] if "--publish" in s.get("run", "")
    )
    step["run"] = step["run"].replace(
        '"oracle-data"', '"${{ github.event.repository.default_branch }}"'
    )
    with pytest.raises(AssertionError):
        assert_safe_publication("affected-rerun.yml", doc)


def test_readers_load_data_before_selection_and_computation():
    affected = workflow("affected-rerun.yml")["jobs"]
    select = affected["select"]["steps"]
    load = next(
        i for i, s in enumerate(select) if "materialize --baseline" in s.get("run", "")
    )
    resolve = next(i for i, s in enumerate(select) if s.get("id") == "heads")
    choose = next(i for i, s in enumerate(select) if s.get("id") == "select")
    assert load < resolve < choose
    for job in [affected["rerun"], workflow("comparisons.yml")["jobs"]["compare"]]:
        steps = job["steps"]
        load = next(
            i
            for i, s in enumerate(steps)
            if "materialize --baseline" in s.get("run", "")
        )
        compare = next(
            i
            for i, s in enumerate(steps)
            if "scripts/run_comparison.py" in s.get("run", "")
        )
        assert load < compare
        checkout = next(
            s for s in steps if s.get("uses", "").startswith("actions/checkout@")
        )
        assert checkout["with"]["ref"] == "main"
        assert checkout["with"]["fetch-depth"] == 0


def test_kpi_prepares_before_generation_and_preserves_manual_dry_run():
    job = workflow("comparisons.yml")["jobs"]["rule-coverage"]
    steps = job["steps"]
    prepare = next(
        i for i, s in enumerate(steps) if "oracle_data.py prepare" in s.get("run", "")
    )
    generate = next(
        i
        for i, s in enumerate(steps)
        if "scripts/rule_verification.py" in s.get("run", "")
    )
    publish = next(
        i for i, s in enumerate(steps) if "oracle_data.py publish" in s.get("run", "")
    )
    assert prepare < generate < publish
    assert steps[publish]["if"] == "github.event_name == 'schedule'"


def assert_publish_environment(job):
    steps = job.get("steps", [])
    for index, step in enumerate(steps):
        if not re.search(
            r"oracle_data\.py\s+publish\b|commit_refreshed_report\.sh\s+--publish\b",
            step.get("run", ""),
        ):
            continue
        assert any(
            re.search(
                r"\b(?:uv\s+)?pip\s+install\s+(?:--system\s+)?-e\s+['\"]?\.(?:\[[\w,]+\])?(?:['\"]|\s|$)",
                previous.get("run", ""),
            )
            for previous in steps[:index]
        ), "publication gates require the installed package, not just PyYAML"


def test_every_workflow_publisher_installs_the_package_before_publication():
    files = sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
    for path in files:
        for job in workflow(path.name)["jobs"].values():
            assert_publish_environment(job)


@pytest.mark.parametrize(
    "install", ["pip install pyyaml", "", "uv pip install requests"]
)
def test_publication_environment_rejects_incomplete_gate_dependencies(install):
    with pytest.raises(AssertionError, match="require the installed package"):
        assert_publish_environment(
            {
                "steps": [
                    {"run": install},
                    {"run": "python3 scripts/oracle_data.py publish --group all"},
                ]
            }
        )


def test_main_data_pushes_reconcile_the_complete_publication():
    doc = workflow("oracle-data-reconcile.yml")
    triggers = doc.get("on", doc.get(True))
    assert triggers["push"]["branches"] == ["main"]
    source = ast.parse((ROOT / "scripts/oracle_data.py").read_text())
    data_paths = ast.literal_eval(
        next(
            node.value
            for node in source.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "DATA_PATHS"
                for target in node.targets
            )
        )
    )
    assert set(triggers["push"]["paths"]) == {
        path + "**" if path.endswith("/") else path for path in data_paths
    }
    job = doc["jobs"]["reconcile"]
    checkout = next(
        step
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/checkout@")
    )
    assert checkout["with"] == {"ref": "main", "fetch-depth": 0}
    shell = runs(job)
    prepare = shell.index("scripts/oracle_data.py prepare --reconcile")
    regenerate = shell.index("SIMULATE_DERIVED_REFRESH=1")
    publish = shell.index("scripts/oracle_data.py publish --group all")
    assert prepare < regenerate < publish
    assert "scripts/commit_refreshed_report.sh reconcile oracle-data" in shell
    assert "for attempt in 1 2 3; do" in shell
    assert (
        'subprocess.run(["git", "clean", "-fdx", "--", *DATA_PATHS], check=True)'
        in shell
    )
    assert "if python3 scripts/oracle_data.py publish --group all" in shell
    assert shell.rstrip().endswith("exit 1")


def test_reconcile_has_scheduled_and_manual_recovery_for_missed_pushes():
    doc = workflow("oracle-data-reconcile.yml")
    triggers = doc.get("on", doc.get(True))
    assert set(triggers) == {"push", "schedule", "workflow_dispatch"}
    assert triggers["push"]["branches"] == ["main"]
    assert triggers["schedule"] == [{"cron": "0 */3 * * *"}]
    assert doc["jobs"]["reconcile"]["concurrency"] == {
        "group": "oracle-data-publication",
        "cancel-in-progress": False,
        "queue": "max",
    }


@pytest.fixture
def scheduled_reconcile_case(tmp_path, monkeypatch):
    import shutil

    from test_oracle_data import commit, data, git
    from test_oracle_data_snapshot_properties import _case

    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    monkeypatch.delenv("AXIOM_ORACLES_DATA_SOURCE", raising=False)
    case = _case(tmp_path)
    # Keep the real snapshot/merge CLI and the fixture's real complete derived
    # family. The other generators supply declarations used by merge policy.
    for name in (
        "oracle_data.py",
        "check_vacuous_gate.py",
        "conformance_scoreboard.py",
        "conformance_burndown.py",
        "exercise_census.py",
        "de_certificate_census.py",
        "certify.py",
        "generate_affected_map.py",
    ):
        shutil.copy2(ROOT / "scripts" / name, case.seed / "scripts" / name)
    (case.seed / "scripts/commit_refreshed_report.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'if [ "${SIMULATE_DERIVED_REFRESH:-0}" = 1 ]; then\n'
        '  echo generate >> "$ORACLE_DATA_ACTIVITY"\n'
        '  "$PYTHON" scripts/generate_dashboard_overview.py\n'
        '  "$PYTHON" scripts/oracle_data.py snapshot\n'
        "  exit 0\nfi\n"
        '[ "${VERIFY_DERIVED_REFRESH:-0}" = 1 ]\n'
        'echo gate >> "$ORACLE_DATA_ACTIVITY"\n'
        '"$PYTHON" scripts/generate_dashboard_overview.py --check\n'
    )
    (case.seed / "scripts/commit_refreshed_report.sh").chmod(0o755)
    case.main = commit(case.seed, {})
    git(case.seed, "push", "origin", f"HEAD:{data.MAIN_REF}", f"HEAD:{data.DATA_REF}")
    case.activity = tmp_path / "generation-and-gates"
    monkeypatch.setenv("ORACLE_DATA_ACTIVITY", str(case.activity))
    return case


def _run_scheduled_reconcile(case, tmp_path):
    import os
    import subprocess
    import sys

    from test_oracle_data import data, git

    # Match checkout@v4's main checkout. A successful probe must not overlay
    # published data here: prepare/publish expects this checkout to stay clean.
    git(case.publisher, "fetch", "origin", data.MAIN_REF)
    git(case.publisher, "reset", "--hard", "FETCH_HEAD")
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    shell = next(
        step["run"]
        for step in workflow("oracle-data-reconcile.yml")["jobs"]["reconcile"]["steps"]
        if "for attempt in 1 2 3" in step.get("run", "")
    )
    result = subprocess.run(
        ["bash", "-eo", "pipefail", "-c", shell],
        cwd=case.publisher,
        env={
            **os.environ,
            "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
            "PYTHON": sys.executable,
            "GITHUB_EVENT_NAME": "schedule",
            "RUNNER_TEMP": str(runner_temp),
        },
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not list(runner_temp.iterdir()), "the scratch probe checkout must be removed"
    return result


def test_scheduled_reconcile_recovers_after_the_last_push_reconcile_is_dropped(
    scheduled_reconcile_case, tmp_path
):
    import subprocess
    import sys

    from test_oracle_data import data, git
    from test_oracle_data_snapshot_properties import (
        BOT_REPORT,
        _published,
        _read,
        _refresh,
        _review,
    )

    case = scheduled_reconcile_case
    assert _refresh(case, 1, "bot-report")
    _review(case, 2, "main-edit-bot")
    reviewed_main = case.main
    reviewed_bytes = (case.seed / BOT_REPORT).read_bytes()
    before_data = _published(case)
    case.activity.unlink()
    assert not _read(case, baseline=False)
    assert not _read(case, baseline=True)

    # Deliberately drop the push-triggered reconcile. Ordinary publishers and
    # producer selection cannot resolve this primary-report conflict, however
    # many subsequent runs are queued.
    git(case.publisher, "fetch", "origin", data.MAIN_REF)
    git(case.publisher, "reset", "--hard", "FETCH_HEAD")
    for _ in range(3):
        for arguments in (("prepare",), ("materialize", "--baseline")):
            result = subprocess.run(
                [sys.executable, "scripts/oracle_data.py", *arguments],
                cwd=case.publisher,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode != 0, result.stdout + result.stderr
            assert "merge failed" in result.stderr
        assert not _read(case, baseline=False)
    assert _published(case) == before_data
    assert git(case.origin, "rev-parse", data.MAIN_REF) == reviewed_main
    assert not case.activity.exists()

    # Evaluate this only after reproducing the wedged producers, so the old
    # workflow fails specifically because it cannot dispatch scheduled recovery.
    doc = workflow("oracle-data-reconcile.yml")
    triggers = doc.get("on", doc.get(True))
    assert "schedule" in triggers, "a dropped push reconcile needs scheduled recovery"
    _run_scheduled_reconcile(case, tmp_path)
    assert case.activity.read_text().splitlines() == ["generate", "gate"]
    assert _published(case) != before_data
    assert git(case.origin, "rev-parse", data.MAIN_REF) == reviewed_main
    assert _read(case, baseline=False), "the next scheduled run must restore reads"
    assert (case.reader / BOT_REPORT).read_bytes() == reviewed_bytes


def test_scheduled_reconcile_with_readable_data_publishes_nothing(
    scheduled_reconcile_case, tmp_path
):
    from test_oracle_data import data, git
    from test_oracle_data_snapshot_properties import _published, _refresh, _state

    case = scheduled_reconcile_case
    assert _refresh(case, 1, "bot-report")
    case.activity.unlink()
    git(case.publisher, "fetch", "origin", data.MAIN_REF)
    git(case.publisher, "reset", "--hard", "FETCH_HEAD")
    # This live publication differs from main. Materializing directly in the
    # publisher would leave an overlay even though the probe succeeds.
    assert git(case.publisher, "diff", "HEAD", _published(case), "--", "dashboard")
    before_checkout = _state(case.publisher)
    before_data = _published(case)
    before_main = git(case.origin, "rev-parse", data.MAIN_REF)
    _run_scheduled_reconcile(case, tmp_path)
    assert not case.activity.exists(), "a healthy read needs no generation or gates"
    assert _published(case) == before_data
    assert git(case.origin, "rev-parse", data.MAIN_REF) == before_main
    assert _state(case.publisher) == before_checkout
    assert git(case.publisher, "status", "--porcelain") == ""


def test_reconcile_workflow_retries_a_source_only_main_race(tmp_path, monkeypatch):
    import os
    import shutil
    import subprocess
    import sys

    from test_oracle_data import commit, data, git
    from test_oracle_data_snapshot_properties import _case, _read, _review

    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    monkeypatch.delenv("AXIOM_ORACLES_DATA_SOURCE", raising=False)
    case = _case(tmp_path)
    # Run the actual CLI and merge policy. These generators are parsed for
    # their output declarations; the fixture's complete derived family is its
    # real overview, just as in the independent interleaving properties.
    for name in (
        "oracle_data.py",
        "check_vacuous_gate.py",
        "conformance_scoreboard.py",
        "conformance_burndown.py",
        "exercise_census.py",
        "de_certificate_census.py",
        "certify.py",
        "generate_affected_map.py",
    ):
        shutil.copy2(ROOT / "scripts" / name, case.seed / "scripts" / name)
    (case.seed / "scripts/commit_refreshed_report.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'if [ "${SIMULATE_DERIVED_REFRESH:-0}" = 1 ]; then\n'
        '  "$PYTHON" scripts/generate_dashboard_overview.py\n'
        '  "$PYTHON" scripts/oracle_data.py snapshot\n'
        "  exit 0\nfi\n"
        '[ "${VERIFY_DERIVED_REFRESH:-0}" = 1 ]\n'
        '"$PYTHON" scripts/generate_dashboard_overview.py --check\n'
        "\"$PYTHON\" - <<'PY'\n"
        "import os\n"
        "from pathlib import Path\n"
        "import subprocess\n"
        'with Path(os.environ["ORACLE_DATA_ATTEMPTS"]).open("a") as stream:\n'
        '    stream.write("publish\\n")\n'
        'marker = Path(os.environ["ORACLE_DATA_RACE_MARKER"])\n'
        "if not marker.exists():\n"
        '    seed = Path(os.environ["ORACLE_DATA_RACE_SEED"])\n'
        '    (seed / "source.py").write_text("source-only advancement during publication\\n")\n'
        '    subprocess.run(["git", "add", "source.py"], cwd=seed, check=True)\n'
        '    subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.com", "commit", "-m", "source-only race"], cwd=seed, check=True)\n'
        '    subprocess.run(["git", "push", "origin", "HEAD:refs/heads/main"], cwd=seed, check=True)\n'
        '    marker.write_text(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=seed, text=True).strip())\n'
        "PY\n"
    )
    (case.seed / "scripts/commit_refreshed_report.sh").chmod(0o755)
    case.main = commit(case.seed, {})
    git(case.seed, "push", "origin", f"HEAD:{data.MAIN_REF}", f"HEAD:{data.DATA_REF}")
    _review(case, 2, "main-add")
    reviewed_main = case.main
    assert not _read(case, baseline=False), (
        "the reviewed data commit needs reconciliation"
    )
    git(case.publisher, "fetch", "origin", data.MAIN_REF)
    git(case.publisher, "reset", "--hard", "FETCH_HEAD")
    attempts = tmp_path / "publication-attempts"
    marker = tmp_path / "source-only-main"
    job = workflow("oracle-data-reconcile.yml")["jobs"]["reconcile"]
    shell = next(
        step["run"]
        for step in job["steps"]
        if "for attempt in 1 2 3" in step.get("run", "")
    )
    env = {
        **os.environ,
        "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
        "PYTHON": sys.executable,
        "ORACLE_DATA_ATTEMPTS": str(attempts),
        "ORACLE_DATA_RACE_MARKER": str(marker),
        "ORACLE_DATA_RACE_SEED": str(case.seed),
    }
    result = subprocess.run(
        ["bash", "-eo", "pipefail", "-c", shell],
        cwd=case.publisher,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert attempts.read_text().splitlines() == ["publish", "publish"]
    assert "Publication attempt 1 failed" in result.stdout
    raced_main = marker.read_text()
    assert git(case.origin, "rev-parse", data.MAIN_REF) == raced_main
    assert (
        git(case.seed, "diff", "--name-only", reviewed_main, raced_main) == "source.py"
    )
    assert _read(case, baseline=False), (
        "one producer run must restore a bound consumer read"
    )


def reads_published_data(job):
    for step in job.get("steps", []):
        shell = step.get("run", "")
        if re.search(r"oracle_data\.py\s+materialize\b|materialize-data\.mjs", shell):
            return True
        directory = step.get(
            "working-directory",
            job.get("defaults", {}).get("run", {}).get("working-directory", ""),
        )
        if directory == "dashboard" and re.search(
            r"\b(?:bun|npm|pnpm)\s+run\s+(?:dev|build)\b", shell
        ):
            return True
    return False


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
    assert {name for name, job in ci["jobs"].items() if reads_published_data(job)} == {
        "dashboard"
    }


@pytest.mark.parametrize(
    "path", ["scripts/regenerate_all.sh", "dashboard/scripts/regenerate_all.sh"]
)
def test_unattended_publishers_use_guarded_data_branch(path):
    script = (ROOT / path).read_text()
    assert "git push" not in script
    prepare = script.index("scripts/oracle_data.py prepare")
    compute = script.index("./scripts/sync_rulespec_roots.sh")
    regenerate = script.index("SIMULATE_DERIVED_REFRESH=1")
    publish = script.index("scripts/oracle_data.py publish --group all")
    deploy = script.index("vercel --prod")
    assert prepare < compute < regenerate < publish < deploy
    assert "scripts/commit_refreshed_report.sh scheduled oracle-data" in script
    assert "git switch -C oracle-data" in script
    assert "AXIOM_ORACLES_DATA_SOURCE=checkout bun run build" in script


def test_workflow_publications_are_serialized_on_the_data_branch():
    for file, job_name in PUBLISHERS:
        assert workflow(file)["jobs"][job_name]["concurrency"] == {
            "group": "oracle-data-publication",
            "cancel-in-progress": False,
            "queue": "max",
        }


@pytest.mark.parametrize(
    "scenario",
    [
        "checkout",
        "project-python",
        "ci",
        "missing-git",
        "missing-helper",
        "failed-read",
    ],
)
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
    interpreter = (
        (root / ".venv/bin/python")
        if scenario == "project-python"
        else bin_dir / "python3"
    )
    interpreter.parent.mkdir(parents=True, exist_ok=True)
    interpreter.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$PWD" "$1" "$2" > "$CALL_LOG"\n'
        'exit "${HELPER_STATUS:-0}"\n'
    )
    interpreter.chmod(0o755)
    log = root / "python-call"
    env = {
        **os.environ,
        "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
        "CALL_LOG": str(log),
        "HELPER_STATUS": "17" if scenario == "failed-read" else "0",
    }
    env.pop("AXIOM_ORACLES_DATA_SOURCE", None)
    if scenario == "ci":
        env["AXIOM_ORACLES_DATA_SOURCE"] = "checkout"
    result = subprocess.run(
        ["node", str(wrapper)],
        cwd=dashboard,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == (17 if scenario == "failed-read" else 0), result.stderr
    if scenario in {"checkout", "project-python", "failed-read"}:
        assert log.read_text().splitlines() == [str(root), str(helper), "materialize"]
    else:
        assert not log.exists(), "CI and uploaded builds must not need Python or Git"
