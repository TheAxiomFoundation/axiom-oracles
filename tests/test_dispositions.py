import json
from pathlib import Path

import pytest
import yaml

from axiom_oracles.comparison.comparator import Comparator
from axiom_oracles.comparison.dispositions import (
    DISPOSITIONED_REPORT_SCHEMA_VERSION,
    DISPOSITIONS_SCHEMA_VERSION,
    DispositionError,
    apply_dispositions,
    dispositioned_rollup,
    evaluate_arithmetic,
    load_dispositions,
    validate_dispositions,
)
from axiom_oracles.comparison.mappings import ProgramMapping
from axiom_oracles.comparison.report import build_comparison_report
from axiom_oracles.core.case import Case
from axiom_oracles.core.results import EngineResult

REPO_ROOT = Path(__file__).resolve().parent.parent
DISPOSITIONS_DIR = REPO_ROOT / "dispositions"
DASHBOARD_DATA_DIR = REPO_ROOT / "dashboard" / "public" / "data"


def _entry(**overrides) -> dict:
    entry = {
        "id": "example-residual",
        "concept": "us:test#income_tax",
        "case_id": "case-1",
        "disposition": "upstream_engine_gap",
        "evidence": {
            "mechanism": "The right engine applies a stale rate table.",
            "arithmetic": [{"expression": "125 - 100", "equals": 25}],
            "upstream_url": "https://example.org/upstream/1",
        },
        "expires_on_source_change": True,
    }
    entry.update(overrides)
    return entry


def _document(entries: list[dict]) -> dict:
    return {
        "schema": DISPOSITIONS_SCHEMA_VERSION,
        "suite": "example-suite",
        "entries": entries,
    }


def _build_report(*, right_values=(125, 50)) -> dict:
    mapping = ProgramMapping(
        standard="us:test#income_tax",
        description="Federal income tax",
        category="tax",
        comparison="amount",
        tolerance=5,
        targets={"taxsim": "fiitax", "policyengine": "fiitax"},
    )
    comparisons = Comparator([mapping]).compare(
        [
            EngineResult("taxsim", "case-1", {"fiitax": 100}),
            EngineResult("taxsim", "case-2", {"fiitax": 50}),
        ],
        [
            EngineResult("policyengine", "case-1", {"fiitax": right_values[0]}),
            EngineResult("policyengine", "case-2", {"fiitax": right_values[1]}),
        ],
    )
    return build_comparison_report(
        suite_name="example-suite",
        population="synthetic",
        locales=set(),
        scope=None,
        cases=[
            Case(case_id="case-1", period="2026"),
            Case(case_id="case-2", period="2026"),
        ],
        mappings=[mapping],
        comparisons=comparisons,
    )


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def test_valid_dispositions_document_passes() -> None:
    assert validate_dispositions(_document([_entry()])) == []


def test_disposition_without_evidence_is_invalid() -> None:
    entry = _entry()
    del entry["evidence"]
    errors = validate_dispositions(_document([entry]))
    assert any("without evidence is invalid" in error for error in errors)


def test_disposition_with_mechanism_but_no_reconciliation_is_invalid() -> None:
    entry = _entry(
        evidence={"mechanism": "Something differs."},
        linked_issue=None,
    )
    del entry["linked_issue"]
    errors = validate_dispositions(_document([entry]))
    assert any(
        "arithmetic that reconciles or an upstream citation" in error
        for error in errors
    )


def test_arithmetic_that_does_not_reconcile_is_invalid() -> None:
    entry = _entry(
        evidence={
            "mechanism": "Claims 2 + 2 is 5.",
            "arithmetic": [{"expression": "2 + 2", "equals": 5}],
        }
    )
    errors = validate_dispositions(_document([entry]))
    assert any("does not reconcile" in error for error in errors)


def test_arithmetic_rejects_non_arithmetic_expressions() -> None:
    with pytest.raises(ValueError, match="unsupported syntax"):
        evaluate_arithmetic("__import__('os').getcwd()")
    assert evaluate_arithmetic("3 * (820.68 + 373.08)") == pytest.approx(
        3581.28
    )


def test_unknown_disposition_kind_is_invalid() -> None:
    errors = validate_dispositions(
        _document([_entry(disposition="wontfix")])
    )
    assert any("disposition must be one of" in error for error in errors)


def test_entry_requires_exactly_one_case_reference() -> None:
    both = _entry(case_selector={"case_ids": ["case-1"]})
    neither = _entry()
    del neither["case_id"]
    errors = validate_dispositions(_document([both]))
    assert any("exactly one of" in error for error in errors)
    errors = validate_dispositions(_document([neither]))
    assert any("exactly one of" in error for error in errors)


def test_expires_on_source_change_is_required() -> None:
    entry = _entry()
    del entry["expires_on_source_change"]
    errors = validate_dispositions(_document([entry]))
    assert any("expires_on_source_change" in error for error in errors)


def test_missing_source_path_is_invalid(tmp_path: Path) -> None:
    entry = _entry(
        evidence={
            "mechanism": "Cites a file that does not exist.",
            "sources": ["docs/does-not-exist.md"],
        }
    )
    errors = validate_dispositions(
        _document([entry]), repo_root=tmp_path
    )
    assert any("missing file" in error for error in errors)


def test_load_dispositions_enforces_suite_file_name(tmp_path: Path) -> None:
    path = tmp_path / "other-suite.yaml"
    path.write_text(yaml.safe_dump(_document([_entry()])))
    with pytest.raises(DispositionError, match="does not match the file name"):
        load_dispositions(path)


# ---------------------------------------------------------------------------
# Generator merge
# ---------------------------------------------------------------------------


def test_merge_adds_dispositioned_block_and_annotates_rows() -> None:
    report = _build_report()
    merged = apply_dispositions(
        report,
        _document([_entry(linked_issue="https://example.org/upstream/1")]),
        dispositions_file="dispositions/example-suite.yaml",
    )

    block = merged["summary"]["dispositioned"]
    assert block["raw_match_rate"] == 50
    assert block["explained_rate"] == 100
    assert block["unexplained_count"] == 0
    assert block["counts"]["upstream_engine_gap"] == 1
    assert block["dispositions_file"] == "dispositions/example-suite.yaml"
    assert merged["schema_version"] == DISPOSITIONED_REPORT_SCHEMA_VERSION

    annotation = merged["mismatches"][0]["disposition"]
    assert annotation["disposition"] == "upstream_engine_gap"
    assert annotation["id"] == "example-residual"
    assert annotation["linked_issue"] == "https://example.org/upstream/1"
    # The original report is untouched (additive merge on a copy).
    assert "dispositioned" not in report["summary"]
    assert "disposition" not in report["mismatches"][0]


def test_axiom_encoding_gap_is_classified_but_not_explained() -> None:
    report = _build_report()
    merged = apply_dispositions(
        report,
        _document([_entry(disposition="axiom_encoding_gap")]),
    )
    block = merged["summary"]["dispositioned"]
    assert block["raw_match_rate"] == 50
    assert block["explained_rate"] == 50
    assert block["unexplained_count"] == 0
    assert block["counts"]["axiom_encoding_gap"] == 1


def test_merge_without_dispositions_keeps_raw_rate() -> None:
    merged = apply_dispositions(_build_report(), None)
    block = merged["summary"]["dispositioned"]
    assert block["raw_match_rate"] == 50
    assert block["explained_rate"] == 50
    assert block["unexplained_count"] == 1
    assert block["dispositions_file"] is None


def test_pinned_disposition_expires_when_source_values_change() -> None:
    entry = _entry(pinned={"left": 100, "right": 999})
    merged = apply_dispositions(_build_report(), _document([entry]))
    block = merged["summary"]["dispositioned"]
    assert block["explained_rate"] == block["raw_match_rate"] == 50
    assert block["unexplained_count"] == 1
    assert block["expired_entries"] == ["example-residual"]
    assert "disposition" not in merged["mismatches"][0]


def test_non_expiring_entry_matching_nothing_is_orphaned() -> None:
    entry = _entry(
        case_id="case-that-does-not-exist",
        expires_on_source_change=False,
    )
    merged = apply_dispositions(_build_report(), _document([entry]))
    block = merged["summary"]["dispositioned"]
    assert block["orphaned_entries"] == ["example-residual"]


def test_case_selector_prefix_matches_multiple_rows() -> None:
    report = _build_report(right_values=(125, 75))
    entry = _entry()
    del entry["case_id"]
    entry["case_selector"] = {"case_id_prefix": "case-"}
    merged = apply_dispositions(report, _document([entry]))
    block = merged["summary"]["dispositioned"]
    assert block["counts"]["upstream_engine_gap"] == 2
    assert block["raw_match_rate"] == 0
    assert block["explained_rate"] == 100


# ---------------------------------------------------------------------------
# Seeded data
# ---------------------------------------------------------------------------


def _load_dashboard_report(suite: str) -> dict:
    matches = [
        json.loads(path.read_text())
        for path in DASHBOARD_DATA_DIR.glob("*.json")
        if path.name != "manifest.json"
    ]
    for report in matches:
        if isinstance(report, dict) and report.get("suite") == suite:
            return report
    raise AssertionError(f"no dashboard report found for suite {suite}")


def test_seeded_dispositions_files_are_schema_valid() -> None:
    paths = sorted(DISPOSITIONS_DIR.glob("*.yaml"))
    assert paths, "expected seeded dispositions files"
    for path in paths:
        load_dispositions(path, repo_root=REPO_ROOT)


def test_seeded_wallonia_suite_shows_raw_below_explained() -> None:
    suite = "be-family-child-benefit-wallonia-social-supplement"
    report = _load_dashboard_report(suite)
    dispositions = load_dispositions(
        DISPOSITIONS_DIR / f"{suite}.yaml", repo_root=REPO_ROOT
    )
    merged = apply_dispositions(report, dispositions)
    block = merged["summary"]["dispositioned"]
    assert block["raw_match_rate"] == 25
    assert block["explained_rate"] == 100
    assert block["raw_match_rate"] < block["explained_rate"]
    assert block["unexplained_count"] == 0
    assert block["counts"]["explained_residual"] == 6


def test_seeded_belgium_lane_rollup_covers_every_mismatch() -> None:
    reports = []
    for path in sorted(DASHBOARD_DATA_DIR.glob("axiom-euromod-be-*.json")):
        report = json.loads(path.read_text())
        suite = report.get("suite")
        dispositions_path = DISPOSITIONS_DIR / f"{suite}.yaml"
        if dispositions_path.exists():
            dispositions = load_dispositions(
                dispositions_path, repo_root=REPO_ROOT
            )
            report = apply_dispositions(report, dispositions)
        reports.append(report)
    rollup = dispositioned_rollup(reports)
    assert rollup["comparison_count"] > 0
    assert rollup["raw_match_rate"] < rollup["explained_rate"]
    assert rollup["unexplained_count"] == 0
    assert rollup["explained_rate"] == 100
