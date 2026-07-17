"""GETTSIM per-case oracle adapter (Germany dual-oracle lane).

Second, independent German comparison oracle alongside EUROMOD: pure-Python,
date-parameterised, deterministic, take-up-randomness-free.
"""

from .case import (
    KNOWN_GROUPING_IDS,
    GettsimCase,
    ProjectedInputs,
    default_value,
    flatten_tree,
    normalize_person_inputs,
    project_case,
)
from .errors import (
    GettsimAdapterError,
    GettsimInputError,
    GettsimNotInstalledError,
    GettsimTargetError,
)
from .runner import (
    LANE_POLICY_DATE,
    GettsimRunner,
    GettsimRunResult,
    gettsim_version,
)

__all__ = [
    "KNOWN_GROUPING_IDS",
    "LANE_POLICY_DATE",
    "GettsimAdapterError",
    "GettsimCase",
    "GettsimInputError",
    "GettsimNotInstalledError",
    "GettsimRunResult",
    "GettsimRunner",
    "GettsimTargetError",
    "ProjectedInputs",
    "default_value",
    "flatten_tree",
    "gettsim_version",
    "normalize_person_inputs",
    "project_case",
]
