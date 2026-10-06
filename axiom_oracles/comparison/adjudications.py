"""Evidence-graded adjudications, verified against immutable source bytes.

All proof atoms are re-read, even on pending records. Readiness additionally
requires evidence appropriate to the verdict and demonstrable legal-year scope.
Engine output is intentionally absent from the proof-atom vocabulary.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

import yaml

SCHEMA = "axiom_oracles.adjudications.v1"
MAINTAINERS_SCHEMA = "axiom_oracles.adjudication-maintainers.v1"
VERDICTS = {
    "taxsim_wrong", "policyengine_wrong", "both_wrong", "convention",
    "input_ambiguity", "open",
}
ATTRIBUTIONS = {"taxsim", "policyengine", "convention", "input", "two_sided"}
STATUSES = {"evidence_ready", "pending_evidence", "open"}
JURISDICTIONS = set(
    "US AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI "
    "MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA "
    "WA WV WI WY AS GU MP PR VI".split()
)
_RECORD_KEYS = {
    "id", "question", "jurisdiction", "law_years", "engines", "verdict",
    "attribution", "status", "issues", "proof_atoms", "notes",
}
_CORPUS_KEYS = {"repository", "commit", "path", "sha256"}
_QUOTE_KEYS = {
    "kind", "corpus", "citation_path", "heading", "excerpt", "applies_to",
    "law_years",
}
_ABSENCE_KEYS = {"kind", "corpus", "citation_path", "body_sha256", "absent_terms"}
_DOCUMENT_KEYS = {
    "kind", "url", "retrieved_on", "snapshot", "snapshot_sha256", "excerpt",
    "establishes_convention",
}
_STATEMENT_KEYS = {
    "kind", "engine", "url", "author", "date", "quote", "snapshot",
    "snapshot_sha256", "acknowledges_error", "establishes_convention",
}
_VERDICT_ATTRIBUTION = {
    "taxsim_wrong": "taxsim", "policyengine_wrong": "policyengine",
    "both_wrong": "two_sided", "convention": "convention",
    "input_ambiguity": "input",
}


class AdjudicationError(ValueError):
    """An adjudication or one of its pinned sources failed verification."""

    def __init__(self, path: str, errors: list[str]) -> None:
        self.path = path
        self.errors = list(errors)
        super().__init__(
            f"invalid adjudications file {path}:\n"
            + "\n".join(f"  - {error}" for error in errors)
        )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _years(value: Any, *, allow_empty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(type(year) is int and 1900 <= year <= 2200 for year in value)
        and len(value) == len(set(value))
    )


def _keys(value: Any, required: set[str], optional: set[str] | None = None) -> None:
    _require(isinstance(value, Mapping), "must be a mapping")
    _require(required <= value.keys(), f"missing fields: {sorted(required - value.keys())}")
    extra = value.keys() - required - (optional or set())
    _require(not extra, f"unknown fields: {sorted(extra)}")


def _url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _github_thread(value: str) -> tuple[str, str, int] | None:
    """Canonicalize GitHub's issue/PR aliases without trusting unrelated URLs."""
    parsed = urlparse(value)
    match = re.fullmatch(r"/([^/]+)/([^/]+)/(?:issues|pull)/([0-9]+)/?", parsed.path)
    if parsed.hostname != "github.com" or match is None:
        return None
    owner, repository, number = match.groups()
    return owner.casefold(), repository.casefold(), int(number)


def _digest(value: Any, length: int = 64) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(f"[0-9a-f]{{{length}}}", value))


def _relative_path(value: Any) -> bool:
    return (
        _text(value)
        and not PurePosixPath(value).is_absolute()
        and ".." not in PurePosixPath(value).parts
        and "\\" not in value
        and value == PurePosixPath(value).as_posix()
    )


def _git(root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, check=False,
    )
    if completed.returncode:
        raise ValueError(f"corpus git {' '.join(args)} failed: {completed.stderr.decode().strip()}")
    return completed.stdout


def find_corpus_root(repo_root: Path, corpus_root: Path | None = None) -> Path:
    """Resolve explicit/configured roots without a broad filesystem search."""
    if corpus_root is not None:
        return Path(corpus_root)
    if configured := os.environ.get("AXIOM_CORPUS_ROOT"):
        return Path(configured)
    for candidate in (repo_root / ".ci/axiom-corpus", repo_root.parent / "axiom-corpus"):
        if candidate.is_dir():
            return candidate
    raise ValueError("corpus checkout required; set AXIOM_CORPUS_ROOT or --corpus-root")


def _source_years(row: Mapping[str, Any]) -> set[int]:
    """Only explicit law/tax-year metadata establishes historical applicability.

    Retrieval dates and current-law version labels are deliberately insufficient.
    """
    result: set[int] = set()
    for source in (row, row.get("metadata", {})):
        if not isinstance(source, Mapping):
            continue
        for field in ("law_years", "tax_years"):
            if _years(source.get(field)):
                result.update(source[field])
        for field in ("law_year", "tax_year"):
            value = source.get(field)
            if type(value) is int and 1900 <= value <= 2200:
                result.add(value)
    return result


@dataclass(frozen=True)
class _Evidence:
    kind: str
    legal_years: frozenset[int] = frozenset()
    error_engine: str | None = None
    convention: bool = False
    body: str = ""
    scope_verified: bool = True


class _Verifier:
    def __init__(
        self, repo_root: Path, corpus_root: Path | None, maintainers_path: Path,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.corpus_root = corpus_root
        self.blobs: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        self.config = yaml.safe_load(maintainers_path.read_text())
        _keys(self.config, {"schema", "engines"}, {"official_document_hosts", "notes"})
        _require(self.config["schema"] == MAINTAINERS_SCHEMA, "invalid maintainers schema")
        _require(isinstance(self.config["engines"], Mapping), "maintainers engines must be a mapping")
        for engine, details in self.config["engines"].items():
            _require(isinstance(details, Mapping), f"maintainers {engine} must be a mapping")
            names = details.get("maintainers")
            _require(
                isinstance(names, list) and bool(names)
                and all(_text(name) for name in names) and len(names) == len(set(names)),
                f"maintainers {engine} needs unique author names",
            )
        hosts = self.config.get("official_document_hosts", [])
        _require(isinstance(hosts, list) and all(_text(host) for host in hosts), "official_document_hosts must be a list")

    def snapshot(self, atom: Mapping[str, Any]) -> str:
        relative = atom["snapshot"]
        _require(_relative_path(relative), "snapshot must be a repository-relative path")
        path = (self.repo_root / relative).resolve()
        _require(path.is_relative_to(self.repo_root), "snapshot escapes repository")
        raw = path.read_bytes()
        digest = atom["snapshot_sha256"]
        _require(_digest(digest), "snapshot_sha256 must be 64 lowercase hex characters")
        _require(hashlib.sha256(raw).hexdigest() == digest, "snapshot sha256 mismatch")
        return raw.decode("utf-8")

    def provision(self, atom: Mapping[str, Any]) -> tuple[dict[str, Any], set[int]]:
        source = atom["corpus"]
        _keys(source, _CORPUS_KEYS)
        _require(source["repository"] == "TheAxiomFoundation/axiom-corpus", "unrecognized corpus repository")
        commit, path, digest = source["commit"], source["path"], source["sha256"]
        _require(_digest(commit, 40), "corpus commit must be 40 lowercase hex characters")
        _require(_relative_path(path) and path.endswith(".jsonl"), "corpus path must be a tracked relative JSONL path")
        _require(_digest(digest), "corpus sha256 must be 64 lowercase hex characters")
        key = (commit, path, digest)
        if key not in self.blobs:
            root = find_corpus_root(self.repo_root, self.corpus_root)
            resolved = _git(root, "rev-parse", f"{commit}^{{commit}}").decode().strip()
            _require(resolved == commit, "corpus commit did not resolve to its pinned commit")
            # A mainline pin is required even when the local working tree differs.
            _git(root, "merge-base", "--is-ancestor", commit, "origin/main")
            tracked = _git(root, "ls-tree", "-z", "--name-only", commit, "--", path)
            _require(tracked == path.encode() + b"\0", "corpus JSONL path is not tracked at pinned commit")
            raw = _git(root, "show", f"{commit}:{path}")
            _require(hashlib.sha256(raw).hexdigest() == digest, "corpus blob sha256 mismatch")
            rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
            _require(all(isinstance(row, dict) for row in rows), "corpus JSONL rows must be mappings")
            self.blobs[key] = rows
        citation = atom["citation_path"]
        _require(_text(citation), "citation_path must be nonempty")
        rows = self.blobs[key]
        matches = [row for row in rows if row.get("citation_path") == citation]
        _require(len(matches) == 1, "citation_path must resolve to exactly one pinned provision")
        row = matches[0]
        _require(_text(row.get("body")), "pinned provision must have a nonempty body")
        years = _source_years(row)
        for parent in rows if not years else []:
            parent_citation = parent.get("citation_path")
            if (
                parent.get("kind") == "document" and isinstance(parent_citation, str)
                and citation.startswith(parent_citation + "/")
            ):
                years.update(_source_years(parent))
        return row, years

    def atom(self, atom: Any) -> _Evidence:
        _require(isinstance(atom, Mapping), "proof atom must be a mapping")
        kind = atom.get("kind")
        if kind == "corpus_quote":
            _keys(atom, _QUOTE_KEYS)
            row, source_years = self.provision(atom)
            _require(_text(atom["heading"]) and atom["heading"] == row.get("heading"), "heading differs from pinned provision heading")
            _require(_text(atom["excerpt"]) and atom["excerpt"] in row["body"], "excerpt does not occur verbatim in pinned provision body")
            _require(_text(atom["applies_to"]), "applies_to must describe the quote's scope")
            _require(_years(atom["law_years"]), "corpus quote law_years must be nonempty unique years")
            return _Evidence(
                kind, frozenset(source_years & set(atom["law_years"])),
                body=row["body"], scope_verified=set(atom["law_years"]) <= source_years,
            )
        if kind == "corpus_absence":
            _keys(atom, _ABSENCE_KEYS)
            row, years = self.provision(atom)
            _require(_digest(atom["body_sha256"]), "body_sha256 must be 64 lowercase hex characters")
            _require(hashlib.sha256(row["body"].encode()).hexdigest() == atom["body_sha256"], "full provision body_sha256 mismatch")
            terms = atom["absent_terms"]
            _require(isinstance(terms, list) and bool(terms) and all(_text(term) for term in terms), "absent_terms must be nonempty strings")
            for term in terms:
                _require(term.casefold() not in row["body"].casefold(), f"absent term {term!r} occurs in full provision body")
            return _Evidence(kind, frozenset(years), body=row["body"])
        if kind == "year_change":
            _keys(atom, {"kind", "before", "after", "changed_text"})
            for side in ("before", "after"):
                _require(isinstance(atom[side], Mapping) and atom[side].get("kind") == "corpus_quote", f"year_change {side} must be a corpus_quote")
            before, after = self.atom(atom["before"]), self.atom(atom["after"])
            before_years, after_years = set(atom["before"]["law_years"]), set(atom["after"]["law_years"])
            _require(not before_years & after_years, "year_change requires different nonoverlapping law years")
            diff = "".join(difflib.unified_diff(
                before.body.splitlines(keepends=True), after.body.splitlines(keepends=True),
                fromfile="before", tofile="after",
            ))
            _require(bool(diff), "year_change documents have no changed text")
            _require(atom["changed_text"] == diff, "changed_text differs from computed full provision diff")
            return _Evidence(
                kind, before.legal_years | after.legal_years,
                scope_verified=before.scope_verified and after.scope_verified,
            )
        if kind == "document_quote":
            _keys(atom, _DOCUMENT_KEYS - {"establishes_convention"}, {"establishes_convention"})
            _require(_url(atom["url"]), "document url must be HTTPS")
            host = urlparse(atom["url"]).hostname or ""
            allowed = set(self.config.get("official_document_hosts", []))
            _require(host.endswith(".gov") or host == "nber.org" or host.endswith(".nber.org") or host in allowed, "document quote must cite an official document host")
            date.fromisoformat(str(atom["retrieved_on"]))
            snapshot = self.snapshot(atom)
            _require(_text(atom["excerpt"]) and atom["excerpt"] in snapshot, "excerpt does not occur verbatim in document snapshot")
            self.support_flags(atom)
            return _Evidence(kind, convention=atom.get("establishes_convention") is True)
        if kind == "maintainer_statement":
            _keys(atom, _STATEMENT_KEYS - {"acknowledges_error", "establishes_convention"}, {"acknowledges_error", "establishes_convention"})
            engine, author = atom["engine"], atom["author"]
            _require(_text(engine) and engine in self.config["engines"], "statement engine has no maintainer configuration")
            _require(author in self.config["engines"][engine]["maintainers"], "statement author is not a configured maintainer of that engine")
            _require(_url(atom["url"]), "maintainer statement url must be HTTPS")
            parsed_url = urlparse(atom["url"])
            _require(
                parsed_url.hostname == "github.com"
                and _github_thread(atom["url"]) is not None
                and bool(re.fullmatch(r"issuecomment-[0-9]+", parsed_url.fragment)),
                "maintainer statement must reference a GitHub issue comment snapshot",
            )
            snapshot = json.loads(self.snapshot(atom))
            _keys(snapshot, {"url", "author", "createdAt", "body"})
            _require(snapshot["author"] == author, "statement author differs from snapshot author")
            _require(snapshot["url"] == atom["url"], "statement url differs from snapshot url")
            created = datetime.fromisoformat(str(snapshot["createdAt"]).replace("Z", "+00:00"))
            stated = str(atom["date"])
            _require(stated == str(snapshot["createdAt"]) or stated == created.date().isoformat(), "statement date differs from snapshot createdAt")
            quote = atom["quote"]
            _require(_text(quote) and len(quote.split()) <= 60, "maintainer quote must contain 1 to 60 words")
            _require(isinstance(snapshot["body"], str) and quote in snapshot["body"], "quote does not occur verbatim in snapshot comment body")
            self.support_flags(atom)
            return _Evidence(
                kind, error_engine=engine if atom.get("acknowledges_error") is True else None,
                convention=atom.get("establishes_convention") is True,
            )
        raise ValueError(f"unsupported proof-atom kind {kind!r}; engine outputs are not evidence")

    @staticmethod
    def support_flags(atom: Mapping[str, Any]) -> None:
        for flag in ("acknowledges_error", "establishes_convention"):
            if flag in atom:
                _require(type(atom[flag]) is bool, f"{flag} must be boolean")


def _readiness(record: Mapping[str, Any], evidence: list[_Evidence]) -> list[str]:
    problems = []
    years = set(record["law_years"])
    if not years:
        problems.append("evidence_ready requires nonempty law_years")
    verdict = record["verdict"]
    if verdict == "open":
        problems.append("open verdict cannot be evidence_ready")
    for atom in evidence:
        if not atom.scope_verified or (
            atom.kind == "corpus_absence" and not years <= atom.legal_years
        ):
            problems.append("corpus atom lacks independently established applicability to its claimed law years")
    legal_years = set().union(*(atom.legal_years for atom in evidence))
    legal = bool(years) and years <= legal_years
    error_engines = {atom.error_engine for atom in evidence}
    for engine in ("taxsim", "policyengine"):
        if verdict in (f"{engine}_wrong", "both_wrong") and not legal and engine not in error_engines:
            problems.append(f"{verdict} requires legal evidence applicable to all law_years or {engine} maintainer acknowledgement")
    if verdict in ("convention", "input_ambiguity") and not any(atom.convention for atom in evidence):
        problems.append(f"{verdict} requires a maintainer statement or official document establishing the convention")
    return problems


def validate_adjudications(
    document: Any, *, repo_root: Path | None = None, corpus_root: Path | None = None,
    maintainers_path: Path | None = None,
) -> list[str]:
    """Return schema/source/readiness errors, verifying every atom each call."""
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    config = maintainers_path or root / "adjudications/maintainers.yaml"
    errors: list[str] = []
    try:
        _keys(document, {"schema", "adjudications"})
        _require(document["schema"] == SCHEMA, f"schema must be {SCHEMA}")
        _require(isinstance(document["adjudications"], list), "adjudications must be a list")
        verifier = _Verifier(root, corpus_root, Path(config))
    except (ValueError, OSError, yaml.YAMLError) as exc:
        return [str(exc)]
    seen: set[str] = set()
    for index, record in enumerate(document["adjudications"]):
        label = f"adjudications[{index}]"
        try:
            _keys(record, _RECORD_KEYS)
            label = f"adjudication {record['id']!r}"
            _require(_text(record["id"]) and bool(re.fullmatch(r"[a-z0-9][a-z0-9-]*", record["id"])), "id must be a lowercase slug")
            _require(record["id"] not in seen, "duplicate adjudication id")
            seen.add(record["id"])
            _require(_text(record["question"]), "question must be nonempty")
            _require(record["jurisdiction"] in JURISDICTIONS, "jurisdiction must be US or a USPS code")
            _require(_years(record["law_years"], allow_empty=True), "law_years must be unique integer years")
            engines = record["engines"]
            _require(isinstance(engines, list) and bool(engines) and all(engine in verifier.config["engines"] for engine in engines) and len(engines) == len(set(engines)), "engines must name unique configured engines")
            _require(record["verdict"] in VERDICTS, "invalid verdict")
            for engine in ("taxsim", "policyengine"):
                if record["verdict"] in (f"{engine}_wrong", "both_wrong"):
                    _require(engine in engines, f"{record['verdict']} requires {engine} in engines")
            _require(record["attribution"] in ATTRIBUTIONS, "invalid attribution")
            expected = _VERDICT_ATTRIBUTION.get(record["verdict"])
            _require(expected is None or record["attribution"] == expected, "verdict and attribution are inconsistent")
            _require(record["status"] in STATUSES, "invalid status")
            _require(record["status"] != "open" or record["verdict"] == "open", "open status requires open verdict")
            _require(isinstance(record["issues"], list) and all(_url(url) for url in record["issues"]), "issues must be HTTPS URLs")
            _require(isinstance(record["notes"], str), "notes must be a string")
            _require(isinstance(record["proof_atoms"], list), "proof_atoms must be a list")
            _require(record["verdict"] == "open" or bool(record["proof_atoms"]), "non-open verdict requires at least one proof atom")
        except (ValueError, TypeError) as exc:
            errors.append(f"{label}: {exc}")
            continue
        evidence = []
        for atom_index, atom in enumerate(record["proof_atoms"]):
            try:
                evidence.append(verifier.atom(atom))
                if atom.get("kind") == "maintainer_statement":
                    _require(atom["engine"] in engines, "statement engine is absent from record engines")
                    _require(
                        _github_thread(atom["url"]) in {
                            _github_thread(url) for url in record["issues"]
                        },
                        "maintainer statement issue must be listed in record issues",
                    )
            except (ValueError, OSError, TypeError, KeyError) as exc:
                errors.append(f"{label} proof_atoms[{atom_index}]: {exc}")
        if record["status"] == "evidence_ready":
            errors.extend(f"{label}: {problem}" for problem in _readiness(record, evidence))
    return errors


def load_adjudications(
    path: str | Path, *, repo_root: Path | None = None, corpus_root: Path | None = None,
    maintainers_path: Path | None = None,
) -> dict[str, Any]:
    """Read YAML and verify schema, pinned sources and evidence grading."""
    path = Path(path)
    try:
        document = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise AdjudicationError(str(path), [str(exc)]) from exc
    errors = validate_adjudications(
        document, repo_root=repo_root, corpus_root=corpus_root,
        maintainers_path=maintainers_path,
    )
    if errors:
        raise AdjudicationError(str(path), errors)
    return document
