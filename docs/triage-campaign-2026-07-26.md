# Full-residual triage campaign — working state

Goal (Pavel, 2026-07-26): explain all differences in all programs; only
verified classes get dispositions; the remainder must be precisely
characterized. Method: per-row verification against persisted household
evidence (input/output panels), PE parameter surfaces as oracle ground
truth, PE-side decomposition where our reports can't decide.

## Ledger (start: 14,479 → **4,611**; batch 4 = AZ decomposed + NC harvested)

AZ (597): fully explained — composition bug (snap_eligible binds
na_budgetary_unit_is_eligible; module not imported → constant-false;
rulespec-us#1116); one-directional signature verified 597/597. En route,
three real mapping fixes landed (AZ state-manual vocabulary income slots,
expanded-test + CE-considered statewide flags) — needed once the
composition is fixed. NC harvested: 124→99 post-SE-fix, 11 BBCE rows
dispositioned. NY/FL/CA reruns remain machine-bound (weekly regen).

Fleet under the self-employment fix: AL 79→53, GA 300→250, MA 262→255,
SC 206→180, TN 89→68 — real eliminations. BBCE dispositions re-verified
on the new baselines: AL 10, GA 170, MA 206, SC 126 (TN non-BBCE, CO
already at 1). Pending disk: AZ/FL/NY/CA/NC reruns under the fix.

| Block | Was | Now | Mechanism / next step |
|---|---|---|---|
| ca-federal-schedule-tax-spsm | 8,841 | **97** | AMT-overwrite class accounted (dispositioned block emitted by generator; regenerated + determinism reconfirmed 99.09%) |
| ca-snap-ecps | 684 | 441 merged (#364) | CORRECTION pending: PE keeps CA net test (net_applies=True) — replace merged classes with corrected 210 gross-band + 33 asset-waiver; the old net-fail arm rows return to raw/deduction-divergence |
| ga-snap-ecps | 300 | pending write | VERIFIED: 111 hheod-gross-band + 59 net-waiver (GA net_applies False) = 170; write dispositions |
| al-snap-ecps | 79 | pending | 9 net-waiver + 1 band verified; 61 other-direction |
| ny/tn-snap-ecps | 354/89 | pending | NY only 5 band (NY non-hheod 1.3); TN non-BBCE — other mechanisms |
| az/fl/ma-snap-ecps | 597/834/262 | RERUNNING | pre-outputs reports; Phase-1 rerun in flight, then classifier |
| nc/sc-snap-ecps | 124/206 | RERUNNING/pending | reports purged; rerun (single-process ok), then classifier |
| co-tax-intersection-taxsim | 1,703 | 72 verified banked (accounting blocked) | NOT selector drift — never triaged. Fingerprints found: taxable_income −400 singles = base std-ded vintage; std-ded +2,050 (single) / +1,650 (per aged spouse) = AGED 65+ additional deduction TAXSIM misses (verify page/sage≥65 per row); itemizer flips (+16,100/−8,050); tax_before_credits/liability = downstream composites. CONFIRMED via pull-one-case: +2,050 row is page=29 (NOT aged) → the increments are the BLINDNESS 63(f) class (wave's taxsim-input-lacks-blindness-column entry — extend its selector; verify diff == Σ member blind increments against axiom input records member blind facts). −400 singles: NOT base vintage (PE=TAXSIM=16,100). Deep-tax rows: e.g.
ecps-tax-unit-59063 (ltcg 1.32M): taxable −400.004 (SS-taxability or
cap-gains flow rounding?) AND tax_before_credits axiom=0 vs 240,718 with
liability within 206 — cap-gains worksheet routes tax through different
concept buckets = probable bridge-artifact/mapping class for
cap-gains-heavy filers. Needs wave-grade per-concept treatment. Downstream rows: composite selector = case in any member class. |
| co-state-income-tax-taxsim | 530 | todo | no dispositions file; fresh triage (see promotion-wave class patterns) |
| income-tax-liability grids (~14 suites × ~6) | ~85 | todo | wave-era classes (fixture uprating vintage etc.); read one suite, generalize |
| small suites (nyc-synthetic 12, medicaid-thresholds 12, ak-apa 9, md-tca 5, ...) | ~40 | todo | individual reads |

## PROVEN: AL 79 → 53 after the self-employment mapping fix (−33%)

## MAJOR FINDING (2026-07-26, verified 12/12 on AL)

The SNAP axiom-side (axiom-pays/axiom-eligible) class root cause is a
PROJECTION BUG, not law divergence: the mapping table's
snap_gross_monthly_earned_income rule sums only YEARLY_EARNED_INCOME
(wages); SELF_EMPLOYMENT_INCOME is loaded as a person fact but never
mapped, so business owners project as zero-income households. PE counts
self-employment in snap_earned_income netted at exactly 0.6 (verified:
39771/66285, 18036/30061). Dead hypotheses, tested: TANF/SSI imputation
(0/12), assets (asset_ok true 12/12). FIX the mapping (include SE,
document netting choice), rerun states — this class should vanish and
raw match rates rise. Same class likely explains axiom-side rows in all
states (CA 70 axiom-pays + 69 axiom-eligible etc.).

## Batch 9 (SPSM close-out)

Parser cell-overflow bug found and fixed: 8-digit values (an \$11.6M
filer) overflowed the extract's 8-char cells leftward; fixed-cell
slicing split them and manufactured 140 "mismatches" over perfect
agreement (schedule(11,600,140)=3,802,819 == SPSM to the dollar).
Digit-aware backoff parsing; +30 taxfilers recovered. Pension-splitting
class: 16 rows verified per-row against actual household pension income
(bounded by min(own eligible pension, 50% cap)); 85 consistency-fits
REJECTED by the strict bound (different mechanism, raw). SPSM final:
967,426 compared, 8,589 AMT + 16 splitting explained, 97 raw (0.010%).

## Accounting limitation found (batch 5)

Dashboard copies truncate to the worst 1,000 mismatches; the disposition
merge annotates only visible rows, so verified classes on small-delta
rows (blindness chain 40, cap-gains bucket 32 — entries validate clean
in dispositions/co-tax-intersection-taxsim.yaml) cannot move
unexplained_count until either the per-suite cap is lifted for
2,540-row suites or dispositioned accounting reads the full report.
Fix next session; the verification itself is done and committed.

## Key facts established

- PE BBCE surface at 2026-01 (from policyengine-us 1.752.2 params,
  gov/hhs/tanf/non_cash): gross mult AL 1.3, AZ 1.85, CA/CO/FL/MA/NC 2.0,
  GA 1.3, NY 1.3, SC 1.3, TN none; HHEOD (elderly/disabled) variant: 2.0
  for AL/GA/NY/SC too; net test applies under BBCE ONLY in CA (and AL
  hheod). Map cached: scratchpad/bbce_map.json.
- Classifier (per-row, uses axiom_all_outputs): band = gil < gross ≤
  gil×(mult/1.3)×1.02 with hheod mult when any member ≥60; asset-waiver
  arm = gross_ok && resource-fail && BBCE state; net-waiver arm only
  where net_applies False.
- other_direction rows (axiom-pays/axiom-eligible/both-differ) need
  PE-side decomposition: run PE per state computing tanf/ssi/
  snap_unearned_income for the flagged household ids; verify the
  imputation hypothesis wholesale (design ready, not yet run — machine
  was busy with reruns).
- rulespec-us#1098 = CalFresh BBCE encoding request (extend to
  multi-state BBCE); axiom-oracles#362 = CA residual tracker; ratchet
  pinned unexplained 441 / axiom_open 243 (will need re-pin as classes
  land across states).

## Process guards (hard-won tonight)

- JSON-validate every dashboard/conformance file before ANY data commit.
- Direct cli invocations MUST pass suite name + stamp provenance
  (run_comparison._build_run_provenance) or conformance drops coverage.
- Reports pre-2026-07-25 lack axiom_all_outputs; verify with fresh runs.
- This machine: guard disk ≥2GB; prune superseded reports between runs;
  CA-scale needs --case-shard.

## Batch 11 (intersection: QBID rental convention + state flat-offset enrollment)

Campaign 4,048 → **3,759**. Intersection unexplained 1,530 → 1,241.

- taxsim-qbid-rental-convention-taxable-income (127 rows,
  bridge_artifact): TAXSIM idtl=2 decomposition shows TI = AGI − std
  (2026 std correct: 16,100/32,200) with ZERO QBI deduction; axiom
  follows the PE convention that rental income is QBI. TAXSIM's
  otherprop column is definitionally non-QBI, so the two engines answer
  different questions on rental-income units. Per-row verifier
  recomputes the bridge QBID (otherprop + SE − SECA ALD; phaseout
  403500/201750 start, 150000/75000 length; H.R.1 §70105 $400 floor
  gated on QBI ≥ 1000) and matched −diff within $0.05 on 127/188. The
  81-row flat −400 subset is the floor binding (high-income wage/UBIA
  phase-out extinguishes the regular deduction; the floor is not
  wage-limited). 61 TI rows failed the verifier (extra mechanisms) —
  raw.
- taxsim-co-flat-{30-8,20-7}-filing-status-offset-intersection (130+32
  rows, upstream_engine_gap): the sibling suite's triangulated TABOR
  vintage class re-observed in the intersection lane on IDENTICALLY the
  same tax-unit ids (162/163 flat rows are members; 1 non-member left
  raw); deltas within 5¢ of 30.80/20.70.
- Cascade honesty: tbc (15/115 would verify) and liability (0/123) on
  QBID cases are multi-mechanism — NOT dispositioned. AMT rows (25)
  untouched.
- Remaining intersection 1,241: tbc continuum 468, fed liability ~240,
  state non-flat ~360, TI fails 61, amt 64, ctc 13, eitc 11, std 2.

## Batch 12 (intersection: CO refundable-credit triangulation + federal credit fingerprints)

Campaign 3,759 → **3,488**. Intersection 1,241 → 970.

- taxsim-co-refundable-credit-vintage (251, upstream_engine_gap):
  triangulated against the COMPLETE 31-row axiom-vs-PE CO mismatch set
  (1,201 units; 4 contaminated ids left raw). TAXSIM idtl=2 state
  decomposition run on all 255 (scratchpad/state_only_taxsim.csv):
  divergence lives in sctc/srebate columns; net siitax goes negative on
  refundable-credit households.
- taxsim-2026-eitc-childless-schedule-applied (9): TAXSIM sits exactly
  on the 2026 CHILDLESS curve (7.65% phase-in to the cent, 664 max,
  phase-out solving to statutory 10,860 on independent incomes) for
  units WITH children; axiom sits on the with-children curve (45%×9,512
  and 40%×17,493 exact). 2 ambiguous rows raw.
- taxsim-2026-ctc-machinery-absent-refundable-arm (11): axiom equals
  statutory 2026 exactly (2,200/child + 500 ODC, or ACTC 15% cap —
  four rows match 0.15×(earned−2,500) to the cent); TAXSIM pre-TCJA
  vintage. 2 no-match rows raw.
- Remaining intersection 970: tbc continuum ~468, fed liability ~240,
  amt 64, TI verifier-fails 61, state raw 111ish, misc.

## Batch 13 (dividend-qualification pair of projection bugs — FIXED, suite rerun)

Campaign 3,488 → **3,324**. Intersection unexplained 970 → 806 (fresh
2026-07-27 report under both fixes; raw mismatches 2,540 → 2,300).

- Bug 1 (TAXSIM projection): total DIVIDEND_INCOME was mapped into
  TAXSIM's dividends column, which is qualified-only — over-preferential
  on the TAXSIM leg. Caught by the tbc ratio fingerprint: diff/dividends
  clustered exactly on bracket differentials (0.12=12%−0%, 0.07=22%−15%,
  0.09=24%−15%). Fix: qualified leaf → dividends, non-qualified
  remainder → otherprop. Regression tests added.
- Bug 2 (axiom bridge, MASKED by bug 1): person_dividend_income bound
  DIVIDEND_INCOME only, so qualified-only ECPS rows (qual leaf > zero
  total leaf) never entered axiom AGI while still hitting the
  preferential worksheet. Surfaced as 238 new TI mismatches after fix 1
  broke the shared blind spot. Fix: AGI leaf takes max(total, qualified)
  per person, mirroring _sum_dividends.
- Suite-stamp trap AGAIN (3rd occurrence): registry rerun stamped
  reports/-side suite as nyc-synthetic because parameters.suite was
  missing (dashboard.suite alone only fixes the dashboard copy). ROOT
  FIX: parameters.suite added to comparisons/co-tax-intersection-
  taxsim.yaml; report patched; add parameters.suite to any suite you
  rerun directly.
- All 17 disposition entries survived the rerun (no orphans); QBID 127
  and state classes intact; explained_residual coverage fell 426 → 351
  because the fix converted those rows to MATCHES.
- Remaining 806: tbc ~370, fed liability ~300 (heavily SECA/FICA-
  correlated), amt 41, TI 66, state ~110, eitc/ctc/std tails.

## Batch 14 (tbc bucket-routing extension, post-dividend-fix)

Campaign 3,324 → **3,169**. Intersection 806 → 651.

- capgains-worksheet-bucket-routing-tbc-postdividendfix (155,
  bridge_artifact): the tbc-only signature — final liability agrees
  within $15 on every row (no liability mismatch exists) with
  ctc/eitc/cdcc/amt all compared and matched; TAXSIM idtl=2 rerun on
  all 155 confirms axiom's tbc bucket + the preferential-rate worksheet
  component reconstructs TAXSIM v28 exactly (22,381.42 + 5,449.08 =
  27,830.50 = fiitax). 9 small tolerance-band tbc-only rows left raw.
- The 134 [liability+tbc] pair cases are genuinely multi-mechanism
  (deltas never equal) — next target, needs per-case decomposition.
- Remaining intersection 651: pairs 268, amt-involved ~80, TI 57,
  singles/misc rest.

## Batch 15 (surtax-scope liability class + tail forensics)

Campaign 3,169 → **3,155**. Intersection 651 → 637.

- taxsim-fiitax-surtax-scope-liability (14, bridge_artifact): axiom's
  liability bucket = 26 USC 6401 chapter-1 tax; TAXSIM fiitax folds in
  NIIT (ch. 2A) + additional Medicare (ch. 2). liab_diff ==
  -(niit+addmed) within $0.60 on every selected row, idtl=2 verified.
- Fingerprints found but NOT yet bankable (next leads):
  * +67.40 per filer (134.80 MFJ) on age-60+/senior rows — 8 cases,
    driver unidentified (not Sch R phase-in, not SS worksheet — one row
    has gssi=0).
  * −148.1x flat remainder on ultra-high-income rows (12) after surtax
    removal — suspiciously 0.37 × 400.4 but no QBI gate present.
  * fed-liability-only rows (24): thousands-scale with tbc matched —
    likely an uncompared credit (PTC-like) on the axiom side; needs
    axiom-side credit chain dump.
  * [amt,liability] ultra-rich (12): surtax composite holds to ~1e-4
    relative but residual hundreds — AMT interaction detail.
- Remaining intersection 637; next big blocks are these forensic tails
  plus TI 57 and amt 41.

## Batch 16 (state suite mirror of the refundable-credit class)

Campaign 3,155 → **2,794**. co-state-income-tax-taxsim 368 → **7**
(99.42% explained).

- taxsim-co-refundable-credit-vintage mirrored into the state suite:
  361/368 remaining rows triangulate clean against the complete 31-row
  axiom-vs-PE mismatch set (same concept, same 1,201-unit population);
  7 contaminated ids stay raw. Same TAXSIM sctc/srebate decomposition
  evidence as the intersection-suite class.
