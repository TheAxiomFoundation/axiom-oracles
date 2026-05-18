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
    args = parser.parse_args()

    if args.list:
        for path in sorted(COMPARISONS_DIR.glob("*.yaml")):
            config = yaml.safe_load(path.read_text())
            print(f"{config['name']:24s}  {config.get('title','')}")
        return 0

    if not args.name:
        parser.error("name is required (or pass --list)")

    config = _load_comparison(args.name)
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
    _ensure_engine_binary(axiom_rules_repo, kind="debug")
    rulespec_root = _ensure_rulespec_us_checkout(runner["rulespec_remote"])
    params = runner["parameters"]
    pinned = params.get("pinned", True)
    pe_pins = (
        [
            "--with", "policyengine==4.4.4",
            "--with", "policyengine-us==1.691.3",
            "--with", "policyengine-core==3.26.0",
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


if __name__ == "__main__":
    sys.exit(main())
