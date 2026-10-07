"""FIIT binding must follow the FIIT producer's actual compared outputs."""

import importlib.util
import json
from pathlib import Path

import pytest

from axiom_oracles.conformance.attestation import attest


ROOT = Path(__file__).parents[1]


def _adapter():
    spec = importlib.util.spec_from_file_location(
        "fiit_run_comparison", ROOT / "scripts/run_comparison.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._adapt_tax_ecps_to_v2


@pytest.mark.parametrize(
    ("surface", "output", "variable"),
    [
        ("tax-before-credits", "income_tax_main_rates", "income_tax_main_rates"),
        ("ctc", "ctc_before_advance_payments", "ctc"),
        ("standard-deduction", "basic_standard_deduction", "basic_standard_deduction"),
        ("income-tax", "income_tax_refundable_credits", "income_tax_refundable_credits"),
    ],
)
def test_adapter_attests_only_positive_fiit_output_summary_rows(surface, output, variable):
    raw = {
        "compared_tax_units": 1,
        "compared_values": 1,
        "mismatch_count": 0,
        "mismatches": [],
        "output_summary": [
            {"surface": surface, "output": output, "compared": 1, "mismatches": 0},
            {
                "surface": "capital-gain-definitions",
                "output": "net_capital_gain",
                "compared": 0,
                "mismatches": 0,
            },
        ],
    }
    report = _adapter()(raw, {}, suite="fiit-ecps")
    evidence = attest(report, oracle="policyengine")

    assert evidence.attested_outputs == frozenset({variable})
    assert evidence.outputs_complete
    assert evidence.eligible
    assert report["output_summary"] == raw["output_summary"]
    assert report["attestation"]["outputs"] == [
        {
            "engine": "policyengine",
            "concept": report["aggregates"][1]["concept"],
            "variable": variable,
            "comparisons": 1,
        }
    ]


def test_committed_legacy_fiit_uses_its_own_producer_bindings():
    report = json.loads(
        (ROOT / "dashboard/public/data/axiom-policyengine-fiit-ecps.json").read_text()
    )
    evidence = attest(report, oracle="policyengine")

    assert not evidence.binds(("capital_gains_tax",))
    assert evidence.binds(("income_tax_main_rates", "ctc"))
    assert "ctc" in evidence.attested_outputs
    assert "ctc_value" not in evidence.attested_outputs
    # The parent is a total of component comparisons, not a queried income_tax.
    assert "income_tax" not in evidence.attested_outputs
    # The legacy adapter dropped the final-income-tax surface while retaining
    # its counts in the synthetic parent, so those outputs remain unrecorded.
    assert not evidence.outputs_complete


def test_partial_legacy_fiit_surface_cannot_invent_unrecorded_outputs():
    report = _adapter()(
        {
            "compared_tax_units": 1,
            "compared_values": 1,
            "mismatch_count": 0,
            "mismatches": [],
            "output_summary": [
                {
                    "surface": "ctc",
                    "output": "ctc_before_advance_payments",
                    "compared": 1,
                    "mismatches": 0,
                }
            ],
        },
        {},
        suite="fiit-ecps",
    )
    report.pop("attestation", None)
    report.pop("output_summary", None)
    report["provenance"] = {"generated_by": "scripts/run_comparison.py::fiit-ecps"}
    evidence = attest(report, oracle="policyengine")

    assert evidence.attested_outputs == frozenset()
    assert not evidence.outputs_complete


def test_unidentified_legacy_fiit_producer_cannot_use_generic_bindings():
    report = json.loads(
        (ROOT / "dashboard/public/data/axiom-policyengine-fiit-ecps.json").read_text()
    )
    report.pop("provenance", None)
    evidence = attest(report, oracle="policyengine")

    assert evidence.eligible
    assert evidence.attested_outputs == frozenset()
    assert not evidence.outputs_complete
