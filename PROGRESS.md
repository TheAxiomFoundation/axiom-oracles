# Progress

## State

- Branch: `fix/snap-concept-citations`
- Base: `origin/main`
- Scope: publish the already-applied SNAP concept-ID relabeling, verify it, and update the separately pinned report hashes in `TheAxiomFoundation/ops`.
- Guardrails: do not run comparison suites, do not change committed numeric values, and do not touch toolchain, CI, or CODEOWNERS.

## Done

- Confirmed the expected branch and inspected the working-tree scope.
- Confirmed the relabeling is present across the expected source, comparison, report, dashboard, documentation, script, and test files.

## Next

- Independently prove that every pre-existing changed line is only one of the two requested concept-ID substitutions.
- Run the requested pytest suite and distinguish rename-caused failures from unrelated failures.
- Audit statutory and regulatory concept IDs in `case.py` and `concept_mappings.yaml` against the corpus.
- Commit and publish the axiom-oracles PR.
- Recompute the three affected report SHA-256 values in a separate ops worktree, update PR #7's branch, and publish the final report.
