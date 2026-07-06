"""Deprecated alias for :mod:`axiom_oracles.bridges.snap_populace`.

The SNAP oracle bridge was renamed to ``snap_populace`` because every data
path it drives resolves the certified **populace-us** artifact (via
``population.load_populace_dataset``), never Enhanced CPS — the ``ecps`` name
was a naming lie left over from the pre-populace era (see
TheAxiomFoundation/axiom-oracles#74).

This module is retained only so external callers that still import
``axiom_oracles.bridges.ecps_snap`` — notably the ``axiom-encode`` shim
``axiom_encode.oracles.policyengine.ecps_snap``, which swaps this module into
``sys.modules`` — keep working while they migrate to the new name. It replaces
itself in ``sys.modules`` with the real module so attribute access, imports,
and monkeypatch targets behave identically. Do not add code here; edit
``snap_populace`` instead.
"""

from __future__ import annotations

import sys
import warnings

import axiom_oracles.bridges.snap_populace as _snap_populace

warnings.warn(
    "axiom_oracles.bridges.ecps_snap is deprecated; import "
    "axiom_oracles.bridges.snap_populace instead. This bridge resolves the "
    "certified populace-us artifact, not Enhanced CPS (axiom-oracles#74).",
    DeprecationWarning,
    stacklevel=2,
)

sys.modules[__name__] = _snap_populace
