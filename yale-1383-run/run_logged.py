#!/usr/bin/env python3
"""Record a measurement command without dumping unrelated environment values."""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import time

p = argparse.ArgumentParser()
p.add_argument("--label", required=True)
p.add_argument("--cwd", required=True)
p.add_argument("--env", action="append", default=[])
p.add_argument("command", nargs=argparse.REMAINDER)
a = p.parse_args()
command = a.command[1:] if a.command[:1] == ["--"] else a.command
root = Path(__file__).resolve().parent
logs = root / "logs"
logs.mkdir(exist_ok=True)
overrides = dict(x.split("=", 1) for x in a.env)
receipt = {
    "command": command,
    "cwd": str(Path(a.cwd).resolve()),
    "environment_overrides": overrides,
    "started_at": datetime.datetime.now(datetime.UTC).isoformat(),
    "stdout": str(logs / (a.label + ".stdout")),
    "stderr": str(logs / (a.label + ".stderr")),
}
started = time.monotonic()
with open(receipt["stdout"], "w") as out, open(receipt["stderr"], "w") as err:
    result = subprocess.run(command, cwd=a.cwd, env={**os.environ, **overrides}, stdout=out, stderr=err)
receipt.update(returncode=result.returncode, elapsed_seconds=round(time.monotonic() - started, 3),
               finished_at=datetime.datetime.now(datetime.UTC).isoformat())
(logs / (a.label + ".json")).write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt, indent=2))
raise SystemExit(result.returncode)
