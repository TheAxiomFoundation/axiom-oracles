# Progress

## State

- Branch: `fix/snap-concept-citations`
- Base: `origin/main`
- Scope: publish the already-applied SNAP concept-ID relabeling, verify it, and update the separately pinned report hashes in `TheAxiomFoundation/ops`.
- Guardrails: do not run comparison suites, do not change committed numeric values, and do not touch toolchain, CI, or CODEOWNERS.
- Local implementation and verification are complete.
- Remote publication is blocked in this environment: both authorized Git pushes fail because `github.com` cannot resolve. A read-only GitHub connector check confirms that the axiom branch is not present remotely and no PR exists for it; the connector's attempted Git-data write was cancelled.

## Done

- Confirmed the expected branch and inspected the working-tree scope.
- Confirmed the relabeling is present across the expected source, comparison, report, dashboard, documentation, script, and test files.
- Independently verified all 112 modified files byte-for-byte:
  - transforming each `HEAD` blob with only the two requested old-to-new ID substitutions exactly reproduces the working file;
  - normalizing the old and new IDs to common sentinels makes every before/after file byte-identical;
  - result: zero other byte changes, so no committed numeric value moved.
- Counted 8,024 removed and 8,024 added physical lines. Those lines contain 63,826 literal ID substitutions (32,560 benefit and 31,266 eligibility) because many case-report JSON files are minified.
- Ran the requested full pytest command from an offline writable mirror of the machine's existing `uv` cache: 1,996 passed, 59 skipped, and 3 failed.
- Reproduced the three failures against `origin/main`:
  - the Ohio RuleSpec output-set failure and dashboard `npx esbuild` network failure are pre-existing;
  - the refreshed-report no-op test passed on `origin/main`, proving its branch failure was rename-caused.
- Traced the rename-caused failure to 13 stale `overview.json` source-byte counts: the new IDs are nine bytes shorter. Regenerated only the dashboard overview (no comparison execution), changing only those integrity byte counts beyond the ID substitutions, and verified the targeted no-op test now passes.
- Reran the full requested pytest command after the fix: 1,997 passed, 59 skipped, and 2 failed. Both remaining failures reproduce on `origin/main`: stale local Ohio RuleSpec outputs and unavailable npm networking for `npx esbuild`.
- Audited all 26 statutory/regulatory occurrences (22 IDs, 17 provision prefixes) in `case.py` and `concept_mappings.yaml` against both report-pinned corpus commits:
  - 10 prefixes resolve exactly and 6 payroll prefixes are operationally grounded through exact parent-section rows;
  - `us:statutes/42/1786#wic_eligible` is the sole further non-resolving citation, at `case.py:116` and `concept_mappings.yaml:2143,2149`;
  - confirmed it also remains absent at the current corpus `origin/main`; left it unchanged as required.
- Committed the relabeling after a final exact-transform audit of all 111 remaining files; no old SNAP statutory IDs remain and no forbidden toolchain, CI, or CODEOWNERS paths were touched.
- Independently recomputed the three ops-pinned report hashes from the post-relabeling bytes:
  - `axiom-policyengine-co-snap-ecps.json`: `4be1a737a517ef65719c336395bfa458b1ee298c2b4816e628400af6a9224219` (changed);
  - `axiom-snapqc-co-snap.json`: `bc2cd881116c0d2a67ee2a587fbd4c850975fb784f8e93338df60801c4235385` (unchanged);
  - `axiom-policyengine-fiit-ecps.json`: `7caca46fc19e19609ca04d319d9e73d832da13d67901dc325329430d9043f51d` (unchanged).
- Updated `launch-readiness/PUBLISHED-NUMBERS-PIN.md` in a separate ops Git worktree, including the relabeled mismatch concept and an explicit citation-only/no-suite-rerun note. Verified every published-number table is unchanged and committed the update as ops commit `7b507d2`.
- Attempted non-force pushes to both exact branch names. Both reached the same DNS blocker; neither remote branch was changed and no PR was merged.
- Wrote the final handoff to `FINAL_REPORT.md`.

## Next

- From an environment with GitHub connectivity, push `fix/snap-concept-citations`, open the axiom-oracles PR referencing #401 without merging it, and push ops commit `7b507d2` to `launch/provenance-pin`.
