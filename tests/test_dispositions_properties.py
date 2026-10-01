"""Seeded generative invariants; Hypothesis could not be locked without PyPI.

Each seed runs 25 independently generated reports per property. Expected row
assignments and counts come from the generated groups, not the merge's counters.
"""

from collections import Counter
import copy
import random

import pytest

from axiom_oracles.comparison.dispositions import (
    CLASSIFIED_DISPOSITION_KINDS,
    DISPOSITIONS_SCHEMA_VERSION,
    DISPOSITION_KINDS,
    DispositionConservationError,
    apply_dispositions,
    assignment_digest,
    selection_binding,
    validate_dispositions,
)


SEEDS = (3, 19, 271, 20260926)
TRIALS = 25
SHA = "a" * 64
CONCEPT = "us:test#tax"


def _generated_report(rng: random.Random) -> tuple[dict, dict]:
    rows = []
    for index in range(rng.randint(1, 30)):
        right = rng.randint(-100_000, 100_000)
        difference = rng.choice((-1, 1)) * rng.randint(1, 10_000)
        rows.append({
            "case_id": f"case-{index}",
            "concept": CONCEPT,
            "kind": "amount_difference",
            "left": right + difference,
            "right": right,
            "difference": difference,
            "facts": {"group": rng.randrange(5), "expected_right": right},
        })
    entries = []
    for group in sorted({row["facts"]["group"] for row in rows}):
        if entries and rng.randrange(4) == 0:
            continue
        selected = [row for row in rows if row["facts"]["group"] == group]
        entries.append({
            "id": f"group-{group}",
            "concept": CONCEPT,
            "match": {"facts": {"group": group}},
            "disposition": rng.choice(DISPOSITION_KINDS),
            "attribution": "taxsim",
            "expires_on_source_change": True,
            "selector_binding": selection_binding(selected),
            "oracle_binding": {"taxsim_binary_sha256": [SHA]},
            "evidence": {
                "mechanism": "Generated row stores its expected right-side value.",
                "row_arithmetic": [{
                    "expression": "right - facts.expected_right",
                    "equals": 0,
                    "tolerance": 0,
                }],
            },
        })
    matches = rng.randint(0, 100)
    report = {
        "schema_version": "axiom.comparison_report.v2",
        "suite": "generated-taxsim",
        "engines": {"left": "policyengine", "right": "taxsim"},
        "provenance": {"oracle": {"taxsim_binaries": [{"sha256": SHA}]}},
        "summary": {
            "match_count": matches,
            "mismatch_count": len(rows),
            "comparison_count": matches + len(rows),
        },
        "mismatches": rows,
    }
    document = {
        "schema": DISPOSITIONS_SCHEMA_VERSION,
        "suite": report["suite"],
        "entries": entries,
    }
    assert validate_dispositions(
        document, suite_engines=("policyengine", "taxsim")
    ) == []
    return report, document


@pytest.mark.parametrize("seed", SEEDS)
def test_generated_merge_conserves_rows_counts_and_rates(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(TRIALS):
        report, document = _generated_report(rng)
        original_report, original_document = copy.deepcopy((report, document))
        merged = apply_dispositions(report, document)
        entries_by_group = {
            entry["match"]["facts"]["group"]: entry for entry in document["entries"]
        }
        expected_counts = Counter()
        for row in merged["mismatches"]:
            expected = entries_by_group.get(row["facts"]["group"])
            if expected is None:
                assert "disposition" not in row
            else:
                assert row["disposition"] == {
                    "id": expected["id"], "disposition": expected["disposition"]
                }
                expected_counts[expected["disposition"]] += 1
        assert len(merged["mismatches"]) == len(report["mismatches"])
        block = merged["summary"]["dispositioned"]
        assert block["counts"] == {
            kind: expected_counts[kind] for kind in DISPOSITION_KINDS
        }
        classified = sum(expected_counts[k] for k in CLASSIFIED_DISPOSITION_KINDS)
        total = report["summary"]["comparison_count"]
        matches = report["summary"]["match_count"]
        assert classified + block["unexplained_count"] + matches == total
        assert sum(block["counts"].values()) <= len(report["mismatches"])
        assert block["raw_match_rate"] == pytest.approx(matches / total * 100, abs=1e-6)
        assert block["explained_rate"] == pytest.approx(
            (matches + classified) / total * 100, abs=1e-6
        )
        assert 0 <= block["raw_match_rate"] <= block["explained_rate"] <= 100
        assert report == original_report and document == original_document
        assert apply_dispositions(merged, document) == merged


@pytest.mark.parametrize("seed", SEEDS)
def test_generated_assignment_digest_is_order_independent(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(TRIALS):
        report, document = _generated_report(rng)
        merged = apply_dispositions(report, document)
        shuffled_report, shuffled_document = copy.deepcopy((report, document))
        rng.shuffle(shuffled_report["mismatches"])
        rng.shuffle(shuffled_document["entries"])
        shuffled = apply_dispositions(shuffled_report, shuffled_document)
        assert assignment_digest(shuffled) == assignment_digest(merged)
        changed = copy.deepcopy(merged)
        row = rng.choice(changed["mismatches"])
        row["disposition"] = {
            "id": "different-assignment", "disposition": "upstream_engine_gap"
        }
        assert assignment_digest(changed) != assignment_digest(merged)


@pytest.mark.parametrize("seed", SEEDS)
def test_generated_overlap_is_rejected_only_in_taxsim_lanes(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(TRIALS):
        report, document = _generated_report(rng)
        if not document["entries"]:
            continue
        original = rng.choice(document["entries"])
        duplicate = copy.deepcopy(original)
        duplicate["id"] = "overlapping-entry"
        document["entries"].append(duplicate)
        with pytest.raises(DispositionConservationError):
            apply_dispositions(report, document)
        report["engines"]["right"] = "euromod"
        merged = apply_dispositions(report, document)
        selected = [
            row for row in merged["mismatches"]
            if row["facts"]["group"] == original["match"]["facts"]["group"]
        ]
        assert selected
        assert all(row["disposition"]["id"] == original["id"] for row in selected)


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("guard", ("binding", "identity", "arithmetic"))
def test_generated_failed_guard_revokes_every_assignment(seed: int, guard: str) -> None:
    rng = random.Random(seed)
    for _ in range(TRIALS):
        report, document = _generated_report(rng)
        if not document["entries"]:
            continue
        entry = rng.choice(document["entries"])
        merged = apply_dispositions(report, document)
        selected = [
            row for row in merged["mismatches"]
            if row["facts"]["group"] == entry["match"]["facts"]["group"]
        ]
        assert selected and all("disposition" in row for row in selected)
        if guard == "binding":
            entry["selector_binding"]["units"] += 1
            reason = "selector_binding_violated"
        elif guard == "identity":
            entry["oracle_binding"]["taxsim_binary_sha256"] = ["b" * 64]
            reason = "oracle_identity_changed"
        else:
            # Only one randomly selected member fails, at any position.
            rng.choice(selected)["facts"]["expected_right"] += 1
            entry["selector_binding"] = selection_binding(selected)
            reason = "row_arithmetic_failed"
        expired = apply_dispositions(merged, document)
        block = expired["summary"]["dispositioned"]
        assert block["expired_reasons"] == {entry["id"]: reason}
        assert all(
            "disposition" not in row for row in expired["mismatches"]
            if row["facts"]["group"] == entry["match"]["facts"]["group"]
        )
        assert not any(
            row.get("disposition", {}).get("id") == entry["id"]
            for row in expired["mismatches"]
        )
