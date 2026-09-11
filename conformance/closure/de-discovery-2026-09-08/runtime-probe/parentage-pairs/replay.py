"""Replay synthetic identifier matching; this is not a legal relationship rule."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).parent
receipt = json.loads((root / "receipt.json").read_text())
for name, expected in receipt["file_sha256"].items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected
for mode in ("explain", "fast"):
    result = subprocess.run(
        [sys.argv[1]], input=(root / f"{mode}-request.json").read_text(),
        capture_output=True, text=True, check=True,
    )
    response = json.loads(result.stdout)
    assert response["metadata"]["actual_mode"] == mode
    actual = {
        row["entity_id"]: row["outputs"]["record_identifiers_match"]["outcome"]
        for row in response["results"]
    }
    assert actual == receipt["expected"], actual
    assert response == json.loads((root / f"{mode}-response.json").read_text())
print("8 candidate-child pair assertions pass in one dataset per mode")
