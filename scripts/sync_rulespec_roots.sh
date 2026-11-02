#!/bin/sh
# Refresh the compose rulespec roots from upstream rulespec-us main.
#
# The federal suites that compose against ~/.axiom-oracles/roots/rulespec-us
# (ssi-ecps, medicaid-magi-co-ecps) need a real directory copy named
# rulespec-<prefix> (axiom-compose derives the corpus prefix from the
# directory name, and resolves symlinks first). State suites read the
# rulespec-us monorepo's us-<st>/ directly through ~/rulespec-us, so no
# rulespec-us-<st> root is synced. Local checkouts drift hundreds of commits
# behind origin/main, so always pull before syncing. Run this before
# regenerating any suite.
set -e
git -C "$HOME/rulespec-us" pull --ff-only origin main
mkdir -p "$HOME/.axiom-oracles/roots"
rsync -a --delete --exclude .axiom "$HOME/rulespec-us/us/"    "$HOME/.axiom-oracles/roots/rulespec-us/"
echo "rulespec roots synced from $(git -C "$HOME/rulespec-us" rev-parse --short origin/main)"
