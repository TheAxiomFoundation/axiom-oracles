#!/usr/bin/env python3
"""Propose a reviewed US default-stack update; never rewrite oracle reports.

Release discovery is PyPI metadata, dependency selection is uv's resolver, and
compatibility evidence is the existing adapter on the same committed cases.
No PyPI field is treated as proof that a release is correct or compatible.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from axiom_oracles import pinned_artifacts  # noqa: E402
from axiom_oracles.policyengine_defaults import (  # noqa: E402
    DEFAULT_REQUIREMENTS_PATH,
    PACKAGE_NAMES,
    load_defaults,
    validate_defaults,
    validate_requirements_lock,
)

FIXTURES = ROOT / "data/policyengine_update_cases.json"
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
PROPOSAL_KEYS = {
    "schema",
    "base_commit",
    "baseline",
    "candidate",
    "status",
    "latest_model",
    "fixture_sha256",
    "candidate_lock_sha256",
    "changes",
    "baseline_result",
    "candidate_result",
    "limitations",
    "errors",
}
LIMITATIONS = [
    "Synthetic adapter compatibility and baseline/candidate differences only; not Axiom parity certification.",
    "No population dataset, licensed input, or full comparison-suite replay is covered by this probe.",
    "Uses the existing generic runner's explicit local-data certification override; does not certify dataset/model compatibility.",
    "Explicit suite pins, dataset-matched historical lanes, expected outputs and dispositions are unchanged.",
]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pypi_project(package: str) -> dict:
    request = Request(
        f"https://pypi.org/pypi/{package}/json", headers={"Cache-Control": "no-cache"}
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def latest_stable_release(project: dict, python_version: str = "3.14") -> str:
    """Highest final/post release with a non-yanked Python-compatible wheel.

    Yanking is file-level, so a release with an unusable or yanked file is not
    rejected if another usable non-yanked wheel remains. uv checks actual
    platform tags and the complete dependency graph afterward.
    """
    candidates = []
    for text, files in project.get("releases", {}).items():
        try:
            release = Version(text)
        except InvalidVersion:
            continue
        if release.is_prerelease or release.is_devrelease or release.local is not None:
            continue
        for artifact in files:
            if (
                artifact.get("yanked") is not False
                or artifact.get("packagetype") != "bdist_wheel"
            ):
                continue
            python_spec = artifact.get("requires_python")
            if python_spec and not SpecifierSet(python_spec).contains(
                python_version, prereleases=False
            ):
                continue
            candidates.append((release, text))
            break
    if not candidates:
        raise ValueError(
            "PyPI lists no final, non-yanked, Python-compatible wheel release"
        )
    return max(candidates)[1]


def locked_versions(text: str) -> dict[str, str]:
    """Validate a data-only, hash-locked public-index requirements file.

    Publication never executes this file. Reject URLs, index changes, editable
    packages, loose constraints and unhashed lines before it enters an update PR.
    """
    if len(text.encode()) > 2_000_000:
        raise ValueError("candidate requirements file exceeds 2 MB")
    result = {}
    joined = text.replace("\\\n", " ")
    for line in joined.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        hashes = re.findall(r"(?:^|\s)--hash=sha256:([0-9a-f]{64})(?=\s|$)", line)
        requirement_text = re.sub(r"\s+--hash=sha256:[0-9a-f]{64}(?=\s|$)", "", line)
        if not hashes or "--" in requirement_text:
            raise ValueError(
                "every candidate requirement must have only SHA-256 hash options"
            )
        req = Requirement(requirement_text)
        specs = list(req.specifier)
        if (
            req.url
            or req.extras
            or len(specs) != 1
            or specs[0].operator != "=="
            or "*" in specs[0].version
        ):
            raise ValueError(
                "candidate requirements must contain exact public-index package pins"
            )
        release = Version(specs[0].version)
        if release.is_prerelease or release.is_devrelease or release.local is not None:
            raise ValueError("candidate requirements contain a pre/dev/local release")
        name = canonicalize_name(req.name)
        if name in result and result[name] != str(release):
            raise ValueError(f"candidate lock has conflicting versions for {name}")
        result[name] = str(release)
    if not result:
        raise ValueError("candidate requirements are empty")
    return result


def release_metadata(package: str, release: str) -> dict:
    request = Request(
        f"https://pypi.org/pypi/{package}/{release}/json",
        headers={"Cache-Control": "no-cache"},
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def non_yanked_lock(text: str, fetch=release_metadata) -> str:
    """Keep only non-yanked wheel hashes, including every resolved dependency.

    Exact-version installs can otherwise allow a yanked file. Hash checking at
    installation limits uv to the non-yanked artifacts observed in this run.
    """
    versions = locked_versions(text)
    with ThreadPoolExecutor(max_workers=8) as executor:
        metadata = dict(
            zip(
                versions,
                executor.map(lambda item: fetch(*item), versions.items()),
                strict=True,
            )
        )
    lines = []
    for line in text.replace("\\\n", " ").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        requirement_text = re.sub(r"\s+--hash=sha256:[0-9a-f]{64}(?=\s|$)", "", line)
        req = Requirement(requirement_text)
        name = canonicalize_name(req.name)
        selected = set(re.findall(r"--hash=sha256:([0-9a-f]{64})", line))
        allowed = {
            artifact.get("digests", {}).get("sha256")
            for artifact in metadata[name].get("urls", [])
            if artifact.get("yanked") is False
            and artifact.get("packagetype") == "bdist_wheel"
            and (
                not artifact.get("requires_python")
                or SpecifierSet(artifact["requires_python"]).contains("3.14")
            )
        }
        hashes = sorted(selected & allowed)
        if not hashes:
            raise ValueError(
                f"{name}=={versions[name]} has no resolved non-yanked wheel"
            )
        lines.append(
            str(req)
            + " \\\n"
            + " \\\n".join(f"    --hash=sha256:{value}" for value in hashes)
        )
    return "\n".join(lines) + "\n"


def validate_candidate_lock(text: str, packages: dict[str, str]) -> None:
    actual = locked_versions(text)
    if any(actual.get(name) != value for name, value in packages.items()):
        raise ValueError("candidate lock does not match the proposed package versions")


def validate_probe_result(
    result: dict, packages: dict[str, str], fixtures: dict
) -> None:
    """Counts alone are not evidence; require every declared case/output pair."""
    expected_cases = {case["id"] for case in fixtures["cases"]}
    expected_variables = set(fixtures["variables"])
    if (
        result.get("errors") != []
        or result.get("packages") != packages
        or type(result.get("case_count")) is not int
        or result["case_count"] != len(expected_cases)
        or type(result.get("comparison_count")) is not int
        or result["comparison_count"] != len(expected_cases) * len(expected_variables)
        or not result["comparison_count"]
        or result.get("batch_count") != (len(expected_cases) + 1) // 2
        or not isinstance(result.get("cases"), list)
    ):
        raise ValueError("proposal lacks successful nonempty version-asserted evidence")
    seen = set()
    for row in result["cases"]:
        if not isinstance(row, dict) or set(row) != {"case_id", "outputs"}:
            raise ValueError("invalid probe case")
        case_id = row["case_id"]
        if (
            not isinstance(case_id, str)
            or case_id not in expected_cases
            or case_id in seen
        ):
            raise ValueError("missing, duplicate, or unexpected probe case")
        seen.add(case_id)
        values = row["outputs"]
        if (
            not isinstance(values, dict)
            or set(values) != expected_variables
            or any(
                type(value) not in (int, float, bool) or not math.isfinite(value)
                for value in values.values()
            )
        ):
            raise ValueError("missing or invalid required probe output")
    if seen != expected_cases:
        raise ValueError("missing required probe case")


def validate_proposal(payload: object) -> dict:
    if not isinstance(payload, dict) or set(payload) != PROPOSAL_KEYS:
        raise ValueError("proposal has missing or unknown fields")
    if type(payload["schema"]) is not int or payload["schema"] != 1:
        raise ValueError("proposal schema must be 1")
    if not isinstance(payload["base_commit"], str) or not HEX40.fullmatch(
        payload["base_commit"]
    ):
        raise ValueError("proposal needs the exact tested repository commit")
    baseline = validate_defaults(payload["baseline"])
    status = payload["status"]
    if not isinstance(status, str) or status not in {
        "passed",
        "needs-review",
        "no-update",
        "failed",
    }:
        raise ValueError("invalid proposal status")
    for key in ("fixture_sha256", "candidate_lock_sha256"):
        value = payload[key]
        if not isinstance(value, str) or not HEX64.fullmatch(value):
            raise ValueError(f"invalid {key}")
    if payload["candidate"] is not None:
        candidate = validate_defaults(payload["candidate"])
        if candidate["policyengine-us"] != payload["latest_model"]:
            raise ValueError("candidate differs from the selected model release")
        if (
            Version(candidate["policyengine-us"])
            <= Version(baseline["policyengine-us"])
            and status != "no-update"
        ):
            raise ValueError("candidate is not newer than the default US model")
    elif status in {"passed", "needs-review"}:
        raise ValueError("publishable proposal has no candidate")
    for key in ("limitations", "errors"):
        if (
            not isinstance(payload[key], list)
            or len(payload[key]) > 100
            or any(not isinstance(x, str) or len(x) > 3000 for x in payload[key])
        ):
            raise ValueError(f"invalid {key}")
    for key in ("baseline_result", "candidate_result"):
        if not isinstance(payload[key], dict):
            raise ValueError(f"invalid {key}")
    if not isinstance(payload["changes"], list) or len(payload["changes"]) > 1000:
        raise ValueError("invalid changes")
    for row in payload["changes"]:
        if not isinstance(row, dict) or set(row) != {
            "case_id",
            "variable",
            "before",
            "after",
            "difference",
        }:
            raise ValueError("invalid change row")
        if any(
            not isinstance(row[k], str) or len(row[k]) > 100
            for k in ("case_id", "variable")
        ):
            raise ValueError("invalid comparison identity")
        if any(
            type(row[k]) not in (int, float, bool) or not math.isfinite(row[k])
            for k in ("before", "after", "difference")
        ):
            raise ValueError("invalid numerical change")
        if not math.isclose(
            row["after"] - row["before"], row["difference"], abs_tol=1e-9
        ):
            raise ValueError("change arithmetic does not reconcile")
    if status in {"passed", "needs-review"}:
        if payload["errors"]:
            raise ValueError("a publishable proposal cannot contain execution errors")
        if payload["fixture_sha256"] != digest(FIXTURES.read_bytes()):
            raise ValueError("proposal inputs differ from the committed probe cases")
        fixtures = json.loads(FIXTURES.read_text())
        for key, packages in (
            ("baseline_result", baseline),
            ("candidate_result", candidate),
        ):
            validate_probe_result(payload[key], packages, fixtures)
        if payload["changes"] != numerical_changes(
            payload["baseline_result"], payload["candidate_result"]
        ):
            raise ValueError(
                "reported numerical changes differ from the returned values"
            )
        if (status == "needs-review") != bool(payload["changes"]):
            raise ValueError(
                "proposal status does not match its measured numerical changes"
            )
    return payload


def render_report(payload: dict) -> str:
    lines = [
        "# Proposed default PolicyEngine-US update",
        "",
        f"Probe status: **{payload['status']}**",
        "",
        f"Tested source commit: `{payload['base_commit']}`",
        "",
        "| Package | Current default | Candidate |",
        "|---|---|---|",
    ]
    candidate = (payload.get("candidate") or {}).get("packages", {})
    for name, value in payload["baseline"]["packages"].items():
        lines.append(f"| {name} | {value} | {candidate.get(name, 'unresolved')} |")
    lines.extend(
        [
            "",
            f"Frozen input SHA-256: `{payload['fixture_sha256']}`",
            f"Candidate requirements SHA-256: `{payload['candidate_lock_sha256']}`",
            "",
            "## Execution and numerical changes",
            "",
        ]
    )
    for key in ("baseline_result", "candidate_result"):
        result = payload[key]
        lines.append(
            f"- {key}: {result.get('case_count', 0)} cases, {result.get('comparison_count', 0)} returned outputs."
        )
        lines.extend(
            f"  - Error: {str(error)[:1500]}" for error in result.get("errors", [])[:10]
        )
    lines.append(
        f"\nChanged household outputs: {len(payload['changes'])}. Changes are evidence to review, not corrected expected values.\n"
    )
    if payload["changes"]:
        lines.extend(
            [
                "| Case | Variable | Before | After | Difference |",
                "|---|---|---:|---:|---:|",
            ]
        )
        for row in payload["changes"][:100]:
            lines.append(
                f"| {row['case_id']} | {row['variable']} | {row['before']:.6g} | {row['after']:.6g} | {row['difference']:.6g} |"
            )
    lines.extend(["", "## Scope", "", *[f"- {x}" for x in payload["limitations"]]])
    lines.extend(
        ["", *[f"- Resolution/probe error: {x}" for x in payload["errors"]], ""]
    )
    return "\n".join(lines)


def _run(cmd: list[str], *, env: dict[str, str], timeout: int = 600) -> None:
    result = subprocess.run(
        cmd, env=env, text=True, capture_output=True, timeout=timeout
    )
    if result.returncode:
        raise RuntimeError(
            f"{Path(cmd[0]).name} failed ({result.returncode}):\n{(result.stderr or result.stdout)[-4000:]}"
        )


def resolve_lock(
    uv: str, requirements: list[str], output: Path, env: dict[str, str]
) -> None:
    source = output.with_suffix(".in")
    source.write_text(
        "\n".join(
            requirements
            + [
                "click>=8.1",
                "cryptography>=44",
                "pyyaml>=6",
                "requests>=2.31",
                "packaging>=24.2",
            ]
        )
        + "\n"
    )
    _run(
        [
            uv,
            "pip",
            "compile",
            "--no-config",
            "--python-version",
            "3.14",
            "--python-platform",
            "x86_64-unknown-linux-gnu",
            "--only-binary",
            ":all:",
            "--generate-hashes",
            "--no-header",
            "--no-annotate",
            "--output-file",
            str(output),
            str(source),
        ],
        env=env,
    )


def baseline_lock(
    uv: str, packages: dict[str, str], work: Path, env: dict[str, str]
) -> Path:
    """Use the exact reviewed default lock after the first accepted update."""
    if DEFAULT_REQUIREMENTS_PATH.exists():
        validate_requirements_lock(DEFAULT_REQUIREMENTS_PATH.read_text(), packages)
        return DEFAULT_REQUIREMENTS_PATH
    lock = work / "baseline-requirements.txt"
    requirements = [
        pinned_artifacts.requirement(f"{name}=={release}")
        for name, release in packages.items()
    ]
    resolve_lock(uv, requirements, lock, env)
    return lock


def execute_probe(
    uv: str, lock: Path, packages: dict[str, str], directory: Path, env: dict[str, str]
) -> dict:
    directory.mkdir()
    profile = directory / "packages.json"
    profile.write_text(json.dumps(packages))
    venv = directory / "venv"
    _run([uv, "venv", "--no-config", "--python", "3.14", str(venv)], env=env)
    python = venv / "bin/python"
    _run(
        [
            uv,
            "pip",
            "sync",
            "--no-config",
            "--python",
            str(python),
            "--only-binary",
            ":all:",
            "--require-hashes",
            str(lock),
        ],
        env=env,
    )
    output = directory / "result.json"
    result = subprocess.run(
        [
            str(python),
            "-I",
            str(ROOT / "scripts/probe_policyengine_update.py"),
            "--fixtures",
            str(FIXTURES),
            "--packages",
            str(profile),
            "--output",
            str(output),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if not output.exists():
        raise RuntimeError(
            f"probe returned no evidence ({result.returncode}): {result.stderr[-3000:]}"
        )
    evidence = json.loads(output.read_text())
    if result.returncode:
        evidence.setdefault("errors", []).append(
            f"probe exited {result.returncode}: {result.stderr[-1500:]}"
        )
    return evidence


def numerical_changes(before: dict, after: dict) -> list[dict]:
    left = {
        (row["case_id"], key): value
        for row in before.get("cases", [])
        for key, value in row["outputs"].items()
    }
    right = {
        (row["case_id"], key): value
        for row in after.get("cases", [])
        for key, value in row["outputs"].items()
    }
    return [
        {
            "case_id": case,
            "variable": variable,
            "before": left[(case, variable)],
            "after": right[(case, variable)],
            "difference": right[(case, variable)] - left[(case, variable)],
        }
        for case, variable in sorted(left.keys() & right.keys())
        if left[(case, variable)] != right[(case, variable)]
    ]


def probe(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    baseline = load_defaults()
    base = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    payload = {
        "schema": 1,
        "base_commit": base,
        "baseline": {"schema": 1, "packages": baseline},
        "candidate": None,
        "status": "failed",
        "latest_model": None,
        "fixture_sha256": digest(FIXTURES.read_bytes()),
        "candidate_lock_sha256": digest(b""),
        "changes": [],
        "baseline_result": {},
        "candidate_result": {},
        "limitations": LIMITATIONS,
        "errors": [],
    }
    try:
        if subprocess.run(
            ["git", "-C", str(ROOT), "diff", "--quiet", "HEAD"]
        ).returncode:
            raise ValueError(
                "probe requires committed source files so its recorded commit identifies the executed code"
            )
        model = latest_stable_release(pypi_project("policyengine-us"))
        payload["latest_model"] = model
        if Version(model) <= Version(baseline["policyengine-us"]):
            payload["status"] = "no-update"
        else:
            wrapper = latest_stable_release(pypi_project("policyengine"))
            uv = shutil.which("uv")
            if uv is None:
                raise RuntimeError("uv is required")
            with tempfile.TemporaryDirectory(prefix="axiom-pe-update-") as tmp:
                work = Path(tmp)
                env = {
                    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                    "UV_CACHE_DIR": str(work / "cache"),
                    "PYTHONNOUSERSITE": "1",
                    "OMP_NUM_THREADS": "1",
                    "OPENBLAS_NUM_THREADS": "1",
                }
                candidate_lock = output.resolve() / "candidate-requirements.txt"
                resolve_lock(
                    uv,
                    [f"policyengine=={wrapper}", f"policyengine-us=={model}"],
                    candidate_lock,
                    env,
                )
                candidate_lock.write_text(non_yanked_lock(candidate_lock.read_text()))
                resolved = locked_versions(candidate_lock.read_text())
                candidate = {name: resolved[name] for name in PACKAGE_NAMES}
                validate_defaults({"schema": 1, "packages": candidate})
                payload["candidate"] = {"schema": 1, "packages": candidate}
                payload["candidate_lock_sha256"] = digest(candidate_lock.read_bytes())
                reviewed_lock = baseline_lock(uv, baseline, work, env)
                payload["baseline_result"] = execute_probe(
                    uv, reviewed_lock, baseline, work / "baseline", env
                )
                payload["candidate_result"] = execute_probe(
                    uv, candidate_lock, candidate, work / "candidate", env
                )
                payload["changes"] = numerical_changes(
                    payload["baseline_result"], payload["candidate_result"]
                )
                payload["status"] = (
                    "failed"
                    if any(
                        payload[k].get("errors")
                        or not payload[k].get("comparison_count")
                        for k in ("baseline_result", "candidate_result")
                    )
                    else "needs-review"
                    if payload["changes"]
                    else "passed"
                )
    except Exception as exc:
        payload["errors"].append(f"{type(exc).__name__}: {exc}"[:3000])
    validate_proposal(payload)
    (output / "proposal.json").write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n"
    )
    (output / "report.md").write_text(render_report(payload))
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("probe")
    command.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    payload = probe(args.output_dir)
    print(render_report(payload))
    return 0 if payload["status"] in {"passed", "needs-review", "no-update"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
