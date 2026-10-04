#!/bin/sh
# Regenerate the GHAMOD-backed Ghana oracle suites and refresh their committed
# dashboard data. GHAMOD is the SOUTHMOD tax-benefit model for Ghana (UNU-WIDER),
# run on the EUROMOD engine (EM_Executable.dll), which is x64-only and needs the
# `euromod` connector plus a .NET runtime. The SOUTHMOD bundle is licensed and
# non-redistributable and lives only in a local, agent-readable path, so every
# gh-* suite declares `ci: manual`: no CI workflow runs them, and their
# committed reports change only when this script (or another supervised
# `run_comparison.py` run) is run where the bundle and x64 runtime exist:
#   cd $HOME/TheAxiomFoundation/axiom-oracles && ./scripts/regenerate_euromod_gh.sh
#
# Prerequisites:
#   - The licensed SOUTHMOD A4.0 bundle at EUROMOD_MODEL_ROOT (default below).
#     NEVER commit, upload, or share any byte of it; it is referenced by path
#     only.
#   - EUROMOD_PYTHON: an x86_64 interpreter with the `euromod` connector (on
#     Apple Silicon, a Rosetta x86_64 venv; see docs/euromod-platform-playbook.md)
#   - DOTNET_ROOT: an x64 .NET runtime; PYTHONNET_RUNTIME=coreclr
#   - A built axiom-rules-engine checkout at the path the comparison configs
#     name (axiom_rules_repo: $HOME/TheAxiomFoundation/axiom-rules-engine).
#     Each report records the engine SHA it ran against in
#     provenance.engine; rulespec-gh's own CI validates against the
#     axiom-rules-engine-ref pinned in its .github/workflows/repository-checks.yml.
#   - AXIOM_RULESPEC_REPO_ROOTS reaching rulespec-gh (every module the gh
#     suites name; each report records the rulespec-gh SHA in
#     provenance.rulespecs).
#   - AXIOM_ORACLES_RUN_KIND=manual (set below) so the reports' provenance
#     records a supervised run.
set -e
cd "$(dirname "$0")/.."

: "${EUROMOD_MODEL_ROOT:=$HOME/.axiom/oracles/southmod/bundle/SOUTHMOD_A4.0}"
: "${EUROMOD_PYTHON:?set EUROMOD_PYTHON to the x86_64 interpreter with the euromod connector}"
: "${DOTNET_ROOT:?set DOTNET_ROOT to an x64 .NET runtime}"
: "${PYTHONNET_RUNTIME:=coreclr}"
: "${AXIOM_RULESPEC_REPO_ROOTS:=$HOME/TheAxiomFoundation}"
: "${AXIOM_ORACLES_RUN_KIND:=manual}"
export EUROMOD_MODEL_ROOT EUROMOD_PYTHON DOTNET_ROOT PYTHONNET_RUNTIME \
  AXIOM_RULESPEC_REPO_ROOTS AXIOM_ORACLES_RUN_KIND

for name in \
  gh-income-tax-rate-schedule \
  gh-personal-reliefs \
  gh-ssnit-contributions \
  gh-capital-income \
  gh-presumptive-turnover \
  gh-vat-levies; do
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
