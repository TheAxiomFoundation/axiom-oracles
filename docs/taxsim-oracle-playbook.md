# TAXSIM Oracle Playbook

How the NBER TAXSIM-35 oracle is wired into axiom-oracles as a first-class
oracle, where it is authoritative, and how to extend its coverage. The
mechanics of the comparison path (shared input row, state-code conversion,
law-year support) live in [policyengine-taxsim.md](policyengine-taxsim.md);
this page is the standing recipe and the standing *judgment*.

Every TAXSIM lane grades **Axiom** against TAXSIM. Oracle-vs-oracle
comparisons (PolicyEngine vs TAXSIM) are diagnostic tooling for triage
sessions, not published lanes — an agreement rate that does not bear on
Axiom's correctness does not go on the dashboard.

## Identity

Every TAXSIM number is produced by an NBER `taxsimtest` executable that
`TaxsimPackageRunner` runs through `policyengine-taxsim`'s `TaxsimRunner`
(input formatting and output parsing). Which executable ran is pinned by
SHA-256, not implied by the package version.
`axiom_oracles/adapters/taxsim/taxsim_pins.json` (schema
`axiom-oracles/taxsim-pin/v2`) is the **single source of truth**:

- `distribution` pins the `policyengine-taxsim` package (version, PyPI sdist
  and wheel hashes, and the executables its wheel bundles). Runtime code
  reads the version via `pins.pinned_version()`; the only versioned literal
  allowed in the repo is `pyproject.toml`'s `taxsim` extra, and
  `tests/test_taxsim_pin.py::test_no_divergent_version_literals` enforces
  both rules (the #266 incident — a stale literal silently regenerating four
  suites at the wrong law year — is why).
- `binaries` pins every executable the adapter may run: SHA-256, byte size,
  platform, the build stamp read from its bytes, and where to fetch it
  (pinned `PolicyEngine/policyengine-taxsim` git blobs, NBER URLs, PyPI
  wheels), plus golden-probe results with their evidence.
- `profiles` map every (TAXSIM SOI state, tax year) to one pinned binary per
  platform: a profile default plus declarative overrides.
  `default_profile` is the one field that changes when the benchmark moves
  to another binary vintage.

| Profile | Linux build (sha256) | What it reproduces |
| --- | --- | --- |
| `dashboard-2026-09` (default) | `cd2026090910` (`8aa880ae…`); GA/MD × 2024–2025: `cd2026081819` (`00a321d2…`) | The September 2026 pe-taxsim dashboard, whose metadata records the GA/MD 2024–2025 fallback (the September Linux build raises SIGFPE there; pe-taxsim #1214, #1215) |
| `pe-taxsim-main-2026-08` | `cd2026081819` (`00a321d2…`) everywhere | The binaries on pe-taxsim `main` and in the `policyengine-taxsim` 2.31.7 wheel |
| `policyengine-taxsim-2.30.0` | `compdate` (`0d934f20…`) everywhere | The v1 pin: the executables bundled in `policyengine-taxsim` 2.30.0 |

`axiom-oracles taxsim pin-status [--profile P | --all-profiles] [--platform
linux|darwin|windows|current|all] [--json]` prints the active profile, where
it came from, the resolution table, and which binaries are present.

**Profile selection** (first that is set wins): the `--taxsim-pin-profile`
flag on `compare` (or a runner's `pin_profile=` argument), then
`$AXIOM_TAXSIM_PIN_PROFILE`, then a suite's
`runner.parameters.taxsim_pin_profile`, then `default_profile`.
`scripts/run_comparison.py` resolves the last three and passes the result to
the CLI as `--taxsim-pin-profile`. An unknown name fails the run.

**Resolution and the runtime check.** Each TAXSIM row resolves from its
`state` (TAXSIM SOI code; 0 = no state, which resolves to the profile
default) and `year`. Before anything runs, every binary the batch needs is
located and hashed, in this order: `$AXIOM_TAXSIM_BINARY_DIR`
(`<dir>/<sha256>/<filename>`, then `<dir>/<filename>`), the cache
(`$AXIOM_TAXSIM_CACHE_DIR`, default
`~/.cache/axiom-oracles/taxsim-binaries/<sha256>/<filename>`), then the
installed `policyengine-taxsim` wheel's bundled executable. Only a candidate
whose SHA-256 and size match the pin is used; otherwise the run fails with a
`TaxsimPinError` naming the SHA-256, profile, (state, year), every path
checked, and the fetch command. There is no fallback to
`policyengine-taxsim`'s own executable search: the adapter always passes the
verified path. Hashes are cached per process by (path, mtime, size).

**Fetching.** `axiom-oracles taxsim fetch-binaries [--profile P |
--all-profiles] [--platform ...] [--from-git-repo ~/PolicyEngine/pe-taxsim]`
tries the local clone's pinned blobs, then
`raw.githubusercontent.com/<repo>/<commit>/<path>`, then pinned URLs, then
pinned wheels, and writes to the cache only bytes whose SHA-256 and size
match (atomically, mode 0755). The August and September 2026 Linux builds
link dynamically against `libgfortran.so.5` and `libquadmath.so.0` (the
2.30.0 Linux build needs only `libc`), so a bare Linux image needs
`libgfortran5`.

**Execution.** Rows are partitioned by resolved binary, each partition runs
on its verified bytes, and results return in input order with
`raw["taxsim_binary_sha256"]`. The adapter replaces only
`TaxsimRunner._execute_taxsim`: the input still goes to the executable's
stdin through a pipe and stdout to the output file, but without a shell, so
a signal death is reported as that signal (through a shell it is 128+n,
indistinguishable from an ordinary exit status above 128). When a partition's
executable fails, the partition is bisected in input order (left half
first, at most ceil(log2 n) + 1 levels and `max_crash_reruns`, default 64,
re-runs). A row whose single-row run fails gets
`EngineResult(values={}, errors=("taxsim-crash:<SIGFPE | rc=n>",),
raw={"taxsim_error": {signature, returncode, stderr_tail, binary_sha256,
isolation}})`; rows left when the budget runs out get the failure of the
smallest run that held them (`isolation: "budget-exhausted"`). Rows that
succeed in a sub-run keep those outputs with `raw["taxsim_rerun"] =
"bisected"`. TAXSIM runs records sequentially in one process and a record's
result can depend on the records before it: pe-taxsim #1214's crash needs a
Delaware record before a Maryland record, and on the August macOS build a
GA 2024 record returned `siitax` 2048.20 / `srebate` 0 after a VA 2021
record carrying `opt1=30` versus 1798.20 / 250 alone (computed 2026-09-25).
So a failure can vanish under bisection, and a partitioned or bisected row
is not guaranteed to equal what one combined run would have produced; the
split sequence is fixed by input order, so a given input and binary always
take the same path. `PolicyEngineTaxsimRunner` (the PolicyEngine emulator
over TAXSIM rows) is unaffected: one run, no partitioning, no binary lookup.

**Provenance.** The CLI report carries `engine_identity.taxsim =
{pin_profile, binaries: [{sha256, build, build_observed, platform, bytes,
rows, scope}]}` (`scope` is `default` or `override:<id>`, `build_observed`
the stamp read from the verified bytes). `run_comparison.py` lifts it into
`provenance.oracle.taxsim_pin_profile` and `provenance.oracle.taxsim_binaries`
next to the `provenance.oracle.policyengine_taxsim` package version. Older
reports record at most that version; the 42 committed TAXSIM dashboard
copies (`axiom-taxsim-*`, `axiom-policyengine-taxsim-*`) checked on
2026-09-25 record no TAXSIM identity at all, so which executable produced
them is not recoverable from the reports.

**Scope.** The state income-tax liability grids
(`scripts/generate_state_income_tax_liability.py`) and the Populace
state-tax leg (`bridges/state_tax_populace_runner.py`) still run the
executable bundled in the installed `policyengine-taxsim` wheel; their
provenance records the package version, which identifies those executables
through `distribution.bundled_binaries`.

**CI.** The `taxsim-pin` job in `.github/workflows/ci.yml` syncs the locked
`taxsim` extra, fetches every profile's Linux binaries, downloads the pinned
wheel, and runs `tests/test_taxsim_pin.py`,
`tests/test_taxsim_pin_runtime.py`, and `tests/test_taxsim_runner_pinned.py`
with `AXIOM_TAXSIM_REQUIRE_BINARIES=1`, which turns every "binary not
present" skip into a failure. It checks each binary's embedded build stamp
and runs pe-taxsim's canonical VA 2021 opt(30) probe on it, asserting only
values documented for that exact binary (2068.05 / 500 for the August and
September builds; 2568.05 / 0 for the 2.30.0 Linux build, per pe-taxsim
#1095).

**Re-pinning.** Add each new executable under `binaries` (SHA-256 and size
computed from the bytes, `build` read from them, git/URL/wheel sources with
full 40-hex commits), point a profile at it or add a profile, and change
`default_profile` only when the benchmark should move. Run
`axiom-oracles taxsim fetch-binaries --all-profiles --platform linux` and the
three test files above, then regenerate the affected suites. A re-pin
changes which binary produces the numbers. Planned (PR 3 of the TAXSIM
ledger series, not yet in place): dispositions will record the binary
identity they were adjudicated against, so a re-pin will expire the
dispositions tied to the old binaries and force a deliberate re-baseline.

## Where TAXSIM is graded

| Lane | Population | Concepts | Column |
| --- | --- | --- | --- |
| `co-state-income-tax-taxsim` | CO Populace slice | CO state liability | `siitax` |
| `co-tax-intersection-taxsim` | CO Populace slice | 9 federal + CO state | per mapping |
| `fiit-taxsim-ecps` | national Populace | std deduction, EITC, FICA | per mapping |

The national federal lane is scoped to itemization-*independent* concepts.
Smoke-verified 2026-08-23: liability, taxable income, tax before credits,
and AMT pull in the oracle-bridge's generated state-income-tax leg for the
SALT/itemization choice, and that leg implements Colorado only —
`_prepare_cases_for_engines` filters those concepts to CO households, so a
national sample prepares zero cases. Growing the state bridge beyond
Colorado is the unlock for a national liability lane; until then the CO
intersection suite carries those concepts. CTC/CDCC are excluded from the
national lane on signal grounds (the 2026 binary's child-credit gap makes
every child row a known NBER artifact).
| State grids (~39 suites) | 12-case synthetic grids | per-state liability concept | per mapping |
| Populace campaign | national Populace, 43 jurisdictions | per-state output concept | per mapping, or skipped |

**The graded output column is always resolved from
`axiom_oracles/config/concept_mappings.yaml`**, never hardcoded:

- Final-liability concepts map `siitax` (state) / `fiitax` (federal).
- Pre-credit schedule concepts map **`staxbc`** — state tax before credits.
  Verified against the pinned binary: `staxbc − v40 (total credits) =
  siitax`. This is what upgraded UT and KY from "supplemental" to exact
  peers and gave AL, GA, AR, MS, and DE their first TAXSIM legs.
- A concept with **no** `taxsim` mapping is **skipped, never guessed**. The
  populace runner records these in `taxsim_skipped_states`. As of 2026-08-23
  the only skip is CA (Behavioral Health Services Tax — no truthful TAXSIM
  surface exists; do not map it). CT/DC/KS/MN/OH were probe-verified and
  mapped to `staxbc` the same day; the probe notes live on their mapping
  entries.

## Standing: where TAXSIM is authoritative vs advisory

**Authoritative** (a disagreement is presumptively an Axiom-side or
PolicyEngine-side issue):

- Federal core at 2026: OBBBA rate schedule, standard deduction, AGI
  (`v10`), taxable income, tax before credits, childless EITC, FICA/SECA
  (`tfica`).
- State flat-rate cores (e.g. CO's taxable × 4.40%).

**Advisory** (a disagreement is presumptively a TAXSIM-side vintage or model
gap; disposition it, do not chase the Axiom encoding):

- Any child-credit machinery at law year 2026: the pinned binary's CTC
  collapses to the $500 ODC path; ACTC, CDCC, and EITC-with-children return
  zero. These rows enroll in the standing NBER-gap disposition classes.
- State modules with extrapolated or un-enacted parameters (KY 4.0% vs
  enacted 3.5%, NC 4.25% vs 3.99%, GA 5.19% vs 4.99%; fractional-dollar
  parameter extrapolations in the `idtl=2` detail).
- NIIT bookkeeping against the composed Axiom program while
  axiom-encode#1213 keeps §1411 out of the composition (TAXSIM `fiitax`
  includes it; the residual equals TAXSIM's own `niit` column).
- Units where a **dependent** carries non-wage income: TAXSIM-35 has no
  dependent-income input, so the shared projection sums non-wage columns
  over head+spouse only, while the Axiom/PolicyEngine side computes the
  full tax-unit value. The one-sided AGI gap equals the dependents'
  unearned income; it is a projection-surface limitation (all lanes,
  ECPS and populace alike), not an oracle disagreement. Social-security
  benefits (`gssi`) follow the same rule: the §86 member is exactly
  0.85 × the non-earner members' benefits, plus the H.R.1 §70103
  senior-deduction phaseout knock-on of the shifted MAGI.
- **SE-tax ALD**: the pinned binary deducts half of the §1401(b)(2)
  additional Medicare tax in its self-employment-tax ALD, which §164(f)(1)
  excludes (isolated probe: w=0, se=810,431 → ALD 24,759.23 = 22,291.28
  statutory + 0.5 × 0.009 × (748,433 − 200,000)). Its OASDI base is the
  official 184,500; the oracle bridge deliberately pins 186,000 to match
  PolicyEngine, so wage-straddling rows differ by exactly 0.5 × 0.124 ×
  1,500 = 93.00. Axiom's ALD is statutory at the bridge base.
- **QBID**: plain 20% of (psemp + ssemp − its SE ALD) — no §199A(b)(3)
  wage/UBIA limitation, no H.R.1 §70105 $400 minimum, no rental in the
  QBI base. Rows above the phase-in ceiling collapse to axiom's $400
  floor vs TAXSIM's full 20%.
- **§461(l)**: the binary DOES cap excess business losses, at its own
  projected 332,389.95 single / 664,779.90 joint, and it treats net
  positive capital gain as business gross income (the allowance grows
  dollar-for-dollar). The axiom leg's cap arrives through the projection
  surface at the 2024-vintage 305,000/610,000 with no gain offset, so
  these rows are two-sided (`explained_residual`), favoring neither.
- **AMT at extreme incomes**: AMTI agrees to the cent (`v26`); `v27`
  departs per the pre-OBBBA AMT parameter vintage compounded with the
  capital-gains bracket vintage, while the bridge's Part III grants the
  gain stack the full 0%/15% brackets (the dispositioned bucket-routing
  convention). Two-sided; axiom's value reproduces exactly from its own
  audited worksheet identity `max(0, TMT − (§1(h)+§1(j)))`.
- **ND/RI grids**: the binary's 2026 state parameters are its own
  inflation projections; axiom reproduces the ND Commissioner's official
  2026 schedule ($49,575 single 0% bracket) and RI's ADV 2025-22 amounts to
  the cent, so these residuals attribute to TAXSIM without triangulation.

**Axiom-side, classified `axiom_encoding_gap` (visible until fixed):**

- The bridge's `earned_income` input for §32 does not net self-employment
  losses; §32(c)(2)(A)(ii) nets net earnings from self-employment. Units
  with wages and an SE loss phase out on the unnetted wage figure (or keep
  a sliver of childless credit when the netted figure would be ≤ 0).
  Four rows across the CO intersection and national lanes. Fixing the
  projection converts them to matches.

## Status

As of 2026-09-01 every TAXSIM lane is at **100% explained, zero
unexplained rows** (PR #515 closed the last 72: 57 + 7 CO, 3 national, 1 ND,
4 RI). The row-by-row member decomposition that licensed the final CO
entries — full-evidence axiom closure (337 outputs per unit, compared
concepts reproducing every committed mismatch value before any chain was
read) plus pinned-binary synthetic probes — is committed as
`reports/axiom-taxsim-co-tax-intersection-ecps-member-decomposition-2026-08-31.json`.
The `unexplained_ratchet` pins the ceiling at zero; a regression on any
TAXSIM lane now fails CI.

## Extending coverage

1. **New state, final-liability concept**: add `taxsim: siitax` to the
   concept's mapping entry. The grid generator and populace leg pick it up
   automatically.
2. **New state, pre-credit concept**: verify `staxbc` semantics for that
   state against the pinned binary first (one probe case:
   `staxbc − v40 = siitax` must hold and the credit split must match the
   concept boundary), then add `taxsim: staxbc` with a comment recording the
   probe.
3. **Component concepts** (state AGI `v32`, state taxable income `v36`,
   state EITC `v39`, state CTC `sctc`, …): the binary already returns all 54
   columns at `idtl=2`; what's missing are Axiom-side concepts to grade them
   against. When a state pipeline grows a reviewed intermediate output, map
   it — do not invent a concept for the column's sake. The same applies to
   federal `qbid` and `v17` (itemized deductions allowed): unmapped until an
   Axiom concept exists.
4. **Law year**: `TAXSIM_MAX_YEAR` (adapter) and the pinned release cap
   modeled law at 2026. When Axiom moves to 2027 before NBER does, the
   TAXSIM lanes stay pinned at their last supported year and their suites'
   `period` must NOT silently advance — bump the pin (a new
   `taxsim_pins.json`, full identity refresh, and re-baselined dispositions)
   or freeze the lane.

## Persistence discipline

TAXSIM suites persist **every** mismatch row in the committed dashboard copy
(`dashboard.max_mismatches` in the suite YAML — see
`co-tax-intersection-taxsim`'s 4,000-row cap and issue #439 for why: 438
unexplained rows were once physically untriageable behind the default
1,000-row cap). If a TAXSIM suite's mismatch count approaches its cap, raise
the cap in the same change that regenerates the suite.
