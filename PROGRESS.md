# PR #427 — real producer integration

## State

- Branch: `autogo/harness-integration`; rewritten onto `origin/main`
  `dd4ec472acd711c6481c381c20bcce034f3ced6b` (verified as GitHub `main` on
  2026-08-20).
- Terminal `git fetch` is DNS-blocked, but the local remote-tracking ref and the
  GitHub connector report the same current `main` commit.
- PR #427 is open, draft, unmerged, and still points at the pre-rewrite head
  `dc8163b0b47d47981ea2b19771deab668e35bf38` pending publication.
- The pre-rewrite tip is preserved locally as
  `autogo-harness-integration-pre-rewrite`.
- The legacy speculative harness has been replaced by a registry-driven
  implementation against the landed certificate, evidence/census, closure,
  and executable producer interfaces.
- The local integration and adversarial hardening are committed through
  `941de4040` (four commits on current main).
- Remote publication is currently blocked: `git push --force-with-lease` cannot
  resolve `github.com`, and two authenticated GitHub blob-write attempts were
  declined before creating any remote object. The remote branch and PR were
  therefore left unchanged.
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
  mutant tests, then expanded the repaired surface to 11 focused tests;
  focused battery: `11 passed`.
- Rewrote `docs/autogo-contract.md` around the landed interfaces and documented
  every material divergence from the pre-producer contract.
- Moved the candidate adapter to root `node-candidates.yaml` so the existing
  `conformance/*.yaml` universe glob cannot mistake it for a report.
- Hardened executable ingestion for current source-reproduction v1, shared
  tiered v2, and the actual public #461 release-only v1 registry/verdict shape;
  bound required tiers to registry policy and release receipts to the exact
  membership-artifact SHA.
- Made provision rooting unconditionally refuse pending a validated engine
  #136 `metadata.nodes` catalog, including when raw graph annotations are
  forged, and required unique program-bound graph membership.
- Added an exact byte snapshot of axiom-api's mirror script and made the mirror
  round-trip mutant mandatory even without a sibling checkout.
- Producer batteries are green: five producer `--check` commands, 273 focused
  producer tests, and 42 supplemental NZ/tariff tests (`315/315` total).
- Final direct checks are green: the five producer drift checks, node-generator
  drift, Ruff format/lint, diff whitespace, and all 11 focused node/mirror
  tests.
- Full pytest battery after the candidate-path repair: `2851 passed, 71
  skipped, 3 failed, 3 warnings in 1633.62s` (27:13). All changed-surface tests
  passed. The three failures are baseline/environment failures independently
  reproduced on untouched `dd4ec472a` with the same Python 3.13 pytest runner:
  Minnesota's installed PolicyEngine formula has a 16.64 residual where the
  test pins 0.81; the installed PolicyEngine parameter tree lacks
  `gov.irs.deductions.itemized.limitation.applies`; and the dashboard loader's
  `npx esbuild` download fails under the sandbox's npm `ENOTFOUND` network
  restriction.

## Next

- Restore GitHub shell connectivity or authorize the authenticated writer,
  then force-with-lease publish the four-commit rewrite and replace PR #427's
  stale speculative description; do not merge it.
- Write the closure-sprint output report with contract divergences, DK/CO
  refusal summaries, exact battery numbers, and remote handoff state.
