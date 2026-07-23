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

## SSI (4,044 = 17.5%) — probable axiom resource-screen gap (needs confirmation)

All 4,044 are `ssi_benefit`; **94% (936/1000 sampled) have PE=0 while axiom
awards a positive SSI benefit.** Concrete records (spm-unit inputs from the h5):
unit 13 age 85 / assets $40,000; unit 70 age 71 / $40,000; unit 87 age 76 /
$46,185 — all far over the SSI resource limit ($2,000 individual / $3,000
couple), which PE screens (→$0) and axiom does not (awards full/near-FBR:
$11,928=$994·12, $17,880=$1,490·12). rulespec-us **does** encode the resource
test (`us/statutes/42/1382b/a.yaml`, 42 USC 1382b), so the live axiom SSI result
ignoring resources points to either (a) the **composed** SSI program not wiring
the resource rule, or (b) the **ssi-ecps bridge** not feeding the artifact's
asset inputs (`bank_account_assets`/`stock_assets`/`bond_assets`) to axiom's
resource variables. One low-asset aged+disabled case (unit 42, $284, PE=0) shows
an additional factor, so SSI needs a composed-program / bridge-input trace before
classing as `axiom_encoding_gap` vs `bridge_artifact`. **Likely axiom-attributed
— flagged, not hidden.** Truncated (1000/4044) → not reducible from the committed
report regardless.

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

---

## PHASE 2 (execution) — 2026-07-08

Environment: dep repos live under `~/TheAxiomFoundation/` (not `$HOME`); bridged
with `$HOME/{axiom-encode,axiom-rules,axiom-rules-engine,axiom-compose}` symlinks
and `$HOME/.axiom-oracles/roots/rulespec-us` (rsync). The shared axiom-compose
main clone is on another session's feature branch and is 13 commits behind
origin/main (no `data_relation`/`derived_formula`); built a durable origin/main
worktree at `~/TheAxiomFoundation/_worktrees/axiom-compose-main` and repointed
`$HOME/axiom-compose` at it (feature branch untouched).

### FIIT — the 1.767.3 hypothesis is FALSIFIED (verified by running it)

Ran fiit-ecps against policyengine-us **1.767.3** (full population, 87,519 tax
units). Result: **EITC did NOT resolve** and total rose 18,791 → **27,513**.
- EITC 16,680: unchanged. tax_unit 154343 axiom 117,741.43 vs PE **0.00** at
  1.767.3 — identical to 1.729.0. The pinned f0af251 Populace build stores
  partnership income in the pre-#8614 layout, so 1.767.3's eitc_earned_income
  still reads $0 partnership. Resolving EITC needs a NEW Populace build, not a
  model bump.
- capital-gain 8 → **6,173** large divergences (e.g. tax_unit 103 axiom 4,334.86
  vs PE 7,192.42): 1.767.3 drifts from the pinned Axiom rulespec on
  adjusted_net_capital_gain; tax_before_credits 2,118 → 4,655 downstream.

Decision: pin the oracle to **1.729.0** (coherent with the data's built_with).
The scoreboard matches reports by suite, not oracle label, so this is the honest
pairing. It keeps capital-gain/tax clean and isolates EITC as the sole structural
divergence — an upstream PE #8614 gap (1.729.0 predates it); Axiom correctly
includes partnership SE net earnings per 26 USC 32(c)(2)/1402(a). Regenerating at
1.729.0 now.

Planned fiit dispositions (on the FULL 1.729.0 report, bounds AST-verified over
all rows): EITC → upstream_engine_gap (linked PE #8614); tax_before_credits,
capital_gain, ctc → explained_residual (rounding/float).

### SSI — root cause found and fixed (issue #227)

Not a rulespec-us gap: `1382/a/1#eligible_individual` already tests
`resources_other_than_excluded_pursuant_to_section_1382b_a <= individual_no_spouse_resource_limit`
($2,000, from 1382/a/3). The defect is in axiom-oracles projection:
`data/populace_input_mapping.yaml` pinned that input to `{constant: 0}` on the
false premise "ECPS carries no asset data ... PE faces the same absence." PE reads
real countable resources from the same populace build and screens them (PE=0 at
$40k), so Axiom's constant-0 left it resource-unconstrained → 4,044 mismatches.
Fixed (committed): add `Concepts.SSI_COUNTABLE_RESOURCES`, project PE
`ssi_countable_resources`, map the slot from that fact (default 0). Verified at
the mapping layer (40k→40000, else 0). Issue TheAxiomFoundation/axiom-oracles#227.
SSI regen kept at the certified in-repo pair (1.752.2), version-invariant here.

Regenerated ssi-ecps (75,112 cases): the fix resolved 977 individual high-resource
cases, 4,044 → 3,067. The residual is NOT the resource screen and NOT takeup
(`takes_up_ssi_if_eligible` is 100% among PE-eligible): it is the v1 individual
slice diverging from PE's full SSI model. Per-household PE correlation of the
2,764 axiom>PE/PE=0 cases: 1,768 have NO PE-eligible member (Axiom's eligibility
determination is broader — SSI-specific disability, qualified-alien/institutional
criteria; projector feeds generic is_disabled/is_blind), 996 have a PE-eligible
taker-up whose benefit offsets to $0 on income (countable-income assembly
diverges). Filed axiom-oracles#228; dispositioned axiom_encoding_gap (3,067) —
classified (unexplained → 0) but counted as axiom_attributed_open on the badge
until the slice is completed. dispositions/ssi-ecps.yaml.

### Small state suites (303) — bridge_artifact

The 7 small suites (ca-tanf 177, medicaid-magi-co 46, ny-tanf 36,
co-state-income-tax 31, ks-tanf 6, az-tanf 4, co-tanf 3) each compare an Axiom
composed state program against PolicyEngine's full state model over the populace.
The residuals are structural — bidirectional benefit differences and boolean
eligibility flips — i.e. the same composed-program-vs-PE bridge/projection class
as ssi-ecps: rulespec encodes the statute; the composed programs + projections are
the documented approximations. Dispositioned bridge_artifact (transparent),
tracked in axiom-oracles#229 with per-suite grounding as the follow-up (ks-tanf
payment standard, co-state refundable credits).

### FINAL — us-pe unexplained_total = 0

23,138 → 4,347 (fiit) → 303 (ssi) → **0**. Attribution:
- oracle_attributed 16,660 — fiit EITC, PE #8614 partnership/S-corp split.
- explained_residual 2,131 — fiit tax_before_credits/capital_gain/ctc rounding.
- bridge_artifacts 3,370 — ssi v1-slice (#228) + 7 small state suites (#229).
- axiom_attributed_open **0**.
conformant=false ONLY from the coverage gap (covered 27 / in_scope 140), which is
out of scope for this lane. All CI gates (scoreboard/ratchet/apply_dispositions
--check) pass; ratchet re-pinned unexplained_max 23,138 → 0.

Issues filed: axiom-oracles#227 (SSI resource screen, FIXED), #228 (SSI v1-slice
residual), #229 (small-suite grounding).

---

# Federal grid suites — 2026-07-22

## State

In progress on `fed-parity/federal-grid-suites`. The configurable
`federal-tax-liability-grid` runner, all four PolicyEngine-US 1.767.3 legs, and
the ACA PTC, NIIT, and SECA Axiom bindings are implemented. Those three landed
RuleSpec fixtures pass strict case/period/input validation. Additional Medicare
remains blocked on one companion-fixture contract correction.

## Done

- Read the mandatory machinery recon, grid contract, state-grid generator,
  runner dispatch/pinning code, reference comparison/disposition, target
  conformance rows, live-suite gate, and conformance documentation.
- Confirmed the branch starts at `origin/main` commit `d4666ae`.
- Verified the exact PolicyEngine stack offline:
  `policyengine==4.18.9`, `policyengine-us==1.767.3`, and
  `policyengine-core==3.30.3`.
- Verified source boundaries and ran all 24 contract cases through the actual
  generator builders. Binding decisions: `additional_medicare_tax` includes
  wage and SE income; `self_employment_tax` excludes the 0.9% additional tax
  and is summed from Person to TaxUnit; NIIT derives AGI from the prescribed
  income inputs; ACA binds `used_aca_ptc` so the enrolled-premium cap is present.
- Added policy-isolated generator/runner machinery with required exact PE pins,
  configurable RuleSpec roots plus remote fallback, strict fixture
  case/period/input checks, canonical v2 aggregates, and a non-vacuous guard.
- Bound the landed ACA PTC (`dd48de7f`), SECA (`a1aa8c35`), and NIIT
  (`9173e7bd`) companions and added their comparison configs with source-boundary
  citations.
- Verified the exact Axiom fixture values and input shapes for all 18 landed
  contract cases. The focused runner/generator/affected-map/vacuous-gate tests
  pass 84/84 and the changed Python files pass `ruff check`.
- Flagged the Additional Medicare fixture mismatch: its current companion omits
  `amt-single-wage-se` and substitutes completed section-1402 income. The grid
  requires $150,000 Schedule C-style profit before PolicyEngine's 0.9235 factor,
  producing $346.725 rather than $450.

## Next

- Run and commit the three fully landed real comparison reports.
- Integrate the Additional Medicare companion once its exact contract case is
  corrected; then run and commit its real report.
- Adopt the four conformance rows only after all four reports exist, regenerate
  artifacts in the mandated order, and run the full deterministic check/build
  battery.
- Write the required build summary with per-case results and command outcomes.
