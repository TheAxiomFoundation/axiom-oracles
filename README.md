# Axiom Programs

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
- placeholder adapter for Axiom

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
axiom-programs accessnyc audit \
  --rules-dir /tmp/access-nyc-rules-review/accessnyc/rules
```

JSON output:

```bash
axiom-programs accessnyc audit \
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
axiom-programs compare accessnyc policyengine
```

By default this uses the Enhanced CPS population, resolves the target
geographic intersection automatically, and samples 50 households. For ACCESS NYC
vs PolicyEngine, that means the NYC Enhanced CPS-derived dataset:

```text
hf://policyengine/policyengine-us-data/cities/NYC.h5
```

Use a different sample size or period with:

```bash
axiom-programs compare accessnyc policyengine \
  --sample-size 250 \
  --period 2026-05
```

To run against NYCOpportunity's local Python replatform instead of the hosted
API:

```bash
axiom-programs compare accessnyc policyengine \
  --sample-size 250 \
  --accessnyc-mode python \
  --accessnyc-python-path /path/to/benefits-screening-api \
  --output reports/accessnyc-policyengine-ecps.json
```

`--population enhanced-cps` is the default validation path. `--suite` is only
used for `--population synthetic`, which is intended for targeted regression
and boundary probes:

```bash
axiom-programs compare accessnyc policyengine \
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

Local Drools execution is not currently available from the public
`ACCESS-NYC-Rules` repo alone. The repo contains the `.drl` files, but not the
compiled Java request/response/fact classes or a runnable Screening API/KJAR.
The public `NYCOpportunity/benefits-screening-api` repo is a separate WIP
Python replatform and can run locally through `--accessnyc-mode python`.
`--accessnyc-mode drools` exists to make the Drools limitation explicit and to
define where a future local runner should attach.

## Thin Case Schema

The shared schema is intentionally not a universal household ontology. Cases are
just periods, entities, facts, and requested outputs keyed by legal or Axiom
concept IDs:

```python
from axiom_programs import Case, Concepts, Entity

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
