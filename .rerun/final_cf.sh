#!/bin/zsh
cd /Users/maxghenis/TheAxiomFoundation/axiom-oracles/.claude/worktrees/amazing-zhukovsky-51fce0
run() {
  uv run --python 3.14 --no-project --with-editable . \
    --with policyengine==4.18.9 --with policyengine-us==1.767.3 --with policyengine-core==3.30.3 \
    python .rerun/final_counterfactuals.py --suite $1 --cases $2 --output .rerun/finalcf-$1.json 2>&1 | grep -vE "Warning|warn|us_latest|Installed"
}
run al-snap-ecps ecps-37422
run sc-snap-ecps ecps-28842,ecps-29732
run nc-snap-ecps ecps-28618
run ma-snap-ecps ecps-2364,ecps-3161
run fl-snap-ecps ecps-33139,ecps-33182,ecps-33897
run ga-snap-ecps ecps-29878,ecps-30033,ecps-30605,ecps-30736,ecps-30843,ecps-31013,ecps-31017,ecps-31306,ecps-71017,ecps-71437
run ny-snap-ecps ecps-4813,ecps-5104,ecps-5196,ecps-5469,ecps-6134,ecps-6692,ecps-6798,ecps-7001,ecps-7277,ecps-65322,ecps-66401
run ca-snap-ecps ecps-57335,ecps-57437,ecps-57912,ecps-58676,ecps-58805,ecps-60285,ecps-60408,ecps-61042,ecps-61658,ecps-62891,ecps-58918,ecps-59112,ecps-59211,ecps-59794
echo FINAL-CF-DONE
