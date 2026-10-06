# axiom-oracles #556: relation tuple producer fix

Worktree: `/Users/maxghenis/.subfleet/worktrees/20260927-153142-producer-axiom-oracles`

Patch: `/Users/maxghenis/.subfleet/worktrees/20260927-153142-producer-axiom-oracles/axiom-oracles-556.patch`

Implemented and left uncommitted. Nothing was pushed, published, or opened as a PR.
**Full-suite validation is incomplete**; the final focused tests, Ruff, CI script checks, and clean package build passed as detailed below.

## Base and scope

Freshly fetched main: `fc3ce90de39d702b5ec3981a4e170d03a488b6eb`.
The assigned detached HEAD remains `ef7e11f5f4e2ff841f2797685ba2807c6090563f` because shared Git metadata is read-only. A normal fetch was denied; fetching into `.lane-validation/base.git` succeeded. Committed main changes were applied to this workspace before implementation. A separate main-based index supplies accurate diffs and Git-index-sensitive checks. The caller checkout was never written.

The patch contains 15 source/test files. Final diff and whitespace checks passed. No committed comparison, dashboard, conformance, certificate, closure, disposition, or manifest outputs differ from fetched main. No stray test evidence files remain under dashboard data, docs, or conformance. Dependency manifests and lockfiles are unchanged.

## Changes

| File | Change |
| --- | --- |
| [axiom_oracles/bridges/relation_binding.py:23](/Users/maxghenis/.subfleet/worktrees/20260927-153142-producer-axiom-oracles/axiom_oracles/bridges/relation_binding.py:23) | Executable slot inference, declaration fallback, derived scopes and aliases |
| [axiom_oracles/bridges/relation_binding.py:285](/Users/maxghenis/.subfleet/worktrees/20260927-153142-producer-axiom-oracles/axiom_oracles/bridges/relation_binding.py:285) | Request binding; untyped missing-label compatibility |
| [axiom_oracles/bridges/tax_populace.py:1100](/Users/maxghenis/.subfleet/worktrees/20260927-153142-producer-axiom-oracles/axiom_oracles/bridges/tax_populace.py:1100) | Artifact-aware CTC/CDCC/AOTC/EITC builders |
| [axiom_oracles/bridges/tax_populace.py:2927](/Users/maxghenis/.subfleet/worktrees/20260927-153142-producer-axiom-oracles/axiom_oracles/bridges/tax_populace.py:2927) | Bind against the actual compiled artifact after name resolution |
| [axiom_oracles/bridges/tax_populace.py:3214](/Users/maxghenis/.subfleet/worktrees/20260927-153142-producer-axiom-oracles/axiom_oracles/bridges/tax_populace.py:3214) | Require a real input entity kind |
| [axiom_oracles/bridges/state_tax_populace_runner.py:2893](/Users/maxghenis/.subfleet/worktrees/20260927-153142-producer-axiom-oracles/axiom_oracles/bridges/state_tax_populace_runner.py:2893) | TaxUnit/Person labels; shared runtime binding |
| [axiom_oracles/bridges/efrs_uk.py:4474](/Users/maxghenis/.subfleet/worktrees/20260927-153142-producer-axiom-oracles/axiom_oracles/bridges/efrs_uk.py:4474) | UK Person/Family/Payment labels |
| [axiom_oracles/bridges/us_populace.py:416](/Users/maxghenis/.subfleet/worktrees/20260927-153142-producer-axiom-oracles/axiom_oracles/bridges/us_populace.py:416) | US Person input labels |
| [axiom_oracles/bridges/snap_populace.py:1771](/Users/maxghenis/.subfleet/worktrees/20260927-153142-producer-axiom-oracles/axiom_oracles/bridges/snap_populace.py:1771) | Bind SNAP requests against their artifact |
| [axiom_oracles/adapters/axiom/runner.py:467](/Users/maxghenis/.subfleet/worktrees/20260927-153142-producer-axiom-oracles/axiom_oracles/adapters/axiom/runner.py:467) | Bind both single and batch generic adapter execution |
| [tests/bridges/test_tax_relation_requests.py:130](/Users/maxghenis/.subfleet/worktrees/20260927-153142-producer-axiom-oracles/tests/bridges/test_tax_relation_requests.py:130) | Generated federal tax-unit invariants |
| [tests/bridges/test_tax_relation_engine.py:203](/Users/maxghenis/.subfleet/worktrees/20260927-153142-producer-axiom-oracles/tests/bridges/test_tax_relation_engine.py:203) | Real strict-engine and previous-engine regressions |

The audit also covered generic/tax/SNAP projections through the shared adapter. Medicaid already supplies Person labels and emits no relation tuples.

## Invariants

1. For used two-slot relations, executable `current_slot`/`related_slot` usage determines positions. Declared `slot_entities` supplies positional order only for unused relations. Conflicting metadata or incompatible labelled kinds fail clearly.
2. Each emitted typed tuple puts ids in slots matching their real input entity kinds. Producers use TaxUnit, Person, Household, Family, Payment, etc. where known; `Entity` is not treated as a wildcard.
3. Historical untyped related-first artifacts preserve legacy tuple order. Unlabelled members in old requests remain supported; absent evidence preserves the supplied tuple. Labels themselves are corrected as expressly requested.
4. No producer adds `relation_binding: lenient`.

Hypothesis exercises empty/multiple tax units and households, varied member counts, typed/untyped declarations, both executable directions, and declaration/usage disagreements. Tests also cover membership, nested predicates, versions, derived relation sources, same-kind ids, aliases, missing labels, and non-two-slot preservation.

## Real-engine before/after

Tests compile unchanged existing `rulespec-us` modules `us/statutes/26/21.yaml`, `24.yaml`, and `24/h.yaml`. The CDCC reference is the encoded companion `single_one_child_low_agi_credit`; no evaluator mock or substitute law is used.

Sample: one single-filing tax unit, AGI $15,000; adult age 38 and child age 8 with valid SSNs. CDCC earned-income cap $10,000, childcare expense $5,000, credit limit $5,000.

| Output | Previous request on main 5a29e03 | Corrected request on main and strict |
| --- | ---: | ---: |
| CDCC | $0 (exit 0) | $1,500 (+$1,500) |
| CTC child count | 0 | 1 (+1) |
| CTC maximum / before advance payments | $0 | $2,200 (+$2,200) |
| CTC phaseout amount | $0 | $0 |
| CTC phaseout threshold | $200,000 | $200,000 |

Strict responses report `metadata.relation_binding = strict`, with no lenient request option. The strict engine rejects reversed tuples and generic Entity labels.

Relevant committed comparison: `dashboard/public/data/axiom-policyengine-fiit-ecps.json` records engine `aa1ff025906c7216c053e9b9c4097cc0dfef1811`, version 0.1.0, generated July 8, 2026. It contains 437,595 CTC values (5 existing mismatches) and 525,114 CDCC values (0 mismatches). Historical tuple order is preserved. Its population results were not replayed; no measured report-wide delta is claimed. The table measures the defect on modern artifacts. No committed comparison outputs were regenerated.

## Commands and results

Commands run from the worktree unless specified. Main dev environment: Python 3.14.7 freethreaded; GETTSIM environment: Python 3.13.9. `UV_CACHE_DIR=.lane-validation/uv-cache` was used for uv commands.

Final focused verification:

- `.venv/bin/pytest -q tests/bridges/test_relation_binding.py tests/test_axiom_adapter.py`: **73 passed in 90.44s**.
- The command below: **17 passed in 135.87s**, including 12 federal example/property cases and all 5 live engine cases.
- `uv run --no-sync ruff check .`: **passed**.

```sh
AXIOM_STRICT_RELATION_ENGINE_BIN=/Users/maxghenis/TheAxiomFoundation/_worktrees/engine-findings/bin-relation-binding \
AXIOM_LEGACY_RELATION_ENGINE_BIN=/Users/maxghenis/TheAxiomFoundation/_worktrees/engine-findings/bin-main-5a29e03 \
AXIOM_RULESPEC_ROOT=/Users/maxghenis/TheAxiomFoundation/rulespec-us \
UV_CACHE_DIR=.lane-validation/uv-cache \
uv run --no-sync pytest -q tests/bridges/test_tax_relation_requests.py tests/bridges/test_tax_relation_engine.py --basetemp=.lane-validation/final-live-recheck
```

Other completed tests:

- `uv sync --extra dev`: passed.
- `uv run pytest -q tests/bridges/test_policyengine_tax_populace.py`: **102 passed**.
- `.venv/bin/pytest tests/test_axiom_adapter.py tests/bridges/test_state_tax_populace_runner.py -q`: **225 passed**.
- `.venv/bin/pytest tests/bridges/test_state_tax_populace_runner.py tests/bridges/test_policyengine_efrs_uk.py tests/bridges/test_policyengine_snap_populace.py tests/bridges/test_policyengine_us_populace.py -q`: **380 passed, 1 failed in 542.93s** (misplaced new UK assertion). After correction, `.venv/bin/pytest tests/bridges/test_policyengine_efrs_uk.py::test_national_insurance_class_1_request_projects_weekly_inputs tests/bridges/test_policyengine_efrs_uk.py::test_income_tax_income_base_request_projects_section_23_relation -q`: **2 passed in 26.00s**. The later full-suite rerun also passed that UK test.
- `GIT_OPTIONAL_LOCKS=0 GIT_INDEX_FILE="$PWD/.lane-validation/main.index" UV_CACHE_DIR=.lane-validation/uv-cache uv run --no-sync pytest -q tests/test_bridge_manifest_validation.py::test_committed_dk_manifests_are_record_and_period_clean tests/test_bridge_manifest_validation.py::test_couple_non_earner_777_suite_mutant_is_a_finding`: **2 passed in 102.57s**.
- `UV_CACHE_DIR=.lane-validation/uv-cache UV_PROJECT_ENVIRONMENT=.venv-gettsim UV_PYTHON_INSTALL_DIR=.lane-validation/python uv sync --python 3.13 --extra gettsim --extra dev`: passed.
- Same environment with `uv run --python 3.13 --extra gettsim --extra dev pytest -q tests/test_gettsim_adapter.py`: **82 passed, 15 warnings in 1603.30s**.

Full-suite attempts:

- Exact CI command `uv run pytest -q`: interrupted. Recorded progress before interruption: **1,605 passed, 41 skipped, 7 failed**; these are progress markers, not a completed pytest summary. This early run collected pre-fix code: the seven failures were the corrected UK assertion, four corrected Hypothesis timing deadlines, and two stale-index manifest checks.
- Diagnostic `uv run --no-sync pytest -q --timeout=180 -o faulthandler_timeout=60`: interrupted (exit 130) at about 46%. Recorded **1,639 passing, 43 skipped, 3 failed progress markers**, not a completed suite summary. The two manifest checks pass with the main index (above). The third failure is an unrelated 180-second timeout in `tests/test_certification_mutants.py::test_nz_computed_premises_without_cleared_blockers_do_not_certify`; traces show report/census loading. Remaining tests were not completed. pytest-timeout 2.4.0 was installed only in the local environment; project dependencies were not changed.
- Full logs: `.lane-validation/pytest-full.log` and `.lane-validation/pytest-bounded-full.log`.

Package build:

- Initial in-place `uv build` failed while traversing a disappearing scratch-cache file. It was replaced with a clean export of 2,293 tracked/current source files, excluding scratch and caches.
- In `/Users/maxghenis/.subfleet/worktrees/20260927-153142-producer-axiom-oracles/.lane-validation/package-source`, `UV_CACHE_DIR=/Users/maxghenis/.subfleet/worktrees/20260927-153142-producer-axiom-oracles/.lane-validation/uv-cache uv build --out-dir /Users/maxghenis/.subfleet/worktrees/20260927-153142-producer-axiom-oracles/.lane-validation/package-dist`: **passed, exit 0 in 569.42s**. An initial 180-second bound timed out; the 600-second retry succeeded.
- Built sdist (148,071,904 bytes) and wheel (1,099,453 bytes). Both contain the delivered helper bytes; full archive scans found no scratch/cache paths. Evidence: `.lane-validation/package-build-retry-result.json`, `package-artifact-checks.json`, and `build-package-source-retry.log`.

## Other CI script checks

All 34 commands below passed. The census and manifest commands required reruns with `GIT_OPTIONAL_LOCKS=0 GIT_INDEX_FILE="$PWD/.lane-validation/main.index"`: the original detached index does not list files added on newer main. No outputs were regenerated.

| Command | Result |
| --- | --- |
| `uv run scripts/run_comparison.py --list` | Pass |
| `uv run scripts/check_rule_verification.py` | Pass |
| `uv run scripts/check_state_tax_populace_contract.py` | Pass |
| `uv run scripts/apply_dispositions.py --check` | Pass |
| `uv run python scripts/nz_incomeexplorer.py --check` | Pass |
| `uv run python scripts/emit_disposition_artifacts.py --check de-worker-dual-oracle` | Pass |
| `uv run python scripts/emit_case_artifacts.py --check de-worker-dual-oracle` | Pass |
| `uv run python scripts/de_axiom_legs.py --check` | Pass |
| `uv run python scripts/de_unified_comparison.py --check` | Pass |
| `uv run python scripts/de_closure.py --check` | Pass |
| `uv run python scripts/de_executable.py --check` | Pass |
| `uv run python scripts/de_certificate_census.py --check` | Pass |
| `uv run python scripts/generate_chunk_indexes.py --check` | Pass |
| `uv run python scripts/exercise_census.py --check` | Pass (main-index rerun) |
| `uv run python scripts/validate_bridge_manifests.py --strict` | Pass (main-index rerun) |
| `uv run python scripts/nz_executable_reproduction.py --check` | Pass |
| `uv run python scripts/nz_closure.py --check` | Pass |
| `uv run python scripts/nz_exercise_denominator.py --check` | Pass |
| `uv run python scripts/certify.py --check` | Pass |
| `uv run python scripts/us_tariff_capture_integrity.py` | Pass |
| `uv run scripts/emit_case_artifacts.py --check al-snap-ecps ma-snap-ecps nc-snap-ecps sc-snap-ecps tn-snap-ecps` | Pass |
| `uv run scripts/emit_disposition_artifacts.py --check al-snap-ecps ma-snap-ecps nc-snap-ecps sc-snap-ecps tn-snap-ecps` | Pass |
| `uv run scripts/extract_grids.py --check` | Pass |
| `uv run scripts/generate_boundary_cases.py --check` | Pass |
| `uv run scripts/generate_affected_map.py --check` | Pass |
| `uv run scripts/check_vacuous_gate.py --check` | Pass |
| `uv run scripts/generate_dashboard_overview.py --check` | Pass |
| `uv run scripts/generate_conformance_universe.py --all --check` | Pass |
| `uv run scripts/closure_universe.py --check` | Pass |
| `uv run scripts/generate_conformance_compositions.py --all --check` | Pass |
| `uv run scripts/conformance_scoreboard.py --check` | Pass |
| `uv run scripts/conformance_ratchet.py --check` | Pass |
| `uv run scripts/unexplained_ratchet.py --check` | Pass |
| `uv run scripts/conformance_burndown.py --check` | Pass |

Additional limits:

- Conformance model-spine checks intentionally left US/UK comparisons unverified because available PolicyEngine source checkouts differ from pinned versions (US 1.822.5 vs 1.767.3; UK 2.88.52 vs 2.89.2).
- The older detached HEAD makes NZ ancestor-floor checks fail open. An additional closure check using the isolated fresh-main Git history failed when two `git rev-list --full-history` calls exceeded its 15-second timeout. The attempted command was `GIT_DIR="$PWD/.lane-validation/base.git" GIT_WORK_TREE="$PWD" GIT_INDEX_FILE="$PWD/.lane-validation/main.index" GIT_OPTIONAL_LOCKS=0 UV_CACHE_DIR=.lane-validation/uv-cache uv run scripts/closure_universe.py --check`; errors are retained in `.lane-validation/closure-fresh-main.log`.
- CI's separate pinned NZ source-build/live replay was not run. Its hermetic checks passed; the supplied strict relation engine was executed by the five new live tests.

## Patch validation

The patch was generated with `git diff origin/main > axiom-oracles-556.patch`, using the separate main-based index and object directory to avoid shared Git metadata writes. It includes new files via intent-to-add entries in that isolated index. `git diff --check origin/main` passed; `git apply --cached --check` passed against a separate clean main index.
