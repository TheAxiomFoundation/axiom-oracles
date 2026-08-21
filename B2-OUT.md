# NZ Brief B2 — instrument frontier burn-down

Review date: 2026-08-21. Certified period: 2026-04-01 through 2027-03-31.

The requested ops destination, `/Users/maxghenis/TheAxiomFoundation/ops/nz-lane/_cert/sol-b2-instrument-burndown.md`, is outside this worktree's writable roots, so this committed file is the requested fallback.

## Act results

| Act | Original pending | Encoded | Excluded with reason | Bearing pending / queued | Pending → 0? |
|---|---:|---:|---:|---:|---|
| Accident Compensation Act 2001 | 65 | 0 | 63 | 2 | No |
| Income Tax Act 2007 | 76 | 0 | 42 | 34 | No |
| Social Security Act 2018 | 56 | 0 | 53 | 3 | No |
| **Total** | **197** | **0** | **158** | **39** | **No** |

The non-zero result is intentional under the CERTIFIED.md bearing rule: every remaining item genuinely bears on a computed surface and is not yet proof-bound by the named module. None was classified around. All 39 are recorded in `closure/nz/instrument-encode-queue.json`, which is sorted, unique, and exactly reconciled to the aggregate bearing frontier.

Honest exclusion classes used in this burn-down:

- ACC: 63 `spine_excluded_surface`.
- Income Tax: 20 `spine_excluded_surface`, 11 `outside_certified_period`, 9 `superseded_regime`, and 2 `not_in_force`.
- Social Security: 43 `superseded_regime` and 10 `spine_excluded_surface`.

The in-period anchor instruments remained encoded after cross-check: Accident Compensation (Earners’ Levy) Regulations 2025, the Social Security Rates Order 2026, and the Income Tax (Tax Credit) Order 2025.

## Unresolved source review

No row was unresolved, walled, or ambiguous. Some direct NZ Legislation `/en/latest/` requests returned HTTP 403 on this host, but official indexed legislation text/PDF results and official Inland Revenue summaries exposed enough operative text to decide every one of the 197 rows. The 39 pending rows are pending because they require encoding, not because source review failed.

The broader pre-existing official-listing capture gap remains 136 rows; it is outside this 197-row disposition set and remains disclosed in the closure artifact.

## Certificate frontier completeness

| Certificate | Encoded | Excluded | Pending | Total | Frontier complete? |
|---|---:|---:|---:|---:|---|
| `nz/acc-earners-levy` | 2 | 130 | 2 | 134 | No |
| `nz/accommodation-supplement` | 3 | 67 | 3 | 73 | No |
| `nz/income-tax` | 1 | 101 | 25 | 127 | No |
| `nz/independent-earner-tax-credit` | 7 | 91 | 32 | 130 | No |
| `nz/main-benefits` | 3 | 66 | 1 | 70 | No |
| `nz/winter-energy-payment` | 0 | 68 | 1 | 69 | No |
| `nz/working-for-families` | 8 | 93 | 33 | 134 | No |
| **Global unique frontier** | **13** | **295** | **39** | **347** | **No** |

## Gates and commits

- Instrument producer check: passed after each act batch and after final regeneration.
- Full mutant file: 18 passed, including exact encode-queue/frontier reconciliation.
- Simulated NZ refresh: passed for `nz-treasury-incomeexplorer`.
- Certification: `certificates up to date` under `certify.py --check`.
- NZ closure and v3 audit report checks: passed.
- No `PROGRESS.md` change; no push or PR.

Act commits:

- `f3bccdfbb` — ACC: 0 encoded, 63 excluded, 2 pending.
- `4d810f6df` — Income Tax: 0 encoded, 42 excluded, 34 pending.
- `f211ffea2` — Social Security: 0 encoded, 53 excluded, 3 pending.

Final committed implementation and gate-artifact SHA (before this report-only commit): `a6a8bd7bb0b1347bfd425c176c92a77655eb6709`.
