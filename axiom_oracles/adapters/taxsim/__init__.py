"""TAXSIM adapter."""

from . import pins
from .pins import TaxsimIdentityError, TaxsimLawYearError, TaxsimPinError
from .output import (
    TaxsimOutputError,
    TaxsimRecord,
    TaxsimStdout,
    parse_taxsim_stdout,
)
from .projection import attach_taxsim_inputs, taxsim_input_for_case
from .runner import (
    BINARY_SHA256_KEY,
    DIAGNOSTICS_KEY,
    PIN_SCOPE_KEY,
    TaxsimExecution,
    TaxsimPackageRunner,
    TaxsimSelection,
)

__all__ = [
    "BINARY_SHA256_KEY",
    "DIAGNOSTICS_KEY",
    "PIN_SCOPE_KEY",
    "TaxsimExecution",
    "TaxsimIdentityError",
    "TaxsimLawYearError",
    "TaxsimOutputError",
    "TaxsimPackageRunner",
    "TaxsimPinError",
    "TaxsimRecord",
    "TaxsimSelection",
    "TaxsimStdout",
    "attach_taxsim_inputs",
    "parse_taxsim_stdout",
    "pins",
    "taxsim_input_for_case",
]
