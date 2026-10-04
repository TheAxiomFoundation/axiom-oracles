#!/bin/sh
# Regenerate the ETMOD-backed Ethiopia oracle suites and refresh their committed
# dashboard data. ETMOD is the SOUTHMOD tax-benefit model for Ethiopia
# (UNU-WIDER), run on the EUROMOD engine (EM_Executable.dll), which is x64-only
# and needs the `euromod` connector plus a .NET runtime. The SOUTHMOD bundle is
# licensed and non-redistributable and lives only in a local, agent-readable
# path, so these suites are `ci: manual` and are not run on the shared CI matrix
# (the registry runner re-emits the committed report there). Run this where the
# bundle and x64 runtime exist:
#   cd $HOME/TheAxiomFoundation/axiom-oracles && ./scripts/regenerate_euromod_et.sh
#
# Prerequisites:
#   - The licensed SOUTHMOD A4.0 bundle at EUROMOD_MODEL_ROOT (default below),
#     with system ET_2025 and dataset et_2022_a2. NEVER commit, upload, or share
#     any byte of it; it is referenced by path only.
#   - EUROMOD_PYTHON: an x86_64 interpreter with the `euromod` connector (on
#     Apple Silicon, a Rosetta x86_64 venv; see docs/euromod-platform-playbook.md)
#   - DOTNET_ROOT: an x64 .NET runtime; PYTHONNET_RUNTIME=coreclr
#   - axiom-rules-engine built at $HOME/TheAxiomFoundation/axiom-rules-engine
#     (the comparison configs' axiom_rules_repo).
#   - AXIOM_RULESPEC_REPO_ROOTS reaching rulespec-et (the Proclamation 1395/2025
#     income-tax amendment, Proclamation 715/2011 and 714/2011 pension, and
#     Proclamation 1341/2024 VAT modules, and the composed disposable-income
#     pipeline).
# The three monthly suites (et-paye-rate-schedule, et-pension-contributions,
# et-dispy) set euromod_annualize_outputs: false in their configs; the runner
# passes that through, so no environment override is needed here.
set -e
cd "$(dirname "$0")/.."

: "${EUROMOD_MODEL_ROOT:=$HOME/.axiom/oracles/southmod/bundle/SOUTHMOD_A4.0}"
: "${EUROMOD_PYTHON:?set EUROMOD_PYTHON to the x86_64 interpreter with the euromod connector}"
: "${DOTNET_ROOT:?set DOTNET_ROOT to an x64 .NET runtime}"
: "${PYTHONNET_RUNTIME:=coreclr}"
: "${AXIOM_RULESPEC_REPO_ROOTS:=$HOME/TheAxiomFoundation}"
export EUROMOD_MODEL_ROOT EUROMOD_PYTHON DOTNET_ROOT PYTHONNET_RUNTIME \
  AXIOM_RULESPEC_REPO_ROOTS

for name in \
  et-paye-rate-schedule \
  et-presumptive \
  et-business-mat \
  et-pension-contributions \
  et-vat; do
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
