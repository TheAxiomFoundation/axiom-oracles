# Germany dual-oracle playbook

## Status and scope

`de-worker-dual-oracle` is the realized direct EUROMOD↔GETTSIM baseline for
Germany. It runs 13 synthetic households through both independent engines and
compares six household amounts at an absolute tolerance of EUR 0.01. Because
neither side is Axiom, the dashboard presents it as an oracle cross-check and
the affected map has `repos: []`.

The committed live report is
`dashboard/public/data/euromod-gettsim-de-worker-dual-oracle.json`. Its pinned
result is 66 matches out of 78 comparisons, 12 expected differences, no engine
errors, and 100% disposition coverage.

## Engine contract

EUROMOD runs with this exact configuration:

```text
model_root=$EUROMOD_MODEL_ROOT_DE
country=DE
system=DE_2025
dataset=DE_2024_b1_2015_03_e2
template_dataset=DE_training_data
extra_columns=[drgn1]
```

GETTSIM runs version 1.2.1 with policy date `2025-06-30` and statutory rounding
enabled. The comparison process must use the locked GETTSIM dependency fork;
EUROMOD executes through the existing delegated `EUROMOD_PYTHON` subprocess.

### Gross-income bridge

EUROMOD receives nominal monthly `yem`. The DE dataset configuration uprates it
by exactly `61/56`; each GETTSIM case therefore receives
`einnahmen__bruttolohn_m = nominal × 61/56`. This makes both engines price the
same gross rather than hiding the dataset transformation in a tolerance.

Every employed EUROMOD row carries `yemmy=12`, `liwmy=12`, `lhw=40`, and
`liwwh=40`. The months field is load-bearing: DE social-insurance formulas cap
amounts using `threshold × rate × yemmy / 12`. Every row also carries
`drgn1=9` for West or `drgn1=4` for East. Pension and unemployment contributions
are gated on those region lists and silently become zero if `drgn1` is absent;
`DE_training_data` does not supply it, hence `extra_columns=[drgn1]`.

## Compared outputs and units

| Comparison amount | EUROMOD | GETTSIM | Report unit / reduction |
|---|---|---|---|
| Employee health insurance | `tsceehl_s` | `sozialversicherung.kranken.beitrag.betrag_versicherter_m` | monthly; SUM people |
| Employee pension insurance | `tsceepi_s` | `sozialversicherung.rente.beitrag.betrag_versicherter_m` | monthly; SUM people |
| Employee unemployment insurance | `tsceeui_s` | `sozialversicherung.arbeitslosen.beitrag.betrag_versicherter_m` | monthly; SUM people |
| Employee long-term-care insurance | `tsceeci_s` | `sozialversicherung.pflege.beitrag.betrag_versicherter_m` | monthly; SUM people |
| Income tax including Soli | `tin_s` | `einkommensteuer.betrag_y_sn` + `solidaritätszuschlag.betrag_y_sn` | annual; MAX each `*_y_sn`, then add |
| Kindergeld | `bch00_s` | `kindergeld.betrag_m` | monthly; SUM people |

The `tin_s` convention is important: EUROMOD's DE total already includes the
solidarity surcharge, so the GETTSIM comparison target is income tax plus Soli,
not income tax alone. GETTSIM replicates each `*_y_sn` tax-unit value across
joint partners; household aggregation must use MAX, never SUM. Ordinary
person-level monthly targets use SUM.

In DE_2025, the employee accident-insurance leg `tsceeac_s` is zero. The average
Zusatzbeitrag is folded into `tsceehl_s`, giving the 8.55% employee health rate.
`bchot_s` is Kinderzuschlag and is outside this comparison. The `tinta*_s`
columns remain useful tax diagnostics, and `yem` is the adapter's annualized
post-uprating gross anchor; neither replaces the six comparison outputs.

## Canonical grid

The fixed grid is defined in `axiom_oracles/suites/de_worker.py`:

- West single workers at EUR 500, 1,200, 2,500, 4,000, 5,500, 7,500, 9,000,
  and 12,000 nominal gross per month;
- an East EUR 4,000 twin;
- married couples at EUR 8,000/0 and EUR 4,000/2,000, jointly assessed; and
- single parents earning EUR 4,000 with one or two children, with
  `familie__alleinerziehend=True`, the Pflegeversicherung `hat_kinder` input,
  parent links, and explicit Kindergeld recipients.

Do not duplicate this grid in a runner or live test. Both engine anchor tests
select cases from the canonical builder.

## Child-eligibility grid (`de-kindergeld-eligibility`)

The canonical grid fixes its children at ages 7 and 10, so the § 32 EStG
conditions behind `qualifying_child_count` are never exercised. The second DE
case set, defined in `axiom_oracles/suites/de_kindergeld.py`, varies one
threshold per case on a single-parent West household at EUR 4,000: age 17;
age 18 in and not in training; age 24 and 25 in training; age 22 in training
working 20 and 25 hours a week; and one eligible plus one ineligible child. It
compares `kindergeld_monthly` and the new concept
`de:policies/kindergeld_eligibility_baseline#kindergeld_qualifying_child_count`
(GETTSIM `kindergeld.anzahl_ansprüche`; EUROMOD has no per-child eligibility
output, so its leg is the household amount).

GETTSIM 1.2.1 inputs are `kindergeld__in_ausbildung` and `arbeitsstunden_w` on
the child; its rule is `alter < 18 or (alter < 25 and in_ausbildung and
arbeitsstunden_w <= 20)`. EUROMOD receives `les = 6` / `dec = 1` for a child in
training, `les = 1` / `dec = 0` otherwise, and `lhw`/`liwwh` for the working
child. Live GETTSIM anchors are pinned in
`tests/test_gettsim_adapter.py::TestGettsimKindergeldEligibilityGridLive`.

Known oracle limits, recorded so they are not mistaken for findings:

- GETTSIM applies the 20-hour rule to every child in training; § 32 Abs. 4
  Satz 2–3 applies it only after a first training or degree is completed
  (DA-KG A 20.1). The 25-hour case pins the engine, not the statute.
- Neither oracle models the job-seeking ground for 18–20-year-olds (§ 32
  Abs. 4 Satz 1 Nr. 1), the disability ground (Nr. 3), foster children, the
  § 62 residence-title conditions, § 64 priority or § 65 exclusions. Those
  parts of the rulespec-de encoding will rest on statute-bound proof atoms.

The comparison config is `comparisons/de-kindergeld-eligibility.yaml`
(runner `gettsim-synthetic-compare`, same engine contract as the canonical
grid); its committed report is
`dashboard/public/data/euromod-gettsim-de-kindergeld-eligibility.json`.
First run (2026-09-08, EUROMOD J2.0+ DE_2025 and GETTSIM 1.2.1): 8 of 8
household amounts match to the cent — both engines pay EUR 255 for the
17-year-old, the 18- and 24-year-olds in training and the 20-hour worker, and
nothing for the 18-year-old not in training, the 25-year-old and the 25-hour
worker. The dual-oracle grid compares the household amount only, because
EUROMOD has no per-child eligibility output; GETTSIM's claim count is pinned
by the live anchors and attaches to the Axiom leg as
`kindergeld_qualifying_child_count` when rulespec-de encodes §§ 63/32 (the
concept id is named for the ledger's law-derived input for that reason).

Apple Silicon note for the EUROMOD leg: `/usr/local/bin/python3-intel64`
builds a venv whose `bin/python` is a universal binary that still launches
as arm64, so `EUROMOD_PYTHON` must point at a wrapper that runs
`exec arch -x86_64 <venv>/bin/python "$@"`, and the venv's wheels must be
installed through that wrapper. The JRC download rejects plain `curl`; send
browser-like `User-Agent`, `Accept` and `Referer` headers.

## Filed model findings

The 12 non-matching rows are not widened away. They retain the one-cent
tolerance and are classified in `dispositions/de-worker-dual-oracle.yaml` as
the repository-supported `upstream_engine_gap` type:

1. [JRC EUROMOD #21](https://github.com/ec-jrc/JRC-EUROMOD-software-source-code/issues/21):
   DE_2025 omits the EStG §10(1) no. 3 sentence 4 four-percent health-insurance
   deduction haircut and the §10c EUR 36 lump sum. Nine tax rows differ by
   EUROMOD−GETTSIM EUR -19.51 to about EUR -88.35 annually. Finding against
   EUROMOD; GETTSIM is statute-consistent.
2. [JRC EUROMOD #22](https://github.com/ec-jrc/JRC-EUROMOD-software-source-code/issues/22):
   DE_2025 deducts §32(6) child allowances while paying full Kindergeld without
   the §31 sentence 4 add-back. The one- and two-child tax rows differ by
   EUR -1,476.17 and EUR -2,824.99. Finding against EUROMOD.
3. [JRC EUROMOD #23](https://github.com/ec-jrc/JRC-EUROMOD-software-source-code/issues/23)
   (re-adjudicated 2026-08-19; supersedes the retracted
   [GETTSIM #1215](https://github.com/ttsim-dev/gettsim/issues/1215)):
   the childless Pflegeversicherung surcharge in the Midijob zone is an
   employee-only component computed on the SGB IV §20(2a) sentence 1 total
   base per BVV §2(2) sentences 3 and 6; EUROMOD applies it to the sentence 6
   employee base. At the committed EUR 1,200 grid row, EUROMOD−GETTSIM is
   EUR -1.06973/month. Finding against EUROMOD; GETTSIM is
   regulation-consistent. Our original #1215 filing against GETTSIM was
   rejected by the maintainer and retracted — the adjudication had not reached
   the controlling BVV provision.

All other grid comparisons match to the cent.

## Rule: encode before filing oracle findings (Max, 2026-08-19)

Never file an issue against an external oracle until we have encoded the
provision ourselves. A divergence discovered before our signed encoding exists
is recorded in dispositions as `unexplained` (or a neutral divergence record),
never as a filed upstream finding. File upstream only when our encoding exists
and the divergence survives against it: the complete-source-unit gate forces
the full mechanism — every base, every rounding rule, the procedural
regulations (the #1215 lesson: BVV §2(2)) — so the finding carries an
independent legal derivation by construction. The certification layer is
unchanged: `upstream_engine_gap` still requires maintainer acceptance or an
independent legal derivation; this rule gates the filing, that one gates the
classification.

## Run and validate

After syncing the locked GETTSIM fork (`uv sync --extra gettsim --extra dev`),
run from that environment with the EUROMOD delegate configured:

```bash
EUROMOD_MODEL_ROOT_DE=/path/to/EUROMOD_RELEASES_J2.0+ \
EUROMOD_PYTHON=/path/to/euromod-python \
DOTNET_ROOT=/path/to/dotnet-x64 \
PYTHONNET_RUNTIME=coreclr \
POLARS_SKIP_CPU_CHECK=1 \
uv run scripts/run_comparison.py de-worker-dual-oracle --summary
```

The command writes an ignored dated raw report and publishes the dispositioned
v2.1 dashboard report. Validate the committed evidence with:

```bash
uv run scripts/apply_dispositions.py --check
uv run pytest -q tests/test_de_worker_suite.py tests/test_de_worker_report.py
```

EUROMOD live tests skip unless both `EUROMOD_MODEL_ROOT_DE` and
`EUROMOD_PYTHON` are set. GETTSIM live tests skip when the optional package is
absent; the dedicated `gettsim-live` CI job installs its locked fork and runs
`tests/test_gettsim_adapter.py` without skips.
