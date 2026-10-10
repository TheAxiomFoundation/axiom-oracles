# Farm rental income on the Case surface

`Concepts.FARM_RENT_INCOME` is Schedule E (Form 1040) line 40: net farm rental
income or (loss) from Form 4835, per person, signed. This page records how
each tax engine receives it, the decisions the Axiom federal oracle bridge
makes where the law turns on facts the Case does not carry, and the known
departures between engines. It closes axiom-oracles#566.

Every quotation was extracted on 2026-10-10 from the source named beside it.
IRS forms, instructions and publications are the 2025 revisions on irs.gov;
statute text is from law.cornell.edu (its §199A text includes the Pub. L.
119-21 amendments); regulations are from eCFR.

## Where the amount sits on the return

- Form 4835 (2025), header: "Farm Rental Income and Expenses (Crop and
  Livestock Shares (Not Cash) Received by Landowner (or Sub-Lessor)) (Income
  Not Subject to Self-Employment Tax)".
- Form 4835 line 32: "Net farm rental income or (loss). Subtract line 31 from
  line 7. If the result is income, enter it here and on Schedule E (Form
  1040), line 40. If the result is a loss, you must go to line 34." Line 34c:
  "enter the deductible loss here and on Schedule E (Form 1040), line 40."
- Schedule E (2025), line 41: "Total income or (loss). Combine lines 26, 32,
  37, 39, and 40. Enter the result here and on Schedule 1 (Form 1040), line
  5".

The data source is the Populace `farm_rent_income` column, built from PUF
`E27200` ("Sch E: Farm rent net income or loss"). The pinned Populace US 2024
artifact has 1,065 person rows with a nonzero amount, 320 of them negative
(counted 2026-09-27, per axiom-oracles#566).

## What each engine receives

| Engine | Input | Reaches |
|---|---|---|
| Axiom bridge | `person_farm_rent_income` (every person) | Gross income (positive part, filers); the §461(l) business income and loss sums (filers); QBI (all members, as for Part I rents); Pub. 596 Worksheet 1 lines 11-13; the §1411 rents input; the Colorado withholding proxy; the head-of-household gross-income test for dependents |
| PolicyEngine-US | `farm_rent_income` | Gross income, `loss_ald`, QBI. Not `eitc_relevant_investment_income` and not `net_investment_income` (see departures) |
| TAXSIM | `otherprop` (head + spouse) | AGI and EITC investment income. No QBID |
| Tax-Calculator | `e02000 +=`, `e27200 =` (head + spouse) | AGI and EITC investment income through `e02000`; QBI through `e27200` |

The Populace loader carries it on **tax-unit** Cases only. Household Cases
feed the benefit lanes, where PolicyEngine counts farm rent (Medicaid MAGI
through AGI; the TX, IL and SC TANF unearned income lists) and the Axiom
benefit encodings do not read it yet (axiom-oracles#610).

## Decision 1: farm rent is qualified business income

**The law.** 26 USC 199A(c)(1): "The term “qualified business income” means,
for any taxable year, the net amount of qualified items of income, gain,
deduction, and loss with respect to any qualified trade or business of the
taxpayer." The exclusions in 199A(c)(3)(B) are capital gains and losses,
dividends, interest "other than interest income which is properly allocable
to a trade or business", certain section 954(c)(1) items, and annuities not
received in connection with the trade or business. Rents are not among them.
So the question is whether the rental is a trade or business:

- 26 CFR 1.199A-1(b)(14): "Trade or business means a trade or business that
  is a trade or business under section 162 (a section 162 trade or business)
  other than the trade or business of performing services as an employee. In
  addition, rental or licensing of tangible or intangible property (rental
  activity) that does not rise to the level of a section 162 trade or business
  is nevertheless treated as a trade or business for purposes of section 199A,
  if the property is rented or licensed to a trade or business conducted by
  the individual or an RPE which is commonly controlled".
- Instructions for Form 8995 (2025): "an activity qualifies as a trade or
  business if your primary purpose for engaging in the activity is for income
  or profit and you're involved in the activity with continuity and
  regularity"; "Material participation under section 469 isn't required to
  qualify for the QBI deduction"; "The ownership and rental of real property
  may constitute a trade or business if it meets the standard described
  above."
- For crop shares specifically, Treasury's closest statement is 26 CFR
  1.175-3: "For the purpose of section 175, a taxpayer who receives a rental
  (either in cash or in kind) which is based upon farm production is engaged
  in the business of farming. However, a taxpayer who receives a fixed rental
  (without reference to production) is engaged in the business of farming
  only if he participates to a material extent in the operation or management
  of the farm." Pub. 225 (2025) repeats it under conservation expenses. It is
  written for section 175, so it does not settle section 199A, but Form 4835
  covers only production-based rent ("Crop and Livestock Shares (Not Cash)").

**What the sources do not say.** No IRS form, instruction or publication read
here says Form 4835 income is, or is not, QBI as such. The 2025 Schedule E
instructions and Form 4835 instructions do not mention the QBI deduction.

**The decision.** Whether one landowner's rental is a section 162 trade or
business depends on facts the Case does not carry (the lease terms, the
landowner's continuity and regularity, whether the tenant is a commonly
controlled business). The bridge therefore needs a convention, and it uses the
one it already applies to Schedule E Part I rents: the rent is QBI. That also
matches PolicyEngine-US (`farm_rent_income_would_be_qualified` defaults to
true) and Tax-Calculator (`e27200` is in `qbinc`). TAXSIM's `otherprop` is
"rent not eligible for QBI deduction", so its leg grants none.

**The $400 minimum.** 26 USC 199A(i)(2)(B) limits the minimum deduction to
"any qualified trade or business of the taxpayer in which the taxpayer
materially participates (within the meaning of section 469(h))". The bridge,
like PolicyEngine, tests the $1,000 floor against all QBI, farm rent and Part
I rents included. Form 4835 is for a landowner who "did not materially
participate (for self-employment tax purposes)", but that is the section
1402(a)(1) test, and 469(h)(3) separately treats certain retired farmers and
surviving spouses as materially participating "in any farming activity". So
this too turns on facts the Case lacks, and the convention is left as it is.

## Decision 2: income and loss enter §461(l) as trade-or-business amounts

26 USC 461(l)(3)(A) measures "the aggregate deductions of the taxpayer for
the taxable year which are attributable to trades or businesses of such
taxpayer" against "the aggregate gross income or gain of such taxpayer for
the taxable year which is attributable to such trades or businesses, plus"
the threshold. Form 461 (2025) line 5 is "Enter amount from Schedule 1 (Form
1040), line 5", and lines 10 and 11 take back out "income or gain" and
"losses or deductions" that are "not attributable to a trade or business".

Having treated the farm rental as a trade or business for QBI, the bridge
treats it the same way here, as it does Part I rents and as PolicyEngine's
`loss_ald` does:

- the positive part is a gross-income leaf and counts as business gross
  income, so it raises the loss allowance;
- the loss is deducted above the line inside the limited business-loss sum.

Not modeled: the passive loss rules. Form 4835 says "Use this form only if
the activity was a rental activity for purposes of the passive activity loss
limitations", line 34c is the loss after Form 8582, and Pub. 225 says "any
loss from these activities may be subject to the limits under the passive
loss rules." No engine on the Case surface applies section 469 to rents.

The bridge's 2026 threshold is 305,000 (610,000 joint), the value in the
pinned PolicyEngine. Rev. Proc. 2025-32 section .31 sets $256,000 ($512,000).
That predates this work and is tracked in axiom-oracles#611.

## Decision 3: farm rent is passive income in the EITC investment-income test

Pub. 596 (2025) Worksheet 1: "11. Enter the total of any net income from
passive activities (such as income included on Schedule E, line 26, 29a (col.
(h)), 34a (col. (d)), or 40; or an ordinary gain on Form 4797, line 10)";
"12. Enter the total of any losses from passive activities (such as losses
included on Schedule E, line 26, 29b (col. (g)), 34b (col. (c)), or 40 ...)";
"13. Combine the amounts on lines 11 and 12 of this worksheet. (If the result
is less than zero, enter -0-.)"

The filers' farm rent is added to their Part I rents before the line 13
floor, so a loss on one offsets income on the other and a net loss never
offsets interest, dividends or capital gains.

## Decision 4: farm rent is net investment income

Instructions for Form 8960 (2025), line 4a: "Enter the following amount from
your properly completed return. • Schedule 1 (Form 1040), line 3. • Schedule
1 (Form 1040), line 5. • Schedule 1 (Form 1040), line 6." And: "Farm income
from a passive activity is subject to the tax under section 1411(c)(2)."
26 USC 469(c)(2): "the term “passive activity” includes any rental activity."

The projection adds the filers' farm rent to the section 1411 rents input.
This has no effect today: `us:statutes/26/1411` is stripped from every
composition (`_tax_oracle_imports_for_concepts` in `axiom_oracles/cli.py`).
Not modeled: Form 8960 line 4b adjustments, including rental income
recharacterized as nonpassive.

## Known departures

| Departure | Side | Record |
|---|---|---|
| PolicyEngine leaves farm rent out of the EITC investment-income test, so its credit survives above $12,200 | PolicyEngine | PolicyEngine/policyengine-us#9635; Axiom encoding debt TheAxiomFoundation/rulespec-us#1416 |
| PolicyEngine leaves farm rent out of net investment income | PolicyEngine | PolicyEngine/policyengine-us#10075 (moot on the Axiom lanes while §1411 is stripped) |
| The pinned PolicyEngine sums dependents' losses into `loss_ald`; the bridge sums filers only | PolicyEngine | PolicyEngine/policyengine-us#9646 (closed 2026-10-03) |
| TAXSIM grants no QBID on `otherprop` | TAXSIM | `docs/taxsim-oracle-playbook.md`, "no rental in the QBI base" |
| TAXSIM reduces the childless EITC dollar for dollar above the investment-income limit instead of denying it | TAXSIM | disposition class `taxsim-2026-eitc-investment-limit-vintage` |
| Tax-Calculator applies the 2026 §461(l) threshold of 256,000; the bridge and the pinned PolicyEngine apply 305,000 | bridge and PolicyEngine | axiom-oracles#611 |
| TAXSIM and Tax-Calculator rows carry head + spouse income only, so a dependent's farm rent reaches neither | projection surface | the playbook's dependent non-wage income class |

## Verification

- `tests/test_farm_rent_case_surface.py`: the projections, with Hypothesis
  invariants (a filer's farm rent moves exactly its Axiom inputs, the TAXSIM
  `otherprop` column and the Tax-Calculator `e02000`/`e27200` pair, by exactly
  the stated amounts; `e27200` is always inside `e02000`).
- `tests/test_eitc_investment_income_worksheet1.py`: Worksheet 1 by hand, and
  a differential against the Populace bridge's projection.
- `tests/test_axiom_farm_rent_engine.py`: worked examples from the forms on
  the pinned Axiom engine.
- `tests/test_farm_rent_cross_engine.py`: the same households through Axiom,
  PolicyEngine, Tax-Calculator and TAXSIM, plus a seeded differential of
  Axiom against PolicyEngine AGI.

The last two need the pinned engine checkout and the engine extras, so they
skip on CI.
