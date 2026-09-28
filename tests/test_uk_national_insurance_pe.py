"""uk-national-insurance-pe: committed report invariants and mechanism attribution.

Properties checked on the committed report (no PolicyEngine or engine run):

* Differential: every Axiom value equals an independent statutory computation
  (SSCBA 1992 s.15(3), regulation 100 with no Class 1/2, the Class 1 pipeline's
  12,570 / 50,270 thresholds), so the engine and a plain-arithmetic reference
  agree on every row.
* Freeze invariance: Axiom's figures for the same income are identical in every
  tax year 2026-27 to 2030-31.
* Monotonicity and bounds of the statutory schedules.
* Every mismatch reconciles to a named PolicyEngine mechanism, and the
  dispositions file is exactly what the builder produces from the report.

Plus a deterministic sweep of ``classify_mechanism`` over synthetic incomes and
limits, checking that it attributes only what reconciles.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT = REPO_ROOT / "dashboard" / "public" / "data" / "axiom-policyengine-uk-national-insurance.json"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


generator = _load("generate_uk_national_insurance_pe")
builder = _load("build_uk_national_insurance_pe_dispositions")

LPL, UPL, PT, UEL = 12570, 50270, 12570, 50270


@pytest.fixture(scope="module")
def report() -> dict:
    return json.loads(REPORT.read_text())


def _statutory(
    measure: str,
    income: float,
    limits: tuple[float, float] = (LPL, UPL),
    class_1_main: float = 0.0,
) -> float:
    lower, upper = limits
    if measure == "c1-main":
        return 0.08 * max(0.0, min(income, UEL) - PT)
    if measure == "c1-additional":
        return 0.02 * max(0.0, income - UEL)
    if measure == "c2":
        return 0.0
    main = 0.06 * max(0.0, min(income, upper) - lower)
    before_maximum = main + 0.02 * max(0.0, income - upper)
    # Regulation 100 (no Class 2): step four is the main-band Class 4 at the
    # limits less the primary Class 1 at the main percentage; case 1 when it
    # exceeds that Class 1 plus the main-rate Class 4, else steps 4 + 8 + 9.
    step_four_value = 0.06 * (upper - lower) - class_1_main
    step_four = max(0.0, step_four_value)
    if step_four_value > 0 and step_four_value > class_1_main + main:
        maximum = step_four
    else:
        step_seven = max(0.0, (min(upper, income) - lower) - step_four / 0.06)
        maximum = step_four + 0.02 * step_seven + 0.02 * max(0.0, income - upper)
    if measure == "c4-main":
        return main
    if measure == "c4-maximum":
        return maximum
    return min(before_maximum, maximum)


def test_every_axiom_value_matches_the_statutory_reference(report: dict) -> None:
    # 5 tax years x (8 Class 1 x 2 + 8 Class 4 x 4) + 4 isolation cases x 2.
    # + 4 dual-earner cases x 3.
    assert report["case_count"] == len(report["cases"]) == 5 * (16 + 32) + 8 + 12
    for row in report["cases"]:
        limits = tuple(row.get("supplied_profits_limits") or (LPL, UPL))
        expected = _statutory(
            row["measure"],
            float(row["compared_income"]),
            limits,
            float(row.get("axiom_class_1_main", 0.0)),
        )
        assert row["axiom"] == pytest.approx(expected, abs=0.005), row["case_id"]


def test_axiom_figures_are_frozen_across_2026_27_to_2030_31(report: dict) -> None:
    by_key: dict[tuple, set] = defaultdict(set)
    for row in report["cases"]:
        if row["scenario"] in ("class-4-float32-isolation", "class-4-dual-earner"):
            continue
        if row["measure"].startswith("c1-"):
            # PolicyEngine's earnings base (the compared income) differs by
            # year; the freeze invariant is on the schedule, so key on it.
            key = (row["measure"], round(float(row["compared_income"]), 6))
        else:
            key = (row["measure"], row["income"])
        by_key[key].add(round(float(row["axiom"]), 6))
    class_4 = {k: v for k, v in by_key.items() if not k[0].startswith("c1-")}
    assert class_4, "no Class 4 rows"
    for key, values in class_4.items():
        assert len(values) == 1, f"{key} varies by year: {sorted(values)}"
    years = {row["validation_year"] for row in report["cases"]}
    assert years == {2026, 2027, 2028, 2029, 2030}


def test_schedules_are_monotone_and_bounded(report: dict) -> None:
    series: dict[tuple, list[tuple[float, float]]] = defaultdict(list)
    for row in report["cases"]:
        if row["scenario"] in ("class-4-float32-isolation", "class-4-dual-earner"):
            continue
        series[(row["validation_year"], row["measure"])].append(
            (float(row["compared_income"]), float(row["axiom"]))
        )
    caps = {"c1-main": 0.08 * (UEL - PT), "c4-main": 0.06 * (UPL - LPL)}
    for (year, measure), points in series.items():
        points.sort()
        values = [v for _, v in points]
        assert all(v >= 0 for v in values), (year, measure)
        assert values == sorted(values), f"{measure} not monotone in {year}"
        if measure in caps:
            assert max(values) <= caps[measure] + 1e-6, (year, measure)


def test_2026_27_control_year_matches_and_every_mismatch_is_attributed(report: dict) -> None:
    mismatches = report["mismatches"]
    assert mismatches, "expected the pinned PolicyEngine-UK to diverge from 2027-28"
    # 2026-27 single earners match; its only mismatches are dual earners.
    assert all(
        m["validation_year"] != 2026 or m["pe_mechanism"] == "class_1_deducted_from_class_4_profits"
        for m in mismatches
    )
    assert {m["pe_mechanism"] for m in mismatches} <= {
        "cpi_uprated_thresholds",
        "float32_drops_additional_band",
        "class_1_deducted_from_class_4_profits",
    }
    dispositioned = report["summary"]["dispositioned"]
    assert dispositioned["unexplained_count"] == 0
    assert dispositioned["counts"]["upstream_engine_gap"] == len(mismatches)
    assert dispositioned["expired_entries"] == []
    assert dispositioned["orphaned_entries"] == []


def test_mechanism_arithmetic_reproduces_every_mismatch_row(report: dict) -> None:
    from axiom_oracles.comparison.dispositions import evaluate_arithmetic

    for row in report["mismatches"]:
        axiom_expr, pe_expr = builder._expressions(row)
        assert evaluate_arithmetic(axiom_expr) == pytest.approx(row["left"], abs=0.005), row[
            "case_id"
        ]
        assert evaluate_arithmetic(pe_expr) == pytest.approx(row["right"], abs=0.005), row[
            "case_id"
        ]


def test_dispositions_file_is_the_builder_output() -> None:
    committed = (REPO_ROOT / "dispositions" / "uk-national-insurance-pe.yaml").read_text()
    rebuilt = builder.HEADER + yaml.safe_dump(
        builder.build(), sort_keys=False, width=100, allow_unicode=True
    )
    assert committed == rebuilt
    entries = yaml.safe_load(committed)["entries"]
    for entry in entries:
        assert entry["disposition"] == "upstream_engine_gap"
        assert entry["expires_on_source_change"] is True
        assert entry["linked_issue"].startswith("https://github.com/PolicyEngine/policyengine-uk/issues/")
        # Org rule: a PolicyEngine attribution cites the Axiom legal id and a test.
        sources = entry["evidence"]["sources"]
        assert any(s.endswith(".test.yaml") for s in sources), entry["id"]
        assert any(s.endswith(".yaml") and not s.endswith(".test.yaml") for s in sources)


def _sweep():
    """Deterministic synthetic (income, limits) cases for the classifier."""

    for i, income in enumerate(
        [5000, 12570, 20000.5, 45678.9, 50270, 52301, 65432, 98765.43, 131071.37, 300000]
    ):
        for j, (lower, upper) in enumerate(
            [(12570, 50270), (12821.380164235901, 51275.32067272385), (13606.11, 54413.63)]
        ):
            yield income, lower, upper, i * 3 + j


@pytest.mark.parametrize("income,lower,upper,seed", list(_sweep()))
def test_classifier_attributes_only_what_reconciles(income, lower, upper, seed) -> None:
    case = generator.NICase(f"sweep-{seed}", 2028, "class_4", income, "sweep")
    params = {
        "primary_threshold_weekly": 246.56,
        "upper_earnings_limit_weekly": 986.06,
        "lower_profits_limit": lower,
        "upper_profits_limit": upper,
        "main_class_4_percentage": 0.06,
        "additional_class_4_percentage": 0.02,
    }
    for measure in ("c4-main", "c4-maximum", "c4-total"):
        expected = generator._pe_expected(case, measure, params, income)
        statute = _statutory(measure, income)
        correct = expected["correct"]
        # A PolicyEngine value equal to its own correct formula is attributed to
        # the thresholds exactly when it differs from the statute.
        got = generator.classify_mechanism(case, measure, statute, correct, params, income)
        if abs(statute - correct) > 0.01:
            assert got == "cpi_uprated_thresholds"
        else:
            assert got == "unreconciled"
        # A value matching neither mechanism is never attributed.
        off = generator.classify_mechanism(case, measure, statute, correct + 7.77, params, income)
        if "main_only" not in expected or abs(expected["main_only"] - (correct + 7.77)) > 0.01:
            assert off == "unreconciled"
        # The float32 attribution needs profits at or above the upper limit
        # (where case 2 exceeds step four) and a value equal to step four.
        if "main_only" in expected:
            flipped = generator.classify_mechanism(
                case, measure, statute, expected["main_only"], params, income
            )
            if abs(correct - expected["main_only"]) > 0.01:
                assert income > upper
                assert flipped == "float32_drops_additional_band"


# --- Review round 1: attribution must require the Axiom side to be statutory. ---

_PE_2027 = {
    "primary_threshold_weekly": 241.73,
    "upper_earnings_limit_weekly": 966.73,
    "lower_profits_limit": 12821.380164235901,
    "upper_profits_limit": 51275.32067272385,
    "main_class_4_percentage": 0.06,
    "additional_class_4_percentage": 0.02,
}
_PE_STATUTORY = {**_PE_2027, "lower_profits_limit": 12570.0, "upper_profits_limit": 50270.0}


@pytest.mark.parametrize("error", [54.2, -0.5, 100.0])
def test_an_axiom_error_is_never_attributed_to_policyengine(error) -> None:
    case = generator.NICase("t", 2027, "class_4", 30000, "t")
    for key in ("c4-main", "c4-maximum", "c4-total"):
        statute = generator.statutory_value(case, key, 30000)
        pe_correct = generator._pe_expected(case, key, _PE_2027, 30000)["correct"]
        assert (
            generator.classify_mechanism(case, key, statute, pe_correct, _PE_2027, 30000)
            == "cpi_uprated_thresholds"
        )
        wrong = statute + error
        assert (
            generator.classify_mechanism(case, key, wrong, pe_correct, _PE_2027, 30000)
            == "unreconciled"
        )


def test_no_threshold_attribution_when_policyengine_uses_the_statutory_limits() -> None:
    # The reviewer's case: unchanged limits, correct PE 1,045.80, wrong Axiom 1,100.
    case = generator.NICase("t", 2026, "class_4", 30000, "t")
    assert (
        generator.classify_mechanism(case, "c4-main", 1100.0, 1045.8, _PE_STATUTORY, 30000)
        == "unreconciled"
    )
    # A wrong Axiom Class 2 amount is never a PolicyEngine threshold defect.
    assert (
        generator.classify_mechanism(case, "c2", 12.5, 0.0, _PE_2027, 30000) == "unreconciled"
    )


def test_dual_attribution_requires_statutory_axiom() -> None:
    case = generator.NICase("t", 2026, "dual", 20000, "t", employment=30000)
    pe_model = generator._pe_dual_model(20000, 1394.4, 1394.4, _PE_STATUTORY)["c4-main"]
    statute = generator.statutory_value(case, "c4-main", 20000, 1394.4)
    assert (
        generator.classify_dual_mechanism(
            case, "c4-main", statute, pe_model, _PE_STATUTORY, 1394.4, 1394.4, 1394.4
        )
        == "class_1_deducted_from_class_4_profits"
    )
    assert (
        generator.classify_dual_mechanism(
            case, "c4-main", statute + 20, pe_model, _PE_STATUTORY, 1394.4, 1394.4, 1394.4
        )
        == "unreconciled"
    )


def test_builder_refuses_a_corrupted_non_representative_row(tmp_path, monkeypatch) -> None:
    report = json.loads(REPORT.read_text())
    groups = defaultdict(list)
    for row in report["mismatches"]:
        groups[(row["validation_year"], row["measure"], row["pe_mechanism"])].append(row)
    rows = next(g for g in groups.values() if len(g) > 1)
    victim = sorted(rows, key=lambda r: r["case_id"])[-1]
    victim["right"] = float(victim["right"]) + 3.0
    corrupted = tmp_path / "report.json"
    corrupted.write_text(json.dumps(report))
    monkeypatch.setattr(builder, "REPORT", corrupted)
    with pytest.raises(SystemExit, match=victim["case_id"]):
        builder.build()


def test_module_parameters_honour_effective_to(tmp_path, monkeypatch) -> None:
    module = tmp_path / "uk" / "m.yaml"
    module.parent.mkdir(parents=True)
    module.write_text(
        yaml.safe_dump(
            {
                "rules": [
                    {
                        "name": "limit",
                        "kind": "parameter",
                        "versions": [
                            {"effective_from": "2026-04-06", "formula": "100"},
                            {
                                "effective_from": "2027-04-06",
                                "effective_to": "2028-04-05",
                                "formula": "200",
                            },
                        ],
                    },
                    {
                        "name": "expired",
                        "kind": "parameter",
                        "versions": [
                            {
                                "effective_from": "2026-04-06",
                                "effective_to": "2027-04-05",
                                "formula": "1",
                            }
                        ],
                    },
                ]
            }
        )
    )
    monkeypatch.setattr(generator, "RULESPEC_UK", tmp_path)
    with pytest.raises(SystemExit, match="expired"):
        generator._module_parameters("uk/m.yaml", "2028-04-06")
    module_doc = yaml.safe_load(module.read_text())
    module_doc["rules"] = module_doc["rules"][:1]
    module.write_text(yaml.safe_dump(module_doc))
    assert generator._module_parameters("uk/m.yaml", "2027-04-06")["limit"] == 200
    # After the temporary version expires, the open-ended one applies again.
    assert generator._module_parameters("uk/m.yaml", "2028-04-06")["limit"] == 100
