#!/usr/bin/env python3
"""Run the two-record emulator probe or one Maryland crash reproducer.

These are observations of pinned executable outputs, not legal evidence.
Only ``emulator`` invokes PolicyEngine, once over the two fixture records.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from importlib.metadata import version
import json
import math
from pathlib import Path
import platform
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.adapters.policyengine import PolicyEngineTaxsimRunner  # noqa: E402
from axiom_oracles.adapters.taxsim import TaxsimPackageRunner, pins  # noqa: E402
from axiom_oracles.comparison.comparator import Comparator  # noqa: E402
from axiom_oracles.comparison.mappings import load_program_mappings  # noqa: E402
from axiom_oracles.comparison.report import build_comparison_report  # noqa: E402
from axiom_oracles.populations.taxsim_csv import read_taxsim_csv  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "taxsim_probes"
FIXTURE_SHA256 = {
    "mfj-itemizer-2024.csv": "a16fd5d9220e649059b23af0e7f54712ca2121303f95df51ae4dfe3515fd5099",
    "pension-only-2024.csv": "25a56476850bd81251e650ad2984e8157a8cef4bfe668b2b286e952b4f8a14bf",
    "pension-only-2025.csv": "df8dda59bd189b763db894de9d951b4dd8ef29d007a88afe59a7280bd0f75ec6",
}
CONCEPTS = (
    "us:tax/federal-income-tax#liability",
    "us:tax/state-income-tax#liability",
)
NO_FALLBACK_PROFILE = "september-2026-09-no-fallback"


def probe_inputs(kind: str, year: int):
    filename = "mfj-itemizer-2024.csv" if kind == "emulator" else f"pension-only-{year}.csv"
    population = read_taxsim_csv(
        FIXTURES / filename, expected_sha256=FIXTURE_SHA256[filename],
        origin={
            "repo": "PolicyEngine/policyengine-taxsim",
            "commit": "3a58992ad6330920a1dc93bc6d83efe5de954d13",
            "path": f"tests/fixtures/maryland_taxsim_crash/{filename}",
        } if kind == "crash" else None,
    )
    cases = population.select().cases
    if len(cases) != 2:
        raise AssertionError("A live probe must contain exactly two records")
    return population, cases


def _results_record(results):
    return [
        {
            "case_id": result.household_id,
            "engine": result.engine,
            "values": result.values,
            "errors": list(result.errors),
            "raw": result.raw,
        }
        for result in results
    ]


def assert_result_contract(cases, results):
    """Assert conservation and usable output or an explicit isolated crash."""
    expected = {case.case_id for case in cases}
    if len(results) != len(cases) or {r.household_id for r in results} != expected:
        raise AssertionError("Probe result IDs must equal the two input IDs")
    for result in results:
        if result.errors:
            if not all(error.startswith("taxsim-crash:") for error in result.errors):
                raise AssertionError(f"Unexpected engine failure: {result.errors}")
            if not result.raw.get("taxsim_error", {}).get("signature"):
                raise AssertionError("A crash must preserve its structured signature")
        else:
            for name in ("fiitax", "siitax"):
                if not math.isfinite(float(result.raw[name])):
                    raise AssertionError(f"Non-finite successful probe output: {name}")


def _report(suite, cases, mappings, left, right):
    report = build_comparison_report(
        suite_name=suite,
        population="taxsim-csv",
        locales={case.metadata.get("locale", "US") for case in cases},
        scope=None,
        cases=cases,
        mappings=mappings,
        comparisons=Comparator(mappings).compare(left, right),
        include_inputs=True,
    )
    errored = {r.household_id for r in (*left, *right) if r.errors}
    for row in report["mismatches"]:
        if row["case_id"] in errored and row["kind"] != "engine_error":
            raise AssertionError("A failed probe must become an engine_error row")
    if sum(row["kind"] == "engine_error" for row in report["mismatches"]) != (
        len(errored) * len(mappings)
    ):
        raise AssertionError("Every failed probe must retain every compared output")
    return report


def run_probe(kind: str, year: int = 2024) -> dict:
    population, cases = probe_inputs(kind, year)
    mappings = [
        replace(mapping, tolerance=15, relative_tolerance=0)
        for mapping in load_program_mappings()
        if mapping.concept_id in CONCEPTS
    ]
    profile = "dashboard-2026-09" if kind == "emulator" else NO_FALLBACK_PROFILE
    taxsim = TaxsimPackageRunner(pin_profile=profile)
    right = taxsim.run_cases(cases, variables=list(CONCEPTS))
    assert_result_contract(cases, right)
    extra = {}
    identities = {"taxsim": taxsim.taxsim_identity()}
    if kind == "emulator":
        # PolicyEngineRunner defaults (native SALT); no second simulation.
        emulator = PolicyEngineTaxsimRunner()
        left = emulator.run_cases(cases, variables=list(CONCEPTS))
        assert_result_contract(cases, left)
        identities["policyengine"] = {
            "policyengine_taxsim": version("policyengine-taxsim"),
            "policyengine_us": version("policyengine-us"),
            "policyengine_core": version("policyengine-core"),
            "runner": "PolicyEngineTaxsimRunner",
            "disable_salt": False,
            "assume_w2_wages": False,
            "output_detail": 2,
        }
        suite = "taxsim-emulator-probes"
    else:
        baseline = TaxsimPackageRunner(pin_profile="pe-taxsim-main-2026-08")
        left = [
            replace(result, engine="taxsim-reference")
            for result in baseline.run_cases(cases, variables=list(CONCEPTS))
        ]
        assert_result_contract(cases, left)
        if any(result.errors for result in left):
            raise AssertionError("The pinned August reference probe failed")
        identities["taxsim-reference"] = baseline.taxsim_identity()
        mappings = [
            replace(mapping, targets={
                **mapping.targets,
                "taxsim-reference": mapping.target_for_engine("taxsim"),
            })
            for mapping in mappings
        ]
        suite = f"taxsim-crash-probes-{year}"
        # The upstream reproducers are batch-dependent. Default bisection may
        # recover both records. A zero-rerun pass independently checks that a
        # failing batch produces C2 engine_error rows when it cannot be retried.
        bounded = TaxsimPackageRunner(pin_profile=profile, max_crash_reruns=0)
        bounded_results = bounded.run_cases(cases, variables=list(CONCEPTS))
        assert_result_contract(cases, bounded_results)
        bounded_report = _report(suite, cases, mappings, left, bounded_results)
        if bounded.crash_log and not all(r.errors for r in bounded_results):
            raise AssertionError("A failed zero-rerun batch must retain both failures")
        if not bounded.crash_log and any(r.errors for r in bounded_results):
            raise AssertionError("Crash results must have a recorded executable failure")
        extra["zero_rerun_budget"] = {
            "crash_log": bounded.crash_log,
            "results": _results_record(bounded_results),
            "mismatches": bounded_report["mismatches"],
        }
    report = _report(suite, cases, mappings, left, right)
    report["dataset_identity"] = population.identity
    report["engine_identity"] = identities
    report["probe_observations"] = {
        "platform": pins.normalize_platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "left": _results_record(left),
        "right": _results_record(right),
        "crash_log": taxsim.crash_log,
        "outcome": "isolated-errors" if any(r.errors for r in right) else (
            "recovered-after-bisection" if taxsim.crash_log else "completed"
        ),
        **extra,
    }
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("emulator", "crash"))
    parser.add_argument("--year", type=int, choices=(2024, 2025), default=2024)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-platform", choices=("linux", "darwin", "windows"))
    args = parser.parse_args(argv)
    if args.kind == "emulator" and args.year != 2024:
        parser.error("The emulator probe is the 2024 fixture")
    if args.expected_platform and pins.normalize_platform() != args.expected_platform:
        parser.error(f"Expected platform {args.expected_platform}, got {pins.normalize_platform()}")
    report = run_probe(args.kind, args.year)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    observed = report["probe_observations"]
    print(f"{report['suite']} ({observed['platform']}): {observed['outcome']}")
    for side in ("left", "right"):
        for result in observed[side]:
            raw = result["raw"]
            print(f"  {result['engine']} {result['case_id']}: "
                  f"fiitax={raw.get('fiitax')} siitax={raw.get('siitax')} "
                  f"errors={result['errors']}")
    if "zero_rerun_budget" in observed:
        bounded = observed["zero_rerun_budget"]
        print(f"  zero-rerun crash log: {bounded['crash_log']}")
        print(f"  zero-rerun engine_error rows: "
              f"{sum(row['kind'] == 'engine_error' for row in bounded['mismatches'])}")
    print(f"Wrote: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
