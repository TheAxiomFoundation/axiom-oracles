#!/bin/sh
# Regenerate every oracle suite against current upstream law and deploy.
#
# Designed for unattended weekly runs, e.g. crontab:
#   17 6 * * 1  cd $HOME/axiom-oracles && ./scripts/regenerate_all.sh >> /tmp/axiom-oracles-regen.log 2>&1
#
# Steps: refresh rulespec roots from upstream -> rerun parameter suites ->
# rerun every household comparison -> resync the coverage inventory ->
# rebuild and deploy the dashboard if anything changed.
set -e
cd "$(dirname "$0")/../.."

# Use a dedicated unattended checkout; never discard review-branch changes.
branch=$(git rev-parse --abbrev-ref HEAD)
case "$branch" in
  main | oracle-data) ;;
  *) echo "!! refusing unattended regen on branch '$branch'"; exit 1 ;;
esac
# Prepare before computing, so generations read current source and live data.
# Refuse local edits before the disposable checkout is rebuilt.
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "!! refusing unattended regen with local tracked changes"
  exit 1
fi
.venv/bin/python scripts/oracle_data.py prepare
git switch -C oracle-data

./scripts/sync_rulespec_roots.sh

(cd scripts && ../.venv/bin/python run_ssa_parameter_comparison.py)
(cd scripts && ../.venv/bin/python run_parameter_comparisons.py)

for suite in fiit-ecps co-state-income-tax-ecps ssi-ecps ny-tanf-ecps \
             wa-tanf-ecps medicaid-magi-co-ecps \
             al-snap-ecps az-snap-ecps ca-snap-ecps co-snap-ecps \
             fl-snap-ecps ma-snap-ecps nc-snap-ecps ny-snap-ecps \
             or-snap-ecps sc-snap-ecps tn-snap-ecps ut-snap-ecps; do
  echo "== $suite"
  .venv/bin/python scripts/run_comparison.py "$suite" --summary || echo "!! $suite failed"
done

.venv/bin/python scripts/sync_encoded_coverage.py || true
# Per-rule verification KPI (A7): joins the freshly-synced rulespec-us tree
# against coverage_overview.json. sync_rulespec_roots.sh already pulled
# $HOME/rulespec-us to origin/main, so read HEAD offline here.
.venv/bin/python scripts/rule_verification.py --no-fetch || true
.venv/bin/python -m pytest tests/ -q

if ! git diff --quiet dashboard/public/data; then
  .venv/bin/python scripts/oracle_data.py publish --group dashboard \
    --message "data: scheduled oracle regeneration $(date +%Y-%m-%d)"
  (cd dashboard && AXIOM_ORACLES_DATA_SOURCE=checkout bun run build && vercel --prod)
else
  echo "no data changes"
fi
