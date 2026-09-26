"""Read JSON reports and deterministic, compact gzip report artifacts."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

import yaml


def read_report_text(path: Path) -> str:
    payload = path.read_bytes()
    if path.suffix == ".gz":
        payload = gzip.decompress(payload)
    return payload.decode("utf-8")


def load_report(path: Path) -> dict[str, Any]:
    report = json.loads(read_report_text(path))
    if not isinstance(report, dict):
        raise ValueError(f"{path}: report must be a JSON object")
    return report


def write_report_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = text.encode("utf-8")
    if path.suffix == ".gz":
        payload = gzip.compress(payload, mtime=0)
    path.write_bytes(payload)


def write_report(path: Path, report: dict[str, Any]) -> None:
    compact = path.suffix == ".gz"
    text = json.dumps(
        report, sort_keys=True, allow_nan=False,
        separators=(",", ":") if compact else None,
        indent=None if compact else 2,
    ) + "\n"
    write_report_text(path, text)


def registered_report_paths(repo_root: Path, *, suites: set[str] | None = None) -> list[Path]:
    """Explicit report artifacts, including manual lanes outside the dashboard.

    Archive reports are deliberately not swept: a suite opts in through
    ``artifacts.report_path``. Paths must remain inside the repository.
    """

    paths: set[Path] = set()
    root = repo_root.resolve()
    for suite_path in sorted((root / "comparisons").glob("*.yaml")):
        doc = yaml.safe_load(suite_path.read_text()) or {}
        if suites is not None and doc.get("name", suite_path.stem) not in suites:
            continue
        artifacts = doc.get("artifacts") or {}
        raw = artifacts.get("report_path")
        if raw is None:
            continue
        if not isinstance(raw, str) or Path(raw).is_absolute():
            raise ValueError(f"{suite_path}: artifacts.report_path must be repo-relative")
        path = (root / raw).resolve()
        if root not in path.parents:
            raise ValueError(f"{suite_path}: artifacts.report_path must stay inside the repository")
        if not (path.name.endswith(".json") or path.name.endswith(".json.gz")):
            raise ValueError(f"{suite_path}: artifacts.report_path must end in .json or .json.gz")
        paths.add(path)
    return sorted(paths)


def unpublished_registered_suites(repo_root: Path) -> set[str]:
    """Explicit ledger artifacts require a dashboard target before publishing.

    Legacy suites without ``artifacts.report_path`` keep their existing
    publishing behavior. ``ci: manual`` alone is not a publishing decision:
    several legacy manual suites are already on the dashboard.
    """

    suites: set[str] = set()
    for path in sorted((repo_root / "comparisons").glob("*.yaml")):
        doc = yaml.safe_load(path.read_text()) or {}
        if (doc.get("artifacts") or {}).get("report_path") and not (
            doc.get("dashboard") or {}
        ).get("filename"):
            suites.add(doc.get("name", path.stem))
    return suites
