"""Statistics Canada SPSD/M adapter.

The Package (model + synthetic database) is licensed, never vendored;
see ``spsm_pins.json`` and ``docs/spsdm-oracle-design.md`` for the
licence constraints this adapter enforces.
"""

from .extract import SpsmHousehold, parse_case_output
from .runner import SPSM_ATTRIBUTION_NOTICE, SpsmRunner, spsm_install_root

__all__ = [
    "SPSM_ATTRIBUTION_NOTICE",
    "SpsmHousehold",
    "SpsmRunner",
    "parse_case_output",
    "spsm_install_root",
]
