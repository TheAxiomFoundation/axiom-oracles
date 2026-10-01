#!/usr/bin/env bash
# Commit refreshed comparison reports atomically with every artifact derived
# from them: vet each suite's refresh where it ran (pack), then commit every
# vetted refresh from one job (publish), retrying only a rejected push.
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
#   NZ closure census                                nz_closure.py
#   axiom_oracles/data/euromod_be_coverage.json      …same (BE parity rollup)
#   conformance/scoreboard.json + conformance/detail/<jur>.json
#     (+ their dashboard/public/data mirrors)      conformance_scoreboard.py
#   conformance/history/<jur>/<YYYY-MM-DD>.json    …with --snapshot (per-day)
#   dashboard/public/data/conformance_burndown.json  conformance_burndown.py
#   dashboard/public/data/cases/*/index.json         generate_chunk_indexes.py
#   conformance/exercise-census.json               exercise_census.py
#   certificates/*.json                            certify.py
#   dashboard/public/data/freshness.json             check_vacuous_gate.py
#
# Pushing a refreshed report without regenerating these turns main red at CI's
# "Validate conformance scoreboard is up to date" step (2026-07-14: the
# il/ky/oh/va refreshes changed dispositioned rates and redded main until #282
# regenerated conformance/detail/us-pe.json by hand). This script makes that
# state unpushable: every push attempt rebuilds the commit FROM SCRATCH on the
# current remote tip — restore each refresh's PRIVATE comparison outputs (the
# refreshed report files), replay its manifest.json additions, then regenerate
# every derived artifact and verify the tree passes the same staleness gates
# ci.yml runs before pushing. A push that loses a race can therefore never
# cause a conflict (nothing is ever rebased) nor an inconsistent tree
# (derivations are recomputed on whatever tip won the race).
#
# PACK, THEN PUBLISH ONCE. Until 2026-09-26 every affected-rerun matrix leg ran
# that push loop itself. Each attempt re-ran the whole derived regeneration
# (about 4 minutes) and then pushed, so with ~47 legs racing for main every
# successful push invalidated every other leg's attempt. Run 36239293795 lost
# 7 legs to the 90-minute job timeout inside the loop (az-snap-qc was on
# attempt 22/60), and run 35958364304 lost 11. The work is now split:
#
#   --pack <bundles-dir> <suite>
#       Runs in each leg, after its comparison. Collects the run's private
#       outputs, vets them ONCE on the leg's checkout (the re-emission guard,
#       regenerate + verify every derived artifact, the unexplained ratchet)
#       and writes a self-contained bundle to <bundles-dir>/<suite>/. Never
#       fetches, resets, commits or pushes. A refresh that fails the vet fails
#       its own leg loudly and packs nothing; nothing changed packs nothing.
#   --publish <bundles-dir> <branch>
#       Runs once, in one job. Every attempt rebuilds on the current remote
#       tip, applies EVERY bundle under <bundles-dir>, regenerates the derived
#       artifacts once for all of them, verifies, gates on the ratchet, and
#       makes ONE commit. Only a rejected push is retried, and contention now
#       comes only from other workflows or humans. Zero bundles is a no-op.
#   <suite> <branch>
#       Single suite (the original interface): pack into a temporary
#       directory, then publish that one bundle. Same two steps, one code
#       path; pack skips only its vet, which publish repeats at once.
#
# A bundle is a directory holding bundle.json (schema
# axiom_oracles.refreshed_report_bundle.v1: the suite, its private paths, its
# deletions, and its manifest additions) plus files/<path> for every private
# path. Publish reads the suite from bundle.json, never from the directory
# name, so a bundle survives any artifact rename.
#
# Only leg-PRIVATE outputs are ever restored across attempts. Shared or
# derived files are not: restoring a stale copy of the shared, append-only
# dashboard/public/data/manifest.json would drop another refresh's entry (so
# each bundle's manifest ADDITIONS are re-applied per attempt instead), and
# restoring stale derived artifacts (freshness, scoreboard/detail, history
# snapshots, burn-down, the BE rollup) could resurrect a prior day's snapshot
# across a UTC rollover or clobber a concurrent regeneration — they are
# recomputed from the fresh tip on every attempt, never copied.
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
#        scripts/commit_refreshed_report.sh --pack <bundles-dir> <suite-name>
#        scripts/commit_refreshed_report.sh --publish <bundles-dir> <branch>
# Env:   PYTHON            interpreter for the regeneration scripts (python3)
#        MAX_ATTEMPTS      push attempts before failing loudly     (10)
#        PUSH_RETRY_DELAY  seconds between attempts (default: growing + jitter)

set -euo pipefail

usage() {
  {
    echo "usage: commit_refreshed_report.sh <suite-name> <branch>"
    echo "       commit_refreshed_report.sh --pack <bundles-dir> <suite-name>"
    echo "       commit_refreshed_report.sh --publish <bundles-dir> <branch>"
  } >&2
  exit 2
}

# A bundles directory is given relative to the caller, before the cd below.
abspath() {
  case "$1" in
    /*) printf '%s\n' "$1" ;;
    *) printf '%s\n' "$PWD/$1" ;;
  esac
}

mode=single
suite=""
branch=""
bundles_dir=""
case "${1:-}" in
  --pack)
    [ "$#" -eq 3 ] || usage
    mode=pack
    bundles_dir="$(abspath "$2")"
    suite="$3"
    ;;
  --publish)
    [ "$#" -eq 3 ] || usage
    mode=publish
    bundles_dir="$(abspath "$2")"
    branch="$3"
    ;;
  "" | -*) usage ;;
  *)
    [ "$#" -eq 2 ] || usage
    suite="$1"
    branch="$2"
    ;;
esac
# The suite names a bundle directory.
case "$suite" in
  */* | . | ..) usage ;;
esac
[ "$mode" = publish ] || [ -n "$suite" ] || usage
[ "$mode" = pack ] || [ -n "$branch" ] || usage

PYTHON="${PYTHON:-python3}"
# 10, not the old per-leg 60: one publisher no longer races 40+ siblings, so
# the only contention left is another workflow or a human pushing to the
# branch, and one or two attempts is the normal case. Every attempt still
# rebuilds from scratch, so a lost race costs one regeneration, not a
# conflict.
MAX_ATTEMPTS="${MAX_ATTEMPTS:-10}"

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Direct ``python scripts/foo.py`` execution puts ``scripts/`` rather than the
# checkout root on sys.path. Production often masks that because the package is
# installed in the uv environment, but the bot's hermetic clone test (and any
# minimally provisioned runner) must still execute the same refresh chain.
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"

# Bundles never live inside the checkout: publish's `git clean` would delete
# them, and pack would collect a bundle under a derived path as a private
# output of the next run.
case "$bundles_dir/" in
  "$PWD"/*)
    echo "bundles directory $bundles_dir is inside the checkout; use a" \
      "directory outside it (e.g. \$RUNNER_TEMP/refreshed)" >&2
    exit 2
    ;;
esac

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
)
manifest="dashboard/public/data/manifest.json"

regenerate_derived() {
  # Registry-derived affected-run metadata is cheap and hermetic. Keep it in
  # the same write/check/stage transaction as reports so a newly registered
  # pair leg can never be committed without becoming selectable.
  "$PYTHON" scripts/generate_affected_map.py
  # Rebuild the NZ unified tuple record, bound verdict chunks, trace-derived
  # exercise views, executable receipt binding, and closure census before
  # their downstream disposition, exercise, and certificate consumers. All
  # generators pin and validate their source inputs before writing. The
  # existence checks preserve the refresh script's small hermetic test seeds
  # and old release branches that predate the NZ inputs.
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
}

verify_derived() {
  # The staleness gates ci.yml runs on main, verbatim; a tree that fails any
  # of them must never be pushed. conformance_ratchet.py --check is
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
    "$PYTHON" scripts/certify.py --check
}

# Safe proof of the exact regeneration path. It exits before collecting
# private report output, fetching, resetting, committing, or pushing.
if [ "${SIMULATE_DERIVED_REFRESH:-0}" = "1" ]; then
  regenerate_derived
  verify_derived
  "$PYTHON" scripts/unexplained_ratchet.py --check
  echo "simulated derived refresh passed${suite:+ for $suite}"
  exit 0
fi

cleanup_dirs=()
cleanup() {
  if [ "${#cleanup_dirs[@]}" -gt 0 ]; then
    rm -rf "${cleanup_dirs[@]}"
  fi
}
trap cleanup EXIT

BUNDLE_SCHEMA="axiom_oracles.refreshed_report_bundle.v1"

# pack <bundles-dir> <suite> [vet]: collect, vet, and bundle this checkout's
# refresh. vet=0 skips only the vet, for the single-suite mode below.
pack() {
  local out="$1" name="$2" vet="${3:-1}" path staging

  # Collect this run's PRIVATE outputs — what run_comparison.py itself wrote
  # (the refreshed report + any fixture reports), BEFORE any regeneration, so
  # nothing derived or shared ever enters the bundle. NUL-safe, and it
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
    # it verbatim would drop another refresh's entry, so it is excluded here
    # too and its additions replayed instead.
    [ "$path" = "$manifest" ] && continue
    private+=("$path")
  done < <(git ls-files --others --exclude-standard -z -- "${derived_paths[@]}")

  mkdir -p "$out"
  # Staged next to its final name so the bundle appears atomically (rename),
  # and dot-named so publish never mistakes a half-written one for a bundle.
  staging="$(mktemp -d "$out/.pack.XXXXXX")"
  cleanup_dirs+=("$staging")

  # The bundle's copies of the private outputs, taken before anything below
  # can rewrite them.
  for path in ${private[@]+"${private[@]}"}; do
    mkdir -p "$staging/files/$(dirname "$path")"
    cp -p "$path" "$staging/files/$path"
  done

  # Record the manifest entries this run ADDED (run_comparison.py appends its
  # report filename) and the bundle's index. Publish re-applies the additions
  # onto whatever tip wins each attempt — the shared file itself is never
  # restored, so a stale copy can't drop a concurrently-added entry.
  "$PYTHON" - "$manifest" "$staging/bundle.json" "$BUNDLE_SCHEMA" "$name" \
    ${private[@]+"${private[@]}"} -- ${deletions[@]+"${deletions[@]}"} <<'PY'
import json, subprocess, sys
from pathlib import Path

manifest, out, schema, suite, *rest = sys.argv[1:]
split = rest.index("--")
private, deletions = rest[:split], rest[split + 1 :]
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
Path(out).write_text(
    json.dumps(
        {
            "schema": schema,
            "suite": suite,
            "private": private,
            "deletions": deletions,
            "manifest_added": [r for r in now if r not in committed],
        },
        indent=2,
    )
    + "\n"
)
PY

  # Fast no-op path: nothing private changed and the checked-out tree already
  # passes every gate — nothing to heal, nothing to publish, no bundle.
  if [ "${#private[@]}" -eq 0 ] && [ "${#deletions[@]}" -eq 0 ] &&
    "$PYTHON" -c 'import json, sys; sys.exit(bool(json.load(open(sys.argv[1]))["manifest_added"]))' \
      "$staging/bundle.json" &&
    verify_derived >/dev/null 2>&1; then
    echo "no report or derived-artifact changes for $name"
    return 0
  fi

  # Vet ONCE, here, on the checkout the comparison ran against, with the same
  # steps publish runs on every attempt: a refresh that could never publish
  # fails its own leg instead of the shared publish job. The re-emission
  # guard runs first, so the gates judge what publish would commit.
  if [ "$vet" = 1 ]; then
    "$PYTHON" scripts/guard_reemitted_reports.py
    regenerate_derived
    verify_derived
    # Publication gate — unlike the conformance ratchet (an alarm that fires
    # on main AFTER an honest regression lands), the per-suite unexplained
    # ratchet stops the regression from publishing at all: a rerun that
    # surfaces NEW unexplained disagreements leaves the previous,
    # fully-accounted-for report live until someone triages
    # (dispositions/<suite>.yaml or the known-causes registry). Fail the leg
    # loudly, and pack nothing.
    if ! "$PYTHON" scripts/unexplained_ratchet.py --check; then
      echo "REFUSED: the $name refresh raises an unexplained-mismatch" \
        "ceiling (conformance/unexplained-ratchet.yaml), so nothing was" \
        "packed. Triage the new disagreements, then rerun; the previous" \
        "report stays published." >&2
      exit 1
    fi
  fi

  rm -rf "${out:?}/$name"
  mv "$staging" "$out/$name"
  echo "packed the $name refresh into $out/$name: ${#private[@]} private" \
    "file(s), ${#deletions[@]} deletion(s)"
}

# publish <bundles-dir> <branch>: apply every bundle on the tip, commit once.
publish() {
  local src="$1" target="$2" bundle work label subject attempt i path

  bundles=()
  if [ -d "$src" ]; then
    while IFS= read -r -d '' bundle; do
      bundles+=("$bundle")
    done < <(find "$src" -mindepth 1 -maxdepth 1 -type d ! -name '.*' -print0 |
      LC_ALL=C sort -z)
  fi
  if [ "${#bundles[@]}" -eq 0 ]; then
    echo "no refreshed-report bundles under $src; nothing to publish"
    return 0
  fi

  # Validate every bundle once, before touching the checkout, and flatten
  # each one's paths into NUL lists the attempt loop replays. Paths must stay
  # inside derived_paths (what pack collects from) and never name the shared
  # manifest; two bundles writing the same path apply in sorted order, last
  # one wins, with a warning.
  work="$(mktemp -d)"
  cleanup_dirs+=("$work")
  "$PYTHON" - "$work" "$manifest" "$BUNDLE_SCHEMA" "${derived_paths[@]}" \
    -- "${bundles[@]}" <<'PY'
import json, os, sys
from pathlib import Path, PurePosixPath

work, manifest, schema, *rest = sys.argv[1:]
split = rest.index("--")
derived, bundles = rest[:split], rest[split + 1 :]
work = Path(work)


def fail(message):
    sys.exit(f"FAILED: {message}; nothing was published")


def in_derived(path):
    return any(
        path.startswith(d) if d.endswith("/") else path == d for d in derived
    )


suites, added, owners = [], [], {}
for index, bundle in enumerate(bundles):
    root = Path(bundle)
    try:
        doc = json.loads((root / "bundle.json").read_text())
    except (OSError, ValueError) as exc:
        fail(f"{bundle} is not a refreshed-report bundle ({exc})")
    if not isinstance(doc, dict) or doc.get("schema") != schema:
        fail(f"{bundle}/bundle.json is not a {schema} bundle")
    suite = doc.get("suite")
    if not isinstance(suite, str) or not suite or suite in suites:
        fail(f"{bundle}/bundle.json has a missing or duplicate suite {suite!r}")
    suites.append(suite)
    lists = {}
    for key in ("private", "deletions", "manifest_added"):
        value = doc.get(key)
        if not isinstance(value, list) or not all(
            isinstance(v, str) and v and "\0" not in v for v in value
        ):
            fail(f"{suite}: bundle.json {key} must be a list of strings")
        lists[key] = value
    for key in ("private", "deletions"):
        for path in lists[key]:
            pure = PurePosixPath(path)
            if (
                pure.is_absolute()
                or ".." in pure.parts
                or path == manifest
                or not in_derived(path)
            ):
                fail(f"{suite}: {key} path {path!r} is outside the derived paths")
            if key == "private" and not (root / "files" / path).is_file():
                fail(f"{suite}: bundle lacks files/{path}")
            if path in owners and owners[path] != suite:
                message = (
                    f"{path} is in both the {owners[path]} and {suite} "
                    f"bundles; applying {suite}'s (last in sorted order)"
                )
                if os.environ.get("GITHUB_ACTIONS") == "true":
                    print(f"::warning title=Overlapping refreshes::{message}")
                else:
                    print(f"warning: {message}", file=sys.stderr)
            owners[path] = suite
        (work / f"{index}.{key}").write_bytes(
            b"".join(p.encode() + b"\0" for p in lists[key])
        )
    added.extend(e for e in lists["manifest_added"] if e not in added)

(work / "suites").write_bytes(b"".join(s.encode() + b"\0" for s in suites))
(work / "manifest-added.json").write_text(json.dumps(added))
PY

  suites=()
  while IFS= read -r -d '' path; do
    suites+=("$path")
  done <"$work/suites"
  if [ "${#suites[@]}" -eq 1 ]; then
    label="${suites[0]}"
  else
    label="${#suites[@]} suites"
  fi
  echo "publishing $label: ${suites[*]}"

  # Bot identity, only where none is configured (CI runners have none).
  git config user.name >/dev/null 2>&1 ||
    git config user.name "github-actions[bot]"
  git config user.email >/dev/null 2>&1 ||
    git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

  push_landed=""
  for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
    # Rebuild from scratch on the current remote tip (fetch + hard reset; never
    # rebase). git clean keeps the generated trees hermetic across attempts.
    git fetch origin "$target"
    git reset --hard FETCH_HEAD --quiet
    git clean -fdq -- "${derived_paths[@]}"

    # Apply every bundle's private outputs and deletions, in sorted order.
    i=0
    for bundle in "${bundles[@]}"; do
      stash="$bundle/files"
      while IFS= read -r -d '' path; do
        mkdir -p "$(dirname "$path")"
        cp -p "$stash/$path" "$path"
      done <"$work/$i.private"
      while IFS= read -r -d '' path; do
        rm -f "$path"
      done <"$work/$i.deletions"
      i=$((i + 1))
    done

    # Replay every bundle's manifest additions onto the tip's manifest
    # (append-only union, same serialization run_comparison.py writes).
    "$PYTHON" - "$manifest" "$work/manifest-added.json" <<'PY'
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

    # A re-emission never replaces a committed report on THIS tip: for any
    # restored dashboard report that is a re-emission, put back the tip's bytes
    # whenever the tip has a copy (real or itself re-emitted).
    # run_comparison.py already declines to publish one; this is the check at
    # the push, which no CI workflow sees (bot pushes don't trigger ci.yml).
    "$PYTHON" scripts/guard_reemitted_reports.py

    # Recompute every derived artifact against THIS tip, once for every
    # bundle, then refuse to push anything ci.yml would call stale.
    regenerate_derived
    verify_derived

    # The publication gate again, now over the combined tree on THIS tip: each
    # bundle passed it alone where it ran, but the tip may have moved since.
    # Retrying cannot help — a regression is not contention — and publishing
    # the passing bundles alone would drop the rest silently, so refuse the
    # whole publish loudly and name every suite in it.
    if ! "$PYTHON" scripts/unexplained_ratchet.py --check; then
      echo "REFUSED: publishing $label raises an unexplained-mismatch" \
        "ceiling (conformance/unexplained-ratchet.yaml), so nothing was" \
        "pushed. Suites in this publish: ${suites[*]}. The lines above name" \
        "the suites over their ceilings; triage those disagreements, then" \
        "rerun. The previous reports stay published." >&2
      exit 1
    fi

    git add -A -- "${derived_paths[@]}"
    if git diff --cached --quiet; then
      echo "nothing to commit for $label after regeneration (attempt $attempt)"
      return 0
    fi
    if [ "${#suites[@]}" -eq 1 ]; then
      subject="data: refresh ${suites[0]}"
    else
      subject="data: refresh ${#suites[@]} suites"
    fi
    git commit --quiet \
      -m "$subject (affected rerun $(date -u +%Y-%m-%d))" \
      -m "Suites: ${suites[*]}" \
      -m "Includes the regenerated derived conformance artifacts (dispositioned
reports + EUROMOD-BE coverage rollup, DE unified/closure/census/executable
status, scoreboard, detail, daily history snapshot, burn-down, freshness) so
main CI's staleness gates stay green.
Committed by scripts/commit_refreshed_report.sh; the ratchet is never
re-pinned here."

    if git push origin "HEAD:$target"; then
      push_landed=1
      break
    fi
    echo "push rejected (attempt $attempt/$MAX_ATTEMPTS): $target advanced" \
      "under this publish; rebuilding on the new tip" >&2
    # Growing delay with wide jitter, so a retry does not collide again with
    # whatever else is pushing to the branch.
    sleep "${PUSH_RETRY_DELAY:-$((attempt * 4 + RANDOM % 25))}"
  done

  if [ -z "$push_landed" ]; then
    echo "FAILED: could not push the $label refresh after $MAX_ATTEMPTS" \
      "attempts; the refresh was NOT committed" >&2
    exit 1
  fi
  echo "pushed $label refresh + derived conformance artifacts to $target"
}

case "$mode" in
  pack) pack "$bundles_dir" "$suite" ;;
  publish) publish "$bundles_dir" "$branch" ;;
  single)
    # The original single-suite interface: the same pack, then a publish of
    # that one bundle. Pack skips its vet here and only here: publish runs the
    # identical gates on a tip at least as new straight afterwards, so a
    # second regeneration would add minutes and catch nothing. Behaviour and
    # cost stay what this mode always had.
    single_dir="$(mktemp -d)"
    cleanup_dirs+=("$single_dir")
    pack "$single_dir" "$suite" 0
    publish "$single_dir" "$branch"
    ;;
esac
