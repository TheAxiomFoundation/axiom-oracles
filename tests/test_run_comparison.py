import importlib.util
import subprocess
from pathlib import Path


def load_run_comparison_module():
    module_path = Path(__file__).parents[1] / "scripts" / "run_comparison.py"
    spec = importlib.util.spec_from_file_location("run_comparison", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_resolve_path_uses_repo_env_override_when_config_path_is_missing(
    monkeypatch, tmp_path
):
    run_comparison = load_run_comparison_module()
    override = tmp_path / "axiom-encode"
    override.mkdir()
    monkeypatch.setenv("AXIOM_ENCODE_REPO", str(override))

    resolved = run_comparison._resolve_path(
        str(tmp_path / "missing-axiom-encode"), "axiom_encode_repo"
    )

    assert resolved == override.resolve()


def test_tax_ecps_runner_uses_current_python_and_policyengine_us(monkeypatch, tmp_path):
    run_comparison = load_run_comparison_module()
    axiom_encode = tmp_path / "axiom-encode"
    axiom_rules = tmp_path / "axiom-rules-engine"
    rulespec = tmp_path / "workspace" / "rulespec-us"
    axiom_encode.mkdir()
    axiom_rules.mkdir()
    rulespec.mkdir(parents=True)
    output = tmp_path / "report.json"
    calls = []

    monkeypatch.setattr(
        run_comparison, "_ensure_engine_binary", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        run_comparison, "_ensure_rulespec_us_checkout", lambda _remote: rulespec
    )

    def fake_run(cmd, *, check, stdout=None, cwd=None):
        del check, cwd
        calls.append(cmd)
        if stdout is not None:
            stdout.write("{}")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(run_comparison.subprocess, "run", fake_run)

    run_comparison._run_axiom_encode_tax_ecps_compare(
        {
            "axiom_encode_repo": str(axiom_encode),
            "axiom_rules_repo": str(axiom_rules),
            "rulespec_remote": "https://example.test/rulespec-us.git",
            "parameters": {
                "sample_size": 1000,
                "year": 2026,
                "surface": "all",
                "pinned": True,
            },
        },
        output,
    )

    cmd = calls[0]
    assert cmd[:4] == ["uv", "run", "--python", "3.14"]
    assert "--with-editable" in cmd
    assert str(axiom_encode.resolve()) in cmd
    assert "policyengine==4.4.4" in cmd
    assert "policyengine-us==1.705.1" in cmd
    assert "policyengine-core==3.26.0" in cmd
    assert "--allow-policyengine-us-version" in cmd
    assert "--allow-uncertified-policyengine-data" in cmd
    assert output.read_text() == "{}"


def test_tax_ecps_dashboard_adapter_maps_summary_and_cases():
    run_comparison = load_run_comparison_module()

    report = run_comparison._adapt_tax_ecps_to_v2(
        {
            "compared_tax_units": 2,
            "compared_values": 5,
            "mismatch_count": 1,
            "output_summary": [
                {
                    "surface": "ctc",
                    "output": "ctc_before_advance_payments",
                    "compared": 3,
                    "mismatches": 1,
                    "max_abs_diff": 50,
                    "max_relative_diff": 1,
                },
                {
                    "surface": "employee-oasdi",
                    "output": "employee_oasdi",
                    "compared": 2,
                    "mismatches": 0,
                    "max_abs_diff": 0,
                    "max_relative_diff": 0,
                },
            ],
            "mismatches": [
                {
                    "entity_id": "tax_unit_1",
                    "surface": "ctc",
                    "output": "ctc_before_advance_payments",
                    "axiom": 100,
                    "policyengine": 150,
                    "diff": -50,
                }
            ],
        },
        {},
        suite="fiit-ecps",
    )

    assert report["schema_version"] == "axiom.comparison_report.v2"
    assert report["suite"] == "fiit-ecps"
    assert report["summary"]["comparison_count"] == 5
    assert report["summary"]["mismatch_count"] == 1
    assert report["summary"]["mismatches_by_concept"] == [
        {"value": "us:tax/federal-income-tax#ctc", "count": 1}
    ]
    assert report["summary"]["mismatches_by_kind"] == [
        {"value": "amount_difference", "count": 1}
    ]
    assert report["aggregates"][0]["concept"] == "us:tax/federal-income-tax#liability"
    assert report["aggregates"][0]["match_rate"] == 80
    assert report["aggregates"][0]["left_weighted_sum"] is None
    assert report["aggregates"][1]["weighted_difference"] is None
    assert report["case_count"] == 2
    assert len(report["cases"]) == 1
    assert report["cases"][0]["metadata"]["entity_id"] == "tax_unit_1"
    assert report["mismatches"][0]["concept"] == "us:tax/federal-income-tax#ctc"
