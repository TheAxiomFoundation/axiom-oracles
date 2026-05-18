#!/usr/bin/env bash
# Run the Axiom vs PolicyEngine federal individual income tax (FIIT)
# comparison on the Enhanced CPS and write a JSON report to reports/.
#
# Recovered from Codex logs / Slack:
# - https://github.com/TheAxiomFoundation/axiom-encode/blob/main/src/axiom_encode/cli.py
#   provides `axiom-encode tax-ecps-compare`, which is the canonical harness.
# - The harness requires the rulespec-us checkout to be in a directory named
#   exactly `rulespec-us` (otherwise RuleSpec module IDs get a different
#   namespace and imports fail).
# - It also requires a debug build of axiom-rules-engine at
#   $AXIOM_RULES_REPO/target/debug/axiom-rules-engine.
#
# The harness hard-pins `policyengine==4.4.4` at runtime; passing newer PE
# versions causes the run to exit with "policyengine==4.4.4 required". Until
# the pin is relaxed upstream (axiom-encode `require_policyengine_versions`),
# the script defaults to the pinned stack (4.4.4 / 1.691.3 / 3.26.0). Pass
# --latest-pe to opt out and surface the error if you need to retest the gate.

set -euo pipefail

SAMPLE_SIZE=${SAMPLE_SIZE:-1000}
YEAR=${YEAR:-2026}
SURFACE=${SURFACE:-all}
PINNED=${PINNED:-1}
AXIOM_ENCODE_REPO=${AXIOM_ENCODE_REPO:-$HOME/axiom-encode}
AXIOM_RULES_REPO=${AXIOM_RULES_REPO:-$HOME/axiom-rules}
OUTPUT=${OUTPUT:-}

usage() {
    cat <<'EOF'
Usage: run_fiit_compare.sh [--sample-size N] [--year YEAR] [--surface NAME]
                           [--latest-pe] [--output PATH]

Environment overrides:
  SAMPLE_SIZE         (default 1000; 0 = full Enhanced CPS)
  YEAR                (default 2026; matches the harness default)
  SURFACE             (default all; or ctc|standard-deduction|eitc|...)
  PINNED              (default 1; set 0 to opt out — currently fails because
                       axiom-encode hard-pins policyengine==4.4.4)
  AXIOM_ENCODE_REPO   (default $HOME/axiom-encode)
  AXIOM_RULES_REPO    (default $HOME/axiom-rules)
  OUTPUT              (default reports/axiom-policyengine-fiit-ecps-<sample>-<date>.json)
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --sample-size) SAMPLE_SIZE=$2; shift 2;;
        --year)        YEAR=$2; shift 2;;
        --surface)     SURFACE=$2; shift 2;;
        --pinned)      PINNED=1; shift;;
        --latest-pe)   PINNED=0; shift;;
        --output)      OUTPUT=$2; shift 2;;
        --axiom-encode-repo) AXIOM_ENCODE_REPO=$2; shift 2;;
        --axiom-rules-repo)  AXIOM_RULES_REPO=$2; shift 2;;
        -h|--help)     usage; exit 0;;
        *) echo "unknown flag: $1" >&2; usage >&2; exit 2;;
    esac
done

if [[ ! -d "$AXIOM_ENCODE_REPO" ]]; then
    echo "axiom-encode repo not found at $AXIOM_ENCODE_REPO" >&2; exit 1
fi
if [[ ! -d "$AXIOM_RULES_REPO" ]]; then
    echo "axiom-rules repo not found at $AXIOM_RULES_REPO" >&2; exit 1
fi

# Build the engine binary in debug mode if missing (the tax-ecps-compare
# harness probes the debug path, not release).
if [[ ! -x "$AXIOM_RULES_REPO/target/debug/axiom-rules-engine" ]]; then
    echo "Building debug axiom-rules-engine..."
    (cd "$AXIOM_RULES_REPO" && cargo build --bin axiom-rules-engine)
fi

# Fresh rulespec-us checkout. The directory name MUST be exactly `rulespec-us`.
workspace=$(mktemp -d -t fiit-compare.XXXXXX)
trap 'rm -rf "$workspace"' EXIT
echo "Workspace: $workspace"
echo "Cloning fresh rulespec-us..."
git clone --quiet --depth 1 \
    https://github.com/TheAxiomFoundation/rulespec-us.git \
    "$workspace/rulespec-us"
rulespec_sha=$(git -C "$workspace/rulespec-us" rev-parse HEAD)
echo "rulespec-us @ $rulespec_sha"

# Output path
if [[ -z "$OUTPUT" ]]; then
    today=$(date +%Y-%m-%d)
    OUTPUT="reports/axiom-policyengine-fiit-ecps-${SAMPLE_SIZE}-${today}.json"
fi
mkdir -p "$(dirname "$OUTPUT")"

# PE version stack
if [[ "$PINNED" -eq 1 ]]; then
    pe_pins=(
        --with 'policyengine==4.4.4'
        --with 'policyengine-us==1.691.3'
        --with 'policyengine-core==3.26.0'
    )
else
    pe_pins=(
        --with 'policyengine'
        --with 'policyengine-us'
        --with 'policyengine-core'
    )
fi

echo "Running tax-ecps-compare (sample=$SAMPLE_SIZE, year=$YEAR, surface=$SURFACE, pinned=$PINNED)..."
uv run --python 3.13 --no-project \
    --with "$AXIOM_ENCODE_REPO" \
    "${pe_pins[@]}" \
    axiom-encode tax-ecps-compare \
    --rulespec-root "$workspace/rulespec-us" \
    --axiom-rules-engine-path "$AXIOM_RULES_REPO" \
    --sample-size "$SAMPLE_SIZE" \
    --year "$YEAR" \
    --surface "$SURFACE" \
    --json > "$OUTPUT"

# Headline summary
echo
echo "Wrote: $OUTPUT"
python3 -c "
import json
d = json.load(open('$OUTPUT'))
cv = d['compared_values']
mc = d['mismatch_count']
pct = 100*(cv-mc)/cv if cv else 0
print(f'Compared persons:   {d[\"compared_persons\"]}')
print(f'Compared tax units: {d[\"compared_tax_units\"]}')
print(f'Compared values:    {cv}')
print(f'Mismatches:         {mc}')
print(f'Agreement:          {pct:.4f}%')
print()
print('Per-surface:')
from collections import defaultdict
by_surf = defaultdict(lambda: [0, 0])
for r in d['output_summary']:
    by_surf[r['surface']][0] += r['compared']
    by_surf[r['surface']][1] += r['mismatches']
for surf, (c, m) in sorted(by_surf.items(), key=lambda x: -x[1][1]):
    p = 100*(c-m)/c if c else 0
    print(f'  {surf:30s}  {c-m}/{c} ({p:6.2f}%)  mismatches={m}')
"
