# Setup commands and observed results

Commands below ran from the assigned workspace. The organization rules and
previous lane report were read first. Source repositories and the engine were
read-only inputs; the new Git stores and checkouts are inside this workspace.

```sh
cat /Users/maxghenis/TheAxiomFoundation/CLAUDE.md
cat /Users/maxghenis/.subfleet/worktrees/20260923-093102-yale-parity-1383-measure/yale-1383-run/RESULT.md
git -C /Users/maxghenis/TheAxiomFoundation/axiom-oracles rev-parse origin/main
# 16fe458fc46512b15c4580cb9f25596bd7cb6984

mkdir -p yale-full-run
git clone --shared --bare /Users/maxghenis/TheAxiomFoundation/axiom-oracles yale-full-run/oracles.git
git --git-dir=yale-full-run/oracles.git worktree add -b subfleet/yale-campaign-full-v2 yale-full-run/B/oracles 16fe458fc46512b15c4580cb9f25596bd7cb6984
git clone --shared --bare /Users/maxghenis/TheAxiomFoundation/rulespec-us yale-full-run/rulespec.git
git --git-dir=yale-full-run/rulespec.git worktree add --detach yale-full-run/B/rulespec-us c62645022a8b2fcb5f9e6afdc2def2c8d68c2baf
git --git-dir=yale-full-run/oracles.git worktree add --detach yale-full-run/A/oracles 16fe458fc46512b15c4580cb9f25596bd7cb6984
git --git-dir=yale-full-run/rulespec.git worktree add --detach yale-full-run/A/rulespec-us 96d5e7c1e6309dc205b7320bbddaae8dd5d410df

shasum -a 256 /Users/maxghenis/TheAxiomFoundation/_tariff-parity/axiom-rules-engine/target/release/axiom-rules-engine
# 674ca6e70afdccb59c3d6847933bc24b4590105e49db54790f2dcd0bdbbe32d7
```

All clone/worktree commands exited 0. The canonical directory name `rulespec-us`
is used independently under `A/` and `B/`, providing the same canonical `us:`
import resolution that the prior lane obtained with a symlink. Fresh compilation
of all 100 chapters passed for both layouts.

The original outer checkout was detached at
`ef7e11f5f4e2ff841f2797685ba2807c6090563f`; initial `git status --short` was empty.
Attempting a branch there failed before modification:

```sh
git -c core.fsmonitor=false switch -c subfleet/yale-campaign-full-v2 origin/main
# exit 128: fatal: Unable to create
# '/Users/maxghenis/TheAxiomFoundation/axiom-oracles/.git/worktrees/20260923-140123-yale-campaign-full-v2/index.lock': Operation not permitted
```

The writable local `B/oracles` branch carries the measurement commits. No fetch,
push, PR, comment or merge command ran. The original checkout and external source
repositories were preserved.

Before fresh evaluation, the committed manifests were archived to
`A/committed/MANIFEST.json` and `B/committed/MANIFEST.json`; each active manifest
was initialized with the normal campaign schema and an empty `shards` mapping.
This avoids mixing old and fresh keys for the same chapter. No cached shard was
rekeyed. Each variant received its own new `AXIOM_TARIFF_C1_CACHE` directory.
Completed fresh CH79 shards were later accepted by the unchanged script's
`evaluate --resume` check; the existing default cache was read only.

Timed command arguments, environment overrides and observed output are retained
in `logs/`. The main report distinguishes commands already run from proposed
continuation commands. A process-list and hardware-query discovery attempt were
denied (`ps`: operation not permitted; `sysctl`: operation not permitted);
neither was used to infer runtime or completion counts.
