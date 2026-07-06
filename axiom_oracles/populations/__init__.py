"""Population loaders for Axiom program comparisons."""

from .populace_us import (
    EnhancedCpsCaseLoader,
    PopulaceUsCaseLoader,
    load_enhanced_cps_cases,
    load_populace_us_cases,
)

__all__ = [
    "PopulaceUsCaseLoader",
    "load_populace_us_cases",
    # Deprecated aliases (see populace_us) — kept for external callers.
    "EnhancedCpsCaseLoader",
    "load_enhanced_cps_cases",
]
