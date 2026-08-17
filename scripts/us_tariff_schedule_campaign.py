#!/usr/bin/env python3
"""Fail-closed stages for the Yale full-schedule tariff campaign.

The disposition pre-pass is deliberately independent of the engine.  It maps
each Yale statistical member to the generated statutory rate line, receipts
the General and column-2 disposition texts, and fixes the query surface before
shards are planned.  A non-ad-valorem base suppresses only the base and total
queries; authority-component queries remain in the plan.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SELECTED = REPO_ROOT / "reference/us-tariff-schedule/selected-intervals.csv.gz"
OUT_DIR = REPO_ROOT / "reference/us-tariff-schedule"
ROUTING_ROWS = OUT_DIR / "disposition-routing.csv.gz"
ROUTING_RECEIPT = OUT_DIR / "disposition-routing-receipt.json"
INPUT_CONTRACT_RECEIPT = OUT_DIR / "declared-input-contract-receipt.json"
EVAL_DIR = OUT_DIR / "eval"
EVAL_PROJECTION_RECEIPT = OUT_DIR / "evaluation-projection-receipt.json"
SCHEMA = "axiom_oracles.us_tariff_schedule.disposition_routing.v1"
DISPOSITIONS = {
    "ad_valorem", "free", "specific", "compound", "component",
    "conditional", "empty",
}
COMPARABLE = {"ad_valorem", "free"}
COLUMN2_ORIGINS = {"CU", "KP", "BY", "RU"}
# The pinned table generator's explicit structural census: a statistical row
# with no rated ancestor.  It is not silently inferred from a failed lookup.
EXPECTED_UNOWNED = {"9802009100"}
COMPONENT_SLOTS = (
    "ieepa", "section_201", "section_122", "section_232_aluminum",
    "section_232_steel", "section_338", "china_section_301",
    "brazil_section_301", "forced_labor_section_301",
)
BASE_DEPENDENT_COMPONENTS = ("ieepa", "forced_labor_section_301")
EXPECTED_DROPPED_ENTRY_FLAGS = frozenset({"entry_is_line_c", "entry_is_line_e"})
NEUTRAL_BOOLEAN_INPUTS = (
    "article_is_potash", "cbp_agrees_chapter_98_entry_is_appropriate",
    "entry_is_9802_excepted_entry", "entry_is_chapter_98_subchapter_xxiii_entry",
    "entry_is_entered_free_of_duty_under_usmca",
    "entry_is_humanitarian_donation_article", "entry_is_informational_material_article",
    "entry_is_personal_use_accompanied_baggage",
    "entry_is_properly_claimed_chapter_98_entry", "entry_is_usmca_duty_free_entry",
    "entry_loaded_and_in_transit_before_july_24_2026",
)
OUTPUT_NAMES = (
    "mfn_ad_valorem_rate", "ieepa_component_rate", "section_201_component_rate",
    "section_122_component_rate", "section_232_aluminum_component_rate",
    "section_232_steel_component_rate", "section_338_component_rate",
    "china_section_301_component_rate", "brazil_section_301_component_rate",
    "forced_labor_section_301_component_rate", "schedule_statutory_stack",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _render(value: Any) -> str:
    return json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _collect_artifact_inputs(node: Any, inputs: set[str]) -> None:
    """Collect the engine's compiled input surface, including input-or-else."""
    if isinstance(node, list):
        for item in node:
            _collect_artifact_inputs(item, inputs)
    elif isinstance(node, dict):
        if node.get("kind") in {"input", "input_or_else"}:
            name = node.get("name")
            _require(isinstance(name, str) and name, "compiled input has no name")
            inputs.add(name)
        for value in node.values():
            _collect_artifact_inputs(value, inputs)


def declared_inputs_from_artifact(path: Path) -> frozenset[str]:
    payload = json.loads(path.read_text())
    program = payload.get("program")
    _require(isinstance(program, dict), f"{path}: compiled artifact has no program")
    inputs: set[str] = set()
    _collect_artifact_inputs(program, inputs)
    _require(inputs, f"{path}: compiled artifact declares no inputs")
    return frozenset(inputs)


def filter_declared_feed(
    feed: dict[str, Any],
    declared_inputs: Iterable[str],
    *,
    emitted_flag_names: Iterable[str],
    expected_dropped_flags: frozenset[str] = EXPECTED_DROPPED_ENTRY_FLAGS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fail-closed projection of one case feed onto its compiled input surface.

    Only surplus fields emitted by the entry-flag tool may be projected away.
    Every declared field must already be present: the engine supports
    ``input_or_else`` defaults, but this campaign deliberately does not rely on
    them because an accidentally unfed declared input must remain observable.
    """
    declared = frozenset(declared_inputs)
    supplied = frozenset(feed)
    emitted = frozenset(emitted_flag_names)
    dropped = supplied - declared
    missing = declared - supplied
    _require(dropped <= emitted, f"undeclared non-flag inputs in feed: {sorted(dropped - emitted)}")
    _require(
        dropped == expected_dropped_flags,
        f"dropped entry flags changed: expected {sorted(expected_dropped_flags)}, got {sorted(dropped)}",
    )
    _require(not missing, f"declared inputs absent from feed: {sorted(missing)}")
    filtered = {name: value for name, value in feed.items() if name in declared}
    return filtered, {
        "declared_input_count": len(declared),
        "supplied_input_count": len(supplied),
        "forwarded_input_count": len(filtered),
        "dropped_entry_flags": sorted(dropped),
        "missing_declared_inputs": sorted(missing),
        "absent_declared_input_semantics": (
            "STOP in harness before engine; engine input_or_else can substitute its "
            "per-reference default, while a strict input raises MissingInput"
        ),
    }


def build_input_contract_receipt(*, rulespec_root: Path, engine_binary: Path) -> dict[str, Any]:
    """Compile all generated compositions and receipt their entry-flag surface."""
    sys.path.insert(0, str(rulespec_root))
    from tools.b16_entry_flags import entry_flags  # type: ignore

    emitted = entry_flags(102294000, "0102294024", "CA")
    # The tool also returns incidence diagnostics (``s232_*``, list-specific
    # helpers).  The harness feeds only its public entry-input namespace.
    emitted_names = frozenset(name for name in emitted if name.startswith("entry_is_"))
    modules = sorted(
        path for path in (rulespec_root / "us/policies/cbp/us-tariff-schedule/generated").glob("ch*/ch*.yaml")
        if not path.name.endswith(".test.yaml")
    )
    _require(len(modules) == 100, f"expected 100 generated compositions, found {len(modules)}")
    env = dict(__import__("os").environ)
    env["AXIOM_RULESPEC_REPO_ROOTS"] = str(rulespec_root.parent)
    chapters = []
    with tempfile.TemporaryDirectory(prefix="tariff-input-contract-") as raw:
        work = Path(raw)
        for index, module in enumerate(modules):
            artifact = work / f"chapter-{index:03d}.json"
            subprocess.run(
                [str(engine_binary), "compile", "--program", str(module.resolve()), "--output", str(artifact)],
                check=True, capture_output=True, text=True, env=env,
            )
            declared = declared_inputs_from_artifact(artifact)
            declared_flags = declared & emitted_names
            dropped = emitted_names - declared_flags
            _require(
                dropped == EXPECTED_DROPPED_ENTRY_FLAGS,
                f"{module}: dropped entry flags changed: {sorted(dropped)}",
            )
            _require(
                not (declared_flags - emitted_names),
                f"{module}: declared entry flags are not emitted: {sorted(declared_flags - emitted_names)}",
            )
            chapters.append({
                "chapter": module.parent.name.removeprefix("ch"),
                "module": str(module.relative_to(rulespec_root)),
                "module_sha256": _sha256(module),
                "artifact_sha256": _sha256(artifact),
                "declared_input_count": len(declared),
                "declared_entry_flags": sorted(declared_flags),
                "dropped_entry_flags": sorted(dropped),
                "missing_declared_entry_flags": [],
            })
    return {
        "schema": "axiom_oracles.us_tariff_schedule.declared_input_contract.v1",
        "composition_count": len(chapters),
        "entry_flag_tool": str((rulespec_root / "tools/b16_entry_flags.py").relative_to(rulespec_root)),
        "entry_flag_tool_sha256": _sha256(rulespec_root / "tools/b16_entry_flags.py"),
        "emitted_entry_flags": sorted(emitted_names),
        "expected_dropped_entry_flags": sorted(EXPECTED_DROPPED_ENTRY_FLAGS),
        "absent_declared_input_semantics": {
            "harness": "STOP before engine execution",
            "engine_strict_input": "MissingInput",
            "engine_input_or_else": "substitutes the compiled per-reference default",
            "campaign_policy": "never default a declared case-feed input silently",
        },
        "chapters": chapters,
        "verdict": "PASS",
    }


def _chapter_table_paths(rulespec_root: Path) -> list[Path]:
    directory = rulespec_root / "us/policies/usitc/us-tariff-duty/lines/generated"
    paths = sorted(
        path for path in directory.glob("ch*.yaml")
        if not path.name.endswith(".test.yaml")
    )
    _require(len(paths) == 100, f"expected 100 generated chapter tables, found {len(paths)}")
    return paths


def _rule_values(payload: dict, name: str) -> dict[int, str]:
    rules = [rule for rule in payload.get("rules", []) if rule.get("name") == name]
    _require(len(rules) == 1, f"expected exactly one {name} rule")
    versions = rules[0].get("versions", [])
    _require(len(versions) == 1 and isinstance(versions[0].get("values"), dict), f"bad {name} values")
    values = {int(key): str(value) for key, value in versions[0]["values"].items()}
    _require(values and set(values.values()) <= DISPOSITIONS, f"invalid {name} disposition")
    return values


def load_tables(rulespec_root: Path) -> tuple[dict[str, dict[int, tuple[str, str]]], list[dict[str, Any]]]:
    tables: dict[str, dict[int, tuple[str, str]]] = {}
    sources = []
    for path in _chapter_table_paths(rulespec_root):
        shard = path.stem.removeprefix("ch")
        payload = yaml.safe_load(path.read_text())
        general = _rule_values(payload, f"ch{shard}_general_disposition")
        column2 = _rule_values(payload, f"ch{shard}_column2_disposition")
        _require(set(general) == set(column2), f"ch{shard} disposition keysets differ")
        tables[shard] = {key: (general[key], column2[key]) for key in general}
        sources.append({"path": str(path.relative_to(rulespec_root)), "sha256": _sha256(path)})
    return tables, sources


def verify_component_formulas(rulespec_root: Path) -> dict[str, Any]:
    """Prove generated authority components do not query base or total."""
    directory = rulespec_root / "us/policies/cbp/us-tariff-schedule/generated"
    paths = sorted(
        path for path in directory.glob("ch*/ch*.yaml")
        if not path.name.endswith(".test.yaml")
    )
    _require(len(paths) == 100, f"expected 100 generated compositions, found {len(paths)}")
    digest = hashlib.sha256()
    checked = 0
    forbidden = ("mfn_ad_valorem_rate", "schedule_base_general_rate", "schedule_statutory_stack")
    dependent: set[str] = set()
    for path in paths:
        raw = path.read_bytes()
        digest.update(hashlib.sha256(raw).digest())
        payload = yaml.safe_load(raw)
        by_name = {rule.get("name"): rule for rule in payload.get("rules", [])}
        for name in COMPONENT_SLOTS:
            rule_name = f"{name}_component_rate"
            rule = by_name.get(rule_name)
            _require(rule is not None, f"{path}: missing {rule_name}")
            formulas = "\n".join(
                str(version.get("formula", "")) for version in rule.get("versions", [])
            )
            if any(token in formulas for token in forbidden):
                dependent.add(name)
            checked += 1
    _require(dependent == set(BASE_DEPENDENT_COMPONENTS),
             f"component/base dependency inventory changed: {sorted(dependent)}")
    return {
        "generated_compositions": len(paths),
        "component_formulas_checked": checked,
        "composition_hash_aggregate": digest.hexdigest(),
        "base_or_total_required_by_component": sorted(dependent),
    }


def route_member(hts10: str, tables: dict[str, dict[int, tuple[str, str]]]) -> tuple[str, int, str, str]:
    _require(re.fullmatch(r"\d{10}", hts10) is not None, f"invalid HTS-10 {hts10!r}")
    if hts10 in EXPECTED_UNOWNED:
        return "98", int(hts10), "empty", "empty"
    shards = [hts10[:2]] if hts10[:2] != "99" else ["99a", "99b", "99c"]
    # HTS document order is numeric within a chapter.  An unrated statistical
    # member belongs to the most recent rated ancestor in that order (the same
    # indent-stack rule used by the pinned generator); exact rated members are
    # naturally their own owner.  Prefix matching is incorrect for structural
    # children such as 9817.22.05.00 under 9817.00.98.00.
    member_number = int(hts10)
    candidates = []
    for shard in shards:
        for key, dispositions in tables.get(shard, {}).items():
            if key <= member_number:
                candidates.append((key, shard, *dispositions))
    _require(candidates, f"no generated disposition route for {hts10}")
    best_key = max(row[0] for row in candidates)
    best = [row for row in candidates if row[0] == best_key]
    _require(len(best) == 1, f"ambiguous generated disposition route for {hts10}: {best}")
    key, shard, general, column2 = best[0]
    return shard, key, general, column2


def query_plan(disposition: str, *, column2_rate_available: bool = True) -> dict[str, Any]:
    _require(disposition in DISPOSITIONS, f"unknown disposition {disposition!r}")
    comparable = disposition in COMPARABLE and column2_rate_available
    reason = None if comparable else (
        f"non_ad_valorem_base:{disposition}"
        if disposition not in COMPARABLE else "structurally_unavailable:column2_rate"
    )
    compared_components = list(COMPONENT_SLOTS if comparable else (
        slot for slot in COMPONENT_SLOTS if slot not in BASE_DEPENDENT_COMPONENTS
    ))
    excluded_components = [] if comparable else list(BASE_DEPENDENT_COMPONENTS)
    return {
        "base": "compare" if comparable else "known_not_comparable",
        "total": "compare" if comparable else "known_not_comparable",
        "reason": reason,
        "components": compared_components,
        "excluded_components": excluded_components,
        "component_exclusion_reason": None if comparable else "requires_noncomparable_base",
    }


def _selected_rows(path: Path) -> Iterable[dict[str, str]]:
    with gzip.open(path, "rt", newline="") as source:
        yield from csv.DictReader(source)


def build_prepass(*, rulespec_root: Path, selected_path: Path = SELECTED) -> tuple[list[dict[str, str]], dict[str, Any]]:
    tables, sources = load_tables(rulespec_root)
    formula_receipt = verify_component_formulas(rulespec_root)
    unique_members: set[str] = set()
    for row in _selected_rows(selected_path):
        unique_members.add(row["hts10"])
    routes = {}
    output_rows = []
    for member in sorted(unique_members):
        shard, line, general, column2 = route_member(member, tables)
        routes[member] = (shard, line, general, column2)
        output_rows.append({
            "hts10": member, "chapter_shard": shard, "hts_line": f"{line:010d}",
            "general_disposition": general, "column2_disposition": column2,
        })

    cell_counts: Counter[str] = Counter()
    disposition_counts: Counter[str] = Counter()
    total = 0
    for row in _selected_rows(selected_path):
        total += 1
        shard, _line, general, column2 = routes[row["hts10"]]
        is_column2 = row["iso2"] in COLUMN2_ORIGINS
        disposition = column2 if is_column2 else general
        column2_available = not (is_column2 and shard in {"99a", "99b"})
        plan = query_plan(disposition, column2_rate_available=column2_available)
        disposition_counts[disposition] += 1
        cell_counts["full_comparison" if plan["base"] == "compare" else "components_only"] += 1
        if not column2_available and disposition in COMPARABLE:
            cell_counts["structurally_unavailable_column2"] += 1

    excluded = cell_counts["components_only"]
    receipt = {
        "schema": SCHEMA,
        "selected_source": {"path": str(selected_path.relative_to(REPO_ROOT)), "sha256": _sha256(selected_path)},
        "rulespec_tables": sources,
        "routing_rows": len(output_rows),
        "evaluated_cells": total,
        "full_comparison_cells": cell_counts["full_comparison"],
        "non_ad_valorem_components_only_cells": excluded,
        "non_ad_valorem_share": excluded / total,
        "structurally_unavailable_column2_cells": cell_counts["structurally_unavailable_column2"],
        "base_dependent_component_excluded_slots": excluded * len(BASE_DEPENDENT_COMPONENTS),
        "selected_disposition_counts": dict(sorted(disposition_counts.items())),
        "scope_statement": (
            f"{excluded} of {total} evaluated cells carry a non-ad-valorem statutory base "
            "and are compared on authority components only"
        ),
        "component_formula_contract": {
            "queried_for_every_cell": [
                slot for slot in COMPONENT_SLOTS if slot not in BASE_DEPENDENT_COMPONENTS
            ],
            "queried_only_with_comparable_base": list(BASE_DEPENDENT_COMPONENTS),
            **formula_receipt,
        },
    }
    _require(total > 0 and sum(cell_counts[k] for k in ("full_comparison", "components_only")) == total,
             "disposition routing does not conserve selected cells")
    return output_rows, receipt


def write_prepass(rows: list[dict[str, str]], receipt: dict[str, Any]) -> None:
    # gzip mtime=0 makes the content-addressed routing artifact reproducible.
    with ROUTING_ROWS.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as compressed:
            with io.TextIOWrapper(compressed, newline="") as target:
                writer = csv.DictWriter(target, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
    receipt["routing_artifact"] = {"path": str(ROUTING_ROWS.relative_to(REPO_ROOT)), "sha256": _sha256(ROUTING_ROWS)}
    ROUTING_RECEIPT.write_text(_render(receipt))


def _routing_by_member() -> dict[str, dict[str, str]]:
    with gzip.open(ROUTING_ROWS, "rt", newline="") as source:
        rows = list(csv.DictReader(source))
    _require(len(rows) == 20_508, f"routing member count changed: {len(rows)}")
    return {row["hts10"]: row for row in rows}


def _probe_dates(row: dict[str, str]) -> tuple[str, ...]:
    start = date.fromisoformat(row["clipped_from"])
    end = date.fromisoformat(row["clipped_until"])
    _require(start <= end, f"inverted clipped interval: {row}")
    return (start.isoformat(),) if start == end else (start.isoformat(), end.isoformat())


def _first_shard_cases(*, rulespec_root: Path, limit: int) -> tuple[list[Any], list[str]]:
    """Build the deterministic timing shard using only full-comparison cells."""
    from axiom_oracles.core.case import Case

    sys.path.insert(0, str(rulespec_root))
    from tools.b16_entry_flags import entry_flags  # type: ignore

    routes = _routing_by_member()
    chapter = "01"
    module = f"us:policies/cbp/us-tariff-schedule/generated/ch{chapter}/ch{chapter}"
    outputs = [f"{module}#{name}" for name in OUTPUT_NAMES]
    cases = []
    for row in _selected_rows(SELECTED):
        route = routes[row["hts10"]]
        if route["chapter_shard"] != chapter:
            continue
        disposition = (
            route["column2_disposition"]
            if row["iso2"] in COLUMN2_ORIGINS else route["general_disposition"]
        )
        if disposition not in COMPARABLE:
            continue
        for probe in _probe_dates(row):
            flags = {
                key: value for key, value in entry_flags(
                    int(route["hts_line"]), row["hts10"], row["iso2"]
                ).items()
                if key.startswith("entry_is_") and key not in EXPECTED_DROPPED_ENTRY_FLAGS
            }
            feed = {
                "hts_line": int(route["hts_line"]),
                "hts_number": row["hts10"],
                "country_of_origin": row["iso2"],
                **{name: False for name in NEUTRAL_BOOLEAN_INPUTS},
                **flags,
            }
            cases.append(Case(
                case_id=f"{row['hts10']}-{row['country']}-{probe}",
                period=probe,
                metadata={
                    "axiom_entity": "CustomsEntry", "axiom_entity_id": "entry",
                    "axiom_inputs": {
                        f"{module}#input.{name}": value for name, value in feed.items()
                    },
                },
                outputs=tuple(outputs),
            ))
            if len(cases) == limit:
                return cases, outputs
    raise ValueError(f"chapter {chapter} has only {len(cases)} timing cases; need {limit}")


def evaluate_projection(*, rulespec_root: Path, engine_binary: Path, limit: int = 5_001) -> dict[str, Any]:
    """Run and deterministically replay the first shard, then enforce 16 hours."""
    from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner

    cases, outputs = _first_shard_cases(rulespec_root=rulespec_root, limit=limit)
    program = rulespec_root / "us/policies/cbp/us-tariff-schedule/generated/ch01/ch01.yaml"
    runs = []
    value_hashes = []
    for _replay in range(2):
        started = time.perf_counter()
        runner = AxiomRulesRunner(
            program_path=program, binary_path=engine_binary,
            default_entity="CustomsEntry", default_entity_id="entry",
            rulespec_repo_roots=(rulespec_root,), batch_size=limit,
        )
        results = runner.run_cases(cases, outputs)
        elapsed = time.perf_counter() - started
        errors = [result for result in results if result.errors]
        if errors:
            raise ValueError(f"first shard engine errors: {errors[0].errors}")
        canonical = _render([
            {"case_id": str(result.household_id), "values": result.values}
            for result in results
        ]).encode()
        value_hashes.append(hashlib.sha256(canonical).hexdigest())
        runs.append({"engine_wall_clock_seconds": elapsed, "case_count": len(results)})
    _require(len(set(value_hashes)) == 1, f"first-shard determinism failure: {value_hashes}")
    selected_cells = json.loads(ROUTING_RECEIPT.read_text())["evaluated_cells"]
    endpoint_upper_bound = selected_cells * 2
    projected_seconds = max(run["engine_wall_clock_seconds"] for run in runs) * endpoint_upper_bound / limit / 3
    receipt = {
        "schema": "axiom_oracles.us_tariff_schedule.evaluation_projection.v1",
        "chapter_shard": "01", "batch_cases": limit, "replay_runs": runs,
        "result_sha256": value_hashes[0], "deterministic": True,
        "selected_interval_cells": selected_cells,
        "endpoint_case_upper_bound": endpoint_upper_bound,
        "maximum_concurrent_engine_processes": 3,
        "projection_method": "slowest replay seconds/case * two-endpoint upper bound / 3 workers",
        "projected_engine_seconds": projected_seconds,
        "projected_engine_hours": projected_seconds / 3600,
        "ceiling_hours": 16,
        "verdict": "PASS" if projected_seconds <= 16 * 3600 else "STOP_16H_PROJECTION_BREACH",
    }
    EVAL_PROJECTION_RECEIPT.write_text(_render(receipt))
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("prepass", "input-contract", "evaluate"))
    parser.add_argument("--rulespec-root", type=Path, required=True)
    parser.add_argument("--engine-binary", type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    if args.stage == "evaluate":
        _require(args.engine_binary is not None, "--engine-binary is required")
        receipt = evaluate_projection(
            rulespec_root=args.rulespec_root.resolve(),
            engine_binary=args.engine_binary.resolve(),
        )
        print(_render(receipt), end="")
        return 0 if receipt["verdict"] == "PASS" else 2
    if args.stage == "input-contract":
        _require(args.engine_binary is not None, "--engine-binary is required")
        receipt = build_input_contract_receipt(
            rulespec_root=args.rulespec_root.resolve(),
            engine_binary=args.engine_binary.resolve(),
        )
        receipt["stage_wall_clock_seconds"] = round(time.perf_counter() - started, 3)
        INPUT_CONTRACT_RECEIPT.write_text(_render(receipt))
        print(_render(receipt), end="")
        return 0
    rows, receipt = build_prepass(rulespec_root=args.rulespec_root.resolve())
    receipt["stage_wall_clock_seconds"] = round(time.perf_counter() - started, 3)
    write_prepass(rows, receipt)
    print(_render(receipt), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
