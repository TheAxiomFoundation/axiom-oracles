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


_SYNTHETIC_PRN = """\
-----------------------------------------------------------
hdseqhh   Household sequence number ...............       7
idseqino  CIS Individual Identifier (Original) .... 1234567
hdprov    Province ................................       5
hdmbmregp Market Basket Measure (MBM) Region for t       22
idage     Age .....................................      40      38      10
idiemp    Wages & salaries ........................  100000   50000       0
imbft     Basic federal tax .......................   12000    4000       0
imptax    Provincial taxes ........................    6000    2000       0
imftax    Federal taxes ...........................   14000    5000       0
-----------------------------------------------------------
hdseqhh   Household sequence number ...............       9
hdprov    Province ................................       2
idage     Age .....................................      70
imbft     Basic federal tax .......................     500
imptax    Provincial taxes ........................     200
imftax    Federal taxes ...........................     600
"""


def test_parse_case_output_handles_member_columns(tmp_path) -> None:
    # Synthetic fixture in the exact ASCSTYLE-1 layout (fixed-width name and
    # dot-padded or truncated description, one column per member). Real
    # extract rows are Database-derived and never appear in the repo.
    from axiom_oracles.adapters.spsm import parse_case_output

    path = tmp_path / "case.prn"
    path.write_text(_SYNTHETIC_PRN)
    households = parse_case_output(path)

    assert [h.sequence for h in households] == [7, 9]
    family = households[0]
    assert family.member_count() == 3
    assert family.values["imbft"] == [12000.0, 4000.0, 0.0]
    assert family.total("imbft") == 16000.0
    assert family.values["hdprov"] == [5.0]
    # Truncated description (no dot padding) still parses.
    assert family.values["hdmbmregp"] == [22.0]
    senior = households[1]
    assert senior.member_count() == 1
    assert senior.total("imftax") == 600.0


def test_batch_dialogue_matches_documented_facility(tmp_path) -> None:
    from axiom_oracles.adapters.spsm import SpsmRunner

    runner = SpsmRunner(install_root=tmp_path)
    dialogue = runner.batch_dialogue(
        control_file="$spsd/ba26",
        output_name="t2",
        sample=0.001,
        includes=("$spsd/detsum.cpi",),
    )
    assert dialogue == (
        "$spsd/ba26#t2#Y#SAMPLEREQ#0.001#read#$spsd/detsum.cpi#go#N#N#N"
    )
    plain = runner.batch_dialogue(control_file="$spsd/ba26", output_name="x")
    assert plain == "$spsd/ba26#x#N#N#N#N"
