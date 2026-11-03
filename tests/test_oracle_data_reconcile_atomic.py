"""Reconcile must preserve whole report revisions across clean Git merges.

These repositories contain only tiny JSON documents and the production overview
generator. Snapshot checks are independent of the publisher implementation.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from test_oracle_data import commit, data, git
from test_oracle_data_snapshot_properties import (
    MANIFEST,
    REVIEWED,
    SCOPES,
    SNAPSHOT,
    _assert_bound,
    _overview,
    _read,
    _state,
    _tree_files,
    _write,
)
from test_oracle_data_snapshot_properties import (
    snapshot_case as snapshot_case,  # noqa: PLC0414
)


def _write_primary(root: Path, report: dict) -> None:
    (root / REVIEWED).write_text(json.dumps(report, indent=2) + "\n")
    _overview(root)
    _overview(root, check=True)


def _bind_and_commit(root: Path) -> str:
    commit(root, {})
    _write(
        root,
        SNAPSHOT,
        {"schema": data.SNAPSHOT_SCHEMA, "files": _tree_files(root, "HEAD")},
    )
    return commit(root, {})


def _diverge_primary(case, original: dict, bot: dict, reviewed: dict) -> bytes:
    _write_primary(case.seed, original)
    case.main = _bind_and_commit(case.seed)
    git(case.seed, "push", "origin", f"HEAD:{data.MAIN_REF}", f"HEAD:{data.DATA_REF}")

    git(case.seed, "checkout", "-B", "oracle-data", case.main)
    _write_primary(case.seed, bot)
    _bind_and_commit(case.seed)
    git(case.seed, "push", "origin", f"HEAD:{data.DATA_REF}")

    git(case.seed, "checkout", "main")
    _write_primary(case.seed, reviewed)
    case.main = commit(case.seed, {})
    reviewed_bytes = (case.seed / REVIEWED).read_bytes()
    git(case.seed, "push", "origin", f"HEAD:{data.MAIN_REF}")
    return reviewed_bytes


def _reconcile_and_read(case) -> bytes:
    data.prepare(case.publisher, reconcile=True)
    _overview(case.publisher)
    assert data.publish(case.publisher, group="all", message="reconcile whole reports")
    assert _read(case, baseline=False)
    _assert_bound(case.reader)
    return (case.reader / REVIEWED).read_bytes()


def _counts(*, matched: int, missing: int, errors: int) -> dict:
    # Separate the changed fields so Git can merge them without a conflict.
    return {
        "total": 100,
        "matched": matched,
        **{f"unchanged_first_{i}": i for i in range(12)},
        "missing": missing,
        **{f"unchanged_second_{i}": i for i in range(12)},
        "errors": errors,
    }


def test_reconcile_keeps_whole_reviewed_report_after_disjoint_bot_edit(snapshot_case):
    case = snapshot_case
    reviewed_bytes = _diverge_primary(
        case,
        _counts(matched=40, missing=30, errors=30),
        _counts(matched=50, missing=20, errors=30),
        _counts(matched=40, missing=20, errors=40),
    )

    actual_bytes = _reconcile_and_read(case)

    actual = json.loads(actual_bytes)
    assert (
        sum(actual[name] for name in ("matched", "missing", "errors"))
        == actual["total"]
    ), (
        "Git's line merge published counts summing to 110 from two valid 100-count reports"
    )
    assert actual_bytes == reviewed_bytes


@pytest.mark.parametrize("operation", ["prepare", "producer-baseline"])
def test_ordinary_producer_refuses_clean_line_merged_primary(snapshot_case, operation):
    case = snapshot_case
    _diverge_primary(
        case,
        _counts(matched=40, missing=30, errors=30),
        _counts(matched=50, missing=20, errors=30),
        _counts(matched=40, missing=20, errors=40),
    )
    root = case.publisher if operation == "prepare" else case.baseline_reader
    if operation == "producer-baseline":
        git(root, "fetch", "origin", data.MAIN_REF)
        git(root, "reset", "--hard", "FETCH_HEAD")
    before = _state(root)
    remote_tips = tuple(
        git(case.origin, "rev-parse", ref) for ref in (data.MAIN_REF, data.DATA_REF)
    )

    with pytest.raises(data.DataError):
        if operation == "prepare":
            data.prepare(root)
        else:
            data.materialize(root, baseline=True)

    assert _state(root) == before
    assert (
        tuple(
            git(case.origin, "rev-parse", ref) for ref in (data.MAIN_REF, data.DATA_REF)
        )
        == remote_tips
    )


_WEIGHT_FIELDS = {
    "household_weight",
    "comparison_weight",
    "match_weight",
    "mismatch_weight",
    "left_weighted_sum",
    "right_weighted_sum",
    "weighted_difference",
}


def _double_population_weights(value):
    if isinstance(value, list):
        return [_double_population_weights(item) for item in value]
    if isinstance(value, dict):
        return {
            key: item * 2 if key in _WEIGHT_FIELDS else _double_population_weights(item)
            for key, item in value.items()
        }
    return value


def _ca_snap_report() -> dict:
    """Two households retain the native CA SNAP result/provenance structure."""
    concept = "us:statutes/7/2014/u#snap_benefit"
    return {
        "aggregates": [
            {
                "category": "food",
                "comparison": "amount",
                "comparison_count": 2,
                "comparison_weight": 5,
                "concept": concept,
                "left_weighted_sum": 1700,
                "match_weight": 2,
                "mismatch_count": 1,
                "mismatch_weight": 3,
                "right_weighted_sum": 1400,
                "weighted_difference": 300,
            }
        ],
        "case_count": 2,
        "cases": [
            {"case_id": "ecps-match", "household_weight": 2},
            {"case_id": "ecps-mismatch", "household_weight": 3},
        ],
        "concepts": [{"id": concept, "comparison": "amount", "category": "food"}],
        "engines": {"left": "axiom", "right": "policyengine"},
        "errors": [],
        "mismatches": [
            {
                "case_id": "ecps-mismatch",
                "concept": concept,
                "difference": 100,
                "household_weight": 3,
                "kind": "amount_difference",
                "left": 300,
                "right": 200,
            }
        ],
        "population": "enhanced-cps",
        "provenance": {
            "dataset": {"population": "enhanced-cps", "source": "config"},
            "generated_at": "2026-10-01T00:00:00Z",
            "generated_by": "scripts/run_comparison.py::ca-snap-ecps",
            "rulespecs": [{"repo": "TheAxiomFoundation/rulespec-us", "sha": "a" * 40}],
            "run_kind": "manual",
            "schema": "axiom_oracles.provenance.v1",
        },
        "schema_version": "axiom.comparison_report.v2.1",
        "scope": "ca",
        "suite": "ca-snap-ecps",
        "summary": {
            "comparison_count": 2,
            "error_count": 0,
            "match_count": 1,
            "mismatch_count": 1,
            "mismatches_by_concept": [{"count": 1, "value": concept}],
            "mismatches_by_kind": [{"count": 1, "value": "amount_difference"}],
            "weighted": {
                "comparison_weight": 5,
                "match_weight": 2,
                "mismatch_weight": 3,
            },
        },
    }


def _assert_native_counts_and_weights(report: dict) -> None:
    assert report["schema_version"] == "axiom.comparison_report.v2.1"
    assert report["suite"] == "ca-snap-ecps"
    summary = report["summary"]
    assert (
        summary["comparison_count"]
        == summary["match_count"] + summary["mismatch_count"]
    )
    assert len(report["mismatches"]) == summary["mismatch_count"]
    for key in ("mismatches_by_kind", "mismatches_by_concept"):
        assert sum(row["count"] for row in summary[key]) == summary["mismatch_count"]
    for weighted in [summary["weighted"], *report["aggregates"]]:
        assert (
            weighted["comparison_weight"]
            == weighted["match_weight"] + weighted["mismatch_weight"]
        )


def test_reconcile_does_not_mix_ca_snap_bot_weights_with_reviewed_provenance(
    snapshot_case,
):
    case = snapshot_case
    original = _ca_snap_report()
    bot = _double_population_weights(original)
    reviewed = copy.deepcopy(original)
    reviewed["provenance"]["rulespecs"][0]["sha"] = "b" * 40
    for report in (original, bot, reviewed):
        _assert_native_counts_and_weights(report)
    reviewed_bytes = _diverge_primary(case, original, bot, reviewed)

    actual_bytes = _reconcile_and_read(case)

    actual = json.loads(actual_bytes)
    _assert_native_counts_and_weights(actual)
    assert actual_bytes == reviewed_bytes, (
        "reconcile combined bot population weights with a reviewed RuleSpec pin the bot did not carry"
    )


def _separated_revisions(*, bot: int, reviewed: int) -> str:
    return (
        json.dumps(
            {
                "bot_revision": bot,
                **{f"unchanged_{i}": i for i in range(12)},
                "reviewed_revision": reviewed,
            },
            indent=2,
        )
        + "\n"
    )


def test_reconcile_selects_whole_reviewed_files_across_every_owned_scope(snapshot_case):
    case = snapshot_case
    # SCOPES is an independent contract, not the implementation's DATA_PATHS.
    # Add distinct dashboard families because the directory scope owns them all.
    paths = [
        scope + "atomic/probe.json" if scope.endswith("/") else scope
        for scope in SCOPES
    ] + [
        REVIEWED,
        "dashboard/public/data/rule_verification.json",
        "dashboard/public/data/rule_verification_summary.json",
        "dashboard/public/data/performance.json",
        "dashboard/public/data/cases/ca-snap-ecps/chunk-000.json",
    ]
    authored = "conformance/README.md"
    original = _separated_revisions(bot=0, reviewed=0)
    bot = _separated_revisions(bot=1, reviewed=0)
    reviewed = _separated_revisions(bot=0, reviewed=1)
    commit(case.seed, {path: original for path in [*paths, authored]})
    _overview(case.seed)
    case.main = _bind_and_commit(case.seed)
    git(case.seed, "push", "origin", f"HEAD:{data.MAIN_REF}", f"HEAD:{data.DATA_REF}")

    git(case.seed, "checkout", "-B", "oracle-data", case.main)
    commit(case.seed, {path: bot for path in [*paths, authored]})
    _overview(case.seed)
    _bind_and_commit(case.seed)
    git(case.seed, "push", "origin", f"HEAD:{data.DATA_REF}")

    git(case.seed, "checkout", "main")
    commit(case.seed, {path: reviewed for path in [*paths, authored]})
    _overview(case.seed)
    case.main = commit(case.seed, {})
    git(case.seed, "push", "origin", f"HEAD:{data.MAIN_REF}")

    data.prepare(case.publisher, reconcile=True)

    for path in paths:
        assert (case.publisher / path).read_bytes() == reviewed.encode(), path
    assert (case.publisher / authored).read_text() == _separated_revisions(
        bot=1, reviewed=1
    )
    _overview(case.publisher)
    assert data.publish(
        case.publisher, group="all", message="reconcile every owned family"
    )
    assert _read(case, baseline=False)
    _assert_bound(case.reader)
    for path in paths:
        assert (case.reader / path).read_bytes() == reviewed.encode(), path
    assert (case.reader / authored).read_bytes() == reviewed.encode()


def test_reconcile_preserves_reviewed_rename_deletion_and_mode(snapshot_case):
    case = snapshot_case
    renamed = "dashboard/public/data/reviewed-renamed.json"
    deleted = "dashboard/public/data/reviewed-deleted.json"
    bot_only = "dashboard/public/data/bot-only.json"
    bot_rename_source = "dashboard/public/data/bot-rename-source.json"
    bot_rename_target = "dashboard/public/data/bot-rename-target.json"
    original = _separated_revisions(bot=0, reviewed=0)
    bot = _separated_revisions(bot=1, reviewed=0)
    reviewed = _separated_revisions(bot=0, reviewed=1)

    def report(path: str, content: str) -> str:
        # Distinct identities make Git's rename pairing unambiguous.
        return content.replace(
            "{\n", '{\n  "report_name": ' + json.dumps(path) + ",\n", 1
        )

    commit(
        case.seed,
        {
            path: report(path, original)
            for path in (REVIEWED, deleted, bot_only, bot_rename_source)
        },
    )
    _overview(case.seed)
    case.main = _bind_and_commit(case.seed)
    git(case.seed, "push", "origin", f"HEAD:{data.MAIN_REF}", f"HEAD:{data.DATA_REF}")

    git(case.seed, "checkout", "-B", "oracle-data", case.main)
    git(case.seed, "mv", bot_rename_source, bot_rename_target)
    commit(
        case.seed,
        {
            **{path: report(path, bot) for path in (REVIEWED, deleted, bot_only)},
            bot_rename_target: report(bot_rename_source, bot),
        },
    )
    _overview(case.seed)
    _bind_and_commit(case.seed)
    git(case.seed, "push", "origin", f"HEAD:{data.DATA_REF}")

    git(case.seed, "checkout", "main")
    git(case.seed, "mv", REVIEWED, renamed)
    (case.seed / renamed).write_text(report(REVIEWED, reviewed))
    (case.seed / bot_rename_source).write_text(report(bot_rename_source, reviewed))
    (case.seed / renamed).chmod(0o755)
    (case.seed / deleted).unlink()
    manifest = json.loads((case.seed / MANIFEST).read_bytes())
    manifest["reports"] = [
        Path(renamed).name if name == Path(REVIEWED).name else name
        for name in manifest["reports"]
    ]
    _write(case.seed, MANIFEST, manifest)
    _overview(case.seed)
    case.main = commit(case.seed, {})
    git(case.seed, "push", "origin", f"HEAD:{data.MAIN_REF}")

    data.prepare(case.publisher, reconcile=True)

    assert (case.publisher / renamed).read_bytes() == report(
        REVIEWED, reviewed
    ).encode()
    assert (case.publisher / renamed).stat().st_mode & 0o111 == 0o111
    assert not (case.publisher / REVIEWED).exists()
    assert not (case.publisher / deleted).exists()
    assert (case.publisher / bot_only).read_bytes() == report(bot_only, bot).encode()
    assert (case.publisher / bot_rename_source).read_bytes() == report(
        bot_rename_source, reviewed
    ).encode()
    assert (case.publisher / bot_rename_target).read_bytes() == report(
        bot_rename_source, bot
    ).encode()
    _overview(case.publisher)
    assert data.publish(case.publisher, group="all", message="reconcile report rename")
    assert _read(case, baseline=False)
    _assert_bound(case.reader)
    assert (case.reader / renamed).read_bytes() == report(REVIEWED, reviewed).encode()
    assert (case.reader / renamed).stat().st_mode & 0o111 == 0o111
    assert not (case.reader / REVIEWED).exists()
    assert not (case.reader / deleted).exists()
    assert (case.reader / bot_only).read_bytes() == report(bot_only, bot).encode()
    assert (case.reader / bot_rename_source).read_bytes() == report(
        bot_rename_source, reviewed
    ).encode()
    assert (case.reader / bot_rename_target).read_bytes() == report(
        bot_rename_source, bot
    ).encode()
