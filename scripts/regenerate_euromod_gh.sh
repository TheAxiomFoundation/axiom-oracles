#!/bin/sh
# Regenerate the GHAMOD-backed Ghana oracle suites and refresh their committed
# dashboard data. GHAMOD is the SOUTHMOD tax-benefit model for Ghana (UNU-WIDER),
# run on the EUROMOD engine (EM_Executable.dll), which is x64-only and needs the
# `euromod` connector plus a .NET runtime. The SOUTHMOD bundle is licensed and
# non-redistributable and lives only in a local, agent-readable path, so these
# suites are not run on the shared CI matrix (the registry runner re-emits the
# committed report there). Run this where the bundle and x64 runtime exist:
#   cd $HOME/TheAxiomFoundation/axiom-oracles && ./scripts/regenerate_euromod_gh.sh
#
# Prerequisites:
#   - The licensed SOUTHMOD A4.0 bundle at EUROMOD_MODEL_ROOT (default below).
#     NEVER commit, upload, or share any byte of it; it is referenced by path
#     only.
#   - EUROMOD_PYTHON: an x86_64 interpreter with the `euromod` connector (on
#     Apple Silicon, a Rosetta x86_64 venv; see docs/euromod-platform-playbook.md)
#   - DOTNET_ROOT: an x64 .NET runtime; PYTHONNET_RUNTIME=coreclr
#   - axiom-rules-engine built at the rulespec-gh toolchain pin (.axiom/
#     toolchain.toml axiom_rules_engine_ref), which seeds the GHS currency unit
#     the Ghana modules use. The comparison configs point axiom_rules_repo at
#     $HOME/TheAxiomFoundation/axiom-rules-engine, so check that repo out at the
#     pin before running (or pre-build the pinned binary there).
#   - AXIOM_RULESPEC_REPO_ROOTS reaching rulespec-gh (the Act 1111 first-schedule
#     rate module and the Act 896 fifth-schedule reliefs module).
set -e
cd "$(dirname "$0")/.."

: "${EUROMOD_MODEL_ROOT:=$HOME/.axiom/oracles/southmod/bundle/SOUTHMOD_A4.0}"
: "${EUROMOD_PYTHON:?set EUROMOD_PYTHON to the x86_64 interpreter with the euromod connector}"
: "${DOTNET_ROOT:?set DOTNET_ROOT to an x64 .NET runtime}"
: "${PYTHONNET_RUNTIME:=coreclr}"
: "${AXIOM_RULESPEC_REPO_ROOTS:=$HOME/TheAxiomFoundation}"
export EUROMOD_MODEL_ROOT EUROMOD_PYTHON DOTNET_ROOT PYTHONNET_RUNTIME AXIOM_RULESPEC_REPO_ROOTS

for name in \
  gh-income-tax-rate-schedule \
  gh-personal-reliefs; do
  echo "== $name"
  .venv/bin/python scripts/run_comparison.py "$name" --summary || echo "!! $name failed"
done

# Merge dispositions into the refreshed dashboard reports and validate they
# still reconcile with the committed data.
.venv/bin/python scripts/apply_dispositions.py

if ! git diff --quiet dashboard/public/data; then
  echo "Dashboard data changed. Review and commit:"
  git --no-pager diff --stat dashboard/public/data
else
  echo "No dashboard data changes."
fi
