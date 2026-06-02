from __future__ import annotations

import os
import sys
from pathlib import Path


PE_ORACLE_PINS = (
    "policyengine==4.11.0",
    "policyengine-us==1.700.0",
    "policyengine-core==3.26.11",
)


def ensure_pinned_policyengine_env(script_path: Path, repo_root: Path) -> None:
    """Re-run debug helpers with the same PE stack as production comparisons."""

    if os.environ.get("AXIOM_ORACLES_DEBUG_PINNED_PE") == "1":
        return
    if os.environ.get("AXIOM_ORACLES_DEBUG_SKIP_PINNED_PE") == "1":
        return

    env = dict(os.environ)
    env["AXIOM_ORACLES_DEBUG_PINNED_PE"] = "1"
    cmd = [
        "uv",
        "run",
        "--python",
        "3.14",
        "--no-project",
        "--with-editable",
        str(repo_root),
    ]
    for pin in PE_ORACLE_PINS:
        cmd.extend(["--with", pin])
    cmd.extend(["python", str(script_path), *sys.argv[1:]])
    os.execvpe("uv", cmd, env)
