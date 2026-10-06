"""Universe discovery keeps the threshold decision ledger out of scoreboards."""

from pathlib import Path

import pytest

from scripts import conformance_scoreboard as scoreboard


def test_reserved_ledgers_are_not_policy_universes(tmp_path, monkeypatch):
    names = (
        "ratchet.yaml",
        "unexplained-ratchet.yaml",
        "threshold-straddle-exemptions.yaml",
        "us-pe.yaml",
    )
    for name in names:
        (tmp_path / name).write_text("schema_version: 1\nexemptions: []\n")
    monkeypatch.setattr(scoreboard, "CONFORMANCE_DIR", tmp_path)
    assert scoreboard._universe_paths() == [tmp_path / "us-pe.yaml"]


def test_unknown_universe_schema_still_fails_closed(tmp_path, monkeypatch):
    candidate = tmp_path / "new-jurisdiction.yaml"
    candidate.write_text("schema: unknown\n")
    monkeypatch.setattr(scoreboard, "CONFORMANCE_DIR", tmp_path)
    assert scoreboard._universe_paths() == [candidate]
    with pytest.raises(ValueError, match="expected schema"):
        scoreboard.parse_universe(Path(candidate))
