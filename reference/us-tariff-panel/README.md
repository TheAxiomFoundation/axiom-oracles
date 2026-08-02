# us-tariff-panel reference artifacts

Committed reference data for the `us-tariff-panel` comparison suite: the
rulespec-us tariff spine (evaluated by the axiom rules engine) vs the Yale
Budget Lab tariff-rate-tracker statutory panel, at per-authority granularity.

The reference is reviewer-independent: expected values come only from the
Yale panel, never from artifacts shared with the rulespec-us implementation.

## Artifacts

| File | What | Produced by |
|---|---|---|
| `covered_lines.txt` | HTS-10 lines in the covered slice (append-only burn-up list) | hand-maintained, gated |
| `yale_panel_slice.csv` | Covered-slice extract of the Yale panel: spine + `statutory_*` columns, all intervals | `scripts/extract_yale_panel.R` (supervised) |
| `yale_panel_provenance.json` | Yale commit, rds sha256/bytes, build flags, extractor sha, extract sha, shape | same |
| `census_schedule_c_country.txt` | Official Census Schedule C country concordance snapshot | census.gov (via `--fetch`) |
| `census_iso_bridge.csv` | census 4-digit code ↔ origin-code bridge (ISO alpha-2 + Schedule C extensions, see below) | `scripts/build_census_iso_bridge.py` |
| `bridge_provenance.json` | Source URL, snapshot sha, builder sha, extension list, build stamp | same |

`tests/test_us_tariff_reference.py` is the CI-side validator. Its trust
model: provenance stamps are mutable data files, so anything checked only
against them can be restamped in the same edit. Every load-bearing identity
is therefore a **reviewed constant in the test file** (the
`EXPECTED_YALE_COMMIT` pattern): the extract bytes
(`EXPECTED_EXTRACT_SHA256`), the exporter source bytes
(`EXPECTED_EXPORTER_SHA256` — the exporter's gates mirror the validator
pins, and since R assignment syntax cannot be policed from Python, the
mirror guarantee is enforced as a byte pin on the exporter itself), the
snapshot bytes
(`EXPECTED_SNAPSHOT_SHA256`), the covered slice (`REVIEWED_COVERED_LINES`,
exact set — not a floor), the country dimension
(`EXPECTED_COUNTRY_COUNT` + `EXPECTED_COUNTRY_SET_SHA256`, with per-line
country-SET equality), the column schema (`EXPECTED_COLUMNS`), and the
temporal profile (`EXPECTED_INTERVALS_PER_SERIES` + one global
interval-boundary signature). The bridge is re-derived exactly from the
pinned snapshot. Provenance checks then verify stamp consistency, not
identity. A legitimate refresh updates the constants in the same reviewed
diff, so any narrowing is visible in review; coverage is **append-only**,
and narrowing the reference to force agreement is the failure mode this
suite exists to prevent.

## Origin-code contract (bridge)

The rulespec-us tariff spine takes 2-letter origin codes. Three Census
Schedule C alpha codes have no assigned ISO 3166-1 counterpart and pass
through the bridge unchanged: `KV` (Kosovo — ISO assigns no code), `GZ` and
`WE` (Gaza Strip / West Bank — ISO assigns `PS` to the State of Palestine as
a whole; Census splits it, and the Yale panel prices them separately). This
is safe because the composed program matches named countries by code and
otherwise applies the statutory "any country" baseline (HTS 9903.01.25):
extension codes get the statutorily correct default, and any country-specific
encoding gap surfaces as a classified mismatch — never a silent remap. The
builder rejects any other non-ISO code until it is reviewed into
`SCHEDULE_C_EXTENSIONS`.

## Why a committed extract (supervised leg)

The full panel (`data/timeseries/rate_timeseries.rds`, ~1.9 GB, 277M
interval-rows) takes ~200 s and ~78 GB RSS to load — it cannot run in CI.
The extraction runs supervised on the build machine; CI consumes only the
committed extract (the comparison runner re-emits the committed report when
the engine/reference legs are unavailable, following the EUROMOD pattern).

Excluded from the extract, deliberately: estimation-touched and effective
columns (`base_rate`, `rate_*`, `total_rate`, `total_additional`, metal
shares, `swiss_*`, `usmca_eligible`, `heading_program`, `base_rate_type`,
`deriv_type`, `s232_annex`, `is_copper_heading`). They are not parity
targets. Totals are reconciled against the **sum of the statutory columns**,
never the stored effective totals (which are utilization-share-scaled).

## What the provenance does and does not bind

The stamp machine-verifies: the extract bytes (`extract_sha256`), the rds
bytes (`panel_sha256`/`panel_bytes`), the exporter bytes
(`extractor_sha256`), and that the Yale checkout was at the reviewed
`EXPECTED_YALE_COMMIT` pin with **no tracked modifications** and an upstream
`Budget-Lab-Yale/tariff-rate-tracker` remote at extraction time. It cannot
machine-verify that the rds was *built* from that checkout with the recorded
flags/date mode — the rds carries no build manifest — so those are attested
by the supervising operator (`panel_build_attestation` in the stamp). A
future upstream build manifest would close that residual; until then the
supervised protocol is the boundary, stated here rather than implied away.

## Refresh procedure (any of: new HTS revision encoded, Yale pin bump, burn-up)

1. In the Yale checkout, build the panel in legal-date mode:
   `--full --unweighted --skip-release-check`.
2. If burning up coverage: **append** the new HTS-10 lines to
   `covered_lines.txt` AND update `REVIEWED_COVERED_LINES` in
   `tests/test_us_tariff_reference.py` in the same reviewed diff (removals
   fail the exporter and the validator).
   If bumping the Yale pin: update `EXPECTED_YALE_COMMIT` in
   `scripts/extract_yale_panel.R` and in `tests/test_us_tariff_reference.py`
   in the same reviewed diff; if the upstream country universe changed,
   `EXPECTED_COUNTRY_COUNT` and `EXPECTED_COUNTRY_SET_SHA256` (in both
   files) too.
3. From this repo root:
   `YALE_TRACKER_CHECKOUT=/path/to/tariff-rate-tracker Rscript scripts/extract_yale_panel.R`
   Then update the reviewed content pins in
   `tests/test_us_tariff_reference.py` to the regenerated artifacts:
   `EXPECTED_EXTRACT_SHA256`, and on a schedule/profile change
   `EXPECTED_COLUMNS` / `EXPECTED_INTERVALS_PER_SERIES` (a snapshot
   refresh via `--fetch` likewise updates `EXPECTED_SNAPSHOT_SHA256`;
   any edit to `scripts/extract_yale_panel.R` updates
   `EXPECTED_EXPORTER_SHA256`).
   These pins changing IS the review surface — the diff shows exactly what
   the reference now claims.
4. Regenerate the comparison report (`scripts/generate_us_tariff_panel.py`).
   On a Yale pin bump, re-run `scripts/apply_dispositions.py`: tariff
   dispositions match mismatch rows by selector, so entries whose underlying
   values changed are reported as expired/orphaned by that script — they do
   not expire automatically on the commit change itself. Reconcile every
   warning before committing.
5. Commit extract + provenance + report together.
