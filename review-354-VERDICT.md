VERDICT: REQUEST-CHANGES

# PR #354 blind adversarial review

Reviewed live PR range:

- base: `f84dee02541562dcf9f93cccbdfa94688e6a7456`
- head: `a577132904328d626b997311a41abdd244c99a47`

The PR head changed during review. The initially verified remote head was
`2a41f72297346f422936b28b19bf9f39f87d3cef`; GitHub then moved it to
`a5771329...`. This verdict gates the latter, re-frozen live head. The former was
also not approvable: its QBID report was stale and it had only one disposition
file.

## Findings

### CRITICAL — The live tree is not the seven-suite 34/127 freeze artifact

The diff adds **eight** configs and reports, including the Saver's Credit suite
that the required freeze withdraws:

- `comparisons/us-savers-credit-grid.yaml`
- `dashboard/public/data/axiom-policyengine-us-savers-credit-grid.json`
- `dispositions/us-savers-credit-grid.yaml`

`conformance/us-pe.yaml:1084-1095` actively adopts Saver's Credit, and
`tests/test_conformance.py` asserts that adoption. The committed scoreboard is
**35/127**, not 34/127 (`conformance/scoreboard.json:71-84`), and the committed
floor is 35 (`conformance/ratchet.yaml:22-26`). This contradicts both the
requested freeze and the PR title's “27→34 covered” claim.

### CRITICAL — QBID is neither provenance-correct nor reproducible on RuleSpec main

The committed QBID report cites RuleSpec `dc6602f...`, not required main
`3373e841...` (`dashboard/public/data/axiom-policyengine-us-qbid-grid.json:568-585`).

An exact replay against the clean canonical checkout
`3373e8411f7e141fd50879e3de964386f606f7f6`, tree
`7e00f195ea81ff9aa21c58d53151e937d974a016`, fails before PolicyEngine
comparison. The generator still requires the obsolete
`qualified_business_income_threshold_amount_2026` fixture key and statute-level
filing status (`scripts/generate_federal_tax_liability.py:1241-1261`), while
merged main derives the threshold and supplies pipeline-level filing status.
Therefore the committed 10/11 match table cannot be regenerated from the
claimed source.

### CRITICAL — The restored Saver's Credit evidence is stale and cannot run on main

The committed Saver's report also cites `dc6602f...`
(`dashboard/public/data/axiom-policyengine-us-savers-credit-grid.json:628-645`).
Replay against `3373e841...` fails because
`us/policies/income_tax/savers_credit_pipeline.test.yaml` does not exist on
merged main. This is the corpus-chain reason the suite was supposed to remain
withdrawn; nevertheless the live tree counts it covered.

### HIGH — The dashboard manifest has none of the federal report entries

`dashboard/public/data/manifest.json` is unchanged by the PR and contains zero
entries matching the eight federal grid report names. Each successful replay
reported that it had to add its report to the manifest. The reports are
committed but not registered as required.

### HIGH — Canonical RuleSpec provenance is not enforced

All federal configs provide only a mutable remote and local-root preference,
for example `comparisons/us-qbid-grid.yaml:47-60`; none pins
`rulespec_upstream_sha` or the canonical tree. The runner accepts any existing
checkout and stamps whatever HEAD it sees. It does not reject a dirty,
noncanonical, or tree-mismatched snapshot. This allowed the two stale
`dc6602f...` reports to coexist with configs/comments implying current main.

### HIGH — The two dispositions do not link the filed upstream issues

Both filed PolicyEngine issues exist and describe the exact committed
mechanisms:

- [PolicyEngine/policyengine-us#9150](https://github.com/PolicyEngine/policyengine-us/issues/9150)
  — QBID active-business-QBI floor defect
- [PolicyEngine/policyengine-us#9151](https://github.com/PolicyEngine/policyengine-us/issues/9151)
  — Saver's Credit inclusive-tier boundary

However, `dispositions/us-qbid-grid.yaml:10-26` and
`dispositions/us-savers-credit-grid.yaml:10-30` link source-code blobs, not
issues #9150/#9151. Thus the required two disposition rows do not carry their
filed upstream issue links.

### MEDIUM — Expected nonstatutory-reason schema/README work is absent

The PR changes row-specific tests but does not change
`axiom_oracles/conformance/schema.py` or `conformance/README.md`. The base
already recognizes the reason token, but validation enforces a note for
`oracle_models_repealed_law` and not for
`oracle_models_nonstatutory_amount` (`schema.py:232-251`), despite the reason's
own documentation saying a governing-instrument note is required. The expected
generic schema/README contract therefore is not delivered by this range.

## Required checks

### Report replay and match-table comparison

Using the exact command shape
`uv run scripts/run_comparison.py <suite> --summary` with offline pinned wheels
and clean RuleSpec main `3373e841...`, six suites reran successfully. Their full
`.cases` match tables were canonicalized with `jq -c` and byte-compared with
`cmp`:

| Suite | Replay | Nonzero matches | Match table |
| --- | ---: | ---: | --- |
| ACA PTC | 6/6 | 4 | byte-identical (`442122f3...`) |
| Additional Medicare | 5/5 | 4 | byte-identical (`488fb036...`) |
| Elderly/disabled | 9/9 | 7 | byte-identical (`991e1f4c...`) |
| LLC | 12/12 | 9 | byte-identical (`4d0daadb...`) |
| NIIT | 6/6 | 5 | byte-identical (`2c929327...`) |
| SECA | 6/6 | 5 | byte-identical (`680d141f...`) |
| QBID | failed pre-comparison | — | no current-main table possible |
| Saver's Credit | missing main fixture | — | withdrawn lane is not runnable |

Provenance across the committed reports is six at `3373e841...` and two
(QBID, Saver's Credit) at `dc6602f...`; it is not correct for all seven required
live suites.

### Additional Medicare wage-only boundary

PASS. The merged RuleSpec compose at `3373e841...` makes the SE domain valid
only when the foreign-system attestation holds and imported federal SE income is
zero, and fail-closes both the SE and combined outputs outside it. The five
generator cases all set SE income to zero; committed results are
`[0, 450, 450, 225, 1800]`, so four are nonzero. The us-pe note states the
five-case wage-only boundary and the pending 26 CFR 1.1401-1 corpus chain
(`conformance/us-pe.yaml:39-56`, `axiom-corpus#523`).

### Ratchet and counts

- Main: 27 covered / 136 in scope, unexplained 0, Axiom-attributed open 0.
- Live head: **35** covered / 127 in scope, unexplained 0, Axiom-attributed
  open 0.

The live head does not regress the monotonic invariant relative to main, and
`conformance_ratchet.py --check` passes. It nevertheless violates the required
34/127 freeze. A 35 floor was also committed in the earlier PR history
(`249adb5e`, `31d6ad57`) though never on main; the current live head commits 35
again.

### Diff prohibition

PASS. No `fiit-ecps` config/report and no other pre-existing comparison
config/report is edited. The suite/report delta consists of additions, but it is
the wrong set of additions because Saver's Credit remains.

### Validation battery

On `a5771329...`:

- all ten CI `--check` gates passed;
- ruff, registry validation, rule-verification validation, and the state-tax
  Populace contract passed;
- full pytest passed in the offline toolchain configuration:
  `1786 passed, 57 skipped`.

With unusable `npx` left visible, the same test run reached
`1787 passed, 55 skipped, 1 failed`; the sole failure was
`test_dashboard_loader.py::test_loader_equivalence` attempting a blocked npm
download of esbuild, not a code assertion. Hiding the unavailable Node toolchain
triggered the test's designed skip and produced the passing full run above.

## Merge gate

Do not merge `a5771329...`. At minimum: withdraw Saver's Credit, restore 34/127;
update QBID to the merged-main fixture contract and rerun it; require
SHA+tree-verified RuleSpec snapshots; regenerate every live report at
`3373e841...`; add all seven manifest entries; link dispositions to the filed
PolicyEngine issues; and restore the expected generic nonstatutory schema/README
contract.
