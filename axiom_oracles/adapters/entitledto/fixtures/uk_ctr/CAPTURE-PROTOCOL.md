# entitledto UK-CTR capture protocol

These fixtures are the **recorded** side of the entitledto Council Tax Reduction
oracle. They ship as `pending_capture` stubs — inputs filled, `outputs: null` —
and a human fills the outputs by running each case once on the public
calculator. This document is that procedure.

## Why capture is manual (read first)

entitledto is a commercial product. Its legal notices state:

> "You must not conduct any systematic or automated data collection activities
> (including without limitation scraping, data mining, data extraction and data
> harvesting) on or in relation to our website without our express written
> consent."
> — entitledto legal notices, https://www.entitledto.co.uk/legal-notices/

So the adapter never drives entitledto programmatically, and **CI never
captures**. The only permitted path is a person using the free public calculator
as intended — one case at a time, human-paced, for a small research cross-check.
Do not script it, do not bulk-run it, and **never invent, estimate, or
back-fill a value**: an uncaptured fixture stays `pending_capture`.

If entitledto grants written API/research access (see the report's
commercial-API section), capture moves to that sanctioned channel and this
manual path is retired.

## What to enter (per case)

Each `<case_id>.json` carries an `inputs` block that is the exact manual-entry
record for that case — relationship status, postcode (which selects the billing
authority and its CTR scheme), council tax band and modelled annual liability,
tenure and rent, each adult's ages and incomes, children's ages, and capital.
Enter those, taking the defaults entitledto offers for anything not listed
(no disabilities, no carer, no existing benefits in payment).

Council tax liability is **entitledto-derived**: it computes the bill from the
postcode and band. Enter the band shown in `council_tax.band`; if entitledto
lets you type the annual council tax, enter `council_tax.annual_liability_gbp`.
Then **record the council tax liability entitledto actually used** in
`provenance.entitledto_council_tax_liability_gbp` — the reconciliation step
re-runs PolicyEngine and the statutory hand-check against *that* liability so the
schemes stay commensurable (the annual liability in `inputs` is the modelled
placeholder until then).

## What to record

On the results page, record the **annual** amount for each row the calculator
shows (also note the weekly figure it displays, for provenance):

| fixture output key      | entitledto result row                          |
|-------------------------|------------------------------------------------|
| `council_tax_reduction` | Council Tax Reduction / Council Tax Support     |
| `universal_credit`      | Universal Credit                                |
| `housing_benefit`       | Housing Benefit (renters only; else omit)       |
| `pension_credit`        | Pension Credit (pension-age only; else omit)    |

Then edit the fixture:

1. Set `provenance.capture_status` to `"captured"`.
2. Set `provenance.capture_date` (ISO date) and `provenance.captured_by`.
3. Set `provenance.calculator_version` if the results page shows a scheme/version
   or "rates as at" date; else record the date you ran it.
4. Set `provenance.entitledto_council_tax_liability_gbp` to the liability
   entitledto used.
5. Fill `outputs`, e.g.:

```json
"outputs": {
  "council_tax_reduction": {"annual_gbp": 1181.00, "weekly_gbp": 22.71},
  "universal_credit": {"annual_gbp": 4510.00, "monthly_gbp": 375.83},
  "housing_benefit": {"annual_gbp": 0.0},
  "pension_credit": {"annual_gbp": 0.0}
}
```

`annual_gbp` is authoritative; `weekly_gbp` / `monthly_gbp` are provenance. If
you only have the weekly figure, record `weekly_gbp` and the runner annualises
(×52). Record `0.0` for a row the calculator shows as nil; omit a row that does
not apply (e.g. Pension Credit for a working-age case).

## Pacing and scope

- One case at a time, with several seconds of genuine reading between steps.
- At most the eight cases in this directory per session.
- Accept the cookie banner as you normally would; do not circumvent any login
  wall or bot check.

## After capturing

Run the validator before committing — it fails loudly on a half-filled fixture,
so a `captured` fixture can never ship without provenance and a CTR amount:

```python
from axiom_oracles.adapters.entitledto import load_captures_by_id, validate_capture
for cid, cap in load_captures_by_id().items():
    problems = validate_capture(cap)
    assert not problems, (cid, problems)
```

Then rebuild the comparison report so the captured cases grade against
PolicyEngine-UK and the statutory hand-check:

```
python scripts/run_uk_ctr_entitledto_report.py
```
