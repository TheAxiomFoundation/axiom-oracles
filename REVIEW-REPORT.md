VERDICT: REQUEST-CHANGES

Target reviewed: PR #416, local head `d78d46e2914a2f3a2b2d075f4dd18eb6ebe430eb`, against merge base `a62340d2f1e2873b43404478835de5577e685736`.

## Blocking finding: unresolved periods silently pass annual values through

**CRITICAL — fail-closed behavior is incomplete for non-SNAP monthly numeric outputs.**

The healthy requested-month path is correct, but period discovery can return an empty string. That unknown period is treated as though the variable were safely non-monthly:

1. The `policyengine` wrapper's variable metadata has no `definition_period` for the tested SNAP, TANF, SSI, and Medicaid variables, so `runner.py:1107-1120` ordinarily depends on the native PolicyEngine-US system.
2. If native lookup returns no period, only the four names in `_MONTHLY_NUMERIC_OUTPUT_VARIABLES` (`snap`, `snap_max_allotment`, `snap_min_allotment`, and `snap_normal_allotment`) are recognized as monthly.
3. The purported source fallback at `runner.py:1137-1165` is ineffective on PolicyEngine-US 1.767.3: `pkgutil.walk_packages(policyengine_us.variables.__path__)` returned zero modules. It therefore returns `""` for real source-backed variables including `al_tanf`, `ks_tanf_maximum_benefit`, and `ssi`.
4. Candidate selection requires an exact `"month"` at `runner.py:664-675`, so an unknown variable is never calculated in the native requested-period simulation.
5. Normalization then returns the annual output-dataset value unchanged for every period other than `"month"` at `runner.py:1038-1046`. It raises only after the variable has already been classified as monthly.

The fallback can therefore fire whenever the wrapper lacks period metadata (normal in `policyengine==4.18.9`) and the native system import/lookup cannot supply it—for example, an unavailable or transiently failing import, a version mismatch/absent native variable, or missing native metadata. Empty results are cached. The source walk does not recover them in 1.767.3.

An end-to-end fault injection forced only native period discovery to return its empty outcome while leaving PolicyEngine itself able to calculate. Results were:

| Variable | Correct 2026-01 runner value | Value after period discovery failure | Error |
|---|---:|---:|---|
| `al_tanf` | 304.0 | 3,648.0 annual sum | none |
| `ssi` | 994.0 | 11,928.0 annual sum | none |
| `snap_min_allotment` | 23.84000015258789 | 23.84000015258789 | none; protected only by the four-name allowlist |

This silently mishandles every affected non-SNAP numeric `MONTH` target used by committed suites: `al_tanf`, `az_tanf`, `de_tanf`, `ga_tanf`, `ks_tanf_maximum_benefit`, `mn_mfip`, `ny_tanf`, `wa_tanf`, and `ssi`. A direct helper probe also silently returned an annual value for monthly `wic`. The committed Medicaid MAGI outputs are not exposed to this defect because all six are boolean `YEAR` variables.

There is no executable annual `/ 12` fallback left in the runner; the only `/ 12` occurrence is explanatory text at `runner.py:1034`. However, the surviving unknown-period path is still fail-open: it silently returns an annual sum for a requested month. That violates the explicit requirement to fail closed whenever the requested month cannot genuinely be obtained.

**Required fix:** remove the name-based allowlist as a correctness boundary. Use authoritative variable definitions from the native situation simulation, or raise whenever a numeric variable's definition period cannot be resolved for a month request. Add regression tests that make native/source discovery unavailable for `ssi` and a state TANF variable and prove that no annual value is emitted.

## Healthy-path correctness

When period discovery succeeds, the implementation does calculate the requested month rather than derive it:

- `_requested_period_values()` builds a native `policyengine_us.Simulation` from the year-keyed situation and calls `simulation.calculate(variable, period=requested_period)` at `runner.py:677-718`.
- Entity values are partitioned back to their originating cases at `runner.py:736-760`; out-of-order native population IDs are covered.
- Simulation creation, definition inspection, calculation, entity-count, and missing-entity failures raise for recognized numeric monthly candidates instead of substituting an annual value.
- A year request exits before monthly simulation at `runner.py:659-661`.
- Booleans are excluded at `runner.py:667-671` and remain unchanged.
- Numeric variables authoritatively defined as `YEAR` remain unchanged.
- Fact-supplied `state_code` is preserved in the native situation even without scope metadata (`runner.py:380-387`), avoiding an accidental California default.

## Independent PolicyEngine-US 1.767.3 numeric proof

The proof used `policyengine==4.18.9`, PolicyEngine-US 1.767.3, and PolicyEngine-Core 3.30.3:

| Check | Observed runner value | Verification |
|---|---:|---|
| `snap_min_allotment`, `2026-01` | 23.84000015258789 | exact match to direct native requested-month calculation |
| `snap_min_allotment`, `2026-10` | 24.3743953704834 | exact match to direct native requested-month calculation |
| `al_tanf`, `2026-01` | 304.0 | exact match to direct native requested-month calculation |
| `ssi`, `2026-01` | 994.0 | exact match to direct native requested-month calculation |
| `income_tax` (`YEAR`), request `2026` | 3,820.0 | unchanged annual value |
| `income_tax` (`YEAR`), request `2026-01` | 3,820.0 | unchanged annual value |
| `is_snap_eligible` (boolean), `2026-01` | `True` | unchanged boolean |

A year request for the monthly `snap_min_allotment` also returned its unchanged annual sum, `287.68316650390625`, with no error. Thus the January/October COLA is selected correctly on the healthy month path, while year requests, booleans, and `YEAR`-defined variables retain their prior semantics. In particular, January is the true `23.84000015258789`, not the old calendar average `23.973597208658855`.

## Affected-suite enumeration

An exhaustive tracked-config search found 29 comparison suites with a scalar `YYYY-MM` runner period: 22 US PolicyEngine suites and seven unrelated UKMOD suites. The claimed follow-up regeneration set is complete at **19 suites**:

- SNAP (10): `al-snap-ecps`, `az-snap-ecps`, `ca-snap-ecps`, `fl-snap-ecps`, `ga-snap-ecps`, `ma-snap-ecps`, `nc-snap-ecps`, `ny-snap-ecps`, `sc-snap-ecps`, `tn-snap-ecps`.
- TANF (8): `al-tanf-ecps`, `az-tanf-ecps`, `de-tanf-ecps`, `ga-tanf-ecps`, `ks-tanf-ecps`, `mn-tanf-ecps`, `ny-tanf-ecps`, `wa-tanf-ecps`.
- SSI (1): `ssi-ecps`.

The other three US month-config suites are correctly omitted:

- `ca-tanf-ecps` and `co-tanf-ecps` target numeric `YEAR` variables.
- `medicaid-magi-co-ecps` targets six boolean `YEAR` eligibility variables.

The other seven month-period suites use the separate UKMOD adapter and cannot execute this runner: `uk-best-start-foods-ukmod`, `uk-healthy-start-ukmod`, `uk-housing-benefit-ukmod`, `uk-pension-credit-ukmod`, `uk-scottish-child-payment-ukmod`, `uk-sure-start-maternity-grant-ukmod`, and `uk-universal-credit-ukmod`.

`comparisons/ca-snap-ecps.fixtures.yaml` also contains a month but is an Axiom-only sanity fixture, not a population comparison suite. No affected committed suite is missing from the PR's regeneration list.

## Containment

The merge-base-to-head diff changes exactly:

- `axiom_oracles/adapters/policyengine/runner.py`
- `tests/test_case_schema.py`
- `tests/test_package_adapters.py`
- `tests/test_policyengine_requested_month.py` (new)

No comparison config, suite report, dashboard report, disposition, affected-map entry, program, or grid changed. Deferring report regeneration to a separate PR is correctly contained.

## Tests, Ruff, and CI coverage

- Targeted exact-environment run: `tests/test_package_adapters.py` plus `tests/test_policyengine_requested_month.py` — **14 passed**.
- Full repository run on the PR tree with the live RuleSpec checkout — **2,251 passed, 63 skipped, 6 failed**.
- All six failures reproduced on clean cached `origin/main` at `5bb07438b32f6009f36e72abaa613d4bc25f1d5d`; none is introduced by PR #416:
  - `tests/bridges/test_ca_2026_bhst_oracle.py::test_california_bhst_exact_mappings_match_rulespec_output_set`
  - `tests/bridges/test_il_2026_pilot_income_tax_oracle.py::test_il_2026_exact_mappings_match_rulespec_output_set`
  - `tests/bridges/test_il_2026_pilot_income_tax_oracle.py::test_il_2026_positive_recapture_branch_is_fixture_covered`
  - `tests/bridges/test_ny_2026_main_income_tax_oracle.py::test_ny_2026_exact_mappings_match_rulespec_output_set`
  - `tests/bridges/test_oh_2026_income_tax_oracle.py::test_oh_2026_exact_mappings_match_the_rulespec_output_set`
  - `tests/test_dashboard_loader.py::test_loader_equivalence`
- The CA/IL/NY/OH failures are pre-existing external-RuleSpec mapping drift. The dashboard-loader failure is also baseline and came from sandboxed `npm` DNS failure while fetching `esbuild`.
- Ruff 0.15.12 lint passed on both PR and clean main. Repository-wide Ruff format check is pre-existing dirty on main (200 files) and slightly improved on the PR (198 files).

The only real-PolicyEngine regression test uses `pytest.importorskip`. Ordinary PR CI installs only the `dev` extra, while PolicyEngine is in the separate `policyengine` extra, so this high-value integration test skips on the merge gate. It also covers SNAP only; there is no committed end-to-end TANF or SSI requested-month regression. This does not create the fail-open defect, but it explains why the defect is not protected by CI and should be addressed with the fix.

## Verification and sandbox disclosures

- Both local `fix/pe-runner-requested-month` refs resolve to the requested head `d78d46e2914a2f3a2b2d075f4dd18eb6ebe430eb`; all commits above that head on the disposable review branch contain only the review ledger/report.
- The cached `origin/main` is 42 commits ahead of the PR merge base. Live fetch was blocked, so staleness could not be reverified against GitHub.
- Live GitHub/fetch verification was unavailable: the sandbox could not resolve `github.com` or connect to `api.github.com`. No remote or PR write was attempted.
- Creating a fresh exact `uv` environment failed with `EPERM` while initializing `~/.cache/uv/sdists-v9/.git`. The exact-version proof instead overlaid the already-cached/extracted PolicyEngine-US 1.767.3 source on the existing environment. The source walker, native calculations, runner calculations, and version-specific definition-period checks were all exercised locally.
- The dashboard test's `npm` fetch failed with `ENOTFOUND` for `esbuild` because outbound DNS/network access was sandboxed.
- No PR-branch, remote, or GitHub state was changed.
