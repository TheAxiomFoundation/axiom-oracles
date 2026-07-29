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
- Phase: TANF/SSI regenerated and dispositions revalidated; seven of ten SNAP
  suites regenerated, with CA/NC/SC still outstanding.

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
- Replaced eight stale `$HOME/axiom-oracles/programs/...` TANF references with
  repository-relative paths during local regeneration so the isolated worktree
  composed the audited files, not an unrelated historical checkout.
- Confirmed from the pinned PolicyEngine-US metadata that all nine oracle
  variables have `MONTH` definition periods. Confirmed the corresponding Axiom
  leaves are monthly, except the Arizona and SSI annual leaves whose new
  wrappers correctly divide by 12.
- Repointed Minnesota, New York, and Washington TANF from missing copied
  state-root directories to the canonical `rulespec-us` monorepo checkout,
  matching the already-working Arizona/Kansas composition pattern.
- Corrected the Kansas suite description from shelter group V to group I,
  matching both the bridge's fixed inputs and PolicyEngine's no-county fallback.
- The sandbox blocks `uv` from initializing its default cache under
  `$HOME/.cache/uv` (`sdists-v9/.git: Operation not permitted`). Verified the
  established read-only cache overlay used by the #423 lane instead: host
  `policyengine==4.18.9` plus cached `policyengine-us==1.767.3` and
  `policyengine-core==3.30.3`; the runtime reports all three exact versions.
- Prepared a clean, local-only RuleSpec clone at cached `origin/main`
  `c13cdf7dda5948e7a86ff0c317872f93743a2084` under `/private/tmp` because
  the `$HOME/rulespec-us` worktree is a dirty historical TANF branch and lacks
  three SNAP program specs. This clone is run input only and is not committed.
- Composed and compiled all eight TANF programs plus SSI successfully after the
  root fixes.
- Targeted validation passed 92 tests with 3 skips. One
  `test_materialize_ci_workspace` assertion remains stale: it requires the old
  `$HOME/axiom-oracles` symlink solely because it assumes the superseded
  absolute TANF program path; the repository-relative program path needs no
  such materialization. The containment order excludes test-file edits.
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

- Regenerated all eight TANF suites and SSI under the declared stack; every
  full report records PolicyEngine `4.18.9`, US `1.767.3`, and core `3.30.3`.
  The true-month raw residuals are AL 3, AZ 0, DE 0, GA 1, KS 218, MN 0,
  NY 36, WA 0, and SSI 2,990.
- Revalidated rather than silently carrying annualized disposition evidence:

  - deleted Arizona's expired four-row disposition;
  - pinned Georgia's surviving case to `0 / 164.970459` (exactly one twelfth
    of the legacy PE amount);
  - replaced Kansas's blanket prefix with seven exact county-group case sets
    (212 rows, each PE-Axiom = $43) and six individually pinned
    applicable-SSI assistance-unit rows;
  - replaced New York's blanket prefix with exact 30 both-positive and 6
    zero-left case sets, documenting 6 vanished and 6 new identities;
  - refreshed SSI's full 2,990-row evidence from a direct PE eligibility join
    and removed obsolete subtype counts and the now-within-tolerance
    `ecps-588` representative.

- Corrected the Kansas program and projector notes: the Axiom bridge fixes
  shelter group I, while PolicyEngine 1.767.3 derives actual county groups.
- Rebuilt Arizona TANF's dashboard copy from its regenerated full report after
  deleting the vanished four-row disposition, so the report now records a null
  dispositions file with no expired legacy entry.
- Restored the eight committed TANF config paths to the CI materializer's
  `$HOME/axiom-oracles/...` convention after regeneration; the focused
  materialization suite now passes all 7 tests. The temporary relative paths
  were an execution overlay, not a portable config change.
- `apply_dispositions.py --check` passes after the TANF/SSI refresh, and the
  focused disposition/requested-month test battery passes (22 tests).
- The SNAP composition preflight exposed two sandbox/toolchain constraints.
  The configured July 6 release binary predates `compile-composed`; a current
  offline rebuild recognizes it but rejects an unrelated noncanonical Unicode
  filename in the cached RuleSpec tree. No source checkout was altered.
  The committed compatibility fallback succeeds when its legacy resolver is
  pointed at the clean `/private/tmp` clone's parent, so the SNAP regeneration
  uses that established release engine and clean RuleSpec input.

## Next

1. Regenerate CA, NC, and SC SNAP, then verify all ten engine-version blocks.
2. Revalidate every SNAP disposition, including the California
   TANF-bridge/lone-minor replay and the January minimum-benefit class.
3. Refresh shared artifacts/counts and run the full `--check` chain.
4. Commit the final ledger, write the untracked worker report, and report HEAD.
