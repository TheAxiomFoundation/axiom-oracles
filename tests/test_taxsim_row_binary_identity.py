"""Successful TAXSIM rows bind only the binaries that actually produced them."""

import copy

import pytest

from axiom_oracles.adapters.taxsim.pins import resolve_binary
from axiom_oracles.comparison.comparator import Comparator
from axiom_oracles.comparison.dispositions import (
    oracle_binding_mismatch,
    report_oracle_identity,
    row_binary_sha256,
    selection_binding,
)
from axiom_oracles.comparison.mappings import ProgramMapping
from axiom_oracles.comparison.report import build_comparison_report
from axiom_oracles.core.case import Case
from axiom_oracles.core.results import EngineResult
from scripts.bind_dispositions import computed_bindings

CONCEPT = "us:tax/state-income-tax#liability"
DEFAULT = resolve_binary(1, 2024, "linux", "dashboard-2026-09")
FALLBACK = resolve_binary(21, 2024, "linux", "dashboard-2026-09")


def _report(*, taxsim_left=False):
    cases = [
        Case(case_id=state, period="2024", metadata={"selector_facts": {"state": state}})
        for state in ("AL", "MD", "GA")
    ]
    pe = [
        EngineResult("policyengine", case.case_id, {"state_income_tax": 100},
                     raw={"taxsim_binary_sha256": "c" * 64})
        for case in cases
    ]
    taxsim = [
        EngineResult("taxsim", case.case_id, {"siitax": 200},
                     raw={"taxsim_binary_sha256": DEFAULT if case.case_id == "AL" else FALLBACK})
        for case in cases
    ]
    mapping = ProgramMapping(
        standard=CONCEPT, description="State income tax", category="tax", comparison="amount", tolerance=15,
        targets={"policyengine": "state_income_tax", "taxsim": "siitax"},
    )
    comparisons = Comparator([mapping]).compare(
        taxsim if taxsim_left else pe, pe if taxsim_left else taxsim,
    )
    report = build_comparison_report(
        suite_name="binary-test", population="taxsim-csv", locales=set(), scope=None,
        cases=cases, mappings=[mapping], comparisons=comparisons,
    )
    report["engine_identity"] = {"taxsim": {"binaries": [
        {"sha256": DEFAULT}, {"sha256": FALLBACK},
    ]}}
    return report


@pytest.mark.parametrize("taxsim_left", [False, True])
def test_successful_rows_retain_only_canonical_taxsim_engine_sha(taxsim_left):
    report = _report(taxsim_left=taxsim_left)
    assert {row["case_id"]: row_binary_sha256(row) for row in report["mismatches"]} == {
        "AL": DEFAULT, "MD": FALLBACK, "GA": FALLBACK,
    }
    assert all(row["kind"] == "amount_difference" for row in report["mismatches"])


@pytest.mark.parametrize(("states", "expected"), [
    (["MD"], [FALLBACK]),
    (["MD", "GA"], [FALLBACK]),
    (["AL"], [DEFAULT]),
    (["AL", "MD"], sorted([DEFAULT, FALLBACK])),
])
def test_binding_helper_selects_exact_successful_row_binaries(states, expected):
    report = _report()
    entry = {"id": "selected", "concept": CONCEPT,
             "match": {"facts": {"state": states}}}
    bindings, notes = computed_bindings(
        [entry], report, lane=True, oracle_binding=True, legacy_version=None,
    )
    assert not notes
    binding = bindings["selected"]["oracle_binding"]
    assert binding == {"taxsim_binary_sha256": expected}
    rows = [row for row in report["mismatches"] if row["case_id"] in states]
    identity = report_oracle_identity(report)
    assert oracle_binding_mismatch(binding, identity, rows) is None
    # Swapping the binary identity expires even an unchanged value population.
    moved = copy.deepcopy(rows)
    moved[0]["taxsim_binary_sha256"] = "f" * 64
    assert oracle_binding_mismatch(binding, identity, moved) == "oracle_identity_malformed"


def test_old_value_population_bindings_keep_their_digest_and_full_binary_set():
    report = _report()
    row = report["mismatches"][1]
    legacy = {key: value for key, value in row.items() if key != "taxsim_binary_sha256"}
    assert selection_binding([row]) == selection_binding([legacy])
    identity = report_oracle_identity(report)
    assert oracle_binding_mismatch({"taxsim_binary_sha256": [FALLBACK]}, identity, [row]) is None
    assert oracle_binding_mismatch(
        {"taxsim_binary_sha256": [FALLBACK]}, identity, [legacy],
    ) == "oracle_identity_changed"
    assert oracle_binding_mismatch(
        {"taxsim_binary_sha256": [DEFAULT, FALLBACK]}, identity, [legacy],
    ) is None


@pytest.mark.parametrize("bad_sha", [None, "", "not-a-digest", 42])
def test_malformed_explicit_row_digest_fails_closed(bad_sha):
    report = _report()
    row = {**report["mismatches"][0], "taxsim_binary_sha256": bad_sha}
    assert oracle_binding_mismatch(
        {"taxsim_binary_sha256": [DEFAULT, FALLBACK]}, report_oracle_identity(report), [row],
    ) == "oracle_identity_malformed"


@pytest.mark.parametrize("other_side", [False, True])
@pytest.mark.parametrize("conflicting", [False, True])
def test_row_digest_must_agree_with_canonical_taxsim_error(other_side, conflicting):
    report = _report()
    row = report["mismatches"][0]
    error = {"engine": "taxsim", "binary_sha256": FALLBACK if conflicting else DEFAULT}
    row["error"] = (
        {"engine": "policyengine", "binary_sha256": "c" * 64, "other_side": error}
        if other_side else error
    )
    binding = {"taxsim_binary_sha256": [DEFAULT]}
    identity = report_oracle_identity(report)
    entry = {"id": "selected", "concept": CONCEPT, "match": {"facts": {"state": ["AL"]}}}
    if conflicting:
        with pytest.raises(ValueError, match="conflicting per-row TAXSIM binary digests"):
            row_binary_sha256(row)
        assert oracle_binding_mismatch(binding, identity, [row]) == "oracle_identity_malformed"
        with pytest.raises(SystemExit, match="per-row TAXSIM identity is malformed"):
            computed_bindings([entry], report, lane=True, oracle_binding=True, legacy_version=None)
    else:
        assert row_binary_sha256(row) == DEFAULT
        assert oracle_binding_mismatch(binding, identity, [row]) is None
        bindings, notes = computed_bindings(
            [entry], report, lane=True, oracle_binding=True, legacy_version=None,
        )
        assert not notes
        assert bindings["selected"]["oracle_binding"] == binding
