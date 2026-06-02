import importlib.util
from pathlib import Path


def load_debug_env_module():
    module_path = Path(__file__).parents[1] / "scripts" / "debug_policyengine_env.py"
    spec = importlib.util.spec_from_file_location("debug_policyengine_env", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_debug_helpers_reexec_with_comparison_policyengine_pins(monkeypatch, tmp_path):
    debug_env = load_debug_env_module()
    calls = []
    script = tmp_path / "debug_gate.py"
    repo = tmp_path / "repo"

    monkeypatch.delenv("AXIOM_ORACLES_DEBUG_PINNED_PE", raising=False)
    monkeypatch.delenv("AXIOM_ORACLES_DEBUG_SKIP_PINNED_PE", raising=False)
    monkeypatch.setattr(debug_env.sys, "argv", [str(script), "--case-ids", "ecps-1"])

    def fake_execvpe(file, args, env):
        calls.append((file, args, env))
        raise RuntimeError("stop before exec")

    monkeypatch.setattr(debug_env.os, "execvpe", fake_execvpe)

    try:
        debug_env.ensure_pinned_policyengine_env(script, repo)
    except RuntimeError as exc:
        assert str(exc) == "stop before exec"

    file, args, env = calls[0]
    assert file == "uv"
    assert args[:5] == ["uv", "run", "--python", "3.14", "--no-project"]
    assert "--with-editable" in args
    assert str(repo) in args
    assert "policyengine==4.11.0" in args
    assert "policyengine-us==1.700.0" in args
    assert "policyengine-core==3.26.11" in args
    assert args[-3:] == [str(script), "--case-ids", "ecps-1"]
    assert env["AXIOM_ORACLES_DEBUG_PINNED_PE"] == "1"


def test_debug_helpers_do_not_reexec_after_pin_marker(monkeypatch, tmp_path):
    debug_env = load_debug_env_module()
    monkeypatch.setenv("AXIOM_ORACLES_DEBUG_PINNED_PE", "1")
    monkeypatch.setattr(
        debug_env.os,
        "execvpe",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("exec")),
    )

    debug_env.ensure_pinned_policyengine_env(
        tmp_path / "debug_gate.py",
        tmp_path / "repo",
    )
