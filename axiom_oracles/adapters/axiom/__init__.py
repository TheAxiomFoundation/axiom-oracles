"""Axiom RuleSpec adapter."""

from .runner import AxiomRulesRunner
from .tax_projection import (
    US_FEDERAL_INCOME_TAX_IMPORTS,
    US_FEDERAL_INCOME_TAX_PROGRAM_RULES,
    attach_axiom_tax_inputs,
    attach_axiom_tax_itemization_choice,
    attach_policyengine_tax_unit_inputs,
)

__all__ = [
    "AxiomRulesRunner",
    "US_FEDERAL_INCOME_TAX_IMPORTS",
    "US_FEDERAL_INCOME_TAX_PROGRAM_RULES",
    "attach_axiom_tax_inputs",
    "attach_axiom_tax_itemization_choice",
    "attach_policyengine_tax_unit_inputs",
]
