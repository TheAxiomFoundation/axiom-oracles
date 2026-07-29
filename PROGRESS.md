# Autogo node certification integration

## State

- Branch: `autogo/harness-integration`.
- Base: merged local `origin/main` at `315c7dc9`; shell DNS remains unavailable.
- The authoritative generated-only entry shape and six critical-path holes were
  read from the ops repository's `origin/launch/certified-nodes` ref at
  `187f8e72`.
- Upstream producer branches remain parked and will be inspected, not merged or
  rebased.
- Core node evaluator, launch-critical mutants, final trust-boundary hardening,
  and the producer integration contract are implemented, committed, and
  validated.
- Publication is locally blocked: `git push` cannot resolve `github.com`, and
  the available GitHub connector rejected write operations. The requested
  draft PR therefore remains unopened.

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
  report ownership, protected-validator output aliasing, recursive/deep
  producer documents, symlink-loop producer paths, and two-node projection
  coverage. The complete fixture passes the real parked executable validator.
  Dispositioned mismatches now require the pinned v1 validator, exact taxonomy,
  a strict/hash-bound source artifact, and exact block recomputation; malformed
  paths/imports/run ids fail with machine reasons. A clean `git archive` of
  `HEAD`, pointed at the real parked executable validator, passes all 54 focused
  tests; Ruff and `git diff --check` pass.
- Wrote and independently reconciled `docs/autogo-contract.md`: all eight input
  envelopes, transitive node scope, exact criterion gates, ledger/result byte
  shapes, 67 stable reasons, six launch-critical mutants, and the concrete
  landing obligations and current gaps for every parked producer.
- Repository-wide validation reached 2,337 passing and 70 skipped; its sole
  failure was `tests/test_dashboard_loader.py::test_loader_equivalence`, where
  `npx esbuild` attempted a registry download while DNS was unavailable.

## Next

- When a GitHub write path is available, push `autogo/harness-integration` and
  open the requested draft pull request.
- Land every producer obligation in `docs/autogo-contract.md` against one
  shared vintage before attempting a production node certification.
