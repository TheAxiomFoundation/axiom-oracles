# FY2024 SNAP QC error-prediction pilot

## Status and interpretation

Pilot over 6,081 regular-benefit FY2024 active-case reviews in Colorado, New
York, California, Arizona, Georgia, Maryland, and Texas. The committed tables
are the **engine-feature experiment**: every `engine_*` feature is computed by
running each case through the axiom-rules-engine on the encoded rules (the same
replay machinery as the seven nightly QC suites), with six additional
finite-difference reruns per case for input sensitivities. The extraction
asserts a per-case identity — the engine benefit must equal the FNS-verified
`FSBEN` — and it holds **6,081/6,081 with zero mismatches** across all seven
states (`universe-features.json`), so the feature values are the encoded law's,
not re-derived approximations. (The earlier committed numbers used a Python
chain-algebra fallback because wide internal-stage engine requests were slow;
requesting the full output surface only for the base variant and a single
benefit output for the six perturbation variants brought the complete 42,567-case
extraction to roughly ten minutes.)

Two error labels run side by side. `label_error` is any QC-found variance
(`STATUS in {2,3} AND AMTERR > 0`). `label_error_official` applies the FY2024
tolerance threshold — the technical documentation states that error amounts of
$56 or less were not included in the official error rates — and is the concept
comparable to published payment error rates. Median `AMTERR` among
variance-status cases is $35, so most found variances fall below the official
threshold (1,630 of 2,501); 871 cases (14.3% of the sample, unweighted) meet
the official concept.

The predictive-band experiment predicts the FNS-verified `FSBEN` from raw
certification-observable features only; the agency's issued `RAWBEN` is flagged
when it falls outside the out-of-fold band. It uses scikit-learn
`HistGradientBoostingRegressor(loss="quantile")`, not a quantile random forest
(`xgboost` and `quantile-forest` were unavailable in the offline Python cache).
Classifier calibration is the Brier score (lower is better).

## Population and official error label

The loader is `axiom_oracles/populations/snap_qc.py::load_qc_units`; no new CSV
parser is used. `STATUS` 1/2/3 is correct/overissuance/underissuance (FY2024
Technical Documentation detailed codebook, PDF p.74) and `AMTERR` the amount of
benefit error (p.87). `label_error` = `STATUS in {2,3} AND AMTERR > 0`
(any variance); `label_error_official` = `STATUS in {2,3} AND AMTERR > 56`
(the FY2024 tolerance threshold: the documentation states error amounts of $56
or less were not included in the official error rates). `RAWBEN` is the issued
benefit and `FSBEN` the final QC Minimodel benefit (codebook p.87; also
`docs/snap-qc-oracle-playbook.md`, “Ground truth”). Counts include every loaded
regular-benefit case; exclusions are the loader's counted MFIP, non-NYSCAP
SSI-CAP, missing-benefit, and missing-size gates. The `AMTERR` distribution
among variance-status cases is in
[tables/amterr_distribution.json](tables/amterr_distribution.json).

Current per-state counts (both labels) are generated in
[tables/label_counts.md](tables/label_counts.md); totals: 6,081 loaded, 2,501
any-variance, 871 official, 113 excluded.

## Feature grounding

All raw features are fields already mapped and cited in
`axiom_oracles/populations/snap_qc.py` and consumed by
`axiom_oracles/bridges/snap_qc_compare.py::map_qc_unit`:

| Analysis feature | QC source and grounding |
|---|---|
| year-month, state | `YRMONTH` p.74; `STATE` p.77 |
| household/member/child/elderly counts | `CERTHHSZ` p.75; `AGEi` p.89; participating/disability handling in the loader |
| earned and unearned income | sums of the documented `FSEARN` components p.79 and `FSUNEARN` components p.81; source columns cited individually on pp.95–97 in the loader |
| rent, utility amount/tier | `RENT`, `UTIL`, `SUA1` p.86 |
| medical, dependent care, child support | `FSMEDEXP` p.85, `FSDEPDED` p.84, `FSCSEXP` p.84 |
| homeless, categorical eligibility, resources | `HOMEDED` p.86, `CAT_ELIG` p.72, `LIQRESOR` p.82 |

Neither `RAWBEN`, `FSBEN`, `STATUS`, nor `AMTERR` enters raw model A. Model B
adds the engine-computed columns: the compared stage outputs (gross income,
standard deduction, excess shelter, net income, maximum allotment, benefit),
the internal 273.10 outputs (earned-income deduction, net income before
shelter, uncapped excess shelter, minimum benefit, pre-minimum allotment),
the derived clamp geometry (unbounded benefit `max allotment −
ceil(0.30·net)`, which-clamp-binds indicators, signed distance-to-clamp
slacks), and six finite-difference sensitivities (benefit change for +$10 to
earned income, unearned income, shelter, dependent care, child support, and
medical where entitled — each an actual engine rerun). The encoded chain is
`$AXIOM_SNAP_QC_RULESPEC_ROOT/us/regulations/7-cfr/273/10.yaml`.

Leakage reasoning: every engine feature is a deterministic function of the
verified case facts and the fiscal-year rules — not of `STATUS`, `AMTERR`, or
`RAWBEN` — so none is a function of the label. The per-case `FSBEN` identity
(6,081/6,081) certifies the features equal the encoded law's values; because
the engine reproduces `FSBEN` exactly, `engine_benefit` carries the same
information as `FSBEN` itself, which is a legitimate certification-time
quantity (the correct benefit for the verified facts), not an outcome
disclosure.

## Design

Cases are sorted by state and stable loader case ID. Fold is
`sha256("294" + case_id) mod 5`; both feature sets use identical folds.
Classifier: `HistGradientBoostingClassifier`, seed 294, 200 iterations,
learning rate .05, 15 leaves, L2=1. Reported metrics are AUC-ROC, average
precision (PR-AUC), and Brier score. LOSO trains on six states and scores the
seventh.

Predictive bands are genuine out-of-fold predictions from six separately fit
quantile `HistGradientBoostingRegressor` models per fold (250 iterations,
learning rate .05, 15 leaves, L2=1). Coverage is evaluated against `FSBEN` on
non-error cases. Recall is the fraction of official error cases whose `RAWBEN`
falls strictly outside the band. No metric/configuration was dropped.

## Classifier results (engine features)

Five-fold CV, mean ± sd; full LOSO detail in [tables/lift.md](tables/lift.md).

| Label | Features | AUC-ROC | PR-AUC | Brier |
|---|---|---:|---:|---:|
| any variance (2,501) | raw | 0.814 ± 0.014 | 0.698 ± 0.033 | 0.171 ± 0.006 |
| any variance (2,501) | raw + engine | 0.844 ± 0.014 | 0.747 ± 0.039 | 0.155 ± 0.007 |
| official > $56 (871) | raw | 0.749 ± 0.024 | 0.364 ± 0.038 | 0.109 ± 0.004 |
| official > $56 (871) | raw + engine | 0.754 ± 0.016 | 0.366 ± 0.034 | 0.109 ± 0.004 |

The engine features lift the any-variance model in every leave-one-state-out
split (e.g. NY 0.794 → 0.879 AUC) but add almost nothing under the official
threshold. A mechanical reading consistent with this split — a hypothesis this
pilot does not test directly: the engine's clamp-geometry and sensitivity
features describe whether and how strongly input discrepancies transmit into
benefit dollars, which decides detectability for the many small variances
(median $35) but rarely decides whether a large wrong-facts error crosses $56.

## Outside-band results

Bands from raw features only; both labels scored against the same bands. Full
per-state detail in [tables/qrf_coverage.md](tables/qrf_coverage.md).

| Label | Band | Non-error coverage | Error recall | All flags | Error flags |
|---|---|---:|---:|---:|---:|
| any variance | q5–q95 | 0.947 | 0.076 | 376 | 189 |
| any variance | q10–q90 | 0.789 | 0.280 | 1,559 | 700 |
| official > $56 | q5–q95 | 0.954 | 0.153 | 376 | 133 |
| official > $56 | q10–q90 | 0.802 | 0.381 | 1,559 | 332 |
| official > $56 | q1–q99 | 0.997 | 0.014 | 33 | 12 |

At q10–q90 the band flags 1,559 of 6,081 cases (25.6%) and catches 38.1% of
official errors; at q5–q95 it flags 6.2% of cases and catches 15.3%. The
official-label recall exceeding the any-variance recall at every band is the
expected size effect: larger errors sit farther outside the band.

## Limitations

This active-case QC PUF is a found/reviewed-error setting, not a production
application stream. Within-state samples are not designed for unadjusted state
estimation (Technical Documentation pp.64 and 77). Error prevalence and cause
mix vary by state, the year is single, and LOSO measures geographic transfer
only. Agency-reported input reconstruction was not used: the prior national R
reconstruction exists only as an external cache artifact and was not a
reproducible committed loader. The predictive bands therefore use verified
inputs explicitly — for the roughly 86% of cases with no official variance the
two coincide, and for error cases the design flags issued-outside-band rather
than modeling the reporting process. The clamp-transmission reading of the
label split is a hypothesis, not a tested mechanism.

## Reproduce

The rerun writes `features.parquet` and provenance under
`~/.cache/axiom-oracles/qc-error-pilot/`; tables are small committed files.
Engine mode is the default and takes roughly ten minutes; the extraction fails
loudly if any case's engine benefit differs from `FSBEN`.

```bash
cd /Users/maxghenis/TheAxiomFoundation/_worktrees/oracles-qc-error-pilot
analysis/qc-error-prediction/run_all.sh          # engine mode (default)
MODE=analytical analysis/qc-error-prediction/run_all.sh   # engine-free fallback
```

Determinism: a second full extraction and model run reproduce the parquet and
every committed table byte-identically (seeded folds, sorted cases,
`PYTHONHASHSEED=294`).

## Ten-line call summary

1. Sample: 6,081 FY2024 active-case reviews across CO/NY/CA/AZ/GA/MD/TX; every case's engine-computed benefit equals the FNS-verified FSBEN, 6,081/6,081.
2. Labels: 2,501 cases carry any QC-found variance; 871 (14.3%) exceed the official $56 FY2024 tolerance; median variance among error-status cases is $35.
3. Any-variance classifier: AUC 0.814 raw vs 0.844 with engine features; PR-AUC 0.698 vs 0.747.
4. The engine lift holds in all seven leave-one-state-out splits (largest: New York, 0.794 → 0.879 AUC).
5. Official-threshold classifier: AUC 0.749 raw vs 0.754 with engine features — no material lift.
6. Reading (hypothesis): clamp geometry decides whether small variances become detectable benefit variances; large wrong-facts errors cross $56 regardless.
7. Predictive bands (raw features → verified benefit, out-of-fold): q5–q95 flags 376 of 6,081 issued amounts (6.2%) and catches 15.3% of official errors at 95.4% non-error coverage.
8. q10–q90 flags 25.6% of cases and catches 38.1% of official errors at 80.2% coverage.
9. Everything is deterministic and rerunnable in one command; features come from the same engine and encodings the seven zero-tolerance replay suites prove nightly.
10. Proposed next test: rerun both experiments on the four partner states' own QA data, and add FY2023 for a second year.
