"""Deprecated alias for :mod:`axiom_oracles.adapters.axiom.populace_mapping_loader`.

The mapping loader was renamed because the population it projects is the
certified populace-us artifact, not Enhanced CPS
(TheAxiomFoundation/axiom-oracles#74). This module re-exports the new one so
external callers keep working while they migrate. Do not add code here; edit
``populace_mapping_loader`` instead.
"""

from __future__ import annotations

import warnings

from .populace_mapping_loader import (
    load_populace_mapping_for_program,
    load_populace_mapping_for_program as load_ecps_mapping_for_program,
)

warnings.warn(
    "axiom_oracles.adapters.axiom.ecps_mapping_loader is deprecated; import "
    "axiom_oracles.adapters.axiom.populace_mapping_loader instead "
    "(axiom-oracles#74).",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["load_populace_mapping_for_program", "load_ecps_mapping_for_program"]
