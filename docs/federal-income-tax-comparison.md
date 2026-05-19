# Federal Income Tax: Axiom vs PolicyEngine

This document covers the canonical recipe for comparing Axiom-encoded RuleSpec
federal individual income tax (FIIT) outputs against PolicyEngine on the
Enhanced CPS. As of May 2026 the comparison runs at ~99.6% agreement across
~28k compared values (7,039 tax units), and the residual mismatches trace to a
small number of known issues, not PE bugs.

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
and prints the headline agreement numbers.

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

4. **`uv run --python 3.13 --no-project`** is the canonical invocation.
   `--with /path/to/axiom-encode` installs it from the local checkout;
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

## Known residuals (May 2026)

Even at 99.6%+ agreement, a few non-PE-bug categories of mismatch persist on
the full run:

- **OASDI 2026 base drift.** PolicyEngine uses $186,000 as the Social Security
  contribution-and-benefit base; the encoded SSA 2026 automatic determination
  is $184,500. These produce ~2 mismatches per surface (employee + employer
  OASDI) at the 50-unit smoke and a larger count at full scale. Not a PE bug;
  the encoded source-of-truth differs.
- **EITC amount residuals.** `axiom-encode` now uses PE's explicit
  tax-unit-role variables for the EITC oracle projection, so the previous
  head/spouse inference mismatch is fixed as of TheAxiomFoundation/axiom-encode#74.
  Any remaining full-run EITC residuals are amount-level differences from
  Axiom computing Section 32 earned income through encoded upstream rules
  rather than passing through PE's filer-adjusted-earnings helper.
- **Capital-gain definition residuals.** Remaining differences trace to
  Section 1(h) definition boundaries, especially inputs such as the
  investment-income-election adjustment. These are semantic boundary
  differences between the encoded statutory definition and PE's helper
  variables, not evidence of a PE bug by themselves.

## CI

`.github/workflows/comparisons.yml` matrix-runs every entry in
`comparisons/*.yaml` weekly (Mondays 06:00 UTC) and on demand
(`workflow_dispatch`, with an optional `only` input to scope to one
comparison). Every run uploads the JSON as a workflow artifact and writes the
headline agreement numbers to the run summary. Reports themselves are
gitignored — the existing repo convention treats them as transient outputs,
not committed history.

Wiring the result into the Oracles dashboard is a known follow-up (the
`tax-ecps-compare` output shape differs from the per-case shape
`dashboard/public/data/` uses, so it needs a small adapter to render
alongside CO SNAP).

## See also

- [`comparisons/fiit-ecps.yaml`](../comparisons/fiit-ecps.yaml) — registry entry.
- [`comparisons/README.md`](../comparisons/README.md) — registry pattern, runner types.
- [`scripts/run_comparison.py`](../scripts/run_comparison.py) — the orchestrator.
- `reports/` — local output directory (gitignored).
- TheAxiomFoundation/axiom-encode#13 (Max's PR introducing the bridge and the
  original 99.04% number).
- TheAxiomFoundation/axiom-encode/blob/main/src/axiom_encode/cli.py — the
  `tax-ecps-compare` subcommand definition.
