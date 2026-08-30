# Canonical case grids

Each `grids/<jurisdiction>.yaml` declares the case sets every oracle in that
jurisdiction runs. The goal is that **comparing a jurisdiction is the same set
of cases regardless of which engines are being triangulated** — the UK
Axiom / PolicyEngine / UKMOD three-oracle shape generalised to every
jurisdiction, not treated as the exception. A new oracle for a jurisdiction
adopts that jurisdiction's grid; it does not invent its own household list.

A grid stores the oracle-neutral *skeleton* of each case and nothing else:

- `id`, `period`, `scenario`;
- the requested output concept id(s);
- the Axiom query `entity` / `entity_id`;
- the household as neutral `entities` (age + relation + any neutral facts);
- case-level neutral `facts`;
- the `parameters` block — the demographic and economic values that vary across
  the set (income, child age, region, single-parent flag, ...), keyed to the
  oracle-neutral scenario names the suites already use.

It deliberately does **not** store the per-engine projections: the RuleSpec
`#input.` payloads, the EUROMOD variable rows, or the input bridge. Those are
*derived* from the skeleton by each suite's factory functions in
`axiom_oracles/suites/`. A grid is the case list; the suite is the wiring.

## Files

| File | What |
| --- | --- |
| `us.yaml`, `be.yaml`, `ca.yaml`, `uk.yaml` | Adopted canonical grids. Generated from the live suites; do not hand-edit. |
| `<cc>.suggested.yaml` | Boundary-case proposals from the generator. **Not** adopted, **not** loaded. |

`us.yaml`, `be.yaml`, and `ca.yaml` are extracted from the suites that ship on `main`.
`uk.yaml` ships ahead of the UK worker suites (they land with the UKMOD work);
its equivalence check activates automatically once those suites are importable.

## How a new oracle adopts a jurisdiction's grid

1. Load the grid: `axiom_oracles.grids.load_grid("be")`.
2. Take the case set you are validating: `grid.case_set("be-employer-ssc")`.
3. Project each `CaseSpec` into your engine's inputs — the same skeleton fields
   the other engines project. If your engine needs an input the skeleton does
   not carry, that input is a *derived projection*: compute it in your adapter,
   the way the Axiom and EUROMOD adapters compute theirs. Do not add it to the
   grid unless it is a genuinely oracle-neutral scenario parameter.
4. Compare against the other engines on the identical `id`/`period` cases.

Because every engine reads the same grid, a third engine joining a two-engine
comparison is a drop-in: it runs the cases that are already there.

## How triangulation works

"Triangulation" means running **3+ engines over one case set** and reading
their agreement per case. The grid guarantees the *inputs* are identical across
engines; each engine produces its own value for the requested output concept;
the comparison report joins those values by `case_id`.

- UK worker income tax runs Axiom, PolicyEngine UK, and UKMOD on
  `uk-worker-pit` — three independent computations of the same liability on the
  same 30k/45k/60k/130k/360k grid.
- Belgium documentary worker/family surfaces run Axiom and EUROMOD (BE) today; a third
  engine adopting `be.yaml` triangulates them without touching the grid.

Majority / discrepancy semantics — how many engines must agree, how a split is
surfaced — are **left to the reports** (`axiom_oracles.comparison.report` and
the dashboard), not the grid. The grid's only job is that the case list is the
same for everyone.

## Regenerating the adopted grids

The grids are a faithful projection of the suites, proven byte-preserving by
the extraction-equivalence test (`tests/test_case_grids.py`): it reconstructs
each suite from the emitted grid and asserts field-by-field equality, so a
regenerated grid can never silently drift from the suites — and therefore can
never shift a comparison report.

```bash
uv run python scripts/extract_grids.py            # rewrite grids/<cc>.yaml
uv run python scripts/extract_grids.py --check     # CI: fail if stale
```

Run this whenever a suite's case list changes. Because the suites remain the
place cases are authored, editing a suite and regenerating is the workflow;
hand-editing a generated grid is not.

## Referencing a case set from a comparison config

A comparison config can name a canonical case set instead of inlining cases,
via a `grid_case_set` reference resolved by
`axiom_oracles.grids.resolve_grid_case_set`:

```yaml
runner:
  parameters:
    grid_case_set: uk:uk-worker-pit   # or a bare 'uk-worker-pit' (globally unique)
```

Inline, suite-specific extras remain possible: a config may still add one-off
cases alongside a referenced set for a probe that does not belong in the shared
grid. See `comparisons/README.md`.

## Boundary-case generator

`scripts/generate_boundary_cases.py` proposes threshold-straddling cases from
the **axiom-corpus** typed concept registry
(`src/axiom_corpus/concepts/data/<cc>.yaml`). It finds concepts whose name
encodes a statutory threshold — a bracket boundary, phase-out start, cap,
floor, or income limit — that carry a PolicyEngine `parameter_value` mapping,
and emits a below/above pair per threshold into `grids/<cc>.suggested.yaml`.

```bash
uv run python scripts/generate_boundary_cases.py               # us, uk
uv run python scripts/generate_boundary_cases.py --check        # CI: idempotent?
# corpus not at ../axiom-corpus or ~/TheAxiomFoundation/axiom-corpus:
uv run python scripts/generate_boundary_cases.py \
    --registry-root /path/to/axiom-corpus/src/axiom_corpus/concepts/data
```

Each suggested case carries a `probe` block naming the concept id, the
PolicyEngine parameter, the program, the dtype/unit, and which `side` of the
threshold it sits on. The straddle **value is intentionally `null`**: the
corpus records *which* parameter bounds the case, not the parameter's runtime
value, so a human or agent fills the concrete number from that parameter before
use.

Suggestions are **never auto-included**. `load_grids()` skips
`*.suggested.yaml` by design. Adoption is a deliberate act: review a probe,
resolve its value and `period`, then move the case into the hand-maintained
`grids/<cc>.yaml`.
