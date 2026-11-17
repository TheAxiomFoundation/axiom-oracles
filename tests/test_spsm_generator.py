"""The SPSM generator's disposition accounting comes from one classification.

``scripts/generate_ca_federal_tax_spsm.py`` once wrote ``counts.unexplained``
as a literal 0 beside ``unexplained_count: len(other)``, so its committed
report says 0 and 97 for the same rows. The bucket now comes from the same
unclassified rows as ``unexplained_count``, matching ``apply_dispositions``.
These tests drive the pure accounting (``classify_rows`` and
``build_summary``); the SPSM run and the engine call need a licensed
SPSD/M install and are not exercised here.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from axiom_oracles.conformance.unexplained import (
    CLASSIFIED_DISPOSITION_KINDS,
    KNOWN_DISPOSITION_KINDS,
    assess_unexplained,
)

ROOT = Path(__file__).resolve().parents[1]
COMMITTED = ROOT / "dashboard/public/data/axiom-spsm-ca-federal-schedule-tax.json"


def _load_module():
    path = ROOT / "scripts" / "generate_ca_federal_tax_spsm.py"
    spec = importlib.util.spec_from_file_location("generate_ca_federal_tax_spsm", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # dataclass resolves string annotations through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


generator = _load_module()

_money = st.floats(min_value=0, max_value=500_000, allow_nan=False, allow_infinity=False)
_row = st.tuples(
    st.integers(min_value=0, max_value=10**6),  # household sequence
    st.integers(min_value=0, max_value=8),  # member
    _money,  # taxable income
    _money,  # SPSM schedule tax
    st.sampled_from([0.0, 0.0, 1.0, 250.0]),  # AMT difference flag
    st.sampled_from([0.0, 0.0, 5_000.0, 40_000.0]),  # household pension
)


@st.composite
def _rows_and_values(draw):
    rows = draw(st.lists(_row, max_size=60))
    values = []
    for row in rows:
        spsm_value = row[3]
        # Mix exact matches, near misses inside the $2 band, and real gaps in
        # both directions so every class is reachable.
        offset = draw(
            st.one_of(
                st.just(0.0),
                st.floats(min_value=-2, max_value=2),
                st.floats(min_value=-50_000, max_value=50_000),
            )
        )
        values.append(spsm_value + offset)
    return rows, values


@given(_rows_and_values())
@settings(deadline=None, database=None, max_examples=300)
def test_unexplained_bucket_equals_unexplained_count(data):
    rows, values = data
    classification = generator.classify_rows(rows, values)
    summary = generator.build_summary(classification)
    block = summary["dispositioned"]
    counts = block["counts"]

    assert counts["unexplained"] == block["unexplained_count"]
    assert block["unexplained_count"] == summary["unclassified_count"]
    assert block["unexplained_count"] == len(classification.unclassified)
    assert set(counts) == set(KNOWN_DISPOSITION_KINDS)
    # Conservation: every compared row lands in exactly one class.
    classified = sum(counts[kind] for kind in CLASSIFIED_DISPOSITION_KINDS)
    assert summary["match_count"] + classified + counts["unexplained"] == len(rows)
    assert classified + counts["unexplained"] == summary["mismatch_count"]
    assert counts["upstream_engine_gap"] == (
        summary["amt_overwrite_class_count"]
        + summary["pension_splitting_class_count"]
    )


@given(_rows_and_values())
@settings(deadline=None, database=None, max_examples=100)
def test_generated_block_reads_consistently_in_the_conformance_assessment(data):
    """The certificate-side reader sees one unexplained figure, conserved."""
    rows, values = data
    classification = generator.classify_rows(rows, values)
    summary = generator.build_summary(classification)
    report = {
        "suite": "ca-federal-schedule-tax-spsm",
        "engines": {"left": "axiom", "right": "spsm"},
        "summary": summary,
        "mismatches": classification.unclassified[:50],
    }
    assessment = assess_unexplained(report)
    assert assessment.defects == ()
    assert "declared unexplained counts disagree; using the maximum" not in assessment.notes
    assert (
        "disposition counts do not conserve against mismatches; using the "
        "conservative maximum"
    ) not in assessment.notes
    assert assessment.declared == summary["unclassified_count"]


def test_classification_is_deterministic():
    rows = [
        (1, 0, 50_000.0, 7_250.0, 0.0, 0.0),  # match
        (2, 0, 80_000.0, 12_000.0, 300.0, 0.0),  # AMT overwrite
        (3, 0, 60_000.0, 1_000.0, 0.0, 0.0),  # unclassified
    ]
    values = [7_251.0, 13_000.0, 9_000.0]
    first = generator.build_summary(generator.classify_rows(rows, values))
    second = generator.build_summary(generator.classify_rows(rows, values))
    assert first == second
    assert first["dispositioned"]["counts"]["unexplained"] == 1
    assert first["dispositioned"]["unexplained_count"] == 1


def test_bucket_cannot_be_supplied_by_the_caller():
    """Passing the bucket in is how the literal 0 got there; it is refused."""
    with pytest.raises(ValueError, match="not classified disposition kinds"):
        generator._dispositioned_block(
            classified_counts={"unexplained": 0, "upstream_engine_gap": 3},
            comparison_count=10,
            match_count=4,
            unexplained_count=3,
        )


@pytest.mark.parametrize("unexplained", [0, 2, 4])
def test_non_conserving_counts_are_refused(unexplained):
    with pytest.raises(ValueError, match="!= comparisons"):
        generator._dispositioned_block(
            classified_counts={"upstream_engine_gap": 3},
            comparison_count=10,
            match_count=4,
            unexplained_count=unexplained,
        )


def test_generator_rebuilds_the_committed_summary_with_the_bucket_corrected():
    """Differential against the committed July 2026 run.

    The committed report keeps only aggregate counts and 50 of its 97
    unclassified rows, so this rebuilds a classification with the same
    counts. Every summary field the generator writes matches the committed
    one except ``counts.unexplained``, which the fixed generator writes as
    97 where the committed report has 0. The report itself is left as is:
    regenerating it needs the licensed SPSD/M extract.
    """
    committed = json.loads(COMMITTED.read_text())["summary"]
    classification = generator.Classification(
        comparison_count=committed["comparison_count"],
        matches=committed["match_count"],
        amt_class=committed["amt_overwrite_class_count"],
        split_class=committed["pension_splitting_class_count"],
        unclassified=[{}] * committed["unclassified_count"],
    )
    rebuilt = generator.build_summary(classification)

    assert rebuilt["dispositioned"]["counts"]["unexplained"] == 97
    assert rebuilt["dispositioned"]["unexplained_count"] == 97
    expected = json.loads(json.dumps(committed))
    expected["dispositioned"]["counts"]["unexplained"] = 97
    assert rebuilt == expected
