# Federal Income Tax: Axiom vs PolicyEngine

This document covers the canonical recipe for comparing Axiom-encoded RuleSpec
federal individual income tax (FIIT) outputs against PolicyEngine over the
certified pinned **Populace US** population. The committed dashboard artifact
uses the full weighted slice (`--sample-size 0`) and runs against Python 3.13,
PolicyEngine 4.11.0, PolicyEngine Core 3.26.11, and PolicyEngine-US 1.729.0 —
the model version the certified pinned Populace artifact was built with, and
the floor the tax harness now enforces (`>= 1.723`).

The comparison is one entry in the [comparisons registry](../comparisons/);
see [`comparisons/README.md`](../comparisons/README.md) for the registry
pattern and the available runner types. FIIT is **the same unified path** as
every other lane: `scripts/run_comparison.py` dispatches it, it is
auto-discovered by the weekly matrix (`.github/workflows/comparisons.yml`),
its output is normalized to the `axiom.comparison_report.v2` schema, and the
committed dashboard artifact refreshes through this path (it is the first suite
in `scripts/regenerate_all.sh`).

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
uv run scripts/run_comparison.py fiit-ecps --summary
```

That reads [`comparisons/fiit-ecps.yaml`](../comparisons/fiit-ecps.yaml),
requires the exact RuleSpec checkout and engine executable named there, runs
the comparison with the pinned PolicyEngine stack, writes a JSON report under `reports/`,
rewrites the dashboard data at
`dashboard/public/data/axiom-policyengine-fiit-ecps.json`, and prints the
headline agreement numbers.

To list every available comparison:

```bash
uv run scripts/run_comparison.py --list
```

## What runs

The harness is **`axiom-encode tax-populace-compare`**. Its shared bridge code
lives in `axiom_oracles.bridges.tax_populace`; axiom-encode imports that
canonical module. The orchestrator dispatches from the comparison YAML,
normalizes the output into the v2 schema, and lands the JSON report under
`reports/`.

### Direct `axiom-encode tax-populace-compare` calls

Invoking `axiom-encode tax-populace-compare` directly requires both
`--rulespec-root` and `--axiom-binary` and remains useful for local development
and residual triage. It is not the CI/reporting entrypoint: it does not normalize into the
`axiom.comparison_report.v2` schema, does not land in the dashboard, and is not
what refreshes the committed FIIT artifact. From now on the committed FIIT
report refreshes only through `scripts/run_comparison.py fiit-ecps` (the weekly
matrix and `regenerate_all.sh`). Use the direct command for a quick local
`--json` dump or `--tax-unit-id` residual check; use the runner for anything
that produces a reported number.

## Gotchas

The harness has four hard requirements that are not obvious:

1. **`rulespec-us` checkout must be named exactly `rulespec-us`.** The engine
   receives that country checkout directly. Workspaces, flat state roots, and
   aliases such as `rulespec-us-main` or `rulespec-us-clean` are rejected.

2. **`axiom-rules-engine` binary must already exist and be executable.** The
   registry names the exact file with `axiom_binary`; the runner neither searches
   for nor builds a substitute.

3. **RuleSpec and engine inputs are explicit.** `tax-populace-compare` requires
   the exact `rulespec-us` checkout via `--rulespec-root` and the exact
   executable via `--axiom-binary`. The bridge strips obsolete ambient-root
   variables and passes only the explicit root argument to the engine.

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

## Current residuals (June 2026)

The June 3, 2026 full ECPS run compared 299,993 values with 172 mismatches for
99.9427% agreement. CTC, standard deduction, capital-gain definitions, tax
before credits, CDCC, AOTC, capped nonrefundable credits, employee/employer
OASDI, and employee/employer Medicare all matched at 100%. The remaining
residuals are all in EITC.

Per-surface result:

| Surface | Compared values | Mismatches | Agreement |
| --- | ---: | ---: | ---: |
| EITC | 77,429 | 172 | 99.78% |
| CTC | 35,195 | 0 | 100.00% |
| Standard deduction | 21,117 | 0 | 100.00% |
| Capital-gain definitions | 14,078 | 0 | 100.00% |
| Tax before credits | 7,039 | 0 | 100.00% |
| CDCC | 42,234 | 0 | 100.00% |
| AOTC | 28,156 | 0 | 100.00% |
| Capped nonrefundable credits | 21,117 | 0 | 100.00% |
| Employee OASDI | 13,407 | 0 | 100.00% |
| Employee Medicare | 13,407 | 0 | 100.00% |
| Employer OASDI | 13,407 | 0 | 100.00% |
| Employer Medicare | 13,407 | 0 | 100.00% |

EITC residual split:

| EITC output | Compared values | Mismatches | Max absolute diff |
| --- | ---: | ---: | ---: |
| `eitc_earned_income` | 7,039 | 113 | $11,439.03 |
| `eitc_reduction` | 7,039 | 59 | $2,409.04 |

Even at high agreement, a few non-PE-bug categories of mismatch can persist:

- **OASDI 2026 base drift.** Older PolicyEngine-US releases used $186,000 as
  the Social Security contribution-and-benefit base; the encoded SSA 2026
  automatic determination is $184,500. The pinned PolicyEngine-US 1.729.0 (and
  every release at or above the runner's 1.723 floor) includes the corrected
  base.
- **EITC amount residuals.** All 113 `eitc_earned_income` residual tax units
  are joint returns. Axiom's live RuleSpec chain still has 26 USC 1402(a),
  1402(b), and 32(c)(2) shaped around aggregate TaxUnit self-employment and
  earned-income inputs, while PolicyEngine computes `self_employment_tax_ald`
  per filer and sums non-dependent filers for EITC. The residual triage
  confirms every Axiom `eitc_earned_income` value matches that aggregate
  Section 1402(b)/164(f) model; 45 of the 113 affected tax units have PE's
  Social Security self-employment taxable income capped below Medicare taxable
  self-employment income for at least one filer. Encoder guardrails now flag
  stale TaxUnit-shaped 26 USC 1402(a) money outputs and block new unit-scope
  formulas that compose those stale imports, but no live RuleSpec file has been
  replaced yet. A no-manual 26 USC 1402(a) rerun deferred because the full
  subsection has unresolved exception branches, and a narrower 26 USC
  1402(a)(12) rerun failed validation while still importing the stale aggregate
  1402(a) base. Replacing the encoded earned-income chain with PE's helper
  would be an output alignment override, so the residuals stay visible until the
  staged person-scoped re-encode can land.
- **Capital-gain definitions and tax before credits.** These now compare
  cleanly on the full ECPS slice. The tax-before-credits surface feeds the
  Section 1(j) rate calculation with source-backed filing-status and taxable
  income inputs, plus the imported Section 1(h) capital-gain definition inputs
  required by the encoded rule.
- **Payroll components.** Employee OASDI, employee Medicare, employer OASDI,
  and employer Medicare compare cleanly on the full ECPS slice. The dashboard
  now tracks these as first-class encoded coverage, backed by 26 USC 3101(a),
  3101(b)(1), 3111(a), and 3111(b).
- **CDCC.** Child and dependent care credit now runs as an emitted ECPS
  surface and compares cleanly on the full ECPS slice. The projection uses
  encoded 26 USC 21 math for qualifying counts, expense limits, rates,
  potential credit, and final credit; childcare expenses, the head/spouse
  earned-income cap, and available nonrefundable-credit limit remain explicit
  upstream boundary inputs until those chains are encoded end-to-end.
- **AOTC.** American Opportunity Credit now runs as an emitted ECPS surface and
  compares cleanly on the current dashboard ECPS cache. The projection uses
  encoded 26 USC 25A math from tuition, educational-assistance, enrollment,
  credential, institution, prior-claim, and SSN facts; income tax before
  credits, CDCC, and foreign tax credit remain explicit upstream boundary
  inputs until the full federal credit-ordering chain is encoded end-to-end.
  A newer local PolicyEngine data cache with raw AOTC fields surfaced 28
  residual output entries across 8 tax units after the duplicate-column loader
  fix: most are PolicyEngine-positive/Axiom-zero where PE uses tuition directly
  while RuleSpec subtracts educational assistance under 26 USC 25A(g)(2), and
  two are filer-identification edge cases that should be handled by a future
  25A re-encode rather than a dashboard override.
- **Capped nonrefundable credits.** Section 26 aggregate nonrefundable-credit
  sum and cap math now runs as an emitted ECPS surface and compares cleanly on
  the full ECPS slice. Upstream component credits are supplied as explicit
  boundary inputs for this aggregate surface; individual component-credit
  correctness remains with each component surface until the full federal
  credit chain is encoded end-to-end.

## CI

`.github/workflows/comparisons.yml` matrix-runs every entry in
`comparisons/*.yaml` weekly (Mondays 06:00 UTC) and on demand
(`workflow_dispatch`, with an optional `only` input to scope to one
comparison). Every run uploads the JSON as a workflow artifact and writes the
headline agreement numbers to the run summary. Reports themselves are
gitignored — the existing repo convention treats them as transient outputs,
not committed history.

The dashboard consumes the generated aggregate report directly through
`dashboard/public/data/axiom-policyengine-fiit-ecps.json`.

## See also

- [`comparisons/fiit-ecps.yaml`](../comparisons/fiit-ecps.yaml) — registry entry.
- [`comparisons/README.md`](../comparisons/README.md) — registry pattern, runner types.
- [`scripts/run_comparison.py`](../scripts/run_comparison.py) — the orchestrator.
- `reports/` — local output directory (gitignored).
- TheAxiomFoundation/axiom-encode#13 (Max's PR introducing the bridge and the
  original 99.04% number).
- TheAxiomFoundation/axiom-encode/blob/main/src/axiom_encode/cli.py — the
  `tax-populace-compare` subcommand definition.
