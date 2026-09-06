#!/bin/zsh
set -e
cd /Users/maxghenis/TheAxiomFoundation/axiom-oracles/.claude/worktrees/amazing-zhukovsky-51fce0
git fetch origin --quiet
git merge origin/main -X ours --no-edit --quiet
uv run scripts/conformance_scoreboard.py > /dev/null 2>&1
uv run scripts/generate_dashboard_overview.py > /dev/null 2>&1
uv run scripts/check_vacuous_gate.py > /dev/null 2>&1
uv run python scripts/exercise_census.py > /dev/null 2>&1
uv run python scripts/certify.py > /dev/null 2>&1
uv run scripts/apply_dispositions.py --check > /dev/null 2>&1
uv run scripts/conformance_ratchet.py --check > /dev/null 2>&1
uv run scripts/unexplained_ratchet.py --check > /dev/null 2>&1
uv run scripts/conformance_burndown.py --check > /dev/null 2>&1
if ! git diff --quiet; then
  git add -A dashboard/ conformance/ certificates/
  git commit -q -m "data: refresh rollups on merge round (automated)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
fi
git push -q origin claude/snap-unexplained-sweep
echo "ROUND-PUSHED $(git rev-parse --short HEAD)"
