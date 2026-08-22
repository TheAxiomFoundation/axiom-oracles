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

### Completed measured-discovery artifacts

- Captured all 3,548 pinned corpus rows (3,376 statute and 172 regulation)
  against corpus commit `6f064ee6081f16440dc706ae09ac60652bb67570` and
  release content sha256
  `b4b405a06bfcf21331cff50a45844fd0117b52212dc24d0f4912ed07575fd574`.
  A hermetically rederivable global index covers all 3,548 rows, all 3,545
  string bodies, and 25 acts. It retains 23 Fundstelle facts, 18 `stand`
  changed-by analogues, 2,859 resolved-or-verbatim body-reference facts, and
  36 amendment targets with source/target hashes. Program frontiers are a
  separately documented relevant-root projection; a grounded UhVorschG §1
  reference to BEEG found by the expanded scan raised the UhV candidate count
  by one without dispositioning it.
- Committed subject-query set `de-subject-matter-2026-08-21-v1`. All 15 URL
  retrieval attempts are recorded as `unretrieved` with the actual
  `URLError: [Errno 8] nodename nor servname provided, or not known` failure;
  no response metadata or byte hash is asserted. The citation-scan channel is
  a sha-bound `not_yet_available` receipt for `axiom-corpus#611`.
- Generated the three schema-v3 all-pending ledgers from empty committed
  decision lists. Every provision, instrument candidate, and typed frontier
  input is pending; all three ledgers compute `closed: false`.
- Measured denominators:

  | candidate | spine | candidate instruments | law-derived leaves | depth lower bound | oracle work | executable work |
  | --- | ---: | ---: | ---: | ---: | ---: | ---: |
  | `de/kindergeld` | 18 | 28 | 4 | 1 | 0 | 0 |
  | `de/unterhaltsvorschuss` | 12 | 21 | 0 | 2 | 2 | 1 |
  | `de/rv-employee-contribution` | 3 | 11 | 0 | 1 | 2 | 1 |

- Spine counts are pinned-corpus scope counts. Instrument counts are unique
  candidates found by any captured channel and mean *potentially bearing*,
  not a legal classification. Law-derived counts include only classifications
  already committed in `closure/de/source.json`. Depth is the maximum captured
  declared-module-to-frontier chain and is a lower bound. Remaining work is a
  target-minus-complete count from the sha-bound current certificate inventory.
- The instrument and depth figures remain lower bounds because every network
  row is unretrieved, citation scan #611 is unavailable, and root-reachable
  transitive RuleSpec import traversal belongs to the stabilization sprint.
  Work counts can grow when that sprint fixes the claim surface or reviewers
  disposition the pending frontier.

### Validation and handoff

- Hermetic snapshot and ledger rederivation checks pass. The new DE suite is
  44/44 green; the existing DK closure mutant suites are 50/50 green; Ruff,
  bytecode compilation, and `git diff --check` pass. Exact commands and hashes
  are recorded in `ops/de-certification/validation-2026-08-21.txt`.
- A broader central-gate selection reports 345 passed and four failures, all
  in pre-existing DE certificate tests because
  `conformance/de-certificate-census.json` does not rederive. The underlying
  `python scripts/de_certificate_census.py --check` failure reproduces at the
  untouched starting commit `56f4e93f3`; this lane does not refresh or wire
  that unrelated central artifact.
- Stabilization must still settle the jurisdiction-neutral v3 shape for
  unclassified leaves, bind one claim surface across all premises, traverse
  imports/root-reachable dependency edges, implement successful-query result
  capture and pagination, consume citation scan #611, and centrally validate
  without program-name conditionals.

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
