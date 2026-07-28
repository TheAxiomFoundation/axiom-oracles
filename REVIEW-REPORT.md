VERDICT: APPROVE

# Blind review: axiom-oracles PR #422

No blocking findings. The two classifications are semantically sound, the
changed-file coverage gate passes, and the source diff is contained.

## Reviewed source

- Live PR head branch: `fed-parity/atomic0-mappings`
- Immutable head: `f9fd1de2001247100b7d68db9ba59a23383fda05`
- PR base: `8b876f6fdea5551fb00d8a98ae33e22707e17c68`
- Source diff: 17 insertions in
  `axiom_oracles/bridges/mappings/us.yaml`; no other source file changes and no
  `git diff --check` errors
- RuleSpec target: `fed-parity/atomic-63c6-67h` at
  `3f933cd935e68cb1cdd50a254ab449aeabe2d468`
- RuleSpec corpus pin:
  `10142cb0f07403c2de4599c76bec01e96640fda9`
- PolicyEngine-US reviewed version: 1.767.3

## Section 63(c)(6)

The `not_comparable` classification is correct.

The retained corpus uniquely preserves the parent and four branches:

1. married filing separately where either spouse itemizes;
2. nonresident alien;
3. a section 443(a)(1) return shorter than 12 months because of a change in
   annual accounting period; and
4. an estate or trust, common trust fund, or partnership.

PolicyEngine's formula-less TaxUnit boolean/year input
`separate_filer_itemizes` covers only the first branch and is consumed by
`basic_standard_deduction`. The exact 1.767.3 source and loaded variable/entity
registry expose no genuine counterpart for branches 2–4:

- filing status has no nonresident-alien tax status; the two alien variables
  found are narrowly limited to section 25A education credits;
- there is no section 443, short-period, or accounting-period return surface;
  and
- there is no estate, trust, common-trust-fund, or partnership taxpayer entity
  or taxpayer-type judgment.

The rationale's “short-year” and “estate/trust” phrases are shorthand for the
more constrained/full statutory text, but they do not misstate the
classification. `separate_filer_itemizes` is an appropriate P4 candidate, not a
one-to-one oracle mapping for the combined judgment.

## Section 67(h)

The `parameter_value` mapping is correct.

`gov.irs.deductions.itemized.misc.applies` exists in PolicyEngine-US 1.767.3
with boolean unit and yearly period. It evaluates to Python `False` at both the
start and end of 2026, matching the RuleSpec companion's `not_holds`.
PolicyEngine's TaxUnit/year `misc_deduction` formula uses the leaf as the gate
around the complete modeled miscellaneous-deduction aggregate, rather than one
expense source or only the two-percent floor.

PolicyEngine history confirms current-law intent: the OBBBA update removed the
former 2026 reactivation, leaving the parameter false from 2018 onward. The
upstream parameter metadata still links the former section 67(g) anchor; this
is stale reference metadata, not a narrower semantic toggle, and is
non-blocking for the section 67(h) mapping.

The mapping also follows repository house style: `period: year`,
`comparison: boolean`, and omitted entity/unit. All 888 repository
`parameter_value` records omit `entity`, and the full registry validates with
zero issues.

## Gate and containment

The exact workflow-pinned changed-file classifier was run with this PR
worktree first on `PYTHONPATH` against the supplied RuleSpec head. It selected
14 outputs across the changed section 63(c), 63(c)(6), and 67(h) files:

- 13 `known_not_comparable`;
- 1 `comparable`;
- 0 missing changed files;
- 0 unmapped or pending outputs; and
- 0 incomplete or untested comparable outputs.

For the two reviewed atoms specifically:

| Atom | Status | Mapping | Companion coverage |
| --- | --- | --- | ---: |
| `63/c/6#standard_deduction_ineligible` | `known_not_comparable` | `not_comparable`; candidate `separate_filer_itemizes` | 5 outputs |
| `67/h#miscellaneous_itemized_deduction_allowed_for_individual` | `comparable` | `parameter_value`; `gov.irs.deductions.itemized.misc.applies` | 1 output |

An independent direct coverage build against the exact supplied worktree
returned the same classifications and `tested: true` values.

The changed YAML parses as a mapping list with 4,409 exact `legal_id` records
and one prefix record. There are zero duplicate exact legal IDs, each new ID
occurs once, both resolve as exact registry mappings, and registry validation
reports zero issues.

The exact-mapping-set selection against the supplied atomic RuleSpec checkout
passed (`28 passed, 2 skipped`). Against the ambient RuleSpec checkout, the
known CA/IL/NY/OH exact-set failures reproduced identically on the review
source and detached clean main (`4 failed` on each). For the explicit
source-parent baseline, only `us.yaml` was restored from `f9fd1de2^`; after the
run it was restored from review `HEAD` through an exit trap. No stash was used,
the final blob equals the immutable PR source, and both oracle worktrees are
clean.

## Limitations and write discipline

- GitNexus could not provide a current graph: the installed tool reported this
  repository unindexed, while the fallback `npx` path could not reach the
  sandbox-blocked npm registry. I did not rely on the prior reviewer's graph
  notes; direct source searches, runtime registry inspection, consumer tracing,
  and executable coverage checks supplied the impact evidence instead.
- The default local axiom-encode environment initially failed before
  classification with `ModuleNotFoundError: receipt`. An existing
  receipt-equipped environment completed the exact pinned gate with the
  intended encoder and PR sources forced through `PYTHONPATH`.
- Initial local/symlink checkout-shape simulations were rejected by the
  classifier's canonical-checkout safeguards. A temporary regular-directory
  layout matching GitHub Actions completed successfully and was removed.
- No PR-branch, remote, or GitHub writes were made. Review artifacts were
  committed only on local branch `review/pr422-f9fd1de2-blind` under
  `.git/review-worktrees/`.
