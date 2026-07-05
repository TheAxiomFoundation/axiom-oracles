# Comparisons registry

Each `*.yaml` in this directory declares one oracle comparison — a head-to-head
between two engines over a validation population. `scripts/run_comparison.py`
reads a config, dispatches to the right runner type, writes a JSON report, and
prints a headline summary. `.github/workflows/comparisons.yml` matrix-runs
every config in the registry on a weekly schedule.

## How to run one locally

```bash
uv run scripts/run_comparison.py fiit-ecps --summary
uv run scripts/run_comparison.py co-snap-ecps --summary
uv run scripts/run_comparison.py uk-universal-credit-efrs --summary
```

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

Invokes `axiom-encode tax-populace-compare` (registered as `tax-ecps-compare`
too — same command) via `uv run`. Builds a release `axiom-rules-engine` binary
if missing; clones `rulespec-us` fresh into a directory named exactly
`rulespec-us` (required by the engine import resolver). Honors a `pinned`
parameter that controls the PolicyEngine version stack. The runner installs the
local `axiom-encode` checkout with `--with-editable` so comparison configs can
validate unmerged harness changes before they land.

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

Invokes `axiom-encode uk-efrs-compare` via `uv run` with the pinned
PolicyEngine UK stack. Supports either one `surface` or a `surfaces` list; the
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

## Affected-comparison map + rerun (O2)

`comparisons/affected_map.json` (generated by `scripts/generate_affected_map.py`,
CI-checked with `--check`) maps each suite to the rulespec repos its concepts
exercise. The **affected-rerun** workflow
(`.github/workflows/affected-rerun.yml`, every 6h + `repository_dispatch`)
resolves each mapped repo's `main` HEAD, and `scripts/select_affected_suites.py`
selects only the suites whose report ran against an older SHA — those get rerun
and their refreshed reports committed. The weekly full matrix
(`comparisons.yml`) stays the backstop. Regenerate the map after adding a
comparison: `uv run scripts/generate_affected_map.py`.

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
