"""Mutants proving the NZ v3 closure frontiers are rederived.

Each mutant is followed by restoration of the exact guarded input.  That
second assertion distinguishes a live guard from an unrelated test failure.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import importlib.util
import json
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest


REPO = Path(__file__).resolve().parent.parent
SUMMARY = REPO / "closure" / "nz" / "summary.json"
INSTRUMENT_GRAPH = REPO / "conformance" / "closure" / "nz-instrument-graph.json"
INSTRUMENT_DISPOSITIONS = REPO / "closure" / "nz" / "instrument-dispositions.json"
INSTRUMENT_ENCODE_QUEUE = REPO / "closure" / "nz" / "instrument-encode-queue.json"
DEPENDENCY_DISPOSITIONS = REPO / "closure" / "nz" / "dependency-dispositions.json"


def _load_nz_closure():
    spec = importlib.util.spec_from_file_location(
        "nz_closure_instrument_mutants", REPO / "scripts" / "nz_closure.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_nz_refresh():
    spec = importlib.util.spec_from_file_location(
        "refresh_nz_instrument_graph_test",
        REPO / "scripts" / "refresh_nz_instrument_graph.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_nz_spine():
    spec = importlib.util.spec_from_file_location(
        "nz_spine_mutants", REPO / "scripts" / "nz_spine.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_nz_audit_report():
    spec = importlib.util.spec_from_file_location(
        "nz_v3_audit_report_mutants", REPO / "scripts" / "nz_v3_audit_report.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _summary() -> dict:
    return json.loads(SUMMARY.read_text())


@contextmanager
def _repo_local_graph_copy(module, monkeypatch) -> Iterator[tuple[Path, bytes, dict]]:
    """Yield an exact graph copy and an artifact adjusted only for its path."""

    original = INSTRUMENT_GRAPH.read_bytes()
    with tempfile.TemporaryDirectory(prefix=".nz-instrument-mutant-", dir=REPO) as raw:
        graph_path = Path(raw) / INSTRUMENT_GRAPH.name
        graph_path.write_bytes(original)
        monkeypatch.setattr(module, "INSTRUMENT_GRAPH_PATH", graph_path)
        artifact = _summary()
        artifact["generated_facts"]["instrument_graph"]["snapshot_path"] = (
            graph_path.relative_to(REPO).as_posix()
        )
        yield graph_path, original, artifact


@contextmanager
def _repo_local_decision_copy(
    module,
    monkeypatch,
    *,
    source_path: Path,
    module_attribute: str,
    prefix: str,
) -> Iterator[tuple[Path, bytes, dict]]:
    """Yield a byte-exact decision copy and its locally rederived baseline."""

    original = source_path.read_bytes()
    with tempfile.TemporaryDirectory(prefix=prefix, dir=REPO) as raw:
        local_path = Path(raw) / source_path.name
        local_path.write_bytes(original)
        monkeypatch.setattr(module, module_attribute, local_path)
        baseline = module.build(module.load_source())
        yield local_path, original, baseline


def _write_json(path: Path, document: dict) -> None:
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )


def test_committed_nz_instrument_frontier_rederives():
    module = _load_nz_closure()
    document = _summary()

    validated = module.validate_artifact(document, repo_root=REPO)
    assert validated == document
    assert validated.closed is False
    verification = module.verify_artifact(artifact_path=SUMMARY)
    assert verification.valid
    assert verification.document == document
    assert set(document["programs"]) == set(module.PROGRAM_INSTRUMENT_ACT)
    assert "instrument_frontier" in document["computed"]
    assert all(
        "instrument_frontier" in program
        for program in document["programs"].values()
    )
    global_frontier = document["computed"]["instrument_frontier"]
    assert global_frontier["instrument_count"] == 301
    assert global_frontier["reported_instrument_count"] == 437
    assert global_frontier["supplemental_count"] == 46
    assert global_frontier["counts"] == {
        "total": 347,
        "encoded": 13,
        "classified-with-reason": 0,
        "excluded-with-reason": 295,
        "pending": 39,
    }
    assert sum(
        row["unresolved_listing_rows"]
        for row in global_frontier["capture_gaps"]
    ) == 136

    dependency = document["computed"]["dependency_closure"]
    assert dependency["closed"] is False
    assert dependency["open_dependency_count"] == 268
    assert len(dependency["law_derived_inputs"]) == 229
    assert len(dependency["instruments_bearing_on_computed"]) == 39
    grounding = document["computed"]["input_grounding"]
    assert grounding["input_count"] == 288
    assert grounding["counts"] == {
        "encoded": 2,
        "law_derived": 229,
        "world_fact": 57,
    }

    expected_program_counts = {
        "nz/acc-earners-levy": (134, 2, 0, 130, 2),
        "nz/accommodation-supplement": (73, 3, 0, 67, 3),
        "nz/income-tax": (127, 1, 0, 101, 25),
        "nz/independent-earner-tax-credit": (130, 7, 0, 91, 32),
        "nz/main-benefits": (70, 3, 0, 66, 1),
        "nz/winter-energy-payment": (69, 0, 0, 68, 1),
        "nz/working-for-families": (134, 8, 0, 93, 33),
    }
    for program, expected in expected_program_counts.items():
        counts = document["programs"][program]["instrument_frontier"]["counts"]
        assert (
            counts["total"],
            counts["encoded"],
            counts["classified-with-reason"],
            counts["excluded-with-reason"],
            counts["pending"],
        ) == expected

    frontiers = [
        global_frontier,
        *(program["instrument_frontier"] for program in document["programs"].values()),
    ]
    for frontier in frontiers:
        assert frontier["counts"]["total"] == len(frontier["ledger"])
        assert frontier["counts"]["pending"] == len(frontier["pending"])


def test_encode_queue_exactly_tracks_unique_bearing_frontier():
    document = _summary()
    queue = json.loads(INSTRUMENT_ENCODE_QUEUE.read_text())
    assert queue["schema"] == "axiom_oracles.nz_instrument_encode_queue.v1"
    assert queue["certified_period"] == {
        "start": "2026-04-01",
        "end": "2027-03-31",
    }
    assert queue["reviewed_acts"] == [
        "Accident Compensation Act 2001",
        "Income Tax Act 2007",
        "Social Security Act 2018",
    ]
    assert queue["source_dispositions"] == (
        "closure/nz/instrument-dispositions.json"
    )

    pending_by_eli: dict[str, dict[str, set[str]]] = {}
    for program, program_document in document["programs"].items():
        for row in program_document["instrument_frontier"]["ledger"]:
            if row["status"] != "pending":
                continue
            pending = pending_by_eli.setdefault(
                row["eli"], {"programs": set(), "target_modules": set(), "sizes": set()}
            )
            pending["programs"].add(program)
            target = row["target_module"]
            pending["target_modules"].update(
                target if isinstance(target, list) else [target]
            )
            pending["sizes"].add(row["size_class"])

    items = queue["items"]
    assert len(items) == 39
    assert [row["eli"] for row in items] == sorted(pending_by_eli)
    assert set(pending_by_eli) == set(
        document["computed"]["dependency_closure"][
            "instruments_bearing_on_computed"
        ]
    )
    for row in items:
        assert set(row) == {
            "bearing_surface",
            "defining_provision",
            "eli",
            "programs",
            "reason",
            "size_class",
            "source_checked_at",
            "source_url",
            "target_modules",
            "title",
        }
        expected = pending_by_eli[row["eli"]]
        assert row["programs"] == sorted(expected["programs"])
        assert row["target_modules"] == sorted(expected["target_modules"])
        assert expected["sizes"] == {row["size_class"]}
        assert row["source_checked_at"] == "2026-08-21"
        assert row["source_url"].startswith("https://")
        assert all(row[field].strip() for field in (
            "bearing_surface",
            "defining_provision",
            "reason",
            "title",
        ))


def test_audit_report_byte_drift_is_rejected_and_exact_bytes_restore_guard():
    module = _load_nz_audit_report()
    baseline = module.render_markdown(module.build_model()).encode()
    with tempfile.TemporaryDirectory(prefix=".nz-v3-report-mutant-", dir=REPO) as raw:
        output = Path(raw) / "audit.md"
        output.write_bytes(baseline)
        arguments = ["--check", "--output", str(output)]
        assert module.main(arguments) == 0

        output.write_bytes(baseline + b" ")
        assert module.main(arguments) == 1

        output.write_bytes(baseline)
        assert output.read_bytes() == baseline
        assert module.main(arguments) == 0


def test_spine_citation_drop_is_rejected_and_exact_denominator_restores_guard():
    module = _load_nz_spine()
    original = list(module.EXPECTED_CANDIDATE_CITATIONS)
    baseline = module.build_spine_frontier(original)
    assert baseline["direct_encoded_subgraph_scope"]["total"] == 57
    assert baseline["requested_legal_subgraph_scope"]["total"] == 174
    assert baseline["all_channel_legal_subgraph_scope"]["total"] == 200
    assert baseline["whole_body_scope"]["total"] == 4707
    mutant = original[:-1]
    with pytest.raises(module.NZSpineError, match="57-path ratchet"):
        module.build_spine_frontier(mutant)
    assert module.build_spine_frontier(original) == baseline


@pytest.mark.parametrize(
    ("argument", "constant", "count"),
    (
        (
            "dependency_root_citations",
            "EXPECTED_DEPENDENCY_ROOT_CITATIONS",
            117,
        ),
        (
            "all_channel_additional_citations",
            "EXPECTED_ALL_CHANNEL_ADDITIONAL_CITATIONS",
            26,
        ),
    ),
)
def test_spine_supplement_drop_is_rejected_and_exact_ratchet_restores_guard(
    argument, constant, count
):
    module = _load_nz_spine()
    direct = list(module.EXPECTED_CANDIDATE_CITATIONS)
    original = list(getattr(module, constant))
    assert len(original) == count
    baseline = module.build_spine_frontier(direct)
    with pytest.raises(module.NZSpineError, match=f"{count}-path ratchet"):
        module.build_spine_frontier(direct, **{argument: original[:-1]})
    assert module.build_spine_frontier(direct, **{argument: original}) == baseline


def test_dependency_row_removal_is_rejected_and_exact_bytes_restore_guard(
    monkeypatch,
):
    module = _load_nz_closure()
    with _repo_local_decision_copy(
        module,
        monkeypatch,
        source_path=DEPENDENCY_DISPOSITIONS,
        module_attribute="DEPENDENCY_DISPOSITIONS_PATH",
        prefix=".nz-dependency-removal-mutant-",
    ) as (path, original, baseline):
        assert module.validate_artifact(baseline, repo_root=REPO) == baseline
        mutant = json.loads(original)
        removed = mutant["input_grounding"].pop()
        try:
            _write_json(path, mutant)
            with pytest.raises(
                module.ClosureError,
                match=(
                    "missing NZ dependency grounding "
                    f"{removed['source_surface']}:{removed['name']}"
                ),
            ):
                module.build(module.load_source())
        finally:
            path.write_bytes(original)
        assert path.read_bytes() == original
        assert module.validate_artifact(baseline, repo_root=REPO) == baseline


def test_law_derived_residence_cannot_be_laundered_to_world_fact(
    monkeypatch,
):
    module = _load_nz_closure()
    with _repo_local_decision_copy(
        module,
        monkeypatch,
        source_path=DEPENDENCY_DISPOSITIONS,
        module_attribute="DEPENDENCY_DISPOSITIONS_PATH",
        prefix=".nz-dependency-kind-mutant-",
    ) as (path, original, baseline):
        assert module.validate_artifact(baseline, repo_root=REPO) == baseline
        mutant = json.loads(original)
        row = next(
            value
            for value in mutant["input_grounding"]
            if value["source_surface"] == "eligibility_closure"
            and value["name"]
            == "residence.iwtc_person_resident_under_yd1_on_credit_days"
        )
        row.update(
            classification="world_fact",
            leaf_kind="world_fact",
            reason="The scenario reports this as an observed residence fact.",
        )
        for field in ("derivation_instrument", "size_class", "target_module"):
            row.pop(field)
        try:
            _write_json(path, mutant)
            with pytest.raises(
                module.ClosureError,
                match="classifications or legal bindings drifted",
            ):
                module.build(module.load_source())
        finally:
            path.write_bytes(original)
        assert path.read_bytes() == original
        assert module.validate_artifact(baseline, repo_root=REPO) == baseline


def test_law_derived_target_cannot_swap_to_another_valid_module(
    monkeypatch,
):
    module = _load_nz_closure()
    with _repo_local_decision_copy(
        module,
        monkeypatch,
        source_path=DEPENDENCY_DISPOSITIONS,
        module_attribute="DEPENDENCY_DISPOSITIONS_PATH",
        prefix=".nz-dependency-module-mutant-",
    ) as (path, original, baseline):
        assert module.validate_artifact(baseline, repo_root=REPO) == baseline
        mutant = json.loads(original)
        row = next(
            value
            for value in mutant["input_grounding"]
            if value["source_surface"] == "engine_request"
            and value["name"]
            == "independent_earner_tax_credit_resident_in_new_zealand"
        )
        assert row["target_module"] == (
            "nz/statutes/income_tax/credits/individual_credits.yaml"
        )
        row["target_module"] = (
            "nz/statutes/income_tax/family_scheme/eligibility.yaml"
        )
        try:
            _write_json(path, mutant)
            with pytest.raises(
                module.ClosureError,
                match="classifications or legal bindings drifted",
            ):
                module.build(module.load_source())
        finally:
            path.write_bytes(original)
        assert path.read_bytes() == original
        assert module.validate_artifact(baseline, repo_root=REPO) == baseline


def test_known_bearing_instrument_cannot_evade_worklist_as_nonbearing_exclusion(
    monkeypatch,
):
    module = _load_nz_closure()
    with _repo_local_decision_copy(
        module,
        monkeypatch,
        source_path=INSTRUMENT_DISPOSITIONS,
        module_attribute="INSTRUMENT_DISPOSITIONS_PATH",
        prefix=".nz-instrument-bearing-mutant-",
    ) as (path, original, baseline):
        assert module.validate_artifact(baseline, repo_root=REPO) == baseline
        mutant = json.loads(original)
        row = next(
            value
            for value in mutant["instrument_dispositions"]
            if value["program"] == "nz/acc-earners-levy"
            and value["eli"]
            == "https://www.ird.govt.nz/deductions-from-salary-and-wages"
        )
        assert row["status"] == "pending"
        assert row["bears_on_computed_surface"] is True
        row.update(
            status="excluded-with-reason",
            classification="no_computational_bearing",
            bears_on_computed_surface=False,
            reason="The guidance is outside the computed surface.",
        )
        for field in ("bearing", "defining_provision", "size_class", "target_module"):
            row.pop(field)
        try:
            _write_json(path, mutant)
            with pytest.raises(
                module.ClosureError,
                match=(
                    "instrument dispositions drifted from the audited "
                    "bearing-rule producer"
                ),
            ):
                module.validate_artifact(baseline, repo_root=REPO)
        finally:
            path.write_bytes(original)
        assert path.read_bytes() == original
        assert module.validate_artifact(baseline, repo_root=REPO) == baseline


@pytest.mark.parametrize("channel", ("subject_matter_search", "corpus_citation_scan"))
def test_instrument_discovery_receipt_drift_is_rejected_and_exact_bytes_restore(
    channel,
    monkeypatch,
):
    module = _load_nz_closure()
    with _repo_local_decision_copy(
        module,
        monkeypatch,
        source_path=INSTRUMENT_DISPOSITIONS,
        module_attribute="INSTRUMENT_DISPOSITIONS_PATH",
        prefix=f".nz-{channel}-receipt-mutant-",
    ) as (path, original, baseline):
        assert module.validate_artifact(baseline, repo_root=REPO) == baseline
        mutant = json.loads(original)
        if channel == "subject_matter_search":
            queries = mutant["discovery_receipts"][channel]["queries"]
            assert len(queries) > 1
            queries.pop()
            error = (
                "instrument dispositions drifted from the audited bearing-rule producer"
            )
        else:
            mutant["discovery_receipts"][channel]["inspected_clone_commit"] = (
                "0" * 40
            )
            error = "citation-scan receipt is malformed"
        try:
            _write_json(path, mutant)
            with pytest.raises(module.ClosureError, match=error):
                module.validate_artifact(baseline, repo_root=REPO)
        finally:
            path.write_bytes(original)
        assert path.read_bytes() == original
        assert module.validate_artifact(baseline, repo_root=REPO) == baseline


def test_citation_source_coverage_drop_is_rejected_and_exact_guard_restores(
    monkeypatch,
):
    """MUTANT: every distinct citation-scan source needs a disposition."""

    module = _load_nz_closure()
    source = module.load_source()
    original = module.CITATION_SCAN_SOURCE_DISPOSITIONS
    assert len(original) == 20
    baseline = module.build(source)
    monkeypatch.setattr(module, "CITATION_SCAN_SOURCE_DISPOSITIONS", original[:-1])
    with pytest.raises(
        module.ClosureError, match="distinct-path source coverage drifted"
    ):
        module.build(source)
    monkeypatch.setattr(module, "CITATION_SCAN_SOURCE_DISPOSITIONS", original)
    assert module.build(source) == baseline


def test_live_capture_derives_exact_metadata_from_instrument_xml():
    module = _load_nz_refresh()
    raw = (
        b'<regulation date.signed="2025-02-24" date.first.valid="2025-04-01" '
        b'date.terminated="nulldate" sr.type="regulation">'
        b"<cover><title>Accident Compensation (Earners' Levy) Regulations 2025"
        b"</title></cover><front><pursuant><para><text>Made under section 329 "
        b"of the Accident Compensation Act 2001</text></para></pursuant></front>"
        b"</regulation>"
    )

    class Response:
        content = raw

        @staticmethod
        def raise_for_status():
            return None

    class Session:
        @staticmethod
        def get(url, **_kwargs):
            assert url.endswith("/en/latest.xml")
            return Response()

    eli = (
        "https://www.legislation.govt.nz/secondary-legislation/"
        "pco-drafted/2025/18/en/latest/"
    )
    row = module._live_instrument_row(
        Session(),
        eli=eli,
        listing_title="",
        act=module.ACTS[2],
        status_as_of=dt.date(2026, 8, 19),
    )

    assert row["date_document"] == "2025-02-24"
    assert row["in_force"] is True
    assert row["type_document"] == "REGULATION"
    assert row["title_short"] == "SL 2025/18"
    assert row["source_sha256"] == hashlib.sha256(raw).hexdigest()


def test_live_listing_normalizes_classic_and_modern_links_to_one_eli():
    module = _load_nz_refresh()
    raw = b"""
      <a href="/regulation/public/2025/0018/latest/whole.html">legacy</a>
      <a href="/secondary-legislation/pco-drafted/2025/18/en/latest/">current</a>
    """
    assert module._extract_instrument_links(
        raw,
        "https://www.legislation.govt.nz/act/public/2001/49/en/latest/",
    ) == [
        (
            "https://www.legislation.govt.nz/secondary-legislation/"
            "pco-drafted/2025/18/en/latest/",
            "current",
        )
    ]


def test_removed_instrument_is_rejected_and_exact_graph_restores_guard(
    monkeypatch,
):
    module = _load_nz_closure()
    with _repo_local_graph_copy(module, monkeypatch) as (
        graph_path,
        original,
        artifact,
    ):
        assert module.validate_artifact(artifact, repo_root=REPO) == artifact

        mutant = json.loads(original)
        removed_index = next(
            index
            for index, row in enumerate(mutant["instruments"])
            if row["relation"] == "basis_for"
        )
        mutant["instruments"].pop(removed_index)
        graph_path.write_text(json.dumps(mutant, indent=2, sort_keys=True) + "\n")

        with pytest.raises(module.ClosureError, match="counts do not reconcile"):
            module.validate_artifact(artifact, repo_root=REPO)

        graph_path.write_bytes(original)
        assert module.validate_artifact(artifact, repo_root=REPO) == artifact


def test_pending_count_regression_is_rejected_and_guard_reversion_passes():
    module = _load_nz_closure()
    document = _summary()
    assert module.validate_artifact(document, repo_root=REPO) == document

    mutant = copy.deepcopy(document)
    counts = mutant["computed"]["instrument_frontier"]["counts"]
    assert counts["pending"] > 0
    counts["pending"] -= 1

    with pytest.raises(module.ClosureError, match="does not rederive"):
        module.validate_artifact(mutant, repo_root=REPO)

    assert module.validate_artifact(document, repo_root=REPO) == document


def test_semantically_identical_snapshot_byte_edit_is_rejected_and_restores(
    monkeypatch,
):
    module = _load_nz_closure()
    with _repo_local_graph_copy(module, monkeypatch) as (
        graph_path,
        original,
        artifact,
    ):
        assert module.validate_artifact(artifact, repo_root=REPO) == artifact

        edited = original + b" "
        assert json.loads(edited) == json.loads(original)
        graph_path.write_bytes(edited)

        with pytest.raises(module.ClosureError, match="does not rederive"):
            module.validate_artifact(artifact, repo_root=REPO)

        graph_path.write_bytes(original)
        assert module.validate_artifact(artifact, repo_root=REPO) == artifact
