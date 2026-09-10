# DE Kindergeld amount-subgraph certification lane

The committed certificate computes `certified: no` under CERTIFIED.md v3.
Three premises compute true — conformant (both live Axiom pair legs),
exercised (13-household variation), executable (the signed EStG 66 module
replayed in pinned release v0.2.2) — and `closed` computes false from the
all-pending v3 discovery ledger (`conformance/closure/de-kindergeld.yaml`,
#503), consumed through the same central gate (`scripts/closure_gate.py`)
that judges every other closure artifact: the instrument frontier has 28 of
28 candidates pending (oracles#491) and the dependency closure has 8 open
dependencies — 4 law-derived and 4 unclassified leaves (CERTIFIED.md v3).
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

## Standing decisions (2026-09-04)

Recorded by Pavel Makarchuk against the #502 decision list; both were
preregistered choices the measured-discovery sprint left open for an owner.

1. **Spine denominator: EStG §§62–78 inclusive, confirmed.** The ledger's
   `spine_scope` (`conformance/closure/de-kindergeld.yaml`, ordinals 62–78,
   18 spine rows) is the certified spine. The narrower §§62–66 branch is
   retired and would need a new, narrower program name to reopen. No
   discovery reads had begun, so the preregistration ordering in
   `de-kg-instr-004` holds.
2. **Candidate: de/kindergeld, chosen with a recorded strategic-demo
   premium.** On the #503 measured denominators kindergeld loses on cost
   (18 spine rows / 28 candidate instruments / 4 law-derived leaves versus
   3 / 11 / 0 for rv-employee-contribution and 12 / 21 / 0 for
   unterhaltsvorschuss). It is chosen anyway because it is the program with
   live dual-oracle legs, a signed executable module, and the public
   Kindergeld demo surface; the premium is the difference between those
   denominators and is accepted knowingly, per step 3 of #502.

Neither decision touches `committed_decisions` in the ledger, which the
hermetic checker requires to stay empty until dispositions begin. The
bearing-vs-classify calls on DA-KG headings and the BKGG / EStG §31
interplay remain open and need native reading.

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

Capture method: EUR-Lex and the BMF handbook sites sit behind bot
challenges, so the texts were read through the in-app browser and hashed
in-page (`innerText` for EUR-Lex and the AStBV page; whitespace-collapsed
`textContent` for handbook pages, whose R/H sections are collapsed in the
rendered view). Multi-page instruments bind the SHA-256 of their page
hashes joined by newline in the listed order. These are page captures,
not corpus rows; a corpus channel for guidance documents would replace
them with receipted bytes.

Result: frontier 5 of 465 pending; 126 open dependencies (8 law-derived
inputs, 0 unclassified inputs, 118 bearing instruments).

## Corpus repin to the kindergeld-civil release (2026-09-08)

`closure/de/source.json` now pins the signed corpus release
`de-rulespec-2026-09-08-kindergeld-civil` (axiom-corpus commit
`15402878eed59a0ab56e7428fe6caa052b5c098a`, content sha
`3a9fd00b…`, 17 scopes, 7,637 rows). The two July scopes are byte-identical
in the new release, so every spine row, every DA-KG heading and every
existing disposition kept its binding; the review pin in
`scripts/de_closure.py` moved with the source. The release object is read
from the corpus checkout's `releases/<name>/<content_sha>.json` cache,
fetched from the public mirror
(`https://pub-a8952f8657fc49fda358146ac001366c.r2.dev/releases/…`) and
verified against its content hash before use.

What the new scopes changed in the Kindergeld frontier:

- `scripts/refresh_de_instrument_graph.py` now pairs each provisions file
  with the inventory of its own scope (it used to keep one inventory per
  document class), so a multi-scope release captures correctly.
- The unresolved "Abgabenordnung" reference resolved to the captured act
  row `de/statute/ao-1977` (its §§ 8, 9, 139a, 139b are captured too); the
  row is dispositioned as a bearing entitlement condition in place of the
  retired unresolved row.
- Four inbound citations of the spine entered as candidates: the
  Einkommensteuer-Handbuch 2024 pages for §§ 32 and 33a, the
  Lohnsteuer-Handbuch 2023 page for § 9 (all bearing guidance, the
  channel-discovered identities of pages the supplemental rows already
  bind), and the CJEU judgment C-411/20 (bearing: its operative part
  disapplies § 62 Abs. 1a Sätze 1–2 for economically inactive EU citizens
  in the first three months).
- The 2026 amending act "Art. 3 G v. 26.5.2026 I Nr. 156" is captured
  (Altersvorsorgereformgesetz) and excluded: it amends §§ 82 ff. EStG and
  other acts, never §§ 62–78.
- The 13 supplementals decided on page captures are rebound to the corpus
  rows of the same texts (`text_source` names the rows; multi-row bindings
  hash the joined body hashes).
- The class "bilateral social-security agreements" is now enumerated by
  the corpus scope `2026-09-08-de-kindergeld-bilateral`: the 22 DVKA
  reprints (SVA, Schlussprotokoll and Durchführungsvereinbarung for Bosnia
  and Herzegovina, Kosovo, Morocco, Montenegro, Serbia, Türkiye and
  Tunisia, plus Tunisia's Zusatzprotokoll) and ARB 3/80 are enrolled as
  `de-kg-suppl-018`–`040`, pending until read. The class row itself stays
  pending until every member is decided.
- AufenthG, FreizügG/EU and the EEA Agreement now resolve to their captured
  rows through the capture script's raw-reference hint table
  (`_RAW_REFERENCE_CORPUS_HINTS`, shared by the global index and the
  program projection): the EStG text cites the inflected short titles
  ("Aufenthaltsgesetzes", "Freizügigkeitsgesetzes/EU"), which the rows'
  title metadata never carries, so alias matching cannot reach them. Their
  dispositions moved to the corpus-bound candidate ids; UHV's AufenthG and
  BGB references resolved the same way. SGB VI § 270 and SGB VII § 217 are
  captured only as historical single-section rows and stay referenced from
  the § 65 comparator dispositions rather than resolved as acts.

The executable contract (`conformance/executable/de-kindergeld-manifest.json`)
still binds the July release: the signed § 66 module's source hash is the
same row in both releases, and the contract is re-attested only by the
signing lane.

Result: spine 5 pending of 18; frontier 27 of 492 pending (4 classes and
23 enrolled members); 130 open dependencies (8 law-derived inputs, 0
unclassified inputs, 122 bearing instruments).

## Bilateral agreements and ARB 3/80 (2026-09-08)

The 23 members enrolled from the corpus scopes are decided on the corpus
rows themselves (`de-kg-suppl-018`–`040`, each bound to its
`…/document-1` body hash):

- **Open bearing (15)**: the seven Sozialversicherungsabkommen (the
  Yugoslavia agreement of 1968 as applied to Bosnia and Herzegovina,
  Kosovo, Montenegro and Serbia; Morocco 1981; Türkiye 1964; Tunisia 1984),
  their seven Schlussprotokolle, and ARB 3/80. The captured extracts carry
  each agreement's material scope (the Yugoslavia and Türkiye extracts name
  "das Kindergeld für Arbeitnehmer"), personal scope, equal-treatment and
  export clauses and the employment-state rule; the DA-KG applies them in
  A 4.5 (treaty-state workers exempt from § 62 Abs. 2), A 23.2 Abs. 2
  (children resident in the treaty state) and A 31 Abs. 2 (agreement
  rates). ARB 3/80 brings family benefits within its scope (Art. 4 Abs. 1
  Buchst. h) and applies Regulation 1408/71's family-benefit rules
  (Art. 18–19).
- **Excluded (8)**: the seven Durchführungsvereinbarungen and Tunisia's
  Zusatzprotokoll — liaison bodies, information duties, payment routing,
  judicial cooperation.
- **Capture gap, recorded in every bearing reason**: the corpus rows are
  the DVKA "Auszüge" for health-insurance liaison; none carries the
  agreement's Kindergeld chapter, and the Morocco and Tunisia extracts are
  lossy at the scope list. Encoding needs the full BGBl II texts.

Result: frontier 4 of 492 pending (the four classes only); 145 open
dependencies (8 law-derived inputs, 0 unclassified inputs, 137 bearing
instruments).

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
  award changes, payment restrictions. DECIDED 2026-09-04: the certified
  spine is §§62–78 inclusive (see "Standing decisions" above); §§67–78 rows
  stay in the frontier as pending spine provisions to disposition, not as an
  open scope question.
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
