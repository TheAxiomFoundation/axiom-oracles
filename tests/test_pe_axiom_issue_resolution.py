"""GitHub's issues route can return a PR: resolution must inspect its payload."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings, strategies as st

from axiom_oracles.comparison.dispositions import apply_dispositions, report_json_text
from axiom_oracles.comparison.pe_axiom_standard import (
    CompanionPointer,
    CompanionResolver,
    Record,
    collect_records,
    is_pe_issue_url,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/pe_axiom_standard"
PE_PR_ALIAS = "https://github.com/PolicyEngine/policyengine-us/issues/8614"
PE_ISSUE = "https://github.com/PolicyEngine/policyengine-us/issues/8613"
API_ISSUE = "https://api.github.com/repos/PolicyEngine/policyengine-us/issues/8613"
ISSUE_PAYLOAD = {
    "number": 8613,
    "html_url": PE_ISSUE,
    "state": "closed",
}


class RecordedSource:
    """Inject both companion contents and a network-free GitHub JSON fetcher."""

    def __init__(self, record: Record, fetch_json):
        self.fetch_json = fetch_json
        companion = record.entry.get("axiom_companion")
        if companion:
            self.pointer = CompanionPointer.parse(companion["tests"][0])
            assert self.pointer is not None
            self.contents = yaml.safe_dump([
                {
                    "name": self.pointer.case,
                    "output": {record.concept: 10000},
                },
            ])

    def read(self, repo, sha, path):
        return self.contents

    def is_merged(self, repo, sha):
        return True

    def main_sha(self, repo):
        return self.pointer.sha


def _salt_record(tmp_path: Path, pe_url: str = PE_ISSUE) -> Record:
    """The review witness's real SALT disposition and comparison report."""

    data = tmp_path / "dashboard/public/data"
    data.mkdir(parents=True)
    (tmp_path / "dispositions").mkdir()
    doc = yaml.safe_load((ROOT / "dispositions/us-salt-deduction-grid.yaml").read_text())
    doc["entries"] = doc["entries"][:1]
    entry = doc["entries"][0]
    entry["evidence"]["upstream_url"] = pe_url
    entry["evidence"]["mechanism"] = entry["evidence"]["mechanism"].replace(
        "/issues/9167", pe_url.removeprefix("https://github.com/PolicyEngine/policyengine-us")
    )
    (tmp_path / "dispositions/us-salt-deduction-grid.yaml").write_text(yaml.safe_dump(doc))
    report = json.loads((ROOT / "dashboard/public/data/axiom-policyengine-us-salt-deduction-grid.json").read_text())
    report = apply_dispositions(
        report, doc, dispositions_file="dispositions/us-salt-deduction-grid.yaml"
    )
    (data / "report.json").write_text(report_json_text(report))
    records, errors = collect_records(tmp_path)
    assert errors == [] and len(records) == 1
    assert records[0].axiom_values == {"salt-low-agi-engine-cap": (10000.0,)}
    return records[0]


def test_policyengine_pr_under_issues_route_is_rejected(tmp_path: Path) -> None:
    # Recorded with read-only gh api GET repos/PolicyEngine/policyengine-us/issues/8614.
    payload = json.loads((FIXTURES / "pe-pr-8614.json").read_text())
    assert "pull_request" in payload and payload["html_url"].endswith("/pull/8614")
    record = _salt_record(tmp_path, PE_PR_ALIAS)
    assert is_pe_issue_url(record.pe_issue)
    requested = []

    def fetch_json(url):
        requested.append(url)
        return 200, payload

    problems = CompanionResolver(RecordedSource(record, fetch_json)).resolve(record)
    assert any("is a pull request" in problem for problem in problems), problems
    assert requested == ["https://api.github.com/repos/PolicyEngine/policyengine-us/issues/8614"]


@pytest.mark.parametrize(
    ("status", "payload", "needle"),
    [
        pytest.param(404, None, "no such issue", id="absent-404"),
        pytest.param(410, None, "no such issue", id="absent-410"),
        pytest.param(200, {}, "cannot verify", id="empty-payload"),
        pytest.param(503, None, "cannot verify", id="unavailable-503"),
        pytest.param(403, None, "cannot verify", id="forbidden-403"),
        pytest.param(200, None, "cannot verify", id="invalid-json"),
        pytest.param(200, [], "cannot verify", id="invalid-type"),
        pytest.param(200, {"state": "open"}, "cannot verify", id="missing-identity"),
        pytest.param(200, dict(ISSUE_PAYLOAD, number=8614), "cannot verify", id="wrong-number"),
        pytest.param(200, dict(ISSUE_PAYLOAD, html_url="https://github.com/PolicyEngine/other/issues/8613"), "cannot verify", id="wrong-repository"),
        pytest.param(200, dict(ISSUE_PAYLOAD, pull_request=None), "is a pull request", id="pr-key-null"),
    ],
)
def test_policyengine_issue_resolution_fails_closed(tmp_path: Path, status, payload, needle) -> None:
    record = _salt_record(tmp_path)
    source = RecordedSource(record, lambda url: (status, payload))
    problems = CompanionResolver(source).resolve(record)
    assert any(needle in problem for problem in problems), problems


@pytest.mark.parametrize("state", ["open", "closed"])
def test_policyengine_issue_state_does_not_limit_resolution(tmp_path: Path, state) -> None:
    record = _salt_record(tmp_path)
    payload = json.loads((FIXTURES / "pe-issue-8613.json").read_text())
    payload["state"] = state
    requested = []

    def fetch_json(url):
        requested.append(url)
        return 200, payload

    resolver = CompanionResolver(RecordedSource(record, fetch_json))
    assert resolver.resolve(record) == []
    assert resolver.resolve(record) == []
    assert requested == [API_ISSUE]  # Shared URLs are read once per resolver.


def test_resolve_cli_rejects_the_recorded_policyengine_pr(tmp_path: Path, monkeypatch, capsys) -> None:
    record = _salt_record(tmp_path, PE_PR_ALIAS)
    payload = json.loads((FIXTURES / "pe-pr-8614.json").read_text())
    source = RecordedSource(record, lambda url: (200, payload))
    spec = importlib.util.spec_from_file_location("issue_resolution_cli", ROOT / "scripts/pe_axiom_standard.py")
    assert spec is not None and spec.loader is not None
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    monkeypatch.setattr(script, "_source", lambda args: source)
    monkeypatch.setattr(script, "GitHubSource", lambda **kwargs: source)
    assert script.main(["--resolve"], repo_root=tmp_path) == 1
    assert "is a pull request" in capsys.readouterr().err


def test_the_json_fetcher_can_be_injected_independently(tmp_path: Path) -> None:
    record = _salt_record(tmp_path)
    source = RecordedSource(record, None)
    resolver = CompanionResolver(source, fetch_json=lambda url: (200, ISSUE_PAYLOAD))
    assert resolver.resolve(record) == []


def test_a_missing_json_fetcher_cannot_verify_the_issue(tmp_path: Path) -> None:
    record = _salt_record(tmp_path)
    source = RecordedSource(record, None)
    problems = CompanionResolver(source).resolve(record)
    assert any("no GitHub source to verify" in problem for problem in problems), problems


@pytest.mark.parametrize("error", [OSError("timeout"), ValueError("invalid JSON")])
def test_a_failed_json_fetcher_cannot_verify_the_issue(tmp_path: Path, error) -> None:
    record = _salt_record(tmp_path)

    def fetch_json(url):
        raise error

    problems = CompanionResolver(RecordedSource(record, fetch_json)).resolve(record)
    assert any("cannot verify" in problem for problem in problems), problems


@settings(max_examples=100, deadline=None, derandomize=True)
@given(st.dictionaries(st.text(max_size=10), st.none() | st.integers() | st.text(max_size=10)))
def test_a_pull_request_key_can_never_verify_a_policyengine_issue(pr_fields) -> None:
    # Every PR payload fails, even with otherwise valid issue identity and no companion.
    record = Record("dispositions/example.yaml", "gap", "example", "us:x#y", "url", PE_ISSUE, {})
    payload = copy.deepcopy(ISSUE_PAYLOAD)
    payload["pull_request"] = pr_fields
    source = RecordedSource(record, lambda url: (200, payload))
    problems = CompanionResolver(source).resolve(record)
    assert any("is a pull request" in problem for problem in problems), problems
