# US TANF fan-out wave 3 — PROGRESS

Goal: cover more of the 19 uncovered us-pe TANF rows. Order: DE ME HI, then MS ND NC SD, then TX MT IL OR.
Covered already (do not touch): AL AZ CA CO GA KS MN NY WA.

## Infra (done this session)
- Signing key `agent/axiom-encode-apply-signing-key` PRESENT; corpus key PRESENT; codex CLI 0.144.0 (local ChatGPT auth ~/.codex/auth.json). NO cloud/API billing.
- Fresh wave3 worktrees from origin/main:
  - rulespec-us: `~/_axiom-worktrees/us-tanf-wave3/rulespec-us` (branch us-tanf-wave3-de). `~/rulespec-us` symlink repointed here.
  - axiom-oracles: `~/_axiom-worktrees/us-tanf-wave3/axiom-oracles` (branch us-tanf-wave3-de-oracle). `~/axiom-oracles/programs` symlink repointed here.
- Roots synced: `~/.axiom-oracles/roots/{rulespec-us,rulespec-us-al,rulespec-us-ga,rulespec-us-de}`.
- Harness validated: GA suite re-ran 1896/1897 (matches pinned). Toolchain (compose+Rust compile+PE microsim+ECPS) works.
- CORPUS GOTCHA: stray `~/TheAxiomFoundation/axiom-corpus/provisions/` (1 tracked BE file) shadows canonical `data/corpus/provisions`. Pass `--corpus-path ~/TheAxiomFoundation/axiom-corpus/data/corpus` to encode.
- ENCODE reviewers hit 401 (no Anthropic auth for reviewer sub-agents); use `--skip-reviewers` (oracle at population scale is the real gate).

## Reusable fixes (apply by default)
1. AU-size chart index declared `dtype: Count` (integer subscript). Encoder already did this for DE budget_size_index.
2. Earned-income deduction projected at HOUSEHOLD scope (per-person collapses to None for zero-earner units).

## DE (in progress)
- Corpus: `de-tanf-rules` (16 DE Admin Code 4000). §4004.2 disregards, §4007.2 payment-standard+SoN tables, §4008.1.1 grant.
- PE de_tanf: grant = min(payment_standard, 0.5*max(SoN - countable_income,0)); SoN=0.75*spm_unit_fpg; payment std {1:201..8:681}+$69/extra (const since 2002); $90 work exp + $30 + 1/3 (PE uses 0.33); gross test 1.85*SoN; deficit rate 0.5.
- INSIGHT: payment standard dominates for zero-income units (0.5*SoN >> payment_std) → benefit = payment_standard; matches PE exactly. SoN precision only affects income units (dispositionable, like GA's 1 residual).
- Leaves encoded+applied (compile=yes ci=yes, all grounded), in rulespec-us/us-de/regulations/title-16/4000-financial-responsibility/:
  - `4007-standards-of-need-and-payment-standard.yaml` → de_tanf_payment_standard (free input: number_people_in_budget)
  - `4008-financial-eligibility-and-grant-computation.yaml` → de_tanf (imports payment std). Free inputs: applicable_tanf_standard_of_need, gross_income, total_wage_earner_earnings, wage_earner_count, child_care_expenses, unearned_income, thirty_plus_one_third_disregard_applies.
- DONE 2026-07-10: **DE 781/781 = 100.0%, 0 residuals** (like AL). Payment-standard dominance held exactly.
  - rulespec-us commit da8ce234 (DE leaves 4007/4008 + signed manifests).
  - Program `programs/us-de/tanf/fy-2026.yaml`: number_people_in_budget declared Count (=assistance_unit_member_count, reusing GA's hh_size slot); benefit gated on household_has_minor_or_pregnant_member; de_tanf_annual_benefit = de_tanf_monthly_benefit*12.
  - Populace block (append): applicable_tanf_standard_of_need via table_by_hh_size = 997.50+355*(N-1) (0.75*monthly FPG, CONTIGUOUS_US 2026 15960/5680); gross_income + total_wage_earner_earnings = monthly AU sums; wage_earner_count=1 (GA-style single household deduction); child_care_expenses=0; thirty_plus_one_third_disregard_applies=true; unearned_income reuses shared NY monthly-unearned slot.
  - Concept us-de:regulations/title-16/4000-financial-responsibility#de_tanf_benefit -> de_tanf. comparison de-tanf-ecps.yaml (FIPS 10). conformance de_tanf row suite=de-tanf-ecps. test_conformance live_pe_suites += de-tanf-ecps. Scoreboard us-pe covered 41->42 (29.93->30.66%). 89 passed/3 skipped.
  - No disposition file (0 residuals, like AL). programs mirrored to rulespec-us/programs/us-de.

## NEXT (order): ME HI, then MS ND NC SD, then TX MT IL OR
ME/HI: corpus ingested, leaves NOT encoded -> Step 2 encode via LOCAL codex (--backend codex --model gpt-5.5 --skip-reviewers, --corpus-path ~/TheAxiomFoundation/axiom-corpus/data/corpus). ME PE me_tanf; HI PE hi_tanf. Then compose/oracle/register as DE.

## Merge discipline
Oracle PRs one at a time; rebase on origin/main immediately before; regenerate 3 aggregates; concept_mappings/mapping append-only; NO admin-merge; update live_pe_suites in tests/test_conformance.py per new suite.
