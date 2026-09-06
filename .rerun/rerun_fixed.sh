#!/bin/zsh
set -o pipefail
cd /Users/maxghenis/TheAxiomFoundation/axiom-oracles/.claude/worktrees/amazing-zhukovsky-51fce0
PIN7=$HOME/TheAxiomFoundation/_oracle-pins/c13cdf7d/rulespec-us
PINCA=$HOME/TheAxiomFoundation/_oracle-pins/edc62ea5/rulespec-us
for suite in al-snap-ecps sc-snap-ecps nc-snap-ecps ma-snap-ecps fl-snap-ecps ga-snap-ecps ny-snap-ecps ca-snap-ecps; do
  if [ "$suite" = "ca-snap-ecps" ]; then export AXIOM_RULESPEC_US_ROOT=$PINCA; else export AXIOM_RULESPEC_US_ROOT=$PIN7; fi
  echo "===== START $suite $(date +%H:%M:%S) pin=$AXIOM_RULESPEC_US_ROOT"
  uv run scripts/run_comparison.py "$suite" > .rerun/$suite.fixed.log 2>&1
  rc=$?
  tail -4 .rerun/$suite.fixed.log
  echo "===== DONE $suite exit=$rc $(date +%H:%M:%S)"
done
echo ALL-FIXED-RERUNS-COMPLETE
