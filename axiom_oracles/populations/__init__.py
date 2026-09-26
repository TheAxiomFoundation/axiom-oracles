"""Population loaders for Axiom program comparisons."""

from .populace_us import (
    EnhancedCpsCaseLoader,
    PopulaceUsCaseLoader,
    load_enhanced_cps_cases,
    load_populace_us_cases,
)
from .taxsim_csv import (
    TaxsimCsvError,
    TaxsimCsvIntegrityError,
    load_taxsim_csv_cases,
    read_taxsim_csv,
    taxsim_csv_identity,
)

__all__ = [
    "PopulaceUsCaseLoader",
    "load_populace_us_cases",
    "TaxsimCsvError",
    "TaxsimCsvIntegrityError",
    "load_taxsim_csv_cases",
    "read_taxsim_csv",
    "taxsim_csv_identity",
    # Deprecated aliases (see populace_us) — kept for external callers.
    "EnhancedCpsCaseLoader",
    "load_enhanced_cps_cases",
]
