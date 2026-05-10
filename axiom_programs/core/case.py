from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .geography import GeographyScope, normalize_scope


@dataclass(frozen=True)
class Entity:
    """A thin case entity with concept-keyed facts."""

    entity_id: str
    kind: str
    facts: Mapping[str, Any] = field(default_factory=dict)

    def fact(self, concept_id: str, default: Any = None) -> Any:
        return self.facts.get(concept_id, default)


@dataclass(frozen=True)
class Case:
    """Engine-neutral case data.

    Facts and requested outputs are keyed by canonical legal or Axiom concept IDs.
    Adapters project those facts into PolicyEngine variables, ACCESS NYC payloads,
    PRD fields, TAXSIM columns, or Axiom RuleSpec runtime inputs.
    """

    case_id: int | str
    period: str
    facts: Mapping[str, Any] = field(default_factory=dict)
    entities: tuple[Entity, ...] = field(default_factory=tuple)
    outputs: tuple[str, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def fact(self, concept_id: str, default: Any = None) -> Any:
        return self.facts.get(concept_id, default)

    def entities_of_kind(self, kind: str) -> tuple[Entity, ...]:
        return tuple(entity for entity in self.entities if entity.kind == kind)

    @property
    def locale(self) -> str | None:
        value = self.metadata.get("locale") or self.facts.get(Concepts.LOCALE)
        return str(value) if value else None

    @property
    def scope(self) -> GeographyScope | None:
        value = self.metadata.get("scope") or self.facts.get(Concepts.GEOGRAPHY_SCOPE)
        return normalize_scope(value)


class Concepts:
    """Small set of cross-engine case facts used by bundled projections.

    Domain-specific outputs should usually use source-backed legal IDs, not these
    generic helper concepts. These helpers exist for facts like age and household
    relation that are needed to project a case into external engines.
    """

    PERSON_AGE = "axiom:demographics/person#age"
    HOUSEHOLD_RELATION = "axiom:demographics/person#household_relation"
    YEARLY_EARNED_INCOME = "axiom:income/person#yearly_earned_income"
    PREGNANT = "axiom:demographics/person#pregnant"
    BLIND = "axiom:demographics/person#blind"
    DISABLED = "axiom:demographics/person#disabled"
    VETERAN = "axiom:demographics/person#veteran"
    BENEFITS_MEDICAID = "axiom:benefits/person#medicaid"
    BENEFITS_MEDICAID_DISABILITY = "axiom:benefits/person#disability_medicaid"
    LIVING_RENTING = "axiom:housing/household#living_renting"
    LIVING_OWNER = "axiom:housing/household#living_owner"
    CASH_ON_HAND = "axiom:assets/household#cash_on_hand"
    LOCALE = "axiom:case#locale"
    GEOGRAPHY_SCOPE = "axiom:case#geography_scope"
    STATE_CODE = "axiom:location/household#state_code"

    SNAP_BENEFIT = "us:statutes/7/2014/u#snap_benefit"
    SNAP_ELIGIBLE = "us:statutes/7/2014/o#snap_eligible"
    MEDICAID_ELIGIBLE = "us:programs/medicaid#eligible"
    MEDICAID_PREGNANT_WOMEN_ELIGIBLE = (
        "us:programs/medicaid-pregnant-women#eligible"
    )
    BASIC_HEALTH_PROGRAM_ELIGIBLE = "us:programs/basic-health-program#eligible"
    CHILD_HEALTH_PLUS_ELIGIBLE = "us:programs/child-health-plus#eligible"
    WIC_ELIGIBLE = "us:statutes/42/1786#wic_eligible"
