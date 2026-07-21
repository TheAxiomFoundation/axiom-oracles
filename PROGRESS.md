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
  three filed-finding dispositions are implemented and focused-tested.
- The real two-engine report is committed, both live test gates pass, and the
  realized lane is documented. Full-repository validation and the final
  handoff report remain.

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
- Ran the full 13-case lane against live EUROMOD J2.0+ / DE_2025 and GETTSIM
  1.2.1 at policy date 2025-06-30. The run produced 78 comparisons: 66 exact-
  tolerance matches, 12 expected amount differences, and 0 engine errors.
- Published the dispositioned v2.1 dashboard report and manifest entry. All 12
  differences are covered by the three filed findings (9 + 2 + 1), yielding an
  84.615385% raw match rate, 100% explained rate, and no unexplained, expired,
  or orphaned DE dispositions.
- Regenerated freshness metadata and added committed-report invariants for the
  engine pair/configuration, exact mismatch coordinates, and disposition counts.
  Ruff passed and 46 report/runner/disposition tests passed.
- Added live-gated canonical-grid anchors to the existing engine-specific test
  files. EUROMOD pins the 1,200 EUR Midijob and two-child cases under the exact
  DE dataset/template/`drgn1` configuration. GETTSIM pins the same two cases
  and proves a joint `*_y_sn` tax target is replicated and MAX-reduced.
- Marked §6 of the GETTSIM playbook as realized and added the DE operating
  playbook covering `yemmy`/hours/months, `drgn1`, the 61/56 bridge,
  `tin_s`-includes-Soli, monthly/annual units, `*_y_sn` MAX, the grid, and all
  three filed findings. The comparison registry links to that playbook.
- Live verification: the EUROMOD Germany selection passed 3 tests (33
  deselected); the dedicated locked GETTSIM environment passed all 73 adapter
  tests. GETTSIM emitted only its documented internal divide/grouping warnings.

## Next

1. Run Ruff plus the full repository test and derived-artifact checks.
2. Finalize this ledger and write the handoff report to `FINAL_REPORT.md`
   (no separate output path was provided), without pushing or opening a pull
   request.
