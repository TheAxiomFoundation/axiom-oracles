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

The model is loaded once per subprocess but **each household runs through
its own engine run**. EUROMOD-platform models are not row-independent
across households: policy spines seed pseudo-random streams and consume
one draw per household *in dataset order* (e.g. Belgium's ``random_be``
``RandSeed seed=1`` feeds the ``bed_be`` non-take-up correction, UKMOD's
``random_uk`` feeds the Universal Credit take-up gate), so in a shared
run a household's outputs depend on its batch position — every position
after the first can silently zero a benefit. Running one household per
engine run gives every household the draws of a solo run, making results
independent of batch composition by construction. A household whose run
raises is reported in ``household_errors`` without poisoning the rest of
the batch; model-load failures still fail the whole job.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
import sys
import tempfile
from pathlib import Path


def _fail(path: Path, message: str) -> None:
    path.write_text(json.dumps({"error": message}), encoding="utf-8")
    sys.exit(0)


@contextmanager
def _model_root_with_overrides(
    model_root: Path,
    country: str,
    system: str,
    policy_switch_overrides: list[tuple[str, bool]],
    constant_overrides: list[tuple[str, str, str]],
):
    """Yield a model root whose country XML carries the requested overrides.

    Policy switches and constant values are patched into the named system's
    XML block on a symlink overlay of the model directory; the source model
    is never modified. Constant overrides rewrite parameter ``<Value>``s in
    place (DefConst policy constants such as take-up rates) — the euromod
    connector's ``constantsToOverwrite`` kwarg reaches only the uprating
    constants registry and silently ignores DefConst names, so the overlay
    is the mechanism that provably lands (verified live: overriding
    ``$bed_FlTakeUp`` to 0.0 zeroes every bed_s; the connector kwarg left
    them untouched).
    """
    if not policy_switch_overrides and not constant_overrides:
        yield model_root
        return

    with tempfile.TemporaryDirectory(prefix="euromod-model-overlay-") as workdir:
        patched_root = Path(workdir) / "model"
        _build_model_overlay(model_root, patched_root, country)

        country_dir = patched_root / "XMLParam" / "Countries" / country
        xml_path = country_dir / f"{country}.xml"
        source_xml_path = (
            model_root / "XMLParam" / "Countries" / country / f"{country}.xml"
        )
        patched_xml = source_xml_path.read_text(encoding="utf-8-sig")
        if policy_switch_overrides:
            patched_xml = _patch_policy_switches(
                patched_xml,
                system=system,
                overrides=policy_switch_overrides,
            )
        if constant_overrides:
            patched_xml = _patch_constants(
                patched_xml,
                system=system,
                overrides=constant_overrides,
            )
        xml_path.write_text(patched_xml, encoding="utf-8")
        yield patched_root


def _build_model_overlay(model_root: Path, patched_root: Path, country: str) -> None:
    patched_root.mkdir()
    for child in model_root.iterdir():
        if child.name == "XMLParam":
            continue
        _symlink(child, patched_root / child.name)

    xml_source = model_root / "XMLParam"
    xml_target = patched_root / "XMLParam"
    xml_target.mkdir()
    for child in xml_source.iterdir():
        if child.name == "Countries":
            continue
        _symlink(child, xml_target / child.name)

    countries_source = xml_source / "Countries"
    countries_target = xml_target / "Countries"
    countries_target.mkdir()
    for child in countries_source.iterdir():
        if child.name == country:
            continue
        _symlink(child, countries_target / child.name)

    country_source = countries_source / country
    country_target = countries_target / country
    country_target.mkdir()
    for child in country_source.iterdir():
        if child.name == f"{country}.xml":
            continue
        _symlink(child, country_target / child.name)


def _symlink(source: Path, target: Path) -> None:
    os.symlink(source, target, target_is_directory=source.is_dir())


def _patch_policy_switches(
    xml: str,
    *,
    system: str,
    overrides: list[tuple[str, bool]],
) -> str:
    system_name = f"<Name>{system}</Name>"
    system_name_at = xml.find(system_name)
    if system_name_at < 0:
        raise ValueError(f"EUROMOD system {system!r} was not found in country XML.")
    system_start = xml.rfind("<System>", 0, system_name_at)
    system_end = xml.find("</System>", system_name_at)
    if system_start < 0 or system_end < 0:
        raise ValueError(f"EUROMOD system {system!r} has no complete XML block.")
    system_end += len("</System>")

    system_xml = xml[system_start:system_end]
    for policy_name, enabled in overrides:
        system_xml = _patch_policy_switch(
            system_xml,
            policy_name=policy_name,
            enabled=enabled,
            system=system,
        )
    return f"{xml[:system_start]}{system_xml}{xml[system_end:]}"


def _patch_constants(
    xml: str,
    *,
    system: str,
    overrides: list[tuple[str, str, str]],
) -> str:
    system_name = f"<Name>{system}</Name>"
    system_name_at = xml.find(system_name)
    if system_name_at < 0:
        raise ValueError(f"EUROMOD system {system!r} was not found in country XML.")
    system_start = xml.rfind("<System>", 0, system_name_at)
    system_end = xml.find("</System>", system_name_at)
    if system_start < 0 or system_end < 0:
        raise ValueError(f"EUROMOD system {system!r} has no complete XML block.")
    system_end += len("</System>")

    system_xml = xml[system_start:system_end]
    for name, group, value in overrides:
        system_xml = _patch_constant(
            system_xml,
            name=name,
            group=group,
            value=value,
            system=system,
        )
    return f"{xml[:system_start]}{system_xml}{xml[system_end:]}"


def _patch_constant(
    system_xml: str,
    *,
    name: str,
    group: str,
    value: str,
    system: str,
) -> str:
    """Rewrite every ``<Parameter>`` named ``name`` to carry ``value``.

    Matches parameter definitions (e.g. DefConst constants); when ``group``
    is non-empty only parameters carrying that ``<Group>`` are patched.
    Raises if nothing matches so a misspelled constant cannot silently
    leave the model unchanged.
    """
    marker = f"<Name>{name}</Name>"
    patched = 0
    search_from = 0
    while True:
        name_at = system_xml.find(marker, search_from)
        if name_at < 0:
            break
        search_from = name_at + len(marker)
        parameter_start = system_xml.rfind("<Parameter>", 0, name_at)
        parameter_end = system_xml.find("</Parameter>", name_at)
        if parameter_start < 0 or parameter_end < 0:
            continue
        # The name must belong to this parameter, not a function or policy
        # further up the block.
        function_start = system_xml.rfind("<Function>", 0, name_at)
        if function_start > parameter_start:
            continue
        parameter_end += len("</Parameter>")
        parameter_xml = system_xml[parameter_start:parameter_end]
        if group and f"<Group>{group}</Group>" not in parameter_xml:
            continue
        value_start = parameter_xml.find("<Value><![CDATA[")
        value_end = parameter_xml.find("]]></Value>", value_start)
        if value_start < 0 or value_end < 0:
            continue
        value_start += len("<Value><![CDATA[")
        patched_parameter = (
            f"{parameter_xml[:value_start]}{value}{parameter_xml[value_end:]}"
        )
        system_xml = (
            f"{system_xml[:parameter_start]}{patched_parameter}"
            f"{system_xml[parameter_end:]}"
        )
        search_from += len(patched_parameter) - len(parameter_xml)
        patched += 1
    if not patched:
        raise ValueError(
            f"EUROMOD constant {name!r}"
            + (f" (group {group!r})" if group else "")
            + f" was not found in system {system!r}."
        )
    return system_xml


def _patch_policy_switch(
    system_xml: str,
    *,
    policy_name: str,
    enabled: bool,
    system: str,
) -> str:
    name_marker = f"<Name>{policy_name}</Name>"
    name_at = system_xml.find(name_marker)
    if name_at < 0:
        raise ValueError(
            f"EUROMOD policy {policy_name!r} was not found in system {system!r}."
        )
    policy_start = system_xml.rfind("<Policy>", 0, name_at)
    policy_end = system_xml.find("</Policy>", name_at)
    if policy_start < 0 or policy_end < 0:
        raise ValueError(
            f"EUROMOD policy {policy_name!r} has no complete XML block."
        )
    policy_end += len("</Policy>")

    policy_xml = system_xml[policy_start:policy_end]
    switch_start = policy_xml.find("<Switch>", policy_xml.find(name_marker))
    function_start = policy_xml.find("<Function>")
    if switch_start < 0 or (function_start >= 0 and switch_start > function_start):
        raise ValueError(
            f"EUROMOD policy {policy_name!r} has no policy-level Switch element."
        )
    switch_end = policy_xml.find("</Switch>", switch_start)
    if switch_end < 0:
        raise ValueError(
            f"EUROMOD policy {policy_name!r} has an incomplete Switch element."
        )
    switch_end += len("</Switch>")

    switch_value = "on" if enabled else "off"
    patched_policy = (
        f"{policy_xml[:switch_start]}<Switch>{switch_value}</Switch>"
        f"{policy_xml[switch_end:]}"
    )
    return f"{system_xml[:policy_start]}{patched_policy}{system_xml[policy_end:]}"


def _rows_by_household(rows: list) -> dict:
    """Group input rows by ``idhh``, preserving first-appearance order.

    Each group becomes its own engine run so no household's outputs can
    depend on which other households share the job (see module docstring).
    """
    groups: dict = {}
    for row in rows:
        groups.setdefault(int(row["idhh"]), []).append(row)
    return groups


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
    households = _rows_by_household(job["rows"])

    requested = job.get("outputs") or []
    columns = None
    missing: list = []
    idhh: list = []
    values: dict = {}
    household_errors: dict = {}
    try:
        switches = [
            (str(name), bool(enabled)) for name, enabled in job.get("switches", [])
        ]
        policy_switch_overrides = [
            (str(name), bool(enabled))
            for name, enabled in job.get("policy_switch_overrides", [])
        ]
        constant_overrides = [
            (str(name), str(group), str(value))
            for name, group, value in job.get("constant_overrides", [])
        ]
        with _model_root_with_overrides(
            model_root,
            country=str(job["country"]),
            system=str(job["system"]),
            policy_switch_overrides=policy_switch_overrides,
            constant_overrides=constant_overrides,
        ) as run_model_root:
            model = Model(str(run_model_root))
            country = [c for c in model.countries if c.name == job["country"]][0]
            system = [s for s in country.systems if s.name == job["system"]][0]
            for household, household_rows in households.items():
                frame_rows = []
                for row in household_rows:
                    filled = dict(template)
                    for key, value in row.items():
                        if key in filled:
                            filled[key] = value
                    frame_rows.append(filled)
                frame = pd.DataFrame(frame_rows, columns=header)
                try:
                    output = system.run(
                        frame, job["dataset"], switches=switches
                    ).outputs[0]
                except Exception as error:  # noqa: BLE001 - isolate the household
                    household_errors[str(household)] = (
                        f"{type(error).__name__}: {error}"
                    )
                    continue
                if columns is None:
                    missing = [name for name in requested if name not in output.columns]
                    columns = [name for name in requested if name in output.columns]
                    values = {name: [] for name in columns}
                idhh.extend(int(value) for value in output["idhh"].tolist())
                for name in columns:
                    values[name].extend(output[name].tolist())
    except Exception as error:  # noqa: BLE001 - report, never crash silently
        _fail(result_path, f"{type(error).__name__}: {error}")
        return

    if households and columns is None and household_errors:
        # Every household failed; a shared cause (bad dataset, broken model)
        # reads better as one job-level error than N copies of it.
        _fail(result_path, next(iter(household_errors.values())))
        return

    payload = {
        "columns": columns or [],
        "missing": missing,
        "idhh": idhh,
        "values": values,
        "household_errors": household_errors,
    }
    result_path.write_text(json.dumps(payload), encoding="utf-8")


if __name__ == "__main__":
    main()
