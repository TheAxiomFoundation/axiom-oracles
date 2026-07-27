import json
from pathlib import Path

from scripts.sync_encoded_coverage import classify


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_ohio_bounded_income_tax_schedule_is_classified() -> None:
    assert classify(
        "us-oh/policies/income_tax/pilot_liability_pipeline.yaml"
    ) == ("state_income_tax", "OH")


def test_california_bhst_pilot_is_classified() -> None:
    assert classify(
        "us-ca/policies/income_tax/pilot_liability_pipeline.yaml"
    ) == ("state_income_tax", "CA")


def test_california_bhst_surface_is_executable_and_suite_backed() -> None:
    coverage = json.loads(
        (
            REPO_ROOT / "dashboard/public/data/coverage_overview.json"
        ).read_text()
    )
    matches = [
        entry
        for entry in coverage["axiom"]["programs"]
        if entry.get("program") == "state_income_tax"
        and entry.get("jurisdiction") == "CA"
    ]

    assert matches == [
        {
            "program": "state_income_tax",
            "jurisdiction": "CA",
            "status": "executable",
            "source": (
                "rulespec-us "
                "6b0773d3f7fa6719f208154f3e609e292ab7abe7 + pinned "
                "Populace campaign projected as ca-income-tax-populace over "
                "the TY2026 Behavioral Health Services Tax subgraph"
            ),
            "known_non_tanf_gaps": [
                "component surface only; caller supplies completed California "
                "taxable income",
                "tax-table and rate-schedule income tax, taxable-income "
                "construction, credits, payments, and final Form 540 liability "
                "remain out of scope",
            ],
            "suite": "ca-income-tax-populace",
        }
    ]


def test_minnesota_schedule_pilot_is_classified() -> None:
    assert classify(
        "us-mn/policies/income_tax/pilot_liability_pipeline.yaml"
    ) == ("state_income_tax", "MN")


def test_minnesota_schedule_surface_is_executable_and_suite_backed() -> None:
    coverage = json.loads(
        (
            REPO_ROOT / "dashboard/public/data/coverage_overview.json"
        ).read_text()
    )
    matches = [
        entry
        for entry in coverage["axiom"]["programs"]
        if entry.get("program") == "state_income_tax"
        and entry.get("jurisdiction") == "MN"
    ]

    assert matches == [
        {
            "program": "state_income_tax",
            "jurisdiction": "MN",
            "status": "executable",
            "source": (
                "rulespec-us "
                "453f8fab7c6bd83f0e0efe604377d4ef85b7db72 + pinned "
                "Populace campaign projected as mn-income-tax-populace over "
                "the tax-year-2026 continuous section 290.06 schedule"
            ),
            "known_non_tanf_gaps": [
                "schedule surface only; caller supplies completed Minnesota "
                "taxable net income and filing-status classifiers",
                "taxable-income construction, tax-table rounding, alternative "
                "minimum tax, net investment income tax, credits, payments, "
                "and final Minnesota liability remain out of scope",
            ],
            "suite": "mn-income-tax-populace",
        }
    ]


def test_new_york_main_income_tax_schedule_is_classified() -> None:
    assert classify(
        "us-ny/policies/income_tax/pilot_liability_pipeline.yaml"
    ) == ("state_income_tax", "NY")


def test_illinois_annual_before_credit_tax_is_classified() -> None:
    assert classify(
        "us-il/policies/income_tax/pilot_liability_pipeline.yaml"
    ) == ("state_income_tax", "IL")


def test_illinois_before_credit_surface_is_executable_and_suite_backed() -> None:
    coverage = json.loads(
        (
            REPO_ROOT / "dashboard/public/data/coverage_overview.json"
        ).read_text()
    )
    matches = [
        entry
        for entry in coverage["axiom"]["programs"]
        if entry.get("program") == "state_income_tax"
        and entry.get("jurisdiction") == "IL"
    ]

    assert matches == [
        {
            "program": "state_income_tax",
            "jurisdiction": "IL",
            "status": "executable",
            "source": (
                "rulespec-us "
                "453f8fab7c6bd83f0e0efe604377d4ef85b7db72 + pinned "
                "Populace campaign projected as il-income-tax-populace over "
                "the canonical bounded TY2026 annual tax before "
                "nonrefundable credits"
            ),
            "known_non_tanf_gaps": [
                "bounded before-nonrefundable-credit surface only; caller "
                "supplies completed Illinois taxable income and completed "
                "investment-credit recapture",
                "taxable-income construction, credit computation, payments, "
                "and final annual liability remain out of scope",
                "the pinned Populace exercises zero recapture for all 2,332 "
                "routed Illinois tax units; the positive-recapture branch is "
                "covered by the canonical RuleSpec fixture, not population "
                "evidence",
            ],
            "suite": "il-income-tax-populace",
        }
    ]


def test_new_york_main_income_tax_surface_is_executable_and_suite_backed() -> None:
    coverage = json.loads(
        (
            REPO_ROOT / "dashboard/public/data/coverage_overview.json"
        ).read_text()
    )
    matches = [
        entry
        for entry in coverage["axiom"]["programs"]
        if entry.get("program") == "state_income_tax"
        and entry.get("jurisdiction") == "NY"
    ]

    assert matches == [
        {
            "program": "state_income_tax",
            "jurisdiction": "NY",
            "status": "executable",
            "source": (
                "rulespec-us "
                "5d8f3469682d8058a1396745812f614ed0f79200 + pinned "
                "Populace campaign projected as ny-income-tax-populace over "
                "the canonical TY2026 Tax Law section 601 main resident "
                "schedule"
            ),
            "known_non_tanf_gaps": [
                "bounded main-schedule surface only; caller supplies completed "
                "New York taxable income and strict filing-status schedule "
                "classifiers",
                "section 601(d-5) supplemental tax, taxable-income construction, "
                "credits, local taxes, payments, and final liability remain "
                "out of scope",
            ],
            "suite": "ny-income-tax-populace",
        }
    ]


def test_kansas_k40es_schedule_is_classified() -> None:
    assert classify(
        "us-ks/policies/income_tax/2026_k40es_schedule_before_credits.yaml"
    ) == ("state_income_tax", "KS")


def test_dc_section_47_1806_03_schedule_is_classified() -> None:
    assert classify(
        "us-dc/policies/income_tax/"
        "2026_section_47_1806_03_schedule_before_credits.yaml"
    ) == ("state_income_tax", "DC")


def test_dc_state_income_tax_surface_is_executable_and_suite_backed() -> None:
    coverage = json.loads(
        (
            REPO_ROOT / "dashboard/public/data/coverage_overview.json"
        ).read_text()
    )
    matches = [
        entry
        for entry in coverage["axiom"]["programs"]
        if entry.get("program") == "state_income_tax"
        and entry.get("jurisdiction") == "DC"
    ]

    assert matches == [
        {
            "program": "state_income_tax",
            "jurisdiction": "DC",
            "status": "executable",
            "source": (
                "rulespec-us "
                "6b0773d3f7fa6719f208154f3e609e292ab7abe7 + pinned "
                "Populace campaign projected as dc-income-tax-populace over "
                "the canonical 2026 section 47-1806.03(a)(11) joint-method "
                "schedule before credits"
            ),
            "known_non_tanf_gaps": [
                "component surface only; caller supplies completed joint-method "
                "District taxable income",
                "filing-method selection, taxable-income construction, credits, "
                "payments, and final D-40 liability remain out of scope",
            ],
            "suite": "dc-income-tax-populace",
        }
    ]
