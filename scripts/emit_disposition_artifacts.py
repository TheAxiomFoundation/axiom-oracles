"""Emit per-suite disposition artifacts for the dashboard.

The dispositions/<suite>.yaml files carry the prose explanation for every
triaged mismatch (evidence.mechanism, the linked upstream issue, the
category). The comparison reports only stamp each mismatch with the entry
id — so the dashboard could say "dispositioned" but never say WHY. This
script ships the explanations: dashboard/public/data/dispositions/
<suite>.json, one compact entry per disposition.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DISPOSITIONS = ROOT / "dispositions"
OUT = ROOT / "dashboard" / "public" / "data" / "dispositions"


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


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    emitted = 0
    for path in sorted(DISPOSITIONS.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text())
        suite = doc.get("suite") or path.stem
        entries = [compact_entry(e) for e in doc.get("entries") or []]
        out_path = OUT / f"{suite}.json"
        out_path.write_text(
            json.dumps(
                {
                    "suite": suite,
                    "updated": doc.get("updated"),
                    "entries": entries,
                },
                indent=1,
            )
            + "\n"
        )
        emitted += 1
    print(f"emitted {emitted} disposition artifacts -> {OUT}")


if __name__ == "__main__":
    main()
