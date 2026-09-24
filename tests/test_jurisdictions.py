"""The jurisdiction registry against the source recorded for each field.

Fixtures under tests/fixtures/jurisdictions are verbatim extractions:
- census_state.txt: the Census Bureau state FIPS file, as downloaded.
- taxsim_state_code_probes.json: TAXSIM taxsimtest state lines per code.
- rulespec_us_root_directories.json: rulespec-us jurisdiction directories.
- income_tax_base_2026.json: the Tax Foundation 2026 table's no-tax rows.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from axiom_oracles import jurisdictions
from axiom_oracles.jurisdictions import (
    REGISTRY_PATH,
    TaxsimSpecialCode,
    UnknownJurisdictionError,
    UsState,
    load_registry,
    state_by_fips,
    state_by_taxsim,
    state_by_usps,
    taxsim_entry,
    taxsim_special_code,
    taxsim_special_code_by_key,
    us_states,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "jurisdictions"
DOCUMENT = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
SOI_LINE = re.compile(r"State \(SOI code\):\s+(-?\d+)\s+(\S.*?)\s*$")


def _census_rows() -> list[dict[str, str]]:
    text = (FIXTURES / "census_state.txt").read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(text), delimiter="|"))


def _taxsim_probes() -> dict:
    return json.loads((FIXTURES / "taxsim_state_code_probes.json").read_text())


# --- Registry shape -------------------------------------------------------


def test_registry_has_fifty_states_and_dc_ordered_by_fips():
    states = us_states()
    assert len(states) == 51
    assert [s.fips for s in states] == sorted(s.fips for s in states)
    assert "DC" in {s.usps for s in states}


def test_registry_file_is_canonically_formatted():
    # Consumers pin this file by sha256; a reformat must be a deliberate edit.
    canonical = json.dumps(DOCUMENT, indent=2, ensure_ascii=False) + "\n"
    assert REGISTRY_PATH.read_text(encoding="utf-8") == canonical


def test_registry_sha256_matches_file_bytes():
    expected = hashlib.sha256(REGISTRY_PATH.read_bytes()).hexdigest()
    assert jurisdictions.registry_sha256() == expected


def test_registry_ships_inside_the_package():
    assert (
        REGISTRY_PATH.parent == Path(jurisdictions.__file__).resolve().parent / "data"
    )


# --- Census FIPS ----------------------------------------------------------


def test_census_fixture_matches_recorded_sha256():
    source = DOCUMENT["sources"]["census_fips"]
    digest = hashlib.sha256((FIXTURES / "census_state.txt").read_bytes()).hexdigest()
    assert digest == source["sha256"]
    assert source["fixture"] == "tests/fixtures/jurisdictions/census_state.txt"


def test_usps_fips_and_name_equal_the_census_file():
    census = [
        (row["STUSAB"], row["STATE"], row["STATE_NAME"])
        for row in _census_rows()
        if int(row["STATE"]) <= 56
    ]
    registry = [(s.usps, s.fips, s.name) for s in us_states()]
    assert registry == census


def test_territories_are_out_of_scope():
    territories = [row for row in _census_rows() if int(row["STATE"]) > 56]
    assert {row["STUSAB"] for row in territories} == {
        "AS",
        "GU",
        "MP",
        "PR",
        "UM",
        "VI",
    }
    for row in territories:
        with pytest.raises(UnknownJurisdictionError):
            state_by_fips(row["STATE"])
        with pytest.raises(UnknownJurisdictionError):
            state_by_usps(row["STUSAB"])


# --- TAXSIM ---------------------------------------------------------------


def test_taxsim_fixture_is_the_recorded_binary_build():
    probes = _taxsim_probes()
    source = DOCUMENT["sources"]["taxsim"]
    assert probes["binary_sha256"] == source["binary_sha256"]
    assert probes["build"] == source["build"] == "cd2026081819"


@pytest.mark.parametrize("echo", ["input_echo", "output_echo"])
def test_taxsim_codes_and_names_equal_the_binary_echo(echo):
    runs = {run["code"]: run for run in _taxsim_probes()["runs"]}
    echoed = {}
    for code in range(1, 52):
        assert runs[code]["exit_status"] == 0
        match = SOI_LINE.search(runs[code][echo])
        assert match, runs[code][echo]
        echoed[int(match.group(1))] = match.group(2)
    assert echoed == {s.taxsim_soi: s.taxsim_name for s in us_states()}


def test_taxsim_special_codes_equal_the_binary_echo():
    runs = {run["code"]: run for run in _taxsim_probes()["runs"]}
    for special in load_registry().taxsim_special_codes:
        run = runs[special.code]
        assert run["exit_status"] == 0
        assert run["input_echo"].strip() == f"3. {special.idtl5_label}"
        assert run["output_echo"].strip() == special.idtl5_label
    assert runs[0]["output_blocks"] == 1
    # -1 computes the record once per state.
    assert runs[-1]["output_blocks"] == 51


def test_taxsim_rejects_the_first_code_past_wyoming():
    run = {run["code"]: run for run in _taxsim_probes()["runs"]}[52]
    assert run["exit_status"] != 0
    assert "is not a valid SOI state code" in run["input_echo"]
    with pytest.raises(UnknownJurisdictionError):
        taxsim_entry(52)


def test_taxsim_csv_probes_back_the_special_code_meanings():
    probes = {probe["name"]: probe for probe in _taxsim_probes()["csv_probes"]}
    registry = load_registry()
    assert "state" not in probes["missing_state_column"]["input"].splitlines()[0]
    assert probes["missing_state_column"]["output_state_column"] == [
        registry.taxsim_missing_state_column_code
    ]
    assert probes["state_0"]["output_state_column"] == [
        taxsim_special_code_by_key("no_state").code
    ]
    assert taxsim_special_code_by_key("all_states").code == -1
    assert probes["state_minus_1"]["output_state_column"] == sorted(
        s.taxsim_soi for s in us_states()
    )


def test_taxsim_codes_are_alphabetical_by_census_name():
    by_name = sorted(us_states(), key=lambda s: s.name)
    assert [s.taxsim_soi for s in by_name] == list(range(1, 52))


def test_taxsim_name_is_the_census_name_except_dc():
    differ = {s.usps: s.taxsim_name for s in us_states() if s.taxsim_name != s.name}
    assert differ == {"DC": "DC"}


def _installed_taxsim_binary() -> Path | None:
    override = os.environ.get("AXIOM_TAXSIM_BINARY")
    if override:
        return Path(override)
    from axiom_oracles.adapters.taxsim.pins import installed_binary_path

    return installed_binary_path()


def test_taxsim_live_binary_echo_matches_registry():
    binary = _installed_taxsim_binary()
    if binary is None or not binary.exists():
        pytest.skip(
            "no TAXSIM binary (install the taxsim extra or set AXIOM_TAXSIM_BINARY)"
        )
    expected = {s.taxsim_soi: s.taxsim_name for s in us_states()}
    for special in load_registry().taxsim_special_codes:
        expected[special.code] = None
    for code, name in sorted(expected.items()):
        record = f"taxsimid,year,state,mstat,pwages,idtl\n1,2024,{code},1,50000,5\n"
        result = subprocess.run(
            [str(binary)], input=record, capture_output=True, text=True, timeout=60
        )
        assert result.returncode == 0, result.stderr
        lines = [line for line in result.stdout.splitlines() if "3. State" in line]
        if name is None:
            label = taxsim_special_code(code).idtl5_label
            assert lines and lines[0].strip() == f"3. {label}"
        else:
            match = SOI_LINE.search(lines[0])
            assert match and (int(match.group(1)), match.group(2)) == (code, name)


# --- rulespec-us ----------------------------------------------------------


def _rulespec_slugs(directories: list[str]) -> set[str]:
    return {d for d in directories if re.fullmatch(r"us-[a-z]{2}", d)}


def test_rulespec_slugs_equal_the_rulespec_us_directories():
    fixture = json.loads((FIXTURES / "rulespec_us_root_directories.json").read_text())
    assert fixture["commit"] == DOCUMENT["sources"]["rulespec_slug"]["commit"]
    assert {s.rulespec_slug for s in us_states()} == _rulespec_slugs(
        fixture["allowed_root_directories"]
    )
    for state in us_states():
        assert state.rulespec_slug == f"us-{state.usps.lower()}"


def test_rulespec_slugs_equal_a_local_rulespec_us_checkout():
    root = Path(os.environ.get("RULESPEC_US_REPO", REPO_ROOT.parent / "rulespec-us"))
    structure = root / ".axiom" / "repository-structure.yaml"
    if not structure.exists():
        pytest.skip("no rulespec-us checkout (set RULESPEC_US_REPO)")
    import yaml

    directories = yaml.safe_load(structure.read_text())["allowed_root_directories"]
    assert _rulespec_slugs(directories) == {s.rulespec_slug for s in us_states()}


# --- Personal income tax base ---------------------------------------------


def test_income_tax_base_equals_the_tax_foundation_table():
    fixture = json.loads((FIXTURES / "income_tax_base_2026.json").read_text())
    source = DOCUMENT["sources"]["personal_income_tax_base"]
    for key, value in fixture["source"].items():
        assert source[key] == value
    by_base = {}
    for state in us_states():
        by_base.setdefault(state.personal_income_tax_base, set()).add(state.name)
    assert by_base["none"] == set(fixture["no_individual_income_tax"])
    assert by_base["capital_gains_only"] == set(fixture["capital_gains_only"])
    assert len(by_base["wages_and_salaries"]) == 42  # 41 states and DC


def test_broad_personal_income_tax_flag_is_wage_taxation():
    no_broad = {s.usps for s in us_states() if not s.has_broad_personal_income_tax}
    assert no_broad == {"AK", "FL", "NH", "NV", "SD", "TN", "TX", "WA", "WY"}


# --- Lookups --------------------------------------------------------------


@pytest.mark.parametrize("state", us_states(), ids=lambda s: s.usps)
def test_every_state_round_trips_through_every_lookup(state):
    assert state_by_usps(state.usps) is state
    assert state_by_usps(f" {state.usps.lower()} ") is state
    assert state_by_fips(state.fips) is state
    assert state_by_fips(state.fips_code) is state
    assert state_by_fips(str(state.fips_code)) is state
    assert state_by_taxsim(state.taxsim_soi) is state
    assert state_by_taxsim(str(state.taxsim_soi)) is state
    assert taxsim_entry(state.taxsim_soi) is state


def test_fips_lookup_accepts_numpy_style_integers():
    class IndexLike:
        def __index__(self):
            return 1

    assert state_by_fips(IndexLike()).usps == "AL"


@pytest.mark.parametrize(
    "code", ["XX", "", " ", "A", "ALA", "PR", "01", None, 1, b"AL"], ids=repr
)
def test_unknown_usps_code_raises(code):
    with pytest.raises(UnknownJurisdictionError):
        state_by_usps(code)


@pytest.mark.parametrize(
    "code",
    [
        0,
        3,
        7,
        14,
        43,
        52,
        57,
        60,
        72,
        99,
        -1,
        "",
        "00",
        "03",
        "001",
        "1.0",
        "AL",
        "x1",
        "١",
        True,
        False,
        1.0,
        None,
    ],
    ids=repr,
)
def test_unknown_fips_code_raises(code):
    with pytest.raises(UnknownJurisdictionError):
        state_by_fips(code)


@pytest.mark.parametrize(
    "code", [52, 53, 99, -2, "52", "", "1.0", "AL", True, 1.0, None], ids=repr
)
def test_unknown_taxsim_code_raises(code):
    with pytest.raises(UnknownJurisdictionError):
        state_by_taxsim(code)
    with pytest.raises(UnknownJurisdictionError):
        taxsim_entry(code)


@pytest.mark.parametrize(
    "code,key", [(0, "no_state"), (-1, "all_states"), ("-1", "all_states")]
)
def test_special_taxsim_codes_are_first_class_entries(code, key):
    entry = taxsim_entry(code)
    assert isinstance(entry, TaxsimSpecialCode)
    assert entry.key == key
    assert taxsim_special_code(code) is entry
    assert taxsim_special_code_by_key(key) is entry
    with pytest.raises(UnknownJurisdictionError, match=key):
        state_by_taxsim(code)


def test_no_state_is_what_taxsim_prints_and_what_a_missing_column_means():
    no_state = taxsim_special_code(0)
    assert no_state.idtl5_label == "State not specified"
    assert load_registry().taxsim_missing_state_column_code == no_state.code


def test_state_codes_are_not_special_codes():
    with pytest.raises(UnknownJurisdictionError):
        taxsim_special_code(1)
    with pytest.raises(UnknownJurisdictionError):
        taxsim_special_code_by_key("texas")


def test_lookups_return_registry_objects():
    assert isinstance(state_by_usps("AL"), UsState)
    assert state_by_usps("AL") == UsState(
        usps="AL",
        fips="01",
        taxsim_soi=1,
        name="Alabama",
        taxsim_name="Alabama",
        rulespec_slug="us-al",
        has_broad_personal_income_tax=True,
        personal_income_tax_base="wages_and_salaries",
    )


# --- Validation of a corrupted file ---------------------------------------


def _corrupt(mutate) -> dict:
    document = copy.deepcopy(DOCUMENT)
    mutate(document)
    return document


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(schema="axiom.jurisdictions.v0"),
        lambda d: d["states"][1].update(fips="01"),
        lambda d: d["states"][1].update(usps="AL"),
        lambda d: d["states"][1].update(taxsim_soi=1),
        lambda d: d["states"][1].update(fips="2"),
        lambda d: d["states"][1].update(taxsim_soi=True),
        lambda d: d["states"][0].update(has_broad_personal_income_tax=False),
        lambda d: d["states"][0].update(personal_income_tax_base="wages"),
        lambda d: d["states"].reverse(),
        lambda d: d["taxsim"]["special_state_codes"][0].update(code=1),
        lambda d: d["taxsim"].update(missing_state_column_code=44),
    ],
)
def test_parse_rejects_a_corrupted_registry(mutate):
    with pytest.raises((ValueError, TypeError)):
        jurisdictions._parse(_corrupt(mutate))


# --- Vendored copies ------------------------------------------------------


def test_installed_policyengine_taxsim_copy_agrees_when_present():
    """policyengine-taxsim (the taxsim extra) vendors this file by sha256."""
    try:
        import policyengine_taxsim
    except ImportError:
        pytest.skip("policyengine-taxsim is not installed")
    copies = sorted(
        Path(policyengine_taxsim.__file__).parent.rglob("jurisdictions.v1.json")
    )
    if not copies:
        pytest.skip("installed policyengine-taxsim predates the vendored registry")

    def crosswalk(document: dict) -> tuple:
        states = tuple(
            (s["usps"], s["fips"], s["taxsim_soi"], s["name"])
            for s in document["states"]
        )
        specials = tuple(
            (c["code"], c["key"]) for c in document["taxsim"]["special_state_codes"]
        )
        return states, specials

    for path in copies:
        assert crosswalk(json.loads(path.read_text())) == crosswalk(DOCUMENT), path
