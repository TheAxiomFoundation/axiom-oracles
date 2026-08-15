# Execution-evidence validator — result

Issue: TheAxiomFoundation/axiom-oracles#378
Branch: `evidence-validator` (based on `bridge-manifests`)
Starting commit: `2778fa1764cc01f0cf10ad64ac89933df16b489a`
Implementation commit before this report:
`1dfdda507fb3fd63e0c6aec6e512972cd246240d`
Date: 2026-07-27

## Result

The execution-evidence validator is implemented, integrated, regenerated, and
green under every requested gate.

The `us-co/snap` certificate remains honest:

- `conformant: true`
- reference `co-snap-ecps`: clean, `binding: bound`,
  `reconciliation: full`
- reality `co-snap-qc`: clean, `binding: bound`,
  `reconciliation: cardinality`
- `certified.state: unavailable` and `exercised: false` remain unchanged in
  meaning because the existing closure/executable premises are still attested
  and the bridge audit is incomplete. No thresholds or verdict rules were
  weakened to preserve conformance.

No push was made.

## What was built

### Importable validator

`axiom_oracles/evidence.py` now provides:

- `validate_suite_evidence(report_path) -> EvidenceReport`
- `validate_chunk_binding(...)` for the census's lightweight pass
- `build_chunk_index(report_path)`
- exact SHA-256/report identity helpers
- immutable `EvidenceReport` and `EvidenceChunk` result types

Strict validation:

- parses the report and every `chunk-*.json` for its suite;
- rejects non-object reports, unsafe suite path components, missing/invalid
  summary counts, non-conserving counts, invalid `case_count`, malformed JSON,
  non-standard `NaN`/`Infinity`, and overflowed non-finite numbers;
- validates every compact row's required `id`, `r`, `h`, and `m` fields;
- validates optional `i` and `v` arrays when present;
- requires compact mismatch/verdict concept names and input names to be
  non-empty strings while leaving compared JSON values unconstrained;
- treats integer and string IDs by their textual identity, so `1` and `"1"`
  cannot evade duplicate detection;
- rejects duplicate IDs within a source or across inline and chunk sources;
- surfaces unreadable reports/chunks/indexes as defects rather than raising;
- separates content defects from binding defects while exposing their ordered
  union as `EvidenceReport.defects`.

### Honest reconciliation

The validator records exactly one of:

- `full`: every parsed case stores complete per-comparison verdict evidence.
  Compact `v` entries count matches and compact `m` entries count mismatches;
  recognized inline shapes are `matched`/`match` booleans or complete
  `matches` plus `mismatches`. All three report summary counts are recomputed.
- `cardinality`: chunks contain well-formed cases but no verdict evidence at
  all. Only `comparison_count == chunk row count` is established, while the
  report summary must still conserve.
- `none`: the stored shape supports neither claim.

There is no fallback laundering:

- explicit mismatch evidence without matched verdict rows is partial evidence
  and yields `none`, not `cardinality`;
- a malformed row cannot become a passing cardinality claim;
- an explicit empty `v: []` remains meaningful for a full-evidence case with
  zero matches;
- the QC shape, which omits `v` and has empty `m`, remains honestly
  cardinality-only.

### Versioned report/chunk binding

The new schema is `axiom_oracles.chunk_index.v1`:

```json
{
  "schema_version": "axiom_oracles.chunk_index.v1",
  "report_path": "dashboard/public/data/report.json",
  "report_sha256": "<exact report bytes>",
  "chunks": [
    {
      "name": "chunk-0.json",
      "sha256": "<exact chunk bytes>",
      "cases": 500
    }
  ]
}
```

The validator requires exact report path and report SHA, an exact descriptor
set for every actual chunk, valid descriptor names, unique descriptor names,
exact chunk SHAs, and exact row counts. Optional legacy display metadata is
retained, but it has no binding authority.

A missing, legacy, malformed, foreign, or stale index returns
`binding: unbound` with a specific binding defect. It does not abort census
generation.

### Generator and refresh trust boundary

`scripts/generate_chunk_indexes.py`:

- generates the initial v1 index only after content validation succeeds and
  reconciliation is not `none`;
- supports deterministic `--check`;
- has a guarded one-time `--strip-inline-mirrors` migration;
- refuses to rebind changed report path/SHA or chunk descriptors on an
  existing v1 corpus.

The last rule is important. Once inline mirrors are removed, aggregate counts
alone cannot prove that replacement chunks came from the same execution.
Therefore `scripts/run_comparison.py`, while it still holds the full case
corpus, now:

1. merges dispositions;
2. compacts and writes fresh chunks;
3. slims the dashboard report to remove inline mirrors;
4. writes the exact report;
5. builds and validates the new bound index.

Skip/re-emit runs that did not execute preserve the existing versioned report,
chunks, and index byte-for-byte. The generic generator then performs an
idempotent verification rather than blessing a no-execution refresh.

`scripts/emit_case_artifacts.py` preserves an existing versioned corpus when a
skip run has no full cases, and emits explicit `v: []` when a true full-evidence
case has zero matches. `scripts/regenerate_all.sh` and
`scripts/commit_refreshed_report.sh` run the generator fail-closed.

### Colorado migration

Both Colorado reports duplicated IDs inline and in chunks. Literal
cross-source uniqueness therefore required making chunks authoritative and
setting the dashboard reports' inline `cases` arrays to empty. Truncation
metadata now states that zero case rows are shown inline.

Final identities:

| Suite | Report SHA-256 | Chunk cases | Summary comparisons | Match | Mismatch | Result |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `co-snap-ecps` | `696efc8883e20afcc80ec69345b46ab88127f50f4a104757c6bc0a903a268a90` | 1,072 | 2,144 | 2,143 | 1 | `bound/full` |
| `co-snap-qc` | `1557af0077ac0a38c63c5318441c9354b30aceedd8d25fb9cff8fd3bb150517d` | 856 | 856 | 856 | 0 | `bound/cardinality` |

ECPS has 2,144 stored verdicts across 1,072 household cases. QC has one
verdict-free compact row per comparison, so cardinality is the strongest
honest claim.

The dashboard case loader accepts both v1 descriptor arrays and the remaining
legacy numeric `chunks` indexes.

### Census and certificate integration

`scripts/exercise_census.py` reuses its existing census-wide chunk read to
record, per row:

- `binding`
- specific `binding_defects`
- `reconciliation`, deliberately capped at `cardinality|none`
- exact report path/SHA
- chunk SHA and raw row cardinality

Missing and legacy indexes remain visible as unbound findings without blocking
census generation. Unsafe suite names cannot traverse outside the census case
root. A full census build covered 213 suites in approximately 1.5 seconds
during implementation.

`scripts/certify.py` calls the strict validator only for suites in `PROGRAMS`.
A clean leg now requires:

- no evidence defects;
- `binding: bound`;
- `reconciliation != none`;
- all pre-existing count/error/disposition conditions.

The leg records binding, reconciliation, and evidence case count, and the
certificate cites the chunk index by SHA. The exercise block independently
compares the census row's report path and SHA against the certificate's own
registry entry and rejects either divergence.

Malformed or unreadable nested report shapes are normalized into specific leg
defects instead of crashing certificate generation.

### Durable mutants

Committed synthetic fixtures under `tests/fixtures/evidence/` cover:

- dummy metadata with asserted counts;
- an uncontested report pointed at foreign chunks;
- duplicate case IDs;
- malformed compact rows;
- stale index report SHA;
- partial mismatch evidence with no matched verdict rows;
- non-standard/non-finite JSON;
- positive bound/full and bound/cardinality controls;
- a synthetic contested-report census, replacing the live
  `nyc-synthetic` dependency.

Additional mutants prove certificate consumption, independent census
report-path and report-SHA divergence, malformed nested report shapes,
non-string compact identifiers, generic stale-rebind refusal, producer-side
fresh chunk emission, deterministic index ordering with input/output slots,
and skip-run byte preservation.

## Alignment with PR #368

PR #368 owns main-side execution attestation: whether an engine executed,
engine identity, output surfaces, comparison/error counts, and output
artifacts. This change does not duplicate that scope.

This component uses compatible vocabulary (`schema_version`, `case_count`,
`comparison_count`) but defines `binding` narrowly as exact aggregate-report
to case-chunk identity. Documentation explicitly distinguishes evidence
binding from execution attestation.

The cost split also follows the same active-universe principle:

- census-wide: one lightweight cardinality/binding pass;
- certificate `PROGRAMS`: strict full row/verdict validation.

## Bot and CI integration

- CI now runs `scripts/generate_chunk_indexes.py --check`.
- The affected-refresh bot regenerates/verifies indexes in the correct order.
- Its asserted origin-tip gate list includes the new index check.
- The scheduled regeneration path validates versioned evidence fail-closed.
- No `SEED_DIRS` change was needed: the new Python files are already under the
  seeded `scripts/` and `axiom_oracles/` trees, while every generated index and
  report is already covered by the fully copied
  `dashboard/public/data` seed. The no-op mutant confirms this.

## Commits

```text
ff5ce221 Document evidence-validator execution plan
5a18f3c3 Record evidence validation contract
7d6cd495 Add strict execution evidence validator
6c4f17bf Tighten evidence reconciliation edge cases
a753d092 Bind Colorado chunk evidence to reports
3d5bf258 Record evidence binding in exercise census
1fd6a701 Require bound evidence for certification
ba4b5054 Regenerate evidence-aware census and certificate
de0c8497 Surface unreadable reports as certificate defects
4df115db Harden evidence refresh and malformed inputs
1dfdda50 Record final evidence validator gates
```

## Gate outputs

### Ruff

Command:

```text
/opt/homebrew/bin/ruff check axiom_oracles/evidence.py \
  scripts/generate_chunk_indexes.py scripts/exercise_census.py \
  scripts/certify.py scripts/emit_case_artifacts.py \
  scripts/run_comparison.py tests/test_certification_mutants.py \
  tests/test_exercise_census.py tests/test_run_comparison.py \
  tests/test_commit_refreshed_report.py
```

Output:

```text
All checks passed!
```

### Versioned chunk indexes

Command:

```text
/opt/homebrew/bin/python3.13 -B scripts/generate_chunk_indexes.py --check
```

Output:

```text
OK co-snap-ecps: bound/full
OK co-snap-qc: bound/cardinality
```

### Exercise census

Command:

```text
/opt/homebrew/bin/python3.13 -B scripts/exercise_census.py --check
```

Output:

```text
exercise census up to date
```

### Certificate

Command:

```text
/opt/homebrew/bin/python3.13 -B scripts/certify.py --check
```

Output:

```text
certificates up to date
```

### Bridge manifests

Command:

```text
/opt/homebrew/bin/python3.13 -B scripts/validate_bridge_manifests.py
```

Output:

```text
FINDING co-snap-populace.yaml: bridged binding [4] covered_by entry 'rulespec-us us-co/regulations/10-ccr-2506-1/4.407.4.test.yam' is not verifiable from this repository (cross-repo evidence — audit debt)
FINDING co-snap-populace.yaml: population pin required but dashboard/public/data/axiom-policyengine-co-snap-ecps.json carries no dataset identity — the lane must stamp the exact populace revision + sha (fiit-ecps shows the pattern)
FINDING co-snap-populace.yaml: 3 binding(s) audit=partial — audit debt
FINDING co-snap-populace.yaml: completeness=unverified — input-catalog verification pending (engine main's metadata.input_catalog)
1 manifest(s): 0 error(s), 4 finding(s)
```

These four findings predate #378 and remain honest audit debt. The gate exits
zero.

### Required certification/bot selection

Command:

```text
/opt/homebrew/bin/python3.13 -B -m pytest -q tests/ \
  -k 'certification or commit_refreshed'
```

Output:

```text
51 passed, 1854 deselected in 208.56s (0:03:28)
```

This includes `test_no_changes_second_run_is_a_noop`.

### Focused validator/census/producer suite

Command:

```text
/opt/homebrew/bin/python3.13 -B -m pytest -q \
  tests/test_certification_mutants.py \
  tests/test_exercise_census.py \
  tests/test_run_comparison.py
```

Output:

```text
........................................................................ [ 94%]
....                                                                     [100%]
76 passed in 2.35s
```

### Shell and diff checks

Commands:

```text
bash -n scripts/commit_refreshed_report.sh scripts/regenerate_all.sh
git diff --check
git status --short
```

All exited zero; the first two produced no output, and `git status --short`
was empty before this report file was added.

### Derived-artifact gates

The full affected-refresh verification sequence also passed:

```text
Dispositions are consistent with the committed dashboard data
vacuous-gate OK: 136 configs oracle-backed; 213 suites, 18 executable surfaces, 83 suite(s) awaiting provenance
conformance scoreboard OK: 4 jurisdiction(s), 3 conformant
conformance burn-down OK: 4 series, 49 point(s)
overview OK: 214 reports bundled
exercise census up to date
certificates up to date
```

## What could not be done honestly

The requested destination
`~/TheAxiomFoundation/ops/reviews/sol-evidence-validator-2026-07-27/result.md`
is outside this task's writable roots. The sandbox grants read-only access
outside the `oracles-evidence` worktree and provides no approval path.

This file is therefore the exact fallback copy inside the authorized worktree.
The placement was attempted and failed exactly as follows:

```text
cp: /Users/maxghenis/TheAxiomFoundation/ops/reviews/sol-evidence-validator-2026-07-27/result.md: Operation not permitted
```

No permission boundary was bypassed. The existing external `result.md` remains
zero bytes. Apart from that filesystem placement, the implementation,
generated artifacts, commits, and all requested checks are complete.
