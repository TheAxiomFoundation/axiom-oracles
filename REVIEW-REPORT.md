VERDICT: REQUEST-CHANGES

# Blind adversarial review — `triage/ca-snap-441`

Reviewed exact local branch head
`102b4edd5875fbe5e856daea0fafa9708a37003b` in a detached disposable
worktree. The merge base with the locally cached `origin/main` is
`86be77210aa03da867a6103558cb57fe51a2ba55`.

The claimed arithmetic decomposition is mechanically conserved, and the 20
PolicyEngine gaps pass independent legal and causal review. Approval is blocked
by failed bridge counterfactuals, a non-replayable evidence builder, a
mischaracterized 77-row drift class, and stale case-explorer artifacts.

## Blocking findings

### 1. Two disposed bridge cases fail the required live-PE counterfactual

The largest proof class labels 64 households / 128 rows as corrected-Axiom
self-employment bridge artifacts. Its committed evidence is a hand-coded
Axiom-side forward-gate replay, not a live-PE neutralization.

I tested all 64 against live PolicyEngine 4.18.9 / PolicyEngine-US 1.767.3 /
PolicyEngine-Core 3.30.3:

- 46 close after zeroing annual self-employment;
- seven require zero self-employment and zero TANF;
- five require direct January and zero self-employment;
- four require direct January, zero self-employment, and zero TANF;
- `ecps-59082` and `ecps-62506` do not close under any of those four
  interventions.

`ecps-59082` remains PE false / $0 versus Axiom true / $148.
`ecps-62506` gets no closer than PE true / $345.120321 versus Axiom true /
$454, a $108.879679 miss. Both retain a material generic-disability /
nonelderly-shelter-cap difference. Nevertheless, their four rows are
dispositioned solely as self-employment bridge artifacts.

This violates the review's explicit rule that any case failing its own
counterfactual is blocking. It also shows that 18 of the 64 static cases have
more than the disposition's stated self-employment mechanism: 16 need a second
period/TANF mechanism and two still do not close.

The medical-input and disability-cap classes also replay corrected Axiom
arithmetic against live January PE rather than moving PE toward the committed
Axiom result. Their arithmetic closes, but the direction of proof should be
made explicit if the required standard is strictly PE-side.

### 2. The committed evidence machinery is not replayable at the reviewed head

The retained worker trace has SHA-256
`286d28ac1307e2b44ac53eab9408d0726d9d4fe84576ec423feb6d5be6623992`.
I independently regenerated all 361 households with the unchanged committed
tracer and the target's pre-merge runner; the output was byte-for-byte
identical. Pointing the builder at the original 441-row report and that trace
reconstructs all 345 generated entries.

The committed post-state cannot reproduce that result:

```text
python scripts/build_ca_snap_362_dispositions.py \
  --trace /private/tmp/ca-snap-441-trace-v2.json --check

ValueError: expected 345 new rows, selected 0
```

The builder selects only report rows whose disposition is currently null, so
the already-applied 345 rows are no longer inputs. The tracer has the same
post-state defect: it now selects only 91 households / 96 rows rather than the
original 361 / 441. This directly contradicts the target ledger's claim that
the builder passes an idempotent `--check`.

There is a second head-consistency failure. The target is a merge commit that
contains the requested-month runner fix, but the evidence and report were
generated with its first-parent runner. On the exact target runner:

- annual live SNAP changes in 286 of 361 households;
- requested-month PE values remain identical in all 361;
- only 75 of 361 annual baselines exactly reproduce the stamped report;
- a fresh full trace has SHA-256
  `732801c34800ef8a99791bdba2398633232c17450b71e162207fca2b1c13feba`;
- the builder fails earlier with
  `ValueError: ecps-57065: minor repro baseline drifted`.

The builder validates only runtime versions. It does not pin or validate the
trace SHA, trace schema, report provenance, uniqueness, or Populace artifact.
The tracer overrides certification and loads the default cached Populace
snapshot without verifying its SHA.

### 3. Seventy-four of the 77 “version-drift” rows remain the same mismatch

The retained trace's strict PE-value-change set exactly equals the worker's 77
listed rows, and all 77 remain unannotated. That proves that their PE values
moved from the report stamp; it does not prove that they are version-only
divergences.

I reran all 77 with the exact current target runner and PE-US 1.767.3. Live
values match the retained `requested_month_pe` values 77/77:

- only `ecps-59207`, `ecps-59732`, and `ecps-60346` close within the $7 suite
  tolerance;
- the other 74 remain the same Axiom-higher `amount_difference` class;
- eligibility still matches in all 77.

The worker report does not disclose the 3-close / 74-persist regeneration
outcome. It also describes the requested-month runner fix as pending even
though merge base `86be7721` and the reviewed target already contain it.
Therefore 74 rows do not satisfy the requested definition of drift that
vanishes or changes class on 1.767.3.

### 4. Case-explorer parity fails by 588 annotations

Canonical overview, detail, history, burn-down, scoreboard, and served
disposition JSON reconcile. The served case shards do not:

```text
python scripts/emit_case_artifacts.py --check ca-snap-ecps

case-artifacts FAILED: ca-snap-ecps:
588 served annotation(s) differ from canonical
```

All 588 canonical annotations are absent from the case explorer: 325 new
bridge rows, 20 new upstream rows, and 243 pre-existing BBCE rows. The explorer
therefore presents all 684 mismatches as unexplained while canonical accounting
says 96. The 243 BBCE omissions predate this branch, but the requested
case-explorer parity gate still fails and the branch adds another 345 stale
annotations.

## Stratified counterfactual sample

I used reviewer seed `362441` to choose three cases from each of the nine bridge
proof classes, for 27 random cases, then added targeted `ecps-59082`. Twenty-one
of the random cases do not appear as examples in `WORKER-REPORT.md`; the six
medical/cap cases exhaust their small classes. `SE` means zero
self-employment, `TANF` means zero TANF, and `Jan` means direct requested-month
evaluation. All dollar comparisons use the suite's $7 tolerance.

For medical and shelter-cap rows, `corrected Axiom → Jan PE` accurately states
the branch's Axiom-side proof direction; every other row is a live-PE
counterfactual against committed Axiom.

| Case ID | Proof class | Selection | Result |
| --- | --- | --- | --- |
| `ecps-59123` | corrected-Axiom SE | random | PE zero-SE $39.059753 vs Axiom $35, delta +$4.059753 — PASS |
| `ecps-60638` | corrected-Axiom SE | random | PE zero-SE $549.059814 vs Axiom $546, delta +$3.059814 — PASS |
| `ecps-62506` | corrected-Axiom SE | random | Best PE zero-SE $345.120321 vs Axiom $454, delta −$108.879679 — **FAIL** |
| `ecps-56950` | live SE | random | PE $299.669983 vs Axiom $298, delta +$1.669983 — PASS |
| `ecps-59173` | live SE | random | PE $426.734823 vs Axiom $421, delta +$5.734823 — PASS |
| `ecps-61485` | live SE | random | PE $241.394979 vs Axiom $238, delta +$3.394979 — PASS |
| `ecps-59012` | live TANF | random | PE $419.309774 vs Axiom $414, delta +$5.309774 — PASS |
| `ecps-59667` | live TANF | random | PE false / $0 vs Axiom false / $0 — PASS |
| `ecps-60690` | live TANF | random | PE $299.669983 vs Axiom $298, delta +$1.669983 — PASS |
| `ecps-57078` | live SE + TANF | random | PE false / $0 vs Axiom false / $0 — PASS |
| `ecps-57341` | live SE + TANF | random | PE $549.059814 vs Axiom $546, delta +$3.059814 — PASS |
| `ecps-61315` | live SE + TANF | random | PE $1,189.629395 vs Axiom $1,183, delta +$6.629395 — PASS |
| `ecps-59102` | direct January | random | PE $1,205.300049 vs Axiom $1,204, delta +$1.300049 — PASS |
| `ecps-60766` | direct January | random | PE $1,571 vs Axiom $1,571 — PASS |
| `ecps-61635` | direct January | random | PE $610 vs Axiom $609, delta +$1 — PASS |
| `ecps-58272` | January + TANF | random | PE $1,231.400024 vs Axiom $1,230, delta +$1.400024 — PASS |
| `ecps-60555` | January + TANF | random | PE $906.700012 vs Axiom $906, delta +$0.700012 — PASS |
| `ecps-62759` | January + TANF | random | PE $724 vs Axiom $723, delta +$1 — PASS |
| `ecps-57027` | January + SE + TANF | random | PE $1,571 vs Axiom $1,571 — PASS |
| `ecps-58088` | January + SE + TANF | random | PE $688.299988 vs Axiom $687, delta +$1.299988 — PASS |
| `ecps-60409` | January + SE + TANF | random | PE $1,196.900024 vs Axiom $1,196, delta +$0.900024 — PASS |
| `ecps-57453` | missing medical input | random | Corrected Axiom $298 vs Jan PE $298 — PASS |
| `ecps-59914` | missing medical input | random | Corrected Axiom $298 vs Jan PE $298 — PASS |
| `ecps-59967` | missing medical input | random | Corrected Axiom $219 vs Jan PE $219.399994, delta −$0.399994 — PASS |
| `ecps-58732` | disability / shelter cap | random | Corrected Axiom $190 vs Jan PE $190.599976, delta −$0.599976 — PASS |
| `ecps-61918` | disability / shelter cap | random | Corrected Axiom $136 vs Jan PE $137, delta −$1 — PASS |
| `ecps-61953` | disability / shelter cap + SE | random | Corrected Axiom $211 vs Jan PE $212.099976, delta −$1.099976 — PASS |
| `ecps-59082` | corrected-Axiom SE | targeted | Annual/Jan zero-SE ± TANF all leave PE false / $0 vs Axiom true / $148 — **FAIL** |

Random sample result: 26 pass, one fails. Including the targeted case: 26 pass,
two fail.

## PolicyEngine-gap audit: all 20 rows pass

The 20 upstream rows are ten cases × eligibility and benefit, all linked to
PolicyEngine-US #9157. Every live PE 1.767.3 baseline sets
`snap_excluded_child_earner=true`, counts zero SNAP earned income, and returns
eligible with a positive benefit. Changing only the erroneous exclusion makes
PE count the wages and return ineligible / $0.

| Case ID | Ages | Stamped Axiom vs PE | Live PE 1.767.3 | Minimal corrected result |
| --- | --- | --- | --- | --- |
| `ecps-57065` | 17, 16 | false/$0 vs true/$412.335 | true/$407.70; both earners excluded | Count $36,171.25/month → false/$0 |
| `ecps-57392` | 14 | false/$0 vs true/$299.670 | true/$298 | Count $18,085.63/month → false/$0 |
| `ecps-58015` | 17 | false/$0 vs true/$299.670 | true/$298 | Count $18,085.63/month → false/$0 |
| `ecps-58260` | 17 | false/$0 vs true/$299.670 | true/$298 | Count $18,085.63/month → false/$0 |
| `ecps-59775` | 16 | false/$0 vs true/$299.670 | true/$298 | Count $18,085.63/month → false/$0 |
| `ecps-60204` | 17 | false/$0 vs true/$299.670 | true/$298 | Count $18,085.63/month → false/$0 |
| `ecps-60550` | 15 | false/$0 vs true/$299.670 | true/$298 | Count $7,653.17/month → false/$0 |
| `ecps-60573` | 16 | false/$0 vs true/$23.974 | true/$23.84 | Count $18,085.63/month → false/$0 |
| `ecps-62068` | 15 | false/$0 vs true/$299.670 | true/$298 | Count $18,085.63/month → false/$0 |
| `ecps-62315` | 16 | false/$0 vs true/$299.670 | true/$298 | Count $18,085.63/month → false/$0 |

I checked retained [7 CFR § 273.9](https://www.ecfr.gov/current/title-7/subtitle-B/chapter-II/subchapter-C/part-273/section-273.9)
(b), (b)(1)(i), and (c)(7) text for all ten cases, exceeding the requested
five. Wages are earned income. The minor-student exclusion additionally
requires residence with a natural, adoptive, or stepparent, or parental
control by another household member. PE-US 1.767.3 tests K–12 status and age
at most 17 but omits that relationship/control condition. The retained
self-contained corpus artifact has SHA-256
`de25d2b32f261e92405a553f65dfc90b47b032a4d1a80b1b585857b7fd342d1e`,
at
`/Users/maxghenis/TheAxiomFoundation/axiom-corpus/data/corpus/provisions/us/regulation/2026-05-10-snap-7-cfr-273-r2026-07-15-self-contained.jsonl`;
the RuleSpec pin is
`ca2d424fcb85ce8c3a8f4706113331710f114460`.

`ecps-57065` has no retained genuine parental-control relationship; the
loader's `Child` label is synthetic. At least one minor's wages must still be
counted, and either wage alone exceeds the limit, so this nuance does not
change the attribution.

## Conservation, unresolved queue, and accounting

All requested conservation checks pass:

- 325 bridge + 20 PE gaps + 77 drift + 19 unresolved = 441;
- the four row sets are pairwise disjoint;
- household sets are also disjoint: 260 bridge, 10 PE-gap, 77 drift, and 14
  unresolved = 361;
- all 345 new YAML selectors are unique and inside the original 441;
- no case outside the original 441 gained a disposition;
- the original four BBCE selectors expand to 243 rows and are byte-identical;
- canonical raw mismatch identities and values are unchanged;
- all 19 unresolved rows remain unannotated across 14 households;
- the worker report records the unsuccessful/confounded annual, January,
  self-employment, TANF, and joint probes for those unresolved households;
- canonical remaining queue is 96 rows: 91 benefit and five
  `eligibility_left_only`, across 91 households;
- CA accounting is exactly 96 unexplained, 243 Axiom-attributed, 20 upstream,
  and 325 bridge;
- global `axiom_attributed_open` remains 243.

## Script audit

Both committed scripts were read in full.

- All proof classes are manually enumerated ID sets. They are not assigned by
  regex or report-value pattern alone.
- Most classes have case-specific baseline, source-alignment, and closure
  checks. The 188 trace-derived bridge rows run live per-case closure checks.
- The 128 static self-employment rows run only a hand-coded Axiom forward-gate
  replay; they do not run the required live-PE neutralization.
- The 20 PE-gap rows check baseline, ages, wages, zero PE SNAP earned income,
  and source alignment, but the builder does not execute its corrective
  minimal counterfactual. The independent audit above supplied it.
- The claimed fail-closed deduction-confound control is only a hard-coded
  three-case exclusion. There is no per-case deduction-stack comparison over
  the 188 trace-derived bridge rows.
- Period classes require January closure but do not assert that period is the
  isolated changed input.
- Twelve joint TANF cases may use a weaker “positive TANF after zero-SE”
  fallback rather than full TANF source alignment.
- The post-state selection and provenance weaknesses described above prevent
  the scripts from serving as durable committed evidence machinery.

## Scope, parity, gates, and tests

The target diff contains exactly 13 expected files: the ledger, two scripts,
CA SNAP disposition/report artifacts, shared regenerated overview/detail/
history/burn-down/scoreboard artifacts, and served disposition JSON.
`git diff --check` passes.

Passing checks:

- `apply_dispositions.py --check`;
- grids and boundary suggestions;
- affected-map and vacuous-gate generation;
- overview, scoreboard, ratchet, and burn-down;
- served disposition JSON parity;
- focused tests: `303 passed, 2 skipped in 53.58s`.

Failing checks:

- `build_ca_snap_362_dispositions.py --check`;
- `emit_case_artifacts.py --check ca-snap-ecps`.

`generate_conformance_universe.py --all --check` exited successfully, but
explicitly no-op'd US-PE because the available general checkout was 1.779.4,
not pinned 1.767.3. All live counterfactuals and 77-row reruns used the exact
cached 1.767.3 runtime.

## Environment and write controls

- Source `WORKER-REPORT.md` was read from
  `/Users/maxghenis/TheAxiomFoundation/axiom-oracles/_worktrees/ca-snap-441/`
  and left untouched.
- The source worktree, target branch, remotes, GitHub, and PR state were not
  modified.
- Review-only commits and this report live on the detached review worktree
  under `.git/review-worktrees/`.
- `uv run --offline` could not initialize `~/.cache/uv` because of sandbox
  permissions. The global Python shim was also broken. I used the existing
  read-only cached exact-version environment instead.
- GitNexus reported the review worktree unindexed and its graph helpers were
  unavailable, so repository-native diff, source, and chain analysis was used.
- No network or remote write was attempted.

## Required remediation before approval

1. Remove or strengthen the four dispositions for `ecps-59082` and
   `ecps-62506`; rerun live PE counterfactuals and capture every required
   mechanism for the other 16 multi-mechanism static cases.
2. Make the tracer and builder replayable from the committed post-state, pin
   trace/report/dataset provenance, and regenerate evidence with the exact
   target runner.
3. Reclassify or accurately document the 74 rows that remain the same mismatch
   on 1.767.3; state the exact regeneration outcome.
4. Regenerate the CA SNAP case shards so served annotations reconcile with
   canonical accounting.
