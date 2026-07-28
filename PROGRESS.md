# PROGRESS — PR #379 round-6 residue closure

## State

- Branch/worktree: `evidence-validator` in the existing
  `/Users/maxghenis/TheAxiomFoundation/_worktrees/oracles-evidence` worktree;
  starting HEAD `336b0a1bbfc87f5609828c209a6a7076c3cf4d4a`.
- Scope: close only the two category-(a) residues from
  `sol-fixverify6-2026-07-27`: per-case matched-value identity and the
  near-100 `r` semantic boundary.
- Constraints: minimal diffs; every fix includes its killed mutant; commit
  every coherent step; do not modify committed reports, run population
  suites, merge PR #379, or expand into category-(b) findings.
- Required gates: full evidence tests, census/certify mutants, census and
  certificate freshness checks, and the relevant dashboard tests.
- Output: a new residue-closure result file will carry the final report so
  prior committed review/build reports remain untouched.

## Done

- Read the encoder preamble, repository-local rules search, round-6 build
  brief/result, and the sixth verification brief/findings.
- Confirmed the requested branch and worktree are clean and match
  `origin/evidence-validator`.
- Confirmed the two accepted witnesses: permuting complete matched values
  between cases preserves aggregate totals, and `r=99.9999995` passes
  representation tolerance while the dashboard branches on exact `r===100`.
- Attempted the prescribed GitNexus debugging workflow; graph tools are not
  available in this session, so direct source/caller tracing is the recorded
  fallback.
- Closed the matched-value identity residue without changing a committed
  report: every `full` corpus now has a domain-separated, order-independent
  `case_verdicts_sha256` commitment in its versioned chunk index over exact
  `(case_id, concept, outcome, left, right)` records. Certification recomputes
  that commitment and treats absence or drift as an unbound evidence leg.
- Hardened the generic index generator so it cannot implicitly bless a
  changed per-case verdict identity; only the full-corpus producer or the
  immutable-source replay can legitimately refresh the commitment.
- Added
  `test_permuted_matched_case_values_must_reconcile_with_case_identity`,
  reproducing the review's exact `ecps-spm-50666` ↔ `ecps-spm-50669` amount
  and eligibility permutation. Aggregate/content reconciliation stays clean,
  but the independent case identity makes the leg unbound.
- Replayed the migrated ECPS corpus from immutable source `6c4f17b...`
  without running an engine or population suite. Only its index gained the
  new commitment; report and chunk bytes did not change. Regenerated the
  certificate solely to bind the new index SHA.
- Residue-1 gates pass: 63 certification mutants, the producer refresh test,
  immutable replay `--check`, both chunk-index checks, certificate freshness,
  Ruff, and diff whitespace.
- Closed the `r` boundary residue with one cross-layer contract: `null` is
  unmeasured, exact `100` is full agreement, and finite `[0,100)` is measured
  non-full agreement. Evidence now applies strict bounds and exact equality at
  derived `0/100` endpoints while retaining representation tolerance only for
  interior fractional percentages.
- Fresh compaction and immutable historical replay derive `r` from stored
  match/mismatch counts, so neither trusts a near-endpoint stored rate.
- Added `test_full_agreement_rate_must_be_exact_at_semantic_boundary` for the
  exact `r=99.9999995` witness and extended the bounds mutant to
  `r=100.0000005`. Added replay/emitter controls proving both normalize exact
  endpoints.
- Replaced both dashboard `r===100` branches with a shared tri-state helper.
  Unmeasured rows are excluded from triangulation and no longer render as
  agreement in the case table. The direct Node mutant pins `100 → true`,
  `99.9999995 → false`, and `null → null`.
- Residue-2 focused gates pass: 107 evidence/replay/producer tests, the direct
  dashboard semantic test, immutable replay and index checks, Ruff, and diff
  whitespace. The existing dashboard loader test cannot obtain `esbuild`
  because network access is unavailable, and a full dashboard build cannot
  start because `next` is not installed in this checkout; both environment
  limits are retained for the final report.
- Completed the clean-HEAD gate battery: 110 focused evidence/census mutants,
  the bot no-op mutant, replay/index/census/certificate/overview freshness,
  bridge validation (0 errors, four pre-existing findings), Ruff, compileall,
  the direct dashboard boundary test, and cumulative whitespace all pass.
- Wrote the requested final report to the new, committed
  `sol-evidence-round6-residue-closure-2026-07-28-result.md`; no prior report
  was edited.

## Next

- Publish the committed branch, append the required `Residues closed` section
  to PR #379 with the exact mutant names, and confirm the PR remains open and
  unmerged.

---

# PROGRESS — round-6 value-level evidence reconciliation

## State

- Branch: `evidence-validator`; starting HEAD
  `627c08df3bf47b2bac1e4c5dc084e84d3a1c7f37`.
- Outcome: category-(a) implementation and integration are complete; every
  requested gate is green. The final ops-path copy is sandbox-blocked, so the
  authorized in-repository fallback report is committed as `fabdf29f`.
- Scope: implement only the round-5 category-(a) blocker and its integration:
  aggregate value reconciliation, dashboard-semantic row validation,
  migrated-corpus replay verification, `origin/main` merge, regeneration, and
  the requested gates. Category-(b) QC publication and root unattended
  regeneration remain trunk follow-ups.
- Source:
  `/Users/maxghenis/TheAxiomFoundation/ops/reviews/sol-fixverify5-2026-07-27/findings.md`.
- Constraint: commit every coherent step locally and do not push. Generated
  merge conflicts must be resolved through regeneration, never by hand.
- Output: the requested ops result path is outside the writable sandbox; if
  the final copy is denied, commit the report in this repository as directed.
- Baseline: worktree is clean at the cached remote branch tip. Cached
  `origin/main` is `0b3f5a70af0ea63728b269e7d6e7657ddbd3bb41`;
  the branch is 102 main commits behind and 32 branch commits ahead.

## Done

- Read the complete round-5 verification finding and isolated its sole
  category-(a) blocker from the explicitly excluded category-(b) follow-ups.
- Confirmed the starting branch, worktree, remote refs, divergence, and output
  sandbox constraint.
- Indexed the checkout locally for impact analysis. `_aggregate_verdicts` and
  compact-row validation are HIGH-risk boundaries because validation,
  regeneration, index generation, certification, and refreshed-report
  publication all depend on them; those downstream paths are in the gate set.
- Confirmed the live ECPS aggregate values independently: amount sums are
  37,933.0 left and 37,996.938652 right, and eligibility-positive counts are
  186 left and 186 right. The report agrees exactly.
- Found an honest pre-regeneration row-semantic defect: live
  `ecps-spm-50970` stores `d = l - x = -1.700012...`, while the round-6 spec
  requires `d = x - l = +1.700012...`. The derived compact delta must be
  normalized during trusted replay; report aggregate values will not be tuned.
- Located the existing synthetic full-evidence fixture, rebind helper,
  migrated replay validator, and exact insertion points for the matched-value,
  isolated-`d`, and isolated-`r` killed mutants.
- Confirmed cached `origin/main` matches the verifier's exact 102-commit
  divergence and was fetched shortly before this round. A merge simulation
  predicts one generated conflict, `dashboard/public/data/overview.json`,
  which must be resolved by running its generator.
- Located the cumulative diff's four trailing-space lines in
  `sol-evidence-validator-2026-07-27-result.md`.
- Implemented aggregate value reconciliation across every matched and
  mismatched verdict: amount left/right sums and eligibility left/right
  positive weights must reproduce the report within six-decimal/IEEE
  representation tolerance, never the looser concept tolerance.
- Made weighted value claims fail closed unless the aggregate carries a unit
  `comparison_weight` reproducible by the unweighted compact verdicts.
- Bound compact dashboard semantics: numeric mismatch `d` must be `x - l`,
  nonnumeric deltas must be null, and `r` must equal the verdict-derived match
  rate whenever `v` makes the row outcomes complete. Every numeric `r` is
  bounded to 0–100, and a partial row with a stored mismatch cannot claim
  `r = 100`; QC cardinality rows with absent `v` and null `r` remain valid.
- Changed fresh dashboard emission and trusted historical replay to derive
  `d` from `l`/`x`; replay never trusts the historical sign convention.
- Added durable killed mutants for matched amount `0/0 -> 999/999`, matched
  eligibility `false/false -> true/true`, missing unit-weight evidence,
  isolated `d` drift, and isolated `r` drift. Strengthened the shared full
  fixture into a positive aggregate-value and row-semantics control.
- Confirmed the tightened live validator initially failed for exactly the
  disclosed `ecps-spm-50970` delta-sign defect; no aggregate value drift
  surfaced.
- Replayed the migrated ECPS and QC corpora from immutable source
  `6c4f17bfe6dc8224ee8251401fe0247b1117a25b`. The staged replay now checks
  37,933.0/37,996.938652 amount sums and 186/186 eligibility positives against
  the report before writing. ECPS validates `bound/full` over 1,072 cases; QC
  remains `bound/cardinality` over 856 cases.
- Regenerated the ECPS binding, census, and `us-co/snap` certificate. The
  certificate remains honest: its reference leg is clean `bound/full` with
  2,143 matches, one explained mismatch, and zero unexplained; its reality leg
  remains clean `bound/cardinality`.
- Focused implementation gates pass: 103 mutant/regeneration/comparison tests,
  Ruff, compileall, replay `--check`, chunk-index validation, census/certificate
  freshness, and diff whitespace.
- An independent post-fix review found no remaining category-(a) correctness
  issue after adding fail-closed unit-weight evidence and partial-row `r`
  checks.
- Attempted to refresh `origin/main`; the sandbox network could not resolve
  GitHub. The cached tip is still the verifier-pinned
  `0b3f5a70af0ea63728b269e7d6e7657ddbd3bb41`, fetched shortly before this
  round, so integration is explicitly pinned to that reviewed snapshot.
- Merged cached `origin/main`. Its sole conflict was the generated
  `dashboard/public/data/overview.json`; resolved it only by rerunning
  `scripts/generate_dashboard_overview.py`.
- Replayed the migrated ECPS/QC compact corpora after the merge, then
  regenerated the exercise census and `us-co/snap` certificate so report and
  index SHA changes from main are rebound rather than hand-edited.
- Removed the cumulative diff's four trailing-space defects from the earlier
  execution-validator report.
- Completed every requested post-merge gate:
  migrated replay `--check` verifies ECPS `bound/full` over 1,072 cases and
  QC `bound/cardinality` over 856; chunk-index validation reports both lanes
  OK; exercise census and certificates are up to date; the full certification
  mutant suite passes 62 tests; and the bot's second-run no-op test passes.
- Supplemental integration checks also pass: the regenerated overview binds
  all 213 reports, the bridge manifest validator has zero errors (and retains
  its four disclosed audit-debt findings), the 103-test focused semantic
  suite passes, Ruff passes, compileall passes, and the staged diff has no
  whitespace errors.
- The pre-commit graph audit classifies the 138-file staged integration merge
  as HIGH impact (413 indexed symbols, 11 affected execution processes), as
  expected for the upstream state-tax-populace campaign. The requested
  downstream evidence, regeneration, mutant, and no-op gates cover the
  category-(a) changes.
- Committed the verified upstream integration and regenerated artifacts as
  `37058619`. Removed the untracked 84 MiB local graph index created for impact
  analysis; the worktree was clean afterward.
- Wrote the complete round-6 result to the in-repository fallback
  `sol-evidence-round6-2026-07-27-result.md`.
- Attempted the required copy to
  `/Users/maxghenis/TheAxiomFoundation/ops/reviews/sol-evidence-round6-2026-07-27/result.md`;
  the sandbox returned `Operation not permitted`. The committed repository
  report is therefore the directed fallback.
- Repeated the exact required gates from clean committed HEAD: replay,
  validator, census, certificate, all 62 certification mutants, the bot no-op
  test, and the cumulative whitespace check all pass.

## Next

- None. Verify the final bookkeeping commit leaves a clean worktree and hand
  off; no implementation work remains.

---

# PROGRESS — round-5 semantic evidence reconciliation

## State

- Branch: `evidence-validator`; starting HEAD `651d5966c061cc2a9793a382595810355e1478af`.
- Scope: implement only the round-4 review's Required closure plus the two
  explicitly promoted PARTIAL items: derived-mode precedence and strict
  disposition-document authorization.
- Source: `/Users/maxghenis/TheAxiomFoundation/ops/reviews/sol-fixverify4-2026-07-27/findings.md`.
- Constraint: commit every coherent step locally; do not push. The requested
  ops result path is outside the writable sandbox, so use a committed in-repo
  fallback report if the external write is denied.
- Baseline: worktree was clean and matched cached `origin/evidence-validator`.
  Fetching current `origin/main` was blocked by DNS; cached `origin/main` is
  `abe2520193439467d5fd1ada46476fc7f05d0611`.

## Done

- Inspected the checkout, branch, worktrees, remotes, cached base, and the full
  round-4 findings before implementation.
- Confirmed the required implementation and mutant boundaries verbatim from
  the review.
- Implemented canonical `full` reconciliation: per-case verdict values now
  reproduce report tolerance semantics, per-concept aggregates, the exact
  mismatch list, unique/non-overlapping concepts, and disposition markers and
  counts.
- Required `full` evidence for reference conformance while retaining
  cardinality as an honest reality-leg strength.
- Closed the two promoted PARTIAL items: derived certificate mode wins over a
  registry `mode`, and disposition accounting requires a valid nonempty
  dispositions document for the same suite.
- Added and passed the expanded 52-case certification mutant suite, including
  foreign values, disposition drift, duplicate/overlapping concepts,
  reference cardinality, later-malformed chunks, mode precedence, and
  same-suite non-disposition artifacts.
- Confirmed the strengthened validator isolates the live ECPS defect exactly:
  `ecps-spm-50970` lacks the report's `explained_residual` compact marker.
- Added an auditable regeneration path pinned to the migration parent
  `6c4f17bfe6dc8224ee8251401fe0247b1117a25b`; it replays both migrated
  Colorado corpora, projects report dispositions bidirectionally, validates
  the complete projection, and rebuilds exact v1 bindings.
- Regenerated both migration-touched suites through that path. ECPS now
  validates `bound/full` over 1,072 cases and `ecps-spm-50970` carries
  `e: explained_residual`; QC validates `bound/cardinality` over 856 cases
  and remained byte-identical.
- Preserved future QC `matched: false` rows as explicit compact mismatches and
  made every skipped versioned corpus immutable, including inline-only v1.
- Added six regeneration-path tests plus the QC-mismatch and inline-v1 skip
  mutants. The combined mutant, regeneration, and comparison test set passes
  all 95 tests.
- Verified `dashboard/src/components/Households.jsx` consumes `m.e` both when
  counting unexplained mismatches and when rendering mismatch dispositions.
- Regenerated the exercise census and `us-co/snap` certificate from the new
  chunk identity. The reference leg is honestly `bound/full`, clean, and has
  one explained mismatch with zero unexplained; the reality leg remains
  `bound/cardinality`. `conformant` remains true, while the pre-existing
  exercise blocker keeps the overall certificate unavailable.
- Confirmed both `exercise_census.py --check` and `certify.py --check` are
  up to date after regeneration.
- Final gates pass: migrated-corpus and chunk-index checks, disposition
  consistency, census/certificate freshness, bridge validation (zero errors
  and four pre-existing conservative findings), all 54 certification mutants,
  41 regeneration/comparison tests, the bot no-op test, Ruff, and diff checks.
- An independent final scope/correctness review found no actionable defect,
  missing required mutant, scope creep, or dishonest certificate state.
- Wrote the full result to
  `sol-evidence-round5-2026-07-27-result.md`. Copying it to the requested ops
  path was denied by the read-only sandbox (`Operation not permitted`), so the
  committed in-repository report is the authorized fallback.

## Next

- No implementation work remains. A caller with write access to the ops
  checkout may copy the committed fallback report to the requested output
  path.

---

# PROGRESS — execution-evidence validator (#378)

## State

- Branch: `evidence-validator`, based on `bridge-manifests`; starting HEAD
  `2778fa1764cc01f0cf10ad64ac89933df16b489a`.
- Scope: add importable suite-evidence validation, versioned report/chunk
  binding indexes, census/certificate integration, and durable synthetic
  certification mutants.
- Constraint: full chunk parsing is limited to certificate `PROGRAMS`; the
  census-wide path must remain cardinality-level and fast.

## Done

- Verified the worktree is clean and checked out on `evidence-validator`.
- Read issue #378, PR #368, every requested verification-history record, and
  the current census/certificate/chunk producer paths.
- Confirmed the blocker: arbitrary inline mappings and filename-only chunks
  can pass certification; chunks are neither parsed nor bound to the cited
  report; the census identity is not checked against the certificate registry.
- Aligned with PR #368 without taking its scope: this component uses its
  `schema_version`, `case_count`, and `comparison_count` vocabulary, while
  leaving engine/oracle/output-surface attestation to that PR. Here,
  `binding: bound|unbound` means only report-to-chunk identity.
- Established reconciliation semantics from the live Colorado shapes:
  `co-snap-ecps` supports `full` because compact `v` rows reproduce 2,143
  matches and compact `m` rows reproduce one mismatch; `co-snap-qc` supports
  only `cardinality` because 856 chunk rows reproduce the comparison
  cardinality but omit per-row verdict values.
- Found two migration constraints: all 114 existing chunk indexes use the
  legacy integer `chunks` field expected by the dashboard loader, and both
  Colorado reports mirror inline case IDs already present in their chunks.
  The new indexes therefore require a loader compatibility change and the two
  bound reports must move to chunk-authoritative case storage before strict
  cross-source ID uniqueness can hold.
- Implemented the importable validator and index builder in
  `axiom_oracles/evidence.py`: strict report counts, compact/inline row shapes,
  every-chunk parsing, global ID uniqueness, exact/full versus cardinality
  reconciliation, and versioned report/path/SHA/chunk binding.
- Added `scripts/generate_chunk_indexes.py`, including deterministic `--check`
  behavior and an explicit one-time inline-mirror migration mode.
- Added committed synthetic evidence fixtures and mutants for dummy metadata,
  uncontested foreign chunks, duplicate IDs, malformed rows, stale report
  hashes, and positive full/cardinality controls. Replaced the NYC-dependent
  contested mutant with a synthetic census fixture.
- Migrated the two Colorado dashboard reports to chunk-authoritative case
  storage, wrote exact v1 indexes, and verified `co-snap-ecps` as
  `bound/full` (1,072 case rows, 2,144 verdicts) and `co-snap-qc` as
  `bound/cardinality` (856 case rows).
- Preserved that contract across refreshes: the report slimmer clears
  versioned inline mirrors, the artifact emitter preserves an existing
  versioned corpus when a skip run has no full rows, and the bot/regeneration
  paths rebuild and check indexes. The dashboard loader accepts both v1 chunk
  descriptors and unmigrated legacy integer indexes.
- Tightened cardinality fallback so nonempty compact mismatch evidence without
  matched verdict rows is partial evidence (`none`), never a weaker passing
  cardinality claim. Added a bound synthetic mutant for that shape.
- Integrated the lightweight path into `exercise_census.py`: its existing
  chunk read now records exact binding defects and a deliberately capped
  `cardinality|none` reconciliation per row without aborting on legacy or
  missing indexes.
- Integrated strict validation into `certify.py` only for `PROGRAMS` suites.
  Clean reference legs now require valid, bound, reconciled evidence, and the
  certificate rejects census report-path or report-SHA divergence from its
  registry entry.
- Closed the refresh-time substitution path: `run_comparison.py` now emits
  fresh compact chunks and a validated v1 index before slimming a versioned
  report. The generic generator refuses changed identities on an existing v1
  corpus, while skip/re-emit runs preserve the prior bound set byte-for-byte.
- Hardened the defect boundary for unreadable/malformed nested report shapes
  and non-standard/non-finite JSON. These inputs now produce leg/row defects
  instead of exceptions or false cardinality passes.
- Focused validation check: Ruff passes and
  the combined validator/census/producer suite reports 76 passed.
- Canonical final gates pass:
  - `generate_chunk_indexes.py --check`: ECPS `bound/full`, QC
    `bound/cardinality`;
  - `exercise_census.py --check`: up to date;
  - `certify.py --check`: up to date;
  - `validate_bridge_manifests.py`: 0 errors, four pre-existing findings;
  - `pytest tests/ -k "certification or commit_refreshed"`: 51 passed,
    1,854 deselected (including the bot no-op path);
  - Ruff, shell syntax, and `git diff --check`: clean.
- Wrote and committed the complete verification report as
  `sol-evidence-validator-2026-07-27-result.md`. The required external copy to
  `ops/reviews/sol-evidence-validator-2026-07-27/result.md` was attempted and
  denied by the read-only sandbox (`Operation not permitted`).

## Next

- No implementation work remains. A caller with write access to the ops
  checkout must copy the committed fallback report to the requested output
  path.

---

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

## PR #354 repair — 2026-07-25

### State

- Branch: `fed-parity/federal-grid-suites`; starting HEAD `a5771329`.
- Target: seven federal suites, no Saver's Credit suite, canonical RuleSpec
  `3373e8411f7e141fd50879e3de964386f606f7f6` / tree
  `7e00f195ea81ff9aa21c58d53151e937d974a016`.
- Required freeze: us-pe 34/127 covered, 0 unexplained, 0 Axiom-attributed;
  committed ratchet must not regress main's floor of 27.
- Constraints: local commits only; no pushes/GitHub writes; preserve this
  load-bearing ledger and all pre-existing suites/reports, including
  `fiit-ecps`.

### Done

- Read `/private/tmp/review-354-VERDICT.md` in full.
- Confirmed the worktree was clean at `a5771329`.
- Confirmed the tracked root `PROGRESS.md` is present and preserved.
- Reapplied the Saver's Credit withdrawal shape from `bc500bc4`: removed its
  config and stale report and returned the us-pe row to `suite: null`.
- Recorded that reinstatement awaits the Notice 2025-67 corpus chain
  (`axiom-corpus#506`). Retained the #9151 disposition as historical evidence
  after verifying that an orphan disposition is a supported, non-scoring state;
  its issue link is in `evidence.upstream_url`, not `linked_issue`.
- Withdrawal validation: `apply_dispositions.py --check` passes with the
  expected informational orphan note, and `run_comparison.py --list` exposes
  exactly seven federal suites. Targeted tests reached 96 passed / 3 skipped;
  the only two failures are the intentionally stale 35-covered scoreboard and
  ratchet, both queued for the required full regeneration to 34.
- Traced merged RuleSpec main's QBID pipeline and companion. The pipeline now
  imports all nine Rev. Proc. 2025-32 parameters, accepts pipeline-level filing
  status, and requires the sole-business attestation; the retired runtime
  threshold, statute-level status, and minimum-COLA inputs are absent.
- Updated the generator to bind the exact 19-input surface and removed the
  misleading threshold field from report case inputs. Added a unit contract for
  the full key set and moved PolicyEngine issue #9150 into
  `evidence.upstream_url`.
- QBID binding validation: 35 targeted generator/disposition tests pass, Ruff
  passes on the touched Python, and the disposition consistency gate passes.
- Restored the `d3a07de7` canonical-snapshot guard and pinned every one of the
  seven live federal configs to RuleSpec SHA `3373e841...` / tree
  `7e00f195...`. The runner now rejects partial pins, noncanonical roots, dirty
  worktrees, and tree mismatches before execution, then stamps the verified
  upstream SHA.
- Provenance validation: 19 targeted tests pass, Ruff passes, and a direct
  verification of the real configured checkout succeeded for all seven suites.
- Reran `us-qbid-grid` for real through `run_comparison.py` with the offline
  pinned oracle stack. The guard verified RuleSpec `3373e841...` /
  `7e00f195...`; every case carried exactly 19 fixture inputs. Result: 10/11
  raw, 11/11 explained, 0 unexplained. The sole mismatch remains the
  dispositioned #9150 row; no expected value or tolerance changed.

### QBID replay table

| case | Axiom | PolicyEngine | match |
| --- | ---: | ---: | :---: |
| qbid-ti-limited | 12,000 | 12,000 | yes |
| qbid-basic-100k | 20,000 | 20,000 | yes |
| qbid-joint-150k | 30,000 | 30,000 | yes |
| qbid-phasein | 27,500 | 27,500 | yes |
| qbid-above-nowages | 0 | 400 | no — #9150 |
| qbid-reit-only | 4,000 | 4,000 | yes |
| qbid-zero | 0 | 0 | yes |
| qbid-single-at-threshold | 30,000 | 30,000 | yes |
| qbid-single-one-dollar-over-threshold | 29,999.6 | 29,999.599609375 | yes |
| qbid-active-minimum | 400 | 400 | yes |
| qbid-net-capital-gain-limit | 14,000 | 14,000 | yes |

### Generic exclusion contract

- Restored the generic nonstatutory exclusion contract: schema validation now
  requires a note identifying the governing instrument and why the modeled
  amount is non-statutory, and `conformance/README.md` documents that rule.
- Reran the other six live federal suites for real against the guarded snapshot:
  ACA PTC 6/6, Additional Medicare 5/5, elderly/disabled 9/9, LLC 12/12,
  NIIT 6/6, and SECA 6/6. No expected value changed.
- The manifest writer preserved all 206 sibling entries and added the seven
  federal reports exactly once (213 total). All seven reports cite RuleSpec
  `3373e8411f7e141fd50879e3de964386f606f7f6`.
- Completed the UTC 2026-07-25 derived regeneration: dispositions, grids,
  affected map, vacuous-gate freshness, scoreboard + dated snapshot, ratchet,
  burndown, and dashboard overview. Saver is absent from every generated live
  registry. Final us-pe headline is 34/127 covered, 0 unexplained,
  0 Axiom-attributed, 16,661 oracle-attributed, and 3,340 bridge artifacts.
- Corrected the corrupted 35 ratchet floor to the honest seven-suite floor of
  34, which remains above main's committed floor of 27. All eight derived
  `--check` gates pass after regeneration.
- Complete validation battery passes: registry listing, rule verification,
  state-tax Populace contract, all eleven current CI `--check` gates, Ruff, and full
  pytest. Pytest result: 1,791 passed / 57 skipped in 169.99 seconds, with the
  unavailable Node/esbuild dashboard loader taking its designed skip.
- The conformance-universe gate validated UK and BE and returned its documented
  clean no-op for local PE-UK/PE-US checkouts whose versions do not match the
  committed pins; every other gate performed a full check.

### Next

- None. Final scope/provenance/count audit passed; see `fix-354-DONE.md`.
