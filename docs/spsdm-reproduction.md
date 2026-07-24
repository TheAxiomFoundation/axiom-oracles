# Reproducing the SPSD/M oracle results

The SPSD/M lane compares rulespec-ca encodings against Statistics Canada's
Social Policy Simulation Database and Model. The Package is licensed and
never ships with this repository, so reproduction has two tiers:

- **Anyone** can audit the full method: the adapter code, the exact batch
  dialogue, the case-output variable list, the concept boundary, the
  classification mechanism (with glass-box source citations), and the
  committed aggregate results.
- **Any SPSD/M licensee** can reproduce the numbers bit-for-bit by
  following this runbook. Licences are issued by Statistics Canada
  (spsdm@statcan.gc.ca; free for Canadian academic use, modest fee
  otherwise).

## 1. Obtain and install the Package

Version pinned by this lane: **SPSD/M v34.0** (catalogue 89F0002X,
February 2026; 2022-base database; legislation announced before
2025-12-18). Any v34.0 copy is identical — verify with the fingerprints
below.

Windows: run `SPSMV3401Setup.exe -silent` with the four `.pak` files in
the same directory (about 10 minutes of silent pause is normal).

macOS (how this repo's results were produced): install Wine, then run the
same silent installer inside a prefix —

```bash
brew install --cask --skip-cask-deps wine-stable   # console model needs no media deps
xattr -dr com.apple.quarantine "/Applications/Wine Stable.app"
wineboot -i
mkdir -p ~/.wine/drive_c/spsm-install && cp SPSMV3401Setup.exe disk*.pak ~/.wine/drive_c/spsm-install/
(cd ~/.wine/drive_c/spsm-install && wine SPSMV3401Setup.exe -silent)
```

The install lands at
`C:\Program Files (x86)\StatCan\SPSDM34.0` (`SPSM_HOME` for the adapter).

## 2. Verify identical inputs

Before comparing anything, check that your Package matches the one the
committed reports were produced from. Each report's
`provenance.oracle_run.input_fingerprints` records SHA-256 digests of the
standard control/parameter files the run loaded (integrity hashes reveal
no Package content). For the federal schedule-tax lane:

```bash
shasum -a 256 "$SPSM_HOME/spsd/ba25.cpr" "$SPSM_HOME/spsd/ba25.mpr"
```

Both digests must equal the values in the committed report. If they do,
your run is guaranteed identical: SPSM is deterministic and the lane runs
the full database (no sampling), so there is no seed or ordering freedom.

## 3. Run the comparison

```bash
export SPSM_HOME="$HOME/.wine/drive_c/Program Files (x86)/StatCan/SPSDM34.0"
uv run python scripts/generate_ca_federal_tax_spsm.py --run-spsm
```

This executes the committed batch dialogue
(`$spsd/ba25#<name>#Y#read#C:\spsm-work\axiom_fedtax.cpi#go#N#N#N`) over
the full database, evaluates the encoded
`ca:policies/cra/t1-2025/federal-tax-on-taxable-income` module with the
axiom rules engine on the same taxable incomes, and rewrites the
aggregate dashboard report. Expected headline (v34.0):

- 967,396 taxfilers compared; 958,555 match within $2 (99.09%)
- 8,588 rows in the T691 overwrite class (see below); 253 unclassified

The per-household extract (`.prn`, ~240 MB) is Database-derived: keep it
local (Licence s.3.1). The committed report contains aggregates only and
carries the s.4.1 attribution notice.

## 4. What the residual class is

Whenever SPSM's T691 minimum-tax path runs, the model **replaces**
`imfedtax` with `netminamt` — the minimum amount net of AMT credits
(glass-box `Atxcalc.cpp`: "The federal tax is set to the net minimum
amount", T691 row 94). For those filers the printed variable is no longer
the schedule output in either direction; `imamtdf` ("difference due to
minimum tax") > 0 identifies them exactly, and SPSM's FTX schedule table
in `ba25.mpr` is value-identical to the encoded worksheet, so none of the
residual is parameter disagreement.
