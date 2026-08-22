# dk/boerne-og-ungeydelse: certification status

Status: **CERTIFIED=NO under definition v3 (CERTIFIED.md) — 81 open
dependencies, instrument frontier complete at fifty instruments.**
Certified requires
full dependency closure: every quantity a legal instrument defines how to
compute must be encoded, with only observable acts (dates, register
entries, issued assessments, judgments, decisions) as leaves. The dk
ledger declares 55 law-derived leaves (BEK 1563/2013's optjening
construction; personskatteloven §§ 7, 14, 20; pensionsbeskatningsloven;
kildeskatteloven § 1; straffeloven § 81 a and the § 4 c offence-list
membership; folkeskoleloven and BEK 1063/2019; the Ankestyrelsen B-1-96 /
B-1-08 tests behind the § 2 condition facts; and the act's own §§ 1-5
cadence, flow, and composite rules currently wired as case-supplied
inputs) and 26 bearing instruments. The launch audit's official-source
search found current precedents OUTSIDE the act's ELI graph (B-1-96,
B-1-08, BEK 1063/2019, B-1-97, B-5-98, B-9-96, B-5-07), and the
2026-08-22 citation scan over a complete national mirror of
retsinformation.dk (axiom-corpus#611 channel 2) found fifteen more —
the Nordic social-security convention among them — demonstrating that
the registry's link graph alone under-discovers and that the two
channels are complementary in both directions. All fifty instruments
are read and dispositioned (34 classified / 16 excluded / 0 pending);
BEK 1563/2013, BEK 1063/2019 and their amendments are in corpus
(axiom-corpus#612) so the encoding worklist can cite them. The other
premises hold: spine closed, input frontier typed and complete, receipt
10/10 exact, suites conformant with zero unexplained. What remains
between this program and certified is encoding, all enumerated in the
certificate's closed verdict.

## Certification scope

What the four premises establish today (and what `certified=yes` would
certify once the dependency worklist is encoded): for benefit year 2025,
Denmark excluding the
Faroe Islands and Greenland, and the exact pinned corpus, RuleSpec, engine,
manifests, and receipts: every provision in the declared LBK 603/2025 spine
is either faithfully encoded for its documented entity/input contract or
explicitly classified or excluded with a text-grounded reason; every
instrument the official registry links to the act (its ELI `basis_for` and
`changed_by` edges — regulations, circulars, guidance letters, appeals
precedents, amendment acts — plus search-discovered supplements) is
tracked and either dispositioned with a text-grounded reason or explicitly
pending its read (today: none pending — all fifty read, including the
fifteen the 2026-08-22 citation scan surfaced); every formula
input is either derivable or case-supplied under a documented contract, or
explicitly declared as an external boundary; the pinned executable artifact
reproduces all 10 committed Axiom cases with exact JSON numeric equality;
and the three comparison suites are conformant in the project's
explained-mismatch sense.

It does **not** claim: raw numerical parity (suite results are 7/8, 0/1,
0/1, with dispositioned mismatches of DKK 313,33 / 60 / 880); exhaustive
household or input coverage; independent correctness or availability of the
25 external judicial, municipal, agency, tax, register, and payment-history
feeds; instruments the registry links to the act after 2026-08-19 (the
committed instrument-graph snapshot date — the graph refreshes by rerun of
`scripts/refresh_instrument_graph.py`); the upstream derivation of
case-supplied inputs that BEK 1563/2013 governs (30-day residence
aggregation, 39/80-hour employment thresholds — dispositioned as an
input-derivation rule, not encoded); entitlement for persons covered by a
bilateral social-security convention (BEK 1563 §§ 16-18 waive the tax and
residence conditions and § 18 bars entitlement for other-state coverage —
neither expressible through the encoded § 2 inputs); collectibility of
§ 8 a residue amounts after the child's death (BEK 1563 § 23 bars
collection of final-regulation debt on death — the encoded residue outputs
are pre-collection arithmetic with no death guard, parallel to the § 11
setoff non-claim); net cash after § 11 setoff; any § 4 entity/routing surface (classified
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
- **closed (computed FALSE — open dependencies)** — the spine, input
  frontier, and instrument frontier are complete, but the typed leaves
  declare 55 law-derived inputs and 26 bearing instruments as open
  encoding work — so the premise computes false with the worklist
  enumerated in `computed.dependency_closure`. The completed
  layers: the closure ledger derives the 24-paragraf
  spine from corpus release `dc646ea3` (body sha256 per row) and maps every
  row: §§ 1, 1a, 2, 3, 4a, 4b, 4c, 4e, 5, 8a encoded by direct signed
  modules; § 4 classified `entity_not_supported`; §§ 4d, 6, 6a, 7, 8, 8b, 9,
  10, 11, 12, 13, 14, 15 excluded with text-grounded reasons; 0 pending;
  boundary frontier complete with 90 committed grounding decisions. The
  ledger also derives the **subordinate-instrument frontier** (oracles#491)
  from a committed snapshot of the act's official ELI graph: all 25
  `basis_for` instruments, both `changed_by` amendment acts, and
  twenty-three search-discovered supplements (eight from the launch audit's
  official-source search, fifteen from the 2026-08-22 citation scan), all
  read and dispositioned — BEK 1563/2013 and
  principafgørelse 64-13 classified as input-derivation rules for the § 2
  case-supplied inputs (cited in the grounding rows), the Ankestyrelsen
  ligedeling line (11-23, 18-24, 4-25) classified against the non-claimed
  § 4 routing surface, the setoff practice line against the § 11 non-claim,
  three bilateral-convention guidances as coordination instruments, LOV
  1642 classified amendment_act_partially_encoded (nr. 1's divisor change
  encoded via the two-version § 1 parameter; nrs. 2-11 commence 2026 under
  the post-2025 non-claim), and the rest excluded as not-in-force,
  superseded-regime, or out-of-period with text-grounded reasons. Certify
  enforces both layers registry-wide: `closed=false` for any closure
  artifact without a complete instrument frontier, and under v3 for any
  ledger with unencoded law-derived leaves or bearing instruments.
- **executable (computed true)** — the pinned engine (binary sha256
  `079c26f4…`) recompiles both composed programs at the recorded rulespec
  commit and reproduces all 10 certified values; `--check` recompiles and
  replays from the validated chunk corpus; the receipt binds the reports'
  provenance commit and the ledger's commit (certify blocks on any
  producer-commit disagreement).

## Gate history

The `certified=yes` claim survived two launch-grade adversarial audit
rounds plus five scoped closing deltas after the certificate first
computed yes; the final delta closed with every ledger row resolved (SHIP,
sol-yes-delta7).
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

After the main landing, a completeness probe found the closed premise
spine-relative only: nothing dispositioned the instruments issued under the
act. The certified claim was withdrawn from circulation pending the fix
(oracles#491). The official ELI graph turned out to enumerate the candidate
set machine-readably (`basis_for`: 25 instruments; `changed_by`: 2), among
them an in-force bekendtgørelse operationalizing § 2's accrual inputs and
an in-period Ankestyrelsen principmeddelelse on the § 4 split surface —
both invisible to the previous predicate. All 28 rows (including one
search-discovered supplement) were read and dispositioned, the ledger
schema moved to v2 with the frontier as a `closed` conjunct, and certify
now refuses `closed=true` from any closure artifact without a complete
instrument frontier — registry-wide, so a statute-only closure can never
again certify. `certified=yes` was then re-derived under the strengthened
predicate. The strengthening itself landed on main first as a dedicated
change (PR#494, sol-audited): between that landing and this one, main
honestly read `certified=no` with the missing-frontier requirement named —
the flag fell because the definition strengthened, never by hand-editing
an artifact.

The second discovery channel mandated by CERTIFIED.md — an
old-fashioned text search independent of the official link graph —
ran on 2026-08-22 over a complete national mirror of
retsinformation.dk (198,572 ELI documents inventoried; 144,087 XML
manifestations scanned; axiom-corpus#611 channel 2). Two token passes
(`ungeydelse`, and `familieydelse` for the benefit's pre-2010 name and
the EU family-benefits coordination vocabulary) hit 715 documents. The
channels proved complementary in both directions, exactly as the
frontier design predicted: the scan found 28 of the 35 then-tracked
frontier rows but could never find BEK 1063/2019 (regulates absence
registration without naming the benefit) or the six 1990s
principafgørelser (drafted under the predecessor name), while the link
graph had never surfaced the scan's discoveries. After triage of the
hit set by in-force status and surface relevance (the bulk are
downstream consumers — programs that disregard the benefit in their own
means tests — recorded in the ops scan artifact, not the ledger),
fifteen in-force instruments entered the frontier, were read the same
day (three from the rendered official page, their XML manifestations
being metadata-only shells), and were dispositioned: the Nordic
social-security convention and its 2025 administrative-agreement
amendment (Lovtidende C — treaty instruments invisible to the act's ELI
graph; article 3(3) confines family-benefit coordination to Nordic
citizens and bars third-country nationals from aggregating Nordic
periods toward the karenstid), the Brexit withdrawal-agreement
implementation order, and three EU-priority precedents, all as
coordination instruments; Ankestyrelsen principmeddelelse 11-21 on
stopping the benefit for unlawful school absence (the serviceloven
§ 155 c stop-decision fact behind § 2, stk. 1, nr. 10), B-4-06, B-2-07
and 31-09 as input-derivation rules for the § 2 residence, custody, and
skattepligt facts; B-7-95 on the non-claimed § 4 routing surface; and
five exclusions (BEK 297/2026 on Familieretshuset's § 44 b
nine-of-fourteen-days declarations, which commences 25 February 2026 —
after the certified benefit year — a 2003 notification-form circular
amending CIR 148, a børnetilskud-act precedent, and two Landsskatteret
decisions on the non-claimed § 11 setoff). Ten of the fifteen bear on
the computed surface, so the dependency worklist grows from 71 to 81
open items; the frontier is complete again at fifty instruments. Scan artifacts (hit lists with
sha256s, scanned-set ledger, summary) and the read notes live in
`ops/dk-lane/national-mirror/citation-scan*/` and
`ops/dk-lane/wave2/scan-reads/` in the ops mirror.

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
