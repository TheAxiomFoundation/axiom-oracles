# PolicyEngine/TAXSIM Validation

This page documents how `axiom-oracles` compares PolicyEngine against TAXSIM,
how to reproduce the current smoke test, and how to triage residual mismatches.

## Comparison Path

PolicyEngine/TAXSIM comparisons intentionally drive both engines from the same
TAXSIM-format input row.

```text
Enhanced CPS Case
        |
        v
TAXSIM row in metadata["taxsim_input"]
        |
        +-- TaxsimPackageRunner -> TAXSIM fiitax / siitax
        |
        +-- PolicyEngineTaxsimRunner -> PolicyEngine income_tax / state_income_tax
```

The important adapter boundary is the attached TAXSIM row. If PolicyEngine were
run directly from the thin Axiom case while TAXSIM ran from a projected row, the
engines could receive different tax units, dependent wages, and state inputs.
`PolicyEngineTaxsimRunner` avoids that by using policyengine-taxsim's
PolicyEngine runner whenever the CLI compares `policyengine` to `taxsim`.

## State Codes

TAXSIM state codes are not FIPS state codes. The TAXSIM projection converts from
USPS/FIPS geography into TAXSIM/SOI state numbers before calling
policyengine-taxsim.

Examples:

| State | FIPS | TAXSIM/SOI |
| --- | ---: | ---: |
| CA | 6 | 5 |
| NY | 36 | 33 |
| TX | 48 | 44 |
| WA | 53 | 48 |

This distinction matters. Passing FIPS codes to TAXSIM can silently compare
different states.

## Concept Mapping

The default `policyengine taxsim` comparison uses the mapped tax concept
intersection from `axiom_oracles/config/concept_mappings.yaml`:

| Canonical concept | PolicyEngine | TAXSIM | Tolerance |
| --- | --- | --- | ---: |
| `us:tax/federal-income-tax#liability` | `income_tax` | `fiitax` | $15 |
| `us:tax/federal-income-tax#agi` | `adjusted_gross_income` | `v10` | $5 |
| `us:tax/federal-income-tax#cdcc` | `cdcc` | `v24` | $5 |
| `us:tax/payroll#employee_fica` | employee FICA + SE tax (summed) | `tfica` | $5 |
| `us:tax/state-income-tax#liability` | `state_income_tax` | `siitax` | $15 |

## Law-Year Support Of The Pinned Binary

The pinned policyengine-taxsim 2.30.0 binary (see
`axiom_oracles/adapters/taxsim/taxsim_pins.json`; `cdate-20260521`) accepts
law years through 2026, and TAXSIM comparisons now default to the 2026
validation year (`TAXSIM_DEFAULT_PERIOD` in `axiom_oracles/cli.py`). Scope of
its 2026 model, verified empirically against the binary:

- **Modeled at 2026**: the OBBBA federal rate schedule and standard
  deduction, childless EITC, FICA/SECA (`tfica`), AGI (`v10`).
- **Missing at 2026** (fine at 2024/2025): the qualifying-child credit
  machinery. The CTC collapses to the $500 ODC path, and ACTC, CDCC, and
  EITC-with-children all return zero. 2025 models all of them, including the
  OBBBA $2,200/child CTC. A 2026 comparison of child-credit concepts must
  treat TAXSIM zeros as an NBER gap, not evidence.
- **Projected at 2026**: state modules extrapolate many parameters
  (fractional-dollar deductions/credits in the `idtl=2` detail) and in some
  states retain un-enacted rates (e.g. KY 4.0% vs enacted 3.5%, NC 4.25% vs
  3.99%, GA 5.19% vs 4.99%). The state income-tax liability suites
  disposition each such residual per case.

## Reproduce The Smoke Test

```bash
uv run --extra policyengine --extra taxsim axiom-oracles compare \
  policyengine taxsim \
  --period 2024 \
  --sample-size 10 \
  --output reports/policyengine-taxsim-ecps-2024-sample10.json
```

Expected result after the state-code and shared-row fixes:

```text
20 comparisons
17 matches
3 mismatches
0 errors
```

## Current Residual Mismatches

The latest 10-case Enhanced CPS smoke test leaves three mismatches:

| Case | TAXSIM state | TAXSIM input summary | Concept | PolicyEngine | TAXSIM | Difference |
| --- | ---: | --- | --- | ---: | ---: | ---: |
| `ecps-17072` | 1 (AL) | single, age 55, one dependent age 17, wages $60,000 | federal income tax | 3,741.00 | 4,241.04 | -500.04 |
| `ecps-17072` | 1 (AL) | same | state income tax | 2,368.45 | 2,348.45 | 20.00 |
| `ecps-130416` | 4 (AR) | single, age 44, no dependents, wages $15,194.62 | state income tax | 1.00 | 75.57 | -74.57 |

The AL federal mismatch appears to be the clearest substantive case:
PolicyEngine applies a $500 other-dependent credit for a 17-year-old dependent;
TAXSIM does not.

The AL state mismatch is only $20, barely above the current $15 tolerance. The
AR state mismatch is the main remaining state-tax case to inspect.

## Mismatch Triage

For each residual mismatch:

1. Reproduce the comparison report.
2. Extract the case's `metadata.taxsim_input` row.
3. Run the row through policyengine-taxsim's detailed tooling and NBER TAXSIM if
   needed.
4. Classify the mismatch as one of:
   - Axiom adapter issue,
   - policyengine-taxsim projection issue,
   - PolicyEngine tax-law/model issue,
   - expected TAXSIM/PolicyEngine semantic drift,
   - NBER TAXSIM issue/question.
5. If it is an upstream issue, file it with the exact TAXSIM row, PE output, and
   any decomposition showing the responsible credit or tax component.
6. Once residuals are classified, scale beyond the 10-household smoke test and
   summarize mismatches by state, tax concept, and case shape.

## Useful Extraction Snippet

```bash
uv run python - <<'PY'
import json
from pathlib import Path

report = json.loads(
    Path("reports/policyengine-taxsim-ecps-2024-sample10.json").read_text()
)
for case in report["cases"]:
    if not case["mismatches"]:
        continue
    print(case["case_id"])
    print(case["metadata"]["taxsim_input"])
    for mismatch in case["mismatches"]:
        print(mismatch)
    print()
PY
```

## Code Paths

- `axiom_oracles/adapters/taxsim/projection.py`
  projects thin Axiom cases into TAXSIM rows.
- `axiom_oracles/adapters/taxsim/runner.py`
  wraps policyengine-taxsim's TAXSIM runner.
- `axiom_oracles/adapters/policyengine/taxsim_runner.py`
  wraps policyengine-taxsim's PolicyEngine runner so PE is driven from the same
  TAXSIM row.
- `axiom_oracles/cli.py`
  automatically uses `PolicyEngineTaxsimRunner` for
  `compare policyengine taxsim`.
- `axiom_oracles/config/concept_mappings.yaml`
  defines the PE/TAXSIM concept mapping and tolerances.

## Verification

Before changing this path, run:

```bash
uv run ruff check .
uv run pytest -q
uv build
uv run --extra policyengine --extra taxsim axiom-oracles compare \
  policyengine taxsim \
  --period 2024 \
  --sample-size 10 \
  --output reports/policyengine-taxsim-ecps-2024-sample10.json
```
