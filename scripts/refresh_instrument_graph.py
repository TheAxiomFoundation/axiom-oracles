#!/usr/bin/env python3
"""Capture the DK act's subordinate-instrument graph from retsinformation ELI.

The closure ledger's instrument frontier (oracles#491) needs an authoritative,
committed candidate set: every instrument the official registry links to the
act. This script fetches the act's ELI JSON-LD graph, follows its ``basis_for``
(instruments issued under the act) and ``changed_by`` (amendment acts) edges,
fetches each instrument's own ELI metadata, and writes the snapshot artifact
the ledger derives from.

Network-using, ops-run — the analogue of ``regenerate_euromod_dk.sh``. The
ledger itself never touches the network: ``closure_ledger.py`` re-derives its
``instrument_graph`` facts from the committed snapshot bytes, so ``--check``
stays hermetic. The snapshot's currency is an explicit boundary: the artifact
records ``retrieved_at`` and the certificate's closure claim is relative to
the graph as of that date.

Usage::

    .venv/bin/python scripts/refresh_instrument_graph.py           # rewrite
    .venv/bin/python scripts/refresh_instrument_graph.py --diff    # dry-run
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = REPO_ROOT / "conformance" / "closure" / "dk-instrument-graph.json"

SCHEMA = "axiom_oracles.closure.instrument_graph.v1"
ACT_ELI = "https://retsinformation.dk/eli/lta/2025/603"
ACT_CITATION_PATH = "dk/statute/lbk-603-2025/boerne-og-ungeydelsesloven"
_ELI = "http://data.europa.eu/eli/ontology#"
_RELATIONS = ("basis_for", "changed_by")
_FIELDS = ("title", "title_short", "type_document", "in_force", "date_document")


def _fetch_json(uri: str) -> list:
    url = uri.replace("https://retsinformation.dk", "https://www.retsinformation.dk")
    request = urllib.request.Request(url + ".json", headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def _relations(graph: list) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for node in graph:
        for key, value in node.items():
            if not key.startswith(_ELI):
                continue
            name = key[len(_ELI) :]
            if name in _RELATIONS:
                for item in value if isinstance(value, list) else [value]:
                    uri = item.get("@value", item.get("@id", "")) if isinstance(item, dict) else item
                    if uri:
                        out.setdefault(name, []).append(uri)
    return out


def _metadata(graph: list) -> dict[str, object]:
    record: dict[str, object] = {}
    for node in graph:
        for key, value in node.items():
            if not key.startswith(_ELI):
                continue
            name = key[len(_ELI) :]
            if name not in _FIELDS or name in record:
                continue
            items = value if isinstance(value, list) else [value]
            first = items[0]
            text = first.get("@value", first.get("@id", "")) if isinstance(first, dict) else first
            if name == "type_document":
                text = str(text).rsplit("#", 1)[-1]
            elif name == "in_force":
                text = str(text).endswith("InForce-inForce")
            record[name] = text
    return record


def build_snapshot() -> dict[str, object]:
    act_graph = _fetch_json(ACT_ELI)
    act_relations = _relations(act_graph)
    instruments: list[dict[str, object]] = []
    for relation in _RELATIONS:
        for uri in sorted(set(act_relations.get(relation, []))):
            time.sleep(0.3)
            record: dict[str, object] = {"eli": uri, "relation": relation}
            record.update(_metadata(_fetch_json(uri)))
            instruments.append(record)
    instruments.sort(key=lambda row: (str(row["relation"]), str(row["eli"])))
    return {
        "schema": SCHEMA,
        "act_eli": ACT_ELI,
        "act_citation_path": ACT_CITATION_PATH,
        "retrieved_at": _dt.date.today().isoformat(),
        "retrieval_method": (
            "retsinformation ELI JSON-LD content negotiation: the act's graph's "
            "basis_for and changed_by edges, then each instrument's own graph"
        ),
        "instruments": instruments,
    }


def serialize(snapshot: dict[str, object]) -> str:
    return json.dumps(snapshot, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diff", action="store_true", help="print drift, write nothing")
    args = parser.parse_args(argv)
    snapshot = build_snapshot()
    rendered = serialize(snapshot)
    if args.diff:
        if SNAPSHOT_PATH.exists():
            committed = json.loads(SNAPSHOT_PATH.read_text())
            fresh_elis = {row["eli"]: row for row in snapshot["instruments"]}
            committed_elis = {row["eli"]: row for row in committed.get("instruments", [])}
            added = sorted(set(fresh_elis) - set(committed_elis))
            removed = sorted(set(committed_elis) - set(fresh_elis))
            changed = sorted(
                eli
                for eli in set(fresh_elis) & set(committed_elis)
                if {k: v for k, v in fresh_elis[eli].items()}
                != {k: v for k, v in committed_elis[eli].items()}
            )
            for label, rows in (("added", added), ("removed", removed), ("changed", changed)):
                for eli in rows:
                    print(f"{label}: {eli}")
            if not (added or removed or changed):
                print("instrument graph unchanged")
                return 0
            return 1
        print("no committed snapshot")
        return 1
    SNAPSHOT_PATH.write_text(rendered)
    print(
        f"wrote {SNAPSHOT_PATH.relative_to(REPO_ROOT)}: "
        f"{len(snapshot['instruments'])} instruments as of {snapshot['retrieved_at']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
