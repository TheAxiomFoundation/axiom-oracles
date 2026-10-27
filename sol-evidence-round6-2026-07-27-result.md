# Value-level evidence reconciliation — round 6 result

Date: 2026-07-27

Branch: `evidence-validator`

Starting commit: `627c08df3bf47b2bac1e4c5dc084e84d3a1c7f37`

Integrated `origin/main`: `0b3f5a70af0ea63728b269e7d6e7657ddbd3bb41`

## Result

**PASS for the requested category-(a) closure and integration.**

Full evidence reconciliation now binds the report's aggregate values to the
chunk-projected verdict values, compact rows are checked against the two
dashboard-visible semantics, and historical migrated values are replayed
through those checks. The counterexample that changed a matched amount from
`0` to `999` while preserving counts is now rejected.

No category-(b) work was implemented. The QC end-to-end mismatch publication
path and root unattended regeneration remain trunk follow-ups.

## Implementation

### Aggregate values

`axiom_oracles/evidence.py` now retains all projected match and mismatch
verdicts while performing full reconciliation and independently derives:

- amount `left_weighted_sum` and `right_weighted_sum`;
- eligibility `left_positive_weight` and `right_positive_weight`; and
- the unit `comparison_weight` supported by the unweighted compact verdicts.

Declared aggregate values must be finite native numbers and agree at
representation tolerance (at least `1e-6`, widened only for four IEEE ULPs).
Concept comparison tolerance is not reused. A report that declares weighted
value fields without reproducible unit comparison weight fails closed.

### Dashboard row semantics

Every compact mismatch row now requires:

- `d = x - l` at representation tolerance when both sides are numeric;
- `d = null` when the sides are nonnumeric; and
- a finite `r` in `[0, 100]` consistent with the row's verdict cardinality.

When `v` is present, `r` must equal
`100 * len(v) / (len(v) + len(m))`. A partial row with a mismatch cannot claim
`r = 100`. Fresh compaction and migrated replay both derive `d` from `l` and
`x` instead of copying a source convention.

### Killed mutants

The full mutant suite includes and kills:

- matched amount `0/0 -> 999/999`, through both aggregate sum defects;
- matched eligibility `false/false -> true/true`, through both positive-weight
  defects;
- omission of aggregate `comparison_weight`;
- isolated `d` drift to `1_000_000_000`;
- isolated `r` drift to `100`;
- out-of-range `r` values; and
- a partial mismatch row falsely claiming `r = 100`.

## Historical replay and live finding

The migrated ECPS and QC chunks were replayed from immutable source commit
`6c4f17bfe6dc8224ee8251401fe0247b1117a25b`. The replay stages its projected
chunks, validates them against the current report, and only then replaces the
derived corpus.

The value-level check found **no live aggregate drift**:

- SNAP benefit: 1,072 comparisons, left sum `37,933.0`, right sum
  `37,996.938652`;
- SNAP eligibility: 1,072 comparisons, 186 left-positive and 186
  right-positive outcomes.

It did surface one honest row-semantic drift before regeneration.
`ecps-spm-50970` stored the historical `l - x` delta
`-1.7000120000000152`; the required dashboard semantic is `x - l`, so trusted
replay regenerated the compact delta as `+1.7000120000000152`. Its row now has
one matched verdict, one explained mismatch, and `r = 50`. The underlying
report values and explained-residual disposition were not tuned.

After replay:

- `co-snap-ecps`: `bound/full`, 1,072 evidence cases;
- `co-snap-qc`: `bound/cardinality`, 856 evidence cases.

The historical matched values are therefore checked against the report's live
aggregates rather than trusted.

## Integration and certificate honesty

Refreshing the remote ref was attempted, but the sandbox could not resolve
`github.com`. The locally cached `origin/main` tip is the verifier-pinned
102-commits-ahead snapshot above, fetched shortly before this round. It was
merged locally in `37058619`.

The merge had exactly one conflict,
`dashboard/public/data/overview.json`. It was resolved only by running
`scripts/generate_dashboard_overview.py`; no generated conflict was edited by
hand. The migrated chunks, chunk bindings, census, and certificate were then
regenerated. The four trailing-space lines in the cumulative branch diff were
also fixed.

The generated `us-co/snap` certificate remains honest:

- computed `conformant.value = true`;
- reference leg: clean `bound/full`, 2,144 comparisons, 2,143 matches, one
  explained mismatch, zero unexplained, weighted mismatch mass `1.0`;
- reality leg: clean `bound/cardinality`, 856 comparisons and 856 matches;
- overall certification remains `unavailable`, with the pre-existing
  exercise-census/unaudited-bridge blocker disclosed.

No report aggregate or certificate threshold was tuned to make a gate pass.

## Verification

| Gate | Result |
| --- | --- |
| `scripts/regenerate_migrated_compact_rows.py --check` | ECPS `bound/full` 1,072; QC `bound/cardinality` 856 |
| `scripts/generate_chunk_indexes.py --check` | both versioned corpora OK |
| `scripts/exercise_census.py --check` | up to date |
| `scripts/certify.py --check` | up to date |
| `tests/test_certification_mutants.py` | 62 passed |
| bot `test_no_changes_second_run_is_a_noop` | 1 passed |
| focused reconciliation/regeneration/comparison suite | 103 passed |
| `scripts/generate_dashboard_overview.py --check` | 213 reports OK |
| `scripts/validate_bridge_manifests.py` | 0 errors; 4 existing audit-debt findings |
| Ruff and compileall on changed implementation paths | passed |
| cumulative `git diff origin/main...HEAD --check` | passed |

The pre-commit graph audit classified the upstream integration as HIGH impact:
138 staged files, 413 indexed symbols, and 11 affected execution processes.
That is expected for the merged state-tax-populace campaign; the evidence
validator, regeneration, mutant, freshness, and bot gates above all passed.

## Local commits

- `5ef927da` — start and commit the round-6 progress record;
- `5cb6ec00` — commit reconciliation analysis and live baselines;
- `35414909` — bind aggregate values and dashboard row semantics;
- `37058619` — merge cached `origin/main` and regenerate evidence.
- `fabdf29f` — commit this round-6 result and the delivery fallback.

All commits are local. Nothing was pushed.

## Delivery

Requested path:
`/Users/maxghenis/TheAxiomFoundation/ops/reviews/sol-evidence-round6-2026-07-27/result.md`.

The copy was attempted and the sandbox rejected it:

```text
cp: /Users/maxghenis/TheAxiomFoundation/ops/reviews/sol-evidence-round6-2026-07-27/result.md: Operation not permitted
```

Per the standing fallback instruction, this report is committed in the
repository as `sol-evidence-round6-2026-07-27-result.md`.
