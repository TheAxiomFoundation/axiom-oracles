from __future__ import annotations

import fcntl
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from scripts import build_us_tariff_cafta_supersession_receipt as cafta
from scripts import build_us_tariff_preview_selector_transition_receipt as transition
from scripts import build_us_tariff_remaining_residual_receipt as remaining
from scripts import build_us_tariff_steel_scope_projection_receipt as steel


PRODUCERS = (cafta, transition, steel, remaining)


def _captured_guard(producer: ModuleType, path: Path):
    inputs = producer._ProofInputs()
    inputs.sha256(path)
    inputs.seal()
    return inputs.require_current


def _replace_with_new_inode(path: Path, body: bytes) -> None:
    with tempfile.NamedTemporaryFile(
        "wb", dir=path.parent, prefix=path.name + ".concurrent.", delete=False
    ) as target:
        staged = Path(target.name)
        target.write(body)
        target.flush()
        os.fsync(target.fileno())
    os.replace(staged, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _quarantined(tmp_path: Path, label: str) -> list[Path]:
    return list(tmp_path.glob(f"proof.json.{label}.*/candidate"))


@pytest.mark.parametrize("producer", PRODUCERS, ids=lambda value: value.__name__)
def test_conditional_publish_refuses_concurrent_output_change(
    producer: ModuleType, tmp_path: Path
) -> None:
    output = tmp_path / "proof.json"
    output.write_bytes(b"prior proof\n")
    previous = producer._output_snapshot(output)
    concurrent = b"concurrent proof\n"

    with pytest.raises(ValueError, match="output changed during proof transaction"):
        producer._conditional_publish_output(
            output,
            b"new proof\n",
            previous,
            before_replace=lambda: _replace_with_new_inode(output, concurrent),
        )

    assert output.read_bytes() == concurrent
    assert not list(tmp_path.glob("proof.json.proof.*"))


@pytest.mark.parametrize("producer", PRODUCERS, ids=lambda value: value.__name__)
def test_destination_replacement_after_final_check_is_not_overwritten(
    producer: ModuleType, tmp_path: Path
) -> None:
    output = tmp_path / "proof.json"
    output.write_bytes(b"prior proof\n")
    previous = producer._output_snapshot(output)
    concurrent = b"concurrent after final check\n"

    with pytest.raises(ValueError, match="output changed during proof transaction"):
        producer._conditional_publish_output(
            output,
            b"new proof\n",
            previous,
            after_destination_check=lambda: _replace_with_new_inode(output, concurrent),
        )

    assert output.read_bytes() == concurrent
    assert not list(tmp_path.glob("proof.json.*"))


@pytest.mark.parametrize("producer", PRODUCERS, ids=lambda value: value.__name__)
def test_destination_creation_after_absence_check_is_not_overwritten(
    producer: ModuleType, tmp_path: Path
) -> None:
    output = tmp_path / "proof.json"
    concurrent = b"concurrent creation after final check\n"

    with pytest.raises(ValueError, match="no-clobber publication"):
        producer._conditional_publish_output(
            output,
            b"new proof\n",
            producer._output_snapshot(output),
            after_destination_check=lambda: _replace_with_new_inode(output, concurrent),
        )

    assert output.read_bytes() == concurrent
    assert not list(tmp_path.glob("proof.json.proof.*"))


@pytest.mark.parametrize("producer", PRODUCERS, ids=lambda value: value.__name__)
def test_destination_creation_after_prior_evacuation_is_not_overwritten(
    producer: ModuleType, tmp_path: Path
) -> None:
    output = tmp_path / "proof.json"
    prior = b"prior proof\n"
    concurrent = b"concurrent before install\n"
    output.write_bytes(prior)

    with pytest.raises(ValueError, match="no-clobber publication"):
        producer._conditional_publish_output(
            output,
            b"new proof\n",
            producer._output_snapshot(output),
            before_install=lambda: _replace_with_new_inode(output, concurrent),
        )

    assert output.read_bytes() == concurrent
    prior_candidates = _quarantined(tmp_path, "prior")
    assert len(prior_candidates) == 1
    assert prior_candidates[0].read_bytes() == prior


@pytest.mark.parametrize("producer", PRODUCERS, ids=lambda value: value.__name__)
def test_conditional_publish_refuses_staged_proof_change(
    producer: ModuleType, tmp_path: Path
) -> None:
    output = tmp_path / "proof.json"
    output.write_bytes(b"prior proof\n")
    previous = producer._output_snapshot(output)

    def mutate_staged_proof() -> None:
        staged = list(tmp_path.glob("proof.json.proof.*"))
        assert len(staged) == 1
        _replace_with_new_inode(staged[0], b"tampered staged proof\n")

    with pytest.raises(ValueError, match="output changed during proof transaction"):
        producer._conditional_publish_output(
            output,
            b"new proof\n",
            previous,
            before_replace=mutate_staged_proof,
        )

    assert output.read_bytes() == b"prior proof\n"
    staged = list(tmp_path.glob("proof.json.proof.*"))
    assert len(staged) == 1
    assert staged[0].read_bytes() == b"tampered staged proof\n"


@pytest.mark.parametrize("producer", PRODUCERS, ids=lambda value: value.__name__)
def test_conditional_publish_is_durable_and_preserves_mode(
    producer: ModuleType, tmp_path: Path
) -> None:
    output = tmp_path / "proof.json"
    output.write_bytes(b"prior proof\n")
    output.chmod(0o640)

    producer._conditional_publish_output(
        output,
        b"new proof\n",
        producer._output_snapshot(output),
    )

    assert output.read_bytes() == b"new proof\n"
    assert stat.S_IMODE(output.stat().st_mode) == 0o640
    assert not list(tmp_path.glob("proof.json.proof.*"))


@pytest.mark.parametrize("producer", PRODUCERS, ids=lambda value: value.__name__)
def test_conditional_publish_rejects_captured_input_change_before_replace(
    producer: ModuleType, tmp_path: Path
) -> None:
    proof_input = tmp_path / "proof-input.json"
    proof_input.write_bytes(b"authenticated input\n")
    output = tmp_path / "proof.json"
    output.write_bytes(b"prior proof\n")

    with pytest.raises(ValueError, match="proof input changed"):
        producer._conditional_publish_output(
            output,
            b"new proof\n",
            producer._output_snapshot(output),
            require_current=_captured_guard(producer, proof_input),
            before_replace=lambda: proof_input.write_bytes(b"changed input body\n"),
        )

    assert output.read_bytes() == b"prior proof\n"
    assert not list(tmp_path.glob("proof.json.proof.*"))


@pytest.mark.parametrize("producer", PRODUCERS, ids=lambda value: value.__name__)
def test_late_input_change_rolls_back_exact_prior_output(
    producer: ModuleType, tmp_path: Path
) -> None:
    proof_input = tmp_path / "proof-input.json"
    proof_input.write_bytes(b"authenticated input\n")
    output = tmp_path / "proof.json"
    output.write_bytes(b"prior proof\n")
    output.chmod(0o620)

    with pytest.raises(ValueError, match="proof input changed"):
        producer._conditional_publish_output(
            output,
            b"new proof\n",
            producer._output_snapshot(output),
            require_current=_captured_guard(producer, proof_input),
            after_replace=lambda: proof_input.write_bytes(b"changed input body\n"),
        )

    assert output.read_bytes() == b"prior proof\n"
    assert stat.S_IMODE(output.stat().st_mode) == 0o620
    assert not list(tmp_path.glob("proof.json.*"))


@pytest.mark.parametrize("producer", PRODUCERS, ids=lambda value: value.__name__)
def test_directory_fsync_failure_immediately_after_rename_rolls_back(
    producer: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "proof.json"
    output.write_bytes(b"prior proof\n")
    output.chmod(0o610)
    real_fsync = producer.os.fsync
    failed_directory_sync = False

    def fail_first_directory_sync(file_descriptor: int) -> None:
        nonlocal failed_directory_sync
        if (
            stat.S_ISDIR(producer.os.fstat(file_descriptor).st_mode)
            and not failed_directory_sync
        ):
            failed_directory_sync = True
            raise OSError("injected directory fsync failure")
        real_fsync(file_descriptor)

    monkeypatch.setattr(producer.os, "fsync", fail_first_directory_sync)
    with pytest.raises(OSError, match="injected directory fsync failure"):
        producer._conditional_publish_output(
            output,
            b"new proof\n",
            producer._output_snapshot(output),
        )

    assert failed_directory_sync is True
    assert output.read_bytes() == b"prior proof\n"
    assert stat.S_IMODE(output.stat().st_mode) == 0o610
    assert not list(tmp_path.glob("proof.json.*"))


@pytest.mark.parametrize("producer", PRODUCERS, ids=lambda value: value.__name__)
def test_late_input_change_removes_new_output_when_no_prior_output(
    producer: ModuleType, tmp_path: Path
) -> None:
    proof_input = tmp_path / "proof-input.json"
    proof_input.write_bytes(b"authenticated input\n")
    output = tmp_path / "proof.json"

    with pytest.raises(ValueError, match="proof input changed"):
        producer._conditional_publish_output(
            output,
            b"new proof\n",
            producer._output_snapshot(output),
            require_current=_captured_guard(producer, proof_input),
            after_replace=lambda: proof_input.write_bytes(b"changed input body\n"),
        )

    assert not output.exists()
    assert not list(tmp_path.glob("proof.json.*"))


@pytest.mark.parametrize("producer", PRODUCERS, ids=lambda value: value.__name__)
def test_late_concurrent_output_replacement_is_preserved(
    producer: ModuleType, tmp_path: Path
) -> None:
    output = tmp_path / "proof.json"
    output.write_bytes(b"prior proof\n")
    concurrent = b"concurrent late proof\n"

    with pytest.raises(ValueError, match="output changed during proof transaction"):
        producer._conditional_publish_output(
            output,
            b"new proof\n",
            producer._output_snapshot(output),
            after_replace=lambda: _replace_with_new_inode(output, concurrent),
        )

    assert output.read_bytes() == concurrent
    prior_candidates = _quarantined(tmp_path, "prior")
    assert len(prior_candidates) == 1
    assert prior_candidates[0].read_bytes() == b"prior proof\n"


@pytest.mark.parametrize("producer", PRODUCERS, ids=lambda value: value.__name__)
def test_replacement_before_published_authentication_is_not_misclassified(
    producer: ModuleType, tmp_path: Path
) -> None:
    output = tmp_path / "proof.json"
    prior = b"prior proof\n"
    concurrent = b"concurrent before published authentication\n"
    output.write_bytes(prior)

    with pytest.raises(
        ValueError, match="published proof changed while removing staged alias"
    ):
        producer._conditional_publish_output(
            output,
            b"new proof\n",
            producer._output_snapshot(output),
            after_staged_unlink=lambda: _replace_with_new_inode(output, concurrent),
        )

    assert output.read_bytes() == concurrent
    prior_candidates = _quarantined(tmp_path, "prior")
    assert len(prior_candidates) == 1
    assert prior_candidates[0].read_bytes() == prior
    assert not _quarantined(tmp_path, "rollback")


@pytest.mark.parametrize("producer", PRODUCERS, ids=lambda value: value.__name__)
def test_concurrent_output_during_rollback_is_preserved(
    producer: ModuleType, tmp_path: Path
) -> None:
    proof_input = tmp_path / "proof-input.json"
    proof_input.write_bytes(b"authenticated input\n")
    output = tmp_path / "proof.json"
    output.write_bytes(b"prior proof\n")
    concurrent = b"concurrent rollback proof\n"

    with pytest.raises(ValueError, match="proof input changed"):
        producer._conditional_publish_output(
            output,
            b"new proof\n",
            producer._output_snapshot(output),
            require_current=_captured_guard(producer, proof_input),
            after_replace=lambda: proof_input.write_bytes(b"changed input body\n"),
            before_rollback_displace=lambda: _replace_with_new_inode(
                output, concurrent
            ),
        )

    assert output.read_bytes() == concurrent
    prior_candidates = _quarantined(tmp_path, "prior")
    assert len(prior_candidates) == 1
    assert prior_candidates[0].read_bytes() == b"prior proof\n"


@pytest.mark.parametrize("producer", PRODUCERS, ids=lambda value: value.__name__)
def test_concurrent_output_after_rollback_displacement_is_preserved(
    producer: ModuleType, tmp_path: Path
) -> None:
    proof_input = tmp_path / "proof-input.json"
    proof_input.write_bytes(b"authenticated input\n")
    output = tmp_path / "proof.json"
    output.write_bytes(b"prior proof\n")
    concurrent = b"concurrent after rollback displacement\n"

    with pytest.raises(ValueError, match="proof input changed"):
        producer._conditional_publish_output(
            output,
            b"new proof\n",
            producer._output_snapshot(output),
            require_current=_captured_guard(producer, proof_input),
            after_replace=lambda: proof_input.write_bytes(b"changed input body\n"),
            after_rollback_displace=lambda: _replace_with_new_inode(output, concurrent),
        )

    assert output.read_bytes() == concurrent
    prior_candidates = _quarantined(tmp_path, "prior")
    assert len(prior_candidates) == 1
    assert prior_candidates[0].read_bytes() == b"prior proof\n"
    assert not _quarantined(tmp_path, "rollback")


@pytest.mark.parametrize("producer", PRODUCERS, ids=lambda value: value.__name__)
def test_concurrent_output_after_absent_rollback_displacement_is_preserved(
    producer: ModuleType, tmp_path: Path
) -> None:
    proof_input = tmp_path / "proof-input.json"
    proof_input.write_bytes(b"authenticated input\n")
    output = tmp_path / "proof.json"
    concurrent = b"concurrent after absent rollback displacement\n"

    with pytest.raises(ValueError, match="proof input changed"):
        producer._conditional_publish_output(
            output,
            b"new proof\n",
            producer._output_snapshot(output),
            require_current=_captured_guard(producer, proof_input),
            after_replace=lambda: proof_input.write_bytes(b"changed input body\n"),
            after_rollback_displace=lambda: _replace_with_new_inode(output, concurrent),
        )

    assert output.read_bytes() == concurrent
    assert not _quarantined(tmp_path, "rollback")


@pytest.mark.parametrize("producer", PRODUCERS, ids=lambda value: value.__name__)
def test_tampered_prior_quarantine_is_not_restored_or_deleted(
    producer: ModuleType, tmp_path: Path
) -> None:
    output = tmp_path / "proof.json"
    output.write_bytes(b"prior proof\n")
    tampered = b"tampered quarantined prior\n"

    def tamper_prior() -> None:
        candidates = _quarantined(tmp_path, "prior")
        assert len(candidates) == 1
        _replace_with_new_inode(candidates[0], tampered)

    with pytest.raises(ValueError, match="output changed during proof transaction"):
        producer._conditional_publish_output(
            output,
            b"new proof\n",
            producer._output_snapshot(output),
            after_replace=tamper_prior,
        )

    assert output.read_bytes() == b"new proof\n"
    prior_candidates = _quarantined(tmp_path, "prior")
    assert len(prior_candidates) == 1
    assert prior_candidates[0].read_bytes() == tampered
    assert not _quarantined(tmp_path, "rollback")


@pytest.mark.parametrize("producer", PRODUCERS, ids=lambda value: value.__name__)
def test_tampered_rollback_quarantine_is_not_restored_or_deleted(
    producer: ModuleType, tmp_path: Path
) -> None:
    proof_input = tmp_path / "proof-input.json"
    proof_input.write_bytes(b"authenticated input\n")
    output = tmp_path / "proof.json"
    output.write_bytes(b"prior proof\n")
    tampered = b"tampered rollback candidate\n"

    def tamper_rollback() -> None:
        candidates = _quarantined(tmp_path, "rollback")
        assert len(candidates) == 1
        _replace_with_new_inode(candidates[0], tampered)

    with pytest.raises(ValueError, match="proof input changed"):
        producer._conditional_publish_output(
            output,
            b"new proof\n",
            producer._output_snapshot(output),
            require_current=_captured_guard(producer, proof_input),
            after_replace=lambda: proof_input.write_bytes(b"changed input body\n"),
            after_rollback_displace=tamper_rollback,
        )

    assert output.read_bytes() == b"prior proof\n"
    rollback_candidates = _quarantined(tmp_path, "rollback")
    assert len(rollback_candidates) == 1
    assert rollback_candidates[0].read_bytes() == tampered
    assert not _quarantined(tmp_path, "prior")


@pytest.mark.parametrize("producer", PRODUCERS, ids=lambda value: value.__name__)
def test_check_output_enforces_captured_input_currentness(
    producer: ModuleType, tmp_path: Path
) -> None:
    proof_input = tmp_path / "proof-input.json"
    proof_input.write_bytes(b"authenticated input\n")
    output = tmp_path / "proof.json"
    output.write_bytes(b"current proof\n")
    guard = _captured_guard(producer, proof_input)
    proof_input.write_bytes(b"changed input body\n")

    with pytest.raises(ValueError, match="proof input changed"):
        producer._check_output(
            output,
            b"current proof\n",
            producer._output_snapshot(output),
            require_current=guard,
        )

    assert output.read_bytes() == b"current proof\n"


@pytest.mark.parametrize("producer", PRODUCERS, ids=lambda value: value.__name__)
def test_captured_input_currentness_does_not_rehash(
    producer: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proof_input = tmp_path / "large-proof-input.bin"
    proof_input.write_bytes(b"authenticated once\n")
    inputs = producer._ProofInputs()
    digest = inputs.sha256(proof_input)
    inputs.seal()

    def unexpected_hash(*_args: Any, **_kwargs: Any):
        raise AssertionError("currentness guard rehashed authenticated input")

    monkeypatch.setattr(producer.hashlib, "sha256", unexpected_hash)
    inputs.require_current()
    assert inputs.sha256(proof_input) == digest


@pytest.mark.parametrize("name", ["parser", "source"])
def test_transition_captures_yale_parser_and_source_files(
    name: str, tmp_path: Path
) -> None:
    path = tmp_path / f"{name}.R"
    path.write_bytes(b"authenticated Yale source\n")
    inputs = transition._ProofInputs()
    with inputs.capture_foundation():
        transition._logical_file_receipt(path, logical_path=f"scripts/{name}.R")
    inputs.seal()
    path.write_bytes(b"changed Yale source body\n")

    with pytest.raises(ValueError, match="proof input changed"):
        inputs.require_current()


def test_transition_transaction_guard_rechecks_pinned_yale_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pinned = {
        "commit": "a" * 40,
        "tree": "b" * 40,
        "files": {},
        "classification_precedence": [],
    }
    current = dict(pinned)
    payload = {
        "transitions": [
            {
                "evidence": {
                    "yale_annex_defect_source_proof": {"pinned_yale_source": pinned}
                }
            }
        ]
    }
    preview = tmp_path / "preview.json"
    preview.write_text("{}")
    monkeypatch.setattr(transition, "_build_receipt_impl", lambda **_kwargs: payload)
    monkeypatch.setattr(transition.full, "load_json", lambda _path: {})
    monkeypatch.setattr(
        transition,
        "_verified_yale_annex_classifier",
        lambda **_kwargs: (lambda *_args: ("", ""), dict(current)),
    )

    _document, guard = transition._build_receipt_transaction(
        preview_receipt_path=preview
    )
    current["commit"] = "c" * 40

    with pytest.raises(ValueError, match="pinned Yale source changed"):
        guard()


@pytest.mark.parametrize("mutated", ["receipt", "producer"])
def test_transition_transaction_guard_captures_live_note16_inputs(
    mutated: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    note16_producer = tmp_path / "build_note16.py"
    note16_producer.write_bytes(b"authenticated producer\n")
    note16_receipt = tmp_path / "note16.json"
    producer_receipt = transition.full.file_receipt(
        note16_producer, relative_to=tmp_path
    )
    note16_receipt.write_text(json.dumps({"producer": producer_receipt}))
    preview = tmp_path / "preview.json"
    preview.write_text("{}")
    pinned_yale = {
        "commit": "a" * 40,
        "tree": "b" * 40,
        "files": {},
        "classification_precedence": [],
    }
    payload = {"transitions": []}

    def note16_identity() -> dict[str, Any]:
        receipt = json.loads(note16_receipt.read_text())
        transition.require(
            receipt.get("producer")
            == transition.full.file_receipt(note16_producer, relative_to=tmp_path),
            "Yale Note 16 assumption producer drift",
        )
        return {
            **transition.full.file_receipt(note16_receipt, relative_to=tmp_path),
            "schema": "test.note16.v1",
            "receipt_payload_sha256": "c" * 64,
            "campaign_binding": {"value": True},
            "yale_commit": "a" * 40,
            "yale_tree": "b" * 40,
        }

    monkeypatch.setattr(
        transition.campaign, "YALE_NOTE16_WEIGHT_ASSUMPTION", note16_receipt
    )
    monkeypatch.setattr(
        transition.campaign,
        "YALE_NOTE16_WEIGHT_ASSUMPTION_PRODUCER",
        note16_producer,
    )
    monkeypatch.setattr(
        transition.campaign,
        "_yale_note16_weight_assumption_identity",
        note16_identity,
    )
    monkeypatch.setattr(transition, "_build_receipt_impl", lambda **_kwargs: payload)
    monkeypatch.setattr(transition.full, "load_json", lambda _path: {})
    monkeypatch.setattr(
        transition,
        "_verified_yale_annex_classifier",
        lambda **_kwargs: (lambda *_args: ("", ""), dict(pinned_yale)),
    )

    _document, guard = transition._build_receipt_transaction(
        repo_root=tmp_path,
        preview_receipt_path=preview,
    )
    target = note16_receipt if mutated == "receipt" else note16_producer
    _replace_with_new_inode(target, b"changed live Note-16 proof input\n")

    with pytest.raises(ValueError, match="proof input changed"):
        guard()


def test_transition_preview_validation_requires_exact_producer(
    tmp_path: Path,
) -> None:
    preview = transition.full.load_json(transition.full.PREVIEW_RECEIPT)
    expected_producer = dict(preview["producer"])
    preview["producer"] = {
        **preview["producer"],
        "script": {**preview["producer"]["script"], "sha256": "0" * 64},
    }
    unsigned = dict(preview)
    unsigned.pop("receipt_payload_sha256")
    preview["receipt_payload_sha256"] = transition.full.canonical_sha256(unsigned)
    path = tmp_path / "preview.json"
    path.write_text(transition.full.render(preview))

    with pytest.raises(ValueError, match="preview receipt producer drift"):
        transition._validate_preview(
            path,
            expected_snapshot_sha256=(
                transition.EXPECTED_PREVIEW_ALL_SELECTOR_SNAPSHOT_SHA256
            ),
            expected_selector_units=transition.preview_builder.EXPECTED_SELECTOR_UNITS,
            expected_producer=expected_producer,
        )


@pytest.mark.parametrize("producer", PRODUCERS, ids=lambda value: value.__name__)
def test_public_build_receipt_preserves_dict_api(
    producer: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = _document_for(producer)
    calls: list[dict[str, Any]] = []

    def transaction(**kwargs: Any):
        calls.append(kwargs)
        return document, lambda: None

    monkeypatch.setattr(producer, "_build_receipt_transaction", transaction)
    if producer is cafta:
        result = producer.build_receipt(
            repo_root=tmp_path,
            producer_source=tmp_path / "producer.py",
            preview_receipt_path=tmp_path / "preview.json",
            historical_artifact_path=tmp_path / "history.jsonl.gz",
            eval_manifest_path=tmp_path / "MANIFEST.json",
            comparison_receipt_path=tmp_path / "comparison.json",
            yale_root=tmp_path / "yale",
        )
    else:
        result = producer.build_receipt()

    assert result is document
    assert len(calls) == 1


def _probe_lock_is_held(lock_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import fcntl, sys\n"
                "with open(sys.argv[1], 'a+') as handle:\n"
                "    try:\n"
                "        fcntl.flock(handle.fileno(), "
                "fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
                "    except BlockingIOError:\n"
                "        raise SystemExit(42)\n"
                "raise SystemExit(0)\n"
            ),
            str(lock_path),
        ],
        check=False,
    )
    assert result.returncode == 42


def _document_for(producer: ModuleType) -> dict[str, Any]:
    if producer is cafta:
        return {"verdict": "PASS", "census": {"cafta_units": 1}}
    if producer is transition:
        return {"verdict": "PASS", "transitions": []}
    return {"verdict": "PASS", "receipt_payload_sha256": "a" * 64}


@pytest.mark.parametrize("check", [False, True], ids=("generate", "check"))
@pytest.mark.parametrize("producer", PRODUCERS, ids=lambda value: value.__name__)
def test_main_holds_shared_manifest_lock_through_build_and_publication(
    producer: ModuleType,
    check: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    foundation = producer.full if producer is transition else producer.foundation
    manifest = tmp_path / "reference/us-tariff-schedule/eval/MANIFEST.json"
    manifest.parent.mkdir(parents=True)
    lock_path = manifest.with_name(f".{manifest.name}.lock")
    output = tmp_path / "proof.json"
    document = _document_for(producer)
    rendered = foundation.render(document).encode()
    if check:
        output.write_bytes(rendered)

    build_calls: list[dict[str, Any]] = []
    guard_calls = 0

    def require_current() -> None:
        nonlocal guard_calls
        guard_calls += 1
        _probe_lock_is_held(lock_path)

    def build(**kwargs: Any):
        _probe_lock_is_held(lock_path)
        build_calls.append(kwargs)
        return document, require_current

    monkeypatch.setattr(producer, "build_receipt", build)
    if producer in {steel, remaining}:
        monkeypatch.setattr(foundation, "EVAL_MANIFEST", manifest)

    if check:
        real_check = producer._check_output

        def check_output(*args: Any, **kwargs: Any) -> None:
            _probe_lock_is_held(lock_path)
            real_check(*args, **kwargs)

        monkeypatch.setattr(producer, "_check_output", check_output)
    else:
        real_publish = producer._conditional_publish_output

        def publish(*args: Any, **kwargs: Any) -> None:
            _probe_lock_is_held(lock_path)
            real_publish(
                *args,
                **kwargs,
                before_replace=lambda: _probe_lock_is_held(lock_path),
            )

        monkeypatch.setattr(producer, "_conditional_publish_output", publish)

    producer_name = getattr(
        producer,
        "PRODUCER_SOURCE",
        getattr(producer, "PRODUCER_PATH", producer.__name__),
    )
    argv = [str(producer_name), "--output", str(output)]
    if producer in {cafta, transition}:
        argv.extend(("--eval-manifest", str(manifest)))
    if check:
        argv.append("--check")
    elif producer in {steel, remaining}:
        argv.append("--generate")
    monkeypatch.setattr(sys, "argv", argv)

    assert producer.main() == 0
    assert output.read_bytes() == rendered
    assert len(build_calls) == 1
    assert guard_calls >= 2
    if producer in {cafta, transition}:
        assert build_calls[0]["manifest_locked"] is True


def test_manifest_lock_path_is_process_shared(tmp_path: Path) -> None:
    manifest = tmp_path / "eval/MANIFEST.json"
    manifest.parent.mkdir(parents=True)
    lock_path = manifest.with_name(f".{manifest.name}.lock")
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        _probe_lock_is_held(lock_path)
