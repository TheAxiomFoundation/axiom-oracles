# Alignment report — progress

Branch `claude/alignment-report`. First, report-only piece of an oracle
alignment check for candidate `rulespec-us` changes. Design and status table:
`docs/alignment-report.md`.

## Done

- `axiom_oracles/alignment.py`: reach, expected suites, status derivation,
  per-case base/candidate comparison with dispositions, provenance, an
  input-keyed compile cache.
- `scripts/alignment_report.py`: CLI. `--execute` runs runnable expected
  suites through `run_comparison.py --require-live`; `--reports-dir` reads
  supplied reports.
- `tests/test_alignment.py`: synthetic fixture (modules, three programs,
  hand-written compiled artifacts, four-case suite reports). Every status
  path and every error cause has a test.
- Mutation run on the status derivation (script kept outside the repository);
  result in the pull request body.
- Three read-only runs on real `rulespec-us` history; results in the pull
  request body. No report or population-derived file is committed.

## Findings while building

- Every program-bound US suite is `ci: manual` (10 bound to a `rulespec-us`
  program file, 12 to a program of this repository). The only runnable US
  suites that the report can bind are the six `snap-qc-replay` suites, through
  the composition modules `snap_qc_compare.py` names.
- 51 manual and 12 runnable US suites build their program in a bridge and
  have no binding (federal and state income tax grids, tariff, ABAWD grid).
  A change that only those may exercise is reported as an error
  (`reach_incomplete_harness_reference`), never as `no_reference`.
- Inline rules of a program file carry no module id in the compiled artifact;
  they are attributed to the program file.
- The engine refuses a staged root inside another repository's work tree, so
  staging goes to the system temp directory.

## Not built

- No gate, no workflow, no required check.
- No rule for wiring pull requests (a program-file change that should be
  paired with a suite run).
- No signed or published evidence.
- No binding for bridge-built suites.
- `--execute` was not run against a real suite: every runnable candidate needs
  the SNAP QC public-use file and the fiscal-year overlay root.
