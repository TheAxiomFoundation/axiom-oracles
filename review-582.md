VERDICT: REQUEST_CHANGES
Reviewed head: 879bce60c9684c63470727f36dc2abf62711f1da
Needs Max: no

The changes remain within the verification-copy correction described as approved in the assignment. No commits, pushes, GitHub comments, or remote writes were made.

Findings

1. [Blocking honesty defect] The revised hero labels a mixed case count as households.
   Where: dashboard/src/components/OraclesV2.jsx:977; counting at :705 and :724; the same unit appears on oracle cards at :374 and program rows at :412.
   Scenario: the committed Medicaid-threshold report alone contributes 196 “households”, although every case compares a scalar policy parameter. The federal-tax suite contributes 87,519 tax units. These are included in the revised public headline.
   Evidence: `node .review-582/audit.mjs` imports the actual dashboard loader and suite metadata and reproduces the overview filter. Output: `heroOracles: 6`, `heroHouseholds: 992281`, `parameter: {reports: 25, cases: 325}`, `household: {reports: 113, cases: 991956}`. The Medicaid example has `population: rulespec-parameters`, `dataset: encoded_parameter_oracle`; the first federal-tax case has `case_unit: tax_unit`. See .review-582/audit.log. The counting machinery predates this PR, but the changed sentence retains its false unit, which this assignment explicitly requires reviewing.
   Fix: use an accurate unit such as comparison cases, explaining parameter checks and repeated comparisons, throughout the affected surfaces; alternatively compute a true household count with the correct entity grain and exclude scalar parameter checks.

2. [Blocking evidence gap under this assignment's checkout-only public-claim gate] The added relationship disclosures lack a supporting record in this checkout.
   Where: dashboard/src/components/OraclesV2.jsx:49 and :54.
   Scenario: the public dashboard asserts Max's CEO/co-founder roles, both organizations' fiscal sponsorship, and PolicyEngine's TAXSIM-successor work with the author's cooperation. A reviewer cannot trace those facts to committed source evidence; the assertions themselves are the only relevant matches.
   Evidence: `git grep -I -n -i -E 'PSL Foundation|Max Ghenis|co.found|fiscal.sponsor|successor|Feenberg|author.s cooperation' -- '*.md' '*.py' '*.jsx' '*.js' '*.yaml' '*.yml' ':!dashboard/public/data/**'` exits 0. The relevant organizational/successor hits are only OraclesV2.jsx:49 and :54; other hits describe unrelated legal succession. A separate `git grep -I -l -i -e 'PSL Foundation' -e 'Max Ghenis' -e "TAXSIM's successor" -e 'successor to Taxsim' -e 'my cooperation' -- '*.json' '*.html' '*.txt' '*.toml'` exits 1 with no matches. This is an evidence gap, not proof that the disclosures are false. External primary pages support Max's roles and the TAXSIM-successor statement ([PolicyEngine team](https://www.policyengine.org/us/team), [Axiom about](https://axiom.org/about), [NBER TAXSIM](https://taxsim.nber.org/)), but do not supply the checkout evidence expressly required here. The fetched PolicyEngine donation page did not expose fiscal-sponsor text.
   Fix: commit dated primary-source evidence for the approved disclosures, with precise links to the team, donation/about, and NBER statements; connect those sources to the rendered disclosures. Keep the correction.

Claim and invariant audit

- Read README.md, the full `git diff origin/main...HEAD`, and both commits from `git log --oneline origin/main..HEAD`. There are no tracked CLAUDE.md or AGENTS.md files, and no checkout-local banned-claim list or claim tests were located. CI contains artifact freshness, disposition, verification, and conformance guards. No RuleSpec module or YAML changes occur in this PR; the encoder-manifest rule is inapplicable.
- The oracle headline count preserves the Axiom-pair invariant: six oracle IDs pass the actual overview filter; a concrete PolicyEngine–TAXSIM pair is excluded by `isAxiomPair`. The revised copy no longer claims universal coverage. Committed verification context records 34/130 executable surfaces and 14,030/34,810 rules on an oracle surface; these are surface coverage signals, not individual-rule verification.
- The TAXSIM executable mechanism is supported by axiom_oracles/adapters/taxsim/pins.py:3–8 and runner.py:60–84, which resolve and use the binary packaged by policyengine-taxsim.
- SNAP QC's retained FSBEN/RAWBEN explanation and new limitation are supported by axiom_oracles/bridges/snap_qc_compare.py:3–20, populations/snap_qc.py:839–845, and docs/snap-qc-oracle-playbook.md:62–139: the replay uses edited income/deduction inputs and passing eligibility facts. Eligibility remains untested.
- SPSD/M's local-evidence limitation is supported by the committed report: 8,702 mismatches, 50 published mismatch examples, no public household case index. The revised hero drops “every”; aggregate disagreement tracking is public, so this narrower wording is not independently a blocker.
- The changed household hint remains a heuristic, not a demonstrated causal diagnosis. The triangulation code joins case IDs and agreement flags; it does not adjudicate legal correctness. No committed-data failure of the revised hint was established.
- `dashboard/next.config.mjs` configures `/oracles`, and dashboard/vercel.json redirects to axiom.org/oracles. Actual live deployment, embedding on axiom.org/validation, companion PR #294, and historical live-bundle text are not verifiable from this checkout. They are contextual PR-body evidence gaps, not additional defects in this head's executable copy.

What I ran

- `git rev-parse HEAD`: exact requested SHA. `git diff --check origin/main...HEAD`: passed. Both commits and the entire two-file diff were read.
- `cd dashboard && bun install --frozen-lockfile --cache-dir ../.review-582/bun-cache`: passed, 54 packages installed.
- `cd dashboard && bun run build`: passed; production compile, TypeScript, static export, 3/3 pages.
- `cd dashboard && node scripts/test-case-agreement.mjs`: 4 assertions passed, 0 failed.
- `cd dashboard && bun build src/utils/data.js --target node --format esm --outfile ../.review-582/data-bundled.mjs`: passed. `cd dashboard && node ../.review-582/test-loader-equivalence.mjs`: 2 gates passed. A scratch copy redirects the existing script's /tmp bundle import into this worktree. Both paths report 229 reports, 228 suites, 9 oracles, 554 concepts, 16 programs, 10,064,931 comparisons; equivalence true, legacy-suite leftovers 0.
- `node .review-582/check-copy.mjs`: 4/4 source checks and 4/4 exported-bundle checks passed across 28 JS/HTML/TXT files. All four specified old strings are absent.
- `node .review-582/audit.mjs`: executed successfully; the household-unit invariant fails on committed data, as described above.
- `UV_CACHE_DIR="$PWD/.review-582/uv-cache" UV_PYTHON_INSTALL_DIR="$PWD/.review-582/python" uv sync --extra dev`: passed, 23 packages installed.
- Local CI checks: see the command table below and .review-582/ci-*.log. `uv run python scripts/de_executable.py --check` initially exited 1 with “DE Kindergeld executable status drifted; regenerate with python scripts/de_executable.py”. Its script, manifest and status have no PR diff. An executed `--print-status` then exactly matched committed status bytes (4,396 bytes; both computed_pass; no blockers), and a repeat of `--check` exited 0. The initial failure was not reproduced; its cause was not established.
- `UV_CACHE_DIR="$PWD/.review-582/uv-cache" UV_PYTHON_INSTALL_DIR="$PWD/.review-582/python" uv run pytest -q --basetemp="$PWD/.review-582/pytest-tmp"`: interrupted, exit 130. Observed summary: 207 passed, 32 skipped in 1,335.63 seconds, followed by KeyboardInterrupt. This is not a full-suite pass. The broad run was stopped while parsing unrelated Pennsylvania state-tax contract YAML; remaining tests were not completed.
- `UV_CACHE_DIR="$PWD/.review-582/uv-cache" UV_PYTHON_INSTALL_DIR="$PWD/.review-582/python" uv run pytest -q tests/test_dashboard_overview.py tests/test_dashboard_loader.py --deselect tests/test_dashboard_loader.py::test_loader_equivalence --basetemp="$PWD/.review-582/dashboard-pytest-tmp"`: 7 passed, 1 deselected, 0 failed in 43.32 seconds. The deselected loader test hardcodes `/tmp/data-bundled.mjs`; its equivalent was executed from a worktree-local scratch copy as described above.
- CI's separately provisioned GETTSIM live job and source-built NZ replay were not run. Their extra dependency environment and pinned external engine/RuleSpec checkouts are not provisioned in this worktree.
- Process diagnostics/control were unavailable: `ps -axo pid,ppid,etime,time,state,command` was denied with “operation not permitted”; the exact-worktree `pkill -INT -f '.../.review-582/pytest-tmp$'` attempt exited 3, “sysmond service not found; Cannot get process list”. The suite was interrupted through its execution session instead. Neither command is counted as passing.
- No new or changed tests appear in the PR, so the requirement to mutate each changed test's guarded code is inapplicable. No tracked file was mutated for review; no restoration was needed. `git status --short --untracked-files=no` and `git diff --check` are clean.

Local CI command results: 33 passed, 1 failed initially, 2 interrupted. The failed DE check passed on recheck. Full CI was not completed. All commands below ran with UV_CACHE_DIR and UV_PYTHON_INSTALL_DIR inside .review-582, through `.venv/bin/python .review-582/run_ci_checks.txt`.

| Exact command | Observed result |
| --- | --- |
| `uv run ruff check .` | PASS (exit 0) |
| `uv run scripts/run_comparison.py --list` | PASS (exit 0) |
| `uv run scripts/check_rule_verification.py` | PASS (exit 0) |
| `uv run scripts/check_state_tax_populace_contract.py` | PASS (exit 0) |
| `uv run scripts/apply_dispositions.py --check` | PASS (exit 0) |
| `uv run python scripts/nz_incomeexplorer.py --check` | PASS (exit 0) |
| `uv run python scripts/emit_disposition_artifacts.py --check de-worker-dual-oracle` | PASS (exit 0) |
| `uv run python scripts/emit_case_artifacts.py --check de-worker-dual-oracle` | PASS (exit 0) |
| `uv run python scripts/de_axiom_legs.py --check` | PASS (exit 0) |
| `uv run python scripts/de_unified_comparison.py --check` | PASS (exit 0) |
| `uv run python scripts/de_closure.py --check` | PASS (exit 0) |
| `uv run python scripts/de_executable.py --check` | FAIL (exit 1); recheck PASS |
| `uv run python scripts/de_certificate_census.py --check` | PASS (exit 0) |
| `uv run python scripts/generate_chunk_indexes.py --check` | PASS (exit 0) |
| `uv run python scripts/exercise_census.py --check` | PASS (exit 0) |
| `uv run python scripts/validate_bridge_manifests.py --strict` | PASS (exit 0) |
| `uv run python scripts/nz_executable_reproduction.py --check` | PASS (exit 0) |
| `uv run python scripts/nz_closure.py --check` | PASS (exit 0) |
| `uv run python scripts/nz_exercise_denominator.py --check` | PASS (exit 0) |
| `uv run python scripts/certify.py --check` | INTERRUPTED (exit 130) |
| `uv run python scripts/us_tariff_capture_integrity.py` | PASS (exit 0) |
| `uv run scripts/emit_case_artifacts.py --check al-snap-ecps ma-snap-ecps nc-snap-ecps sc-snap-ecps tn-snap-ecps` | PASS (exit 0) |
| `uv run scripts/emit_disposition_artifacts.py --check al-snap-ecps ma-snap-ecps nc-snap-ecps sc-snap-ecps tn-snap-ecps` | PASS (exit 0) |
| `uv run scripts/extract_grids.py --check` | PASS (exit 0) |
| `uv run scripts/generate_boundary_cases.py --check` | PASS (exit 0) |
| `uv run scripts/generate_affected_map.py --check` | PASS (exit 0) |
| `uv run scripts/check_vacuous_gate.py --check` | PASS (exit 0) |
| `uv run scripts/generate_dashboard_overview.py --check` | PASS (exit 0) |
| `uv run scripts/generate_conformance_universe.py --all --check` | PASS (exit 0) |
| `uv run scripts/closure_universe.py --check` | PASS (exit 0) |
| `uv run scripts/generate_conformance_compositions.py --all --check` | PASS (exit 0) |
| `uv run scripts/conformance_scoreboard.py --check` | PASS (exit 0) |
| `uv run scripts/conformance_ratchet.py --check` | PASS (exit 0) |
| `uv run scripts/unexplained_ratchet.py --check` | PASS (exit 0) |
| `uv run scripts/conformance_burndown.py --check` | PASS (exit 0) |
| `uv build` | INTERRUPTED (exit -2) |

The interrupted certificate check spent 1,769.8 seconds before stopping in the NZ closure ancestor-history subprocess. `uv build` spent 416.1 seconds and had emitted only “Building source distribution...” before interruption. Neither is a pass or an established PR defect. Their sources are unchanged by this two-component copy diff.
