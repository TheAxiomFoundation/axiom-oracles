# DE measured-discovery ledger progress

## Current lane (2026-08-21)

- Worktree: `oracles-de-discovery`, branch `feat/de-discovery-ledgers`, starting
  at `56f4e93f3` (`origin/main`).
- Objective: produce all-pending `axiom_oracles.closure.ledger.v3` discovery
  ledgers for `de/kindergeld`, `de/unterhaltsvorschuss`, and
  `de/rv-employee-contribution`; no RuleSpec encoding and no certification or
  refresh-chain wiring is in scope.
- Read first, in the requested order: `CERTIFIED.md`; the issue #502 brief;
  the DK capture/generator/snapshot/ledger/mutant reference files. Also read
  the mandated path-discovery rules and the cross-family strategy review.
- The repository-root `PROGRESS.md` is dispositions evidence and remains
  untouched.

### Preregistered discovery scopes

- `de/kindergeld`: the spine is EStG sections 62 through 78 inclusive. This
  selects the conservative branch of the preregistered §§62–66 versus §§62–78
  decision before the automated discovery snapshot is generated. The broad
  program name and its entitlement/payment surface do not justify silently
  omitting application, award-change, payment, and special-payment provisions.
  EStG §31, BKGG, DA-KG, and other discovered dependencies stay in the pending
  instrument frontier; this is not a legal disposition.
- `de/unterhaltsvorschuss`: the spine is every direct provision of the compact
  UhVorschG governing act (sections 1 through 12). The declared MinUhV §1 and
  EStG §66 dependencies are roots/candidates outside that governing-act spine.
- `de/rv-employee-contribution`: the spine is the three exact, already-declared
  source provisions in `closure/de/source.json`: BSV 2018 §1, SGB VI §168, and
  SVBezGrV 2025 §4. This program name is an expressly narrow contribution-share
  calculation rather than a claim over every provision of SGB VI.

### Open decision points and constraints

- The DK v3 producer requires committed classifications for every input and
  instrument. This no-disposition sprint instead derives `pending` from empty
  decision lists. `leaf_kind` is a separate axis: the four Kindergeld rows
  already classified by `closure/de/source.json` remain `law_derived`; every
  other discovered boundary input is `unclassified` pending human review.
- The current central dependency gate has no `unclassified_inputs` field. The
  DE producer will count those inputs honestly, which is intentionally
  fail-closed under today's central shape. Reconciliation belongs to the #502
  stabilization sprint; this lane will not edit `scripts/certify.py`.
- Direct network probes from this sandbox currently fail at DNS resolution.
  The subject-search capture will record each attempted URL as `unretrieved`
  with the actual failure and will not infer titles, dates, page counts, or
  byte hashes.
- The requested `-o` report target is
  `/Users/maxghenis/TheAxiomFoundation/ops/de-lane/de-discovery-ledgers-report.md`;
  the Codex CLI captures the final response there.

## Prior lane: DE axiom legs and executable replay

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
