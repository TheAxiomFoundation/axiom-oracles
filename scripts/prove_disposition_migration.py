"""Prove the TAXSIM disposition migration left every row assignment unchanged.

Loads the pre-migration merge module, dispositions and reports from a baseline
commit (default: the audited origin/main, 69d6e1b1), merges both versions from
annotation-free reports, and compares assignment digests (no engine runs). See
docs/taxsim-disposition-migration-audit.md.

Usage: uv run python scripts/prove_disposition_migration.py [BASELINE_REF]
"""

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
from axiom_oracles.comparison import dispositions as current  # noqa: E402

BASELINE = (
    sys.argv[1] if len(sys.argv) > 1 else "69d6e1b121b76b1406dfd8c73a5d45cc12d932cc"
)
REF = subprocess.check_output(["git", "rev-parse", BASELINE], text=True).strip()
TRACKED = subprocess.check_output(
    ["git", "ls-tree", "-r", "--name-only", REF], text=True
).splitlines()
TRACKED_SET = set(TRACKED)


def before_bytes(path):
    return subprocess.check_output(["git", "show", f"{REF}:{path}"])


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def is_taxsim(report):
    engines = report.get("engines") or {}
    return "taxsim" in engines or "taxsim" in engines.values()


with tempfile.TemporaryDirectory(prefix="disposition-migration-baseline-") as directory:
    temp = Path(directory)
    source = temp / "dispositions_original.py"
    source.write_bytes(before_bytes("axiom_oracles/comparison/dispositions.py"))
    spec = importlib.util.spec_from_file_location("pr3_dispositions_original", source)
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    report_paths = []
    for path in TRACKED:
        if not path.endswith(".json") or not path.startswith(
            ("reports/", "dashboard/public/data/")
        ):
            continue
        if "/cases/" in path or "/dispositions/" in path:
            continue
        # Inspect all tracked report artifacts, not only filenames containing taxsim.
        report = json.loads((ROOT / path).read_text())
        if (
            isinstance(report, dict)
            and "summary" in report
            and "suite" in report
            and is_taxsim(report)
        ):
            report_paths.append(path)
    reports = {}
    for path in report_paths:
        reports[path] = (
            json.loads(before_bytes(path)),
            json.loads((ROOT / path).read_text()),
        )
        target = temp / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(before_bytes(path))
    documents = {}
    for before_report, after_report in reports.values():
        suite = before_report["suite"]
        path = f"dispositions/{suite}.yaml"
        if path not in TRACKED_SET:
            documents[suite] = (None, None)
            continue
        target = temp / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(before_bytes(path))
        # Original load validates old schema/arithmetic. Its optional source-existence
        # check uses the repo; all source citations predate this migration.
        documents[suite] = (
            original.load_dispositions(target, repo_root=ROOT),
            current.load_dispositions(ROOT / path, repo_root=ROOT),
        )
    cache = {}

    def merge(path, side):
        key = (path, side)
        if key in cache:
            return cache[key]
        report = reports[path][side]
        module = (original, current)[side]
        count = report["summary"]["mismatch_count"]
        source_report = (report["summary"].get("dispositioned") or {}).get(
            "source_report"
        )
        if len(report.get("mismatches") or []) < count:
            assert source_report is not None, path
            full_path = source_report["path"]
            raw = (
                before_bytes(full_path)
                if side == 0
                else (ROOT / full_path).read_bytes()
            )
            assert digest(raw) == source_report["sha256"], path
            full = merge(full_path, side)
            assert len(full["mismatches"]) == count
            expected = report["summary"]["dispositioned"]["assignment_sha256"]
            assert module.assignment_digest(full) == expected, path
            assignments = {
                (r["case_id"], r["concept"]): r.get("disposition")
                for r in full["mismatches"]
            }
            assert len(assignments) == len(full["mismatches"])
            merged = dict(report)
            retained = []
            for row in report["mismatches"]:
                annotation = assignments[(row["case_id"], row["concept"])]
                assert row.get("disposition") == annotation, (path, row["case_id"])
                fresh_row = dict(row)
                fresh_row.pop("disposition", None)
                if annotation is not None:
                    fresh_row["disposition"] = annotation
                retained.append(fresh_row)
            merged["mismatches"] = retained
        else:
            assert len(report.get("mismatches") or []) == count, path
            # Drop stored annotations so neither implementation can pass by
            # accidentally retaining already-merged assignments.
            raw = dict(report)
            raw["mismatches"] = [
                {k: v for k, v in row.items() if k != "disposition"}
                for row in report.get("mismatches") or []
            ]
            merged = module.apply_dispositions(raw, documents[report["suite"]][side])
        cache[key] = merged
        return merged

    rows = []
    for path in report_paths:
        before, after = merge(path, 0), merge(path, 1)
        old_digest, new_digest = (
            original.assignment_digest(before),
            current.assignment_digest(after),
        )
        assert old_digest == new_digest, path
        before_file, after_file = reports[path]
        pointer = (after_file["summary"].get("dispositioned") or {}).get(
            "source_report"
        )
        item = {
            "path": path,
            "suite": before_file["suite"],
            "stored_rows": len(after["mismatches"]),
            "mismatch_count": after_file["summary"]["mismatch_count"],
            "before_assignment_digest": old_digest,
            "after_assignment_digest": new_digest,
            "before_report_sha256": digest(before_bytes(path)),
            "after_report_sha256": digest((ROOT / path).read_bytes()),
            "dispositions_file": f"dispositions/{before_file['suite']}.yaml"
            if documents[before_file["suite"]][0] is not None
            else None,
        }
        if pointer:
            item["source_report"] = pointer
            item["full_assignment_digest"] = current.assignment_digest(
                merge(pointer["path"], 1)
            )
        rows.append(item)
    chunks = []
    for path in TRACKED:
        if (
            path.startswith("dashboard/public/data/cases/")
            and path.endswith(".json")
            and "taxsim" in path
        ):
            old, new = before_bytes(path), (ROOT / path).read_bytes()
            assert old == new, path
            chunks.append({"path": path, "sha256": digest(new)})
    non_taxsim_path = "dashboard/public/data/axiom-euromod-be-worker-ssc.json"
    before_ssc, after_ssc = (
        json.loads(before_bytes(non_taxsim_path)),
        json.loads((ROOT / non_taxsim_path).read_text()),
    )
    delta = after_ssc["summary"]["dispositioned"].pop("expired_reasons")
    assert before_ssc == after_ssc
    assert delta == {"dataset-uprating-bridge-artifact-resolved": "no_live_rows"}
    result = {
        "baseline_ref": "origin/main",
        "baseline_commit": REF,
        "baseline_module_sha256": digest(source.read_bytes()),
        "reports": rows,
        "unchanged_case_artifacts": chunks,
        "non_taxsim_metadata_only_change": {
            "path": non_taxsim_path,
            "expired_reasons": delta,
        },
    }
    out = ROOT / "docs/taxsim-disposition-migration-baseline.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(
        f"PASS: {len(rows)} TAXSIM reports preserve independently re-merged assignment digests; {len(chunks)} case artifacts byte-identical."
    )
    print(
        f"Baseline origin/main {REF}; module SHA256 {result['baseline_module_sha256']}"
    )
    for row in rows:
        print(
            row["path"],
            row["stored_rows"],
            row["before_assignment_digest"],
            row["after_assignment_digest"],
        )
