"""Stage 2 of the fiit-ecps EITC attribution: the rows stage 1 left residual.

Stage 1 (counterfactuals.py) applied every combination of the age,
partnership and investment mechanisms. Here those three are applied
together as a fixed base, so their effects are already neutralized, and two
further mechanisms in Axiom's 26 USC 32(c)(2) input are layered on top in
every combination. Each makes the bridge's
``net_earnings_from_self_employment_after_self_employment_tax_deduction``
input what PolicyEngine-US 1.729.0's ``eitc_earned_income`` uses:

- ``se_loss``: sum the filers' self-employment amounts before flooring.
  The bridge floors each filer at zero, so a filer's self-employment loss
  never reduces their wages; PolicyEngine sums the non-dependents' gross
  amounts and floors only the total.
- ``seca``: subtract PolicyEngine's own ``self_employment_tax_ald_person``
  summed over the filers, instead of the bridge's flat one-half-of-15.3%-
  of-92.35% fraction. PolicyEngine's deduction is one-half of the SECA tax
  it computes, which stops at the OASDI contribution base.

A row is attributed to the smallest stage-2 mechanism set that clears it on
top of the stage-1 base; a row nothing clears stays residual. The base
variant (stage-1 mechanisms only) must reproduce stage 1's all-mechanism
rows on these units, or the attribution is void (exit 3).

The PolicyEngine data for the units is cached as a pickle beside the output,
so a further stage can reuse it without reloading the population.
"""

from __future__ import annotations

import argparse
import itertools
import json
import pickle
import sys
from importlib.metadata import version
from pathlib import Path

import axiom_oracles.bridges.tax_populace as tp

sys.path.insert(0, str(Path(__file__).resolve().parent))
import counterfactuals as cf  # noqa: E402
import minimal_sets  # noqa: E402

STAGE1 = frozenset(cf.MECHANISMS)
MECHANISMS = ("se_loss", "seca")
SE_COLUMNS = (
    "self_employment_income_before_lsr",
    "sstb_self_employment_income_before_lsr",
    "farm_operations_income",
    "partnership_se_income",
)
PE_SECA_ALD = "self_employment_tax_ald_person"
# The bridge's flat 26 USC 164(f) fraction (project_section_32_c_2_tax_unit_inputs).
FLAT_SECA_FRACTION = 0.5 * (0.124 + 0.029) * (1 - 0.5 * (0.124 + 0.029))


# PolicyEngine-US 1.729.0 values read for the decomposition. Person-level
# names are read from the captured simulation rather than requested from
# the loader, so they never replace the raw columns the bridge projects.
DECOMPOSITION_TAX_UNIT = (
    "eitc_relevant_investment_income",
    "net_investment_income",
    "net_capital_gains",
    "loss_limited_net_capital_gains",
    "eitc_child_count",
)
DECOMPOSITION_PERSON = (
    "age",
    "is_tax_unit_head",
    "is_tax_unit_spouse",
    "is_tax_unit_dependent",
    "taxable_interest_income",
    "tax_exempt_interest_income",
    "dividend_income",
    "rental_income",
)


def load_with_decomposition(load_ids):
    import policyengine_us

    captured = {}
    original_cls = policyengine_us.Microsimulation

    class Capturing(original_cls):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            captured["sim"] = self

    policyengine_us.Microsimulation = Capturing
    try:
        tax_unit_variables, person_variables = tp.policyengine_variables_for_surfaces(
            list(tp.SURFACE_OUTPUTS)
        )
        tax_unit_variables = tuple(
            sorted({*tax_unit_variables, cf.PE_INVESTMENT_INCOME})
        )
        person_variables = tuple(sorted({*person_variables, PE_SECA_ALD}))
        pe_data = tp.load_policyengine_tax_data(
            year=cf.YEAR,
            sample_size=0,
            positive_ctc_only=False,
            data_folder=Path(".axiom/policyengine-data"),
            populace_year=tp.DEFAULT_US_POPULACE_YEAR,
            tax_unit_ids=tuple(load_ids),
            allow_uncertified_policyengine_data=True,
            tax_unit_variables=tax_unit_variables,
            person_variables=person_variables,
        )
    finally:
        policyengine_us.Microsimulation = original_cls
    sim = captured["sim"]
    keep = set(load_ids)
    tax_unit_ids = [int(v) for v in tp.calculate(sim, "tax_unit_id", cf.YEAR)]
    person_tax_unit = [int(v) for v in tp.calculate(sim, "person_tax_unit_id", cf.YEAR)]
    person_ids = [int(v) for v in tp.calculate(sim, "person_id", cf.YEAR)]
    tax_unit_values = {}
    for name in DECOMPOSITION_TAX_UNIT:
        values = tp.calculate(sim, name, cf.YEAR)
        if len(values) != len(tax_unit_ids):
            raise SystemExit(f"{name} is not a tax-unit variable")
        for tu, value in zip(tax_unit_ids, values, strict=True):
            if tu in keep:
                tax_unit_values.setdefault(tu, {})[name] = float(value)
    person_values = {}
    for name in DECOMPOSITION_PERSON:
        values = tp.calculate(sim, name, cf.YEAR)
        if len(values) != len(person_ids):
            raise SystemExit(f"{name} is not a person variable")
        for pid, tu, value in zip(person_ids, person_tax_unit, values, strict=True):
            if tu in keep:
                person_values.setdefault(tu, {}).setdefault(pid, {})[name] = (
                    bool(value) if name.startswith("is_") else float(value)
                )
    return pe_data, {"tax_unit": tax_unit_values, "person": person_values}


def decompose(pe_data, decomposition_values, unit_ids):
    """Per-unit evidence for the age and investment-income mechanisms.

    Axiom's aggregate is the bridge's own projection over the exact person
    rows the full run used; PolicyEngine's is its own variable. The
    components show which statutory difference produces the gap.
    """
    persons_by_unit = tp.group_person_rows_by_tax_unit(pe_data["persons"])
    rows_by_unit = {
        int(row["tax_unit_id"]): row for _i, row in pe_data["tax_units"].iterrows()
    }
    out = {}
    for tu in unit_ids:
        persons = persons_by_unit.get(tu, [])
        row = rows_by_unit.get(tu)
        if row is None:
            continue
        filers = tp.tax_unit_filers(persons)
        pe_people = decomposition_values["person"].get(tu, {})
        pe_unit = decomposition_values["tax_unit"].get(tu, {})
        dependents = [p for p in pe_people.values() if p["is_tax_unit_dependent"]]
        filers_pe = [p for p in pe_people.values() if not p["is_tax_unit_dependent"]]

        def pe_sum(people, *names):
            return sum(p[n] for p in people for n in names)

        out[str(tu)] = {
            "axiom_investment_income": tp.project_eitc_relevant_investment_income(
                row=row, persons=filers
            ),
            "pe_investment_income": pe_unit.get("eitc_relevant_investment_income"),
            "pe_components": {
                "interest_dividends_tax_exempt_all_members": pe_sum(
                    pe_people.values(),
                    "taxable_interest_income", "dividend_income",
                    "tax_exempt_interest_income",
                ),
                "interest_dividends_tax_exempt_dependents": pe_sum(
                    dependents,
                    "taxable_interest_income", "dividend_income",
                    "tax_exempt_interest_income",
                ),
                "rental_income_filers": pe_sum(filers_pe, "rental_income"),
                "rental_income_dependents": pe_sum(dependents, "rental_income"),
                "net_capital_gains": pe_unit.get("net_capital_gains"),
            },
            "bridge_columns_filers": {
                column: sum(tp.money(p.get(column, 0)) for p in filers)
                for column in (
                    *tp.EITC_INTEREST_AND_DIVIDEND_COLUMNS,
                    *tp.EITC_PASSIVE_INCOME_COLUMNS,
                    "short_term_capital_gains", "non_sch_d_capital_gains",
                    *tp.LONG_TERM_CAPITAL_GAINS_COLUMNS,
                )
            },
            "pe_eitc_child_count": pe_unit.get("eitc_child_count"),
            "members": [
                {
                    "age": p["age"],
                    "head": p["is_tax_unit_head"],
                    "spouse": p["is_tax_unit_spouse"],
                    "dependent": p["is_tax_unit_dependent"],
                }
                for p in pe_people.values()
            ],
            "axiom_filer_ages": [tp.money(p["age"]) for p in filers],
        }
    return out


def patched_32_c_2(original, mechanisms: frozenset[str]):
    def patched(*, persons, contexts):
        inputs = original(persons=persons, contexts=contexts)
        if not mechanisms:
            return inputs
        filers = [
            person
            for person, context in zip(persons, contexts, strict=True)
            if context.is_head or context.is_spouse
        ]
        per_filer = [
            sum(tp.money(person.get(column, 0)) for column in SE_COLUMNS)
            for person in filers
        ]
        gross = (
            sum(per_filer)
            if "se_loss" in mechanisms
            else sum(max(0.0, amount) for amount in per_filer)
        )
        if "seca" in mechanisms:
            deduction = sum(tp.money(person.get(PE_SECA_ALD, 0)) for person in filers)
            net = gross - deduction
        else:
            net = gross * (1 - FLAT_SECA_FRACTION)
        inputs["net_earnings_from_self_employment_after_self_employment_tax_deduction"] = net
        return inputs

    return patched


def run(name, pe_data, *, stage2, args, ids):
    original = tp.project_section_32_c_2_tax_unit_inputs
    tp.project_section_32_c_2_tax_unit_inputs = patched_32_c_2(original, stage2)
    try:
        data = cf.zero_partnership_se(pe_data)
        return cf.run_variant(name, data, mechanisms=STAGE1, args=args, ids=ids)
    finally:
        tp.project_section_32_c_2_tax_unit_inputs = original


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage1", type=Path, required=True)
    parser.add_argument("--rulespec-root", type=Path, required=True)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    stage1 = json.loads(args.stage1.read_text())
    residual = {
        key for key, entry in stage1["attribution"].items()
        if entry["mechanism"] == "residual"
    }
    ids = sorted({cf.tax_unit_id(key.split("|", 1)[0]) for key in residual})
    print(f"{len(residual)} residual rows over {len(ids)} tax units", file=sys.stderr)
    stage1_all = {
        key: value
        for key, value in stage1["variants"]["age+partnership+investment"]["rows"].items()
        if cf.tax_unit_id(key.split("|", 1)[0]) in set(ids)
    }

    explained_ids = {
        mechanism: sorted({
            cf.tax_unit_id(key.split("|", 1)[0])
            for key, entry in stage1["attribution"].items()
            if entry["mechanism"] == mechanism
        })
        for mechanism in ("age", "investment", "age+investment", "partnership")
    }
    load_ids = sorted(set(ids).union(*explained_ids.values()))
    cache = args.out.with_suffix(".pe_data.pkl")
    if cache.exists():
        pe_data, decomposition_values = pickle.loads(cache.read_bytes())
    else:
        pe_data, decomposition_values = load_with_decomposition(load_ids)
        cache.write_bytes(pickle.dumps((pe_data, decomposition_values)))
    residual_data = cf.subset_pe_data(pe_data, ids)

    variants = {}
    for size in range(len(MECHANISMS) + 1):
        for combo in itertools.combinations(MECHANISMS, size):
            stage2 = frozenset(combo)
            name = "+".join(sorted(STAGE1)) + ("+" + "+".join(combo) if combo else "")
            rows, compared = run(name, residual_data, stage2=stage2, args=args, ids=ids)
            variants[stage2] = {
                "compared_tax_units": compared,
                "rows": {"|".join(key): value for key, value in rows.items()},
            }

    base = variants[frozenset()]["rows"]
    reproduced = base == stage1_all
    attribution = minimal_sets.attribute(
        residual,
        {m: v["rows"] for m, v in variants.items()},
        lambda m: "+".join(sorted(m)),
    )

    decomposition = decompose(
        pe_data,
        decomposition_values,
        sorted(set().union(*(set(v) for k, v in explained_ids.items() if k != "partnership"))),
    )
    payload = {
        "decomposition": decomposition,
        "explained_units": explained_ids,
        "stage1": str(args.stage1),
        "policyengine_us": version("policyengine-us"),
        "rulespec_root": str(args.rulespec_root),
        "engine": str(args.engine),
        "tax_units": ids,
        "residual_rows_in": len(residual),
        "base_reproduces_stage1_all_mechanisms": reproduced,
        "base_only_rows": sorted(set(base) - set(stage1_all)),
        "stage1_only_rows": sorted(set(stage1_all) - set(base)),
        "variants": {
            ("+".join(sorted(m)) or "base"): v for m, v in variants.items()
        },
        "attribution": attribution,
    }
    args.out.write_text(json.dumps(payload, indent=1, sort_keys=True))
    print(f"base reproduces stage 1: {reproduced}", file=sys.stderr)
    return 0 if reproduced else 3


if __name__ == "__main__":
    sys.exit(main())
