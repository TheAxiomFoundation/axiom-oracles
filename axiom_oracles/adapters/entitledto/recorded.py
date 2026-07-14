"""Recorded-fixture oracle for the entitledto benefits calculator.

entitledto sells API access and its legal notices bar automated data
collection (``fixtures/uk_ctr/CAPTURE-PROTOCOL.md``), so — unlike the ACCESS NYC
adapter, which can call a sandbox API or run the open-source engine — this
adapter never probes entitledto live. It compares against **recorded** calculator
responses: a human runs each case once, by hand, on the public calculator and
records the result (with provenance) into a fixture JSON. This runner replays
those fixtures. It is the ACCESS-NYC-synthetic-report pattern taken to its
logical end: the recording *is* the oracle, and live access is only the (human,
out-of-band) capture step, never something CI does.

A fixture that has not been captured yet is a ``pending_capture`` stub: it
carries the exact inputs to enter but ``outputs: null``. The runner surfaces it
as an errored :class:`EngineResult` with no values, so a pending case can never
be mistaken for a real £0 award or produce a spurious match — an uncaptured
fixture stays uncaptured until a human fills it, and is never invented.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...core.case import Case
from ...core.engine import EngineAdapter
from ...core.results import EngineResult

CAPTURE_STATUS_PENDING = "pending_capture"
CAPTURE_STATUS_CAPTURED = "captured"

# The output rows an entitledto result page shows that this oracle records. The
# EngineResult is keyed by these names; the concept registry points each CTR /
# UC / HB / PC concept's ``entitledto`` target at the matching name.
OUTPUT_FIELDS = (
    "council_tax_reduction",
    "universal_credit",
    "housing_benefit",
    "pension_credit",
)

# Provenance fields every fixture must carry so a recorded value is auditable
# and reproducible without this session's context.
_REQUIRED_PROVENANCE = (
    "calculator",
    "calculator_url",
    "scheme_year",
    "council_name",
    "council_gss_code",
    "council_tax_band",
    "capture_status",
)

# Default fixtures live next to the adapter so the runner resolves them in a
# source checkout (how the comparison harness runs) without configuration.
DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "uk_ctr"


@dataclass(frozen=True)
class RecordedCapture:
    """One recorded (or pending) entitledto calculator response for a case."""

    case_id: str
    oracle: str
    provenance: dict[str, Any]
    inputs: dict[str, Any]
    outputs: dict[str, Any] | None
    source_path: Path | None = None

    @property
    def capture_status(self) -> str:
        return str(self.provenance.get("capture_status", CAPTURE_STATUS_PENDING))

    @property
    def is_captured(self) -> bool:
        return self.capture_status == CAPTURE_STATUS_CAPTURED and self.outputs is not None

    def annual_value(self, field: str) -> float | None:
        """Annual GBP for an output row, or ``None`` when not recorded."""
        if not self.outputs:
            return None
        entry = self.outputs.get(field)
        if entry is None:
            return None
        return _annual_gbp(entry)


def load_capture(path: str | Path) -> RecordedCapture:
    path = Path(path)
    data = json.loads(path.read_text())
    return RecordedCapture(
        case_id=str(data["case_id"]),
        oracle=str(data.get("oracle", "entitledto")),
        provenance=dict(data.get("provenance") or {}),
        inputs=dict(data.get("inputs") or {}),
        outputs=data.get("outputs"),
        source_path=path,
    )


def load_captures_by_id(
    fixtures_dir: str | Path | None = None,
) -> dict[str, RecordedCapture]:
    directory = Path(fixtures_dir) if fixtures_dir else DEFAULT_FIXTURES_DIR
    captures: dict[str, RecordedCapture] = {}
    for path in sorted(directory.glob("*.json")):
        capture = load_capture(path)
        captures[capture.case_id] = capture
    return captures


def validate_capture(capture: RecordedCapture) -> list[str]:
    """Return the fixture's provenance/integrity problems (empty == valid).

    Enforced both by the test suite and, at capture time, before a human commits
    a filled fixture — a ``captured`` fixture missing provenance or a CTR amount
    is a loud failure, never a silently accepted (or invented) value.
    """
    problems: list[str] = []
    for field in _REQUIRED_PROVENANCE:
        if not capture.provenance.get(field):
            problems.append(f"provenance missing {field!r}")

    status = capture.capture_status
    if status not in (CAPTURE_STATUS_PENDING, CAPTURE_STATUS_CAPTURED):
        problems.append(f"unknown capture_status {status!r}")

    if status == CAPTURE_STATUS_PENDING:
        if capture.outputs is not None:
            problems.append("pending_capture fixture must have outputs: null")
    else:  # captured
        for field in ("capture_date", "captured_by"):
            if not capture.provenance.get(field):
                problems.append(f"captured fixture missing provenance {field!r}")
        if not capture.outputs:
            problems.append("captured fixture must record outputs")
        elif capture.annual_value("council_tax_reduction") is None:
            problems.append(
                "captured fixture must record a council_tax_reduction annual amount"
            )
    return problems


class EntitledToRecordedRunner(EngineAdapter):
    """Replay recorded entitledto responses as an :class:`EngineAdapter`."""

    name = "entitledto"

    def __init__(self, fixtures_dir: str | Path | None = None):
        self.fixtures_dir = Path(fixtures_dir) if fixtures_dir else DEFAULT_FIXTURES_DIR
        self._captures = load_captures_by_id(self.fixtures_dir)

    def run_cases(
        self,
        cases: list[Case],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        del variables
        return [self._result_for_case(case) for case in cases]

    def _result_for_case(self, case: Case) -> EngineResult:
        capture = self._captures.get(str(case.case_id))
        if capture is None:
            return EngineResult(
                engine=self.name,
                household_id=case.case_id,
                values={},
                raw=None,
                errors=(f"no entitledto fixture for case {case.case_id!r}",),
            )
        if not capture.is_captured:
            return EngineResult(
                engine=self.name,
                household_id=case.case_id,
                values={},
                raw={"provenance": capture.provenance, "inputs": capture.inputs},
                errors=(
                    f"{capture.capture_status}: entitledto output not yet captured "
                    f"for case {case.case_id!r}",
                ),
            )
        values = {
            field: capture.annual_value(field)
            for field in OUTPUT_FIELDS
            if capture.annual_value(field) is not None
        }
        return EngineResult(
            engine=self.name,
            household_id=case.case_id,
            values=values,
            raw={"provenance": capture.provenance, "outputs": capture.outputs},
        )


def _annual_gbp(entry: Any) -> float | None:
    """Annualise a recorded output row (explicit annual wins; else week/month)."""
    if isinstance(entry, int | float):
        return float(entry)
    if not isinstance(entry, dict):
        return None
    if entry.get("annual_gbp") is not None:
        return float(entry["annual_gbp"])
    if entry.get("weekly_gbp") is not None:
        return round(float(entry["weekly_gbp"]) * 52.0, 2)
    if entry.get("monthly_gbp") is not None:
        return round(float(entry["monthly_gbp"]) * 12.0, 2)
    return None
