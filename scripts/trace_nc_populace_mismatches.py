#!/usr/bin/env python
"""Trace NC resident-core Populace mismatches to PolicyEngine's components.

For every compared North Carolina TaxUnit in a state-tax Populace campaign
report, recompute the section 105-153.5 deduction from PolicyEngine's own
component values two ways:

* PolicyEngine's reading: ``nc_itemized_deductions`` as PolicyEngine computes
  it (policyengine-us before 2.60.4 adds ``mortgage_interest``, which includes
  ``non_deductible_mortgage_interest``, under the $20,000 cap);
* the statute's reading: min(deductible_mortgage_interest + real_estate_taxes,
  20000) + charitable + medical, since section 105-153.5(a)(2)b allows only
  interest allowed under Code section 163(h).

It then predicts the Axiom value as 3.99 percent of PolicyEngine's
``nc_taxable_income`` adjusted by the deduction difference, floored at zero.
If the statute reading reproduces Axiom on every unit, the reading is the
whole mismatch mechanism.

From policyengine-us 2.60.4 the two readings agree, so on a current oracle the
trace should find no mismatch and move no unit's deduction beyond float32
storage noise; a unit that moves further shows a new divergence to examine.

Usage:
    python scripts/trace_nc_populace_mismatches.py CAMPAIGN.json OUT.json
"""

from __future__ import annotations

import json
import sys
from importlib.metadata import version
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.bridges.population import load_populace_dataset  # noqa: E402
from axiom_oracles.bridges.state_tax_populace import (  # noqa: E402
    load_state_tax_populace_contract,
)
from axiom_oracles.bridges.state_tax_populace_runner import (  # noqa: E402
    validate_campaign_dataset_identity,
)

YEAR = 2026
RATE = 0.0399
MORTGAGE_AND_PROPERTY_TAX_CAP = 20000.0


def main() -> int:
    campaign_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])
    campaign = json.loads(campaign_path.read_text())
    state = campaign["comparison"]["states"]["NC"]
    axiom = {int(c["tax_unit_id"]): float(c["axiom"]) for c in state["cases"]}
    policyengine = {
        int(c["tax_unit_id"]): float(c["policyengine"]) for c in state["cases"]
    }
    mismatch_ids = sorted(int(m["tax_unit_id"]) for m in state["mismatches"])

    identity: dict = {}
    dataset = load_populace_dataset(
        "us", year=2024, command="trace-nc-populace-mismatches", provenance=identity
    )
    validate_campaign_dataset_identity(
        identity, contract=load_state_tax_populace_contract()
    )
    if identity.get("revision") != campaign["dataset_identity"]["revision"]:
        raise SystemExit("Populace revision differs from the campaign report")
    from policyengine_us import Microsimulation

    sim = Microsimulation(dataset=dataset)

    def tax_unit(variable: str) -> np.ndarray:
        return np.asarray(sim.calculate(variable, period=YEAR).values, dtype=float)

    def person_sum(variable: str) -> np.ndarray:
        return np.asarray(
            sim.calculate(variable, period=YEAR, map_to="tax_unit").values,
            dtype=float,
        )

    ids = np.asarray(sim.calculate("tax_unit_id", period=YEAR).values).astype(int)
    index = {int(tax_unit_id): i for i, tax_unit_id in enumerate(ids)}
    values = {
        "agi": tax_unit("adjusted_gross_income"),
        "nc_taxable_income": tax_unit("nc_taxable_income"),
        "nc_standard_deduction": tax_unit("nc_standard_deduction"),
        "nc_itemized_deductions": tax_unit("nc_itemized_deductions"),
        "charitable": tax_unit("charitable_deduction"),
        "medical": tax_unit("medical_expense_deduction"),
        "mortgage_interest": person_sum("mortgage_interest"),
        "deductible_mortgage_interest": person_sum("deductible_mortgage_interest"),
        "non_deductible_mortgage_interest": person_sum(
            "non_deductible_mortgage_interest"
        ),
        "real_estate_taxes": person_sum("real_estate_taxes"),
    }
    filing_status = np.asarray(
        sim.calculate("filing_status", period=YEAR).values
    ).astype(str)

    def statute_reading(i: int) -> tuple[float, float, float]:
        """Return (statute itemized, deduction change, predicted Axiom tax)."""

        statute_itemized = (
            min(
                values["deductible_mortgage_interest"][i]
                + values["real_estate_taxes"][i],
                MORTGAGE_AND_PROPERTY_TAX_CAP,
            )
            + values["charitable"][i]
            + values["medical"][i]
        )
        standard = values["nc_standard_deduction"][i]
        statute_deduction = max(standard, statute_itemized)
        policyengine_deduction = max(standard, values["nc_itemized_deductions"][i])
        taxable = (
            values["nc_taxable_income"][i]
            + policyengine_deduction
            - statute_deduction
        )
        return (
            statute_itemized,
            statute_deduction - policyengine_deduction,
            max(0.0, taxable) * RATE,
        )

    rows = []
    for tax_unit_id in mismatch_ids:
        i = index[tax_unit_id]
        statute_itemized, deduction_change, predicted = statute_reading(i)
        rows.append(
            {
                "tax_unit_id": tax_unit_id,
                "filing_status": filing_status[i],
                "agi": round(values["agi"][i], 2),
                "policyengine_nc_taxable_income": round(
                    values["nc_taxable_income"][i], 2
                ),
                "nc_standard_deduction": values["nc_standard_deduction"][i],
                "policyengine_nc_itemized_deductions": round(
                    values["nc_itemized_deductions"][i], 2
                ),
                "statute_itemized_deductions": round(statute_itemized, 2),
                "mortgage_interest": round(values["mortgage_interest"][i], 2),
                "deductible_mortgage_interest": round(
                    values["deductible_mortgage_interest"][i], 2
                ),
                "non_deductible_mortgage_interest": round(
                    values["non_deductible_mortgage_interest"][i], 2
                ),
                "real_estate_taxes": round(values["real_estate_taxes"][i], 2),
                "charitable": round(values["charitable"][i], 2),
                "medical": round(values["medical"][i], 2),
                "deduction_change": round(deduction_change, 2),
                "policyengine_tax": policyengine[tax_unit_id],
                "axiom_tax": axiom[tax_unit_id],
                "predicted_axiom_tax": round(predicted, 4),
                "axiom_minus_predicted": round(axiom[tax_unit_id] - predicted, 4),
            }
        )

    compared = [index[tax_unit_id] for tax_unit_id in axiom]
    moved = []
    residuals = []
    for i in compared:
        _, deduction_change, predicted = statute_reading(i)
        tax_unit_id = int(ids[i])
        residuals.append(abs(axiom[tax_unit_id] - predicted))
        if abs(deduction_change) > 0.005:
            moved.append(
                {
                    "tax_unit_id": tax_unit_id,
                    "deduction_change": round(deduction_change, 2),
                    "predicted_tax_change": round(
                        predicted - policyengine[tax_unit_id], 4
                    ),
                    "observed_tax_change": round(
                        axiom[tax_unit_id] - policyengine[tax_unit_id], 4
                    ),
                    "reported_mismatch": tax_unit_id in mismatch_ids,
                }
            )
    out = {
        "schema_version": "axiom.nc_populace_mismatch_trace.v1",
        "campaign_report": campaign_path.name,
        "dataset_identity": identity,
        "packages": {
            "policyengine": version("policyengine"),
            "policyengine-us": version("policyengine-us"),
        },
        "year": YEAR,
        "rate": RATE,
        "compared_tax_unit_count": len(compared),
        "mismatches": rows,
        "units_where_statute_reading_moves_deduction": moved,
        "units_with_nonzero_non_deductible_mortgage_interest": int(
            sum(values["non_deductible_mortgage_interest"][i] > 0 for i in compared)
        ),
        "max_abs_axiom_minus_predicted_all_units": round(max(residuals), 4),
        "count_axiom_minus_predicted_over_0_50": int(
            sum(residual > 0.5 for residual in residuals)
        ),
    }
    out_path.write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "mismatches"}, default=str)[:2000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
