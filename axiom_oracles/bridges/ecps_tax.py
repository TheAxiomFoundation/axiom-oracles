"""Deprecated alias for :mod:`axiom_oracles.bridges.tax_populace`.

The federal-tax oracle bridge was renamed to ``tax_populace`` because every
data path it drives resolves the certified **populace-us** artifact (via
``population.load_populace_dataset``), never Enhanced CPS — the ``ecps`` name
was a naming lie left over from the pre-populace era (see
TheAxiomFoundation/axiom-oracles#74).

This module is retained only so external callers that still import
``axiom_oracles.bridges.ecps_tax`` — notably the ``axiom-encode`` shim
``axiom_encode.oracles.policyengine.ecps_tax``, which swaps this module into
``sys.modules`` — keep working while they migrate to the new name. It replaces
itself in ``sys.modules`` with the real module so attribute access, imports,
and monkeypatch targets behave identically. Do not add code here; edit
``tax_populace`` instead.
"""

from __future__ import annotations

import sys
import warnings

import axiom_oracles.bridges.tax_populace as _tax_populace

warnings.warn(
    "axiom_oracles.bridges.ecps_tax is deprecated; import "
    "axiom_oracles.bridges.tax_populace instead. This bridge resolves the "
    "certified populace-us artifact, not Enhanced CPS (axiom-oracles#74).",
    DeprecationWarning,
    stacklevel=2,
)

sys.modules[__name__] = _tax_populace
