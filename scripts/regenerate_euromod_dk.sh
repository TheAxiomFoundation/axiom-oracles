#!/bin/sh
# Regenerate the EUROMOD-backed Denmark oracle suites and refresh their committed
# dashboard data. EUROMOD's engine (EM_Executable.dll) is x64-only and needs the
# `euromod` connector plus a .NET runtime, and the model is a local checkout, so
# these suites are not run on the shared CI matrix (the registry runner re-emits
# the committed report there). Run this where the model and x64 runtime exist,
# e.g. weekly:
#   19 6 * * 1  cd $HOME/axiom-oracles && ./scripts/regenerate_euromod_dk.sh
#
# Prerequisites (see docs/euromod-platform-playbook.md):
#   - The public JRC EUROMOD release checkout (EUROMOD_RELEASES_J2.0+) with the
#     Danish country XML and the bundled DK_training_data dataset.
#   - EUROMOD_PYTHON: an x86_64 interpreter with the `euromod` connector installed
#   - DOTNET_ROOT: an x64 .NET runtime; PYTHONNET_RUNTIME=coreclr
#   - AXIOM_RULESPEC_REPO_ROOTS reaching rulespec-dk with the composed pipeline
#     (dk/statutes/composed/boerne-og-ungeydelse-pipeline)
set -e
cd "$(dirname "$0")/.."

: "${EUROMOD_MODEL_ROOT:=$HOME/Downloads/EUROMOD_J2.0/EUROMOD_RELEASES_J2.0+}"
: "${EUROMOD_PYTHON:?set EUROMOD_PYTHON to the x86_64 interpreter with the euromod connector}"
: "${DOTNET_ROOT:?set DOTNET_ROOT to an x64 .NET runtime}"
: "${PYTHONNET_RUNTIME:=coreclr}"
: "${POLARS_SKIP_CPU_CHECK:=1}"
: "${AXIOM_RULESPEC_REPO_ROOTS:=$HOME/TheAxiomFoundation}"
export EUROMOD_MODEL_ROOT EUROMOD_PYTHON DOTNET_ROOT PYTHONNET_RUNTIME \
  POLARS_SKIP_CPU_CHECK AXIOM_RULESPEC_REPO_ROOTS

for name in \
  dk-child-youth-benefit-euromod \
  dk-child-youth-benefit-2023-euromod; do
  echo "== $name"
  .venv/bin/python scripts/run_comparison.py "$name" --summary || echo "!! $name failed"
done

if ! git diff --quiet dashboard/public/data; then
  echo "Dashboard data changed. Review and commit:"
  git --no-pager diff --stat dashboard/public/data
else
  echo "No dashboard data changes."
fi
