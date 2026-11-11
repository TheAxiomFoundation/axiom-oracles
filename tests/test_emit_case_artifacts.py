from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


def _load_module():
    path = Path(__file__).parents[1] / "scripts" / "emit_case_artifacts.py"
    spec = importlib.util.spec_from_file_location("emit_case_artifacts", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _canonical_report(*, mismatch_count: int = 2) -> dict:
    return {
        "case_count": 2,
        "engines": {
            "left": "axiom",
            "right": "policyengine",
            "versions": {
                "policyengine": "4.18.9",
                "policyengine_core": "3.30.3",
                "policyengine_us": "1.767.3",
            },
        },
        "mismatches": [
            {
                "case_id": "case-1",
                "concept": "benefit",
                "left": 24,
                "right": 100,
                "difference": -76,
                "disposition": {"disposition": "bridge_artifact"},
            },
            {
                "case_id": "case-2",
                "concept": "eligibility",
                "left": False,
                "right": True,
                "difference": None,
            },
        ],
        "summary": {"mismatch_count": mismatch_count},
    }


def _served_rows() -> list[dict]:
    return [
        {
            "id": "case-1",
            "r": 50,
            "h": {"n": 1, "e": 0, "a": [30]},
            "m": [
                {
                    "c": "benefit",
                    "l": 24,
                    "x": 100,
                    "d": 76,
                    "e": "bridge_artifact",
                }
            ],
        },
        {
            "id": "case-2",
            "r": 50,
            "h": {"n": 1, "e": 0, "a": [17]},
            "m": [
                {
                    "c": "eligibility",
                    "l": False,
                    "x": True,
                    "d": None,
                }
            ],
        },
    ]


def _write_fixture(
    module,
    tmp_path: Path,
    *,
    report: dict,
    rows: list[dict],
    index_updates: dict | None = None,
) -> dict:
    data = tmp_path / "data"
    out = data / "cases" / "test-suite"
    out.mkdir(parents=True)
    module.DASHBOARD_DATA = data
    module.OUT_ROOT = data / "cases"
    basename = "axiom-policyengine-test"
    (data / f"{basename}.json").write_text(json.dumps(report))
    (out / "chunk-0.json").write_text(json.dumps(rows))
    index = {
        "suite": "test-suite",
        "count": len(rows),
        "chunks": 1,
        "chunk_size": 500,
        "engines": report["engines"],
        "mismatch_concepts": sorted(
            {mismatch["concept"] for mismatch in report["mismatches"]}
        ),
        "source": "ignored-full-report.json",
        "total_cases": report["case_count"],
    }
    index.update(index_updates or {})
    (out / "index.json").write_text(json.dumps(index))
    return {"basename": basename}


def test_emitter_preserves_complete_legacy_corpus_without_full_source(tmp_path):
    module = _load_module()
    config = _write_fixture(
        module, tmp_path, report=_canonical_report(), rows=_served_rows(),
    )
    module.REPORTS = tmp_path / "absent-reports"
    corpus = module.OUT_ROOT / "test-suite"
    before = {path.name: path.read_bytes() for path in corpus.iterdir()}

    assert "preserve" in module.emit_suite("test-suite", config)
    assert {path.name: path.read_bytes() for path in corpus.iterdir()} == before


def test_emitter_refuses_stale_legacy_corpus_without_downgrading(tmp_path):
    module = _load_module()
    rows = _served_rows()
    rows[0]["m"][0]["x"] = 101
    config = _write_fixture(
        module, tmp_path, report=_canonical_report(), rows=rows,
    )
    module.REPORTS = tmp_path / "absent-reports"
    corpus = module.OUT_ROOT / "test-suite"
    before = {path.name: path.read_bytes() for path in corpus.iterdir()}

    with pytest.raises(ValueError, match="cannot preserve complete case corpus"):
        module.emit_suite("test-suite", config)
    assert {path.name: path.read_bytes() for path in corpus.iterdir()} == before


@pytest.mark.parametrize("index", [[], False, None, {"partial": True}, {"partial": "unknown"}])
def test_emitter_refuses_malformed_existing_index_without_deleting_cases(tmp_path, index):
    module = _load_module()
    config = _write_fixture(
        module, tmp_path, report=_canonical_report(), rows=_served_rows(),
    )
    module.REPORTS = tmp_path / "absent-reports"
    corpus = module.OUT_ROOT / "test-suite"
    (corpus / "index.json").write_text(json.dumps(index))
    before = {path.name: path.read_bytes() for path in corpus.iterdir()}

    with pytest.raises(ValueError, match="index must be an object|unsupported.*partial mode"):
        module.emit_suite("test-suite", config)
    assert {path.name: path.read_bytes() for path in corpus.iterdir()} == before


def test_case_artifact_check_accepts_exact_annotations_and_values(tmp_path):
    module = _load_module()
    config = _write_fixture(
        module,
        tmp_path,
        report=_canonical_report(),
        rows=_served_rows(),
    )

    problems, stats = module.check_suite_artifacts("test-suite", config)

    assert problems == []
    assert stats == {
        "cases": 2,
        "mismatches": 2,
        "annotated": 1,
        "silent": 0,
    }


def test_case_artifact_check_accepts_v1_chunk_descriptors(tmp_path):
    module = _load_module()
    config = _write_fixture(
        module,
        tmp_path,
        report=_canonical_report(),
        rows=_served_rows(),
        index_updates={
            "schema_version": "axiom_oracles.chunk_index.v1",
            "chunk_count": 1,
            "chunks": [
                {
                    "name": "chunk-0.json",
                    "sha256": "0" * 64,
                    "cases": 2,
                }
            ],
        },
    )

    problems, stats = module.check_suite_artifacts("test-suite", config)

    assert problems == []
    assert stats["cases"] == 2


def test_compact_case_preserves_exact_execution_inputs():
    module = _load_module()
    inputs = {"benefit#input.amount": 919999.9999999999, "benefit#input.flag": False}
    row = module.compact_case(
        {
            "case_id": "case-1",
            "matches": [{"concept": "benefit", "left": 1, "right": 1}],
            "mismatches": [],
            "metadata": {
                "axiom_entity": "Person",
                "axiom_entity_id": "recipient",
                "axiom_inputs": inputs,
            },
        },
        {},
    )

    assert row["execution"] == {
        "schema_version": "axiom_oracles.case_execution.v1",
        "axiom_entity": "Person",
        "axiom_entity_id": "recipient",
        "axiom_inputs": inputs,
    }


def test_case_artifact_check_rejects_silent_classification(tmp_path):
    module = _load_module()
    rows = _served_rows()
    rows[1]["m"][0]["e"] = "axiom_encoding_gap"
    config = _write_fixture(
        module,
        tmp_path,
        report=_canonical_report(),
        rows=rows,
    )

    problems, _ = module.check_suite_artifacts("test-suite", config)

    assert any("1 silent classifications" in problem for problem in problems)


def test_case_artifact_check_reports_missing_and_obsolete_rows(tmp_path):
    module = _load_module()
    rows = _served_rows()
    rows[1]["id"] = "obsolete-case"
    config = _write_fixture(
        module,
        tmp_path,
        report=_canonical_report(),
        rows=rows,
    )

    problems, _ = module.check_suite_artifacts("test-suite", config)

    assert any("canonical mismatch row(s) missing" in problem for problem in problems)
    assert any("obsolete served mismatch row(s)" in problem for problem in problems)


def test_case_artifact_check_rejects_chunk_and_index_drift(tmp_path):
    module = _load_module()
    report = _canonical_report()
    config = _write_fixture(
        module,
        tmp_path,
        report=report,
        rows=_served_rows(),
        index_updates={
            "count": 99,
            "engines": {"left": "axiom", "right": "policyengine"},
            "total_cases": 99,
        },
    )
    stale = module.OUT_ROOT / "test-suite" / "chunk-1.json"
    stale.write_text("[]")

    problems, _ = module.check_suite_artifacts("test-suite", config)

    assert any("chunk file set drift" in problem for problem in problems)
    assert any("index count" in problem for problem in problems)
    assert any("index engines drift" in problem for problem in problems)
    assert any("index total_cases" in problem for problem in problems)


def test_case_artifact_check_accepts_complete_mismatch_only_artifact(tmp_path):
    module = _load_module()
    report = _canonical_report()
    report["case_count"] = 10
    report["mismatches"][1]["case_id"] = "case-1"
    rows = _served_rows()[:1]
    rows[0]["m"].append(_served_rows()[1]["m"][0])
    config = _write_fixture(
        module,
        tmp_path,
        report=report,
        rows=rows,
        index_updates={"partial": "mismatch-only"},
    )

    problems, stats = module.check_suite_artifacts("test-suite", config)

    assert problems == []
    assert stats["mismatches"] == 2


def test_case_artifact_check_fails_closed_on_incomplete_canonical_list(tmp_path):
    module = _load_module()
    report = _canonical_report(mismatch_count=3)
    config = _write_fixture(
        module,
        tmp_path,
        report=report,
        rows=_served_rows(),
    )

    problems, stats = module.check_suite_artifacts("test-suite", config)

    assert stats == {}
    assert problems == [
        "test-suite: canonical mismatch list is incomplete (2/3); "
        "compact parity is uncheckable"
    ]


def test_served_delta_parity_accepts_either_faithful_convention():
    """PR #475 CI: two served-delta sign conventions coexist on main — this
    emitter writes right-minus-left (dashboard_delta) while Microcosm
    campaign artifacts (AL/MA/NC/SC/TN SNAP) serve the report's stored
    left-minus-right `difference`. The parity check must accept either
    (both are faithful projections of the same (l, x)) and reject anything
    else — otherwise whichever suite is being worked on silently redefines
    the contract for the rest."""
    import importlib.util
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "_eca", repo / "scripts" / "emit_case_artifacts.py"
    )
    eca = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(eca)
    report = {
        "mismatches": [
            {"case_id": "c1", "concept": "k", "left": 10.0, "right": 16.0, "difference": -6.0},
        ]
    }
    canonical, problems = eca._canonical_mismatch_payloads(report)
    assert not problems
    payload = canonical[("c1", "k")]
    assert payload["d"] == -6.0  # stored (left-minus-right)
    assert payload["d_alt"] == eca.dashboard_delta(10.0, 16.0)  # right-minus-left
    assert payload["d_alt"] == 6.0
    # a served row carrying either is parity-clean; a third value is drift
    for served_d, ok in ((-6.0, True), (6.0, True), (5.0, False), (None, False)):
        served = {("c1", "k"): {"l": 10.0, "x": 16.0, "d": served_d, "e": None}}
        drift = [
            key
            for key in served
            if any(canonical[key][f] != served[key][f] for f in ("l", "x"))
            or not (
                served[key]["d"] == canonical[key]["d"]
                or served[key]["d"] == canonical[key]["d_alt"]
            )
        ]
        assert (not drift) is ok, (served_d, drift)


OUTPUT_NAMES = [f"module#rule_{index}" for index in range(11)]
# Each case evaluates its own subset of rules (full evidence lists only what
# the engine evaluated), to a zero-like or a non-zero value.
CASE_OUTPUTS = st.lists(
    st.dictionaries(
        st.sampled_from(OUTPUT_NAMES),
        st.sampled_from([0, 0.0, False, None, True, 1, 250.5, -3]),
        max_size=len(OUTPUT_NAMES),
    ),
    min_size=1,
    max_size=6,
)


def _is_zero(value) -> bool:
    return value is None or value is False or value == 0


def _compact_rows(module, case_outputs):
    rows = [
        module.compact_case(
            {
                "case_id": f"case-{index}",
                "matches": [],
                "mismatches": [],
                "metadata": {"axiom_all_outputs": outputs},
            },
            {},
        )
        for index, outputs in enumerate(case_outputs)
    ]
    _, output_slots = module.finalize_slot_dictionaries(rows)
    return rows, output_slots


def _decode_zero_mask(mask: str, output_slots: list[str]) -> list[str]:
    return [
        name
        for index, name in enumerate(output_slots)
        if (int(mask[index // 4], 16) >> (3 - index % 4)) & 1
    ]


@settings(max_examples=200, deadline=None, derandomize=True)
@given(case_outputs=CASE_OUTPUTS)
def test_rows_record_exactly_their_own_zero_outputs(case_outputs):
    """A slot is non-zero (o), zero (oz) or unevaluated (neither) per case;
    the suite-wide slot union never turns an unevaluated rule into a zero."""

    module = _load_module()
    rows, output_slots = _compact_rows(module, case_outputs)

    assert output_slots == sorted(
        {name for outputs in case_outputs for name in outputs}
    )
    for row, outputs in zip(rows, case_outputs, strict=True):
        assert "_zero_output_names" not in row
        assert "_all_output_names" not in row
        zero = sorted(name for name, value in outputs.items() if _is_zero(value))
        non_zero = sorted(
            name for name, value in outputs.items() if not _is_zero(value)
        )
        assert [record["n"] for record in row.get("o", [])] == non_zero
        assert row.get("o0", 0) == len(zero)
        decoded = _decode_zero_mask(row["oz"], output_slots) if "oz" in row else []
        assert decoded == zero
        assert not (set(decoded) | set(non_zero)) - set(outputs)


@pytest.mark.skipif(shutil.which("node") is None, reason="node runtime not available")
def test_dashboard_decodes_the_python_zero_output_masks():
    module = _load_module()
    case_outputs = [
        {"module#rule_0": 0, "module#rule_3": 12.5, "module#rule_9": False},
        {"module#rule_3": 0, "module#rule_4": True},
        {name: 0 for name in OUTPUT_NAMES},
        {"module#rule_10": 7},
    ]
    rows, output_slots = _compact_rows(module, case_outputs)
    fixture = {
        "output_slots": output_slots,
        "cases": [
            {
                "row": row,
                "zero": sorted(
                    name for name, value in outputs.items() if _is_zero(value)
                ),
            }
            for row, outputs in zip(rows, case_outputs, strict=True)
        ],
    }
    proc = subprocess.run(
        ["node", "scripts/test-zero-outputs.mjs"],
        cwd=Path(__file__).parents[1] / "dashboard",
        env={**os.environ, "ZERO_OUTPUTS_FIXTURE": json.dumps(fixture)},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "ZERO OUTPUT MASKS: true" in proc.stdout


ROOT = Path(__file__).resolve().parents[1]
BUN = shutil.which("bun")
needs_bun = pytest.mark.skipif(BUN is None, reason="household helpers require Bun")


def _emit_household_fixture(module, directory: Path, report: dict) -> Path:
    """Exercise emit_suite, including its full-case versus fallback decision."""
    module.DASHBOARD_DATA = directory / "data"
    module.DASHBOARD_DATA.mkdir(parents=True)
    module.OUT_ROOT = module.DASHBOARD_DATA / "cases"
    module.REPORTS = directory / "absent-reports"
    (module.DASHBOARD_DATA / "snap-probe.json").write_text(json.dumps(report))
    assert "wrote snap-probe:" in module.emit_suite(
        "snap-probe", {"basename": "snap-probe"}
    )
    return module.OUT_ROOT / "snap-probe" / "chunk-0.json"


def _read_household_artifact(path: Path, *, include_delta=False):
    imports = "caseDisagreements, caseUncompared, caseUnexplainedCount"
    delta = ""
    if include_delta:
        imports += ", hasMismatchDelta"
        delta = """
  deltas: c.m.map(hasMismatchDelta),
  previousDeltas: c.m.map((m) => typeof m.d === "number" && m.d !== 0),
"""
    script = f"""
import {{ {imports} }} from "./dashboard/src/utils/caseMismatches.mjs";
const cases = await Bun.file(process.argv[1]).json();
console.log(JSON.stringify(cases.map((c) => ({{
  disagreements: caseDisagreements(c).length,
  uncompared: caseUncompared(c).length,
  unexplained: caseUnexplainedCount(c),
  {delta}
}}))));
"""
    proc = subprocess.run(
        [BUN, "-e", script, str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return json.loads(proc.stdout)


@needs_bun
def test_mismatch_only_emitter_preserves_uncompared_pairs_for_household_reader(tmp_path):
    from tests.test_native_snap_invalid_returns import produce, publish

    report = publish(produce([(None, True, 100.0, "holds")]))
    module = _load_module()
    full = _emit_household_fixture(module, tmp_path / "full", report)
    fallback = _emit_household_fixture(
        module, tmp_path / "fallback", {**report, "cases": []}
    )
    expected = [{"disagreements": 0, "uncompared": 1, "unexplained": 0}]
    assert _read_household_artifact(full) == expected
    assert _read_household_artifact(fallback) == expected
    index = json.loads(fallback.with_name("index.json").read_text())
    assert index["partial"] == "mismatch-only"


@needs_bun
def test_household_hides_delta_for_finite_failed_snap_comparison(tmp_path):
    from tests.test_native_snap_invalid_returns import produce, runner, through_csv

    rows = through_csv(produce([(200.0, True, 100.0, "holds")]))
    rows[0]["amount_compared"] = "False"
    rows[0]["errors"] = "[]"
    report = runner()._adapt_snap_ecps_csv_to_v2(
        rows, {"parameters": {"jurisdiction": "us-co"}}
    )
    path = _emit_household_fixture(_load_module(), tmp_path, report)
    [case] = json.loads(path.read_text())
    assert case["m"] == [
        {
            "c": "us:statutes/7/2014/u#snap_benefit",
            "l": 100.0,
            "x": 200.0,
            "d": 100.0,
            "u": True,
        }
    ]
    assert _read_household_artifact(path, include_delta=True) == [
        {
            "disagreements": 0,
            "uncompared": 1,
            "unexplained": 0,
            "deltas": [False],
            "previousDeltas": [True],
        }
    ]


@settings(max_examples=50, deadline=None, derandomize=True)
@given(flags=st.lists(st.booleans(), min_size=1, max_size=10))
def test_property_uncompared_flag_survives_both_compact_paths(flags):
    """Compacting changes neither a pair's comparison verdict nor legacy rows."""
    module = _load_module()
    mismatches = [
        {
            "case_id": "case-1",
            "concept": f"benefit-{index}",
            "left": 100,
            "right": 200,
            **({"uncompared": True} if flag else {}),
        }
        for index, flag in enumerate(flags)
    ]
    case = {"case_id": "case-1", "matches": [], "mismatches": mismatches}
    [fallback] = module.mismatch_only_rows({"mismatches": mismatches}, {})
    full = module.compact_case(case, {})
    assert fallback["m"] == full["m"]
    assert [m.get("u") is True for m in fallback["m"]] == flags
    for mismatch, flagged in zip(fallback["m"], flags, strict=True):
        if not flagged:
            assert "u" not in mismatch


@pytest.mark.parametrize("flag", [False, True])
def test_fiit_mismatch_only_rows_preserve_uncompared_flag(flag):
    [case] = _load_module().mismatch_only_rows(
        {
            "mismatches": [
                {
                    "entity_id": "person-1",
                    "surface": "employee-medicare",
                    "axiom": 0,
                    "policyengine": None if flag else 50,
                    "uncompared": flag,
                }
            ]
        },
        {},
    )
    assert (case["m"][0].get("u") is True) is flag


@needs_bun
@pytest.mark.parametrize("fallback", [False, True], ids=["full", "fallback"])
@pytest.mark.parametrize("finite_return", [0, 50], ids=["agreement", "disagreement"])
def test_native_fiit_errors_reach_household_reader_as_uncompared(
    tmp_path, fallback, finite_return,
):
    from tests.test_fiit_pattern_readers import fiit_report

    # FIIT enumerates only entities with diagnostic/mismatch rows. A clean
    # entity leaves the inline cases sparse and makes emit_suite use fallback.
    pairs = [(0, None)] if finite_return == 0 else [(0, finite_return), (0, None)]
    if fallback:
        pairs.insert(0, (0, 0))
    report = fiit_report(pairs)
    path = _emit_household_fixture(_load_module(), tmp_path, report)
    index = json.loads(path.with_name("index.json").read_text())
    assert index.get("partial") == ("mismatch-only" if fallback else None)
    expected = [] if finite_return == 0 else [
        {"disagreements": 1, "uncompared": 0, "unexplained": 1},
    ]
    expected.append({"disagreements": 0, "uncompared": 1, "unexplained": 0})
    assert _read_household_artifact(path) == expected


@needs_bun
def test_native_fiit_fallback_preserves_producer_comparison_status(tmp_path):
    from tests.test_native_fiit_missing_returns import produce

    raw, _ = produce(None, 0)
    path = _emit_household_fixture(_load_module(), tmp_path, raw)
    assert _read_household_artifact(path) == [
        {"disagreements": 0, "uncompared": 1, "unexplained": 0},
    ]


@settings(max_examples=24, deadline=None, derandomize=True)
@given(returns=st.lists(st.sampled_from([None, 0, 50]), min_size=1, max_size=8))
def test_property_native_fiit_comparison_status_survives_both_artifact_paths(returns):
    """Every retained native pair keeps its compared/uncompared disposition."""
    from tests.test_fiit_pattern_readers import fiit_report

    report = fiit_report([(0, right) for right in returns])
    module = _load_module()
    full = [module.compact_case(case, {}) for case in report["cases"]]
    fallback = module.mismatch_only_rows(report, {})
    assert [case["m"] for case in full] == [case["m"] for case in fallback]
    flags = [m.get("u") is True for case in full for m in case["m"]]
    assert flags == [right is None for right in returns if right != 0]
    assert sum(flags) == report["summary"]["uncompared_mismatches"]


@needs_bun
@settings(max_examples=15, deadline=None, derandomize=True)
@given(
    deltas=st.lists(
        st.tuples(st.integers(-100_000, 100_000), st.booleans()),
        min_size=1,
        max_size=10,
    )
)
def test_property_household_delta_requires_a_compared_pair(deltas):
    script = """
import { hasMismatchDelta } from "./dashboard/src/utils/caseMismatches.mjs";
const rows = await new Response(Bun.stdin.stream()).json();
console.log(JSON.stringify(rows.map(hasMismatchDelta)));
"""
    rows = [
        {"d": delta, **({"u": True} if uncompared else {})}
        for delta, uncompared in deltas
    ]
    result = subprocess.run(
        [BUN, "-e", script], cwd=ROOT, input=json.dumps(rows), capture_output=True,
        text=True, check=True, timeout=30,
    )
    assert json.loads(result.stdout) == [
        delta != 0 and not uncompared for delta, uncompared in deltas
    ]


@needs_bun
def test_household_delta_helper_preserves_unflagged_rendering():
    script = """
import { hasMismatchDelta } from "./dashboard/src/utils/caseMismatches.mjs";
const rows = [{}, ...[null, false, "100", 0, 100, -100, NaN, Infinity].map(
  (d) => ({ d }))];
console.log(JSON.stringify(rows.map((m) => ({
  before: typeof m.d === "number" && m.d !== 0,
  after: hasMismatchDelta(m),
}))));
"""
    result = subprocess.run(
        [BUN, "-e", script], cwd=ROOT, capture_output=True, text=True,
        check=True, timeout=30,
    )
    assert all(row["before"] == row["after"] for row in json.loads(result.stdout))
