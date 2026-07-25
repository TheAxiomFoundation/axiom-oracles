# PR #354 repair — DONE

Date: 2026-07-25 UTC  
Branch: `fed-parity/federal-grid-suites`  
Starting HEAD: `a577132904328d626b997311a41abdd244c99a47`

This marker was written only after all seven real federal replays, the full
dated regeneration, the current CI-equivalent check battery, Ruff, full pytest,
and a final scope/provenance/count audit completed successfully.

## Finding 1 — Saver's Credit suite withdrawn

- Deleted `comparisons/us-savers-credit-grid.yaml`.
- Deleted the stale
  `dashboard/public/data/axiom-policyengine-us-savers-credit-grid.json`.
- Removed Saver's Credit from the live comparison registry, generated affected
  map, freshness data, manifest, conformance detail, and dashboard overview.
- Restored `us-pe:savers_credit` to `suite: null`. Its note states that the
  pipeline and fixture were split out of rulespec-us PR #1004 and that coverage
  awaits the Notice 2025-67 corpus chain tracked by `axiom-corpus#506`.
- Preserved PolicyEngine #9151 as historical evidence, not live coverage.
  `scripts/apply_dispositions.py --check` explicitly tolerates the retained
  no-report disposition and emits only an informational orphan note.
- The #9151 URL is in `evidence.upstream_url`; the IRS Notice and pinned
  PolicyEngine source blob are in `evidence.sources`. There is no
  `linked_issue`.

Result: seven live federal suites, no Saver's Credit coverage, and the
historical boundary evidence remains schema-valid without affecting the
scoreboard.

## Finding 2 — QBID binding repaired and replayed

Merged RuleSpec main imports all nine tax-year-2026 Rev. Proc. 2025-32
parameters and selects them at the pipeline's own filing-status boundary. The
generator binding now matches the exact 19-input fixture surface:

- Removed the retired pipeline runtime input
  `qualified_business_income_threshold_amount_2026`.
- Removed the retired statute-level `filing_status`.
- Removed the retired statute-level
  `minimum_deduction_cost_of_living_adjustment`.
- Added pipeline-level `filing_status`.
- Added the required
  `supplied_amounts_are_for_taxpayers_only_qualified_trade_or_business`
  attestation as `true`.
- Removed the misleading `threshold` field from each report case's descriptive
  inputs.
- Added a unit test that asserts the complete 19-key surface.

The registered selection remains the reviewed 11 cases. The merged companion's
four additional diagnostics—including invalid filing status 9—remain companion
tests; status 9 uses the fixture's `tables.TaxUnit` form and is not one of the
generator's 11 `record.input` cases. The new enumerated-status and attestation
guards changed none of the selected expected values.

Real replay result:

| Case | Axiom | PolicyEngine | Match |
| --- | ---: | ---: | :---: |
| `qbid-ti-limited` | 12,000 | 12,000 | yes |
| `qbid-basic-100k` | 20,000 | 20,000 | yes |
| `qbid-joint-150k` | 30,000 | 30,000 | yes |
| `qbid-phasein` | 27,500 | 27,500 | yes |
| `qbid-above-nowages` | 0 | 400 | no — dispositioned #9150 |
| `qbid-reit-only` | 4,000 | 4,000 | yes |
| `qbid-zero` | 0 | 0 | yes |
| `qbid-single-at-threshold` | 30,000 | 30,000 | yes |
| `qbid-single-one-dollar-over-threshold` | 29,999.6 | 29,999.599609375 | yes |
| `qbid-active-minimum` | 400 | 400 | yes |
| `qbid-net-capital-gain-limit` | 14,000 | 14,000 | yes |

QBID is 10/11 raw, 11/11 explained, 0 unexplained. The sole mismatch is still
`qbid-above-nowages` (Axiom 0, PolicyEngine 400); fixtures and tolerances were
not bent.

## Finding 3 — Manifest restored as a union

The starting manifest had 206 sibling reports and no federal reports. The
comparison writer preserved every one of those entries and added exactly these
seven:

- `axiom-policyengine-us-aca-ptc-grid.json`
- `axiom-policyengine-us-additional-medicare-grid.json`
- `axiom-policyengine-us-elderly-disabled-grid.json`
- `axiom-policyengine-us-llc-grid.json`
- `axiom-policyengine-us-niit-grid.json`
- `axiom-policyengine-us-qbid-grid.json`
- `axiom-policyengine-us-seca-grid.json`

Final manifest: 213 unique reports. A set comparison confirmed all 206 starting
entries survive and the only additions are the seven federal reports.

## Finding 4 — Filed PolicyEngine issues attached without Axiom attribution

- QBID uses
  `evidence.upstream_url: https://github.com/PolicyEngine/policyengine-us/issues/9150`.
- The retained Saver evidence uses
  `evidence.upstream_url: https://github.com/PolicyEngine/policyengine-us/issues/9151`.
- Pinned source-code URLs and primary instruments remain in
  `evidence.sources`.
- Neither disposition uses `linked_issue`.

`axiom_oracles/conformance/scoreboard.py` treats only a top-level
`linked_issue` pointing to an open `rulespec-*` issue as Axiom-attributed.
Final Axiom-attributed open count is therefore honestly 0.

## Finding 5 — Canonical RuleSpec SHA/tree enforced everywhere

Every live `federal-tax-liability-grid` config carries:

```yaml
rulespec_upstream_sha: 3373e8411f7e141fd50879e3de964386f606f7f6
rulespec_upstream_tree: 7e00f195ea81ff9aa21c58d53151e937d974a016
```

The restored runner guard:

- requires SHA and tree together;
- requires exactly one canonical-basename `rulespec-us` root;
- rejects malformed object IDs;
- rejects a dirty checkout;
- rejects a tree mismatch before running the generator; and
- stamps the verified upstream SHA in report provenance.

The real configured checkout passed the guard for all seven suites. A final
audit confirmed all seven committed reports cite
`3373e8411f7e141fd50879e3de964386f606f7f6`.

## Additional reviewer contract

`oracle_models_nonstatutory_amount` now requires a note naming the governing
instrument and explaining why the modeled amount is non-statutory.
`conformance/README.md` documents the same generic contract, and a negative and
positive unit test enforce it.

## Real federal replay results

All runs used `scripts/run_comparison.py`, PolicyEngine 4.18.9,
PolicyEngine-US 1.767.3, PolicyEngine Core 3.30.3, offline cached wheels, and
the guarded canonical RuleSpec checkout.

| Suite | Result | Unexplained | RuleSpec |
| --- | ---: | ---: | --- |
| ACA PTC | 6/6 | 0 | `3373e841…` |
| Additional Medicare | 5/5 | 0 | `3373e841…` |
| Elderly/disabled | 9/9 | 0 | `3373e841…` |
| LLC | 12/12 | 0 | `3373e841…` |
| NIIT | 6/6 | 0 | `3373e841…` |
| QBID | 10/11 raw; 11/11 explained | 0 | `3373e841…` |
| SECA | 6/6 | 0 | `3373e841…` |

## Dated regeneration and final numbers

Regenerated at UTC date 2026-07-25:

- dispositions;
- extracted grids;
- affected-comparison map;
- vacuous-gate freshness;
- scoreboard, detail, dashboard mirrors, and dated snapshot;
- ratchet;
- conformance burndown; and
- dashboard overview.

Final us-pe state:

| Metric | Value |
| --- | ---: |
| In scope | 127 |
| Covered | 34 |
| Unexplained | 0 |
| Axiom-attributed open | 0 |
| Oracle-attributed | 16,661 |
| Bridge artifacts | 3,340 |
| Ratchet covered floor | 34 |

The branch floor of 34 remains above `origin/main`'s committed floor of 27.

## Gate results

| Gate | Result |
| --- | --- |
| Comparison registry | PASS — seven federal suites, no Saver suite |
| Rule-verification KPI | PASS — 20,154 rules; 99.6% grounded; 98.4% manifest-backed |
| State-tax Populace contract | PASS — 43 jurisdictions |
| `apply_dispositions.py --check` | PASS |
| `extract_grids.py --check` | PASS |
| `generate_boundary_cases.py --check` | PASS |
| `generate_affected_map.py --check` | PASS — 157 suites / 167 edges |
| `check_vacuous_gate.py --check` | PASS — 213 suites |
| `generate_dashboard_overview.py --check` | PASS — 213 reports |
| `generate_conformance_universe.py --all --check` | PASS |
| `generate_conformance_compositions.py --all --check` | PASS |
| `conformance_scoreboard.py --check` | PASS |
| `conformance_ratchet.py --check` | PASS |
| `conformance_burndown.py --check` | PASS |
| Ruff | PASS |
| Full pytest | PASS — 1,791 passed, 57 skipped in 169.99s |

The universe checker fully validated UK and BE. It returned its documented
clean no-op for the local PE-UK and PE-US checkouts because their installed
versions differ from the committed universe pins. Full pytest hid the
unavailable Node/npm/esbuild toolchain from `PATH`, activating the dashboard
loader test's designed skip instead of attempting a blocked download.

## Scope and safety audit

- No pushes or GitHub writes were made.
- Root `PROGRESS.md` was preserved and extended; it was never deleted.
- No `fiit-ecps` file changed.
- No unrelated pre-existing suite or report changed. The report delta from the
  starting head is limited to the seven retained federal reports plus deletion
  of the withdrawn Saver report.
- No fixture expected value or tolerance was changed.
- Final worktree was clean before this marker was added.

## Repair commits

| Commit | Purpose |
| --- | --- |
| `8f3c3f2d` | Start and commit the PR #354 progress ledger |
| `63b0f3fc` | Withdraw the stale Saver's Credit suite |
| `41e7f92e` | Align QBID fixture binding with merged RuleSpec main |
| `35fc013a` | Restore canonical RuleSpec SHA/tree verification |
| `4d4286a2` | Real QBID replay against merged main |
| `3784be5b` | Enforce the generic nonstatutory evidence contract |
| `29244d58` | Real replay of the other six federal suites |
| `f621a461` | Regenerate the 34/127 federal conformance freeze |
| `7c8fcfb4` | Record the complete validation results |
