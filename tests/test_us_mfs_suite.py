"""The us-mfs married-filing-separately suite and its concept wiring.

Expectations here are the suite's INPUTS (case ids, facts, entities, scope)
and the static mapping/import wiring the three us-mfs comparison configs rely
on. No engine output is asserted: those are hypotheses for the reports.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from axiom_oracles.adapters.axiom.tax_projection import US_TAX_ORACLE_IMPORTS
from axiom_oracles.adapters.policyengine.taxsim_runner import (
    _taxsim_to_policyengine_pairs,
)
from axiom_oracles.adapters.taxsim.projection import taxsim_input_for_case
from axiom_oracles.cli import (
    _filter_cases_for_scope,
    _is_co_household,
    _tax_oracle_imports_for_concepts,
)
from axiom_oracles.comparison.mappings import (
    comparable_mappings,
    comparison_scope_for_targets,
    mappings_by_concept,
)
from axiom_oracles.core.case import Concepts
from axiom_oracles.core.filing import separate_filing
from axiom_oracles.suites import available_suites, load_suite, us_mfs_cases

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ADDITIONAL_MEDICARE = "us:tax/payroll#additional_medicare_tax"

# Stable contract: comparison reports and dispositions key on these ids.
_EXPECTED_IDS = [
    "mfs-wages-40000",
    "mfs-wages-150000",
    "mfs-wages-250000",
    "mfs-wages-450000",
    "mfs-wages-750000",
    "mfs-child-wages-15000",
    "mfs-child-wages-45000",
    "mfs-ss-cohabiting-wages-20000-ss-24000",
    "mfs-ss-cohabiting-ss-30000",
    "mfs-ss-lived-apart-wages-20000-ss-24000",
    "mfs-eitc-wages-6000",
    "mfs-eitc-wages-11000",
    "mfs-eitc-wages-16000",
]

# (scenario, filer age, wages, social security, child ages, lived apart)
_EXPECTED_SHAPE = {
    "mfs-wages-40000": ("childless-wages", 40, 40_000, 0, (), False),
    "mfs-wages-150000": ("childless-wages", 40, 150_000, 0, (), False),
    "mfs-wages-250000": ("childless-wages", 40, 250_000, 0, (), False),
    "mfs-wages-450000": ("childless-wages", 40, 450_000, 0, (), False),
    "mfs-wages-750000": ("childless-wages", 40, 750_000, 0, (), False),
    "mfs-child-wages-15000": ("child-lived-apart", 35, 15_000, 0, (8,), True),
    "mfs-child-wages-45000": ("child-lived-apart", 35, 45_000, 0, (8,), True),
    "mfs-ss-cohabiting-wages-20000-ss-24000": (
        "social-security",
        70,
        20_000,
        24_000,
        (),
        False,
    ),
    "mfs-ss-cohabiting-ss-30000": ("social-security", 70, 0, 30_000, (), False),
    "mfs-ss-lived-apart-wages-20000-ss-24000": (
        "social-security",
        70,
        20_000,
        24_000,
        (),
        True,
    ),
    "mfs-eitc-wages-6000": ("childless-eitc", 30, 6_000, 0, (), False),
    "mfs-eitc-wages-11000": ("childless-eitc", 30, 11_000, 0, (), False),
    "mfs-eitc-wages-16000": ("childless-eitc", 30, 16_000, 0, (), False),
}


def _config(name: str) -> dict:
    return yaml.safe_load((_REPO_ROOT / "comparisons" / f"{name}.yaml").read_text())


def test_us_mfs_is_registered_and_exported() -> None:
    assert "us-mfs" in available_suites()
    assert [c.case_id for c in load_suite("us-mfs")] == [
        c.case_id for c in us_mfs_cases()
    ]


def test_us_mfs_case_ids_are_the_stable_contract() -> None:
    assert [case.case_id for case in load_suite("us-mfs")] == _EXPECTED_IDS


@pytest.mark.parametrize("case", load_suite("us-mfs"), ids=lambda c: c.case_id)
def test_us_mfs_case_shape(case) -> None:
    scenario, age, wages, social_security, child_ages, lived_apart = _EXPECTED_SHAPE[
        case.case_id
    ]
    assert case.period == "2026"
    assert case.locale == "US"
    assert case.metadata["scope"] == {"type": "census_state", "geoid": "08"}
    assert case.metadata["suite"] == "us-mfs"
    assert case.metadata["scenario"] == scenario
    assert case.fact(Concepts.STATE_CODE) == "CO"
    assert case.fact(Concepts.MARRIED_FILING_SEPARATELY) is True

    head, *children = case.entities
    assert head.fact(Concepts.HOUSEHOLD_RELATION) == "HeadOfHousehold"
    assert head.fact(Concepts.PERSON_AGE) == age
    assert head.fact(Concepts.YEARLY_EARNED_INCOME) == wages
    assert head.fact(Concepts.SOCIAL_SECURITY_BENEFITS, 0) == social_security
    # A separate return never carries the other spouse: only the filer and
    # dependent children are entities.
    assert [c.fact(Concepts.HOUSEHOLD_RELATION) for c in children] == ["Child"] * len(
        child_ages
    )
    assert tuple(c.fact(Concepts.PERSON_AGE) for c in children) == child_ages
    assert all(entity.kind == "person" for entity in case.entities)

    filing = separate_filing(case)
    assert filing.married_filing_separately is True
    assert filing.lived_apart_from_spouse_all_year is lived_apart
    # The suite never sets the six-month fact, so it inherits lived-apart.
    assert case.fact(Concepts.SPOUSE_ABSENT_LAST_SIX_MONTHS) is None
    assert filing.spouse_absent_last_six_months is lived_apart


def test_social_security_cases_set_the_residence_fact_explicitly() -> None:
    # The residence fact is the variable under test for 26 USC 86(c)(1)(C),
    # so the cohabiting cases state False rather than relying on the default.
    by_id = {case.case_id: case for case in load_suite("us-mfs")}
    for case_id in (
        "mfs-ss-cohabiting-wages-20000-ss-24000",
        "mfs-ss-cohabiting-ss-30000",
    ):
        assert by_id[case_id].fact(Concepts.LIVED_APART_FROM_SPOUSE_ALL_YEAR) is False
    lived_apart = by_id["mfs-ss-lived-apart-wages-20000-ss-24000"]
    assert lived_apart.fact(Concepts.LIVED_APART_FROM_SPOUSE_ALL_YEAR) is True


def test_every_us_mfs_case_survives_the_colorado_tax_filter() -> None:
    # cli._prepare_cases_for_engines keeps liability, taxable income and tax
    # before credits only for _is_co_household cases on the Axiom leg.
    assert all(_is_co_household(case) for case in load_suite("us-mfs"))


@pytest.mark.parametrize(
    "left,right",
    [("axiom", "taxsim"), ("axiom", "policyengine"), ("policyengine", "taxsim")],
)
def test_every_us_mfs_case_is_in_the_engine_pair_scope(left, right) -> None:
    cases = load_suite("us-mfs")
    scope = comparison_scope_for_targets(left, right)
    assert _filter_cases_for_scope(cases, scope) == cases


@pytest.mark.parametrize("case", load_suite("us-mfs"), ids=lambda c: c.case_id)
def test_taxsim_rows_carry_no_spouse_income(case) -> None:
    # The pinned binary aborts a whole batch when a non-joint row reports
    # spouse income, so the suite must never populate a spouse column.
    row = taxsim_input_for_case(case)
    for column in ("sage", "swages", "ssemp", "sui", "sbusinc", "sprofinc"):
        assert row.get(column, 0) == 0, column
    assert row["depx"] == len(_EXPECTED_SHAPE[case.case_id][4])


def test_additional_medicare_tax_mapping_targets() -> None:
    mapping = mappings_by_concept()[_ADDITIONAL_MEDICARE]
    assert mapping.target_for_engine("axiom") == (
        "us:statutes/26/3101/b/2#additional_medicare_tax"
    )
    assert mapping.target_for_engine("policyengine") == "additional_medicare_tax"
    assert mapping.target_for_engine("taxsim") == "addmed"
    assert mapping.parent == "us:tax/federal-income-tax#liability"
    liability = mappings_by_concept()["us:tax/federal-income-tax#liability"]
    assert _ADDITIONAL_MEDICARE in liability.components


def test_additional_medicare_tax_module_is_composed_into_the_axiom_program() -> None:
    module = "us:statutes/26/3101/b/2"
    assert module in US_TAX_ORACLE_IMPORTS
    assert module in _tax_oracle_imports_for_concepts((_ADDITIONAL_MEDICARE,))


@pytest.mark.parametrize(
    "name", ["us-mfs-taxsim", "us-mfs-policyengine", "us-mfs-pe-taxsim"]
)
def test_every_configured_concept_is_comparable_for_its_engine_pair(name) -> None:
    params = _config(name)["runner"]["parameters"]
    concepts = set(params["concepts"])
    selected = comparable_mappings(
        params["left"],
        params["right"],
        locales={"US"},
        scope=comparison_scope_for_targets(params["left"], params["right"]),
        concepts=concepts,
    )
    assert {mapping.concept_id for mapping in selected} == concepts


def test_axiom_legs_share_one_concept_list_and_pinned_stack() -> None:
    taxsim = _config("us-mfs-taxsim")
    policyengine = _config("us-mfs-policyengine")
    for config in (taxsim, policyengine):
        runner = config["runner"]
        assert runner["axiom_rules_repo"] == "$HOME/axiom-rules-engine-0c39023e"
        assert runner["axiom_rules_repo_revision"] == "0c39023e"
        params = runner["parameters"]
        assert params["axiom_rulespec_repo_roots"] == "$HOME/oracle-pins"
        assert params["axiom_rulespec_repo_roots_revision"] == "ca2d424f"
    assert (
        taxsim["runner"]["parameters"]["concepts"]
        == policyengine["runner"]["parameters"]["concepts"]
    )
    assert _ADDITIONAL_MEDICARE in taxsim["runner"]["parameters"]["concepts"]


def test_pe_taxsim_leg_is_the_axiom_concept_list_plus_agi() -> None:
    axiom_concepts = _config("us-mfs-taxsim")["runner"]["parameters"]["concepts"]
    pe_taxsim = _config("us-mfs-pe-taxsim")["runner"]["parameters"]["concepts"]
    assert set(pe_taxsim) == set(axiom_concepts) | {"us:tax/federal-income-tax#agi"}
    assert _ADDITIONAL_MEDICARE in pe_taxsim


def test_pe_taxsim_leg_reads_addmed_back_as_additional_medicare_tax() -> None:
    # On the emulator leg both engines get the TAXSIM row and the PolicyEngine
    # side is read back from TAXSIM-format columns; the concept must claim the
    # `addmed` column for the PolicyEngine target the comparator reads.
    pairs = _taxsim_to_policyengine_pairs([_ADDITIONAL_MEDICARE])
    assert pairs == {"addmed": "additional_medicare_tax"}
