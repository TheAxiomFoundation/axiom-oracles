# PROGRESS — PR #468 cross-lane reconciliation

## State

- Branch/worktree: `evidence-validator-land` in
  `/Users/maxghenis/TheAxiomFoundation/_worktrees/evidence-land`.
- Requested operation: finish the `origin/main` reconciliation in place, keep
  the strict evidence layer together with the DK/NZ multi-program and
  oracle-switch machinery, regenerate all certificates and downstream
  artifacts, run every freshness check and the full requested battery, then
  push the branch without merging PR #468.
- Starting checkout: clean at `27e3a51fc`; contrary to the task handoff,
  `MERGE_HEAD` is absent. The tip contains an earlier merge of main at
  `7f4e579b3`, but current `origin/main` is `a33cadea0` and is not an ancestor.
  The current remote-tracking tip will therefore be merged without discarding
  or aborting the prior reconciliation history.
- Reconciliation rules: union both code lanes; prove the certification-mutant
  function-name union in both directions; never hand-edit certificate
  conflicts; preserve and prominently report honest DK/NZ regressions caused
  by strict evidence requirements.
- Final report target:
  `sol-evidence-validator-land-reconciliation-2026-08-15-result.md`.
- Current status: reconciliation is committed and every requested gate is
  green. Publication is externally blocked: terminal transport cannot resolve
  GitHub, and the connected GitHub interface rejected its first blob write.
  The remote branch and PR remain unchanged.

## Done

- Confirmed the requested branch and clean worktree.
- Confirmed there is no active merge metadata and recorded the exact local and
  `origin/main` tips rather than aborting or rewriting any history.
- Started independent read-only audits of `scripts/certify.py`, mutant-test
  function sets, and the repository's canonical regeneration/check pipeline.
- Read `origin/main`'s 1,055-line `scripts/certify.py` end to end before
  resolving it. The result retains CO+DK+seven NZ registry entries, NZ
  report/view and attestation switching, and every strict evidence contract:
  bound/full reference evidence, typed fail-closed report parsing, disposition
  schema/marker agreement, exact report/index byte hashes, per-case evidence,
  and census-to-registry identity. Derived premise modes still override any
  registry-supplied `mode` field.
- Reconciled `tests/test_certification_mutants.py` as the exact name union:
  branch 55 functions, main 41, 23 shared, merged 73. Both parent-to-merged
  differences are empty, and the merged-to-parent-union difference is empty.
- Preserved main's fresh 856-case Colorado QC execution, then used the guarded
  inline-mirror migration and immutable source replay rather than hand edits.
  CO QC now validates `bound/cardinality`; CO ECPS validates `bound/full`.
- Regenerated NZ unified/closure receipts, dispositions, both certified chunk
  indexes, freshness, scoreboard/history, both ratchets, burn-down, overview,
  the exercise census, and every program certificate. Certificate conflicts
  were resolved solely by `scripts/certify.py` output.
- Preserved the honest protocol regressions: CO remains conformant=true and
  certified=unavailable; DK changes from main's conformant=true to false and
  remains certified=unavailable; all seven NZ program views change from
  conformant=true to false and certified=no.
- DK's three legs are `unbound/full`: each lacks a chunk index, disagrees on
  the stored case/report disposition marker, and has a non-object
  `errors_by_engine`. NZ's shared leg is `unbound/none`: the unified report
  lacks a non-negative top-level `case_count`, its stored cases cannot support
  full/cardinality reconciliation, and its chunk index is absent. No strict
  rule was softened and no certificate verdict was edited by hand.
- All canonical checks pass: NZ record/closure, 95 disposition files, both
  immutable Colorado replays and indexes, freshness (223 suites / 34
  executable surfaces), scoreboard (6 jurisdictions / 4 conformant), both
  ratchets, burn-down (6 series / 143 points), overview (224 reports), census,
  and certificates.
- Requested batteries pass: 83/83 certification mutants, 84/84 complete
  evidence cases (the historical 66 expanded by the 18 NZ mutants), and 65/65
  runner/refresh cases in 565.35 seconds.
- Focused Ruff/compile/whitespace checks and the 10-case census/immutable-replay
  support battery pass.
- Created merge commit `0e4d9a840578264bc6e862c4169cd52666d5d312`
  with parents `511cacaa9` and `a33cadea0`; its subject and body explicitly
  document the three-way union and the DK/NZ conformant regressions.
- A normal push failed before authentication with `Could not resolve host:
  github.com`. A connected GitHub Git-data interface is available as the
  publication fallback; PR #468 has not been merged or edited.
- The connected interface confirmed PR #468 is open and unmerged at remote
  head `27e3a51fc`, then rejected the first atomic blob write as
  `user cancelled MCP tool call`. No remote object, ref, or PR state changed.

## Next

- When GitHub terminal transport or connected write authorization is
  available, push `evidence-validator-land`, verify the remote ref, and leave
  PR #468 unmerged.

### Earlier branch handoff

- No implementation work remains. Handoff the committed branch HEAD and
  untracked worker report; do not push.

# Month-fix regeneration review repair

## State

- Branch: `data/month-fix-regen`
- Repair start: `f0a6598e1337310fdf2f663af91b7ab81f773491`
- Literal merge base: `819f370bf0346e4a6a8dfb1c8c4f0d873d6d0340`
- Review ledger: closed at `3097abcb`; verdict `REQUEST-CHANGES`.
- Purpose: defensively repair reviewability and containment findings without
  regenerating or changing any suite artifact.
- Phase: in progress. The root ledger now follows append discipline; the
  California literal-merged-set reconciliation and checker repair remain.

## Done

- Read the closed blind review before inspecting or changing the branch.
- Preserved the pre-existing untracked `WORKER-REPORT.md` without modification.
- Restored all 57,579 bytes and 951 lines of the merge-base `PROGRESS.md` as
  the exact file prefix (SHA-256
  `c453af85c7e77b13a2ea18fcfd884f149d4783c4edf712354a85485d67b8379a`).
- Appended all 14,644 bytes and 245 lines of the branch's prior progress ledger
  unchanged (SHA-256
  `0e2cabe4771cd9cb75547f6908d83d79dbb9d269aac46bc3e3892f8ce5d95851`).
- Confirmed the restoration is append-only relative to the branch head:
  `952` insertions and `0` deletions before this repair entry.
- GitNexus graph tools were not exposed, so the schema failure will be traced
  directly through the tracked checker and its tests.

## Next

- Reconcile all 345 literal merged #423 rows as 192 vanished, 22
  materially-drifted-and-dropped, and 131 kept.
- Track a reproducible `scripts/` reconciler with explicit `--base-ref`
  discipline and make the tracked disposition checker validate the current
  compact schema without weakening checks.
- Verify that every tracked accounting and provenance reference names the
  literal 345-row merged set and its tracked checker.
- Run the full `--check` battery, assert suite artifacts are byte-unchanged,
  commit each coherent step, and write the short untracked
  `WORKER-REPORT-REPAIR.md`.

## Repair checkpoint — literal merged accounting committed

### State

- Phase: accounting and checker repairs are committed; full repository gates
  and final artifact-containment proof remain.
- Root `PROGRESS.md` still begins with the merge-base's exact 57,579-byte,
  951-line content.

### Done

- Committed `47949eb5` with a read-only literal-base reconciler and focused
  regression coverage.
- Reconciled the 345 literal merged #423 rows exactly as 192 vanished, 22
  materially drifted and dropped, and 131 kept; the kept set closes as 115
  materially moved pins plus 16 unchanged pins.
- Validated the current 7,101-case `id/r/h/m` compact schema against all 529
  report mismatches and 288 expanded annotations.
- Kept the historical builder check operational by requiring the explicit
  base ref and validating its pinned report, legacy compact snapshot, trace,
  and generated YAML. The real saved-trace gate validates 345 rows with 96
  historical unexplained rows.
- Passed 50 focused checker/disposition/artifact tests, Ruff, diff-check, the
  current checker, the historical checker, and exact current-checker receipt
  parity through the builder dispatch.
- Replaced the non-authoritative repaired-source provenance in both compact
  BBCE disposition notes with the literal merged base ref, source SHA-256,
  tracked checker command, and corrected partition.

### Next

- Commit the corrected tracked accounting prose and exact derived disposition
  copy.
- Run the full `--check` and validation battery, prove CA/KS/SSI suite
  artifacts remain byte-identical to repair start, and close the ledger.
- Write untracked `WORKER-REPORT-REPAIR.md`; do not modify the pre-existing
  untracked `WORKER-REPORT.md`, push, or write to GitHub.

## Repair closeout — defensive audit complete

### State

- Phase: complete. The branch contains the append-only ledger restoration,
  literal merged-set reconciliation, tracked checker, corrected provenance,
  focused tests, and final validation evidence.
- No suite was regenerated. The only tracked data edits are the two required
  California source row-note corrections and their exact served copy.
- No push or GitHub write was performed.

### Done

- Passed the review's complete seven-command lightweight battery:
  dispositions, grids, affected map, vacuous gate, scoreboard, ratchet, and
  burn-down.
- Also passed boundary cases, dashboard overview, conformance
  universe/compositions, comparison registry listing (135 suites), rule
  verification (21,859 rules), and the state-tax populace contract (43
  jurisdictions; 32 ready and 11 blocked). The UK-PE and US-PE universe checks
  were clean no-ops because the adjacent checkout versions do not match the
  committed pins.
- Passed both tracked CA checker entry points with byte-identical receipts:
  345 literal rows close as 192 vanished + 22 materially drifted and dropped
  + 131 kept, and kept pins close as 115 moved + 16 unchanged. The current
  evidence closes at 529 report mismatches, 288 expanded annotations, and
  7,101 compact cases.
- Passed the real saved-trace historical gate: 345 evidence-pinned rows
  validate with 96 historical unexplained rows.
- Passed Ruff, diff-check, and 50 focused disposition/checker/artifact tests.
  A broad Python run passed 2,304 tests and skipped 70. Its sole failure was
  the known network-dependent dashboard loader: `npx esbuild` could not reach
  `registry.npmjs.org` (`ENOTFOUND`), so no code assertion failed.
- The exact affected emitter scope passes for 18 complete canonical case
  suites and all 13 extant disposition suites. SSI intentionally stores only
  1,000 of 2,990 mismatches in its canonical dashboard report, so the case
  emitter correctly refuses to claim full parity; its 2,990-row
  mismatch-only compact tree is internally consistent and unchanged.
  Repository-wide no-argument emitter probes likewise expose unrelated
  pre-existing stale/missing suites; California is absent from those findings.
- Proved every protected tracked path containing `ca-snap-ecps`,
  `ks-tanf-ecps`, or `ssi-ecps` is byte-identical to repair start, excluding
  only the explicitly required California disposition note and served copy.
  The primary report SHA-256 values remain `d5b95f7c8f9e9a66...`,
  `1132d023920d7685...`, and `0eb73772a9220a0c...`.
- Reconfirmed the root ledger's exact merge-base prefix: 57,579 bytes, 951
  lines, SHA-256
  `c453af85c7e77b13a2ea18fcfd884f149d4783c4edf712354a85485d67b8379a`.
- Confirmed no tracked `188/341` accounting or non-authoritative
  `da5bf292...` provenance remains.
- Wrote the required short untracked `WORKER-REPORT-REPAIR.md` and preserved
  pre-existing untracked `WORKER-REPORT.md` byte-for-byte.
- Sandbox disclosure: a read-only `ps` diagnostic was denied while monitoring
  the broad test run. It did not affect the test process; no other sandbox
  permission failure occurred during this repair.

### Next

- Handoff the committed local branch and untracked repair report. Do not push
  or write to GitHub.

## Independent repair re-review opened — `58c6075f0`

### State

- Phase: in progress. Review scope is limited to the two mechanical repairs
  and containment requested for `data/month-fix-regen` at reviewed head
  `58c6075f0`.
- Work is confined to the disposable local worktree. No remote or GitHub
  writes are authorized.

### Done

- Confirmed the worktree began at `58c6075f0` on
  `data/month-fix-regen`.
- Recorded two pre-existing untracked files, `WORKER-REPORT.md` and
  `WORKER-REPORT-REPAIR.md`; they will remain untouched.
- Loaded the repository review workflow and identified merge base
  `819f370bf0346e4a6a8dfb1c8c4f0d873d6d0340`.

### Next

- Verify exact merge-base ledger prefix identity and audit the appended record.
- Independently re-derive the literal 345-row California disposition split,
  inspect checker discipline and coverage, and sample at least 10 vanished
  plus 5 kept rows.
- Verify protected artifact parity, SSI truncation/fail-closed behavior,
  containment, the seven-check battery, and focused tests.
- Write and commit the final review report, then close this ledger.

## Independent re-review checkpoint — ledger and gates verified

### State

- Phase: in progress. Ledger repair, repair-commit containment, the complete
  seven-check battery, and focused test coverage are verified.
- Independent California row sampling and SSI truncation history remain in
  progress.

### Done

- Compared the first 57,579 bytes of reviewed-head `PROGRESS.md` directly with
  merge-base `819f370b`; `cmp` returned zero and both byte streams have SHA-256
  `c453af85c7e77b13a2ea18fcfd884f149d4783c4edf712354a85485d67b8379a`.
  The prefix is exactly 951 lines.
- Isolated the restored historical month-regeneration ledger after its
  separator and proved it is byte-identical to `f0a6598e:PROGRESS.md`:
  14,644 bytes, 245 lines, SHA-256
  `0e2cabe4771cd9cb75547f6908d83d79dbb9d269aac46bc3e3892f8ce5d95851`.
- Confirmed the final base-to-reviewed-head ledger diff is 391 insertions and
  zero deletions. Its repair narrative agrees with the four repair commits,
  their changed-path inventory, and the validations repeated so far.
- Audited `f0a6598e..58c6075f0`: seven paths changed—`PROGRESS.md`, the
  historical builder, the new reconciler, two focused test modules, and the
  source/served copies of the California accounting note. No report, case
  tree, comparison config, or other suite artifact changed.
- Re-ran the complete required battery: dispositions, grids, affected map,
  vacuous gate, scoreboard, ratchet, and burn-down all exited zero (7/7).
- Re-ran the focused builder/reconciler/disposition/artifact suite: 50 tests
  passed. The current reconciler and builder dispatch also both passed and
  emitted byte-identical receipts.
- Proved pre/post tracked status was unchanged; only the two pre-existing
  untracked worker reports remain.
- Sandbox disclosure: the review workflow's local GitNexus analysis could
  create a partial worktree index but could not register it at
  `/Users/maxghenis/.gitnexus/registry.json` (`EPERM`). The generated partial
  index was removed, and direct diff/caller/test inspection replaced graph
  queries.

### Next

- Complete the independent 345-row California derivation and required samples.
- Complete protected-artifact hash parity and SSI pre-existing/fail-closed
  verification.
- Write `REVIEW-REPORT.md`, close this ledger, and commit each final unit.

## Independent re-review checkpoint — CA and protected artifacts verified

### State

- Phase: evidence collection complete. Both requested repairs and containment
  verify cleanly; final report drafting remains.
- Provisional verdict: approve.

### Done

- Independently parsed the literal `819f370b` disposition blob and reviewed
  `58c6075f0` source/report/compact artifacts without importing the tracked
  reconciler. The 345 rows partition exactly as 192 vanished, 22
  current-but-dropped, and 131 kept; kept pins divide into 115 moved and 16
  unchanged.
- Confirmed the literal base blob is byte-identical to PR #423 merge
  `1b57affd`, with SHA-256
  `18cfbe28f951261142bfa3c52d0c88f6d0a3d53b77b597fcd807b4d2e9a23086`.
- Independently joined the pinned saved trace to the new report and verified
  that all 22 current-but-dropped requested-month pins moved materially.
- Sampled 12 vanished rows, including all four merged-only identities for
  `ecps-59082` and `ecps-62506`; every sampled household is present at 100%
  compact match rate with zero current rows for the old concept identity.
- Sampled ten kept rows across moved benefit pins and unchanged eligibility
  pins. Every sample has exact current source/report identity and pin parity,
  the expected report disposition ID, and one exact compact mismatch payload.
- Reviewed the checker change and negative coverage. The current-schema path
  validates all 529 canonical mismatches, 288 expanded annotations, exact
  `id/r/h/m` compact parity, base/partition/movement identity digests,
  requested-month pin receipts, and source/served parity. Historical mode now
  reads hash-pinned legacy inputs from the explicit base ref. Tests cover
  unsafe refs, byte drift, equal-count identity swaps, retired schema,
  silent annotations, merged-only omissions, pin tampering, and invalid
  dispatch modes; no guard was weakened.
- Proved all 39 protected paths containing `ca-snap-ecps`,
  `ks-tanf-ecps`, or `ssi-ecps` match repair start `f0a6598e` except the two
  permitted California accounting-note copies. Primary report SHA-256 values
  remain `d5b95f7c8f9e9a66f5146dcf82bcfe719c6433cb150217a181f4db959fe3911d`,
  `1132d023920d768577617e074b914cd17c89a057dd7fd893c5052454b4a33532`,
  and `0eb73772a9220a0cd0aaeb1ec174a43fab61bf33289f56c600202a1f7128399b`,
  preserving 529, 218, and 2,990 total mismatches.
- Confirmed SSI truncation predates this branch on both merge-base and current
  local `origin/main`: the served report explicitly records 1,000 shown of
  3,067 total there, versus 1,000 of 2,990 at the reviewed head. Its checker
  exits one with `canonical mismatch list is incomplete (1000/2990); compact
  parity is uncheckable`; the mismatch-only compact tree independently closes
  to 2,990 unique rows. The behavior is genuinely fail-closed.
- Containment wording caveat: the repair adds the reconciler and two explicitly
  requested focused test modules; the accounting documents are modified, not
  added. No unexpected tracked file or suite artifact was introduced.

### Next

- Write and commit `REVIEW-REPORT.md`.
- Append and commit the final ledger closeout, verify final status, and report
  the verdict without any remote or GitHub write.

## Independent repair re-review closeout

### State

- Phase: complete.
- Verdict: `APPROVE`.
- Reviewed target remains frozen at `58c6075f0`; subsequent local commits
  contain only this re-review's ledger and output report.

### Done

- Committed `REVIEW-REPORT.md` at `5da282c9` with exact first line
  `VERDICT: APPROVE` and the complete repair/containment evidence digest.
- Verified both prior mechanical findings are resolved, the required 7/7
  battery and 50 focused tests pass, protected artifact hashes/counts remain
  exact, and SSI truncation is pre-existing and fail-closed.
- Preserved `WORKER-REPORT.md` and `WORKER-REPORT-REPAIR.md` as the only
  pre-existing untracked files.
- Removed the partial untracked GitNexus index produced before its sandbox
  registry denial; it left no repository residue.
- Performed no remote or GitHub write.

### Next

- Handoff the committed local re-review ledger and `REVIEW-REPORT.md`.

---

## Spine Chunk 1 oracle build — SALT + itemized deductions — 2026-07-29

### State

- Worktree: `axiom-oracles/_worktrees/chunk1-oracle`.
- Branch: `fed-parity/chunk1-oracle-suites`.
- Starting point: local `origin/main`
  `f8ea6027984b9da73c6f4b58d15a20b450181ac4` (tree
  `27d02d523547c23a5a29d38a98babe90021420b6`).
- Scope: add the `us-salt-deduction-grid` and
  `us-itemized-taxable-income-deductions-grid` oracle suites specified by
  `SPINE-PLAN.md`, adopt exactly their two `us-pe` rows, and regenerate the
  dependent conformance/dashboard artifacts.
- Constraints: local commits only; no push or GitHub writes; expected values
  must come from the engine-verified RuleSpec PR #1177 companions;
  `WORKER-REPORT.md` remains untracked.

### Done

- Verified the source checkout was clean and the requested branch/worktree did
  not already exist.
- Created this branch and worktree directly from the recorded local
  `origin/main`.
- Began read-only inspection of the binding plan, RuleSpec companion evidence,
  generator contracts, and regeneration pipeline.

### Next

- Pin the exact RuleSpec PR #1177 head SHA/tree and transcribe the two verified
  companion case inventories into generator configs.
- Implement the generator, tests, bridge mappings, conformance rows, and
  evidence-rich divergence dispositions in coherent committed steps.
- Run real PolicyEngine generation on the declared stack, then the full
  regeneration and `--check` gate chain.

### Checkpoint — runner and registry implementation

#### State

- RuleSpec PR #1177 is pinned at
  `f4cc1b88d1efd8dcca25058695dc1735c0fbb3de` (tree
  `3388c508f2d565f3c067d3f9beb4bfd03182b9b1`) through the two comparison
  registries.
- Both federal configs, their complete adopted case inventories, their strict
  fixture contracts, the SALT output bridge, itemized diagnostic
  reconciliation, and all seven reviewed mapping rows are implemented.

#### Done

- Added explicit HOH and surviving-spouse situations and confirmed live PE
  simulations return filing-status enum values `0, 1, 2, 3, 4`.
- Added missing/extra/nonnumeric bridge rejection, compared-output separation,
  RuleSpec domain/only-input closure, undeclared PE-override rejection, and a
  fresh-Simulation-per-case test.
- Corrected the SALT builder after exact-stack measurement proved
  `real_estate_taxes` is a Person input in PE-US 1.767.3; the implementation
  error was fixed rather than dispositioned.
- The focused generator suite passes all 32 tests under Python 3.13 with
  PolicyEngine 4.18.9, PE-US 1.767.3, and Core 3.30.3. Ruff and
  `git diff --check` pass.

#### Next

- Commit the runner/registry step, then commit measured per-case evidence and
  dashboard reports separately.
- Regenerate the adoption/scoreboard chain and run every available
  `--check` gate before final handoff.

### Checkpoint — measured divergence evidence

#### State

- The two reports were generated from the clean pinned RuleSpec snapshot with
  Python 3.13, PolicyEngine 4.18.9, PE-US 1.767.3, and Core 3.30.3.
- Every raw mismatch belongs to a pre-registered §6.1/§6.2 divergence class;
  there are no boundary or unexplained implementation mismatches.

#### Done

- SALT measured `13/16` raw matches. Exact Axiom/PE values are:
  low-AGI ceiling `10000/5000`, §911 MAGI add-back `38900/40400`, and
  personal-property tax `4000/0`.
- Itemized deductions measured `15/17` raw matches. Exact Axiom/PE finals are:
  other-deduction §68 base `50000/47297.296875` (PE reduction
  `2702.702392578125`) and rational-rate probe
  `9459459.45945946/9459460` (PE reduction `540540.5`).
- Added one evidence-rich, source-expiring disposition per mismatching case,
  retaining a literal placeholder (since replaced with the filed issue URLs, policyengine-us#9167-#9171) for the main lane to fill after filing
  upstream issues. Both suites validate at 100% explained parity with zero
  orphaned, expired, or unexplained entries.
- Emitted the two declared dashboard reports with RuleSpec and engine
  provenance and confirmed `apply_dispositions.py --check`.

#### Next

- Commit the measured evidence/reports.
- Adopt exactly the two requested conformance rows, execute the ordered full
  regeneration chain, and prove write/check parity.

### Checkpoint — refreshed pin, adoption, and derived-data parity

#### State

- A final upstream audit found RuleSpec PR #1177 had advanced after the first
  evidence run. The authoritative pin is now
  `345c22030642cbd37a9fe46877591a8e1df5af7e` (tree
  `40e08f7dbaa88a70660006f3a5a32bfa283ebd85`) in both comparison registries
  and both regenerated reports.
- The two adopted companion files are byte-unchanged between the earlier
  signed head and this repaired/re-signed head, and all five measured values
  reproduced exactly.

#### Done

- Adopted only `us-pe:salt_deduction` and
  `us-pe:itemized_taxable_income_deductions`. Their notes state the 2026 exact
  engine stack, `16/16` and `16/17` nonzero counts, completed-return
  boundaries, explicit exclusions, and named placeholder issue
  placeholders.
- Ran the full ordered write chain: dispositions, grids, affected map,
  vacuous/freshness gate, dated scoreboard snapshot, ratchet, burn-down, and
  dashboard overview. No grid file changed.
- Ran all eight check forms successfully: 85 disposition files; 174 affected
  suites / 183 edges; 138 oracle-backed configs; 217 suites / 34 executable
  surfaces; 4 scoreboard jurisdictions / 3 conformant; no ratchet regression;
  4 burn-down series / 57 points; 218 overview reports.
- Focused exact-stack validation passes: 33 generator tests and 81 conformance
  tests with 2 unrelated skips. The broader validation pass previously
  completed 716 additional relevant tests with 2 unrelated skips. Ruff and
  `git diff --check` pass.
- US-PE coverage rises from 34 to 36 rows. Only the two requested detail rows
  change; unexplained and Axiom-attributed-open counts do not increase.

#### Next

- Commit the conformance and derived adoption artifacts.
- Perform one final live-pin/containment audit, write the untracked
  `WORKER-REPORT.md`, append the closing ledger entry, and hand off without
  pushing.

### Checkpoint — final-review test closure

#### State

- Final review found no numerical, mapping, disposition, provenance, or
  containment defect, but identified two missing direct assertions in the
  generator tests.
- Both test gaps are now closed before the adoption commit.

#### Done

- Replaced the self-referential Chunk 1 fixture test with a durable comparison:
  all 33 committed report `axiom_fixture_inputs` mappings are checked against
  the applicable exact fixture validator and RuleSpec input contract.
- Added a live exact-stack test that invokes both Chunk 1 PE parameter
  validators and independently asserts the complete §5 expected mappings:
  SALT sources/caps/thresholds/rate/floors/flags and itemized aggregate,
  applicability flags, five thresholds, and stored OBBBA rate.
- Exact-stack validation now passes 34 generator tests and 81 conformance tests
  with 2 unrelated skips. Ruff and `git diff --check` pass.
- Re-ran all eight read-only derived-data gates successfully: dispositions,
  grids, affected map, vacuous gate, scoreboard, ratchet, burn-down, and
  dashboard overview.

#### Next

- Commit the adoption artifacts and closed test contract.
- Complete the final live-pin/containment audit, append the closing ledger
  entry, and write the untracked worker report.

### Checkpoint — worker closeout

#### State

- The complete implementation is committed through `3cf99290`.
- The branch contains only the 26 intended ledger, generator, suite,
  disposition, mapping, conformance, test, history, and dashboard paths
  relative to `origin/main`.
- Both comparison registries and both reports pin live RuleSpec branch
  `fed-parity/chunk1-salt-itemized` at
  `345c22030642cbd37a9fe46877591a8e1df5af7e` (tree
  `40e08f7dbaa88a70660006f3a5a32bfa283ebd85`); the external worktree and its
  local origin ref agree exactly.

#### Done

- Final targeted review passed the two repaired test requirements and reported
  no remaining blocker.
- Reconfirmed raw/dispositioned results of SALT `13/16 -> 16/16` and itemized
  `15/17 -> 17/17`, with all five mismatches tied to their pre-registered,
  source-expiring evidence entries.
- Reconfirmed all eight derived-data gates, exact-stack focused tests, Ruff,
  diff hygiene, live pin, and changed-path containment.
- No corpus citation path changed, so the conditional citation census is not
  applicable; this repository exposes no citation-census command.
- No branch was pushed and no GitHub write was made.

#### Next

- Main lane: file the five upstream PolicyEngine issues from the measured
  evidence and replace each literal placeholder with its issue URL (done: policyengine-us#9167-#9171).
- Review and merge this local branch through the campaign's authorized main
  lane. No worker implementation step remains.

## 2026-07-28 main-lane closeout: issues filed, placeholders resolved (chunk1-oracle)

- State: review round 1 findings repaired on the main lane.
- Done: filed policyengine-us#9167 (simulation taxable-income ceiling),
  #9168 (AGI vs section 164(b)(7)(B)(iv) MAGI phaseout), #9169
  (personal-property-tax source omission), #9170 (section 68 proxy base),
  #9171 (truncated 2/37 rate); corrected #9168's repro entity binding and
  statutory subsection and #9170's pinned-arithmetic statement after the
  blind review verified both mechanisms; remapped the two shifted SALT
  evidence URLs (magi->9168, personal-property->9169); added
  evidence.upstream_url and the local comparison YAML source to all five
  dispositions per the us-qbid-grid model; replaced the five literal
  literals in conformance/us-pe.yaml adoption notes and regenerated the
  detail copies; full check battery green.
- Next: round-2 blind re-review, then merge after rulespec-us#1177 per the
  section 9 pairing order.

## 2026-07-29 spine Chunk 2 taxable-income oracle

### Checkpoint — worker start

#### State

- Work is isolated in `_worktrees/chunk2-oracle` on
  `fed-parity/chunk2-oracle-suite`.
- The sandbox blocks DNS, so a read-only `git fetch origin main` failed with
  `Could not resolve host: github.com`. The local `origin/main` is
  `2a1660dcd9e175f6e3fd5e34861cb302d1b1d54e`, immediately before the remote
  merge of PR #425.
- The worktree therefore starts at the locally available merged Chunk 1 head
  `def5c8cc8e0bd3f5450448f5fadfd7cb35220866`, whose first-parent merge
  includes local `origin/main` and whose tree is the tree merged remotely by
  PR #425. No push or GitHub write will be made.
- The binding RuleSpec target is PR #1179 at
  `4ced8fb7065311338ea732cab0a26105e750c40f`; its worktree, tree, companion
  assertions, and mapping candidates remain to be verified before changes.

#### Done

- Confirmed the requested branch name was unused and created the isolated
  worktree without modifying the caller's dirty root worktree.
- Read SPINE-PLAN §5, §6.3, and §9 Chunk 2 and identified the one-config,
  one-suite, exact-stack, evidence, adoption, and regeneration contracts.
- Confirmed the merged Chunk 1 implementation and final-review refs are
  locally available for structural reuse.

#### Next

- Verify the exact RuleSpec SHA/tree, engine-verified companion, three bridge
  variables, and three conformance mapping candidates.
- Trace the merged generator/tests and final SALT disposition schema, then
  implement and commit the runner/test step.

### Checkpoint — taxable-income contract implementation

#### State

- RuleSpec PR #1179 is pinned at
  `4ced8fb7065311338ea732cab0a26105e750c40f` with tree
  `9a4aaf64acd4c0cfe407cce5b3bb94516aaceacb`; the tracked worktree is clean
  apart from its unrelated untracked worker report.
- The sandbox also blocks `uv` from writing its cache at
  `/Users/maxghenis/.cache/uv`. Validation therefore uses the repository's
  Python 3.13.9 interpreter with the already-cached, read-only exact package
  roots for PolicyEngine 4.18.9, PolicyEngine-Core 3.30.3, and
  PolicyEngine-US 1.767.3.
- The exact companion omits imported zero-output assertions for three
  senior-only cases. A narrow supplemental assertion-closure fixture supplies
  only those five missing zero bridge assertions and supplies no scored
  taxable-income expected value.

#### Done

- Added the single `taxable_income` PolicyConfig and all 14 adopted §6.3
  cases, with all five filing statuses, direct election binding, the exact
  three-output bridge map named in the worker brief, independently derived
  standard/senior/exemption amounts, and fresh-simulation compatibility.
- Added an exact 85-input companion validator, reviewed auxiliary-module
  allowlist, complete diagnostic inventory, exact 2026 parameter/list
  validator, and strict bridge/input fail-closed checks.
- Added the pinned `us-taxable-income-grid` comparison config and exactly
  three registry mappings: taxable income, selected deductions, and the
  non-comparable verified-domain judgment.
- Exact-stack dry evaluation produced 14 values within the one-cent
  tolerance; 13 were bit-for-bit equal and
  `ti-senior-single-plus-one` differed by $0.0025.
- Ruff, 36 focused generator tests (two report-dependent tests deferred until
  generation), 26 bridge import-surface tests, and `git diff --check` pass.

#### Next

- Commit this coherent contract implementation.
- Create the clean canonical RuleSpec clone, run the registry comparison,
  inspect raw mismatches, and add dispositions only for measured mismatches.

### Checkpoint — exact-stack measured comparison

#### State

- A clean canonical RuleSpec checkout now exists at
  `/private/tmp/oracle-rerun/rulespec-us`; HEAD and the verified tree match the
  exact PR #1179 pin.
- The registry runner completed through its normal provenance, dashboard, and
  manifest path. Because its hardcoded `uv --with` subprocess cannot write the
  sandboxed uv cache or reach package indexes, a temporary untracked shim
  dispatched that exact command to the cached reviewed stack; the generator's
  independent version gate confirmed all three required package versions.

#### Done

- Generated `us-taxable-income-grid` under Python 3.13.9, PolicyEngine 4.18.9,
  PolicyEngine-US 1.767.3, and PolicyEngine-Core 3.30.3 from a fresh
  Simulation per case.
- The raw result is 14/14 matches, zero mismatches, and zero errors. The
  after-disposition result is also 14/14 with zero unexplained rows.
- No disposition file was created: none of §6.3's pre-registered divergence
  classes produced a mismatch in the primary election-bound grid.
- The only nonzero observed amount residual is the expected sub-cent float32
  representation in `ti-senior-single-plus-one`: Axiom $50,851.06 versus
  PolicyEngine $50,851.0625, a signed Axiom-minus-PolicyEngine difference of
  -$0.0025, within the $0.01 contract tolerance.
- All 38 focused generator tests, Ruff, and diff hygiene pass with the
  generated report present.

#### Next

- Commit the measured dashboard report and manifest entry.
- Adopt only `us-pe:taxable_income`, run the full derived-data regeneration
  chain, and prove `--check` parity.

### Checkpoint — taxable-income conformance adoption

#### State

- The measured report is committed at `92861ea4`; it has no mismatch entries
  and therefore no disposition dependency.

#### Done

- Adopted only `us-pe:taxable_income` into
  `us-taxable-income-grid`. The note records the direct boundary, three
  bridges, independent deductions, 14/14 raw and after-disposition result,
  sub-cent residual, and aggregate-suite exclusions.
- Extended the conformance allowlist/assertions to require this one Chunk 2
  adoption while keeping alternative minimum tax and foreign tax credit
  unadopted.
- The targeted conformance adoption test, Ruff, and diff hygiene pass.

#### Next

- Commit the adoption source change.
- Run the complete dispositions, grids, affected-map, vacuity, dated
  scoreboard snapshot, ratchet, burndown, and overview regeneration chain.

### Checkpoint — derived-data regeneration and parity

#### State

- The taxable-income adoption source is committed at `7f2356d2`.
- The full required regeneration chain was run with the UTC scoreboard
  snapshot date `2026-07-30`.

#### Done

- Re-applied dispositions, extracted every jurisdiction grid, regenerated the
  affected map and freshness register, wrote the dated scoreboard/detail
  snapshot, tightened the ratchet, rebuilt the burndown, and rebuilt the
  dashboard overview.
- Every paired parity command passes:
  `apply_dispositions.py --check`, `extract_grids.py --check`,
  `generate_affected_map.py --check`, `check_vacuous_gate.py --check`,
  `conformance_scoreboard.py --check`, `conformance_ratchet.py --check`,
  `conformance_burndown.py --check`, and
  `generate_dashboard_overview.py --check`.
- The exact-stack federal-generator plus conformance test battery passes with
  119 tests and 2 environment-conditioned skips. Ruff and diff hygiene pass.
- The regeneration changed only the expected affected-map, us-pe detail,
  dated history, scoreboard, ratchet, burndown, freshness, and overview
  artifacts; canonical grids were already byte-identical.

#### Next

- Commit the derived artifacts.
- Run the full repository test/lint battery, inspect final containment and
  committed history, append the closeout ledger entry, and write the untracked
  worker report.

### Checkpoint — taxable-income diagnostic contract closure

#### State

- The first full regeneration is committed at `71a77451`; a final contract
  audit found three evidence gaps that did not change the scored 14-case grid.

#### Done

- Added a separate, non-scored `unbound-itemization-heuristic` diagnostic
  family. Each primary case still binds the legal section 63(e) election, while
  a second fresh PolicyEngine simulation removes exactly that override and
  records the engine-derived branch as an `oracle-model boundary`.
- Measured the unbound family on the exact pinned stack. All 14 heuristic
  results agree with the registered elections: 12 nonitemizers and 2
  itemizers. Diagnostic rows remain outside cases, aggregates, and raw or
  after-disposition counts.
- Completed the five-status aged/blind parameter assertion: $2,050 for single
  and head of household, and $1,650 for joint, separate, and surviving spouse.
- Restored the shared-contract meaning of `rulespec_only_inputs` by leaving it
  empty for taxable income; the exact 85-input fixture validator continues to
  record and reject drift in all companion inputs.
- Added fail-closed config validation, distinct-simulation regression coverage,
  14-case component/bridge/diagnostic reconciliation, and exact tests for all
  three worker-handoff registry mappings.
- Refreshed the comparison through the official runner shape. The report
  remains 14/14 with zero mismatches and zero errors, and now carries the
  separate diagnostic family.
- A direct probe through the repository venv was correctly rejected because
  its installed metadata resolves PE-US 1.752.2/Core 3.28.0. The successful
  rerun used Python 3.13 with isolated cached PE 4.18.9, PE-US 1.767.3, and
  Core 3.30.3; the generator's independent version gate passed.

#### Next

- Commit the diagnostic-contract source, tests, and refreshed measured report.
- Regenerate every conformance derivative affected by the adoption-note
  clarification, prove the complete `--check` chain again, and close out the
  full test/containment audit.

### Checkpoint — diagnostic derivative parity

#### State

- The unbound diagnostic implementation, strengthened parameter/input
  contracts, refreshed exact-stack report, and focused tests are committed at
  `479bab42`.

#### Done

- Re-ran dispositions, canonical grid extraction, affected-map generation,
  vacuity/freshness, the UTC `2026-07-30` scoreboard snapshot, ratchet,
  burn-down, and dashboard overview after the conformance-note clarification.
- The history snapshot and ratchet were already current. Only the US
  conformance detail copies, freshness timestamps, and overview bundle changed.
- All eight paired checks pass: dispositions, grids, affected map,
  vacuity/freshness, scoreboard, ratchet, burn-down, and overview.

#### Next

- Commit the refreshed derivatives.
- Run the complete repository test suite with the cached esbuild executable,
  repeat lint and containment audits, append the final closeout, and write the
  untracked worker report.

### Closeout — Chunk 2 taxable-income oracle

#### State

- Source and measured evidence are committed through `507ebc36`.
- The branch is ready for main-lane review; no push or GitHub write was made.

#### Done

- Final evidence is 14/14 raw matches, zero mismatches, zero errors, and 14/14
  after disposition with zero unexplained rows and no disposition file.
- The only nonzero final residual is
  `ti-senior-single-plus-one`: Axiom $50,851.06 versus PolicyEngine
  $50,851.0625, signed Axiom-minus-PolicyEngine -$0.0025, within $0.01.
- The non-scored unbound itemization family records 12 nonitemizers and 2
  itemizers; all 14 agree with the legal elections.
- The exact-stack generator/conformance battery passes with 122 tests and 2
  environment-conditioned skips. The normal full repository suite passes with
  2,323 tests and 70 skips. Ruff, formatter checks on the touched Python files,
  diff hygiene, Git object integrity, and all eight derived-data parity checks
  pass.
- Final containment against the Chunk 1 merged tree is exactly 20 intended
  paths. An independent read-only audit found no implementation, adoption,
  evidence, or containment blocker.
- `PROGRESS.md` remains byte-prefix append-only across every task commit.
- The pinned companion asserts all 14 scored taxable-income finals, all 14
  deduction diagnostics, and all 14 verified-domain judgments. It omits five
  zero-valued assertions across the three bridge outputs; the committed narrow
  supplemental fixture supplies only those zero bridge assertions, is
  fail-closed/tested, and is reported transparently. It supplies no scored
  expected.
- Environment disclosures: DNS blocked the requested remote refresh and npm/uv
  resolution, so the branch used the locally verified Chunk 1 merged tree and
  cached exact packages. The filesystem sandbox rejected one attempt to place a
  temporary launcher under `/private/tmp`; launchers were instead created
  inside the worktree and deleted after use. A direct repository-venv probe was
  rejected by the generator's version gate, as intended. A later `python -S`
  full-suite probe disabled editable-package and pandas loading and produced 14
  environment-only failures; the normal-environment full rerun passed.

#### Next

- Main lane reviews the 20-path branch, the untracked `WORKER-REPORT.md`, and
  the five-zero supplemental bridge-assertion caveat.
- If main lane requires those five bridge assertions inside RuleSpec itself,
  add them upstream, engine-verify a new RuleSpec commit, and advance both the
  SHA and tree pins together; do not mutate the exact `4ced8fb7` evidence.
- No upstream issue or disposition filing is warranted by the measured grid.
