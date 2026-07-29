# Autogo node certification integration

## State

- Branch: `autogo/harness-integration`.
- Base: merged local `origin/main` at `315c7dc9`; shell DNS remains unavailable.
- The authoritative generated-only entry shape and six critical-path holes were
  read from the ops repository's `origin/launch/certified-nodes` ref at
  `187f8e72`.
- Upstream producer branches remain parked and will be inspected, not merged or
  rebased.
- Core node evaluator, launch-critical mutants, and adversarial integration
  hardening are implemented and passing; contract reconciliation remains.

## Done

- Read the closure-sprint discipline, repository guidance, task brief, and
  certified-nodes contract.
- Created this dedicated worktree from `origin/main`.
- Audited `program-certificate` / PR #373, `closure-universes` / PR #400, the
  #372/#375/#379 census/evidence stack, engine #115's parked node annotations,
  and the parked executable producer without merging or rebasing them.
- Implemented `scripts/certify_nodes.py`: transitive node subgraphs, strict
  provenance, exact-root closure, parsed and reconciled comparison reports,
  dimension-level exercise, validated-receipt node coverage, separately
  governed workflow provenance, exact producer-input binding, deterministic
  YAML, atomic writes, byte-exact `--check`, manual-entry drift, partial-run
  preservation, and decertification.
- Added six committed mutant inputs plus green, missing-producer, bridge-audit,
  comparison-error, dependency-cycle, bridged-dimension, foreign-report,
  foreign-receipt, governance, path-escape, impossible-cardinality,
  duplicate/vacuous-root, CRLF, output-alias, and two-node projection coverage.
  Focused validation: 30 tests pass; Ruff and `git diff --check` pass.
- Repository-wide validation reached 2,299 passing and 70 skipped; its sole
  failure was `npx` attempting a network download while DNS was unavailable.

## Next

- Reconcile and review `docs/autogo-contract.md` against the hardened v1
  schemas and record what every parked producer must add.
- Re-run independent review and repository-wide validation after reconciliation.
- Commit the final ledger, push if possible, open the requested draft pull
  request, and write the closure-sprint output report.
