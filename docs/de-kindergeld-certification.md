# DE Kindergeld amount-subgraph certification lane

The committed certificate computes `certified: no` under CERTIFIED.md v3.
Three premises compute true — conformant (both live Axiom pair legs),
exercised (13-household variation), executable (the signed EStG 66 module
replayed in pinned release v0.2.2) — and `closed` computes false from the
v3 discovery ledger (`conformance/closure/de-kindergeld.yaml`), consumed
through the same central gate (`scripts/closure_gate.py`) that judges every
other closure artifact. The current frontier has 316 of 842 instruments
pending, and dependency closure has 169 open dependencies: eight law-derived
inputs and 161 bearing instruments, with no unclassified inputs. The signed
BGB §§1591 and 187 prerequisites, EStG §78 record helpers, EStG §32(3) age
criterion Regulation 987/2009 Article 59 payment-continuity rules, and the MiLoV4 §1
historical minimum-wage parameter, MiLoV5 §1 future rates, historical SGB IV §8(1a)
earnings threshold, BFDG §5 recognition-preservation norms and the BGB §126(1)
documentary signature mechanism are declared at
RuleSpec merge `b1a72d0fa2fd8238708bdfc8fe5fd282a5f8e967`; the live amount-only oracle and
replay pins remain scoped to their existing §66 evidence. The §78 helpers
add five observable payment-record and filing facts; full transition priority
and same-child credit remain deferred to §64, and the §78 spine remains pending.
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

The SHA-bound class snapshot contains 229 entries. With the committed dispositions,
202 members remain pending, sixteen captured members are bearing, and eleven entries
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
`de-rulespec-2026-09-11-kindergeld-illness-precedents` release at commit
`279e27503c00ce1fab35809d069c076d3abad362`, content SHA-256
`1a8434379a899f4224e4201441fd94f2bbffb22636b73f4ab1c9d4bf3e84ea4c`
(9,894 rows, 50 scopes). The complete DA-KG 2026 edition is separately
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
uniform 2025 amount; its historical ordinal advantage expressly ended in 2023. The remaining pending members are 109 citation-only seeds and
96 receipted instruments. The 2023 country-group letter remains citation-only
as a capture matter, but the receipted 2 December 2025 replacement expressly
replaces it from assessment year 2025; that operative clause supports the
period-specific exclusion without misattributing a captured body to the old letter. The 22 DVKA documents are publisher extracts.
Enumeration and identity deduplication remain incomplete, with all four class
rows pending. Current result: 291 of 813 instruments pending, 165 open
dependencies (eight law-derived inputs, 157 bearing instruments, no unclassified
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
clearing pending rows alone cannot close the partially encoded §66 amount
and payment-period rules. The current ledger retains five pending provisions and one partial
provision; all six must be resolved before the spine can close.

EStG §32(4) native run `34403571398` exhausted its third standard attempt
without an apply signature or RuleSpec PR. It removed the earlier law-derived
caller inputs, retaining two birth-record fields, but still failed date
arithmetic, proof, precise-deferral and behavior checks. The retained candidate
uses an unsupported third `date_add_years` argument; the later candidate omits
the leap-day correction and returns 28 February instead of 1 March. Neither
candidate is declared as coverage. The subsequent instruction to continue allows
preparing the requested additional scoped attempt, but the source-coverage plan
below is not yet ready for dispatch. No budget override has been set; §32(6)
and §66 retain their separately paused attempt decisions.

## Adult-child repair review (2026-09-10)

The [source-bound § 32(4) worklist](de-kindergeld-adult-child-coverage-plan.md)
records why birth-date helpers alone cannot repair the complete source unit.
The reviewed DA-KG sections are retained in full and verified against their hashes.
A 19.2 is now an open bearing instrument: paragraph 2 limits consideration to
the period for which disability is proven, while card expiry alone does not
limit the award. This corrects the earlier whole-section evidence exclusion.
The correction exposes an unencoded rule. No new signed module or certified
claim results from this review.

Full-text review of BFH III R 37/21 (22 September 2022), paragraphs 1–22,
adds bearing dispositions for its discovery and corpus frontier rows. It also
corrects A 14.1’s former “only breach” termination summary: the child’s own
termination request and an effectively notified termination decision are
separate routes. Register deletion and ending a careers-advice appointment alone
are insufficient. The judgment’s historical SGB III wording must be distinguished
from the current guidance when encoding. These bearing dispositions remain
open encoding dependencies.

## Signed overseas-service recognition preservation (2026-09-10)

[RuleSpec PR87](https://github.com/TheAxiomFoundation/rulespec-de/pull/87) merged
at `212bba29ea06d0166037e4cc24ba4d03b4dd6c02` after all exact-head checks passed.
BFDG §5 supplies six normative preservation outputs: existing recognitions and
new-recognition powers under ZDG §14b(3), each for providers, projects and
service deployment plans. The module has zero inputs and no deferrals; every
proof atom quotes the full corpus sentence, body SHA-256
`eef6e0dc2ef478dd2b29b8869e4d8e12eb6d1f601b3b1f054eef111cd387bf5b`.
Three native companion cases exercise all six outputs in supported 2025/2026
observation periods. These norms do not decide individual recognition validity,
service qualification or child eligibility. DA-KG A18.5 remains bearing.

The protected signing run used encoder
`5d4562d822e6d4a53420f0f9cb0a5891a7edf6fe`. DE repository CI now uses that exact
identity; the initial mismatch was repaired by aligning the pin, with the policy
gate retained. Generated module, companion and manifest bytes were not edited.
The DE workstream's owned display follow-up in PR536 includes `bfdg` and `zdg`
in both canonical acronym registries, alongside `milov4` and `milov5`.

The consumer now declares ten signed modules against the same corpus release.
Native graph refresh adds four pending candidates: the BFDG amendment reference
of 23 May 2024, SGB V, ZDG and the 2021 IJFD guideline. Their identity and bearing
must be reviewed from the bound source edges; discovery alone does not establish
applicability. The SGB V §226(6) text refers to its own §5 insurance categories
and separately mentions service under BFDG. The old proximity matcher incorrectly
bound that section number to BFDG. The producer now requires connected citation
syntax for an `explicit_cross_reference_inbound` binding. Other nearby act and
section mentions remain `unresolved_cross_reference_proximity` candidates with a
`candidate_target_citation_path`, never a `resolved_citation_path`. This preserves
recall for unfamiliar citation forms without asserting their identity. The SGB V
candidate remains pending for a text-bound disposition; this correction does not
classify the whole act as non-bearing. Current totals are 291 pending of 813
instruments and 165 open dependencies (eight law-derived, 157 bearing), with
five pending and one partially encoded spine provision. Closure remains false.

For a corpus-evidence-only refresh, `refresh_de_instrument_graph.py
--subject-snapshot <prior-snapshot.json>` can retain an existing subject channel.
The producer validates the complete prior snapshot and requires identical source
and query bindings before reuse. It preserves every original capture timestamp,
success, failure and receipt; it does not describe reused evidence as a new web
capture. `--offline` cannot be combined with this option. The September 10
binding correction uses the previously committed subject receipts after a fresh
DA-KG PDF fetch timed out. All corpus evidence and dependent artifacts are still
regenerated by their native producers.
The [bound comparison](../conformance/closure/de-discovery-2026-09-08/inbound-reference-review.json)
records all 30 unresolved associations and verifies that no program loses a
candidate instrument.

The first-qualification review binds the full A 20.1–A 20.2.4 text and the complete
BFH III R 10/22 decision. III R 10/22 is bearing
through the current A 20.2.4 earliest-start rule: an intervening voluntary service
cannot replace the connection between actual training stages. The review retains
the decision’s vocational-training exception and separates the sentence-2 test
from the independent service and transition consideration grounds. Both the court
class member and its corpus identity are dispositioned as bearing.
The implementation remains open. A 20.2.4’s 26-week employment indicator is part
of an overall assessment, not an automatic threshold.

The adult-child review now binds all 50 DA-KG sections from A14 through A20
(including seven structural headings) and seven complete BFH decisions. III R19/16
supplies the statutory-training-term exception; III R40/19 distinguishes objective
online result availability and the whole-transition four-calendar-month limit.
III R58/12 preserves the maternity exception without requiring later resumed
search. III R41/19 distinguishes training termination, temporary-illness prognosis
and contemporaneous evidence of training intention. Their relevant class/corpus
identities are bearing and remain unencoded. A18.7 preserves training averaging
at least 60 hours per year. Current totals are 291 pending of 813 instruments
and 165 open dependencies (eight law-derived, 157 bearing).

The recall review records 188 matching BFH citation occurrences in the retained
DA-KG text and one missing case label: III R42/22, printed with “S.16”. Its exact
citation is enrolled; all 228 prior member payloads were preserved. This is a
recall repair, not exhaustive court enumeration or proof of BStBl II membership.
Corpus PR668 merged after all required checks passed. Publication run34491213953
signed and registered `de-rulespec-2026-09-10-kindergeld-maternity`; its signature
and all 355 artifact bytes were verified against commit
`5a77472300eb240e303a6f52c1d45040d671e7a4`. Mirror run34491742281 passed, and
a direct public fetch was byte-identical to the signed publication object. The consumer binds the new release,
which preserves all 41 prior scopes and adds 56 rows in four scopes.

The new scopes contain the complete current MuSchG, two official historical §3
versions distinguishing the 1 June2025 amendment, the complete 2025 amendment
acts I59 and I371, and the full five-page BFH III R42/22 decision. The complete
52-page I371 capture is not a claim that every article has received legal review;
this workstream reviewed its MuSchG article13 and commencement article14.
Current capture dates do not establish blanket applicability throughout2025.
III R42/22 refines substantial co-causation during psychiatric placement and
requires an individual overall assessment. It does not permit a blanket
placement exclusion or an automatic entitlement flag. These sources support
remaining implementation work, not signed encoding coverage or certification.

The recipient-priority review adds full §64/§78 and seven DA-KG sections plus
complete BFH III R3/13 and III R57/13 decisions. Their four class/corpus identities
are bearing. Court selection does not create entitlement outside §§62–63. The
maintenance decision excludes payments begun years late but leaves continuously
recurring payments delayed by weeks or months undecided. The worklist preserves
that boundary instead of inventing a universal lateness threshold. FamFG is
captured and signed in merged corpus PR669. Publication run34496812231 succeeded;
the native verifier checked the signature and all360artifact hashes against
merge commit `eb2c46117b2cf2a396a48a41be409fe1e5ecc696`. The consumer retains
that 46-scope release within the newer additive release. Historical applicability and recipient-priority encoding
remain open.

FamFG40 is explicitly enrolled as bearing `de-kg-suppl-018`, discovered in the
full hash-bound A25.1(7) read and bound to its exact corpus body. Before the genitive-title repair described below, the fresh graph
scan retained the same 111 Kindergeld identities and did not project FamFG into
that set. The separate reading-discovery mechanism prevents its omission from
hiding the dependency. This enrollment does not claim the entire FamFG has
been reviewed or encoded. The current ledger has 291 pending instruments out of 813
and 165 open dependencies: eight law-derived inputs and 157 bearing instruments.

The genitive-title recall repair adds three corpus candidates: FamFG, KiZDAV
and the separately captured EStG §32(4) document. FamFG and §32(4) are bearing
and unencoded. All nine KiZDAV row bodies match the existing supplemental016
receipt and support the same data-retrieval-only exclusion. The graph now has
114 Kindergeld identities. At that revision, its 9,862-row extraction index recorded 6,745 explicit
body references; the prior 6,741 count is retained in the recall audit. No
Kindergeld identity was removed. In the Unterhaltsvorschuss graph, the genitive
EStG title now matches the existing in-scope act alias instead of emitting a
separate unresolved identity. Current totals are 291 pending instruments out of
813 and 165 open dependencies (eight law-derived inputs and 157 bearing
instruments). The [recall review](../conformance/closure/de-discovery-2026-09-08/genitive-citation-recall-review.json)
retains the graph comparison, exact evidence and full KiZDAV texts. This fixes
a demonstrated recall gap; the four discovery classes remain open.

The EU predecessor release adds three complete original German Official Journal
texts: Regulations 2018/1475, 1288/2013 and 2021/817. Publication run34521018738
and mirror run34521605732 succeeded; native verification checked the signature
and all 366 artifact hashes, and the public object is byte-identical. That release’s
graph scanned 9,868 rows and records 6,764 explicit body references, retaining
114 Kindergeld candidates. It does not project the three predecessor instruments
into that frontier, so the recorded A18.4 source review enrolls them as bearing
supplemental019–021. The 2021/817 discovery is indirect: it supplies repeal and
continuation rules for the 1288/2013 programme named in A18.4. It is not named
in A18.4 itself.

The [transition review](../conformance/closure/de-discovery-2026-09-08/eu-service-transition-review.json)
binds eleven complete article spans and the full A18.4 section to corpus bodies.
It records the original Article13 service route, its later replacement, repeal
and continuation of initiated actions, and separate entry and application dates.
Financial transition exceptions do not automatically set Kindergeld award dates.
This is a limited article review, not a legal review of all 77 captured pages.
All three instruments remain unencoded. The generated ledger reports 291 pending
of 813 instruments and 165 open dependencies: eight law-derived inputs and 157
bearing instruments. Five spine provisions remain pending and one partially
encoded; dependency closure remains false.

The same review also enrolls four earlier instruments as pending
supplemental022–025: Regulation375/2014, named in 2021/888 Articles32–33, and
Decisions1719/2006,1720/2006 and1298/2008, named in 1288/2013 Article37.
These are indirect reading discoveries. All four complete original German
Official Journal instruments are now captured in the pinned 49-scope release.
The selected complete operative spans and exact body/excerpt hashes are retained
in `conformance/closure/de-discovery-2026-09-08/eu-earlier-service-source-review.json`.
Their historical application to 2025 Kindergeld remains pending; old dates alone
do not support exclusion. The four rows stay pending and unencoded.

### All-generations service agreement review

The complete captured BFH III R 68/11 decision (24 May 2012, paragraphs 1–24)
requires the SGB VII §2(1a) service conditions and a written agreement meeting
BGB §126(1)–(2). Its two frontier identities are bearing and unencoded.
The judgment specifies agreement contents, including liability and accident
insurance; DA-KG A18.7 mentions liability insurance. Both texts remain bound
for reconciliation. A unilateral appointment letter did not establish the
agreement in that case; the ruling does not reject a properly evidenced
agreement universally. The complete body, hashes and limitations are retained
in `conformance/closure/de-discovery-2026-09-08/generations-service-source-review.json`.
This review does not establish exact BStBl II issue membership or encode the
service conditions. The generated totals are 291 pending of 813 instruments
and 165 open dependencies (eight law-derived inputs and 157 bearing instruments).

The combined service-prerequisite release was published by run 34533390855
from merged corpus PR683, commit `4779d3deb7db854bdb6e702abc523dee8d95fb31`.
Native verification accepted the release signature and all 379 artifact hashes
and byte counts. It includes the complete SGB VII §2(1a) and BGB §126(1)–(2)
paragraphs, each matching its retained parent-section text. Capture dates are
not statutory commencement dates. The paragraph bodies are retained alongside
the decision review; no additional module is declared encoded by this repin.

Public mirror run 34533791093 succeeded; the fetched release object is
byte-identical to the verified signed publication object (SHA-256
`aa969bbf7a9aeaa434cebf568d87f7e6e04a8ee91aff117eccae08a3c07b1c09`).

The refreshed graph retains all 114 Kindergeld identities (no additions or
removals); the global index scans 9,882 rows, including 9,691 body rows and
231 act roots, and records 6,777 explicit body references. The review artifact
records the before/after graph hashes. Native generation leaves 291 pending
instruments out of 813 and 165 open dependencies: eight law-derived inputs
and 157 bearing instruments. Five spine provisions remain pending; §66 is
partially encoded and §78 remains pending. Dependency closure is false.

## Illness prognosis and annuity-capital review

The complete III R49/18, III R43/20 and III R23/22 decisions were reviewed with their complete DA-KG sections. The two illness decisions preserve the distinction between illness duration and the prognosis for each disputed month, including earlier months before a later long-term prognosis. III R23/22 distinguishes returned existing capital from annuity income and expressly leaves the savings-allowance issue open. The review artifacts retain complete source bodies, SHA-256 bindings, limitations and exact indirect citation excerpts.

Native ledger generation records four additional bearing identities and 21 newly discovered pending authorities, including contextual/comparison citations requiring their own bearing review. The generated result is 291 pending of 813 instruments and 165 open dependencies: eight law-derived inputs and 157 bearing instruments. No statutory spine provision is closed by these reviews.

The six recovered illness/training originals are now bound to published corpus release `de-rulespec-2026-09-11-kindergeld-illness-precedents`, merged in corpus PR684. Native publication 34538761714 and mirror 34539151964 succeeded. The release signature and all 388 artifact bytes match the merge commit; the public mirror matches the signed object exactly. These receipts replace indirect-source-only provenance for supplemental rows 026, 028, 030, 031, 033 and 034. At that publication step their original-source legal reviews remained pending; the later III R65/18 review is recorded below.

Fresh graph capture against the 50-scope release adds four pending Kindergeld corpus identities and one UHV identity, with no removals. These are separately discovered rows for recovered named cases; the supplemental reading discoveries remain explicit. The global index contains 9,894 rows, 9,697 body rows, 237 document roots and 6,827 explicit body references. The exact before/after hashes and added identities are retained in the illness-prognosis review artifact.

## Signed BGB §126(1) documentary signature mechanism

RuleSpec PR93 merged as `019619f0422766eab2e30b73d465c5309f0b5b47` after exact-head CI34539559771 passed. Dedicated encoder-pin PR94 resolved the initial provenance mismatch before that final validation. The three generated files remain byte-identical to native run34536457917; the rejected PR91 andPR92 candidates are closed and never counted as coverage.

The declared paragraph module derives only documentary conformance with the issuer-signature mechanism: a handwritten name signature, or an issued notarial authentication associated with the observed handmark, issuer, document and version. It does not decide statutory applicability, whole-contract validity, other writing substitutes or service eligibility. Its fourteen used inputs describe retained observations. Positive surrogate identifiers preserve observed identity, while zero represents absent/unidentified associations; this convention is technical, not a statutory numerical threshold. All14 complete companion cases and six additional pinned-engine counterexamples passed, including absent identities, mismatches, unrelated authentication and an unknown physical method. Full-paragraph proof binds body SHA-256 `28ff8e921b9384a922dbc2ed654e199ae40fc5b5226306ecb2581a8cef3dffb0`.

The source and manifest are declared in `closure/de/source.json`; `bgb1261-signature-mechanism-review.json` records the replay and observable-input bindings. SGBVII §2(1a), BGB §126(2), DA-KGA18.7 and BFHIII R68/11 remain open. This prerequisite does not close a Kindergeld spine provision or remove the eight law-derived inputs.


The complete BFH III R65/18 examination judgment is reviewed with DA-KG 2025
A15.2, A15.7 and A15.10 in `training-examination-source-review.json`. Its
supplemental and corpus-graph identities are bearing and unencoded. The decision
requires actual training efforts and distinguishes final loss of examination
rights from preparation for a possible repeat examination. It does not support
an automatic exclusion for every missed examination or a determination based
solely on formal enrolment or exmatriculation. Seven earlier cited authorities
are enrolled as pending supplemental rows 047–053; their own source review and
historical application remain open. There are now 53 supplemental instruments.


The native BGB §126(1) release refresh in RuleSpec PR97 merged as `b1a72d0fa2fd8238708bdfc8fe5fd282a5f8e967`.
Its signed source attestation now matches the published illness-precedents release.
The fourteen-input contract and executable rules, proofs and versions are identical
to PR93; the generated summary and companion fixtures changed. The original 20-case
replay still produces byte-identical responses, and all 14 current companion cases
pass. Both requests and responses are retained beside
`bgb1261-release50-refresh-review.json` in the discovery review directory.
This remains a documentary signature mechanism: it does not determine statutory
writing applicability, whole-contract validity or other writing substitutes.
The 2025 observation boundary is not statutory commencement. This refresh adds no
declared root or coverage and leaves §126(2) and the service prerequisites open.


The subsequent native §126(2) run34544226511 passed existing-import verification
but produced an unsigned, rejected candidate: every output was deferred, rules
and cases were empty, and `imports: null` failed compilation. Its reported lack
of a relational mechanism is not independently established; the pinned engine
already supports related derived judgments and current-entity predicates.
`bgb1262-release50-failure-review.json` retains the exact rejected source, artifact
hash, validation issues and limitation of that diagnosis. No §126(2) coverage is
claimed, and a cosmetic serialization repair alone would not close it.


The full five-page BFH III R24/08 judgment and current DA-KG A14.1, A14.2 and
A17.2 are retained in `historical-search-access-source-review.json`. Its two
Kindergeld identities are bearing and unencoded. The review distinguishes legal
inability to obtain work permission from merely not holding permission while
searching, and excludes automatic reuse of the historical three-month renewal,
former age27 limit and pre-2005 permit regime as current parameters. The remand
for findings on issued restrictions is not an award. ARB1/80 Articles7/9 access
was expressly left undecided. Twenty-two indirectly cited authorities enter the
pending frontier as supplemental054–075; they include historical and procedural
material requiring its own source and current-surface review. There are75
supplementals; this review adds no encoded module or closed spine provision.

Engine PR173 subsequently merged as `f19b03a6aafc9503c943510bc7946127e291784f`
after all required exact-head checks passed. It fixes the demonstrated scalar
scope discrepancy; the technical regression covers both entity scopes, duplicate
facts, a shared record, empty/mismatching groups and conditional fallback traces.
Default307 and schema322 engine tests pass, along with the release build and
Python binding check. This is a verified engine primitive, not a §126(2) encoding;
the dedicated DE pinPR98 and the next native source-bound attempt are separate.
