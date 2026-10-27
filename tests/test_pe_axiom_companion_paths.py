"""Companion locators identify literal regular files, never URL/path aliases."""

from __future__ import annotations

import json
import os
import subprocess
from urllib.parse import unquote, urlsplit

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.comparison import pe_axiom_standard as standard
from scripts import pe_axiom_standard as cli

PIN = "dcb2e47e0af964be6d59f80688f519d0a6a96a71"
PATH = "us/policies/income_tax/salt_deduction_pipeline.test.yaml"
CONCEPT = "us:policies/income_tax/salt_deduction_pipeline#federal_salt_deduction"
CASE = "salt-low-agi-engine-cap"
YAML_CASE = yaml.safe_dump([{ "name": CASE, "output": {CONCEPT: 10000}}])


def _pointer(path: str, sha: str = PIN) -> str:
    return f"rulespec-us@{sha}:{path}#{CASE}"


def _record(path: str, sha: str = PIN) -> standard.Record:
    return standard.Record(
        source="disposition",
        id="salt-gap",
        suite="salt",
        concept=CONCEPT,
        basis="row",
        pe_issue=None,
        entry={"axiom_companion": {"legal_ids": [CONCEPT], "tests": [_pointer(path, sha)]}},
        case_ids=(CASE,),
        axiom_values={CASE: (10000,)},
        row_kinds=("amount_difference",),
    )


@pytest.mark.parametrize(
    "path",
    [
        PATH + "?alias/ignored.test.yaml",
        "archive/non-test.yaml?alias/ignored.test.yaml",
    ],
    ids=["absent-query-path", "query-disguised-non-test"],
)
def test_query_bearing_pointers_fail_syntax(path) -> None:
    assert standard.CompanionPointer.parse(_pointer(path)) is None
    assert standard.validate_axiom_side_fields(_record(path).entry, "query")


@pytest.mark.parametrize(
    "path", [PATH + "?alias/ignored.test.yaml", "us/archive/non-test.yaml?alias/ignored.test.yaml"]
)
def test_query_bearing_disposition_fails_both_gates(tmp_path, monkeypatch, path) -> None:
    entry = {
        "id": "salt-gap",
        "concept": CONCEPT,
        "kind": "amount_difference",
        "disposition": "upstream_engine_gap",
        "linked_issue": "https://github.com/PolicyEngine/policyengine-us/issues/9999",
        **_record(path).entry,
    }
    dispositions = tmp_path / "dispositions"
    dispositions.mkdir()
    (dispositions / "salt.yaml").write_text(yaml.safe_dump({"suite": "salt", "entries": [entry]}))
    # Report fallback attributes the disposition, even with no sampled rows.
    data = tmp_path / "dashboard" / "public" / "data"
    data.mkdir(parents=True)
    (data / "salt.json").write_text(json.dumps({
        "suite": "salt", "engines": {"left": "axiom", "right": "policyengine-us"},
        "mismatches": [],
    }))
    records, errors = standard.collect_records(tmp_path)
    assert len(records) == 1
    ratchet = tmp_path / standard.RATCHET_RELATIVE_PATH
    ratchet.parent.mkdir()
    ratchet.write_text(standard.serialize_ratchet(standard.derive_ratchet(records, None)))
    source = _HTTPSource(files={path.split("?", 1)[0]: YAML_CASE})
    monkeypatch.setattr(cli, "GitHubSource", lambda **kwargs: source)
    check = cli.main(["--check"], repo_root=tmp_path)
    resolve = cli.main(["--resolve"], repo_root=tmp_path)
    assert (bool(errors), check, resolve) == (True, 1, 1)
    assert standard.CompanionResolver(source).resolve(_record(path))


@pytest.mark.parametrize(
    "path",
    [
        "/" + PATH,
        "us/../" + PATH,
        "us/./policies/salt.test.yaml",
        "us//policies/salt.test.yaml",
        "us\\policies\\salt.test.yaml",
        "C:/us/policies/salt.test.yaml",
        "us/%2e%2e/policies/salt.test.yaml",
        "us/policies/salt%2ftest.test.yaml",
        "us/policies/salt%23case.test.yaml",
        PATH + "/",
        PATH.upper(),
        "us/policies/salt.yaml#alias.test.yaml",
        "us/policies/salt.test.yаml",  # Cyrillic a is not the test extension.
        "us/policies/salt.test.yaml\x00alias.test.yaml",
        "us/policies/salt.test.yaml\x1falias.test.yaml",
    ],
)
def test_nonliteral_or_nontest_paths_fail_syntax(path) -> None:
    assert standard.CompanionPointer.parse(_pointer(path)) is None


class _HTTPSource(standard.GitHubSource):
    """Model HTTP URL interpretation, including one percent decode."""

    def __init__(self, files=None, tree=None):
        super().__init__(backoff=0)
        self.files = files or {PATH: YAML_CASE}
        self.tree = tree or [{"path": PATH, "type": "blob", "mode": "100644"}]
        self.urls = []

    def _get(self, url, *, api=False):
        self.urls.append(url)
        if api:
            return 200, json.dumps({"tree": self.tree, "truncated": False}).encode()
        path = unquote(urlsplit(url).path).split("/", 4)[-1]
        body = self.files.get(path)
        return (404, b"") if body is None else (200, body.encode())

    def is_merged(self, repo, sha):
        return True

    def main_sha(self, repo):
        return PIN

    def fetch_json(self, url):
        if "/issues/9999" in url:
            return 200, {
                "number": 9999,
                "html_url": "https://github.com/PolicyEngine/policyengine-us/issues/9999",
            }
        return self._json(url)


@pytest.mark.parametrize(
    "path, served",
    [
        (PATH + "?alias/ignored.test.yaml", PATH),
        ("archive/non-test.yaml?alias/ignored.test.yaml", "archive/non-test.yaml"),
        (PATH + "#ignored", PATH),
        ("us/policies/salt%2falias.test.yaml", "us/policies/salt/alias.test.yaml"),
    ],
)
def test_raw_fetch_does_not_serve_another_path(path, served) -> None:
    source = _HTTPSource(files={served: YAML_CASE})
    assert source.read("rulespec-us", PIN, path) is None


@pytest.mark.parametrize("path", [PATH, "us/policies/ＳＡＬＴ.test.yaml", "us/policies/literal%2f.test.yaml"])
def test_raw_fetch_preserves_literal_unicode_and_percent(path) -> None:
    source = _HTTPSource(files={path: YAML_CASE})
    assert source.read("rulespec-us", PIN, path) == YAML_CASE
    assert source.urls[0].isascii()
    url = urlsplit(source.urls[0])
    assert not url.query and not url.fragment
    assert unquote(url.path).split("/", 4)[-1] == path


@pytest.mark.parametrize("mode, kind", [("120000", "blob"), ("160000", "commit"), ("040000", "tree")])
def test_remote_companion_must_be_a_regular_git_blob(mode, kind) -> None:
    # A symlink target string can itself be valid case-shaped YAML.
    source = _HTTPSource(tree=[{"path": PATH, "type": kind, "mode": mode}])
    assert standard.CompanionResolver(source).resolve(_record(PATH))


@pytest.mark.parametrize("mode", ["100644", "100755"])
def test_remote_regular_companions_remain_valid(mode) -> None:
    source = _HTTPSource(tree=[{"path": PATH, "type": "blob", "mode": mode}])
    assert standard.CompanionResolver(source).resolve(_record(PATH)) == []


def test_main_cannot_replace_a_regular_companion_with_a_symlink(monkeypatch) -> None:
    main = "e" * 40
    source = _HTTPSource()
    monkeypatch.setattr(source, "main_sha", lambda repo: main)
    monkeypatch.setattr(source, "_json", lambda url: (200, {
        "truncated": False,
        "tree": [{"path": PATH, "type": "blob", "mode": "120000" if main in url else "100644"}],
    }))
    assert standard.CompanionResolver(source).resolve(_record(PATH))


@pytest.mark.parametrize("suffix", ["#fragment", "?query", "%20", "/"])
def test_case_fragment_is_matched_literally(suffix) -> None:
    record = _record(PATH)
    record.entry["axiom_companion"]["tests"] = [_pointer(PATH) + suffix]
    assert standard.CompanionResolver(_HTTPSource()).resolve(record)


@pytest.mark.parametrize(
    "payload",
    [
        {"tree": [{"path": PATH, "type": "blob", "mode": "100644"}], "truncated": True},
        {"tree": [{"path": PATH, "type": "blob", "mode": "100644"}]},
        {"tree": {}, "truncated": False},
        {"tree": [None, {}], "truncated": False},
        {"tree": [], "truncated": False},
        {"tree": [{"path": PATH, "type": "blob", "mode": "100644"}] * 2, "truncated": False},
    ],
    ids=["truncated", "truncation-unknown", "malformed-tree", "missing-fields", "absent-path", "ambiguous-path"],
)
def test_remote_tree_cannot_omit_file_identity(monkeypatch, payload) -> None:
    source = _HTTPSource()
    monkeypatch.setattr(source, "_json", lambda url: (200, payload))
    assert standard.CompanionResolver(source).resolve(_record(PATH))


@pytest.mark.parametrize("tree_path", [PATH.upper(), PATH.replace("us/", "US/"), "us/policies/ѕalt.test.yaml"])
def test_remote_tree_requires_exact_path_case_and_unicode(tree_path) -> None:
    source = _HTTPSource(tree=[{"path": tree_path, "type": "blob", "mode": "100644"}])
    assert standard.CompanionResolver(source).resolve(_record(PATH))


def test_unicode_normalization_does_not_alias_a_tree_path() -> None:
    declared = "us/policies/caf\u00e9.test.yaml"
    actual = "us/policies/cafe\u0301.test.yaml"
    source = _HTTPSource(files={declared: YAML_CASE}, tree=[{"path": actual, "type": "blob", "mode": "100644"}])
    assert standard.CompanionResolver(source).resolve(_record(declared))


def _git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def test_local_case_shaped_symlink_is_not_a_companion(tmp_path) -> None:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.name", "Companion fixture")
    _git(tmp_path, "config", "user.email", "companion@example.invalid")
    target = tmp_path / PATH
    target.parent.mkdir(parents=True)
    os.symlink(YAML_CASE, target)
    _git(tmp_path, "add", "--", PATH)
    _git(tmp_path, "commit", "--quiet", "-m", "case-shaped symlink")
    sha = _git(tmp_path, "rev-parse", "HEAD")
    source = standard.LocalGitSource({"rulespec-us": tmp_path}, main_ref="HEAD")
    # The old content-only check accepts the symlink's YAML target as a case.
    assert source.read("rulespec-us", sha, PATH) == YAML_CASE
    assert standard.CompanionResolver(source).resolve(_record(PATH, sha))


@settings(max_examples=100, deadline=None, derandomize=True)
@given(
    prefix=st.from_regex(r"[a-z][a-z0-9_-]{0,15}", fullmatch=True),
    alias=st.from_regex(r"[a-z][a-z0-9_-]{0,15}", fullmatch=True),
    escape=st.sampled_from(["?", "%2f", "%2e%2e", "\\", "/./", "//", "\x00"]),
)
def test_pointer_paths_never_accept_normalizing_syntax(prefix, alias, escape) -> None:
    path = f"us/{prefix}{escape}{alias}.test.yaml"
    assert standard.CompanionPointer.parse(_pointer(path)) is None


@settings(max_examples=100, deadline=None, derandomize=True)
@given(name=st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs", "Cc", "Zs", "Zl", "Zp"),
        blacklist_characters="/\\:?#%",
    ),
    min_size=1, max_size=20,
))
def test_literal_unicode_paths_survive_transport_without_aliases(name) -> None:
    path = f"us/policies/{name}.test.yaml"
    pointer = standard.CompanionPointer.parse(_pointer(path))
    assert pointer is not None and pointer.path == path
    source = _HTTPSource(files={path: YAML_CASE}, tree=[{"path": path, "type": "blob", "mode": "100644"}])
    assert standard.CompanionResolver(source).resolve(_record(path)) == []
    raw_url = next(url for url in source.urls if "raw.githubusercontent.com" in url)
    assert raw_url.isascii()
    assert unquote(urlsplit(raw_url).path).split("/", 4)[-1] == path
