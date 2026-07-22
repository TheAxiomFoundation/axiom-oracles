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
        "cra-gst-hst",
        "GST/HST calculator",
        "Canada Revenue Agency",
        "https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/gst-hst-businesses/charge-collect-which-rate/calculator.html",
        "live_page_bundle",
        "numeric",
        True,
        "The official page embeds its current rate table and deterministic calculator code.",
    ),
    CanadaOfficialOracle(
        "rq-webras",
        "WebRAS",
        "Revenu Quebec",
        "https://www.revenuquebec.ca/en/online-services/tools/webras/",
        "official_formula_fallback",
        "numeric",
        False,
        "The live UI is Cloudflare-gated; TP-1015.F-V formulas are the reproducible official surface.",
    ),
    CanadaOfficialOracle(
        "esdc-ei-estimator",
        "Canadian EI Benefits Estimator",
        "Employment and Social Development Canada",
        "https://estimateurae-eiestimator.service.canada.ca/",
        "temporarily_unavailable",
        "numeric",
        False,
        "The public step-three route currently returns HTTP 500; do not record guessed outputs.",
    ),
    CanadaOfficialOracle(
        "esdc-retirement-calculator",
        "Canadian Retirement Income Calculator",
        "Employment and Social Development Canada",
        "https://srv111.services.gc.ca/GeneralInformation/Index",
        "session_bound_web_service",
        "projection",
        False,
        "CPP/OAS projections depend on user assumptions and ASP.NET session state.",
    ),
    CanadaOfficialOracle(
        "esdc-canada-disability-benefit",
        "Canada Disability Benefit amount guidance",
        "Employment and Social Development Canada",
        "https://www.canada.ca/en/services/benefits/disability/canada-disability-benefit/amount.html",
        "official_parameter_page",
        "parameter",
        False,
        "Suitable for formula and parameter parity, not an independent executable engine.",
    ),
    CanadaOfficialOracle(
        "canada-benefits-finder",
        "Benefits Finder",
        "Government of Canada",
        "https://www.canada.ca/en/services/benefits/finder/tool.html",
        "discovery_only",
        "coverage",
        False,
        "Recommends programs but does not calculate statutory entitlement amounts.",
    ),
    CanadaOfficialOracle(
        "statcan-spsdm",
        "Social Policy Simulation Database and Model",
        "Statistics Canada",
        "https://www.statcan.gc.ca/en/microsimulation/spsdm/spsdm",
        "licensed_local_model",
        "numeric",
        False,
        "Broad tax-transfer oracle pending delivery and local licensing setup.",
    ),
)


def get_oracle(oracle_id: str) -> CanadaOfficialOracle:
    try:
        return next(item for item in ORACLES if item.oracle_id == oracle_id)
    except StopIteration as exc:
        raise KeyError(oracle_id) from exc
