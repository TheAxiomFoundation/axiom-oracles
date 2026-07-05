# axiom_oracles.bridges — shared oracle-bridge layer

The PolicyEngine/Populace oracle bridge, extracted from the encoder
(`axiom_encode.oracles.policyengine`) so that axiom-oracles owns one copy and
other repos consume it as a package instead of duplicating it. This closes the
June 9 architecture-review P1 item ("~17k LOC oracle bridge embedded in the
encoder") and gives the duplicated `Case`/`Concepts` types (microsim
DECISIONS.md D5) an installable home.

## Provenance

Copied verbatim from `TheAxiomFoundation/axiom-encode` @
`a314fc624967b4e990beb7d9ffc429dae6e26642` (2026-07-05). The only edits are
mechanical import rewrites (absolute `axiom_encode.*` imports became relative
imports inside this package). `rulespec_paths.py` collects the
`validator_pipeline` helpers `ecps_tax` needs, verbatim, so the bridge does
not depend on the encoder harness. The ported test files under
`tests/bridges/` are the same focused suites the encoder runs against these
modules — passing them is the copy-fidelity contract.

## Module map

| Module | Origin (in axiom-encode) | What it does |
|---|---|---|
| `population.py` | `oracles/policyengine/population.py` | Pinned Populace artifact loading (`PopulacePin`, `POPULACE_PINS`, `load_populace_dataset`) — sha256-verified HF downloads, env overrides, unpinned escape hatch |
| `ecps_tax.py` | `oracles/policyengine/ecps_tax.py` | Federal income tax population comparison (Axiom RuleSpec vs PolicyEngine over pinned Populace) |
| `ecps_snap.py` | `oracles/policyengine/ecps_snap.py` | SNAP population comparison harness |
| `us_populace.py` | `oracles/policyengine/us_populace.py` | Generic US variable population comparison |
| `medicaid_populace.py` | `oracles/policyengine/medicaid_populace.py` | Medicaid/MAGI population comparison |
| `efrs_uk.py` | `oracles/policyengine/efrs_uk.py` | UK tax/benefit population comparison (EFRS) |
| `adapters.py` | `oracles/policyengine/adapters.py` | Declarative PE-US variable adapters (`PolicyEngineUSVarAdapter`, `PE_US_VAR_ADAPTERS`) |
| `registry.py` | `oracles/policyengine/registry.py` | Legal-ID keyed PE mapping registry (`load_policyengine_registry`), backed by `mappings/*.yaml` |
| `coverage.py` | `oracles/policyengine/coverage.py` | Per-rule oracle coverage reports for rulespec repos, backed by `program_surfaces/*.yaml` |
| `snapscreener.py` | `oracles/snapscreener.py` | SnapScreener diagnostic cross-check |
| `jurisdiction.py` | `concepts/jurisdiction.py` | Jurisdiction prefix resolution for rulespec checkouts |
| `repo_routing.py` | `repo_routing.py` | Rulespec monorepo/legacy checkout routing |
| `rulespec_paths.py` | `harness/validator_pipeline.py` (extracted subset) | Canonical rulespec compile paths and public item-id aliases |
| `mappings/*.yaml`, `program_surfaces/*.yaml` | same paths | Registry and coverage data files (packaged) |

## Public API

Stable, importable without PolicyEngine installed (all heavy dependencies are
lazy):

- `axiom_oracles.bridges` — `Case`, `Entity`, `Concepts`, `GeographyScope`
  (the shared engine-neutral case types, re-exported from
  `axiom_oracles.core`), `PopulacePin`, `POPULACE_PINS`,
  `load_populace_dataset`, `resolve_populace_pin`, `PolicyEngineMapping`,
  `PolicyEngineOracleRegistry`, `PolicyEngineOracleCoverage`,
  `load_policyengine_registry`.
- The comparison modules (`ecps_tax`, `ecps_snap`, `us_populace`,
  `medicaid_populace`, `efrs_uk`, `coverage`, `adapters`, `registry`,
  `population`, `snapscreener`) are imported explicitly, e.g.
  `from axiom_oracles.bridges import ecps_tax`. Their module-level surfaces
  mirror the encoder originals name-for-name; the encoder re-exports them as
  shims, so a symbol rename here is a breaking change for both repos.

`POPULACE_PINS` in `population.py` is the single certified pin table for
`populace://` artifacts. `axiom_oracles.populations.enhanced_cps` derives its
`(repo_id, filename)`-keyed pin table from it, so a re-pin lands in exactly
one place.

Underscored helpers inside modules (including all of `rulespec_paths.py`) are
implementation detail shared with the encoder copy, not API.

## Consumers

- **axiom-encode** re-exports these modules under
  `axiom_encode.oracles.policyengine.*` (thin shims), keeping its CLI and
  import paths unchanged.
- **axiom-oracles** itself: `populations/enhanced_cps.py` (pin table) and,
  as follow-ups, the `axiom-encode-*` comparison runners in
  `scripts/run_comparison.py`, which today still shell out to the encoder CLI
  in a separate pinned environment.

## Follow-ups (deliberately out of scope here)

- Point the `scripts/run_comparison.py` populace/EFRS lanes at this package
  in-process instead of shelling out to `axiom-encode`.
- Migrate encoder-internal callers (`cli.py`, `validator_pipeline.py`) to
  import `axiom_oracles.bridges` directly, then delete the encoder shims.
- De-duplicate `rulespec_paths.py` against `validator_pipeline` by making the
  encoder import these helpers from here.
- The `uv run --with … axiom-encode …` remediation strings in
  `population.py` install messages still name the encoder CLI; parameterize
  if a non-encoder consumer needs friendlier hints.
