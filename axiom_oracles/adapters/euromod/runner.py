"""Adapter for EUROMOD-platform models (EUROMOD, UKMOD) as oracles.

One adapter serves every model built on the EUROMOD software platform: the
JRC's EUROMOD release (Belgium and the other member states) and CeMPA's
UKMOD, both of which ship openly downloadable policy XMLs and demo input
data — per-case oracle validation needs no licensed microdata.

The engine executes through the ``euromod`` connector in a subprocess (see
``_runner.py`` for why), pointed at by ``EUROMOD_PYTHON``; the model root
is a plain directory (``UKMOD_PUBLIC_B2026.03``,
``EUROMOD_RELEASES_J2.0+``). Monetary conventions: case facts are annual;
demo datasets are monthly, so inputs divide by 12 on projection and
monthly outputs multiply by 12 on the way back (``annualize_outputs``).
Dataset uprating means the engine may compute on uprated income — read the
engine's own post-uprating input back (e.g. ``yem``) when a comparison
must bridge on identical gross amounts.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

from axiom_oracles.comparison.mappings import mappings_by_concept
from axiom_oracles.core.case import Case
from axiom_oracles.core.engine import EngineAdapter
from axiom_oracles.core.results import EngineResult

from .projection import euromod_input_rows

SubprocessRun = Callable[..., "subprocess.CompletedProcess[Any]"]

#: Outputs returned when a comparison does not name variables explicitly:
#: simulated income tax, employee social contributions, the standard
#: income lists, and the engine's post-uprating employment income.
DEFAULT_OUTPUTS: tuple[str, ...] = (
    "tin_s",
    "tscee_s",
    "tscee_net_s",
    "ils_tax",
    "ils_ben",
    "ils_dispy",
    "yem",
)

DERIVED_OUTPUTS: dict[str, tuple[str, ...]] = {
    "tscee_net_s": ("tscee_s", "tsceerd_s"),
}

# Most EUROMOD monetary outputs are monthly and need annualization for Axiom
# concepts. Belgium property-tax outputs are already annual-law amounts in
# BE_2025: the model applies annual cadastral-income tests (for example
# ``khooo<=745#y``), and the raw ``tprhm_s`` value is the annual levy.
NON_ANNUALIZED_OUTPUTS: frozenset[str] = frozenset(
    {
        "khooo_s",
        "tprhm_s",
        "tprhmtr_s",
    }
)

SwitchSetting = tuple[str, bool]
PolicySwitchOverride = tuple[str, bool]


class EuromodPlatformRunner(EngineAdapter):
    """Run concept-keyed cases through a EUROMOD-platform model.

    Args:
        model_root: Model directory (contains ``XMLParam`` and ``Input``).
        country: Country name inside the model (``"UK"`` in UKMOD B2026.03,
            ``"BE"`` in EUROMOD releases).
        system: Policy system to simulate (e.g. ``"UK_2025"``, ``"BE_2025"``).
        dataset: Dataset *configuration* the rows are interpreted under
            (default ``"training_data"`` for UKMOD; EUROMOD releases name
            theirs ``"<CC>_training_data"``). Some model content is
            conditioned on the dataset name (``Run_Cond IsUsedDatabase``),
            so per-case runs may need a real dataset's configuration name
            even though its licensed file is absent.
        template_dataset: Dataset file whose header supplies the input-row
            schema when it differs from ``dataset`` (e.g. run under the
            real ``BE_2024_c1_2015_03_e2`` configuration while templating
            rows from the bundled ``BE_training_data``).
        country_code: ``dct`` value for schemas that carry one (UKMOD demo
            data uses 15). Ignored by schemas without a ``dct`` column.
        monthly_inputs: Whether the dataset's monetary convention is
            monthly (both bundled demo datasets are).
        annualize_outputs: Multiply monetary outputs by 12 so results match
            the annual Axiom concept convention.
        switches: EUROMOD extension switches to apply for every run, as
            ``("extension_short_name", enabled)`` pairs.
        policy_switch_overrides: Temporary model XML policy switches to apply
            for every run, as ``("policy_name", enabled)`` pairs. This is for
            policies that EUROMOD marks as manually switched off in the system
            XML and cannot be enabled through extension switches.
        python_executable: Interpreter for the EUROMOD execution
            environment; defaults to ``$EUROMOD_PYTHON`` then
            ``sys.executable``.
        dotnet_root: .NET runtime root exported as ``DOTNET_ROOT``;
            defaults to ``$DOTNET_ROOT``.
        timeout: Subprocess timeout in seconds.
    """

    name = "euromod"

    def __init__(
        self,
        *,
        model_root: str | Path,
        country: str,
        system: str,
        dataset: str = "training_data",
        template_dataset: str | None = None,
        country_code: int = 15,
        monthly_inputs: bool = True,
        annualize_outputs: bool = True,
        switches: list[SwitchSetting] | tuple[SwitchSetting, ...] | None = None,
        policy_switch_overrides: (
            list[PolicySwitchOverride] | tuple[PolicySwitchOverride, ...] | None
        ) = None,
        python_executable: str | Path | None = None,
        dotnet_root: str | Path | None = None,
        timeout: float = 900.0,
        subprocess_run: SubprocessRun = subprocess.run,
    ) -> None:
        self.model_root = Path(model_root).expanduser()
        self.country = country
        self.system = system
        self.dataset = dataset
        self.template_dataset = template_dataset
        self.country_code = country_code
        self.monthly_inputs = monthly_inputs
        self.annualize_outputs = annualize_outputs
        self.switches = _normalize_switches(switches)
        self.policy_switch_overrides = _normalize_switches(policy_switch_overrides)
        self.python_executable = str(
            python_executable
            or os.environ.get("EUROMOD_PYTHON")
            or sys.executable
        )
        self.dotnet_root = str(dotnet_root or os.environ.get("DOTNET_ROOT") or "")
        self.timeout = timeout
        self.subprocess_run = subprocess_run

    def run_cases(
        self,
        cases: list[Case],
        variables: list[str] | None = None,
    ) -> list[EngineResult]:
        """Run cases through the model and return per-case results.

        Each case becomes one engine household; per-person monetary outputs
        are summed to the case level (a household's income tax is the sum
        of its members'), and monthly amounts are annualized when
        ``annualize_outputs`` is set.
        """
        outputs = _euromod_outputs_for_variables(variables)
        worker_outputs = _expand_derived_outputs(outputs)
        try:
            switches = _switches_for_cases(cases, self.switches)
            policy_switch_overrides = _policy_switch_overrides_for_cases(
                cases,
                self.policy_switch_overrides,
            )
        except ValueError as error:
            return [
                EngineResult(
                    engine=self.name,
                    household_id=case.case_id,
                    values={},
                    errors=(str(error),),
                )
                for case in cases
            ]

        rows: list[dict[str, Any]] = []
        for index, case in enumerate(cases):
            for row in euromod_input_rows(
                case,
                household_number=index + 1,
                country_code=self.country_code,
                monthly_inputs=self.monthly_inputs,
            ):
                rows.append(row)

        payload = self._execute(
            rows,
            worker_outputs,
            switches,
            policy_switch_overrides,
        )
        if "error" in payload:
            error = (payload["error"],)
            return [
                EngineResult(
                    engine=self.name,
                    household_id=case.case_id,
                    values={},
                    errors=error,
                )
                for case in cases
            ]
        _attach_derived_outputs(payload, outputs)

        by_household: dict[int, dict[str, float]] = {}
        for position, household in enumerate(payload["idhh"]):
            sums = by_household.setdefault(int(household), dict.fromkeys(payload["columns"], 0.0))
            for column in payload["columns"]:
                sums[column] += float(payload["values"][column][position])

        annualization_factor = 12.0 if self.annualize_outputs else 1.0
        missing = tuple(
            f"output {name!r} is not a column of the {self.system} output"
            for name in payload["missing"]
        )
        results = []
        for index, case in enumerate(cases):
            sums = by_household.get(index + 1, {})
            results.append(
                EngineResult(
                    engine=self.name,
                    household_id=case.case_id,
                    values={
                        name: value * _annualization_factor(
                            name,
                            annualization_factor,
                        )
                        for name, value in sums.items()
                    },
                    errors=missing,
                )
            )
        return results

    def _execute(
        self,
        rows: list[dict[str, Any]],
        outputs: list[str],
        switches: tuple[SwitchSetting, ...],
        policy_switch_overrides: tuple[PolicySwitchOverride, ...],
    ) -> dict:
        """Invoke the subprocess worker and return its JSON payload."""
        job = {
            "model_root": str(self.model_root),
            "country": self.country,
            "system": self.system,
            "dataset": self.dataset,
            "template_dataset": self.template_dataset,
            "rows": rows,
            "outputs": outputs,
            "switches": list(switches),
            "policy_switch_overrides": list(policy_switch_overrides),
        }
        worker = Path(__file__).parent / "_runner.py"
        env = dict(os.environ)
        env.setdefault("PYTHONNET_RUNTIME", "coreclr")
        if self.dotnet_root:
            env["DOTNET_ROOT"] = self.dotnet_root
        with tempfile.TemporaryDirectory(prefix="euromod-oracle-") as workdir:
            job_path = Path(workdir) / "job.json"
            result_path = Path(workdir) / "result.json"
            job_path.write_text(json.dumps(job), encoding="utf-8")
            completed = self.subprocess_run(
                [self.python_executable, str(worker), str(job_path), str(result_path)],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=env,
            )
            if not result_path.exists():
                detail = (completed.stderr or completed.stdout or "").strip()
                return {
                    "error": (
                        "EUROMOD worker produced no result "
                        f"(exit {completed.returncode}): {detail[-2000:]}"
                    )
                }
            return json.loads(result_path.read_text(encoding="utf-8"))


def _euromod_outputs_for_variables(variables: list[str] | None) -> list[str]:
    if not variables:
        return list(DEFAULT_OUTPUTS)

    by_concept = mappings_by_concept()
    outputs: list[str] = []
    for variable in variables:
        mapping = by_concept.get(variable)
        target = mapping.target_for_engine("euromod") if mapping is not None else None
        if isinstance(target, list):
            outputs.extend(target)
        elif target:
            outputs.append(target)
        else:
            outputs.append(variable)
    return list(dict.fromkeys(outputs))


def _switches_for_cases(
    cases: list[Case], base_switches: tuple[SwitchSetting, ...]
) -> tuple[SwitchSetting, ...]:
    return _settings_for_cases(
        cases,
        base_switches,
        metadata_key="euromod_switches",
        setting_label="EUROMOD extension switches",
    )


def _policy_switch_overrides_for_cases(
    cases: list[Case],
    base_overrides: tuple[PolicySwitchOverride, ...],
) -> tuple[PolicySwitchOverride, ...]:
    return _settings_for_cases(
        cases,
        base_overrides,
        metadata_key="euromod_policy_switch_overrides",
        setting_label="EUROMOD policy switch overrides",
    )


def _settings_for_cases(
    cases: list[Case],
    base_settings: tuple[SwitchSetting, ...],
    *,
    metadata_key: str,
    setting_label: str,
) -> tuple[SwitchSetting, ...]:
    case_settings = {
        _normalize_switches(case.metadata.get(metadata_key)) for case in cases
    }
    if not case_settings:
        return base_settings
    if len(case_settings) > 1:
        raise ValueError(
            f"Cases in one EUROMOD batch require incompatible {setting_label} "
            f"metadata[{metadata_key!r}]; split the run by switch set."
        )
    return _merge_switches(base_settings, next(iter(case_settings)))


def _merge_switches(
    base_switches: tuple[SwitchSetting, ...],
    case_switches: tuple[SwitchSetting, ...],
) -> tuple[SwitchSetting, ...]:
    merged: dict[str, bool] = {}
    for name, enabled in (*base_switches, *case_switches):
        merged[name] = enabled
    return tuple(merged.items())


def _normalize_switches(value: Any) -> tuple[SwitchSetting, ...]:
    if value is None:
        return ()
    if isinstance(value, dict):
        raw_items = value.items()
    elif isinstance(value, (list, tuple)):
        raw_items = value
    else:
        raise ValueError("EUROMOD switches must be a mapping or a sequence of pairs.")

    switches: list[SwitchSetting] = []
    for item in raw_items:
        try:
            name, enabled = item
        except (TypeError, ValueError) as error:
            raise ValueError(
                "EUROMOD switches must be pairs of extension short name and boolean."
            ) from error
        if not isinstance(name, str) or not name:
            raise ValueError("EUROMOD switch names must be non-empty strings.")
        switches.append((name, _switch_bool(enabled)))
    return tuple(switches)


def _switch_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ValueError("EUROMOD switch values must be boolean or on/off strings.")


def _expand_derived_outputs(outputs: list[str]) -> list[str]:
    expanded: list[str] = []
    for output in outputs:
        components = DERIVED_OUTPUTS.get(output)
        if components is None:
            expanded.append(output)
        else:
            expanded.extend(components)
    return list(dict.fromkeys(expanded))


def _annualization_factor(output: str, default_factor: float) -> float:
    if output in NON_ANNUALIZED_OUTPUTS:
        return 1.0
    return default_factor


def _attach_derived_outputs(payload: dict[str, Any], outputs: list[str]) -> None:
    columns = list(payload.get("columns", []))
    values = payload.get("values", {})
    missing = list(payload.get("missing", []))
    for output in outputs:
        if output != "tscee_net_s":
            continue
        if output in columns:
            continue
        if "tscee_s" not in values or "tsceerd_s" not in values:
            if output not in missing:
                missing.append(output)
            continue
        values[output] = [
            float(gross) - float(reduction)
            for gross, reduction in zip(values["tscee_s"], values["tsceerd_s"], strict=True)
        ]
        columns.append(output)
    payload["columns"] = columns
    payload["values"] = values
    payload["missing"] = missing
