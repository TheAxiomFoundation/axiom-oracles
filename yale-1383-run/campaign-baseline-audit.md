# Observed campaign baseline failure

Main examined: `c52688619542c5e4a581c84d83283a0b0a5bf1b7`.
No candidate evaluation was run by this audit.

## Report stage

Command from the assigned workspace:

```sh
python3 main-checkout/scripts/us_tariff_schedule_campaign.py report > yale-1383-run/baseline-report-stage.log 2>&1
```

Observed exit status: **1**. Final output:

```text
ValueError: classification receipt schema is stale
```

The traceback is preserved in `baseline-report-stage.log`. The failure occurs
in `scripts/us_tariff_schedule_campaign.py:1549–1553`: the script requires
`axiom_oracles.us_tariff_schedule.classification.v2`. The committed receipt
reports `axiom_oracles.us_tariff_schedule.classification.v1` and has no
`inputs` field. Its census still contains `fed-false-family-brazil=93198`
and `fed-false-family-forced-labor=1499038`
(`reference/us-tariff-schedule/classification-receipt.json:4–5`).

The stage failed before writing a report. This is an observed baseline
reproduction failure, independent of any candidate corpus resolution.

## History and current selectors

Commands:

```sh
/usr/bin/git -C main-checkout log -10 --format='%H %s' -S 'fed-false-family-brazil' -- reference/us-tariff-schedule/campaign-dispositions.yaml
/usr/bin/git -C main-checkout log -5 --format='%H %s' -S 'classification receipt schema is stale' -- scripts/us_tariff_schedule_campaign.py
/usr/bin/git -C main-checkout show --format=fuller --stat 6ce2e674306d02506a5e1dbce21754a220290cbd -- reference/us-tariff-schedule/campaign-dispositions.yaml conformance/detail/us-tariff-schedule.json reference/us-tariff-schedule/classification-receipt.json certificates/us-tariff-duty.json
```

Observed removing/guard-introducing commit:

```text
6ce2e674306d02506a5e1dbce21754a220290cbd feat: classify tariff output-semantics dispositions
```

Commit date: 2026-08-28. For the four paths in the last command, its stat
listed only the disposition ledger (514 lines changed) and certificate
(2 lines changed); neither the classification receipt nor detail report was
listed. The diff removes both `fed-false-family-*` selectors and adds
`preview-1311-*` selectors. Current main's first selector is
`aircraft-utilization-proxy-brazil`, requiring a positive delta
(`campaign-dispositions.yaml:11–18`).

The current preview receipt records 18 selector populations totaling 395,330
units, including aircraft-utilization-proxy-brazil=3,654 and
aircraft-utilization-proxy-forced-labor=71,168. Neither ID appears in the
committed classification census. The current script also contains later
guards rejecting unknown class IDs and stale preview populations
(`us_tariff_schedule_campaign.py:1563–1581`); those guards were **not reached**
by the failed report command.

## Read-only chapter 79 census

The smallest nonempty cached chapters inspected were 31 (4,509 cases), 97
(5,670), and 79 (8,100). Chapters 31 and 97 had no mismatches in either target
slot. Chapter 79 had 36 Brazil and 620 forced-labor slot mismatches.

Command:

```sh
python3 yale-1383-run/chapter_census.py --oracles-root main-checkout --rulespec-root rulespec-baseline --manifest yale-1383-run/committed-main/reference/us-tariff-schedule/eval/MANIFEST.json --chapter 79 --output yale-1383-run/committed-ch79-census.json
```

This helper imports the unchanged main comparator and selector functions,
hash-verifies the committed shard, and reads it without rerunning the engine.
It is a **partial diagnostic**, not a fresh engine baseline or certificate.
The first attempt omitted `--manifest` and failed with `FileNotFoundError`
because the main-checkout manifest had been archived for the fresh baseline;
the command above is the corrected invocation.

Observed output (elapsed 161.864 seconds):

| Measure | Chapter 79 |
|---|---:|
| Cases | 8,100 |
| Comparisons | 90,072 |
| Matches | 87,762 |
| Mismatches | 2,310 |
| Engine errors | 0 |
| Direct units with no current selector | 656 |
| Unexplained, including totals | 1,286 |
| Classified derived totals | 495 |
| `column2-gn3b` | 351 |
| `legal-date-boundary-ieepa` | 70 |
| `vintage-revision-301-removed-lines` | 108 |

The helper's `axiom_attributed_open=0` is accompanied by 1,286 unexplained
units: the old target selectors have disappeared. It does not indicate
closure or conformance.

Observed sample: HTS10 `7903906000`, origin `CA`, 2026-07-24,
`forced_labor_section_301`: Axiom **0.0**, Yale **0.1**, delta **−0.1**;
no current selector matches. Further samples are in the census receipt.

Verified shard:

```text
/Users/maxghenis/PolicyEngine/_tariff-p5/c1-cache/eval/a1/a1a7f1475b4dc03548b924aae7ce2ef77fdda158b866ed0c2b6dbf6f503d4761.jsonl.gz
SHA-256 03624b9ab3ee7539ae7ef0333725e1a1e79211dbee08d035e07786ab44ee3e62
Canonical record SHA-256 148469a88a2144c9e8c9cb137b1f0c3057cf1a06cee568e3a2d868e0992e1dc9
```

Artifacts from this audit: `chapter_census.py`,
`committed-ch79-census.json`, `baseline-report-stage.log`, and this file.
No default-cache file was written.
