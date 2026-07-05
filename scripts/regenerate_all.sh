#!/bin/sh
# Regenerate every oracle suite against current upstream law and deploy.
#
# Designed for unattended weekly runs, e.g. crontab:
#   17 6 * * 1  cd $HOME/axiom-oracles && ./scripts/regenerate_all.sh >> /tmp/axiom-oracles-regen.log 2>&1
set -e
cd "$(dirname "$0")/.."

./scripts/sync_rulespec_roots.sh

(cd scripts && ../.venv/bin/python run_ssa_parameter_comparison.py)
(cd scripts && ../.venv/bin/python run_parameter_comparisons.py)

for suite in fiit-ecps co-state-income-tax-ecps ssi-ecps ny-tanf-ecps \
             wa-tanf-ecps co-tanf-ecps medicaid-magi-co-ecps \
             al-snap-ecps az-snap-ecps ca-snap-ecps co-snap-ecps \
             fl-snap-ecps ma-snap-ecps nc-snap-ecps ny-snap-ecps \
             or-snap-ecps sc-snap-ecps tn-snap-ecps ut-snap-ecps; do
  echo "== $suite"
  .venv/bin/python scripts/run_comparison.py "$suite" --summary || echo "!! $suite failed"
done

.venv/bin/python scripts/sync_encoded_coverage.py || true
.venv/bin/python -m pytest tests/ -q

if ! git diff --quiet dashboard/public/data; then
  git add dashboard/public/data
  git commit -m "data: scheduled oracle regeneration $(date +%Y-%m-%d)"
  git push origin main
  (cd dashboard && bun run build && vercel --prod)
else
  echo "no data changes"
fi
