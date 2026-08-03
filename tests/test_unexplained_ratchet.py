"""The per-suite unexplained ratchet must be able to fail.

Follows the repo's gate-testing convention: every CI gate carries negative
tests proving it bites (see tests/test_conformance.py for the conformance
ratchet's).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import unexplained_ratchet  # noqa: E402


def test_committed_ratchet_passes_against_committed_reports():
    counts = unexplained_ratchet.live_counts()
    ceilings = unexplained_ratchet.load_ratchet()
    assert unexplained_ratchet.check(counts, ceilings) == []


def test_every_gated_suite_is_pinned():
    # A suite missing from the pin file has ceiling 0 by design; every
    # currently-published suite should carry an explicit row so improvements
    # ratchet down from a recorded baseline.
    counts = unexplained_ratchet.live_counts()
    ceilings = unexplained_ratchet.load_ratchet()
    assert set(counts) <= set(ceilings)


def test_a_new_unexplained_row_fails_the_gate():
    ceilings = {"some-suite": 3}
    problems = unexplained_ratchet.check({"some-suite": 4}, ceilings)
    assert len(problems) == 1
    assert "RATCHET regressed" in problems[0]
    assert "some-suite" in problems[0]


def test_a_new_suite_defaults_to_a_zero_ceiling():
    problems = unexplained_ratchet.check({"brand-new-suite": 1}, {})
    assert len(problems) == 1
    assert "brand-new-suite" in problems[0]
    # ...and a fully triaged new suite publishes freely.
    assert unexplained_ratchet.check({"brand-new-suite": 0}, {}) == []


def test_counts_at_the_ceiling_pass_and_below_it_pass():
    ceilings = {"suite-a": 5}
    assert unexplained_ratchet.check({"suite-a": 5}, ceilings) == []
    assert unexplained_ratchet.check({"suite-a": 2}, ceilings) == []


def test_count_unexplained_prefers_backed_disposition_block():
    report = {
        "summary": {
            "dispositioned": {
                "dispositions_file": "dispositions/x.yaml",
                "unexplained_count": 7,
            },
            "mismatch_count": 100,
        },
        "mismatches": [
            {"concept": "c1", "kind": "amount_difference"} for _ in range(100)
        ],
    }
    assert unexplained_ratchet.count_unexplained(report, []) == 7


def test_count_unexplained_stub_block_falls_back_to_buckets():
    # A dispositioned block with no backing file is a stub (mirrors the
    # dashboard's countUnexplained): fall back to known-causes buckets.
    report = {
        "suite": "s",
        "engines": {"left": "axiom", "right": "policyengine"},
        "summary": {"dispositioned": {"dispositions_file": None, "unexplained_count": 0}},
        "mismatches": [
            {"concept": "c1", "kind": "amount_difference"},
            {"concept": "c2", "kind": "amount_difference"},
            {"concept": None, "kind": "not_concept_keyed"},
        ],
    }
    causes = [{"suite": "s", "concept": "c1", "kind": "amount_difference"}]
    # c1 covered by the registry, c2 not; the concept-less row never counts.
    assert unexplained_ratchet.count_unexplained(report, causes) == 1


def test_engine_specific_known_cause_does_not_cover_other_pairs():
    report = {
        "suite": "s",
        "engines": {"left": "axiom", "right": "policyengine"},
        "summary": {},
        "mismatches": [{"concept": "c1", "kind": "amount_difference"}],
    }
    causes = [
        {
            "suite": "s",
            "concept": "c1",
            "kind": "amount_difference",
            "engines": {"left": "policyengine", "right": "taxsim"},
        }
    ]
    assert unexplained_ratchet.count_unexplained(report, causes) == 1
