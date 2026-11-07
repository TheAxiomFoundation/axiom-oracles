"""Per-row mechanism attribution for fiit-ecps EITC mismatches, by counterfactual.

Each mechanism is one Axiom-side input change that makes Axiom see what
PolicyEngine-US 1.729.0 sees. The PolicyEngine leg is held fixed. Every
combination of mechanisms (2^3 = 8, the empty one is the baseline) re-runs
the Axiom EITC surface over the tax units that have an EITC mismatch in the
full run. A row is attributed to the smallest mechanism set whose variant
clears it; a row no combination clears is residual.

Mechanisms:

- ``age``: the childless age input over every tax-unit member, the rule
  PolicyEngine-US 1.729.0's ``eitc_demographic_eligible`` applies
  (``tax_unit.any(meets_age_requirements)``; fixed upstream by
  PolicyEngine/policyengine-us#9132) and axiom-oracles used before #632.
- ``partnership``: ``partnership_se_income`` set to 0 for every person fed
  to Axiom. PolicyEngine-US 1.729.0 has no such variable (#8614 renamed it
  ``partnership_self_employment_net_earnings``, which the pinned artifact
  does not store), so PolicyEngine reads 0 for it.
- ``investment``: Axiom's ``eitc_relevant_investment_income`` input replaced
  by PolicyEngine-US 1.729.0's own ``eitc_relevant_investment_income``
  (``net_investment_income`` + tax-exempt interest with capital-loss
  adjustments; replaced upstream by PolicyEngine/policyengine-us#9572).

Checks that void the attribution (exit 3) unless they hold:

- the baseline (no mechanism) reproduces the full run's EITC rows exactly
  on this subset of units (subset invariance);
- an explain-mode baseline on a sample of the units reproduces the same
  rows (mode differential; the full run requested fast).

Usage: see README.md (``run_stage.sh counterfactuals.py --report ...``).
"""

from __future__ import annotations

import argparse
import copy
import itertools
import json
import sys
from importlib.metadata import version
from pathlib import Path

import axiom_oracles.bridges.tax_populace as tp

sys.path.insert(0, str(Path(__file__).resolve().parent))
import minimal_sets  # noqa: E402

YEAR = 2026
EXPLAIN_SAMPLE = 1500
MECHANISMS = ("age", "partnership", "investment")
PE_INVESTMENT_INCOME = "eitc_relevant_investment_income"


def tax_unit_id(entity_id: str) -> int:
    return int(str(entity_id).rsplit("_", 1)[-1])


def row_key(row) -> tuple[str, str]:
    data = row if isinstance(row, dict) else row.__dict__
    return (str(data["entity_id"]), str(data["output"]))


def row_values(row) -> dict:
    data = row if isinstance(row, dict) else row.__dict__
    return {
        "axiom": data["axiom"],
        "policyengine": data["policyengine"],
        "diff": data["diff"],
    }


def patched_eitc_inputs(original, mechanisms: frozenset[str]):
    def patched(row, persons):
        inputs = original(row, persons)
        if "age" in mechanisms:
            inputs["childless_taxpayer_or_spouse_age_eligible_for_eitc"] = any(
                25 <= tp.money(person["age"]) < 65 for person in persons
            )
        if "investment" in mechanisms:
            inputs["eitc_relevant_investment_income"] = tp.money(
                row[PE_INVESTMENT_INCOME]
            )
        return inputs

    return patched


def zero_partnership_se(pe_data: dict) -> dict:
    changed = copy.deepcopy(pe_data)
    persons = changed["persons"]
    if "partnership_se_income" not in persons.columns:
        raise SystemExit("persons table has no partnership_se_income column")
    persons["partnership_se_income"] = 0.0
    return changed


def subset_pe_data(pe_data: dict, ids: list[int]) -> dict:
    keep = set(ids)
    tax_units = pe_data["tax_units"]
    persons = pe_data["persons"]
    tax_units = tax_units[tax_units["tax_unit_id"].astype(int).isin(keep)].copy()
    persons = persons[persons["person_tax_unit_id"].astype(int).isin(keep)].copy()
    return {
        **pe_data,
        "tax_units": tax_units,
        "persons": persons,
        "tax_unit_ids": [int(v) for v in tax_units["tax_unit_id"]],
        "person_ids": [int(v) for v in persons["person_id"]],
    }


def run_variant(name, pe_data, *, mechanisms, args, ids, mode=None):
    original_load = tp.load_policyengine_tax_data
    original_inputs = tp.project_eitc_tax_unit_inputs
    original_mode = tp.AXIOM_REQUEST_MODE
    tp.load_policyengine_tax_data = lambda **_kwargs: pe_data
    tp.project_eitc_tax_unit_inputs = patched_eitc_inputs(original_inputs, mechanisms)
    if mode is not None:
        tp.AXIOM_REQUEST_MODE = mode
    try:
        report = tp.compare_tax_ecps(
            workspace_root=args.rulespec_root.parent,
            rulespec_root=args.rulespec_root,
            axiom_rules_path=args.engine,
            year=YEAR,
            sample_size=0,
            positive_ctc_only=False,
            surface="eitc",
            data_folder=Path(".axiom/policyengine-data"),
            populace_year=tp.DEFAULT_US_POPULACE_YEAR,
            tolerance=0.01,
            relative_tolerance=2e-7,
            tax_unit_ids=tuple(ids),
            allow_policyengine_us_version=True,
            allow_uncertified_policyengine_data=True,
        )
    finally:
        tp.load_policyengine_tax_data = original_load
        tp.project_eitc_tax_unit_inputs = original_inputs
        tp.AXIOM_REQUEST_MODE = original_mode
    rows = {row_key(row): row_values(row) for row in report.mismatches}
    print(f"[{name}] {len(rows)} EITC mismatch rows", file=sys.stderr, flush=True)
    return rows, report.compared_tax_units


def variant_name(mechanisms: frozenset[str]) -> str:
    return "+".join(m for m in MECHANISMS if m in mechanisms) or "baseline"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--rulespec-root", type=Path, required=True)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    full = json.loads(args.report.read_text())
    full_rows = {
        row_key(row): row_values(row)
        for row in full["mismatches"]
        if row["surface"] == "eitc"
    }
    del full
    ids = sorted({tax_unit_id(entity_id) for entity_id, _ in full_rows})
    print(f"{len(full_rows)} EITC rows over {len(ids)} tax units", file=sys.stderr)

    # The same PolicyEngine variable request as the full ("all") run, so the
    # raw-versus-PolicyEngine column choice in the person rows is identical,
    # plus PolicyEngine's own investment income for the `investment` variant.
    tax_unit_variables, person_variables = tp.policyengine_variables_for_surfaces(
        list(tp.SURFACE_OUTPUTS)
    )
    tax_unit_variables = tuple(sorted({*tax_unit_variables, PE_INVESTMENT_INCOME}))
    pe_data = tp.load_policyengine_tax_data(
        year=YEAR,
        sample_size=0,
        positive_ctc_only=False,
        data_folder=Path(".axiom/policyengine-data"),
        populace_year=tp.DEFAULT_US_POPULACE_YEAR,
        tax_unit_ids=tuple(ids),
        allow_uncertified_policyengine_data=True,
        tax_unit_variables=tax_unit_variables,
        person_variables=person_variables,
    )
    partnership_zero = zero_partnership_se(pe_data)

    variants: dict[frozenset[str], dict] = {}
    for size in range(len(MECHANISMS) + 1):
        for combo in itertools.combinations(MECHANISMS, size):
            mechanisms = frozenset(combo)
            data = partnership_zero if "partnership" in mechanisms else pe_data
            rows, compared = run_variant(
                variant_name(mechanisms), data, mechanisms=mechanisms, args=args, ids=ids
            )
            variants[mechanisms] = {"compared_tax_units": compared, "rows": rows}

    # Mode differential on a sample of the same units.
    sample_ids = ids[:: max(1, len(ids) // EXPLAIN_SAMPLE)][:EXPLAIN_SAMPLE]
    explain_rows, _ = run_variant(
        "baseline_explain_sample",
        subset_pe_data(pe_data, sample_ids),
        mechanisms=frozenset(),
        args=args,
        ids=sample_ids,
        mode="explain",
    )
    sample_set = set(sample_ids)
    full_on_sample = {
        key: value for key, value in full_rows.items()
        if tax_unit_id(key[0]) in sample_set
    }
    explain_matches = explain_rows == full_on_sample

    baseline = variants[frozenset()]["rows"]
    reproduced = baseline == full_rows
    attribution = {
        "|".join(key): entry
        for key, entry in minimal_sets.attribute(
            full_rows, {m: v["rows"] for m, v in variants.items()}, variant_name
        ).items()
    }

    payload = {
        "full_report": str(args.report),
        "policyengine_us": version("policyengine-us"),
        "policyengine_core": version("policyengine-core"),
        "rulespec_root": str(args.rulespec_root),
        "engine": str(args.engine),
        "tax_units": ids,
        "full_eitc_rows": len(full_rows),
        "baseline_reproduces_full_run": reproduced,
        "baseline_only_rows": sorted(
            "|".join(key) for key in set(baseline) - set(full_rows)
        ),
        "full_only_rows": sorted(
            "|".join(key) for key in set(full_rows) - set(baseline)
        ),
        "baseline_value_drift": sorted(
            "|".join(key)
            for key in set(full_rows) & set(baseline)
            if full_rows[key] != baseline[key]
        ),
        "explain_sample_tax_units": len(sample_ids),
        "explain_sample_rows": len(explain_rows),
        "explain_sample_matches_full_run": explain_matches,
        "variants": {
            variant_name(m): {
                "compared_tax_units": v["compared_tax_units"],
                "rows": {"|".join(key): value for key, value in v["rows"].items()},
            }
            for m, v in variants.items()
        },
        "attribution": attribution,
    }
    args.out.write_text(json.dumps(payload, indent=1, sort_keys=True))
    print(
        f"baseline reproduces full run: {reproduced}; "
        f"explain sample matches: {explain_matches}",
        file=sys.stderr,
    )
    return 0 if reproduced and explain_matches else 3


if __name__ == "__main__":
    sys.exit(main())
