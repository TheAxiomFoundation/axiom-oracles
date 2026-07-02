"""Subprocess worker: run EUROMOD-platform cases and write JSON results.

Runs inside the *EUROMOD execution environment* — a Python that can load
the ``euromod`` connector and its .NET engine — which is not necessarily
the axiom-oracles interpreter: ``EM_Executable.dll`` requires an x86_64
process, so on Apple Silicon this worker runs under a Rosetta x86_64
Python while axiom-oracles itself stays native. The adapter always
invokes it as a subprocess, on every platform, so there is exactly one
execution path.

Protocol: ``python _runner.py <job.json> <result.json>``. The job carries
the model root, country, system, dataset name, projected input rows, and
the output columns to return. Input rows are overlaid onto a zero-filled
template built from the model's own dataset header (UKMOD's demo schema
has ~22 columns, EUROMOD's ~273 — the template makes one projection serve
both). The engine prints progress chatter to stdout, so results travel
through the result file, never stdout.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _fail(path: Path, message: str) -> None:
    path.write_text(json.dumps({"error": message}), encoding="utf-8")
    sys.exit(0)


def main() -> None:
    job_path, result_path = Path(sys.argv[1]), Path(sys.argv[2])
    job = json.loads(job_path.read_text(encoding="utf-8"))
    try:
        import pandas as pd
        from euromod import Model
    except ImportError as error:
        _fail(
            result_path,
            "The EUROMOD execution environment is missing a dependency "
            f"({error}). Install the euromod connector (and its dense .NET "
            "runtime) into the interpreter named by EUROMOD_PYTHON.",
        )
        return

    model_root = Path(job["model_root"])
    template_name = job.get("template_dataset") or job["dataset"]
    dataset_header_path = model_root / "Input" / f"{template_name}.txt"
    if not dataset_header_path.exists():
        _fail(result_path, f"No dataset file at {dataset_header_path}.")
        return
    with open(dataset_header_path, encoding="utf-8") as handle:
        header = handle.readline().rstrip("\n").split("\t")
    header = [name.strip() for name in header if name.strip()]

    template = {name: 0.0 for name in header}
    frame_rows = []
    for row in job["rows"]:
        filled = dict(template)
        for key, value in row.items():
            if key in filled:
                filled[key] = value
        frame_rows.append(filled)
    frame = pd.DataFrame(frame_rows, columns=header)

    try:
        model = Model(str(model_root))
        country = [c for c in model.countries if c.name == job["country"]][0]
        system = [s for s in country.systems if s.name == job["system"]][0]
        output = system.run(frame, job["dataset"]).outputs[0]
    except Exception as error:  # noqa: BLE001 - report, never crash silently
        _fail(result_path, f"{type(error).__name__}: {error}")
        return

    requested = job.get("outputs") or []
    missing = [name for name in requested if name not in output.columns]
    present = [name for name in requested if name in output.columns]
    payload = {
        "columns": present,
        "missing": missing,
        "idhh": [int(value) for value in output["idhh"].tolist()],
        "values": {name: output[name].tolist() for name in present},
    }
    result_path.write_text(json.dumps(payload), encoding="utf-8")


if __name__ == "__main__":
    main()
