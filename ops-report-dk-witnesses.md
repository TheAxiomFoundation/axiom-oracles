# DK witness cases and dispositions (D3)

Status: **SHIP-READY — all three witnesses executed and dispositioned.**

## Execution provenance

- Branch: `d3/dk-conformance`; changes committed locally only and never pushed.
- All three final comparisons ran through `scripts/regenerate_euromod_dk.sh`
  with EUROMOD release J2.0+, dataset `DK_training_data`, the x64/coreclr
  runtime, and pinned Axiom engine
  `05eac9d2f89dabe5c6673176260762cef3a58f47`.
- The committed reports were regenerated against clean `rulespec-dk/main` at
  merge `9986b6035c4e557b9b40645dfe2f3e4cffb6037c`, which contains PR #16 head
  `bca3fdc` and the couple pipeline.
- The execution environment matched the regeneration script exactly:
  `EUROMOD_PYTHON=~/.venvs/axiom-euromod-x64/bin/python`,
  `DOTNET_ROOT=~/.dotnet-x64`, `PYTHONNET_RUNTIME=coreclr`, and
  `AXIOM_RULESPEC_REPO_ROOTS=$HOME/TheAxiomFoundation` (with a writable offline
  uv cache inside `/private/tmp`).
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

- New suite/case: `dk-child-youth-benefit-couple` /
  `dk-child-youth-benefit-couple-age5-yem1500000-spouse0`, using three EUROMOD
  rows: married head (`yem=125,000` monthly), married spouse (`yem=0`), and
  their age-5 child.
- Comparison level: **household sum**. The Axiom surface is per recipient, so
  the adapter executes the `earner` and `non_earner` Person rows and sums those
  two outputs. The EUROMOD adapter independently sums `bfachnm_s` over the same
  household. This keeps both engines at one documented aggregation level.
- Executed EUROMOD `tintbto_s`: **1,380,000**. The bridge writes that value only
  to the earner's two § 1 a income-basis records; the non-earner's own basis
  remains zero.
- Independent statutory derivation: § 5, stk. 3-4 establish the per-payment
  cadence, with four quarterly payments for this age-5 child. Section 4, stk. 1
  splits each **4,191** payment and rounds the half upward, yielding
  `4 × 2,096 = 8,384` per holder. Section 1 a then tests income *hos
  modtageren af ydelsen* — the recipient's own income.
- Axiom earner: `1,380,000 − 917,000 = 463,000` excess; the 2 pct. reduction
  is **9,260**, which exhausts the **8,384** share, so the executed result is
  **0**. Axiom non-earner: own basis **0**, so the executed result is **8,384**.
  Executed statutory household sum: **8,384**.
- EUROMOD DK_2025 executed **7,504** (the raw binary-float payload was
  `7503.999999999998`). This equals `16,764 − 9,260`, consistent with the
  reported pre-2022 spousal/couple test. The executed signed report delta
  (`EUROMOD - Axiom`) is **−880**.
- Disposition ID: `euromod-dk-bfachnm-pre2022-spousal-taper`;
  `upstream_engine_gap`; linked to
  <https://github.com/ec-jrc/JRC-EUROMOD-software-source-code/issues/18>. The
  disposition records the full § 4, stk. 1 + § 5, stk. 3-4 + § 1 a arithmetic
  and the ministry's two ligedeling/own-income quotations from
  `reference/dk-satser/provenance.json`.
- Report summary: **0/1 raw matches (0%)**, **100% explained**, **0
  unexplained**.
- Committed dashboard report:
  `dashboard/public/data/axiom-euromod-dk-child-youth-benefit-couple.json`.

## Verification

- `scripts/regenerate_euromod_dk.sh`: all three live comparisons completed with
  the exact values above against `rulespec-dk` merge `9986b60`.
- Combined executed result: **7/10 raw matches (70%)** and **3/3 mismatches
  dispositioned as upstream engine gaps**, for **100% explained** and **0
  unexplained**. The original seven 2025 controls remain raw matches.
- Exact report assertions pin all three mismatch values and signed deltas, all
  three disposition IDs, the combined counts, the original seven controls, and
  witness 3's Axiom component outputs (`earner=0`, `non_earner=8,384`).
- `UV_CACHE_DIR=... UV_OFFLINE=1 uv run --with pytest python -m pytest tests/
  -q -k 'dk or disposition'`: **87 passed, 2,495 deselected**. This is the same
  selector that previously selected 83 tests; the new DK coverage raises the
  count to 87. It passed without `--ignore` exclusions.
- Focused adapter, bridge, grid, and comparison-config tests: **149 passed**.
- Ruff: `check` and `format --check` clean on every Python file changed by this
  work.
- Dispositions: **94 files schema-valid**; all three DK dashboard reports are
  consistent; all three served disposition artifacts have exact YAML parity.
- Generated-data checks clean: DK grids, affected map, exercise census,
  freshness/vacuous gate, dashboard overview, and the packaged/dashboard
  EUROMOD issue-ledger mirror (**4 inventory tests passed**).
- Conformance composition, universe, scoreboard, and unexplained-ratchet checks
  exited clean. The universe checker reported its existing no-op notices for
  unrelated local PolicyEngine UK/US checkouts whose installed versions do not
  match their pins; the verified EUROMOD universes remained clean.

## Local commits

- `19ad129f0` — `dk: add pension gross-up witness for ec-jrc 20`
- `d35f90944` — `dk: add 2023 supplement witness for ec-jrc 19`
- `750ea883f` — `dk: finalize witness reports and verification`
- Witness 3 implementation, live reports, and this updated report are committed
  together in the final local commit; nothing was pushed.


## Correction addendum (2026-08-14, post-audit)

- The gross-up witness as first built supplied the 61.200 kr.
  within-seven-years-of-pension-age PBL § 16 cap to an age-35 recipient —
  legally impossible for that person (the ordinary 2025 cap is 9.400 kr.).
  Caught in the clean-context adversarial audit of PR #473. Rerun with the
  ordinary cap: EUROMOD 11.184 vs Axiom 11.497,33, delta −313,33 (2 pct. of
  the 15.666,67 grossed-up capped contribution). The disposition and the
  suite constant now carry the two-cap rule with citations.
- The 'SHIP-READY' verdict above therefore overstated the first build; it
  became accurate only after this correction.
- The couple witness commit omitted from the earlier commit list:
  e754cdebb (dk: add couple spousal-taper witness for ec-jrc 18).
