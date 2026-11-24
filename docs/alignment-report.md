# Oracle alignment report (report only)

`scripts/alignment_report.py` answers one question for a candidate change in
`rulespec-us`: **is there a reference that can say whether the change moved a
compared result, and if so, what did it say?** It prints and writes a JSON
report. It gates nothing: no workflow calls it, and the exit code is 0 for
every completed derivation.

The module is `axiom_oracles/alignment.py`. The coverage declarations are in
`axiom_oracles/config/alignment_coverage.yaml`.

## Inputs

1. A git repository and a revision for the base commit.
2. A git repository and a revision for the candidate commit.
3. The suite registry (`comparisons/`), the coverage configuration and
   `dispositions/` of this repository at the checked-out commit.

```bash
# two revisions of one repository
uv run python scripts/alignment_report.py \
  --rulespec-repo ~/rulespec-us --base <sha> --candidate <sha> \
  --output alignment.json

# two repositories (the HEAD of each, or --base-rev / --candidate-rev)
uv run python scripts/alignment_report.py \
  --base-repo base/rulespec-us --candidate-repo candidate/rulespec-us
```

**The report reads commits, not work trees.** Each commit is resolved in the
named repository and exported into a new clone under the work directory, with
`git --no-replace-objects`. The file list, the blob ids and the tree id are
read from the commit. Programs are compiled against the export, and suites run
against it. So an uncommitted change, an untracked file, an edit hidden behind
`--skip-worktree` or `--assume-unchanged`, a file hidden by
`.git/info/exclude`, and a `git replace` ref in the named repository cannot
reach the report. A dirty work tree in the named repository is therefore no
longer refused: it is not read. The export itself is still checked (it must be
clean and hold every tracked file), and the tree ids are recorded.

The changed files are always the files whose mode or content differs between
the two commits, over the whole repository. `--changed` is a cross-check only:
the given list must be exactly that set, spelled as git spells it, or the run
is an error. There is no option to state a commit.

The compose and engine binaries default to the supervised layout
(`~/axiom-compose/.venv/bin/axiom-compose`,
`~/axiom-rules-engine/target/release/axiom-rules-engine`); pass
`--compose-binary` and `--engine-binary` for pinned builds.

## What the report holds

### `reach`

For each changed file, the program files whose compared outputs depend on it.

* Every `programs/**.yaml` the commit tracks, and every `programs/**.yaml` of
  this repository, is composed and compiled on both sides, the way
  `run_comparison.py` does it (`axiom-compose`, then `compile-composed`
  against a staged pure root). A commit that tracks no program file is an
  error (`no_programs`).
* The compared outputs of a program are the `outputs` its program file
  declares, plus the `concepts` of every suite bound to it.
* The walk is `axiom_oracles.coverage._transitive_dependencies` from those
  outputs over the compiled program. It follows the current expression and
  every dated version of a rule. A module is reached when the walk visits one
  of its derived rules, or a visited rule reads one of its parameters or
  relations. Reach on either side counts, so a candidate that unwires or
  deletes a module is still reported.
* A changed program file reaches its own program, on the sides that have it.
* A rule written in the program file itself carries no module id; it belongs
  to the program file.
* When a bound suite compares a concept that is not a rule name of its program
  (the harness maps it elsewhere), every rule of that program counts as
  compared (`via: every_rule_unresolved_suite_concept`).
* Reach is per module, not per rule. That errs toward naming a reference.
* A file is a `module`, a companion `test` file, a `program`, or `other`. A
  changed file that looks like a rule file but sits where the engine does not
  read one (a `.yml` module, a jurisdiction directory in another letter case)
  is an error (`changed_file_unclassified`).
* `programs` records program files found and programs compiled per side. A
  difference is an error.

### `expected_suites`

The suites that can observe the change, each marked `runnable` or `manual`.

Every comparison has exactly one binding. A comparison is a suite file of
`comparisons/`, a row of a suite manifest there, or a script-run comparison
registered in the coverage configuration:

| binding | how the suite covers a change |
| --- | --- |
| `program` | `runner.parameters.axiom_program` names a program file that compiled. Expected when that program reaches the change. A declaration that also matches adds what the suite's bridge reads outside the program (the Medicaid population bridge is the one case today). |
| `parameter_files` | A row of `parameter-oracles.yaml`. Covers the `file` of each of its comparisons and what those modules name. |
| `declared` | A declaration in `alignment_coverage.yaml` gives `roots` (module files the harness compiles; the suite covers them and every module they name, transitively, in either tree; a name that is a directory stands for the modules in it) and `paths` (files the harness reads as files: a case template, a directory it globs, a tool it imports from the rulespec tree, the file that selects its engine). |
| `script_run` | A comparison that runs outside `comparisons/`, registered under `script_suites` with its script and its roots and paths. Always manual. |
| `declared_reads_no_rulespec_us` | A declaration says the harness reads no rulespec-us file. Never expected. |
| `pinned_snapshot` | The suite replays a pinned rulespec snapshot. It cannot observe a candidate. Never expected; listed in `suite_registry.pinned_snapshot_suites`. |
| `no_axiom_side` | An `axiom-oracles-compare` suite whose `left` and `right` are both one of `policyengine`, `taxsim`, `taxcalc`. Never expected. |

`pinned_snapshot` is accepted only for the runner types whose runner refuses
to run on any other tree, named in `alignment.PINNED_RUNNERS`:
`federal-tax-liability-grid` with both `rulespec_upstream_sha` and
`rulespec_upstream_tree`, and `axiom-oracles-compare` with both
`axiom_rulespec_repo_roots_revision` and `axiom_rulespec_repo_roots`. The same
keys on any other runner type, or only one of them, are not a pin.

A suite with none of these is an error for every report
(`reference_unbound`), whatever changed: an undeclared suite could cover
anything, so nothing may be called `no_reference` while one exists. That
includes a suite whose `axiom_program` does not resolve to a compiled program
and has no declaration, and a new suite of a runner type that other suites
have a declaration for: a declaration names its suites, by id or by an
explicit pattern, and a runner type alone does not match.

Three more checks keep the model from missing a comparison or holding a dead
entry. Each is an error for every report:

* `comparison_evidence_unregistered`: a dispositions file, a file under
  `dashboard/public/data`, a dated report under `reports/`, a script named
  `scripts/run_*comparison*.py` or `scripts/*campaign*.py`, or a console
  command of `pyproject.toml` that belongs to no registered suite and to no
  entry of `evidence` in the coverage configuration. Each `evidence` entry
  gives a reason. An entry that matches no file is an error too.
* `coverage_declaration_stale`: a declared glob, or a file of a parameter
  manifest row, that matches no tracked file in either tree. A glob written
  `{glob: ..., optional: true}` is exempt.
* `coverage_declarations_unreadable`: the configuration does not parse, a
  declaration matches no suite, two declarations match one suite, a named
  source or script does not exist.

`manual` is `ci: manual` in the suite file, every row of a manifest and every
script-run comparison (those are not dispatched through `run_comparison.py`). Every other suite runs in a
CI lane (the bare matrix, or a named lane such as `snap-qc-replay`) and is
`runnable`.

A declaration is a statement about a harness, written by a person. Two things
keep it honest: `sources` names the registry files it was read from, and
`tests/test_alignment.py` checks that every module those files name, by id or
by path, and every tool or `.axiom` file of the rulespec tree they name, is
inside the declared globs (and, for the SNAP QC suites, that the bridge's own
program, template and overlay files are). A harness that reaches
a module no source text names (through a glob, a built path, another
repository) is covered only as far as the declared globs are wide. The
declarations for harnesses outside this repository (`axiom-encode`) are the
whole jurisdiction for that reason.

### `status`

Exactly one of:

| status | meaning |
| --- | --- |
| `no_reference` | The derivation completed and no suite is expected. `reason` is `no_program_reaches` or `no_suite_for_reaching_programs`. |
| `reference_not_runnable` | Expected suites exist and every one is manual. They are listed. This is its own state, not `no_reference`. |
| `reference_not_executed` | At least one expected suite is runnable, and neither `--execute` nor `--reports-dir` was given. |
| `aligned` / `regressed` | Every runnable expected suite was run by this tool (`--execute`) on base and candidate. See below. |
| `aligned_unverified` / `regressed_unverified` | The same comparison on reports that were supplied (`--reports-dir`), not run by this tool. Not a gate-grade result. |
| `error` | Anything failed. `error.cause` names it. Exit code 2. |

`no_reference` is reached through one path only: both commits exported; at
least one program file on each side and every program compiled; every
comparison bound; all comparison evidence registered; no declared glob stale;
and then no bound program reaches the change and no declaration covers it. Every failure before that
point is `error`.

### `aligned` / `regressed`

With `--execute`, each runnable expected suite is run on both trees with
`scripts/run_comparison.py <suite> --require-live`, with `HOME` set to a
directory that holds that side's `rulespec-us` checkout.

With `--reports-dir DIR`, reports are read from
`DIR/{base,candidate}/<suite>.json`. `DIR/manifest.json` must hold
`schema: axiom_oracles.alignment_supplied_reports.v1`, the `registry_commit`,
the `rulespec_commit` of both sides, and under `reports.<suite>` the sha256 of
both files and of the suite file (`suite_file_sha256`). All must equal what
this run sees, and the reports must record an engine identity. The manifest is
the supplier's own statement: it ties the files to one run, it does not prove
who produced them or that anything ran. **A gate may only use `--execute`
evidence.** A result from supplied reports has `evidence:
supplied_reports_unverified` and the status `aligned_unverified` or
`regressed_unverified`.

Either way a report is accepted only when it:

* was stamped for the suite by the runner (`provenance.generated_by` is
  exactly `scripts/run_comparison.py::<suite>`; the report's own `suite` key
  is the case-set name for a population comparison and is not used);
* is not a re-emitted committed report (`reemitted_report`, or a `run_kind`
  that says so);
* records exactly one `provenance.rulespecs` row for
  `TheAxiomFoundation/rulespec-us`, with the side's commit and `dirty: false`;
* records an oracle identity, the same on both sides, the same engine
  identity on both sides, and the same tolerance and concept table;
* records `case_count` equal to the case rows present, and is not a truncated
  dashboard copy;
* has at least one case, the same case ids on both sides, and in every case
  compares at least the outputs base compared.

Three case shapes are read: the population comparison (`matches`,
`mismatches`, `left_errors`, `right_errors` per case), the SNAP QC replay and
the ABAWD boundary grid (`matched` per case), and the federal tax grids
(`match` per case). In the last two a mismatching case takes its concepts from
the report-level mismatch rows. The replay writes `matched: null, stage:
"error"` for a case one side of which is missing and counts it in
`case_count`; that row is the error state of the case. A grid run that
recorded errors is an error, because that shape does not say which cases
errored. Any other shape is an
error (`suite_report_shape_unsupported`).

The change is `regressed` when, in any executed suite:

* a case that matched on base, or errored on base, mismatches on candidate, or
* a case that mismatched on base has a compared output that newly mismatches,

and no entry of `dispositions/<suite>.yaml` selects every new mismatch row of
that case (the selector and pin rules of `apply_dispositions.py`), or

* a case that did not error on base errors on candidate.

`counts` holds cases, matched before and after, newly matched, newly
mismatched, newly errored, dispositioned, and undispositioned regressions.
Manual expected suites are listed in `manual_suites_not_run`.

### Artifact reuse

Compiling is the slow step (146 program files per side at the time of
writing). An artifact is reused when everything its compile read is
byte-identical: the program file, the file of every module the artifact
compiled from or the composed program imports, every module those name
transitively, and the listing of each same-named directory. Within one report
that makes an unchanged candidate program take the base artifact.
`--cache-dir` keeps artifacts across reports, keyed also by the engine binary
and the installed `axiom-compose`; it is switched off when that install comes
from a source tree with uncommitted changes. An entry on disk is used only
when its artifact digest is the recorded one and its recorded inputs are
exactly the inputs this run computes for that artifact. `--recompile-all`
reuses nothing.

A cache directory that another party can write is not trusted by this check:
a consistent forged entry is accepted. Keep the directory private to the runs
that use it.

### `provenance`

Registry commit and dirty flag, both rulespec-us commits and their tracked
file counts, the sha256 of the coverage declarations, of every compiled
program per side and of every changed file per side, the engine version the
artifacts record, the sha256 of the engine binary, the identity of the
`axiom-compose` install, and the tool version.

## What the owner should know about the references

Three facts about the suites themselves, found in review. None is a defect of
this report; each limits what a result from it can mean.

1. **No runnable suite can compare a candidate federal income tax change.**
   All 11 federal tax grids replay a pinned rulespec snapshot. They run in
   CI, but on the pinned tree, not on a candidate. The suites that do read a
   candidate federal tax module (`fiit-ecps`, the state suites) are manual.
2. **36 of the 39 state income tax grids do not evaluate candidate modules.**
   Their generator takes the Axiom value from the expected output of the
   pipeline's `.test.yaml` fixture
   (`scripts/generate_state_income_tax_liability.py`). Only Kentucky,
   Mississippi and Utah run the engine. An `aligned` from the other 36 would
   say that the fixture did not change, not that the rule still agrees. They
   are manual today, so this report never executes them.
3. **The parameter comparisons see a change only after it lands.**
   `scripts/run_medicaid_thresholds_comparison.py` and
   `scripts/run_parameter_comparisons.py` read `origin/main` of rulespec-us.
   They cannot be pointed at a candidate.

## What must hold before this may gate a landing

This report does not gate. The list is what two independent reviews asked for
before it could, with the state of each item after review round 2. Round 2
has not been re-reviewed.

| requirement | state |
| --- | --- |
| 1. `no_reference` only through a completed computation with a truly empty expected set | Built by construction: every comparison has a binding, or the run is an error. Holds only as far as each declaration is at least as wide as its harness. |
| 2. Every comparison of the repository is in the model, also those outside `comparisons/` | Script-run comparisons are registered suites. A completeness check fails the run when a dispositions file, dashboard file, dated report, comparison or campaign script, or console command belongs to no suite and no reasoned exclusion. It finds a comparison by those traces; a comparison that leaves none of them is not found. |
| 3. Files that are no module (tools, toolchain file, fixtures) are covered when a harness reads them | Declarations name them in `paths`; a test checks the tools and `.axiom` files the named sources reference. Other kinds of file a harness might read are not searched for. |
| 4. Pinned and no-Axiom-side suites are exempt only when that is certain | Pins count only for the two runner types whose runner enforces them, with all their keys. No-Axiom-side needs two named other engines. |
| 5. The bytes read are the bytes of the named commits | Both commits are exported from the object store with replace refs ignored; the work tree of the caller is never read; tree ids are recorded. |
| 6. Supplied reports cannot stand in for a run | They give `aligned_unverified` / `regressed_unverified` only. Signed evidence is not built. |
| 7. Declarations cannot go stale silently | A glob or manifest file that matches no tracked file is an error; a declaration that matches no suite is an error; a new suite does not inherit a declaration by runner type. |
| 8. Declared coverage is what the harness reads | Checked against the literal ids and paths in the named sources. **Not** checked against what a harness reads at run time. Harnesses in `axiom-encode` are declared wide and are not verified. Module references are read as `xx:path` text, not through the engine's resolver. |
| 9. `aligned` means the candidate was compared | True only for a suite that evaluates the candidate tree. See the three facts above: pinned suites and fixture-reading grids would not. Today the only runnable suites that read a candidate are the six SNAP QC replays and the ABAWD grid. `--execute` has not been run against a real suite. |

## What this does not do

* It does not gate a merge and no workflow runs it.
* It does not compute bridge coverage from a run of the harness.
* It does not sign or publish its report.
