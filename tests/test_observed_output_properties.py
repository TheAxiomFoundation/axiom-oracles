"""Every report dialect obeys the same four necessary observation conditions."""

from itertools import product

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from axiom_oracles.conformance.attestation import (
    EXECUTION_ATTESTATION_SCHEMA,
    OracleTargetResolver,
    observed_output_value,
)
from axiom_oracles.conformance.loader import OracleIdentity, Universe
from axiom_oracles.conformance.schema import UniversePolicy
from axiom_oracles.conformance.scoreboard import score_jurisdiction


SHAPES = (
    "stamped-ledger", "role-scalar", "grid-scalar", "grid-components",
    "fiit", "yale-singleton", "yale-multiple-columns",
)
FINITE_VALUES = st.one_of(
    st.booleans(), st.integers(-100, 100),
    st.floats(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False),
)
INVALID_VALUES = st.one_of(
    st.none(), st.sampled_from((float("nan"), float("inf"), float("-inf"))),
    st.sampled_from(("0", "returned string")), st.just([]), st.just({"value": 0}),
)


def _shape_report(shape, value, *, returned=True, location="metadata"):
    engine = "yale_statutory" if shape.startswith("yale-") else "policyengine"
    output = "registered_tax"
    concept = "test:policy#registered_tax"
    targets = (output,)
    suite = "observation-probe"
    engines = {"left": "axiom", "right": engine}
    if shape == "fiit":
        suite = "fiit-ecps"
        concept = "us:tax/payroll#employee_medicare"
        output = "employee_medicare_tax"
        targets = (output,)
    elif shape.startswith("yale-"):
        suite = "us-tariff-panel"
        singleton = shape == "yale-singleton"
        concept = "mfn" if singleton else "ieepa"
        output = "statutory_base_rate" if singleton else "statutory_rate_ieepa_recip"
        targets = (output,) if singleton else (output, "statutory_rate_ieepa_fent")
        engines = {"axiom": "tariff_total", engine: "Yale statutory panel"}
        # Yale's authority-slot comparison has an existing numeric-rate gate.
        # Preserve that precondition while testing the four observation gates;
        # the other dialects continue to exercise raw False as an output value.
        if isinstance(value, bool):
            value = int(value)
    elif shape.startswith("grid-"):
        if shape == "grid-components":
            targets = ("other_sum_component", output)
        engines = {"axiom": "axiom_tax", engine: ",".join(targets)}

    report = {
        "suite": suite,
        "case_count": 1,
        "engines": engines,
        "summary": {
            "comparison_count": 1, "match_count": 1, "mismatch_count": 0,
            "error_count": 0,
        },
        "aggregates": [{"concept": concept, "comparison_count": 1}],
        "output_bindings": {concept: {
            engine: list(targets),
            "axiom": list(targets) if shape in {"grid-components", "yale-multiple-columns"} else "axiom_tax",
        }},
        "attestation": {
            "schema_version": EXECUTION_ATTESTATION_SCHEMA,
            "executed": True,
            "case_count": 1,
            "comparison_count": 1,
            "error_count": 0,
        },
        "cases": [],
        "observed_outputs": [],
    }
    if shape == "fiit":
        report["output_bindings"][concept]["axiom"] = "us:statutes/26/3101/b/1#hospital_insurance_wage_tax"
    elif shape == "yale-singleton":
        report["output_bindings"][concept]["axiom"] = output
    row = {
        "case_id": "c1", "engine": engine, "concept": concept,
        "variable": output, "value": value,
    }
    if shape == "stamped-ledger":
        report["attestation"]["outputs"] = [{
            "concept": concept, "engine": engine, "variable": output,
            "comparisons": 1,
        }]
        if returned:
            report["observed_outputs"] = [row, {
                "case_id": "c1", "engine": "axiom", "concept": concept,
                "variable": "axiom_tax", "value": value,
            }]
    elif shape == "role-scalar":
        if returned:
            report["cases"] = [{
                "case_id": "c1", "matches": [{"concept": concept, "left": 0, "right": value}],
            }]
    elif shape == "grid-scalar":
        if returned:
            report["cases"] = [{"case_id": "c1", "axiom": 0, engine: value}]
    elif shape == "grid-components":
        if returned:
            report["cases"] = [{
                "case_id": "c1", "axiom": 0, engine: 0,
                f"{engine}_components": {"other_sum_component": 0, output: value},
                "axiom_components": {"other_sum_component": 0, output: 0},
            }]
    elif shape == "fiit":
        report["provenance"] = {"generated_by": "scripts/run_comparison.py::fiit-ecps"}
        report["output_summary"] = [{
            "surface": "employee-medicare", "output": output,
            "compared": 1, "mismatches": 0,
        }]
        if returned:
            report["observed_outputs"] = [dict(
                row, surface="employee-medicare", output=output, counterpart_value=0,
            )]
    else:
        report["provenance"] = {"generator": "scripts/generate_us_tariff_panel.py"}
        report["summary"]["slots"] = {concept: {"matches": 1, "mismatches": 0}}
        report["scope"] = {
            "comparison_units": 1, "authority_slots": [concept],
            "reference": {"columns": list(targets)},
        }
        # Multiple-column expected sums do not identify either returned member.
        # Positive evidence for a member comes from its own value ledger.
        report["cases"] = [{
            "case_id": "c1", "unit_count": 1,
            "expected": {concept: value if returned and len(targets) == 1 else 0},
            "axiom": {concept: 0},
        }]
        if returned and len(targets) > 1:
            report["observed_outputs"] = [row, {
                "case_id": "c1", "engine": "axiom", "concept": concept,
                "variable": output, "value": 0,
            }]
        elif not returned and len(targets) == 1:
            report["cases"][0]["expected"].pop(concept)

    if not returned:
        # Deliberately offer the exact candidate value in non-output locations.
        # None can provide evidence that an executed comparison returned it.
        report[location] = {"outputs": [row], "type": "number", "variable": output}
    return report, engine, concept, output, targets


def _execution_claim(report, claim):
    if claim == "missing-stamp":
        report.pop("attestation")
    elif claim == "missing-executed":
        report["attestation"].pop("executed")
    else:
        report["attestation"]["executed"] = claim


def _contradict(report, engine, concept, output, value, kind, *, case_id="c1", variable=None):
    row = {
        "case_id": case_id, "engine": engine, "concept": concept,
        "variable": output if variable is None else variable, "value": value,
    }
    if kind == "missing":
        row.update(value=None, missing=True)
    elif kind == "error":
        row["error"] = "output comparison failed"
    else:
        row["skipped"] = True
    report["observed_outputs"].append(row)


def _coverage(report, engine, concept, output, targets, declared_type=None):
    axiom_targets = report["output_bindings"][concept]["axiom"]
    axiom_targets = (axiom_targets,) if isinstance(axiom_targets, str) else axiom_targets
    resolver = OracleTargetResolver(
        concept_targets={concept: {engine: frozenset(targets), "axiom": frozenset(axiom_targets)}},
        output_types={} if declared_type is None else {
            (engine, output): declared_type, ("axiom", axiom_targets[0]): declared_type,
        },
    )
    oracle = OracleIdentity(
        "policyengine-us" if engine == "policyengine" else "yale-statutory",
        "1", "us", "US", "policyengine" if engine == "policyengine" else "yale-tariff",
    )
    universe = Universe("probe", oracle, [UniversePolicy(
        id="probe:registered-output", oracle_policy_name=output, output_vars=(output,),
        in_scope=True, suite=report["suite"],
    )])
    return score_jurisdiction(universe, [report], resolver=resolver)[0].covered


@pytest.mark.parametrize("shape", SHAPES)
@settings(max_examples=12, deadline=None, database=None, derandomize=True)
@given(
    finite_value=FINITE_VALUES,
    invalid_value=INVALID_VALUES,
    invalid_execution=st.sampled_from((False, None, 1, "true")),
    location=st.sampled_from(("declarations", "schema", "metadata")),
    contradiction=st.sampled_from(("missing", "error", "skipped")),
    contradiction_concept=st.sampled_from(("same-concept", "different-concept", None)),
    unrelated=st.sampled_from(("none", "different-case", "different-output")),
)
@example(finite_value=0, invalid_value=None, invalid_execution=1, location="declarations",
         contradiction="missing", contradiction_concept="different-concept", unrelated="different-output")
@example(finite_value=False, invalid_value=float("nan"), invalid_execution=False,
         location="metadata", contradiction="error", contradiction_concept="same-concept", unrelated="different-case")
@example(finite_value=0, invalid_value=None, invalid_execution=False,
         location="schema", contradiction="missing", contradiction_concept=None, unrelated="none")
def test_every_observation_condition_is_necessary_and_sufficient_in_every_report_shape(
    shape, finite_value, invalid_value, invalid_execution, location, contradiction,
    contradiction_concept, unrelated,
):
    # Exhaust all four Boolean conditions for every generated dialect/value.
    # The expected result uses test-owned conditions, never the production predicate.
    for executed, returned, valid_value, consistent in product((False, True), repeat=4):
        value = finite_value if valid_value else invalid_value
        report, engine, concept, output, targets = _shape_report(
            shape, value, returned=returned, location=location,
        )
        if shape.startswith("yale-") and isinstance(value, bool):
            value = int(value)
        _execution_claim(report, True if executed else invalid_execution)
        if not consistent:
            conflicting_concept = (
                concept if contradiction_concept == "same-concept"
                else "another:concept" if contradiction_concept == "different-concept"
                else None
            )
            _contradict(report, engine, conflicting_concept, output, value, contradiction)
        if unrelated == "different-case":
            _contradict(report, engine, concept, output, value, contradiction, case_id="c2")
        elif unrelated == "different-output":
            _contradict(report, engine, concept, output, value, contradiction, variable="unrelated_output")
        expected = executed and returned and valid_value and consistent
        observed = observed_output_value(
            report, case_id="c1", engine=engine, concept=concept,
            output=output, value=value, targets=targets,
        )
        assert observed is expected, (shape, executed, returned, valid_value, consistent)
        assert _coverage(report, engine, concept, output, targets) == int(expected)


@settings(max_examples=20, deadline=None, database=None, derandomize=True)
@given(value=st.text(min_size=1, max_size=30), registered=st.booleans())
@example(value="0", registered=True)
@example(value="0", registered=False)
def test_non_numeric_output_type_requires_registered_type_not_report_metadata(value, registered):
    report, engine, concept, output, targets = _shape_report("stamped-ledger", value)
    report["metadata"] = {"output_types": {output: "str"}}
    report["schema"] = {"properties": {output: {"type": "string"}}}
    declared_type = str if registered else None
    assert observed_output_value(
        report, case_id="c1", engine=engine, concept=concept,
        output=output, value=value, targets=targets, declared_type=declared_type,
    ) is registered
    assert _coverage(report, engine, concept, output, targets, declared_type) == int(registered)
