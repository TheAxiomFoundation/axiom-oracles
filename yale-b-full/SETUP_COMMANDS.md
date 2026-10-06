# Candidate B continuation setup

Read the org rules and prior checkpoint report, setup commands, logs, B workspace,
and diagnostic helpers before preparing this continuation.

The assigned outer checkout was detached and initially clean. Attempting
`git -c core.fsmonitor=false switch -c subfleet/yale-campaign-b-full` failed:
Git could not create a branch ref in its shared metadata outside this workspace.
The command did not create a branch or commit. A writable local B checkout was
created on `subfleet/yale-campaign-b-full`, preserving the previous lane's history.

Clone and checkout commands completed in this workspace. The following shell command chain was submitted; its rsync portion was interrupted with exit 130 before the cache/log destinations appeared. Commands later in that chain are not claimed completed:

```sh
mkdir -p yale-b-full/B yale-b-full/helpers yale-b-full/prior-checkpoint yale-b-full/logs
git clone --shared --no-checkout /Users/maxghenis/.subfleet/worktrees/20260923-140123-yale-campaign-full-v2/yale-full-run/B/oracles yale-b-full/B/oracles
git -C yale-b-full/B/oracles switch -c subfleet/yale-campaign-b-full origin/subfleet/yale-campaign-full-v2
git clone --shared --no-checkout /Users/maxghenis/.subfleet/worktrees/20260923-140123-yale-campaign-full-v2/yale-full-run/B/rulespec-us yale-b-full/B/rulespec-us
git -C yale-b-full/B/rulespec-us checkout --detach c62645022a8b2fcb5f9e6afdc2def2c8d68c2baf
rsync -a --exclude=.git --exclude=target --exclude=dist --exclude=.venv --exclude=node_modules /Users/maxghenis/.subfleet/worktrees/20260923-140123-yale-campaign-full-v2/yale-full-run/B/oracles/ yale-b-full/B/oracles/
rsync -a --exclude=.git --exclude=target --exclude=dist --exclude=.venv --exclude=node_modules /Users/maxghenis/.subfleet/worktrees/20260923-140123-yale-campaign-full-v2/yale-full-run/B/rulespec-us/ yale-b-full/B/rulespec-us/
rsync -a /Users/maxghenis/.subfleet/worktrees/20260923-140123-yale-campaign-full-v2/yale-full-run/B/cache/ yale-b-full/B/cache/
rsync -a /Users/maxghenis/.subfleet/worktrees/20260923-140123-yale-campaign-full-v2/yale-full-run/logs/ yale-b-full/prior-checkpoint/logs/
```

After the interrupted rsync chain, scoped `shutil.copytree` calls copied B/cache, logs and B/committed, and `shutil.copy2` copied the six preparation/manifest files. `copy-recovery.json` records the cache/log copy intervals. The Git clones already contain the retained source history. Both prior repositories and local rulespec-us were subsequently observed clean; local oracles differs only in relocated manifest path metadata.

Selected prior reports and unchanged diagnostic helpers were copied using
`shutil.copy2`. All copying excludes Git metadata, dependencies and build outputs.
Preparation receipts were verified, not regenerated. `verify_setup.py` archives
the exact starting manifest and verifies the original manifest, receipts, engine,
current keys and shard hashes before relocating only the two cache path strings.
The following campaign resume check is separately logged to prove acceptance.

Setup verification exited 0 (`logs/setup-verification.json`), matching the pinned engine, B rulespec commit, unchanged campaign and selector files, five retained preparation inputs/receipts, both current keys and both compressed shard hashes. The relocated manifest is followed by an official `evaluate --chapters 29,79 --workers 3 --resume` check under `nice -n 10`, exit 0: both chapters skipped. The priority wrapper emitted `setpriority: Operation not permitted`; `B-priority-preflight` independently exited 2 because the observed niceness remains 0 rather than the required 10. No remaining-chapter evaluation was started at this checkpoint.
