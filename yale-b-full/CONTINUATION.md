# Exact B continuation

Only CH29 and CH79 are completed. Their shards, keys, preparation receipts and
paths have been verified in this workspace. Do not rerun `prepass`,
`input-contract`, or `projection`: input-contract's measured duration changes
its receipt hash and invalidates the retained keys.

Run from a terminal that permits `nice` to apply process niceness 10:

```sh
sh /Users/maxghenis/.subfleet/worktrees/20260923-222653-yale-campaign-b-full/yale-b-full/resume_pipeline.sh
```

The script verifies actual niceness, then runs the following evaluation with all
100 declared chapter shards selected. The unchanged evaluator skips CH29/79,
then processes the 98 remaining shards with three workers. It runs official
`compare` only after evaluation succeeds, then the current-selector diagnostic
inventory. It does not run official `classify`, whose preview-population
producer needs an update.

The evaluator command in full:

```sh
RUN=/Users/maxghenis/.subfleet/worktrees/20260923-222653-yale-campaign-b-full/yale-b-full
PY=/Users/maxghenis/TheAxiomFoundation/axiom-oracles/.venv/bin/python
ENGINE=/Users/maxghenis/TheAxiomFoundation/_tariff-parity/axiom-rules-engine/target/release/axiom-rules-engine
cd "$RUN/B/oracles"
export AXIOM_TARIFF_C1_CACHE="$RUN/B/cache"
export RULESPEC_US_CHECKOUT="$RUN/B/rulespec-us"
export TMPDIR="$RUN/tmp"
mkdir -p "$TMPDIR"
nice -n 10 "$PY" "$RUN/check_priority.py"
nice -n 10 "$PY" -u scripts/us_tariff_schedule_campaign.py evaluate \
  --rulespec-root ../rulespec-us --engine-binary "$ENGINE" --workers 3 --resume
nice -n 10 "$PY" -u scripts/us_tariff_schedule_campaign.py compare \
  --rulespec-root ../rulespec-us --engine-binary "$ENGINE"
nice -n 10 "$PY" "$RUN/helpers/inventory_completed.py" \
  --oracles-root "$RUN/B/oracles" --rulespec-root "$RUN/B/rulespec-us" \
  --engine-binary "$ENGINE" --output "$RUN/B-completed-gap-inventory.json"
```

Prefer the script: it stops on a failed priority check or stage and records
argument vectors, explicit environment overrides, timestamps, output and exit
codes in `logs/`. The manual block is an explanation of its stages, not a record
that the remaining chapters or comparison ran in this lane.

The current sandbox rejects `setpriority`; the priority preflight observed
niceness 0, required 10, and exited 2. The long evaluation was not started while
a decision about relaxing the requested priority was pending.

If a future evaluation is interrupted, keep the manifest as written by the
campaign. Only completed compressed shards enter that manifest. Verify its
completed chapter set using `evaluate --chapters <comma-separated-completed-list>
--workers 3 --resume` with the same environment. Never promote partial data or
change keys. Then rerun the same script. The diagnostic helper also resumes only
when its source/receipt/shard fingerprint and stored census hash match.

The chapter manifest is
`B/oracles/reference/us-tariff-schedule/eval/MANIFEST.json`.
The complete required and remaining lists are in `CHECKPOINT.json`.
