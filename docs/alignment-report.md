# Oracle alignment report (report only)

`scripts/alignment_report.py` answers one question for a candidate change in
`rulespec-us`: **is there a reference that can say whether the change moved a
compared result, and if so, what did it say?** It prints and writes a JSON
report. It gates nothing: no workflow calls it, and the exit code is 0 for
every completed derivation.

The module is `axiom_oracles/alignment.py`.

## Inputs

1. A `rulespec-us` tree at the base commit.
2. The same tree at the candidate commit, or a list of changed files with
   `--changed`.
3. The suite registry (`comparisons/*.yaml`) and `dispositions/` of this
   repository at the checked-out commit.

```bash
# two revisions of one repository; clones are made under --work-dir
uv run python scripts/alignment_report.py \
  --rulespec-repo ~/rulespec-us --base <sha> --candidate <sha> \
  --output alignment.json

# two existing checkouts (each a directory named rulespec-us)
uv run python scripts/alignment_report.py \
  --base-root base/rulespec-us --candidate-root candidate/rulespec-us
```

The compose and engine binaries default to the supervised layout
(`~/axiom-compose/.venv/bin/axiom-compose`,
`~/axiom-rules-engine/target/release/axiom-rules-engine`); pass
`--compose-binary` and `--engine-binary` for pinned builds.

## What the report holds

### `reach`

For each changed file, the program files whose compared outputs depend on it.

* Every `programs/**.yaml` of the rulespec tree, and every `programs/**.yaml`
  of this repository, is composed and compiled on both sides, the way
  `run_comparison.py` does it (`axiom-compose`, then `compile-composed`
  against a staged pure root).
* The compared outputs of a program are the `outputs` its program file
  declares, plus the `concepts` of every suite bound to it.
* The walk is `axiom_oracles.coverage._transitive_dependencies` from those
  outputs over the compiled program. A module is reached when the walk visits
  one of its derived rules, or a visited rule reads one of its parameters or
  relations. Reach on either side counts, so a candidate that unwires a module
  is still reported.
* A changed program file reaches its own program.
* Reach is per module, not per rule: a new rule in a module whose other rules
  are reached counts as reached. That errs toward naming a reference.
* A rule written in the program file itself carries no module id; it belongs
  to the program file, whose change reaches the program directly.
* When a bound suite compares a concept that is not a rule name of its program
  (the harness maps it elsewhere), every rule of that program counts as
  compared (`via: every_rule_unresolved_suite_concept`). Wider than the truth,
  never narrower.
* `programs` records program files found and programs compiled per side. A
  difference is an error.

Compiling is the slow step (146 program files per side at the time of
writing). An artifact is reused when everything its compile read is
byte-identical: the program file, the file of every module the artifact
compiled from or the composed program imports, every module those name
transitively, and the listing of each same-named directory. Within one report
that makes an unchanged candidate program take the base artifact;
`--cache-dir` keeps artifacts across reports, keyed also by the engine binary
and the installed `axiom-compose`. `--recompile-all` reuses nothing.
`programs.<side>.reused` counts the reused artifacts.

### `expected_suites`

The suites bound to a reaching program, each marked `runnable` or `manual`.

* A suite is bound through `runner.parameters.axiom_program`
  (`.../rulespec-us/programs/...` or this repository's `programs/...`).
* `snap-qc-compare` suites compile a state composition module, not a program
  file. They are bound through the modules that
  `axiom_oracles/bridges/snap_qc_compare.py` and the state's overlay name for
  the suite's `jurisdiction` (`binding: runner_source_reference`): the suite is
  expected when one of those modules is the changed module or names it,
  directly or through other modules. This is a module-level text reference, so
  it can name a suite that the change does not move.
* `manual` is `ci: manual` in the suite file. Every other suite runs in a CI
  lane (the bare matrix, or a named lane such as `snap-qc-replay`) and is
  `runnable`.
* `compared_concepts_reach_change` says whether the suite's own concepts, not
  only its program's outputs, depend on the change.
* A changed `<module>.test.yaml` file has no reach through a program, but a
  harness can read it (the SNAP QC replay takes its case template from one),
  so a suite or harness file that names that test file by path counts for it.
* Any other suite with no program binding is expected when its own file names
  a changed module, or a module that names one (`binding: module_reference`).

### `status`

Exactly one of:

| status | meaning |
| --- | --- |
| `no_reference` | The derivation completed and no suite is expected. `reason` is `no_program_reaches` or `no_suite_for_reaching_programs`. |
| `reference_not_runnable` | Expected suites exist and every one is `ci: manual`. They are listed. This is its own state, not `no_reference`. |
| `reference_not_executed` | At least one expected suite is runnable, and neither `--execute` nor `--reports-dir` was given. |
| `aligned` / `regressed` | Every runnable expected suite ran on base and candidate. See below. |
| `error` | Anything failed. `error.cause` names it. Exit code 2. |

An error is never reported as `no_reference`. Causes include an unreadable
registry, a program that does not compile, a compiled count that differs from
the files found, a declared output the compiled program does not define, two
trees that do not differ under the jurisdiction directories or `programs/`,
a suite run that fails, re-emits a committed report, returns zero
cases, or ran against another commit, a case count or case-id set that differs
between base and candidate, and a timeout.

One more cause guards `no_reference`:
`reach_incomplete_harness_reference`. Bridges and overlays in this repository
compile RuleSpec modules without a program file (the tax bridges, the SNAP
population bridge). When no suite is expected but a changed module, or a
module that names it, is named in `axiom_oracles/`, `scripts/` or
`comparisons/` (as `us:path` or as a `us/path.yaml` file path), a suite this
report cannot bind may still exercise the change. That is
unknown, so it is an error and not `no_reference`.

### `aligned` / `regressed`

With `--execute`, each runnable expected suite is run on both trees with
`scripts/run_comparison.py <suite> --require-live`, with `HOME` set to a
directory that holds that side's `rulespec-us` checkout. With
`--reports-dir DIR`, reports are read from `DIR/{base,candidate}/<suite>.json`
instead. Either way a report must record the side's rulespec-us commit in
`provenance.rulespecs`.

Cases are compared by `case_id`. A case is a match, a mismatch, or an error.
The change is `regressed` when, in any executed suite:

* a case that matched on base mismatches on candidate, or
* a case that mismatched on base has a compared output that newly mismatches,

and no entry of `dispositions/<suite>.yaml` selects every new mismatch row of
that case (the same selector as `apply_dispositions.py`), or

* a case that did not error on base errors on candidate.

`counts` holds cases, matched before and after, newly matched, newly
mismatched, newly errored, dispositioned, and undispositioned regressions.
Manual expected suites are listed in `manual_suites_not_run`.

### `provenance`

Registry commit and dirty flag, both rulespec-us commits, the sha256 of every
compiled program per side, the sha256 of every changed file per side, the
engine version the artifacts record, the sha256 of the engine binary, the
identity of the `axiom-compose` install, and the tool version.

## What this does not do

* It does not gate a merge and no workflow runs it.
* It does not bind the suites that build their program in a bridge (federal
  and state income tax, the tariff suites) to a program file. A change they
  may exercise is an error, not a status.
* It does not sign or publish its report.
