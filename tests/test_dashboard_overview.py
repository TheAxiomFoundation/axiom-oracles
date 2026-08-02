"""generate_dashboard_overview.py --check must compare bundle CONTENT.

Sol stack review r4: the committed overview bundle carried a superseded
dispositioned block because the checker compared only source file sizes —
a regenerated panel report that happened to be byte-length-identical to
its predecessor slipped past `--check` while the UI preferentially
consumes the stale bundle. The check now requires the committed bundle to
equal a fresh rebuild of the committed reports exactly.
"""

import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    path = Path(__file__).parents[1] / "scripts" / "generate_dashboard_overview.py"
    spec = importlib.util.spec_from_file_location("generate_dashboard_overview", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _seed(tmp_path: Path, monkeypatch):
    module = _load_module()
    data = tmp_path / "dashboard" / "public" / "data"
    data.mkdir(parents=True)
    (data / "manifest.json").write_text(json.dumps({"reports": ["a.json"]}))
    (data / "a.json").write_text(
        json.dumps(
            {
                "suite": "example-suite",
                "summary": {"match_rate": 0.61, "mismatch_count": 1},
                "cases": [{"case_id": "c1"}],
            }
        )
    )
    monkeypatch.setattr(module, "DATA", data)
    monkeypatch.setattr(module, "OUT", data / "overview.json")
    return module, data


def _run(module, monkeypatch, *args: str) -> int:
    monkeypatch.setattr(sys, "argv", ["generate_dashboard_overview.py", *args])
    return module.main()


def test_fresh_bundle_passes_check(tmp_path, monkeypatch):
    module, data = _seed(tmp_path, monkeypatch)
    assert _run(module, monkeypatch) == 0
    assert _run(module, monkeypatch, "--check") == 0
    bundle = json.loads((data / "overview.json").read_text())
    # cases are stripped; sources carry content hashes, not sizes
    assert bundle["reports"][0].get("cases") is None
    assert all(len(v) == 64 for v in bundle["sources"].values())


def test_size_preserving_report_edit_fails_check(tmp_path, monkeypatch):
    """The exact r4 shape: report content changes, byte length does not."""
    module, data = _seed(tmp_path, monkeypatch)
    assert _run(module, monkeypatch) == 0

    original = (data / "a.json").read_text()
    mutated = original.replace('"match_rate": 0.61', '"match_rate": 0.16')
    assert mutated != original and len(mutated) == len(original)
    (data / "a.json").write_text(mutated)

    assert _run(module, monkeypatch, "--check") == 1
    # regeneration clears it
    assert _run(module, monkeypatch) == 0
    assert _run(module, monkeypatch, "--check") == 0


def test_edited_bundle_itself_fails_check(tmp_path, monkeypatch):
    module, data = _seed(tmp_path, monkeypatch)
    assert _run(module, monkeypatch) == 0
    out = data / "overview.json"
    bundle = json.loads(out.read_text())
    bundle["reports"][0]["summary"]["match_rate"] = 0.16
    out.write_text(json.dumps(bundle, sort_keys=True) + "\n")
    assert _run(module, monkeypatch, "--check") == 1


def test_numeric_to_boolean_bundle_edit_fails_check(tmp_path, monkeypatch):
    """Python's `1 == True`: parsed-value equality accepted a type-only
    bundle edit (sol stack review r5). The byte-exact check must not."""
    module, data = _seed(tmp_path, monkeypatch)
    assert _run(module, monkeypatch) == 0
    out = data / "overview.json"
    text = out.read_text()
    mutated = text.replace('"mismatch_count": 1', '"mismatch_count": true')
    assert mutated != text
    out.write_text(mutated)
    # the parsed values still compare equal — the defective pre-r5 check
    assert json.loads(mutated) == json.loads(text)
    assert _run(module, monkeypatch, "--check") == 1


def test_crlf_bundle_edit_fails_check(tmp_path, monkeypatch):
    """Text-mode reads apply universal-newline translation, so a
    `read_text()` comparison accepted a terminal LF -> CRLF rewrite of the
    bundle (sol stack review r6). The comparison must be over raw bytes."""
    module, data = _seed(tmp_path, monkeypatch)
    assert _run(module, monkeypatch) == 0
    out = data / "overview.json"
    raw = out.read_bytes()
    assert raw.endswith(b"\n") and not raw.endswith(b"\r\n")
    mutated = raw[:-1] + b"\r\n"
    out.write_bytes(mutated)
    # parsed equality holds AND a text-mode read normalizes the CRLF away —
    # both defective pre-r6 comparisons would accept this mutant
    assert json.loads(mutated) == json.loads(raw)
    assert out.read_text() == raw.decode("utf-8")
    assert _run(module, monkeypatch, "--check") == 1


def test_missing_bundle_fails_check(tmp_path, monkeypatch):
    module, _ = _seed(tmp_path, monkeypatch)
    assert _run(module, monkeypatch, "--check") == 1
