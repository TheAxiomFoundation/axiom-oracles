import json
from pathlib import Path

import pytest

from axiom_oracles.adapters.spsm import (
    SPSM_ATTRIBUTION_NOTICE,
    SpsmRunner,
)
from axiom_oracles.adapters.spsm.runner import attribution_provenance


def test_attribution_notice_matches_licence_wording() -> None:
    # SPSD/M Licence Agreement s.4.1 prescribes the notice text; the
    # constant must keep the licence's operative sentences intact.
    assert "Statistics Canada's Social Policy" in SPSM_ATTRIBUTION_NOTICE
    assert "Simulation Database and Model" in SPSM_ATTRIBUTION_NOTICE
    assert (
        "responsibility for the use and interpretation of these data"
        in SPSM_ATTRIBUTION_NOTICE
    )
    provenance = attribution_provenance()
    assert provenance["attribution"] == SPSM_ATTRIBUTION_NOTICE
    assert provenance["oracle"] == "spsm"


def test_runner_requires_licensed_install(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SPSM_HOME", str(tmp_path / "does-not-exist"))
    runner = SpsmRunner()
    with pytest.raises(RuntimeError, match="No SPSD/M installation"):
        runner.require_install()


def test_pins_file_never_references_package_contents() -> None:
    # The pin records public identity only; it must carry the licence
    # constraints and must not embed any Package payload.
    pins = json.loads(
        (
            Path(__file__).parent.parent
            / "axiom_oracles"
            / "adapters"
            / "spsm"
            / "spsm_pins.json"
        ).read_text()
    )
    assert pins["package"]["version"] == "34.0"
    assert "no part of the Package" in pins["licence"]["redistribution"]
    assert pins["licence"]["publication_notice"] == SPSM_ATTRIBUTION_NOTICE
