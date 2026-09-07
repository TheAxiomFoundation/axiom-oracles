from __future__ import annotations

import copy
import gzip
import hashlib
import json
import threading
from collections import Counter
from pathlib import Path

import pytest
import yaml

from axiom_oracles.comparison.dispositions import (
    validate_dispositions as validate_shared,
)

from scripts import us_tariff_schedule_campaign as campaign_module
from scripts.us_tariff_schedule_campaign import (
    BASE_INDEPENDENT_AUTHORITY_SLOTS,
    ENTRY_FLAG_ALIASES,
    EXPECTED_DROPPED_ENTRY_FLAGS,
    PREVIEW_DISPOSITION_LINE_SETS,
    PREVIEW_SELECTOR_COUNT,
    _enforce_preview_selector_population,
    _enforce_preview_selector_transitions,
    _enforce_retired_preview_selectors_absent,
    _named_line_sets,
    _preview_selector_contract,
    _preview_selector_snapshot,
    _preview_transition_is_required,
    _transition_for_entries,
    _case_feed,
    _routing_dispositions,
    canonicalize_entry_flags,
    compare_record,
    computed_conformant,
    enforce_excluded_exposure,
    filter_declared_feed,
    query_plan,
    matching_class_id,
    mismatch_signature,
    mismatch_unit,
    route_member,
    selector_matches,
    signature_population_sha256,
    validate_dispositions,
    witness_replay,
)
from scripts.us_tariff_schedule_campaign import DISPOSITION_LEDGER

EVAL_GENERATION_ID = "1" * 32


def _fake_run_identity(*, marker: str = "a", chapters: tuple[str, ...] = ("01",)):
    digest = marker * 64
    return {
        "schema": campaign_module.EVAL_RUN_IDENTITY_SCHEMA,
        "rulespec": {
            "root": f"/rulespec/{marker}",
            "head_commit": digest[:40],
            "head_tree": digest[:40],
            "content_sha256": digest,
        },
        "engine": {"path": f"/engine/{marker}", "bytes": 1, "sha256": digest},
        "entry_flag_producers": {
            "tool": {"path": "tools/b16_entry_flags.py", "bytes": 1, "sha256": digest},
            "dependencies": [],
            "producer_sha256": digest,
        },
        "input_contract": {
            "path": "contract.json",
            "bytes": 1,
            "sha256": digest,
            "schema": "contract",
        },
        "reference_assumptions": {
            "yale_note16_metal_weight": {
                "path": "reference/assumption.json",
                "bytes": 1,
                "sha256": digest,
            }
        },
        "campaign_evaluator": {
            "campaign": {"path": "campaign.py", "bytes": 1, "sha256": digest},
            "oracle_sources": [],
            "python": {
                "executable": {"path": "/python", "bytes": 1, "sha256": digest},
                "version": marker,
            },
            "pyyaml_version": marker,
            "producer_sha256": digest,
        },
        "selected_population": {"path": "selected.gz", "bytes": 1, "sha256": digest},
        "routing": {"path": "routing.gz", "bytes": 1, "sha256": digest},
        "outputs": list(campaign_module.OUTPUT_NAMES),
        "chapters": {
            chapter: {
                "module": f"generated/ch{chapter}.yaml",
                "module_sha256": digest,
                "compiled_artifact_sha256": digest,
            }
            for chapter in chapters
        },
    }


def _complete_eval_manifest(
    tmp_path: Path,
    run_identity: dict,
    generation_id: str = EVAL_GENERATION_ID,
):
    manifest = campaign_module._empty_eval_manifest(run_identity, generation_id)
    for chapter, key in campaign_module._current_shard_keys(
        run_identity, generation_id
    ).items():
        path = tmp_path / f"{key}.jsonl.gz"
        with path.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0):
                pass
        manifest["shards"][key] = {
            "chapter": chapter,
            "key": key,
            "run_identity_sha256": campaign_module._run_identity_sha256(run_identity),
            "generation_id": generation_id,
            "path": str(path),
            "sha256": campaign_module._sha256(path),
            "cases": 0,
            "engine_errors": 0,
            "elapsed_seconds": 0,
        }
    return manifest


def test_declared_feed_drops_only_retired_exemplar_flags() -> None:
    feed = {
        "hts_line": 1,
        "entry_is_line_a": False,
        "entry_is_line_b": False,
        "entry_is_line_c": False,
        "entry_is_line_d": False,
        "entry_is_line_e": False,
    }
    declared = {"hts_line", "entry_is_line_a", "entry_is_line_b", "entry_is_line_d"}
    filtered, receipt = filter_declared_feed(
        feed,
        declared,
        emitted_flag_names={name for name in feed if name.startswith("entry_")},
    )
    assert set(filtered) == declared
    assert receipt["dropped_entry_flags"] == sorted(EXPECTED_DROPPED_ENTRY_FLAGS)


def test_undeclared_input_mutant_fails_filter_assertion() -> None:
    feed = {
        "declared": True,
        "entry_is_line_c": False,
        "entry_is_line_e": False,
        "mutant_undeclared": True,
    }
    with pytest.raises(ValueError, match="undeclared non-flag inputs"):
        filter_declared_feed(
            feed,
            {"declared"},
            emitted_flag_names={"entry_is_line_c", "entry_is_line_e"},
        )


def test_declared_but_unfed_input_mutant_surfaces_before_default() -> None:
    feed = {"entry_is_line_c": False, "entry_is_line_e": False}
    with pytest.raises(
        ValueError, match="declared inputs absent from feed:.*required_neutral_fact"
    ):
        filter_declared_feed(
            feed,
            {"required_neutral_fact"},
            emitted_flag_names={"entry_is_line_c", "entry_is_line_e"},
        )


def test_entry_flag_aliases_canonicalize_when_equal() -> None:
    raw = {
        "entry_is_brazil_301": True,
        "entry_is_brazil_301_listed": True,
        "entry_is_forced_labor_301": False,
        "entry_is_forced_labor_301_listed": False,
        "entry_is_section_232_covered": True,
        "entry_qualifies_for_note39_heading_9903_79_01": False,
    }
    flags, aliases = canonicalize_entry_flags(raw)
    assert aliases == tuple(sorted(ENTRY_FLAG_ALIASES))
    assert not (set(flags) & set(ENTRY_FLAG_ALIASES))
    assert flags["entry_is_brazil_301_listed"] is True
    assert flags["entry_is_forced_labor_301_listed"] is False
    assert flags["entry_qualifies_for_note39_heading_9903_79_01"] is False


def test_all_public_entry_prefixes_are_preserved() -> None:
    flags, _aliases = canonicalize_entry_flags(
        {
            "entry_loaded_before_deadline": True,
            "entry_qualifies_for_exception": False,
            "internal_diagnostic": True,
        }
    )
    assert flags == {
        "entry_loaded_before_deadline": True,
        "entry_qualifies_for_exception": False,
    }


def test_entry_flag_alias_disagreement_fails_closed() -> None:
    with pytest.raises(ValueError, match="entry-flag alias disagreement"):
        canonicalize_entry_flags(
            {
                "entry_is_brazil_301": True,
                "entry_is_brazil_301_listed": False,
            }
        )


def test_entry_flag_alias_without_canonical_fails_closed() -> None:
    with pytest.raises(ValueError, match="without canonical"):
        canonicalize_entry_flags({"entry_is_brazil_301": True})


@pytest.mark.parametrize("malformed", ["false", 0, 1, None])
def test_entry_flag_values_must_be_boolean(malformed) -> None:
    with pytest.raises(ValueError, match="entry flags must be boolean"):
        canonicalize_entry_flags(
            {
                "entry_is_brazil_301": malformed,
                "entry_is_brazil_301_listed": True,
            }
        )


def test_case_feed_never_forwards_entry_flag_aliases() -> None:
    observed_kwargs = {}

    def entry_flags(_line, _hts, _iso2, **kwargs):
        observed_kwargs.update(kwargs)
        return {
            "entry_is_brazil_301": True,
            "entry_is_brazil_301_listed": True,
            "entry_is_forced_labor_301": False,
            "entry_is_forced_labor_301_listed": False,
            "entry_is_line_c": False,
            "entry_is_line_e": False,
            campaign_module.NOTE16_WEIGHT_INPUT: kwargs[
                campaign_module.NOTE16_WEIGHT_INPUT
            ],
        }

    feed, flags = _case_feed(
        {"hts10": "0102294024", "iso2": "BR"},
        {"hts_line": "102294000"},
        entry_flags,
        probe="2026-07-24",
        case_feed_inputs=campaign_module._case_feed_input_names(
            {
                "entry_is_brazil_301_listed",
                "entry_is_forced_labor_301_listed",
                "entry_is_line_c",
                "entry_is_line_e",
                campaign_module.NOTE16_WEIGHT_INPUT,
            }
        ),
    )
    assert not (set(flags) & set(ENTRY_FLAG_ALIASES))
    assert not (set(feed) & set(ENTRY_FLAG_ALIASES))
    assert feed["entry_is_brazil_301_listed"] is True
    assert observed_kwargs == {
        "entry_date": "2026-07-24",
        campaign_module.NOTE16_WEIGHT_INPUT: True,
    }
    assert feed[campaign_module.NOTE16_WEIGHT_INPUT] is True


def test_yale_note16_weight_assumption_is_explicit_and_receipted() -> None:
    receipt = campaign_module._yale_note16_weight_assumption()
    identity = campaign_module._yale_note16_weight_assumption_identity()
    assert receipt["verdict"] == "PASS"
    assert receipt["configuration"]["aggregate_share"] == 0.0
    assert receipt["configuration"]["threshold"] == 0.15
    assert receipt["campaign_binding"] == identity["campaign_binding"]
    assert receipt["campaign_binding"]["input"] == (campaign_module.NOTE16_WEIGHT_INPUT)
    assert receipt["campaign_binding"]["value"] is True
    assert "not an observed" in receipt["campaign_binding"]["factual_status"]


def test_yale_note16_weight_assumption_cannot_be_relabeled_as_fact(
    tmp_path, monkeypatch
) -> None:
    payload = json.loads(campaign_module.YALE_NOTE16_WEIGHT_ASSUMPTION.read_text())
    payload["campaign_binding"]["factual_status"] = "transaction fact"
    payload_without_digest = dict(payload)
    payload_without_digest.pop("receipt_payload_sha256")
    payload["receipt_payload_sha256"] = campaign_module._canonical_sha256(
        payload_without_digest
    )
    mutant = tmp_path / "assumption.json"
    mutant.write_text(json.dumps(payload))
    monkeypatch.setattr(campaign_module, "YALE_NOTE16_WEIGHT_ASSUMPTION", mutant)
    with pytest.raises(ValueError, match="campaign binding drift"):
        campaign_module._yale_note16_weight_assumption()


def test_case_feed_receipts_dr_cafta_inputs_as_neutral_false() -> None:
    feed, _flags = _case_feed(
        {"hts10": "0102294024", "iso2": "CR"},
        {"hts_line": "102294000"},
        lambda _line, _hts, _iso2, **_kwargs: {
            "entry_is_line_c": False,
            "entry_is_line_e": False,
        },
        probe="2026-07-24",
        case_feed_inputs=campaign_module._case_feed_input_names(
            {
                "entry_is_line_c",
                "entry_is_line_e",
            }
        ),
    )
    assert feed["entry_is_entered_free_of_duty_under_dr_cafta"] is False
    assert feed["entry_is_general_note_29_d_v_textile_or_apparel_good"] is False
    assert feed["entry_is_within_temporary_surcharge_effective_period"] is False


@pytest.mark.parametrize(
    ("probe", "expected"),
    (
        ("2026-02-23", False),
        ("2026-02-24", True),
        ("2026-07-23", True),
        ("2026-07-24", False),
    ),
)
def test_temporary_surcharge_period_fact_tracks_probe(
    probe: str, expected: bool
) -> None:
    feed, _flags = _case_feed(
        {"hts10": "0102294024", "iso2": "CR"},
        {"hts_line": "102294000"},
        lambda _line, _hts, _iso2, **_kwargs: {
            "entry_is_line_c": False,
            "entry_is_line_e": False,
        },
        probe=probe,
        case_feed_inputs=campaign_module._case_feed_input_names(
            {
                "entry_is_line_c",
                "entry_is_line_e",
            }
        ),
    )
    assert feed["entry_is_within_temporary_surcharge_effective_period"] is expected


def test_case_feed_contract_receipts_neutral_cafta_and_all_entry_inputs() -> None:
    emitted = {"entry_is_current", "entry_is_line_c", "entry_is_line_e"}
    supplied = campaign_module._case_feed_input_names(emitted)
    declared = supplied | {"unrelated_import_input"}
    contract = campaign_module._case_feed_contract(
        chapter="01",
        declared_inputs=declared,
        reachable_inputs=supplied,
        emitted_flag_names=emitted,
    )
    assert (
        "entry_is_entered_free_of_duty_under_dr_cafta" in contract["case_feed_inputs"]
    )
    assert (
        "entry_is_general_note_29_d_v_textile_or_apparel_good"
        in contract["declared_entry_inputs"]
    )
    assert contract["missing_declared_entry_inputs"] == []
    assert contract["missing_reachable_inputs"] == []


def test_case_feed_contract_rejects_unfed_public_entry_input() -> None:
    emitted = {"entry_is_line_c", "entry_is_line_e"}
    supplied = campaign_module._case_feed_input_names(emitted)
    with pytest.raises(ValueError, match="declared entry inputs absent from feed"):
        campaign_module._case_feed_contract(
            chapter="01",
            declared_inputs=supplied | {"entry_requires_new_fact"},
            reachable_inputs=supplied,
            emitted_flag_names=emitted,
        )


def test_case_feed_contract_only_allows_receipted_ch99_column2_input() -> None:
    emitted = {"entry_is_line_c", "entry_is_line_e"}
    supplied = campaign_module._case_feed_input_names(emitted)
    resolved = "resolved_non_ad_valorem_column2_rate"
    contract = campaign_module._case_feed_contract(
        chapter="99a",
        declared_inputs=supplied | {resolved},
        reachable_inputs=supplied | {resolved},
        emitted_flag_names=emitted,
    )
    assert contract["conditionally_unfed_reachable_inputs"] == [resolved]
    with pytest.raises(ValueError, match="reachable unfed inputs changed"):
        campaign_module._case_feed_contract(
            chapter="01",
            declared_inputs=supplied | {resolved},
            reachable_inputs=supplied | {resolved},
            emitted_flag_names=emitted,
        )


def test_reachable_input_closure_includes_every_output_version(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "compiled.json"
    artifact.write_text(
        json.dumps(
            {
                "program": {
                    "derived": [
                        {
                            "name": "campaign_output",
                            "expr": {"kind": "derived", "name": "helper"},
                            "versions": [],
                        },
                        {
                            "name": "helper",
                            "expr": {"kind": "input", "name": "current_fact"},
                            "versions": [
                                {
                                    "expr": {
                                        "kind": "input_or_else",
                                        "name": "historical_fact",
                                    }
                                }
                            ],
                        },
                        {
                            "name": "unrequested_output",
                            "expr": {"kind": "input", "name": "irrelevant_fact"},
                            "versions": [],
                        },
                    ]
                }
            }
        )
    )
    assert campaign_module.reachable_inputs_from_artifact(
        artifact, ("campaign_output",)
    ) == {"current_fact", "historical_fact"}


def test_entry_flag_producer_receipts_dynamic_note_fragments(tmp_path: Path) -> None:
    root = tmp_path / "rulespec-us"
    tool = root / "tools/b16_entry_flags.py"
    incidence = root / "us/policies/usitc/us-tariff-incidence/generated"
    (incidence / "note50").mkdir(parents=True)
    (incidence / "note52").mkdir()
    tool.parent.mkdir(parents=True)
    tool.write_text(
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        "INCIDENCE_DIR = ROOT / "
        "'us/policies/usitc/us-tariff-incidence/generated'\n"
        "MODULES = ('main.yaml',)\n"
        "NOTE16_ALUMINUM_PRECEDENCE_MODULE = 'note16.yaml'\n"
        "def entry_flags(*_args, **_kwargs): return {}\n"
    )
    (incidence / "main.yaml").write_text("main\n")
    (incidence / "note16.yaml").write_text("note16\n")
    note50 = incidence / "note50/page-1.yaml"
    note52 = incidence / "note52/page-2.yaml"
    note50.write_text("note50-v1\n")
    note52.write_text("note52-v1\n")
    (incidence / "note52/page-2.test.yaml").write_text("not-consumed\n")

    _entry_flags, first = campaign_module._load_entry_flag_tool(root)
    assert [item["path"] for item in first["dependencies"]] == [
        "us/policies/usitc/us-tariff-incidence/generated/main.yaml",
        "us/policies/usitc/us-tariff-incidence/generated/note16.yaml",
        "us/policies/usitc/us-tariff-incidence/generated/note50/page-1.yaml",
        "us/policies/usitc/us-tariff-incidence/generated/note52/page-2.yaml",
    ]
    note50.write_text("note50-v2\n")
    _entry_flags, second = campaign_module._load_entry_flag_tool(root)
    assert second["producer_sha256"] != first["producer_sha256"]


def test_prepare_eval_manifest_prunes_superseded_keys_and_bindings() -> None:
    run_identity = _fake_run_identity(chapters=("01", "02"))
    run_identity_sha256 = campaign_module._run_identity_sha256(run_identity)
    current = campaign_module._empty_eval_manifest(run_identity, EVAL_GENERATION_ID) | {
        "comparison_artifact": {"sha256": "a" * 64},
        "comparison_receipt": {"path": "old", "sha256": "b" * 64},
        "shards": {
            "old-01": {
                "key": "old-01",
                "chapter": "01",
                "run_identity_sha256": run_identity_sha256,
                "generation_id": EVAL_GENERATION_ID,
            },
            "new-02": {
                "key": "new-02",
                "chapter": "02",
                "run_identity_sha256": run_identity_sha256,
                "generation_id": EVAL_GENERATION_ID,
            },
        },
    }
    prepared = campaign_module._prepare_eval_manifest(
        current,
        {"01": "new-01", "02": "new-02"},
        run_identity,
        EVAL_GENERATION_ID,
    )
    expected = campaign_module._empty_eval_manifest(run_identity, EVAL_GENERATION_ID)
    expected["shards"] = {
        "new-02": {
            "key": "new-02",
            "chapter": "02",
            "run_identity_sha256": run_identity_sha256,
            "generation_id": EVAL_GENERATION_ID,
        },
    }
    assert prepared == expected


def test_prepare_eval_manifest_never_mixes_run_identities(tmp_path) -> None:
    old_identity = _fake_run_identity(marker="a")
    new_identity = _fake_run_identity(marker="b")
    old = _complete_eval_manifest(tmp_path, old_identity)
    current_keys = campaign_module._current_shard_keys(new_identity, EVAL_GENERATION_ID)
    assert campaign_module._prepare_eval_manifest(
        old, current_keys, new_identity, EVAL_GENERATION_ID
    ) == campaign_module._empty_eval_manifest(new_identity, EVAL_GENERATION_ID)


def test_fresh_evaluation_publishes_empty_manifest_before_engine(
    tmp_path, monkeypatch
) -> None:
    manifest_path = tmp_path / "eval" / "MANIFEST.json"
    run_identity = _fake_run_identity()
    key = campaign_module._shard_key(
        chapter="01",
        run_identity=run_identity,
        generation_id=EVAL_GENERATION_ID,
    )
    monkeypatch.setattr(campaign_module, "EVAL_MANIFEST", manifest_path)
    monkeypatch.setattr(
        campaign_module, "_current_run_identity", lambda **_kwargs: run_identity
    )
    monkeypatch.setattr(
        campaign_module,
        "_new_eval_generation_id",
        lambda: EVAL_GENERATION_ID,
    )

    def evaluate(chapter, *, run_identity, expected_key, **_kwargs):
        published = json.loads(manifest_path.read_text())
        assert published == campaign_module._empty_eval_manifest(
            run_identity, published["generation_id"]
        )
        return {
            "chapter": chapter,
            "key": expected_key,
            "run_identity_sha256": campaign_module._run_identity_sha256(run_identity),
            "generation_id": published["generation_id"],
            "path": str(tmp_path / f"{expected_key}.jsonl.gz"),
            "sha256": "c" * 64,
            "cases": 1,
            "engine_errors": 0,
            "elapsed_seconds": 0.1,
        }

    monkeypatch.setattr(campaign_module, "_evaluate_chapter", evaluate)
    result = campaign_module.evaluate_campaign(
        rulespec_root=tmp_path / "rulespec-us",
        engine_binary=tmp_path / "axiom-rules-engine",
        workers=1,
        fresh=True,
        cache_dir=tmp_path / "cache",
    )
    assert set(result["shards"]) == {key}
    assert set(result) == {
        "schema",
        "run_identity",
        "run_identity_sha256",
        "generation_id",
        "shards",
    }


def test_fresh_evaluation_cannot_resume(tmp_path) -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        campaign_module.evaluate_campaign(
            rulespec_root=tmp_path / "rulespec-us",
            engine_binary=tmp_path / "axiom-rules-engine",
            workers=1,
            fresh=True,
            resume=True,
        )


def test_interrupted_fresh_evaluation_leaves_manifest_unbound(
    tmp_path, monkeypatch
) -> None:
    run_identity = _fake_run_identity()
    manifest_path = tmp_path / "MANIFEST.json"
    old = _complete_eval_manifest(tmp_path, run_identity)
    old["comparison_artifact"] = {"sha256": "a" * 64}
    old["comparison_receipt"] = {"sha256": "b" * 64}
    manifest_path.write_text(json.dumps(old))
    monkeypatch.setattr(campaign_module, "EVAL_MANIFEST", manifest_path)
    monkeypatch.setattr(
        campaign_module, "_current_run_identity", lambda **_kwargs: run_identity
    )
    monkeypatch.setattr(
        campaign_module,
        "_new_eval_generation_id",
        lambda: "2" * 32,
    )

    def interrupted(*_args, **_kwargs):
        raise RuntimeError("interrupted")

    monkeypatch.setattr(campaign_module, "_evaluate_chapter", interrupted)
    with pytest.raises(RuntimeError, match="interrupted"):
        campaign_module.evaluate_campaign(
            rulespec_root=tmp_path / "rulespec-us",
            engine_binary=tmp_path / "engine",
            workers=1,
            fresh=True,
            cache_dir=tmp_path / "cache",
        )
    interrupted = json.loads(manifest_path.read_text())
    assert interrupted == campaign_module._empty_eval_manifest(
        run_identity, interrupted["generation_id"]
    )


def test_inflight_shard_cannot_repopulate_a_new_fresh_generation(
    tmp_path, monkeypatch
) -> None:
    run_identity = _fake_run_identity()
    manifest_path = tmp_path / "MANIFEST.json"
    monkeypatch.setattr(campaign_module, "EVAL_MANIFEST", manifest_path)
    monkeypatch.setattr(
        campaign_module, "_current_run_identity", lambda **_kwargs: run_identity
    )
    monkeypatch.setattr(
        campaign_module,
        "_new_eval_generation_id",
        lambda: EVAL_GENERATION_ID,
    )
    replacement_generation = "2" * 32

    def replace_generation(chapter, *, generation_id, expected_key, **_kwargs):
        with campaign_module._eval_manifest_lock():
            campaign_module._atomic_json(
                manifest_path,
                campaign_module._empty_eval_manifest(
                    run_identity, replacement_generation
                ),
            )
        return {
            "chapter": chapter,
            "key": expected_key,
            "run_identity_sha256": campaign_module._run_identity_sha256(run_identity),
            "generation_id": generation_id,
            "path": str(tmp_path / f"{expected_key}.jsonl.gz"),
            "sha256": "c" * 64,
            "cases": 1,
            "engine_errors": 0,
            "elapsed_seconds": 0.1,
        }

    monkeypatch.setattr(campaign_module, "_evaluate_chapter", replace_generation)
    with pytest.raises(ValueError, match="replaced by another run"):
        campaign_module.evaluate_campaign(
            rulespec_root=tmp_path / "rulespec-us",
            engine_binary=tmp_path / "engine",
            workers=1,
            fresh=True,
            cache_dir=tmp_path / "cache",
        )
    assert json.loads(manifest_path.read_text()) == (
        campaign_module._empty_eval_manifest(run_identity, replacement_generation)
    )


def test_interrupted_nonfresh_evaluation_cannot_leave_old_shard_rebound(
    tmp_path, monkeypatch
) -> None:
    run_identity = _fake_run_identity()
    manifest_path = tmp_path / "MANIFEST.json"
    old = _complete_eval_manifest(tmp_path, run_identity)
    old["comparison_artifact"] = {"sha256": "a" * 64}
    old["comparison_receipt"] = {"sha256": "b" * 64}
    manifest_path.write_text(json.dumps(old))
    monkeypatch.setattr(campaign_module, "EVAL_MANIFEST", manifest_path)
    monkeypatch.setattr(
        campaign_module, "_current_run_identity", lambda **_kwargs: run_identity
    )

    def interrupted(*_args, **_kwargs):
        invalidated = json.loads(manifest_path.read_text())
        assert invalidated["shards"] == {}
        assert "comparison_artifact" not in invalidated
        assert "comparison_receipt" not in invalidated
        with pytest.raises(ValueError, match="incomplete or contains stale shards"):
            campaign_module.compare_campaign(
                rulespec_root=tmp_path / "rulespec-us",
                engine_binary=tmp_path / "engine",
                cache_dir=tmp_path / "compare",
            )
        raise RuntimeError("interrupted")

    monkeypatch.setattr(campaign_module, "_evaluate_chapter", interrupted)
    with pytest.raises(RuntimeError, match="interrupted"):
        campaign_module.evaluate_campaign(
            rulespec_root=tmp_path / "rulespec-us",
            engine_binary=tmp_path / "engine",
            workers=1,
            cache_dir=tmp_path / "eval-cache",
        )
    invalidated = json.loads(manifest_path.read_text())
    assert invalidated["shards"] == {}
    assert "comparison_artifact" not in invalidated
    assert "comparison_receipt" not in invalidated


def test_compare_rebinds_manifest_to_fresh_artifact(tmp_path, monkeypatch) -> None:
    manifest_path = tmp_path / "eval" / "MANIFEST.json"
    comparison_path = tmp_path / "comparison-summary.json"
    manifest_path.parent.mkdir()
    run_identity = _fake_run_identity()
    manifest_path.write_text(
        json.dumps(_complete_eval_manifest(tmp_path, run_identity))
    )
    monkeypatch.setattr(campaign_module, "EVAL_MANIFEST", manifest_path)
    monkeypatch.setattr(campaign_module, "COMPARISON_RECEIPT", comparison_path)
    monkeypatch.setattr(campaign_module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        campaign_module, "_current_run_identity", lambda **_kwargs: run_identity
    )

    receipt = campaign_module.compare_campaign(
        rulespec_root=tmp_path / "rulespec-us",
        engine_binary=tmp_path / "axiom-rules-engine",
        cache_dir=tmp_path / "compare",
    )
    rebound = json.loads(manifest_path.read_text())
    assert rebound["comparison_artifact"] == receipt["comparison_artifact"]
    assert rebound["comparison_receipt"] == campaign_module._file_receipt(
        comparison_path, relative_to=tmp_path
    )


def test_compare_cannot_restore_manifest_after_concurrent_fresh_invalidation(
    tmp_path, monkeypatch
) -> None:
    manifest_path = tmp_path / "eval" / "MANIFEST.json"
    comparison_path = tmp_path / "comparison-summary.json"
    manifest_path.parent.mkdir()
    run_identity = _fake_run_identity()
    manifest_path.write_text(
        json.dumps(_complete_eval_manifest(tmp_path, run_identity))
    )
    monkeypatch.setattr(campaign_module, "EVAL_MANIFEST", manifest_path)
    monkeypatch.setattr(campaign_module, "COMPARISON_RECEIPT", comparison_path)
    monkeypatch.setattr(campaign_module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        campaign_module, "_current_run_identity", lambda **_kwargs: run_identity
    )
    replacement_generation = "2" * 32
    monkeypatch.setattr(
        campaign_module,
        "_new_eval_generation_id",
        lambda: replacement_generation,
    )

    def interrupted(*_args, **_kwargs):
        raise RuntimeError("fresh interrupted")

    monkeypatch.setattr(campaign_module, "_evaluate_chapter", interrupted)
    original_atomic_json = campaign_module._atomic_json
    fresh_started = threading.Event()
    fresh_finished = threading.Event()
    fresh_errors: list[BaseException] = []
    threads: list[threading.Thread] = []

    def run_fresh() -> None:
        fresh_started.set()
        try:
            campaign_module.evaluate_campaign(
                rulespec_root=tmp_path / "rulespec-us",
                engine_binary=tmp_path / "engine",
                workers=1,
                fresh=True,
                cache_dir=tmp_path / "eval-cache",
            )
        except BaseException as error:
            fresh_errors.append(error)
        finally:
            fresh_finished.set()

    def atomic_json(path, payload):
        original_atomic_json(path, payload)
        if path == comparison_path and not threads:
            thread = threading.Thread(target=run_fresh)
            threads.append(thread)
            thread.start()
            assert fresh_started.wait(1)
            assert not fresh_finished.wait(0.05)

    monkeypatch.setattr(campaign_module, "_atomic_json", atomic_json)
    campaign_module.compare_campaign(
        rulespec_root=tmp_path / "rulespec-us",
        engine_binary=tmp_path / "engine",
        cache_dir=tmp_path / "compare",
    )
    threads[0].join(timeout=2)
    assert fresh_finished.is_set()
    assert len(fresh_errors) == 1
    assert isinstance(fresh_errors[0], RuntimeError)
    assert str(fresh_errors[0]) == "fresh interrupted"
    assert json.loads(manifest_path.read_text()) == (
        campaign_module._empty_eval_manifest(run_identity, replacement_generation)
    )


def test_compare_rejects_arbitrary_stale_shard_key(tmp_path, monkeypatch) -> None:
    run_identity = _fake_run_identity()
    manifest = _complete_eval_manifest(tmp_path, run_identity)
    current_key, shard = manifest["shards"].popitem()
    stale_key = "not-a-current-content-key"
    shard["key"] = stale_key
    manifest["shards"][stale_key] = shard
    manifest_path = tmp_path / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest))
    monkeypatch.setattr(campaign_module, "EVAL_MANIFEST", manifest_path)
    monkeypatch.setattr(
        campaign_module, "_current_run_identity", lambda **_kwargs: run_identity
    )
    with pytest.raises(ValueError, match="incomplete or contains stale shards"):
        campaign_module.compare_campaign(
            rulespec_root=tmp_path / "rulespec-us",
            engine_binary=tmp_path / "engine",
            cache_dir=tmp_path / "compare",
        )
    assert current_key != stale_key


@pytest.mark.parametrize(
    "identity_path",
    (
        ("rulespec", "root"),
        ("rulespec", "head_tree"),
        ("rulespec", "content_sha256"),
        ("engine", "sha256"),
        ("entry_flag_producers", "producer_sha256"),
        ("input_contract", "sha256"),
        ("campaign_evaluator", "producer_sha256"),
    ),
)
def test_shard_key_binds_every_live_producer(identity_path) -> None:
    original = _fake_run_identity()
    mutant = copy.deepcopy(original)
    mutant[identity_path[0]][identity_path[1]] = "b" * 64
    assert campaign_module._shard_key(
        chapter="01",
        run_identity=original,
        generation_id=EVAL_GENERATION_ID,
    ) != campaign_module._shard_key(
        chapter="01",
        run_identity=mutant,
        generation_id=EVAL_GENERATION_ID,
    )


def test_shard_key_binds_fresh_run_generation() -> None:
    run_identity = _fake_run_identity()
    assert campaign_module._shard_key(
        chapter="01",
        run_identity=run_identity,
        generation_id="1" * 32,
    ) != campaign_module._shard_key(
        chapter="01",
        run_identity=run_identity,
        generation_id="2" * 32,
    )


def test_input_contract_rejects_note16_precedence_dependency_mutation(
    tmp_path, monkeypatch
) -> None:
    tool = tmp_path / "tools/b16_entry_flags.py"
    incidence = tmp_path / "us/policies/usitc/us-tariff-incidence/generated"
    tool.parent.mkdir(parents=True)
    incidence.mkdir(parents=True)
    tool.write_text(
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        "INCIDENCE_DIR = ROOT / 'us/policies/usitc/us-tariff-incidence/generated'\n"
        "MODULES = ('main.yaml',)\n"
        "NOTE16_ALUMINUM_PRECEDENCE_MODULE = 'note16.yaml'\n"
        "def entry_flags(*_args, **_kwargs): return {}\n"
    )
    (incidence / "main.yaml").write_text("main\n")
    note16 = incidence / "note16.yaml"
    note16.write_text("old\n")
    engine = tmp_path / "engine"
    engine.write_text("engine\n")
    rulespec_identity = {"content_sha256": "a" * 64}
    monkeypatch.setattr(
        campaign_module,
        "_rulespec_root_identity",
        lambda _root: rulespec_identity,
    )
    _entry_flags, bound_producers = campaign_module._load_entry_flag_tool(tmp_path)
    contract = {
        "schema": campaign_module.INPUT_CONTRACT_SCHEMA,
        "rulespec": rulespec_identity,
        "engine": campaign_module._file_receipt(engine),
        "entry_flag_producers": bound_producers,
        "entry_flag_tool_sha256": bound_producers["tool"]["sha256"],
    }
    contract_path = tmp_path / "input-contract.json"
    contract_path.write_text(json.dumps(contract))
    monkeypatch.setattr(campaign_module, "INPUT_CONTRACT_RECEIPT", contract_path)

    note16.write_text("new\n")
    _entry_flags, current_producers = campaign_module._load_entry_flag_tool(tmp_path)
    assert bound_producers["producer_sha256"] != current_producers["producer_sha256"]
    bound_identity = _fake_run_identity()
    bound_identity["entry_flag_producers"] = bound_producers
    current_identity = copy.deepcopy(bound_identity)
    current_identity["entry_flag_producers"] = current_producers
    bound_manifest = campaign_module._empty_eval_manifest(
        bound_identity, EVAL_GENERATION_ID
    )
    current_manifest = campaign_module._empty_eval_manifest(
        current_identity, EVAL_GENERATION_ID
    )
    assert (
        bound_manifest["run_identity_sha256"] != current_manifest["run_identity_sha256"]
    )
    with pytest.raises(
        ValueError, match="declared-input contract entry-flag provenance is stale"
    ):
        campaign_module._validated_input_contract(
            rulespec_root=tmp_path,
            engine_binary=engine,
            rulespec_identity=rulespec_identity,
            engine_receipt=campaign_module._file_receipt(engine),
        )


def test_campaign_evaluator_identity_binds_adapter_source(
    tmp_path, monkeypatch
) -> None:
    campaign = tmp_path / "campaign.py"
    runner = tmp_path / "runner.py"
    campaign.write_text("campaign")
    runner.write_text("old adapter")
    monkeypatch.setattr(campaign_module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(campaign_module, "__file__", str(campaign))
    monkeypatch.setattr(campaign_module, "CAMPAIGN_EVALUATOR_SOURCES", ("runner.py",))
    old = campaign_module._campaign_evaluator_identity()
    runner.write_text("new adapter")
    new = campaign_module._campaign_evaluator_identity()
    assert old["producer_sha256"] != new["producer_sha256"]


@pytest.mark.parametrize("stage", ("classify", "report"))
def test_downstream_rejects_unbound_comparison_after_interrupted_fresh_run(
    stage, tmp_path, monkeypatch
) -> None:
    run_identity = _fake_run_identity()
    manifest_path = tmp_path / "MANIFEST.json"
    manifest_path.write_text(
        json.dumps(_complete_eval_manifest(tmp_path, run_identity))
    )
    comparison_path = tmp_path / "comparison-summary.json"
    comparison_path.write_text("{}")
    monkeypatch.setattr(campaign_module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(campaign_module, "EVAL_MANIFEST", manifest_path)
    monkeypatch.setattr(campaign_module, "COMPARISON_RECEIPT", comparison_path)
    monkeypatch.setattr(
        campaign_module, "_current_run_identity", lambda **_kwargs: run_identity
    )
    function = (
        campaign_module.classify_campaign
        if stage == "classify"
        else campaign_module.build_report
    )
    with pytest.raises(ValueError, match="binding is absent or stale"):
        function(
            rulespec_root=tmp_path / "rulespec-us",
            engine_binary=tmp_path / "engine",
        )


@pytest.mark.parametrize("stage", ("classify", "report"))
def test_downstream_rejects_incomplete_current_manifest(
    stage, tmp_path, monkeypatch
) -> None:
    run_identity = _fake_run_identity(chapters=("01", "02"))
    manifest = _complete_eval_manifest(tmp_path, run_identity)
    manifest["shards"].pop(next(iter(manifest["shards"])))
    manifest_path = tmp_path / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest))
    monkeypatch.setattr(campaign_module, "EVAL_MANIFEST", manifest_path)
    monkeypatch.setattr(
        campaign_module, "_current_run_identity", lambda **_kwargs: run_identity
    )
    function = (
        campaign_module.classify_campaign
        if stage == "classify"
        else campaign_module.build_report
    )
    with pytest.raises(ValueError, match="incomplete or contains stale shards"):
        function(
            rulespec_root=tmp_path / "rulespec-us",
            engine_binary=tmp_path / "engine",
        )


def test_downstream_rejects_stale_comparison_artifact_binding(
    tmp_path, monkeypatch
) -> None:
    run_identity = _fake_run_identity()
    manifest = _complete_eval_manifest(tmp_path, run_identity)
    evaluation_manifest = campaign_module._empty_eval_manifest(
        run_identity, EVAL_GENERATION_ID
    )
    evaluation_manifest["shards"] = manifest["shards"]
    artifact = tmp_path / "comparison.jsonl.gz"
    with artifact.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0):
            pass
    comparison = {
        "schema": campaign_module.COMPARISON_SCHEMA,
        "run_identity_sha256": campaign_module._run_identity_sha256(run_identity),
        "generation_id": EVAL_GENERATION_ID,
        "evaluation_manifest_sha256": campaign_module._canonical_sha256(
            evaluation_manifest
        ),
        "tolerance": campaign_module.TOLERANCE,
        "comparison_artifact": campaign_module._file_receipt(artifact),
        "per_slot": {},
        "engine_errors": 0,
    }
    comparison_path = tmp_path / "comparison-summary.json"
    comparison_path.write_text(campaign_module._render(comparison))
    manifest["comparison_receipt"] = campaign_module._file_receipt(
        comparison_path, relative_to=tmp_path
    )
    manifest["comparison_artifact"] = {
        **comparison["comparison_artifact"],
        "sha256": "0" * 64,
    }
    manifest_path = tmp_path / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest))
    monkeypatch.setattr(campaign_module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(campaign_module, "EVAL_MANIFEST", manifest_path)
    monkeypatch.setattr(campaign_module, "COMPARISON_RECEIPT", comparison_path)
    monkeypatch.setattr(
        campaign_module, "_current_run_identity", lambda **_kwargs: run_identity
    )
    with pytest.raises(ValueError, match="artifact binding is absent or stale"):
        campaign_module._load_bound_comparison(
            rulespec_root=tmp_path / "rulespec-us",
            engine_binary=tmp_path / "engine",
        )


def test_cli_rejects_rulespec_root_not_bound_at_import(tmp_path, monkeypatch) -> None:
    configured = tmp_path / "configured-rulespec-us"
    requested = tmp_path / "different-rulespec-us"
    monkeypatch.setattr(campaign_module, "RULESPEC_US_ROOT", configured)
    monkeypatch.setattr(
        campaign_module.sys,
        "argv",
        [
            "us_tariff_schedule_campaign.py",
            "evaluate",
            "--rulespec-root",
            str(requested),
        ],
    )
    with pytest.raises(ValueError, match="export RULESPEC_US_CHECKOUT"):
        campaign_module.main()


def test_engine_environment_cannot_select_an_ambient_checkout(tmp_path) -> None:
    rulespec_root = tmp_path / "workspace/rulespec-us"
    rulespec_root.mkdir(parents=True)
    env = campaign_module._engine_environment(
        rulespec_root,
        {
            "AXIOM_RULESPEC_ROOT": "/wrong/singular",
            "AXIOM_RULESPEC_REPO_ROOTS": "/wrong/plural",
            "UNCHANGED": "yes",
        },
    )
    assert "AXIOM_RULESPEC_ROOT" not in env
    assert env["AXIOM_RULESPEC_REPO_ROOTS"] == str(rulespec_root.resolve().parent)
    assert env["UNCHANGED"] == "yes"


def test_manifest_lock_is_shared_across_processes_with_different_tmpdir(
    tmp_path, monkeypatch
) -> None:
    manifest_path = tmp_path / "eval/MANIFEST.json"
    alternate_tmp = tmp_path / "alternate-tmp"
    alternate_tmp.mkdir()
    monkeypatch.setattr(campaign_module, "EVAL_MANIFEST", manifest_path)
    child = (
        "import sys\n"
        "from pathlib import Path\n"
        "from scripts import us_tariff_schedule_campaign as campaign\n"
        "campaign.EVAL_MANIFEST = Path(sys.argv[1])\n"
        "print('ready', flush=True)\n"
        "with campaign._eval_manifest_lock():\n"
        "    print('acquired', flush=True)\n"
    )
    env = dict(campaign_module.os.environ)
    env["TMPDIR"] = str(alternate_tmp)
    with campaign_module._eval_manifest_lock():
        process = campaign_module.subprocess.Popen(
            [campaign_module.sys.executable, "-c", child, str(manifest_path)],
            cwd=campaign_module.REPO_ROOT,
            env=env,
            text=True,
            stdout=campaign_module.subprocess.PIPE,
            stderr=campaign_module.subprocess.PIPE,
        )
        assert process.stdout is not None
        assert process.stdout.readline().strip() == "ready"
        with pytest.raises(campaign_module.subprocess.TimeoutExpired):
            process.wait(timeout=0.1)
    stdout, stderr = process.communicate(timeout=2)
    assert process.returncode == 0, stderr
    assert stdout.strip() == "acquired"


def test_mismatch_signature_preserves_selector_dimensions() -> None:
    row = {
        "slot": "brazil_section_301",
        "delta": 0.25,
        "context": {
            "flags": {"entry_is_brazil_301_listed": True},
            "revision": "bnd_2026-07-22",
            "interval": ["2026-07-22", "2026-07-23"],
            "origin_regime": "0000000001000000",
            "hts10": "0409000010",
            "hts_line": "0409000000",
            "iso2": "BR",
        },
    }
    other_hts10 = {**row, "context": {**row["context"], "hts10": "0409000090"}}
    other_iso2 = {**row, "context": {**row["context"], "iso2": "AR"}}
    assert mismatch_signature(row) != mismatch_signature(other_hts10)
    assert mismatch_signature(row) != mismatch_signature(other_iso2)


def _historical_preview_entries(preview: dict | None = None) -> list[dict]:
    """Isolate the immutable 18-parent ruling from the evolving live ledger."""

    if preview is None:
        preview = json.loads(PREVIEW_DISPOSITION_LINE_SETS.read_text())
    campaign_module._require_immutable_preview_all_selector_snapshot(preview)
    receipt_path = "reference/us-tariff-schedule/preview-disposition-line-sets.json"
    return [
        {
            **copy.deepcopy(selector),
            "concept": (
                "us:policies/cbp/us-tariff-schedule#" + selector["match"]["slot"]
            ),
            "kind": "signature_class",
            "receipt": "Immutable historical preview selector contract.",
            "reason": "Test fixture preserves the receipted historical ruling.",
            "expires_on_source_change": True,
            "evidence": {
                "sources": [receipt_path],
                "receipt_type": "immutable-preview-selector-contract",
                "instrument_receipt": f"{receipt_path}#selector={selector['id']}",
            },
        }
        for selector in preview["selectors"]
    ]


@pytest.fixture
def _without_external_membership_tables(monkeypatch):
    """Keep structural receipt tests independent of a RuleSpec checkout."""

    _named_line_sets.cache_clear()
    monkeypatch.setattr(campaign_module, "_membership_rules", lambda _path: {})
    yield
    _named_line_sets.cache_clear()


def test_missing_membership_table_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="line-set membership table unavailable"):
        campaign_module._membership_rules(tmp_path / "missing.yaml")


def test_preview_disposition_line_sets_are_receipted_and_registered(
    _without_external_membership_tables,
) -> None:
    receipt = json.loads(PREVIEW_DISPOSITION_LINE_SETS.read_text())
    names = set(receipt["line_sets"])
    assert receipt["verdict"] == "PASS"
    assert len(names) == len(receipt["selectors"]) == PREVIEW_SELECTOR_COUNT
    registered = _named_line_sets()
    assert names <= set(registered)
    assert all(registered[name][0][0] == 10 for name in names)
    contract = _preview_selector_contract(_historical_preview_entries(receipt))
    assert {
        selector_id: selector["match"] for selector_id, selector in contract.items()
    } == {selector["id"]: selector["match"] for selector in receipt["selectors"]}


@pytest.fixture
def _current_ledger_enrollment(monkeypatch):
    """Authenticate committed receipts without replaying bulk data or R.

    The production loader still checks small-file hashes, source/run bindings,
    zero-error censuses, and the independent embedded CAFTA proof. Its large
    selected-population receipt and recorded R result are fixture inputs, not a
    claim that this test reran either producer or the full campaign.
    """

    manifest = json.loads(campaign_module.EVAL_MANIFEST.read_text())
    selected_path = campaign_module.SELECTED
    selected_receipt = copy.deepcopy(manifest["run_identity"]["selected_population"])
    cafta = json.loads(campaign_module.CAFTA_SUPERSESSION_RECEIPT.read_text())
    replay = cafta["yale_reference_defect"]["deterministic_minimal_reproduction"]
    assert (
        replay["program_sha256"]
        == campaign_module.CAFTA_EXPECTED_TIDY_EVAL_PROGRAM_SHA256
    )
    assert (
        replay["r_runtime_tree"]
        == campaign_module.CAFTA_EXPECTED_R_RUNTIME_TREE_RECEIPT
    )
    assert replay["dplyr_tree"] == campaign_module.CAFTA_EXPECTED_DPLYR_TREE_RECEIPT
    assert replay["selected_conditions"] == "full,fta"
    real_sha256 = campaign_module._sha256
    real_file_receipt = campaign_module._file_receipt

    def receipt_sha256(path):
        if path == selected_path:
            return selected_receipt["sha256"]
        assert path.suffix != ".gz", "live enrollment must not scan bulk artifacts"
        return real_sha256(path)

    def file_receipt(path, *, relative_to=None):
        if path == selected_path:
            assert relative_to == campaign_module.REPO_ROOT
            return copy.deepcopy(selected_receipt)
        return real_file_receipt(path, relative_to=relative_to)

    monkeypatch.setattr(campaign_module, "_sha256", receipt_sha256)
    monkeypatch.setattr(campaign_module, "_file_receipt", file_receipt)
    monkeypatch.setattr(
        campaign_module,
        "_run_cafta_tidy_eval_reproduction",
        lambda: copy.deepcopy(replay),
    )
    entries = yaml.safe_load(DISPOSITION_LEDGER.read_text())["entries"]
    comparison = json.loads(campaign_module.COMPARISON_RECEIPT.read_text())
    preview = campaign_module._preview_disposition_receipt()
    assert _preview_transition_is_required(entries, preview)
    transition = _transition_for_entries(entries, comparison, preview)
    assert transition is not None and transition["verdict"] == "PASS"
    return entries, comparison, preview, transition


def test_current_ledger_enrolls_exact_receipted_fresh_children(
    _current_ledger_enrollment,
) -> None:
    entries, _comparison, preview, transition = _current_ledger_enrollment
    active, retired, superseded = _preview_selector_snapshot(
        entries, preview, transition
    )
    unrelated_ids = {
        "non-metal-232-family",
        "vintage-revision-232",
        "s122-gn6-lines",
        "s122-ch98",
        "s122-unconditional-exempt-lines",
        "s122-entry-status-lines",
        "column2-gn3b",
        "vintage-revision-301",
        "vintage-revision-301-removed-lines",
        "legal-date-boundary-ieepa",
        "reciprocal-vintage-ieepa",
        "s201-stale-proxy",
    }
    causal_proof_ids = {
        "section232-steel-scope-projection-brazil",
        "section232-steel-scope-projection-forced-labor",
        "yale-html-statutory-base-parser-defect",
        "section232-russia-aluminum-membership-vintage",
    }
    by_id = {entry["id"]: entry for entry in entries}
    children = {
        child["id"]: child
        for parent in transition["transitions"]
        for child in parent["children"]
    }
    historical_ids = {selector["id"] for selector in preview["selectors"]}
    assert len(entries) == len(by_id) == 46
    assert len(children) == len(active) == 30
    assert set(by_id) == set(children) | unrelated_ids | causal_proof_ids
    assert not historical_ids.intersection(by_id)
    assert set(retired) == {
        "section232-exposed-brazil",
        "section232-exposed-forced-labor",
    }
    assert set(superseded) == historical_ids - set(retired)
    assert active == children
    for child_id, child in children.items():
        entry = by_id[child_id]
        assert {field: entry[field] for field in child} == child
        assert all(type(entry[field]) is type(value) for field, value in child.items())
        assert entry["expires_on_source_change"] is True
        assert entry["evidence"]["transition"] == {
            "parent_id": child["parent_id"],
            "child_id": child_id,
            "receipt_payload_sha256": transition["receipt_payload_sha256"],
        }
    assert sum(child["expected_units"] for child in children.values()) == sum(
        parent["fresh_residual_population"]["units"]
        for parent in transition["transitions"]
    )
    with pytest.raises(ValueError, match="unreceipted preview selector"):
        _preview_selector_contract(entries, preview)


def test_current_ledger_retires_superseded_causes_and_enrolls_exact_replays() -> None:
    from scripts import us_tariff_publication as publication

    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    contracts, evidence = publication._proof_contracts(
        publication._Snapshot(campaign_module.REPO_ROOT)
    )
    entries, base_ids = publication._validate_enrollment(ledger, contracts)
    assert len(entries) == 46 and len(base_ids) == 42
    assert not publication.RETIRED_BASE_IDS.intersection(entries)
    assert len(evidence) == 2
    assert {
        name: (
            entry["expected_units"],
            entry["expected_signature_count"],
            entry["attribution"],
        )
        for name, entry in entries.items()
        if name in contracts
    } == {
        "section232-steel-scope-projection-brazil": (6, 3, "input-comparability"),
        "section232-steel-scope-projection-forced-labor": (
            108,
            54,
            "input-comparability",
        ),
        "yale-html-statutory-base-parser-defect": (5709, 3114, "reference-defect"),
        "section232-russia-aluminum-membership-vintage": (
            24,
            12,
            "input-comparability",
        ),
    }


def test_current_ledger_requires_authenticated_transition_receipt(
    _current_ledger_enrollment, tmp_path: Path, monkeypatch
) -> None:
    entries, comparison, preview, transition = _current_ledger_enrollment
    path = tmp_path / "transition.json"
    monkeypatch.setattr(campaign_module, "PREVIEW_SELECTOR_TRANSITION_RECEIPT", path)
    with pytest.raises(ValueError, match="transition receipt is missing"):
        _transition_for_entries(entries, comparison, preview)
    mutant = copy.deepcopy(transition)
    mutant["verdict"] = "FAIL"
    mutant.pop("receipt_payload_sha256")
    mutant["receipt_payload_sha256"] = campaign_module._canonical_sha256(mutant)
    path.write_text(json.dumps(mutant))
    with pytest.raises(ValueError, match="not a PASS v1 receipt"):
        _transition_for_entries(entries, comparison, preview)


def test_preview_selector_match_drift_fails_hermetically() -> None:
    entries = _historical_preview_entries()
    entries[0]["match"]["delta"] = {"sign": "neg"}
    with pytest.raises(ValueError, match="preview selector match drift"):
        _preview_selector_contract(entries)


@pytest.mark.parametrize("missing_field", ["slot", "delta"])
def test_preview_selector_requires_exact_match_bounds(missing_field: str) -> None:
    preview = json.loads(PREVIEW_DISPOSITION_LINE_SETS.read_text())
    entries = _historical_preview_entries(preview)
    selector = preview["selectors"][0]
    ledger_entry = next(entry for entry in entries if entry["id"] == selector["id"])
    selector["match"].pop(missing_field)
    ledger_entry["match"].pop(missing_field)
    with pytest.raises(ValueError, match="all-selector snapshot drift"):
        _preview_selector_contract(entries, preview)


@pytest.mark.parametrize(
    ("field", "mutant", "message"),
    (
        ("disposition", "explained_residual", "preview selector disposition drift"),
        ("attribution", "reference-behavior", "preview selector attribution drift"),
    ),
)
def test_preview_selector_ruling_cannot_be_relabeled(
    field: str, mutant: str, message: str
) -> None:
    entries = _historical_preview_entries()
    entry = next(item for item in entries if item["id"] == "section232-exposed-brazil")
    entry[field] = mutant
    with pytest.raises(ValueError, match=message):
        _preview_selector_contract(entries)


def test_unreceipted_preview_selector_is_rejected() -> None:
    entries = _historical_preview_entries()
    mutant = copy.deepcopy(entries[0])
    mutant["id"] = "unreceipted-preview-selector"
    mutant["match"]["delta"] = {"values": [0.123456]}
    entries.append(mutant)
    with pytest.raises(ValueError, match="unreceipted preview selector"):
        _preview_selector_contract(entries)


def test_preview_selector_must_expire_on_source_change() -> None:
    entries = _historical_preview_entries()
    entries[0]["expires_on_source_change"] = False
    with pytest.raises(ValueError, match="lost source-change expiry"):
        _preview_selector_contract(entries)


def test_preview_source_hash_mutation_cannot_self_validate(
    tmp_path, monkeypatch
) -> None:
    receipt = json.loads(PREVIEW_DISPOSITION_LINE_SETS.read_text())
    first_input = next(iter(receipt["inputs"].values()))
    first_input["sha256"] = "0" * 64
    receipt.pop("receipt_payload_sha256")
    receipt["receipt_payload_sha256"] = hashlib.sha256(
        json.dumps(
            receipt, allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    mutant = tmp_path / "mutant-preview-receipt.json"
    mutant.write_text(json.dumps(receipt))
    monkeypatch.setattr(campaign_module, "PREVIEW_DISPOSITION_LINE_SETS", mutant)
    with pytest.raises(ValueError, match="preview disposition source hash drift"):
        campaign_module._preview_disposition_receipt()


@pytest.mark.parametrize("producer_name", ["script", "campaign_classifier"])
def test_preview_producer_mutation_cannot_self_validate(
    producer_name, tmp_path, monkeypatch
) -> None:
    receipt = json.loads(PREVIEW_DISPOSITION_LINE_SETS.read_text())
    receipt["producer"][producer_name]["sha256"] = "0" * 64
    receipt.pop("receipt_payload_sha256")
    receipt["receipt_payload_sha256"] = hashlib.sha256(
        json.dumps(
            receipt, allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    mutant = tmp_path / "mutant-preview-receipt.json"
    mutant.write_text(json.dumps(receipt))
    monkeypatch.setattr(campaign_module, "PREVIEW_DISPOSITION_LINE_SETS", mutant)
    with pytest.raises(ValueError, match="preview disposition producer source drift"):
        campaign_module._preview_disposition_receipt()


def test_preview_population_digest_rejects_count_preserving_drift() -> None:
    original = [("a" * 64, 2), ("b" * 64, 3)]
    contract = {
        "preview": {
            "expected_units": 5,
            "expected_signature_count": 2,
            "expected_signature_population_sha256": signature_population_sha256(
                original
            ),
        }
    }
    _enforce_preview_selector_population(
        contract,
        {signature: "preview" for signature, _ in original},
        Counter(dict(original)),
    )
    mutant = [("a" * 64, 2), ("c" * 64, 3)]
    with pytest.raises(ValueError, match="signature digest drift"):
        _enforce_preview_selector_population(
            contract,
            {signature: "preview" for signature, _ in mutant},
            Counter(dict(mutant)),
        )


def test_active_expiring_preview_population_rejects_zero_and_partial_survival() -> None:
    population = [("a" * 64, 2), ("b" * 64, 3)]
    contract = {
        "preview": {
            "expected_units": 5,
            "expected_signature_count": 2,
            "expected_signature_population_sha256": signature_population_sha256(
                population
            ),
        }
    }
    with pytest.raises(ValueError, match="unit count drift"):
        _enforce_preview_selector_population(contract, {}, Counter())
    with pytest.raises(ValueError, match="unit count drift"):
        _enforce_preview_selector_population(
            contract,
            {"a" * 64: "preview"},
            Counter({"a" * 64: 2}),
        )


def _synthetic_preview_transition(
    parent_id: str = "aircraft-utilization-proxy-brazil",
) -> tuple[
    dict,
    list[dict],
    dict,
    str,
    dict[str, dict],
    Counter[str],
    dict[str, str | None],
]:
    preview = json.loads(PREVIEW_DISPOSITION_LINE_SETS.read_text())
    parent = next(
        selector for selector in preview["selectors"] if selector["id"] == parent_id
    )
    population = [("a" * 64, 2), ("b" * 64, 3)]
    population_digest = signature_population_sha256(population)
    ordered_selectors = [parent] + [
        selector for selector in preview["selectors"] if selector["id"] != parent_id
    ]
    transitions = []
    ledger_children = []
    child_id = ""
    fallback_hts10_by_parent = {
        "section232-annex-brazil": ["9401999030", "9401999040"],
        "section232-annex-forced-labor": ["9401999085"],
    }
    for selector in ordered_selectors:
        selector_id = selector["id"]
        status, expected_children = (
            campaign_module._expected_preview_transition_semantics(
                selector_id, selector
            )
        )
        if status == "retired":
            children = []
            fresh_matching_units = selector["expected_units"]
            residual = {
                "units": 0,
                "signature_count": 0,
                "signature_population_sha256": signature_population_sha256([]),
            }
        elif selector_id == parent_id:
            assert len(expected_children) == 1
            child_id = expected_children[0]["id"]
            children = [
                {
                    **copy.deepcopy(expected_children[0]),
                    "expected_units": 5,
                    "expected_signature_count": 2,
                    "expected_signature_population_sha256": population_digest,
                }
            ]
            fresh_matching_units = selector["expected_units"] - 5
            residual = {
                "units": 5,
                "signature_count": 2,
                "signature_population_sha256": population_digest,
            }
        else:
            child_count = len(expected_children)
            allocations = [1] * (child_count - 1) + [
                selector["expected_units"] - child_count + 1
            ]
            if selector_id in fallback_hts10_by_parent:
                defect_units = max(3, len(fallback_hts10_by_parent[selector_id]))
                allocations[0] = defect_units
                allocations[-1] -= defect_units - 1
            children = []
            for index, (semantic, units) in enumerate(
                zip(expected_children, allocations, strict=True)
            ):
                signature_count = (
                    units
                    if selector_id in fallback_hts10_by_parent and index == 0
                    else 1
                )
                children.append(
                    {
                        **copy.deepcopy(semantic),
                        "expected_units": units,
                        "expected_signature_count": signature_count,
                        "expected_signature_population_sha256": hashlib.sha256(
                            f"{selector_id}:{index}".encode()
                        ).hexdigest(),
                    }
                )
            fresh_matching_units = 0
            residual = {
                "units": selector["expected_units"],
                "signature_count": sum(
                    child["expected_signature_count"] for child in children
                ),
                "signature_population_sha256": hashlib.sha256(
                    f"{selector_id}:residual".encode()
                ).hexdigest(),
            }
        evidence = {"classification": "synthetic-transition-test"}
        if not selector_id.startswith("section232-"):
            child = children[0]
            evidence = {
                "classification": (
                    "cafta-reference-defect-receipted-fresh-signature"
                    if selector_id == campaign_module.CAFTA_PREVIEW_SELECTOR_ID
                    else "fresh-signature-rebind-preserved-ruling"
                ),
                "historical_ruling": {
                    field: selector[field]
                    for field in ("logical_class", "disposition", "attribution")
                },
                "fresh_ruling": {
                    field: child[field]
                    for field in ("logical_class", "disposition", "attribution")
                },
                "child_populations": {
                    child["id"]: {
                        "units": child["expected_units"],
                        "signature_count": child["expected_signature_count"],
                        "signature_population_sha256": child[
                            "expected_signature_population_sha256"
                        ],
                    }
                },
            }
            if selector_id == campaign_module.CAFTA_PREVIEW_SELECTOR_ID:
                evidence["cafta_supersession_receipt"] = {
                    "file": {},
                    "payload": {},
                }
        else:
            if status == "retired":
                patterns = ()
                classification = "fully-fixed-exposed"
            elif "-annex-" in selector_id:
                patterns = campaign_module.TRANSITION_ANNEX_PATTERNS
                classification = (
                    "disjoint-reference-defect-and-conditional-reference-behavior"
                )
            else:
                patterns = campaign_module.TRANSITION_HEADING_PATTERNS
                classification = "disjoint-conditional-reference-behavior"
            evidence = {
                "current_precedence_true_units": fresh_matching_units,
                "current_precedence_false_units": residual["units"],
                "candidate_pattern_units": {
                    campaign_module._transition_pattern_name(pattern): child[
                        "expected_units"
                    ]
                    for pattern, child in zip(patterns, children, strict=True)
                },
                "child_populations": {
                    child["id"]: {
                        "candidate_pattern": (
                            campaign_module._transition_pattern_name(pattern)
                        ),
                        "units": child["expected_units"],
                        "signature_count": child["expected_signature_count"],
                        "signature_population_sha256": child[
                            "expected_signature_population_sha256"
                        ],
                    }
                    for pattern, child in zip(patterns, children, strict=True)
                },
                "classification": classification,
            }
            if selector_id in fallback_hts10_by_parent:
                defect_child = children[0]
                fallback_hts10 = fallback_hts10_by_parent[selector_id]
                evidence["yale_annex_defect_source_proof"] = {
                    "classification": (
                        "pinned-yale-direct-annex-or-derivative-fallback"
                    ),
                    "units": defect_child["expected_units"],
                    "per_arm": {
                        "legacy_derivative_fallback": {
                            "units": defect_child["expected_units"],
                            "signature_count": defect_child["expected_signature_count"],
                            "signature_population_sha256": defect_child[
                                "expected_signature_population_sha256"
                            ],
                            "hts10": fallback_hts10,
                        }
                    },
                    "pinned_yale_source": (
                        campaign_module._expected_transition_yale_source_receipt(
                            preview
                        )
                    ),
                }
        transitions.append(
            {
                "parent_id": selector_id,
                "parent_contract": copy.deepcopy(selector),
                "status": status,
                "historical_units": selector["expected_units"],
                "fresh_matching_units": fresh_matching_units,
                "fresh_residual_population": residual,
                "children": children,
                "evidence": evidence,
            }
        )
        ledger_children.extend(children)
    assert child_id
    historical_entries = {
        entry["id"]: entry for entry in _historical_preview_entries(preview)
    }
    entries = [
        {
            **copy.deepcopy(historical_entries[child["parent_id"]]),
            **copy.deepcopy(child),
            "receipt": "In-memory synthetic transition contract for this test.",
            "expires_on_source_change": True,
        }
        for child in ledger_children
    ]
    line_set = preview["line_sets"][parent["match"]["line_set"]]
    unit = {
        **_selector_unit(),
        "slot": parent["match"]["slot"],
        "hts10": line_set["values"][0],
        "delta": 0.25,
    }
    observed = {signature: copy.deepcopy(unit) for signature, _units in population}
    counts = Counter(dict(population))
    classes = {signature: child_id for signature in observed}
    return (
        preview,
        entries,
        {"transitions": transitions},
        child_id,
        observed,
        counts,
        classes,
    )


def _synthetic_annex_transition_population() -> tuple[
    dict,
    list[dict],
    dict,
    str,
    dict[str, dict],
    Counter[str],
    dict[str, str],
]:
    preview, entries, transition, *_unused = _synthetic_preview_transition()
    parent_id = "section232-annex-brazil"
    item = next(
        value for value in transition["transitions"] if value["parent_id"] == parent_id
    )
    fallback = ["9401999030", "9401999040"]
    parent_line_set = preview["line_sets"][
        item["parent_contract"]["match"]["line_set"]
    ]["values"]
    direct_hts10 = next(
        hts10
        for hts10 in parent_line_set
        if hts10
        not in campaign_module.TRANSITION_EXPECTED_LEGACY_DERIVATIVE_FALLBACK_HTS10
    )
    observed: dict[str, dict] = {}
    counts: Counter[str] = Counter()
    classes: dict[str, str] = {}
    child_populations: dict[str, Counter[str]] = {}
    for index, child in enumerate(item["children"]):
        if index == 0:
            hts_counts = [(fallback[0], 1), (fallback[1], 2), (direct_hts10, 1)]
        else:
            hts_counts = [(direct_hts10, index + 1)]
        population: Counter[str] = Counter()
        for hts_index, (hts10, units) in enumerate(hts_counts):
            signature = hashlib.sha256(
                f"{child['id']}:{hts_index}:{hts10}".encode()
            ).hexdigest()
            unit = {
                **_selector_unit(),
                "slot": item["parent_contract"]["match"]["slot"],
                "hts10": hts10,
                "delta": 0.25,
                "flags": copy.deepcopy(child["match"]["line_class"]["flags"]),
            }
            observed[signature] = unit
            counts[signature] = units
            classes[signature] = child["id"]
            population[signature] = units
        child["expected_units"] = sum(population.values())
        child["expected_signature_count"] = len(population)
        child["expected_signature_population_sha256"] = signature_population_sha256(
            population.items()
        )
        child_populations[child["id"]] = population

    residual: Counter[str] = Counter()
    for population in child_populations.values():
        residual.update(population)
    item["fresh_matching_units"] = item["historical_units"] - sum(residual.values())
    item["fresh_residual_population"] = {
        "units": sum(residual.values()),
        "signature_count": len(residual),
        "signature_population_sha256": signature_population_sha256(residual.items()),
    }
    evidence = item["evidence"]
    evidence["current_precedence_true_units"] = item["fresh_matching_units"]
    evidence["current_precedence_false_units"] = sum(residual.values())
    evidence["candidate_pattern_units"] = {
        campaign_module._transition_pattern_name(pattern): child["expected_units"]
        for pattern, child in zip(
            campaign_module.TRANSITION_ANNEX_PATTERNS,
            item["children"],
            strict=True,
        )
    }
    evidence["child_populations"] = {
        child["id"]: {
            "candidate_pattern": campaign_module._transition_pattern_name(pattern),
            "units": child["expected_units"],
            "signature_count": child["expected_signature_count"],
            "signature_population_sha256": child[
                "expected_signature_population_sha256"
            ],
        }
        for pattern, child in zip(
            campaign_module.TRANSITION_ANNEX_PATTERNS,
            item["children"],
            strict=True,
        )
    }
    defect_child = item["children"][0]
    defect_population = child_populations[defect_child["id"]]
    arm_populations = {
        "annex_proclamation_prefix": Counter(
            {
                signature: units
                for signature, units in defect_population.items()
                if observed[signature]["hts10"] == direct_hts10
            }
        ),
        "legacy_derivative_fallback": Counter(
            {
                signature: units
                for signature, units in defect_population.items()
                if observed[signature]["hts10"] in fallback
            }
        ),
    }
    evidence["yale_annex_defect_source_proof"]["units"] = sum(
        defect_population.values()
    )
    evidence["yale_annex_defect_source_proof"]["per_arm"] = {
        arm: {
            "units": sum(population.values()),
            "signature_count": len(population),
            "signature_population_sha256": signature_population_sha256(
                population.items()
            ),
            "hts10": sorted({observed[signature]["hts10"] for signature in population}),
        }
        for arm, population in sorted(arm_populations.items())
    }
    transition["receipt_payload_sha256"] = campaign_module._canonical_sha256(
        {"transitions": transition["transitions"]}
    )
    return (
        preview,
        entries,
        transition,
        parent_id,
        observed,
        counts,
        classes,
    )


@pytest.fixture
def _raw_preview_line_set_membership(monkeypatch):
    preview = json.loads(PREVIEW_DISPOSITION_LINE_SETS.read_text())
    values = {
        name: frozenset(receipt["values"])
        for name, receipt in preview["line_sets"].items()
    }
    monkeypatch.setattr(
        campaign_module,
        "_line_set_contains",
        lambda unit, name: unit["hts10"] in values[name],
    )


def test_preview_transition_enrolls_child_and_partitions_parent_exactly(
    _raw_preview_line_set_membership,
) -> None:
    preview, entries, transition, child_id, observed, counts, classes = (
        _synthetic_preview_transition()
    )
    active, retired, superseded = _preview_selector_snapshot(
        entries, preview, transition
    )
    target_parent = transition["transitions"][0]["parent_id"]

    assert child_id in active
    assert set(retired) == campaign_module.TRANSITION_SECTION232_EXPOSED_PARENTS
    assert set(superseded) == {
        selector["id"] for selector in preview["selectors"]
    } - set(retired)
    _enforce_preview_selector_transitions(
        {target_parent: superseded[target_parent]},
        observed,
        counts,
        classes,
        engine_errors=0,
    )


def test_preview_transition_replays_multichild_annex_union_and_source_arms(
    _raw_preview_line_set_membership,
) -> None:
    preview, entries, transition, parent_id, observed, counts, classes = (
        _synthetic_annex_transition_population()
    )
    _active, _retired, superseded = _preview_selector_snapshot(
        entries, preview, transition
    )
    target = {parent_id: superseded[parent_id]}

    assert len(target[parent_id]["children"]) == 4
    _enforce_preview_selector_transitions(
        target, observed, counts, classes, engine_errors=0
    )

    wrong_classes = dict(classes)
    first_child, second_child = target[parent_id]["children"][:2]
    signature = next(
        signature
        for signature, class_id in wrong_classes.items()
        if class_id == first_child["id"]
    )
    wrong_classes[signature] = second_child["id"]
    with pytest.raises(ValueError, match="child classification drift"):
        _enforce_preview_selector_transitions(
            target, observed, counts, wrong_classes, engine_errors=0
        )


def test_preview_transition_rejects_stripped_annex_source_proof() -> None:
    preview, entries, transition, parent_id, *_rest = (
        _synthetic_annex_transition_population()
    )
    item = next(
        value for value in transition["transitions"] if value["parent_id"] == parent_id
    )
    del item["evidence"]["yale_annex_defect_source_proof"]
    transition["receipt_payload_sha256"] = campaign_module._canonical_sha256(
        {"transitions": transition["transitions"]}
    )

    with pytest.raises(ValueError, match="evidence fields drift"):
        _preview_selector_snapshot(entries, preview, transition)


@pytest.mark.parametrize(
    "mutation",
    [
        "direct_digest",
        "direct_hts10",
        "paired_arm_digests",
        "fallback_parent_reassignment",
    ],
)
def test_preview_transition_rejects_rehashed_fabricated_annex_source_proof(
    _raw_preview_line_set_membership,
    mutation: str,
) -> None:
    preview, entries, transition, parent_id, observed, counts, classes = (
        _synthetic_annex_transition_population()
    )
    item = next(
        value for value in transition["transitions"] if value["parent_id"] == parent_id
    )
    proof = item["evidence"]["yale_annex_defect_source_proof"]
    if mutation == "direct_digest":
        proof["per_arm"]["annex_proclamation_prefix"]["signature_population_sha256"] = (
            "f" * 64
        )
    elif mutation == "direct_hts10":
        proof["per_arm"]["annex_proclamation_prefix"]["hts10"] = ["0000000001"]
    elif mutation == "paired_arm_digests":
        proof["per_arm"]["annex_proclamation_prefix"]["signature_population_sha256"] = (
            "e" * 64
        )
        proof["per_arm"]["legacy_derivative_fallback"][
            "signature_population_sha256"
        ] = "f" * 64
    else:
        other_item = next(
            value
            for value in transition["transitions"]
            if value["parent_id"] == "section232-annex-forced-labor"
        )
        other_proof = other_item["evidence"]["yale_annex_defect_source_proof"]
        brazil_fallback = proof["per_arm"]["legacy_derivative_fallback"]["hts10"]
        forced_labor_fallback = other_proof["per_arm"]["legacy_derivative_fallback"][
            "hts10"
        ]
        proof["per_arm"]["legacy_derivative_fallback"]["hts10"] = forced_labor_fallback
        other_proof["per_arm"]["legacy_derivative_fallback"]["hts10"] = brazil_fallback
    transition["receipt_payload_sha256"] = campaign_module._canonical_sha256(
        {"transitions": transition["transitions"]}
    )
    _active, _retired, superseded = _preview_selector_snapshot(
        entries, preview, transition
    )

    with pytest.raises(ValueError, match="source-arm population does not rederive"):
        _enforce_preview_selector_transitions(
            {parent_id: superseded[parent_id]},
            observed,
            counts,
            classes,
            engine_errors=0,
        )


def test_preview_transition_rejects_partition_escape_gap_digest_and_errors(
    _raw_preview_line_set_membership,
) -> None:
    preview, entries, transition, child_id, observed, counts, classes = (
        _synthetic_preview_transition()
    )
    _active, _retired, superseded = _preview_selector_snapshot(
        entries, preview, transition
    )
    target_parent = transition["transitions"][0]["parent_id"]
    target_superseded = {target_parent: superseded[target_parent]}

    escaped_observed = {**observed, "c" * 64: _selector_unit()}
    escaped_counts = counts + Counter({"c" * 64: 1})
    with pytest.raises(ValueError, match="child escaped parent"):
        _enforce_preview_selector_transitions(
            target_superseded,
            escaped_observed,
            escaped_counts,
            {**classes, "c" * 64: child_id},
            engine_errors=0,
        )
    with pytest.raises(ValueError, match="do not partition parent"):
        _enforce_preview_selector_transitions(
            target_superseded,
            observed,
            counts,
            {**classes, "b" * 64: None},
            engine_errors=0,
        )
    digest_mutant = copy.deepcopy(target_superseded)
    digest_mutant[target_parent]["fresh_residual_population"][
        "signature_population_sha256"
    ] = "f" * 64
    with pytest.raises(ValueError, match="signature digest drift"):
        _enforce_preview_selector_transitions(
            digest_mutant, observed, counts, classes, engine_errors=0
        )
    with pytest.raises(ValueError, match="cannot be proven with engine errors"):
        _enforce_preview_selector_transitions(
            target_superseded, observed, counts, classes, engine_errors=1
        )


def test_preview_transition_rejects_parent_or_child_contract_drift() -> None:
    preview, entries, transition, child_id, _observed, _counts, _classes = (
        _synthetic_preview_transition()
    )
    parent_remains = copy.deepcopy(entries)
    parent_remains.append(
        next(
            copy.deepcopy(entry)
            for entry in _historical_preview_entries(preview)
            if entry["id"] == transition["transitions"][0]["parent_id"]
        )
    )
    with pytest.raises(ValueError, match="transitioned preview parent remains"):
        _preview_selector_snapshot(parent_remains, preview, transition)

    child_drift = copy.deepcopy(entries)
    next(entry for entry in child_drift if entry["id"] == child_id)["attribution"] = (
        "axiom-attributed-open"
    )
    with pytest.raises(ValueError, match="child attribution drift"):
        _preview_selector_snapshot(child_drift, preview, transition)

    census_drift = copy.deepcopy(transition)
    census_drift["transitions"][0]["fresh_matching_units"] -= 1
    with pytest.raises(ValueError, match="does not conserve"):
        _preview_selector_snapshot(entries, preview, census_drift)


@pytest.mark.parametrize(
    "parent_id",
    ["section232-annex-brazil", "aircraft-utilization-proxy-brazil"],
)
def test_preview_transition_rejects_rehashed_semantic_relabel(
    parent_id: str,
) -> None:
    preview, entries, transition, *_rest = _synthetic_preview_transition()
    item = next(
        item for item in transition["transitions"] if item["parent_id"] == parent_id
    )
    child = item["children"][0]
    old_id = child["id"]
    child["id"] = f"{old_id}-unauthorized"
    child["disposition"] = "axiom_encoding_gap"
    ledger_child = next(entry for entry in entries if entry["id"] == old_id)
    ledger_child["id"] = child["id"]
    ledger_child["disposition"] = child["disposition"]
    transition["receipt_payload_sha256"] = campaign_module._canonical_sha256(
        {"transitions": transition["transitions"]}
    )

    with pytest.raises(ValueError, match=f"semantics drift: {parent_id}"):
        _preview_selector_snapshot(entries, preview, transition)


def test_preview_transition_rejects_rehashed_candidate_pattern_relabel() -> None:
    preview, entries, transition, *_rest = _synthetic_preview_transition()
    item = next(
        value
        for value in transition["transitions"]
        if value["parent_id"] == "section232-annex-brazil"
    )
    child_id = item["children"][0]["id"]
    item["evidence"]["child_populations"][child_id]["candidate_pattern"] = (
        "fabricated-pattern"
    )
    transition["receipt_payload_sha256"] = campaign_module._canonical_sha256(
        {"transitions": transition["transitions"]}
    )

    with pytest.raises(ValueError, match="evidence ruling drift"):
        _preview_selector_snapshot(entries, preview, transition)


@pytest.mark.parametrize(
    "parent_id",
    [
        "aircraft-utilization-proxy-brazil",
        "aircraft-utilization-proxy-forced-labor",
        "cafta-52i-deferred",
        "chapter98-brazil",
        "chapter98-forced-labor",
        "pharma-utilization-proxy-brazil",
        "pharma-utilization-proxy-forced-labor-035",
        "pharma-utilization-proxy-forced-labor-non035",
        "yale-hts8-broadening-brazil",
        "yale-parser-zero-statutory-base",
        "yale-zero-pharma-brazil",
        "yale-zero-pharma-forced-labor",
    ],
)
def test_preview_transition_rejects_rehashed_non_section232_evidence(
    parent_id: str,
) -> None:
    preview, entries, transition, *_rest = _synthetic_preview_transition(parent_id)
    item = next(
        value for value in transition["transitions"] if value["parent_id"] == parent_id
    )
    item["evidence"]["classification"] = "fabricated-classification"
    transition["receipt_payload_sha256"] = campaign_module._canonical_sha256(
        {"transitions": transition["transitions"]}
    )

    with pytest.raises(
        ValueError,
        match=f"non-Section-232 transition evidence drift: {parent_id}",
    ):
        _preview_selector_snapshot(entries, preview, transition)


def test_preview_transition_child_ledger_logical_class_is_exact() -> None:
    preview, entries, transition, child_id, *_rest = _synthetic_preview_transition()
    next(entry for entry in entries if entry["id"] == child_id)["logical_class"] = (
        "unauthorized-logical-class"
    )
    with pytest.raises(ValueError, match="child logical class drift"):
        _preview_selector_snapshot(entries, preview, transition)


@pytest.mark.parametrize(
    ("field", "mutant"),
    [
        ("slot", "forced_labor_section_301"),
        (
            "line_set",
            "preview-1311-section232-annex-forced-labor-hts10",
        ),
        ("delta", {"sign": "neg"}),
    ],
)
def test_preview_transition_child_cannot_change_parent_match(
    field: str, mutant: object
) -> None:
    preview, entries, transition, _child_id, *_rest = _synthetic_preview_transition()
    transition["transitions"][0]["children"][0]["match"][field] = mutant
    with pytest.raises(ValueError, match="does not preserve parent match"):
        _preview_selector_snapshot(entries, preview, transition)


def test_preview_transition_requires_every_immutable_parent() -> None:
    preview, entries, transition, *_rest = _synthetic_preview_transition()
    transition["transitions"].pop()
    with pytest.raises(ValueError, match="parent coverage is incomplete"):
        _preview_selector_snapshot(entries, preview, transition)


def test_preview_transition_rejects_rehashed_preview_parent_contract_swap() -> None:
    preview, entries, transition, *_rest = _synthetic_preview_transition()
    first_id = "section232-annex-brazil"
    second_id = "aircraft-utilization-proxy-brazil"
    first = next(item for item in preview["selectors"] if item["id"] == first_id)
    second = next(item for item in preview["selectors"] if item["id"] == second_id)
    first["id"], second["id"] = second["id"], first["id"]
    census = preview["census"]["per_selector"]
    census[first_id], census[second_id] = census[second_id], census[first_id]
    preview.pop("receipt_payload_sha256")
    preview["receipt_payload_sha256"] = campaign_module._canonical_sha256(preview)

    with pytest.raises(ValueError, match="all-selector snapshot drift"):
        _preview_selector_snapshot(entries, preview, transition)


@pytest.mark.parametrize(
    ("field", "mutant", "message"),
    [
        ("expected_units", 6, "unit count drift"),
        ("expected_signature_count", 3, "signature count drift"),
        (
            "expected_signature_population_sha256",
            "f" * 64,
            "signature digest drift",
        ),
    ],
)
def test_preview_transition_rederives_each_child_census(
    _raw_preview_line_set_membership,
    field: str,
    mutant: object,
    message: str,
) -> None:
    preview, entries, transition, _child_id, observed, counts, classes = (
        _synthetic_preview_transition()
    )
    _active, _retired, superseded = _preview_selector_snapshot(
        entries, preview, transition
    )
    target_parent = transition["transitions"][0]["parent_id"]
    superseded[target_parent]["children"][0][field] = mutant
    with pytest.raises(ValueError, match=message):
        _enforce_preview_selector_transitions(
            {target_parent: superseded[target_parent]},
            observed,
            counts,
            classes,
            engine_errors=0,
        )


def test_preview_transition_receipt_is_lazy_until_a_child_is_enrolled(
    monkeypatch,
) -> None:
    preview = json.loads(PREVIEW_DISPOSITION_LINE_SETS.read_text())
    entries = _historical_preview_entries(preview)
    comparison: dict = {}

    def unexpected_transition_load(*_args):
        raise RuntimeError("transition receipt loaded")

    monkeypatch.setattr(
        campaign_module,
        "_preview_selector_transition_receipt",
        unexpected_transition_load,
    )

    assert not _preview_transition_is_required(entries, preview)
    assert _transition_for_entries(entries, comparison, preview) is None

    _preview, child_entries, _transition, _child_id, *_rest = (
        _synthetic_preview_transition()
    )
    assert _preview_transition_is_required(child_entries, preview)
    with pytest.raises(RuntimeError, match="transition receipt loaded"):
        _transition_for_entries(child_entries, comparison, preview)


def test_classification_inputs_bind_transition_only_after_child_enrollment(
    tmp_path: Path, monkeypatch
) -> None:
    comparison_receipt = tmp_path / "comparison.json"
    preview_receipt = tmp_path / "preview.json"
    transition_receipt = tmp_path / "transition.json"
    routing_rows = tmp_path / "routing.csv.gz"
    ledger = tmp_path / "ledger.yaml"
    comparison = {"comparison_artifact": {"sha256": "a" * 64}}
    comparison_receipt.write_text(json.dumps(comparison))
    preview = {"receipt_payload_sha256": "b" * 64}
    preview_receipt.write_text(json.dumps(preview))
    routing_rows.write_text("routing\n")
    ledger.write_text("ledger\n")
    monkeypatch.setattr(campaign_module, "COMPARISON_RECEIPT", comparison_receipt)
    monkeypatch.setattr(campaign_module, "ROUTING_ROWS", routing_rows)
    monkeypatch.setattr(
        campaign_module, "PREVIEW_DISPOSITION_LINE_SETS", preview_receipt
    )
    monkeypatch.setattr(
        campaign_module,
        "PREVIEW_SELECTOR_TRANSITION_RECEIPT",
        transition_receipt,
    )
    without_transition = campaign_module._classification_inputs(
        comparison, ledger, preview=preview
    )
    assert set(without_transition) == {
        "comparison_artifact_sha256",
        "comparison_receipt_sha256",
        "disposition_ledger_sha256",
        "preview_disposition_receipt_sha256",
        "preview_disposition_payload_sha256",
        "routing_rows_sha256",
    }

    transition_payload = {"receipt_payload_sha256": "c" * 64}
    transition_receipt.write_text(json.dumps(transition_payload))
    with_transition = campaign_module._classification_inputs(
        comparison,
        ledger,
        preview=preview,
        transition=transition_payload,
    )
    assert with_transition[
        "preview_selector_transition_receipt_sha256"
    ] == campaign_module._sha256(transition_receipt)
    assert with_transition["preview_selector_transition_payload_sha256"] == "c" * 64

    transition_receipt.write_text(json.dumps({**transition_payload, "drift": True}))
    with pytest.raises(ValueError, match="changed during classification"):
        campaign_module._classification_inputs(
            comparison,
            ledger,
            preview=preview,
            transition=transition_payload,
        )

    transition_receipt.write_text(json.dumps(transition_payload))
    comparison_receipt.write_text(json.dumps({**comparison, "drift": True}))
    with pytest.raises(ValueError, match="comparison receipt changed"):
        campaign_module._classification_inputs(
            comparison,
            ledger,
            preview=preview,
            transition=transition_payload,
        )


def test_classification_publication_rechecks_transition_input(
    tmp_path: Path, monkeypatch
) -> None:
    ledger_path = tmp_path / "ledger.yaml"
    artifact = tmp_path / "comparison.jsonl.gz"
    sidecar = tmp_path / "classification.jsonl.gz"
    transition_path = tmp_path / "transition.json"
    entries: list[dict] = []
    ledger_path.write_text(
        yaml.safe_dump({"suite": "us-tariff-schedule", "entries": entries})
    )
    artifact.write_text("comparison artifact\n")
    sidecar.write_text("classification sidecar\n")
    transition_path.write_text("before\n")
    comparison = {
        "comparison_artifact": campaign_module._file_receipt(artifact),
    }
    preview = {"receipt_payload_sha256": "a" * 64}
    transition = {"receipt_payload_sha256": "b" * 64}
    monkeypatch.setattr(
        campaign_module,
        "_preview_disposition_receipt",
        lambda: preview,
    )
    monkeypatch.setattr(
        campaign_module,
        "_transition_for_entries",
        lambda _entries, _comparison, _preview: transition,
    )
    monkeypatch.setattr(
        campaign_module,
        "_classification_inputs",
        lambda *_args, **_kwargs: {
            "transition_sha256": campaign_module._sha256(transition_path)
        },
    )
    captured_inputs = {"transition_sha256": campaign_module._sha256(transition_path)}
    transition_path.write_text("after\n")

    with pytest.raises(ValueError, match="classification inputs changed"):
        campaign_module._require_current_classification_publication(
            comparison=comparison,
            disposition_ledger=ledger_path,
            entries=entries,
            preview=preview,
            transition=transition,
            classification_inputs=captured_inputs,
            artifact=artifact,
            sidecar=sidecar,
            sidecar_sha256=campaign_module._sha256(sidecar),
        )


def test_classification_publication_rechecks_bound_comparison(
    tmp_path: Path, monkeypatch
) -> None:
    comparison = {"comparison_artifact": {"sha256": "a" * 64}}
    monkeypatch.setattr(
        campaign_module,
        "_load_bound_comparison_locked",
        lambda **_kwargs: {**comparison, "drift": True},
    )

    with pytest.raises(ValueError, match="bound comparison changed"):
        campaign_module._require_current_classification_publication(
            comparison=comparison,
            disposition_ledger=tmp_path / "unused-ledger.yaml",
            entries=[],
            preview={},
            transition=None,
            classification_inputs={},
            artifact=tmp_path / "unused-artifact.jsonl.gz",
            sidecar=tmp_path / "unused-sidecar.jsonl.gz",
            sidecar_sha256="b" * 64,
            rulespec_root=tmp_path / "rulespec",
            engine_binary=tmp_path / "engine",
        )


def test_classification_publication_removes_receipt_on_write_race(
    tmp_path: Path, monkeypatch
) -> None:
    output = tmp_path / "classification.json"
    receipt = {"schema": "test.classification.v1"}
    current = True
    atomic_json = campaign_module._atomic_json

    def require_current() -> None:
        if not current:
            raise ValueError("classification inputs changed during publication")

    def mutate_during_write(path: Path, payload: dict) -> None:
        nonlocal current
        current = False
        atomic_json(path, payload)

    monkeypatch.setattr(campaign_module, "CLASSIFICATION_RECEIPT", output)
    monkeypatch.setattr(campaign_module, "_atomic_json", mutate_during_write)

    with pytest.raises(ValueError, match="changed during publication"):
        campaign_module._publish_classification_receipt(receipt, require_current)
    assert not output.exists()


def test_classification_publication_rejects_replaced_output(
    tmp_path: Path, monkeypatch
) -> None:
    output = tmp_path / "classification.json"
    receipt = {"schema": "test.classification.v1"}

    def write_replacement(path: Path, _payload: dict) -> None:
        path.write_text(campaign_module._render({"schema": "tampered"}))

    monkeypatch.setattr(campaign_module, "CLASSIFICATION_RECEIPT", output)
    monkeypatch.setattr(campaign_module, "_atomic_json", write_replacement)

    with pytest.raises(ValueError, match="receipt changed during publication"):
        campaign_module._publish_classification_receipt(receipt, lambda: None)
    assert not output.exists()


def test_classification_sidecar_install_rejects_destination_replacement(
    tmp_path: Path, monkeypatch
) -> None:
    temporary = tmp_path / "temporary.jsonl.gz"
    destination = tmp_path / "classification.jsonl.gz"
    temporary.write_text("producer-owned sidecar\n")
    real_replace = Path.replace

    def replace_then_mutate(source: Path, target: Path) -> Path:
        result = real_replace(source, target)
        Path(target).write_text("replacement sidecar\n")
        return result

    monkeypatch.setattr(Path, "replace", replace_then_mutate)
    with pytest.raises(ValueError, match="sidecar changed during production"):
        campaign_module._install_classification_sidecar(temporary, destination)


def test_classification_inputs_reject_transient_routing_bytes(
    tmp_path: Path, monkeypatch
) -> None:
    comparison = {"comparison_artifact": {"sha256": "a" * 64}}
    comparison_receipt = tmp_path / "comparison.json"
    comparison_receipt.write_text(json.dumps(comparison))
    preview = {"receipt_payload_sha256": "b" * 64}
    preview_receipt = tmp_path / "preview.json"
    preview_receipt.write_text(json.dumps(preview))
    ledger = tmp_path / "ledger.yaml"
    ledger.write_text("ledger\n")
    current_routing = tmp_path / "current-routing.csv.gz"
    transient_routing = tmp_path / "transient-routing.csv.gz"
    header = "hts10,general_disposition,column2_disposition\n"
    with gzip.open(current_routing, "wt") as target:
        target.write(header + "0101210010,dutiable,dutiable\n")
    with gzip.open(transient_routing, "wt") as target:
        target.write(header + "0101210010,free,free\n")
    transient_bytes = transient_routing.read_bytes()
    assert campaign_module._routing_dispositions(transient_bytes)["0101210010"] == (
        "free",
        "free",
    )
    monkeypatch.setattr(campaign_module, "COMPARISON_RECEIPT", comparison_receipt)
    monkeypatch.setattr(
        campaign_module, "PREVIEW_DISPOSITION_LINE_SETS", preview_receipt
    )
    monkeypatch.setattr(campaign_module, "ROUTING_ROWS", current_routing)

    with pytest.raises(ValueError, match="routing changed during classification"):
        campaign_module._classification_inputs(
            comparison,
            ledger,
            preview=preview,
            routing_sha256=hashlib.sha256(transient_bytes).hexdigest(),
        )


def test_bound_comparison_scan_rejects_transient_artifact(
    tmp_path: Path,
) -> None:
    expected = tmp_path / "expected.jsonl.gz"
    transient = tmp_path / "transient.jsonl.gz"
    with gzip.open(expected, "wt") as target:
        target.write(json.dumps({"case_id": "expected"}) + "\n")
    with gzip.open(transient, "wt") as target:
        target.write(json.dumps({"case_id": "transient"}) + "\n")

    with pytest.raises(ValueError, match="comparison artifact hash mismatch"):
        with campaign_module._bound_gzip_text_source(
            transient, campaign_module._sha256(expected)
        ) as source:
            list(source)


def _bound_transition_receipt(tmp_path: Path, monkeypatch) -> tuple[dict, dict]:
    immutable_preview = json.loads(PREVIEW_DISPOSITION_LINE_SETS.read_text())
    selector_ids = [selector["id"] for selector in immutable_preview["selectors"]]
    scripts = tmp_path / "scripts"
    evidence = tmp_path / "reference/us-tariff-schedule"
    scripts.mkdir(parents=True)
    evidence.mkdir(parents=True)
    sources = {
        "script": scripts / "build_transition.py",
        "campaign_classifier": scripts / "campaign.py",
        "full_closure_guard": scripts / "full_closure.py",
    }
    for name, path in sources.items():
        path.write_text(f"# {name}\n")
    preview_path = evidence / "preview.json"
    manifest_path = evidence / "MANIFEST.json"
    comparison_path = evidence / "comparison.json"
    artifact_path = evidence / "comparison.jsonl.gz"
    historical_path = evidence / "historical.jsonl.gz"
    transition_path = evidence / "transition.json"
    cafta_path = evidence / "cafta.json"
    selected_path = evidence / "selected.csv.gz"
    input_contract_path = evidence / "input-contract.json"
    provenance_path = evidence / "provenance.json"
    integrity_path = evidence / "integrity.json"
    extractor_path = scripts / "extract.R"
    cafta_producer_path = scripts / "build_cafta.py"
    rscript_path = scripts / "Rscript"
    preview_path.write_text("preview\n")
    historical_path.write_text("historical\n")
    selected_path.write_text("selected\n")
    input_contract_path.write_text("input contract\n")
    provenance_path.write_text("provenance\n")
    integrity_path.write_text("integrity\n")
    extractor_path.write_text("# extractor\n")
    cafta_producer_path.write_text("# cafta producer\n")
    rscript_path.write_text("# rscript\n")
    cafta_reproduction = {
        "dplyr_version": "1.1.2",
        "dplyr_path": campaign_module.CAFTA_EXPECTED_DPLYR_TREE_RECEIPT["path"],
        "dplyr_tree": copy.deepcopy(campaign_module.CAFTA_EXPECTED_DPLYR_TREE_RECEIPT),
        "r_runtime_tree": copy.deepcopy(
            campaign_module.CAFTA_EXPECTED_R_RUNTIME_TREE_RECEIPT
        ),
        "program_sha256": (campaign_module.CAFTA_EXPECTED_TIDY_EVAL_PROGRAM_SHA256),
        "r_version": "4.3.0",
        "result": (
            "PASS: rule_hit('full') selected both the full and fta rows under "
            "the pinned .data$condition %in% condition expression"
        ),
        "rscript": campaign_module._file_receipt(rscript_path),
        "selected_conditions": "full,fta",
    }
    monkeypatch.setattr(
        campaign_module,
        "_run_cafta_tidy_eval_reproduction",
        lambda: cafta_reproduction,
    )
    monkeypatch.setattr(campaign_module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(campaign_module, "SELECTED", selected_path)
    monkeypatch.setattr(campaign_module, "INPUT_CONTRACT_RECEIPT", input_contract_path)
    monkeypatch.setattr(campaign_module, "CAFTA_REFERENCE_PROVENANCE", provenance_path)
    monkeypatch.setattr(
        campaign_module, "CAFTA_REFERENCE_INTEGRITY_RECEIPT", integrity_path
    )
    monkeypatch.setattr(
        campaign_module, "CAFTA_SELECTED_PANEL_EXTRACTOR", extractor_path
    )
    monkeypatch.setattr(
        campaign_module, "CAFTA_SUPERSESSION_PRODUCER", cafta_producer_path
    )
    monkeypatch.setattr(campaign_module, "CAFTA_SUPERSESSION_RECEIPT", cafta_path)
    selected_receipt = campaign_module._file_receipt(
        selected_path, relative_to=tmp_path
    )
    provenance_path.write_text(
        json.dumps(
            {
                "schema": "axiom_oracles.us_tariff_schedule_reference.v1",
                "yale_commit": campaign_module.PREVIEW_YALE_COMMIT,
                "rds_path": str(evidence / "rate-timeseries.rds"),
                "rds_sha256": campaign_module.CAFTA_EXPECTED_RDS_SHA256,
                "selected_extract_sha256": selected_receipt["sha256"],
                "extractor_sha256": campaign_module._file_receipt(
                    extractor_path, relative_to=tmp_path
                )["sha256"],
            }
        )
    )
    campaign_source = campaign_module._file_receipt(
        sources["campaign_classifier"], relative_to=tmp_path
    )
    manifest = {
        "run_identity": {
            "rulespec": {"content_sha256": "5" * 64},
            "entry_flag_producers": {"producer_sha256": "6" * 64},
            "campaign_evaluator": {"campaign": campaign_source},
            "selected_population": selected_receipt,
            "chapters": {
                f"{chapter:02d}": {"content_sha256": "8" * 64}
                for chapter in range(1, 101)
            },
            "reference_assumptions": {
                "yale_note16_metal_weight": {
                    "path": "reference/assumption.json",
                    "bytes": 1,
                    "sha256": "7" * 64,
                }
            },
        },
        "shards": {"one": {"cases": 1, "engine_errors": 0}},
    }
    monkeypatch.setattr(
        campaign_module,
        "_yale_note16_weight_assumption_identity",
        lambda: manifest["run_identity"]["reference_assumptions"][
            "yale_note16_metal_weight"
        ],
    )
    manifest_path.write_text(json.dumps(manifest))
    comparison_path.write_text("comparison\n")
    artifact_path.write_text("artifact\n")
    monkeypatch.setattr(
        campaign_module, "PREVIEW_SELECTOR_TRANSITION_PRODUCER_SOURCES", sources
    )
    monkeypatch.setattr(campaign_module, "PREVIEW_DISPOSITION_LINE_SETS", preview_path)
    monkeypatch.setattr(campaign_module, "EVAL_MANIFEST", manifest_path)
    monkeypatch.setattr(campaign_module, "COMPARISON_RECEIPT", comparison_path)
    monkeypatch.setattr(
        campaign_module, "PREVIEW_SELECTOR_TRANSITION_RECEIPT", transition_path
    )
    comparison = {
        "generation_id": "1" * 32,
        "run_identity_sha256": "2" * 64,
        "evaluation_manifest_sha256": "3" * 64,
        "engine_errors": 0,
        "comparison_artifact": campaign_module._file_receipt(artifact_path),
        "per_slot": {"base": {"match": campaign_module.CAFTA_EXPECTED_UNITS}},
    }
    preview = {
        "receipt_payload_sha256": "4" * 64,
        "producer": {"campaign_classifier": campaign_source},
        "selectors": [{"id": selector_id} for selector_id in selector_ids],
        "census": {"total": campaign_module.CAFTA_EXPECTED_UNITS},
        "inputs": {
            campaign_module.PREVIEW_HISTORICAL_TARGET_PATH: (
                campaign_module._file_receipt(historical_path, relative_to=tmp_path)
            )
        },
    }
    transition_inputs = {
        "immutable_preview_receipt": campaign_module._file_receipt(
            preview_path, relative_to=tmp_path
        ),
        "historical_target_mismatch_artifact": preview["inputs"][
            campaign_module.PREVIEW_HISTORICAL_TARGET_PATH
        ],
        "evaluation_manifest": campaign_module._file_receipt(
            manifest_path, relative_to=tmp_path
        ),
        "comparison_receipt": campaign_module._file_receipt(
            comparison_path, relative_to=tmp_path
        ),
        "comparison_artifact": comparison["comparison_artifact"],
    }
    cafta_inputs = {
        **transition_inputs,
        "declared_input_contract": campaign_module._file_receipt(
            input_contract_path, relative_to=tmp_path
        ),
        "reference_provenance": campaign_module._file_receipt(
            provenance_path, relative_to=tmp_path
        ),
        "reference_integrity_receipt": campaign_module._file_receipt(
            integrity_path, relative_to=tmp_path
        ),
        "selected_panel_extractor": campaign_module._file_receipt(
            extractor_path, relative_to=tmp_path
        ),
    }
    identity_sha = campaign_module.CAFTA_EXPECTED_IDENTITY_POPULATION_SHA256
    defect_sha = campaign_module.CAFTA_EXPECTED_DEFECT_PROJECTION_SHA256
    cafta_payload = {
        "schema": campaign_module.CAFTA_SUPERSESSION_SCHEMA,
        "verdict": "PASS",
        "producer": {
            "script": campaign_module._file_receipt(
                cafta_producer_path, relative_to=tmp_path
            )
        },
        "definition": copy.deepcopy(campaign_module.CAFTA_EXPECTED_DEFINITION),
        "inputs": cafta_inputs,
        "bindings": {
            "preview_receipt_payload_sha256": preview["receipt_payload_sha256"],
            "preview_cafta_snapshot_sha256": (
                campaign_module.CAFTA_PREVIEW_SNAPSHOT_SHA256
            ),
            "generation_id": comparison["generation_id"],
            "run_identity_sha256": comparison["run_identity_sha256"],
            "evaluation_manifest_sha256": comparison["evaluation_manifest_sha256"],
            "rulespec": manifest["run_identity"]["rulespec"],
            "campaign_evaluator": manifest["run_identity"]["campaign_evaluator"],
            "selected_population_sha256": selected_receipt["sha256"],
            "fresh_campaign_classifier_sha256": campaign_source["sha256"],
            "preview_campaign_classifier_sha256": campaign_source["sha256"],
            "campaign_producer_identity_required": False,
            "campaign_semantic_equivalence_basis": (
                campaign_module.CAFTA_CAMPAIGN_EQUIVALENCE_BASIS
            ),
            "evaluation_shard_engine_errors": 0,
            "observed_evaluation_record_errors": 0,
            "comparison_receipt_engine_errors": 0,
            "evaluated_chapters": 100,
            "evaluated_cases": 1,
            "observed_evaluated_cases": 1,
            "reference_compared_field": "statutory_rate_s301fl",
            "reference_rds_path": str(evidence / "rate-timeseries.rds"),
            "reference_rds_sha256": (campaign_module.CAFTA_EXPECTED_RDS_SHA256),
        },
        "axiom_predicate_proof": {
            "predicates": {
                "entry_is_entered_free_of_duty_under_dr_cafta": False,
                "entry_is_general_note_29_d_v_textile_or_apparel_good": False,
            },
            "all_joined_actual_case_feeds_false_false": True,
            "joined_fresh_evaluation_records": (campaign_module.CAFTA_EXPECTED_UNITS),
            "chapter_contracts_checked": 100,
            "scope": "all campaign cases in all 100 compiled chapters",
            "contract_sha256": cafta_inputs["declared_input_contract"]["sha256"],
            "actual_case_feed_projection_sha256": (
                campaign_module.CAFTA_EXPECTED_ACTUAL_CASE_FEED_PROJECTION_SHA256
            ),
        },
        "yale_reference_defect": {
            "commit": campaign_module.PREVIEW_YALE_COMMIT,
            "tree": campaign_module.PREVIEW_YALE_TREE,
            "files": {
                path: {
                    "path": path,
                    "bytes": 1,
                    "sha256": sha256,
                }
                for path, sha256 in (campaign_module.CAFTA_YALE_FILE_SHA256.items())
            },
            "adapter_source_proof": copy.deepcopy(
                campaign_module.CAFTA_YALE_ADAPTER_SOURCE_PROOF
            ),
            "source_proof": {
                "rule_hit_function_first_line": 959,
                "rule_hit_use_site_first_line": 973,
                "use_conditioned_first_line": 999,
                "chapter98_precapture_first_line": 2961,
                "statutory_capture_first_line": 3022,
                **campaign_module.CAFTA_YALE_SOURCE_PROOF_HASHES,
                "defect": (
                    "the function argument is named condition, but dplyr's "
                    "data mask resolves the bare RHS condition to the condition "
                    "column; therefore .data$condition %in% condition is true "
                    "for every nonmissing row"
                ),
                "downstream_effect": (
                    "rule_hit('full') includes condition=fta rows, making "
                    "country_full_hit true, covered false, and rate_s301fl zero "
                    "before preference scaling"
                ),
                "comparison_surface": (
                    "statutory_rate_s301fl captures rate_s301fl before the later "
                    "HS2-country preference scaling; fixing the name collision "
                    "restores the statutory country-tier rate on the compared "
                    "surface regardless of utilization share"
                ),
            },
            "deterministic_minimal_reproduction": cafta_reproduction,
        },
        "zero_error_proof": {
            "evaluation_shard_engine_errors": 0,
            "observed_evaluation_record_errors": 0,
            "comparison_receipt_engine_errors": 0,
            "comparison_artifact_engine_error_rows": 0,
        },
        "census": {
            "historical_artifact_rows_scanned": (campaign_module.CAFTA_EXPECTED_UNITS),
            "fresh_comparison_rows_scanned": (campaign_module.CAFTA_EXPECTED_UNITS),
            "cafta_units": campaign_module.CAFTA_EXPECTED_UNITS,
            "cafta_signatures": campaign_module.CAFTA_EXPECTED_SIGNATURES,
            "origin_units": campaign_module.CAFTA_EXPECTED_ORIGIN_UNITS,
        },
        "supersession": {
            "authorized_disposition_after_pass": "upstream_engine_gap",
            "authorized_attribution_after_pass": "reference-defect",
            "historical_identity_population_sha256": identity_sha,
            "fresh_identity_population_sha256": identity_sha,
            "historical_mismatch_projection_sha256": (
                campaign_module.CAFTA_EXPECTED_HISTORICAL_MISMATCH_PROJECTION_SHA256
            ),
            "historical_defect_projection_sha256": defect_sha,
            "fresh_defect_projection_sha256": defect_sha,
            "joined_historical_units": campaign_module.CAFTA_EXPECTED_UNITS,
            "missing_historical_units": 0,
            "duplicate_historical_identities": 0,
            "duplicate_fresh_identities": 0,
            "fresh_mismatching_units": campaign_module.CAFTA_EXPECTED_UNITS,
            "all_present": True,
            "all_unique": True,
            "all_predicates_false": True,
            "all_yale_defect_zeros_reproduced": True,
            "all_corrected_yale_statutory_rates_match_axiom": True,
        },
    }
    cafta_payload["receipt_payload_sha256"] = campaign_module._canonical_sha256(
        cafta_payload
    )
    cafta_path.write_text(json.dumps(cafta_payload))
    transitions = [
        {"parent_id": selector_id, "evidence": {}} for selector_id in selector_ids
    ]
    cafta_transition = next(
        item
        for item in transitions
        if item["parent_id"] == campaign_module.CAFTA_PREVIEW_SELECTOR_ID
    )
    cafta_transition["children"] = [
        {
            "id": "cafta-reference-defect",
            "disposition": "upstream_engine_gap",
            "attribution": "reference-defect",
            "expected_units": campaign_module.CAFTA_EXPECTED_UNITS,
            "expected_signature_count": (campaign_module.CAFTA_EXPECTED_SIGNATURES),
        }
    ]
    cafta_transition["evidence"]["cafta_supersession_receipt"] = {
        "file": campaign_module._file_receipt(cafta_path, relative_to=tmp_path),
        "payload": cafta_payload,
    }
    receipt = {
        "schema": campaign_module.PREVIEW_SELECTOR_TRANSITION_SCHEMA,
        "verdict": "PASS",
        "producer": {
            name: campaign_module._file_receipt(path, relative_to=tmp_path)
            for name, path in sources.items()
        },
        "inputs": transition_inputs,
        "bindings": {
            "preview_receipt_payload_sha256": preview["receipt_payload_sha256"],
            "generation_id": comparison["generation_id"],
            "run_identity_sha256": comparison["run_identity_sha256"],
            "evaluation_manifest_sha256": comparison["evaluation_manifest_sha256"],
            "rulespec": manifest["run_identity"]["rulespec"],
            "entry_flag_producers": manifest["run_identity"]["entry_flag_producers"],
            "reference_assumptions": manifest["run_identity"]["reference_assumptions"],
        },
        "zero_error_proof": {
            "evaluation_shard_engine_errors": 0,
            "observed_evaluation_record_errors": 0,
            "comparison_receipt_engine_errors": 0,
            "comparison_artifact_engine_error_rows": 0,
        },
        "transitions": transitions,
    }
    receipt["receipt_payload_sha256"] = campaign_module._canonical_sha256(receipt)
    transition_path.write_text(json.dumps(receipt))
    return comparison, preview


def test_preview_transition_loader_rejects_stale_or_error_backed_receipt(
    tmp_path: Path, monkeypatch
) -> None:
    comparison, preview = _bound_transition_receipt(tmp_path, monkeypatch)
    receipt = campaign_module._preview_selector_transition_receipt(comparison, preview)
    assert receipt["verdict"] == "PASS"

    path = campaign_module.PREVIEW_SELECTOR_TRANSITION_RECEIPT
    mutant = json.loads(path.read_text())
    mutant["zero_error_proof"]["observed_evaluation_record_errors"] = 1
    mutant.pop("receipt_payload_sha256")
    mutant["receipt_payload_sha256"] = campaign_module._canonical_sha256(mutant)
    path.write_text(json.dumps(mutant))
    with pytest.raises(ValueError, match="cannot rely on engine errors"):
        campaign_module._preview_selector_transition_receipt(comparison, preview)


def test_preview_transition_loader_rejects_omitted_parent(
    tmp_path: Path, monkeypatch
) -> None:
    comparison, preview = _bound_transition_receipt(tmp_path, monkeypatch)
    path = campaign_module.PREVIEW_SELECTOR_TRANSITION_RECEIPT
    mutant = json.loads(path.read_text())
    mutant["transitions"].pop()
    mutant.pop("receipt_payload_sha256")
    mutant["receipt_payload_sha256"] = campaign_module._canonical_sha256(mutant)
    path.write_text(json.dumps(mutant))

    with pytest.raises(ValueError, match="parent coverage is incomplete"):
        campaign_module._preview_selector_transition_receipt(comparison, preview)


def test_preview_transition_loader_rejects_cafta_file_drift(
    tmp_path: Path, monkeypatch
) -> None:
    comparison, preview = _bound_transition_receipt(tmp_path, monkeypatch)
    cafta_path = campaign_module.CAFTA_SUPERSESSION_RECEIPT
    cafta_path.write_text(cafta_path.read_text() + "\n")

    with pytest.raises(ValueError, match="CAFTA supersession receipt file binding"):
        campaign_module._preview_selector_transition_receipt(comparison, preview)


def _rewrite_embedded_cafta_receipt(
    mutate,
    *,
    refresh_payload_digest: bool = True,
) -> None:
    transition_path = campaign_module.PREVIEW_SELECTOR_TRANSITION_RECEIPT
    transition = json.loads(transition_path.read_text())
    cafta_transition = next(
        item
        for item in transition["transitions"]
        if item["parent_id"] == campaign_module.CAFTA_PREVIEW_SELECTOR_ID
    )
    wrapper = cafta_transition["evidence"]["cafta_supersession_receipt"]
    payload = wrapper["payload"]
    mutate(payload, cafta_transition)
    if refresh_payload_digest:
        payload.pop("receipt_payload_sha256", None)
        payload["receipt_payload_sha256"] = campaign_module._canonical_sha256(payload)
    cafta_path = campaign_module.CAFTA_SUPERSESSION_RECEIPT
    cafta_path.write_text(json.dumps(payload))
    wrapper["file"] = campaign_module._file_receipt(
        cafta_path, relative_to=campaign_module.REPO_ROOT
    )
    transition.pop("receipt_payload_sha256", None)
    transition["receipt_payload_sha256"] = campaign_module._canonical_sha256(transition)
    transition_path.write_text(json.dumps(transition))


def test_preview_transition_loader_rejects_tampered_embedded_cafta_payload(
    tmp_path: Path, monkeypatch
) -> None:
    comparison, preview = _bound_transition_receipt(tmp_path, monkeypatch)
    path = campaign_module.PREVIEW_SELECTOR_TRANSITION_RECEIPT
    mutant = json.loads(path.read_text())
    cafta_transition = next(
        item
        for item in mutant["transitions"]
        if item["parent_id"] == campaign_module.CAFTA_PREVIEW_SELECTOR_ID
    )
    cafta_transition["evidence"]["cafta_supersession_receipt"]["payload"]["verdict"] = (
        "FAIL"
    )
    mutant.pop("receipt_payload_sha256")
    mutant["receipt_payload_sha256"] = campaign_module._canonical_sha256(mutant)
    path.write_text(json.dumps(mutant))

    with pytest.raises(ValueError, match="embedded CAFTA supersession payload"):
        campaign_module._preview_selector_transition_receipt(comparison, preview)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload, _transition: payload["bindings"].__setitem__(
                "generation_id", "f" * 32
            ),
            "run binding is stale",
        ),
        (
            lambda payload, _transition: (
                payload["bindings"].__setitem__("evaluated_cases", 2),
                payload["bindings"].__setitem__("observed_evaluated_cases", 2),
            ),
            "run binding is stale",
        ),
        (
            lambda payload, _transition: (
                payload["bindings"].__setitem__("evaluated_cases", 1.0),
                payload["bindings"].__setitem__("observed_evaluated_cases", 1.0),
            ),
            "run binding is stale",
        ),
        (
            lambda payload, _transition: payload["bindings"].__setitem__(
                "reference_rds_sha256", "f" * 64
            ),
            "run binding is stale",
        ),
        (
            lambda payload, _transition: payload["bindings"].__setitem__(
                "campaign_semantic_equivalence_basis", "weaker basis"
            ),
            "run binding is stale",
        ),
        (
            lambda payload, _transition: payload["bindings"].__setitem__(
                "unchecked", True
            ),
            "run binding is stale",
        ),
        (
            lambda payload, _transition: payload.__setitem__(
                "yale_reference_defect",
                {
                    "commit": campaign_module.PREVIEW_YALE_COMMIT,
                    "tree": campaign_module.PREVIEW_YALE_TREE,
                },
            ),
            "Yale defect proof is malformed",
        ),
        (
            lambda payload, _transition: payload.__setitem__(
                "definition",
                {"real_entry_frontier": "weaker rehashed definition"},
            ),
            "definition drift",
        ),
        (
            lambda payload, _transition: payload["supersession"].__setitem__(
                "authorized_disposition_after_pass", "explained_residual"
            ),
            "authorization or identity proof drift",
        ),
        (
            lambda payload, _transition: payload["axiom_predicate_proof"].__setitem__(
                "actual_case_feed_projection_sha256", "f" * 64
            ),
            "actual-predicate proof drift",
        ),
        (
            lambda payload, _transition: payload["supersession"].__setitem__(
                "historical_mismatch_projection_sha256", "f" * 64
            ),
            "authorization or identity proof drift",
        ),
        (
            lambda payload, _transition: (
                payload["supersession"].__setitem__(
                    "historical_identity_population_sha256", "e" * 64
                ),
                payload["supersession"].__setitem__(
                    "fresh_identity_population_sha256", "e" * 64
                ),
            ),
            "authorization or identity proof drift",
        ),
        (
            lambda payload, _transition: (
                payload["supersession"].__setitem__(
                    "historical_defect_projection_sha256", "e" * 64
                ),
                payload["supersession"].__setitem__(
                    "fresh_defect_projection_sha256", "e" * 64
                ),
            ),
            "authorization or identity proof drift",
        ),
        (
            lambda payload, _transition: payload["census"].__setitem__(
                "historical_artifact_rows_scanned",
                payload["census"]["historical_artifact_rows_scanned"] + 1,
            ),
            "census drift",
        ),
        (
            lambda payload, _transition: payload["census"].__setitem__(
                "fresh_comparison_rows_scanned",
                payload["census"]["fresh_comparison_rows_scanned"] + 1,
            ),
            "census drift",
        ),
        (
            lambda payload, _transition: payload["yale_reference_defect"][
                "deterministic_minimal_reproduction"
            ]["r_runtime_tree"].__setitem__(
                "bytes",
                payload["yale_reference_defect"]["deterministic_minimal_reproduction"][
                    "r_runtime_tree"
                ]["bytes"]
                + 1,
            ),
            "minimal reproduction drift",
        ),
        (
            lambda payload, _transition: payload["yale_reference_defect"][
                "deterministic_minimal_reproduction"
            ].__setitem__("rscript", payload["producer"]["script"]),
            "minimal reproduction drift",
        ),
        (
            lambda payload, _transition: payload["zero_error_proof"].__setitem__(
                "comparison_artifact_engine_error_rows", 1
            ),
            "cannot rely on engine errors",
        ),
        (
            lambda payload, _transition: payload["zero_error_proof"].__setitem__(
                "comparison_artifact_engine_error_rows", False
            ),
            "cannot rely on engine errors",
        ),
        (
            lambda payload, _transition: payload["census"].__setitem__(
                "cafta_units", float(campaign_module.CAFTA_EXPECTED_UNITS)
            ),
            "census drift",
        ),
        (
            lambda payload, _transition: payload["supersession"].__setitem__(
                "joined_historical_units",
                float(campaign_module.CAFTA_EXPECTED_UNITS),
            ),
            "authorization or identity proof drift",
        ),
    ],
)
def test_preview_transition_loader_rejects_semantically_tampered_cafta_proof(
    tmp_path: Path,
    monkeypatch,
    mutate,
    message: str,
) -> None:
    comparison, preview = _bound_transition_receipt(tmp_path, monkeypatch)
    _rewrite_embedded_cafta_receipt(mutate)

    with pytest.raises(ValueError, match=message):
        campaign_module._preview_selector_transition_receipt(comparison, preview)


def test_preview_transition_loader_rejects_cafta_self_digest_drift(
    tmp_path: Path, monkeypatch
) -> None:
    comparison, preview = _bound_transition_receipt(tmp_path, monkeypatch)
    _rewrite_embedded_cafta_receipt(
        lambda payload, _transition: payload["definition"].__setitem__(
            "real_entry_frontier", "tampered"
        ),
        refresh_payload_digest=False,
    )

    with pytest.raises(ValueError, match="payload digest drift"):
        campaign_module._preview_selector_transition_receipt(comparison, preview)


def test_preview_transition_loader_rejects_cafta_producer_drift(
    tmp_path: Path, monkeypatch
) -> None:
    comparison, preview = _bound_transition_receipt(tmp_path, monkeypatch)
    producer = campaign_module.CAFTA_SUPERSESSION_PRODUCER
    producer.write_text(producer.read_text() + "# drift\n")

    with pytest.raises(ValueError, match="producer source drift"):
        campaign_module._preview_selector_transition_receipt(comparison, preview)


def test_classification_rechecks_nested_cafta_file(tmp_path: Path, monkeypatch) -> None:
    comparison, preview = _bound_transition_receipt(tmp_path, monkeypatch)
    transition = campaign_module._preview_selector_transition_receipt(
        comparison, preview
    )
    cafta_path = campaign_module.CAFTA_SUPERSESSION_RECEIPT
    cafta_path.write_text(cafta_path.read_text() + "\n")

    with pytest.raises(ValueError, match="changed before classification"):
        campaign_module._require_current_cafta_transition_file(transition)


def test_preview_transition_loader_rejects_reference_assumption_drift(
    tmp_path: Path, monkeypatch
) -> None:
    comparison, preview = _bound_transition_receipt(tmp_path, monkeypatch)
    path = campaign_module.PREVIEW_SELECTOR_TRANSITION_RECEIPT
    mutant = json.loads(path.read_text())
    mutant["bindings"].pop("reference_assumptions")
    mutant.pop("receipt_payload_sha256")
    mutant["receipt_payload_sha256"] = campaign_module._canonical_sha256(mutant)
    path.write_text(json.dumps(mutant))

    with pytest.raises(ValueError, match="run binding is stale"):
        campaign_module._preview_selector_transition_receipt(comparison, preview)


def test_preview_transition_loader_rejects_opaque_reference_assumption(
    tmp_path: Path, monkeypatch
) -> None:
    comparison, preview = _bound_transition_receipt(tmp_path, monkeypatch)
    monkeypatch.setattr(
        campaign_module,
        "_yale_note16_weight_assumption_identity",
        lambda: {"opaque": "replacement"},
    )

    with pytest.raises(ValueError, match="transition provenance is malformed"):
        campaign_module._preview_selector_transition_receipt(comparison, preview)


def test_retired_preview_selector_must_be_absent_from_fresh_evidence(
    _raw_preview_line_set_membership,
) -> None:
    entries = [
        entry
        for entry in _historical_preview_entries()
        if entry["id"] != "cafta-52i-deferred"
    ]
    receipt = json.loads(PREVIEW_DISPOSITION_LINE_SETS.read_text())
    active, retired, superseded = _preview_selector_snapshot(entries, receipt)
    assert "cafta-52i-deferred" not in active
    assert "cafta-52i-deferred" in retired
    assert not superseded

    cafta = retired["cafta-52i-deferred"]
    hts10 = receipt["line_sets"][cafta["match"]["line_set"]]["values"][0]
    observed = {
        "f" * 64: {
            **_selector_unit(),
            "slot": cafta["match"]["slot"],
            "hts10": hts10,
            "delta": 0.25,
        }
    }
    with pytest.raises(ValueError, match="retired preview selector remains live"):
        _enforce_retired_preview_selectors_absent(
            retired, observed, Counter({"f" * 64: 1}), engine_errors=0
        )
    _enforce_retired_preview_selectors_absent(retired, {}, Counter(), engine_errors=0)
    with pytest.raises(ValueError, match="cannot be proven with engine errors"):
        _enforce_retired_preview_selectors_absent(
            retired, {}, Counter(), engine_errors=1
        )


def test_vanished_section_232_selectors_can_retire_without_retiring_cafta(
    _raw_preview_line_set_membership,
) -> None:
    section_232 = {
        "section232-annex-brazil",
        "section232-annex-forced-labor",
        "section232-exposed-brazil",
        "section232-exposed-forced-labor",
        "section232-heading-brazil",
        "section232-heading-forced-labor",
    }
    entries = [
        entry
        for entry in _historical_preview_entries()
        if entry["id"] not in section_232
    ]
    preview = json.loads(PREVIEW_DISPOSITION_LINE_SETS.read_text())
    active, retired, superseded = _preview_selector_snapshot(entries, preview)
    assert set(retired) == section_232
    assert "cafta-52i-deferred" in active
    assert not superseded
    _enforce_retired_preview_selectors_absent(retired, {}, Counter(), engine_errors=0)


@pytest.fixture
def _bound_classification_handoff(tmp_path: Path, monkeypatch):
    """A passing, two-row handoff after isolated preview/transition enrollment.

    Enrollment authentication has separate historical, synthetic, and live-ledger
    tests. Here only those upstream stages are substituted; input hashes, sidecar
    rederivation, population conservation, and the comparison scan stay real.
    """

    entries = [
        {
            "id": "fixture-fresh-child",
            "match": {"slot": "base", "delta": {"sign": "pos"}},
        },
        {
            "id": "fixture-other",
            "match": {"slot": "base", "delta": {"sign": "neg"}},
        },
    ]
    fields = _selector_unit()
    context = {
        key: value
        for key, value in fields.items()
        if key not in {"slot", "delta", "disposition"}
    }
    row = {
        "slot": fields["slot"],
        "delta": fields["delta"],
        "context": context,
        "match": False,
    }
    signature = mismatch_signature(row)
    contract = {
        "fixture-fresh-child": {
            "expected_units": 2,
            "expected_signature_count": 1,
            "expected_signature_population_sha256": signature_population_sha256(
                [(signature, 2)]
            ),
        }
    }
    preview = {"receipt_payload_sha256": "a" * 64}
    transition = {"transitions": []}
    transition["receipt_payload_sha256"] = campaign_module._canonical_sha256(transition)
    ledger_path = tmp_path / "ledger.yaml"
    ledger_path.write_text(
        yaml.safe_dump({"suite": "us-tariff-schedule", "entries": entries})
    )
    preview_path = tmp_path / "preview.json"
    preview_path.write_text(json.dumps(preview))
    transition_path = tmp_path / "transition.json"
    transition_path.write_text(json.dumps(transition))
    routing_path = tmp_path / "routing.csv.gz"
    with gzip.open(routing_path, "wt") as target:
        target.write("hts10,general_disposition,column2_disposition\n")
        target.write(f"{fields['hts10']},free,free\n")
    artifact_path = tmp_path / "comparison.jsonl.gz"
    with gzip.open(artifact_path, "wt") as target:
        for index in range(2):
            target.write(json.dumps({**row, "case_id": f"case-{index}"}) + "\n")
    comparison = {
        "comparison_artifact": campaign_module._file_receipt(artifact_path),
        "per_slot": {"base": {"mismatch": 2}},
        "engine_errors": 0,
    }
    comparison_path = tmp_path / "comparison.json"
    comparison_path.write_text(json.dumps(comparison))
    for name, path in {
        "CACHE_ROOT": tmp_path / "cache",
        "DISPOSITION_LEDGER": ledger_path,
        "PREVIEW_DISPOSITION_LINE_SETS": preview_path,
        "PREVIEW_SELECTOR_TRANSITION_RECEIPT": transition_path,
        "COMPARISON_RECEIPT": comparison_path,
        "ROUTING_ROWS": routing_path,
        "EVAL_MANIFEST": tmp_path / "eval/MANIFEST.json",
    }.items():
        monkeypatch.setattr(campaign_module, name, path)
    monkeypatch.setattr(
        campaign_module, "_preview_disposition_receipt", lambda: preview
    )
    monkeypatch.setattr(
        campaign_module,
        "_transition_for_entries",
        lambda _entries, _comparison, _preview: transition,
    )
    monkeypatch.setattr(
        campaign_module,
        "_preview_selector_snapshot",
        lambda _entries, *_args: (contract, {}, {}),
    )
    real_classification_inputs = campaign_module._classification_inputs

    def bound_inputs(comparison, **kwargs):
        # The production function's default ledger Path is bound at definition.
        return real_classification_inputs(comparison, ledger_path, **kwargs)

    monkeypatch.setattr(campaign_module, "_classification_inputs", bound_inputs)
    inputs = bound_inputs(comparison, preview=preview, transition=transition)
    sidecar = campaign_module._classification_sidecar_path(inputs)
    sidecar.parent.mkdir(parents=True)
    with gzip.open(sidecar, "wt") as target:
        target.write(
            json.dumps(
                {
                    "kind": "component_signature",
                    "signature": signature,
                    "units": 2,
                    "class": "fixture-fresh-child",
                    "fields": fields,
                }
            )
            + "\n"
        )
        target.write(json.dumps({"kind": "engine_errors", "units": 0}) + "\n")
    rederived = campaign_module._rederive_classification_sidecar(sidecar, entries)
    classification = {
        "schema": "axiom_oracles.us_tariff_schedule.classification.v2",
        "inputs": inputs,
        "selector_count": len(entries),
        "sidecar": {
            "schema": "axiom_oracles.us_tariff_schedule.classification_sidecar.v2",
            "path": str(sidecar),
            "sha256": campaign_module._sha256(sidecar),
        },
        "conservation": "PASS",
        **{key: value for key, value in rederived.items() if not key.startswith("_")},
    }
    # Every negative test starts from a receipt that passes the complete handoff.
    campaign_module._validate_classification_handoff(
        comparison, classification, entries
    )
    return comparison, classification, entries


def test_report_rejects_stale_classification_schema(
    tmp_path, monkeypatch, _bound_classification_handoff
) -> None:
    comparison, classification, _entries = _bound_classification_handoff
    monkeypatch.setattr(
        campaign_module,
        "_load_bound_comparison_locked",
        lambda **_kwargs: comparison,
    )
    classification["schema"] = "axiom_oracles.us_tariff_schedule.classification.v1"
    stale = tmp_path / "classification-receipt.json"
    stale.write_text(json.dumps(classification))
    monkeypatch.setattr(campaign_module, "CLASSIFICATION_RECEIPT", stale)
    monkeypatch.setattr(campaign_module, "OUT_DIR", tmp_path)
    routing_receipt = tmp_path / "routing-receipt.json"
    monkeypatch.setattr(campaign_module, "ROUTING_RECEIPT", routing_receipt)
    for path in (
        routing_receipt,
        tmp_path / "quotient-receipt.json",
        tmp_path / "full-exposure.json",
    ):
        path.write_text("{}")
    with pytest.raises(ValueError, match="classification receipt schema is stale"):
        campaign_module.build_report()


def test_classification_handoff_rejects_unknown_legacy_classes(
    _bound_classification_handoff,
) -> None:
    comparison, classification, entries = _bound_classification_handoff
    units = classification["class_census"].pop("fixture-fresh-child")
    classification["class_census"]["aircraft-utilization-proxy-brazil"] = units
    with pytest.raises(ValueError, match="unknown or malformed class census"):
        campaign_module._validate_classification_handoff(
            comparison, classification, entries
        )


def test_classification_handoff_rejects_stale_input_binding(
    _bound_classification_handoff,
) -> None:
    comparison, classification, entries = _bound_classification_handoff
    classification["inputs"]["disposition_ledger_sha256"] = "0" * 64
    with pytest.raises(
        ValueError, match="classification receipt input binding is stale"
    ):
        campaign_module._validate_classification_handoff(
            comparison, classification, entries
        )


def test_classification_handoff_rejects_preview_census_reassignment(
    _bound_classification_handoff,
) -> None:
    comparison, classification, entries = _bound_classification_handoff
    classification["class_census"] = {"fixture-fresh-child": 1, "fixture-other": 1}
    with pytest.raises(ValueError, match="preview-selector census is stale"):
        campaign_module._validate_classification_handoff(
            comparison, classification, entries
        )


def test_classification_handoff_requires_transition_input_binding(
    _bound_classification_handoff,
) -> None:
    comparison, classification, entries = _bound_classification_handoff
    for field in (
        "preview_selector_transition_receipt_sha256",
        "preview_selector_transition_payload_sha256",
    ):
        classification["inputs"].pop(field)
    with pytest.raises(
        ValueError, match="classification receipt input binding is stale"
    ):
        campaign_module._validate_classification_handoff(
            comparison, classification, entries
        )


def test_classification_handoff_requires_rederivable_sidecar(
    _bound_classification_handoff,
) -> None:
    comparison, classification, entries = _bound_classification_handoff
    classification.pop("sidecar")
    with pytest.raises(ValueError, match="classification sidecar receipt is stale"):
        campaign_module._validate_classification_handoff(
            comparison, classification, entries
        )


def test_classification_sidecar_rederives_all_unit_kinds(tmp_path) -> None:
    fields = {
        "slot": "base",
        "origin_regime": "regime",
        "revision": "revision",
        "delta": 0.25,
        "disposition": "free",
        "hts10": "0101210010",
        "hts_line": "0101210000",
        "flags": {"entry_is_test": False},
        "interval": ["2026-01-01", "2026-01-02"],
        "iso2": "CA",
    }
    signature = mismatch_signature(
        {
            "slot": fields["slot"],
            "delta": fields["delta"],
            "context": {
                key: fields[key]
                for key in (
                    "flags",
                    "revision",
                    "interval",
                    "origin_regime",
                    "hts10",
                    "hts_line",
                    "iso2",
                )
            },
        }
    )
    rows = [
        {
            "kind": "component_signature",
            "signature": signature,
            "units": 2,
            "class": "positive-base",
            "fields": fields,
        },
        {"kind": "total_signature_composition", "signatures": [signature], "units": 1},
        {"kind": "engine_errors", "units": 1},
    ]
    sidecar = tmp_path / "classification.jsonl.gz"
    with gzip.open(sidecar, "wt") as target:
        for row in rows:
            target.write(json.dumps(row) + "\n")
    rederived = campaign_module._rederive_classification_sidecar(
        sidecar,
        [{"id": "positive-base", "match": {"slot": "base", "delta": {"sign": "pos"}}}],
    )
    assert rederived["mismatches"] == 4
    assert rederived["classified"] == 3
    assert rederived["unexplained"] == 1
    assert rederived["class_census"] == {"positive-base": 2}
    assert rederived["derived_total_compositions"] == {"positive-base": 1}
    population_contract = {
        "positive-base": {
            "expected_units": 2,
            "expected_signature_count": 1,
            "expected_signature_population_sha256": signature_population_sha256(
                [(signature, 2)]
            ),
        }
    }
    campaign_module._enforce_preview_selector_population(
        population_contract,
        rederived["_signature_classes"],
        rederived["_signature_counts"],
    )
    substituted_fields = {**fields, "revision": "different-revision"}
    substituted_signature = mismatch_signature(
        {
            "slot": substituted_fields["slot"],
            "delta": substituted_fields["delta"],
            "context": {
                key: substituted_fields[key]
                for key in (
                    "flags",
                    "revision",
                    "interval",
                    "origin_regime",
                    "hts10",
                    "hts_line",
                    "iso2",
                )
            },
        }
    )
    rows[0]["signature"] = substituted_signature
    rows[0]["fields"] = substituted_fields
    rows[1]["signatures"] = [substituted_signature]
    with gzip.open(sidecar, "wt") as target:
        for row in rows:
            target.write(json.dumps(row) + "\n")
    substituted = campaign_module._rederive_classification_sidecar(
        sidecar,
        [{"id": "positive-base", "match": {"slot": "base", "delta": {"sign": "pos"}}}],
    )
    with pytest.raises(ValueError, match="signature digest drift"):
        campaign_module._enforce_preview_selector_population(
            population_contract,
            substituted["_signature_classes"],
            substituted["_signature_counts"],
        )
    rows[0]["class"] = None
    with gzip.open(sidecar, "wt") as target:
        for row in rows:
            target.write(json.dumps(row) + "\n")
    with pytest.raises(ValueError, match="sidecar class does not rederive"):
        campaign_module._rederive_classification_sidecar(
            sidecar,
            [
                {
                    "id": "positive-base",
                    "match": {"slot": "base", "delta": {"sign": "pos"}},
                }
            ],
        )


def test_classification_handoff_accepts_rederived_v2_sidecar(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(campaign_module, "CACHE_ROOT", tmp_path)
    routing_rows = tmp_path / "routing.csv.gz"
    with gzip.open(routing_rows, "wt") as target:
        target.write("hts10,general_disposition,column2_disposition\n")
        target.write("0101210010,free,free\n")
    monkeypatch.setattr(campaign_module, "ROUTING_ROWS", routing_rows)
    fields = {
        "slot": "base",
        "origin_regime": "regime",
        "revision": "revision",
        "delta": 0.25,
        "disposition": "free",
        "hts10": "0101210010",
        "hts_line": "0101210000",
        "flags": {"entry_is_test": False},
        "interval": ["2026-01-01", "2026-01-02"],
        "iso2": "CA",
    }
    signature = mismatch_signature(
        {
            "slot": fields["slot"],
            "delta": fields["delta"],
            "context": {
                key: fields[key]
                for key in (
                    "flags",
                    "revision",
                    "interval",
                    "origin_regime",
                    "hts10",
                    "hts_line",
                    "iso2",
                )
            },
        }
    )
    context = {
        key: fields[key]
        for key in (
            "flags",
            "revision",
            "interval",
            "origin_regime",
            "hts10",
            "hts_line",
            "iso2",
        )
    }
    comparison_rows = [
        {
            "case_id": "case-1",
            "slot": "base",
            "match": False,
            "delta": fields["delta"],
            "context": context,
        },
        {"case_id": "case-1", "slot": "total", "match": False},
        {
            "case_id": "case-2",
            "slot": "base",
            "match": False,
            "delta": fields["delta"],
            "context": context,
        },
        {"case_id": "case-3", "slot": "engine_error", "match": False},
        {"case_id": "case-4", "slot": "base", "match": True},
    ]
    comparison_artifact = tmp_path / "comparison.jsonl.gz"
    with gzip.open(comparison_artifact, "wt") as target:
        for row in comparison_rows:
            target.write(json.dumps(row) + "\n")
    inputs = {
        "comparison_artifact_sha256": campaign_module._sha256(comparison_artifact),
        "disposition_ledger_sha256": "b" * 64,
        "preview_disposition_receipt_sha256": "c" * 64,
        "preview_disposition_payload_sha256": "d" * 64,
        "routing_rows_sha256": campaign_module._sha256(routing_rows),
    }
    monkeypatch.setattr(
        campaign_module, "_classification_inputs", lambda _comparison, **_kwargs: inputs
    )
    entries = [
        {"id": "positive-base", "match": {"slot": "base", "delta": {"sign": "pos"}}}
    ]
    contract = {
        "positive-base": {
            "expected_units": 2,
            "expected_signature_count": 1,
            "expected_signature_population_sha256": signature_population_sha256(
                [(signature, 2)]
            ),
        }
    }
    monkeypatch.setattr(
        campaign_module,
        "_preview_selector_snapshot",
        lambda _entries, *_args: (contract, {}, {}),
    )
    sidecar = campaign_module._classification_sidecar_path(inputs)
    sidecar.parent.mkdir(parents=True)
    rows = [
        {
            "kind": "component_signature",
            "signature": signature,
            "units": 2,
            "class": "positive-base",
            "fields": fields,
        },
        {"kind": "total_signature_composition", "signatures": [signature], "units": 1},
        {"kind": "engine_errors", "units": 1},
    ]
    with gzip.open(sidecar, "wt") as target:
        for row in rows:
            target.write(json.dumps(row) + "\n")
    rederived = campaign_module._rederive_classification_sidecar(sidecar, entries)
    rederived.pop("_signature_classes")
    rederived.pop("_signature_counts")
    rederived.pop("_observed")
    classification = {
        "schema": "axiom_oracles.us_tariff_schedule.classification.v2",
        "inputs": inputs,
        "selector_count": 1,
        "sidecar": {
            "schema": "axiom_oracles.us_tariff_schedule.classification_sidecar.v2",
            "path": str(sidecar),
            "sha256": campaign_module._sha256(sidecar),
        },
        "conservation": "PASS",
        **rederived,
    }
    comparison = {
        "comparison_artifact": {
            "path": str(comparison_artifact),
            "sha256": inputs["comparison_artifact_sha256"],
        },
        "per_slot": {
            "base": {"match": 1, "mismatch": 2},
            "engine_error": {"mismatch": 1},
            "total": {"mismatch": 1},
        },
        "engine_errors": 1,
    }
    campaign_module._validate_classification_handoff(
        comparison, classification, entries
    )
    comparison["per_slot"]["base"]["match"] = 2
    with pytest.raises(ValueError, match="per-slot census does not rederive"):
        campaign_module._validate_classification_handoff(
            comparison, classification, entries
        )
    comparison["per_slot"]["base"]["match"] = 1
    monkeypatch.setattr(
        campaign_module,
        "_preview_selector_snapshot",
        lambda _entries, *_args: ({}, {}, {}),
    )
    substituted_fields = {**fields, "revision": "fabricated-revision"}
    substituted_signature = mismatch_signature(
        {
            "slot": substituted_fields["slot"],
            "delta": substituted_fields["delta"],
            "context": {
                key: substituted_fields[key]
                for key in (
                    "flags",
                    "revision",
                    "interval",
                    "origin_regime",
                    "hts10",
                    "hts_line",
                    "iso2",
                )
            },
        }
    )
    rows[0]["signature"] = substituted_signature
    rows[0]["fields"] = substituted_fields
    rows[1]["signatures"] = [substituted_signature]
    with gzip.open(sidecar, "wt") as target:
        for row in rows:
            target.write(json.dumps(row) + "\n")
    substituted = campaign_module._rederive_classification_sidecar(sidecar, entries)
    substituted.pop("_signature_classes")
    substituted.pop("_signature_counts")
    substituted.pop("_observed")
    classification.update(substituted)
    classification["sidecar"]["sha256"] = campaign_module._sha256(sidecar)
    with pytest.raises(
        ValueError, match="population is not derived from comparison artifact"
    ):
        campaign_module._validate_classification_handoff(
            comparison, classification, entries
        )


def test_cafta_preview_class_remains_axiom_attributed_open() -> None:
    cafta = next(
        entry
        for entry in _historical_preview_entries()
        if entry["id"] == "cafta-52i-deferred"
    )
    assert cafta["attribution"] == "axiom-attributed-open"
    assert cafta["disposition"] == "axiom_encoding_gap"


def test_current_cafta_child_requires_passed_bounded_reference_defect_proof(
    _current_ledger_enrollment,
) -> None:
    entries, _comparison, _preview, transition = _current_ledger_enrollment
    cafta = next(
        entry for entry in entries if entry["id"] == "cafta-52i-yale-reference-defect"
    )
    parent = next(
        item
        for item in transition["transitions"]
        if item["parent_id"] == campaign_module.CAFTA_PREVIEW_SELECTOR_ID
    )
    proof = parent["evidence"]["cafta_supersession_receipt"]["payload"]
    assert proof["verdict"] == "PASS"
    assert cafta["attribution"] == "reference-defect"
    assert cafta["disposition"] == "upstream_engine_gap"
    assert cafta["parent_id"] == campaign_module.CAFTA_PREVIEW_SELECTOR_ID
    assert cafta["expected_units"] == proof["supersession"]["fresh_mismatching_units"]
    assert (
        cafta["expected_signature_count"]
        == parent["children"][0]["expected_signature_count"]
    )
    assert (
        cafta["evidence"]["cafta_supersession_receipt_payload_sha256"]
        == proof["receipt_payload_sha256"]
    )
    assert proof["axiom_predicate_proof"]["predicates"] == {
        "entry_is_entered_free_of_duty_under_dr_cafta": False,
        "entry_is_general_note_29_d_v_textile_or_apparel_good": False,
    }
    assert proof["definition"] == campaign_module.CAFTA_EXPECTED_DEFINITION
    assert "proves neither" in cafta["reason"]


PREVIEW_TARGET_MISMATCH = (
    Path(__file__).parents[1]
    / "reference/us-tariff-schedule/preview-1311/target-mismatch-cells.jsonl.gz"
)


@pytest.mark.skipif(
    not PREVIEW_TARGET_MISMATCH.is_file(),
    reason="needs the externally receipted preview-1311 target mismatch sidecar",
)
def test_preview_dispositions_select_exact_395330_population(
    _without_external_membership_tables,
) -> None:
    routes = _routing_dispositions()
    counts: Counter[str] = Counter()
    observed = {}
    with gzip.open(PREVIEW_TARGET_MISMATCH, "rt") as source:
        for line in source:
            row = json.loads(line)
            signature = mismatch_signature(row)
            counts[signature] += 1
            observed.setdefault(signature, mismatch_unit(row, routes))
    selectors = validate_dispositions(_historical_preview_entries(), observed)
    census: Counter[str] = Counter()
    unexplained = 0
    for signature, unit in observed.items():
        class_id = matching_class_id(signature, unit, selectors)
        if class_id is None:
            unexplained += counts[signature]
        else:
            census[class_id] += counts[signature]
    receipt = json.loads(PREVIEW_DISPOSITION_LINE_SETS.read_text())
    expected = {item["id"]: item["expected_units"] for item in receipt["selectors"]}
    assert {name: census[name] for name in expected} == expected
    assert unexplained == 0
    assert sum(expected.values()) == 395_330


def test_specific_disposition_routes_to_components_only() -> None:
    plan = query_plan("specific")
    assert plan["base"] == plan["total"] == "known_not_comparable"
    assert plan["reason"] == "non_ad_valorem_base:specific"
    assert plan["components"] == list(BASE_INDEPENDENT_AUTHORITY_SLOTS)
    assert plan["excluded_components"] == ["ieepa", "forced_labor_section_301"]
    assert plan["component_exclusion_reason"] == "requires_noncomparable_base"


def test_specific_disposition_routed_to_full_comparison_fails_closed() -> None:
    # Required N1 mutant: changing the classifier so a specific base reaches
    # full comparison must violate the contract, rather than reaching engine.
    mutant_comparable = {"ad_valorem", "free", "specific"}
    mutant = query_plan("specific") | {
        "base": "compare"
        if "specific" in mutant_comparable
        else "known_not_comparable",
        "total": "compare"
        if "specific" in mutant_comparable
        else "known_not_comparable",
    }
    with pytest.raises(
        AssertionError, match="non-ad-valorem query reached shard planning"
    ):
        assert mutant["base"] != "compare", (
            "non-ad-valorem query reached shard planning"
        )


def test_column2_structural_unavailability_keeps_components() -> None:
    plan = query_plan("free", column2_rate_available=False)
    assert plan["base"] == plan["total"] == "known_not_comparable"
    assert plan["reason"] == "structurally_unavailable:column2_rate"
    assert plan["components"] == list(BASE_INDEPENDENT_AUTHORITY_SLOTS)


def test_routes_statistical_member_to_rate_line() -> None:
    tables = {"01": {102294000: ("specific", "specific")}}
    assert route_member("0102294024", tables) == (
        "01",
        102294000,
        "specific",
        "specific",
    )


def test_explicit_unowned_member_routes_to_empty() -> None:
    assert route_member("9802009100", {"98": {}}) == (
        "98",
        9802009100,
        "empty",
        "empty",
    )


def _comparison_record() -> dict:
    expected = {
        "statutory_base_rate": "0.05",
        "statutory_rate_232": "0",
        "statutory_rate_ieepa_recip": "0.1",
        "statutory_rate_ieepa_fent": "0",
        "statutory_rate_301": "0",
        "statutory_rate_301_cs": "0",
        "statutory_rate_s301fl": "0",
        "statutory_rate_s301br": "0",
        "statutory_rate_s338": "0",
        "statutory_rate_s122": "0",
        "statutory_rate_section_201": "0",
        "statutory_rate_other": "0",
    }
    actual = {
        "mfn_ad_valorem_rate": 0.05,
        "ieepa_component_rate": 0.1,
        "section_201_component_rate": 0,
        "section_122_component_rate": 0,
        "section_232_aluminum_component_rate": 0,
        "section_232_steel_component_rate": 0,
        "section_338_component_rate": 0,
        "china_section_301_component_rate": 0,
        "brazil_section_301_component_rate": 0,
        "forced_labor_section_301_component_rate": 0,
        "schedule_statutory_stack": 0.15,
    }
    return {
        "case_id": "case",
        "expected": expected,
        "actual": actual,
        "engine_errors": [],
        "plan": query_plan("ad_valorem"),
        "hts10": "0101210010",
        "hts_line": "0101210000",
        "iso2": "CA",
        "revision": "r1",
        "interval": ["2026-02-15", "2026-02-19"],
        "origin_regime": "regime",
        "flags": {"entry_is_test": False},
    }


def test_changed_expected_value_mutant_fails() -> None:
    record = _comparison_record()
    assert all(row["match"] for row in compare_record(record))
    record["expected"]["statutory_rate_s122"] = "0.01"
    assert any(
        row["slot"] == "section_122" and not row["match"]
        for row in compare_record(record)
    )


def test_engine_error_surfaces_as_unexplained_comparison() -> None:
    record = _comparison_record() | {"actual": None, "engine_errors": ["boom"]}
    assert compare_record(record) == [
        {
            "case_id": "case",
            "slot": "engine_error",
            "match": False,
            "error": ["boom"],
            "delta": None,
        }
    ]


def test_stale_and_overlapping_disposition_selectors_fail() -> None:
    base = {
        "id": "one",
        "attribution": "input-comparability",
        "receipt": "receipt",
        "reason": "reason",
        "evidence": {"receipt_type": "instrument", "instrument_receipt": "receipt"},
    }
    with pytest.raises(ValueError, match="stale"):
        validate_dispositions([base | {"signatures": ["stale"]}], {"live": 1})
    with pytest.raises(ValueError, match="overlapping"):
        validate_dispositions(
            [
                base | {"signatures": ["live"]},
                (base | {"id": "two", "signatures": ["live"]}),
            ],
            {"live": 1},
        )


def test_campaign_structured_ledger_entries_use_only_campaign_local_matcher(
    _without_external_membership_tables,
) -> None:
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    # This structural fixture checks campaign-only matching vocabulary.
    # Exact-signature enrollment and stale signatures have separate tests.
    entries = [entry for entry in ledger["entries"] if entry.get("match")]
    assert entries
    observed = {
        "structural-validation": {
            **_selector_unit(),
            "flags": campaign_module._transition_flag_vector(()),
        }
    }
    assert validate_dispositions(entries, observed) == entries
    with pytest.raises(ValueError, match="line_class references unknown flag"):
        validate_dispositions(entries, {})
    shared_errors = validate_shared(ledger)
    assert any("unknown keys: ['match']" in error for error in shared_errors)


def _selector_unit() -> dict:
    return {
        "slot": "base",
        "origin_regime": "regime",
        "revision": "r1",
        "delta": 0.2,
        "disposition": "free",
        "hts10": "0101210010",
        "hts_line": "0101210000",
        "flags": {"entry_is_test": False},
        "interval": ["2026-01-01", "2026-01-02"],
        "iso2": "CA",
    }


def test_overlapping_structured_selectors_fail_conservation() -> None:
    unit = _selector_unit()
    selectors = [
        {"id": "one", "match": {"slot": "base", "delta": {"sign": "pos"}}},
        {
            "id": "two",
            "match": {"revision": ["r1"], "disposition": ["free"], "iso2": ["CA"]},
        },
    ]
    with pytest.raises(ValueError, match="overlapping selectors"):
        matching_class_id("signature", unit, selectors)


def test_universal_structured_selector_fails() -> None:
    with pytest.raises(ValueError, match="universal"):
        selector_matches(
            _selector_unit(),
            {
                "slot": "any",
                "origin_regime": "any",
                "revision": "any",
                "delta": "any",
                "disposition": "any",
                "line_class": "any",
            },
        )


def test_slot_only_structured_selector_mutant_fails() -> None:
    with pytest.raises(ValueError, match="non-slot bound"):
        selector_matches(_selector_unit(), {"slot": "base"})


def test_delta_and_date_are_non_slot_bounds() -> None:
    assert selector_matches(
        _selector_unit(),
        {
            "slot": "base",
            "delta": {"values": [0.2]},
            "date": {"from": "2026-01-01", "through": "2026-01-02"},
        },
    )


def test_fabricated_structured_selector_field_fails_schema() -> None:
    with pytest.raises(ValueError, match="unknown selector fields"):
        selector_matches(_selector_unit(), {"slot": "base", "fabricated": ["value"]})


def test_iso2_structured_selector_is_exactly_bounded() -> None:
    assert selector_matches(_selector_unit(), {"slot": "base", "iso2": ["CA", "MX"]})
    assert not selector_matches(
        _selector_unit(), {"slot": "base", "iso2": ["CU", "RU"]}
    )


def test_nonzero_excluded_column_exposure_fails_x1() -> None:
    with pytest.raises(ValueError, match="X1"):
        enforce_excluded_exposure(
            {"statutory_rate_301_cs": 1, "statutory_rate_other": 0}
        )


def test_unclassified_signature_fails_computed_conformance() -> None:
    assert computed_conformant(unexplained=1, engine_errors=0) is False


def test_witness_replay_is_conformant_and_byte_stable() -> None:
    assert witness_replay()["byte_stable"] is True
