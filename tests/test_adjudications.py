"""Adversarial evidence tests: source fidelity is independent of readiness."""

from __future__ import annotations

import copy
import difflib
import hashlib
import json
import subprocess
from pathlib import Path

import pytest
import yaml
from hypothesis import HealthCheck, given, settings, strategies as st

from axiom_oracles.comparison.adjudications import (
    MAINTAINERS_SCHEMA,
    SCHEMA,
    AdjudicationError,
    load_adjudications,
    validate_adjudications,
)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.check_output([
        "git", "-c", "core.fsmonitor=false", "-c", "commit.gpgsign=false",
        "-c", "core.hooksPath=/dev/null", "-C", str(root), *args,
    ]).decode().strip()


@pytest.fixture
def sources(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "adjudications/snapshots").mkdir(parents=True)
    config = {
        "schema": MAINTAINERS_SCHEMA,
        "engines": {
            "taxsim": {"maintainers": ["feenberg"]},
            "policyengine": {"maintainers": ["pe-maintainer"]},
        },
    }
    (root / "adjudications/maintainers.yaml").write_text(yaml.safe_dump(config))
    comment = {
        "url": "https://github.com/PolicyEngine/pe-taxsim/issues/1#issuecomment-2",
        "author": "feenberg", "createdAt": "2025-01-02T03:04:05Z",
        "body": "This is a TAXSIM error. I have fixed it.\nWe treat this input as wages.",
    }
    snapshot = "adjudications/snapshots/comment.json"
    raw = (json.dumps(comment, indent=2) + "\n").encode()
    (root / snapshot).write_bytes(raw)
    statement = {
        "kind": "maintainer_statement", "engine": "taxsim", "url": comment["url"],
        "author": "feenberg", "date": "2025-01-02",
        "quote": "This is a TAXSIM error. I have fixed it.",
        "snapshot": snapshot, "snapshot_sha256": digest(raw),
        "acknowledges_error": True,
    }
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    git(corpus, "init", "-b", "main")
    git(corpus, "config", "user.email", "test@example.com")
    git(corpus, "config", "user.name", "Evidence Test")
    path = "provisions/law.jsonl"
    (corpus / "provisions").mkdir()
    provision = {
        "citation_path": "us/statute/26/123", "kind": "section",
        "heading": "Taxable wages", "body": "Wages are taxable.\nInterest is exempt.\n",
        "metadata": {"law_years": [2024]},
    }
    future = {
        **provision, "citation_path": "us/statute/26/123/2025",
        "body": "Wages are taxable.\nInterest is taxable.\n",
        "metadata": {"law_years": [2025]},
    }
    current = {
        **provision, "citation_path": "us/statute/26/123/current",
        "metadata": {"source_as_of": "2026-07-13", "version": "2026-07-13"},
    }
    blob = "".join(json.dumps(row) + "\n" for row in (provision, future, current)).encode()
    (corpus / path).write_bytes(blob)
    git(corpus, "add", path)
    git(corpus, "commit", "-qm", "Fixture provisions")
    commit = git(corpus, "rev-parse", "HEAD")
    git(corpus, "update-ref", "refs/remotes/origin/main", commit)
    quote = {
        "kind": "corpus_quote",
        "corpus": {
            "repository": "TheAxiomFoundation/axiom-corpus", "commit": commit,
            "path": path, "sha256": digest(blob),
        },
        "citation_path": provision["citation_path"], "heading": provision["heading"],
        "excerpt": "Wages are taxable.", "applies_to": "Taxpayers with wages",
        "law_years": [2024],
    }
    record = {
        "id": "taxable-wages", "question": "Are wages taxable?", "jurisdiction": "US",
        "law_years": [2024], "engines": ["taxsim", "policyengine"],
        "verdict": "taxsim_wrong", "attribution": "taxsim", "status": "evidence_ready",
        "issues": ["https://github.com/PolicyEngine/pe-taxsim/issues/1"],
        "proof_atoms": [statement], "notes": "Reviewed explicit admission.",
    }
    return root, corpus, record, statement, quote, provision, future


def errors(sources, record):
    root, corpus, *_ = sources
    return validate_adjudications(
        {"schema": SCHEMA, "adjudications": [record]}, repo_root=root, corpus_root=corpus,
    )


def test_verified_maintainer_and_legal_evidence(sources):
    _, _, record, _, quote, *_ = sources
    assert not errors(sources, record)
    record["proof_atoms"] = [quote]
    assert not errors(sources, record)


@pytest.mark.parametrize("status", ["evidence_ready", "pending_evidence", "open"])
def test_all_statuses_reverify_snapshot_bytes(sources, status):
    root, _, record, statement, *_ = sources
    record["status"] = status
    if status == "open":
        record["verdict"] = "open"
    path = root / statement["snapshot"]
    path.write_bytes(path.read_bytes() + b" ")
    assert any("snapshot sha256 mismatch" in error for error in errors(sources, record))


@pytest.mark.parametrize("field,value,message", [
    ("quote", "This is an invented quote.", "verbatim"),
    ("author", "pe-maintainer", "configured maintainer"),
    ("date", "2025-02-02", "createdAt"),
    ("url", "https://github.com/PolicyEngine/pe-taxsim/issues/9#issuecomment-2", "snapshot url"),
    ("engine", "policyengine", "configured maintainer"),
    ("quote", "word " * 61, "1 to 60 words"),
])
def test_statement_identity_and_quote_fail_closed(sources, field, value, message):
    record = sources[2]
    record["proof_atoms"][0][field] = value
    assert any(message in error for error in errors(sources, record))


def test_rehashed_snapshot_author_cannot_impersonate_maintainer(sources):
    root, _, record, statement, *_ = sources
    path = root / statement["snapshot"]
    snapshot = json.loads(path.read_text())
    snapshot["author"] = "someone-else"
    raw = json.dumps(snapshot).encode()
    path.write_bytes(raw)
    statement["snapshot_sha256"] = digest(raw)
    assert any("snapshot author" in error for error in errors(sources, record))


def test_other_engine_admission_cannot_establish_error(sources):
    record = sources[2]
    record.update(verdict="policyengine_wrong", attribution="policyengine")
    assert any("policyengine maintainer acknowledgement" in error for error in errors(sources, record))
    record["status"] = "pending_evidence"
    assert not errors(sources, record)


def test_authentic_comment_cannot_be_borrowed_from_an_unrelated_issue(sources):
    record = sources[2]
    record["issues"] = ["https://github.com/PolicyEngine/pe-taxsim/issues/999"]
    assert any("must be listed in record issues" in error for error in errors(sources, record))


@pytest.mark.parametrize("reference", [
    "https://github.com/PolicyEngine/pe-taxsim/pull/1",
    "https://github.com/policyengine/PE-TAXSIM/issues/1/",
])
def test_github_issue_and_pull_request_aliases_share_source_identity(sources, reference):
    record = sources[2]
    record["issues"] = [reference]
    assert not errors(sources, record)


def test_discussion_is_not_an_acknowledgement(sources):
    record = sources[2]
    del record["proof_atoms"][0]["acknowledges_error"]
    assert any("maintainer acknowledgement" in error for error in errors(sources, record))


@pytest.mark.parametrize("field", ["excerpt", "heading", "sha256", "commit"])
@given(suffix=st.text(alphabet="abcdef0123456789", min_size=1, max_size=12))
@settings(max_examples=12, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_arbitrary_quote_and_corpus_pin_tampering_fails(sources, field, suffix):
    record, quote = copy.deepcopy(sources[2]), copy.deepcopy(sources[4])
    target = quote["corpus"] if field in ("sha256", "commit") else quote
    if field in ("sha256", "commit"):
        offset = int(suffix, 16) % len(target[field])
        original = target[field]
        replacement = "a" if original[offset] != "a" else "b"
        target[field] = original[:offset] + replacement + original[offset + 1:]
    else:
        target[field] += suffix
    record["proof_atoms"] = [quote]
    assert errors(sources, record)


@given(offset=st.integers(min_value=0, max_value=10000))
@settings(max_examples=12, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_any_changed_snapshot_byte_fails(sources, offset):
    root, _, record, statement, *_ = sources
    path = root / statement["snapshot"]
    raw = path.read_bytes()
    modified = bytearray(raw)
    modified[offset % len(modified)] ^= 1
    try:
        path.write_bytes(modified)
        assert any("snapshot sha256 mismatch" in error for error in errors(sources, record))
    finally:
        path.write_bytes(raw)


def test_corpus_digest_and_working_tree_independence(sources):
    _, corpus, record, _, quote, *_ = sources
    record["proof_atoms"] = [quote]
    (corpus / quote["corpus"]["path"]).write_text("tampered uncommitted tree")
    assert not errors(sources, record)  # git show reads immutable pinned bytes.
    quote["corpus"]["sha256"] = "0" * 64
    assert any("blob sha256 mismatch" in error for error in errors(sources, record))


def test_non_mainline_pin_rejected(sources):
    _, corpus, record, _, quote, *_ = sources
    git(corpus, "checkout", "-qb", "unmerged")
    (corpus / "unmerged").write_text("unmerged change")
    git(corpus, "add", "unmerged")
    git(corpus, "commit", "-qm", "Not on main")
    quote["corpus"]["commit"] = git(corpus, "rev-parse", "HEAD")
    record["proof_atoms"] = [quote]
    assert any("merge-base" in error for error in errors(sources, record))


def test_current_law_cannot_establish_historical_year(sources):
    record, quote = sources[2], sources[4]
    quote["citation_path"] += "/current"
    record["proof_atoms"] = [quote]
    assert any("applicable to all law_years" in error for error in errors(sources, record))
    record["status"] = "pending_evidence"
    assert not errors(sources, record)


def test_current_law_also_blocks_convention_readiness(sources):
    record, quote = sources[2], sources[4]
    record["proof_atoms"][0]["establishes_convention"] = True
    quote["citation_path"] += "/current"
    record["proof_atoms"].append(quote)
    record.update(verdict="convention", attribution="convention")
    assert any("independently established" in error for error in errors(sources, record))


def test_absence_requires_full_body_hash_and_actual_absence(sources):
    record, quote, provision = sources[2], sources[4], sources[5]
    atom = {
        "kind": "corpus_absence", "corpus": quote["corpus"],
        "citation_path": quote["citation_path"], "absent_terms": ["dividends"],
        "body_sha256": digest(provision["body"].encode()),
    }
    record["proof_atoms"] = [atom]
    assert not errors(sources, record)
    del atom["body_sha256"]
    assert any("body_sha256" in error for error in errors(sources, record))
    atom["body_sha256"] = digest(provision["body"].encode())
    atom["absent_terms"] = ["INTEREST"]
    assert any("occurs in full provision body" in error for error in errors(sources, record))


def test_year_change_recomputes_both_full_documents(sources):
    record, quote, before, after = sources[2], sources[4], sources[5], sources[6]
    after_quote = {**quote, "citation_path": after["citation_path"], "law_years": [2025]}
    diff = "".join(difflib.unified_diff(
        before["body"].splitlines(keepends=True), after["body"].splitlines(keepends=True),
        fromfile="before", tofile="after",
    ))
    atom = {"kind": "year_change", "before": quote, "after": after_quote, "changed_text": diff}
    record["proof_atoms"] = [atom]
    record["law_years"] = [2024, 2025]
    assert not errors(sources, record)
    atom["changed_text"] += "invented change"
    assert any("computed full provision diff" in error for error in errors(sources, record))
    atom["changed_text"] = diff
    after_quote["law_years"] = [2024]
    assert any("nonoverlapping law years" in error for error in errors(sources, record))


def test_convention_needs_affirmative_support(sources):
    record = sources[2]
    record.update(verdict="convention", attribution="convention")
    assert any("establishing the convention" in error for error in errors(sources, record))
    record["proof_atoms"][0]["establishes_convention"] = True
    assert not errors(sources, record)


def test_official_document_snapshot(sources):
    root, _, record, *_ = sources
    raw = b"TAXSIM includes an additional tax in federal liability.\n"
    path = "adjudications/snapshots/document.txt"
    (root / path).write_bytes(raw)
    atom = {
        "kind": "document_quote", "url": "https://taxsim.nber.org/taxsim35/",
        "retrieved_on": "2026-09-27", "snapshot": path, "snapshot_sha256": digest(raw),
        "excerpt": raw.decode().strip(), "establishes_convention": True,
    }
    record.update(verdict="convention", attribution="convention", proof_atoms=[atom])
    assert not errors(sources, record)
    atom["url"] = "https://unofficial.example.org/taxsim/"
    assert any("official document host" in error for error in errors(sources, record))


@pytest.mark.parametrize("kind", ["engine_output", "calculation", "simulation", "hypothesis"])
def test_engine_outputs_have_no_atom_kind(sources, kind):
    record = sources[2]
    record["proof_atoms"] = [{"kind": kind}]
    assert any("unsupported proof-atom kind" in error for error in errors(sources, record))


def test_non_open_verdict_needs_atom_even_when_pending(sources):
    record = sources[2]
    record.update(proof_atoms=[], status="pending_evidence")
    assert any("requires at least one proof atom" in error for error in errors(sources, record))
    record.update(verdict="open", law_years=[])
    assert not errors(sources, record)


def test_both_wrong_needs_evidence_for_both_engines(sources):
    record = sources[2]
    record.update(verdict="both_wrong", attribution="two_sided")
    assert any("policyengine maintainer acknowledgement" in error for error in errors(sources, record))


def test_snapshot_cannot_escape_repository(sources):
    record = sources[2]
    record["proof_atoms"][0]["snapshot"] = "../outside.json"
    assert any("repository-relative" in error for error in errors(sources, record))


def test_load_checks_and_reports_errors(sources):
    root, corpus, record, *_ = sources
    path = root / "adjudications/example.yaml"
    document = {"schema": SCHEMA, "adjudications": [record]}
    path.write_text(yaml.safe_dump(document))
    assert load_adjudications(path, repo_root=root, corpus_root=corpus) == document
    record["proof_atoms"][0]["quote"] = "Invented."
    path.write_text(yaml.safe_dump(document))
    with pytest.raises(AdjudicationError, match="verbatim"):
        load_adjudications(path, repo_root=root, corpus_root=corpus)
