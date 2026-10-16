"""Incoming Git attributes must never change a bound snapshot's raw bytes."""

from __future__ import annotations

import json
import shlex
import sys

import pytest
from test_oracle_data import data, git
from test_oracle_data_snapshot_properties import (
    BOT_REPORT,
    SNAPSHOT,
    _assert_bound,
    _data_files,
    _overview,
    _tree_files,
    snapshot_case as snapshot_case,
)

ATTRIBUTES = "dashboard/public/data/.gitattributes"
SIDECAR = "dashboard/public/data/sidecar.json"
CONTENT = b'{"revision": 1, "sidecar": "published LF bytes"}\n'


def _raw_state(root) -> tuple:
    # Git status can itself run a configured encoding or clean filter. Capture
    # exact bytes and index/HEAD independently of those checkout conversions.
    return (
        git(root, "rev-parse", "HEAD"),
        git(root, "write-tree"),
        _data_files(root),
        data._state_path(root).read_bytes(),
    )


def _publish_raw_sidecar(case, attribute: str | None = None) -> None:
    """Build a tiny bound tree without letting fixture attributes clean its blobs.

    The incoming attributes are themselves generated-scope files. In particular,
    working-tree-encoding must not turn fixture creation into the conversion we
    are trying to detect in the reader. The overview is unchanged because this
    auxiliary sidecar is deliberately outside its primary-report manifest.
    """

    def stage(name: str, payload: bytes) -> None:
        oid = (
            data._git(case.seed, "hash-object", "-w", "--stdin", input=payload)
            .stdout.decode()
            .strip()
        )
        git(case.seed, "update-index", "--add", "--cacheinfo", "100644", oid, name)

    stage(SIDECAR, CONTENT)
    if attribute is not None:
        stage(ATTRIBUTES, f"sidecar.json {attribute}\n".encode())
    tree = git(case.seed, "write-tree")
    snapshot = {"schema": data.SNAPSHOT_SCHEMA, "files": _tree_files(case.seed, tree)}
    stage(SNAPSHOT, (json.dumps(snapshot, sort_keys=True) + "\n").encode())
    tree = git(case.seed, "write-tree")
    published = git(
        case.seed,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.com",
        "commit-tree",
        tree,
        "-p",
        case.main,
        "-m",
        "publish exact sidecar and incoming attributes",
    )
    git(case.seed, "push", "origin", f"{published}:{data.DATA_REF}")
    assert (
        data._git(case.seed, "cat-file", "blob", f"{published}:{SIDECAR}").stdout
        == CONTENT
    )


@pytest.mark.parametrize(
    "baseline", [False, True], ids=["consumer", "producer-baseline"]
)
@pytest.mark.parametrize(
    "attribute",
    ["text eol=crlf", "filter=change-number", "working-tree-encoding=UTF-16LE"],
    ids=["incoming-crlf", "incoming-filter", "incoming-encoding"],
)
def test_incoming_attributes_preserve_exact_bound_bytes_and_identical_reads(
    snapshot_case, baseline, attribute
):
    case = snapshot_case
    _publish_raw_sidecar(case, attribute)
    reader = case.baseline_reader if baseline else case.reader
    # If Git restores this file normally, this configured incoming filter
    # changes a valid report value while still producing valid JSON.
    code = (
        "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read().replace("
        "b'\"revision\": 1', b'\"revision\": 999'))"
    )
    command = shlex.quote(sys.executable) + " -c " + shlex.quote(code)
    git(reader, "config", "filter.change-number.smudge", command)
    git(reader, "config", "filter.change-number.clean", "cat")

    data.materialize(reader, baseline=baseline)

    assert (reader / SIDECAR).read_bytes() == CONTENT
    _assert_bound(reader)
    after_first = _raw_state(reader)
    data.materialize(reader, baseline=baseline)
    assert _raw_state(reader) == after_first
    _assert_bound(reader)


@pytest.mark.parametrize(
    "baseline", [False, True], ids=["consumer", "producer-baseline"]
)
@pytest.mark.parametrize("setting", ["local-attributes-crlf", "core-autocrlf"])
def test_local_checkout_transformations_preserve_exact_bound_bytes(
    snapshot_case, baseline, setting
):
    case = snapshot_case
    _publish_raw_sidecar(case)
    reader = case.baseline_reader if baseline else case.reader
    if setting == "local-attributes-crlf":
        (reader / ".git/info/attributes").write_text(f"{SIDECAR} text eol=crlf\n")
    else:
        git(reader, "config", "core.autocrlf", "true")

    # Set transformations after the clean checkout exists. They must not cause
    # a false refusal or change the incoming sidecar's raw bound bytes.
    data.materialize(reader, baseline=baseline)
    assert (reader / SIDECAR).read_bytes() == CONTENT
    _assert_bound(reader)
    data.materialize(reader, baseline=baseline)
    _assert_bound(reader)


def test_materialize_verifies_written_bytes_before_recording_success(
    snapshot_case, monkeypatch
):
    case = snapshot_case
    _publish_raw_sidecar(case)
    real_identities = data._worktree_identities
    calls = 0

    def corrupt_before_postwrite_verification(root, paths):
        nonlocal calls
        calls += 1
        if calls == 2:
            # Model an I/O layer that writes bytes different from the blob.
            # The second hash pass must detect it before success is recorded.
            (root / SIDECAR).write_bytes(b'{"revision": 999}\n')
        return real_identities(root, paths)

    monkeypatch.setattr(
        data, "_worktree_identities", corrupt_before_postwrite_verification
    )
    with pytest.raises(data.DataError, match="materializ|bytes|binding|snapshot"):
        data.materialize(case.reader)

    assert calls >= 2, "materialization must verify raw bytes after writing them"
    assert not (case.reader / ".git/oracle-data-materialized.json").exists()


def test_candidate_gate_checks_exact_primary_blob_instead_of_smudged_bytes(
    snapshot_case,
):
    case = snapshot_case
    data.prepare(case.publisher)
    (case.publisher / ATTRIBUTES).write_bytes(b"bot.json text eol=crlf\n")
    raw_primary = (
        json.dumps(
            {"suite": "bot", "revision": "incoming-attributes"}, sort_keys=True
        ).encode()
        + b"\r\n"
    )
    (case.publisher / BOT_REPORT).write_bytes(raw_primary)
    # The real overview currently agrees with the publisher's CRLF bytes. Git
    # will stage LF bytes, so the exact publication candidate must fail its
    # overview gate even though an ordinary checkout smudges it back to CRLF.
    _overview(case.publisher)
    _overview(case.publisher, check=True)
    before_main = git(case.origin, "rev-parse", data.MAIN_REF)
    before_data = git(case.origin, "rev-parse", data.DATA_REF)
    before_head = git(case.publisher, "rev-parse", "HEAD")
    before_index = git(case.publisher, "write-tree")

    with pytest.raises(data.DataError, match="publication freshness gates failed"):
        data.publish(
            case.publisher,
            group="dashboard",
            message="reject overview of smudged primary bytes",
        )

    assert git(case.origin, "rev-parse", data.MAIN_REF) == before_main
    assert git(case.origin, "rev-parse", data.DATA_REF) == before_data
    assert git(case.publisher, "rev-parse", "HEAD") == before_head
    assert git(case.publisher, "write-tree") == before_index
