# DK strict-clean bridge manifests (WS1)

Status: **SHIP-READY — all three DK census rows are bridge-audited, the
computed exercised verdict is true, and `certified.state` remains
`unavailable` because closed/executable still have no computed producers.**

## Checkout provenance

- Branch: `d3/dk-exercised`; local-only work, never pushed.
- Base: locally cached `origin/main` at
  `7f4e579b3f904ada8f00e63cffba63b539d4151e`.
- The required `git fetch origin main` was attempted first, but the sandbox
  could not resolve `github.com`. The base therefore could not be refreshed
  from the network. The branch was created only after confirming its tracked
  state exactly matched the available `origin/main` (`0 0` left/right).
- The pre-existing untracked `.axiom/run-logs/a2b7ab89.jsonl` was left
  untouched.

## What changed

- Added strict-clean manifests for `dk-child-youth-benefit`,
  `dk-child-youth-benefit-2023`, and `dk-child-youth-benefit-couple` under
  `axiom_oracles/bridges/manifests/`.
- Read the complete DK suite and declared its exact nine-input surface for
  each experiment. No suite behavior was changed. In particular:
  - `child_age_years` is mapped from the case demographic in all three suites;
  - the main suite maps the constructor's 0/60,000 pension-contribution
    dimension, while the 2023 and couple suites hold it constant at zero;
  - CPI, supplement flag, pension cap, part-year flag, and allowance match the
    literal values each suite supplies;
  - both section-7-basis inputs are bridged from annual EUROMOD `tintbto_s`;
    the couple declaration states that only the earner records are overwritten
    and the non-earner records remain zero.
- Declared each population as suite-enumerated synthetic cases with
  `pin_required: false` and `pinned: null`. No dataset identity was invented.
- Added computed `completeness.source: suite_cases`. The validator now loads
  the registered suite cases, reconciles flat inputs, entity input records,
  bridge targets, and exact EUROMOD bridge sources; rejects omitted/extra
  inputs, non-bridged bridge targets, and a constant declaration for values
  that demonstrably vary. A bare self-asserted `completeness: verified`
  remains an error. One-value mapped-versus-constant provenance is not
  machine-inferable and remains covered by the explicit human `audit: read`.
- Added explicit `strict: true` enforcement for audited manifests. This lets
  the requested global `--strict` command enforce zero findings for the three
  DK manifests without misrepresenting the older CO exemplar as clean. CO's
  existing four findings remain visible and unchanged. CI now invokes the
  validator with `--strict`.
- Added mutants for dropped inputs, a 0/60,000 mapped-to-constant flip,
  bridge-kind and `tintbto_s` source drift (including a multi-source target),
  stripped synthetic-population declarations, directory evidence, selective
  strict enforcement, and malformed manifest identity fields. Added a positive
  propagation test for all three census rows and the certificate.

## Evidence reviewed

- Bridge code: the full
  `axiom_oracles/suites/dk_child_youth_benefit.py`, including all constructors,
  `_axiom_inputs`, the couple's 18 entity-addressed records, and both bridge
  target shapes.
- RuleSpec evidence at
  `TheAxiomFoundation/rulespec-dk@9986b6035c4e557b9b40645dfe2f3e4cffb6037c`:
  - `dk/statutes/lbk-603-2025/boerne-og-ungeydelsesloven/paragraf-1-a.yaml`;
  - its `paragraf-1-a.test.yaml` companion, including the partial-year
    recalculated-basis fixture;
  - `dk/statutes/composed/boerne-og-ungeydelse-pipeline.test.yaml`;
  - the couple pipeline module and its companion fixture.
- Each `covered_by` entry names an in-repo committed execution receipt or
  adapter test. The receipts provenance-pin the RuleSpec commit above, and the
  exact external module/fixture paths are recorded alongside them.

## Computed result

| suite | period | census cases | bridge audited |
|---|---:|---:|---|
| `dk-child-youth-benefit` | 2025 | 8 | true |
| `dk-child-youth-benefit-2023` | 2023 | 1 | true |
| `dk-child-youth-benefit-couple` | 2025 | 1 | true |

The regenerated DK certificate reports:

- `verdicts.conformant.value: true` (computed);
- `verdicts.exercised.value: true` (computed);
- all three exercise legs `bridge_audited: true`;
- no exercise blocker (the certificate's blocker list is empty);
- `certified.value: false`, `certified.state: unavailable`, as expected while
  closed and executable lack computed producers.

Regenerating the census also changed the census SHA cited by the existing CO
certificate; no CO verdict changed.

## Verification

- `uv run python scripts/validate_bridge_manifests.py --strict`: exit 0;
  4 manifests, 0 errors; 3 strict manifests, **0 strict findings**. The four
  printed findings are the unchanged CO debt (one external `covered_by`,
  unpinned Populace, three partial bindings, and unverified completeness).
- `uv run python scripts/exercise_census.py --check`: **up to date**.
- `uv run python scripts/certify.py --check`: **up to date**.
- Focused certification/grid/config tests: **133 passed**.
- Required DK/disposition selector
  (`pytest -q tests/ -k 'dk or disposition'`): **103 passed, 2,497 deselected**.
- `ruff check .`: **all checks passed**.
- `ruff format --check` on changed Python: **3 files already formatted**.
- Independent manifest audit: **clean**, with exact input catalogs, evidence
  paths, census state, and certificate state rechecked. A separate adversarial
  validator review found several bypasses; all were fixed, mutant-tested, and the
  second review returned clean.

An additional, non-required full-suite attempt reached 1,543 passed and 33
skipped before it was stopped during slow integration tests. Its five failures
were local sibling `rulespec-us` checkout mismatches in CA, IL, NY, and OH
output/fixture expectations; those tests and artifacts do not overlap this diff
or the required DK selector.
