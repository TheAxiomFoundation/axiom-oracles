"""Offline ports of review 20261004-124541's known-cause/kind witnesses.

Fixtures retain the committed Colorado 1032-vs-967 and QBID 0-vs-400 rows;
the companion assertions are the review's deliberately incorrect witnesses.
"""

import copy
import json
from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings, strategies as st

from axiom_oracles.comparison.dispositions import apply_dispositions
from axiom_oracles.comparison.pe_axiom_standard import (
    CompanionResolver,
    collect_records,
)

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40


class RecordedSource:
    def __init__(self, record, assertion):
        self.text = yaml.safe_dump(
            [
                {
                    "name": record.case_ids[0]
                    if record.case_ids
                    else record.entry.get(
                        "case_id",
                        "co-state-supplement-oap_total_monthly_grant_standard",
                    ),
                    "output": {record.concept: assertion},
                }
            ]
        )

    def read(self, *args):
        return self.text

    def is_merged(self, *args):
        return True

    def main_sha(self, *args):
        return SHA

    def fetch_json(self, url):
        number = int(url.rsplit("/", 1)[1])
        return 200, {
            "number": number,
            "html_url": url.replace("api.github.com/repos", "github.com"),
            "state": "closed",
        }


def _write(root, report, *, entry=None, causes=None):
    data = root / "dashboard/public/data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "report.json").write_text(json.dumps(report))
    if causes is not None:
        (data / "known_causes.json").write_text(json.dumps({"entries": causes}))
    if entry is not None:
        dispositions = root / "dispositions"
        dispositions.mkdir(exist_ok=True)
        (dispositions / "example.yaml").write_text(
            yaml.safe_dump({"suite": report["suite"], "entries": [entry]})
        )
    return collect_records(root)


def _companion(concept, case, path):
    return {"legal_ids": [concept], "tests": [f"rulespec-us@{SHA}:{path}#{case}"]}


def test_known_cause_same_name_wrong_value_fails(tmp_path):
    report = json.loads(
        (
            ROOT / "dashboard/public/data/axiom-policyengine-co-state-supplement.json"
        ).read_text()
    )
    cause = next(
        c
        for c in json.loads(
            (ROOT / "dashboard/public/data/known_causes.json").read_text()
        )["entries"]
        if c["suite"] == "co-state-supplement"
    )
    row = report["mismatches"][0]
    cause["axiom_companion"] = _companion(
        row["concept"], row["case_id"], "us-co/regulations/9-ccr-2503-5/3.530.test.yaml"
    )
    records, errors = _write(tmp_path, report, causes=[cause])
    assert errors == [] and len(records) == 1
    record = records[0]
    problems = CompanionResolver(RecordedSource(record, 999)).resolve(record)
    assert any("disputed Axiom value is 1032.0" in p for p in problems), problems
    assert record.case_ids == (row["case_id"],)
    assert record.axiom_values == {row["case_id"]: (1032.0,)}


def _qbid():
    entry = yaml.safe_load((ROOT / "dispositions/us-qbid-grid.yaml").read_text())[
        "entries"
    ][0]
    report = json.loads(
        (
            ROOT / "dashboard/public/data/axiom-policyengine-us-qbid-grid.json"
        ).read_text()
    )
    row = next(
        r
        for r in report["mismatches"]
        if r["case_id"] == entry["case_id"] and r["concept"] == entry["concept"]
    )
    report["mismatches"] = [row]
    entry["axiom_companion"] = _companion(
        entry["concept"],
        entry["case_id"],
        "us/policies/income_tax/qualified_business_income_deduction_pipeline.test.yaml",
    )
    return entry, report


def test_editable_kind_cannot_make_false_back_qbid_amount(tmp_path):
    entry, report = _qbid()
    entry["kind"] = "eligibility_right_only"
    records, errors = _write(tmp_path, report, entry=entry)
    assert errors == [] and len(records) == 1
    record = records[0]
    assert record.axiom_values == {"qbid-above-nowages": (0.0,)}
    assert CompanionResolver(RecordedSource(record, False)).resolve(record)


def test_reapplying_a_changed_kind_clears_stale_annotation():
    entry, report = _qbid()
    entry["kind"] = "eligibility_right_only"
    document = {"suite": report["suite"], "entries": [entry]}
    reapplied = apply_dispositions(report, document)
    assert "disposition" not in reapplied["mismatches"][0]
    assert sum(reapplied["summary"]["dispositioned"]["counts"].values()) == 0


@pytest.mark.parametrize("filtered", [False, True])
def test_eligibility_judgment_resolves_without_optional_kind(tmp_path, filtered):
    entry, report = _qbid()
    entry.pop("pinned")
    row = report["mismatches"][0]
    row.update(kind="eligibility_right_only", left=False, right=True)
    if filtered:
        entry["kind"] = row["kind"]
    else:
        entry.pop("kind")
    report = apply_dispositions(report, {"suite": report["suite"], "entries": [entry]})
    records, errors = _write(tmp_path, report, entry=entry)
    assert errors == [] and len(records) == 1
    record = records[0]
    assert CompanionResolver(RecordedSource(record, "not_holds")).resolve(record) == []


def test_conflicting_actual_row_types_fail_closed(tmp_path):
    entry, report = _qbid()
    entry.pop("kind")
    entry.pop("pinned")
    case = entry.pop("case_id")
    entry["case_selector"] = {"case_ids": [case, "other-case"]}
    other = copy.deepcopy(report["mismatches"][0])
    other.update(
        case_id="other-case", kind="eligibility_right_only", left=False, right=True
    )
    report["mismatches"].append(other)
    report = apply_dispositions(report, {"suite": report["suite"], "entries": [entry]})
    records, errors = _write(tmp_path, report, entry=entry)
    assert errors == []
    record = records[0]
    assert any(
        "conflicting" in p
        for p in CompanionResolver(RecordedSource(record, 0)).resolve(record)
    )


def test_empty_known_cause_engine_mapping_is_rejected(tmp_path):
    entry, report = _qbid()
    cause = {
        "suite": report["suite"],
        "concept": entry["concept"],
        "kind": "amount_difference",
        "fix_owner": "policyengine",
        "engines": {},
    }
    generic = dict(cause, fix_owner="axiom")
    generic.pop("engines")
    _, errors = _write(tmp_path, report, causes=[cause, generic])
    assert any("engines" in e and "empty" in e for e in errors), errors


@pytest.mark.parametrize("kind", ["eligibility_left_only", "eligibility_right_only"])
def test_sampled_known_cause_cannot_authorize_judgment_from_filter(tmp_path, kind):
    # Summary-only liveness cannot make editable cause metadata an actual
    # mismatch type. With no selected row, the companion stays numeric.
    concept = "us:policies/example#amount"
    case = "sampled-dispute"
    report = {
        "suite": "example",
        "engines": {"left": "axiom", "right": "policyengine-us"},
        "summary": {
            "mismatch_count": 2,
            "mismatches_by_concept": [{"concept": concept, "count": 2}],
        },
        "mismatches": [],
    }
    cause = {
        "suite": "example",
        "concept": concept,
        "kind": kind,
        "fix_owner": "policyengine",
        "issue_url": "https://github.com/PolicyEngine/policyengine-us/issues/8832",
        "axiom_companion": _companion(
            concept, case, "us/policies/example.test.yaml"
        ),
    }
    records, errors = _write(tmp_path, report, causes=[cause])
    assert errors == [] and len(records) == 1
    record = records[0]
    source = RecordedSource(record, False)
    source.text = yaml.safe_dump([{"name": case, "output": {concept: False}}])
    problems = CompanionResolver(source).resolve(record)
    assert any("numeric amount assertion" in p for p in problems), problems
    assert record.row_kinds == ()


@settings(max_examples=30, derandomize=True, deadline=None)
@given(
    kind=st.sampled_from(
        [None, "amount_difference", "eligibility_left_only", "eligibility_right_only"]
    )
)
def test_amount_type_does_not_depend_on_optional_filter(kind, tmp_path_factory):
    entry, report = _qbid()
    if kind is None:
        entry.pop("kind")
    else:
        entry["kind"] = kind
    records, errors = _write(tmp_path_factory.mktemp("amount"), report, entry=entry)
    assert errors == []
    record = records[0]
    assert CompanionResolver(RecordedSource(record, False)).resolve(record)


@settings(max_examples=30, derandomize=True, deadline=None)
@given(
    value=st.integers(min_value=0, max_value=10**8),
    offset=st.integers(min_value=1, max_value=100),
)
def test_known_cause_collects_only_its_selected_bucket(value, offset, tmp_path_factory):
    concept = "us:policies/example#amount"
    row = {
        "case_id": "disputed",
        "concept": concept,
        "kind": "amount_difference",
        "left": value,
        "right": value + 1,
    }
    report = {
        "suite": "example",
        "engines": {"left": "axiom", "right": "policyengine"},
        "summary": {"mismatch_count": 1},
        "mismatches": [row],
    }
    cause = {
        "suite": "example",
        "concept": concept,
        "kind": "amount_difference",
        "fix_owner": "policyengine",
        "issue_url": "https://github.com/PolicyEngine/policyengine-us/issues/8832",
        "axiom_companion": _companion(
            concept, "disputed", "us/policies/example.test.yaml"
        ),
    }
    # The same concept/kind in a different engine bucket selects another
    # cause, so its values must never pollute this PolicyEngine record.
    other_cause = dict(
        cause,
        fix_owner="axiom",
        issue_url=None,
        engines={"left": "axiom", "right": "taxsim"},
    )
    root = tmp_path_factory.mktemp("cause")
    records, errors = _write(root, report, causes=[cause, other_cause])
    other_report = copy.deepcopy(report)
    other_report["engines"]["right"] = "taxsim"
    other_report["mismatches"][0]["left"] = value + offset
    (root / "dashboard/public/data/other.json").write_text(json.dumps(other_report))
    records, errors = collect_records(root)
    assert errors == [] and len(records) == 1
    record = records[0]
    assert record.case_ids == ("disputed",)
    assert record.axiom_values == {"disputed": (value,)}
    assert CompanionResolver(RecordedSource(record, value)).resolve(record) == []
    assert CompanionResolver(RecordedSource(record, value + offset)).resolve(record)


@settings(max_examples=20, derandomize=True, deadline=None)
@given(
    pe_first=st.booleans(),
    counterpart=st.sampled_from(["policyengine", "policyengine-us", "taxsim"]),
)
def test_empty_engine_mapping_is_always_invalid(
    pe_first, counterpart, tmp_path_factory
):
    concept = "us:policies/example#amount"
    report = {
        "suite": "example",
        "engines": {"left": "axiom", "right": counterpart},
        "summary": {"mismatch_count": 1},
        "mismatches": [
            {
                "case_id": "case",
                "concept": concept,
                "kind": "amount_difference",
                "left": 1,
                "right": 2,
            }
        ],
    }
    empty = {
        "suite": "example",
        "concept": concept,
        "kind": "amount_difference",
        "fix_owner": "policyengine",
        "engines": {},
    }
    generic = dict(empty, fix_owner="axiom")
    generic.pop("engines")
    causes = [empty, generic] if pe_first else [generic, empty]
    _, errors = _write(tmp_path_factory.mktemp("empty"), report, causes=causes)
    assert any("engines mapping must not be empty" in e for e in errors)
