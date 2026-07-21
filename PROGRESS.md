# PROGRESS — Germany dual-oracle comparison suites

## State

- Branch: `feat/de-dual-oracle-suites`.
- Starting point: `13d064d`, including EUROMOD `extra_columns` support.
- Architecture discovery is complete. The implementation will instantiate one
  direct EUROMOD-to-GETTSIM synthetic comparison, using the repository's
  pairwise v2 report, suite registry, canonical grid, and runner registry.
- No DE suite code has been changed yet.

## Done

- Verified the requested branch and clean starting worktree.
- Recorded the supplied DE engine configuration, case-grid facts, uprating,
  aggregation rule, and the three already-filed model findings as requirements.
- Confirmed that the GitNexus MCP index is unavailable in this session; local
  source and Git history will be used for architecture discovery.
- Confirmed that bridge-registry YAML is PolicyEngine-specific; the shared DE
  concepts belong in `axiom_oracles/config/concept_mappings.yaml` with explicit
  `euromod` and `gettsim` targets.
- Confirmed that the smallest repository-idiomatic integration is a registered
  in-process dual runner. The script runs in the GETTSIM environment while the
  existing EUROMOD adapter delegates to `EUROMOD_PYTHON`.
- Confirmed two repository conventions that supersede requested terminology:
  filed engine findings use the supported `upstream_engine_gap` disposition,
  with model attribution in evidence; generated committed evidence is the
  dashboard report plus manifest because dated `reports/*.json` are ignored.
- Read the supplied parity-grid source and report and recorded the exact 13-case
  order, engine projections, target reductions, anchor values, and 12 raw
  differences covered by the three filed findings.

## Next

1. Implement and test the DE projections, mappings, canonical grid, monthly
   EUROMOD output convention, suite config, and pure contracts.
2. Implement the registered dual runner, GETTSIM household reductions, live
   skip/re-emission behavior, and provenance.
3. Run both live engines and commit the generated dashboard report and the
   three expected dispositions.
4. Add live-gated anchors for each engine, update the DE playbooks, and
   document the realized lane.
5. Run Ruff plus the full and GETTSIM-specific test commands.
6. Finalize this ledger and write the handoff report to `FINAL_REPORT.md`
   (no separate output path was provided), without pushing or opening a pull
   request.
