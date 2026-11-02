#!/usr/bin/env python3
"""Fail, naming the file, when a pinned PolicyEngine artifact stops installing.

PolicyEngine prunes old releases from PyPI's index. A comparison whose pin is
pruned fails at install time ("there is no version of policyengine-us==...")
and its report on oracle-data stops refreshing. This check runs on a schedule
so the break shows up here first, with the file to fix:

1. Every file in ``axiom_oracles/pinned_artifacts.py`` downloads from its
   hashed URL and matches its recorded SHA-256.
2. Every exact PolicyEngine-family pin a runtime install path names is either
   listed on PyPI's index or recoverable from that table. The pins come from
   ``comparisons/*.yaml`` runner parameters, the literal pins and parameter
   defaults in ``scripts/run_comparison.py``, ``scripts/debug_policyengine_env.py``,
   the manual ``scripts/probe_*.py`` recipes, and the TAXSIM pin file.
3. Every ``policyengine_us_source`` archive a suite installs downloads.

Exit status 1 lists each failure as ``<file>[:line]: <pin>: <reason>``.

    python3 scripts/check_pinned_artifacts.py            # all three checks
    python3 scripts/check_pinned_artifacts.py --list     # print the inventory
"""

from __future__ import annotations

import argparse
import json
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

PACKAGES = (
    "policyengine",
    "policyengine-us",
    "policyengine-core",
    "policyengine-uk",
    "policyengine-taxsim",
    "spm-calculator",
)
_PARAM_PACKAGE = {
    "policyengine_version": "policyengine",
    "policyengine_us_version": "policyengine-us",
    "policyengine_core_version": "policyengine-core",
    "policyengine_uk_version": "policyengine-uk",
}
_NAME = "|".join(re.escape(name) for name in sorted(PACKAGES, key=len, reverse=True))
_LITERAL_PIN = re.compile(rf"(?<![\w-])({_NAME})==([0-9]+(?:\.[0-9]+)*)(?![\w.])")
_PARAM_DEFAULT = re.compile(
    r"""params\.get\(\s*["'](policyengine(?:_us|_core|_uk)?_version)["']\s*,"""
    r"""\s*["']([0-9]+(?:\.[0-9]+)*)["']"""
)
# Files whose pins are installed at run time (or, for the probes, by the
# command their docstring gives). Report provenance labels such as
# scripts/backfill_report_provenance.py are not installs and are not read.
CODE_SOURCES = (
    "scripts/run_comparison.py",
    "scripts/debug_policyengine_env.py",
)
PROBE_GLOB = "scripts/probe_*.py"
TAXSIM_PINS = "axiom_oracles/adapters/taxsim/taxsim_pins.json"


@dataclass(frozen=True)
class Use:
    path: str
    line: int | None = None

    def __str__(self) -> str:
        return f"{self.path}:{self.line}" if self.line else self.path


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _scan_code(rel: str, inventory: dict) -> None:
    text = (REPO_ROOT / rel).read_text()
    for match in _LITERAL_PIN.finditer(text):
        inventory[(match.group(1), match.group(2))].add(
            Use(rel, _line_of(text, match.start()))
        )
    for match in _PARAM_DEFAULT.finditer(text):
        package = _PARAM_PACKAGE[match.group(1)]
        inventory[(package, match.group(2))].add(
            Use(rel, _line_of(text, match.start()))
        )


def _scan_comparisons(inventory: dict, sources: dict) -> None:
    import yaml

    for path in sorted((REPO_ROOT / "comparisons").glob("*.yaml")):
        rel = str(path.relative_to(REPO_ROOT))
        try:
            config = yaml.safe_load(path.read_text())
        except yaml.YAMLError:
            continue
        if not isinstance(config, dict):
            continue
        params = ((config.get("runner") or {}).get("parameters")) or {}
        if not isinstance(params, dict):
            continue
        source = params.get("policyengine_us_source")
        if source:
            sources[str(source)].add(Use(rel))
        for key, package in _PARAM_PACKAGE.items():
            value = params.get(key)
            if value is None:
                continue
            if package == "policyengine-us" and source:
                # Installed from the commit archive; the version is its label.
                continue
            inventory[(package, str(value))].add(Use(rel))


def inventory() -> tuple[dict, dict]:
    """``{(package, version): {Use}}`` and ``{source_url: {Use}}``."""
    pins: dict = defaultdict(set)
    sources: dict = defaultdict(set)
    for rel in CODE_SOURCES:
        _scan_code(rel, pins)
    for path in sorted(REPO_ROOT.glob(PROBE_GLOB)):
        _scan_code(str(path.relative_to(REPO_ROOT)), pins)
    _scan_comparisons(pins, sources)
    taxsim = json.loads((REPO_ROOT / TAXSIM_PINS).read_text())
    distribution = taxsim.get("distribution") or {}
    if distribution.get("version"):
        pins[(str(distribution["package"]), str(distribution["version"]))].add(
            Use(TAXSIM_PINS)
        )
    return pins, sources


def _index_versions(package: str, session) -> set[str]:
    response = session.get(
        f"https://pypi.org/simple/{package}/",
        headers={"Accept": "application/vnd.pypi.simple.v1+json"},
        timeout=60,
    )
    response.raise_for_status()
    return set(response.json().get("versions") or [])


def check(*, verbose: bool = False) -> list[str]:
    import requests

    failures: list[str] = []
    session = requests.Session()

    # 1. Every recorded file still downloads and matches its hash.
    with tempfile.TemporaryDirectory(prefix="pinned-artifacts.") as tmp:
        import os

        previous = os.environ.get(pinned_artifacts.CACHE_ENV)
        os.environ[pinned_artifacts.CACHE_ENV] = tmp
        try:
            for artifact in pinned_artifacts.PRUNED_ARTIFACTS:
                try:
                    pinned_artifacts.fetch(artifact)
                except pinned_artifacts.PinnedArtifactError as exc:
                    failures.append(
                        f"axiom_oracles/pinned_artifacts.py: "
                        f"{artifact.name}=={artifact.version}: {exc}"
                    )
                else:
                    if verbose:
                        print(f"ok   {artifact.name}=={artifact.version} (hashed URL)")
        finally:
            if previous is None:
                os.environ.pop(pinned_artifacts.CACHE_ENV, None)
            else:
                os.environ[pinned_artifacts.CACHE_ENV] = previous

    # 2. Every runtime pin is on the index or in the table.
    pins, sources = inventory()
    listed: dict[str, set[str]] = {}
    for (package, version), uses in sorted(pins.items()):
        if pinned_artifacts.lookup(package, version) is not None:
            continue
        if package not in listed:
            try:
                listed[package] = _index_versions(package, session)
            except requests.RequestException as exc:
                failures.append(f"{package}: cannot read PyPI's index: {exc}")
                listed[package] = set()
                continue
        if version in listed[package]:
            if verbose:
                print(f"ok   {package}=={version} (PyPI index)")
            continue
        for use in sorted(uses, key=str):
            failures.append(
                f"{use}: {package}=={version}: PyPI's index no longer lists "
                "it and axiom_oracles/pinned_artifacts.py has no hashed URL "
                "for it"
            )

    # 3. Every commit archive a suite installs downloads.
    for url, uses in sorted(sources.items()):
        try:
            response = session.head(url, allow_redirects=True, timeout=60)
            status = response.status_code
        except requests.RequestException as exc:
            status = f"error ({exc})"
        if status != 200:
            for use in sorted(uses, key=str):
                failures.append(
                    f"{use}: policyengine_us_source {url}: HTTP {status}"
                )
        elif verbose:
            print(f"ok   {url}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--list", action="store_true", help="print the pin inventory and exit"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    if args.list:
        pins, sources = inventory()
        for (package, version), uses in sorted(pins.items()):
            table = " [hashed URL]" if pinned_artifacts.lookup(package, version) else ""
            print(f"{package}=={version}{table}: {len(uses)} use(s)")
            for use in sorted(uses, key=str):
                print(f"    {use}")
        for url, uses in sorted(sources.items()):
            print(f"source {url}: {', '.join(sorted(map(str, uses)))}")
        return 0
    failures = check(verbose=args.verbose)
    for failure in failures:
        print(f"FAIL {failure}")
    if failures:
        print(f"{len(failures)} pinned artifact(s) will not install", file=sys.stderr)
        return 1
    print("every pinned PolicyEngine artifact installs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
