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
- Legacy harness files have been recovered into the worktree for adaptation;
  they are not yet committed on the new base and still encode speculative
  producer contracts.
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

## Next

- Commit this progress baseline.
- Read the landed certificate registry, program certificates, closure
  universes, strict evidence/census artifacts, and source-reproduction receipt
  schema, plus the ops ledger and axiom-api mirror contract.
- Replace the speculative harness with the real registry-driven generator,
  preserving computed-or-refused provenance and tiered executable evidence.
- Add the three requested mutants, generate the zero-entry ledger and refusal
  sidecar, run focused and full batteries, push, and update PR #427 without
  merging it.
