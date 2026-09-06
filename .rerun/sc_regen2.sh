#!/bin/zsh
cd /Users/maxghenis/TheAxiomFoundation/axiom-oracles/.claude/worktrees/amazing-zhukovsky-51fce0
echo "== apply_dispositions (merge all)"; uv run scripts/apply_dispositions.py 2>&1 | grep -v "^note:" | tail -3; echo "rc=${pipestatus[1]}"
echo "== emit_case_artifacts sc"; uv run scripts/emit_case_artifacts.py sc-snap-ecps 2>&1 | tail -2; echo "rc=${pipestatus[1]}"
echo "== emit_disposition_artifacts"; uv run scripts/emit_disposition_artifacts.py 2>&1 | tail -1
echo "== overview"; uv run scripts/generate_dashboard_overview.py 2>&1 | tail -1
echo "== scoreboard"; uv run scripts/conformance_scoreboard.py 2>&1 | tail -1
echo "== apply --check"; uv run scripts/apply_dispositions.py --check 2>&1 | grep -v "^note:" | tail -2; echo "rc=${pipestatus[1]}"
echo "== case-artifacts --check (sc only)"; uv run scripts/emit_case_artifacts.py --check sc-snap-ecps 2>&1 | tail -1; echo "rc=${pipestatus[1]}"
echo "== case-artifacts --check (all, informational)"; uv run scripts/emit_case_artifacts.py --check 2>&1 | tail -1; echo "rc=${pipestatus[1]}"
echo "== ratchets"; uv run scripts/conformance_ratchet.py --check 2>&1 | tail -1; uv run scripts/unexplained_ratchet.py --check 2>&1 | tail -1
echo "== census/certify"; uv run python scripts/exercise_census.py 2>&1 | tail -1; uv run python scripts/certify.py 2>&1 | tail -1
echo "== overview --check"; uv run scripts/generate_dashboard_overview.py --check 2>&1 | tail -1
git status --short | grep -v "^?? .rerun"
echo REGEN2-DONE
