from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# The SPSM case-output facility (ASCFLAG/ASCVARS, ASCSTYLE 1) writes one
# labeled block per household, separated by dashed rules. Each line is
# fixed-width: variable name (cols 0..9), English description (cols 10..50,
# dot-padded or truncated), then one right-aligned integer value per
# household member for person-level variables (a single value for
# household-level ones). Values are annual dollars.
_NAME_END = 10
_VALUES_START = 51
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

    households: list[SpsmHousehold] = []
    current: SpsmHousehold | None = None
    for raw_line in path.read_text(errors="replace").splitlines():
        line = raw_line.rstrip("\n")
        if not line.strip():
            continue
        if line.startswith(_RULE_PREFIX):
            continue
        name = line[:_NAME_END].strip()
        if not name:
            continue
        values = _parse_values(line)
        if values is None:
            continue
        if name == "hdseqhh":
            current = SpsmHousehold(sequence=int(values[0]))
            households.append(current)
        if current is None:
            continue
        current.values[name] = values
    return households


def _parse_values(line: str) -> list[float] | None:
    tail = line[_VALUES_START:].split()
    if not tail:
        return None
    values: list[float] = []
    for token in tail:
        try:
            values.append(float(token))
        except ValueError:
            return None
    return values
