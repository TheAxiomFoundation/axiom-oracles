# Historical A eligibility

**No original historical A shard is accepted by the current cache keys.**
The only retained, freshly evaluated A chapter accepted by its preserved receipt
is CH79. Its compressed body is identical to historical CH79, providing a
current-key reproduction of that chapter only. Historical full-schedule
match-to-mismatch counts remain unavailable under the requested key restriction.

The local hash-only audit [historical-eligibility.json](historical-eligibility.json)
recomputed the current campaign's exact key ingredients, checked its optimized
calculation against the actual `_shard_key` helper for CH79, and verified all
100 historical compressed bodies (722,142,701 bytes). It took 17.056 seconds.
No shard was decompressed, evaluated, rekeyed, paired, or classified by this audit.
No receipt or manifest was changed.

| A source | Hash-verified chapters | Matching keys | Current-key paired population |
|---|---:|---:|---|
| Original historical manifest, retained fresh-A receipt | 100 | 0 | None |
| Original historical manifest, archived origin/main receipt | 100 | 0 | None |
| Original historical manifest, historical pre-#510 receipt digest | 100 | 100 | Diagnostic explanation only; that receipt was not installed |
| Retained freshly evaluated A manifest, retained fresh-A receipt | 1 | 1 | CH79: 8,100 cases / 90,072 comparisons |

The original historical keys also match 0/100 when calculated using B's receipt;
baseline eligibility must in any event use A's own inputs and receipt.

For **CH79 only**, the prior fresh A/B pair receipt remains bound to the exact
current campaign source, accepted A key, accepted B key and both shard hashes.
It records **0 matches becoming mismatches** and **1,266 mismatches becoming
matches** across 90,072 comparisons. These are prior-lane measured results whose
artifact and input hashes were reverified here; pairing was not rerun. Historical
CH79's compressed body is byte-identical to this accepted A reproduction, so
the same numerical transition count describes that historical output, while
the original historical key itself remains stale. This is not a full-schedule
historical comparison.

The prior lane separately measured CH29 historical-A/fresh-B transitions:
2,066 matches became mismatches (Brazil 82, note 52 1,000, total 984), and
104,030 mismatches became matches. Its A shard fails the current-key restriction,
so those historical diagnostic counts are **excluded** from the eligible
population above. They are not fresh observations from this audit. Evidence is
the prior run's `paired-ch29-historical-A-fresh-B.json` and `RESULT.md`.

## Why the keys differ

The current campaign hashes the whole input-contract receipt in
`B/oracles/scripts/us_tariff_schedule_campaign.py:728–735`. It appends measured
duration to that receipt at `:2143–2144`. The resume condition requires the
computed key to exist in the manifest and its file to pass the recorded hash
at `:825–829`; matching output bytes alone cannot satisfy a different key.

The independently retained receipt hashes are:

| Receipt | SHA-256 |
|---|---|
| Retained fresh A | `8b043af60d2b7c3be4b54072d1ebadb95ed3bd8e68dd793fffa0ed8ccf0c9d64` |
| Archived origin/main | `bdd258d7e86a81d4ffd472149d14033b75c11ceb490ae13685592c06475da717` |
| Historical pre-#510 | `48f9caf2ad8461035007a1ee3b0d38968abc4c3da6239d5383631bae9de2ba29` |
| Retained B | `8494896f42fff6a6a24700d979bef4fd4f6f57a88c783b19bd4f139eed196e8a` |

The historical digest comes from the prior lane's hashed
`baseline-historical-cache-audit.json`; no historical receipt was installed.
The audit also confirmed byte-identical A/B campaign source and selected/routing
inputs, and that A's preserved input-contract entry-flag tool hash still matches
its source.

## Command run

Run from the assigned workspace:

```sh
nice -n 10 /Users/maxghenis/TheAxiomFoundation/axiom-oracles/.venv/bin/python -B \
  yale-b-full/audit_historical_eligibility.py \
  --prior-run /Users/maxghenis/.subfleet/worktrees/20260923-140123-yale-campaign-full-v2/yale-full-run \
  --candidate yale-b-full/B \
  --engine /Users/maxghenis/TheAxiomFoundation/_tariff-parity/axiom-rules-engine/target/release/axiom-rules-engine \
  --output yale-b-full/historical-eligibility.json
```

Exit code: 0. The shell emitted `nice: setpriority: Operation not permitted`
before the Python process completed; this audit therefore makes no claim that
the requested priority was applied. All assertions passed. Organization rules,
the prior checkpoint report, setup commands, relevant logs and cache diagnostics
were read. All inputs remained read-only. No network, API, publication or git
mutation command ran for this audit.

Artifacts: [audit_historical_eligibility.py](audit_historical_eligibility.py),
[historical-eligibility.json](historical-eligibility.json), and this report.
