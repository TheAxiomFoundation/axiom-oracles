#!/usr/bin/env python3
"""Build the local RWAMOD input-schema header the rw-* suites run against.

RWAMOD (SOUTHMOD Rwanda, SOUTHMOD A4.0) registers the dataset name
``rw_2024_a1`` but the bundle ships no Rwandan input file, and its data
configuration lists no variables. The EUROMOD worker reads the input-row
schema from the first line of ``<model_root>/Input/<dataset>.txt``
(``axiom_oracles/adapters/euromod/_runner.py``) and silently drops any case
input that is not a schema column, so the rw-* comparison suites need a
header-only file under that name before they can run.

This script derives that header from the licensed bundle itself and writes
it only into the bundle's ``Input/`` directory:

1. Seed the column list from the first line of a bundled sister SOUTHMOD
   dataset (default ``et_2022_a2``).
2. Run RW_2025 on one zero-filled synthetic row with that schema.
3. While the run fails, append the variables the engine reports as unknown
   (sorted within each attempt) and run again.
4. Once the run is clean, append the input variables the engine reports it
   read as zero because the schema lacks them (in the order it reports
   them; these include inputs the suites set, such as monthly turnover and
   the pensioner flag), and run again until it reports none.
5. Write the column names as one tab-separated line to
   ``<model_root>/Input/<dataset>.txt``.

Nothing derived from the bundle is written to the repository: the output
path must resolve inside ``<model_root>/Input`` and outside this checkout,
the engine log is captured to a temporary file and discarded, and the
script prints only counts. Run it with the x86_64 interpreter that carries
the ``euromod`` connector (``EUROMOD_PYTHON``; see
docs/euromod-platform-playbook.md):

    $EUROMOD_PYTHON scripts/southmod_rw_header.py            # create if absent
    $EUROMOD_PYTHON scripts/southmod_rw_header.py --check    # rebuild in memory, compare
    $EUROMOD_PYTHON scripts/southmod_rw_header.py --force    # rebuild and overwrite

``--check`` exits 1 when the existing file differs from a fresh build (or is
missing) and says whether the difference is the column set or only the
column order.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_ROOT = "~/.axiom/oracles/southmod/bundle/SOUTHMOD_A4.0"
UNKNOWN_VARIABLE = re.compile(r"unknown variable (\w+)")
DEFAULTED_TO_ZERO = re.compile(
    r"Variable\(s\) ([\w ,]+?) not found in user-provided lists \(zero is used as default\)"
)

# One synthetic formal earner, as in the harness probe that first assembled
# the schema; every other column is zero-filled.
_PROBE_ROW = {
    "idhh": 1,
    "idperson": 101,
    "idpartner": 0,
    "idmother": 0,
    "idfather": 0,
    "dwt": 1.0,
    "dag": 35,
    "dgn": 1,
    "dms": 1,
    "dhh": 1,
    "les": 3,
    "lfo": 1,
    "yem": 100000.0,
}


def _read_header(path: Path) -> list[str]:
    with open(path, encoding="utf-8") as handle:
        first_line = handle.readline().rstrip("\n").split("\t")
    return [name.strip() for name in first_line if name.strip()]


def _unknown_variables(log: str) -> list[str]:
    """Variables the engine rejected as unknown, sorted and de-duplicated."""

    return sorted(set(UNKNOWN_VARIABLE.findall(log)))


def _defaulted_variables(log: str) -> list[str]:
    """Variables the engine read as zero, in the order it first reports them."""

    names: list[str] = []
    for match in DEFAULTED_TO_ZERO.finditer(log):
        for name in match.group(1).split(","):
            name = name.strip()
            if name and name not in names:
                names.append(name)
    return names


@contextlib.contextmanager
def _captured_process_output():
    """Capture fd-level stdout/stderr, where the .NET engine logs.

    The EUROMOD engine reports schema problems on the process's own output
    streams, not in the Python exception text, so both file descriptors
    point at a temporary file for the duration of a run. The captured log
    stays local (it names model internals) and only variable names are
    parsed out of it.
    """

    sys.stdout.flush()
    sys.stderr.flush()
    saved = (os.dup(1), os.dup(2))
    log: dict[str, str] = {"text": ""}
    with tempfile.TemporaryFile(mode="w+b") as sink:
        os.dup2(sink.fileno(), 1)
        os.dup2(sink.fileno(), 2)
        try:
            yield log
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
            os.dup2(saved[0], 1)
            os.dup2(saved[1], 2)
            os.close(saved[0])
            os.close(saved[1])
            sink.seek(0)
            log["text"] = sink.read().decode("utf-8", errors="replace")


def build_header(
    model_root: Path,
    *,
    seed_dataset: str,
    country: str,
    system_name: str,
    dataset: str,
    max_attempts: int,
) -> list[str]:
    """Return the column list on which ``system_name`` runs without gaps."""

    import pandas as pd
    from euromod import Model

    seed_path = model_root / "Input" / f"{seed_dataset}.txt"
    if not seed_path.exists():
        raise SystemExit(f"Seed dataset header not found: {seed_path}")
    columns = _read_header(seed_path)
    print(f"seed {seed_dataset}: {len(columns)} columns")

    model = Model(str(model_root))
    matches = [c for c in model.countries if c.name == country]
    if not matches:
        raise SystemExit(f"Country {country} is not in {model_root}")
    systems = [s for s in matches[0].systems if s.name == system_name]
    if not systems:
        raise SystemExit(f"System {system_name} is not in country {country}")
    system = systems[0]

    for attempt in range(1, max_attempts + 1):
        row = {name: 0 for name in columns}
        row.update(_PROBE_ROW)
        frame = pd.DataFrame([row], columns=columns)
        failure: Exception | None = None
        with _captured_process_output() as log:
            try:
                system.run(frame, dataset)
            except Exception as error:  # noqa: BLE001 - the engine reports schema gaps as errors
                failure = error
        if failure is not None:
            reported = _unknown_variables(log["text"] + "\n" + str(failure))
            missing = [name for name in reported if name not in columns]
            if not missing:
                raise SystemExit(
                    f"attempt {attempt}: run failed without an unknown-variable "
                    f"report ({type(failure).__name__}); stopping"
                ) from failure
            columns.extend(missing)
            print(f"attempt {attempt}: +{len(missing)} unknown variables")
            continue
        defaulted = [name for name in _defaulted_variables(log["text"]) if name not in columns]
        if defaulted:
            columns.extend(defaulted)
            print(f"attempt {attempt}: clean run; +{len(defaulted)} variables read as zero")
            continue
        print(f"attempt {attempt}: clean run, no gaps, {len(columns)} columns")
        return columns
    raise SystemExit(f"Schema still incomplete after {max_attempts} attempts")


def _target_path(model_root: Path, dataset: str) -> Path:
    input_dir = (model_root / "Input").resolve()
    target = (input_dir / f"{dataset}.txt").resolve()
    if target.parent != input_dir:
        raise SystemExit(f"Refusing to write outside {input_dir}: {target}")
    if target.is_relative_to(REPO_ROOT.resolve()):
        raise SystemExit(f"Refusing to write into the repository: {target}")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--model-root",
        default=os.environ.get("EUROMOD_MODEL_ROOT", DEFAULT_MODEL_ROOT),
        help="SOUTHMOD A4.0 bundle root (default: $EUROMOD_MODEL_ROOT or %(default)s)",
    )
    parser.add_argument("--seed-dataset", default="et_2022_a2")
    parser.add_argument("--country", default="RW")
    parser.add_argument("--system", default="RW_2025")
    parser.add_argument("--dataset", default="rw_2024_a1")
    parser.add_argument("--max-attempts", type=int, default=20)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true", help="compare a fresh build with the existing file"
    )
    mode.add_argument(
        "--force", action="store_true", help="rebuild and overwrite an existing file"
    )
    args = parser.parse_args(argv)

    model_root = Path(os.path.expanduser(args.model_root)).resolve()
    if not (model_root / "XMLParam").is_dir():
        raise SystemExit(f"Not a EUROMOD model root: {model_root}")
    target = _target_path(model_root, args.dataset)

    if target.exists() and not (args.check or args.force):
        print(f"{target.name} already present ({len(_read_header(target))} columns); nothing to do")
        return 0

    columns = build_header(
        model_root,
        seed_dataset=args.seed_dataset,
        country=args.country,
        system_name=args.system,
        dataset=args.dataset,
        max_attempts=args.max_attempts,
    )
    text = "\t".join(columns) + "\n"

    if args.check:
        if not target.exists():
            print(f"{target.name} is missing; a fresh build has {len(columns)} columns")
            return 1
        if target.read_text(encoding="utf-8") == text:
            print(f"{target.name} matches a fresh build byte for byte ({len(columns)} columns)")
            return 0
        existing = _read_header(target)
        if sorted(existing) == sorted(columns):
            print(f"{target.name} has the same {len(columns)} columns in a different order")
        else:
            print(
                f"{target.name} differs: {len(existing)} existing vs {len(columns)} fresh "
                f"columns ({len(set(existing) - set(columns))} only in the existing file, "
                f"{len(set(columns) - set(existing))} only in the fresh build)"
            )
        return 1

    target.write_text(text, encoding="utf-8")
    print(f"wrote {target} ({len(columns)} columns)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
