"""Shared PolicyEngine/Populace oracle-bridge layer.

This package is the shared home of the oracle bridge code that previously
lived inside the encoder as ``axiom_encode.oracles.policyengine`` (the ~19k
LOC PolicyEngine/Populace comparison harnesses) plus the engine-neutral
``Case``/``Concepts`` types that downstream repos otherwise duplicate.

Modules mirror the encoder layout one-to-one and were copied verbatim from
TheAxiomFoundation/axiom-encode @ a314fc624967b4e990beb7d9ffc429dae6e26642
(only intra-package imports were adjusted). See ``README.md`` in this
directory for the public API and stability contract.

PolicyEngine, populace-data, and huggingface-hub remain optional runtime
dependencies: every module in this package imports them lazily, so the
package (and this ``__init__``) is importable without any of them installed.
"""

from ..core.case import Case, Concepts, Entity
from ..core.geography import GeographyScope
from .population import (
    POPULACE_PINS,
    PopulacePin,
    load_populace_dataset,
    resolve_populace_pin,
)
from .registry import (
    PolicyEngineMapping,
    PolicyEngineOracleCoverage,
    PolicyEngineOracleRegistry,
    load_policyengine_registry,
)

__all__ = [
    "POPULACE_PINS",
    "Case",
    "Concepts",
    "Entity",
    "GeographyScope",
    "PolicyEngineMapping",
    "PolicyEngineOracleCoverage",
    "PolicyEngineOracleRegistry",
    "PopulacePin",
    "load_policyengine_registry",
    "load_populace_dataset",
    "resolve_populace_pin",
]
