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
That object was the first source-manifest repin; the expanded pin is recorded below. Snapshot member capture-state
labels describe the original discovery time, before signing and publication;
they are not current release verification results. No new signed RuleSpec
module has been accepted on main; draft #46 now carries a signed candidate
with unresolved review findings. Module declarations and legal dispositions
are not promoted merely because a source became available.

The expanded tranche in axiom-corpus PR #648 passed all required checks and
merged as `15402878eed59a0ab56e7428fe6caa052b5c098a`. Publication run
34250312875 produced `de-rulespec-2026-09-08-kindergeld-civil`, content SHA
`3a9fd00b3e189d9158e221b45251b1e30b4ee29d33c68ede0d1eb974206cce35`,
selector SHA `76600c66ac8b9b6c5740ca8fb300a975b717879f6751a4f6d2e061ce84258940`.
Its signature verifies against the trusted public key. Mirror run 34250674219
succeeded, and the anonymous public object is byte-identical to the signed
publication receipt. It preserves all
fourteen frontier scopes and adds full BGB/Unification Treaty, the German
C-411/20 judgment, and all eight previously missing BMF handbook pages:
7,637 rows in seventeen scopes. The three new scopes have signed ingest
manifests; the signature guard and deep release dry-run pass. The handbook
scope has sixteen rows with explicit ISO capture expression dates; 119
focused adapter/release-quality tests pass.

The source manifest now binds this expanded release. Supplemental entries
001–006 and 011–017 bind 32 corpus rows through
`supplemental-corpus-bindings.json`, replacing their earlier page captures.
The thirteen entries retain their existing bearing and legal dispositions.
No new executable RuleSpec module has been accepted. The release did not
activate or change a serving pointer.

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

## Signed encoding gate

No new module has been accepted on main. Protected DE run
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

After the expanded corpus pin merged in rulespec-de PR #45 as
`18b23afe7079ee142bb05faa8183d7e5b26c81b8`, protected run
[34252049347](https://github.com/TheAxiomFoundation/axiom-encode/actions/runs/34252049347)
used the source's literal `Dezember` as a String month parameter. That removed
the numeric-month grounding failure, but the candidate's deferrals still
failed validation and the signer again reported zero signatures. It also
reintroduced an irrelevant parameter for a cross-referenced paragraph number.

A read-only diagnostic isolated a validator issue: the source-bound dependency
matcher rejects both the actual `1Abweichend von § 64 Absatz 2 und 3` clause
and the clause making §64 applicable from the application month. Draft
[axiom-encode PR #1588](https://github.com/TheAxiomFoundation/axiom-encode/pull/1588)
adds bounded recognition of those forms, with ten positive/negative regression
cases passing and independent review requested. It does not validate the
unimplemented residence/qualification conditions or make the rejected
candidate complete. The review cycle, CI and a dedicated gated validator-pin
update must precede any use of changed validation semantics in RuleSpec.

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

### Civil-release frontier dispositions

Four new candidate rows are now text-bound dispositions. The empty document
containers for EStH 2024 §§32/33a and LStH 2023 §9 point to their sole corpus
text children and the existing open supplemental rows. The C-411/20 judgment
is a bearing entitlement interpretation, bound to its complete German text;
its first-three-month non-application rule retains the habitual-residence
scope in paragraphs 70–72 and remains unencoded.

The regenerated Kindergeld ledger has 206 pending instruments out of 670,
five pending spine provisions, and 127 open dependencies (eight law-derived
leaves and 119 bearing instruments). The extra bearing row makes the court
judgment explicit; it is not encoded progress. Closure remains false.

Validation: 109 ledger/parser tests pass, two skip; live corpus/RuleSpec
re-derivation and certificate checks pass. Computed blocks and all affected
certificate bindings were regenerated by their producers.

The corrected §64 generation was protected run
[34255549641](https://github.com/TheAxiomFoundation/axiom-encode/actions/runs/34255549641),
using the civil release and RuleSpec main pin from PR #45. It corrects the
prior formula's requirement for joint designation before sole-parent priority
in a shared parent/grandparent household, and requires effective waiver and
multiple-recipient cases to be handled separately. The run produced zero signatures. Its final candidate has `rules: []` and
source-unit/branch deferrals for claimant entitlement, family relationships,
legitimate interest and same-child recipient selection. The source-unit
deferral failed validation on every model attempt. Several sentence addresses
were also written as numeric subparagraphs rather than `satz-N`. No candidate
was applied or declared encoded.

The generated claim that a unique-Person/maximum selector is unavailable is
not an independently established engine limitation: recipient priority could
be represented by candidate-specific judgments if the relation grammar
supports the required comparisons. Do not relax deferral validation or rerun
the same prompt to turn this empty module into encoding progress. Upstream
entitlement/relationship outputs and a verified same-child relation design
are still required.

### Verified relation comparison capability

The isolated [runtime probe](runtime-probe/README.md) builds engine commit
`05eac9d2f89dabe5c6673176260762cef3a58f47` and executes candidate-linked
higher/equal payment counts in both explain and fast modes. All 28 numeric
assertions pass; a removed payment input fails explicitly. Child-scoped
comparison pairs keep an unrelated child's much larger payment out of the
count. This supplies a tested alternative to a maximum-and-identity selector,
without asserting a complete §64 rule or closing any legal dependency.
The retained JSON is synthetic engine IR, not manually authored RuleSpec.

### Signed maternal-relationship candidate awaiting repair

Protected run
[34257259104](https://github.com/TheAxiomFoundation/axiom-encode/actions/runs/34257259104)
succeeded with one signature and opened draft
[rulespec-de PR #46](https://github.com/TheAxiomFoundation/rulespec-de/pull/46).
The signature establishes provenance, not legal completeness. Review found an
unsupported effective date of year 0001, a potentially incorrect current-sex
input, and missing evidence that a childbirth fact persists after the event.
The four isolated tests also do not establish that one shared dataset can
represent a mother with multiple children without candidate/child collisions.
The candidate is not merged or declared as an encoded source.

[axiom-corpus PR #650](https://github.com/TheAxiomFoundation/axiom-corpus/pull/650)
adds the original KindRG, EGBGB and SBGG in 537 rows. KindRG Article 17 §1
provides the 1 July 1998 commencement. The original PDF is retained; its
machine-readable body is OCR, with the operative maternity sentence and
commencement visually checked. EGBGB Article 224 §1 concerns historical
paternity and does not justify excluding all pre-July-1998 maternity.
SBGG §11 makes the sex-register entry irrelevant to BGB §1591; a current
register-sex gate must not defeat the childbirth-based relationship.
The parentage capture passed local preflight with zero warnings, 167 focused
tests, the signed-ingest guard and all required CI. PR #650 merged as
`bd481e0973df6286349bbbee53ef899b063beb05`. Publication run 34261313166
and mirror run 34261816427 succeeded. The signed release
`de-rulespec-2026-09-08-kindergeld-parentage` contains 8,174 rows in 19 scopes,
preserving all 17 civil scopes, with content SHA-256
`98ee18f6d9eb5241112fe386aa545d042002ecb8310689ed39cf14df32f669c0`.
Its signature and content address verify, and the anonymous mirror is
byte-identical. Dedicated rulespec-de PR #47 passed all checks and merged as
`c734e76183b478a628d7736679fb1c7b1e61d7ea`. Fresh protected generation
34262819783 uses that pin and the signed parentage corpus. The oracle source manifest now binds this release.

The workflow's `repair_run_id` accepts only failed runs, so the successful
signed run cannot be used as a failed-run replay. A fresh supervised generation
must address commencement, persistent birth records, the SBGG rule and shared
candidate/child composition. No handwritten RuleSpec repair is permitted. The additional retained
[parentage pair probe](runtime-probe/parentage-pairs/README.md) confirms
identifier comparisons for two candidates and two children in one shared
dataset: all eight assertions pass across explain and fast modes. This is
synthetic runtime IR, not a legal encoding or companion-test proof.

### V 23.1 rounding reconciliation

The retained DA-KG 2025 section `de-kg-dakg-V23.1` has body SHA-256
`a05f55831bb8bc106689f9faf23c14230a143ccf5f2d9d3cf5b55153b2ae1fe7`
and heading SHA-256
`fa1b2d49432e94b3953965134e9de9e7d2338191766700d92bcf496d9c3f2df8`,
as recorded in `de-subject-document-headings.json`. Paragraph 1 sentence 3
states: “Das festgesetzte Kindergeld ist ungerundet auszuzahlen.”

The pinned §66 module at rulespec-de commit `d83ba3d` binds corpus body
`2ac3c9ff2d11aa23e6850d0a8e81abd612034582a571c036627c8b689293871e`.
Its §66(3) proof says “Das Kindergeld ist dabei auf volle Euro kaufmännisch
zu runden.” The preceding sentence ties “dabei” to an increase following
higher child allowances. This is rounding while calculating the increased
statutory amount; V 23.1 addresses payment of the amount already assessed.
The provisions therefore concern successive stages, not incompatible
rounding directions for the same stage.

`kindergeld_before_whole_euro_rounding` is an intermediate §66(3) amount,
not the amount already assessed for payout. The existing
`kindergeld_after_child_allowance_increase` rounds that intermediate amount.
Its no-increase branch returns the integer base amount, so the rounding is
an identity operation there. The 2025 base is EUR 255 and the 2026 base is
EUR 259; the existing increase/rounding rules start in 2026. This observation
does not supply their two unencoded allowance inputs or prove historical
applicability of the full increase mechanism.

The supervised §66/EU composition must preserve three boundaries: compute
and round a §66(3) statutory increase at that stage; compute any coordinated
differential under its own governing rules; pay the assessed amount without
introducing another whole-euro rounding operation. In particular, do not
route an already assessed fractional differential back through
`kindergeld_after_child_allowance_increase`. Acceptance cases must cover the
two annual base amounts, both sides of the statutory half-euro boundary,
and preservation of cents in an assessed payout. Synthetic fractional
examples test the payment boundary, not a claimed legal entitlement amount.

V 23.1 remains an open bearing row until the signed composed implementation
and its tests establish these boundaries. The narrow executable base-amount
root is not grounds for excluding this row from the full dependency graph.

Parentage repin validation: 111 ledger/parser tests pass with the isolated
corpus configured, including both live-corpus tests previously skipped by
the default local checkout setup. All three live ledger checks, source
summary freshness, certificate freshness and focused Ruff pass. The
forged-spine mutation retains committed decisions so its expected failure
is specifically the source-hash mismatch. Closure counts remain unchanged.
