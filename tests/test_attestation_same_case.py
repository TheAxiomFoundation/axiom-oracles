"""Coverage requires both returned engines in one real output comparison."""

import json
from collections import Counter
from pathlib import Path

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from axiom_oracles.conformance.attestation import OracleTargetResolver, attest
from axiom_oracles.conformance.loader import OracleIdentity, Universe
from axiom_oracles.conformance.schema import UniversePolicy
from axiom_oracles.conformance.scoreboard import score_jurisdiction


ROOT = Path(__file__).parents[1]
DIALECTS = ("ledger", "role", "reverse-role", "grid", "components", "fiit", "efrs", "yale", "yale-members")


def _report(dialect, pairs, *, stamped=True):
    engine, output, concept, axiom_target = "policyengine", "registered", "probe:tax", "axiom_tax"
    suite = "same-case-probe"
    if dialect == "fiit":
        suite, output, concept = "fiit-ecps", "employee_medicare_tax", "us:tax/payroll#employee_medicare"
        axiom_target = "us:statutes/26/3101/b/1#hospital_insurance_wage_tax"
    elif dialect == "efrs":
        suite, output, concept = "uk-tax-benefits-efrs", "carers_allowance", "uk:policies/govuk/carers-allowance#carers_allowance_annual_amount"
        axiom_target = concept
    elif dialect.startswith("yale"):
        suite, engine, output, concept = "us-tariff-panel", "yale_statutory", "statutory_base_rate", "mfn"
        axiom_target = output
        if dialect == "yale-members":
            output, concept, axiom_target = "statutory_rate_ieepa_recip", "ieepa", "statutory_rate_ieepa_recip"
    targets = ("other_component", output) if dialect == "components" else (output,)
    if dialect == "yale-members":
        targets = (output, "statutory_rate_ieepa_fent")
    axiom_targets = targets if dialect == "components" else (axiom_target,)
    engines = {"left": "axiom", "right": engine}
    if dialect == "reverse-role":
        engines = {"left": engine, "right": "axiom"}
    elif dialect in {"grid", "components", "yale", "yale-members"}:
        engines = {"axiom": axiom_target, engine: ",".join(targets)}
    report = {
        "suite": suite, "engines": engines, "case_count": len(pairs),
        "summary": {"comparison_count": len(pairs), "error_count": 0},
        "aggregates": [{"concept": concept, "comparison_count": len(pairs)}],
        "output_bindings": {concept: {"axiom": list(axiom_targets), engine: list(targets)}},
        "cases": [], "observed_outputs": [],
    }
    for index, (axiom, oracle) in enumerate(pairs):
        case_id = f"real-{index}"
        case = {"case_id": case_id}
        if dialect in {"role", "reverse-role", "efrs"}:
            left, right = (oracle, axiom) if dialect == "reverse-role" else (axiom, oracle)
            kind = "missing_left" if left is None else "missing_right" if right is None else "amount_difference"
            case["mismatches"] = [{"concept": concept, "left": left, "right": right, "kind": kind}]
            if dialect == "efrs":
                case["mismatches"][0].update(surface="carers-allowance-final", description="UK Carer's Allowance annual amount — output=carers_allowance_annual_amount")
        elif dialect in {"grid", "components"}:
            case.update(concept=concept, axiom=axiom, policyengine=oracle)
            if dialect == "components":
                case["policyengine_components"] = {output: oracle, "other_component": 0}
                case["axiom_components"] = {output: axiom, "other_component": 0}
        elif dialect.startswith("yale"):
            case.update(unit_count=1, expected={concept: oracle}, axiom={concept: axiom})
            if dialect == "yale-members":
                report["observed_outputs"].extend([
                    {"case_id": case_id, "engine": "axiom", "concept": concept, "variable": output, "value": axiom},
                    {"case_id": case_id, "engine": engine, "concept": concept, "variable": output, "value": oracle},
                ])
        elif dialect == "fiit":
            report["observed_outputs"].append({
                "case_id": case_id, "engine": engine, "concept": concept,
                "variable": output, "value": oracle, "counterpart_value": axiom,
                "surface": "employee-medicare", "output": output,
            })
        else:
            report["observed_outputs"].extend([
                {"case_id": case_id, "engine": "axiom", "concept": concept, "variable": axiom_target, "value": axiom},
                {"case_id": case_id, "engine": engine, "concept": concept, "variable": output, "value": oracle},
            ])
        report["cases"].append(case)
    if dialect == "fiit":
        report["provenance"] = {"generated_by": "scripts/run_comparison.py::fiit-ecps"}
        report["output_summary"] = [{"surface": "employee-medicare", "output": output, "compared": len(pairs), "mismatches": 0}]
    if dialect.startswith("yale"):
        report["provenance"] = {"generator": "scripts/generate_us_tariff_panel.py"}
        report["summary"]["slots"] = {concept: {"matches": len(pairs), "mismatches": 0}}
        report["scope"] = {"comparison_units": len(pairs), "authority_slots": [concept], "reference": {"columns": list(targets)}}
    if stamped:
        # The claims truthfully count each side's returns, even for disjoint cases.
        report["attestation"] = {"executed": True, "outputs": [{
            "engine": engine, "concept": concept, "variable": output,
            "comparisons": sum(oracle is not None for _, oracle in pairs),
        }]}
        if dialect not in {"fiit", "yale", "yale-members", "components"} and any(axiom is not None for axiom, _ in pairs):
            report["attestation"]["outputs"].append({
                "engine": "axiom", "concept": concept, "variable": axiom_target,
                "comparisons": sum(axiom is not None for axiom, _ in pairs),
            })
    resolver = OracleTargetResolver({concept: {engine: frozenset(targets), "axiom": frozenset(axiom_targets)}})
    oracle = OracleIdentity("probe", "1", "US", "US", "yale-tariff" if dialect.startswith("yale") else "policyengine")
    universe = Universe("probe", oracle, [UniversePolicy("p", "p", (output,), True, suite=suite)])
    return report, resolver, universe


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("pairs", [[(None, 0)], [(None, 0), (0, None)]], ids=["missing-axiom", "disjoint-cases"])
def test_each_dialect_rejects_oracle_only_or_disjoint_case_evidence(dialect, pairs):
    report, resolver, universe = _report(dialect, pairs)
    evidence = attest(report, oracle=universe.oracle, resolver=resolver)
    board, rows = score_jurisdiction(universe, [report], resolver=resolver)
    assert not evidence.binds(universe.policies[0].output_vars)
    assert board.covered == 0
    assert not rows[0].covered


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("axiom_value", [float("nan"), float("inf"), float("-inf"), "0"])
def test_each_dialect_requires_a_valid_returned_axiom_value(dialect, axiom_value):
    report, resolver, universe = _report(dialect, [(axiom_value, 0)])
    assert not attest(report, oracle=universe.oracle, resolver=resolver).binds(universe.policies[0].output_vars)
    assert score_jurisdiction(universe, [report], resolver=resolver)[0].covered == 0


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("pairs", [[(0, 0), (1, 1)], [(None, 0), (0, None)]], ids=["contradictory-values", "contradictory-missing-sides"])
def test_duplicate_case_id_cannot_combine_contradictory_returns(dialect, pairs):
    report, resolver, universe = _report(dialect, pairs)
    report["cases"][1]["case_id"] = "real-0"
    for row in report["observed_outputs"]:
        row["case_id"] = "real-0"
    assert not attest(report, oracle=universe.oracle, resolver=resolver).binds(universe.policies[0].output_vars)
    assert score_jurisdiction(universe, [report], resolver=resolver)[0].covered == 0


def test_native_fiit_oracle_ledger_without_retained_counterpart_cannot_cover():
    report, resolver, universe = _report("fiit", [(0, 0)])
    report["observed_outputs"][0].pop("counterpart_value")
    assert not attest(report, oracle=universe.oracle, resolver=resolver).binds(universe.policies[0].output_vars)
    assert score_jurisdiction(universe, [report], resolver=resolver)[0].covered == 0


@pytest.mark.parametrize("engine", ["axiom", "policyengine"])
@pytest.mark.parametrize("declaration", ["output_bindings", "engine_bindings"])
def test_native_fiit_authoritative_pair_rejects_contradictory_recorded_target(engine, declaration):
    report, resolver, universe = _report("fiit", [(0, 0)], stamped=False)
    assert attest(report, oracle=universe.oracle, resolver=resolver).binds(universe.policies[0].output_vars)
    assert score_jurisdiction(universe, [report], resolver=resolver)[0].covered == 1
    concept = report["aggregates"][0]["concept"]
    if declaration == "output_bindings":
        report[declaration][concept][engine] = "contradictory_native_target"
    else:
        report[declaration] = {engine: {"outputs": ["contradictory_native_target"]}}
    assert not attest(report, oracle=universe.oracle, resolver=resolver).binds(universe.policies[0].output_vars)
    assert score_jurisdiction(universe, [report], resolver=resolver)[0].covered == 0


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("stamped", [False, True])
def test_same_case_zero_pair_survives_in_each_dialect_with_or_without_stamp(dialect, stamped):
    report, resolver, universe = _report(dialect, [(0, 0)], stamped=stamped)
    evidence = attest(report, oracle=universe.oracle, resolver=resolver)
    assert evidence.binds(universe.policies[0].output_vars)
    assert score_jurisdiction(universe, [report], resolver=resolver)[0].covered == 1


@settings(max_examples=35, deadline=None, database=None, derandomize=True)
@example(pairs=[(None, False), (False, None)], stamped=True)
@example(pairs=[(False, False)], stamped=False)
@given(pairs=st.lists(st.tuples(st.none() | st.booleans() | st.integers(-10, 10), st.none() | st.booleans() | st.integers(-10, 10)), min_size=1, max_size=5), stamped=st.booleans())
def test_coverage_intersects_valid_case_identities_instead_of_engine_totals(pairs, stamped):
    report, resolver, universe = _report("ledger", pairs, stamped=stamped)
    # A stamp can omit output rows, while execution evidence remains in the body.
    if stamped:
        report["attestation"].pop("outputs")
    expected = any(axiom is not None and oracle is not None for axiom, oracle in pairs)
    assert score_jurisdiction(universe, [report], resolver=resolver)[0].covered == int(expected)


def test_historical_fiit_intermediate_scalars_cannot_attest_final_eitc():
    report = json.loads((ROOT / "dashboard/public/data/axiom-policyengine-fiit-ecps.json").read_text())
    concept = "us:tax/federal-income-tax#eitc"
    rows = [row for case in report["cases"] for row in case.get("mismatches", []) if row.get("concept") == concept]
    assert Counter(row.get("description") for row in rows) == {
        "Earned Income Tax Credit — output=eitc_earned_income": 272,
        "Earned Income Tax Credit — output=eitc_phased_in": 95,
    }
    assert not any("variable" in row for row in rows)
    report["attestation"] = {"executed": True, "outputs": [{"engine": "policyengine", "concept": concept, "variable": "eitc", "comparisons": 1}]}
    oracle = OracleIdentity("policyengine-us", "1.767.3", "US_2026", "US", "policyengine")
    universe = Universe("us-pe", oracle, [UniversePolicy("us-pe:eitc", "eitc", ("eitc",), True, suite="fiit-ecps")])
    assert not attest(report, oracle=oracle).binds(("eitc",))
    board, scores = score_jurisdiction(universe, [report])
    assert board.covered == 0
    assert not scores[0].covered


@pytest.mark.parametrize(("filename", "output", "backend"), [
    ("axiom-policyengine-us-seca-grid.json", "self_employment_tax", "policyengine"),
    ("axiom-euromod-be-unemployment.json", "bun_s", "euromod"),
])
def test_historical_unstamped_same_case_pairs_restore_registered_coverage(filename, output, backend):
    report = json.loads((ROOT / "dashboard/public/data" / filename).read_text())
    assert "attestation" not in report
    oracle = OracleIdentity("probe", "1", "US", "US", backend)
    universe = Universe("probe", oracle, [UniversePolicy("p", "p", (output,), True, suite=report["suite"])])
    assert attest(report, oracle=backend).binds((output,))
    # Ignore unrelated provenance model identity in this output-binding probe.
    report.get("provenance", {}).pop("oracle", None)
    assert score_jurisdiction(universe, [report])[0].covered == 1


@pytest.mark.parametrize(("output", "concept", "case_id", "oracle_value"), [
    ("carers_allowance", "uk:policies/govuk/carers-allowance#carers_allowance_annual_amount", "uk-efrs-person_17164005", 4495.39990234375),
    ("carer_support_payment", "uk:policies/govuk/carer-support-payment#carer_support_payment_annual_amount", "uk-efrs-person_18720006", 5103.7998046875),
])
def test_historical_efrs_final_output_pairs_bind_to_native_single_targets(output, concept, case_id, oracle_value):
    report = json.loads((ROOT / "dashboard/public/data/axiom-policyengine-uk-tax-benefits-efrs.json").read_text())
    assert "attestation" not in report
    case = next(case for case in report["cases"] if case["case_id"] == case_id)
    comparison = next(row for row in case["mismatches"] if row["concept"] == concept)
    assert comparison["left"] == 0
    assert comparison["right"] == oracle_value
    # Native producer output specs bind these exact scalar finals to the oracle.
    assert attest(report, oracle="policyengine").binds((output,))
    oracle = OracleIdentity("policyengine-uk", "1", "UK", "UK", "policyengine")
    report.get("provenance", {}).pop("oracle", None)
    universe = Universe("uk-pe", oracle, [UniversePolicy(output, output, (output,), True, suite=report["suite"])])
    assert score_jurisdiction(universe, [report])[0].covered == 1


@pytest.mark.parametrize("stamped", [False, True])
def test_historical_aca_recorded_target_overrides_conflicting_generic_final_mapping(stamped):
    report = json.loads((ROOT / "dashboard/public/data/axiom-policyengine-us-aca-ptc-grid.json").read_text())
    concept = report["concept"]
    axiom = report["engine_bindings"]["axiom"]["output"]
    assert report["engine_bindings"]["policyengine"]["outputs"] == ["used_aca_ptc"]
    resolver = OracleTargetResolver({concept: {"axiom": frozenset({axiom}), "policyengine": frozenset({"aca_ptc"})}})
    if stamped:
        report["attestation"] = {"executed": True, "outputs": [{"engine": "policyengine", "concept": concept, "variable": "aca_ptc", "comparisons": 1}]}
    evidence = attest(report, oracle="policyengine", resolver=resolver)
    assert not evidence.binds(("aca_ptc",))
    assert evidence.binds(("used_aca_ptc",))
    oracle = OracleIdentity("policyengine-us", "1", "US", "US", "policyengine")
    report.get("provenance", {}).pop("oracle", None)
    universe = Universe("us-pe", oracle, [UniversePolicy(output, output, (output,), True, suite=report["suite"]) for output in ("aca_ptc", "used_aca_ptc")])
    board, rows = score_jurisdiction(universe, [report], resolver=resolver)
    assert not rows[0].covered
    assert rows[1].covered is (not stamped)
    assert board.covered == int(not stamped)


@pytest.mark.parametrize("engine", ["axiom", "policyengine"])
def test_conflicting_recorded_aca_bindings_cannot_attest_either_candidate(engine):
    report = json.loads((ROOT / "dashboard/public/data/axiom-policyengine-us-aca-ptc-grid.json").read_text())
    concept = report["concept"]
    report["output_bindings"] = {concept: {engine: "contradictory_axiom_query" if engine == "axiom" else "aca_ptc"}}
    report["attestation"] = {"executed": True, "outputs": [{"engine": "policyengine", "concept": concept, "variable": "aca_ptc" if engine == "policyengine" else "used_aca_ptc", "comparisons": 1}]}
    evidence = attest(report, oracle="policyengine")
    assert not evidence.binds(("aca_ptc", "used_aca_ptc"))


@pytest.mark.parametrize(("slot", "output"), [
    ("china_semiconductor_section_301", "statutory_rate_301_cs"),
    ("other", "statutory_rate_other"),
])
@pytest.mark.parametrize("stamped", [False, True])
def test_yale_slot_without_encoded_axiom_query_cannot_attest_implicit_zero(slot, output, stamped):
    report, _, _ = _report("yale", [(0, 0)], stamped=False)
    report["aggregates"][0]["concept"] = slot
    report["output_bindings"] = {slot: {"axiom": output, "yale_statutory": output}}
    report["summary"]["slots"] = {slot: {"matches": 1, "mismatches": 0}}
    report["scope"]["authority_slots"] = [slot]
    report["scope"]["reference"]["columns"] = [output]
    report["cases"][0].update(expected={slot: 0}, axiom={slot: 0})
    if stamped:
        report["attestation"] = {"executed": True, "outputs": [{"engine": "yale_statutory", "concept": slot, "variable": output, "comparisons": 1}]}
    resolver = OracleTargetResolver({slot: {"axiom": frozenset({output}), "yale_statutory": frozenset({output})}})
    evidence = attest(report, oracle="yale-tariff", resolver=resolver)
    assert not evidence.binds((output,))
    oracle = OracleIdentity("yale-statutory", "1", "US", "US", "yale-tariff")
    universe = Universe("probe", oracle, [UniversePolicy(output, output, (output,), True, suite="us-tariff-panel")])
    assert score_jurisdiction(universe, [report], resolver=resolver)[0].covered == 0


@pytest.mark.parametrize("engine", ["axiom", "yale_statutory"])
@pytest.mark.parametrize("declaration", ["output_bindings", "engine_bindings"])
def test_yale_native_slot_rejects_contradictory_recorded_targets(engine, declaration):
    report, resolver, universe = _report("yale", [(0, 0)], stamped=False)
    assert attest(report, oracle=universe.oracle, resolver=resolver).binds(universe.policies[0].output_vars)
    assert score_jurisdiction(universe, [report], resolver=resolver)[0].covered == 1
    if declaration == "output_bindings":
        report[declaration]["mfn"][engine] = "contradictory_slot_target"
    else:
        report[declaration] = {engine: {"outputs": ["contradictory_slot_target"]}}
    assert not attest(report, oracle=universe.oracle, resolver=resolver).binds(universe.policies[0].output_vars)
    assert score_jurisdiction(universe, [report], resolver=resolver)[0].covered == 0


def test_yale_authoritative_axiom_query_uri_retains_the_real_slot_pair():
    from axiom_oracles.suites.us_tariff_panel import AUTHORITY_SLOTS

    report, resolver, universe = _report("yale", [(0, 0)], stamped=False)
    native_query, columns = AUTHORITY_SLOTS["mfn"]
    assert columns == ("statutory_base_rate",)
    report["output_bindings"]["mfn"]["axiom"] = native_query
    assert attest(report, oracle=universe.oracle, resolver=resolver).binds(columns)
    assert score_jurisdiction(universe, [report], resolver=resolver)[0].covered == 1


@pytest.mark.parametrize("change", [
    {"concept": "wrong:concept"}, {"concept": None},
    {"variable": "wrong_output"}, {"variable": None},
    {"concept": "wrong:concept", "variable": "wrong_output"},
])
def test_native_fiit_malformed_labels_cannot_hide_a_contradictory_native_output(change):
    report, resolver, universe = _report("fiit", [(0, 0)])
    conflict = dict(report["observed_outputs"][0], value=None, **change)
    report["observed_outputs"].append(conflict)
    assert not attest(report, oracle=universe.oracle, resolver=resolver).binds(universe.policies[0].output_vars)
    assert score_jurisdiction(universe, [report], resolver=resolver)[0].covered == 0


@pytest.mark.parametrize("engine", ["axiom", "policyengine"])
def test_grid_engine_declaration_must_agree_with_recorded_comparison_binding(engine):
    report, resolver, universe = _report("grid", [(0, 0)])
    report["engines"][engine] = "contradictory_target"
    assert not attest(report, oracle=universe.oracle, resolver=resolver).binds(universe.policies[0].output_vars)
    assert score_jurisdiction(universe, [report], resolver=resolver)[0].covered == 0


def test_historical_tv_licence_duplicate_ids_for_distinct_outputs_retain_final_pair():
    report = json.loads((ROOT / "dashboard/public/data/axiom-policyengine-uk-tv-licence.json").read_text())
    assert "attestation" not in report
    cases = [case for case in report["cases"] if case["case_id"] == "tvl-working-age-full-fee"]
    assert {case["concept"] for case in cases} == {
        "uk:policies/govuk/tv-licence#tv_licence_net_cost",
        "uk:policies/govuk/tv-licence#free_tv_licence_value",
    }
    assert {(case["axiom"], case["policyengine"]) for case in cases} == {(180, 180), (0, 0)}
    assert attest(report, oracle="policyengine").binds(("tv_licence",))
    oracle = OracleIdentity("policyengine-uk", "1", "UK", "UK", "policyengine")
    universe = Universe("uk-pe", oracle, [UniversePolicy("tv_licence", "tv_licence", ("tv_licence",), True, suite=report["suite"])])
    report.get("provenance", {}).pop("oracle", None)
    assert score_jurisdiction(universe, [report])[0].covered == 1


def test_historical_tv_licence_diagnostic_rows_alone_cannot_cover_final_output():
    report = json.loads((ROOT / "dashboard/public/data/axiom-policyengine-uk-tv-licence.json").read_text())
    report["cases"] = [case for case in report["cases"] if case["concept"].endswith("#free_tv_licence_value")]
    report["case_count"] = len(report["cases"])
    report["summary"]["comparison_count"] = len(report["cases"])
    assert not attest(report, oracle="policyengine").binds(("tv_licence",))
    oracle = OracleIdentity("policyengine-uk", "1", "UK", "UK", "policyengine")
    universe = Universe("uk-pe", oracle, [UniversePolicy("tv_licence", "tv_licence", ("tv_licence",), True, suite=report["suite"])])
    report.get("provenance", {}).pop("oracle", None)
    assert score_jurisdiction(universe, [report])[0].covered == 0
