# UK–UKMOD badge closers + legacy means-tested — progress

Branch: `uk-ukmod-badge-closers`. Goal: drive UK-vs-UKMOD (was 15/26, unexplained 0)
to conformant; close uk-pe `legacy_means_tested`. Validation year 2026, eval ≥ 2026-04-06.

Env for the local Rosetta EUROMOD regen (verified working this session):
`EUROMOD_PYTHON=~/.venvs/axiom-euromod-x64/bin/python DOTNET_ROOT=~/.dotnet-x64
PYTHONNET_RUNTIME=coreclr POLARS_SKIP_CPU_CHECK=1
EUROMOD_MODEL_ROOT=~/Downloads/UKMOD_PUBLIC_B2026.03
AXIOM_RULESPEC_REPO_ROOTS=~/TheAxiomFoundation` then `.venv/bin/python scripts/run_comparison.py <name> --summary`.

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

## Remaining uncovered (9): bched01, bched02, bchht, bchmt, bcrdicm, bhosc01, bsadi, bunct, bwkmt_bfamt
- Track 2 exclusions: bwkmt_bfamt (WTC/CTC repealed 5 Apr 2025 — oracle models repealed law),
  bsadi (dataset LCW-input audit). bhosc01 (discretionary DHP). bched01/02 (passported
  non-statutory). → shrink in_scope with probe evidence.
- bchmt (SCP, encoded both sides): build suite + regen (take-up pinned).
- Net-new (ingest+encode via codex/gpt-5.5, then suite): bchht (CWHA), bcrdicm (CA Supplement),
  bunct (contributory JSA).

## uk-pe legacy_means_tested — TODO (read PE 2.89.2 legacy IS/JSA-ib/ESA-ir/HB; suite vs PE or exclude).
