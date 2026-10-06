# Fresh bounded endpoint diagnostics

Both rulespec variants were freshly evaluated on the same 2,438 selected
endpoint cases using the unchanged current campaign case feed, query plan,
comparison functions, selectors and `AxiomRulesRunner`. This is a bounded
diagnostic cohort, not a full-schedule campaign or a classification receipt.
No counts below are extrapolated to the full schedule. Official preview
selector population validation was not performed by the diagnostic helpers.

| Metric | A: 96d5e7c | B: c626450 |
|---|---:|---:|
| Endpoint cases | 2,438 | 2,438 |
| Comparisons | 28,122 | 28,122 |
| Matches | 24,268 | 25,504 |
| Mismatches | 3,854 | 2,618 |
| Unexplained Brazil components | 390 | 6 |
| Unexplained note 52 components | 762 | 80 |
| Unexplained totals | 956 | 82 |
| All unexplained units | 2,108 | 168 |
| Axiom-attributed-open components | 0 | 83 |
| Engine errors | 0 | 0 |
| Cohort satisfies zero unexplained and zero open | No | No |

The selected case counts are CH62 640, CH84 800, CH29 800 and CH94 198.
CH94 is restricted to HTS10 `9403999020`. All 168 unexplained B units are on
that line. Its B flags remain false for Brazil and note 52 while the steel
and Section 232 covered flags are true. Samples include BR 2026-07-22
Brazil actual 0 versus Yale 0.25, and MX 2026-07-24 note 52 actual 0 versus
Yale 0.10. The paired diagnostic observed no A/B output change in CH94.

The B open-unit census is `cafta-52i-deferred` 5,
`section232-annex-brazil` 33, `section232-annex-forced-labor` 35,
`section232-heading-brazil` 2 and `section232-heading-forced-labor` 8.
The former is in CH62; the latter four are in CH84.

| Paired transition | Brazil | Note 52 | Total | All |
|---|---:|---:|---:|---:|
| Mismatch to match | 293 | 534 | 567 | 1,394 |
| Match to mismatch | 61 | 70 | 27 | 158 |
| Retained mismatch, changed actual | 91 | 148 | 367 | 606 |

All newly mismatching component and total rows have positive candidate
deltas. Examples from the paired output:

| HTS10 | Origin/date | Slot | A | B | Yale |
|---|---|---|---:|---:|---:|
| 2933492600 | BR / 2026-08-01 | Brazil | 0 | 0.25 | 0 |
| 2933492600 | BR / 2026-08-01 | Note 52 | 0 | 0.125 | 0 |
| 6203331040 | CR / 2026-08-01 | Note 52 | 0 | 0.125 | 0 |
| 8422409160 | BR / 2026-07-30 | Brazil | 0 | 0.25 | 0 |
| 8407344400 | RU / 2026-07-30 | Note 52 | 0 | 0.125 | 0 |

## Selection and provenance

`run_targeted_probe.py select` streamed all 9,913,304 selected CSV rows once.
Eligible endpoint dates start 2026-07-22. Strata combine chapter, nonzero
versus zero Yale Brazil/note 52 rates, origin group BR/CA-MX/column-2/other,
and July 22-23 versus July 24 onward. Each stratum retains the 64 lowest
SHA-256 ranks of `bounded-yale-probe-v1|<campaign case_id>`; round-robin
selection caps each chapter at 800 cases. The exact criteria, eligible
populations, chosen records and source hashes are in `targeted-selection.json`.

B was evaluated before A. Each evaluation used one engine process at a
time; all selected cases were freshly evaluated. The diagnostic manifests
use `measurement.bounded_endpoint_eval_manifest.v1`, not the official
campaign schema. Shards were hash-verified before comparison. Pairing
verified case ID, HTS10/rate line, origin, endpoint date, expected values and
query plan equality for every case. All selected/routing source hashes
matched when evaluating both variants.

## Commands, output and runtime

Exact argv, cwd, explicit environment overrides, timestamps, return codes,
stdout and stderr are in `logs/targeted-*.json`, `.stdout` and `.stderr`.
All four logged commands exited 0; all stderr files are empty.

| Logged command | Observed output | Wrapper elapsed seconds |
|---|---|---:|
| `targeted-selection` | 2,438 selected cases | 162.797 |
| `targeted-B-evaluate` | Four chapters completed, zero engine errors | 40.587 |
| `targeted-A-evaluate` | Four chapters completed, zero engine errors | 35.685 |
| `targeted-pair` | 2,438 matched case identities, transition counts above | 0.810 |

From the assigned workspace, the underlying reproduction commands are:

```sh
PY=/Users/maxghenis/TheAxiomFoundation/axiom-oracles/.venv/bin/python
ENGINE=/Users/maxghenis/TheAxiomFoundation/_tariff-parity/axiom-rules-engine/target/release/axiom-rules-engine
RUN=/Users/maxghenis/.subfleet/worktrees/20260923-140123-yale-campaign-full-v2
"$PY" yale-full-run/run_targeted_probe.py select --oracles-root yale-full-run/B/oracles --output yale-full-run/targeted-selection.json
TMPDIR="$RUN/yale-full-run/probe-tmp" "$PY" yale-full-run/run_targeted_probe.py evaluate --oracles-root "$RUN/yale-full-run/B/oracles" --rulespec-root "$RUN/yale-full-run/B/rulespec-us" --engine-binary "$ENGINE" --selection yale-full-run/targeted-selection.json --output-dir yale-full-run/targeted-B
TMPDIR="$RUN/yale-full-run/probe-tmp" "$PY" yale-full-run/run_targeted_probe.py evaluate --oracles-root "$RUN/yale-full-run/A/oracles" --rulespec-root "$RUN/yale-full-run/A/rulespec-us" --engine-binary "$ENGINE" --selection yale-full-run/targeted-selection.json --output-dir yale-full-run/targeted-A
"$PY" yale-full-run/pair_targeted_probe.py --oracles-root yale-full-run/B/oracles --baseline-manifest yale-full-run/targeted-A/diagnostic-MANIFEST.json --candidate-manifest yale-full-run/targeted-B/diagnostic-MANIFEST.json --output yale-full-run/targeted-A-B-paired.json
```

Artifacts: `targeted-selection.json`; `targeted-A/` and `targeted-B/` each
contain the diagnostic manifest, four compressed result shards and four
census files; `targeted-A-B-paired.json` contains all transition counts and
samples; the four `logs/targeted-*` command records retain reproduction
details. `run_targeted_probe.py` and `pair_targeted_probe.py` are the helpers.

## Helper regression checks

The current comparator/selectors replay over the prior hash-verified CH79
shard reproduced 90,072 comparisons, 87,762 matches, 2,310 mismatches and
1,286 unexplained units (Brazil 36, note 52 620, totals 630). The canonical
record SHA and all six prior summary fields matched the prior lane receipt.
The identity pair test on that same shard returned 87,762 retained matches,
2,310 retained mismatches and no changed/new/fixed rows. Receipts:
`baseline-ch79-current-census.json`, its chapter artifact, and
`pair-helper-self-test-ch79.json`, its chapter artifact.
