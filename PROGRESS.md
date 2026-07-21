# PROGRESS — Germany dual-oracle comparison suites

## State

- Branch: `feat/de-dual-oracle-suites`.
- Starting point: `13d064d`, including EUROMOD `extra_columns` support.
- Architecture discovery is in progress. The implementation will follow the
  established UK/BE comparison, runner, report, test, and live-skip patterns.
- No DE suite code has been changed yet.

## Done

- Verified the requested branch and clean starting worktree.
- Recorded the supplied DE engine configuration, case-grid facts, uprating,
  aggregation rule, and the three already-filed model findings as requirements.
- Confirmed that the GitNexus MCP index is unavailable in this session; local
  source and Git history will be used for architecture discovery.

## Next

1. Study bridge mappings/registry, UK and BE comparison configs, runner
   registration, UK worker history, live-test skip gates, and playbook section 6.
2. Inspect the supplied 13-household parity-grid design and real-run report.
3. Implement and test the DE projections, mappings, dual runner, suite config,
   expected dispositions, and live anchors in coherent committed steps.
4. Run both live engines, commit generated reports, complete documentation, and
   run Ruff plus the full and GETTSIM-specific test commands.
5. Finalize this ledger and write the handoff report to the requested output
   artifact without pushing or opening a pull request.
