"""EUROMOD-platform oracle adapter (EUROMOD, UKMOD)."""

from .projection import EUROMOD_INPUT_COLUMNS, euromod_input_rows
from .runner import DEFAULT_OUTPUTS, EuromodPlatformRunner

__all__ = [
    "DEFAULT_OUTPUTS",
    "EUROMOD_INPUT_COLUMNS",
    "EuromodPlatformRunner",
    "euromod_input_rows",
]
