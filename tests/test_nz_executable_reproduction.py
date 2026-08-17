"""Hermetic mutants for the NZ executable receipt."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "nz_executable_reproduction.py"
RECEIPT = (
    REPO_ROOT / "conformance" / "executable" / "nz-treasury-incomeexplorer.json"
)


def _load_script():
    spec = importlib.util.spec_from_file_location("nz_executable_reproduction", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_nz_executable_receipt_validates_hermetically():
    module = _load_script()
    summary = module.validate_artifact(json.loads(RECEIPT.read_text()))

    assert summary["program_count"] == 7
    assert summary["request_count"] == 19
    assert summary["comparison_cell_count"] == 22
    assert summary["all_golden_outputs_reproduced"] is True
    assert all(row["executable"] for row in summary["programs"].values())


def test_compiled_artifact_bytes_must_match_recorded_digest(tmp_path, monkeypatch):
    module = _load_script()
    mutant = tmp_path / "compiled-program.json"
    mutant.write_bytes(module.ARTIFACT_PATH.read_bytes() + b" ")
    monkeypatch.setattr(module, "ARTIFACT_PATH", mutant)

    with pytest.raises(ValueError, match="compiled artifact bytes drifted"):
        module.validate_artifact(json.loads(RECEIPT.read_text()))


def test_transcript_digest_is_bound_into_receipt():
    module = _load_script()
    mutant = copy.deepcopy(json.loads(RECEIPT.read_text()))
    mutant["transcript"]["sha256"] = "0" * 64

    with pytest.raises(ValueError, match="not derived from committed artifacts"):
        module.validate_artifact(mutant)


def test_transcript_match_is_rederived_from_golden_outputs():
    module = _load_script()
    requests = module._load(module.REQUESTS_PATH)
    golden = module._load(module.GOLDEN_PATH)
    golden_by_id = module._validate_golden(
        golden, requests, module._load(module.SOURCE_REPORT_PATH)
    )
    transcript = module._load(module.TRANSCRIPT_PATH)
    mutant = copy.deepcopy(transcript)
    row = mutant["requests"][0]
    output = next(iter(row["outputs"].values()))
    output["value"]["value"] = "999999"

    with pytest.raises(ValueError, match="golden_match is not derived"):
        module._validate_transcript(mutant, requests, golden_by_id)
