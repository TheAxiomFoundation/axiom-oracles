"""Expected-failing mutants found by the AUTOGO gate-coverage audit.

The gates under review live on sibling feature branches that are intentionally
read-only for this review.  Load their pinned Git objects in memory so the
mutants prove the reviewed implementations without checking out or copying
those branches into this worktree.

Every test is a strict xfail: an XPASS means the corresponding gate hole was
closed and the marker should be removed when this review is integrated with the
gate branches.
"""

from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
CUMULATIVE_GATE_REF = "a312ace12615593ef2076d95a41e7c68d18c9412"
CLOSURE_GATE_REF = "9414bc89781e0ea12ebbc6c9b2d1e2f7c709735b"


def _git_text(ref: str, path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        pytest.fail(f"cannot read reviewed gate object {ref}:{path}: {result.stderr}")
    return result.stdout


def _exec_module(ref: str, path: str, name: str) -> ModuleType:
    module = ModuleType(name)
    module.__file__ = str(REPO_ROOT / path)
    module.__package__ = name.rpartition(".")[0]
    sys.modules[name] = module
    source = _git_text(ref, path)
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


@lru_cache
def _evidence() -> ModuleType:
    # certify.py imports this exact module name.
    return _exec_module(
        CUMULATIVE_GATE_REF,
        "axiom_oracles/evidence.py",
        "axiom_oracles.evidence",
    )


@lru_cache
def _certify() -> ModuleType:
    _evidence()
    return _exec_module(
        CUMULATIVE_GATE_REF,
        "scripts/certify.py",
        "_gate_review_certify",
    )


@lru_cache
def _apply_dispositions() -> ModuleType:
    return _exec_module(
        CUMULATIVE_GATE_REF,
        "scripts/apply_dispositions.py",
        "_gate_review_apply_dispositions",
    )


@lru_cache
def _manifests() -> ModuleType:
    return _exec_module(
        CUMULATIVE_GATE_REF,
        "scripts/validate_bridge_manifests.py",
        "_gate_review_validate_bridge_manifests",
    )


@lru_cache
def _closure() -> ModuleType:
    return _exec_module(
        CLOSURE_GATE_REF,
        "scripts/closure_universe.py",
        "_gate_review_closure_universe",
    )


@lru_cache
def _merge_closure() -> ModuleType:
    return _exec_module(
        CLOSURE_GATE_REF,
        "scripts/merge_closure_classifications.py",
        "_gate_review_merge_closure",
    )


def _stub_leg(entry: dict, *, clean: bool, unexplained: int = 0, axiom: int = 0):
    return (
        {
            "suite": entry["suite"],
            "oracle_type": entry["oracle_type"],
            "oracle": entry.get("oracle", "synthetic"),
            "comparisons": 1,
            "matches": 1 if clean else 0,
            "mismatches": 0 if clean else 1,
            "unexplained": unexplained,
            "axiom_attributed_open": axiom,
            "report_defects": [],
            "clean": clean,
        },
        [],
        [],
    )


def _patch_certificate_inputs(monkeypatch: pytest.MonkeyPatch, certify: ModuleType):
    monkeypatch.setattr(certify, "_load", lambda _path: {"suites": {}})
    monkeypatch.setattr(certify, "sha256_of", lambda _path: "0" * 64)
    monkeypatch.setattr(
        certify,
        "_exercise_block",
        lambda _suites, _census, _defects: ({}, True),
    )


@pytest.mark.xfail(
    strict=True,
    reason="GCR-01: a false slim count bypasses disposition replay",
)
def test_forged_stored_mismatch_count_cannot_skip_disposition_replay():
    """Finding GCR-01: the full disposition/evidence/certificate composition leaks."""

    gate = _apply_dispositions()
    mutant = {
        "schema_version": "axiom.comparison_report.v2.1",
        "suite": "victim",
        "summary": {
            "comparison_count": 1,
            "match_count": 0,
            "mismatch_count": 1,
            # Exact exploit: one row is present, but this lie makes replay skip.
            "stored_mismatch_example_count": 0,
            "dispositioned": {
                "dispositions_file": "dispositions/victim.yaml",
                "unexplained_count": 0,
                "counts": {"upstream_engine_gap": 1},
            },
        },
        "mismatches": [
            {
                "case_id": "live-case",
                "concept": "program#benefit",
                "left": 1,
                "right": 2,
                "disposition": {
                    "id": "forged-not-in-cited-file",
                    "disposition": "upstream_engine_gap",
                },
            }
        ],
    }

    assert gate._is_premerged_slim_report(mutant) is False


@pytest.mark.xfail(
    strict=True,
    reason="GCR-02: status strings activate a four-premise certificate",
)
def test_certified_requires_a_real_producer_and_provision_root(
    monkeypatch: pytest.MonkeyPatch,
):
    """Finding GCR-02: mutable registry text is treated as computed evidence."""

    certify = _certify()
    _patch_certificate_inputs(monkeypatch, certify)
    monkeypatch.setattr(
        certify,
        "_suite_verdict",
        lambda entry: _stub_leg(entry, clean=True),
    )
    spec = {
        "period": "2026-01",
        "suites": [
            {
                "suite": "clean-reference",
                "oracle_type": "reference",
                "oracle": "synthetic",
                "report": "does-not-matter.json",
            }
        ],
        # There is no provision_rooted premise and neither claimed producer exists.
        "attested": {
            "closed": {
                "status": "computed",
                "value": True,
                "source": "does-not-exist",
            },
            "executable": {
                "status": "computed",
                "value": True,
                "source": "does-not-exist",
            },
        },
    }

    certificate = certify.build_certificate("unrooted/node", spec)
    assert certificate["certified"]["state"] != "yes"


@pytest.mark.xfail(
    strict=True,
    reason="GCR-03: an unknown oracle type drops a dirty suite",
)
def test_unknown_oracle_type_is_a_certificate_defect(
    monkeypatch: pytest.MonkeyPatch,
):
    """Finding GCR-03: `referance` lands in neither verdict leg nor blockers."""

    certify = _certify()
    _patch_certificate_inputs(monkeypatch, certify)

    def verdict(entry: dict):
        if entry["oracle_type"] == "reference":
            return _stub_leg(entry, clean=True)
        return _stub_leg(entry, clean=False, unexplained=1)

    monkeypatch.setattr(certify, "_suite_verdict", verdict)
    spec = {
        "period": "2026-01",
        "suites": [
            {
                "suite": "clean",
                "oracle_type": "reference",
                "oracle": "synthetic",
                "report": "clean.json",
            },
            {
                "suite": "dirty-but-dropped",
                "oracle_type": "referance",
                "oracle": "synthetic",
                "report": "dirty.json",
            },
        ],
    }

    certificate = certify.build_certificate("program", spec)
    assert certificate["verdicts"]["conformant"]["value"] is False
    assert any("oracle_type" in blocker for blocker in certificate["blockers"])


@pytest.mark.xfail(
    strict=True,
    reason="GCR-04: a reality leg's admitted Axiom gap does not block",
)
def test_reality_leg_axiom_encoding_gap_is_an_open_defect(
    monkeypatch: pytest.MonkeyPatch,
):
    """Finding GCR-04: nonblocking leads must not include admitted Axiom defects."""

    certify = _certify()
    _patch_certificate_inputs(monkeypatch, certify)

    def verdict(entry: dict):
        if entry["oracle_type"] == "reference":
            return _stub_leg(entry, clean=True)
        return _stub_leg(entry, clean=False, axiom=1)

    monkeypatch.setattr(certify, "_suite_verdict", verdict)
    spec = {
        "period": "2026-01",
        "suites": [
            {
                "suite": "clean-reference",
                "oracle_type": "reference",
                "oracle": "synthetic",
                "report": "clean.json",
            },
            {
                "suite": "known-axiom-gap",
                "oracle_type": "reality",
                "oracle": "administrative outcomes",
                "report": "reality.json",
            },
        ],
    }

    certificate = certify.build_certificate("program", spec)
    assert certificate["blockers"]


@pytest.mark.xfail(
    strict=True,
    reason="GCR-05: conformance is not pinned to an execution/dependency tuple",
)
def test_clean_reference_leg_requires_execution_and_dependency_provenance(
    monkeypatch: pytest.MonkeyPatch,
):
    """Finding GCR-05: a fully bound report with no provenance is clean."""

    certify = _certify()
    execution_evidence = SimpleNamespace(
        defects=(),
        reconciliation="full",
        valid=True,
        binding="bound",
        report_sha256="1" * 64,
        suite="victim",
        chunk_case_count=1,
        case_count=1,
    )
    monkeypatch.setattr(
        certify,
        "validate_suite_evidence",
        lambda _path: execution_evidence,
    )
    monkeypatch.setattr(
        certify,
        "_load",
        lambda _path: {
            "suite": "victim",
            # Deliberately no provenance, engines, RuleSpec pins, or artifact id.
            "summary": {
                "comparison_count": 1,
                "match_count": 1,
                "mismatch_count": 0,
            },
            "cases": [],
            "mismatches": [],
        },
    )

    leg, _evidence_rows, defects = certify._suite_verdict(
        {
            "suite": "victim",
            "oracle_type": "reference",
            "oracle": "declared oracle 9.9",
            "report": "missing-provenance.json",
        }
    )
    assert leg["clean"] is False
    assert any("provenance" in defect for defect in defects)


@pytest.mark.xfail(
    strict=True,
    reason="GCR-20: malformed unexplained_count escapes its validation branch",
)
def test_unexplained_count_is_validated_even_when_counts_are_empty(
    monkeypatch: pytest.MonkeyPatch,
):
    """Finding GCR-20: `unexplained_count: one` is ignored on a clean leg."""

    certify = _certify()
    execution_evidence = SimpleNamespace(
        defects=(),
        reconciliation="full",
        valid=True,
        binding="bound",
        report_sha256="1" * 64,
        suite="victim",
        chunk_case_count=1,
        case_count=1,
    )
    monkeypatch.setattr(
        certify,
        "validate_suite_evidence",
        lambda _path: execution_evidence,
    )
    monkeypatch.setattr(
        certify,
        "_load",
        lambda _path: {
            "suite": "victim",
            "summary": {
                "comparison_count": 1,
                "match_count": 1,
                "mismatch_count": 0,
                "dispositioned": {
                    "counts": {},
                    "unexplained_count": "one",
                },
            },
            "cases": [],
            "mismatches": [],
        },
    )

    leg, _evidence_rows, defects = certify._suite_verdict(
        {
            "suite": "victim",
            "oracle_type": "reference",
            "oracle": "synthetic",
            "report": "mutant.json",
        }
    )
    assert leg["clean"] is False
    assert any("unexplained_count" in defect for defect in defects)


@pytest.mark.xfail(
    strict=True,
    reason="GCR-06: all-constant unbound census evidence counts as exercised",
)
def test_exercised_requires_bound_material_variation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Finding GCR-06: one constant field satisfies the exercise predicate."""

    certify = _certify()
    monkeypatch.setattr(certify, "REPO_ROOT", tmp_path)
    report_path = tmp_path / "report.json"
    report_path.write_text("{}\n")
    report_sha = hashlib.sha256(report_path.read_bytes()).hexdigest()
    entry = {
        "suite": "victim",
        "oracle_type": "reference",
        "oracle": "synthetic",
        "report": "report.json",
    }
    row = {
        "cases_scanned": 1,
        "report": "report.json",
        "report_sha256": report_sha,
        "contested_reports": [],
        "evidence_fields": {
            "material_input": {"distinct": 1, "state": "constant"}
        },
        "varied_fields": 0,
        "constant_fields": 1,
        "bridged_through": {},
        "bridge_audited": True,
        "binding": "unbound",
        "reconciliation": "none",
    }

    _rows, complete = certify._exercise_block(
        [entry],
        {"suites": {"victim": row}},
        [],
    )
    assert complete is False


@pytest.mark.xfail(
    strict=True,
    reason="GCR-07: an empty pinned closure denominator is accepted",
)
def test_empty_pinned_closure_denominator_cannot_be_closed(tmp_path: Path):
    """Finding GCR-07: zero rows is valid input and `all([])` closes the root."""

    closure = _closure()
    config = closure.ROOTS[0]
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / config.source_file).write_text("")
    errors: list[str] = []
    rows = closure._load_source_rows(config, data_dir, errors)
    universes = {
        root.root: {
            "provisions": [],
            "ratchet": {"pins_sha256": "0" * 64, "pending_max": 0},
        }
        for root in closure.ROOTS
    }
    summary_errors: list[str] = []
    summary = closure._summary_document(
        universes,
        tree_paths=set(),
        errors=summary_errors,
    )

    assert rows == []
    assert errors or summary_errors or summary["closed"] is False


@pytest.mark.xfail(
    strict=True,
    reason="GCR-08: exclusion truth is accepted as ungrounded prose",
)
def test_substantive_provision_cannot_be_excluded_by_bare_assertion():
    """Finding GCR-08: body is discarded; taxonomy plus `Reviewed.` passes."""

    closure = _closure()
    config = closure.ROOTS[0]
    errors: list[str] = []
    closure._validate_provision_rows(
        [
            {
                "citation": f"{config.citation_root}/eligibility-formula",
                "heading": "Eligibility amount formula",
                "status": "excluded",
                "reason": "no_household_computation",
                "basis": "Reviewed.",
            }
        ],
        config=config,
        label="mutant",
        tree_paths=set(),
        allow_generated_path_drift=False,
        errors=errors,
    )
    assert errors


@pytest.mark.xfail(
    strict=True,
    reason="GCR-09: encoded_by need not bind the module to the provision",
)
def test_corrected_encoded_by_must_bind_module_to_provision():
    """Finding GCR-09: a Colorado provision may cite an unrelated federal file."""

    closure = _closure()
    config = closure.ROOTS[0]
    unrelated = "us/statutes/7/2011.yaml"
    errors: list[str] = []
    closure._validate_provision_rows(
        [
            {
                "citation": f"{config.citation_root}/eligibility-formula",
                "heading": "Eligibility amount formula",
                "status": "encoded",
                "encoded_by": [unrelated],
            }
        ],
        config=config,
        label="mutant",
        tree_paths={unrelated},
        allow_generated_path_drift=False,
        errors=errors,
    )
    assert errors


@pytest.mark.xfail(
    strict=True,
    reason="GCR-10: partial_coverage need not have a joined module",
)
def test_partial_coverage_requires_a_present_joined_deferred_module():
    """Finding GCR-10: any nonempty disclosure text authorizes the allowance."""

    closure = _closure()
    config = closure.ROOTS[0]
    errors: list[str] = []
    closure._validate_provision_rows(
        [
            {
                "citation": f"{config.citation_root}/missing-module",
                "heading": "Substantive computation",
                "status": "pending",
                "partial_coverage": "The joined module defers this output.",
            }
        ],
        config=config,
        label="mutant",
        tree_paths=set(),
        allow_generated_path_drift=False,
        errors=errors,
    )
    assert errors


@pytest.mark.xfail(
    strict=True,
    reason="GCR-18: filename presence is treated as semantic encoding",
)
def test_rulespec_filename_presence_is_not_complete_encoding_evidence():
    """Finding GCR-18: the generated join never reads module content."""

    closure = _closure()
    config = closure.RootConfig(
        root="synthetic",
        source_file="source.jsonl",
        citation_root="us/test",
        module_root="us/tests",
    )
    provisions = closure._merge_provisions(
        config,
        [{"citation": "us/test/substantive", "heading": "Benefit formula"}],
        {"us/tests/substantive.yaml"},
        [],
    )

    # The only supplied fact is a filename; no module bytes or executable output
    # were supplied, so the gate cannot truthfully conclude "encoded".
    assert provisions[0]["status"] == "pending"


@pytest.mark.xfail(
    strict=True,
    reason="GCR-19: source changes do not expire reviewed closure overlays",
)
def test_source_change_expires_reviewed_exclusion():
    """Finding GCR-19: overlays are preserved by citation alone."""

    closure = _closure()
    config = closure.RootConfig(
        root="synthetic",
        source_file="source.jsonl",
        citation_root="us/test",
        module_root="us/tests",
    )
    provisions = closure._merge_provisions(
        config,
        [
            {
                "citation": "us/test/a",
                "heading": "NEW: substantive eligibility computation",
            }
        ],
        set(),
        [
            {
                "citation": "us/test/a",
                "heading": "Old bodyless heading",
                "status": "excluded",
                "reason": "container_heading",
                "basis": "The old version had no substantive body.",
            }
        ],
    )

    assert provisions[0]["status"] == "pending"


@pytest.mark.xfail(
    strict=True,
    reason="GCR-11: old partial disclosures mask unrelated pending regressions",
)
def test_existing_disclosure_cannot_mask_unrelated_pending_rise():
    """Finding GCR-11: rise is compared with all disclosures, not new ones."""

    closure = _closure()
    config = closure.RootConfig(
        root="synthetic",
        source_file="source.jsonl",
        citation_root="us/test",
        module_root="us/tests",
    )
    source_rows = [
        {"citation": "us/test/a", "heading": "A"},
        {"citation": "us/test/b", "heading": "B"},
    ]
    tree_paths = {"us/tests/a.yaml"}
    committed_rows = [
        {
            "citation": "us/test/a",
            "heading": "A",
            "status": "pending",
            "partial_coverage": "A already disclosed a deferred output.",
        },
        {
            "citation": "us/test/b",
            "heading": "B",
            # Exact exploit: unrelated reviewed exclusion is reopened plainly.
            "status": "pending",
        },
    ]
    snapshots = {
        "source.jsonl": {
            "source_repo": "repo",
            "source_ref": "ref",
            "sha256": "1" * 64,
        },
        closure.TREE_FILE: {
            "source_repo": "repo",
            "source_ref": "ref",
            "sha256": "2" * 64,
        },
    }
    provenance = closure._generated_provenance(config, snapshots)
    baseline = closure.RatchetBaseline(
        pins_sha256=closure._pins_sha256(provenance),
        pending_max=1,
    )
    errors: list[str] = []
    document = closure._build_universe(
        config,
        source_rows=source_rows,
        tree_paths=tree_paths,
        snapshots=snapshots,
        committed_rows=committed_rows,
        baseline=baseline,
        errors=errors,
    )

    assert sum(row["status"] == "pending" for row in document["provisions"]) == 2
    assert errors


@pytest.mark.xfail(
    strict=True,
    reason="GCR-12: semantic no-op snapshot bytes reset the pending ratchet",
)
def test_semantic_noop_repin_does_not_reset_pending_floor(tmp_path: Path):
    """Finding GCR-12: a blank line changes pins although parsed rows do not."""

    closure = _closure()
    config = closure.RootConfig(
        root="synthetic",
        source_file="source.jsonl",
        citation_root="us/test",
        module_root="us/tests",
    )
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    row = json.dumps({"citation_path": "us/test/a", "heading": "A"}) + "\n"
    (first_dir / config.source_file).write_text(row)
    (second_dir / config.source_file).write_text(row + "\n")
    first_errors: list[str] = []
    second_errors: list[str] = []
    first_rows = closure._load_source_rows(config, first_dir, first_errors)
    second_rows = closure._load_source_rows(config, second_dir, second_errors)
    assert first_rows == second_rows
    assert not first_errors and not second_errors

    def pin(path: Path) -> str:
        provenance = {
            "source_file": config.source_file,
            "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "rulespec_file": closure.TREE_FILE,
            "rulespec_sha256": "3" * 64,
        }
        return closure._pins_sha256(provenance)

    assert pin(first_dir / config.source_file) == pin(
        second_dir / config.source_file
    )


@pytest.mark.xfail(
    strict=True,
    reason="GCR-13: malformed closure classification rows are silently dropped",
)
def test_merge_rejects_classification_missing_citation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Finding GCR-13: a misspelled citation can leave a known stub encoded."""

    merge = _merge_closure()
    classifications = tmp_path / "classifications"
    universes = tmp_path / "universes"
    classifications.mkdir()
    universes.mkdir()
    (classifications / "mutant.yaml").write_text(
        yaml.safe_dump(
            {
                "rows": [
                    {
                        "citaiton": "us/test/a",
                        "status": "pending",
                        "note": "Module defers the substantive output.",
                    }
                ]
            }
        )
    )
    (universes / "root.yaml").write_text(
        yaml.safe_dump(
            {
                "provisions": [
                    {
                        "citation": "us/test/a",
                        "status": "encoded",
                        "encoded_by": ["us/tests/a.yaml"],
                    }
                ],
                "ratchet": {"pending_max": 0},
            }
        )
    )
    tree = tmp_path / "rulespec-us-files.txt"
    tree.write_text("us/tests/a.yaml\n")
    monkeypatch.setattr(merge, "UNIVERSE_DIR", universes)
    monkeypatch.setattr(merge, "PINNED_TREE", tree)

    assert merge.main(["--in", str(classifications), "--dry-run"]) != 0


@pytest.mark.xfail(
    strict=True,
    reason="GCR-14: scalar manifest inputs bypass typed duplicate detection",
)
def test_bridge_manifest_inputs_must_be_an_array(
    monkeypatch: pytest.MonkeyPatch,
):
    """Finding GCR-14: `inputs: abc` is iterated as three input names."""

    manifests = _manifests()
    monkeypatch.setattr(manifests, "_report_for", lambda _names: ("report.json", {}))
    payload = {
        "schema": manifests.SCHEMA,
        "suite": "victim",
        "program": "program",
        "population": {"pin_required": False},
        "oracle": {},
        "bindings": [
            {
                "kind": "mapped",
                "inputs": "abc",
                "source": "population:x",
                "audit": "read",
            },
            {
                "kind": "constant",
                "input": "abc",
                "reason": "fixture",
                "audit": "read",
            },
        ],
    }

    errors, _findings = manifests.validate(Path("mutant.yaml"), payload)
    assert errors


@pytest.mark.xfail(
    strict=True,
    reason="GCR-15: covered_by accepts circular or unrelated repository files",
)
def test_bridge_covered_by_must_resolve_to_relevant_independent_evidence():
    """Finding GCR-15: any existing path, including pyproject.toml, authorizes."""

    manifests = _manifests()
    assert manifests._covered_by_resolves("pyproject.toml") is False


@pytest.mark.xfail(
    strict=True,
    reason="GCR-16: one malformed token satisfies population pinning",
)
def test_population_pin_requires_revision_and_valid_digest(
    monkeypatch: pytest.MonkeyPatch,
):
    """Finding GCR-16: sha256='yes' suppresses the missing-pin finding."""

    manifests = _manifests()
    monkeypatch.setattr(
        manifests,
        "_report_for",
        lambda _names: (
            "report.json",
            {"dataset_identity": {"sha256": "yes"}},
        ),
    )
    payload = {
        "schema": manifests.SCHEMA,
        "suite": "victim",
        "program": "program",
        "population": {"pin_required": True},
        "oracle": {},
        "bindings": [
            {
                "kind": "mapped",
                "input": "income",
                "source": "population:income",
                "audit": "read",
            }
        ],
        "completeness": {"status": "unverified"},
    }

    errors, findings = manifests.validate(Path("mutant.yaml"), payload)
    population_problems = [
        problem
        for problem in [*errors, *findings]
        if "population pin" in problem or "dataset identity" in problem
    ]
    assert population_problems


@pytest.mark.xfail(
    strict=True,
    reason="GCR-17: cardinality-only evidence may claim a measured match rate",
)
def test_cardinality_only_case_cannot_claim_full_agreement():
    """Finding GCR-17: `r: 100` is accepted without any stored verdict."""

    evidence = _evidence()
    defects: list[str] = []
    _identity, outcomes, explicit, _verdicts = evidence._validate_compact_case(
        {"id": "case-1", "r": 100, "h": {}, "m": []},
        "chunk-0.json row 0",
        defects,
        "victim",
    )
    assert outcomes is None
    assert explicit is False
    assert defects
