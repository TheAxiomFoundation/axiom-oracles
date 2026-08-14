# DK witness cases and dispositions (D3)

Status: **PARTIAL — witness 3 skipped pending the couple-pipeline merge.**

## Execution provenance

- Branch: `d3/dk-conformance`; changes committed locally only and never pushed.
- Final comparisons ran through `scripts/regenerate_euromod_dk.sh` with EUROMOD
  release J2.0+, dataset `DK_training_data`, the x64/coreclr runtime, and pinned
  Axiom engine `05eac9d2f89dabe5c6673176260762cef3a58f47`.
- Both committed reports were finally regenerated against an isolated clean
  snapshot of `rulespec-dk/main` at
  `75923db8b3b759133275ec12e33391fa1109244d`. The shared rulespec checkout was
  switched externally to the couple-feature branch late in the run; isolating
  `main` prevented that unrelated checkout change from altering report
  provenance.
- The repository has no `upstream` remote, and a live `origin/main` fetch was
  blocked by the sandbox's network restriction. The requested existing
  branch/worktree was therefore preserved without rebasing; no dirty user data
  was removed (`.axiom/` remains untracked and untouched).

## Witness 1 — ec-jrc #20 pension gross-up

- Case: `dk-child-youth-benefit-age5-yem1300000-pension60000` in the existing
  `dk-child-youth-benefit` suite.
- The case records `qualifying_pension_contributions: 60000` in neutral metadata
  and supplies
  `total_contributions_to_qualifying_pension_accounts=60000` to the § 1 a
  module. No EUROMOD column was added.
- Executed `tintbto_s`: **1,196,000** on both bridged § 7-basis inputs.
- Axiom: `60,000 / 0.6 = 100,000` gross-up; basis **1,096,000**; excess
  **179,000**; reduction **3,580**; benefit **13,184**.
- EUROMOD DK_2025: no contribution gross-up; excess **279,000**; reduction
  **5,580**; benefit **11,184**.
- Executed signed report delta (`EUROMOD - Axiom`): **−2,000**; absolute gap
  **2,000**, exactly 2 pct. of the 100,000 gross-up.
- Disposition ID:
  `euromod-dk-bfachnm-taper-pension-grossup-absent`;
  `upstream_engine_gap`; linked to
  <https://github.com/ec-jrc/JRC-EUROMOD-software-source-code/issues/20>.
- Report summary: **7/8 raw matches (87.5%)**, **100% explained**, **0
  unexplained**. All seven original cases still match raw.
- Committed dashboard report:
  `dashboard/public/data/axiom-euromod-dk-child-youth-benefit.json`.

## Witness 2 — ec-jrc #19 2023 supplement

- New suite/case: `dk-child-youth-benefit-2023` /
  `dk-child-youth-benefit-2023-age5-yem300000`.
- New comparison: `dk-child-youth-benefit-2023-euromod`, selecting
  `euromod_system: DK_2023` and `euromod_dataset: DK_training_data`. The live
  connector accepted `DK_training_data` directly, so no dataset-name/template
  gating workaround was needed.
- The logical case period is 2023. Axiom evaluates on `2025-06-01` because the
  composed pipeline's first executable version starts 2025-05-12; explicit
  inputs `percentage_change_rounded_to_one_decimal_place=0.156`,
  `payment_year_has_additional_statutory_increase=true`, and the 2023 threshold
  852,600 preserve the 2023 arithmetic.
- Axiom: `round12(13,452 × (1 + 0.156 − 0.039)) = 15,024`; plus **660** gives
  **15,684**, matching `reference/dk-satser/satser_annual.csv`.
- EUROMOD DK_2023 executed benefit: **15,624** (15,024 base plus its 600
  constant).
- Executed signed report delta (`EUROMOD - Axiom`): **−60**.
- Disposition ID: `euromod-dk-2023-bfachnm-supplement-600-vs-660`;
  `upstream_engine_gap`; linked to
  <https://github.com/ec-jrc/JRC-EUROMOD-software-source-code/issues/19>.
- Report summary: **0/1 raw matches (0%)**, **100% explained**, **0
  unexplained**.
- Committed dashboard report:
  `dashboard/public/data/axiom-euromod-dk-child-youth-benefit-2023.json`.

## Witness 3 — ec-jrc #18 couple taper

**SKIPPED-PENDING-MERGE.** At the required start-time check,
`rulespec-dk/main` (`75923db8`) did not contain
`dk/statutes/composed/boerne-og-ungeydelse-couple-pipeline.yaml`. Per the task
gate, work on this item stopped: no couple comparison, case suite, concept
registration, run, or disposition was added. A later external checkout switch
made the in-flight feature branch visible, but it did not change the required
start-time `main` result.

## Verification

- `scripts/regenerate_euromod_dk.sh`: both live comparisons completed with the
  exact values above.
- Exact report assertions: both mismatch values, signed deltas, disposition
  IDs, explained rates, and unexplained counts passed; the original seven 2025
  cases remained raw matches.
- `UV_CACHE_DIR=... UV_OFFLINE=1 uv run --with pytest python -m pytest tests/
  -q -k 'dk or disposition'`: **83 passed, 2,491 deselected**. This broader run
  passed without any `--ignore` exclusions, so the four prior known-broken file
  exclusions were not needed to make the requested selection green.
- Ruff: `check` and `format --check` clean on every Python file changed by this
  work.
- Dispositions: 93 files schema-valid; both DK dashboard reports consistent;
  both served disposition artifacts have exact YAML parity.
- Generated-data checks clean: DK grids, affected map, exercise census,
  freshness/vacuous gate, and dashboard overview.
- Conformance compositions, conformance universes, and scoreboard remained
  clean; no DK couple surfaces were introduced.

## Local commits

- `19ad129f0` — `dk: add pension gross-up witness for ec-jrc 20`
- `d35f90944` — `dk: add 2023 supplement witness for ec-jrc 19`
