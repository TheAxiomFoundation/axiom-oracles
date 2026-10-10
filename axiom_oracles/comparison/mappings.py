from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..core.geography import (
    GeographyScope,
    normalize_scope,
    scope_contains,
    scope_intersection,
)


Target = str | list[str] | dict[str, Any]


@dataclass(frozen=True)
class ProgramMapping:
    """Mapping from a source-backed concept to engine-specific targets."""

    standard: str
    description: str
    category: str
    targets: dict[str, Target] = field(default_factory=dict)
    locales: tuple[str, ...] = field(default_factory=tuple)
    scope: GeographyScope | dict[str, Any] | None = None
    accessnyc_code: str | None = None
    policyengine_variable: str | list[str] | None = None
    axiom_output: str | None = None
    comparison: str = "eligibility"
    tolerance: float = 0
    relative_tolerance: float = 0
    priority: str = "normal"
    components: tuple[str, ...] = field(default_factory=tuple)
    parent: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.locales, str):
            object.__setattr__(self, "locales", (self.locales,))
        elif not isinstance(self.locales, tuple):
            object.__setattr__(self, "locales", tuple(self.locales))
        if isinstance(self.components, list):
            object.__setattr__(self, "components", tuple(self.components))
        if self.scope is not None:
            object.__setattr__(self, "scope", normalize_scope(self.scope))

    @property
    def concept_id(self) -> str:
        return self.standard

    def target_for_engine(self, engine: str) -> str | list[str] | None:
        if engine in self.targets:
            return self._target_name(self.targets[engine])
        if engine == "accessnyc":
            return self.accessnyc_code
        if engine == "policyengine":
            return self.policyengine_variable
        if engine == "axiom":
            return self.axiom_output
        return None

    def supports_any_locale(self, locales: set[str] | None) -> bool:
        if not self.locales or not locales:
            return True
        return any(
            _locale_matches(mapping_locale, case_locale)
            for mapping_locale in self.locales
            for case_locale in locales
        )

    def supports_engine_locale(self, engine: str, locales: set[str] | None) -> bool:
        target_locales = self.target_locales(engine) or self.locales
        if not target_locales or not locales:
            return True
        return any(
            _locale_matches(target_locale, case_locale)
            for target_locale in target_locales
            for case_locale in locales
        )

    def target_locales(self, engine: str) -> tuple[str, ...]:
        target = self.targets.get(engine)
        if not isinstance(target, dict):
            return ()
        locales = target.get("locales", ())
        if isinstance(locales, str):
            return (locales,)
        return tuple(locales)

    def target_scope(self, engine: str) -> GeographyScope | None:
        target = self.targets.get(engine)
        if not isinstance(target, dict) or "scope" not in target:
            return None
        return normalize_scope(target["scope"])

    def supports_engine_scope(
        self,
        engine: str,
        scope: GeographyScope | dict[str, Any] | None,
        target_scopes: dict[str, GeographyScope] | None = None,
    ) -> bool:
        requested_scope = normalize_scope(scope)
        if requested_scope is None:
            return True
        if self.scope is not None and not scope_contains(self.scope, requested_scope):
            return False

        engine_scope = self.target_scope(engine)
        if engine_scope is None and target_scopes is not None:
            engine_scope = target_scopes.get(engine)
        if engine_scope is None:
            return True
        return scope_contains(engine_scope, requested_scope)

    @staticmethod
    def _target_name(target: Target) -> str | list[str] | None:
        if isinstance(target, dict):
            value = target.get("name") or target.get("variable") or target.get("code")
            if isinstance(value, str | list):
                return value
            return None
        return target


def default_mapping_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "concept_mappings.yaml"


def legacy_mapping_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "program_mappings.yaml"


@functools.lru_cache(maxsize=8)
def _load_mapping_data_cached(mapping_path: str) -> dict[str, Any]:
    with Path(mapping_path).open() as f:
        return yaml.safe_load(f)


def _load_mapping_data(path: str | Path | None = None) -> dict[str, Any]:
    # Cached: per-jurisdiction column resolution calls this in loops, and
    # an uncached reparse of the full mapping costs ~85 ms per call. The
    # returned structure is shared — treat it as immutable.
    mapping_path = Path(path) if path else default_mapping_path()
    return _load_mapping_data_cached(str(mapping_path.resolve()))


def load_program_mappings(path: str | Path | None = None) -> list[ProgramMapping]:
    data = _load_mapping_data(path)

    if "concepts" in data:
        return [
            ProgramMapping(standard=concept_id, **config)
            for concept_id, config in data.get("concepts", {}).items()
        ]

    return [
        ProgramMapping(standard=standard, **config)
        for standard, config in data.get("programs", {}).items()
    ]


def load_legacy_program_mappings() -> list[ProgramMapping]:
    return load_program_mappings(legacy_mapping_path())


def load_target_scopes(path: str | Path | None = None) -> dict[str, GeographyScope]:
    data = _load_mapping_data(path)
    scopes: dict[str, GeographyScope] = {}
    for engine, config in data.get("targets", {}).items():
        if isinstance(config, dict) and "scope" in config:
            scope = normalize_scope(config["scope"])
            if scope is not None:
                scopes[engine] = scope
    return scopes


def comparison_scope_for_targets(
    left_engine: str,
    right_engine: str,
    target_scopes: dict[str, GeographyScope] | None = None,
) -> GeographyScope | None:
    scopes = target_scopes if target_scopes is not None else load_target_scopes()
    return scope_intersection(scopes.get(left_engine), scopes.get(right_engine))


def mappings_by_concept(
    mappings: list[ProgramMapping] | None = None,
) -> dict[str, ProgramMapping]:
    return {
        mapping.concept_id: mapping
        for mapping in (mappings if mappings is not None else load_program_mappings())
    }


def engine_targets_for_concepts(
    concept_ids: list[str] | tuple[str, ...],
    engine: str,
    mappings: list[ProgramMapping] | None = None,
) -> list[str]:
    by_concept = mappings_by_concept(mappings)
    targets: list[str] = []
    for concept_id in concept_ids:
        mapping = by_concept.get(concept_id)
        if mapping is None:
            continue
        target = mapping.target_for_engine(engine)
        if isinstance(target, list):
            targets.extend(target)
        elif target:
            targets.append(target)
    return targets


def comparable_mappings(
    left_engine: str,
    right_engine: str,
    mappings: list[ProgramMapping] | None = None,
    *,
    locales: set[str] | None = None,
    scope: GeographyScope | dict[str, Any] | None = None,
    target_scopes: dict[str, GeographyScope] | None = None,
    concepts: set[str] | None = None,
    categories: set[str] | None = None,
    include_components: bool = False,
) -> list[ProgramMapping]:
    selected = []
    selected_ids: set[str] = set()
    source = mappings if mappings is not None else load_program_mappings()
    by_concept = {mapping.concept_id: mapping for mapping in source}
    scopes = target_scopes if target_scopes is not None else load_target_scopes()

    def _engine_ok(mapping: ProgramMapping) -> bool:
        if not mapping.target_for_engine(left_engine):
            return False
        if not mapping.target_for_engine(right_engine):
            return False
        if not mapping.supports_engine_locale(left_engine, locales):
            return False
        if not mapping.supports_engine_locale(right_engine, locales):
            return False
        if not mapping.supports_engine_scope(left_engine, scope, scopes):
            return False
        if not mapping.supports_engine_scope(right_engine, scope, scopes):
            return False
        return True

    def _append(mapping: ProgramMapping) -> None:
        if mapping.concept_id in selected_ids:
            return
        selected.append(mapping)
        selected_ids.add(mapping.concept_id)

    for mapping in source:
        if mapping.parent is not None:
            if not concepts or mapping.concept_id not in concepts:
                continue
            if categories and mapping.category not in categories:
                continue
            if not _engine_ok(mapping):
                continue
            _append(mapping)
            continue
        if concepts and mapping.concept_id not in concepts:
            continue
        if categories and mapping.category not in categories:
            continue
        if not _engine_ok(mapping):
            continue
        _append(mapping)
        if include_components:
            for component_id in mapping.components:
                component = by_concept.get(component_id)
                if component is None or not _engine_ok(component):
                    continue
                _append(component)
    return selected


def _locale_matches(mapping_locale: str, case_locale: str) -> bool:
    return case_locale == mapping_locale or case_locale.startswith(f"{mapping_locale}-")
