from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "produce_executable_receipt.py"
WORKFLOW = ROOT / ".github" / "workflows" / "executable-receipt.yml"

BENEFIT_ID = "us-co:regulations/10-ccr-2506-1/4.207.2#snap_allotment"
NET_INCOME_ID = "us:statutes/7/2014/e/6/A#snap_net_income"
ELIGIBILITY_ID = (
    "us-co:policies/cdhs/snap/fy-2026-benefit-calculation#snap_eligible"
)
WORKFLOW_SPEC = {
    "repository": "TheAxiomFoundation/axiom-oracles",
    "repository_id": "1229891647",
    "path": ".github/workflows/executable-receipt.yml",
    "event": "workflow_dispatch",
    "ref": "refs/heads/main",
}


def _load_producer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "produce_executable_receipt", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


producer = _load_producer()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _github_env() -> dict[str, str]:
    ref = "refs/heads/main"
    return {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": WORKFLOW_SPEC["repository"],
        "GITHUB_REPOSITORY_ID": WORKFLOW_SPEC["repository_id"],
        "GITHUB_EVENT_NAME": WORKFLOW_SPEC["event"],
        "GITHUB_WORKFLOW_SHA": "a" * 40,
        "GITHUB_SHA": "a" * 40,
        "GITHUB_REF": ref,
        "GITHUB_WORKFLOW_REF": (
            f"{WORKFLOW_SPEC['repository']}/{WORKFLOW_SPEC['path']}@{ref}"
        ),
        "GITHUB_RUN_ID": "123456789",
        "GITHUB_RUN_ATTEMPT": "2",
    }


def _golden_bindings() -> dict[str, Any]:
    return {
        "bindings": {
            "snap_benefit_amount": BENEFIT_ID,
            "snap_net_income": NET_INCOME_ID,
            "snap_eligible": ELIGIBILITY_ID,
        },
        "expected": {
            "snap_benefit_amount": 478,
            "snap_net_income": 226,
            "snap_eligible": "holds",
        },
    }


def _engine_response(
    *,
    benefit: Any = 478,
    net_income: Any = 226,
    eligibility: Any = "holds",
) -> bytes:
    return json.dumps(
        {
            "results": [
                {
                    "outputs": {
                        BENEFIT_ID: {
                            "kind": "scalar",
                            "name": "snap_allotment",
                            "id": BENEFIT_ID,
                            "dtype": "integer",
                            "unit": None,
                            "value": {
                                "kind": "integer",
                                "value": benefit,
                            },
                        },
                        NET_INCOME_ID: {
                            "kind": "scalar",
                            "name": "snap_net_income",
                            "id": NET_INCOME_ID,
                            "dtype": "integer",
                            "unit": None,
                            "value": {
                                "kind": "integer",
                                "value": net_income,
                            },
                        },
                        ELIGIBILITY_ID: {
                            "kind": "judgment",
                            "name": "snap_eligible",
                            "id": ELIGIBILITY_ID,
                            "unit": None,
                            "outcome": eligibility,
                        },
                    }
                }
            ]
        }
    ).encode()


@pytest.mark.parametrize("receipt_already_exists", [False, True])
def test_local_cli_fails_without_creating_or_deleting_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    receipt_already_exists: bool,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    receipt_path = tmp_path / "receipt.json"
    manifest_path.write_text(
        json.dumps(
            {
                "receipt_path": "receipt.json",
                "workflow": WORKFLOW_SPEC,
            }
        )
    )
    sentinel = b'{"existing": "governed evidence"}\n'
    if receipt_already_exists:
        receipt_path.write_bytes(sentinel)

    monkeypatch.setattr(producer, "REPO_ROOT", tmp_path.resolve())
    monkeypatch.setattr(producer, "MANIFEST_PATH", manifest_path)
    for name in _github_env():
        monkeypatch.delenv(name, raising=False)
    for name in producer.FORBIDDEN_CREDENTIALS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])

    assert producer.main() != 0
    assert receipt_path.exists() is receipt_already_exists
    if receipt_already_exists:
        assert receipt_path.read_bytes() == sentinel
    assert not (tmp_path / producer.WORK_DIR).exists()
    assert "restricted to GitHub Actions" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ("--engine", "/tmp/dev-engine"),
        ("--engine=/tmp/dev-engine",),
        ("--artifact", "/tmp/unpublished-artifact.json"),
        ("--artifact=/tmp/unpublished-artifact.json",),
    ],
)
def test_cli_rejects_engine_and_artifact_escape_hatches(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: tuple[str, ...],
) -> None:
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), *argv])

    def unexpected_produce() -> Path:
        raise AssertionError("CLI arguments must be rejected before production")

    monkeypatch.setattr(producer, "produce", unexpected_produce)

    assert producer.main() != 0
    assert "argument" in capsys.readouterr().err.lower()


def test_producer_api_has_no_engine_artifact_or_manifest_escape_hatches() -> None:
    assert set(inspect.signature(producer.main).parameters) == set()
    assert set(inspect.signature(producer.produce).parameters) == set()
    workflow_command = [
        line.strip()
        for line in WORKFLOW.read_text().splitlines()
        if "scripts/produce_executable_receipt.py" in line
    ]
    assert workflow_command == [
        "run: python3 scripts/produce_executable_receipt.py"
    ]


def test_workflow_separates_secretless_execution_from_signing() -> None:
    workflow = WORKFLOW.read_text()
    produce_job, sign_job = workflow.split("\n  sign:\n", maxsplit=1)

    assert "permissions: {}" in produce_job
    assert "id-token: write" not in produce_job
    assert "attestations: write" not in produce_job
    assert "scripts/produce_executable_receipt.py" in produce_job
    assert "id-token: write" in sign_job
    assert "attestations: write" in sign_job
    assert "scripts/produce_executable_receipt.py" not in sign_job
    assert "actions/attest-build-provenance@" in sign_job
    assert "receipt.sigstore.json" in sign_job
    assert "${{ secrets." not in workflow


@pytest.mark.parametrize("credential", producer.FORBIDDEN_CREDENTIALS)
def test_credential_bearing_environment_is_rejected(credential: str) -> None:
    env = _github_env()
    env[credential] = "not-usable-in-a-sign-only-job"

    with pytest.raises(producer.ProducerError, match=credential):
        producer._workflow_provenance({"workflow": WORKFLOW_SPEC}, env)


@pytest.mark.parametrize(
    "missing",
    [
        "GITHUB_ACTIONS",
        "GITHUB_REPOSITORY",
        "GITHUB_REPOSITORY_ID",
        "GITHUB_EVENT_NAME",
        "GITHUB_WORKFLOW_SHA",
        "GITHUB_SHA",
        "GITHUB_REF",
        "GITHUB_WORKFLOW_REF",
        "GITHUB_RUN_ID",
        "GITHUB_RUN_ATTEMPT",
    ],
)
def test_workflow_provenance_fields_are_required(missing: str) -> None:
    env = _github_env()
    del env[missing]

    with pytest.raises(producer.ProducerError):
        producer._workflow_provenance({"workflow": WORKFLOW_SPEC}, env)


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("GITHUB_REPOSITORY", "attacker/fork"),
        ("GITHUB_REPOSITORY_ID", "999"),
        ("GITHUB_EVENT_NAME", "pull_request"),
        ("GITHUB_WORKFLOW_SHA", "A" * 40),
        ("GITHUB_WORKFLOW_SHA", "a" * 39),
        ("GITHUB_SHA", "b" * 40),
        (
            "GITHUB_WORKFLOW_REF",
            "TheAxiomFoundation/axiom-oracles/.github/workflows/other.yml"
            "@refs/heads/main",
        ),
        ("GITHUB_RUN_ID", "0"),
        ("GITHUB_RUN_ATTEMPT", "-1"),
    ],
)
def test_workflow_provenance_values_are_pinned(
    field: str, bad_value: str
) -> None:
    env = _github_env()
    env[field] = bad_value

    with pytest.raises(producer.ProducerError):
        producer._workflow_provenance({"workflow": WORKFLOW_SPEC}, env)


def test_workflow_provenance_records_the_governed_run() -> None:
    assert producer._workflow_provenance(
        {"workflow": WORKFLOW_SPEC}, _github_env()
    ) == {
        "repository": WORKFLOW_SPEC["repository"],
        "repository_id": WORKFLOW_SPEC["repository_id"],
        "path": WORKFLOW_SPEC["path"],
        "sha": "a" * 40,
        "source_sha": "a" * 40,
        "run_id": 123456789,
        "run_attempt": 2,
        "event": "workflow_dispatch",
        "ref": "refs/heads/main",
    }


def test_golden_output_extraction_returns_478_226_and_holds() -> None:
    assert producer._extract_outputs(
        _engine_response(), _golden_bindings()
    ) == {
        "snap_benefit_amount": 478,
        "snap_net_income": 226,
        "snap_eligible": "holds",
    }


@pytest.mark.parametrize(
    "response",
    [
        _engine_response(benefit=477),
        _engine_response(net_income=225),
        _engine_response(eligibility="not_holds"),
    ],
)
def test_wrong_golden_output_is_rejected(response: bytes) -> None:
    with pytest.raises(producer.ProducerError, match="golden mismatch"):
        producer._extract_outputs(response, _golden_bindings())


@pytest.mark.parametrize(
    "response",
    [
        pytest.param(
            _engine_response(benefit="478"),
            id="numeric-string",
        ),
        pytest.param(
            _engine_response(benefit=478.0),
            id="float",
        ),
        pytest.param(
            _engine_response().replace(
                b'"value": 478}',
                b'"value": 4.78e2}',
                1,
            ),
            id="scientific-notation",
        ),
        pytest.param(
            _engine_response(benefit=True),
            id="boolean-is-not-integer",
        ),
    ],
)
def test_integer_output_rejects_noninteger_json_types(response: bytes) -> None:
    with pytest.raises(
        producer.ProducerError,
        match="expected exact JSON integer output",
    ):
        producer._extract_outputs(response, _golden_bindings())


def test_integer_output_rejects_wrong_released_engine_value_kind() -> None:
    response = json.loads(_engine_response())
    response["results"][0]["outputs"][BENEFIT_ID]["value"]["kind"] = "decimal"

    with pytest.raises(
        producer.ProducerError,
        match="expected released-engine scalar/integer output",
    ):
        producer._extract_outputs(
            json.dumps(response).encode(),
            _golden_bindings(),
        )


@pytest.mark.parametrize(
    "published_row",
    [
        {
            "jurisdiction": "us-co",
            "program_id": "snap",
            "artifact": "different.compiled.json",
            "artifact_sha256": "b" * 64,
        },
        {
            "jurisdiction": "us-co",
            "program_id": "snap",
            "artifact": "us-co-snap.compiled.json",
            "artifact_sha256": "c" * 64,
        },
    ],
)
def test_published_manifest_binding_mismatch_is_rejected(
    published_row: dict[str, str],
) -> None:
    artifact = {
        "name": "us-co-snap.compiled.json",
        "sha256": "b" * 64,
    }
    with pytest.raises(producer.ProducerError, match="different"):
        producer._published_program_entry(
            {"programs": [published_row]}, artifact
        )


def test_wrong_engine_checksum_is_rejected_after_command_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(producer, "REPO_ROOT", tmp_path.resolve())
    monkeypatch.chdir(tmp_path)
    archive = Path("engine.tar.xz")
    archive.write_bytes(b"wrong released engine bytes")
    commands: list[dict[str, Any]] = []

    def successful_command(
        argv: list[str], **_: Any
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    monkeypatch.setattr(producer.subprocess, "run", successful_command)

    with pytest.raises(producer.ProducerError, match="SHA-256 mismatch"):
        producer._checksum(
            archive,
            "0" * 64,
            Path("engine.sha256"),
            commands,
        )
    assert commands == [
        {
            "argv": [
                "sha256sum",
                "--check",
                "engine.sha256",
            ],
            "exit_code": 0,
        }
    ]


def test_command_recording_captures_nonzero_exit_before_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    argv = ["released-engine", "run-compiled"]
    stdin = b'{"golden": true}\n'
    commands: list[dict[str, Any]] = []

    def failed_command(
        command: list[str], **_: Any
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(command, 23, b"", b"engine failed")

    monkeypatch.setattr(producer.subprocess, "run", failed_command)

    with pytest.raises(producer.ProducerError, match="exited 23"):
        producer._recorded_run(argv, commands, input_bytes=stdin)
    assert commands == [
        {
            "argv": argv,
            "exit_code": 23,
            "stdin_sha256": _sha256(stdin),
        }
    ]


@pytest.fixture
def governed_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> SimpleNamespace:
    repo_root = tmp_path.resolve()
    monkeypatch.setattr(producer, "REPO_ROOT", repo_root)
    monkeypatch.setattr(producer.platform, "system", lambda: "Linux")
    monkeypatch.setattr(producer.platform, "machine", lambda: "x86_64")
    monkeypatch.chdir(repo_root)

    fixture_dir = repo_root / "certificates" / "executable" / "us-co-snap"
    fixture_dir.mkdir(parents=True)
    engine_releases_path = (
        repo_root / "certificates" / "executable" / "engine-releases.json"
    )
    receipt_path = fixture_dir / "receipt.json"
    manifest_path = fixture_dir / "manifest.json"
    input_path = fixture_dir / "golden-request.json"
    outputs_path = fixture_dir / "golden-outputs.json"

    input_document = {
        "dataset": {
            "inputs": [
                {
                    "name": "example#input.monthly_income",
                    "value": {"kind": "integer", "value": 1200},
                }
            ]
        }
    }
    input_bytes = (json.dumps(input_document, sort_keys=True) + "\n").encode()
    outputs_bytes = (
        json.dumps(_golden_bindings(), sort_keys=True) + "\n"
    ).encode()
    input_path.write_bytes(input_bytes)
    outputs_path.write_bytes(outputs_bytes)

    engine_archive = b"pinned released engine archive"
    artifact_bytes = b'{"compiled_program": "published"}\n'
    artifact_name = "us-co-snap.compiled.json"
    artifact_sha = _sha256(artifact_bytes)
    published_manifest = {
        "programs": [
            {
                "jurisdiction": "us-co",
                "program_id": "snap",
                "artifact": artifact_name,
                "artifact_sha256": artifact_sha,
            }
        ]
    }
    published_manifest_bytes = (
        json.dumps(published_manifest, sort_keys=True) + "\n"
    ).encode()

    engine_releases_path.write_text(
        json.dumps(
            {
                "releases": {
                    "v0.1.1": {
                        "repository": (
                            "TheAxiomFoundation/axiom-rules-engine"
                        ),
                        "version": "0.1.1",
                        "assets": {
                            "x86_64-unknown-linux-gnu": {
                                "name": (
                                    "axiom-rules-engine-"
                                    "x86_64-unknown-linux-gnu.tar.xz"
                                ),
                                "sha256": _sha256(engine_archive),
                            }
                        },
                    }
                }
            }
        )
    )
    manifest_path.write_text(
        json.dumps(
            {
                "program": "us-co/snap",
                "receipt_path": (
                    "certificates/executable/us-co-snap/receipt.json"
                ),
                "engine": {
                    "release_manifest": (
                        "certificates/executable/engine-releases.json"
                    ),
                    "release": "v0.1.1",
                    "target": "x86_64-unknown-linux-gnu",
                },
                "artifact": {
                    "repository": "TheAxiomFoundation/rulespec-us",
                    "release": "program-artifacts-test",
                    "release_manifest": {
                        "name": "manifest.json",
                        "sha256": _sha256(published_manifest_bytes),
                    },
                    "name": artifact_name,
                    "sha256": artifact_sha,
                },
                "golden": {
                    "name": "co-snap-golden",
                    "input_path": (
                        "certificates/executable/us-co-snap/"
                        "golden-request.json"
                    ),
                    "input_sha256": _sha256(input_bytes),
                    "outputs_path": (
                        "certificates/executable/us-co-snap/"
                        "golden-outputs.json"
                    ),
                    "outputs_sha256": _sha256(outputs_bytes),
                },
                "workflow": WORKFLOW_SPEC,
            }
        )
    )
    monkeypatch.setattr(producer, "MANIFEST_PATH", manifest_path)
    for name, value in _github_env().items():
        monkeypatch.setenv(name, value)
    for name in producer.FORBIDDEN_CREDENTIALS:
        monkeypatch.delenv(name, raising=False)

    engine_url = (
        "https://github.com/TheAxiomFoundation/axiom-rules-engine/"
        "releases/download/v0.1.1/"
        "axiom-rules-engine-x86_64-unknown-linux-gnu.tar.xz"
    )
    artifact_base = (
        "https://github.com/TheAxiomFoundation/rulespec-us/"
        "releases/download/program-artifacts-test"
    )
    return SimpleNamespace(
        repo_root=repo_root,
        manifest_path=manifest_path,
        receipt_path=receipt_path,
        input_document=input_document,
        input_bytes=input_bytes,
        engine_archive=engine_archive,
        artifact_bytes=artifact_bytes,
        artifact_name=artifact_name,
        published_manifest_bytes=published_manifest_bytes,
        engine_url=engine_url,
        published_manifest_url=f"{artifact_base}/manifest.json",
        artifact_url=f"{artifact_base}/{artifact_name}",
    )


def _install_stranger_path(
    monkeypatch: pytest.MonkeyPatch,
    case: SimpleNamespace,
    *,
    fail_step: int | None = None,
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    downloads = {
        case.engine_url: case.engine_archive,
        case.published_manifest_url: case.published_manifest_bytes,
        case.artifact_url: case.artifact_bytes,
    }

    def fake_run(
        argv: list[str],
        *,
        cwd: Path,
        input: bytes | None,
        capture_output: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[bytes]:
        call = {
            "argv": list(argv),
            "cwd": cwd,
            "input": input,
            "capture_output": capture_output,
            "check": check,
        }
        calls.append(call)
        step = len(calls)
        if step == fail_step:
            return subprocess.CompletedProcess(
                argv, 41, b"", f"failure at command {step}".encode()
            )

        stdout = b""
        if argv[0] == "curl":
            destination = Path(argv[argv.index("--output") + 1])
            url = argv[-1]
            (Path(cwd) / destination).write_bytes(downloads[url])
        elif argv[0] == "tar":
            binary = (
                Path(cwd)
                / producer.WORK_DIR
                / "engine"
                / "axiom-rules-engine-x86_64-unknown-linux-gnu"
                / "axiom-rules-engine"
            )
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_bytes(b"released engine executable")
        elif argv[-1] == "--version":
            stdout = b"axiom-rules-engine 0.1.1\n"
        elif "run-compiled" in argv:
            assert input == case.input_bytes
            stdout = _engine_response()
        elif argv[0] != "sha256sum":
            raise AssertionError(f"unexpected stranger-path command: {argv!r}")

        return subprocess.CompletedProcess(argv, 0, stdout, b"")

    monkeypatch.setattr(producer.subprocess, "run", fake_run)
    return calls


def test_mocked_nine_command_stranger_path_emits_complete_receipt(
    governed_case: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_stranger_path(monkeypatch, governed_case)

    output_path = producer.produce()

    assert output_path == governed_case.receipt_path
    receipt = json.loads(output_path.read_text())
    assert set(receipt) == {
        "schema",
        "program",
        "engine",
        "artifact",
        "golden",
        "commands",
        "timestamp",
        "workflow",
    }
    assert receipt["schema"] == "axiom_oracles.executable_receipt.v1"
    assert receipt["program"] == "us-co/snap"
    assert receipt["engine"] == {
        "repository": "TheAxiomFoundation/axiom-rules-engine",
        "release": "v0.1.1",
        "version": "0.1.1",
        "target": "x86_64-unknown-linux-gnu",
        "asset": "axiom-rules-engine-x86_64-unknown-linux-gnu.tar.xz",
        "sha256": _sha256(governed_case.engine_archive),
    }
    assert receipt["artifact"] == {
        "repository": "TheAxiomFoundation/rulespec-us",
        "release": "program-artifacts-test",
        "name": governed_case.artifact_name,
        "sha256": _sha256(governed_case.artifact_bytes),
        "manifest_sha256": _sha256(governed_case.published_manifest_bytes),
    }
    assert receipt["golden"] == {
        "name": "co-snap-golden",
        "input_path": (
            "certificates/executable/us-co-snap/golden-request.json"
        ),
        "input_sha256": _sha256(governed_case.input_bytes),
        "inputs": governed_case.input_document,
        "outputs": {
            "snap_benefit_amount": 478,
            "snap_net_income": 226,
            "snap_eligible": "holds",
        },
    }
    assert receipt["workflow"] == {
        "repository": WORKFLOW_SPEC["repository"],
        "repository_id": WORKFLOW_SPEC["repository_id"],
        "path": WORKFLOW_SPEC["path"],
        "sha": "a" * 40,
        "source_sha": "a" * 40,
        "run_id": 123456789,
        "run_attempt": 2,
        "event": "workflow_dispatch",
        "ref": "refs/heads/main",
    }
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
        receipt["timestamp"],
    )

    assert len(calls) == 9
    assert len(receipt["commands"]) == 9
    assert [record["exit_code"] for record in receipt["commands"]] == [0] * 9
    assert [Path(record["argv"][0]).name for record in receipt["commands"]] == [
        "curl",
        "sha256sum",
        "tar",
        "axiom-rules-engine",
        "curl",
        "sha256sum",
        "curl",
        "sha256sum",
        "axiom-rules-engine",
    ]
    assert receipt["commands"][-1]["stdin_sha256"] == _sha256(
        governed_case.input_bytes
    )
    assert all(call["cwd"] == governed_case.repo_root for call in calls)
    assert not (governed_case.repo_root / producer.WORK_DIR).exists()


@pytest.mark.parametrize(
    ("fail_step", "failed_command"),
    [
        (1, "curl"),
        (2, "sha256sum"),
        (9, "axiom-rules-engine"),
    ],
)
def test_download_hash_and_run_failures_remove_stale_receipt(
    governed_case: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    fail_step: int,
    failed_command: str,
) -> None:
    governed_case.receipt_path.write_text('{"stale": true}\n')
    calls = _install_stranger_path(
        monkeypatch, governed_case, fail_step=fail_step
    )

    with pytest.raises(producer.ProducerError, match="exited 41"):
        producer.produce()

    assert len(calls) == fail_step
    assert Path(calls[-1]["argv"][0]).name == failed_command
    assert not governed_case.receipt_path.exists()
    assert not (governed_case.repo_root / producer.WORK_DIR).exists()
