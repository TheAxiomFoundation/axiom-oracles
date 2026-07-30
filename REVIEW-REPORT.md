VERDICT: REQUEST-CHANGES

# Blind adversarial review — axiom-oracles PR #432

Target reverified read-only at closeout:

- PR: `TheAxiomFoundation/axiom-oracles#432`
- Branch: `data/ca-snap-bbce-rerun`
- Exact PR head: `eee181a30885626b1c85c4273badb732d7840ba3`
- Base: `e1374eb30c582639f8f71f9bf9c22ba93b6e36f4`
- Review worktree: `.git/review-worktrees/pr432-eee181a-blind`

The result is request-changes for two blockers. The upstream attribution,
frozen-row accounting, tolerances, guards, and numerical regeneration are
otherwise well supported.

## Blocking findings

### 1. The retained authority does not support statewide
`household_was_issued_pub_275 = true`

The PR binds the specifically named *issuance* leaf to true for every
California comparison household while deliberately leaving the distinct
online-access leaf unmapped:

- [`axiom_oracles/data/populace_input_mapping.yaml`](axiom_oracles/data/populace_input_mapping.yaml)
- [`tests/test_populace_mapping_loader.py`](tests/test_populace_mapping_loader.py)

The retained rows say:

- ACL 14-56 page 3 distinguishes “receipt of, or online access to” PUB 275,
  says receipt alone does not confer MCE, and gives paper-packet and linked-
  website alternatives.
- ACL 14-56 page 6 requires counties to document that an MCE household was
  given the brochure and supplies a corrective-benefit remedy when
  implementation failed.
- ACL 15-42 page 2 says households must be conferred MCE **if** they are
  issued or have online access to PUB 275 and satisfy the other conditions.

Those rows are in the retained corpus at
[`2026-07-28-ca-cdss-calfresh-bbce-authority.jsonl`](</Users/maxghenis/TheAxiomFoundation/axiom-corpus/.worktrees/pin-8af59216/data/corpus/provisions/us-ca/guidance/2026-07-28-ca-cdss-calfresh-bbce-authority.jsonl>).

This establishes a statewide administrative rule and a household-specific
issuance/access disjunction. It does not establish the historical fact that
the specifically named issuance limb was true for every modeled household.
The documentation and corrective-remedy language also recognizes that
delivery/implementation can fail.

Pinned RuleSpec keeps issuance and online access as separate OR operands and
contains an online-only fixture. The generic unmapped Judgment fallback is
false. The PR therefore converts:

`observed issuance OR observed online access`

into:

`true OR false`

for every household. That is an oracle-side assumption that confers MCE when
neither household fact was observed. Leaving online access unmapped makes the
semantic substitution especially clear.

The “receipt in and of itself” sentence is not a separate reason to reject
the encode: the formula retains the income, membership, exclusion, and other
eligibility gates. The blocker is treating a conditional, household-level
administrative fact as a universal fact.

Required change: remove the unconditional issuance leaf. Supply an empirical
household fact, or model a separately named and explicitly scoped composite
administrative-delivery assumption whose uncertainty is visible; then rerun
the suite and attribution from that corrected premise.

### 2. The served CA disposition artifact is stale

The final PR commit changed the source evidence URLs for the net-test and ACIN
classes to PolicyEngine issues #9175 and #9176, but did not regenerate
[`dashboard/public/data/dispositions/ca-snap-ecps.json`](dashboard/public/data/dispositions/ca-snap-ecps.json).
Six served entries still expose the superseded PolicyEngine blob URLs.

Consequences reproduced at the exact PR head:

- `emit_disposition_artifacts.py --check ca-snap-ecps` fails stale.
- `reconcile_ca_snap_423_dispositions.py --base-ref 819f370... --check`
  fails `served CA dispositions do not exactly match compacted source entries`.
- The dependent `build_ca_snap_362_dispositions.py --check --base-ref
  819f370...` entry point fails at the same assertion.
- The focused repository guard and full test suite fail for the same reason.

The PR description’s claim that both reconciliation checks and the full
`--check` chain pass is therefore false at its exact head. Regenerate the
served disposition JSON, append the final source-only change and validation
to `PROGRESS.md`, and rerun all three entry points.

## Upstream attribution: validated

The newly exposed rows are not being hidden behind an encoding label:

- Base/head reports contain 529 and 1,058 mismatch identities.
- The transition adds 735 rows across 377 cases. Of those, 725 are newly
  upstream-attributed and ten are bridge-attributed.
- A treatment that changed only
  `meets_tanf_non_cash_net_income_test = true`, with baseline and treatment
  evaluated by the same direct requested-month runner, cleared exactly 723
  rows / 370 cases: 353 paired, two eligibility-only, and 15 benefit-only.
- Independent implementations produced the same sorted identity receipt:
  `862c27d5068e3ccbff79b52876fa19f23e63a0d38e3ed6763b375e8e3bd437bd`.

Pinned PolicyEngine-US source
`49d19b239a593dbac8920ac6fd80cfe33372343a` and the installed wheel agree:

- `is_tanf_non_cash_eligible` is `gross & net & asset`.
- Both CA `net_applies` parameter files are true from 2015-10-01.
- Issues
  [#9175](https://github.com/PolicyEngine/policyengine-us/issues/9175) and
  [#9176](https://github.com/PolicyEngine/policyengine-us/issues/9176)
  accurately describe the pinned behavior, and both published repros run.

The ACIN boundary also checks out. Retained ACIN I-46-25 page 7 publishes a
two-person MCE/BBCE limit of $3,526. `ecps-69070` has annual interest
$42,303.4375, or $3,525.286458 monthly—$0.713542 inside the table. Against the
unrounded two-person monthly FPG of $1,762.50, PolicyEngine computes
`2.00016253 > 2.0` and rejects the case. That supports the two-row upstream
boundary attribution.

## No silent movement, tolerances, and guards

- Frozen #423 partition reproduced exactly: 156 vanished, 17
  current-but-dropped, 41 reclassified, and 131 kept.
- Twelve vanished rows were sampled across eligibility/benefit,
  self-employment, forward, and period classes. Each identity is absent from
  the canonical report and each household is a compact clean case
  (`r = 100.0`, `m = []`).
- Eleven reclassified rows across six cases were sampled. Canonical report,
  compact artifact, and expanded selector agree on pins and disposition.
- The 41-row replacement receipt is 20 paired eligibility, 20 paired benefit,
  and one benefit-only row, SHA-256
  `e70a713f5610eb393432df046fc8386c43cde3255769f9547ce939674b46373e`.
- The original 22-row drift receipt reconstructs to 9,033 bytes and SHA-256
  `fa54f6fdf05592da62c3c03b74264a4dfb7d9828e4f33ea169e75fc033ad3a51`.
  Its literal pin map and full-receipt expectation are unchanged.
- Comparison config, fixtures, and concept mappings are byte-identical.
  Benefit tolerance remains $7, eligibility tolerance zero,
  `MOVEMENT_THRESHOLD` remains `0.005`, and all 323 common mismatch identities
  retain identical absolute/relative tolerances.

The eight changed frozen-guard invocations were not weakened: no prior test
was removed, no skip/xfail was added, and `_require` calls increased from 106
to 113. New equal-count replacement-swap and retired-pin tamper tests add
coverage. The focused mapping/#423/#362 run produced 36 passes and one
end-to-end failure—the stale artifact—showing the retained assertion is
working.

## Regeneration and validation

The complete comparison was replayed with:

- RuleSpec-US `edc62ea566a617cf5b9c3b620f712b73c6767c94`
- clean legacy engine source
  `e19f1b7573c74512f20a6b71a0c55dbbf333d41b`
- PolicyEngine 4.18.9 / US 1.767.3 / core 3.30.3

Result: 7,101 cases, 14,202 comparisons, zero execution errors, 13,144
matches, and 1,058 mismatches. All 1,058 identity/value payloads and all 670
mismatch-case payloads match the committed canonical report exactly. All 15
compact chunks regenerate byte-for-byte; after normalizing only run-stamped
engine provenance/key order, the compact index is byte-exact too.

The full 15-command `--check` battery produced 12 passes and the three
stale-artifact failures listed above. UK and BE conformance universes were
verified; US-PE and UK-PE were explicit no-op/unverified because available
external checkouts are newer than the registry pins.

Full pytest result: **2,316 passed, 70 skipped, 3 failed, 104 warnings**.
The two non-CA failures reproduce directly on archived base
`e1374eb30c582639f8f71f9bf9c22ba93b6e36f4`:

- `npx esbuild` cannot resolve the npm registry in the sandbox.
- The unchanged federal-grid test expects commit `345c2203...` while the
  unchanged config pins equivalent-tree commit `ae64af27...`.

The third failure is the PR-specific stale served-disposition guard.

## Containment, ledger, and tooling disclosures

- Base-to-PR diff: exactly 32 modified, mode-stable paths; all are within the
  CA bridge/rerun, frozen guards, permitted shared derivatives, and ledger.
- `PROGRESS.md` is byte-prefix append-only from base through every PR and
  reviewer commit. Its PR-head tail is semantically stale because the final
  source-link commit appended no validation entry.
- The live PR head remained `eee181a3...` through closeout.
- No PR branch, remote, issue, comment, review, or GitHub write occurred.
- GitNexus built a task-local graph, but sandboxing denied registration at
  `/Users/maxghenis/.gitnexus/registry.json`. The generated 87 MB index was
  moved recoverably to `/private/tmp/pr432-review-gitnexus-index`; the review
  worktree is clean.
- Normal `uv` cache/dependency resolution was sandbox/offline-sensitive, so
  validation used the existing parent environment and byte-checked cached
  exact packages. No network-fetched dependency was substituted.
- A read-only `gh` issue lookup failed network access in one independent
  audit; the GitHub connector supplied the issue bodies and final PR metadata.
- Some exploratory counterfactual attempts hit memory/materialization limits;
  the successful targeted dataset retained production metadata parity for
  all 377 affected households and independently reproduced the 723-row
  receipt.
