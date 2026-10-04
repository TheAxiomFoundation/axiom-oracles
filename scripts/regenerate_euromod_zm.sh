#!/bin/sh
# Regenerate the MicroZAMOD-backed Zambia oracle suites and refresh their
# committed dashboard data. MicroZAMOD is the SOUTHMOD tax-benefit model for
# Zambia (UNU-WIDER), run on the EUROMOD engine (EM_Executable.dll), which is
# x64-only and needs the `euromod` connector plus a .NET runtime. The SOUTHMOD
# bundle is licensed and non-redistributable and lives only in a local,
# agent-readable path, so these suites are not run on the shared CI matrix.
# Run this where the bundle and x64 runtime exist:
#   cd $HOME/TheAxiomFoundation/axiom-oracles && ./scripts/regenerate_euromod_zm.sh
#
# Prerequisites:
#   - The licensed SOUTHMOD A4.0 bundle at EUROMOD_MODEL_ROOT (default below),
#     with the ZM country files and the zm_2022_a2 dataset. NEVER commit,
#     upload, or share any byte of it; it is referenced by path only.
#   - EUROMOD_PYTHON: an x86_64 interpreter with the `euromod` connector (on
#     Apple Silicon, a Rosetta x86_64 venv; see docs/euromod-platform-playbook.md)
#   - DOTNET_ROOT: an x64 .NET runtime; PYTHONNET_RUNTIME=coreclr
#   - axiom-rules-engine built at the comparison configs' axiom_rules_repo
#     ($HOME/TheAxiomFoundation/axiom-rules-engine).
#   - AXIOM_RULESPEC_REPO_ROOTS reaching rulespec-zm (the Act 22 of 2023 PAYE,
#     Act 22 of 2024 turnover, S.I. 9 of 2024 NAPSA, S.I. 63 of 2019 NHIMA,
#     Cap. 331 VAT, Act 24 of 2024 excise and MCDSS SCT modules, and the
#     composed disposable-income pipeline).
#
# The suites use two period bases. zm-paye-rate-schedule, zm-turnover, zm-vat,
# zm-excise-ad-valorem and zm-dispy compare annual amounts (the adapter's x12
# output annualization). zm-napsa-contributions, zm-nhima-contributions and
# zm-sct compare monthly amounts (their configs set
# euromod_annualize_outputs: false because the rulespec-zm modules are
# Month-period).
set -e
cd "$(dirname "$0")/.."

: "${EUROMOD_MODEL_ROOT:=$HOME/.axiom/oracles/southmod/bundle/SOUTHMOD_A4.0}"
: "${EUROMOD_PYTHON:?set EUROMOD_PYTHON to the x86_64 interpreter with the euromod connector}"
: "${DOTNET_ROOT:?set DOTNET_ROOT to an x64 .NET runtime}"
: "${PYTHONNET_RUNTIME:=coreclr}"
: "${AXIOM_RULESPEC_REPO_ROOTS:=$HOME/TheAxiomFoundation}"
export EUROMOD_MODEL_ROOT EUROMOD_PYTHON DOTNET_ROOT PYTHONNET_RUNTIME AXIOM_RULESPEC_REPO_ROOTS

for name in \
  zm-paye-rate-schedule \
  zm-turnover \
  zm-napsa-contributions \
  zm-nhima-contributions; do
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
