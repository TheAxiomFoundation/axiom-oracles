# PROGRESS — us-pe reconciliation (drive `unexplained_total` 23,138 → 0)

Predecessor: **#224** stood up the us-pe conformance universe (measurement only,
day-one unexplained=23,138). This lane (`us-pe-reconciliation` from `origin/main`
`2ad66f9`) dispositions/attributes those residuals. Oracle pin
policyengine-us==1.767.3, validation year 2026. Pattern: BE reconciliation
(or#177) — a day-one universe registered 16 existing suites whose comparison
residuals were never dispositioned into conformance accounting.

## Scoreboard entry point (origin/main)

```
us-pe  policyengine-us_1.767.3/us  in_scope=140 covered=27 (16 suites)
       unexplained_total=23138  axiom_attributed_open=0  oracle_attributed=0  conformant=false
```
Coverage gap (113/140 uncovered) is OUT OF SCOPE (coverage waves come after
unexplained=0). This lane touches **only** the 23,138 unexplained on covered suites.

## Decomposition — unexplained by suite × concept-output × signature

| suite | unexpl | concept-output | signature | provisional cause |
| --- | ---: | --- | --- | --- |
| fiit-ecps | 18791 | (12 federal rows share one report) | | |
| — eitc | 16660 | eitc_earned_income / eitc_phased_in | axiom includes partnership SE income in EITC earned income; PE-US **1.729.0** (report engine) omits it | **RESOLVED — upstream engine gap / vintage** (see below) |
| — tax_before_credits | 2118 | income_tax_main_rates | float/rounding noise, \|diff\|≤$5.83 on values to $2.8M (rel ≤1e-6) | explained_residual (bracket rounding) |
| — capital_gain | 8 | adjusted_net_capital_gain | float noise, \|diff\|≤$3.25 on values to $8.3M | explained_residual (float) |
| — ctc | 5 | ctc_phaseout_amount | exactly ±$50 = one $1,000 excess-AGI increment ×5% (26 USC 24(b)); credit fully phased out both sides | explained_residual (excess-AGI rounding) |
| ssi-ecps | 4044 | (truncated) | TBD | UNRESOLVED — needs inputs |
| ca-tanf-ecps | 177 | ca_tanf_benefit | structural: PE=0 in 66, axiom=0 in 39, big $ diffs | UNRESOLVED — needs inputs |
| medicaid-magi-co-ecps | 46 | adult_eligible(45)/older_child(1) | boolean eligibility flips: axiom False/PE True ×38, axiom True/PE False ×8 (42 CFR 435.119) | UNRESOLVED — needs inputs/params |
| ny-tanf-ecps | 36 | ny_tanf_benefit | PE=0 in 15, big $ diffs | UNRESOLVED — needs inputs |
| co-state-income-tax-ecps | 31 | liability | $ diffs $19–$1107, negative liabilities (refundable credits) | UNRESOLVED — needs inputs |
| ks-tanf-ecps | 6 | ks_tanf_maximum_benefit | axiom 3708 vs PE 2688 (Δ$1020); one PE=0 | param-groundable |
| az-tanf-ecps | 4 | az_tanf_benefit | small $ diffs $37–$52 | UNRESOLVED — needs inputs |
| co-tanf-ecps | 3 | co_tanf_benefit | PE=0 in 2, big diffs | UNRESOLVED — needs inputs |
| **TOTAL** | **23138** | | | |

fiit + ssi = 22,835 (98.7%). eitc alone = 16,660 (72%).

## Architecture findings that shape feasibility

1. Scoreboard reads `summary.dispositioned.unexplained_count` from each committed
   `dashboard/public/data/axiom-policyengine-<suite>.json`
   (`= mismatch_count − classified_rows`). `dispositions.py` classifies **per-row**
   against `report["mismatches"]`.
2. **fiit and ssi reports are TRUNCATED** to 1000 of 18,791 / 4,044 rows
   (`dashboard_truncation`). Per-row dispositions on the committed truncated file
   cannot reduce the full count — the reduction must merge on the FULL set before
   slimming (a `run_comparison.py` re-run). The other 7 suites (303 mismatches)
   have ALL rows on disk → per-row disposition + `apply_dispositions.py` works now.
3. Reports carry outputs only, **not inputs**. Rigorous attribution needs
   per-record inputs; source is the pinned Populace artifact, present in local HF
   cache: snapshot `d8f5cff65f36205a613cb144fd97db3087bbd82a/populace_us_2024.h5`
   (revision `populace-us-2024-f0af251-...`, DENSE f0af251 build).
4. Vintage gap: reports generated vs **PE-US 1.729.0** (Populace build version);
   universe pins **1.767.3**. OBBBA-era shifts plausible.

## Plan / status

- [x] Worktree from origin/main; decomposition committed (this file).
- [ ] Ground fiit rounding signatures from report values + formula reading.
- [ ] Extract per-case inputs from populace_us_2024.h5 for divergent case_ids.
- [ ] Attribute each signature (axiom→rulespec-us issue/axiom_attributed_open;
      PE→policyengine-us issue/oracle_attributed; dataset→disposition citing
      populace issue; plumbing→fix suite).
- [ ] Dispositions with AST-checked arithmetic; issues each side.
- [ ] apply_dispositions + scoreboard + ratchet + snapshot per batch; ratchet down.
- [ ] fiit/ssi: author dispositions; regenerate if feasible, else document re-run.

## RESOLVED — EITC earned-income divergence (16,660 = 72% of total)

Root cause, verified on 8 concrete tax-unit records against the pinned Populace
`person/table` inputs (`~/PolicyEngine/policyengine-us/.venv/bin/python` reading
the h5 directly): **axiom's rulespec `earned_income` (us:statutes/26/32/c/2)
includes partnership self-employment income (`partnership_se_income`) as net
earnings from self-employment per 26 USC 32(c)(2)(A)/§1402(a), netting the actual
½ SE-tax deduction; the PE-US engine the committed report was generated against
(1.729.0) omits partnership SE income from `eitc_earned_income`.**

Airtight arithmetic (axiom eitc_earned_income reproduced to the cent from inputs):
- tu 154343: partnership 126,692, no other earnings → axiom 117,741.43 =
  126,692 − ½·SE-tax(126,692·0.9235); PE 0.00. **exact.**
- tu 154463 / 161849: partnership 128,316 → axiom 119,250.94; PE 0.00. **exact.**
- tu 17243: partnership 23,099 → axiom 21,466.75; PE 0.00. **exact.**
- tu 154392: emp 62,785 + partnership 43,313 → axiom−PE = 108,896.96−68,643.48 =
  40,253.48 = 43,313·0.9294 (partnership netted). **exact delta.**
- tu 163592 (partnership 1, control): axiom 62,625.93 vs PE 62,625.01 = $0.92
  rounding — correctly NOT a partnership case.
Population: **6,269 tax units** carry non-dependent `partnership_se_income`
shifting EITC earned income >$5 (×2 outputs eitc_earned_income+eitc_phased_in
≈ the bulk of 16,660; remainder = SE-netting/phased-in-cap/float on non-partnership units).

Attribution: **oracle/vintage, NOT axiom.** PE-US **#8614** "Split partnership and
S-corp income inputs" (merged 2026-06-14) added `partnership_self_employment_net_earnings`
to `eitc_earned_income`'s sources; **#8337** (2026-05-19) created the variable.
Report engine 1.729.0 (uploaded 2026-06-14T18:05Z) predates the partnership
plumbing landing in the data pipeline; the **pinned oracle 1.767.3**
(2026-07-07) contains #8614. So the committed fiit report is **stale** — run
against 1.729.0, not the pinned 1.767.3. Remediation = regenerate fiit against
the pinned oracle (with a Populace build wiring the split partnership input), not
a disposition.

## Why the number can't be ratcheted from committed artifacts alone

- **fiit (18,791) + ssi (4,044) = 98.7% are truncated** (1000 of N rows on disk).
  `apply_dispositions` classifies per-row against the truncated array, so it
  cannot reduce the full `unexplained_count`; and authoring `dispositions/fiit-ecps.yaml`
  would make `apply_dispositions.py --check` rewrite the committed report's
  `summary.dispositioned` with a **partial, mechanism-mismatched** number (only
  the ~1000 present rows), baking a wrong count / breaking CI. The correct
  reduction requires a harness re-run that merges dispositions (or the fixed
  oracle) on the full row set **before** slimming — out of budget/reproducibility
  here (needs isolated PE-US install + a 3.88M-case run + a 1.767.3-compatible
  Populace build).
- The 7 non-truncated small suites (303 mismatches) are per-row dispositionable,
  but each structural signature (TANF benefit/eligibility, medicaid MAGI flips,
  state-liability) needs per-record inputs to attribute without blanket-dispositioning;
  ks-tanf is a household-size-shifted benefit-standard disagreement (axiom vs PE
  KS payment standard), plausibly axiom off-by-one — needs size + param-vintage
  confirmation before an issue/disposition.

No dispositions committed and no issues filed: the dominant cause (72%) is an
already-fixed upstream PE bug (#8614) surfacing as report staleness, not an open
defect; the small-suite causes are scoped but not yet verified to issue-filing
confidence. Committing a reduction from truncated reports would be fabricated.

Discipline: no blanket dispositions; ≥3 concrete records per signature;
corpus-grounded amounts; oracle merges serialized; NO admin-merge; sentence case.
