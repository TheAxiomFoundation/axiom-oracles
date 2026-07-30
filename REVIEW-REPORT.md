VERDICT: REQUEST-CHANGES

# Blind review — axiom-oracles PR #430

Reviewed PR head
`2404dd5b30ef0f76f199664aee713ba83ca8ac68`
(`fed-parity/chunk2-oracle-suite`) against base
`a0b859eeceae401617805ecd1fd04a6ba34c80e6`.
The RuleSpec boundary was
`87d3cbd3b6ec580724f0b79a0472105347f79518`, tree
`66562bc60977c02c6ea353de6323b57fe927bd4c`, as required.

Merge risk is medium. The scored comparison is numerically sound, but two
binding review requirements are not met. This review made no PR-branch,
remote, or GitHub writes.

## Blocking findings

### 1. The final RuleSpec re-pin leaves the exact-pin census test stale

The comparison correctly pins the merged RuleSpec commit/tree in
[`comparisons/us-taxable-income-grid.yaml`](comparisons/us-taxable-income-grid.yaml#L47),
but
[`tests/test_federal_tax_liability_generator.py`](tests/test_federal_tax_liability_generator.py#L70)
still expects the pre-merge pair:

| Surface | Commit | Tree |
|---|---|---|
| Required and configured | `87d3cbd3…` | `66562bc6…` |
| Test expectation | `4ced8fb7…` | `9a4aaf64…` |

The focused
`test_every_live_federal_grid_pins_its_reviewed_rulespec_snapshot` fails.
The full suite ended with **2,315 passed, 76 skipped, 2 failed**. One other
failure was an environment-only `npx esbuild` DNS failure and passed in
isolation with the cached esbuild binary; the pin-census failure is
actionable.

Clean main also fails this census for an older Chunk 1 stale expectation. The
PR repairs that Chunk 1 entry, then its final four-file re-pin introduces the
analogous Chunk 2 mismatch. Therefore the reviewed head does not satisfy the
required full-green validation chain.

Required change: update the Chunk 2 expected pair to the required merge
commit/tree and rerun the complete test suite.

### 2. Five bridge values are hand-entered outside the pinned companion

The exact pinned RuleSpec companion provides 37 of the 42 required bridge
assertions (three outputs across 14 cases). The remaining five are literal
zero strings in
[`comparisons/fixtures/us-taxable-income-grid-assertion-closure.yaml`](comparisons/fixtures/us-taxable-income-grid-assertion-closure.yaml#L7):

- itemized-deduction zero for each of the three senior cases;
- QBI-deduction zero for `ti-senior-single-plus-one`;
- nonitemizer-charity zero for `ti-senior-single-plus-one`.

The generator explicitly merges this oracle-owned supplemental fixture in
[`scripts/generate_federal_tax_liability.py`](scripts/generate_federal_tax_liability.py#L3898).
Removing it makes extraction fail immediately because the companion lacks the
senior-threshold itemized bridge output. These values therefore are not
engine-asserted companion outputs, contrary to the binding “never
hand-entered” bridge-provenance requirement.

The five zeros do **not** conceal a scored taxable-income mismatch: QBI and
charity are forced to zero by the asserted inputs and totals, while the three
itemized aggregates have zero components and sit on the unselected standard
branch. That numerical safety does not cure their provenance.

Required change: obtain the bridge assertions from an authorized immutable
RuleSpec companion. Because the required merge tree is immutable, this needs
either an explicit contract exception for the narrow supplement or an
authorized successor RuleSpec pin; it should not be silently encoded in this
repository.

## Independent regeneration

The exact RuleSpec checkout at
`/private/tmp/oracle-rerun/rulespec-us` was clean at the required commit and
tree. I ran the registry path
`scripts/run_comparison.py us-taxable-income-grid` under:

| Component | Version |
|---|---:|
| Python | 3.13.9 |
| PolicyEngine | 4.18.9 |
| PolicyEngine-US | 1.767.3 |
| PolicyEngine Core | 3.30.3 |

The official runner produced 14/14 matches, zero mismatches, zero errors, and
zero unexplained dispositions. Its regenerated committed dashboard report
differed only in `provenance.generated_at`
(`2026-07-30T04:02:44Z` versus `2026-07-30T04:11:31Z`). An independent
raw-to-v2 adaptation and disposition merge was also structurally identical
after removing that volatile timestamp.

The zero was checked for vacuity:

- the Axiom scored output is
  `taxable_income_pipeline#federal_taxable_income`;
- the PolicyEngine scored output is `taxable_income`;
- both are annual TaxUnit money outputs;
- tolerance remains absolute `0.01`, relative `0.0`;
- 13 of 14 values are nonzero, with 11 distinct values spanning $0 through
  $167,800;
- both engines have a 92.857% positive rate;
- the suite passes the generator non-vacuity assertion and the repository
  vacuous gate.

The sole nonzero residual is the senior-plus-one floating-point result:
Axiom $50,851.06 versus PolicyEngine $50,851.0625, a $0.0025 difference
within the unchanged cent tolerance.

## Bridge and senior-deduction integrity

The three mappings in
[`scripts/generate_federal_tax_liability.py`](scripts/generate_federal_tax_liability.py#L3393)
bind exactly:

| RuleSpec bridge output | PolicyEngine-US variable |
|---|---|
| `federal_itemized_taxable_income_deductions` | `itemized_taxable_income_deductions` |
| `federal_qualified_business_income_deduction` | `qualified_business_income_deduction` |
| `nonitemizer_charitable_deduction` | `charitable_deduction_for_non_itemizers` |

The pinned PolicyEngine-US source declares all three as TaxUnit, yearly, USD
variables. The builder takes their values from the extracted bridge mapping;
it has no per-case constants. Exact-key/type validation rejects a missing,
extra, Boolean, or nonnumeric bridge, and the fixture/PE-input validators
reject missing fixture inputs, unexpected fixture inputs, undeclared
PolicyEngine overrides, and missing bridge bindings. Direct negative probes
for a removed required input and an added unexpected input both failed
closed.

The generator does not override `additional_senior_deduction`. PolicyEngine
derives it from age, citizen SSN status, filing status, AGI, and its MAGI
addbacks. The report reconciles RuleSpec `senior_deduction` to PolicyEngine
`additional_senior_deduction` on every case, including five nonzero cases.

The nonzero senior-MAGI addback probe is absent from the scored 14-case report,
but it is present in the merged companion as
`ti-senior-magi-section-931-addback`. An independent exact-stack PolicyEngine
simulation with AGI $75,000 and a $10,000 section 931 addback derived:

| Diagnostic | RuleSpec | PolicyEngine |
|---|---:|---:|
| Senior MAGI | $85,000 | $85,000 |
| Senior deduction | $5,400 | $5,400 |
| Total deductions | $23,550 | $23,550 |
| Taxable income | $51,450 | $51,450 |

This is a scored-grid coverage gap, not an observed hidden divergence class.

## Statutory spot-check

Independent arithmetic from SPINE-PLAN section 6.3 and the pinned companion
agreed with the committed expected values:

| Case | Recalculation | Expected |
|---|---|---:|
| Single standard | $100,000 − $16,100 | $83,900 |
| Head of household | $100,000 − $24,150 | $75,850 |
| Single itemized | $100,000 − $25,000 | $75,000 |
| Nonitemizer, all components | $75,000 − ($18,150 + $10,000 + $500 + $5,000 + $2,000 + $6,000 + $1,000) | $32,350 |
| Itemizer, all components | $75,000 − ($30,000 + $10,000 + $5,000 + $5,000 + $2,000 + $6,000 + $1,000) | $16,000 |
| Zero floor | max(0, $10,000 − $16,100) | $0 |
| Senior single threshold | $75,000 − $18,150 − $6,000 | $50,850 |
| Senior single plus one | $75,001 − $18,150 − ($6,000 − 6% × $1) | **$50,851.06** |
| Senior joint threshold | $150,000 − ($32,200 + 2 × $1,650 + $12,000) | $102,500 |

## Adoption and output-surface mappings

The pinned RuleSpec taxable-income module has exactly three outputs, and
[`axiom_oracles/bridges/mappings/us.yaml`](axiom_oracles/bridges/mappings/us.yaml#L8418)
has exactly the corresponding three rows:

- verified-domain judgment: `not_comparable`, P4;
- total deductions: direct `taxable_income_deductions`, P1;
- final taxable income: direct `taxable_income`, P1.

There are no phantom or missing module-output rows. Both comparable outputs
are asserted in all 14 companion cases.
[`conformance/us-pe.yaml`](conformance/us-pe.yaml#L1246) adopts exactly
`us-pe:taxable_income`; no adjacent row was accidentally adopted.

## Checks, baseline, and containment

All 16 current CI validation commands passed: registry listing, rule
verification, state-populace contract, disposition validation,
case/disposition artifacts, grids, boundaries, affected map, vacuous gate,
dashboard overview, conformance universe/compositions, scoreboard, ratchet,
and burndown. `ruff check .`, `git diff --check`, and repository object checks
also passed.

The live-RuleSpec CA/IL/NY/OH state-oracle baseline is unchanged:

- reviewed head: 5 failed, 19 passed, 1 skipped;
- clean main: 5 failed, 19 passed, 1 skipped;
- identical failure-nodeid-set SHA-256:
  `a58b31bbb71579ab116ca9184a7c54e3af3a35d73dceda6ad1e272c7775aaf29`.

The shared failures are CA BHST output-set mapping, IL output-set mapping, IL
positive-recapture fixture coverage, NY output-set mapping, and OH output-set
mapping. All 25 corresponding tests pass against the exact reviewed RuleSpec
checkout.

Containment is exactly the intended 20 paths:

```text
PROGRESS.md
axiom_oracles/bridges/mappings/us.yaml
comparisons/affected_map.json
comparisons/fixtures/us-taxable-income-grid-assertion-closure.yaml
comparisons/us-taxable-income-grid.yaml
conformance/detail/us-pe.json
conformance/history/us-pe/2026-07-30.json
conformance/ratchet.yaml
conformance/scoreboard.json
conformance/us-pe.yaml
dashboard/public/data/axiom-policyengine-us-taxable-income-grid.json
dashboard/public/data/conformance_burndown.json
dashboard/public/data/conformance_detail_us-pe.json
dashboard/public/data/conformance_scoreboard.json
dashboard/public/data/freshness.json
dashboard/public/data/manifest.json
dashboard/public/data/overview.json
scripts/generate_federal_tax_liability.py
tests/test_conformance.py
tests/test_federal_tax_liability_generator.py
```

The PR's ten first-parent `PROGRESS.md` changes are byte-prefix append-only.
The reviewed and clean-main disposable worktrees were clean at closeout.

## Sandbox and environment disclosures

- GitNexus could inspect neither an existing graph nor finish indexing:
  registration at `~/.gitnexus/registry.json` was denied with `EPERM`.
  Direct diff, source, and symbol tracing replaced graph analysis. The
  untracked partial index was moved recoverably to
  `/private/tmp/pr430-gitnexus-failed-2404dd5b` after sandbox policy rejected
  its recursive removal.
- Normal `uv` initialization under `~/.cache/uv` was denied. Exact
  regeneration used a fail-closed temporary runner shim plus already-cached
  package roots; runtime imports and versions were verified before execution.
- A redundant write-capable checkout command against the already-correct
  RuleSpec worktree was denied at the source repository's `index.lock`.
  Read-only HEAD, tree, status, and source verification succeeded.
- Full pytest's dashboard-loader failure was caused by restricted DNS during
  `npx esbuild`; the isolated test passed with cached esbuild 0.28.1.
- The generic conformance-universe check explicitly skipped US-PE and UK-PE
  because the available generic checkouts did not match their pins. This
  review separately ran the target US suite on its exact required stack.
- Cached Ruff 0.15.12 would reformat `tests/test_conformance.py` identically
  at head and clean main. Current CI's required `ruff check` is green.

## Disposition

Request changes until the exact-pin census agrees with the required merged
RuleSpec snapshot and the five supplemental bridge literals receive an
explicitly authorized provenance resolution. No numerical correction to the
14 scored taxable-income expecteds is indicated by this review.
