# dk-satser reference artifacts

Committed reference data for Denmark's official børne- og ungeydelse satser,
from the ministry's own pages (Skatte- og Vækstministeriet, svmn.dk — the
renamed Skatteministeriet). This is the second, EUROMOD-independent reference
leg for the dk child/youth-benefit suite: the amounts the administration
actually publishes, against which the statute-mechanism outputs are graded.

The reference is reviewer-independent: expected values come only from the
ministry pages, never from artifacts shared with the rulespec-dk
implementation.

## Artifacts

| File | What | Produced by |
|---|---|---|
| `satser_annual.csv` | Annual amounts per age band, 2022–2027; 2023 carries both printed values (base and incl. the Q1 660 kr. engangsforhøjelse) | ministry pages (see provenance) |
| `aftrapning_threshold.csv` | § 1 a aftrapningsgrænse series (2010 grundbeløb + regulated years as printed) | same |
| `provenance.json` | Page URLs, printed last-updated stamps, fetch date, printed quarterly/monthly amounts, ministry-rename note | same |

`tests/test_dk_satser_reference.py` is the CI-side validator. Trust model
(us-tariff-panel pattern): provenance stamps are mutable data files, so every
load-bearing identity is a reviewed constant in the test file — the CSV
bytes (sha256 pins), the full expected row sets, and the internal arithmetic
(quarterly×4 = annual and monthly×12 = annual for the printed period
amounts; 12-krone divisibility through 2025 and 24-krone divisibility from
2026 per LOV nr 1642; the 2023 supplement = exactly +660 per band). A
legitimate refresh updates the constants in the same reviewed diff.
