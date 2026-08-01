"""Integrity gates for the committed us-tariff-panel reference artifacts.

These tests bind the committed Yale panel extract, the census<->origin
bridge, and both provenance stamps to each other — so a hand-edited,
partially regenerated, or silently narrowed reference fails CI instead of
self-certifying. They consume only committed files (no Yale checkout, no
network): this is the PR-local validator leg; the supervised exporter and
bridge builder enforce the generation-time invariants.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]
REFERENCE_DIR = REPO_ROOT / "reference" / "us-tariff-panel"
EXTRACT = REFERENCE_DIR / "yale_panel_slice.csv"
EXTRACT_PROVENANCE = REFERENCE_DIR / "yale_panel_provenance.json"
COVERED_LINES = REFERENCE_DIR / "covered_lines.txt"
BRIDGE = REFERENCE_DIR / "census_iso_bridge.csv"
BRIDGE_PROVENANCE = REFERENCE_DIR / "bridge_provenance.json"
SNAPSHOT = REFERENCE_DIR / "census_schedule_c_country.txt"

#: The Yale pin: must equal the exporter's EXPECTED_YALE_COMMIT and the
#: provenance stamp. Bumping the pin edits all three in one reviewed diff.
EXPECTED_YALE_COMMIT = "c4307e514196618afcbf88cf7fd33746417eeabf"

#: Append-only coverage floor: the T0 pilot lines (laneB design memo §scope).
#: Lines may be ADDED as rulespec-us coverage burns up; removing one is a
#: reference-narrowing event and must fail here until this reviewed floor is
#: deliberately changed.
T0_COVERED_FLOOR = frozenset({"7202111000", "7601103000", "9506624040"})


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_builder():
    path = REPO_ROOT / "scripts" / "build_census_iso_bridge.py"
    spec = importlib.util.spec_from_file_location("build_census_iso_bridge", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _covered_lines() -> list[str]:
    lines = [
        line.strip()
        for line in COVERED_LINES.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    return lines


def _extract_rows() -> list[dict]:
    with EXTRACT.open(newline="") as fh:
        return list(csv.DictReader(fh))


def _provenance() -> dict:
    return json.loads(EXTRACT_PROVENANCE.read_text())


def test_extract_hash_matches_provenance():
    assert _sha256(EXTRACT) == _provenance()["extract_sha256"]


def test_extractor_hash_matches_provenance():
    prov = _provenance()
    assert _sha256(REPO_ROOT / prov["extractor"]) == prov["extractor_sha256"]


def test_yale_pin_is_the_reviewed_commit():
    """Provenance and the exporter's reviewed constant carry the same pin."""
    prov = _provenance()
    assert prov["yale_commit"] == EXPECTED_YALE_COMMIT
    assert prov["yale_repo"] == "Budget-Lab-Yale/tariff-rate-tracker"
    exporter = (REPO_ROOT / "scripts" / "extract_yale_panel.R").read_text()
    assert f'EXPECTED_YALE_COMMIT <- "{EXPECTED_YALE_COMMIT}"' in exporter


def test_covered_lines_nonempty_unique_and_stamped():
    lines = _covered_lines()
    assert lines, "empty covered slice verifies nothing"
    assert len(lines) == len(set(lines)), "duplicate covered lines"
    assert all(len(x) == 10 and x.isdigit() for x in lines)
    assert list(_provenance()["covered_lines"]) == sorted(lines) or list(
        _provenance()["covered_lines"]
    ) == lines


def test_covered_lines_respect_the_append_only_floor():
    assert T0_COVERED_FLOOR <= set(_covered_lines()), (
        "a previously covered line was removed — reference narrowing; "
        "coverage is append-only (see reference/us-tariff-panel/README.md)"
    )


def test_extract_shape_matches_provenance():
    rows = _extract_rows()
    prov = _provenance()
    assert len(rows) == prov["extract_rows"]
    assert len({r["country"] for r in rows}) == prov["extract_countries"]
    assert len({r["revision"] for r in rows}) == prov["extract_revisions"]
    assert list(rows[0].keys()) == list(prov["columns"])
    assert {r["hts10"] for r in rows} == set(_covered_lines())


def test_extract_keys_unique_rates_valid_intervals_tile():
    rows = _extract_rows()
    keys = [(r["hts10"], r["country"], r["valid_from"]) for r in rows]
    assert len(keys) == len(set(keys)), "duplicate extract keys"
    rate_cols = [c for c in rows[0] if c.startswith("statutory_")]
    series: dict[tuple[str, str], list[tuple[date, date]]] = {}
    for r in rows:
        for c in rate_cols:
            value = float(r[c])  # raises on blank/non-numeric
            assert value >= 0.0, (r["hts10"], r["country"], c, value)
        lo, hi = date.fromisoformat(r["valid_from"]), date.fromisoformat(
            r["valid_until"]
        )
        assert lo <= hi
        series.setdefault((r["hts10"], r["country"]), []).append((lo, hi))
    interval_counts = set()
    for key, intervals in series.items():
        intervals.sort()
        interval_counts.add(len(intervals))
        for (_, prev_hi), (next_lo, _) in zip(intervals, intervals[1:]):
            assert next_lo == prev_hi + timedelta(days=1), (
                f"gap/overlap in {key}: {prev_hi} -> {next_lo}"
            )
    assert len(interval_counts) == 1, (
        f"differing interval counts across series: {sorted(interval_counts)}"
    )


def test_bridge_hashes_match_provenance():
    prov = json.loads(BRIDGE_PROVENANCE.read_text())
    assert _sha256(BRIDGE) == prov["bridge_sha256"]
    assert _sha256(SNAPSHOT) == prov["snapshot_sha256"]
    assert _sha256(REPO_ROOT / prov["builder"]) == prov["builder_sha256"]


def test_bridge_schema_uniqueness_and_code_contract():
    with BRIDGE.open(newline="") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == ["census_code", "iso2", "name"]
        rows = list(reader)
    prov = json.loads(BRIDGE_PROVENANCE.read_text())
    assert len(rows) == prov["bridge_rows"]
    codes = [r["census_code"] for r in rows]
    alphas = [r["iso2"] for r in rows]
    assert len(codes) == len(set(codes)), "duplicate census codes"
    assert len(alphas) == len(set(alphas)), "origin-code collisions"
    assert all(len(a) == 2 and a.isalpha() and a.isupper() for a in alphas)
    # Non-ISO codes must be exactly the documented Schedule C extensions.
    builder = _load_builder()
    extensions = {a for a in alphas if a not in builder.ISO_3166_ALPHA2}
    assert extensions == set(builder.SCHEDULE_C_EXTENSIONS), (
        f"undocumented non-ISO origin codes in the bridge: "
        f"{sorted(extensions - set(builder.SCHEDULE_C_EXTENSIONS))}"
    )
    assert set(prov["schedule_c_extensions"]) == extensions


def test_bridge_covers_every_panel_country():
    with BRIDGE.open(newline="") as fh:
        bridged = {r["census_code"] for r in csv.DictReader(fh)}
    panel = {r["country"] for r in _extract_rows()}
    assert panel <= bridged, f"unbridged panel countries: {sorted(panel - bridged)}"
