# TAXSIM Oracle Playbook

How the NBER TAXSIM-35 oracle is wired into axiom-oracles as a first-class
oracle, which side a disagreement is presumed to be on, and how to extend its
coverage. The
mechanics of the comparison path (shared input row, state-code conversion,
law-year support) live in [policyengine-taxsim.md](policyengine-taxsim.md);
this page is the standing recipe and the standing *judgment*.

Disclosure: Max Ghenis is CEO of both the Axiom Foundation and PolicyEngine,
and our TAXSIM runs use the TAXSIM executable that PolicyEngine packages
(`policyengine-taxsim`, pinned in `axiom_oracles/adapters/taxsim/taxsim_pins.json`).

Every TAXSIM lane compares **Axiom** with TAXSIM. Oracle-vs-oracle
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
| `dashboard-2026-09` | `cd2026090910` (`8aa880ae…`); GA/MD × 2024–2025: `cd2026081819` (`00a321d2…`) | The September 2026 pe-taxsim dashboard: `summary_<year>.json` records `taxsimBinarySha256` `8aa880ae…` for 2021–2025 and, for 2024 and 2025, a `taxsimFallback` sending GA and MD to `00a321d2…` (the September Linux build raises SIGFPE there; pe-taxsim #1214) |
| `pe-taxsim-main-2026-08` | `cd2026081819` (`00a321d2…`) everywhere | The August builds pe-taxsim `main` bundled from #1150 until #1206 merged (2026-11-02), and the `policyengine-taxsim` 2.31.7 wheel's |
| `policyengine-taxsim-2.30.0` (default) | `cdate-compdate` (`0d934f20…`) everywhere | The v1 pin: the executables bundled in `policyengine-taxsim` 2.30.0, which the `taxsim` extra installs |

No profile pins the November 1 builds (`cd2026110117`: Linux `beb897fd…`, macOS `21d36bac…`) that pe-taxsim `main` has bundled since #1206 merged; pe-taxsim's Windows build stayed at `a8207e7c…`. A profile for them is a follow-up.

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
2.30.0 Linux build is statically linked and needs no shared libraries), so a bare Linux image needs
`libgfortran5`.

**Execution.** Rows are partitioned by resolved binary. Every partition's
binary is located and range-checked before any partition runs, so a missing
or mismatched binary fails the batch with no partial run. Each partition then
goes through the per-batch checks the runner already had: its law years are
checked against the binary's pinned range (`pins.require_law_years`), the
bytes are hashed again just before the run and must still equal the pinned
SHA-256, and after the run the recorder hashes them a third time
(`TaxsimIdentityRecorder`). policyengine-taxsim's `TaxsimRunner` only
formats the input; the adapter runs the verified absolute path itself and
parses stdout with `parse_taxsim_stdout`. Results return in input order,
each with `raw["taxsim_binary_sha256"]` and `raw["taxsim_pin_scope"]`.
TAXSIM runs records sequentially in one process, and a record's result can
depend on the records before it (pe-taxsim #1214's crash needs a Delaware
record before a Maryland record), so a partitioned row is not guaranteed to
equal what one combined run would have produced. A non-zero exit fails the
batch, as before. `PolicyEngineTaxsimRunner` (the PolicyEngine emulator over
TAXSIM rows) is unaffected: one run, no partitioning, no binary lookup.

**Provenance.** The CLI report's `engine_identity.taxsim` block gains
`pin_profile`, and each binary entry gains `scopes`, the rows it ran per
profile scope (`default` or `override:<id>`), next to the path, SHA-256,
build stamps, platform and rows it already recorded. `run_comparison.py`
lifts them into `provenance.oracle.taxsim_pin_profile` and
`provenance.oracle.taxsim_binaries`, and `scripts/merge_shard_reports.py`
sums rows and scope rows across shards and refuses shards run under
different profiles. Reports written before the runner recorded a binary
record at most the `policyengine_taxsim` package version.

**Scope.** The state income-tax liability grids
(`scripts/generate_state_income_tax_liability.py`) and the Populace
state-tax leg (`bridges/state_tax_populace_runner.py`) still run the
executable bundled in the installed `policyengine-taxsim` wheel and ignore
`--taxsim-pin-profile` and `$AXIOM_TAXSIM_PIN_PROFILE`. Their provenance
records the package version and, in `engine_identity.taxsim`, the hash of
the binary that ran. `pinned_entry_for_sha` also finds every v2 profile
binary, so if such a caller runs a wheel other than the pinned 2.30.0 one
whose binary is a profile binary, its identity reads `pinned: true` with key
`binaries/<sha256>` while `distribution` still names 2.30.0.

**CI.** The `taxsim-pin` job in `.github/workflows/ci.yml` syncs the locked
`taxsim` extra, fetches every profile's Linux binaries, downloads the pinned
wheel, and runs `tests/test_taxsim_pin.py`,
`tests/test_taxsim_pin_runtime.py`, `tests/test_taxsim_identity.py` and
`tests/test_taxsim_execution_identity.py` with
`AXIOM_TAXSIM_REQUIRE_BINARIES=1`, which turns every "binary not
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
test files above, then regenerate the affected suites. A re-pin
changes which binary produces the numbers. Dispositions do not yet record
the binary identity they were adjudicated against, so a re-pin does not by
itself expire the dispositions tied to the old binaries.

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

## Standing: which side a TAXSIM disagreement is presumed to be on

**Disagreement presumed Axiom- or PolicyEngine-side:**

- Federal core at 2026: OBBBA rate schedule, standard deduction, AGI
  (`v10`), taxable income, tax before credits, childless EITC, FICA/SECA
  (`tfica`).
- State flat-rate cores (e.g. CO's taxable × 4.40%).

**Disagreement presumed TAXSIM-side** (a vintage or model gap; disposition it,
do not chase the Axiom encoding):

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
- Units with **tax-exempt interest** (Form 1040 line 2a): the complete
  [NBER input list](https://taxsim.nber.org/taxsimtest/) has no input for it
  and defines `intrec` as taxable interest. The pinned macOS binary rejected
  an added `exint` column with `STOP 901` in the independent review; the
  reproduction below checks that observation against the binary's hash.
  The projection therefore leaves
  `Concepts.TAX_EXEMPT_INTEREST_INCOME` out of the row and records the
  dropped signed head+spouse sum when nonzero under the attached Case's
  `metadata.taxsim_unprojected_inputs`, including preprojected Cases.
  Direct `TaxsimPackageRunner.run_cases` calls carry the same diagnostic in
  `EngineResult.raw`; the state campaign carries it in each affected
  comparison case row's metadata. These paths preserve the row and output
  values. TAXSIM therefore computes as if
  line 2a were 0: its taxable Social Security (`v12`) omits the §86(b)(2)(B)
  add-back to modified AGI, and its EITC investment-income test omits
  Pub. 596 Worksheet 1 line 2 (§32(i)(2)(B)), while the Axiom side counts
  both. **Classification rule, limited to this omission:** an affected
  Axiom-vs-TAXSIM row may be dispositioned as `bridge_artifact` only when
  per-row causal evidence and arithmetic reconcile the mismatch to the
  dropped filer input's effect on the compared output, under
  [the disposition rules](../dispositions/README.md#rules). This class
  describes a projection-surface limitation rather than an oracle
  disagreement. A nonzero diagnostic alone does not establish the cause,
  and must not hide any residual beyond what the omission can explain.
  Retain and investigate the unreconciled portion, including a mismatch
  larger than the explained effect. No automatic disposition follows from
  this key, and this rule makes no claim about other omitted income.
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

### Reproducing the tax-exempt-interest input rejection

Run this from the repository root on macOS with Python. It downloads the
wheel URL recorded in [the pin](../axiom_oracles/adapters/taxsim/taxsim_pins.json),
checks the wheel and macOS executable hashes, then sends the control CSV and
the same CSV with `exint=10000` to separate subprocesses. The pin at this
review head records wheel SHA-256
`2897300fbcd0596791ca8f8528f579b90c605ff3a918bfef4d1b3ad272152ad1`
and macOS binary SHA-256
`0d9e43a983055d44eec9e5de7edfc933fa061b2a336716d760fe98abf4336319`.

```bash
python - <<'PY'
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
from urllib.request import urlopen
import zipfile

pin = json.loads(Path("axiom_oracles/adapters/taxsim/taxsim_pins.json").read_text())
wheel = pin["distribution"]["wheel"]
with urlopen(wheel["url"], timeout=20) as response:
    wheel_bytes = response.read()
assert hashlib.sha256(wheel_bytes).hexdigest() == wheel["sha256"]
key = "taxsimtest/taxsimtest-osx.exe"
with zipfile.ZipFile(io.BytesIO(wheel_bytes)) as archive:
    (entry,) = [name for name in archive.namelist() if name.endswith("/" + key)]
    binary_bytes = archive.read(entry)
assert hashlib.sha256(binary_bytes).hexdigest() == pin["bundled_binaries"][key]["sha256"]
with tempfile.TemporaryDirectory(prefix="taxsim-exint-") as scratch:
    binary = Path(scratch) / "taxsimtest-osx.exe"
    binary.write_bytes(binary_bytes)
    binary.chmod(0o755)
    for label, csv_input in (
        ("control", "year,mstat,taxsimid,pwages,idtl\n2026,1,1,8000,2\n"),
        ("exint", "year,mstat,taxsimid,pwages,idtl,exint\n2026,1,1,8000,2,10000\n"),
    ):
        try:
            result = subprocess.run(
                [str(binary)], input=csv_input, text=True,
                capture_output=True, timeout=20,
            )
        except subprocess.TimeoutExpired:
            print(label, "timed out; no rejection or calculation result observed")
            continue
        print(label, "exit", result.returncode)
        print("stdout:", result.stdout)
        print("stderr:", result.stderr)
PY
```

The independent review's initial control exited 0 with `v10=8000.00` and
`v25=612.00`. The `exint` input exited 133, with
`TAXSIM: ERROR 'exint' is not a taxsimtest input variable.` on stdout and
`STOP 901` on stderr. Later retries timed out at 20 seconds; a timeout is
not a reproduced rejection or a passing calculation. The input-list
evidence and this rejection establish the missing surface; they do not
reconcile any particular liability mismatch.

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
   modeled law at 2026, but of the platform executables only the macOS one is
   known to accept 2026. Each bundled executable's accepted range is pinned in
   `taxsim_pins.json` (`law_years`; the Linux build stops at 2024), and the
   code paths that run the pinned binary refuse a law year outside its range
   before running it (`pins.require_law_years`). When Axiom moves to 2027
   before NBER does, the
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

## Disposition ledger discipline

A suite with `taxsim` on either side is a TAXSIM lane, and its
`dispositions/<suite>.yaml` is held to the hardened rules in
[`dispositions/README.md`](../dispositions/README.md#taxsim-lanes): every
entry names its `attribution` (`taxsim`, the other side's engine,
`convention`, `input`, or `two_sided`), binds the TAXSIM identity it was
classified against (`oracle_binding`), binds its selected population
(`selector_binding`, or `pinned` values for a single row), and reconciles
per row (`evidence.row_arithmetic`) or cites an upstream record. A row
claimed by two entries fails the merge.

Consequences for a re-pin or a refresh:

- **Re-pinning TAXSIM expires every classification** bound to the previous
  identity: the merge compares each entry's `oracle_binding` with the
  binaries the new report records, and a mismatch returns the entry's rows
  to unexplained (`expired_reasons: oracle_identity_changed`), which the
  unexplained ratchet then gates. The reports committed before binaries
  were recorded carry `identity_unrecorded: true` bindings: their committed
  provenance contains neither binary digests nor a TAXSIM package version.
  This explicit legacy exception preserves the existing assignments without
  asserting an unrecorded identity. It expires the first time a report records
  any TAXSIM identity (binary digests or a package version). An unrecorded
  binary change with identical rows remains undetectable; refreshed reports
  must record their actual binary identity.
- **Re-verify, then re-bind.** After re-checking a class against the
  refreshed report, stamp its bindings from the committed FULL report with
  `uv run scripts/bind_dispositions.py <suite>` (`--check` reports drift
  without writing) in the same commit as the report. Never re-bind a class
  that was not re-verified: the binding is the claim that it was.
- **Engine crashes are rows, not gaps in the report.** A case whose TAXSIM
  run fails becomes `engine_error` mismatch rows carrying the crash
  signature and failing binary (`row["error"]`); disposition them with
  `kind: engine_error` and `match.error_signature`, bound to that binary's
  sha256.
