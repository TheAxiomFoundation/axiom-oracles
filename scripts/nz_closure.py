#!/usr/bin/env python3
"""Compute NZ RuleSpec closure against the pinned corpus release by citation path."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
from nz_programs import PROGRAM_VIEWS  # noqa: E402

OUT_DIR = REPO_ROOT / "closure" / "nz"
SOURCE_PATH = OUT_DIR / "source.json"
SUMMARY_PATH = OUT_DIR / "summary.json"
SOURCE_SHA256 = "a69b872fbc9fd9a98132ea5b7f5272d8be9631d3060651603b2b3c1f7cd64aea"
RULESPEC_REPO = Path("/Users/maxghenis/TheAxiomFoundation/rulespec-nz")
CORPUS_REPO = Path("/Users/maxghenis/TheAxiomFoundation/axiom-corpus")
RULESPEC_SHA = "89a7d25dc03a4d045348620283332de10b1047da"
CORPUS_RELEASE_REF = "origin/release/nz-rulespec-2026-07-18"
CORPUS_RELEASE_SHA = "3f7b5d985bce759cb487f1b7fd050f5cbf007d17"
ROOTS = ("nz/statutes", "nz/regulations", "nz/policies")
CORPUS_FILES = (
    "data/corpus/provisions/nz/statute/2026-06-16-rulespec-nz-pco.jsonl",
    "data/corpus/provisions/nz/regulation/2026-06-16-rulespec-nz-pco.jsonl",
    "data/corpus/provisions/nz/district-plan/2026-07-18-wellington-district-plan.jsonl",
)
LEDGER_REPO_PATH = "known-missing-money-atoms.yaml"


class ClosureError(ValueError):
    pass


def _git(repo: Path, *args: str) -> str:
    process = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if process.returncode:
        raise ClosureError(process.stderr.strip() or process.stdout.strip())
    return process.stdout


def _citations(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "corpus_citation_path" and isinstance(child, str):
                found.add(child)
            found.update(_citations(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_citations(child))
    return found


def _formula_texts(value: object) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "formula" and isinstance(child, str):
                found.append(child)
            else:
                found.extend(_formula_texts(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_formula_texts(child))
    return found


def _list_sha256(values: list[str]) -> str:
    raw = json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _node_id(path: str, name: str) -> str:
    module = path.removeprefix("nz/").removesuffix(".yaml")
    return f"nz:{module}#{name}"


def load_source() -> dict:
    """Load the versioned denominator only when its review pin still matches."""

    try:
        raw = SOURCE_PATH.read_bytes()
        if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
            raise ClosureError(
                "NZ closure source bytes changed; review and re-pin the denominator"
            )
        source = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ClosureError(f"cannot read the NZ closure source: {exc}") from exc
    if not isinstance(source, dict):
        raise ClosureError("NZ closure source must contain an object")
    return source


def bootstrap_source() -> dict:
    if _git(RULESPEC_REPO, "rev-parse", RULESPEC_SHA).strip() != RULESPEC_SHA:
        raise ClosureError("pinned RuleSpec commit is unavailable")
    if _git(CORPUS_REPO, "rev-parse", CORPUS_RELEASE_REF).strip() != CORPUS_RELEASE_SHA:
        raise ClosureError("pinned corpus release ref moved or is unavailable")
    parsed_files: list[tuple[str, object]] = []
    rule_names: set[str] = set()
    for path in _git(
        RULESPEC_REPO,
        "ls-tree", "-r", "--name-only", RULESPEC_SHA, "--", *ROOTS,
    ).splitlines():
        raw = _git(RULESPEC_REPO, "show", f"{RULESPEC_SHA}:{path}")
        try:
            document = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise ClosureError(f"{path}: invalid YAML at pinned commit: {exc}") from exc
        parsed_files.append((path, document))
        rules = document.get("rules") or [] if isinstance(document, dict) else []
        for rule in rules:
            if not isinstance(rule, dict) or not isinstance(rule.get("name"), str):
                raise ClosureError(f"{path}: rule without a string name")
            name = rule["name"]
            if name in rule_names:
                raise ClosureError(f"duplicate RuleSpec rule name {name!r}")
            rule_names.add(name)
    files: list[dict] = []
    for path, document in parsed_files:
        nodes = []
        rules = document.get("rules") or [] if isinstance(document, dict) else []
        for rule in rules:
            name = rule["name"]
            citations = sorted(_citations(rule))
            tokens = {
                token
                for formula in _formula_texts(rule)
                for token in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", formula)
            }
            dependencies = sorted((tokens & rule_names) - {name})
            nodes.append(
                {
                    "id": _node_id(path, name),
                    "name": name,
                    "citations": citations,
                    "citations_sha256": _list_sha256(citations),
                    "dependencies": dependencies,
                    "dependencies_sha256": _list_sha256(dependencies),
                }
            )
        files.append(
            {
                "path": path,
                "citations": sorted(_citations(document)),
                "nodes": nodes,
            }
        )
    corpus_paths: set[str] = set()
    for path in CORPUS_FILES:
        for line_number, line in enumerate(
            _git(CORPUS_REPO, "show", f"{CORPUS_RELEASE_REF}:{path}").splitlines(), 1
        ):
            try:
                row = json.loads(line)
                citation = row["citation_path"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise ClosureError(f"{path}:{line_number}: invalid provision row") from exc
            if citation in corpus_paths:
                raise ClosureError(f"duplicate corpus citation path {citation!r}")
            corpus_paths.add(citation)
    ledger_raw = _git(RULESPEC_REPO, "show", f"{RULESPEC_SHA}:{LEDGER_REPO_PATH}")
    ledger = yaml.safe_load(ledger_raw)
    return {
        "schema": "axiom_oracles.nz_closure_source.v2",
        "rulespec": {
            "repository": "TheAxiomFoundation/rulespec-nz",
            "commit": RULESPEC_SHA,
            "roots": list(ROOTS),
            "files": files,
        },
        "program_roots": {
            program: sorted(spec["roots"])
            for program, spec in sorted(PROGRAM_VIEWS.items())
        },
        "corpus": {
            "repository": "TheAxiomFoundation/axiom-corpus",
            "release": "nz-rulespec-2026-07-18",
            "commit": CORPUS_RELEASE_SHA,
            "provision_sources": list(CORPUS_FILES),
            "citation_paths": sorted(corpus_paths),
        },
        "pending_ledger": {
            "source": f"TheAxiomFoundation/rulespec-nz/{LEDGER_REPO_PATH}",
            "sha256": hashlib.sha256(ledger_raw.encode()).hexdigest(),
            "document": ledger,
        },
    }


def build(source: dict) -> dict:
    if source.get("schema") != "axiom_oracles.nz_closure_source.v2":
        raise ClosureError("unexpected NZ closure source schema")
    rulespec = source.get("rulespec") or {}
    corpus = source.get("corpus") or {}
    ledger = source.get("pending_ledger") or {}
    if rulespec.get("commit") != RULESPEC_SHA or tuple(rulespec.get("roots") or ()) != ROOTS:
        raise ClosureError("NZ closure RuleSpec pin or declared roots drifted")
    if (
        corpus.get("release") != "nz-rulespec-2026-07-18"
        or corpus.get("commit") != CORPUS_RELEASE_SHA
    ):
        raise ClosureError("NZ closure corpus release pin drifted")
    if (ledger.get("document") or {}).get("total_allowed") != 0:
        raise ClosureError("known-missing-money-atoms ceiling rose above zero")
    corpus_paths = corpus.get("citation_paths") or []
    if corpus_paths != sorted(set(corpus_paths)):
        raise ClosureError("corpus citation paths must be unique and sorted")
    corpus_set = set(corpus_paths)
    files = rulespec.get("files") or []
    paths = [row.get("path") for row in files if isinstance(row, dict)]
    if paths != sorted(set(paths)):
        raise ClosureError("RuleSpec file inventory must be unique and sorted")
    expected_program_roots = {
        program: sorted(spec["roots"])
        for program, spec in sorted(PROGRAM_VIEWS.items())
    }
    if source.get("program_roots") != expected_program_roots:
        raise ClosureError("NZ program root sets drifted from the ratified node views")
    nodes_by_id: dict[str, dict] = {}
    nodes_by_name: dict[str, dict] = {}
    for row in files:
        file_citations = row.get("citations")
        if not isinstance(file_citations, list) or file_citations != sorted(
            set(file_citations)
        ):
            raise ClosureError(f"{row.get('path')}: citations must be unique and sorted")
        for node in row.get("nodes") or []:
            if not isinstance(node, dict):
                raise ClosureError(f"{row.get('path')}: invalid node entry")
            node_id = node.get("id")
            name = node.get("name")
            if not isinstance(node_id, str) or not isinstance(name, str):
                raise ClosureError(f"{row.get('path')}: node lacks id or name")
            if node_id != _node_id(row["path"], name):
                raise ClosureError(f"{node_id}: node id does not match its RuleSpec path")
            if node_id in nodes_by_id or name in nodes_by_name:
                raise ClosureError(f"duplicate RuleSpec node {node_id!r}")
            citations = node.get("citations")
            dependencies = node.get("dependencies")
            if not isinstance(citations, list) or citations != sorted(set(citations)):
                raise ClosureError(f"{node_id}: citations must be unique and sorted")
            if node.get("citations_sha256") != _list_sha256(citations):
                raise ClosureError(f"{node_id}: cited path was dropped or changed")
            if not set(citations).issubset(file_citations):
                raise ClosureError(f"{node_id}: node citation missing from its file census")
            if not isinstance(dependencies, list) or dependencies != sorted(
                set(dependencies)
            ):
                raise ClosureError(f"{node_id}: dependencies must be unique and sorted")
            if node.get("dependencies_sha256") != _list_sha256(dependencies):
                raise ClosureError(f"{node_id}: dependency edge was dropped or changed")
            nodes_by_id[node_id] = node
            nodes_by_name[name] = node
    for node_id, node in nodes_by_id.items():
        missing_dependencies = set(node["dependencies"]) - set(nodes_by_name)
        if missing_dependencies:
            raise ClosureError(
                f"{node_id}: missing dependency node(s) {sorted(missing_dependencies)}"
            )
    summaries = []
    all_pending: set[str] = set()
    for root in ROOTS:
        root_files = [row for row in files if str(row.get("path", "")).startswith(root + "/")]
        classifications = []
        for row in root_files:
            citations = row.get("citations")
            missing = sorted(set(citations) - corpus_set)
            all_pending.update(missing)
            if missing:
                status, reason = "pending", "citation_absent_from_pinned_corpus_release"
            elif citations:
                status, reason = "encoded", "all_citations_resolve_by_exact_path"
            else:
                status, reason = "excluded", "storage_or_test_file_without_corpus_citation"
            classifications.append(
                {
                    "path": row["path"],
                    "status": status,
                    "reason": reason,
                    "citations": citations,
                    "missing_citations": missing,
                }
            )
        by_status = {
            name: sum(row["status"] == name for row in classifications)
            for name in ("encoded", "excluded", "pending")
        }
        summaries.append(
            {
                "root": root,
                "total_files": len(classifications),
                "by_status": by_status,
                "classifications": classifications,
            }
        )
    classified = sum(root["total_files"] for root in summaries)
    if classified != len(files):
        raise ClosureError("a RuleSpec file fell outside every declared closure root")
    program_summaries = {}
    for program, root_nodes in expected_program_roots.items():
        reached: set[str] = set()
        stack = list(root_nodes)
        while stack:
            node_id = stack.pop()
            if node_id in reached:
                continue
            node = nodes_by_id.get(node_id)
            if node is None:
                raise ClosureError(f"{program}: unknown subgraph root {node_id!r}")
            reached.add(node_id)
            stack.extend(nodes_by_name[name]["id"] for name in node["dependencies"])
        citations = sorted(
            {
                citation
                for node_id in reached
                for citation in nodes_by_id[node_id]["citations"]
            }
        )
        citation_rows = [
            {
                "citation_path": citation,
                "status": "encoded" if citation in corpus_set else "pending",
                "reason": (
                    "exact_path_present_in_pinned_corpus_release"
                    if citation in corpus_set
                    else "citation_absent_from_pinned_corpus_release"
                ),
            }
            for citation in citations
        ]
        pending = [
            row["citation_path"] for row in citation_rows if row["status"] == "pending"
        ]
        program_summaries[program] = {
            "closed": not pending,
            "root_nodes": root_nodes,
            "root_node_count": len(root_nodes),
            "subgraph_node_count": len(reached),
            "citation_root_count": len(citation_rows),
            "by_status": {
                "encoded": len(citation_rows) - len(pending),
                "excluded": 0,
                "pending": len(pending),
            },
            "citations": citation_rows,
            "pending_citations": pending,
            "pending_money_atoms": 0,
        }
    return {
        "schema": "axiom_oracles.nz_closure_summary.v2",
        "jurisdiction": "nz",
        "rulespec_commit": RULESPEC_SHA,
        "corpus_release": "nz-rulespec-2026-07-18",
        "corpus_commit": CORPUS_RELEASE_SHA,
        "roots": summaries,
        "pending_citations": sorted(all_pending),
        "pending_money_atoms": 0,
        "closed": not all_pending,
        "programs": program_summaries,
        "source": {
            "artifact": str(SOURCE_PATH.relative_to(REPO_ROOT)),
            "sha256": hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest(),
        },
    }


def _render(value: dict) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--bootstrap-source", action="store_true")
    args = parser.parse_args()
    try:
        if args.bootstrap_source:
            rendered = _render(bootstrap_source())
            if args.check:
                if not SOURCE_PATH.exists() or SOURCE_PATH.read_text() != rendered:
                    print("NZ closure source snapshot drifted", file=sys.stderr)
                    return 1
            else:
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                SOURCE_PATH.write_text(rendered)
            return 0
        source = load_source()
        summary = build(source)
    except (OSError, json.JSONDecodeError, ClosureError) as exc:
        print(f"NZ closure ERROR: {exc}", file=sys.stderr)
        return 1
    rendered = _render(summary)
    if args.check:
        if not SUMMARY_PATH.exists() or SUMMARY_PATH.read_text() != rendered:
            print("NZ closure summary drifted", file=sys.stderr)
            return 1
        print("NZ closure summary up to date")
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(rendered)
    print(f"wrote {SUMMARY_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
