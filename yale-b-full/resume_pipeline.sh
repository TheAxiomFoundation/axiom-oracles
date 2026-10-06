#!/bin/sh
# Preserve all preparation receipts. This runs only evaluation, comparison,
# and diagnostic census; official classify needs a separate producer update.
set -eu
RUN_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON_BIN=/Users/maxghenis/TheAxiomFoundation/axiom-oracles/.venv/bin/python
ENGINE_BIN=/Users/maxghenis/TheAxiomFoundation/_tariff-parity/axiom-rules-engine/target/release/axiom-rules-engine
RUN_STAMP=$(date -u +%Y%m%dT%H%M%SZ)
run_stage() {
    STAGE=$1
    shift
    "$PYTHON_BIN" "$RUN_ROOT/run_logged.py" \
        --label "B-$RUN_STAMP-$STAGE" \
        --cwd "$RUN_ROOT/B/oracles" \
        --env "AXIOM_TARIFF_C1_CACHE=$RUN_ROOT/B/cache" \
        --env "RULESPEC_US_CHECKOUT=$RUN_ROOT/B/rulespec-us" \
        --env "TMPDIR=$RUN_ROOT/tmp" \
        -- nice -n 10 "$PYTHON_BIN" -u scripts/us_tariff_schedule_campaign.py "$STAGE" \
        --rulespec-root ../rulespec-us --engine-binary "$ENGINE_BIN" "$@"
}
mkdir -p "$RUN_ROOT/tmp"
"$PYTHON_BIN" "$RUN_ROOT/run_logged.py" \
    --label "B-$RUN_STAMP-priority-check" --cwd "$RUN_ROOT" \
    -- nice -n 10 "$PYTHON_BIN" "$RUN_ROOT/check_priority.py"
run_stage evaluate --workers 3 --resume
run_stage compare
"$PYTHON_BIN" "$RUN_ROOT/run_logged.py" \
    --label "B-$RUN_STAMP-diagnostic-inventory" --cwd "$RUN_ROOT" \
    --env "RULESPEC_US_CHECKOUT=$RUN_ROOT/B/rulespec-us" \
    -- nice -n 10 "$PYTHON_BIN" "$RUN_ROOT/helpers/inventory_completed.py" \
    --oracles-root "$RUN_ROOT/B/oracles" --rulespec-root "$RUN_ROOT/B/rulespec-us" \
    --engine-binary "$ENGINE_BIN" --output "$RUN_ROOT/B-completed-gap-inventory.json"
