"""Tests for the sanity fixture loader and case-builder.

End-to-end engine execution is exercised by `scripts/run_comparison.py
--sanity` against real comparisons; these unit tests pin down the
fixture-to-Case mapping so future fixture-format changes don't silently
drop facts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from axiom_oracles.core.case import Concepts
from axiom_oracles.sanity import (
    SanityResult,
    SanitySummary,
    fixture_to_case,
    load_fixtures,
    print_summary,
)


@pytest.fixture
def fixtures_yaml(tmp_path: Path) -> Path:
    """A minimal valid fixtures YAML covering the canonical eligibility cases."""
    path = tmp_path / "test.fixtures.yaml"
    path.write_text(
        """
concept: us:programs/snap#eligible
period: 2026-01
fixtures:
  - id: ineligible-high-income
    description: High earner should be SNAP-ineligible.
    facts:
      household:
        state_code: CA
      members:
        - age: 30
          yearly_earned_income: 200000
          is_disabled: false
          is_us_citizen: true
    expected:
      axiom: false
      policyengine: false
  - id: eligible-low-income
    description: Low earner should be SNAP-eligible.
    facts:
      household:
        state_code: CA
      members:
        - age: 30
          yearly_earned_income: 5000
    expected:
      axiom: true
      policyengine: true
""".strip()
    )
    return path


def test_load_fixtures_parses_concept_period_and_entries(fixtures_yaml: Path) -> None:
    concept, period, fixtures = load_fixtures(fixtures_yaml)
    assert concept == "us:programs/snap#eligible"
    assert period == "2026-01"
    assert [f.id for f in fixtures] == ["ineligible-high-income", "eligible-low-income"]
    assert fixtures[0].expected == {"axiom": False, "policyengine": False}


def test_fixture_to_case_emits_person_entities_with_concept_keys(
    fixtures_yaml: Path,
) -> None:
    _, _, fixtures = load_fixtures(fixtures_yaml)
    case = fixture_to_case(
        fixtures[0],
        concept="us:programs/snap#eligible",
        period="2026-01",
    )
    assert case.case_id == "sanity-ineligible-high-income"
    persons = [e for e in case.entities if e.kind == "person"]
    assert len(persons) == 1
    facts = persons[0].facts
    # Use Concepts keys so the YAML mapping resolves the same way as for ECPS.
    assert facts[Concepts.PERSON_AGE] == 30
    assert facts[Concepts.YEARLY_EARNED_INCOME] == 200000.0
    assert facts[Concepts.DISABLED] is False


def test_fixture_to_case_sets_scope_for_jurisdiction_filter(
    fixtures_yaml: Path,
) -> None:
    """Sanity cases must pass the jurisdiction-FIPS filter that ECPS cases use."""
    _, _, fixtures = load_fixtures(fixtures_yaml)
    case = fixture_to_case(
        fixtures[0],
        concept="us:programs/snap#eligible",
        period="2026-01",
    )
    assert case.scope is not None
    assert str(case.scope.geoid).startswith("06")  # CA FIPS


def test_summary_pass_and_fail_modes() -> None:
    summary = SanitySummary(concept="x", period="2026-01")
    summary.results.append(SanityResult(
        fixture_id="a", engine="axiom", expected=True, actual=True, matched=True
    ))
    assert summary.passed is True
    assert summary.fail_count == 0

    summary.results.append(SanityResult(
        fixture_id="b", engine="axiom", expected=False, actual=True, matched=False
    ))
    assert summary.passed is False
    assert summary.fail_count == 1


def test_print_summary_includes_failure_banner(capsys) -> None:
    summary = SanitySummary(concept="x", period="2026-01")
    summary.results.append(SanityResult(
        fixture_id="a", engine="axiom", expected=False, actual=True, matched=False
    ))
    print_summary(summary)
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "SANITY FAILURE" in out
