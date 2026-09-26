"""Hardened dispositions: attribution, oracle identity, structured selectors,
population bindings, row arithmetic, engine-error rows, facts plumbing, and
the TAXSIM-lane migration's row-assignment invariance."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

from axiom_oracles.comparison.comparator import Comparator
from axiom_oracles.comparison.dispositions import (
    DISPOSITIONS_SCHEMA_VERSION,
    DispositionConservationError,
    SuiteContext,
    adapter_engine_names,
    apply_dispositions,
    assignment_digest,
    load_dispositions,
    oracle_binding_mismatch,
    row_binary_sha256,
    report_is_taxsim_lane,
    report_oracle_identity,
    select_rows,
    selected_rows_sha256,
    selection_binding,
    suite_context,
    validate_dispositions,
)
from axiom_oracles.comparison.mappings import ProgramMapping
from axiom_oracles.comparison.report import (
    MismatchKind,
    build_comparison_report,
    engine_error_signature,
)
from axiom_oracles.comparison.selectors import (
    ArithmeticEvaluationError,
    evaluate_expression,
    expression_variables,
    match_row,
    mismatch_signature,
    row_variables,
    signature_population,
    signature_population_sha256,
    validate_match,
)
from axiom_oracles.core.case import Case
from axiom_oracles.core.results import EngineResult

REPO_ROOT = Path(__file__).resolve().parent.parent
TAXSIM = ("axiom", "taxsim")
SHA_A = "a" * 64
SHA_B = "b" * 64
CONCEPT = "us:test#income_tax"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _row(case_id, left, right, *, concept=CONCEPT, kind="amount_difference", **extra):
    row = {
        "case_id": case_id,
        "concept": concept,
        "kind": kind,
        "left": left,
        "right": right,
        "difference": (
            left - right
            if isinstance(left, int | float) and isinstance(right, int | float)
            else None
        ),
    }
    row.update(extra)
    return row


def _report(rows, *, engines=TAXSIM, oracle=None, engine_identity=None) -> dict:
    report = {
        "schema_version": "axiom.comparison_report.v2",
        "suite": "example-suite",
        "engines": {"left": engines[0], "right": engines[1]},
        "summary": {
            "comparison_count": len(rows) + 1,
            "match_count": 1,
            "mismatch_count": len(rows),
        },
        "mismatches": rows,
    }
    if oracle is not None:
        report["provenance"] = {"oracle": oracle}
    if engine_identity is not None:
        report["engine_identity"] = engine_identity
    return report


def _entry(**overrides) -> dict:
    entry = {
        "id": "example",
        "concept": CONCEPT,
        "case_selector": {"case_id_prefix": "case-"},
        "disposition": "upstream_engine_gap",
        "attribution": "taxsim",
        "evidence": {
            "mechanism": "TAXSIM returns zero for this class.",
            "row_arithmetic": [{"expression": "right", "equals": 0}],
        },
        "expires_on_source_change": True,
        "oracle_binding": {"identity_unrecorded": True},
    }
    entry.update(overrides)
    return entry


def _doc(entries, suite="example-suite") -> dict:
    return {"schema": DISPOSITIONS_SCHEMA_VERSION, "suite": suite, "entries": entries}


def _bound(entry: dict, rows: list[dict]) -> dict:
    """Stamp the entry's selector_binding from the rows it should select."""

    entry = copy.deepcopy(entry)
    entry["selector_binding"] = selection_binding(rows)
    return entry


def _block(merged: dict) -> dict:
    return merged["summary"]["dispositioned"]


def _load_script(name: str):
    path = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Suite context and attribution
# ---------------------------------------------------------------------------


def test_suite_context_reads_sides_from_comparison_config(tmp_path: Path) -> None:
    comparisons = tmp_path / "comparisons"
    comparisons.mkdir()
    (comparisons / "pe-taxsim.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "pe-taxsim",
                "runner": {"parameters": {"left": "policyengine", "right": "taxsim"}},
                "dashboard": {"suite": "pe-taxsim-dash"},
            }
        )
    )
    for suite in ("pe-taxsim", "pe-taxsim-dash"):
        context = suite_context(suite, tmp_path)
        assert context.engines == frozenset({"policyengine", "taxsim"})
        assert context.taxsim_lane
        assert context.external_only
        assert context.attribution_values() == frozenset(
            {"policyengine", "taxsim", "convention", "input", "two_sided"}
        )
    unknown = suite_context("other", tmp_path)
    assert unknown.engines is None and not unknown.taxsim_lane


def test_repo_taxsim_suites_resolve_as_taxsim_lanes() -> None:
    for suite in (
        "fiit-taxsim-ecps",
        "co-tax-intersection-taxsim",
        "co-state-income-tax-taxsim",
    ):
        context = suite_context(suite, REPO_ROOT)
        assert context.engines == frozenset(TAXSIM), suite
        assert context.taxsim_lane


def test_quoted_comparison_keys_enforce_taxsim_lane_rules(tmp_path: Path) -> None:
    module = _load_script("apply_dispositions")
    comparisons = tmp_path / "comparisons"
    comparisons.mkdir()
    # JSON-form YAML has no literal 'left:' or 'right:' substring.
    (comparisons / "example-suite.yaml").write_text(json.dumps({
        "runner": {"parameters": {"left": "policyengine", "right": "taxsim"}}
    }))
    context = suite_context("example-suite", tmp_path)
    assert context.taxsim_lane
    rows = [_row("case-1", 10, 0)]
    missing = _bound(_entry(), rows)
    del missing["attribution"], missing["oracle_binding"]
    errors = validate_dispositions(_doc([missing]), repo_root=tmp_path)
    assert any("needs `attribution` (TAXSIM lane)" in error for error in errors)
    assert any("needs `oracle_binding` (TAXSIM lane)" in error for error in errors)

    module.REPO_ROOT = tmp_path
    module.DASHBOARD_DATA_DIR = tmp_path / "dashboard"
    module.DASHBOARD_DATA_DIR.mkdir()
    report = _report(rows)
    del report["engines"]
    (module.DASHBOARD_DATA_DIR / "example-suite.json").write_text(json.dumps(report))
    entries = [_bound(_entry(id="a"), rows), _bound(_entry(id="b"), rows)]
    problems, _, _ = module._merge_reports({"example-suite": _doc(entries)}, check=True)
    assert any("classification conservation failure" in problem for problem in problems)


def test_fallback_attribution_vocabulary_is_the_adapter_names() -> None:
    names = adapter_engine_names()
    assert {"axiom", "policyengine", "taxsim", "euromod"} <= names
    assert SuiteContext("x").attribution_values() == names | {
        "convention", "input", "two_sided"
    }


def test_unknown_attribution_is_invalid_everywhere() -> None:
    entry = _entry(attribution="nber")
    errors = validate_dispositions(_doc([entry]), suite_engines=("axiom", "policyengine"))
    assert any("attribution must be one of" in error for error in errors)
    errors = validate_dispositions(_doc([entry]))  # sides unknown
    assert any("attribution must be one of" in error for error in errors)
    # An engine that is not on this suite's sides is not a valid attribution.
    errors = validate_dispositions(
        _doc([_entry(attribution="taxsim")]), suite_engines=("axiom", "policyengine")
    )
    assert any("attribution must be one of" in error for error in errors)


def test_attribution_required_in_taxsim_lane() -> None:
    entry = _entry()
    del entry["attribution"]
    errors = validate_dispositions(_doc([_bound(entry, [])]), suite_engines=TAXSIM)
    assert any("needs `attribution` (TAXSIM lane)" in error for error in errors)


def test_attribution_required_on_upstream_gap_without_axiom_side() -> None:
    entry = {
        "id": "gap",
        "concept": CONCEPT,
        "case_id": "case-1",
        "disposition": "upstream_engine_gap",
        "evidence": {"mechanism": "m", "upstream_url": "https://example.org/1"},
        "expires_on_source_change": True,
    }
    errors = validate_dispositions(_doc([entry]), suite_engines=("euromod", "gettsim"))
    assert any("both sides of this suite are external" in error for error in errors)
    assert validate_dispositions(
        _doc([{**entry, "attribution": "gettsim"}]), suite_engines=("euromod", "gettsim")
    ) == []
    # Not required when an Axiom side exists, nor for other kinds.
    assert validate_dispositions(_doc([entry]), suite_engines=("axiom", "euromod")) == []
    assert validate_dispositions(
        _doc([{**entry, "disposition": "explained_residual"}]),
        suite_engines=("euromod", "gettsim"),
    ) == []


# ---------------------------------------------------------------------------
# TAXSIM-lane validation requirements
# ---------------------------------------------------------------------------


def _valid_taxsim_entry() -> dict:
    return _bound(_entry(), [_row("case-1", 10, 0)])


def test_valid_taxsim_lane_entry_passes() -> None:
    assert validate_dispositions(_doc([_valid_taxsim_entry()]), suite_engines=TAXSIM) == []


def test_taxsim_lane_requires_oracle_binding() -> None:
    entry = _valid_taxsim_entry()
    del entry["oracle_binding"]
    errors = validate_dispositions(_doc([entry]), suite_engines=TAXSIM)
    assert any("needs `oracle_binding`" in error for error in errors)


def test_taxsim_lane_requires_population_binding_on_multi_row_selectors() -> None:
    entry = _valid_taxsim_entry()
    del entry["selector_binding"]
    errors = validate_dispositions(_doc([entry]), suite_engines=TAXSIM)
    assert any("needs `selector_binding`" in error for error in errors)
    match_entry = _entry(match={"delta": {"sign": "pos"}})
    del match_entry["case_selector"]
    errors = validate_dispositions(_doc([match_entry]), suite_engines=TAXSIM)
    assert any("needs `selector_binding`" in error for error in errors)


def test_taxsim_lane_single_row_entries_need_pinned_left_and_right() -> None:
    entry = _entry(case_id="case-1")
    del entry["case_selector"]
    errors = validate_dispositions(_doc([entry]), suite_engines=TAXSIM)
    assert any("needs `pinned` left and right" in error for error in errors)
    entry["pinned"] = {"left": 10}
    errors = validate_dispositions(_doc([entry]), suite_engines=TAXSIM)
    assert any("needs `pinned` left and right" in error for error in errors)
    entry["pinned"] = {"left": 10, "right": 0}
    assert validate_dispositions(_doc([entry]), suite_engines=TAXSIM) == []


def test_constant_arithmetic_alone_no_longer_reconciles_in_taxsim_lane() -> None:
    entry = _valid_taxsim_entry()
    entry["evidence"] = {
        "mechanism": "m",
        "arithmetic": [{"expression": "0 * 1", "equals": 0}],
    }
    errors = validate_dispositions(_doc([entry]), suite_engines=TAXSIM)
    assert any("constant-only evidence.arithmetic" in error for error in errors)
    # A citation satisfies the rule...
    cited = copy.deepcopy(entry)
    cited["linked_issue"] = "https://example.org/issue/1"
    assert validate_dispositions(_doc([cited]), suite_engines=TAXSIM) == []
    # ...and constant arithmetic stays valid outside TAXSIM lanes.
    plain = copy.deepcopy(entry)
    plain["attribution"] = "policyengine"
    assert validate_dispositions(
        _doc([plain]), suite_engines=("axiom", "policyengine")
    ) == []


def test_repo_taxsim_dispositions_validate_under_lane_rules() -> None:
    for suite in (
        "fiit-taxsim-ecps",
        "co-tax-intersection-taxsim",
        "co-state-income-tax-taxsim",
    ):
        document = load_dispositions(
            REPO_ROOT / "dispositions" / f"{suite}.yaml", repo_root=REPO_ROOT
        )
        for entry in document["entries"]:
            assert entry["attribution"] in {
                "taxsim", "axiom", "convention", "input", "two_sided"
            }
            assert entry["oracle_binding"]


# ---------------------------------------------------------------------------
# Oracle identity binding
# ---------------------------------------------------------------------------


def test_report_identity_reads_contract_c1_sources_in_order() -> None:
    binaries = [{"sha256": SHA_A, "scope": "default"}]
    identity = report_oracle_identity(
        _report([], oracle={"taxsim_binaries": binaries, "policyengine_taxsim": "2.31.0"})
    )
    assert identity["source"] == "provenance.oracle.taxsim_binaries"
    assert identity["taxsim_binary_sha256"] == [SHA_A]
    assert identity["policyengine_taxsim"] == "2.31.0"
    cli = report_oracle_identity(
        _report([], engine_identity={"taxsim": {"binaries": [{"sha256": SHA_B}]}})
    )
    assert cli["source"] == "engine_identity.taxsim.binaries"
    assert cli["taxsim_binary_sha256"] == [SHA_B]
    legacy = report_oracle_identity(_report([], oracle={"policyengine_taxsim": "2.30.0"}))
    assert legacy["taxsim_binary_sha256"] is None
    assert legacy["policyengine_taxsim"] == "2.30.0"
    bare = report_oracle_identity(_report([], oracle={"name": "taxsim"}))
    assert bare == {
        "source": None,
        "taxsim_binary_sha256": None,
        "policyengine_taxsim": None,
        "malformed": False,
    }
    assert report_oracle_identity(
        _report([], oracle={"taxsim_binaries": [{"sha256": "short"}]})
    )["malformed"]


@pytest.mark.parametrize(
    ("binding", "oracle", "expected"),
    [
        ({"taxsim_binary_sha256": [SHA_A]}, {"taxsim_binaries": [{"sha256": SHA_A}]}, None),
        (
            {"taxsim_binary_sha256": [SHA_A]},
            {"taxsim_binaries": [{"sha256": SHA_B}]},
            "oracle_identity_changed",
        ),
        # A two-binary report needs both listed when rows do not say which ran.
        (
            {"taxsim_binary_sha256": [SHA_A]},
            {"taxsim_binaries": [{"sha256": SHA_A}, {"sha256": SHA_B}]},
            "oracle_identity_changed",
        ),
        (
            {"taxsim_binary_sha256": [SHA_B, SHA_A]},
            {"taxsim_binaries": [{"sha256": SHA_A}, {"sha256": SHA_B}]},
            None,
        ),
        ({"policyengine_taxsim": "2.30.0"}, {"policyengine_taxsim": "2.30.0"}, None),
        (
            {"policyengine_taxsim": "2.30.0"},
            {"policyengine_taxsim": "2.31.0"},
            "oracle_identity_changed",
        ),
        # A recorded binary set outranks a matching version string.
        (
            {"policyengine_taxsim": "2.30.0"},
            {"policyengine_taxsim": "2.30.0", "taxsim_binaries": [{"sha256": SHA_A}]},
            "oracle_identity_changed",
        ),
        ({"identity_unrecorded": True}, {"name": "taxsim"}, None),
        ({"taxsim_binary_sha256": [SHA_A]}, {"name": "taxsim"}, "oracle_identity_unrecorded"),
        # Re-pinning expires a legacy binding: the new report records binaries.
        (
            {"policyengine_taxsim": "2.30.0", "identity_unrecorded": True},
            {"taxsim_binaries": [{"sha256": SHA_A}]},
            "oracle_identity_changed",
        ),
        (
            {"policyengine_taxsim": "2.30.0", "identity_unrecorded": True},
            {"policyengine_taxsim": "2.30.0"},
            None,
        ),
    ],
)
def test_oracle_binding_match_rule(binding, oracle, expected) -> None:
    identity = report_oracle_identity(_report([], oracle=oracle))
    assert oracle_binding_mismatch(binding, identity, [_row("case-1", 1, 0)]) == expected


def test_oracle_binding_uses_per_row_binary_when_every_row_records_one() -> None:
    identity = report_oracle_identity(
        _report([], oracle={"taxsim_binaries": [{"sha256": SHA_A}, {"sha256": SHA_B}]})
    )
    crash_rows = [
        _row("case-1", 5, None, kind="engine_error", error={"engine": "taxsim", "signature": "SIGFPE", "binary_sha256": SHA_B})
    ]
    assert oracle_binding_mismatch({"taxsim_binary_sha256": [SHA_B]}, identity, crash_rows) is None
    mixed = crash_rows + [_row("case-2", 5, 1)]
    assert (
        oracle_binding_mismatch({"taxsim_binary_sha256": [SHA_B]}, identity, mixed)
        == "oracle_identity_changed"
    )


def test_sha_change_expires_entry_with_reason_and_unclassifies_rows() -> None:
    rows = [_row("case-1", 10, 0), _row("case-2", 20, 0)]
    entry = _bound(_entry(oracle_binding={"taxsim_binary_sha256": [SHA_A]}), rows)
    same = apply_dispositions(
        _report(copy.deepcopy(rows), oracle={"taxsim_binaries": [{"sha256": SHA_A}]}),
        _doc([entry]),
    )
    assert _block(same)["counts"]["upstream_engine_gap"] == 2
    assert _block(same)["expired_entries"] == []
    assert "expired_reasons" not in _block(same)

    repinned = apply_dispositions(
        _report(copy.deepcopy(rows), oracle={"taxsim_binaries": [{"sha256": SHA_B}]}),
        _doc([entry]),
    )
    block = _block(repinned)
    assert block["expired_entries"] == ["example"]
    assert block["expired_reasons"] == {"example": "oracle_identity_changed"}
    assert block["counts"]["upstream_engine_gap"] == 0
    assert block["unexplained_count"] == 2
    assert all("disposition" not in row for row in repinned["mismatches"])


def test_taxsim_lane_entry_without_oracle_binding_expires_at_merge() -> None:
    rows = [_row("case-1", 10, 0)]
    entry = _bound(_entry(), rows)
    del entry["oracle_binding"]
    block = _block(apply_dispositions(_report(rows), _doc([entry])))
    assert block["expired_reasons"] == {"example": "oracle_binding_missing"}
    # Outside a TAXSIM lane the same entry applies.
    block = _block(
        apply_dispositions(_report(rows, engines=("axiom", "policyengine")), _doc([entry]))
    )
    assert block["counts"]["upstream_engine_gap"] == 1


def test_report_lane_detection_uses_engine_sides() -> None:
    assert report_is_taxsim_lane(_report([]))
    assert report_is_taxsim_lane(_report([], engines=("taxsim", "policyengine")))
    assert not report_is_taxsim_lane(_report([], engines=("axiom", "policyengine")))
    # Grid lanes key engines by name, not by side.
    assert not report_is_taxsim_lane({"engines": {"axiom": "a", "taxsim": "siitax"}})


@pytest.mark.parametrize("malformed", [None, {}, "not-a-list", [None], [{"sha256": "short"}]])
def test_malformed_binary_identity_never_falls_back_to_legacy_version(malformed) -> None:
    report = _report(
        [_row("case-1", 10, 0)],
        oracle={"taxsim_binaries": malformed, "policyengine_taxsim": "2.30.0"},
        engine_identity={"taxsim": {"binaries": [{"sha256": SHA_A}]}},
    )
    entry = _bound(_entry(oracle_binding={"policyengine_taxsim": "2.30.0"}), report["mismatches"])
    merged = apply_dispositions(report, _doc([entry]))
    assert _block(merged)["expired_reasons"] == {"example": "oracle_identity_malformed"}
    assert all("disposition" not in row for row in merged["mismatches"])


def test_identity_precedence_with_all_three_contract_sources_present() -> None:
    report = _report(
        [], oracle={"taxsim_binaries": [{"sha256": SHA_A}], "policyengine_taxsim": "2.30.0"},
        engine_identity={"taxsim": {"binaries": [{"sha256": SHA_B}]}},
    )
    identity = report_oracle_identity(report)
    assert identity["taxsim_binary_sha256"] == [SHA_A]
    assert oracle_binding_mismatch({"taxsim_binary_sha256": [SHA_B]}, identity, []) == "oracle_identity_changed"
    del report["provenance"]["oracle"]["taxsim_binaries"]
    identity = report_oracle_identity(report)
    assert identity["taxsim_binary_sha256"] == [SHA_B]
    assert oracle_binding_mismatch({"policyengine_taxsim": "2.30.0"}, identity, []) == "oracle_identity_changed"


def test_per_row_binary_must_belong_to_taxsim_and_report_identity() -> None:
    row = _row("case-1", None, None, kind="engine_error", error={
        "engine": "policyengine", "binary_sha256": SHA_A,
        "other_side": {"engine": "taxsim", "binary_sha256": SHA_B},
    })
    assert row_binary_sha256(row) == SHA_B
    identity = report_oracle_identity(_report([], oracle={"taxsim_binaries": [{"sha256": SHA_A}]}))
    assert oracle_binding_mismatch({"taxsim_binary_sha256": [SHA_B]}, identity, [row]) == "oracle_identity_malformed"
    del row["error"]["other_side"]
    assert row_binary_sha256(row) is None


def test_engine_error_case_id_can_pin_missing_values_without_matching_false() -> None:
    entry = _entry(case_id="case-1", pinned={"left": 10, "right": None})
    del entry["case_selector"]
    entry["evidence"] = {"mechanism": "TAXSIM run failed.", "upstream_url": "https://example.org/1"}
    assert validate_dispositions(_doc([entry]), suite_engines=TAXSIM) == []
    report = _report([_row("case-1", 10, None, kind="engine_error")])
    assert _block(apply_dispositions(report, _doc([entry])))["counts"]["upstream_engine_gap"] == 1
    report["mismatches"][0]["right"] = False
    merged = apply_dispositions(report, _doc([entry]))
    assert _block(merged)["expired_reasons"] == {"example": "pinned_values_changed"}


# ---------------------------------------------------------------------------
# Structured match selectors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("match", "message"),
    [
        ({}, "universal selectors are forbidden"),
        (None, "universal selectors are forbidden"),
        ({"kind": "amount_difference"}, "at least one bound beyond concept and kind"),
        ({"slot": "base", "delta": {"sign": "pos"}}, "unknown fields: ['slot']"),
        ({"delta": {}}, "delta is vacuous"),
        ({"delta": {"tolerance": 1}}, "delta is vacuous"),
        ({"delta": {"sign": "up"}}, "sign must be 'pos' or 'neg'"),
        ({"delta": {"min": 5, "max": 1}}, "min exceeds"),
        ({"left": {"values": []}}, "values must be a non-empty numeric list"),
        ({"right": {"min": 0, "tolerance": 1}}, "tolerance only applies to `values`"),
        ({"facts": {}}, "facts must be a non-empty mapping"),
        ({"facts": {"state": {"nested": 1}}}, "must be a JSON scalar"),
        ({"facts": {"bad-name": 1}}, "must be an identifier"),
        ({"error_signature": ""}, "error_signature must be a non-empty string"),
    ],
)
def test_match_selector_guards(match, message) -> None:
    errors = validate_match(match)
    assert any(message in error for error in errors), errors


def test_match_selector_semantics() -> None:
    row = _row("case-1", 100, 70, facts={"state": "GA", "year": 2024, "mstat": 2, "blind": True})
    assert match_row({"facts": {"state": "GA"}}, row)
    assert match_row({"facts": {"state": ["MD", "GA"], "year": 2024}}, row)
    assert not match_row({"facts": {"state": "MD"}}, row)
    assert not match_row({"facts": {"missing": 1}}, row)
    # Type-aware: a boolean fact never equals a number.
    assert match_row({"facts": {"blind": True}}, row)
    assert not match_row({"facts": {"blind": 1}}, row)
    assert match_row({"facts": {"year": 2024.0}}, row)
    assert match_row({"delta": {"sign": "pos", "min": 30, "max": 30}}, row)
    assert not match_row({"delta": {"sign": "neg"}}, row)
    assert match_row({"delta": {"values": [29.996], "tolerance": 0.005}}, row)
    assert not match_row({"delta": {"values": [29.9]}}, row)
    assert match_row({"delta": {"abs_min": 30, "abs_max": 30}}, row)
    assert match_row({"left": {"min": 100}, "right": {"values": [70]}}, row)
    assert not match_row({"right": {"max": 69}}, row)
    assert match_row({"kind": ["amount_difference"], "delta": {"sign": "pos"}}, row)
    assert not match_row({"kind": "engine_error", "delta": {"sign": "pos"}}, row)
    # Rows without the bounded field never match.
    assert not match_row({"facts": {"state": "GA"}}, _row("case-2", 1, 0))
    assert not match_row({"delta": {"sign": "pos"}}, _row("case-3", None, 0))
    assert not match_row({"error_signature": "SIGFPE"}, row)


def test_error_selector_bounds_describe_one_engine_when_both_fail() -> None:
    row = _row("both", None, None, kind="engine_error", error={
        "engine": "policyengine", "signature": "unclassified",
        "other_side": {"engine": "taxsim", "signature": "SIGFPE"},
    })
    assert match_row({"error_signature": "SIGFPE"}, row)
    assert match_row({"error_engine": "taxsim", "error_signature": "SIGFPE"}, row)
    assert not match_row({"error_engine": "policyengine", "error_signature": "SIGFPE"}, row)


def test_match_entries_select_by_structure_not_case_list() -> None:
    rows = [
        _row("a", 30.8, 0, facts={"mstat": 2}),
        _row("b", 20.7, 0, facts={"mstat": 1}),
        _row("c", 5, 0, facts={"mstat": 2}),
    ]
    entry = _entry(match={"facts": {"mstat": 2}, "delta": {"values": [30.8]}})
    del entry["case_selector"]
    entry["evidence"]["row_arithmetic"] = [{"expression": "difference", "equals": 30.8}]
    entry = _bound(entry, [rows[0]])
    assert validate_dispositions(_doc([entry]), suite_engines=TAXSIM) == []
    merged = apply_dispositions(_report(rows), _doc([entry]))
    assert [row.get("disposition", {}).get("id") for row in merged["mismatches"]] == [
        "example", None, None
    ]


# ---------------------------------------------------------------------------
# Classification conservation
# ---------------------------------------------------------------------------


def test_overlapping_entries_fail_conservation_in_taxsim_lane() -> None:
    rows = [_row("case-1", 10, 0)]
    first = _bound(_entry(id="first"), rows)
    second = _bound(_entry(id="second", case_selector={"case_ids": ["case-1"]}), rows)
    with pytest.raises(DispositionConservationError, match=r"selected by entries \['first', 'second'\]"):
        apply_dispositions(_report(rows), _doc([first, second]))


def test_pins_do_not_resolve_a_taxsim_lane_overlap() -> None:
    rows = [_row("case-1", 10, 0)]
    pinned_away = _entry(id="pinned", case_id="case-1", pinned={"left": 999, "right": 0})
    del pinned_away["case_selector"]
    other = _bound(_entry(id="other"), rows)
    with pytest.raises(DispositionConservationError):
        apply_dispositions(_report(rows), _doc([pinned_away, other]))


def test_first_entry_still_wins_outside_taxsim_lanes() -> None:
    rows = [_row("case-1", 10, 0)]
    first = _entry(id="first")
    second = _entry(id="second", disposition="explained_residual")
    merged = apply_dispositions(
        _report(rows, engines=("axiom", "policyengine")), _doc([first, second])
    )
    assert merged["mismatches"][0]["disposition"]["id"] == "first"
    assert _block(merged)["expired_reasons"] == {"second": "no_live_rows"}


def test_select_rows_reports_every_claimant_only_under_conservation() -> None:
    rows = [_row("case-1", 10, 0)]
    entries = [_entry(id="first"), _entry(id="second")]
    winners, selected, _, conflicts = select_rows(entries, rows, conservation=False)
    assert winners == ["first"] and conflicts == []
    _, _, _, conflicts = select_rows(entries, rows, conservation=True)
    assert conflicts == [(rows[0], ["first", "second"])]


# ---------------------------------------------------------------------------
# Population bindings
# ---------------------------------------------------------------------------


def test_population_binding_drift_expires_entry() -> None:
    rows = [_row("case-1", 10, 0), _row("case-2", 20, 0)]
    entry = _bound(_entry(), rows)
    ok = _block(apply_dispositions(_report(copy.deepcopy(rows)), _doc([entry])))
    assert ok["counts"]["upstream_engine_gap"] == 2
    grown = rows + [_row("case-3", 30, 0)]
    block = _block(apply_dispositions(_report(grown), _doc([entry])))
    assert block["expired_reasons"] == {"example": "selector_binding_violated"}
    assert block["binding_violated_entries"] == ["example"]
    moved = [_row("case-1", 11, 0), _row("case-2", 20, 0)]
    block = _block(apply_dispositions(_report(moved), _doc([entry])))
    assert block["expired_reasons"] == {"example": "selector_binding_violated"}


def test_signature_population_binding_for_signatures_entries() -> None:
    rows = [
        _row("case-1", 30.8, 0, facts={"mstat": 2}),
        _row("case-2", 30.8, 0, facts={"mstat": 2}),
        _row("case-3", 20.7, 0, facts={"mstat": 1}),
    ]
    signature = mismatch_signature(rows[0])
    # The signature excludes the case id: the two MFJ rows share one.
    assert signature == mismatch_signature(rows[1])
    assert signature != mismatch_signature(rows[2])
    entry = _entry(signatures=[signature])
    del entry["case_selector"]
    entry["selector_binding"] = selection_binding(rows[:2], signature=True)
    assert entry["selector_binding"]["units"] == 2
    assert validate_dispositions(_doc([entry]), suite_engines=TAXSIM) == []
    merged = apply_dispositions(_report(copy.deepcopy(rows)), _doc([entry]))
    assert _block(merged)["counts"]["upstream_engine_gap"] == 2
    # A third member of the class changes the multiplicity: the binding drifts.
    extra = rows + [_row("case-4", 30.8, 0, facts={"mstat": 2})]
    block = _block(apply_dispositions(_report(extra), _doc([entry])))
    assert block["expired_reasons"] == {"example": "selector_binding_violated"}


def test_signature_population_digest_validation() -> None:
    assert signature_population_sha256([(SHA_B, 1), (SHA_A, 2)]) == (
        signature_population_sha256([(SHA_A, 2), (SHA_B, 1)])
    )
    for bad in ([("short", 1)], [(SHA_A, 1), (SHA_A, 1)], [(SHA_A, 0)], [(SHA_A, True)]):
        with pytest.raises(ValueError):
            signature_population_sha256(bad)
    rows = [_row("a", 1, 0), _row("b", 1, 0)]
    assert signature_population(rows) == [(mismatch_signature(rows[0]), 2)]


def test_selector_binding_shape_is_validated() -> None:
    entry = _entry(selector_binding={"units": 1, "rows_sha256": "xyz"})
    errors = validate_dispositions(_doc([entry]), suite_engines=TAXSIM)
    assert any("64-char lowercase hex" in error for error in errors)
    entry = _entry(selector_binding={"units": 0, "rows_sha256": SHA_A})
    errors = validate_dispositions(_doc([entry]), suite_engines=TAXSIM)
    assert any("positive integer" in error for error in errors)
    entry = _entry(selector_binding={"units": 1, "rows_sha256": SHA_A, "extra": 1})
    errors = validate_dispositions(_doc([entry]), suite_engines=TAXSIM)
    assert any("exactly the keys" in error for error in errors)


# ---------------------------------------------------------------------------
# Row arithmetic
# ---------------------------------------------------------------------------


def test_expression_evaluator_named_variables_only() -> None:
    assert evaluate_expression("left - right", {"left": 5, "right": 2}) == 3
    assert evaluate_expression("500 * facts.depx", {"facts.depx": 3}) == 1500
    assert expression_variables("difference - 500 * facts.depx") == {
        "difference", "facts.depx"
    }
    for bad in ("abs(left)", "left.real", "__import__('os')", "left[0]", "left < 1"):
        with pytest.raises(ArithmeticEvaluationError):
            evaluate_expression(bad, {"left": 1})
    with pytest.raises(ArithmeticEvaluationError, match="unknown variable"):
        expression_variables("wages * 0.0765")
    with pytest.raises(ArithmeticEvaluationError, match="missing or not numeric"):
        evaluate_expression("facts.depx", {})
    # Without variables the evaluator is the plain constant evaluator.
    with pytest.raises(ArithmeticEvaluationError, match="unsupported syntax"):
        evaluate_expression("left", None)
    with pytest.raises(ArithmeticEvaluationError, match="division by zero"):
        evaluate_expression("1 / 0", None)


@pytest.mark.parametrize("number", [float("nan"), float("inf"), -float("inf"), 10**400])
def test_evidence_and_pins_reject_nonfinite_values(number) -> None:
    entry = _valid_taxsim_entry()
    entry["evidence"]["row_arithmetic"][0]["equals"] = number
    assert any("numeric `equals`" in error for error in validate_dispositions(_doc([entry]), suite_engines=TAXSIM))
    entry["evidence"]["row_arithmetic"][0]["equals"] = 0
    entry["evidence"]["row_arithmetic"][0]["tolerance"] = number
    assert any("tolerance must" in error for error in validate_dispositions(_doc([entry]), suite_engines=TAXSIM))
    pinned = _entry(case_id="case-1", pinned={"left": number, "right": 0})
    del pinned["case_selector"]
    assert any("pinned.left must" in error for error in validate_dispositions(_doc([pinned]), suite_engines=TAXSIM))
    with pytest.raises(ArithmeticEvaluationError, match="missing or not numeric"):
        evaluate_expression("left", {"left": number})


def test_arithmetic_cannot_reconcile_nonfinite_intermediates() -> None:
    with pytest.raises(ArithmeticEvaluationError):
        expression_variables("left + 1e999")
    with pytest.raises(ArithmeticEvaluationError, match="non-finite"):
        evaluate_expression("left * left", {"left": 1e308})
    entry = _valid_taxsim_entry()
    entry["evidence"]["arithmetic"] = [{"expression": "1e308 * 1e308", "equals": 0}]
    assert any("non-finite" in error for error in validate_dispositions(_doc([entry]), suite_engines=TAXSIM))


def test_malformed_enum_values_return_validation_errors() -> None:
    entry = _valid_taxsim_entry()
    entry["attribution"] = ["taxsim"]
    assert any("attribution must" in error for error in validate_dispositions(_doc([entry]), suite_engines=TAXSIM))
    assert any("sign must" in error for error in validate_match({"delta": {"sign": ["pos"]}}))


def test_row_variables_expose_numeric_values_and_facts() -> None:
    row = _row("a", 10, 4, facts={"depx": 2, "state": "GA", "blind": False})
    assert row_variables(row) == {
        "left": 10.0, "right": 4.0, "difference": 6.0,
        "facts.depx": 2.0, "facts.blind": 0.0,
    }


def test_row_arithmetic_validation() -> None:
    def errors_for(items):
        entry = _valid_taxsim_entry()
        entry["evidence"]["row_arithmetic"] = items
        return validate_dispositions(_doc([entry]), suite_engines=TAXSIM)

    assert any("references no row variable" in e for e in errors_for([{"expression": "2 + 2", "equals": 4}]))
    assert any("unknown variable" in e for e in errors_for([{"expression": "wages", "equals": 4}]))
    assert any("numeric `equals`" in e for e in errors_for([{"expression": "left", "equals": "4"}]))
    assert any("numeric `equals`" in e for e in errors_for([{"expression": "left", "equals": []}]))
    assert any("tolerance must be >= 0" in e for e in errors_for([{"expression": "left", "equals": 1, "tolerance": -1}]))
    assert any("unknown keys" in e for e in errors_for([{"expression": "left", "equals": 1, "why": "x"}]))
    assert errors_for([{"expression": "right", "equals": [0, 500]}]) == []


def test_row_arithmetic_checks_every_selected_row() -> None:
    rows = [
        _row("case-1", 1700, 500, facts={"depx": 1}),
        _row("case-2", 3400, 1000, facts={"depx": 2}),
    ]
    entry = _bound(_entry(), rows)
    entry["evidence"]["row_arithmetic"] = [
        {"expression": "right - 500 * facts.depx", "equals": 0},
        {"expression": "right", "equals": [500, 1000, 1500]},
    ]
    assert validate_dispositions(_doc([entry]), suite_engines=TAXSIM) == []
    block = _block(apply_dispositions(_report(copy.deepcopy(rows)), _doc([entry])))
    assert block["counts"]["upstream_engine_gap"] == 2

    broken = [rows[0], _row("case-2", 3400, 1001, facts={"depx": 2})]
    entry = _bound(entry, broken)  # binding tracks the moved row...
    merged = apply_dispositions(_report(broken), _doc([entry]))
    block = _block(merged)  # ...but its evidence no longer holds on it.
    assert block["expired_reasons"] == {"example": "row_arithmetic_failed"}
    assert block["unexplained_count"] == 2
    # A row that lacks a referenced fact fails too (never read as zero).
    no_facts = [_row("case-1", 1700, 500), _row("case-2", 3400, 1000)]
    entry = _bound(entry, no_facts)
    block = _block(apply_dispositions(_report(no_facts), _doc([entry])))
    assert block["expired_reasons"] == {"example": "row_arithmetic_failed"}


def test_check_fails_on_row_arithmetic_failure_in_committed_report(tmp_path: Path) -> None:
    module = _load_script("apply_dispositions")
    dashboard = tmp_path / "dashboard" / "public" / "data"
    dashboard.mkdir(parents=True)
    module.REPO_ROOT = tmp_path
    module.DASHBOARD_DATA_DIR = dashboard
    rows = [_row("case-1", 10, 3)]
    entry = _bound(_entry(), rows)  # claims right == 0; the row says 3
    report = _report(rows)
    (dashboard / "example-suite.json").write_text(json.dumps(report, indent=2, sort_keys=True))
    problems, _, _ = module._merge_reports({"example-suite": _doc([entry])}, check=True)
    assert any("fails its evidence.row_arithmetic" in problem for problem in problems)


def test_check_reports_conservation_failure_as_problem(tmp_path: Path) -> None:
    module = _load_script("apply_dispositions")
    dashboard = tmp_path / "dashboard" / "public" / "data"
    dashboard.mkdir(parents=True)
    module.REPO_ROOT = tmp_path
    module.DASHBOARD_DATA_DIR = dashboard
    rows = [_row("case-1", 10, 0)]
    doc = _doc([_bound(_entry(id="a"), rows), _bound(_entry(id="b"), rows)])
    (dashboard / "example-suite.json").write_text(json.dumps(_report(rows), indent=2, sort_keys=True))
    problems, _, _ = module._merge_reports({"example-suite": doc}, check=True)
    assert any("classification conservation failure" in problem for problem in problems)


def test_check_uses_suite_sides_when_report_omits_engines(tmp_path: Path) -> None:
    module = _load_script("apply_dispositions")
    dashboard = tmp_path / "dashboard"
    dashboard.mkdir()
    comparisons = tmp_path / "comparisons"
    comparisons.mkdir()
    (comparisons / "example-suite.yaml").write_text(yaml.safe_dump({
        "runner": {"parameters": {"left": "policyengine", "right": "taxsim"}}
    }))
    module.REPO_ROOT = tmp_path
    module.DASHBOARD_DATA_DIR = dashboard
    rows = [_row("case-1", 10, 0)]
    report = _report(rows)
    del report["engines"]
    (dashboard / "example-suite.json").write_text(json.dumps(report))
    entries = [_bound(_entry(id="a"), rows), _bound(_entry(id="b"), rows)]
    problems, _, _ = module._merge_reports({"example-suite": _doc(entries)}, check=True)
    assert any("classification conservation failure" in problem for problem in problems)


# ---------------------------------------------------------------------------
# Engine-error rows (interface contract C2) and facts plumbing (C3)
# ---------------------------------------------------------------------------

_MAPPING = ProgramMapping(
    standard=CONCEPT,
    description="Federal income tax",
    category="tax",
    comparison="amount",
    tolerance=5,
    targets={"policyengine": "income_tax", "taxsim": "fiitax"},
)


def _engine_report(left_results, right_results, cases) -> dict:
    comparisons = Comparator([_MAPPING]).compare(left_results, right_results)
    return build_comparison_report(
        suite_name="pe-taxsim",
        population="taxsim-csv",
        locales=set(),
        scope=None,
        cases=cases,
        mappings=[_MAPPING],
        comparisons=comparisons,
    )


def test_taxsim_crash_becomes_engine_error_row() -> None:
    crash = EngineResult(
        "taxsim",
        "case-1",
        {},
        raw={
            "taxsim_error": {
                "signature": "SIGFPE",
                "returncode": -8,
                "stderr_tail": "Floating point exception",
                "binary_sha256": SHA_A,
            }
        },
        errors=("taxsim-crash:SIGFPE",),
    )
    report = _engine_report(
        [EngineResult("policyengine", "case-1", {"income_tax": 100}),
         EngineResult("policyengine", "case-2", {"income_tax": 50})],
        [crash, EngineResult("taxsim", "case-2", {"fiitax": 50})],
        [Case(case_id="case-1", period="2026"), Case(case_id="case-2", period="2026")],
    )
    summary = report["summary"]
    assert summary["match_count"] == 1
    assert summary["mismatch_count"] == 1
    assert summary["engine_error_count"] == 1
    assert summary["mismatches_by_kind"] == [{"value": MismatchKind.ENGINE_ERROR, "count": 1}]
    (row,) = report["mismatches"]
    assert row["kind"] == "engine_error"
    assert row["error"] == {
        "engine": "taxsim",
        "side": "right",
        "signature": "SIGFPE",
        "messages": ["taxsim-crash:SIGFPE"],
        "binary_sha256": SHA_A,
        "returncode": -8,
    }
    assert report["cases"][0]["mismatches"][0]["kind"] == "engine_error"
    assert report["errors"][0]["error"] == "taxsim-crash:SIGFPE"


def test_errored_case_never_counts_as_a_match() -> None:
    # PolicyEngine errored on the case yet its partial value equals TAXSIM's.
    report = _engine_report(
        [EngineResult("policyengine", "case-1", {"income_tax": 50}, errors=("aux: failed",))],
        [EngineResult("taxsim", "case-1", {"fiitax": 50})],
        [Case(case_id="case-1", period="2026")],
    )
    assert report["summary"]["match_count"] == 0
    (row,) = report["mismatches"]
    assert row["kind"] == "engine_error"
    assert row["error"]["signature"] == "unclassified"
    assert row["left"] == row["right"] == 50


def test_both_sides_errored_records_the_other_side() -> None:
    report = _engine_report(
        [EngineResult("policyengine", "case-1", {}, errors=("boom",))],
        [EngineResult("taxsim", "case-1", {}, errors=("taxsim-crash:rc=139",))],
        [Case(case_id="case-1", period="2026")],
    )
    error = report["mismatches"][0]["error"]
    assert error["engine"] == "policyengine" and error["signature"] == "unclassified"
    assert error["other_side"]["signature"] == "rc=139"


def test_reports_without_errors_keep_their_summary_shape() -> None:
    report = _engine_report(
        [EngineResult("policyengine", "case-1", {"income_tax": 100})],
        [EngineResult("taxsim", "case-1", {"fiitax": 50})],
        [Case(case_id="case-1", period="2026")],
    )
    assert "engine_error_count" not in report["summary"]
    assert "error" not in report["mismatches"][0]
    assert "facts" not in report["mismatches"][0]
    assert report["mismatches"][0]["kind"] == "amount_difference"


def test_engine_error_signature_parsing() -> None:
    assert engine_error_signature(("taxsim-crash:SIGFPE",)) == "SIGFPE"
    assert engine_error_signature(("x", "taxsim-crash: rc=2 ")) == "rc=2"
    assert engine_error_signature(("plain failure",), {"signature": "SIGSEGV"}) == "SIGSEGV"
    assert engine_error_signature(("plain failure",)) == "unclassified"


def test_selector_facts_ride_on_mismatch_rows_verbatim() -> None:
    facts = {"taxsim_state": 11, "state": "GA", "year": 2024, "mstat": 1, "page": 40,
             "sage": 0, "depx": 2, "idtl": 2}
    report = _engine_report(
        [EngineResult("policyengine", "case-1", {"income_tax": 100})],
        [EngineResult("taxsim", "case-1", {"fiitax": 50})],
        [Case(case_id="case-1", period="2024", metadata={"selector_facts": facts})],
    )
    row = report["mismatches"][0]
    assert row["facts"] == facts
    assert row["facts"] is not facts  # a copy, not the case's own dict


def test_dispositions_select_engine_error_rows_by_signature() -> None:
    crash_row = _row(
        "ga-2024-1", 100, None, kind="engine_error",
        facts={"state": "GA", "year": 2024},
        error={"engine": "taxsim", "side": "right", "signature": "SIGFPE",
               "messages": ["taxsim-crash:SIGFPE"], "binary_sha256": SHA_B},
    )
    rc_row = _row(
        "md-2024-1", 100, None, kind="engine_error",
        error={"engine": "taxsim", "side": "right", "signature": "rc=2",
               "messages": ["taxsim-crash:rc=2"], "binary_sha256": SHA_B},
    )
    rows = [crash_row, rc_row]
    entry = _entry(
        id="september-build-sigfpe",
        kind="engine_error",
        match={"error_signature": "SIGFPE", "facts": {"state": ["GA", "MD"]}},
        oracle_binding={"taxsim_binary_sha256": [SHA_B]},
        linked_issue="https://github.com/PolicyEngine/policyengine-taxsim/issues/1214",
    )
    del entry["case_selector"]
    entry["evidence"] = {"mechanism": "The September build crashes (SIGFPE) in gatax24."}
    entry = _bound(entry, [crash_row])
    assert validate_dispositions(_doc([entry]), suite_engines=("policyengine", "taxsim")) == []
    # The report ran two binaries; the crash row itself records the one that
    # failed, so a binding to that binary alone holds.
    report = _report(
        rows,
        engines=("policyengine", "taxsim"),
        oracle={"taxsim_binaries": [{"sha256": SHA_A}, {"sha256": SHA_B}]},
    )
    merged = apply_dispositions(report, _doc([entry]))
    assert [row.get("disposition", {}).get("id") for row in merged["mismatches"]] == [
        "september-build-sigfpe", None
    ]
    assert _block(merged)["unexplained_count"] == 1


# ---------------------------------------------------------------------------
# Migration invariance and repo-wide safety
# ---------------------------------------------------------------------------

#: Row-level assignment digests of the checked-in TAXSIM reports, computed
#: with the pre-hardening merge over the pre-migration dispositions files.
#: The migration (attribution, oracle/population bindings, row arithmetic,
#: citations) must reproduce them exactly.
MIGRATION_BASELINE = {
    "fiit-taxsim-ecps": (
        "reports/axiom-taxsim-fiit-ecps-verify-2026-08-28.json",
        "2a144e710e3875c3e247abea5861c5c5eca3b6a9b3d81054e5b19a8ac80299dc",
    ),
    "co-tax-intersection-taxsim": (
        "dashboard/public/data/axiom-taxsim-co-tax-intersection-ecps.json",
        "ecfa30855fc9130c7ae192b0d7b5cbaf43231d4b2d3437b665e08d78ff87e47c",
    ),
    "co-state-income-tax-taxsim": (
        "dashboard/public/data/axiom-taxsim-co-state-income-tax-ecps.json",
        "0cc14e9c2027b1f9397174836cfeab1157ab93a986866b7c9f5150008684069f",
    ),
}


@pytest.mark.parametrize("suite", sorted(MIGRATION_BASELINE))
def test_taxsim_migration_preserves_row_assignment(suite: str) -> None:
    report_path, digest = MIGRATION_BASELINE[suite]
    report = json.loads((REPO_ROOT / report_path).read_text())
    document = load_dispositions(
        REPO_ROOT / "dispositions" / f"{suite}.yaml", repo_root=REPO_ROOT
    )
    merged = apply_dispositions(report, document)
    block = _block(merged)
    assert assignment_digest(merged) == digest
    assert block["expired_entries"] == []
    assert block["orphaned_entries"] == []
    assert block["unexplained_count"] == 0
    # The checked-in reports record no TAXSIM identity; the migrated
    # bindings say so explicitly and expire once a report records one.
    assert report_oracle_identity(report)["source"] is None
    repinned = copy.deepcopy(report)
    repinned.setdefault("provenance", {}).setdefault("oracle", {})["taxsim_binaries"] = [
        {"sha256": SHA_A}
    ]
    expired = _block(apply_dispositions(repinned, document))
    assert set(expired["expired_reasons"].values()) == {"oracle_identity_changed"}
    assert expired["unexplained_count"] == report["summary"]["mismatch_count"]


def test_selected_rows_digest_is_order_independent() -> None:
    rows = [_row("b", 2, 1), _row("a", 1, 0)]
    assert selected_rows_sha256(rows) == selected_rows_sha256(list(reversed(rows)))


# ---------------------------------------------------------------------------
# scripts/bind_dispositions.py
# ---------------------------------------------------------------------------


def test_bind_dispositions_stamps_and_checks(tmp_path: Path, capsys) -> None:
    module = _load_script("bind_dispositions")
    dispositions_dir = tmp_path / "dispositions"
    dispositions_dir.mkdir()
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    comparisons = tmp_path / "comparisons"
    comparisons.mkdir()
    (comparisons / "example-suite.yaml").write_text(
        yaml.safe_dump({"name": "example-suite",
                        "runner": {"parameters": {"left": "axiom", "right": "taxsim"}}})
    )
    module.REPO_ROOT = tmp_path
    module.DISPOSITIONS_DIR = dispositions_dir
    module.DASHBOARD_DATA_DIR = tmp_path / "dashboard"
    rows = [_row("case-1", 10, 0), _row("case-2", 20, 0), _row("single", 5, 0, concept="us:test#other")]
    report_path = reports_dir / "full.json"
    report_path.write_text(json.dumps(_report(rows)))
    multi = _entry()
    del multi["oracle_binding"]
    single = _entry(id="single-row", concept="us:test#other", case_id="single")
    del single["case_selector"], single["oracle_binding"]
    text = "# hand comment survives\n" + yaml.safe_dump(_doc([multi, single]), sort_keys=False)
    (dispositions_dir / "example-suite.yaml").write_text(text)

    argv = ["example-suite", "--report", str(report_path), "--legacy-policyengine-taxsim", "2.30.0"]
    assert module.main([*argv, "--check"]) == 1
    assert module.main(argv) == 0
    stamped_text = (dispositions_dir / "example-suite.yaml").read_text()
    assert stamped_text.startswith("# hand comment survives\n")
    stamped = yaml.safe_load(stamped_text)
    by_id = {entry["id"]: entry for entry in stamped["entries"]}
    assert by_id["example"]["selector_binding"] == selection_binding(rows[:2])
    assert by_id["single-row"]["pinned"] == {"left": 5, "right": 0}
    assert by_id["example"]["oracle_binding"] == {
        "policyengine_taxsim": "2.30.0", "identity_unrecorded": True
    }
    assert validate_dispositions(stamped, repo_root=tmp_path) == []
    assert module.main([*argv, "--check"]) == 0
    # A moved value is drift.
    moved = [_row("case-1", 11, 0), rows[1], _row("single", 6, 0, concept="us:test#other")]
    report_path.write_text(json.dumps(_report(moved)))
    assert module.main([*argv, "--check"]) == 1
    diagnostics = capsys.readouterr().err
    assert "drift: example: selector_binding" in diagnostics
    assert "drift: single-row: pinned" in diagnostics
    assert module.main(argv) == 0
    refreshed = yaml.safe_load((dispositions_dir / "example-suite.yaml").read_text())
    assert refreshed["entries"][1]["pinned"] == {"left": 6, "right": 0}
    assert module.main([*argv, "--check"]) == 0


def test_shard_merge_sums_engine_error_counts() -> None:
    module = _load_script("merge_shard_reports")

    def shard(count):
        summary = {"match_count": 0, "mismatch_count": count, "comparison_count": count}
        if count:
            summary["engine_error_count"] = count
        return {"schema_version": "v2", "suite": "s", "population": "p",
                "engines": {"left": "policyengine", "right": "taxsim"},
                "locales": [], "summary": summary}

    assert module.merge([shard(0), shard(3), shard(2)])["summary"]["engine_error_count"] == 5
    assert "engine_error_count" not in module.merge([shard(0), shard(0)])["summary"]
