"""Integrity gates for the committed us-tariff-panel reference artifacts.

These tests bind the committed Yale panel extract, the census<->origin
bridge, and both provenance stamps to each other — so a hand-edited,
partially regenerated, or silently narrowed reference fails CI instead of
self-certifying. They consume only committed files (no Yale checkout, no
network): this is the PR-local validator leg; the supervised exporter and
bridge builder enforce the generation-time invariants.

Trust model: provenance stamps are MUTABLE data files — anything checked
only against them can be restamped in the same edit. Every load-bearing
identity is therefore pinned as a reviewed constant in THIS file (content
sha256 of the extract and the snapshot, the covered-line set, the country
dimension, the column schema, the interval profile), mirroring the
EXPECTED_YALE_COMMIT pattern: a legitimate refresh must update the
constants here in the same reviewed diff, so any narrowing is visible in
review rather than absorbable by restamping. Provenance checks then verify
stamp CONSISTENCY, not identity.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
import re
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

#: The EXACT reviewed covered slice — not a floor. Every burn-up (and any
#: deliberate scope change) must edit this frozen set in the same reviewed
#: diff as covered_lines.txt. An exact-set pin is what makes append-only
#: durable: the exporter's check against the previous provenance stamp can
#: be bypassed by editing/deleting the (mutable) stamp before a refresh,
#: but this constant only changes in reviewed code.
REVIEWED_COVERED_LINES = frozenset(
    {"7202111000", "7601103000", "9506624040", "2203000030", "8541420010"}
)

#: The reviewed country dimension of the Yale panel (240 Schedule C census
#: codes). A pin bump that changes the upstream country universe must edit
#: these constants in the same reviewed diff — a shrunk or substituted
#: country set cannot hide behind a self-stamped provenance count/list.
#: The digest is sha256 of the comma-joined sorted census codes; the
#: exporter carries the same pin (EXPECTED_COUNTRY_SET_SHA256).
EXPECTED_COUNTRY_COUNT = 240
EXPECTED_COUNTRY_SET_SHA256 = (
    "17640ac633347c44d3017a4b43bbc12a8b7d3c5323393c780b89f262fcc166d7"
)

#: Reviewed content digests of the committed reference bytes. The refresh
#: procedure (README) regenerates the artifacts supervised, then updates
#: these pins in the same reviewed diff — CI accepts no other bytes, so a
#: restamped provenance cannot certify an altered or narrowed reference.
EXPECTED_EXTRACT_SHA256 = (
    "add5540f497ba2788eb963d58d0e1ca06352026c96f9e14ddb931abbf69d3da5"
)
EXPECTED_SNAPSHOT_SHA256 = (
    "ad7d599359d14c7d1d5977cf6b2331b85e25592bc51e594aae140c78a29204a5"
)
#: The exporter SOURCE is byte-pinned too. Its gates mirror this file's
#: pins, but the exporter is R — assignment can be spelled `<-`, `->`,
#: `assign()`, backticks, … — so no Python-side pattern match can prove
#: the mirror semantically. The byte pin makes the guarantee total: ANY
#: exporter edit fails CI until this constant is updated in the same
#: reviewed diff (the _assert_exporter_pin checks below remain as a
#: readable first-line diagnostic for WHICH pin drifted).
EXPECTED_EXPORTER_SHA256 = (
    "97086c88292eb339fa01abe07167062956bd570c732a3609a9ebb923760705dd"
)

#: Reviewed extract schema: the spine plus the COMPLETE statutory-column
#: set (the sum-of-statutory-columns totals claim depends on completeness —
#: dynamic discovery would let a column removal make rate checks vacuous).
EXPECTED_COLUMNS = (
    "hts10",
    "country",
    "revision",
    "effective_date",
    "valid_from",
    "valid_until",
    "statutory_base_rate",
    "statutory_rate_232",
    "statutory_rate_ieepa_recip",
    "statutory_rate_ieepa_fent",
    "statutory_rate_301",
    "statutory_rate_301_cs",
    "statutory_rate_s301fl",
    "statutory_rate_s301br",
    "statutory_rate_s338",
    "statutory_rate_s122",
    "statutory_rate_section_201",
    "statutory_rate_other",
)
STATUTORY_COLUMNS = tuple(c for c in EXPECTED_COLUMNS if c.startswith("statutory_"))

#: Reviewed temporal profile: every (hts10, country) series carries exactly
#: this many intervals, and all series share ONE global boundary signature
#: (Yale revisions are global dates). A Yale pin bump that adds revisions
#: updates this constant in the same reviewed diff.
EXPECTED_INTERVALS_PER_SERIES = 57


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


def _assert_exporter_pin(name: str, expected_rhs: str) -> None:
    """Assert the exporter carries EXACTLY ONE leftward assignment to
    `name`, whose full right-hand side (to end of line) is exactly
    `expected_rhs`. Substring containment is not enough: `NAME <- 57 - 1`
    contains "NAME <- 57" yet evaluates to 56, and a later assignment
    would silently override the first. This is a DIAGNOSTIC layer only —
    R assignment can also be spelled `->`, `assign()`, backticks, …,
    which no Python-side pattern can rule out; the hard guarantee against
    any exporter drift is the EXPECTED_EXPORTER_SHA256 byte pin."""
    exporter = (REPO_ROOT / "scripts" / "extract_yale_panel.R").read_text()
    assignments = re.findall(
        rf"{re.escape(name)}\s*(?:<<-|<-|=)\s*([^\n]*)", exporter
    )
    assert assignments == [expected_rhs], (
        f"exporter pin {name}: expected exactly one assignment with RHS "
        f"{expected_rhs!r}, found {assignments!r} — exporter pin drifted "
        "from the reviewed constant in this file"
    )


def test_extract_bytes_match_the_reviewed_pin():
    """The extract itself is pinned in reviewed code; the provenance stamp
    must agree (consistency, not identity — the stamp is mutable)."""
    assert _sha256(EXTRACT) == EXPECTED_EXTRACT_SHA256
    assert _provenance()["extract_sha256"] == EXPECTED_EXTRACT_SHA256


def test_extractor_hash_matches_provenance():
    """The exporter source is itself a reviewed byte pin (identity), and
    the provenance stamp must agree (consistency)."""
    exporter_path = REPO_ROOT / "scripts" / "extract_yale_panel.R"
    assert _sha256(exporter_path) == EXPECTED_EXPORTER_SHA256
    prov = _provenance()
    assert (REPO_ROOT / prov["extractor"]) == exporter_path
    assert prov["extractor_sha256"] == EXPECTED_EXPORTER_SHA256


def test_yale_pin_is_the_reviewed_commit():
    """Provenance and the exporter's reviewed constant carry the same pin."""
    prov = _provenance()
    assert prov["yale_commit"] == EXPECTED_YALE_COMMIT
    assert prov["yale_repo"] == "Budget-Lab-Yale/tariff-rate-tracker"
    _assert_exporter_pin("EXPECTED_YALE_COMMIT", f'"{EXPECTED_YALE_COMMIT}"')


def test_exporter_mirrors_the_reviewed_pins():
    """The exporter's fail-before-write gates carry the same reviewed pins
    as this validator; a one-sided edit (drifting the exporter's copy) is a
    CI failure, not a silent divergence. The hard guarantee is the
    EXPECTED_EXPORTER_SHA256 byte pin (any exporter edit whatsoever fails
    CI until the pin is bumped in a reviewed diff); these assignment
    checks are the readable diagnostic underneath it."""
    _assert_exporter_pin(
        "EXPECTED_INTERVALS_PER_SERIES", str(EXPECTED_INTERVALS_PER_SERIES)
    )
    _assert_exporter_pin(
        "EXPECTED_COUNTRY_SET_SHA256", f'"{EXPECTED_COUNTRY_SET_SHA256}"'
    )


def test_covered_lines_nonempty_unique_and_stamped():
    lines = _covered_lines()
    assert lines, "empty covered slice verifies nothing"
    assert len(lines) == len(set(lines)), "duplicate covered lines"
    assert all(len(x) == 10 and x.isdigit() for x in lines)
    assert list(_provenance()["covered_lines"]) == sorted(lines) or list(
        _provenance()["covered_lines"]
    ) == lines


def test_covered_lines_equal_the_reviewed_set():
    assert set(_covered_lines()) == REVIEWED_COVERED_LINES, (
        "covered_lines.txt differs from the reviewed covered slice — a "
        "removal is reference narrowing; an addition (burn-up) must update "
        "REVIEWED_COVERED_LINES in the same reviewed diff (see "
        "reference/us-tariff-panel/README.md)"
    )


def test_extract_shape_matches_reviewed_schema_and_provenance():
    rows = _extract_rows()
    prov = _provenance()
    assert list(rows[0].keys()) == list(EXPECTED_COLUMNS), (
        "extract columns differ from the reviewed schema"
    )
    assert list(prov["columns"]) == list(EXPECTED_COLUMNS)
    assert len(rows) == prov["extract_rows"]
    assert len({r["country"] for r in rows}) == prov["extract_countries"]
    assert len({r["revision"] for r in rows}) == prov["extract_revisions"]
    assert {r["hts10"] for r in rows} == set(_covered_lines())


def test_extract_country_dimension_is_complete():
    """Every covered line carries the identical, full country set.

    Set equality per line (not count equality: dropping a different country
    from each line keeps counts equal) plus the reviewed
    EXPECTED_COUNTRY_COUNT pin (not the self-stamped provenance count, which
    a narrowed refresh would restamp)."""
    per_line: dict[str, set[str]] = {}
    for r in _extract_rows():
        per_line.setdefault(r["hts10"], set()).add(r["country"])
    country_sets = list(per_line.values())
    assert all(s == country_sets[0] for s in country_sets), (
        "covered lines carry differing country sets — a country series "
        "was dropped from some line(s)"
    )
    assert len(country_sets[0]) == EXPECTED_COUNTRY_COUNT
    canonical = ",".join(sorted(country_sets[0])).encode()
    assert hashlib.sha256(canonical).hexdigest() == EXPECTED_COUNTRY_SET_SHA256, (
        "extract country IDENTITY differs from the reviewed set digest — "
        "a substituted country cannot hide behind a matching count"
    )
    assert sorted(country_sets[0]) == list(_provenance()["countries"])


def test_extract_keys_unique_rates_valid_intervals_tile():
    rows = _extract_rows()
    keys = [(r["hts10"], r["country"], r["valid_from"]) for r in rows]
    assert len(keys) == len(set(keys)), "duplicate extract keys"
    series: dict[tuple[str, str], list[tuple[date, date]]] = {}
    for r in rows:
        # Reviewed column list, NOT dynamic discovery: removing the
        # statutory columns must fail here, not make this loop vacuous.
        for c in STATUTORY_COLUMNS:
            value = float(r[c])  # raises on blank/non-numeric
            assert math.isfinite(value) and value >= 0.0, (
                r["hts10"], r["country"], c, value,
            )
        lo, hi = date.fromisoformat(r["valid_from"]), date.fromisoformat(
            r["valid_until"]
        )
        assert lo <= hi
        series.setdefault((r["hts10"], r["country"]), []).append((lo, hi))
    boundary_signatures = set()
    for key, intervals in series.items():
        intervals.sort()
        assert len(intervals) == EXPECTED_INTERVALS_PER_SERIES, (
            f"{key} carries {len(intervals)} intervals, reviewed profile is "
            f"{EXPECTED_INTERVALS_PER_SERIES} — truncated/narrowed series"
        )
        boundary_signatures.add(tuple(intervals))
        for (_, prev_hi), (next_lo, _) in zip(intervals, intervals[1:]):
            assert next_lo == prev_hi + timedelta(days=1), (
                f"gap/overlap in {key}: {prev_hi} -> {next_lo}"
            )
    # Yale revisions are global dates: every series must share ONE exact
    # boundary signature (equal counts alone would admit shifted intervals).
    assert len(boundary_signatures) == 1, (
        f"{len(boundary_signatures)} distinct interval-boundary signatures "
        "across series — the temporal profile is not uniform"
    )


def test_snapshot_bytes_match_the_reviewed_pin():
    """The Schedule C snapshot is the root of the bridge derivation chain;
    pinning its bytes in reviewed code closes the co-edit path (snapshot
    swap + rebuild + restamp)."""
    assert _sha256(SNAPSHOT) == EXPECTED_SNAPSHOT_SHA256


def test_bridge_hashes_match_provenance():
    prov = json.loads(BRIDGE_PROVENANCE.read_text())
    assert _sha256(BRIDGE) == prov["bridge_sha256"]
    assert prov["snapshot_sha256"] == EXPECTED_SNAPSHOT_SHA256
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


def test_bridge_rederives_exactly_from_snapshot():
    """The committed bridge must be the exact deterministic derivation of
    the committed snapshot — hash self-consistency alone would accept a
    hand-edited bridge with a restamped bridge_sha256."""
    builder = _load_builder()
    rows, _ = builder.parse_snapshot(SNAPSHOT.read_text())
    expected = [[code, alpha, name] for code, name, alpha in sorted(rows)]
    with BRIDGE.open(newline="") as fh:
        reader = csv.reader(fh)
        assert next(reader) == ["census_code", "iso2", "name"]
        assert list(reader) == expected


def test_bridge_covers_every_panel_country():
    with BRIDGE.open(newline="") as fh:
        bridged = {r["census_code"] for r in csv.DictReader(fh)}
    panel = {r["country"] for r in _extract_rows()}
    assert panel <= bridged, f"unbridged panel countries: {sorted(panel - bridged)}"
