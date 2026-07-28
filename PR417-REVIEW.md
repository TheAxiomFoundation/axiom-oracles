VERDICT: REQUEST-CHANGES

# PR #417 blind adversarial review

Reviewed target:
`3f59d6b596d6af3817b526bd50db9abdacb9c811`
(`fed-parity/savers-addmed-grids`), against its cached `main` parent
`43631d24c8e161ca1af36368a2b5abaa73c3a910`.

The 11 Saver's Credit dispositions are legally and numerically correct. Direct
Axiom execution, an independent section 25B calculation, and live
PolicyEngine-US 1.767.3 reproduce every asserted value and delta. The
Additional Medicare report also reproduces 18/18 matches. I nevertheless
request changes because the PR violates the required comparable-only rule,
does not cover the full requested boundary domains, contains a wrong legal
citation, and is currently conflicting with live `main`.

## Findings

### Critical — both gridded outputs fail the comparable-only rule

The exact Additional Medicare concept selected by
`comparisons/us-additional-medicare-grid.yaml:51` is
`us:policies/income_tax/additional_medicare_tax_pipeline#federal_additional_medicare_tax`.
The bridge registry explicitly classifies that same ID `not_comparable` at
`axiom_oracles/bridges/mappings/us.yaml:8074-8080`. Its rationale is material:
Axiom's output fail-closes outside the ordinary section 1401(c) domain, while
PolicyEngine's unconditional combined output has no equivalent guard.

The saver concept selected at `comparisons/us-savers-grid.yaml:51` is
`us:policies/income_tax/savers_credit_pipeline#federal_savers_credit`. A direct
registry lookup returns no mapping for that ID. The corresponding canonical
section 25B amount is itself `not_comparable` to
`savers_credit_potential` at
`axiom_oracles/bridges/mappings/us.yaml:18469-18475`. The suite openly
acknowledges that global non-equivalence at
`comparisons/us-savers-grid.yaml:16-22`.

| Gridded Axiom output | Registry result | Comparable |
|---|---|---:|
| `...savers_credit_pipeline#federal_savers_credit` | no mapping; corresponding `26/25B#savers_credit` is `not_comparable` | no |
| `...additional_medicare_tax_pipeline#federal_additional_medicare_tax` | `mapping_type: not_comparable` | no |

A prose restriction to selected ordinary-domain or fixture-bound cases does
not make an unmapped or globally `not_comparable` output comparable in the
machine-readable bridge registry. The generator bypasses the registry, and
`tests/test_conformance.py` tests the explanatory note rather than enforcing
comparability. The PR therefore counts two prohibited concepts toward coverage
and moves `us-pe:savers_credit` to covered.

Before either row is counted as covered, expose a globally equivalent output
or implement a machine-enforced conditional-domain mapping. Add an invariant
that every gridded concept used to cover a row resolves to a mapping whose
`comparable` property is true.

### Should address — Saver's Credit omits all nine below-adjacent probes

The task requires both sides and the exact value of every tier boundary. The
grid has exact and one-dollar-over cases, but none of the nine boundaries has
the local one-dollar-below probe needed to test its other side:

| Filing category | Boundary | Missing below | Exact | Above |
|---|---:|---:|---:|---:|
| Single | $24,250 | $24,249 | present | $24,251 |
| Single | $26,250 | $26,249 | present | $26,251 |
| Single | $40,250 | $40,249 | present | $40,251 |
| Joint | $48,500 | $48,499 | present | $48,501 |
| Joint | $52,500 | $52,499 | present | $52,501 |
| Joint | $80,500 | $80,499 | present | $80,501 |
| Head of household | $36,375 | $36,374 | present | $36,376 |
| Head of household | $39,375 | $39,374 | present | $39,376 |
| Head of household | $60,375 | $60,374 | present | $60,376 |

The other requested saver dimensions do pass: all five filing categories
appear; all nine exact and upper-adjacent values appear; the joint
$5,000 + $5,000 contribution case proves separate per-individual caps; the
section 911 add-back case is present; and age, student, and dependent screens
are present.

### Should address — Additional Medicare does not span positive SE income around every threshold

All 18 selected cases are within the ordinary section 1401(c) domain and all
18 values match, but the required self-employment threshold coverage is
incomplete.

Reading “SE income above/below each threshold” as positive taxable SE income
itself:

| Threshold category | Below | Above | Missing |
|---|---:|---:|---|
| Joint, $250,000 | no | yes | below |
| Married filing separately, $125,000 | yes | no | above |
| Other, $200,000 | yes | no | above |

Reading it as wages plus positive coordinated taxable SE income:

| Threshold category | Below | Exact | Above | Missing |
|---|---:|---:|---:|---|
| Joint, $250,000 | no | no | yes | below and exact |
| Married filing separately, $125,000 | no | no | yes | below and exact |
| Other, $200,000 | no | yes | yes | below |

The suite does cover partial wage consumption, full wage consumption, the
reduced-threshold floor at zero, a self-employment loss, two positive SE
earners in one joint tax unit, and the ordinary section 1401(c) domain. Those
successes do not fill the missing required threshold probes.

### Critical — the section 911/931/933 rule is cited to the wrong subsection

`comparisons/us-savers-grid.yaml:29-32` and the generated diagnostic note at
`scripts/generate_federal_tax_liability.py:2294-2297` call the add-back
“section 25B(d)(3).” The current statute places the rule in **26 USC 25B(e)**:
AGI is determined without regard to sections 911, 931, and 933. Subsection (d)
instead concerns qualified retirement savings contributions and
distributions.

The pinned RuleSpec implementation uses the correct subsection and computes
the right amount; this is a report/config citation defect, not an Axiom
arithmetic defect. Replace both references with `section 25B(e)` and
regenerate.

### Operational blocker — the live PR is reported conflicting

A successful read-only GitHub query during this review returned:

```text
headRefOid:       3f59d6b596d6af3817b526bd50db9abdacb9c811
mergeStateStatus: DIRTY
mergeable:        CONFLICTING
state:            OPEN
```

The exact head's `test` and `gettsim-live` jobs are both `SUCCESS`, but GitHub's
reported conflict must be resolved or shown stale and the resulting head
reviewed again. The reviewed merge commit contains
`43631d24...` as its cached-main second parent; intermittent live access did
not establish why GitHub simultaneously reports `DIRTY` / `CONFLICTING`.

## Legal truth of all 11 saver dispositions

### Sources and method

The exact RuleSpec checkout is clean at
`dcbae4344c522b4ad8004169316266cbc153186f`, tree
`7ee3ca44edd11cdaaf5d074a6a2a6c32d2f25dfb`. Its toolchain pins
axiom-corpus
`db12795577c5809009168982cf8a72fb58440620`.

The retained official Notice PDF has SHA-256
`1eea8f141b0cddd182f9f09b3bc8ffad683d27ceb806dfc6da126811dc0a1f8d`.
It contains the same nine 2026 limits published in
[IRS Notice 2025-67](https://www.irs.gov/irb/2025-49_IRB): joint
$48,500 / $52,500 / $80,500; head of household
$36,375 / $39,375 / $60,375; all other taxpayers
$24,250 / $26,250 / $40,250.

[26 USC 25B](https://uscode.house.gov/view.xhtml?edition=prelim&num=0&req=granuleid%3AUSC-prelim-title26-section25B)
applies the percentage to each eligible individual's contributions up to
$2,000, uses inclusive “not over” ceilings, and puts the sections 911/931/933
AGI rule in subsection (e).

For all 25 cases, `review-artifacts/recompute_savers.py`:

1. executes the compiled pinned RuleSpec with the local released Axiom binary;
2. evaluates live PolicyEngine with exact runtime versions
   `policyengine==4.18.9`, `policyengine-us==1.767.3`, and
   `policyengine-core==3.30.3`; and
3. independently calculates modified AGI, inclusive rate, each $2,000 cap,
   eligibility, and final section 25B amount.

Every directly executed Axiom intermediate and final output equals the
independent statutory calculation. The 11 disposition rows are:

| Case | Exact §25B AGI | Inclusive rate | Contribution base | Statute | Axiom | PE 1.767.3 | Axiom − PE |
|---|---:|---:|---:|---:|---:|---:|---:|
| Single, 50% ceiling | $24,250 | 50% | $2,000 | $1,000 | $1,000 | $400 | $600 |
| Single, 20% ceiling | $26,250 | 20% | $2,000 | $400 | $400 | $200 | $200 |
| Single, 10% ceiling | $40,250 | 10% | $2,000 | $200 | $200 | $0 | $200 |
| Joint, 50% ceiling | $48,500 | 50% | $2,000 | $1,000 | $1,000 | $400 | $600 |
| Joint, 20% ceiling | $52,500 | 20% | $2,000 | $400 | $400 | $200 | $200 |
| Joint, 10% ceiling | $80,500 | 10% | $2,000 | $200 | $200 | $0 | $200 |
| Head of household, 50% ceiling | $36,375 | 50% | $2,000 | $1,000 | $1,000 | $400 | $600 |
| Head of household, 20% ceiling | $39,375 | 20% | $2,000 | $400 | $400 | $200 | $200 |
| Head of household, 10% ceiling | $60,375 | 10% | $2,000 | $200 | $200 | $0 | $200 |
| MFS, all-other 50% ceiling | $24,250 | 50% | $2,000 primary | $1,000 | $1,000 | $400 | $600 |
| Surviving spouse, all-other 50% ceiling | $24,250 | 50% | $2,000 | $1,000 | $1,000 | $400 | $600 |

These are exactly the five 50%-ceiling deltas of $600, three 20%-ceiling
deltas of $200, and three 10%-ceiling deltas of $200 asserted in
`dispositions/us-savers-grid.yaml`.

### Adversarial checks for a masked Axiom defect

- The pinned Axiom composition uses inclusive `<=` tests at all three ceilings.
- It calculates `min(max(0, contribution), 2000)` independently for primary
  and spouse, then includes only eligible legs. The joint
  `$5,000 + $5,000` case directly returned two $2,000 bases and a $2,000
  credit at 50%; live PE returned the same.
- In the MFS case, Axiom caps the supplied spouse contribution but correctly
  excludes the spouse from the non-joint credit, yielding only the primary
  $1,000. PE returns $400 because of the equality defect, not because of a
  contribution-base difference.
- In the section 911 case, Axiom directly returned modified AGI
  `$24,250 + $1 = $24,251`, a 20% rate, and a $400 credit. PE omits the
  add-back but also returns $400 because its exclusive digitization moves
  exact $24,250 into the 20% tier. The committed report correctly calls this
  an offsetting-error match, apart from the wrong subsection citation.
- All three Axiom eligibility-screen cases return zero.

No disposition papers over an Axiom amount, cap, eligibility, or modified-AGI
bug. The live PE behavior reproduces the mechanism attributed to
[PolicyEngine-US issue #9151](https://github.com/PolicyEngine/policyengine-us/issues/9151).

## Additional Medicare numerical and domain verification

The exact-version regeneration produced 18/18 matches. Independent decimal
arithmetic used:

```text
taxable SE = max(0, 0.9235 × gross SE profit), subject to the $400 SE floor
reduced SE threshold = max(0, filing threshold − wages)
tax = 0.009 × (
  max(0, wages − filing threshold)
  + max(0, taxable SE − reduced SE threshold)
)
```

Every case agrees with that formula. The maximum live-PE floating difference
from exact decimal arithmetic was $0.0000244140625, within the report's $0.01
tolerance.

All selected cases affirm the pinned RuleSpec's ordinary-domain predicates:
no foreign-system-exclusive SE income, no relevant nonresident-alien fact, no
Social Security Act section 233 agreement, and no territory condition. The
deliberate false-domain diagnostic is excluded. This verifies the suite's
domain statement but does not override the registry's global
`not_comparable` classification.

## Generation provenance and reproducibility

Both committed reports' engine blocks and provenance attest:

```text
policyengine       4.18.9
policyengine-us    1.767.3
policyengine-core  3.30.3
RuleSpec commit    dcbae4344c522b4ad8004169316266cbc153186f
RuleSpec tree      7ee3ca44edd11cdaaf5d074a6a2a6c32d2f25dfb
```

The saver generator was rerun with those exact cached distributions and the
clean pinned RuleSpec checkout. It produced 25 comparisons, 14 raw matches,
and the same 11 mismatches. Applying the repository's normal v2-to-v2.1
disposition merge, metadata stripping, and dashboard serialization, while
retaining the committed immutable provenance block, produced a byte-identical
70,765-byte report:

```text
SHA-256 826062ec24bb4b9a664aadfce6d7b30db2b22c7df5be046b2c5e2b9eb91b742c
```

The Additional Medicare exact-version regeneration similarly produced 18/18
matches and, after the normal report adaptation with committed provenance, a
byte-identical 34,113-byte report:

```text
SHA-256 beb6dcf31df7fc2d974c3dfa3b2525c6640371eeaecfc927e89915bcec92884c
```

## Chain, containment, and hygiene

The remaining claimed invariants verify at the exact target:

- Semantic parsing of all 148 `conformance/us-pe.yaml` rows finds exactly two
  changed records: `us-pe:additional_medicare_tax` changes only its note;
  `us-pe:savers_credit` gains the suite and changes its note.
- The detail JSON and dashboard mirror contain the same two policy changes.
- `covered` moves 33 to 34. `unexplained_total=441` and
  `axiom_attributed_open=243` are unchanged and both come only from
  `us-pe:snap` / `ca-snap-ecps`.
- The only suite reports changed are the intended Additional Medicare report
  and new saver report. The only disposition change is replacement of the old
  saver filename with `us-savers-grid.yaml`. Six other federal comparison
  configs change only their common RuleSpec SHA/tree pins; their reports are
  untouched. Other changed JSON files are the expected shared/derived
  affected-map, scoreboard/detail mirrors, history, ratchet, burndown,
  freshness, manifest, and overview artifacts.
- Every committed chain/check gate passed: rule verification, state contract,
  dispositions, both SNAP artifact checks, grids, boundary suggestions,
  affected map, vacuous gate, overview, compositions, scoreboard, ratchet,
  burndown, and comparison registry listing.
- The conformance-universe check exits zero, but its US-PE live validation
  explicitly no-ops because the only local model checkout is 1.779.4 rather
  than the pinned 1.767.3. The target grids themselves were separately rerun
  with exact cached 1.767.3.
- Ruff 0.15.0 reports `All checks passed!`.
- The full local test run completed with `2270 passed, 70 skipped, 1 failed`.
  The sole failure is
  `tests/test_dashboard_loader.py::test_loader_equivalence`: its `npx esbuild`
  subprocess could not reach `registry.npmjs.org` because sandbox DNS is
  blocked. The exact target's live GitHub `test` and `gettsim-live` jobs both
  passed.
- `git diff --check` and `git fsck` pass.
- Neither `WORKER-REPORT` nor `PROGRESS.md` appears in the target diff. The
  review ledger and helper exist only on the throwaway review branch.
- No PR branch, remote, PR, or GitHub state was written.

## Required changes

1. Requery and resolve GitHub's reported conflict; publish a new reviewable
   head if resolution changes the branch.
2. Do not count either row as covered unless its exact gridded concept resolves
   to a machine-readable comparable mapping. Implement conditional-domain
   mapping support or expose a genuinely global equivalent, and add a gate
   preventing unmapped/`not_comparable` concepts from covering rows.
3. Add the nine below-boundary Saver's Credit cases.
4. Add Additional Medicare cases that put positive SE income on both required
   sides of the joint, MFS, and other thresholds, including the missing
   coordinated below/exact cases.
5. Correct both `section 25B(d)(3)` references to `section 25B(e)` and
   regenerate.
6. Rerun the exact-version grids, the committed check chain, tests, and the
   containment audit at the new head.

## Sandbox and provenance disclosures

- `uv run` could not initialize its default cache under the restricted home
  directory. Exact already-downloaded wheels were placed first on
  `PYTHONPATH`, and their distribution versions were checked immediately
  before live calculation.
- The local released Axiom binary successfully compiled and executed the exact
  RuleSpec pin, but the sandbox did not provide independent Git-ref provenance
  proving that binary came from the toolchain's engine ref
  `ffd8213271947b0189a9dd61a055c1e0e78908a0`.
- A separately built current source-tree Axiom engine rejected the pinned
  RuleSpec's older root layout. The successful direct run therefore compiled
  the pinned atomic composition with the existing released binary; this is a
  version-compatibility limitation, not a numerical mismatch.
- Direct attempts by the primary reviewer to fetch GitHub and to repeat the
  successful `gh` query failed intermittently with DNS/API errors. A parallel
  read-only query succeeded and captured the exact head, check results, and
  conflict state above.
- The one local pytest failure is the disclosed npm DNS failure; it is not a
  repository assertion failure. The exact-head GitHub test job passed.
