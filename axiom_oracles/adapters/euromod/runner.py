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
    "ils_tax",
    "ils_ben",
    "ils_dispy",
    "yem",
)


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
        outputs = list(variables) if variables else list(DEFAULT_OUTPUTS)
        rows: list[dict[str, Any]] = []
        for index, case in enumerate(cases):
            for row in euromod_input_rows(
                case,
                household_number=index + 1,
                country_code=self.country_code,
                monthly_inputs=self.monthly_inputs,
            ):
                rows.append(row)

        payload = self._execute(rows, outputs)
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

        by_household: dict[int, dict[str, float]] = {}
        for position, household in enumerate(payload["idhh"]):
            sums = by_household.setdefault(int(household), dict.fromkeys(payload["columns"], 0.0))
            for column in payload["columns"]:
                sums[column] += float(payload["values"][column][position])

        factor = 12.0 if self.annualize_outputs else 1.0
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
                    values={name: value * factor for name, value in sums.items()},
                    errors=missing,
                )
            )
        return results

    def _execute(self, rows: list[dict[str, Any]], outputs: list[str]) -> dict:
        """Invoke the subprocess worker and return its JSON payload."""
        job = {
            "model_root": str(self.model_root),
            "country": self.country,
            "system": self.system,
            "dataset": self.dataset,
            "template_dataset": self.template_dataset,
            "rows": rows,
            "outputs": outputs,
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
