"""The dashboard loader's overview fast path must equal per-file loading."""

import shutil
import subprocess
from pathlib import Path

import pytest

DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard"


@pytest.mark.skipif(
    shutil.which("node") is None or shutil.which("npx") is None,
    reason="node toolchain not available",
)
def test_loader_equivalence() -> None:
    subprocess.run(
        [
            "npx",
            "esbuild",
            "src/utils/data.js",
            "--bundle",
            "--format=esm",
            "--outfile=/tmp/data-bundled.mjs",
        ],
        cwd=DASHBOARD,
        check=True,
        capture_output=True,
    )
    proc = subprocess.run(
        ["node", "scripts/test-loader-equivalence.mjs"],
        cwd=DASHBOARD,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "EQUIVALENT: true" in proc.stdout
