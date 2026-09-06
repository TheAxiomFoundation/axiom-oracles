#!/bin/zsh
set -e
cd /Users/maxghenis/TheAxiomFoundation/axiom-oracles/.claude/worktrees/amazing-zhukovsky-51fce0
echo "== apply_dispositions (merge sc)"
uv run scripts/apply_dispositions.py --suite sc-snap-ecps 2>&1 | tail -3 || uv run scripts/apply_dispositions.py 2>&1 | tail -3
echo "== emit_disposition_artifacts"
uv run scripts/emit_disposition_artifacts.py 2>&1 | tail -2
echo "== emit_case_artifacts"
uv run scripts/emit_case_artifacts.py --suite sc-snap-ecps 2>&1 | tail -2 || uv run scripts/emit_case_artifacts.py 2>&1 | tail -2
echo "== overview"
uv run scripts/generate_dashboard_overview.py 2>&1 | tail -1
echo "== scoreboard"
uv run scripts/conformance_scoreboard.py 2>&1 | tail -1
echo "== checks"
uv run scripts/apply_dispositions.py --check 2>&1 | tail -2
uv run scripts/emit_case_artifacts.py --check 2>&1 | tail -1
uv run scripts/conformance_ratchet.py --check 2>&1 | tail -1
uv run scripts/unexplained_ratchet.py --check 2>&1 | tail -1
uv run python scripts/exercise_census.py 2>&1 | tail -1
uv run python scripts/certify.py 2>&1 | tail -1
uv run scripts/generate_dashboard_overview.py --check 2>&1 | tail -1
echo REGEN-DONE
