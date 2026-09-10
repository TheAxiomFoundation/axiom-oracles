# DE measured-discovery ledger progress

## Stabilization sprint (2026-09-04, Pavel owning)

- oracles#498 fixed: certificates recompute on macOS (per-target engine
  pins; the receipt still binds the producing x86_64-linux archive).
- DE routed through the central producer gate: `PROGRAMS["de/*"]` declare
  the v3 ledgers as `computed.closed` producers; `scripts/closure_gate.py`
  is the one v3 gate (frontier complete, dependency closure well-formed and
  closed, `unclassified_inputs` counted as open) for DK/NZ/tariff/DE alike;
  the unconditional DE fail-closed block in `certify.py` is retired and the
  DE census derives its closure blockers from the same gate. Verdicts
  unchanged (all three DE programs `certified: no`), blockers now measured.
- Hash cycle broken: the ledgers' `work_inventory` now binds
  `certificate_premises_sha256` over the conformant and executable verdicts
  it reads, not the whole certificate file — the certificate embeds the
  ledger's own SHA-256 as closure evidence, so whole-file binding had no
  fixpoint. Regenerating either side now converges in one pass.
- Ledger consumes committed decisions: `committed_decisions.provisions`
  (bound by citation_path + spine body_sha256), `instrument_dispositions`
  (bound by candidate id + body_sha256 for corpus rows, with the v3
  bears_on_computed_surface rule), and `leaf_classifications` (bound by
  frontier input; source-typed law_derived leaves cannot be demoted) overlay
  the generated facts in `computed`; `closed` computes true only when every
  row is dispositioned and the dependency closure is empty. Committed
  ledgers unchanged (empty decisions reproduce the all-pending join).
  Kindergeld discovery reads can now be recorded row by row
  (docs/de-kindergeld-certification.md, "Recording dispositions").
- Document layer measured: DA-KG 2025 (the retrieved `de-subject-003`
  bytes, sha-verified against the snapshot receipt) parsed with
  `pdftotext -layout` into 420 numbered headings, all 420 section bodies
  located and hashed (`scripts/parse_de_subject_documents.py`,
  `conformance/closure/de-subject-document-headings.json`). The ledger
  consumes the committed JSON hermetically; kindergeld's instrument frontier
  is now 448 candidates (28 + 420), all pending. The four unretrieved
  subject queries are 404s on preregistered URLs, not connectivity; fixing
  them is a query-set revision plus a corpus recapture, left open.
- Kindergeld reads, DA-KG 2025 Kapitel O (27 headings, 2026-09-07): all
  dispositioned in `committed_decisions.instrument_dispositions` with the
  section body hash — 26 excluded (structural headings, five
  "(weggefallen)", competence, forms, tax secrecy/data protection,
  records, IdNr control, periodic review, statistics, supervision,
  inter-agency cooperation) and O 2.4 classified as an instrument index.
  O 2.4 Abs. 2 names instruments not yet in the frontier (EStR/EStH, LStR,
  AEAO, AStBV (St), BMF letters, BZSt directives, published court
  decisions, bilateral social-security agreements, Regulations (EC)
  883/2004, 987/2009, 859/2003, Regulation (EU) 1231/2010, the EU/UK
  Withdrawal Agreement); they are recorded in the reason and need a
  `supplemental_instruments` section (as in the DK ledger) to enter as
  pending candidates — next contract change. Frontier: 421 of 448
  pending. Hermetic rederivation now takes decisions from the document
  under check (working-tree edits are checkable before commit).
- `supplemental_instruments` section landed in the ledger contract (mirrors
  DK): the 15 instruments O 2.4 Abs. 2 names are enrolled as pending rows
  bound to O 2.4's section hash (`de-kg-suppl-001`–`015`). Four are classes
  (BMF letters, BZSt directives, published court decisions, bilateral
  agreements) whose members a discovery channel must enumerate; the
  frontier cannot complete around them. Kindergeld: 463 candidates, 436
  pending.
- Kindergeld reads, DA-KG 2025 Kapitel V (148 headings, 2026-09-07): 144
  excluded as procedure / payment mechanics / recovery / payout routing;
  four classified as open bearing restatements of spine rules (V 14.3
  month principle § 66 Abs. 2; V 23.1 unrounded payout vs the module's
  whole-euro rounding rule; V 23.4 six-month payout limit § 70 Abs. 1;
  V 24.2 per-child share § 76). Those four stay open dependencies until the
  spine provisions are encoded and the rules bound to them — the first
  concrete encoder work the reads have produced. Frontier 288 of 463
  pending; 12 open dependencies. Next: Kapitel R (69) and S (64), then A
  (108, where most bearing instruments are expected).
- Kindergeld reads, DA-KG 2025 Kapitel R (69) and S (64), 2026-09-07: all
  133 excluded as appeals / court / penal procedure and penalty scales; no
  bearing rows. KiZDAV (issued under § 68 Abs. 5 EStG) and RiStBV enrolled
  as pending supplementals. Frontier 157 of 465 pending: Kapitel A (108
  headings, entitlement conditions — where bearing instruments and the
  encoder work are expected), the 28 discovered candidates (BKGG, EStG
  § 31, corpus citations, unresolved references), and 17 supplementals.
- Kindergeld reads, DA-KG 2025 Kapitel A (112 headings, 2026-09-07): 20
  excluded (structural headings, A 21 repealed, A 19.2 proof of disability);
  92 classified as open bearing rows — 28 spine restatements (§§ 62–66, 78)
  and 64 entitlement conditions from outside the spine (AO residence, § 1
  EStG, AufenthG/FreizügG, BGB kinship, foster children, the § 32 Abs. 4
  grounds for adult children including the quantified disability
  self-support test, the second-training 20-hour exclusion). Each names the
  law-derived input it decides (claimant_entitlement, qualifying_child_count,
  recipient_priority, substitute_child_benefit_exclusion). The DA-KG reads
  are complete: 465 candidates, 45 pending (28 discovered candidates, 17
  supplementals); 104 open dependencies (4 law-derived inputs, 4
  unclassified inputs, 96 bearing instruments). The open count is now the
  honest size of the encoder work: the entitlement layer (§§ 62–65, § 32
  EStG) is unencoded and every DA-KG rule on it stays open until it is.
- Spine and leaf dispositions (2026-09-08): 13 of 18 spine rows recorded —
  § 66 partially-encoded by the captured module; §§ 67–69, 71–77 excluded
  (procedure, data, payout routing, set-off, attachment, appeal costs,
  repealed); § 70 excluded as fixing/payout/correction machinery on the
  strength of Abs. 1 Satz 3. §§ 62–65 and § 78 stay pending by decision:
  they define the four law-derived inputs and can only leave the spine as
  encoded. The four unclassified § 66 inputs are typed law-derived (month
  window from §§ 62–65/§ 32; § 31/§ 32 Abs. 6 increase; increased amount).
  V 23.4 and V 24.2 re-dispositioned non-bearing to match the § 70 / § 76
  spine rows. Spine 5 pending; frontier 45 of 465; 102 open dependencies
  (8 law-derived, 0 unclassified, 94 bearing). Provision texts were
  fetched from axiom-corpus at the pinned commit and hash-verified — no
  local corpus checkout needed for spine reads.
- Discovered candidates (2026-09-08): 27 of 28 dispositioned — SteFeG
  encoded (its § 66 amounts are the module's two versions); 14 open bearing
  (EStG §§ 1, 2, 19, 31, 32, BKGG, SGB III, SGB VI, BEEG, AufenthG,
  FreizügG/EU, AO §§ 139a/139b, SGB VII § 217 Abs. 3 old, EEA Agreement),
  of which five are not in the pinned corpus release and need capture; 11
  excluded (data, procedure, recovery references; inbound WoGG/UhVorschG;
  EStG § 19a mis-resolved from SGB I); the DA-KG seed recorded as a
  container. One left pending: the 26.5.2026 EStG amending act (not in the
  corpus). Frontier 18 of 465 pending (17 supplementals + that act); 116
  open dependencies (8 law-derived, 0 unclassified, 108 bearing).
- Supplementals (2026-09-08): 13 of 17 decided on captured text — 10 open
  bearing (EStR/EStH, LStR/LStH, AEAO §§ 8/9, Regulations 883/2004,
  987/2009, 1231/2010, 859/2003, Withdrawal Agreement), 3 excluded (AStBV,
  KiZDAV, RiStBV). The four classes (BMF letters, BZSt directives, court
  decisions, bilateral agreements) stay pending until a discovery channel
  enumerates members. EUR-Lex and BMF handbook texts were captured through
  the in-app browser (bot challenges block curl) and hashed in-page; a
  corpus channel for guidance documents should replace these page
  captures. Frontier 5 of 465; 126 open dependencies (8 law-derived, 0
  unclassified, 118 bearing).
- Corpus repin (2026-09-08): closure source and instrument graph moved to
  the encoder's signed release de-rulespec-2026-09-08-kindergeld-civil (17
  scopes, 7,637 rows; July scopes byte-identical, so no binding broke).
  Capture script fixed for multi-scope releases. AO resolved to its act
  row; four handbook/CJEU inbound rows and the 2026 amending act
  dispositioned; 13 supplementals rebound to corpus rows; the bilateral
  agreements and ARB 3/80 enrolled as 23 pending members of the class.
  Toolchain now runs end to end on this host (corpus and rulespec-de
  blobless clones, release objects from the public mirror). Frontier 27 of
  492; 130 open dependencies (8 law-derived, 0 unclassified, 122 bearing).
  Next: read the 23 agreement texts; rebind AufenthG/FreizügG/EEA/SGB
  VI–VII rows once the resolver matches inflected act names.
- Agreement members (2026-09-08): the 23 enrolled rows decided on their
  corpus texts — 7 SVA + 7 Schlussprotokolle + ARB 3/80 open bearing, 7
  Durchführungsvereinbarungen + Tunisia ZP excluded. Capture gap flagged:
  the DVKA extracts omit the Kindergeld chapters; full BGBl II texts are
  needed to encode. Frontier 4 of 492 (classes only); 145 open dependencies
  (8 law-derived, 0 unclassified, 137 bearing).
- Resolver fix (2026-09-08): raw-reference hint table added to the capture
  script; AufenthG, FreizügG/EU and the EEA Agreement now bind to their
  corpus rows (UHV: AufenthG, BGB). Counts unchanged (4 of 492; 145 open).
  Remaining in-repo frontier work: none until the encoder or corpus lane
  delivers (full agreement texts, class channels).
- Remaining sprint items: single claim-surface digest bound across all four
  premises; import / root-reachable dependency-edge traversal; successful
  subject-query result capture and pagination; corpus citation scan (#611);
  program-scoped dependency attribution (the NZ #493 adjudication question,
  which kindergeld also needs to certify alone).

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
