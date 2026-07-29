# Defensive gate-coverage completeness audit

Date: 2026-07-29  
Review branch: `autogo/gate-coverage-review`  
Framing: defensive correctness and completeness verification for AUTOGO

## Verdict

The current aggregate state is fail-closed: no node certifies today. The
certificate is `unavailable` while `closed` and `executable` are attested, the
bridge manifests cannot yet become strict-clean, and the committed closure
summary is not closed.

That safe present-day outcome does **not** make the gate set ready for AUTOGO.
Six critical and eight high-severity acceptance gaps remain. The most important
are:

1. a false slim-report count skips disposition replay, after which forged
   mismatch classifications pass the evidence and certificate gates;
2. the certificate state machine can call mutable registry text “computed,”
   omits the required node-level `provision_rooted` premise, and can therefore
   self-activate once the other legs are green;
3. closure accepts an empty pinned denominator as `closed: true`;
4. closure treats a filename or review prose as semantic coverage even when the
   branch's own review data says the module has no executable rules; and
5. conformance evidence is not bound to the engine, artifact, RuleSpec, or
   dependency tuple named by the executable evidence.

Twenty strict xfailed mutants in
`tests/test_gate_coverage_gaps.py` preserve executable acceptance proofs at the
gate responsible for each rejection. Composition mutants isolate the missing
join rather than reimplementing every upstream gate. They all fail against the
reviewed branch objects; an XPASS against an integrated gate family means the
corresponding hole was fixed.

## Scope and method

All target repositories and feature branches were read-only. Branch contents
were inspected with `git show`; no target branch was checked out or changed.

Reviewed objects:

| Surface | Reviewed object |
|---|---|
| AUTOGO contract | `ops` `launch/certified-nodes@187f8e7` |
| Original program certificate tip | `program-certificate@871454d4` |
| Cumulative certificate, census, manifest, and evidence implementation | `evidence-validator@a312ace1` |
| Census precursor | `exercise-census@03a0b401` |
| Manifest/certificate precursor | `bridge-manifests@b8f73d8b` |
| Closure implementation | `closure-universes@9414bc89` |

The named `program-certificate` tip predates `_count`, the certified state
machine, and the certification mutant suite named in the task. It is an
ancestor of `evidence-validator`, which contains the cumulative six-round
hardening. The audit therefore used the cumulative implementation for new
findings rather than re-reporting defects already fixed on descendant branches.

Each candidate was required to have:

- an exact malformed, incomplete, or mislabeled input;
- a reproducible accepted result at the reviewed object;
- a stated rejection rule grounded in the gate's own contract or in the five
  AUTOGO criteria; and
- a regression mutant when the behavior was directly testable.

## Ranked findings

| Rank | ID | Severity | Gate that must reject |
|---:|---|---|---|
| 1 | GCR-01 | Critical | disposition replay + evidence + certificate composition |
| 2 | GCR-02 | Critical | certified state machine |
| 3 | GCR-07 | Critical | closure denominator and summary |
| 4 | GCR-18 | Critical | closure encoding join / AUTOGO `closed` composition |
| 5 | GCR-05 | Critical | conformance-to-executable provenance join |
| 6 | GCR-08 | Critical | closure exclusion validation |
| 7 | GCR-03 | High | certificate oracle-type validation |
| 8 | GCR-04 | High | certificate zero-open-defects rule |
| 9 | GCR-06 | High | exercise certificate predicate |
| 10 | GCR-09 | High | closure `encoded_by` binding |
| 11 | GCR-19 | High | closure review provenance/expiry |
| 12 | GCR-10 | High | closure `partial_coverage` validation |
| 13 | GCR-11 | High | closure pending ratchet |
| 14 | GCR-12 | High | closure ratchet pin identity |
| 15 | GCR-13 | Medium | classification merge ingestion |
| 16 | GCR-14 | Medium | bridge-manifest input typing |
| 17 | GCR-15 | Medium | bridge-manifest `covered_by` relevance |
| 18 | GCR-16 | Medium | population identity pinning |
| 19 | GCR-17 | Medium | cardinality-only evidence semantics |
| 20 | GCR-20 | Medium | certificate `_count` coverage |

### GCR-01 — A false slim count bypasses disposition replay

**Severity:** Critical  
**Reject in:** `scripts/apply_dispositions.py`, with defense in
`axiom_oracles/evidence.py` and `scripts/certify.py`  
**Code:** `apply_dispositions.py:115-159`; `certify.py:396-508`

Exact report mutation:

```json
{
  "schema_version": "axiom.comparison_report.v2.1",
  "suite": "victim",
  "summary": {
    "comparison_count": 1,
    "match_count": 0,
    "mismatch_count": 1,
    "stored_mismatch_example_count": 0,
    "dispositioned": {
      "dispositions_file": "dispositions/victim.yaml",
      "unexplained_count": 0,
      "counts": {"upstream_engine_gap": 1}
    }
  },
  "mismatches": [{
    "case_id": "live-case",
    "concept": "program#benefit",
    "left": 1,
    "right": 2,
    "disposition": {
      "id": "forged-not-in-cited-file",
      "disposition": "upstream_engine_gap"
    }
  }]
}
```

The cited file is schema-valid and declares `suite: victim`, but its sole entry
selects `case_id: never-matches` and `concept: other#output`. The compact case
chunk repeats the forged marker and all report/index hashes are refreshed.

**Actual:** `_is_premerged_slim_report` returns true solely because
`0 < mismatch_count`. The replay gate skips the report without checking that
`len(mismatches) == 1`. Evidence validation proves only that the report and
chunk agree with each other. Certification validates the disposition document's
schema and suite, not that the cited entry selected this row. The leg is clean
with zero unexplained mismatches.

**Required:** reconcile `stored_mismatch_example_count` with stored rows; replay
every stored row even for legitimately slim reports; bind each marker ID,
selector, concept, disposition kind, and pin to the cited entry.

**Mutant:** `test_forged_stored_mismatch_count_cannot_skip_disposition_replay`

The mutant isolates the first required rejection: the false stored count must
not activate the slim-report bypass. The downstream evidence and certificate
acceptance described above was checked separately against the composed branch
objects.

### GCR-02 — The four-premise state machine treats registry text as computation

**Severity:** Critical  
**Reject in:** `scripts/certify.py` certified state machine  
**Code:** `certify.py:703-739`

Exact registry input after making conformance and exercise clean:

```python
spec["attested"] = {
    "closed": {
        "status": "computed",
        "value": True,
        "source": "does-not-exist",
    },
    "executable": {
        "status": "computed",
        "value": True,
        "source": "does-not-exist",
    },
}
# No provision_rooted field or node identity exists.
```

**Actual:** `_premise` derives emitted mode only from
`block["status"] == "computed"` and tests `value is True`. With clean reference
and exercise legs, the certificate returns:

```json
{"certified": {"state": "yes", "value": true}, "blockers": []}
```

No producer, artifact, receipt, or hash is opened. The rule includes only
`conformant AND exercised AND closed AND executable`; the AUTOGO contract
requires the fifth `provision_rooted` criterion for the specific node.

**Required:** computed premises must be outputs of registered deterministic
producers and bind their artifacts/hashes. Certification must be node-level and
must include `provision_rooted`.

**Mutant:** `test_certified_requires_a_real_producer_and_provision_root`

### GCR-07 — Empty pinned closure denominators are closed

**Severity:** Critical  
**Reject in:** `scripts/closure_universe.py` source loader and summary  
**Code:** `closure_universe.py:251-305, 1207-1257, 1321-1377`

Exact input:

1. replace each required source JSONL with empty bytes;
2. set its provenance SHA to
   `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`;
3. run `--generate`, then `--check`.

**Actual:** an empty source file is valid. Generation starts a new baseline for
the new pin and emits three zero-row universes. The summary computes
`closed = all(pending == 0)` and returns `closed: true`; the subsequent check
passes. Partial truncation similarly erases omitted pending citations when the
pin changes.

**Required:** each declared root needs an independently pinned denominator
identity and non-vacuity/cardinality/root-row invariants. A pin change must not
turn disappearance into closure without a separately computed denominator
reconciliation.

**Mutant:** `test_empty_pinned_closure_denominator_cannot_be_closed`

### GCR-18 — Filename presence is promoted to semantic encoding

**Severity:** Critical for AUTOGO composition  
**Reject in:** closure encoding join or the downstream mapping to `closed`  
**Code:** `closure_universe.py:236-248, 1046-1067`

Exact generated input is only:

```python
source_rows = [{
    "citation": "us/test/substantive",
    "heading": "Benefit formula",
}]
tree_paths = {"us/tests/substantive.yaml"}
```

No module bytes, node provenance, declared outputs, executable rules, or test
evidence are supplied.

**Actual:** the row becomes `status: encoded`.

This is not hypothetical on the branch. `closure/classifications/a3-state.yaml`
states that `4.000.1` is `entity_not_supported` with no executable rules,
`4.903.3` and `4.903.4` are deferred with no executable rules, and `4.702.4`
has a deferred branch. All four rows remain `encoded` in the generated
universe, while the state root reports zero pending.

The closure README accurately calls the v1 join repository coverage rather than
faithful implementation proof. The hole is treating that narrow signal as the
AUTOGO `closed` criterion.

**Required:** either inspect content/executable node metadata and hold stubs at
pending, or keep repository-file coverage as a separately named non-certifying
signal.

**Mutant:** `test_rulespec_filename_presence_is_not_complete_encoding_evidence`

### GCR-05 — Conformance is not joined to the executable/dependency tuple

**Severity:** Critical  
**Reject in:** certificate composition / execution-attestation integration  
**Code:** `evidence.py:1-6`; `certify.py:189-305`

Exact accepted report: a bound, fully reconciled, all-match reference report
with **no** `provenance`, engine identity, artifact identity, RuleSpec pins, or
dependency pins.

**Actual:** the evidence validator intentionally does not attest engine
identity. The certificate copies the registry's oracle label without comparing
it with the report and returns a clean reference leg.

There is a concrete live mismatch: the executable block names
`engine v0.1.1 x program-artifacts-59a10dab866e`, while the co-SNAP conformance
report records engine version `0.1.0`, engine SHA `48797e...`, and separate
RuleSpec SHAs `ca2d...` and `8e636...`. No gate joins those identities.

**Required:** one content-addressed execution tuple must bind report producer,
oracle version/artifact, engine, program artifact, all transitive RuleSpec
dependencies, period, and certified node.

**Mutant:**
`test_clean_reference_leg_requires_execution_and_dependency_provenance`

This is a certificate-join proof: it injects a successful internal evidence
validation result and demonstrates that the certificate asks no provenance
question of that result.

### GCR-08 — A substantive provision can be excluded by bare assertion

**Severity:** Critical under no-human AUTOGO  
**Reject in:** `scripts/closure_universe.py` exclusion validation  
**Code:** `closure_universe.py:251-305, 618-628`

Exact source and overlay:

```json
{"citation_path": "us/test/a",
 "heading": "Eligibility formula",
 "body": "The household benefit equals ..."}
```

```yaml
citation: us/test/a
heading: Eligibility formula
status: excluded
reason: no_household_computation
basis: Reviewed.
```

**Actual:** the source loader discards `body` and source kind. The validator
checks only that the reason is in the taxonomy and `basis` is nonempty. The
exclusion passes, lowers pending, and can contribute to `closed: true`.

**Required:** every exclusion reason needs a deterministic predicate over the
pinned source row, or a separately governed machine-verifiable classification
artifact. Free prose cannot decide an AUTOGO gate.

**Mutant:** `test_substantive_provision_cannot_be_excluded_by_bare_assertion`

### GCR-03 — A misspelled oracle type drops a dirty suite

**Severity:** High  
**Reject in:** `scripts/certify.py` suite registry validation  
**Code:** `certify.py:201-205, 679-690`

Exact registry entry:

```python
{
    "suite": "dirty-but-dropped",
    "oracle_type": "referance",
    "report": "dirty.json",
}
```

The report is valid and carries one unexplained mismatch.

**Actual:** the suite is treated with non-reference evidence strength, then
appears in neither `reference_legs` nor `reality_legs`. It contributes no
blocker; a separate clean reference leg makes `conformant: true`.

**Required:** reject every oracle type outside the exact
`{"reference", "reality"}` enum before reading the report.

**Mutant:** `test_unknown_oracle_type_is_a_certificate_defect`

### GCR-04 — A reality leg's admitted Axiom defect is nonblocking

**Severity:** High  
**Reject in:** `scripts/certify.py` zero-open-defects computation  
**Code:** `certify.py:679-699`

Exact leg:

```python
{
    "oracle_type": "reality",
    "mismatches": 1,
    "unexplained": 0,
    "axiom_attributed_open": 1,
    "clean": False,
}
```

**Actual:** reality disagreement counts are leads, but blockers are constructed
only from reference legs. The explicit `axiom_encoding_gap` is omitted and the
certificate can reach `yes`.

**Required:** ordinary unexplained reality disagreement may remain a lead, but
an explicitly attributed open Axiom defect must violate the certificate's
“zero open defects” rule.

**Mutant:** `test_reality_leg_axiom_encoding_gap_is_an_open_defect`

### GCR-06 — An all-constant, unbound census row is “exercised”

**Severity:** High  
**Reject in:** `scripts/certify.py::_exercise_block`, joined to manifest/catalog  
**Code:** `certify.py:574-658`; `exercise_census.py:17-40`

Exact census row, with report path and SHA matching the registry:

```json
{
  "cases_scanned": 1,
  "evidence_fields": {
    "material_input": {"distinct": 1, "state": "constant"}
  },
  "varied_fields": 0,
  "constant_fields": 1,
  "bridge_audited": true,
  "binding": "unbound",
  "reconciliation": "none",
  "contested_reports": []
}
```

**Actual:** `bool(evidence_fields)` is the evidence predicate. Binding,
reconciliation, material-field variation, and alignment with mapped/projected
manifest inputs are not required. The row returns exercise complete even though
the census's own contract says a constant dimension carries no evidence.

**Required:** reconcile the complete input catalog to manifest bindings and
require the program's material dimensions/branches to be varied or explicitly
covered elsewhere. An unrelated varied metadata field must not suffice.

**Mutant:** `test_exercised_requires_bound_material_variation`

### GCR-09 — `encoded_by` can name an unrelated existing module

**Severity:** High  
**Reject in:** `scripts/closure_universe.py::_validate_encoded_by`  
**Code:** `closure_universe.py:455-509`

Exact row for a Colorado provision:

```yaml
citation: us-co/regulation/10-ccr-2506-1/eligibility-formula
heading: Eligibility amount formula
status: encoded
encoded_by:
  - us/statutes/7/2011.yaml
```

If the federal path is in the pinned tree, this passes.

**Actual:** validation proves lexical safety and tree membership only. It does
not bind the module's citations, outputs, dependency graph, or program/root to
the provision.

**Required:** verify module-to-provision node provenance and output coverage;
at minimum, reject a corrected path outside the root unless a machine-readable
cross-provision realization declares the relationship.

**Mutant:** `test_corrected_encoded_by_must_bind_module_to_provision`

### GCR-19 — Reviewed closure overlays do not expire on source changes

**Severity:** High  
**Reject in:** closure review/provenance binding  
**Code:** `closure_universe.py:1046-1117`

Exact transition:

```yaml
# Old source/review
citation: us/test/a
heading: Old bodyless heading
status: excluded
reason: container_heading
basis: The old version had no substantive body.
```

At a new source pin, the same citation becomes
`heading: "NEW: substantive eligibility computation"` with substantive body.

**Actual:** overlays are keyed only by citation and remain excluded. No source
row hash, body hash, RuleSpec hash, or review commit is attached to the
decision.

The committed data also exposes an unvalidated provenance split: closure pins
RuleSpec `1158ba5b...`, while `a3-state.yaml` says its content audit used
`3373e8411`.

**Required:** bind every reviewed decision to exact source-row and RuleSpec
content identities and expire it on either change.

**Mutant:** `test_source_change_expires_reviewed_exclusion`

### GCR-10 — `partial_coverage` does not require a joined deferred module

**Severity:** High  
**Reject in:** `scripts/closure_universe.py` pending-row validation  
**Code:** `closure_universe.py:635-650`

Exact row where the candidate module is absent from the tree:

```yaml
citation: us/test/missing-module
heading: Substantive computation
status: pending
partial_coverage: The joined module defers this output.
```

**Actual:** any nonblank text is accepted. Validation enforces
`join_found_module -> partial_coverage` but not the reverse. The existing
positive closure mutant demonstrates this on a fixture that intentionally has
no Colorado module.

**Required:** the disclosure must bind to a present joined module and a
machine-readable deferred output/branch that covers this provision.

**Mutant:** `test_partial_coverage_requires_a_present_joined_deferred_module`

### GCR-11 — Old disclosures mask unrelated pending regressions

**Severity:** High  
**Reject in:** closure pending ratchet  
**Code:** `closure_universe.py:1144-1170`

Exact baseline/current transition with unchanged pins:

```text
baseline pending_max = 1
row A = pending + existing partial_coverage
row B = excluded

current:
row A = same pending + existing partial_coverage
row B = plain pending, no disclosure
```

**Actual:** `rise == 1`; the code counts all current disclosure rows, so
`disclosed == 1` and accepts the unrelated reopening. On the committed CFR
root, seven existing partial rows can similarly authorize reopening an
unrelated excluded row.

**Required:** compare row identities across the baseline and allow only a
newly disclosed encoded-to-pending correction for the same row.

**Mutant:** `test_existing_disclosure_cannot_mask_unrelated_pending_rise`

### GCR-12 — A semantic no-op repin resets the pending floor

**Severity:** High  
**Reject in:** closure ratchet pin identity  
**Code:** `closure_universe.py:133-153, 267, 1004, 1144`

Exact input change:

```diff
 {"citation_path":"us/test/a","heading":"A"}
+
```

The parser ignores the added blank line, so the denominator is identical.
Updating the declared raw-file SHA nevertheless changes `pins_sha256`.

**Actual:** artifact and history baselines with the old pin are ignored. A
pending regression may be committed as a fresh baseline; later `--check`
passes. Reordering source rows or the tree inventory has the same effect because
parsers normalize those shapes but pins hash raw bytes.

**Required:** ratchet identity must use canonical parsed denominator/tree
semantics, while raw byte hashes remain separate provenance integrity fields.

**Mutant:** `test_semantic_noop_repin_does_not_reset_pending_floor`

### GCR-13 — Malformed classification rows are silently dropped

**Severity:** Medium  
**Reject in:** `scripts/merge_closure_classifications.py` ingestion  
**Code:** `merge_closure_classifications.py:59-66`

Exact classification:

```yaml
rows:
  - citaiton: us/test/a
    status: pending
    note: Module defers the substantive output.
```

**Actual:** `_rows_from` filters out any row without `citation`; the merge
reports zero classifications and zero errors. The known stub remains encoded.
Full closure CI does not read `closure/classifications/`, so it also passes.

**Required:** every non-comment classification document and every row must be
schema-validated; no row may disappear during parsing.

**Mutant:** `test_merge_rejects_classification_missing_citation`

### GCR-14 — Scalar manifest `inputs` bypasses typed duplicate detection

**Severity:** Medium  
**Reject in:** `scripts/validate_bridge_manifests.py`  
**Code:** `validate_bridge_manifests.py:136-151`

Exact input:

```yaml
bindings:
  - kind: mapped
    inputs: abc
    source: population:x
    audit: read
  - kind: constant
    input: abc
    reason: fixture
    audit: read
```

**Actual:** the scalar is iterated as input names `a`, `b`, `c`; the later
`abc` binding is not detected as a duplicate. No type error is emitted.

**Required:** `inputs` must be a nonempty array of nonempty strings before
duplicate analysis.

**Mutant:** `test_bridge_manifest_inputs_must_be_an_array`

### GCR-15 — `covered_by` accepts circular or unrelated files

**Severity:** Medium  
**Reject in:** bridge-manifest evidence resolution  
**Code:** `validate_bridge_manifests.py:60-85`

Exact references that resolve:

```yaml
covered_by:
  - pyproject.toml
  # The manifest's own repository path also resolves.
```

**Actual:** any existing repository path satisfies the check, regardless of
artifact type, suite, concept, derivation, or circularity.

**Required:** resolve a typed evidence claim and verify that it independently
covers the bridged dimension for the same program/period.

**Mutant:**
`test_bridge_covered_by_must_resolve_to_relevant_independent_evidence`

### GCR-16 — One malformed token satisfies population pinning

**Severity:** Medium  
**Reject in:** bridge-manifest population validation  
**Code:** `validate_bridge_manifests.py:205-219`

Exact report fragment:

```json
{"dataset_identity": {"sha256": "yes"}}
```

**Actual:** pinning is `bool(revision OR sha256)`. The invalid one-field token
suppresses the population-pin finding.

**Required:** require the specified identity tuple, including a nonempty
revision and a valid lowercase digest, and bind it to the exact report/cases.

**Mutant:** `test_population_pin_requires_revision_and_valid_digest`

### GCR-17 — Verdict-free cardinality evidence may claim 100% agreement

**Severity:** Medium  
**Reject in:** `axiom_oracles/evidence.py` compact row validation  
**Code:** `evidence.py:507-640, 1766-1775`

Exact compact row:

```json
{"id": "case-1", "r": 100, "h": {}, "m": []}
```

There is no `v` array and no mismatch verdict.

**Actual:** the numeric rate is accepted, and a chunk of such rows can remain
valid under cardinality reconciliation.

**Required:** without verdict evidence, `r` must be `null`; cardinality proves
only that rows exist, not agreement.

**Mutant:** `test_cardinality_only_case_cannot_claim_full_agreement`

### GCR-20 — Malformed `unexplained_count` escapes `_count`

**Severity:** Medium  
**Reject in:** `scripts/certify.py` disposition-shape validation  
**Code:** `certify.py:345-523`

Exact otherwise clean summary:

```json
{
  "comparison_count": 1,
  "match_count": 1,
  "mismatch_count": 0,
  "dispositioned": {
    "counts": {},
    "unexplained_count": "one"
  }
}
```

**Actual:** because `classified == 0` and there is no disposition file,
`unexplained_count` is never passed to `_count`. The leg is clean with no
defect.

**Required:** validate the entire disposition block independent of which
accounting branch consumes each field.

**Mutant:** `test_unexplained_count_is_validated_even_when_counts_are_empty`

This is a certificate-local proof: it injects otherwise successful evidence
validation to isolate `_suite_verdict`'s incomplete `_count` coverage.

## Composition-level gaps

The following relationships are absent even where each local artifact is
internally consistent:

1. **Node subject:** certificates are program-level. No gate joins a certified
   node to `provision_rooted`, its citation, reachable RuleSpec dependencies,
   closure rows, exercise dimensions, conformance concepts, and executable
   artifact. GCR-02, GCR-06, GCR-09, and GCR-18 are consequences.
2. **Execution identity:** conformance and executable evidence can describe
   different engines/artifacts/dependencies. GCR-05 is present in the committed
   co-SNAP evidence.
3. **Disposition authority:** report/chunk agreement is not authority to
   classify a mismatch. The cited disposition selectors and pins must be
   replayed. GCR-01 crosses three individually plausible gates.
4. **Closure-to-exercise/conformance:** closure's `encoded` paths are never
   compared with census fields or conformance concepts. A provision can be
   counted encoded while all material dimensions are constant or absent.
5. **Classification provenance:** CI runs `closure_universe.py --check` but does
   not validate `closure/classifications/` or bind those reviews to the merged
   rows. Classification files may be stale, contradictory, or deleted without
   changing the closure verdict.
6. **Dependency closure:** closure has three hard-coded roots and a filename
   inventory, not a computed citation/import graph from the candidate node.
   A node can have dependencies outside the ledgers with no pending row.

## Gates and portions found sound

No additional finding was manufactured where the reviewed code rejected the
mutant or where the contract was not clear.

### Certification and dispositions

Subject to the findings above, the cumulative implementation correctly rejects:

- zero-work reports;
- missing/malformed reports;
- report-suite mismatches and contested reports;
- invalid core counts, negative counts, engine error shapes, and nonfinite or
  negative weighted mismatch mass;
- missing, unsafe, unreadable, empty, schema-invalid, or foreign-suite
  disposition documents;
- unknown disposition kinds and nonconserving disposition counts;
- unauditable slim reports without case evidence; and
- stray generated certificates and byte drift.

The present `unavailable` state for attested premises is fail-closed. The defect
is the reachable transition demonstrated by GCR-02.

### Evidence validator

The following were sound:

- strict JSON/nonfinite rejection;
- safe suite-directory names;
- required, nonnegative summary counts and conservation;
- case ID presence and global uniqueness;
- duplicate/overlapping per-case concept rejection;
- chunk filename, digest, cardinality, report path/SHA, and case-verdict binding;
- full per-verdict summary/aggregate/mismatch reconciliation for fields the
  report carries;
- report/chunk disposition-marker agreement; and
- refusal to promote partial verdict evidence to cardinality reconciliation.

The validator's explicit exclusion of engine identity is honest locally; GCR-05
is the missing composition gate.

### Exercise census and bridge manifests

The census correctly binds its row to the exact report path and SHA, surfaces
contested reports, prefers full chunks over illustrative inline cases, and
records constant/varied/bridged states deterministically for ordinary numeric
ranges.

The manifest set correctly rejects unknown binding kinds, invalid audit states,
duplicate names for correctly typed inputs, missing bridge source/mechanism,
namespace collisions, ghost/absolute/traversal `covered_by` paths, partial audit
debt under strict evaluation, and self-asserted completeness. Because every
current completeness state produces a finding or error, `bridge_audited` remains
false; this is a deliberate safe blocker until catalog verification exists.

### Closure ledger and ratchet

For nonempty sources and unchanged semantic pins, the closure gate correctly
rejects malformed JSON, missing/duplicate/out-of-root citations, malformed
headings, invalid statuses, contradictory row fields, empty exclusion basis,
unsafe/ghost/test module paths, duplicate `encoded_by` paths, descendant-as-
parent joins, citation drift, stale generated artifacts, forged one-sided
ratchet ceilings, coordinated current-artifact ceiling edits, forged universe
provenance, shallow history, and simplified merge history.

The direct closure taxonomy parser is exact. The assertion-grounding,
partial-disclosure, semantic-repin, and classification-ingestion holes are the
remaining gaps.

## Verification

Run:

```console
.venv/bin/pytest -q tests/test_gate_coverage_gaps.py -rxX
```

Expected result at the reviewed objects:

```text
20 xfailed
```

The test file prefers the current implementation when a complete gate family
has been integrated into its worktree. Until then, as on this review branch, it
loads the pinned branch objects in memory with `git show`. It never checks out
or modifies a reviewed branch.

## Defensive conclusion

The gate set is not AUTOGO-complete yet. The current blockers prevent an actual
false certification, but GCR-02 shows that the state machine can remove that
protection by accepting registry text as computation. Before any node may
self-certify, the critical findings must be closed as one composed protocol:
node subject, complete denominator, semantic closure, exact execution/dependency
identity, replayed dispositions, material exercise, and zero open defects.
