# PolicyEngine/TAXSIM comparison

This page documents how `axiom-oracles` compares PolicyEngine against TAXSIM,
how to reproduce the current smoke test, and how to triage residual mismatches.

Disclosure: Max Ghenis is CEO of both the Axiom Foundation and PolicyEngine,
and our TAXSIM runs use the TAXSIM executable that PolicyEngine packages
(`policyengine-taxsim`, pinned in `axiom_oracles/adapters/taxsim/taxsim_pins.json`).

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

The macOS binary in the pinned policyengine-taxsim 2.30.0 release
(`taxsimtest-osx.exe`, `cdate-20260521`; see
`axiom_oracles/adapters/taxsim/taxsim_pins.json`) accepts law years through
2026, and TAXSIM comparisons now default to the 2026 validation year
(`TAXSIM_DEFAULT_PERIOD` in `axiom_oracles/cli.py`). The Linux binary in the
same release (`taxsimtest-linux.exe`) is a different build that accepts law
years 1960-2024 only, so on Linux pass `--period 2024` (see
[Platforms and binary identity](#platforms-and-binary-identity)). Scope of the
macOS binary's 2026 model, verified empirically against that binary:

- **Modeled at 2026**: the OBBBA federal rate schedule and standard
  deduction, childless EITC, FICA/SECA (`tfica`), AGI (`v10`).
- **Missing at 2026** (fine at 2024/2025): the qualifying-child credit
  machinery. The CTC collapses to the $500 ODC path, ACTC and CDCC return
  zero, and the EITC ignores qualifying children, so a family with children
  gets the childless EITC. 2025 models all of them, including the OBBBA
  $2,200/child CTC. A 2026 comparison of child-credit concepts must treat
  these TAXSIM values as an NBER gap, not evidence.
- **Projected at 2026**: state modules extrapolate many parameters
  (fractional-dollar deductions/credits in the `idtl=2` detail) and in some
  states retain un-enacted rates (e.g. KY 4.0% vs enacted 3.5%, NC 4.25% vs
  3.99%, GA 5.19% vs 4.99%). The state income-tax liability suites
  disposition each such residual per case.

## Diagnostic Lines In TAXSIM Stdout

The binary writes Fortran diagnostics to the same stdout stream as its CSV
table. In the bundled fixtures, the pinned macOS build prints six copies of
a line such as `" d2       29126       25000         103         346"`
immediately before the CSV rows of Utah (TAXSIM state 45) profiles with
$30,000 wages and primary filers aged 73, 74, and 80. The `idtl=0` fixture
places those lines before the header itself. These captures establish the
behavior for their input profiles, not an age-only trigger (fixtures in
`tests/fixtures/taxsim/`, captured 2026-09-27).

The original `fiit-taxsim-ecps` batch-13 failure and solo/complement checks
were reported on 2026-09-27; those historical inputs and captures are not
bundled here.
policyengine-taxsim's `TaxsimRunner.run()` reads the stream with
`pandas.read_csv` and coerces every column to numeric, so each diagnostic line
became a phantom row with a NaN `taxsimid` and the comparator failed with
`unexpected [nan, nan, ...]`.

`TaxsimPackageRunner` therefore uses policyengine-taxsim only to format the
input file and locate the binary, runs the binary itself, and parses stdout
with `axiom_oracles.adapters.taxsim.output.parse_taxsim_stdout`:

- duplicate normalized submitted ids are rejected before either runner path
  executes, with an error naming the id and colliding cases;
- a line is a record when it has the header's field count and a numeric first
  field; every other non-blank line is a diagnostic attributed to the record
  whose row follows it, kept on `EngineResult.raw["taxsim_stdout_diagnostics"]`
  and summarized in one `WARNING` log line per batch;
- a submitted case with no output row gets an `errors` entry naming its
  `taxsimid` (plus stderr and any trailing stdout), so it surfaces in the
  report's `errors` rows instead of vanishing;
- an output row matching no submitted case, a duplicate row, a nonzero exit,
  or trailing diagnostics that no missing case can own abort the batch with
  the offending ids or lines in the message.

These stdout and result-row checks apply to `TaxsimPackageRunner`.
`PolicyEngineTaxsimRunner` uses its own in-process result conversion.

Verbose `idtl=5` output is also accepted: each `Basic Output` record and its
`Marginal Rates` section supply the same fields as the pinned package's verbose
parser, including `state_name`. Numeric fields must be finite and complete;
records use their output IDs for the same duplicate and case-attribution checks.
Input echoes and detailed tax calculations do not become result rows. A recorded
California fixture and tests with the pinned formatter and binary cover this mode.

## Platforms and binary identity

The executables bundled in the pinned policyengine-taxsim 2.30.0 wheel are
different NBER builds. Each was run on 2026-10-10 on one-record inputs for law
years 1960, 2023-2027 (Linux builds through pe-taxsim's
`resources/taxsimtest/taxsim-docker-wrapper.sh`, the macOS build on a macOS
arm64 host); `taxsim_pins.json` records each one's build stamp, accepted range,
and the line it printed for a rejected year.

| Platform | Executable | SHA-256 | Build stamp | Law years accepted |
| --- | --- | --- | --- | --- |
| linux | `taxsimtest-linux.exe` | `0d934f20…` | `cdate-compdate` | 1960-2024 |
| darwin | `taxsimtest-osx.exe` | `0d9e43a9…` | `cdate-20260521` | 1960-2026 |
| windows | `taxsimtest-windows.exe` | `92e01169…` | `cdate-2025Aug20` (from its bytes) | not run |
| none | `taxsimtest-osx-new.exe` (a Linux ELF) | `8371718c…` | `cdate-compdate` | 1960-2026 |

The Linux build, given the `fiit-taxsim-ecps` batch-13 input (5,000 rows, law
year 2026), writes this to stdout, `STOP 1` to stderr, and exits 1:

```text
 TAXSIM: Federal tax calculator available 1960 - 2024 only.
 TAXSIM: Logical Record Number    :           0
 TAXSIM: Law Year                 :   2026.0000000000000
 ...
 TAXSIM: Abandoning processing    :          14
 TAXSIM: Taxsimtest version of    : compdate
```

(full capture: `tests/fixtures/taxsim/linux_2026_rejection_stdout.txt`). So
2025 and 2026 TAXSIM suites run only on macOS under this pin. No platform
selects `taxsimtest-osx-new.exe`; on the same batch it abandons processing at
the record with taxsimid 8 (`TAXSIM: More CTC elegible than EIC elegible`), so
it cannot stand in for the Linux build.

Every caller that runs the binary checks the requested law years against the
resolved binary's pinned range first (`pins.require_law_years`): `compare`
before it loads the population, `scripts/run_comparison.py` before it builds
the environment, `scripts/generate_state_income_tax_liability.py` and
`scripts/run_state_tax_populace.py` before any engine runs, and
`TaxsimPackageRunner` before each batch. The error names the binary, its range,
the line it printed, and the pinned binary that does accept the year. A binary
the pin does not record (other SHA-256) is not checked.

Each run records the binary it executed in the report's top-level
`engine_identity.taxsim`: path, SHA-256, size, the build stamp embedded in the
bytes (`build`) and the one the run printed (`build_observed`, the last CSV
header column or the `idtl=5` banner), host platform and machine, whether the
SHA-256 is pinned, the pinned law-year range, the installed policyengine-taxsim
version, and the rows it ran. A printed stamp that names a different build
than the hashed bytes raises `TaxsimIdentityError`. `scripts/run_comparison.py`
copies the binaries into `provenance.oracle.taxsim_binaries`, and
`scripts/merge_shard_reports.py` sums their rows across shards. Reports
generated before this existed (such as the committed
`axiom-taxsim-fiit-ecps.json`, generated 2026-08-28) do not say which binary
produced them.

### Why the pin was not moved for Linux

Newer policyengine-taxsim releases were checked on 2026-10-10 with the same
batch-13 input:

- 2.31.0 and 2.31.1 bundle Linux build `4dea6830…` (`cdate-2025Dec24`). It
  rejects 2026 the same way.
- 2.31.2 through 3.1.1 bundle Linux build `00a321d2…` and macOS build
  `4a17af9c…`, both stamped `cd2026081819`. Both accept 2026, and on batch 13
  their stdout is byte-identical.
- Against the pinned macOS build (`cdate-20260521`), that newer build differs
  on batch 13 in `siitax` for 306 of 5,000 rows, `tfica` for 289, `fiitax` for
  32 and `v10` for 21. Five 2026 probe households, with and without
  children, get the same EITC, CTC, ACTC and CDCC from both macOS builds, so
  the newer build has the same 2026 child-credit gap.

Moving the pin would therefore change the TAXSIM numbers of every suite, on
macOS as well as Linux. Choosing the benchmark's NBER build is the open
question in axiom-oracles#559, which moves the pin together with
re-baselined dispositions.

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
