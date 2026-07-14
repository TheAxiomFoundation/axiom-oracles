"""entitledto benefits-calculator oracle (recorded fixtures).

The per-council ground truth for UK Council Tax Reduction: entitledto models
every billing authority's CTR scheme, where PolicyEngine-UK models only the
three national schemes plus five named English councils, and UKMOD is national.
entitledto exposes no open-source engine and bars automated access, so this is
a *recorded* oracle — a human captures each case once and the runner replays it.
"""

from .input_mapper import EntitledToInputMapper
from .recorded import (
    CAPTURE_STATUS_CAPTURED,
    CAPTURE_STATUS_PENDING,
    DEFAULT_FIXTURES_DIR,
    OUTPUT_FIELDS,
    EntitledToRecordedRunner,
    RecordedCapture,
    load_capture,
    load_captures_by_id,
    validate_capture,
)

__all__ = [
    "CAPTURE_STATUS_CAPTURED",
    "CAPTURE_STATUS_PENDING",
    "DEFAULT_FIXTURES_DIR",
    "EntitledToInputMapper",
    "EntitledToRecordedRunner",
    "OUTPUT_FIELDS",
    "RecordedCapture",
    "load_capture",
    "load_captures_by_id",
    "validate_capture",
]
