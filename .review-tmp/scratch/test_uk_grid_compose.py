import json, subprocess, sys
from pathlib import Path
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests"))
from test_run_comparison import load_run_comparison_module  # noqa: E402

REPORT = "axiom-policyengine-uk-vat.json"


def _setup(monkeypatch, tmp_path, rc):
    committed = REPO / "dashboard/public/data" / REPORT
    dash = tmp_path / "dash"
    dash.mkdir()
    (dash / REPORT).write_bytes(committed.read_bytes())
    (dash / "manifest.json").write_text(json.dumps({"reports": [REPORT]}) + "\n")
    monkeypatch.setattr(rc, "DASHBOARD_DATA_DIR", dash)

    def boom(cmd, *a, **k):
        if any("generate_uk_vat.py" in str(c) for c in cmd):
            raise subprocess.CalledProcessError(1, cmd)
        return subprocess.run.__wrapped__(cmd, *a, **k) if hasattr(subprocess.run, "__wrapped__") else real_run(cmd, *a, **k)

    real_run = subprocess.run
    monkeypatch.setattr(rc.subprocess, "run", lambda cmd, *a, **k: (_ for _ in ()).throw(subprocess.CalledProcessError(1, cmd)) if any("generate_uk_vat.py" in str(c) for c in cmd) else real_run(cmd, *a, **k))
    monkeypatch.setenv("AXIOM_ORACLES_RUN_KIND", "affected-rerun")
    return dash, committed.read_bytes()


def test_uk_grid_marked_fallback_preserves_real_report(monkeypatch, tmp_path, capsys):
    rc = load_run_comparison_module()
    dash, before = _setup(monkeypatch, tmp_path, rc)
    out = tmp_path / "reports"
    monkeypatch.setattr("sys.argv", ["run_comparison.py", "uk-vat", "--output-dir", str(out)])
    assert rc.main() == 0
    assert (dash / REPORT).read_bytes() == before
    (published,) = out.glob("axiom-policyengine-uk-vat-*.json")
    prov = json.loads(published.read_text())["provenance"]
    assert prov["reemitted_report"] is True
    assert all(e.get("sha") is None for e in prov.get("rulespecs") or [])
    assert "a re-emission never replaces a real run" in capsys.readouterr().out


def test_uk_grid_require_live_still_refuses(monkeypatch, tmp_path):
    rc = load_run_comparison_module()
    dash, before = _setup(monkeypatch, tmp_path, rc)
    out = tmp_path / "reports"
    monkeypatch.setattr("sys.argv", ["run_comparison.py", "uk-vat", "--require-live", "--output-dir", str(out)])
    with pytest.raises(SystemExit) as exc:
        rc.main()
    assert "--require-live" in str(exc.value)
    assert (dash / REPORT).read_bytes() == before
    assert not list(out.glob("axiom-policyengine-uk-vat-*.json"))


def test_snap_qc_require_live_still_refuses(monkeypatch, tmp_path):
    rc = load_run_comparison_module()
    committed = REPO / "dashboard/public/data/axiom-snapqc-ny-snap.json"
    dash = tmp_path / "dash"; dash.mkdir()
    (dash / committed.name).write_bytes(committed.read_bytes())
    monkeypatch.setattr(rc, "DASHBOARD_DATA_DIR", dash)
    monkeypatch.setattr(rc, "_snap_qc_skip_reason", lambda *_a, **_k: "no engine here")
    out = tmp_path / "reports"
    monkeypatch.setattr("sys.argv", ["run_comparison.py", "ny-snap-qc", "--require-live", "--output-dir", str(out)])
    with pytest.raises(SystemExit):
        rc.main()
    assert (dash / committed.name).read_bytes() == committed.read_bytes()
    assert not list(out.glob("axiom-snapqc-ny-snap-*.json"))
