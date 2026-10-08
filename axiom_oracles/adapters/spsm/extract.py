from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# The SPSM case-output facility (ASCFLAG/ASCVARS, ASCSTYLE 1) writes one
# labeled block per household, separated by dashed rules. Each line is
# fixed-width: variable name (cols 0..9), an English description column
# whose WIDTH DEPENDS ON THE VARIABLE LIST (dot-padded or truncated), then
# one right-aligned value per household member in 8-character columns
# (a single value for household-level variables). The value-column origin
# is therefore derived per file from the ``hdseqhh`` row — its single
# sequence number occupies exactly the last 8-character cell.
_NAME_END = 10
_VALUE_CELL = 8
_RULE_PREFIX = "-----"


@dataclass
class SpsmHousehold:
    """One household's variables from a case-output extract.

    ``values[name]`` is the per-member list exactly as printed; household-
    level variables carry a single element. Licence note: instances are
    Database-derived records — they exist in memory and gitignored local
    reports only, never in committed artifacts.
    """

    sequence: int
    values: dict[str, list[float]] = field(default_factory=dict)

    def total(self, name: str, default: float = 0.0) -> float:
        row = self.values.get(name)
        if not row:
            return default
        return float(sum(row))

    def member_count(self) -> int:
        return max((len(row) for row in self.values.values()), default=0)


def parse_case_output(path: Path) -> list[SpsmHousehold]:
    """Parse an SPSM ``.prn`` case-output file into households."""

    lines = path.read_text(errors="replace").splitlines()
    values_start = _detect_values_start(lines)
    households: list[SpsmHousehold] = []
    current: SpsmHousehold | None = None
    for line in lines:
        if not line.strip() or line.startswith(_RULE_PREFIX):
            continue
        name = line[:_NAME_END].strip()
        if not name:
            continue
        values = _parse_values(line, values_start)
        if values is None:
            continue
        if name == "hdseqhh":
            current = SpsmHousehold(sequence=int(values[0]))
            households.append(current)
        if current is None:
            continue
        current.values[name] = values
    return households


def _detect_values_start(lines: list[str]) -> int:
    for line in lines:
        if line.startswith("hdseqhh"):
            return len(line.rstrip()) - _VALUE_CELL
    raise ValueError(
        "Not an SPSM case-output extract: no hdseqhh row found (include "
        "hdseqhh in ASCVARS so household identity and column origin are "
        "recoverable)."
    )


def _parse_values(line: str, values_start: int) -> list[float] | None:
    # Values are whitespace-separated within the value region. Fixed-cell
    # slicing is WRONG here: values wider than the 8-character cell
    # (8-digit incomes — a real $11.6M ECPS filer) overflow leftward into
    # the separator space, and slicing split "11670672" into 1167067 and
    # 2, manufacturing mismatches out of perfect agreement. Back off one
    # character so a one-column overflow stays inside the region, then
    # split on whitespace.
    start = values_start
    # Extend left only across digit overflow (an 8-digit value's leading
    # digit sits one column left of the cell boundary); never across the
    # dot-padded description.
    while start > 0 and line[start - 1 : start].isdigit():
        start -= 1
    tail = line[start:]
    if not tail.strip():
        return None
    values: list[float] = []
    for token in tail.split():
        try:
            values.append(float(token))
        except ValueError:
            return None
    return values or None
