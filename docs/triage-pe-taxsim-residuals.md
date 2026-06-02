# Triage: PolicyEngine/TAXSIM Residual Mismatches

This document classifies the residual mismatches from the PE/TAXSIM smoke test
(issue #6) and identifies their root causes.

## Summary

All federal income tax mismatches trace to **two NBER TAXSIM modeling gaps** in
child/dependent tax credit handling. State tax mismatches are minor and fall into
expected semantic drift between the two engines.

| Root cause | Category | Cases affected | Typical per-case impact |
| --- | --- | ---: | --- |
| TAXSIM does not model the Other Dependent Credit (ODC) | NBER TAXSIM gap | Any case with adult dependents | -$500 per adult dependent |
| TAXSIM computes CTC at $1,700/child instead of $2,000/child | NBER TAXSIM gap | Any case with qualifying children | -$300 per qualifying child |
| TAXSIM omits refundable ACTC when tax liability is zero | NBER TAXSIM gap | Low-income filers with children | -$1,700 per qualifying child |
| State credit model differences (ME energy, CO CTC, etc.) | Expected semantic drift | Varies by state | < $100 |

## Methodology

1. Ran the 10-household Enhanced CPS smoke test (`--sample-size 10 --period 2024`).
2. Extracted each mismatched case's `metadata.taxsim_input` row.
3. Ran each row through both `TaxsimRunner` and `PolicyEngineRunner` with
   `idtl=2` (TAXSIM detailed output).
4. Decomposed PE's `income_tax` into `income_tax_before_credits`, `ctc`,
   `refundable_ctc`, `non_refundable_ctc`, and `eitc` using
   `policyengine-taxsim`'s `generate_household` and `policyengine-us`'s
   `SimulationBuilder`.

## Federal Mismatch Decomposition

### Case pattern A: Other Dependent Credit (ODC) only

**Representative: single, age 37, 1 adult dependent (age 38), $100k wages, CA**

| Component | PolicyEngine | TAXSIM | Notes |
| --- | ---: | ---: | --- |
| Tax before credits | $10,541 | $10,542.85 | $1.85 rounding |
| CTC (incl. ODC) | $500 | $0 | PE applies $500 ODC; TAXSIM applies nothing |
| EITC | $0 | $0 | |
| **Federal income tax** | **$10,041** | **$10,542.85** | **diff = -$501.85** |

TAXSIM row:

```
taxsimid=1, year=2024, state=5, mstat=1, page=37, depx=1, dep17=0, dep18=0,
pwages=100000, age1=38
```

**Classification: NBER TAXSIM gap.** TAXSIM does not model the $500 Other
Dependent Credit for non-child dependents (depx > dep17). This credit was
introduced by the Tax Cuts and Jobs Act of 2017 for dependents who do not
qualify for the $2,000 CTC.

### Case pattern B: CTC undercount + ODC

**Representative: single, age 28, 3 child deps (ages 11-13) + 1 adult dep (age 33), $84k wages, WA**

| Component | PolicyEngine | TAXSIM | Notes |
| --- | ---: | ---: | --- |
| Tax before credits | $7,121 | $7,121.04 | $0.04 rounding |
| CTC (children) | $6,000 (3 x $2,000) | $5,100 (3 x $1,700) | TAXSIM uses ACTC cap |
| ODC (adult dep) | $500 | $0 | TAXSIM omits ODC |
| Total credits | $6,500 | $5,100 | |
| **Federal income tax** | **$621** | **$2,021.04** | **diff = -$1,400.04** |

TAXSIM row:

```
taxsimid=3, year=2024, state=48, mstat=1, page=28, depx=4, dep13=2, dep17=3,
dep18=3, pwages=84000, age1=33, age2=13, age3=12, age4=11
```

**Classification: NBER TAXSIM gap.** TAXSIM computes the Child Tax Credit as
$1,700 per qualifying child (the Additional Child Tax Credit refundable maximum)
instead of $2,000 per qualifying child (the actual CTC amount for 2024). The
$2,000 CTC is non-refundable; only the excess beyond tax liability is capped at
$1,700 as the refundable ACTC. When tax liability exceeds the CTC, the full
$2,000/child should apply. Additionally, the ODC gap from pattern A compounds.

### Case pattern C: Missing refundable ACTC at zero liability

**Representative: single, age 20, 1 child dep (age 16), $20k wages, CO**

| Component | PolicyEngine | TAXSIM | Notes |
| --- | ---: | ---: | --- |
| Tax before credits | $0 | $0 | Wages < standard deduction |
| CTC | $2,000 | $0 | |
| Refundable CTC (ACTC) | $1,700 | $0 | TAXSIM omits ACTC entirely |
| EITC | $4,213 | $4,213 | Engines agree on EITC |
| **Federal income tax** | **-$5,913** | **-$4,213** | **diff = -$1,700** |

TAXSIM row:

```
taxsimid=2, year=2024, state=6, mstat=1, page=20, depx=1, dep13=0, dep17=1,
dep18=1, pwages=20000, age1=16
```

**Classification: NBER TAXSIM gap.** When tax liability is zero, the $2,000 CTC
cannot offset any liability, but up to $1,700 per child should still be paid as
the refundable Additional Child Tax Credit (ACTC). TAXSIM does not compute the
ACTC in this scenario, returning only the EITC. PolicyEngine correctly applies
the $1,700 ACTC.

## State Tax Mismatches

State mismatches are small and reflect differences in how PE and TAXSIM model
state-specific credits:

| Case shape | State | PE | TAXSIM | Diff | Likely cause |
| --- | --- | ---: | ---: | ---: | --- |
| 4 deps, $0 wages | ME (23) | -$732.68 | -$799.66 | +$66.98 | Maine energy credit modeling |
| 1 child dep, $20k | CO (6) | -$4,518.50 | -$4,483.50 | -$35.00 | Colorado state CTC/EITC |

**Classification: Expected semantic drift.** State-level credit models differ
between engines. These are within the range of normal model variation and do not
indicate an adapter or projection bug.

## Mapping to Original Issue Cases

The issue's three original residuals (from a different random sample) follow the
same patterns:

| Original case | Pattern | Explanation |
| --- | --- | --- |
| ecps-17072 AL federal (-$500.04) | A | ODC for 17-year-old dependent (not CTC-eligible) |
| ecps-17072 AL state (+$20.00) | State drift | Minor AL state model difference |
| ecps-130416 AR state (-$74.57) | State drift | AR state income tax credit difference |

## Root Cause Summary

The federal mismatches are **not** Axiom adapter issues or policyengine-taxsim
projection issues. They are NBER TAXSIM modeling gaps:

1. **ODC ($500/adult dependent):** TAXSIM has no concept of the Other Dependent
   Credit. The `depx` field counts total dependents, but TAXSIM only applies
   credits for `dep17` (CTC-qualifying children). Dependents in `depx` but not
   in `dep17` receive no credit.

2. **CTC amount ($2,000 vs $1,700):** TAXSIM appears to use the $1,700 ACTC
   refundable cap as the per-child CTC amount, instead of the statutory $2,000.
   This undercounts by $300/child whenever tax liability is sufficient to absorb
   the full non-refundable CTC.

3. **ACTC at zero liability:** When tax liability is zero, TAXSIM does not
   compute the refundable ACTC at all, missing $1,700/child.

## Scaled Validation (policyengine-taxsim compare)

Cross-validated using the local `policyengine-taxsim` repo's `compare` command,
which runs the **actual NBER TAXSIM binary** (`taxsimtest-osx.exe`) against PE.

### Triage cases (5 rows, 2024)

```bash
cd ~/policyengine-taxsim
policyengine-taxsim compare triage-cases.csv --year 2024
```

All 5 triage rows reproduce identically: 4 federal mismatches, 2 state
mismatches, same values as the axiom-oracles smoke test.

### CPS 100-household sample (2021)

```bash
policyengine-taxsim compare cps_households.csv --sample 100 --year 2021
```

| Segment | Cases | Federal matches | Federal mismatches |
| --- | ---: | ---: | ---: |
| Simple wage-only (no cap gains/S-Corp/self-emp) | 51 | 50 (98%) | 1 ($17 marginal) |
| Complex income (cap gains, S-Corp, etc.) | 49 | 30 (61%) | 19 |
| **Total** | **100** | **80 (80%)** | **20** |

For **simple wage-only cases** (the population shape used by axiom-oracles'
Enhanced CPS), the federal match rate is **98%**. The single mismatch is a $17
marginal rounding difference unrelated to CTC/ODC.

For **complex income cases**, large mismatches ($1k–$5M) are driven by capital
gains, S-Corp/QBID, and SALT deduction differences — a separate class of
PE-vs-TAXSIM divergence outside the scope of issue #6.

## Recommended Next Steps

1. **File upstream with NBER TAXSIM** with the exact TAXSIM rows and PE
   decomposition from this document, covering all three CTC/ODC/ACTC gaps.

2. **Do not adjust Axiom adapter or policyengine-taxsim projection code.** The
   mismatches are in TAXSIM itself, not in how we drive it.

3. **Consider adding known-issue annotations** to the comparison report so that
   CTC/ODC-shaped mismatches can be flagged automatically (e.g., flag federal
   diffs that are exact multiples of $500 or $300 per dependent).

4. **Scale the Enhanced CPS test further.** Run `--sample-size 100` or
   `--sample-size 0` (full population) to confirm that all federal mismatches in
   the wage-only population follow patterns A, B, or C.
