"""Conformance harness — per-oracle policy-universe enumeration and scoring.

The conformance layer answers one question with an auditable predicate rather
than a vibe: *for a given oracle, is every policy it simulates either covered by
an Axiom comparison suite that matches, or excluded for a declared reason, with
no unexplained residual and no open Axiom-attributed gap?*

Two halves keep that honest:

* **Universe facts are generated from the oracle's own model spine** — never
  hand-invented. :mod:`axiom_oracles.conformance.universe` parses the UKMOD /
  EUROMOD policy XML (and a policyengine variable stub) to enumerate every
  policy the oracle simulates and the queryable output variables it writes.
* **Scope decisions are committed and drift-checked.** Each generated row
  carries an ``in_scope`` flag and, when out of scope, a required
  ``exclusion_reason`` from a closed enum. The generator re-derives the facts
  and fails CI if the committed universe drifts from the model — so a new
  oracle policy cannot silently disappear from the accounting.

See ``conformance/README.md`` for the adoption workflow and the exact
conformance predicate.
"""

from axiom_oracles.conformance.compositions import (
    COMPOSITIONS_SCHEMA_VERSION,
    CompositionsDocument,
    ResolvedComposition,
    SuiteComposition,
    build_compositions_document,
    composition_for_suite,
    load_composition,
    resolve_suite_program,
    rulespec_imports_for_concepts,
)
from axiom_oracles.conformance.schema import (
    CONFORMANCE_SCHEMA_VERSION,
    EXCLUSION_REASONS,
    ExclusionReason,
    UniversePolicy,
)

__all__ = [
    "COMPOSITIONS_SCHEMA_VERSION",
    "CONFORMANCE_SCHEMA_VERSION",
    "CompositionsDocument",
    "EXCLUSION_REASONS",
    "ExclusionReason",
    "ResolvedComposition",
    "SuiteComposition",
    "UniversePolicy",
    "build_compositions_document",
    "composition_for_suite",
    "load_composition",
    "resolve_suite_program",
    "rulespec_imports_for_concepts",
]
