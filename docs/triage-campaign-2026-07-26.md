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
