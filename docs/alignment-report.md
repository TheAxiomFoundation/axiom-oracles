# Oracle alignment report (report only)

`scripts/alignment_report.py` answers one question for a candidate change in
`rulespec-us`: **is there a reference that can say whether the change moved a
compared result, and if so, what did it say?** It prints and writes a JSON
report. It gates nothing: no workflow calls it, and the exit code is 0 for
every completed derivation.

The module is `axiom_oracles/alignment.py`. The coverage declarations are in
`axiom_oracles/config/alignment_coverage.yaml`.

## Inputs

1. A `rulespec-us` checkout at the base commit.
2. A `rulespec-us` checkout at the candidate commit.
3. The suite registry (`comparisons/`), the coverage declarations and
   `dispositions/` of this repository at the checked-out commit.

```bash
# two revisions of one repository; clones are made under --work-dir
uv run python scripts/alignment_report.py \
  --rulespec-repo ~/rulespec-us --base <sha> --candidate <sha> \
  --output alignment.json

# two existing checkouts (each a directory named rulespec-us)
uv run python scripts/alignment_report.py \
  --base-root base/rulespec-us --candidate-root candidate/rulespec-us
```

Each tree must be the top level of a git checkout with no staged, unstaged or
untracked change, and must hold every file its commit tracks. A dirty tree, a
sparse or partly deleted tree, and a directory that is not a checkout are
errors. The commits are read from the checkouts; there is no option to state
them.

The changed files are always the files whose content differs between the two
commits, over the whole repository. `--changed` is a cross-check only: the
given list must be exactly that set, spelled as git spells it, or the run is
an error.

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

Every suite of `comparisons/` (a suite file, or a row of a suite manifest) has
exactly one binding:

| binding | how the suite covers a change |
| --- | --- |
| `program` | `runner.parameters.axiom_program` names a program file that compiled. Expected when that program reaches the change. |
| `parameter_files` | A row of `parameter-oracles.yaml`. Covers the `file` of each of its comparisons and what those modules name. |
| `declared` | A declaration in `alignment_coverage.yaml` gives `roots` (module files the harness compiles; the suite covers them and every module they name, transitively, in either tree) and `paths` (files the harness reads as files). |
| `declared_reads_no_rulespec_us` | A declaration says the harness reads no rulespec-us file. Never expected. |
| `pinned_snapshot` | The suite replays a pinned rulespec snapshot (`rulespec_upstream_sha` + `rulespec_upstream_tree`, or `axiom_rulespec_repo_roots_revision`). It cannot observe a candidate. Never expected; listed in `suite_registry.pinned_snapshot_suites`. |
| `no_axiom_side` | An `axiom-oracles-compare` suite between two other engines. Never expected. |

A suite bound through a program file may also match a declaration; the
declaration then adds what the suite's bridge reads outside that program
(the Medicaid population bridge is the one case today).

A suite with none of these is an error for every report
(`reference_unbound`), whatever changed: an undeclared suite could cover
anything, so nothing may be called `no_reference` while one exists. That
includes a suite whose `axiom_program` does not resolve to a compiled program
and has no declaration.

`manual` is `ci: manual` in the suite file, and every row of a manifest (those
are not dispatched through `run_comparison.py`). Every other suite runs in a
CI lane (the bare matrix, or a named lane such as `snap-qc-replay`) and is
`runnable`.

A declaration is a statement about a harness, written by a person. Two things
keep it honest: `sources` names the registry files it was read from, and
`tests/test_alignment.py` checks that every module those files name, by id or
by path, is inside the declared globs (and, for the SNAP QC suites, that the
bridge's own program, template and overlay files are). A harness that reaches
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
| `aligned` / `regressed` | Every runnable expected suite ran on base and candidate. See below. |
| `error` | Anything failed. `error.cause` names it. Exit code 2. |

`no_reference` is reached through one path only: both trees read as clean,
complete checkouts; at least one program file on each side and every program
compiled; every suite bound; the declarations read; and then no bound program
reaches the change and no declaration covers it. Every failure before that
point is `error`.

### `aligned` / `regressed`

With `--execute`, each runnable expected suite is run on both trees with
`scripts/run_comparison.py <suite> --require-live`, with `HOME` set to a
directory that holds that side's `rulespec-us` checkout.

With `--reports-dir DIR`, reports are read from
`DIR/{base,candidate}/<suite>.json`. `DIR/manifest.json` must hold
`schema: axiom_oracles.alignment_supplied_reports.v1`, the `registry_commit`,
the `rulespec_commit` of both sides, and under `reports.<suite>` the sha256 of
both files. All four must equal what this run sees. The manifest is the
supplier's own statement; it ties the files to one run, it does not prove who
produced them. The result carries `evidence: supplied_reports`.

Either way a report is accepted only when it:

* was stamped for the suite by the runner (`provenance.generated_by` ends
  with `::<suite>`; the report's own `suite` key is the case-set name for a
  population comparison and is not used);
* is not a re-emitted committed report (`reemitted_report`, or a `run_kind`
  that says so);
* records exactly one `provenance.rulespecs` row for
  `TheAxiomFoundation/rulespec-us`, with the side's commit and `dirty: false`;
* records an oracle identity, the same on both sides, and the same engine
  identity on both sides;
* records `case_count` equal to the case rows present, and is not a truncated
  dashboard copy;
* has at least one case, the same case ids on both sides, and in every case
  compares at least the outputs base compared.

Three case shapes are read: the population comparison (`matches`,
`mismatches`, `left_errors`, `right_errors` per case), the SNAP QC replay and
the ABAWD boundary grid (`matched` per case), and the federal tax grids
(`match` per case). In the last two a mismatching case takes its concepts from
the report-level mismatch rows, and a run that recorded errors is an error,
because those shapes do not say which cases errored. Any other shape is an
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

## What must hold before this may gate a landing

This report does not gate. The list below is what an independent review asked
for before it could, with the state of each item after review round 1. None of
it has been re-reviewed.

| requirement | state |
| --- | --- |
| `no_reference` only through a completed computation with a truly empty expected set | Built by construction: every suite has a program binding or a declaration, or the run is an error. Holds only as far as each declaration is at least as wide as its harness. |
| Coverage of suites that build their program in a bridge | Declared, not derived. Checked against the literal module ids and paths in the named sources. Not checked against what the harness reads at run time. |
| Harnesses outside this repository (`axiom-encode` SNAP and tax population runs) | Declared as the whole jurisdiction or the federal tax directories. Not verified against that repository. |
| Reference completeness of module files | Module-to-module references are read as `xx:path` literals in the module text. A reference in another form would be missed by declared-root closures. Not verified against the engine's resolver. |
| Missing, empty or unreadable `programs/` | Error. Program files are taken from the commit's tree; the work tree must be clean and complete. |
| Changed files cannot be stated by the caller | Done. Derived from the two commits; a given list must equal it. |
| Every version of a dated rule is walked | Done, in the shared `_transitive_dependencies`. |
| Reports bound to suite, repository, commit, clean tree, live run, oracle and engine identity | Done for what a report records. A report does not record the registry commit or a tree digest; for supplied reports the manifest states them. |
| Per-case comparison catches a dropped output, base error to candidate mismatch, and like-truncated reports | Done. |
| Runnable suites' real report shapes are read | Done for the three shapes above, tested on synthetic rows in those shapes. Not run against a real suite: the SNAP QC replay needs the public-use file and the overlay root. |
| Cache entries verified | Digest and input record verified. A writable shared directory is still not trusted. |
| Signed evidence | Not built. Supplied reports are self-described. |
| Independent re-review after these changes | Not done. |

## What this does not do

* It does not gate a merge and no workflow runs it.
* It does not compute bridge coverage from a run of the harness.
* It does not sign or publish its report.
