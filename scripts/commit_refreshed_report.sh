#!/usr/bin/env bash
# Commit a refreshed comparison report atomically with every artifact derived
# from it, retrying against concurrent sibling pushes.
#
# Refreshing a dashboard/public/data/*.json report changes the inputs of
# derived, CI-validated artifacts:
#
#   dispositioned reports (dispositions merged)     apply_dispositions.py
#   DE served dispositions/case chunks               emit_*_artifacts.py
#   DE pinned Axiom comparison legs                  de_axiom_legs.py
#   comparison registry dependency map                generate_affected_map.py
#   DE worker unified comparison record              de_unified_comparison.py
#   DE exact-citation closure summary                 de_closure.py
#   DE Kindergeld executable status                  de_executable.py
#   DE certificate-candidate census                  de_certificate_census.py
#   NZ IncomeExplorer unified record                 nz_incomeexplorer.py
#   NZ bound case chunks + trace-derived view receipts nz_incomeexplorer.py
#   NZ single-person attestations                    nz_incomeexplorer.py
#   NZ closure + bound instrument frontier           nz_closure.py
#   axiom_oracles/data/euromod_be_coverage.json      …same (BE parity rollup)
#   conformance/scoreboard.json + conformance/detail/<jur>.json
#     (+ their dashboard/public/data mirrors)      conformance_scoreboard.py
#   conformance/history/<jur>/<YYYY-MM-DD>.json    …with --snapshot (per-day)
#   dashboard/public/data/conformance_burndown.json  conformance_burndown.py
#   dashboard/public/data/cases/*/index.json         generate_chunk_indexes.py
#   conformance/exercise-census.json               exercise_census.py
#   certificates/*.json                            certify.py
#   V3-AUDIT-OUT.md                                nz_v3_audit_report.py
#   dashboard/public/data/freshness.json             check_vacuous_gate.py
#
# Pushing a refreshed report without regenerating these turns main red at CI's
# "Validate conformance scoreboard is up to date" step (2026-07-14: the
# il/ky/oh/va refreshes changed dispositioned rates and redded main until #282
# regenerated conformance/detail/us-pe.json by hand). This script makes that
# state unpushable: every push attempt rebuilds the commit FROM SCRATCH on the
# current remote tip — restore this run's PRIVATE comparison outputs (the
# refreshed report files), replay this run's manifest.json additions, then
# regenerate every derived artifact and verify the tree passes the same
# staleness gates ci.yml runs before pushing. Sibling matrix jobs pushing
# between attempts can therefore never cause a conflict (nothing is ever
# rebased) nor an inconsistent tree (derivations are recomputed on whatever
# tip won the race).
#
# Only leg-PRIVATE outputs are ever restored across attempts. Shared or
# derived files are not: restoring a stale copy of the shared, append-only
# dashboard/public/data/manifest.json would drop a sibling's entry (so the
# leg's manifest ADDITIONS are re-applied per attempt instead), and restoring
# stale derived artifacts (freshness, scoreboard/detail, history snapshots,
# burn-down, the BE rollup) could resurrect a prior day's snapshot across a
# UTC rollover or clobber a sibling's regeneration — they are recomputed from
# the fresh tip on every attempt, never copied.
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
#        MAX_ATTEMPTS      push attempts before failing loudly     (60)
#        PUSH_RETRY_DELAY  seconds between attempts (default: growing + jitter)

set -euo pipefail

suite="${1:?usage: commit_refreshed_report.sh <suite-name> <branch>}"
branch="${2:?usage: commit_refreshed_report.sh <suite-name> <branch>}"
PYTHON="${PYTHON:-python3}"
# 60 attempts, not 20: with 40+ sibling legs each pushing within the same
# sweep, a leg's vulnerable window (fetch → regenerate → push) is comparable
# to the herd's inter-push gap, and legs that had completed their comparison
# were observed losing 20 straight races (#337). The affected-rerun job
# timeout still bounds the loop.
MAX_ATTEMPTS="${MAX_ATTEMPTS:-60}"

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Direct ``python scripts/foo.py`` execution puts ``scripts/`` rather than the
# checkout root on sys.path. Production often masks that because the package is
# installed in the uv environment, but the bot's hermetic clone test (and any
# minimally provisioned runner) must still execute the same refresh chain.
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"

# Every tree holding a report or report-derived artifact this script may
# refresh, regenerate, and commit. The EUROMOD-BE coverage rollup lives
# outside the two data trees, so it is listed explicitly.
#
# certificates/ MUST be here. It was omitted when census+certify were first
# wired in, and the failure was silent in the worst way: certify.py wrote the
# corrected certificate, verify_derived confirmed it in the worktree, and then
# `git add -- "${derived_paths[@]}"` skipped it — so the bot pushed a STALE
# certificate with every command exiting 0. set -e cannot see that class of
# bug. Anything a regenerate_derived step writes belongs in this list.
derived_paths=(
  dashboard/public/data/
  conformance/
  certificates/
  closure/de/summary.json
  closure/nz/summary.json
  comparisons/de-worker-dual-oracle/
  comparisons/affected_map.json
  comparisons/nz-treasury-incomeexplorer/single-person-attestations.json
  axiom_oracles/data/euromod_be_coverage.json
  V3-AUDIT-OUT.md
)
manifest="dashboard/public/data/manifest.json"

# Bot identity, only where none is configured (CI runners have none).
git config user.name >/dev/null 2>&1 ||
  git config user.name "github-actions[bot]"
git config user.email >/dev/null 2>&1 ||
  git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

regenerate_derived() {
  # Registry-derived affected-run metadata is cheap and hermetic. Keep it in
  # the same write/check/stage transaction as reports so a newly registered
  # pair leg can never be committed without becoming selectable.
  "$PYTHON" scripts/generate_affected_map.py
  # Rebuild the NZ unified tuple record, bound verdict chunks, trace-derived
  # exercise views, executable receipt binding, and closure census before
  # their downstream disposition, exercise, and certificate consumers. The
  # closure producer also validates and byte-binds the committed subordinate-
  # instrument graph and its dispositions; this refresh path deliberately
  # never invokes the network capture script. All generators pin and validate
  # their source inputs before writing. The existence checks preserve the
  # refresh script's small hermetic test seeds and old release branches that
  # predate the NZ inputs.
  if [ -f comparisons/nz-treasury-incomeexplorer/source-comparison.json ]; then
    "$PYTHON" scripts/nz_incomeexplorer.py
  fi
  if [ -f conformance/executable/nz-treasury-incomeexplorer.json ]; then
    "$PYTHON" scripts/nz_executable_reproduction.py --refresh-receipt
  fi
  if [ -f closure/nz/source.json ]; then
    "$PYTHON" scripts/nz_closure.py
  fi
  # Dispositions merge + the EUROMOD-BE coverage rollup
  # (axiom_oracles/data/euromod_be_coverage.json). run_comparison.py merges
  # dispositions into the reports it writes, but the rollup is maintained ONLY
  # here, aggregates every be-* report, and BE suites are in the bot matrix —
  # skipping this leaves the rollup stale and reds ci.yml's
  # apply_dispositions.py --check gate. Runs FIRST because it rewrites report
  # bytes that freshness and the scoreboard then read. A non-zero exit is a
  # dispositions schema problem (nothing was written) — not derivation lag —
  # so under `set -e` the refresh aborts loudly with nothing pushed.
  "$PYTHON" scripts/apply_dispositions.py
  # The DE report has a public case explorer and a public disposition mirror.
  # Both are generated from the just-rewritten canonical
  # report/YAML, so refresh them before downstream DE certification artifacts
  # cite the report. Without these two writes the affected-rerun bot can push a
  # report whose served claims still carry the prior dispositions.
  if [ -f dashboard/public/data/euromod-gettsim-de-worker-dual-oracle.json ]; then
    if [ -f scripts/emit_disposition_artifacts.py ]; then
      "$PYTHON" scripts/emit_disposition_artifacts.py de-worker-dual-oracle
    fi
    if [ -f scripts/emit_case_artifacts.py ]; then
      "$PYTHON" scripts/emit_case_artifacts.py de-worker-dual-oracle
    fi
  fi
  # DE certification chain. The two pinned Axiom pair records inspect the
  # configured RuleSpec-DE ref first, emitting explicit module-not-on-main
  # pending records until EStG 66 is signed there. The unified record MUST
  # follow those legs and disposition application because its source report is
  # rewritten above. Closure and executable status then precede the census,
  # which aligns exact root declarations with the freshly computed input
  # states. Certificates run later, after the shared exercise census is
  # current. Guards retain compatibility with small hermetic fixtures and
  # release branches that predate the DE lane.
  if [ -f dashboard/public/data/euromod-gettsim-de-worker-dual-oracle.json ] &&
    [ -f scripts/de_axiom_legs.py ]; then
    "$PYTHON" scripts/de_axiom_legs.py
  fi
  if [ -f dashboard/public/data/euromod-gettsim-de-worker-dual-oracle.json ] &&
    [ -f scripts/de_unified_comparison.py ]; then
    "$PYTHON" scripts/de_unified_comparison.py
  fi
  if [ -f closure/de/source.json ] && [ -f scripts/de_closure.py ]; then
    "$PYTHON" scripts/de_closure.py
  fi
  if [ -f conformance/executable/de-kindergeld-manifest.json ] &&
    [ -f scripts/de_executable.py ]; then
    "$PYTHON" scripts/de_executable.py
  fi
  if [ -f comparisons/de-worker-dual-oracle/unified-record.json ] &&
    [ -f closure/de/source.json ] && [ -f scripts/de_certificate_census.py ]; then
    "$PYTHON" scripts/de_certificate_census.py
  fi
  # Certified per-case chunks are refreshed and bound by run_comparison while
  # it still holds the full case corpus. Here the generator validates that
  # identity (or performs an initial legacy migration); it refuses to rebind
  # changed report/chunk identities, so stale/foreign chunks cannot inherit a
  # new report.
  "$PYTHON" scripts/generate_chunk_indexes.py
  # Freshness register. Write mode exits 1 when a registry config has a schema
  # problem but STILL writes freshness.json — that is a content alarm for
  # verify_derived's --check (the same arbiter ci.yml uses) to rule on, not a
  # reason to drop this refresh here. Any other exit means freshness.json may
  # not have been rewritten — abort instead.
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
  # Front-page single-fetch bundle (every report minus per-case rows).
  "$PYTHON" scripts/generate_dashboard_overview.py
  # Exercise census and program certificates. Both read report bytes and
  # per-case chunks, so a refresh moves them; without regenerating here the
  # bot would push a tree whose census/certificate --check gates are red on
  # main. Census runs first — certify consumes it.
  "$PYTHON" scripts/exercise_census.py
  "$PYTHON" scripts/certify.py
  if [ -f scripts/nz_v3_audit_report.py ]; then
    "$PYTHON" scripts/nz_v3_audit_report.py
  fi
}

verify_derived() {
  # The staleness gates ci.yml runs on main, verbatim; a tree that fails any
  # of them must never be pushed. nz_closure.py --check includes exact-byte
  # verification of the committed instrument graph and complete disposition
  # coverage, without a network retrieval. conformance_ratchet.py --check is
  # intentionally absent — see the header. Explicitly &&-chained: this
  # function is also called in an if-condition (the fast no-op path), where
  # errexit is suppressed and bare lines would reduce the verdict to the LAST
  # gate's status, silently ignoring an earlier stale gate.
  #
  # validate_bridge_manifests.py is absent deliberately: it does not derive an
  # artifact, so it cannot go stale from a refresh. Its errors are authoring
  # mistakes for ci.yml to catch on the PR that makes them, not a reason to
  # drop a data refresh.
  "$PYTHON" scripts/generate_affected_map.py --check || return
  if [ -f comparisons/nz-treasury-incomeexplorer/source-comparison.json ]; then
    "$PYTHON" scripts/nz_incomeexplorer.py --check || return
  fi
  if [ -f conformance/executable/nz-treasury-incomeexplorer.json ]; then
    "$PYTHON" scripts/nz_executable_reproduction.py --check || return
    "$PYTHON" scripts/nz_exercise_denominator.py --check || return
  fi
  if [ -f closure/nz/source.json ]; then
    "$PYTHON" scripts/nz_closure.py \
      --bootstrap-instrument-dispositions --check || return
    "$PYTHON" scripts/nz_closure.py \
      --bootstrap-dependency-dispositions --check || return
    "$PYTHON" scripts/nz_closure.py --check || return
  fi
  "$PYTHON" scripts/apply_dispositions.py --check || return
  if [ -f dashboard/public/data/euromod-gettsim-de-worker-dual-oracle.json ]; then
    if [ -f scripts/emit_disposition_artifacts.py ]; then
      "$PYTHON" scripts/emit_disposition_artifacts.py --check \
        de-worker-dual-oracle || return
    fi
    if [ -f scripts/emit_case_artifacts.py ]; then
      "$PYTHON" scripts/emit_case_artifacts.py --check \
        de-worker-dual-oracle || return
    fi
  fi
  if [ -f dashboard/public/data/euromod-gettsim-de-worker-dual-oracle.json ] &&
    [ -f scripts/de_axiom_legs.py ]; then
    "$PYTHON" scripts/de_axiom_legs.py --check || return
  fi
  if [ -f dashboard/public/data/euromod-gettsim-de-worker-dual-oracle.json ] &&
    [ -f scripts/de_unified_comparison.py ]; then
    "$PYTHON" scripts/de_unified_comparison.py --check || return
  fi
  if [ -f closure/de/source.json ] && [ -f scripts/de_closure.py ]; then
    "$PYTHON" scripts/de_closure.py --check || return
  fi
  if [ -f conformance/executable/de-kindergeld-manifest.json ] &&
    [ -f scripts/de_executable.py ]; then
    "$PYTHON" scripts/de_executable.py --check || return
  fi
  if [ -f comparisons/de-worker-dual-oracle/unified-record.json ] &&
    [ -f closure/de/source.json ] && [ -f scripts/de_certificate_census.py ]; then
    "$PYTHON" scripts/de_certificate_census.py --check || return
  fi
  "$PYTHON" scripts/generate_chunk_indexes.py --check &&
    "$PYTHON" scripts/check_vacuous_gate.py --check &&
    "$PYTHON" scripts/conformance_scoreboard.py --check &&
    "$PYTHON" scripts/conformance_burndown.py --check &&
    "$PYTHON" scripts/generate_dashboard_overview.py --check &&
    "$PYTHON" scripts/exercise_census.py --check &&
    "$PYTHON" scripts/certify.py --check &&
    { [ ! -f scripts/nz_v3_audit_report.py ] ||
      "$PYTHON" scripts/nz_v3_audit_report.py --check; }
}

# Safe proof of the exact regeneration path. It exits before collecting
# private report output, fetching, resetting, committing, or pushing.
if [ "${SIMULATE_DERIVED_REFRESH:-0}" = "1" ]; then
  regenerate_derived
  verify_derived
  "$PYTHON" scripts/unexplained_ratchet.py --check
  echo "simulated derived refresh passed for $suite"
  exit 0
fi

# Collect this run's PRIVATE outputs — what run_comparison.py itself wrote
# (the refreshed report + any fixture reports), BEFORE any regeneration, so
# nothing derived or shared ever enters the restore set. NUL-safe, and it
# catches brand-new untracked files too: the first report of a new suite is
# untracked, and `git diff` alone would silently drop it.
private=()   # changed paths that exist in the worktree
deletions=() # paths the refresh deleted (rare; handled for completeness)
while IFS= read -r -d '' path; do
  [ "$path" = "$manifest" ] && continue # shared; additions replayed instead
  if [ -e "$path" ]; then private+=("$path"); else deletions+=("$path"); fi
done < <(git diff HEAD --name-only -z -- "${derived_paths[@]}")
while IFS= read -r -d '' path; do
  # The manifest is shared even when brand-new (HEAD without one): restoring
  # it verbatim would drop a racing sibling's entry, so it is excluded here
  # too and its additions replayed instead.
  [ "$path" = "$manifest" ] && continue
  private+=("$path")
done < <(git ls-files --others --exclude-standard -z -- "${derived_paths[@]}")

# Record the manifest entries this run ADDED (run_comparison.py appends its
# report filename). They are re-applied onto whatever tip wins each attempt —
# the shared file itself is never restored, so a stale copy can't drop a
# sibling's concurrently-added entry.
stash="$(mktemp -d)"
trap 'rm -rf "$stash"' EXIT
manifest_added="$stash/manifest-added.json"
"$PYTHON" - "$manifest" "$manifest_added" <<'PY'
import json, subprocess, sys
from pathlib import Path

manifest, out = sys.argv[1], sys.argv[2]
try:
    now = json.loads(Path(manifest).read_text()).get("reports", [])
except FileNotFoundError:
    now = []
show = subprocess.run(
    ["git", "show", f"HEAD:{manifest}"], capture_output=True, text=True
)
committed = (
    json.loads(show.stdout).get("reports", []) if show.returncode == 0 else []
)
Path(out).write_text(json.dumps([r for r in now if r not in committed]))
PY

for path in ${private[@]+"${private[@]}"}; do
  mkdir -p "$stash/$(dirname "$path")"
  cp -p "$path" "$stash/$path"
done

# Fast no-op path: nothing private changed and the checked-out tree already
# passes every gate — nothing to heal, nothing to push.
if [ "${#private[@]}" -eq 0 ] && [ "${#deletions[@]}" -eq 0 ] &&
  [ "$(cat "$manifest_added")" = "[]" ] && verify_derived >/dev/null 2>&1; then
  echo "no report or derived-artifact changes for $suite"
  exit 0
fi

push_landed=""
for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  # Rebuild from scratch on the current remote tip (fetch + hard reset; never
  # rebase). git clean keeps the generated trees hermetic across attempts.
  git fetch origin "$branch"
  git reset --hard FETCH_HEAD --quiet
  git clean -fdq -- "${derived_paths[@]}"

  for path in ${private[@]+"${private[@]}"}; do
    mkdir -p "$(dirname "$path")"
    cp -p "$stash/$path" "$path"
  done
  for path in ${deletions[@]+"${deletions[@]}"}; do
    rm -f "$path"
  done

  # Replay this run's manifest additions onto the tip's manifest (append-only
  # union, same serialization run_comparison.py writes).
  "$PYTHON" - "$manifest" "$manifest_added" <<'PY'
import json, sys
from pathlib import Path

manifest, added_path = Path(sys.argv[1]), Path(sys.argv[2])
added = json.loads(added_path.read_text())
if added:
    doc = (
        json.loads(manifest.read_text())
        if manifest.exists()
        else {"reports": []}
    )
    reports = doc.setdefault("reports", [])
    changed = False
    for entry in added:
        if entry not in reports:
            reports.append(entry)
            changed = True
    if changed:
        manifest.write_text(json.dumps(doc, indent=2) + "\n")
PY

  # Recompute every derived artifact against THIS tip, then refuse to push
  # anything ci.yml would call stale.
  regenerate_derived
  verify_derived

  # Publication gate — unlike the conformance ratchet (an alarm that fires on
  # main AFTER an honest regression lands), the per-suite unexplained ratchet
  # stops the regression from publishing at all: a rerun that surfaces NEW
  # unexplained disagreements leaves the previous, fully-accounted-for report
  # live until someone triages (dispositions/<suite>.yaml or the known-causes
  # registry). Retrying cannot help — a regression is not contention — so
  # fail the leg loudly instead of looping.
  if ! "$PYTHON" scripts/unexplained_ratchet.py --check; then
    echo "REFUSED: this refresh raises an unexplained-mismatch ceiling" \
      "(conformance/unexplained-ratchet.yaml). Triage the new" \
      "disagreements, then rerun; the previous report stays published." >&2
    exit 1
  fi

  git add -A -- "${derived_paths[@]}"
  if git diff --cached --quiet; then
    echo "nothing to commit for $suite after regeneration (attempt $attempt)"
    exit 0
  fi
  git commit --quiet \
    -m "data: refresh $suite (affected rerun $(date -u +%Y-%m-%d))" \
    -m "Includes the regenerated derived conformance artifacts (dispositioned
reports + EUROMOD-BE coverage rollup, DE unified/closure/census/executable
status, scoreboard, detail, daily history snapshot, burn-down, freshness) so
main CI's staleness gates stay green.
Committed by scripts/commit_refreshed_report.sh; the ratchet is never
re-pinned here."

  if git push origin "HEAD:$branch"; then
    push_landed=1
    break
  fi
  echo "push rejected (attempt $attempt/$MAX_ATTEMPTS): a sibling job" \
    "advanced $branch; rebuilding on the new tip" >&2
  # Growing delay with wide jitter to decorrelate the herd — synchronized
  # retries were losing to each other far more than a Poisson model predicts.
  sleep "${PUSH_RETRY_DELAY:-$((attempt * 4 + RANDOM % 25))}"
done

if [ -z "$push_landed" ]; then
  echo "FAILED: could not push the $suite refresh after $MAX_ATTEMPTS" \
    "attempts; the refresh was NOT committed" >&2
  exit 1
fi
echo "pushed $suite refresh + derived conformance artifacts to $branch"
