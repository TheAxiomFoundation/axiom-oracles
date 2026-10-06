"""Companion evidence must preserve the dispute's value and output type."""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings, strategies as st

from axiom_oracles.comparison.pe_axiom_standard import (
    CompanionPointer,
    CompanionResolver,
    Record,
    attribute_disposition,
)

ROOT = Path(__file__).resolve().parent.parent
MAIN_SHA = "f" * 40
PROPERTY_SETTINGS = settings(max_examples=300, deadline=None, derandomize=True)


@lru_cache
def _record_template(suite: str, index: int) -> Record:
    entry = yaml.safe_load((ROOT / "dispositions" / f"{suite}.yaml").read_text())[
        "entries"
    ][index]
    report = json.loads(
        (ROOT / "dashboard/public/data" / f"axiom-policyengine-{suite}.json").read_text()
    )
    basis, cases, values = attribute_disposition(entry, [report])
    return Record(
        source=f"dispositions/{suite}.yaml",
        id=entry["id"],
        suite=suite,
        concept=entry["concept"],
        basis=basis,
        pe_issue=entry["evidence"]["upstream_url"],
        entry=entry,
        case_ids=cases,
        axiom_values=values,
    )


def _real_record(suite: str, index: int = 0) -> Record:
    return copy.deepcopy(_record_template(suite, index))


class AssertionSource:
    def __init__(self, record: Record, asserted, main_asserted):
        self.pointer = CompanionPointer.parse(record.entry["axiom_companion"]["tests"][0])
        assert self.pointer is not None
        self.files = {
            sha: yaml.safe_dump([
                {"name": self.pointer.case, "output": {record.concept: value}}
            ])
            for sha, value in ((self.pointer.sha, asserted), (MAIN_SHA, main_asserted))
        }

    def read(self, repo, sha, path):
        return self.files.get(sha) if path == self.pointer.path else None

    def is_merged(self, repo, sha):
        return True

    def main_sha(self, repo):
        return MAIN_SHA


@pytest.mark.parametrize("main_asserted", ["0", False])
def test_real_zero_qbid_amount_rejects_false(main_asserted) -> None:
    # F3: false must never stand in for this numeric zero, even if main agrees.
    record = _real_record("us-qbid-grid")
    assert record.entry["kind"] == "amount_difference"
    assert record.axiom_values["qbid-above-nowages"] == (0.0,)
    problems = CompanionResolver(AssertionSource(record, False, main_asserted)).resolve(record)
    assert any("cannot compare" in problem for problem in problems), problems


@pytest.mark.parametrize("asserted", [0, "0", ["0"]])
def test_real_zero_qbid_amount_keeps_numeric_assertions(asserted) -> None:
    record = _real_record("us-qbid-grid")
    assert CompanionResolver(AssertionSource(record, asserted, "0")).resolve(record) == []


def test_amount_main_comparison_rejects_false_for_zero() -> None:
    record = _real_record("us-qbid-grid")
    problems = CompanionResolver(AssertionSource(record, "0", False)).resolve(record)
    assert any("no longer asserts" in problem for problem in problems), problems


def _supplementary_problems(pinned, main):
    record = _real_record("us-qbid-grid")
    additional = "us:policies/income_tax/qualified_business_income_deduction_pipeline#other"
    record.entry["axiom_companion"]["legal_ids"].append(additional)
    source = AssertionSource(record, "0", "0")
    for sha, value in ((source.pointer.sha, pinned), (MAIN_SHA, main)):
        document = yaml.safe_load(source.files[sha])
        document[0]["output"][additional] = value
        source.files[sha] = yaml.safe_dump(document)
    return CompanionResolver(source).resolve(record)


@pytest.mark.parametrize("pinned,main", [([False, False], [0, 0]), ({"flag": False}, {"flag": 0})])
def test_supplementary_main_assertions_preserve_nested_types(pinned, main) -> None:
    problems = _supplementary_problems(pinned, main)
    assert any("no longer asserts" in problem for problem in problems), problems


@pytest.mark.parametrize("asserted", [[False, False], {"flag": False}])
def test_unchanged_structured_supplementary_assertions_still_pass(asserted) -> None:
    assert _supplementary_problems(asserted, asserted) == []


@PROPERTY_SETTINGS
@given(judgments=st.lists(st.booleans(), min_size=2, max_size=8), as_mapping=st.booleans())
def test_nested_judgments_do_not_alias_numbers(judgments, as_mapping) -> None:
    amounts = [int(value) for value in judgments]
    if as_mapping:
        judgments, amounts = {"flags": judgments}, {"flags": amounts}
    assert _supplementary_problems(judgments, amounts)


@PROPERTY_SETTINGS
@given(number=st.sampled_from((0.0, 1.0)), judgment_as_text=st.booleans())
def test_amount_assertions_do_not_normalize_judgments(number, judgment_as_text) -> None:
    record = _real_record("us-qbid-grid")
    case = next(iter(record.axiom_values))
    record.axiom_values = {case: (number,)}
    judgment = ("holds" if number else "not_holds") if judgment_as_text else bool(number)
    problems = CompanionResolver(AssertionSource(record, judgment, str(number))).resolve(record)
    assert any("cannot compare" in problem for problem in problems), problems


@pytest.mark.parametrize("kind", ["eligibility_left_only", "eligibility_right_only"])
@pytest.mark.parametrize("value, asserted", [(False, "not_holds"), (True, 1), (0, False), (1, "holds")])
def test_explicit_eligibility_keeps_judgment_normalization(kind, value, asserted) -> None:
    record = _real_record("us-qbid-grid")
    record.entry["kind"] = kind
    case = next(iter(record.axiom_values))
    record.axiom_values = {case: (value,)}
    assert CompanionResolver(AssertionSource(record, asserted, value)).resolve(record) == []


@pytest.mark.parametrize("actual", [(None,), (), (10000.0, None), (10000.0, 9999.0)])
@pytest.mark.parametrize("asserted", ["garbage", "10000"])
def test_known_salt_case_rejects_unreadable_or_conflicting_values(actual, asserted) -> None:
    # F4: membership in the case mapping, rather than readable-value count,
    # distinguishes a known disputed case from an unrelated companion case.
    record = _real_record("us-salt-deduction-grid")
    record.axiom_values = {"salt-low-agi-engine-cap": actual}
    problems = CompanionResolver(AssertionSource(record, asserted, asserted)).resolve(record)
    assert any("disputed Axiom values" in problem for problem in problems), problems


@PROPERTY_SETTINGS
@given(
    values=st.lists(st.sampled_from((None, "garbage", float("inf"))), min_size=1, max_size=5),
    asserted=st.one_of(st.floats(allow_nan=False, allow_infinity=False), st.none()),
)
def test_mapped_unreadable_values_always_fail(values, asserted) -> None:
    record = _real_record("us-salt-deduction-grid")
    record.axiom_values = {"salt-low-agi-engine-cap": tuple(values)}
    assert CompanionResolver(AssertionSource(record, asserted, asserted)).resolve(record)


@PROPERTY_SETTINGS
@given(other=st.floats(min_value=100, max_value=9000, allow_nan=False, allow_infinity=False))
def test_mapped_conflicting_amounts_always_fail(other) -> None:
    record = _real_record("us-salt-deduction-grid")
    record.axiom_values = {"salt-low-agi-engine-cap": (10000.0, other)}
    assert CompanionResolver(AssertionSource(record, "10000", "10000")).resolve(record)


def test_unmapped_companion_case_keeps_its_own_value() -> None:
    record = _real_record("us-salt-deduction-grid")
    record.axiom_values = {"a-different-disputed-case": (10000.0,)}
    assert CompanionResolver(AssertionSource(record, "5000", "5000")).resolve(record) == []


@pytest.mark.parametrize("asserted", [False, "not_holds", None, "garbage"])
def test_unmapped_amount_case_requires_numeric_assertion_even_at_main(asserted) -> None:
    record = _real_record("us-qbid-grid")
    record.axiom_values = {"a-different-disputed-case": (0.0,)}
    source = AssertionSource(record, asserted, asserted)
    source.main_sha = lambda repo: source.pointer.sha
    problems = CompanionResolver(source).resolve(record)
    assert any("numeric amount assertion" in problem for problem in problems), problems


def test_real_high_itemized_amount_uses_absolute_tolerance() -> None:
    # F5: relative error must not widen the documented absolute 0.005 bound.
    record = _real_record("us-itemized-taxable-income-deductions-grid", 1)
    actual = record.axiom_values["itemized-68-rational-rate"][0]
    assert actual == 9459459.45945946
    asserted = actual + 0.009
    problems = CompanionResolver(AssertionSource(record, asserted, asserted)).resolve(record)
    assert any("disputed Axiom value is" in problem for problem in problems), problems


@PROPERTY_SETTINGS
@given(
    actual=st.floats(min_value=10_000_000, max_value=1_000_000_000),
    delta=st.floats(min_value=0.006, max_value=0.009),
)
def test_large_amounts_cannot_expand_absolute_tolerance(actual, delta) -> None:
    record = _real_record("us-itemized-taxable-income-deductions-grid", 1)
    record.axiom_values = {"itemized-68-rational-rate": (actual,)}
    asserted = actual + delta
    assert abs(asserted - actual) > 0.005
    assert CompanionResolver(AssertionSource(record, asserted, asserted)).resolve(record)
