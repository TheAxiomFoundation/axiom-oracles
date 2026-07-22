# US pipeline/suite lane A — oracle-side coverage (states A–M + OH)

Turns merged rulespec-us state income-tax cores into us-pe covered rows: a
per-case suite vs pinned PolicyEngine-US (penny-exact) and TAXSIM (2026 since
the realignment below; 2024 before it), coverage registration in
`conformance/us-pe.yaml`, and a scoreboard regen. Mirrors the #561 CA/NY/IL/MA
pilot pattern.

## Done: TAXSIM 2026 realignment (2026-07-21)

All 21 state suites moved from `taxsim_law_year: 2024` to 2026 — the pinned
policyengine-taxsim 2.30.0 binary (cdate-20260521) models 2026 law, so all
three engines now compare at the same validation year and the 2024→2026
indexation-vintage disposition class is retired. Findings, verified
empirically against the binary:

- Federal 2026 models the OBBBA rate schedule/standard deduction, childless
  EITC, and FICA/SECA, but the qualifying-child credit machinery is absent
  (CTC collapses to the $500 ODC path; ACTC/CDCC/EITC-with-children return
  zero; 2025 models all of them incl. the $2,200 CTC). Documented in
  `docs/policyengine-taxsim.md`; the childless grids never exercise it.
- State modules at 2026 are projections: fractional extrapolated deductions/
  credits, and un-enacted rates in KY (4.0% vs enacted 3.5%), NC (4.25% vs
  3.99%), GA (5.19% vs 4.99%), UT (4.50% vs 4.45%). CO's staxbc now matches
  the pipeline to the cent (residual = its projected TABOR refund netting).
- Raw TAXSIM match moved: NY 4/6→6/6, CA 1/6→4/6, IL stays 6/6; MA 6/6→0/6
  and DE 6/6→0/6 (projection drift on fixed statutory amounts). All 110
  residual rows re-dispositioned as `explained_residual` with exact
  staxbc/credit decompositions from TAXSIM's own idtl=2 detail;
  `apply_dispositions --check`, scoreboard/ratchet/burndown, pytest (1422),
  and ruff all green. New TAXSIM concept mappings landed alongside:
  AGI↔v10, CDCC↔v24 (with the 2026 gap note), and the summed
  `us:tax/payroll#employee_fica`↔tfica scope.

## Done: axiom↔TAXSIM intersection lane + triage (2026-07-22)

New `co-tax-intersection-taxsim` suite: all 10 shared axiom/TAXSIM concepts
over the full 1,201-unit certified Colorado ECPS population. First run
9,470/12,010 match (78.9%), zero axiom execution errors; the state slice
reproduces `co-state-income-tax-taxsim` exactly. Unblocking the dormant
full-federal bridge required: excluding 26/1411 everywhere
(axiom-encode#1213, 911/a vs 911/a/1 duplicate rule), dropping the bridge
`self_employment_income` shim in favor of encoded 1402/b, aggregation-only
supply of the 1402/b tax-unit leaves, and correcting the
tax_before_credits mapping v19→v28.

Triage state (dispositions/co-tax-intersection-taxsim.yaml, 837/2,540 rows
classified with verified arithmetic):
- upstream_engine_gap: CTC (205, TAXSIM v22 = 500×depx exactly) and EITC
  (49, v25=0 with children) — the 2026 child-credit machinery gap.
- explained_residual: standard deduction (20, exact 63(f) $2,050/$1,650
  increments; TAXSIM input has no blindness column) and liability rows
  that decompose into component classes − niit − addmed within $15 (265).
- axiom_encoding_gap: uncapped OASDI (198 rows, axiom = flat 7.65% of
  wages with no 3121(a)(1) cap — axiom-encode#1214) and the SECA-chain
  rows (100, pending pull-one-case).
- Raw, fingerprinted in axiom-oracles#304 with pull-one-case
  instructions: AMT axiom-high (64 rows, 63/64 with large LTCG, median
  $24k), tax-before-credits continuum (521), taxable income (197),
  liability residual (365), state liability (530, same TABOR/credit
  mechanisms as the dedicated suite).

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
