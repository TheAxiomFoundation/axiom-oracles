# Axiom Oracles

Unified validation and oracle-comparison tooling for policy engines.

This repo is the home for executable program comparisons across:

- PolicyEngine
- TAXSIM
- Atlanta Fed PRD
- ACCESS NYC
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

Requires Python 3.14.

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
is returned alongside the outputs. The live UKMOD tests reproduce
hand-computed 2025-26 income tax and employee NICs; the live EUROMOD
Belgium tests recover the statutory 13.07% employee social contribution
exactly and progressive PIT.

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
(`axiom_oracles/populations/enhanced_cps.py::POPULACE_PINS`) — it does NOT
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
