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
- Phase: period semantics reconciled; pre-regeneration validation in progress.

## Done

- Created an isolated worktree from the exact local `origin/main` ref.
- Confirmed the worktree branch tracks `origin/main`.
- Audited one committed report shape and all nine TANF/SSI configurations and
  program outputs before regenerating. The requested comparison period remains
  `2026-01` for every suite: changing it to a year would evade the runner fix.
- Reconciled the Axiom side to true-month units without changing any tolerance:

  | Suite | Period decision | Axiom comparison output |
  |---|---|---|
  | `al-tanf-ecps` | keep `2026-01` | `al_tanf_monthly_benefit` |
  | `az-tanf-ecps` | keep `2026-01` | `az_tanf_monthly_cash_benefit` |
  | `de-tanf-ecps` | keep `2026-01` | `de_tanf_monthly_benefit` |
  | `ga-tanf-ecps` | keep `2026-01` | `ga_tanf_monthly_benefit` |
  | `ks-tanf-ecps` | keep `2026-01` | new `ks_tanf_monthly_maximum_benefit` wrapper |
  | `mn-tanf-ecps` | keep `2026-01` | `mn_mfip_monthly_cash_benefit` |
  | `ny-tanf-ecps` | keep `2026-01` | `ny_tanf_benefit` |
  | `wa-tanf-ecps` | keep `2026-01` | `wa_tanf_monthly_benefit` |
  | `ssi-ecps` | keep `2026-01` | new `ssi_monthly_benefit` household output |

- Kept each literal `$25` TANF/SSI tolerance unchanged; movements must be
  exposed and disposition evidence revalidated, not absorbed by tolerance.
- Added the declared Python/PolicyEngine pins to every affected config that did
  not already carry them and corrected Minnesota's stale New York description.
- Captured the committed pre-regeneration baseline:

  | Suite | Raw mismatches | Unexplained |
  |---|---:|---:|
  | `al-snap-ecps` | 53 | 23 |
  | `az-snap-ecps` | 597 | 0 |
  | `ca-snap-ecps` | 684 | 96 |
  | `fl-snap-ecps` | 834 | 834 |
  | `ga-snap-ecps` | 250 | 80 |
  | `ma-snap-ecps` | 255 | 83 |
  | `nc-snap-ecps` | 99 | 71 |
  | `ny-snap-ecps` | 354 | 349 |
  | `sc-snap-ecps` | 181 | 106 |
  | `tn-snap-ecps` | 68 | 41 |
  | `al-tanf-ecps` | 0 | 0 |
  | `az-tanf-ecps` | 4 | 0 |
  | `de-tanf-ecps` | 0 | 0 |
  | `ga-tanf-ecps` | 1 | 0 |
  | `ks-tanf-ecps` | 6 | 0 |
  | `mn-tanf-ecps` | 0 | 0 |
  | `ny-tanf-ecps` | 36 | 0 |
  | `wa-tanf-ecps` | 0 | 0 |
  | `ssi-ecps` | 3,067 | 0 |

## Next

1. Validate program composition/mapping and the exact cached oracle stack.
2. Regenerate all 19 suites and verify every report's engine-version block.
3. Revalidate dispositions, including materially shifted deltas and the
   California TANF-bridge/lone-minor evidence.
4. Refresh shared artifacts and counts and run the full `--check` chain.
5. Write the untracked worker report and finish this ledger.
