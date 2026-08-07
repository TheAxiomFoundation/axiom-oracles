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
from datetime import date, timedelta
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
    column_exposure,
    covered_units,
    dotted_hts,
    load_provenance,
    load_reference,
    panel_case,
    straddle_clipped,
    temporal_debt,
    temporal_debt_records,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = REPO_ROOT / REFERENCE_DIRNAME

#: Reviewed universe size: 20,400 covered intervals probed at both clipped
#: endpoints, deduplicated where clipping collapses an interval to one day.
#: A Yale pin bump or coverage burn-up changes this in the same reviewed
#: diff (the reference-side EXPECTED_* pin pattern).
EXPECTED_COMPARISON_UNITS = 39_600

#: Reviewed OUTCOME pins for the committed artifacts (#448 review round 3):
#: without these, an artifact relabelling mismatches as matches — or a
#: 23,760-match/0-mismatch account — reconciles internally and passes.
#: An encoding fix or reference-vintage change moves these in the same
#: reviewed diff.
EXPECTED_MATCH_COUNT = 24_400
EXPECTED_MISMATCH_COUNT = 15_200
EXPECTED_SIGNATURE_COUNT = 87

#: Reviewed sha256 of the committed report's canonical ACCOUNT — the
#: {summary, mismatches, mismatch_signatures, cases} sections serialized
#: with sort_keys and compact separators (#448 review round 4). The count
#: pins above constrain totals; this pin binds mismatch IDENTITY and the
#: Axiom-side values, so relocating a genuine mismatch onto a
#: previously-matching unit with the same Yale vector (consistent
#: signature/family rewrites included) cannot reconcile. A genuine
#: encoding or reference change moves this in the same reviewed diff.
EXPECTED_ACCOUNT_SHA256 = (
    "0a326bcd9e1f47ac95d49d9877b9ae9054f648cc40409757deb3d6be24f26d62"
)

#: Reviewed positive-exposure counts per Yale statutory column: the number
#: of comparison units whose REFERENCE value for the column is positive.
#: This is the witness basis for the conformance scoreboard's covered
#: verdicts (sol stack review F3): a policy whose columns are 0 everywhere
#: in the covered slice (301_cs, other) is exercised by NOTHING —
#: "covered" for it is vacuous, and the scoreboard must say uncovered.
#: A Yale pin bump or coverage burn-up moves these in the same reviewed
#: diff.
EXPECTED_COLUMN_EXPOSURE = {
    "statutory_base_rate": 15_840,
    "statutory_rate_232": 9_840,
    "statutory_rate_ieepa_recip": 1_906,
    "statutory_rate_ieepa_fent": 40,
    "statutory_rate_301": 165,
    "statutory_rate_301_cs": 0,
    "statutory_rate_s301fl": 2_580,
    "statutory_rate_s301br": 36,
    "statutory_rate_s338": 6,
    "statutory_rate_s122": 18_240,
    "statutory_rate_section_201": 7_887,
    "statutory_rate_other": 0,
}

#: Reviewed temporal-debt account (sol stack review F4): intervals wholly
#: before the encoded domain (no probes at all) plus intervals straddling
#: the boundary (probed, but their pre-domain days are unaudited). Every
#: unit is addressable via scope.temporal_debt.records; these totals move
#: only with a domain burn-down or Yale pin bump, in the same reviewed diff.
EXPECTED_PRE_DOMAIN_INTERVALS = 48_000
EXPECTED_STRADDLE_CLIPPED_INTERVALS = 1_200
EXPECTED_PRE_DOMAIN_RECORD_GROUPS = 200
EXPECTED_STRADDLE_RECORD_GROUPS = 5

#: Reviewed dashboard truncation cap (run_comparison._DASHBOARD_MAX_MISMATCHES)
#: — the dashboard copy must carry EXACTLY min(cap, mismatch_count) rows, not
#: any self-declared prefix length.
DASHBOARD_MAX_MISMATCHES = 1_000

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
    "section_338": (f"{_C}#section_338_component_rate", ("statutory_rate_s338",)),
    "section_201": (
        f"{_C}#section_201_component_rate",
        ("statutory_rate_section_201",),
    ),
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
    # Account digest pin: byte-level identity of the four account
    # sections. Everything below re-derives structure; this closes the
    # remaining relabelling family (round 4) where an internally
    # consistent mutant relocates a mismatch between same-Yale-vector
    # units without moving any count.
    account = {
        key: report[key]
        for key in ("summary", "mismatches", "mismatch_signatures", "cases")
    }
    account_sha256 = hashlib.sha256(
        json.dumps(account, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert account_sha256 == EXPECTED_ACCOUNT_SHA256, (
        "committed report account sections do not match the reviewed "
        "digest — mismatch identity or values changed outside a reviewed "
        "pin bump"
    )
    summary = report["summary"]
    assert summary["comparison_count"] == EXPECTED_COMPARISON_UNITS
    # Reviewed outcome pins: internal reconciliation alone cannot prove
    # fullness (a relabelled or all-match account reconciles too).
    assert summary["match_count"] == EXPECTED_MATCH_COUNT
    assert summary["mismatch_count"] == EXPECTED_MISMATCH_COUNT
    assert (
        summary["match_count"] + summary["mismatch_count"]
        == summary["comparison_count"]
    )
    # The per-slot ledger must carry the ENTIRE reviewed slot universe —
    # deleting an authority from summary.slots must not pass.
    assert set(summary["slots"]) == set(REVIEWED_AUTHORITY_SLOTS) | {"total"}
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
        # The unit identity is BOUND to the cell coordinates (test-owned
        # format) — arbitrary unique ids cannot stand in for real units.
        assert row["case_id"] == (
            f"panel-{row['hts_number']}-{row['country_census']}-"
            f"{row['probe_date']}"
        )
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
        if "total" not in slots:
            # component_difference means the components cancelled in the
            # total: the top-level totals must actually agree.
            assert abs(row["left"] - row["right"]) <= 1e-12, (
                f"{row['case_id']}: component_difference row with a "
                "diverging total"
            )
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
    assert len(signatures) == EXPECTED_SIGNATURE_COUNT
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

    # The complete case-family ledger must reconcile against the summary
    # and the mismatch rows: every unit lives in a family, each family's
    # match flag equals its own vector agreement, non-matching family
    # units total exactly the mismatch count, and every mismatch row is
    # covered by a non-matching family cell.
    families = report["cases"]
    family_units = 0
    family_mismatch_units = 0
    mismatch_family_cells: dict[str, list[tuple[set, set]]] = {}
    for family in families:
        assert set(family["expected"]) == set(family["axiom"]) == (
            set(REVIEWED_AUTHORITY_SLOTS) | {"total"}
        )
        vectors_agree = all(
            abs(family["axiom"][slot] - family["expected"][slot]) <= 1e-12
            for slot in family["expected"]
        )
        assert family["match"] == vectors_agree, (
            f"{family['case_id']}: match flag contradicts its own vectors"
        )
        assert family["unit_count"] > 0
        family_units += family["unit_count"]
        if not vectors_agree:
            family_mismatch_units += family["unit_count"]
            mismatch_family_cells.setdefault(
                family["hts_number"], []
            ).append(
                (set(family["countries"]), set(family["probe_dates"]))
            )
    assert family_units == summary["comparison_count"]
    assert family_mismatch_units == summary["mismatch_count"]
    for row in rows:
        cells = mismatch_family_cells.get(row["hts_number"]) or []
        assert any(
            row["country_census"] in countries
            and row["probe_date"] in probes
            for countries, probes in cells
        ), f"{row['case_id']}: no covering non-matching case family"

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
    # Exactly the reviewed cap — a shorter self-declared prefix (1 row with
    # matching shown_mismatches) must not pass.
    assert len(dash_rows) == min(
        DASHBOARD_MAX_MISMATCHES, summary["mismatch_count"]
    )
    assert [
        {k: v for k, v in row.items() if k != "disposition"}
        for row in dash_rows
    ] == rows[: len(dash_rows)], (
        "dashboard mismatch rows must be the deterministic prefix of the "
        "full report's rows"
    )
    # Case-family evidence must survive publication (#448 review round
    # 4): the panel's family ledger fits under the case cap, so the
    # dashboard must carry ALL committed families verbatim — not zero
    # rows dropped by an ID-set filter keyed to mismatch rows.
    assert dashboard["cases"] == families, (
        "dashboard case-family ledger must equal the full report's"
    )
    truncation = dashboard.get("dashboard_truncation")
    if len(dash_rows) < summary["mismatch_count"]:
        assert truncation is not None, (
            "truncated dashboard copy must declare dashboard_truncation"
        )
    if truncation is not None:
        assert truncation["shown_mismatches"] == len(dash_rows)
        assert truncation["total_mismatches"] == summary["mismatch_count"]
        assert truncation["shown_case_rows"] == len(dashboard["cases"])
        assert truncation["total_case_rows"] == len(families)


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


def test_panel_stays_on_the_manual_ci_lane() -> None:
    """Standard CI neither builds the Rust rules engine nor exports
    AXIOM_RULES_ENGINE_BINARY, so a matrix or affected-rerun dispatch of
    this suite could only ever take the HEAD re-emit path — a permanently
    stale lane presenting as a scheduled refresh (#448 review round 4).
    The suite must stay `ci: manual` (and therefore `name: null` in the
    committed affected map) until a CI leg actually builds and exports the
    engine binary; whoever adds that leg flips these pins in the same
    reviewed diff."""
    import yaml

    config = yaml.safe_load(
        (REPO_ROOT / "comparisons" / "us-tariff-panel.yaml").read_text()
    )
    assert config.get("ci") == "manual", (
        "us-tariff-panel must declare `ci: manual` — CI has no engine "
        "binary, so a dispatched run silently re-emits HEAD bytes"
    )
    affected = json.loads(
        (REPO_ROOT / "comparisons" / "affected_map.json").read_text()
    )
    entry = next(
        e for e in affected["suites"] if e["suite"] == "us-tariff-panel"
    )
    assert entry["name"] is None, (
        "us-tariff-panel must ride the manual lane (name: null) in the "
        "committed affected map"
    )


def test_column_exposure_matches_the_reviewed_pin(reference) -> None:
    """Positive-exposure counts, derived independently of the suite helper,
    must equal the reviewed pin — and so must the helper. The two
    zero-exposure columns are the reason 301_cs/other CANNOT be covered by
    this suite: no unit ever exercises them."""
    intervals, _ = reference
    units = covered_units(intervals)
    derived = {column: 0 for column in YALE_STATUTORY_COLUMNS}
    for interval, _probe in units:
        for column in YALE_STATUTORY_COLUMNS:
            if interval.rates[column] > 0:
                derived[column] += 1
    assert derived == EXPECTED_COLUMN_EXPOSURE
    assert column_exposure(units) == EXPECTED_COLUMN_EXPOSURE
    assert [
        c for c, n in EXPECTED_COLUMN_EXPOSURE.items() if n == 0
    ] == [
        "statutory_rate_301_cs",
        "statutory_rate_other",
    ]


def test_temporal_debt_records_conserve_and_address_every_interval(
    reference,
) -> None:
    """The addressable debt account must conserve the interval totals and
    keep every unaudited interval addressable: unique ids, exact interval
    bounds, and kind-correct classification (pre-domain intervals end
    before the domain; straddle records name their unaudited day range)."""
    intervals, _ = reference
    records = temporal_debt_records(intervals)

    pre = [r for r in records if r["kind"] == "pre_domain"]
    straddle = [r for r in records if r["kind"] == "straddle_clipped"]
    assert len(records) == len(pre) + len(straddle)
    assert len(pre) == EXPECTED_PRE_DOMAIN_RECORD_GROUPS
    assert len(straddle) == EXPECTED_STRADDLE_RECORD_GROUPS
    assert (
        sum(r["interval_count"] for r in pre) == EXPECTED_PRE_DOMAIN_INTERVALS
    )
    assert (
        sum(r["interval_count"] for r in straddle)
        == EXPECTED_STRADDLE_CLIPPED_INTERVALS
    )
    # Independent totals: the helper-free derivation must agree.
    assert len(temporal_debt(intervals)) == EXPECTED_PRE_DOMAIN_INTERVALS
    assert (
        len(straddle_clipped(intervals))
        == EXPECTED_STRADDLE_CLIPPED_INTERVALS
    )
    assert sum(
        1 for i in intervals if i.valid_until < DOMAIN_START
    ) == EXPECTED_PRE_DOMAIN_INTERVALS
    assert sum(
        1 for i in intervals if i.valid_from < DOMAIN_START <= i.valid_until
    ) == EXPECTED_STRADDLE_CLIPPED_INTERVALS

    ids = [r["debt_id"] for r in records]
    assert len(ids) == len(set(ids)), "debt records must be addressable"
    for record in pre:
        assert date.fromisoformat(record["valid_until"]) < DOMAIN_START
    for record in straddle:
        assert record["unprobed_from"] == record["valid_from"]
        assert (
            date.fromisoformat(record["unprobed_until"])
            == DOMAIN_START - timedelta(days=1)
        )
        assert (
            date.fromisoformat(record["valid_from"])
            < DOMAIN_START
            <= date.fromisoformat(record["valid_until"])
        )


def test_committed_report_scope_carries_exposure_and_debt(reference) -> None:
    """Every committed report derivative must carry the positive-exposure
    witness basis and the addressable temporal-debt account, exactly as
    re-derived from the committed reference — the scoreboard consumes
    these, so a drifted or forged account here would launder vacuous
    coverage or hide debt (sol stack review F3/F4)."""
    intervals, _ = reference
    expected_records = temporal_debt_records(intervals)
    paths = [
        REPO_ROOT
        / "dashboard"
        / "public"
        / "data"
        / "axiom-yale-us-tariff-panel.json",
        *sorted((REPO_ROOT / "reports").glob("axiom-yale-us-tariff-panel-*.json")),
    ]
    for path in paths:
        if not path.exists():
            pytest.skip("panel report not yet published")
        scope = json.loads(path.read_text())["scope"]
        assert scope["column_exposure"] == EXPECTED_COLUMN_EXPOSURE, path.name
        debt = scope["temporal_debt"]
        assert debt["pre_domain_intervals"] == EXPECTED_PRE_DOMAIN_INTERVALS
        assert (
            debt["straddle_clipped_intervals"]
            == EXPECTED_STRADDLE_CLIPPED_INTERVALS
        )
        assert debt["records"] == expected_records, path.name
        assert (
            scope["temporal_debt_intervals"] == debt["pre_domain_intervals"]
        )


def test_generator_refuses_a_domain_start_composition_divergence(
    tmp_path,
) -> None:
    """DOMAIN_START is only honest while it equals the live spine's earliest
    effective_from: the generator must hard-refuse a divergent pair, in
    either direction, and must refuse a composition it cannot read dates
    from (a silent no-dates pass would unbind the domain entirely)."""
    generator = _load_generator()

    good = tmp_path / "good.yaml"
    good.write_text(
        "modules:\n"
        "  - params:\n"
        f"      - effective_from: '{DOMAIN_START.isoformat()}'\n"
        "      - effective_from: '2026-06-01'\n"
    )
    generator.assert_domain_matches_composition(good)

    earlier = tmp_path / "earlier.yaml"
    earlier.write_text(
        "modules:\n"
        "  - params:\n"
        "      - effective_from: '2026-01-01'\n"
        f"      - effective_from: '{DOMAIN_START.isoformat()}'\n"
    )
    with pytest.raises(SystemExit, match="does not match"):
        generator.assert_domain_matches_composition(earlier)

    later = tmp_path / "later.yaml"
    later.write_text("params:\n  - effective_from: '2026-03-01'\n")
    with pytest.raises(SystemExit, match="does not match"):
        generator.assert_domain_matches_composition(later)

    empty = tmp_path / "empty.yaml"
    empty.write_text("modules: []\n")
    with pytest.raises(SystemExit, match="no effective_from"):
        generator.assert_domain_matches_composition(empty)


def test_generator_domain_binding_holds_against_the_live_spine() -> None:
    """When the rulespec-us checkout is present (supervised hosts), the
    binding must actually hold — the committed debt account was derived
    under this DOMAIN_START."""
    generator = _load_generator()
    composition = generator.RULESPEC_US / generator.COMPOSITION_PATH
    if not composition.exists():
        pytest.skip("rulespec-us checkout not available")
    generator.assert_domain_matches_composition(composition)
