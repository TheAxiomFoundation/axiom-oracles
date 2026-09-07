"""Isolated pinned Axiom execution that also preserves native failure responses."""

from __future__ import annotations
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
from scripts import build_us_tariff_boundary_evidence as original


@contextmanager
def compiled(modules):
    engine_bytes = original.closure.INPUT_INVENTORY_ENGINE.read_bytes()
    original.require(
        original.digest(engine_bytes) == original.closure.INPUT_INVENTORY_ENGINE_SHA256,
        "pinned engine changed",
    )
    with tempfile.TemporaryDirectory(prefix="tariff-native-replay-") as raw:
        work = Path(raw)
        engine = work / "axiom-rules-engine"
        engine.write_bytes(engine_bytes)
        engine.chmod(0o700)
        archive = subprocess.check_output(
            [
                "git",
                "-C",
                str(original.closure.RULESPEC),
                "archive",
                original.closure.RULESPEC_REF,
                "us",
                "programs",
            ]
        )
        snapshot = work / "rulespec-us"
        snapshot.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(snapshot, filter="data")
        env = dict(os.environ)
        env.pop("AXIOM_RULESPEC_ROOT", None)
        env["AXIOM_RULESPEC_REPO_ROOTS"] = str(work)
        programs = {}
        for index, module in enumerate(modules):
            artifact = work / f"{index}.compiled.json"
            subprocess.run(
                [
                    str(engine),
                    "compile",
                    "--program",
                    str(snapshot / module),
                    "--output",
                    str(artifact),
                ],
                capture_output=True,
                check=True,
                env=env,
            )
            programs[module] = {
                "path": artifact,
                "compiled_bytes": artifact.read_bytes(),
                "module": original.binding(module, (snapshot / module).read_bytes()),
            }

        def invoke(module, request):
            program = programs[module]
            result = subprocess.run(
                [str(engine), "run-compiled", "--artifact", str(program["path"])],
                input=original.canonical(request),
                capture_output=True,
                env=env,
            )
            stdout = result.stdout.decode()
            try:
                response = json.loads(stdout)
            except json.JSONDecodeError:
                response = None
            return {
                "module": program["module"],
                "compiled_sha256": original.digest(program["compiled_bytes"]),
                "request": request,
                "request_sha256": original.digest(original.canonical(request)),
                "returncode": result.returncode,
                "stdout": stdout,
                "stderr": result.stderr.decode(),
                "response": response,
                "response_sha256": original.digest(original.canonical(response))
                if response is not None
                else None,
            }

        invoke.programs = programs
        yield invoke
