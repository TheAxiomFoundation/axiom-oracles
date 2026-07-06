"""Deprecated alias for :mod:`axiom_oracles.populations.populace_us`.

The US-representative population loader was renamed from ``enhanced_cps`` to
``populace_us`` because every scope it serves resolves the certified
**populace-us** artifact — the only Enhanced-CPS load left is the NYC per-city
file, kept until the populace spine grows place geography (see
TheAxiomFoundation/axiom-oracles#74).

This module re-exports the new one under the old path so external callers keep
working while they migrate. It swaps itself into ``sys.modules`` with the real
module so attribute access, imports, and monkeypatch targets behave
identically. Do not add code here; edit ``populace_us`` instead.
"""

from __future__ import annotations

import sys
import warnings

import axiom_oracles.populations.populace_us as _populace_us

warnings.warn(
    "axiom_oracles.populations.enhanced_cps is deprecated; import "
    "axiom_oracles.populations.populace_us instead (the loader resolves the "
    "certified populace-us artifact for every scope but NYC — "
    "axiom-oracles#74).",
    DeprecationWarning,
    stacklevel=2,
)

sys.modules[__name__] = _populace_us
