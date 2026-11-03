#!/usr/bin/env python3
"""Fail, naming the file, when a pinned PolicyEngine artifact stops installing.

PolicyEngine prunes old releases from PyPI's index. A comparison whose pin is
pruned fails at install time ("there is no version of policyengine-us==...")
and its report on oracle-data stops refreshing. This check runs on a schedule
so the break shows up here first, with the file to fix:

1. Every file in ``axiom_oracles/pinned_artifacts.py`` downloads from its
   hashed URL and matches its recorded SHA-256.
2. Every exact PolicyEngine-family pin is either listed on PyPI's index or
   recoverable from that table. The pins come from every script under
   ``scripts/`` (literal, spaced, underscore and tuple spellings, parameter
   defaults, ``--oracle-with-args`` recipes, and f-string versions, which
   must resolve), every
   ``comparisons/**/*.yaml`` (version keys at any depth), and the TAXSIM pin
   file.
3. Every ``policyengine-us`` commit archive a suite or script installs
   downloads.

A 5xx or a connection error is retried twice with backoff and reported as
transient, apart from a 4xx such as 404, which means the file or release is
gone. Breaks already tracked in an issue (``KNOWN_OPEN``) print as warnings,
so only a new break fails the run.

Exit status 1 lists each failure as ``<file>[:line]: <pin>: <reason>``.

    python3 scripts/check_pinned_artifacts.py            # all three checks
    python3 scripts/check_pinned_artifacts.py --list     # print the inventory
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles import pinned_artifacts  # noqa: E402

#: Unrecoverable pins and archives already tracked in an issue. They print as
#: warnings; anything else that will not install fails the run.
KNOWN_OPEN: dict[tuple[str, str], str] = {
    ("policyengine-us", "1.784.4"): "#659",
}
KNOWN_OPEN_SOURCES: dict[str, str] = {}

_NAMES = r"policyengine(?:[-_](?:us|core|uk|taxsim))?|spm[-_]calculator"
_VERSION = r"[0-9]+(?:\.[0-9]+)*"
_PIN = re.compile(rf"(?<![\w-])({_NAMES})\s*==\s*({_VERSION})(?!\w|\.[0-9])")
_TUPLE_PIN = re.compile(rf"""\(\s*["']({_NAMES})["']\s*,\s*["']({_VERSION})["']\s*\)""")
_FSTRING_PIN = re.compile(rf"(?<![\w-])({_NAMES})\s*==\s*\{{([^}}]*)\}}")
_PARAM_DEFAULT = re.compile(
    rf"""params\.get\(\s*["'](policyengine(?:_us|_core|_uk)?_version)["']\s*,"""
    rf"""\s*["']({_VERSION})["']\s*\)"""
)
#: ``python -m axiom_oracles.pinned_artifacts --oracle-with-args VERSION``
#: (the probe recipes) installs that policyengine-us release.
_ORACLE_WITH_ARGS = re.compile(rf"--oracle-with-args[\s\\]+({_VERSION})(?!\w|\.[0-9])")
_ARCHIVE = re.compile(
    r"https://github\.com/PolicyEngine/policyengine-us/archive/[0-9a-f]{40}\.tar\.gz"
)
_PARAM_PACKAGE = {
    "policyengine_version": "policyengine",
    "policyengine_us_version": "policyengine-us",
    "policyengine_core_version": "policyengine-core",
    "policyengine_uk_version": "policyengine-uk",
}
#: Version keys a YAML file may carry at any depth.
_YAML_VERSION_KEYS = {
    **_PARAM_PACKAGE,
    "policyengine_taxsim_version": "policyengine-taxsim",
    "policyengine_us": "policyengine-us",
    "policyengine_core": "policyengine-core",
    "policyengine_uk": "policyengine-uk",
}
_VERSION_VALUE = re.compile(rf"{_VERSION}")

#: f-string versions this check resolves elsewhere, by file and expression.
#: Any other ``name=={expr}`` fails closed: the check cannot know its version.
RESOLVED_ELSEWHERE: dict[tuple[str, str], str] = {
    ("scripts/run_comparison.py", "pe_meta"): "params.get default, scanned",
    ("scripts/run_comparison.py", "pe_us"): "params.get default, scanned",
    ("scripts/run_comparison.py", "pe_core"): "params.get default, scanned",
    ("scripts/run_comparison.py", "meta"): "_resolve_pe_oracle_pins: YAML or _PE_ORACLE_PINS",
    ("scripts/run_comparison.py", "us"): "_resolve_pe_oracle_pins: YAML or _PE_ORACLE_PINS",
    ("scripts/run_comparison.py", "core"): "_resolve_pe_oracle_pins: YAML or _PE_ORACLE_PINS",
    ("scripts/run_comparison.py", "_taxsim_pin_version()"): "taxsim_pins.json",
}
#: Top-level functions and assignments that only build report provenance
#: labels. They name versions but install nothing, so pins inside them are
#: not counted; the installs they describe are counted where they happen.
LABEL_SCOPES: dict[tuple[str, str], str] = {
    ("scripts/run_comparison.py", "_build_run_provenance"): "provenance.oracle labels",
    ("scripts/backfill_report_provenance.py", "_PE_ORACLE_PINS"): "backfilled labels",
    ("scripts/backfill_report_provenance.py", "_reconstruct_oracle"): "backfilled labels",
}
#: Files under scripts/ that are not scanned. This checker names example pins
#: in its own KNOWN_OPEN map. axiom_oracles/ is not scanned at all: its
#: PolicyEngine pins (e.g. the bridges' "Run with: uv run --with
#: policyengine-core==..." hints) are remediation messages for a human, not
#: installs; the runtime installs live under scripts/ and comparisons/.
SKIP_FILES = {"scripts/check_pinned_artifacts.py"}
TAXSIM_PINS = "axiom_oracles/adapters/taxsim/taxsim_pins.json"


@dataclass(frozen=True)
class Use:
    path: str
    line: int | None = None

    def __str__(self) -> str:
        return f"{self.path}:{self.line}" if self.line else self.path


def _normalize(name: str) -> str:
    return name.lower().replace("_", "-")


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _label_lines(rel: str, text: str) -> set[int]:
    """Line numbers inside this file's LABEL_SCOPES."""
    names = {name for (path, name) in LABEL_SCOPES if path == rel}
    if not names or not rel.endswith(".py"):
        return set()
    lines: set[int] = set()
    for node in ast.parse(text).body:
        targets = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            targets = [node.name]
        elif isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if names.intersection(targets):
            lines.update(range(node.lineno, node.end_lineno + 1))
    return lines


def _scan_text(rel: str, text: str, pins: dict, sources: dict, problems: list) -> None:
    skip = _label_lines(rel, text)

    def add(package: str, version: str, offset: int) -> None:
        line = _line_of(text, offset)
        if line not in skip:
            pins[(_normalize(package), version)].add(Use(rel, line))

    for match in _PIN.finditer(text):
        add(match.group(1), match.group(2), match.start())
    for match in _TUPLE_PIN.finditer(text):
        add(match.group(1), match.group(2), match.start())
    for match in _PARAM_DEFAULT.finditer(text):
        add(_PARAM_PACKAGE[match.group(1)], match.group(2), match.start())
    for match in _ORACLE_WITH_ARGS.finditer(text):
        add("policyengine-us", match.group(1), match.start())
    for match in _FSTRING_PIN.finditer(text):
        line = _line_of(text, match.start())
        if line in skip:
            continue
        expr = match.group(2).strip()
        default = _PARAM_DEFAULT.fullmatch(expr)
        if default:
            continue  # the parameter-default pattern above counted it
        if (rel, expr) in RESOLVED_ELSEWHERE:
            continue
        problems.append(
            f"{rel}:{line}: {match.group(1)}=={{{expr}}}: cannot resolve the "
            "version of this f-string pin; give it a literal or add it to "
            "RESOLVED_ELSEWHERE in scripts/check_pinned_artifacts.py"
        )
    for match in _ARCHIVE.finditer(text):
        line = _line_of(text, match.start())
        if line not in skip:
            sources[match.group(0)].add(Use(rel, line))


def _scan_scripts(pins: dict, sources: dict, problems: list) -> None:
    for path in sorted((REPO_ROOT / "scripts").rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in SKIP_FILES:
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue  # binary, not a script
        _scan_text(rel, text, pins, sources, problems)


def _walk_yaml(node, rel: str, pins: dict, sources: dict) -> None:
    if isinstance(node, dict):
        source = node.get("policyengine_us_source")
        if source:
            sources[str(source)].add(Use(rel))
        for key, value in node.items():
            package = _YAML_VERSION_KEYS.get(str(key))
            if package and not isinstance(value, (dict, list)) and value is not None:
                version = str(value)
                if _VERSION_VALUE.fullmatch(version):
                    if package == "policyengine-us" and source:
                        continue  # installed from the archive; a label
                    pins[(package, version)].add(Use(rel))
                    continue
            _walk_yaml(value, rel, pins, sources)
    elif isinstance(node, list):
        for item in node:
            _walk_yaml(item, rel, pins, sources)
    elif isinstance(node, str):
        for match in _PIN.finditer(node):
            pins[(_normalize(match.group(1)), match.group(2))].add(Use(rel))
        for match in _ARCHIVE.finditer(node):
            sources[match.group(0)].add(Use(rel))


def _scan_comparisons(pins: dict, sources: dict, problems: list) -> None:
    import yaml

    for path in sorted((REPO_ROOT / "comparisons").rglob("*.y*ml")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            document = yaml.safe_load(path.read_text())
        except yaml.YAMLError as exc:
            problems.append(f"{rel}: cannot parse, so its pins were not checked: {exc}")
            continue
        _walk_yaml(document, rel, pins, sources)


def scan() -> tuple[dict, dict, list[str]]:
    """``({(package, version): {Use}}, {archive_url: {Use}}, problems)``.

    ``problems`` lists what the scan could not read (an unparseable YAML
    file, an f-string version it cannot resolve); each one fails the check.
    """
    pins: dict = defaultdict(set)
    sources: dict = defaultdict(set)
    problems: list[str] = []
    _scan_scripts(pins, sources, problems)
    _scan_comparisons(pins, sources, problems)
    taxsim = json.loads((REPO_ROOT / TAXSIM_PINS).read_text())
    distribution = taxsim.get("distribution") or {}
    if distribution.get("version"):
        pins[(str(distribution["package"]), str(distribution["version"]))].add(
            Use(TAXSIM_PINS)
        )
    return pins, sources, problems


def inventory() -> tuple[dict, dict]:
    """``{(package, version): {Use}}`` and ``{archive_url: {Use}}``."""
    pins, sources, _problems = scan()
    return pins, sources


def _request(session, method: str, url: str, **kwargs):
    """``(status, error)`` for one request, retrying a 5xx or connection error.

    Returns the final HTTP status (None after a connection error) and the
    last connection error's text.
    """
    import requests

    attempts = len(pinned_artifacts.RETRY_DELAYS) + 1
    for attempt in range(attempts):
        try:
            response = getattr(session, method)(url, timeout=60, **kwargs)
        except requests.RequestException as exc:
            status, error, value = None, str(exc), None
        else:
            status, error, value = response.status_code, None, response
            if not pinned_artifacts.is_transient_status(status):
                return status, None, value
        if attempt + 1 < attempts:
            pinned_artifacts._sleep(pinned_artifacts.RETRY_DELAYS[attempt])
    return status, error, value


def _describe(status, error) -> str:
    attempts = len(pinned_artifacts.RETRY_DELAYS) + 1
    if status is None:
        return f"transient: connection failed on all {attempts} attempts ({error})"
    if pinned_artifacts.is_transient_status(status):
        return f"transient: HTTP {status} on all {attempts} attempts, not a removal"
    return f"HTTP {status}"


def check(*, verbose: bool = False) -> tuple[list[str], list[str]]:
    """``(failures, warnings)``. Warnings are KNOWN_OPEN breaks."""
    import requests

    failures: list[str] = []
    warnings: list[str] = []
    session = requests.Session()

    # 1. Every recorded file still downloads and matches its hash.
    with tempfile.TemporaryDirectory(prefix="pinned-artifacts.") as tmp:
        previous = os.environ.get(pinned_artifacts.CACHE_ENV)
        os.environ[pinned_artifacts.CACHE_ENV] = tmp
        try:
            for artifact in pinned_artifacts.PRUNED_ARTIFACTS:
                try:
                    pinned_artifacts.fetch(artifact)
                except pinned_artifacts.PinnedArtifactError as exc:
                    failures.append(
                        f"axiom_oracles/pinned_artifacts.py: "
                        f"{artifact.name}=={artifact.version}: [{exc.kind}] {exc}"
                    )
                else:
                    if verbose:
                        print(f"ok   {artifact.name}=={artifact.version} (hashed URL)")
        finally:
            if previous is None:
                os.environ.pop(pinned_artifacts.CACHE_ENV, None)
            else:
                os.environ[pinned_artifacts.CACHE_ENV] = previous

    # 2. Every pin is on the index or in the table.
    pins, sources, problems = scan()
    failures.extend(problems)
    listed: dict[str, set[str] | None] = {}
    for (package, version), uses in sorted(pins.items()):
        if pinned_artifacts.lookup(package, version) is not None:
            continue
        if package not in listed:
            status, error, response = _request(
                session,
                "get",
                f"https://pypi.org/simple/{package}/",
                headers={"Accept": "application/vnd.pypi.simple.v1+json"},
            )
            if status == 200:
                listed[package] = set(response.json().get("versions") or [])
            else:
                listed[package] = None
                failures.append(
                    f"{package}: cannot read PyPI's index: {_describe(status, error)}"
                )
        if listed[package] is None:
            continue
        if version in listed[package]:
            if verbose:
                print(f"ok   {package}=={version} (PyPI index)")
            continue
        issue = KNOWN_OPEN.get((package, version))
        for use in sorted(uses, key=str):
            message = (
                f"{use}: {package}=={version}: PyPI's index no longer lists "
                "it and axiom_oracles/pinned_artifacts.py has no hashed URL "
                "for it"
            )
            if issue:
                warnings.append(f"{message} (known open: {issue})")
            else:
                failures.append(message)

    # 3. Every commit archive downloads.
    for url, uses in sorted(sources.items()):
        status, error, _response = _request(session, "head", url, allow_redirects=True)
        if status == 200:
            if verbose:
                print(f"ok   {url}")
            continue
        issue = KNOWN_OPEN_SOURCES.get(url)
        for use in sorted(uses, key=str):
            message = f"{use}: policyengine-us archive {url}: {_describe(status, error)}"
            if issue:
                warnings.append(f"{message} (known open: {issue})")
            else:
                failures.append(message)
    return failures, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--list", action="store_true", help="print the pin inventory and exit"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    if args.list:
        pins, sources, problems = scan()
        for (package, version), uses in sorted(pins.items()):
            table = " [hashed URL]" if pinned_artifacts.lookup(package, version) else ""
            print(f"{package}=={version}{table}: {len(uses)} use(s)")
            for use in sorted(uses, key=str):
                print(f"    {use}")
        for url, uses in sorted(sources.items()):
            print(f"archive {url}: {', '.join(sorted(map(str, uses)))}")
        for problem in problems:
            print(f"PROBLEM {problem}")
        return 1 if problems else 0
    failures, warnings = check(verbose=args.verbose)
    for warning in warnings:
        print(f"WARN {warning}")
    for failure in failures:
        print(f"FAIL {failure}")
    if failures:
        print(f"{len(failures)} pinned artifact(s) will not install", file=sys.stderr)
        return 1
    print(
        "every pinned PolicyEngine artifact installs"
        + (f" ({len(warnings)} known-open warning(s))" if warnings else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
