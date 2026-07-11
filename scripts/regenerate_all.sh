#!/bin/sh
# Regenerate every oracle suite against current upstream law and deploy.
#
# Designed for unattended weekly runs, e.g. crontab:
#   ./scripts/regenerate_all.sh /path/to/rulespec-us /path/to/axiom-rules-engine-binary
set -e
cd "$(dirname "$0")/.."

if [ "$#" -ne 2 ]; then
  echo "usage: $0 <rulespec-us-root> <axiom-binary>" >&2
  exit 2
fi
rulespec_root=$1
axiom_binary=$2

(cd scripts && ../.venv/bin/python run_ssa_parameter_comparison.py --rulespec-root "$rulespec_root" --axiom-binary "$axiom_binary")
(cd scripts && ../.venv/bin/python run_parameter_comparisons.py --rulespec-root "$rulespec_root" --axiom-binary "$axiom_binary")
(cd scripts && ../.venv/bin/python run_medicaid_thresholds_comparison.py --rulespec-root "$rulespec_root" --axiom-binary "$axiom_binary")

for suite in fiit-ecps co-state-income-tax-ecps ssi-ecps ny-tanf-ecps \
             wa-tanf-ecps co-tanf-ecps ca-tanf-ecps mn-tanf-ecps az-tanf-ecps \
             ks-tanf-ecps medicaid-magi-co-ecps \
             al-snap-ecps az-snap-ecps ca-snap-ecps co-snap-ecps \
             fl-snap-ecps ma-snap-ecps nc-snap-ecps ny-snap-ecps \
             or-snap-ecps sc-snap-ecps tn-snap-ecps ut-snap-ecps; do
  echo "== $suite"
  .venv/bin/python scripts/run_comparison.py "$suite" --summary || echo "!! $suite failed"
done

.venv/bin/python scripts/sync_encoded_coverage.py --rulespec-root "$rulespec_root" || true
.venv/bin/python scripts/rule_verification.py --rulespec-root "$rulespec_root" || true
.venv/bin/python -m pytest tests/ -q

if ! git diff --quiet dashboard/public/data; then
  git add dashboard/public/data
  git commit -m "data: scheduled oracle regeneration $(date +%Y-%m-%d)"
  git push origin main
  (cd dashboard && bun run build && vercel --prod)
else
  echo "no data changes"
fi
