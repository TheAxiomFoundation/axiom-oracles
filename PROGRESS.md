# PROGRESS — Germany dual-oracle comparison suites

## State

- Branch: `feat/de-dual-oracle-suites`.
- Starting point: `13d064d`, including EUROMOD `extra_columns` support.
- Architecture discovery is complete. The implementation will instantiate one
  direct EUROMOD-to-GETTSIM synthetic comparison, using the repository's
  pairwise v2 report, suite registry, canonical grid, and runner registry.
- The engine-neutral DE concepts, exact 13-case projections, canonical grid,
  and monthly/annual output contracts are implemented and pure-tested.
- The `gettsim-synthetic-compare` runner, DE comparison configuration, and
  three filed-finding dispositions are implemented and focused-tested. The
  next coherent step is the real two-engine run and committed report.

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
- Added six DE comparison concepts and explicit EUROMOD/GETTSIM mappings at a
  one-cent absolute tolerance, including `tin_s` versus GETTSIM income tax plus
  Soli and a monthly Kindergeld contract.
- Added the 13-case `de-worker-dual-oracle` suite with exact `yemmy`/hours/
  months/`drgn1` EUROMOD rows, exact 61/56 GETTSIM gross mirrors, joint and
  single-parent relationships, and `*_y_sn` MAX reduction.
- Added Germany geography support, the PolicyEngine not-comparable prefix, the
  generated `grids/de.yaml`, wheel packaging, and extraction-equivalence tests.
- Kept DE employee SIC legs and `bch00_s` monthly in the EUROMOD adapter while
  leaving `tin_s` annual; a subprocess-contract test pins the behavior.
- Pure verification: Ruff passed on touched Python files; 552 focused tests
  passed (6 live tests deselected). The only output was pre-existing pytest temp
  cleanup warnings on macOS.
- Registered `gettsim-synthetic-compare` as a direct in-process cross-oracle
  runner. It preflights both live engines, executes EUROMOD through the existing
  delegated interpreter and GETTSIM in-process, applies the configured household
  reductions, emits v2.1 provenance/engine metadata, honors `sample_size`, and
  re-emits committed evidence when an engine is unavailable.
- Added `comparisons/de-worker-dual-oracle.yaml` and the three supplied finding
  dispositions. Their selectors cover the expected 9 EUROMOD income-tax rows,
  2 EUROMOD child-benefit rows, and 1 GETTSIM Midijob care-insurance row.
- Kept direct-oracle comparisons out of rulespec dependency inference: the DE
  affected-map entry intentionally has `repos: []`, because neither side is an
  Axiom rulespec implementation.
- Tightened unavailable-engine behavior so an unsupported or broken GETTSIM
  runtime fails loudly rather than being mistaken for an optional-engine skip;
  empty reports now attribute each unavailable side to the correct engine.
- Focused runner verification: Ruff passed; 102 tests passed. The generated
  affected map and all disposition files validate, with the expected note that
  the DE suite has no committed dashboard report until the next step.
- Added an explicit Germany dashboard route and jurisdiction toggle. The DE
  suite no longer falls through the two-letter `DE` US-state heuristic, and
  GETTSIM now has a first-class engine label in report views.

## Next

1. Run both live engines, validate the exact 66/78 raw matches and 12
   dispositioned rows, and commit the generated report.
2. Add live-gated anchors for each engine, update the DE playbooks, and
   document the realized lane.
3. Run Ruff plus the full and GETTSIM-specific test commands.
4. Finalize this ledger and write the handoff report to `FINAL_REPORT.md`
   (no separate output path was provided), without pushing or opening a pull
   request.
