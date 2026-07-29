VERDICT: REQUEST-CHANGES

# PR #425 repair re-review

## Reviewed state

- Repository: `TheAxiomFoundation/axiom-oracles`
- Repair head: `1ce97c22a4d0c9213e8a44c94fe120693b91faf1`
- Repair base: `309e380a6d7bc6f80fb47b4341985786e98c9ad0`
- Scope: only the five claimed repairs and `309e380a..1ce97c22`
  containment
- Review writes: local review branch/worktree only; no PR branch, remote,
  issue, or other GitHub mutation

The structured disposition repairs, exact URL mapping, both requested issue
body corrections, active conformance notes, generated detail artifacts,
append-only closeout, eight canonical checks, and changed-path containment all
pass. Approval remains blocked by two literal residual defects in the repaired
evidence/acceptance surface.

## Findings

### 1. Issue #9168 still presents the wrong statutory subsection in its title

The corrected body of
[policyengine-us#9168](https://github.com/PolicyEngine/policyengine-us/issues/9168)
is accurate: it binds `foreign_earned_income_exclusion` on `tax_units`, cites
section 164(b)(7)(B)(iv), and explains that PE phases out the SALT cap from
plain AGI. The live issue title still says:

```text
SALT cap phaseout uses AGI instead of §164(b)(7)(D) modified AGI ...
```

That stale title contradicts the repaired body and the governing
section 164(b)(7)(B)(iv). The upstream issue is the source-expiring evidence
artifact linked by the disposition, so leaving its headline legally incorrect
does not fully repair the prior wrong-subsection finding.

Required change: update the issue title to section 164(b)(7)(B)(iv), then
reconfirm the linked evidence.

### 2. The claimed whole-tree `MAIN-LANE-TBD` count is four, not zero

At the frozen target:

```text
PROGRESS.md:1042
PROGRESS.md:1072
PROGRESS.md:1155
PROGRESS.md:1170
```

These are historical ledger sentences; no occurrence remains in
`conformance/us-pe.yaml`, either generated detail copy, the dispositions, or
any other path. Nevertheless, the explicit acceptance criterion was a
whole-tree grep returning zero, and the target does not meet it.

The repair also correctly preserves the prior ledger and appends its closeout
at EOF (`PROGRESS.md` is `+17/-0`). Those two requirements are in tension:
strict byte-preservation retains three earlier mentions, while the appended
closeout itself adds the fourth. The repair must either remove/replace the
literal token under an agreed ledger policy or the acceptance criterion must
explicitly exempt historical `PROGRESS.md` prose. The reviewer cannot treat
“whole tree” as that unstated exemption.

## Passing repair evidence

### Dispositions and issue mapping

- All five `upstream_engine_gap` entries have the same evidence-key set as the
  `us-qbid-grid` model: `mechanism`, `arithmetic`, `upstream_url`, and
  `sources`.
- Each entry includes its applicable local comparison YAML:
  `comparisons/us-salt-deduction-grid.yaml` or
  `comparisons/us-itemized-taxable-income-deductions-grid.yaml`.
- Both the structured field and free-text mechanism map exactly:
  `salt-low-agi-engine-cap` to #9167,
  `salt-magi-911-addback` to #9168,
  `salt-personal-property-tax-probe` to #9169,
  `itemized-68-other-deduction-base` to #9170, and
  `itemized-68-rational-rate` to #9171.
- Each of #9167-#9171 occurs exactly once in each representation.
- `scripts/apply_dispositions.py --check` exits zero: 85 files validated and
  committed dashboard data consistent.

### Issue bodies and pinned source

- Issue #9168's body was replayed verbatim against cached PE-US 1.767.3 and
  PE-Core 3.30.3. It runs without a parsing error and returns
  `foreign_earned_income_exclusion=[10000]` and `salt_cap=[40400]`.
- Pinned commit `49d19b239a593dbac8920ac6fd80cfe33372343a` declares the
  exclusion on `TaxUnit`/year. Its `salt_cap.py` uses
  `adjusted_gross_income` directly and applies no sections 911/931/933
  addback.
- Issue #9170's body now matches the pinned formula:
  taxable-income proxy `700000`, excess `59400`, lesser amount `50000`,
  decimal product `2702.7025`, observed float-array reduction
  `2702.702392578125`, and final deductions `47297.296875`.

### Conformance, regeneration, and checks

- The active adoption notes name #9167-#9169 for SALT and #9170-#9171 for
  itemized deductions; they contain no placeholder.
- `conformance/detail/us-pe.json` and
  `dashboard/public/data/conformance_detail_us-pe.json` are byte-identical
  with SHA-256
  `574f41ab7c4ba2ff0dffa1dc92edba1a4198fc68a93e6d3cb37350f9dd122159`.
- All eight canonical read-only checks exit zero:
  dispositions; grids; affected map (174 suites / 183 edges); vacuous gate
  (138 configs, 217 suites / 34 executable surfaces); scoreboard
  (4 jurisdictions / 3 conformant); ratchet; burn-down (4 series / 57 points);
  and dashboard overview (218 reports).
- Per the repair-only brief, the previously accepted 33-case suite
  regeneration, tolerances, containment, and statutory arithmetic were not
  re-reviewed.

### Diff containment

`1ce97c22` is the direct child of `309e380a`. The repair changes exactly six
regular files, all inside the allowed surface:

```text
PROGRESS.md
conformance/detail/us-pe.json
conformance/us-pe.yaml
dashboard/public/data/conformance_detail_us-pe.json
dispositions/us-itemized-taxable-income-deductions-grid.yaml
dispositions/us-salt-deduction-grid.yaml
```

There are no renames, copies, mode changes, submodules, or foreign paths.
`git diff --check 309e380a..1ce97c22` passes.

## Sandbox and tooling disclosure

- The installed GitNexus CLI reports the disposable worktree unindexed, and
  graph MCP tools are unavailable. An `npx` fallback attempted a blocked npm
  DNS lookup (`ENOTFOUND registry.npmjs.org`). Direct immutable-diff analysis
  was used; the repair changes YAML/JSON/ledger artifacts, not executable
  symbols.
- An initial `uv run --no-sync` check attempt created an ignored, incomplete
  worktree `.venv`; seven commands then lacked PyYAML. The same eight checks
  all passed using the existing Python 3.13 project interpreter. The tracked
  worktree remained clean.
- Sandbox policy denied one nonessential `ps` diagnostic. Direct web opening
  of the two GitHub issue pages also failed, but their bodies and titles were
  retrieved read-only through the connected GitHub service.
- No remote, PR branch, pull request, or GitHub issue was modified.
