"""Suite-wide test fixtures."""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest

from axiom_oracles import pinned_artifacts


@pytest.fixture
def pin_taxsim_stand_in(monkeypatch) -> Callable[..., str]:
    """Pin a stand-in TAXSIM executable as the default profile's only binary.

    The default TAXSIM runner executes only bytes whose SHA-256 and size equal
    a pin profile's binary. Tests that run a shell script in place of
    taxsimtest call ``pin_taxsim_stand_in(path)``: it adds the script's hash
    to a copy of the pin document under a profile named ``stand-in``, makes
    that profile the default for the host platform, and points
    ``$AXIOM_TAXSIM_BINARY_DIR`` at the script's directory. Returns the
    pinned SHA-256. ``law_years`` gives the stand-in a pinned law-year range.
    """
    from axiom_oracles.adapters.taxsim import pins

    original = copy.deepcopy(pins.load_pins())

    def pin(
        binary: Path,
        *,
        system: str | None = None,
        law_years: dict | None = None,
        build: str | None = None,
    ) -> str:
        binary = Path(binary)
        system = pins.normalize_platform(system)
        data = binary.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        doc = copy.deepcopy(original)
        entry = {
            "platform": system,
            "build": build or pins.build_stamp_from_bytes(data) or "stand-in",
            "bytes": len(data),
            "filename": binary.name,
            "sources": [
                {
                    "kind": "url",
                    "url": "https://example.invalid/taxsim-stand-in",
                    "retrieved_on": "2026-11-02",
                }
            ],
        }
        if law_years is not None:
            entry["law_years"] = law_years
        doc["binaries"][sha] = entry
        doc["profiles"]["stand-in"] = {
            "description": "A test stand-in for taxsimtest.",
            "binaries": {system: sha},
            "overrides": [],
        }
        doc["default_profile"] = "stand-in"
        parsed = pins.parse_pin_document(doc)
        monkeypatch.setattr(pins, "load_pins", lambda: doc)
        monkeypatch.setattr(pins, "pin_document", lambda: parsed)
        monkeypatch.setenv(pins.BINARY_DIR_ENV, str(binary.parent.resolve()))
        monkeypatch.delenv(pins.PROFILE_ENV, raising=False)
        pins.clear_hash_cache()
        return sha

    return pin


@pytest.fixture(autouse=True)
def _offline_pinned_artifacts(monkeypatch, tmp_path_factory):
    """Resolve pruned PolicyEngine pins without downloading them.

    Command-building tests reach axiom_oracles.pinned_artifacts.requirement
    for the default oracle pins; the real fetch downloads a 13 MB wheel. Point
    the cache at a per-session directory and return the path the verified
    file would have. tests/test_pinned_artifacts.py exercises the real fetch.
    """
    monkeypatch.setenv(
        pinned_artifacts.CACHE_ENV,
        str(tmp_path_factory.getbasetemp() / "pinned-artifacts"),
    )
    monkeypatch.setattr(pinned_artifacts, "fetch", pinned_artifacts.cache_path)


_FAKE_RULES_ENGINE = r'''#!{python}
"""Test stand-in for axiom-rules-engine: compile and run-compiled only.

``compile`` writes the program in ``spec.json`` beside this file as the
artifact. ``run-compiled`` evaluates each queried output with the rule the
spec gives it: ``ge``/``lt``/``eq`` compare an input with a value, ``any``
and ``all`` combine rules, and a boolean result is a judgment;
``{"copy": input}`` returns the input, ``{"count": relation}`` counts the
relation's tuples and ``{"const": value}`` returns a fixed decimal.  Every request is appended to ``requests.jsonl``.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = json.loads((HERE / "spec.json").read_text())
args = sys.argv[1:]
if args[0] == "compile":
    output = Path(args[args.index("--output") + 1])
    output.write_text(json.dumps({"program": spec["program"]}))
    sys.exit(0)
if args[0] != "run-compiled":
    sys.exit(f"unknown command {args[0]}")
request = json.loads(sys.stdin.read())
with (HERE / "requests.jsonl").open("a") as log:
    log.write(json.dumps(request) + "\n")
inputs = {}
for record in request["dataset"]["inputs"]:
    inputs[record["name"]] = record["value"]["value"]
relations = request["dataset"]["relations"]
def ev(rule):
    if "ge" in rule:
        return inputs[rule["ge"][0]] >= rule["ge"][1]
    if "lt" in rule:
        return inputs[rule["lt"][0]] < rule["lt"][1]
    if "eq" in rule:
        return inputs[rule["eq"][0]] == rule["eq"][1]
    if "any" in rule:
        return any(ev(item) for item in rule["any"])
    if "all" in rule:
        return all(ev(item) for item in rule["all"])
    if "copy" in rule:
        return inputs[rule["copy"]]
    if "count" in rule:
        return sum(1 for r in relations if r["name"] == rule["count"])
    return rule["const"]


results = []
for query in request["queries"]:
    outputs = {}
    for output in query["outputs"]:
        value = ev(spec["rules"][output])
        if isinstance(value, bool):
            outcome = "holds" if value else "not_holds"
            outputs[output] = {"kind": "judgment", "id": output, "outcome": outcome}
        else:
            outputs[output] = {
                "kind": "scalar",
                "id": output,
                "value": {"kind": "decimal", "value": str(value)},
            }
    results.append({"entity_id": query["entity_id"], "outputs": outputs})
print(json.dumps({"results": results}))
'''


@pytest.fixture
def fake_rules_engine(tmp_path):
    """Install a receipted stand-in engine; return a writer for its spec.

    ``install(program, rules)`` writes the spec and returns the executable,
    whose build receipt binds it to commit ``"a" * 40`` so
    :func:`axiom_oracles.engine_identity.engine_receipt` verifies it.
    """
    import json
    import sys

    directory = tmp_path / "fake-engine"
    directory.mkdir()
    binary = directory / "axiom-rules-engine"
    binary.write_text(_FAKE_RULES_ENGINE.replace("{python}", sys.executable, 1))
    binary.chmod(0o755)
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    (directory / "axiom-rules-engine.provenance.json").write_text(
        json.dumps(
            {
                "repository": "TheAxiomFoundation/axiom-rules-engine",
                "commit": "a" * 40,
                "binary_sha256": digest,
                "working_tree": "clean",
            }
        )
    )

    def install(program: dict, rules: dict) -> Path:
        (directory / "spec.json").write_text(
            json.dumps({"program": program, "rules": rules})
        )
        return binary

    install.requests = lambda: [
        json.loads(line)
        for line in (directory / "requests.jsonl").read_text().splitlines()
    ]
    install.digest = digest
    return install
