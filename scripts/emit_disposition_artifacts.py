"""Emit per-suite disposition artifacts for the dashboard.

The dispositions/<suite>.yaml files carry the prose explanation for every
triaged mismatch (evidence.mechanism, the linked upstream issue, the
category). The comparison reports only stamp each mismatch with the entry
id — so the dashboard could say "dispositioned" but never say WHY. This
script ships the explanations: dashboard/public/data/dispositions/
<suite>.json, one compact entry per disposition.

Usage:
    uv run scripts/emit_disposition_artifacts.py
    uv run scripts/emit_disposition_artifacts.py <suite>...
    uv run scripts/emit_disposition_artifacts.py --check <suite>...
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DISPOSITIONS = ROOT / "dispositions"
OUT = ROOT / "dashboard" / "public" / "data" / "dispositions"
SUITE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def compact_entry(entry: dict) -> dict:
    evidence = entry.get("evidence") or {}
    selector = entry.get("case_selector") or {}
    cases = selector.get("case_ids") or (
        [entry["case_id"]] if entry.get("case_id") else []
    )
    arithmetic = [
        {"expression": a.get("expression"), "equals": a.get("equals")}
        for a in evidence.get("arithmetic") or []
        if a.get("expression") is not None
    ]
    return {
        "id": entry.get("id"),
        "concept": entry.get("concept"),
        "kind": entry.get("kind"),
        "disposition": entry.get("disposition"),
        "mechanism": (evidence.get("mechanism") or "").strip() or None,
        "cases": cases,
        "arithmetic": arithmetic,
        "linked_issue": entry.get("linked_issue")
        or evidence.get("upstream_url"),
    }


def _selected_paths(suites: list[str]) -> tuple[list[Path], list[str]]:
    """Resolve requested suite slugs without allowing path traversal."""

    if not suites:
        paths = sorted(DISPOSITIONS.glob("*.yaml"))
        if not paths:
            return [], [f"no disposition YAML files found under {DISPOSITIONS}"]
        return paths, []

    paths: list[Path] = []
    problems: list[str] = []
    for suite in dict.fromkeys(suites):
        if not SUITE_RE.fullmatch(suite):
            problems.append(f"invalid suite slug {suite!r}")
            continue
        path = DISPOSITIONS / f"{suite}.yaml"
        if not path.is_file():
            problems.append(f"{suite}: no dispositions/{suite}.yaml")
            continue
        paths.append(path)
    return paths, problems


def _render_artifact(path: Path) -> tuple[str, str, int]:
    """Return (suite, exact JSON text, entry count) for one YAML source."""

    try:
        doc = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"{path.name}: cannot load YAML: {exc}") from exc
    if not isinstance(doc, dict):
        raise ValueError(f"{path.name}: YAML root must be a mapping")

    suite = doc.get("suite") or path.stem
    if not isinstance(suite, str) or not SUITE_RE.fullmatch(suite):
        raise ValueError(f"{path.name}: invalid suite value {suite!r}")
    if suite != path.stem:
        raise ValueError(
            f"{path.name}: declares suite {suite!r}, expected {path.stem!r}"
        )

    raw_entries = doc.get("entries") or []
    if not isinstance(raw_entries, list):
        raise ValueError(f"{path.name}: entries must be a list")
    entries = []
    for index, entry in enumerate(raw_entries):
        if not isinstance(entry, dict):
            raise ValueError(
                f"{path.name}: entries[{index}] must be a mapping"
            )
        try:
            entries.append(compact_entry(entry))
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"{path.name}: cannot compact entries[{index}]: {exc}"
            ) from exc

    payload = {
        "suite": suite,
        "updated": doc.get("updated"),
        "entries": entries,
    }
    try:
        text = json.dumps(payload, indent=1) + "\n"
    except TypeError as exc:
        raise ValueError(
            f"{path.name}: artifact contains a non-JSON value: {exc}"
        ) from exc
    return suite, text, len(entries)


def _expected_artifacts(
    paths: list[Path],
) -> tuple[list[tuple[str, str, int]], list[str]]:
    artifacts: list[tuple[str, str, int]] = []
    problems: list[str] = []
    seen: dict[str, Path] = {}
    for path in paths:
        try:
            suite, text, entry_count = _render_artifact(path)
        except ValueError as exc:
            problems.append(str(exc))
            continue
        if suite in seen:
            problems.append(
                f"{suite}: duplicate suite in {seen[suite].name} and {path.name}"
            )
            continue
        seen[suite] = path
        artifacts.append((suite, text, entry_count))
    return artifacts, problems


def _report_problems(problems: list[str]) -> None:
    for problem in problems:
        print(f"disposition-artifacts FAILED: {problem}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Verify committed JSON is the exact generated form of the selected "
            "YAML without writing files."
        ),
    )
    parser.add_argument(
        "suite",
        nargs="*",
        help="Suite slug(s) to emit or check; defaults to every YAML source.",
    )
    args = parser.parse_args(argv)

    paths, problems = _selected_paths(args.suite)
    artifacts, render_problems = _expected_artifacts(paths)
    problems.extend(render_problems)
    if problems:
        _report_problems(problems)
        return 1

    if args.check:
        for suite, expected, _ in artifacts:
            target = OUT / f"{suite}.json"
            try:
                actual = target.read_text()
            except FileNotFoundError:
                problems.append(f"{suite}: {target} is missing")
                continue
            except OSError as exc:
                problems.append(f"{suite}: cannot read {target}: {exc}")
                continue
            if actual != expected:
                problems.append(
                    f"{suite}: {target} is stale; rerun "
                    f"`uv run scripts/emit_disposition_artifacts.py {suite}`"
                )
        if problems:
            _report_problems(problems)
            return 1
        entries = sum(entry_count for _, _, entry_count in artifacts)
        print(
            f"disposition-artifacts OK: {len(artifacts)} suites, "
            f"{entries} entries, exact YAML parity"
        )
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    for suite, text, _ in artifacts:
        (OUT / f"{suite}.json").write_text(text)
    print(f"emitted {len(artifacts)} disposition artifacts -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
