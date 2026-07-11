#!/usr/bin/env python3
"""Backfill provenance blocks onto committed dashboard reports (O2).

New comparison runs get a ``provenance`` block from ``run_comparison.py``. The
reports already committed to ``dashboard/public/data/`` predate that, so this
one-shot-but-idempotent stamper reconstructs an honest provenance block for
each of them:

* ``generated_at`` is the report file's **git commit date** — its real age in
  version control, not a fabricated "now" (an invented timestamp would defeat
  the freshness gate it feeds).
* ``rulespecs`` come from the committed affected-map (``sha: null`` — the exact
  historical rules SHA is not recoverable from the report alone; the affected-
  rerun workflow treats a null SHA as "stale, needs a real run", which is the
  safe default).
* ``engine`` / ``oracle`` are reconstructed from the matching comparison config
  (the pinned stack each runner installs), when one exists.
* ``dataset`` reuses any ``dataset_identity`` the report already carries.

Every backfilled block is flagged ``backfilled: true`` so it is never mistaken
for a real fresh run. Reports that already carry a ``provenance`` block are left
untouched, so re-running is a no-op and a real run's stamp always wins.

Usage:
    uv run scripts/backfill_report_provenance.py            # stamp in place
    uv run scripts/backfill_report_provenance.py --check    # CI: fail on drift
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.stderr.write("PyYAML is required (uv pip install pyyaml).\n")
    sys.exit(2)

from axiom_oracles.provenance import (  # noqa: E402
    PROVENANCE_SCHEMA_VERSION,
    dataset_provenance_from_identity,
)

DASHBOARD_DATA_DIR = REPO_ROOT / "dashboard" / "public" / "data"
COMPARISONS_DIR = REPO_ROOT / "comparisons"
AFFECTED_MAP = COMPARISONS_DIR / "affected_map.json"

_PE_ORACLE_PINS = (
    "policyengine==4.11.0",
    "policyengine-us==1.700.0",
    "policyengine-core==3.26.11",
)


def _git_commit_date(path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "log", "-1", "--format=%cI", "--", str(path)],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
    iso = result.stdout.strip()
    if not iso:
        return None
    # Normalize `2026-06-02T00:00:40-04:00` → UTC `…Z` to match run_comparison.
    from datetime import datetime, timezone

    try:
        when = datetime.fromisoformat(iso).astimezone(timezone.utc)
    except ValueError:
        return None
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _affected_repos_by_suite() -> dict[str, list[str]]:
    if not AFFECTED_MAP.exists():
        return {}
    try:
        data = json.loads(AFFECTED_MAP.read_text())
    except json.JSONDecodeError:
        return {}
    return {e["suite"]: e.get("repos", []) for e in data.get("suites", [])}


def _config_by_suite() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in sorted(COMPARISONS_DIR.glob("*.yaml")):
        if path.name.endswith(".fixtures.yaml"):
            continue
        config = yaml.safe_load(path.read_text())
        if not isinstance(config, dict):
            continue
        if config.get("kind") == "parameter-suite-list":
            for suite in config.get("suites") or []:
                out[suite["suite"]] = {"_parameter_suite": True}
            continue
        suite = (config.get("dashboard") or {}).get("suite", config.get("name"))
        if suite:
            out[suite] = config
    return out


def _reconstruct_oracle(config: dict) -> dict:
    if config.get("_parameter_suite"):
        return {"name": "policyengine", "source": "repo-venv-parameters"}
    runner = config.get("runner") or {}
    params = runner.get("parameters") or {}
    rtype = runner.get("type")
    if rtype == "axiom-encode-tax-populace-compare":
        return {"name": "policyengine", "policyengine_package": "policyengine==4.11.0"}
    if rtype == "axiom-encode-uk-populace-compare":
        return {
            "name": "policyengine",
            "policyengine_uk": params.get("policyengine_uk_version", "2.88.56"),
        }
    if rtype == "axiom-oracles-compare":
        return {
            "name": params.get("right", "policyengine"),
            "policyengine_package": _PE_ORACLE_PINS[0],
            # Emit the pinned PE-US version too, so all three tuple entries are
            # actually used and a future pin bump here isn't silently inert.
            "policyengine_us": _PE_ORACLE_PINS[1].split("==", 1)[-1],
        }
    if rtype == "axiom-encode-snap-populace-compare":
        return {"name": "policyengine", "policyengine_us": "1.705.1"}
    # Committed EUROMOD reports have no run_comparison config; infer from suite.
    return {}


def build_backfill_block(path: Path, report: dict, *, repos, config) -> dict:
    generated_at = _git_commit_date(path) or "1970-01-01T00:00:00Z"
    rulespecs = [{"repo": r, "sha": None} for r in repos]
    oracle: dict = {}
    engines = report.get("engines") or {}
    other = engines.get("right") or engines.get("left")
    if config is not None:
        oracle = _reconstruct_oracle(config)
    if not oracle and other:
        oracle = {"name": other}
    dataset = dataset_provenance_from_identity(report.get("dataset_identity"))
    if dataset is None and report.get("population"):
        dataset = {"source": "report", "population": str(report["population"])}

    block: dict = {
        "schema": PROVENANCE_SCHEMA_VERSION,
        "generated_at": generated_at,
        "generated_by": "scripts/backfill_report_provenance.py",
        "run_kind": "manual",
        "backfilled": True,
    }
    if rulespecs:
        block["rulespecs"] = rulespecs
    if oracle:
        block["oracle"] = oracle
    if dataset:
        block["dataset"] = dataset
    return block


def _serialize_like(original_text: str, report: dict) -> str:
    """Rewrite `report` in the same on-disk format the file already uses."""
    original = json.loads(original_text)
    for sort_keys in (True, False):
        for indent in (2, 1):
            candidate = json.dumps(original, indent=indent, sort_keys=sort_keys)
            if original_text in (candidate, candidate + "\n"):
                text = json.dumps(report, indent=indent, sort_keys=sort_keys)
                return text + "\n" if original_text.endswith("\n") else text
    # Unknown formatting: default to indent=2 sorted with trailing newline.
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Fail on any missing stamp."
    )
    args = parser.parse_args()

    repos_by_suite = _affected_repos_by_suite()
    config_by_suite = _config_by_suite()

    stamped = 0
    missing: list[str] = []
    for path in sorted(DASHBOARD_DATA_DIR.glob("*.json")):
        try:
            report = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if not isinstance(report, dict) or not report.get("suite"):
            continue
        if isinstance(report.get("provenance"), dict):
            continue  # already stamped (real run or prior backfill)
        suite = report["suite"]
        block = build_backfill_block(
            path,
            report,
            repos=repos_by_suite.get(suite, []),
            config=config_by_suite.get(suite),
        )
        rel = path.relative_to(REPO_ROOT)
        if args.check:
            missing.append(str(rel))
            continue
        report["provenance"] = block
        original_text = path.read_text()
        path.write_text(_serialize_like(original_text, report))
        print(f"Stamped {rel} (generated_at={block['generated_at']})")
        stamped += 1

    if args.check:
        if missing:
            for rel in missing:
                sys.stderr.write(
                    f"backfill check FAILED: {rel} has no provenance block; run "
                    "`uv run scripts/backfill_report_provenance.py`\n"
                )
            return 1
        print("All committed dashboard reports carry a provenance block")
        return 0

    print(f"Backfilled provenance on {stamped} report(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
