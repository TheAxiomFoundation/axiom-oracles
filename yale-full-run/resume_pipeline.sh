#!/bin/sh
# Resume the retained, unmodified current campaign. This can take many hours.
# Existing prepass/input-contract/projection receipts are retained: re-running
# input-contract changes its timing hash and invalidates every current key.
set -eu
RUN_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
VARIANT=${1:-B}
case "$VARIANT" in A|B) ;; *) echo 'usage: resume_pipeline.sh A|B' >&2; exit 2;; esac
PYTHON_BIN=/Users/maxghenis/TheAxiomFoundation/axiom-oracles/.venv/bin/python
ENGINE_BIN=/Users/maxghenis/TheAxiomFoundation/_tariff-parity/axiom-rules-engine/target/release/axiom-rules-engine
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
run_stage() {
    STAGE=$1
    shift
    python3 "$RUN_ROOT/run_logged.py" \
        --label "$VARIANT-resume-$STAMP-$STAGE" \
        --cwd "$RUN_ROOT/$VARIANT/oracles" \
        --env "AXIOM_TARIFF_C1_CACHE=$RUN_ROOT/$VARIANT/cache" \
        --env "RULESPEC_US_CHECKOUT=$RUN_ROOT/$VARIANT/rulespec-us" \
        -- "$PYTHON_BIN" scripts/us_tariff_schedule_campaign.py "$STAGE" \
        --rulespec-root ../rulespec-us --engine-binary "$ENGINE_BIN" "$@"
}
# Largest combined Brazil/note-52 exposures first; all remaining chapters next.
run_stage evaluate --chapters 62,84,29 --workers 3 --resume
run_stage evaluate --workers 3 --resume
run_stage compare
# These unmodified stages may fail on the historical preview population guard.
# Preserve the failure; do not substitute a diagnostic for a v2 receipt.
run_stage classify
run_stage report
