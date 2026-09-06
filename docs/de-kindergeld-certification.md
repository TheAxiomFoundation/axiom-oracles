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

## Closing worklist (seed enumeration — discovery incomplete)

Stable IDs; each row is a node of the open frontier, not an engineering
unit. This is a SEED list: the instrument-discovery sprint (registry graph +
subject search + citation scan) will extend it, and rows only ever move to
dispositioned/encoded — they are never deleted. Reference implementation:
the dk ledger (`conformance/closure/dk-boerne-og-ungeydelse.yaml`, schema
v3) and `scripts/refresh_instrument_graph.py`.

Instrument frontier (`de-kg-instr-*`):

- `de-kg-instr-001` DA-KG (BZSt Dienstanweisung zum Kindergeld, 2025
  edition, ~173 pp / ~419 numbered headings) — bears directly on computed
  surfaces; requires per-heading disposition rows with body-hash binding,
  encode-vs-classify split per the bearing test.
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
