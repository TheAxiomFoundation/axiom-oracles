# Federal Income Tax: Axiom vs PolicyEngine

This document covers the canonical recipe for comparing Axiom-encoded RuleSpec
federal individual income tax (FIIT) outputs against PolicyEngine on the
Enhanced CPS. As of May 2026 the comparison runs at ~99.6% agreement across
~28k compared values (7,039 tax units), and the residual mismatches trace to a
small number of known issues, not PE bugs.

## TL;DR — run it locally

```bash
scripts/run_fiit_compare.sh --sample-size 1000
```

That clones `rulespec-us` fresh, builds the engine if needed, runs the
comparison with the latest PolicyEngine release on PyPI, writes a JSON report
to `reports/axiom-policyengine-fiit-ecps-1000-<date>.json`, and prints the
headline numbers.

For the canonical "Max's PR #13" reproduction against pinned PE versions:

```bash
scripts/run_fiit_compare.sh --sample-size 0 --pinned
```

## What runs

The harness is **`axiom-encode tax-ecps-compare`** — it lives in `axiom-encode`,
not `axiom-oracles` (the SNAP comparison uses a different code path with a
precompiled artifact; the two should converge eventually). The script in this
repo wraps the harness, takes care of the gotchas below, and lands the JSON
report under `reports/`.

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

Even at 99.6%+ agreement, two non-PE-bug categories of mismatch persist on the
full run:

- **OASDI 2026 base drift.** PolicyEngine uses $186,000 as the Social Security
  contribution-and-benefit base; the encoded SSA 2026 automatic determination
  is $184,500. These produce ~2 mismatches per surface (employee + employer
  OASDI) at the 50-unit smoke and a larger count at full scale. Not a PE bug;
  the encoded source-of-truth differs.
- **EITC tax-unit-role inference.** The harness in `axiom-encode` currently
  infers head/spouse roles from age, not from PE's `is_tax_unit_head` /
  `is_tax_unit_spouse` variables. Max maintains an uncommitted local patch in
  `src/axiom_encode/oracles/policyengine/ecps_tax.py` (and the matching test)
  that uses PE's role variables directly; with that patch applied, EITC drops
  to ~99.8%+. Without it, expect a small EITC mismatch count.

Capital-gain mismatches in earlier runs traced to PE's capital-gain inputs vs
encoded Section 1(h) definitions; recent rulespec-us tip resolves most of
them.

## CI

`.github/workflows/fiit-compare.yml` runs this script weekly (Mondays 06:00
UTC) and on demand (`workflow_dispatch`). Every run uploads the JSON as a
workflow artifact and writes the headline agreement numbers to the run
summary. Reports themselves are gitignored — the existing repo convention
treats them as transient outputs, not committed history. Wiring the result
into the Oracles dashboard is a known follow-up (the `tax-ecps-compare`
output shape differs from the per-case shape `dashboard/public/data/` uses,
so it needs a small adapter to render alongside CO SNAP).

## See also

- [`scripts/run_fiit_compare.sh`](../scripts/run_fiit_compare.sh) — the wrapper.
- `reports/` — local output directory (gitignored).
- TheAxiomFoundation/axiom-encode#13 (Max's PR introducing the bridge and the
  original 99.04% number).
- TheAxiomFoundation/axiom-encode/blob/main/src/axiom_encode/cli.py — the
  `tax-ecps-compare` subcommand definition.
