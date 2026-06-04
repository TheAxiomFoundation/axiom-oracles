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

## Supported runners

### `axiom-encode-tax-ecps-compare`

Invokes `axiom-encode tax-ecps-compare` via `uv run`. Builds a debug
`axiom-rules-engine` binary if missing; clones `rulespec-us` fresh into a
directory named exactly `rulespec-us` (required by the engine import
resolver). Honors a `pinned` parameter that controls the PolicyEngine version
stack. The runner installs the local `axiom-encode` checkout with
`--with-editable` so comparison configs can validate unmerged harness changes
before they land.

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
