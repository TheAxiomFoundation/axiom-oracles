VERDICT: REQUEST-CHANGES

# PR #417 round-2 blind review

Reviewed source object: `12dae249aeb4765204e93d344c3ca400d36f70fe`

Cached comparison base: `86be77210aa03da867a6103558cb57fe51a2ba55`

Scope: Saver's Credit and Additional Medicare Tax comparison/conformance
changes, their bridge mappings, fixtures, dispositions, generator/tests, and
generated artifacts. This was a local-only review in the disposable review
worktree; no PR branch, remote, or GitHub state was written.

## Blocking finding

### Critical — the parameter-only Additional Medicare suite does not satisfy the row's full-output coverage contract

`conformance/us-pe.yaml:39-56` defines the generated row with:

- `output_vars: [additional_medicare_tax]`;
- `in_scope: true`;
- `suite: us-additional-medicare-grid`; and
- no `comparability` override, so the schema default is `full`.

The assigned suite never evaluates or compares `additional_medicare_tax`:

- `scripts/generate_federal_tax_liability.py:2114-2165` sets
  `pe_output_variables=()` and binds only the filing-status-selected exclusion
  threshold and the 0.009 rate.
- `dashboard/public/data/axiom-policyengine-us-additional-medicare-grid.json:1000-1065`
  records only 27 threshold comparisons and one rate comparison; PolicyEngine
  `outputs` and `diagnostic_outputs` are empty.
- `axiom_oracles/bridges/mappings/us.yaml:8074-8080` correctly leaves Axiom's
  combined final tax `not_comparable`, because its section 1401(c) domain guard
  has no PolicyEngine counterpart expressible by the current registry.

This is useful parameter evidence, but it does not prove parity for the row's
household-facing liability output. The repository contract is explicit:

- PolicyEngine-US rows are generated at the granularity of the
  household-facing output variable PolicyEngine computes
  (`conformance/README.md:88-104`).
- `comparability: full` means the oracle computes entitlement/liability from
  parameters and circumstances and requires a full statutory comparison
  (`conformance/README.md:133-150`;
  `axiom_oracles/conformance/schema.py:145-183`).
- An in-scope row must have a queryable `output_var` "to compare against"
  (`axiom_oracles/conformance/schema.py:199-214`).
- The neighboring conformance precedent says coverage counts only a comparison
  proving the final public variable; component grids remain uncovered
  (`tests/test_conformance.py:655-659`).

The generated scoreboard mechanically joins a row to any live report named by
its suite. It therefore emits `covered: true` / `status: conformant` for this
row even though its note says the tax is not compared
(`conformance/detail/us-pe.json:43-58`). That is a validation hole, not
fulfillment of the full-output contract. Errors in the tax base, wage/self-
employment coordination, section 1401(c) domain behavior, or final dollar
formula would not affect any of the 28 green checks.

Required remediation is minimal and clear: leave
`us-pe:additional_medicare_tax` uncovered (`suite: null`) while retaining the
threshold/rate suite as narrower evidence, or add registry support for the
domain precondition (or another legally equivalent unconditional surface) and
compare an actual tax-dollar output with PE `additional_medicare_tax`. Marking
the row `rate_only` would not be truthful: PE-US 1.767.3 computes the full
liability from circumstances, rather than applying a rate to a frozen
award/category input.

## Verification results

### 1. Comparable-only grids and Saver mapping truthfulness

Pass.

Every actually scored concept in the two reports is registry-classified
`comparable` and targets the exact registered PolicyEngine variable or
parameter:

- Saver final: Axiom `federal_savers_credit` to PE
  `savers_credit_potential`.
- Additional Medicare threshold to
  `gov.irs.payroll.medicare.additional.exclusion`.
- Additional Medicare rate to
  `gov.irs.payroll.medicare.additional.rate`.

The new Saver mapping was checked against exact PolicyEngine-US 1.767.3 source
and the pinned RuleSpec-US source:

- `savers_credit_potential` is a TaxUnit/year/USD pre-section-26 amount that
  sums separately eligible and separately capped person legs.
- Public `savers_credit` applies the section 26 credit limit afterward, so it
  would be the wrong target for Axiom's pipeline final.
- Axiom's pipeline final is likewise the pre-section-26 TaxUnit/year/USD
  quantity.

Thus the direct comparable mapping is truthful and exposes, rather than
conceals, the known inclusive-boundary divergences.

The other ten new Saver classifications are also truthful `not_comparable`
mappings:

- PE's ordinary `adjusted_gross_income` lacks the Saver-specific sections
  911/931/933 add-back.
- The joint scale and filing-status adjustment exist separately, but PE
  exposes none of Axiom's three composed selected-ceiling outputs.
- PE exposes neither the Saver-specific filing-status-validity judgment nor
  the selected percentage as a public surface.
- Eligibility and qualified contributions are Person surfaces in PE, whereas
  Axiom exposes role-projected TaxUnit outputs.
- PE's qualified-contributions variable is pre-cap, while Axiom's
  role-projected amounts are post-cap.

The Saver grid scores only the truthful final mapping. PE `savers_credit` and
`savers_credit_credit_limit` are diagnostics, not scored outputs.

### 2. Additional Medicare honesty and row coverage

Disclosure: pass.

No Additional Medicare tax-dollar liability/output is compared. The suite
comments and description say so and explain the section 1401(c)
registry-precondition blocker
(`comparisons/us-additional-medicare-grid.yaml:3-42`). The conformance note
repeats that the combined output and isolated legs are excluded
(`conformance/us-pe.yaml:47-56`), and the generated report preserves the
limitation.

The wording "no tax-dollar output" is important: the 27 selected thresholds are
themselves USD-valued RuleSpec outputs, but none is a tax liability.

Coverage-contract answer: fail, blocking.

The row does not legitimately count as covered under its default-`full`,
`output_vars: [additional_medicare_tax]` contract. Threshold/rate-only
comparisons cannot prove the final public liability. The scoreboard's current
`covered` result is mechanical and overstates conformance.

### 3. Saver B-1 probes, exact-boundary dispositions, and section 25B citation

Pass.

All nine required B-1 probes are present and match:

| Filing status | 50% tier B-1 | 20% tier B-1 | 10% tier B-1 |
| --- | ---: | ---: | ---: |
| Single | AGI 24,249 to 1,000 | 26,249 to 400 | 40,249 to 200 |
| Joint | AGI 48,499 to 1,000 | 52,499 to 400 | 80,499 to 200 |
| Head of household | AGI 36,374 to 1,000 | 39,374 to 400 | 60,374 to 200 |

Independent RuleSpec execution, committed fixtures, and committed PE report
values agree on all nine.

The report has 34 cases, 23 raw matches, and exactly 11 mismatches. Those
mismatch IDs exactly equal the disposition selector:

- nine single/joint/head-of-household exact tier-ceiling cases; and
- the married-filing-separately and surviving-spouse first-ceiling cases.

All 11 use the same reviewed inclusive-tier-ceiling disposition. There are no
extra mismatches, unexplained cases, orphaned entries, or expired entries.

A tracked-tree search at the exact target found no `25B(d)(3)` occurrence,
including whitespace/case variants. The Saver-specific sections 911/931/933
AGI add-back is consistently cited to section 25B(e), which is also where the
[official U.S. Code text places that rule](https://uscode.house.gov/view.xhtml?edition=prelim&num=0&req=granuleid%3AUSC-prelim-title26-section25B).
The two remaining `25B(d)` strings concern contribution amounts and are
legitimate.

### 4. Self-employment scenario coverage

Pass as input-scenario coverage, with an important limitation.

The 27-case inventory spans both sides of every requested threshold, including
positive-SE wage-reduced variants:

| Status group | Wage/SE coordinated B-1 / exact / B+1 | Positive SE below unreduced threshold | Positive SE above unreduced threshold |
| --- | ---: | ---: | ---: |
| Joint, 250,000 | 249,999 / 250,000 / 250,001 | 184,700 | 277,050 |
| Separate, 125,000 | 124,999 / 125,000 / 125,001 | 92,350 | 138,525 |
| Other, 200,000 | 199,999 / 200,000 / 200,001 | 92,350 | 230,875 |

These combined amounts were independently recomputed using the encoded 0.9235
conversion from gross profit to taxable self-employment income.

This verifies scenario inventory only. Because every scenario compares the
same filing-status-selected unreduced threshold, not the reduced
self-employment threshold or a tax result, the suite does not validate that
those cases produce correct wage/SE coordination or liability. That limitation
reinforces, rather than cures, the blocking coverage-contract finding.

### 5. Generated chain, containment, and scoreboard effects

Pass mechanically.

All eight requested generated-artifact checks returned exit 0:

1. `scripts/apply_dispositions.py --check`
2. `scripts/extract_grids.py --check`
3. `scripts/generate_affected_map.py --check`
4. `scripts/check_vacuous_gate.py --check`
5. `scripts/conformance_scoreboard.py --check`
6. `scripts/conformance_ratchet.py --check`
7. `scripts/conformance_burndown.py --check`
8. `scripts/generate_dashboard_overview.py --check`

The disposition check emitted four pre-existing expiry notes for unrelated
BE/CO/NYC entries but exited successfully; none concerns either reviewed row.

Focused validation also passed:

- `206 passed, 3 skipped` across conformance, affected-map, case-grid, and
  derived-staleness tests;
- `1 passed` for the canonical RuleSpec snapshot pin invariant; and
- `6 passed` for the targeted Saver probe/cancellation, Additional Medicare
  SE-span/binding/comparable-only, and suite-registration assertions.

`git diff --check` passed.

Structural containment is clean:

- no conformance policy IDs were added or removed;
- exactly `us-pe:additional_medicare_tax` and `us-pe:savers_credit` changed in
  the source and generated detail rows;
- six peer grid YAML changes only update the shared RuleSpec SHA/tree pin;
- no third conformance row or unrelated jurisdiction changed.

The mechanical scoreboard deltas are confined to the Saver row's roll-up:

- covered 33 to 34;
- covered percent 25.9843 to 26.7717;
- oracle-attributed 16,661 to 16,672;
- uncovered 94 to 93; and
- `savers_credit` leaves the uncovered list.

Other headline values, including `unexplained_total=441` and
`axiom_attributed_open=243`, are unchanged. Generated dashboard mirrors are
byte-identical to their canonical conformance artifacts.

These clean chain/containment results do not validate the semantic decision to
keep the Additional Medicare row covered; the generators currently accept any
live named suite regardless of whether it compares the row's full output.

## Scope and limitations

- The review used the exact requested source object. The disposable branch has
  only committed `PROGRESS.md` ledger commits above it; source and generated
  artifacts remain identical to `12dae249`.
- The cached base is the exact merge base, and the target is 10 commits ahead /
  0 behind it.
- Live GitHub metadata, fresh fetches, and CI status could not be queried
  because sandbox DNS could not resolve GitHub. No conclusion about current
  remote CI is claimed.
- Exact local PolicyEngine-US 1.767.3 source and the exact pinned RuleSpec-US
  checkout were available for the mapping and execution audits.
- This is a verdict only under the repository merge freeze. No merge or PR
  mutation was attempted.

## Final disposition

Request changes solely for the critical conformance-contract defect: the
Additional Medicare parameter suite is candid and its 28 scored mappings are
valid, but it cannot cover the default-full `additional_medicare_tax` row
without a final tax-output comparison. All other requested round-2 checks pass.
