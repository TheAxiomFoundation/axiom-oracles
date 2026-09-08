# Kindergeld class discovery seeds

This snapshot adds 201 pending candidate entries to the closure frontier:
11 BMF letters, 2 BZSt instructions, 165 court citations, and 23 bilateral
or association instruments. A court citation entry is not necessarily a
unique case: spelling variants and duplicate legal identities still require
reconciliation. These counts do not establish complete enumeration.

The DA-KG text was extracted with `pdftotext -layout` from the exact PDF
already receipted as `de-subject-003` in `de-instrument-graph.json` (PDF SHA
`33e1a8c4f6bd65034febc9d0c45850e64e982f665f519f08eaeceb80ac02dedd`).
Whitespace-normalized citation excerpts identify each seed. The retained
DVKA official bilateral index identifies the 22 linked instruments; DA-KG
also explicitly identifies Association Council Decision 3/80.

`snapshot.json` binds the retained discovery source files by SHA-256 and
contains a canonical-JSON receipt over all fields except `receipt_sha256`
(UTF-8, sorted keys, compact separators, no ASCII escaping). The ledger
producer verifies every source hash and every whitespace-normalized
excerpt, rejects duplicates and missing snapshots, and adds pending rows.
Discovery-source hashes are deliberately not operative-body hashes.

The corpus capture tranche in axiom-corpus PR #647 was signed, merged and
published as `de-rulespec-2026-09-08-kindergeld-frontier` from commit
`c3623fe4bfea336be6b990a947f69e270d8bf951`, with content SHA
`39ddd6b5090e25f8eb8822c4492e5e2c18d4a5f077fd0ca481feed5e67391a9a`.
Publication run 34239272192 and mirror run 34239946209 succeeded. The public
object is byte-identical to the locally signature-verified publication receipt.
The source manifest is repinned to that object. Snapshot member capture-state
labels describe the original discovery time, before signing and publication;
they are not current release verification results. No new signed RuleSpec
modules exist yet, so module declarations and legal dispositions are not
promoted merely because a source became available.

The next corpus tranche is in draft axiom-corpus PR #648 at
`273fcedd7ac44036feeb215717b41b22a9f4dd9c`. Its unpublished selector
`de-rulespec-2026-09-08-kindergeld-civil` preserves the fourteen published
scopes and adds three: full BGB/Unification Treaty, the German C-411/20
judgment, and all eight previously missing BMF handbook pages. The planned
release has 7,637 rows in seventeen scopes. All three new scopes have signed
ingest manifests; the signature guard and deep release dry-run pass. The
handbook scope has sixteen rows with explicit ISO capture expression dates;
119 focused adapter/release-quality tests pass. Publication, signature and
public-mirror verification must precede repinning this consumer. This ledger
still binds the earlier published release, and no handbook page-capture hash
has yet been replaced using the unpublished tranche.

Remaining work: exhaust the official BMF/BZSt registers; verify individual
case identities and BStBl II publication against official records; reconcile
duplicate identities; capture operative texts; disposition each member and
encode every bearing rule. The four class rows remain pending. No complete
discovery or certified claim is made.

Regeneration (with the corpus and RuleSpec checkouts supplied as needed):

```
python scripts/de_closure_ledger.py --generate --artifact de/kindergeld
python scripts/de_certificate_census.py
python scripts/certify.py
```

## V 23.1 reconciliation still requiring an implementation

The receipted DA-KG section says, “Das festgesetzte Kindergeld ist ungerundet
auszuzahlen.” That addresses payment of an amount already fixed. The signed
§66 module's `kindergeld_before_whole_euro_rounding` instead feeds the
§66(3) child-allowance-increase calculation. The statutory proof for rounding
says “Das Kindergeld ist dabei auf volle Euro kaufmännisch zu runden.”

These are different stages. The integration must constrain whole-euro
rounding to that statutory increase calculation and pass an issued fixing's
amount through payment without a second rounding step. In particular, the
EU differential output must not acquire whole-euro rounding merely by being
routed through a generic payment rule. The existing fixed €255/€259 cases
alone cannot demonstrate this distinction, because rounding already-integral
amounts is numerically inert. The V23.1 row stays bearing and open until the
assessment/payment boundary and any fractional amount cases are implemented
and verified from the applicable sources. No disposition is changed here.

## Signed encoding gate

No new module has been applied. Protected DE run
[34235202346](https://github.com/TheAxiomFoundation/axiom-encode/actions/runs/34235202346)
compiled a §64 candidate but failed the parent/grandparent priority test:
`household_recipient_priority` expected `holds`, returned `not_holds`.
The formula required a designation/court act even for that test's parental
priority branch. Its inputs also did not distinguish a sole parent from
multiple competing parents, so changing the expected result alone would not
resolve the source-defined priority semantics. The candidate retained
unresolved maintenance-priority, entitlement, child-qualification and §78(5)
composition dependencies. Its claimed runtime limitations require verification
against the engine; they are not established by generated prose.

The signer reported zero signatures. Earlier run
[34232900768](https://github.com/TheAxiomFoundation/axiom-encode/actions/runs/34232900768)
failed proof validation, and replacement-only repair dispatch
[34234316564](https://github.com/TheAxiomFoundation/axiom-encode/actions/runs/34234316564)
was inapplicable to a new module. These rejected artifacts must not be treated
as encoded dependencies or manually applied to bypass the signed workflow.
Next encoding work needs source-grounded, child-scoped household/claimant
relations and the missing upstream modules, followed by signed regeneration
and successful proof and behavior checks.

### Residence encoding attempts after the release pin merged

The dedicated corpus-pin PR `rulespec-de#44` passed all repository checks and
merged as `2d74a6126d10c3038106e09d9f15b61453f298cb`. The following protected
runs resolved the published September release but produced zero signatures:

- [AO §8, run 34242110828](https://github.com/TheAxiomFoundation/axiom-encode/actions/runs/34242110828):
  the initial full-unit deferral failed the exact-dependency check. The later
  candidate used a `Judgment` input with string values `holds`, `not_holds`
  and `undetermined`; the pinned formula lowering treats a bare input as a
  scalar comparison against Boolean true, and execution failed with “left
  side of comparison is not numeric”. It also used annual periods and an
  unsupported year-0001 effective date. The legal inference about retaining
  and using a dwelling remains unimplemented; registration alone cannot
  replace it. A type-only repair would not close that legal dependency.
- [AO §9, run 34242115184](https://github.com/TheAxiomFoundation/axiom-encode/actions/runs/34242115184):
  the candidate supplied the six-month and one-year parameters, but its
  sentence-1 deferral failed the exact-dependency check. It deferred calendar
  duration arithmetic and the classifications of temporary stays, short
  interruptions and similar private purposes, and duplicated several deferred
  outputs. No executable habitual-abode test was accepted. The pinned
  `src/formula.rs` exposes `days_between` and `date_add_days`; it does not
  expose calendar-month/year addition. That observation does not establish
  that every exact alternative representation is impossible. Fixed 180/183-day
  or 365-day replacements would not implement the statutory calendar periods.

Neither failed candidate was applied or declared as an encoded source.
Further work must implement the source-bound residence judgments and exact
calendar boundaries, with valid monthly tests and temporal provenance; merely
renaming those judgments as observable inputs would leave the frontier open.

### Section 78 transition attempts

Protected runs [34244951490](https://github.com/TheAxiomFoundation/axiom-encode/actions/runs/34244951490)
and [34246359794](https://github.com/TheAxiomFoundation/axiom-encode/actions/runs/34246359794)
produced zero signatures. Read-only diagnostics established that the source
structure recognizer already omits repealed paragraphs 1–4, and that the
dependency-reason matcher recognizes `de/statute/estg/78(5)(satz-1)` whereas
the German display citation alone does not satisfy that matcher. Those are
validator observations, not findings that the legal dependencies are closed.

The corrected run compiled but rejected the numeric month `12` as ungrounded
against the source's word “Dezember”. A repair then attached the unrelated
income-tax excerpt “bis 12 096 Euro” to the month parameter. That is not a
valid justification for December and must not be accepted even if a numeric
matcher could be made to pass. The rejected candidate also duplicated the
sentence-1 deferral and left `payment_was_made_under_sentence_1` as a legal
conclusion input. These semantic issues survive any calendar-literal fix.

Further implementation must distinguish the December 1990 payment reference
month from disbursement date, use receipt by the competent office for the
application-month cutoff, derive sentence-1 status from the residence,
territory and continuing-child conditions, and credit the relevant same-child
payments. No failed candidate is declared as an encoded source.

### Captured amendment identity

The raw EStG changed-by reference formerly identified by
`de-kg-instr-8939b62ab3b44a39` now resolves to
`de-kg-instr-38f449529edd140f`, corpus path
`de/statute/bgbl-2026-i-156/altersvorsorgereformgesetz/document-1`, body SHA-256
`17a83adf2b9427f081a9d3a2761212e2c010b776124146ed5bbcae180746af28`.
The producer requires agreement of the numbered BGBl citation, document date
and a unique PDF body; it preserves the original metadata reference in the
discovery evidence. The row remains pending for legal disposition. Article 14
stages commencement: Article 3 is effective 1 January 2028; Articles 1 and 2
have different commencement dates. Reading Article 3 alone cannot justify
excluding the entire amending act or its indirect income effects. The capture
is now available for that review, replacing the unreadable-source obstacle.
