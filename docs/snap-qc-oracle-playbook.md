# SNAP QC administrative data oracle playbook

The SNAP QC oracle validates Axiom SNAP encodings against real administrative
microdata rather than against a second engine. It replays the USDA SNAP Quality
Control public-use file (PUF) through the Axiom RuleSpec SNAP composition and
checks the file's own recomputed benefit and stage intermediates against Axiom's.
This playbook is the standing recipe — the one a future contributor follows to add
a fiscal year, add a state, or triage a mismatch class. The first jurisdiction is
Colorado FY2024:

```bash
uv run scripts/run_comparison.py co-snap-qc --summary
```

That runs the real replay where the `axiom-rules-engine` binary, a rulespec-us
checkout carrying the `fy-2024-cola` modules, and the downloaded QC file all exist,
and re-emits the committed dashboard report everywhere else (the same graceful-skip
contract the EUROMOD runner honors). The pins, sha256s, and archive members live in
`axiom_oracles/populations/snap_qc.py::SNAP_QC_PINS`; the loader (`load_qc_units`)
downloads, verifies, caches, and parses them; the replay harness is
`axiom_oracles/bridges/snap_qc_compare.py`. Everything below cites the FY2024 QC
technical documentation by its PDF page (the `qcfy2024_csv.zip` companion doc).

## 1. What the QC public-use file is

- FNS draws a monthly stratified random sample of active (participating) SNAP cases
  across the 50 states, DC, Guam, and the Virgin Islands; a QC reviewer re-interviews
  each household and re-derives every eligibility and benefit input. FY2024 pools the
  twelve monthly samples into 44,891 unit records for sample months October 2023
  through September 2024 (`YRMONTH` 202310–202409) (tech doc PDF p.15, p.64).
- The file is nationally representative when weighted by `HWGT`, the monthly sample
  weight; the documentation warns against within-state tabulations because the
  per-state sample is not itself representative (tech doc PDF p.64, p.77). Benefit
  parity does not tabulate by state, so this caveat does not bite — see §7 on
  replicate weights.
- `qc_pub_fy2024.csv` (44,891 rows, ~1,177 columns) is the redacted release of the
  restricted file. Colorado contributes 856 reviews. Person-level facts (`AGE1`–
  `AGE16`, per-source monthly income, relations) and unit-level facts (`CERTHHSZ`,
  shelter, `SUA1`/`SUA2`, `FSMEDEXP`, dependent-care and child-support expenses,
  `LIQRESOR`, `CAT_ELIG`, `STATE` FIPS, `HWGT`) are all present.

## 2. Ground truth: FSBEN is a constructed benefit

- `FSBEN` is not the benefit the household received. It is FNS/Mathematica's QC
  Minimodel recomputation of the *correct* benefit from the edited, internally
  consistent inputs and the official FY parameters (tech doc chapter IV, the QC
  Minimodel, PDF p.47; the QC-specific portion, PDF p.49). `RAWBEN` is the reported
  issuance; `STATUS` 1/2/3 = correct/over/under-issuance and `AMTERR` is the dollar
  error the reviewer recorded.
- Before recomputation the file is edited so that "certain relationships hold for
  all cases" (tech doc chapter III.B, *Obtaining file consistency*; standard editing
  procedures begin PDF p.27). Person-level income is reconciled and de-duplicated
  against unit-level totals, and a cascade of reconciliations runs until the
  calculated benefit matches the raw benefit. A unit is retained as *matching* when
  the calculated benefit is within $5 of the raw benefit (adjusted for any recorded
  payment error), after adjusting, in order, the dependent-care deduction, the
  excess-shelter deduction, and — for standard-medical-deduction-demonstration
  participants — the medical deduction (Steps 13a–13d, tech doc PDF p.32–33).
- That is the editing guarantee the oracle leans on: every retained unit is a
  complete, eligible, internally consistent benefit computation whose FSBEN is
  reproducible from its own recorded inputs. Constructed intermediates travel with it
  for stage-by-stage diagnosis — `FSGRINC` (gross), `FSNETINC` (net),
  `FSERNDED`/`FSSTDDED`/`FSMEDDED`/`FSDEPDED`/`FSCSDED`/`FSSLTDED` (deductions;
  `FSSLTDED` is the final calculated excess-shelter deduction — the reported
  `SHELDED` is pre-edit and the codebook redirects to `FSSLTDED`),
  `GROSSCRN`/`NETSCRN` and `FSGRTEST`/`FSNETEST` (screens), and
  `MINIMUM_BEN`/`FSMINBEN` (tech doc chapter V codebook, PDF p.63; constructed-
  variable overview V.1, PDF p.63).

## 3. What the oracle validates — and what it does not

- The replay scores the benefit computation, not the eligibility screening. The
  public file already dropped every incomplete review and every ineligible unit (§4),
  and the records carry no application dates for initial-month proration, so the
  mapper feeds the composition's passing defaults for the eligibility gates (work
  registration/ABAWD, student, SSN, citizenship). Concretely, the work-requirement
  member age stays pinned at the template's exempting value while the QC member's
  real age drives `snap_member_is_elderly_or_disabled` — the fact the benefit chain
  actually consumes (shelter cap, medical entitlement, gross-test path) — mirroring
  the `snap_populace` work-projection convention. The comparison covers only the
  benefit chain:
  gross income → each deduction → net income → income screens → maximum allotment →
  allotment. This mirrors the `snap_populace` convention of comparing
  `snap_regular_month_allotment` (not the take-up-adjusted `snap`) and is stated
  explicitly in the bridge module docstring.
- An eligibility-side divergence is therefore out of scope *by construction* and is
  dispositioned as such, not scored as a benefit error. The oracle's claim is narrow
  and strong: given the QC unit's edited inputs, does Axiom reproduce FNS's own
  benefit arithmetic? This is the US analogue of the BEAMM full-admin-returns
  income-tax check — administrative ground truth, not a second model's opinion.

## 4. Exclusions

Two kinds. The upstream drops are already gone from the public file — the loader
must not re-filter them (that would double-count what Mathematica already removed);
it documents them. The loader's own exclusions are each counted by reason in
`QcExclusionLog`, never silent.

| exclusion | flag / field | removed by | why |
|---|---|---|---|
| incomplete reviews | `REVDISP = 3` | FNS upstream (already absent) | not a completed benefit computation (tech doc PDF p.17–18) |
| not subject to review | `REVDISP = 2` | FNS upstream | outside the active QC universe (PDF p.17) |
| ineligible / non-compliance findings | `STATUS = 4`; listed-in-error actives | FNS upstream | no positive benefit to reproduce (PDF p.16–17) |
| MFIP units | `MN_FIP` | loader (counted) | the Minnesota Family Investment Program uses a separate benefit procedure — only a 50% earnings deduction, all other deductions coded missing (Table F.3 note, PDF p.180; MFIP benefits Table F.8, PDF p.186) |
| SSI-CAP units | SSI-CAP participation flag | loader (counted) | Combined Application Projects use separate procedures; standard-benefit units have deductions coded missing (Table F.3 note, PDF p.180; SSI-CAP shelter Table F.23, PDF p.192) |
| missing benefit | `FSBEN` missing or 0 | loader (counted) | no constructed benefit to replay (the file's minimum is $1) |
| missing certified size | `CERTHHSZ` missing or 0 | loader (counted) | no unit size to drive `household_size` |

Of the FY2024 sample, 6,332 reviews were dropped as incomplete and 46,418 were
completed; a further set of ineligible and listed-in-error actives left 44,891 units
in the public file (tech doc Table II.1, PDF p.18). Demonstration-state components
(§7, §9) are transformed rather than excluded.

## 5. Getting the data (pins, caching, the 403)

- `SNAP_QC_PINS` pins each fiscal year to its CSV-zip URL, sha256, and archive
  member. FY2024: `https://snapqcdata.net/sites/default/files/2026-05/qcfy2024_csv.zip`,
  sha256 `0f3230a4318307d3088382546095eebfde03e781da6f65c9eac7f077bd4263f4`, member
  `qc_pub_fy2024.csv`. The loader refuses unpinned fiscal years outright — the
  postings are immutable, so there is no allow-unpinned escape hatch.
- The host 403s non-browser user agents. The loader's lazily imported `requests`
  call sends a Chrome UA string and `Referer: https://snapqcdata.net/datafiles`; a
  plain `curl`/`urllib` fetch is rejected. Downloads cache under
  `~/.cache/axiom-oracles/snap-qc/`. Point `AXIOM_SNAP_QC_DATA_DIR` at a directory
  that already holds `qc_pub_fy{YYYY}.csv` to skip the download entirely — that is
  also how the engine-gated live test and a local real run pick up the file. The
  sha256 is verified after download with the populace-style remediation message.
- Until the fy-2024-cola modules merge to rulespec-us main, a local run also needs
  `AXIOM_SNAP_QC_RULESPEC_ROOT` pointed at a checkout that carries them (and
  `AXIOM_SNAP_QC_AXIOM_BINARY` at a built engine when the default debug-path
  resolution does not apply). The `scripts/run_comparison.py co-snap-qc` runner
  honors both alongside the yaml parameters; absent any of the three
  prerequisites it degrades to re-emitting the committed dashboard report.

## 6. The fiscal-year gap and the overlay

Only fy-2026 SNAP COLA modules and compositions exist in rulespec-us today, and the
Axiom engine selects a parameter version by the latest `effective_from <=
period.start` (period end is ignored). The entire federal-regulation (7 CFR 273) and
Colorado-manual (10 CCR 2506-1) chain is snapshot-dated `2025-10-01`, so evaluating
at a true FY2024 period reads the wrong vintage — true-period FY2024 evaluation is
impossible today. Broadly re-dating the chain without per-provision legal research
would fabricate legislative history, so it was rejected (filed upstream: snapshot
dating breaks historical-period evaluation).

The pilot mechanism instead evaluates an FY2024-parameter composition at the nominal
period `2026-01`:

- fy-2024-cola modules (under `us/policies/usda/snap/fy-2024-cola/` —
  `maximum-allotments.yaml`, `deductions.yaml`, `income-eligibility-standards.yaml`)
  are truthfully dated `effective_from 2023-10-01`; at `2026-01` they resolve as the
  sole version at or
  before the period. Their values come from the FNS FY2024 COLA memo (corpus
  `us/guidance/usda/fns/snap-fy2024-cola`, re-archived 2026-07-08 from the Wayback
  capture of the official FNS URL after the earlier archive proved to be a 404 page
  — TheAxiomFoundation/axiom-corpus#281) and are cross-checked
  against tech doc Appendix F (max allotments Table F.5 PDF p.182; deductions Table
  F.3 PDF p.180; income screens Tables F.1/F.2 PDF p.179; minimum benefit Table F.6
  PDF p.182).
- `bridges/rulespec_overlay.py` materializes a patched overlay root from the overlay
  spec `bridges/overlays/us-co-snap-fy2024.yaml`: it copies the referenced prefix
  trees (`us/`, `us-co/`) into a temporary root that reuses the monorepo basename,
  rewrites the SNAP COLA module ids from `fy-2026-cola` to `fy-2024-cola` across the
  sixteen federal and Colorado reg/manual files, and applies four structural YAML
  patches to the Colorado standard-utility-allowance amounts in
  `10-ccr-2506-1/4.407.31.yaml` — heating/cooling 594→560, basic 377→356,
  one-utility 71→67, telephone 97→91 (tech doc Table F.7, PDF p.183). Each patch
  asserts its from-value first, so a moved base repo fails loudly instead of silently
  mispatching. The engine then runs with `AXIOM_RULESPEC_REPO_ROOTS` set to the
  overlay root alone: the engine unions module ids across roots rather than
  shadowing, so a sparse overlay in front of the real monorepo would compile both
  COLA years and abort on duplicate rules.
- Caveat, carried in the report provenance and here: the rule *structure* is the
  current-manual snapshot, not the FY2024 manual. The benefit-calculation chain is
  structurally stable FY2024→FY2026 (only parameters moved), but genuine FY2024
  structural drift (for example the FRA-2023 ABAWD age phase-in) surfaces as a
  dispositioned mismatch class, never as a silent error.
- This apparatus is temporary. `TheAxiomFoundation/rulespec-us#759` inverts the
  version chain so historical periods resolve correctly; once it lands, a comparison
  sets a true FY2024 period and the overlay is deleted (§8).

Verification anchor: the proven worked example — one person,
`snap_countable_earned_income` 1000, `household_shelter_costs_incurred` 500,
heating/cooling utility flag true — evaluates to allotment 291, net income 0,
excess-shelter deduction 672, standard deduction 198, HCSUA 560, matching the FY2024
Colorado parameters exactly.

## 7. Conventions the comparisons must respect

- **Whole dollars.** SNAP allotments and the QC amounts are whole-dollar, so the
  benefit is compared exactly after rounding to whole dollars (`--tolerance 0`), with
  stage intermediates at `--stage-tolerance 1` to absorb the file's per-field
  rounding. The homeless shelter deduction, statutorily $179.66, is recorded as $180
  in the QC file (whole-dollar rounding; tech doc Table F.3 note, PDF p.180) — expect
  and disposition that one-dollar artifact rather than chase it.
- **Utility tiers when standard, `UTIL` when not.** The QC `SUA1` code maps to the
  Colorado composition's utility-allowance flags (heating/cooling, limited,
  single-utility, telephone, none) so the awarded allowance exercises the encoded
  FY2024 amounts — the same "type projection" the `snap_populace` bridge uses for
  oracle parity. But `UTIL` (the QC-applied utility amount) is authoritative: the
  codebook notes SUA1 itself was edited for consistency with UTIL, so when UTIL
  differs from the tier's standard amount (an actual-expense claim, SUA1 = 2, or a
  prorated allowance), the mapper drops the flags and carries UTIL as an incurred
  shelter cost instead.
- **Medical expenses: feed the applied deduction, not the reported excess.**
  `FSMEDEXP` is the allowable medical expense *in excess of $35* and `FSMEDDED`
  is the deduction FNS applied (codebook PDF p.84). The two are equal in
  ordinary states, but in standard-medical-deduction demonstration states
  `FSMEDDED` is a flat standard that can differ from the excess (10 FY2024 rows
  nationally, none in Colorado; Table F.4, PDF p.181). The mapper therefore
  feeds `FSMEDDED + 35` into the engine's `total − 35` rule, which reproduces
  the applied deduction in both kinds of state; only units with an elderly or
  disabled member are entitled, which the engine gates itself.
- **The homeless shelter deduction is a flat path.** `HOMEDED = 3` units receive
  the standard homeless shelter deduction; the QC file zeroes `FSSLTDED` for them
  by construction (codebook PDF p.85), so the mapper raises the composition's
  homeless flags, raises no utility flag, and the engine takes the flat-deduction
  path. First-run finding: the federal 273.10 encoding caps that deduction at the
  stale CFR literal $143 where the statute indexes it ($179.66 in FY 2024) —
  TheAxiomFoundation/rulespec-us#761, carried as `axiom_encoding_gap` dispositions
  until fixed.
- **Child support: exclusion, not deduction.** Colorado elects the 7 USC
  2014(e)(4) child-support income exclusion, so the composition removes child
  support paid from countable gross income while the QC file books the same
  amount as a deduction (`FSCSDED`; the `FSCSEXP` codebook entry documents the
  state split). Net income is identical either way; the gross-income comparison
  nets `FSCSDED` out of `FSGRINC`.
- **Whole-dollar rounding is a known encoding gap.** The encoded chain carries
  cents (20 percent earned-income deduction, half-income shelter subtraction)
  where the FNS Minimodel computes with whole dollars at each step; when the
  fractional net crosses a dollar boundary the benefit flips by exactly $1.
  TheAxiomFoundation/rulespec-us#762 tracks encoding the rounding steps; the
  affected rows are `axiom_encoding_gap` dispositions until then.
- **Replicate weights are not needed for parity.** The QC file ships `HWGT` plus
  replicate weights for design-consistent variance estimation. Per-unit benefit
  reproduction uses neither: `HWGT` is applied only to report a caseload-weighted
  match rate alongside the unweighted one, and the replicate weights — for standard
  errors of population estimates — are irrelevant to whether Axiom reproduces a given
  unit's FSBEN.

## 8. Adding a fiscal year

1. **Pin the file.** Add a `SnapQcPin(fiscal_year, url, sha256, archive_member)` to
   `SNAP_QC_PINS` from that year's `qcfy{YYYY}_csv.zip` posting (compute the sha256
   from the downloaded zip). FY2023 is already pinned as a second data point.
2. **Encode the COLA.** Add the `maximum-allotments.yaml`, `deductions.yaml`, and
   `income-eligibility-standards.yaml` modules under
   `us/policies/usda/snap/fy-{YYYY}-cola/` to rulespec-us, dated `effective_from
   {YYYY-1}-10-01`, valued from that year's FNS COLA memo and cross-checked against
   the year's Appendix F (Tables F.1, F.2, F.3, F.5, F.6). Mirror the fy-2026 module
   structure so the ids line up.
3. **Point the overlay (or invert).** Until rulespec-us#759 lands, add an overlay
   spec whose `module_id_rewrites` map `fy-2026-cola → fy-{YYYY}-cola` and whose
   `parameter_patches` carry that year's per-state SUA amounts (Table F.7). After #759
   lands, skip the overlay entirely: set the comparison's period to the true fiscal
   year and let the engine resolve the dated modules directly.

## 9. Adding a state

1. **Jurisdiction config.** Add a `QcJurisdiction` entry in
   `bridges/snap_qc_compare.py` wrapping `snap_populace.JURISDICTION_CONFIGS`
   `["us-<st>"]`, its fy-2024 composition and test template, `state_fips`, and
   `supported_fiscal_years`. `load_qc_units(..., state_fips=…)` filters the national
   file to that state.
2. **SUA sources.** The state's standard utility allowances come from tech doc
   Appendix F, Table F.7 (PDF p.183) cross-checked against the state's FNS SUA memo or
   state manual; encode them as the overlay's parameter patches (or as fy-{YYYY}-cola
   state modules once #759 lands). Some states publish tiered SUAs by household size
   (Arizona, Hawaii) — encode the tier the composition selects.
3. **Special-program caveats.** Check the state against the demonstration and CAP
   tables before trusting its deduction chain. Standard-medical-deduction-demonstration
   states (Table F.4 / Table III.4, PDF p.181 / printed p.34) need the §7 medical
   transform; SSI-CAP states (Tables F.9–F.23) and MFIP (Minnesota only) are excluded
   per §4 because their benefits bypass the deduction chain. A state that standardizes
   shelter for SSI-CAP (Table F.23, PDF p.192) has those deductions coded missing and
   must not be scored on them.

## Track record

Colorado FY2024 is the pilot. The overlay compiles the existing
`us-co/policies/cdhs/snap/fy-2026-benefit-calculation.yaml` under the FY2024
parameters and reproduces the worked example above — allotment 291, standard
deduction 198, excess-shelter deduction 672, HCSUA 560 — to the dollar. Running the
full 856-review Colorado subset turns the editing guarantee into a benefit-computation
match rate and a stage-keyed mismatch taxonomy, so a real encoding gap shows up as a
dispositioned class against administrative ground truth rather than as a green light
nobody checked.
