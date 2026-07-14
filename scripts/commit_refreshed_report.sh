#!/usr/bin/env bash
# Commit a refreshed comparison report atomically with every artifact derived
# from it, retrying against concurrent sibling pushes.
#
# Refreshing a dashboard/public/data/*.json report changes the inputs of
# derived, CI-validated artifacts:
#
#   conformance/scoreboard.json + conformance/detail/<jur>.json
#     (+ their dashboard/public/data mirrors)      conformance_scoreboard.py
#   conformance/history/<jur>/<YYYY-MM-DD>.json    …with --snapshot (per-day)
#   dashboard/public/data/conformance_burndown.json  conformance_burndown.py
#   dashboard/public/data/freshness.json             check_vacuous_gate.py
#
# Pushing a refreshed report without regenerating these turns main red at CI's
# "Validate conformance scoreboard is up to date" step (2026-07-14: the
# il/ky/oh/va refreshes changed dispositioned rates and redded main until #282
# regenerated conformance/detail/us-pe.json by hand). This script makes that
# state unpushable: every push attempt rebuilds the commit FROM SCRATCH on the
# current remote tip — restore this run's refreshed files, regenerate every
# derived artifact, verify the tree passes the same staleness gates ci.yml
# runs, then push. Sibling matrix jobs pushing between attempts can therefore
# never cause a conflict (nothing is ever rebased — siblings commit the SAME
# derived files, so replaying a stale local commit would collide) nor an
# inconsistent tree (derivations are recomputed on whatever tip won the race).
#
# The conformance RATCHET (conformance/ratchet.yaml) is deliberately NOT
# re-pinned here: floors tighten only via a deliberate human run of
# scripts/conformance_ratchet.py after a genuine improvement, and a transient
# rerun improvement must not silently raise a floor the next honest run would
# fail. Conversely, if a rerun genuinely regresses an invariant, ci.yml's
# ratchet gate failing on main IS the alarm working as designed — this script
# keeps mechanical staleness out of CI; it must not muffle real regressions.
#
# Usage: scripts/commit_refreshed_report.sh <suite-name> <branch>
# Env:   PYTHON            interpreter for the regeneration scripts (python3)
#        MAX_ATTEMPTS      push attempts before failing loudly     (20)
#        PUSH_RETRY_DELAY  seconds between attempts (default: growing + jitter)

set -euo pipefail

suite="${1:?usage: commit_refreshed_report.sh <suite-name> <branch>}"
branch="${2:?usage: commit_refreshed_report.sh <suite-name> <branch>}"
PYTHON="${PYTHON:-python3}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-20}"

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Bot identity, only where none is configured (CI runners have none).
git config user.name >/dev/null 2>&1 ||
  git config user.name "github-actions[bot]"
git config user.email >/dev/null 2>&1 ||
  git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

regenerate_derived() {
  # Freshness register. Write mode exits 1 when a registry config has a schema
  # problem but STILL writes freshness.json — that is a content alarm for CI to
  # raise, not a reason to drop this refresh. Any other exit means
  # freshness.json may not have been rewritten, so pushing could commit a stale
  # freshness artifact — abort instead.
  local rc=0
  "$PYTHON" scripts/check_vacuous_gate.py || rc=$?
  if [ "$rc" -ne 0 ] && [ "$rc" -ne 1 ]; then
    echo "check_vacuous_gate.py failed (exit $rc); refusing to push a" \
      "possibly-stale freshness.json" >&2
    return "$rc"
  fi
  # Scoreboard + per-jurisdiction detail (+ dashboard mirrors), today's dated
  # history snapshot (idempotent per day), and the burn-down series derived
  # from that history.
  "$PYTHON" scripts/conformance_scoreboard.py --snapshot
  "$PYTHON" scripts/conformance_burndown.py
}

verify_derived() {
  # The exact staleness gates ci.yml runs on main; a tree that fails them must
  # never be pushed. check_vacuous_gate.py --check is structurally covered
  # (freshness was regenerated from this same tree just above) but conflates
  # drift with registry schema problems, and conformance_ratchet.py --check is
  # intentionally absent — see the header.
  "$PYTHON" scripts/conformance_scoreboard.py --check
  "$PYTHON" scripts/conformance_burndown.py --check
}

# Self-heal + refresh pass on the tree as checked out: regenerate every derived
# artifact so (a) this run's report refresh is joined by its derivations below,
# and (b) staleness already sitting on the branch (e.g. left by a rerun that
# predates this script) converges back to green on the next rerun instead of
# needing a manual regeneration PR like #282.
regenerate_derived

# Collect this run's changed paths — the retry loop's only inputs. NUL-safe,
# and it catches brand-new untracked files too: the first report of a new
# suite and today's first history snapshot are untracked, and `git diff`
# alone would silently drop them.
inputs=()    # changed paths that exist in the worktree
deletions=() # paths the refresh deleted (rare; handled for completeness)
while IFS= read -r -d '' path; do
  if [ -e "$path" ]; then inputs+=("$path"); else deletions+=("$path"); fi
done < <(git diff HEAD --name-only -z -- dashboard/public/data/ conformance/)
while IFS= read -r -d '' path; do
  inputs+=("$path")
done < <(git ls-files --others --exclude-standard -z -- \
  dashboard/public/data/ conformance/)

if [ "${#inputs[@]}" -eq 0 ] && [ "${#deletions[@]}" -eq 0 ]; then
  echo "no report or derived-artifact changes for $suite"
  exit 0
fi

stash="$(mktemp -d)"
trap 'rm -rf "$stash"' EXIT
for path in ${inputs[@]+"${inputs[@]}"}; do
  mkdir -p "$stash/$(dirname "$path")"
  cp -p "$path" "$stash/$path"
done

push_landed=""
for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  # Rebuild from scratch on the current remote tip (fetch + hard reset; never
  # rebase). git clean keeps the two generated trees hermetic across attempts.
  git fetch origin "$branch"
  git reset --hard FETCH_HEAD --quiet
  git clean -fdq -- dashboard/public/data/ conformance/

  for path in ${inputs[@]+"${inputs[@]}"}; do
    mkdir -p "$(dirname "$path")"
    cp -p "$stash/$path" "$path"
  done
  for path in ${deletions[@]+"${deletions[@]}"}; do
    rm -f "$path"
  done

  # Recompute every derived artifact against THIS tip (restored copies of
  # derived files are stale the moment a sibling's push wins — overwrite them),
  # then refuse to push anything ci.yml would call stale.
  regenerate_derived
  verify_derived

  git add -A -- dashboard/public/data/ conformance/
  if git diff --cached --quiet; then
    echo "nothing to commit for $suite after regeneration (attempt $attempt)"
    exit 0
  fi
  git commit --quiet \
    -m "data: refresh $suite (affected rerun $(date -u +%Y-%m-%d))" \
    -m "Includes the regenerated derived conformance artifacts (scoreboard,
detail, daily history snapshot, burn-down, freshness) so main CI's
staleness gates stay green. Committed by
scripts/commit_refreshed_report.sh; the ratchet is never re-pinned here."

  if git push origin "HEAD:$branch"; then
    push_landed=1
    break
  fi
  echo "push rejected (attempt $attempt/$MAX_ATTEMPTS): a sibling job" \
    "advanced $branch; rebuilding on the new tip" >&2
  sleep "${PUSH_RETRY_DELAY:-$((attempt * 3 + RANDOM % 10))}"
done

if [ -z "$push_landed" ]; then
  echo "FAILED: could not push the $suite refresh after $MAX_ATTEMPTS" \
    "attempts; the refresh was NOT committed" >&2
  exit 1
fi
echo "pushed $suite refresh + derived conformance artifacts to $branch"
