#!/bin/sh
# Regenerate the UKMOD-backed UK oracle suites and refresh their committed
# dashboard data. UKMOD's engine (EM_Executable.dll) is x64-only and needs the
# `euromod` connector plus a .NET runtime, and the model is a local checkout,
# so these suites are not run on the shared CI matrix (the registry runner
# re-emits the committed report there). Run this where the model and x64
# runtime exist, e.g. weekly:
#   17 6 * * 1  cd $HOME/axiom-oracles && ./scripts/regenerate_euromod_uk.sh
#
# Prerequisites (see docs/euromod-platform-playbook.md):
#   - UKMOD_PUBLIC_B2026.03 checkout (registration-free):
#       git clone --branch B2026.03 \
#         https://github.com/centreformicrosimulation/UKMOD-PUBLIC
#   - EUROMOD_PYTHON: an x86_64 interpreter with `euromod` installed
#   - DOTNET_ROOT: an x64 .NET runtime
#   - AXIOM_RULESPEC_REPO_ROOTS reaching rulespec-uk with the composed pilot
#     pipelines (uk/statutes/income_tax/individual/pilot_worker_oracle_pipeline,
#     uk/statutes/social_security/workers/pilot_worker_class_1_nic_pipeline, and
#     uk/policies/universal_credit_composed_award_pipeline)
set -e
cd "$(dirname "$0")/.."

: "${EUROMOD_MODEL_ROOT:=$HOME/Downloads/UKMOD_PUBLIC_B2026.03}"
: "${EUROMOD_PYTHON:?set EUROMOD_PYTHON to the x86_64 interpreter with the euromod connector}"
: "${DOTNET_ROOT:?set DOTNET_ROOT to an x64 .NET runtime}"
: "${AXIOM_RULESPEC_REPO_ROOTS:=$HOME/TheAxiomFoundation}"
export EUROMOD_MODEL_ROOT EUROMOD_PYTHON DOTNET_ROOT AXIOM_RULESPEC_REPO_ROOTS

for name in \
  uk-worker-pit-ukmod \
  uk-worker-nic-ukmod \
  uk-self-employed-nic-ukmod \
  uk-employer-nic-ukmod \
  uk-universal-credit-ukmod \
  uk-income-tax-savings-ukmod \
  uk-income-tax-dividend-ukmod \
  uk-income-tax-mixed-ukmod; do
  echo "== $name"
  .venv/bin/python scripts/run_comparison.py "$name" --summary || echo "!! $name failed"
done

if ! git diff --quiet dashboard/public/data; then
  echo "Dashboard data changed. Review and commit:"
  git --no-pager diff --stat dashboard/public/data
else
  echo "No dashboard data changes."
fi
