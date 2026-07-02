from __future__ import annotations

from .be_worker import be_worker_pit_cases, be_worker_ssc_cases
from .nyc_basic import nyc_basic_cases
from .nyc_synthetic import nyc_synthetic_cases


def available_suites() -> tuple[str, ...]:
    return ("nyc-basic", "nyc-synthetic", "be-worker-pit", "be-worker-ssc")


def load_suite(name: str):
    if name == "nyc-basic":
        return nyc_basic_cases()
    if name == "nyc-synthetic":
        return nyc_synthetic_cases()
    if name == "be-worker-pit":
        return be_worker_pit_cases()
    if name == "be-worker-ssc":
        return be_worker_ssc_cases()
    raise ValueError(f"Unknown suite: {name}")


__all__ = [
    "available_suites",
    "be_worker_pit_cases",
    "be_worker_ssc_cases",
    "load_suite",
    "nyc_basic_cases",
    "nyc_synthetic_cases",
]
