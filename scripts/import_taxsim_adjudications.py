#!/usr/bin/env python3
"""Import the reviewed TAXSIM census, or refresh its public summary.

The private census is only needed with --census. Without it, --check verifies the
deterministic import summary and documentation against the public registry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = Path("adjudications/taxsim-emulator.yaml")
DECISIONS = Path("adjudications/taxsim-import-decisions.json")
SPECIALS = Path("adjudications/taxsim-special-records.json")
SUMMARY = Path("reports/taxsim-emulator/adjudication-summary.json")
DOC = Path("docs/taxsim-adjudications.md")
ATTRIBUTIONS = {
    "taxsim_wrong": "taxsim", "policyengine_wrong": "policyengine",
    "both_wrong": "two_sided", "convention": "convention",
    "input_ambiguity": "input", "open": "two_sided",
}


def json_text(value: object) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def changed_file(path: Path, text: str, check: bool) -> bool:
    if path.exists() and path.read_text() == text:
        return False
    if check:
        print(f"STALE {path.relative_to(ROOT)}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        print(f"WROTE {path.relative_to(ROOT)}")
    return True


def import_census(census: Path, review: dict, check: bool) -> bool:
    """Regenerate the registry using mechanically pinned reviewed inputs."""
    for name, expected in review["input_sha256"].items():
        if digest((census / name).read_bytes()) != expected:
            raise ValueError(f"Census input changed since review: {name}")
    candidates = json.loads((census / "rule_level.json").read_text())
    issues = {row["number"]: row for row in json.loads((census / "issues.json").read_text())}
    specials = json.loads((ROOT / SPECIALS).read_text())
    special_ids = {record["id"] for record in specials}
    records = []
    stale = False
    for candidate in candidates:
        number = candidate["number"]
        if f"pe-taxsim-{number}" in special_ids:
            continue
        issue = issues[number]
        decision = review["decisions"].get(str(number), {})
        verdict = decision.get("verdict", "open")
        years = decision.get("years")
        if years is None:
            years = sorted({int(year) for year in re.findall(r"\b20\d{2}\b", issue["title"])})
        note = decision.get("note", "No explicit admissible maintainer verdict was found in the reviewed issue and comments. Numerical alignment, closure, links, and issue-body legal allegations do not establish an adjudication.")
        if candidate["candidate_disposition"] != "unexplained":
            note += " Included in the census's 111 proposed non-unexplained candidates; the proposal is not evidence."
        jurisdictions = candidate.get("jurisdictions", [])
        jurisdiction = decision.get("jurisdiction") or candidate["jurisdiction"]
        if jurisdiction is None:
            jurisdiction = "US" if "US" in jurisdictions else jurisdictions[0]
        if len(jurisdictions) > 1:
            note += " Thread also discusses jurisdiction(s): " + ", ".join(jurisdictions) + ". The record's jurisdiction limits its adjudicated scope."
        atoms = []
        comment_index = decision.get("comment")
        # An open question has no adjudicative proof. Keeping its review quote
        # in the manifest preserves the review without laundering output-only
        # agreement, a retraction, or issue closure into an evidence atom.
        if comment_index is not None and verdict != "open":
            comments = json.loads((census / "comments" / f"{number}.json").read_text())["comments"]
            comment = comments[comment_index]
            author = comment["author"]["login"]
            engine = "taxsim" if author == "feenberg" else "policyengine"
            quote = decision["quote"]
            if not quote or quote not in comment["body"] or len(quote.split()) > 60:
                raise ValueError(f"Invalid curated quote for #{number}")
            snapshot = {
                "url": comment["url"], "author": author,
                "createdAt": comment["createdAt"], "body": comment["body"],
            }
            relative = Path("adjudications/snapshots") / f"pe-taxsim-{number}-{comment['url'].rsplit('-', 1)[1]}.json"
            content = json_text(snapshot)
            stale |= changed_file(ROOT / relative, content, check)
            atom = {
                "kind": "maintainer_statement", "engine": engine,
                "url": comment["url"], "author": author,
                "date": comment["createdAt"][:10], "quote": quote,
                "snapshot": relative.as_posix(), "snapshot_sha256": digest(content.encode()),
            }
            if decision.get("ready"):
                if verdict == f"{engine}_wrong":
                    atom["acknowledges_error"] = True
                if verdict in {"convention", "input_ambiguity"}:
                    atom["establishes_convention"] = True
            atoms.append(atom)
        ready = decision.get("ready") and bool(years) and bool(atoms) and verdict != "open"
        if ready and verdict.endswith("_wrong"):
            ready = any(atom.get("acknowledges_error") for atom in atoms)
        records.append({
            "id": f"pe-taxsim-{number}", "question": decision.get("question", issue["title"]),
            "jurisdiction": jurisdiction,
            "law_years": years, "engines": ["taxsim", "policyengine"],
            "verdict": verdict, "attribution": decision.get("attribution") or ATTRIBUTIONS[verdict],
            "status": "evidence_ready" if ready else ("open" if verdict == "open" else "pending_evidence"),
            "issues": [candidate["url"]], "proof_atoms": atoms, "notes": note,
        })
    by_id = {record["id"]: record for record in records}
    for issue, jurisdictions in review["jurisdiction_splits"].items():
        source = by_id[f"pe-taxsim-{issue}"]
        source["jurisdiction"] = jurisdictions[0]
        for jurisdiction in jurisdictions[1:]:
            clone = dict(source)
            clone.update(id=f"pe-taxsim-{issue}-{jurisdiction.lower()}", jurisdiction=jurisdiction)
            by_id[clone["id"]] = clone
    for record in specials:
        by_id[record["id"]] = record
    document = {"schema": "axiom_oracles.adjudications.v1", "adjudications": sorted(by_id.values(), key=lambda row: (int(row["id"].split("-")[2]), row["id"]))}
    needed_snapshots = {
        atom["snapshot"] for record in by_id.values() for atom in record["proof_atoms"]
        if atom["kind"] == "maintainer_statement"
    }
    for snapshot in (ROOT / "adjudications/snapshots").glob("pe-taxsim-*.json"):
        if snapshot.relative_to(ROOT).as_posix() not in needed_snapshots:
            stale = True
            print(f"{'STALE' if check else 'REMOVE'} {snapshot.relative_to(ROOT)}")
            if not check:
                snapshot.unlink()
    stale |= changed_file(ROOT / REGISTRY, yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100), check)
    return stale


def summary_data(records: list[dict], review: dict) -> dict:
    return {
        "schema": "axiom_oracles.adjudication-summary.v1",
        "reviewed_candidates": review["reviewed_candidates"],
        "reviewed_comments": review["reviewed_comments"],
        "mandatory_candidate_count": len(review["mandatory_candidate_ids"]),
        "registry_records": len(records),
        "evidence_ready": sum(row["status"] == "evidence_ready" for row in records),
        **{f"by_{field}": dict(sorted(Counter(row[field] for row in records).items()))
           for field in ("status", "verdict", "attribution", "jurisdiction")},
        "evidence_ready_records": [
            {"id": row["id"], "jurisdiction": row["jurisdiction"], "law_years": row["law_years"],
             "verdict": row["verdict"], "attribution": row["attribution"],
             "atoms": [{key: atom[key] for key in ("kind", "url", "author", "quote", "citation_path", "excerpt") if key in atom}
                       for atom in row["proof_atoms"]]}
            for row in records if row["status"] == "evidence_ready"
        ],
    }


def markdown_summary(summary: dict) -> str:
    lines = [
        f"Reviewed **{summary['reviewed_candidates']} candidate issues and {summary['reviewed_comments']:,} comments**. "
        f"All **{summary['mandatory_candidate_count']}** proposed non-unexplained census candidates are retained. "
        f"The registry has **{summary['registry_records']} records**, including jurisdiction splits and the separate state-zero probe; "
        f"**{summary['evidence_ready']} are evidence_ready**.",
        "", "| Dimension | Value | Records |", "|---|---|---:|",
    ]
    for field in ("status", "verdict", "attribution", "jurisdiction"):
        lines.extend(f"| {field} | `{value}` | {count} |" for value, count in summary[f"by_{field}"].items())
    return "\n".join(lines)


def markdown_ready(records: list[dict]) -> str:
    lines = ["| Record | Scope | Verdict | Verified atoms |", "|---|---|---|---|"]
    for row in records:
        if row["status"] != "evidence_ready":
            continue
        atoms = []
        for atom in row["proof_atoms"]:
            label = atom["kind"]
            if atom.get("author"):
                label += f" ({atom['author']}, {atom['date']})"
            if atom.get("url"):
                atoms.append(f"[{label}]({atom['url']})")
            else:
                atoms.append(f"{label}: `{atom.get('citation_path', '')}`")
        years = ", ".join(map(str, row["law_years"]))
        lines.append(f"| `{row['id']}` | {row['jurisdiction']} {years} | `{row['verdict']}` | {'; '.join(atoms)} |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--census", type=Path, help="Regenerate registry from the pinned read-only source census")
    args = parser.parse_args()
    review = json.loads((ROOT / DECISIONS).read_text())
    stale = import_census(args.census, review, args.check) if args.census else False
    records = yaml.safe_load((ROOT / REGISTRY).read_text())["adjudications"]
    ids = {row["id"] for row in records}
    if not set(review["candidate_ids"]) <= ids:
        raise ValueError("Registry lost reviewed census candidate coverage")
    summary = summary_data(records, review)
    stale |= changed_file(ROOT / SUMMARY, json_text(summary), args.check)
    doc = (ROOT / DOC).read_text()
    for marker, body in (("IMPORT SUMMARY", markdown_summary(summary)), ("READY RECORDS", markdown_ready(records))):
        pattern = rf"(<!-- BEGIN {marker} -->).*?(<!-- END {marker} -->)"
        doc, count = re.subn(pattern, lambda match: match[1] + "\n\n" + body + "\n\n" + match[2], doc, flags=re.S)
        if count != 1:
            raise ValueError(f"Missing or repeated documentation marker {marker}")
    stale |= changed_file(ROOT / DOC, doc, args.check)
    if not stale:
        print(f"OK adjudication import summary: {len(records)} records, {summary['evidence_ready']} evidence_ready")
    return int(args.check and stale)


if __name__ == "__main__":
    raise SystemExit(main())
