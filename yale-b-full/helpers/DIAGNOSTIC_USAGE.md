# Incremental diagnostic inventory

`inventory_completed.py` uses the preceding lane's unchanged `measure_shards.py`
and the campaign's current comparison and selector functions. It does not run
official `classify` or create an official classification receipt. The existing
preview-population producer still requires an update before official classification.

Run sequentially after the evaluator has stopped, so the three evaluation workers
retain the machine's available capacity. The command snapshots the manifest and
measures only its completed chapters. A subsequent invocation picks up new
completed chapters and skips retained censuses after verification.

```sh
RUN=/Users/maxghenis/.subfleet/worktrees/20260923-222653-yale-campaign-b-full/yale-b-full
PY=/Users/maxghenis/TheAxiomFoundation/axiom-oracles/.venv/bin/python
ENGINE=/Users/maxghenis/TheAxiomFoundation/_tariff-parity/axiom-rules-engine/target/release/axiom-rules-engine
nice -n 10 "$PY" "$RUN/helpers/inventory_completed.py" \
  --oracles-root "$RUN/B/oracles" \
  --rulespec-root "$RUN/B/rulespec-us" \
  --engine-binary "$ENGINE" \
  --output "$RUN/B-completed-gap-inventory.json"
```

Add `--chapters 79` for a bounded verification, or `--verify-only` to verify all
retained censuses without measuring missing chapters. Use the same output path
for continuation. Do not rerun `input-contract` to prepare this helper.

Every retained chapter is bound to the compressed shard hash, the unchanged
campaign's recomputed cache key, helper hashes, current comparison/selector code,
input receipt, routing assets, preview receipt/producer, four membership tables,
and sample limit. A changed fingerprint fails closed; use a new output stem for
an intentionally changed diagnostic source. The manifest's own hash is recorded
as a snapshot, but new completed chapters do not invalidate earlier censuses.

Outputs:

- `B-completed-gap-inventory.json`: aggregate counts, all mismatch classes/slots
  per chapter, nonzero unexplained/open gap families ranked by comparison units,
  samples containing HTS10/origin/date/Axiom/Yale, and per-chapter artifact hashes.
- `B-completed-gap-inventory.md`: summary and ranked chapter/class/slot gap table.
- `B-completed-gap-inventory-chapters/chXX.json`: independently resumable census
  envelopes with source/shard fingerprints, sample records and conservation checks.

Class/slot families group observed units. Different legal mechanisms can share a
class; assigning a cause and proposing a fix still requires the separate source
audit. Total comparison units and component units are both counted explicitly;
their sum is not a count of distinct entries. Historical A pairing is separate.

Completed chapters are checkpointed atomically. A SIGINT is recorded as
interrupted; a killed in-progress chapter is absent from the completed list and
will be measured on the next invocation. The evaluator's official manifest is
never edited by this helper.
