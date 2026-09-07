"""Shared isolated real Axiom runtime for bounded continuation evidence batches."""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
import io
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile

from scripts import build_us_tariff_boundary_evidence as original


def value(raw):
    if type(raw) is bool:
        return {"kind": "bool", "value": raw}
    if isinstance(raw, str):
        return {"kind": "text", "value": raw}
    if type(raw) is int:
        return {"kind": "integer", "value": raw}
    if type(raw) is float:
        return {"kind": "decimal", "value": str(raw)}
    raise ValueError("unsupported runtime input type")


def output(raw):
    if raw["kind"] == "judgment":
        original.require(
            raw["outcome"] in ("holds", "not_holds"), "non-binary runtime judgment"
        )
        return raw["outcome"] == "holds"
    if raw["kind"] == "scalar" and raw["value"]["kind"] == "text":
        return raw["value"]["value"]
    original.require(
        raw["kind"] == "scalar" and raw["value"]["kind"] in ("decimal", "integer"),
        "unexpected runtime scalar type: " + str(raw),
    )
    number = Decimal(raw["value"]["value"])
    original.require(number.is_finite(), "non-finite runtime number")
    return str(number.normalize())


def request(module, fixtures, outputs):
    prefix = "us:" + module.removeprefix("us/").removesuffix(".yaml") + "#"
    inputs = []
    queries = []
    for row in fixtures:
        for name, raw in sorted(row["facts"].items()):
            inputs.append(
                {
                    "name": prefix + "input." + name,
                    "entity": "CustomsEntry",
                    "entity_id": row["case_id"],
                    "interval": {"start": row["day"], "end": row["day"]},
                    "value": value(raw),
                }
            )
        queries.append(
            {
                "entity_id": row["case_id"],
                "period": {
                    "period_kind": "custom",
                    "name": "day",
                    "start": row["day"],
                    "end": row["day"],
                },
                "outputs": [prefix + name for name in outputs],
            }
        )
    return {
        "mode": "explain",
        "dataset": {"inputs": inputs, "relations": []},
        "queries": queries,
    }


@contextmanager
def compiled(
    modules,
    *,
    rulespec=original.closure.RULESPEC,
    engine=original.closure.INPUT_INVENTORY_ENGINE,
):
    binary = engine.read_bytes()
    original.require(
        original.digest(binary) == original.closure.INPUT_INVENTORY_ENGINE_SHA256,
        "pinned engine changed",
    )
    with tempfile.TemporaryDirectory(prefix="tariff-continuation-replay-") as raw:
        work = Path(raw)
        exe = work / "axiom-rules-engine"
        exe.write_bytes(binary)
        exe.chmod(0o700)
        archive = subprocess.check_output(
            [
                "git",
                "-C",
                str(rulespec),
                "archive",
                original.closure.RULESPEC_REF,
                "us",
                "programs",
                "tools/b16_entry_flags.py",
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
                    str(exe),
                    "compile",
                    "--program",
                    str(snapshot / module),
                    "--output",
                    str(artifact),
                ],
                check=True,
                capture_output=True,
                env=env,
            )
            programs[module] = {
                "artifact": artifact,
                "program": json.loads(artifact.read_bytes())["program"],
                "module": original.binding(module, (snapshot / module).read_bytes()),
                "compiled_sha256": original.digest(artifact.read_bytes()),
            }

        def execute(module, fixtures, outputs):
            program = programs[module]
            needed = original.closure._reachable_inputs_from_program(
                program["program"], outputs
            )
            effective = []
            for row in fixtures:
                facts = {
                    name: raw
                    for name, raw in row.get("defaults", {}).items()
                    if name in needed
                }
                facts.update(row["facts"])
                original.require(
                    needed <= facts.keys(),
                    "missing explicit fixture facts/defaults: "
                    + str(sorted(needed - facts.keys())),
                )
                effective.append({**row, "facts": facts})
            query = request(module, effective, outputs)
            result = subprocess.run(
                [str(exe), "run-compiled", "--artifact", str(program["artifact"])],
                input=original.canonical(query),
                capture_output=True,
                check=True,
                env=env,
            )
            response = json.loads(result.stdout)
            original.require(
                len(response["results"]) == len(fixtures),
                "runtime result population changed",
            )
            checked = []
            for row, expected_query in zip(
                response["results"], query["queries"], strict=True
            ):
                original.require(
                    row["entity_id"] == expected_query["entity_id"]
                    and row["period"] == expected_query["period"],
                    "runtime identity/period changed",
                )
                original.require(
                    set(row["outputs"]) == set(expected_query["outputs"]),
                    "runtime output population changed",
                )
                actual = {
                    name: output(row["outputs"][absolute])
                    for name, absolute in zip(
                        outputs, expected_query["outputs"], strict=True
                    )
                }
                checked.append({"case_id": row["entity_id"], "actual": actual})
            return {
                "module": program["module"],
                "compiled_sha256": program["compiled_sha256"],
                "request": query,
                "request_sha256": original.digest(original.canonical(query)),
                "response": response,
                "response_sha256": original.digest(original.canonical(response)),
                "results": checked,
            }

        adapter_path = snapshot / "tools/b16_entry_flags.py"
        spec = importlib.util.spec_from_file_location(
            "tariff_boundary_adapter", adapter_path
        )
        adapter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(adapter)
        execute.entry_flags = adapter.entry_flags
        execute.adapter_binding = original.binding(
            "tools/b16_entry_flags.py", adapter_path.read_bytes()
        )
        yield execute
