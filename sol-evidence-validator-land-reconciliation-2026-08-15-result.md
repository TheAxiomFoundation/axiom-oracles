# PR #468 cross-lane reconciliation result

## Outcome

The `origin/main` reconciliation is complete and tested on
`evidence-validator-land`. Merge commit `0e4d9a840578264bc6e862c4169cd52666d5d312`
has parents `511cacaa9f1cbca9e6d87e9dc47b2e1845f620dd` and
`a33cadea08b69368fab33ac219d8de0ac47e8eaf`.

The strict evidence protocol was not softened. As an intentional consequence,
Denmark and all seven New Zealand program views regress from main's
`conformant=true` to `conformant=false`. Colorado remains conformant.

The task handoff said a merge was already in progress, but the starting
checkout was clean at `27e3a51fc` with no `MERGE_HEAD`; current `origin/main`
was not an ancestor. The current main tip was merged without aborting,
discarding, or rewriting the prior reconciliation history.

## Per-file reconciliation

| File | Resolution |
|---|---|
| `scripts/certify.py` | Read main's 1,055-line version end to end, then retained its CO/DK/seven-NZ registry, NZ report rederivation, per-program views, receipt helpers, blockers, and oracle switching. Retained the strict lane's schema-valid dispositions, bound/full reference gate, typed fail-closed report handling, disposition-marker agreement, exact report/index byte hashes, per-case validation, and census-to-registry identity. Derived premise modes override registry-supplied modes. |
| `tests/test_certification_mutants.py` | Exact function-name union: branch 55, main 41, shared 23, merged 73. `branch -> merged` missing = 0, `main -> merged` missing = 0, and `merged -> parent union` extra = 0. |
| `certificates/dk-boerne-og-ungeydelse.json` | Never hand-resolved. Regenerated from the reconciled validator; it honestly changes to `conformant=false`. |
| `certificates/us-co-snap.json` and seven `certificates/nz-*.json` files | Never hand-resolved. All were regenerated together. CO stays conformant; every NZ view becomes nonconformant. |
| `dashboard/public/data/axiom-snapqc-co-snap.json` | Preserved main's fresh 856-case execution, then used the guarded inline-mirror migration and immutable source replay. The resulting slim report and index validate `bound/cardinality`; no case or verdict was invented. |
| `conformance/exercise-census.json`, `dashboard/public/data/freshness.json`, `dashboard/public/data/overview.json` | Conflict bytes were discarded in favor of canonical generator output after report/index reconciliation. Scoreboard, ratchets, history/burn-down, NZ receipts, and disposition derivatives were regenerated in dependency order as well. |

## Certificate outcomes

| Program | Conformant | Certified state | Evidence result |
|---|---:|---|---|
| `us-co/snap` | `true` | `unavailable` | Reference leg `co-snap-ecps` is `bound/full`; reality leg `co-snap-qc` is `bound/cardinality`. No new evidence defect. |
| `dk/boerne-og-ungeydelse` | `false` | `unavailable` | All three reference legs are `unbound/full`. |
| `nz/acc-earners-levy` | `false` | `no` | Shared NZ reference leg is `unbound/none`. |
| `nz/accommodation-supplement` | `false` | `no` | Shared NZ reference leg is `unbound/none`. |
| `nz/income-tax` | `false` | `no` | Shared NZ reference leg is `unbound/none`. |
| `nz/independent-earner-tax-credit` | `false` | `no` | Shared NZ reference leg is `unbound/none`. |
| `nz/main-benefits` | `false` | `no` | Shared NZ reference leg is `unbound/none`. |
| `nz/winter-energy-payment` | `false` | `no` | Shared NZ reference leg is `unbound/none`. |
| `nz/working-for-families` | `false` | `no` | Shared NZ reference leg is `unbound/none`. |

### New strict-evidence defects

Each DK leg has the same three defect classes:

- no versioned case-chunk index, leaving the report/chunk binding unbound;
- the inline case mismatch has no disposition marker while the report mismatch
  is marked `upstream_engine_gap`;
- `summary.errors_by_engine` is an array rather than an object.

Each NZ program view inherits the same three shared-report defects:

- no non-negative top-level `case_count`;
- the stored cases support neither full verdict nor chunk-cardinality
  reconciliation;
- no `cases/nz-treasury-incomeexplorer/index.json`, leaving the binding
  unbound.

These are protocol-rule regressions and the generated certificates retain
them. No DK/NZ leg was marked clean by hand.

## Derived checks

All checks are green:

- NZ unified record and closure receipts;
- 95 disposition files (two informational expired-entry notes);
- immutable replay and versioned indexes for both certified Colorado suites:
  1,072 `bound/full` ECPS cases and 856 `bound/cardinality` QC cases;
- freshness: 223 suites, 34 executable surfaces;
- scoreboard: 6 jurisdictions, 4 conformant;
- conformance ratchet: 6 jurisdictions, no invariant regression;
- unexplained ratchet: 135 suites, 644 unexplained within ceilings;
- burn-down: 6 series, 143 points;
- overview: 224 reports;
- exercise census and all certificates;
- Ruff, Python compilation, and staged diff whitespace.

## Test batteries

- Certification mutants: **83 passed** in 6.91 seconds. The cross-lane union
  expands the prior 65 cases with 18 NZ/switch mutants.
- Complete evidence battery: **84 passed** in 7.11 seconds. This is the
  historical 66-case command expanded by the same 18 retained main mutants.
- Runner/refresh battery: **65 passed** in 565.35 seconds.
- Census/immutable-replay support: **10 passed** in 0.57 seconds.

## Publication

The ordinary `git push origin evidence-validator-land` attempt failed before
authentication because the sandbox could not resolve `github.com`. A
connected GitHub Git-data publication path is available and is the next step.
PR #468 has not been merged or otherwise changed.
