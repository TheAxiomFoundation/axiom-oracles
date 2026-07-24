# SPSD/M as an oracle — design and licence constraints

Statistics Canada's Social Policy Simulation Database and Model (SPSD/M) as
the Canadian oracle: the reference tax–transfer microsimulation maintained
by the national statistical agency, driven over its own synthetic
household database.

## The licensed package (v34.0, February 2026)

- **Model**: SPSM, a Windows console batch model (32-bit x86). Glass-box
  C++ sources ship with the package and can be recompiled (VS 2019/2022).
- **Database**: 2022-base synthetic microdata (non-identifiable,
  StatCan-constructed), with a dynamic labour adjustment reflecting
  2020–2021 employment patterns.
- **Law coverage**: tax years 1997–2030 as parameterized; legislative
  changes announced before 2025-12-18 are modeled (per the v34 README and
  Addendum). The Addendum catalogues federal/provincial changes, new and
  modified parameters, and variable changes since v30.3.
- **Platform**: Windows 11 only per StatCan; "not compatible with Apple
  Mac OS". This repo drives it through Wine (32-bit), mirroring the
  EUROMOD-under-Rosetta precedent. The pinned identity of the licensed
  copy lives in `axiom_oracles/adapters/spsm/spsm_pins.json`.

## Licence constraints (SPSD/M Licence Agreement, v34, signed)

These are load-bearing for how the lane is built. Reading of the executed
agreement:

1. **Research use is licensed** (§2.1: "statistical and research
   purposes") — oracle validation is squarely that.
2. **No part of the Package may be redistributed** (§3.1). Therefore this
   repository must NEVER contain: the database or any records derived
   from it, the model binaries, the parameter files, the glass-box
   sources, or documentation extracts beyond short quotations. Reports
   that embed per-household synthetic-database attributes are treated as
   Database records and stay out of git (local `reports/` only, which is
   gitignored).
3. **Published analysis requires the notice** (§4.1). Every committed
   artifact that presents SPSD/M-derived results (dashboard JSON,
   suite documentation) must carry:

   > "This analysis is based on Statistics Canada's Social Policy
   > Simulation Database and Model. The assumptions and calculations
   > underlying the simulation results were prepared by the Axiom
   > Foundation and the responsibility for the use and interpretation of
   > these data is entirely that of the author(s)."

4. **No derived software product for distribution** (§3.1). The adapter
   drives the licensed model as an external engine — the same
   arm's-length relationship the TAXSIM/EUROMOD/PRD adapters have to
   their oracles — and embeds nothing from the Package.

## Lane design

Two-layer comparison, licence-shaped:

- **Committed (dashboard)**: aggregate-level agreement only — per-concept
  match rates, weighted aggregates, mismatch-class counts, dispositions —
  plus the §4.1 notice in the suite description and report provenance.
  `include_inputs=False` is forced for SPSM suites regardless of size so
  no synthetic-database household attributes are persisted.
- **Local (gitignored reports/)**: full per-household evidence for
  triage, exactly like other lanes, never committed.

Engine mechanics (first iteration):

- The adapter writes an SPSM control-parameter file requesting a
  per-household variable extract for the concepts under comparison
  (federal/provincial income tax, GST/HST credit, CCB, OAS/GIS, EI/CPP
  contributions), runs `spsm` under Wine in batch mode, and parses the
  extract.
- The axiom leg runs the rulespec-ca encodings (cra / esdc /
  revenu-quebec policies) over households projected from the same
  SPSD synthetic records — the SPSD database is the validation
  population for this lane, as Enhanced CPS is for the US lanes.
- Concept mappings gain `spsm:` targets naming SPSM output variables.

## Open items tracked before first data lands

- Wine bootstrap and silent install (`SPSMV3401Setup.exe -silent`) —
  installer is a GEA-packed set; if the installer resists Wine, the
  fallback is installing on a Windows machine and copying the installed
  tree (permitted: the licensee may make copies for their own use, §2.2).
- Which SPSM output variables map to which rulespec-ca concepts —
  requires the installed Variable Guide.
- Year alignment: rulespec-ca validation year vs SPSM's parameterized
  years (SPSM models through 2030 projections; the enacted-law horizon
  is 2025-12-18, so 2026 comparisons carry the same
  "announced-before-cutoff" caveat the TAXSIM lane documents).
