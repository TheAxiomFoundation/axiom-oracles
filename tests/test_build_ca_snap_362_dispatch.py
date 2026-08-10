from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import build_ca_snap_362_dispositions as builder
from scripts import reconcile_ca_snap_423_dispositions as reconciliation


def test_current_check_dispatches_to_reconciler_and_prints_receipt(
    monkeypatch,
    capsys,
) -> None:
    receipt = {
        "base_rows": 345,
        "drifted_dropped": 22,
        "kept": 131,
        "vanished": 192,
    }
    calls = []

    def check(base_ref: str) -> dict:
        calls.append(base_ref)
        return receipt

    monkeypatch.setattr(builder, "_check_current_reconciliation", check)
    monkeypatch.setattr(
        builder,
        "_run_legacy",
        lambda _args: pytest.fail("current check entered legacy generation"),
    )

    assert (
        builder.main(
            [
                "--check",
                "--base-ref",
                "819f370bf0346e4a6a8dfb1c8c4f0d873d6d0340",
            ]
        )
        == 0
    )

    assert calls == ["819f370bf0346e4a6a8dfb1c8c4f0d873d6d0340"]
    assert capsys.readouterr().out == (
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )


def test_legacy_trace_dispatch_remains_generation_only(
    monkeypatch,
    capsys,
) -> None:
    observed = []

    def run_legacy(args) -> int:
        observed.append((args.trace, args.check, args.base_ref))
        return 17

    monkeypatch.setattr(builder, "_run_legacy", run_legacy)
    monkeypatch.setattr(
        builder,
        "_check_current_reconciliation",
        lambda _ref: pytest.fail("legacy generation entered current check"),
    )

    assert (
        builder.main(
            [
                "--trace",
                "trace.json",
                "--base-ref",
                "literal-base",
            ]
        )
        == 17
    )
    assert observed == [(Path("trace.json"), False, "literal-base")]
    assert capsys.readouterr().out == ""


def test_legacy_trace_check_remains_reachable(
    monkeypatch,
    capsys,
) -> None:
    observed = []

    def run_legacy(args) -> int:
        observed.append((args.trace, args.check, args.base_ref))
        return 0

    monkeypatch.setattr(builder, "_run_legacy", run_legacy)
    monkeypatch.setattr(
        builder,
        "_check_current_reconciliation",
        lambda _ref: pytest.fail("legacy check entered current reconciliation"),
    )

    assert (
        builder.main(
            [
                "--trace",
                "trace.json",
                "--base-ref",
                "literal-base",
                "--check",
            ]
        )
        == 0
    )
    assert observed == [(Path("trace.json"), True, "literal-base")]
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (
            ["--base-ref", "literal-base"],
            "--base-ref without --trace requires --check",
        ),
        (
            ["--trace", "trace.json"],
            "--base-ref is required",
        ),
        (
            ["--trace", "trace.json", "--check"],
            "--base-ref is required",
        ),
    ],
)
def test_invalid_mode_combinations_fail_closed(
    argv,
    message,
    capsys,
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        builder.main(argv)

    assert exc_info.value.code == 2
    assert message in capsys.readouterr().err


def test_legacy_base_loader_uses_pinned_report_and_output_schema(monkeypatch):
    report = {
        "mismatches": [
            {
                "case_id": "ecps-1",
                "disposition": {"id": "ca-362-example"},
            },
            {
                "case_id": "ecps-2",
                "disposition": None,
            },
        ]
    }
    case = {"id": "ecps-1", "o": [{"n": "benefit", "v": 1}]}
    index = {"chunks": 1}
    disposition_text = "schema: axiom_oracles.dispositions.v1\n"
    blobs = {
        builder.LEGACY_REPORT_RELATIVE_PATH: json.dumps(report).encode(),
        f"{builder.LEGACY_CASE_DIR_RELATIVE_PATH}/index.json": (
            json.dumps(index).encode()
        ),
        f"{builder.LEGACY_CASE_DIR_RELATIVE_PATH}/chunk-0.json": (
            json.dumps([case]).encode()
        ),
        reconciliation.BASE_DISPOSITIONS_RELATIVE_PATH: (disposition_text.encode()),
    }

    monkeypatch.setattr(
        reconciliation,
        "_load_base_dispositions",
        lambda _ref: ("resolved-commit", {"entries": []}, []),
    )
    monkeypatch.setattr(
        reconciliation,
        "_git_show",
        lambda _commit, path: blobs[path],
    )
    monkeypatch.setattr(
        builder,
        "LEGACY_REPORT_SHA256",
        hashlib.sha256(blobs[builder.LEGACY_REPORT_RELATIVE_PATH]).hexdigest(),
    )
    monkeypatch.setattr(
        builder,
        "LEGACY_CASE_INDEX_SHA256",
        hashlib.sha256(
            blobs[f"{builder.LEGACY_CASE_DIR_RELATIVE_PATH}/index.json"]
        ).hexdigest(),
    )
    monkeypatch.setattr(
        builder,
        "LEGACY_CASE_CHUNKS_SHA256",
        hashlib.sha256(
            blobs[f"{builder.LEGACY_CASE_DIR_RELATIVE_PATH}/chunk-0.json"]
        ).hexdigest(),
    )
    monkeypatch.setattr(builder, "EXPECTED_LEGACY_REPORT_ROWS", 2)
    monkeypatch.setattr(builder, "EXPECTED_LEGACY_ISSUE_362_ANNOTATIONS", 1)
    monkeypatch.setattr(builder, "EXPECTED_LEGACY_UNEXPLAINED_ROWS", 2)
    monkeypatch.setattr(builder, "EXPECTED_LEGACY_CASES", 1)

    commit, loaded_report, existing, compact, expected_text = (
        builder._load_legacy_base_inputs("literal-base")
    )

    assert commit == "resolved-commit"
    assert loaded_report["mismatches"][0]["disposition"] is None
    assert existing == {"entries": []}
    assert compact == {"ecps-1": case}
    assert expected_text == disposition_text
