# Dividends and capital gain distributions on the Case

How the cross-engine `Case` carries Form 1040 lines 3a, 3b and 7a, and how
each engine projection reads them. `axiom_oracles/core/investment_income.py`
holds the code; `tests/test_investment_income_case_surface.py` tests the
projections and their properties, and
`tests/test_investment_income_live_engines.py` runs the four engines live on
worked returns.

## What the concepts mean

| Concept | Form 1040 (2025) | Relation |
|---|---|---|
| `Concepts.DIVIDEND_INCOME` | Line 3b, ordinary dividends (Form 1099-DIV box 1a) | Includes the qualified dividends |
| `Concepts.QUALIFIED_DIVIDEND_INCOME` | Line 3a, qualified dividends (box 1b) | Part of line 3b; adding the two counts it twice |
| `Concepts.NON_SCHEDULE_D_CAPITAL_GAIN_DISTRIBUTIONS` | Line 7a with the line 7b box "Schedule D not required" checked (box 2a) | Long-term gain; disjoint from the Schedule D concepts |
| `Concepts.SHORT_TERM_CAPITAL_GAINS`, `Concepts.LONG_TERM_CAPITAL_GAINS` | Schedule D net short- and long-term gain or loss | |

The quotes come from the 2025 instructions (i1040gi.pdf, which the IRS
posted on 2026-02-27):

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
| Total income, AGI | Social Security Benefits Worksheet line 3: "Combine the amounts from Form 1040 or 1040-SR, lines 1z, 2b, 3b, 4b, 5b, 7a, and 8" | 3b and 7a (3b already holds 3a) |
| Preferential rates, 26 USC 1(h) | Qualified Dividends and Capital Gain Tax Worksheet: line 2 "line 3a"; line 3 "Are you filing Schedule D? ... No. Enter the amount from Form 1040 or 1040-SR, line 7a" | 3a and 7a |
| EITC investment income, 26 USC 32(i) | Pub. 596 (2025) Worksheet 1: line 3 "line 3b"; line 5 "line 7a. If the amount on that line is a loss, enter -0-" | 3b and 7a |
| Net investment income, 26 USC 1411 | Instructions for Form 8960 (2024), line 5a: combine "Form 1040 or 1040-SR, line 7, and Schedule 1 (Form 1040), line 4" | 3b (line 2) and 7a |

26 USC 852(b)(3)(B): "A capital gain dividend shall be treated by the
shareholders as a gain from the sale or exchange of a capital asset held for
more than 1 year."

## One normalization that every projection reads

`person_dividends` floors qualified dividends at zero and never lets ordinary
dividends fall below the qualified part; `person_non_schedule_d_capital_gain_distributions`
floors line 7a at zero. So every engine prices a Case that breaks the line
3a/3b relation the same way; some hand-built and legacy rows carry qualified
dividends above ordinary dividends.

| Projection | Line 3b | Line 3a | Line 7a |
|---|---|---|---|
| PolicyEngine (`adapters/policyengine/runner.py`) | `dividend_income`, with `non_qualified_dividend_income` = 3b - 3a | `qualified_dividend_income` | `non_sch_d_capital_gains` |
| Axiom tax bridge (`adapters/axiom/tax_projection.py`) | `person_dividend_income` (AGI leaf), `dividend_income` | `capital_gains_tax_qualified_dividend_income`, 1(h) `qualified_dividend_income` | `person_non_sch_d_capital_gains` (AGI leaf), `non_sch_d_capital_gains` (worksheet rules, the 199A net capital gain, the 1411 net-gain rule), 1(h) `long_term_capital_gains`, Worksheet 1 capital basket |
| TAXSIM (`adapters/taxsim/projection.py`) | `dividends` + the non-qualified part in `otherprop` | `dividends` | added to `ltcg` |
| Tax-Calculator (`adapters/taxcalc/projection.py`) | `e00600` | `e00650` | `e01100` |
| Axiom benefit mapping (`adapters/axiom/generic_inputs.py`) | `DIVIDEND_INCOME`, once | not in the lists | none (see below) |

Whose amounts each engine sums:

- TAXSIM, Tax-Calculator and the Axiom AGI leaves sum the filers (head and
  spouse). So does every Axiom line 7a input: a dependent's distributions
  belong to the dependent's own return, in AGI and in the 1(h) base alike.
- The Axiom bridge's qualified-dividend and Schedule D leaves
  (`capital_gains_tax_*`, the 1(h) qualified-dividend input) sum every
  tax-unit member, dependents included, as PolicyEngine-US 1.764.6's
  `add(tax_unit, ...)` does. PolicyEngine/policyengine-us#9869 reported that
  sum as wrong for the filer's 1(h) base, PolicyEngine-US 2.35.2 moved its
  worksheet to the head and spouse, and axiom-oracles#619 tracks moving the
  bridge's leaves to the filers. PolicyEngine-US 1.764.6 also sums
  `non_sch_d_capital_gains` over every member.
- The engines pick the filers from the Case's relations. When a Case names
  no spouse, PolicyEngine and the Axiom bridge fall back to the two oldest
  adults while TAXSIM and Tax-Calculator take only named relations, so
  "the same filers" holds for Cases whose relations name the head and
  spouse. The Schedule D fold below never uses that fallback.

No projection models Exception 1's second condition: Form 1099-DIV boxes
2b, 2c and 2d have no Case concept, so every projection treats a return as
meeting it.

## What the Populace producer loads

`populations/populace_us.py` builds line 3b as `qualified_dividend_income +
non_qualified_dividend_income` and line 3a as `qualified_dividend_income`,
and fails closed if PolicyEngine cannot calculate either.

It does not read the artifact's stored `dividend_income` column.
PolicyEngine-US defines `dividend_income` as an alias of
`ordinary_dividend_income`, the sum above. The pinned Populace US 2024
artifact also stores a legacy column under that name, and a stored value
overrides the alias; PolicyEngine/microcosm#24 lists it among the
formula-owned columns the artifact should not store. In the pinned artifact
(sha256 `16be6338f9d0...`, raw 2024 values, unweighted;
`scripts/probe_case_investment_income.py` prints every artifact figure on
this page):

| Column | Nonzero persons | Sum |
|---|---|---|
| `dividend_income` (stored legacy) | 16,090 | $85.7M |
| `qualified_dividend_income` | 29,206 | $28.64B |
| `non_qualified_dividend_income` | 24,426 | $6.42B |
| `non_sch_d_capital_gains` | 3,086 | $25.1M |

The legacy column can't serve as line 3b: it falls short of the qualified
amount on 2,631 of the 4,103 persons that carry both. Nor does it add to the
split. Every amount in the split sits on a tax-unit head row, while the
legacy column also has amounts on 4,969 spouse rows and 142 dependent rows,
and 11,760 persons carry it with no split at all ($59.0M); the Case carries
no dividends for them.

The loader reads line 7a, fail closed, on both case units, like the Schedule
D gains: both report one kind of income, and the fold below must give a
person the same dividend and capital-gain facts on a household Case and on a
tax-unit Case. No Axiom benefit income list
(`axiom_oracles/data/populace_input_mapping.yaml`) reads capital gains of
either kind, while PolicyEngine's `medicaid_magi` starts from AGI, so the two
engines' benefit inputs differ on Schedule D gains and line 7a alike.

## Schedule D fold

Exception 1 sets a condition on a return, so a return never has both line 7a
and Schedule D amounts. When the people on one return carry a Schedule D
amount (a nonzero short- or long-term gain or loss), the fold adds each
one's capital gain distributions to that person's long-term gain and drops
the line 7a fact. A tax unit's filers (head and spouse) make one return; a
dependent's gains belong to the dependent's own return, so a child's capital
loss never moves the parents' line 7a.

The head and the spouse the Case names file one return; everyone else files
alone. On a tax-unit Case they match the tax unit's filers. A household Case
names no spouse (the producer makes person 0 the head, anyone under 18 a
"Child" and every other adult "Other"), so there every adult files alone,
and an adult child's capital loss never moves the head's line 7a.
PolicyEngine and the Axiom bridge price such a household as one tax unit,
pairing the two oldest adults, while the fold keeps to the returns the Case
names.

The same function applies the fold twice:

- The Populace producer folds each tax unit (`fold_tax_unit_returns`), on
  either case unit, and records how many people it folded in
  `metadata["capital_gain_distributions_folded_into_schedule_d"]`, so the
  Case itself holds coherent returns. In the pinned artifact 3,086 persons
  carry line 7a, one per tax unit; 23 of them also carry a Schedule D
  amount on the same row (14 a capital loss), and the fold moves their
  line 7a, which leaves 3,063 tax units with line 7a.
- Every tax projection folds the people it prices
  (`with_schedule_d_fold`), so every engine prices a hand-built or future
  Case that carries both paths identically. On a Case the producer
  built it moves nothing: a tax-unit Case names the returns the producer
  folded, and a household Case splits them further, into one person each.
  TAXSIM needs no fold: its `ltcg` column takes Schedule D long-term gain
  plus line 7a on either path.

Grouping the projection fold by the two oldest adults instead would move
line 7a onto Schedule D on 70 household Cases of the pinned artifact
(unweighted, all states), where the two oldest adults head different tax
units, one with line 7a and the other with a Schedule D amount. In all, 144
households have line 7a beside another tax unit's Schedule D amount.

The state-tax campaign's TAXSIM leg (`bridges/state_tax_populace_runner.py`)
reads the same dividend and line 7a sources as the loader.

## Engine differences to expect

- **PolicyEngine-US 1.752.2**, which the Case suites pin, predates
  PolicyEngine/policyengine-us#8839 (issue #8828): `non_sch_d_capital_gains`
  enters its capital gains worksheet but not gross income or net investment
  income. On a unit with line 7a its AGI falls short by that amount. The issue
  closed on 2026-07-05; 1.764.6 has the fix and reproduces the worked
  returns in `tests/test_investment_income_live_engines.py` to the cent.
- **Tax-Calculator 6.7.1** counts `e01100` in AGI and in the capital gains
  worksheet, but leaves it out of its EITC investment income, its net
  investment income and its QBI income limit. PSLmodels/Tax-Calculator#3181
  reported the last two, and Tax-Calculator 6.8.5 counts `e01100` in all
  three.
- **TAXSIM-35** has no line 7a column; the amount rides in `ltcg`, as the
  long-term gain 852(b)(3)(B) makes it. Two behaviors of the pinned binary
  show up in the live tests:
  - On the worked 2026 return whose preferential income straddles the
    $49,450 zero-rate amount, its tax falls $67.40 short of the worksheet,
    by the same amount whether the return enters the gain as line 7a or as
    Schedule D long-term gain.
  - Its EITC investment-income test (which the live tests run at law year
    2024, since the binary has no child EITC at 2026) counts `intrec`,
    `dividends`, `otherprop` and `ltcg` alike, so it covers every Case line; but it
    reduces the credit dollar for dollar above the limit instead of
    disallowing it.
- **Schedule D worksheet line 9.** PolicyEngine-US 1.764.6's `dwks09`
  sums `non_sch_d_capital_gains` over every member and takes that sum in
  place of the Schedule D term whenever the sum exceeds zero. Tax-Calculator
  6.7.1's `dwks9` adds `e01100` to the Schedule D term ("The two cases are
  mutually exclusive, so the sum captures both"), and so does the Axiom
  bridge's `capital_gains_worksheet_line_9`. The forms agree on a return
  without both, which the fold leaves on every return. They differ only
  where a sum over people the fold treats as separate returns puts one
  person's line 7a beside another's Schedule D amount: the bridge's
  every-member `capital_gains_tax_*` leaves (a dependent's gain beside the
  filers' line 7a), PolicyEngine's `add(tax_unit, ...)`, and a household
  that PolicyEngine or the bridge prices as one tax unit. There the bridge
  also disagrees with itself on a loss: line 9 floors the Schedule D term at
  zero and then adds line 7a, while the 26 USC 1(h) long-term gain input adds
  line 7a to the every-member gain as it stands. A dependent's 1,000
  long-term loss beside the filer's 2,000 of line 7a leaves line 9 at 2,000
  and takes 1,000 off the 1(h) net capital gain (axiom-oracles#619 tracks the
  every-member leaves). In the pinned artifact every line 7a and Schedule
  D amount sits on a tax-unit head row, so no tax-unit Case has both; 71
  household Cases do once the household prices as one tax unit. Within
  the bridge, line 9 reaches only worksheet lines 10, 13, 14 and 19 and the
  Form 6251 Part III capital gain lines.
- **Axiom** leaves 26 USC 1411 out of the composed program
  (axiom-encode#1213). The bridge's 1411 net-gain rule includes line 7a
  (Form 8960 line 5a) but stays inert while the composed program leaves
  1411 out, so the Axiom side computes no net investment income tax on
  dividends, line 7a or any other investment income.
