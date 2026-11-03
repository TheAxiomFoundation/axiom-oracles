from __future__ import annotations

import os
import sys
from pathlib import Path


PE_ORACLE_PINS = (
    "policyengine==4.11.0",
    "policyengine-us==1.700.0",
    "policyengine-core==3.26.11",
    # Unpinned, spm-calculator resolves 1.0.x, which removed the
    # spm_calculator.geoadj module PolicyEngine-US imports (see
    # _PE_US_COMPANION_PINS in scripts/run_comparison.py).
    "spm-calculator==0.3.1",
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
        "--isolated",
        "--with-editable",
        str(repo_root),
    ]
    # A pin PyPI's index no longer lists installs from its verified
    # hashed-URL file (axiom_oracles/pinned_artifacts.py), as in
    # scripts/run_comparison.py.
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from axiom_oracles import pinned_artifacts

    cmd.extend(pinned_artifacts.with_args(PE_ORACLE_PINS))
    cmd.extend(["python", str(script_path), *sys.argv[1:]])
    os.execvpe("uv", cmd, env)
