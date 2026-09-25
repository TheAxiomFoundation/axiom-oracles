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

## TAXSIM-format CSV population

`--population taxsim-csv` (`axiom_oracles/populations/taxsim_csv.py`) replaces
the Enhanced CPS projection with a TAXSIM-35 input file read verbatim. Its
purpose is to score PolicyEngine against TAXSIM over exactly the rows
policyengine-taxsim's own benchmark dashboard scores.

### Pointing it at the benchmark file

The September 2026 dashboard's `summary_<year>.json` metadata (2021-2025, as
published on pe-taxsim `main`) records `source: cps_households.csv` with
`sourceSha256`
`ecabc8dd33e8b570fad21650745b9d94f6b51fc9780d9c59bb033ede7d16a689`. That file
is `cps_households.csv` at pe-taxsim commit
`2b69146bfb2e16f83e1c021d72c4258d67872190` (PR #1204). pe-taxsim `main` still
holds the earlier version (sha256 `828b6740...`) with 1,155 state-0 rows, which
PR #1204 identified as Alabama tax units and recoded to state 1. Both versions
have 111,347 rows, all with `year` 2021.

```bash
git -C ~/PolicyEngine/pe-taxsim show \
  2b69146bfb2e16f83e1c021d72c4258d67872190:cps_households.csv \
  > ~/data/cps_households.csv
shasum -a 256 ~/data/cps_households.csv   # ecabc8dd...

export AXIOM_TAXSIM_CSV=~/data/cps_households.csv
uv run --extra policyengine --extra taxsim axiom-oracles compare \
  policyengine taxsim \
  --population taxsim-csv \
  --taxsim-csv-sha256 ecabc8dd33e8b570fad21650745b9d94f6b51fc9780d9c59bb033ede7d16a689 \
  --taxsim-csv-origin PolicyEngine/policyengine-taxsim@2b69146bfb2e16f83e1c021d72c4258d67872190:cps_households.csv \
  --period 2024 \
  --sample-size 100 \
  --output reports/policyengine-taxsim-cps-2024-sample100.json
```

Only `compare policyengine taxsim` (either order) accepts this population:
`TaxsimPackageRunner` and `PolicyEngineTaxsimRunner` are the runners that read
`metadata["taxsim_input"]`, and a TAXSIM row carries none of the person facts
the other adapters project from.

### What the loader guarantees

- **Rows are verbatim.** An integer-literal cell becomes an `int`, any other
  numeric cell a Python `float`, and a blank cell is left out of the row. For
  every column with a non-blank cell, the rows frame to the dtypes
  `pandas.read_csv` infers and to the values
  `pandas.read_csv(float_precision="round_trip")` parses (tested). The
  benchmark worker's plain `pd.read_csv` uses pandas' default float parser,
  which is not correctly rounded: on the September file it differs from the
  cell text in 24,611 cells, by at most 2.0e-14 relative (measured with pandas
  3.0.2), so these rows reach the engines with the file's exact values rather
  than that parser's.
- **Year override.** An explicit `--period YYYY` (or `period=` in Python)
  replaces every row's `year`, as pe-taxsim's `scripts/refresh_dashboard.py`
  does with `dict(row, year=args.year)` to run one file for 2021-2025. Without
  it, each case keeps its row's year (the TAXSIM default period of 2026 is not
  applied). The identity records both `years_in_file` and `year_override`.
- **State 0 is kept.** pe-taxsim PR #1204 describes state 0 as the code TAXSIM
  reads as "no state tax", and its `refresh_dashboard.py` rejects state 0 for
  that reason. This loader does not reject or remap it: a state-0 row runs as
  written, its case scope is `country: US` (locale `US`), and it appears only
  when the load scope is national. States 1-51 map through the SOI crosswalk
  in `adapters/taxsim/projection.py` to a `census_state` scope and a
  `US-<USPS>` locale. Any other state code, or a blank state cell, fails the
  load.
- **Fail closed.** Unknown column names (outside the TAXSIM-35 input set copied
  from policyengine-taxsim's `api.py` `KNOWN_COLUMNS` plus `TaxsimRunner`'s
  `opt1`/`opt1v`), duplicate header names, a repeated or non-integer
  `taxsimid`, ragged rows, non-numeric or non-finite cells (`NA`, `nan`,
  `inf`), and non-UTF-8 bytes all raise. `--taxsim-csv-allow-unknown-columns`
  admits extra columns and records them as `unknown_columns`.
- **sha256 first.** The file is read once and hashed over the same bytes that
  are parsed; `--taxsim-csv-sha256` is compared before any row is parsed.

### Cases

| Field | Value |
| --- | --- |
| `case_id` | `taxsim-<taxsimid>` |
| `period` | the row's (possibly overridden) year |
| `metadata["taxsim_input"]` | the verbatim row |
| `metadata["selector_facts"]` | `taxsim_state`, `state` (USPS or `null` for 0), `year`, `mstat`, `page`, `sage`, `depx`, `idtl` (`null` when blank) |
| `metadata["scope"]` / `locale` | `census_state` + `US-<USPS>`, or `country: US` + `US` for state 0 |
| `metadata["source_row"]` | 1-based data-row position in the file |
| weight | none: report weighted totals equal case counts |

`--sample-size N` (default 50, `0` for all) keeps the N in-scope rows whose
`sha256("0:<taxsimid>")` digests sort lowest, in file order. The choice
depends only on the ids, not on file order or Python version.
`--jurisdiction-fips` narrows the load to one state.

### Provenance

The CLI report gains a top-level `dataset_identity` block: `source`
(`taxsim-csv`), `path` (`$HOME`-relative when under home), `filename`, the full
64-hex `sha256`, `bytes`, `rows`, `columns`, `years_in_file`, `year_override`,
`state_counts` (SOI code to row count, `"0"` included), `origin` when
`--taxsim-csv-origin REPO@COMMIT:PATH` is given, and `selection` (load scope,
rows in scope, sample size/seed/method, cases). A `scripts/run_comparison.py`
suite opts in with:

```yaml
runner:
  type: axiom-oracles-compare
  parameters:
    left: policyengine
    right: taxsim
    population: taxsim-csv
    period: "2024"          # omit to keep each row's year
    taxsim_csv:
      path: $HOME/data/cps_households.csv
      sha256: ecabc8dd33e8b570fad21650745b9d94f6b51fc9780d9c59bb033ede7d16a689
      origin:
        repo: PolicyEngine/policyengine-taxsim
        commit: 2b69146bfb2e16f83e1c021d72c4258d67872190
        path: cps_households.csv
```

`sha256` is required there, and the whole identity is stamped as
`provenance.dataset`.

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
