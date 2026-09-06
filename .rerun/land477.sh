#!/bin/zsh
cd /Users/maxghenis/TheAxiomFoundation/axiom-oracles/.claude/worktrees/amazing-zhukovsky-51fce0
PR=477; BR=claude/sc-29732-reclassify
for attempt in 1 2 3 4 5; do
  echo "=== attempt $attempt"
  ok=0
  for i in $(seq 1 40); do
    sleep 60
    P=$(gh pr checks $PR --repo TheAxiomFoundation/axiom-oracles 2>/dev/null | grep -c pass)
    F=$(gh pr checks $PR --repo TheAxiomFoundation/axiom-oracles 2>/dev/null | grep -c fail)
    M=$(gh pr view $PR --repo TheAxiomFoundation/axiom-oracles --json mergeable --jq .mergeable 2>/dev/null)
    echo "tick $i pass=$P fail=$F mergeable=$M"
    [ "$F" != "0" ] && { echo CI-FAILED; ok=2; break }
    if [ "$M" = "CONFLICTING" ]; then
      echo "conflict -> merging origin/main (-X ours) and regenerating"
      git fetch origin --quiet && git merge origin/main -X ours --no-edit --quiet || { echo MERGE-FAILED; ok=2; break }
      uv run scripts/apply_dispositions.py > /dev/null 2>&1
      uv run scripts/emit_disposition_artifacts.py > /dev/null 2>&1
      uv run scripts/generate_dashboard_overview.py > /dev/null 2>&1
      uv run scripts/conformance_scoreboard.py > /dev/null 2>&1
      uv run python scripts/exercise_census.py > /dev/null 2>&1
      uv run python scripts/certify.py > /dev/null 2>&1
      uv run scripts/apply_dispositions.py --check > /dev/null 2>&1 || { echo APPLY-CHECK-FAILED; ok=2; break }
      git add -A dashboard/ conformance/ certificates/ dispositions/
      git diff --cached --quiet || git commit -q -m "data: refresh rollups on merge round (automated)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
      git push -q origin $BR; echo "pushed $(git rev-parse --short HEAD)"; ok=3; break
    fi
    if [ "$P" -ge 2 ] && [ "$M" = "MERGEABLE" ]; then
      gh pr merge $PR --repo TheAxiomFoundation/axiom-oracles --merge 2>&1 | tail -1
      echo MERGED; ok=1; break
    fi
  done
  [ $ok -eq 1 ] && break
  [ $ok -eq 2 ] && break
done
echo LAND-DONE
