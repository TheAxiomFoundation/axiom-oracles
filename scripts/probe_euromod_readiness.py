#!/usr/bin/env python3
"""Probe EUROMOD-platform countries for oracle readiness.

Runs INSIDE the EUROMOD execution environment (the interpreter with the
``euromod`` connector — ``$EUROMOD_PYTHON``; on Apple Silicon a Rosetta
venv, see docs/euromod-platform-playbook.md). For each country it smoke-
runs three demo households through the latest system, first under the
bundled ``<CC>_training_data`` name and then — when the spine gates
content on real dataset names (ec-jrc/JRC-EUROMOD-software-source-code#4)
— under the newest real dataset configuration with the training schema as
the row template.

Usage::

    $EUROMOD_PYTHON scripts/probe_euromod_readiness.py <model_root> [CC ...]

Writes JSON to stdout; redirect into
``axiom_oracles/data/euromod_country_readiness.json`` (with the manifest
header fields) when refreshing the committed matrix for a new release.
"""

from __future__ import annotations

import json
import re
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


def probe(model_root: Path, only: set[str]) -> dict:
    import pandas as pd
    from euromod import Model

    model = Model(str(model_root))
    results: dict[str, dict] = {}
    for country in model.countries:
        code = country.name
        if not re.fullmatch(r"[A-Z]{2}", code):
            continue
        if only and code not in only:
            continue
        entry: dict = {
            "systems": None,
            "latest_system": None,
            "training_dataset": None,
            "training_rows": None,
            "status": "unknown",
            "run_dataset": None,
            "template_dataset": None,
            "error": None,
        }
        results[code] = entry
        try:
            systems = [s.name for s in country.systems]
            entry["systems"] = f"{systems[0]}..{systems[-1]} ({len(systems)})"
            latest = sorted(systems)[-1]
            entry["latest_system"] = latest
            system = [s for s in country.systems if s.name == latest][0]

            training = f"{code}_training_data"
            training_path = model_root / "Input" / f"{training}.txt"
            if not training_path.exists():
                entry["status"] = "no_training_data"
                continue
            entry["training_dataset"] = training
            frame = pd.read_csv(training_path, sep="\t")
            entry["training_rows"] = int(frame.idhh.nunique())
            sample = frame[frame.idhh.isin(frame.idhh.unique()[:3])]

            def run(dataset_name: str) -> None:
                # The engine narrates to stdout; keep probe output clean.
                with redirect_stdout(StringIO()):
                    system.run(sample, dataset_name, verbose=False, nowarnings=True)

            try:
                run(training)
                entry["status"] = "ok_training_name"
                entry["run_dataset"] = training
                continue
            except Exception as training_error:  # noqa: BLE001 - probe records it
                entry["error"] = str(training_error)[:120]

            real = sorted(
                (
                    d.name
                    for d in system.datasets
                    if "hhot" not in d.name.lower()
                    and "training" not in d.name.lower()
                ),
                reverse=True,
            )
            for candidate in real[:2]:
                try:
                    run(candidate)
                    entry["status"] = "ok_real_config_workaround"
                    entry["run_dataset"] = candidate
                    entry["template_dataset"] = training
                    entry["error"] = None
                    break
                except Exception as retry_error:  # noqa: BLE001
                    entry["error"] = str(retry_error)[:120]
            else:
                entry["status"] = "fails"
        except Exception as outer:  # noqa: BLE001
            entry["status"] = "load_error"
            entry["error"] = str(outer)[:120]
    return results


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    model_root = Path(sys.argv[1]).expanduser()
    only = {code.upper() for code in sys.argv[2:]}
    results = probe(model_root, only)
    runnable = sum(1 for e in results.values() if e["status"].startswith("ok"))
    print(json.dumps(results, indent=2))
    print(f"{runnable}/{len(results)} countries runnable", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
