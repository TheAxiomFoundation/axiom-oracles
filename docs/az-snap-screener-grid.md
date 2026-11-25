# Arizona SNAP screener grid

`comparisons/az-snap-screener.yaml` runs Axiom's composed Arizona SNAP
program (`programs/us-az/snap/fy-2026.yaml` in rulespec-us) and PolicyEngine
US on 1,211 synthetic Arizona households. The households come from
`axiom_oracles/suites/us_az_snap_screener.py`. No population microdata is
involved. The suite is report-only (`ci: manual`): it shows where the two
engines differ on the facts a benefits screener collects. Do not tune the
grid to remove a mismatch; record the mismatch and its cause.

## How the grid is built

- Every household starts from a base: a head and `n - 1` children, no shelter
  cost, no utility bills, no expenses, no resources. The head is 35 with
  unemployment compensation (`none`), 62 with Social Security (`elderly`;
  under 65, so PolicyEngine's modeled Medicare Part B premium stays out), or
  45 with Social Security disability benefits (`disabled`; at least $100 a
  month, so PolicyEngine's USDA disability test holds).
- Monthly gross income is a percentage of the monthly HHS poverty guideline
  for the household size (48 states and DC). `us-az-snap-screener` uses the
  FY2026 guideline year; `us-az-snap-screener-fy2027` uses FY2027.
- Each path block crosses only its own factors (a full cross product of the
  values below). All other factors stay at the base. This is the pairing
  rule: one block per path, nothing random, ids that name the factors.
- The shelter, minimum-benefit and resource blocks place their edges with
  FY2026 SNAP amounts. At other periods those rows are near the edge, not on
  it.

| Path | Rows | Factors |
|---|---|---|
| `income` | 810 | sizes 1-10; 0, 50, 129-131, 164-166, 184-186, 199-201% of the guideline; earned or unearned; head none, elderly or disabled |
| `medical` | 64 | elderly or disabled head, sizes 1 and 3, 50 and 100%, medical $0, $35, $35.01, $100, $180, $180.01, $300 a month; controls: no elderly or disabled member ($100, $300), a 70-year-old ($0, $100) |
| `shelter` | 48 | sizes 1, 3, 5; head none or elderly; 50 and 100%; excess shelter cost $1 below, at, $1 above and $300 above the $744 cap |
| `utility` | 96 | standard (heating or cooling plus electricity), limited (electricity and water), telephone only, none; sizes 1-6; rent $0 or $600; head none or elderly |
| `homeless` | 18 | homeless; sizes 1, 2, 4; 0 and 50%; shelter cost $0, $100, $250 |
| `dependent_care` | 54 | working head, sizes 2-4, youngest child 3 or 10, 50, 100, 130%, care $0, $200, $800 a month |
| `child_support` | 36 | working head, sizes 1-3, 50, 100, 129, 131%, child support paid $0, $150, $600 a month |
| `income_mix` | 45 | sizes 1, 2, 4; 50, 100, 129%; earned share 0, 25, 50, 75, 100% |
| `resources` | 24 | elderly head, sizes 1-2, 190 and 210%, rent that leaves net income at 80%, resources $0, $4,499, $4,500, $4,501, $10,000; controls: size 2 at 120% earned, $0 to $50,000 |
| `minimum_benefit` | 16 | sizes 1-2; allotment before the minimum of $30, $25, $24, $23, $10, $1, $0, -$5 |

`PATHS` in the suite module names, for each path, the Axiom rules and the
PolicyEngine variables it is meant to exercise.

## How the facts reach each engine

The screener facts are Case concepts (`core/case.py`, "Screener facts").
Population Cases never carry them, and both projections read them only when
present, so population comparisons project as before.

- PolicyEngine (`adapters/policyengine/runner.py`): Social Security
  disability benefits, other medical expenses, child support paid, bank
  account assets (head), heating or cooling, electricity, water and phone
  expenses, out-of-pocket child care (`childcare_expenses`), and
  `is_homeless`.
- Axiom (`data/populace_input_mapping.yaml`, "Screener facts"): the federal
  7 CFR 273.10 operands for the homeless claim, child support and medical
  expenses; the Arizona utility allowance tests; the Arizona dependent care
  payment; countable resources. The mapping comments state each assumption
  (a paid bill is billed separately, owed and verified; dependent care is
  needed for work; a homeless household claims its shelter cost).

## Reading a run

For each path, count households, matches, and mismatches by class:

- **Axiom rule missing**: no Axiom rule decides the fact (for example a
  FY2027 amount).
- **Wiring missing**: the Axiom rule exists but the ProgramSpec does not
  compose it into the outputs (for example the Arizona medical deduction,
  rulespec-us#952).
- **Comparison projection missing**: a fact reaches one engine and not the
  other, or reaches it in a different form.
- **PolicyEngine differs from the Arizona manual**: both engines get the same
  facts and PolicyEngine's rule is not the manual's.
- **PolicyEngine pin too old**: the pinned policyengine-us predates the law
  in force at the period (Arizona's 200% expanded categorical eligibility
  from 2026-03-01; the FY2027 COLA from 2026-10-01).
