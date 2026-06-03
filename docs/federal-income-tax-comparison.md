# Federal Income Tax: Axiom vs PolicyEngine

This document covers the canonical recipe for comparing Axiom-encoded RuleSpec
federal individual income tax (FIIT) outputs against PolicyEngine on the
Enhanced CPS. As of June 2, 2026 the committed dashboard artifact uses the
full weighted ECPS slice (`--sample-size 0`) and runs against Python 3.14,
PolicyEngine 4.11.0, PolicyEngine Core 3.26.11, and PolicyEngine-US 1.705.16.

The comparison is one entry in the [comparisons registry](../comparisons/);
see [`comparisons/README.md`](../comparisons/README.md) for the registry
pattern and the available runner types.

## TL;DR — run it locally

```bash
uv run scripts/run_comparison.py fiit-ecps --summary
```

That reads [`comparisons/fiit-ecps.yaml`](../comparisons/fiit-ecps.yaml),
clones `rulespec-us` fresh, builds the engine if needed, runs the comparison
with the pinned PolicyEngine stack, writes a JSON report under `reports/`,
rewrites the dashboard data at
`dashboard/public/data/axiom-policyengine-fiit-ecps.json`, and prints the
headline agreement numbers.

To list every available comparison:

```bash
uv run scripts/run_comparison.py --list
```

## What runs

The harness is **`axiom-encode tax-ecps-compare`** — it lives in `axiom-encode`,
not `axiom-oracles` (the SNAP comparison uses a different code path through the
in-repo `axiom-oracles compare` CLI; the two should converge eventually). The
orchestrator in this repo dispatches to the right harness based on the
`runner.type` field of the comparison YAML, takes care of the gotchas below,
and lands the JSON report under `reports/`.

## Gotchas

The harness has four hard requirements that are not obvious:

1. **`rulespec-us` checkout must be named exactly `rulespec-us`.** The engine
   resolves `us:` import targets by looking for a directory named
   `rulespec-us` in the search root. Anything else (`rulespec-us-main`,
   `rulespec-us-clean`, etc.) produces a different namespace and every import
   fails. The script enforces this by cloning to `<tmpdir>/rulespec-us`.

2. **`axiom-rules-engine` debug binary must exist.** The harness probes
   `$AXIOM_RULES_REPO/target/debug/axiom-rules-engine`, not the release build.
   The script runs `cargo build --bin axiom-rules-engine` if it's missing.

3. **`AXIOM_RULESPEC_REPO_ROOTS` only matters for the lower-level
   `axiom-oracles compare` path.** `tax-ecps-compare` takes
   `--rulespec-root` directly.

4. **`uv run --python 3.14 --no-project`** is the canonical invocation.
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
  "projection_notes": [...]       // human notes on boundary assumptions
}
```

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
  automatic determination is $184,500. PolicyEngine-US 1.705.16 includes the
  corrected base, and the comparison runner pins that or newer vetted releases.
- **EITC amount residuals.** `axiom-encode` now uses PE's explicit
  tax-unit-role variables for the EITC oracle projection, so the previous
  head/spouse inference mismatch is fixed as of TheAxiomFoundation/axiom-encode#74.
  Any remaining full-run EITC residuals are amount-level differences from
  Axiom computing Section 32 earned income through encoded upstream rules
  rather than passing through PE's filer-adjusted-earnings helper. Replacing
  the encoded earned-income chain with PE's helper would be an output alignment
  override, so the residuals stay visible until the upstream earned-income and
  self-employment surfaces are encoded tighter.
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
  `tax-ecps-compare` subcommand definition.
