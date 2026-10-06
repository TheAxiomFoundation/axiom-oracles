# MFS statutory hand computation, tax year 2026

Computed 2026-09-24. This file is the external ground truth for adjudicating engine residues on the 13 synthetic married-filing-separately cases. It uses only the verbatim extracts in `mfs-statute-extracts.md` (cited below as "X §n", meaning section n of that file). Section 15 of that file was appended for this computation by `supplement.py`. It adds §1(b), §3, §24(c), §26, §32(a) and (c), §55, §56(b)(1)(D), §151(c), and Rev. Proc. 2025-32 §4.10. `verify_quotes.py` still finds every quoted line verbatim in `raw/` (970 lines checked, 0 missing).

`hand_compute_check.py`, next to this file, reruns every figure below in exact decimal arithmetic. It reproduces all of them.

No engine output was used. Engines produce hypotheses, not evidence (evidence rule 3).

## Facts common to every case, and the assumptions added to them

Facts as given: each filer is a Colorado resident, married at the close of 2026, and not filing jointly. The other spouse is not on the return. Neither spouse itemizes. Income is wages only unless noted.

Assumptions added so the law can be applied. Each is needed, and each is flagged again under uncertainties where it matters.

- **A1.** Wages are §3121(a) wages from a single employer. All of them are includible in gross income, and there are no pre-tax exclusions, tips, overtime premiums, self-employment income, investment income, or adjustments to income. So AGI = wages + taxable Social Security.
- **A2.** The filer is not blind. No additional amount is claimed for the spouse. §63(f)(1)(B) and (2)(B) allow the spouse's amount on a separate return only if a §151(b) exemption is allowable for the spouse, and that needs the spouse to have no gross income (X §4, §8). The spouse's age and income are not given.
- **A3.** The filer and the child are US citizens or residents with SSNs valid under §24(h)(7)(B), and the return lists them (§24(h)(7), §32(c)(1)(E), §32(c)(3)(D); X §9, §15.5). Nobody is anyone else's dependent. There is no decree of divorce or separate maintenance (§7703(a)(2)). The spouse is alive and is not a nonresident alien (§2(b)(2)(B)-(C)). There is no prior-year EITC disallowance.
- **A4.** In the child cases, the child is the filer's son or daughter, so a "child" within §152(f)(1) (X §10). The child is under 17, lived with the filer in the US all year, did not provide over half of their own support, and is the filer's §152(c), §24(c), and §32(c)(3) qualifying child. The other spouse did not live with the child, so no competing claim exists.
- **A5.** The tax before credits is the §1 rate-table tax from Rev. Proc. 2025-32 §4.01 (X §11.2), as the task directs. See uncertainty U1 on §3 tax tables.

## 2026 parameters used (all from the extracts)

| Item | Amount | Source |
|---|---|---|
| MFS rate table (Table 4) | 10% to $12,400; $1,240 + 12% to $50,400; $5,800 + 22% to $105,700; $17,966 + 24% to $201,775; $41,024 + 32% to $256,225; $58,448 + 35% to $384,350; $103,291.75 + 37% above | Rev. Proc. 2025-32 §4.01 Table 4 (X §11.2); IRB 2025-45 matches (X §11.7) |
| HoH rate table (Table 2) | 10% to $17,700; $1,770 + 12% to $67,450; $7,740 + 22% to $105,700; ... | Rev. Proc. 2025-32 §4.01 Table 2 (X §11.2) |
| Basic standard deduction, MFS / HoH | $16,100 / $24,150 | §63(c)(2)(B)-(C), (c)(7); Rev. Proc. 2025-32 §4.14(1) (X §4, §11.5) |
| Additional amount, aged, married | $1,650 ($2,050 only if "unmarried and not a surviving spouse") | §63(f)(1)(A), (f)(3), (g); Rev. Proc. 2025-32 §4.14(3) (X §4, §11.5) |
| Senior deduction | $6,000, but for a §7703 married individual only on a joint return | §151(d)(5)(C)(i), (v) (X §8) |
| §86 base / adjusted base | $25,000 / $34,000; **zero / zero** for a married non-joint filer who did not live apart from the spouse at all times during the year; not indexed | §86(c)(1)-(2) (X §5) |
| EITC, 1 child | credit 34%, phaseout 15.98%; earned income amount $13,020; phaseout amount $23,890 ('all other') | §32(b)(1) (X §6); Rev. Proc. 2025-32 §4.06 (X §11.4) |
| EITC, no child | 7.65% / 7.65%; $8,680; $10,860 ('all other') | same |
| CTC | $2,200 per child; refundable cap $1,700 per child; refundable floor $2,500 at 15%; phase-out threshold $200,000 for any non-joint return | §24(a), (d)(1), (h)(2)-(6), (i); Rev. Proc. 2025-32 §4.05 (X §9, §11.3) |
| OASDI | 6.2% of wages up to the contribution and benefit base, $184,500 | §3101(a), §3121(a)(1); SSA FR notice and ssa.gov (X §7, §7.1) |
| HI | 1.45% of all wages | §3101(b)(1) (X §7) |
| Additional Medicare | 0.9% of wages over $125,000 (MFS: ½ × $250,000); $200,000 "in any other case"; not indexed | §3101(b)(2) (X §7, §13) |
| AMT, MFS | exemption $70,100; phase-out from $500,000 to $640,200; 26% up to $122,250 of taxable excess, then 28% | §55(a), (b)(1)(C), (d)(1)-(2), (d)(4); §56(b)(1)(D); Rev. Proc. 2025-32 §4.10 (X §15.6, §15.7, §15.9) |

## Filing status, by group

### Group 1 (mfs-wages-*) and group 4 (mfs-eitc-wages-*): married filing separately

- §7703(a)(1): marital status is determined at the close of the year. The filer is married.
- §7703(b)(1) applies only to a filer who maintains a household for a child for whom the filer is entitled to a §151 deduction. These filers have no dependents, so §7703(b) cannot apply, and §2(c) has nothing to act on.
- §2(b)(1) requires the filer to be "not married at the close of his taxable year" and to have a qualifying person. Both fail, so the filer is not a head of household.
- The filer is a "married individual (as defined in section 7703) who does not make a single return jointly" under §1(d). The tax comes from the §1(j)(2)(D) table as prescribed for 2026 in Rev. Proc. 2025-32 Table 4 (X §1.1, §1.3, §11.2).
- §63(c)(6)(A) is not triggered because neither spouse itemizes, so the MFS basic standard deduction of $16,100 applies (§63(c)(2)(C); X §11.5).

### Group 2 (mfs-child-wages-*): head of household

- §7703(b)(1)-(3) (X §3): the filer is married within the meaning of (a) and files a separate return (not a joint one).
  - The filer maintains as a home a household that was the principal place of abode of the filer's son or daughter (a §152(f)(1) child, A4) for all of 2026, which is more than half the year.
  - The filer is entitled to the §151(c) deduction for the child (X §15.8). The child is a §152(c) qualifying child and so a dependent. §151(d)(5)(B) says the zero exemption amount "shall not be taken into account in determining whether a deduction is allowed or allowable" (X §8).
  - The filer furnished over half the cost of the household.
  - The spouse was not a member of the household during the last 6 months, having lived apart all year.
  - So "such individual shall not be considered as married."
- §2(c) (X §2): "For purposes of this part" (Part I of subchapter A, which includes §§1, 2 and 3 per the uscode itempaths in X §2 and §15.2), the filer "shall be treated as not married at the close of the taxable year" because §7703(b) so treats them. §2(c) names §7703(b) expressly, so the open question in X §14 flag 1 (whether a bare reference to "section 7703" reaches subsection (b)) does not arise here.
- §2(b)(1)(A)(i) (X §2): the filer is not married at year end, is not a surviving spouse, and maintains a household that is the principal place of abode of a §152(c) qualifying child for more than half the year. The filer furnished over half the cost. §2(b)(3) does not disqualify the filer.
- **Result: head of household.** The tax is imposed by §1(b) on "every head of a household (as defined in section 2(b))" (X §15.1), using the §1(j)(2)(B) table, which is Rev. Proc. 2025-32 Table 2 for 2026 (X §11.2). The HoH basic standard deduction is $24,150 (§63(c)(2)(B), (c)(7); X §11.5). §2(b) makes this a status the law assigns, not an election, and §1(b) imposes the HoH tax on "every" head of household.
- **EITC under §32(d)** (X §6):
  - §32(d)(2)(A) sets marital status "under section 7703(a)". §7703(b) does not help here, so the filer starts out married, and §32(d)(1) would require a joint return.
  - §32(d)(2)(B) overrides that. The filer (i) is married under §7703(a) and does not file jointly, (ii) resides with a qualifying child for more than half the year (all year), and (iii)(I) does not share a principal place of abode with the spouse during the last 6 months.
  - So the filer "shall not be treated as married", and **the EITC is allowed**. Rev. Proc. 2025-32 §4.06 says such filers use the 'all other filing statuses' amounts (X §11.4).
- **CTC:** §24 has no joint-return condition. The (h)(3) phase-out threshold for any non-joint return is $200,000, far above the filer's AGI. **The CTC is allowed.**

### Group 3 (mfs-ss-*): married filing separately, age 70

There is no child, so §7703(b) cannot apply. All three filers are married under §7703(a) and are MFS, as in group 1. Three rules then differ by case:

- **§86(c)** (X §5):
  - Base amount and adjusted base amount are both **zero** for a taxpayer who "(i) is married as of the close of the taxable year (within the meaning of section 7703) but does not file a joint return for such year, and (ii) does not live apart from his spouse at all times during the taxable year." The cohabiting filers meet (i) and (ii), so both amounts are $0.
  - The lived-apart filer meets (i) but not (ii), having lived apart at all times. That filer falls to "(A) except as otherwise provided in this paragraph, $25,000" and the $34,000 adjusted base amount.
  - §86 has no inflation adjustment (X §5, full-section check).
- **§63(f)** (X §4): a filer who "has attained age 65 before the close of his taxable year" gets the additional amount. §63(f)(3) raises it to the $750 base ($2,050 in 2026) only for an individual "not married", and §63(g) determines marital status under §7703. All three filers are married, including the lived-apart one, because §7703(b) needs a child. So the amount is **$1,650** (Rev. Proc. 2025-32 §4.14(3)), and the standard deduction is 16,100 + 1,650 = **$17,750**.
- **§151(d)(5)(C)** (X §8): (v) says "If the taxpayer is a married individual (within the meaning of section 7703), this subparagraph shall apply only if the taxpayer and the taxpayer's spouse file a joint return." None of the three files jointly, so the **senior deduction is $0** for all three, including the lived-apart filer.
- **EITC:** §32(d)(1) bars it because the filers are married under §7703(a), file no joint return, and have no qualifying child, so (d)(2)(B)(ii) fails. Separately, the age-65 limit in §32(c)(1)(A)(ii)(II) fails too.

## Alternative minimum tax check (applies to every case)

§55(a) imposes AMT only to the extent that the tentative minimum tax exceeds the regular tax (X §15.6). §56(b)(1)(D) disallows the standard deduction in computing AMTI (X §15.7). So for these facts AMTI = AGI, assuming wages and Social Security carry no other §56-§58 adjustment or preference. The rest of §56-§58 is not extracted.

- **AGI at most $45,000 (every case except mfs-wages-150000 through -750000):** AMTI is below the smallest 2026 exemption, $70,100 for MFS (X §15.9). The tentative minimum tax is 0.
- **mfs-wages-150000:** the exemption is $70,100, because AMTI is under the $500,000 phase-out threshold. The taxable excess is 79,900, and 26% × 79,900 = 20,774, which is below the regular tax of 24,734. AMT = 0.
- **mfs-wages-250000:** the taxable excess is 179,900. TMT = 26% × 122,250 + 28% × 57,650 = 31,785 + 16,142 = 47,927, below 51,304. AMT = 0.
- **mfs-wages-450000:** the taxable excess is 379,900. TMT = 31,785 + 28% × 257,650 = 31,785 + 72,142 = 103,927, below 121,625.25. AMT = 0.
- **mfs-wages-750000:**
  - The exemption is 70,100 − 50% × (750,000 − 500,000), which is below zero, so it is 0. The Rev. Proc.'s $640,200 complete phase-out equals 500,000 + 70,100 / 0.5, which confirms the 50% rate.
  - The MFS add-back in the last sentence of §55(d)(2) is the lesser of 25% (or 50%, see the X §15.6 reading note) × (750,000 − 640,200) = 27,450 (or 54,900) and 70,100.
  - So AMTI is 777,450 (or 804,900), and TMT = 31,785 + 28% × 655,200 = 215,241 (or 31,785 + 28% × 682,650 = 222,927).
  - Both are below 232,625.25, so AMT = 0 under either reading.

So the §26(a)(2) term is 0 in every case, and the §26(a) limit on nonrefundable credits equals the regular tax liability (X §15.4).

## Case computations

Notation: SD = standard deduction, TI = taxable income, TBC = tax before credits. FICA is the employee share, with OASDI = 6.2% × min(wages, 184,500) and HI = 1.45% × wages. AddMed is the Additional Medicare Tax. Liability = TBC − nonrefundable credits − refundable credits.

### 1. mfs-wages-40000: MFS

- AGI = 40,000. SD = 16,100 (§63(c)(2)(C), (c)(7); X §11.5). No additional amounts.
- TI = 40,000 − 16,100 = 23,900.
- TBC (Table 4, 12% bracket) = 1,240 + 12% × (23,900 − 12,400) = 1,240 + 1,380 = **2,620.00**.
- EITC = 0 (§32(d)(1); (d)(2)(B)(ii) fails with no qualifying child). CTC = 0 (no qualifying child, §24(a); no other dependent, §24(h)(4)).
- Liability = **2,620.00**.
- FICA = 2,480.00 + 580.00 = **3,060.00**. AddMed = 0 (wages at or below 125,000).

### 2. mfs-wages-150000: MFS

- AGI = 150,000. SD = 16,100. TI = 133,900.
- TBC (24% bracket) = 17,966 + 24% × (133,900 − 105,700) = 17,966 + 6,768 = **24,734.00**.
- EITC = 0, CTC = 0, AMT = 0. Liability = **24,734.00**.
- FICA = 9,300.00 + 2,175.00 = **11,475.00**. AddMed = 0.9% × (150,000 − 125,000) = **225.00** (§3101(b)(2)(B)).

### 3. mfs-wages-250000: MFS

- AGI = 250,000. SD = 16,100. TI = 233,900.
- TBC (32% bracket) = 41,024 + 32% × (233,900 − 201,775) = 41,024 + 10,280 = **51,304.00**.
- EITC = 0, CTC = 0, AMT = 0. Liability = **51,304.00**.
- FICA: OASDI = 6.2% × 184,500 = 11,439.00 (§3121(a)(1) cap). HI = 3,625.00. Total **15,064.00**.
- AddMed = 0.9% × 125,000 = **1,125.00**.

### 4. mfs-wages-450000: MFS

- AGI = 450,000. SD = 16,100. TI = 433,900.
- TBC (37% bracket, which starts at $384,350 for MFS) = 103,291.75 + 37% × (433,900 − 384,350) = 103,291.75 + 18,333.50 = **121,625.25**.
- EITC = 0, CTC = 0, AMT = 0. Liability = **121,625.25**.
- FICA = 11,439.00 + 6,525.00 = **17,964.00**. AddMed = 0.9% × 325,000 = **2,925.00**.

### 5. mfs-wages-750000: MFS

- AGI = 750,000. SD = 16,100. TI = 733,900.
- TBC = 103,291.75 + 37% × (733,900 − 384,350) = 103,291.75 + 129,333.50 = **232,625.25**.
- EITC = 0, CTC = 0, AMT = 0. Liability = **232,625.25**.
- FICA = 11,439.00 + 10,875.00 = **22,314.00**. AddMed = 0.9% × 625,000 = **5,625.00**.

### 6. mfs-child-wages-15000: head of household under §2(b) via §2(c) and §7703(b)

- AGI = 15,000. SD = 24,150 (HoH). TI = max(0, 15,000 − 24,150) = 0. TBC = **0.00**.
- **EITC** (§32(a); X §15.5), 1 child, allowed through §32(d)(2)(B):
  - Credit = 34% × min(15,000, 13,020) = 4,426.80.
  - Limitation = 34% × 13,020 − 15.98% × max(0, 15,000 − 23,890) = 4,426.80 − 0 = 4,426.80.
  - EITC = **4,426.80**.
- **CTC** (§24; X §9, §15.3, §15.4):
  - Credit before limits = 2,200. There is no phase-out: AGI 15,000 is at most the §24(h)(3) $200,000 threshold.
  - §26(a) limit = regular tax 0 + AMT 0 = 0, so the credit allowed without subsection (d) is 0.
  - (d)(1)(A) = 2,200, capped per child by (h)(5) and (i)(1) at 1,700 (Rev. Proc. 2025-32 §4.05(2)), so 1,700.
  - (d)(1)(B): raising the §26(a) limit by 15% × (15,000 − 2,500) = 1,875 (with the (h)(6) $2,500 floor) raises allowed credits from 0 to min(2,200, 1,875) = 1,875. So (B) = 1,875.
  - Refundable = min(1,700, 1,875) = **1,700.00**.
  - Nonrefundable: (2,200 − 1,700) limited by §26(a) to 0 = **0.00**. CTC total = **1,700.00**.
- Liability = 0 − 0 − 1,700.00 − 4,426.80 = **−6,126.80**.
- FICA = 930.00 + 217.50 = **1,147.50**. AddMed = 0.

### 7. mfs-child-wages-45000: head of household under §2(b) via §2(c) and §7703(b)

- AGI = 45,000. SD = 24,150. TI = 20,850.
- TBC (Table 2, 12% bracket) = 1,770 + 12% × (20,850 − 17,700) = 1,770 + 378 = **2,148.00**.
- **EITC**:
  - Credit = 34% × 13,020 = 4,426.80.
  - Limitation = 4,426.80 − 15.98% × (45,000 − 23,890) = 4,426.80 − 15.98% × 21,110 = 4,426.80 − 3,373.378 = 1,053.422.
  - EITC = **1,053.42**.
- **CTC**:
  - §26(a) limit = 2,148, so the credit allowed without (d) = min(2,200, 2,148) = 2,148.
  - (d)(1)(B): raising the limit by 15% × (45,000 − 2,500) = 6,375 raises allowed credits to min(2,200, 8,523) = 2,200, so (B) = 52.
  - (d)(1)(A) = 1,700. Refundable = min(1,700, 52) = **52.00**.
  - Nonrefundable: (2,200 − 52) = 2,148, which is within the §26(a) limit of 2,148, so **2,148.00**. CTC total = **2,200.00**.
- Liability = 2,148.00 − 2,148.00 − 52.00 − 1,053.42 = **−1,105.42**.
- FICA = 2,790.00 + 652.50 = **3,442.50**. AddMed = 0.

### 8. mfs-ss-cohabiting-wages-20000-ss-24000: MFS, age 70, lived with spouse

- **§86**, with base = adjusted base = 0 under (c)(1)(C) and (c)(2)(C):
  - MAGI (without regard to §86) = 20,000. (b)(1)(A) sum = 20,000 + ½ × 24,000 = 32,000, which exceeds the base of 0.
  - (a)(1) = lesser of ½ × 24,000 = 12,000 and ½ × (32,000 − 0) = 16,000, so 12,000.
  - (a)(2) applies because 32,000 exceeds the adjusted base of 0. It is the lesser of (A) 85% × (32,000 − 0) + lesser(12,000, ½ × (0 − 0)) = 27,200 + 0 = 27,200 and (B) 85% × 24,000 = 20,400.
  - Taxable SS = **20,400**.
- AGI = 20,000 + 20,400 = **40,400**.
- SD = 16,100 + 1,650 (aged, married) = **17,750**. Senior deduction = **0** (§151(d)(5)(C)(v)).
- TI = 40,400 − 17,750 = 22,650.
- TBC = 1,240 + 12% × (22,650 − 12,400) = 1,240 + 1,230 = **2,470.00**.
- EITC = 0, CTC = 0. Liability = **2,470.00**.
- FICA = 1,240.00 + 290.00 = **1,530.00**. AddMed = 0.

### 9. mfs-ss-cohabiting-ss-30000: MFS, age 70, lived with spouse, no wages

- **§86**, base = adjusted base = 0:
  - (b)(1)(A) sum = 0 + 15,000 = 15,000.
  - (a)(1) = lesser of 15,000 and ½ × 15,000 = 7,500, so 7,500.
  - (a)(2) = lesser of 85% × 15,000 + lesser(7,500, 0) = 12,750 and 85% × 30,000 = 25,500.
  - Taxable SS = **12,750**.
- AGI = **12,750**. SD = **17,750**. Senior deduction = 0. TI = 0. TBC = **0.00**.
- EITC = 0 (no earned income; §32(d)(1)). CTC = 0. Liability = **0.00**.
- FICA = **0.00**. AddMed = 0.

### 10. mfs-ss-lived-apart-wages-20000-ss-24000: MFS, age 70, lived apart all year, no child

- **§86**: (c)(1)(C)(ii) is not met, so the base is $25,000 and the adjusted base $34,000.
  - (b)(1)(A) sum = 20,000 + 12,000 = 32,000, which exceeds 25,000 by 7,000.
  - (a)(1) = lesser of 12,000 and ½ × 7,000 = 3,500, so 3,500.
  - 32,000 does not exceed 34,000, so (a)(2) does not apply. Taxable SS = **3,500**.
- AGI = **23,500**.
- SD = 16,100 + 1,650 = **17,750**. The filer is still married under §7703, because §7703(b) needs a child, so the $2,050 unmarried amount is unavailable.
- Senior deduction = **0** (§151(d)(5)(C)(v)).
- TI = 5,750. TBC = 10% × 5,750 = **575.00**.
- EITC = 0, CTC = 0. Liability = **575.00**.
- FICA = **1,530.00**. AddMed = 0.

### 11-13. mfs-eitc-wages-6000 / 11000 / 16000: MFS, age 30, shared home

- AGI = 6,000 / 11,000 / 16,000. SD = 16,100. TI = 0 in all three, because each AGI is below 16,100. TBC = **0.00**.
- **EITC = 0.00** in all three. §32(d)(1): "In the case of an individual who is married, this section shall apply only if a joint return is filed". Marital status comes from §7703(a) under (d)(2)(A), and the filer is married. The (d)(2)(B) exception needs the filer to reside "with a qualifying child of the individual for more than one-half of such taxable year" under (ii). There is no child, so the exception fails.
- CTC = 0. Liability = **0.00**.
- FICA: 6,000 → 372.00 + 87.00 = **459.00**; 11,000 → 682.00 + 159.50 = **841.50**; 16,000 → 992.00 + 232.00 = **1,224.00**. AddMed = 0.

## Summary (statutory result)

| Case | Status | AGI | SD | TI | TBC | EITC | CTC nonref + ref | Liability | Employee FICA | AddMed |
|---|---|---|---|---|---|---|---|---|---|---|
| mfs-wages-40000 | MFS | 40,000 | 16,100 | 23,900 | 2,620.00 | 0 | 0 + 0 | 2,620.00 | 3,060.00 | 0 |
| mfs-wages-150000 | MFS | 150,000 | 16,100 | 133,900 | 24,734.00 | 0 | 0 + 0 | 24,734.00 | 11,475.00 | 225.00 |
| mfs-wages-250000 | MFS | 250,000 | 16,100 | 233,900 | 51,304.00 | 0 | 0 + 0 | 51,304.00 | 15,064.00 | 1,125.00 |
| mfs-wages-450000 | MFS | 450,000 | 16,100 | 433,900 | 121,625.25 | 0 | 0 + 0 | 121,625.25 | 17,964.00 | 2,925.00 |
| mfs-wages-750000 | MFS | 750,000 | 16,100 | 733,900 | 232,625.25 | 0 | 0 + 0 | 232,625.25 | 22,314.00 | 5,625.00 |
| mfs-child-wages-15000 | **HoH** | 15,000 | 24,150 | 0 | 0.00 | 4,426.80 | 0 + 1,700 | −6,126.80 | 1,147.50 | 0 |
| mfs-child-wages-45000 | **HoH** | 45,000 | 24,150 | 20,850 | 2,148.00 | 1,053.42 | 2,148 + 52 | −1,105.42 | 3,442.50 | 0 |
| mfs-ss-cohabiting-wages-20000-ss-24000 | MFS | 40,400 (SS 20,400) | 17,750 | 22,650 | 2,470.00 | 0 | 0 + 0 | 2,470.00 | 1,530.00 | 0 |
| mfs-ss-cohabiting-ss-30000 | MFS | 12,750 (SS 12,750) | 17,750 | 0 | 0.00 | 0 | 0 + 0 | 0.00 | 0.00 | 0 |
| mfs-ss-lived-apart-wages-20000-ss-24000 | MFS | 23,500 (SS 3,500) | 17,750 | 5,750 | 575.00 | 0 | 0 + 0 | 575.00 | 1,530.00 | 0 |
| mfs-eitc-wages-6000 | MFS | 6,000 | 16,100 | 0 | 0.00 | 0 | 0 + 0 | 0.00 | 459.00 | 0 |
| mfs-eitc-wages-11000 | MFS | 11,000 | 16,100 | 0 | 0.00 | 0 | 0 + 0 | 0.00 | 841.50 | 0 |
| mfs-eitc-wages-16000 | MFS | 16,000 | 16,100 | 0 | 0.00 | 0 | 0 + 0 | 0.00 | 1,224.00 | 0 |

The senior deduction is 0 in every case. AMT is 0 in every case.

## Deviation signatures (counterfactuals, not the law)

These are the values an engine would produce if it made one specific error. They are listed only so that a residue can be matched to its cause. They are not statutory results.

| Case | If the engine... | It would show |
|---|---|---|
| mfs-wages-450000 / 750000 | used the single table (Table 3) instead of Table 4 | TBC 120,634.25 / 227,500.25 (−991.00 / −5,125.00) |
| mfs-wages-150000 ... 750000 | used the $200,000 AddMed threshold, not $125,000 | AddMed 0 / 450 / 2,250 / 4,950 (−225 / −675 / −675 / −675) |
| mfs-child-wages-45000 | kept MFS instead of HoH | SD 16,100, TI 28,900, TBC 3,220.00, CTC 2,200 nonref + 0 ref, EITC 1,053.42, liability −33.42 |
| mfs-child-wages-15000 | kept MFS instead of HoH | TI 0 either way; liability unchanged at −6,126.80 (only SD and status differ) |
| mfs-child-wages-15000 / 45000 | applied §32(d)(1) without the (d)(2)(B) exception | EITC 0; liability −1,700.00 / −52.00 |
| mfs-child-wages-15000 / 45000 | used the Rev. Proc.'s printed maximum credit, $4,427, instead of 34% × 13,020 | EITC 4,427.00 / 1,053.62; liability −6,127.00 / −1,105.62 |
| mfs-ss-cohabiting-wages-20000-ss-24000 | used the $25,000 / $34,000 base | taxable SS 3,500, AGI 23,500, TI 5,750, TBC 575.00 |
| mfs-ss-cohabiting-ss-30000 | used the $25,000 / $34,000 base | taxable SS 0, AGI 0 |
| mfs-ss-lived-apart-wages-20000-ss-24000 | used the zero base (cohabiting rule) | taxable SS 20,400, AGI 40,400, TI 22,650, TBC 2,470.00 |
| mfs-ss-* | used the $2,050 unmarried aged amount | SD 18,150; TBC 2,422.00 (cohabiting-wages) / 535.00 (lived-apart) / 0 (SS-only) |
| mfs-ss-* | allowed the $6,000 senior deduction | TI 16,650 → TBC 1,750.00 (cohabiting-wages); 0 (lived-apart); 0 (SS-only) |
| mfs-eitc-wages-6000 / 11000 / 16000 | ignored §32(d) | EITC 459.00 / 653.31 / 270.81 (with the printed $664 maximum: 459.00 / 653.29 / 270.79); liability equals minus the EITC |

A note on comparing with TAXSIM (engine documentation, X §12, not law): TAXSIM's `fiitax` is documented as including the Additional Medicare Tax. The comparable statutory figure is therefore liability + AddMed. `tfica` is documented as the employee share of FICA, and the page says `fica` includes Additional Medicare Tax, so whether `tfica` includes it is not stated. The taxsimtest page documents law only "through December 2024" (X §12).

## Uncertainties and limits

- **U1 (§3 tax tables).** §3(a) imposes the tax-table tax "in lieu of the tax imposed by section 1" on non-itemizers whose taxable income does not exceed a ceiling amount "(not less than $20,000)" set by the Secretary (X §15.2).
  - For TI 5,750 (lived-apart SS), and possibly 20,850 (HoH 45k), 22,650 (cohabiting SS with wages), and 23,900 (mfs-wages-40000), the legally operative tax is therefore the Secretary's 2026 table amount, not the rate-schedule amount reported here.
  - Neither the 2026 tables nor the 2026 ceiling amount is in the extracts, so the table amounts were not computed. They may differ from the reported TBC by a few dollars.
  - The rate-schedule figures are reported as the task directs.
- **U2 (EITC rounding and EIC table).**
  - §32(a)(2)(A) gives a maximum of 34% × 13,020 = 4,426.80. Rev. Proc. 2025-32 §4.06 prints $4,427. §32(j)(2) rounds only the §32(b)(2) amounts (to $10), so the statutory formula value is reported.
  - The Rev. Proc. also points to "tables showing the amount of the earned income credit" in the Form 1040 instructions. Those tables are not extracted, and the 2026 table was not available.
  - EITC values under the printed $4,427 maximum are listed in the signatures table.
- **U3 (the spouse's own amounts).** A2 assumes no §63(f)(1)(B) or (2)(B) additional amount for the spouse. On a separate return that amount needs a §151(b) exemption to be allowable for the spouse, which requires the spouse to have no gross income. The spouse's age and income are not given.
- **U4 (§7703(b) scope).** X §14 flag 1 leaves open whether a bare reference to "section 7703" reaches §7703(b). It does not change any result here:
  - In groups 1, 3 and 4 there is no child, so §7703(b) cannot apply under any reading.
  - In group 2, HoH status rests on §2(c), which names §7703(b) expressly, and the EITC rests on §32(d)(2)(B).
  - The provisions that use a bare reference are §63(f)(3) and §63(g), §151(d)(5)(C)(v), §3101(b)(2)(B), §55, and §24(b)(2). For the group 2 filer (age 35, wages under $125,000, AGI far below every threshold) each of them gives the same number under either reading.
- **U5 (qualifying-child details).** The child cases rely on A4. §152(c)(2)-(4), §152(e), and §32(c)(3)(B)-(D) are only partly extracted. The task states that the child is a qualifying child who lived with the filer all year.
- **U6 (AMT).** AMT = 0 depends on AMTI = AGI. That holds if no §56-§58 item other than the §56(b)(1)(D) standard-deduction add-back applies to wages or Social Security, and the rest of §56-§58 is not extracted. The margins are at least $3,377 (mfs-wages-250000). The mfs-wages-750000 result holds under both readings of the §55(d)(4)(A)(ii)(IV) "50 percent" substitution.
- **U7 (FICA scope).** OASDI is capped per employer per calendar year (§3121(a)(1)), and a single employer is assumed (A1). The Additional Medicare Tax is computed at the statutory §3101(b)(2)(B) $125,000 threshold. The withholding threshold that applies to employers is not extracted, so how the tax splits between withholding and the return is not addressed. The total liability is the statutory figure.
- **U8 (other OBBBA deductions not extracted).** Deductions for qualified tips, overtime, and car-loan interest are not in the extracts. A1 assumes none of those items exist, so no such deduction is taken.
- **U9 (Rev. Proc. version).** All 2026 amounts come from the Oct. 17, 2025 drop version of Rev. Proc. 2025-32, which IRB 2025-45 matches (X §11, §11.7). The Oct. 9 versions printed $17,996 as the MFS 24% base tax (X §11.6). That figure would change mfs-wages-150000's TBC to 24,764.00. $17,966 is the operative figure, and the arithmetic cross-check in X §13 confirms it.
- **U10 (Colorado).** Only federal amounts are computed. Colorado residence has no effect on any federal figure above.

## Addendum (2026-09-27): state income tax as an itemized deduction

The cases are Colorado residents, so the state income tax they pay is a potential §164 itemized deduction. This computation assumed that neither spouse itemizes. The assumption holds wherever the §164(b)(6)-(7) limitation keeps state and local taxes at or below the standard deduction. The one case where an engine disagreed is mfs-wages-450000, and extract §16 settles it independently of the Colorado tax amount:
- MAGI of 450,000 exceeds half the 2026 threshold (505,000 / 2 = 252,500) by 197,500.
- 40,400 - 0.30 × 197,500 is negative, so the (b)(7)(B)(iii) floor of 10,000 applies.
- A separate filer takes half of that, 5,000.

Whatever the Colorado tax, the deductible amount is at most 5,000, which is below the 16,100 standard deduction. The standard deduction therefore applies and the §1 results above stand. The same holds at 750,000 of MAGI.
