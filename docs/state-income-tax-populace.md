# State income tax over the full US Populace

This campaign extends the 44 state and District of Columbia individual-income-
tax pilot pipelines from their six-case verification grids to the complete,
sha256-pinned US Populace validation population. The historical `ecps` command
name is retained for compatibility, but the dataset is the certified
`populace-us` artifact rather than Enhanced CPS.

## Why the grid runner cannot simply use a larger sample

The committed state liability reports exercise 44 RuleSpec modules with 270
hand-computed cases. Forty-three modules are intentionally narrow pilots and New
Hampshire is a grounded repeal-to-zero module. The initial pilots exposed 255
explicit caller-supplied inputs; reviewed promotions for Georgia, Iowa, Illinois,
Indiana, Kansas, Louisiana, Michigan, North Carolina, Pennsylvania, South
Carolina, Utah, Virginia, Arizona, Oklahoma, Alabama, Connecticut, Delaware,
Hawaii, New Mexico, New York, West Virginia, Montana, Ohio, New Jersey, and
Vermont reduce the current contract to 171 inputs and one explicit relation. Most
remaining inputs are completed-return boundaries or schedule values, including
adjusted or taxable income, deductions, exemptions, credits, bracket selection,
recapture, and state-specific capital-gain facts.

Using PolicyEngine's target liability, or a downstream value derived from that
target, to fill those inputs would turn the comparison into an output-alignment
test. The population runner therefore requires a declarative projection contract
for every compiled input and rejects incomplete or circular contracts before an
engine runs.

## Projection contract

Every state contract records:

- the RuleSpec program and output;
- the PolicyEngine comparison target and tolerances;
- the state/FIPS routing key;
- every required input and imported dependency;
- the source kind and evidence for each boundary; and
- whether the state is ready for the declared campaign scope or blocked.

Permitted source kinds are raw Populace leaves, independently derived
transformations, source-backed statutory constants or schedules, RuleSpec
imports, and explicitly disclosed upstream PolicyEngine boundaries. An upstream
PolicyEngine boundary is permitted only when it is legally upstream of the
output under test and no independent encoded chain exists yet. The target itself,
post-target variables, residual-driven adjustments, candidate min/max selection,
and silent zero defaults are forbidden.

## Population routing

The pinned artifact contains 87,519 tax units, 160,858 people, and 75,112
households. Tax units do not carry geography directly. The runner assigns a tax
unit to a state by joining `person_tax_unit_id` to `person_household_id` and then
to household `state_fips`. Conflicting household assignments are errors; they
are never resolved by picking one state.

Sampling occurs after state routing and readiness filtering. `sample_size: 0`
means every eligible positive-weight unit. Reports retain total, eligible,
excluded, compared, errored, and weighted counts by state, plus the pinned
dataset revision, checksum, build model, RuleSpec commit, Axiom engine commit,
and PolicyEngine package versions.

Canonical execution also requires clean RuleSpec and Axiom engine checkouts
with the expected upstream remotes. The report records the SHA-256 of the exact
`axiom-rules-engine` executable, so a stale or substituted binary cannot be
mistaken for an unidentified build of the recorded source commit.

A successful canonical report has `errored_count: 0`. Dataset, compilation, or
engine failures abort the command without publishing a canonical report; they
are operational failures, not case exclusions or parity results.

Current household state is not proof of full-year residency. This campaign
therefore discloses one uniform modeling assumption:
`household_state_as_full_year_residence`. It includes every positive-weight
routed tax unit. Filtered slices are forbidden by the v1 contract until stable,
source-backed exclusion predicates and per-reason ledgers are implemented and
independently reviewed.

Delaware, Hawaii, and Montana are the current ready-state projections that cross a
PolicyEngine entity boundary. Delaware validates certified Person identity,
order, cardinality, and every TaxUnit link before projecting separate taxable
income at Person grain, summing the combined taxable-income candidate to
TaxUnit, and emitting raw relation membership for every Person linked by the
certified `person_tax_unit_id` column. An explicit reviewed Boolean-OR of
PolicyEngine's upstream `is_tax_unit_head` and `is_tax_unit_spouse` roles
controls inclusion inside `sum_where`; zero-filer units validly aggregate to
zero. The pinned engine's current aggregation lowering reads the related Person
from runtime tuple slot 0 and current TaxUnit from slot 1, so the adapter emits
`(Person, TaxUnit)` pending an engine/RuleSpec follow-up to preserve declared
relation argument labels. Montana's projector is likewise state- and
variable-specific:
it verifies the certified Person IDs and order, rejects duplicate or missing
members and unknown tax-unit links, and only then sums the allowlisted Montana
taxable-income, long-term-gain, and short-term-gain arrays to TaxUnit. The net
long-term amount is reconstructed as `max(0, min(sum(LTCG), sum(LTCG) +
sum(STCG)))`; no generic Person-to-TaxUnit transform is exposed.
Hawaii uses the same fail-closed Person identity and membership projector only
for the source-required sum of `long_term_capital_gains`; taxable income, net
capital gain, and filing status remain TaxUnit-grain upstream boundaries. The
RuleSpec accepts completed Form N-11 capital-gains worksheet line 10 after
Hawaii adjustments and any Form N-158 subtraction. PolicyEngine does not model
those intervening amounts, so the reviewed oracle proxy supplies
`max(0, min(net_capital_gain, sum(long_term_capital_gains)))` and fails closed
on identity, membership, or nonfinite-value drift.

## National denominator

The 44 pilot jurisdictions cover broad individual income taxes, including DC
and Washington's capital-gains tax. A national router must also account for the
seven jurisdictions without a broad current PIT: Alaska, Florida, Nevada, South
Dakota, Tennessee, Texas, and Wyoming. They must be represented by grounded
no-tax/repeal results or explicit non-applicability records; absence is not
treated as zero. New Hampshire's 2026 Chapter 77 repeal is already grounded in
its pilot module.

## Delivery sequence

1. Land the projection-contract schema, validator, geography join, batching,
   provenance, and exclusion accounting without claiming parity.
2. Expand reusable RuleSpec groups from simple flat/taxable-income schedules to
   complete filing-status, exemption, dependent, deduction, high-bracket, and
   credit scope.
3. Handle special systems separately: California high brackets and surcharge,
   Massachusetts Parts A/B/C and surtax, Vermont's completed indexed-normal-tax
   boundary, and Washington sourcing/loss/deduction rules.
4. Run the entire pinned population, triage every residual, and fix source-backed
   Axiom gaps before recording any genuine oracle or bridge divergence.
5. Publish the canonical v2.1 report only after every residual is dispositioned,
   independent review is clean, and current CI is green.

Population readiness is a legal-coverage claim, not merely a successful engine
invocation. A state is ready only when every included case has a non-circular
projection, every excluded case has a stable reason, and all operative branches
within the declared comparison scope are encoded and tested.

Validate the current contract with:

```bash
uv run scripts/check_state_tax_populace_contract.py
uv run scripts/check_state_tax_populace_contract.py --json
```

Audit all 87,519 tax units without executing blocked state programs:

```bash
uv run --extra policyengine scripts/audit_state_tax_populace.py \
  --sample-size-per-state 0 --output /tmp/state-tax-populace-routing.json
```

Execute all currently ready states (Alabama, Arizona, Connecticut, Delaware,
Georgia, Hawaii, Iowa, Illinois, Indiana, Kansas, Louisiana, Michigan, Montana,
New Mexico, New York, North
Carolina, New Hampshire, New Jersey, Ohio, Oklahoma, Pennsylvania, South
Carolina, Utah, Virginia, Vermont, and West Virginia; later states remain blocked
until their source-backed projection contracts land):

```bash
uv run --extra policyengine scripts/run_state_tax_populace.py \
  --sample-size-per-state 0 \
  --rulespec-root /path/to/rulespec-us \
  --axiom-rules-path /path/to/axiom-rules-engine \
  --output /tmp/state-tax-populace-report.json
```

For a bounded execution, repeat the case-insensitive `--state` option. Unknown
or currently blocked jurisdictions fail before the dataset is loaded:

```bash
uv run --extra policyengine scripts/run_state_tax_populace.py \
  --state NJ --state NM \
  --sample-size-per-state 0 \
  --rulespec-root /path/to/rulespec-us \
  --axiom-rules-path /path/to/axiom-rules-engine \
  --output /tmp/nj-nm-state-tax-populace-report.json
```

The report records normalized requested abbreviations in `requested_states`.
Its routing section always retains the full certified national denominator;
only target calculation, input projection, and comparison are restricted to
the requested ready jurisdictions. This selects whole jurisdictions, not a
filtered population slice: every eligible unit in each selected state remains
in scope.
