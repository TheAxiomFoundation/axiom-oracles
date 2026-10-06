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

## Bound dispositions (evidence migration, 2026-09-27)

`scripts/build_taxsim_emulator_dispositions.py` is the reproducible selection
recipe. It enumerates case IDs after applying the predicates below, in the
listed order, and uses the binding script's shared implementation. Running
`scripts/bind_dispositions.py <suite> --check` independently checks each file.
All entries expire on population/output or oracle drift. There are no overlaps.
Rows labeled `unexplained` remain in the unexplained denominator; attaching
an issue does not increase the explained rate.

Explained residuals and upstream engine gaps now require an `adjudication`
reference into [`adjudications/taxsim-emulator.yaml`](../adjudications/taxsim-emulator.yaml).
The referenced record must be `evidence_ready`, cover the selected law years
and jurisdictions, and agree on attribution. Both file loading and direct
report merging re-verify the registry; every selected row is checked at merge
time. US records cover federal findings and nationwide conventions; a
state-specific record must match every selected row's state. Pending records
can be linked as hypotheses on unexplained entries.

The migration preserves every selector and binary/population binding but
withdraws 7,222 S-corp NIIT explanations: 1,511 / 1,330 / 1,491 / 1,499 /
1,391 rows in 2021–2025. The pinned section 1411 text is a current-law
snapshot; its historical applicability to those years is unproven. The one
state-zero probe formerly attributed to PolicyEngine is also unexplained:
its PR body has no qualifying maintainer comment atom. These changes are
asserted explicitly in the ledger regression tests.

Regenerate the count and remaining-cluster tables after applying dispositions
with `uv run scripts/generate_taxsim_emulator_ledger_summary.py`; `--check`
detects drift. The dashboard handoff is generated separately by
`uv run scripts/export_taxsim_dashboard_notes.py` into
[`dashboard-notes.json`](../reports/taxsim-emulator/dashboard-notes.json).
Counts in that export are mismatch rows from the bound full reports, not
households. A verified record without a bound explanation has zero affected
rows and does not explain an unclassified difference.

Each year has 111,347 households and two comparisons per household. Explained
rate means `(raw matches + explained mismatches) / comparisons`; it includes
documented input/convention differences and acknowledged engine errors, not
unexplained mechanisms. The fixed count regression is
`tests/test_taxsim_emulator_dispositions.py`.

<!-- BEGIN LEDGER COUNTS -->
| Year | Comparisons | Raw match rate | Explained rate | Explained mismatches | Unexplained |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2021 | 222,694 | 75.4821% | 82.4023% | 15,411 | 39,189 |
| 2022 | 222,694 | 78.8283% | 85.8303% | 15,593 | 31,555 |
| 2023 | 222,694 | 82.4418% | 84.6390% | 4,893 | 34,208 |
| 2024 | 222,694 | 84.4325% | 85.7500% | 2,934 | 31,734 |
| 2025 | 222,694 | 84.4522% | 85.6606% | 2,691 | 31,933 |
<!-- END LEDGER COUNTS -->

The following counts use the same entry IDs in each
`taxsim-emulator-ecps-<year>` suite. A dash means no entry for that year.

| Entry ID | 2021 | 2022 | 2023 | 2024 | 2025 | Disposition / attribution |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `addmed-in-fiitax` | 539 | 478 | 506 | — | — | upstream_engine_gap / taxsim |
| `niit-scorp` | 3 | 3 | 3 | 93 | 174 | unexplained / two_sided |
| `niit-scorp-at-cap-joint` | 1,203 | 1,188 | 1,185 | 1,184 | 1,015 | unexplained / two_sided |
| `niit-scorp-at-cap-single` | 305 | 139 | 303 | 222 | 202 | unexplained / two_sided |
| `niit-scorp-unreconciled` | 282 | 288 | 293 | 8,170 | 7,736 | unexplained / two_sided |
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
| `niit-scorp` | Federal, nonzero `facts.scorp`, nonzero N, `abs(D + N) <= 1`; for 2021–23 also `A == 0`; and `abs(N - .038*facts.scorp) <= 1`, the passive treatment's effect while neither NIIT is at the 26 U.S.C. 1411(a)(1)(B) limit. |
| `niit-scorp-at-cap-<status>` | Same NIIT identity; `facts.mstat` fixed per entry; AGI (`v10`) agrees within $1; `right_aux.niit - .038*(right_aux.v10 - threshold)` within $1 (TAXSIM at the 1411(a)(1)(B) limit, thresholds $250,000 joint, $125,000 separate, $200,000 otherwise under 1411(b)); the emulator's NIIT is below that limit and its implied net investment income plus scorp reaches it (recipe-enforced, re-derived per row in `tests/test_taxsim_emulator_dispositions.py`). |
| `niit-scorp-unreconciled` | Remaining nonzero-scorp rows with the NIIT identity where neither reconciliation holds; unexplained. |
| `niit-no-scorp` | Same NIIT identity, `facts.scorp == 0`; for 2021–23 `A == 0`. |
| `niit-addmed-scorp` | Remaining federal rows, nonzero scorp and N, `abs(D + N + A) <= 1`; mixed cause stays unexplained. |
| `niit-addmed-no-scorp` | Same combined identity on remaining federal rows with scorp zero and N nonzero. |
| `rebate-timing` | State, `abs(D + left_aux.srebate - right_aux.srebate) <= 15`. |
| `md-august-county-signature` | Maryland state, 2024–25; `abs(D + .032*(right_aux.v36-right_aux.v25)) <= 1`. |
| `al-federal-residual`, `al-state-residual` | Alabama rows left after those classes, separately by concept. No common reconciliation asserted. |
| `la-standard-deduction-omission` | Louisiana state 2025, left v34 in {12,500, 25,000}, state AGI gap within $1, `(right v36-left v36)-left v34` within $1, `D+.03*(right v36-left v36)` within $1. All four checks apply to every row. |
| `la-other-state-residual` | Remaining Louisiana state 2025 rows; no shared reconciliation asserted. |

The two `taxsim-emulator-probes` entries pin left and right amounts and
check D within $0.000001:

* `state-zero-sales-tax` (`case_id: taxsim-77`, `D = -849.1484375`) is
  `unexplained / two_sided`, linked to the open record `pe-taxsim-1249`.
  The PR body is not a qualifying maintainer comment acknowledging an emulator
  error, and this record has no proof atoms. The observed
  amounts alone cannot supply that acknowledgment. A changed output expires
  this entry's pins.
* `texas-sales-tax-proxy` (`case_id: taxsim-78`, `D = -302.4484375000029`)
  stays `unexplained / two_sided`: both engines take a sales-tax deduction at
  Texas, in different amounts, and #1249 does not address it.

Binary bindings use the exact selected-row union:

* Default Linux: `8aa880aeea33fd501f669d42125615e3b2a0ab19c17d93a76457e9de16615059`.
* GA/MD 2024–25 Linux fallback: `00a321d2467ba011992f8b83c6e485a9b710c48fca4262a23fec1de26942a89b`.
* The Maryland signature entries contain only the fallback SHA. Some nationwide
  NIIT/rebate entries contain both, because they actually select both populations.
* Probe entries use the macOS SHA documented above.

## Evidence and issue map

The registry stores the operative quotes and minimal comment snapshots, with
source hashes, author/date checks and corpus pins. CI re-reads every atom on
every run. See [the adjudications guide](taxsim-adjudications.md) for the
requirements and full import summary. A cited issue or an arithmetical match
alone cannot establish that an engine is wrong.

| Adjudication | Bound ledger entries | Evidence and classification |
| --- | --- | --- |
| `pe-taxsim-1225` | `addmed-in-fiitax` | Verified TAXSIM maintainer acknowledgment of the AddMed error in 2000–2023; evidence_ready, taxsim_wrong / taxsim. |
| `pe-taxsim-1068` (also #716) | `rebate-timing` | Maintainer statements establish payout-year versus liability-year timing and the rebate output convention; evidence_ready, convention / convention. |
| `pe-taxsim-1222` | `la-standard-deduction-omission` | Verified TAXSIM maintainer acknowledgment of Louisiana's 2025 deduction omission; evidence_ready, taxsim_wrong / taxsim. |
| `pe-taxsim-1053` | `niit-scorp`, `niit-scorp-at-cap-*` | Official NBER input definitions and pinned current-law section 1411 text; historical legal applicability missing, pending_evidence. All bound entries are unexplained / two_sided. |
| `pe-taxsim-1249` | `state-zero-sales-tax` | Open, no proof atoms: no qualifying PolicyEngine maintainer comment admitting error. Bound entry is unexplained / two_sided. |

The AddMed acknowledgment covers only the isolated AddMed class. Mixed
`niit-addmed-*` identities remain unexplained because the NIIT component is
unresolved. The #1226 allocation acknowledgment likewise does not prove that
the broad no-S-corp populations share that cause. No population was expanded
because an issue describes a related defect.

Maryland's `md-august-county-signature` entries remain unexplained: their
output identity does not establish the source/build hypothesis in #1223.
Alabama residuals still lack paired state-zero reruns. The other Louisiana
rows remain unexplained because they fail the narrower deduction identity.
The #1214 Linux crash report remains a follow-up question; it is not a
locally observed crash that can be bound to these successful macOS probes.

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
| 2021 | 14,607 | 24,582 | NY state 2,775; CA state 2,191; AR state 1,445 | MI +$175: 250; MT -$2,477: 234; NY +$75: 161 |
| 2022 | 12,581 | 18,974 | AR state 1,369; HI state 1,134; CA federal 791 | MI +$164: 258; WA +$700: 194; NY +$100: 156 |
| 2023 | 14,296 | 19,912 | NY state 3,688; AR state 1,358; HI state 1,177 | NY -$200: 1,425; NY -$400: 654; MI +$111: 270 |
| 2024 | 12,063 | 19,671 | AR state 1,384; SC state 1,015; HI state 939 | SC +$20: 950; OK -$22: 753; OR +$44: 435 |
| 2025 | 11,885 | 20,048 | AR state 1,389; MI state 1,129; CA federal 936 | OK -$22: 753; KS +$16: 406; OH -$19: 313 |

All listed dollar clusters are state-liability differences, rounded to the
nearest dollar for descriptive grouping only. Their selectors were not
expanded on that basis. Maryland's unbound state residuals number 290/284
in 2024/2025, after the county signature; they do not share its $1 identity.
<!-- END REMAINING CLUSTERS -->

There are still substantial clusters as well as heterogeneous residuals.
This is a seed ledger, not full closure: engine-output patterns alone do not
justify expanding the explained numerator. Historical section 1411 evidence
is needed before the S-corp NIIT hypotheses can count as explained. The lane
also needs paired Alabama state-0/state-1 evidence and observed Linux crash
outcomes. The
Maryland source/build hypothesis and no-S-corp allocation classes need
independent evidence before any stronger attribution.
pe-taxsim PR #1219's `docs/ce-pumd-comparison.md` counts 9,847
suppressed-state CE records, and a #1204 comment rounds this to about 9,800.
Neither number is used in a ledger selector or evidence arithmetic.
