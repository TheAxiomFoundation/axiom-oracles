"""Replay synthetic relation probes; this does not validate a legal encoding."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent
receipt = json.loads((root / "receipt.json").read_text())
engine = Path(sys.argv[1]).resolve(strict=True)
for case in receipt["receipts"]:
    mode = case["mode"]
    request = (root / f"{mode}-request.json").read_bytes()
    response = (root / f"{mode}-response.json").read_bytes()
    assert hashlib.sha256(request).hexdigest() == case["request_sha256"]
    assert hashlib.sha256(response).hexdigest() == case["response_sha256"]
    result = subprocess.run([str(engine)], input=request, capture_output=True, check=True)
    actual = json.loads(result.stdout)
    assert actual["metadata"]["actual_mode"] == mode
    assert len(actual["results"]) == case["candidate_count"]
    for candidate in actual["results"]:
        for name, value in receipt["expected"][candidate["entity_id"]].items():
            assert int(candidate["outputs"][name]["value"]["value"]) == value
missing = receipt["missing_input_case"]
request = (root / "missing-payment-request.json").read_bytes()
assert hashlib.sha256(request).hexdigest() == missing["request_sha256"]
response = (root / "missing-payment-response.txt").read_bytes()
assert hashlib.sha256(response).hexdigest() == missing["response_sha256"]
result = subprocess.run([str(engine)], input=request, capture_output=True)
assert result.returncode == missing["exit_code"]
assert missing["expected_error"] in result.stderr.decode()
print(json.dumps({
    "comparison_assertions_passed": 28,
    "missing_payment_fails": True,
    "executed_binary_sha256": hashlib.sha256(engine.read_bytes()).hexdigest(),
    "legal_encoding_claim": False,
}, indent=2))
