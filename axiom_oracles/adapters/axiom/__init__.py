"""Axiom RuleSpec adapter."""

from .runner import AxiomRulesRunner
from .snap_co_projection import attach_axiom_snap_co_inputs
from .tax_projection import (
    US_TAX_ORACLE_BRIDGE_TARGET,
    US_TAX_ORACLE_IMPORTS,
    US_TAX_ORACLE_PROGRAM_RULES,
    attach_axiom_tax_inputs,
    attach_axiom_tax_itemization_choice,
)

__all__ = [
    "AxiomRulesRunner",
    "US_TAX_ORACLE_BRIDGE_TARGET",
    "US_TAX_ORACLE_IMPORTS",
    "US_TAX_ORACLE_PROGRAM_RULES",
    "attach_axiom_snap_co_inputs",
    "attach_axiom_tax_inputs",
    "attach_axiom_tax_itemization_choice",
]
