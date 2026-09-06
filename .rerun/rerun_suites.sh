#!/bin/zsh
set -o pipefail
cd /Users/maxghenis/TheAxiomFoundation/axiom-oracles/.claude/worktrees/amazing-zhukovsky-51fce0
export AXIOM_RULESPEC_US_ROOT=$HOME/TheAxiomFoundation/_oracle-pins/rulespec-us
for suite in sc-snap-ecps az-snap-ecps tn-snap-ecps al-snap-ecps ma-snap-ecps nc-snap-ecps ga-snap-ecps ny-snap-ecps fl-snap-ecps ca-snap-ecps; do
  echo "===== START $suite $(date +%H:%M:%S) ====="
  uv run scripts/run_comparison.py "$suite" > .rerun/$suite.log 2>&1
  rc=$?
  tail -6 .rerun/$suite.log
  echo "===== DONE $suite exit=$rc $(date +%H:%M:%S) ====="
done
echo "ALL RERUNS COMPLETE"
