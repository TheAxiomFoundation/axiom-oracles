"""The per-suite unexplained ratchet must be able to fail.

Follows the repo's gate-testing convention: every CI gate carries negative
tests proving it bites (see tests/test_conformance.py for the conformance
ratchet's).
"""

from __future__ import annotations

import sys
import json
from pathlib import Path

import pytest
import yaml

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
                "counts": {"upstream_engine_gap": 93},
            },
            "mismatch_count": 100,
        },
        "mismatches": [
            {"concept": "c1", "kind": "amount_difference"} for _ in range(100)
        ],
    }
    assert unexplained_ratchet.count_unexplained(report, []) == 7


def test_count_unexplained_stub_block_preserves_conceptless_rows():
    # No admitted classifications: known causes can cover concept-keyed rows,
    # while concept-less mismatch rows remain unexplained.
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
    # c1 is covered; c2 and the concept-less row remain unexplained.
    assert unexplained_ratchet.count_unexplained(report, causes) == 2


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


def _gate_report(suite="some-suite", count=0):
    return {
        "suite": suite,
        "engines": {"left": "axiom", "right": "reference"},
        "summary": {"mismatch_count": count},
        "mismatches": [],
    }


def test_vanished_pin_fails_instead_of_becoming_zero():
    problems = unexplained_ratchet.check({}, {"retired-suite": 0})
    assert len(problems) == 1
    assert "retired-suite" in problems[0] and "no live gated report" in problems[0]


@pytest.mark.parametrize("payload", ['{"broken":', '{"value": NaN}', '{"value": Infinity}', '{"value": 1e999}'])
def test_unparseable_dashboard_json_fails_check(tmp_path, monkeypatch, capsys, payload):
    (tmp_path / "broken.json").write_text(payload)
    monkeypatch.setattr(unexplained_ratchet, "DASHBOARD_DATA", tmp_path)
    monkeypatch.setattr(sys, "argv", ["ratchet", "--check"])
    assert unexplained_ratchet.main() == 1
    assert "broken.json: invalid dashboard JSON" in capsys.readouterr().err


def test_diagnostic_name_alone_does_not_exempt_report(tmp_path, monkeypatch):
    suite = "new-diagnostic-should-gate"
    (tmp_path / "report.json").write_text(json.dumps(_gate_report(suite, 3)))
    monkeypatch.setattr(unexplained_ratchet, "DASHBOARD_DATA", tmp_path)
    monkeypatch.setattr(unexplained_ratchet, "diagnostic_suites", lambda: set())
    assert unexplained_ratchet.live_counts() == {suite: 3}
    monkeypatch.setattr(unexplained_ratchet, "diagnostic_suites", lambda: {suite})
    assert unexplained_ratchet.live_counts() == {}


def test_duplicate_resolver_uses_unexplained_not_raw_mismatches(tmp_path, monkeypatch):
    classified = _gate_report(count=100)
    classified["summary"]["dispositioned"] = {
        "counts": {"upstream_engine_gap": 99}, "unexplained_count": 1,
    }
    (tmp_path / "a.json").write_text(json.dumps(classified))
    (tmp_path / "b.json").write_text(json.dumps(_gate_report(count=3)))
    monkeypatch.setattr(unexplained_ratchet, "DASHBOARD_DATA", tmp_path)
    assert unexplained_ratchet.live_counts() == {"some-suite": 3}
    assert unexplained_ratchet.gated_reports()["some-suite"]["_file"] == "b.json"


def test_lower_count_duplicate_cannot_hide_hard_defect(tmp_path, monkeypatch, capsys):
    (tmp_path / "bad.json").write_text(json.dumps(_gate_report(count=True)))
    (tmp_path / "large.json").write_text(json.dumps(_gate_report(count=3)))
    monkeypatch.setattr(unexplained_ratchet, "DASHBOARD_DATA", tmp_path)
    monkeypatch.setattr(unexplained_ratchet, "load_ratchet", lambda: {"some-suite": 3})
    monkeypatch.setattr(sys, "argv", ["ratchet", "--check"])
    assert unexplained_ratchet.main() == 1
    output = capsys.readouterr().err
    assert "some-suite" in output and "bad.json" in output and "boolean" in output


def test_repin_preserves_correction_note(tmp_path, monkeypatch):
    path = tmp_path / "ratchet.yaml"
    monkeypatch.setattr(unexplained_ratchet, "RATCHET_PATH", path)
    unexplained_ratchet.write_ratchet({"suite": 97}, notes={"suite": "review correction"})
    unexplained_ratchet.write_ratchet({"suite": 90})
    assert yaml.safe_load(path.read_text())["ratchets"] == [
        {"suite": "suite", "unexplained_max": 90, "note": "review correction"},
    ]


def test_repin_refuses_to_tighten_vanished_suite(tmp_path, monkeypatch):
    path = tmp_path / "ratchet.yaml"
    monkeypatch.setattr(unexplained_ratchet, "RATCHET_PATH", path)
    unexplained_ratchet.write_ratchet({"vanished": 5})
    before = path.read_bytes()
    monkeypatch.setattr(unexplained_ratchet, "live_assessments", lambda: ({}, []))
    monkeypatch.setattr(sys, "argv", ["ratchet"])
    assert unexplained_ratchet.main() == 1
    assert path.read_bytes() == before
