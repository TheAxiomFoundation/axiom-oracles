"""One itemization election per tax unit, whatever the lane compares (#624).

The Axiom tax bridge runs each tax unit twice, once taking the standard
deduction and once itemizing, and keeps one candidate. With federal concepts
in the set it kept the candidate with the lower federal income tax
(``us:statutes/26/6401#income_tax``); with state income tax alone it kept the
candidate with the lower state tax. So the Colorado value for one unit
depended on which concepts the lane compared.

26 USC 63(e)(1): "Unless an individual makes an election under this
subsection for the taxable year, no itemized deduction shall be allowed for
the taxable year", and 63(e)(2): "Any election under this subsection shall be
made on the taxpayer's return". The bridge's Colorado tax starts from that
federal taxable income, and its state income tax addback (``co_state_addback``)
applies only to a candidate that itemizes federally. One unit makes one
election, so the state lanes take the candidate the federal lanes take: the
federal election, by minimum federal income tax.

Because the old state-only choice minimized state tax over the same two
candidates, the new choice can only raise a unit's Axiom state tax or leave it
unchanged.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from axiom_oracles.adapters.axiom.runner import AxiomRulesRunner
from axiom_oracles.cli import _prepare_cases_for_engines
from axiom_oracles.core.case import Case, Concepts, Entity

PROPERTY_SETTINGS = settings(max_examples=100, deadline=None, derandomize=True)
FEDERAL_SELECTION = {"strategy": "min", "output": "us:statutes/26/6401#income_tax"}
ITEMIZES = (
    "us:statutes/26/63#input."
    "individual_makes_election_to_itemize_deductions_for_taxable_year"
)
INCOME_TAX = "us:statutes/26/6401#income_tax"
STATE_TAX = "us:tax/oracle-bridge#state_income_tax"
# Concepts whose Axiom values need the itemization candidates.
ITEMIZATION_CONCEPTS = (
    Concepts.STATE_INCOME_TAX,
    Concepts.FEDERAL_INCOME_TAX,
    Concepts.TAXABLE_INCOME,
    Concepts.TAX_BEFORE_CREDITS,
    Concepts.AMT,
)
OTHER_TAX_CONCEPTS = (
    Concepts.STANDARD_DEDUCTION,
    Concepts.EITC,
    Concepts.CTC,
    Concepts.CDCC,
    Concepts.EMPLOYEE_FICA,
)


def _colorado_filer() -> Case:
    return Case(
        case_id="co-itemizer",
        period="2026",
        metadata={"scope": {"type": "census_state", "geoid": "08"}},
        entities=(
            Entity(
                "person-1",
                "person",
                facts={
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.PERSON_AGE: 40,
                    Concepts.YEARLY_EARNED_INCOME: 120_000,
                },
            ),
        ),
        facts={Concepts.MORTGAGE_INTEREST_PAID: 12_000},
    )


def _prepared(concepts, engines=frozenset({"policyengine", "axiom"})) -> Case:
    [case] = _prepare_cases_for_engines(
        [_colorado_filer()],
        set(engines),
        tuple(concepts),
        axiom_program=None,
    )
    return case


@pytest.mark.xfail(strict=True, reason="#624: state-only lanes minimize state tax")
@pytest.mark.parametrize("oracle", ["policyengine", "taxsim"])
def test_state_only_lane_selects_by_the_federal_election(oracle) -> None:
    prepared = _prepared((Concepts.STATE_INCOME_TAX,), {oracle, "axiom"})

    assert prepared.metadata["axiom_result_selection"] == FEDERAL_SELECTION


@pytest.mark.xfail(strict=True, reason="#624: state-only lanes minimize state tax")
@PROPERTY_SETTINGS
@given(
    concepts=st.sets(
        st.sampled_from(ITEMIZATION_CONCEPTS + OTHER_TAX_CONCEPTS), min_size=1
    ).filter(lambda chosen: any(c in ITEMIZATION_CONCEPTS for c in chosen))
)
@example(concepts={Concepts.STATE_INCOME_TAX})
def test_selection_does_not_depend_on_the_concept_set(concepts) -> None:
    prepared = _prepared(sorted(concepts))

    assert prepared.metadata["axiom_result_selection"] == FEDERAL_SELECTION
    assert prepared.metadata["axiom_input_record_overlays"] == (
        _prepared((Concepts.FEDERAL_INCOME_TAX,)).metadata[
            "axiom_input_record_overlays"
        ]
    )


def _fake_engine(calls):
    """Itemizing lowers federal tax (400 < 500) and raises state tax
    (150 > 100), the shape of ecps-tax-unit-162440 and 59285."""

    def fake_run(args, **kwargs):
        calls.append(args[1])
        if args[1] in ("compile", "compile-composed"):
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        request = json.loads(kwargs["input"])
        [itemizes] = [
            record["value"]["value"]
            for record in request["dataset"]["inputs"]
            if record["name"] == ITEMIZES
        ]
        values = {
            INCOME_TAX: 400 if itemizes else 500,
            STATE_TAX: 150 if itemizes else 100,
        }
        outputs = {
            output: {
                "kind": "scalar",
                "value": {"kind": "decimal", "value": str(values[output])},
            }
            for output in request["queries"][0]["outputs"]
        }
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps({"results": [{"outputs": outputs}]}),
            stderr="",
        )

    return fake_run


@pytest.mark.xfail(strict=True, reason="#624: state-only lanes minimize state tax")
def test_state_value_comes_from_the_federal_candidate_on_every_lane(
    tmp_path: Path,
) -> None:
    state_values = {}
    for lane, concepts in {
        "state-only": (Concepts.STATE_INCOME_TAX,),
        "federal-and-state": (Concepts.STATE_INCOME_TAX, Concepts.FEDERAL_INCOME_TAX),
    }.items():
        prepared = _prepared(concepts)
        # Only the selection metadata is under test; the engine is faked.
        case = Case(
            case_id=lane,
            period="2026",
            metadata={
                "axiom_input_records": [
                    {
                        "name": ITEMIZES,
                        "entity": "TaxUnit",
                        "entity_id": "tax_unit",
                        "value": False,
                    }
                ],
                "axiom_input_record_overlays": prepared.metadata[
                    "axiom_input_record_overlays"
                ],
                "axiom_result_selection": prepared.metadata["axiom_result_selection"],
            },
        )
        calls: list[str] = []
        runner = AxiomRulesRunner(
            program_path=tmp_path / "program.yaml",
            binary_path=tmp_path / "axiom-rules",
            subprocess_run=_fake_engine(calls),
        )
        [result] = runner.run_cases([case], [STATE_TAX])
        assert result.errors == ()
        assert result.raw["selected_candidate"] == 1
        state_values[lane] = result.values[STATE_TAX]

    assert state_values == {"state-only": 150.0, "federal-and-state": 150.0}
