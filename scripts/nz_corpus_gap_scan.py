#!/usr/bin/env python3
"""Produce the NZ CERTIFIED-v3 corpus ingest gap ledger.

The producer reads the NZ dependency and instrument disposition ledgers from
this repository, the release pin from the read-only ``rulespec-nz`` clone,
and the pinned release inventory/provision JSONL from the read-only
``axiom-corpus`` clone.  It never uses the live web.  A provision counts as
present when its own body is non-empty or, for a structural document,
schedule, or part row, at least one descendant row has a non-empty body.

Usage::

    python scripts/nz_corpus_gap_scan.py
    python scripts/nz_corpus_gap_scan.py --check
    python scripts/nz_corpus_gap_scan.py \
        --rulespec-root /path/to/rulespec-nz \
        --corpus-root /path/to/axiom-corpus
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tomllib
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from nz_spine import (
    EXPECTED_ALL_CHANNEL_ADDITIONAL_CITATIONS,
    EXPECTED_CANDIDATE_CITATIONS,
    EXPECTED_DEPENDENCY_ROOT_CITATIONS,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RULESPEC_ROOT = REPO_ROOT.parent.parent / "rulespec-nz"
DEFAULT_CORPUS_ROOT = REPO_ROOT.parent.parent / "axiom-corpus"
DEFAULT_OUTPUT = REPO_ROOT / "closure" / "nz" / "corpus-gap-scan.json"
DEPENDENCY_PATH = REPO_ROOT / "closure" / "nz" / "dependency-dispositions.json"
INSTRUMENT_PATH = REPO_ROOT / "closure" / "nz" / "instrument-dispositions.json"

SCHEMA = "axiom_oracles.nz_corpus_gap_scan.v1"
EXPECTED_RELEASE = "nz-rulespec-2026-07-25"
EXPECTED_RELEASE_CONTENT_SHA256 = (
    "fec362b985739f27910f0e950fc03e298528a42cdff6f694b19c9ed0850c8405"
)
EXPECTED_RELEASE_CORPUS_COMMIT = "2d077803ee17f921c30014b9e98ae9ee3b612512"
EXPECTED_LAW_DERIVED_ROWS = 229
EXPECTED_UNIQUE_DERIVATION_EXPRESSIONS = 77
EXPECTED_DERIVATION_EXPRESSION_SHA256 = (
    "4269491a0c3fb6b259731c31c9424321c0b31e02ad95cc65cf716c1ccb6ee02c"
)
EXPECTED_BEARING_INSTRUMENTS = 39
EXPECTED_BEARING_SOURCE_SHA256 = (
    "31baeda69fc0ce360b10d0d7103f68a44adecb039802e2d9b20a4322e7530c48"
)
EXACT_SOURCE_URLS = {
    "nz/statute/act/public/2025/0009/section/105": (
        "https://www.legislation.govt.nz/act/public/2025/0009/latest/LMS1000039.html"
    ),
}


class CorpusGapError(RuntimeError):
    """Raised when a release, source ledger, or normalized provision drifts."""


@dataclass(frozen=True)
class Instrument:
    key: str
    title: str
    citation_prefix: str | None
    source_url: str


@dataclass(frozen=True)
class Provision:
    instrument_key: str
    citation_path: str | None = None
    label: str | None = None
    source_url: str | None = None


@dataclass(frozen=True)
class PriorityCone:
    priority: int
    key: str
    target_modules: tuple[str, ...]
    reason: str
    citation_paths: tuple[str, ...]
    document_instrument_keys: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


ADDITIONAL_BEARING_SECONDARY_INSTRUMENTS = (
    Instrument(
        "double_taxation_relief_czech_republic_order_2008",
        "Double Taxation Relief (Czech Republic) Order 2008",
        "nz/regulation/regulation/public/2008/0227/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2008/227/en/latest/",
    ),
    Instrument(
        "approved_territories_qfei_order_2008",
        "Income Tax (Approved Territories for Qualifying Foreign Equity "
        "Investor Definition) Order 2008",
        "nz/regulation/regulation/public/2008/0290/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2008/290/en/latest/",
    ),
    Instrument(
        "double_taxation_relief_usa_amendment_order_2009",
        "Double Taxation Relief (United States of America) Amendment Order 2009",
        "nz/regulation/regulation/public/2009/0365/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2009/365/en/latest/",
    ),
    Instrument(
        "double_tax_agreements_singapore_order_2010",
        "Double Tax Agreements (Singapore) Order 2010",
        "nz/regulation/regulation/public/2010/0115/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2010/115/en/latest/",
    ),
    Instrument(
        "double_taxation_relief_australia_order_2010",
        "Double Taxation Relief (Australia) Order 2010",
        "nz/regulation/regulation/public/2010/0013/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2010/13/en/latest/",
    ),
    Instrument(
        "double_tax_agreements_british_virgin_islands_order_2010",
        "Double Tax Agreements (British Virgin Islands) Order 2010",
        "nz/regulation/regulation/public/2010/0146/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2010/146/en/latest/",
    ),
    Instrument(
        "double_tax_agreements_cayman_islands_order_2010",
        "Double Tax Agreements (Cayman Islands) Order 2010",
        "nz/regulation/regulation/public/2010/0147/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2010/147/en/latest/",
    ),
    Instrument(
        "double_tax_agreements_cook_islands_order_2010",
        "Double Tax Agreements (Cook Islands) Order 2010",
        "nz/regulation/regulation/public/2010/0148/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2010/148/en/latest/",
    ),
    Instrument(
        "double_tax_agreements_guernsey_order_2010",
        "Double Tax Agreements (Guernsey) Order 2010",
        "nz/regulation/regulation/public/2010/0151/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2010/151/en/latest/",
    ),
    Instrument(
        "double_tax_agreements_isle_of_man_order_2010",
        "Double Tax Agreements (Isle of Man) Order 2010",
        "nz/regulation/regulation/public/2010/0152/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2010/152/en/latest/",
    ),
    Instrument(
        "double_tax_agreements_jersey_order_2010",
        "Double Tax Agreements (Jersey) Order 2010",
        "nz/regulation/regulation/public/2010/0153/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2010/153/en/latest/",
    ),
    Instrument(
        "double_tax_agreements_turkey_order_2010",
        "Double Tax Agreements (Turkey) Order 2010",
        "nz/regulation/regulation/public/2010/0311/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2010/311/en/latest/",
    ),
    Instrument(
        "double_tax_agreements_hong_kong_order_2011",
        "Double Tax Agreements (Hong Kong) Order 2011",
        "nz/regulation/regulation/public/2011/0354/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2011/354/en/latest/",
    ),
    Instrument(
        "double_tax_agreements_papua_new_guinea_order_2013",
        "Double Tax Agreements (Papua New Guinea) Order 2013",
        "nz/regulation/regulation/public/2013/0276/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2013/276/en/latest/",
    ),
    Instrument(
        "double_tax_agreements_japan_order_2013",
        "Double Tax Agreements (Japan) Order 2013",
        "nz/regulation/regulation/public/2013/0316/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2013/316/en/latest/",
    ),
    Instrument(
        "double_tax_agreements_viet_nam_order_2014",
        "Double Tax Agreements (Viet Nam) Order 2014",
        "nz/regulation/regulation/public/2014/0112/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2014/112/en/latest/",
    ),
    Instrument(
        "income_tax_maximum_pooling_value_order_2015",
        "Income Tax (Maximum Pooling Value) Order 2015",
        "nz/regulation/regulation/public/2015/0141/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2015/141/en/latest/",
    ),
    Instrument(
        "double_tax_agreements_samoa_order_2015",
        "Double Tax Agreements (Samoa) Order 2015",
        "nz/regulation/regulation/public/2015/0261/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2015/261/en/latest/",
    ),
    Instrument(
        "double_tax_agreements_canada_order_2015",
        "Double Tax Agreements (Canada) Order 2015",
        "nz/regulation/regulation/public/2015/0074/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2015/74/en/latest/",
    ),
    Instrument(
        "double_tax_agreements_multilateral_convention_order_2018",
        "Double Tax Agreements (Multilateral Convention to Implement Tax Treaty "
        "Related Measures to Prevent Base Erosion and Profit Shifting) Order 2018",
        "nz/regulation/regulation/public/2018/0072/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2018/72/en/latest/",
    ),
    Instrument(
        "double_tax_agreements_china_order_2019",
        "Double Tax Agreements (China) Order 2019",
        "nz/regulation/regulation/public/2019/0241/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2019/241/en/latest/",
    ),
    Instrument(
        "double_tax_agreements_switzerland_order_2020",
        "Double Tax Agreements (Switzerland) Order 2020",
        "nz/regulation/regulation/public/2020/0022/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2020/22/en/latest/",
    ),
    Instrument(
        "double_taxation_relief_austria_amendment_order_2024",
        "Double Taxation Relief (Austria) Amendment Order 2024",
        "nz/regulation/regulation/public/2024/0153/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2024/153/en/latest/",
    ),
    Instrument(
        "double_tax_agreements_slovak_republic_order_2024",
        "Double Tax Agreements (Slovak Republic) Order 2024",
        "nz/regulation/regulation/public/2024/0154/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2024/154/en/latest/",
    ),
)


INSTRUMENTS = (
    Instrument(
        "accident_compensation_act_2001",
        "Accident Compensation Act 2001",
        "nz/statute/act/public/2001/0049/",
        "https://www.legislation.govt.nz/act/public/2001/49/en/latest/",
    ),
    Instrument(
        "goods_and_services_tax_act_1985",
        "Goods and Services Tax Act 1985",
        "nz/statute/act/public/1985/0141/",
        "https://www.legislation.govt.nz/act/public/1985/141/en/latest/",
    ),
    Instrument(
        "income_tax_act_2007",
        "Income Tax Act 2007",
        "nz/statute/act/public/2007/0097/",
        "https://www.legislation.govt.nz/act/public/2007/97/en/latest/",
    ),
    Instrument(
        "public_and_community_housing_management_act_1992",
        "Public and Community Housing Management Act 1992",
        "nz/statute/act/public/1992/0076/",
        "https://www.legislation.govt.nz/act/public/1992/76/en/latest/",
    ),
    Instrument(
        "tax_administration_act_1994",
        "Tax Administration Act 1994",
        "nz/statute/act/public/1994/0166/",
        "https://www.legislation.govt.nz/act/public/1994/166/en/latest/",
    ),
    Instrument(
        "social_security_act_2018",
        "Social Security Act 2018",
        "nz/statute/act/public/2018/0032/",
        "https://www.legislation.govt.nz/act/public/2018/32/en/latest/",
    ),
    Instrument(
        "legislation_act_2019",
        "Legislation Act 2019",
        "nz/statute/act/public/2019/0058/",
        "https://www.legislation.govt.nz/act/public/2019/58/en/latest/",
    ),
    Instrument(
        "taxation_annual_rates_2024_25_act_2025",
        "Taxation (Annual Rates for 2024–25, Emergency Response, and "
        "Remedial Measures) Act 2025",
        "nz/statute/act/public/2025/0009/",
        "https://www.legislation.govt.nz/act/public/2025/9/en/latest/",
    ),
    Instrument(
        "taxation_budget_measures_act_2025",
        "Taxation (Budget Measures) Act 2025",
        "nz/statute/act/public/2025/0026/",
        "https://www.legislation.govt.nz/act/public/2025/26/en/latest/",
    ),
    Instrument(
        "social_assistance_amendment_act_2025",
        "Social Assistance Legislation (Accommodation Supplement and "
        "Income-related Rent) Amendment Act 2025",
        "nz/statute/act/public/2025/0027/",
        "https://www.legislation.govt.nz/act/public/2025/27/en/latest/",
    ),
    Instrument(
        "annual_rates_act_2026",
        "Taxation (Annual Rates for 2025–26, Compliance Simplification, "
        "and Remedial Measures) Act 2026",
        "nz/statute/act/public/2026/0008/",
        "https://www.legislation.govt.nz/act/public/2026/8/en/latest/",
    ),
    Instrument(
        "social_security_modernisation_amendment_act_2026",
        "Social Security (Modernisation) Amendment Act 2026",
        "nz/statute/act/public/2026/0027/",
        "https://www.legislation.govt.nz/act/public/2026/27/en/latest/",
    ),
    Instrument(
        "student_allowances_regulations_1998",
        "Student Allowances Regulations 1998",
        "nz/regulation/regulation/public/1998/0277/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/1998/277/en/latest/",
    ),
    *ADDITIONAL_BEARING_SECONDARY_INSTRUMENTS,
    Instrument(
        "social_security_regulations_2018",
        "Social Security Regulations 2018",
        "nz/regulation/regulation/public/2018/0202/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2018/202/en/latest/",
    ),
    Instrument(
        "acc_earners_levy_regulations_2025",
        "Accident Compensation (Earners' Levy) Regulations 2025",
        "nz/regulation/regulation/public/2025/0018/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2025/18/en/latest/",
    ),
    Instrument(
        "social_security_rates_order_2026",
        "Social Security (Rates of Benefits and Allowances) Order 2026",
        "nz/regulation/regulation/public/2026/0036/",
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2026/36/en/latest/",
    ),
    Instrument(
        "ird_paye_deduction_guidance",
        "Inland Revenue — Deductions from salary and wages",
        None,
        "https://www.ird.govt.nz/deductions-from-salary-and-wages",
    ),
    Instrument(
        "ird_2026_act_commentary",
        "Taxation (Annual Rates 2025–26, Compliance Simplification, and "
        "Remedial Measures) Act 2026 commentary",
        None,
        "https://www.taxtechnical.ird.govt.nz/-/media/project/ir/tp/"
        "publications/2026/compliance-simplification-bill-act-commentary.pdf",
    ),
    Instrument(
        "ird_tib_37_5_ietc",
        "Tax Information Bulletin Vol 37 No 5 — Clarifying IETC eligibility",
        None,
        "https://www.taxtechnical.ird.govt.nz/-/media/project/ir/tt/pdfs/"
        "tib/volume-37---2025/tib-vol37-no5.pdf",
    ),
    Instrument(
        "ird_tib_37_7_wff",
        "Tax Information Bulletin Vol 37 No 7 — Budget 2025 WFF commentary",
        None,
        "https://www.taxtechnical.ird.govt.nz/-/media/project/ir/tt/pdfs/"
        "tib/volume-37---2025/tib-vol37-no7.pdf",
    ),
    Instrument(
        "ird_tra_005_21_case_summary",
        "TRA 005/21 [2023] NZTRA 1 (CSUM 23/04)",
        None,
        "https://www.taxtechnical.ird.govt.nz/case-summaries/2023/csum-23-04",
    ),
    Instrument(
        "ird_det_26_01",
        "DET 26/01",
        None,
        "https://www.taxtechnical.ird.govt.nz/determinations/"
        "emergency-events/2026/det-26-01",
    ),
    Instrument(
        "ird_det_26_02",
        "DET 26/02",
        None,
        "https://www.taxtechnical.ird.govt.nz/determinations/"
        "emergency-events/2026/det-26-02",
    ),
    Instrument(
        "ird_det_26_03",
        "DET 26/03",
        None,
        "https://www.taxtechnical.ird.govt.nz/determinations/"
        "emergency-events/2026/det-26-03",
    ),
    Instrument(
        "ird_is_26_12_fact_sheet",
        "IS 26/12 FS 1",
        None,
        "https://www.taxtechnical.ird.govt.nz/fact-sheets/2026/is-26-12-fs-1",
    ),
    Instrument(
        "ird_is_26_12",
        "IS 26/12",
        None,
        "https://www.taxtechnical.ird.govt.nz/interpretation-statements/2026/is-26-12",
    ),
)

INSTRUMENT_BY_KEY = {row.key: row for row in INSTRUMENTS}


# These supplement the 200 exact roots already ratcheted by nz_spine.  Four
# Schedule 2 definitions are named by the dependency ledger but were disclosed
# as unquantified root expansion by the V3 audit.  The remaining paths expand
# the statutory defining provisions from C1's original bearing set
# conservatively: whole cited subparts, every current section in a cited range,
# and every named schedule.  B2's additional secondary instruments are tracked
# as whole-document provisions below because none is in the pinned release.
ADDITIONAL_PATH_PROVISIONS = (
    # Explicit dependency roots outside the audit's 174-root lower bound.
    Provision(
        "social_security_act_2018",
        "nz/statute/act/public/2018/0032/schedule/2/definition/"
        "area-1-area-2-area-3-and-area-4",
    ),
    Provision(
        "social_security_act_2018",
        "nz/statute/act/public/2018/0032/schedule/2/definition/boarder",
    ),
    Provision(
        "social_security_act_2018",
        "nz/statute/act/public/2018/0032/schedule/2/definition/dependent-child",
    ),
    Provision(
        "social_security_act_2018",
        "nz/statute/act/public/2018/0032/schedule/2/definition/young-person",
    ),
    # Conservative expansion of the ITA cross-citations in bearing sources.
    *(
        Provision(
            "income_tax_act_2007", f"nz/statute/act/public/2007/0097/section/{name}"
        )
        for name in (
            "bc-1",
            "bc-6",
            "bc-7",
            "bc-8",
            "bd-3",
            "bd-4",
            "bh-1",
            "cb-32",
            "cw-12",
            "ee-65",
            "mb-5",
            "mb-6",
            "mb-14",
            "mc-11",
        )
    ),
    Provision(
        "income_tax_act_2007",
        "nz/statute/act/public/2007/0097/schedule/31",
    ),
    # Bearing amendment Acts present in the pinned release.
    *(
        Provision(
            "taxation_budget_measures_act_2025",
            f"nz/statute/act/public/2025/0026/section/{number}",
        )
        for number in (2, 7, 8, 16)
    ),
    *(
        Provision(
            "social_assistance_amendment_act_2025",
            f"nz/statute/act/public/2025/0027/section/{number}",
        )
        for number in (2, *range(4, 16))
    ),
    # Bearing legal sources absent from the pinned release.
    *(
        Provision(
            "social_security_modernisation_amendment_act_2026",
            f"nz/statute/act/public/2026/0027/section/{number}",
        )
        for number in (
            *range(4, 14),
            19,
            21,
            33,
            34,
            *range(43, 66),
        )
    ),
    *(
        Provision(
            "social_security_modernisation_amendment_act_2026",
            f"nz/statute/act/public/2026/0027/schedule/{number}",
        )
        for number in range(1, 5)
    ),
    *(
        Provision(
            "legislation_act_2019",
            f"nz/statute/act/public/2019/0058/section/{number}",
        )
        for number in (13, 14)
    ),
    # Brief C1 names the complete WEP ss 72–74 rule and rates schedule.
    Provision(
        "social_security_act_2018",
        "nz/statute/act/public/2018/0032/section/74",
    ),
)


DOCUMENT_PROVISIONS = (
    *(
        Provision(
            row.key,
            label=f"{row.title} — operative document and schedules",
        )
        for row in ADDITIONAL_BEARING_SECONDARY_INSTRUMENTS
    ),
    Provision(
        "ird_paye_deduction_guidance",
        "nz/guidance/ird/paye-deduction-tables",
        "Inland Revenue salary-and-wages guidance — ACC earners' levy "
        "deduction mechanics",
    ),
    Provision(
        "ird_2026_act_commentary",
        label="Official 2026 Act commentary — section 105 IWTC article",
    ),
    Provision(
        "ird_tib_37_5_ietc",
        label="TIB Vol 37 No 5 — Clarifying IETC eligibility",
    ),
    Provision(
        "ird_tib_37_7_wff",
        label="TIB Vol 37 No 7 — Budget 2025 WFF commentary",
    ),
    Provision(
        "ird_tra_005_21_case_summary",
        label="TRA 005/21 [2023] NZTRA 1 — CSUM 23/04",
    ),
    Provision("ird_det_26_01", label="DET 26/01 emergency-event determination"),
    Provision("ird_det_26_02", label="DET 26/02 emergency-event determination"),
    Provision("ird_det_26_03", label="DET 26/03 emergency-event determination"),
    Provision(
        "ird_is_26_12_fact_sheet",
        label="IS 26/12 FS 1 — family-scheme-income fact sheet",
    ),
    Provision(
        "ird_is_26_12",
        label="IS 26/12 — family-scheme-income interpretation statement",
    ),
)


BEARING_ELI_TO_INSTRUMENT_KEYS = {
    **{
        row.source_url: (row.key, "income_tax_act_2007")
        for row in ADDITIONAL_BEARING_SECONDARY_INSTRUMENTS
    },
    "https://www.ird.govt.nz/deductions-from-salary-and-wages": (
        "ird_paye_deduction_guidance",
    ),
    "https://www.legislation.govt.nz/act/public/1985/141/en/latest/": (
        "goods_and_services_tax_act_1985",
    ),
    "https://www.legislation.govt.nz/act/public/1992/76/en/latest/": (
        "public_and_community_housing_management_act_1992",
        "social_security_act_2018",
    ),
    "https://www.legislation.govt.nz/act/public/1994/166/en/latest/": (
        "tax_administration_act_1994",
        "income_tax_act_2007",
    ),
    "https://www.legislation.govt.nz/act/public/2026/27/en/latest/": (
        "social_security_modernisation_amendment_act_2026",
    ),
    "https://www.legislation.govt.nz/secondary-legislation/"
    "pco-drafted/1998/277/en/latest/": (
        "student_allowances_regulations_1998",
        "social_security_act_2018",
    ),
    INSTRUMENT_BY_KEY["ird_2026_act_commentary"].source_url: (
        "ird_2026_act_commentary",
    ),
    INSTRUMENT_BY_KEY["ird_tib_37_5_ietc"].source_url: (
        "ird_tib_37_5_ietc",
        "income_tax_act_2007",
    ),
    INSTRUMENT_BY_KEY["ird_tib_37_7_wff"].source_url: (
        "ird_tib_37_7_wff",
        "income_tax_act_2007",
    ),
    INSTRUMENT_BY_KEY["ird_tra_005_21_case_summary"].source_url: (
        "ird_tra_005_21_case_summary",
        "income_tax_act_2007",
        "legislation_act_2019",
    ),
    INSTRUMENT_BY_KEY["ird_det_26_01"].source_url: (
        "ird_det_26_01",
        "income_tax_act_2007",
    ),
    INSTRUMENT_BY_KEY["ird_det_26_02"].source_url: (
        "ird_det_26_02",
        "income_tax_act_2007",
    ),
    INSTRUMENT_BY_KEY["ird_det_26_03"].source_url: (
        "ird_det_26_03",
        "income_tax_act_2007",
    ),
    INSTRUMENT_BY_KEY["ird_is_26_12_fact_sheet"].source_url: (
        "ird_is_26_12_fact_sheet",
        "income_tax_act_2007",
    ),
    INSTRUMENT_BY_KEY["ird_is_26_12"].source_url: (
        "ird_is_26_12",
        "income_tax_act_2007",
    ),
}


DERIVATION_INSTRUMENT_MARKERS = (
    (
        "Accident Compensation (Earners' Levy) Regulations 2025",
        "acc_earners_levy_regulations_2025",
    ),
    ("Accident Compensation Act 2001", "accident_compensation_act_2001"),
    ("Income Tax Act 2007", "income_tax_act_2007"),
    (
        "Public and Community Housing Management Act 1992",
        "public_and_community_housing_management_act_1992",
    ),
    ("Social Security Regulations 2018", "social_security_regulations_2018"),
    ("Social Security Act 2018", "social_security_act_2018"),
    ("Student Allowances Regulations 1998", "student_allowances_regulations_1998"),
    ("Tax Administration Act 1994", "tax_administration_act_1994"),
)


def _paths(prefix: str, values: Iterable[str | int]) -> tuple[str, ...]:
    return tuple(f"{prefix}/{value}" for value in values)


PRIORITY_CONES = (
    PriorityCone(
        1,
        "acc_earnings_definition_instruments",
        ("nz/regulations/acc/earners_levy.yaml",),
        "First small-cone priority named by Brief C1: the ACC earnings "
        "definition and the bearing deduction/GST sources.",
        (
            *_paths(
                "nz/statute/act/public/2001/0049/section",
                (6, *range(9, 16), 221),
            ),
            *_paths(
                "nz/statute/act/public/2007/0097/section",
                ("rd-3b", "rd-3c", "ya-1"),
            ),
            *_paths(
                "nz/regulation/regulation/public/2025/0018/regulation",
                (4, 5, 8),
            ),
            *_paths(
                "nz/statute/act/public/1985/0141/section",
                (5, 8, 10),
            ),
        ),
        ("ird_paye_deduction_guidance",),
    ),
    PriorityCone(
        2,
        "individual_income_tax",
        ("nz/statutes/income_tax/schedule_1/individual_income_tax.yaml",),
        "Second small-cone priority named by Brief C1: taxable-income roots "
        "and the individual rates schedule consumed by the module.",
        (
            *_paths(
                "nz/statute/act/public/2007/0097/section",
                ("bc-4", "bc-5", "bd-1"),
            ),
            "nz/statute/act/public/2007/0097/schedule/1/part/a/clause/1",
        ),
    ),
    PriorityCone(
        3,
        "independent_earner_tax_credit",
        ("nz/statutes/income_tax/credits/individual_credits.yaml",),
        "Third small-cone priority named by Brief C1: IETC LC 13, YD 1, "
        "HR 8, and the non-order bearing sources selected by C1 for individual "
        "credits. B2's later secondary-instrument additions remain explicit in "
        "the global ingest worklist.",
        (
            *_paths(
                "nz/statute/act/public/2007/0097/section",
                (
                    "bc-4",
                    "bc-5",
                    "bd-1",
                    "cb-32",
                    "hr-8",
                    "lc-13",
                    "mb-13",
                    "mc-4",
                    "mc-7",
                    "mc-8",
                    "mc-11",
                    "ya-1",
                    "yd-1",
                ),
            ),
            *_paths(
                "nz/statute/act/public/1994/0166/section",
                (
                    "80ka",
                    "80kb",
                    "80kc",
                    "80kd",
                    "80ke",
                    "80kf",
                    "80kg",
                    "80kh",
                    "80ki",
                    "80kj",
                    "80kk",
                    "80kl",
                    "80klb",
                    "80kn",
                    "80ko",
                    "80kp",
                    "80kq",
                    "80kr",
                    "80ks",
                    "80kt",
                    "80ku",
                    "80kv",
                    "80kw",
                    "91aas",
                ),
            ),
            "nz/statute/act/public/2025/0009/section/105",
            *_paths(
                "nz/statute/act/public/2019/0058/section",
                (13, 14),
            ),
        ),
        (
            "ird_tib_37_5_ietc",
            "ird_tra_005_21_case_summary",
            "ird_det_26_01",
            "ird_det_26_02",
            "ird_det_26_03",
            "ird_is_26_12_fact_sheet",
            "ird_is_26_12",
        ),
    ),
    PriorityCone(
        4,
        "winter_energy_payment",
        ("nz/statutes/social_security/winter_energy_payment/core.yaml",),
        "Fourth small-cone priority named by Brief C1: Social Security Act "
        "ss 72–74, the linked entitlement/absence root, rates schedule, and "
        "the pending 2026 modernisation amendment.",
        (
            *_paths(
                "nz/statute/act/public/2018/0032/section",
                (71, 72, 73, 74, 220),
            ),
            "nz/statute/act/public/2018/0032/schedule/4/part/8/clause/lms118454",
            *_paths(
                "nz/statute/act/public/2026/0027/section",
                (*range(4, 14), 19, 21, 33, 34, *range(43, 66)),
            ),
            *_paths(
                "nz/statute/act/public/2026/0027/schedule",
                range(1, 5),
            ),
        ),
    ),
    PriorityCone(
        5,
        "demographics",
        ("nz/policies/common/demographics.yaml",),
        "Fifth small-cone priority named by Brief C1: the statutory age roots "
        "and child definitions used with observable birth dates.",
        (
            *_paths(
                "nz/statute/act/public/2007/0097/section",
                ("mc-2", "mc-3", "mc-6", "mc-7", "mc-8", "mc-9", "md-5"),
            ),
            *_paths(
                "nz/statute/act/public/2018/0032/section",
                (23, 29, 72),
            ),
            "nz/statute/act/public/2018/0032/schedule/2/definition/dependent-child",
            "nz/statute/act/public/2018/0032/schedule/2/definition/young-person",
        ),
        notes=(
            "Birth-register dates remain an external observable record; they "
            "are not corpus provision text and do not create an ingest gap.",
        ),
    ),
)


MISSING_PRIORITY_BY_INSTRUMENT = {
    "taxation_annual_rates_2024_25_act_2025": (3, "IETC amendment root"),
    "ird_tib_37_5_ietc": (3, "IETC official explanatory source"),
    "ird_tra_005_21_case_summary": (3, "IETC/WFF relationship precedent"),
    "legislation_act_2019": (3, "interpretation roots cited by IETC precedent"),
    "ird_det_26_01": (3, "individual-credits emergency-event source"),
    "ird_det_26_02": (3, "individual-credits emergency-event source"),
    "ird_det_26_03": (3, "individual-credits emergency-event source"),
    "ird_is_26_12_fact_sheet": (3, "individual-credits official guidance"),
    "ird_is_26_12": (3, "individual-credits official interpretation"),
    "social_security_modernisation_amendment_act_2026": (
        4,
        "WEP-bearing 2026 amendment roots",
    ),
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CorpusGapError(message)


def _load_mapping(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CorpusGapError(f"cannot read {label} ({path}): {exc}") from exc
    if not isinstance(value, dict):
        raise CorpusGapError(f"{label} must contain an object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise CorpusGapError(f"cannot hash {path}: {exc}") from exc
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    payload = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalized_url(value: str) -> str:
    return value.rstrip("/")


def _release_inventory(
    rulespec_root: Path, corpus_root: Path
) -> tuple[dict[str, Any], list[Path]]:
    toolchain_path = rulespec_root / ".axiom" / "toolchain.toml"
    try:
        toolchain = tomllib.loads(toolchain_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise CorpusGapError(
            f"cannot read rulespec release pin {toolchain_path}: {exc}"
        ) from exc
    pin = toolchain.get("toolchain")
    _require(isinstance(pin, dict), "rulespec toolchain pin is missing [toolchain]")
    release = pin.get("axiom_corpus_release")
    content_sha = pin.get("axiom_corpus_release_content_sha256")
    _require(release == EXPECTED_RELEASE, f"rulespec release drifted: {release!r}")
    _require(
        content_sha == EXPECTED_RELEASE_CONTENT_SHA256,
        f"rulespec release content SHA drifted: {content_sha!r}",
    )

    release_dir = corpus_root / "releases" / str(release)
    manifest_path = release_dir / f"{content_sha}.json"
    manifest = _load_mapping(manifest_path, "corpus release manifest")
    _require(
        manifest.get("content_sha256") == content_sha,
        "corpus release manifest content SHA does not match its pin",
    )
    content = manifest.get("content")
    _require(isinstance(content, dict), "corpus release manifest lacks content")
    canonical_content = json.dumps(
        content,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    _require(
        hashlib.sha256(canonical_content).hexdigest() == content_sha,
        "corpus release manifest content does not hash to the signed pin",
    )
    _require(content.get("release") == release, "corpus manifest release id drifted")
    git = content.get("git")
    _require(
        isinstance(git, dict) and git.get("commit") == EXPECTED_RELEASE_CORPUS_COMMIT,
        "corpus release commit drifted",
    )
    artifacts = content.get("artifacts")
    _require(isinstance(artifacts, list), "corpus release manifest lacks artifacts")
    provision_artifacts = [
        row
        for row in artifacts
        if isinstance(row, dict) and row.get("artifact_class") == "provisions"
    ]
    _require(
        len(provision_artifacts) == 8,
        "pinned NZ release must contain 8 provision scopes",
    )

    paths: list[Path] = []
    artifact_receipts: list[dict[str, Any]] = []
    for row in sorted(provision_artifacts, key=lambda value: str(value["path"])):
        relative = row.get("path")
        expected_sha = row.get("sha256")
        _require(isinstance(relative, str), "provision artifact has no path")
        _require(
            isinstance(expected_sha, str), f"{relative}: provision artifact has no SHA"
        )
        path = corpus_root / relative
        actual_sha = _sha256(path)
        _require(
            actual_sha == expected_sha,
            f"{relative}: bytes drifted from release manifest",
        )
        paths.append(path)
        artifact_receipts.append(
            {
                "path": relative,
                "sha256": actual_sha,
                "bytes": path.stat().st_size,
            }
        )

    return (
        {
            "release": release,
            "content_sha256": content_sha,
            "corpus_commit": git["commit"],
            "manifest_path": str(manifest_path.relative_to(corpus_root)),
            "created_at": content.get("created_at"),
            "provision_artifacts": artifact_receipts,
        },
        paths,
    )


def _read_provisions(paths: Iterable[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        try:
            with path.open(encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, 1):
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise CorpusGapError(
                            f"{path}:{line_number}: row is not an object"
                        )
                    rows.append(value)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CorpusGapError(f"cannot read provision JSONL {path}: {exc}") from exc
    return rows


def _has_body(row: Mapping[str, Any]) -> bool:
    body = row.get("body")
    return isinstance(body, str) and bool(body.strip())


def _instrument_for_path(path: str) -> Instrument:
    matches = [
        row
        for row in INSTRUMENTS
        if row.citation_prefix is not None and path.startswith(row.citation_prefix)
    ]
    _require(
        len(matches) == 1, f"normalized citation has {len(matches)} owners: {path}"
    )
    return matches[0]


def _token_label(value: str) -> str:
    if value.startswith("lms"):
        return value.upper()
    return (
        value.upper().replace("-", " ") if any(ch.isalpha() for ch in value) else value
    )


def _path_label(path: str, instrument: Instrument) -> str:
    relative = path.removeprefix(instrument.citation_prefix or "")
    pieces = relative.split("/")
    if pieces[0] == "section" and len(pieces) == 2:
        return f"{instrument.title} s {_token_label(pieces[1])}"
    if pieces[0] == "regulation" and len(pieces) == 2:
        return f"{instrument.title} reg {_token_label(pieces[1])}"
    if pieces[0] == "schedule":
        label = f"{instrument.title} Schedule {_token_label(pieces[1])}"
        if len(pieces) >= 4 and pieces[2] == "definition":
            definition = pieces[3].replace("-", " ")
            return f"{label} definition ‘{definition}’"
        if len(pieces) >= 4 and pieces[2] == "part":
            label += f" Part {_token_label(pieces[3])}"
        if len(pieces) >= 6 and pieces[4] == "clause":
            clause = pieces[5]
            if clause.startswith("lms"):
                return f"{label} clauses (consolidated corpus row {clause.upper()})"
            return f"{label} cl {_token_label(clause)}"
        return label
    raise CorpusGapError(f"cannot render normalized provision label for {path}")


def _normalized_provisions() -> list[Provision]:
    spine_paths = sorted(
        set(EXPECTED_CANDIDATE_CITATIONS)
        | set(EXPECTED_DEPENDENCY_ROOT_CITATIONS)
        | set(EXPECTED_ALL_CHANNEL_ADDITIONAL_CITATIONS)
    )
    _require(len(spine_paths) == 200, "NZ all-channel exact-root denominator drifted")
    provisions = [
        Provision(_instrument_for_path(path).key, citation_path=path)
        for path in spine_paths
    ]
    provisions.extend(ADDITIONAL_PATH_PROVISIONS)
    provisions.extend(DOCUMENT_PROVISIONS)
    identity = [
        (row.instrument_key, row.citation_path, row.label) for row in provisions
    ]
    _require(
        len(identity) == len(set(identity)), "normalized provision ledger repeats a row"
    )
    _require(
        len(provisions) == 314, "normalized provision denominator drifted from 314"
    )
    return provisions


def _source_expression_mappings(dependency: Mapping[str, Any]) -> list[dict[str, Any]]:
    grounding = dependency.get("input_grounding")
    _require(isinstance(grounding, list), "dependency input_grounding must be a list")
    law_rows = [
        row
        for row in grounding
        if isinstance(row, dict) and row.get("classification") == "law_derived"
    ]
    _require(
        len(law_rows) == EXPECTED_LAW_DERIVED_ROWS, "law-derived row count drifted"
    )
    counts = Counter(str(row.get("derivation_instrument")) for row in law_rows)
    expressions = sorted(counts)
    _require(
        len(expressions) == EXPECTED_UNIQUE_DERIVATION_EXPRESSIONS,
        "unique derivation expression count drifted",
    )
    _require(
        _canonical_sha256(expressions) == EXPECTED_DERIVATION_EXPRESSION_SHA256,
        "derivation expression bytes drifted",
    )

    mappings: list[dict[str, Any]] = []
    for expression in expressions:
        instrument_keys = {
            key for marker, key in DERIVATION_INSTRUMENT_MARKERS if marker in expression
        }
        exceptions: list[str] = []
        if "2025 No 9 s 105" in expression:
            instrument_keys.add("taxation_annual_rates_2024_25_act_2025")
        if "applicable emergency-event determinations" in expression:
            instrument_keys.update(("ird_det_26_01", "ird_det_26_02", "ird_det_26_03"))
        if "Birth-register dates" in expression:
            exceptions.append("external_observable_birth_register_record")
        if "Treasury IncomeExplorer" in expression:
            exceptions.append("no_identified_statutory_threshold_equivalent")
        if "imported income/entity definitions" in expression:
            exceptions.append(
                "unnamed_imported_definition_roots_require_encode-time_expansion"
            )
        _require(
            bool(instrument_keys or exceptions),
            f"unmapped derivation expression: {expression}",
        )
        mappings.append(
            {
                "source_expression": expression,
                "occurrence_count": counts[expression],
                "instrument_groups": sorted(instrument_keys),
                "honest_exceptions": exceptions,
            }
        )
    _require(
        sum(row["occurrence_count"] for row in mappings) == 229,
        "expression count sum drifted",
    )
    return mappings


def _bearing_mappings(instrument: Mapping[str, Any]) -> list[dict[str, Any]]:
    decisions = instrument.get("instrument_dispositions")
    supplements = instrument.get("supplemental_instruments")
    _require(isinstance(decisions, list), "instrument dispositions must be a list")
    _require(isinstance(supplements, list), "supplemental instruments must be a list")
    by_eli: dict[str, set[str]] = defaultdict(set)
    for row in [*decisions, *supplements]:
        if not isinstance(row, dict):
            raise CorpusGapError("instrument disposition row must be an object")
        if (
            row.get("status") != "pending"
            or not row.get("bears_on_computed_surface")
            or row.get("size_class") not in {"S", "M", "L"}
        ):
            continue
        value = row.get("defining_provision")
        values = value if isinstance(value, list) else [value]
        by_eli[str(row["eli"])].update(str(item) for item in values if item)

    normalized = [
        {"eli": eli, "defining_provisions": sorted(values)}
        for eli, values in sorted(by_eli.items())
    ]
    _require(
        len(normalized) == EXPECTED_BEARING_INSTRUMENTS,
        "bearing instrument count drifted",
    )
    _require(
        _canonical_sha256(normalized) == EXPECTED_BEARING_SOURCE_SHA256,
        "bearing instrument defining-provision bytes drifted",
    )
    _require(
        set(by_eli) == set(BEARING_ELI_TO_INSTRUMENT_KEYS),
        "bearing instrument mapping set drifted",
    )
    return [
        {
            **row,
            "instrument_groups": list(BEARING_ELI_TO_INSTRUMENT_KEYS[row["eli"]]),
        }
        for row in normalized
    ]


def _priority_receipts(
    ledger_with_meta: Iterable[tuple[dict[str, Any], dict[str, Any]]],
) -> list[dict[str, Any]]:
    pairs = list(ledger_with_meta)
    by_path: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    by_instrument: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(
        list
    )
    for pair in pairs:
        path = pair[1].get("citation_path")
        if isinstance(path, str):
            by_path[path].append(pair)
        by_instrument[str(pair[1]["instrument_key"])].append(pair)

    receipts: list[dict[str, Any]] = []
    for cone in PRIORITY_CONES:
        _require(
            len(cone.citation_paths) == len(set(cone.citation_paths)),
            f"{cone.key}: priority cone repeats a citation path",
        )
        selected: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for path in cone.citation_paths:
            matches = by_path.get(path, [])
            _require(
                len(matches) == 1,
                f"{cone.key}: priority path has {len(matches)} ledger rows: {path}",
            )
            selected.extend(matches)
        for instrument_key in cone.document_instrument_keys:
            matches = by_instrument.get(instrument_key, [])
            _require(
                len(matches) == 1,
                f"{cone.key}: priority document has {len(matches)} ledger rows: "
                f"{instrument_key}",
            )
            selected.extend(matches)

        identities = [
            (str(pair[1]["instrument_key"]), pair[1].get("citation_path"))
            for pair in selected
        ]
        _require(
            len(identities) == len(set(identities)),
            f"{cone.key}: priority receipt selects a provision twice",
        )
        missing = [
            pair[0]["provision"] for pair in selected if not pair[0]["in_release"]
        ]
        receipts.append(
            {
                "priority": cone.priority,
                "cone": cone.key,
                "target_modules": list(cone.target_modules),
                "priority_reason": cone.reason,
                "provision_count": len(selected),
                "in_release": len(selected) - len(missing),
                "missing": len(missing),
                "missing_provisions": sorted(missing),
                "status": "zero_gap" if not missing else "ingest_required",
                "notes": list(cone.notes),
            }
        )

    _require(
        [row["priority"] for row in receipts] == list(range(1, 6)),
        "small-cone priority order drifted",
    )
    return receipts


def build_document(*, rulespec_root: Path, corpus_root: Path) -> dict[str, Any]:
    dependency = _load_mapping(DEPENDENCY_PATH, "NZ dependency dispositions")
    instrument = _load_mapping(INSTRUMENT_PATH, "NZ instrument dispositions")
    release, artifact_paths = _release_inventory(rulespec_root, corpus_root)
    corpus_rows = _read_provisions(artifact_paths)

    by_path: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_url: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in corpus_rows:
        path = row.get("citation_path")
        url = row.get("source_url")
        if isinstance(path, str):
            by_path[path].append(row)
        if isinstance(url, str):
            by_url[_normalized_url(url)].append(row)

    normalized = _normalized_provisions()
    ledger_with_meta: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for spec in normalized:
        owner = INSTRUMENT_BY_KEY[spec.instrument_key]
        candidate_rows: list[dict[str, Any]] = []
        basis = "absent"
        if spec.citation_path is not None:
            candidate_rows.extend(by_path.get(spec.citation_path, []))
            descendant_prefix = f"{spec.citation_path}/"
            descendants = [
                row
                for path, rows in by_path.items()
                if path.startswith(descendant_prefix)
                for row in rows
            ]
            if any(_has_body(row) for row in candidate_rows):
                basis = "exact_nonempty_body"
            elif any(_has_body(row) for row in descendants):
                basis = "nonempty_descendant_body"
                candidate_rows.extend(descendants)
        else:
            candidate_rows.extend(by_url.get(_normalized_url(owner.source_url), []))
            if any(_has_body(row) for row in candidate_rows):
                basis = "official_url_nonempty_body"

        in_release = basis != "absent"
        corpus_urls = sorted(
            {
                str(row["source_url"])
                for row in candidate_rows
                if isinstance(row.get("source_url"), str)
            }
        )
        source_url = (
            spec.source_url
            or EXACT_SOURCE_URLS.get(str(spec.citation_path))
            or (corpus_urls[0] if corpus_urls else owner.source_url)
        )
        label = spec.label or _path_label(str(spec.citation_path), owner)
        ledger = {
            "provision": label,
            "in_release": in_release,
            "source_url": source_url,
        }
        meta = {
            "provision": label,
            "instrument_key": owner.key,
            "instrument": owner.title,
            "citation_path": spec.citation_path,
            "coverage_basis": basis,
        }
        ledger_with_meta.append((ledger, meta))

    ledger_with_meta.sort(
        key=lambda pair: (pair[1]["instrument"], pair[0]["provision"])
    )
    ledger = [pair[0] for pair in ledger_with_meta]
    metadata = [pair[1] for pair in ledger_with_meta]
    labels = [row["provision"] for row in ledger]
    _require(
        len(labels) == len(set(labels)), "normalized provision labels are not unique"
    )

    grouped: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for pair in ledger_with_meta:
        grouped[pair[1]["instrument_key"]].append(pair)
    instrument_counts: list[dict[str, Any]] = []
    missing_by_instrument: list[dict[str, Any]] = []
    for key, pairs in grouped.items():
        owner = INSTRUMENT_BY_KEY[key]
        present = sum(bool(row[0]["in_release"]) for row in pairs)
        missing = len(pairs) - present
        instrument_counts.append(
            {
                "instrument_key": key,
                "instrument": owner.title,
                "total": len(pairs),
                "in_release": present,
                "missing": missing,
            }
        )
        if missing:
            priority, priority_reason = MISSING_PRIORITY_BY_INSTRUMENT.get(
                key,
                (
                    6,
                    "remaining corpus-ingest work after the five named "
                    "small-cone priorities",
                ),
            )
            missing_by_instrument.append(
                {
                    "priority": priority,
                    "priority_reason": priority_reason,
                    "instrument_key": key,
                    "instrument": owner.title,
                    "missing_count": missing,
                    "provisions": [
                        row[0]["provision"] for row in pairs if not row[0]["in_release"]
                    ],
                    "source_url": owner.source_url,
                }
            )
    instrument_counts.sort(key=lambda row: str(row["instrument"]))
    missing_by_instrument.sort(
        key=lambda row: (int(row["priority"]), str(row["instrument"]))
    )

    present_count = sum(bool(row["in_release"]) for row in ledger)
    _require(len(ledger) == 314, "rendered provision denominator drifted")
    _require(
        present_count == 236,
        f"in-release provision count drifted from 236 (actual {present_count})",
    )
    _require(
        len(ledger) - present_count == 78,
        "missing provision count drifted from 78 "
        f"(actual {len(ledger) - present_count})",
    )
    _require(
        len(missing_by_instrument) == 37,
        "missing instrument count drifted from 37 "
        f"(actual {len(missing_by_instrument)})",
    )

    source_mappings = _source_expression_mappings(dependency)
    bearing_mappings = _bearing_mappings(instrument)
    priority_receipts = _priority_receipts(ledger_with_meta)
    honest_exceptions = [
        {
            "source_expression_contains": "Birth-register dates",
            "type": "external_observable_record",
            "reason": "A birth-register date is a world record, not corpus provision text; the statutory age definitions are ledgered separately.",
        },
        {
            "source_expression_contains": "Treasury IncomeExplorer FamilyAssistance_IWTC_IncomeThreshold",
            "type": "no_identified_statutory_equivalent",
            "reason": "The audit found no statutory threshold equivalent, so no invented provision enters the ingest worklist.",
        },
        {
            "source_expression_contains": "imported income/entity definitions",
            "type": "unresolved_exact_root_expansion",
            "reason": "The source expression does not name the imported definitions. Named ITA roots are scanned, but encode-time expansion remains explicit.",
        },
    ]

    return {
        "schema": SCHEMA,
        "release": release,
        "coverage_rule": (
            "in_release is true only when the pinned release has a non-empty body "
            "at the normalized citation path or official URL, or a non-empty body "
            "below an exact structural path"
        ),
        "counts": {
            "law_derived_rows": EXPECTED_LAW_DERIVED_ROWS,
            "unique_derivation_expressions": EXPECTED_UNIQUE_DERIVATION_EXPRESSIONS,
            "bearing_instruments": EXPECTED_BEARING_INSTRUMENTS,
            "provisions": len(ledger),
            "in_release": present_count,
            "missing": len(ledger) - present_count,
            "instruments": len(grouped),
            "instruments_with_missing": len(missing_by_instrument),
        },
        "provisions": ledger,
        "provision_metadata": metadata,
        "instrument_counts": instrument_counts,
        "missing_by_instrument": missing_by_instrument,
        "priority_receipts": priority_receipts,
        "ingest_worklist": missing_by_instrument,
        "source_expression_mappings": source_mappings,
        "bearing_instrument_mappings": bearing_mappings,
        "honest_exceptions": honest_exceptions,
        "normalization": {
            "subsection_rule": "subsections map to their parent section/regulation corpus row",
            "range_rule": "closed ranges are expanded inclusively",
            "subpart_rule": "named ITA subparts BC, BD, and MB are expanded to every current section row in the pinned release",
            "structural_descendant_rule": "a null-body structural root is present only when a non-empty descendant body exists",
            "all_channel_spine_roots": 200,
            "explicit_schedule_2_definition_additions": 4,
            "schedule_2_student_definition_rule": (
                "The source phrase 'Schedule 2 student definitions' is normalized "
                "to the 'full-time student' definition consumed by the "
                "jobseeker_full_time_student dependency leaf; the separate "
                "'student allowance' definition is not named by that leaf."
            ),
            "brief_c1_explicit_wep_additions": [
                "nz/statute/act/public/2018/0032/section/74"
            ],
        },
    }


def render(document: Mapping[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Fail if the committed ledger drifts"
    )
    parser.add_argument("--rulespec-root", type=Path, default=DEFAULT_RULESPEC_ROOT)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    try:
        document = build_document(
            rulespec_root=args.rulespec_root.resolve(),
            corpus_root=args.corpus_root.resolve(),
        )
        rendered = render(document)
        if args.check:
            try:
                committed = args.output.read_text(encoding="utf-8")
            except OSError as exc:
                raise CorpusGapError(
                    f"cannot read committed output {args.output}: {exc}"
                ) from exc
            if committed != rendered:
                raise CorpusGapError(f"{args.output} is out of date")
            print(
                "NZ corpus gap scan OK: "
                f"{document['counts']['provisions']} provisions, "
                f"{document['counts']['in_release']} in release, "
                f"{document['counts']['missing']} missing"
            )
            return 0
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(
            f"wrote {args.output}: {document['counts']['provisions']} provisions, "
            f"{document['counts']['missing']} missing"
        )
        return 0
    except CorpusGapError as exc:
        print(f"NZ corpus gap scan ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
