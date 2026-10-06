# MFS adjudication: verbatim statutory and IRS extracts

Retrieved 2026-09-24. Every quoted passage below was extracted mechanically and copied into this file by `build.py`, not retyped:

- US Code: `curl` of the uscode.house.gov section page, then `strip_usc.py` / `strip_usc_tables.py` / `strip_notes.py` (regex tag strip plus `html.unescape`). Statute indentation is dropped; the (A)/(i)/(I) enumerators carry the structure.
- IRS Rev. Proc. 2025-32 and IRB 2025-45: `curl` of the irs.gov PDF, then `pdftotext -layout`. Quoted inside code fences to keep the column layout.
- SSA Federal Register notice: `curl` of the govinfo.gov PDF, then `pdftotext` in reading order, because the three-column layout interleaves under `-layout`.
- ssa.gov contribution and benefit base page: ssa.gov's CDN returns `HTTP 403 Access Denied` to curl, so the page text was read from an in-app browser (`document.body.innerText` / page text).
- TAXSIM: `curl` of https://taxsim.nber.org/taxsimtest/, with the raw HTML quoted in code fences and a tag-stripped copy in `raw/taxsimtest.txt`.

Raw sources and intermediate text are in `raw/`, with hashes in `SHA256SUMS.txt`, next to this file.

Verbatim check: `verify_quotes.py` confirms that every blockquoted line in this file appears verbatim, after whitespace normalization, in a file under `raw/`. The last run checked 838 lines and found 0 missing. The only text added inside quotes is the markdown `|---|` table-separator rows.

Rules followed: each quote carries its document, currency, heading, URL, and the filers it applies to. Engine documentation (TAXSIM) is recorded as a description of the engine's inputs and outputs. It is not evidence of what the law requires. Arithmetic cross-checks are in a separate labeled section and are not quotes.

## 0. US Code currency (release point)

- **Document:** uscode.house.gov, *Download the United States Code* page
- **Currency / version:** fetched 2026-09-24
- **Heading the quote sits under:** Current Release Point
- **URL:** https://uscode.house.gov/download/download.shtml
- **Applies to:** All titles, including Title 26 (listed as current through 119-111)
- **Extraction:** `curl`, then tags stripped (`raw/download.txt`)

> Current Release Point Public Law 119-111 (09/18/2026) Each update of the United States Code is a release point. This page provides downloadable files for the current release point. All files are current through Public Law 119-111 (09/18/2026). Titles in bold have been changed since the last release point.

Each section page fetched below carries the same machine marker in an HTML comment. For example, raw/s86.html has `<!-- documentid:26_86  usckey:260000000008600000000000000000000 currentthrough:20260918_119-111 documentPDFPage:-1 -->`. The marker was checked on all 11 section pages fetched: 1, 2, 24, 32, 63, 86, 151, 152, 3101, 3121, and 7703.

## 1. 26 USC 1: tax imposed, MFS rate table (1(d), 1(f)(7)-(8), 1(j))

### 1.1 §1(c) and §1(d): who the unmarried and MFS tables apply to

- **Document:** 26 U.S.C. §1
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §1. Tax imposed → (c) Unmarried individuals (other than surviving spouses and heads of households); (d) Married individuals filing separate returns
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1&num=0&edition=prelim
- **Applies to:** (c): individuals who are not married under §7703, not a surviving spouse, and not a head of household. (d): every married individual under §7703 who does not file a joint return
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (c) Unmarried individuals (other than surviving spouses and heads of households)
>
> There is hereby imposed on the taxable income of every individual (other than a surviving spouse as defined in section 2(a) or the head of a household as defined in section 2(b)) who is not a married individual (as defined in section 7703) a tax determined in accordance with the following table:
>
> (d) Married individuals filing separate returns
>
> There is hereby imposed on the taxable income of every married individual (as defined in section 7703) who does not make a single return jointly with his spouse under section 6013, a tax determined in accordance with the following table:

Note: the uscode page gives the original (c)/(d) dollar tables as HTML tables, which `strip_usc.py` skips. §1(j)(2) displaces them, as shown in 1.3.

### 1.2 §1(f)(7) and §1(f)(8): rounding and the ½-of-joint rule for MFS

- **Document:** 26 U.S.C. §1(f)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §1 → (f) Phaseout of marriage penalty in 15-percent bracket; adjustments in tax tables so that inflation will not result in tax increases → (7) Rounding; (8) Elimination of marriage penalty in 15-percent bracket
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1&num=0&edition=prelim
- **Applies to:** (7)(B): married individuals filing separate returns ($25 rounding). (8)(B): the MFS table. §1(j)(3)(B)(iii) switches (8) off for years after 2018 (see 1.4)
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (7) Rounding
>
> (A) In general
>
> If any increase determined under paragraph (2)(A), section 63(c)(4), section 68(b)(2) 1 or section 151(d)(4) is not a multiple of $50, such increase shall be rounded to the next lowest multiple of $50.
>
> (B) Table for married individuals filing separately
>
> In the case of a married individual filing a separate return, subparagraph (A) (other than with respect to sections 63(c)(4) and 151(d)(4)(A)) shall be applied by substituting "$25" for "$50" each place it appears.
>
> (8) Elimination of marriage penalty in 15-percent bracket
>
> With respect to taxable years beginning after December 31, 2003, in prescribing the tables under paragraph (1)-
>
> (A) the maximum taxable income in the 15-percent rate bracket in the table contained in subsection (a) (and the minimum taxable income in the next higher taxable income bracket in such table) shall be 200 percent of the maximum taxable income in the 15-percent rate bracket in the table contained in subsection (c) (after any other adjustment under this subsection), and
>
> (B) the comparable taxable income amounts in the table contained in subsection (d) shall be ½ of the amounts determined under subparagraph (A).

Extraction artifact: the `1` after 'section 68(b)(2)' in (7)(A) is the uscode page's footnote marker. Footnote 1 on the page: 'See References in Text note below'. The References in Text note says §68(b)(2) was omitted when Pub. L. 119-21 §70111(a) rewrote §68. The same marker appears after 'section 68(b),' in §151(d)(3).

### 1.3 §1(j)(1)-(2): TCJA rate tables made permanent, with the (A) joint, (B) HoH, (C) unmarried, and (D) MFS tables

- **Document:** 26 U.S.C. §1(j)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §1 → (j) Modifications for taxable years beginning after 2017 → (1) In general; (2) Rate tables → (A)-(D)
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1&num=0&edition=prelim
- **Applies to:** (A) joint returns and surviving spouses; (B) heads of household; (C) unmarried individuals; (D) married individuals filing separate returns
- **Extraction:** `strip_usc_tables.py` (same, plus `<tr>` rows emitted as `| cell | cell |`; the markdown `|---|` separator row is the only added text)

> (j) Modifications for taxable years beginning after 2017
>
> (1) In general
>
> In the case of a taxable year beginning after December 31, 2017-
>
> (A) subsection (i) shall not apply, and
>
> (B) this section (other than subsection (i)) shall be applied as provided in paragraphs (2) through (6).

> (2) Rate tables
>
> (A) Married individuals filing joint returns and surviving spouses
>
> The following table shall be applied in lieu of the table contained in subsection (a):
>
> | If taxable income is: | The tax is: |
> |---|---|
> | Not over $19,050 | 10% of taxable income. |
> | Over $19,050 but not over $77,400 | $1,905, plus 12% of the excess over $19,050. |
> | Over $77,400 but not over $165,000 | $8,907, plus 22% of the excess over $77,400. |
> | Over $165,000 but not over $315,000 | $28,179, plus 24% of the excess over $165,000. |
> | Over $315,000 but not over $400,000 | $64,179, plus 32% of the excess over $315,000. |
> | Over $400,000 but not over $600,000 | $91,379, plus 35% of the excess over $400,000. |
> | Over $600,000 | $161,379, plus 37% of the excess over $600,000. |
>
> (B) Heads of households
>
> The following table shall be applied in lieu of the table contained in subsection (b):
>
> | If taxable income is: | The tax is: |
> |---|---|
> | Not over $13,600 | 10% of taxable income. |
> | Over $13,600 but not over $51,800 | $1,360, plus 12% of the excess over $13,600. |
> | Over $51,800 but not over $82,500 | $5,944, plus 22% of the excess over $51,800. |
> | Over $82,500 but not over $157,500 | $12,698, plus 24% of the excess over $82,500. |
> | Over $157,500 but not over $200,000 | $30,698, plus 32% of the excess over $157,500. |
> | Over $200,000 but not over $500,000 | $44,298, plus 35% of the excess over $200,000. |
> | Over $500,000 | $149,298, plus 37% of the excess over $500,000. |
>
> (C) Unmarried individuals other than surviving spouses and heads of households
>
> The following table shall be applied in lieu of the table contained in subsection (c):
>
> | If taxable income is: | The tax is: |
> |---|---|
> | Not over $9,525 | 10% of taxable income. |
> | Over $9,525 but not over $38,700 | $952.50, plus 12% of the excess over $9,525. |
> | Over $38,700 but not over $82,500 | $4,453.50, plus 22% of the excess over $38,700. |
> | Over $82,500 but not over $157,500 | $14,089.50, plus 24% of the excess over $82,500. |
> | Over $157,500 but not over $200,000 | $32,089.50, plus 32% of the excess over $157,500. |
> | Over $200,000 but not over $500,000 | $45,689.50, plus 35% of the excess over $200,000. |
> | Over $500,000 | $150,689.50, plus 37% of the excess over $500,000. |
>
> (D) Married individuals filing separate returns
>
> The following table shall be applied in lieu of the table contained in subsection (d):
>
> | If taxable income is: | The tax is: |
> |---|---|
> | Not over $9,525 | 10% of taxable income. |
> | Over $9,525 but not over $38,700 | $952.50, plus 12% of the excess over $9,525. |
> | Over $38,700 but not over $82,500 | $4,453.50, plus 22% of the excess over $38,700. |
> | Over $82,500 but not over $157,500 | $14,089.50, plus 24% of the excess over $82,500. |
> | Over $157,500 but not over $200,000 | $32,089.50, plus 32% of the excess over $157,500. |
> | Over $200,000 but not over $300,000 | $45,689.50, plus 35% of the excess over $200,000. |
> | Over $300,000 | $80,689.50, plus 37% of the excess over $300,000. |

### 1.4 §1(j)(3): annual adjustment of the (j)(2) tables

- **Document:** 26 U.S.C. §1(j)(3)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §1 → (j) → (3) Adjustments → (A) No adjustment in 2018; (B) Subsequent years
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1&num=0&edition=prelim
- **Applies to:** All §1(j)(2) tables. Clause (ii) extends the MFS $25 rounding of (f)(7)(B) to unmarried filers. Clause (iii) switches off the (f)(8) ½-of-joint rule
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (3) Adjustments
>
> (A) No adjustment in 2018
>
> The tables contained in paragraph (2) shall apply without adjustment for taxable years beginning after December 31, 2017, and before January 1, 2019.
>
> (B) Subsequent years
>
> For taxable years beginning after December 31, 2018, the Secretary shall prescribe tables which shall apply in lieu of the tables contained in paragraph (2) in the same manner as under paragraphs (1) and (2) of subsection (f) (applied without regard to clauses (i) and (ii) of subsection (f)(2)(A)), except that in prescribing such tables-
>
> (i) solely for purposes of determining the dollar amounts at which any rate bracket higher than 12 percent ends and at which any rate bracket higher than 22 percent begins, subsection (f)(3) shall be applied by substituting "calendar year 2017" for "calendar year 2016" in subparagraph (A)(ii) thereof,
>
> (ii) subsection (f)(7)(B) shall apply to any unmarried individual other than a surviving spouse or head of household, and
>
> (iii) subsection (f)(8) shall not apply.

### 1.5 §1(j)(5)(B): capital-gains breakpoints, including the MFS ½ rule

- **Document:** 26 U.S.C. §1(j)(5)(B)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §1 → (j) → (5) Application of current income tax brackets to capital gains brackets → (B) Maximum amounts defined
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1&num=0&edition=prelim
- **Applies to:** (i)(III) any other individual, including MFS, gets ½ of the joint zero-rate amount. (ii)(I) MFS gets ½ of the joint 15-percent amount
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (B) Maximum amounts defined
>
> For purposes of applying section 1(h) with the modifications described in subparagraph (A)-
>
> (i) Maximum zero rate amount
>
> The maximum zero rate amount shall be-
>
> (I) in the case of a joint return or surviving spouse, $77,200,
>
> (II) in the case of an individual who is a head of household (as defined in section 2(b)), $51,700,
>
> (III) in the case of any other individual (other than an estate or trust), an amount equal to ½ of the amount in effect for the taxable year under subclause (I), and
>
> (IV) in the case of an estate or trust, $2,600.
>
> (ii) Maximum 15-percent rate amount
>
> The maximum 15-percent rate amount shall be-
>
> (I) in the case of a joint return or surviving spouse, $479,000 (½ such amount in the case of a married individual filing a separate return),
>
> (II) in the case of an individual who is the head of a household (as defined in section 2(b)), $452,400,
>
> (III) in the case of any other individual (other than an estate or trust), $425,800, and
>
> (IV) in the case of an estate or trust, $12,700.

### 1.6 Editorial notes: OBBBA (Pub. L. 119-21) amendments to §1(j) and their effective date

- **Document:** 26 U.S.C. §1, Editorial Notes → Amendments; Statutory Notes → Effective Date of 2025 Amendment
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** Amendments → 2025; Effective Date of 2025 Amendment
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1&num=0&edition=prelim
- **Applies to:** §1(j) for taxable years beginning after Dec. 31, 2025
- **Extraction:** `strip_notes.py` (uscode HTML statute + editorial notes, tags stripped)

> 2025-Subsec. (j). Pub. L. 119–21, §70101(a)(2), substituted "beginning after 2017" for "2018 through 2025" in heading.
>
> Subsec. (j)(1). Pub. L. 119–21, §70101(a)(1), struck out ", and before January 1, 2026" after "December 31, 2017" in introductory provisions.
>
> Subsec. (j)(3)(B)(i). Pub. L. 119–21, §70101(b), inserted "solely for purposes of determining the dollar amounts at which any rate bracket higher than 12 percent ends and at which any rate bracket higher than 22 percent begins," before "subsection (f)(3)".

> Pub. L. 119–21, title VII, §70101(c), July 4, 2025, 139 Stat. 158 , provided that: "The amendments made by this section [amending this section] shall apply to taxable years beginning after December 31, 2025."

## 2. 26 USC 2(b) (head of household) and 2(c) (certain married individuals living apart)

- **Document:** 26 U.S.C. §2(b)-(c)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §2. Definitions and special rules → (b) Definition of head of household; (c) Certain married individuals living apart
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section2&num=0&edition=prelim
- **Applies to:** (b): individuals claiming head-of-household status. It requires the individual to be 'not married at the close of his taxable year'. (c): 'for purposes of this part'. That is Part I of subchapter A of chapter 1, which contains §§1 and 2 per the uscode itempaths `/260/Subtitle A/CHAPTER 1/Subchapter A/PART I/Sec. 1` and `.../PART I/Sec. 2`. An individual whom §7703(b) treats as not married is treated as not married at year end, which is how a qualifying married-living-apart filer reaches the §2(b) HoH definition and the §1 rate tables
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (b) Definition of head of household
>
> (1) In general
>
> For purposes of this subtitle, an individual shall be considered a head of a household if, and only if, such individual is not married at the close of his taxable year, is not a surviving spouse (as defined in subsection (a)), and either-
>
> (A) maintains as his home a household which constitutes for more than one-half of such taxable year the principal place of abode, as a member of such household, of-
>
> (i) a qualifying child of the individual (as defined in section 152(c), determined without regard to section 152(e)), but not if such child-
>
> (I) is married at the close of the taxpayer's taxable year, and
>
> (II) is not a dependent of such individual by reason of section 152(b)(2) or 152(b)(3), or both, or
>
> (ii) any other person who is a dependent of the taxpayer, if the taxpayer is entitled to a deduction for the taxable year for such person under section 151, or
>
> (B) maintains a household which constitutes for such taxable year the principal place of abode of the father or mother of the taxpayer, if the taxpayer is entitled to a deduction for the taxable year for such father or mother under section 151.
>
> For purposes of this paragraph, an individual shall be considered as maintaining a household only if over half of the cost of maintaining the household during the taxable year is furnished by such individual.
>
> (2) Determination of status
>
> For purposes of this subsection-
>
> (A) an individual who is legally separated from his spouse under a decree of divorce or of separate maintenance shall not be considered as married;
>
> (B) a taxpayer shall be considered as not married at the close of his taxable year if at any time during the taxable year his spouse is a nonresident alien; and
>
> (C) a taxpayer shall be considered as married at the close of his taxable year if his spouse (other than a spouse described in subparagraph (B)) died during the taxable year.
>
> (3) Limitations
>
> Notwithstanding paragraph (1), for purposes of this subtitle a taxpayer shall not be considered to be a head of a household-
>
> (A) if at any time during the taxable year he is a nonresident alien; or
>
> (B) by reason of an individual who would not be a dependent for the taxable year but for-
>
> (i) subparagraph (H) of section 152(d)(2), or
>
> (ii) paragraph (3) of section 152(d).
>
> (c) Certain married individuals living apart
>
> For purposes of this part, an individual shall be treated as not married at the close of the taxable year if such individual is so treated under the provisions of section 7703(b).

Scope note: §2(b)(1)(A)(i) points to §152(c) for the qualifying child. §2(b)(1)(A)(ii) covers 'any other person who is a dependent', which includes a §152(d) qualifying relative. §2(b)(3)(B) excludes a dependent who qualifies only through §152(d)(2)(H) (unrelated member of the household) or §152(d)(3) (multiple-support agreement). Section 10 below extracts §152(c)(1), (d)(1)-(3), and (f)(1)(A).

## 3. 26 USC 7703(a) and (b), in full

- **Document:** 26 U.S.C. §7703
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §7703. Determination of marital status → (a) General rule; (b) Certain married individuals living apart
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section7703&num=0&edition=prelim
- **Applies to:** (a): 'part V of subchapter B of chapter 1 and those provisions of this title which refer to this subsection'. (b): only 'those provisions of this title which refer to this subsection'
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (a) General rule
>
> For purposes of part V of subchapter B of chapter 1 and those provisions of this title which refer to this subsection-
>
> (1) the determination of whether an individual is married shall be made as of the close of his taxable year; except that if his spouse dies during his taxable year such determination shall be made as of the time of such death; and
>
> (2) an individual legally separated from his spouse under a decree of divorce or of separate maintenance shall not be considered as married.
>
> (b) Certain married individuals living apart
>
> For purposes of those provisions of this title which refer to this subsection, if-
>
> (1) an individual who is married (within the meaning of subsection (a)) and who files a separate return maintains as his home a household which constitutes for more than one-half of the taxable year the principal place of abode of a child (within the meaning of section 152(f)(1)) with respect to whom such individual is entitled to a deduction for the taxable year under section 151 (or would be so entitled but for section 152(e)),
>
> (2) such individual furnishes over one-half of the cost of maintaining such household during the taxable year, and
>
> (3) during the last 6 months of the taxable year, such individual's spouse is not a member of such household,
>
> such individual shall not be considered as married.

## 4. 26 USC 63: standard deduction (63(c)(2), (c)(6), (c)(7), (f), (g))

- **Document:** 26 U.S.C. §63(c)(1)-(7)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §63. Taxable income defined → (c) Standard deduction → (2) Basic standard deduction; (3); (4); (5); (6) Certain individuals, etc., not eligible for standard deduction; (7) Special rules for taxable years beginning after 2017
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section63&num=0&edition=prelim
- **Applies to:** (2)(C) 'any other case', which covers single filers and MFS filers. (6)(A): a married individual filing a separate return when either spouse itemizes. (7): the OBBBA base amounts ($15,750 for (2)(C))
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (c) Standard deduction
>
> For purposes of this subtitle-
>
> (1) In general
>
> Except as otherwise provided in this subsection, the term "standard deduction" means the sum of-
>
> (A) the basic standard deduction, and
>
> (B) the additional standard deduction.
>
> (2) Basic standard deduction
>
> For purposes of paragraph (1), the basic standard deduction is-
>
> (A) 200 percent of the dollar amount in effect under subparagraph (C) for the taxable year in the case of-
>
> (i) a joint return, or
>
> (ii) a surviving spouse (as defined in section 2(a)),
>
> (B) $4,400 in the case of a head of household (as defined in section 2(b)), or
>
> (C) $3,000 in any other case.
>
> (3) Additional standard deduction for aged and blind
>
> For purposes of paragraph (1), the additional standard deduction is the sum of each additional amount to which the taxpayer is entitled under subsection (f).
>
> (4) Adjustments for inflation
>
> In the case of any taxable year beginning in a calendar year after 1988, each dollar amount contained in paragraph (2)(B), (2)(C), or (5) or subsection (f) shall be increased by an amount equal to-
>
> (A) such dollar amount, multiplied by
>
> (B) the cost-of-living adjustment determined under section 1(f)(3) for the calendar year in which the taxable year begins, by substituting for "calendar year 2016" in subparagraph (A)(ii) thereof-
>
> (i) "calendar year 1987" in the case of the dollar amounts contained in paragraph (2)(B), (2)(C), or (5)(A) or subsection (f), and
>
> (ii) "calendar year 1997" in the case of the dollar amount contained in paragraph (5)(B).
>
> (5) Limitation on basic standard deduction in the case of certain dependents
>
> In the case of an individual with respect to whom a deduction under section 151 is allowable to another taxpayer for a taxable year beginning in the calendar year in which the individual's taxable year begins, the basic standard deduction applicable to such individual for such individual's taxable year shall not exceed the greater of-
>
> (A) $500, or
>
> (B) the sum of $250 and such individual's earned income.
>
> (6) Certain individuals, etc., not eligible for standard deduction
>
> In the case of-
>
> (A) a married individual filing a separate return where either spouse itemizes deductions,
>
> (B) a nonresident alien individual,
>
> (C) an individual making a return under section 443(a)(1) for a period of less than 12 months on account of a change in his annual accounting period, or
>
> (D) an estate or trust, common trust fund, or partnership,
>
> the standard deduction shall be zero.
>
> (7) Special rules for taxable years beginning after 2017
>
> In the case of a taxable year beginning after December 31, 2017-
>
> (A) Increase in standard deduction
>
> Paragraph (2) shall be applied-
>
> (i) by substituting "$23,625" for "$4,400" in subparagraph (B), and
>
> (ii) by substituting "$15,750" for "$3,000" in subparagraph (C).
>
> (B) Adjustment for inflation
>
> (i) In general
>
> Paragraph (4) shall not apply to the dollar amounts contained in paragraphs (2)(B) and (2)(C).
>
> (ii) Adjustment of increased amounts
>
> In the case of a taxable year beginning after 2025, the $23,625 and $15,750 amounts in subparagraph (A) shall each be increased by an amount equal to-
>
> (I) such dollar amount, multiplied by
>
> (II) the cost-of-living adjustment determined under section 1(f)(3) for the calendar year in which the taxable year begins, determined by substituting "2024" for "2016" in subparagraph (A)(ii) thereof.
>
> If any increase under this clause is not a multiple of $50, such increase shall be rounded to the next lowest multiple of $50.

- **Document:** 26 U.S.C. §63(f)-(g)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §63 → (f) Aged or blind additional amounts; (g) Marital status
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section63&num=0&edition=prelim
- **Applies to:** (f)(1)-(2): $600 base per aged/blind condition, for the taxpayer and for the spouse only if a §151(b) spousal exemption is allowable (see §151(b) in section 8). (f)(3): $750 base for an individual who 'is not married and is not a surviving spouse'. (g): marital status determined under §7703
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (f) Aged or blind additional amounts
>
> (1) Additional amounts for the aged
>
> The taxpayer shall be entitled to an additional amount of $600-
>
> (A) for himself if he has attained age 65 before the close of his taxable year, and
>
> (B) for the spouse of the taxpayer if the spouse has attained age 65 before the close of the taxable year and an additional exemption is allowable to the taxpayer for such spouse under section 151(b).
>
> (2) Additional amount for blind
>
> The taxpayer shall be entitled to an additional amount of $600-
>
> (A) for himself if he is blind at the close of the taxable year, and
>
> (B) for the spouse of the taxpayer if the spouse is blind as of the close of the taxable year and an additional exemption is allowable to the taxpayer for such spouse under section 151(b).
>
> For purposes of subparagraph (B), if the spouse dies during the taxable year the determination of whether such spouse is blind shall be made as of the time of such death.
>
> (3) Higher amount for certain unmarried individuals
>
> In the case of an individual who is not married and is not a surviving spouse, paragraphs (1) and (2) shall be applied by substituting "$750" for "$600".
>
> (4) Blindness defined
>
> For purposes of this subsection, an individual is blind only if his central visual acuity does not exceed 20/200 in the better eye with correcting lenses, or if his visual acuity is greater than 20/200 but is accompanied by a limitation in the fields of vision such that the widest diameter of the visual field subtends an angle no greater than 20 degrees.
>
> (g) Marital status
>
> For purposes of this section, marital status shall be determined under section 7703.

- **Document:** 26 U.S.C. §63, Editorial Notes → Amendments (2025) and Effective Date of 2025 Amendment
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** Amendments → 2025-Subsec. (c)(7)...
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section63&num=0&edition=prelim
- **Applies to:** §63(c)(7), taxable years beginning after Dec. 31, 2024
- **Extraction:** `strip_notes.py` (uscode HTML statute + editorial notes, tags stripped)

> Subsec. (c)(7). Pub. L. 119–21, §70102(a), substituted "beginning after 2017" for "2018 through 2025" in heading and struck out ", and before January 1, 2026" after "December 31, 2017" in introductory provisions.
>
> Subsec. (c)(7)(A)(i). Pub. L. 119–21, §70102(b)(1), substituted "$23,625" for "$18,000".
>
> Subsec. (c)(7)(A)(ii). Pub. L. 119–21, §70102(b)(2), substituted "$15,750" for "$12,000".
>
> Subsec. (c)(7)(B)(ii). Pub. L. 119–21, §70102(b)(1)–(3), substituted "2025" for "2018", "$23,625" for "$18,000", and "$15,750" for "$12,000" in introductory provisions.
>
> Subsec. (c)(7)(B)(ii)(II). Pub. L. 119–21, §70102(b)(4), substituted "2024" for "2017".

> Pub. L. 119–21, title VII, §70102(c), July 4, 2025, 139 Stat. 159 , provided that: "The amendments made by this section [amending this section] shall apply to taxable years beginning after December 31, 2024."

## 5. 26 USC 86: Social Security benefits (86(a)-(b) for context; 86(c)(1)-(2) in full)

- **Document:** 26 U.S.C. §86(a)-(c)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §86. Social security and tier 1 railroad retirement benefits → (a) In general; (b) Taxpayers to whom subsection (a) applies; (c) Base amount and adjusted base amount
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section86&num=0&edition=prelim
- **Applies to:** (c)(1)(A) and (c)(2)(A) ($25,000 / $34,000): every filer not covered by (B) or (C), for example single and HoH filers and MFS filers who lived apart from the spouse at all times during the year. (c)(1)(B) and (c)(2)(B): joint returns. (c)(1)(C) and (c)(2)(C): a married individual under §7703 who does not file jointly and did not live apart from the spouse at all times during the year (base and adjusted base both zero)
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (a) In general
>
> (1) In general
>
> Except as provided in paragraph (2), gross income for the taxable year of any taxpayer described in subsection (b) (notwithstanding section 207 of the Social Security Act) includes social security benefits in an amount equal to the lesser of-
>
> (A) one-half of the social security benefits received during the taxable year, or
>
> (B) one-half of the excess described in subsection (b)(1).
>
> (2) Additional amount
>
> In the case of a taxpayer with respect to whom the amount determined under subsection (b)(1)(A) exceeds the adjusted base amount, the amount included in gross income under this section shall be equal to the lesser of-
>
> (A) the sum of-
>
> (i) 85 percent of such excess, plus
>
> (ii) the lesser of the amount determined under paragraph (1) or an amount equal to one-half of the difference between the adjusted base amount and the base amount of the taxpayer, or
>
> (B) 85 percent of the social security benefits received during the taxable year.
>
> (b) Taxpayers to whom subsection (a) applies
>
> (1) In general
>
> A taxpayer is described in this subsection if-
>
> (A) the sum of-
>
> (i) the modified adjusted gross income of the taxpayer for the taxable year, plus
>
> (ii) one-half of the social security benefits received during the taxable year, exceeds
>
> (B) the base amount.
>
> (2) Modified adjusted gross income
>
> For purposes of this subsection, the term "modified adjusted gross income" means adjusted gross income-
>
> (A) determined without regard to this section and sections 85(c), 135, 137, 221, 911, 931, and 933, and
>
> (B) increased by the amount of interest received or accrued by the taxpayer during the taxable year which is exempt from tax.
>
> (c) Base amount and adjusted base amount
>
> For purposes of this section-
>
> (1) Base amount
>
> The term "base amount" means-
>
> (A) except as otherwise provided in this paragraph, $25,000,
>
> (B) $32,000 in the case of a joint return, and
>
> (C) zero in the case of a taxpayer who-
>
> (i) is married as of the close of the taxable year (within the meaning of section 7703) but does not file a joint return for such year, and
>
> (ii) does not live apart from his spouse at all times during the taxable year.
>
> (2) Adjusted base amount
>
> The term "adjusted base amount" means-
>
> (A) except as otherwise provided in this paragraph, $34,000,
>
> (B) $44,000 in the case of a joint return, and
>
> (C) zero in the case of a taxpayer described in paragraph (1)(C).

Full-section check: all of §86 (a)-(f) was extracted to `raw/s86.txt`. It contains no inflation-adjustment provision; searching the file for `inflation` and `cost-of-living` finds nothing.

## 6. 26 USC 32: EITC (32(b) tables, 32(c)(1)(A), 32(d) in full as amended by ARPA 2021)

- **Document:** 26 U.S.C. §32(b)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §32. Earned income → (b) Percentages and amounts → (1) Percentages; (2) Amounts → (A) In general; (B) Joint returns
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section32&num=0&edition=prelim
- **Applies to:** All eligible individuals; the (b)(2)(B) +$5,000 phaseout increase applies only to joint returns
- **Extraction:** `strip_usc_tables.py` (same, plus `<tr>` rows emitted as `| cell | cell |`; the markdown `|---|` separator row is the only added text)

> (b) Percentages and amounts
>
> For purposes of subsection (a)-
>
> (1) Percentages
>
> The credit percentage and the phaseout percentage shall be determined as follows:
>
> | In the case of an eligible individual with: | The credit percentage is: | The phaseout percentage is: |
> |---|---|---|
> | 1 qualifying child | 34 | 15.98 |
> | 2 qualifying children | 40 | 21.06 |
> | 3 or more qualifying children | 45 | 21.06 |
> | No qualifying children | 7.65 | 7.65 |
>
> (2) Amounts
>
> (A) In general
>
> Subject to subparagraph (B), the earned income amount and the phaseout amount shall be determined as follows:
>
> | In the case of an eligible individual with: | The earned income amount is: | The phaseout amount is: |
> |---|---|---|
> | 1 qualifying child | $6,330 | $11,610 |
> | 2 or more qualifying children | $8,890 | $11,610 |
> | No qualifying children | $4,220 | $5,280 |
>
> (B) Joint returns
>
> In the case of a joint return filed by an eligible individual and such individual's spouse, the phaseout amount determined under subparagraph (A) shall be increased by $5,000.

- **Document:** 26 U.S.C. §32(c)(1)(A)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §32 → (c) Definitions and special rules → (1) Eligible individual → (A) In general
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section32&num=0&edition=prelim
- **Applies to:** (ii): individuals with no qualifying child. The age test in (ii)(II) reads 'such individual (or, if the individual is married, either the individual or the individual's spouse) has attained age 25 but not attained age 65'
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (c) Definitions and special rules
>
> For purposes of this section-
>
> (1) Eligible individual
>
> (A) In general
>
> The term "eligible individual" means-
>
> (i) any individual who has a qualifying child for the taxable year, or
>
> (ii) any other individual who does not have a qualifying child for the taxable year, if-
>
> (I) such individual's principal place of abode is in the United States for more than one-half of such taxable year,
>
> (II) such individual (or, if the individual is married, either the individual or the individual's spouse) has attained age 25 but not attained age 65 before the close of the taxable year, and
>
> (III) such individual is not a dependent for whom a deduction is allowable under section 151 to another taxpayer for any taxable year beginning in the same calendar year as such taxable year.

- **Document:** 26 U.S.C. §32(d)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §32 → (d) Married individuals → (1) In general; (2) Determination of marital status → (A) In general; (B) Special rule for separated spouse
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section32&num=0&edition=prelim
- **Applies to:** Married individuals. The credit is allowed to a married individual only on a joint return, except that (d)(2)(B) treats a qualifying separated spouse as not married
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (d) Married individuals
>
> (1) In general
>
> In the case of an individual who is married, this section shall apply only if a joint return is filed for the taxable year under section 6013.
>
> (2) Determination of marital status
>
> For purposes of this section-
>
> (A) In general
>
> Except as provided in subparagraph (B), marital status shall be determined under section 7703(a).
>
> (B) Special rule for separated spouse
>
> An individual shall not be treated as married if such individual-
>
> (i) is married (as determined under section 7703(a)) and does not file a joint return for the taxable year,
>
> (ii) resides with a qualifying child of the individual for more than one-half of such taxable year, and
>
> (iii)(I) during the last 6 months of such taxable year, does not have the same principal place of abode as the individual's spouse, or
>
> (II) has a decree, instrument, or agreement (other than a decree of divorce) described in section 121(d)(3)(C) with respect to the individual's spouse and is not a member of the same household with the individual's spouse by the end of the taxable year.

- **Document:** 26 U.S.C. §32(n), introductory text only
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §32 → (n) Special rules for individuals without qualifying children
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section32&num=0&edition=prelim
- **Applies to:** Taxable years beginning after Dec. 31, 2020 and before Jan. 1, 2022 only. The 2021 ARPA childless-EITC expansion does not apply to 2026
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (n) Special rules for individuals without qualifying children
>
> In the case of any taxable year beginning after December 31, 2020, and before January 1, 2022-

- **Document:** 26 U.S.C. §32, Editorial Notes → Amendments (2021); Statutory Notes → Effective Date of 2021 Amendment
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** Amendments → 2021-Subsec. (c)(1)(A) ... Subsec. (d)(1)
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section32&num=0&edition=prelim
- **Applies to:** ARPA (Pub. L. 117-2) §9623, the separated-spouse rule
- **Extraction:** `strip_notes.py` (uscode HTML statute + editorial notes, tags stripped)

> 2021-Subsec. (c)(1)(A). Pub. L. 117–2, §9623(b)(1), struck out concluding provisions which read as follows: "For purposes of the preceding sentence, marital status shall be determined under section 7703."
>
> Subsec. (c)(1)(E)(ii). Pub. L. 117–2, §9623(b)(2), struck out "(within the meaning of section 7703)" after "is married".
>
> Subsec. (c)(1)(F). Pub. L. 117–2, §9622(a), struck out heading and text of subpar. (F). Text read as follows: "No credit shall be allowed under this section to any eligible individual who has one or more qualifying children if no qualifying child of such individual is taken into account under subsection (b) by reason of paragraph (3)(D)."
>
> Subsec. (d). Pub. L. 117–2, §9623(a), designated existing provisions as par. (1), inserted heading, and added par. (2).
>
> Subsec. (d)(1). Pub. L. 117–2, §9623(b)(3), struck out "(within the meaning of section 7703)" after "is married".

> Pub. L. 117–2, title IX, §9623(c), Mar. 11, 2021, 135 Stat. 154 , provided that: "The amendments made by this section [amending this section] shall apply to taxable years beginning after December 31, 2020."

Full-section check: no 119th-Congress law amends §32. A search of `raw/s32.full.txt` (statute plus all notes) for `Pub. L. 119–` finds no hits, and the section's source credit ends with Pub. L. 117-2 (Mar. 11, 2021).

## 7. 26 USC 3101(b)(2) (Additional Medicare Tax) and 3121(a)(1) (contribution and benefit base)

- **Document:** 26 U.S.C. §3101 (entire section, (a)-(c))
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §3101. Rate of tax → (a) Old-age, survivors, and disability insurance; (b) Hospital insurance → (1) In general; (2) Additional tax; (c)
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section3101&num=0&edition=prelim
- **Applies to:** (b)(2)(A): joint returns, $250,000. (b)(2)(B): a married taxpayer under §7703 filing a separate return, ½ of the (A) amount. (b)(2)(C): 'any other case', $200,000
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (a) Old-age, survivors, and disability insurance
>
> In addition to other taxes, there is hereby imposed on the income of every individual a tax equal to 6.2 percent of the wages (as defined in section 3121(a)) received by the individual with respect to employment (as defined in section 3121(b)).
>
> (b) Hospital insurance
>
> (1) In general
>
> In addition to the tax imposed by the preceding subsection, there is hereby imposed on the income of every individual a tax equal to 1.45 percent of the wages (as defined in section 3121(a)) received by him with respect to employment (as defined in section 3121(b)).
>
> (2) Additional tax
>
> In addition to the tax imposed by paragraph (1) and the preceding subsection, there is hereby imposed on every taxpayer (other than a corporation, estate, or trust) a tax equal to 0.9 percent of wages which are received with respect to employment (as defined in section 3121(b)) during any taxable year beginning after December 31, 2012, and which are in excess of-
>
> (A) in the case of a joint return, $250,000,
>
> (B) in the case of a married taxpayer (as defined in section 7703) filing a separate return, ½ of the dollar amount determined under subparagraph (A), and
>
> (C) in any other case, $200,000.
>
> (c) Relief from taxes in cases covered by certain international agreements
>
> During any period in which there is in effect an agreement entered into pursuant to section 233 of the Social Security Act with any foreign country, wages received by or paid to an individual shall be exempt from the taxes imposed by this section to the extent that such wages are subject under such agreement exclusively to the laws applicable to the social security system of such foreign country.

Full-section check: all of §3101 is quoted above. It contains no inflation adjustment of the $250,000 or $200,000 thresholds.

- **Document:** 26 U.S.C. §3121(a)(1)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §3121. Definitions → (a) Wages → (1)
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section3121&num=0&edition=prelim
- **Applies to:** Wages subject to the §3101(a) OASDI tax and the §3111(a) employer tax, per employer, per calendar year. The (b) HI tax is not capped by (a)(1)
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (a) Wages
>
> For purposes of this chapter, the term "wages" means all remuneration for employment, including the cash value of all remuneration (including benefits) paid in any medium other than cash; except that such term shall not include-
>
> (1) in the case of the taxes imposed by sections 3101(a) and 3111(a) that part of the remuneration which, after remuneration (other than remuneration referred to in the succeeding paragraphs of this subsection) equal to the contribution and benefit base (as determined under section 230 of the Social Security Act) with respect to employment has been paid to an individual by an employer during the calendar year with respect to which such contribution and benefit base is effective, is paid to such individual by such employer during such calendar year. If an employer (hereinafter referred to as successor employer) during any calendar year acquires substantially all the property used in a trade or business of another employer (hereinafter referred to as a predecessor), or used in a separate unit of a trade or business of a predecessor, and immediately after the acquisition employs in his trade or business an individual who immediately prior to the acquisition was employed in the trade or business of such predecessor, then, for the purpose of determining whether the successor employer has paid remuneration (other than remuneration referred to in the succeeding paragraphs of this subsection) with respect to employment equal to the contribution and benefit base (as determined under section 230 of the Social Security Act) to such individual during such calendar year, any remuneration (other than remuneration referred to in the succeeding paragraphs of this subsection) with respect to employment paid (or considered under this paragraph as having been paid) to such individual by such predecessor during such calendar year and prior to such acquisition shall be considered as having been paid by such successor employer;

### 7.1 SSA: the 2026 contribution and benefit base

- **Document:** SSA, *Cost-of-Living Increase and Other Determinations for 2026*, Federal Register Vol. 90, No. 210, Monday, November 3, 2025, Notices (FR Doc. 2025-19763)
- **Currency / version:** published 2025-11-03
- **Heading the quote sits under:** Summary list ('The national average wage index for 2024 is $69,846.57. This index affects the following amounts:') and the section 'OASDI Contribution and Benefit Base' → General; Computation; Amount
- **URL:** https://www.govinfo.gov/content/pkg/FR-2025-11-03/pdf/2025-19763.pdf (HTML: https://www.federalregister.gov/documents/2025/11/03/2025-19763/cost-of-living-increase-and-other-determinations-for-2026)
- **Applies to:** Remuneration paid in 2026 and self-employment income earned in taxable years beginning in 2026. This is the §3121(a)(1) OASDI wage cap
- **Extraction:** `pdftotext` in reading order (`raw/fr-2025-19763.flow.txt`). The PDF prints a running header, date stamp, and margin text inside the column. In the second excerpt, the lines 'lotter on DSK11XQN23PROD with NOTICES1', 'VerDate Sep<11>2014', '16:58 Oct 31, 2025', and 'Jkt 268001' are those print artifacts, not notice text

> ```text
> The national average wage index for
> 2024 is $69,846.57. This index affects
> the following amounts:
> (1) The Old-Age, Survivors, and
> Disability Insurance (OASDI)
> contribution and benefit base will be
> $184,500 for remuneration paid in 2026
> and self-employment income earned in
> tax years beginning in 2026.
> ```

> ```text
> OASDI Contribution and Benefit Base
> General
> The OASDI contribution and benefit
> base is $184,500 for remuneration paid
> in 2026 and self-employment income
> earned in tax years beginning in 2026.
> The OASDI contribution and benefit
> base serves as the maximum annual
> earnings on which OASDI taxes are
> paid. It is also the maximum annual
> earnings used in determining a person’s
> OASDI benefits.
> 
> lotter on DSK11XQN23PROD with NOTICES1
> 
> Computation
> Section 230(b) of the Act provides the
> formula used to determine the OASDI
> contribution and benefit base. Under the
> formula, the base for 2026 is the larger
> of: (1) the 1994 base of $60,600
> multiplied by the ratio of the national
> average wage index for 2024 to that for
> 1992; or (2) the current base ($176,100).
> If the resulting amount is not a multiple
> of $300, we round it to the nearest
> multiple of $300.
> OASDI Contribution and Benefit Base
> Amount
> Multiplying the 1994 OASDI
> contribution and benefit base ($60,600)
> by the ratio of the national average wage
> index for 2024 ($69,846.57 as
> determined above) to that for 1992
> 
> VerDate Sep<11>2014
> 
> 16:58 Oct 31, 2025
> 
> Jkt 268001
> 
> ($22,935.42) produces $184,548.71. We
> round this amount to $184,500. Because
> $184,500 exceeds the current base
> amount of $176,100, the OASDI
> contribution and benefit base is
> $184,500 for 2026.
> ```

- **Document:** SSA Office of the Chief Actuary, *Contribution and Benefit Base*
- **Currency / version:** page text read 2026-09-24
- **Heading the quote sits under:** Contribution And Benefit Base (body text and the table 'Contribution and benefit bases, 1937-2026')
- **URL:** https://www.ssa.gov/oact/cola/cbb.html
- **Applies to:** OASDI wage cap for 2026 earnings
- **Extraction:** curl gets HTTP 403 from ssa.gov, so the text was read with an in-app browser and saved as `raw/ssa_cbb_browser.txt`. That file keeps the full 1937-2026 table

> Social Security's Old-Age, Survivors, and Disability Insurance (OASDI) program limits the amount of earnings subject to taxation for a given year. The same annual limit also applies when those earnings are used in a benefit computation. This limit changes each year with changes in the national average wage index. We call this annual limit the contribution and benefit base. This amount is also commonly referred to as the taxable maximum. For earnings in 2026, this base is $184,500.
>
> The OASDI tax rate for wages paid in 2026 is set by statute at 6.2 percent for employees and employers, each. Thus, an individual with wages equal to or larger than $184,500 would contribute $11,439.00 to the OASDI program in 2026, and his or her employer would contribute the same amount. The OASDI tax rate for self-employment income in 2026 is 12.4 percent.

> ```text
> 2024	168,600
> 2025	176,100
> 2026	$184,500
> 
> Note: Amounts for 1937-74 and for 1979-81 were set by statute; all other amounts were determined under automatic adjustment provisions of the Social Security Act.
> ```

## 8. 26 USC 151: 151(b) spousal exemption and 151(d)(5) with the OBBBA senior deduction

- **Document:** 26 U.S.C. §151(b)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §151. Allowance of deductions for personal exemptions → (b) Taxpayer and spouse
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section151&num=0&edition=prelim
- **Applies to:** A taxpayer who does not file jointly may take a spousal exemption only if the spouse had no gross income and is not another taxpayer's dependent. §63(f)(1)(B) and (f)(2)(B) tie the spouse's aged/blind additional amount on a separate return to this test
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (b) Taxpayer and spouse
>
> An exemption of the exemption amount for the taxpayer; and an additional exemption of the exemption amount for the spouse of the taxpayer if a joint return is not made by the taxpayer and his spouse, and if the spouse, for the calendar year in which the taxable year of the taxpayer begins, has no gross income and is not the dependent of another taxpayer.

- **Document:** 26 U.S.C. §151(d)(5)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §151 → (d) Exemption amount → (5) Special rules for taxable years beginning after 2017 → (A) Exemption amount; (B) References; (C) Deduction for seniors → (i)-(v)
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section151&num=0&edition=prelim
- **Applies to:** (C): taxable years beginning before Jan. 1, 2029. (C)(iii)(I) sets the MAGI phase-out: $75,000, or $150,000 on a joint return. (C)(v): a married individual under §7703 may take the deduction only on a joint return
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (5) Special rules for taxable years beginning after 2017
>
> In the case of a taxable year beginning after December 31, 2017-
>
> (A) Exemption amount
>
> The term "exemption amount" means zero.
>
> (B) References
>
> For purposes of any other provision of this title, the reduction of the exemption amount to zero under subparagraph (A) shall not be taken into account in determining whether a deduction is allowed or allowable, or whether a taxpayer is entitled to a deduction, under this section.
>
> (C) Deduction for seniors
>
> (i) In general
>
> In the case of a taxable year beginning before January 1, 2029, there shall be allowed a deduction in an amount equal to $6,000 for each qualified individual with respect to the taxpayer.
>
> (ii) Qualified individual
>
> For purposes of clause (i), the term "qualified individual" means-
>
> (I) the taxpayer, if the taxpayer has attained age 65 before the close of the taxable year, and
>
> (II) in the case of a joint return, the taxpayer's spouse, if such spouse has attained age 65 before the close of the taxable year.
>
> (iii) Limitation based on modified adjusted gross income
>
> (I) In general
>
> In the case of any taxpayer for any taxable year, the $6,000 amount in clause (i) shall be reduced (but not below zero) by 6 percent of so much of the taxpayer's modified adjusted gross income as exceeds $75,000 ($150,000 in the case of a joint return).
>
> (II) Modified adjusted gross income
>
> For purposes of this clause, the term "modified adjusted gross income" means the adjusted gross income of the taxpayer for the taxable year increased by any amount excluded from gross income under section 911, 931, or 933.
>
> (iv) Social security number required
>
> (I) In general
>
> Clause (i) shall not apply with respect to a qualified individual unless the taxpayer includes such qualified individual's social security number on the return of tax for the taxable year.
>
> (II) Social security number
>
> For purposes of subclause (I), the term "social security number" has the meaning given such term in section 24(h)(7).
>
> (v) Married individuals
>
> If the taxpayer is a married individual (within the meaning of section 7703), this subparagraph shall apply only if the taxpayer and the taxpayer's spouse file a joint return for the taxable year.

- **Document:** 26 U.S.C. §151, Editorial Notes → Amendments (2025); Effective Date of 2025 Amendment
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** Amendments → 2025-Subsec. (d)(5)
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section151&num=0&edition=prelim
- **Applies to:** Taxable years beginning after Dec. 31, 2024
- **Extraction:** `strip_notes.py` (uscode HTML statute + editorial notes, tags stripped)

> 2025-Subsec. (d)(5). Pub. L. 119–21, §70103(a)(1), (2), substituted "beginning after 2017" for "2018 through 2025" in heading and struck out ", and before January 1, 2026" after "December 31, 2017" in introductory provisions.
>
> Subsec. (d)(5)(C). Pub. L. 119–21, §70103(a)(3), added subpar. (C).

> Pub. L. 119–21, title VII, §70103(c), July 4, 2025, 139 Stat. 160 , provided that: "The amendments made by this section [amending this section and section 6213 of this title] shall apply to taxable years beginning after December 31, 2024."

Full-document check: the full text of Rev. Proc. 2025-32 (`raw/rp-25-32.txt`, 1,596 lines) contains no occurrence of `151`, so it sets no 2026 inflation adjustment for the §151(d)(5)(C) $6,000 or its $75,000/$150,000 thresholds. The statute quoted above has no inflation-adjustment clause for (C).

## 9. 26 USC 24: child tax credit (24(a), (b), (d)(1), (h), (i))

- **Document:** 26 U.S.C. §24(a)-(b)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §24. Child tax credit → (a) Allowance of credit; (b) Limitations → (1); (2) Threshold amount
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section24&num=0&edition=prelim
- **Applies to:** (b)(2)(C) gives $55,000 for a married individual filing a separate return, but (h)(3) replaces (b)(2) for taxable years after 2017
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (a) Allowance of credit
>
> There shall be allowed as a credit against the tax imposed by this chapter for the taxable year with respect to each qualifying child of the taxpayer for which the taxpayer is allowed a deduction under section 151 an amount equal to $1,000.
>
> (b) Limitations
>
> (1) Limitation based on adjusted gross income
>
> The amount of the credit allowable under subsection (a) shall be reduced (but not below zero) by $50 for each $1,000 (or fraction thereof) by which the taxpayer's modified adjusted gross income exceeds the threshold amount. For purposes of the preceding sentence, the term "modified adjusted gross income" means adjusted gross income increased by any amount excluded from gross income under section 911, 931, or 933.
>
> (2) Threshold amount
>
> For purposes of paragraph (1), the term "threshold amount" means-
>
> (A) $110,000 in the case of a joint return,
>
> (B) $75,000 in the case of an individual who is not married, and
>
> (C) $55,000 in the case of a married individual filing a separate return.
>
> For purposes of this paragraph, marital status shall be determined under section 7703.

- **Document:** 26 U.S.C. §24(d)(1)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §24 → (d) Portion of credit refundable → (1) In general
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section24&num=0&edition=prelim
- **Applies to:** Refundable ACTC for all filers. (h)(5)-(6) and (i)(1) modify it
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (d) Portion of credit refundable
>
> (1) In general
>
> The aggregate credits allowed to a taxpayer under subpart C shall be increased by the lesser of-
>
> (A) the credit which would be allowed under this section without regard to this subsection and the limitation under section 26(a) or
>
> (B) the amount by which the aggregate amount of credits allowed by this subpart (determined without regard to this subsection) would increase if the limitation imposed by section 26(a) were increased by the greater of-
>
> (i) 15 percent of so much of the taxpayer's earned income (within the meaning of section 32) which is taken into account in computing taxable income for the taxable year as exceeds $3,000, or
>
> (ii) in the case of a taxpayer with 3 or more qualifying children, the excess (if any) of-
>
> (I) the taxpayer's social security taxes for the taxable year, over
>
> (II) the credit allowed under section 32 for the taxable year.
>
> The amount of the credit allowed under this subsection shall not be treated as a credit allowed under this subpart and shall reduce the amount of credit otherwise allowable under subsection (a) without regard to section 26(a). For purposes of subparagraph (B), any amount excluded from gross income by reason of section 112 shall be treated as earned income which is taken into account in computing taxable income for the taxable year.

- **Document:** 26 U.S.C. §24(h)-(i)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §24 → (h) Special rules for taxable years beginning after 2017 → (1)-(7); (i) Inflation adjustments → (1)-(3)
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section24&num=0&edition=prelim
- **Applies to:** (h)(3): a $400,000 threshold for joint returns and $200,000 'in any other case', which includes MFS. (h)(7)(A)(i): the taxpayer's SSN, or on a joint return at least one spouse's SSN
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (h) Special rules for taxable years beginning after 2017
>
> (1) In general
>
> In the case of a taxable year beginning after December 31, 2017, this section shall be applied as provided in paragraphs (2) through (7).
>
> (2) Credit amount
>
> Subsection (a) shall be applied by substituting "$2,200" for "$1,000".
>
> (3) Limitation
>
> In lieu of the amount determined under subsection (b)(2), the threshold amount shall be $400,000 in the case of a joint return ($200,000 in any other case).
>
> (4) Partial credit allowed for certain other dependents
>
> (A) In general
>
> The credit determined under subsection (a) (after the application of paragraph (2)) shall be increased by $500 for each dependent of the taxpayer (as defined in section 152) other than a qualifying child described in subsection (c).
>
> (B) Exception for certain noncitizens
>
> Subparagraph (A) shall not apply with respect to any individual who would not be a dependent if subparagraph (A) of section 152(b)(3) were applied without regard to all that follows "resident of the United States".
>
> (C) Certain qualifying children
>
> In the case of any qualifying child with respect to whom a credit is not allowed under this section by reason of paragraph (7), such child shall be treated as a dependent to whom subparagraph (A) applies.
>
> (5) Maximum amount of refundable credit
>
> The amount determined under subsection (d)(1)(A) with respect to any qualifying child shall not exceed $1,400, and such subsection shall be applied without regard to paragraph (4) of this subsection.
>
> (6) Earned income threshold for refundable credit
>
> Subsection (d)(1)(B)(i) shall be applied by substituting "$2,500" for "$3,000".
>
> (7) Social security number required
>
> (A) In general
>
> No credit shall be allowed under this section to a taxpayer with respect to any qualifying child unless the taxpayer includes on the return of tax for the taxable year-
>
> (i) the taxpayer's social security number (or, in the case of a joint return, the social security number of at least 1 spouse), and
>
> (ii) the social security number of such qualifying child.
>
> (B) Social security number
>
> For purposes of this paragraph, the term "social security number" means a social security number issued to an individual by the Social Security Administration, but only if the social security number is issued-
>
> (i) to a citizen of the United States or pursuant to subclause (I) (or that portion of subclause (III) that relates to subclause (I)) of section 205(c)(2)(B)(i) of the Social Security Act, and
>
> (ii) before the due date for such return.
>
> (i) Inflation adjustments
>
> (1) Maximum amount of refundable credit
>
> In the case of a taxable year beginning after 2024, the $1,400 amount in subsection (h)(5) shall be increased by an amount equal to-
>
> (A) such dollar amount, multiplied by
>
> (B) the cost-of-living adjustment determined under section 1(f)(3) for the calendar year in which the taxable year begins, determined by substituting "2017" for "2016" in subparagraph (A)(ii) thereof.
>
> (2) Special rule for adjustment of credit amount
>
> In the case of a taxable year beginning after 2025, the $2,200 amount in subsection (h)(2) shall be increased by an amount equal to-
>
> (A) such dollar amount, multiplied by
>
> (B) the cost-of-living adjustment determined under section 1(f)(3) for the calendar year in which the taxable year begins, determined by substituting "2024" for "2016" in subparagraph (A)(ii) thereof.
>
> (3) Rounding
>
> If any increase under this subsection is not a multiple of $100, such increase shall be rounded to the next lowest multiple of $100.

- **Document:** 26 U.S.C. §24, Editorial Notes → Amendments (2025); Effective Date of 2025 Amendment
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** Amendments → 2025-Subsec. (h) ... Subsec. (i)
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section24&num=0&edition=prelim
- **Applies to:** Taxable years beginning after Dec. 31, 2024
- **Extraction:** `strip_notes.py` (uscode HTML statute + editorial notes, tags stripped)

> 2025-Subsec. (h). Pub. L. 119–21, §70104(a)(3), substituted "beginning after 2017" for "2018 through 2025" in heading.
>
> Subsec. (h)(1). Pub. L. 119–21, §70104(a)(1), struck out ", and before January 1, 2026" after "December 31, 2017".
>
> Subsec. (h)(2). Pub. L. 119–21, §70104(a)(2), substituted "$2,200" for "$2,000".
>
> Subsec. (h)(5). Pub. L. 119–21, §70104(d), amended par. (5) generally. Prior to amendment, par. (5) related to maximum amount of refundable credit and its adjustment for inflation.
>
> Subsec. (h)(7). Pub. L. 119–21, §70104(b), amended par. (7) generally. Prior to amendment, par. (7) allowed a credit under this section to a taxpayer with respect to any qualifying child if the taxpayer included the social security number of such child on the tax return for the taxable year.
>
> Subsec. (i). Pub. L. 119–21, §70104(c), amended subsec. (i) generally. Prior to amendment, subsec. (i) related to special rules for 2021 for refundable credit, 17-year-olds eligible for treatment as qualifying children, credit amount, and reduction of increased credit amount based on modified adjusted gross income.

> Pub. L. 119–21, title VII, §70104(f), July 4, 2025, 139 Stat. 161 , provided that: "The amendments made by this section [amending this section and section 6213 of this title] shall apply to taxable years beginning after December 31, 2024."

## 10. 26 USC 152 (context for §2(b) qualifying child and qualifying relative)

- **Document:** 26 U.S.C. §152(c)(1), (d)(1)-(3), (f)(1)(A)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §152. Dependent defined → (c) Qualifying child → (1) In general; (d) Qualifying relative → (1) In general, (2) Relationship, (3) Special rule relating to multiple support agreements; (f) Other definitions and rules → (1) Child defined → (A)
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section152&num=0&edition=prelim
- **Applies to:** Dependency tests referenced by §2(b)(1)(A)(i)-(ii), §2(b)(3)(B), and §7703(b)(1) ('child (within the meaning of section 152(f)(1))')
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (c) Qualifying child
>
> For purposes of this section-
>
> (1) In general
>
> The term "qualifying child" means, with respect to any taxpayer for any taxable year, an individual-
>
> (A) who bears a relationship to the taxpayer described in paragraph (2),
>
> (B) who has the same principal place of abode as the taxpayer for more than one-half of such taxable year,
>
> (C) who meets the age requirements of paragraph (3),
>
> (D) who has not provided over one-half of such individual's own support for the calendar year in which the taxable year of the taxpayer begins, and
>
> (E) who has not filed a joint return (other than only for a claim of refund) with the individual's spouse under section 6013 for the taxable year beginning in the calendar year in which the taxable year of the taxpayer begins.

> (d) Qualifying relative
>
> For purposes of this section-
>
> (1) In general
>
> The term "qualifying relative" means, with respect to any taxpayer for any taxable year, an individual-
>
> (A) who bears a relationship to the taxpayer described in paragraph (2),
>
> (B) whose gross income for the calendar year in which such taxable year begins is less than the exemption amount (as defined in section 151(d)),
>
> (C) with respect to whom the taxpayer provides over one-half of the individual's support for the calendar year in which such taxable year begins, and
>
> (D) who is not a qualifying child of such taxpayer or of any other taxpayer for any taxable year beginning in the calendar year in which such taxable year begins.
>
> (2) Relationship
>
> For purposes of paragraph (1)(A), an individual bears a relationship to the taxpayer described in this paragraph if the individual is any of the following with respect to the taxpayer:
>
> (A) A child or a descendant of a child.
>
> (B) A brother, sister, stepbrother, or stepsister.
>
> (C) The father or mother, or an ancestor of either.
>
> (D) A stepfather or stepmother.
>
> (E) A son or daughter of a brother or sister of the taxpayer.
>
> (F) A brother or sister of the father or mother of the taxpayer.
>
> (G) A son-in-law, daughter-in-law, father-in-law, mother-in-law, brother-in-law, or sister-in-law.
>
> (H) An individual (other than an individual who at any time during the taxable year was the spouse, determined without regard to section 7703, of the taxpayer) who, for the taxable year of the taxpayer, has the same principal place of abode as the taxpayer and is a member of the taxpayer's household.
>
> (3) Special rule relating to multiple support agreements
>
> For purposes of paragraph (1)(C), over one-half of the support of an individual for a calendar year shall be treated as received from the taxpayer if-
>
> (A) no one person contributed over one-half of such support,
>
> (B) over one-half of such support was received from 2 or more persons each of whom, but for the fact that any such person alone did not contribute over one-half of such support, would have been entitled to claim such individual as a dependent for a taxable year beginning in such calendar year,
>
> (C) the taxpayer contributed over 10 percent of such support, and
>
> (D) each person described in subparagraph (B) (other than the taxpayer) who contributed over 10 percent of such support files a written declaration (in such manner and form as the Secretary may by regulations prescribe) that such person will not claim such individual as a dependent for any taxable year beginning in such calendar year.

> (f) Other definitions and rules
>
> For purposes of this section-
>
> (1) Child defined
>
> (A) In general
>
> The term "child" means an individual who is-
>
> (i) a son, daughter, stepson, or stepdaughter of the taxpayer, or
>
> (ii) an eligible foster child of the taxpayer.

## 11. IRS Rev. Proc. 2025-32: 2026 inflation-adjusted amounts (operative version)

**Which version is operative.** The IRS drop URL now serves a PDF with Wayback SHA-1 digest `FJ7E6FGDMMK63VV7XYJRPEC4OHU3QKPA` (sha256 `e9ada115…635b`). The Wayback Machine first captured that version on 2025-10-19; its PDF metadata gives CreationDate Fri Oct 17 15:43:06 2025 EDT. Two earlier versions, both dated October 9, 2025, carried different figures (see 11.6). The version published in Internal Revenue Bulletin 2025-45 (November 3, 2025, page 695) matches the current drop version on every figure quoted here; cross-checked below. The USC table of inflation revenue procedures under §1 lists only 'Revenue Procedure 2025–32' for 2026, with no modifying procedure (quoted in 11.7). No statute amendment after Pub. L. 119-21 touches §1(j), §24(h)-(i), §32(b)/(d)/(j), §63(c)(7)/(f), or §151(d)(5): on those pages, the only 119th-Congress laws cited as amending are 119-21 and, for §63, 119-108, which added §63(b)(8), a disaster-loss item.

### 11.1 Purpose and OBBBA changes (§1(j), §24, §63(c)(7))

- **Document:** IRS Rev. Proc. 2025-32 (drop version dated Oct. 17, 2025; also published at 2025-45 I.R.B. 695, Nov. 3, 2025)
- **Currency / version:** items 'as in effect on October 9, 2025'
- **Heading the quote sits under:** SECTION 1. PURPOSE; SECTION 2. CHANGES → .01, .03, .08
- **URL:** https://www.irs.gov/pub/irs-drop/rp-25-32.pdf
- **Applies to:** All individual filers
- **Extraction:** `pdftotext -layout` (`raw/rp-25-32.txt`)

> ```text
> SECTION 1. PURPOSE
> 
>    This revenue procedure modifies certain sections of Rev. Proc. 2024-40, 2024-45
> 
> I.R.B. 1100, to reflect the amendments to the Internal Revenue Code (Code) by Public
> 
> Law 119-21, 139 Stat. 72 (July 4, 2025), commonly known as the One, Big, Beautiful
> 
> Bill Act (OBBBA). This revenue procedure sets forth inflation-adjusted items for 2026
> 
> for various Code provisions as in effect on October 9, 2025.
> 
>    The inflation-adjusted items for the Code sections set forth in section 4 of this
> 
> revenue procedure are generally determined by reference to § 1(f). To the extent
> 
> amendments to the Code are enacted for 2025 or 2026 after October 9, 2025,
> 
> taxpayers should consult additional guidance to determine whether these adjustments
> 
> remain applicable for 2026.
> 
> ```

> ```text
>    .01 Section 70101 of the OBBBA amends § 1(j) to make the tax rate tables that were
> 
> effective for taxable years beginning after December 31, 2017, and before January 1,
> 
> 2026, permanent. The existing seven tax rates of 10%, 12%, 22%, 24%, 32%, 35%,
> 
>                                              5
> 
> 
> and 37% remain in effect for individual taxpayers. The existing four tax rates of 10%,
> 
> 24%, 35%, and 37% remain in effect for estates and trusts.
> 
> ```

> ```text
>    .03 Section 70104 of the OBBBA amends § 24 to make the increased and expanded
> 
> child tax credit under § 24(h) that were effective for taxable years beginning after
> 
> December 31, 2017, and before January 1, 2026, permanent. In addition, the OBBBA
> 
> amends § 24(h)(2) to provide that the maximum amount of child tax credit is $2,200 for
> 
> any taxable year beginning in 2025. This amount is adjusted for inflation for taxable
> 
> years beginning after December 31, 2025.
> 
> ```

> ```text
>    .08 Section 70102 of the OBBBA amends § 63(c)(7) to make the temporary
> 
> increases of the basic standard deduction amounts provided in § 63(c)(2) that were
> 
> effective for taxable years beginning after December 31, 2017, and before January 1,
> 
> 2026, permanent, and further increased the base amounts. As a result, § 63(c)(7) as
> 
> amended by the OBBBA provides that, for taxable years beginning after December 31,
> 
> 2024, the basic standard deduction amounts provided in § 63(c)(2) are increased to
> 
> $15,750 for single individuals and married individuals filing separate returns; $23,625 for
> 
> heads of households; and $31,500 for married individuals filing a joint return and
> 
> surviving spouses. These amounts are adjusted for inflation for taxable years beginning
> 
> after 2025. See section 3 of this revenue procedure for removal of section 2.15(1) of
> 
> Rev. Proc. 2024-40.
> 
> ```

### 11.2 §4.01: 2026 tax rate tables (Table 1 joint, Table 2 HoH, Table 3 unmarried, Table 4 MFS)

- **Document:** IRS Rev. Proc. 2025-32 (drop version dated Oct. 17, 2025; also published at 2025-45 I.R.B. 695, Nov. 3, 2025)
- **Currency / version:** taxable years beginning in 2026
- **Heading the quote sits under:** SECTION 4. 2026 ADJUSTED ITEMS → .01 Tax Rate Tables → TABLES 1-4
- **URL:** https://www.irs.gov/pub/irs-drop/rp-25-32.pdf
- **Applies to:** Table 1: joint returns and surviving spouses. Table 2: heads of household. Table 3: unmarried individuals. Table 4: married individuals filing separate returns
- **Extraction:** `pdftotext -layout` (`raw/rp-25-32.txt`)

> ```text
>    .01 Tax Rate Tables. For taxable years beginning in 2026, the tax rate tables under
> 
> § 1 are as follows:
> 
>   TABLE 1 - Section 1(j)(2)(A) –Married Individuals Filing Joint Returns and Surviving
>                                        Spouses
> 
>            If Taxable Income Is:                       The Tax Is:
>            Not over $24,800                            10% of the taxable income
>            Over $24,800 but not over                   $2,480 plus 12% of the excess
>            $100,800                                    over $24,800
>            Over $100,800 but not over                  $11,600 plus 22% of the excess
>            $211,400                                    over $100,800
>            Over $211,400 but not over                  $35,932 plus 24% of the excess
>            $403,550                                    over $211,400
>            Over $403,550 but not over                  $82,048 plus 32% of the excess
>            $512,450                                    over $403,550
>            Over $512,450 but not over                  $116,896 plus 35% of the
>            $768,700                                    excess over $512,450
>            Over $768,700                               $206,583.50 plus 37% of the
>                                                        excess over $768,700
> 
> 
>                     TABLE 2 - Section 1(j)(2)(B) – Heads of Households
> 
> 
>            If Taxable Income Is:                       The Tax Is:
>            Not over $17,700                            10% of the taxable income
>            Over $17,700 but                            $1,770 plus 12% of
>            not over $67,450                            the excess over $17,700
>            Over $67,450 but                            $7,740 plus 22% of
>            not over $105,700                           the excess over $67,450
> 
>                                          11
> 
> 
>         Over $105,700 but                            $16,155 plus 24% of
>         not over $201,750                            the excess over $105,700
>         Over $201,750 but                            $39,207 plus 32% of
>         not over $256,200                            the excess over $201,750
>         Over $256,200 but                            $56,631 plus 35% of
>         not over $640,600                            the excess over $256,200
>         Over $640,600                                $191,171 plus 37% of
>                                                      the excess over $640,600
> 
> 
> TABLE 3 - Section 1(j)(2)(C) – Unmarried Individuals (other than Surviving Spouses and
>                                 Heads of Households)
> 
> 
>         If Taxable Income Is:                        The Tax Is:
>         Not over $12,400                             10% of the taxable income
>         Over $12,400 but                             $1,240 plus 12% of
>         not over $50,400                             the excess over $12,400
>         Over $50,400 but                             $5,800 plus 22% of
>         not over $105,700                            the excess over $50,400
>         Over $105,700 but                            $17,966 plus 24% of
>         not over $201,775                            the excess over $105,700
>         Over $201,775 but                            $41,024 plus 32% of
>         not over $256,225                            the excess over $201,775
>         Over $256,225 but                            $58,448 plus 35% of
>         not over $640,600                            the excess over $256,225
>         Over $640,600                                $192,979.25 plus 37% of
>                                                      the excess over $640,600
> 
> 
>       TABLE 4 - Section 1(j)(2)(D) – Married Individuals Filing Separate Returns
> 
> 
>         If Taxable Income Is:                        The Tax Is:
>         Not over $12,400                             10% of the taxable income
>         Over $12,400 but                             $1,240 plus 12% of
>         not over $50,400                             the excess over $12,400
>         Over $50,400 but                             $5,800 plus 22% of
>         not over $105,700                            the excess over $50,400
> 
>                                              12
> 
> 
>          Over $105,700 but                               $17,966 plus 24% of
>          not over $201,775                               the excess over $105,700
>          Over $201,775 but                               $41,024 plus 32% of
>          not over $256,225                               the excess over $201,775
>          Over $256,225 but                               $58,448 plus 35% of
>          not over $384,350                               the excess over $256,225
>          Over $384,350                                   $103,291.75 plus 37% of
>                                                          the excess over $384,350
> 
> 
> ```

### 11.2a §4.03: 2026 capital-gains breakpoints under §1(j)(5)(B)

- **Document:** IRS Rev. Proc. 2025-32 (drop version dated Oct. 17, 2025; also published at 2025-45 I.R.B. 695, Nov. 3, 2025)
- **Currency / version:** taxable years beginning in 2026
- **Heading the quote sits under:** SECTION 4 → .03 Maximum Capital Gains Rate (§ 1(h), § 1(j)(5))
- **URL:** https://www.irs.gov/pub/irs-drop/rp-25-32.pdf
- **Applies to:** MFS row: 'Married Individuals Filing Separate Returns'. Its maximum zero-rate amount equals the 'All Other Individuals' row, and its maximum 15% amount differs from that row
- **Extraction:** `pdftotext -layout` (`raw/rp-25-32.txt`)

> ```text
>    .03 Maximum Capital Gains Rate (§ 1(h), § 1(j)(5)). For taxable years beginning in
> 
> 2026, the maximum zero rate amounts and maximum 15 percent rate amounts under
> 
> § 1(j)(5)(B), as adjusted for inflation, are as follows:
> 
>                    Filing Status                       Maximum Zero     Maximum15%
>                                                         Rate Amount     Rate Amount
> 
>  Married Individuals Filing Joint Returns and                 $98,900          $613,700
>  Surviving Spouse
> 
>  Married Individuals Filing Separate Returns                  $49,450          $306,850
> 
>  Heads of Household                                           $66,200          $579,600
> 
>  All Other Individuals                                        $49,450          $545,500
> 
>  Estates and Trusts                                            $3,300             $16,250
> 
> 
> 
> ```

### 11.3 §4.05: child tax credit, 2026

- **Document:** IRS Rev. Proc. 2025-32 (drop version dated Oct. 17, 2025; also published at 2025-45 I.R.B. 695, Nov. 3, 2025)
- **Currency / version:** taxable years beginning in 2026
- **Heading the quote sits under:** SECTION 4 → .05 Child Tax Credit → (1) Maximum amount of the credit; (2) Refundable portion
- **URL:** https://www.irs.gov/pub/irs-drop/rp-25-32.pdf
- **Applies to:** All filers, including MFS
- **Extraction:** `pdftotext -layout` (`raw/rp-25-32.txt`)

> ```text
>    .05 Child Tax Credit.
> 
>      (1) Maximum amount of the credit. For taxable years beginning in 2026, the
> 
> maximum amount of the credit allowed under § 24(a) is $2,200.
> 
>      (2) Refundable portion. For taxable years beginning in 2026, the amount used in
> 
> § 24(d)(1)(A) to determine the amount of the credit under § 24 that may be refundable is
> 
> $1,700.
> 
> ```

### 11.4 §4.06: earned income credit, 2026 (0-child and 1-child columns included)

- **Document:** IRS Rev. Proc. 2025-32 (drop version dated Oct. 17, 2025; also published at 2025-45 I.R.B. 695, Nov. 3, 2025)
- **Currency / version:** taxable years beginning in 2026
- **Heading the quote sits under:** SECTION 4 → .06 Earned Income Credit → (1) In general (table); (2) Excessive Investment Income
- **URL:** https://www.irs.gov/pub/irs-drop/rp-25-32.pdf
- **Applies to:** Joint rows: married filing jointly. 'All other filing statuses' rows: single, HoH, and married individuals who do not file jointly but meet the §32(d) separated-spouse rules (the text says so)
- **Extraction:** `pdftotext -layout` (`raw/rp-25-32.txt`)

> ```text
>    .06 Earned Income Credit.
> 
>      (1) In general. For taxable years beginning in 2026, the following amounts are
> 
> used to determine the earned income credit under § 32(b). The "earned income
> 
> amount" is the amount of earned income at or above which the maximum amount of the
> 
> earned income credit is allowed. The "threshold phaseout amount" is the amount of
> 
> adjusted gross income (or, if greater, earned income) above which the maximum
> 
> amount of the credit begins to phase out. The "completed phaseout amount" is the
> 
> amount of adjusted gross income (or, if greater, earned income) at or above which no
> 
> credit is allowed. The threshold phaseout amounts and the completed phaseout
> 
> amounts shown in the table below for married taxpayers filing a joint return include the
> 
> increase provided in § 32(b)(2)(B), as adjusted for inflation for taxable years beginning
> 
> in 2026. The threshold phaseout amounts and the completed phaseout amounts shown
> 
> in the table below for taxpayers with all other filing statuses also apply to married
> 
> taxpayers who are not filing a joint return and satisfy the special rules for separated
> 
> spouses in § 32(d).
> 
>                                               15
> 
> 
>                                          Number of Qualifying Children
> 
>              Item                    One            Two      Three or More        None
> 
>  Earned Income Amount               $13,020        $18,290          $18,290       $8,680
> 
>  Maximum Amount of Credit            $4,427         $7,316           $8,231         $664
> 
>  Threshold Phaseout Amount          $31,160        $31,160          $31,160     $18,140
>  (Married Filing Jointly)
> 
>  Completed Phaseout                 $58,863        $65,899          $70,244     $26,820
>  Amount (Married Filing
>  Jointly)
> 
>  Threshold Phaseout Amount          $23,890        $23,890          $23,890     $10,860
>  (All other filing statuses)
> 
>  Completed Phaseout                 $51,593        $58,629          $62,974     $19,540
>  Amount (All other filing
>  statuses)
> 
> 
> 
> The instructions for the Form 1040 series provide tables showing the amount of the
> 
> earned income credit for each type of taxpayer.
> 
>      (2) Excessive Investment Income. For taxable years beginning in 2026, the
> 
> earned income tax credit is not allowed under § 32(i) if the aggregate amount of certain
> 
> investment income exceeds $12,200.
> 
> ```

### 11.5 §4.14: standard deduction, 2026 (basic, dependent, aged/blind)

- **Document:** IRS Rev. Proc. 2025-32 (drop version dated Oct. 17, 2025; also published at 2025-45 I.R.B. 695, Nov. 3, 2025)
- **Currency / version:** taxable years beginning in 2026
- **Heading the quote sits under:** SECTION 4 → .14 Standard Deduction → (1) In general; (2) Dependent; (3) Aged or blind
- **URL:** https://www.irs.gov/pub/irs-drop/rp-25-32.pdf
- **Applies to:** (1): each filing status, with MFS listed separately. (3): $1,650 for each aged or blind condition; $2,050 if 'also unmarried and not a surviving spouse'. MFS filers are married, so the $1,650 figure applies to them
- **Extraction:** `pdftotext -layout` (`raw/rp-25-32.txt`)

> ```text
>     .14 Standard Deduction.
> 
>       (1) In general. For taxable years beginning in 2026, the standard deduction
> 
> amounts under § 63(c)(2) are as follows:
> 
>                             Filing Status                                Standard
>                                                                          Deduction
> Married Individuals Filing Joint Returns and Surviving Spouses                $32,200
> (§ 1(j)(2)(A))
> Heads of Households (§ 1(j)(2)(B))                                            $24,150
> Unmarried Individuals (other than Surviving Spouses and Heads of              $16,100
> Households) (§ 1(j)(2)(C))
> Married Individuals Filing Separate Returns (§ 1(j)(2)(D))                    $16,100
> 
> 
> 
>       (2) Dependent. For taxable years beginning in 2026, the standard deduction
> 
> amount under § 63(c)(5) for an individual who may be claimed as a dependent by
> 
> another taxpayer cannot exceed the greater of (1) $1,350, or (2) the sum of $450 and
> 
> the individual's earned income.
> 
>       (3) Aged or blind. For taxable years beginning in 2026, the additional standard
> 
> deduction amount under § 63(f) for the aged or the blind is $1,650. The additional
> 
> standard deduction amount is increased to $2,050 if the individual is also unmarried and
> 
> not a surviving spouse.
> 
> ```

- **Document:** IRS Rev. Proc. 2025-32 (drop version dated Oct. 17, 2025; also published at 2025-45 I.R.B. 695, Nov. 3, 2025)
- **Currency / version:** taxable years beginning in 2026
- **Heading the quote sits under:** SECTION 4 → .23 Gross Income Limitation for a Qualifying Relative
- **URL:** https://www.irs.gov/pub/irs-drop/rp-25-32.pdf
- **Applies to:** §152(d)(1)(B) gross income test, relevant to HoH via §2(b)(1)(A)(ii)
- **Extraction:** `pdftotext -layout` (`raw/rp-25-32.txt`)

> ```text
>    .23 Gross Income Limitation for a Qualifying Relative. For taxable years beginning in
> 
> 2026, the exemption amount referred to in § 152(d)(1)(B) is $5,300.
> 
>                                           21
> 
> 
> ```

### 11.6 Version history: MFS and HoH table figures that changed after the October 9, 2025 release

The three versions of `rp-25-32.pdf` in the Wayback Machine were each put through `pdftotext -layout` and diffed (`raw/rp-25-32-wb20251009144523.txt`, `raw/rp-25-32-wb20251009195737.txt`, `raw/rp-25-32.txt`). Table lines that differ:

- **Wayback 2025-10-09 14:45:23 (digest EED2PPAS…), Table 2 (HoH), 24% row** (`raw/rp-25-32-wb20251009144523.txt`):

> ```text
>         Over $105,700 but                            $16,155 plus 24% of
>         not over $201,775                            the excess over $105,700
> ```

- **Wayback 2025-10-09 14:45:23 (digest EED2PPAS…), Table 4 (MFS), 24% row** (`raw/rp-25-32-wb20251009144523.txt`):

> ```text
>          Over $105,700 but                               $17,996 plus 24% of
>          not over $201,775                               the excess over $105,700
> ```

- **Wayback 2025-10-09 19:57:37 (digest NJ2RSDME…), Table 4 (MFS), 24% row** (`raw/rp-25-32-wb20251009195737.txt`):

> ```text
>          Over $105,700 but                               $17,996 plus 24% of
>          not over $201,775                               the excess over $105,700
> ```

- **Current drop version (digest FJ7E6FGD…), Table 4 (MFS), 24% row** (`raw/rp-25-32.txt`):

> ```text
>          Over $105,700 but                               $17,966 plus 24% of
>          not over $201,775                               the excess over $105,700
> ```

- **Current drop version (digest FJ7E6FGD…), Table 2 (HoH), 24% row** (`raw/rp-25-32.txt`):

> ```text
>         Over $105,700 but                            $16,155 plus 24% of
>         not over $201,750                            the excess over $105,700
> ```

Result: the October 9 versions printed the MFS 24%-bracket base tax as `$17,996`. The current version and IRB 2025-45 print `$17,966`. The first October 9 capture also printed the HoH 24%-bracket ceiling as `$201,775`, where the later versions print `$201,750`. Separately, a secondary source (Current Federal Tax Developments, 2025-10-20) reports that the revised version changed the 3+-child MFJ EITC completed phaseout from `$70,224` to `$70,244`. The diff confirms this.

### 11.7 Cross-checks against the IRB and USC

- **Document:** Internal Revenue Bulletin 2025-45 (Nov. 3, 2025), Rev. Proc. 2025-32 as published, pp. 699-700
- **Currency / version:** IRB PDF title 'IRB 2025-45 (Rev. 11-03-2025)'
- **Heading the quote sits under:** SECTION 4 → TABLE 4; .06 Earned Income Credit table; .14 Standard Deduction
- **URL:** https://www.irs.gov/pub/irs-irbs/irb25-45.pdf
- **Applies to:** Same as 11.2-11.5
- **Extraction:** `pdftotext -layout` (`raw/irb25-45.txt`)

> ```text
> TABLE 4 - Section 1(j)(2)(D) – Married Individuals Filing Separate Returns
> If Taxable Income Is:                                   The Tax Is:
> Not over $12,400                                        10% of the taxable income
> Over $12,400 but                                        $1,240 plus 12% of
> not over $50,400                                        the excess over $12,400
> Over $50,400 but                                        $5,800 plus 22% of
> not over $105,700                                       the excess over $50,400
> Over $105,700 but                                       $17,966 plus 24% of
> not over $201,775                                       the excess over $105,700
> Over $201,775 but                                       $41,024 plus 32% of
> not over $256,225                                       the excess over $201,775
> Over $256,225 but                                       $58,448 plus 35% of
> not over $384,350                                       the excess over $256,225
> Over $384,350                                           $103,291.75 plus 37% of
>                                                         the excess over $384,350
> 
> 
> 
> ```

> ```text
>                                                                                    Number of Qualifying Children
>                          Item                                        One              Two          Three or More           None
>  Earned Income Amount                                              $13,020          $18,290           $18,290             $8,680
>  Maximum Amount of Credit                                           $4,427           $7,316            $8,231              $664
>  Threshold Phaseout Amount (Married Filing Jointly)                $31,160          $31,160           $31,160            $18,140
>  Completed Phaseout Amount (Married Filing Jointly)                $58,863         $65,899            $70,244            $26,820
>  Threshold Phaseout Amount (All other filing statuses)             $23,890         $23,890            $23,890            $10,860
>  Completed Phaseout Amount (All other filing statuses)             $51,593         $58,629            $62,974            $19,540
> 
> 
> ```

> ```text
>                                             Filing Status                                                     Standard Deduction
>  Married Individuals Filing Joint Returns and Surviving Spouses (§ 1(j)(2)(A))                                     $32,200
>  Heads of Households (§ 1(j)(2)(B))                                                                                $24,150
>  Unmarried Individuals (other than Surviving Spouses and Heads of Households) (§ 1(j)(2)(C))                       $16,100
>  Married Individuals Filing Separate Returns (§ 1(j)(2)(D))                                                        $16,100
> ```

- **Document:** 26 U.S.C. §1, Executive Documents → Inflation Adjusted Items for Certain Years
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** Executive Documents → Inflation Adjusted Items for Certain Years (table of revenue procedures)
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1&num=0&edition=prelim
- **Applies to:** Lists the revenue procedure that governs each year's inflation adjustments
- **Extraction:** `strip_notes.py` (uscode HTML statute + editorial notes, tags stripped)

> Provisions relating to inflation adjustment of items in sections 1, 23, 24, 25A, 25B, 32, 36B, 42, 45R, 55, 59, 62, 63, 68, 125, 132, 135, 137, 146, 147, 148, 151, 152, 179, 179D, 199A, 213, 219, 220, 221, 223, 408A, 448, 461, 512, 513, 529A, 642, 685, 831, 877, 877A, 911, 1274A, 2010, 2032A, 2503, 2523, 2631, 2801, 4001, 4003, 4161, 4261, 4611, 5000A, 6012, 6013, 6033, 6039F, 6323, 6334, 6601, 6651, 6652, 6695, 6698, 6699, 6721, 6722, 6726, 7345, 7430, 7702B, and 9831 of this title for certain years were contained in the following:
>
> 2026-Revenue Procedure 2025–32.
>
> 2025-Revenue Procedure 2024–40.

## 12. TAXSIM-35 documentation (taxsimtest): mstat, spouse-income restriction, output columns

Engine documentation. It describes TAXSIM's inputs and outputs. It is not evidence of what the law is (evidence rule 3).

- **Document:** NBER, *Internet TAXSIM Test Version*
- **Currency / version:** fetched 2026-09-24. The page prints two different 'Date last modified' stamps: '28 February 2026' (after the input form) and 'August 23, 2024' (at the bottom)
- **Heading the quote sits under:** Page intro (law coverage and year range)
- **URL:** https://taxsim.nber.org/taxsimtest/
- **Applies to:** The whole TAXSIM test version
- **Extraction:** raw HTML, quoted in a code fence

> ```text
> <p>The federal law and state code is accurate to the best
> of our abilities
> through December 2024, including the ACA taxes on earned and
> unearned income (but not the penalties for lacking health
> insurance) and the pass-through features of the TCJA
> (except for the limitations based on capital or employees).
> ```

> ```text
> <b>2. year</b> Tax year ending Dec 31(4 digits between 1960 and 2024, but
> state must be zero if year is before 1977. (We don't have code for state
> laws before 1977).
> ```

- **Document:** NBER, *Internet TAXSIM Test Version*
- **Currency / version:** fetched 2026-09-24. The page prints two different 'Date last modified' stamps: '28 February 2026' (after the input form) and 'August 23, 2024' (at the bottom)
- **Heading the quote sits under:** Basic Data → Demography → '4. mstat Marital Status'
- **URL:** https://taxsim.nber.org/taxsimtest/
- **Applies to:** Input coding. `6` is separate (married). HoH is not an input code: TAXSIM derives it
- **Extraction:** raw HTML, quoted in a code fence

> ```text
> <b>4. mstat</b> Marital Status
>   <ul>
>   <li>1. single or head of household (unmarried)
>   <li>2. joint (married)
>   <li>6. separate (married). Note that Married-separate is not usually
>          desirable under US tax law.
>   <li>8. Dependent taxpayer. (Typically a child with income).
>   </ul>
> 
> Head of Household status is determined by taxsim from
> dependent information below. Unmarried taxpayers with dependents
> are assigned head-of-household.
> ```

- **Document:** NBER, *Internet TAXSIM Test Version*
- **Currency / version:** fetched 2026-09-24. The page prints two different 'Date last modified' stamps: '28 February 2026' (after the input form) and 'August 23, 2024' (at the bottom)
- **Heading the quote sits under:** Demography → '5. page and sage'
- **URL:** https://taxsim.nber.org/taxsimtest/
- **Applies to:** Spouse age input. The page says a non-zero sage is an error for an unmarried taxpayer
- **Extraction:** raw HTML, quoted in a code fence

> ```text
> <b>5. page</b> and <b>sage</b>
> 
> Age of primary and secondary taxpayers as of December 31st of the
> tax year (or zero). Taxpayer and spouse age variables determine
> eligibility for additional standard deductions, personal exemption,
> EITC and AMT exclusions etc. It is an error to specify a non-zero
> spouse age for an unmarried taxpayer. If left as zero will be treated
> as age 40.
> ```

- **Document:** NBER, *Internet TAXSIM Test Version*
- **Currency / version:** fetched 2026-09-24. The page prints two different 'Date last modified' stamps: '28 February 2026' (after the input form) and 'August 23, 2024' (at the bottom)
- **Heading the quote sits under:** Incomes → '8. pwages and swages'
- **URL:** https://taxsim.nber.org/taxsimtest/
- **Applies to:** Spousal wage input. The page says swages must be zero for non-joint returns, which includes mstat=6
- **Extraction:** raw HTML, quoted in a code fence

> ```text
> <b>8. pwages</b> and <b>swages</b> Wage and salary income of Primary
> and secondary taxpayers. Note that <b>swages must be zero</b> for
> non-joint returns. Watch out for this if you use current marital
> status and last year's income, which will happen in survey data.
> ```

- **Document:** NBER, *Internet TAXSIM Test Version*
- **Currency / version:** fetched 2026-09-24. The page prints two different 'Date last modified' stamps: '28 February 2026' (after the input form) and 'August 23, 2024' (at the bottom)
- **Heading the quote sits under:** Instructions → state separate filing (one paragraph)
- **URL:** https://taxsim.nber.org/taxsimtest/
- **Applies to:** State-level optional separate filing for husbands and wives, as the page describes it. The paragraph does not mention federal MFS or mstat=6
- **Extraction:** raw HTML, quoted in a code fence

> ```text
> <p> A number of states allow optional separate filing for
> husbands and wives. The tax calculator tries both options
> and selects the lower tax. If separate filing is chosen
> non-wage income and deductions are split equally.
> ```

- **Document:** NBER, *Internet TAXSIM Test Version*
- **Currency / version:** fetched 2026-09-24. The page prints two different 'Date last modified' stamps: '28 February 2026' (after the input form) and 'August 23, 2024' (at the bottom)
- **Heading the quote sits under:** File Uploads → list of common errors
- **URL:** https://taxsim.nber.org/taxsimtest/
- **Applies to:** Input validation
- **Extraction:** raw HTML, quoted in a code fence

> ```text
> following common errors:</p>
> 
> 
> 
> <UL>
> <LI>      missing value codes (na, dot, -9, etc)
> <LI>      out of range state id
> <LI>      asterisks
> <li>      value labels anywhere in the input data
> <LI>      negative ages, wages, dependents or deductions
> <LI>      invalid year
> <li>      commas embedded in values
> <li>      tabs between values
> <li>      binary files, (.dta, .xls, .doc, etc).
> <li>      spouse income on a single return
> </ul>
> 
> <p>The tax calculator stops on any conversion error or value out of range
> and returns a range error with the case ID. </p>
> ```

- **Document:** NBER, *Internet TAXSIM Test Version*
- **Currency / version:** fetched 2026-09-24. The page prints two different 'Date last modified' stamps: '28 February 2026' (after the input form) and 'August 23, 2024' (at the bottom)
- **Heading the quote sits under:** File Uploads → the 'Show detailed intermediate calculations' radio buttons
- **URL:** https://taxsim.nber.org/taxsimtest/
- **Applies to:** The radio buttons under 'Show detailed intermediate calculations' label idtl=0 'Off', idtl=2 'On', and idtl=5 'Labeled'. The Output Results section below lists the columns added 'If detailed intermediate results are requested'
- **Extraction:** raw HTML, quoted in a code fence

> ```text
> Show detailed intermediate calculations:
> <input type="radio" name="idtl" value="0" checked>Off
> <input type="radio" name="idtl" value="2">On
> <input type="radio" name="idtl" value="5">Labeled<br>
> ```

- **Document:** NBER, *Internet TAXSIM Test Version*
- **Currency / version:** fetched 2026-09-24. The page prints two different 'Date last modified' stamps: '28 February 2026' (after the input form) and 'August 23, 2024' (at the bottom)
- **Heading the quote sits under:** ▼Output Results (the complete output column list: default 9 columns, then detailed columns)
- **URL:** https://taxsim.nber.org/taxsimtest/
- **Applies to:** Output column definitions, including fiitax, fica, tfica, v10-v29, v42-v44, niit, addmed, and actc
- **Extraction:** raw HTML, quoted in a code fence

> ```text
> <p>The 9 columns of results returned by default are:
> 
> <p><ul>
> 
> <li>taxsimid = Case ID
> 
> <li>year = Year
> 
> <li>state = State code
> 
> <li>fiitax = Federal income tax liability including capital gains rates,
> surtaxes, Maximum Tax, NIIT, AMT, Additional Medicare Tax and refundable
> and non-refundable credits including CTC, ACTC and EIC etc, but not
> including self-employment or FICA taxes. The adjustment to AGI for SE FICA
> is made.
> 
> <li>siitax = State income tax liability, also after all credits.
> 
> <li>fica = FICA (OADSI and HI, sum of employee AND employer including
> Additional Medicare Tax)
> 
> <li>frate = federal marginal rate
> <li>srate = state marginal rate
> 
> <li>ficar = FICA rate
> 
> <li> tfica = taxpayer liability for FICA.
> 
> <p>Marginal rates are with respect to wage income unless another rate is
> requested. If detailed intermediate results are requested, the following
> 35 columns of data are added:
> 
> <p>
> 
> <li>v10 = Federal AGI
> <li>v11 = UI in AGI
> <li>v12 = Social Security in AGI
> <li>v13 = Zero Bracket Amount (zero for itemizers)
> <li>v14 = Personal Exemptions
> <li>v15 = Exemption Phaseout
> <li>v16 = Deduction Phaseout
> <li>v17 = Itemized Deductions in taxable income
> <li>v18 = Federal Taxable Income
> <li>v19 = Tax on Taxable Income (no special capital gains rates)
> <li>v20 = Exemption Surtax
> <li>v21 = General Tax Credit
> <li>v22 = Child Tax Credit (as adjusted includes additional ctc)
> <li>v23 = reserved
> <li>v24 = Child Care Credit (including additional credit)
> <li>v25 = Earned Income Credit (total federal)
> <li>v26 = Income for the Alternative Minimum Tax
> <li>v27 = AMT Liability after credit for regular tax and other allowed
> credits.
> <li>v28 = Federal Income Tax Before Credits (includes special treatment of
> Capital gains, exemption surtax (1988-1996) and 15% rate phaseout
> (1988-1990) but not AMT)
> <li>v29 = FICA
> 
> <p>The next 11 columns are zeroed if no state is specified: <p>
> 
> <li>v30 = State Household Income (imputation for property tax credit)
> <li>v31 = State Rent Expense (imputation for property tax credit)
> <li>v32 = State AGI
> <li>v33 = State Exemption amount
> <li>v34 = State Standard Deduction
> <li>v35 = State Itemized Deductions
> <li>v36 = State Taxable Income
> <li>v37 = State Property Tax Credit
> <li>v38 = State Child Care Credit
> <li>v39 = State EIC
> <li>v40 = State Total Credits
> <li>v41 = State Bracket Rate
> 
> <p>More federal results:
> 
> <li>v42 = Earned Self-Employment Income for FICA
> <li>v43 = Medicare Tax on Unearned Income
> <li>v44 = Medicare Tax on Earned Income
> <li>v45 = CARES act Recovery Rebates
> 
> <p>More state results:
> 
> <li>staxbc = State tax before credits
> <li>srebate = State income tax rebates (shown only in year paid even
> if eligibility depends on prior year)
> <li>senergy = State energy/fuel tax credits
> <li>sctc = State child tax credit
> <li>sptcr = Stata property tax credit
> <li>samt = State alternative minimum tax
> 
> <p>Still more federal results:
> <li>qbid = Qualified business income deduction
> <li>niit = Medicare Net Investment Income Tax
> <li>addmed = Medicare additional earnings Tax
> <li>cares = cares rebate
> <li>actc = Additional child tax credit
> <li>cdate = date this version of Taxsim was compiled
> ```

- **Document:** NBER, *Internet TAXSIM Test Version*
- **Currency / version:** fetched 2026-09-24. The page prints two different 'Date last modified' stamps: '28 February 2026' (after the input form) and 'August 23, 2024' (at the bottom)
- **Heading the quote sits under:** ▼Random Notes
- **URL:** https://taxsim.nber.org/taxsimtest/
- **Applies to:** Married-separate filing and FICA/TFICA interpretation
- **Extraction:** raw HTML, quoted in a code fence

> ```text
> <ul> <li>Married folk do not usually file separate returns in the
> US. There is a tax penalty compared to joint filing in most cases.
> Single folk do not have income or age for a spouse. This is
> problematic in survey data, since the marital status information is
> typically current, but the income information is from the prior
> year. The solution is to either change the marital status to married
> (so the return status becomes joint) or convert the record to two
> individual returns. Otherwise taxsim will fail at the first such
> record, and subsequent records will have only missing tax data.
> ```

> ```text
> <li>The FICA estimate includes both employee and employer tax. Half of FICA is paid by the employer, so the
> variable TFICA is supplied with the employee share. The values you supply for psemp and ssemp should be
> pre-FICA while the vaues you supply for the other QBI eligible amounts should be post-FICA, consistent with
> the information returns supplied to taxpayers.
> ```

Observation (documentation text only): the page states tax law 'through December 2024' and years 'between 1960 and 2024'. It does not document 2026 law. Any 2026 behaviour of taxsimtest has to be established by running the binary, not by this page.

## 13. Computed cross-checks (arithmetic on the quotes above; these are not quotes)

| Check | Holds | Working |
|---|---|---|
| §1(j)(2)(D) statutory MFS breakpoints = ½ × §1(j)(2)(A) joint breakpoints | yes | joint [19050, 77400, 165000, 315000, 400000, 600000] / 2 = [9525.0, 38700.0, 82500.0, 157500.0, 200000.0, 300000.0]; MFS [9525, 38700, 82500, 157500, 200000, 300000] |
| §1(j)(2)(D) MFS matches §1(j)(2)(C) unmarried except the 35% bracket ceiling | yes | single [9525, 38700, 82500, 157500, 200000, 500000]; MFS [9525, 38700, 82500, 157500, 200000, 300000] |
| Rev. Proc. 2025-32 Table 4 (MFS) 2026 breakpoints = ½ × Table 1 (joint) | yes | joint [24800, 100800, 211400, 403550, 512450, 768700] / 2 = [12400.0, 50400.0, 105700.0, 201775.0, 256225.0, 384350.0]; MFS [12400, 50400, 105700, 201775, 256225, 384350] |
| 2026 Table 4 (MFS) matches Table 3 (single) except the 35% ceiling ($384,350 MFS vs $640,600 single) | yes | single [12400, 50400, 105700, 201775, 256225, 640600]; MFS [12400, 50400, 105700, 201775, 256225, 384350] |
| Table 4 base-tax column recomputed from the brackets equals the printed column (so $17,966 is right and the Oct 9 figure $17,996 was a typo) | yes | recomputed [0, 1240.0, 5800.0, 17966.0, 41024.0, 58448.0, 103291.75]; printed [0, 1240, 5800, 17966, 41024, 58448, 103291.75] |
| 2026 MFS standard deduction $16,100 = single $16,100 = ½ × joint $32,200 | yes | 32,200 / 2 = 16,100 |
| §3101(b)(2)(B) MFS Additional Medicare threshold = ½ × $250,000 = $125,000 (not indexed) | yes | 250,000 / 2 = 125,000 |
| §86(c): MFS living with spouse at any time → base amount and adjusted base amount both 0; under §86(a)(2)(B), taxable SS is capped at 85% of benefits | yes | read directly from (c)(1)(C), (c)(2)(C), (a)(2) |
| §151(d)(5)(C)(i) with (iii)(I): on a non-joint return each qualified individual's $6,000 reaches $0 at MAGI $75,000 + $6,000/0.06 = $175,000 | yes | 75,000 + 100,000 = 175,000 (applies to single/HoH; (C)(v) bars MFS entirely) |
| 2026 EITC, no children, 'all other' completed phaseout ≈ threshold + max credit / 7.65% | yes | 10,860 + 664/0.0765 = 19,539.74 (printed 19,540; difference under $1) |
| 2026 EITC, 1 child, 'all other' completed phaseout ≈ threshold + max credit / 15.98% | yes | 23,890 + 4,427/0.1598 = 51,593.38 (printed 51,593; difference under $1) |
| 2026 OASDI cap: SSA $184,500 × 6.2% = $11,439.00 (SSA page) | yes | 184,500 × 0.062 = 11,439.00 |

## 14. Textual scope flags for the adjudication (what the quoted text says and leaves open)

These flags read the quoted provisions against one another. They state no conclusion that the text does not state.

1. **Which marital-status rule each MFS-relevant provision uses:**
   - §1(d) and §1(c): 'married individual (as defined in section 7703)'.
   - §2(c): uses §7703(b) directly, 'for purposes of this part'. That is Part I of subchapter A, which holds §1's rate tables and §2(b).
   - §63(g): 'marital status shall be determined under section 7703'.
   - §86(c)(1)(C)(i): 'married … (within the meaning of section 7703)', plus a separate test that the taxpayer lived with the spouse at some point in the year.
   - §32(d)(2)(A): 'marital status shall be determined under section 7703(a)', with the §32(d)(2)(B) separated-spouse exception.
   - §3101(b)(2)(B): 'married taxpayer (as defined in section 7703)'.
   - §24(b)(2): 'marital status shall be determined under section 7703'. The operative (h)(3) amounts are keyed to 'a joint return' and 'any other case'.
   - §151(d)(5)(C)(v): 'married individual (within the meaning of section 7703)'.
   Location matters for §7703(a), which applies automatically to 'part V of subchapter B of chapter 1'. The uscode itempaths put §151 and §152 there (`/260/Subtitle A/CHAPTER 1/Subchapter B/PART V/Sec. 151`). §63 is in Subchapter B Part I, §86 in Subchapter B Part II, §1 and §2 in Subchapter A Part I, §24 and §32 in Subchapter A Part IV, and §3101 in Subtitle C, Chapter 21.
   §7703(b) applies only to 'those provisions of this title which refer to this subsection'. Whether a bare reference to 'section 7703' counts as referring to subsection (b) is not answered by the quoted text. Settle it from regulations or IRS instructions before encoding it.
2. **§63(c)(6)(A):** the MFS standard deduction is zero when 'either spouse itemizes'. None of the input variables listed on the taxsimtest page describes the other spouse's itemization choice, and the page says swages must be zero for non-joint returns.
3. **§63(f)(1)(B)/(2)(B) with §151(b):** on a separate return, the spouse's aged/blind additional amount needs a §151(b) spousal exemption to be 'allowable'. That requires the spouse to have no gross income and not be another taxpayer's dependent. §151(d)(5)(B) keeps allowability alive even though the exemption amount is zero.
4. **§63(f)(3):** the $750 base, $2,050 for 2026, is only for individuals who are 'not married and … not a surviving spouse'. An MFS filer is married, so the $600 base, $1,650 for 2026, applies. A §7703(b) filer treated as not married raises the flag-1 question.
5. **§32(d):** an MFS filer gets the EITC only through (d)(2)(B). That requires residing with 'a qualifying child of the individual' for more than half the year, and either (I) not having the same principal place of abode as the spouse during the last 6 months, or (II) having a 'decree, instrument, or agreement (other than a decree of divorce) described in section 121(d)(3)(C)' and not being a member of the same household as the spouse by year end. A married separate filer who does not reside with such a child cannot meet (d)(2)(B)(ii). Rev. Proc. 2025-32 §4.06 says filers who meet the rule use the 'all other filing statuses' phaseout rows.
6. **§24(h)(3):** the phase-out threshold is $400,000 for joint returns and $200,000 'in any other case', which covers MFS. The (b)(2)(C) $55,000 MFS amount is displaced by (h)(3) ('In lieu of the amount determined under subsection (b)(2)').
7. **§1(j)(5)(B):** the MFS capital-gains 0% ceiling is ½ of the joint amount (clause (i)(III)), and the 15% ceiling is ½ of the joint amount (clause (ii)(I)). The single 15% ceiling is a separate figure (clause (ii)(III)).

## 15. Supplementary extracts for the hand computation

Appended 2026-09-24 by `supplement.py` (run after `build.py`) because the statutory hand computation (`mfs-statutory-hand-computation.md`) needs provisions sections 1-14 do not quote: the §1(b) head-of-household imposition, the §3 tax-table rule, the §24(c) child age limit, the §26(a) credit limit, the §32(a) credit formula and §32(c) definitions, the §55/§56 minimum tax, the §151(c) dependent deduction, and Rev. Proc. 2025-32 §4.10. Same pipeline as `build.py`: `curl` of the uscode.house.gov section page, `strip_usc.py`, quotes copied programmatically from `raw/`. New raw files: `raw/s3.*`, `raw/s26.*`, `raw/s55.*`, `raw/s56.*`; each carries the page marker `currentthrough:20260918_119-111`. `verify_quotes.py` covers this section too.

### 15.1 §1(b): tax on heads of households

- **Document:** 26 U.S.C. §1(b)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §1. Tax imposed → (b) Heads of households
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1&num=0&edition=prelim
- **Applies to:** Every head of a household as defined in §2(b). §1(j)(2)(B) (section 1.3) and Rev. Proc. 2025-32 Table 2 (section 11.2) supply the 2026 table
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (b) Heads of households
>
> There is hereby imposed on the taxable income of every head of a household (as defined in section 2(b)) a tax determined in accordance with the following table:

### 15.2 §3: tax tables for individuals

- **Document:** 26 U.S.C. §3(a), (c)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §3. Tax tables for individuals → (a) Imposition of tax table tax → (1) In general; (2) Ceiling amount defined; (3); (c) Tax treated as imposed by section 1
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section3&num=0&edition=prelim
- **Applies to:** Individuals who do not itemize and whose taxable income does not exceed the Secretary's 'ceiling amount' (not less than $20,000). §3 sits in Part I of subchapter A (uscode itempath `/260/Subtitle A/CHAPTER 1/Subchapter A/PART I/Sec. 3`), so §2(c) reaches it. The 2026 tables and the 2026 ceiling amount are not quoted anywhere in this file
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (a) Imposition of tax table tax
>
> (1) In general
>
> In lieu of the tax imposed by section 1, there is hereby imposed for each taxable year on the taxable income of every individual-
>
> (A) who does not itemize his deductions for the taxable year, and
>
> (B) whose taxable income for such taxable year does not exceed the ceiling amount,
>
> a tax determined under tables, applicable to such taxable year, which shall be prescribed by the Secretary and which shall be in such form as he determines appropriate. In the table so prescribed, the amounts of the tax shall be computed on the basis of the rates prescribed by section 1.
>
> (2) Ceiling amount defined
>
> For purposes of paragraph (1), the term "ceiling amount" means, with respect to any taxpayer, the amount (not less than $20,000) determined by the Secretary for the tax rate category in which such taxpayer falls.
>
> (3) Authority to prescribe tables for taxpayers who itemize deductions
>
> The Secretary may provide that this section shall apply also for any taxable year to individuals who itemize their deductions. Any tables prescribed under the preceding sentence shall be on the basis of taxable income.

> (c) Tax treated as imposed by section 1
>
> For purposes of this title, the tax imposed by this section shall be treated as tax imposed by section 1.

### 15.3 §24(c)(1): CTC qualifying child (age limit)

- **Document:** 26 U.S.C. §24(c)(1)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §24. Child tax credit → (c) Qualifying child → (1) In general
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section24&num=0&edition=prelim
- **Applies to:** Every §24 claimant: a §152(c) qualifying child under age 17
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (c) Qualifying child
>
> For purposes of this section-
>
> (1) In general
>
> The term "qualifying child" means a qualifying child of the taxpayer (as defined in section 152(c)) who has not attained age 17.

### 15.4 §26(a)-(b): limit on nonrefundable personal credits

- **Document:** 26 U.S.C. §26(a), (b)(1), (b)(2)(A)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §26. Limitation based on tax liability; definition of tax liability → (a) Limitation based on amount of tax; (b) Regular tax liability → (1); (2)(A)
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section26&num=0&edition=prelim
- **Applies to:** Credits in subpart A of part IV of subchapter A (uscode itempath `.../PART IV/Subpart A/Sec. 26`), which includes §24 (section 9 places §24 in Part IV). §24(d)(1) measures the refundable portion against this limit
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (a) Limitation based on amount of tax
>
> The aggregate amount of credits allowed by this subpart for the taxable year shall not exceed the sum of-
>
> (1) the taxpayer's regular tax liability for the taxable year reduced by the foreign tax credit allowable under section 27, and
>
> (2) the tax imposed by section 55(a) for the taxable year.
>
> (b) Regular tax liability
>
> For purposes of this part-
>
> (1) In general
>
> The term "regular tax liability" means the tax imposed by this chapter for the taxable year.
>
> (2) Exception for certain taxes
>
> For purposes of paragraph (1), any tax imposed by any of the following provisions shall not be treated as tax imposed by this chapter:
>
> (A) section 55 (relating to minimum tax),

### 15.5 §32(a), (c)(1)(E), (c)(2)(A), (c)(3)(A): EITC formula and definitions

- **Document:** 26 U.S.C. §32(a)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §32. Earned income → (a) Allowance of credit → (1) In general; (2) Limitation
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section32&num=0&edition=prelim
- **Applies to:** Every eligible individual. The credit percentage, phaseout percentage, earned income amount and phaseout amount come from §32(b) (section 6) as adjusted by Rev. Proc. 2025-32 §4.06 (section 11.4)
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (a) Allowance of credit
>
> (1) In general
>
> In the case of an eligible individual, there shall be allowed as a credit against the tax imposed by this subtitle for the taxable year an amount equal to the credit percentage of so much of the taxpayer's earned income for the taxable year as does not exceed the earned income amount.
>
> (2) Limitation
>
> The amount of the credit allowable to a taxpayer under paragraph (1) for any taxable year shall not exceed the excess (if any) of-
>
> (A) the credit percentage of the earned income amount, over
>
> (B) the phaseout percentage of so much of the adjusted gross income (or, if greater, the earned income) of the taxpayer for the taxable year as exceeds the phaseout amount.

- **Document:** 26 U.S.C. §32(c)(1)(E), (c)(2)(A), (c)(3)(A)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §32 → (c) Definitions and special rules → (1) Eligible individual → (E) Identification number requirement; (2) Earned income → (A); (3) Qualifying child → (A) In general
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section32&num=0&edition=prelim
- **Applies to:** (1)(E): every EITC claimant; clause (ii) only 'if the individual is married'. (2)(A): the earned-income definition (wages count). (3)(A): the EITC qualifying child
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (E) Identification number requirement
>
> No credit shall be allowed under this section to an eligible individual who does not include on the return of tax for the taxable year-
>
> (i) such individual's taxpayer identification number, and
>
> (ii) if the individual is married, the taxpayer identification number of such individual's spouse.

> (2) Earned income
>
> (A) The term "earned income" means-
>
> (i) wages, salaries, tips, and other employee compensation, but only if such amounts are includible in gross income for the taxable year, plus
>
> (ii) the amount of the taxpayer's net earnings from self-employment for the taxable year (within the meaning of section 1402(a)), but such net earnings shall be determined with regard to the deduction allowed to the taxpayer by section 164(f).

> (3) Qualifying child
>
> (A) In general
>
> The term "qualifying child" means a qualifying child of the taxpayer (as defined in section 152(c), determined without regard to paragraph (1)(D) thereof and section 152(e)).

### 15.6 §55(a), (b)(1), (d)(1)-(2), (d)(4)(A): alternative minimum tax

- **Document:** 26 U.S.C. §55
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §55. Alternative minimum tax imposed → (a) General rule; (b) Tentative minimum tax → (1) Noncorporate taxpayers → (A)-(C); (d) Exemption amount → (1); (2) Phase-out of exemption amount; (4) Special rule for taxable years beginning after 2017 → (A)
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section55&num=0&edition=prelim
- **Applies to:** Noncorporate taxpayers. (b)(1)(C), (d)(1)(C), (d)(2)(C) and the last sentence of (d)(2): married individuals filing separate returns (marital status under §7703). Rev. Proc. 2025-32 §4.10 (15.9) gives the 2026 amounts
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (a) General rule
>
> There is hereby imposed (in addition to any other tax imposed by this subtitle) a tax equal to the excess (if any) of-
>
> (1) the tentative minimum tax for the taxable year, over
>
> (2) the regular tax for the taxable year plus, in the case of an applicable corporation, the tax imposed by section 59A.
>
> (b) Tentative minimum tax
>
> For purposes of this part-
>
> (1) Noncorporate taxpayers
>
> In the case of a taxpayer other than a corporation-
>
> (A) In general
>
> The tentative minimum tax for the taxable year is the sum of-
>
> (i) 26 percent of so much of the taxable excess as does not exceed $175,000, plus
>
> (ii) 28 percent of so much of the taxable excess as exceeds $175,000.
>
> The amount determined under the preceding sentence shall be reduced by the alternative minimum tax foreign tax credit for the taxable year.
>
> (B) Taxable excess
>
> For purposes of this subsection, the term "taxable excess" means so much of the alternative minimum taxable income for the taxable year as exceeds the exemption amount.
>
> (C) Married individual filing separate return
>
> In the case of a married individual filing a separate return, subparagraph (A) shall be applied by substituting 50 percent of the dollar amount otherwise applicable under clause (i) and clause (ii) thereof. For purposes of the preceding sentence, marital status shall be determined under section 7703.

> (d) Exemption amount
>
> For purposes of this section-
>
> (1) Exemption amount for taxpayers other than corporations
>
> In the case of a taxpayer other than a corporation, the term "exemption amount" means-
>
> (A) $78,750 in the case of-
>
> (i) a joint return, or
>
> (ii) a surviving spouse,
>
> (B) $50,600 in the case of an individual who-
>
> (i) is not a married individual, and
>
> (ii) is not a surviving spouse,
>
> (C) 50 percent of the dollar amount applicable under subparagraph (A) in the case of a married individual who files a separate return, and
>
> (D) $22,500 in the case of an estate or trust.
>
> For purposes of this paragraph, the term "surviving spouse" has the meaning given to such term by section 2(a), and marital status shall be determined under section 7703.
>
> (2) Phase-out of exemption amount
>
> The exemption amount of any taxpayer shall be reduced (but not below zero) by an amount equal to 25 percent of the amount by which the alternative minimum taxable income of the taxpayer exceeds-
>
> (A) $150,000 in the case of a taxpayer described in paragraph (1)(A),
>
> (B) $112,500 in the case of a taxpayer described in paragraph (1)(B), and
>
> (C) 50 percent of the dollar amount applicable under subparagraph (A) in the case of a taxpayer described in subparagraph (C) or (D) of paragraph (1).
>
> In the case of a taxpayer described in paragraph (1)(C), alternative minimum taxable income shall be increased by the lesser of (i) 25 percent of the excess of alternative minimum taxable income (determined without regard to this sentence) over the minimum amount of such income (as so determined) for which the exemption amount under paragraph (1)(C) is zero, or (ii) such exemption amount (determined without regard to this paragraph).

> (4) Special rule for taxable years beginning after 2017
>
> (A) In general
>
> In the case of any taxable year beginning after December 31, 2017-
>
> (i) paragraph (1) shall be applied-
>
> (I) by substituting "$109,400" for "$78,750" in subparagraph (A), and
>
> (II) by substituting "$70,300" for "$50,600" in subparagraph (B),
>
> (ii) paragraph (2) shall be applied-
>
> (I) by substituting "$1,000,000" for "$150,000" in subparagraph (A),
>
> (II) by substituting "50 percent of the dollar amount applicable under subparagraph (A)" for "$112,500" in subparagraph (B),
>
> (III) in the case of a taxpayer described in paragraph (1)(D), without regard to the substitution under subclause (I), and
>
> (IV) by substituting "50 percent" for "25 percent", and
>
> (iii) subsection (j) of section 59 shall not apply.

Reading note (not a quote): (d)(4)(A)(ii)(IV) substitutes '50 percent' for '25 percent' in paragraph (2), and paragraph (2) says '25 percent' twice (the phase-out rate and the MFS add-back in its last sentence). The quoted text does not say whether the substitution reaches both. The hand computation tests the MFS cases under both readings; the result is the same.

### 15.7 §56(b)(1)(D): standard deduction not allowed in computing AMTI

- **Document:** 26 U.S.C. §56(b)(1)(D)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §56. Adjustments in computing alternative minimum taxable income → (b) Adjustments applicable to individuals → (1) Limitation on deductions → (D)
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section56&num=0&edition=prelim
- **Applies to:** Individuals computing alternative minimum taxable income
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (b) Adjustments applicable to individuals
>
> In determining the amount of the alternative minimum taxable income of any taxpayer (other than a corporation), the following treatment shall apply (in lieu of the treatment applicable for purposes of computing the regular tax):

> (D) Standard deduction and deduction for personal exemptions not allowed
>
> The standard deduction under section 63(c), the deduction for personal exemptions under section 151, and the deduction under section 642(b) shall not be allowed.

### 15.8 §151(c): deduction for dependents

- **Document:** 26 U.S.C. §151(c)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §151. Allowance of deductions for personal exemptions → (c) Additional exemption for dependents
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section151&num=0&edition=prelim
- **Applies to:** Every taxpayer with a §152 dependent. §7703(b)(1) and §24(a) ask whether the taxpayer is 'entitled to' / 'allowed' this deduction; §151(d)(5)(B) (section 8) says the zero exemption amount is not taken into account for that question
- **Extraction:** `strip_usc.py` (uscode HTML statute field, tags stripped, one line per block element)

> (c) Additional exemption for dependents
>
> An exemption of the exemption amount for each individual who is a dependent (as defined in section 152) of the taxpayer for the taxable year.

### 15.9 Rev. Proc. 2025-32 §2.07 and §4.10: 2026 AMT amounts

- **Document:** IRS Rev. Proc. 2025-32 (drop version dated Oct. 17, 2025; also published at 2025-45 I.R.B. 695, Nov. 3, 2025)
- **Currency / version:** taxable years beginning in 2026
- **Heading the quote sits under:** SECTION 2. CHANGES → .07; SECTION 4. 2026 ADJUSTED ITEMS → .10 Exemption Amounts for Alternative Minimum Tax
- **URL:** https://www.irs.gov/pub/irs-drop/rp-25-32.pdf
- **Applies to:** Exemption: separate MFS row ($70,100). 28% breakpoint: separate MFS row ($122,250). Phase-out: separate MFS row ($500,000 threshold, $640,200 complete)
- **Extraction:** `pdftotext -layout` (`raw/rp-25-32.txt`)

> ```text
>    .07 Section 70107 of the OBBBA amends § 55(d)(4) to make the temporary
> 
> increases of the exemption amounts and the phaseout threshold amounts that were
> 
> effective for taxable years beginning after December 31, 2017, and before January 1,
> 
> 2026, permanent. Section 55(d)(4)(B) as amended provides that the $1,000,000
> 
> amount described in § 55(d)(4)(A)(ii)(I) is not adjusted for inflation for any taxable year
> 
> beginning before January 1, 2027.
> 
> ```

> ```text
>    .10 Exemption Amounts for Alternative Minimum Tax. For taxable years beginning in
> 
> 2026, the exemption amounts under § 55(d)(1) are:
> 
>  Filing status                                                            Exemption
>                                                                             amount
>  Joint Returns or Surviving Spouses                                        $140,200
> 
>  Unmarried Individuals (other than Surviving Spouses)                        $90,100
> 
>  Married Individuals Filing Separate Returns                                 $70,100
> 
>  Estates and Trusts                                                          $31,400
> 
> 
> 
>    For taxable years beginning in 2026, under § 55(b)(1), the excess taxable income
> 
> above which the 28 percent tax rate applies is:
> 
>  Filing status                                                        Excess taxable
>                                                                              income
> 
>  Married Individuals Filing Separate Returns                                $122,250
> 
>  All Other Taxpayers                                                        $244,500
> 
> 
> 
>    For taxable years beginning in 2026, the amounts used under § 55(d)(2) to
> 
> determine the phaseout of the exemption amounts are:
> 
>                                               17
> 
> 
>              Filing status               Threshold Phaseout        Complete Phaseout
>                                               Amount                   Amount
>  Joint Returns or Surviving Spouses                $1,000,000               $1,280,400
>  Unmarried Individuals (other than                   $500,000                 $680,200
>  Surviving Spouses)
>  Married Individuals Filing Separate                 $500,000                 $640,200
>  Returns
>  Estates and Trusts                                  $104,800                 $167,600
> 
> 
> ```



## 16. 26 USC 164(b)(6)-(7): SALT limitation, separate-return halving, and the OBBBA MAGI phasedown

- **Document:** 26 U.S.C. §164 (Taxes), paragraphs (b)(6) and (b)(7)
- **Currency / version:** US Code (uscode.house.gov, prelim edition), current through Public Law 119-111 (09/18/2026); page marker `currentthrough:20260918_119-111`
- **Heading the quote sits under:** §164. Taxes → (b) Definitions and special rules → (6) Limitation on individual deductions for taxable years 2018 through 2025; (7) Applicable limitation amount
- **URL:** https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section164&num=0&edition=prelim
- **Applies to:** individuals. (b)(6)(B) caps state and local taxes at the applicable limitation amount, halved for "a married individual filing a separate return". (b)(7)(A)(ii) sets $40,400 for 2026. (b)(7)(B)(i) reduces it by 30% of MAGI over the threshold amount (halved for a separate return); (b)(7)(B)(ii)(II) sets $505,000 for 2026; (b)(7)(B)(iii) floors the reduced amount at $10,000 before the (b)(6)(B) halving.
- **Extraction:** `strip_usc.py raw/s164.html` (fetched 2026-09-27; uscode HTML statute field, tags stripped, one line per block element). The (6) heading still reads "2018 through 2025"; the operative text is (6)(B) plus (7).

> (6) Limitation on individual deductions for taxable years 2018 through 2025
>
> In the case of an individual and a taxable year beginning after December 31, 2017,2-
>
> (A) foreign real property taxes shall not be taken into account under subsection (a)(1), and
>
> (B) the aggregate amount of taxes taken into account under paragraphs (1), (2), and (3) of subsection (a) and paragraph (5) of this subsection for any taxable year shall not exceed the applicable limitation amount (half the applicable limitation amount in the case of a married individual filing a separate return).
>
> The preceding sentence shall not apply to any foreign taxes described in subsection (a)(3) or to any taxes described in paragraph (1) and (2) of subsection (a) which are paid or accrued in carrying on a trade or business or an activity described in section 212. For purposes of subparagraph (B), an amount paid in a taxable year beginning before January 1, 2018, with respect to a State or local income tax imposed for a taxable year beginning after December 31, 2017, shall be treated as paid on the last day of the taxable year for which such tax is so imposed.
>
> (7) Applicable limitation amount
>
> (A) In general
>
> For purposes of paragraph (6), the term "applicable limitation amount" means-
>
> (i) in the case of any taxable year beginning in calendar year 2025, $40,000,
>
> (ii) in the case of any taxable year beginning in calendar year 2026, $40,400,
>
> (iii) in the case of any taxable year beginning after calendar year 2026 and before 2030, 101 percent of the dollar amount in effect under this subparagraph for taxable years beginning in the preceding calendar year, and
>
> (iv) in the case of any taxable year beginning after calendar year 2029, $10,000.
>
> (B) Phasedown based on modified adjusted gross income
>
> (i) In general
>
> Except as provided in clause (iii), in the case of any taxable year beginning before January 1, 2030, the applicable limitation amount shall be reduced by 30 percent of the excess (if any) of the taxpayer's modified adjusted gross income over the threshold amount (half the threshold amount in the case of a married individual filing a separate return).
>
> (ii) Threshold amount
>
> For purposes of this subparagraph, the term "threshold amount" means-
>
> (I) in the case of any taxable year beginning in calendar year 2025, $500,000,
>
> (II) in the case of any taxable year beginning in calendar year 2026, $505,000, and
>
> (III) in the case of any taxable year beginning after calendar year 2026, 101 percent of the dollar amount in effect under this subparagraph for taxable years beginning in the preceding calendar year.
>
> (iii) Limitation on reduction
>
> The reduction under clause (i) shall not result in the applicable limitation amount being less than $10,000.
>
> (iv) Modified adjusted gross income
>
> For purposes of this paragraph, the term "modified adjusted gross income" means adjusted gross income increased by any amount excluded from gross income under section 911, 931, or 933.

**Computed (not a quote), mfs-wages-450000, 2026:** MAGI 450,000 exceeds half the threshold (505,000 / 2 = 252,500) by 197,500; 40,400 - 0.30 x 197,500 = -18,850, floored at 10,000 by (b)(7)(B)(iii); a separate filer takes half, 5,000. State income tax above 5,000 is not deductible, and 5,000 < the 16,100 standard deduction, so the standard deduction applies.
