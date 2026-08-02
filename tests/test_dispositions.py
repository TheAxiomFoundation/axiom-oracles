import copy
import hashlib
import importlib.util
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
    assignment_digest,
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
    # Every BE mismatch is classified (none unexplained). explained_rate is now
    # 100: the be-pensioner-contributions suite that once carried the tscpe_be
    # axiom_encoding_gap residuals (the article 191 health-floor and article 68
    # solidarity base-table gaps, rulespec-be#89) now matches EUROMOD exactly
    # (6/6), so no BE mismatch remains to classify. raw_match_rate stays below
    # explained because other BE suites still carry dispositioned residuals.
    assert rollup["unexplained_count"] == 0
    assert rollup["explained_rate"] == 100


# ---------------------------------------------------------------------------
# apply_dispositions.py script: premerged-slim block validation (F2)
# ---------------------------------------------------------------------------


def _load_script_module():
    path = REPO_ROOT / "scripts" / "apply_dispositions.py"
    spec = importlib.util.spec_from_file_location(
        "apply_dispositions_script", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _premerged_fixture(tmp_path: Path) -> tuple[object, Path, dict, dict]:
    """A tmp repo with a committed full report and its premerged-slim copy.

    Returns (script module bound to tmp_path, slim dashboard path, slim
    report, dispositions document). The full report carries TWO mismatch
    rows classified by two entries of EQUAL cardinality but different
    disposition classes — the shape whose class swap keeps every aggregate
    count identical (sol stack review r2). The slim copy embeds the
    ``summary.dispositioned`` block a fresh merge over the full report
    produces, bound to its source via the ``source_report`` pointer and
    the row-level ``assignment_sha256``, and retains one annotated
    mismatch row — the exact shape the panel generator writes.
    """

    module = _load_script_module()
    module.REPO_ROOT = tmp_path

    doc = _document(
        [
            _entry(linked_issue="https://example.org/upstream/1"),
            _entry(
                id="example-axiom-gap",
                case_id="case-2",
                disposition="axiom_encoding_gap",
                evidence={
                    "mechanism": "Our encoding misses a component.",
                    "arithmetic": [
                        {"expression": "75 - 50", "equals": 25}
                    ],
                },
            ),
        ]
    )
    full = _build_report(right_values=(125, 75))
    merged = apply_dispositions(
        full, doc, dispositions_file="dispositions/example-suite.yaml"
    )
    assert merged["summary"]["mismatch_count"] == 2

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    full_path = reports_dir / "example-suite-full.json"
    full_path.write_text(json.dumps(full, indent=2))

    slim = copy.deepcopy(merged)
    slim["schema_version"] = DISPOSITIONED_REPORT_SCHEMA_VERSION
    slim["summary"]["stored_mismatch_example_count"] = 1
    slim["mismatches"] = [copy.deepcopy(merged["mismatches"][0])]
    block = slim["summary"]["dispositioned"]
    block["source_report"] = {
        "path": "reports/example-suite-full.json",
        "sha256": hashlib.sha256(full_path.read_bytes()).hexdigest(),
    }
    block["assignment_sha256"] = assignment_digest(merged)
    dashboard_dir = tmp_path / "dashboard" / "public" / "data"
    dashboard_dir.mkdir(parents=True)
    slim_path = dashboard_dir / "example-suite.json"
    slim_path.write_text(json.dumps(slim, indent=2))

    assert module._is_premerged_slim_report(slim)
    return module, slim_path, slim, doc


def test_premerged_block_matching_full_report_merge_passes(
    tmp_path: Path,
) -> None:
    module, slim_path, slim, doc = _premerged_fixture(tmp_path)
    assert module._premerged_block_problems(slim_path, slim, doc) == []


def test_hand_edited_premerged_block_is_flagged(tmp_path: Path) -> None:
    module, slim_path, slim, doc = _premerged_fixture(tmp_path)
    slim["summary"]["dispositioned"]["raw_match_rate"] = 95
    problems = module._premerged_block_problems(slim_path, slim, doc)
    assert problems
    assert "does not match a fresh dispositions merge" in problems[0]


def test_reclassified_dispositions_entry_is_flagged(tmp_path: Path) -> None:
    # The embedded block was computed while the entry explained the
    # mismatch as an upstream engine gap; reclassifying it (or deleting
    # it) must fail --check instead of riding the trusted-block bypass.
    module, slim_path, slim, doc = _premerged_fixture(tmp_path)
    reclassified = copy.deepcopy(doc)
    reclassified["entries"][0]["disposition"] = "axiom_encoding_gap"
    problems = module._premerged_block_problems(
        slim_path, slim, reclassified
    )
    assert problems
    assert "does not match a fresh dispositions merge" in problems[0]

    deleted = copy.deepcopy(doc)
    deleted["entries"] = []
    assert module._premerged_block_problems(slim_path, slim, deleted)


def _strip_binding_keys(slim: dict) -> None:
    """Represent a population-diagnostic block that predates pointers."""

    block = slim["summary"]["dispositioned"]
    for key in ("source_report", "assignment_sha256"):
        block.pop(key, None)


def test_suite_without_committed_full_report_keeps_trusted_block(
    tmp_path: Path,
) -> None:
    # Population diagnostics that store aggregates only have nothing to
    # re-derive from and no pointer; the embedded block stays trusted.
    module, slim_path, slim, doc = _premerged_fixture(tmp_path)
    _strip_binding_keys(slim)
    (tmp_path / "reports" / "example-suite-full.json").unlink()
    slim["summary"]["dispositioned"]["unexplained_count"] = 99
    assert module._premerged_block_problems(slim_path, slim, doc) == []


def test_partial_reports_are_not_full_merge_targets(tmp_path: Path) -> None:
    # A committed report whose stored mismatch rows undercount its summary
    # is itself a trimmed copy — re-deriving from it would undercount, so
    # it must not qualify as a full report for an unpointered block.
    module, slim_path, slim, doc = _premerged_fixture(tmp_path)
    _strip_binding_keys(slim)
    full_path = tmp_path / "reports" / "example-suite-full.json"
    partial = json.loads(full_path.read_text())
    partial["mismatches"] = []
    full_path.write_text(json.dumps(partial))
    assert module._committed_full_reports("example-suite") == []
    slim["summary"]["dispositioned"]["unexplained_count"] = 99
    assert module._premerged_block_problems(slim_path, slim, doc) == []


def test_equal_cardinality_class_swap_is_flagged(tmp_path: Path) -> None:
    # Sol stack review r2 F2 residual: swapping the disposition classes of
    # two equal-cardinality entries keeps EVERY aggregate count identical,
    # so the aggregate comparison stays silent — the row-level assignment
    # digest and the retained row's annotation must catch it.
    module, slim_path, slim, doc = _premerged_fixture(tmp_path)
    swapped = copy.deepcopy(doc)
    assert swapped["entries"][0]["disposition"] == "upstream_engine_gap"
    assert swapped["entries"][1]["disposition"] == "axiom_encoding_gap"
    swapped["entries"][0]["disposition"] = "axiom_encoding_gap"
    swapped["entries"][1]["disposition"] = "upstream_engine_gap"
    problems = module._premerged_block_problems(slim_path, slim, swapped)
    assert problems
    # The aggregate block really is identical under the swap — the digest
    # and the retained-row annotation are what flag it.
    assert not any(
        "embeds a summary.dispositioned block" in problem
        for problem in problems
    )
    assert any("assignment_sha256" in problem for problem in problems)
    assert any("retained mismatch row" in problem for problem in problems)


def test_retained_row_annotation_drift_is_flagged(tmp_path: Path) -> None:
    # Hand-editing the annotation on a retained mismatch row (dashboard
    # copy only) leaves aggregates and the embedded digest untouched; the
    # per-row comparison against the fresh merge must flag it.
    module, slim_path, slim, doc = _premerged_fixture(tmp_path)
    slim["mismatches"][0]["disposition"]["disposition"] = (
        "axiom_encoding_gap"
    )
    problems = module._premerged_block_problems(slim_path, slim, doc)
    assert problems
    assert any(
        "retained mismatch row" in problem
        and "does not match the fresh merge" in problem
        for problem in problems
    )


def test_missing_pointer_with_committed_full_report_is_flagged(
    tmp_path: Path,
) -> None:
    # A suite that commits a full report may not ship an unbound dashboard
    # block: the block still validates against every committed full report
    # but the missing pointer itself is a problem.
    module, slim_path, slim, doc = _premerged_fixture(tmp_path)
    _strip_binding_keys(slim)
    problems = module._premerged_block_problems(slim_path, slim, doc)
    assert problems
    assert any(
        "lacks a source_report pointer" in problem for problem in problems
    )


def test_dangling_source_pointer_fails_closed(tmp_path: Path) -> None:
    # Sol stack review r2 MED: an absent source must fail --check, never
    # fall back to trusting the embedded block.
    module, slim_path, slim, doc = _premerged_fixture(tmp_path)
    (tmp_path / "reports" / "example-suite-full.json").unlink()
    slim["summary"]["dispositioned"]["unexplained_count"] = 99
    problems = module._premerged_block_problems(slim_path, slim, doc)
    assert problems
    assert any("is missing" in problem for problem in problems)


def test_source_pointer_sha_mismatch_is_flagged(tmp_path: Path) -> None:
    # Editing the committed full report without refreshing the dashboard
    # copy breaks the hash binding and fails closed.
    module, slim_path, slim, doc = _premerged_fixture(tmp_path)
    full_path = tmp_path / "reports" / "example-suite-full.json"
    full_path.write_text(full_path.read_text() + "\n")
    problems = module._premerged_block_problems(slim_path, slim, doc)
    assert problems
    assert any("sha256 mismatch" in problem for problem in problems)


def test_source_pointer_to_partial_report_fails_closed(
    tmp_path: Path,
) -> None:
    # Re-pointing the block at a trimmed report (hash updated to match)
    # must fail: a partial source cannot re-derive the full merge.
    module, slim_path, slim, doc = _premerged_fixture(tmp_path)
    full_path = tmp_path / "reports" / "example-suite-full.json"
    partial = json.loads(full_path.read_text())
    partial["mismatches"] = partial["mismatches"][:1]
    payload = json.dumps(partial, indent=2)
    full_path.write_text(payload)
    slim["summary"]["dispositioned"]["source_report"]["sha256"] = (
        hashlib.sha256(payload.encode("utf-8")).hexdigest()
    )
    problems = module._premerged_block_problems(slim_path, slim, doc)
    assert problems
    assert any("not a FULL report" in problem for problem in problems)


def test_source_pointer_outside_reports_dir_is_rejected(
    tmp_path: Path,
) -> None:
    module, slim_path, slim, doc = _premerged_fixture(tmp_path)
    slim["summary"]["dispositioned"]["source_report"]["path"] = (
        "../outside.json"
    )
    problems = module._premerged_block_problems(slim_path, slim, doc)
    assert problems
    assert any("outside reports/" in problem for problem in problems)


def test_absolute_source_pointer_path_is_rejected(tmp_path: Path) -> None:
    # The pointer contract is repo-relative; an absolute path — even one
    # that resolves inside reports/ — must be rejected (sol stack review
    # r3).
    module, slim_path, slim, doc = _premerged_fixture(tmp_path)
    slim["summary"]["dispositioned"]["source_report"]["path"] = str(
        tmp_path / "reports" / "example-suite-full.json"
    )
    problems = module._premerged_block_problems(slim_path, slim, doc)
    assert problems
    assert any("must be repo-relative" in problem for problem in problems)


def test_non_mapping_json_source_is_a_problem_not_a_crash(
    tmp_path: Path,
) -> None:
    # A hash-matching source whose JSON is valid but not a report object
    # (e.g. a bare list) must produce a validation problem, not an
    # AttributeError (sol stack review r3).
    module, slim_path, slim, doc = _premerged_fixture(tmp_path)
    full_path = tmp_path / "reports" / "example-suite-full.json"
    payload = "[1]"
    full_path.write_text(payload)
    slim["summary"]["dispositioned"]["source_report"]["sha256"] = (
        hashlib.sha256(payload.encode("utf-8")).hexdigest()
    )
    problems = module._premerged_block_problems(slim_path, slim, doc)
    assert problems
    assert any(
        "is not a example-suite report" in problem for problem in problems
    )


def _premerged_multi_concept_fixture(
    tmp_path: Path,
) -> tuple[object, Path, dict, dict]:
    """Premerged fixture where each case carries TWO mismatch rows.

    A report validly emits one mismatch row per (case, concept); a digest
    or row map keyed by case_id alone collapses same-case rows, so a
    count-preserving swap confined to rows shadowed in that map — and to
    rows not retained in the dashboard sample — would go unseen (sol
    stack review r3). Two single-row entries of different classes annotate
    the income-tax row of each case; the payroll rows stay unannotated,
    and the retained dashboard row is an unannotated payroll row.
    """

    module = _load_script_module()
    module.REPO_ROOT = tmp_path

    income = ProgramMapping(
        standard="us:test#income_tax",
        description="Federal income tax",
        category="tax",
        comparison="amount",
        tolerance=5,
        targets={"taxsim": "fiitax", "policyengine": "fiitax"},
    )
    payroll = ProgramMapping(
        standard="us:test#payroll_tax",
        description="Payroll tax",
        category="tax",
        comparison="amount",
        tolerance=5,
        targets={"taxsim": "tfica", "policyengine": "tfica"},
    )
    comparisons = Comparator([income, payroll]).compare(
        [
            EngineResult("taxsim", "case-1", {"fiitax": 100, "tfica": 10}),
            EngineResult("taxsim", "case-2", {"fiitax": 50, "tfica": 20}),
        ],
        [
            EngineResult(
                "policyengine", "case-1", {"fiitax": 125, "tfica": 40}
            ),
            EngineResult(
                "policyengine", "case-2", {"fiitax": 75, "tfica": 50}
            ),
        ],
    )
    full = build_comparison_report(
        suite_name="example-suite",
        population="synthetic",
        locales=set(),
        scope=None,
        cases=[
            Case(case_id="case-1", period="2026"),
            Case(case_id="case-2", period="2026"),
        ],
        mappings=[income, payroll],
        comparisons=comparisons,
    )
    doc = _document(
        [
            _entry(linked_issue="https://example.org/upstream/1"),
            _entry(
                id="example-axiom-gap",
                case_id="case-2",
                disposition="axiom_encoding_gap",
                evidence={
                    "mechanism": "Our encoding misses a component.",
                    "arithmetic": [{"expression": "75 - 50", "equals": 25}],
                },
            ),
        ]
    )
    merged = apply_dispositions(
        full, doc, dispositions_file="dispositions/example-suite.yaml"
    )
    assert merged["summary"]["mismatch_count"] == 4
    rows = merged["mismatches"]
    assert [
        (row["case_id"], row["concept"], row.get("disposition") is not None)
        for row in rows
    ] == [
        ("case-1", "us:test#income_tax", True),
        ("case-1", "us:test#payroll_tax", False),
        ("case-2", "us:test#income_tax", True),
        ("case-2", "us:test#payroll_tax", False),
    ]

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    full_path = reports_dir / "example-suite-full.json"
    full_path.write_text(json.dumps(full, indent=2))

    slim = copy.deepcopy(merged)
    slim["schema_version"] = DISPOSITIONED_REPORT_SCHEMA_VERSION
    slim["summary"]["stored_mismatch_example_count"] = 1
    # Retain ONLY the unannotated case-1 payroll row: the mutant below is
    # confined to non-retained rows.
    slim["mismatches"] = [copy.deepcopy(rows[1])]
    block = slim["summary"]["dispositioned"]
    block["source_report"] = {
        "path": "reports/example-suite-full.json",
        "sha256": hashlib.sha256(full_path.read_bytes()).hexdigest(),
    }
    block["assignment_sha256"] = assignment_digest(merged)
    dashboard_dir = tmp_path / "dashboard" / "public" / "data"
    dashboard_dir.mkdir(parents=True)
    slim_path = dashboard_dir / "example-suite.json"
    slim_path.write_text(json.dumps(slim, indent=2))

    assert module._is_premerged_slim_report(slim)
    assert module._premerged_block_problems(slim_path, slim, doc) == []
    return module, slim_path, slim, doc


def test_same_case_multi_concept_swap_is_flagged(tmp_path: Path) -> None:
    # Sol stack review r3: with one mismatch row per (case, concept), a
    # case_id-keyed digest lets later concept rows shadow earlier ones, so
    # swapping the classes of two single-row entries that annotate only
    # shadowed, non-retained rows preserved aggregates, digest, and
    # retained annotations. The row-identity digest must catch it.
    module, slim_path, slim, doc = _premerged_multi_concept_fixture(tmp_path)
    swapped = copy.deepcopy(doc)
    assert swapped["entries"][0]["disposition"] == "upstream_engine_gap"
    assert swapped["entries"][1]["disposition"] == "axiom_encoding_gap"
    swapped["entries"][0]["disposition"] = "axiom_encoding_gap"
    swapped["entries"][1]["disposition"] = "upstream_engine_gap"
    problems = module._premerged_block_problems(slim_path, slim, swapped)
    assert problems
    # Aggregates and the retained (unannotated) row are unchanged by the
    # swap — only the digest can flag it.
    assert not any(
        "embeds a summary.dispositioned block" in problem
        for problem in problems
    )
    assert not any("retained mismatch row" in problem for problem in problems)
    assert any("assignment_sha256" in problem for problem in problems)


def test_merge_reports_check_flags_premerged_drift(tmp_path: Path) -> None:
    # End-to-end through _merge_reports: the premerged branch must route
    # through the block validation in check mode, not trust-and-continue.
    module, slim_path, slim, doc = _premerged_fixture(tmp_path)
    slim["summary"]["dispositioned"]["raw_match_rate"] = 95
    slim_path.write_text(json.dumps(slim, indent=2))
    module.DASHBOARD_DATA_DIR = slim_path.parent
    problems, _, changed = module._merge_reports(
        {"example-suite": doc}, check=True
    )
    assert changed is False
    assert any(
        "does not match a fresh dispositions merge" in problem
        for problem in problems
    )


def test_panel_dashboard_block_is_bound_to_committed_full_report() -> None:
    # Committed-artifact pin: the panel's dashboard copy must bind to its
    # committed full report (pointer path + sha256) and reproduce the
    # row-level assignment digest under a fresh merge — the fail-closed
    # ladder validated end-to-end on the real artifacts.
    module = _load_script_module()
    slim_path = DASHBOARD_DATA_DIR / "axiom-yale-us-tariff-panel.json"
    slim = json.loads(slim_path.read_text())
    assert module._is_premerged_slim_report(slim)
    pointer = slim["summary"]["dispositioned"]["source_report"]
    full_path = REPO_ROOT / pointer["path"]
    assert full_path.is_file()
    assert (
        hashlib.sha256(full_path.read_bytes()).hexdigest()
        == pointer["sha256"]
    )
    doc = load_dispositions(
        DISPOSITIONS_DIR / "us-tariff-panel.yaml", repo_root=REPO_ROOT
    )
    assert module._premerged_block_problems(slim_path, slim, doc) == []
