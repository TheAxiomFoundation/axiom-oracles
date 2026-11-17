"""The optional ``display`` block: dashboard wording (a title and a cause tag
from a fixed list) that never changes a disposition's class or the report."""

from pathlib import Path

import pytest

from axiom_oracles.comparison.dispositions import (
    DISPLAY_CAUSES,
    DISPOSITIONS_SCHEMA_VERSION,
    validate_dispositions,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _entry(**overrides) -> dict:
    entry = {
        "id": "example-residual",
        "concept": "us:test#income_tax",
        "case_id": "case-1",
        "disposition": "upstream_engine_gap",
        "evidence": {
            "mechanism": "The right engine applies a stale rate table.",
            "arithmetic": [{"expression": "125 - 100", "equals": 25}],
            "upstream_url": "https://example.org/upstream/1",
        },
        "expires_on_source_change": True,
    }
    entry.update(overrides)
    return entry


def _document(entries: list[dict]) -> dict:
    return {
        "schema": DISPOSITIONS_SCHEMA_VERSION,
        "suite": "example-suite",
        "entries": entries,
    }


def test_display_block_is_optional_and_validated() -> None:
    shown = _entry(display={"title": "Plain title", "cause": "comparison_setup"})
    assert validate_dispositions(_document([shown])) == []
    assert validate_dispositions(_document([_entry(display={"cause": "open"})])) == []
    assert validate_dispositions(_document([_entry(display={"title": "Only a title"})])) == []


@pytest.mark.parametrize(
    "display, fragment",
    [
        ({}, "display"),
        ("comparison_setup", "display"),
        ({"title": "t", "label": "x"}, "label"),
        ({"title": ""}, "title"),
        ({"title": " padded "}, "title"),
        ({"title": "two\nlines"}, "title"),
        ({"title": "two\rlines"}, "title"),
        ({"title": "two" + chr(0x2028) + "lines"}, "title"),
        ({"title": "x" * 121}, "title"),
        ({"title": 7}, "title"),
        ({"cause": "upstream"}, "cause"),
        ({"cause": None}, "cause"),
    ],
)
def test_malformed_display_block_is_invalid(display, fragment) -> None:
    errors = validate_dispositions(_document([_entry(display=display)]))
    assert errors, display
    assert any(fragment in error for error in errors), errors


@pytest.mark.parametrize("disposition", ["axiom_encoding_gap", "unexplained"])
def test_display_cause_cannot_relabel_axiom_or_unexplained_entries(
    disposition,
) -> None:
    entry = _entry(disposition=disposition, display={"cause": "comparison_setup"})
    errors = validate_dispositions(_document([entry]))
    assert any("cause" in error for error in errors), errors


def test_display_causes_match_the_dashboard_labels() -> None:
    source = (
        REPO_ROOT / "dashboard" / "src" / "utils" / "dispositionDisplay.mjs"
    ).read_text()
    block = source.split("DISPLAY_CAUSE_LABELS = Object.freeze({", 1)[1]
    block = block.split("});", 1)[0]
    keys = sorted(
        line.split(":", 1)[0].strip()
        for line in block.splitlines()
        if ":" in line
    )
    assert keys == sorted(DISPLAY_CAUSES)
