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

#: TEST-OWNED copy of the reviewed slot -> (engine concept, Yale statutory
#: columns) mapping (design memo §4). Deliberately NOT derived from the
#: production ``AUTHORITY_SLOTS`` — the synthetic-value and row-verification
#: tests below build their expectations from THIS dict, so swapping two
#: mappings in the suite (e.g. MFN ↔ §122) cannot re-derive its own
#: expectation and pass (#448 review round 2). Changing the mapping means
#: changing this literal in the same reviewed diff.
_C = "us:policies/cbp/us-tariff-duty/composition"
REVIEWED_AUTHORITY_SLOTS: dict[str, tuple[str | None, tuple[str, ...]]] = {
    "mfn": (f"{_C}#mfn_ad_valorem_rate", ("statutory_base_rate",)),
    "ieepa": (
        f"{_C}#ieepa_component_rate",
        ("statutory_rate_ieepa_recip", "statutory_rate_ieepa_fent"),
    ),
    "section_122": (f"{_C}#section_122_component_rate", ("statutory_rate_s122",)),
    "section_232": (
        f"{_C}#section_232_aluminum_component_rate",
        ("statutory_rate_232",),
    ),
    "china_section_301": (
        f"{_C}#china_section_301_component_rate",
        ("statutory_rate_301",),
    ),
    "brazil_section_301": (
        f"{_C}#brazil_section_301_component_rate",
        ("statutory_rate_s301br",),
    ),
    "forced_labor_section_301": (
        f"{_C}#forced_labor_section_301_component_rate",
        ("statutory_rate_s301fl",),
    ),
    "china_semiconductor_section_301": (None, ("statutory_rate_301_cs",)),
    "section_338": (None, ("statutory_rate_s338",)),
    "section_201": (None, ("statutory_rate_section_201",)),
    "other": (None, ("statutory_rate_other",)),
}
REVIEWED_TOTAL = f"{_C}#us_tariff_total_ad_valorem_rate"


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


def test_authority_slot_mapping_is_the_reviewed_one() -> None:
    # The production mapping must equal the test-owned literal — a swap of
    # two slot mappings in the suite cannot survive this pin.
    assert AUTHORITY_SLOTS == REVIEWED_AUTHORITY_SLOTS
    assert TOTAL == REVIEWED_TOTAL
    assert MFN == REVIEWED_AUTHORITY_SLOTS["mfn"][0]


def _agreeing_values(units) -> dict[str, dict[str, float]]:
    """Synthetic engine values built from the TEST-OWNED mapping only."""
    values: dict[str, dict[str, float]] = {}
    for interval, probe in units:
        vals: dict[str, float] = {}
        for concept, yale_columns in REVIEWED_AUTHORITY_SLOTS.values():
            if concept is not None:
                vals[concept] = sum(
                    interval.rates[column] for column in yale_columns
                )
        vals[REVIEWED_TOTAL] = interval.statutory_total
        values[case_id(interval, probe)] = vals
    return values


def test_build_report_conserves_units_and_indexes_every_mismatch(reference) -> None:
    """Engine-free build_report: agreeing values everywhere except one unit
    perturbed consistently (component AND total) must yield exactly one
    unit-grain mismatch row, matching signature membership, conserved
    counts, and no internal-inconsistency flag."""
    generator = _load_generator()
    intervals, _ = reference
    units = covered_units(intervals)
    values = _agreeing_values(units)
    perturbed = case_id(*units[0])
    values[perturbed][REVIEWED_AUTHORITY_SLOTS["mfn"][0]] += 0.5
    values[perturbed][REVIEWED_TOTAL] += 0.5

    report = generator.build_report(intervals, [], units, values, {"stub": True})

    summary = report["summary"]
    assert summary["comparison_count"] == len(units) == EXPECTED_COMPARISON_UNITS
    assert summary["mismatch_count"] == 1
    assert summary["match_count"] == len(units) - 1
    assert summary["match_count"] + summary["mismatch_count"] == len(units)
    assert [r["case_id"] for r in report["mismatches"]] == [perturbed]
    assert report["mismatches"][0]["kind"] == "total_difference"
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


def test_build_report_flags_component_only_divergence(reference) -> None:
    """A component that diverges while the total agrees must still fail the
    unit (deleting the component-side unit_ok branch cannot pass) and must
    trip the engine-side component-sum consistency counter."""
    generator = _load_generator()
    intervals, _ = reference
    units = covered_units(intervals)
    values = _agreeing_values(units)
    perturbed = case_id(*units[0])
    values[perturbed][REVIEWED_AUTHORITY_SLOTS["mfn"][0]] += 0.5

    report = generator.build_report(intervals, [], units, values, {"stub": True})

    summary = report["summary"]
    assert summary["mismatch_count"] == 1
    assert summary["match_count"] == len(units) - 1
    assert [r["case_id"] for r in report["mismatches"]] == [perturbed]
    assert report["mismatches"][0]["kind"] == "component_difference"
    assert set(report["mismatches"][0]["slots"]) == {"mfn"}
    assert summary["slots"]["mfn"]["mismatches"] == 1
    assert summary["slots"]["total"]["mismatches"] == 0
    assert summary["internal_component_sum_inconsistencies"] == 1
    assert {s["authority"] for s in report["mismatch_signatures"]} == {"mfn"}


def test_build_report_flags_total_only_divergence(reference) -> None:
    """A total that diverges while every component agrees must fail the unit
    (deleting the total-side unit_ok branch cannot pass)."""
    generator = _load_generator()
    intervals, _ = reference
    units = covered_units(intervals)
    values = _agreeing_values(units)
    perturbed = case_id(*units[0])
    values[perturbed][REVIEWED_TOTAL] += 0.5

    report = generator.build_report(intervals, [], units, values, {"stub": True})

    summary = report["summary"]
    assert summary["mismatch_count"] == 1
    assert [r["case_id"] for r in report["mismatches"]] == [perturbed]
    assert report["mismatches"][0]["kind"] == "total_difference"
    assert set(report["mismatches"][0]["slots"]) == {"total"}
    assert summary["slots"]["total"]["mismatches"] == 1
    assert sum(
        counts["mismatches"]
        for slot, counts in summary["slots"].items()
        if slot != "total"
    ) == 0
    assert summary["internal_component_sum_inconsistencies"] == 1
    assert {s["authority"] for s in report["mismatch_signatures"]} == {"total"}


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


def _raw_reference_intervals() -> (
    dict[tuple[str, str], list[tuple[date, date, dict[str, float]]]]
):
    """Raw (hts10, census country) -> intervals straight from the CSV,
    parsed with the TEST-OWNED column list — no PanelInterval, no
    production column constants."""
    columns = [
        column
        for _, yale_columns in REVIEWED_AUTHORITY_SLOTS.values()
        for column in yale_columns
    ]
    intervals: dict[tuple[str, str], list[tuple[date, date, dict[str, float]]]] = {}
    with (REFERENCE_DIR / "yale_panel_slice.csv").open(newline="") as fh:
        for row in csv.DictReader(fh):
            intervals.setdefault((row["hts10"], row["country"]), []).append(
                (
                    date.fromisoformat(row["valid_from"]),
                    date.fromisoformat(row["valid_until"]),
                    {column: float(row[column]) for column in columns},
                )
            )
    return intervals


def test_committed_report_reconciles_counts_rows_and_signatures() -> None:
    """The committed full report must reconcile SEMANTICALLY, not just by
    counts and IDs (#448 review round 2): every mismatch row's expected
    values are re-derived from the committed reference extract via the
    test-owned mapping, the signature index is rebuilt from the rows, and
    the dashboard copy must be the deterministic row prefix of the full
    report — never a divergent account."""
    report = json.loads(_full_panel_report_path().read_text())
    assert "dashboard_truncation" not in report, (
        "the committed dated report must be the FULL report, not a "
        "dashboard-truncated copy"
    )
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
    assert [
        (r["hts_number"], r["country_census"], r["probe_date"]) for r in rows
    ] == sorted(
        (r["hts_number"], r["country_census"], r["probe_date"]) for r in rows
    ), "mismatch rows must be deterministically sorted"

    # Every row re-verified against the raw reference extract with the
    # test-owned mapping: the probe hits exactly one interval at a real
    # clipped endpoint, the Yale side of every delta is the test-owned
    # column sum, and every delta is a genuine beyond-tolerance divergence.
    reference_intervals = _raw_reference_intervals()
    rebuilt_signatures: dict[tuple, set[str]] = {}
    row_slot_tally: dict[str, int] = {}
    for row in rows:
        probe = date.fromisoformat(row["probe_date"])
        hits = [
            interval
            for interval in reference_intervals[
                (row["hts_number"], row["country_census"])
            ]
            if interval[0] <= probe <= interval[1]
        ]
        assert len(hits) == 1, (
            f"{row['case_id']}: probe date must land in exactly one "
            "reference interval"
        )
        valid_from, valid_until, rates = hits[0]
        assert probe in {max(valid_from, DOMAIN_START), valid_until}, (
            f"{row['case_id']}: probe is not a clipped interval endpoint"
        )
        expected_total = sum(rates.values())
        assert row["right"] == pytest.approx(expected_total, abs=1e-12), (
            f"{row['case_id']}: expected total does not match the "
            "reference extract"
        )
        assert row["difference"] == pytest.approx(
            row["left"] - row["right"], abs=1e-12
        )
        slots = row["slots"]
        assert slots, f"{row['case_id']}: mismatch row with no diverging slots"
        assert (row["kind"] == "total_difference") == ("total" in slots)
        for slot, delta in slots.items():
            if slot == "total":
                expected_slot = expected_total
                assert delta["axiom"] == row["left"]
            else:
                expected_slot = sum(
                    rates[column]
                    for column in REVIEWED_AUTHORITY_SLOTS[slot][1]
                )
            assert delta["yale"] == pytest.approx(expected_slot, abs=1e-12), (
                f"{row['case_id']}/{slot}: Yale-side delta does not match "
                "the test-owned column sum over the reference extract"
            )
            assert abs(delta["axiom"] - delta["yale"]) > 1e-12, (
                f"{row['case_id']}/{slot}: within-tolerance delta recorded "
                "as a mismatch"
            )
            row_slot_tally[slot] = row_slot_tally.get(slot, 0) + 1
            key = (
                row["hts_number"],
                slot,
                round(delta["yale"], 12),
                round(delta["axiom"], 12),
            )
            rebuilt_signatures.setdefault(key, set()).add(row["case_id"])

    # The signature index must be exactly the lossless regrouping of the
    # row-level deltas — same keys, same memberships, correct kind/concept
    # per the test-owned mapping.
    signatures = report["mismatch_signatures"]
    reported_signatures: dict[tuple, set[str]] = {}
    for signature in signatures:
        key = (
            signature["hts_number"],
            signature["authority"],
            round(signature["right"], 12),
            round(signature["left"], 12),
        )
        assert key not in reported_signatures, f"duplicate signature {key}"
        assert signature["unit_count"] == len(signature["units"])
        assert len(set(signature["units"])) == len(signature["units"])
        assert signature["difference"] == pytest.approx(
            signature["left"] - signature["right"], abs=1e-12
        )
        if signature["authority"] == "total":
            assert signature["kind"] == "total_difference"
            assert signature["concept"] == REVIEWED_TOTAL
        else:
            assert signature["kind"] == "component_difference"
            assert signature["concept"] == (
                REVIEWED_AUTHORITY_SLOTS[signature["authority"]][0]
            )
        reported_signatures[key] = set(signature["units"])
    assert reported_signatures == rebuilt_signatures, (
        "signature index must equal the lossless regrouping of the "
        "row-level deltas — nothing capped, orphaned, or misassigned"
    )
    member_ids = {cid for s in signatures for cid in s["units"]}
    assert member_ids == row_ids
    # Per-slot mismatch tallies equal BOTH independent recountings.
    for slot, counts in summary["slots"].items():
        assert counts["mismatches"] == row_slot_tally.get(slot, 0)
        assert counts["matches"] + counts["mismatches"] == (
            summary["comparison_count"]
        )
    kind_tally = {
        kind: sum(1 for r in rows if r["kind"] == kind)
        for kind in ("component_difference", "total_difference")
    }
    assert summary["mismatches_by_kind"] == [
        {"count": kind_tally[kind], "value": kind}
        for kind in ("component_difference", "total_difference")
        if kind_tally[kind]
    ]

    # The dashboard copy: identical core accounting and signatures; its
    # mismatch rows must be the DETERMINISTIC PREFIX of the full rows
    # (complete row objects, not just matching IDs), truncated only via
    # the declared dashboard_truncation block. The disposition key is
    # merged into dashboard rows downstream and is stripped before the
    # prefix comparison.
    dashboard_path = (
        REPO_ROOT / "dashboard" / "public" / "data" / "axiom-yale-us-tariff-panel.json"
    )
    dashboard = json.loads(dashboard_path.read_text())
    dash_summary = dashboard["summary"]
    for key in ("comparison_count", "match_count", "mismatch_count", "slots"):
        assert dash_summary[key] == summary[key]
    assert dashboard["mismatch_signatures"] == signatures
    dash_rows = dashboard["mismatches"]
    assert [
        {k: v for k, v in row.items() if k != "disposition"}
        for row in dash_rows
    ] == rows[: len(dash_rows)], (
        "dashboard mismatch rows must be the deterministic prefix of the "
        "full report's rows"
    )
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
