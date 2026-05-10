from __future__ import annotations

from .nyc_basic import nyc_basic_cases
from .nyc_synthetic import nyc_synthetic_cases


def available_suites() -> tuple[str, ...]:
    return ("nyc-basic", "nyc-synthetic")


def load_suite(name: str):
    if name == "nyc-basic":
        return nyc_basic_cases()
    if name == "nyc-synthetic":
        return nyc_synthetic_cases()
    raise ValueError(f"Unknown suite: {name}")


__all__ = ["available_suites", "load_suite", "nyc_basic_cases", "nyc_synthetic_cases"]
