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
        targets={"axiom": "fiitax", "policyengine": "fiitax"},
    )
    comparisons = Comparator([mapping]).compare(
        [
            EngineResult("axiom", "case-1", {"fiitax": 100}),
            EngineResult("axiom", "case-2", {"fiitax": 50}),
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


@pytest.mark.parametrize("field", ["comparison_count", "match_count", "mismatch_count"])
@pytest.mark.parametrize("raw", [True, False, -1, -0.5, 1.5, float("nan"), float("inf"), "1", None])
def test_merge_rejects_invalid_summary_counts(field, raw) -> None:
    report = _build_report()
    report["summary"][field] = raw
    with pytest.raises(ValueError, match=field):
        apply_dispositions(report, _document([_entry()]))


@pytest.mark.parametrize("raw", [None, False, [], ""])
def test_merge_rejects_invalid_summary_shape(raw) -> None:
    report = _build_report()
    report["summary"] = raw
    with pytest.raises(ValueError, match="summary must be an object"):
        apply_dispositions(report, _document([_entry()]))


def test_merge_accepts_integral_float_counts() -> None:
    report = _build_report()
    for field in ("comparison_count", "match_count", "mismatch_count"):
        report["summary"][field] = float(report["summary"][field])
    merged = apply_dispositions(report, _document([_entry()]))
    assert merged["summary"]["dispositioned"]["unexplained_count"] == 0


def test_classified_rows_cannot_exceed_reported_mismatches() -> None:
    report = _build_report()
    report["summary"]["mismatch_count"] = 0
    with pytest.raises(ValueError, match="classified_rows.*exceeds mismatch_count"):
        apply_dispositions(report, _document([_entry()]))


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


def test_shared_validator_rejects_campaign_match_selector() -> None:
    # The shared schema now has its own structured `match` selector over
    # mismatch-row fields; the tariff campaign's slot-based matcher is still
    # rejected, field by field.
    entry = _entry(match={"slot": "base", "delta": {"sign": "pos"}})
    del entry["case_id"]
    errors = validate_dispositions(_document([entry]))
    assert any("match has unknown fields: ['slot']" in error for error in errors)


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


def test_axiom_encoding_gap_counts_as_explained_but_stays_broken_out() -> None:
    # Owner decision 2026-08-24: a verified encoding bug IS explained — the
    # cause is named, reproduced, and filed. It stays visible via its own
    # counts bucket (and the dashboard) until fixed upstream and
    # regenerated away; it never quietly disappears into the explained mass.
    report = _build_report()
    merged = apply_dispositions(
        report,
        _document([_entry(disposition="axiom_encoding_gap")]),
    )
    block = merged["summary"]["dispositioned"]
    assert block["raw_match_rate"] == 50
    assert block["explained_rate"] == 100
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
    paths = sorted(
        path
        for path in DISPOSITIONS_DIR.glob("*.yaml")
        if path.name != "us-tariff-schedule.yaml"
    )
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


def test_shared_apply_loader_skips_only_tariff_campaign_ledger(
    tmp_path: Path,
) -> None:
    module = _load_script_module()
    dispositions_dir = tmp_path / "dispositions"
    dispositions_dir.mkdir()
    module.REPO_ROOT = tmp_path
    module.DISPOSITIONS_DIR = dispositions_dir

    (dispositions_dir / "example-suite.yaml").write_text(
        yaml.safe_dump(_document([_entry()]))
    )
    campaign_document = {
        "schema": DISPOSITIONS_SCHEMA_VERSION,
        "suite": "us-tariff-schedule",
        "entries": [
            _entry(
                match={"slot": "base", "delta": {"sign": "pos"}},
            )
        ],
    }
    campaign_document["entries"][0].pop("case_id")
    (dispositions_dir / "us-tariff-schedule.yaml").write_text(
        yaml.safe_dump(campaign_document)
    )

    loaded, errors = module._load_dispositions_files()
    assert loaded == {"example-suite": _document([_entry()])}
    assert errors == []

    # The exception is exact: another ledger using the campaign-only matcher
    # must still fail the shared validator rather than receiving a broad skip.
    campaign_document["suite"] = "other-campaign"
    (dispositions_dir / "other-campaign.yaml").write_text(
        yaml.safe_dump(campaign_document)
    )
    loaded, errors = module._load_dispositions_files()
    assert loaded == {"example-suite": _document([_entry()])}
    assert len(errors) == 1
    assert "other-campaign.yaml" in errors[0]
    assert "match has unknown fields" in errors[0]


def _premerged_fixture(tmp_path: Path) -> tuple[object, Path, dict, dict]:
    """A tmp repo with a committed full report and its premerged-slim copy.

    Returns (script module bound to tmp_path, slim dashboard path, slim
    report, dispositions document). The full report carries TWO mismatch
    rows classified by two entries of EQUAL cardinality but different
    disposition classes — the shape whose class swap keeps every aggregate
    count identical. The slim copy embeds the
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
    # Swapping the disposition classes of
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
    # An absent source must fail --check, never
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
    # that resolves inside reports/ — must be rejected.
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
    # AttributeError.
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
    rows not retained in the dashboard sample — would go unseen.
    Two single-row entries of different classes annotate
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
        targets={"axiom": "fiitax", "policyengine": "fiitax"},
    )
    payroll = ProgramMapping(
        standard="us:test#payroll_tax",
        description="Payroll tax",
        category="tax",
        comparison="amount",
        tolerance=5,
        targets={"axiom": "tfica", "policyengine": "tfica"},
    )
    comparisons = Comparator([income, payroll]).compare(
        [
            EngineResult("axiom", "case-1", {"fiitax": 100, "tfica": 10}),
            EngineResult("axiom", "case-2", {"fiitax": 50, "tfica": 20}),
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
    # With one mismatch row per (case, concept), a
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


def test_selector_binding_violation_expires_entry_and_unclassifies_rows():
    """expires_on_source_change made real for selector entries:
    a selector_binding records the selected population's unit
    count and summed |difference|; a source change that moves any selected
    value violates the binding, EXPIRES the entry, and returns its rows to
    unexplained. Before the binding, an
    in-memory value mutation stayed classified with zero unexplained."""
    entry = {
        "id": "sel-bound",
        "concept": "x:y#z",
        "case_selector": {"case_id_prefix": "panel-a-"},
        "kind": "value",
        "disposition": "explained_residual",
        "evidence": {"mechanism": "test"},
        "expires_on_source_change": True,
    }
    report = {
        "schema_version": "axiom.comparison_report.v2",
        "summary": {
            "comparison_count": 4,
            "match_count": 2,
            "mismatch_count": 2,
        },
        "mismatches": [
            {"case_id": "panel-a-1", "concept": "x:y#z", "kind": "value",
             "left": 0.0, "right": 0.145, "difference": -0.145},
            {"case_id": "panel-a-2", "concept": "x:y#z", "kind": "value",
             "left": 0.0, "right": 0.145, "difference": -0.145},
        ],
    }
    from axiom_oracles.comparison.dispositions import (
        apply_dispositions,
        selected_rows_sha256,
    )

    entry["selector_binding"] = {
        "units": 2,
        "rows_sha256": selected_rows_sha256(report["mismatches"]),
    }
    merged = apply_dispositions(report, {"entries": [entry]})
    block = merged["summary"]["dispositioned"]
    assert block["unexplained_count"] == 0
    assert block["expired_entries"] == []
    assert "binding_violated_entries" not in block
    assert merged["mismatches"][0]["disposition"]["id"] == "sel-bound"

    # One selected row's value drifts (.145 -> .89).
    mutated = json.loads(json.dumps(report))
    mutated["mismatches"][1]["right"] = 0.99
    mutated["mismatches"][1]["difference"] = -0.89
    merged = apply_dispositions(mutated, {"entries": [entry]})
    block = merged["summary"]["dispositioned"]
    assert block["expired_entries"] == ["sel-bound"]
    assert block["binding_violated_entries"] == ["sel-bound"]
    assert block["unexplained_count"] == 2
    assert all("disposition" not in row for row in merged["mismatches"])

    # A sign flip preserves unit count and |difference|
    # aggregates — the per-row digest must still trip.
    flipped = json.loads(json.dumps(report))
    flipped["mismatches"][1]["left"] = 0.145
    flipped["mismatches"][1]["right"] = 0.0
    flipped["mismatches"][1]["difference"] = 0.145
    merged = apply_dispositions(flipped, {"entries": [entry]})
    block = merged["summary"]["dispositioned"]
    assert block["expired_entries"] == ["sel-bound"]
    assert block["binding_violated_entries"] == ["sel-bound"]
    assert block["unexplained_count"] == 2

    # Vacuity: unit-count drift alone (a selected row vanishing) also trips.
    shrunk = json.loads(json.dumps(report))
    shrunk["mismatches"] = shrunk["mismatches"][:1]
    shrunk["summary"]["mismatch_count"] = 1
    merged = apply_dispositions(shrunk, {"entries": [entry]})
    assert merged["summary"]["dispositioned"]["expired_entries"] == [
        "sel-bound"
    ]


# ---------------------------------------------------------------------------
# case_selector.case_ids_by_output: one concept can cover several compared
# outputs (fiit-ecps's EITC surface compares eleven), so a case can carry
# several rows under one concept with different mechanisms. The row-level
# selector attributes each row by its `output`.
# ---------------------------------------------------------------------------

from hypothesis import given, settings, strategies as st  # noqa: E402

from axiom_oracles.comparison.dispositions import _entry_selects_row  # noqa: E402


def _by_output_entry(mapping, **overrides):
    entry = _entry(case_selector={"case_ids_by_output": mapping}, **overrides)
    entry.pop("case_id")
    return entry


def _row(case_id, output, concept="us:test#income_tax"):
    return {"case_id": case_id, "concept": concept, "output": output}


def test_case_ids_by_output_is_valid() -> None:
    assert validate_dispositions(
        _document([_by_output_entry({"eitc_earned_income": ["c1", "c2"]})])
    ) == []


@pytest.mark.parametrize(
    "selector",
    [
        {"case_ids_by_output": {}},
        {"case_ids_by_output": {"eitc_earned_income": []}},
        {"case_ids_by_output": {"eitc_earned_income": "c1"}},
        {"case_ids_by_output": {"": ["c1"]}},
        {"case_ids_by_output": ["c1"]},
        {"case_ids_by_output": {"eitc_earned_income": ["c1"]}, "case_ids": ["c1"]},
        {"case_ids_by_output": {"x": ["c1"]}, "case_id_prefix": "c"},
    ],
)
def test_case_ids_by_output_rejects_malformed_selectors(selector) -> None:
    entry = _entry(case_selector=selector)
    entry.pop("case_id")
    errors = validate_dispositions(_document([entry]))
    assert any("case_selector" in error for error in errors), errors


def test_case_ids_by_output_selects_only_the_named_output() -> None:
    entry = _by_output_entry({"eitc_earned_income": ["c1"]})
    assert _entry_selects_row(entry, _row("c1", "eitc_earned_income"))
    # Same case and concept, another output: a different mechanism's row.
    assert not _entry_selects_row(entry, _row("c1", "eitc_investment_income_eligible"))
    assert not _entry_selects_row(entry, _row("c2", "eitc_earned_income"))
    # Outputs are matched as strings, as the binding digest identifies them.
    numeric = _by_output_entry({"1": ["c1"]})
    assert _entry_selects_row(numeric, _row("c1", 1))
    # Rows that do not name their output are never selected by output.
    assert not _entry_selects_row(entry, {"case_id": "c1", "concept": "us:test#income_tax"})
    assert not _entry_selects_row(
        entry, _row("c1", "eitc_earned_income", concept="us:test#other")
    )


def test_merge_splits_one_cases_rows_by_output() -> None:
    first = _by_output_entry(
        {"eitc_earned_income": ["c1"]}, id="earned", disposition="bridge_artifact"
    )
    second = _by_output_entry({"eitc_investment_income_eligible": ["c1"]}, id="investment")
    report = {
        "schema_version": "axiom.comparison_report.v2",
        "summary": {"comparison_count": 4, "match_count": 2, "mismatch_count": 2},
        "mismatches": [
            {**_row("c1", "eitc_earned_income"), "left": 1, "right": 2, "difference": -1},
            {**_row("c1", "eitc_investment_income_eligible"), "left": 0, "right": 1,
             "difference": -1},
        ],
    }
    merged = apply_dispositions(report, _document([first, second]))
    assert [row["disposition"]["id"] for row in merged["mismatches"]] == [
        "earned", "investment",
    ]
    counts = merged["summary"]["dispositioned"]["counts"]
    assert counts["bridge_artifact"] == 1 and counts["upstream_engine_gap"] == 1


_cases = st.sampled_from([f"c{i}" for i in range(8)])
_outputs = st.sampled_from(["a", "b", "c", "d"])


@settings(max_examples=200, deadline=None)
@given(
    mapping=st.dictionaries(_outputs, st.lists(_cases, min_size=1), min_size=1),
    rows=st.lists(st.tuples(_cases, _outputs), max_size=30),
    extra=st.lists(st.tuples(_cases, _outputs), max_size=10),
)
def test_case_ids_by_output_selects_exactly_its_pairs(mapping, rows, extra) -> None:
    """For all inputs: a row is selected iff its (case, output) pair is listed,
    and adding rows elsewhere never changes which listed rows are selected."""
    entry = _by_output_entry(mapping)
    listed = {(case, output) for output, cases in mapping.items() for case in cases}
    selected = {pair for pair in rows if _entry_selects_row(entry, _row(*pair))}
    assert selected == set(rows) & listed
    selected_with_extra = {
        pair for pair in rows + extra if _entry_selects_row(entry, _row(*pair))
    }
    assert selected_with_extra & set(rows) == selected


def _two_output_report():
    """One case, two outputs, identical values: the rows differ only in output."""
    rows = [
        {**_row("c1", output), "left": 0, "right": 1, "difference": -1,
         "kind": "amount_difference"}
        for output in ("eitc_investment_income_eligible", "eitc_demographic_eligible")
    ]
    return {
        "schema_version": "axiom.comparison_report.v2",
        "summary": {"comparison_count": 4, "match_count": 2, "mismatch_count": 2},
        "mismatches": rows,
    }


def test_digests_tell_apart_rows_that_differ_only_in_output() -> None:
    """Swapping two equal-valued rows of one case between entries changes both
    digests, so neither a selector binding nor a premerged assignment survives
    the swap (sol review of #635, finding 1)."""
    from axiom_oracles.comparison.dispositions import selected_rows_sha256

    report = _two_output_report()
    investment, age = report["mismatches"]
    assert selected_rows_sha256([investment]) != selected_rows_sha256([age])

    def merged(first_output, second_output):
        first = _by_output_entry({first_output: ["c1"]}, id="dividend",
                                 disposition="bridge_artifact")
        second = _by_output_entry({second_output: ["c1"]}, id="age")
        return apply_dispositions(report, _document([first, second]))

    straight = merged("eitc_investment_income_eligible", "eitc_demographic_eligible")
    swapped = merged("eitc_demographic_eligible", "eitc_investment_income_eligible")
    assert straight["summary"]["dispositioned"]["counts"] == (
        swapped["summary"]["dispositioned"]["counts"]
    )
    assert assignment_digest(straight) != assignment_digest(swapped)

    # A binding stamped for one output's row expires when the entry is moved
    # to the other output's equal-valued row.
    binding = {"units": 1, "rows_sha256": selected_rows_sha256([investment])}
    moved = _by_output_entry({"eitc_demographic_eligible": ["c1"]}, id="dividend",
                             selector_binding=binding)
    result = apply_dispositions(report, _document([moved]))
    assert result["summary"]["dispositioned"]["binding_violated_entries"] == ["dividend"]


def test_digests_of_rows_without_an_output_are_unchanged() -> None:
    """Output-less rows hash as before, so other suites' bindings stay valid."""
    from axiom_oracles.comparison.dispositions import selected_rows_sha256

    rows = [
        {"case_id": f"c{i}", "concept": "us:test#income_tax", "left": i, "right": 2 * i,
         "difference": -i}
        for i in range(3)
    ]
    legacy = sorted(
        [str(r["case_id"]), str(r["concept"]), json.dumps(r["left"]),
         json.dumps(r["right"]), json.dumps(r["difference"])]
        for r in rows
    )
    assert selected_rows_sha256(rows) == hashlib.sha256(
        json.dumps(legacy, separators=(",", ":")).encode()
    ).hexdigest()


@pytest.mark.parametrize("edit", ["replace", "slice", "case_ids"])
def test_a_merge_sees_same_length_in_place_selector_edits(edit) -> None:
    """Editing a selector in place between merges, without changing its length,
    reclassifies on the next merge (sol review of #635, finding 3)."""
    from axiom_oracles.comparison.dispositions import selected_rows_sha256

    report = {
        "schema_version": "axiom.comparison_report.v2",
        "summary": {"comparison_count": 2, "match_count": 1, "mismatch_count": 1},
        "mismatches": [{**_row("a", "o"), "left": 1, "right": 2, "difference": -1}],
    }
    binding = {"units": 1, "rows_sha256": selected_rows_sha256(report["mismatches"])}
    if edit == "case_ids":
        entry = _entry(case_selector={"case_ids": ["a"]}, selector_binding=binding)
        ids = entry["case_selector"]["case_ids"]
    else:
        entry = _by_output_entry({"o": ["a"]}, selector_binding=binding)
        ids = entry["case_selector"]["case_ids_by_output"]["o"]
    entry.pop("case_id", None)
    document = _document([entry])
    first = apply_dispositions(report, document)
    assert first["mismatches"][0]["disposition"]["id"] == entry["id"]

    if edit == "slice":
        ids[:] = ["b"]
    else:
        ids[0] = "b"
    second = apply_dispositions(report, document)
    assert "disposition" not in second["mismatches"][0]
    assert second["summary"]["dispositioned"]["unexplained_count"] == 1
    assert entry["id"] in second["summary"]["dispositioned"]["expired_entries"]


def test_selector_cache_sees_an_edited_selector() -> None:
    entry = _by_output_entry({"eitc_earned_income": ["c1"]})
    assert not _entry_selects_row(entry, _row("c2", "eitc_earned_income"))
    entry["case_selector"]["case_ids_by_output"]["eitc_earned_income"].append("c2")
    assert _entry_selects_row(entry, _row("c2", "eitc_earned_income"))
    plain = _entry(case_selector={"case_ids": ["c1"]})
    plain.pop("case_id")
    assert not _entry_selects_row(plain, {"case_id": "c3", "concept": "us:test#income_tax"})
    plain["case_selector"]["case_ids"].append("c3")
    assert _entry_selects_row(plain, {"case_id": "c3", "concept": "us:test#income_tax"})
    plain["case_selector"]["case_ids"][0] = "c4"
    assert not _entry_selects_row(plain, {"case_id": "c1", "concept": "us:test#income_tax"})


def test_serialize_like_keeps_the_microcosm_projector_indent(tmp_path: Path) -> None:
    """The Microcosm projector writes sorted indent-1 JSON; a merge keeps it."""

    module = _load_script_module()
    original = {"suite": "nc-income-tax-populace", "summary": {"match_count": 1}}
    text = json.dumps(original, indent=1, sort_keys=True) + "\n"
    path = tmp_path / "report.json"
    path.write_text(text)
    merged = {
        **original,
        "summary": {**original["summary"], "dispositioned": {"counts": {}}},
    }

    assert module._serialize_like(path, text, original) == text
    assert module._serialize_like(path, text, merged) == (
        json.dumps(merged, indent=1, sort_keys=True) + "\n"
    )


# --- #526: non-finite arithmetic never validates -------------------------

from hypothesis import given, settings, strategies as st  # noqa: E402

from axiom_oracles.comparison.dispositions import (  # noqa: E402
    ArithmeticEvaluationError,
    _validate_arithmetic,
)

_NON_FINITE_LITERALS = ("1e309", "-1e309", "1.5e400", "9" * 400 + ".0")
_NON_FINITE_FLOATS = (float("inf"), float("-inf"), float("nan"))


@pytest.mark.parametrize(
    "item",
    [
        # inf - inf is NaN, and every comparison with NaN is false.
        {"expression": "1e309 - 1e309", "equals": 123, "tolerance": 0},
        {"expression": "1e309", "equals": 1},
        {"expression": "1e309 * 0", "equals": 0},
        {"expression": "1", "equals": float("inf")},
        {"expression": "1", "equals": float("nan")},
        {"expression": "1", "equals": 5, "tolerance": float("inf")},
        {"expression": "1", "equals": 1, "tolerance": float("nan")},
        {"expression": "1 / 0", "equals": 0},
        {"expression": "1" + "0" * 400, "equals": 1},
        {"expression": "1", "equals": 10**400},
        # An intermediate overflows and a later step makes it finite again:
        # only a per-step finiteness check refuses these.
        {"expression": "1/(1e200*1e200)", "equals": 0},
        {"expression": "1/1e309", "equals": 0},
    ],
)
def test_non_finite_arithmetic_is_invalid(item) -> None:
    errors = _validate_arithmetic([item], "entries[0]")
    assert errors, item
    entry = _entry(evidence={"mechanism": "m", "arithmetic": [item]})
    assert validate_dispositions(_document([entry]))


_finite = st.floats(
    min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False
)


@st.composite
def _expression_with_non_finite_literal(draw) -> str:
    literal = draw(st.sampled_from(_NON_FINITE_LITERALS))
    others = draw(st.lists(_finite.map(repr), min_size=0, max_size=3))
    operators = draw(
        st.lists(
            st.sampled_from(["+", "-", "*"]),
            min_size=len(others),
            max_size=len(others),
        )
    )
    position = draw(st.integers(min_value=0, max_value=len(others)))
    operands = [*others[:position], literal, *others[position:]]
    expression = operands[0]
    for operator, operand in zip(operators, operands[1:]):
        expression = f"({expression}) {operator} ({operand})"
    return expression


@settings(max_examples=200, deadline=None)
@given(
    expression=_expression_with_non_finite_literal(),
    equals=st.one_of(_finite, st.sampled_from(_NON_FINITE_FLOATS)),
    tolerance=st.one_of(
        st.floats(min_value=0, max_value=1e300),
        st.sampled_from(_NON_FINITE_FLOATS),
    ),
)
def test_property_non_finite_literal_never_validates(
    expression, equals, tolerance
) -> None:
    # Any expression that carries a non-finite literal (1e309-style) is
    # refused, whatever it evaluates to and whatever target and tolerance
    # the entry states.
    item = {"expression": expression, "equals": equals, "tolerance": tolerance}
    assert _validate_arithmetic([item], "entries[0]")


@settings(max_examples=200, deadline=None)
@given(
    value=_finite,
    bad=st.sampled_from(["equals", "tolerance"]),
    non_finite=st.sampled_from(_NON_FINITE_FLOATS),
)
def test_property_non_finite_target_or_tolerance_never_validates(
    value, bad, non_finite
) -> None:
    item = {"expression": repr(value), "equals": value, "tolerance": 0.01}
    assert _validate_arithmetic([item], "entries[0]") == []
    item[bad] = non_finite
    assert _validate_arithmetic([item], "entries[0]")


@settings(max_examples=200, deadline=None)
@given(left=_finite, right=_finite, op=st.sampled_from(["+", "-", "*"]))
def test_property_finite_arithmetic_still_reconciles(left, right, op) -> None:
    # Control: the hardening does not reject honest finite evidence.
    expression = f"({left!r}) {op} ({right!r})"
    result = evaluate_arithmetic(expression)
    item = {"expression": expression, "equals": result, "tolerance": 0}
    assert _validate_arithmetic([item], "entries[0]") == []


# --- #521: re-applying on a premerged report clears stale labels ----------


def _premerged_report() -> tuple[dict, dict]:
    entry = _entry(pinned={"left": 100, "right": 125})
    document = _document([entry])
    premerged = apply_dispositions(_build_report(), document)
    assert premerged["mismatches"][0]["disposition"]["id"] == "example-residual"
    return premerged, document


def test_reapply_after_pin_moves_clears_stale_row_label() -> None:
    premerged, document = _premerged_report()
    moved = copy.deepcopy(premerged)
    moved["mismatches"][0]["right"] = 126
    moved["mismatches"][0]["difference"] = 26
    merged = apply_dispositions(moved, document)
    block = merged["summary"]["dispositioned"]
    assert block["expired_entries"] == ["example-residual"]
    assert block["unexplained_count"] == 1
    assert block["counts"]["unexplained"] == 1
    assert "disposition" not in merged["mismatches"][0]


def test_reapply_after_entry_deleted_clears_stale_row_label() -> None:
    premerged, _ = _premerged_report()
    merged = apply_dispositions(premerged, _document([]))
    block = merged["summary"]["dispositioned"]
    assert block["expired_entries"] == []
    assert block["unexplained_count"] == 1
    assert block["counts"]["unexplained"] == 1
    assert "disposition" not in merged["mismatches"][0]


_SUITE_ROW_KINDS = ("upstream_engine_gap", "explained_residual", "bridge_artifact")


@settings(max_examples=150, deadline=None)
@given(
    rows=st.lists(
        st.tuples(
            st.integers(min_value=-50, max_value=50),
            st.sampled_from(_SUITE_ROW_KINDS),
            st.booleans(),
        ),
        min_size=1,
        max_size=8,
    ),
    keep=st.lists(st.booleans(), min_size=8, max_size=8),
    shift=st.lists(st.integers(min_value=-2, max_value=2), min_size=8, max_size=8),
)
def test_property_reapply_equals_apply_on_raw_rows(rows, keep, shift) -> None:
    # Re-applying any (possibly edited) dispositions file to a premerged
    # report yields exactly what applying it to the raw rows yields: no row
    # label survives unless a current entry wins that row, and the
    # `unexplained` bucket equals unexplained_count.
    mismatches = [
        {
            "case_id": f"case-{i}",
            "concept": "us:test#income_tax",
            "kind": "amount",
            "left": 100,
            "right": 100 + delta + (0 if delta else 1),
            "difference": delta if delta else 1,
        }
        for i, (delta, _, _) in enumerate(rows)
    ]
    raw = {
        "suite": "example-suite",
        "summary": {
            "comparison_count": len(rows) + 1,
            "match_count": 1,
            "mismatch_count": len(rows),
        },
        "mismatches": mismatches,
    }
    entries = [
        _entry(
            id=f"entry-{i}",
            case_id=f"case-{i}",
            disposition=kind,
            pinned={"left": row["left"], "right": row["right"]} if pinned else None,
        )
        for i, ((_, kind, pinned), row) in enumerate(zip(rows, mismatches))
    ]
    for entry in entries:
        if entry["pinned"] is None:
            del entry["pinned"]
    premerged = apply_dispositions(raw, _document(entries))

    edited_raw = copy.deepcopy(raw)
    edited_premerged = copy.deepcopy(premerged)
    for target in (edited_raw, edited_premerged):
        for row, step in zip(target["mismatches"], shift):
            row["right"] += step
    survivors = [entry for entry, kept in zip(entries, keep) if kept]

    from_premerged = apply_dispositions(edited_premerged, _document(survivors))
    from_raw = apply_dispositions(edited_raw, _document(survivors))
    assert from_premerged["mismatches"] == from_raw["mismatches"]
    assert from_premerged["summary"]["dispositioned"] == (
        from_raw["summary"]["dispositioned"]
    )
    block = from_premerged["summary"]["dispositioned"]
    assert block["counts"]["unexplained"] == block["unexplained_count"]
    assert sum(block["counts"].values()) == len(rows)
    labelled = sum("disposition" in row for row in from_premerged["mismatches"])
    assert labelled == len(rows) - block["unexplained_count"]


# --- #522: policyengine-us citations must be commit-pinned ----------------

_PE_SHA = "49d19b239a593dbac8920ac6fd80cfe33372343a"
_PE_PATH = "policyengine_us/parameters/gov/usda/snap/income/deductions/rate.yaml"


@pytest.mark.parametrize(
    "url",
    [
        f"https://github.com/PolicyEngine/policyengine-us/blob/1.767.3/{_PE_PATH}",
        f"https://github.com/PolicyEngine/policyengine-us/tree/1.767.3/{_PE_PATH}",
        f"https://github.com/PolicyEngine/policyengine-us/blob/master/{_PE_PATH}",
        f"https://github.com/PolicyEngine/policyengine-us/blob/main/{_PE_PATH}",
        f"https://github.com/policyengine/POLICYENGINE-US/blob/1.767.3/{_PE_PATH}",
        f"https://www.github.com/PolicyEngine/policyengine-us/blob/1.767.3/{_PE_PATH}",
        f"http://github.com/PolicyEngine/policyengine-us/blob/v1.767.3/{_PE_PATH}",
        f"https://github.com/PolicyEngine/policyengine-us/blob/{_PE_SHA[:7]}/{_PE_PATH}",
        f"https://raw.githubusercontent.com/PolicyEngine/policyengine-us/1.767.3/{_PE_PATH}",
    ],
)
@pytest.mark.parametrize("field", ["sources", "upstream_url", "linked_issue"])
def test_policyengine_us_citation_by_moving_ref_is_invalid(url, field) -> None:
    evidence = {"mechanism": "m", "arithmetic": [{"expression": "1", "equals": 1}]}
    entry = _entry(evidence=evidence)
    if field == "sources":
        evidence["sources"] = [url]
    elif field == "upstream_url":
        evidence["upstream_url"] = url
    else:
        entry["linked_issue"] = url
    errors = validate_dispositions(_document([entry]))
    assert any("40-hex commit" in error for error in errors), errors


@pytest.mark.parametrize(
    "url",
    [
        f"https://github.com/PolicyEngine/policyengine-us/blob/{_PE_SHA}/{_PE_PATH}",
        f"https://github.com/PolicyEngine/policyengine-us/blob/{_PE_SHA}/{_PE_PATH}#L3",
        f"https://raw.githubusercontent.com/PolicyEngine/policyengine-us/{_PE_SHA}/{_PE_PATH}",
        "https://github.com/PolicyEngine/policyengine-us/issues/8614",
        "https://github.com/PolicyEngine/policyengine-us/pull/8614",
    ],
)
def test_commit_pinned_or_non_code_policyengine_us_urls_pass(url) -> None:
    evidence = {
        "mechanism": "m",
        "arithmetic": [{"expression": "1", "equals": 1}],
        "sources": [url],
        "upstream_url": url,
    }
    entry = _entry(evidence=evidence, linked_issue=url)
    assert validate_dispositions(_document([entry])) == []


@settings(max_examples=200, deadline=None)
@given(
    ref=st.text(
        alphabet="0123456789abcdefABCDEF.v-_mainster",
        min_size=1,
        max_size=45,
    ).filter(lambda ref: ref not in {".", ".."}),
    kind=st.sampled_from(["blob", "tree"]),
)
def test_property_policyengine_us_ref_must_be_full_commit(ref, kind) -> None:
    url = f"https://github.com/PolicyEngine/policyengine-us/{kind}/{ref}/{_PE_PATH}"
    evidence = {"mechanism": "m", "sources": [url]}
    errors = validate_dispositions(_document([_entry(evidence=evidence)]))
    pinned = len(ref) == 40 and all(c in "0123456789abcdef" for c in ref)
    assert (errors == []) is pinned, (ref, errors)


@pytest.mark.parametrize("expression", ["1/(1e200*1e200)", "1/1e309", "1e309 - 1e309"])
def test_evaluator_refuses_any_non_finite_intermediate(expression) -> None:
    with pytest.raises(ArithmeticEvaluationError, match="non-finite"):
        evaluate_arithmetic(expression)


@pytest.mark.parametrize("terms", [600, 5000, 200_000])
def test_deep_expression_fails_closed_instead_of_crashing(terms) -> None:
    expression = "+".join(["1"] * terms)
    with pytest.raises(ArithmeticEvaluationError):
        evaluate_arithmetic(expression)
    errors = _validate_arithmetic(
        [{"expression": expression, "equals": terms}], "entries[0]"
    )
    assert errors and "entries[0]" in errors[0]


def test_negative_tolerance_is_named_in_the_error() -> None:
    errors = _validate_arithmetic(
        [{"expression": "1", "equals": 1, "tolerance": -0.01}], "entries[0]"
    )
    assert errors == [
        "entries[0]: evidence.arithmetic[0] tolerance must be finite and >= 0"
    ]


# --- every GitHub code link must be commit-pinned (#522, hub review) ---------

_SHA = "c4307e514196618afcbf88cf7fd33746417eeabf"


@pytest.mark.parametrize(
    "url",
    [
        # Any repository, not only policyengine-us.
        "https://github.com/Budget-Lab-Yale/tariff-rate-tracker/blob/main/R/rates.R",
        "https://github.com/TheAxiomFoundation/rulespec-us/tree/v1.0/us/statutes",
        "https://raw.githubusercontent.com/PSLmodels/Tax-Calculator/master/x.py",
        # blame and commits views name a ref the same way.
        "https://github.com/Budget-Lab-Yale/tariff-rate-tracker/blame/main/R/rates.R",
        "https://github.com/PolicyEngine/policyengine-us/commits/master/policyengine_us",
        "https://github.com/PolicyEngine/policyengine-us/blame/1.767.3/x.py",
        # The singular commit view resolves a branch name too.
        "https://github.com/a/b/commit/main",
        "https://github.com/PolicyEngine/policyengine-us/commit/1.767.3",
        # Mixed-case host and path segments are still GitHub code links.
        "https://GitHub.COM/PolicyEngine/policyengine-us/BLOB/1.767.3/x.py",
        "https://RAW.GithubUserContent.com/PolicyEngine/policyengine-us/1.767.3/x.py",
    ],
)
def test_any_github_code_link_by_moving_ref_is_invalid(url) -> None:
    evidence = {"mechanism": "m", "sources": [url]}
    errors = validate_dispositions(_document([_entry(evidence=evidence)]))
    assert any("40-hex commit" in error for error in errors), errors


@pytest.mark.parametrize(
    "url",
    [
        f"https://github.com/Budget-Lab-Yale/tariff-rate-tracker/blob/{_SHA}/R/rates.R",
        f"https://github.com/Budget-Lab-Yale/tariff-rate-tracker/blame/{_SHA}/R/rates.R",
        f"https://github.com/PolicyEngine/policyengine-us/commits/{_SHA}/x",
        f"https://GitHub.com/PolicyEngine/policyengine-us/Blob/{_SHA}/x.py",
        "https://github.com/TheAxiomFoundation/rulespec-us/issues/1416",
        f"https://github.com/PolicyEngine/policyengine-us/commit/{_SHA}",
    ],
)
def test_commit_pinned_github_code_links_in_any_repository_pass(url) -> None:
    evidence = {"mechanism": "m", "sources": [url], "upstream_url": url}
    entry = _entry(evidence=evidence, linked_issue=url)
    assert validate_dispositions(_document([entry])) == []
