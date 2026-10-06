# Complete fresh candidate Chapter 29

The isolated candidate evaluation completed successfully at
2026-09-23 20:16:33 UTC, before its timeout. Its complete shard contains
991,575 endpoint cases and no engine errors. SHA-256 verification passed:
`24bda301e144abc4cd1e7c8d2868d91a9edfbd1ca0d83ecc803e63f110ca5d1c`.

| Current comparator/selector diagnostic | Fresh B CH29 |
|---|---:|
| Cases | 991,575 |
| Comparisons | 11,689,650 |
| Matches | 11,493,380 |
| Mismatches | 196,270 |
| Unexplained | 0 |
| Axiom-attributed-open | 0 |
| Derived total mismatch units | 95,567 |
| Engine errors | 0 |

The remaining Brazil and note 52 mismatch counts are 4,218 and 54,496.
Current selectors classify all of them. Their component classes are:

| Class | Units |
|---|---:|
| pharma-utilization-proxy-brazil | 4,136 |
| pharma-utilization-proxy-forced-labor-035 | 964 |
| pharma-utilization-proxy-forced-labor-non035 | 52,532 |
| yale-zero-pharma-brazil | 82 |
| yale-zero-pharma-forced-labor | 1,000 |

This is a complete chapter census, not a full-schedule classification or
conformance receipt. Full campaign and preview-selector population guards
were not evaluated by this diagnostic. These results remain separate from
the fresh matched A/B primary table: A has no fresh complete CH29 run, and
the bounded CH29 probes already contribute to that table.

## Pairing against historical A

The separate historical-A/fresh-B pairing verified both shard hashes and
the identity and comparability of every paired case. Historical A CH29 is
not represented as a fresh run or as accepted by current cache-key rules.

| Paired transition | Brazil | Note 52 | Total | All |
|---|---:|---:|---:|---:|
| Mismatch to match | 2,610 | 50,600 | 50,820 | 104,030 |
| Match to mismatch | 82 | 1,000 | 984 | 2,066 |
| Retained mismatch, changed actual | 4,136 | 53,496 | 55,582 | 113,214 |

Historical A's 298,234 mismatches decline to B's 196,270, a net reduction
of 101,964. The source historical census contains 217,228 unexplained
units; B contains zero. Pairing evidence and samples are in
`paired-ch29-historical-A-fresh-B.json` and its chapter artifact.

## Commands and observed output

```sh
/Users/maxghenis/TheAxiomFoundation/axiom-oracles/.venv/bin/python yale-full-run/measure_shards.py --oracles-root yale-full-run/B/oracles --rulespec-root yale-full-run/B/rulespec-us --manifest yale-full-run/B/ch29-isolated-MANIFEST.json --chapters 29 --output yale-full-run/B-fresh-ch29-census.json
/Users/maxghenis/TheAxiomFoundation/axiom-oracles/.venv/bin/python yale-full-run/pair_shards.py --oracles-root yale-full-run/B/oracles --rulespec-root yale-full-run/B/rulespec-us --baseline-manifest yale-full-run/A/committed/MANIFEST.json --candidate-manifest yale-full-run/B/ch29-isolated-MANIFEST.json --chapters 29 --output yale-full-run/paired-ch29-historical-A-fresh-B.json
```

Both commands exited 0 with empty stderr and printed the counts above.
The census command took 94.800 seconds through the logging wrapper
(86.676 seconds processing the chapter); the pairing command took 122.089
seconds (121.743 seconds processing the pair). The earlier isolated engine
command took 1,782.190 seconds through its wrapper; its shard receipt
records 1,730.683 seconds.

Exact argv, environment overrides, timestamps, stdout and stderr:
`logs/B-evaluate-ch29-isolated.*`, `logs/B-fresh-ch29-census.*`, and
`logs/paired-ch29-historical-A-fresh-B.*`.

Artifacts: `B/ch29-isolated-MANIFEST.json`, the hash-verified shard it
references, `B-fresh-ch29-census.json`,
`B-fresh-ch29-census-chapters/ch29.json`,
`paired-ch29-historical-A-fresh-B.json`, and
`paired-ch29-historical-A-fresh-B-chapters/ch29.json`.
No official manifest was edited by this diagnostic work.
