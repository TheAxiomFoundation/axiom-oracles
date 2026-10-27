#!/bin/sh
# Regenerate the RWAMOD-backed Rwanda oracle suites and refresh their committed
# dashboard data. RWAMOD is the SOUTHMOD tax-benefit model for Rwanda
# (UNU-WIDER), run on the EUROMOD engine (EM_Executable.dll), which is x64-only
# and needs the `euromod` connector plus a .NET runtime. The SOUTHMOD bundle is
# licensed and non-redistributable and lives only in a local, agent-readable
# path, so these suites are not run on the shared CI matrix (the registry
# runner re-emits the committed report there). Run this where the bundle and
# x64 runtime exist:
#   cd $HOME/TheAxiomFoundation/axiom-oracles && ./scripts/regenerate_euromod_rw.sh
#
# Prerequisites:
#   - The licensed SOUTHMOD A4.0 bundle at EUROMOD_MODEL_ROOT (default below;
#     the comparisons/rw-*.yaml configs name the same path). NEVER commit,
#     upload, or share any byte of it; it is referenced by path only.
#   - EUROMOD_PYTHON: an x86_64 interpreter with the `euromod` connector (on
#     Apple Silicon, a Rosetta x86_64 venv; see docs/euromod-platform-playbook.md)
#   - DOTNET_ROOT: an x64 .NET runtime; PYTHONNET_RUNTIME=coreclr
#   - axiom-rules-engine built at $HOME/TheAxiomFoundation/axiom-rules-engine
#     (the configs' axiom_rules_repo)
#   - AXIOM_RULESPEC_REPO_ROOTS reaching rulespec-rw
#
# RWAMOD registers the dataset name rw_2024_a1 but the bundle ships no
# Rwandan input file. scripts/southmod_rw_header.py builds the header-only
# schema file the EUROMOD worker needs from the bundle itself and writes it
# into the bundle's Input/ directory (never into this repository); it does
# nothing when the file is already present.
set -e
cd "$(dirname "$0")/.."

: "${EUROMOD_MODEL_ROOT:=$HOME/.axiom/oracles/southmod/bundle/SOUTHMOD_A4.0}"
: "${EUROMOD_PYTHON:?set EUROMOD_PYTHON to the x86_64 interpreter with the euromod connector}"
: "${DOTNET_ROOT:?set DOTNET_ROOT to an x64 .NET runtime}"
: "${PYTHONNET_RUNTIME:=coreclr}"
: "${AXIOM_RULESPEC_REPO_ROOTS:=$HOME/TheAxiomFoundation}"
export EUROMOD_MODEL_ROOT EUROMOD_PYTHON DOTNET_ROOT PYTHONNET_RUNTIME AXIOM_RULESPEC_REPO_ROOTS

"$EUROMOD_PYTHON" scripts/southmod_rw_header.py --model-root "$EUROMOD_MODEL_ROOT"

for name in \
  rw-paye-rate-schedule \
  rw-lump-sum \
  rw-rental \
  rw-contributions \
  rw-vat \
  rw-excise \
  rw-cbhi-tiers \
  rw-dispy; do
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
