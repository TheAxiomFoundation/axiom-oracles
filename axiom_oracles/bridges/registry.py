"""Legal-ID keyed PolicyEngine oracle mapping registry."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

try:
    from yaml import CSafeLoader as _YamlLoader
except ImportError:
    from yaml import SafeLoader as _YamlLoader

SUPPORTED_MAPPING_TYPES = {
    "direct_variable",
    "derived_expression",
    "many_to_one",
    "one_to_many",
    "parameter_value",
    "not_comparable",
}
SUPPORTED_MATCH_TYPES = {"exact", "prefix"}
SUPPORTED_CANDIDATE_PRIORITIES = {"P1", "P2", "P3", "P4"}


@dataclass(frozen=True)
class PolicyEngineMapping:
    """Mapping from an Axiom legal output ID to a PolicyEngine comparison target."""

    legal_id: str
    country: str
    mapping_type: str
    match_type: str = "exact"
    policyengine_variable: str | None = None
    policyengine_parameter: str | None = None
    parameter_key: str | None = None
    parameter_keys: tuple[str, ...] = ()
    parameter_key_input: str | None = None
    parameter_key_map: dict[str, str] = field(default_factory=dict)
    parameter_key_path: tuple[Any, ...] = ()
    parameter_calc_input: str | None = None
    parameter_calc_value: Any | None = None
    program: str | None = None
    entity: str | None = None
    period: str | None = None
    unit: str | None = None
    comparison: str | None = None
    expression: str | None = None
    result_multiplier: float | None = None
    rationale: str | None = None
    candidate_priority: str | None = None
    aliases: tuple[str, ...] = ()
    tested_by_legal_ids: tuple[str, ...] = ()

    @property
    def comparable(self) -> bool:
        return self.mapping_type != "not_comparable" and bool(
            self.policyengine_variable or self.policyengine_parameter or self.expression
        )


@dataclass
class PolicyEngineOracleCoverage:
    """Coverage counters for a PolicyEngine oracle run."""

    total_outputs: int = 0
    skipped: int = 0
    comparable: int = 0
    passed: int = 0
    failed: int = 0
    unmapped: int = 0
    unsupported: int = 0
    adapter_errors: int = 0
    setup_errors: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "total_outputs": self.total_outputs,
            "skipped": self.skipped,
            "comparable": self.comparable,
            "passed": self.passed,
            "failed": self.failed,
            "unmapped": self.unmapped,
            "unsupported": self.unsupported,
            "adapter_errors": self.adapter_errors,
            "setup_errors": self.setup_errors,
        }


@dataclass(frozen=True)
class PolicyEngineOracleRegistry:
    """Resolved PolicyEngine mapping registry."""

    mappings_by_legal_id: dict[str, PolicyEngineMapping] = field(default_factory=dict)
    prefix_mappings: tuple[PolicyEngineMapping, ...] = ()

    def mapping_for_legal_id(
        self, legal_id: str | None, *, country: str | None = None
    ) -> PolicyEngineMapping | None:
        if not legal_id:
            return None
        legal_id_text = str(legal_id)
        mapping = self.mappings_by_legal_id.get(legal_id_text)
        if mapping is not None and (country is None or mapping.country == country):
            return mapping
        synthetic_mapping = _cms_chip_composition_mapping(legal_id_text)
        if synthetic_mapping is not None and (
            country is None or synthetic_mapping.country == country
        ):
            return synthetic_mapping
        for prefix_mapping in self.prefix_mappings:
            if country and prefix_mapping.country != country:
                continue
            if legal_id_text.startswith(prefix_mapping.legal_id):
                return prefix_mapping
        return None

    def legal_ids_for_policyengine_variable(
        self, policyengine_variable: str, *, country: str | None = None
    ) -> list[str]:
        return [
            legal_id
            for legal_id, mapping in self.mappings_by_legal_id.items()
            if mapping.policyengine_variable == policyengine_variable
            and (country is None or mapping.country == country)
        ]

    def mappings_for_policyengine_variable(
        self, policyengine_variable: str, *, country: str | None = None
    ) -> list[PolicyEngineMapping]:
        """Return exact and prefix mappings that reference a PE variable."""
        mappings = [
            mapping
            for mapping in self.mappings_by_legal_id.values()
            if mapping.policyengine_variable == policyengine_variable
            and (country is None or mapping.country == country)
        ]
        mappings.extend(
            mapping
            for mapping in self.prefix_mappings
            if mapping.policyengine_variable == policyengine_variable
            and (country is None or mapping.country == country)
        )
        return sorted(mappings, key=lambda mapping: mapping.legal_id)

    def validate(self) -> list[str]:
        issues: list[str] = []
        seen: set[str] = set()
        for legal_id, mapping in [
            *self.mappings_by_legal_id.items(),
            *((mapping.legal_id, mapping) for mapping in self.prefix_mappings),
        ]:
            if legal_id in seen:
                issues.append(f"Duplicate PolicyEngine mapping legal_id: {legal_id}")
            seen.add(legal_id)
            if mapping.match_type not in SUPPORTED_MATCH_TYPES:
                issues.append(
                    f"Unsupported PolicyEngine match_type for {legal_id}: "
                    f"{mapping.match_type}"
                )
            if mapping.match_type == "exact" and (
                "#" not in legal_id or ":" not in legal_id
            ):
                issues.append(
                    f"PolicyEngine mapping key must be a canonical legal ID: {legal_id}"
                )
            if mapping.match_type == "prefix":
                if ":" not in legal_id:
                    issues.append(
                        "PolicyEngine prefix mapping key must be a canonical "
                        f"legal ID prefix: {legal_id}"
                    )
                if mapping.mapping_type != "not_comparable":
                    issues.append(
                        "PolicyEngine prefix mappings may only classify "
                        f"not_comparable outputs: {legal_id}"
                    )
            if mapping.mapping_type not in SUPPORTED_MAPPING_TYPES:
                issues.append(
                    f"Unsupported PolicyEngine mapping_type for {legal_id}: "
                    f"{mapping.mapping_type}"
                )
            if mapping.mapping_type == "direct_variable" and not (
                mapping.policyengine_variable
            ):
                issues.append(
                    f"Direct PolicyEngine mapping missing policyengine_variable: {legal_id}"
                )
            if (
                mapping.mapping_type == "parameter_value"
                and not mapping.policyengine_parameter
            ):
                issues.append(
                    f"PolicyEngine parameter mapping missing policyengine_parameter: {legal_id}"
                )
            key_selectors = [
                bool(mapping.parameter_key),
                bool(mapping.parameter_keys),
                bool(mapping.parameter_key_input),
                bool(mapping.parameter_key_path),
                bool(mapping.parameter_calc_input),
                mapping.parameter_calc_value is not None,
            ]
            if sum(key_selectors) > 1:
                issues.append(
                    "PolicyEngine parameter mapping must use only one of "
                    "parameter_key, parameter_keys, parameter_key_input, "
                    "parameter_key_path, parameter_calc_input, or "
                    f"parameter_calc_value: {legal_id}"
                )
            if mapping.parameter_key_map and not mapping.parameter_key_input:
                issues.append(
                    "PolicyEngine parameter_key_map requires "
                    f"parameter_key_input: {legal_id}"
                )
            for index, part in enumerate(mapping.parameter_key_path):
                if isinstance(part, dict):
                    if "input" not in part:
                        issues.append(
                            "PolicyEngine parameter_key_path dict entries require "
                            f"input: {legal_id}[{index}]"
                        )
                    key_map = part.get("parameter_key_map") or part.get("key_map")
                    if key_map is not None and not isinstance(key_map, dict):
                        issues.append(
                            "PolicyEngine parameter_key_path key_map must be a "
                            f"mapping: {legal_id}[{index}]"
                        )
            if mapping.mapping_type == "not_comparable" and not mapping.rationale:
                issues.append(
                    f"PolicyEngine not_comparable mapping missing rationale: {legal_id}"
                )
            if (
                mapping.candidate_priority
                and mapping.candidate_priority not in SUPPORTED_CANDIDATE_PRIORITIES
            ):
                issues.append(
                    "Unsupported PolicyEngine candidate_priority for "
                    f"{legal_id}: {mapping.candidate_priority}"
                )
            for evidence_legal_id in mapping.tested_by_legal_ids:
                if ":" not in evidence_legal_id or "#" not in evidence_legal_id:
                    issues.append(
                        "PolicyEngine tested_by_legal_ids entries must be "
                        f"canonical legal IDs: {legal_id} -> {evidence_legal_id}"
                    )
        return issues


_CMS_CHIP_COMPOSITION_LEGAL_ID_RE = re.compile(
    r"^(?P<jurisdiction>us-[a-z]{2}|us-dc):policies/cms/"
    r"(?P<state_slug>[a-z-]+)-chip-eligibility#(?P<rule>[a-z0-9_]+)$"
)


def _cms_chip_composition_mapping(legal_id: str) -> PolicyEngineMapping | None:
    match = _CMS_CHIP_COMPOSITION_LEGAL_ID_RE.match(legal_id)
    if not match:
        return None
    rule = match.group("rule")
    if rule == "is_chip_eligible_child":
        return PolicyEngineMapping(
            legal_id=legal_id,
            country="us",
            program="chip",
            mapping_type="direct_variable",
            policyengine_variable="is_chip_eligible_child",
            entity="Person",
            period="year",
            rationale=(
                "CMS CHIP composition output for final child CHIP eligibility; "
                "mapped directly to the PolicyEngine-US child CHIP eligibility "
                "variable."
            ),
        )
    if rule == "is_chip_eligible_standard_pregnant_person":
        return PolicyEngineMapping(
            legal_id=legal_id,
            country="us",
            program="chip",
            mapping_type="direct_variable",
            policyengine_variable="is_chip_eligible_standard_pregnant_person",
            entity="Person",
            period="year",
            rationale=(
                "CMS CHIP composition output for final standard pregnant-person "
                "CHIP eligibility; mapped directly to the PolicyEngine-US "
                "standard pregnant CHIP eligibility variable."
            ),
        )
    if rule.endswith("_separate_chip_child_eligibility_available"):
        return PolicyEngineMapping(
            legal_id=legal_id,
            country="us",
            program="chip",
            mapping_type="not_comparable",
            policyengine_variable="is_chip_eligible_child",
            candidate_priority="P4",
            rationale=(
                "Axiom exposes the source-level CMS child CHIP availability "
                "fact used by the state composition. PolicyEngine-US exposes "
                "final child CHIP eligibility rather than a separate availability "
                "boolean."
            ),
        )
    if rule.endswith("_standard_pregnant_chip_eligibility_available"):
        return PolicyEngineMapping(
            legal_id=legal_id,
            country="us",
            program="chip",
            mapping_type="not_comparable",
            policyengine_variable="is_chip_eligible_standard_pregnant_person",
            candidate_priority="P4",
            rationale=(
                "Axiom exposes the source-level CMS standard pregnant CHIP "
                "availability fact used by the state composition. "
                "PolicyEngine-US exposes final standard pregnant CHIP "
                "eligibility rather than a separate availability boolean."
            ),
        )
    if rule == "is_chip_fcep_eligible_person":
        return PolicyEngineMapping(
            legal_id=legal_id,
            country="us",
            program="chip",
            mapping_type="not_comparable",
            policyengine_variable="is_chip_fcep_eligible_person",
            candidate_priority="P4",
            rationale=(
                "CMS CHIP composition output for final from-conception-to-end-"
                "of-pregnancy (FCEP) person eligibility. This is a state-"
                "adopted coverage surface assembled from CMS SPA income limits "
                "and other category rules; PolicyEngine-US does not expose a "
                "one-to-one FCEP eligibility oracle target."
            ),
        )
    if rule.endswith("_fcep_eligibility_available"):
        return PolicyEngineMapping(
            legal_id=legal_id,
            country="us",
            program="chip",
            mapping_type="not_comparable",
            policyengine_variable="is_chip_fcep_eligible_person",
            candidate_priority="P4",
            rationale=(
                "Axiom exposes the source-level CMS CHIP FCEP availability fact "
                "used by the state composition. PolicyEngine-US exposes final "
                "FCEP eligibility rather than a separate state availability "
                "boolean."
            ),
        )
    if rule.endswith("_fcep_effective_fpl_limit"):
        return PolicyEngineMapping(
            legal_id=legal_id,
            country="us",
            program="chip",
            mapping_type="not_comparable",
            policyengine_variable="is_chip_fcep_eligible_person",
            candidate_priority="P4",
            rationale=(
                "Axiom exposes the source-level CMS CHIP FCEP income limit "
                "including the MAGI 5-percentage-point disregard used by the "
                "state composition. PolicyEngine-US does not expose this state "
                "income threshold as a one-to-one parameter."
            ),
        )
    if rule.endswith("_fcep_fpl_limit"):
        return PolicyEngineMapping(
            legal_id=legal_id,
            country="us",
            program="chip",
            mapping_type="not_comparable",
            policyengine_variable="is_chip_fcep_eligible_person",
            candidate_priority="P4",
            rationale=(
                "Axiom exposes the source-level CMS CHIP FCEP SPA income limit "
                "used by the state composition. PolicyEngine-US does not expose "
                "this state income threshold as a one-to-one parameter."
            ),
        )
    return None


@lru_cache(maxsize=1)
def load_policyengine_registry() -> PolicyEngineOracleRegistry:
    """Load packaged PolicyEngine mappings.

    The packaged mappings are static (~1MB of YAML), so the parsed registry is
    cached for the lifetime of the process; callers must treat it as read-only.
    """
    mappings: dict[str, PolicyEngineMapping] = {}
    prefix_mappings: list[PolicyEngineMapping] = []
    mapping_dir = Path(__file__).with_name("mappings")
    for mapping_path in sorted(mapping_dir.glob("*.yaml")):
        payload = yaml.load(mapping_path.read_text(), Loader=_YamlLoader) or {}
        raw_mappings = payload.get("mappings", [])
        if not isinstance(raw_mappings, list):
            raise ValueError(f"{mapping_path} mappings must be a list")
        for raw_mapping in raw_mappings:
            if not isinstance(raw_mapping, dict):
                raise ValueError(f"{mapping_path} contains a non-object mapping")
            mapping = _mapping_from_payload(raw_mapping)
            if mapping.legal_id in mappings:
                raise ValueError(
                    f"Duplicate PolicyEngine mapping legal_id: {mapping.legal_id}"
                )
            mappings[mapping.legal_id] = mapping
        raw_prefixes = payload.get("prefixes", [])
        if not isinstance(raw_prefixes, list):
            raise ValueError(f"{mapping_path} prefixes must be a list")
        for raw_prefix in raw_prefixes:
            if not isinstance(raw_prefix, dict):
                raise ValueError(f"{mapping_path} contains a non-object prefix")
            prefix_payload = {**raw_prefix, "match_type": "prefix"}
            prefix_mappings.append(_mapping_from_payload(prefix_payload))
    registry = PolicyEngineOracleRegistry(
        mappings,
        tuple(
            sorted(
                prefix_mappings,
                key=lambda mapping: len(mapping.legal_id),
                reverse=True,
            )
        ),
    )
    issues = registry.validate()
    if issues:
        raise ValueError("Invalid PolicyEngine registry: " + "; ".join(issues))
    return registry


def _mapping_from_payload(payload: dict[str, Any]) -> PolicyEngineMapping:
    aliases = payload.get("aliases", ())
    if aliases is None:
        aliases = ()
    if isinstance(aliases, str):
        aliases = (aliases,)
    tested_by_legal_ids = payload.get("tested_by_legal_ids", ())
    if tested_by_legal_ids is None:
        tested_by_legal_ids = ()
    if isinstance(tested_by_legal_ids, str):
        tested_by_legal_ids = (tested_by_legal_ids,)
    parameter_keys = payload.get("parameter_keys", ())
    if parameter_keys is None:
        parameter_keys = ()
    if isinstance(parameter_keys, str):
        parameter_keys = (parameter_keys,)
    parameter_key_path = payload.get("parameter_key_path", ())
    if parameter_key_path is None:
        parameter_key_path = ()
    if isinstance(parameter_key_path, (str, int, float)):
        parameter_key_path = (parameter_key_path,)
    legal_id = payload.get("legal_id", payload.get("legal_id_prefix"))
    if legal_id is None:
        raise ValueError("PolicyEngine mapping missing legal_id")
    return PolicyEngineMapping(
        legal_id=str(legal_id),
        country=str(payload.get("country", "us")),
        mapping_type=str(payload.get("mapping_type", "direct_variable")),
        match_type=str(payload.get("match_type", "exact")),
        policyengine_variable=payload.get("policyengine_variable"),
        policyengine_parameter=payload.get("policyengine_parameter"),
        parameter_key=(
            str(payload["parameter_key"])
            if payload.get("parameter_key") is not None
            else None
        ),
        parameter_keys=tuple(str(key) for key in parameter_keys),
        parameter_key_input=payload.get("parameter_key_input"),
        parameter_key_map={
            str(key): str(value)
            for key, value in (payload.get("parameter_key_map") or {}).items()
        },
        parameter_key_path=tuple(parameter_key_path),
        parameter_calc_input=payload.get("parameter_calc_input"),
        parameter_calc_value=payload.get("parameter_calc_value"),
        program=payload.get("program"),
        entity=payload.get("entity"),
        period=payload.get("period"),
        unit=payload.get("unit"),
        comparison=payload.get("comparison"),
        expression=payload.get("expression"),
        result_multiplier=(
            float(payload["result_multiplier"])
            if payload.get("result_multiplier") is not None
            else None
        ),
        rationale=payload.get("rationale"),
        candidate_priority=payload.get("candidate_priority"),
        aliases=tuple(str(alias) for alias in aliases),
        tested_by_legal_ids=tuple(str(legal_id) for legal_id in tested_by_legal_ids),
    )
