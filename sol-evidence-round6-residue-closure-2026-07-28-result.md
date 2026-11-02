# PR #379 — round-6 residue closure

Implemented on the existing `evidence-validator` branch without running a
population suite or changing a committed comparison report.

## Residue 1 — permuted matched-value drift

`full` evidence now carries a domain-separated, order-independent
`case_verdicts_sha256` commitment in its versioned chunk index. The commitment
binds each exact `(case_id, concept, outcome, left, right)` record, so aggregate
totals remain independently reproducible while case/value association can no
longer be permuted.

The generic index generator treats that commitment as immutable execution
identity. Fresh full-corpus producers and the immutable-source migration replay
can create it; an implicit rebind cannot bless changed semantics. The live ECPS
index was replayed from `6c4f17bfe6dc8224ee8251401fe0247b1117a25b`;
report and chunk bytes did not change.

Killed mutant:

- `test_permuted_matched_case_values_must_reconcile_with_case_identity`
  reproduces the exact round-6 witness: it swaps both amount and eligibility
  `l/x` pairs between `ecps-spm-50666` and `ecps-spm-50669`. Aggregate and
  content reconciliation remain clean, but the independent per-case identity
  fails and the evidence leg becomes unbound.

## Residue 2 — exact `r` semantics

The shared contract is now:

- `r = null`: case-level agreement is unmeasured;
- exact `r = 100`: full agreement;
- finite `0 <= r < 100`: measured non-full agreement.

Evidence validation applies strict `[0,100]` bounds and exact equality at
verdict-derived `0/100` endpoints. Six-decimal/IEEE representation tolerance is
retained only for interior fractional rates. Fresh compaction and migrated
historical replay derive `r` from stored verdict counts, so neither trusts a
near-endpoint stored rate.

Both dashboard consumers now use a single tri-state helper. Unmeasured rows are
excluded from triangulation rather than classified as disagreement, and the
case table no longer labels them as agreement.

Killed mutants:

- `test_full_agreement_rate_must_be_exact_at_semantic_boundary` rejects the
  exact `r=99.9999995` witness.
- `test_dashboard_match_rate_is_bounded_even_without_full_verdicts` now also
  rejects `r=100.0000005`.
- `test_dashboard_case_agreement_is_tristate_at_exact_boundary` pins the
  dashboard boundary: `100 → true`, `99.9999995 → false`, `null → null`.

## Verification

| Gate | Result |
| --- | --- |
| Full focused evidence + census mutants (`test_certification_mutants.py`, `test_regenerate_migrated_compact_rows.py`, `test_run_comparison.py`, `test_exercise_census.py`) | 110 passed |
| Bot no-op mutant | 1 passed |
| Migrated replay `--check` | ECPS `bound/full` over 1,072 cases; QC `bound/cardinality` over 856 |
| Chunk-index `--check` | both versioned corpora OK |
| Exercise census `--check` | up to date |
| Certificate `--check` | up to date |
| Dashboard overview `--check` | 213 reports OK |
| Bridge-manifest validator | 0 errors; 4 pre-existing audit-debt findings |
| Dashboard exact-boundary Node test | passed |
| Ruff, compileall, branch/cumulative diff whitespace | passed |

The existing dashboard loader-equivalence test could not acquire `esbuild`
because this sandbox cannot resolve the npm registry. A full dashboard build
could not start because the checkout has no installed `next` binary. The new
dependency-free Node boundary test passed; these are environment limitations,
not test suppressions.

The generated `us-co/snap` certificate remains honest: the reference leg is
clean `bound/full` with 2,143 matches, one explained mismatch, and zero
unexplained; the reality leg is clean `bound/cardinality` with 856/856 matches.
Computed conformance remains true, while overall certification remains
unavailable on the pre-existing exercise/bridge blocker.

## Judgment calls

- The matched-value commitment belongs in the versioned evidence index, not the
  dashboard report. Aggregate reports intentionally omit matched case rows, and
  the standing order prohibited changing committed reports.
- The dashboard is tri-state rather than epsilon-aware. Full agreement is an
  exact semantic endpoint, while tolerance remains appropriate only for
  representational drift in interior derived percentages.
- The inherited absolute-value Δ rendering and the review's optional aggregate
  fields/true weighted-row follow-ups are outside these two category-(a)
  residues and were not changed.

## Publication

Local implementation commits:

- `9aed1431` — bind matched verdict values to case identity;
- `4e023fc9` — align exact match-rate semantics across evidence and dashboard.

The branch could not be published from this environment. Two normal
fast-forward push attempts failed before authentication because the sandbox
could not resolve `github.com`. The connected GitHub interface exposed an
atomic Git-data alternative, but both orchestrated and direct blob writes were
rejected by its write gate. No partial remote commit or ref update occurred.

PR #379 was re-read successfully and remained open, unmerged, and pointed at
the pre-fix `336b0a1b` head. Its description was deliberately left unchanged
because the fix commits are not yet present on the remote branch.

The exact body addition ready for publication after the branch is pushed is:

```markdown
## Residues closed

- Permuted matched-value drift is closed by a per-case verdict-identity
  commitment. Mutant:
  `test_permuted_matched_case_values_must_reconcile_with_case_identity`.
- The `r` boundary now has exact endpoint semantics and a tri-state dashboard
  consumer. Mutants:
  `test_full_agreement_rate_must_be_exact_at_semantic_boundary`,
  `test_dashboard_match_rate_is_bounded_even_without_full_verdicts`, and
  `test_dashboard_case_agreement_is_tristate_at_exact_boundary`.
- Full focused evidence/census mutant battery: 110 passed. Bot no-op mutant:
  1 passed. Replay, index, census, certificate, dashboard-overview, direct
  Node boundary, Ruff, compileall, and whitespace checks pass.

The PR remains open and unmerged for the standing review flow.
```

Remaining delivery action: publish the committed `evidence-validator` branch,
append that section to PR #379, and re-confirm the PR remains open and
unmerged.
