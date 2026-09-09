# DE Kindergeld amount-subgraph certification lane

The committed certificate computes `certified: no` under CERTIFIED.md v3.
Three premises compute true — conformant (both live Axiom pair legs),
exercised (13-household variation), executable (the signed EStG 66 module
replayed in pinned release v0.2.2) — and `closed` computes false from the
v3 discovery ledger (`conformance/closure/de-kindergeld.yaml`), consumed
through the same central gate (`scripts/closure_gate.py`) that judges every
other closure artifact. The current frontier has 278 of 770 instruments
pending, and dependency closure has 135 open dependencies: eight law-derived
inputs and 127 bearing instruments, with no unclassified inputs. The signed
BGB §§1591 and 187 prerequisites, EStG §78 record helpers, EStG §32(3) age
criterion Regulation 987/2009 Article 59 payment-continuity rules, and the MiLoV4 §1
historical minimum-wage parameter, MiLoV5 §1 future rates, and historical SGB IV §8(1a) earnings threshold are declared at RuleSpec merge
`af3e4f1c15550f8b871a1c14d0a6d1bd7c6a2a41`; the live amount-only oracle and
replay pins remain scoped to their existing §66 evidence. The §78 helpers
add five observable payment-record and filing facts; full transition priority
and same-child credit remain deferred to §64, and the §78 spine stays pending.
The exact-citation-path summary (`closure/de/summary.json`) contributes only
its source-universe and signature fields; nothing DE-specific decides the
premise, and a forged ledger fails the producer's exact rederivation before
it reaches the gate. The honest scope of
the positive evidence is narrow: one encoded output root, the EStG 66
per-child amount parameter, reproduced against two oracles across 13 cases
(22 of the 26 comparisons are zero-children zeros); household Kindergeld is
an attested external multiplication by child count. The clean historical
EUROMOD-to-GETTSIM aggregate is a source-source conservation crosscheck; it
is not per-case oracle evidence and cannot satisfy either Axiom leg.

## Landing the evidence bundle

The reviewed RuleSpec-DE pin lives in both registered leg configs:

- `comparisons/de-worker-dual-oracle-axiom-euromod.yaml`;
- `comparisons/de-worker-dual-oracle-axiom-gettsim.yaml`.

The `rulespec_upstream_sha` and `rulespec_upstream_tree` fields must move
together in a visible change. The same commit/tree is mirrored in the
executable manifest and checked for exact equality by tests. Moving
RuleSpec-DE `main` by itself does not move this lane: after EStG 66 lands, bump
the reviewed pin, regenerate the pending records, and run the live producer
below. Until then, both pair records say exactly `pending:
module-not-on-main`; that state never counts as conformance.

The signing/oracle lane produces every mutually dependent artifact in one run:

```sh
python scripts/de_executable.py --run \
  --engine-archive /path/to/axiom-rules-engine-x86_64-unknown-linux-gnu.tar.xz \
  --rulespec-root /path/to/rulespec-de \
  --signing-public-key /path/to/apply-public-key \
  --euromod-model-root /path/to/EUROMOD_RELEASES_J2.0+ \
  --euromod-python /path/to/euromod/python
```

Run this command on the provisioned x86_64 Linux oracle host: the pinned Axiom
release asset is `x86_64-unknown-linux-gnu`, and the same host must have the
EUROMOD J2.0+ model/Python environment plus the locked GETTSIM 1.2.1 extra.
For ordinary engine development, discover the local binary with
`axiom-locate engine` or use the sibling `axiom-rules-engine` checkout. The
certificate producer deliberately requires the published release archive,
because its exact SHA-256 and version output are part of the replay receipt.

This path executes EUROMOD and GETTSIM directly over the canonical thirteen
households; it has no report-reemission branch. It separately extracts the
digest-pinned released Axiom engine, verifies the EStG section 66 apply
manifest's Ed25519 signature and exact module bytes, and executes the amount
root. It then writes:

- `comparisons/de-worker-dual-oracle/axiom-euromod.json`;
- `comparisons/de-worker-dual-oracle/axiom-gettsim.json`;
- `comparisons/de-worker-dual-oracle/unified-record.json`;
- `conformance/executable/de-kindergeld-signed-rulespec.json`;
- `conformance/executable/de-kindergeld-replay-receipt.json`; and
- `conformance/executable/de-kindergeld-status.json`.

Each comparison left value is bound to the stored live-oracle execution row.
Each comparison right value is the actual Axiom amount-root output multiplied
by the canonical suite's computed child count. The historical 765 EUR sum is
checked only after those rows exist. Ordinary verification reruns the embedded
released-engine archive and fails closed on any leg, rulespec, receipt, or
cross-leg inconsistency.

Every JSON output is replaced atomically. If a host interruption lands only a
prefix of the six-file bundle, rerunning the command rebuilds the canonical
source population without trusting those replaceable files and repairs the
bundle; ordinary status regeneration remains fail-closed in the meantime.

After the bundle lands, run `scripts/commit_refreshed_report.sh` (or the same
derived regeneration/check sequence in CI). The refresh chain rederives the
unified record, executable status, DE census, and certificates; there is no
manual certificate-status edit.

## Claim labels

Stored EUROMOD/GETTSIM result rows and external engine release identities are
attested observations because ordinary refresh does not rerun those licensed
or optional engines. Their row digests and comparison verdicts are computed.
Axiom results, fresh released-binary replay, hashes, signature verification,
variation, and citation-path resolution are computed. The rulespec checkout
commit is attested metadata and is not part of the computed signature premise
because the signed v5 apply manifest does not cover it. No artifact in this
pending lane is labeled certified.

## Certified is an honest no (2026-08-20 ruling)

`closed` is false under the central completeness requirement (CERTIFIED.md
v3, per Max's 2026-08-20 ruling): a closure claim must disposition every
subordinate instrument the official registry links to the act, and a
law-derived quantity can never be a case-supplied leaf. The DE closure
declares neither block, and the certify gate for the DE path fails both
requirements unconditionally — nothing written into the rederived closure
summary can flip them; the real ledger must land through the central
producer gate.

## Verifying on a non-Linux host (oracles#498)

The receipt embeds the producing `x86_64-unknown-linux-gnu` archive, and the
manifest, receipt, and status bind that pin; none of them change with the
verifying host. A verifier on another target replays the receipt's exact
request with the sha-pinned sibling asset of the same release from
`ENGINE_PLATFORM_PINS` in `scripts/de_executable.py`, and every fresh equality
except the binary's own SHA-256 (platform-specific by construction) must still
hold: version line, compiled artifact bytes, engine stdout bytes, and all 13
result rows. The rendered status is host-invariant, so `--check` compares
byte-for-byte on macOS and Linux alike.

One-time setup on macOS or aarch64 Linux:

```sh
python scripts/de_executable.py --fetch-host-engine
```

This downloads this host's asset into `~/.cache/axiom-oracles/axiom-rules-engine/<release>/`,
refusing any bytes whose SHA-256 differs from the pin. Alternatively point
`AXIOM_RULES_ENGINE_HOST_ARCHIVE` at an already-downloaded archive; it is
verified against the same pin before it runs. Without either, the executable
status computes `computed_invalid` with a blocker naming the asset and its
expected hash — never a silent pass. Producing a new receipt (`--run`) still
requires the producing target and its archive.

## Recording dispositions in the ledger

Discovery reads land as rows under `committed_decisions` in
`conformance/closure/de-kindergeld.yaml`; `scripts/de_closure_ledger.py
--check --artifact all` validates every row against the generated fact it
binds and rederives `computed` from the join. Nothing a decision says can
create a fact; a row that binds nothing, binds the wrong text, or decides a
fact twice fails the check. The three sections:

- `provisions` — one row per spine citation: `citation_path`, the spine
  row's `body_sha256` (text binding; a corpus refresh that changes the text
  retires the decision), `status` ∈ `encoded` / `partially-encoded` /
  `classified-with-reason` / `excluded-with-reason`, `classification` +
  `reason` for classified/excluded, and `encoded_by` naming a captured
  RuleSpec module bound to that citation for encoded/partially-encoded
  (`partially-encoded` also needs a `reason` saying what remains).
- `instrument_dispositions` — one row per candidate `id` from the instrument
  graph (`de-kg-instr-*`): `status` ∈ `encoded` / `classified-with-reason` /
  `excluded-with-reason`, `classification`, `reason`, the candidate's
  `body_sha256` when it is a captured corpus row, and — for classified or
  excluded — `bears_on_computed_surface: true|false`. Per CERTIFIED.md v3 a
  bearing instrument classified around stays an open dependency; only
  `encoded` (with `encoded_by`) removes it.
- `supplemental_instruments` — instruments found by reading rather than by a
  captured discovery channel: `id` (`de-kg-suppl-NNN`), `identity` (official
  citation), `title_short`, `relation` ∈ `bears_on` / `issued_under` /
  `coordination` / `guidance`, `discovered_by` (the candidate whose text
  named it — that candidate must itself have a recorded disposition) plus
  `discovered_in_body_sha256` (that candidate's section hash), `provenance`
  (where in the read), and `status`. Rows enter `pending` and count toward
  the frontier like any candidate; deciding one later requires
  `text_source` + `text_sha256` of the captured text it was read from. A
  named class ("BMF-Schreiben") is enrolled as one pending row whose
  members a discovery channel must still enumerate — the frontier cannot
  complete around it.
- `leaf_classifications` — one row per frontier `input` the ledger lists as
  `unclassified`: `leaf_kind` ∈ `world_fact` / `law_derived`, `reason`, and
  for `law_derived` the `defining_citation_path`. Leaves already typed
  `law_derived` by `closure/de/source.json` cannot be reclassified here;
  they leave the frontier only when a RuleSpec module encodes them.

`closed` computes true only when no spine row, candidate, or leaf is
pending, every non-encoded row carries a reason, and the dependency closure
has zero law-derived leaves, zero unclassified leaves, and zero bearing
instruments. The central gate (`scripts/closure_gate.py`) re-derives that
verdict from the committed block; a hand-edited `closed: true` fails the
producer's exact rederivation before it reaches certify.

## Spine and leaf dispositions (2026-09-08)

`committed_decisions.provisions` now carries 13 of the 18 spine rows, each
bound to the pinned corpus row's `body_sha256` (texts re-fetched from
`TheAxiomFoundation/axiom-corpus` at the pinned commit and hash-verified):

- § 66 — `partially-encoded` by the captured module `de:statutes/estg/66`
  (Abs. 1 dual-version amount, Abs. 2 month window, Abs. 3 increase and
  whole-euro rounding). What remains: the entitlement tests behind Abs. 2
  and the § 31 / § 32 Abs. 6 increase behind Abs. 3 enter the module only
  as inputs.
- §§ 67, 68, 69, 71, 74, 75, 76, 77 and the repealed §§ 72, 73, 76a —
  `excluded-with-reason` (application procedure, cooperation and data
  powers, data transmission, provisional suspension, payout routing,
  set-off, attachment, appeal costs). § 70 is excluded as fixing, payout
  and correction machinery: Abs. 1 Satz 3 says in terms that the payout
  limitation of Satz 2 leaves the claim untouched, and the claim per month
  is what the module computes.
- §§ 62, 63, 64, 65 and § 78 (Abs. 5 priority exception) stay `pending`
  by decision: they define the law-derived inputs `claimant_entitlement`,
  `qualifying_child_count`, `recipient_priority`,
  `substitute_child_benefit_exclusion`, bear on the computed output, and
  under CERTIFIED.md v3 have no honest non-encoded disposition. They leave
  the spine only as `encoded`, mirroring the DK ledger, which likewise
  records only exclusions until the entitlement provisions are encoded.

`leaf_classifications` types the four previously unclassified § 66 module
inputs as `law_derived`: the first- and last-qualifying-month conditions
(defined by §§ 62–65 with § 32 EStG), the § 31 / § 32 Abs. 6 Satz 1
allowance-increase trigger (EStG § 31, discovered candidate
`de-kg-instr-003`), and the correspondingly increased amount (§ 66 Abs. 3
Satz 1). None is an observable act; all stay open.

Two Kapitel V rows were re-dispositioned to match the spine: V 23.4
(payout limitation, § 70 Abs. 1 Satz 2–3) and V 24.2 (attachment-purpose
attribution, § 76) are now non-bearing, each reason citing the spine row.
V 14.3 (month principle) and V 23.1 (unrounded payout against the module's
whole-euro rounding rule) remain open bearing rows against the
partially-encoded § 66.

Result: spine 5 pending of 18; frontier 45 of 465 pending; 102 open
dependencies (8 law-derived inputs, 0 unclassified inputs, 94 bearing
instruments).

## Discovered candidates (2026-09-08)

The 28 candidates the citation scan and subject search put on the frontier
are dispositioned in `instrument_dispositions` (ids `de-kg-instr-*`), 27
of them; every reason quotes the citing spine sentence:

- **Encoded (1)**: the Steuerfortentwicklungsgesetz (BGBl. 2024 I Nr. 449)
  — its § 66 Abs. 1 amounts (255 EUR from 2025, 259 EUR from 2026) are the
  two versions of `monthly_kindergeld_per_child` in the captured module,
  whose proof atoms cite the act.
- **Open bearing (14)**: EStG §§ 1, 2, 19, 31, 32, the BKGG, SGB III, SGB
  VI, BEEG, and the unresolved references AufenthG, FreizügG/EU,
  Abgabenordnung (§§ 139a, 139b), SGB VII (§ 217 Abs. 3 old version) and
  the EEA Agreement. Each is a term of an entitlement condition, a child
  condition, an exclusion comparator or the § 66 Abs. 3 trigger; each names
  the law-derived input it bears on. AufenthG, FreizügG/EU, AO, SGB VII and
  the EEA Agreement are not in the pinned corpus release and must be
  captured before they can be encoded.
- **Excluded (11)**: EStG § 39e, SGB I, SGB X, SGB II, SGB XII, StBerG,
  Regulation (EC) 883/2004 and Regulation (EU) 2017/492 as cited in § 68
  Abs. 6 (data purpose only — the Regulation's coordination bearing is
  carried by its supplemental row), WoGG and UhVorschG (inbound
  cross-programme references only), and EStG § 19a, which the scan
  mis-resolved from "§ 19a Absatz 2 … des Ersten Buches Sozialgesetzbuch"
  in § 68 Abs. 5.
- **Container (1)**: the DA-KG 2025 subject seed, whose bearing content is
  carried by its 420 heading rows; recorded non-bearing so the document is
  not counted twice.
- **Left pending (1)**: the `law_metadata_changed_by` string "zuletzt
  geändert durch Art. 3 G v. 26.5.2026 I Nr. 156" on the EStG act row. The
  amending act is not in the pinned corpus release; it cannot be read, so
  it cannot be dispositioned.

Result: frontier 18 of 465 pending (the 17 supplementals and that amending
act); 116 open dependencies (8 law-derived inputs, 0 unclassified inputs,
108 bearing instruments).

## Supplemental instruments (2026-09-08)

13 of the 17 supplementals are decided in `supplemental_instruments`,
each bound to captured text (`text_source` names the source and capture
method, `text_sha256` the hash):

- **Open bearing (10)**: EStR and EStH (BMF Einkommensteuer-Handbuch 2024
  pages for §§ 3, 32, 32b, 33a — R 32.2 Kostkinder presumption, R 33a.1
  cost lump sum, R 32b unused employee allowance, H 3.29 WÜD/WÜK), LStR
  and LStH (Lohnsteuer-Handbuch 2023 pages for §§ 3b, 8, 9 — the 4.35
  factor of the 20-hour test, R/H 9.2 training service relationship, R
  9.1–9.13 work expenses, H 8.1 foreign-currency conversion), AEAO (AO-
  Handbuch 2025 pages for §§ 8, 9 — the residence test the DA-KG copies),
  Regulations (EC) 883/2004 (Art. 1 z, 3, 67, 68: children abroad,
  priority, differential), 987/2009 (Art. 58–60), 1231/2010 and 859/2003
  (third-country scope), and the Withdrawal Agreement (Art. 30–32). Each
  reason quotes the captured text and names the law-derived input it
  bears on.
- **Excluded (3)**: AStBV (St) 2025 (penal procedure, AO-Handbuch 2025
  Anhang 45), KiZDAV (data retrieval under § 68 Abs. 5, read in full from
  the gesetze-im-internet PDF), RiStBV (prosecutor guidelines, Nr. 266–267
  on tax offences).
- **Still pending (4)**: the classes BMF-Schreiben, BZSt-Weisungen,
  published BFH/BVerfG/EuGH decisions, bilateral social-security
  agreements. A class cannot be decided; a discovery channel must
  enumerate its members.

The original browser capture methods remain recorded in git history. All
thirteen decided supplementals (001–006 and 011–017) now bind 32 receipted
corpus bodies from `de-rulespec-2026-09-09-kindergeld-treaty-texts`, commit
`27510ad32be7e2111c20f3a7dd41a2ae40310c17`, content SHA-256
`415ed064787982bd65ba6b5c882efd53ae6d1ba2f98f0e1fc66232a27977d69f`.
[Supplemental corpus bindings](../conformance/closure/de-discovery-2026-09-08/supplemental-corpus-bindings.json)
records each citation path, pinned JSONL path and line, row hash, body hash,
expression date and official URL. Single-body instruments use the body hash;
multi-body instruments use the SHA-256 of body hashes joined by newline in
citation-path order, without a trailing newline. Source receipt changes alone
do not change bearing or close a legal dependency.

The SHA-bound class snapshot contains 228 entries. With the committed dispositions,
210 members remain pending, seven captured members are bearing, and eleven entries
are non-bearing or structural: the transfer letter, BFH file-access decision,
misdated BFH duplicate, combined BFH citation, superseded country-group letter, BFH remission decision
BFH objection-notice decision, BFH appeal-cost decision, and BFH inter-agency
refund decision, final-rejection decision, and non-reporting limitation decision.
The transfer letter allocates parental tax allowances and a child's lump sum among
adults; it does not alter the statutory §32(6) sentence1 amount, the qualifying
child tests or §64 priority. The 2025 country-group letter remains bearing
through §1(3) EStG and its specified allowance adjustments. C-328/20 and both
parentage decisions remain bearing; their BStBl II membership is provisional.
The complete Morocco/Tunisia Kindergeld treaty publications, their commencement
notices and the 2014 civil-partner letter are now receipted. The latter remains
bearing through the EStG §2(8) spouse-equivalence bridge into §§63 and64; its
encoding is pending. Treaty applicability and encoding remain pending. The Swiss free-movement agreement (consolidated 2021) and Joint Committee
Decision 1/2012 are now receipted discovery members; their applicability and
coordination rules remain pending. The consumer now pins the additive
`de-rulespec-2026-09-09-kindergeld-threshold` release at commit
`9bc4f5f0afad97e8edc9834609a53a56435d0509`, content SHA-256
`7f3743883a536d7aca5e22e2cf58cfbc660c4cb6ce8645928104363d9f1fc162`
(9,208 rows, 41 scopes). The complete DA-KG 2026 edition is separately
receipted at `de/guidance/bzst-dakg-2026/document-1`, body SHA-256
`2e6bda7e7fa84cbf696959e70920cc0577c995b3c5aa8dfafde0feea70b3ed58`.
Its applicability remains pending; it does not replace the retained 2025 edition. The additive service captures cover JFDG, BFDG,
EhfG, ZDG, SG, WPflG and SGB VII, the European Solidarity Corps regulation,
the statutorily referenced weltwärts guideline, and the IJFD guideline.
A separate official archived SG §58b row preserves the wording applicable
through 2025; its service duration differs from the current consolidation.
The SGB VII discovery reference now resolves to the complete act; its historic
§217(3) comparator remains bearing and unencoded. The earlier supplemental receipts remain valid
and retain their original release identities. Eight article-level EU coordination
captures supplement the complete regulation bodies without creating eight new
instrument identities. DA-KG A30 is now bound to the signed §66 module for its
uniform 2025 amount; its historical ordinal advantage expressly ended in 2023. The remaining pending members are 108 citation-only seeds and
102 receipted instruments. The 2023 country-group letter remains citation-only
as a capture matter, but the receipted 2 December 2025 replacement expressly
replaces it from assessment year 2025; that operative clause supports the
period-specific exclusion without misattributing a captured body to the old letter. The 22 DVKA documents are publisher extracts.
Enumeration and identity deduplication remain incomplete, with all four class
rows pending. Current result: 278 of 770 instruments pending, 135 open
dependencies (eight law-derived inputs, 127 bearing instruments, no unclassified
inputs). Dependency closure remains false.

The latest release also retains complete EStG §32 paragraph captures and the
complete official BGBl. 2026 I No. 198 act. The latter’s Article 2 commences on
1 July 2027. Its raw BGB amendment reference is explicitly dispositioned from
that body for the 2025 scope; the conservative automatic resolver still retains
the raw identity because optional document-date metadata is absent. The captured
BGBl. 2026 I No. 156 retirement reform is likewise excluded only for 2025 after
reading its EStG amendments, transitions and commencement provisions.

The BFH recovery contains 81 complete official PDFs (338 pages). Eighty existing
single-case discovery rows now bind those texts; two individual case rows were
added for the compound III R 10/11 / III R 63/11 citation. The compound seed is dispositioned as a container; both individual decisions remain
pending. The conflicting III R 21/12 seed date remains visible:
the court records 8 May 2014, while one seed says 8 November 2014. Neither case
bearing nor exact BStBl issue/page verification is inferred from capture alone.

The new §32(3) module derives birth-month and age-at-month-start conditions from
two birth-register facts. Article 59 derives calendar continuity from identified
coordination and original-payment records; successor payment is not a prerequisite
for its takeover duty. Its date helpers are consumed only with the applicable
original-payer or successor predicate. Nineteen new record facts are classified.
Full §32/§63 child qualification, national eligibility, priority, EU scope and
benefit differentials remain open; DA-KG A8 stays bearing because its adult-child
and disability provisions are not covered by the age criterion.

## Reads log

- 2026-09-07 — DA-KG 2025 Kapitel O (Organisation), 27 headings: 26
  excluded with text-grounded reasons, O 2.4 classified as an instrument
  index whose cited instruments await enrolment as supplemental candidates.
  Rows: `committed_decisions.instrument_dispositions` in
  `conformance/closure/de-kindergeld.yaml`, ids `de-kg-dakg-O*`.
- 2026-09-07 — O 2.4 Abs. 2 enrolment: 15 supplemental instruments
  (`de-kg-suppl-001`–`015`, all pending, bound to O 2.4's section hash):
  EStR, EStH, LStR, LStH, AEAO, AStBV (St); the classes BMF-Schreiben,
  BZSt-Weisungen, published BFH/BVerfG/EuGH decisions, bilateral
  social-security agreements; Regulations (EC) 883/2004, 987/2009,
  859/2003, Regulation (EU) 1231/2010, and the EU/UK Withdrawal Agreement.
  Frontier 463 candidates, 436 pending.
- 2026-09-07 — DA-KG 2025 Kapitel V (Verfahren), 148 headings: 144 excluded
  (structural headings, five "(weggefallen)", competence, procedure —
  participation, application, fact-finding, cooperation duties, notices,
  provisional and reserved fixings, limitation, the §§ 129–175 AO and § 70
  Abs. 2/3 EStG correction rules — payment mechanics, recovery and
  enforcement — deferral, remission, allocation, set-off under § 75, payment
  limitation, interest, surcharges, reminders, enforcement, write-off,
  liability — and payout routing — attachment, assignment, diversion under
  § 74 Abs. 1, refunds under § 74 Abs. 2, claimant change, forwarding).
  Four headings bear on the computed surface and are classified as OPEN
  bearing restatements of spine provisions (`bears_on_computed_surface:
  true`, counted as open dependencies): V 14.3 (month principle of § 66
  Abs. 2 EStG), V 23.1 (fixed amount is paid unrounded — to reconcile with
  the captured module's `kindergeld_before_whole_euro_rounding` rule),
  V 23.4 (six-month payout limit of § 70 Abs. 1 Satz 2–3 EStG), V 24.2
  (per-child share of the household total, § 76 EStG). Frontier 463
  candidates, 288 pending; 12 open dependencies.
- 2026-09-07 — DA-KG 2025 Kapitel R (Rechtsbehelfsverfahren), 69 headings:
  all excluded — the appeals register, the extra-judicial appeal
  (admissibility, periods, restoration, suspension of enforcement, stay,
  joinder, withdrawal, relief, appeal decision and its parts, costs under
  § 77 EStG) and the fiscal-court procedure (types of action, admissibility,
  course, ending, costs, process interest). R 6.4 Abs. 3 governs the temporal
  reach of a rejected revocation, not the monthly amount. No bearing rows.
- 2026-09-07 — DA-KG 2025 Kapitel S (Steuerstraftaten und
  -ordnungswidrigkeiten), 64 headings: all excluded — competence, the
  offences and their elements, intent / recklessness / guilt, attempt,
  limitation, grounds for investigation, self-disclosure, procedure,
  sentencing and fine scales (the per-month-and-child daily-rate guide and
  the EUR 600 / 1,500 / 5,000 / 25,000 thresholds size penalties and
  prosecution discretion, not the Kindergeld amount), registers. S 12's
  section text carries the document's appendices after the last heading.
  Two supplemental enrolments from these reads: KiZDAV (`de-kg-suppl-016`,
  issued under § 68 Abs. 5 EStG, from O 4.5) and RiStBV (`de-kg-suppl-017`,
  from S 1.2). Frontier 465 candidates, 157 pending (all in Kapitel A plus
  the 28 discovered candidates and 17 supplementals); 12 open dependencies.
- 2026-09-07 — DA-KG 2025 Kapitel A (Anspruchsvoraussetzungen), 112
  headings: 20 excluded (18 structural headings, A 21 "(weggefallen)", and
  A 19.2, which prescribes how a disability is proven and that
  consideration tracks the proven period) and 92 classified as OPEN bearing
  rows. The captured § 66 module takes four law-derived inputs —
  `claimant_entitlement`, `qualifying_child_count`, `recipient_priority`,
  `substitute_child_benefit_exclusion` — and every Kapitel A heading that
  states a condition of law deciding one of them bears on the computed
  output through that input: 28 `spine_restatement` rows (§ 62 Abs. 1, 1a,
  2 claimant conditions and IdNr; § 63 Abs. 1 child categories,
  identification and territorial condition; § 64 priority; § 65 exclusions
  and the EU differential; § 66 Abs. 1 amount table and ordinal rule in
  A 30; § 66 Abs. 2 month principle in A 20.4 and A 31; § 78 Abs. 5) and 64
  `entitlement_condition` rows (§§ 8, 9 AO residence and the treaty
  fictions; § 1 Abs. 2, 3 EStG; AufenthG, FreizügG/EU and treaty-state
  workers; §§ 1591, 1592, 1755, 1772 BGB kinship; foster-child conditions;
  the § 32 Abs. 4 grounds for adult children — job-seeking, training in all
  its forms with begin/end/interruption rules, transition period, lack of a
  place, the seven voluntary services, disability with the quantified
  self-support test of A 19.4–19.6 (Grundfreibetrag, additional need,
  disposable net income, third-party benefits) — and the § 32 Abs. 4 Satz 2
  and 3 second-training exclusion with the 20-hour rule). Each row names
  the input it bears on and stays open until §§ 62–65 / § 32 EStG are
  encoded and the rule bound. Frontier 465 candidates, 45 pending (the 28
  discovered candidates and 17 supplementals); 104 open dependencies
  (4 law-derived inputs, 4 unclassified inputs, 96 bearing instruments).

## Closing worklist (seed enumeration — discovery incomplete)

Stable IDs; each row is a node of the open frontier, not an engineering
unit. This is a SEED list: the instrument-discovery sprint (registry graph +
subject search + citation scan) will extend it, and rows only ever move to
dispositioned/encoded — they are never deleted. Reference implementation:
the dk ledger (`conformance/closure/dk-boerne-og-ungeydelse.yaml`, schema
v3) and `scripts/refresh_instrument_graph.py`.

Instrument frontier (`de-kg-instr-*`):

- `de-kg-instr-001` DA-KG (BZSt Dienstanweisung zum Kindergeld, 2025
  edition, 173 pp / 420 numbered headings) — bears directly on computed
  surfaces; requires per-heading disposition rows with body-hash binding,
  encode-vs-classify split per the bearing test. MEASURED 2026-09-07: the
  retrieved document (`de-subject-003`, byte-bound by the snapshot receipt)
  is parsed by `scripts/parse_de_subject_documents.py` into
  `conformance/closure/de-subject-document-headings.json` — 420 headings,
  420 section bodies located — and each heading enters the kindergeld
  frontier as a pending `document_heading` candidate (`de-kg-dakg-<code>`)
  whose `body_sha256` is the section text a disposition must cite.
- `de-kg-instr-002` BKGG (Bundeskindergeldgesetz) — alternative/interacting
  scheme; must be dispositioned as such, not left an unnamed boundary.
- `de-kg-instr-003` EStG §31 (Familienleistungsausgleich) — the
  Günstigerprüfung interplay with §32(6) allowances.
- `de-kg-instr-004` EStG §§67–78 spine-denominator decision — application,
  award changes, payment restrictions. Whether the certified spine is
  §§62–66 only or §§62–78 must be preregistered BEFORE discovery runs.
- `de-kg-instr-005` registry/search/citation discovery receipts — the
  sha-bound snapshot of the official link graph plus mandatory
  subject-search and citation-scan channels (frontier rows enter as pending
  until dispositioned).

Law-derived leaves to encode (`de-kg-leaf-*`; all currently case-supplied
boundary inputs, classification `open-law-derived-dependency` in
`closure/de/source.json`):

- `de-kg-leaf-001` `claimant_entitlement` (EStG §62) — pulls EStG §1 tax
  status, residence/ordinary abode (AO §§8–9), immigration-permit classes,
  EU free-movement status.
- `de-kg-leaf-002` `qualifying_child_count` (EStG §63 → §32) — parentage,
  age tiers, education/training status, unemployment registration,
  voluntary service, disability, self-support; the deepest subgraph
  (DA-KG devotes ~70 headings here).
- `de-kg-leaf-003` `recipient_priority` (EStG §64) — household membership,
  maintenance payments, written designation, family-court acts.
- `de-kg-leaf-004` `substitute_child_benefit_exclusion` (EStG §65) —
  foreign/comparable benefits, EU and treaty coordination.

Each leaf closes only when its defining rules are encoded down to
observable-act leaves (dates, register entries, issued assessments,
judgments). Working both lists to completion — then rerunning the closure,
census, and certify chain through the central gate — is the path back to a
certified claim. No certified claim is announced anywhere without Max's
explicit clear.

The historical SGB VII §217(3) capture expressly refers to RVO §§583,
584(1) sentence 2, 585, 579(1) sentence 2 and 609(3) immediately before
1 January 1997. Subject query `de-subject-016` enrolls that dependency as
`de-kg-instr-rvo-1996` and binds the archived §217 body digest. The current
official RVO index confirms the instrument identity, but marks those sections
repealed; it does not supply their historical text. Historical capture and
encoding remain pending.

Direct retrieval of the BZSt endpoint in `de-subject-002` now returns
DA-KG Stand 2026 despite its legacy filename. `de-subject-017` binds that
173-page PDF digest and enrolls `de-kg-instr-dakg-2026` separately. Its
application to non-final cases has explicit temporal restrictions; applicability
to the 2025 program remains pending. The retained 2025 heading evidence is
not replaced by the new edition.


The minimum-wage tranche adds complete official MiLoG and MiLoV5 sources and
the DRV archive of SGB IV §8 effective from 1 March 2024 through 31 December
2025 (`de/statute/sgb-4/fassung-2024-03-01/8/inhalt`). The archived body
preserves the three-month/70-workday short-term-employment limit applicable
in 2025. MiLoV5 supplies dated 2026 and 2027 rates; MiLoV4 remains the
2025 rate source. The historical SGB IV §8(1a) threshold calculation is signed; the remaining
§8 employment classification and composition into EStG §32(4) stay pending.

The MiLoV5 prerequisite starts in 2026 and has no 2025 version. Its declaration preserves explicit source accounting for the 2026/2027 wage schedule; the 2025 certificate retains the separately captured MiLoV4 prerequisite. Neither wage module establishes marginal-employment eligibility or child qualification.

The threshold release adds a complete, independently captured historical SGB IV §8(1a) paragraph from the unchanged official DRV HTML. All 40 preceding scopes remain. The new paragraph now binds the ninth signed declared module. It imports the signed MiLoV4 hourly wage and computes the monthly threshold as the ceiling of that wage multiplied by 130 and divided by three: EUR 538 from March 2024 and EUR 556 during 2025. It has no inputs or deferrals and no formula outside March 2024–December 2025. The declared import is resolved from hash-verified module bytes; this prerequisite does not establish marginal-employment classification or child qualification.

The complete BFH decision III R 59/19 (3 November 2020) is dispositioned as non-bearing after review of all sixteen paragraphs. It concerns discretionary file access and litigation costs, consistent with the existing DA-KG V9 procedural exclusion; it does not determine a child entitlement or amount. Its exact corpus-body hash is recorded in the committed decision. This individual disposition does not resolve the separate BStBl II publication verification or exhaustive class-discovery requirement.

The misdated III R 21/12 seed and the correctly dated 8 May 2014 seed bind the same
complete official body. The former is recorded as a duplicate; the correctly dated
member remains pending. The combined III R 10/11 / III R 63/11 citation is a
container for the two separately captured decisions, whose individual rows remain
pending. These structural dispositions neither close their legal interpretations
nor establish BStBl II issue/page membership.

Declaring the historical threshold also enrolls its previously unlisted raw reference to the Mindestlohngesetz as `de-kg-instr-dde9fcbc9faae4c7`. The act is captured, but this raw identity still requires source-bound resolution and disposition. The frontier therefore has 278 pending instruments out of 770; adding a signed prerequisite does not suppress newly discovered references.

The complete captured BFH III R19/17 decision of 13 September 2018 concerns
discretionary remission of an established recovery under AO §227, including
reporting and interagency information. Its discovery member and corpus parent
identity receive the same procedural disposition. BFH III R26/22 of 17 August
2023 concerns objection timeliness and the adequacy of the notice of remedies
under AO §§355–357. Neither decision defines an additional entitlement, child
qualification, priority or benefit-amount rule; both dispositions cite the full
receipted text and its body hash. Exact BStBl II membership and exhaustive
class enumeration remain pending.

The full BFH III R18/21 decision (1 September 2021), paragraphs 1–21,
limits EStG §77 cost reimbursement after objections concerning evasion interest.
BFH III R36/21 (19 January 2023), paragraphs 1–37, determines inter-agency
refund procedure and timely-payment/prior-knowledge limits under EStG §74(2)
and SGB X §104, taking the underlying Kindergeld award as given. Its receipt
and agency-knowledge rules remain on the refund surface already excluded by
the §74 spine and DA-KG V34.1. Both complete texts support non-bearing
dispositions of their discovery and corpus parent identities; this does not
exclude a new entitlement or amount surface. Reasons bind the exact corpus
body hashes and preserve outstanding BStBl II enumeration verification.

The certificate distinguishes declared-source resolution from full-spine
disposition: `declared_sources_closed` reports resolution of the declared
module subset, while `spine_closed` is derived from the validated provision
ledger. Kindergeld therefore has `declared_sources_closed: true` and
`spine_closed: false` with five pending provisions. Source resolution cannot
substitute for the governing-act denominator or change the overall closure gate.

Full-text review of BFH III R71/10 (4 August 2011), paragraphs 1–16,
dispositions its final-rejection and objection-decision binding rules on the
existing §70 administrative-fixing surface. BFH III R21/13 (26 June 2014),
paragraphs 1–18, concerns suspension of assessment limitation and completion
of an offence caused by failure to report loss of eligibility. Its residence
facts are established lower-court findings; it defines no new AO §§8–9 test.
Both decisions restate the §66 monthly principle while distinguishing their
procedural questions. Their exact corpus bodies support the discovery and
parent-row dispositions; the monthly-condition dependency remains open.

Full-text review of BFH III R73/09 (9 February 2012), paragraphs 1–23, retains
its maintenance-payment treatment as a bearing dependency. Although the case
concerns the former annual income ceiling, DA-KG 2025 A19.5 sentence 3
expressly uses it in the disabled child's disposable-income calculation.
The discovery and corpus-parent identities are classified as bearing and
remain unencoded; neither the historical ceiling nor the former age limit
is imported into the 2025 computation.

The companion BFH III R72/07 decision (7 April 2011), paragraphs 1–18,
is likewise bearing through DA-KG A19.5: maintenance paid to the child's
spouse does not reduce available income. The disposition preserves this
open computation without importing the judgment's historical marriage
exclusion, age limit or annual income ceiling into current eligibility.

Spine closure requires both zero pending provisions and zero partially encoded
provisions. The producer and certificate projection both enforce this rule:
clearing pending rows alone cannot close the still-partial §78 transition
helpers. The current ledger retains five pending provisions and one partial
provision; all six must be resolved before the spine can close.

EStG §32(4) native run `34403571398` exhausted its third standard attempt
without an apply signature or RuleSpec PR. It removed the earlier law-derived
caller inputs, retaining two birth-record fields, but still failed date
arithmetic, proof, precise-deferral and behavior checks. The retained candidate
uses an unsupported third `date_add_years` argument; the later candidate omits
the leap-day correction and returns 28 February instead of 1 March. Neither
candidate is declared as coverage. An additional scoped-attempt decision is
pending; §32(6) and §66 retain their separately paused attempt decisions.
