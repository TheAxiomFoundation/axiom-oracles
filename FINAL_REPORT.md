# Germany dual-oracle suites — final report

## Outcome

The Germany dual-oracle lane is complete on `feat/de-dual-oracle-suites`. It
instantiates the repository's existing synthetic-suite and v2.1 report
architecture for a direct EUROMOD↔GETTSIM comparison; it does not create a new
comparison architecture or claim Axiom conformance.

The committed live report covers 13 households and six concepts (78 total
comparisons):

- 66 matches at the explicit EUR 0.01 tolerance;
- 12 expected amount differences covered by the three supplied filed findings;
- 0 engine errors and 0 unexplained differences;
- 84.615385% raw agreement and 100% explained agreement; and
- no expired or orphaned Germany dispositions.

No commits were pushed and no pull request was opened.

## Delivered

1. Added six engine-neutral DE concepts and explicit EUROMOD/GETTSIM mappings:
   four monthly employee social-insurance legs, annual income tax including
   Soli, and monthly Kindergeld. Each money comparison retains the one-cent
   tolerance.
2. Added the canonical 13-case grid and both engine projections, including
   `yemmy`/hours/months, `drgn1`, the exact `61/56` GETTSIM gross bridge,
   relationships, and household reduction rules.
3. Registered `gettsim-synthetic-compare` and
   `de-worker-dual-oracle`, with live-engine preflight, correct optional-engine
   re-emission, provenance, engine metadata, and `sample_size` support.
4. Generated and committed the report from a real local two-engine run, then
   applied the three schema-validated dispositions and published it through
   the dashboard manifest/freshness data.
5. Added pure, report-invariant, and live-gated tests. The GETTSIM live CI file
   now pins canonical Midijob, two-child, and joint-partner MAX behavior; the
   EUROMOD live file pins the same grid surface under the exact DE model
   configuration.
6. Marked the GETTSIM playbook's DE lane as realized and added a dedicated DE
   playbook for engine inputs, units, aggregation, findings, and reproduction.
   The dashboard now routes the suite to Germany and labels GETTSIM correctly.

## Filed findings represented

| Finding | Attributed model | Rows | Pinned effect |
|---|---|---:|---|
| `ec-jrc/JRC-EUROMOD-software-source-code#21` | EUROMOD | 9 | annual tax differences from EUR -19.51 to about EUR -88.35 |
| `ec-jrc/JRC-EUROMOD-software-source-code#22` | EUROMOD | 2 | annual parent-tax differences of EUR -1,476.17 and EUR -2,824.99 |
| `ttsim-dev/gettsim#1215` | GETTSIM | 1 | Midijob care-insurance difference of EUR -1.06973/month |

The repository disposition schema does not define the requested literal
`model_finding` value. Following the repository pattern, all three use
`upstream_engine_gap`, with the responsible model, mechanism, and issue URL in
the evidence. Likewise, dated `reports/*.json` files are ignored by repository
policy; the committed evidence is the dispositioned dashboard report plus its
manifest/freshness entries. Because this is oracle-versus-oracle, the generated
affected-map entry intentionally has `repos: []`.

## Commits

- `4491425` — start the committed progress ledger
- `98e6e17` — record the DE suite architecture decision
- `7ee098d` — add the Germany concepts, grid, mappings, and projections
- `69fbd82` — register the dual-oracle runner/configuration/dispositions
- `cfaaa52` — route the Germany comparison in the dashboard
- `3c9306b` — publish the real live report
- `7625068` — add live anchors and realized-lane documentation

## Files changed

Relative to the supplied `13d064d` starting point:

- Progress/output: `PROGRESS.md`, `FINAL_REPORT.md`.
- Core and suite: `axiom_oracles/core/case.py`,
  `axiom_oracles/core/geography.py`, `axiom_oracles/suites/__init__.py`,
  `axiom_oracles/suites/de_worker.py`.
- Mappings and grids: `axiom_oracles/config/concept_mappings.yaml`,
  `axiom_oracles/bridges/mappings/de.yaml`, `axiom_oracles/grids/extract.py`,
  `grids/de.yaml`, `scripts/extract_grids.py`, `pyproject.toml`.
- EUROMOD unit handling: `axiom_oracles/adapters/euromod/runner.py`.
- Comparison registry/runner: `comparisons/de-worker-dual-oracle.yaml`,
  `comparisons/README.md`, `comparisons/affected_map.json`,
  `scripts/run_comparison.py`, `scripts/generate_affected_map.py`,
  `scripts/check_vacuous_gate.py`.
- Findings/evidence: `dispositions/de-worker-dual-oracle.yaml`,
  `dashboard/public/data/euromod-gettsim-de-worker-dual-oracle.json`,
  `dashboard/public/data/manifest.json`,
  `dashboard/public/data/freshness.json`.
- Dashboard routing: `dashboard/src/components/DashboardContent.jsx`,
  `dashboard/src/utils/format.js`, `dashboard/src/utils/suites.js`.
- Documentation: `docs/gettsim-oracle-playbook.md`,
  `docs/de-dual-oracle-playbook.md`.
- Tests: `tests/test_de_worker_suite.py`, `tests/test_de_worker_report.py`,
  `tests/test_case_grids.py`, `tests/test_euromod_adapter.py`,
  `tests/test_gettsim_adapter.py`, `tests/test_run_comparison.py`,
  `tests/test_affected_map.py`, `tests/test_provenance.py`,
  `tests/test_vacuous_gate.py`.

No conformance or scoreboard files were changed.

## Commands run

The live report was generated with:

```bash
EUROMOD_MODEL_ROOT_DE=/Users/maxghenis/Downloads/EUROMOD_J2.0/EUROMOD_RELEASES_J2.0+ \
EUROMOD_PYTHON=/Users/maxghenis/TheAxiomFoundation/ops/de-lane/emx86/bin/python \
DOTNET_ROOT=/Users/maxghenis/.dotnet-x64 \
PYTHONNET_RUNTIME=coreclr \
POLARS_SKIP_CPU_CHECK=1 \
/Users/maxghenis/TheAxiomFoundation/axiom-oracles-286/.venv-gettsim/bin/python \
  scripts/run_comparison.py de-worker-dual-oracle --summary
```

Live and full validation commands:

```bash
# EUROMOD DE live anchors
EUROMOD_MODEL_ROOT_DE=/Users/maxghenis/Downloads/EUROMOD_J2.0/EUROMOD_RELEASES_J2.0+ \
EUROMOD_PYTHON=/Users/maxghenis/TheAxiomFoundation/ops/de-lane/emx86/bin/python \
DOTNET_ROOT=/Users/maxghenis/.dotnet-x64 PYTHONNET_RUNTIME=coreclr \
POLARS_SKIP_CPU_CHECK=1 UV_CACHE_DIR=/tmp/axiom-de-uv-cache \
uv run --no-sync pytest -q tests/test_euromod_adapter.py -k Germany

# Locked GETTSIM fork
PYTHONPATH=/Users/maxghenis/TheAxiomFoundation/axiom-oracles-de-suites \
/Users/maxghenis/TheAxiomFoundation/axiom-oracles-286/.venv-gettsim/bin/python \
  -m pytest -q tests/test_gettsim_adapter.py

# Full repository suite and Ruff
UV_CACHE_DIR=/tmp/axiom-de-uv-cache \
uv run --no-sync --extra dev pytest -q
UV_CACHE_DIR=/tmp/axiom-de-uv-cache \
uv run --no-sync --extra dev ruff check .

# Derived evidence and dependency gates
.venv/bin/python scripts/generate_affected_map.py --check
.venv/bin/python scripts/apply_dispositions.py --check
.venv/bin/python scripts/check_vacuous_gate.py --check
```

`--no-sync` uses the already-synced workspace environment and avoids writing to
the sandbox-blocked global uv cache; it runs the same repository test command
with the installed `dev` fork. Focused runner, report, disposition, and
ordinary-environment skip tests were also run throughout each committed step.

The dashboard utility modules were syntax-imported with Node. A full Next build
was not run because this checkout has neither `dashboard/node_modules` nor a
package lock, and the task prohibited network installation.

## Test results

- Full repository: **1,505 passed, 33 skipped** in 46.50s.
- Ruff: **all checks passed**.
- EUROMOD Germany live selection: **3 passed, 33 deselected**.
- Locked GETTSIM adapter/live file: **73 passed**.
- Ordinary optional-engine run: **93 passed, 25 skipped**.
- Focused runner/config/provenance suite: **102 passed**.
- Focused report/runner/disposition suite: **46 passed**.
- Affected map: **OK** (127 suites, 141 suite-repo edges).
- Dispositions: **55 files validated**; the DE report has no unexplained,
  orphaned, or expired entries. Notes about already-expired BE/NY/NYC entries
  pre-date and are unrelated to this work.
- Vacuous/freshness gate: **OK** (107 oracle-backed configs, 154 suites,
  17 executable surfaces).

Expected warnings were GETTSIM's documented internal divide/grouping warnings
and pytest's pre-existing macOS temporary-directory cleanup warning; neither
affected results.

## Open questions

None for the requested scope. The branch is ready for orchestrator review; push
and pull-request creation were intentionally left undone.
