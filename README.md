# Axiom Oracles

Unified validation and oracle-comparison tooling for policy engines.

This repo is the home for executable program comparisons across:

- PolicyEngine
- TAXSIM
- Atlanta Fed PRD
- ACCESS NYC
- UKMOD / EUROMOD (recorded and live)
- entitledto (recorded per-council UK Council Tax Reduction reference)
- Axiom RuleSpec/runtime programs

The core idea is to keep each external system behind an adapter, then compare
them through thin, concept-keyed cases and normalized program outputs. ACCESS NYC
is the first implemented external adapter because its public Drools rules and
Screening API make it a useful oracle for NYC benefit eligibility.

This repo should stay a library/CLI boundary, not a product UI. Axiom apps can
render comparison reports, but adapters, concept bindings, and mismatch JSON live
here.

## Architecture

```text
Thin concept-keyed cases
        |
        +-- ACCESS NYC adapter
        +-- entitledto adapter (recorded fixtures)
        +-- PolicyEngine adapter
        +-- TAXSIM adapter
        +-- PRD adapter
        +-- Axiom adapter
        |
Normalized engine outputs
        |
Comparator and audit reports
```

The current implementation includes:

- generic engine result and comparison primitives
- concept-keyed `Case` and `Entity` objects
- the shared PolicyEngine/Populace oracle-bridge layer (`axiom_oracles/bridges/`,
  extracted from axiom-encode — see `axiom_oracles/bridges/README.md`)
- Enhanced CPS-backed population loading through PolicyEngine microsimulation
- ACCESS NYC Screening API payload mapper
- ACCESS NYC API runner
- ACCESS NYC static Drools audit checks
- target-scope metadata and locale-aware concept mapping config for ACCESS NYC
  to PolicyEngine overlap
- stable JSON comparison reports with mismatch taxonomy and weighted aggregates
- generic `compare <left> <right>` CLI
- thin package-runner adapters for TAXSIM and PRD
- Axiom RuleSpec adapter backed by `axiom-rules`

## Install

Requires Python 3.13 or newer.

```bash
uv pip install -e ".[dev]"
```

Install the PolicyEngine extra only when running PE calculations:

```bash
uv pip install -e ".[policyengine,dev]"
```

Install the TAXSIM extra only when running local TAXSIM comparisons:

```bash
uv pip install -e ".[taxsim,dev]"
```

Install the ACCESS NYC Python extra only when running the local Python
replatform:

```bash
uv pip install -e ".[accessnyc-python,dev]"
```

Install the GETTSIM extra only when running German (GETTSIM) comparisons — via
the locked fork, since a bare pip install can drift the pinned engine:

```bash
uv sync --extra gettsim --extra dev
```

## ACCESS NYC Rule Audit

The static audit does not need API credentials. It inspects the public Drools
rules and can compare active returned `S2R` codes to NYC's public benefits
dataset.

```bash
axiom-oracles accessnyc audit \
  --rules-dir /tmp/access-nyc-rules-review/accessnyc/rules
```

JSON output:

```bash
axiom-oracles accessnyc audit \
  --rules-dir /tmp/access-nyc-rules-review/accessnyc/rules \
  --json
```

The initial checks cover:

- active rule codes missing from the public benefits dataset
- public dataset codes without active rule returns
- Medicaid to Essential Plan threshold gaps/overlaps
- Medicaid to Child Health Plus threshold overlaps
- likely same-person binding bugs where separate `Person(...)` patterns can
  match different household members

## ACCESS NYC API Oracle

Set either a token or username/password:

```bash
export ACCESSNYC_TOKEN=...
```

or:

```bash
export ACCESSNYC_USERNAME=...
export ACCESSNYC_PASSWORD=...
```

Then run the generic comparison CLI:

```bash
axiom-oracles compare accessnyc policyengine
```

By default this uses the Enhanced CPS population, resolves the target
geographic intersection automatically, and samples 50 households. For ACCESS NYC
vs PolicyEngine, that means the NYC Enhanced CPS-derived dataset:

```text
hf://policyengine/policyengine-us-data/cities/NYC.h5
```

Use a different sample size or period with:

```bash
axiom-oracles compare accessnyc policyengine \
  --sample-size 250 \
  --period 2026-05
```

To run against NYCOpportunity's local Python replatform instead of the hosted
API:

```bash
axiom-oracles compare accessnyc policyengine \
  --sample-size 250 \
  --accessnyc-mode python \
  --accessnyc-python-path /path/to/benefits-screening-api \
  --output reports/accessnyc-policyengine-ecps.json
```

`--population enhanced-cps` is the default validation path. `--suite` is only
used for `--population synthetic`, which is intended for targeted regression
and boundary probes:

```bash
axiom-oracles compare accessnyc policyengine \
  --population synthetic \
  --suite nyc-synthetic
```

`--sample-size` also applies to synthetic suites, which is useful for quick
oracle smoke tests.

Program concepts are the intersection of the compared engines' mappings after
target-scope and locale filtering. ACCESS NYC is scoped to the NYC Census place
GEOID (`{type: census_place, geoid: "3651000"}`), while PolicyEngine and Axiom
are scoped to the US. Comparing ACCESS NYC to PolicyEngine therefore resolves
to the NYC scope automatically.

Parent concepts compare only the parent output unless `--include-components` is
supplied. For example, `--concept us:tax/federal-income-tax#liability` compares
federal liability only; add `--include-components` when you also want mapped
breakdowns like standard deduction, taxable income, EITC, CTC, and AMT.
Use `--axiom-batch-size` to tune large RuleSpec runs over the full Enhanced CPS
population; the default favors bounded Rust execution over maximum throughput.
Use `--comparison-batch-size` to tune how many cases are prepared, executed, and
accumulated per pass. JSON reports written with `--output` stream per-case rows
through a temporary JSONL file, so full-population runs do not need to retain all
engine results and report cases in memory.

Reports include per-case mismatches plus weighted aggregate summaries when the
population supplies household weights. The JSON report's `summary.weighted`
block gives weighted match/mismatch totals, and `aggregates` gives per-concept
weighted match rates, eligibility-rate deltas, or weighted amount differences.
The report also includes a `schema_version`, left/right engine names, concept
tolerances and priorities, and `mismatches_by_kind` so downstream apps can render
the same report without duplicating comparison logic.

Comparison mappings define the requested output surface, independently of which
values the engines return. A missing value on either or both sides remains a
mismatch; a summed target requires every component, including explicit zeroes.
Duplicate or unpaired result IDs and non-finite values raise `ValueError` instead
of producing a partial agreement report. The report accumulator also checks that
each submitted case and each requested output appears exactly once, including
case IDs across streaming batches. Case-specific output selections remain scoped
to `Case.outputs`; an empty comparison is not a successful case. The CLI reports
these validation failures and does not write the incomplete report. This validates
comparison completeness, not the independence or authority of either engine.

TAXSIM and PRD are exposed as package adapters rather than separate comparison
systems. The TAXSIM adapter projects thin `Case` objects to TAXSIM rows from
period, geography, age, relation, and earned-income facts, while still accepting
explicit `metadata["taxsim_input"]` rows for hand-authored fixtures. The bundled
TAXSIM executable currently supports tax years through 2024, so comparisons
involving TAXSIM default to tax year 2024 unless `--period` is supplied. PRD
cases carry an external PRD household object in `metadata["prd_household"]` or
use a mapper. The adapters normalize those package outputs to the same
`EngineResult` shape consumed by the comparator. `compare policyengine taxsim`
defaults to the explicit tax concept intersection (`fiitax` and `siitax` with a
$15 tolerance), while
`compare policyengine prd` currently maps the PRD SNAP value output to
PolicyEngine `snap`.

See [docs/policyengine-taxsim.md](docs/policyengine-taxsim.md) for the
PolicyEngine/TAXSIM comparison path, state-code handling, residual smoke-test
mismatches, and upstream triage workflow.

## Axiom RuleSpec Oracle

The Axiom adapter executes a RuleSpec program through the local `axiom-rules`
binary and compares its outputs through the same concept mapping layer:

```bash
axiom-oracles compare axiom policyengine \
  --population enhanced-cps \
  --category tax \
  --period 2026 \
  --axiom-program /path/to/rulespec-us/statutes/26/6401.yaml
```

Cases must carry Axiom runtime inputs in `metadata["axiom_inputs"]` or as
case facts keyed by absolute `#input.` RuleSpec references. The adapter does not
invent missing legal inputs; incomplete ECPS projections are reported as Axiom
execution errors in the comparison report.

Local Drools execution is not currently available from the public
`ACCESS-NYC-Rules` repo alone. The repo contains the `.drl` files, but not the
compiled Java request/response/fact classes or a runnable Screening API/KJAR.
The public `NYCOpportunity/benefits-screening-api` repo is a separate WIP
Python replatform and can run locally through `--accessnyc-mode python`.
`--accessnyc-mode drools` exists to make the Drools limitation explicit and to
define where a future local runner should attach.

## EUROMOD-Platform Oracle (UKMOD, EUROMOD)

`EuromodPlatformRunner` runs concept-keyed cases through any model built on
the EUROMOD software platform — CeMPA's UKMOD for the UK and the JRC's
EUROMOD release for Belgium and the other member states. Both ship openly
downloadable policy XMLs and demo input data, so per-case oracle validation
needs no licensed microdata:

- UKMOD: `git clone --branch B2026.03 https://github.com/centreformicrosimulation/UKMOD-PUBLIC`
- EUROMOD: the `EUROMOD_RELEASES_J*.zip` bundle from the JRC download page

The engine (`EM_Executable.dll`, .NET) executes via the official `euromod`
PyPI connector in a subprocess. The DLL requires an x86_64 process, so the
adapter targets an execution environment named by `EUROMOD_PYTHON`: on
Linux/CI a normal x86_64 venv with `uv pip install euromod`, on Apple
Silicon a Rosetta venv (x86_64 Python + x64 .NET via `dotnet-install.sh`,
`polars-lts-cpu` instead of `polars`, and the manylinux wheel unpacked into
site-packages).

```python
from axiom_oracles.adapters.euromod import EuromodPlatformRunner

runner = EuromodPlatformRunner(
    model_root="~/Downloads/UKMOD_PUBLIC_B2026.03",
    country="UK",
    system="UK_2025",
)
results = runner.run_cases(cases, variables=["tin_s", "tscee_s", "yem"])
```

Conventions the adapter owns: case facts are annual while the demo
datasets are monthly (inputs divide by 12, outputs annualize back), and
the datasets uprate incomes from their data year to the system year — so
comparisons bridge on the engine's own post-uprating gross (`yem`), which
is returned alongside the outputs. Batches share one worker subprocess
(one model load) but every household executes as its own engine run:
EUROMOD-platform spines consume fixed-seed random draws per household in
dataset order (benefit take-up corrections such as Belgium `bed_be`'s or
UKMOD Universal Credit's), so households sharing an engine run would get
batch-position-dependent results (issue ledger:
`euromod-be-2025-bed-study-allowance-batch-position-contamination`).
Stochastic take-up corrections themselves can be neutralized with
`constant_overrides` (metadata `euromod_constant_overrides`, env
`EUROMOD_CONSTANT_OVERRIDES`, e.g. `$bed_FlTakeUp=1.0`): the worker
patches the named DefConst values into the system XML on the model
overlay — the euromod connector's `constantsToOverwrite` kwarg silently
ignores DefConst constants. The live UKMOD tests reproduce hand-computed
2025-26 income tax and employee NICs; the live EUROMOD Belgium tests
recover the statutory 13.07% employee social contribution exactly and
progressive PIT.

One EUROMOD-release quirk the adapter absorbs: some model content is
gated on the *dataset name* (`Run_Cond IsUsedDatabase` patterns matching
real SILC files), and the engine skips registering gated income lists
while still compiling identically gated formulas that reference them —
so running under the bundled `BE_training_data` name aborts at parameter
preparation (`Operand index does not contain operand il_xs_hl06`; raised
upstream). Per-case runs therefore pass a real dataset *configuration*
name (`dataset="BE_2024_c1_2015_03_e2"`) while templating input rows
from the bundled training schema (`template_dataset="BE_training_data"`)
— no licensed file is ever read.

### Population source: populace-us (the default)

The US representative population is the **certified populace-us artifact**
(`populace://policyengine/populace-us/populace_us_2024.h5`, resolved
through the Hugging Face dataset repo). The reference is **content-pinned**
to a specific Hugging Face revision with a verified sha256
(`axiom_oracles/populations/populace_us.py::POPULACE_PINS`) — it does NOT
follow HF-latest. Latest currently points at a sparse L0 refit that zeroes
untargeted input bases (IRA/HSA/self-employed pension/childcare and ~80
other engine inputs are dead in that artifact, PolicyEngine/populace#278),
so a comparison run against latest would silently score against ~$0 bases.
The pin is the dense release certified in PolicyEngine bundle 4.18.6/4.18.7;
re-pin once the post-#279 rebuilt dense release is published and certified.
The enhanced CPS is retired for every scope populace can serve; the one
remaining eCPS-derived path is the NYC per-city file, because populace-us
carries no place/county geography yet (PolicyEngine/populace#204) — it
retires the moment the populace spine grows place grain. Override any run
with `--ecps-dataset` (CLI) or `ecps_dataset` (comparison config
parameters); an override to a different `populace://…@revision` reference
carries its own pin, and unpinned references resolve at HF-latest.

Known populace-us gaps that shape which rule branches a comparison
exercises: the artifact stores no immigration/SSN columns (everyone
defaults to citizen) and housing tenure is degenerate, so
immigrant-status-sensitive eligibility paths and owner-shelter deductions
see no coverage until those imputation stages land
(PolicyEngine/populace#225).

For the CLI, `axiom-oracles compare euromod axiom ...` reads
`EUROMOD_MODEL_ROOT`, `EUROMOD_COUNTRY`, `EUROMOD_SYSTEM`,
`EUROMOD_DATASET`, and `EUROMOD_PYTHON` from the environment.

## entitledto UK Council Tax Reduction oracle (recorded fixtures)

Council Tax Reduction is set scheme-by-scheme by ~300 English billing
authorities (plus the three national GB schemes). PolicyEngine-UK and UKMOD are
national on the working-age side — PolicyEngine adds only five named English
councils — so neither is a per-council oracle. entitledto
(https://www.entitledto.co.uk/) models every council, making it the most
complete per-council CTR reference (its figures are estimates, not authoritative
awards).

entitledto is a commercial product whose legal notices prohibit systematic *and*
automated data collection and restrict the free calculator to personal use, so
this is a **recorded** oracle, not a live one
(`axiom_oracles/adapters/entitledto/`). Capturing this research grid requires
entitledto's express written consent (a research/API licence); under that
permission a person captures each case once and records the result — with
provenance (capture date, council, scheme year, entitledto-derived council-tax
liability, URL) — into a fixture JSON, and the runner replays it. Fixtures ship
as `pending_capture` stubs (inputs filled, `outputs: null`) and grading is
**fail-closed**: a fixture is graded only if it is `captured` and passes
`validate_capture`, so an uncaptured or malformed fixture is surfaced as an
error, never a spurious £0 or invented value. Terms and the exact capture steps
are in `axiom_oracles/adapters/entitledto/fixtures/uk_ctr/CAPTURE-PROTOCOL.md`.

The `uk-ctr` suite is an eight-case grid across the England pension-age,
Scotland and Wales national schemes, the PolicyEngine-supported Kingston upon
Thames local scheme, and two unsupported councils (Manchester, Birmingham). The
on-demand report combines, per case, the recorded entitledto value, the
committed PolicyEngine-UK 2.89.2 reference, and a statutory hand-check
(reconciled to entitledto's council-tax liability once captured):

```bash
python scripts/run_uk_ctr_entitledto_report.py
```

Wiring this into the weekly comparison matrix is a follow-up for once fixtures
are captured under licence (a pending oracle grades nothing, so it is kept out of
the auto-run matrix until then).

## GETTSIM oracle (Germany)

`GettsimRunner` is the **second, independent** German comparison oracle in the
dual-oracle lane (`rulespec-de#1`), running alongside `EuromodPlatformRunner`.
GETTSIM (the German Taxes and Transfers SIMulator, IZA and an academic
consortium) is pure Python with an explicit policy DAG, date-parameterized,
deterministic, and free of take-up randomness — so it is fast and reproducible,
the complement to the EUROMOD engine path. No licensed microdata is needed;
per-case validation uses hypothetical households.

```python
from axiom_oracles.adapters.gettsim import GettsimCase, GettsimRunner

runner = GettsimRunner(policy_date_str="2025-06-30")  # rules in force 30 Jun 2025

result = runner.compute(
    GettsimCase.single_person({"einnahmen__bruttolohn_m": 4000.0}),
    {"sozialversicherung": {"kranken": {"beitrag": {"betrag_versicherter_m": "health_ee_m"}}}},
)
# {"health_ee_m": [342.0]}  -- one value per person, in p_id order
```

The runner discovers GETTSIM's full input template for the policy date, defaults
every column (dtype-first, with the age/year table-lookup guards), resolves the
four birth-date demographics jointly (contradictions raise), overlays the case,
and computes the requested `tt_targets` (a nested tree whose string leaves name
the output columns). Conventions the adapter owns: input paths are validated
against the template and unknown paths raise `GettsimInputError` (GETTSIM
ignores unknown inputs silently); unknown targets and duplicate output aliases
raise `GettsimTargetError`; `run_case()` returns a `GettsimRunResult` carrying
the exact `gettsim` version alongside the values (`compute()` returns the bare
values dict), and the runner refuses to run an engine version outside its
validated set; `p_id` links use −1, and only `hh_id` is an input grouping id
(GETTSIM derives the finer `wthh/bg/eg/fg/sn` ids for simple households, and
the case can supply them for complex ones — the tests show the explicit ids
changing the Bürgergeld means test). The verified seed — a €4,000/month
worker — reproduces health 342.00 / pension 372.00 / unemployment 52.00 /
long-term care 96.00 / income tax 6,433, and a one-child household pays
255.00/month Kindergeld at the 2025 dates and 259.00 at 2026-01-01 (the two
SteFeG stages, executed as tests). GETTSIM is an optional heavy dependency,
imported lazily; the `gettsim-live` CI job runs the live tests with the locked
fork installed. See `docs/gettsim-oracle-playbook.md` for the full API-gotcha
notes and the DE comparison-suite wiring (a follow-up, once `rulespec-de` has
encodings).

## SNAP QC administrative data oracle

The SNAP QC oracle validates Axiom SNAP encodings against real administrative
microdata rather than another engine. It replays the USDA SNAP Quality Control
public-use file — a nationally representative sample of completed active-case
reviews, 44,891 units in FY2024 — through the Axiom RuleSpec SNAP composition and
compares the file's own constructed benefit (`FSBEN`) and stage intermediates
(gross income, each deduction, net income, income screens, maximum allotment)
against Axiom's. `FSBEN` is FNS/Mathematica's QC Minimodel recomputation from
edited, internally consistent inputs, so agreement is admin-grade
benefit-computation parity — the US analogue of the BEAMM full-admin-returns
income-tax check. The oracle scores the benefit calculation, not the eligibility
screening: the public file already dropped every incomplete or ineligible review,
so the replay feeds eligibility gates the composition's passing defaults.

The first jurisdiction is Colorado FY2024, currently 856/856 (100%)
benefit-exact with every stage intermediate exact — a state reached by fixing
two encoding defects the suite's first run surfaced (the playbook's
track-record section has the path):

```bash
uv run scripts/run_comparison.py co-snap-qc --summary
```

The comparison bridge (`axiom_oracles.bridges.snap_qc_compare`) downloads and
sha256-verifies the pinned public-use file, materializes a patched FY2024 rule overlay,
and evaluates at a nominal period; the run skips gracefully and re-emits the
committed dashboard report on any machine that lacks the engine binary, the dated
rulespec checkout, or the QC file. The standing recipe — the FY-gap overlay
mechanism, the exclusion table, and how to add a fiscal year or a second state —
is in [docs/snap-qc-oracle-playbook.md](docs/snap-qc-oracle-playbook.md).

## Thin Case Schema

The shared schema is intentionally not a universal household ontology. Cases are
just periods, entities, facts, and requested outputs keyed by legal or Axiom
concept IDs:

```python
from axiom_oracles import Case, Concepts, Entity

case = Case(
    case_id="snap-case-1",
    period="2026-01",
    entities=(
        Entity(
            entity_id="head",
            kind="person",
            facts={
                Concepts.PERSON_AGE: 30,
                Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                Concepts.YEARLY_EARNED_INCOME: 30_000,
            },
        ),
    ),
    outputs=(Concepts.SNAP_BENEFIT,),
)
```

Engine adapters project those facts into their own input languages. For example,
the same concept can point at an Axiom legal output, a PolicyEngine variable, or
an ACCESS NYC program code:

```yaml
us:statutes/7/2014/o#snap_eligible:
  comparison: eligibility
  targets:
    axiom: us:statutes/7/2014/o#snap_eligible
    policyengine: is_snap_eligible
    accessnyc:
      code: S2R007
      locales: [US-NY-NYC]
```

Convenience objects like `Household` remain useful for specific adapters, but
they are projection targets rather than the canonical interface.

## Why This Belongs In Axiom

TAXSIM and PRD comparisons are useful validation artifacts, but Axiom's broader
product claim is source-linked, executable law with external oracle checks. This
repo gives those checks a single thin interface instead of letting every oracle
become its own custom comparator or UI.
