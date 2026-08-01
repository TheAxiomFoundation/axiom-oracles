"""Pure-logic tests for the us-tariff-panel suite against the committed
reference extract — no engine, CI-runnable.

The engine-evaluation leg is supervised (see reference/us-tariff-panel/
README.md); these tests pin the pieces CI can check: the committed extract's
integrity against its provenance stamp, the census<->ISO bridge coverage,
the temporal-domain clipping (the batch-poisoning guard), and the
authority-slot mapping invariants.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from axiom_oracles.suites.us_tariff_panel import (
    AUTHORITY_SLOTS,
    DOMAIN_START,
    OUTPUTS,
    REFERENCE_DIRNAME,
    TOTAL,
    YALE_STATUTORY_COLUMNS,
    covered_units,
    dotted_hts,
    load_provenance,
    load_reference,
    panel_case,
    temporal_debt,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = REPO_ROOT / REFERENCE_DIRNAME


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
    # committed extract (not a stale or divergent one).
    report_path = (
        REPO_ROOT / "dashboard" / "public" / "data" / "axiom-yale-us-tariff-panel.json"
    )
    if not report_path.exists():
        pytest.skip("panel report not yet published")
    report = json.loads(report_path.read_text())
    # The run_comparison chain replaces the provenance block with runner
    # provenance, so the reference vintage is pinned under scope.
    reference = report["scope"]["reference"]
    assert reference["extract_sha256"] == provenance["extract_sha256"]
    assert reference["yale_commit"] == provenance["yale_commit"]
