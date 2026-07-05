"""Canonical per-jurisdiction case grids.

A *grid* is one ``grids/<jurisdiction>.yaml`` file describing the
oracle-neutral case skeletons every oracle in that jurisdiction runs. The
point is that comparing a jurisdiction is the *same* set of cases regardless
of which two (or three) engines are being triangulated — the UK
Axiom/PolicyEngine/UKMOD triangulation shape generalised to every
jurisdiction, not treated as a special case.

What a grid stores is deliberately narrow: the *skeleton* of each case — its
id, period, requested output concept(s), the query entity, and the demographic
and economic parameters that vary across the set — keyed to oracle-neutral
concept ids (the ``axiom_oracles.core.case.Concepts`` vocabulary and the
scenario parameter names the suites already use). It does **not** store the
per-engine projections (``axiom_inputs`` RuleSpec ``#input.`` payloads,
``euromod_inputs`` variable rows, bridge specs). Those are *derived* from the
skeleton by each suite's factory functions and stay in
``axiom_oracles.suites``; a grid is the case list, not the wiring.

This split is what makes the extraction byte-preserving: the grids are a
faithful, machine-checkable projection of the live suites (see
``axiom_oracles.grids.extract.case_skeleton`` and the extraction-equivalence
test), the suite factories are untouched, and therefore no comparison report
can shift.

Nothing here executes a case. The module is a read-only schema + loader, in
the same spirit as ``axiom_corpus.concepts.registry``.
"""

from __future__ import annotations

from .model import (
    CaseSet,
    CaseSpec,
    EntitySpec,
    Grid,
    GRID_SCHEMA_VERSION,
    load_grid,
    load_grid_file,
    load_grids,
    resolve_grid_case_set,
)

__all__ = [
    "CaseSet",
    "CaseSpec",
    "EntitySpec",
    "Grid",
    "GRID_SCHEMA_VERSION",
    "load_grid",
    "load_grid_file",
    "load_grids",
    "resolve_grid_case_set",
]
