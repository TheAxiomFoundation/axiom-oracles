# C1 bounded classification residue — 2026-08-17

The repaired classification leaves S1 false: 8,934,110 of 9,503,693 mismatch
units are classified, 569,583 are unexplained after derived-total propagation,
engine errors are zero, and conservation is `PASS`.

| Bounded class | Component units | Non-slot bounds | Attribution |
|---|---:|---|---|
| fed-false-family-forced-labor | 1,241,176 | delta {-12.5, -10}; date >= 2026-07-24 | axiom-attributed-open |
| s122-entry-status-lines | 779,746 | no-exemption complement; date; [-10, +10] | input-comparability |
| non-metal-232-family | 754,434 | outside notes 16/19 union; negative delta | input-comparability |
| s122-gn6-lines | 687,295 | GN6 conditional table; date; [-10, +10] | input-comparability |
| column2-gn3b | 683,334 | CU/KP/BY/RU origin list | upstream-methodology |
| vintage-revision-232 | 513,556 | notes 16/19 union; [-150, +50] | input-comparability |
| fed-false-family-brazil | 93,198 | BR; delta {-25, -12.5, -2.5}; date | axiom-attributed-open |
| legal-date-boundary-ieepa | 38,392 | positive delta; 2026-02-15..2026-02-24 | input-comparability |
| s122-ch98 | 18,848 | chapter 98 list; +10; statutory window | input-comparability |
| s201-stale-proxy | 9,384 | delta {-14.5, -30, -40}; after expiry | upstream-methodology |
| preference-entry-semantics | 5,709 | exact origin list | input-comparability |
| vintage-revision-301 | 4,716 | note 20 union; [-100, +25] | input-comparability |
| s122-unconditional-exempt-lines | 0 | 2(aa)(ii)/(iii) tables; statutory window | input-comparability |

Direct unexplained residue is 284,860 component units: 257,862 forced-labor
rows outside the required two-delta bound, 26,730 China-301 rows outside the
note-20 generated memberships, 244 IEEPA rows outside the bounded
direction/window, and 24 metal-232 rows outside the declared delta range. The
remaining 284,723 unexplained units are totals whose component composition
contains at least one of those direct unexplained signatures.

The note-52 corpus finding and the absence of a B1.6 generated note-52 table
are recorded in `note52-corpus-receipt.json`. Upstream-methodology classes are
receipted divergences, not agreement.
