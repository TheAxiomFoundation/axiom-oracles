# Autogo node-certification integration contract

Status: normative contract for `scripts/certify_nodes.py`.

Autogo is a deterministic projection, not an attestation or approval workflow.
No person grants certification, and no manual entry, waiver, or assertion can
substitute for a computed producer. Given the same requested nodes and the same
existing-ledger node-ID set, repo-root-relative path layout, producer bytes,
and evidence bytes, the harness produces the same certification ledger.

The certification unit is an exact RuleSpec node, not a program. For each
candidate node, the harness resolves that node plus every transitive dependency
from the compiled artifact and computes five criteria:

```text
provision_rooted = every node in the resolved subgraph is provision-backed
closed            = every exactly declared closure root exists and pending == 0
completeness      = provision_rooted AND closed

conformant         = every declared comparison is committed, bound, fully
                     reconciled, nonempty, error-free, and has zero
                     unexplained and zero Axiom-attributed mismatches
exercised          = every required dimension was varied in evidence bound to
                     that exact comparison report and was not bridged
fidelity           = conformant AND exercised

certified          = provision_rooted AND closed AND conformant
                     AND exercised AND executable
                   = completeness AND fidelity AND executable
```

There are no vacuous passes. Missing provenance, roots, comparisons, required
dimensions, census evidence, computed-producer markers, pins, reports,
disposition conservation, executable manifests/receipts/coverage, input-byte
bindings, or governed run verification are red.

## Command-line interface

```console
uv run python scripts/certify_nodes.py \
  us:statutes/26/3101/b/1#medicare_wage_tax \
  [MORE_NODE_IDS ...] \
  --artifact PATH \
  --node-index PATH \
  --closure-summary PATH \
  --comparisons PATH \
  --exercise-census PATH \
  --executable PATH \
  --run-manifest PATH \
  --governance PATH \
  [--output PATH] \
  [--reasons-output PATH] \
  [--repo-root PATH] \
  [--check]
```

All eight integration inputs are required. `--output` defaults to
`certified-nodes.yaml`, and `--repo-root` defaults to the repository containing
the script. Relative CLI producer and output paths resolve against
`--repo-root`; absolute CLI paths remain absolute.

Producer-declared evidence paths are stricter: comparison reports, disposition
files, executable manifests, executable receipts, and all four executable trust
roots must be relative paths that contain no `..` and resolve to a strict
descendant of `--repo-root`. Reports and executable evidence must have a
case-insensitive `.json` suffix; dispositions must use `.yaml` or `.yml`. An
absolute path, traversal, symlink escape, directory, malformed/NUL-bearing
path, or wrong-suffix evidence target fails closed.

Files ending in `.yaml` or `.yml` are parsed as YAML; other integration
documents are parsed as JSON. Duplicate mapping/object keys, non-finite
numbers, recursive aliases, nesting deeper than 128 levels, malformed input,
and non-object top levels are rejected. The same strict loader is used for
linked evidence.

Resolution failures for integration inputs—including malformed paths and
symlink loops—make that producer unavailable and yield its machine-readable
`*.producer_missing` reason rather than a traceback. Producer-declared linked
paths additionally remain subject to the repository-confinement and suffix
rules above.

Positional node IDs must be unique and match the legal-node form accepted by
the script: a supported jurisdiction and source path followed by `#rule_name`.
The jurisdiction starts with two lowercase letters and may have lowercase
alphanumeric `-` suffixes; the source kind is exactly one of `legislation`,
`policies`, `regulations`, or `statutes`; path segments use
`[A-Za-z0-9_.~-]+`; and the rule name uses `[A-Za-z0-9_.-]+`. Malformed IDs
fail argument parsing before producer evaluation.

The candidate set is the union of the positional node IDs and every nonempty
`node` ID recoverable from the existing output ledger. This is intentional:
partial invocations preserve an existing node only by recomputing it green,
and a regression is evaluated and removed even when that node was not named on
the command line.

Without `--check`, the command stages every requested output in its target
directory, flushes and `fsync`s the staged bytes, then replaces the targets.
The reasons file, when requested, is replaced before the canonical ledger so a
diagnostic write failure cannot leave the ledger advanced by itself. Each
replacement is atomic; the pair is staged together but is not a transactional
multi-file commit. Missing parent directories are created. The decertified
projection is written even when a candidate is red, and the process then
returns nonzero.

With `--check`, the command is read-only. It recomputes both documents and
compares their exact UTF-8 bytes with the existing files. Line endings,
comments, final newlines, ordering, and encoding all participate; CRLF is
drift. A missing file is drift. It returns nonzero for any rejected candidate
or for ledger/result drift.

Accordingly, drift includes:

- a green requested node missing from the ledger;
- a regressed requested node that remains in the ledger;
- a hand-added or otherwise extra entry;
- stale presentation, run, pin, criterion, or evidence fields; and
- stale `--reasons-output`, when supplied.

`--output` and `--reasons-output` must resolve to different files. Neither may
overwrite `scripts/certify_nodes.py`, the imported executable-validator source,
any of the eight integration inputs, or any producer-declared comparison
report, disposition file, executable manifest, executable receipt, or
golden-output bindings file. The imported dispositions-validator source,
engine-release manifests, golden requests, and executable workflow allowlists
referenced by an executable manifest are protected too. These aliases are
argument errors detected before writing.

Exit status is `0` only when every candidate certifies and, in check mode, both
requested outputs are byte-current. Rejection, drift, or write failure returns
`1`; argument/ID/path-alias errors use argparse's status `2`.

## Validation primitives

Every integration envelope producer has the schema discriminator shown below.
The engine's compiled artifact instead uses its native
`artifact_format_version: 2` plus a `program` object. Unsupported schemas or
artifact formats fail closed.

SHA-256 content identities are 64 lowercase hexadecimal characters. Git and
workflow commit identities are 40 lowercase hexadecimal characters. Counts are
real integers, not booleans. A linked evidence identity consists of both its
repository-relative path and the SHA-256 of the actual bytes at that resolved
path.

The harness does not coerce strings such as `"true"` or `"0"` into booleans or
counts. A CI run ID may be a positive integer or a decimal string representing
one. A string run ID uses only ASCII decimal digits, contains at most 20
characters, and is not all zeroes.

## Compiled artifact

`--artifact` is the published compiled RuleSpec artifact. Engine issue #115 must
produce an array at `metadata.nodes` and an adjacency object at
`metadata.dependency_graph`:

```yaml
artifact_format_version: 2
engine_version: 0.1.1
program:
  units: []
  relations: []
  parameters: []
  derived: []
metadata:
  pinned:
    rulespec_us: eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee
    corpus: ffffffffffffffffffffffffffffffffffffffff
    engine: v0.1.1
  nodes:
    - id: us:statutes/26/3101/b/1#medicare_wage_tax
      provenance: provision_backed
      corpus_citation_path: us/statute/26/3101
    - id: us:statutes/26/3121/a#medicare_wage_base
      provenance: provision_backed
      corpus_citation_path: us/statute/26/3121
  dependency_graph:
    us:statutes/26/3101/b/1#medicare_wage_tax:
      - us:statutes/26/3121/a#medicare_wage_base
    us:statutes/26/3121/a#medicare_wage_base: []
```

`artifact_format_version` must be the integer `2`, and `program` must be an
object. This is the real engine artifact interface; the integration does not
invent an `axiom.compiled_artifact.v1` schema field. `metadata.pinned` must
exactly equal the run's `rulespec_us`, `corpus`, and `engine` pins; no extra or
missing key is accepted.

Every node record needs a unique nonempty `id`. Each graph value is a list of
unique, nonempty direct-dependency IDs. Every requested or reached node needs a
node record and an explicit graph row; a dependency that has no node record is
invalid. Cycles are invalid. Traversal starts with the target and follows
dependency values until the full reachable set is visited.

For `provision_rooted` to hold, every reached node record must have exactly
`provenance: provision_backed` and a nonempty `corpus_citation_path`. An absent
provenance field is read as `unverified` and fails. No program-level certificate
or module filename can replace these node facts.

The SHA-256 of the exact artifact bytes is the shared artifact identity. It must
match:

- `node_index.artifact_sha256`;
- `node_comparisons.artifact_sha256`;
- `node_executable.artifact_sha256`;
- every comparison row's `pinned.artifact`;
- every executable row's `pinned.artifact`;
- every executable manifest's `artifact.sha256`;
- every executable receipt's `artifact.sha256`; and
- `run_manifest.pinned.artifact`.

The run manifest also binds the artifact's exact byte hash as
`inputs.compiled_artifact`.

## Node certification index v1

`--node-index` is scope and presentation metadata. It declares what must be
computed; it never declares a verdict.

```yaml
schema: axiom_oracles.node_certification_index.v1
artifact_sha256: <compiled artifact sha256>
producer:
  mode: computed
nodes:
  us:statutes/26/3101/b/1#medicare_wage_tax:
    label: Employee Medicare payroll tax
    provision: 26 USC 3101(b)(1)
    corpus_citation_path: us/statute/26/3101
    closure_roots:
      - us:statutes/26/3101
    comparisons:
      - suite: us-medicare-wage-tax
        required_dimensions:
          - wages
  us:statutes/26/3121/a#medicare_wage_base:
    label: Medicare wage base
    provision: 26 USC 3121(a)
    corpus_citation_path: us/statute/26/3121
    closure_roots:
      - us:statutes/26/3121
    comparisons:
      - suite: us-medicare-wage-tax
        required_dimensions:
          - wages
```

`nodes` is an object keyed by exact node ID. Every node in the target's resolved
subgraph needs an object member, not just the target. The target member's
`label`, `provision`, and `corpus_citation_path` become the ledger presentation
fields. Before emission, the target's declared `corpus_citation_path` must
equal its artifact node's citation.

Each subgraph member's `closure_roots` is a nonempty, duplicate-free list of
exact root IDs. The harness never infers a root from a node ID, citation prefix,
module path, or program. It takes the stable first-seen union of the roots
declared by every subgraph member. The computed index producer is responsible
for declaring that complete root set; omission is a producer defect, not an
invitation for the integration layer to guess.

Each subgraph member's `comparisons` is a nonempty list of objects. Within one
member, every object needs a unique nonempty `suite` and, for exercise, a
nonempty list of unique `required_dimensions`. Applicability and legally
behavior-changing dimensions are declared here and must be independently
repeated by the comparison producer for that same subgraph node. Only exact
agreement creates applicability; extra producer rows or census fields cannot
do so. When several subgraph members use one suite, the report is evaluated
once and the exercise requirement is the stable union of their dimensions.

The top-level `artifact_sha256` must match the artifact bytes, and
`producer.mode` must be exactly `computed`. The run manifest separately binds
the index's exact bytes as `inputs.node_index`.

## Governed certification run and trust boundary

The candidate-produced run manifest is not its own authority. `--governance`
supplies the allowlist and run-verification ledger consumed by the script:

```yaml
schema: axiom_oracles.certify_nodes.governance.v1
repository: TheAxiomFoundation/axiom-oracles
workflow_path: .github/workflows/certify-nodes.yml
event: workflow_dispatch
ref: refs/heads/main
allowed_workflow_shas:
  - cccccccccccccccccccccccccccccccccccccccc
allowed_certify_check_shas:
  - dddddddddddddddddddddddddddddddddddddddd
verified_runs:
  - ci_run_id: "424242"
    certified_at: 2026-07-29T12:34:56Z
    run_manifest_sha256: <sha256 of exact run-manifest bytes>
    workflow_sha: cccccccccccccccccccccccccccccccccccccccc
    certify_check: dddddddddddddddddddddddddddddddddddddddd
    inputs:
      compiled_artifact: <artifact sha256>
      node_index: <node-index sha256>
      closure_summary: <closure-summary sha256>
      node_comparisons: <node-comparisons sha256>
      exercise_census: <exercise-census sha256>
      node_executable: <node-executable sha256>
```

The schema must be exactly
`axiom_oracles.certify_nodes.governance.v1`. The repository, workflow path,
event, and ref are nonempty governed values. Both allowlists are nonempty,
duplicate-free lists of full 40-character lowercase commit SHAs.

The run ID must match exactly one `verified_runs` row after converting both IDs
to strings. That row's `run_manifest_sha256` must equal the exact
`--run-manifest` bytes, and its `certified_at`, `workflow_sha`,
`certify_check`, and complete six-input map must exactly equal the parsed run
manifest. Merely placing a workflow SHA on an allowlist cannot authorize an
unverified run.

The script validates the supplied governance bytes, but it cannot establish who
controlled the path passed to `--governance`. Authoritative production CI must
therefore fetch that document from a separately controlled verifier
checkout/ref, outside candidate-write authority, and must run the allowlisted
checker bytes. A caller that can replace both governance and the run manifest
can manufacture a locally green pair; such a run validates the file protocol
but is not authoritative certification. Governance is deliberately absent from
the six candidate hashes because it is an external policy input, not a
candidate-produced artifact.

`--run-manifest` binds the candidate producer bytes and emitted entry to one
certification vintage:

```yaml
schema: axiom_oracles.certify_nodes.run.v1
certified_at: 2026-07-29T12:34:56Z
harness:
  ci_run_id: "424242"
  repository: TheAxiomFoundation/axiom-oracles
  workflow_path: .github/workflows/certify-nodes.yml
  event: workflow_dispatch
  ref: refs/heads/main
  workflow_sha: cccccccccccccccccccccccccccccccccccccccc
  certify_check: dddddddddddddddddddddddddddddddddddddddd
pinned:
  rulespec_us: eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee
  corpus: ffffffffffffffffffffffffffffffffffffffff
  engine: v0.1.1
  artifact: <compiled artifact sha256>
inputs:
  compiled_artifact: <artifact sha256>
  node_index: <node-index sha256>
  closure_summary: <closure-summary sha256>
  node_comparisons: <node-comparisons sha256>
  exercise_census: <exercise-census sha256>
  node_executable: <node-executable sha256>
```

`certified_at` must parse as a timezone-bearing timestamp and end in `Z`.
`harness.ci_run_id` may be a positive integer or the bounded ASCII decimal
string form described above.
`harness.workflow_sha` and `harness.certify_check` are full 40-character
lowercase commit SHAs. The other four harness fields must exactly equal the
governed values, and both SHAs must be members of their respective allowlists.

`pinned.rulespec_us` and `pinned.corpus` are full 40-character lowercase commit
SHAs. `pinned.engine` is a nonempty released-version string.
`pinned.artifact` is the compiled artifact's 64-character SHA-256 and must
equal the actual artifact bytes. The artifact's `metadata.pinned` object must
exactly equal the other three vintage pins.

`inputs` must have exactly the six keys shown—no governance hash and no extra
producer—and every value must equal the SHA-256 of the CLI input's actual
bytes.

If any run, governance, pin, or input-binding field is missing, malformed, or
inconsistent, the run context is unavailable and no entry can be emitted.

## Closure summary v1

`--closure-summary` consumes PR #400's roots-array schema, extended with
independently comparable pins on every root row:

```yaml
schema: axiom_oracles.closure.summary.v1
program: us/medicare
roots:
  - root: us:statutes/26/3101
    total: 2
    by_status:
      encoded: 1
      excluded: 1
      pending: 0
    by_reason:
      outside_node_scope: 1
    pins_sha256: 1111111111111111111111111111111111111111111111111111111111111111
    pinned:
      rulespec_us: eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee
      corpus: ffffffffffffffffffffffffffffffffffffffff
  - root: us:statutes/26/3121
    total: 1
    by_status:
      encoded: 1
      excluded: 0
      pending: 0
    by_reason: {}
    pins_sha256: 2222222222222222222222222222222222222222222222222222222222222222
    pinned:
      rulespec_us: eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee
      corpus: ffffffffffffffffffffffffffffffffffffffff
closed: true
```

For every root declared by every node in the resolved subgraph, the consumer
exact-looks up a `roots` array row whose `root` string matches. Every per-node
declaration and the producer array must be duplicate-free; a root shared by
several subgraph members is evaluated once. Every producer root row must be an
object with a nonempty `root`; a malformed or duplicate row anywhere makes the
closure producer invalid.

`by_status` must have exactly the keys `encoded`, `excluded`, and `pending`,
each with a nonnegative integer value. Their sum must equal `total`, and
`total` must be a positive integer: a vacuous zero-provision root is not
closed. `by_reason` must be an object whose keys are nonempty strings and whose
values are positive integers; its sum must exactly equal
`by_status.excluded`. An empty `by_reason` is valid only when `excluded == 0`.
This is the producer's machine-readable excluded-with-reason accounting.

The root passes only when the live `by_status.pending` is exactly zero.
`pins_sha256` must be a 64-character SHA-256. The row's `pinned` object must be
exactly:

```yaml
rulespec_us: <run pinned.rulespec_us>
corpus: <run pinned.corpus>
```

The current producer's `pending_max` and global `closed` may still be present,
but the node harness does not use them as the per-node verdict. `by_reason` is
validated as described above. Likewise, `closure_universe.py --check` validates
integrity and can exit zero while live pending is positive; its process status
is not closure.

An encoded provision is producer-computed/reviewed coverage. An excluded
provision must already have a closure-producer-validated reason and basis. A
partial module remains pending. The integration layer does not reinterpret
individual closure classifications.

The run manifest binds the closure summary's exact bytes as
`inputs.closure_summary`.

## Node comparisons v1

`--comparisons` is the node-level projection of committed, validated comparison
evidence:

```yaml
schema: axiom_oracles.node_comparisons.v1
artifact_sha256: <compiled artifact sha256>
producer:
  mode: computed
  dispositions_validator: axiom_oracles.comparison.dispositions.validate_dispositions
  dispositions_validator_sha256: <sha256 of dispositions.py>
comparisons:
  us-medicare-wage-tax:
    applicable_nodes:
      - us:statutes/26/3101/b/1#medicare_wage_tax
      - us:statutes/26/3121/a#medicare_wage_base
    required_dimensions:
      us:statutes/26/3101/b/1#medicare_wage_tax:
        - wages
      us:statutes/26/3121/a#medicare_wage_base:
        - wages
    committed: true
    binding: bound
    reconciliation: full
    case_count: 4
    comparison_count: 4
    error_count: 0
    unexplained_count: 0
    axiom_attributed_count: 0
    report:
      path: reports/us-medicare-wage-tax.json
      sha256: <sha256 of the report bytes>
    pinned:
      rulespec_us: eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee
      corpus: ffffffffffffffffffffffffffffffffffffffff
      engine: v0.1.1
      artifact: <compiled artifact sha256>
```

The top-level `artifact_sha256` must match the artifact, and
`producer.mode` must be exactly `computed`.
`producer.dispositions_validator` must be exactly
`axiom_oracles.comparison.dispositions.validate_dispositions`, and
`producer.dispositions_validator_sha256` must equal the bytes of
`axiom_oracles/comparison/dispositions.py` in the harness checkout. The module
must load with the exact v1 schema, taxonomy, `validate_dispositions`, and
`apply_dispositions` public contract. A missing, unreadable, hash-mismatched, or
incompatible validator is a missing producer, not permission to trust report
counts. `comparisons` is an object keyed by suite. The run manifest binds the
comparison projection's exact bytes—including the validator hash—as
`inputs.node_comparisons`.

Applicability is double-entered and reconciled, not trusted from either side
alone:

- Every producer row has a nonempty, duplicate-free `applicable_nodes` list.
- Its `required_dimensions` is an object with exactly those node IDs as keys.
  Every value is a nonempty, duplicate-free list of nonempty strings.
- For every node in the target's resolved subgraph, the producer's suite set
  must exactly equal that node's index suite set.
- For each `(subgraph node, suite)` pair, the producer and node index must
  declare the same required dimensions, compared as a set and cardinality. A
  rekeyed report, omitted dependency, added suite, or changed dimension set
  fails.

Every object-valued producer row is structurally checked, including rows that
do not apply to the current node. A declared suite whose value is not an object
is absent and fails as a missing row.

For every declared suite, the matching comparison member passes only when:

- `committed` is literal `true`;
- `case_count` is a positive integer;
- `comparison_count` is a positive integer;
- `binding` is exactly `bound`;
- `reconciliation` is exactly `full`;
- `error_count` is the integer zero;
- `unexplained_count` is the integer zero;
- `axiom_attributed_count` is the integer zero;
- `report.path` resolves to a readable file whose actual SHA-256 equals
  `report.sha256`; and
- `pinned` exactly equals all four fields in the run manifest's `pinned`
  object.

The report is not an opaque hash. It must be repository-confined JSON with this
identity and summary interface:

```yaml
schema_version: axiom.comparison_report.v2.1
suite: us-medicare-wage-tax
case_count: 4
summary:
  comparison_count: 4
  match_count: 4
  mismatch_count: 0
  error_count: 0
```

The report's `schema_version` must be exactly
`axiom.comparison_report.v2.1`, its `suite` must equal the producer key, and
its top-level `case_count` must be a positive integer.
`summary.comparison_count` is positive; `match_count`, `mismatch_count`, and
`error_count` are nonnegative integers; and
`match_count + mismatch_count == comparison_count`.

When `summary.dispositioned` is absent and the report is otherwise countable,
every mismatch is derived as unexplained and the Axiom-attributed count is
zero, and the comparison row must not carry a `dispositions` reference. When
present, the block must exactly equal the output of the pinned
`apply_dispositions` implementation. Its interface is:

```yaml
summary:
  dispositioned:
    schema_version: axiom_oracles.dispositions.v1
    dispositions_file: dispositions/us-medicare-wage-tax.yaml
    raw_match_rate: 75
    explained_rate: 100
    unexplained_count: 0
    counts:
      explained_residual: 0
      upstream_engine_gap: 1
      bridge_artifact: 0
      axiom_encoding_gap: 0
      unexplained: 0
    expired_entries: []
    orphaned_entries: []
```

`schema_version` must be exactly `axiom_oracles.dispositions.v1`. `counts`
must have exactly the five keys shown, all nonnegative integers—no invented
safe bucket is accepted. `unexplained_count` is a nonnegative integer. The
real v2.1 block may repeat explicitly marked unexplained rows inside
`counts.unexplained`; that informational category is not added a second time.
The recomputation enforces:

```text
sum(count for category != "unexplained")
    + dispositioned.unexplained_count
    == summary.mismatch_count

dispositioned.counts.get("unexplained", 0)
    <= dispositioned.unexplained_count
```

When `dispositions_file` is non-null it must be a nonempty repo-confined
`.yaml`/`.yml` path. The comparison row must repeat and hash-bind it:

```yaml
dispositions:
  path: dispositions/us-medicare-wage-tax.yaml
  sha256: <sha256 of exact disposition bytes>
```

The path must exactly equal `summary.dispositioned.dispositions_file`, and the
actual bytes must match the row hash. The strict YAML document must pass the
pinned `validate_dispositions` function for the report suite. Its producer
interface begins:

```yaml
schema: axiom_oracles.dispositions.v1
suite: us-medicare-wage-tax
updated: '2026-07-29'
entries:
  - id: medicare-wage-tax-upstream-gap
    concept: us:statutes/26/3101/b/1#medicare_wage_tax
    case_id: case-4
    disposition: upstream_engine_gap
    evidence:
      mechanism: The residual is attributable to the upstream oracle.
    linked_issue: https://github.com/example/upstream/issues/123
    expires_on_source_change: true
```

Entries have unique IDs, use only `explained_residual`,
`upstream_engine_gap`, `bridge_artifact`, `axiom_encoding_gap`, or
`unexplained`, and carry the evidence required by that validator. The validator
also checks suite identity, selectors, arithmetic/source evidence, issue URLs,
source-change expiry, and pinned values where supplied. The harness then runs
`apply_dispositions` over the parsed report and validated document and requires
the entire stored `summary.dispositioned` block—rates, exact counts, and
expired/orphaned IDs included—to equal recomputation.

A null `dispositions_file` must have no comparison-row pointer and is
recomputed with no disposition document. A false, empty, escaping, unbound, or
invalid file reference is red. Only `axiom_encoding_gap` contributes to the
integration row's `axiom_attributed_count`. A comparison producer may claim
`reconciliation: full` only after the evidence validator has reconciled the
report's mismatch rows as well.

The node-comparison row's `case_count`, `comparison_count`, `error_count`,
`unexplained_count`, and `axiom_attributed_count` must exactly equal the values
derived from the parsed report. Those fields must then pass the direct zero
gates above. Thus a copied or rekeyed hash, an inconsistent summary, an
unconserved disposition, or a row that lies about report counts fails as
`conformant.report_invalid`.

Cardinality-only or unreconciled comparison evidence is not full. A
disposition that attributes a mismatch to Axiom does not create fidelity:
unexplained and Axiom-attributed counts must both be zero. Missing disposition
machinery cannot turn a mismatch into zero.

Program-level `scripts/certify.py` from PR #373 stays program-level. Its logic
may feed this producer, but a program verdict is not evidence for every node.

## Exercise census v1

`--exercise-census` consumes the existing census schema:

```yaml
schema: axiom_oracles.exercise_census.v1
suites:
  us-medicare-wage-tax:
    report: reports/us-medicare-wage-tax.json
    report_sha256: <same report sha256 as node_comparisons>
    contested_reports: []
    binding: bound
    binding_defects: []
    reconciliation: cardinality
    bridge_declared: true
    bridge_audited: true
    cases_scanned: 4
    evidence_fields:
      wages:
        distinct: 4
        state: varied
    bridged_through: {}
```

For every comparison declared by every node in the resolved subgraph, the
consumer checks the following. A suite shared by several subgraph nodes is
looked up once, and their required dimensions are combined without treating a
duplicate dimension as additional evidence.

1. The census must have an object member for that exact suite.
2. Its `(report, report_sha256)` pair must exactly equal the comparison row's
   `(report.path, report.sha256)` pair.
3. `contested_reports` may be absent/null or exactly `[]`; any nonempty or
   malformed value fails. A suite claimed by multiple reports has ambiguous
   suite-keyed evidence ownership and cannot establish fidelity.
4. `binding` must be `bound` and `binding_defects` must be exactly `[]`.
   `reconciliation` may be `cardinality` or `full`; the census interface is
   cardinality-reconciled even though the comparison verdict itself requires
   `full`.
5. `bridge_declared` and `bridge_audited` must both be literal `true`.
   Absence is not evidence that no bridge was used.
6. `cases_scanned` must be a positive integer and must exactly equal the parsed
   comparison report's top-level `case_count`. It is deliberately not compared
   with `summary.comparison_count`, which may be cases multiplied by compared
   dimensions. `evidence_fields` and `bridged_through` must both be objects.
7. Every `required_dimensions` item must exist in `evidence_fields`, have
   `state: varied`, and have an integer `distinct` satisfying
   `2 <= distinct <= cases_scanned`.
8. No required dimension may appear as a key in `bridged_through`.

The final rule is deliberate: a dimension that is constant or bridged
contributes **zero fidelity**. An audited bridge can explain experiment design,
but it is not evidence that the compared implementations independently varied
the dimension where the law changes behavior. Extra varied dimensions cannot
compensate for a missing, constant, invalid, or bridged required dimension.

The run manifest binds the census's exact bytes as `inputs.exercise_census`.

## Parked executable receipt and node adapter

The parked executable producer owns a rich **program-level**
`axiom_oracles.executable_receipt.v1`. The integration does not redefine that
receipt as a one-node assertion. Instead, `--executable` is a separate computed
node adapter over the parked validator:

```yaml
schema: axiom_oracles.node_executable.v1
artifact_sha256: <compiled artifact sha256>
producer:
  mode: computed
  adapter: axiom_oracles.node_executable.from_validated_receipt.v1
  validator: axiom_oracles.executable_receipt.validate_executable_receipt
  validator_sha256: <sha256 of axiom_oracles/executable_receipt.py>
nodes:
  us:statutes/26/3101/b/1#medicare_wage_tax:
    program: us/medicare
    validated: true
    covered_nodes:
      - us:statutes/26/3101/b/1#medicare_wage_tax
      - us:statutes/26/3121/a#medicare_wage_base
    manifest:
      path: manifests/us-medicare.json
      sha256: <sha256 of executable manifest bytes>
    receipt:
      path: receipts/us-medicare-wage-tax.json
      sha256: <sha256 of executable receipt bytes>
    trust_roots:
      manifests/engine-releases.json: <sha256>
      manifests/executable-workflow-allowlist.json: <sha256>
      manifests/us-medicare-golden-outputs.json: <sha256>
      manifests/us-medicare-golden-request.json: <sha256>
    pinned:
      engine: v0.1.1
      artifact: <compiled artifact sha256>
```

The top-level schema and artifact hash must match. `producer.mode`,
`producer.adapter`, and `producer.validator` must be the exact values shown,
and `producer.validator_sha256` must be a lowercase SHA-256. `nodes` is keyed
by legal node ID. The requested row needs a nonempty `program`, literal
`validated: true`, and a nonempty, duplicate-free `covered_nodes` list
containing that node. Its `pinned` object must exactly equal the run's `engine`
and `artifact` pins. The run manifest binds the adapter's exact bytes,
including its validator and trust-root hashes, as `inputs.node_executable`.

Every node that may certify needs its own `nodes` member, even when several
members point to the same validated program receipt and repeat the same
derived coverage set.

The integration then dynamically imports
`axiom_oracles.executable_receipt.validate_executable_receipt`. The module's
resolved source file must be inside `--repo-root`, its bytes must be readable,
and their SHA-256 must equal `producer.validator_sha256`. An authorized
validator change therefore requires a new adapter hash and changes the governed
`node_executable` input hash. Absence of the module or callable, loading it
from outside the repository, or unreadable validator bytes is
`executable.producer_missing`; module-initialization exceptions are caught as
the same machine-readable absence. A hash mismatch is
`executable.receipt_invalid`. Producer strings alone cannot stand in for
execution. The consumer calls:

```python
validate_executable_receipt(
    receipt_path,
    repo_root=repo_root,
    manifest_path=manifest_path,
)
```

The return object must have literal `valid is True`, the actual
`receipt_sha256`, and an evidence object binding the adapter's `program`, the
run's `engine` release, and the compiled artifact SHA-256. For a negative
result, its `failures` are copied into the machine-readable detail. An
exception, negative result, missing evidence, or identity mismatch is
`executable.receipt_invalid`.

The row hash-binds a repository-confined executable manifest:

```yaml
schema: axiom_oracles.executable_manifest.v1
program: us/medicare
receipt_path: receipts/us-medicare-wage-tax.json
engine:
  release_manifest: manifests/engine-releases.json
  release: v0.1.1
  target: x86_64-unknown-linux-gnu
artifact:
  repository: TheAxiomFoundation/rulespec-us
  release: program-artifacts-test
  release_manifest:
    name: manifest.json
    sha256: <release-manifest sha256>
  name: us-medicare.compiled.json
  sha256: <compiled artifact sha256>
golden:
  name: us-medicare-golden
  input_path: manifests/us-medicare-golden-request.json
  input_sha256: <golden request sha256>
  outputs_path: manifests/us-medicare-golden-outputs.json
  outputs_sha256: <golden-output bindings sha256>
workflow:
  allowlist: manifests/executable-workflow-allowlist.json
  repository: TheAxiomFoundation/axiom-oracles
  path: .github/workflows/executable-receipt.yml
  event: workflow_dispatch
  ref: refs/heads/main
```

At the integration boundary, the manifest schema, program, artifact SHA,
engine release, and `receipt_path` must match the adapter, artifact, run pins,
and receipt pointer. The parked validator owns the manifest's stronger exact
shape and the engine-release, artifact-release, golden-input, and executable
workflow trust roots.

The row's `trust_roots` must have exactly four keys, taken from the manifest:

- `engine.release_manifest`;
- `golden.input_path`;
- `golden.outputs_path`; and
- `workflow.allowlist`.

Those four manifest paths must be distinct, nonempty strings. Each must resolve
to repository-confined JSON, and its actual SHA-256 must equal the corresponding
row value. Because the exact `trust_roots` map is inside the governed
`node_executable` bytes, the engine release manifest, golden request, golden
output bindings, and executable-workflow allowlist are content-bound even
though they are not separate keys in the six-input run map. All four paths are
also protected from output aliasing.

The manifest's `golden.outputs_path` names a hash-bound mapping:

```yaml
description: Hash-bound legal-id coverage for the executable receipt.
bindings:
  medicare_wage_tax: us:statutes/26/3101/b/1#medicare_wage_tax
  medicare_wage_base: us:statutes/26/3121/a#medicare_wage_base
expected:
  medicare_wage_tax: 145
  medicare_wage_base: 10000
```

`bindings` and `expected` must be nonempty objects with exactly the same output
keys. Every binding value is a nonempty node-ID string. The adapter's
`covered_nodes` must equal the sorted unique set of binding values. The
receipt's golden output keys must also exactly equal the binding keys. This is
the only accepted program-to-node coverage derivation; relabeling a foreign
program receipt or merely listing a node in the adapter is insufficient.

The referenced receipt retains the parked program-level v1 shape:

```yaml
schema: axiom_oracles.executable_receipt.v1
program: us/medicare
engine:
  repository: TheAxiomFoundation/axiom-rules
  release: v0.1.1
  version: 0.1.1
  target: x86_64-unknown-linux-gnu
  asset: axiom-rules-engine-x86_64-unknown-linux-gnu.tar.xz
  sha256: <released engine asset sha256>
artifact:
  repository: TheAxiomFoundation/rulespec-us
  release: program-artifacts-test
  name: us-medicare.compiled.json
  sha256: <compiled artifact sha256>
  manifest_sha256: <published artifact manifest sha256>
golden:
  name: us-medicare-golden
  input_path: manifests/us-medicare-golden-request.json
  input_sha256: <golden request sha256>
  inputs:
    wages: 10000
  outputs:
    medicare_wage_tax: 145
    medicare_wage_base: 10000
commands:
  - argv:
      - .executable-receipt-work/engine/axiom-rules-engine
      - run-compiled
    exit_code: 0
    stdin_sha256: <golden request sha256>
timestamp: 2026-07-29T12:30:00Z
workflow:
  repository: TheAxiomFoundation/axiom-oracles
  path: .github/workflows/executable-receipt.yml
  sha: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
  run_id: 424241
  run_attempt: 1
  event: workflow_dispatch
  ref: refs/heads/main
```

The example abbreviates the parked producer's exact multi-command sequence.
The imported validator re-derives the rich receipt from the committed
executable manifest, engine release manifest, golden fixture, golden-output
bindings, workflow allowlist, exact released-binary stranger-path commands,
zero exit codes, hashes, timestamp, and workflow provenance. Focused unit tests
inject a contract double on `PYTHONPATH` for failure isolation; the expanded
fixture has also been checked against the actual parked validator. Production
must import that real implementation from the governed repository checkout.

The integration independently rechecks the receipt schema and program,
released engine and artifact identities, a nonempty command list and timestamp,
and workflow repository/path/event/ref, positive run ID and integer run
attempt, and full workflow commit SHA. It also checks the hash-bound manifest,
receipt, and output-bindings bytes and node coverage described above.

This producer must run the **published** artifact on the **released** engine
through the public stranger path. An attested prototype, unpublished checkout,
candidate engine, model-assisted run, private credential, loads-only result,
or ad hoc node receipt is not executable evidence.

## Generated certified-node ledger

`--output` is the exact concatenation of:

1. the authoritative launch header carried in `HEADER`, including the ruling
   and all six critical-path holes;
2. one blank line and the deterministic YAML payload; and
3. one blank line and the fixed commented entry template in
   `ENTRY_SHAPE_COMMENT`.

Both comment blocks, all newlines, and the final newline are part of the
byte-level contract. The semantic `axiom.certified_nodes.v1` payload and entry
shape are:

```yaml
schema: axiom.certified_nodes.v1
generated: true
as_of: '2026-07-29'
nodes:
  - node: us:statutes/26/3101/b/1#medicare_wage_tax
    label: Employee Medicare payroll tax
    provision: 26 USC 3101(b)(1)
    corpus_citation_path: us/statute/26/3101
    certified_at: '2026-07-29T12:34:56Z'
    harness:
      run: 424242@cccccccccccccccccccccccccccccccccccccccc
      certify_check: dddddddddddddddddddddddddddddddddddddddd
    pinned:
      rulespec_us: eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee
      corpus: ffffffffffffffffffffffffffffffffffffffff
      engine: v0.1.1
      artifact: <compiled artifact sha256>
    criteria:
      provision_rooted:
        holds: true
        evidence:
          artifact: <artifact path>
          sha256: <artifact sha256>
          nodes:
            - us:statutes/26/3101/b/1#medicare_wage_tax
            - us:statutes/26/3121/a#medicare_wage_base
      conformant:
        holds: true
        evidence:
          index: <node comparisons path>
          sha256: <node comparisons sha256>
          reports:
            - suite: us-medicare-wage-tax
              report: reports/us-medicare-wage-tax.json
              sha256: <report sha256>
          dispositions_validator:
            validator: axiom_oracles.comparison.dispositions.validate_dispositions
            validator_path: axiom_oracles/comparison/dispositions.py
            validator_sha256: <sha256 of validator bytes>
      exercised:
        holds: true
        evidence:
          census: <exercise census path>
          sha256: <exercise census sha256>
          suites:
            - suite: us-medicare-wage-tax
              required_dimensions:
                - wages
      closed:
        holds: true
        evidence:
          summary: <closure summary path>
          sha256: <closure summary sha256>
          roots:
            - us:statutes/26/3101
            - us:statutes/26/3121
      executable:
        holds: true
        evidence:
          index: <node executable path>
          index_sha256: <node executable sha256>
          manifest: manifests/us-medicare.json
          manifest_sha256: <executable manifest sha256>
          receipt: receipts/us-medicare-wage-tax.json
          receipt_sha256: <executable receipt sha256>
          covered_nodes:
            - us:statutes/26/3101/b/1#medicare_wage_tax
            - us:statutes/26/3121/a#medicare_wage_base
          trust_roots:
            - path: manifests/engine-releases.json
              sha256: <sha256>
            - path: manifests/us-medicare-golden-request.json
              sha256: <sha256>
            - path: manifests/us-medicare-golden-outputs.json
              sha256: <sha256>
            - path: manifests/executable-workflow-allowlist.json
              sha256: <sha256>
          validator_path: axiom_oracles/executable_receipt.py
          validator_sha256: <sha256 of validator bytes>
          validator: axiom_oracles.executable_receipt.validate_executable_receipt
          output_bindings: manifests/us-medicare-golden-outputs.json
          output_bindings_sha256: <golden-output bindings sha256>
```

Only entries with all five `holds: true` are emitted. Entries are sorted by node
ID; criteria retain the fixed order `provision_rooted`, `conformant`,
`exercised`, `closed`, `executable`. `as_of` is the date portion of
the validated run's `certified_at`; it is `unverified` when the run,
governance, pins, or input bindings do not validate.

When a report uses a disposition document, its member in
`criteria.conformant.evidence.reports` additionally carries
`dispositions: {path: ..., sha256: ...}`.

Generation starts from the union of the requested IDs and existing ledger IDs,
then rebuilds every entry from producer evidence. This preserves an existing
green entry across a partial invocation without trusting its old fields. A
regression removes a formerly green node in write mode and causes drift in
check mode. A hand-added entry is likewise recomputed and cannot survive
without all producers green.

No mode, attester, reviewer, override, waiver, grandfathering, or manual-note
field is permitted in an entry.

## Result document, stdout, and drift

When `--reasons-output` is supplied, the canonical JSON file is:

```yaml
schema: axiom_oracles.certify_nodes.result.v1
certified:
  - us:statutes/26/3101/b/1#medicare_wage_tax
rejected: []
```

For a rejected node, `rejected` contains its computed criteria and all reasons:

```yaml
schema: axiom_oracles.certify_nodes.result.v1
certified: []
rejected:
  - node: us:statutes/26/3101/b/1#medicare_wage_tax
    criteria:
      provision_rooted:
        holds: true
        evidence: <producer evidence object>
      conformant:
        holds: true
        evidence: <producer evidence object>
      exercised:
        holds: false
        evidence: <producer evidence object>
      closed:
        holds: true
        evidence: <producer evidence object>
      executable:
        holds: true
        evidence: <producer evidence object>
    reasons:
      - criterion: exercised
        code: exercised.dimension_constant
        producer: exercise_census
        detail: Suite dimension was constant and contributes zero fidelity.
```

Each reason has `criterion`, a criterion-namespaced `code`, `producer`, and
human-readable `detail`; some reasons also have an `evidence` string.
Automation keys on `criterion` and `code`.

The stdout JSON starts with that same result and adds:

```yaml
drift:
  certified_nodes: false
  reasons: false
output_reasons: []
```

`drift.certified_nodes` reports ledger drift.
`drift.reasons` reports `--reasons-output` drift, or remains false when that
option was omitted. `output_reasons` holds `output.drift`,
`output.reasons_drift`, and/or `output.write_failed` reason objects. These
stdout-only fields are added after the canonical reasons file is rendered, so
they are not written into `--reasons-output`.

After a successful write both drift booleans are reset to false. A staging or
replacement error is reported as `output.write_failed` and returns nonzero. In
check mode neither target nor its parent directory is modified.

## Stable fail-closed reason codes

Internal detailed checks are normalized to stable namespaced codes:

| Criterion | Code | Meaning |
| --- | --- | --- |
| `provision_rooted` | `provision_rooted.producer_missing` | Artifact metadata or node index is unavailable. |
| `provision_rooted` | `provision_rooted.producer_invalid` | Artifact v2 format/program or node-index schema is unsupported. |
| `provision_rooted` | `provision_rooted.graph_missing` | `metadata.dependency_graph` is absent. |
| `provision_rooted` | `provision_rooted.graph_invalid` | Node metadata or a dependency row/reference is malformed. |
| `provision_rooted` | `provision_rooted.node_missing` | The requested node has no artifact node record. |
| `provision_rooted` | `provision_rooted.unverified` | A subgraph node is not provision-backed with a citation. |
| `provision_rooted` | `provision_rooted.pin_mismatch` | Node-index artifact identity differs. |
| `provision_rooted` | `provision_rooted.declaration_missing` | A resolved subgraph node has no index declaration. |
| `provision_rooted` | `provision_rooted.node_declaration_invalid` | Presentation/citation fields are invalid or inconsistent. |
| `closed` | `closed.producer_missing` | Closure summary or its roots array is unavailable. |
| `closed` | `closed.producer_invalid` | Closure schema or counts are invalid. |
| `closed` | `closed.declaration_missing` | A subgraph node has no nonempty closure-root list. |
| `closed` | `closed.declaration_invalid` | A subgraph node repeats a closure root. |
| `closed` | `closed.root_missing` | An exact declared root row is absent. |
| `closed` | `closed.pending` | A declared root has positive live pending. |
| `closed` | `closed.producer_provenance_missing` | A root lacks a valid `pins_sha256`. |
| `closed` | `closed.pin_mismatch` | A root's rulespec/corpus pins differ from the run. |
| `conformant` | `conformant.producer_missing` | Applicability, computed comparison output, or the pinned dispositions validator is unavailable. |
| `conformant` | `conformant.producer_invalid` | Comparison schema, counts, or result fields are invalid. |
| `conformant` | `conformant.declaration_missing` | A comparison declaration lacks a suite. |
| `conformant` | `conformant.declaration_invalid` | Suite applicability or required dimensions are malformed or duplicated. |
| `conformant` | `conformant.declaration_mismatch` | Node index and producer disagree on applicable suites or dimensions. |
| `conformant` | `conformant.pin_mismatch` | Comparison artifact or four-key vintage pins differ. |
| `conformant` | `conformant.row_missing` | A declared suite has no computed row. |
| `conformant` | `conformant.report_missing` | Its report is absent or not hash-bound. |
| `conformant` | `conformant.report_invalid` | The parsed report identity, counts, exact validated disposition recomputation, or projected fields are inconsistent. |
| `conformant` | `conformant.not_committed` | The comparison is not committed. |
| `conformant` | `conformant.empty` | `case_count` or `comparison_count` is not positive. |
| `conformant` | `conformant.unbound` | `binding` is not `bound`. |
| `conformant` | `conformant.not_full` | `reconciliation` is not `full`. |
| `conformant` | `conformant.errors` | At least one comparison ended in an error. |
| `conformant` | `conformant.unexplained` | At least one mismatch is unexplained. |
| `conformant` | `conformant.axiom_attributed` | At least one mismatch is attributed to Axiom. |
| `exercised` | `exercised.producer_missing` | Applicability, required dimensions, or census output is unavailable. |
| `exercised` | `exercised.producer_invalid` | Census schema is unsupported. |
| `exercised` | `exercised.declaration_invalid` | Required dimensions are duplicated. |
| `exercised` | `exercised.suite_missing` | The census has no exact suite row. |
| `exercised` | `exercised.report_mismatch` | Census and comparison report identities differ. |
| `exercised` | `exercised.contested_reports` | The suite is claimed by another report or its contest marker is malformed. |
| `exercised` | `exercised.unbound` | Census `binding` is not `bound`. |
| `exercised` | `exercised.not_full` | Census `reconciliation` is neither `cardinality` nor `full`. |
| `exercised` | `exercised.bridge_undeclared` | The census has no affirmative bridge-manifest declaration. |
| `exercised` | `exercised.bridge_unaudited` | The census has no affirmative clean bridge audit. |
| `exercised` | `exercised.evidence_missing` | No positive `cases_scanned` is available. |
| `exercised` | `exercised.evidence_incomplete` | `cases_scanned` differs from the comparison report's `case_count`. |
| `exercised` | `exercised.dimension_missing` | A required dimension has no measured field. |
| `exercised` | `exercised.dimension_constant` | A required dimension was constant. |
| `exercised` | `exercised.dimension_bridged` | A required dimension was bridged through. |
| `exercised` | `exercised.dimension_unvaried` | A field has another invalid/unvaried state. |
| `executable` | `executable.producer_missing` | Computed node output or row is absent, or the upstream validator is unavailable, outside the repo, or unreadable. |
| `executable` | `executable.producer_invalid` | Executable-index schema is unsupported. |
| `executable` | `executable.pin_mismatch` | Artifact, engine, or row pins differ. |
| `executable` | `executable.unvalidated` | The producer row is not validated. |
| `executable` | `executable.receipt_invalid` | The manifest/receipt/trust roots are absent, malformed, unbound, rejected by the parked validator, or have the wrong identity; this also covers a validator-byte mismatch. |
| `executable` | `executable.coverage_invalid` | Hash-bound golden outputs do not derive coverage for the node. |
| `harness` | `harness.producer_missing` | The run manifest or governance document is unavailable. |
| `harness` | `harness.producer_invalid` | Run or governance schema is unsupported. |
| `harness` | `harness.harness_provenance_invalid` | Timestamp or harness fields are invalid. |
| `harness` | `harness.governance_invalid` | Governed identity, allowlists, or verified-run records are malformed. |
| `harness` | `harness.governance_mismatch` | The run is not uniquely verified or differs from governed identity, allowlists, timestamp, run-manifest hash, or inputs. |
| `harness` | `harness.pin_missing` | A required run pin is absent or malformed. |
| `harness` | `harness.pin_mismatch` | Run/artifact content or vintage pins disagree. |
| `harness` | `harness.harness_inputs_invalid` | The run does not name exactly the six candidate producer hashes. |
| `harness` | `harness.harness_input_mismatch` | A named producer hash differs from the actual CLI input bytes. |
| `output` | `output.drift` | The ledger differs from recomputation. |
| `output` | `output.reasons_drift` | The result file differs from recomputation. |
| `output` | `output.write_failed` | Atomic staging or replacement failed. |

Producer absence is always a criterion-specific `*.producer_missing`, never an
empty success object or a zero count.

## Committed launch-critical mutants

Each launch-critical rejection ships with the exact input that exercises it:

| Mutant input | Rejection |
| --- | --- |
| `tests/fixtures/autogo/mutant-unverified-provenance.json` | A dependency lacks verified provision provenance: `provision_rooted.unverified`. |
| `tests/fixtures/autogo/mutant-closure-pending.json` | A declared root has one pending provision: `closed.pending`. |
| `tests/fixtures/autogo/mutant-axiom-attributed-mismatch.json` plus its linked `reports/mutant-axiom-attributed.json` and `dispositions/us-medicare-wage-tax.yaml` | One validated mismatch is attributed to Axiom: `conformant.axiom_attributed`. |
| `tests/fixtures/autogo/mutant-dimension-constant.json` | The legally required dimension is constant: `exercised.dimension_constant`. |
| `tests/fixtures/autogo/mutant-hand-added-entry.yaml` | A manually inserted ledger entry produces `output.drift`; check mode leaves the bytes untouched. |
| `tests/fixtures/autogo/mutant-regressed-executable.json` | A previously green node becomes `executable.unvalidated`; check detects the stale entry and write mode removes it. |

The adversarial suite additionally covers a bridged or unaudited dimension,
comparison errors, dependency cycles, foreign/rekeyed reports and receipts,
invented disposition buckets, repository path escape and malformed paths,
recursive/deep producer documents, broken validator imports, unverified
governed runs, malformed or duplicate closure/applicability data, impossible
dimension cardinality, CRLF-only drift, output aliases, and
preservation-by-recomputation in partial invocations.

## Upstream landing checklist

The integration and its committed mutants can run against fixtures now, but no
real node can certify until every producer below lands against one shared
vintage:

- **Engine #115:** publish `metadata.nodes[]` with exact
  `provenance: provision_backed` and `corpus_citation_path`, publish the complete
  acyclic `metadata.dependency_graph`, carry the exact three-key
  `metadata.pinned` vintage, preserve native
  `artifact_format_version: 2` plus the `program` object, and rebuild the
  release artifacts. Old artifacts without these fields remain unverified.
- **PR #400 (`closure-universes`):** land its pinned roots-array generator and
  live zero-pending calculation; reject duplicate and vacuous roots; fully
  account exclusions in positive `by_reason` counts; add each root row's exact
  `pinned.rulespec_us` and `pinned.corpus`; and generalize beyond the three
  hardcoded CO SNAP roots.
- **PR #373 (`program-certificate`):** preserve `scripts/certify.py` as
  program-level, but extract or reuse its computed verdict logic to emit
  `axiom_oracles.node_comparisons.v1` with explicit `applicable_nodes`,
  per-node `required_dimensions`, parsed `axiom.comparison_report.v2.1`
  identities, report `case_count`, derived conserved disposition counts, and
  full four-key pins. It must pin the exact dispositions validator and
  hash-bind each disposition document named by a report. A program pass cannot
  be projected onto every node.
- **PR #372 (`exercise-census`):** land the generated per-suite
  varied/constant census and its drift check; emit exact report identity,
  no contested report owners, `binding_defects: []`, cardinality-or-full
  reconciliation, positive case counts, and dimension cardinalities bounded
  by cases scanned.
- **PR #375 (`bridge-manifests`):** land explicit bridge declarations and audit
  metadata so the census can emit both `bridge_declared: true` and
  `bridge_audited: true`. The node harness deliberately counts a required
  bridged dimension as zero fidelity even when audited.
- **PR #379 (`evidence-validator`):** land exact report/chunk binding, parsed
  committed rows, exact `axiom_oracles.dispositions.v1` kind validation,
  disposition-file validation, and full comparison-verdict reconciliation.
  Its producer output must retain the exact `apply_dispositions` block and
  expose a hash-bound disposition pointer for the node projection.
  Cardinality is sufficient for the census interface but not for a comparison
  row's `reconciliation: full`.
- **Executable producer (`autogo/executable-producer`):** land the sign-only CI
  job and make its existing
  `axiom_oracles.executable_receipt.validate_executable_receipt` importable.
  Add a separate
  `axiom_oracles.node_executable.v1` adapter that actually invokes
  `validate_executable_receipt`, derives `covered_nodes` only from hash-bound
  golden-output legal-ID bindings, hash-binds the loaded validator bytes, and
  carries the exact four-file `trust_roots` map derived from the manifest.
  Emit the exact adapter/validator provenance strings. Do not replace the
  parked receipt with a simplified node receipt.
- **Certification workflow and governance:** freeze the certification protocol
  before candidate SHAs are known. Emit
  `axiom_oracles.certify_nodes.run.v1` with governed repository, workflow,
  event, and ref identity, full pins, and the exact six candidate input hashes.
  Source `axiom_oracles.certify_nodes.governance.v1` from a separately
  controlled verifier checkout/ref, not a candidate-controlled CLI path. Its
  allowlists and unique `verified_runs` row must bind the run ID,
  `certified_at`, the exact run-manifest SHA-256, workflow/checker SHAs, and the
  identical six hashes. Governance is an external policy input and must not
  become a candidate-hashed artifact.
- **Node index:** generate `axiom_oracles.node_certification_index.v1` with
  `producer.mode: computed`, artifact identity, target presentation, and exact
  roots, suites, and legally required dimensions for every node in each
  resolved subgraph. It must contain no verdict or override field, and its
  per-node suite/dimension declarations must reconcile with the comparison
  producer.

## Current interface gaps

At the time of this contract, real nodes remain fail-closed:

- Engine #115 provenance is not yet present in the published artifacts used by
  this harness, and published artifacts must also carry the new dependency
  graph and exact vintage pins.
- PR #400 currently emits a program-wide aggregate for three hardcoded CO SNAP
  roots and no node-to-root declaration. At its parked head, the Colorado state
  root has zero pending, while 7 CFR 273 has 23 and 7 USC chapter 51 has 267. It
  has no Title 26 root for the example node and no per-root independently
  comparable rulespec/corpus pin object.
- PR #373 computes program verdicts, not node/subgraph verdicts, and does not
  yet emit the double-entered node applicability, parsed report projection,
  pinned dispositions-validator identity, or disposition-document pointer.
- PR #372 measures suite evidence but does not declare which dimensions are
  legally required for a specific node. The current Additional Medicare census
  evidence is not yet a bound, cardinality-reconciled, varied node-fidelity
  producer.
- PR #375's historical `bridged-through` category describes construction, not
  independent exercise; it cannot satisfy this fidelity rule.
- PR #379 supplies suite-level binding and reconciliation but no node/suite
  applicability projection; its validated disposition artifact still needs to
  feed the node projection with an exact byte identity.
- The parked executable branch supplies the rich validator and stranger-path
  receipt contract, but no landed producer emits the separate hash-bound
  program-to-node adapter with validator and transitive trust-root hashes.
- No landed production workflow yet sources governance from a separately
  controlled verifier checkout/ref and binds a unique CI run, its timestamp,
  and all six candidate producer byte identities. Passing caller-selected local
  `--governance` bytes alone is not authoritative.

These are producer gaps, not integration defaults. Until each one is filled,
the node is omitted and the result document records the namespaced fail-closed
reason.
