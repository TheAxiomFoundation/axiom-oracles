"""Attestation surveys only jurisdiction universes beside conformance controls."""

import importlib.util
from pathlib import Path


def test_attestation_discovers_every_universe_and_skips_control_files(tmp_path):
    script_path = (
        Path(__file__).parents[1] / "scripts" / "conformance_attestation.py"
    )
    spec = importlib.util.spec_from_file_location("attestation_discovery_script", script_path)
    assert spec is not None and spec.loader is not None
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    script.CONFORMANCE_DIR = tmp_path

    universe_stems = ("be", "dk", "uk", "uk-pe", "us-pe", "us-tariff-yale")
    for stem in (*universe_stems, "ratchet", "unexplained-ratchet",
                 "pe-axiom-standard", "attestation_waivers"):
        (tmp_path / f"{stem}.yaml").write_text("")
    (tmp_path / "README.md").write_text("")
    nested = tmp_path / "compositions"
    nested.mkdir()
    (nested / "be.yaml").write_text("")

    assert [path.stem for path in script._universe_paths()] == sorted(
        universe_stems, key=lambda stem: f"{stem}.yaml"
    )
