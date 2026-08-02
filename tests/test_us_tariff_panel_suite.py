"""Pure-logic tests for the us-tariff-panel suite against the committed
reference extract — no engine, CI-runnable.

The engine-evaluation leg is supervised (see reference/us-tariff-panel/
README.md); these tests pin the pieces CI can check: the committed extract's
integrity against its provenance stamp, the census<->ISO bridge coverage,
the temporal-domain clipping (the batch-poisoning guard), and the
authority-slot mapping invariants.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

from axiom_oracles.suites.us_tariff_panel import (
    AUTHORITY_SLOTS,
    DOMAIN_START,
    MFN,
    OUTPUTS,
    REFERENCE_DIRNAME,
    TOTAL,
    YALE_STATUTORY_COLUMNS,
    case_id,
    covered_units,
    dotted_hts,
    load_provenance,
    load_reference,
    panel_case,
    temporal_debt,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = REPO_ROOT / REFERENCE_DIRNAME

#: Reviewed universe size: 12,240 covered intervals probed at both clipped
#: endpoints, deduplicated where clipping collapses an interval to one day.
#: A Yale pin bump or coverage burn-up changes this in the same reviewed
#: diff (the reference-side EXPECTED_* pin pattern).
EXPECTED_COMPARISON_UNITS = 23_760


@pytest.fixture(scope="module")
def reference():
    return load_reference(REFERENCE_DIR)


@pytest.fixture(scope="module")
def provenance():
    return load_provenance(REFERENCE_DIR)


def test_extract_matches_its_provenance_stamp(reference, provenance) -> None:
    intervals, _ = reference
    digest = hashlib.sha256(
        (REFERENCE_DIR / "yale_panel_slice.csv").read_bytes()
    ).hexdigest()
    assert digest == provenance["extract_sha256"], (
        "yale_panel_slice.csv does not match its provenance stamp — "
        "re-run the supervised extraction, never hand-edit the extract"
    )
    assert len(intervals) == provenance["extract_rows"]
    assert len({i.country_census for i in intervals}) == (
        provenance["extract_countries"]
    )
    assert len({i.revision for i in intervals}) == provenance["extract_revisions"]


def test_covered_lines_file_matches_extract(reference, provenance) -> None:
    intervals, _ = reference
    listed = [
        line.strip()
        for line in (REFERENCE_DIR / "covered_lines.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert sorted(listed) == sorted(provenance["covered_lines"])
    assert {i.hts10 for i in intervals} == set(listed)


def test_bridge_covers_every_panel_country(reference) -> None:
    _, unbridged = reference
    # Schedule C covers all panel countries today; a drift must surface as
    # a bridge_artifact disposition, never a silent drop.
    assert unbridged == []


def test_temporal_clipping_guards_the_engine_domain(reference) -> None:
    intervals, _ = reference
    units = covered_units(intervals)
    assert units, "covered slice produced no comparison units"
    # The engine's parameter domain starts at DOMAIN_START; probing earlier
    # dates poisons the whole run-compiled batch.
    assert all(probe >= DOMAIN_START for _, probe in units)
    # Both endpoints, deduplicated when the clipped interval is one day.
    for interval, probe in units:
        assert interval.valid_from <= probe <= interval.valid_until
    # Debt + covered partitions the extract.
    debt = temporal_debt(intervals)
    covered = {id(i) for i, _ in units}
    assert all(id(i) not in covered for i in debt)
    assert len(debt) + len({id(i) for i, _ in units}) == len(intervals)


def test_covered_units_match_an_independent_endpoint_derivation(reference) -> None:
    """Derive the expected probe set straight from the raw CSV, without
    PanelInterval/covered_dates — a mutation of the shared clipping code
    (e.g. probing only the clipped start) cannot satisfy both sides."""
    expected: set[tuple[str, str, date]] = set()
    with (REFERENCE_DIR / "yale_panel_slice.csv").open(newline="") as fh:
        for row in csv.DictReader(fh):
            valid_from = date.fromisoformat(row["valid_from"])
            valid_until = date.fromisoformat(row["valid_until"])
            if valid_until < DOMAIN_START:
                continue
            expected.add(
                (row["hts10"], row["country"], max(valid_from, DOMAIN_START))
            )
            expected.add((row["hts10"], row["country"], valid_until))
    intervals, _ = reference
    units = covered_units(intervals)
    actual = {(i.hts10, i.country_census, probe) for i, probe in units}
    assert actual == expected
    # No duplicate units either: intervals tile, so endpoint probes are
    # unique across a series.
    assert len(units) == len(actual)
    assert len(actual) == EXPECTED_COMPARISON_UNITS


def _load_generator():
    path = REPO_ROOT / "scripts" / "generate_us_tariff_panel.py"
    spec = importlib.util.spec_from_file_location("generate_us_tariff_panel", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_report_conserves_units_and_indexes_every_mismatch(reference) -> None:
    """Exercise build_report engine-free: agreeing values everywhere except
    one perturbed unit must yield exactly one unit-grain mismatch row,
    matching signature membership, and conserved counts."""
    generator = _load_generator()
    intervals, _ = reference
    units = covered_units(intervals)
    values: dict[str, dict[str, float]] = {}
    for interval, probe in units:
        vals: dict[str, float] = {}
        for concept, yale_columns in AUTHORITY_SLOTS.values():
            if concept is not None:
                vals[concept] = sum(
                    interval.rates[column] for column in yale_columns
                )
        vals[TOTAL] = interval.statutory_total
        values[case_id(interval, probe)] = vals
    perturbed = case_id(*units[0])
    values[perturbed][MFN] += 0.5
    values[perturbed][TOTAL] += 0.5

    report = generator.build_report(intervals, [], units, values, {"stub": True})

    summary = report["summary"]
    assert summary["comparison_count"] == len(units) == EXPECTED_COMPARISON_UNITS
    assert summary["mismatch_count"] == 1
    assert summary["match_count"] == len(units) - 1
    assert summary["match_count"] + summary["mismatch_count"] == len(units)
    assert [r["case_id"] for r in report["mismatches"]] == [perturbed]
    assert summary["slots"]["mfn"]["mismatches"] == 1
    assert summary["slots"]["total"]["mismatches"] == 1
    assert summary["internal_component_sum_inconsistencies"] == 0
    # Signature index is lossless: every signature enumerates its members,
    # and the members are exactly the mismatched units.
    signatures = report["mismatch_signatures"]
    assert {s["authority"] for s in signatures} == {"mfn", "total"}
    for signature in signatures:
        assert signature["unit_count"] == len(signature["units"]) == 1
        assert signature["units"] == [perturbed]


def _full_panel_report_path() -> Path:
    """The single committed full (untruncated) dated report."""
    candidates = sorted(
        (REPO_ROOT / "reports").glob("axiom-yale-us-tariff-panel-all-*.json")
    )
    assert len(candidates) == 1, (
        "expected exactly one committed full panel report, found "
        f"{[p.name for p in candidates]}"
    )
    return candidates[0]


def test_committed_report_reconciles_counts_rows_and_signatures() -> None:
    """The committed full report must be internally conserved — unit
    accounting, unit-grain mismatch rows, and lossless signature
    memberships all reconcile — and the dashboard copy must be a
    declared truncation of it, never a divergent account."""
    report = json.loads(_full_panel_report_path().read_text())
    summary = report["summary"]
    assert summary["comparison_count"] == EXPECTED_COMPARISON_UNITS
    assert (
        summary["match_count"] + summary["mismatch_count"]
        == summary["comparison_count"]
    )
    rows = report["mismatches"]
    assert len(rows) == summary["mismatch_count"]
    row_ids = {row["case_id"] for row in rows}
    assert len(row_ids) == len(rows), "duplicate unit-grain mismatch rows"
    signatures = report["mismatch_signatures"]
    for signature in signatures:
        assert signature["unit_count"] == len(signature["units"])
    member_ids = {cid for s in signatures for cid in s["units"]}
    assert member_ids == row_ids, (
        "signature membership must cover exactly the mismatched units — "
        "nothing capped, nothing orphaned"
    )
    # Per-slot mismatch tallies equal the signature memberships per slot.
    per_slot_members: dict[str, int] = {}
    for signature in signatures:
        per_slot_members[signature["authority"]] = (
            per_slot_members.get(signature["authority"], 0)
            + signature["unit_count"]
        )
    for slot, counts in summary["slots"].items():
        assert counts["mismatches"] == per_slot_members.get(slot, 0)
        assert counts["matches"] + counts["mismatches"] == (
            summary["comparison_count"]
        )
    # The dashboard copy: identical core accounting and signatures; its
    # mismatch rows may be truncated but only via the declared
    # dashboard_truncation block, and only as a subset of the full rows.
    dashboard_path = (
        REPO_ROOT / "dashboard" / "public" / "data" / "axiom-yale-us-tariff-panel.json"
    )
    dashboard = json.loads(dashboard_path.read_text())
    dash_summary = dashboard["summary"]
    for key in ("comparison_count", "match_count", "mismatch_count", "slots"):
        assert dash_summary[key] == summary[key]
    assert dashboard["mismatch_signatures"] == signatures
    dash_rows = dashboard["mismatches"]
    dash_ids = {row["case_id"] for row in dash_rows}
    assert len(dash_ids) == len(dash_rows)
    assert dash_ids <= row_ids, "dashboard rows must come from the full report"
    truncation = dashboard.get("dashboard_truncation")
    if len(dash_rows) < summary["mismatch_count"]:
        assert truncation is not None, (
            "truncated dashboard copy must declare dashboard_truncation"
        )
    if truncation is not None:
        assert truncation["shown_mismatches"] == len(dash_rows)
        assert truncation["total_mismatches"] == summary["mismatch_count"]


def test_authority_slots_partition_the_statutory_columns() -> None:
    # Every Yale statutory column feeds exactly one slot (the statutory
    # total is the sum of all of them), so no reference rate can be
    # silently dropped from the comparison.
    used = [
        column
        for _, columns in AUTHORITY_SLOTS.values()
        for column in columns
    ]
    assert sorted(used) == sorted(YALE_STATUTORY_COLUMNS)
    # Slots with an encoded counterpart request it from the engine.
    for concept, _ in AUTHORITY_SLOTS.values():
        if concept is not None:
            assert concept in OUTPUTS
    assert TOTAL in OUTPUTS


def test_statutory_total_is_column_sum(reference) -> None:
    intervals, _ = reference
    sample = intervals[0]
    assert sample.statutory_total == pytest.approx(
        sum(sample.rates[c] for c in YALE_STATUTORY_COLUMNS)
    )


def test_spot_cell_china_9506624040(reference) -> None:
    # Frozen spot verification (probed directly against the rds during
    # design): CN (census 5700) x 9506.62.40.40, interval 2026-02-24..
    # 03-31 — MFN free, China §301 7.5%, §122 10% after the IEEPA
    # termination.
    intervals, _ = reference
    cell = next(
        i
        for i in intervals
        if i.hts10 == "9506624040"
        and i.country_census == "5700"
        and i.valid_from == date(2026, 2, 24)
    )
    assert cell.iso2 == "CN"
    assert cell.rates["statutory_base_rate"] == 0.0
    assert cell.rates["statutory_rate_301"] == 0.075
    assert cell.rates["statutory_rate_s122"] == 0.1
    assert cell.statutory_total == pytest.approx(0.175)


def test_panel_case_shape(reference) -> None:
    intervals, _ = reference
    interval = next(i for i in intervals if i.covered_dates)
    probe = interval.covered_dates[0]
    case = panel_case(interval, probe)
    assert case.period == probe.isoformat()
    assert case.outputs == OUTPUTS
    inputs = case.metadata["axiom_inputs"]
    line = dotted_hts(interval.hts10)
    assert inputs[
        "us:policies/cbp/us-tariff-duty/composition#input.hts_number"
    ] == line
    assert inputs[
        "us:policies/cbp/us-tariff-duty/composition#input.country_of_origin"
    ] == interval.iso2
    assert inputs[
        "us:policies/cbp/us-tariff-duty/composition#input.is_postal_shipment"
    ] is False


def test_dotted_hts() -> None:
    assert dotted_hts("9506624040") == "9506.62.40.40"


def test_committed_report_provenance_pins_the_committed_extract(provenance) -> None:
    # The committed dashboard report must have been generated against the
    # committed reference — the ENTIRE embedded provenance object must
    # equal the committed one, not just the extract sha and Yale pin
    # (field-subset checks let extractor-sha/attestation drift break the
    # audit lineage silently — #448 review).
    report_path = (
        REPO_ROOT / "dashboard" / "public" / "data" / "axiom-yale-us-tariff-panel.json"
    )
    if not report_path.exists():
        pytest.skip("panel report not yet published")
    report = json.loads(report_path.read_text())
    # The run_comparison chain replaces the provenance block with runner
    # provenance, so the reference vintage is pinned under scope.
    assert report["scope"]["reference"] == provenance, (
        "embedded reference provenance differs from the committed "
        "yale_panel_provenance.json — regenerate the report derivatives"
    )
    # Same lineage requirement for every committed reports/ derivative.
    for reports_path in sorted(
        (REPO_ROOT / "reports").glob("axiom-yale-us-tariff-panel-*.json")
    ):
        dated = json.loads(reports_path.read_text())
        assert dated["scope"]["reference"] == provenance, (
            f"{reports_path.name} embeds a reference provenance that "
            "differs from the committed yale_panel_provenance.json"
        )
