VERDICT: APPROVE

PR #416 head `b5e0cd31e4252df32bc8188ad3c8c759fa74da53` makes a sound
test-environment carve-out without weakening the production fail-closed
guarantee. No supported real comparison can produce genuine PolicyEngine-US
month results while lacking both metadata sources recognized by the new guard.
No blocking finding was found.

## 1. Carve-out merits

### Why it is sound for this repository

- Production has no injected `pe` object. The CLI constructs
  `PolicyEngineRunner`, and every single-case and batch path obtains the
  official module through `_policyengine()`.
- The supported extra is `policyengine[us]==4.18.9`; its locked `us` extra
  depends on both `policyengine-us` and Core. Comparison CI installs that extra,
  while `scripts/run_comparison.py` explicitly places pinned `policyengine`,
  `policyengine-us`, and Core versions into every in-repo comparison process.
- All 24 PolicyEngine comparison configs were inspected. Twenty-two request
  `2026-01` and two request a year; all use that pinned harness.
- In the pinned official package, a normal import exposes `pe.us` only when
  `policyengine_us` is discoverable, and the resulting US module defines a
  non-null `model`. The runner rejects normal installs whose `pe.us` is `None`.
- The batch path dereferences `pe.us.model` before normalization, and exact
  month calculation directly imports `policyengine_us.Simulation`.

Two fresh-process absence probes closed the remaining edge. Hiding
`policyengine_us` made a normal official import set `pe.us=None`, which the
runner rejected before calculation. Reproducing the harness's explicit US
module import under the same absence produced a module with neither `model` nor
`calculate_household`; a month request returned no value and an engine error.
It never reached the metadata-less pass-through with a genuine PE result.

The carve-out therefore covers the intended PE-less stub environment. A real
comparison either has model/package metadata and remains fail-closed when
period lookup fails, or cannot calculate a PolicyEngine-US result at all.

### The counterargument

The helper is a structural heuristic, not a proof about arbitrary engines. An
externally injected or custom `pe.us` object could theoretically implement
`calculate_household`, return an annual sum for a genuinely monthly variable,
and expose neither `.model` nor an importable `policyengine_us` package. The new
branch would pass that value through.

That state is not constructible through any repository suite, supported install,
CLI factory, comparison harness, or official pinned PolicyEngine package. Tests
are the only code that inject model-less engines, and the affected stub returns
the annual variable `income_tax`. The theoretical custom-engine concern is
therefore not a blocking real-runtime path.

## 2. Forced-unavailable probe

Round 2's exact fault injection was re-run with PolicyEngine 4.18.9,
PolicyEngine-US 1.767.3, and Core 3.30.3. It kept real calculations available
while forcing both native and source definition-period discovery to return
empty.

- `al_tanf` at `2026-01` raised `RuntimeError`; the diagnostic names
  `al_tanf` and `2026-01`.
- `ssi` at `2026-01` independently raised `RuntimeError`; the diagnostic names
  `ssi` and `2026-01`.

Neither request returned a numeric value. Because real PE supplies metadata,
the new carve-out was not entered and round 2's fail-closed behavior remains
intact.

## 3. PE-less stub contract

`tests/test_case_schema.py` passed twice (`47 passed`): once in the available
installed environment and once in a fresh process that blocked all
`policyengine_us` imports, reproducing base CI without the optional PE extra.

The annual-variable/month-request test records every
`calculate_household` invocation. Its final ledger was exactly:

```text
[(("income_tax",), 2026)]
```

Thus the stub makes one calculation, requests year 2026, and does not enter the
old per-variable retry.

## 4. Healthy real-PE values

The same real runtime used for the forced-unavailable probe produced unchanged
SNAP values:

| Variable | Requested period | Result |
| --- | --- | ---: |
| `snap_min_allotment` | `2026-01` | `23.84000015258789` |
| `snap_min_allotment` | `2026-10` | `24.3743953704834` |

Ancillary round-2 checks also remained unchanged: `al_tanf=304.0`,
`ssi=994.0`, annual `income_tax=3820.0`, and boolean SNAP eligibility `True`.

## 5. Delta and gates

`b5e0cd31` is one non-merge commit whose sole parent is `bd9085e3`. The range
touches only:

- `axiom_oracles/adapters/policyengine/runner.py`: 27 additions, 5 deletions
- `tests/test_policyengine_requested_month.py`: 35 additions

`git diff --check` passes. Ruff 0.15.12, the exact `uv.lock` pin, reports
`All checks passed!`.

Full repository pytest completed with:

```text
1 failed, 2253 passed, 68 skipped, 104 warnings in 547.51s
```

The sole failure is the known sandboxed
`tests/test_dashboard_loader.py::test_loader_equivalence` failure: `npx` cannot
resolve the `esbuild` package (`ENOTFOUND`). There is no new failure. The other
five known clean-main failures were explicitly selected and all skipped because
the external `rulespec-us` checkout is unavailable here; the observed failure
set is therefore a strict subset of the six known failures.

The five dependency-skipped known node IDs were:

1. `tests/bridges/test_ca_2026_bhst_oracle.py::test_california_bhst_exact_mappings_match_rulespec_output_set`
2. `tests/bridges/test_il_2026_pilot_income_tax_oracle.py::test_il_2026_exact_mappings_match_rulespec_output_set`
3. `tests/bridges/test_il_2026_pilot_income_tax_oracle.py::test_il_2026_positive_recapture_branch_is_fixture_covered`
4. `tests/bridges/test_ny_2026_main_income_tax_oracle.py::test_ny_2026_exact_mappings_match_rulespec_output_set`
5. `tests/bridges/test_oh_2026_income_tax_oracle.py::test_oh_2026_exact_mappings_match_the_rulespec_output_set`

## Review discipline

The review ran in `.git/review-worktrees/pr416-b5e0cd31-confirm` on throwaway
branch `review/pr416-b5e0cd31-confirm`. The graph review integration was
unavailable in this sandbox, so production callers, configs, and execution
paths were traced directly. Temporary index files from the failed local graph
attempt were removed. Reviewed source files still match `b5e0cd31` exactly.
No PR branch, remote, or GitHub state was modified, and no remote/GitHub write
was attempted.
