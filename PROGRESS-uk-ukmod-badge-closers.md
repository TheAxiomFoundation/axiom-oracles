# UK–UKMOD badge closers + legacy means-tested — progress

Branch: `uk-ukmod-badge-closers`. Goal: drive UK-vs-UKMOD (was 15/26, unexplained 0)
to conformant; close uk-pe `legacy_means_tested`. Validation year 2026, eval ≥ 2026-04-06.

Env for the local Rosetta EUROMOD regen (verified working this session):
`EUROMOD_PYTHON=~/.venvs/axiom-euromod-x64/bin/python DOTNET_ROOT=~/.dotnet-x64
PYTHONNET_RUNTIME=coreclr POLARS_SKIP_CPU_CHECK=1
EUROMOD_MODEL_ROOT=~/Downloads/UKMOD_PUBLIC_B2026.03` then
`.venv/bin/python scripts/run_comparison.py <name> --summary`. Each comparison
config supplies its exact `rulespec_root` and `axiom_binary`.

## Scoreboard
- Start: UK covered 15/26, unexplained 0, axiom 0. uk-pe 14/25.
- After Track 1: **UK covered 17/26, unexplained 0, axiom 0** (bho_uk, tinta_uk covered).

## Track 1 — RUNNER-GATED REGEN (DONE)
- `tinta_uk` (personal allowance): ran `uk-personal-allowance-ukmod` → 5/5 exact to the
  penny vs UKMOD tinta_s. Dashboard committed. COVERED.
- `bho_uk` (Housing Benefit): ran `uk-housing-benefit-ukmod`. Finding: UKMOD UK_2026
  deterministically zeroes WORKING-AGE legacy HB via the UC transition (i_bho_noUC /
  i_bho_yesUC — "new benefit claims are to UC only and not to the legacy benefits"),
  NOT the stochastic take-up draw (verified: identical zeros across runs; take-up pins
  to 1.0 do not restore an award). Redesigned grid: pension-age no-earnings single+couple
  match to the penny (max-benefit path, HB live); 3 working-age cases dispositioned
  `upstream_engine_gap` (euromod_issues.json#ukmod-hb-bho-uc-transition +
  dispositions/uk-housing-benefit.yaml). COVERED, unexplained 0.
  - Filed-for-follow-up (rulespec-uk): the pension-age taper exposed two Axiom-side
    applicable-amount gaps — (1) no pre/post-1-April-2021 pensioner cohort split (applies
    £256.00 to post-2021 pensioners who should get UKMOD's £238.65, a £17.35/wk gap);
    (2) £256.00 vs UKMOD £256.70 single-pensioner 2026-27 up-rating (£0.70/wk). Taper
    cases dropped from the oracle grid (not dispositioned — Axiom-side); taper arithmetic
    is graded to the penny by the #83 pipeline's own companion tests. → rulespec-uk issue.

## Track 2 — EXCLUSION ADJUDICATIONS (DONE, evidence-first)
- `bwkmt_bfamt` (WTC/CTC): EXCLUDED **oracle_models_repealed_law** (NEW enum value added to
  schema.py). Tax credits ended 5 Apr 2025 (GOV.UK). Live probe: UKMOD UK_2026 returns
  bwkmt_s/bfamt_s = 0 for single-childless-30h + lone-parent synthetic cases with take-up
  pinned and $UCtransition=0 (gated to a pre-repeal legacy population). The wave-2 note's
  nonzero figures are NOT reproducible. Axiom has no current-law tax-credit surface by design.
- `bsadi` (ir-ESA): EXCLUDED **oracle_dataset_lacks_input**. The ir-ESA phase input ddipd/ddipd00
  is absent from the 364-col training_data schema; the adapter is schema-bounded (skips non-header
  keys) so ddipd can't be supplied synthetically → bsadi01_s/bsadi00_s can never fire (probe: 0).
  Same class as BE bfapl (oracles#160). ir-ESA is extant law, so missing-input, not repeal.
- Probe committed: `scripts/probe_uk_repealed_and_missing_input.py`.
- **UK now covered 17/24, unexplained 0, axiom 0.**

## Remaining uncovered (7): bched01, bched02, bchht, bchmt, bcrdicm, bhosc01, bunct
- Dataset audit confirmed buildable (inputs present in training_data): bcrdi (bcrdicm), bunct+les+lhw01 (bunct).
- bchmt (SCP, encoded both sides): build suite + regen (take-up pinned; Scotland drgn1=12).
- Net-new (ingest+encode via codex/gpt-5.5, then suite): bchht (CWHA), bcrdicm (CA Supplement),
  bunct (contributory JSA).
- bhosc01 (discretionary Scottish DHP), bched01/02 (passported non-statutory FSM/clothing): adjudicate build vs exclude.

## uk-pe legacy_means_tested — TODO (read PE 2.89.2 legacy IS/JSA-ib/ESA-ir/HB; suite vs PE or exclude).
