"""Admission properties for new reports and byte-bound historical exceptions."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest
from hypothesis import given, strategies as st

from axiom_oracles.engine_publication import (
    BINARY_SHA256,
    ENGINE_COMMIT,
    LEGACY_ALLOWLIST,
    LEGACY_SCHEMA,
    check_publications,
    engine_identity_errors,
    is_axiom_report,
    legacy_history_errors,
    load_legacy_allowlist,
    publication_errors,
    validate_engine_identity,
)
from axiom_oracles.provenance import _git_env

REPORT_PATH = "dashboard/public/data/axiom-policyengine-test.json"


def _report() -> dict:
    return {
        "engines": {"left": "axiom", "right": "policyengine"},
        "provenance": {"engine": {"commit": "a" * 40, "binary_sha256": "b" * 64}},
    }


@pytest.mark.parametrize("value", ["0", "A", "f"])
def test_full_hex_engine_identity_is_accepted(value):
    report = _report()
    report["provenance"]["engine"] = {"commit": value * 40, "binary_sha256": value * 64}
    validate_engine_identity(report)


@pytest.mark.parametrize("field", ["commit", "binary_sha256"])
@pytest.mark.parametrize("value", [None, "", "ab", "z" * 64, False, 42, {}, []])
def test_missing_short_or_nonhex_engine_identity_is_rejected(field, value):
    report = _report()
    report["provenance"]["engine"][field] = value
    with pytest.raises(ValueError, match=field):
        validate_engine_identity(report)


@given(
    field=st.sampled_from(["commit", "binary_sha256"]),
    value=st.one_of(st.none(), st.integers(), st.booleans(), st.text()),
)
def test_every_malformed_commit_or_binary_hash_is_rejected(field, value):
    pattern = ENGINE_COMMIT if field == "commit" else BINARY_SHA256
    if isinstance(value, str) and pattern.fullmatch(value):
        return
    report = _report()
    report["provenance"]["engine"][field] = value
    with pytest.raises(ValueError, match=field):
        validate_engine_identity(report)


@pytest.mark.parametrize("provenance", [None, [], "", {}, {"engine": []}, {"engine": None}])
def test_missing_engine_block_is_rejected(provenance):
    report = _report()
    report["provenance"] = provenance
    assert len(engine_identity_errors(report)) == 2


@pytest.mark.parametrize(
    "engines", [{"left": "axiom"}, {"right": "axiom"}, {"axiom": "module#rule"}, ["axiom"]]
)
def test_runner_and_campaign_reports_are_axiom_bearing(engines):
    assert is_axiom_report({"engines": engines})
    assert not is_axiom_report({"engines": {"left": "euromod", "right": "gettsim"}})


def test_engine_cannot_be_hidden_by_removing_engine_labels():
    assert is_axiom_report({"cases": [{"axiom": False}]})
    assert publication_errors({}, path=REPORT_PATH, content=b"{}", legacy={})


@pytest.mark.parametrize("report", [
    {"engine_identity": {"axiom": {}}},
    {"runtime_provenance": {"axiom_engine": {}}},
    {"provenance": {"runtime_provenance": {"axiom_engine": {}}}},
    {"provenance": {"engine": {"repository": "TheAxiomFoundation/axiom-rules-engine"}}},
])
def test_receipt_and_campaign_identity_cannot_bypass_report_admission(report):
    assert is_axiom_report(report)
    assert publication_errors(report, path="dashboard/public/data/campaign.json",
                              content=json.dumps(report).encode(), legacy={})


@given(content=st.binary())
def test_historical_exception_only_applies_to_identical_bytes_and_path(content):
    report = {"engines": {"left": "axiom"}, "provenance": {"engine": {}}}
    legacy = {REPORT_PATH: hashlib.sha256(content).hexdigest()}
    assert not publication_errors(report, path=REPORT_PATH, content=content, legacy=legacy)
    assert publication_errors(report, path=REPORT_PATH, content=content + b" ", legacy=legacy)
    assert publication_errors(report, path=REPORT_PATH + ".copy", content=content, legacy=legacy)


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@test", *args],
        cwd=root,
        capture_output=True,
        check=True,
        env=_git_env(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull),
    )


def _write_allowlist(root: Path, reports: dict[str, str]) -> None:
    path = root / LEGACY_ALLOWLIST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": LEGACY_SCHEMA, "reports": reports}))


def _legacy_repo(root: Path) -> dict[str, str]:
    _git(root, "init", "-q")
    path = root / REPORT_PATH
    path.parent.mkdir(parents=True)
    content = json.dumps({"engines": {"left": "axiom"}}).encode()
    path.write_bytes(content)
    legacy = {REPORT_PATH: hashlib.sha256(content).hexdigest()}
    _write_allowlist(root, legacy)
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "legacy baseline")
    return legacy


def test_gate_accepts_original_legacy_and_rejects_edited_and_untracked_reports(tmp_path):
    _legacy_repo(tmp_path)
    result = check_publications(tmp_path)
    assert result == {
        "axiom_reports": 1, "legacy_reports": 1, "unresolved_reports": 1, "errors": []
    }
    assert check_publications(tmp_path, allow_legacy=False)["errors"]
    report = tmp_path / REPORT_PATH
    report.write_bytes(report.read_bytes() + b"\n")
    new = report.with_name("axiom-policyengine-new.json")
    new.write_text(json.dumps({"engines": {"left": "axiom"}}))
    result = check_publications(tmp_path)
    assert result["axiom_reports"] == result["unresolved_reports"] == 2
    assert result["legacy_reports"] == 0
    assert len(result["errors"]) == 4


def test_legacy_allowlist_cannot_grow_or_change_digest(tmp_path):
    legacy = _legacy_repo(tmp_path)
    assert not legacy_history_errors(tmp_path, legacy)
    assert legacy_history_errors(tmp_path, {**legacy, REPORT_PATH + ".json": "a" * 64})
    assert legacy_history_errors(tmp_path, {REPORT_PATH: "a" * 64})
    assert not legacy_history_errors(tmp_path, {})


def test_removed_legacy_exception_cannot_return_after_revert(tmp_path):
    legacy = _legacy_repo(tmp_path)
    _write_allowlist(tmp_path, {})
    _git(tmp_path, "add", LEGACY_ALLOWLIST)
    _git(tmp_path, "commit", "-q", "-m", "remove old exception")
    assert legacy_history_errors(tmp_path, legacy)


def test_a_shallow_clone_cannot_run_the_allowlist_ratchet(tmp_path):
    """A shallow clone lacks the commit that removed an exception, so a
    restored entry would look like the baseline."""
    origin = tmp_path / "origin"
    origin.mkdir()
    legacy = _legacy_repo(origin)
    _write_allowlist(origin, {})
    _git(origin, "add", LEGACY_ALLOWLIST)
    _git(origin, "commit", "-q", "-m", "remove old exception")
    _write_allowlist(origin, legacy)
    _git(origin, "add", LEGACY_ALLOWLIST)
    _git(origin, "commit", "-q", "-m", "restore it")
    shallow = tmp_path / "shallow"
    _git(tmp_path, "clone", "-q", "--depth", "1", f"file://{origin}", str(shallow))
    assert legacy_history_errors(shallow, legacy) == [
        "legacy engine identity allow-list history needs a full clone; "
        "this checkout is shallow"
    ]
    assert legacy_history_errors(origin, legacy)


@pytest.mark.parametrize("reports", [[], {"../outside.json": "a" * 64}, {REPORT_PATH: "abc"}])
def test_legacy_allowlist_rejects_invalid_entries(reports):
    with pytest.raises(ValueError):
        load_legacy_allowlist({"schema": LEGACY_SCHEMA, "reports": reports})


def test_migration_allowlist_covers_only_unchanged_reports():
    root = Path(__file__).resolve().parents[1]
    legacy = load_legacy_allowlist(json.loads((root / LEGACY_ALLOWLIST).read_text()))
    assert len(legacy) <= 266
    for path, digest in legacy.items():
        content = (root / path).read_bytes()
        assert hashlib.sha256(content).hexdigest() == digest
        assert is_axiom_report(json.loads(content))
        assert engine_identity_errors(json.loads(content))
