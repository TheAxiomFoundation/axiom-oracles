from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    path = (
        Path(__file__).parents[1]
        / "scripts"
        / "emit_disposition_artifacts.py"
    )
    spec = importlib.util.spec_from_file_location(
        "emit_disposition_artifacts", path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_disposition(root: Path, suite: str, *, mechanism: str) -> None:
    (root / f"{suite}.yaml").write_text(
        f"""\
schema: axiom_oracles.dispositions.v1
suite: {suite}
updated: "2026-07-27"
entries:
  - id: {suite}-case
    concept: benefit
    kind: amount_difference
    case_selector:
      case_ids: [case-1]
    disposition: bridge_artifact
    evidence:
      mechanism: {mechanism}
      arithmetic:
        - expression: 1 + 1
          equals: 2
"""
    )


def _isolated_module(tmp_path: Path, monkeypatch):
    module = _load_module()
    dispositions = tmp_path / "dispositions"
    output = tmp_path / "served"
    dispositions.mkdir()
    monkeypatch.setattr(module, "DISPOSITIONS", dispositions)
    monkeypatch.setattr(module, "OUT", output)
    return module, dispositions, output


def test_named_emit_and_check_are_targeted_and_exact(
    tmp_path, monkeypatch, capsys
):
    module, dispositions, output = _isolated_module(tmp_path, monkeypatch)
    _write_disposition(dispositions, "suite-a", mechanism="first")
    _write_disposition(dispositions, "suite-b", mechanism="second")

    assert module.main(["suite-a"]) == 0
    target = output / "suite-a.json"
    original = target.read_text()
    assert not (output / "suite-b.json").exists()
    assert json.loads(original) == {
        "suite": "suite-a",
        "updated": "2026-07-27",
        "entries": [
            {
                "id": "suite-a-case",
                "concept": "benefit",
                "kind": "amount_difference",
                "disposition": "bridge_artifact",
                "mechanism": "first",
                "cases": ["case-1"],
                "arithmetic": [{"expression": "1 + 1", "equals": 2}],
                "linked_issue": None,
            }
        ],
    }

    assert module.main(["--check", "suite-a"]) == 0
    assert target.read_text() == original
    assert "exact YAML parity" in capsys.readouterr().out


def test_check_rejects_semantically_equal_but_noncanonical_json(
    tmp_path, monkeypatch, capsys
):
    module, dispositions, output = _isolated_module(tmp_path, monkeypatch)
    _write_disposition(dispositions, "suite-a", mechanism="first")
    assert module.main(["suite-a"]) == 0
    target = output / "suite-a.json"
    target.write_text(json.dumps(json.loads(target.read_text())))
    stale = target.read_text()

    assert module.main(["--check", "suite-a"]) == 1
    assert target.read_text() == stale
    error = capsys.readouterr().err
    assert "suite-a" in error
    assert "is stale" in error


def test_check_fails_closed_for_missing_and_unknown_suites(
    tmp_path, monkeypatch, capsys
):
    module, dispositions, output = _isolated_module(tmp_path, monkeypatch)
    _write_disposition(dispositions, "suite-a", mechanism="first")

    assert module.main(["--check", "suite-a"]) == 1
    assert not output.exists()
    missing_error = capsys.readouterr().err
    assert "suite-a" in missing_error
    assert "is missing" in missing_error

    assert module.main(["--check", "unknown-suite"]) == 1
    unknown_error = capsys.readouterr().err
    assert "unknown-suite: no dispositions/unknown-suite.yaml" in unknown_error


def test_invalid_suite_slug_cannot_escape_dispositions_directory(
    tmp_path, monkeypatch, capsys
):
    module, _, output = _isolated_module(tmp_path, monkeypatch)

    assert module.main(["--check", "../outside"]) == 1
    assert not output.exists()
    assert "invalid suite slug '../outside'" in capsys.readouterr().err
