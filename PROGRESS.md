# PR #427 — real producer integration

## State

- Branch: `autogo/harness-integration`; rewritten onto `origin/main`
  `dd4ec472acd711c6481c381c20bcce034f3ced6b` (verified as GitHub `main` on
  2026-08-20).
- Terminal `git fetch` is DNS-blocked, but the local remote-tracking ref and the
  GitHub connector report the same current `main` commit.
- PR #427 is open, draft, unmerged, and still points at the pre-rewrite head
  `dc8163b0b47d47981ea2b19771deab668e35bf38` until publication.
- The pre-rewrite tip is preserved locally as
  `autogo-harness-integration-pre-rewrite`.
- The legacy speculative harness has been replaced by a registry-driven
  implementation against the landed certificate, evidence/census, closure,
  and executable producer interfaces.
- Canonical output is five refused candidates (two DK, three CO), zero
  certified nodes. The sidecar is directly compatible with axiom-api's
  `axiom-validation-evidence/1` queue projection.
- Final report target: the closure-sprint `w427-rebase.result.md` output.

## Done

- Read the closure-sprint discipline and confirmed the repository has no root
  `CLAUDE.md` or applicable `AGENTS.md`.
- Read the GitNexus exploring skill; its MCP server is unavailable, so source
  exploration will use direct repository inspection.
- Verified current GitHub `main`, inspected PR #427, attempted the required
  terminal fetch, and recorded the DNS limitation.
- Rewrote the branch pointer to current main while preserving the old tip and
  only restored the 28 harness-specific code, documentation, test, and fixture
  paths (no stale-main reversions).
- Audited the real producer registry and downstream ops/API contracts. Bound
  five exact graph candidates, rejected CO comparison aliases, and recorded
  the ops/API nonempty-entry `mode` mismatch without weakening the ops output.
- Implemented `scripts/certify_nodes.py`, the explicit candidate adapter,
  ops-schema-exact empty ledger, per-candidate refusal/API queue sidecar, and
  distinct `source_reproduction` / `release_receipt` handling.
- Kept provision rooting computed-or-refused with the missing producer named
  as `TheAxiomFoundation/axiom-rules-engine#136`.
- Replaced the old speculative fixtures with eight focused real-interface and
  mutant tests; focused battery: `8 passed`.
- Rewrote `docs/autogo-contract.md` around the landed interfaces and documented
  every material divergence from the pre-producer contract.

## Next

- Commit the integrated generator, contract, outputs, and focused mutants.
- Run certificate, closure, generator, exact mirror, lint/format, and full
  pytest batteries; record exact counts.
- Commit the final progress/battery ledger, publish the rewritten branch, and
  update PR #427's description without merging it.
