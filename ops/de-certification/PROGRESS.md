# DE axiom legs and executable replay progress

## State

- Worktree: `axiom-oracles-decert` on `feat/de-certificates`.
- Starting commit: `482095a42` (`docs: relocate DE certification report under ops; drop scratch progress log`).
- Objective: add pinned rulespec-DE axiom comparison legs and released-engine replay wiring so the `(de, kindergeld)` certificate becomes certified by computation as soon as `de/statutes/estg/66.yaml` is present and signed at the pinned ref.
- Pre-signing behavior must be honest and skip-graceful: missing required modules produce `pending: module-not-on-main`, never a conformant or executable success.
- The repository-root `PROGRESS.md` belongs to another lane and is intentionally untouched.
- Current pre-sign result: both Axiom pair records and the Kindergeld module
  view are `leg-pending` with the exact `pending: module-not-on-main` marker;
  the computed certificate remains `no`.
- Implementation, branch-baseline verification, and the designated final
  result report are complete for the pre-signing state.

## Done

- Confirmed a clean worktree and preserved the existing DE certificate commit stack.
- Read and adopted `ops/encoder-hygiene/PATH-DISCOVERY-RULES.md` from the shared operations checkout.
- Completed scoped audits of the DE certificate, unified-record, selectors,
  refresh path, and the US released-engine receipt machinery.
- Added the two exact-name, pinned Axiom↔EUROMOD and Axiom↔GETTSIM registry
  legs over the canonical 13-household population.
- Added a six-view dependency plan. Signed SGB-5/241 is recorded only as a
  partial health-insurance dependency; no incomplete output is fabricated.
- Added exact pinned-ref Git-object inspection and regenerated both pending
  records, including the signed SGB-5/241 apply-manifest hash.
- Added released-engine replay and signed EStG 66 bindings, computed
  certificate consumption, transition/pending mutants, and a synthetic
  `certified=yes` conjunction test.
- Added affected-map generation to the refresh write/check/stage transaction;
  both new selector names appear in the force-all matrix.
- Documented the two YAML pin locations and the deliberate repin/live-run
  procedure.
- The no-push refresh simulation passes end to end: 181 affected-map suites,
  223 freshness suites, 34 executable surfaces, and 6 certificate
  jurisdictions.
- Focused leg/registry/selector battery: 113 passed. All mutant modules pass
  143/143; the focused DE selection passes 47/47 (46 baseline plus the new
  computed flip mutant).
- Baseline isolation at `482095a42`: 2,712 collected, 2,641 passed, 70 skipped,
  and the one network-only dashboard-loader failure in 834.89 seconds.
- Current collection: 2,736 tests (+24). In the same Python 3.13.9 / pytest
  8.4.2 environment, the two optional-policy tests that failed only under the
  ambient interpreter pass. The full run without the two-test dashboard-loader
  file is green at 2,699 passed / 35 skipped in 661.51 seconds, and the second
  dashboard test separately passes. Complete coverage excluding only the one
  reproduced baseline failure is therefore 2,700 passed / 35 skipped.
- Final deterministic checks are green for both Axiom pair records, the unified
  record, executable status, certificate census/certificates, affected map
  (181 suites / 193 edges), exact selectors, Ruff, and `git diff --check`.
- Implementation commits are `2a1485a69` and `d58e72a09`, stacked without
  rewriting the existing certificate commits. No push or PR was made.
- Wrote the final architecture, pin, output-coverage, replay, mutant, refresh,
  and baseline comparison report to
  `ops/de-certification/result-2026-08-17.md`.

## Next

- When a correct signed 2025 EStG 66 module and apply manifest land on
  RuleSpec-DE main, deliberately bump the commit/tree pins in both Axiom pair
  configs and run the supervised x86_64 Linux replay producer.
- Do not promote the current parallel draft if it still encodes EUR 259: the
  canonical 2025 oracle grid requires EUR 255 per child / EUR 765 total, and
  the live comparison is expected to reject that mismatch.
