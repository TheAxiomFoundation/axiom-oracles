# P3 — NZ program-scoped dependency cones

Outcome: implemented and locally verified. The implementation commit is
`2eee532b3fcc300b2d5f9c0d054d0b80041aba70`. This file is the required fallback
because the ops checkout is read-only; no ops file was modified.

## Program cones

The jurisdiction ledger remains 229 open law-derived inputs plus 39 unique
bearing instruments, or 268 open dependencies. Each certificate now also
publishes the open subset attributed to its requested-output cone.

| Rank | Program | Reached inputs | Law-derived open | Bearing open | Scoped open | Jurisdiction open | Reached spine rows | Pending spine rows |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | `nz/acc-earners-levy` | 1 | 1 | 2 | 3 | 268 | 2 | 0 |
| 2 | `nz/winter-energy-payment` | 2 | 2 | 1 | 3 | 268 | 1 | 0 |
| 3 | `nz/main-benefits` | 13 | 11 | 1 | 12 | 268 | 7 | 0 |
| 4 | `nz/income-tax` | 1 | 1 | 25 | 26 | 268 | 8 | 0 |
| 5 | `nz/accommodation-supplement` | 28 | 26 | 3 | 29 | 268 | 5 | 0 |
| 6 | `nz/independent-earner-tax-credit` | 11 | 7 | 32 | 39 | 268 | 1 | 0 |
| 7 | `nz/working-for-families` | 91 | 80 | 33 | 113 | 268 | 33 | 0 |

ACC's trace root is
`nz:regulations/acc/earners_levy#acc_standard_earners_levy_including_gst`.
Its formula cone reaches only
`engine_request:acc_earnings_for_earners_levy`. Its two bearing instruments are
the IRD deductions-from-salary-and-wages guidance and the Goods and Services
Tax Act 1985. Thus its certificate reports 1 + 2 = 3 scoped open dependencies,
while retaining the jurisdiction count of 268. Its two reached spine rows are
encoded and none is pending.

## Attribution and gate behavior

Requested roots are read from the committed evaluation trace. Formula edges
and the topological evaluation order are read from the pinned compiled program.
The producer walks that graph afresh during `--check`; the committed
`programs` lists are checked against the derived result rather than trusted.

Of 288 grounding rows, 147 are reached by a certified view and 141 are reached
by none. The latter remain in the global ledger with `programs: []` and an
`attribution_reason`: 99 implicit legal surfaces, 27 eligibility-closure rows,
11 scenario rows, 3 harness-only engine requests, and 1 host rule. They are not
dropped from the jurisdiction count.

Pending bearing-instrument rows use the same sorted `programs` vocabulary.
Multi-owner instruments retain every owner. The central certificate gate
derives the law and bearing lists for program P from row attribution, retains
the global count, and requires P's scoped dependency count to be zero, P's
instrument frontier to be complete, and every spine row reached by P to be
non-pending. A ledger with no `programs` fields retains the pre-P3 global path
and four-field dependency block.

The v3 audit report now includes the ranked cone table and resolves its Q2/Q3
ownership questions. Dependency dispositions moved to schema v2 and the NZ
closure summary to v3.

## Honesty guards and reversion evidence

- Removing ACC from its reachable input's attribution, even while adding a
  plausible empty-owner reason, is rejected by canonical recomputation; the
  restored ledger rebuilds byte-for-byte.
- Moving the ACC input to another valid program cannot coordinate a cone
  shrink: a fresh full build walks the trace/formulas and rejects the forged
  list; restoration reproduces the baseline artifact.
- The unattributed host law row remains inside the global 268. Forging the
  jurisdiction block down to 267 is rejected; restoration validates.
- Missing or malformed input/instrument ownership, duplicate bearing rows,
  missing `attribution_reason`, forged scoped/global counts, and malformed or
  non-topological evaluation orders all red, with baseline restoration checks.
- The synthetic no-attribution mutant proves that a forged scoped summary
  cannot opt a legacy ledger into P3. Fresh DK and both US builds reproduce
  their committed bytes exactly; DK keeps its global four-field dependency
  block at 67 open and has no jurisdiction-count field.

The focused P3 files contain 22 passing tests. The full NZ selection contains
174 passing tests with 2,870 deselected.

## Gate receipts

- All ten NZ producer checks pass: IncomeExplorer, executable reproduction,
  both closure bootstraps, closure summary, exercise denominator, corpus gap
  scan, spine ledger, PCO reverse index, and v3 audit report.
- All seven NZ certificates were regenerated through
  `certify.build_certificate` and compare byte-for-byte with fresh builds.
- `uv run pytest -q -k nz`: 174 passed, 2,870 deselected.
- New P3 guard files: 22 passed.
- `uv run ruff check .`: pass.
- All six present non-NZ certificate files retain their starting SHA-256 bytes
  and are unchanged from branch start `04118a08b` and merge-base
  `9a8274b430`. A controlled DE check that bypassed only the known local replay
  boundary also reproduced all three DE certificate objects and bytes.
- The guarded simulated NZ refresh was run in an isolated clone. It completed
  NZ regeneration and the NZ producer chain, then stopped at the DE census
  during the global certification step. The simulation guard exited before
  fetch, reset, commit, or push; the shared worktree was untouched.
- The B2/C1 merge had left the corpus-gap producer ratcheted at 18 bearing
  instruments while its source ledger contained 39. This was reconciled: 24
  additional secondary documents are explicit missing-corpus rows and their
  three exact ITA roots are explicit present rows. The scan now records 314
  provisions (236 present, 78 missing); the adopted 174-row spine and its hash
  did not change.

## Limits that could not be made honest locally

- Whole `scripts/certify.py --check` cannot complete on Darwin arm64: the DE
  Kindergeld replay invokes a committed x86_64-linux binary. Linux CI is the
  global arbiter, as specified in the brief.
- For the same reason, the guarded simulated refresh stops only when it reaches
  the global DE certification step; its NZ portion completes.
- Literal byte identity with current `origin/main` was already impossible at
  the requested starting commit. All six present non-NZ certificates differed
  before P3 because upstream refreshed them after this branch diverged; neither
  tree contains UK or BE certificate JSON. P3 introduced zero non-NZ byte
  drift, but this report does not relabel the pre-existing cross-origin mismatch
  as a pass.
- The required initial `git fetch origin` was attempted but DNS resolution for
  GitHub was unavailable. Read-only remote metadata confirmed `origin/main` at
  `efbdede1f0d8cb0a5f09aafd4009618e7e6629a5` and the requested branch tip at
  `04118a08bd82dd4f3a61a0b5366a44692616b530`; the corresponding local refs were
  already at those SHAs.
