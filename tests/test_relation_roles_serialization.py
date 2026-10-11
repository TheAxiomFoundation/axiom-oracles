"""Producer role hints never change public report or chunk bytes."""

import importlib.util
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from axiom_oracles.adapters.axiom.generic_inputs import attach_generic_inputs
from axiom_oracles.comparison.comparator import Comparator
from axiom_oracles.comparison.mappings import ProgramMapping
from axiom_oracles.comparison.report import (
    ComparisonReportAccumulator,
    build_comparison_report,
)
from axiom_oracles.core.case import Case, Entity
from axiom_oracles.core.results import EngineResult


def _emitter():
    path = Path(__file__).parents[1] / "scripts" / "emit_case_artifacts.py"
    spec = importlib.util.spec_from_file_location("relation_roles_emitter", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _producer_case(tmp_path, *, current_slot, member_count=3):
    relation = "us:statutes/7/2012/j#relation.member_of_household"
    artifact = {"program": {
        "relations": [{"name": relation, "arity": 2}],
        "derived": [{
            "name": "member_count", "entity": "Household",
            "expr": {"kind": "count_related", "relation": relation,
                     "current_slot": current_slot, "related_slot": 1 - current_slot},
        }],
    }}
    path = tmp_path / "producer.compiled.json"
    path.write_text(json.dumps(artifact))
    [case] = attach_generic_inputs(
        [Case("case", "2026-01", entities=tuple(
            Entity(f"person-{index}", "Person") for index in range(member_count)
        ))],
        compiled_program_path=path, load_default_mapping=False,
    )
    assert all("roles" in row for row in case.metadata["axiom_relations"])
    return case


def _without_roles(case):
    metadata = deepcopy(case.metadata)
    for record in metadata["axiom_relations"]:
        record.pop("roles")
    return replace(case, metadata=metadata)


def _comparison(case):
    mapping = ProgramMapping(
        standard="us:test#member_count", description="Member count", category="test",
        comparison="amount", targets={"axiom": "count", "policyengine": "count"},
    )
    comparisons = Comparator([mapping]).compare(
        [EngineResult("axiom", case.case_id, {"count": 3})],
        [EngineResult("policyengine", case.case_id, {"count": 3})],
    )
    return [mapping], comparisons


def _report(case):
    mappings, comparisons = _comparison(case)
    return build_comparison_report(
        suite_name="role-hints", population="synthetic", locales=set(), scope=None,
        cases=[case], mappings=mappings, comparisons=comparisons,
    )


@pytest.mark.parametrize("current_slot", [0, 1])
@pytest.mark.parametrize("streamed", [False, True])
def test_full_report_bytes_ignore_producer_roles(tmp_path, current_slot, streamed):
    case = _producer_case(tmp_path, current_slot=current_slot)
    before = deepcopy(case.metadata)
    report_bytes = []
    for index, candidate in enumerate((case, _without_roles(case))):
        if streamed:
            mappings, comparisons = _comparison(candidate)
            accumulator = ComparisonReportAccumulator(
                suite_name="role-hints", population="synthetic", locales=set(), scope=None,
                mappings=mappings, include_inputs=True,
                case_rows_path=tmp_path / f"cases-{index}.jsonl",
            )
            accumulator.add_batch([candidate], comparisons)
            path = tmp_path / f"report-{index}.json"
            accumulator.write_json(path)
            report_bytes.append(path.read_bytes())
        else:
            report_bytes.append(json.dumps(_report(candidate), sort_keys=True).encode())

    assert report_bytes[0] == report_bytes[1]
    assert b'"roles"' not in report_bytes[0]
    assert case.metadata == before


@pytest.mark.parametrize("current_slot", [0, 1])
def test_emitted_chunk_bytes_ignore_producer_roles(tmp_path, current_slot):
    case = _producer_case(tmp_path, current_slot=current_slot)
    before = deepcopy(case.metadata)
    emitter = _emitter()
    emitter.OUT_ROOT = tmp_path / "chunks"
    chunk_bytes = []
    for index, candidate in enumerate((case, _without_roles(case))):
        # Use producer metadata directly, so old reports also exercise the
        # emitter's independent boundary instead of relying on report cleanup.
        row = emitter.compact_case({
            "case_id": candidate.case_id, "metadata": candidate.metadata,
            "matches": [{"concept": "count", "left": 3, "right": 3}],
            "mismatches": [],
        }, {})
        suite = f"roles-{index}"
        emitter.write_artifacts(suite, [row], {}, "report.json", partial=False)
        chunk_bytes.append((emitter.OUT_ROOT / suite / "chunk-0.json").read_bytes())

    assert chunk_bytes[0] == chunk_bytes[1]
    assert b'"roles"' not in chunk_bytes[0]
    assert case.metadata == before


@settings(max_examples=24, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(member_count=st.integers(min_value=1, max_value=8), current_slot=st.integers(0, 1))
def test_serialization_preserves_relation_evidence_without_roles(
    tmp_path, member_count, current_slot,
):
    # Every example replaces this fixture's artifact and creates fresh Cases;
    # retaining tmp_path across examples cannot affect the projected evidence.
    case = _producer_case(tmp_path, current_slot=current_slot, member_count=member_count)
    before = deepcopy(case.metadata)
    baseline = _without_roles(case)
    with_roles = _report(case)
    without_roles = _report(baseline)
    assert json.dumps(with_roles, sort_keys=True) == json.dumps(without_roles, sort_keys=True)
    records = with_roles["cases"][0]["metadata"]["axiom_relations"]
    assert records == baseline.metadata["axiom_relations"]
    emitter = _emitter()
    assert json.dumps(emitter.engine_pair_records(case.metadata), sort_keys=True) == (
        json.dumps(emitter.engine_pair_records(baseline.metadata), sort_keys=True)
    )
    assert case.metadata == before
