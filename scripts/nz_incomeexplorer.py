#!/usr/bin/env python3
"""Build the unified NZ Treasury IncomeExplorer comparison record.

The committed source receipt is the deterministic double-run output of the
external TheAxiomFoundation/ops reproduction harness. This adapter does not
split that experiment by program: it emits one population x oracle x
jurisdiction record, with program subgraphs represented only as node views.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_FLOOR, localcontext
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from nz_programs import PROGRAM_VIEWS, SINGLE_PERSON_PROGRAMS  # noqa: E402
SOURCE_DIR = REPO_ROOT / "comparisons" / "nz-treasury-incomeexplorer"
SOURCE_PATH = SOURCE_DIR / "source-comparison.json"
SNAPSHOT_PATH = SOURCE_DIR / "treasury-emtr-snapshot-expanded.json"
CLOSURES_PATH = SOURCE_DIR / "eligibility-closures.json"
DISPOSITIONS_PATH = REPO_ROOT / "dispositions" / "nz-treasury-incomeexplorer.yaml"
OUTPUT_PATH = (
    REPO_ROOT / "dashboard" / "public" / "data" / "nz-treasury-incomeexplorer.json"
)
ATTESTATION_PATH = SOURCE_DIR / "single-person-attestations.json"

SCHEMA = "axiom.unified_comparison_record.v1"
SUITE = "nz-treasury-incomeexplorer"
SOURCE_SHA256 = "abd3bcbebc01c73e58c27496db5897a306bb0496ae1d53e5abbd5ae487010b3b"
SNAPSHOT_SHA256 = "6bed8c0a91e4ba6416238ef1cf381bc8033f3122f3eeb5766074d763929293fd"
TREASURY_COMMIT = "741a6ca4f5d27b1dc00b43dc395e39ffc4040a4b"
AMOUNT_TOLERANCE = Decimal("0.005")
ATTESTATION_BASELINE_SCENARIO = "single_no_children_area2_no_housing_costs"
ATTESTATION_PERTURBED_SCENARIO = "couple_two_children_dual_full_time"
ACC_RATE_INCLUDING_GST = Decimal("0.0175")
ACC_MAXIMUM_EARNINGS = Decimal("156641")
ACC_CENTS_SCALE = Decimal("100")

COLUMN_CONCEPTS = {
    "gross_wage1": "nz:population/treasury-incomeexplorer#input.gross_wage1",
    "hours1": "nz:population/treasury-incomeexplorer#input.hours1",
    "gross_wage1_annual": "nz:population/treasury-incomeexplorer#input.gross_wage1_annual",
    "gross_wage2": "nz:population/treasury-incomeexplorer#input.gross_wage2",
    "wage1_tax": PROGRAM_VIEWS["nz/income-tax"]["roots"][0],
    "wage1_ACC_levy": PROGRAM_VIEWS["nz/acc-earners-levy"]["roots"][0],
    "net_wage1": "nz:comparison/treasury-incomeexplorer#net_wage1",
    "net_wage": "nz:comparison/treasury-incomeexplorer#net_wage",
    "net_benefit": PROGRAM_VIEWS["nz/main-benefits"]["roots"][0],
    "FTC_abated": PROGRAM_VIEWS["nz/working-for-families"]["roots"][0],
    "IWTC_abated": PROGRAM_VIEWS["nz/working-for-families"]["roots"][1],
    "MFTC": PROGRAM_VIEWS["nz/working-for-families"]["roots"][2],
    "IETC_abated": PROGRAM_VIEWS["nz/independent-earner-tax-credit"]["roots"][0],
    "WinterEnergy": PROGRAM_VIEWS["nz/winter-energy-payment"]["roots"][0],
    "BestStart_Total": PROGRAM_VIEWS["nz/working-for-families"]["roots"][3],
    "AS_Amount": PROGRAM_VIEWS["nz/accommodation-supplement"]["roots"][0],
    "WFF_abated": "nz:statutes/income_tax/family_scheme/tax_credits#wff_total",
    "Net_Income": "nz:comparison/treasury-incomeexplorer#net_income",
    "Net_Income_annual": "nz:comparison/treasury-incomeexplorer#net_income_annual",
}


class NZRecordError(ValueError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NZRecordError(f"cannot read {path.relative_to(REPO_ROOT)}: {exc}") from exc
    if not isinstance(value, dict):
        raise NZRecordError(f"{path.relative_to(REPO_ROOT)} must contain an object")
    return value


def _case_id(row: dict) -> str:
    return f"nz-ie::{row['scenario_id']}::{row['weekly_wage']}"


def _number(value: object) -> int | float:
    number = Decimal(str(value))
    return int(number) if number == number.to_integral_value() else float(number)


def _decimal_text(value: Decimal) -> str:
    if value.is_zero():
        return "0"
    return format(value, "f").rstrip("0").rstrip(".")


def _acc_cell(weekly_wage: int, _profile: dict) -> Decimal:
    """Recompute the exact ACC cell used by the pinned harness.

    The harness passes only primary annual earnings to
    ``acc_standard_earners_levy_including_gst``.  The selected 2026-04-01
    RuleSpec values are 0.0175 and NZD 156,641, with annual-cent rounding
    before conversion back to the 365/7 weekly convention.
    """

    with localcontext() as context:
        context.prec = 40
        nonnegative_wage = max(Decimal(0), Decimal(weekly_wage))
        if nonnegative_wage * Decimal("365") <= ACC_MAXIMUM_EARNINGS * Decimal("7"):
            unrounded_cents = (
                nonnegative_wage
                * Decimal("365")
                * ACC_RATE_INCLUDING_GST
                * ACC_CENTS_SCALE
                / Decimal("7")
            )
        else:
            unrounded_cents = (
                ACC_MAXIMUM_EARNINGS
                * ACC_RATE_INCLUDING_GST
                * ACC_CENTS_SCALE
            )
        annual_levy = (
            (unrounded_cents + Decimal("0.5")).to_integral_value(
                rounding=ROUND_FLOOR
            )
            / ACC_CENTS_SCALE
        )
        return annual_levy * Decimal("7") / Decimal("365")


def _rulespec_receipt_cells(
    source: dict, scenario_id: str, column: str
) -> dict[int, Decimal]:
    return {
        int(row["weekly_wage"]): Decimal(str(row["rulespec"]))
        for row in source.get("comparisons") or []
        if row.get("scenario_id") == scenario_id and row.get("column") == column
    }


def assert_single_person_invariant(
    source: dict,
    program: str,
    calculator=None,
) -> dict:
    """Perturb every non-primary person fact and require identical cell bytes.

    ``calculator`` is injectable solely so the mutant can route the same gate
    through the genuinely cross-person WfF receipt and prove that it bites.
    """

    if program not in PROGRAM_VIEWS:
        raise NZRecordError(f"unknown NZ program {program!r}")
    scenarios = {item["id"]: item for item in source.get("scenarios") or []}
    try:
        baseline = scenarios[ATTESTATION_BASELINE_SCENARIO]
        perturbed = scenarios[ATTESTATION_PERTURBED_SCENARIO]
    except KeyError as exc:
        raise NZRecordError(f"attestation scenario missing: {exc}") from exc
    primary_fields = ("wage1_hourly", "accommodation_area", "accommodation_costs")
    for field in primary_fields:
        if baseline["inputs"].get(field) != perturbed["inputs"].get(field):
            raise NZRecordError(f"attestation changed primary field {field}")
    non_primary_fields = ("partnered", "gross_wage2", "hours2", "children_ages")
    unchanged = [
        field
        for field in non_primary_fields
        if baseline["inputs"].get(field) == perturbed["inputs"].get(field)
    ]
    if unchanged:
        raise NZRecordError(
            f"attestation did not perturb non-primary field(s) {unchanged}"
        )
    baseline_wages = set(baseline["sampled_weekly_wages"])
    perturbed_wages = set(perturbed["sampled_weekly_wages"])
    wages = sorted(baseline_wages & perturbed_wages)
    if not wages:
        raise NZRecordError("attestation scenarios have no shared primary wage cells")
    if calculator is None:
        if program != "nz/acc-earners-levy":
            raise NZRecordError(f"{program}: no single-person calculator is ratified")
        calculator = _acc_cell
    baseline_cells = [
        _decimal_text(calculator(wage, baseline)) for wage in wages
    ]
    perturbed_cells = [
        _decimal_text(calculator(wage, perturbed)) for wage in wages
    ]
    baseline_bytes = json.dumps(
        baseline_cells, separators=(",", ":"), ensure_ascii=False
    ).encode()
    perturbed_bytes = json.dumps(
        perturbed_cells, separators=(",", ":"), ensure_ascii=False
    ).encode()
    if baseline_bytes != perturbed_bytes:
        raise NZRecordError(
            f"{program}: non-primary-person perturbation changed program cells"
        )
    if program == "nz/acc-earners-levy" and calculator is _acc_cell:
        for scenario_id, cells in (
            (ATTESTATION_BASELINE_SCENARIO, baseline_cells),
            (ATTESTATION_PERTURBED_SCENARIO, perturbed_cells),
        ):
            receipt = _rulespec_receipt_cells(source, scenario_id, "wage1_ACC_levy")
            if any(
                abs(receipt[wage] - calculator(wage, scenarios[scenario_id]))
                > Decimal("1e-36")
                for wage in wages
            ):
                raise NZRecordError(
                    f"{program}: recomputed cells differ from the engine receipt"
                )
    return {
        "status": "pass",
        "program": program,
        "root_nodes": list(PROGRAM_VIEWS[program]["roots"]),
        "baseline_scenario": ATTESTATION_BASELINE_SCENARIO,
        "perturbed_scenario": ATTESTATION_PERTURBED_SCENARIO,
        "perturbed_non_primary_inputs": {
            field: {
                "before": baseline["inputs"].get(field),
                "after": perturbed["inputs"].get(field),
            }
            for field in non_primary_fields
        },
        "primary_weekly_wages": wages,
        "cell_count": len(wages),
        "baseline_cells": baseline_cells,
        "perturbed_cells": perturbed_cells,
        "baseline_cells_sha256": hashlib.sha256(baseline_bytes).hexdigest(),
        "perturbed_cells_sha256": hashlib.sha256(perturbed_bytes).hexdigest(),
    }


def build_single_person_attestations() -> dict:
    source = _load(SOURCE_PATH)
    snapshot = _load(SNAPSHOT_PATH)
    closures = _load(CLOSURES_PATH)
    _validate_inputs(source, snapshot, closures)
    return {
        "schema": "axiom_oracles.nz_single_person_attestations.v1",
        "source_receipt": {
            "artifact": str(SOURCE_PATH.relative_to(REPO_ROOT)),
            "sha256": SOURCE_SHA256,
        },
        "programs": {
            program: assert_single_person_invariant(source, program)
            for program in sorted(SINGLE_PERSON_PROGRAMS)
        },
    }


def _validate_inputs(source: dict, snapshot: dict, closures: dict) -> None:
    if _sha256(SOURCE_PATH) != SOURCE_SHA256:
        raise NZRecordError("source comparison bytes changed; a new receipt series is required")
    if _sha256(SNAPSHOT_PATH) != SNAPSHOT_SHA256:
        raise NZRecordError("Treasury snapshot does not reproduce byte-identically")
    oracle = snapshot.get("oracle") or {}
    if oracle.get("commit") != TREASURY_COMMIT:
        raise NZRecordError("Treasury oracle commit drifted")
    provenance = source.get("provenance") or {}
    if (provenance.get("oracle_snapshot") or {}).get("sha256") != SNAPSHOT_SHA256:
        raise NZRecordError("source receipt is not bound to the committed Treasury snapshot")
    closure_provenance = provenance.get("eligibility_closures") or {}
    if closure_provenance.get("sha256") != _sha256(CLOSURES_PATH):
        raise NZRecordError("source receipt is not bound to eligibility-closures.json")
    if source.get("declared_eligibility_closures") != closures:
        raise NZRecordError("declared eligibility closures differ from the harness receipt")

    snapshot_spine = [
        (item["id"], tuple(int(r["gross_wage1"]) for r in item["sampled_outputs"]))
        for item in snapshot.get("scenarios") or []
    ]
    source_spine = [
        (item["id"], tuple(item["sampled_weekly_wages"]))
        for item in source.get("scenarios") or []
    ]
    if source_spine != snapshot_spine or sum(len(wages) for _, wages in source_spine) != 104:
        raise NZRecordError("source population is not Treasury's complete 104-point scenario spine")

    rows = source.get("comparisons") or []
    amount_rows = [row for row in rows if row.get("column") != "EMTR"]
    outside = [row for row in amount_rows if Decimal(row["absolute_delta"]) >= AMOUNT_TOLERANCE]
    classes = Counter(row.get("classification") for row in outside)
    if len(amount_rows) != 1976 or len(outside) != 522 or classes != {"b": 520, "c": 2}:
        raise NZRecordError(
            f"unexpected amount matrix: rows={len(amount_rows)}, outside={len(outside)}, classes={dict(classes)}"
        )
    if set(COLUMN_CONCEPTS) != {row["column"] for row in amount_rows}:
        raise NZRecordError("the amount/control output surface changed without node mappings")


def _mismatch(row: dict) -> dict:
    return {
        "case_id": _case_id(row),
        "concept": COLUMN_CONCEPTS[row["column"]],
        "description": row["reason_title"],
        "difference": _number(row["signed_delta_rulespec_minus_treasury"]),
        "kind": "amount_difference",
        "left": _number(row["rulespec"]),
        "right": _number(row["treasury"]),
        "tolerance": float(AMOUNT_TOLERANCE),
        "metadata": {
            "column": row["column"],
            "classification": row["classification"],
            "reason_code": row["reason_code"],
        },
    }


def _base_report(source: dict, snapshot: dict, closures: dict) -> dict:
    amount_rows = [row for row in source["comparisons"] if row["column"] != "EMTR"]
    mismatch_rows = [
        _mismatch(row)
        for row in amount_rows
        if Decimal(row["absolute_delta"]) >= AMOUNT_TOLERANCE
    ]
    by_case: dict[str, list[dict]] = defaultdict(list)
    for mismatch in mismatch_rows:
        by_case[mismatch["case_id"]].append(mismatch)
    scenarios = {item["id"]: item for item in source["scenarios"]}
    cases = []
    for scenario_id, wages in (
        (item["id"], item["sampled_weekly_wages"]) for item in source["scenarios"]
    ):
        scenario = scenarios[scenario_id]
        for wage in wages:
            case_id = f"nz-ie::{scenario_id}::{wage}"
            cases.append(
                {
                    "case_id": case_id,
                    "metadata": {
                        "scenario_id": scenario_id,
                        "weekly_wage": wage,
                        **scenario["inputs"],
                    },
                    "mismatches": by_case.get(case_id, []),
                }
            )

    active_catalog = {
        name: value
        for name, value in source["exercise_input_catalog"].items()
        if value["state"] != "not_supplied"
    }
    if Counter(item["state"] for item in active_catalog.values()) != {
        "constant": 98,
        "varied": 52,
    }:
        raise NZRecordError("the exercised active input surface changed")
    aggregates = []
    for concept in sorted(set(COLUMN_CONCEPTS.values())):
        concept_rows = [row for row in amount_rows if COLUMN_CONCEPTS[row["column"]] == concept]
        concept_mismatches = [
            row for row in concept_rows if Decimal(row["absolute_delta"]) >= AMOUNT_TOLERANCE
        ]
        aggregates.append(
            {
                "concept": concept,
                "comparison": "amount",
                "comparison_count": len(concept_rows),
                "match_count": len(concept_rows) - len(concept_mismatches),
                "mismatch_count": len(concept_mismatches),
            }
        )
    report = {
        "record_schema": SCHEMA,
        "schema_version": "axiom.comparison_report.v2",
        "suite": SUITE,
        "tuple": {
            "jurisdiction": "nz",
            "population": {
                "id": "treasury-incomeexplorer-emtr-scenario-grid",
                "sha256": SNAPSHOT_SHA256,
                "scenario_count": 11,
                "points": 104,
            },
            "oracle": {"id": "treasury-incomeexplorer", "version": TREASURY_COMMIT},
        },
        "period": "2026-04-01/2027-03-31",
        "population": "treasury-incomeexplorer-emtr-scenario-grid",
        "dataset_identity": {"sha256": SNAPSHOT_SHA256, "revision": TREASURY_COMMIT},
        "engines": {"left": "axiom", "right": "treasury-incomeexplorer"},
        "aggregates": aggregates,
        "cases": cases,
        "mismatches": mismatch_rows,
        "summary": {
            "comparison_count": len(amount_rows),
            "match_count": len(amount_rows) - len(mismatch_rows),
            "mismatch_count": len(mismatch_rows),
            "error_count": 0,
        },
        "experiment": {
            "schema": "axiom.experiment_boundary_receipt.v1",
            "active_inputs": active_catalog,
            "compiled_input_catalog_count": len(source["exercise_input_catalog"]),
            "inactive_compiled_inputs": sum(
                item["state"] == "not_supplied"
                for item in source["exercise_input_catalog"].values()
            ),
            "bridged_through": {},
            "eligibility_closures": {
                "artifact": str(CLOSURES_PATH.relative_to(REPO_ROOT)),
                "sha256": _sha256(CLOSURES_PATH),
                "version": closures["version"],
            },
        },
        "compiled_program": source["compiled_program"],
        "views": {
            program: {
                "kind": "subgraph",
                "columns": list(spec["columns"]),
                "root_nodes": list(spec["roots"]),
            }
            for program, spec in PROGRAM_VIEWS.items()
        },
        "provenance": {
            **source["provenance"],
            "source_receipt": {
                "artifact": str(SOURCE_PATH.relative_to(REPO_ROOT)),
                "sha256": SOURCE_SHA256,
            },
            "generated_by": "scripts/nz_incomeexplorer.py",
        },
    }
    return report


def _apply_and_view(report: dict) -> dict:
    from axiom_oracles.comparison.dispositions import apply_dispositions, load_dispositions

    dispositions = load_dispositions(DISPOSITIONS_PATH, repo_root=REPO_ROOT)
    merged = apply_dispositions(
        report,
        dispositions,
        dispositions_file=str(DISPOSITIONS_PATH.relative_to(REPO_ROOT)),
    )
    for program, view in merged["views"].items():
        columns = set(view["columns"])
        rows = [
            row for row in merged["mismatches"]
            if (row.get("metadata") or {}).get("column") in columns
        ]
        comparisons = 104 * len(columns)
        counts = Counter(
            (row.get("disposition") or {}).get("disposition", "unexplained")
            for row in rows
        )
        view["summary"] = {
            "comparison_count": comparisons,
            "match_count": comparisons - len(rows),
            "mismatch_count": len(rows),
            "dispositioned": {
                "dispositions_file": str(DISPOSITIONS_PATH.relative_to(REPO_ROOT)),
                "counts": {
                    name: counts.get(name, 0)
                    for name in (
                        "explained_residual",
                        "upstream_engine_gap",
                        "bridge_artifact",
                        "axiom_encoding_gap",
                        "unexplained",
                    )
                },
                "unexplained_count": counts.get("unexplained", 0),
            },
        }
    return merged


def build() -> dict:
    source = _load(SOURCE_PATH)
    snapshot = _load(SNAPSHOT_PATH)
    closures = _load(CLOSURES_PATH)
    _validate_inputs(source, snapshot, closures)
    return _apply_and_view(_base_report(source, snapshot, closures))


def _instrument_names(source: dict, row: dict, at_point: dict[tuple, list[dict]]) -> list[str]:
    code = row["reason_code"]
    column = row["column"]
    scenario = next(item for item in source["scenarios"] if item["id"] == row["scenario_id"])
    children = scenario["inputs"]["children_ages"]
    partnered = scenario["inputs"]["partnered"]

    def benefit() -> str:
        if partnered and children:
            return "JSS partnered-with-children weekly rate (SSA 2018 Sch 4 pt 1 cl 1(g)(ii))"
        if children and min(children) < 14:
            return "Sole Parent Support weekly rate (SSA 2018 Sch 4 pt 2 cl 1)"
        if children:
            return "lone-parent JSS weekly rate (SSA 2018 Sch 4 pt 1 cl 1(e))"
        return "JSS single-no-children weekly rate (SSA 2018 Sch 4 pt 1 cl 1(d))"

    direct = {
        "FTC_abated": "Family Tax Credit annual prescribed amount (Income Tax Act 2007 s MD 3)",
        "IWTC_abated": "In-Work Tax Credit base (Income Tax Act 2007 s MD 10)",
        "MFTC": "Minimum Family Tax Credit prescribed amount (Income Tax Act 2007 s ME 1)",
        "BestStart_Total": "Best Start prescribed amount (Income Tax Act 2007 s MG 2)",
    }
    if code == "B_BENEFIT_VINTAGE" or code == "B_BENEFIT_GROSSUP_TAX" or code == "B_WINTER_ENERGY_BENEFIT_GATE":
        return [benefit()]
    if column in direct:
        return [direct[column]]
    if code == "C_IETC_WHOLE_DOLLARS":
        return ["IETC statutory complete-dollar arithmetic (Income Tax Act 2007 s LC 13)"]
    point_rows = at_point[(row["scenario_id"], row["weekly_wage"])]
    names = [direct[item["column"]] for item in point_rows if item["column"] in direct and item["classification"] == "b"]
    if any(item["column"] == "net_benefit" and item["classification"] == "b" for item in point_rows):
        names.append(benefit())
    if not names:
        names = [benefit()]
    return sorted(set(names))


def bootstrap_dispositions() -> str:
    source = _load(SOURCE_PATH)
    snapshot = _load(SNAPSHOT_PATH)
    closures = _load(CLOSURES_PATH)
    _validate_inputs(source, snapshot, closures)
    amount = [row for row in source["comparisons"] if row["column"] != "EMTR"]
    outside = [row for row in amount if Decimal(row["absolute_delta"]) >= AMOUNT_TOLERANCE]
    at_point: dict[tuple, list[dict]] = defaultdict(list)
    for row in amount:
        at_point[(row["scenario_id"], row["weekly_wage"])].append(row)
    entries = []
    for index, row in enumerate(outside, start=1):
        instruments = _instrument_names(source, row, at_point)
        entries.append(
            {
                "id": f"nz-ie-{index:04d}-{row['reason_code'].lower().replace('_', '-')}",
                "concept": COLUMN_CONCEPTS[row["column"]],
                "case_id": _case_id(row),
                "kind": "amount_difference",
                "disposition": "explained_residual",
                "evidence": {
                    "mechanism": (
                        f"{row['reason_title']}: {row['reason']} Named instrument(s): "
                        + "; ".join(instruments)
                    ),
                    "sources": [
                        str(SOURCE_PATH.relative_to(REPO_ROOT)),
                        "https://github.com/TheAxiomFoundation/rulespec-nz/issues/108",
                    ],
                },
                "expires_on_source_change": True,
                "pinned": {
                    "left": _number(row["rulespec"]),
                    "right": _number(row["treasury"]),
                    "difference": _number(row["signed_delta_rulespec_minus_treasury"]),
                },
            }
        )
    document = {
        "schema": "axiom_oracles.dispositions.v1",
        "suite": SUITE,
        "updated": "2026-08-13",
        "entries": entries,
    }
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--bootstrap-dispositions", action="store_true")
    args = parser.parse_args()
    try:
        if args.bootstrap_dispositions:
            rendered = bootstrap_dispositions()
            if args.check:
                if not DISPOSITIONS_PATH.exists() or DISPOSITIONS_PATH.read_text() != rendered:
                    print("NZ IncomeExplorer dispositions drifted", file=sys.stderr)
                    return 1
            else:
                DISPOSITIONS_PATH.write_text(rendered, encoding="utf-8")
            return 0
        record = build()
        attestations = build_single_person_attestations()
    except (NZRecordError, OSError, ValueError) as exc:
        print(f"NZ IncomeExplorer ERROR: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    attestation_rendered = (
        json.dumps(attestations, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )
    if args.check:
        if not OUTPUT_PATH.exists() or OUTPUT_PATH.read_text(encoding="utf-8") != rendered:
            print("NZ IncomeExplorer unified record drifted", file=sys.stderr)
            return 1
        if (
            not ATTESTATION_PATH.exists()
            or ATTESTATION_PATH.read_text(encoding="utf-8") != attestation_rendered
        ):
            print("NZ single-person attestations drifted", file=sys.stderr)
            return 1
        print("NZ IncomeExplorer unified record up to date")
        return 0
    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    ATTESTATION_PATH.write_text(attestation_rendered, encoding="utf-8")
    print(f"wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    print(f"wrote {ATTESTATION_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
