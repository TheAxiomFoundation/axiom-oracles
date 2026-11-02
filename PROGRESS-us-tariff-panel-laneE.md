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
- [x] Regenerated committed report + dashboard artifact against the lane
      checkout (`reports/axiom-yale-us-tariff-panel-all-2026-08-03.json`
      replaces the 2026-08-02 one; 39,600 units, 24,400 match, 15,200
      mismatched in 87 signatures; dashboard copy truncated 1,000/15,200
      with a fresh premerged dispositions block).
- [x] Burned down `dispositions/us-tariff-panel.yaml` 46→30 entries:
      retired all 17 ieepa-scotus-timing entries + the scotus+mfn combined
      entry + the HK fentanyl-routing axiom_encoding_gap + the flipped
      7202111000-ieepa-0v10 entry (all now matching); re-verified the 26
      surviving old-line entries (3 case-set reshapes: 7601103000
      ieepa-0v20 10→8, ieepa-10v20 2→4 incl. HK, 9506624040-mfn-30v0
      124→132 absorbing the retired combined entry's mfn leg); added 4
      new-line entries (s201 solar stale-proxy ×2 incl. the mfn-column-2
      combo, s232 beer aluminum-content-basis ×2 incl. the UK 25% cell).
      unexplained 0, axiom_attributed_open 0.
- [x] Gates: apply_dispositions --check, scoreboard/ratchet/burndown/
      vacuous-gate/overview --check, pytest tariff+dispositions+
      conformance suites — all green. Conformance: covered 8→10 (s201,
      s338 witnessed), axiom_attributed_open 2→0, oracle_attributed
      396→8,283.
- [x] Reviewed-pin bump (counts, account sha, exposure, temporal debt,
      us-tariff-yale scoreboard witness pins) in the same reviewed diff.

## Next

Open a PR to main once the lane's rulespec-us#1200 dependency merges and
the checkout can be provenance-pinned to a real sha (the lane content
checkout has no git history, so the report carries `sha: null`).
