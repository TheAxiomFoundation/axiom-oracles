# Month-scoped suite regeneration audit

## State

- Branch: `data/month-fix-regen`
- Base: `origin/main` at `819f370bf0346e4a6a8dfb1c8c4f0d873d6d0340`
- Purpose: defensively regenerate the 19 US month-scoped comparison suites after
  the requested-month PolicyEngine runner fix merged in `86be7721`.
- Required oracle stack: `policyengine==4.18.9`,
  `policyengine-us==1.767.3`, `policyengine-core==3.30.3`.
- Containment: the 19 suites, their dispositions, shared regenerated artifacts,
  row notes whose counts change, and this ledger only.

## Done

- Created an isolated worktree from the exact local `origin/main` ref.
- Confirmed the worktree branch tracks `origin/main`.

## Next

1. Inventory the committed suite machinery and exact 19-suite file set.
2. Reconcile TANF and SSI annualized-period semantics before regeneration,
   recording a decision for each of the nine suites.
3. Verify/reproduce the pinned cached oracle stack.
4. Regenerate all suites, revalidate dispositions and shifted CA SNAP evidence,
   then run the full `--check` chain.
5. Refresh shared artifacts and counts, write the untracked worker report, and
   finish the ledger.
