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
- **axiom-oracles** suites are the 33 published `dashboard/public/data/axiom-euromod-be-*.json`
  reports, all listed in `dashboard/public/data/manifest.json`; per-case counts
  are read from those JSONs (see the sanity check below for where each figure
  comes from).

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
| 5 | `tscpe_be` | on | `tscpe_s` | Pensioner health/disability + solidarity contributions | compared (`be/statutes/social_security/non_labour_income_contributions.yaml` — Law 30.03.1994 art. 68 solidarity + Law 14.07.1994 art. 191 health 3.55%, composed into an annual combined output; **not** `chapter_10_special_contributions.yaml`, which encodes the Law 29.06.1981 art. 38 employer/fringe special contributions) | `be-pensioner-contributions` (6/6 since `42e378047`, #169); `tscpe_s` also 3/3 inside `be-pensioner-pit` | — (the art. 191 low-pension floor and 2025-indexed art. 68 thresholds landed in rulespec-be#91, closing rulespec-be#89; broaden: family-charge floors and thresholds, complementary/capital pensions — all six cases are isolated single pensioners) |
| 6 | `tci_be` | on | `tci_s` (+ `brv_s`) | Flemish care insurance / social-protection flat premium (zorgverzekering) | compared | `be-flemish-social-protection-premium` (2/2) | — (broaden: Brussels voluntary affiliation, sanctions) |
| 7 | `tinna_be` | on | `tin_s`, `tinna_s` | Federal PIT — brackets, tax-free amount, credits; writes total `tin_s` | compared (worker pilot + pensioner, replacement-income and self-employment pipelines) | `be-worker-pit` (2/3; EUROMOD #12); `tin_s` also in `be-pensioner-pit` (3/4), `be-replacement-income-pit` (4/5), `be-self-employment-pit` (2/4); `tintcri_s` in `be-pensioner-pit` (3/3) and `be-replacement-income-pit` (4/4) | — (broaden: full household PIT, joint assessment) |
| 8 | `tintb_be` | on | `tintasp_s`, marital-quotient, deductions | PIT deductions & marital quotient (CIR 92 arts. 87–89, 131–145) | compared (marital quotient) | `be-marital-quotient` (3/3 within EUR 15 since `9bd179697`, #500, against rulespec-be `7c85808a` = the rulespec-be#118 merge) | — (`tintasp_s`/`tintami_s` not emitted by EUROMOD, so only the `tin_s` couple total is comparable) |
| 9 | `tinfe_be` | on | `tintcch_s`, `tin_s`, fiscal-expenditure reductions | PIT fiscal expenditures — childcare, service vouchers, pensions, donations reductions (CIR 92 arts. 145/1 ff.) | **partial** (tax_reductions_and_credits.yaml encodes childcare 145/35, pension savings 145/8, donations 145/33, domestic-employee 145/34, adoption 145/48, legal-protection 145/49; service vouchers not encoded) | `be-work-bonus-credit` (`tintcly_s` 2/4, both residuals `upstream_engine_gap`; `f6df151bc`, #183) | **Service vouchers** (titres-services/dienstencheques) absent from BE_2025 entirely; `tintcch_s` childcare stays 0 for any constructible synthetic household (data-driven, not input-driven). Only `tintcly_s` (289ter/1 work-bonus reduction) is drivable, and `be-work-bonus-credit` compares it (the suite `conformance/be.yaml` maps to `tinfe_be`). Encode remaining reductions → CIR 92 arts. 145/1–145/48 + regional decrees, unit-test-only |
| 10 | `tinrg_be` | on | `tinrg_s`, `tin_s` | Regional PIT surcharges / reductions (post-6th-state-reform regional additional %) | compared (`regional_surcharge.yaml`: reduced-state-tax base × supplied regional rate) | `be-regional-pit-surcharge` (3/3; BXL/FL/WAL) | — (broaden: regional reductions/credits, regional bracket structure) |
| 11 | `tinmu_be` | on | `tinmu_s`, `tin_s` | Municipal/local PIT surcharge (communal additional centimes on PIT) | compared (`regional_surcharge.yaml`: state+regional net of `tinfe` reductions × supplied communal rate; `communal_additions.yaml` base mechanics) | `be-local-municipal-pit` (3/3; BXL/FL/WAL) | — (broaden: municipality-specific centimes tables, agglomeration additions) |
| 12 | `tintace_be` | on | `tintace_s` | PIT professional-expense deduction (forfait) | compared (`article_51_forfaits.yaml`) | `be-article-51-forfait` (`tintace_s` 5/5; `f6df151bc`, #183); also feeds `be-worker-pit` | — |
| 13 | `tinkt_be` | on | `tinkt_s` | Capital income tax (separately-taxed movable income) | compared (`movable_withholding/rates.yaml`: taxable movable income × art. 269 30%) | `be-capital-income-tax` (3/3; 2k/10k/50k) | — (broaden: art. 171 reduced/special rates, globalization choice) |
| 14 | `tprhm_be` | on | `tprhm_s`, `khooo_s` | Advance levy on immovable property (précompte immobilier) + indexed cadastral income | compared (2 concepts) | `be-property-tax` (3/3), `be-cadastral-income-indexation` (1/2; EUROMOD #14) | — (broaden: art. 15 remission, regional reductions, BE HOME) |
| 15 | `bch_be` | on | `bch_s` | Monthly child benefit — 4 regions × base/supplement/rank (Growth Package / groeipakket / AGF) | compared (base + BXL/WAL supplements) | `be-family-child-benefit-*` (5 suites: base 13/17 #8, BXL same-age 4/4, BXL supp 3/3, WAL supp 2/8 #9, `ils_ben` income list 4/4) | — (broaden: orphan/disability/single-parent supplements, mixed-age rank) |
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
**company car** benefit-in-kind, **mobility budget**, the rest of the
**non-labour-income contributions** module (RD 33 invalidity/pre-pension
withholding and the art. 68 complementary-capital withholding; its pensioner
health/solidarity total is compared in row 5), and the **guaranteed family benefits / LGAF** transition
surfaces. They belong in a PolicyEngine/TAXSIM-style oracle or unit tests, not
the EUROMOD matrix.

## Sanity-check vs the live dashboard

Recomputed on 2026-09-24 from the committed data at `78223652e`.

**33 published suites, 156 comparisons, 116 exact matches (raw 74.36%);
explained 100%, 0 unexplained.** These are the `dispositioned_parity` figures in
`axiom_oracles/data/euromod_be_coverage.json` (identical to the dashboard copy,
`dashboard/public/data/euromod-be-coverage.json`). CI runs
`uv run scripts/apply_dispositions.py --check`, which fails if either copy
drifts from the sum over the 33 `dashboard/public/data/axiom-euromod-be-*.json`
reports. Each of the 40 non-exact comparisons carries a disposition from
`dispositions/be-*.yaml`: 33 `upstream_engine_gap` and 7 `explained_residual`
(6 in `be-family-child-benefit-wallonia-social-supplement`, 1 in
`be-self-employment-pit`). None is `axiom_encoding_gap`, `bridge_artifact` or
unexplained. `conformance/scoreboard.json` has BE at 23/23 in-scope policies
covered. Two suites check EUROMOD income lists rather than a single policy:
`be-worker-tax-income-list` (`ils_tax`, 2/2) and
`be-worker-disposable-income-list` (`ils_dispy`, 2/2); the benefit list
`ils_ben` is the fifth family child benefit suite in row 15.

**Refreshes come from supervised runs.** A BE figure changes only when someone
runs `uv run scripts/run_comparison.py <suite>` on a machine with the EUROMOD
J2.0+ model and an x64 runtime reachable through `EUROMOD_PYTHON`, then commits
the report. Such a report records `run_kind: manual` (the default in
`axiom_oracles/provenance.py`) and the rulespec-be SHA it ran against. The
scheduled affected rerun (`.github/workflows/affected-rerun.yml`) cannot compute
BE numbers: every workflow runs on `ubuntu-latest`, and none sets
`EUROMOD_PYTHON` or provides the model. When the rerun selects a BE suite,
`_run_euromod_synthetic_compare` in `scripts/run_comparison.py` copies the
committed report back out, and its provenance is restamped with
`reemitted_report: true`, `run_kind: affected-rerun` and a null rulespec-be
SHA. `scripts/select_affected_suites.py` treats a null SHA as unproven
freshness, so the same suites are selected again on the next sweep. The values
do not change, but the `generated_at` time and engine SHA on a re-emitted report
describe the re-emission, not the run that computed the numbers. The 12 BE
suites in `comparisons/affected_map.json`, the only ones the rerun can select,
trace to these runs:

| Suite(s) | Published | Values from | rulespec-be recorded by that run | File on `main` |
|---|---|---|---|---|
| `be-marital-quotient` | 3/3 | `9bd179697` (#500), run 2026-08-21 | `7c85808a` (the rulespec-be#118 merge) | re-emitted |
| `be-pensioner-contributions` | 6/6 | `42e378047` (#169), run 2026-07-06 | `f4c58055`, a local commit whose `non_labour_income_contributions.yaml` is identical to the rulespec-be#91 merge `09c68b40` | re-emitted |
| `be-elderly-income-support` | 1/1 | `f14904a2e` (#162), run 2026-07-05 | `b2797668` | re-emitted |
| `be-regional-pit-surcharge`, `be-local-municipal-pit`, `be-capital-income-tax` | 3/3 each | `1d64b93d6` (#156), run 2026-07-05 | not recorded | re-emitted |
| `be-study-allowance` | 6/6 | `cfae64354` (#167) | not recorded (the committed report has no provenance block) | re-emitted |
| `be-article-51-forfait`, `be-work-bonus-credit` | 5/5; 2/4 | `f6df151bc` (#183), run 2026-07-06 | `4089efe2` | re-emitted |
| `be-pensioner-pit`, `be-replacement-income-pit`, `be-self-employment-pit` | 9/10; 8/9; 2/5 | `46aa8f39a` (#508), run 2026-08-22 | `b105e2b3` (rulespec-be `main` as of 2026-09-24) | original run |

The other 21 reports have no `comparisons/*.yaml` registry entry and no
provenance block. The affected rerun never selects them and no bot commit has
touched them, so each holds the values from the commit that last changed it.

The previous version of this section, written in `cfae64354` (#167), reported
28 suites, 123 comparisons, 82 exact matches and 95.93% explained. The
`dispositioned_parity` history accounts for the difference:

- `42e378047` (#169, 2026-07-06) reran `be-pensioner-contributions` (`tscpe_s`)
  after rulespec-be#91 encoded the article 191 low-pension health floor and the
  2025-indexed article 68 solidarity thresholds, closing rulespec-be#89. The
  suite went from 1/6 to 6/6. The commit deleted
  `dispositions/be-pensioner-contributions.yaml` (five `axiom_encoding_gap`
  entries, a kind the rollup did not yet count as explained, hence the old
  95.93%) and set `be:tscpe_be` to `suite: be-pensioner-contributions` in
  `conformance/be.yaml`. Rollup: 28 suites, 123 comparisons, 87 exact, 100%
  explained.
- `f6df151bc` (#183, 2026-07-06) added `be-article-51-forfait` (5/5) and
  `be-work-bonus-credit` (2/4, two `upstream_engine_gap`). Rollup: 30, 132, 94.
- `9bd179697` (#500, merged 2026-08-21) refreshed `be-marital-quotient`
  (`tintb_be`, CIR 92 Article 87) against rulespec-be `7c85808a`. The suite went
  from 0/3 to 3/3 within the EUR 15 tolerance (absolute deltas 4.730748,
  0.001332 and 0.001688). The commit deleted `dispositions/be-marital-quotient.yaml`
  (three `explained_residual` entries). Rollup: 30, 132, 97.
- `46aa8f39a` (#508, merged 2026-08-22) added `be-pensioner-pit`,
  `be-replacement-income-pit` and `be-self-employment-pit`. Rollup: 33, 156,
  116, unchanged since.

`be-elderly-income-support` (`bsaoa_s`, GRAPA) has been published since
`f14904a2e` (#162): for the isolated no-resources senior, EUROMOD `bsaoa_s` =
Axiom GRAPA = 18,964.44, with the case's `euromod_policy_switch_overrides`
switching `bsaoa_be` on. The same commit added the missing `manifest.json` entry
for `be-social-assistance`, whose report had been in the parity rollup but not
in the manifest the dashboard loads its report list from. It also added two
tests in `tests/test_run_comparison.py`,
`test_euromod_be_registry_reports_are_published_and_manifested` and
`test_every_euromod_be_dashboard_report_is_manifested`, which fail if a BE
report is unmanifested or a registered BE suite is unpublished (#158 had
restored the `be-maternity-leave` and `be-birth-leave` entries). All 33 reports
are in the manifest. Nothing already-compared is marked missing above.

## Wave plan (gap workers, grouped)

Ordered by reasoned fiscal/population importance (labeled reasoned — no country report):

1. **PIT decomposition** (`tinna`/`tinfe`/`tintb`/`tinrg`/`tinmu`/`tinkt`) →
   CIR 92 (arts. 130–178 rate/credits; 145/1 ff. fiscal expenditures; 465–470bis
   communal; 17–22/171/269 movable) + Special Financing Law regional %. Highest
   weight; largest EUROMOD surface (`tinfe`+`tintb`+`tinna` = 209 functions).
   **Every listed policy now has a published suite** (rows 7–13 above; `tinfe`
   only through `tintcly_s`). Remaining: the per-row broadening notes.
2. ~~**Study allowances** (`bed_be`, `bed_s`) → Flemish Onderwijs codex +
   Fédération Wallonie-Bruxelles décret allocations d'études.~~ **DONE** —
   encoded (row 18) and compared by `be-study-allowance` (6/6; `cfae64354`,
   #167). Original note: Fully unencoded, 147 EUROMOD functions.
3. ~~**Unemployment** (`bun_be`, `bun_s`; switch on) → RD 25.11.1991.~~
   **DONE** — `be-unemployment` suite live (switch on per run), 4/4 dispositioned
   `upstream_engine_gap` (EUROMOD stylised `bun_s` vs statute Article 111/114/115).
   Broaden: household-status partner-income branches, degressivity phases 2/3,
   temporary unemployment. Original note:
   Encoded,
   never oracle-compared; core working-age transfer.
4. **Pensions / GRAPA / early-retirement** (`byr_be`, `bsaoa_be`) → RD No. 50 +
   RD 23.12.1996 (pensions); Law 22.03.2001 (GRAPA). **GRAPA DONE** —
   `be-elderly-income-support` published 1/1 (`f14904a2e`, #162). `byr_be` has
   nothing to compare (conformance exclusion `input_carrying`; see the
   passthrough table).
5. ~~**Pensioner & special contributions** (`tscpe_be`, `tscpe_s`) → Law
   30.03.1994 ch. 10 + ZIV/AMI RD 03.07.1996.~~ **DONE** —
   `be-pensioner-contributions` 6/6 and `tscpe_be` conformance-covered
   (`42e378047`, #169).
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
