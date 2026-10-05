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
      companion test case that exercises the disputed case. When the disputed
      concept is itself a RuleSpec output it must be among the legal ids;
      otherwise every legal id and test must be in the concept's country
      (:func:`companion_scope_problems`, and ``--resolve``).
  ``axiom_encoding_debt``
      ``https://github.com/TheAxiomFoundation/rulespec-<jur>/issues/<n>`` —
      the Axiom encoding (or its companion case) is owed and tracked; counted
      by the ratchet in ``conformance/pe-axiom-standard.yaml``.

* It keeps the ratchet (:func:`derive_ratchet`, :func:`check_records`,
  :func:`check_history`). Explanations that predate the standard are
  grandfathered with their status computed at freeze time. Across every
  committed version of the ratchet file the grandfathered set may only
  shrink, a grandfathered entry's recorded status may only rise, the
  ``debt_raises`` log only grows, and ``open_max`` — PolicyEngine
  attributions without a companion (declared debt plus grandfathered) — may
  not exceed any committed version's ``open_max`` plus the increments
  (``to - from``) of the raises recorded since (:func:`history_ceiling`).
  Charging each version only for the raises it has not seen keeps parallel
  branches mergeable; re-pinning starts from :func:`effective_ratchet`, what
  history enforces. Monotonicity is derived from Git history, as
  ``scripts/closure_universe.py`` derives its pending floor, so it bites on
  pull requests and on direct pushes alike and cannot be defeated by editing
  the ratchet file in the same change.
* Optionally it resolves each declared Axiom side against GitHub or local
  clones (:class:`CompanionResolver`). A companion test file must exist at
  the pinned commit, which must be on the repository's main line; the named
  case must assert every declared legal id, the Axiom value the comparison
  produced when it shares the disputed case's id, and the same values on
  main today. PolicyEngine citations must resolve to issue payloads rather
  than pull requests. Encoding debt must be an open issue.

Attribution rule (``upstream_engine_gap`` dispositions only — the one kind
that says the counterpart engine is wrong):

1. Rows: the committed dashboard report rows this entry annotates name their
   counterpart engine (``left_engine``/``right_engine``, a row ``engines``
   list, or the report's two-engine ``engines``). A PolicyEngine counterpart
   of Axiom makes the entry PolicyEngine-attributed; a row between two
   oracles (no Axiom leg) attributes nothing by itself.
2. Report: an entry that annotates no row (expired, or a sampled report) is
   attributed from the report's engine set when PolicyEngine is the only
   counterpart, or — in a multi-oracle report — when its mismatch ``kind``
   is a PolicyEngine-leg kind (``policyengine_amount_difference``).
3. URL: an entry whose ``linked_issue`` or ``evidence.upstream_url`` links a
   PolicyEngine issue or pull request is PolicyEngine-attributed whatever
   the rows say. Only an issue satisfies the requirement to cite one.

Known causes (``dashboard/public/data/known_causes.json``) are the second
place a mismatch bucket can be explained. A cause whose ``fix_owner`` names
``policyengine`` or whose ``issue_url`` links PolicyEngine is attributed when
it is live: the dashboard's ``causeFor()`` picks it for a mismatch bucket in
a committed report (:func:`_known_cause_live`).
"""
from __future__ import annotations

import datetime as _dt
import http.client
import json
import math
import re
import subprocess
import time
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_SCHEMA_FAMILY = "axiom_oracles.pe_axiom_standard.v"
RATCHET_SCHEMA = f"{_SCHEMA_FAMILY}1"
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

# A PolicyEngine issue or pull request (any casing of the org, optionally
# with a comment anchor or query). Either one attributes a mismatch to
# PolicyEngine; only an issue satisfies the standard's "cite the PE issue".
PE_LINK_URL_RE = re.compile(
    r"^https://github\.com/(?i:policyengine)/(?P<repo>[A-Za-z0-9._-]+)/"
    r"(?P<kind>issues|pull)/(?P<number>[1-9]\d*)/?(?:[?#]\S*)?$"
)
RULESPEC_ISSUE_URL_RE = re.compile(
    r"^https://github\.com/TheAxiomFoundation/(?P<repo>rulespec-[a-z0-9-]+)/"
    r"issues/(?P<number>[1-9]\d*)/?$"
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
    f"# {RATCHET_SCHEMA} - GENERATED; advance only via "
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


def is_pe_link_url(value: object) -> bool:
    """A PolicyEngine issue or pull request: enough to attribute."""

    return isinstance(value, str) and PE_LINK_URL_RE.match(value) is not None


def is_pe_issue_url(value: object) -> bool:
    """A PolicyEngine issue: what the standard requires an entry to cite."""

    match = PE_LINK_URL_RE.match(value) if isinstance(value, str) else None
    return match is not None and match.group("kind") == "issues"


def is_pe_owner(owner: object) -> bool:
    """A known cause's ``fix_owner`` names PolicyEngine as one of its tokens
    (``policyengine``, ``policyengine-data``, ``upstream-policyengine``)."""

    return "policyengine" in re.split(r"[^a-z0-9]+", str(owner or "").lower())


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
    # Actual dashboard row kinds, independent of an optional entry filter.
    row_kinds: tuple[str, ...] = ()

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
    if AXIOM_ENGINE not in (left, right):
        # Oracle vs oracle (PolicyEngine vs TAXSIM, Tax-Calculator vs
        # PolicyEngine): the row does not say which side is wrong, so it
        # attributes nothing; a linked PolicyEngine issue still does.
        return set()
    return {str(e) for e in (left, right) if e and e != AXIOM_ENGINE}


def _row_axiom_value(report: dict, row: dict):
    left, right = _row_sides(report, row)
    if left == AXIOM_ENGINE:
        return row.get("left")
    if right == AXIOM_ENGINE:
        return row.get("right")
    return None


def _disposition_links(entry: dict) -> tuple[object, ...]:
    evidence = entry.get("evidence") or {}
    return (
        entry.get("linked_issue"),
        evidence.get("upstream_url") if isinstance(evidence, dict) else None,
    )


def _pe_issue_of_disposition(entry: dict) -> str | None:
    """The PolicyEngine issue an entry cites (a pull request does not count)."""

    return next(
        (url for url in _disposition_links(entry) if is_pe_issue_url(url)), None
    )


def _links_pe(entry: dict) -> bool:
    return any(is_pe_link_url(url) for url in _disposition_links(entry))


def _disposition_rows(entry: dict, reports: list[dict]):
    for report in reports:
        for row in report.get("mismatches") or []:
            annotation = row.get("disposition")
            if (
                isinstance(annotation, dict)
                and str(annotation.get("id")) == str(entry.get("id"))
                and row.get("concept") == entry.get("concept")
            ):
                yield report, row


def _row_evidence(rows) -> tuple[tuple[str, ...], dict[str, tuple], tuple[str, ...]]:
    values: dict[str, list] = {}
    kinds: dict[str, None] = {}
    for report, row in rows:
        case = str(row.get("case_id"))
        values.setdefault(case, []).append(_row_axiom_value(report, row))
        kinds[str(row.get("kind"))] = None
    return tuple(values), {case: tuple(v) for case, v in values.items()}, tuple(kinds)


def attribute_disposition(
    entry: dict, reports: list[dict]
) -> tuple[str | None, tuple[str, ...], dict[str, tuple]]:
    """Return (basis or None, annotated case ids, axiom values by case).

    ``basis`` is ``"rows"``, ``"report"``, ``"kind"`` or ``"url"`` when the
    entry blames PolicyEngine, else ``None``.
    """

    if entry.get("disposition") != UPSTREAM_ENGINE_GAP:
        return None, (), {}
    counterparts: set[str] = set()
    case_ids: list[str] = []
    axiom_values: dict[str, list] = {}
    annotated = 0
    for report, row in _disposition_rows(entry, reports):
        annotated += 1
        counterparts |= _row_counterparts(report, row)
        case_id = str(row.get("case_id"))
        case_ids.append(case_id)
        axiom_values.setdefault(case_id, []).append(_row_axiom_value(report, row))
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
    if basis is None and _links_pe(entry):
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


def _cause_for(
    known_causes: list[dict], report: dict, concept: object, kind: object
) -> dict | None:
    """Mirror ``causeFor()`` in dashboard/src/utils/programs.js."""

    candidates = [
        c
        for c in known_causes
        if c.get("suite") == report.get("suite")
        and c.get("concept") == concept
        and c.get("kind") == kind
    ]
    engines = report.get("engines") or {}
    for cause in candidates:
        own = cause.get("engines")
        if isinstance(own, dict) and own and (
            own.get("left") == engines.get("left")
            and own.get("right") == engines.get("right")
        ):
            return cause
    return next((c for c in candidates if not c.get("engines")), None)


def _known_cause_live(
    cause: dict, known_causes: list[dict], reports: list[dict]
) -> bool:
    """The cause explains a mismatch bucket in a committed report.

    A cause is live when the dashboard would pick it (``causeFor``) for some
    (concept, kind) bucket of mismatch rows. When a report publishes only a
    sample of its rows, a nonzero ``mismatches_by_concept`` count for the
    cause's concept keeps it live (fail closed: attributed).
    """

    concept, kind = cause.get("concept"), cause.get("kind")
    for report in reports:
        # Only the cause the dashboard would show for this bucket is live, so
        # two causes for one bucket never both attribute.
        if _cause_for(known_causes, report, concept, kind) is not cause:
            continue
        rows = report.get("mismatches") or []
        if any(
            row.get("concept") == concept and row.get("kind") == kind
            for row in rows
        ):
            return True
        summary = report.get("summary") or {}
        if (summary.get("mismatch_count") or 0) > len(rows):
            for bucket in summary.get("mismatches_by_concept") or []:
                if (
                    isinstance(bucket, dict)
                    and concept in (bucket.get("concept"), bucket.get("value"))
                    and bucket.get("count")
                ):
                    return True
    return False


def _known_cause_rows(cause: dict, known_causes: list[dict], reports: list[dict]):
    concept, kind = cause.get("concept"), cause.get("kind")
    for report in reports:
        if _cause_for(known_causes, report, concept, kind) is cause:
            for row in report.get("mismatches") or []:
                if row.get("concept") == concept and row.get("kind") == kind:
                    yield report, row


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
            _, _, row_kinds = _row_evidence(
                _disposition_rows(entry, reports.get(suite, []))
            )
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
                    row_kinds=row_kinds,
                )
            )
    known_causes_path = repo_root / KNOWN_CAUSES_RELATIVE_PATH
    if known_causes_path.exists():
        payload = json.loads(known_causes_path.read_text())
        source = KNOWN_CAUSES_RELATIVE_PATH.as_posix()
        causes = [c for c in payload.get("entries") or [] if isinstance(c, dict)]
        for cause in causes:
            cause_id = known_cause_id(cause)
            if isinstance(cause.get("engines"), dict) and not cause["engines"]:
                errors.append(
                    f"{source} [{cause_id}]: engines mapping must not be empty"
                )
            errors.extend(
                validate_axiom_side_fields(cause, f"{source} [{cause_id}]")
            )
            issue = cause.get("issue_url")
            owned = is_pe_owner(cause.get("fix_owner"))
            if not (owned or is_pe_link_url(issue)):
                continue
            # A cause that explains no mismatch in the committed reports
            # attributes nothing (PolicyEngine fixed it, or the rows moved).
            if not _known_cause_live(
                cause, causes, reports.get(str(cause.get("suite")), [])
            ):
                continue
            case_ids, axiom_values, row_kinds = _row_evidence(
                _known_cause_rows(
                    cause, causes, reports.get(str(cause.get("suite")), [])
                )
            )
            records.append(
                Record(
                    source=source,
                    id=cause_id,
                    suite=str(cause.get("suite")),
                    concept=str(cause.get("concept")),
                    basis="fix_owner" if owned else "url",
                    pe_issue=issue if is_pe_issue_url(issue) else None,
                    entry=cause,
                    case_ids=case_ids,
                    axiom_values=axiom_values,
                    row_kinds=row_kinds,
                )
            )
    # Grandfathering and the presence rule are keyed by (source, id,
    # concept); two explanations sharing a key would share one baseline.
    seen: set[tuple[str, str, str]] = set()
    for record in records:
        if record.key in seen:
            errors.append(
                f"{record.label()}: two PolicyEngine attributions share the key "
                f"{record.key}; known causes must be unique per suite, concept, "
                "kind and engines"
            )
        seen.add(record.key)
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
    def from_document(cls, document: object, *, strict: bool = True) -> Ratchet:
        """Parse a ratchet document.

        ``strict`` (the working file) requires exactly this schema's keys.
        Committed versions are parsed leniently: a later schema may add keys,
        so only the fields the monotonic rules read must be present and well
        formed there.
        """

        if not isinstance(document, Mapping):
            raise RatchetDocumentError("ratchet document must be a mapping")
        schema = document.get("schema")
        if schema != RATCHET_SCHEMA and (
            strict or not str(schema).startswith(_SCHEMA_FAMILY)
        ):
            raise RatchetDocumentError(
                f"unexpected ratchet schema {schema!r}; expected {RATCHET_SCHEMA!r}"
            )
        unknown = set(document) - _DOCUMENT_KEYS
        if strict and unknown:
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
            if not _has_keys(item, _RAISE_KEYS, strict):
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
        rows = document.get("grandfathered") or []
        if not isinstance(rows, list):
            raise RatchetDocumentError("grandfathered must be a list")
        grandfathered: dict[tuple[str, str, str], dict] = {}
        for index, row in enumerate(rows):
            if not _has_keys(row, _GRANDFATHERED_KEYS, strict):
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
            grandfathered[key] = {k: row[k] for k in _GRANDFATHERED_KEYS}
        return cls(
            open_max=open_max,
            grandfathered=grandfathered,
            debt_raises=[{k: item[k] for k in _RAISE_KEYS} for item in raises],
        )


def _has_keys(item: object, keys: set[str], strict: bool) -> bool:
    if not isinstance(item, Mapping):
        return False
    return set(item) == keys if strict else keys <= set(item)


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
    # Escaped, not allow_unicode: PyYAML writes U+0085 raw and reads it back
    # as a line break, so an id containing it would not round-trip and its
    # grandfathered row would stop matching (found by the round-trip property).
    return _HEADER + yaml.safe_dump(
        document, sort_keys=False, allow_unicode=False, width=79
    )


_REMEDY = (
    "link the PolicyEngine issue (linked_issue or evidence.upstream_url: "
    "https://github.com/PolicyEngine/<repo>/issues/<n>) and declare either "
    "axiom_companion: {legal_ids: [<jurisdiction>:<path>#<output>], tests: "
    "[rulespec-us@<sha>:<path>.test.yaml#<case>]} or axiom_encoding_debt: "
    "https://github.com/TheAxiomFoundation/rulespec-us/issues/<n>"
)


def _status_baselines(
    current: Mapping[tuple[str, str, str], dict],
    versions: Iterable[tuple[str, Ratchet]],
) -> dict[tuple[str, str, str], dict]:
    """Recorded ranks, including rows only removed from the working file.

    A committed removal closes a row's historical status baseline. An
    uncommitted removal cannot erase that baseline, but these ranks never
    authorize grandfathering a record absent from the working ratchet.
    """

    baselines = dict(current)
    versions = list(versions)
    if not versions:
        return baselines
    shared = set(versions[0][1].grandfathered)
    for _, version in versions[1:]:
        shared.intersection_update(version.grandfathered)
    for key in shared:
        best = dict(baselines.get(key, versions[0][1].grandfathered[key]))
        for _, version in versions:
            then = version.grandfathered[key]
            if _PE_ISSUE_RANK[then["pe_issue"]] > _PE_ISSUE_RANK[best["pe_issue"]]:
                best["pe_issue"] = then["pe_issue"]
            if _AXIOM_RANK[then["axiom"]] > _AXIOM_RANK[best["axiom"]]:
                best["axiom"] = then["axiom"]
        baselines[key] = best
    return baselines


def check_records(
    records: list[Record],
    ratchet: Ratchet | None,
    *,
    versions: Iterable[tuple[str, Ratchet]] = (),
) -> list[str]:
    """Presence + monotonic rules for the live records against the ratchet."""

    problems: list[str] = []
    grandfathered = ratchet.grandfathered if ratchet else {}
    status_baselines = _status_baselines(grandfathered, versions)
    for record in records:
        problems.extend(companion_scope_problems(record))
        problems.extend(companion_row_kind_problems(record))
        baseline = status_baselines.get(record.key)
        # Presence improvements do not waive either recorded status: adding
        # the PE issue must not hide a companion -> debt downgrade.
        if baseline is not None and (
            _PE_ISSUE_RANK[record.pe_issue_status] < _PE_ISSUE_RANK[baseline["pe_issue"]]
            or _AXIOM_RANK[record.axiom_status] < _AXIOM_RANK[baseline["axiom"]]
        ):
            problems.append(
                f"{record.label()}: grandfathered entry regressed from "
                f"pe_issue={baseline['pe_issue']}, "
                f"axiom={baseline['axiom']} to "
                f"pe_issue={record.pe_issue_status}, "
                f"axiom={record.axiom_status}"
            )
        if record.compliant:
            continue
        missing = []
        if record.pe_issue is None:
            missing.append("a PolicyEngine issue URL")
        if record.axiom_status == "missing":
            missing.append("axiom_companion or axiom_encoding_debt")
        if record.key not in grandfathered:
            problems.append(
                f"{record.label()}: PolicyEngine-attributed mismatch "
                f"(basis: {record.basis}) lacks {' and '.join(missing)}. "
                f"New attributions cannot be grandfathered: {_REMEDY}."
            )
            continue
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
                (
                    commit,
                    Ratchet.from_document(
                        yaml.safe_load(shown.stdout), strict=False
                    ),
                )
            )
        except (yaml.YAMLError, RatchetDocumentError) as exc:
            errors.append(
                f"{RATCHET_RELATIVE_PATH}@{commit[:12]} is malformed ({exc}); "
                "a committed version cannot be skipped when deriving the floor"
            )
    return versions, errors


def _raise_key(item: Mapping) -> tuple[str, int, int, str]:
    return (str(item["date"]), item["from"], item["to"], str(item["reason"]))


def _raise_log(ratchet: Ratchet) -> Counter:
    return Counter(_raise_key(item) for item in ratchet.debt_raises)


def history_ceiling(
    current: Ratchet, versions: Iterable[tuple[str, Ratchet]]
) -> tuple[int, str] | None:
    """The highest ``open_max`` every committed version allows ``current``.

    A committed version allows its own ``open_max`` plus the increments
    (``to - from``) of the raise records ``current`` carries that the version
    does not. The ceiling is the least of those allowances, with the commit
    that sets it; ``None`` without history. Because each version is charged
    only for the raises it has not seen, parallel branches merge: a pay-down
    on one branch and a raise on another combine to the pay-down plus the
    raise, and two raises combine to both increments.
    """

    ceiling: tuple[int, str] | None = None
    log = _raise_log(current)
    for commit, version in versions:
        unseen = log - _raise_log(version)
        allowed = version.open_max + sum(
            (to - start) * count for (_, start, to, _), count in unseen.items()
        )
        if ceiling is None or allowed < ceiling[0]:
            ceiling = (allowed, commit[:12])
    return ceiling


def effective_ratchet(
    current: Ratchet, versions: Iterable[tuple[str, Ratchet]]
) -> Ratchet:
    """The working ratchet tightened to what :func:`check_history` enforces.

    Re-pinning starts from this, not from the working file alone, so that
    after a revert or a merge (where the file may be one side's version) the
    result passes history whenever the live data allows it:

    * the raise log is the union of every committed log and the file's;
    * a grandfathered row survives only if every committed version still
      grandfathers it, at the highest status any of them recorded (so a
      regression against either side of a merge is judged, not absorbed);
    * ``open_max`` is at most :func:`history_ceiling`.
    """

    versions = list(versions)
    if not versions:
        return current
    log = _raise_log(current)
    for _, version in versions:
        log |= _raise_log(version)
    raises = [
        {"date": date, "from": start, "to": to, "reason": reason}
        for (date, start, to, reason) in sorted(log.elements())
    ]
    merged = Ratchet(open_max=current.open_max, debt_raises=raises)
    ceiling = history_ceiling(merged, versions)
    rows: dict[tuple[str, str, str], dict] = {}
    for key, row in current.grandfathered.items():
        if not all(key in version.grandfathered for _, version in versions):
            continue
        best = dict(row)
        for _, version in versions:
            then = version.grandfathered[key]
            if _PE_ISSUE_RANK[then["pe_issue"]] > _PE_ISSUE_RANK[best["pe_issue"]]:
                best["pe_issue"] = then["pe_issue"]
            if _AXIOM_RANK[then["axiom"]] > _AXIOM_RANK[best["axiom"]]:
                best["axiom"] = then["axiom"]
        rows[key] = best
    return Ratchet(
        open_max=min(current.open_max, ceiling[0]),
        grandfathered=rows,
        debt_raises=raises,
    )


def check_history(
    current: Ratchet, versions: Iterable[tuple[str, Ratchet]]
) -> list[str]:
    """The ratchet may not loosen relative to any committed version.

    * ``grandfathered`` keys must be a subset of every committed version's
      keys, and each key's recorded status may not fall below any committed
      status (the grandfather door stays closed);
    * the ``debt_raises`` log only grows: every committed record is still
      present, unedited;
    * ``open_max`` may not exceed :func:`history_ceiling`: every committed
      version's ``open_max`` plus the increments of the raises recorded since.
    """

    versions = list(versions)
    problems: list[str] = []
    grown: dict[tuple[str, str, str], str] = {}
    lowered: dict[tuple[str, str, str], str] = {}
    log = _raise_log(current)
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
        dropped = _raise_log(version) - log
        if dropped:
            problems.append(
                f"debt_raises records committed at {short} were removed or "
                f"edited ({sorted(dropped)}): the log only grows"
            )
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
    ceiling = history_ceiling(current, versions)
    if ceiling is not None and current.open_max > ceiling[0]:
        problems.append(
            f"open_max {current.open_max} exceeds the committed floor "
            f"{ceiling[0]} (at {ceiling[1]}, plus the increments of the raises "
            "recorded since). open_max may only fall; a deliberate raise must "
            "append a debt_raises record via `--raise-ceiling`."
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


class SourceUnavailable(RuntimeError):
    """A remote read failed for a reason other than absence; re-run."""


# HTTP statuses (0: no response) worth retrying before giving up.
_TRANSIENT_STATUSES = frozenset({0, 429, 500, 502, 503, 504})


class GitHubSource:
    """Read public RuleSpec repositories over HTTPS (content-addressed).

    Transient failures (no response, 429, 5xx) are retried with backoff.
    Absence (404) is an answer; any other failure is reported as
    "cannot verify", never as "not found".
    """

    def __init__(
        self,
        owner: str = "TheAxiomFoundation",
        token: str | None = None,
        *,
        attempts: int = 3,
        backoff: float = 2.0,
    ):
        self.owner = owner
        self.token = token
        self.attempts = attempts
        self.backoff = backoff

    def _get(self, url: str, *, api: bool = False) -> tuple[int, bytes]:
        request = urllib.request.Request(url)
        if api:
            request.add_header("Accept", "application/vnd.github+json")
            if self.token:
                request.add_header("Authorization", f"Bearer {self.token}")
        status = 0
        for attempt in range(self.attempts):
            if attempt:
                time.sleep(self.backoff * 2 ** (attempt - 1))
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    return response.status, response.read()
            except urllib.error.HTTPError as exc:
                status = exc.code
            except (OSError, http.client.HTTPException):
                status = 0  # reset, timeout, refused, truncated response
            if status not in _TRANSIENT_STATUSES:
                break
        return status, b""

    def _json(self, url: str) -> tuple[int, object]:
        status, body = self._get(url, api=True)
        if status != 200:
            return status, None
        try:
            return status, json.loads(body)
        except ValueError:
            return 0, None

    def fetch_json(self, url: str) -> tuple[int, object]:
        """Read a GitHub API payload, preserving absence vs failed reads."""

        return self._json(url)

    def read(self, repo: str, sha: str, path: str) -> str | None:
        status, body = self._get(
            f"https://raw.githubusercontent.com/{self.owner}/{repo}/{sha}/{path}"
        )
        if status == 200:
            return body.decode("utf-8")
        if status == 404:
            return None
        raise SourceUnavailable(
            f"could not fetch {repo}@{sha[:12]}:{path} (HTTP {status or 'no response'})"
        )

    def is_merged(self, repo: str, sha: str) -> bool | None:
        status, payload = self._json(
            f"https://api.github.com/repos/{self.owner}/{repo}/compare/{sha}...main"
        )
        if status == 404:
            return False  # the commit (or the repository) is unknown to GitHub
        if not isinstance(payload, dict):
            return None
        return payload.get("status") in {"ahead", "identical"}

    def main_sha(self, repo: str) -> str | None:
        _, payload = self._json(
            f"https://api.github.com/repos/{self.owner}/{repo}/commits/main"
        )
        return payload.get("sha") if isinstance(payload, dict) else None

    def issue(self, repo: str, number: int) -> dict | None:
        """The issue payload; ``{}`` when it does not exist; ``None`` when
        GitHub could not be asked."""

        status, payload = self._json(
            f"https://api.github.com/repos/{self.owner}/{repo}/issues/{number}"
        )
        if status in (404, 410):
            return {}
        return payload if isinstance(payload, dict) else None


def _numeric(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


# RuleSpec encodes judgments as holds / not_holds; comparisons carry booleans.
_JUDGMENTS = {"holds": True, "not_holds": False}
_ELIGIBILITY_KINDS = {"eligibility_left_only", "eligibility_right_only"}


def _comparable(value) -> tuple[str, object] | None:
    """A value normalized for comparison: ("judgment", bool) or ("number",
    float); ``None`` when it cannot be read as either. A one-row tables-style
    list is its row; a longer list cannot stand for one disputed value."""

    if isinstance(value, list):
        return _comparable(value[0]) if len(value) == 1 else None
    if isinstance(value, bool):
        return ("judgment", value)
    if isinstance(value, str) and value.strip() in _JUDGMENTS:
        return ("judgment", _JUDGMENTS[value.strip()])
    number = _numeric(value)
    return None if number is None else ("number", number)


def _same(
    left: tuple[str, object], right: tuple[str, object], *, eligibility: bool = False
) -> bool:
    if left[0] == right[0] == "number":
        return math.isclose(left[1], right[1], rel_tol=0, abs_tol=0.005)
    if left[0] == right[0]:
        return left[1] == right[1]
    if not eligibility:
        return False
    # Only explicitly identified eligibility outputs may carry a 0/1 judgment.
    judgment, number = (left, right) if left[0] == "judgment" else (right, left)
    return number[1] in (0.0, 1.0) and bool(number[1]) == judgment[1]


def _same_assertion(
    left, right, *, eligibility: bool = False, numeric: bool = False
) -> bool:
    a, b = _comparable(left), _comparable(right)
    if numeric:
        return (
            a is not None
            and b is not None
            and a[0] == b[0] == "number"
            and _same(a, b)
        )
    if a is not None and b is not None:
        return _same(a, b, eligibility=eligibility)
    if type(left) is not type(right):
        return False
    # Python's container equality also aliases nested false/true with 0/1.
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _same_assertion(x, y, eligibility=eligibility)
            for x, y in zip(left, right)
        )
    if isinstance(left, Mapping):
        return left.keys() == right.keys() and all(
            _same_assertion(left[key], right[key], eligibility=eligibility)
            for key in left
        )
    return left == right


def _find_case(document: object, name: str) -> dict | None:
    cases = document if isinstance(document, list) else (
        document.get("cases") if isinstance(document, dict) else None
    )
    for case in cases or []:
        if isinstance(case, dict) and case.get("name") == name:
            return case
    return None


def _asserts(document: object, legal_id: str) -> bool:
    cases = document if isinstance(document, list) else (
        document.get("cases") if isinstance(document, dict) else None
    )
    return any(
        isinstance(case, dict)
        and isinstance(case.get("output"), Mapping)
        and legal_id in case["output"]
        for case in cases or []
    )


def _country(legal_id: object) -> str | None:
    match = LEGAL_ID_RE.match(legal_id) if isinstance(legal_id, str) else None
    return match.group("jurisdiction").split("-", 1)[0] if match else None


def companion_scope_problems(record: Record) -> list[str]:
    """A companion must be about the disputed concept (offline part).

    When the concept is not among ``legal_ids`` (a comparison-surface concept
    such as ``us:tax/federal-income-tax#eitc`` has no RuleSpec module of its
    own), every legal id and test must at least be in the concept's country.
    ``--resolve`` additionally requires the concept itself whenever it is a
    RuleSpec output on its canonical repository's main or at the pinned commit.
    """

    companion = record.entry.get("axiom_companion")
    if not isinstance(companion, Mapping):
        return []
    legal_ids = companion.get("legal_ids")
    if not isinstance(legal_ids, list) or record.concept in legal_ids:
        return []
    country = _country(record.concept)
    if country is None:
        return []
    problems = [
        f"{record.label()}: companion legal id {legal_id} is outside the "
        f"disputed concept's country ({record.concept})"
        for legal_id in legal_ids
        if _country(legal_id) not in (None, country)
    ]
    for raw in companion.get("tests") or []:
        pointer = CompanionPointer.parse(raw)
        if pointer is not None and not (
            pointer.repo == f"rulespec-{country}"
            or pointer.repo.startswith(f"rulespec-{country}-")
        ):
            problems.append(
                f"{record.label()}: companion test {pointer} is outside "
                f"rulespec-{country} (the disputed concept's country)"
            )
    return problems


_UNAVAILABLE = object()


def _record_eligibility(record: Record) -> bool:
    return bool(record.row_kinds) and all(
        kind in _ELIGIBILITY_KINDS for kind in record.row_kinds
    )


def companion_row_kind_problems(record: Record) -> list[str]:
    if not isinstance(record.entry.get("axiom_companion"), Mapping):
        return []
    types = {kind in _ELIGIBILITY_KINDS for kind in record.row_kinds}
    if len(types) > 1:
        return [
            f"{record.label()}: conflicting actual mismatch row types: "
            f"{record.row_kinds!r}"
        ]
    kind = record.entry.get("kind")
    if types and kind is not None and (kind in _ELIGIBILITY_KINDS) not in types:
        return [
            f"{record.label()}: kind filter {kind!r} conflicts with actual "
            f"mismatch row types: {record.row_kinds!r}"
        ]
    return []


class CompanionResolver:
    """Resolve an entry's Axiom side against the RuleSpec repositories."""

    def __init__(
        self,
        source,
        *,
        require_merged: bool = True,
        issue_source=None,
        fetch_json: Callable[[str], tuple[int, object]] | None = None,
    ):
        self.source = source
        self.require_merged = require_merged
        if issue_source is None and hasattr(source, "issue"):
            issue_source = source
        self.issue_source = issue_source
        self.fetch_json = (
            fetch_json
            or getattr(issue_source, "fetch_json", None)
            or getattr(source, "fetch_json", None)
        )
        self._pe_issues: dict[str, tuple[int, object]] = {}
        self._cache: dict[tuple[str, str, str], object] = {}
        self._merged: dict[tuple[str, str], bool | None] = {}
        self._main: dict[str, str | None] = {}

    def _document(self, repo: str, sha: str, path: str):
        key = (repo, sha, path)
        if key not in self._cache:
            try:
                text = self.source.read(repo, sha, path)
            except SourceUnavailable:
                self._cache[key] = _UNAVAILABLE
            else:
                try:
                    self._cache[key] = None if text is None else yaml.safe_load(text)
                except yaml.YAMLError:
                    self._cache[key] = None
        return self._cache[key]

    def _is_merged(self, repo: str, sha: str) -> bool | None:
        if (repo, sha) not in self._merged:
            self._merged[(repo, sha)] = self.source.is_merged(repo, sha)
        return self._merged[(repo, sha)]

    def _main_sha(self, repo: str) -> str | None:
        if repo not in self._main:
            self._main[repo] = self.source.main_sha(repo)
        return self._main[repo]

    def resolve(self, record: Record) -> list[str]:
        problems = self.resolve_pe_issue(record) + companion_row_kind_problems(record)
        companion = record.entry.get("axiom_companion")
        if not isinstance(companion, Mapping):
            return problems
        legal_ids = [str(x) for x in companion.get("legal_ids") or []]
        concept_module = legal_id_companion_path(record.concept)
        if record.concept not in legal_ids and concept_module is not None:
            # Discover scope independently of the submitted repository/SHA:
            # an older or unrelated pin cannot hide a RuleSpec output on main.
            repo, path = concept_module
            head = self._main_sha(repo)
            if head is None:
                problems.append(
                    f"{record.label()}: cannot read {repo} main to verify "
                    f"the disputed concept {record.concept} (re-run)"
                )
            else:
                module = self._document(repo, head, path)
                if module is _UNAVAILABLE:
                    problems.append(
                        f"{record.label()}: could not fetch {path} on {repo} "
                        f"main to verify the disputed concept {record.concept} "
                        "(transient; re-run)"
                    )
                elif module is not None and _asserts(module, record.concept):
                    problems.append(
                        f"{record.label()}: the disputed concept {record.concept} "
                        f"is a RuleSpec output ({path} asserts it on {repo} "
                        "main); declare it among legal_ids"
                    )
        for raw in companion.get("tests") or []:
            pointer = CompanionPointer.parse(raw)
            if pointer is None:
                continue  # syntax already reported
            label = f"{record.label()} companion {pointer}"
            if self.require_merged:
                merged = self._is_merged(pointer.repo, pointer.sha)
                if merged is None:
                    problems.append(
                        f"{label}: cannot verify the commit is on "
                        f"{pointer.repo} main (GitHub unavailable; re-run)"
                    )
                elif not merged:
                    problems.append(
                        f"{label}: commit is not on {pointer.repo} main"
                    )
            document = self._document(pointer.repo, pointer.sha, pointer.path)
            if document is _UNAVAILABLE:
                problems.append(
                    f"{label}: could not fetch the test file (transient; re-run)"
                )
                continue
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
            # When the disputed concept is itself a RuleSpec output, the
            # companion must declare it, which brings in the value check.
            if (
                record.concept not in legal_ids
                and concept_module is not None
                and concept_module[0] == pointer.repo
            ):
                module = self._document(pointer.repo, pointer.sha, concept_module[1])
                if module is _UNAVAILABLE:
                    problems.append(
                        f"{label}: could not fetch {concept_module[1]} "
                        "(transient; re-run)"
                    )
                elif module is not None and _asserts(module, record.concept):
                    problems.append(
                        f"{label}: the disputed concept {record.concept} is a "
                        f"RuleSpec output ({concept_module[1]} asserts it at "
                        "the pinned commit); declare it among legal_ids"
                    )
            for legal_id in legal_ids:
                if legal_id not in outputs:
                    problems.append(f"{label}: case does not assert {legal_id}")
            if record.concept in legal_ids and record.concept in outputs:
                problems.extend(
                    self._value_problems(
                        label, record, pointer.case, outputs[record.concept]
                    )
                )
            if self.require_merged:
                problems.extend(
                    self._main_problems(label, pointer, legal_ids, outputs, record)
                )
        return problems

    def resolve_pe_issue(self, record: Record) -> list[str]:
        """GitHub's issues endpoint also returns PRs; verify the issue identity.

        Open and closed issues both satisfy the citation requirement. Missing
        grandfathered citations remain governed by the offline presence gate.
        """

        match = (
            PE_LINK_URL_RE.match(record.pe_issue)
            if isinstance(record.pe_issue, str)
            else None
        )
        if match is None or match.group("kind") != "issues":
            return []  # Presence and URL syntax are checked by the offline gate.
        label = f"{record.label()} PolicyEngine issue {record.pe_issue}"
        if self.fetch_json is None:
            return [f"{label}: no GitHub source to verify the issue"]
        repo, number = match.group("repo"), int(match.group("number"))
        url = f"https://api.github.com/repos/PolicyEngine/{repo}/issues/{number}"
        if url not in self._pe_issues:
            try:
                self._pe_issues[url] = self.fetch_json(url)
            except (SourceUnavailable, OSError, ValueError):
                self._pe_issues[url] = (0, None)
        status, payload = self._pe_issues[url]
        if status in (404, 410):
            return [f"{label}: no such issue"]
        if status != 200 or not isinstance(payload, Mapping):
            return [f"{label}: cannot verify the issue (GitHub unavailable; re-run)"]
        if "pull_request" in payload:
            return [f"{label}: is a pull request, not an issue"]
        actual_url = payload.get("html_url")
        actual = (
            PE_LINK_URL_RE.match(actual_url)
            if isinstance(actual_url, str) else None
        )
        if (
            type(payload.get("number")) is not int
            or payload["number"] != number
            or actual is None
            or actual.group("kind") != "issues"
            or actual.group("repo").lower() != repo.lower()
            or int(actual.group("number")) != number
        ):
            return [
                f"{label}: cannot verify the issue identity in the GitHub "
                "response (re-run)"
            ]
        return []

    def _value_problems(
        self, label: str, record: Record, case_name: str, asserted
    ) -> list[str]:
        """A companion case that IS the disputed case must assert the value
        Axiom produced in the comparison, so the dispute is pinned in RuleSpec
        CI, not just described."""

        eligibility = _record_eligibility(record)
        expected = _comparable(asserted)
        if case_name not in record.axiom_values:
            if not eligibility and (expected is None or expected[0] != "number"):
                return [
                    f"{label}: cannot compare {record.concept} = {asserted!r} "
                    "as a numeric amount assertion; pin it with a scalar "
                    "(or one-row) numeric case"
                ]
            return []  # a differently named companion case has its own value
        actual = {_comparable(value) for value in record.axiom_values[case_name]}
        if None in actual or len(actual) != 1:
            return [
                f"{label}: disputed Axiom values for {record.concept} in "
                f"{case_name!r} are unreadable or conflicting: "
                f"{record.axiom_values[case_name]!r}"
            ]
        (value,) = actual
        if expected is None or (
            not eligibility and (expected[0] != "number" or value[0] != "number")
        ):
            return [
                f"{label}: cannot compare {record.concept} = {asserted!r} with "
                f"the disputed Axiom value {value[1]!r}; pin it with a scalar "
                "(or one-row) case"
            ]
        if not _same(expected, value, eligibility=eligibility):
            return [
                f"{label}: case asserts {record.concept} = {expected[1]!r} but "
                f"the disputed Axiom value is {value[1]!r}"
            ]
        return []

    def _main_problems(
        self, label: str, pointer: CompanionPointer, legal_ids, outputs, record: Record
    ) -> list[str]:
        """The pinned case must still be on main, asserting the same values:
        RuleSpec CI runs main, so a case deleted or changed there no longer
        pins anything."""

        head = self._main_sha(pointer.repo)
        if head is None:
            return [
                f"{label}: cannot read {pointer.repo} main to confirm the case "
                "is still there (re-run)"
            ]
        if head == pointer.sha:
            return []
        document = self._document(pointer.repo, head, pointer.path)
        if document is _UNAVAILABLE:
            return [f"{label}: could not fetch the test file on main (transient; re-run)"]
        case = _find_case(document, pointer.case) if document is not None else None
        if case is None:
            return [
                f"{label}: the case is gone from {pointer.repo} main "
                f"({head[:12]}); re-pin the companion or replace it"
            ]
        head_outputs = case.get("output")
        if not isinstance(head_outputs, Mapping):
            head_outputs = {}
        return [
            f"{label}: {pointer.repo} main ({head[:12]}) no longer asserts "
            f"{legal_id} = {outputs[legal_id]!r}; re-pin the companion"
            for legal_id in legal_ids
            if legal_id in outputs
            and not (
                legal_id in head_outputs
                and _same_assertion(
                    head_outputs[legal_id],
                    outputs[legal_id],
                    eligibility=(
                        legal_id == record.concept
                        and _record_eligibility(record)
                    ),
                    numeric=(
                        legal_id == record.concept
                        and not _record_eligibility(record)
                    ),
                )
            )
        ]

    def resolve_debt(self, record: Record) -> list[str]:
        """``axiom_encoding_debt`` must name an open issue in a rulespec repo."""

        url = record.entry.get("axiom_encoding_debt")
        match = RULESPEC_ISSUE_URL_RE.match(url) if isinstance(url, str) else None
        if match is None:
            return []  # syntax already reported
        label = f"{record.label()} axiom_encoding_debt {url}"
        if self.issue_source is None:
            return [f"{label}: no GitHub source to verify the issue"]
        payload = self.issue_source.issue(match.group("repo"), int(match.group("number")))
        if payload is None:
            return [f"{label}: cannot verify the issue (GitHub unavailable; re-run)"]
        if not payload:
            return [f"{label}: no such issue"]
        if payload.get("pull_request") is not None:
            return [f"{label}: is a pull request, not an issue"]
        if payload.get("state") != "open":
            return [
                f"{label}: the issue is closed. If the encoding landed, replace "
                "the debt with axiom_companion; otherwise reopen the issue."
            ]
        return []


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
