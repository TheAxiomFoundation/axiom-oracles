VERDICT: APPROVE

# Blind review — axiom-oracles PR #424

No blocking or nonblocking correctness finding was identified. The one
comparable mapping is exact at the pinned PolicyEngine version, all 16
`not_comparable` classifications withstand an adversarial counterpart search,
the 17 legal IDs exactly cover the new RuleSpec public surface, and the PR does
not introduce the five observed registry failures.

## Frozen scope

- GitHub PR: `TheAxiomFoundation/axiom-oracles#424`, open and mergeable.
- Base: `main@f8ea6027984b9da73c6f4b58d15a20b450181ac4`.
- Head branch: `fed-parity/ca-bbce-mappings`.
- Head: `b8fc73f06b48dffce269573af35653386dd84f81`.
- Final read-only GitHub recheck still reported one commit, one changed file,
  130 additions, and the same base/head SHAs.
- RuleSpec source:
  `fed-parity/ca-bbce@8d1f31d50cfa094db9206172ee56c6fb68665e7c`,
  based on `af6c57d618acff5cb268d345653ea3e4cf64feb6`.
- PolicyEngine US: exact 1.767.3 cached wheel and source commit
  `49d19b239a593dbac8920ac6fd80cfe33372343a`.
- The review used only a local disposable branch and worktree. No PR branch,
  remote, or GitHub write was made.

## Comparable mapping

`calfresh_mce_gross_income_limit_rate` is correctly mapped as a keyed
`parameter_value` to
`gov.hhs.tanf.non_cash.income_limit.gross`, key `CA`, period `year`,
comparison `rate`.

Evidence:

- The exact wheel metadata identifies `policyengine-us` version `1.767.3`.
- A runtime lookup loaded that wheel, resolved the exact parameter name, and
  returned CA `2` at both `2015-10-01` and `2026-01-01`.
- Commit-qualified `gross.yaml` has one and only one CA history entry:
  `2015-10-01: 2`. Its metadata is unit `/1`, period `year`, with
  `state_code` breakdown. There is no later CA change at the pin.
- RuleSpec
  `us-ca/policies/cdss/snap/modified-categorical-eligibility.yaml:56`
  defines a `Rate` parameter with formula `2.00`; the amount rule multiplies
  the monthly 100%-FPL standard by that rate and the conferral formula uses an
  inclusive `<=` boundary.
- The companion case at
  `modified-categorical-eligibility.test.yaml:29` asserts `2.0`; its exact
  200% case passes and its 201% case fails.
- The mapping shape matches the Pell `max_pell_limits` precedent:
  `parameter_value`, parameter path, `parameter_key`, yearly period, and rate
  comparison, with no spurious unit field.

## Sixteen not-comparable mappings

Every named PolicyEngine candidate exists at 1.767.3. Runtime/source inspection
confirmed these relevant shapes:

| Candidate | PE entity / period | Material behavior |
| --- | --- | --- |
| `is_snap_ineligible_student` | Person / year | Negative student predicate, guarded by `is_snap_higher_ed_student` |
| `meets_tanf_non_cash_gross_income_test` | SPMUnit / month | Compares a gross-income FPG ratio to a rate |
| `meets_snap_work_requirements` | SPMUnit / month | `any()` over person work eligibility |
| `is_snap_immigration_status_eligible` | Person / month | Positive federal-or-California eligibility |
| `is_tanf_non_cash_eligible` | SPMUnit / month | Exactly gross AND net AND asset |
| `meets_tanf_non_cash_asset_test` | SPMUnit / month | Assets less than or equal to the state limit |
| `meets_tanf_non_cash_net_income_test` | SPMUnit / month | Nonapplicability OR passing the federal net limit |
| `is_snap_eligible` | SPMUnit / month | Financial/categorical status plus partial person gates |
| `snap_normal_allotment` | SPMUnit / month | Downstream money amount, defined for SNAP eligibility |

Row-by-row disposition:

1. `calfresh_categorical_member_student_exclusion_applies`: correctly held.
   RuleSpec and its source rule are Person/Month; every variable in PE's
   seven-file SNAP student subtree is year-defined. No month-scoped PE student
   judgment exists.
2. `calfresh_mce_gross_income_limit`: correctly held. RuleSpec publishes a
   Household/Month Money ceiling; PE publishes a ratio pass/fail predicate,
   not the ceiling.
3. `calfresh_wic_18901_3_drug_felony_opt_out_applies`: correctly held. PE has
   no California SNAP drug-felony opt-out judgment.
4. `calfresh_mce_federal_drug_felony_exclusion_before_state_opt_out`:
   correctly held. PE has no SNAP drug-felony ineligibility fact. Its global
   AOTC conviction variable is annual and tax-credit-specific, not a SNAP
   counterpart.
5. `calfresh_mce_household_exclusion_applies`: correctly held. No PE variable
   covers the complete seven-gate household bar.
6. `calfresh_mce_member_household_exclusion_applies`: correctly held. The
   named PE work candidate is an SPMUnit aggregate with opposite eligibility
   semantics and covers only one limb.
7. `calfresh_categorical_member_ineligible_alien_exclusion_applies`:
   correctly held. The PE candidate is the positive Person/Month eligibility
   predicate. The ordinary registry runner has no generic output-negation
   transform.
8. `calfresh_categorical_member_cash_out_ssi_exclusion_applies`: correctly
   held. PE has no California cash-out SSI member exclusion.
9. `calfresh_categorical_member_institution_exclusion_applies`: correctly
   held. PE has no SNAP nonexempt-institution member judgment.
10. `calfresh_categorical_member_work_exclusion_applies`: correctly held. The
    closest Person/Month PE general-work variable is positive-polarity and
    explicitly omits some disqualifications; the named SPMUnit variable also
    includes ABAWD logic.
11. `calfresh_categorical_member_inclusion_status`: correctly held. PE has no
    Person composite over immigration, student, cash-out SSI, institution,
    and work gates. `snap_unit_size` is an integer aggregate and omits two of
    those gates.
12. `calfresh_mce_member_eligible`: correctly held. PE has no same-person
    conjunction of generic member eligibility and all five exclusions.
13. `calfresh_mce_status_conferred`: correctly held. RuleSpec requires a
    PUB 275 trigger, the gross screen, no household bar, and at least one
    fully eligible member. PE's candidate has none of those trigger/bar gates
    and instead imposes gross, net, and asset tests. Both California net-test
    applicability flags are true at the pin.
14. `calfresh_mce_resource_eligibility_test_waived`: correctly held. RuleSpec
    publishes a status-dependent waiver. PE publishes a test outcome under
    California's infinite asset limit, not a waiver fact.
15. `calfresh_mce_net_income_eligibility_test_waived`: correctly held.
    RuleSpec publishes a waiver equal to MCE status; PE actively applies and
    evaluates the net test in California.
16. `calfresh_categorical_zero_benefit_denial_applies`: correctly held.
    RuleSpec publishes the size-at-least-three categorical zero-benefit denial.
    PE eligibility does not test allotment, and its zero-minimum path can leave
    such a household eligible with a zero allotment. Neither the status nor
    money output is the denial judgment.

Commit-qualified class inventory and concept searches found no omitted
one-to-one PE surface that would justify promoting any of these rows.

## RuleSpec public surface

The set comparison is exact:

- The new modified-categorical-eligibility module contains 14 public rules.
- Its remaining declaration is
  `calfresh_mce_member_of_household`, a `data_relation`, not a public output.
- The modified FY-2026 benefit module adds three public rules: the resource
  waiver, net waiver, and zero-benefit denial.
- Expected public-output delta: 17.
- Added exact mapping records: 17.
- Missing IDs: none.
- Phantom IDs: none.

Both companion YAML files parse: 32 MCE cases and 12 benefit-composition cases.
The cases explicitly cover the rate, student month, PUB 275 gates, resource
and net waivers, and MCE/traditional-CE zero-benefit denials.

## Containment and validation

- `f8ea6027..b8fc73f0` changes only
  `axiom_oracles/bridges/mappings/us.yaml`.
- Diff: 130 insertions; `git diff --check` passes.
- All 11 mapping YAML files parse.
- Registry load: 4,742 records, comprising 4,741 exact legal IDs plus one
  prefix fallback; zero duplicate legal IDs.
- Reviewed records: 17 exact matches, one `parameter_value`, 16
  `not_comparable`, and P4 on all 16 non-comparable rows.
- Focused registry/coverage battery: 402 passed.

Full battery command:

```text
pytest tests/bridges tests/test_federal_tax_liability_generator.py -q
```

On the PR file: 5 failed, 1,268 passed, 33 skipped. Replacing only `us.yaml`
with the base blob produced the identical five failures and identical
pass/skip counts:

- California BHST exact mapping set
- Illinois pilot exact mapping set
- Illinois positive-recapture companion fixture
- New York exact mapping set
- Ohio exact mapping set

The target file was restored exactly with
`git show HEAD:axiom_oracles/bridges/mappings/us.yaml > ...`; its blob hash
matches HEAD and the worktree is clean. The 33 skips are environmental: 32
configured RuleSpec paths were absent in the available checkout and one test
lacked an importable default `policyengine_us`; the exact 1.767.3 wheel was
loaded separately for the direct runtime audits above.

## Execution disclosures

- GitNexus graph change/impact/context tools were not exposed in this session.
  This is a registry-YAML-only PR with no changed code symbols; direct registry,
  consumer, surface, and baseline tests supplied the blast-radius evidence.
- The first `uv run` could not initialize its default cache under
  `~/.cache/uv` in the sandbox. An offline retry then could not download
  PyYAML. Existing local virtual environments were used successfully.
- A direct shell GitHub lookup from a subreview was DNS-blocked, but the
  read-only GitHub connector succeeded and was rechecked before verdict.
- RuleSpec companion CLI execution was unavailable because one encoder
  environment lacked `receipt` and another rejected the nested worktree as a
  noncanonical root. The companion YAML was parsed and its assertions/formulas
  were inspected directly; PolicyEngine parameter and variable runtime checks
  did execute.

## Recommendation

Approve PR #424 at `b8fc73f06b48dffce269573af35653386dd84f81`.
