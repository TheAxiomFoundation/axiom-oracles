"""Tamper resistance and native-outcome semantics; real replay runs separately."""

import copy
import json
from pathlib import Path
import subprocess

import pytest

from scripts import tariff_continuation_replay_bundle as bundle

REPO = Path(__file__).resolve().parents[1]


def native_error():
    receipt = json.loads((REPO / bundle.ROOT / "column2-resolution.json").read_text())
    return next(run for run in receipt["native_runs"] if run["returncode"] == 1)


def test_untrusted_manifest_stops_before_execution(tmp_path, monkeypatch):
    (tmp_path / "manifest.json").write_bytes(b"{}")
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: pytest.fail("executed untrusted binary")
    )
    with pytest.raises(ValueError, match="trust anchor"):
        bundle.verify(tmp_path, "0" * 64)


def test_changed_file_stops_before_execution(tmp_path, monkeypatch):
    manifest = {
        "schema": bundle.SCHEMA,
        "files": {
            "axiom-rules-engine": {"sha256": bundle.digest(b"original"), "bytes": 8}
        },
    }
    raw = bundle.render(manifest)
    (tmp_path / "manifest.json").write_bytes(raw)
    (tmp_path / "axiom-rules-engine").write_bytes(b"modified")
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: pytest.fail("executed changed binary")
    )
    with pytest.raises(ValueError, match="digest/size"):
        bundle.verify(tmp_path, bundle.digest(raw))


@pytest.mark.parametrize(
    "relative", ["../escape", "/absolute", "a/../escape", "a\\escape", "a//escape"]
)
def test_unsafe_member_paths_are_rejected(tmp_path, relative):
    with pytest.raises(ValueError, match="invalid bundle path"):
        bundle.bounded_file(tmp_path, relative)


def test_parent_symlink_is_rejected(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    (target / "body").write_text("body")
    (tmp_path / "alias").symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        bundle.bounded_file(tmp_path, "alias/body")


def test_native_missing_input_is_distinct_from_runtime_crash():
    run = native_error()
    expected = subprocess.CompletedProcess(
        [], 1, run["stdout"].encode(), run["stderr"].encode()
    )
    assert bundle.checked_response(run, expected) == (0, 1)
    crash = subprocess.CompletedProcess([], -9, b"", b"")
    with pytest.raises(ValueError, match="return code"):
        bundle.checked_response(run, crash)
    other = copy.deepcopy(run)
    other["stderr"] = "compiler crashed\n"
    with pytest.raises(ValueError, match="unexpected failure"):
        bundle.checked_response(
            other, subprocess.CompletedProcess([], 1, b"", other["stderr"].encode())
        )


def test_counterexample_must_reproduce_recorded_output():
    receipt = json.loads((REPO / bundle.ROOT / "china-lists.json").read_text())
    run = next(run for run in receipt["runs"] if "/ch22/" in run["module"]["path"])
    response = bundle.canonical(run["response"])
    count, errors = bundle.checked_response(
        run, subprocess.CompletedProcess([], 0, response, b"")
    )
    assert count == 3 and errors == 0
    changed = copy.deepcopy(run["response"])
    changed["results"] = []
    with pytest.raises(ValueError, match="response mismatch"):
        bundle.checked_response(
            run, subprocess.CompletedProcess([], 0, bundle.canonical(changed), b"")
        )
