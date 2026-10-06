"""Offline companions for the review's round-one resolver counterexamples.

These preserve the recorded SALT/saver scope, QBID zero, and large itemized
amount witnesses. Each source is local: GitHub/main answers and RuleSpec YAML
are supplied by the test, and disputed values come from annotated report rows.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.comparison import pe_axiom_standard as standard

PIN = "0a8d9dd557c120bc081c0b152e149faf43ccef1a"
MAIN = "2066cef61139ebe381b617b37eb6dabcbae109e7"
PE_ISSUE = "https://github.com/PolicyEngine/policyengine-us/issues/9999"
SALT = "us:policies/income_tax/salt_deduction_pipeline#federal_salt_deduction"
SAVER = "us:policies/income_tax/savers_credit_pipeline#federal_savers_credit"
QBID = (
    "us:policies/income_tax/qualified_business_income_deduction_pipeline"
    "#federal_qualified_business_income_deduction"
)
ITEMIZED = (
    "us:policies/income_tax/itemized_taxable_income_deductions_pipeline"
    "#federal_itemized_taxable_income_deductions"
)
SALT_CASE = "salt-low-agi-engine-cap"
QBID_CASE = "qbid-above-nowages"
ITEMIZED_CASE = "itemized-68-rational-rate"


class RecordedSource:
    """Read-only source with explicit pinned and main contents."""

    def __init__(self, files: dict, main: str | None = MAIN):
        self.files = files
        self.main = main

    def read(self, repo, sha, path):
        value = self.files.get((repo, sha, path))
        if isinstance(value, Exception):
            raise value
        return value

    def is_merged(self, repo, sha):
        return sha == PIN

    def main_sha(self, repo):
        return self.main

    def fetch_json(self, url):
        return 200, {"number": 9999, "html_url": PE_ISSUE, "state": "open"}


def _yaml_case(concept: str, case: str, value) -> str:
    return yaml.safe_dump(
        [{"name": case, "period": 2026, "input": {}, "output": {concept: value}}]
    )


def _record(
    root: Path,
    concept: str = SALT,
    case: str = SALT_CASE,
    values: tuple = (10000.0,),
):
    """Collect an amount record rather than trusting its optional filter."""

    located = standard.legal_id_companion_path(concept)
    assert located is not None
    repo, path = located
    entry = {
        "id": "recorded-gap",
        "concept": concept,
        "case_id": case,
        "kind": "amount_difference",
        "disposition": "upstream_engine_gap",
        "evidence": {"upstream_url": PE_ISSUE},
        "axiom_companion": {
            "legal_ids": [concept],
            "tests": [f"{repo}@{PIN}:{path}#{case}"],
        },
    }
    dispositions = root / "dispositions"
    dispositions.mkdir(parents=True, exist_ok=True)
    (dispositions / "recorded-grid.yaml").write_text(
        yaml.safe_dump({"suite": "recorded-grid", "entries": [entry]})
    )
    data = root / "dashboard" / "public" / "data"
    data.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "case_id": case,
            "concept": concept,
            "kind": "amount_difference",
            "left": value,
            "right": 400,
            "disposition": {"id": entry["id"]},
        }
        for value in values
    ]
    (data / "recorded-report.json").write_text(
        json.dumps(
            {
                "suite": "recorded-grid",
                "engines": {"left": "axiom", "right": "policyengine-us"},
                "summary": {"mismatch_count": len(rows)},
                "mismatches": rows,
            }
        )
    )
    records, errors = standard.collect_records(root)
    assert errors == []
    assert len(records) == 1
    return records[0]


def _source(record, pinned, main=None):
    pointer = standard.CompanionPointer.parse(record.entry["axiom_companion"]["tests"][0])
    assert pointer is not None
    return RecordedSource(
        {
            (pointer.repo, PIN, pointer.path): _yaml_case(
                record.concept, pointer.case, pinned
            ),
            (pointer.repo, MAIN, pointer.path): _yaml_case(
                record.concept, pointer.case, pinned if main is None else main
            ),
        }
    )


def test_older_merged_pin_cannot_hide_a_current_rulespec_output(tmp_path) -> None:
    # The saver test existed at this merged pin before the SALT test did.
    # SALT on canonical main still makes SALT a required declared legal id.
    record = _record(tmp_path)
    saver_path = standard.legal_id_companion_path(SAVER)[1]
    salt_path = standard.legal_id_companion_path(SALT)[1]
    saver_case = "single-at-50-percent-limit-inclusive"
    record.entry["axiom_companion"] = {
        "legal_ids": [SAVER],
        "tests": [f"rulespec-us@{PIN}:{saver_path}#{saver_case}"],
    }
    source = RecordedSource(
        {
            ("rulespec-us", PIN, saver_path): _yaml_case(SAVER, saver_case, 1000),
            ("rulespec-us", MAIN, saver_path): _yaml_case(SAVER, saver_case, 1000),
            ("rulespec-us", MAIN, salt_path): _yaml_case(SALT, SALT_CASE, 10000),
        }
    )
    problems = standard.CompanionResolver(source).resolve(record)
    assert any("declare it among legal_ids" in p for p in problems), problems


@pytest.mark.parametrize("unavailable", ["unknown-main", "transient-module"])
def test_scope_discovery_fails_closed_when_canonical_main_is_unverifiable(
    tmp_path, unavailable
) -> None:
    record = _record(tmp_path)
    saver_path = standard.legal_id_companion_path(SAVER)[1]
    salt_path = standard.legal_id_companion_path(SALT)[1]
    record.entry["axiom_companion"] = {
        "legal_ids": [SAVER],
        "tests": [f"rulespec-us@{PIN}:{saver_path}#saver-case"],
    }
    source = RecordedSource(
        {
            ("rulespec-us", PIN, saver_path): _yaml_case(SAVER, "saver-case", 1000),
            ("rulespec-us", MAIN, saver_path): _yaml_case(SAVER, "saver-case", 1000),
            ("rulespec-us", MAIN, salt_path): standard.SourceUnavailable("503"),
        },
        main=None if unavailable == "unknown-main" else MAIN,
    )
    problems = standard.CompanionResolver(source).resolve(record)
    # A generic inability to re-read the submitted saver is insufficient:
    # the diagnostic must bind canonical-main discovery to the SALT dispute.
    assert any("verify the disputed concept" in p for p in problems), problems


@pytest.mark.parametrize(
    "asserted", [False, [False], "not_holds"], ids=["false", "boxed-false", "not-holds"]
)
def test_amount_zero_cannot_be_backed_by_a_judgment(tmp_path, asserted) -> None:
    record = _record(tmp_path, QBID, QBID_CASE, (0.0,))
    problems = standard.CompanionResolver(_source(record, asserted)).resolve(record)
    assert any("cannot compare" in p for p in problems), problems


@pytest.mark.parametrize(
    "values",
    [(None,), (10000.0, 9999.0), (0.0, False), ("Infinity",)],
    ids=["unreadable", "conflicting-numbers", "conflicting-types", "nonfinite"],
)
def test_disputed_values_must_be_readable_and_consistent(tmp_path, values) -> None:
    record = _record(tmp_path, values=values)
    problems = standard.CompanionResolver(_source(record, "garbage")).resolve(record)
    assert any("unreadable or conflicting" in p for p in problems), problems


def test_large_itemized_amount_cannot_use_relative_tolerance(tmp_path) -> None:
    # Recorded itemized-68-rational-rate Axiom amount, perturbed by $0.009.
    actual = 9459459.45945946
    record = _record(tmp_path, ITEMIZED, ITEMIZED_CASE, (actual,))
    problems = standard.CompanionResolver(_source(record, actual + 0.009)).resolve(record)
    assert any("disputed Axiom value is" in p for p in problems), problems


def test_main_assertion_cannot_use_relative_tolerance(tmp_path) -> None:
    actual = 9459459.45945946
    record = _record(tmp_path, ITEMIZED, ITEMIZED_CASE, (actual,))
    problems = standard.CompanionResolver(
        _source(record, actual, main=actual + 0.009)
    ).resolve(record)
    assert any("no longer asserts" in p for p in problems), problems


@pytest.mark.parametrize("replacement", [False, [False]], ids=["false", "boxed-false"])
def test_main_cannot_replace_a_numeric_zero_with_a_judgment(tmp_path, replacement) -> None:
    record = _record(tmp_path, QBID, QBID_CASE, (0.0,))
    problems = standard.CompanionResolver(
        _source(record, 0.0, main=replacement)
    ).resolve(record)
    assert any("no longer asserts" in p for p in problems), problems


@settings(max_examples=100, deadline=None, derandomize=True)
@given(
    actual=st.integers(min_value=10_000_000, max_value=100_000_000),
    mills=st.integers(min_value=6, max_value=9),
)
def test_amount_tolerance_is_absolute_for_every_magnitude(actual, mills) -> None:
    # The same monetary error is unacceptable at every amount magnitude.
    assert not standard._same(("number", float(actual)), ("number", actual + mills / 1000))
