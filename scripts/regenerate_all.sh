#!/bin/sh
# Regenerate every oracle suite against current upstream law and deploy.
#
# Designed for unattended weekly runs, e.g. crontab:
#   17 6 * * 1  cd $HOME/axiom-oracles && ./scripts/regenerate_all.sh >> /tmp/axiom-oracles-regen.log 2>&1
set -e
cd "$(dirname "$0")/.."

# Unattended runs publish data and deploy production. Use a dedicated
# checkout; never run from a review branch someone left checked out.
branch=$(git rev-parse --abbrev-ref HEAD)
if [ "$branch" != "main" ] && [ "$branch" != "oracle-data" ]; then
  echo "!! refusing unattended regen on branch '$branch' (expected main or oracle-data)"
  exit 1
fi

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
(cd scripts && ../.venv/bin/python run_medicaid_thresholds_comparison.py)

for suite in fiit-ecps co-state-income-tax-ecps co-state-income-tax-taxsim \
             co-tax-intersection-taxsim \
             ssi-ecps ny-tanf-ecps \
             wa-tanf-ecps co-tanf-ecps ca-tanf-ecps mn-tanf-ecps az-tanf-ecps \
             ks-tanf-ecps medicaid-magi-co-ecps \
             al-snap-ecps az-snap-ecps ca-snap-ecps co-snap-ecps \
             fl-snap-ecps ma-snap-ecps nc-snap-ecps ny-snap-ecps \
             or-snap-ecps sc-snap-ecps tn-snap-ecps ut-snap-ecps \
             de-tanf-ecps al-tanf-ecps ga-tanf-ecps \
             co-snap-qc az-snap-qc ca-snap-qc ga-snap-qc md-snap-qc \
             ny-snap-qc tx-snap-qc; do
  echo "== $suite"
  .venv/bin/python scripts/run_comparison.py "$suite" --summary || echo "!! $suite failed"
done

# State-tax Populace campaign: one report covering every ready state,
# then per-state dashboard reports AND case-explorer chunks projected
# from its per-tax-unit rows.
.venv/bin/python scripts/run_state_tax_populace.py \
  --rulespec-root "$HOME/rulespec-us" \
  --axiom-rules-path "$HOME/axiom-rules-engine" \
  --output "reports/state-tax-populace-campaign-$(date +%Y-%m-%d).json" \
  || echo "!! populace campaign failed"
.venv/bin/python scripts/emit_populace_campaign_artifacts.py || echo "!! populace artifacts failed"

.venv/bin/python scripts/sync_encoded_coverage.py || true
# Re-emit per-suite case artifacts for the dashboard's case explorer from
# the fresh full reports (auto-discovers suites from comparisons/*.yaml).
.venv/bin/python scripts/emit_case_artifacts.py || echo "!! case artifacts failed"
# Validate producer-bound certified chunks against the exact refreshed reports.
# Initial legacy indexes may migrate; existing v1 identities cannot be rebound
# here, so an emitter failure or stale corpus stops the scheduled run.
.venv/bin/python scripts/generate_chunk_indexes.py
# Ship each disposition's prose explanation (evidence.mechanism) so the
# dashboard can say WHY a class is dispositioned, not just that it is.
.venv/bin/python scripts/emit_disposition_artifacts.py || echo "!! disposition artifacts failed"
# Rebundle the front page's single-fetch overview after any report changes
# (CI gates on its consistency with the manifest).
.venv/bin/python scripts/generate_dashboard_overview.py || echo "!! overview bundle failed"
# Full-evidence reports run to GBs; keep only the newest generation each.
.venv/bin/python scripts/prune_superseded_reports.py || echo "!! report prune failed"
.venv/bin/python -m pytest tests/ -q

if ! git diff --quiet dashboard/public/data; then
  .venv/bin/python scripts/oracle_data.py publish --group dashboard \
    --message "data: scheduled oracle regeneration $(date +%Y-%m-%d)"
  (cd dashboard && AXIOM_ORACLES_DATA_SOURCE=checkout bun run build && vercel --prod)
else
  echo "no data changes"
fi
