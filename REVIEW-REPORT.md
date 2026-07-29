VERDICT: REQUEST-CHANGES

# Blind adversarial review — axiom-oracles PR #425

## Reviewed state

- PR: `TheAxiomFoundation/axiom-oracles#425`
- Verified head branch: `fed-parity/chunk1-oracle-suites`
- Frozen head: `309e380a6d7bc6f80fb47b4341985786e98c9ad0`
- Merge base: `f8ea6027984b9da73c6f4b58d15a20b450181ac4`
- GitHub base observed during review:
  `fe00bad51f85e7128f762d66dd5121324889b156`
- RuleSpec: `345c22030642cbd37a9fe46877591a8e1df5af7e`,
  tree `40e08f7dbaa88a70660006f3a5a32bfa283ebd85`
- PolicyEngine source pin:
  `49d19b239a593dbac8920ac6fd80cfe33372343a`, tree
  `272be973bc0adddc9e176a6a772a3e113bc15427`
- Runtime: Python 3.13, PolicyEngine 4.18.9,
  PolicyEngine-US 1.767.3, PolicyEngine-Core 3.30.3

The suites, expected values, live divergences, statutory arithmetic, generator
contracts, mappings, and generated artifacts are technically sound. Approval is
blocked because the evidence chain required to adopt five known mismatches is
mislinked and partly inaccurate.

## Required changes

### 1. Two SALT dispositions point to the wrong upstream issues

The evidence URLs are shifted by one issue:

- [`salt-magi-911-addback` links #9167](dispositions/us-salt-deduction-grid.yaml),
  at line 47. Issue
  [#9167](https://github.com/PolicyEngine/policyengine-us/issues/9167) is the
  low-AGI ceiling issue; this case belongs to
  [#9168](https://github.com/PolicyEngine/policyengine-us/issues/9168).
- [`salt-personal-property-tax-probe` links #9168](dispositions/us-salt-deduction-grid.yaml),
  at line 89. This case belongs to
  [#9169](https://github.com/PolicyEngine/policyengine-us/issues/9169).

As committed, #9169 is not referenced by any disposition. Correct both URLs so
each source-expiring exception points to the issue that actually tracks its
mechanism.

### 2. Issue #9168 is not an accurate, runnable evidence artifact

The divergence is real, but the filed reproduction is defective:

- Its situation binds `foreign_earned_income_exclusion` under `people`.
  PE-US 1.767.3 defines that variable on `TaxUnit`/year. Running the pasted
  situation verbatim raises `SituationParsingError`.
- Moving the value to `tax_units` makes the reproduction run and yields the
  expected live diagnostics: exclusion `10000`, SALT cap `40400`.
- The issue cites section 164(b)(7)(D) for modified AGI. The applicable
  provision in the pinned RuleSpec proof is section 164(b)(7)(B)(iv).

Update [#9168](https://github.com/PolicyEngine/policyengine-us/issues/9168), or
replace it with a correct issue, before using it as disposition evidence.

### 3. Issue #9170 inaccurately states the pinned PE mechanism

The issue's high-level mismatch and observed result are correct, but its
parenthetical arithmetic is not the path in the pinned code. PE does not add
the $50,000 itemized deduction while constructing its taxable-income proxy.
The actual path is:

```text
taxable_income = max(0, 700000 - 0) = 700000
excess = max(0, 700000 - 640600) = 59400
lesser_amount = min(50000, 59400) = 50000
```

Update [#9170](https://github.com/PolicyEngine/policyengine-us/issues/9170) so
the filed mechanism matches
`itemized_taxable_income_deductions_reduction.py` at the pin.

### 4. Adoption notes and the author ledger still describe unfinished work

All five issue placeholders remain literal `MAIN-LANE-TBD` values in
[`conformance/us-pe.yaml`](conformance/us-pe.yaml), at lines 596–597 and
1120–1122. The two generated conformance-detail copies faithfully inherit the
stale text. SPINE-PLAN section 8 requires the filed issue links in the adoption
notes.

The frozen PR-head `PROGRESS.md` also ends by saying the next step is to file
the five issues and replace those placeholders. Commit `309e380a` changed only
the two disposition files and did not append the required state/done/next
checkpoint. Replace the placeholders, regenerate the dependent artifacts, and
append a truthful closeout checkpoint.

## Independent regeneration

Both suites were generated independently from the clean RuleSpec snapshot with
a fresh `Simulation` for every case.

| Suite | Raw result | After dispositions | Independent parity |
|---|---:|---:|---|
| `us-salt-deduction-grid` | 13/16 | 16/16 | Exact except provenance timestamp |
| `us-itemized-taxable-income-deductions-grid` | 15/17 | 17/17 | Exact except provenance timestamp |

- Registry regeneration left both comparison YAML files byte-identical.
  Their SHA-256 values are
  `5b30fdad77e910e3c35a897e7353734f83701ea7df362180be6ed7cc48944b88`
  and
  `0692842e4a04fda5f2dd5393d5f5ce00396aec7817dbb67a6181ccc5a33b04ac`.
- Canonical report bytes matched after removing only
  `provenance.generated_at`.
- All 33 Axiom values and all 33 `axiom_fixture_inputs` mappings equal the
  #1177 companion outputs and inputs. Eight explicit spot checks covered both
  suites and all disposition classes.
- The absolute/relative tolerance remains exactly `0.01`/`0.0`; there is no
  case or binding override and no widened tolerance.

## Five live divergences and lawful results

Every mismatch was rerun in a separate exact-stack simulation. The mismatch set
was exactly the five pre-registered cases; the other 28 adopted cases passed.

| Case | Lawful Axiom value | Live PE value | Pinned PE mechanism |
|---|---:|---:|---|
| Low-AGI SALT ceiling | 10,000 | 5,000 | Extra AGI-minus-exemptions deduction ceiling |
| Section-911 MAGI addback | 38,900 | 40,400 | Cap phaseout uses AGI without section-911 addback |
| Personal-property tax | 4,000 | 0 | SALT source list omits personal-property tax |
| Section-68 lawful base | 50,000 | 47,297.296875 | Reduction base uses AGI-minus-exemptions proxy |
| Exact 2/37 rate | 9,459,459.45945946 | 9,459,460 | Stored decimal rate and float32 rounding |

Installed exact-version blobs matched the pinned Git objects for all required
SALT, source-list, itemized-reduction, OBBB-rate, and OBBB-applies files. Each
disposition has `expires_on_source_change: true`.

The statutory arithmetic recomputed from the pinned corpus is:

```text
min(10000, 40400) = 10000
40400 - 0.30 * (500000 + 10000 - 505000) = 38900
personal-property tax = 4000
max(0, 550000 + 50000 - 640600) = 0; reduction = 0
2 / 37 * 10000000 = 540540.540540...
```

## Generator contract

- Instrumentation observed 16 distinct SALT simulations and 17 distinct
  itemized simulations.
- Both suites resolved filing statuses to all five PE enum values
  `0, 1, 2, 3, 4`. Head of household and surviving spouse are explicitly
  bound; joint and separate are relationship-derived rather than falling
  through to single.
- Mutation probes reject missing, extra, string, and boolean bridge outputs,
  as well as missing/wrong RuleSpec domain and RuleSpec-only inputs.
- Personal-property tax is nonzero only in its named probe and never enters a
  PE situation.
- `taxable_income_determined_without_section_68` is present in all 17 itemized
  companions and never enters PE.
- Each suite scores exactly one Axiom output, disjoint from its bridge and
  diagnostic outputs.
- Exact-stack generator tests: `34 passed`.

## Adoption, mappings, checks, and containment

- `conformance/us-pe.yaml` changes exactly the SALT and itemized target rows;
  each receives the intended suite and engine-backed report.
- The RuleSpec modules expose exactly seven derived outputs, and the patch adds
  exactly seven corresponding mapping records. The five named PE candidates
  resolve dynamically in PE-US 1.767.3 with matching TaxUnit/year/USD
  metadata. All 4,421 preceding mapping records are unchanged.
- Nine read-only drift gates pass:
  dispositions, grids, affected map, vacuous gate, scoreboard, ratchet,
  burn-down, overview, and conformance compositions.
- Additional results:
  `81 passed, 2 skipped` conformance tests;
  `147 passed` affected-map/grid/disposition tests;
  `39 passed` mapping loader/import tests;
  `47 passed` case-schema tests; and
  `25 passed` pinned-RuleSpec state bridge tests.
- The merge-base-to-head patch contains exactly the intended 26 paths,
  5,681 additions, and 137 deletions. `git diff --check` passes; no foreign
  path is present.
- Against current RuleSpec, the known clean-main fingerprint remains exactly
  `5 failed, 19 passed, 1 skipped`: one CA, two IL, one NY, and one OH test.
  For the live GitHub base, the only test-relevant post-merge-base change was a
  17-row CalFresh BBCE addition. A clean control with that exact patch matched
  live main's mapping blob
  `ca6238a9e519bacd8fbb3c7a33d71faa372f8e30` and reproduced the identical
  fingerprint.

## Sandbox and review limitations

- The default `uv` cache could not initialize its internal Git directory
  because the sandbox denied access. Exact-stack runs succeeded offline using
  existing immutable packages and writable temporary caches.
- GitNexus indexed a disposable frozen-head copy, but registry creation was
  denied at `/Users/maxghenis/.gitnexus/registry.json`; direct
  changed-symbol/caller/gate analysis was used instead.
- Shell GitHub access and `git fetch` could not resolve `github.com`. Live PR,
  issue, commit, patch, and blob evidence was retrieved read-only through the
  connected GitHub service. No branch, remote, PR, or issue was modified.
- Direct `uscode.house.gov` requests returned HTTP 403. Statutory verification
  used the pinned RuleSpec/corpus sources and official enrolled-law material.
- Sandbox policy rejected one `rm -rf` cleanup attempt. Both explicitly named
  disposable control archives were subsequently removed with a bounded
  depth-first deletion.

## Required retest after correction

Correct the two disposition URLs and the two filed issue bodies; replace all
five adoption placeholders; regenerate conformance detail, scoreboard,
history/ratchet/burn-down/freshness/overview as applicable; append
`PROGRESS.md`; then rerun the two generators, disposition check, all nine drift
gates, exact-stack generator/conformance tests, and diff containment check.
