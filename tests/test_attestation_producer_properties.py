"""Producer output stamps describe observed targets, including real zero values."""

import importlib.util
from functools import lru_cache
from pathlib import Path

from hypothesis import example, given, settings
from hypothesis import strategies as st

from axiom_oracles.comparison.comparator import Comparator
from axiom_oracles.comparison.mappings import ProgramMapping
from axiom_oracles.comparison.report import build_comparison_report
from axiom_oracles.conformance.attestation import OracleTargetResolver, attest
from axiom_oracles.core.case import Case
from axiom_oracles.core.results import EngineResult


ROOT = Path(__file__).parents[1]
PROPERTY_SETTINGS = settings(max_examples=30, deadline=None, derandomize=True)
# Test-owned expectations for the four reviewed FIIT producer examples.
FIIT_OUTPUTS = (
    (
        "tax-before-credits", "income_tax_main_rates", "income_tax_main_rates",
        "us:tax/federal-income-tax#tax_before_credits",
    ),
    (
        "ctc", "ctc_before_advance_payments", "ctc",
        "us:tax/federal-income-tax#ctc",
    ),
    (
        "standard-deduction", "basic_standard_deduction", "basic_standard_deduction",
        "us:tax/federal-income-tax#standard_deduction",
    ),
    (
        "income-tax", "income_tax_refundable_credits", "income_tax_refundable_credits",
        "us:tax/federal-income-tax#income_tax",
    ),
)


@lru_cache(maxsize=1)
def _fiit_adapter():
    spec = importlib.util.spec_from_file_location(
        "fiit_property_run_comparison", ROOT / "scripts/run_comparison.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._adapt_tax_ecps_to_v2


@st.composite
def _positive_fiit_counts(draw):
    selected = draw(st.sets(st.integers(0, len(FIIT_OUTPUTS) - 1), min_size=1))
    return tuple(
        draw(st.integers(1, 20)) if index in selected else 0
        for index in range(len(FIIT_OUTPUTS))
    )


@PROPERTY_SETTINGS
@example(counts=(0, 1, 0, 0))
@given(counts=_positive_fiit_counts())
def test_fiit_stamp_targets_equal_its_positive_producer_output_subset(counts):
    output_summary = [
        {"surface": surface, "output": output, "compared": count, "mismatches": 0}
        for (surface, output, _, _), count in zip(FIIT_OUTPUTS, counts)
    ]
    report = _fiit_adapter()(
        {
            "compared_tax_units": max(counts),
            "compared_values": sum(counts),
            "mismatch_count": 0,
            "mismatches": [],
            "output_summary": output_summary,
            "observed_outputs": [
                {"case_id": index, "surface": surface, "output": output,
                 "engine": "policyengine", "variable": variable, "value": 0,
                 "counterpart_value": 0}
                for (surface, output, variable, _), count in zip(FIIT_OUTPUTS, counts)
                for index in range(count)
            ],
        },
        {},
        suite="fiit-ecps",
    )
    expected = {
        ("policyengine", concept, variable, count)
        for (_, _, variable, concept), count in zip(FIIT_OUTPUTS, counts)
        if count > 0
    }

    assert report["output_summary"] == output_summary
    assert {
        (row["engine"], row["concept"], row["variable"], row["comparisons"])
        for row in report["attestation"]["outputs"]
    } == expected
    evidence = attest(report, oracle="policyengine", resolver=OracleTargetResolver())
    assert evidence.eligible, evidence.problems
    assert evidence.attested_outputs == frozenset(variable for _, _, variable, _ in expected)


@st.composite
def _list_target_presence(draw):
    targets = draw(st.lists(
        st.sampled_from(("ordinary_tax", "gains_tax", "surtax", "credit", "levy")),
        min_size=1,
        max_size=5,
        unique=True,
    ))
    present = draw(st.sets(st.sampled_from(targets)))
    return targets, present


@PROPERTY_SETTINGS
@example(observed=(["ordinary_tax", "gains_tax"], {"ordinary_tax"}), oracle_on_left=False)
@given(observed=_list_target_presence(), oracle_on_left=st.booleans())
def test_comparator_stamp_targets_equal_observed_list_subset_including_zero(
    observed, oracle_on_left
):
    targets, present = observed
    mapping = ProgramMapping(
        standard="us:test#tax",
        description="Tax",
        category="tax",
        comparison="amount",
        targets={"axiom": "tax", "policyengine": targets},
    )
    axiom = EngineResult("axiom", "case-1", {"tax": 0})
    # A real zero is observed; an extra unmapped zero is never stamp evidence.
    oracle = EngineResult(
        "policyengine", "case-1", {**{target: 0 for target in present}, "unmapped": 0}
    )
    left, right = (oracle, axiom) if oracle_on_left else (axiom, oracle)
    comparisons = Comparator([mapping]).compare([left], [right])
    variable = comparisons[0].comparisons[0]
    observed_names = variable.left_variables if oracle_on_left else variable.right_variables
    assert observed_names == tuple(target for target in targets if target in present)

    report = build_comparison_report(
        suite_name="probe",
        population="synthetic",
        locales=set(),
        scope=None,
        cases=[Case(case_id="case-1", period="2026")],
        mappings=[mapping],
        comparisons=comparisons,
    )
    assert {
        row["variable"]
        for row in report["attestation"]["outputs"]
        if row["engine"] == "policyengine"
    } == present
