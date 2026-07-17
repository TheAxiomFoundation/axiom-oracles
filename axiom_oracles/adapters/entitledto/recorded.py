"""Recorded-fixture oracle for the entitledto benefits calculator.

entitledto sells API access and its legal notices bar automated *and* systematic
data collection (`fixtures/uk_ctr/CAPTURE-PROTOCOL.md`), so — unlike the ACCESS
NYC adapter, which can call a sandbox API or run the open-source engine — this
adapter never probes entitledto. It compares against **recorded** calculator
responses that a person captures once, out of band, under entitledto's express
permission, and records (with provenance) into a fixture JSON. This runner
replays those fixtures; live access is never something the code or CI does.

The load-bearing safety property is **fail-closed replay**: a fixture is graded
only if it declares itself `captured` *and* passes `validate_capture`. So an
uncaptured stub, a half-filled fixture, or a malformed value (a boolean, a
negative, a non-finite number, an unknown output key, a missing council-tax
liability) is surfaced as an errored :class:`EngineResult` with no values — it
can never be mistaken for a real £0 award or produce a spurious match. The code
cannot authenticate that a human's recorded number is truthful; the human
capturer is that trust boundary. What the code *can* and does enforce is that a
value is present, well-formed, and provenance-complete before it is ever graded,
and that nothing is invented in place of a missing capture.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...core.case import Case
from ...core.engine import EngineAdapter
from ...core.results import EngineResult

CAPTURE_STATUS_PENDING = "pending_capture"
CAPTURE_STATUS_CAPTURED = "captured"
_CAPTURE_STATUSES = (CAPTURE_STATUS_PENDING, CAPTURE_STATUS_CAPTURED)

# The output rows an entitledto result page shows that this oracle records. The
# EngineResult is keyed by these names.
OUTPUT_FIELDS = (
    "council_tax_reduction",
    "universal_credit",
    "housing_benefit",
    "pension_credit",
)
_OUTPUT_KEYS = frozenset(OUTPUT_FIELDS)

# Provenance every fixture must carry so a recorded value is auditable.
_REQUIRED_PROVENANCE = (
    "calculator",
    "calculator_url",
    "scheme_year",
    "council_name",
    "council_gss_code",
    "council_tax_band",
    "capture_status",
)

# Additional provenance a *captured* fixture must carry.
_REQUIRED_CAPTURED_PROVENANCE = (
    "capture_date",
    "captured_by",
    # entitledto derives the council tax bill from postcode + band (after any
    # single-person discount), so the actual liability it used must be recorded
    # — the report reconciles PolicyEngine and the statutory hand-check to it.
    "entitledto_council_tax_liability_gbp",
)

DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "uk_ctr"


def _is_number(value: Any) -> bool:
    """A real, finite, non-boolean number (JSON ``true`` must not read as 1)."""
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _nonneg_number(value: Any) -> bool:
    return _is_number(value) and value >= 0


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
        """True only for a captured fixture that passes strict validation."""
        return self.capture_status == CAPTURE_STATUS_CAPTURED and not validate_capture(
            self
        )

    def annual_value(self, field: str) -> float | None:
        """Annual GBP for an output row, or ``None`` when absent/invalid."""
        if not self.outputs:
            return None
        return _annual_gbp(self.outputs.get(field))


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
    """Load fixtures keyed by case id; reject duplicate ids and id/filename mismatch."""
    directory = Path(fixtures_dir) if fixtures_dir else DEFAULT_FIXTURES_DIR
    captures: dict[str, RecordedCapture] = {}
    for path in sorted(directory.glob("*.json")):
        capture = load_capture(path)
        if capture.case_id != path.stem:
            raise ValueError(
                f"fixture {path.name} declares case_id {capture.case_id!r} that does "
                f"not match its filename stem {path.stem!r}"
            )
        if capture.case_id in captures:
            prior = captures[capture.case_id].source_path
            raise ValueError(
                f"duplicate fixture case_id {capture.case_id!r} in {path.name} "
                f"(already loaded from {prior.name if prior else '?'})"
            )
        captures[capture.case_id] = capture
    return captures


def validate_capture(capture: RecordedCapture) -> list[str]:
    """Return the fixture's provenance/integrity problems (empty == valid).

    Enforced by the runner before any grading, by the test suite, and at capture
    time before a human commits a filled fixture. A ``captured`` fixture missing
    provenance, a council-tax liability, or a well-formed CTR amount — or carrying
    a boolean / negative / non-finite / unknown-key output — is a loud failure,
    never a silently graded (or invented) value.
    """
    problems: list[str] = []
    for field in _REQUIRED_PROVENANCE:
        if capture.provenance.get(field) in (None, ""):
            problems.append(f"provenance missing {field!r}")

    status = capture.capture_status
    if status not in _CAPTURE_STATUSES:
        problems.append(f"unknown capture_status {status!r}")
        return problems

    if status == CAPTURE_STATUS_PENDING:
        if capture.outputs is not None:
            problems.append("pending_capture fixture must have outputs: null")
        return problems

    # captured
    for field in _REQUIRED_CAPTURED_PROVENANCE:
        if capture.provenance.get(field) in (None, ""):
            problems.append(f"captured fixture missing provenance {field!r}")
    liability = capture.provenance.get("entitledto_council_tax_liability_gbp")
    if liability not in (None, "") and not _nonneg_number(liability):
        problems.append(
            "provenance entitledto_council_tax_liability_gbp must be a non-negative number"
        )

    outputs = capture.outputs
    if not isinstance(outputs, dict) or not outputs:
        problems.append("captured fixture must record outputs")
        return problems
    unknown = set(outputs) - _OUTPUT_KEYS
    if unknown:
        problems.append(f"captured fixture has unknown output keys {sorted(unknown)}")
    for field, entry in outputs.items():
        if field not in _OUTPUT_KEYS:
            continue
        problems.extend(f"output {field}: {p}" for p in _output_entry_problems(entry))
    if "council_tax_reduction" not in outputs:
        problems.append("captured fixture must record a council_tax_reduction amount")
    return problems


def _output_entry_problems(entry: Any) -> list[str]:
    """Strict shape check for one recorded output row (no lenient coercion).

    ``annual_gbp`` is required: the capture protocol records the calculator's
    annual figure as authoritative, and a penny-rounded weekly figure annualised
    by ×52 can differ from it by up to ±£0.26 — wider than the £0.01 comparison
    tolerance. Weekly/monthly figures are optional corroboration only, and when
    present must reconcile with the annual to within £1.
    """
    if isinstance(entry, bool):
        return ["must be a number or object, not a boolean"]
    if isinstance(entry, int | float):
        return [] if _nonneg_number(entry) else ["must be a finite non-negative number"]
    if not isinstance(entry, dict):
        return ["must be a number or an object with an annual_gbp amount"]
    if "annual_gbp" not in entry:
        return [
            "needs annual_gbp (annual is authoritative; a penny-rounded weekly or "
            "monthly figure cannot be annualised within the £0.01 tolerance)"
        ]
    problems = [
        f"{k} must be a finite non-negative number"
        for k in ("annual_gbp", "weekly_gbp", "monthly_gbp")
        if k in entry and not _nonneg_number(entry[k])
    ]
    if problems:
        return problems
    annual = float(entry["annual_gbp"])
    for key, factor in (("weekly_gbp", 52.0), ("monthly_gbp", 12.0)):
        if key in entry and abs(float(entry[key]) * factor - annual) > 1.0:
            problems.append(
                f"{key} does not corroborate annual_gbp "
                f"({entry[key]} × {factor:g} vs {annual})"
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

    def _errored(self, case_id: int | str, raw: Any, *errors: str) -> EngineResult:
        return EngineResult(
            engine=self.name, household_id=case_id, values={}, raw=raw, errors=errors
        )

    def _result_for_case(self, case: Case) -> EngineResult:
        capture = self._captures.get(str(case.case_id))
        if capture is None:
            return self._errored(
                case.case_id, None, f"no entitledto fixture for case {case.case_id!r}"
            )
        problems = validate_capture(capture)
        raw = {"provenance": capture.provenance, "inputs": capture.inputs}
        if capture.capture_status == CAPTURE_STATUS_PENDING:
            errors = (
                f"pending_capture: entitledto output not yet captured for "
                f"case {case.case_id!r}",
            )
            if problems:
                errors = errors + (f"malformed pending stub: {problems}",)
            return self._errored(case.case_id, raw, *errors)
        # claims captured
        if problems:
            # Fail closed: a captured fixture that does not validate is never graded.
            return self._errored(
                case.case_id, raw, f"invalid capture, not graded: {problems}"
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
    """The recorded annual amount; ``None`` for absent or malformed values.

    Rejects booleans (JSON ``true``/``false`` must not read as 1/0), non-finite,
    and negative values, so a malformed capture yields ``None`` rather than a
    spurious number. Only the explicit annual figure is ever graded — weekly and
    monthly figures are corroboration, never annualised into a graded value
    (penny-rounding makes ×52/×12 wider than the comparison tolerance).
    """
    if _is_number(entry):
        return float(entry) if entry >= 0 else None
    if not isinstance(entry, dict):
        return None
    if _nonneg_number(entry.get("annual_gbp")):
        return float(entry["annual_gbp"])
    return None
