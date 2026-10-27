#!/bin/sh
# Run one fiit-ecps EITC attribution stage in the harness environment of the
# suite's runner (comparisons/fiit-ecps.yaml, pinned: Python 3.13,
# policyengine 4.11.0, PolicyEngine-US 1.729.0 from its release commit,
# policyengine-core 3.26.11, spm-calculator 0.3.1).
#
# Usage: run_stage.sh <stage script> [stage arguments...]
#
# Environment:
#   AXIOM_ORACLES  axiom-oracles checkout whose bridge the full run used; the
#                  stage runs from it, with it first on PYTHONPATH
#   AXIOM_ENCODE   axiom-encode checkout (the tax-ecps harness)
#
# Stages run for hours on the full mismatch population; launch them under
# launchd (or another supervisor that outlives the shell), not nohup.
set -u
: "${AXIOM_ORACLES:?set AXIOM_ORACLES to the axiom-oracles checkout}"
: "${AXIOM_ENCODE:?set AXIOM_ENCODE to the axiom-encode checkout}"
here=$(cd "$(dirname "$0")" && pwd)
script=$1
shift
export OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4
export VECLIB_MAXIMUM_THREADS=4 NUMEXPR_NUM_THREADS=4 RAYON_NUM_THREADS=4
export OMP_WAIT_POLICY=PASSIVE
export PYTHONPATH="$AXIOM_ORACLES"
cd "$AXIOM_ORACLES" || exit 1
echo "START $(date -u +%FT%TZ) $script"
status=0
uv run --python 3.13 --no-project --with-editable "$AXIOM_ENCODE" \
  --with policyengine==4.11.0 \
  --with "policyengine-us @ https://github.com/PolicyEngine/policyengine-us/archive/180410fe35209fb8201378c1b32dadd38051c342.tar.gz" \
  --with policyengine-core==3.26.11 --with spm-calculator==0.3.1 \
  python "$here/$script" "$@" || status=$?
echo "EXIT $status $(date -u +%FT%TZ)"
exit "$status"
