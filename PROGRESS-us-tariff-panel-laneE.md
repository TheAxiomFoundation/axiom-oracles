# PROGRESS — us-tariff-panel lane E (witness-line burn-up dispositions)

Branch `laneE/witness-extract-refresh`. Predecessor commit `aabd3465` burned
the covered slice up from 3 to 5 HTS-10 lines (adding `2203000030` beer,
`8541420010` solar PV cells) at the unchanged Yale pin `c4307e51`. The
rulespec-us composition gained the witness-line encodings plus the IEEPA
termination fix (EO 14389 legal-date reading: active versions end
2026-02-19, proved-zero 2026-02-20→2026-02-23) on rulespec-us#1200
(content at the pinned lane checkout).

## State

- [x] Suite wiring: section_201/section_338 slots mapped to their encoded
      concepts (`axiom_oracles/suites/us_tariff_panel.py`), test-owned
      REVIEWED_AUTHORITY_SLOTS literal moved in the same diff.
- [ ] Regenerate committed report + dashboard artifact against the lane
      checkout (run_comparison us-tariff-panel; new dated `-all-` report
      replaces the 2026-08-02 one).
- [ ] Burn down `dispositions/us-tariff-panel.yaml`: retire
      ieepa-scotus-timing (now matching), re-verify surviving old-line
      entries, add new-line entries (s201 solar proxy, s232
      beer aluminum-derivative basis, mfn column-2 on the new lines, plus
      whatever the fresh report's signatures actually contain).
- [ ] Gates: apply_dispositions --check, pytest tariff suites, conformance
      scoreboard/ratchet/vacuous-gate surfaces regenerated.
- [ ] Reviewed-pin bump commit (counts, account sha, exposure, debt,
      scoreboard witness pins).

## Next

Regenerate the panel report with:
`RULESPEC_US_CHECKOUT=/private/tmp/laneE-test/rulespec-us`
`AXIOM_RULES_ENGINE_BINARY=/private/tmp/laneE-test/axiom-rules-engine/target/release/axiom-rules-engine`
