# Belgium coverage matrix — EUROMOD BE_2025 vs rulespec-be vs axiom-oracles

Authoritative per-policy coverage of the EUROMOD Belgium `BE_2025` model surface
against the `rulespec-be` encoded surface and the `axiom-oracles` cross-engine
comparison suites. This gates the Belgium encoding wave: a row's status tells a
worker whether the instrument is unencoded, encoded-but-unvalidated, or already
oracle-compared.

- **EUROMOD facts** are parsed from the model itself:
  `EUROMOD_RELEASES_J2.0+/XMLParam/Countries/BE/BE.xml`, system `BE_2025`
  (SystemID `98820bac-c53d-4fac-8abf-96e0b43d29eb`), sha256
  `71b63c3662d35a5a633003e69a0bb7a7dfed27532d8c38b4de9f12327136afaf`. Switch
  status, function counts, and output variables are read from the XML, not from
  memory of what EUROMOD "probably" models.
- **rulespec-be** inventory is from `main` (HEAD `206f110`), `.yaml` modules only.
- **axiom-oracles** suites are the 25 published `dashboard/public/data/axiom-euromod-be-*.json`
  plus 1 registered-but-unpublished suite (`be-elderly-income-support`); per-case
  counts read from those JSONs.

## Denominator (from the XML)

`BE_2025` has **43 policy nodes**, switch counts `{on: 32, off: 7, switch: 3,
n/a: 1}` (identical to `dashboard/public/data/euromod-be-coverage.json`). Of the
43, **13 are technical/definitional** (`def` type: SetDefault, uprate, ConstDef,
ILsDef, ILsUDBDef, ILDef, random, TUDef, InitVars, neg, hhot_switch,
output_std, output_std_hh) and are not benefit/tax instruments. The remaining 30
are computing policies (`sic`/`tax`/`ben`/`inc`).

**SIMULATED** here = switch `on` (or `switch`, i.e. extension-gated) AND the
policy computes an `_s` output from inputs via `ArithOp`/`BenCalc`/`SchedCalc`/
`Allocate`/`Elig` functions. **Passthrough/off** = present in the spine but not
active in a default `BE_2025` run (income taken from the input data, or gated on
an add-on): `bun_be`, `byr_be`, `bsaoa_be`, `yem_be`, `tco_be`.

## No bundled BE country report

This release's `Documentation/` folder ships add-on notes, FAQs, the data
codebook (`EM_data_codebook_J2.0+.xlsm`), and the policy-parameters workbook
(`EUROMOD policy parameters J2.0+.xlsx`) — **no per-country policy report** for
Belgium. Gap ordering below is therefore **reasoned** (by whether the policy is
switched on, its structural breadth = function count, and the known fiscal
weight of the instrument class), explicitly **not** cited to a country report.

## Status legend

- **compared** — encoded in rulespec-be AND an axiom-oracles suite live-compares it to the EUROMOD output.
- **compared*** — suite exists and is registered (concept mapping present), but **not** in the published dashboard JSONs.
- **encoded, not compared** — a real rulespec-be module (statutory content + companion test) exists, but no EUROMOD oracle suite.
- **partial** — some sub-surface encoded, large parts not.
- **NOT ENCODED** — no rulespec-be module.

## Matrix — SIMULATED BE_2025 policies

| # | EUROMOD policy | switch | main output(s) | what it does | rulespec-be status | suite (cases match/total) | gap → Belgian legal source family |
|---|---|---|---|---|---|---|---|
| 1 | `tscee_be` | on | `tscee_s`, `tsceerd_s`, `yemeq_s` | Employee social-security contributions (13.07%) + work-bonus reduction | compared (partial) | `be-worker-ssc` (4/6 across 3 concepts) | — (broaden: special regimes, manual workers) |
| 2 | `tscer_be` | on | `tscer_s` (+ component `_s`) | Employer social-security contributions (ONSS/RSZ) | compared (partial) | `be-employer-ssc` (0/2; EUROMOD #11) | — (broaden: structural reductions, ≥20-worker, manual-worker vacation) |
| 3 | `tscse_be` | on | `tscse_s` | Self-employed social contributions (RD No. 38) | compared (partial) | `be-self-employed-ssc` (4/7; EUROMOD #6) | — (broaden: student/starter/spouse-helper/survivor) |
| 4 | `tsceesp_be` | on | `tsceesp_s` | Special social-security contribution (household, Law 30.03.1994 art. 108) | compared (partial) | `be-special-social-security-contribution` (3/7; EUROMOD #7) | — (broaden: art. 109 withholding, art. 110 settlement) |
| 5 | `tscpe_be` | on | `tscpe_s` | Pensioner health/disability + solidarity contributions | **compared with encoding gaps** (`be/statutes/social_security/non_labour_income_contributions.yaml` — Law 30.03.1994 art. 68 solidarity + Law 14.07.1994 art. 191 health 3.55%, composed into an annual combined output; **not** `chapter_10_special_contributions.yaml`, which encodes the Law 29.06.1981 art. 38 employer/fringe special contributions) | `be-pensioner-contributions` (1/6 exact; 5 axiom_encoding_gap residuals) | encode art. 191 low-pension **floor** + reconcile art. 68 solidarity base table to 2025 indexation → rulespec-be#89 |
| 6 | `tci_be` | on | `tci_s` (+ `brv_s`) | Flemish care insurance / social-protection flat premium (zorgverzekering) | compared | `be-flemish-social-protection-premium` (2/2) | — (broaden: Brussels voluntary affiliation, sanctions) |
| 7 | `tinna_be` | on | `tin_s`, `tinna_s` | Federal PIT — brackets, tax-free amount, credits; writes total `tin_s` | compared (worker pilot only) | `be-worker-pit` (2/3; EUROMOD #12) | — (broaden: full household PIT, joint assessment) |
| 8 | `tintb_be` | on | `tintasp_s`, marital-quotient, deductions | PIT deductions & marital quotient (CIR 92 arts. 87–89, 131–145) | compared (marital quotient) | `be-marital-quotient` (current publication 0/3 raw, 100% explained; repaired rulespec-be#118 worktree 3/3 within EUR 15) | — (`tintasp_s`/`tintami_s` not emitted by EUROMOD, so only the `tin_s` couple total is comparable; refresh the canonical report and retire the old slice dispositions after #118 reaches main) |
| 9 | `tinfe_be` | on | `tintcch_s`, `tin_s`, fiscal-expenditure reductions | PIT fiscal expenditures — childcare, service vouchers, pensions, donations reductions (CIR 92 arts. 145/1 ff.) | **partial** (tax_reductions_and_credits.yaml encodes childcare 145/35, pension savings 145/8, donations 145/33, domestic-employee 145/34, adoption 145/48, legal-protection 145/49; service vouchers not encoded) | — (not EUROMOD-comparable) | **Service vouchers** (titres-services/dienstencheques) absent from BE_2025 entirely; `tintcch_s` childcare stays 0 for any constructible synthetic household (data-driven, not input-driven). Only `tintcly_s` (289ter/1 work-bonus reduction) is drivable and is already covered by `be-worker-pit`. Encode remaining reductions → CIR 92 arts. 145/1–145/48 + regional decrees, unit-test-only |
| 10 | `tinrg_be` | on | `tinrg_s`, `tin_s` | Regional PIT surcharges / reductions (post-6th-state-reform regional additional %) | compared (`regional_surcharge.yaml`: reduced-state-tax base × supplied regional rate) | `be-regional-pit-surcharge` (3/3; BXL/FL/WAL) | — (broaden: regional reductions/credits, regional bracket structure) |
| 11 | `tinmu_be` | on | `tinmu_s`, `tin_s` | Municipal/local PIT surcharge (communal additional centimes on PIT) | compared (`regional_surcharge.yaml`: state+regional net of `tinfe` reductions × supplied communal rate; `communal_additions.yaml` base mechanics) | `be-local-municipal-pit` (3/3; BXL/FL/WAL) | — (broaden: municipality-specific centimes tables, agglomeration additions) |
| 12 | `tintace_be` | on | `tintace_s` | PIT professional-expense deduction (forfait) | encoded (`article_51_forfaits.yaml`) — compared via pilot | (feeds `be-worker-pit`) | — |
| 13 | `tinkt_be` | on | `tinkt_s` | Capital income tax (separately-taxed movable income) | compared (`movable_withholding/rates.yaml`: taxable movable income × art. 269 30%) | `be-capital-income-tax` (3/3; 2k/10k/50k) | — (broaden: art. 171 reduced/special rates, globalization choice) |
| 14 | `tprhm_be` | on | `tprhm_s`, `khooo_s` | Advance levy on immovable property (précompte immobilier) + indexed cadastral income | compared (2 concepts) | `be-property-tax` (3/3), `be-cadastral-income-indexation` (1/2; EUROMOD #14) | — (broaden: art. 15 remission, regional reductions, BE HOME) |
| 15 | `bch_be` | on | `bch_s` | Monthly child benefit — 4 regions × base/supplement/rank (Growth Package / groeipakket / AGF) | compared (base + BXL/WAL supplements) | `be-family-child-benefit-*` (5 suites: base 13/17 #8, BXL same-age 4/4, BXL supp 3/3, WAL supp 2/8 #9) | — (broaden: orphan/disability/single-parent supplements, mixed-age rank) |
| 16 | `bchba_be` | on | `bchba_s` | Regional birth allowance / starting amount (4 regions) | compared | `be-family-birth-allowance` (6/7; EUROMOD #13) | — (broaden: multiple-birth, payment recipient) |
| 17 | `bsa_be` | on | `bsa_s` | Social-integration income support (leefloon / revenu d'intégration, CPAS/OCMW) | compared (partial) | `be-social-assistance` (2/2) | — (broaden: itemized/cohabitant resources, earned-income disregards) |
| 18 | `bed_be` | on | `bed_s` | Study allowances — Flemish (school/study toelage) + French Community grants (147 functions) | **encoded** (`be-vlg/statutes/education/study_grant`, `be-vlg/statutes/education/school_allowance`, `be-wal/statutes/education/study_allowance`, `be/statutes/education/study_allowance_routing`) | `be-study-allowance` (6/6; batch-size 1) | — (broaden: Brussels random split + non-take-up, intern/kot amounts, disability points) |
| 19 | `bwkrg_be` | on | `bwkrg_s` | Flemish jobbonus (low-wage employment top-up) | compared | `be-flemish-jobbonus` (2/7; EUROMOD #10) | — (broaden: part-time/partial-year, frontier workers) |
| 20 | `yemcomp_be` | on | `bwkmcee_s`, `yemmw_s` | Covid-19 temporary-unemployment wage compensation (employees) | **NOT ENCODED** | — | (low priority; historical) → RD 30.03.2020 + ONEM temp-unemployment Covid measures |
| 21 | `ysecomp_be` | on | `bwkmcse_s` | Covid-19 wage compensation (self-employed bridging right / droit passerelle) | **NOT ENCODED** | — | (low priority; historical) → Law 23.03.2020 crisis bridging right |
| 22 | `bmact_be` | PBE | `bmact_s` | Maternity-leave indemnity (rest period 82%/75%, RD 03.07.1996 art. 216) | compared | `be-maternity-leave` (3/3; PBE=on) | — (broaden self-employed/unemployed maternity) |
| 23 | `bpact_be` | PBE | `bpact_s` | Paternity/birth-leave compensation (3 employer days + 82%, RD 03.07.1996 art. 223bis) | compared | `be-birth-leave` (3/3; PBE=on) | — (broaden eligibility/scheduling) |
| 24 | `bfapl_be` | PBE | `bfapl_s` | Parental-leave allowance (RVA/ONEM career-break interruption benefit) | **encoded, not compared** (`be/regulations/career_break/parental_leave/allowance_amounts.yaml`) | — (EUROMOD `bfapl_be` unreachable via HHoT: the `lpb` parental-leave-months input is absent from the BE demo schema, so `bfapl_s` stays 0 for every synthetic case) | broaden lone-parent/age-50 amounts; regional variants; PolicyEngine-style oracle |

## Passthrough / off in a default BE_2025 run (income from data or add-on-gated)

| EUROMOD policy | switch | output | why not active | rulespec-be status | gap → source family |
|---|---|---|---|---|---|
| `bun_be` | off → **switched on per run** | `bun_s` | "PART SIMULATED" and shipped **off** (unemployment income carried from input data); **activated per run** via `euromod_policy_switch_overrides` for hypothetical cases — see verdict below | **compared (dispositioned)** — `be-unemployment` (0/4 exact, **4/4 dispositioned** `upstream_engine_gap`); composed pilot `be/regulations/unemployment/pilot_oracle_pipeline.yaml` | — (broaden: household-status partner-income branches, Article 114 degressivity phases 2/3, temporary unemployment) |
| `bsaoa_be` | off (case switch → on) | `bsaoa_s` | "TO BE SWITCHED ON MANUALLY, otherwise from data" | encoded (`be/statutes/income_guarantee_for_elderly/*`) | **compared** (published `axiom-euromod-be-elderly-income-support`, 1/1 exact) via per-case XML switch overlay (`bsaoa_be`→on): isolated no-resources senior, EUROMOD `bsaoa_s` = Axiom GRAPA = 18,964.44 → Law 22.03.2001 (GRAPA/IGO). Broaden: cohabiting, delegated resource exclusions, property/capital resources |
| `byr_be` | n/a | `byr_s` (never emitted) | early-retirement / old-age pension income is a **pure input** to BE_2025. `byr_be` (12 functions, 106 params) carries policy switch **n/a**, not `off`; a live probe forcing it on (same XML overlay as GRAPA) returns **no `byr_s` column** while the run succeeds, so `n/a` is structural — the functions never register in the spine. `poa` (old-age pension) has no computing policy at all | **encoded, not compared** (`be/regulations/pensions/workers/retirement_and_survivor.yaml`) | conformance exclusion `input_carrying` (`conformance/be.yaml` `be:byr_be`): nothing to compare — unlike `bsaoa_be` (`off`, activatable), no override resurrects `byr_be`. The rulespec-be pension encodings (RD No. 50; RD 23.12.1996) validate via other oracles, not EUROMOD |
| `tco_be` | off | (commodities) | indirect consumption tax; body is `DefConst`/`DefIl` only (no `OutputVar`); **not oracle-comparable** — see verdict below | **encoded** (`be/regulations/vat/rates.yaml`, `be/statutes/excise/rates.yaml`) | conformance exclusion `extension_not_available` (RD No. 20 VAT + excise codes) |
| `yem_be` | off | `yem` | minimum-wage definition (not a benefit) | n/a (definitional) | — |

## `bun_be` activation verdict (ambiguity resolved) — `be-unemployment` suite live

The flagged ambiguity — whether `bun_be` (PART SIMULATED, switched **off** in
`BE_2025`) can be activated per run and what it then computes — is **resolved:
`bun_be` is activatable**. Its policy block carries a policy-level
`<Switch>off</Switch>` before its 22 computing functions (13 `BenCalc`, 3
`Elig`, 4 `ArithOp`, 1 `DefVar`, 1 `DefConst`), which the EUROMOD connector's
`policy_switch_overrides` machinery flips to `on` in a model overlay (the same
mechanism `be-elderly-income-support` uses for `bsaoa_be`). Every input it needs
is present in the `BE_training_data` schema (`bun`, `dag`, `liwmy`, `liwwh`,
`yivwg`/`yempv`, `lunmy`, `dms`), so this is **not** an
`oracle_dataset_lacks_input` exclusion — the suite is buildable and is built
(`be-unemployment`).

When switched on, `bun_s` for the ordinary first spell month equals
`0.65 × min(post-uprating prior monthly wage, 3432.38 EUR/month highwage cap)`,
stored divided by twelve; the oracle bridge annualizes it (×12) to recover a
monthly benefit. Household status (`i_bunft` 1/2/3 = family-charge / isolated /
cohabiting) selects distinct replacement rates and per-day min/max, and
`i_lunmy` (months in spell) drives a spell-cumulative degressivity across three
phases (period rates 0.65 / 0.60 / 0.60). **Semantically `bun_s` is a stylised
proxy, not the statute:** it caps the prior *monthly* wage at a stylised
3432.38 EUR figure (vs the RD 25.11.1991 Article 111 daily cap A1 = 92.3956
EUR/day), applies no Article 115 household-status daily floor on the ordinary
path at realistic wages, and carries no Article 114 degressivity schedule beyond
the round period rates. The composed pilot returns the Article 111 A1 cap-bound
monthly payable (92.3956 × 0.65 × 26 = 1561.49 EUR); EUROMOD returns
1645.83–2231.05 EUR across the prior-wage sweep (rising until its highwage cap
binds). All four cases are dispositioned `upstream_engine_gap` with AST-checked
reconciling arithmetic, filed as
`axiom_oracles/data/euromod_issues.json#euromod-be-2025-unemployment-simplified-bun-s`.

## `tco_be` indirect-tax verdict — conformance exclusion `extension_not_available`

Probed live against `EUROMOD_RELEASES_J2.0+` through the `euromod` connector
(0.2.18). **`tco_be` cannot be oracle-compared through the public release.** It
is a conformance exclusion, not a buildable suite:

- **Body is definitional only.** In `BE_2025`, `tco_be` is 15 functions — 6
  `DefConst` + 9 `DefIl` — with **no `OutputVar` parameter and no computational
  function** (`ArithOp`/`BenCalc`). It assigns COICOP-category VAT rate constants
  (`$tco_t_std`/`red1`/`red2`/`zero` mapped onto ~500 COICOP items via
  `$tco_t_0xxxx`) and declares consumption income lists. Force-switching it on
  (the connector's `policy_switch_overrides` path) therefore emits **no tax
  variable** — there is nothing to compare against `be/regulations/vat/rates.yaml`
  or `be/statutes/excise/rates.yaml`.
- **The compute add-ons ship, but not for Belgium.** J2.0+ *does* bundle the
  Indirect Tax Extension add-ons `CT_XBASE`, `CT_XCES`, `CT_XCIS`, `CT_XCQ`.
  Their systems cover **DE, ES, IT, HR, EE, LT, LV only** — **no BE system in any
  of them.** At country level, BE registers `BTA` (take-up), `TCA` (compliance),
  `CIA` (consumption-*inflation* uprating), and the `HHoT`/`BELMOD` extensions —
  **none compute VAT/excise.** (The earlier "needs BTA/consumption extension"
  note conflated `BTA` take-up with indirect tax; corrected here.)
- **Data prerequisite also absent.** The `DefConst` gate on
  `Run_Cond GetDataCOICOPVersion=2003`, and the shipped BE demo dataset
  `BE_training_data` carries **zero COICOP expenditure columns**, so the rate
  constants never bind on the public data.

**What would enable it:** a Belgium consumption-tax extension system in the
`CT_X*` add-ons (or an equivalent BE indirect-tax add-on) supplying the
expenditure × rate compute functions plus an `OutputVar` (e.g. `tco_s`), together
with COICOP-coded household expenditure microdata (HBS/HFCS) at
`GetDataCOICOPVersion=2003`. None of these ship in the public release; the JRC
Indirect Tax Tool covering BE is not part of it. Recorded in
`euromod_be_coverage.json` (`tco_be.conformance`).

## Encoded in rulespec-be with NO EUROMOD BE_2025 counterpart (out of scope for this oracle)

These are real encoded surfaces but EUROMOD BE_2025 does not simulate them, so
they cannot be EUROMOD-compared: regional **gift tax**, **inheritance tax**, and
**vehicle taxes** (`be-bru`/`be-vlg`/`be-wal`), Brussels **housing allowances**
and **social-housing rental**, **disability allowances** (`be/statutes/disability`),
**incapacity/invalidity indemnity** (`be/regulations/health_insurance/incapacity`),
**company car** benefit-in-kind, **mobility budget**, **non-labour-income
contributions**, and the **guaranteed family benefits / LGAF** transition
surfaces. They belong in a PolicyEngine/TAXSIM-style oracle or unit tests, not
the EUROMOD matrix.

## Sanity-check vs the live dashboard

28 published suites, **123 comparisons, 82 exact matches; explained 95.93%,
0 unexplained** (matches `euromod-be-coverage.json` `dispositioned_parity`; the
new `be-study-allowance` adds 6 comparisons, all exact matches).
`be-elderly-income-support` (`bsaoa_s`, GRAPA) is now **published** — EUROMOD
`bsaoa_s` = Axiom GRAPA = 18,964.44, exact, via the per-case `bsaoa_be`→on switch
overlay. Publishing it also closed the last of a class of pre-existing manifest
gaps: `be-social-assistance` had a committed dashboard report but no
`manifest.json` entry (direct-CLI `compare` calls, unlike the registry runner,
never touch the manifest), so it was folded into the parity rollup yet invisible
in the dashboard suite selector — now manifested, with a test pin enforcing the
invariant (the `be-maternity-leave` and `be-birth-leave` entries were restored in
#158). The three PIT-decomposition suites — `be-regional-pit-surcharge`
(`tinrg_s`), `be-local-municipal-pit` (`tinmu_s`), and `be-capital-income-tax`
(`tinkt_s`) — remain 9/9 exact. The published **`be-marital-quotient`**
(`tintb_be` Article 87) report still contributes 3 explained residuals from the
old flat couple slice. The repaired rulespec-be#118 worktree instead receives
two related Person records, runs the imported SSC/Article 51/work-bonus stages,
and matched the same three EUROMOD cases 3/3 within the unchanged EUR 15
tolerance (absolute deltas 4.730748, 0.001332, and 0.001688). Those dispositions
remain until #118 reaches main and a canonical affected rerun replaces the
published report. The **`be-pensioner-contributions`**
(`tscpe_s`) suite sweeps an isolated old-age pensioner across the health and
solidarity thresholds and is 1/6 exact (48k, where both engines' 3.55% health +
2% solidarity coincide above every threshold); its 5 residuals are the reason
`explained_rate` is below 100% — two RuleSpec-attributed encoding gaps
(the article 191 health withholding lacks EUROMOD's low-pension floor, and the
article 68 solidarity base table at index factor 1 is a different vintage from
EUROMOD's 2025-indexed thresholds), dispositioned as `axiom_encoding_gap` with
AST-checked arithmetic and filed as rulespec-be#89. `tscpe_be` therefore stays
**in scope but not conformance-covered** (`conformance/be.yaml` `suite: null`)
until #89 lands. Nothing already-compared is marked missing above.

## Wave plan (gap workers, grouped)

Ordered by reasoned fiscal/population importance (labeled reasoned — no country report):

1. **PIT decomposition** (`tinna`/`tinfe`/`tintb`/`tinrg`/`tinmu`/`tinkt`) →
   CIR 92 (arts. 130–178 rate/credits; 145/1 ff. fiscal expenditures; 465–470bis
   communal; 17–22/171/269 movable) + Special Financing Law regional %. Highest
   weight; largest EUROMOD surface (`tinfe`+`tintb`+`tinna` = 209 functions).
2. **Study allowances** (`bed_be`, `bed_s`) → Flemish Onderwijs codex +
   Fédération Wallonie-Bruxelles décret allocations d'études. Fully unencoded,
   147 EUROMOD functions.
3. ~~**Unemployment** (`bun_be`, `bun_s`; switch on) → RD 25.11.1991.~~
   **DONE** — `be-unemployment` suite live (switch on per run), 4/4 dispositioned
   `upstream_engine_gap` (EUROMOD stylised `bun_s` vs statute Article 111/114/115).
   Broaden: household-status partner-income branches, degressivity phases 2/3,
   temporary unemployment. Original note:
   Encoded,
   never oracle-compared; core working-age transfer.
4. **Pensions / GRAPA / early-retirement** (`byr_be`, `bsaoa_be`) → RD No. 50 +
   RD 23.12.1996 (pensions); Law 22.03.2001 (GRAPA). Publish the registered
   `be-elderly-income-support` suite; build a pension suite.
5. **Pensioner & special contributions** (`tscpe_be`, `tscpe_s`) → Law
   30.03.1994 ch. 10 + ZIV/AMI RD 03.07.1996.
6. **Leave suites — DONE.** `bmact_s` and `bpact_s` published (3/3 each, PBE on);
   parental leave `bfapl_be` encoded from RD 29.10.1997 (durations 4/8/20/40mo) +
   RD 02.01.1991 (amounts 508.92/254.46/86.32/43.16 EUR) at
   `be/regulations/career_break/parental_leave/allowance_amounts.yaml`. No
   `bfapl_s` oracle: EUROMOD `bfapl_be` needs the `lpb` input, absent from the BE
   HHoT demo schema, so `bfapl_s` is 0 for every synthetic case. Remaining:
   broaden self-employed/unemployed maternity, lone-parent/age-50 parental amounts,
   regional variants → RD 03.07.1996 arts. 216/223bis.
7. **Indirect tax** (`tco_be`) → RD No. 20 (VAT) + excise codes. **Resolved as a
   conformance exclusion (`extension_not_available`), not a buildable suite** —
   see the `tco_be` verdict above. Revisit only if a Belgium consumption-tax
   extension + COICOP microdata ship in a future EUROMOD release.
8. **Covid schemes** (`yemcomp`/`ysecomp`) → historical crisis measures; lowest
   priority.
