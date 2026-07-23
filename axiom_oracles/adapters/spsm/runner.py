from __future__ import annotations

import os
import subprocess
from pathlib import Path

# The licence's mandatory publication notice (SPSD/M Licence Agreement
# s.4.1). Every committed artifact presenting SPSD/M-derived results must
# carry it; report builders attach it via `attribution_provenance()`.
SPSM_ATTRIBUTION_NOTICE = (
    "This analysis is based on Statistics Canada's Social Policy "
    "Simulation Database and Model. The assumptions and calculations "
    "underlying the simulation results were prepared by the Axiom "
    "Foundation and the responsibility for the use and interpretation of "
    "these data is entirely that of the author(s)."
)

SPSM_HOME_ENV = "SPSM_HOME"
SPSM_WINE_ENV = "SPSM_WINE"

_DEFAULT_WINE_CANDIDATES = (
    "/Applications/Wine Stable.app/Contents/Resources/wine/bin/wine",
    "/Applications/Wine Crossover.app/Contents/Resources/wine/bin/wine",
)


def spsm_install_root() -> Path | None:
    """Locate the licensed SPSD/M installation, if present on this machine.

    The Package is licensed per-operator and never ships with this repo;
    ``SPSM_HOME`` names the installed tree (a Windows-layout directory,
    typically ``.../drive_c/SPSM`` inside a Wine prefix).
    """

    env = os.environ.get(SPSM_HOME_ENV)
    if env:
        path = Path(env).expanduser()
        return path if path.is_dir() else None
    default = Path.home() / ".wine" / "drive_c" / "SPSM"
    return default if default.is_dir() else None


def _wine_binary() -> str:
    env = os.environ.get(SPSM_WINE_ENV)
    if env:
        return env
    for candidate in _DEFAULT_WINE_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return "wine"


def attribution_provenance() -> dict:
    """Provenance block for reports built from SPSD/M results."""

    return {
        "oracle": "spsm",
        "attribution": SPSM_ATTRIBUTION_NOTICE,
        "licence": "SPSD/M Licence Agreement v34; no Package contents are "
        "redistributed with this repository (s.3.1).",
    }


class SpsmRunner:
    """Batch driver for the SPSM model executable under Wine.

    SPSD/M is a database-driven microsimulation: a run is parameterized by
    a control-parameter file and executes over the licensed synthetic
    database, not over injected per-case inputs. The oracle lane therefore
    runs SPSM in batch over (subsets of) its database and compares
    variable extracts against the axiom leg evaluated on households
    projected from the same records — the SPSD database plays the role
    Enhanced CPS plays for the US lanes.

    This runner intentionally does NOT implement the generic
    ``EngineAdapter.run_cases`` case-projection contract yet; driving SPSM
    from synthetic single cases requires the model's database-creation
    tooling and is a later iteration. See docs/spsdm-oracle-design.md.
    """

    name = "spsm"

    def __init__(
        self,
        *,
        install_root: Path | None = None,
        wine_binary: str | None = None,
        timeout: float = 3600.0,
    ) -> None:
        self.install_root = install_root or spsm_install_root()
        self.wine_binary = wine_binary or _wine_binary()
        self.timeout = timeout

    def require_install(self) -> Path:
        if self.install_root is None:
            raise RuntimeError(
                "No SPSD/M installation found. Install the licensed Package "
                f"and point {SPSM_HOME_ENV} at it (the Package is never "
                "vendored with this repository; see "
                "axiom_oracles/adapters/spsm/spsm_pins.json)."
            )
        return self.install_root

    def model_executable(self) -> Path:
        root = self.require_install()
        for name in ("spsm.exe", "SPSM.exe", "bin/spsm.exe"):
            candidate = root / name
            if candidate.exists():
                return candidate
        raise RuntimeError(
            f"SPSD/M install at {root} has no spsm.exe; expected the "
            "standard model executable from the v34 installer."
        )

    def run_control_file(
        self,
        control_file: Path,
        *,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess:
        """Run one SPSM batch simulation from a control-parameter file."""

        executable = self.model_executable()
        command = [self.wine_binary, str(executable), str(control_file)]
        return subprocess.run(
            command,
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=False,
        )
