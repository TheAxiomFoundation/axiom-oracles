"""Adversarial checks for GitHub identities and the gate's historical floor."""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from axiom_oracles.comparison.pe_axiom_standard import (
    CompanionResolver,
    GitHubSource,
    Ratchet,
    Record,
    UPSTREAM_ENGINE_GAP,
    attribute_disposition,
    check_history,
    check_records,
    collect_records,
    derive_ratchet,
    effective_ratchet,
    history_ceiling,
    is_pe_issue_url,
    is_pe_link_url,
)


PE_ISSUE = "https://github.com/PolicyEngine/policyengine-us/issues/8613"
DEBT_ISSUE = "https://github.com/TheAxiomFoundation/rulespec-us/issues/123"
CONCEPT = "us:policies/example#amount"
PE_ALIASES = [
    pytest.param(PE_ISSUE.replace("github.com", "GITHUB.COM"), id="host-case"),
    pytest.param(PE_ISSUE.replace("PolicyEngine", "%50olicyEngine"), id="encoded-owner"),
    pytest.param(PE_ISSUE.replace("/8613", "/08613"), id="zero-padded-number"),
    pytest.param(PE_ISSUE.replace("/PolicyEngine/", "/PolicyEngine/./"), id="dot-segment"),
    pytest.param(PE_ISSUE.replace("https://", "http://"), id="http-redirect"),
    pytest.param("https://api.github.com/repos/PolicyEngine/policyengine-us/issues/8613", id="api-issue"),
    pytest.param(PE_ISSUE.replace("github.com", "www.github.com"), id="www-redirect"),
]
BROWSER_ALIASES = [
    pytest.param(PE_ISSUE.removeprefix("https:"), id="protocol-relative"),
    pytest.param(f" \t{PE_ISSUE}\r\n ", id="browser-whitespace"),
    pytest.param(PE_ISSUE.replace("github.com/", "github.com\\"), id="browser-backslash"),
    pytest.param(PE_ISSUE.replace("github.com", "%67ithub.com"), id="encoded-host"),
    pytest.param(PE_ISSUE.replace("github.com", "ｇｉｔｈｕｂ．ｃｏｍ"), id="idna-host"),
    pytest.param(PE_ISSUE.replace("https://", "https:///"), id="extra-authority-slash"),
    pytest.param(PE_ISSUE.replace("https://", "https:////"), id="extra-authority-slashes"),
]


def _record(pe_url: str = PE_ISSUE, **entry) -> Record:
    return Record("dispositions/example.yaml", "gap", "example", CONCEPT, "url", pe_url, entry)


def _url_only_cause_records(tmp_path: Path, url: str):
    data = tmp_path / "dashboard/public/data"
    data.mkdir(parents=True)
    (data / "report.json").write_text(json.dumps({
        "suite": "example", "engines": {"left": "axiom", "right": "taxsim"},
        "summary": {"mismatch_count": 1},
        "mismatches": [{"case_id": "case", "concept": CONCEPT, "kind": "amount_difference"}],
    }))
    (data / "known_causes.json").write_text(json.dumps({"entries": [{
        "suite": "example", "concept": CONCEPT, "kind": "amount_difference",
        "fix_owner": "other", "issue_url": url,
    }]}))
    return collect_records(tmp_path)


@pytest.mark.parametrize("url", PE_ALIASES)
def test_equivalent_policyengine_urls_cannot_hide_attribution(url: str, tmp_path: Path) -> None:
    # Read-only GETs of these aliases return issue #8613 and its canonical og:url.
    # Both explanatory input surfaces must recognize that same PE identity.
    entry = {"id": "gap", "concept": CONCEPT, "disposition": UPSTREAM_ENGINE_GAP, "linked_issue": url}
    assert attribute_disposition(entry, [])[0] == "url"
    records, errors = _url_only_cause_records(tmp_path, url)
    assert errors == [] and len(records) == 1
    assert check_records(records, Ratchet(open_max=0))


@pytest.mark.parametrize("url", BROWSER_ALIASES)
def test_browser_equivalent_policyengine_urls_cannot_hide_attribution(url: str, tmp_path: Path) -> None:
    canonical = subprocess.run(
        ["node", "-e", "process.stdout.write(new URL(process.argv[1], 'https://axiom.invalid').href)", url],
        check=True, capture_output=True, text=True,
    ).stdout
    assert canonical == PE_ISSUE
    assert is_pe_link_url(url) and is_pe_issue_url(url)
    entry = {"id": "gap", "concept": CONCEPT, "disposition": UPSTREAM_ENGINE_GAP, "linked_issue": url}
    assert attribute_disposition(entry, [])[0] == "url"
    records, errors = _url_only_cause_records(tmp_path, url)
    assert errors == [] and len(records) == 1
    assert check_records(records, Ratchet(open_max=0))


@pytest.mark.parametrize("scheme", ["http:", "http:/"])
def test_http_browser_href_cannot_hide_policyengine_attribution(scheme: str, tmp_path: Path) -> None:
    url = scheme + PE_ISSUE.removeprefix("https://")
    canonical = subprocess.run(
        ["node", "-e", "process.stdout.write(new URL(process.argv[1], 'https://axiom.invalid').href)", url],
        check=True, capture_output=True, text=True,
    ).stdout
    assert canonical == PE_ISSUE.replace("https://", "http://")
    # A no/one-slash href can be relative under a same-scheme dashboard base.
    # Attribute conservatively, but require a clear issue URL for citation.
    assert is_pe_link_url(url) and not is_pe_issue_url(url)
    entry = {"id": "gap", "concept": CONCEPT, "disposition": UPSTREAM_ENGINE_GAP, "linked_issue": url}
    assert attribute_disposition(entry, [])[0] == "url"
    records, errors = _url_only_cause_records(tmp_path, url)
    assert errors == [] and len(records) == 1
    assert records[0].pe_issue is None
    assert any("a PolicyEngine issue URL" in problem for problem in check_records(records, Ratchet(open_max=1)))


@settings(max_examples=100, deadline=None, derandomize=True)
@given(slash_count=st.integers(min_value=2, max_value=50), scheme=st.sampled_from(["http", "https"]))
def test_browser_authority_slash_counts_preserve_policyengine_identity(slash_count, scheme) -> None:
    url = f"{scheme}:{'/' * slash_count}" + PE_ISSUE.removeprefix("https://")
    assert is_pe_link_url(url) and is_pe_issue_url(url)


@pytest.mark.parametrize("prefix", ["https:", "https:/"])
def test_ambiguous_same_scheme_relative_github_links_require_a_clear_issue_url(prefix: str, tmp_path: Path) -> None:
    url = prefix + PE_ISSUE.removeprefix("https://")
    canonical = subprocess.run(
        ["node", "-e", "process.stdout.write(new URL(process.argv[1], 'https://axiom.invalid').href)", url],
        check=True, capture_output=True, text=True,
    ).stdout
    assert canonical.startswith("https://axiom.invalid/")
    assert is_pe_link_url(url) and not is_pe_issue_url(url)
    records, errors = _url_only_cause_records(tmp_path, url)
    assert errors == [] and len(records) == 1 and records[0].pe_issue is None
    assert any("a PolicyEngine issue URL" in problem for problem in check_records(records, Ratchet(open_max=1)))


def test_api_pull_link_attributes_without_satisfying_the_issue_requirement(tmp_path: Path) -> None:
    url = "https://api.github.com/repos/PolicyEngine/policyengine-us/pulls/8614"
    assert is_pe_link_url(url) and not is_pe_issue_url(url)
    entry = {"id": "gap", "concept": CONCEPT, "disposition": UPSTREAM_ENGINE_GAP, "linked_issue": url}
    assert attribute_disposition(entry, [])[0] == "url"
    records, errors = _url_only_cause_records(tmp_path, url)
    assert errors == [] and len(records) == 1 and records[0].pe_issue is None
    assert any("a PolicyEngine issue URL" in problem for problem in check_records(records, Ratchet(open_max=1)))


@settings(max_examples=100, deadline=None, derandomize=True)
@given(
    host=st.sampled_from(["github.com", "GITHUB.COM", "GitHub.Com"]),
    owner=st.sampled_from(["PolicyEngine", "policyengine", "%50olicyEngine"]),
    padding=st.integers(min_value=0, max_value=4),
    dot=st.sampled_from(["", "./", "unused/../"]),
    suffix=st.sampled_from(["", "/", "?query=ignored#issuecomment-1"]),
)
def test_equivalent_policyengine_urls_resolve_the_same_issue(host, owner, padding, dot, suffix) -> None:
    url = f"https://{host}/{owner}/{dot}policyengine-us/issues/{'0' * padding}8613{suffix}"
    assert is_pe_link_url(url) and is_pe_issue_url(url)
    requested = []

    def fetch_json(api_url):
        requested.append(api_url)
        return 200, {"number": 8613, "html_url": PE_ISSUE, "state": "open"}

    resolver = CompanionResolver(object(), fetch_json=fetch_json)
    assert resolver.resolve_pe_issue(_record(url)) == []
    assert requested == ["https://api.github.com/repos/PolicyEngine/policyengine-us/issues/8613"]


class _InjectedGitHubSource(GitHubSource):
    def __init__(self, payload):
        super().__init__(attempts=1, backoff=0)
        self.payload = payload

    def _json(self, url):
        return 200, self.payload


@pytest.mark.parametrize("debt", [False, True], ids=["policyengine", "rulespec-debt"])
@pytest.mark.parametrize("repository_url", [
    "https://api.github.com/repos/OtherOwner/unrelated",
    "https://api.github.com/repos/PolicyEngine/policyengine-us/issues/8613",
    None,
], ids=["different-repository", "wrong-api-route", "null-identity"])
def test_issue_payload_repository_identity_cannot_disagree(debt: bool, repository_url) -> None:
    record = _record(axiom_encoding_debt=DEBT_ISSUE) if debt else _record()
    payload = {
        "number": 123 if debt else 8613,
        "html_url": DEBT_ISSUE if debt else PE_ISSUE,
        "state": "open", "repository_url": repository_url,
    }
    resolver = CompanionResolver(_InjectedGitHubSource(payload))
    problems = resolver.resolve_debt(record) if debt else resolver.resolve_pe_issue(record)
    assert any("cannot verify the issue identity" in problem for problem in problems), problems


@pytest.mark.parametrize("url", [
    "https://github.com.evil.example/PolicyEngine/policyengine-us/issues/8613",
    "https://github.com@evil.example/PolicyEngine/policyengine-us/issues/8613",
    "https://github.com/PоlicyEngine/policyengine-us/issues/8613",  # Cyrillic o.
    "https://github.com/PolicyEngine/policyengine-us/issues/０８６１３",
    "https://github.com/PolicyEngine/policyengine-us/issues/0",
    "https://github.com//PolicyEngine/policyengine-us/issues/8613",
    "https://github.com/PolicyEngine/policyengine-us/issues/8613//",
    "https://github.com/PolicyEngine%2Fpolicyengine-us/issues/8613",
    "https://github.com/PolicyEngine%5Cpolicyengine-us/issues/8613",
    "https://api.github.com/repos/PolicyEngine/policyengine-us/issues/8613/comments",
    "https://api.github.com/repos/PolicyEngine/policyengine-us/pulls",
    "https://github.com/PolicyEngine/policyengine-us//issues/8613",
    "https://github.com/PolicyEngine/policyengine-us/issues//8613",
    "https:github.com/PolicyEngine/policyengine-us/issues/8613",
    "https:/github.com/PolicyEngine/policyengine-us/issues/8613",
    "https://github.com/PolicyEngine/policyengine-us/issues/+8613",
    "https://github.com/PolicyEngine/policyengine-us/issues/8613.0",
    "https://github.com/PolicyEngine/policyengine-us/issues/8613extra",
    "https://github.com/PolicyEngine/policyengine-us/issues/8613%20",
    "https://github.com/PolicyEngine/policyengine-us/issues/%EF%BC%98%EF%BC%96%EF%BC%91%EF%BC%93",
    "https://github.com/PolıcyEngine/policyengine-us/issues/8613",  # Dotless i.
    "https://github.com/PolicyEngİne/policyengine-us/issues/8613",  # Dotted I.
    "https://api.github.com/repos/PolıcyEngine/policyengine-us/issues/8613",
])
def test_policyengine_lookalikes_cannot_satisfy_issue_identity(url: str) -> None:
    assert not is_pe_issue_url(url)


@settings(max_examples=100, deadline=None, derandomize=True)
@given(open_max=st.integers(0, 1000), increase=st.integers(1, 1000))
def test_history_never_allows_more_than_an_appended_raise_increment(open_max, increase) -> None:
    historical = Ratchet(open_max=open_max)
    current = Ratchet(open_max=open_max + increase + 1, debt_raises=[{
        "date": "2026-10-06", "from": 5000, "to": 5000 + increase, "reason": "raise",
    }])
    versions = [("committed", historical)]
    assert history_ceiling(current, versions) == (open_max + increase, "committed")
    assert any("exceeds the committed floor" in problem for problem in check_history(current, versions))


@pytest.mark.parametrize("field", ["source", "id", "concept"])
def test_history_rejects_forged_grandfather_identity(field: str) -> None:
    baseline = Ratchet.from_document(derive_ratchet([_record()], None))
    document = derive_ratchet([_record()], baseline)
    document["grandfathered"][0][field] += "-forged"
    current = Ratchet.from_document(document)
    assert any("grandfather door is closed" in problem for problem in check_history(current, [("baseline", baseline)]))


@pytest.mark.parametrize("change", ["delete", "date", "reason", "from", "to"])
def test_history_rejects_deleting_or_editing_committed_raises(change: str) -> None:
    baseline = Ratchet(open_max=2, debt_raises=[{
        "date": "2026-10-05", "from": 1, "to": 2, "reason": "committed raise",
    }])
    current = copy.deepcopy(baseline)
    if change == "delete":
        current.debt_raises = []
    elif change in {"date", "reason"}:
        current.debt_raises[0][change] += "-edited"
    else:
        current.debt_raises[0][change] += 1
    assert any("the log only grows" in problem for problem in check_history(current, [("baseline", baseline)]))


def test_uncommitted_grandfather_removal_cannot_hide_a_status_downgrade() -> None:
    record = _record()
    baseline = Ratchet.from_document(derive_ratchet([record], None))
    baseline.grandfathered[record.key]["axiom"] = "companion"
    current = Ratchet(open_max=1)
    history = [("baseline", baseline)]
    assert any("grandfathered entry regressed" in problem for problem in check_records([record], current, versions=history))
    assert record.key not in effective_ratchet(current, history).grandfathered
