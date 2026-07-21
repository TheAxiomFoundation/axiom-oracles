#!/usr/bin/env bash
set -euo pipefail
export PYTHONHASHSEED=294
export AXIOM_SNAP_QC_AXIOM_BINARY="${AXIOM_SNAP_QC_AXIOM_BINARY:-/Users/maxghenis/TheAxiomFoundation/axiom-rules-engine/target/debug/axiom-rules-engine}"
export AXIOM_SNAP_QC_RULESPEC_ROOT="${AXIOM_SNAP_QC_RULESPEC_ROOT:-/Users/maxghenis/TheAxiomFoundation/_worktrees/rulespec-us-snap-sua-states}"
export AXIOM_CORPUS_REPO="${AXIOM_CORPUS_REPO:-/Users/maxghenis/TheAxiomFoundation/_worktrees/axiom-corpus-snap-suas}"
export AXIOM_CORPUS_ARTIFACT_ROOT="${AXIOM_CORPUS_ARTIFACT_ROOT:-$AXIOM_CORPUS_REPO/data/corpus}"
cd "$(dirname "$0")/../.."
# Engine mode is the quotable default: features come from the encoded rules
# through the axiom-rules-engine, with a per-case FSBEN identity assertion.
# Pass MODE=analytical for the engine-free fallback (QC-file stage columns).
if [ "${MODE:-engine}" = "engine" ]; then
  uv run --with pandas --with pyarrow python analysis/qc-error-prediction/extract_features.py --engine
else
  uv run --with pandas --with pyarrow python analysis/qc-error-prediction/extract_features.py
fi
uv run --with pandas --with pyarrow --with scikit-learn python analysis/qc-error-prediction/run_models.py
