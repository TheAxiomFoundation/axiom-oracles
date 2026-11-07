# Tax-exempt interest in the benefit lanes

Household Cases carry `Concepts.TAX_EXEMPT_INTEREST_INCOME` (Form 1040 line 2a: interest that 26 USC 103 keeps out of federal gross income, mostly state and municipal bond interest) beside the taxable `Concepts.INTEREST_INCOME` (line 2b). PolicyEngine receives both. The Axiom input projection (`axiom_oracles/data/populace_input_mapping.yaml`) lists line 2a only for the programs whose own income definition counts it.

None of the programs behind the 22 benefit suites (axiom-oracles#567) distinguishes taxable from tax-exempt interest: each either counts interest or does not.

## Summary

| Program | Suites | Counts interest? | Axiom input projection |
|---|---|---|---|
| SNAP | al, az, ca, ga, ma, nc, ny, sc, tn | Yes | Both interest facts in every SNAP income slot |
| SNAP | fl | No (state option) | Both interest facts, since rulespec-us does not encode the exclusion yet (rulespec-us#1646) |
| TANF | al, ca, co, de, mn, ny, wa | Yes | Both interest facts in each state's income slots |
| TANF | az | Yes, when paid out | Both interest facts, as an upper bound |
| TANF | ga | No | Neither interest fact; dividends stay |
| TANF | ks | Yes | No income slot; the suite compares only the maximum benefit |
| SSI | ssi | No, nor dividends | Neither interest fact, nor dividends |
| Medicaid MAGI | medicaid-magi-co | Yes | Both interest facts |

PolicyEngine counts taxable and tax-exempt interest in all four programs (`interest_income` adds the two; Medicaid MAGI adds tax-exempt interest to adjusted gross income). Where the law does not, we filed a PolicyEngine issue: SSI (PolicyEngine/policyengine-us#10079), Florida SNAP and TCA (#10080) and Georgia TANF (#10081).

## Sources

We retrieved every quotation below from its linked source on 2026-10-10, fetching the federal texts and Georgia's TANF chart directly. The state texts come from the research and adversarial-verification runs for #567, which quote the official source where they could reach it and name Cornell LII where they fell back to it. Each date gives the edition or revision the source states.

## SNAP

**Federal rule.** 7 CFR 273.9(b)(2)(v) ([eCFR](https://www.ecfr.gov/current/title-7/section-273.9), current 2026-10-01) lists as unearned income:

> Payments from Government-sponsored programs, dividends, interest, royalties, and all other direct money payments from any source which can be construed to be a gain or benefit.

No exclusion in 273.9(c) turns on federal tax treatment. A state may go further under 273.9(c)(19): "At the State agency's option, any types of income that the State agency excludes when determining eligibility or benefits for TANF cash assistance".

**States that follow the federal rule.**

| State | Text | Source |
|---|---|---|
| AL | "dividends, interest, royalties" (unearned income list); the $30-a-quarter irregular-income exclusion begins "Other than interest income" | DHR SNAP Points of Eligibility Manual, ch. 9, §901 B.5 and §902(10) |
| AZ | "For NA, interest payments are countable as unearned income regardless of how the payments are received." | DES CNAP Manual, FAA4, Interest Payments (revised 2025-10-27) |
| CA | "Payments from government-sponsored programs, dividends, interest, royalties" | CDSS MPP 63-502.146 |
| GA | Interest: "UNEARNED-Income received on investments.", treatment I (included) | DFCS SNAP Policy Manual §3420, Chart 3420.2 (effective November 2025) |
| MA | "Interest income is countable unearned income in SNAP"; tax forms are read for "Taxable and Tax-Exempt Interest as Interest Income" | DTA Transitions, February 2014; DTA online guide, "How to Read a 1040" |
| NC | Interest and dividend income: "Interest paid from stocks, bonds, bank accounts and other Investments", counted, unearned | FNS 300.02 (change 01-2022) |
| NY | "Interest, except interest from funeral agreements or accounts." | OTDA SNAP Source Book §13.C (revised July 2025) |
| SC | "interest income of any amount must be verified." | DSS SNAP Manual vol. 69 §11.5(T) (January 2026) |
| TN | "Interest payments, dividends, and royalty's income and all other such direct money payments that can be for gain or benefit" | DHS Policy 24.14 §D.6 (effective 2022-01-04) |

Arizona stops counting interest, dividends and royalties for SNAP and cash assistance "effective the benefit month of 06/2026" (DES urgent bulletin, 2026-05-15). The suites run January 2026.

The sc-snap and tn-snap suites leave out two small-amount rules whose current force we could not settle. South Carolina's SNAP manual adopted its TANF interest treatment in 2016 ("SNAP will follow SC TANF Policy regarding interest income"). The TANF regulation excludes "Up to four hundred dollars of interest and dividends per benefit group" a year (S.C. Code Regs. 114-1140(N)(2)), and we could not confirm that SNAP still follows it. Tennessee's 2017 manual counted interest only "in excess of $60 quarterly", and the current Policy 24.14 does not repeat it.

**Florida.** DCF ESS Program Policy Manual, passage 1810.1000 (FS):

> Payments of dividends and interest on countable assets, including interest on bank accounts, are excluded as unearned income. This includes interest on a trust account when the interest is either paid to the assistance group, or allowed to accrue to the account at the option of the recipient. Royalties are counted as unearned income.

Passage 1820.1000 gives cash assistance the matching rule, as 273.9(c)(19) requires. Florida's composed SNAP program takes unearned income through the shared federal input `snap_total_monthly_unearned_income`. Nothing feeds the separate `snap_income_exclusions` input of 7 CFR 273.10, so Axiom counts Florida's interest, as PolicyEngine does. The two engines agree, and both overstate income. rulespec-us#1646 tracks the missing exclusion.

## TANF

| State | Rule | Source |
|---|---|---|
| AL | "Only currently available gross income is taken into consideration ... unless specifically excluded according to State and Federal law or as otherwise provided for in program operating manuals."; "Interest is considered available to the account holder" | Ala. Admin. Code r. 660-2-2-.30(1); Public Assistance Payment Manual §3225E |
| AZ | Unearned income counts "Minus those types of income excluded under R6-12-503", which lists "Dividends, interest, and royalty payments left on deposit or converted into additional securities" | A.A.C. R6-12-501(B)(3)–(4), R6-12-503(29) |
| CA | "All interest received is net income" (personal property: interest on money, stocks, bonds) | CDSS MPP 44-113.1(e) |
| CO | "Unless otherwise specified, any unearned income is countable"; the list includes "Dividends and interest received on savings bonds, leases, etc." | 9 CCR 2503-6 §3.605.3 and §3.605.3.A.15 |
| DE | "Interest or dividends from a potential resource that is not yet available is counted as income." | DSSM (16 Del. Admin. Code 4000) §4002.1 |
| GA | Interest: "UNEARNED – income received on investments.", treatment E, "excluded (E) in determining financial eligibility and benefit amount"; Dividend: treatment I | DFCS TANF Policy Manual (PAMMS) §1530, Chart 1530.1 (effective February 2025) |
| KS | "“Unearned income” means all income not earned." | K.A.R. 30-4-110(a)(2) |
| MN | Unearned income includes "interest and dividends from investments and savings"; "Count interest or dividends as unearned income." | Minn. Stat. 256P.06 subd. 3(2)(i); Combined Manual 0017.15.42 |
| NY | "Normally, accrued interest on an exempt resource is countable unearned income in the month received and countable toward the resource limit in ensuing months." | OTDA 03-INF-25, attachment, Q47; 18 NYCRR 352.22 lists the exemptions and has none for interest |
| WA | "Unearned income is income you get from a source other than employment or self-employment."; "Count interest income as unearned income" | WAC 388-450-0025(1); DSHS EA-Z Manual, Treatment of Income |

**Arizona.** The population carries annual interest totals and does not record whether the holder took the interest or left it on deposit, so the projection counts every dollar. That overstates income on both engines wherever interest stayed on deposit.

**Georgia.** Georgia's TANF program reads its own income slot, `assistance_unit_included_income`, so the projection follows the chart: interest out, dividends in. PolicyEngine's Georgia TANF uses the federal source list, which counts interest (PolicyEngine/policyengine-us#10081). rulespec-us does not encode the chart yet (rulespec-us#1648).

**Kansas.** Interest counts, with two conflicting small-amount exemptions (K.A.R. 30-4-113(p): "interest income that does not exceed $50.00 per month per family group"; KEESM 6410(35): interest and dividends "received irregularly", "unpredictable" and "less than $30 in a quarter"). The composed Kansas program compares only the maximum benefit and has no income input.

**Narrow exclusions.** The population cannot identify interest held in individual development accounts, ABLE accounts, specified tribal trust funds, California restricted accounts or New York tuition accounts. Nor can it identify the income a state's small or infrequent-income rule excludes, so none of the suites models these exclusions.

## SSI

42 USC 1382a(b)(23) ([U.S. Code, 2023 edition](https://www.govinfo.gov/content/pkg/USCODE-2023-title42/html/USCODE-2023-title42-chap7-subchapXVI-partA-sec1382a.htm); section 430 of P.L. 108-203, for benefits payable from July 2004) excludes from income:

> (23) interest or dividend income from resources— (A) not excluded under section 1382b(a) of this title, or (B) excluded pursuant to Federal law other than section 1382b(a) of this title;

20 CFR 416.1124(c)(22) ([eCFR](https://www.ecfr.gov/current/title-20/section-416.1124), current 2026-10-01): "We do not count as unearned income— ... (22) Interest and dividend income from a countable resource or from a resource excluded under a Federal statute other than section 1613(a) of the Social Security Act".

20 CFR 416.1201(b) gives stocks, bonds and financial institution accounts as examples of "ordinarily liquid" resources, and POMS SI 01140.250 B counts bonds as resources: "Municipal, corporate, and government bonds are negotiable and transferable. Therefore, their value as a resource is their CMV."

The SSI program spec computes countable unearned income as the input `annual_income_not_paid_on_basis_of_need` less the $20 monthly general exclusion, and rulespec-us encodes only 1382a(b)(2) and (b)(4). So the projection carries the (b)(23) exclusion: it leaves interest and dividends out of that input and out of the couple transform, treating all of a person's interest and dividends as income from countable resources. Income from a resource that 1382b(a) excludes follows that exclusion's own rule, which the projection does not model. rulespec-us#1645 tracks encoding (b)(23). PolicyEngine counts the income (PolicyEngine/policyengine-us#10079).

## Medicaid MAGI

42 CFR 435.603(e) ([eCFR](https://www.ecfr.gov/current/title-42/section-435.603), current 2026-10-01): "MAGI-based income means income calculated using the same financial methodologies used to determine modified adjusted gross income as defined in section 36B(d)(2)(B) of the Code".

26 USC 36B(d)(2)(B) ([U.S. Code, 2023 edition](https://www.govinfo.gov/content/pkg/USCODE-2023-title26/html/USCODE-2023-title26-subtitleA-chap1-subchapA-partIV-subpartC-sec36B.htm)):

> The term "modified adjusted gross income" means adjusted gross income increased by— (i) any amount excluded from gross income under section 911, (ii) any amount of interest received or accrued by the taxpayer during the taxable year which is exempt from tax, and (iii) an amount equal to the portion of the taxpayer's social security benefits (as defined in section 86(d)) which is not included in gross income under section 86 for the taxable year.

Colorado's rule lists "Interest (includes tax exempt interest)" among MAGI income (10 CCR 2505-10 §8.100.4.C.1.b.i).

## Dashboards and dispositions

The 22 benefit suites run outside CI (`ci: manual`), and their committed dashboard reports predate the projection above. A dispositions edit lands only with a refreshed report:

- `scripts/apply_dispositions.py` merges each suite's entries into its report's `summary.dispositioned` block, and `--check` fails when a committed report differs from that merge.
- `conformance/legacy-engine-identity.json` freezes each of these reports byte for byte.
- An edited report must carry a receipt-bound engine identity (`docs/engine-publication-identity.md`).

We measured the projection with an A/B that ran both arms in one pinned toolchain. axiom-oracles#690 records the results and what the next identity-bound refresh of each report owes. For SSI, that refresh adds an `upstream_engine_gap` entry for the rows where PolicyEngine counts interest and dividends, citing PolicyEngine/policyengine-us#10079 and rulespec-us#1645.

## Tests

- `tests/test_tax_exempt_interest_benefit_inputs.py`: for every income slot the 22 compiled programs read, moving interest between line 2b and line 2a changes nothing; the SSI inputs ignore interest and dividends; Georgia's TANF input ignores interest and keeps dividends; no mapping entry names one interest fact without the other.
- `tests/test_tax_exempt_interest_policyengine_live.py` (CI's `policyengine-live` job): PolicyEngine gives the two kinds of interest the same weight in SNAP, TANF and Medicaid MAGI, and still counts interest in SSI. When PolicyEngine fixes PolicyEngine/policyengine-us#10079, the SSI test fails. Retire the test then, with any SSI disposition that cites the issue (axiom-oracles#690).
