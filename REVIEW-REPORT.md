VERDICT: REQUEST-CHANGES

# Blind adversarial review — axiom-oracles PR #409

Target: `36bfd1a167b48f0bbba60af1381c02cfbf68c0ac`
(`fed-parity/addmed-mappings`)

Base: local `origin/main` at
`98dfa9e8dcd5a227c349c697a52b91da6522eeaa`

Rulespec target: `191e6c5a52e354bb1d3f424e198b8887a5db20e0`
(`fed-parity/addmed-se-leg`)

Risk: **HIGH for oracle-classification integrity.** The file-only change is
small, but one false `not_comparable` hides an exact PolicyEngine quantity and
one over-broad `direct_variable` asserts equivalence outside the domain where it
holds.

## Blocking findings

### 1. The 0.9% self-employment-leg rate is exactly comparable

`pipeline_additional_medicare_self_employment_tax_rate` is classified
`not_comparable` at `axiom_oracles/bridges/mappings/us.yaml:8144-8148`.
Its own rationale acknowledges the exact PolicyEngine parameter but rejects it
because PE does not expose a distinct pipeline-local output.

That is not a valid reason under this registry: `parameter_value` exists
precisely to compare a RuleSpec output with an oracle parameter.

- RuleSpec defines the value as `0.009`, sourced to 26 USC
  1401(b)(2)(A): `additional_medicare_tax_pipeline.yaml:143-157`.
- The cached wheel's `METADATA` identifies PolicyEngine-US **1.767.3**.
- PE 1.767.3 stores `0.009` at
  `gov.irs.payroll.medicare.additional.rate`, labels it the rate shared by
  wages and self-employment, and cites section 1401(b)(2):
  `parameters/gov/irs/payroll/medicare/additional/rate.yaml:1-13`.
- The same Axiom mappings file already classifies the underlying RuleSpec
  statute output as `parameter_value` to that exact parameter:
  `us.yaml:8230-8237`.

Required change: make the pipeline rate a `parameter_value` mapping to
`gov.irs.payroll.medicare.additional.rate`, with annual period and rate
comparison metadata. The companion test currently contains no direct assertion
of this output, so add a direct expected rate (preferred) or genuine proxy
evidence as part of the correction.

### 2. The combined tax direct mapping is only conditionally equivalent

`federal_additional_medicare_tax` is mapped directly to PE
`additional_medicare_tax` at `us.yaml:8074-8083`. Its TaxUnit/Year/USD metadata
is correct, and the formulas are algebraically identical when RuleSpec's
ordinary-case attestation holds. They are not the same output over the encoded
domain:

- RuleSpec returns wage tax plus self-employment tax only when
  `additional_medicare_tax_pipeline_self_employment_domain_is_valid` holds; it
  returns **zero** otherwise:
  `additional_medicare_tax_pipeline.yaml:376-411`.
- PE 1.767.3 has no section-1401(c) or international-agreement guard. It sums
  tax-unit member `payroll_tax_gross_wages` and
  `taxable_self_employment_income`, subtracts the filing-status exclusion, and
  applies the 0.9% rate:
  `variables/gov/irs/tax/federal_income/additional_medicare_tax.py:4-19`.
- The companion false-domain fixture uses single status, $250,000 wages, and
  $138,525 derived taxable self-employment income, but asserts RuleSpec's
  combined output is zero:
  `additional_medicare_tax_pipeline.test.yaml:294-315`.
- Replaying those exact wage/SE/filing-status facts in the cached PE 1.767.3
  runtime returned **$1,696.725**:
  `(250,000 + 138,525 - 200,000) × 0.009`.

The rationale's ordinary-domain caveat is honest prose, but
`PolicyEngineMapping` has no executable condition/domain field. A
`direct_variable` mapping cannot enforce that caveat.

Required change: classify the guarded public output as not comparable to the
adjacent PE target, expose and map an unguarded ordinary-case combined output,
or add a real conditional-mapping mechanism. A prose-only scope restriction is
not enough.

Correcting these two entries would swap which output is comparable: the
combined guarded output would leave the comparable set and the exact rate
parameter would enter it. Counts alone could still read 5/9, which is why the
current green coverage gate does not establish truthfulness.

## Per-entry findings

Evidence roots used below:

- Mapping: `axiom_oracles/bridges/mappings/us.yaml:8060-8189`
- RuleSpec:
  `/Users/maxghenis/TheAxiomFoundation/wt-addmed-se/us/policies/income_tax/additional_medicare_tax_pipeline.yaml`
- Companion:
  `/Users/maxghenis/TheAxiomFoundation/wt-addmed-se/us/policies/income_tax/additional_medicare_tax_pipeline.test.yaml`
- PE 1.767.3:
  `/Users/maxghenis/.cache/uv/archive-v0/-QudTS5FEzSKZ0Anf7ddx/policyengine_us`

| Output | Review finding |
| --- | --- |
| `additional_medicare_tax_pipeline_self_employment_domain_is_valid` | **Correct `not_comparable`.** RuleSpec exposes a TaxUnit/Year section-1401(c) ordinary-case judgment. A search of the 1.767.3 variable and parameter inventories found no totalization/international-agreement counterpart. |
| `federal_additional_medicare_self_employment_tax` | **Correct `not_comparable`.** RuleSpec isolates the coordinated 0.9% self-employment leg. PE exposes only the combined tax. `self_employment_medicare_tax` is not a substitute: it is Person/Year/USD, cites section 1401(b)(1), and applies the ordinary 2.9% Medicare rate to all taxable SE income. |
| `federal_additional_medicare_tax` | **Blocking over-broad `direct_variable`.** Entity/period/unit match PE TaxUnit/Year/USD and valid-domain formulas match, but RuleSpec's false-domain zero differs from PE's unguarded positive result. |
| `federal_additional_medicare_wage_tax` | **Correct `not_comparable`.** PE has no isolated 0.9% wage-leg variable. `employee_medicare_tax` is Person/Year/USD and applies the ordinary 1.45% rate; PE's additional tax combines wage and SE income at TaxUnit. |
| `pipeline_additional_medicare_self_employment_joint_threshold` | **Correct `parameter_value`.** RuleSpec's $250,000 joint threshold equals `additional.exclusion.JOINT`. Annual USD metadata is correct. It is indirectly but genuinely exercised through a selected-threshold status-1 assertion. |
| `pipeline_additional_medicare_self_employment_other_threshold` | **Correct `parameter_value`.** RuleSpec's “any other case” $200,000 amount equals PE `SINGLE`; PE's `HEAD_OF_HOUSEHOLD` and `SURVIVING_SPOUSE` keys also store $200,000. Selected-threshold status-0 and status-3 cases provide genuine proxy evidence. |
| `pipeline_additional_medicare_self_employment_separate_threshold` | **Correct `parameter_value`.** RuleSpec derives $125,000 and PE `SEPARATE` stores $125,000. It has one direct companion assertion. |
| `pipeline_additional_medicare_self_employment_separate_threshold_fraction` | **Correct `not_comparable`.** RuleSpec exposes the one-half derivation; PE stores only the resulting $125,000 amount, not a one-half parameter. |
| `pipeline_additional_medicare_self_employment_tax_base` | **Correct `not_comparable`.** RuleSpec exposes an SE-only excess base after wage coordination. PE forms only an unregistered combined base inside `additional_medicare_tax`; it is not the same quantity when wages already exceed the threshold. |
| `pipeline_additional_medicare_self_employment_tax_rate` | **Blocking false `not_comparable`.** Exact PE rate parameter exists, has the same value, legal source, period semantics, and dimensionless unit. |
| `pipeline_additional_medicare_self_employment_threshold` | **Correct `parameter_value`.** RuleSpec codes 0/1/2/3/4 map exactly to PE `SINGLE`/`JOINT`/`SEPARATE`/`HEAD_OF_HOUSEHOLD`/`SURVIVING_SPOUSE`; PE selects the exclusion from TaxUnit filing status. Six direct assertions cover codes 0-3; code 4 is not exercised in this companion file. |
| `pipeline_federal_self_employment_income_for_additional_medicare_tax_ordinary_case` | **Correct `not_comparable`; rationale needs precision.** RuleSpec exposes a TaxUnit/Year/USD aggregate. PE's `taxable_self_employment_income` is Person/Year/USD, with no generic TaxUnit output. The rationale overstates that PE aggregates it “only” inside `additional_medicare_tax`; PE 1.767.3 also aggregates it internally in Vermont child-care contributions. This does not create a comparable TaxUnit surface. |
| `pipeline_reduced_additional_medicare_self_employment_threshold` | **Correct `not_comparable`.** RuleSpec explicitly outputs `max(0, threshold - tax-unit wages)`. PE uses algebraically combined arithmetic and exposes no reduced-threshold variable. |
| `wages_taken_into_account_for_additional_medicare_tax` | **Correct `not_comparable`.** RuleSpec's boundary is TaxUnit/Year/USD and includes both spouses. PE `payroll_tax_gross_wages` is Person/Year/USD and is aggregated only inside calculations; mapping it directly would paper over an entity mismatch. |

The only plausible PE Medicare variables in 1.767.3 are
`additional_medicare_tax` (TaxUnit), ordinary person-level employee/employer
Medicare taxes, ordinary person-level self-employment Medicare tax,
`payroll_tax_gross_wages` (Person), and
`taxable_self_employment_income` (Person). None rescues the eight accepted
`not_comparable` entries.

## Entity, period, unit, and comparison metadata

- PE `additional_medicare_tax` was loaded from the cached 1.767.3 runtime and
  reports `tax_unit`, `year`, and `currency-USD`; the RuleSpec combined output
  is TaxUnit/Year/USD. The metadata is correct, but the domain mismatch still
  blocks direct equivalence.
- PE exclusion parameters are scalar/entityless annual USD values. The four
  threshold mappings correctly omit a PE entity, use annual period and money
  comparison, and select the same statutory amounts.
- PE's filing-status enum keys and RuleSpec's numeric convention align exactly.
- The person-level wage and SE-income variables are aggregated inside PE's
  TaxUnit formula. That makes the ordinary-domain combined result valid; it
  does not turn those Person variables into comparable TaxUnit intermediate
  outputs.

## Changed-file gate and test evidence

The gate was reproduced against a canonical archive of rulespec branch head
`191e6c5a`, with PR #409's worktree first on `PYTHONPATH`. The exact workflow
file filter matched all 14 pipeline outputs, so the pass was not vacuous:

```text
matched_items=14
statuses={'comparable': 5, 'known_not_comparable': 9}
pending=0
unmapped=0
untested_comparable=0
gate_failures=[]
```

Current comparable evidence:

```text
federal_additional_medicare_tax: 19 direct assertions
pipeline_additional_medicare_self_employment_threshold: 6 direct assertions
pipeline_additional_medicare_self_employment_separate_threshold: 1 direct assertion
pipeline_additional_medicare_self_employment_joint_threshold: 0 direct,
  proxy to selected threshold (including status 1 -> 250000)
pipeline_additional_medicare_self_employment_other_threshold: 0 direct,
  proxy to selected threshold (including status 0/3 -> 200000)
```

The joint/other proxy claims are substantively exercised, though the generic
proxy counter credits all six selected-threshold cases to each source
parameter. The pipeline's rate output has no direct assertion because it is
currently hidden as not comparable.

All 14 IDs remain in rulespec-us's `oracle-coverage-pending.yaml`. With these
mappings loaded they are stale declarations rather than
`pending_classification` statuses, so the requested changed-file status gate
passes. The downstream rulespec branch should sync/remove them after corrected
mappings land.

## Live consumer diagnosis

The stated diagnosis is independently confirmed:

1. `build_policyengine_coverage_report` in
   `axiom_oracles.bridges.coverage` calls `load_policyengine_registry`.
2. `load_policyengine_registry` resolves its mapping directory package-relative
   to `axiom_oracles/bridges/mappings` and loads those YAML files.
3. axiom-encode's CLI and classifier import the bridge coverage/registry
   functions from `axiom_oracles`; source search found no loader for
   `src/axiom_encode/oracles/policyengine/mappings`.
4. A runtime import with this PR worktree first on `PYTHONPATH` loaded all 14
   target entries from axiom-oracles and returned zero registry validation
   issues.
5. axiom-encode commit `dc8ffaa8` contains the earlier equivalent additions in
   its legacy `src/.../mappings/us.yaml`, corroborating why that attempt did not
   affect the live classifier.

## Containment and YAML integrity

- `36bfd1a1` is one commit over local `origin/main`.
- The target diff contains one path:
  `axiom_oracles/bridges/mappings/us.yaml`.
- Diff size is 131 additions, zero deletions; `git diff --check` passes.
- All 14 additions are `country: us`, `program: tax`.
- No schema, loader, classifier, or other jurisdiction's mapping file changed.
- The full YAML parses as 4,399 mapping rows: 4,398 `legal_id` rows plus one
  legitimate `legal_id_prefix` row.
- There are zero missing or duplicate IDs.
- The packaged registry resolves all 14 target IDs, has zero validation issues,
  and `test_registry_loads_packaged_mappings` passes.

## NY/OH clean-main regression baseline

The requested no-stash protocol was executed in a separate detached helper
worktree whose `HEAD` was exactly `origin/main` (`98dfa9e8`):

1. Overlay the PR `us.yaml` and run the focused NY/OH test files.
2. Copy the working mapping aside.
3. Install the clean baseline with exactly
   `git show HEAD:axiom_oracles/bridges/mappings/us.yaml > ...`.
4. Rerun the same tests.
5. Copy the PR mapping back and verify byte identity.

Both runs returned the same result:

```text
2 failed, 7 passed

NY: discovered RuleSpec output count 3, expected 38
OH: four expected source-hold outputs absent
```

The two identical node IDs failed with the PR mapping and the clean-main
mapping, so the failures are pre-existing and not caused by PR #409. The
relevant NY/OH RuleSpec files were clean at canonical sibling checkout
`c3e1c3ad`; unrelated paths in that checkout were dirty but were not read by
these tests.

The task described “4 NY/OH ... test failures.” Local evidence supports four
failure **occurrences** across the paired PR/baseline runs, but only two distinct
failing node IDs. No four-distinct-node result was reproduced. Against
`wt-addmed-se`, the same test files pass 9/9 because that branch already carries
the expected NY/OH surfaces; that is not the clean canonical baseline.

## Environment and write-safety disclosures

- No PR-branch, remote, or GitHub writes were made. All commits are local review
  ledger/report commits on detached disposable worktrees.
- No stash operation was used.
- GitNexus MCP graph tools were not exposed. The `npx gitnexus status` fallback
  produced no output in the restricted environment and was interrupted after
  60 seconds. Direct registry/coverage call-path tracing was used for this
  YAML-only change.
- One axiom-encode CLI import attempt failed because that venv lacked
  `receipt`; direct bridge imports and the repository's complete test/runtime
  environments completed the requested checks.
- The pending loader correctly rejected the noncanonical worktree name
  `wt-addmed-se`; a temporary canonical `rulespec-us` archive resolved the
  check. Temporary archives and copies created by this review were removed.
- During the final write-safety audit, the primary repository worktree had
  concurrently moved from `main` to `z1-wic-citation` and gained commit
  `24a94978` (`chore: initialize WIC citation progress`), as recorded by its
  reflog. Its untracked `.gitnexus/` metadata names that WIC commit and was
  timestamped after the concurrent checkout/commit. The review did not alter or
  remove those artifacts; both detached review worktrees remained isolated.

## Required resolution

1. Replace the rate's false `not_comparable` entry with the exact PE parameter
   mapping and add genuine companion evidence.
2. Remove the over-broad direct mapping for the fail-closed combined output, or
   introduce an enforceable ordinary-domain mapping surface.
3. Correct the “aggregates it only inside” rationale.
4. Rerun the same non-vacuous changed-file gate; expect a truthful comparable
   set with zero untested, pending, or unmapped outputs.
