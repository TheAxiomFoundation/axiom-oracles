"""Small contract double for the parked executable receipt validator.

Production deliberately imports the real implementation from
``autogo/executable-producer`` once that branch lands.  CLI tests put this
module first on ``PYTHONPATH`` so the integration can exercise the exact public
return interface without copying the parked implementation into this branch.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True, slots=True)
class ReceiptValidation:
    valid: bool
    failures: tuple[str, ...]
    receipt_sha256: str | None = None
    evidence: dict[str, Any] | None = None


def validate_executable_receipt(
    receipt: str | Path,
    *,
    repo_root: str | Path,
    manifest_path: str | Path,
    expected_outputs: dict[str, Any] | None = None,
) -> ReceiptValidation:
    """Validate the fixture's trust-root relationships and return v1 evidence."""

    root = Path(repo_root).resolve()
    receipt_path = Path(receipt).resolve()
    manifest_path = Path(manifest_path).resolve()
    failures: list[str] = []
    try:
        receipt_value = json.loads(receipt_path.read_text())
        manifest = json.loads(manifest_path.read_text())
        golden = manifest["golden"]
        bindings_path = (root / golden["outputs_path"]).resolve()
        bindings = json.loads(bindings_path.read_text())
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        return ReceiptValidation(False, (f"fixture trust roots: {exc}",))

    receipt_hash = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    if receipt_value.get("schema") != "axiom_oracles.executable_receipt.v1":
        failures.append("receipt schema")
    if receipt_value.get("program") != manifest.get("program"):
        failures.append("receipt program")

    engine = receipt_value.get("engine")
    if (
        not isinstance(engine, dict)
        or engine.get("release") != manifest.get("engine", {}).get("release")
        or not isinstance(engine.get("sha256"), str)
    ):
        failures.append("released engine")
    artifact = receipt_value.get("artifact")
    if not isinstance(artifact, dict) or artifact.get("sha256") != manifest.get(
        "artifact", {}
    ).get("sha256"):
        failures.append("published artifact")

    expected = bindings.get("expected")
    outputs = receipt_value.get("golden", {}).get("outputs")
    if outputs != expected or (
        expected_outputs is not None and expected_outputs != expected
    ):
        failures.append("golden outputs")
    commands = receipt_value.get("commands")
    if (
        not isinstance(commands, list)
        or not commands
        or any(
            not isinstance(command, dict) or command.get("exit_code") != 0
            for command in commands
        )
    ):
        failures.append("command sequence")

    workflow = receipt_value.get("workflow")
    expected_workflow = manifest.get("workflow")
    if (
        not isinstance(workflow, dict)
        or not isinstance(expected_workflow, dict)
        or any(
            workflow.get(field) != expected_workflow.get(field)
            for field in ("repository", "path", "event", "ref")
        )
        or not isinstance(workflow.get("sha"), str)
        or _COMMIT_RE.fullmatch(workflow["sha"]) is None
    ):
        failures.append("governed executable workflow")

    evidence = {
        "schema": "axiom_oracles.executable_receipt.v1",
        "program": manifest.get("program"),
        "engine": engine,
        "artifact": artifact,
        "golden": receipt_value.get("golden"),
        "workflow": workflow,
    }
    return ReceiptValidation(
        not failures,
        tuple(failures),
        receipt_sha256=receipt_hash,
        evidence=evidence,
    )
