#!/bin/zsh
cd /Users/maxghenis/TheAxiomFoundation/axiom-oracles/.claude/worktrees/amazing-zhukovsky-51fce0
for suite in al-snap-ecps sc-snap-ecps nc-snap-ecps ma-snap-ecps; do
  echo "===== TRACE $suite $(date +%H:%M:%S)"
  uv run --python 3.14 --no-project --with-editable . \
    --with policyengine==4.18.9 --with policyengine-us==1.767.3 --with policyengine-core==3.30.3 \
    python .rerun/trace_suite_residuals.py --suite $suite --output .rerun/trace-$suite.json 2>&1 | tail -3
  echo "===== rc=$? $(date +%H:%M:%S)"
done
echo TRACE-SMALL-DONE
