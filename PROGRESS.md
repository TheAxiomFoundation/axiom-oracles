# Autogo node certification integration

## State

- Branch: `autogo/harness-integration`.
- Base: local `origin/main` at `f8ea6027` (GitHub DNS fetch is unavailable).
- The authoritative generated-only entry shape and six critical-path holes were
  read from the ops repository's `origin/launch/certified-nodes` ref at
  `187f8e72`.
- Upstream producer branches remain parked and will be inspected, not merged or
  rebased.

## Done

- Read the closure-sprint discipline, repository guidance, task brief, and
  certified-nodes contract.
- Created this dedicated worktree from `origin/main`.

## Next

- Inventory the parked producer interfaces and existing test conventions.
- Implement and test `scripts/certify_nodes.py`, including all six required
  rejecting mutants.
- Document `docs/autogo-contract.md`, validate, push if possible, and open the
  requested draft pull request.
