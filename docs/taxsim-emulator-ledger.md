# PolicyEngine TAXSIM emulator ledger

This manual lane replays the five paired household result files in
[PolicyEngine/policyengine-taxsim release full-ecps-comparison-run-35953332152](https://github.com/PolicyEngine/policyengine-taxsim/releases/tag/full-ecps-comparison-run-35953332152).
It compares recorded PolicyEngine emulator outputs (left) with recorded TAXSIM
outputs (right), over all 111,347 tax units in each year, 2021–2025. Replaying
these records runs neither PolicyEngine nor a TAXSIM executable.

The reports are observations of engine outputs. They provide no independent
legal adjudication. Part B will add dispositions; this change seeds none.
All suites have `ci: manual`, pending Max's decision d229 about publication.
They have no `dashboard` entry, and are absent from the published manifest and
overview. The unexplained ratchet currently gates published dashboard reports
with an Axiom side; these manual PE/TAXSIM reports require no ratchet ceilings.
`scripts/apply_dispositions.py --check` discovers their explicit artifact paths.

## Inputs and regeneration

Use the pinned source bytes, rather than the current checkout's CSV:

```sh
mkdir -p data/.cache/taxsim-emulator
export AXIOM_TAXSIM_CSV="$PWD/data/.cache/taxsim-emulator/cps_households.csv"
git -C <pe-taxsim> show 2b69146bfb2e16f83e1c021d72c4258d67872190:cps_households.csv > "$AXIOM_TAXSIM_CSV"
export AXIOM_TAXSIM_RECORDED_RELEASE="$PWD/data/.cache/taxsim-emulator/full-ecps-comparison-run-35953332152"
uv run axiom-oracles taxsim fetch-release \
  --repo PolicyEngine/policyengine-taxsim \
  --tag full-ecps-comparison-run-35953332152 \
  --dir "$AXIOM_TAXSIM_RECORDED_RELEASE"
for year in 2021 2022 2023 2024 2025; do
  uv run scripts/run_comparison.py "taxsim-emulator-ecps-$year" --summary
done
uv run scripts/apply_dispositions.py --check
uv run scripts/unexplained_ratchet.py --check
```

The source SHA-256 is
`ecabc8dd33e8b570fad21650745b9d94f6b51fc9780d9c59bb033ede7d16a689`.
The fetch command downloads each `comparison_results_<year>.csv` and
`provenance_<year>.json` from the GitHub release asset URLs, checking built-in
hashes before storing bytes. Unknown release tags have no implicit trusted pin.
The suite pins each year's CSV independently.

Direct replay uses `axiom-oracles compare policyengine taxsim` with
`--population taxsim-csv`, `--taxsim-csv PATH`, `--taxsim-csv-sha256 HEX`,
`--taxsim-csv-origin REPO@COMMIT:PATH`, `--period YEAR`, `--sample-size 0`,
`--recorded-release DIR`, `--recorded-release-repo REPO`,
`--recorded-release-tag TAG`, and `--recorded-release-sha256 HEX`.
The last hash may be omitted only for the built-in release. Select both
`--concept us:tax/federal-income-tax#liability` and
`--concept us:tax/state-income-tax#liability`, with `--tolerance 15` and
`--relative-tolerance 0`. Repeat `--row-aux-output NAME` for auxiliary outputs.
A partial population fails against a full release, including a sample or shard.

The registry's `runner.parameters.recorded_release` mapping accepts `repo`,
`tag`, exactly one of `path_env` or `path`, and `sha256_by_year`.
Other suite keys are `taxsim_csv`, `taxsim_pin_profile`, `period`, `concepts`,
`tolerance`, `relative_tolerance`, `row_aux_outputs`, and
`report_include_cases: false`.
`artifacts.report_path` gives a stable path under `reports/`; such suites cannot
also publish to a dashboard. `report_basename` remains the registry label.

## Checks and evidence

The loader rejects CSV bytes that disagree with either the suite hash or
provenance `outputSha256`, and rejects a provenance `sourceSha256` that differs
from the population identity. It compares every input cell on both sources
with the case's `taxsim_input`, after the population year override. Only
numeric float parsing differences up to 1e-9 relative are accepted (zero
absolute tolerance). Duplicate, missing, and extra rows fail with counts;
each source must cover exactly the loaded case IDs. Junk header stamp columns
are ignored, while known output columns are retained.

For every TAXSIM row it resolves the binary using state, year, platform
`linux`, and the suite pin profile. It checks the per-row SHA, falling back to
provenance `taxsimFallback` where applicable or `taxsimBinarySha256` otherwise.
The `dashboard-2026-09` profile uses the September Linux binary except for
GA/MD 2024–2025, which resolve to the pinned August binary. Identity describes
these recorded Linux runs even when replay happens on macOS.

`engine_identity.taxsim` records SHA, platform, pinned build, null
`build_observed`, row counts and default/override scope. `recorded_release`
records repo, tag, file, SHA, provenance file/hash, and the full provenance.
`engine_identity.policyengine` carries the emulator commit, package versions,
runner flags, and other emulator provenance. The registry propagates these
identities into `provenance.oracle`, including `taxsim_binaries`.

`reports/taxsim-emulator/taxsim-emulator-ecps-<year>.json.gz` is deterministic
gzip (zero timestamp) containing compact `axiom.comparison_report.v2` JSON.
It retains every mismatch, aggregates, counts, input dataset identity and
engine identities. It omits the redundant `cases` array and explicitly marks
`case_rows_omitted`; the full case set was validated before comparison.
`apply_dispositions.py` and `bind_dispositions.py` read these compressed files.
The former can also update them without changing the compression format.

Mismatch `aux.left` and `aux.right` retain configured raw output values.
These suites request `niit`, `addmed`, `srebate`, `staxbc`, `fica`, `tfica`,
`sctc`, `samt`, `qbid`, `actc`, `senergy`, `sptcr`, and every `v10`–`v41` column.
`v32` is state AGI and `v36` state taxable income, as documented in the
[idtl=2 output table](https://github.com/PolicyEngine/policyengine-taxsim/blob/a80b8c1dca088b147e36f9c770ed92d403d747f6/README.md)
and `policyengine_taxsim/config/variable_mappings.yaml` at that same commit.
Dispositions may use `left_aux.niit` or `right_aux.srebate` (and other names)
in `row_arithmetic` expressions or structured `match` predicates. No function
calls or arbitrary attribute access are allowed. Aux is part of population
binding row digests when present; existing rows without aux retain their
original digests. Tests verify the three existing TAXSIM assignment bindings.

## Raw match rates

The comparator uses `math.isclose`; these suites explicitly set its relative
tolerance to zero, so agreement means `abs(PE - TAXSIM) <= 15`. Other suites'
mappings are unchanged. This matches `match_flags` in
[`scripts/refresh_dashboard.py`](https://github.com/PolicyEngine/policyengine-taxsim/blob/9538f802068ffd81d3b039722069e9dde3350f01/scripts/refresh_dashboard.py).
The recorded adapter maps emulator `fiitax` to `income_tax`, and `siitax` to
`state_income_tax`, through the existing canonical concept mappings.

| Year | Federal raw match | State raw match | Federal mismatches | State mismatches |
| --- | ---: | ---: | ---: | ---: |
| 2021 | 78.82% | 72.15% | 23,586 | 31,014 |
| 2022 | 81.15% | 76.51% | 20,992 | 26,156 |
| 2023 | 81.11% | 83.78% | 21,036 | 18,065 |
| 2024 | 83.81% | 85.05% | 18,025 | 16,643 |
| 2025 | 82.96% | 85.95% | 18,975 | 15,649 |

`tests/fixtures/taxsim_emulator_dashboard.json` vendors the ten one-decimal
headline rates with their source paths and pe-taxsim commit
`a80b8c1dca088b147e36f9c770ed92d403d747f6`. Differential tests compare every report
with those independent dashboard numbers and check persisted mismatch counts.
Property tests mutate input cells, output bytes and binary SHAs, vary row
order, and check result ID conservation.

## Live probes

These commands require the optional emulator package and verified binaries:

```sh
uv sync --extra taxsim --extra dev
uv run axiom-oracles taxsim fetch-binaries --profile dashboard-2026-09 --platform current
uv run axiom-oracles taxsim fetch-binaries --profile september-2026-09-no-fallback --platform current
uv run scripts/run_comparison.py taxsim-emulator-probes --summary
uv run scripts/run_comparison.py taxsim-crash-probes-2024 --summary
uv run scripts/run_comparison.py taxsim-crash-probes-2025 --summary
```

The emulator probe has exactly two MFJ itemizers for 2024, ages 45/45, $300,000
primary wages, $3,000 property tax, $30,000 mortgage interest, states 0 and 44.
The inputs come from the local Git version of PR #1204's
`tests/test_state_zero_salt.py` (commit
`200b9b3e2c3a087a2750bf0f5ffafc3369883f59`); GitHub access was unavailable here.
The Maryland crash fixtures preserve both input records and their order from
commit `3a58992ad6330920a1dc93bc6d83efe5de954d13`, files
`tests/fixtures/maryland_taxsim_crash/pension-only-2024.csv` and `-2025.csv`.
The no-fallback profile resolves September binaries everywhere.

The `taxsim-pin` CI job runs the probes on Linux, prints the actual outcome,
checks ID conservation and crash-to-engine_error propagation, and uploads the
reports. It checks both normal isolation and zero-rerun behavior, since a
batch crash can recover after bisection. Linux numeric/crash outcomes have not
been observed in this macOS workspace; CI does not assume the upstream claim.

Observed locally on macOS (`darwin`, arm64 host; pinned executable x86-64):

| Probe | TAXSIM fiitax | Emulator fiitax | TAXSIM / emulator siitax |
| --- | ---: | ---: | ---: |
| 2024 MFJ, state 0 | 50,165.00 | 49,315.8515625 | 0 / 0 |
| 2024 MFJ, Texas 44 | 49,618.30 | 49,315.8515625 | 0 / 0 |

This reproduces the two quoted TAXSIM values and the state-0 native-SALT
emulator amount to cents. The live environment was `policyengine-taxsim`
2.31.7, PolicyEngine-US 2.15.1 and Core 3.32.7 (different from the recorded
release's US 2.6.17 / Core 3.32.6). Runner options were native SALT,
`assume_w2_wages=False`, and `idtl=2`. Only these two records ran through
PolicyEngine; the `disable_salt` assertion was not tested. The September
macOS pin is `02286e`-prefixed, build `cd2026090910`; the full SHA is in the
probe report.

Both 2024 and 2025 crash fixtures returned zero federal and state liability
for both records under the August reference and September macOS binaries.
Neither normal isolation nor zero-rerun execution crashed. Direct binary runs
returned exit 0 with an IEEE_DENORMAL floating-point note on stderr. This is
an observation of macOS, not a prediction of Linux. The three live reports
are uncompressed JSON alongside the five recorded gzip reports.

Local environment note: normal `uv sync --extra taxsim --extra dev` could
not fetch an uncached locked dependency under the network sandbox. The
Hypothesis lock update was verified with `uv lock --offline` and
`uv lock --check --offline`; tests and probes used packages installed from
the existing offline cache with `uv run --no-sync`. Consequently local
probe versions above are explicitly recorded rather than attributed to the
locked environment. CI uses the ordinary locked sync and records its own
observations.
