VERDICT: APPROVE

# Round-2 blind review — axiom-oracles PR #409

Target: `1c912ab1a0cab60d9b7080ec71ff0a9d0ffe6717`
(`fed-parity/addmed-mappings`)

Base and merge-base: `98dfa9e8dcd5a227c349c697a52b91da6522eeaa`
(`origin/main`)

RuleSpec gate target: `b42b34c0a4d40dd9a17cf59e74a5129d2037601b`
(`fed-parity/addmed-se-leg`)

Oracle inspected: PolicyEngine-US 1.767.3

## Outcome

The two round-1 blockers are correctly resolved:

1. `pipeline_additional_medicare_self_employment_tax_rate` now maps to the
   exact PolicyEngine 0.009 parameter and has genuine companion evidence.
2. The guarded `federal_additional_medicare_tax` output is correctly
   `not_comparable`, with `additional_medicare_tax` retained as a P1 candidate
   and an accurate restoration condition.

There is no schema-supported conditional mapping being missed. The mapping
dataclass has no condition, precondition, domain, predicate, applicability, or
row-filter field; `_mapping_from_payload` preserves only its fixed fields and
silently discards unknown keys. `derived_expression` supports an oracle-side
formula, not a RuleSpec-domain guard. A prose caveat would therefore remain
non-executable.

No blocking finding remains. One prior nonblocking rationale wording issue
remains and is recorded below; it does not change the classification or hide a
divergence.

## Round-2 corrections

### Rate mapping is exact and tested

RuleSpec defines an entityless `Rate` parameter of `0.009`, sourced to 26 USC
1401(b)(2)(A), at
`us/policies/income_tax/additional_medicare_tax_pipeline.yaml:143-157`.
PolicyEngine-US 1.767.3 stores `0.009` at
`gov.irs.payroll.medicare.additional.rate`, metadata unit `/1`, effective from
2013, and cites both sections 3101(b)(2) and 1401(b)(2).

The mapping at `axiom_oracles/bridges/mappings/us.yaml:8141-8148` correctly uses:

- `mapping_type: parameter_value`
- `policyengine_parameter: gov.irs.payroll.medicare.additional.rate`
- `period: year`
- `comparison: rate`

No entity or currency unit belongs on this dimensionless parameter mapping.
RuleSpec commit `f9f0f22e3` adds one direct `0.009` assertion in
`amt-single-wage-se`; the gate reports `tested: true`, `test_output_count: 1`.

### Guarded combined output is correctly not comparable

RuleSpec's `federal_additional_medicare_tax` returns the sum of the wage and
self-employment legs only when its section-1401(c) ordinary-domain judgment
holds; it returns zero otherwise
(`additional_medicare_tax_pipeline.yaml:376-411`).

PolicyEngine's `additional_medicare_tax` is TaxUnit/Year/USD, but its formula
has no international-agreement/domain guard. It aggregates person-level
`payroll_tax_gross_wages` and `taxable_self_employment_income`, subtracts the
filing-status exclusion, and applies 0.009.

The companion false-domain case supplies SINGLE status, $250,000 wages, and
$138,525 taxable self-employment income, while asserting zero for RuleSpec's
public combined output. Replaying those exact facts in the cached 1.767.3
runtime returned `1696.7249755859375`, i.e. statutory $1,696.725:

```text
(250000 + 138525 - 200000) * 0.009 = 1696.725
```

Accordingly, `not_comparable` plus the exact PE candidate at P1 is truthful.
The recorded restoration condition—add an executable domain precondition or
expose a domain-unconditional RuleSpec output—is also correct.

## Per-entry findings

| RuleSpec output | Mapping | Finding |
| --- | --- | --- |
| `additional_medicare_tax_pipeline_self_employment_domain_is_valid` | `not_comparable` | Correct. PE has no section-1401(c) international-agreement/ordinary-domain judgment. |
| `federal_additional_medicare_self_employment_tax` | `not_comparable`, `additional_medicare_tax` P4 candidate | Correct. RuleSpec isolates the coordinated 0.9% self-employment leg; PE exposes only the combined additional tax. PE's `self_employment_medicare_tax` is instead the ordinary Person-level 2.9% section-1401(b)(1) tax. |
| `federal_additional_medicare_tax` | `not_comparable`, `additional_medicare_tax` P1 candidate | Correct. Entity/period/unit align inside the ordinary domain, but the executable domain guard does not. The schema cannot express that condition. |
| `federal_additional_medicare_wage_tax` | `not_comparable`, `additional_medicare_tax` P4 candidate | Correct. PE has no isolated 0.9% wage-leg output; `employee_medicare_tax` is the ordinary Person-level 1.45% tax. |
| `pipeline_additional_medicare_self_employment_joint_threshold` | `parameter_value`, exclusion `JOINT` | Correct $250,000 annual USD threshold. Its selected-threshold proxy genuinely includes a JOINT/$250,000 case. |
| `pipeline_additional_medicare_self_employment_other_threshold` | `parameter_value`, exclusion `SINGLE` | Correct $200,000 annual USD threshold. PE also stores $200,000 for head of household and surviving spouse; the proxy genuinely includes $200,000 ordinary-status cases. |
| `pipeline_additional_medicare_self_employment_separate_threshold` | `parameter_value`, exclusion `SEPARATE` | Correct $125,000 annual USD threshold, with one direct assertion. |
| `pipeline_additional_medicare_self_employment_separate_threshold_fraction` | `not_comparable` | Correct. PE stores the resulting $125,000 amount, not the statutory one-half derivation. |
| `pipeline_additional_medicare_self_employment_tax_base` | `not_comparable`, `additional_medicare_tax` P4 candidate | Correct. RuleSpec exposes an SE-only excess base after wage coordination; PE forms an unexposed combined wage-plus-SE base. |
| `pipeline_additional_medicare_self_employment_tax_rate` | `parameter_value`, additional rate | Correct exact 0.009 legal quantity and metadata, directly tested once. |
| `pipeline_additional_medicare_self_employment_threshold` | filing-status-selected `parameter_value` | Correct. RuleSpec codes 0/1/2/3/4 map to PE SINGLE/JOINT/SEPARATE/HEAD_OF_HOUSEHOLD/SURVIVING_SPOUSE, and the five PE values match. Six direct assertions exercise codes 0-3. |
| `pipeline_federal_self_employment_income_for_additional_medicare_tax_ordinary_case` | `not_comparable`, `taxable_self_employment_income` P4 candidate | Correct classification. RuleSpec exposes TaxUnit/Year/USD; PE's candidate is Person/Year/USD and no generic TaxUnit aggregate variable exists. The rationale's word “only” is imprecise, as noted below. |
| `pipeline_reduced_additional_medicare_self_employment_threshold` | `not_comparable`, `additional_medicare_tax` P4 candidate | Correct. PE applies one exclusion to combined earnings algebraically and exposes no reduced-SE-threshold surface. |
| `wages_taken_into_account_for_additional_medicare_tax` | `not_comparable`, `payroll_tax_gross_wages` P4 candidate | Correct. The PE wage concept is Person/Year/USD; RuleSpec exposes the TaxUnit aggregate, and PE has no named TaxUnit Additional-Medicare wage surface. |

The exact 1.767.3 inventory contains only one variable named for the additional
Medicare tax: `additional_medicare_tax`. The tempting adjacent variables
`payroll_tax_gross_wages`, `taxable_self_employment_income`,
`self_employment_medicare_tax`, and `employee_medicare_tax` are all
Person/Year/USD, so none rescues a `not_comparable` TaxUnit output without
papering over an entity or legal-quantity mismatch.

## Entity, period, unit, and comparison metadata

All five comparable mappings are parameter comparisons after the guarded
combined variable was correctly removed:

- The rate is entityless and dimensionless on both sides; `comparison: rate`
  and annual parameter selection are correct.
- The PE exclusion is an entityless annual USD parameter. Joint and other are
  entityless RuleSpec source parameters. Separate and selected threshold are
  TaxUnit/Year/USD RuleSpec derived outputs, compared to the same scalar
  statutory parameter; the selected mapping uses the RuleSpec filing-status
  input to choose the corresponding PE key.
- No Person target is presented as a TaxUnit comparable. Person-level PE wage
  and self-employment variables appear only as rejected candidates.

## Changed-file gate and companion evidence

The complete workflow-style gate was run against an exact tracked archive of
RuleSpec head `b42b34c0`, using this PR worktree first on `PYTHONPATH` and the
canonical nested checkout layout expected in GitHub Actions. Filtering the
exact changed pipeline file produced:

```text
changed_item_count=14
changed_status_counts={comparable: 5, known_not_comparable: 9}
changed_untested_comparable=0
changed_pending_or_unmapped=0
failures=[]
```

The full archived repository still contains unrelated declared debt
(`pending_classification: 2238` of 21,815 outputs), but none belongs to these
14 changed outputs.

Comparable companion evidence:

```text
joint threshold:    6 assertions through selected-threshold proxy
other threshold:    6 assertions through selected-threshold proxy
separate threshold: 1 direct assertion
rate:               1 direct assertion
selected threshold: 6 direct assertions
```

The generic proxy counter credits all six selected-threshold assertions to both
source thresholds, but the fixture substantively contains matching JOINT
$250,000 and ordinary-status $200,000 cases, so these are genuine proxies
rather than formal-only evidence.

## Live consumer diagnosis

The stated diagnosis is independently confirmed:

1. axiom-encode's CLI imports `build_policyengine_coverage_report` from
   `axiom_oracles.bridges.coverage`.
2. That function calls `load_policyengine_registry`.
3. The registry resolves its mapping directory package-relative to
   `axiom_oracles/bridges/mappings` and loads those YAML files.
4. axiom-encode's classifier likewise imports the bridge registry. Source
   search found no runtime loader for its legacy
   `src/axiom_encode/oracles/policyengine/mappings`.
5. Behavioral A/B proof: with all 14 legacy axiom-encode entries present but
   this PR absent, the exact pipeline fixture returned `{unmapped: 14}`. With
   this PR first on `PYTHONPATH`, the identical command returned
   `{comparable: 5, known_not_comparable: 9}`.

The earlier axiom-encode placement therefore could not satisfy the live
classifier; axiom-oracles is the required consumer-facing location.

## Containment and YAML integrity

- `1c912ab1` is two commits over base/merge-base `98dfa9e8`.
- The complete PR diff modifies only
  `axiom_oracles/bridges/mappings/us.yaml`: 131 additions, zero deletions.
- All 14 additions are `country: us`, `program: tax`.
- No schema, loader, classifier, other mapping file, or other jurisdiction's
  entry changed.
- `git diff --check` passes.
- Duplicate-key-rejecting YAML parse: 4,399 rows, comprising 4,398 exact
  `legal_id` rows and one legitimate `legal_id_prefix`
  (`us-ny:regulations/18-nycrr/387/14/a/1#`).
- Zero rows have a missing/double identity; zero duplicate legal IDs exist.
- The target slice is exactly five `parameter_value` and nine
  `not_comparable` rows.
- The packaged registry loads with zero validation issues; its focused import
  test passes (`1 passed`).

GitNexus found broad consumers for the shared loader (54 direct / 164 total
upstream dependants) and coverage builder (32 direct callers), but this PR
changes neither function—only the 14 US mapping data rows.

## NY/OH clean-main regression baseline

The requested no-stash protocol ran in the clean detached helper worktree at
exact `origin/main` `98dfa9e8`:

1. Overlay the PR mapping and run the focused NY/OH files.
2. Copy the working PR mapping aside.
3. Install the exact baseline with
   `git show HEAD:axiom_oracles/bridges/mappings/us.yaml > ...`.
4. Rerun the identical test command.
5. Copy the PR mapping back and verify byte identity, then restore the helper
   to its clean HEAD file.

Both runs returned the same result:

```text
2 failed, 7 passed
```

The identical failing node IDs and messages were:

- NY exact mapping set: canonical RuleSpec exposes 3 outputs, expected 38.
- OH exact mapping set: four expected source-hold outputs are absent.

Thus the task's four failures are four failure occurrences across the two
paired runs, not four distinct failing node IDs. They reproduce unchanged on
clean `origin/main` and are not caused by PR #409. The helper finished clean;
no shared stash operation was used.

## Nonblocking finding

`pipeline_federal_self_employment_income_for_additional_medicare_tax_ordinary_case`
says PE aggregates `taxable_self_employment_income` “only” inside
`additional_medicare_tax`. PE 1.767.3 also aggregates it internally in Vermont
child-care contributions. PE still exposes no generic TaxUnit
self-employment-income output, so the `not_comparable` classification remains
correct and no divergence is hidden. Tightening “only” would improve rationale
precision but is not merge-blocking.

## Environment and write-safety disclosures

- No PR-branch, remote, GitHub, branch/ref, primary-worktree, or shared-stash
  writes were made. Review commits exist only in this disposable detached
  worktree under `.git/review-worktrees/`.
- GitNexus built and served a usable local graph, but both its best-effort
  registration and unregister steps hit sandbox `EPERM` on
  `/Users/maxghenis/.gitnexus/registry.json`. Initial registration never
  succeeded; the untracked 85 MB local graph was removed after use, and the
  review worktree was clean afterward.
- `uv run --frozen` could not initialize its global cache at
  `/Users/maxghenis/.cache/uv/sdists-v9/.git` because of sandbox permissions.
  Existing project interpreters and the cached exact 1.767.3 wheel completed
  the YAML, source, introspection, and simulation checks.
- The generic axiom-encode venv lacked `receipt`; the complete existing venv at
  axiom-encode commit `dc8ffaa8` ran the final gate.
- A direct gate call against the noncanonical checkout basename
  `wt-addmed-se` was correctly rejected, and a first flat archive layout made
  the workflow filter match zero items. Neither was accepted as evidence; the
  successful run used an exact tracked, GHA-shaped
  `rulespec-us/rulespec-us` archive and matched all 14 items.
- The live RuleSpec worktree had unrelated untracked progress/report files.
  The gate used its exact tracked head archive, so those files were excluded.

## Recommendation

Approve PR #409. The two classification-truthfulness blockers are fixed, all
five comparables are genuine and tested, all nine not-comparables remain
truthful, containment is exact, and the focused baseline failures are
pre-existing.
