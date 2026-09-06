#!/bin/zsh
cd /Users/maxghenis/TheAxiomFoundation/axiom-oracles/.claude/worktrees/amazing-zhukovsky-51fce0
for suite in al-snap-ecps sc-snap-ecps ga-snap-ecps ny-snap-ecps nc-snap-ecps ma-snap-ecps ca-snap-ecps; do
  until [ -f .rerun/trace-$suite.json ]; do sleep 20; done
  if [ -f .rerun/unforced-$suite.json ]; then echo "skip $suite"; continue; fi
  echo "===== UNFORCED $suite $(date +%H:%M:%S)"
  uv run --python 3.14 --no-project --with-editable . \
    --with policyengine==4.18.9 --with policyengine-us==1.767.3 --with policyengine-core==3.30.3 \
    python .rerun/unforced_pass.py --suite $suite --output .rerun/unforced-$suite.json 2>&1 | grep -vE "Warning|warn|Installed|Built|Uninstalled" | tail -25
  echo "===== rc=$? $(date +%H:%M:%S)"
done
echo UNFORCED-ALL-DONE
