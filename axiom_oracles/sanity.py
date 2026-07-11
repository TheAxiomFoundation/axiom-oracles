"""Sanity fixture runner — hand-built cases as a tripwire for silent failures.

A sanity fixture is a synthetic case whose expected per-engine output is
unambiguous from public domain knowledge of the program rules. Running
fixtures *before* the population-scale comparison catches infrastructure
bugs (dropped relations, wrong intervals, missing inputs) AND rule-chain
gaps (missing income limits, missing exemptions) that would otherwise
hide inside an aggregate match-rate number.

The fixture format is one YAML per comparison; see
``comparisons/<name>.fixtures.yaml`` for the canonical example.

This module is invoked by ``scripts/run_comparison.py --sanity`` (which
spawns a uv subprocess so engines can run in their pinned venv); it
exports the loader/builder/checker in case other tools want to invoke
the same checks directly.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .core.case import Case, Concepts, Entity


@dataclass
class SanityFixture:
    """One sanity-test entry: synthetic case + expected per-engine outputs."""

    id: str
    description: str
    facts: dict
    expected: dict[str, bool]


@dataclass
class SanityResult:
    """Result of running one fixture through a single engine."""

    fixture_id: str
    engine: str
    expected: bool
    actual: Any
    matched: bool
    error: str | None = None


@dataclass
class SanitySummary:
    """Aggregate verdict for a sanity run; non-zero exit if any fixture failed."""

    concept: str
    period: str
    results: list[SanityResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.matched for r in self.results)

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if not r.matched)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_fixtures(path: Path) -> tuple[str, str, list[SanityFixture]]:
    """Parse a fixtures YAML into (concept, period, fixtures)."""
    config = yaml.safe_load(Path(path).read_text())
    concept = config["concept"]
    period = str(config["period"])
    fixtures = [
        SanityFixture(
            id=str(entry["id"]),
            description=str(entry.get("description", "")).strip(),
            facts=dict(entry.get("facts", {})),
            expected=dict(entry.get("expected", {})),
        )
        for entry in config.get("fixtures", [])
    ]
    return concept, period, fixtures


# ---------------------------------------------------------------------------
# Fixture → Case
# ---------------------------------------------------------------------------


def fixture_to_case(
    fixture: SanityFixture,
    *,
    concept: str,
    period: str,
) -> Case:
    """Build an engine-neutral Case from a fixture's hand-written facts.

    Person facts use ``Concepts.X`` keys so the generic projector's YAML
    mapping resolves them the same way it resolves real ECPS facts —
    fixtures travel through the same projection pipeline as production
    cases, which is the whole point of using them as a tripwire.
    """
    household_facts = dict(fixture.facts.get("household", {}))
    state_code = household_facts.pop("state_code", "CA")

    members = fixture.facts.get("members", []) or []
    entities: list[Entity] = []
    for index, member in enumerate(members):
        person_facts = {
            Concepts.PERSON_AGE: int(member.get("age", 0)),
            Concepts.YEARLY_EARNED_INCOME: float(member.get("yearly_earned_income", 0)),
            Concepts.DISABLED: bool(member.get("is_disabled", False)),
            Concepts.PREGNANT: bool(member.get("is_pregnant", False)),
            Concepts.VETERAN: bool(member.get("is_veteran", False)),
        }
        entities.append(
            Entity(
                entity_id=f"sanity-person-{index}",
                kind="person",
                facts=person_facts,
            )
        )

    # Household entity carries scope info for the FIPS filter.
    fips = {"CA": "06000000000000", "CO": "08000000000000"}.get(
        str(state_code).upper(), "06000000000000"
    )
    entities.append(
        Entity(
            entity_id="sanity-household",
            kind="household",
            facts={Concepts.STATE_CODE: state_code, **household_facts},
        )
    )

    return Case(
        case_id=f"sanity-{fixture.id}",
        period=period,
        facts={Concepts.STATE_CODE: state_code},
        entities=tuple(entities),
        outputs=(concept,),
        metadata={
            "scope": {"type": "census_state", "geoid": fips[:2]},
        },
    )


# ---------------------------------------------------------------------------
# Pretty-print
# ---------------------------------------------------------------------------


def print_summary(summary: SanitySummary, *, stream=None) -> None:
    """Render the sanity-run summary so the failure mode is impossible to miss."""
    if stream is None:
        stream = sys.stdout
    print(f"\nSanity fixtures — concept: {summary.concept}", file=stream)
    print(f"Period: {summary.period}", file=stream)
    print(
        f"Total checks: {len(summary.results)}; failed: {summary.fail_count}\n",
        file=stream,
    )
    by_fixture: dict[str, list[SanityResult]] = {}
    for r in summary.results:
        by_fixture.setdefault(r.fixture_id, []).append(r)
    for fixture_id, results in by_fixture.items():
        verdict = "PASS" if all(r.matched for r in results) else "FAIL"
        print(f"  [{verdict}] {fixture_id}", file=stream)
        for r in results:
            mark = "ok " if r.matched else "FAIL"
            if r.error:
                print(f"    {mark} {r.engine}: ERROR {r.error}", file=stream)
            else:
                print(
                    f"    {mark} {r.engine}: got={r.actual!r} expected={r.expected!r}",
                    file=stream,
                )
    if not summary.passed:
        print(
            "\n!! SANITY FAILURE — do not trust population-scale agreement numbers "
            "until these fixtures pass.\n",
            file=stream,
        )
