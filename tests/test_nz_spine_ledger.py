"""Focused reproduction and coordinated-row-drop mutants for the NZ spine."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "closure" / "nz" / "spine-ledger.json"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "nz_spine_ledger_test", REPO / "scripts" / "nz_spine_ledger.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_full_spine_verifier_rejects_coordinated_dropped_row(tmp_path, monkeypatch):
    """MUTANT: a coherent count/hash edit cannot hide a dropped spine root."""

    module = _load_module()
    baseline = json.loads(LEDGER.read_text(encoding="utf-8"))
    module.validate_document(baseline)

    mutant = copy.deepcopy(baseline)
    removed = mutant["rows"].pop()
    mutant["counts"]["total"] -= 1
    mutant["counts"][removed["status"]] -= 1
    mutant["rowset_sha256"] = module._canonical_sha256(mutant["rows"])
    with pytest.raises(module.SpineLedgerError, match="exact 174-root set"):
        module.validate_document(mutant)

    output = tmp_path / "spine-ledger.json"
    output.write_text(module.render(baseline), encoding="utf-8")
    monkeypatch.setattr(module, "build_document", lambda **_kwargs: baseline)
    arguments = [
        "--check",
        "--output",
        str(output),
        "--rulespec-root",
        str(tmp_path),
        "--corpus-root",
        str(tmp_path),
        "--official-xml",
        str(tmp_path / "source.xml"),
        "--act-manifest",
        str(tmp_path / "manifest.json"),
    ]
    assert module.main(arguments) == 0
    output.write_text(module.render(mutant), encoding="utf-8")
    assert module.main(arguments) == 1
    output.write_text(module.render(baseline), encoding="utf-8")
    assert module.main(arguments) == 0
