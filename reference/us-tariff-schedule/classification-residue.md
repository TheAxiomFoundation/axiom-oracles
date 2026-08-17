# C1 classification residue — 2026-08-17

Classification stopped fail-closed with conservation passing and 9,503,693
unexplained mismatch units across 1,654,848 incidence signatures. The reviewed
mapping and instrument receipts referenced by the task as
`sol-c1-dispositions-brief.md` are not present in this checkout or its Git
history. The existing disposition ledger contains class-name stubs and pending
receipts only. Broad slot selectors would therefore assign heterogeneous
families without the required reviewed authority.

| Slot | Residual units |
|---|---:|
| total | 4,389,045 |
| forced_labor_section_301 | 1,499,038 |
| section_122 | 1,485,889 |
| section_232 | 1,268,014 |
| base | 689,043 |
| brazil_section_301 | 93,198 |
| ieepa | 38,636 |
| china_section_301 | 31,446 |
| section_201 | 9,384 |

The data review verified that forced-labor mismatches occur only in revisions
`bnd_2026-07-24` (750,048 units) and `bnd_2026-07-31` (748,990 units), are all
negative, and include observed deltas of -0.10 and -0.125 among 202 rounded
delta values. Other large slots are not uniform: Section 122 contains both
signs and 686 rounded delta values; Section 232 contains both signs and 2,308
rounded delta values; total contains both signs and 9,877 rounded delta values.
Those populations cannot honestly be collapsed to the pending stub classes
without the missing reviewed mapping and receipts.

The full signature sidecar, including normalized selector fields and unit
counts, is identified by path and SHA-256 in `classification-receipt.json`.
