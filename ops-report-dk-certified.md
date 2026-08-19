# dk/boerne-og-ungeydelse: the registry's first certified=yes

Status: **CERTIFIED=YES at rulespec-dk `9a9469edbbc4` — all four premises
computed true, blockers=[], 10 provisions encoded / 1 classified / 13
excluded with text-grounded reasons / 0 pending, boundary frontier complete
(90 grounded inputs: 65 captured, 25 uncaptured external boundaries).**

## Certification scope

`certified=yes` certifies that, for benefit year 2025, Denmark excluding the
Faroe Islands and Greenland, and the exact pinned corpus, RuleSpec, engine,
manifests, and receipts: every provision in the declared LBK 603/2025 spine
is either faithfully encoded for its documented entity/input contract or
explicitly classified or excluded with a text-grounded reason; every formula
input is either derivable or case-supplied under a documented contract, or
explicitly declared as an external boundary; the pinned executable artifact
reproduces all 10 committed Axiom cases with exact JSON numeric equality;
and the three comparison suites are conformant in the project's
explained-mismatch sense.

It does **not** claim: raw numerical parity (suite results are 7/8, 0/1,
0/1, with dispositioned mismatches of DKK 313,33 / 60 / 880); exhaustive
household or input coverage; independent correctness or availability of the
25 external judicial, municipal, agency, tax, register, and payment-history
feeds; net cash after § 11 setoff; any § 4 entity/routing surface (classified
`entity_not_supported`); effects under other benefit schemes; application in
the Faroe Islands or Greenland; or post-2025 law, including LOV 303/2026's
§ 4 e changes and the new § 4 f.

## The four premises and their producers

- **conformant (computed true)** — three provenance-pinned EUROMOD J2.0+
  reference legs (DK_2025 single, DK_2023 witness year, DK_2025 couple),
  migrated to the strict execution-evidence contract: bound chunk corpus,
  report-bound v1 index, full per-case reconciliation.
- **exercised (computed true)** — three strict-declared bridge manifests,
  validated clean; typed suite-bound covered_by evidence
  (`{report|chunk_index|chunk, claim}`); the census binds each manifest's
  sha and the strict opt-in, so no evidence edit is invisible downstream.
- **closed (computed true)** — the closure ledger derives the 24-paragraf
  spine from corpus release `a2e71391` (body sha256 per row) and maps every
  row: §§ 1, 1a, 2, 3, 4a, 4b, 4c, 4e, 5, 8a encoded by direct signed
  modules; § 4 classified `entity_not_supported`; §§ 4d, 6, 6a, 7, 8, 8b, 9,
  10, 11, 12, 13, 14, 15 excluded with text-grounded reasons; 0 pending;
  boundary frontier complete with 90 committed grounding decisions.
- **executable (computed true)** — the pinned engine (binary sha256
  `079c26f4…`) recompiles both composed programs at the recorded rulespec
  commit and reproduces all 10 certified values; `--check` recompiles and
  replays from the validated chunk corpus; the receipt binds the reports'
  provenance commit and the ledger's commit (certify blocks on any
  producer-commit disagreement).

## Gate history

The `certified=yes` claim survived two launch-grade adversarial audit
rounds plus two scoped deltas after the certificate first computed yes.
Substantive blockers found and fixed (each by a signed CI re-encode):

1. § 8 a had been excluded as administrative — gerrymandered: it governs
   the legally required income source for the § 1 a reduction (provisional
   per the latest forskudsopgørelse; final exclusively per the
   årsopgørelse) and mandates reconciliation. Now encoded, including the
   stk. 1, 5. pkt. rule that a subsequent årsopgørelse change reconciles
   against the previously settled final amount, stage-gated from the
   initial settlement so the two stages never both fire.
2. § 2's partial-entitlement route consumed residence months with no
   defined holder aggregation. The contract now fixes the maximum accrual
   among the child's maintenance-duty holders, consistent with stk. 1,
   nr. 7's »mindst en af de personer«, with the existential wording as the
   proof excerpt.
3. § 3 claimed nonexistent module outputs; its inputs are now documented
   case-supplied composite condition facts, with the ledger's grounding
   rows saying exactly that.
4. § 4 c redirected payment without checking that repayment had occurred;
   the stk. 3 redirect is now gated on the repayment-occurred fact, with a
   companion case pinning judgment-without-repayment → no redirect.

Grounding corrections from the same rounds: passport-decision reversal
covers administrative omgørelse and judicial annulment; the § 4 c offence
list is enumerated exactly (no §§ 114 c–j abbreviation); §§ 4a/4b
attribution; both barnets lov placement branches; § 4 routing facts
documented as case-supplied against a classified surface; § 8 b's register
exception stated in the correct direction; the offset-capacity input
documented as a DKK amount.

The § 8 a companion test took two further signed re-encodes to reach its
final form: the first preserved module semantics but regenerated the test
as a degenerate per-output scaffold (every formula exercised only at zero,
Boolean fixtures for DKK inputs); the second — a finding stating all
fifteen formulas and all seven cases as explicit requirements — produced
the exact target suite: both forecast cases, the initial-settlement
offset/collection case asserting the subsequent stage inert, and both
signed-delta amended-assessment directions, with every capacity fixture a
DKK amount. Suite values were identical at every pin along the way.

## Strict evidence contract (unchanged from the certified-arc landing)

`--strict` enforces findings on manifests that declare `strict: true`; the
census counts a lane as `bridge_audited` only when it declares the opt-in
AND validates clean. Findings on non-strict manifests are visible audit
debt: co-snap-populace's four genuine findings print on every run and keep
its row unaudited without redding CI — that lane's own burndown.

## Historical record

The WS1–WS3 build narrative (the first decidable certificate, honest
`certified=no` at 2 encoded / 12 pending, and its audit rounds) lives in
the git history of this file and in the ops mirror under
`ops/dk-lane/certified/` and `ops/dk-lane/wave2/` (briefs, audit reports,
and run logs for every round).
