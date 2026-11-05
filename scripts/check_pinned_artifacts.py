#!/usr/bin/env python3
"""Fail, naming the file, when a pinned PolicyEngine artifact stops installing.

PolicyEngine prunes old releases from PyPI's index. A comparison whose pin is
pruned fails at install time ("there is no version of policyengine-us==...")
and its report on oracle-data stops refreshing. This check runs on a schedule
so the break shows up here first, with the file to fix:

1. Every file in ``axiom_oracles/pinned_artifacts.py`` downloads from its
   hashed URL and matches its recorded SHA-256.
2. Every exact PolicyEngine-family pin is either listed on PyPI's index or
   recoverable from that table. The pins come from every file under
   ``scripts/``, ``ops/`` and ``.github/workflows/``, every
   ``comparisons/**/*.yaml`` (version keys at any depth), and the TAXSIM pin
   file. Names compare as PEP 503 does; ``==`` and ``===``, spaced and tuple
   spellings, parameter defaults and ``--oracle-with-args`` recipes are read.
   The scan fails closed on what it cannot read: an f-string version not in
   RESOLVED_ELSEWHERE, a non-literal policyengine-us version (concatenation,
   ``%``, ``$VER``), a policyengine-us wheel URL the table does not list, a
   label scope that runs a command, and an unparseable file.
3. Every ``policyengine-us`` commit archive a suite or script installs
   downloads.

A 5xx, 408 or 429, or a connection error, is retried twice with backoff and
reported as transient. A 404 or 410 means the file or release is gone; any
other 4xx (403, 401, ...) is reported as refused, at once. Breaks already
tracked in an issue (``KNOWN_OPEN``, keyed by the file that pins them) print
as warnings, so only a new break fails the run.

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

#: Unrecoverable pins and archives already tracked in an issue, keyed by the
#: file that pins them. They print as warnings; anything else that will not
#: install fails the run, including a new file adopting a known-open pin.
KNOWN_OPEN: dict[tuple[str, str, str], str] = {
    ("policyengine-us", "1.784.4", "comparisons/ri-income-tax-liability.yaml"): "#659",
}
KNOWN_OPEN_SOURCES: dict[tuple[str, str], str] = {}

# Package names as PEP 503 compares them: any case, and any run of "-", "_"
# or "." between the parts.
_NAMES = (
    r"(?i:policyengine(?:[-_.]+(?:us|core|uk|taxsim))?|spm[-_.]+calculator)"
)
_US = r"(?i:policyengine[-_.]+us)"
_VERSION = r"[0-9]+(?:\.[0-9]+)*"
_EQ = r"\s*={2,3}\s*"  # == and ===
_PIN = re.compile(rf"(?<![\w.-])({_NAMES}){_EQ}({_VERSION})(?!\w|\.[0-9])")
_TUPLE_PIN = re.compile(rf"""\(\s*["']({_NAMES})["']\s*,\s*["']({_VERSION})["']\s*\)""")
_FSTRING_PIN = re.compile(rf"(?<![\w.-])({_NAMES}){_EQ}\{{([^}}]*)\}}")
# A policyengine-us install whose version is not a literal the scan can read:
# string concatenation ("policyengine-us==" + v), % formatting, or a shell
# variable ($VER, ${VER}).
_UNREADABLE_US = re.compile(rf"(?<![\w.-])({_US}){_EQ}(?=[\"'%$])")
# A direct reference to a policyengine-us wheel; it must be a table row.
_US_WHEEL_URL = re.compile(
    rf"(?<![\w.-]){_US}\s*@\s*((?:https?|file)://[^\s\"'\]]+?\.whl)"
)
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

#: f-string versions this check resolves elsewhere, by file, enclosing
#: function and expression. Any other ``name=={expr}`` fails closed, in any
#: function of any file: the check cannot know its version.
RESOLVED_ELSEWHERE: dict[tuple[str, str, str], str] = {
    ("scripts/run_comparison.py", "_run_axiom_encode_tax_ecps_compare", "pe_meta"):
        "params.get default, scanned",
    ("scripts/run_comparison.py", "_run_axiom_encode_tax_ecps_compare", "pe_us"):
        "params.get default, scanned",
    ("scripts/run_comparison.py", "_run_axiom_encode_tax_ecps_compare", "pe_core"):
        "params.get default, scanned",
    ("scripts/run_comparison.py", "_resolve_pe_oracle_pins", "meta"):
        "comparison YAML parameters or _PE_ORACLE_PINS, both scanned",
    ("scripts/run_comparison.py", "_resolve_pe_oracle_pins", "us"):
        "comparison YAML parameters or _PE_ORACLE_PINS, both scanned",
    ("scripts/run_comparison.py", "_resolve_pe_oracle_pins", "core"):
        "comparison YAML parameters or _PE_ORACLE_PINS, both scanned",
    ("scripts/run_comparison.py", "_run_axiom_oracles_compare", "_taxsim_pin_version()"):
        "taxsim_pins.json, scanned",
    (
        "scripts/run_comparison.py",
        "_run_state_income_tax_liability_grid",
        "_taxsim_pin_version()",
    ): "taxsim_pins.json, scanned",
}
#: Top-level functions and assignments that only build report provenance
#: labels. They name versions but install nothing, so pins inside them are
#: not counted; the installs they describe are counted where they happen.
#: The scan fails if one of them gains a ``uv`` or ``subprocess`` call.
LABEL_SCOPES: dict[tuple[str, str], str] = {
    ("scripts/run_comparison.py", "_build_run_provenance"): "provenance.oracle labels",
    ("scripts/backfill_report_provenance.py", "_PE_ORACLE_PINS"): "backfilled labels",
    ("scripts/backfill_report_provenance.py", "_reconstruct_oracle"): "backfilled labels",
}
#: Trees whose every text file is scanned. axiom_oracles/ is not scanned: its
#: PolicyEngine pins (e.g. the bridges' "Run with: uv run --with
#: policyengine-core==..." hints) are remediation messages for a human, not
#: installs; the installs live in these trees and in comparisons/.
CODE_TREES = ("scripts", "ops", ".github/workflows")
#: This checker names example pins in its own KNOWN_OPEN map.
SKIP_FILES = {"scripts/check_pinned_artifacts.py"}
TAXSIM_PINS = "axiom_oracles/adapters/taxsim/taxsim_pins.json"


@dataclass(frozen=True)
class Use:
    path: str
    line: int | None = None

    def __str__(self) -> str:
        return f"{self.path}:{self.line}" if self.line else self.path


def _normalize(name: str) -> str:
    """PEP 503: lower case, and each run of ``-``, ``_`` or ``.`` becomes ``-``."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _is_install_call(node: ast.AST) -> bool:
    """A call that runs a command, or a string that starts a uv command."""
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id == "subprocess":
                return True
            if func.value.id == "os" and (
                func.attr == "system" or func.attr.startswith(("exec", "spawn"))
            ):
                return True
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        value = node.value.strip()
        return value == "uv" or value.startswith(("uv run", "uv pip", "uv sync"))
    return False


class _PythonLayout:
    """Label-scope lines and the enclosing function of each line of a file."""

    def __init__(self, rel: str, text: str, problems: list):
        self.label_lines: set[int] = set()
        self._functions: list[tuple[int, int, str]] = []
        if not rel.endswith(".py"):
            return
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            problems.append(
                f"{rel}:{exc.lineno}: cannot parse, so label scopes and "
                f"f-string pins in it could not be checked: {exc.msg}"
            )
            return
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._functions.append((node.lineno, node.end_lineno, node.name))
        names = {name for (path, name) in LABEL_SCOPES if path == rel}
        for node in tree.body:
            targets = []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                targets = [node.name]
            elif isinstance(node, ast.Assign):
                targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            scope = names.intersection(targets)
            if not scope:
                continue
            calls = [n for n in ast.walk(node) if _is_install_call(n)]
            if calls:
                problems.append(
                    f"{rel}:{calls[0].lineno}: label scope {sorted(scope)[0]} runs a "
                    "uv or subprocess command; pins in a label scope are not "
                    "counted, so it must install nothing (move the call out, or "
                    "drop the scope from LABEL_SCOPES)"
                )
                continue
            self.label_lines.update(range(node.lineno, node.end_lineno + 1))

    def function_at(self, line: int) -> str:
        enclosing = [f for f in self._functions if f[0] <= line <= f[1]]
        if not enclosing:
            return "<module>"
        return min(enclosing, key=lambda f: f[1] - f[0])[2]


def _scan_text(rel: str, text: str, pins: dict, sources: dict, problems: list) -> None:
    layout = _PythonLayout(rel, text, problems)
    skip = layout.label_lines

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
        if _PARAM_DEFAULT.fullmatch(expr):
            continue  # the parameter-default pattern above counted it
        if (rel, layout.function_at(line), expr) in RESOLVED_ELSEWHERE:
            continue
        problems.append(
            f"{rel}:{line}: {match.group(1)}=={{{expr}}} in "
            f"{layout.function_at(line)}: cannot resolve the version of this "
            "f-string pin; give it a literal or add it to RESOLVED_ELSEWHERE "
            "in scripts/check_pinned_artifacts.py"
        )
    for match in _UNREADABLE_US.finditer(text):
        line = _line_of(text, match.start())
        if line in skip:
            continue
        snippet = text[match.start() : match.end() + 12].splitlines()[0]
        problems.append(
            f"{rel}:{line}: {snippet!r}: a policyengine-us install whose version "
            "is not a literal (concatenation, % formatting or a shell variable); "
            "the scan cannot check it, so write the version literally"
        )
    table_urls = {artifact.url for artifact in pinned_artifacts.PRUNED_ARTIFACTS}
    for match in _US_WHEEL_URL.finditer(text):
        line = _line_of(text, match.start())
        url = match.group(1)
        if line in skip or url in table_urls:
            continue
        problems.append(
            f"{rel}:{line}: policyengine-us @ {url}: a direct URL to a wheel "
            "axiom_oracles/pinned_artifacts.py does not list, so nothing checks "
            "its SHA-256; add a table row and install it by version"
        )
    for match in _ARCHIVE.finditer(text):
        line = _line_of(text, match.start())
        if line not in skip:
            sources[match.group(0)].add(Use(rel, line))


def _scan_code_trees(pins: dict, sources: dict, problems: list) -> None:
    for tree in CODE_TREES:
        for path in sorted((REPO_ROOT / tree).rglob("*")):
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
    _scan_code_trees(pins, sources, problems)
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
    kind = pinned_artifacts.classify_status(status)
    if kind == "transient":
        return f"transient: HTTP {status} on all {attempts} attempts, not a removal"
    if kind == "refused":
        return f"refused: HTTP {status}, not retried and not by itself a removal"
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
        for use in sorted(uses, key=str):
            issue = KNOWN_OPEN.get((package, version, use.path))
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
        for use in sorted(uses, key=str):
            issue = KNOWN_OPEN_SOURCES.get((url, use.path))
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
