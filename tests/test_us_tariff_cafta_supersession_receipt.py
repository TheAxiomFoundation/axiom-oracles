from __future__ import annotations

import gzip
import json
import os
from pathlib import Path

import pytest

from scripts import build_us_tariff_cafta_supersession_receipt as producer


def test_expected_rulespec_commit_is_completed_clean_tariff_precedence_commit() -> None:
    assert (
        producer.EXPECTED_RULESPEC_COMMIT == "4f591c4267063094cc6da9d590872ea982940b81"
    )


def test_campaign_schema_and_yale_provenance_pins_are_current() -> None:
    assert (
        producer.INPUT_CONTRACT_SCHEMA
        == producer.campaign.INPUT_CONTRACT_SCHEMA
        == "axiom_oracles.us_tariff_schedule.declared_input_contract.v4"
    )
    assert (
        producer.EVAL_RUN_IDENTITY_SCHEMA
        == producer.campaign.EVAL_RUN_IDENTITY_SCHEMA
        == "axiom_oracles.us_tariff_schedule.eval_run_identity.v4"
    )
    assert (
        producer.EVAL_MANIFEST_SCHEMA
        == producer.campaign.EVAL_MANIFEST_SCHEMA
        == producer.foundation.EVAL_SCHEMA
        == "axiom_oracles.us_tariff_schedule.eval_manifest.v3"
    )
    assert (
        producer.COMPARISON_SCHEMA
        == producer.campaign.COMPARISON_SCHEMA
        == producer.foundation.COMPARISON_SCHEMA
        == "axiom_oracles.us_tariff_schedule.comparison_summary.v3"
    )
    assert producer.EXPECTED_YALE_COMMIT == producer.campaign.PREVIEW_YALE_COMMIT
    assert producer.EXPECTED_YALE_TREE == producer.campaign.PREVIEW_YALE_TREE
    provenance = json.loads(producer.PROVENANCE.read_text())
    assert provenance["schema"] == producer.REFERENCE_PROVENANCE_SCHEMA


def test_campaign_runtime_rejects_stale_run_identity_schema() -> None:
    with pytest.raises(ValueError, match="run identity schema is stale"):
        producer._validate_campaign_and_rulespec_runtime(
            {"schema": "axiom_oracles.us_tariff_schedule.eval_run_identity.v3"}
        )


def _identity(*, expected: float = 0.0) -> dict:
    return {
        "case_id": "schedule-" + "a" * 24,
        "slot": "forced_labor_section_301",
        "hts10": "4202110030",
        "hts_line": "4202110000",
        "iso2": "CR",
        "revision": "bnd_2026-07-24",
        "interval": ["2026-07-24", "2026-07-30"],
        "origin_regime": "0000000000000000",
        "expected": expected,
    }


def _context(identity: dict) -> dict:
    return {
        "hts10": identity["hts10"],
        "hts_line": identity["hts_line"],
        "iso2": identity["iso2"],
        "revision": identity["revision"],
        "interval": identity["interval"],
        "origin_regime": identity["origin_regime"],
        "flags": {
            "entry_is_forced_labor_301_listed": True,
            "entry_is_section_232_covered": False,
        },
    }


def _defect_model() -> dict:
    return {
        "fta_rules": {("2230", "42021100")},
        "intended_country_full_rules": set(),
        "country_aircraft_rules": set(),
        "country_pharma_rules": set(),
        "common_full_rules": set(),
        "common_aircraft_rules": set(),
        "common_pharma_rules": set(),
        "patented_pharma": set(),
        "target_rates": {"2230": 0.125},
        "rate_types": {"2230": "surcharge"},
    }


def _write_gzip(path: Path, rows: list[dict]) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            for row in rows:
                zipped.write(
                    (
                        json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
                    ).encode()
                )


def test_committed_preview_cafta_snapshot_is_immutable_and_still_open() -> None:
    preview = json.loads(producer.PREVIEW_RECEIPT.read_text())
    assert (
        producer.canonical_sha256(producer.cafta_preview_snapshot(preview))
        == producer.EXPECTED_PREVIEW_CAFTA_SNAPSHOT_SHA256
    )
    selector = next(
        item
        for item in preview["selectors"]
        if item["id"] == producer.CAFTA_SELECTOR_ID
    )
    assert selector["expected_units"] == producer.EXPECTED_CAFTA_UNITS
    assert selector["attribution"] == "axiom-attributed-open"
    assert selector["disposition"] == "axiom_encoding_gap"


def test_input_contract_proves_both_cafta_predicates_false(tmp_path: Path) -> None:
    chapters = [
        {
            "chapter": f"{chapter:02d}",
            "case_feed_inputs": list(producer.CAFTA_INPUTS),
            "missing_declared_entry_inputs": [],
            "missing_reachable_inputs": [],
        }
        for chapter in range(1, 101)
    ]
    contract = {
        "schema": producer.INPUT_CONTRACT_SCHEMA,
        "verdict": "PASS",
        "neutral_boolean_inputs": list(producer.CAFTA_INPUTS),
        "neutral_boolean_value": False,
        "chapters": chapters,
    }
    path = tmp_path / "contract.json"
    path.write_text(producer.render(contract))
    run_identity = {
        "chapters": {
            chapter["chapter"]: {"case_feed_inputs": list(producer.CAFTA_INPUTS)}
            for chapter in chapters
        },
        "input_contract": {
            **producer.foundation.file_receipt(path, relative_to=tmp_path),
            "schema": producer.INPUT_CONTRACT_SCHEMA,
        },
    }
    _, proof = producer._validate_input_contract(
        repo_root=tmp_path, run_identity=run_identity
    )
    assert proof["predicates"] == {name: False for name in producer.CAFTA_INPUTS}

    contract["neutral_boolean_value"] = True
    path.write_text(producer.render(contract))
    run_identity["input_contract"] = {
        **producer.foundation.file_receipt(path, relative_to=tmp_path),
        "schema": producer.INPUT_CONTRACT_SCHEMA,
    }
    with pytest.raises(ValueError, match="not explicitly neutral false"):
        producer._validate_input_contract(repo_root=tmp_path, run_identity=run_identity)

    contract["neutral_boolean_value"] = False
    contract["chapters"][1]["chapter"] = contract["chapters"][0]["chapter"]
    path.write_text(producer.render(contract))
    run_identity["input_contract"] = {
        **producer.foundation.file_receipt(path, relative_to=tmp_path),
        "schema": producer.INPUT_CONTRACT_SCHEMA,
    }
    with pytest.raises(ValueError, match="bind uniquely"):
        producer._validate_input_contract(repo_root=tmp_path, run_identity=run_identity)


def test_tidy_eval_minimal_reproduction_requires_full_and_fta_rows() -> None:
    assert (
        producer._validate_tidy_eval_reproduction_output(
            "r_version=4.3.0\ndplyr_version=1.1.2\n"
            f"dplyr_path={producer.campaign.CAFTA_EXPECTED_DPLYR_TREE_RECEIPT['path']}\n"
            "selected_conditions=full,fta\n"
        )["selected_conditions"]
        == "full,fta"
    )
    with pytest.raises(ValueError, match="name-collision reproduction drift"):
        producer._validate_tidy_eval_reproduction_output(
            "r_version=4.3.0\ndplyr_version=1.1.2\n"
            f"dplyr_path={producer.campaign.CAFTA_EXPECTED_DPLYR_TREE_RECEIPT['path']}\n"
            "selected_conditions=full\n"
        )


def test_tidy_eval_minimal_reproduction_rejects_path_shadow_rscript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "Rscript"
    fake.write_text(
        "#!/bin/sh\n"
        "printf 'r_version=4.3.0\\ndplyr_version=1.1.2\\n"
        "selected_conditions=full,fta\\n'\n"
    )
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")

    with pytest.raises(ValueError, match="Rscript runtime drift"):
        producer._run_tidy_eval_reproduction()


def test_tidy_eval_minimal_reproduction_ignores_hostile_r_startup_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = tmp_path / "hostile.Rprofile"
    profile.write_text('stop("R profile must not execute")\n')
    monkeypatch.setenv("R_PROFILE_USER", str(profile))
    monkeypatch.setenv("R_LIBS_USER", str(tmp_path / "untrusted-library"))

    replay = producer._run_tidy_eval_reproduction()
    assert replay["selected_conditions"] == "full,fta"
    assert (
        replay["r_runtime_tree"]
        == producer.campaign.CAFTA_EXPECTED_R_RUNTIME_TREE_RECEIPT
    )
    assert replay["dplyr_tree"] == producer.campaign.CAFTA_EXPECTED_DPLYR_TREE_RECEIPT


def test_yale_defect_replay_requires_zero_and_only_fta_membership() -> None:
    identity = _identity()
    replay = producer._replay_yale_defect(
        identity=identity,
        actual=0.125,
        expected=0.0,
        delta=0.125,
        defect_model=_defect_model(),
    )
    assert replay["predicted_yale_rate_s301fl"] == 0
    assert replay["corrected_yale_statutory_rate_s301fl"] == 0.125
    assert replay["corrected_yale_matches_axiom"] is True

    with pytest.raises(ValueError, match="name-collision zero"):
        producer._replay_yale_defect(
            identity=identity,
            actual=0.125,
            expected=0.025,
            delta=0.1,
            defect_model=_defect_model(),
        )
    mutant = _defect_model()
    mutant["intended_country_full_rules"] = {("2230", "42021100")}
    with pytest.raises(ValueError, match="non-bug Yale exclusion"):
        producer._replay_yale_defect(
            identity=identity,
            actual=0.125,
            expected=0.0,
            delta=0.125,
            defect_model=mutant,
        )


@pytest.mark.parametrize(
    "field",
    (
        "country_aircraft_rules",
        "country_pharma_rules",
        "common_aircraft_rules",
        "common_pharma_rules",
    ),
)
def test_yale_defect_replay_rejects_use_conditioned_paths(field: str) -> None:
    mutant = _defect_model()
    mutant[field] = (
        {("2230", "42021100")} if field.startswith("country_") else {"42021100"}
    )
    with pytest.raises(ValueError, match="non-bug Yale exclusion"):
        producer._replay_yale_defect(
            identity=_identity(),
            actual=0.125,
            expected=0.0,
            delta=0.125,
            defect_model=mutant,
        )


def test_yale_defect_replay_rejects_floor_and_chapter98_paths() -> None:
    mutant = _defect_model()
    mutant["rate_types"]["2230"] = "floor"
    with pytest.raises(ValueError, match="name-collision zero"):
        producer._replay_yale_defect(
            identity=_identity(),
            actual=0.125,
            expected=0.0,
            delta=0.125,
            defect_model=mutant,
        )
    chapter98_model = _defect_model()
    chapter98_model["fta_rules"] = {("2230", "98021100")}
    with pytest.raises(ValueError, match="name-collision zero"):
        producer._replay_yale_defect(
            identity={
                **_identity(),
                "hts10": "9802110030",
                "hts_line": "9802110000",
            },
            actual=0.125,
            expected=0.0,
            delta=0.125,
            defect_model=chapter98_model,
        )


def test_fresh_reference_population_requires_exact_mismatch_and_defect(
    tmp_path: Path,
) -> None:
    identity = _identity()
    context = _context(identity)
    row = {
        "case_id": identity["case_id"],
        "slot": identity["slot"],
        "expected": 0.0,
        "actual": 0.125,
        "delta": 0.125,
        "match": False,
        "context": context,
    }
    artifact = tmp_path / "comparison.jsonl.gz"
    _write_gzip(artifact, [row])
    key = (identity["case_id"], identity["slot"])
    historical_units = {
        key: {"selector": producer.CAFTA_SELECTOR_ID, "identity": identity}
    }
    historical_rows = [
        {
            "selector": producer.CAFTA_SELECTOR_ID,
            "identity": identity,
            "historical_actual": 0.125,
            "historical_delta": 0.125,
        }
    ]
    source_eval_units = {
        key: {
            "comparison": {
                **row,
                "match": False,
            }
        }
    }
    comparison = {
        "tolerance": producer.TOLERANCE,
        "per_slot": {"forced_labor_section_301": {"mismatch": 1}},
    }
    defect_rows, audit = producer._scan_fresh_reference_population(
        comparison_artifact=artifact,
        comparison=comparison,
        historical_units=historical_units,
        historical_rows=historical_rows,
        source_eval_units=source_eval_units,
        defect_model=_defect_model(),
        expected_origin_units={"CR": 1},
    )
    assert len(defect_rows) == audit["joined_historical_units"] == 1

    row["match"] = True
    _write_gzip(artifact, [row])
    comparison["per_slot"] = {"forced_labor_section_301": {"match": 1}}
    with pytest.raises(ValueError, match="no longer has a reference discrepancy"):
        producer._scan_fresh_reference_population(
            comparison_artifact=artifact,
            comparison=comparison,
            historical_units=historical_units,
            historical_rows=historical_rows,
            source_eval_units=source_eval_units,
            defect_model=_defect_model(),
            expected_origin_units={"CR": 1},
        )


def test_joined_eval_feed_reconstruction_requires_actual_false_false(
    monkeypatch,
) -> None:
    identity = _identity()
    key = (identity["case_id"], identity["slot"])
    run_identity = {
        "chapters": {"42": {"case_feed_inputs": list(producer.CAFTA_INPUTS)}}
    }
    source_eval_units = {
        key: {
            "identity": identity,
            "evaluation_record": {
                "chapter": "42",
                "probe": "2026-07-24",
                "country": "2230",
            },
            "comparison": {"context": {"flags": {"listed": True}}},
        }
    }

    def reconstructed(_row, _route, _entry_flags, **_kwargs):
        return ({name: False for name in producer.CAFTA_INPUTS}, {"listed": True})

    monkeypatch.setattr(producer.campaign, "_case_feed", reconstructed)
    rows = producer._reconstruct_joined_cafta_feeds(
        run_identity=run_identity,
        source_eval_units=source_eval_units,
        entry_flags=object(),
        expected_units=1,
    )
    assert rows[0]["actual_cafta_inputs"] == {
        name: False for name in producer.CAFTA_INPUTS
    }

    def mutant(_row, _route, _entry_flags, **_kwargs):
        feed = {name: False for name in producer.CAFTA_INPUTS}
        feed[producer.CAFTA_INPUTS[0]] = True
        return feed, {"listed": True}

    monkeypatch.setattr(producer.campaign, "_case_feed", mutant)
    with pytest.raises(ValueError, match="actually feed both predicates false"):
        producer._reconstruct_joined_cafta_feeds(
            run_identity=run_identity,
            source_eval_units=source_eval_units,
            entry_flags=object(),
            expected_units=1,
        )


def test_end_receipt_recheck_rejects_mutation(tmp_path: Path) -> None:
    path = tmp_path / "evidence.json"
    path.write_text("{}\n")
    receipt = producer.foundation.file_receipt(path, relative_to=tmp_path)
    producer._require_file_receipt_unchanged(
        path, receipt, label="test evidence", relative_to=tmp_path
    )
    path.write_text('{"mutated":true}\n')
    with pytest.raises(ValueError, match="changed during CAFTA proof"):
        producer._require_file_receipt_unchanged(
            path, receipt, label="test evidence", relative_to=tmp_path
        )
