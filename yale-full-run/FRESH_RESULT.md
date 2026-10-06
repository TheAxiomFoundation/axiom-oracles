# Combined fresh A/B measurements

The measured cohort comprises complete Chapter 79 (8,100 endpoint cases)
plus 2,438 disjoint bounded probes in Chapters 62, 84, 29 and 94. Both
variants were freshly evaluated. The combined 10,538 case identities and
their origin counts match exactly across A/B; 141 origins are represented.
This is partial schedule coverage and is not a representative sample for
estimating full-schedule counts. It is not an official classification or
conformance receipt.

| Metric | A: 96d5e7c1 | B: c6264502 |
|---|---:|---:|
| Endpoint cases | 10,538 | 10,538 |
| Comparisons | 118,194 | 118,194 |
| Matches | 112,030 | 114,532 |
| Mismatches | 6,164 | 3,662 |
| Unexplained Brazil components | 426 | 6 |
| Unexplained note 52 components | 1,382 | 80 |
| Unexplained totals | 1,586 | 82 |
| All unexplained units | 3,394 | 168 |
| Axiom-attributed-open components | 0 | 83 |
| Engine errors | 0 | 0 |
| Measured cohort satisfies zero unexplained and zero open | No | No |

B closes all 1,286 unexplained units observed in complete CH79. Its 168
remaining unexplained units in the combined cohort are on HTS10
`9403999020`: six Brazil component rows, 80 note 52 component rows and 82
totals. The 83 B open components are `cafta-52i-deferred` 5,
`section232-annex-brazil` 33, `section232-annex-forced-labor` 35,
`section232-heading-brazil` 2 and `section232-heading-forced-labor` 8.

The paired records show 2,660 mismatching rows becoming matches and 158
matching rows becoming mismatches, a net reduction of 2,502 mismatches.

| Paired transition | Brazil | Note 52 | Total | All |
|---|---:|---:|---:|---:|
| Mismatch to match | 329 | 1,154 | 1,177 | 2,660 |
| Match to mismatch | 61 | 70 | 27 | 158 |
| Retained mismatch, changed actual | 91 | 148 | 387 | 626 |

The new mismatches occur in the bounded probes. Their component and total
deltas are positive. Samples, selection criteria and per-class breakdowns
are in [TARGETED_RESULT.md](TARGETED_RESULT.md),
`targeted-A-B-paired.json` and the underlying chapter census files.

## Verified provenance

`combine_fresh.py` uses the existing `aggregate()` function on five disjoint
chapter populations for each variant. It verifies census artifact hashes,
all ten underlying compressed shard hashes, source case counts, absence of
duplicate case IDs, equality of combined A/B identities, and conservation
of comparison and transition counts. It recomputes the complete CH79 pair
directly from the fresh A/B result shards, without invoking the engine.

The earlier CH79 pair had used historical cached A results. The fresh A
CH79 gzip bytes independently hash to the same SHA-256 as that historical
shard:
`03624b9ab3ee7539ae7ef0333725e1a1e79211dbee08d035e07786ab44ee3e62`.
The directly recomputed fresh CH79 pairing also produces exactly the same
transition counts as the earlier historical/fresh pair. The combined
receipt uses the directly recomputed fresh pair.

Fresh B CH79 gzip SHA-256 is
`d0dbcb414a8314765aa75ad1d24f216d464614a5972fbdd49c8baf597a0f5704`.
The common combined case-ID population SHA-256 is
`214b89cb39265424b60117eeb2e17d054d81c4da8155345815197bbde9222fdd`.

All source paths, hashes, campaign/ledger/routing input hashes, case counts,
origin histograms, bounded selection criteria and complete class/slot
censuses are retained in `fresh-combined-census.json`. The schema is
`measurement.fresh_combined_partial_census.v1`; it explicitly marks full
schedule coverage and representative-population claims false.

## Command and observed output

```sh
/Users/maxghenis/TheAxiomFoundation/axiom-oracles/.venv/bin/python yale-full-run/combine_fresh.py --run-root yale-full-run --output yale-full-run/fresh-combined-census.json
```

The logged command exited 0 with empty stderr. It printed the table totals
above and `PASS: artifact/shard hashes, disjoint cohorts, equal A/B identities,
census and paired conservation`. Helper runtime was 7.107 seconds; the
logging wrapper measured 13.359 seconds. Exact argv, cwd, timestamps and
output are in `logs/fresh-combined.json`, `.stdout` and `.stderr`.

Underlying fresh CH79 shard receipts record 153.706 seconds for A and
303.372 seconds for B. The bounded selection/evaluation/pair command times
are recorded separately in `TARGETED_RESULT.md`; these overlapping runs
must not be summed as overall wall time.

New artifacts: `combine_fresh.py`, `fresh-combined-census.json`,
`fresh-ch79-paired.json`, `FRESH_RESULT.md`, and `logs/fresh-combined.*`.
No engine evaluation was run to produce this combined report.
