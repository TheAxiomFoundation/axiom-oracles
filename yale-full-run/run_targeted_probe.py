#!/usr/bin/env python3
"""Bounded fresh tariff endpoint diagnostics, explicitly not campaign artifacts."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import heapq
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

from measure_shards import atomic_json, sha256, utc_now, measure, aggregate


def campaign_module(root, rulespec=None):
    if rulespec:
        os.environ["RULESPEC_US_CHECKOUT"] = str(rulespec.resolve())
    path = root.resolve() / "scripts/us_tariff_schedule_campaign.py"
    spec = importlib.util.spec_from_file_location("targeted_campaign", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def select(args):
    started = time.monotonic()
    started_utc = utc_now()
    campaign = campaign_module(args.oracles_root)
    routes = campaign._routing_by_member()
    selected_chapters = args.chapters.split(",")
    heaps = defaultdict(list)
    population = Counter()
    rows_scanned = 0
    for row in campaign._selected_rows(campaign.SELECTED):
        rows_scanned += 1
        if rows_scanned % 1000000 == 0:
            print(json.dumps({"stage": "selection", "rows_scanned": rows_scanned, "elapsed_seconds": round(time.monotonic() - started, 3)}), flush=True)
        route = routes[row["hts10"]]
        chapter = route["chapter_shard"]
        if chapter not in selected_chapters or (chapter == "94" and row["hts10"] != "9403999020"):
            continue
        origin = ("BR" if row["iso2"] == "BR" else "CA_MX" if row["iso2"] in {"CA", "MX"}
                  else "column2" if row["iso2"] in campaign.COLUMN2_ORIGINS else "other")
        positives = "BR" + str(int(float(row["statutory_rate_s301br"]) != 0)) + "_FL" + str(int(float(row["statutory_rate_s301fl"]) != 0))
        disposition = route["column2_disposition"] if row["iso2"] in campaign.COLUMN2_ORIGINS else route["general_disposition"]
        plan = campaign.query_plan(disposition, column2_rate_available=True)
        for ordinal, probe in enumerate(campaign._probe_dates(row)):
            if probe < "2026-07-22":
                continue
            phase = "July22_23" if probe < "2026-07-24" else "July24_or_later"
            stratum = "|".join((chapter, positives, origin, phase))
            population[stratum] += 1
            case_id = campaign._case_id(row, probe, ordinal)
            # Uniform deterministic bottom-k ranking over complete case identity;
            # this deliberately samples, and never extrapolates population counts.
            rank = int(hashlib.sha256(("bounded-yale-probe-v1|" + case_id).encode()).hexdigest(), 16)
            heap = heaps[stratum]
            if len(heap) >= args.per_stratum and rank >= -heap[0][0]:
                continue
            record = {"row": row, "route": route, "plan": plan, "probe": probe,
                      "ordinal": ordinal, "case_id": case_id, "stratum": stratum,
                      "selection_rank": format(rank, "064x")}
            item = (-rank, case_id, record)
            if len(heap) < args.per_stratum:
                heapq.heappush(heap, item)
            else:
                heapq.heapreplace(heap, item)
    chosen = {}
    for chapter in selected_chapters:
        strata = {key: sorted((item[2] for item in heap), key=lambda record: record["selection_rank"])
                  for key, heap in sorted(heaps.items()) if key.startswith(chapter + "|")}
        records = []
        for index in range(args.per_stratum):
            for records_in_stratum in strata.values():
                if index < len(records_in_stratum) and len(records) < args.max_cases:
                    records.append(records_in_stratum[index])
        chosen[chapter] = sorted(records, key=lambda record: record["case_id"])
    receipt = {
        "schema": "measurement.bounded_endpoint_selection.v1", "diagnostic_only": True,
        "representative_full_schedule_claim": False,
        "criteria": {"chapters": selected_chapters, "chapter94_exact_hts10": "9403999020",
                     "minimum_probe_date": "2026-07-22", "strata": "chapter; expected Brazil/nonzero; expected note52/nonzero; origin BR/CA_MX/column2/other; July22_23/July24_or_later",
                     "selection": "Lowest SHA256(bounded-yale-probe-v1|campaign case_id) ranks per stratum, then round robin by rank within sorted strata until chapter max",
                     "per_stratum": args.per_stratum, "maximum_per_chapter": args.max_cases},
        "argv": sys.argv, "cwd": str(Path.cwd()), "started_utc": started_utc, "finished_utc": utc_now(),
        "elapsed_seconds": round(time.monotonic() - started, 3), "rows_scanned": rows_scanned,
        "inputs": {"selected_sha256": sha256(campaign.SELECTED), "routing_sha256": sha256(campaign.ROUTING_ROWS),
                   "campaign_source_sha256": sha256(Path(campaign.__file__)), "diagnostic_source_sha256": sha256(__file__)},
        "eligible_endpoint_population_per_stratum": dict(sorted(population.items())),
        "sample_cases_per_chapter": {chapter: len(records) for chapter, records in chosen.items()},
        "sample_cases_per_stratum": dict(sorted(Counter(record["stratum"] for records in chosen.values() for record in records).items())),
        "chapters": chosen,
    }
    atomic_json(args.output, receipt)
    print(json.dumps({"selection_output": str(args.output), "sample_cases_per_chapter": receipt["sample_cases_per_chapter"], "elapsed_seconds": receipt["elapsed_seconds"]}), flush=True)


def evaluate(args):
    started = time.monotonic()
    campaign = campaign_module(args.oracles_root, args.rulespec_root)
    from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner
    from axiom_oracles.core.case import Case

    sys.path.insert(0, str(args.rulespec_root.resolve()))
    from tools.b16_entry_flags import entry_flags

    selection = json.loads(args.selection.read_text())
    if selection["inputs"]["selected_sha256"] != sha256(campaign.SELECTED) or selection["inputs"]["routing_sha256"] != sha256(campaign.ROUTING_ROWS):
        raise ValueError("selection source/routing drift; A/B comparability not established")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_dir / "diagnostic-MANIFEST.json"
    receipt = {
        "schema": "measurement.bounded_endpoint_eval_manifest.v1", "diagnostic_only": True,
        "official_campaign_evaluation": False, "engine_reuse": "none; every selected case evaluated freshly",
        "argv": sys.argv, "cwd": str(Path.cwd()), "started_utc": utc_now(), "status": "running",
        "selection_path": str(args.selection.resolve()), "selection_sha256": sha256(args.selection),
        "rulespec_root": str(args.rulespec_root.resolve()),
        "inputs": {"engine_sha256": sha256(args.engine_binary), "campaign_source_sha256": sha256(Path(campaign.__file__)),
                   "diagnostic_source_sha256": sha256(__file__), "entry_flags_sha256": sha256(args.rulespec_root / "tools/b16_entry_flags.py")},
        "shards": {}, "chapter_diagnostics": {},
    }
    atomic_json(manifest_path, receipt)
    routes = campaign._routing_dispositions()
    entries = campaign.yaml.safe_load(campaign.DISPOSITION_LEDGER.read_text())["entries"]
    selectors = campaign.validate_dispositions(entries, {})
    diagnostics = []
    try:
        for chapter in args.chapters.split(","):
            chapter_started = time.monotonic()
            records = selection["chapters"][chapter]
            module_ref = f"us:policies/cbp/us-tariff-schedule/generated/ch{chapter}/ch{chapter}"
            cases, contexts = {"full": [], "components": []}, {"full": [], "components": []}
            for record in records:
                feed, flags = campaign._case_feed(record["row"], record["route"], entry_flags)
                case_id = campaign._case_id(record["row"], record["probe"], record["ordinal"])
                if case_id != record["case_id"]:
                    raise ValueError("selection case identity drift")
                group = "full" if record["plan"]["base"] == "compare" else "components"
                requested = list(dict.fromkeys(name for slot in record["plan"]["components"] for name in campaign.SLOT_OUTPUTS[slot]))
                if group == "full":
                    requested += ["mfn_ad_valorem_rate", "schedule_statutory_stack"]
                outputs = tuple(f"{module_ref}#{name}" for name in requested)
                cases[group].append(Case(case_id=case_id, period=record["probe"], metadata={
                    "axiom_entity": "CustomsEntry", "axiom_entity_id": "entry",
                    "axiom_inputs": {f"{module_ref}#input.{name}": value for name, value in feed.items()}}, outputs=outputs))
                contexts[group].append((record, flags, case_id, requested))
            runner = AxiomRulesRunner(program_path=campaign._module_path(args.rulespec_root, chapter), binary_path=args.engine_binary,
                                     default_entity="CustomsEntry", default_entity_id="entry", rulespec_repo_roots=(args.rulespec_root,), batch_size=5000)
            payloads = []
            engine_started = time.monotonic()
            for group in ("full", "components"):
                if not cases[group]:
                    continue
                results = runner.run_cases(cases[group], list(cases[group][0].outputs))
                if len(results) != len(contexts[group]):
                    raise ValueError("missing engine results")
                for result, (record, flags, case_id, requested) in zip(results, contexts[group], strict=True):
                    errors = list(result.errors or [])
                    payloads.append({"schema": "measurement.bounded_endpoint_eval_record.v1", "case_id": case_id,
                        "chapter": chapter, "probe": record["probe"], "expected": {name: record["row"][name] for name in campaign.EXPECTED_COLUMNS},
                        "actual": None if errors else campaign._result_values(result, requested), "engine_errors": errors,
                        "plan": record["plan"], "hts10": record["row"]["hts10"], "country": record["row"]["country"],
                        "iso2": record["row"]["iso2"], "revision": record["row"]["revision"],
                        "interval": [record["row"]["clipped_from"], record["row"]["clipped_until"]],
                        "origin_regime": record["row"]["origin_regime"], "flags": flags, "hts_line": record["route"]["hts_line"],
                        "selection_stratum": record["stratum"]})
            engine_seconds = time.monotonic() - engine_started
            shard_path = args.output_dir / f"diagnostic-ch{chapter}.jsonl.gz"
            with shard_path.open("wb") as raw:
                with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
                    for payload in sorted(payloads, key=lambda payload: payload["case_id"]):
                        zipped.write((json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode())
            shard = {"chapter": chapter, "path": str(shard_path.resolve()), "sha256": sha256(shard_path), "cases": len(payloads),
                     "engine_errors": sum(bool(payload["engine_errors"]) for payload in payloads), "engine_seconds": engine_seconds,
                     "module_sha256": sha256(campaign._module_path(args.rulespec_root, chapter)),
                     "elapsed_seconds": round(time.monotonic() - chapter_started, 3), "diagnostic_only": True}
            receipt["shards"][chapter] = shard
            atomic_json(manifest_path, receipt)
            diagnostic = measure(campaign, shard, selectors, routes, 5)
            diagnostic_path = args.output_dir / f"diagnostic-ch{chapter}-census.json"
            atomic_json(diagnostic_path, diagnostic)
            diagnostics.append(diagnostic)
            receipt["chapter_diagnostics"][chapter] = {"path": str(diagnostic_path.resolve()), "sha256": sha256(diagnostic_path)}
            receipt["aggregate"] = aggregate(diagnostics)
            receipt["elapsed_seconds"] = round(time.monotonic() - started, 3)
            atomic_json(manifest_path, receipt)
            print(json.dumps({"chapter": chapter, "cases": len(payloads), "engine_seconds": engine_seconds,
                              "summary": diagnostic["summary"], "elapsed_seconds": receipt["elapsed_seconds"]}), flush=True)
        receipt["status"] = "complete"
    except BaseException as exc:
        receipt["status"] = "failed"
        receipt["error"] = {"type": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        receipt["finished_utc"] = utc_now()
        receipt["elapsed_seconds"] = round(time.monotonic() - started, 3)
        atomic_json(manifest_path, receipt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="stage", required=True)
    selection = sub.add_parser("select")
    selection.add_argument("--oracles-root", type=Path, required=True)
    selection.add_argument("--chapters", default="62,84,29,94")
    selection.add_argument("--per-stratum", type=int, default=64)
    selection.add_argument("--max-cases", type=int, default=800)
    selection.add_argument("--output", type=Path, required=True)
    evaluation = sub.add_parser("evaluate")
    evaluation.add_argument("--oracles-root", type=Path, required=True)
    evaluation.add_argument("--rulespec-root", type=Path, required=True)
    evaluation.add_argument("--engine-binary", type=Path, required=True)
    evaluation.add_argument("--selection", type=Path, required=True)
    evaluation.add_argument("--chapters", default="62,84,29,94")
    evaluation.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    select(args) if args.stage == "select" else evaluate(args)


if __name__ == "__main__":
    main()
