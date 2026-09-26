"""Run a verified TAXSIM executable and surface failures with an exit status.

policyengine-taxsim's ``TaxsimRunner._execute_taxsim`` pipes the input file
through the executable with ``shell=True`` and, on a non-zero exit, raises a
bare ``Exception("TAXSIM execution failed: <stderr>")``: the exit status is
lost, and through a shell a signal-killed executable shows up as 128+n,
indistinguishable from an ordinary exit status above 128.

:func:`pinned_taxsim_runner_class` subclasses that runner (keeping its input
formatting and output parsing) and replaces only the execution step: the
input bytes are written to the executable's stdin pipe and stdout goes to the
output file, as in the original pipeline, but without a shell, so
``returncode`` is the executable's own status (negative = killed by that
signal). A failure raises :class:`TaxsimExecutionError`, which carries the
return code, stderr, and the executable path.
"""

from __future__ import annotations

import os
import platform
import signal
import subprocess
from pathlib import Path
from typing import Any

STDERR_TAIL_CHARS = 2000


class TaxsimExecutionError(RuntimeError):
    """The TAXSIM executable exited non-zero (or was killed by a signal)."""

    def __init__(
        self,
        *,
        returncode: int,
        stderr: str = "",
        binary: Path | str | None = None,
        via_shell: bool = False,
    ) -> None:
        self.returncode = int(returncode)
        self.stderr = stderr or ""
        self.binary = Path(binary) if binary is not None else None
        self.via_shell = via_shell
        super().__init__(
            f"TAXSIM execution failed ({self.signature}): {self.stderr_tail}"
        )

    @property
    def signature(self) -> str:
        return crash_signature(self.returncode, via_shell=self.via_shell)

    @property
    def stderr_tail(self) -> str:
        return self.stderr[-STDERR_TAIL_CHARS:]


def crash_signature(returncode: int, *, via_shell: bool = False) -> str:
    """Name a failed exit: ``SIGFPE`` for signal deaths, else ``rc=<n>``.

    A negative return code is a signal number (Python's subprocess
    convention). 128+n is read as signal n only when the status came through
    a shell, since a process can also exit normally with a status above 128.
    """
    number = None
    if returncode < 0:
        number = -returncode
    elif via_shell and 128 < returncode < 128 + 65:
        number = returncode - 128
    if number is not None:
        try:
            return signal.Signals(number).name
        except ValueError:
            return f"SIG{number}"
    return f"rc={returncode}"


def execute_taxsim_binary(
    binary: Path, input_file: Path, output_file: Path
) -> subprocess.CompletedProcess[bytes]:
    """Pipe ``input_file`` through ``binary`` into ``output_file`` (no shell)."""
    system = platform.system().lower()
    env = os.environ.copy()
    if system == "darwin":
        # Same PATH prefix policyengine-taxsim's runner applies on macOS.
        current_path = env.get("PATH", "")
        for homebrew_path in reversed(["/opt/homebrew/bin", "/usr/local/bin"]):
            if homebrew_path not in current_path:
                current_path = f"{homebrew_path}:{current_path}"
        env["PATH"] = current_path
    creationflags = 0
    if system == "windows":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    if not Path(binary).is_absolute():
        # subprocess resolves a bare name on PATH, which would run bytes the
        # pin check never saw. Only verified absolute paths may execute.
        raise ValueError(f"refusing to execute non-absolute TAXSIM path {binary!s}")
    payload = Path(input_file).read_bytes()
    with Path(output_file).open("wb") as stdout:
        process = subprocess.run(
            [str(binary)],
            input=payload,
            stdout=stdout,
            stderr=subprocess.PIPE,
            env=env,
            creationflags=creationflags,
            check=False,
        )
    if process.returncode != 0:
        raise TaxsimExecutionError(
            returncode=process.returncode,
            stderr=process.stderr.decode("utf-8", errors="replace"),
            binary=binary,
        )
    return process


_PINNED_RUNNER_CLASS: type | None = None


def pinned_taxsim_runner_class() -> type:
    """policyengine-taxsim's TaxsimRunner with the exit-status-preserving step."""
    global _PINNED_RUNNER_CLASS
    if _PINNED_RUNNER_CLASS is None:
        from policyengine_taxsim.runners.taxsim_runner import TaxsimRunner

        class PinnedTaxsimRunner(TaxsimRunner):
            """TaxsimRunner whose execution raises TaxsimExecutionError."""

            def _execute_taxsim(self, input_file: str, output_file: str) -> Any:
                return execute_taxsim_binary(
                    Path(self.taxsim_path), Path(input_file), Path(output_file)
                )

        _PINNED_RUNNER_CLASS = PinnedTaxsimRunner
    return _PINNED_RUNNER_CLASS
