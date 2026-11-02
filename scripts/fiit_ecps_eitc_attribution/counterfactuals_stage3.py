"""Stage 3 of the fiit-ecps EITC attribution: what the investment rows are.

Stage 1 attributed rows to ``investment`` when replacing Axiom's 26 USC
32(i)(2) input with PolicyEngine-US 1.729.0's own
``eitc_relevant_investment_income`` cleared them. That says the aggregate
differs, not why. The two aggregates differ in exactly five ways, each a
switch in ``aggregate()`` below:

- ``div_aggregate``: dividends. The pinned Populace artifact stores a
  ``dividend_income`` value beside ``qualified_dividend_income`` and
  ``non_qualified_dividend_income``, and the two disagree. PolicyEngine uses
  the stored aggregate; the bridge sums the components.
- ``dependents``: PolicyEngine-US 1.729.0 sums every tax-unit member; the
  bridge reads the head and spouse (fixed upstream by
  PolicyEngine/policyengine-us#9883; issue #9635).
- ``cg_distributions``: PolicyEngine-US 1.729.0's ``net_capital_gains``
  leaves out capital gain distributions (``non_sch_d_capital_gains``); the
  bridge counts them (fixed upstream by #9572; issue #9567).
- ``farm_rent``: PolicyEngine-US 1.729.0 leaves farm rental income out of the
  passive basket; the bridge counts it (fixed upstream by #9889; issue #9635).
- ``rental_unfloor``: PolicyEngine-US 1.729.0 nets rental losses against
  other income; the bridge floors the passive basket at zero (fixed upstream
  by #9572; issue #9567).

With no switch the function returns the bridge's aggregate and with all five
PolicyEngine's, to the cent, for every unit (checked here; exit 3 if not).

Every other mechanism (age, partnership, se_loss, seca) is applied as a
fixed base. Each of the 32 switch combinations sets Axiom's input to that
combination's aggregate and re-runs the Axiom EITC surface over the
investment units. A row is attributed to the smallest switch set that
clears it.

The base (the bridge's aggregate, every other mechanism applied) must leave
every target row, and any further row it leaves must be absent from the full
run: with the all-members age rule applied, Axiom can newly mismatch where
PolicyEngine still denies on its own aggregate. Such rows exist only in the
counterfactual, so they are recorded (``base_counterfactual_only_rows``) and
not attributed. The 2026-10-14 run predates this check; it compared the base
with the target for equality, and failed only on four such rows.
"""

from __future__ import annotations

import argparse
import itertools
import json
import pickle
import sys
from pathlib import Path

import axiom_oracles.bridges.tax_populace as tp

sys.path.insert(0, str(Path(__file__).resolve().parent))
import counterfactuals as cf  # noqa: E402
import counterfactuals_stage2 as s2  # noqa: E402
import minimal_sets  # noqa: E402

SWITCHES = ("div_aggregate", "dependents", "cg_distributions", "farm_rent", "rental_unfloor")


def aggregate(persons, pe_people, flags) -> float:
    filers = tp.tax_unit_filers(persons)
    filer_ids = {int(p["person_id"]) for p in filers}
    people = [
        p for p in persons if int(p["person_id"]) in filer_ids or "dependents" in flags
    ]
    m = tp.money
    interest = sum(
        m(p.get("taxable_interest_income", 0)) + m(p.get("tax_exempt_interest_income", 0))
        for p in people
    )
    if "div_aggregate" in flags:
        dividends = sum(pe_people[int(p["person_id"])]["dividend_income"] for p in people)
    else:
        dividends = sum(
            m(p.get("qualified_dividend_income", 0))
            + m(p.get("non_qualified_dividend_income", 0))
            for p in people
        )
    gains = sum(
        tp.first_available_money(p, tp.LONG_TERM_CAPITAL_GAINS_COLUMNS)
        + m(p.get("short_term_capital_gains", 0))
        + (0.0 if "cg_distributions" in flags else m(p.get("non_sch_d_capital_gains", 0)))
        for p in people
    )
    passive = sum(
        m(p.get("rental_income", 0))
        + m(p.get("passive_partnership_s_corp_income", 0))
        + (0.0 if "farm_rent" in flags else m(p.get("farm_rent_income", 0)))
        for p in people
    )
    return (
        interest
        + dividends
        + max(0.0, gains)
        + (passive if "rental_unfloor" in flags else max(0.0, passive))
    )


def switch_name(flags: frozenset[str]) -> str:
    return "+".join(switch for switch in SWITCHES if switch in flags)


def base_check(base_rows, target, full_run_rows) -> tuple[bool, list[str]]:
    """Whether the base leaves every target row and no other full-run row.

    Returns the verdict and the base's rows outside the target, each of which
    the verdict requires to be absent from the full run (counterfactual-only).
    """
    extra = sorted(set(base_rows) - set(target))
    ok = set(target) <= set(base_rows) and not any(key in full_run_rows for key in extra)
    return ok, extra


def run(name, pe_data, *, aggregates, args, ids):
    original_inputs = tp.project_eitc_tax_unit_inputs
    original_32c2 = tp.project_section_32_c_2_tax_unit_inputs

    def with_aggregate(row, persons):
        inputs = original_inputs(row, persons)
        inputs["eitc_relevant_investment_income"] = aggregates[int(row["tax_unit_id"])]
        return inputs

    tp.project_eitc_tax_unit_inputs = with_aggregate
    tp.project_section_32_c_2_tax_unit_inputs = s2.patched_32_c_2(
        original_32c2, frozenset(s2.MECHANISMS)
    )
    try:
        data = cf.zero_partnership_se(pe_data)
        # Only the age mechanism from stage 1: `investment` is replaced by the
        # aggregate above, and partnership is applied through the data.
        return cf.run_variant(
            name, data, mechanisms=frozenset({"age"}), args=args, ids=ids
        )
    finally:
        tp.project_eitc_tax_unit_inputs = original_inputs
        tp.project_section_32_c_2_tax_unit_inputs = original_32c2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage1", type=Path, required=True)
    parser.add_argument("--stage2", type=Path, required=True)
    parser.add_argument("--rulespec-root", type=Path, required=True)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    stage1 = json.loads(args.stage1.read_text())
    target = {
        key for key, entry in stage1["attribution"].items()
        if entry["mechanism"] in ("investment", "age+investment")
    }
    ids = sorted({cf.tax_unit_id(key.split("|", 1)[0]) for key in target})
    print(f"{len(target)} investment rows over {len(ids)} tax units", file=sys.stderr)

    # Stage 2's PolicyEngine data and decomposition values, cached beside it.
    cache = args.stage2.with_suffix(".pe_data.pkl")
    pe_data, decomposition_values = pickle.loads(cache.read_bytes())
    data = cf.subset_pe_data(pe_data, ids)
    persons_by_unit = tp.group_person_rows_by_tax_unit(data["persons"])

    # The switch model must reproduce both engines' aggregates exactly.
    mismatched = []
    for tu in ids:
        persons = persons_by_unit[tu]
        pe_people = decomposition_values["person"][tu]
        bridge = tp.project_eitc_relevant_investment_income(
            row=None, persons=tp.tax_unit_filers(persons)
        )
        policyengine = decomposition_values["tax_unit"][tu]["eitc_relevant_investment_income"]
        if abs(aggregate(persons, pe_people, frozenset()) - bridge) > 0.01 or abs(
            aggregate(persons, pe_people, frozenset(SWITCHES)) - policyengine
        ) > 0.01:
            mismatched.append(tu)
    if mismatched:
        print(f"switch model does not reproduce {len(mismatched)} units", file=sys.stderr)
        return 3

    variants = {}
    for size in range(len(SWITCHES) + 1):
        for combo in itertools.combinations(SWITCHES, size):
            flags = frozenset(combo)
            aggregates = {
                tu: aggregate(
                    persons_by_unit[tu], decomposition_values["person"][tu], flags
                )
                for tu in ids
            }
            name = "+".join(combo) or "bridge_aggregate"
            rows, _compared = run(name, data, aggregates=aggregates, args=args, ids=ids)
            variants[flags] = {"|".join(key): value for key, value in rows.items()}

    # On these units, the bridge-aggregate variant leaves every row stage 1
    # attributed to investment and no other row of the full run, and the
    # PolicyEngine-aggregate variant leaves none.
    base_ok, extra = base_check(variants[frozenset()], target, stage1["attribution"])
    all_clear = not variants[frozenset(SWITCHES)]
    attribution = minimal_sets.attribute(target, variants, switch_name)
    payload = {
        "stage1": str(args.stage1),
        "stage2": str(args.stage2),
        "tax_units": ids,
        "target_rows": len(target),
        "switch_model_exact": True,
        "bridge_aggregate_variant_leaves_stage1_investment_rows": base_ok,
        "base_counterfactual_only_rows": extra,
        "policyengine_aggregate_variant_clears_all": all_clear,
        "variants": {("+".join(sorted(f)) or "bridge_aggregate"): len(r) for f, r in variants.items()},
        "attribution": attribution,
    }
    args.out.write_text(json.dumps(payload, indent=1, sort_keys=True))
    print(f"base ok: {base_ok}; all clear: {all_clear}", file=sys.stderr)
    return 0 if base_ok and all_clear else 3


if __name__ == "__main__":
    sys.exit(main())
