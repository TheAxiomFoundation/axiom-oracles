# entitledto UK-CTR capture protocol

These fixtures are the **recorded** side of the entitledto Council Tax Reduction
oracle. They ship as `pending_capture` stubs — inputs filled, `outputs: null` —
and are filled only under the permission described below. This document is that
procedure.

## Permission first (read before capturing anything)

entitledto is a commercial product. Capturing this eight-case research grid is
**not** sanctioned by the free public calculator's terms, for two independent
reasons:

- **Systematic collection is barred without written consent.** entitledto's legal
  notices state: *"You must not conduct any systematic or automated data
  collection activities (including without limitation scraping, data mining, data
  extraction and data harvesting) on or in relation to our website without our
  express written consent"* (https://www.entitledto.co.uk/legal-notices). Running
  a defined grid of hypothetical households and recording the outputs is
  systematic collection — the "systematic" bar applies even though a person, not
  a script, does the typing.
- **The free calculator is capped and personal-use.** Its current terms restrict
  the free site to personal use, limit unregistered users to a small number of
  calculations per day, and restrict saving/republishing of results. (Confirm the
  current figures on the live terms before relying on them; they have changed over
  time.)

**So do not capture these cases on the free calculator.** Capture requires
entitledto's **express written consent** — in practice a research or API licence
(see the lane report's commercial-API section and the draft outreach). Until that
is in hand, every fixture stays `pending_capture`. The adapter never probes
entitledto, and **no value is ever invented, estimated, or back-filled** — an
uncaptured fixture stays uncaptured.

Once permission is granted, capture through the sanctioned channel (the licensed
API, or a manual run entitledto has explicitly authorised), following the steps
below.

## What to enter (per case)

Each `<case_id>.json` carries an `inputs` block that is the exact manual-entry
record for that case — relationship status, postcode (which selects the billing
authority and its CTR scheme), council tax band and modelled annual liability,
tenure and rent, each adult's ages and incomes, children's ages, and capital.
Enter those, taking the calculator's defaults for anything not listed (no
disabilities, no carer, no existing benefits in payment). All adult income
amounts are **annual GBP, gross** (before income tax and National Insurance),
per the record's `income_basis`.

Council tax liability is **entitledto-derived**: it computes the bill from the
postcode and band (and applies any single-person 25% discount). Enter the band
shown in `council_tax.band`. Then **record the council-tax liability entitledto
actually used** in `provenance.entitledto_council_tax_liability_gbp` — this is a
*required* field for a captured fixture, because the report reconciles the
statutory hand-check (and flags PolicyEngine parity) against that liability, not
the modelled placeholder in `inputs`.

## What to record

On the results page, record the **annual** amount for each row the calculator
shows. Annual is authoritative; also note the weekly figure for provenance, but
do not derive the annual from a penny-rounded weekly (£22.71 × 52 = £1,180.92 ≠
£1,181 — a rounding gap wider than the £0.01 comparison tolerance).

| fixture output key      | entitledto result row                          |
|-------------------------|------------------------------------------------|
| `council_tax_reduction` | Council Tax Reduction / Council Tax Support     |
| `universal_credit`      | Universal Credit                                |
| `housing_benefit`       | Housing Benefit (renters only; else omit)       |
| `pension_credit`        | Pension Credit (pension-age only; else omit)    |

Then edit the fixture:

1. Set `provenance.capture_status` to `"captured"`.
2. Set `provenance.capture_date` (ISO date) and `provenance.captured_by`.
3. Set `provenance.entitledto_council_tax_liability_gbp` to the liability
   entitledto used (required).
4. Set `provenance.calculator_version` if the results page shows a scheme/version
   or "rates as at" date; else record the date you ran it.
5. Fill `outputs` with **annual** amounts, e.g.:

```json
"outputs": {
  "council_tax_reduction": {"annual_gbp": 1181.00, "weekly_gbp": 22.71},
  "universal_credit": {"annual_gbp": 4510.00, "monthly_gbp": 375.83},
  "housing_benefit": {"annual_gbp": 0.0},
  "pension_credit": {"annual_gbp": 0.0}
}
```

`annual_gbp` is authoritative. Record `0.0` for a row the calculator shows as
nil; omit a row that does not apply (e.g. Pension Credit for a working-age case).
Values must be finite, non-negative numbers — never a boolean, and never blank.

## Validation (before committing a capture)

Run the validator; it fails loudly on a half-filled or malformed fixture, and the
runner refuses to grade anything that does not pass (fail-closed):

```python
from axiom_oracles.adapters.entitledto import load_captures_by_id, validate_capture
for cid, cap in load_captures_by_id().items():
    problems = validate_capture(cap)
    assert not problems, (cid, problems)
```

Then rebuild the report so the captured cases grade against PolicyEngine-UK and
the statutory hand-check:

```
python scripts/run_uk_ctr_entitledto_report.py
```
