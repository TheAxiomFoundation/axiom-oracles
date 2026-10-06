"""Evidence readiness and scope cannot be bypassed by direct report merging."""

from copy import deepcopy
import json

import pytest
import yaml
from hypothesis import HealthCheck, given, settings, strategies as st

from axiom_oracles.comparison import adjudications
from axiom_oracles.comparison.dispositions import (
    DispositionError,
    apply_dispositions,
    validate_dispositions,
)
from scripts import export_taxsim_dashboard_notes as exporter


@pytest.fixture
def example(tmp_path, monkeypatch):
    record = {
        "id": "verified", "question": "Does the deduction apply?", "jurisdiction": "LA",
        "law_years": [2025], "engines": ["policyengine", "taxsim"],
        "status": "evidence_ready", "attribution": "taxsim", "verdict": "taxsim_wrong",
        "issues": ["https://github.com/PolicyEngine/policyengine-taxsim/issues/1222"],
    }
    registry = {"adjudications": [record]}
    monkeypatch.setattr(adjudications, "load_adjudications", lambda *a, **kw: registry)
    monkeypatch.setattr(exporter, "load_adjudications", lambda *a, **kw: registry)
    suite = "taxsim-emulator-test"
    entry = {
        "id": "deduction", "concept": "us:tax/state-income-tax#liability",
        "case_id": "case-1", "disposition": "upstream_engine_gap", "attribution": "taxsim",
        "adjudication": "verified", "expires_on_source_change": True,
        "pinned": {"left": 10, "right": 20}, "oracle_binding": {"identity_unrecorded": True},
        "evidence": {"mechanism": "The verified deduction is omitted.",
                     "upstream_url": record["issues"][0]},
    }
    document = {"schema": "axiom_oracles.dispositions.v1", "suite": suite, "entries": [entry]}
    report = {
        "suite": suite, "engines": {"left": "policyengine", "right": "taxsim"},
        "locales": ["US-LA", "US-TX"],
        "summary": {"comparison_count": 2, "match_count": 1, "mismatch_count": 1},
        "mismatches": [{"case_id": "case-1", "concept": entry["concept"],
                        "left": 10, "right": 20, "difference": -10,
                        "facts": {"state": "LA", "year": 2025}}],
    }
    comparisons = tmp_path / "comparisons"
    comparisons.mkdir()
    (comparisons / f"{suite}.yaml").write_text(yaml.safe_dump({
        "name": suite, "runner": {"parameters": {"left": "policyengine", "right": "taxsim",
                                                  "period": "2025"}},
        "artifacts": {"report_path": "reports/test.json"},
    }))
    return tmp_path, record, document, report


@pytest.mark.parametrize("field,value,error", [
    ("status", "pending_evidence", "evidence_ready"),
    ("status", "open", "evidence_ready"),
    ("attribution", "policyengine", "attribution"),
    ("engines", ["taxsim"], "cover policyengine"),
    ("law_years", [2024], "law year"),
])
def test_load_and_direct_merge_require_ready_matching_adjudication(example, field, value, error):
    root, record, document, report = example
    record[field] = value
    assert any(error in problem for problem in validate_dispositions(document, repo_root=root))
    with pytest.raises(DispositionError, match=error):
        apply_dispositions(report, document, repo_root=root)


@pytest.mark.parametrize("field,value,error", [
    ("state", "TX", "jurisdiction"),
    ("state", None, "jurisdiction"),
    ("year", 2024, "law year"),
    ("year", None, "law year"),
])
def test_every_selected_row_must_be_in_scope_even_when_lane_flag_is_false(example, field, value, error):
    root, _, document, report = example
    report["mismatches"][0]["facts"][field] = value
    with pytest.raises(DispositionError, match=error):
        apply_dispositions(report, document, repo_root=root, taxsim_lane=False)


@given(year=st.integers(min_value=1900, max_value=2100).filter(lambda year: year != 2025))
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=20)
def test_any_out_of_scope_year_fails_before_an_explanation_can_be_assigned(example, year):
    root, _, document, original = example
    report = deepcopy(original)
    report["mismatches"][0]["facts"]["year"] = year
    with pytest.raises(DispositionError, match="law year"):
        apply_dispositions(report, document, repo_root=root)


def test_missing_reference_and_document_suite_mismatch_fail(example):
    root, _, document, report = example
    del document["entries"][0]["adjudication"]
    with pytest.raises(DispositionError, match="existing adjudication"):
        apply_dispositions(report, document, repo_root=root)
    document["suite"] = "other"
    with pytest.raises(DispositionError, match="suite must equal"):
        apply_dispositions(report, document, repo_root=root)


def test_unexplained_hypothesis_may_be_pending_but_reference_must_exist(example):
    root, record, document, report = example
    record["status"] = "pending_evidence"
    entry = document["entries"][0]
    entry["disposition"], entry["attribution"] = "unexplained", "two_sided"
    assert apply_dispositions(report, document, repo_root=root)["summary"]["dispositioned"]["unexplained_count"] == 1
    entry["adjudication"] = "missing"
    with pytest.raises(DispositionError, match="existing adjudication"):
        apply_dispositions(report, document, repo_root=root)


def test_only_us_conventions_can_span_state_income_tax_jurisdictions(example):
    root, record, document, report = example
    record["jurisdiction"] = "US"
    with pytest.raises(DispositionError, match="federal adjudication"):
        apply_dispositions(report, document, repo_root=root)
    record["verdict"], record["attribution"] = "convention", "convention"
    document["entries"][0]["attribution"] = "convention"
    assert apply_dispositions(report, document, repo_root=root)["summary"]["dispositioned"]["unexplained_count"] == 0


def test_merge_reverifies_registry_and_does_not_trust_prior_success(example, monkeypatch):
    root, _, document, report = example
    assert validate_dispositions(document, repo_root=root) == []

    def changed_snapshot(*args, **kwargs):
        raise ValueError("snapshot sha256 mismatch")

    monkeypatch.setattr(adjudications, "load_adjudications", changed_snapshot)
    with pytest.raises(DispositionError, match="snapshot sha256 mismatch"):
        apply_dispositions(report, document, repo_root=root)


def test_export_is_deterministic_and_counts_bound_rows_without_inventing_coverage(example):
    root, record, document, report = example
    (root / "dispositions").mkdir()
    (root / "dispositions" / f"{report['suite']}.yaml").write_text(yaml.safe_dump(document))
    (root / "reports").mkdir()
    (root / "reports/test.json").write_text(json.dumps(report))
    before = deepcopy(document)
    first = exporter.dashboard_notes(root)
    assert first == exporter.dashboard_notes(root)
    assert document == before
    by_state = {note["state"]: note for note in first["notes"]}
    assert by_state["TX"]["adjudications"] == []
    note, = by_state["LA"]["adjudications"]
    assert note["id"] == record["id"]
    assert note["affected_rows"] == 1
    assert note["ledger_entries"][0]["affected_rows"] == 1
    assert note["ledger_entries"][0]["entry_id"] == "deduction"

    record["status"] = "pending_evidence"
    document["entries"][0]["disposition"] = "unexplained"
    (root / "dispositions" / f"{report['suite']}.yaml").write_text(yaml.safe_dump(document))
    assert all(not note["adjudications"] for note in exporter.dashboard_notes(root)["notes"])


def test_export_preserves_states_with_no_mismatches_or_ledger(example):
    root, _, _, report = example
    report["mismatches"] = []
    report["summary"].update(match_count=2, mismatch_count=0)
    (root / "reports").mkdir()
    (root / "reports/test.json").write_text(json.dumps(report))
    notes = exporter.dashboard_notes(root)["notes"]
    assert {(note["state"], note["year"]) for note in notes} == {("LA", 2025), ("TX", 2025)}
    assert notes[0]["adjudications"][0]["affected_rows"] == 0
    assert notes[0]["adjudications"][0]["ledger_entries"] == []


def test_export_rejects_header_swap_to_another_registered_emulator_suite(example):
    root, _, _, report = example
    second = "taxsim-emulator-other"
    (root / "comparisons" / f"{second}.yaml").write_text(yaml.safe_dump({
        "name": second, "artifacts": {"report_path": "reports/other.json"},
    }))
    report["suite"] = second
    (root / "reports").mkdir()
    (root / "reports/test.json").write_text(json.dumps(report))
    (root / "reports/other.json").write_text(json.dumps(report))
    with pytest.raises(ValueError, match="unexpected suite"):
        exporter.dashboard_notes(root)
