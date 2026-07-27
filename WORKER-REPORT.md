# SNAP residual integration worker report

Date: 2026-07-27 UTC  
Branch: `fed-parity/snap-residual-cleanup`  
Starting commit: `105b7133`

## Outcome

The AL, MA, NC, SC, and TN SNAP Enhanced CPS suites were regenerated locally
with their existing `axiom-oracles-compare` configurations and a single
PolicyEngine-US version, 1.767.3. The final reports contain 656 raw mismatch
rows, of which 324 rows across 239 households remain unexplained.

Only evidence-backed classifications were added:

- all 10 staged lone-minor entries survived regeneration and classify 24 rows
  across 12 households against
  [PolicyEngine-US #9157](https://github.com/PolicyEngine/policyengine-us/issues/9157);
- exact-household live TANF counterfactuals passed for 95 of 121 candidates,
  and only those 95 benefit rows are classified `bridge_artifact` against
  [axiom-oracles #397](https://github.com/TheAxiomFoundation/axiom-oracles/issues/397);
- no regenerated mismatch qualified for the joint minimum-allotment
  rounding/month-averaging classification under
  [PolicyEngine-US #9158](https://github.com/PolicyEngine/policyengine-us/issues/9158)
  and
  [axiom-oracles #399](https://github.com/TheAxiomFoundation/axiom-oracles/issues/399);
- all 69 requested MA/SC categorical-only candidates, comprising 138 mismatch
  rows, are physically unannotated and remain unexplained pending state-law
  validation.

The runner's month-averaging behavior was not changed.

## Before and after

Counts are mismatch rows. Parenthesized values are distinct unexplained
households. “Before” is the committed state at `105b7133`; “after” is the
final regenerated and dispositioned report.

| State | Before raw | Before unexplained | Regenerated raw | After unexplained | Unexplained change |
| --- | ---: | ---: | ---: | ---: | ---: |
| AL | 53 | 43 (38) | 53 | 23 (21) | -20 |
| MA | 255 | 49 (47) | 255 | 83 (55) | +34 |
| NC | 99 | 88 (82) | 99 | 71 (68) | -17 |
| SC | 180 | 54 (49) | 181 | 106 (61) | +52 |
| TN | 68 | 68 (59) | 68 | 41 (34) | -27 |
| **Total** | **655** | **302 (275)** | **656** | **324 (239)** | **+22** |

MA and SC rise because 138 categorical-only rows that had previously been
classified as broad-based categorical eligibility encoding gaps were
deliberately returned to the unexplained pool. SC also gained one regenerated
raw benefit mismatch, `ecps-29277`; its exact TANF counterfactual passed and it
is one of SC's 29 bridge artifacts.

## Generation and provenance

All five suite configurations retained `sample_size: 0`, period `2026-01`,
population `enhanced-cps`, and their existing jurisdiction FIPS filters. They
ran through `scripts/run_comparison.py` and the general
`axiom-oracles-compare` runner that produced the committed reports.

| Component | Version or identity |
| --- | --- |
| PolicyEngine | 4.18.9 |
| PolicyEngine-US | 1.767.3 |
| PolicyEngine-Core | 3.28.0 |
| Axiom rules engine | 0.1.0, commit `48797e101c093bb388be718c6f5d8fc9d9f94a7d` |
| RuleSpec-US | commit `ca2d424fcb85ce8c3a8f4706113331710f114460` |

Each dashboard report records all four engine versions under `engines.versions`
and retains the schema-required `engines.left` and `engines.right` values:

- [AL report](dashboard/public/data/axiom-policyengine-al-snap-ecps.json)
- [MA report](dashboard/public/data/axiom-policyengine-ma-snap-ecps.json)
- [NC report](dashboard/public/data/axiom-policyengine-nc-snap-ecps.json)
- [SC report](dashboard/public/data/axiom-policyengine-sc-snap-ecps.json)
- [TN report](dashboard/public/data/axiom-policyengine-tn-snap-ecps.json)

Generation used the locally cached PolicyEngine wheel and Populace data
offline. CI remains verification-only and does not generate these suites.

## Dispositions applied

The counts below are newly applied by this task. Existing, unrelated
state-encoding dispositions were left in place except for the 69 categorical
households explicitly returned to unexplained.

| Class | AL households/rows | MA | NC | SC | TN | Total households/rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Lone-minor, #9157 | 4/8 | 1/2 | 3/6 | 2/4 | 2/4 | 12/24 |
| TANF bridge, #397 | 14/14 | 18/18 | 11/11 | 29/29 | 23/23 | 95/95 |
| Minimum benefit, #9158 + #399 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| Categorical-only, deliberately not dispositioned | 0/0 | 27/54 | 0/0 | 42/84 | 0/0 | 69/138 |

### Lone-minor class

Every staged selector was still live after regeneration. The 10 entries cover
benefit and eligibility rows for 12 exact households. AL `ecps-36459` had
previously overlapped an existing categorical selector, so moving its two rows
to the correct #9157 class means the 24 classified rows reduce the unexplained
count by 22 rather than 24.

The committed source-linked entries are in:

- [AL dispositions](dispositions/al-snap-ecps.yaml)
- [MA dispositions](dispositions/ma-snap-ecps.yaml)
- [NC dispositions](dispositions/nc-snap-ecps.yaml)
- [SC dispositions](dispositions/sc-snap-ecps.yaml)
- [TN dispositions](dispositions/tn-snap-ecps.yaml)

### TANF bridge counterfactual

For every benefit-only candidate with positive endogenous TANF, the exact
Populace household was loaded into a live PolicyEngine-US 1.767.3 simulation.
The regenerated baseline was reproduced first. The state TANF component
(`al_tanf`, `ma_tafdc`, `nc_tanf`, `sc_tanf`, or `tn_ff`) and aggregate
`tanf` were then both forced to zero. A case passed only when:

1. the baseline state component equaled aggregate TANF;
2. SNAP eligibility was true before and after neutralization; and
3. the zero-TANF SNAP amount landed within the suite's strict $7 tolerance of
   Axiom.

| State | Candidates | Pass | Fail |
| --- | ---: | ---: | ---: |
| AL | 16 | 14 | 2 |
| MA | 23 | 18 | 5 |
| NC | 13 | 11 | 2 |
| SC | 38 | 29 | 9 |
| TN | 31 | 23 | 8 |
| **Total** | **121** | **95** | **26** |

The full live evidence artifact had SHA-256
`084db4c17c97c3ab6ed057186b5c6df969737944013069361125499674497f66`.
Its passing values are preserved in the 95 committed disposition entries:
each entry contains the exact Axiom amount, baseline PE amount, monthly TANF,
zero-TANF amount, eligibility result, tolerance arithmetic, source links, and
pinned mismatch values. An independent read-only audit found no missing,
extra, duplicate, or fail-case entry.

The 26 failures remain unexplained because neutralizing TANF did not land
within tolerance:

- AL: `ecps-37187`, `ecps-37415`
- MA: `ecps-2680`, `ecps-2778`, `ecps-3141`, `ecps-3235`, `ecps-3307`
- NC: `ecps-28003`, `ecps-28066`
- SC: `ecps-28773`, `ecps-28997`, `ecps-29028`, `ecps-29094`,
  `ecps-29175`, `ecps-29298`, `ecps-29397`, `ecps-29465`, `ecps-29754`
- TN: `ecps-35304`, `ecps-35647`, `ecps-35696`, `ecps-35835`,
  `ecps-35911`, `ecps-36061`, `ecps-36247`, `ecps-36303`

The strict near-misses were retained: NC `ecps-28066` was $7.04549 from
Axiom and TN `ecps-36247` was $7.19539 from Axiom after neutralization.

### Minimum-benefit screen

No residual reproduced the required $24 versus $23.84/$23.9736 arithmetic
while both engines agreed on eligibility. The six shared-eligibility rows
with one amount at $24 or $23.973597 were:

| State/case | Axiom | PolicyEngine | Result |
| --- | ---: | ---: | --- |
| MA `ecps-2070` | 24.00 | 44.294978 | Not the rounding/averaging delta |
| NC `ecps-27289` | 24.00 | 63.494980 | Not the rounding/averaging delta |
| NC `ecps-27882` | 24.00 | 6.093599 | Not the rounding/averaging delta |
| NC `ecps-27513` | 76.00 | 23.973597 | Axiom is not the $24 minimum |
| NC `ecps-28338` | 151.00 | 23.973597 | Axiom is not the $24 minimum |
| SC `ecps-28997` | 45.00 | 23.973597 | Axiom is not the $24 minimum; TANF counterfactual also failed |

NC `ecps-27653` and TN `ecps-35997` have Axiom $24 versus PE $0, but they
also have eligibility-left-only mismatches and therefore fail the
shared-eligibility condition. No #9158/#399 disposition was applied.

## Remaining unexplained classification

This table is exhaustive and mutually exclusive. Each cell is
`households / mismatch rows`. “Left” means Axiom and “right” means
PolicyEngine.

| Classification | AL | MA | NC | SC | TN | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Tracked categorical-only candidates | 0/0 | 27/54 | 0/0 | 42/84 | 0/0 | 69/138 |
| TANF present, but zero-TANF counterfactual failed | 2/2 | 5/5 | 2/2 | 9/9 | 8/8 | 26/26 |
| Other benefit-only; eligibility output agrees | 17/17 | 21/21 | 58/58 | 6/6 | 16/16 | 118/118 |
| Benefit plus eligibility-left-only | 1/2 | 1/2 | 3/6 | 0/0 | 6/12 | 11/22 |
| Benefit plus eligibility-right-only | 1/2 | 0/0 | 0/0 | 3/6 | 1/2 | 5/10 |
| Eligibility-left-only, no benefit residual | 0/0 | 0/0 | 5/5 | 0/0 | 0/0 | 5/5 |
| Eligibility-right-only, no benefit residual | 0/0 | 1/1 | 0/0 | 1/1 | 3/3 | 5/5 |
| **Total** | **21/23** | **55/83** | **68/71** | **61/106** | **34/41** | **239/324** |

An independent read-only reconciliation reproduced every category, state
subtotal, and the 239-household/324-row grand total. It also confirmed that
no unresolved household has a dispositioned companion mismatch.

The small non-categorical eligibility groups are:

- benefit plus eligibility-left-only: AL `ecps-73185`; MA `ecps-75035`;
  NC `ecps-27653`, `ecps-28339`, `ecps-66350`; TN `ecps-35306`,
  `ecps-35997`, `ecps-36256`, `ecps-36374`, `ecps-67898`, `ecps-70724`;
- benefit plus eligibility-right-only: AL `ecps-37198`; SC `ecps-28690`,
  `ecps-29141`, `ecps-29647`; TN `ecps-36308`;
- eligibility-left-only without a benefit residual: NC `ecps-27222`,
  `ecps-27250`, `ecps-27256`, `ecps-27574`, `ecps-28309`;
- eligibility-right-only without a benefit residual: MA `ecps-2986`;
  SC `ecps-28726`; TN `ecps-35744`, `ecps-35845`, `ecps-35971`.

The remaining 118 benefit-only households have no evidence-backed shared
mechanism yet. They remain unannotated rather than being inferred into one of
the filed classes.

## PR body text — tracked categorical candidates

### Tracked candidates: categorical-only SNAP eligibility

These 69 households remain unexplained and have no disposition. Each has both
a benefit and eligibility mismatch, for 138 rows total. State-law validation
of the categorical eligibility mechanism is a follow-up; this branch does not
assert an Axiom or PolicyEngine defect.

MA (27):

`ecps-1984`, `ecps-1985`, `ecps-2008`, `ecps-2106`, `ecps-2221`,
`ecps-2227`, `ecps-2251`, `ecps-2305`, `ecps-2316`, `ecps-2343`,
`ecps-2577`, `ecps-2645`, `ecps-2689`, `ecps-2714`, `ecps-2733`,
`ecps-2846`, `ecps-2877`, `ecps-2942`, `ecps-2947`, `ecps-3010`,
`ecps-3033`, `ecps-3036`, `ecps-3121`, `ecps-3239`, `ecps-3241`,
`ecps-3338`, `ecps-3359`.

SC (42):

`ecps-28671`, `ecps-28714`, `ecps-28745`, `ecps-28748`, `ecps-28756`,
`ecps-28757`, `ecps-28764`, `ecps-28798`, `ecps-28815`, `ecps-28833`,
`ecps-28836`, `ecps-28837`, `ecps-28852`, `ecps-28903`, `ecps-28909`,
`ecps-28943`, `ecps-28961`, `ecps-29026`, `ecps-29055`, `ecps-29067`,
`ecps-29074`, `ecps-29107`, `ecps-29147`, `ecps-29249`, `ecps-29267`,
`ecps-29330`, `ecps-29346`, `ecps-29347`, `ecps-29354`, `ecps-29365`,
`ecps-29370`, `ecps-29404`, `ecps-29406`, `ecps-29429`, `ecps-29502`,
`ecps-29514`, `ecps-29526`, `ecps-29534`, `ecps-29561`, `ecps-29611`,
`ecps-29640`, `ecps-29695`.

An exhaustive report audit confirmed that all 138 of these mismatch rows lack
a `disposition` annotation.

## Committed generated chain

The complete requested chain ran in this order:

1. `scripts/apply_dispositions.py`
2. `scripts/extract_grids.py`
3. `scripts/generate_affected_map.py`
4. `scripts/check_vacuous_gate.py`
5. `scripts/conformance_scoreboard.py --snapshot --date 2026-07-27`
6. `scripts/conformance_ratchet.py`
7. `scripts/conformance_burndown.py`

Every script's supported `--check` invocation passed:

- dispositions: 83 files validated and committed dashboard data consistent;
- grids: up to date;
- affected map: 162 suites and 171 suite-repository edges;
- vacuous gate: 136 oracle-backed configs, 212 suites, 23 executable
  surfaces;
- scoreboard: 4 jurisdictions, 3 conformant;
- ratchet: 4 jurisdictions, no invariant regression;
- burndown: 4 series, 49 points.

The dated scoreboard snapshot already matched, so the writer reported zero
history snapshot files updated. The ratchet writer made no numeric change; its
unrelated inline history comments were preserved after serialization.

The `us-pe:snap` row still registers `ca-snap-ecps`. Only its note now records
the final AL/MA/NC/SC/TN unexplained counts, and the generated US-PE detail
copies reflect that text.

## Scope and local commits

No state conformance row owned by another lane changed. Relative to
`105b7133`, the intended tracked changes are limited to:

- `PROGRESS.md` and this worker report;
- the five SNAP dashboard reports;
- the five SNAP disposition files;
- the `us-pe:snap` note;
- generated US-PE detail and freshness data.

Logical commits before this report:

- `a9b9a66d` — start the committed progress log;
- `78eba425` — regenerate five suites on PolicyEngine-US 1.767.3;
- `8e219599` — apply the lone-minor #9157 class;
- `3f021c27` — return categorical-only candidates to unexplained;
- `37ece521` — apply the per-case TANF bridge #397 class;
- `5ff80113` — regenerate clean row-level annotations against final selectors;
- `955e7385` — update the SNAP row note and regenerate the conformance chain.

Nothing was pushed, and no GitHub write was made.

## Sandbox and tooling disclosures

- The sandbox denied `uv` cache initialization under
  `/Users/maxghenis/.cache/uv` at `sdists-v9/.git`. Generation therefore used
  the exact cached PolicyEngine-US 1.767.3 environment read-only through a
  temporary local `uv` shim while retaining the repository's normal
  `scripts/run_comparison.py` machinery.
- A diagnostic `ps` listing was denied with `operation not permitted` during
  the long regeneration. Bounded runner polling, report timestamps, exit
  status, and the subsequent checks confirmed successful completion.
- A helper's exploratory `py_compile` cache write outside the worktree was
  denied; it was not needed for generation or validation and produced no
  tracked change.
- GitNexus graph tools were unavailable for this worktree, so runner tracing
  used the repository's configurations and source directly.
