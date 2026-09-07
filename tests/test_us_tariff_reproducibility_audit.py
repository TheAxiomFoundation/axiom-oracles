import hashlib
from pathlib import Path

from scripts import audit_us_tariff_reproducibility as audit


def test_large_file_never_reads_bytes(tmp_path, monkeypatch):
    source = tmp_path / "large"
    source.write_bytes(b"12345")
    monkeypatch.setattr(audit, "MAX_HASH_BYTES", 4)
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda _: (_ for _ in ()).throw(AssertionError("must not read large data")),
    )
    assert audit.inspect_file(source, {"sha256": "unverified"}) == {
        "status": "present_not_rehashed_large",
        "actual_bytes": 5,
    }


def test_hash_drift_and_size_drift_are_distinct(tmp_path):
    source = tmp_path / "small"
    source.write_bytes(b"123")
    expected = {"bytes": 3, "sha256": hashlib.sha256(b"123").hexdigest()}
    assert audit.inspect_file(source, expected)["status"] == "sha256_match"
    source.write_bytes(b"456")
    assert audit.inspect_file(source, expected)["status"] == "sha256_mismatch"
    source.write_bytes(b"12")
    assert audit.inspect_file(source, expected)["status"] == "size_mismatch"
    source.unlink()
    assert audit.inspect_file(source, expected)["status"] == "missing"


def test_project_roots_are_explicit():
    roots = dict(repo=Path("oracles"), rulespec=Path("rulespec"), yale=Path("yale"))
    assert audit.root_for("tools/b16_entry_flags.py", **roots) == (
        "rulespec-us",
        Path("rulespec/tools/b16_entry_flags.py"),
    )
    assert audit.root_for("scripts/parse_annex_products.R", **roots)[0] == "yale"
    assert (
        audit.root_for("scripts/build_us_tariff_boundary_evidence.py", **roots)[0]
        == "axiom-oracles"
    )
