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
import concurrent.futures
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
import os
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Iterator

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
EVAL_MANIFEST = EVAL_DIR / "MANIFEST.json"
COMPARISON_RECEIPT = OUT_DIR / "comparison-summary.json"
CLASSIFICATION_RECEIPT = OUT_DIR / "classification-receipt.json"
DISPOSITION_LEDGER = REPO_ROOT / "dispositions/us-tariff-schedule.yaml"
REPORT_PATH = REPO_ROOT / "conformance/detail/us-tariff-schedule.json"
CACHE_ROOT = Path(os.environ.get(
    "AXIOM_TARIFF_C1_CACHE", "~/PolicyEngine/_tariff-p5/c1-cache"
)).expanduser()
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
TOLERANCE = 1e-12
SELECTOR_FIELDS = frozenset({
    "slot", "origin_regime", "revision", "delta", "disposition", "line_class", "iso2",
})
EXPECTED_COLUMNS = (
    "statutory_base_rate", "statutory_rate_232", "statutory_rate_ieepa_recip",
    "statutory_rate_ieepa_fent", "statutory_rate_301", "statutory_rate_301_cs",
    "statutory_rate_s301fl", "statutory_rate_s301br", "statutory_rate_s338",
    "statutory_rate_s122", "statutory_rate_section_201", "statutory_rate_other",
)
SLOT_OUTPUTS = {
    "base": ("mfn_ad_valorem_rate",),
    "ieepa": ("ieepa_component_rate",),
    "section_122": ("section_122_component_rate",),
    "section_201": ("section_201_component_rate",),
    "section_232": ("section_232_aluminum_component_rate", "section_232_steel_component_rate"),
    "china_section_301": ("china_section_301_component_rate",),
    "brazil_section_301": ("brazil_section_301_component_rate",),
    "forced_labor_section_301": ("forced_labor_section_301_component_rate",),
    "section_338": ("section_338_component_rate",),
}
EXPECTED_SLOT_COLUMNS = {
    "base": ("statutory_base_rate",),
    "ieepa": ("statutory_rate_ieepa_recip", "statutory_rate_ieepa_fent"),
    "section_122": ("statutory_rate_s122",),
    "section_201": ("statutory_rate_section_201",),
    "section_232": ("statutory_rate_232",),
    "china_section_301": ("statutory_rate_301",),
    "brazil_section_301": ("statutory_rate_s301br",),
    "forced_labor_section_301": ("statutory_rate_s301fl",),
    "section_338": ("statutory_rate_s338",),
}
AUTHORITY_SLOTS = tuple(slot for slot in SLOT_OUTPUTS if slot != "base")
BASE_INDEPENDENT_AUTHORITY_SLOTS = (
    "section_201", "section_122", "section_232", "section_338",
    "china_section_301", "brazil_section_301",
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
    compared_components = list(AUTHORITY_SLOTS if comparable else BASE_INDEPENDENT_AUTHORITY_SLOTS)
    excluded_components = [] if comparable else ["ieepa", "forced_labor_section_301"]
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


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = _render(payload)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as target:
        target.write(rendered)
        temporary = Path(target.name)
    temporary.replace(path)


def _load_manifest() -> dict[str, Any]:
    if not EVAL_MANIFEST.exists():
        return {"schema": "axiom_oracles.us_tariff_schedule.eval_manifest.v1", "shards": {}}
    payload = json.loads(EVAL_MANIFEST.read_text())
    _require(payload.get("schema") == "axiom_oracles.us_tariff_schedule.eval_manifest.v1", "bad eval manifest schema")
    _require(isinstance(payload.get("shards"), dict), "bad eval manifest shards")
    return payload


def _chapter_from_route(route: dict[str, str]) -> str:
    return route["chapter_shard"]


def _case_feed(row: dict[str, str], route: dict[str, str], entry_flags: Any) -> tuple[dict[str, Any], dict[str, bool]]:
    raw_flags = entry_flags(int(route["hts_line"]), row["hts10"], row["iso2"])
    flags = {
        key: bool(value) for key, value in raw_flags.items()
        if key.startswith("entry_is_") and key not in EXPECTED_DROPPED_ENTRY_FLAGS
    }
    feed = {
        "hts_line": int(route["hts_line"]), "hts_number": row["hts10"],
        "country_of_origin": row["iso2"],
        **{name: False for name in NEUTRAL_BOOLEAN_INPUTS}, **flags,
    }
    return feed, flags


def _case_id(row: dict[str, str], probe: str, ordinal: int) -> str:
    identity = "|".join((row["hts10"], row["country"], row["revision"],
                         row["clipped_from"], row["clipped_until"], probe, str(ordinal)))
    return "schedule-" + hashlib.sha256(identity.encode()).hexdigest()[:24]


def _chapter_records(chapter: str) -> Iterator[dict[str, Any]]:
    routes = _routing_by_member()
    for row in _selected_rows(SELECTED):
        route = routes[row["hts10"]]
        if _chapter_from_route(route) != chapter:
            continue
        disposition = route["column2_disposition"] if row["iso2"] in COLUMN2_ORIGINS else route["general_disposition"]
        column2_available = not (row["iso2"] in COLUMN2_ORIGINS and route["chapter_shard"] in {"99a", "99b"})
        plan = query_plan(disposition, column2_rate_available=column2_available)
        for ordinal, probe in enumerate(_probe_dates(row)):
            yield {"row": row, "route": route, "plan": plan, "probe": probe, "ordinal": ordinal}


def _module_path(rulespec_root: Path, chapter: str) -> Path:
    return rulespec_root / f"us/policies/cbp/us-tariff-schedule/generated/ch{chapter}/ch{chapter}.yaml"


def _shard_key(*, chapter: str, rulespec_root: Path, engine_binary: Path) -> str:
    ingredients = {
        "chapter": chapter, "selected_sha256": _sha256(SELECTED),
        "routing_sha256": _sha256(ROUTING_ROWS), "module_sha256": _sha256(_module_path(rulespec_root, chapter)),
        "engine_sha256": _sha256(engine_binary), "outputs": OUTPUT_NAMES,
        "input_contract_sha256": _sha256(INPUT_CONTRACT_RECEIPT),
    }
    return hashlib.sha256(_render(ingredients).encode()).hexdigest()


def _result_values(result: Any, requested: Iterable[str]) -> dict[str, float]:
    values = {}
    for key, value in result.values.items():
        short = key.rsplit("#", 1)[-1]
        _require(short in OUTPUT_NAMES, f"unexpected engine output {key}")
        number = float(value)
        _require(number == number and abs(number) != float("inf"), f"non-finite engine output {key}")
        values[short] = number
    _require(set(values) == set(requested), f"missing engine outputs: {sorted(set(requested) - set(values))}")
    return values


def _evaluate_chapter(chapter: str, *, rulespec_root: Path, engine_binary: Path, cache_dir: Path) -> dict[str, Any]:
    from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner
    from axiom_oracles.core.case import Case

    sys.path.insert(0, str(rulespec_root))
    from tools.b16_entry_flags import entry_flags  # type: ignore

    started = time.perf_counter()
    records = list(_chapter_records(chapter))
    module_ref = f"us:policies/cbp/us-tariff-schedule/generated/ch{chapter}/ch{chapter}"
    cases: dict[str, list[Any]] = {"full": [], "components": []}
    contexts: dict[str, list[Any]] = {"full": [], "components": []}
    for record in records:
        feed, flags = _case_feed(record["row"], record["route"], entry_flags)
        case_id = _case_id(record["row"], record["probe"], record["ordinal"])
        group = "full" if record["plan"]["base"] == "compare" else "components"
        requested = list(dict.fromkeys(
            name for slot in record["plan"]["components"] for name in SLOT_OUTPUTS[slot]
        ))
        if group == "full":
            requested += ["mfn_ad_valorem_rate", "schedule_statutory_stack"]
        outputs = tuple(f"{module_ref}#{name}" for name in requested)
        cases[group].append(Case(case_id=case_id, period=record["probe"], metadata={
            "axiom_entity": "CustomsEntry", "axiom_entity_id": "entry",
            "axiom_inputs": {f"{module_ref}#input.{name}": value for name, value in feed.items()},
        }, outputs=outputs))
        contexts[group].append((record, flags, case_id, requested))
    runner = AxiomRulesRunner(program_path=_module_path(rulespec_root, chapter), binary_path=engine_binary,
                              default_entity="CustomsEntry", default_entity_id="entry",
                              rulespec_repo_roots=(rulespec_root,), batch_size=5_000)
    paired = []
    for group in ("full", "components"):
        group_cases = cases[group]
        if not group_cases:
            continue
        variables = list(group_cases[0].outputs)
        results = runner.run_cases(group_cases, variables)
        _require(len(results) == len(contexts[group]), f"chapter {chapter}: missing engine results")
        paired.extend(zip(results, contexts[group], strict=True))
    key = _shard_key(chapter=chapter, rulespec_root=rulespec_root, engine_binary=engine_binary)
    path = cache_dir / key[:2] / f"{key}.jsonl.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    errors = 0
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as raw:
        temporary = Path(raw.name)
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=6, mtime=0) as zipped:
            for result, (record, flags, case_id, requested) in paired:
                error = list(result.errors or [])
                errors += bool(error)
                payload = {
                    "case_id": case_id, "chapter": chapter, "probe": record["probe"],
                    "expected": {name: record["row"][name] for name in EXPECTED_COLUMNS},
                    "actual": None if error else _result_values(result, requested), "engine_errors": error,
                    "plan": record["plan"], "hts10": record["row"]["hts10"],
                    "country": record["row"]["country"], "iso2": record["row"]["iso2"],
                    "revision": record["row"]["revision"],
                    "interval": [record["row"]["clipped_from"], record["row"]["clipped_until"]],
                    "origin_regime": record["row"]["origin_regime"],
                    "flags": flags, "hts_line": record["route"]["hts_line"],
                }
                zipped.write((json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode())
    temporary.replace(path)
    return {"chapter": chapter, "key": key, "sha256": _sha256(path), "path": str(path),
            "cases": sum(map(len, cases.values())), "engine_errors": errors,
            "elapsed_seconds": round(time.perf_counter() - started, 3)}


def evaluate_campaign(*, rulespec_root: Path, engine_binary: Path, workers: int,
                      chapters: Iterable[str] | None = None, resume: bool = False,
                      cache_dir: Path | None = None) -> dict[str, Any]:
    _require(1 <= workers <= 3, "workers must be between 1 and 3")
    declared_chapters = [item["chapter"] for item in json.loads(INPUT_CONTRACT_RECEIPT.read_text())["chapters"]]
    chosen = sorted(set(chapters or declared_chapters))
    _require(set(chosen) <= set(declared_chapters), f"unknown chapters: {sorted(set(chosen) - set(declared_chapters))}")
    cache = cache_dir or CACHE_ROOT / "eval"
    manifest = _load_manifest()
    pending = []
    for chapter in chosen:
        key = _shard_key(chapter=chapter, rulespec_root=rulespec_root, engine_binary=engine_binary)
        old = manifest["shards"].get(key)
        complete = old and Path(old["path"]).is_file() and _sha256(Path(old["path"])) == old["sha256"]
        if resume and complete:
            print(f"{chapter}: resume skip cases={old['cases']} errors={old['engine_errors']}", flush=True)
        else:
            pending.append(chapter)
    campaign_started = time.perf_counter()
    finished = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_evaluate_chapter, chapter, rulespec_root=rulespec_root,
                               engine_binary=engine_binary, cache_dir=cache): chapter for chapter in pending}
        for future in concurrent.futures.as_completed(futures):
            receipt = future.result()
            manifest["shards"][receipt["key"]] = receipt
            _atomic_json(EVAL_MANIFEST, manifest)
            finished += 1
            elapsed = time.perf_counter() - campaign_started
            eta = elapsed / finished * (len(pending) - finished) if finished else 0
            print(f"{receipt['chapter']}: cases={receipt['cases']} errors={receipt['engine_errors']} "
                  f"elapsed={receipt['elapsed_seconds']:.1f}s ETA={eta:.0f}s", flush=True)
    return manifest


def _iter_eval_records(manifest: dict[str, Any]) -> Iterator[dict[str, Any]]:
    seen_chapters = set()
    for shard in sorted(manifest["shards"].values(), key=lambda item: item["chapter"]):
        path = Path(shard["path"])
        _require(path.is_file() and _sha256(path) == shard["sha256"], f"invalid shard {shard['key']}")
        _require(shard["chapter"] not in seen_chapters, f"duplicate chapter shard {shard['chapter']}")
        seen_chapters.add(shard["chapter"])
        with gzip.open(path, "rt") as source:
            for line in source:
                yield json.loads(line)


def _expected_slots(expected: dict[str, str]) -> dict[str, float]:
    values = {name: float(value) for name, value in expected.items()}
    return {slot: sum(values[name] for name in columns) for slot, columns in EXPECTED_SLOT_COLUMNS.items()}


def compare_record(record: dict[str, Any], tolerance: float = TOLERANCE) -> list[dict[str, Any]]:
    if record["engine_errors"]:
        return [{"case_id": record["case_id"], "slot": "engine_error", "match": False,
                 "error": record["engine_errors"], "delta": None}]
    expected = _expected_slots(record["expected"])
    comparable = list(record["plan"]["components"])
    if record["plan"]["base"] == "compare":
        comparable += ["base"]
    actual = {slot: sum(record["actual"][name] for name in SLOT_OUTPUTS[slot]) for slot in comparable}
    rows = []
    for slot in comparable:
        delta = actual[slot] - expected[slot]
        rows.append({"case_id": record["case_id"], "slot": slot,
                     "expected": expected[slot], "actual": actual[slot],
                     "delta": delta, "match": abs(delta) <= tolerance})
    yale_total = sum(float(record["expected"][name]) for name in EXPECTED_COLUMNS)
    axiom_total = sum(actual.values())
    if record["plan"]["total"] == "compare":
        total_delta = axiom_total - yale_total
        rows.append({"case_id": record["case_id"], "slot": "total", "expected": yale_total,
                     "actual": axiom_total, "delta": total_delta, "match": abs(total_delta) <= tolerance})
        stack_delta = record["actual"]["schedule_statutory_stack"] - axiom_total
        rows.append({"case_id": record["case_id"], "slot": "axiom_total_reconciliation",
                     "expected": axiom_total, "actual": record["actual"]["schedule_statutory_stack"],
                     "delta": stack_delta, "match": abs(stack_delta) <= tolerance})
        yale_rebuilt = sum(expected.values()) + float(record["expected"]["statutory_rate_301_cs"]) + float(record["expected"]["statutory_rate_other"])
        rows.append({"case_id": record["case_id"], "slot": "yale_total_reconciliation",
                     "expected": yale_total, "actual": yale_rebuilt, "delta": yale_rebuilt - yale_total,
                     "match": abs(yale_rebuilt - yale_total) <= tolerance})
    for row in rows:
        row["context"] = {key: record[key] for key in ("hts10", "hts_line", "iso2", "revision", "interval", "origin_regime", "flags")}
    return rows


def compare_campaign(*, cache_dir: Path | None = None) -> dict[str, Any]:
    manifest = _load_manifest()
    chapters = {shard["chapter"] for shard in manifest["shards"].values()}
    expected_chapters = {item["chapter"] for item in json.loads(INPUT_CONTRACT_RECEIPT.read_text())["chapters"]}
    _require(chapters == expected_chapters, "evaluation manifest is incomplete")
    counts: dict[str, Counter[str]] = {}
    digest = hashlib.sha256(_render(manifest).encode()).hexdigest()
    output = (cache_dir or CACHE_ROOT / "compare") / digest[:2] / f"{digest}.jsonl.gz"
    output.parent.mkdir(parents=True, exist_ok=True)
    engine_errors = 0
    with tempfile.NamedTemporaryFile("wb", dir=output.parent, delete=False) as raw:
        temporary = Path(raw.name)
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            for record in _iter_eval_records(manifest):
                for comparison in compare_record(record):
                    slot = comparison["slot"]
                    counts.setdefault(slot, Counter())["match" if comparison["match"] else "mismatch"] += 1
                    engine_errors += slot == "engine_error"
                    zipped.write((json.dumps(comparison, sort_keys=True, separators=(",", ":")) + "\n").encode())
    temporary.replace(output)
    receipt = {"schema": "axiom_oracles.us_tariff_schedule.comparison_summary.v1",
               "tolerance": TOLERANCE, "comparison_artifact": {"path": str(output), "sha256": _sha256(output)},
               "per_slot": {slot: dict(counter) for slot, counter in sorted(counts.items())},
               "engine_errors": engine_errors}
    _atomic_json(COMPARISON_RECEIPT, receipt)
    return receipt


def mismatch_signature(row: dict[str, Any]) -> str:
    context = row["context"]
    signature = {
        "authority_slot": row["slot"], "delta": row["delta"],
        "flag_vector": context["flags"], "revision_interval_regime": [context["revision"], *context["interval"]],
        "origin_regime": context["origin_regime"],
        "line_incidence_signature": [context["hts_line"], sorted(name for name, value in context["flags"].items() if value)],
    }
    return hashlib.sha256(_render(signature).encode()).hexdigest()


def _routing_dispositions() -> dict[str, tuple[str, str]]:
    with gzip.open(ROUTING_ROWS, "rt", newline="") as source:
        return {
            row["hts10"]: (row["general_disposition"], row["column2_disposition"])
            for row in csv.DictReader(source)
        }


def mismatch_unit(row: dict[str, Any], routes: dict[str, tuple[str, str]]) -> dict[str, Any]:
    context = row["context"]
    general, column2 = routes[context["hts10"]]
    return {
        "slot": row["slot"],
        "origin_regime": context["origin_regime"],
        "revision": context["revision"],
        "delta": row["delta"],
        "disposition": column2 if context["iso2"] in COLUMN2_ORIGINS else general,
        "hts10": context["hts10"],
        "hts_line": context["hts_line"],
        "flags": context["flags"],
        "interval": context["interval"],
        "iso2": context["iso2"],
    }


def _match_scalar_or_list(value: Any, selector: Any, field: str) -> bool:
    if selector == "any":
        return True
    _require(isinstance(selector, list) and selector, f"selector {field} must be any or a nonempty list")
    _require(all(isinstance(item, str) and item for item in selector), f"selector {field} has invalid values")
    return value in selector


def _match_line_class(unit: dict[str, Any], selector: Any) -> bool:
    if isinstance(selector, str):
        _require(selector in {"yale_member_only", "yale_rate_line"},
                 f"unknown line_class {selector}")
        return (unit["hts10"] != unit["hts_line"]) == (selector == "yale_member_only")
    _require(isinstance(selector, dict) and selector, "line_class must be a named class or nonempty mapping")
    allowed = {"membership", "hts_prefix", "hts10", "flags"}
    _require(set(selector) <= allowed, f"unknown line_class fields: {sorted(set(selector) - allowed)}")
    if "membership" in selector:
        _require(selector["membership"] in {"member_only", "rate_line"}, "invalid line_class membership")
        if (unit["hts10"] != unit["hts_line"]) != (selector["membership"] == "member_only"):
            return False
    for field in ("hts_prefix", "hts10"):
        if field not in selector:
            continue
        values = selector[field]
        _require(isinstance(values, list) and values and all(isinstance(v, str) and v for v in values),
                 f"line_class {field} must be a nonempty string list")
        if field == "hts_prefix" and not any(unit["hts10"].startswith(value) for value in values):
            return False
        if field == "hts10" and unit["hts10"] not in values:
            return False
    if "flags" in selector:
        flags = selector["flags"]
        _require(isinstance(flags, dict) and flags, "line_class flags must be a nonempty mapping")
        _require(all(name in unit["flags"] for name in flags), "line_class references unknown flag")
        _require(all(isinstance(value, bool) for value in flags.values()), "line_class flag values must be boolean")
        if any(unit["flags"][name] is not value for name, value in flags.items()):
            return False
    return True


def selector_matches(unit: dict[str, Any], match: dict[str, Any]) -> bool:
    _require(isinstance(match, dict) and match, "structured selector match must be a nonempty mapping")
    _require(set(match) <= SELECTOR_FIELDS,
             f"unknown selector fields: {sorted(set(match) - SELECTOR_FIELDS)}")
    _require(not all(selector == "any" for selector in match.values()),
             "universal disposition selector is forbidden")
    for field, selector in match.items():
        if field in {"slot", "origin_regime", "revision", "disposition", "iso2"}:
            if field == "slot":
                _require(isinstance(selector, str) and selector, "selector slot must be an exact string")
                if unit[field] != selector:
                    return False
            elif not _match_scalar_or_list(unit[field], selector, field):
                return False
        elif field == "delta":
            if selector == "any":
                continue
            _require(isinstance(selector, dict) and set(selector) <= {"sign", "min", "max"},
                     "selector delta must be any or a sign/min/max mapping")
            _require(selector and selector.get("sign") in {None, "pos", "neg"}, "invalid delta sign")
            if selector.get("sign") == "pos" and unit[field] <= 0:
                return False
            if selector.get("sign") == "neg" and unit[field] >= 0:
                return False
            if "min" in selector and unit[field] < selector["min"]:
                return False
            if "max" in selector and unit[field] > selector["max"]:
                return False
        elif field == "line_class" and not _match_line_class(unit, selector):
            return False
    return True


def validate_dispositions(entries: list[dict[str, Any]], observed: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    selectors: list[dict[str, Any]] = []
    claimed_signatures: set[str] = set()
    for entry in entries:
        _require(isinstance(entry.get("id"), str) and entry["id"], "disposition lacks id")
        signatures = entry.get("signatures", [])
        match = entry.get("match")
        _require(bool(signatures) != bool(match),
                 f"disposition {entry['id']} must have exactly one of signatures or match")
        evidence = entry.get("evidence", {})
        _require(evidence.get("instrument_receipt") and evidence.get("receipt_type"),
                 f"disposition {entry.get('id')} lacks instrument receipt fields")
        _require(entry.get("attribution") and entry.get("receipt") and entry.get("reason"),
                 f"disposition {entry.get('id')} lacks attribution/receipt/reason")
        for signature in signatures:
            _require(signature in observed, f"stale disposition signature {signature}")
            _require(signature not in claimed_signatures, f"overlapping disposition signature {signature}")
            claimed_signatures.add(signature)
        if match:
            # Schema validation is independent of whether this particular census
            # happens to contain a matching row.
            selector_matches(next(iter(observed.values()), {
                "slot": "base", "origin_regime": "x", "revision": "x", "delta": 1.0,
                "disposition": "free", "hts10": "0000000000", "hts_line": "0000000000",
                "flags": {}, "interval": ["", ""], "iso2": "US",
            }), match)
        selectors.append(entry)
    return selectors


def matching_class_id(signature: str, unit: dict[str, Any], selectors: list[dict[str, Any]]) -> str | None:
    matches = [
        entry["id"] for entry in selectors
        if signature in entry.get("signatures", [])
        or (entry.get("match") and selector_matches(unit, entry["match"]))
    ]
    _require(len(matches) <= 1,
             f"classification conservation failure: overlapping selectors {matches} for {signature}")
    return matches[0] if matches else None


def classify_campaign(*, disposition_ledger: Path = DISPOSITION_LEDGER,
                      entries_override: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    comparison = json.loads(COMPARISON_RECEIPT.read_text())
    artifact = Path(comparison["comparison_artifact"]["path"])
    _require(_sha256(artifact) == comparison["comparison_artifact"]["sha256"], "comparison artifact hash mismatch")
    observed: dict[str, dict[str, Any]] = {}
    counts: Counter[str] = Counter()
    total_signature_compositions: Counter[tuple[str, ...]] = Counter()
    routes = _routing_dispositions()
    engine_errors = 0
    active_case: str | None = None
    active_signatures: list[str] = []
    with gzip.open(artifact, "rt") as source:
        for line in source:
            row = json.loads(line)
            case_id = row.get("case_id")
            if case_id != active_case:
                # Components-only non-ad-valorem cases intentionally have no
                # comparable total row; their component classes do not derive
                # a total classification unit.
                active_signatures = []
                active_case = case_id
            if row["slot"] == "total":
                if not row["match"]:
                    _require(active_signatures,
                             "total mismatch lacks a mismatching component composition")
                    total_signature_compositions[tuple(sorted(active_signatures))] += 1
                active_signatures = []
                continue
            if row["match"]:
                continue
            if row["slot"] == "engine_error":
                engine_errors += 1
                continue
            signature = mismatch_signature(row)
            counts[signature] += 1
            observed.setdefault(signature, mismatch_unit(row, routes))
            active_signatures.append(signature)
    ledger = yaml.safe_load(disposition_ledger.read_text())
    _require(ledger.get("suite") == "us-tariff-schedule", "wrong disposition suite")
    entries = ledger.get("entries", []) if entries_override is None else entries_override
    selectors = validate_dispositions(entries, observed)
    census: Counter[str] = Counter()
    derived_total_compositions: Counter[str] = Counter()
    per_slot: dict[str, Counter[str]] = {}
    sample_signatures: dict[str, list[str]] = {}
    unexplained = engine_errors
    derived_total_units = 0
    for signature_composition, units in total_signature_compositions.items():
        component_classes = {
            matching_class_id(signature, observed[signature], selectors)
            for signature in signature_composition
        }
        if None in component_classes:
            unexplained += units
            continue
        class_composition = tuple(sorted(component_classes))
        derived_total_units += units
        derived_total_compositions[" + ".join(class_composition)] += units
    selector_digest = _sha256(disposition_ledger) if entries_override is None else hashlib.sha256(_render(entries).encode()).hexdigest()
    digest = hashlib.sha256((comparison["comparison_artifact"]["sha256"] + selector_digest).encode()).hexdigest()
    sidecar = CACHE_ROOT / "classify" / digest[:2] / f"{digest}.jsonl.gz"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=sidecar.parent, delete=False) as raw:
        temporary = Path(raw.name)
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
          for signature, unit in observed.items():
            count = counts[signature]
            class_id = matching_class_id(signature, unit, selectors)
            bucket = class_id or "__unexplained__"
            per_slot.setdefault(bucket, Counter())[unit["slot"]] += count
            sample_signatures.setdefault(bucket, [])
            if len(sample_signatures[bucket]) < 5:
                sample_signatures[bucket].append(signature)
            zipped.write((json.dumps({"signature": signature, "units": count, "class": class_id,
                                      "fields": unit}, sort_keys=True, separators=(",", ":")) + "\n").encode())
            if class_id is None:
                unexplained += count
            else:
                census[class_id] += count
    temporary.replace(sidecar)
    mismatch_total = sum(counts.values()) + sum(total_signature_compositions.values()) + engine_errors
    _require(mismatch_total == sum(census.values()) + derived_total_units + unexplained,
             "classification conservation failure")
    receipt = {"schema": "axiom_oracles.us_tariff_schedule.classification.v1",
               "mismatches": mismatch_total,
               "classified": sum(census.values()) + derived_total_units, "unexplained": unexplained,
               "engine_errors": engine_errors, "class_census": dict(sorted(census.items())),
               "derived_total_units": derived_total_units,
               "derived_total_compositions": dict(sorted(derived_total_compositions.items())),
               "observed_signature_count": len(observed),
               "selector_count": len(selectors),
               "groups": {name: {"units": sum(per_slot[name].values()),
                                  "per_slot": dict(sorted(per_slot[name].items())),
                                  "sample_signatures": sample_signatures[name]}
                          for name in sorted(per_slot)},
               "sidecar": {"path": str(sidecar), "sha256": _sha256(sidecar)},
               "conservation": "PASS"}
    _atomic_json(CLASSIFICATION_RECEIPT, receipt)
    return receipt


def enforce_excluded_exposure(exposure: dict[str, Any]) -> None:
    for column in ("statutory_rate_301_cs", "statutory_rate_other"):
        value = exposure.get(column)
        _require(isinstance(value, (int, float)) and value == value and value == 0,
                 f"X1 excluded-column exposure is nonzero or missing: {column}={value!r}")


def computed_conformant(*, unexplained: int, engine_errors: int) -> bool:
    return unexplained == 0 and engine_errors == 0


def build_report() -> dict[str, Any]:
    comparison = json.loads(COMPARISON_RECEIPT.read_text())
    classification = json.loads(CLASSIFICATION_RECEIPT.read_text())
    quotient = json.loads((OUT_DIR / "quotient-receipt.json").read_text())
    routing = json.loads(ROUTING_RECEIPT.read_text())
    exposure = json.loads((OUT_DIR / "full-exposure.json").read_text())
    enforce_excluded_exposure(exposure)
    per_slot = comparison["per_slot"]
    matches = sum(item.get("match", 0) for item in per_slot.values())
    mismatches = sum(item.get("mismatch", 0) for item in per_slot.values())
    unexplained = classification["unexplained"]
    conformant = computed_conformant(unexplained=unexplained, engine_errors=comparison["engine_errors"])
    scope_sentence = routing["scope_statement"] + f" ({routing['non_ad_valorem_share'] * 100:.4f}%; components-only)."
    report = {
        "schema": "axiom.comparison_report.v2", "suite": "us-tariff-schedule",
        "title": "US tariff full schedule — Axiom bulk path vs Yale statutory panel",
        "conformant": conformant,
        "summary": {"total": matches + mismatches, "matches": matches, "mismatches": mismatches,
                    "explained": classification["classified"], "unexplained": unexplained,
                    "engine_errors": comparison["engine_errors"]},
        "output_summary": per_slot, "column_exposure": exposure,
        "scope": {
            "full_universe_interval_cells": quotient["full_interval_cells"],
            "evaluated_quotient_interval_cells": quotient["evaluated_interval_cells"],
            "trajectory_quotient_label": "lossless partition of the EXPECTED side",
            "components_only_interval_cells": routing["non_ad_valorem_components_only_cells"],
            "components_only_share": routing["non_ad_valorem_share"],
            "components_only_statement": scope_sentence,
            "limitation": "Does not prove identical Axiom behavior for unprobed countries grouped by Yale trajectory.",
        },
        "classification": classification,
        "scoreboard": {"gate": "S1", "conformant": conformant,
                       "derivation": "unexplained == 0 and engine_errors == 0"},
    }
    _atomic_json(REPORT_PATH, report)
    return report


def _witness_surface(summary: dict[str, Any]) -> dict[str, Any]:
    # The replay-invariant raw comparison surface. The regenerated detail
    # legitimately differs in run date and truncated example ordering, so
    # W1 compares this surface, not file bytes.
    concept = {row["value"]: row["count"]
               for row in summary.get("mismatches_by_concept", [])}
    return {"comparison_count": summary.get("comparison_count"),
            "match_count": summary.get("match_count"),
            "mismatch_count": summary.get("mismatch_count"),
            "error_count": summary.get("error_count"),
            "internal_component_sum_inconsistencies":
                summary.get("internal_component_sum_inconsistencies"),
            "mismatches_by_concept": concept}


def witness_replay(*, execute: bool = False) -> dict[str, Any]:
    dashboard = REPO_ROOT / "dashboard/public/data/axiom-yale-us-tariff-panel.json"
    _require(dashboard.is_file(), "missing committed us-tariff-panel detail")
    before = dashboard.read_bytes()
    payload = json.loads(before)
    summary = payload.get("summary", {})
    dispositioned = summary.get("dispositioned", {})
    verdict = summary.get("error_count") == 0 and dispositioned.get("unexplained_count") == 0
    _require(verdict, "us-tariff-panel witness is not conformant")
    fresh_surface = None
    if execute:
        try:
            subprocess.run([sys.executable, str(REPO_ROOT / "scripts/run_comparison.py"),
                            "us-tariff-panel"], check=True)
            fresh = json.loads(dashboard.read_bytes())
            fresh_surface = _witness_surface(fresh.get("summary", {}))
            _require(fresh_surface == _witness_surface(summary),
                     "us-tariff-panel raw comparison surface changed during replay")
        finally:
            dashboard.write_bytes(before)
    _require(dashboard.read_bytes() == before, "us-tariff-panel detail bytes not restored")
    return {"schema": "axiom_oracles.us_tariff_schedule.witness_replay.v1",
            "conformant": True, "detail_sha256": hashlib.sha256(before).hexdigest(),
            "byte_stable": True,
            "surface_reproduced": fresh_surface is not None,
            "surface": _witness_surface(summary)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("prepass", "input-contract", "projection", "evaluate",
                                         "compare", "classify", "report", "witness-replay"))
    parser.add_argument("--rulespec-root", type=Path,
                        default=Path("/Users/maxghenis/TheAxiomFoundation/_b1wt/rulespec-us-b16"))
    parser.add_argument("--engine-binary", type=Path,
                        default=Path("/Users/maxghenis/TheAxiomFoundation/axiom-rules-engine-pinned/target/release/axiom-rules-engine"))
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--chapters", help="comma-separated chapters, for example CH01,CH72")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    started = time.perf_counter()
    if args.stage == "projection":
        receipt = evaluate_projection(
            rulespec_root=args.rulespec_root.resolve(),
            engine_binary=args.engine_binary.resolve(),
        )
        print(_render(receipt), end="")
        return 0 if receipt["verdict"] == "PASS" else 2
    if args.stage == "evaluate":
        chapters = None if not args.chapters else [item.strip().upper().removeprefix("CH") for item in args.chapters.split(",")]
        receipt = evaluate_campaign(rulespec_root=args.rulespec_root.resolve(),
                                    engine_binary=args.engine_binary.resolve(), workers=args.workers,
                                    chapters=chapters, resume=args.resume)
        print(_render(receipt), end="")
        return 0
    if args.stage == "compare":
        print(_render(compare_campaign()), end="")
        return 0
    if args.stage == "classify":
        print(_render(classify_campaign()), end="")
        return 0
    if args.stage == "report":
        print(_render(build_report()), end="")
        return 0
    if args.stage == "witness-replay":
        print(_render(witness_replay(execute=True)), end="")
        return 0
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
