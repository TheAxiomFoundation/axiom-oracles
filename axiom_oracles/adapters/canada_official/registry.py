from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CanadaOfficialOracle:
    oracle_id: str
    title: str
    organization: str
    url: str
    mode: str
    comparison_role: str
    implemented: bool
    notes: str


# Keep this inventory executable-only. Discovery pages, unavailable services,
# formula fallbacks, and adapters without a RuleSpec comparison target belong
# in documentation, not in the oracle registry.
ORACLES = (
    CanadaOfficialOracle(
        "cra-child-family",
        "Child and family benefits calculator",
        "Canada Revenue Agency",
        "https://apps.cra-arc.gc.ca/ebci/icbc/prot/ntr?request_locale=en_CA",
        "live_http_session",
        "numeric",
        True,
        "CCB, child disability, federal credits, ACWB, and linked provincial benefits.",
    ),
    CanadaOfficialOracle(
        "cra-pdoc",
        "Payroll Deductions Online Calculator",
        "Canada Revenue Agency",
        "https://apps.cra-arc.gc.ca/ebci/rhpd/beta/entry/en",
        "live_json_api",
        "numeric",
        True,
        "Federal/provincial withholding, CPP/CPP2, EI, employer remittance, and net pay.",
    ),
    CanadaOfficialOracle(
        "statcan-spsdm",
        "Social Policy Simulation Database and Model",
        "Statistics Canada",
        "https://www.statcan.gc.ca/en/microsimulation/spsdm/spsdm",
        "licensed_local_model",
        "numeric",
        True,
        "Licensed v34.0 adapter and reproducible full-database federal schedule-tax suite; execution requires a local SPSD/M installation and never redistributes Package data.",
    ),
)


def get_oracle(oracle_id: str) -> CanadaOfficialOracle:
    try:
        return next(item for item in ORACLES if item.oracle_id == oracle_id)
    except StopIteration as exc:
        raise KeyError(oracle_id) from exc
