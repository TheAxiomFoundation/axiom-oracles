# Autogo node certification integration

## State

- Branch: `autogo/harness-integration`.
- Base: merged local `origin/main` at `315c7dc9`; shell DNS remains unavailable.
- The authoritative generated-only entry shape and six critical-path holes were
  read from the ops repository's `origin/launch/certified-nodes` ref at
  `187f8e72`.
- Upstream producer branches remain parked and will be inspected, not merged or
  rebased.
- Core node evaluator, launch-critical mutants, and final trust-boundary
  hardening are implemented and passing; contract reconciliation is in final
  review.

## Done

- Read the closure-sprint discipline, repository guidance, task brief, and
  certified-nodes contract.
- Created this dedicated worktree from `origin/main`.
- Audited `program-certificate` / PR #373, `closure-universes` / PR #400, the
  #372/#375/#379 census/evidence stack, engine #115's parked node annotations,
  and the parked executable producer without merging or rebasing them.
- Implemented `scripts/certify_nodes.py`: transitive node subgraphs, strict
  provenance, subgraph-wide exact-root closure and comparison applicability,
  parsed and reconciled comparison reports, report-to-census case cardinality,
  dimension-level exercise, validated-receipt node coverage, hash-bound
  validator and transitive receipt trust roots, separately governed and
  run-recorded workflow provenance, exact run/candidate-producer input binding,
  deterministic YAML, atomic writes, byte-exact `--check`, manual-entry drift,
  partial-run preservation, and decertification.
- Added six committed mutant inputs plus green, missing-producer, bridge-audit,
  comparison-error, dependency-cycle, bridged-dimension, foreign-report,
  foreign-receipt, governance, path-escape, impossible-cardinality,
  duplicate/vacuous-root, CRLF, output/evidence alias, unrecorded-run, malformed
  applicability/coverage, dependency-root pending, partial census, validator
  absence/mutation, receipt-command failure, trust-root mutation, contested
  report ownership, protected-validator output aliasing, and two-node projection
  coverage. The complete fixture passes the real parked executable validator.
  Focused validation: 45 tests pass; Ruff and `git diff --check` pass.
- Repository-wide validation reached 2,299 passing and 70 skipped; its sole
  failure was `npx` attempting a network download while DNS was unavailable.

## Next

- Finish the independent contract audit and commit `docs/autogo-contract.md`.
- Re-run the focused suite from a clean archive and repository-wide validation.
- Commit the final ledger, push if possible, open the requested draft pull
  request, and write the closure-sprint output report.
