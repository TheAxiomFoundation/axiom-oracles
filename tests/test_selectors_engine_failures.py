"""Signature bindings must account for both failing comparison engines."""

import copy
import hashlib
import json

import pytest

from axiom_oracles.comparison.dispositions import (
    DISPOSITIONS_SCHEMA_VERSION,
    apply_dispositions,
    selection_binding,
    validate_dispositions,
)
from axiom_oracles.comparison.selectors import mismatch_signature


SHA = "a" * 64


def _both_failed_row() -> dict:
    return {
        "case_id": "case-1",
        "concept": "us:test#income_tax",
        "kind": "engine_error",
        "left": None,
        "right": None,
        "difference": None,
        "facts": {"state": "GA", "year": 2024},
        "error": {
            "engine": "policyengine",
            "side": "left",
            "signature": "unclassified",
            "messages": ["PolicyEngine failed"],
            "other_side": {
                "engine": "taxsim",
                "side": "right",
                "signature": "SIGFPE",
                "messages": ["taxsim-crash:SIGFPE"],
                "binary_sha256": SHA,
            },
        },
    }


def test_other_side_failure_change_expires_signature_bound_disposition() -> None:
    row = _both_failed_row()
    report = {
        "schema_version": "axiom.comparison_report.v2",
        "suite": "example-taxsim",
        "engines": {"left": "policyengine", "right": "taxsim"},
        "provenance": {"oracle": {"taxsim_binaries": [{"sha256": SHA}]}},
        "summary": {
            "comparison_count": 1,
            "match_count": 0,
            "mismatch_count": 1,
        },
        "mismatches": [row],
    }
    document = {
        "schema": DISPOSITIONS_SCHEMA_VERSION,
        "suite": report["suite"],
        "entries": [{
            "id": "taxsim-sigfpe",
            "concept": row["concept"],
            "signatures": [mismatch_signature(row)],
            "selector_binding": selection_binding([row], signature=True),
            "disposition": "upstream_engine_gap",
            "attribution": "taxsim",
            "evidence": {"mechanism": "This TAXSIM binary crashes with SIGFPE."},
            "linked_issue": "https://example.test/taxsim/issues/1",
            "oracle_binding": {"taxsim_binary_sha256": [SHA]},
            "expires_on_source_change": True,
        }],
    }
    assert validate_dispositions(
        document, suite_engines=("policyengine", "taxsim")
    ) == []
    classified = apply_dispositions(report, document)
    assert classified["summary"]["dispositioned"]["counts"]["upstream_engine_gap"] == 1

    changed = copy.deepcopy(classified)
    changed["mismatches"][0]["error"]["other_side"]["signature"] = "rc=127"
    reapplied = apply_dispositions(changed, document)
    block = reapplied["summary"]["dispositioned"]
    assert block["counts"]["upstream_engine_gap"] == 0
    assert block["expired_entries"] == ["taxsim-sigfpe"]
    assert "disposition" not in reapplied["mismatches"][0]


@pytest.mark.parametrize("field,value", [
    ("engine", "euromod"), ("side", "unknown"), ("signature", "rc=127"),
])
@pytest.mark.parametrize("secondary", [False, True])
def test_both_failure_signature_binds_each_side_identity(
    field, value, secondary
) -> None:
    row = _both_failed_row()
    changed = copy.deepcopy(row)
    detail = changed["error"]
    if secondary:
        detail = detail["other_side"]
    detail[field] = value
    assert mismatch_signature(changed) != mismatch_signature(row)


def test_second_failure_changes_a_single_failure_signature() -> None:
    row = _both_failed_row()
    single_failure = copy.deepcopy(row)
    del single_failure["error"]["other_side"]
    assert mismatch_signature(single_failure) != mismatch_signature(row)


def test_both_failure_signature_is_independent_of_primary_error_order() -> None:
    row = _both_failed_row()
    swapped = copy.deepcopy(row)
    first = swapped["error"]
    second = first.pop("other_side")
    second["other_side"] = first
    swapped["error"] = second
    assert mismatch_signature(swapped) == mismatch_signature(row)


def test_both_failure_signature_ignores_messages_and_mapping_order() -> None:
    row = _both_failed_row()
    changed = copy.deepcopy(row)
    changed["error"]["messages"] = ["New diagnostic wording"]
    second = changed["error"]["other_side"]
    second["messages"] = ["A different SIGFPE diagnostic"]
    changed["error"]["other_side"] = dict(reversed(list(second.items())))
    assert mismatch_signature(changed) == mismatch_signature(row)


@pytest.mark.parametrize("has_error", [False, True])
def test_signature_without_second_failure_preserves_legacy_digest(has_error) -> None:
    row = _both_failed_row()
    if has_error:
        del row["error"]["other_side"]
    else:
        del row["error"]
        row["kind"] = "amount_difference"
        row.update(left=100, right=90, difference=10)
    legacy_identity = {
        "concept": row["concept"],
        "kind": row["kind"],
        "delta": row["difference"],
        "facts": row["facts"],
        "error_signature": row.get("error", {}).get("signature"),
    }
    legacy_digest = hashlib.sha256(json.dumps(
        legacy_identity, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    assert mismatch_signature(row) == legacy_digest
