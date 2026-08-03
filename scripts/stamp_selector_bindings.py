#!/usr/bin/env python3
"""Stamp selector_binding aggregates into a suite's disposition entries.

For every ``case_selector`` entry in ``dispositions/<suite>.yaml``, replay the
merge against the committed FULL report and record the selected population's
aggregate — ``units`` (row count) and ``abs_difference_sum`` (summed absolute
difference) — as the entry's ``selector_binding``. The merge validates the
binding on every subsequent application: a source change that moves any
selected row's values expires the entry and returns its rows to unexplained
(``expires_on_source_change`` made real for selector entries; sol closing
review F4).

Run after any legitimate refresh that changes selected values, in the same
commit as the refreshed report:

    uv run scripts/stamp_selector_bindings.py us-tariff-panel

Refuses to run when the suite has no committed FULL report to bind against.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from axiom_oracles.comparison.dispositions import (  # noqa: E402
    _entry_selects_row,
    _pin_matches,
)


def full_report_path(suite: str) -> Path:
    candidates = sorted(REPO.glob(f"reports/axiom-yale-{suite}-all-*.json"))
    if not candidates:
        candidates = sorted(REPO.glob(f"reports/*{suite}*-all-*.json"))
    if not candidates:
        raise SystemExit(
            f"no committed FULL report found for suite {suite!r} under reports/"
        )
    return candidates[-1]


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    suite = sys.argv[1]
    dispositions_path = REPO / "dispositions" / f"{suite}.yaml"
    if not dispositions_path.exists():
        raise SystemExit(f"{dispositions_path} does not exist")
    report = json.loads(full_report_path(suite).read_text())
    data = yaml.safe_load(dispositions_path.read_text())
    entries = data.get("entries") or []

    applied: dict[str, int] = {}
    sums: dict[str, float] = {}
    for row in report.get("mismatches") or []:
        for entry in entries:
            if not _entry_selects_row(entry, row):
                continue
            if not _pin_matches(entry.get("pinned"), row):
                continue
            entry_id = str(entry.get("id"))
            applied[entry_id] = applied.get(entry_id, 0) + 1
            diff = row.get("difference")
            if isinstance(diff, int | float):
                sums[entry_id] = sums.get(entry_id, 0.0) + abs(float(diff))
            break

    # Textual insertion — the committed file is hand-formatted (block-scalar
    # notes, comments); a yaml.dump round-trip would reflow it and drop
    # comments. Insert/replace each entry's selector_binding block right
    # after its expires_on_source_change line, byte-preserving the rest.
    import re

    text = dispositions_path.read_text()
    selector_ids = {
        str(e.get("id"))
        for e in entries
        if "case_selector" in e and applied.get(str(e.get("id")), 0) > 0
    }
    for entry in entries:
        entry_id = str(entry.get("id"))
        if entry_id not in selector_ids:
            if "case_selector" in entry:
                print(
                    f"note: {entry_id} selects no rows in the FULL report; skipped"
                )
            continue
        binding_block = (
            "  selector_binding:\n"
            f"    units: {applied[entry_id]}\n"
            f"    abs_difference_sum: {round(sums.get(entry_id, 0.0), 9)}\n"
        )
        # Locate this entry's block: from its `- id: <entry_id>` line to the
        # next top-level entry or EOF.
        entry_pattern = re.compile(
            rf"^- id: \"?{re.escape(entry_id)}\"?\n(?:.*?\n)*?(?=^- id: |\Z)",
            re.M,
        )
        m = entry_pattern.search(text)
        if not m:
            raise SystemExit(f"could not locate entry block for {entry_id}")
        block = m.group(0)
        block_new = re.sub(
            r"^  selector_binding:\n(?:    .*\n)*", "", block, flags=re.M
        )
        expires = re.search(
            r"^  expires_on_source_change: .*\n", block_new, re.M
        )
        if not expires:
            raise SystemExit(
                f"{entry_id} lacks an expires_on_source_change line"
            )
        insert_at = expires.end()
        block_new = block_new[:insert_at] + binding_block + block_new[insert_at:]
        text = text[: m.start()] + block_new + text[m.end():]

    dispositions_path.write_text(text)
    print(
        f"stamped selector_binding on {len(selector_ids)} entr"
        f"{'y' if len(selector_ids) == 1 else 'ies'} in "
        f"{dispositions_path.name} against {full_report_path(suite).name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
