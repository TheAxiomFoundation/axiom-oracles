# Federal Income Tax: Axiom vs PolicyEngine

This document covers the canonical recipe for comparing Axiom-encoded RuleSpec
federal individual income tax (FIIT) outputs against PolicyEngine over the
certified pinned **Populace US** population. The committed dashboard artifact
uses the full weighted slice (`--sample-size 0`) and runs against Python 3.13,
PolicyEngine 4.11.0, PolicyEngine Core 3.26.11, and PolicyEngine-US 1.729.0 —
the model version the certified pinned Populace artifact was built with, and
the floor the tax harness now enforces (`>= 1.723`).

Disclosure: Max Ghenis is CEO of both the Axiom Foundation and PolicyEngine.

The comparison is one entry in the [comparisons registry](../comparisons/);
see [`comparisons/README.md`](../comparisons/README.md) for the registry
pattern and the available runner types. FIIT is **the same unified path** as
every other lane: `scripts/run_comparison.py` dispatches it, its output is
normalized to the `axiom.comparison_report.v2` schema, and the committed
dashboard artifact refreshes through this path (it is the first suite in both
regeneration entry points, `scripts/regenerate_all.sh` and
`dashboard/scripts/regenerate_all.sh`). It declares `ci: manual`, so the weekly
matrix (`.github/workflows/comparisons.yml`) skips it and it refreshes only from
a supervised local run; [`comparisons/fiit-ecps.yaml`](../comparisons/fiit-ecps.yaml)
records why. Refreshed dashboard data publishes to `oracle-data`; `main` retains
the reviewed baseline.

## Population: pinned Populace, with recorded identity

The harness resolves its PolicyEngine oracle population from the **pinned**
Populace artifact by default (axiom-encode#952): a fixed Hugging Face revision,
downloaded and sha256-verified, never HF-latest unless
`AXIOM_POPULACE_ALLOW_UNPINNED` is deliberately set. That is the same
verified-artifact discipline the in-repo `axiom-oracles-compare` runner gained
in axiom-oracles#80.

Because the pin can move (a re-pin bumps the revision + sha256), the harness's
`--json` output carries a top-level `dataset_identity` block — `{country,
source, path, sha256, revision, built_with}` — naming exactly which artifact
produced the run. `scripts/run_comparison.py` threads that block onto the
generated report top-level and into each case's `metadata`, so a checked-in
FIIT report is self-documenting about its data provenance. (Older harness
output without the block falls back to the legacy `enhanced_cps` label.)

## TL;DR — run it locally

```bash
python3 scripts/oracle_data.py materialize
uv run scripts/run_comparison.py fiit-ecps --summary
```

Materialization loads the current published data into the checkout's existing
data paths before the comparison. For offline or reviewed-baseline validation,
set `AXIOM_ORACLES_DATA_SOURCE=checkout` instead.

That reads [`comparisons/fiit-ecps.yaml`](../comparisons/fiit-ecps.yaml),
clones `rulespec-us` fresh, builds the engine if needed, runs the comparison
with the pinned PolicyEngine stack, writes a JSON report under `reports/`,
rewrites the dashboard data at
`dashboard/public/data/axiom-policyengine-fiit-ecps.json`, and prints the
headline agreement numbers.

A full run takes hours. Run it under launchd (or another supervisor that
outlives the shell), and raise the engine timeouts with
`AXIOM_ENGINE_RUN_TIMEOUT_SECONDS` and `AXIOM_ENGINE_COMPILE_TIMEOUT_SECONDS`
(defaults 600 and 60 seconds; the 2026-10-14 run used 14400 and 1800). To
republish the dashboard copy from a finished run, for example after a
dispositions edit, without executing anything:

```bash
uv run scripts/run_comparison.py fiit-ecps --from-report reports/<raw report>.json
```

To list every available comparison:

```bash
uv run scripts/run_comparison.py --list
```

## What runs

The harness is **`axiom-encode tax-populace-compare`** (the CLI also registers
`tax-ecps-compare` as an alias for the identical command) — it lives in
`axiom-encode`, not `axiom-oracles`. The ~17k LOC of oracle-bridge code stays
in `axiom-encode`; A9 unified FIIT *operationally* by wrapping that harness in
the standard runner, not by moving the bridge. The orchestrator in this repo
dispatches to the right harness based on the `runner.type` field of the
comparison YAML, takes care of the gotchas below, normalizes the output into
the v2 schema, and lands the JSON report under `reports/`.

### Deprecated for CI: the direct `axiom-encode tax-populace-compare` call

Invoking `axiom-encode tax-populace-compare` directly (outside this repo's
runner) still works and is fine for local development and residual triage. But
it is **deprecated for CI / weekly reporting**: it does not normalize into the
`axiom.comparison_report.v2` schema, does not land in the dashboard, and is not
what refreshes the committed FIIT artifact. From now on the committed FIIT
report refreshes only through `scripts/run_comparison.py fiit-ecps`. The weekly
matrix uploads its output as an artifact; the affected rerun and unattended
regeneration scripts publish refreshes to `oracle-data`. Use the direct command
for a quick local
`--json` dump or `--tax-unit-id` residual check; use the runner for anything
that produces a reported number.

## Gotchas

The harness has four hard requirements that are not obvious:

1. **`rulespec-us` checkout must be named exactly `rulespec-us`.** The engine
   resolves `us:` import targets by looking for a directory named
   `rulespec-us` in the search root. Anything else (`rulespec-us-main`,
   `rulespec-us-clean`, etc.) produces a different namespace and every import
   fails. The script enforces this by cloning to `<tmpdir>/rulespec-us`.

2. **`axiom-rules-engine` release binary must exist, at the pinned commit.**
   The runner probes `$AXIOM_RULES_REPO/target/release/axiom-rules-engine`
   and runs `cargo build --bin axiom-rules-engine --release` if it's missing.
   It refuses a checkout at any commit but `axiom_rules_repo_revision`
   (v0.1.2, `98af0dce`). On 2026-10-14, engine main could not compile
   rulespec-us main's 1(h), 1(j), 32 and 25A programs.

3. **`AXIOM_RULESPEC_REPO_ROOTS` only matters for the lower-level
   `axiom-oracles compare` path.** `tax-ecps-compare` takes
   `--rulespec-root` directly.

4. **`uv run --python 3.13 --no-project`** is the canonical invocation (the
   `python` key in `fiit-ecps.yaml` is the source of truth).
   `--with-editable /path/to/axiom-encode` installs it from the local checkout;
   `--with 'policyengine[...]'` resolves PE from PyPI on every run.

## Interpreting the output

The JSON report has this top-level shape (this is *not* the same shape as the
existing `axiom-policyengine.json` in `dashboard/public/data/` — the dashboard
data-model is per-case; this report is aggregated by federal-tax surface):

```jsonc
{
  "compared_persons":   <int>,
  "compared_tax_units": <int>,
  "compared_values":    <int>,    // total scalar comparisons across surfaces
  "mismatch_count":     <int>,
  "mismatches":         [...],    // per-mismatch detail
  "output_summary":     [         // per-output rollup
    {
      "surface":          "ctc",
      "output":           "non_refundable_ctc_capped",
      "compared":         <int>,
      "mismatches":       <int>,
      "max_abs_diff":     <float>,
      "max_relative_diff":<float>
    },
    ...
  ],
  "projection_notes": [...],      // human notes on boundary assumptions
  "dataset_identity": {           // axiom-encode#952; null on pre-#952 output
    "country":    "us",
    "source":     "pinned",       // or "local-override" / "unpinned"
    "path":       null,           // set for local overrides
    "sha256":     "<12 hex>",
    "revision":   "populace-us-2024-...",
    "built_with": "<pe-us version>"
  }
}
```

The v2 report this repo generates surfaces `dataset_identity` at the report
top-level (so it survives dashboard case-row slimming) and copies it into each
case's `metadata.dataset_identity`, with `metadata.dataset` set to a
`populace-<country>@<revision>` label.

`agreement = 100 * (compared_values - mismatch_count) / compared_values`.

## Current residuals (October 2026)

The 2026-10-14 full run compared 3,881,635 values over 87,519 tax units with
19,555 mismatches, 99.50% agreement. It ran rulespec-us `172bf04e`,
axiom-rules-engine v0.1.2 `98af0dce` and PolicyEngine-US 1.729.0 over
`populace-us-2024-f0af251`. Every mismatch is dispositioned in
[`dispositions/fiit-ecps.yaml`](../dispositions/fiit-ecps.yaml), and none is
unexplained.

| Surface | Compared values | Mismatches | Agreement |
| --- | ---: | ---: | ---: |
| EITC | 962,709 | 17,424 | 98.19% |
| Tax before credits | 87,519 | 2,118 | 97.58% |
| Capital-gain definitions | 175,038 | 8 | 99.995% |
| CTC | 437,595 | 5 | 99.999% |
| Standard deduction | 262,557 | 0 | 100.00% |
| CDCC | 525,114 | 0 | 100.00% |
| AOTC | 350,076 | 0 | 100.00% |
| Capped nonrefundable credits | 262,557 | 0 | 100.00% |
| Income tax | 175,038 | 0 | 100.00% |
| Employee OASDI | 160,858 | 0 | 100.00% |
| Employee Medicare | 160,858 | 0 | 100.00% |
| Employer OASDI | 160,858 | 0 | 100.00% |
| Employer Medicare | 160,858 | 0 | 100.00% |

Each EITC row was attributed by counterfactual. Each mechanism is one change
to Axiom's inputs that makes Axiom see what PolicyEngine sees, and a row
belongs to the smallest set of changes whose re-run clears it. The evidence is
[`reports/fiit-ecps-eitc-attribution-2026-10-14.json`](../reports/fiit-ecps-eitc-attribution-2026-10-14.json)
and the tooling is in
[`scripts/fiit_ecps_eitc_attribution/`](../scripts/fiit_ecps_eitc_attribution/).

| EITC mechanism | Rows | Disposition | Tracked in |
| --- | ---: | --- | --- |
| The bridge's 26 USC 32(c)(2) self-employment input floors each filer at zero and deducts a flat 164(f) fraction | 7,627 | `bridge_artifact` | axiom-oracles#640 |
| The Populace artifact stores `partnership_se_income`, which PolicyEngine-US 1.729.0 no longer reads after #8614's rename | 4,618 | `bridge_artifact` | PolicyEngine/microcosm#35 |
| The Populace artifact's stored `dividend_income` disagrees with its components | 4,086 | `bridge_artifact` | PolicyEngine/microcosm#37 |
| PolicyEngine-US 1.729.0's 32(i)(2) investment-income definition | 890 | `upstream_engine_gap` | PolicyEngine/policyengine-us#9635 and #9567; rulespec-us#1416 |
| PolicyEngine-US 1.729.0's childless age test counts dependents | 203 | `upstream_engine_gap` | PolicyEngine/policyengine-us#9131; rulespec-us#1776 |

The other surfaces' rows are explained residuals, each re-verified on every
row:

- **Tax before credits.** All 2,118 rows have |diff| <= $5.83, with both
  signs. That rounding-scale signature is the one attributed to
  bracket-boundary rounding in July 2026.
- **Capital-gain definitions.** All 8 rows have |diff| <= $3.25, which is float
  noise.
- **CTC.** All 5 rows are exactly +$50, one $1,000 excess-AGI increment at 5%.

### Surface notes

- **OASDI 2026 base drift.** Older PolicyEngine-US releases used $186,000 as
  the Social Security contribution-and-benefit base; the encoded SSA 2026
  automatic determination is $184,500. The pinned PolicyEngine-US 1.729.0 (and
  every release at or above the runner's 1.723 floor) includes the corrected
  base.
- **Payroll components.** Employee OASDI, employee Medicare, employer OASDI,
  and employer Medicare are tracked as first-class encoded coverage, backed by
  26 USC 3101(a), 3101(b)(1), 3111(a), and 3111(b).
- **CDCC.** The projection uses encoded 26 USC 21 math for qualifying counts,
  expense limits, rates, potential credit, and final credit; childcare
  expenses, the head/spouse earned-income cap, and available
  nonrefundable-credit limit remain explicit upstream boundary inputs until
  those chains are encoded end-to-end.
- **AOTC.** The projection uses encoded 26 USC 25A math from tuition,
  educational-assistance, enrollment, credential, institution, prior-claim,
  and SSN facts; income tax before credits, CDCC, and foreign tax credit remain
  explicit upstream boundary inputs until the full federal credit-ordering
  chain is encoded end-to-end.
- **Capped nonrefundable credits.** Upstream component credits are supplied as
  explicit boundary inputs for this aggregate surface; individual
  component-credit correctness remains with each component surface until the
  full federal credit chain is encoded end-to-end.

## CI

`.github/workflows/comparisons.yml` matrix-runs every entry in
`comparisons/*.yaml` weekly (Mondays 06:00 UTC) and on demand
(`workflow_dispatch`, with an optional `only` input to scope to one
comparison), except suites that declare `ci: manual`, as fiit-ecps does. Every
run uploads the JSON as a workflow artifact and writes the headline agreement
numbers to the run summary. Raw reports are gitignored, since the repo treats
them as transient outputs. Two fiit-ecps reports are committed anyway:

- the FULL v2 report the dashboard copy's dispositions bind to;
- the EITC attribution evidence the dispositions cite.

The raw report carries 3.9 million observed-output rows (about 1 GB). Neither
the dashboard copy nor the FULL v2 report carries them. Both keep the
per-output comparison counts in `output_summary`.

The dashboard consumes the generated aggregate report directly through
`dashboard/public/data/axiom-policyengine-fiit-ecps.json`. Its build and dev
commands materialize the published `oracle-data` snapshot when run from a full
Git checkout, preserving the existing report and case-explorer URLs. Uploaded
or archived dashboards build from their bundled data; materialize in the source
checkout before uploading or manually deploying. The workflow publishes data
without deploying the dashboard. PR CI sets
`AXIOM_ORACLES_DATA_SOURCE=checkout` and validates the reviewed committed
snapshot instead. See the
[publication and rollout instructions](../README.md#generated-data-and-dashboard-publication).

## See also

- [`comparisons/fiit-ecps.yaml`](../comparisons/fiit-ecps.yaml) — registry entry.
- [`comparisons/README.md`](../comparisons/README.md) — registry pattern, runner types.
- [`scripts/run_comparison.py`](../scripts/run_comparison.py) — the orchestrator.
- `reports/` — local output directory (gitignored).
- TheAxiomFoundation/axiom-encode#13 (Max's PR introducing the bridge and the
  original 99.04% number).
- TheAxiomFoundation/axiom-encode/blob/main/src/axiom_encode/cli.py — the
  `tax-ecps-compare` subcommand definition.
