"""PolicyEngine-attributed mismatches must carry their Axiom side.

Standard (Max, 2026-09-24): when a policy bug is found in PolicyEngine, the
same policy must be encoded correctly in Axiom too. In this repository a
PolicyEngine policy bug is recorded as a mismatch explanation that blames the
PolicyEngine leg of a comparison. This module makes the standard structural:

* It computes, from committed data rather than from names or prose, which
  explanations attribute a mismatch to PolicyEngine (:func:`collect_records`).
* It validates the two fields such an explanation must carry besides its
  PolicyEngine issue URL (:func:`validate_axiom_side_fields`):

  ``axiom_companion``
      ``{legal_ids: [...], tests: ["rulespec-us@<sha>:<path>.test.yaml#<case>"]}``
      — the Axiom legal id(s) asserted correct and a committed RuleSpec
      companion test case that exercises the disputed case.
  ``axiom_encoding_debt``
      ``https://github.com/TheAxiomFoundation/rulespec-<jur>/issues/<n>`` —
      the Axiom encoding (or its companion case) is owed and tracked; counted
      by the ratchet in ``conformance/pe-axiom-standard.yaml``.

* It keeps the ratchet (:func:`derive_ratchet`, :func:`check_records`,
  :func:`check_history`). Explanations that predate the standard are
  grandfathered with their status computed at freeze time. Across every
  committed version of the ratchet file the grandfathered set may only
  shrink, a grandfathered entry's recorded status may only rise, and
  ``open_max`` — PolicyEngine attributions without a companion (declared
  debt plus grandfathered) — may only fall. The one deliberate exception is
  an appended ``debt_raises`` record, which starts a new epoch and bounds
  it (``open_max`` <= the record's ``to``; its ``from`` <= the ceiling it
  replaces); the ``debt_raises`` list itself is append-only. Monotonicity is
  derived from
  Git history, as ``scripts/closure_universe.py`` derives its pending floor,
  so it bites on pull requests and on direct pushes alike and cannot be
  defeated by editing the ratchet file in the same change.
* Optionally it resolves each companion pointer against the RuleSpec
  repository (:class:`CompanionResolver`): the test file must exist at the
  pinned commit, that commit must be on the repository's main line, the named
  case must assert every declared legal id, and a case that shares the
  disputed case's id must assert the Axiom value the comparison produced.

Attribution rule (``upstream_engine_gap`` dispositions only — the one kind
that says the counterpart engine is wrong):

1. Rows: the committed dashboard report rows this entry annotates name their
   counterpart engine (``left_engine``/``right_engine``, a row ``engines``
   list, or the report's two-engine ``engines``). Any PolicyEngine
   counterpart makes the entry PolicyEngine-attributed.
2. Report: an entry that annotates no row (expired, or a sampled report) is
   attributed from the report's engine set when PolicyEngine is the only
   counterpart, or — in a multi-oracle report — when its mismatch ``kind``
   is a PolicyEngine-leg kind (``policyengine_amount_difference``).
3. URL: an entry whose ``linked_issue`` or ``evidence.upstream_url`` is a
   PolicyEngine GitHub issue or pull request is PolicyEngine-attributed
   whatever the rows say.

Known causes (``dashboard/public/data/known_causes.json``) are the second
place a mismatch bucket can be explained; a cause whose ``fix_owner`` starts
with ``policyengine`` or whose ``issue_url`` is a PolicyEngine issue is
PolicyEngine-attributed and carries the same two fields.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import re
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import yaml

RATCHET_SCHEMA = "axiom_oracles.pe_axiom_standard.v1"
RATCHET_RELATIVE_PATH = Path("conformance") / "pe-axiom-standard.yaml"
KNOWN_CAUSES_RELATIVE_PATH = (
    Path("dashboard") / "public" / "data" / "known_causes.json"
)
DISPOSITIONS_RELATIVE_DIR = Path("dispositions")
DASHBOARD_RELATIVE_DIR = Path("dashboard") / "public" / "data"
# Campaign-local ledger with its own schema (see scripts/apply_dispositions.py).
CAMPAIGN_LOCAL_DISPOSITIONS_FILES = frozenset({"us-tariff-schedule.yaml"})

UPSTREAM_ENGINE_GAP = "upstream_engine_gap"
AXIOM_ENGINE = "axiom"

PE_ISSUE_URL_RE = re.compile(
    r"^https://github\.com/PolicyEngine/[A-Za-z0-9._-]+/(?:issues|pull)/\d+/?$"
)
RULESPEC_ISSUE_URL_RE = re.compile(
    r"^https://github\.com/TheAxiomFoundation/rulespec-[a-z0-9-]+/issues/\d+/?$"
)
COMPANION_POINTER_RE = re.compile(
    r"^(?P<repo>rulespec-[a-z0-9-]+)@(?P<sha>[0-9a-f]{40}):"
    r"(?P<path>[^#\s]+\.test\.yaml)#(?P<case>\S(?:.*\S)?)$"
)
LEGAL_ID_RE = re.compile(
    r"^(?P<jurisdiction>[a-z]{2,3}(?:-[a-z0-9-]+)?):"
    r"(?P<path>[^#\s]+)#(?P<output>[^#\s]+)$"
)

_COMPANION_KEYS = {"legal_ids", "tests"}
AXIOM_SIDE_KEYS = ("axiom_companion", "axiom_encoding_debt")
_DOCUMENT_KEYS = {"schema", "_comment", "open_max", "debt_raises", "grandfathered"}
_RAISE_KEYS = {"date", "from", "to", "reason"}
_GRANDFATHERED_KEYS = {"source", "id", "concept", "basis", "pe_issue", "axiom"}

# Status ranks: a grandfathered entry may improve, never regress.
_PE_ISSUE_RANK = {"missing": 0, "present": 1}
_AXIOM_RANK = {"missing": 0, "debt": 1, "companion": 2}

_HEADER = (
    f"# {RATCHET_SCHEMA} — GENERATED; advance only via "
    "scripts/pe_axiom_standard.py.\n"
)
_COMMENT = (
    "PolicyEngine-attributed mismatch explanations and their Axiom side. "
    "Every explanation that blames PolicyEngine must link the PolicyEngine "
    "issue and declare axiom_companion (legal ids + a committed RuleSpec "
    "companion test case) or axiom_encoding_debt (a rulespec issue). "
    "Entries listed under grandfathered predate the standard; the list may "
    "only shrink. open_max counts attributions without a companion "
    "(declared debt + grandfathered) and may only fall, except through an "
    "appended debt_raises record (append-only). Monotonicity is checked "
    "against every committed version of this file. Re-pin with `uv run "
    "scripts/pe_axiom_standard.py` after an improvement."
)


# --------------------------------------------------------------------------
# Field syntax (shared with the dispositions schema validator)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CompanionPointer:
    """``rulespec-<jur>@<sha>:<path>.test.yaml#<case>``."""

    repo: str
    sha: str
    path: str
    case: str

    @classmethod
    def parse(cls, value: object) -> CompanionPointer | None:
        if not isinstance(value, str):
            return None
        match = COMPANION_POINTER_RE.match(value)
        if match is None:
            return None
        path = match.group("path")
        if path.startswith("/") or ".." in Path(path).parts:
            return None
        return cls(
            repo=match.group("repo"),
            sha=match.group("sha"),
            path=path,
            case=match.group("case"),
        )

    def __str__(self) -> str:
        return f"{self.repo}@{self.sha}:{self.path}#{self.case}"


def validate_axiom_side_fields(
    entry: Mapping,
    label: str,
    *,
    disposition_kind: str | None = None,
) -> list[str]:
    """Syntax of ``axiom_companion`` / ``axiom_encoding_debt`` on one entry.

    Used by the dispositions schema validator for every entry and by the
    standard gate for known causes. Presence rules (which entries MUST carry
    one) live in :func:`check_records`, because they depend on attribution.
    """

    errors: list[str] = []
    companion = entry.get("axiom_companion")
    debt = entry.get("axiom_encoding_debt")
    if companion is None and debt is None:
        return errors
    if companion is not None and debt is not None:
        errors.append(
            f"{label} declares both axiom_companion and axiom_encoding_debt; "
            "declare exactly one"
        )
    if disposition_kind is not None and disposition_kind != UPSTREAM_ENGINE_GAP:
        errors.append(
            f"{label} axiom_companion/axiom_encoding_debt belong on "
            f"{UPSTREAM_ENGINE_GAP} entries (the kind that blames the "
            f"counterpart engine); got {disposition_kind!r}"
        )
    if debt is not None and (
        not isinstance(debt, str) or not RULESPEC_ISSUE_URL_RE.match(debt)
    ):
        errors.append(
            f"{label} axiom_encoding_debt must be a TheAxiomFoundation "
            "rulespec-* issue URL (https://github.com/TheAxiomFoundation/"
            f"rulespec-<jur>/issues/<n>); got {debt!r}"
        )
    if companion is not None:
        if not isinstance(companion, Mapping):
            errors.append(f"{label} axiom_companion must be a mapping")
            return errors
        unknown = set(companion) - _COMPANION_KEYS
        if unknown:
            errors.append(
                f"{label} axiom_companion has unknown keys: {sorted(unknown)}"
            )
        legal_ids = companion.get("legal_ids")
        if not isinstance(legal_ids, list) or not legal_ids:
            errors.append(
                f"{label} axiom_companion.legal_ids must be a non-empty list"
            )
        else:
            for index, legal_id in enumerate(legal_ids):
                if not isinstance(legal_id, str) or not LEGAL_ID_RE.match(
                    legal_id
                ):
                    errors.append(
                        f"{label} axiom_companion.legal_ids[{index}] must be "
                        "a legal id <jurisdiction>:<module path>#<output>; "
                        f"got {legal_id!r}"
                    )
        tests = companion.get("tests")
        if not isinstance(tests, list) or not tests:
            errors.append(
                f"{label} axiom_companion.tests must be a non-empty list"
            )
        else:
            for index, pointer in enumerate(tests):
                if CompanionPointer.parse(pointer) is None:
                    errors.append(
                        f"{label} axiom_companion.tests[{index}] must be "
                        "rulespec-<jur>@<40-hex sha>:<path>.test.yaml#<case "
                        f"name>; got {pointer!r}"
                    )
    return errors


def is_pe_engine(name: object) -> bool:
    return isinstance(name, str) and name.lower().replace("_", "-").startswith(
        "policyengine"
    )


def is_pe_issue_url(value: object) -> bool:
    return isinstance(value, str) and PE_ISSUE_URL_RE.match(value) is not None


# --------------------------------------------------------------------------
# Attribution
# --------------------------------------------------------------------------


@dataclass
class Record:
    """One PolicyEngine-attributed mismatch explanation."""

    source: str
    id: str
    suite: str
    concept: str
    basis: str
    pe_issue: str | None
    entry: dict
    case_ids: tuple[str, ...] = ()
    # case id -> Axiom-side values of the rows this entry annotates.
    axiom_values: dict[str, tuple] = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.source, self.id, self.concept)

    @property
    def pe_issue_status(self) -> str:
        return "present" if self.pe_issue else "missing"

    @property
    def axiom_status(self) -> str:
        if self.entry.get("axiom_companion") is not None:
            return "companion"
        if self.entry.get("axiom_encoding_debt") is not None:
            return "debt"
        return "missing"

    @property
    def compliant(self) -> bool:
        return self.pe_issue is not None and self.axiom_status != "missing"

    @property
    def open(self) -> bool:
        """Counted by ``open_max``: no companion-backed Axiom side yet."""

        return self.axiom_status != "companion"

    def label(self) -> str:
        return f"{self.source} [{self.id}]"


def _dashboard_reports(repo_root: Path) -> dict[str, list[dict]]:
    by_suite: dict[str, list[dict]] = {}
    for path in sorted((repo_root / DASHBOARD_RELATIVE_DIR).glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("suite") and "summary" in data:
            by_suite.setdefault(str(data["suite"]), []).append(data)
    return by_suite


def _report_counterparts(report: dict) -> set[str]:
    engines = report.get("engines") or {}
    if not isinstance(engines, dict):
        return set()
    if "left" in engines or "right" in engines:
        return {
            str(engines[side])
            for side in ("left", "right")
            if engines.get(side) and engines.get(side) != AXIOM_ENGINE
        }
    return {
        str(name) for name in engines if name not in (AXIOM_ENGINE, "versions")
    }


def _row_sides(report: dict, row: dict) -> tuple[str | None, str | None]:
    if row.get("left_engine") or row.get("right_engine"):
        return row.get("left_engine"), row.get("right_engine")
    if isinstance(row.get("engines"), list) and len(row["engines"]) == 2:
        return row["engines"][0], row["engines"][1]
    engines = report.get("engines") or {}
    if isinstance(engines, dict) and ("left" in engines or "right" in engines):
        return engines.get("left"), engines.get("right")
    return None, None


def _row_counterparts(report: dict, row: dict) -> set[str]:
    left, right = _row_sides(report, row)
    if left is None and right is None:
        return _report_counterparts(report)
    return {str(e) for e in (left, right) if e and e != AXIOM_ENGINE}


def _row_axiom_value(report: dict, row: dict):
    left, right = _row_sides(report, row)
    if left == AXIOM_ENGINE:
        return row.get("left")
    if right == AXIOM_ENGINE:
        return row.get("right")
    return None


def _pe_issue_of_disposition(entry: dict) -> str | None:
    evidence = entry.get("evidence") or {}
    for candidate in (
        entry.get("linked_issue"),
        evidence.get("upstream_url") if isinstance(evidence, dict) else None,
    ):
        if is_pe_issue_url(candidate):
            return candidate
    return None


def attribute_disposition(
    entry: dict, reports: list[dict]
) -> tuple[str | None, tuple[str, ...], dict[str, tuple]]:
    """Return (basis or None, annotated case ids, axiom values by case).

    ``basis`` is ``"rows"``, ``"report"``, ``"kind"`` or ``"url"`` when the
    entry blames PolicyEngine, else ``None``.
    """

    if entry.get("disposition") != UPSTREAM_ENGINE_GAP:
        return None, (), {}
    entry_id = str(entry.get("id"))
    counterparts: set[str] = set()
    case_ids: list[str] = []
    axiom_values: dict[str, list] = {}
    annotated = 0
    for report in reports:
        for row in report.get("mismatches") or []:
            annotation = row.get("disposition")
            if not isinstance(annotation, dict):
                continue
            if str(annotation.get("id")) != entry_id:
                continue
            if row.get("concept") != entry.get("concept"):
                continue
            annotated += 1
            counterparts |= _row_counterparts(report, row)
            case_id = str(row.get("case_id"))
            case_ids.append(case_id)
            axiom_values.setdefault(case_id, []).append(
                _row_axiom_value(report, row)
            )
    basis = None
    if annotated:
        if any(is_pe_engine(engine) for engine in counterparts):
            basis = "rows"
    else:
        report_counterparts: set[str] = set()
        for report in reports:
            report_counterparts |= _report_counterparts(report)
        if report_counterparts and all(
            is_pe_engine(engine) for engine in report_counterparts
        ):
            basis = "report"
        elif any(is_pe_engine(e) for e in report_counterparts) and is_pe_engine(
            entry.get("kind")
        ):
            basis = "kind"
    if basis is None and _pe_issue_of_disposition(entry):
        basis = "url"
    return (
        basis,
        tuple(dict.fromkeys(case_ids)),
        {case: tuple(values) for case, values in axiom_values.items()},
    )


def _declared_case_ids(entry: dict) -> tuple[str, ...]:
    if entry.get("case_id") is not None:
        return (str(entry["case_id"]),)
    selector = entry.get("case_selector") or {}
    if isinstance(selector, dict) and isinstance(selector.get("case_ids"), list):
        return tuple(str(value) for value in selector["case_ids"])
    return ()


def known_cause_id(cause: dict) -> str:
    parts = [
        str(cause.get("suite")),
        str(cause.get("concept")),
        str(cause.get("kind")),
    ]
    engines = cause.get("engines")
    if isinstance(engines, dict) and engines:
        parts.append(f"{engines.get('left')}-{engines.get('right')}")
    return "|".join(parts)


def collect_records(repo_root: Path) -> tuple[list[Record], list[str]]:
    """Every PolicyEngine-attributed explanation, plus syntax errors."""

    reports = _dashboard_reports(repo_root)
    records: list[Record] = []
    errors: list[str] = []
    dispositions_dir = repo_root / DISPOSITIONS_RELATIVE_DIR
    for path in sorted(dispositions_dir.glob("*.yaml")):
        if path.name in CAMPAIGN_LOCAL_DISPOSITIONS_FILES:
            continue
        document = yaml.safe_load(path.read_text()) or {}
        suite = str(document.get("suite") or path.stem)
        source = path.relative_to(repo_root).as_posix()
        for entry in document.get("entries") or []:
            if not isinstance(entry, dict):
                continue
            basis, case_ids, axiom_values = attribute_disposition(
                entry, reports.get(suite, [])
            )
            if basis is None:
                continue
            records.append(
                Record(
                    source=source,
                    id=str(entry.get("id")),
                    suite=suite,
                    concept=str(entry.get("concept")),
                    basis=basis,
                    pe_issue=_pe_issue_of_disposition(entry),
                    entry=entry,
                    case_ids=case_ids or _declared_case_ids(entry),
                    axiom_values=axiom_values,
                )
            )
    known_causes_path = repo_root / KNOWN_CAUSES_RELATIVE_PATH
    if known_causes_path.exists():
        payload = json.loads(known_causes_path.read_text())
        source = KNOWN_CAUSES_RELATIVE_PATH.as_posix()
        for cause in payload.get("entries") or []:
            if not isinstance(cause, dict):
                continue
            cause_id = known_cause_id(cause)
            errors.extend(
                validate_axiom_side_fields(cause, f"{source} [{cause_id}]")
            )
            issue = cause.get("issue_url")
            owner = str(cause.get("fix_owner") or "").lower()
            owned = owner.startswith("policyengine")
            if not (owned or is_pe_issue_url(issue)):
                continue
            records.append(
                Record(
                    source=source,
                    id=cause_id,
                    suite=str(cause.get("suite")),
                    concept=str(cause.get("concept")),
                    basis="fix_owner" if owned else "url",
                    pe_issue=issue if is_pe_issue_url(issue) else None,
                    entry=cause,
                )
            )
    return records, errors


# --------------------------------------------------------------------------
# Ratchet document
# --------------------------------------------------------------------------


class RatchetDocumentError(ValueError):
    """The ratchet file is malformed."""


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


@dataclass
class Ratchet:
    open_max: int
    grandfathered: dict[tuple[str, str, str], dict] = field(default_factory=dict)
    debt_raises: list[dict] = field(default_factory=list)

    @classmethod
    def from_document(cls, document: object) -> Ratchet:
        if not isinstance(document, Mapping):
            raise RatchetDocumentError("ratchet document must be a mapping")
        if document.get("schema") != RATCHET_SCHEMA:
            raise RatchetDocumentError(
                f"unexpected ratchet schema {document.get('schema')!r}; "
                f"expected {RATCHET_SCHEMA!r}"
            )
        unknown = set(document) - _DOCUMENT_KEYS
        if unknown:
            raise RatchetDocumentError(
                f"ratchet document has unknown keys: {sorted(unknown)}"
            )
        open_max = document.get("open_max")
        if not _is_count(open_max):
            raise RatchetDocumentError("open_max must be a non-negative integer")
        raises = document.get("debt_raises") or []
        if not isinstance(raises, list):
            raise RatchetDocumentError("debt_raises must be a list")
        for index, item in enumerate(raises):
            if not isinstance(item, Mapping) or set(item) != _RAISE_KEYS:
                raise RatchetDocumentError(
                    f"debt_raises[{index}] must have exactly the keys "
                    f"{sorted(_RAISE_KEYS)}"
                )
            if not str(item.get("reason") or "").strip():
                raise RatchetDocumentError(
                    f"debt_raises[{index}] needs a non-empty reason"
                )
            if not (_is_count(item["from"]) and _is_count(item["to"])):
                raise RatchetDocumentError(
                    f"debt_raises[{index}] from/to must be non-negative integers"
                )
            if item["to"] <= item["from"]:
                raise RatchetDocumentError(
                    f"debt_raises[{index}] must raise the ceiling (to > from)"
                )
            # A raise starts from the ceiling of the epoch it closes, which
            # the previous raise bounds.
            if index and item["from"] > raises[index - 1]["to"]:
                raise RatchetDocumentError(
                    f"debt_raises[{index}] starts from {item['from']}, above "
                    f"the previous raise's ceiling {raises[index - 1]['to']}"
                )
        # The latest raise is the ceiling of the current epoch: a raise record
        # cannot authorize more debt than it names.
        if raises and open_max > raises[-1]["to"]:
            raise RatchetDocumentError(
                f"open_max {open_max} exceeds the latest debt_raises ceiling "
                f"{raises[-1]['to']}"
            )
        rows = document.get("grandfathered") or []
        if not isinstance(rows, list):
            raise RatchetDocumentError("grandfathered must be a list")
        grandfathered: dict[tuple[str, str, str], dict] = {}
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping) or set(row) != _GRANDFATHERED_KEYS:
                raise RatchetDocumentError(
                    f"grandfathered[{index}] must have exactly the keys "
                    f"{sorted(_GRANDFATHERED_KEYS)}"
                )
            if row["pe_issue"] not in _PE_ISSUE_RANK or row["axiom"] not in _AXIOM_RANK:
                raise RatchetDocumentError(
                    f"grandfathered[{index}] has an unknown status"
                )
            key = (str(row["source"]), str(row["id"]), str(row["concept"]))
            if key in grandfathered:
                raise RatchetDocumentError(
                    f"grandfathered[{index}] duplicates {key[0]} [{key[1]}]"
                )
            grandfathered[key] = dict(row)
        return cls(
            open_max=open_max,
            grandfathered=grandfathered,
            debt_raises=[dict(item) for item in raises],
        )


def _row_for(record: Record) -> dict:
    return {
        "source": record.source,
        "id": record.id,
        "concept": record.concept,
        "basis": record.basis,
        "pe_issue": record.pe_issue_status,
        "axiom": record.axiom_status,
    }


def summarize(records: list[Record]) -> dict:
    return {
        "pe_attributed": len(records),
        "pe_issue_linked": sum(1 for r in records if r.pe_issue),
        "axiom_companion": sum(
            1 for r in records if r.axiom_status == "companion"
        ),
        "axiom_encoding_debt": sum(
            1 for r in records if r.axiom_status == "debt"
        ),
        "axiom_side_missing": sum(
            1 for r in records if r.axiom_status == "missing"
        ),
        "open": sum(1 for r in records if r.open),
    }


def derive_ratchet(
    records: list[Record],
    current: Ratchet | None,
    *,
    raise_reason: str | None = None,
    today: str | None = None,
) -> dict:
    """The ratchet document the live records justify.

    Without a current ratchet this bootstraps: every currently non-compliant
    record is grandfathered and ``open_max`` is the live open count.
    Otherwise the grandfathered set is the current set minus records that
    became compliant or disappeared, and ``open_max`` only tightens — unless
    ``raise_reason`` deliberately raises it to the live count, which appends
    a ``debt_raises`` record.
    """

    open_count = sum(1 for r in records if r.open)
    noncompliant = [r for r in records if not r.compliant]
    raises: list[dict] = []
    if current is None:
        grandfathered = noncompliant
        open_max = open_count
    else:
        grandfathered = [
            r for r in noncompliant if r.key in current.grandfathered
        ]
        raises = [dict(item) for item in current.debt_raises]
        open_max = min(current.open_max, open_count)
        if raise_reason is not None and open_count > current.open_max:
            raises.append(
                {
                    "date": today or _dt.date.today().isoformat(),
                    "from": current.open_max,
                    "to": open_count,
                    "reason": raise_reason,
                }
            )
            open_max = open_count
    rows = sorted(
        (_row_for(r) for r in grandfathered),
        key=lambda row: (row["source"], row["id"], row["concept"]),
    )
    document = {
        "schema": RATCHET_SCHEMA,
        "_comment": _COMMENT,
        "open_max": open_max,
    }
    if raises:
        document["debt_raises"] = raises
    document["grandfathered"] = rows
    return document


def serialize_ratchet(document: dict) -> str:
    return _HEADER + yaml.safe_dump(
        document, sort_keys=False, allow_unicode=True, width=79
    )


_REMEDY = (
    "link the PolicyEngine issue (linked_issue or evidence.upstream_url: "
    "https://github.com/PolicyEngine/<repo>/issues/<n>) and declare either "
    "axiom_companion: {legal_ids: [<jurisdiction>:<path>#<output>], tests: "
    "[rulespec-us@<sha>:<path>.test.yaml#<case>]} or axiom_encoding_debt: "
    "https://github.com/TheAxiomFoundation/rulespec-us/issues/<n>"
)


def check_records(records: list[Record], ratchet: Ratchet | None) -> list[str]:
    """Presence + monotonic rules for the live records against the ratchet."""

    problems: list[str] = []
    grandfathered = ratchet.grandfathered if ratchet else {}
    for record in records:
        if record.compliant:
            continue
        missing = []
        if record.pe_issue is None:
            missing.append("a PolicyEngine issue URL")
        if record.axiom_status == "missing":
            missing.append("axiom_companion or axiom_encoding_debt")
        baseline = grandfathered.get(record.key)
        if baseline is None:
            problems.append(
                f"{record.label()}: PolicyEngine-attributed mismatch "
                f"(basis: {record.basis}) lacks {' and '.join(missing)}. "
                f"New attributions cannot be grandfathered: {_REMEDY}."
            )
            continue
        if _PE_ISSUE_RANK[record.pe_issue_status] < _PE_ISSUE_RANK[
            baseline["pe_issue"]
        ] or _AXIOM_RANK[record.axiom_status] < _AXIOM_RANK[baseline["axiom"]]:
            problems.append(
                f"{record.label()}: grandfathered entry regressed from "
                f"pe_issue={baseline['pe_issue']}, "
                f"axiom={baseline['axiom']} to "
                f"pe_issue={record.pe_issue_status}, "
                f"axiom={record.axiom_status}"
            )
    open_count = sum(1 for r in records if r.open)
    if ratchet is not None and open_count > ratchet.open_max:
        problems.append(
            f"RATCHET regressed: {open_count} PolicyEngine attributions lack a "
            f"companion-backed Axiom side, above open_max {ratchet.open_max}. "
            "Back the new attribution with axiom_companion or pay down "
            "existing debt; a deliberate raise is `uv run "
            "scripts/pe_axiom_standard.py --raise-ceiling \"<reason>\"`, which "
            "appends an auditable debt_raises record."
        )
    return problems


# --------------------------------------------------------------------------
# Monotonicity across committed history
# --------------------------------------------------------------------------


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def committed_versions(
    repo_root: Path,
) -> tuple[list[tuple[str, Ratchet]] | None, list[str]]:
    """Every committed version of the ratchet file reachable from HEAD.

    Returns ``(None, [])`` outside a Git work tree (tmpdir callers), and an
    error for a shallow checkout — like ``scripts/closure_universe.py``, the
    floor cannot be derived without full history (CI uses fetch-depth: 0).
    Versions that fail to parse are reported, not silently skipped: a
    malformed ancestor must not quietly erase a floor.
    """

    toplevel = _git(repo_root, "rev-parse", "--show-toplevel")
    if toplevel.returncode != 0:
        return None, []
    try:
        if Path(toplevel.stdout.strip()).resolve() != repo_root.resolve():
            return None, []
    except OSError:
        return None, []
    shallow = _git(repo_root, "rev-parse", "--is-shallow-repository")
    if shallow.returncode != 0 or shallow.stdout.strip() == "true":
        return None, [
            f"{RATCHET_RELATIVE_PATH}: cannot derive the monotonic floor from "
            "a shallow Git checkout; fetch full history (fetch-depth: 0)"
        ]
    head = _git(repo_root, "rev-parse", "--verify", "--quiet", "HEAD")
    if head.returncode != 0:
        return [], []  # a repository with no commits yet
    path = RATCHET_RELATIVE_PATH.as_posix()
    listed = _git(repo_root, "rev-list", "--full-history", "HEAD", "--", path)
    if listed.returncode != 0:
        return None, [
            f"{RATCHET_RELATIVE_PATH}: cannot enumerate committed versions: "
            f"{listed.stderr.strip()}"
        ]
    versions: list[tuple[str, Ratchet]] = []
    errors: list[str] = []
    for commit in listed.stdout.split():
        shown = _git(repo_root, "show", f"{commit}:{path}")
        if shown.returncode != 0:
            continue  # the commit deleted the file
        try:
            versions.append(
                (commit, Ratchet.from_document(yaml.safe_load(shown.stdout)))
            )
        except (yaml.YAMLError, RatchetDocumentError) as exc:
            errors.append(
                f"{RATCHET_RELATIVE_PATH}@{commit[:12]} is malformed ({exc}); "
                "a committed version cannot be skipped when deriving the floor"
            )
    return versions, errors


def check_history(
    current: Ratchet, versions: Iterable[tuple[str, Ratchet]]
) -> list[str]:
    """The ratchet may not loosen relative to any committed version.

    * ``grandfathered`` keys must be a subset of every committed version's
      keys, and each key's recorded status may not fall below any committed
      status (the grandfather door stays closed);
    * every committed ``debt_raises`` list must be a prefix of the current
      one (append-only);
    * ``open_max`` may not exceed any committed value in the same epoch
      (versions carrying the same number of ``debt_raises`` records);
    * each raise starts from at most the committed floor of the epoch it
      closes, so the record states the full increase it authorizes (the
      document itself bounds ``open_max`` by the latest raise's ``to``).
    """

    problems: list[str] = []
    grown: dict[tuple[str, str, str], str] = {}
    lowered: dict[tuple[str, str, str], str] = {}
    # epoch (number of debt_raises records) -> lowest committed open_max.
    floors: dict[int, tuple[int, str]] = {}
    for commit, version in versions:
        short = commit[:12]
        for key in set(current.grandfathered) - set(version.grandfathered):
            grown.setdefault(key, short)
        for key in set(current.grandfathered) & set(version.grandfathered):
            now = current.grandfathered[key]
            then = version.grandfathered[key]
            if (
                _PE_ISSUE_RANK[now["pe_issue"]] < _PE_ISSUE_RANK[then["pe_issue"]]
                or _AXIOM_RANK[now["axiom"]] < _AXIOM_RANK[then["axiom"]]
            ):
                lowered.setdefault(key, short)
        prefix = current.debt_raises[: len(version.debt_raises)]
        if prefix != version.debt_raises:
            problems.append(
                f"debt_raises was rewritten relative to {short}: the list is "
                "append-only"
            )
        epoch = len(version.debt_raises)
        if epoch not in floors or version.open_max < floors[epoch][0]:
            floors[epoch] = (version.open_max, short)
    for key, short in sorted(grown.items()):
        problems.append(
            f"grandfathered list grew relative to {short}: {key[0]} "
            f"[{key[1]}]. The grandfather door is closed; new attributions "
            "must declare axiom_companion or axiom_encoding_debt."
        )
    for key, short in sorted(lowered.items()):
        problems.append(
            f"grandfathered status of {key[0]} [{key[1]}] fell below the "
            f"status recorded at {short}"
        )
    for index, item in enumerate(current.debt_raises):
        closed = floors.get(index)
        if closed is not None and item["from"] > closed[0]:
            problems.append(
                f"debt_raises[{index}] raises from {item['from']}, but the "
                f"committed ceiling it replaces was {closed[0]} (at "
                f"{closed[1]}); a raise must record the full increase"
            )
    floor = floors.get(len(current.debt_raises))
    if floor is not None and current.open_max > floor[0]:
        problems.append(
            f"open_max {current.open_max} exceeds the committed floor "
            f"{floor[0]} (at {floor[1]}). open_max may only fall; a deliberate "
            "raise must append a debt_raises record via `--raise-ceiling`."
        )
    return problems


# --------------------------------------------------------------------------
# Companion resolution
# --------------------------------------------------------------------------

Fetcher = Callable[[str, str, str], "str | None"]
MergedCheck = Callable[[str, str], "bool | None"]


class LocalGitSource:
    """Read RuleSpec repositories from local clones (``repo=path``)."""

    def __init__(self, checkouts: Mapping[str, Path], main_ref: str = "origin/main"):
        self.checkouts = {name: Path(path) for name, path in checkouts.items()}
        self.main_ref = main_ref

    def _git(self, repo: str, *args: str) -> subprocess.CompletedProcess | None:
        root = self.checkouts.get(repo)
        if root is None:
            return None
        return _git(root, *args)

    def read(self, repo: str, sha: str, path: str) -> str | None:
        result = self._git(repo, "show", f"{sha}:{path}")
        if result is None or result.returncode != 0:
            return None
        return result.stdout

    def is_merged(self, repo: str, sha: str) -> bool | None:
        result = self._git(repo, "merge-base", "--is-ancestor", sha, self.main_ref)
        if result is None:
            return None
        return result.returncode == 0

    def main_sha(self, repo: str) -> str | None:
        result = self._git(repo, "rev-parse", self.main_ref)
        if result is None or result.returncode != 0:
            return None
        return result.stdout.strip()


class GitHubSource:
    """Read public RuleSpec repositories over HTTPS (content-addressed)."""

    def __init__(self, owner: str = "TheAxiomFoundation", token: str | None = None):
        self.owner = owner
        self.token = token

    def _get(self, url: str, *, api: bool = False) -> tuple[int, bytes]:
        request = urllib.request.Request(url)
        if api:
            request.add_header("Accept", "application/vnd.github+json")
            if self.token:
                request.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, b""
        except urllib.error.URLError:
            return 0, b""

    def read(self, repo: str, sha: str, path: str) -> str | None:
        status, body = self._get(
            f"https://raw.githubusercontent.com/{self.owner}/{repo}/{sha}/{path}"
        )
        return body.decode("utf-8") if status == 200 else None

    def is_merged(self, repo: str, sha: str) -> bool | None:
        status, body = self._get(
            f"https://api.github.com/repos/{self.owner}/{repo}/compare/{sha}...main",
            api=True,
        )
        if status != 200:
            return None
        return json.loads(body).get("status") in {"ahead", "identical"}

    def main_sha(self, repo: str) -> str | None:
        status, body = self._get(
            f"https://api.github.com/repos/{self.owner}/{repo}/commits/main",
            api=True,
        )
        return json.loads(body).get("sha") if status == 200 else None


def _numeric(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def _find_case(document: object, name: str) -> dict | None:
    cases = document if isinstance(document, list) else (
        document.get("cases") if isinstance(document, dict) else None
    )
    for case in cases or []:
        if isinstance(case, dict) and case.get("name") == name:
            return case
    return None


class CompanionResolver:
    def __init__(self, source, *, require_merged: bool = True):
        self.source = source
        self.require_merged = require_merged
        self._cache: dict[tuple[str, str, str], object] = {}

    def _document(self, pointer: CompanionPointer):
        key = (pointer.repo, pointer.sha, pointer.path)
        if key not in self._cache:
            text = self.source.read(pointer.repo, pointer.sha, pointer.path)
            try:
                self._cache[key] = None if text is None else yaml.safe_load(text)
            except yaml.YAMLError:
                self._cache[key] = None
        return self._cache[key]

    def resolve(self, record: Record) -> list[str]:
        companion = record.entry.get("axiom_companion")
        if not isinstance(companion, Mapping):
            return []
        problems: list[str] = []
        legal_ids = [str(x) for x in companion.get("legal_ids") or []]
        for raw in companion.get("tests") or []:
            pointer = CompanionPointer.parse(raw)
            if pointer is None:
                continue  # syntax already reported
            label = f"{record.label()} companion {pointer}"
            if self.require_merged:
                merged = self.source.is_merged(pointer.repo, pointer.sha)
                if merged is None:
                    problems.append(
                        f"{label}: cannot verify the commit is on "
                        f"{pointer.repo} main"
                    )
                elif not merged:
                    problems.append(
                        f"{label}: commit is not on {pointer.repo} main"
                    )
            document = self._document(pointer)
            if document is None:
                problems.append(
                    f"{label}: test file not found (or not YAML) at the "
                    "pinned commit"
                )
                continue
            case = _find_case(document, pointer.case)
            if case is None:
                problems.append(f"{label}: no case named {pointer.case!r}")
                continue
            outputs = case.get("output") or {}
            if not isinstance(outputs, Mapping):
                problems.append(f"{label}: case has no output mapping")
                continue
            for legal_id in legal_ids:
                if legal_id not in outputs:
                    problems.append(
                        f"{label}: case does not assert {legal_id}"
                    )
                    continue
                # A companion case that IS the disputed case must assert the
                # value Axiom produced in the comparison — the dispute is then
                # pinned in RuleSpec CI, not just described.
                axiom_numbers = {
                    _numeric(value)
                    for value in record.axiom_values.get(pointer.case, ())
                } - {None}
                if legal_id == record.concept and len(axiom_numbers) == 1:
                    expected = _numeric(outputs[legal_id])
                    (actual,) = axiom_numbers
                    if expected is not None and not math.isclose(
                        expected, actual, rel_tol=1e-9, abs_tol=0.005
                    ):
                        problems.append(
                            f"{label}: case asserts {legal_id} = {expected} "
                            f"but the disputed Axiom value is {actual}"
                        )
        return problems


def legal_id_companion_path(legal_id: str) -> tuple[str, str] | None:
    """``us-tn:policies/x#y`` -> (``rulespec-us``, ``us-tn/policies/x.test.yaml``)."""

    match = LEGAL_ID_RE.match(legal_id)
    if match is None:
        return None
    jurisdiction = match.group("jurisdiction")
    country = jurisdiction.split("-", 1)[0]
    return f"rulespec-{country}", f"{jurisdiction}/{match.group('path')}.test.yaml"


def suggest_companions(records: Iterable[Record], source) -> list[dict]:
    """Open records whose disputed case already has a companion case.

    Looks for a case in the concept module's companion test whose name is one
    of the disputed case ids and whose outputs assert the concept.
    """

    suggestions: list[dict] = []
    main_shas: dict[str, str | None] = {}
    for record in records:
        if record.axiom_status == "companion":
            continue
        located = legal_id_companion_path(record.concept)
        if located is None:
            continue
        repo, path = located
        if repo not in main_shas:
            main_shas[repo] = source.main_sha(repo)
        sha = main_shas[repo]
        if not sha:
            continue
        text = source.read(repo, sha, path)
        if text is None:
            continue
        document = yaml.safe_load(text)
        for case_id in record.case_ids:
            case = _find_case(document, case_id)
            if case and record.concept in (case.get("output") or {}):
                suggestions.append(
                    {
                        "source": record.source,
                        "id": record.id,
                        "axiom_companion": {
                            "legal_ids": [record.concept],
                            "tests": [f"{repo}@{sha}:{path}#{case_id}"],
                        },
                    }
                )
                break
    return suggestions
