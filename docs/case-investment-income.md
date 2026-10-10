# Dividends and capital gain distributions on the Case

How the cross-engine `Case` carries Form 1040 lines 3a, 3b and 7a, and how
each engine projection reads them. The code is
`axiom_oracles/core/investment_income.py`; the tests are
`tests/test_investment_income_case_surface.py` (projections, properties) and
`tests/test_investment_income_live_engines.py` (the four engines run live on
worked returns).

## What the concepts mean

| Concept | Form 1040 (2025) | Relation |
|---|---|---|
| `Concepts.DIVIDEND_INCOME` | Line 3b, ordinary dividends (Form 1099-DIV box 1a) | Includes the qualified dividends |
| `Concepts.QUALIFIED_DIVIDEND_INCOME` | Line 3a, qualified dividends (box 1b) | Part of line 3b, never added to it |
| `Concepts.NON_SCHEDULE_D_CAPITAL_GAIN_DISTRIBUTIONS` | Line 7a with the line 7b box "Schedule D not required" checked (box 2a) | Long-term gain; disjoint from the Schedule D concepts |
| `Concepts.SHORT_TERM_CAPITAL_GAINS`, `Concepts.LONG_TERM_CAPITAL_GAINS` | Schedule D net short- and long-term gain or loss | |

The instructions these come from (i1040gi.pdf for 2025, as posted
2026-02-27):

- Line 3a: "Enter your total qualified dividends on line 3a. Qualified
  dividends are also included in the ordinary dividend total required to be
  shown on line 3b."
- Line 3b: "Enter your total ordinary dividends on line 3b. This amount
  should be shown in box 1a of Form(s) 1099-DIV."
- Line 7a: "Exception 1. You don't have to file Form 8949 or Schedule D if
  you aren't deferring any capital gain by investing in a qualified
  opportunity fund and both of the following apply. 1. You have no capital
  losses, and your only capital gains are capital gain distributions from
  Form(s) 1099-DIV, box 2a (or substitute statements); and 2. None of the
  Form(s) 1099-DIV (or substitute statements) have an amount in box 2b
  (unrecaptured section 1250 gain), box 2c (section 1202 gain), or box 2d
  (collectibles (28%) gain)." And: "If Exception 1 applies, enter your total
  capital gain distributions (from box 2a of Form(s) 1099-DIV) on line 7a and
  check the box 'Schedule D not required' on line 7b."

Where the lines go on the return:

| Use | Source text | Lines |
|---|---|---|
| Total income, AGI | Social Security Benefits Worksheet line 3: "Combine the amounts from Form 1040 or 1040-SR, lines 1z, 2b, 3b, 4b, 5b, 7a, and 8" | 3b and 7a (3a is not added again) |
| Preferential rates, 26 USC 1(h) | Qualified Dividends and Capital Gain Tax Worksheet: line 2 "line 3a"; line 3 "Are you filing Schedule D? ... No. Enter the amount from Form 1040 or 1040-SR, line 7a" | 3a and 7a |
| EITC investment income, 26 USC 32(i) | Pub. 596 (2025) Worksheet 1: line 3 "line 3b"; line 5 "line 7a. If the amount on that line is a loss, enter -0-" | 3b and 7a |
| Net investment income, 26 USC 1411 | Instructions for Form 8960 (2024), line 5a: combine "Form 1040 or 1040-SR, line 7, and Schedule 1 (Form 1040), line 4" | 3b (line 2) and 7a |

26 USC 852(b)(3)(B): "A capital gain dividend shall be treated by the
shareholders as a gain from the sale or exchange of a capital asset held for
more than 1 year."

## One normalization, read by every projection

`person_dividends` floors qualified dividends at zero and never lets ordinary
dividends fall below the qualified part; `person_non_schedule_d_capital_gain_distributions`
floors line 7a at zero. A Case that breaks the line 3a/3b relation (some
hand-built and legacy rows carry qualified above ordinary) is therefore still
priced identically by every engine.

| Projection | Line 3b | Line 3a | Line 7a |
|---|---|---|---|
| PolicyEngine (`adapters/policyengine/runner.py`) | `dividend_income`, with `non_qualified_dividend_income` = 3b - 3a | `qualified_dividend_income` | `non_sch_d_capital_gains` |
| Axiom tax bridge (`adapters/axiom/tax_projection.py`) | `person_dividend_income` (AGI leaf), `dividend_income` | `capital_gains_tax_qualified_dividend_income`, 1(h) `qualified_dividend_income` | `person_non_sch_d_capital_gains` (AGI leaf), `non_sch_d_capital_gains` (worksheet, QBI cap, 1411 net gain), 1(h) `long_term_capital_gains`, Worksheet 1 capital basket |
| TAXSIM (`adapters/taxsim/projection.py`) | `dividends` + the non-qualified part in `otherprop` | `dividends` | added to `ltcg` |
| Tax-Calculator (`adapters/taxcalc/projection.py`) | `e00600` | `e00650` | `e01100` |
| Axiom benefit mapping (`adapters/axiom/generic_inputs.py`) | `DIVIDEND_INCOME`, counted once | not listed beside it | not carried (see below) |

TAXSIM, Tax-Calculator and the Axiom AGI leaves sum the filers (head and
spouse). The Axiom worksheet leaves and PolicyEngine's `add(tax_unit, ...)`
sum every member; PolicyEngine/policyengine-us#9869 tracks that difference
for dependents.

## What the Populace producer loads

`populations/populace_us.py` builds line 3b as `qualified_dividend_income +
non_qualified_dividend_income` and line 3a as `qualified_dividend_income`,
and fails closed if PolicyEngine cannot calculate either.

It does not read the artifact's stored `dividend_income` column.
PolicyEngine-US defines `dividend_income` as an alias of
`ordinary_dividend_income`, the sum above, but the pinned Populace US 2024
artifact also stores a legacy column under that name, and a stored value
overrides the alias (PolicyEngine/microcosm#24 lists it among the
formula-owned columns the artifact should not store). In the pinned artifact
(sha256 `16be6338f9d0...`, raw 2024 values, unweighted):

| Column | Nonzero persons | Sum |
|---|---|---|
| `dividend_income` (stored legacy) | 16,090 | $85.7M |
| `qualified_dividend_income` | 29,206 | $28.64B |
| `non_qualified_dividend_income` | 24,426 | $6.42B |
| `non_sch_d_capital_gains` | 3,086 | $25.1M |

The legacy column cannot be line 3b: it is below the qualified amount on
2,631 of the 4,103 persons that carry both. Nor is it a part to add: every
amount in the split sits on a tax-unit head row, while the legacy column
also has amounts on 4,969 spouse rows and 142 dependent rows, and 11,760
persons carry it with no split at all ($59.0M). Those persons' dividends are
no longer on the Case.

Line 7a is loaded on tax-unit Cases only. Household Cases feed the benefit
lanes, whose Axiom income lists (`data/populace_input_mapping.yaml`) read no
capital gains, while PolicyEngine's `medicaid_magi` starts from AGI, which
includes line 7a from policyengine-us#8839 on.

## Schedule D fold

Exception 1 is a condition on a return, so a return never has both line 7a
and Schedule D amounts. When the people on one return carry a Schedule D
amount (a nonzero short- or long-term gain or loss), each one's capital gain
distributions are added to that person's long-term gain and the line 7a fact
is dropped. A tax unit's filers (head and spouse) are one return; a
dependent's gains are on the dependent's own return, so a child's capital
loss never moves her parents' line 7a.

The fold is applied twice, by the same function:

- The Populace producer folds each tax-unit Case
  (`fold_tax_unit_returns`) and records the number of members folded in
  `metadata["capital_gain_distributions_folded_into_schedule_d"]`, so the
  Case itself is a coherent return. In the pinned artifact 3,086 persons
  carry line 7a, one per tax unit; 23 of them also carry a Schedule D
  amount on the same row (14 a capital loss) and are folded, which leaves
  3,063 tax units with line 7a.
- Every tax projection folds the people it is about to price
  (`with_schedule_d_fold`), so a hand-built or future Case that carries both
  paths is still priced identically everywhere. TAXSIM needs no fold: its
  `ltcg` column is Schedule D long-term gain plus line 7a on either path.

The state-tax campaign's TAXSIM leg (`bridges/state_tax_populace_runner.py`)
reads the same dividend and line 7a sources as the loader.

## Engine differences to expect

- **PolicyEngine-US 1.752.2**, which the Case suites pin, predates
  PolicyEngine/policyengine-us#8839 (issue #8828): `non_sch_d_capital_gains`
  enters its capital gains worksheet but not gross income or net investment
  income. On a unit with line 7a its AGI is low by that amount. The issue
  closed on 2026-07-05; 1.764.6 has the fix and reproduces the worked
  returns in `tests/test_investment_income_live_engines.py` to the cent.
- **Tax-Calculator 6.7.1** counts `e01100` in AGI and in the capital gains
  worksheet, but leaves it out of its EITC investment income, its net
  investment income and its QBI income limit (PSLmodels/Tax-Calculator#3181
  reports the last two).
- **TAXSIM-35** has no line 7a column; the amount rides in `ltcg`, which is
  what 852(b)(3)(B) makes it. On the worked 2026 return whose preferential
  income straddles the $49,450 zero-rate amount, the pinned binary's tax is
  $67.40 below the worksheet, by the same amount whether the gain is entered
  as line 7a or as Schedule D long-term gain.
- **Axiom** leaves 26 USC 1411 out of the composed program
  (axiom-encode#1213), so net investment income tax on dividends and line 7a
  is a TAXSIM-only amount, as it already was for the other investment income.
