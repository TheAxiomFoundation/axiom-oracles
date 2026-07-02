"""The committed EUROMOD country-readiness matrix stays well-formed."""

from __future__ import annotations

import json
from pathlib import Path

MATRIX = (
    Path(__file__).parents[1]
    / "axiom_oracles"
    / "data"
    / "euromod_country_readiness.json"
)

KNOWN_STATUSES = {
    "ok_training_name",
    "ok_real_config_workaround",
    "no_training_data",
    "fails",
    "load_error",
}


def test_matrix_parses_with_provenance_and_valid_statuses() -> None:
    payload = json.loads(MATRIX.read_text())
    assert payload["model_release"].startswith("EUROMOD_RELEASES_")
    assert payload["probed"]
    countries = payload["countries"]
    assert len(countries) >= 27  # every EU member state (plus variants)
    for code, entry in countries.items():
        assert len(code) == 2 and code.isupper()
        assert entry["status"] in KNOWN_STATUSES
        if entry["status"] == "ok_real_config_workaround":
            # the workaround requires both names
            assert entry["run_dataset"] and entry["run_dataset"] != entry[
                "training_dataset"
            ]


def test_every_probed_country_is_currently_runnable() -> None:
    payload = json.loads(MATRIX.read_text())
    not_runnable = {
        code: entry["status"]
        for code, entry in payload["countries"].items()
        if not entry["status"].startswith("ok")
    }
    assert not_runnable == {}, (
        "Countries regressed since the last probe; rerun "
        "scripts/probe_euromod_readiness.py and update the matrix + "
        "playbook: " + json.dumps(not_runnable)
    )
