# Autogo node certification integration

## State

- Branch: `autogo/harness-integration`.
- Base: local `origin/main` at `f8ea6027` (GitHub DNS fetch is unavailable).
- The authoritative generated-only entry shape and six critical-path holes were
  read from the ops repository's `origin/launch/certified-nodes` ref at
  `187f8e72`.
- Upstream producer branches remain parked and will be inspected, not merged or
  rebased.
- Core node evaluator and the full launch-critical mutant set are implemented
  and passing; contract reconciliation and broader validation remain.

## Done

- Read the closure-sprint discipline, repository guidance, task brief, and
  certified-nodes contract.
- Created this dedicated worktree from `origin/main`.
- Audited `program-certificate` / PR #373, `closure-universes` / PR #400, the
  #372/#375/#379 census/evidence stack, engine #115's parked node annotations,
  and the parked executable producer without merging or rebasing them.
- Implemented `scripts/certify_nodes.py`: transitive node subgraphs, strict
  provenance, exact-root closure, per-suite conformance, dimension-level
  exercise, receipt/pin validation, deterministic YAML, structured rejection
  reasons, byte-exact `--check`, manual-entry drift, and decertification.
- Added six committed mutant inputs plus green/missing-producer/bridged
  coverage. Focused validation: 13 tests pass; Ruff and `git diff --check` pass.

## Next

- Reconcile and review `docs/autogo-contract.md` against the implemented v1
  schemas and record what every parked producer must add.
- Run independent adversarial review, focused and repository-wide validation.
- Commit the final ledger, push if possible, open the requested draft pull
  request, and write the closure-sprint output report.
