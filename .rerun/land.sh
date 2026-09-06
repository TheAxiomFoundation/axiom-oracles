#!/bin/zsh
cd /Users/maxghenis/TheAxiomFoundation/axiom-oracles/.claude/worktrees/amazing-zhukovsky-51fce0
for attempt in 1 2 3 4; do
  echo "=== attempt $attempt: waiting for quiet main"
  last=$(git ls-remote origin main | cut -f1)
  quiet=0
  while [ $quiet -lt 15 ]; do
    sleep 60
    cur=$(git ls-remote origin main | cut -f1)
    if [ "$cur" = "$last" ]; then quiet=$((quiet+1)); else last=$cur; quiet=0; echo "main moved -> $cur"; fi
  done
  echo "=== quiet window; running round"
  ./.rerun/round.sh || { echo ROUND-FAILED; continue }
  echo "=== waiting for CI"
  ok=0
  for i in $(seq 1 35); do
    sleep 60
    P=$(gh pr checks 474 --repo TheAxiomFoundation/axiom-oracles 2>/dev/null | grep -c pass)
    F=$(gh pr checks 474 --repo TheAxiomFoundation/axiom-oracles 2>/dev/null | grep -c fail)
    M=$(gh pr view 474 --repo TheAxiomFoundation/axiom-oracles --json mergeable --jq .mergeable 2>/dev/null)
    echo "tick $i pass=$P fail=$F mergeable=$M"
    [ "$F" != "0" ] && { echo CI-FAILED; ok=2; break }
    [ "$M" = "CONFLICTING" ] && { echo CONFLICTED; ok=3; break }
    if [ "$P" -ge 2 ] && [ "$M" = "MERGEABLE" ]; then
      gh pr merge 474 --repo TheAxiomFoundation/axiom-oracles --merge 2>&1 | tail -1
      echo MERGED; ok=1; break
    fi
  done
  [ $ok -eq 1 ] && break
  [ $ok -eq 2 ] && break
done
echo LAND-DONE
