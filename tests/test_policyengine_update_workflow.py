"""The updater can propose versions without rewriting comparison evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest
import yaml

from scripts import publish_policyengine_update as publisher

ROOT = Path(__file__).resolve().parents[1]
BASE = "a" * 40
PACKAGES = {
    "policyengine": "6.12.0",
    "policyengine-us": "2.91.12",
    "policyengine-core": "3.44.0",
    "spm-calculator": "0.3.1",
}


@pytest.fixture
def proposal(tmp_path, monkeypatch):
    baseline = {"schema": 1, "packages": {**PACKAGES, "policyengine-us": "2.90.0"}}
    lock = (
        "\n".join(
            f"{name}=={version} \\\n    --hash=sha256:{'b' * 64}"
            for name, version in PACKAGES.items()
        )
        + "\n"
    )
    payload = {
        "schema": 1,
        "base_commit": BASE,
        "baseline": baseline,
        "candidate": {"schema": 1, "packages": PACKAGES},
        "status": "passed",
        "latest_model": "2.91.12",
        "fixture_sha256": "c" * 64,
        "candidate_lock_sha256": hashlib.sha256(lock.encode()).hexdigest(),
        "changes": [],
        "baseline_result": {"compared": 8},
        "candidate_result": {"compared": 8},
        "limitations": ["Bounded sample only."],
    }
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    (artifact / "proposal.json").write_text(json.dumps(payload))
    (artifact / "candidate-requirements.txt").write_text(lock)
    # Artifact Markdown is never copied into the publication checkout.
    (artifact / "report.md").write_text("untrusted Markdown must not be published")
    checkout = tmp_path / "checkout"
    (checkout / publisher.MANIFEST).parent.mkdir(parents=True)
    (checkout / publisher.MANIFEST).write_text(json.dumps(baseline))
    monkeypatch.setenv("GITHUB_REPOSITORY", publisher.REPOSITORY)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("DEFAULT_BRANCH", "main")
    monkeypatch.setenv("GITHUB_SHA", BASE)
    # Proposal schema and execution-result checks have their own updater tests.
    monkeypatch.setattr(publisher, "validate_proposal", lambda value: value)
    return artifact, checkout, payload


def fake_commands(monkeypatch, *, open_pr=False, existing_branch=False):
    calls = []

    def run(*args, cwd, check=True):
        calls.append(args)
        output, code = "", 0
        if args[:3] == ("git", "rev-parse", "HEAD"):
            output = BASE
        elif args[:3] == ("gh", "pr", "list"):
            output = json.dumps(
                [
                    {
                        "headRefName": publisher.BRANCH_PREFIX + "2.91.11",
                        "url": "https://github.com/example/pull/1",
                    }
                ]
                if open_pr
                else []
            )
        elif args[:2] == ("git", "ls-remote"):
            code = 0 if existing_branch else 2
        elif args[:4] == ("git", "diff", "--cached", "--name-only"):
            output = "\n".join(str(path) for path in publisher.ALLOWED_PATHS)
        elif args[:3] == ("gh", "pr", "create"):
            output = "https://github.com/example/pull/2"
        return subprocess.CompletedProcess(args, code, output, "")

    monkeypatch.setattr(publisher, "run", run)
    return calls


@pytest.mark.parametrize("status", ["passed", "needs-review"])
def test_publishes_only_draft_and_allowlisted_data(proposal, monkeypatch, status):
    artifact, checkout, payload = proposal
    payload["status"] = status
    (artifact / "proposal.json").write_text(json.dumps(payload))
    calls = fake_commands(monkeypatch)
    assert publisher.publish(artifact, repo_dir=checkout).endswith("/2")
    files = {
        str(path.relative_to(checkout))
        for path in checkout.rglob("*")
        if path.is_file()
    }
    assert files == {str(path) for path in publisher.ALLOWED_PATHS}
    assert (
        json.loads((checkout / publisher.MANIFEST).read_text()) == payload["candidate"]
    )
    assert "untrusted Markdown" not in (checkout / publisher.REPORT).read_text()
    pr = next(c for c in calls if c[:3] == ("gh", "pr", "create"))
    assert "--draft" in pr and "--base" in pr and "main" in pr
    push = next(c for c in calls if c[:2] == ("git", "push"))
    assert push == (
        "git",
        "push",
        "origin",
        "HEAD:refs/heads/automation/policyengine-us-2.91.12",
    )
    reserve = next(i for i, c in enumerate(calls) if c[:3] == ("gh", "api", "--method"))
    assert "POST" in calls[reserve] and f"sha={BASE}" in calls[reserve]
    assert reserve < calls.index(push)
    assert not any("--force" in c or "--auto" in c for c in calls)


@pytest.mark.parametrize("options", [{"open_pr": True}, {"existing_branch": True}])
def test_leaves_existing_review_work_untouched(proposal, monkeypatch, options):
    artifact, checkout, _ = proposal
    calls = fake_commands(monkeypatch, **options)
    assert publisher.publish(artifact, repo_dir=checkout) is None
    assert not any(c[:2] == ("git", "checkout") for c in calls)
    assert not (checkout / publisher.LOCK).exists()


@pytest.mark.parametrize("status", ["no-update", "failed"])
def test_no_proposal_for_failed_or_unchanged_probe(proposal, monkeypatch, status):
    artifact, checkout, payload = proposal
    payload["status"] = status
    (artifact / "proposal.json").write_text(json.dumps(payload))
    calls = fake_commands(monkeypatch)
    assert publisher.publish(artifact, repo_dir=checkout) is None
    assert calls == []


@pytest.mark.parametrize(
    "bad_line",
    [
        "evil @ https://example.com/package.whl",
        "--extra-index-url https://example.com/simple",
        "-e /tmp/candidate",
        "--trusted-host example.com",
    ],
)
def test_lock_cannot_supply_install_options_or_urls(proposal, bad_line):
    _, _, payload = proposal
    raw = (bad_line + "\n").encode()
    payload["candidate_lock_sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match="only exact"):
        publisher.validate_lock(raw, payload)


def test_refuses_tampered_lock_and_wrong_base(proposal, monkeypatch):
    artifact, checkout, payload = proposal
    fake_commands(monkeypatch)
    (artifact / "candidate-requirements.txt").write_text("tampered")
    with pytest.raises(ValueError, match="SHA-256"):
        publisher.publish(artifact, repo_dir=checkout)
    payload["base_commit"] = "d" * 40
    (artifact / "proposal.json").write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="trusted workflow checkout"):
        publisher.publish(artifact, repo_dir=checkout)


def test_refuses_duplicate_proposal_fields(proposal):
    artifact, checkout, _ = proposal
    (artifact / "proposal.json").write_text('{"status":"passed","status":"failed"}')
    with pytest.raises(ValueError, match="duplicate proposal field"):
        publisher.publish(artifact, repo_dir=checkout)


def test_workflow_separates_probe_execution_from_publication():
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/policyengine-us-updates.yml").read_text()
    )
    events = workflow.get("on", workflow.get(True))
    assert set(events) == {"schedule", "workflow_dispatch"}
    assert workflow["permissions"] == {"contents": "read"}
    probe, publish = (workflow["jobs"][name] for name in ("probe", "publish"))
    assert probe["permissions"] == {"contents": "read"}
    assert publish["permissions"] == {"contents": "write", "pull-requests": "write"}
    assert publish["needs"] == "probe" and "default_branch" in probe["if"]
    for job in (probe, publish):
        checkout = next(
            s for s in job["steps"] if s.get("uses", "").startswith("actions/checkout@")
        )
        assert checkout["with"]["persist-credentials"] is False
        assert checkout["with"]["ref"] == "${{ github.sha }}"
    probe_text = json.dumps(probe)
    assert "secrets." not in probe_text and "github.token" not in probe_text
    probe_command = next(
        s["run"]
        for s in probe["steps"]
        if "scripts/update_policyengine_defaults.py" in s.get("run", "")
    )
    assert "probe --output-dir" in probe_command
    publication = "\n".join(step.get("run", "") for step in publish["steps"])
    assert "scripts/publish_policyengine_update.py" in publication
    assert "scripts/update_policyengine_defaults.py" not in publication
    assert "--extra policyengine" not in publication
