#!/usr/bin/env python3
"""Run an oracle comparison declared in comparisons/<name>.yaml.

The registry decouples "which comparisons exist" (YAML) from "how to run
them" (runner functions below). Adding a new comparison is a YAML edit;
adding a new runner type is a function here plus a README update.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
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

# The outer script runs under the host python interpreter (not the uv
# subprocess that runs the actual comparison), so make sure the editable
# package layout is importable for in-process helpers like the coverage
# analyzer. Without this, `from axiom_oracles.coverage import ...`
# silently fails and the coverage warnings get dropped.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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
    "tax-before-credits": {
        "concept": "us:tax/federal-income-tax#tax_before_credits",
        "description": "Federal tax before credits",
        "parent": "us:tax/federal-income-tax#liability",
        "category": "tax",
        "tolerance": 5,
    },
    "nonrefundable-credits": {
        "concept": "us:tax/federal-income-tax#nonrefundable_credits",
        "description": "Federal capped nonrefundable credits",
        "parent": "us:tax/federal-income-tax#liability",
        "category": "tax",
        "tolerance": 5,
    },
    "cdcc": {
        "concept": "us:tax/federal-income-tax#cdcc",
        "description": "Child and Dependent Care Credit",
        "parent": "us:tax/federal-income-tax#liability",
        "category": "tax",
        "tolerance": 5,
    },
    "aotc": {
        "concept": "us:tax/federal-income-tax#aotc",
        "description": "American Opportunity Credit",
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
    parser.add_argument(
        "--sanity",
        action="store_true",
        help=(
            "Run the comparison's hand-built sanity fixtures "
            "(<name>.fixtures.yaml) instead of the population-scale "
            "comparison. Non-zero exit if any fixture fails."
        ),
    )
    args = parser.parse_args()

    if args.list:
        for path in sorted(COMPARISONS_DIR.glob("*.yaml")):
            if path.name.endswith(".fixtures.yaml"):
                continue
            config = yaml.safe_load(path.read_text())
            print(f"{config['name']:24s}  {config.get('title', '')}")
        return 0

    if not args.name:
        parser.error("name is required (or pass --list)")

    if args.sanity:
        return _run_sanity(args.name)

    config = _load_comparison(args.name)
    if args.sample_size is not None:
        config["runner"]["parameters"]["sample_size"] = args.sample_size
    runner_type = config["runner"]["type"]
    runner_fn = RUNNERS.get(runner_type)
    if runner_fn is None:
        raise SystemExit(
            f"unknown runner type {runner_type!r}; available: {sorted(RUNNERS)}"
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
            output,
            runner_type,
            config,
            suite=suite,
        )
        _write_dashboard_report(adapted, dashboard_target)

    if args.summary:
        _print_summary(output)
        _print_coverage_warnings(config)

    return 0


def _print_coverage_warnings(config: dict) -> None:
    """Run compose-spec coverage analysis against the comparison's compiled
    program and surface any eligibility-looking rules that aren't
    referenced by the comparison concept's expression tree.

    Cheap static analysis — runs in-process (no uv subprocess) since it
    only needs to read the compiled JSON. Silent when there are no gaps.
    """
    params = config.get("runner", {}).get("parameters") or {}
    compiled_program_ref = params.get("axiom_compiled_program")
    # Coverage analysis is per-concept; if a comparison declares multiple,
    # iterate. Falls back to the legacy single `concept:` field.
    concepts_raw = params.get("concepts") or (
        [params.get("concept")] if params.get("concept") else []
    )
    concepts: list[str] = [c for c in concepts_raw if isinstance(c, str) and c]
    if not compiled_program_ref or not concepts:
        return
    try:
        compiled_program = _resolve_path(compiled_program_ref, "axiom_compiled_program")
    except SystemExit:
        return
    if not compiled_program.exists():
        return
    try:
        from axiom_oracles.coverage import (
            find_uncovered_eligibility_rules,
            format_coverage_warning,
        )
    except ImportError:
        return
    # Coverage detection asks "what eligibility tests are orphaned" — only
    # auto-fires when the target itself looks like an eligibility judgment.
    # For amount targets (snap_benefit, federal-income-tax#liability) the
    # orphaned eligibility rules are intentionally on a different chain;
    # surfacing them as alarms would be noise. Users can still opt in
    # via `axiom-oracles coverage` directly with any target.
    for concept in concepts:
        target = str(concept).rsplit("#", 1)[-1]
        if not any(m in target for m in ("eligible", "ineligible")):
            continue
        uncovered = find_uncovered_eligibility_rules(compiled_program, target=target)
        warning = format_coverage_warning(target, uncovered)
        if warning:
            print()
            print(warning)


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
            "--with",
            "policyengine==4.11.0",
            "--with",
            "policyengine-us==1.705.16",
            "--with",
            "policyengine-core==3.26.11",
        ]
        if pinned
        else [
            "--with",
            "policyengine",
            "--with",
            "policyengine-us",
            "--with",
            "policyengine-core",
        ]
    )
    cmd = [
        "uv",
        "run",
        "--python",
        str(params.get("python", "3.14")),
        "--no-project",
        "--with-editable",
        str(axiom_encode_repo),
        *pe_pins,
        "axiom-encode",
        "tax-ecps-compare",
        "--rulespec-root",
        str(rulespec_root),
        "--axiom-rules-engine-path",
        str(axiom_rules_repo),
        "--sample-size",
        str(params.get("sample_size", 1000)),
        "--year",
        str(params.get("year", 2026)),
        "--surface",
        params.get("surface", "all"),
        "--json",
    ]
    if params.get("data_folder"):
        cmd.extend([
            "--data-folder",
            str(_resolve_path(params["data_folder"], "data_folder")),
        ])
    if params.get("allow_policyengine_us_version", True):
        cmd.append("--allow-policyengine-us-version")
    if params.get("allow_uncertified_policyengine_data", True):
        cmd.append("--allow-uncertified-policyengine-data")
    try:
        with output.open("w") as f:
            subprocess.run(cmd, check=True, stdout=f)
    finally:
        shutil.rmtree(rulespec_root.parent, ignore_errors=True)


def _run_axiom_encode_snap_ecps_compare(runner: dict, output: Path) -> None:
    """`axiom-encode snap-ecps-compare`, adapted from CSV to v2 JSON."""
    axiom_encode_repo = _resolve_path(runner["axiom_encode_repo"], "axiom_encode_repo")
    params = runner["parameters"]
    axiom_binary = None
    if runner.get("axiom_rules_repo"):
        axiom_rules_repo = _resolve_path(runner["axiom_rules_repo"], "axiom_rules_repo")
        _ensure_engine_binary(axiom_rules_repo, kind="release")
        axiom_binary = axiom_rules_repo / "target" / "release" / "axiom-rules-engine"

    with tempfile.TemporaryDirectory(prefix="snap-ecps-compare.") as tmp:
        csv_path = Path(tmp) / "rows.csv"
        cmd = [
            "uv",
            "run",
            "--directory",
            str(axiom_encode_repo),
            "--with",
            "policyengine-us==1.705.1",
            "--with",
            "numpy",
            "axiom-encode",
            "snap-ecps-compare",
            "--jurisdiction",
            str(params.get("jurisdiction", "us-co")),
            "--year",
            str(params.get("year", 2026)),
            "--month",
            str(params.get("month", 1)),
            "--utility-projection",
            str(params.get("utility_projection", "policyengine-type")),
            "--tolerance",
            str(params.get("tolerance", 1.5)),
            "--max-differences",
            str(params.get("max_differences", 50)),
            "--write-csv",
            str(csv_path),
        ]
        sample_size = params.get("sample_size")
        if sample_size not in (None, 0, "0"):
            cmd.extend(["--sample-size", str(sample_size)])
        if params.get("positive_snap_only"):
            cmd.append("--positive-snap-only")
        if params.get("state"):
            cmd.extend(["--state", str(params["state"])])
        if params.get("program"):
            cmd.extend(["--program", str(_resolve_path(params["program"], "program"))])
        if params.get("test_template"):
            cmd.extend(
                [
                    "--test-template",
                    str(_resolve_path(params["test_template"], "test_template")),
                ]
            )
        if params.get("workspace_root"):
            cmd.extend(
                [
                    "--workspace-root",
                    str(_resolve_path(params["workspace_root"], "workspace_root")),
                ]
            )
        if axiom_binary is not None:
            cmd.extend(["--axiom-binary", str(axiom_binary)])

        subprocess.run(cmd, check=True, cwd=REPO_ROOT)
        with csv_path.open(newline="") as f:
            rows = list(csv.DictReader(f))

    report = _adapt_snap_ecps_csv_to_v2(rows, runner)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


# PolicyEngine 4.11.0 hard-pins its bundled ECPS manifest at PE-US 1.700.0.
# Keep the in-repo oracle runner on that certified pair so PE SNAP outputs are
# reproducible across environments. The axiom-encode subprocess runners above
# keep their own pins because they are validating the encoder stack.
_PE_ORACLE_PINS = (
    "policyengine==4.11.0",
    "policyengine-us==1.700.0",
    "policyengine-core==3.26.11",
)

# The compare and sanity subprocesses share this import shim — extracted to
# module scope so `_run_sanity` can reuse it. With _PE_ORACLE_PINS it should not
# need to bypass certification, but the shim keeps policyengine.us import
# behavior stable for the local CLI.
_PE_CERT_OVERRIDE = """
import os, sys
os.environ['POLICYENGINE_SKIP_COUNTRY_IMPORTS'] = '1'
try:
    import policyengine
    import policyengine.provenance.manifest as _m

    def _allow_local_oracle_data(
        country_id, runtime_model_version, runtime_data_build_fingerprint=None
    ):
        return _m.DataCertification(
            compatibility_basis='axiom_oracle_local_policyengine_us_override',
            certified_for_model_version=runtime_model_version,
            data_build_fingerprint=runtime_data_build_fingerprint,
            certified_by='axiom-oracles run_comparison.py',
        )

    _m.certify_data_release_compatibility = _allow_local_oracle_data
    try:
        import policyengine.tax_benefit_models.common.model_version as _mv
        _mv.certify_data_release_compatibility = _allow_local_oracle_data
    except ImportError:
        pass
except ImportError:
    pass

os.environ.pop('POLICYENGINE_SKIP_COUNTRY_IMPORTS', None)
try:
    import policyengine
    from policyengine.tax_benefit_models import us as _us
    policyengine.us = _us
except Exception:
    pass

from axiom_oracles.cli import cli as _cli
_cli(sys.argv[1:], standalone_mode=False)
"""


def _concept_args(params: dict) -> list[str]:
    """Build `--concept <id>` repetitions from the comparison config.

    Accepts either ``concept: <id>`` (legacy single-string form) or
    ``concepts: [<id>, ...]`` for comparisons that span more than one
    output (e.g. SNAP eligibility AND benefit amount). The compare CLI's
    ``--concept`` option is ``multiple=True``, so we just repeat the
    flag once per concept."""

    concepts: list[str] = []
    raw_list = params.get("concepts")
    if isinstance(raw_list, list):
        concepts.extend(str(item) for item in raw_list if item)
    single = params.get("concept")
    if isinstance(single, str) and single and single not in concepts:
        concepts.append(single)
    if not concepts:
        raise SystemExit(
            "comparison config must declare either `concept:` (single) "
            "or `concepts:` (list) under runner.parameters"
        )
    args: list[str] = []
    for concept in concepts:
        args.extend(["--concept", concept])
    return args


def _run_axiom_oracles_compare(runner: dict, output: Path) -> None:
    """`axiom_oracles.cli compare <left> <right>` (in-repo CLI).

    Runs via `uv run --python 3.13` against pinned PolicyEngine versions so
    PE 4.11.0's pydantic-based models load cleanly. Mirrors the
    `axiom-encode-tax-ecps-compare` runner's environment.
    """
    axiom_rules_repo = _resolve_path(runner["axiom_rules_repo"], "axiom_rules_repo")
    _ensure_engine_binary(axiom_rules_repo, kind="release")
    params = runner["parameters"]
    _ensure_composed_axiom_program(params, axiom_rules_repo)
    cmd = [
        "uv",
        "run",
        "--python",
        "3.14",
        "--no-project",
        "--with-editable",
        str(REPO_ROOT),
        *(arg for pin in _PE_ORACLE_PINS for arg in ("--with", pin)),
        "python",
        "-c",
        _PE_CERT_OVERRIDE,
        "compare",
        params["left"],
        params["right"],
        "--population",
        params.get("population", "enhanced-cps"),
        "--sample-size",
        str(params.get("sample_size", 1000)),
        "--period",
        str(params["period"]),
        *_concept_args(params),
        "--axiom-engine-binary",
        str(axiom_rules_repo / "target" / "release" / "axiom-rules-engine"),
        "--output",
        str(output),
    ]
    if params.get("comparison_batch_size"):
        comparison_batch_size = params["comparison_batch_size"]
    elif any(
        concept.endswith("#snap_eligible") or concept.endswith("#snap_benefit")
        for concept in params.get("concepts", [])
    ):
        comparison_batch_size = 100
    else:
        comparison_batch_size = None
    if comparison_batch_size is not None:
        cmd.extend(["--comparison-batch-size", str(comparison_batch_size)])
    if params.get("axiom_compiled_program"):
        compiled_program = (
            _expand_path(params["axiom_compiled_program"])
            if params.get("axiom_program")
            else _resolve_path(
                params["axiom_compiled_program"],
                "axiom_compiled_program",
            )
        )
        cmd.extend([
            "--axiom-compiled-program",
            str(compiled_program),
        ])
    if params.get("jurisdiction_fips"):
        cmd.extend(["--jurisdiction-fips", str(params["jurisdiction_fips"])])
    env = dict(os.environ)
    roots_env = params.get("axiom_rulespec_repo_roots")
    if roots_env:
        env["AXIOM_RULESPEC_REPO_ROOTS"] = str(
            _resolve_path(roots_env, "axiom_rulespec_repo_roots")
        )
    subprocess.run(cmd, check=True, cwd=REPO_ROOT, env=env)


def _ensure_composed_axiom_program(params: dict, axiom_rules_repo: Path) -> None:
    """Compose/compile a program artifact when the comparison config declares one.

    Dashboard comparisons consume compiled artifacts, but `/tmp` artifacts are
    intentionally disposable. This hook keeps state SNAP dashboard regeneration
    reproducible from the declarative `axiom-programs` spec instead of relying
    on a prior manual compose step.
    """
    program_ref = params.get("axiom_program")
    if not program_ref:
        return
    compiled_ref = params.get("axiom_compiled_program")
    if not compiled_ref:
        raise SystemExit(
            "`axiom_program` comparisons must also declare "
            "`axiom_compiled_program`."
        )

    compose_binary = _resolve_path(
        params.get(
            "axiom_compose_binary",
            "$HOME/axiom-compose/.venv/bin/axiom-compose",
        ),
        "axiom_compose_binary",
    )
    program_path = _resolve_path(program_ref, "axiom_program")
    composed_path = _expand_path(
        params.get(
            "axiom_composed_program",
            str(_expand_path(compiled_ref).with_suffix(".composed.yaml")),
        )
    )
    compiled_path = _expand_path(compiled_ref)
    composed_path.parent.mkdir(parents=True, exist_ok=True)
    compiled_path.parent.mkdir(parents=True, exist_ok=True)

    roots = [
        _resolve_path(root, "rulespec_roots")
        for root in params.get("rulespec_roots", [])
    ]
    compose_cmd = [str(compose_binary), str(program_path)]
    for root in roots:
        compose_cmd.extend(["--rulespec-root", str(root)])
    compose_cmd.extend(["-o", str(composed_path)])
    subprocess.run(compose_cmd, check=True, cwd=REPO_ROOT)

    compile_env = dict(os.environ)
    roots_env = params.get("axiom_rulespec_repo_roots")
    if roots_env:
        compile_env["AXIOM_RULESPEC_REPO_ROOTS"] = str(_expand_path(roots_env))
    elif "AXIOM_RULESPEC_REPO_ROOTS" not in compile_env and roots:
        compile_env["AXIOM_RULESPEC_REPO_ROOTS"] = os.pathsep.join(
            str(root.parent) for root in roots
        )

    subprocess.run(
        [
            str(axiom_rules_repo / "target" / "release" / "axiom-rules-engine"),
            "compile",
            "--program",
            str(composed_path),
            "--output",
            str(compiled_path),
        ],
        check=True,
        cwd=REPO_ROOT,
        env=compile_env,
    )


RUNNERS = {
    "axiom-encode-snap-ecps-compare": _run_axiom_encode_snap_ecps_compare,
    "axiom-encode-tax-ecps-compare": _run_axiom_encode_tax_ecps_compare,
    "axiom-oracles-compare": _run_axiom_oracles_compare,
}


def _run_sanity(name: str) -> int:
    """Run a comparison's sanity fixtures via the CLI's `sanity` command.

    Reuses the same uv subprocess shape and PE certification override as
    the population comparison so engines see the same environment. Returns
    the CLI's exit code (non-zero on any failure).
    """
    config = _load_comparison(name)
    fixtures_path = COMPARISONS_DIR / f"{name}.fixtures.yaml"
    if not fixtures_path.exists():
        print(f"No fixtures file at {fixtures_path}", file=sys.stderr)
        return 2
    params = config["runner"]["parameters"]
    axiom_rules_repo = _resolve_path(
        config["runner"].get("axiom_rules_repo", "$HOME/axiom-rules"),
        "axiom_rules_repo",
    )
    cmd = [
        "uv", "run", "--python", "3.14", "--no-project",
        "--with-editable", str(REPO_ROOT),
        *(arg for pin in _PE_ORACLE_PINS for arg in ("--with", pin)),
        "python", "-c", _PE_CERT_OVERRIDE,
        "sanity", str(fixtures_path),
        "--left", params.get("left", "axiom"),
        "--right", params.get("right", "policyengine"),
        "--axiom-engine-binary",
        str(axiom_rules_repo / "target" / "release" / "axiom-rules-engine"),
    ]
    if params.get("axiom_compiled_program"):
        cmd.extend([
            "--axiom-compiled-program",
            str(_resolve_path(params["axiom_compiled_program"], "axiom_compiled_program")),
        ])
    if params.get("jurisdiction_fips"):
        cmd.extend(["--jurisdiction-fips", str(params["jurisdiction_fips"])])
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    return result.returncode


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
    expanded = _expand_path(raw)
    if not expanded.exists():
        env_override = {
            "axiom_encode_repo": "AXIOM_ENCODE_REPO",
            "axiom_rules_repo": "AXIOM_RULES_REPO",
        }.get(field)
        if env_override and os.environ.get(env_override):
            expanded = Path(
                os.path.expandvars(os.path.expanduser(os.environ[env_override]))
            ).resolve()
    if not expanded.exists():
        raise SystemExit(f"{field}: path does not exist: {expanded}")
    return expanded


def _expand_path(raw: str | Path) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(str(raw)))).resolve()


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
            print(f"  {surf:30s}  {c - m}/{c} ({p:6.2f}%)  mismatches={m}")
    elif "case_count" in data:
        cc = data.get("case_count", 0)
        mm = sum(len(c.get("mismatches", []) or []) for c in data.get("cases", []))
        print(f"Cases:             {cc}")
        print(f"Mismatch entries:  {mm}")
        agg = data.get("aggregates") or []
        if agg:
            print()
            for a in agg[:8]:
                compared = a.get("compared", a.get("comparison_count", 0))
                matched = a.get("matched", a.get("match_count"))
                if matched is None:
                    matched = compared - a.get("mismatch_count", 0)
                line = (
                    f"  {a.get('concept', '?'):40s}  "
                    f"compared={compared}  "
                    f"matched={matched}"
                )
                # Surface positive-rate context for binary concepts so the
                # reader can tell whether "agreement" is real agreement or
                # both-engines-returning-the-dominant-value agreement.
                if a.get("comparison") != "amount" and "left_positive_rate" in a:
                    line += (
                        f"  left+={a['left_positive_rate']:.0f}%"
                        f"  right+={a['right_positive_rate']:.0f}%"
                    )
                print(line)
            _print_quality_flags(agg)
    else:
        print("(unknown report shape — committed JSON for offline inspection)")


def _print_quality_flags(aggregates: list) -> None:
    """Print loud, separable alarms for degenerate positive rates.

    Quality flags computed in report.py travel attached to each aggregate
    row; rendering them as a dedicated block (not nested inside the per-
    concept table) is what makes them visible at a glance.
    """
    flags = [
        (a.get("concept", "?"), flag)
        for a in aggregates
        for flag in (a.get("quality_flags") or [])
    ]
    if not flags:
        return
    print()
    print("!! QUALITY ALARMS")
    for concept, flag in flags:
        print(f"  [{flag.get('severity', '?').upper()}] {concept}")
        print(f"    {flag.get('code', '?')}: {flag.get('message', '')}")


# ---------------------------------------------------------------------------
# Dashboard adapter
# ---------------------------------------------------------------------------


def _adapt_to_v2(raw_path: Path, runner_type: str, config: dict, *, suite: str) -> dict:
    raw = json.loads(raw_path.read_text())
    if runner_type == "axiom-encode-tax-ecps-compare":
        return _adapt_tax_ecps_to_v2(raw, config, suite=suite)
    # axiom-oracles-compare already emits v2 — pass through, but override
    # the suite with the comparison-config value. The upstream report
    # stamps the population/synthetic-subset name (e.g. "nyc-synthetic"),
    # not the per-comparison identity, so without this override every
    # state's SNAP report collapses into one suite bucket in the
    # dashboard's suite selector.
    raw["suite"] = suite
    return raw


def _adapt_tax_ecps_to_v2(raw: dict, config: dict, *, suite: str) -> dict:
    """Convert tax-ecps-compare flat output to axiom.comparison_report.v2.

    Surfaces become aggregates; mismatching entities become cases (matching
    units are counted in summary/aggregates but don't appear in cases[]). The
    schema treats `comparison_weight` as the running denominator; we don't
    have ECPS household weights here, so we set weights = counts to keep
    the dashboard's weighted columns identical to unweighted.
    """
    from collections import Counter, defaultdict

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
        aggregates.append(
            {
                "category": spec["category"],
                "comparison": "amount",
                "comparison_count": compared,
                "comparison_weight": compared,
                "components": [],
                "concept": spec["concept"],
                "description": spec["description"],
                "left_weighted_sum": None,
                "match_rate": match_rate,
                "match_weight": matched,
                "mismatch_count": mismatches,
                "mismatch_weight": mismatches,
                "missing_both_count": 0,
                "missing_left_count": 0,
                "missing_right_count": 0,
                "parent": spec["parent"],
                "right_weighted_sum": None,
                "weighted_difference": None,
                "weighted_match_rate": match_rate,
            }
        )
        component_concepts.append(spec["concept"])

    parent_compared = raw.get("compared_values", 0)
    parent_mismatches = raw.get("mismatch_count", 0)
    parent_matched = parent_compared - parent_mismatches
    parent_rate = (parent_matched / parent_compared * 100) if parent_compared else 100.0
    aggregates.insert(
        0,
        {
            "category": "tax",
            "comparison": "amount",
            "comparison_count": parent_compared,
            "comparison_weight": parent_compared,
            "components": component_concepts,
            "concept": "us:tax/federal-income-tax#liability",
            "description": "Federal income tax liability (ECPS, all surfaces)",
            "left_weighted_sum": None,
            "match_rate": parent_rate,
            "match_weight": parent_matched,
            "mismatch_count": parent_mismatches,
            "mismatch_weight": parent_mismatches,
            "missing_both_count": 0,
            "missing_left_count": 0,
            "missing_right_count": 0,
            "parent": None,
            "right_weighted_sum": None,
            "weighted_difference": None,
            "weighted_match_rate": parent_rate,
        },
    )

    # Concepts manifest mirrors aggregates so the dashboard's concept loader
    # picks them up. Components carry parent={parent_id} for auto-allow.
    concepts: list[dict] = [
        {
            "category": "tax",
            "comparison": "amount",
            "components": component_concepts,
            "description": "Federal income tax liability (ECPS, all surfaces)",
            "id": "us:tax/federal-income-tax#liability",
            "parent": None,
            "tolerance": 15,
        }
    ]
    for surface, rows in by_surface.items():
        spec = FIIT_SURFACE_CONCEPTS.get(surface)
        if spec is None:
            continue
        concepts.append(
            {
                "category": spec["category"],
                "comparison": "amount",
                "components": [],
                "description": spec["description"],
                "id": spec["concept"],
                "parent": spec["parent"],
                "tolerance": spec["tolerance"],
            }
        )

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
        cases.append(
            {
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
            }
        )

    mismatches_by_concept = [
        {"value": value, "count": count}
        for value, count in sorted(
            Counter(m["concept"] for m in flat_mismatches).items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]

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
            "mismatches_by_concept": mismatches_by_concept,
            "mismatches_by_kind": [
                {"value": "amount_difference", "count": parent_mismatches}
            ],
            "mismatches_by_scenario": {},
            "weighted": {
                "comparison_weight": parent_compared,
                "match_rate": parent_rate,
                "match_weight": parent_matched,
                "mismatch_weight": parent_mismatches,
            },
        },
    }


def _adapt_snap_ecps_csv_to_v2(rows: list[dict], runner: dict) -> dict:
    """Convert snap-ecps-compare row CSV into axiom.comparison_report.v2."""
    params = runner.get("parameters", {})
    jurisdiction = str(params.get("jurisdiction", "us-co"))
    state_code = str(params.get("state") or jurisdiction.rsplit("-", 1)[-1]).upper()
    tolerance = float(params.get("tolerance", 1.5))
    amount_concept_id = "us:statutes/7/2014/u#snap_benefit"
    eligibility_concept_id = "us:statutes/7/2014/o#snap_eligible"
    compared = len(rows)
    amount_mismatching_rows = [row for row in rows if not _csv_bool(row.get("match"))]
    eligibility_mismatching_rows = [
        row
        for row in rows
        if _csv_bool(row.get("axiom_snap_eligible"))
        != _csv_bool(row.get("pe_snap_eligible"))
    ]
    amount_matched = compared - len(amount_mismatching_rows)
    eligibility_matched = compared - len(eligibility_mismatching_rows)
    amount_match_rate = (amount_matched / compared * 100) if compared else 100.0
    eligibility_match_rate = (
        eligibility_matched / compared * 100
    ) if compared else 100.0
    left_sum = sum(_csv_float(row.get("axiom_snap_allotment")) for row in rows)
    right_sum = sum(_csv_float(row.get("pe_snap")) for row in rows)
    left_eligible_count = sum(
        1 for row in rows if _csv_bool(row.get("axiom_snap_eligible"))
    )
    right_eligible_count = sum(
        1 for row in rows if _csv_bool(row.get("pe_snap_eligible"))
    )

    cases: list[dict] = []
    flat_mismatches: list[dict] = []
    mismatching_rows_by_spm = {
        str(row.get("spm_unit_id") or "unknown"): row
        for row in [*amount_mismatching_rows, *eligibility_mismatching_rows]
    }
    for spm_unit_id, row in mismatching_rows_by_spm.items():
        spm_unit_id = str(row.get("spm_unit_id") or "unknown")
        case_id = f"ecps-spm-{spm_unit_id}"
        case_mismatches = []
        if not _csv_bool(row.get("match")):
            axiom_value = _csv_float(row.get("axiom_snap_allotment"))
            pe_value = _csv_float(row.get("pe_snap"))
            difference = _csv_float(row.get("difference"), axiom_value - pe_value)
            mismatch = {
                "case_id": case_id,
                "concept": amount_concept_id,
                "description": "SNAP benefit amount",
                "difference": difference,
                "kind": "amount_difference",
                "left": axiom_value,
                "parent": None,
                "relative_tolerance": 0,
                "right": pe_value,
                "tolerance": tolerance,
            }
            case_mismatches.append(mismatch)
            flat_mismatches.append(mismatch)
        axiom_eligible = _csv_bool(row.get("axiom_snap_eligible"))
        pe_eligible = _csv_bool(row.get("pe_snap_eligible"))
        if axiom_eligible != pe_eligible:
            if axiom_eligible and not pe_eligible:
                kind = "eligibility_left_only"
            elif pe_eligible and not axiom_eligible:
                kind = "eligibility_right_only"
            else:
                kind = "eligibility_mismatch"
            mismatch = {
                "case_id": case_id,
                "concept": eligibility_concept_id,
                "description": "SNAP eligibility",
                "difference": None,
                "kind": kind,
                "left": axiom_eligible,
                "parent": None,
                "relative_tolerance": 0,
                "right": pe_eligible,
                "tolerance": 0,
            }
            case_mismatches.append(mismatch)
            flat_mismatches.append(mismatch)
        case_match_rate = (
            (2 - len(case_mismatches)) / 2 * 100 if case_mismatches else 100.0
        )
        metadata = {
            "axiom_gross_income": _csv_float(row.get("axiom_gross_income")),
            "axiom_net_income": _csv_float(row.get("axiom_net_income")),
            "axiom_shelter_deduction": _csv_float(
                row.get("axiom_shelter_deduction")
            ),
            "axiom_snap_eligible": _csv_bool(row.get("axiom_snap_eligible")),
            "axiom_utility_allowance": _csv_float(
                row.get("axiom_utility_allowance")
            ),
            "case_unit": "spm_unit",
            "dataset": "enhanced_cps",
            "household_id": row.get("household_id"),
            "population": "enhanced-cps",
            "pe_gross_income": _csv_float(row.get("pe_gross_income")),
            "pe_net_income": _csv_float(row.get("pe_net_income")),
            "pe_shelter_deduction": _csv_float(row.get("pe_shelter_deduction")),
            "pe_snap_eligible": _csv_bool(row.get("pe_snap_eligible")),
            "pe_utility_allowance": _csv_float(row.get("pe_utility_allowance")),
            "spm_unit_id": spm_unit_id,
            "state": state_code,
            "suite": f"{jurisdiction}-snap-ecps",
        }
        for key, value in row.items():
            if key.startswith(("axiom_", "pe_")) and key not in metadata:
                metadata[key] = _csv_scalar(value)
        cases.append(
            {
                "case_id": case_id,
                "left_engine": "axiom",
                "left_errors": [],
                "match_rate": case_match_rate,
                "metadata": metadata,
                "mismatches": case_mismatches,
                "right_engine": "policyengine",
                "right_errors": [],
            }
        )

    amount_aggregate = {
        "category": "food",
        "comparison": "amount",
        "comparison_count": compared,
        "comparison_weight": compared,
        "compared": compared,
        "components": [],
        "concept": amount_concept_id,
        "description": "SNAP benefit amount",
        "left_weighted_sum": left_sum,
        "match_count": amount_matched,
        "match_rate": amount_match_rate,
        "match_weight": amount_matched,
        "matched": amount_matched,
        "mismatch_count": len(amount_mismatching_rows),
        "mismatch_weight": len(amount_mismatching_rows),
        "missing_both_count": 0,
        "missing_left_count": 0,
        "missing_right_count": 0,
        "parent": None,
        "right_weighted_sum": right_sum,
        "weighted_difference": left_sum - right_sum,
        "weighted_match_rate": amount_match_rate,
    }
    eligibility_aggregate = {
        "category": "food",
        "comparison": "eligibility",
        "comparison_count": compared,
        "comparison_weight": compared,
        "compared": compared,
        "components": [],
        "concept": eligibility_concept_id,
        "description": "SNAP eligibility",
        "left_positive_rate": (left_eligible_count / compared * 100)
        if compared
        else 0.0,
        "left_positive_weight": left_eligible_count,
        "match_count": eligibility_matched,
        "match_rate": eligibility_match_rate,
        "match_weight": eligibility_matched,
        "matched": eligibility_matched,
        "mismatch_count": len(eligibility_mismatching_rows),
        "mismatch_weight": len(eligibility_mismatching_rows),
        "missing_both_count": 0,
        "missing_left_count": 0,
        "missing_right_count": 0,
        "parent": None,
        "positive_rate_difference": (
            (left_eligible_count - right_eligible_count) / compared * 100
        )
        if compared
        else 0.0,
        "quality_flags": [],
        "right_positive_rate": (right_eligible_count / compared * 100)
        if compared
        else 0.0,
        "right_positive_weight": right_eligible_count,
        "weighted_match_rate": eligibility_match_rate,
    }
    mismatches_by_concept = [
        {"value": value, "count": count}
        for value, count in sorted(
            Counter(m["concept"] for m in flat_mismatches).items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    mismatches_by_kind = [
        {"value": value, "count": count}
        for value, count in sorted(
            Counter(m["kind"] for m in flat_mismatches).items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    summary_comparison_count = compared * 2
    summary_match_count = amount_matched + eligibility_matched
    summary_mismatch_count = len(amount_mismatching_rows) + len(
        eligibility_mismatching_rows
    )
    summary_match_rate = (
        summary_match_count / summary_comparison_count * 100
        if summary_comparison_count
        else 100.0
    )

    return {
        "aggregates": [amount_aggregate, eligibility_aggregate],
        "case_count": compared,
        "cases": cases,
        "concepts": [
            {
                "category": "food",
                "comparison": "amount",
                "components": [],
                "description": "SNAP benefit amount",
                "id": amount_concept_id,
                "parent": None,
                "priority": "high",
                "relative_tolerance": 0,
                "tolerance": tolerance,
            },
            {
                "category": "food",
                "comparison": "eligibility",
                "components": [],
                "description": "SNAP eligibility",
                "id": eligibility_concept_id,
                "parent": None,
                "priority": "high",
                "relative_tolerance": 0,
                "tolerance": 0,
            },
        ],
        "engines": {"left": "axiom", "right": "policyengine"},
        "errors": [],
        "locales": [state_code],
        "mismatches": flat_mismatches,
        "population": "enhanced-cps",
        "schema_version": "axiom.comparison_report.v2",
        "scope": {"geoid": state_code, "type": "state"},
        "suite": f"{jurisdiction}-snap-ecps",
        "summary": {
            "comparison_count": summary_comparison_count,
            "error_count": 0,
            "errors_by_engine": {},
            "match_count": summary_match_count,
            "mismatch_count": summary_mismatch_count,
            "mismatches_by_concept": mismatches_by_concept,
            "mismatches_by_kind": mismatches_by_kind,
            "mismatches_by_scenario": {},
            "weighted": {
                "comparison_weight": summary_comparison_count,
                "match_rate": summary_match_rate,
                "match_weight": summary_match_count,
                "mismatch_weight": summary_mismatch_count,
            },
        },
    }


def _csv_bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y", "holds"}


def _csv_float(value: object, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _csv_scalar(value: object) -> object:
    text = str(value).strip()
    if text.lower() in {"1", "true", "t", "yes", "y", "holds"}:
        return True
    if text.lower() in {"0", "false", "f", "no", "n", "not_holds"}:
        return False
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return value


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
