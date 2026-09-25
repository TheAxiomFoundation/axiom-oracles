"""One conservative unexplained-mismatch assessment for every consumer.

Counts are admitted without coercion. Invalid evidence is a hard defect; an
inconsistent declared unexplained signal can only raise the assessed count.
File validation is optional for offline consumers; certificates supply a root.
The dependency-free dashboard mirror is differential-tested against this module.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

CLASSIFIED_DISPOSITION_KINDS = (
    "explained_residual",
    "upstream_engine_gap",
    "bridge_artifact",
    "axiom_encoding_gap",
)
KNOWN_DISPOSITION_KINDS = (*CLASSIFIED_DISPOSITION_KINDS, "unexplained")


@dataclass(frozen=True)
class UnexplainedAssessment:
    count: int
    mode: Literal["file", "inline", "none"]
    mismatch_count: int
    declared: int | None
    classified: int
    known_cause_covered: int
    axiom_attributed: int
    defects: tuple[str, ...]
    notes: tuple[str, ...]


def admit_count(value: object) -> int | None:
    """Admit only nonnegative integers and finite integral floats, never bools."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, float) and math.isfinite(value) and value.is_integer() and value >= 0:
        return int(value)
    return None


def count_defect(value: object, field: str, suite: str) -> str:
    """Keep the certificate's established count diagnostics."""
    if isinstance(value, bool):
        return f"{suite}: {field} is a boolean, not a count"
    if isinstance(value, int) and value < 0 or (
        isinstance(value, float) and math.isfinite(value) and value.is_integer() and value < 0
    ):
        return f"{suite}: {field} is negative ({int(value)})"
    return f"{suite}: {field} is not a non-negative integer ({value!r})"


def load_known_causes(repo_root: Path | None = None) -> list[dict]:
    root = repo_root if repo_root is not None else Path(__file__).resolve().parents[2]
    path = root / "dashboard/public/data/known_causes.json"
    if not path.exists():
        return []
    return json.loads(path.read_text()).get("entries") or []


def is_open_rulespec_issue(url: object) -> bool:
    """Offline attribution conservatively treats linked rulespec issues as open."""
    lowered = str(url).lower()
    return "/rulespec-" in lowered and "/issues/" in lowered


def cause_for(known_causes, report: dict, concept: str, kind: str, suite: str):
    """Prefer an exact engine-pair label; otherwise use an engine-less label."""
    engines = report.get("engines") or {}
    candidates = [
        cause for cause in known_causes
        if cause.get("suite") == suite
        and cause.get("concept") == concept
        and cause.get("kind") == kind
    ]
    for cause in candidates:
        pair = cause.get("engines")
        if pair and pair.get("left") == engines.get("left") and pair.get("right") == engines.get("right"):
            return cause
    return next((cause for cause in candidates if not cause.get("engines")), None)


def _file_defect(filename: str, suite: str, aliases: set[str], repo_root: Path) -> str | None:
    # Lazy import: the dispositions producer itself uses admit_count.
    import yaml

    from axiom_oracles.comparison.dispositions import validate_dispositions

    relative = Path(filename)
    path = repo_root / relative
    if relative.is_absolute() or ".." in relative.parts or not path.resolve().is_relative_to(repo_root.resolve()):
        return f"{suite}: dispositions_file {filename!r} is not a repository-relative path"
    if not path.is_file():
        return f"{suite}: dispositions_file {filename!r} does not exist in the repository"
    try:
        payload = yaml.safe_load(path.read_text())
    except (OSError, UnicodeError, yaml.YAMLError):
        payload = None
    errors = validate_dispositions(payload, path_label=filename, repo_root=repo_root)
    if errors:
        return f"{suite}: {filename} is not a readable dispositions document declaring a suite"
    if payload["suite"] not in aliases:
        return f"{suite}: {filename} declares suite {payload['suite']!r}, which is not this suite"
    return None


def assess_unexplained(
    report: dict,
    *,
    known_causes=(),
    summary=None,
    rows=None,
    suite=None,
    repo_root: Path | None = None,
) -> UnexplainedAssessment:
    """Assess raw report evidence, before dashboard concept filtering.

    A suite entry mapping may supply a canonical ``suite`` and ``aliases`` for
    certificate file validation. Explicit summary/row overrides scope a view.
    """
    if isinstance(suite, dict):
        aliases = set(suite.get("aliases") or ())
        suite = suite.get("suite")
    else:
        aliases = set()
    suite = suite if suite is not None else report.get("suite", "<unknown>")
    aliases.add(suite)
    defects: list[str] = []
    notes: list[str] = []
    if summary is None:
        summary = report.get("summary", {})
    if not isinstance(summary, dict):
        defects.append(f"{suite}: summary must be an object")
        summary = {}
    if rows is None:
        rows = report.get("mismatches", [])
    if not isinstance(rows, list):
        defects.append(f"{suite}: mismatches must be an array")
        rows = []

    def read(value, field):
        admitted = admit_count(value)
        if admitted is None:
            defects.append(count_defect(value, field, suite))
        return admitted

    mismatch = len(rows)
    if "mismatch_count" in summary:
        admitted = read(summary["mismatch_count"], "mismatch_count")
        if admitted is not None:
            mismatch = admitted
    if len(rows) > mismatch:
        # Listed rows are evidence. A total below them understates the
        # report (a row with mismatch_count 0 read as 0 in every consumer).
        defects.append(
            f"{suite}: {len(rows)} mismatch rows are listed but mismatch_count "
            f"is {mismatch}"
        )
        mismatch = len(rows)
    block = summary.get("dispositioned")
    if block is None:
        block = {}
    elif not isinstance(block, dict):
        defects.append(f"{suite}: dispositioned must be an object")
        block = {}
    counts = block.get("counts", {})
    if not isinstance(counts, dict):
        defects.append(f"{suite}: disposition counts must be an object")
        counts = {}
    unknown = set(counts) - set(KNOWN_DISPOSITION_KINDS)
    if unknown:
        defects.append(
            f"{suite}: unknown disposition kind(s) {sorted(unknown)} — only "
            f"{sorted(KNOWN_DISPOSITION_KINDS)} carry defined meaning"
        )
    admitted_counts = {
        kind: read(value, f"counts.{kind}") for kind, value in sorted(counts.items())
    }
    classified = sum(admitted_counts.get(kind) or 0 for kind in CLASSIFIED_DISPOSITION_KINDS)
    signals = []
    if "unexplained_count" in block:
        signal = read(block["unexplained_count"], "unexplained_count")
        if signal is not None:
            signals.append(signal)
    if admitted_counts.get("unexplained") is not None:
        signals.append(admitted_counts["unexplained"])
    declared = max(signals) if signals else None
    if len(set(signals)) > 1:
        notes.append("declared unexplained counts disagree; using the maximum")
    filename = block.get("dispositions_file")
    if filename is not None and filename != "" and not isinstance(filename, str):
        defects.append(f"{suite}: dispositions_file must be a repository-relative string")
    mode = "file" if isinstance(filename, str) and filename else "inline" if classified > 0 else "none"
    covered = 0
    axiom = 0
    if mode in ("file", "inline"):
        count = max(declared or 0, mismatch - classified)
        axiom = admitted_counts.get("axiom_encoding_gap") or 0
        for row in rows:
            disposition = row.get("disposition") if isinstance(row, dict) else None
            if isinstance(disposition, dict) and disposition.get("disposition") != "axiom_encoding_gap" and is_open_rulespec_issue(disposition.get("linked_issue")):
                axiom += 1
        if classified + (declared or 0) != mismatch:
            notes.append("disposition counts do not conserve against mismatches; using the conservative maximum")
        if mode == "inline":
            notes.append("inline classification is producer-declared, not file-validated")
        elif repo_root is not None:
            defect = _file_defect(filename, suite, aliases, Path(repo_root))
            if defect:
                defects.append(defect)
                count = max(mismatch, declared or 0)
    else:
        for row in rows:
            if not isinstance(row, dict):
                defects.append(f"{suite}: mismatch row must be an object")
                continue
            if "disposition" in row or not row.get("concept"):
                continue
            cause = cause_for(known_causes, report, row["concept"], row.get("kind"), suite)
            if cause is not None:
                covered += 1
                owner = cause.get("fix_owner") or ""
                if str(owner).startswith("rulespec") or owner == "axiom-encode" or is_open_rulespec_issue(cause.get("issue_url")):
                    axiom += 1
        if covered > mismatch:
            defects.append(f"{suite}: known-cause covered rows ({covered}) exceed mismatches ({mismatch})")
            count = mismatch
        else:
            count = mismatch - covered
        # Even a block with no explanatory classes cannot erase a declared
        # unexplained signal (including when a mutation removes its last class).
        count = max(count, declared or 0)
    return UnexplainedAssessment(
        count, mode, mismatch, declared, classified, covered, axiom,
        tuple(defects), tuple(notes),
    )


def resolve_suite_reports(reports, *, known_causes=(), repo_root=None) -> dict[str, dict]:
    """Select the maximum unexplained count per suite, independent of input order.

    Consumers must inspect all reports for defects and contested coverage. This
    resolver only selects the numerical signal, using canonical JSON for ties.
    """
    index = {}
    ranks = {}
    for report in reports:
        suite = report.get("suite")
        if not suite:
            continue
        assessment = assess_unexplained(report, known_causes=known_causes, repo_root=repo_root)
        rank = (assessment.count, json.dumps(report, sort_keys=True, default=str))
        if suite not in ranks or rank > ranks[suite]:
            ranks[suite] = rank
            index[suite] = report
    return index
