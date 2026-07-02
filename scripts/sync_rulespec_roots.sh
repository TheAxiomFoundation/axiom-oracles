#!/bin/sh
# Refresh the compose rulespec roots from upstream rulespec-us main.
#
# The oracle comparisons compose against ~/.axiom-oracles/roots/* — real
# directory copies named rulespec-<prefix> (axiom-compose derives the
# corpus prefix from the directory name, and resolves symlinks first).
# Local checkouts drift hundreds of commits behind origin/main, so always
# pull before syncing. Run this before regenerating any suite.
set -e
git -C "$HOME/rulespec-us" pull --ff-only origin main
mkdir -p "$HOME/.axiom-oracles/roots"
rsync -a --delete --exclude .axiom "$HOME/rulespec-us/us/"    "$HOME/.axiom-oracles/roots/rulespec-us/"
rsync -a --delete --exclude .axiom "$HOME/rulespec-us/us-ny/" "$HOME/.axiom-oracles/roots/rulespec-us-ny/"
rsync -a --delete --exclude .axiom "$HOME/rulespec-us/us-wa/" "$HOME/.axiom-oracles/roots/rulespec-us-wa/"
echo "rulespec roots synced from $(git -C "$HOME/rulespec-us" rev-parse --short origin/main)"
