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

from axiom_oracles.comparison.dispositions import validate_dispositions as validate_shared

from scripts import us_tariff_schedule_campaign as campaign_module
from scripts.us_tariff_schedule_campaign import (
    BASE_INDEPENDENT_AUTHORITY_SLOTS,
    ENTRY_FLAG_ALIASES,
    EXPECTED_DROPPED_ENTRY_FLAGS,
    PREVIEW_DISPOSITION_LINE_SETS,
    PREVIEW_SELECTOR_COUNT,
    _enforce_preview_selector_population,
    _enforce_retired_preview_selectors_absent,
    _named_line_sets,
    _preview_selector_contract,
    _preview_selector_snapshot,
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
            "tool": {"path": "tools/b16_entry_flags.py", "bytes": 1,
                     "sha256": digest},
            "dependencies": [],
            "producer_sha256": digest,
        },
        "input_contract": {"path": "contract.json", "bytes": 1,
                           "sha256": digest, "schema": "contract"},
        "campaign_evaluator": {
            "campaign": {"path": "campaign.py", "bytes": 1,
                         "sha256": digest},
            "oracle_sources": [],
            "python": {"executable": {"path": "/python", "bytes": 1,
                                      "sha256": digest}, "version": marker},
            "pyyaml_version": marker,
            "producer_sha256": digest,
        },
        "selected_population": {"path": "selected.gz", "bytes": 1,
                                "sha256": digest},
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
            "run_identity_sha256": campaign_module._run_identity_sha256(
                run_identity
            ),
            "generation_id": generation_id,
            "path": str(path),
            "sha256": campaign_module._sha256(path),
            "cases": 0,
            "engine_errors": 0,
            "elapsed_seconds": 0,
        }
    return manifest


def test_declared_feed_drops_only_retired_exemplar_flags() -> None:
    feed = {"hts_line": 1, "entry_is_line_a": False, "entry_is_line_b": False,
            "entry_is_line_c": False, "entry_is_line_d": False, "entry_is_line_e": False}
    declared = {"hts_line", "entry_is_line_a", "entry_is_line_b", "entry_is_line_d"}
    filtered, receipt = filter_declared_feed(
        feed, declared, emitted_flag_names={name for name in feed if name.startswith("entry_")}
    )
    assert set(filtered) == declared
    assert receipt["dropped_entry_flags"] == sorted(EXPECTED_DROPPED_ENTRY_FLAGS)


def test_undeclared_input_mutant_fails_filter_assertion() -> None:
    feed = {"declared": True, "entry_is_line_c": False, "entry_is_line_e": False,
            "mutant_undeclared": True}
    with pytest.raises(ValueError, match="undeclared non-flag inputs"):
        filter_declared_feed(
            feed, {"declared"}, emitted_flag_names={"entry_is_line_c", "entry_is_line_e"}
        )


def test_declared_but_unfed_input_mutant_surfaces_before_default() -> None:
    feed = {"entry_is_line_c": False, "entry_is_line_e": False}
    with pytest.raises(ValueError, match="declared inputs absent from feed:.*required_neutral_fact"):
        filter_declared_feed(
            feed, {"required_neutral_fact"},
            emitted_flag_names={"entry_is_line_c", "entry_is_line_e"},
        )


def test_entry_flag_aliases_canonicalize_when_equal() -> None:
    raw = {
        "entry_is_brazil_301": True,
        "entry_is_brazil_301_listed": True,
        "entry_is_forced_labor_301": False,
        "entry_is_forced_labor_301_listed": False,
        "entry_is_section_232_covered": True,
    }
    flags, aliases = canonicalize_entry_flags(raw)
    assert aliases == tuple(sorted(ENTRY_FLAG_ALIASES))
    assert not (set(flags) & set(ENTRY_FLAG_ALIASES))
    assert flags["entry_is_brazil_301_listed"] is True
    assert flags["entry_is_forced_labor_301_listed"] is False


def test_entry_flag_alias_disagreement_fails_closed() -> None:
    with pytest.raises(ValueError, match="entry-flag alias disagreement"):
        canonicalize_entry_flags({
            "entry_is_brazil_301": True,
            "entry_is_brazil_301_listed": False,
        })


def test_entry_flag_alias_without_canonical_fails_closed() -> None:
    with pytest.raises(ValueError, match="without canonical"):
        canonicalize_entry_flags({"entry_is_brazil_301": True})


@pytest.mark.parametrize("malformed", ["false", 0, 1, None])
def test_entry_flag_values_must_be_boolean(malformed) -> None:
    with pytest.raises(ValueError, match="entry flags must be boolean"):
        canonicalize_entry_flags({
            "entry_is_brazil_301": malformed,
            "entry_is_brazil_301_listed": True,
        })


def test_case_feed_never_forwards_entry_flag_aliases() -> None:
    def entry_flags(_line, _hts, _iso2):
        return {
            "entry_is_brazil_301": True,
            "entry_is_brazil_301_listed": True,
            "entry_is_forced_labor_301": False,
            "entry_is_forced_labor_301_listed": False,
            "entry_is_line_c": False,
            "entry_is_line_e": False,
        }

    feed, flags = _case_feed(
        {"hts10": "0102294024", "iso2": "BR"},
        {"hts_line": "102294000"},
        entry_flags,
    )
    assert not (set(flags) & set(ENTRY_FLAG_ALIASES))
    assert not (set(feed) & set(ENTRY_FLAG_ALIASES))
    assert feed["entry_is_brazil_301_listed"] is True


def test_prepare_eval_manifest_prunes_superseded_keys_and_bindings() -> None:
    run_identity = _fake_run_identity(chapters=("01", "02"))
    run_identity_sha256 = campaign_module._run_identity_sha256(run_identity)
    current = campaign_module._empty_eval_manifest(
        run_identity, EVAL_GENERATION_ID
    ) | {
        "comparison_artifact": {"sha256": "a" * 64},
        "comparison_receipt": {"path": "old", "sha256": "b" * 64},
        "shards": {
            "old-01": {"key": "old-01", "chapter": "01",
                       "run_identity_sha256": run_identity_sha256,
                       "generation_id": EVAL_GENERATION_ID},
            "new-02": {"key": "new-02", "chapter": "02",
                       "run_identity_sha256": run_identity_sha256,
                       "generation_id": EVAL_GENERATION_ID},
        },
    }
    prepared = campaign_module._prepare_eval_manifest(
        current, {"01": "new-01", "02": "new-02"}, run_identity,
        EVAL_GENERATION_ID,
    )
    expected = campaign_module._empty_eval_manifest(
        run_identity, EVAL_GENERATION_ID
    )
    expected["shards"] = {
        "new-02": {"key": "new-02", "chapter": "02",
                   "run_identity_sha256": run_identity_sha256,
                   "generation_id": EVAL_GENERATION_ID},
    }
    assert prepared == expected


def test_prepare_eval_manifest_never_mixes_run_identities(tmp_path) -> None:
    old_identity = _fake_run_identity(marker="a")
    new_identity = _fake_run_identity(marker="b")
    old = _complete_eval_manifest(tmp_path, old_identity)
    current_keys = campaign_module._current_shard_keys(
        new_identity, EVAL_GENERATION_ID
    )
    assert campaign_module._prepare_eval_manifest(
        old, current_keys, new_identity, EVAL_GENERATION_ID
    ) == campaign_module._empty_eval_manifest(
        new_identity, EVAL_GENERATION_ID
    )


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
        campaign_module, "_new_eval_generation_id",
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
            "run_identity_sha256": campaign_module._run_identity_sha256(
                run_identity
            ),
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
        "schema", "run_identity", "run_identity_sha256", "generation_id",
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
        campaign_module, "_new_eval_generation_id",
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
        campaign_module, "_new_eval_generation_id",
        lambda: EVAL_GENERATION_ID,
    )
    replacement_generation = "2" * 32

    def replace_generation(
        chapter, *, generation_id, expected_key, **_kwargs
    ):
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
            "run_identity_sha256": campaign_module._run_identity_sha256(
                run_identity
            ),
            "generation_id": generation_id,
            "path": str(tmp_path / f"{expected_key}.jsonl.gz"),
            "sha256": "c" * 64,
            "cases": 1,
            "engine_errors": 0,
            "elapsed_seconds": 0.1,
        }

    monkeypatch.setattr(
        campaign_module, "_evaluate_chapter", replace_generation
    )
    with pytest.raises(ValueError, match="replaced by another run"):
        campaign_module.evaluate_campaign(
            rulespec_root=tmp_path / "rulespec-us",
            engine_binary=tmp_path / "engine",
            workers=1,
            fresh=True,
            cache_dir=tmp_path / "cache",
        )
    assert json.loads(manifest_path.read_text()) == (
        campaign_module._empty_eval_manifest(
            run_identity, replacement_generation
        )
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
        with pytest.raises(
            ValueError, match="incomplete or contains stale shards"
        ):
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
    manifest_path.write_text(json.dumps(
        _complete_eval_manifest(tmp_path, run_identity)
    ))
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
    manifest_path.write_text(json.dumps(
        _complete_eval_manifest(tmp_path, run_identity)
    ))
    monkeypatch.setattr(campaign_module, "EVAL_MANIFEST", manifest_path)
    monkeypatch.setattr(campaign_module, "COMPARISON_RECEIPT", comparison_path)
    monkeypatch.setattr(campaign_module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        campaign_module, "_current_run_identity", lambda **_kwargs: run_identity
    )
    replacement_generation = "2" * 32
    monkeypatch.setattr(
        campaign_module, "_new_eval_generation_id",
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
        campaign_module._empty_eval_manifest(
            run_identity, replacement_generation
        )
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
        chapter="01", run_identity=original,
        generation_id=EVAL_GENERATION_ID,
    ) != campaign_module._shard_key(
        chapter="01", run_identity=mutant,
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


def test_entry_flag_provenance_binds_live_dependency_content(tmp_path) -> None:
    tool = tmp_path / "tools/b16_entry_flags.py"
    dependency = (
        tmp_path
        / "us/policies/usitc/us-tariff-incidence/generated/note.yaml"
    )
    tool.parent.mkdir(parents=True)
    dependency.parent.mkdir(parents=True)
    tool.write_text(
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        "INCIDENCE_DIR = ROOT / 'us/policies/usitc/us-tariff-incidence/generated'\n"
        "MODULES = ('note.yaml',)\n"
        "def entry_flags(*_args): return {}\n"
    )
    dependency.write_text("old")
    _entry_flags, old = campaign_module._load_entry_flag_tool(tmp_path)
    dependency.write_text("new")
    _entry_flags, new = campaign_module._load_entry_flag_tool(tmp_path)
    assert old["producer_sha256"] != new["producer_sha256"]


def test_campaign_evaluator_identity_binds_adapter_source(
    tmp_path, monkeypatch
) -> None:
    campaign = tmp_path / "campaign.py"
    runner = tmp_path / "runner.py"
    campaign.write_text("campaign")
    runner.write_text("old adapter")
    monkeypatch.setattr(campaign_module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(campaign_module, "__file__", str(campaign))
    monkeypatch.setattr(
        campaign_module, "CAMPAIGN_EVALUATOR_SOURCES", ("runner.py",)
    )
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
    manifest_path.write_text(json.dumps(
        _complete_eval_manifest(tmp_path, run_identity)
    ))
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
        if stage == "classify" else campaign_module.build_report
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
        if stage == "classify" else campaign_module.build_report
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
    assert env["AXIOM_RULESPEC_REPO_ROOTS"] == str(
        rulespec_root.resolve().parent
    )
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
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    contract = _preview_selector_contract(ledger["entries"])
    assert {
        selector_id: selector["match"] for selector_id, selector in contract.items()
    } == {
        selector["id"]: selector["match"] for selector in receipt["selectors"]
    }


def test_preview_selector_match_drift_fails_hermetically() -> None:
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    entries = copy.deepcopy(ledger["entries"])
    entries[0]["match"]["delta"] = {"sign": "neg"}
    with pytest.raises(ValueError, match="preview selector match drift"):
        _preview_selector_contract(entries)


@pytest.mark.parametrize("missing_field", ["slot", "delta"])
def test_preview_selector_requires_exact_match_bounds(missing_field: str) -> None:
    preview = json.loads(PREVIEW_DISPOSITION_LINE_SETS.read_text())
    entries = copy.deepcopy(yaml.safe_load(DISPOSITION_LEDGER.read_text())["entries"])
    selector = preview["selectors"][0]
    ledger_entry = next(entry for entry in entries if entry["id"] == selector["id"])
    selector["match"].pop(missing_field)
    ledger_entry["match"].pop(missing_field)
    with pytest.raises(ValueError, match="invalid preview selector match fields"):
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
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    entries = copy.deepcopy(ledger["entries"])
    entry = next(item for item in entries if item["id"] == "section232-exposed-brazil")
    entry[field] = mutant
    with pytest.raises(ValueError, match=message):
        _preview_selector_contract(entries)


def test_unreceipted_preview_selector_is_rejected() -> None:
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    entries = copy.deepcopy(ledger["entries"])
    mutant = copy.deepcopy(entries[0])
    mutant["id"] = "unreceipted-preview-selector"
    mutant["match"]["delta"] = {"values": [0.123456]}
    entries.append(mutant)
    with pytest.raises(ValueError, match="unreceipted preview selector"):
        _preview_selector_contract(entries)


def test_preview_selector_must_expire_on_source_change() -> None:
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    entries = copy.deepcopy(ledger["entries"])
    entries[0]["expires_on_source_change"] = False
    with pytest.raises(ValueError, match="lost source-change expiry"):
        _preview_selector_contract(entries)


def test_preview_source_hash_mutation_cannot_self_validate(tmp_path, monkeypatch) -> None:
    receipt = json.loads(PREVIEW_DISPOSITION_LINE_SETS.read_text())
    first_input = next(iter(receipt["inputs"].values()))
    first_input["sha256"] = "0" * 64
    receipt.pop("receipt_payload_sha256")
    receipt["receipt_payload_sha256"] = hashlib.sha256(json.dumps(
        receipt, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
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
    receipt["receipt_payload_sha256"] = hashlib.sha256(json.dumps(
        receipt, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
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
            "expected_signature_population_sha256": signature_population_sha256(original),
        }
    }
    _enforce_preview_selector_population(
        contract, {signature: "preview" for signature, _ in original}, Counter(dict(original))
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


def test_retired_preview_selector_must_be_absent_from_fresh_evidence(
    _without_external_membership_tables,
) -> None:
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    entries = [
        entry for entry in ledger["entries"]
        if entry["id"] != "cafta-52i-deferred"
    ]
    active, retired = _preview_selector_snapshot(entries)
    assert "cafta-52i-deferred" not in active
    assert "cafta-52i-deferred" in retired

    cafta = retired["cafta-52i-deferred"]
    receipt = json.loads(PREVIEW_DISPOSITION_LINE_SETS.read_text())
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
    _enforce_retired_preview_selectors_absent(
        retired, {}, Counter(), engine_errors=0
    )
    with pytest.raises(ValueError, match="cannot be proven with engine errors"):
        _enforce_retired_preview_selectors_absent(
            retired, {}, Counter(), engine_errors=1
        )


def test_vanished_section_232_selectors_can_retire_without_retiring_cafta() -> None:
    section_232 = {
        "section232-annex-brazil",
        "section232-annex-forced-labor",
        "section232-exposed-brazil",
        "section232-exposed-forced-labor",
        "section232-heading-brazil",
        "section232-heading-forced-labor",
    }
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    entries = [
        entry for entry in ledger["entries"] if entry["id"] not in section_232
    ]
    active, retired = _preview_selector_snapshot(entries)
    assert set(retired) == section_232
    assert "cafta-52i-deferred" in active
    _enforce_retired_preview_selectors_absent(
        retired, {}, Counter(), engine_errors=0
    )


def test_report_rejects_stale_classification_schema(tmp_path, monkeypatch) -> None:
    comparison = json.loads(campaign_module.COMPARISON_RECEIPT.read_text())
    monkeypatch.setattr(
        campaign_module, "_load_bound_comparison_locked",
        lambda **_kwargs: comparison,
    )
    classification = json.loads(campaign_module.CLASSIFICATION_RECEIPT.read_text())
    classification["schema"] = "axiom_oracles.us_tariff_schedule.classification.v1"
    stale = tmp_path / "classification-receipt.json"
    stale.write_text(json.dumps(classification))
    monkeypatch.setattr(campaign_module, "CLASSIFICATION_RECEIPT", stale)
    with pytest.raises(ValueError, match="classification receipt schema is stale"):
        campaign_module.build_report()


def test_classification_handoff_rejects_unknown_legacy_classes() -> None:
    comparison = json.loads(campaign_module.COMPARISON_RECEIPT.read_text())
    classification = json.loads(campaign_module.CLASSIFICATION_RECEIPT.read_text())
    classification["schema"] = "axiom_oracles.us_tariff_schedule.classification.v2"
    classification["inputs"] = campaign_module._classification_inputs(comparison)
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    with pytest.raises(ValueError, match="unknown or malformed class census"):
        campaign_module._validate_classification_handoff(
            comparison, classification, ledger["entries"]
        )


def test_classification_handoff_rejects_stale_input_binding() -> None:
    comparison = json.loads(campaign_module.COMPARISON_RECEIPT.read_text())
    classification = json.loads(campaign_module.CLASSIFICATION_RECEIPT.read_text())
    classification["schema"] = "axiom_oracles.us_tariff_schedule.classification.v2"
    classification["inputs"] = campaign_module._classification_inputs(comparison)
    classification["inputs"]["disposition_ledger_sha256"] = "0" * 64
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    with pytest.raises(ValueError, match="classification receipt input binding is stale"):
        campaign_module._validate_classification_handoff(
            comparison, classification, ledger["entries"]
        )


def test_classification_handoff_rejects_preview_census_reassignment() -> None:
    comparison = json.loads(campaign_module.COMPARISON_RECEIPT.read_text())
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    classification = {
        "schema": "axiom_oracles.us_tariff_schedule.classification.v2",
        "inputs": campaign_module._classification_inputs(comparison),
        "mismatches": 395_330,
        "classified": 395_330,
        "unexplained": 0,
        "engine_errors": comparison["engine_errors"],
        "class_census": {
            "aircraft-utilization-proxy-brazil": 1,
            "non-metal-232-family": 395_329,
        },
        "derived_total_units": 0,
        "derived_total_compositions": {},
        "selector_count": len(ledger["entries"]),
        "groups": {},
    }
    with pytest.raises(ValueError, match="preview-selector census is stale"):
        campaign_module._validate_classification_handoff(
            comparison, classification, ledger["entries"]
        )


def test_classification_handoff_requires_rederivable_sidecar() -> None:
    comparison = json.loads(campaign_module.COMPARISON_RECEIPT.read_text())
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    contract = campaign_module._preview_selector_contract(ledger["entries"])
    class_census = {
        selector_id: selector["expected_units"]
        for selector_id, selector in contract.items()
    }
    mismatch_total = sum(
        slot.get("mismatch", 0) for slot in comparison["per_slot"].values()
    )
    class_census["non-metal-232-family"] = mismatch_total - sum(class_census.values())
    classification = {
        "schema": "axiom_oracles.us_tariff_schedule.classification.v2",
        "inputs": campaign_module._classification_inputs(comparison),
        "mismatches": mismatch_total,
        "classified": mismatch_total,
        "unexplained": 0,
        "engine_errors": comparison["engine_errors"],
        "class_census": class_census,
        "derived_total_units": 0,
        "derived_total_compositions": {},
        "selector_count": len(ledger["entries"]),
        "groups": {},
    }
    with pytest.raises(ValueError, match="classification sidecar receipt is stale"):
        campaign_module._validate_classification_handoff(
            comparison, classification, ledger["entries"]
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
    signature = mismatch_signature({
        "slot": fields["slot"],
        "delta": fields["delta"],
        "context": {
            key: fields[key]
            for key in (
                "flags", "revision", "interval", "origin_regime", "hts10",
                "hts_line", "iso2",
            )
        },
    })
    rows = [
        {"kind": "component_signature", "signature": signature, "units": 2,
         "class": "positive-base", "fields": fields},
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
    substituted_signature = mismatch_signature({
        "slot": substituted_fields["slot"],
        "delta": substituted_fields["delta"],
        "context": {
            key: substituted_fields[key]
            for key in (
                "flags", "revision", "interval", "origin_regime", "hts10",
                "hts_line", "iso2",
            )
        },
    })
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
            [{"id": "positive-base",
              "match": {"slot": "base", "delta": {"sign": "pos"}}}],
        )


def test_classification_handoff_accepts_rederived_v2_sidecar(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(campaign_module, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(
        campaign_module, "_routing_dispositions",
        lambda: {"0101210010": ("free", "free")},
    )
    fields = {
        "slot": "base", "origin_regime": "regime", "revision": "revision",
        "delta": 0.25, "disposition": "free", "hts10": "0101210010",
        "hts_line": "0101210000", "flags": {"entry_is_test": False},
        "interval": ["2026-01-01", "2026-01-02"], "iso2": "CA",
    }
    signature = mismatch_signature({
        "slot": fields["slot"], "delta": fields["delta"],
        "context": {
            key: fields[key]
            for key in (
                "flags", "revision", "interval", "origin_regime", "hts10",
                "hts_line", "iso2",
            )
        },
    })
    context = {
        key: fields[key]
        for key in (
            "flags", "revision", "interval", "origin_regime", "hts10",
            "hts_line", "iso2",
        )
    }
    comparison_rows = [
        {"case_id": "case-1", "slot": "base", "match": False,
         "delta": fields["delta"], "context": context},
        {"case_id": "case-1", "slot": "total", "match": False},
        {"case_id": "case-2", "slot": "base", "match": False,
         "delta": fields["delta"], "context": context},
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
    }
    monkeypatch.setattr(
        campaign_module, "_classification_inputs", lambda _comparison: inputs
    )
    entries = [
        {"id": "positive-base",
         "match": {"slot": "base", "delta": {"sign": "pos"}}}
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
        lambda _entries: (contract, {}),
    )
    sidecar = campaign_module._classification_sidecar_path(inputs)
    sidecar.parent.mkdir(parents=True)
    rows = [
        {"kind": "component_signature", "signature": signature, "units": 2,
         "class": "positive-base", "fields": fields},
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
            "path": str(sidecar), "sha256": campaign_module._sha256(sidecar),
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
        campaign_module, "_preview_selector_snapshot", lambda _entries: ({}, {})
    )
    substituted_fields = {**fields, "revision": "fabricated-revision"}
    substituted_signature = mismatch_signature({
        "slot": substituted_fields["slot"],
        "delta": substituted_fields["delta"],
        "context": {
            key: substituted_fields[key]
            for key in (
                "flags", "revision", "interval", "origin_regime", "hts10",
                "hts_line", "iso2",
            )
        },
    })
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
    with pytest.raises(ValueError, match="population is not derived from comparison artifact"):
        campaign_module._validate_classification_handoff(
            comparison, classification, entries
        )


def test_cafta_preview_class_remains_axiom_attributed_open() -> None:
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    cafta = next(entry for entry in ledger["entries"] if entry["id"] == "cafta-52i-deferred")
    assert cafta["attribution"] == "axiom-attributed-open"
    assert cafta["disposition"] == "axiom_encoding_gap"


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
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    selectors = validate_dispositions(ledger["entries"], observed)
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
        "base": "compare" if "specific" in mutant_comparable else "known_not_comparable",
        "total": "compare" if "specific" in mutant_comparable else "known_not_comparable",
    }
    with pytest.raises(AssertionError, match="non-ad-valorem query reached shard planning"):
        assert mutant["base"] != "compare", "non-ad-valorem query reached shard planning"


def test_column2_structural_unavailability_keeps_components() -> None:
    plan = query_plan("free", column2_rate_available=False)
    assert plan["base"] == plan["total"] == "known_not_comparable"
    assert plan["reason"] == "structurally_unavailable:column2_rate"
    assert plan["components"] == list(BASE_INDEPENDENT_AUTHORITY_SLOTS)


def test_routes_statistical_member_to_rate_line() -> None:
    tables = {"01": {102294000: ("specific", "specific")}}
    assert route_member("0102294024", tables) == ("01", 102294000, "specific", "specific")


def test_explicit_unowned_member_routes_to_empty() -> None:
    assert route_member("9802009100", {"98": {}}) == (
        "98", 9802009100, "empty", "empty"
    )


def _comparison_record() -> dict:
    expected = {
        "statutory_base_rate": "0.05", "statutory_rate_232": "0",
        "statutory_rate_ieepa_recip": "0.1", "statutory_rate_ieepa_fent": "0",
        "statutory_rate_301": "0", "statutory_rate_301_cs": "0",
        "statutory_rate_s301fl": "0", "statutory_rate_s301br": "0",
        "statutory_rate_s338": "0", "statutory_rate_s122": "0",
        "statutory_rate_section_201": "0", "statutory_rate_other": "0",
    }
    actual = {
        "mfn_ad_valorem_rate": 0.05, "ieepa_component_rate": 0.1,
        "section_201_component_rate": 0, "section_122_component_rate": 0,
        "section_232_aluminum_component_rate": 0, "section_232_steel_component_rate": 0,
        "section_338_component_rate": 0, "china_section_301_component_rate": 0,
        "brazil_section_301_component_rate": 0, "forced_labor_section_301_component_rate": 0,
        "schedule_statutory_stack": 0.15,
    }
    return {"case_id": "case", "expected": expected, "actual": actual, "engine_errors": [],
            "plan": query_plan("ad_valorem"), "hts10": "0101210010", "hts_line": "0101210000",
            "iso2": "CA", "revision": "r1", "interval": ["2026-02-15", "2026-02-19"],
            "origin_regime": "regime", "flags": {"entry_is_test": False}}


def test_changed_expected_value_mutant_fails() -> None:
    record = _comparison_record()
    assert all(row["match"] for row in compare_record(record))
    record["expected"]["statutory_rate_s122"] = "0.01"
    assert any(row["slot"] == "section_122" and not row["match"] for row in compare_record(record))


def test_engine_error_surfaces_as_unexplained_comparison() -> None:
    record = _comparison_record() | {"actual": None, "engine_errors": ["boom"]}
    assert compare_record(record) == [{"case_id": "case", "slot": "engine_error", "match": False,
                                       "error": ["boom"], "delta": None}]


def test_stale_and_overlapping_disposition_selectors_fail() -> None:
    base = {"id": "one", "attribution": "input-comparability", "receipt": "receipt",
            "reason": "reason", "evidence": {"receipt_type": "instrument",
                                                "instrument_receipt": "receipt"}}
    with pytest.raises(ValueError, match="stale"):
        validate_dispositions([base | {"signatures": ["stale"]}], {"live": 1})
    with pytest.raises(ValueError, match="overlapping"):
        validate_dispositions([base | {"signatures": ["live"]},
                               (base | {"id": "two", "signatures": ["live"]})], {"live": 1})


def test_campaign_ledger_uses_only_campaign_local_matcher(
    _without_external_membership_tables,
) -> None:
    ledger = yaml.safe_load(DISPOSITION_LEDGER.read_text())
    entries = ledger["entries"]
    assert any(entry.get("match") for entry in entries)
    assert validate_dispositions(entries, {}) == entries
    shared_errors = validate_shared(ledger)
    assert any("unknown keys: ['match']" in error for error in shared_errors)


def _selector_unit() -> dict:
    return {
        "slot": "base", "origin_regime": "regime", "revision": "r1", "delta": 0.2,
        "disposition": "free", "hts10": "0101210010", "hts_line": "0101210000",
        "flags": {"entry_is_test": False}, "interval": ["2026-01-01", "2026-01-02"],
        "iso2": "CA",
    }


def test_overlapping_structured_selectors_fail_conservation() -> None:
    unit = _selector_unit()
    selectors = [
        {"id": "one", "match": {"slot": "base", "delta": {"sign": "pos"}}},
        {"id": "two", "match": {"revision": ["r1"], "disposition": ["free"],
                                  "iso2": ["CA"]}},
    ]
    with pytest.raises(ValueError, match="overlapping selectors"):
        matching_class_id("signature", unit, selectors)


def test_universal_structured_selector_fails() -> None:
    with pytest.raises(ValueError, match="universal"):
        selector_matches(_selector_unit(), {
            "slot": "any", "origin_regime": "any", "revision": "any", "delta": "any",
            "disposition": "any", "line_class": "any",
        })


def test_slot_only_structured_selector_mutant_fails() -> None:
    with pytest.raises(ValueError, match="non-slot bound"):
        selector_matches(_selector_unit(), {"slot": "base"})


def test_delta_and_date_are_non_slot_bounds() -> None:
    assert selector_matches(_selector_unit(), {
        "slot": "base", "delta": {"values": [0.2]},
        "date": {"from": "2026-01-01", "through": "2026-01-02"},
    })


def test_fabricated_structured_selector_field_fails_schema() -> None:
    with pytest.raises(ValueError, match="unknown selector fields"):
        selector_matches(_selector_unit(), {"slot": "base", "fabricated": ["value"]})


def test_iso2_structured_selector_is_exactly_bounded() -> None:
    assert selector_matches(_selector_unit(), {"slot": "base", "iso2": ["CA", "MX"]})
    assert not selector_matches(_selector_unit(), {"slot": "base", "iso2": ["CU", "RU"]})


def test_nonzero_excluded_column_exposure_fails_x1() -> None:
    with pytest.raises(ValueError, match="X1"):
        enforce_excluded_exposure({"statutory_rate_301_cs": 1, "statutory_rate_other": 0})


def test_unclassified_signature_fails_computed_conformance() -> None:
    assert computed_conformant(unexplained=1, engine_errors=0) is False


def test_witness_replay_is_conformant_and_byte_stable() -> None:
    assert witness_replay()["byte_stable"] is True
