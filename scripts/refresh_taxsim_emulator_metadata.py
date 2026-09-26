#!/usr/bin/env python3
"""Refresh input facts and row binary identity on verified recorded reports.

This metadata-only operation performs no tax calculations and does not reload
the paired release outputs. It preserves all amounts, auxiliary outputs,
aggregates, counts, and original run provenance. Use the full comparison
runner when changing outputs or comparison settings. After changing metadata,
rebind and apply dispositions with the ordinary ledger tools.

Usage: uv run scripts/refresh_taxsim_emulator_metadata.py --taxsim-csv PATH
       [--release-dir PATH] [--year 2021 ...] [--check]
"""

from __future__ import annotations

import argparse
from collections import Counter
import gc
import hashlib
import json
from pathlib import Path
import sys

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.adapters.taxsim import pins  # noqa: E402
from axiom_oracles.comparison.report_io import load_report, write_report  # noqa: E402
from axiom_oracles.populations.taxsim_csv import read_taxsim_csv  # noqa: E402

YEARS = tuple(range(2021, 2026))
SCOPE = {"type": "country", "geoid": "US"}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def refresh_metadata(
    report: dict, config: dict, taxsim_csv: Path, *, release_dir: Path | None = None,
) -> bool:
    """Validate all provenance, then replace only the allowed metadata in place.

    Returns whether any metadata changed. All checks precede mutation; callers
    may use this in memory for ``--check`` without writing the report.
    """
    params = config["runner"]["parameters"]
    year = int(params["period"])
    suite = f"taxsim-emulator-ecps-{year}"
    _require(year in YEARS and config["name"] == suite and report["suite"] == suite,
             "unsupported suite or period")
    _require(config["runner"]["type"] == "axiom-oracles-compare"
             and params["population"] == report["population"] == "taxsim-csv"
             and params["left"] == report["engines"]["left"] == "policyengine"
             and params["right"] == report["engines"]["right"] == "taxsim",
             "suite/report engine or population mismatch")
    _require(params["sample_size"] == 0 and params["report_include_cases"] is False
             and report.get("case_rows_omitted") is True and "cases" not in report
             and report["scope"] == SCOPE,
             "metadata refresh requires a full national recorded report without case rows")
    _require(params["tolerance"] == 15 and params["relative_tolerance"] == 0,
             "comparison settings changed; use full replay")
    expected_concepts = set(params["concepts"])
    _require({item["id"] for item in report["concepts"]} == expected_concepts
             and all(item["tolerance"] == 15 and item["relative_tolerance"] == 0
                     for item in report["concepts"]),
             "report comparison settings differ from suite")

    source = params["taxsim_csv"]
    dataset = report["dataset_identity"]
    provenance = report["provenance"]
    _require(dataset == provenance["dataset"], "dataset provenance copies differ")
    population = read_taxsim_csv(
        taxsim_csv, period=year, expected_sha256=source["sha256"],
        origin=source.get("origin"),
        allow_unknown_columns=source.get("allow_unknown_columns", False),
    )
    # Path/filename describe the original run and may differ for identical bytes.
    for key, value in population.identity.items():
        if key not in {"path", "filename"}:
            _require(dataset.get(key) == value, f"source identity mismatch: {key}")
    selection = population.select(
        scope=SCOPE, sample_size=0,
        selector_fact_columns=source.get("selector_fact_columns", ()),
    )
    old_selection = dataset["selection"]
    for key, value in selection.summary.items():
        if key != "selector_fact_columns":
            _require(old_selection.get(key) == value, f"population selection changed: {key}")
    cases = {case.case_id: case for case in selection.cases}
    _require(report["case_count"] == len(cases) == dataset["rows"],
             "report does not cover the complete source population")
    summary = report["summary"]
    _require(summary["comparison_count"] == len(cases) * len(expected_concepts)
             and summary["comparison_count"] == summary["match_count"] + summary["mismatch_count"]
             and summary["mismatch_count"] == len(report["mismatches"]),
             "report comparison/mismatch count mismatch")

    recorded = report["recorded_release"]
    release = params["recorded_release"]
    oracle = provenance["oracle"]
    _require(recorded == oracle["recorded_release"], "recorded-release provenance copies differ")
    expected_output_sha = release["sha256_by_year"][str(year)]
    _require(recorded["repo"] == release["repo"] and recorded["tag"] == release["tag"]
             and recorded["sha256"] == expected_output_sha
             and recorded["file"] == f"comparison_results_{year}.csv"
             and recorded["provenance_file"] == f"provenance_{year}.json",
             "recorded release differs from suite pin")
    release_provenance = recorded["provenance"]
    _require(release_provenance["year"] == year
             and release_provenance["records"] == len(cases)
             and release_provenance["outputSha256"] == expected_output_sha
             and release_provenance["sourceSha256"] == source["sha256"],
             "recorded release output/source provenance mismatch")
    if release_dir is not None:
        _require(_file_sha256(release_dir / recorded["file"]) == expected_output_sha,
                 "raw release CSV sha256 mismatch")
        provenance_path = release_dir / recorded["provenance_file"]
        _require(_file_sha256(provenance_path) == recorded["provenance_sha256"],
                 "raw release provenance sha256 mismatch")
        _require(json.loads(provenance_path.read_text()) == release_provenance,
                 "raw release provenance contents differ")

    profile = params["taxsim_pin_profile"]
    taxsim_identity = report["engine_identity"]["taxsim"]
    _require(taxsim_identity["pin_profile"] == oracle["taxsim_pin_profile"] == profile,
             "TAXSIM profile mismatch")
    binaries = taxsim_identity["binaries"]
    _require(binaries == oracle["taxsim_binaries"]
             and all(item["platform"] == "linux" for item in binaries),
             "TAXSIM binary provenance mismatch")
    resolved = {
        state: pins.resolve_binary(int(state), year, "linux", profile)
        for state in dataset["state_counts"]
    }
    expected_usage = Counter()
    for state, count in dataset["state_counts"].items():
        expected_usage[resolved[state]] += count
    _require({item["sha256"]: item["rows"] for item in binaries} == dict(expected_usage),
             "TAXSIM binary usage differs from pinned population")

    updates = []
    seen = set()
    for row in report["mismatches"]:
        key = (row["case_id"], row["concept"])
        _require(key not in seen, f"duplicate mismatch row: {key}")
        seen.add(key)
        _require(row["case_id"] in cases, f"missing source case: {row['case_id']}")
        _require(row["concept"] in expected_concepts and row["kind"] == "amount_difference",
                 "unexpected mismatch concept or kind; use full replay")
        facts = dict(cases[row["case_id"]].metadata["selector_facts"])
        previous = row["facts"]
        _require(all(previous.get(key) == facts[key] for key in ("state", "taxsim_state", "year")),
                 f"row state/year facts mismatch: {row['case_id']}")
        _require(all(key in facts and facts[key] == value for key, value in previous.items()),
                 f"existing row facts differ from source: {row['case_id']}")
        sha = resolved[str(facts["taxsim_state"])]
        _require("taxsim_binary_sha256" not in row or row["taxsim_binary_sha256"] == sha,
                 f"existing row TAXSIM sha256 mismatch: {row['case_id']}")
        updates.append((row, facts, sha))

    changed = old_selection != selection.summary
    for row, facts, sha in updates:
        changed |= row["facts"] != facts or row.get("taxsim_binary_sha256") != sha
        row["facts"] = facts
        row["taxsim_binary_sha256"] = sha
    dataset["selection"] = dict(selection.summary)
    provenance["dataset"]["selection"] = dict(selection.summary)
    return changed


def _refresh_report_file(
    report_path: Path, config: dict, source: Path, *, release_dir: Path | None, check: bool,
) -> bool:
    # These JSON/CSV-derived graphs are acyclic. As in CLI compare, avoid
    # repeatedly scanning the accumulated report while building its cases.
    # Reference counting still releases objects, including between years.
    gc_was_enabled = gc.isenabled()
    if gc_was_enabled:
        gc.disable()
    try:
        report = load_report(report_path)
        changed = refresh_metadata(report, config, source, release_dir=release_dir)
        if changed and not check:
            write_report(report_path, report)
        return changed
    finally:
        if gc_was_enabled:
            gc.enable()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--taxsim-csv", type=Path, required=True)
    parser.add_argument("--release-dir", type=Path)
    parser.add_argument("--year", action="append", type=int, choices=YEARS)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    stale = False
    for year in sorted(set(args.year or YEARS)):
        suite = f"taxsim-emulator-ecps-{year}"
        try:
            config = yaml.safe_load((REPO_ROOT / "comparisons" / f"{suite}.yaml").read_text())
            report_path = REPO_ROOT / "reports" / "taxsim-emulator" / f"{suite}.json.gz"
            _require(config["artifacts"]["report_path"] == str(report_path.relative_to(REPO_ROOT)),
                     "suite report path changed")
            changed = _refresh_report_file(
                report_path, config, args.taxsim_csv, release_dir=args.release_dir, check=args.check,
            )
            print(f"{suite}: {'metadata differs' if args.check and changed else 'metadata refreshed' if changed else 'metadata current'}")
            stale |= changed
        except (KeyError, TypeError, ValueError, OSError) as exc:
            print(f"{suite}: {exc}", file=sys.stderr)
            return 1
    return int(args.check and stale)


if __name__ == "__main__":
    raise SystemExit(main())
