# US pipeline/suite lane A — oracle-side coverage (states A–M + OH)

Turns merged rulespec-us state income-tax cores into us-pe covered rows: a
per-case suite vs pinned PolicyEngine-US (penny-exact) and TAXSIM-2024, coverage
registration in `conformance/us-pe.yaml`, and a scoreboard regen. Mirrors the
#561 CA/NY/IL/MA pilot pattern.

## Done: OH (Ohio)

- rulespec-us: `us-oh/policies/income_tax/pilot_liability_pipeline` (separate PR,
  branch lane-a-suite-oh) — section 5747.02 graduated tax less the 5747.98
  exemption credit, six childless single/married cases 30k–300k.
- `scripts/generate_state_income_tax_liability.py`: added OH (TAXSIM state 36, PE
  `oh_income_tax_before_refundable_credits`); refactored the grid + main loop to
  a shared `_STATES` tuple so new states append in one place.
- `comparisons/oh-income-tax-liability.yaml`, `dispositions/oh-income-tax-liability.yaml`
  (6 entries — every TAXSIM-2024 residual is the Ohio 2024→2026 schedule
  vintage: HB33 base indexation $360.69→$332.00 and the 3.5%-over-$100k top rate
  collapsed to 2.75%), concept_mappings block, `conformance/us-pe.yaml`
  oh_income_tax → suite `oh-income-tax-liability`.
- Result: **PE match 100% (6/6), penny-exact** (residual < $0.0001, PE float32).
  Scoreboard us-pe covered **28 → 29**; oh_income_tax off the uncovered list.
- CI green locally: apply_dispositions --check, conformance_scoreboard/ratchet/
  burndown --check, extract_grids --check, affected_map --check, vacuous-gate
  --check, pytest (116 pass), ruff.

## Gaps logged (fail-closed/split ledger, oracle #757)

- ME: only 36/5219-SS (a dependent credit) on main; no rate schedule (36/5111)
  → not composable.
- OH nuance: the 5747.025 personal-exemption and 5747.98 exemption-credit
  SECTIONS are not yet encoded; the pipeline supplies their indexed values as
  declared inputs (CA-pilot precedent) and cites all three ORC authorities.
- CO already covered by `co-state-income-tax-ecps` (ECPS bridge) — not duplicated.

## Fan-out (blocked on rulespec-us#763 merge train, 132 modules)

Train carries A–M income-tax cores: AL, AZ, CT, DE, GA (rate + ded/exempt →
composable), DC (rate only → gap), plus CA augments. On merge, re-scan main and
fan out one state at a time. Oracle-repo merges serialize (rebase before merge,
no admin-merge).
