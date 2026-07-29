# Month-scoped suite regeneration audit

## State

- Branch: `data/month-fix-regen`
- Base: `origin/main` at `819f370bf0346e4a6a8dfb1c8c4f0d873d6d0340`
- Purpose: defensively regenerate the 19 US month-scoped comparison suites after
  the requested-month PolicyEngine runner fix merged in `86be7721`.
- Required oracle stack: `policyengine==4.18.9`,
  `policyengine-us==1.767.3`, `policyengine-core==3.30.3`.
- Containment: the 19 suites, their dispositions, shared regenerated artifacts,
  row notes whose counts change, and this ledger only.
- Phase: complete. All 19 suites are regenerated, dispositions revalidated,
  shared artifacts refreshed, final checks complete, and the untracked worker
  report written.

## Done

- Created an isolated worktree from the exact local `origin/main` ref.
- Confirmed the worktree branch tracks `origin/main`.
- Audited one committed report shape and all nine TANF/SSI configurations and
  program outputs before regenerating. The requested comparison period remains
  `2026-01` for every suite: changing it to a year would evade the runner fix.
- Reconciled the Axiom side to true-month units without changing any tolerance:

  | Suite | Period decision | Axiom comparison output |
  |---|---|---|
  | `al-tanf-ecps` | keep `2026-01` | `al_tanf_monthly_benefit` |
  | `az-tanf-ecps` | keep `2026-01` | `az_tanf_monthly_cash_benefit` |
  | `de-tanf-ecps` | keep `2026-01` | `de_tanf_monthly_benefit` |
  | `ga-tanf-ecps` | keep `2026-01` | `ga_tanf_monthly_benefit` |
  | `ks-tanf-ecps` | keep `2026-01` | new `ks_tanf_monthly_maximum_benefit` wrapper |
  | `mn-tanf-ecps` | keep `2026-01` | `mn_mfip_monthly_cash_benefit` |
  | `ny-tanf-ecps` | keep `2026-01` | `ny_tanf_benefit` |
  | `wa-tanf-ecps` | keep `2026-01` | `wa_tanf_monthly_benefit` |
  | `ssi-ecps` | keep `2026-01` | new `ssi_monthly_benefit` household output |

- Kept each literal `$25` TANF/SSI tolerance unchanged; movements must be
  exposed and disposition evidence revalidated, not absorbed by tolerance.
- Added the declared Python/PolicyEngine pins to every affected config that did
  not already carry them and corrected Minnesota's stale New York description.
- Replaced eight stale `$HOME/axiom-oracles/programs/...` TANF references with
  repository-relative paths during local regeneration so the isolated worktree
  composed the audited files, not an unrelated historical checkout.
- Confirmed from the pinned PolicyEngine-US metadata that all nine oracle
  variables have `MONTH` definition periods. Confirmed the corresponding Axiom
  leaves are monthly, except the Arizona and SSI annual leaves whose new
  wrappers correctly divide by 12.
- Repointed Minnesota, New York, and Washington TANF from missing copied
  state-root directories to the canonical `rulespec-us` monorepo checkout,
  matching the already-working Arizona/Kansas composition pattern.
- Corrected the Kansas suite description from shelter group V to group I,
  matching both the bridge's fixed inputs and PolicyEngine's no-county fallback.
- The sandbox blocks `uv` from initializing its default cache under
  `$HOME/.cache/uv` (`sdists-v9/.git: Operation not permitted`). Verified the
  established read-only cache overlay used by the #423 lane instead: host
  `policyengine==4.18.9` plus cached `policyengine-us==1.767.3` and
  `policyengine-core==3.30.3`; the runtime reports all three exact versions.
- Prepared a clean, local-only RuleSpec clone at cached `origin/main`
  `c13cdf7dda5948e7a86ff0c317872f93743a2084` under `/private/tmp` because
  the `$HOME/rulespec-us` worktree is a dirty historical TANF branch and lacks
  three SNAP program specs. This clone is run input only and is not committed.
- Composed and compiled all eight TANF programs plus SSI successfully after the
  root fixes.
- Targeted validation passed 92 tests with 3 skips. One
  `test_materialize_ci_workspace` assertion remains stale: it requires the old
  `$HOME/axiom-oracles` symlink solely because it assumes the superseded
  absolute TANF program path; the repository-relative program path needs no
  such materialization. The containment order excludes test-file edits.
- Captured the committed pre-regeneration baseline:

  | Suite | Raw mismatches | Unexplained |
  |---|---:|---:|
  | `al-snap-ecps` | 53 | 23 |
  | `az-snap-ecps` | 597 | 0 |
  | `ca-snap-ecps` | 684 | 96 |
  | `fl-snap-ecps` | 834 | 834 |
  | `ga-snap-ecps` | 250 | 80 |
  | `ma-snap-ecps` | 255 | 83 |
  | `nc-snap-ecps` | 99 | 71 |
  | `ny-snap-ecps` | 354 | 349 |
  | `sc-snap-ecps` | 181 | 106 |
  | `tn-snap-ecps` | 68 | 41 |
  | `al-tanf-ecps` | 0 | 0 |
  | `az-tanf-ecps` | 4 | 0 |
  | `de-tanf-ecps` | 0 | 0 |
  | `ga-tanf-ecps` | 1 | 0 |
  | `ks-tanf-ecps` | 6 | 0 |
  | `mn-tanf-ecps` | 0 | 0 |
  | `ny-tanf-ecps` | 36 | 0 |
  | `wa-tanf-ecps` | 0 | 0 |
  | `ssi-ecps` | 3,067 | 0 |

- Regenerated all eight TANF suites and SSI under the declared stack; every
  full report records PolicyEngine `4.18.9`, US `1.767.3`, and core `3.30.3`.
  The true-month raw residuals are AL 3, AZ 0, DE 0, GA 1, KS 218, MN 0,
  NY 36, WA 0, and SSI 2,990.
- Revalidated rather than silently carrying annualized disposition evidence:

  - deleted Arizona's expired four-row disposition;
  - pinned Georgia's surviving case to `0 / 164.970459` (exactly one twelfth
    of the legacy PE amount);
  - replaced Kansas's blanket prefix with seven exact county-group case sets
    (212 rows, each PE-Axiom = $43) and six individually pinned
    applicable-SSI assistance-unit rows;
  - replaced New York's blanket prefix with exact 30 both-positive and 6
    zero-left case sets, documenting 6 vanished and 6 new identities;
  - refreshed SSI's full 2,990-row evidence from a direct PE eligibility join
    and removed obsolete subtype counts and the now-within-tolerance
    `ecps-588` representative.

- Corrected the Kansas program and projector notes: the Axiom bridge fixes
  shelter group I, while PolicyEngine 1.767.3 derives actual county groups.
- Rebuilt Arizona TANF's dashboard copy from its regenerated full report after
  deleting the vanished four-row disposition, so the report now records a null
  dispositions file with no expired legacy entry.
- Restored the eight committed TANF config paths to the CI materializer's
  `$HOME/axiom-oracles/...` convention after regeneration; the focused
  materialization suite now passes all 7 tests. The temporary relative paths
  were an execution overlay, not a portable config change.
- `apply_dispositions.py --check` passes after the TANF/SSI refresh, and the
  focused disposition/requested-month test battery passes (22 tests).
- The SNAP composition preflight exposed two sandbox/toolchain constraints.
  The configured July 6 release binary predates `compile-composed`; a current
  offline rebuild recognizes it but rejects an unrelated noncanonical Unicode
  filename in the cached RuleSpec tree. No source checkout was altered.
  The committed compatibility fallback succeeds when its legacy resolver is
  pointed at the clean `/private/tmp` clone's parent, so the SNAP regeneration
  uses that established release engine and clean RuleSpec input.
- Regenerated seven SNAP suites on the declared engine stack and re-applied
  their dispositions:

  | Suite | Before raw/unexplained | True-month raw/unexplained |
  |---|---:|---:|
  | `al-snap-ecps` | 53 / 23 | 56 / 40 |
  | `az-snap-ecps` | 597 / 0 | 597 / 0 |
  | `fl-snap-ecps` | 834 / 834 | 774 / 774 |
  | `ga-snap-ecps` | 250 / 80 | 245 / 75 |
  | `ma-snap-ecps` | 255 / 83 | 263 / 92 |
  | `ny-snap-ecps` | 354 / 349 | 245 / 240 |
  | `tn-snap-ecps` | 68 / 41 | 70 / 43 |

- Revalidated their legacy evidence row by row. Alabama drops 14 materially
  moved TANF-counterfactual classifications rather than silently retaining
  them; Massachusetts refreshes 17 TANF pins and drops one invalidated row;
  Tennessee refreshes all 23 TANF pins. The AL/MA/TN lone-minor case sets are
  unchanged, with their moved benefits explicitly recorded. New York's five
  BBCE boolean rows are byte-identical and remain classified; an interrupted
  worker's deletion of that still-valid disposition was reversed.
- Across these seven suites, 524 old `23.973597208658855` mismatch rows became
  511 rows at January's `23.84000015258789`, three at other true-January
  amounts, and ten matches. CA/NC/SC remain to be measured.
- Regenerated North Carolina and South Carolina SNAP on the same declared
  stack. North Carolina moved from `99 / 71` raw/unexplained to `76 / 49`;
  South Carolina moved from `181 / 106` to `185 / 110`. Both reports record
  PolicyEngine `4.18.9`, US `1.767.3`, and core `3.30.3`.
- Replayed all 40 surviving NC/SC TANF bridge households through direct
  requested-period simulations. All 11 North Carolina and 29 South Carolina
  zero-TANF counterfactuals reproduce the fixed-runner baseline and close
  within the unchanged $7 tolerance. Their legacy pins all moved materially
  and are now replaced with exact January pins and old-to-new evidence.
- The NC/SC lone-minor case sets are unchanged (three and two cases,
  respectively). All five eligibility rows are unchanged; all five benefit
  rows moved materially and are explicitly listed in their evidence. The
  obsolete North Carolina BBCE amount selector was deleted after its sole
  mismatch vanished. No current NC/SC disposition is expired or orphaned.
- North Carolina's two and South Carolina's 64 old
  `23.973597208658855` rows all persist at January's
  `23.84000015258789`. Across the nine completed SNAP suites, the old constant
  therefore resolves to 577 rows at `23.84000015258789`, three other
  true-January amounts, and ten matches; California's 45 rows remain.
- Verified the saved #423 California replay receipt at SHA-256
  `c46af9b87c8f5ad01f1909bc45e80e00b4c4a50e5b802ea4ccbe194b5954b568`
  with its hardened builder and pinned base. It validates 341 issue-362 rows
  and predicts 29 repaired rows, 172 materially moved surviving pins, and 140
  unchanged surviving pins on that base. Its authoritative YAML is used as
  evidence input only; no unrelated #423 commit is imported.
- A defensive California BBCE review found 83 of the 243 legacy annotations
  contradict their stated Axiom gate proof. The reconciliation removes both
  unsupported asset-waiver selectors and retains only the clean gross-band
  proof: 79 eligibility rows and 78 benefit rows. Three otherwise-supported
  identities vanished, and all 78 surviving benefit pins moved materially.
- The first California regeneration reached batch 68 of 72 before the process
  was killed with signal 9. A retry kept cyclic garbage collection enabled
  (the runner disables it by default) and completed all 72 batches under the
  exact declared stack. This was a runtime-only containment measure.
- California regenerated from `684 / 96` raw/unexplained to `529 / 241`.
  Its final disposition set classifies 157 BBCE encoding rows, 111 bridge
  rows, and 20 upstream-engine rows. No disposition is expired or orphaned.
- The current clean RuleSpec checkout differs from the pinned #423 base, so the
  341 issue entries were revalidated fail-closed against both sources. Of
  those, 188 current identities vanished; 22 still exist but no longer
  reproduce the replay's requested-month left/right evidence and were flagged
  and dropped; 131 reproduce it exactly and were retained. Among those 131,
  115 legacy pins moved materially and 16 are unchanged.
- California's 45 old `23.973597208658855` rows became 42 rows at
  `23.84000015258789` and three matches. Across all ten SNAP suites, the 635
  old constant rows therefore became 619 rows at January's
  `23.84000015258789`, three rows at other true-January amounts, and 13
  matches.
- Verified all 19 regenerated reports record PolicyEngine `4.18.9`,
  PolicyEngine-US `1.767.3`, and PolicyEngine-Core `3.30.3`.
- Caught and removed 67 stale California row-level labels left by applying the
  final dispositions additively over the generation-time legacy merge. Rebuilt
  the dashboard copy from the raw regenerated report with the final YAML and
  re-emitted its case explorer. The report, case artifacts, and rollup now
  agree exactly at 157 encoding + 111 bridge + 20 upstream annotations, with
  zero silent classifications.
- Refreshed all 19 case-artifact trees, all 13 affected disposition artifacts,
  the affected map, freshness register, conformance scoreboard/detail and
  four jurisdiction history snapshots, burn-down, and dashboard overview.
  Removed Arizona TANF's now-obsolete served disposition artifact.
- Corrected Kansas and New York TANF evidence citations to tracked
  config/mapping sources available to the hermetic refresh fixture. Its full
  11-test concurrency/regeneration suite now passes.
- A first full pytest run reached 2,273 passes and 70 skips. Ten failures from
  the now-corrected evidence citations were re-run successfully; the only
  independent failure was `npx esbuild` attempting a network download in the
  network-restricted sandbox.
- The state-tax populace contract passes checkout-locally (43 jurisdictions,
  32 ready, 11 blocked). Invoking the parent checkout's editable virtualenv
  without `PYTHONPATH=.` imports a different parent `axiom_oracles` tree and
  falsely reports DE/MN metadata drift; the governing files are identical at
  this branch's base, HEAD, and local `origin/main`.
- Final post-commit gates pass: comparison registry listing (135 entries),
  rule verification (21,859 rules), checkout-local state-tax contract,
  dispositions (82 files), selected affected case artifacts (zero silent
  classifications), all 13 affected disposition artifacts, grids, boundary
  cases, affected map, vacuous gate, dashboard overview, conformance
  universes/compositions, scoreboard, ratchet, and burn-down.
- The final broad Python run, excluding only the separately exercised
  network-dependent dashboard loader, passes 2,283 tests with 70 skips. The
  loader's `npx esbuild` invocation cannot reach the npm registry in the
  network-restricted sandbox (`ENOTFOUND`). Ruff is not installed in the
  declared virtualenv.
- Additional sandbox disclosures: `ps` and `sysctl -n hw.memsize` were denied
  during the California recovery audit; process status and memory pressure
  were checked with permitted alternatives. The bare system Python lacks
  PyYAML, so all repository checks used the declared virtualenv.
- Wrote the required final audit report to untracked `WORKER-REPORT.md`.

## Next

- No implementation work remains. Handoff the committed branch HEAD and
  untracked worker report; do not push.

# Blind review of `data/month-fix-regen`

## State

- Review target: local `data/month-fix-regen` at immutable commit
  `f0a6598e1337310fdf2f663af91b7ab81f773491`.
- Review base declared by the branch:
  `819f370bf0346e4a6a8dfb1c8c4f0d873d6d0340`.
- Disposable worktree:
  `.git/review-worktrees/month-fix-regen-f0a6598e-blind`.
- Local review branch: `review/month-fix-regen-f0a6598e-blind`.
- Rules: no writes to the target branch, remotes, or GitHub; all review
  artifacts and commits remain on this local review branch.
- Required replay stack: `policyengine==4.18.9`,
  `policyengine-us==1.767.3`, `policyengine-core==3.30.3`.
- Output: `REVIEW-REPORT.md`.
- Verdict: pending evidence.

## Done

- Read the `gitnexus-pr-review` workflow and adapted it to a local branch
  comparison.
- Verified the supplied target worktree and local branch both resolve to the
  requested immutable commit.
- Created this disposable review worktree directly from that commit.
- Preserved the worker's complete ledger above and appended this review ledger.

## Next

1. Freeze the base-to-target diff and audit affected-set containment.
2. Verify stack pins, report engine blocks, and unchanged suite tolerances.
3. Replay California SNAP, one TANF suite, and SSI for byte parity.
4. Audit California disposition drops/retentions and January-value movement.
5. Verify comparison-period decisions and AL/KS TANF outcomes.
6. Run the complete derived-artifact check battery and reconcile totals.
7. Write and commit `REVIEW-REPORT.md`, append the closing ledger entry, and
   issue the recorded verdict.

## Review checkpoint — regeneration and independent audits

### State

- Required replays: complete with byte parity.
- Containment, disposition, period-semantics, and chain audits: complete.
- Provisional verdict: request changes because the target rewrites the existing
  progress ledger; final report remains to be written.

### Done

- Replayed `ks-tanf-ecps` with 861 cases and 218 mismatches. The regenerated
  dashboard artifact is byte-identical to the committed artifact at SHA-256
  `1132d023920d768577617e074b914cd17c89a057dd7fd893c5052454b4a33532`.
- Replayed `ssi-ecps` with 75,112 cases and 2,990 mismatches. Byte-identical
  artifact SHA-256:
  `0eb73772a9220a0cd0aaeb1ec174a43fab61bf33289f56c600202a1f7128399b`.
- Replayed `ca-snap-ecps` through all 72 comparison batches with cyclic garbage
  collection retained. It produced 7,101 cases and 529 mismatches and is
  byte-identical at SHA-256
  `d5b95f7c8f9e9a66f5146dcf82bcfe719c6433cb150217a181f4db959fe3911d`.
- Each replay reported `policyengine==4.18.9`,
  `policyengine-us==1.767.3`, and `policyengine-core==3.30.3`; every
  provenance field other than the inherently volatile `generated_at` matched
  independently. The committed timestamp was then reused for the literal byte
  comparison.
- Accounted for all 194 target paths and found no foreign artifact paths. The
  primary reports and case trees cover exactly the 19 requested suites.
  CA/CO TANF, Medicaid MAGI, and UKMOD suite artifacts remain unchanged.
- Verified no comparison tolerance changed and all 19 reports/configs carry
  the declared engine stack.
- Reconstructed the California disposition results: the repaired 341-row
  evidence source yields 188 vanished, 22 drifted/unclassified, and 131
  retained rows; the requested vanished and retained samples pass.
- Identified a provenance caveat: the literal merged #423/base tree contains
  345 rather than 341 issue identities. Its accounting is 192 vanished, 22
  drifted, and 131 retained; the four additional vanished identities belong
  to `ecps-59082` and `ecps-62506`. The 341-row reconciler and exact drift
  receipt are untracked temporary files, and the tracked HEAD builder cannot
  read the refreshed compact case schema.
- Reconciled the old SNAP minimum-benefit class exactly:
  635 becomes 619 at `23.84000015258789`, three at other January values, and
  13 matches.
- Verified all nine TANF/SSI suites retain monthly `2026-01` semantics and
  unchanged `$25` tolerance. Kansas's 218 rows are evidence-backed; Alabama's
  three new rows are unclassified and unexplained.
- The complete required derived check battery passed, including byte
  recomputation of all four history snapshots. Every requested suite row
  reconciles, including California
  `529 = 157 + 111 + 20 + 241`.
- Found the blocking containment failure: base `PROGRESS.md` has 951 lines and
  the target has 245; base-to-target numstat is `+245/-951`, so the target
  replaced rather than appended the pre-existing ledger.

### Next

1. Write and commit the self-contained verdict and evidence to
   `REVIEW-REPORT.md`.
2. Append the final review closure to this ledger and commit it.
3. Confirm the disposable review worktree is clean and report the verdict
   without any remote or GitHub write.
