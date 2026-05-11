from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


Value = float | int | bool | str | None


@dataclass(frozen=True)
class EngineResult:
    engine: str
    household_id: int | str
    values: dict[str, Value]
    raw: Any = None
    errors: tuple[str, ...] = field(default_factory=tuple)

    def get(self, key: str, default: Value = None) -> Value:
        return self.values.get(key, default)
