"""Import-surface contract for the shared oracle-bridge package.

Every bridge module must be importable WITHOUT PolicyEngine, populace-data,
huggingface-hub, or numpy installed (heavy dependencies are lazy, imported
inside functions), and the documented public names must exist. axiom-encode
re-exports these modules as thin shims, so a name disappearing here breaks
the encoder's import paths and CLI — this test is the tripwire.

The federal-tax and SNAP bridges were renamed ``ecps_tax`` -> ``tax_populace``
and ``ecps_snap`` -> ``snap_populace`` (axiom-oracles#74). The old paths remain
as deprecation shims — encode's shims swap them into ``sys.modules`` — so both
the new module names (in ``MODULES``) and the old ones (in
``DEPRECATED_MODULE_ALIASES``) are asserted here.
"""

from __future__ import annotations

import importlib
import warnings
from pathlib import Path

import pytest

MODULES = [
    "axiom_oracles.bridges",
    "axiom_oracles.bridges.adapters",
    "axiom_oracles.bridges.coverage",
    "axiom_oracles.bridges.efrs_uk",
    "axiom_oracles.bridges.jurisdiction",
    "axiom_oracles.bridges.medicaid_populace",
    "axiom_oracles.bridges.population",
    "axiom_oracles.bridges.registry",
    "axiom_oracles.bridges.repo_routing",
    "axiom_oracles.bridges.rulespec_paths",
    "axiom_oracles.bridges.snap_populace",
    "axiom_oracles.bridges.snapscreener",
    "axiom_oracles.bridges.tax_populace",
    "axiom_oracles.bridges.us_populace",
]

#: Deprecated module paths that must still import (encode's shims target these
#: via ``sys.modules``). Importing each emits a DeprecationWarning and resolves
#: to the renamed module object.
DEPRECATED_MODULE_ALIASES = {
    "axiom_oracles.bridges.ecps_snap": "axiom_oracles.bridges.snap_populace",
    "axiom_oracles.bridges.ecps_tax": "axiom_oracles.bridges.tax_populace",
}

#: Names the package __init__ promises (see bridges/README.md).
PACKAGE_EXPORTS = [
    "Case",
    "Concepts",
    "Entity",
    "GeographyScope",
    "POPULACE_PINS",
    "PolicyEngineMapping",
    "PolicyEngineOracleCoverage",
    "PolicyEngineOracleRegistry",
    "PopulacePin",
    "load_policyengine_registry",
    "load_populace_dataset",
    "resolve_populace_pin",
]

#: Module-level symbols the encoder shims (and this repo) import by name.
MODULE_SURFACE = {
    "axiom_oracles.bridges.adapters": [
        "PE_US_VAR_ADAPTERS",
        "PolicyEngineUSVarAdapter",
        "get_pe_us_var_adapter",
    ],
    "axiom_oracles.bridges.tax_populace": [
        "DEFAULT_US_POPULACE_YEAR",
    ],
    "axiom_oracles.bridges.population": [
        "POPULACE_PINS",
        "PopulacePin",
        "load_populace_dataset",
        "population_table",
        "resolve_populace_pin",
    ],
    "axiom_oracles.bridges.registry": [
        "PolicyEngineMapping",
        "PolicyEngineOracleCoverage",
        "PolicyEngineOracleRegistry",
        "load_policyengine_registry",
    ],
    "axiom_oracles.bridges.rulespec_paths": [
        "_canonical_rulespec_compile_path",
        "_rulespec_public_item_keys",
        "_rulespec_repo_alias_parent",
    ],
}


@pytest.mark.parametrize("module_name", MODULES)
def test_module_imports(module_name: str) -> None:
    importlib.import_module(module_name)


@pytest.mark.parametrize(
    ("deprecated", "target"), sorted(DEPRECATED_MODULE_ALIASES.items())
)
def test_deprecated_bridge_module_aliases_still_import(
    deprecated: str, target: str
) -> None:
    """Old ecps_* bridge paths must resolve to the renamed module and warn.

    encode's shims do ``sys.modules[...] = axiom_oracles.bridges.ecps_tax``, so
    the old path must import, emit a DeprecationWarning, and be the *same*
    module object as the renamed bridge — otherwise encode's monkeypatch
    targets and attribute access would silently diverge.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        with pytest.raises(DeprecationWarning):
            importlib.import_module(deprecated)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        legacy = importlib.import_module(deprecated)
        renamed = importlib.import_module(target)
    assert legacy is renamed


def test_package_exports() -> None:
    bridges = importlib.import_module("axiom_oracles.bridges")
    missing = [name for name in PACKAGE_EXPORTS if not hasattr(bridges, name)]
    assert not missing, f"axiom_oracles.bridges lost exports: {missing}"
    assert sorted(bridges.__all__) == sorted(PACKAGE_EXPORTS)


@pytest.mark.parametrize("module_name", sorted(MODULE_SURFACE))
def test_module_surface(module_name: str) -> None:
    module = importlib.import_module(module_name)
    missing = [name for name in MODULE_SURFACE[module_name] if not hasattr(module, name)]
    assert not missing, f"{module_name} lost symbols: {missing}"


def test_shared_case_types_are_core_types() -> None:
    """bridges re-exports the ONE Case/Concepts definition, not a copy."""
    bridges = importlib.import_module("axiom_oracles.bridges")
    core_case = importlib.import_module("axiom_oracles.core.case")
    assert bridges.Case is core_case.Case
    assert bridges.Concepts is core_case.Concepts
    assert bridges.Entity is core_case.Entity


def test_populace_us_pins_derive_from_bridge_pins() -> None:
    """The populace:// pin table re-keys the shared certified pin table."""
    bridge_population = importlib.import_module("axiom_oracles.bridges.population")
    populace_us = importlib.import_module("axiom_oracles.populations.populace_us")
    for pin in bridge_population.POPULACE_PINS.values():
        derived = populace_us.POPULACE_PINS[(pin.repo_id, pin.filename)]
        assert derived.revision == pin.revision
        assert derived.sha256 == pin.sha256
    assert len(populace_us.POPULACE_PINS) == len(bridge_population.POPULACE_PINS)


def test_packaged_data_files_present() -> None:
    """Registry mappings and coverage program surfaces ship with the package."""
    registry = importlib.import_module("axiom_oracles.bridges.registry")
    package_dir = Path(registry.__file__).parent
    mapping_files = sorted(p.name for p in (package_dir / "mappings").glob("*.yaml"))
    assert "us.yaml" in mapping_files and "uk.yaml" in mapping_files
    assert (package_dir / "program_surfaces" / "us.yaml").is_file()


def test_registry_loads_packaged_mappings() -> None:
    registry = importlib.import_module("axiom_oracles.bridges.registry")
    loaded = registry.load_policyengine_registry()
    assert loaded.mappings_by_legal_id, "packaged mapping registry is empty"
