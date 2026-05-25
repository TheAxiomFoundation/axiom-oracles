#!/usr/bin/env python3
"""Run an oracle comparison declared in comparisons/<name>.yaml.

The registry decouples "which comparisons exist" (YAML) from "how to run
them" (runner functions below). Adding a new comparison is a YAML edit;
adding a new runner type is a function here plus a README update.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write(
        "PyYAML is required. Install with `uv pip install pyyaml` or "
        "run from the repo's .venv.\n"
    )
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPARISONS_DIR = REPO_ROOT / "comparisons"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports"
DASHBOARD_DATA_DIR = REPO_ROOT / "dashboard" / "public" / "data"

# ---------------------------------------------------------------------------
# tax-ecps-compare → v2 dashboard schema adapter
# ---------------------------------------------------------------------------
#
# The axiom-encode `tax-ecps-compare` harness emits a flat shape
# (`output_summary` + `mismatches` by entity_id) that the dashboard
# (`axiom.comparison_report.v2`) doesn't speak natively. The mapping below
# pins each FIIT surface to a concept id the dashboard already understands.
#
# Surfaces without a real concept (payroll, capital-gain) are hung off the
# FIIT liability parent so data.js auto-allows them. Long-term, these belong
# in axiom_oracles/config/concept_mappings.yaml so sync_programs.py picks them
# up legitimately — tracked as a follow-up.
FIIT_SURFACE_CONCEPTS: dict[str, dict] = {
    "ctc": {
        "concept": "us:tax/federal-income-tax#ctc",
        "description": "Child Tax Credit value",
        "parent": "us:tax/federal-income-tax#liability",
        "category": "tax",
        "tolerance": 5,
    },
    "standard-deduction": {
        "concept": "us:tax/federal-income-tax#standard_deduction",
        "description": "Federal standard deduction",
        "parent": "us:tax/federal-income-tax#liability",
        "category": "tax",
        "tolerance": 5,
    },
    "eitc": {
        "concept": "us:tax/federal-income-tax#eitc",
        "description": "Earned Income Tax Credit",
        "parent": "us:tax/federal-income-tax#liability",
        "category": "tax",
        "tolerance": 5,
    },
    "capital-gain-definitions": {
        "concept": "us:tax/federal-income-tax#capital_gain",
        "description": "Capital gain definitions",
        "parent": "us:tax/federal-income-tax#liability",
        "category": "tax",
        "tolerance": 5,
    },
    "employee-oasdi": {
        "concept": "us:tax/payroll#employee_oasdi",
        "description": "Employee OASDI (Social Security)",
        "parent": "us:tax/federal-income-tax#liability",
        "category": "tax",
        "tolerance": 5,
    },
    "employer-oasdi": {
        "concept": "us:tax/payroll#employer_oasdi",
        "description": "Employer OASDI (Social Security)",
        "parent": "us:tax/federal-income-tax#liability",
        "category": "tax",
        "tolerance": 5,
    },
    "employee-medicare": {
        "concept": "us:tax/payroll#employee_medicare",
        "description": "Employee Medicare",
        "parent": "us:tax/federal-income-tax#liability",
        "category": "tax",
        "tolerance": 5,
    },
    "employer-medicare": {
        "concept": "us:tax/payroll#employer_medicare",
        "description": "Employer Medicare",
        "parent": "us:tax/federal-income-tax#liability",
        "category": "tax",
        "tolerance": 5,
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "name",
        nargs="?",
        help="Comparison name (comparisons/<name>.yaml)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for the JSON report (default: reports/)",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print headline numbers after the run",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available comparisons and exit",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Override the comparison's sample_size for this run only",
    )
    args = parser.parse_args()

    if args.list:
        for path in sorted(COMPARISONS_DIR.glob("*.yaml")):
            config = yaml.safe_load(path.read_text())
            print(f"{config['name']:24s}  {config.get('title','')}")
        return 0

    if not args.name:
        parser.error("name is required (or pass --list)")

    config = _load_comparison(args.name)
    if args.sample_size is not None:
        config["runner"]["parameters"]["sample_size"] = args.sample_size
    runner_type = config["runner"]["type"]
    runner_fn = RUNNERS.get(runner_type)
    if runner_fn is None:
        raise SystemExit(
            f"unknown runner type {runner_type!r}; "
            f"available: {sorted(RUNNERS)}"
        )

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    basename = config["artifacts"]["report_basename"]
    sample = config["runner"]["parameters"].get("sample_size", "all")
    output = args.output_dir / f"{basename}-{sample}-{today}.json"
    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Running {config['name']}: {config.get('title', config['name'])}")
    runner_fn(config["runner"], output)
    print(f"Wrote: {output}")

    dashboard_target = config.get("dashboard", {}).get("filename")
    if dashboard_target:
        suite = config.get("dashboard", {}).get("suite", config["name"])
        adapted = _adapt_to_v2(
            output, runner_type, config, suite=suite,
        )
        _write_dashboard_report(adapted, dashboard_target)

    if args.summary:
        _print_summary(output)

    return 0


# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------


def _run_axiom_encode_tax_ecps_compare(runner: dict, output: Path) -> None:
    """`axiom-encode tax-ecps-compare` via uv run with the pinned PE stack."""
    axiom_encode_repo = _resolve_path(runner["axiom_encode_repo"], "axiom_encode_repo")
    axiom_rules_repo = _resolve_path(runner["axiom_rules_repo"], "axiom_rules_repo")
    _ensure_engine_binary(axiom_rules_repo, kind="release")
    rulespec_root = _ensure_rulespec_us_checkout(runner["rulespec_remote"])
    params = runner["parameters"]
    pinned = params.get("pinned", True)
    pe_pins = (
        [
            "--with", "policyengine==4.11.0",
            "--with", "policyengine-us==1.705.16",
            "--with", "policyengine-core==3.26.11",
        ]
        if pinned
        else [
            "--with", "policyengine",
            "--with", "policyengine-us",
            "--with", "policyengine-core",
        ]
    )
    cmd = [
        "uv", "run", "--python", "3.13", "--no-project",
        "--with", str(axiom_encode_repo),
        *pe_pins,
        "axiom-encode", "tax-ecps-compare",
        "--rulespec-root", str(rulespec_root),
        "--axiom-rules-engine-path", str(axiom_rules_repo),
        "--sample-size", str(params.get("sample_size", 1000)),
        "--year", str(params.get("year", 2026)),
        "--surface", params.get("surface", "all"),
        "--json",
    ]
    try:
        with output.open("w") as f:
            subprocess.run(cmd, check=True, stdout=f)
    finally:
        shutil.rmtree(rulespec_root.parent, ignore_errors=True)


def _run_axiom_oracles_compare(runner: dict, output: Path) -> None:
    """`axiom_oracles.cli compare <left> <right>` (in-repo CLI)."""
    axiom_rules_repo = _resolve_path(runner["axiom_rules_repo"], "axiom_rules_repo")
    _ensure_engine_binary(axiom_rules_repo, kind="release")
    params = runner["parameters"]
    cmd = [
        sys.executable, "-m", "axiom_oracles.cli", "compare",
        params["left"], params["right"],
        "--population", params.get("population", "enhanced-cps"),
        "--sample-size", str(params.get("sample_size", 1000)),
        "--period", str(params["period"]),
        "--concept", params["concept"],
        "--axiom-engine-binary",
        str(axiom_rules_repo / "target" / "release" / "axiom-rules-engine"),
        "--output", str(output),
    ]
    subprocess.run(cmd, check=True, cwd=REPO_ROOT)


RUNNERS = {
    "axiom-encode-tax-ecps-compare": _run_axiom_encode_tax_ecps_compare,
    "axiom-oracles-compare": _run_axiom_oracles_compare,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_comparison(name: str) -> dict:
    path = COMPARISONS_DIR / f"{name}.yaml"
    if not path.exists():
        available = sorted(p.stem for p in COMPARISONS_DIR.glob("*.yaml"))
        raise SystemExit(
            f"unknown comparison {name!r}; available: {', '.join(available)}"
        )
    return yaml.safe_load(path.read_text())


def _resolve_path(raw: str, field: str) -> Path:
    expanded = Path(os.path.expandvars(os.path.expanduser(str(raw)))).resolve()
    if not expanded.exists():
        raise SystemExit(f"{field}: path does not exist: {expanded}")
    return expanded


def _ensure_engine_binary(repo: Path, *, kind: str) -> None:
    bin_path = repo / "target" / kind / "axiom-rules-engine"
    if bin_path.exists():
        return
    print(f"Building {kind} axiom-rules-engine in {repo}...")
    cmd = ["cargo", "build", "--bin", "axiom-rules-engine"]
    if kind == "release":
        cmd.append("--release")
    subprocess.run(cmd, check=True, cwd=repo)


def _ensure_rulespec_us_checkout(remote: str) -> Path:
    workspace = Path(tempfile.mkdtemp(prefix="oracle-compare."))
    target = workspace / "rulespec-us"
    print(f"Cloning rulespec-us into {target}...")
    subprocess.run(
        ["git", "clone", "--depth", "1", "--quiet", remote, str(target)],
        check=True,
    )
    return target


def _print_summary(output: Path) -> None:
    data = json.loads(output.read_text())
    print()
    if "compared_values" in data:
        cv = data["compared_values"]
        mc = data["mismatch_count"]
        pct = 100 * (cv - mc) / cv if cv else 0
        print(f"Compared values:   {cv}")
        print(f"Mismatches:        {mc}")
        print(f"Agreement:         {pct:.4f}%")
        from collections import defaultdict
        by_surface = defaultdict(lambda: [0, 0])
        for row in data.get("output_summary", []):
            by_surface[row["surface"]][0] += row["compared"]
            by_surface[row["surface"]][1] += row["mismatches"]
        print()
        for surf, (c, m) in sorted(by_surface.items(), key=lambda x: -x[1][1]):
            p = 100 * (c - m) / c if c else 0
            print(f"  {surf:30s}  {c-m}/{c} ({p:6.2f}%)  mismatches={m}")
    elif "case_count" in data:
        cc = data.get("case_count", 0)
        mm = sum(len(c.get("mismatches", []) or []) for c in data.get("cases", []))
        print(f"Cases:             {cc}")
        print(f"Mismatch entries:  {mm}")
        agg = data.get("aggregates") or []
        if agg:
            print()
            for a in agg[:8]:
                print(
                    f"  {a.get('concept','?'):40s}  "
                    f"compared={a.get('compared',0)}  "
                    f"matched={a.get('matched',0)}"
                )
    else:
        print("(unknown report shape — committed JSON for offline inspection)")


# ---------------------------------------------------------------------------
# Dashboard adapter
# ---------------------------------------------------------------------------


def _adapt_to_v2(raw_path: Path, runner_type: str, config: dict, *, suite: str) -> dict:
    raw = json.loads(raw_path.read_text())
    if runner_type == "axiom-encode-tax-ecps-compare":
        return _adapt_tax_ecps_to_v2(raw, config, suite=suite)
    # axiom-oracles-compare already emits v2 — pass through, just normalize suite.
    raw.setdefault("suite", suite)
    return raw


def _adapt_tax_ecps_to_v2(raw: dict, config: dict, *, suite: str) -> dict:
    """Convert tax-ecps-compare flat output to axiom.comparison_report.v2.

    Surfaces become aggregates; mismatching entities become cases (matching
    units are counted in summary/aggregates but don't appear in cases[]). The
    schema treats `comparison_weight` as the running denominator; we don't
    have ECPS household weights here, so we set weights = counts to keep
    the dashboard's weighted columns identical to unweighted.
    """
    from collections import defaultdict

    # Surface → list of output rows from output_summary
    by_surface: dict[str, list[dict]] = defaultdict(list)
    for row in raw.get("output_summary", []):
        by_surface[row["surface"]].append(row)

    # Surface → list of mismatch tuples grouped by tax-unit entity
    mismatches_by_entity: dict[str, list[dict]] = defaultdict(list)
    for m in raw.get("mismatches", []):
        mismatches_by_entity[m["entity_id"]].append(m)

    # Aggregates: one per surface, plus a synthetic FIIT-liability parent
    aggregates: list[dict] = []
    component_concepts: list[str] = []
    for surface, rows in by_surface.items():
        spec = FIIT_SURFACE_CONCEPTS.get(surface)
        if spec is None:
            continue
        compared = sum(r["compared"] for r in rows)
        mismatches = sum(r["mismatches"] for r in rows)
        matched = compared - mismatches
        match_rate = (matched / compared * 100) if compared else 100.0
        aggregates.append({
            "category": spec["category"],
            "comparison": "amount",
            "comparison_count": compared,
            "comparison_weight": compared,
            "components": [],
            "concept": spec["concept"],
            "description": spec["description"],
            "left_weighted_sum": 0,
            "match_rate": match_rate,
            "match_weight": matched,
            "mismatch_count": mismatches,
            "mismatch_weight": mismatches,
            "missing_both_count": 0,
            "missing_left_count": 0,
            "missing_right_count": 0,
            "parent": spec["parent"],
            "right_weighted_sum": 0,
            "weighted_difference": 0,
            "weighted_match_rate": match_rate,
        })
        component_concepts.append(spec["concept"])

    parent_compared = raw.get("compared_values", 0)
    parent_mismatches = raw.get("mismatch_count", 0)
    parent_matched = parent_compared - parent_mismatches
    parent_rate = (parent_matched / parent_compared * 100) if parent_compared else 100.0
    aggregates.insert(0, {
        "category": "tax",
        "comparison": "amount",
        "comparison_count": parent_compared,
        "comparison_weight": parent_compared,
        "components": component_concepts,
        "concept": "us:tax/federal-income-tax#liability",
        "description": "Federal income tax liability (ECPS, all surfaces)",
        "left_weighted_sum": 0,
        "match_rate": parent_rate,
        "match_weight": parent_matched,
        "mismatch_count": parent_mismatches,
        "mismatch_weight": parent_mismatches,
        "missing_both_count": 0,
        "missing_left_count": 0,
        "missing_right_count": 0,
        "parent": None,
        "right_weighted_sum": 0,
        "weighted_difference": 0,
        "weighted_match_rate": parent_rate,
    })

    # Concepts manifest mirrors aggregates so the dashboard's concept loader
    # picks them up. Components carry parent={parent_id} for auto-allow.
    concepts: list[dict] = [{
        "category": "tax",
        "comparison": "amount",
        "components": component_concepts,
        "description": "Federal income tax liability (ECPS, all surfaces)",
        "id": "us:tax/federal-income-tax#liability",
        "parent": None,
        "tolerance": 15,
    }]
    for surface, rows in by_surface.items():
        spec = FIIT_SURFACE_CONCEPTS.get(surface)
        if spec is None:
            continue
        concepts.append({
            "category": spec["category"],
            "comparison": "amount",
            "components": [],
            "description": spec["description"],
            "id": spec["concept"],
            "parent": spec["parent"],
            "tolerance": spec["tolerance"],
        })

    # Cases: one per mismatching entity. Matching entities are not enumerated
    # (the harness doesn't surface their ids); summary/aggregates capture them.
    surface_to_spec = {
        s: FIIT_SURFACE_CONCEPTS[s] for s in by_surface if s in FIIT_SURFACE_CONCEPTS
    }
    cases: list[dict] = []
    flat_mismatches: list[dict] = []
    for entity_id, ms in mismatches_by_entity.items():
        case_id = f"ecps-{entity_id}"
        case_mismatches = []
        for m in ms:
            spec = surface_to_spec.get(m["surface"])
            if spec is None:
                continue
            mm = {
                "case_id": case_id,
                "concept": spec["concept"],
                "description": f"{spec['description']} — output={m['output']}",
                "difference": m.get("diff", 0),
                "kind": "amount_difference",
                "left": m.get("axiom", 0),
                "parent": spec["parent"],
                "right": m.get("policyengine", 0),
                "tolerance": spec["tolerance"],
            }
            case_mismatches.append(mm)
            flat_mismatches.append(mm)
        if not case_mismatches:
            continue
        cases.append({
            "case_id": case_id,
            "left_engine": "axiom",
            "left_errors": [],
            "match_rate": 0.0,
            "metadata": {
                "case_unit": "tax_unit",
                "dataset": "enhanced_cps",
                "entity_id": entity_id,
                "population": "enhanced-cps",
                "suite": suite,
            },
            "mismatches": case_mismatches,
            "right_engine": "policyengine",
            "right_errors": [],
        })

    return {
        "aggregates": aggregates,
        "case_count": raw.get("compared_tax_units", 0),
        "cases": cases,
        "concepts": concepts,
        "engines": {"left": "axiom", "right": "policyengine"},
        "errors": [],
        "locales": [],
        "mismatches": flat_mismatches,
        "population": "enhanced-cps",
        "schema_version": "axiom.comparison_report.v2",
        "scope": {"geoid": "US", "type": "country"},
        "suite": suite,
        "summary": {
            "comparison_count": parent_compared,
            "error_count": 0,
            "errors_by_engine": {},
            "match_count": parent_matched,
            "mismatch_count": parent_mismatches,
            "mismatches_by_concept": {},
            "mismatches_by_kind": {"amount_difference": parent_mismatches},
            "mismatches_by_scenario": {},
            "weighted": {
                "comparison_weight": parent_compared,
                "match_rate": parent_rate,
                "match_weight": parent_matched,
                "mismatch_weight": parent_mismatches,
            },
        },
    }


def _write_dashboard_report(report: dict, filename: str) -> None:
    DASHBOARD_DATA_DIR.mkdir(parents=True, exist_ok=True)
    target = DASHBOARD_DATA_DIR / filename
    target.write_text(json.dumps(report, indent=2, sort_keys=True))
    print(f"Wrote dashboard report: {target}")

    manifest_path = DASHBOARD_DATA_DIR / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
    else:
        manifest = {"reports": []}
    reports = manifest.setdefault("reports", [])
    if filename not in reports:
        reports.append(filename)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"Added {filename} to manifest.json")


if __name__ == "__main__":
    sys.exit(main())
