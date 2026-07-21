# FY2024 SNAP QC error-prediction pilot

## Status and interpretation

This is a deadline pilot over 6,081 regular-benefit FY2024 active-case reviews in
Colorado, New York, California, Arizona, Georgia, Maryland, and Texas. The
classifier result is **not yet the requested engine-feature experiment**: the
debug engine could not complete even one 50-case wide internal-stage request in
two minutes (nor a 500-case request in ten). The committed `raw_plus_engine`
numbers therefore use the same 7 CFR 273.10 chain algebra over QC-verified
inputs and QC constructed stages. `extract_features.py --engine` contains the
full replay and six finite-difference paths, but those paths did not produce the
committed table. Do not quote the lift as evidence about the engine until that
run completes.

The predictive-band experiment is complete under the brief's permitted
verified-input fallback: models predict the FNS-verified `FSBEN`; the agency's
issued `RAWBEN` is flagged when it is outside the out-of-fold band. It uses
scikit-learn `HistGradientBoostingRegressor(loss="quantile")`, not a quantile
random forest. `xgboost` and `quantile-forest` were unavailable in the offline
Python cache. Calibration for the classifier is the Brier score (lower is
better).

## Population and official error label

The loader is `axiom_oracles/populations/snap_qc.py::load_qc_units`; no new CSV
parser is used. The label is `STATUS in {2,3} AND AMTERR > 0`: the FY2024
Technical Documentation detailed codebook defines `STATUS` 1/2/3 as
correct/overissuance/underissuance on PDF p.74 and `AMTERR` as the amount of
benefit error on PDF p.87. This is zero-dollar tolerance. `RAWBEN` is the issued
benefit and `FSBEN` the final QC Minimodel benefit (codebook p.87; also
`docs/snap-qc-oracle-playbook.md`, “Ground truth”). Counts include every loaded
regular-benefit case; exclusions are the loader's counted MFIP, non-NYSCAP
SSI-CAP, missing-benefit, and missing-size gates.

<!-- label table -->

| State | Loaded | Errors | Correct | Excluded |
|---|---:|---:|---:|---:|
| AZ | 922 | 291 | 631 | 3 |
| CA | 883 | 386 | 497 | 0 |
| CO | 856 | 305 | 551 | 0 |
| GA | 945 | 446 | 499 | 0 |
| MD | 722 | 294 | 428 | 23 |
| NY | 847 | 349 | 498 | 38 |
| TX | 906 | 430 | 476 | 49 |
| **Total** | **6,081** | **2,501** | **3,580** | **113** |

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
adds stage/algebra columns. The encoded chain is
`$AXIOM_SNAP_QC_RULESPEC_ROOT/us/regulations/7-cfr/273/10.yaml`: net income is
floored after shelter; uncapped shelter is capped for households without an
elderly/disabled member; the pre-minimum allotment is the maximum allotment
minus `ceil(0.30 * net income)`, floored at zero; eligible one/two-person units
receive the minimum benefit. The committed fallback computes the requested
unbounded pre-zero-clamp value separately.

Leakage reasoning: stage values and unbounded benefit depend on verified case
facts and fiscal-year rules, not `STATUS` or `AMTERR`. They are not a
deterministic function of the error label. They nevertheless include
QC-constructed intermediates in this fallback, so their apparent lift can mix
rules structure with upstream QC editing; this is why the lift is not treated
as the requested engine result.

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

## Classifier results (provisional fallback)

| Features | AUC-ROC | PR-AUC | Brier |
|---|---:|---:|---:|
| Raw | 0.813 ± 0.014 | 0.697 ± 0.031 | 0.171 ± 0.006 |
| Raw + stage algebra | 0.845 ± 0.015 | 0.751 ± 0.036 | 0.154 ± 0.008 |
| Delta | +0.032 | +0.054 | -0.017 |

Every LOSO value is in [tables/lift.md](tables/lift.md).

## Outside-band results

| Band | Cases | Errors | Non-error coverage | Error recall | All flags | Error flags |
|---|---:|---:|---:|---:|---:|---:|
| q5–q95 | 6,081 | 2,501 | 0.939 | 0.074 | 398 | 186 |
| q10–q90 | 6,081 | 2,501 | 0.789 | 0.277 | 1,550 | 692 |
| q1–q99 | 6,081 | 2,501 | 0.996 | 0.006 | 33 | 15 |

State breakdowns are in [tables/qrf_coverage.md](tables/qrf_coverage.md).

## Limitations

This active-case QC PUF is a found/reviewed-error setting, not a production
application stream. Within-state samples are not designed for unadjusted state
estimation (Technical Documentation pp.64 and 77). Error prevalence and cause
mix vary by state, the year is single, and LOSO measures geographic transfer
only. Agency-reported input reconstruction was not used: the prior national R
reconstruction exists only as an external cache artifact and was not a
reproducible committed loader. The predictive-band fallback therefore uses
verified inputs explicitly. The engine replay remains incomplete as described
above.

## Reproduce

The normal rerun writes only `features.parquet` and provenance under
`~/.cache/axiom-oracles/qc-error-pilot/`; tables are small committed files.

```bash
cd /Users/maxghenis/TheAxiomFoundation/_worktrees/oracles-qc-error-pilot
analysis/qc-error-prediction/run_all.sh
```

Add `--engine` to the extraction command only when sufficient debug-engine time
is available; doing so changes the feature source and requires regenerating and
relabeling the provisional lift table.

## Ten-line call summary

1. The FY2024 sample contains 6,081 loaded cases across seven states; 2,501 meet the zero-dollar official error definition.
2. The loader counted 113 excluded regular-replay cases across those states.
3. Raw-feature five-fold AUC-ROC was 0.813 ± 0.014 on 6,081 cases.
4. Stage-algebra five-fold AUC-ROC was 0.845 ± 0.015; delta +0.032, pending the full engine replay.
5. Raw-feature PR-AUC was 0.697 ± 0.031; stage-algebra PR-AUC was 0.751 ± 0.036; delta +0.054.
6. Raw Brier score was 0.171 ± 0.006; stage-algebra Brier score was 0.154 ± 0.008; delta -0.017.
7. The q5–q95 band covered 3,361/3,580 non-error cases and flagged 186/2,501 error cases.
8. The q10–q90 band covered 2,824/3,580 non-error cases and flagged 692/2,501 error cases.
9. The q1–q99 band covered 3,565/3,580 non-error cases and flagged 15/2,501 error cases.
10. The predictive bands use verified inputs to predict FSBEN and test issued RAWBEN; they do not reconstruct agency-reported inputs.
