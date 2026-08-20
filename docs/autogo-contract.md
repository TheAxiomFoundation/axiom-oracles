# Autogo node-certification contract

This document describes the interface implemented by
`scripts/certify_nodes.py` on current `main`. It replaces the pre-producer
contract that originally accompanied PR #427.

The generator is deliberately useful while every candidate is red. A refused
candidate is a computed result and is written to the public validation queue;
it is not a generator crash. Producer drift, malformed artifacts, unknown
programs, or output drift are errors.

## Predicate

An explicit candidate must first be an exact node in one and only one
registered program graph. Program-level evidence may be projected onto it only
after that membership check succeeds.

```text
certified(node) =
    exact_program_subgraph_member(node)
    AND computed(provision_rooted(node))
    AND computed(conformant(program(node)))
    AND computed(exercised(program(node)))
    AND computed(closed(program(node)))
    AND computed(executable(program(node), required_tier(node)))
```

All five criteria must hold. Attested claims, prose, a passing status string,
or a receipt whose producer was not invoked by the program certificate never
satisfy a criterion.

## Candidate surface

Current main did not land a generic node-candidate producer or node index.
`conformance/node-candidates.yaml` is therefore a small, explicit adapter. It
selects only exact public/executable output nodes and names the membership
artifact and required executable tier for each program.

| Program | Candidate | Exact membership evidence |
| --- | --- | --- |
| `dk/boerne-og-ungeydelse` | `dk:statutes/composed/boerne-og-ungeydelse-pipeline#single_recipient_annual_child_youth_benefit` | Rule in the DK closure ledger and exact output in the source-reproduction receipt |
| `dk/boerne-og-ungeydelse` | `dk:statutes/composed/boerne-og-ungeydelse-couple-pipeline#couple_recipient_annual_child_youth_benefit` | Rule in the DK closure ledger and exact output in the source-reproduction receipt |
| `us-co/snap` | `us-co:regulations/10-ccr-2506-1/4.207.2#snap_allotment` | Unique `derived[].id` in the committed CO compiled program |
| `us-co/snap` | `us:statutes/7/2014/e/6/A#snap_net_income` | Unique `derived[].id` in the committed CO compiled program |
| `us-co/snap` | `us-co:policies/cdhs/snap/fy-2026-benefit-calculation#snap_eligible` | Unique `derived[].id` in the committed CO compiled program |

The CO ECPS report concepts
`us:statutes/7/2014/u#snap_benefit` and
`us:statutes/7/2014/o#snap_eligible` are comparison aliases. They are not exact
nodes in the committed compiled program and are not silently promoted. The CO
wrapper output named `snap_benefit` has no legal ID in that artifact, so it
cannot be a node candidate until its producer emits one.

Adding or changing candidates changes the candidate adapter, not the evidence
gate. The generator rejects duplicates, malformed legal IDs, unknown programs,
unsupported adapters, and missing exact membership.

## Real producer bindings

### Program registry and certificates

`scripts/certify.py:PROGRAMS` is the authority for program ownership and the
producer artifacts attached to each program. `certify_nodes` imports that
module, runs `build_certificate()` for each selected program, and requires the
result to equal the committed `certificates/<program>.json` document exactly.

This reuses the strict evidence implementation rather than copying its rules:

- `axiom_oracles/evidence.py` validates report binding, chunk indexes, case
  evidence, and reconciliation;
- `conformance/exercise-census.json` supplies the audited exercise rows;
- the named closure and executable producer validators are invoked by
  `scripts/certify.py`; and
- stale or hand-edited program certificates stop generation.

`conformant` and `exercised` are accepted only when their recomputed certificate
verdict has `mode: computed` and `value: true`.

### Closure

Closure uses the strongest real computed interface available for each program.

- DK consumes the producer-validated
  `conformance/closure/dk-boerne-og-ungeydelse.yaml` verdict already carried by
  its recomputed certificate.
- CO invokes `scripts/closure_universe.py` in memory, checks all three committed
  `closure/universes/us-co-snap/*.yaml` files and `closure/summary.json` against
  the producer's canonical serialization, and uses the computed summary. The
  old attested closure prose in the CO certificate is explicitly ignored.

CO closure is program-wide in v1. It covers 1,156 provisions in three roots and
currently has 290 pending, so it is computed open. The landed closure producer
does not yet supply an exact node/citation dependency join for CO.

### Executable evidence tiers

Executable evidence has two distinct labels:

| Tier | Required proof | Current producer |
| --- | --- | --- |
| `source_reproduction` | Pinned source compiles and committed cases replay under the producer validator | `scripts/executable_reproduction.py` and the other named source-reproduction producers |
| `release_receipt` | The published artifact runs on a released engine through the authenticated release-receipt contract | Pending in axiom-oracles #461 |

Tier labels are assigned only after `scripts/certify.py` has invoked the named
producer validator. A schema string, compiled hash, `target/release` path, or
legacy attestation cannot manufacture a tier.

DK's `axiom_oracles.executable_reproduction.v1` receipt is labeled
`source_reproduction`. It is program-level evidence: its witness output roots
do not imply that every individual graph node was itself executed. Exact graph
membership is checked first, then the program-level receipt is attached.

The CO surface is a published-artifact/released-engine surface and requires
`release_receipt`. Current main has no computed release receipt. A valid source
reproduction offered for CO would still refuse with
`executable.tier_insufficient`; source reproduction never satisfies a release
requirement.

A `release_receipt` may satisfy a source-level requirement, but not the other
way around.

### Provision rooting

`provision_rooted` remains computed-or-refused. The accepted node record must
carry both:

```yaml
provenance: provision_backed
corpus_citation_path: <non-empty exact path>
```

Neither the DK closure/receipt artifacts nor the CO compiled program carry the
node-level engine provenance annotation. The generator does not substitute a
module source path, a comparison concept, a program certificate, or a compiled
artifact hash. It emits:

```text
code: provision_rooted.producer_missing
producer: TheAxiomFoundation/axiom-rules-engine#136
```

If a provenance field exists but is not `provision_backed` with a citation, the
refusal is `provision_rooted.unverified`.

## Generated artifacts

### `certified-nodes.yaml`

The canonical file has the ops top-level schema exactly:

```yaml
schema: axiom.certified_nodes.v1
generated: true
as_of: '2026-08-20'
nodes: []
```

`as_of` is deliberately quoted so JavaScript YAML loaders retain a date string.
Manual entries are invalid. A generated nonempty entry follows the documented
ops computed-only shape and has no `mode` field.

### `certified-node-refusals.json`

The sidecar uses the richer schema
`axiom_oracles.node_certification_refusals.v1`. It records, per candidate:

- exact node and registered program;
- certificate state and hash;
- program-subgraph membership proof and artifact hash;
- required and offered executable tier;
- all five `{holds, evidence}` records; and
- every refusal code, missing producer, and explanation.

It also has top-level `format: axiom-validation-evidence/1` and an `entries`
projection with `{legal_id, oracle, evidence, shortfall}`. axiom-api can consume
that same file through `AXIOM_VALIDATION_EVIDENCE_FILE` as the `validated`
queue in its four-status taxonomy. The richer `refusals` records are ignored by
that loader but remain available to automation.

## Current computed result

| Candidates | `provision_rooted` | `conformant` | `exercised` | `closed` | `executable` |
| --- | --- | --- | --- | --- | --- |
| DK (2) | false — engine #136 producer missing | true | true | true | true — `source_reproduction` |
| CO (3) | false — engine #136 producer missing | true | false | false — 290 pending | false — `release_receipt` missing on #461 |

The honest ledger therefore has zero entries. The sidecar has five candidate
rows and the following refusal counts:

```text
provision_rooted.producer_missing  5
exercised.computed_false           3
closed.computed_open               3
executable.release_receipt_missing 3
```

## Command and exit contract

```bash
python3 scripts/certify_nodes.py --as-of 2026-08-20
python3 scripts/certify_nodes.py --check
```

Generation defaults `as_of` to the current date. Check mode reuses the quoted
date already committed in `certified-nodes.yaml`, recomputes both outputs, and
compares bytes.

Exit codes:

- `0`: producers and artifacts validated; outputs were written or are current.
  Candidate refusals do not change this status.
- `1`: check-mode output drift.
- `2`: malformed contract input, unknown program, producer failure, invalid or
  stale evidence, or unsafe path.

The generator writes neither output until every input producer has validated.

## Downstream mirror parity

The exact axiom-api `scripts/mirror-certified-nodes.mjs` is exercised against
the committed YAML twice. The test checks that:

- the source bytes are unchanged;
- the ledger is `axiom-certified-ledger/1`;
- `ledger_id` retains the quoted `as_of` date;
- source node IDs equal mirrored entry IDs; and
- the two outputs are identical after removing the wall-clock `issued_at`.

The current empty file mirrors successfully. A downstream divergence remains:
ops documents nonempty entries as computed-only with no `mode`, while the API
mirror currently requires `mode: computed|attested`. The first nonempty
ops-schema-exact ledger will require an axiom-api repair. This generator does
not add the forbidden field merely to satisfy that bug. The mirror also does
not copy the refusal sidecar; deployment must point the API validation-evidence
loader at the sidecar (or copy it to that data path).

## Required mutants

`tests/test_certify_nodes.py` commits the new-surface checks:

1. a registry-certified DK program whose node lacks engine #136 provenance
   refuses on `provision_rooted` while its other four criteria remain green;
2. a `source_reproduction` receipt offered where `release_receipt` is required
   refuses with `executable.tier_insufficient`; and
3. the exact downstream mirror script round-trips the generated empty ledger
   with node-ID parity and no source mutation.

Additional checks pin the five exact graph members, both executable tier
labels, CO's real computed closure counts, rejection of comparison aliases,
sidecar/API queue compatibility, and committed-output drift.

## Where reality diverged from the old contract

The original contract was written before the producer work landed. The
important differences are:

| Old assumption | Landed reality and this adapter |
| --- | --- |
| Eight speculative node-index, graph, manifest, governance, and receipt inputs would arrive together. | The real authority is the program registry and its named producer validators. Most speculative inputs never landed. |
| A generic candidate/node index would enumerate nodes and dependencies. | No candidate producer landed. This PR adds a minimal explicit five-node adapter and verifies membership against real program artifacts. |
| Closure would be per-node over a dependency graph. | DK exposes a closure ledger with module/rule facts. CO v1 closure is program-wide across three universes and remains open. |
| Conformance could be read from a flat comparisons file. | `scripts/certify.py` now consumes strict bound reports, chunk evidence, dispositions, and reference/reality oracle types. |
| Exercise required the speculative dimensions contract. | The landed census and certificate define audited bridge, per-case evidence, reconciliation, and observed variation semantics. |
| Executable meant one release-only node adapter with golden binding maps. | Main first landed multiple program-scoped source-reproduction families. Release receipt authentication grew into a separate, still-pending #461 producer. |
| Receipt witness outputs enumerated node coverage. | Source receipts prove a program replay, not per-node execution. Program-subgraph membership is established separately. |
| Provision annotations were expected from engine #115. | The current missing producer is engine #136; no artifact carries its node annotation yet. |
| A run manifest and workflow-governance document authorized certification. | Certification is deterministic and computed-only. Producer validation and committed-byte drift checks replace the speculative governance ceremony. |
| Report concept IDs were graph node IDs. | CO reports contain semantic aliases; only exact compiled `derived[].id` members qualify. |
| CO's certificate closure/executable prose was the best available evidence. | The committed closure universes are stronger computed evidence and override stale closure prose; legacy executable attestation remains insufficient. |
| Ops and API shared one nonempty entry shape. | Empty parity works, but ops forbids `mode` while the API mirror requires it. This is documented downstream debt, not weakened here. |

CO's report, closure universes, local compiled artifact, and published release
also pin different vintages. The current false exercise, open closure, and
missing release receipt already prevent their conjunction; no cross-vintage
certification is inferred.
