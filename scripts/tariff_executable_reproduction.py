#!/usr/bin/env python3
"""Build/check the executable receipt for the US tariff witness slice.

The receipt binds an exact rulespec-us commit and hash-identified engine binary. It
recompiles the witness composition plus every generated chapter schedule
composition, then reruns ten values reviewed as conformant in the
``us-tariff-panel`` report: both endpoints of one deterministic Canada-origin
interval for each of the five covered witness lines.  JSON numeric equality is
type-aware and exact.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner  # noqa: E402
from axiom_oracles.suites.us_tariff_panel import (  # noqa: E402
    AUTHORITY_SLOTS,
    OUTPUTS,
    REFERENCE_DIRNAME,
    TOTAL,
    load_reference,
    panel_case,
)

SCHEMA = "axiom_oracles.executable_reproduction.v1"
PROGRAM = "us/tariff-witness"
RULESPEC_REPO = "TheAxiomFoundation/rulespec-us"
GENERATED_BY = "scripts/tariff_executable_reproduction.py"
SOURCE_PRODUCER_COMMIT = "5402e5bf6"
SOURCE_REFRESH_COMMIT = "d236e5320"
PINNED_RULESPEC_SHA = "96d5e7c1e6309dc205b7320bbddaae8dd5d410df"
PINNED_ENGINE_SHA256 = (
    "674ca6e70afdccb59c3d6847933bc24b4590105e49db54790f2dcd0bdbbe32d7"
)
DEFAULT_RULESPEC_ROOT = Path("/Users/maxghenis/TheAxiomFoundation/_b1wt/rulespec-us")
DEFAULT_ENGINE_BINARY = Path(
    "/Users/maxghenis/TheAxiomFoundation/axiom-rules-engine-pinned/target/release/axiom-rules-engine"
)
OUTPUT_PATH = REPO_ROOT / "conformance/executable/us-tariff-witness.json"
REPORT_PATH = Path("reports/axiom-yale-us-tariff-panel-all-2026-08-03.json")
REFERENCE_PATHS = (
    Path("reference/us-tariff-panel/covered_lines.txt"),
    Path("reference/us-tariff-panel/yale_panel_slice.csv"),
    Path("reference/us-tariff-panel/census_iso_bridge.csv"),
    REPORT_PATH,
)
WITNESS_SPEC = Path("programs/us/us-tariff-duty/fy-2026.yaml")
WITNESS_MODULE = Path("us/policies/cbp/us-tariff-duty/composition.yaml")
SCHEDULE_SPEC_GLOB = "programs/us/us-tariff-schedule/ch*.yaml"
SCHEDULE_MODULE_TEMPLATE = (
    "us/policies/cbp/us-tariff-schedule/generated/{stem}/{stem}.yaml"
)
ORIGIN_CENSUS = (
    "1220"  # Canada: the sole raw-conformant cohort common to all five lines.
)
HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
PROGRAM_SET = {
    "id": "us-tariff-schedule-ensemble-v1",
    "scope_kind": "multi-program-ensemble",
    "row_contract": "program_spec<TAB>module<TAB>promised_output",
    "program_count": 101,
    "rows_sha256": ("c476cb14ac580ff7e8cf92b8f077bbbe58915beca429ee0c18b76e44484c53d3"),
    "singular_composed_output": False,
}
COMPILED_ARTIFACT_ROWS_SHA256 = (
    "713ee709a7c62841efed1b5d9874f1b04996db7052fe798e5d2de40065742f68"
)
EXECUTION_TRACE_ROWS_SHA256 = (
    "c2542eb7685d4f196cc89922d9f065a62da5ab0feeab96a34f2a2b62b8f6e9fb"
)
EXECUTION_COVERAGE_BLOCKER = (
    "executable: promised-output coverage incomplete — 101 programs compile, "
    "but only 10 values on one non-promised witness output replay"
)
EXECUTION_SCOPE = {
    "claim": (
        "compile-bound ensemble; 10 reviewed values replayed on one "
        "non-promised witness output"
    ),
    "compiled_program_count": 101,
    "replayed_program_count": 1,
    "replayed_program_spec": str(WITNESS_SPEC),
    "replayed_module": str(WITNESS_MODULE),
    "replayed_case_count": 10,
    "replayed_output": TOTAL,
    "replayed_output_is_promised": False,
    "promised_output_case_count": 0,
    "ensemble_promised_output_coverage_complete": False,
}
REPRODUCTION_CONTRACT = {
    "repo_only": False,
    "external_rulespec_git_object_required": True,
    "external_engine_binary_required": True,
    "source_build_proven": False,
    "engine_binary_provenance": {
        "identity": "sha256-only",
        "published_source_commit": None,
        "published_release_tag": None,
        "published_build_recipe": None,
        "source_build_proven": False,
        "published_provenance": False,
        "limitation": (
            "Within this contract, identity is the tested binary SHA-256 only; "
            "the contract does not bind a source commit, release tag, or build "
            "recipe and does not prove a source build. Other artifacts may "
            "record a source ref without proving its build link to these bytes."
        ),
    },
    "limitation": (
        "Full reproduction requires external pinned RuleSpec Git objects and the "
        "hash-identified engine binary; repo-only CI validates the committed "
        "receipt only."
    ),
}
COMPILE_CONTRACT = (
    "env AXIOM_RULESPEC_REPO_ROOTS=<parent-of-archived-rulespec-us> "
    "compile --program <absolute module path> --output <artifact>"
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True)


def _render(value: Any) -> str:
    return json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _git_commit(repo: Path, ref: str) -> str:
    process = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", f"{ref}^{{commit}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    sha = process.stdout.strip()
    _require(HEX_40.fullmatch(sha) is not None, f"invalid rulespec commit {sha!r}")
    return sha


def _materialize(repo: Path, sha: str, destination: Path) -> Path:
    archive = subprocess.run(
        ["git", "-C", str(repo), "archive", "--format=tar", sha, "us", "programs"],
        check=True,
        capture_output=True,
    ).stdout
    root = destination / "rulespec-us"
    root.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as source:
        source.extractall(root, filter="data")
    return root


def _programs(root: Path) -> list[dict[str, str]]:
    rows = [
        {
            "program_spec": str(WITNESS_SPEC),
            "module": str(WITNESS_MODULE),
            "promised_output": "us_tariff_duty",
        }
    ]
    specs = sorted(root.glob(SCHEDULE_SPEC_GLOB))
    _require(len(specs) == 100, f"expected 100 schedule specs, found {len(specs)}")
    for spec in specs:
        relative = spec.relative_to(root)
        rows.append(
            {
                "program_spec": str(relative),
                "module": SCHEDULE_MODULE_TEMPLATE.format(stem=spec.stem),
                "promised_output": "schedule_statutory_stack",
            }
        )
    for row in rows:
        _require(
            (root / row["program_spec"]).is_file(), f"missing {row['program_spec']}"
        )
        _require((root / row["module"]).is_file(), f"missing {row['module']}")
        program_spec = yaml.safe_load((root / row["program_spec"]).read_text())
        outputs = (
            program_spec.get("outputs") if isinstance(program_spec, dict) else None
        )
        _require(
            outputs == [row["promised_output"]],
            f"promised output drifted for {row['program_spec']}",
        )
    return rows


def _program_set(rows: list[dict[str, Any]]) -> dict[str, Any]:
    identities = [
        (
            row.get("program_spec"),
            row.get("module"),
            row.get("promised_output"),
        )
        for row in rows
    ]
    _require(
        all(
            all(isinstance(value, str) and value for value in row) for row in identities
        ),
        "program-set identities must be nonempty strings",
    )
    _require(len(identities) == len(set(identities)), "program-set identities repeat")
    lines = ["\t".join(row) for row in sorted(identities)]
    return {
        "id": PROGRAM_SET["id"],
        "scope_kind": PROGRAM_SET["scope_kind"],
        "row_contract": PROGRAM_SET["row_contract"],
        "program_count": len(rows),
        "rows_sha256": hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest(),
        "singular_composed_output": False,
    }


def _rows_sha256(rows: list[dict[str, Any]], *, sort_programs: bool) -> str:
    payload = (
        sorted(
            rows,
            key=lambda row: (
                row.get("program_spec", ""),
                row.get("module", ""),
                row.get("promised_output", ""),
            ),
        )
        if sort_programs
        else rows
    )
    return hashlib.sha256(_canonical_json(payload).encode()).hexdigest()


def _compile_all(root: Path, engine: Path, work: Path) -> list[dict[str, Any]]:
    env = os.environ.copy()
    # An archived rulespec-us directory sits under this root, preserving the
    # campaign harness's AXIOM_RULESPEC_REPO_ROOTS parent-directory contract.
    env["AXIOM_RULESPEC_REPO_ROOTS"] = str(root.parent)
    compiled = []
    for index, row in enumerate(_programs(root)):
        artifact = work / f"compiled-{index:03d}.json"
        subprocess.run(
            [
                str(engine),
                "compile",
                "--program",
                str(root / row["module"]),
                "--output",
                str(artifact),
            ],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        compiled.append(
            {
                **row,
                "program_spec_sha256": _sha256(root / row["program_spec"]),
                "source_sha256": _sha256(root / row["module"]),
                "sha256": _sha256(artifact),
                "byte_count": artifact.stat().st_size,
                "compile_contract": COMPILE_CONTRACT,
            }
        )
    return compiled


def _expected_vector(interval: Any) -> dict[str, float]:
    vector = {
        slot: sum(interval.rates[column] for column in columns)
        for slot, (_concept, columns) in AUTHORITY_SLOTS.items()
    }
    vector["total"] = interval.statutory_total
    return vector


def _reviewed_conformant_cases(repo_root: Path) -> list[dict[str, Any]]:
    intervals, unbridged = load_reference(repo_root / REFERENCE_DIRNAME)
    _require(not unbridged, f"reference contains unbridged origins: {unbridged}")
    report = json.loads((repo_root / REPORT_PATH).read_text())
    families = report.get("cases")
    _require(
        report.get("suite") == "us-tariff-panel" and isinstance(families, list),
        "bad tariff report",
    )
    lines = sorted(
        line.strip()
        for line in (repo_root / "reference/us-tariff-panel/covered_lines.txt")
        .read_text()
        .splitlines()
        if line.strip() and not line.startswith("#")
    )
    _require(len(lines) == 5, f"expected five witness lines, found {len(lines)}")
    selected = []
    for line in lines:
        candidates = [
            interval
            for interval in intervals
            if interval.hts10 == line
            and interval.country_census == ORIGIN_CENSUS
            and len(interval.covered_dates) == 2
        ]
        _require(candidates, f"no two-endpoint Canada interval for {line}")
        interval = None
        family = None
        for candidate in sorted(
            candidates, key=lambda item: (item.valid_from, item.valid_until)
        ):
            expected = _expected_vector(candidate)
            family_matches = [
                row
                for row in families
                if row.get("hts_number") == line
                and row.get("expected") == expected
                and row.get("match") is True
                and ORIGIN_CENSUS in row.get("countries", [])
                and all(
                    day.isoformat() in row.get("probe_dates", [])
                    for day in candidate.covered_dates
                )
            ]
            if len(family_matches) == 1:
                interval, family = candidate, family_matches[0]
                break
        _require(
            interval is not None and family is not None,
            f"no conformant two-endpoint Canada family for {line}",
        )
        for probe in interval.covered_dates:
            case = panel_case(interval, probe)
            selected.append(
                {
                    "case": case,
                    "case_id": case.case_id,
                    "hts_number": line,
                    "origin_census": ORIGIN_CENSUS,
                    "origin_iso2": interval.iso2,
                    "probe_date": probe.isoformat(),
                    "source_family": family["case_id"],
                    "output": TOTAL,
                    "committed_value": family["axiom"]["total"],
                    "input_sha256": hashlib.sha256(
                        _canonical_json(case.metadata).encode()
                    ).hexdigest(),
                }
            )
    _require(
        len(selected) == 10,
        f"expected ten reviewed conformant values, found {len(selected)}",
    )
    return selected


def build_reproduction(
    *,
    rulespec_repo: Path = DEFAULT_RULESPEC_ROOT,
    rulespec_ref: str,
    engine_binary: Path = DEFAULT_ENGINE_BINARY,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    rulespec_repo = rulespec_repo.expanduser().resolve()
    engine_binary = engine_binary.expanduser().resolve()
    sha = _git_commit(rulespec_repo, rulespec_ref)
    _require(
        sha == PINNED_RULESPEC_SHA,
        f"rulespec commit must equal reviewed pin {PINNED_RULESPEC_SHA}",
    )
    binary_sha = _sha256(engine_binary)
    expected = _reviewed_conformant_cases(repo_root)
    with tempfile.TemporaryDirectory(prefix="tariff-executable-") as raw:
        work = Path(raw)
        archived = _materialize(rulespec_repo, sha, work)
        compiled = _compile_all(archived, engine_binary, work)
        runner = AxiomRulesRunner(
            program_path=archived / WITNESS_MODULE,
            binary_path=engine_binary,
            default_entity="CustomsEntry",
            default_entity_id="entry",
            rulespec_repo_roots=(archived,),
            mode="explain",
        )
        results = runner.run_cases([row["case"] for row in expected], list(OUTPUTS))
    actual_by_id = {str(result.household_id): result for result in results}
    cases = []
    for row in expected:
        result = actual_by_id[row["case_id"]]
        reproduced = result.values.get(TOTAL)
        errors = list(result.errors)
        match = not errors and _canonical_json(reproduced) == _canonical_json(
            row["committed_value"]
        )
        cases.append(
            {key: value for key, value in row.items() if key != "case"}
            | {"reproduced_value": reproduced, "errors": errors, "match": match}
        )
    sources = [
        {"path": str(path), "sha256": _sha256(repo_root / path)}
        for path in REFERENCE_PATHS
    ]
    matched = sum(row["match"] for row in cases)
    return {
        "schema": SCHEMA,
        "program": PROGRAM,
        "generated_by": GENERATED_BY,
        "producer_source": {
            "introduced_commit": SOURCE_PRODUCER_COMMIT,
            "adopted_refresh_commit": SOURCE_REFRESH_COMMIT,
        },
        "rulespec": {"repo": RULESPEC_REPO, "ref": sha, "sha": sha},
        "engine": {
            "binary_sha256": binary_sha,
            "configured_sha256": PINNED_ENGINE_SHA256,
            "matches_config_pin": binary_sha == PINNED_ENGINE_SHA256,
            "provenance": REPRODUCTION_CONTRACT["engine_binary_provenance"],
        },
        "source_reports": sources,
        "selection": {
            "convention": "dk-sized deterministic witness subset",
            "covered_lines": sorted({row["hts_number"] for row in cases}),
            "origin_census": ORIGIN_CENSUS,
            "interval_rule": "earliest conformant in-domain interval having two endpoints per line",
            "values_per_line": 2,
        },
        "execution_scope": EXECUTION_SCOPE,
        "reproduction_contract": REPRODUCTION_CONTRACT,
        "program_set": _program_set(compiled),
        "compiled_artifact_rows_sha256": _rows_sha256(compiled, sort_programs=True),
        "compiled_artifacts": compiled,
        "execution_trace_rows_sha256": _rows_sha256(cases, sort_programs=False),
        "cases": cases,
        "summary": {
            "program_count": len(compiled),
            "case_count": len(cases),
            "matched_case_count": matched,
            "all_cases_reproduced": matched == len(cases),
            "engine_binary_matches_pin": binary_sha == PINNED_ENGINE_SHA256,
            "compile_replay_reproduced": (
                matched == len(cases) and binary_sha == PINNED_ENGINE_SHA256
            ),
            "promised_output_coverage_complete": False,
            "executable": False,
            "blockers": [EXECUTION_COVERAGE_BLOCKER],
        },
    }


def validate_artifact(
    document: dict[str, Any], repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    _require(document.get("schema") == SCHEMA, "wrong schema")
    _require(
        document.get("program") == PROGRAM,
        "program identity drifted",
    )
    _require(
        document.get("generated_by") == GENERATED_BY,
        "generator identity drifted",
    )
    _require(
        document.get("producer_source")
        == {
            "introduced_commit": SOURCE_PRODUCER_COMMIT,
            "adopted_refresh_commit": SOURCE_REFRESH_COMMIT,
        },
        "producer source metadata drifted",
    )
    _require(
        document.get("rulespec")
        == {
            "repo": RULESPEC_REPO,
            "ref": PINNED_RULESPEC_SHA,
            "sha": PINNED_RULESPEC_SHA,
        },
        "rulespec identity differs from the reviewed pin",
    )
    _require(
        document.get("engine")
        == {
            "binary_sha256": PINNED_ENGINE_SHA256,
            "configured_sha256": PINNED_ENGINE_SHA256,
            "matches_config_pin": True,
            "provenance": REPRODUCTION_CONTRACT["engine_binary_provenance"],
        },
        "engine identity differs from the reviewed pin",
    )
    expected_source_reports = [
        {"path": str(path), "sha256": _sha256(repo_root / path)}
        for path in REFERENCE_PATHS
    ]
    _require(
        document.get("source_reports") == expected_source_reports,
        "source report identity or digest drifted",
    )
    expected = _reviewed_conformant_cases(repo_root)
    cases = document.get("cases")
    _require(
        isinstance(cases, list) and len(cases) == 10,
        "cases must contain exactly 10 rows",
    )
    for actual, source in zip(cases, expected, strict=True):
        for key in (
            "case_id",
            "hts_number",
            "origin_census",
            "origin_iso2",
            "probe_date",
            "source_family",
            "output",
            "input_sha256",
        ):
            _require(
                actual.get(key) == source[key], f"{source['case_id']}: {key} drifted"
            )
        _require(
            _canonical_json(actual.get("committed_value"))
            == _canonical_json(source["committed_value"]),
            f"{source['case_id']}: committed_value drifted",
        )
        derived = not actual.get("errors") and _canonical_json(
            actual.get("reproduced_value")
        ) == _canonical_json(source["committed_value"])
        _require(
            actual.get("match") is derived,
            f"{source['case_id']}: match is not exact JSON numeric equality",
        )
    expected_selection = {
        "convention": "dk-sized deterministic witness subset",
        "covered_lines": sorted({row["hts_number"] for row in expected}),
        "origin_census": ORIGIN_CENSUS,
        "interval_rule": (
            "earliest conformant in-domain interval having two endpoints per line"
        ),
        "values_per_line": 2,
    }
    _require(
        document.get("selection") == expected_selection,
        "selection metadata drifted",
    )
    _require(
        document.get("execution_scope") == EXECUTION_SCOPE,
        "execution scope drifted or overstates promised-output coverage",
    )
    _require(
        document.get("reproduction_contract") == REPRODUCTION_CONTRACT,
        "reproduction contract drifted",
    )
    compiled = document.get("compiled_artifacts")
    _require(
        isinstance(compiled, list) and len(compiled) == 101,
        "compiled_artifacts must bind 101 programs",
    )
    derived_program_set = _program_set(compiled)
    _require(derived_program_set == PROGRAM_SET, "compiled program set drifted")
    _require(document.get("program_set") == PROGRAM_SET, "program_set summary drifted")
    compiled_rows_sha256 = _rows_sha256(compiled, sort_programs=True)
    _require(
        compiled_rows_sha256 == COMPILED_ARTIFACT_ROWS_SHA256,
        "compiled artifact rows differ from the reviewed producer pin",
    )
    _require(
        document.get("compiled_artifact_rows_sha256") == COMPILED_ARTIFACT_ROWS_SHA256,
        "compiled artifact row digest drifted",
    )
    for row in compiled:
        _require(
            set(row)
            == {
                "program_spec",
                "module",
                "promised_output",
                "program_spec_sha256",
                "source_sha256",
                "sha256",
                "byte_count",
                "compile_contract",
            },
            "compiled artifact row fields drifted",
        )
        for key in ("program_spec_sha256", "source_sha256", "sha256"):
            _require(
                isinstance(row.get(key), str)
                and HEX_64.fullmatch(row[key]) is not None,
                f"invalid {key}",
            )
        _require(
            isinstance(row.get("byte_count"), int)
            and not isinstance(row["byte_count"], bool)
            and row["byte_count"] > 0,
            "invalid compiled byte_count",
        )
        _require(
            row.get("compile_contract") == COMPILE_CONTRACT,
            "compile contract drifted",
        )
    execution_trace_sha256 = _rows_sha256(cases, sort_programs=False)
    _require(
        execution_trace_sha256 == EXECUTION_TRACE_ROWS_SHA256,
        "execution trace rows differ from the reviewed producer pin",
    )
    _require(
        document.get("execution_trace_rows_sha256") == EXECUTION_TRACE_ROWS_SHA256,
        "execution trace row digest drifted",
    )
    summary = document.get("summary", {})
    matched = sum(row.get("match") is True for row in cases)
    expected_summary = {
        "program_count": len(compiled),
        "case_count": len(cases),
        "matched_case_count": matched,
        "all_cases_reproduced": matched == len(cases),
        "engine_binary_matches_pin": True,
        "compile_replay_reproduced": matched == len(cases),
        "promised_output_coverage_complete": False,
        "executable": False,
        "blockers": [EXECUTION_COVERAGE_BLOCKER],
    }
    _require(summary == expected_summary, "summary is not derived")
    _require(
        summary["compile_replay_reproduced"] is True,
        "compile/replay receipt did not reproduce",
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--artifact", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--rulespec-root", type=Path, default=DEFAULT_RULESPEC_ROOT)
    parser.add_argument("--rulespec-ref", default=None)
    parser.add_argument("--engine-binary", type=Path, default=DEFAULT_ENGINE_BINARY)
    args = parser.parse_args(argv)
    artifact = args.artifact.expanduser()
    ref = args.rulespec_ref or "main"
    committed = None
    if args.check:
        try:
            committed = json.loads(artifact.read_text())
            validate_artifact(committed)
            ref = committed["rulespec"]["sha"]
            if args.rulespec_ref is not None:
                _require(
                    _git_commit(args.rulespec_root, args.rulespec_ref) == ref,
                    "--rulespec-ref differs from receipt",
                )
        except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
            print(f"invalid executable artifact: {exc}", file=sys.stderr)
            return 1
    try:
        reproduced = build_reproduction(
            rulespec_repo=args.rulespec_root,
            rulespec_ref=ref,
            engine_binary=args.engine_binary,
        )
        validate_artifact(reproduced)
    except (OSError, subprocess.CalledProcessError, ValueError, RuntimeError) as exc:
        print(f"executable reproduction failed: {exc}", file=sys.stderr)
        return 1
    rendered = _render(reproduced)
    if args.check:
        if artifact.read_text() != rendered:
            print("executable reproduction drifted", file=sys.stderr)
            return 1
        print(
            "compile/replay receipt up to date: 101 programs compiled; 10/10 exact "
            "JSON numeric equality on one non-promised witness output; executable=false"
        )
        return 0
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(rendered)
    print(f"wrote {artifact}; reproduced 10/10 values")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
