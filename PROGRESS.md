# Progress

## State

- Branch: `fix/snap-concept-citations`
- Base: `origin/main`
- Scope: publish the already-applied SNAP concept-ID relabeling, verify it, and update the separately pinned report hashes in `TheAxiomFoundation/ops`.
- Guardrails: do not run comparison suites, do not change committed numeric values, and do not touch toolchain, CI, or CODEOWNERS.

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

## Next

- Commit and publish the axiom-oracles PR.
- Recompute the three affected report SHA-256 values in a separate ops worktree, update PR #7's branch, and publish the final report.
