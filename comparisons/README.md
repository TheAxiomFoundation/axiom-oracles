# Comparisons registry

Each `*.yaml` in this directory declares one oracle comparison — a head-to-head
between two engines over a validation population. `scripts/run_comparison.py`
reads a config, dispatches to the right runner type, writes a JSON report, and
prints a headline summary. `.github/workflows/comparisons.yml` matrix-runs
every config in the registry that does not declare `ci: manual` on a weekly
schedule.

## How to run one locally

Materialize the latest published data first when the run should use current
reports and fallback artifacts. Set `AXIOM_ORACLES_DATA_SOURCE=checkout` to
validate the reviewed checkout or work offline instead.

```bash
python3 scripts/oracle_data.py materialize
uv run scripts/run_comparison.py fiit-ecps --summary
uv run scripts/run_comparison.py co-snap-ecps --summary
uv run scripts/run_comparison.py co-snap-qc --summary
uv run scripts/run_comparison.py uk-universal-credit-efrs --summary
```

## CI workspace materialization and the manual lane

The comparison harnesses resolve rulespec checkouts, synced roots, and the
axiom-compose venv from supervised-layout conventions under `$HOME`
(`~/TheAxiomFoundation/<repo>`, `~/rulespec-us`, `~/.axiom-oracles/roots`,
`~/rulespec-uk-official`, `~/axiom-compose/.venv`, `~/axiom-oracles`). Both CI
workflows materialize that layout per matrix leg with
`scripts/materialize_ci_workspace.py <registry-name>` — data-driven from
`affected_map.json` (which repos to clone) and the suite YAML (which
conventions to link, whether to build the compose venv), skip-if-present so a
supervised machine is never touched (#296, #300).

Source checkouts use `main` with full history. Before selecting suites or
running a comparison, the workflows run
`scripts/oracle_data.py materialize --baseline` to combine that source with
the latest `oracle-data` snapshot. This makes published report provenance and
fallback reports available at their existing paths while retaining current
source code. `--baseline` records the combined tree as a disposable detached
baseline, so packing a run measures its own generated changes. It requires a
clean tracked worktree and index; save or commit local edits before using it.
For manual publication, run it before the producer as shown
[below](#manual-single-suite-publication).

Engine compiles follow the post-hard-cut contract via
`axiom_oracles/engine_compat.py`: explicit repeatable `--rulespec-root` flags
naming canonical `rulespec-<cc>` checkouts (staged pure — jurisdiction dirs
only), `compile-composed` for out-of-root compositions (compose output, the
generated oracle-bridge programs), and a legacy env-resolved fallback for
pre-hard-cut engine builds on supervised machines.

A suite CI cannot execute at all declares `ci: manual` at the top level of its
YAML (with a comment saying why and what unblocks it). The affected-map
generator then emits `name: null`, the 6-hourly selector routes it to the
manual lane instead of dispatching a doomed leg, and the weekly matrix skips
it. Its committed report refreshes only via a supervised
`run_comparison.py` run. The seven SNAP QC suites (`*-snap-qc`) declare
`ci: manual` for that reason: both workflows clone rulespec-us main but never
build the engine binary or download the QC public-use file, so their legs
could only re-emit the committed report, and on 2026-09-23 the affected rerun
committed such re-emissions over the five real reports #548 had landed. The
same holds, and the same marker applies, for:

- the 40 EUROMOD-platform suites (`euromod-synthetic-compare`: the BE and DK
  EUROMOD suites and the `*-ukmod` UKMOD suites). Neither workflow provides the
  x64 engine, the `euromod` connector under `EUROMOD_PYTHON`, a .NET runtime,
  or the model checkout. They refresh through `scripts/regenerate_euromod_uk.sh`,
  `scripts/regenerate_euromod_dk.sh`, or a supervised run.
- the ten UK PolicyEngine case grids and the `us-tariff` grid. Their generators
  evaluate the rules through an engine binary (`AXIOM_RULES_ENGINE_BINARY`, an
  `axiom-rules-engine` build, or `axiom-rules` on `PATH`) that neither workflow
  exports or builds, so their legs fail with "No such file or directory:
  'axiom-rules'" and fall back to the committed report.
- the SPSD/M suite (`ca-federal-schedule-tax-spsm`, `spsm-ca-compare`).
  SPSD/M is licensed and never vendored (`docs/spsdm-oracle-design.md`), so no
  runner can hold an install. Its generator hard-fails rather than re-emitting
  ("No SPSD/M installation found"), and it was the weekly matrix's only red leg
  (run 36426573617). It maps to no rulespec repo, so the affected rerun never
  selected it; the marker takes it out of the weekly matrix.

Before these suites were marked, the affected rerun committed their legs' output
over 45 of their reports (34 EUROMOD/UKMOD suites, `us-tariff`, and the ten UK
grids): first over the real runs, then over each other on every sweep, often
changing nothing but `generated_at`. The UK grid fallback is not even marked as
a re-emission, so those commits stamped the July numbers with each later
rulespec-uk SHA as if they had run. `tests/test_affected_map.py` fails if a
suite of any of these runner types lacks `ci: manual`. (The two DE GETTSIM
suites also only re-emit here, but they map to no rulespec repo, so the affected
rerun never selects them, and the DE lane is left as it is.)

Reports must carry real rulespec SHAs: `provenance.rulespecs[].sha` is what
`select_affected_suites.py` diffs against repo HEADs, and a `null` SHA means
"cannot prove fresh" — re-selected every sweep. The always-real runner lanes
complete missing SHAs from the affected map plus the checkout the run actually
resolved; skip-capable lanes (euromod/gettsim/snap-qc) are deliberately excluded
so a re-emitted report is never stamped fresh. A re-emission never replaces a
committed report, whether that report came from a real run or was itself a
re-emission: it copies the committed numbers, so publishing it could only change
labels. `run_comparison.py` leaves any existing dashboard copy byte-for-byte
unchanged, and `scripts/commit_refreshed_report.sh` puts back the tip's copy
(`scripts/guard_reemitted_reports.py`) before it commits. Only a suite's first
report may be a re-emission. A re-emission also records no engine in its
provenance, because none ran, and it leaves the copied report's
`engines.versions` alone. Both guards rely on the runner marking its re-emission
(`provenance.reemitted_report`). The UK PolicyEngine case-grid runners'
fallbacks do not mark theirs yet (#549 adds the marker): `ci: manual` keeps
those suites off the bot, but until #549 lands a manual run of one of them on a
machine without the engine still copies the committed report under fresh
provenance and replaces it.

A suite that pins one reviewed rulespec snapshot
(`rulespec_upstream_sha`/`rulespec_upstream_tree` in its parameters — the
federal tax grids) is judged against the PIN instead of the repo's moving
HEAD: the map generator copies the pin into the entry (`pinned: {repo:
sha}`), the selector treats `recorded == pin` as fresh, and the suite goes
stale exactly when a deliberate re-pin PR changes the pin. Judging a pinned
suite against HEAD would re-select it every sweep forever, since its report
can only ever stamp the pinned SHA.

## How to add a new comparison

Drop a new `<name>.yaml` in this directory matching the schema below. The
workflow picks it up automatically on the next run. No workflow edit required.

```yaml
name: <slug>                       # filename without .yaml
title: One-line human description
description: |
  Multi-line description; goes into the workflow summary.
documentation: docs/<file>.md      # optional pointer to recipe doc

runner:
  type: <runner-name>              # see "Supported runners" below
  # plus runner-specific keys (see existing comparisons for shape)

artifacts:
  report_basename: axiom-policyengine-<slug>
```

## Referencing a canonical case set

Synthetic-suite comparisons (the EUROMOD/UKMOD triangulations) run a named case
set rather than a population. That case set is canonicalised in
`grids/<jurisdiction>.yaml` — the same skeleton every engine in the
jurisdiction runs (see `grids/README.md`). Instead of inlining cases, a
comparison references the grid set:

```yaml
runner:
  parameters:
    grid_case_set: uk:uk-worker-pit   # or bare 'uk-worker-pit' (globally unique)
```

`axiom_oracles.grids.resolve_grid_case_set(reference)` resolves it. The suite
factory in `axiom_oracles/suites/` still derives the per-engine projections from
that skeleton, so a config points at the canonical case list without duplicating
it. Suite-specific one-off cases can still be added inline alongside a referenced
set for a probe that does not belong in the shared grid.

## Supported runners

### `axiom-encode-tax-ecps-compare`

Invokes `axiom-encode tax-populace-compare` (renamed from `tax-ecps-compare`
in the encoder's ECPS→Populace rename; no alias survives on axiom-encode main
— the runner type keeps the old name so existing suite YAMLs stay valid) via
`uv run`. Builds a release `axiom-rules-engine` binary if missing; clones
`rulespec-us` fresh into a directory named exactly `rulespec-us` (required by
the engine import resolver) and records the clone's HEAD SHA into the report's
`provenance.rulespecs`. Honors a `pinned` parameter that controls the
PolicyEngine version stack. The runner installs the local `axiom-encode`
checkout with `--with-editable` so comparison configs can validate unmerged
harness changes before they land.

The oracle population is the pinned Populace US artifact (resolved and
sha256-verified inside axiom-encode; axiom-encode#952). The harness emits a
`dataset_identity` block in its `--json` output; the dashboard adapter threads
it onto the generated v2 report so a checked-in report records which pinned
artifact produced it. This is the FIIT lane of the A9 runner unification — one
runner, one schema, one dashboard. The ~19k LOC oracle bridge itself now lives
in this repo as `axiom_oracles/bridges/` (axiom-encode re-exports it as thin
shims); this runner still shells out to the encoder CLI in a pinned
PolicyEngine environment, and pointing it at the in-repo package is a
follow-up.

Required runner keys: `axiom_encode_repo`, `axiom_rules_repo`,
`rulespec_remote`. Required `parameters`: `sample_size`, `year`, `surface`.

### `axiom-encode-uk-efrs-compare`

Invokes `axiom-encode uk-populace-compare` (renamed from `uk-efrs-compare` in
the encoder's ECPS→Populace hard cut, axiom-encode #1108; no alias survives
on axiom-encode main — the runner type keeps the old name so existing suite
YAMLs stay valid) via `uv run` with the pinned PolicyEngine UK stack. The
subcommand's implementation is this repo's own
`axiom_oracles.bridges.efrs_uk` module, re-exported by axiom-encode; the
runner overlays this checkout's bridge over the encoder's pinned
axiom-oracles dependency via `PYTHONPATH` (uv rejects a second URL for a
pinned package), so suite runs validate the current oracle code — this was
the "pointing it at the in-repo package" follow-up. Supports either
one `surface` or a `surfaces` list; the
runner merges multi-surface JSON output before adapting it to the dashboard.
When `parameters.axiom_program` is declared, the runner first composes that
`axiom-programs` spec and passes the composed RuleSpec file as the Universal
Credit program under test.

Required runner keys: `axiom_encode_repo`, `axiom_rules_repo`,
`rulespec_root`. Required `parameters`: `sample_size`, `year`, `dataset`.

### `axiom-oracles-compare`

Invokes `axiom-oracles compare <left> <right>` — the generic comparator in
this repo. The SNAP path uses a precompiled artifact bundled at
`axiom_oracles/adapters/axiom/artifacts/`. Builds a release engine binary if
missing.

Required runner keys: `axiom_rules_repo`. Required `parameters`: `left`,
`right`, `concept`, `period`, `sample_size`, `population`.

### `federal-tax-liability-grid`

Runs one reviewed federal tax case grid through
`scripts/generate_federal_tax_liability.py`. The Axiom leg reads the selected
policy's engine-verified RuleSpec companion fixture; the PolicyEngine leg builds
fresh 2026 simulations under the config's explicit per-suite PE-US/core pins.
Runs are policy-isolated and have no committed-report fallback, so one missing
companion cannot couple the other policies and an unavailable oracle fails
rather than replaying stale evidence. A policy may select all companion cases
or an explicitly documented non-vacuous exact-input subset.

Required `parameters`: `policy`, `rulespec_roots`,
`policyengine_version: 4.18.9`, `policyengine_us_version: 1.767.3`, and
`policyengine_core_version: 3.30.3`. The federal runner rejects missing or
different pins so these suites cannot silently fall back to the older default
oracle universe. Optional `parameters`: `python` (defaults to `3.13`). The
roots are passed to the generator explicitly; it never assumes a fixed sibling
RuleSpec checkout. Configs using development-worktree roots should also declare
the canonical `rulespec_remote` so the affected-rerun map retains the
`rulespec-us` dependency and CI can clone it when the development root is
absent.

When `rulespec_upstream_sha`/`rulespec_upstream_tree` pin the reviewed
snapshot, a configured root is used only if it IS that snapshot (clean, tree
equal to the pin); otherwise the runner materializes the pinned revision in a
scratch clone (`git fetch` of the pinned SHA — reachable from main — then a
detached checkout) and verifies it before running. Previously the runner
cloned main HEAD and died on "pinned federal rulespec snapshot tree mismatch"
on every sweep after upstream moved. The affected-rerun selector judges these
suites against the pin, not HEAD (see above), so a green refresh settles them
until the next deliberate re-pin.

### `snap-abawd-boundary-grid`

Runs the SNAP ABAWD post-P.L. 119-21 statute-boundary grid
(`scripts/generate_snap_abawd_boundary.py`) — the behavioral companion to the
PR #400 structural closure warning on the 2015(o)(3) / 273.24 divergence. The
Axiom leg replays the nine July 2026 boundary cases from the rulespec-us
`us/regulations/7-cfr/273/24.test.yaml` companion fixture (engine-verified in
rulespec-us CI) and fails closed unless each replayed verdict equals the
pinned legal expectation and each case still zeroes every unrelated
exception; the PolicyEngine leg builds fresh person-level monthly simulations
under the reviewed 2026 oracle stack and verifies the oracle's own
exempted-age brackets flip at the 2025-07-04 effective date before trusting
its verdicts.

Unlike the federal tax grids the rulespec snapshot is deliberately unpinned:
each run clones rulespec-us main (or reads the materialized CI checkout) and
stamps its real HEAD into provenance, so the affected-rerun sweep re-runs the
matrix whenever rulespec-us moves — encoding drift at the boundaries fails
the generator loudly, and oracle drift surfaces as report mismatches gated by
the unexplained ratchet.

Required `parameters`: `rulespec_roots` (with a `rulespec_remote` fallback for
runners where no checkout is materialized), `policyengine_version: 4.18.9`,
`policyengine_us_version: 1.767.3`, and `policyengine_core_version: 3.30.3`.
The runner rejects missing or different pins. Optional `parameters`: `python`
(defaults to `3.13`).

### `snap-qc-compare`

Replays USDA SNAP Quality Control public-use reviews through the Axiom RuleSpec
SNAP composition and compares the composition's benefit and stage
intermediates with the file's constructed values (`FSBEN`, `FSGRINC`,
`FSSTDDED`, `FSSLTDED`, `FSNETINC`), which Mathematica calculates for USDA from
each edited case record; the maximum allotment is checked against the
oracle's FY2024 table. Unlike the
`axiom-encode-*` runners this calls the in-repo bridge
(`axiom_oracles.bridges.snap_qc_compare.run_snap_qc_comparison`) **in process** —
the oracle lives in this repo, so there is no encoder CLI to shell out to.

FY2024 law is evaluated through a sparse compile-time overlay (SNAP COLA module
ids rewritten from the in-repo fy-2026 vintage to `fy-2024-cola`, plus the
state's standard-utility-allowance amount patches — four Colorado amounts,
seven New York regional amounts, one California amount) at the nominal period
`2026-01`, because the federal-regulation and state-manual chain is snapshot-
dated `2025-10-01` and true-period FY2024 evaluation is impossible today (see the
playbook and TheAxiomFoundation/rulespec-us#759). Suites: `co-snap-qc`,
`ny-snap-qc` (847 reviews including the 107 NYSCAP units), `ca-snap-qc`
(883 reviews), `az-snap-qc`, `ga-snap-qc`, `md-snap-qc`, and `tx-snap-qc`
(its composition is not on rulespec-us main yet); all seven declare
`ci: manual` (see above). The runner **skips gracefully**
— re-emitting the committed dashboard report, exactly like
`euromod-synthetic-compare` — when the `axiom-rules-engine` binary, a rulespec-us
checkout carrying the `fy-2024-cola` modules, or the downloaded QC public-use file
is absent, or while the bridge is still mid-build. Where all three exist it runs
for real; the checked-in numbers are regenerated there. Because the weekly
matrix and the affected rerun never have all three, those legs always
re-emit. The **SNAP QC live replay** workflow
(`.github/workflows/snap-qc-replay.yml`, weekly and on demand) provisions the
pinned engine, a rulespec-us checkout, and the pinned PUF. It runs every
selected suite with `run_comparison.py --require-live` and fails on any re-emission,
mismatch, or error (`scripts/snap_qc_replay.py check`). See the playbook's §10.

Required `parameters`: `jurisdiction`, `fiscal_year`, `sample_size` (`0` runs the
whole jurisdiction-fiscal-year subset). Optional `parameters`: `months`,
`tolerance` (FSBEN dollar tolerance, default exact after whole-dollar rounding),
`stage_tolerance` (intermediate dollar tolerance, default `1.0`), `data_dir`,
`rulespec_root`, `workspace_root`, `axiom_binary`, `include_special_programs`,
`keep_overlay`, and `dashboard_filename` (the committed report the skip path
re-emits). See [docs/snap-qc-oracle-playbook.md](../docs/snap-qc-oracle-playbook.md).

### `gettsim-synthetic-compare`

The direct Germany dual-oracle lane. It loads a registered synthetic suite in
process, runs EUROMOD DE_2025 through the existing `EUROMOD_PYTHON` subprocess
adapter, runs GETTSIM through the host interpreter, and writes the same pairwise
v2 report with `euromod` on the left and `gettsim` on the right. If either
optional engine is unavailable, it re-emits the committed dashboard report.

Required `parameters`: `suite`, `period`, `sample_size` (`0` runs the whole
grid), the EUROMOD country/system/dataset/template configuration, and the
GETTSIM policy date/version. `euromod_extra_columns` carries model-required
inputs absent from the template dataset; Germany pins `[drgn1]`. See
`comparisons/de-worker-dual-oracle.yaml` and
`docs/de-dual-oracle-playbook.md` for the live invocation and engine contracts.

## Adding a new runner type

If a comparison needs invocation logic neither runner provides, register a
new runner in `scripts/run_comparison.py` (`RUNNERS` table near the top) and
extend this README. Keep the per-comparison YAML schema declarative; runner
implementations live in the orchestrator.

## Provenance (O2)

Every report `run_comparison.py` writes carries a `provenance` block
(`axiom_oracles.provenance.v1`): the rulespec repos + SHAs the cases ran
against, the Axiom engine SHA/version, the oracle stack identity, the pinned
dataset identity (reused from `dataset_identity`, axiom-encode#952 / populace#80),
`generated_by`, `run_kind` (`weekly` | `pr-triggered` | `affected-rerun` |
`manual`, from `$AXIOM_ORACLES_RUN_KIND`), and `generated_at`. It is additive —
a checked-in report records exactly what produced it. `axiom_oracles/provenance.py`
builds it; committed pre-provenance reports can be stamped from their git commit
date with `scripts/backfill_report_provenance.py`.

A SHA names a commit, but a run reads the working tree. So every
`provenance.rulespecs[]` entry with a SHA also records `dirty`: `false` when
the checkout's tracked index and raw files match that commit, `true` plus
`diff_sha256` when they do not, and `null` when inspection fails. Each entry
records the resolved checkout roots in `sha_toplevel` and
`worktree_toplevel`; the non-manual publication gate refuses mismatched or unverifiable
roots, and an enclosing repository cannot attest a requested subdirectory.
The check compares raw Git blob identities without clean filters or line-ending
normalization, so converted or smudged checkout bytes that differ from the
commit count as dirty. `diff_sha256` hashes a canonical manifest of each
changed path's HEAD, index and raw working-tree content ids. Initialized
submodules are inspected recursively; their HEAD and recursive dirty digest
enter the parent manifest, and an unverifiable child makes the parent
unverifiable (see `worktree_state`). Edits and deletions hidden behind
`skip-worktree` or `assume-unchanged` count, except absent skip-worktree files
that effective sparse-checkout patterns exclude; untracked files do not count,
so build output never marks a tree dirty. Reads use a private Git directory with
copies of the index and shared split-index files, preserving the checkout's
index metadata. A DE pair run reads its pinned commit from git objects, so its
entry records the pin as clean whatever the checkout holds. Without this
record, a checkout whose tracked files differ from its HEAD would be published
under a SHA whose rules did not produce the values.
`run_comparison.py` refuses
to publish a `weekly`, `pr-triggered` or `affected-rerun` report unless every
SHA-bearing rulespec entry is recorded clean. A `manual` run on a dirty tree
publishes with the flag and a stderr warning. `select_affected_suites.py`
treats a dirty or unverifiable entry as stale whatever its SHA, and
`check_vacuous_gate.py` lists the repos as `dirty_rulespecs` on the suite's
`freshness.json` row (only when there are any) with a CI warning.

## Affected-comparison map + rerun (O2)

`comparisons/affected_map.json` (generated by `scripts/generate_affected_map.py`,
CI-checked with `--check`) maps each suite to the rulespec repos its concepts
exercise. A SNAP QC suite maps to the one rulespec root its overlay is built
from (rulespec-us), since both the federal `us/` chain and the state's
`us-<st>/` layer are copied out of it; the archived `rulespec-us-<st>` repos
are never read. The **affected-rerun** workflow
(`.github/workflows/affected-rerun.yml`, every 6h + `repository_dispatch`)
resolves each mapped repo's `main` HEAD, and `scripts/select_affected_suites.py`
selects only the suites whose report ran against an older SHA — those get
rerun. Selection and matrix legs read the published `oracle-data` snapshot
materialized over current `main`. Each matrix leg then packs its refresh
(`scripts/commit_refreshed_report.sh --pack`): it collects the run's private
outputs, vets them once on its own checkout (the re-emission guard,
regenerating and verifying every derived artifact, the unexplained ratchet)
and uploads the bundle as the `refreshed-<suite>` artifact. Legs only read the
repository. One `publish` job then runs `--publish` over every bundle: it
regenerates every derived, CI-validated artifact once, in the same commit as
the reports (the dispositions merge + EUROMOD-BE coverage rollup, freshness,
conformance scoreboard + detail, the daily history snapshot, the burn-down,
census and certificates), self-checks the tree against ci.yml's staleness
gates and the unexplained ratchet before pushing, and rebuilds the commit from
scratch on the current `oracle-data` tip whenever a push is rejected. Each
attempt incorporates current `main` first. Conflicts in regenerated aggregates
use `main`'s version before regeneration and verification; the shared manifest
retains an append-only union of both report lists. Primary report and authored
input conflicts refuse publication and materialization until a maintainer
performs the [source-data conflict recovery](#recovering-source-data-conflicts).
Readers resolve aggregate conflicts to the published data version, which
matches the reports they load. A missing data branch is seeded from
`main`; successful pushes explicitly target `HEAD:refs/heads/oracle-data`
without force. The [manual sequence below](#manual-single-suite-publication)
packs and publishes one suite. The publisher refuses `main`, `master`, and
other targets.
The conformance ratchet is never re-pinned from that bot path. Stale suites
with `name: null` (parameter suites and `ci: manual` suites) are listed as
awaiting the manual lane, not rerun. The weekly full matrix (`comparisons.yml`)
runs every suite that does not declare `ci: manual` as a CI signal; it uploads
reports as artifacts and never commits them. Its separate scheduled KPI job
prepares the same data branch before generating `rule_verification.json` and
`rule_verification_summary.json`, and publishes only those files. A manual
dispatch of that job computes the KPI without publishing.
The affected publisher and KPI job share the `oracle-data-publication`
concurrency group, serializing their writes to the data branch.
Regenerate the map after adding a comparison:
`uv run scripts/generate_affected_map.py`.

### Manual single-suite publication

Use a clean disposable checkout of current `main` with full history and the
suite's required dependencies. Establish the published baseline before running
the producer; for example:

```bash
python3 scripts/oracle_data.py materialize --baseline
uv run scripts/run_comparison.py fiit-ecps --summary
scripts/commit_refreshed_report.sh fiit-ecps oracle-data
```

Substitute the registry suite name and its documented producer when the lane
uses a specialized live-run command. `--baseline` requires no tracked staged
or unstaged edits and records the combined snapshot in a detached local
commit. Plain `materialize` leaves `HEAD` unchanged and is insufficient for
packing a refresh after prior publication. Single-suite and `--pack` modes
refuse when the locally known `oracle-data` tip is missing from `HEAD`'s
history; packing itself never fetches. If this guard fires, save the output
for inspection, restart in a clean checkout, run `materialize --baseline`,
then rerun the producer and pack. If a remote report changes after packing,
the stale-bundle guard similarly requires regeneration and repacking.

### Recovering source-data conflicts

For a primary report conflict, follow the
[recovery procedure](../README.md#recovering-a-source-data-conflict): reconcile
current `main` into the data branch in a separate checkout, keep reviewed
`main` report corrections, regenerate and verify derived outputs, and publish
the merge with a normal push to `oracle-data`. Then rerun selection and rebuild
old bundles. Do not resolve that refusal by pushing an older bundle over the
reviewed report.

Regenerating these aggregates with the report is required because they are
*derived* from its bytes. The `oracle-data` snapshot keeps the reports,
`conformance/scoreboard.json`, detail, history, census, certificates, and served
mirrors consistent. Regeneration happens inside the publish job's push-retry
loop against the combined source and data tip, followed by the existing
staleness and publication gates (see `tests/test_commit_refreshed_report.py`).
PR CI independently validates the reviewed committed baseline using
`AXIOM_ORACLES_DATA_SOURCE=checkout`; a PR that updates baseline reports must
still regenerate their derivatives. Before publication moved off `main`,
skipping this step reddened every open PR in the 2026-07-14 income-tax incident
(#282). Regeneration also used to happen in every matrix leg, each racing its
siblings to push: with ~47 legs, each successful push invalidated every other
leg's ~4-minute attempt, and runs
36239293795 and 35958364304 lost 7 and 11 legs to the 90-minute timeout inside
that loop. Publishing once removes the race; the legs still vet their own
refresh so that a refused one fails its own leg (`tests/test_affected_rerun_publisher.py`
pins the wiring).

## Vacuous-verification gate (O3)

`scripts/check_vacuous_gate.py` (blocking in CI) enforces that every comparison
config is genuinely oracle-backed: an intentional exception must declare
`oracle: none` **with** a `reason:`, and a generic `axiom-oracles-compare` may
not compare an engine against itself. Fixture cases must declare an `expected`
outcome or opt out the same way. The same script writes
`dashboard/public/data/freshness.json` (per-suite report age + executable-surface
staleness alarms); stale executable surfaces raise a **non-blocking** dashboard
alarm, while a structurally stale committed `freshness.json` fails `--check`.

## Parameter-suite list

`parameter-oracles.yaml` is not a single-runner config — it declares a *list* of
parameter-oracle suites consumed by `scripts/run_parameter_comparisons.py`. It
self-identifies with `schema: axiom_oracles.parameter_suite_list.v1` and
`kind: parameter-suite-list`; `--list`, the affected-map generator, and the
vacuous gate branch on that marker rather than the absence of a `name:` key.
