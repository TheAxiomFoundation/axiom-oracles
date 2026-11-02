"""Tests for the compose-spec coverage analyzer."""

from __future__ import annotations

from axiom_oracles.coverage import (
    find_uncovered_eligibility_rules,
    format_coverage_warning,
)


def _rule(name: str, expr: dict | None = None) -> dict:
    return {"name": name, "expr": expr or {}}


def test_reports_unreferenced_eligibility_rules() -> None:
    program = {
        "derived": [
            _rule(
                "snap_eligible",
                {"kind": "derived", "name": "snap_member_eligible"},
            ),
            _rule("snap_member_eligible"),
            _rule("snap_income_eligibility"),  # eligibility-looking, unreferenced
            _rule("snap_asset_limit"),           # eligibility-looking, unreferenced
            _rule("some_unrelated_rule"),        # not eligibility-looking, ignored
        ]
    }
    uncovered = find_uncovered_eligibility_rules(program, target="snap_eligible")
    assert "snap_income_eligibility" in uncovered
    assert "snap_asset_limit" in uncovered
    assert "snap_member_eligible" not in uncovered  # it IS referenced
    assert "some_unrelated_rule" not in uncovered    # not eligibility-looking


def test_transitive_references_are_credited() -> None:
    """A rule reachable through another derived rule counts as covered."""
    program = {
        "derived": [
            _rule(
                "snap_eligible",
                {"kind": "derived", "name": "intermediate"},
            ),
            _rule(
                "intermediate",
                {"kind": "derived", "name": "snap_income_eligibility"},
            ),
            _rule("snap_income_eligibility"),
        ]
    }
    uncovered = find_uncovered_eligibility_rules(program, target="snap_eligible")
    assert uncovered == []


def test_derived_relation_predicates_are_followed() -> None:
    """Predicates inside derivation specs count as references too."""
    program = {
        "derived": [
            _rule("target", {"kind": "derived", "name": "snap_unit_count"}),
            {
                "name": "snap_unit_count",
                "derivation": {
                    "predicate": {"kind": "derived", "name": "snap_member_eligible"},
                },
            },
            _rule("snap_member_eligible"),
            _rule("snap_other_eligible_rule"),  # unreferenced
        ]
    }
    uncovered = find_uncovered_eligibility_rules(program, target="target")
    assert "snap_member_eligible" not in uncovered
    assert "snap_other_eligible_rule" in uncovered


def test_format_warning_returns_empty_when_no_gaps() -> None:
    assert format_coverage_warning("target", []) == ""


def test_format_warning_includes_rule_names() -> None:
    out = format_coverage_warning("snap_eligible", ["snap_income_eligibility", "snap_asset_limit"])
    assert "snap_income_eligibility" in out
    assert "snap_asset_limit" in out
    assert "COVERAGE GAP" in out
