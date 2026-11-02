"""Unit tests for the per-rule verification generator (A7).

The generator is a standalone script under scripts/, so it is loaded by path.
These cover the pure join logic — grounding classification, manifest-path
resolution, surface (oracle) indexing — plus a consistency check that the
committed artifacts recompute correctly.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
DATA = Path(__file__).resolve().parents[1] / "dashboard" / "public" / "data"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rv = _load("rule_verification")


# ── grounding ──────────────────────────────────────────────────────────────
def test_grounded_by_span_anchored_proof_atoms():
    rule = {
        "name": "x",
        "source": "42 U.S.C. 1382b(a)(5)",
        "metadata": {
            "proof": {
                "atoms": [
                    {
                        "path": "versions[0].formula",
                        "source": {
                            "corpus_citation_path": "us/statute/42/1382b/a",
                            "excerpt": "during the period of twenty years",
                        },
                    }
                ]
            }
        },
    }
    g = rv.rule_grounding(rule, module_citation="us/statute/42/1382b/a")
    assert g["grounded"] is True
    assert g["span_anchored"] is True
    assert g["has_proof_atoms"] is True


def test_grounded_by_source_plus_module_citation_without_atoms():
    rule = {"name": "x", "source": "Texas Works Handbook A-1340"}
    g = rv.rule_grounding(rule, module_citation="us-tx/manual/hhs/...")
    assert g["grounded"] is True
    assert g["span_anchored"] is False
    assert g["has_proof_atoms"] is False


def test_not_grounded_without_citation_or_atoms():
    rule = {"name": "x"}
    g = rv.rule_grounding(rule, module_citation=None)
    assert g["grounded"] is False


def test_source_without_module_citation_is_not_grounded():
    # A bare source string with no module-level corpus path and no proof atoms
    # is not enough to call the rule grounded.
    rule = {"name": "x", "source": "some statute"}
    g = rv.rule_grounding(rule, module_citation=None)
    assert g["grounded"] is False
    assert g["has_source_citation"] is True


# ── manifest index resolution ──────────────────────────────────────────────
def test_manifest_index_resolves_federal_and_state_paths(monkeypatch):
    tree = [
        ".axiom/encoding-manifests/statutes/26/3127.json",  # federal (root tree)
        ".axiom/encoding-manifests/us-al/policies/x.json",  # state under root tree
        "us-nc/.axiom/encoding-manifests/policies/y.json",  # per-state tree
    ]
    blobs = {
        ".axiom/encoding-manifests/statutes/26/3127.json": json.dumps(
            {
                "signature": {"value": "sig"},
                "applied_files": [
                    {"path": "statutes/26/3127.yaml", "sha256": "aaa"},
                    {"path": "statutes/26/3127.test.yaml", "sha256": "ttt"},
                ],
            }
        ).encode(),
        ".axiom/encoding-manifests/us-al/policies/x.json": json.dumps(
            {
                "signature": {"value": "sig"},
                "applied_files": [{"path": "us-al/policies/x.yaml", "sha256": "bbb"}],
            }
        ).encode(),
        "us-nc/.axiom/encoding-manifests/policies/y.json": json.dumps(
            {
                # unsigned manifest → recorded but signed=False
                "applied_files": [{"path": "policies/y.yaml", "sha256": "ccc"}],
            }
        ).encode(),
    }
    monkeypatch.setattr(rv, "batch_blobs", lambda repo, ref, paths: blobs)
    index = rv.build_manifest_index(Path("/repo"), "HEAD", tree)

    # federal manifest drops us/ in applied_files → resolves to us/statutes/...
    assert index["us/statutes/26/3127.yaml"] == {"signed": True, "sha256": "aaa"}
    # state-under-root keeps its us-al/ prefix
    assert index["us-al/policies/x.yaml"] == {"signed": True, "sha256": "bbb"}
    # per-state tree resolves relative to us-nc/, unsigned
    assert index["us-nc/policies/y.yaml"] == {"signed": False, "sha256": "ccc"}
    # .test.yaml entries are never indexed as rule files
    assert not any(k.endswith(".test.yaml") for k in index)


# ── surface (oracle) index ─────────────────────────────────────────────────
def test_surface_index_prefers_oracle_status_over_coverage_only():
    coverage = {
        "axiom": {
            "programs": [
                {"program": "snap", "jurisdiction": "CO", "status": "coverageOnly"},
                {"program": "snap", "jurisdiction": "CO", "status": "executable"},
                {"program": "tanf", "jurisdiction": "TX", "status": "coverageOnly"},
            ]
        }
    }
    surfaces = rv.build_surface_index(coverage)
    # executable beats coverageOnly for the same (family, jurisdiction)
    assert surfaces[("snap", "CO")]["status"] == "executable"
    assert surfaces[("tanf", "TX")]["status"] == "coverageOnly"


def test_ct_ordinary_income_tax_module_classifies_to_reviewed_surface():
    assert rv.classify(
        "us-ct/policies/income_tax/"
        "2026_resident_ordinary_tax_before_personal_credit.yaml"
    ) == ("state_income_tax", "CT")
    assert (
        rv.classify(
            "us-ct/policies/income_tax/2026_resident_liability_source_hold.yaml"
        )
        is None
    )


def test_ga_annual_tax_component_classifies_to_reviewed_surface():
    assert rv.classify(
        "us-ga/policies/income_tax/"
        "2026_annual_tax_before_nonrefundable_credits.yaml"
    ) == ("state_income_tax", "GA")
    assert (
        rv.classify(
            "us-ga/policies/income_tax/2026_resident_liability_source_hold.yaml"
        )
        is None
    )


def test_al_schedule_module_classifies_to_reviewed_surface():
    assert rv.classify(
        "us-al/policies/income_tax/"
        "2026_section_40_18_5_schedule_before_credits.yaml"
    ) == ("state_income_tax", "AL")
    assert (
        rv.classify(
            "us-al/policies/income_tax/2026_resident_liability_source_hold.yaml"
        )
        is None
    )


def test_ms_schedule_module_classifies_to_reviewed_surface():
    assert rv.classify(
        "us-ms/policies/income_tax/2026_section_27_7_5_schedule.yaml"
    ) == ("state_income_tax", "MS")
    assert (
        rv.classify(
            "us-ms/policies/income_tax/pilot_liability_pipeline.yaml"
        )
        is None
    )


def test_oracle_status_constants_match_plan_headline():
    # The strict headline counts only 'executable' surfaces (the plan's 14/56);
    # the broader ORACLE_STATUSES set additionally admits parameter/partial runs.
    assert rv.STRICT_EXECUTABLE == {"executable"}
    assert "executable" in rv.ORACLE_STATUSES
    assert "coverageOnly" not in rv.ORACLE_STATUSES


# ── committed-artifact consistency (mirrors the CI guard) ───────────────────
@pytest.mark.skipif(
    not (DATA / "rule_verification_summary.json").exists(),
    reason="generated data not present",
)
def test_committed_summary_recomputes_from_full():
    full = json.loads((DATA / "rule_verification.json").read_text())
    summary = json.loads((DATA / "rule_verification_summary.json").read_text())
    rules = full["rules"]
    assert summary["rules"]["total"] == len(rules)
    assert summary["rules"]["grounded"] == sum(1 for r in rules if r["grounded"])
    assert summary["rules"]["manifest_backed"] == sum(
        1 for r in rules if r["manifest_backed"]
    )
    # invariant: no rule is marked oracle-covered on a coverageOnly surface
    assert not any(
        r["surface_oracle"] and r["surface_status"] == "coverageOnly" for r in rules
    )
    # invariant: executable ⊆ any_oracle ⊆ total surfaces
    surf = summary["surfaces"]
    assert surf["executable"] <= surf["any_oracle"] <= surf["total"]


# ── #644: non-ASCII paths survive git listing ─────────────────────────────
import subprocess  # noqa: E402

from hypothesis import HealthCheck, given, settings, strategies as st  # noqa: E402


def _commit_tree(repo: Path, files: dict[str, bytes]) -> None:
    def run(*args: str) -> None:
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    run("init", "-q")
    for name, body in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    run("add", "-A")
    run(
        "-c", "user.name=t", "-c", "user.email=t@example.org", "commit", "-q", "-m", "x"
    )


def test_list_tree_keeps_non_ascii_paths(tmp_path: Path) -> None:
    # git quotes "1437c–1.yaml" as "1437c\342\200\2231.yaml" without -z.
    en_dash = "us/statutes/42/1437c–1.yaml"
    files = {en_dash: b"rules: []\n", "us/statutes/42/1437c.yaml": b"rules: []\n"}
    _commit_tree(tmp_path, files)
    tree = rv.list_tree(tmp_path, "HEAD")
    assert sorted(tree) == sorted(files)
    assert rv.batch_blobs(tmp_path, "HEAD", tree) == files


_NAME_CHARS = st.characters(
    codec="utf-8",
    categories=("L", "N", "Pd", "Zs"),
    exclude_characters="\n\r\t",
)


@settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    names=st.sets(
        st.text(_NAME_CHARS, min_size=1, max_size=12).map(str.strip).filter(bool),
        min_size=1,
        max_size=5,
    )
)
def test_property_list_tree_round_trips_any_utf8_name(tmp_path_factory, names) -> None:
    # Every listed name reads back its own bytes through batch_blobs, so no
    # blob can shift to another path.
    repo = tmp_path_factory.mktemp("repo")
    files = {f"mod/{name}.yaml": f"body of {name}\n".encode() for name in names}
    _commit_tree(repo, files)
    tree = rv.list_tree(repo, "HEAD")
    assert sorted(tree) == sorted(files)
    assert rv.batch_blobs(repo, "HEAD", tree) == files


def test_list_tree_refuses_a_newline_in_a_path(tmp_path):
    # batch_blobs speaks newline-separated `git cat-file --batch`; a name with
    # a newline would split into two requests and shift every later blob to
    # the wrong path (us/e.yaml would get us/d.yaml's bytes).
    files = {
        "us/a.yaml": b"A\n",
        "us/b\nc.yaml": b"BC\n",
        "us/d.yaml": b"D\n",
        "us/e.yaml": b"E\n",
    }
    _commit_tree(tmp_path, files)
    with pytest.raises(ValueError, match="newline"):
        rv.list_tree(tmp_path, "HEAD")


def test_batch_blobs_refuses_a_newline_name(tmp_path):
    _commit_tree(tmp_path, {"us/a.yaml": b"A\n"})
    with pytest.raises(ValueError, match="newline"):
        rv.batch_blobs(tmp_path, "HEAD", ["us/a.yaml", "us/b\nc.yaml"])
