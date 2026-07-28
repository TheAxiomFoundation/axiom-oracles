# CA SNAP 441 repair — round 2

## State

- Branch: `triage/ca-snap-441`
- Round-2 base: `102b4edd5875fbe5e856daea0fafa9708a37003b`
- Audit frame: defensive correctness and completeness.
- The round-1 report at review commit `364f7066` is read.
- Starting canonical accounting is 441 formerly unexplained rows split into
  325 bridge dispositions, 20 upstream-engine-gap dispositions, and 96 rows
  still unexplained. The 243 pre-existing BBCE rows are out of repair scope
  and must remain byte-identical.
- Blocking repairs:
  1. remove any disposition that lacks a complete live per-case
     counterfactual, including the four rows for `ecps-59082` and
     `ecps-62506`;
  2. make the tracer and builder replay the committed disposition set from an
     explicit pre-disposition report state;
  3. reserve the version-drift note for the three cases that actually close on
     PolicyEngine-US 1.767.3 and record the other 74 as persistent unexplained
     mismatches;
  4. regenerate all canonical and served artifacts with exact annotation
     parity.

## Done

- Confirmed the worktree and branch.
- Read the full round-1 adversarial findings and sampled-counterfactual table.
- Confirmed `WORKER-REPORT.md` is intentionally untracked and currently holds
  the round-1 report.
- Established this tracked repair ledger before implementation changes.

## Next

1. Inventory the two evidence scripts, disposition/report schemas, artifact
   generators, and all references to the old 77-row and 96-row claims.
2. Reconstruct the challenged self-employment class from live trace evidence;
   keep only entries whose full stated mechanism closes within tolerance.
3. Add explicit replay-base/provenance handling and deterministic
   byte-identical replay checks.
4. Apply the corrected disposition set, regenerate every served artifact, and
   refresh scoreboard, burn-down, history, and report text.
5. Run the complete repository `--check` chain and focused tests; record exact
   commands and results in the final untracked worker report.
