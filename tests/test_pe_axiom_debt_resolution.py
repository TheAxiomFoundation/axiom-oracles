"""Encoding debt must retain a verifiable open RuleSpec issue after redirects."""

from __future__ import annotations

import copy

import pytest
from hypothesis import given, settings, strategies as st

from axiom_oracles.comparison.pe_axiom_standard import (
    RATCHET_SCHEMA,
    CompanionResolver,
    GitHubSource,
    Ratchet,
    Record,
    check_records,
    validate_axiom_side_fields,
)

PE_ISSUE = "https://github.com/PolicyEngine/policyengine-us/issues/8613"
DEBT_ISSUE = "https://github.com/TheAxiomFoundation/rulespec-us/issues/123"
API_DEBT_ISSUE = "https://api.github.com/repos/TheAxiomFoundation/rulespec-us/issues/123"
OPEN_ISSUE = {"number": 123, "state": "open", "html_url": DEBT_ISSUE}


class InjectedGitHubSource(GitHubSource):
    """Exercise production issue decoding with recorded final API payloads."""

    def __init__(self, fetch_json):
        super().__init__(attempts=1, backoff=0)
        self.injected_fetcher = fetch_json

    def _json(self, url):
        return self.injected_fetcher(url)


def _record() -> Record:
    # Ported from the review's transfer witness; no imports or HTTP reads.
    return Record(
        "dispositions/example.yaml", "new-gap", "example",
        "us:policies/example#amount", "url", PE_ISSUE,
        {"axiom_encoding_debt": DEBT_ISSUE},
    )


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(
            {"number": 590, "state": "open", "html_url": "https://github.com/TheAxiomFoundation/axiom-oracles/issues/590"},
            id="transferred-after-redirect",
        ),
        pytest.param(dict(OPEN_ISSUE, html_url="https://github.com/TheAxiomFoundation/renamed-us/issues/123"), id="repository-renamed"),
        pytest.param(dict(OPEN_ISSUE, html_url="https://github.com/OtherOwner/rulespec-us/issues/123"), id="owner-transferred"),
        pytest.param(dict(OPEN_ISSUE, number=124), id="wrong-payload-number"),
        pytest.param(dict(OPEN_ISSUE, html_url=DEBT_ISSUE.replace("/123", "/124")), id="wrong-url-number"),
        pytest.param({"number": 123, "state": "open"}, id="missing-url"),
        pytest.param({"state": "open", "html_url": DEBT_ISSUE}, id="missing-number"),
        pytest.param({"state": "open"}, id="missing-identity"),
        pytest.param(dict(OPEN_ISSUE, number="123"), id="string-number"),
        pytest.param(dict(OPEN_ISSUE, html_url=None), id="null-url"),
        pytest.param(dict(OPEN_ISSUE, html_url=DEBT_ISSUE.replace("/issues/", "/pull/")), id="pull-url"),
    ],
)
def test_encoding_debt_checks_the_final_issue_identity(payload) -> None:
    record = _record()
    ratchet = Ratchet.from_document({
        "schema": RATCHET_SCHEMA, "open_max": 1,
        "grandfathered": [], "debt_raises": [],
    })
    assert validate_axiom_side_fields(record.entry, record.label()) == []
    assert check_records([record], ratchet) == []
    requests = []

    def fetch_json(url):
        requests.append(url)
        return 200, payload

    resolver = CompanionResolver(InjectedGitHubSource(fetch_json))
    problems = resolver.resolve_debt(record)
    assert any("cannot verify the issue identity" in problem for problem in problems), problems
    # A fetcher returns the final response, including a followed redirect.
    assert requests == [API_DEBT_ISSUE]


@pytest.mark.parametrize("marker", [None, {}, {"url": "x"}, False, ""])
def test_encoding_debt_rejects_any_pull_request_key(marker) -> None:
    payload = dict(OPEN_ISSUE, pull_request=marker)
    problems = CompanionResolver(
        InjectedGitHubSource(lambda url: (200, payload))
    ).resolve_debt(_record())
    assert any("is a pull request" in problem for problem in problems), problems


@pytest.mark.parametrize("repo", ["rulespec-us", "rulespec-renamed-us"])
def test_encoding_debt_accepts_the_final_open_rulespec_identity(repo) -> None:
    # A rename within RuleSpec retains the invariant, unlike renaming outside it.
    payload = dict(OPEN_ISSUE, html_url=f"https://github.com/TheAxiomFoundation/{repo}/issues/123")
    resolver = CompanionResolver(InjectedGitHubSource(lambda url: (200, payload)))
    assert resolver.resolve_debt(_record()) == []


@settings(max_examples=100, deadline=None, derandomize=True)
@given(st.none() | st.booleans() | st.integers() | st.text(max_size=10) | st.lists(st.integers(), max_size=3) | st.dictionaries(st.text(max_size=10), st.none()))
def test_no_pull_request_marker_can_verify_encoding_debt(marker) -> None:
    payload = copy.deepcopy(OPEN_ISSUE)
    payload["pull_request"] = marker
    problems = CompanionResolver(
        InjectedGitHubSource(lambda url: (200, payload))
    ).resolve_debt(_record())
    assert any("is a pull request" in problem for problem in problems), problems


@settings(max_examples=100, deadline=None, derandomize=True)
@given(
    st.sampled_from(["OtherOwner", "TheAxiomFoundation"]),
    st.sampled_from(["rulespec-us", "axiom-oracles", "renamed-us"]),
    st.integers(min_value=1, max_value=200),
)
def test_encoding_debt_identity_scope_survives_redirects(owner, repo, number) -> None:
    payload = dict(OPEN_ISSUE, number=number, html_url=f"https://github.com/{owner}/{repo}/issues/{number}")
    problems = CompanionResolver(
        InjectedGitHubSource(lambda url: (200, payload))
    ).resolve_debt(_record())
    valid = owner == "TheAxiomFoundation" and repo == "rulespec-us" and number == 123
    assert (problems == []) == valid, problems


@pytest.mark.parametrize(
    "html_url",
    [
        pytest.param("https://github.com/TheAxiomFoundation/axiom-oracles/issues/8613", id="transferred-after-redirect"),
        pytest.param("https://github.com/PolicyEngine/renamed-us/issues/8613", id="repository-renamed"),
        pytest.param(None, id="missing-identity"),
    ],
)
def test_policyengine_citation_checks_the_final_issue_identity(html_url) -> None:
    payload = {"number": 8613, "state": "open", "html_url": html_url}
    resolver = CompanionResolver(InjectedGitHubSource(lambda url: (200, payload)))
    problems = resolver.resolve_pe_issue(_record())
    assert any("cannot verify the issue identity" in problem for problem in problems), problems
