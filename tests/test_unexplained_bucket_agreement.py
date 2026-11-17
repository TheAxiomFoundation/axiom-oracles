"""Every committed block that carries both unexplained fields agrees on them.

A disposition block reports unexplained rows twice: ``unexplained_count`` and
the ``counts.unexplained`` bucket. Both mean every row left unexplained, so
any block carrying both must give one figure. This walks every tracked JSON
file, at any depth, so a bundle that embeds a report (``overview.json``) is
held to the same rule as the report.

One committed report predates its generator's fix and cannot be regenerated
without the licensed SPSD/M extract; ``check_engine_identity.py`` also
refuses any edit to its bytes without a recorded engine identity. Its
exception binds the exact report bytes, so a rerun retires it: new bytes no
longer match, and the stale-exception test then requires removing the entry.
Entries may only be removed.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OVERVIEW = "dashboard/public/data/overview.json"

# Report path -> sha256 of the committed bytes whose block disagrees.
# axiom-spsm-ca-federal-schedule-tax.json: counts.unexplained 0 against
# unexplained_count 97, written on 2026-07-27 by the generator before it took
# the bucket from its unclassified rows. Issue #606 (section A) tracks the
# SPSM evidence; a licensed rerun regenerates this report.
LEGACY_DISAGREEMENTS = {
    "dashboard/public/data/axiom-spsm-ca-federal-schedule-tax.json": (
        "6c1d0f93641a8a62de947b166205a3db0c7287161cc72c41a5210406af7e0f5b"
    ),
}


def _blocks(node, pointer=""):
    """Yield (JSON pointer, block) for every object carrying both fields."""
    if isinstance(node, dict):
        counts = node.get("counts")
        if (
            "unexplained_count" in node
            and isinstance(counts, dict)
            and "unexplained" in counts
        ):
            yield pointer, node
        for key, value in node.items():
            yield from _blocks(value, f"{pointer}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _blocks(value, f"{pointer}/{index}")


def _tracked_json():
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\0")
    for relative in sorted(filter(None, listed)):
        path = ROOT / relative
        if not path.is_file():
            continue
        content = path.read_bytes()
        # Cheap prefilter: most tracked JSON carries no disposition block.
        if b'"unexplained_count"' not in content:
            continue
        yield relative, content, json.loads(content)


def _disagreements():
    found = []
    total = 0
    for relative, content, document in _tracked_json():
        for pointer, block in _blocks(document):
            total += 1
            if block["counts"]["unexplained"] != block["unexplained_count"]:
                found.append((relative, content, document, pointer, block))
    return total, found


def _excused(relative, content, document, pointer):
    """Whether a disagreement sits in the exact bytes an exception names."""
    if relative in LEGACY_DISAGREEMENTS:
        return hashlib.sha256(content).hexdigest() == LEGACY_DISAGREEMENTS[relative]
    if relative == OVERVIEW and pointer.startswith("/reports/"):
        # The bundle embeds each report and records its source digest;
        # generate_dashboard_overview.py --check holds the copy to the source.
        report = document["reports"][int(pointer.split("/")[2])]
        source = f"dashboard/public/data/{report.get('file')}"
        return (
            source in LEGACY_DISAGREEMENTS
            and document["sources"].get(report.get("file"))
            == LEGACY_DISAGREEMENTS[source]
        )
    return False


def test_every_committed_block_agrees():
    total, found = _disagreements()
    # A walker that finds nothing would pass vacuously.
    assert total > 0
    unexcused = [
        f"{relative}{pointer}: counts.unexplained "
        f"{block['counts']['unexplained']} != unexplained_count "
        f"{block['unexplained_count']}"
        for relative, content, document, pointer, block in found
        if not _excused(relative, content, document, pointer)
    ]
    assert unexcused == []


def test_legacy_disagreements_are_still_live():
    """An exception whose bytes changed or now agree must be removed."""
    _, found = _disagreements()
    excused_reports = {relative for relative, *_ in found if relative in LEGACY_DISAGREEMENTS}
    for relative, digest in LEGACY_DISAGREEMENTS.items():
        path = ROOT / relative
        assert path.is_file(), f"{relative} is gone; remove its exception"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, (
            f"{relative} was regenerated; remove its exception"
        )
        assert relative in excused_reports, (
            f"{relative} now agrees; remove its exception"
        )


def test_walker_finds_nested_blocks_and_excuses_only_exact_bytes():
    document = {
        "reports": [
            {"summary": {"dispositioned": {"counts": {"unexplained": 1}, "unexplained_count": 1}}},
            {"x": [{"counts": {"unexplained": 0}, "unexplained_count": 2}]},
        ]
    }
    assert [pointer for pointer, _ in _blocks(document)] == [
        "/reports/0/summary/dispositioned",
        "/reports/1/x/0",
    ]
    legacy = next(iter(LEGACY_DISAGREEMENTS))
    assert _excused(legacy, (ROOT / legacy).read_bytes(), {}, "/summary/dispositioned")
    assert not _excused(legacy, b"{}", {}, "/summary/dispositioned")
    assert not _excused("dashboard/public/data/other.json", b"{}", {}, "/summary")
    bundle = {
        "sources": {Path(legacy).name: "0" * 64},
        "reports": [{"file": Path(legacy).name}],
    }
    assert not _excused(OVERVIEW, b"", bundle, "/reports/0/summary/dispositioned")
    bundle["sources"][Path(legacy).name] = LEGACY_DISAGREEMENTS[legacy]
    assert _excused(OVERVIEW, b"", bundle, "/reports/0/summary/dispositioned")
