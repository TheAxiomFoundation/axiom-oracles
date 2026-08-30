# EUROMOD-platform oracle playbook

Every model built on the EUROMOD software platform — the JRC's EUROMOD
release (all EU member states), CeMPA's UKMOD, and UNU-WIDER's SOUTHMOD
family — runs through the same `EuromodPlatformRunner`. This playbook is
the standing recipe for wiring the oracle when an Axiom country model
(`rulespec-<cc>`) starts, so cross-engine validation exists from the first
encoded module.

The per-country readiness matrix for the current EUROMOD release lives at
`axiom_oracles/data/euromod_country_readiness.json` (probed live, all 28
country directories runnable). Regenerate it against a new release with
`scripts/probe_euromod_readiness.py`.

## 1. Get the model (no licensed microdata needed, ever)

Per-case oracle validation uses hypothetical households; only the policy
XMLs and a bundled demo-schema file are required.

| family | countries | acquisition |
|---|---|---|
| EUROMOD (JRC) | all EU member states | direct download, no registration: `EUROMOD_RELEASES_J*.zip` from the JRC download page |
| UKMOD (CeMPA) | UK + nations | `git clone --branch <release> https://github.com/centreformicrosimulation/UKMOD-PUBLIC` |
| SOUTHMOD (UNU-WIDER) | ET, GH, MZ, TZ, UG, ZM, RW, SA (SAMOD), VN, EC (ECUAMOD), BO, PE, CO, … | free non-commercial access via the UNU-WIDER SOUTHMOD request form (per-model bundles; same engine, so the adapter applies unchanged — verify each bundle ships a demo/training dataset and note its DRD provenance) |

Each release documents its demo data in a per-country DRD
(`Input/DRD_<CC>_training_data.xls`). The EUROMOD training datasets are
synthetic hypothetical-household grids produced by HHoT with
population-ish weights (per their own DRDs) — legitimate schema templates
and support strata, **not** representativeness sources.

## 2. Execution environment

The `euromod` PyPI connector bundles the real EM engine as .NET
assemblies; `EM_Executable.dll` is x64-only, so the adapter always drives
it in a subprocess pointed at by `EUROMOD_PYTHON`:

- Linux/CI (x86_64): a plain venv with `uv pip install euromod`.
- Apple Silicon: a Rosetta venv — x86_64 Python, x64 .NET 10 via
  `dotnet-install.sh`, `polars-lts-cpu` instead of `polars`, and the
  manylinux wheel unzipped into site-packages (see the README section).

## 3. Probe the country

```bash
EUROMOD_PYTHON=... DOTNET_ROOT=... \
  uv run scripts/probe_euromod_readiness.py <model_root> [CC ...]
```

The probe answers, per country: which systems exist, whether the bundled
training-data name runs, and — when it does not — which real dataset
*configuration* name to run under instead.

## 4. The dataset-name gating workaround

Many country spines gate content on real dataset names
(`Run_Cond IsUsedDatabase` with patterns like `be_20??_??_????_??_??`);
the engine skips registering gated income lists while still compiling the
identically gated formulas that reference them, so runs under the bundled
training name abort at parameter preparation
(ec-jrc/JRC-EUROMOD-software-source-code#4). In the current EUROMOD
release this affects 21 of 28 country directories. The adapter absorbs
it:

```python
EuromodPlatformRunner(
    model_root=..., country="BE", system="BE_2025",
    dataset="BE_2024_c1_2015_03_e2",      # real configuration name (readiness matrix)
    template_dataset="BE_training_data",  # bundled schema for the input rows
)
```

No licensed file is read — the configuration supplies uprating/monetary
semantics; the rows are ours.

## 5. Conventions the comparisons must respect

- **Units**: demo datasets are monthly; case facts are annual. The
  adapter divides inputs by 12 and annualizes outputs.
- **Uprating**: dataset configurations uprate incomes to the system year.
  Bridge on the engine's returned post-uprating gross (`yem`) — see #76.
  Until the bridge lands, engine agreement shows up as a uniform ratio
  equal to the uprating factor.
- **Outputs**: `tin_s` (simulated income tax) and `tscee_s` (employee
  social contributions) are the standard first bindings; country-specific
  instruments come from the release's data codebook
  (`Documentation/EM_data_codebook_*.xlsm`).
- **Per-household engine runs**: model spines consume fixed-seed random
  draws one household at a time in dataset order (benefit take-up
  corrections; Belgium's `random_be`, UKMOD's `random_uk`), so households
  sharing an engine run get batch-position-dependent benefits. The worker
  therefore loads the model once per batch and runs each household as its
  own engine run — every case reproduces its solo baseline at any batch
  size (issue ledger:
  `euromod-be-2025-bed-study-allowance-batch-position-contamination`).
- **Take-up neutralization**: where a benefit's solo draw still marks
  non-take (UKMOD Pension Credit) or take-up rates could drift under the
  solo draw, pin the take-up constants to 1.0 with
  `euromod_constant_overrides` (comparison parameter → env
  `EUROMOD_CONSTANT_OVERRIDES`, `$name=value` pairs). The worker patches
  the DefConst values into the system XML on the model overlay; the
  connector's `constantsToOverwrite` kwarg does not reach DefConst
  constants.

## 6. Wiring a new country (the Belgium pattern, PR #75)

1. **Concepts**: add durable-id concepts in `core/case.py` pointing at the
   rulespec modules (`<cc>:statutes/...#rule`) and map them to EUROMOD
   output columns in `comparison/mappings`.
2. **Suites**: a `<cc>-worker-*` synthetic suite (mirror
   `suites/be_worker.py`) over an income grid that exercises the encoded
   brackets/caps; explicit `axiom_inputs` pin the supplied boundaries.
3. **External composition**: RuleSpec may expose only concepts stated in public
   policy documents. Compose end-to-end liability, routing, income-list, and
   behavioral surfaces in the oracle or application layer from those
   documentary outputs; never add a comparator-shaped RuleSpec module.
4. **Issue ledger**: engine/model findings go in
   `axiom_oracles/data/euromod_issues.json` (dashboard panel reads it);
   encoding findings go on the `rulespec-<cc>` repo with the exact
   arithmetic decomposition (see TheAxiomFoundation/rulespec-be#1 for the
   template).
5. **Expectations**: hand-compute against post-uprating gross, exactly as
   `tests/test_euromod_adapter.py::TestUkmodLive` does.

Track record so far: UKMOD reproduces hand-computed 2025-26 UK law to the
pound; EUROMOD Belgium agrees with rulespec-be on employee SSC at the
statutory 13.07% exactly (modulo the uprating bridge), and the first PIT
comparison surfaced two real encoding gaps within minutes of running —
which is the point.
