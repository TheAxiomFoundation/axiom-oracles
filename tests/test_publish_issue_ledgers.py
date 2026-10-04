"""scripts/publish_issue_ledgers.py: the dashboard copies of the findings ledgers.

Invariants under test:

- The committed copies are current (the CI ``--check``), and the published
  file is never mistaken for a comparison report (no top-level ``suite``, not
  in manifest.json).
- Conservation: every source ledger entry appears in the bundle exactly once,
  verbatim, in registry order; a ledger-less model appears once with a note.
- ``--check`` fails on a missing copy, a stale source, an edited copy, a
  type-only edit (1 -> true) and a line-ending-only edit (LF -> CRLF).
- Fail closed: a ledger that breaks the licence lint is never written.
- Determinism and round-trip: building twice gives identical bytes, and the
  canonical serialization parses back to the document it encoded.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.euromod_coverage import load_euromod_issues
from axiom_oracles.southmod_issues import SOUTHMOD_MODELS, load_southmod_issues

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dashboard/public/data"


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "publish_issue_ledgers", ROOT / "scripts/publish_issue_ledgers.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """The script pointed at a scratch copy of its inputs and outputs."""
    module = _load_script()
    package = tmp_path / "data"
    package.mkdir()
    for path in (ROOT / "axiom_oracles/data").glob("*_issues.json"):
        shutil.copy(path, package / path.name)
    dashboard = tmp_path / "public"
    dashboard.mkdir()
    monkeypatch.setattr(module, "PACKAGE_DATA", package)
    monkeypatch.setattr(module, "DASHBOARD_DATA", dashboard)
    assert module.main([]) == 0
    return module, package, dashboard


def test_committed_copies_are_current(capsys) -> None:
    assert _load_script().main(["--check"]) == 0
    assert "current" in capsys.readouterr().out


def test_euromod_copy_is_the_packaged_ledger() -> None:
    published = (DATA / "euromod-issues.json").read_bytes()
    assert json.loads(published) == load_euromod_issues()
    assert published == _load_script().serialize(load_euromod_issues())


def test_bundle_conserves_every_entry_in_registry_order() -> None:
    bundle = json.loads((DATA / "southmod-issues.json").read_text())
    assert bundle["schema"] == "axiom_oracles.southmod_issues_bundle.v1"
    assert "suite" not in bundle
    assert [(m["region"], m["model"]) for m in bundle["models"]] == [
        (m.region, m.model) for m in SOUTHMOD_MODELS
    ]
    published_ids = []
    for model, published in zip(SOUTHMOD_MODELS, bundle["models"], strict=True):
        if model.ledger is None:
            assert published["ledger"] is None
            assert published["source"] is None
            assert published["note"] == model.no_ledger_note
            continue
        source = load_southmod_issues(model.region)
        assert published["source"] == f"axiom_oracles/data/{model.ledger}"
        assert published["ledger"] == source
        published_ids += [e["id"] for e in published["ledger"]["entries"]]
    source_ids = [
        e["id"]
        for m in SOUTHMOD_MODELS
        if m.ledger is not None
        for e in load_southmod_issues(m.region)["entries"]
    ]
    assert published_ids == source_ids
    assert len(set(published_ids)) == len(published_ids)


def test_published_ledgers_are_not_reports() -> None:
    manifest = json.loads((DATA / "manifest.json").read_text())
    for name in ("euromod-issues.json", "southmod-issues.json"):
        assert name not in manifest.get("reports", [])
        assert "suite" not in json.loads((DATA / name).read_text())


def test_fresh_tree_passes_check(tree) -> None:
    module, _, _ = tree
    assert module.main(["--check"]) == 0


def test_missing_copy_fails(tree, capsys) -> None:
    module, _, dashboard = tree
    (dashboard / "southmod-issues.json").unlink()
    assert module.main(["--check"]) == 1
    assert "southmod-issues.json missing" in capsys.readouterr().err


def test_stale_source_fails(tree, capsys) -> None:
    module, package, _ = tree
    path = package / "rwamod_issues.json"
    ledger = json.loads(path.read_text())
    ledger["updated_at"] = "2026-10-05"
    path.write_text(json.dumps(ledger, indent=2))
    assert module.main(["--check"]) == 1
    assert "southmod-issues.json is stale" in capsys.readouterr().err


def test_euromod_source_edit_fails(tree, capsys) -> None:
    module, package, _ = tree
    path = package / "euromod_issues.json"
    ledger = json.loads(path.read_text())
    ledger["entries"][0]["summary"] += " (edited)"
    path.write_text(json.dumps(ledger, indent=2))
    assert module.main(["--check"]) == 1
    assert "euromod-issues.json is stale" in capsys.readouterr().err


def test_type_only_edit_fails(tree) -> None:
    module, _, dashboard = tree
    path = dashboard / "southmod-issues.json"
    bundle = json.loads(path.read_text())
    entry = bundle["models"][0]["ledger"]["entries"][0]
    assert entry["counts_as_axiom_gap"] is False
    entry["counts_as_axiom_gap"] = 0  # equal under ==, different JSON
    path.write_bytes(module.serialize(bundle))
    assert module.main(["--check"]) == 1


def test_crlf_rewrite_fails(tree) -> None:
    module, _, dashboard = tree
    path = dashboard / "euromod-issues.json"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert module.main(["--check"]) == 1


def test_licence_violation_is_never_published(tree, capsys) -> None:
    module, package, dashboard = tree
    before = (dashboard / "southmod-issues.json").read_bytes()
    path = package / "etmod_issues.json"
    ledger = json.loads(path.read_text())
    ledger["entries"][0]["summary"] += " The tin_et policy applies $mat_rate."
    path.write_text(json.dumps(ledger, indent=1))
    assert module.main([]) == 1
    assert module.main(["--check"]) == 1
    err = capsys.readouterr().err
    assert "Refusing to publish" in err and "policy_or_unit" in err
    assert (dashboard / "southmod-issues.json").read_bytes() == before


def test_missing_registered_ledger_fails(tree, capsys) -> None:
    module, package, _ = tree
    (package / "etmod_issues.json").unlink()
    assert module.main(["--check"]) == 1
    assert "etmod_issues.json missing" in capsys.readouterr().err


def test_non_finite_number_is_never_published(tree, capsys) -> None:
    module, package, dashboard = tree
    before = (dashboard / "southmod-issues.json").read_bytes()
    path = package / "rwamod_issues.json"
    ledger = json.loads(path.read_text())
    ledger["entries"][0]["observed_with"]["reproduction_note"] = float("nan")
    path.write_text(json.dumps(ledger, indent=2))  # writes the NaN token
    assert module.main([]) == 1
    assert "non-finite" in capsys.readouterr().err
    assert (dashboard / "southmod-issues.json").read_bytes() == before
    with pytest.raises(ValueError):
        module.serialize({"x": float("inf")})


def test_unregistered_ledger_for_ledgerless_model_fails(tree, capsys) -> None:
    module, package, _ = tree
    model = next(m for m in SOUTHMOD_MODELS if m.ledger is None)
    (package / f"{model.model.lower()}_issues.json").write_text("{}")
    assert module.main(["--check"]) == 1
    assert "registers no ledger" in capsys.readouterr().err


def test_build_is_deterministic() -> None:
    module = _load_script()
    assert module.build_outputs() == module.build_outputs()


JSON = st.recursive(
    st.none()
    | st.booleans()
    | st.integers(-(2**53), 2**53)
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(),
    lambda children: (
        st.lists(children, max_size=4)
        | st.dictionaries(st.text(max_size=8), children, max_size=4)
    ),
    max_leaves=20,
)


@settings(max_examples=300, deadline=None)
@given(document=JSON)
def test_serialization_round_trips_and_is_type_strict(document) -> None:
    serialize = _load_script().serialize
    encoded = serialize(document)
    assert encoded.endswith(b"\n") and b"\r" not in encoded
    assert json.loads(encoded.decode("utf-8")) == document
    assert serialize(json.loads(encoded)) == encoded
