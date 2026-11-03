"""TAXSIM adapter."""

from . import pins
from .pins import TaxsimIdentityError, TaxsimLawYearError
from .output import (
    TaxsimOutputError,
    TaxsimRecord,
    TaxsimStdout,
    parse_taxsim_stdout,
)
from .projection import attach_taxsim_inputs, taxsim_input_for_case
from .runner import DIAGNOSTICS_KEY, TaxsimExecution, TaxsimPackageRunner

__all__ = [
    "DIAGNOSTICS_KEY",
    "TaxsimExecution",
    "TaxsimIdentityError",
    "TaxsimLawYearError",
    "TaxsimOutputError",
    "TaxsimPackageRunner",
    "TaxsimRecord",
    "TaxsimStdout",
    "attach_taxsim_inputs",
    "parse_taxsim_stdout",
    "pins",
    "taxsim_input_for_case",
]
