# PolicyEngine TAXSIM emulator ledger

This manual lane replays the five paired household result files in
[PolicyEngine/policyengine-taxsim release full-ecps-comparison-run-35953332152](https://github.com/PolicyEngine/policyengine-taxsim/releases/tag/full-ecps-comparison-run-35953332152).
It compares recorded PolicyEngine emulator outputs (left) with recorded TAXSIM
outputs (right), over all 111,347 tax units in each year, 2021–2025. Replaying
these records runs neither PolicyEngine nor a TAXSIM executable.

The reports are observations of engine outputs. They provide no independent
legal adjudication. The bound ledger below separates documented conventions,
acknowledged engine errors, and explicitly unexplained mechanisms.
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
uv run scripts/build_taxsim_emulator_dispositions.py
for year in 2021 2022 2023 2024 2025; do
  uv run scripts/bind_dispositions.py "taxsim-emulator-ecps-$year"
done
uv run scripts/bind_dispositions.py taxsim-emulator-probes
uv run scripts/apply_dispositions.py
uv run scripts/apply_dispositions.py --check
uv run scripts/build_taxsim_emulator_dispositions.py --check
uv run scripts/unexplained_ratchet.py --check
```

The source SHA-256 is
`ecabc8dd33e8b570fad21650745b9d94f6b51fc9780d9c59bb033ede7d16a689`.
The fetch command downloads each `comparison_results_<year>.csv` and
`provenance_<year>.json` from the GitHub release asset URLs, checking built-in
hashes before storing bytes. Unknown release tags have no implicit trusted pin.
The suite pins each year's CSV independently.

For metadata changes on these already verified recorded reports, use:

```sh
uv run scripts/refresh_taxsim_emulator_metadata.py \
  --taxsim-csv "$AXIOM_TAXSIM_CSV" \
  --release-dir "$AXIOM_TAXSIM_RECORDED_RELEASE"
```

The refresh verifies source and release hashes, population identity, existing
row facts, binary usage, and comparison settings. It changes only selector
facts, row binary identities, and population selection metadata. It preserves
every output amount, auxiliary value, aggregate, and original run timestamp.
Use full replay for changes to outputs or comparison settings. Add `--check`
to verify metadata without writing. The ledger's first build completed a full 2021 replay as a
differential check, then used this refresh to avoid repeatedly creating and
reparsing the full runner's 350 MB staging reports. Rebuild, bind, and apply
the disposition files after either path.

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
The optional `taxsim_csv.selector_fact_columns: [scorp]` copies the raw,
signed input value into mismatch `facts.scorp` (CLI:
`--taxsim-csv-selector-fact scorp`). Missing values remain null; this does not
change engine inputs. The opt-in is recorded in dataset selection provenance.
Unconfigured populations retain their original facts and bindings.
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
Each amount mismatch also carries `taxsim_binary_sha256`, propagated from the
verified TAXSIM result. This lets a Maryland-only entry bind just the August
SHA, and a mixed-state entry bind the exact union of its rows' binaries.

`reports/taxsim-emulator/taxsim-emulator-ecps-<year>.json.gz` is deterministic
gzip (zero timestamp) containing compact `axiom.comparison_report.v2` JSON.
Applying dispositions upgrades that schema marker to `axiom.comparison_report.v2.1`.
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

The two federal probe mismatches now have individually pinned `unexplained`
entries. Their binary binding is the observed macOS SHA
`02286edad9c023b0f61d32e6aed680370ecf3e767c217bbb0289f85b64ff105d`, rather than
either Linux SHA from the recorded release.

Both 2024 and 2025 crash fixtures returned zero federal and state liability
for both records under the August reference and September macOS binaries.
Neither normal isolation nor zero-rerun execution crashed. Direct binary runs
returned exit 0 with an IEEE_DENORMAL floating-point note on stderr. This is
an observation of macOS, not a prediction of Linux. The three live reports
are uncompressed JSON alongside the five recorded gzip reports.

**TODO — Linux crash evidence:** inspect the Linux CI probe artifacts for
both isolation modes before adding an `engine_error` selector linked to
[#1214](https://github.com/PolicyEngine/policyengine-taxsim/issues/1214).
The recorded release's fallback reason and an upstream crash report are not
observations that these probe runs crashed. No speculative crash disposition
has been added.

Local environment note: normal `uv sync --extra taxsim --extra dev` could
not fetch an uncached locked dependency under the network sandbox. The
Hypothesis lock update was verified with `uv lock --offline` and
`uv lock --check --offline`; tests and probes used packages installed from
the existing offline cache with `uv run --no-sync`. Consequently local
probe versions above are explicitly recorded rather than attributed to the
locked environment. CI uses the ordinary locked sync and records its own
observations.

## Bound dispositions (2026-09-25)

`scripts/build_taxsim_emulator_dispositions.py` is the reproducible selection
recipe. It enumerates case IDs after applying the predicates below, in the
listed order, and uses the binding script's shared implementation. Running
`scripts/bind_dispositions.py <suite> --check` independently checks each file.
All entries expire on population/output or oracle drift. There are no overlaps.
Rows labeled `unexplained` remain in the unexplained denominator; attaching
an issue does not increase the explained rate.

Each year has 111,347 households and two comparisons per household. Explained
rate means `(raw matches + explained mismatches) / comparisons`; it includes
documented input/convention differences and acknowledged engine errors, not
unexplained mechanisms. The fixed count regression is
`tests/test_taxsim_emulator_dispositions.py`.

<!-- BEGIN LEDGER COUNTS -->
| Year | Comparisons | Raw match rate | Explained rate | Explained mismatches | Unexplained |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2021 | 222,694 | 75.4821% | 83.2075% | 17,204 | 37,396 |
| 2022 | 222,694 | 78.8283% | 86.5569% | 17,211 | 29,937 |
| 2023 | 222,694 | 82.4418% | 85.4401% | 6,677 | 32,424 |
| 2024 | 222,694 | 84.4324% | 90.0918% | 12,603 | 22,065 |
| 2025 | 222,694 | 84.4522% | 89.7590% | 11,818 | 22,806 |
<!-- END LEDGER COUNTS -->

The following counts use the same entry IDs in each
`taxsim-emulator-ecps-<year>` suite. A dash means no entry for that year.

| Entry ID | 2021 | 2022 | 2023 | 2024 | 2025 | Disposition / attribution |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `addmed-in-fiitax` | 539 | 478 | 506 | — | — | upstream_engine_gap / taxsim |
| `niit-scorp` | 1,793 | 1,618 | 1,784 | 9,669 | 9,127 | explained_residual / input |
| `niit-addmed-scorp` | 8,559 | 6,996 | 8,464 | — | — | unexplained / two_sided |
| `niit-no-scorp` | 83 | 84 | 84 | 1,152 | 1,003 | unexplained / two_sided |
| `niit-addmed-no-scorp` | 3,443 | 3,332 | 3,455 | — | — | unexplained / two_sided |
| `rebate-timing` | 14,872 | 15,115 | 4,387 | 2,934 | 1,261 | explained_residual / convention |
| `md-august-county-signature` | — | — | — | 739 | 742 | unexplained / two_sided |
| `al-federal-residual` | 134 | 160 | 121 | 128 | 154 | unexplained / two_sided |
| `al-state-residual` | 595 | 391 | 388 | 375 | 378 | unexplained / two_sided |
| `la-standard-deduction-omission` | — | — | — | — | 1,430 | upstream_engine_gap / taxsim |
| `la-other-state-residual` | — | — | — | — | 481 | unexplained / two_sided |

In the predicates below, `D = left - right`, `N = right_aux.niit -
left_aux.niit`, and `A = right_aux.addmed`. The release has **null emulator
AddMed output on every federal mismatch**. Nothing treats null as a measured
zero: the pre-2024 identity is `D + N + A`, supported by the documented
fiitax inclusion/exclusion convention. Amounts are dollars.

| Entry ID | Selector recipe and checked row arithmetic |
| --- | --- |
| `addmed-in-fiitax` | Federal, 2021–23; `abs(N) <= .005`, `abs(D + A) <= 1`; both checked on every selected row. |
| `niit-scorp` | Federal, nonzero `facts.scorp`, nonzero N, `abs(D + N) <= 1`; for 2021–23 also `A == 0`. `facts.scorp / facts.scorp == 1` checks nonzero input. |
| `niit-no-scorp` | Same NIIT identity, `facts.scorp == 0`; for 2021–23 `A == 0`. |
| `niit-addmed-scorp` | Remaining federal rows, nonzero scorp and N, `abs(D + N + A) <= 1`; mixed cause stays unexplained. |
| `niit-addmed-no-scorp` | Same combined identity on remaining federal rows with scorp zero and N nonzero. |
| `rebate-timing` | State, `abs(D + left_aux.srebate - right_aux.srebate) <= 15`. |
| `md-august-county-signature` | Maryland state, 2024–25; `abs(D + .032*(right_aux.v36-right_aux.v25)) <= 1`. |
| `al-federal-residual`, `al-state-residual` | Alabama rows left after those classes, separately by concept. No common reconciliation asserted. |
| `la-standard-deduction-omission` | Louisiana state 2025, left v34 in {12,500, 25,000}, state AGI gap within $1, `(right v36-left v36)-left v34` within $1, `D+.03*(right v36-left v36)` within $1. All four checks apply to every row. |
| `la-other-state-residual` | Remaining Louisiana state 2025 rows; no shared reconciliation asserted. |

The two `taxsim-emulator-probes` entries are `state-zero-sales-tax`
(`case_id: taxsim-77`, one row, `D = -849.1484375`) and
`texas-sales-tax-proxy` (`case_id: taxsim-78`, one row,
`D = -302.4484375000029`). Both are `unexplained / two_sided`, pin left and
right amounts, and check D within $0.000001. The constant difference checks
preserve observations; they do not prove a sales-tax mechanism.

Binary bindings use the exact selected-row union:

* Default Linux: `8aa880aeea33fd501f669d42125615e3b2a0ab19c17d93a76457e9de16615059`.
* GA/MD 2024–25 Linux fallback: `00a321d2467ba011992f8b83c6e485a9b710c48fca4262a23fec1de26942a89b`.
* The Maryland signature entries contain only the fallback SHA. Some nationwide
  NIIT/rebate entries contain both, because they actually select both populations.
* Probe entries use the macOS SHA documented above.

## Evidence and issue map

The evidence below was read from the supplied September 25 issue/comment
census, with NBER input documentation verified online. Cached comments retain
the original author, timestamp, and URL. GitHub API access failed locally;
the cached PR bodies were used for #1204, #1219, #1223 and #1199.

**S-corp input contract.** NBER's [taxsimtest input 25](https://taxsim.nber.org/taxsimtest/)
reads: “scorp Passive business income not subject to FICA, SSTB, SECA or QBID
phaseout but subject to the passive loss limitation.” Its
[taxsim35 input 31](https://taxsim.nber.org/taxsim35/) instead reads: “scorp
Active S-Corp income (is SSTB).” These are incompatible documented meanings.
Pavel Makarchuk, July 5, 2026: “This depends on what `taxsimtest` assumes about
material participation for S-corp income.” [Issue #1053](https://github.com/PolicyEngine/policyengine-taxsim/issues/1053).
`niit-scorp` records an input-contract ambiguity, not a finding that either
engine is legally right. Nonzero scorp and the NIIT identity do **not** prove
that every NIIT dollar comes from that ambiguity. Keeping this class as
explained/input is a judgment call for the lane owner to confirm; mixed
NIIT/AddMed classes remain unexplained. [Draft #1199](https://github.com/PolicyEngine/policyengine-taxsim/pull/1199)
documents regressions and is not treated as a settled correction.

**Additional Medicare.** Daniel Feenberg (`feenberg`), September 24, 2026:
“it did demonstrate an error that was present in 2000-2023. I believe I have
corrected it corrected now.” [Comment on #1225](https://github.com/PolicyEngine/policyengine-taxsim/issues/1225#issuecomment-5820033668).
This acknowledgment supports TAXSIM attribution only on the isolated AddMed
class. [PR #1239](https://github.com/PolicyEngine/policyengine-taxsim/pull/1239)
documents the emulator convention; it does not resolve the NIIT component.

**Rebate timing and sign.** Daniel Feenberg, July 6, 2026: “The production
default for 27 is zero, that selects the paid year.”
[Comment on #1068](https://github.com/PolicyEngine/policyengine-taxsim/issues/1068#issuecomment-4897009628).
Pavel Makarchuk, July 6, 2026: “PE books each rebate to the year whose
liability determines it; TAXSIM subtracts it in the payout year.”
[Convention comment](https://github.com/PolicyEngine/policyengine-taxsim/issues/1068#issuecomment-4896784506).
His description of srebate is “computed as `state_income_tax` with one-time
rebates zeroed minus actual”. [Sign comment](https://github.com/PolicyEngine/policyengine-taxsim/issues/1068#issuecomment-4897543635).
This verifies adding srebate back on each side. All 1,260 Virginia 2024 and
1,229 Virginia 2025 rows rounding to ±$200/$400 are already in `rebate-timing`;
no second Virginia selector is needed.

**NIIT without S-corp.** Feenberg, September 24, 2026: “Agreed, subtraction is
now for itemizer only.” [Comment on #1226](https://github.com/PolicyEngine/policyengine-taxsim/issues/1226#issuecomment-5823307696).
That acknowledgment concerns a narrower allocation defect. The broad
no-S-corp classes have not been shown to be the same non-itemizers, nor do
these reports contain paired Alabama/state-zero reruns. They stay unexplained.

**Maryland.** [PR #1223](https://github.com/PolicyEngine/policyengine-taxsim/pull/1223)
describes the county-tax hypothesis. The
[pinned README output table](https://github.com/PolicyEngine/policyengine-taxsim/blob/a80b8c1dca088b147e36f9c770ed92d403d747f6/README.md)
identifies v36 as state taxable income and v25 as federal EITC. The arithmetic
holds within $1 for 739/742 rows; this is a numerical signature, not an
acknowledged error or legal evidence. Direct retrieval of the
[published NBER source](https://taxsim.nber.org/out2psl/taxsim.f) failed here,
so the proposed source/build difference is not independently verified. No
Fortran is reproduced and no invented source line references are supplied.
The entries remain unexplained. Maryland has 1,310 state comparisons per
year: 281 raw matches (21.4504%) in 2024 and 284 (21.6794%) in 2025.
Streaming the full paired release gives all-Maryland median differences
of -$1,795.63 in 2024 and -$1,774.83 in 2025. Mismatch-only medians are
-$2,941.24 and -$2,922.47; those are different populations.

**Louisiana.** Feenberg, September 25, 2026: “Agreed, corrected.”
[Comment on #1222](https://github.com/PolicyEngine/policyengine-taxsim/issues/1222#issuecomment-5833721957).
This responds to the 2025 standard-deduction omission report. Combined with
the row-specific deduction/taxable-income checks, it supports TAXSIM
attribution for 1,430 rows. Of those, 548 use $12,500 and 882 use $25,000.
The raw rounded -$375/-$750 clusters contain 594/946 rows; the stricter class
does not claim every cluster member. The other 481 Louisiana rows remain
explicitly unexplained.

| pe-taxsim issue / PR | Ledger entries | Interpretation |
| --- | --- | --- |
| [#1053](https://github.com/PolicyEngine/policyengine-taxsim/issues/1053), [#1199](https://github.com/PolicyEngine/policyengine-taxsim/pull/1199) | `niit-scorp`, `niit-addmed-scorp` | Input ambiguity; mixed mechanism open. |
| [#1225](https://github.com/PolicyEngine/policyengine-taxsim/issues/1225), [#1239](https://github.com/PolicyEngine/policyengine-taxsim/pull/1239) | `addmed-in-fiitax`, `niit-addmed-*` | Acknowledged AddMed defect; mixed identity is not fully adjudicated. |
| [#1068](https://github.com/PolicyEngine/policyengine-taxsim/issues/1068), [#716](https://github.com/PolicyEngine/policyengine-taxsim/issues/716), [#1062](https://github.com/PolicyEngine/policyengine-taxsim/issues/1062) | `rebate-timing` | Documented assessment/payout-year convention; #1068 supplies quotes. |
| [#1226](https://github.com/PolicyEngine/policyengine-taxsim/issues/1226) | `niit-no-scorp`, `niit-addmed-no-scorp` | Related allocation defect; selected population not proven to share it. |
| [#1223](https://github.com/PolicyEngine/policyengine-taxsim/pull/1223) | `md-august-county-signature` | Bound county signature, legal ownership unresolved. |
| [#1204](https://github.com/PolicyEngine/policyengine-taxsim/pull/1204) | `al-federal-residual`, `al-state-residual`, both probe entries | Residual populations and observed state-zero probe. |
| [#1219](https://github.com/PolicyEngine/policyengine-taxsim/pull/1219) | Both probe entries | Related CE suppressed-state Texas proxy, not a proof of the probe mechanism. |
| [#1222](https://github.com/PolicyEngine/policyengine-taxsim/issues/1222) | `la-standard-deduction-omission`, `la-other-state-residual` | Acknowledged omission; other Louisiana mechanisms remain open. |
| [#1214](https://github.com/PolicyEngine/policyengine-taxsim/issues/1214) | None; crash-probe TODO | No observed Linux crash available to bind. |

## Remaining questions

The checked raw NIIT identities reproduce 14,417 / 12,508 / 14,293 federal
rows in 2021–23 (`D+N+A` within $1), and 10,821 / 10,130 in 2024–25
(`D+N` within $1). Nonzero NIIT gaps on nonzero-S-corp federal mismatches
number 14,797 / 14,797 / 14,788 / 14,649 / 14,712. They exceed the reconciled
classes: the other rows have additional residuals that were not forced into
an explanation.

<!-- BEGIN REMAINING CLUSTERS -->
| Year | Bound unexplained | No ledger entry | Largest unbound state/concept populations | Largest rounded dollar clusters |
| --- | ---: | ---: | --- | --- |
| 2021 | 12,814 | 24,582 | NY state 2,775; CA state 2,191; AR state 1,445 | MI +$175: 250; MT -$2,477: 234; NY +$75: 161 |
| 2022 | 10,963 | 18,974 | AR state 1,369; HI state 1,134; CA federal 791 | MI +$164: 258; WA +$700: 194; NY +$100: 156 |
| 2023 | 12,512 | 19,912 | NY state 3,688; AR state 1,358; HI state 1,177 | NY -$200: 1,425; NY -$400: 654; MI +$111: 270 |
| 2024 | 2,394 | 19,671 | AR state 1,384; SC state 1,015; HI state 939 | SC +$20: 950; OK -$22: 753; OR +$44: 435 |
| 2025 | 2,758 | 20,048 | AR state 1,389; MI state 1,129; CA federal 936 | OK -$22: 753; KS +$16: 406; OH -$19: 313 |

All listed dollar clusters are state-liability differences, rounded to the
nearest dollar for descriptive grouping only. Their selectors were not
expanded on that basis. Maryland's unbound state residuals number 290/284
in 2024/2025, after the county signature; they do not share its $1 identity.
<!-- END REMAINING CLUSTERS -->

There are still substantial clusters as well as heterogeneous residuals.
This is a seed ledger, not full closure: engine-output patterns alone do not
justify expanding the explained numerator. The lane owner should confirm
the input-ambiguity treatment of `niit-scorp`, seek the missing paired
Alabama/state-zero evidence, and obtain observed Linux crash outcomes. The
Maryland source/build hypothesis and no-S-corp allocation classes need
independent evidence before any stronger attribution.
The exact 9,847 suppressed-state CE count could not be verified in the cached
#1219 body; #1204 says approximately 9,800. Neither number is used in a ledger
selector or evidence arithmetic.
