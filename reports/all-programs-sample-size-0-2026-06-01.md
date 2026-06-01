# All Programs Sample Size 0 Refresh - 2026-06-01

## Scope

Reran every registered comparison with `--sample-size 0`:

```bash
uv run python scripts/run_comparison.py al-snap-ecps --sample-size 0 --summary
uv run python scripts/run_comparison.py ca-snap-ecps --sample-size 0 --summary
uv run python scripts/run_comparison.py co-snap-ecps --sample-size 0 --summary
uv run python scripts/run_comparison.py fiit-ecps --sample-size 0 --summary
uv run python scripts/run_comparison.py ma-snap-ecps --sample-size 0 --summary
uv run python scripts/run_comparison.py ny-snap-ecps --sample-size 0 --summary
uv run python scripts/run_comparison.py tn-snap-ecps --sample-size 0 --summary
```

The dashboard-backed runs refreshed `dashboard/public/data/*.json`. The CO run
does not currently feed the dashboard and remains diagnostic.

## Dashboard Results

| Program | Cases | Eligibility | Benefit / amount | Mismatch entries |
| --- | ---: | ---: | ---: | ---: |
| AL SNAP | 704 | 700 / 704 | 672 / 704 | 36 |
| CA SNAP | 4,420 | 4,296 / 4,420 | 4,072 / 4,420 | 472 |
| MA SNAP | 896 | 854 / 896 | 819 / 896 | 119 |
| NY SNAP | 2,288 | 2,260 / 2,288 | 2,116 / 2,288 | 200 |
| TN SNAP | 852 | 846 / 852 | 813 / 852 | 45 |

## Federal Income Tax

- Tax units: 7,039
- Compared values: 201,447
- Mismatches: 172
- Agreement: 99.9146%
- EITC: 77,257 / 77,429 matched
- CTC: 35,195 / 35,195 matched
- Standard deduction: 21,117 / 21,117 matched
- Capital-gain definitions: 14,078 / 14,078 matched
- Payroll OASDI/Medicare employee and employer surfaces: all matched

## Colorado SNAP Diagnostic

- Cases: 694
- Compared values: 694
- Mismatches: 694

The CO comparison currently returns Axiom `None` for `snap_benefit` across the
state slice, so it is not a usable alignment report. This should be treated as a
CO wiring/comparison-surface issue before adding it to the dashboard.

## Config Change

Updated the comparison defaults for these previously sampled runs:

- `comparisons/ca-snap-ecps.yaml`: `sample_size: 0`
- `comparisons/co-snap-ecps.yaml`: `sample_size: 0`
- `comparisons/fiit-ecps.yaml`: `sample_size: 0`
- `comparisons/ny-snap-ecps.yaml`: `sample_size: 0`

This prevents future dashboard refreshes from silently sampling before the state
filter. NY now shows the full 2,288-household state slice instead of the earlier
92-household sampled slice.
