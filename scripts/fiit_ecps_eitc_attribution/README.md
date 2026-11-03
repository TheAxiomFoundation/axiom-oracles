# fiit-ecps EITC attribution

These scripts attribute each EITC mismatch row of a fiit-ecps run to the
mechanism behind it, by counterfactual. Their output backs the EITC entries
of `dispositions/fiit-ecps.yaml` through the evidence report
`reports/fiit-ecps-eitc-attribution-2026-10-14.json`.

## Method

Each mechanism is one change to Axiom's inputs that makes Axiom see what
PolicyEngine-US 1.729.0 sees. The PolicyEngine leg stays fixed. A stage runs
the Axiom EITC surface once for every combination of its mechanisms, over
the tax units its rows belong to. Each row goes to the smallest combinations
that clear it (`minimal_sets.py`):

- one smallest combination is the row's mechanism;
- several make the row `ambiguous:`;
- none leaves the row `residual`.

| Stage | Script | Rows | Mechanisms |
| --- | --- | --- | --- |
| 1 | `counterfactuals.py` | every EITC mismatch row | `age`, `partnership`, `investment` (2^3) |
| 2 | `counterfactuals_stage2.py` | stage 1's residual rows | `se_loss`, `seca`, over all of stage 1 (2^2) |
| 3 | `counterfactuals_stage3.py` | stage 1's investment rows | the five ways the two 26 USC 32(i)(2) aggregates differ (2^5), over every other mechanism |

Each script's docstring defines its mechanisms. A stage exits 3, and its
attribution does not count, unless its checks hold:

- **Stage 1.** The baseline reproduces the full run's EITC rows and values
  on the subset of units. An explain-mode baseline on a sample of 1,500
  units also reproduces them, because the full run requested fast mode.
- **Stage 2.** The base reproduces stage 1's all-mechanism rows.
- **Stage 3:**
  - the switch model reproduces both engines' aggregates for every unit;
  - the PolicyEngine-aggregate variant clears every row;
  - the base leaves every target row and no other row of the full run.

`characterize.py` summarizes a raw report's rows by output and tests the
non-EITC surfaces' per-row signatures.

## Reproduce

Prerequisites:

- the full run's raw report under `reports/`;
- an axiom-oracles checkout carrying the bridge the run used;
- an axiom-encode checkout;
- the RuleSpec checkout the run compiled;
- the engine checkout, built.

`run_stage.sh` runs a stage in the suite runner's pinned environment: Python
3.13, PolicyEngine-US 1.729.0 from its release commit, policyengine 4.11.0,
policyengine-core 3.26.11 and spm-calculator 0.3.1. Every stage takes
`--rulespec-root <rulespec-us> --engine <axiom-rules-engine>`:

```bash
export AXIOM_ORACLES=<axiom-oracles checkout> AXIOM_ENCODE=<axiom-encode checkout>
S=scripts/fiit_ecps_eitc_attribution
RULES="--rulespec-root <rulespec-us> --engine <axiom-rules-engine>"
$S/run_stage.sh counterfactuals.py --report <raw report> $RULES --out stage1.json
$S/run_stage.sh counterfactuals_stage2.py --stage1 stage1.json $RULES --out stage2.json
$S/run_stage.sh counterfactuals_stage3.py --stage1 stage1.json --stage2 stage2.json $RULES --out stage3.json
```

Stage 2 caches the PolicyEngine data and the per-unit decomposition values
beside its output (`stage2.pe_data.pkl`), and stage 3 reads that cache. Run
the stages under launchd or another supervisor; they take tens of minutes to
hours.

Then build the evidence and the dispositions, stamp the selector bindings,
and audit:

```bash
uv run python scripts/build_fiit_ecps_eitc_dispositions.py \
  --stage1 stage1.json --stage2 stage2.json --stage3 stage3.json \
  --raw-report <raw report>
uv run scripts/stamp_selector_bindings.py fiit-ecps
uv run python scripts/build_fiit_ecps_eitc_dispositions.py --check
```

The builder reads the mismatch rows from the FULL v2 report the dashboard
copy is bound to, so republish the dashboard copy from the raw report first
(`scripts/run_comparison.py fiit-ecps --from-report <raw report>`). The
`--check` audit runs offline from committed files, and
`tests/test_fiit_ecps_eitc_attribution.py` runs it.

## The 2026-10-14 attribution

Inputs:

- the full run of 2026-10-14;
- axiom-oracles `367d86feb`, whose bridge is the one in this tree;
- axiom-encode `c6384d95`;
- rulespec-us `172bf04e`;
- axiom-rules-engine v0.1.2 `98af0dce`;
- the Populace artifact `populace-us-2024-f0af251`.

The run had 19,555 mismatch rows, 17,424 of them in EITC. Stage results:

| Stage | Rows | Result |
| --- | ---: | --- |
| 1 | 17,424 | age 192; age+investment 11; investment 4,976; partnership 4,618; residual 7,627 |
| 2 | 7,627 | seca 3,556; se_loss 971; se_loss+seca 3,100; none left residual |
| 3 | 4,987 | div_aggregate alone 4,093: 4,086 go to the dividend entry and 7 (age+investment) to the age entry; each of the other 894 has a smallest clearing set holding a PolicyEngine-US definition switch |

Every check held, with one exception. That run's stage 3 compared its base
with the target for equality, and the base also left four `eitc_eligible`
rows that the full run does not have (tax units 27227, 52975, 85432 and
95378). Its current check accepts such counterfactual-only rows and records
them in `base_counterfactual_only_rows`. Applied to that run's outputs, it
holds.

The run is a rebuild input. Rebuilding from its stage outputs gives the
committed evidence report byte for byte.

The shared `minimal_sets.attribute` replaced each stage's inline copy of
the rule after the run. Re-applied to the variant rows stages 1 and 2
stored, it reproduces their attributions exactly. Stage 3 stored only
variant counts, so its attribution was not re-derived.
