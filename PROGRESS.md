# PROGRESS — us-pe conformance universe

Branch `claude/us-pe-conformance` (from `origin/main`). Stand up the `us-pe`
conformance universe mirroring `uk-pe` (axiom-oracles#188). **Measurement, not
coverage work** — no new suites built; day-one number is honestly low.

## Status: COMPLETE — ready for PR / CI

All gates green locally (`uv run`): ruff, `generate_conformance_universe.py --all
--check`, `conformance_scoreboard.py --check`, `conformance_ratchet.py --check`,
`conformance_burndown.py --check`, full `pytest` (1253 passed, 12 skipped),
`uv build`.

## Scoreboard line (verbatim)

```
"jurisdiction": "us-pe", "oracle": "policyengine-us_1.767.3/us",
"policies_in_scope": 140, "covered": 27, "covered_pct": 19.2857, "excluded": 8,
"excluded_by_reason": {"input_carrying": 7, "technical": 1},
"unexplained_total": 23138, "axiom_attributed_open": 0, "oracle_attributed": 0,
"bridge_artifacts": 0, "conformant": false
```

## Granularity rule (badge denominator)

One row per PE-US program instrument at the granularity of the household-facing
output variable PE computes, derived deterministically from PE-US's own module
tree (`policyengine_us/variables/gov`) + PE-native parameter lists:
- Federal income tax → component surfaces + each credit in
  `gov.irs.credits.refundable`/`non_refundable` (23 rows).
- Payroll & SECA (6).
- Federal benefit/health programs = `gov.household.household_benefits` list +
  `household_health_benefits` expansion (24 rows, 8 excluded).
- **Per-state** rows for each `<state>_income_tax` (44) and each
  `STATE_TANF_VARIABLES` member (51) — mirroring PE's per-state variable tree.
  SNAP/SSI stay national (one PE variable each). The per-state/national split is
  the rule following PE's tree, not a coverage choice.
In-scope iff PE carries the primary output with a computed surface (`def formula`
OR `adds`/`subtracts`). 148 rows total, **140 in-scope**, 8 excluded
(`input_carrying` reported passthroughs ×7 + `technical` reform-lever
`basic_income`) — the PE-US analogue of uk-pe's 8 exclusions.

## Pin

`policyengine-us==1.767.3` (current release; the `pinned_version()` metadata
fallback reads it from the installed distribution — no dirty local checkout).

## Day-one coverage (27 covered, verified running vs PE-2026, no vacuous regs)

- Federal income tax + payroll via `fiit-ecps` (12 rows).
- `ssi-ecps` (SSI); `ca-snap-ecps` (SNAP, national row, canonical of 11 state
  suites); `medicaid-magi-co-ecps` (Medicaid categorical).
- State income tax: `co-state-income-tax-ecps` (pop) + CA/NY/IL/MA
  `*-income-tax-liability` composed grids (rulespec-us #556-#561, 3-way vs PE + TAXSIM).
- Per-state TANF: az/ca/co/ks/mn/ny/wa suites.
- `fl-snap-ecps` NOT registered — its committed report is mislabeled
  `nyc-synthetic`; co-tanf-coverage NOT registered (0 comparisons, vacuous).

## Files

- Code: `axiom_oracles/conformance/universe.py` (adds/subtracts computed test,
  `pinned_version` metadata fallback, `PE_US_PROGRAM_SPINE`),
  `scripts/generate_conformance_universe.py` (us-pe config + spine wiring),
  `tests/test_conformance.py` (+7 tests), `conformance/README.md`.
- Artifacts: `conformance/us-pe.yaml`, `conformance/detail/us-pe.json`,
  `conformance/history/us-pe/2026-07-07.json`, `conformance/scoreboard.json`,
  `conformance/ratchet.yaml` (us-pe row added), burndown + dashboard mirrors.

## Reproduce enumeration

`pip install policyengine-us==1.767.3` into a venv, then
`generate_conformance_universe.py us-pe --model-root <site-packages>` (metadata
fallback pins the version). CI runs it as a no-op (no matching checkout).

## Remaining

Open PR, poll CI foreground to green, merge (no admin-merge). concept_mappings.yaml
untouched. rulespec-us untouched (bulk-health worker owns it).
