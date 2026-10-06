Hardens certification evidence for the 2026-09-24 adversarial review (slice s3), including the independent REQUEST_CHANGES review of `3568df45e`. The original comparison base is `5f038b8f5`; the fix round reuses the independent review’s probes and records their before/after results.

| Finding | Before | After |
|---|---|---|
| `ca-federal-schedule-tax-spsm` declares 97 unexplained mismatches (inline producer classification, concept-less rows) | The unexplained ratchet and dashboard assessment read **0** against ceiling 0; a mutant declaring 5000 also read 0 | Gate reads **97** and the 5000 mutant reads **5000**. The ceiling moves 0 → 97 as a documented correction, and the dashboard assessment is 97; no hero renders this total |
| Scoreboard, ratchet and certify each defined "unexplained" differently (3 of 222 gated suites disagreed) | 3 divergent suites | **0 divergent**: one shared assessment, plus Python/JS parity |
| de/kindergeld skipped the closed/executable commit binding | A forged executable commit (`"6"*40`) certified **yes** | **no**, with a commit blocker. Bindings now apply on every computed route pair |
| nz/income-tax `exercised=true` although no oracle case exceeds the 180000 top-bracket threshold (max 78214.29) | exercised **true** | exercised **false**, with a blocker naming the threshold |
| `apply_dispositions` clamped junk counts to 0 (latent) | `summary.get(...) or 0`, `max(..., 0)` | Junk counts raise; classified > mismatches raises |

## What changed

**One unexplained definition** (`axiom_oracles/conformance/unexplained.py`). The unexplained ratchet, the conformance scoreboard and the certificate legs all call it. `dashboard/src/utils/unexplained.js` mirrors it, and the loader now counts reports before concept filtering. `OraclesV2.jsx` computes `totals.unexplained`, but no rendered element uses it; this PR does not add such a display. The certificate legs keep their stricter admission as defects (inline classifications and known-cause-only explanations are not certifiable) rather than as a different number. Sibling holes closed in the same gates:
- the ratchet fails on unparseable reports instead of skipping them;
- a suite is exempted as diagnostic only through the shared parsed `diagnostic-suites.json` source imported by `suites.js`, not its name;
- a pinned suite that vanishes fails the check;
- duplicate suites resolve to the maximum count, independent of order;
- the scoreboard treats a non-finite exposure as invalidating an exclusion and a contested suite as uncovered.

The fix round also rejects impossible over-classification and integers above 2**53-1 in both runtimes, constrains inconsistent mismatch totals by comparisons minus matches, and floors unexplained counts at explicitly unexplained rows. Summary-only reports enter the gate (measurement found zero new committed reports). Report-carried JavaScript assessment fields are not trusted as loader-owned calculations.

The SPSM producer now labels its rows with the concept and keeps `counts.unexplained == unexplained_count`. SPSM cannot be rerun here: the licensed install and extract are not on this machine. The committed report therefore stays as it is, and the gate reads it as 97.

**Bindings on every route pair** (`scripts/certify.py`, `axiom_oracles/provenance.py`). Premise dispatch goes through the `CLOSED_ROUTES` / `EXECUTABLE_ROUTES` registries, whose selectors are mutually exclusive. One central check runs whenever both emitted premises are computed:
- a single `GIT_SHA`-shaped rulespec commit on both sides (DE compares the closure commit with the signed RuleSpec checkout commit);
- equal program sets when either side carries one;
- strict JSON/YAML admission for every premise artifact (enforced by an AST test).

`GIT_SHA` is now defined once. Three producers had accepted digit-only commits. The fix round rejects empty program sets, moves strict YAML admission to the shared evidence module, and extends strict loading to the certification producers. Merge keys are forbidden, strict report parse errors become leg defects, and the DE executable flag cannot suppress missing-leg or census blockers.

**Threshold straddling** (`scripts/threshold_straddle.py`). The check runs over the committed, sha-bound NZ compiled program IR:
- it interprets the IR exactly and first reproduces every recorded requested output (883 evaluations, 2459 outputs);
- it finds each min/max/ordering site where a parameter-dependent, input-free threshold meets an input-dependent quantity;
- it counts only live-path observations. Min/max pairs require strictly below and above; ordered comparisons require the operator’s false and true outcomes, assigning equality accordingly. A typed exemption ledger records legally unreachable missing sides as decisions, never observations; stale entries fail.

Trace replay is cached within a process by IR and trace-content hashes, across views and repeated passes, while byte bindings are checked again. Equal version dates choose the last version, duplicate derived IDs fail, and the DE parameter proof allowlists accepted keys.

Routes without committed IR cannot claim exercised; the DK attempt checkpoint records matching composed-source hashes, an unavailable pinned binary, and rejection of overlapping version dates by the available compiler. It records no successful compiled-IR byte comparison. DE Kindergeld is proved to reach zero sites from its signed, parameter-only module bytes. CERTIFIED.md gains v4.

## Certificate deltas relative to the original base (regenerated; no certified state changes)

| Certificate | exercised | Blockers |
|---|---|---|
| nz/income-tax | true → false | + unobserved side above the 180000 top bracket |
| nz/acc-earners-levy | true → false | + maximum earnings 156641 never exceeded |
| nz/accommodation-supplement | true → true | zero parameter-only threshold sites after refinement; fix round restores exercised from false to true |
| nz/independent-earner-tax-credit | true → false | + no below-12 observation; above-12 side is legally unreachable and explicitly exempted |
| nz/main-benefits | true → false | + 4 unstraddled sites after refinement |
| nz/working-for-families | true → false | + 5 unstraddled sites after refinement |
| nz/winter-energy-payment | true (0 sites) | unchanged |
| dk/boerne-og-ungeydelse | true → false | + no committed IR |
| us/tariff-duty | true → false | + no committed IR (101 × 1.6 MB compiled programs are not committed) |
| de/kindergeld | true (0 sites, proved) | unchanged |
| de/rv-employee-contribution, de/unterhaltsvorschuss | false | + no-executable-commit binding blocker, + straddle unavailable |
| us-co/snap | false (attested) | incomplete-census blocker reworded; a separate straddle-unavailable blocker added |

Every state stays `no` (us-co/snap stays `unavailable`). These verdicts are public (certificates feed the site), so merging is Max's call.

## Invariants (tested)

Unexplained assessment (`tests/test_unexplained_definition.py`, Hypothesis plus examples):
1. The count preserves admitted declared unexplained signals and explicitly unexplained rows. With consistent classifications, file/inline modes preserve mismatches minus classifications; none mode preserves mismatches minus admitted known-cause coverage. Classified counts above mismatches are hard defects and retain at least max(mismatches, declared).
2. A bool, negative, non-integral, non-finite, string, or integer above 2**53-1 is a hard defect. Admitted scalar counts are integers in 0..2**53-1.
3. Known causes reduce only listed, undispositioned rows with non-empty string concepts, in none mode.
4. Resolution is independent of report order. Raising an admitted unexplained declaration cannot lower the count. Removing an explanation cannot lower it within a fixed mode with otherwise consistent counts. Removing the last inline classification can switch to none mode and activate known causes: M=5, C=1, K=5 changes 4 to 0. Properties include known causes and explicitly test this transition.
5. Scoreboard, ratchet and certify-leg counts agree on every committed gated report (222). Python and JS agree on report arithmetic and gate membership (differential test with independently loaded diagnostic sets). JavaScript cannot validate dispositions files: file-mode gate counts agree when the cited file is valid; Python rejects invalid files and fails closed.

Bindings (`tests/test_certify_route_bindings.py`, exhaustive over the finite route space derived from the registries, plus a Hypothesis property over commit-string shapes):

6. Exactly one route selects each spec per premise, across all 256 dispatch-flag subsets.
7. For all 24 route pairs and all 13 programs, a certificate with computed/computed premises is `yes` only if both commits are equal `GIT_SHA` strings, and program sets match when either side carries one. Unequal, digit-only, uppercase, int, None and missing commits each block.
8. Covered certification producer readers use shared strict admission (an AST scan of certify and its producer modules). Non-finite JSON/YAML numbers, duplicate keys, and YAML merge keys are rejected.

Straddle (`tests/test_threshold_straddle.py`, Hypothesis plus examples):

9. The interpreter reproduces every recorded requested output exactly, or exercised is false.
10. exercised=true requires every reachable parameter-threshold site to have both observed sides or a validated legal exemption for each missing side. For comparisons below=false and above=true (at=0); min/max retain strict numeric below/at/above. Adding valid evaluations cannot remove an observed side; the verdict is permutation-invariant; below + at + above = live observations. Exemptions never alter observed counts.

## Verification

The final fix-round report records targeted test and gate results, local platform limits, generated-artifact deltas, and refresh timing. Certificates use the supplied local harness, which preloads the committed Linux DE census/status. The dispatcher runs the full suite and network-dependent dashboard build.

The review also identified slim reports without a source pointer (`fiit-ecps`, `ssi-ecps`); that evidence-format repair is outside this fix round.


