"""Comparison primitives."""

from .report import (
    COMPARISON_REPORT_SCHEMA_VERSION,
    MismatchKind,
    build_comparison_report,
    classify_mismatch,
)

__all__ = [
    "COMPARISON_REPORT_SCHEMA_VERSION",
    "MismatchKind",
    "build_comparison_report",
    "classify_mismatch",
]
