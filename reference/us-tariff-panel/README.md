# us-tariff-panel reference artifacts

Committed reference data for the `us-tariff-panel` comparison suite: the
rulespec-us tariff spine (evaluated by the axiom rules engine) vs the Yale
Budget Lab tariff-rate-tracker statutory panel, at per-authority granularity.

The reference is reviewer-independent: expected values come only from the
Yale panel, never from artifacts shared with the rulespec-us implementation.

## Artifacts

| File | What | Produced by |
|---|---|---|
| `covered_lines.txt` | HTS-10 lines in the covered slice (burn-up list) | hand-maintained |
| `yale_panel_slice.csv` | Covered-slice extract of the Yale panel: spine + `statutory_*` columns, all intervals | `scripts/extract_yale_panel.R` (supervised) |
| `yale_panel_provenance.json` | Yale commit, rds sha256/bytes, build flags, extractor sha, extract sha, shape | same |
| `census_schedule_c_country.txt` | Official Census Schedule C country concordance snapshot | census.gov (via `--fetch`) |
| `census_iso_bridge.csv` | census 4-digit code ↔ ISO alpha-2 bridge | `scripts/build_census_iso_bridge.py` |
| `bridge_provenance.json` | Source URL, snapshot sha, build stamp | same |

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

## Refresh procedure (any of: new HTS revision encoded, Yale pin bump, burn-up)

1. In the Yale checkout, build the panel in legal-date mode:
   `--full --unweighted --skip-release-check`.
2. If burning up coverage: append the new HTS-10 lines to `covered_lines.txt`.
3. From this repo root:
   `YALE_TRACKER_CHECKOUT=/path/to/tariff-rate-tracker Rscript scripts/extract_yale_panel.R`
4. Regenerate the comparison report (`scripts/generate_us_tariff_panel.py`)
   and review dispositions whose `expires_on_source_change` is invalidated by
   the new Yale commit.
5. Commit extract + provenance + report together.
