#!/usr/bin/env python3
"""Per-rule verification status: grounding, manifest provenance, and oracle coverage.

Implements Phase-A item A7 of the platform plan: make "which rules have no
oracle?" answerable and turn the coverage number into a tracked KPI.

For every *rule* (not every program surface) in a local ``rulespec-us``
checkout, this joins three independent axes:

1. **Grounding** — does the rule carry span-anchored evidence back to the
   corpus? Signals: the module's ``source_verification.corpus_citation_path``,
   the rule's ``source`` citation string, and ``metadata.proof.atoms`` (each
   atom pinning a ``corpus_citation_path`` + ``excerpt``). A rule is *grounded*
   when it has proof atoms, or a source citation backed by a module citation
   path.

2. **Manifest provenance** — is the rule's file covered by a *signed*
   ``.axiom/encoding-manifests`` entry whose recorded ``sha256`` still matches
   the file's current content? A stale manifest (sha mismatch) does not count:
   provenance must be live to mean anything.

3. **Oracle coverage** — is the rule's program *surface* exercised by a live
   cross-engine comparison? This is read from ``coverage_overview.json`` (the
   registry the weekly matrix already maintains): surfaces with status
   ``executable`` / ``executableCoverage`` / ``parameter`` have an oracle;
   ``coverageOnly`` surfaces are encoded but unverified. **This axis is
   surface-level, not rule-level** — a comparison on a program's
   benefit-calculation surface does not verify every appendix/table rule in
   that program's tree. It is therefore reported as an honest *lower-bound
   context* signal ("this rule's surface is exercised by an oracle"), never as
   "this rule is individually verified." The headline oracle KPI stays at the
   surface grain the plan names (14 of 56 executable), because that is the
   number that is actually true.

Rule → surface classification reuses ``classify()`` from
``sync_encoded_coverage.py`` verbatim, so the per-rule view and the
surface-level coverage register agree by construction.

Emits two files under ``dashboard/public/data/``:

* ``rule_verification.json`` — the full per-rule join (module path, rule name,
  kind, jurisdiction, grounding/manifest/oracle flags) plus per-surface and
  per-module rollups.
* ``rule_verification_summary.json`` — the compact KPI: rule/surface counts and
  percentages by status, broken down by jurisdiction. This is the tracked
  number.

Usage::

    python scripts/rule_verification.py \
      --rulespec-root ~/TheAxiomFoundation/rulespec-us --ref HEAD
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - matches sibling scripts' guard
    sys.stderr.write(
        "This script requires PyYAML. Install with: uv pip install pyyaml\n"
    )
    raise SystemExit(1)

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

from axiom_oracles.bridges.repo_routing import RULESPEC_ATOMIC_ROOTS  # noqa: E402
from axiom_oracles.bridges.rulespec_paths import (  # noqa: E402
    require_rulespec_checkout,
)

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
COVERAGE_PATH = REPO_ROOT / "dashboard" / "public" / "data" / "coverage_overview.json"
OUT_FULL = REPO_ROOT / "dashboard" / "public" / "data" / "rule_verification.json"
OUT_SUMMARY = (
    REPO_ROOT / "dashboard" / "public" / "data" / "rule_verification_summary.json"
)

# Surface statuses in coverage_overview.json that mean "a live comparison
# exercises this surface". ``coverageOnly`` (encoded, no suite) and ``missing``
# do not. ``partial`` is a real-but-incomplete comparison — counted as having an
# oracle for the boolean flag, but tracked separately in the summary.
# ``executable`` is a full household-level comparison — the plan's headline
# "14 of 56 surfaces". ``executableCoverage`` is a narrower executable slice,
# ``parameter`` is a parameter-only check, ``partial`` a real-but-incomplete
# comparison. All four mean *some* live oracle exercises the surface, but only
# ``executable`` counts toward the strict headline so the number matches the
# figure the plan tracks.
ORACLE_STATUSES = {"executable", "executableCoverage", "parameter", "partial"}
STRICT_EXECUTABLE = {"executable"}


def _load_classifier():
    """Import ``classify`` + ``SKIP_DIRS`` from the sibling coverage script.

    Loaded by path (not a package import) so this runs the same whether invoked
    as ``scripts/rule_verification.py`` or ``python -m``. Keeping a single
    classifier guarantees the per-rule join and the surface register never
    disagree on which (family, jurisdiction) a path belongs to.
    """
    spec = importlib.util.spec_from_file_location(
        "sync_encoded_coverage", SCRIPTS_DIR / "sync_encoded_coverage.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.classify, module.SKIP_DIRS


classify, SKIP_DIRS = _load_classifier()


# ── git plumbing (deterministic: everything reads a pinned ref, never the
#    working tree) ──────────────────────────────────────────────────────────
def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def list_tree(repo: Path, ref: str) -> list[str]:
    return git(repo, "ls-tree", "-r", "--name-only", ref).splitlines()


def batch_blobs(repo: Path, ref: str, paths: list[str]) -> dict[str, bytes]:
    """Read many blob contents in one ``git cat-file --batch`` subprocess.

    Spawning one ``git show`` per file makes the whole run take minutes on 3k
    files; batching keeps it to a couple of seconds so it is cheap enough for
    the weekly CI job.
    """
    if not paths:
        return {}
    req = "".join(f"{ref}:{p}\n" for p in paths).encode()
    proc = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        input=req,
        capture_output=True,
        check=True,
    )
    out = proc.stdout
    result: dict[str, bytes] = {}
    pos = 0
    for path in paths:
        nl = out.index(b"\n", pos)
        header = out[pos:nl].decode()
        pos = nl + 1
        parts = header.split(" ")
        if len(parts) >= 3 and parts[1] != "missing":
            size = int(parts[2])
            result[path] = out[pos : pos + size]
            pos += size + 1  # trailing newline after blob
        # missing/deleted blob: no body, nothing to advance past
    return result


# ── manifest index ────────────────────────────────────────────────────────
def build_manifest_index(repo: Path, ref: str, tree: list[str]) -> dict[str, dict]:
    """Map every rule-file path → its signed-manifest record (or absence).

    A manifest lives at ``<tree>/.axiom/encoding-manifests/<rel>.json`` and
    lists ``applied_files[]`` with ``path`` + ``sha256``. ``path`` is resolved
    relative to the manifest's tree root: the repo-root ``.axiom`` tree stores
    federal paths without the ``us/`` prefix (``statutes/26/x.yaml`` →
    ``us/statutes/26/x.yaml``) but state paths with it (``us-al/...``); per-state
    ``us-xx/.axiom`` trees store paths relative to that state dir.

    Returns ``path -> {"signed": bool, "sha256": str}`` for the resolved rule
    file (``.test.yaml`` entries are ignored — tests are not rules).
    """
    manifest_paths = [
        p for p in tree if p.endswith(".json") and ".axiom/encoding-manifests/" in p
    ]
    blobs = batch_blobs(repo, ref, manifest_paths)
    index: dict[str, dict] = {}
    for mpath in manifest_paths:
        raw = blobs.get(mpath)
        if raw is None:
            continue
        try:
            doc = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        signed = bool((doc.get("signature") or {}).get("value"))
        root = mpath.split(".axiom/encoding-manifests/", 1)[0].rstrip("/")
        for entry in doc.get("applied_files") or []:
            rel = entry.get("path", "")
            if not rel.endswith(".yaml") or rel.endswith(".test.yaml"):
                continue
            candidates = [f"{root}/{rel}"] if root else [rel, f"us/{rel}"]
            for cand in candidates:
                # Prefer a signed record if one exists for this path.
                prior = index.get(cand)
                if prior is None or (signed and not prior["signed"]):
                    index[cand] = {"signed": signed, "sha256": entry.get("sha256")}
    return index


# ── surface (oracle) index ────────────────────────────────────────────────
STATUS_RANK = {
    "executable": 0,
    "executableCoverage": 1,
    "parameter": 2,
    "partial": 3,
    "coverageOnly": 4,
    "missing": 5,
}


def build_surface_index(coverage: dict) -> dict[tuple, dict]:
    """(family, jurisdiction) → best surface record from coverage_overview."""
    surfaces: dict[tuple, dict] = {}
    for prog in coverage.get("axiom", {}).get("programs", []):
        family = prog.get("program")
        jurisdiction = prog.get("jurisdiction")
        if not family:
            continue
        key = (family, jurisdiction)
        status = prog.get("status", "coverageOnly")
        cur = surfaces.get(key)
        if cur is None or STATUS_RANK.get(status, 9) < STATUS_RANK.get(
            cur["status"], 9
        ):
            surfaces[key] = {
                "family": family,
                "jurisdiction": jurisdiction,
                "status": status,
                "source": prog.get("source"),
            }
    return surfaces


# ── per-rule grounding ─────────────────────────────────────────────────────
def rule_grounding(rule: dict, module_citation: str | None) -> dict:
    meta = rule.get("metadata") or {}
    proof = meta.get("proof") or {}
    atoms = proof.get("atoms") or []
    has_atoms = isinstance(atoms, list) and len(atoms) > 0
    # An atom is span-anchored if it cites a corpus path AND quotes an excerpt.
    span_anchored = any(
        isinstance(a, dict)
        and (a.get("source") or {}).get("corpus_citation_path")
        and (a.get("source") or {}).get("excerpt")
        for a in atoms
    )
    has_source = bool(rule.get("source"))
    # Grounded = span-anchored proof, or (a source citation backed by a
    # module-level corpus path). Proof-required-but-empty is not grounded.
    grounded = span_anchored or has_atoms or (has_source and bool(module_citation))
    return {
        "grounded": bool(grounded),
        "has_proof_atoms": has_atoms,
        "span_anchored": bool(span_anchored),
        "has_source_citation": has_source,
        "has_module_citation": bool(module_citation),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate per-rule verification status data for the dashboard."
    )
    parser.add_argument(
        "--rulespec-root",
        type=Path,
        required=True,
        help="Path to a rulespec-us monorepo checkout (federal us/ + state us-xx/).",
    )
    parser.add_argument(
        "--ref",
        default="HEAD",
        help="Exact local Git ref to read (default: HEAD).",
    )
    parser.add_argument(
        "--coverage",
        type=Path,
        default=COVERAGE_PATH,
        help="Path to coverage_overview.json (surface → oracle status).",
    )
    args = parser.parse_args()

    try:
        repo = require_rulespec_checkout(args.rulespec_root, country="us")
    except ValueError as exc:
        parser.error(str(exc))
    ref = args.ref
    # Resolve to a concrete commit so the output records exactly what was read.
    commit = git(repo, "rev-parse", ref).strip()

    tree = list_tree(repo, ref)
    rule_files = []
    for path in tree:
        parts = Path(path).parts
        if (
            len(parts) >= 3
            and re.fullmatch(r"us(?:-[a-z0-9]+)*", parts[0])
            and parts[1] in RULESPEC_ATOMIC_ROOTS
            and path.endswith(".yml")
        ):
            raise ValueError(f"legacy .yml RuleSpec module is unsupported: {path}")
        if (
            len(parts) < 3
            or re.fullmatch(r"us(?:-[a-z0-9]+)*", parts[0]) is None
            or parts[1] not in RULESPEC_ATOMIC_ROOTS
            or not path.endswith(".yaml")
            or path.endswith(".test.yaml")
            or SKIP_DIRS.search(path)
        ):
            continue
        rule_files.append(path)

    manifest_index = build_manifest_index(repo, ref, tree)
    coverage = json.loads(args.coverage.read_text())
    surfaces = build_surface_index(coverage)

    file_blobs = batch_blobs(repo, ref, rule_files)

    rules_out: list[dict] = []
    unclassified_files: list[str] = []
    surface_rollup: dict[tuple, dict] = defaultdict(
        lambda: {"rules": 0, "grounded": 0, "manifest_backed": 0}
    )

    for path in rule_files:
        raw = file_blobs.get(path)
        if raw is None:
            continue
        try:
            doc = yaml.safe_load(raw)
        except yaml.YAMLError:
            continue
        if not isinstance(doc, dict):
            continue
        rules = doc.get("rules")
        if not isinstance(rules, list) or not rules:
            continue

        module = doc.get("module") or {}
        module_citation = (module.get("source_verification") or {}).get(
            "corpus_citation_path"
        )

        hit = classify(path)
        if hit is None:
            unclassified_files.append(path)
            family, jurisdiction = None, None
            surface = None
        else:
            family, jurisdiction = hit
            surface = surfaces.get((family, jurisdiction))

        surface_status = surface["status"] if surface else None
        surface_oracle = surface_status in ORACLE_STATUSES
        surface_executable = surface_status in STRICT_EXECUTABLE

        # Manifest provenance: signed record whose sha still matches the file.
        man = manifest_index.get(path)
        has_manifest = bool(man)
        manifest_signed = bool(man and man["signed"])
        pin_matches = bool(
            man
            and man["signed"]
            and man.get("sha256") == hashlib.sha256(raw).hexdigest()
        )

        rollup_key = (family, jurisdiction)

        for rule in rules:
            if not isinstance(rule, dict) or "name" not in rule:
                continue
            grounding = rule_grounding(rule, module_citation)
            record = {
                "module_path": path,
                "name": rule["name"],
                "kind": rule.get("kind"),
                "dtype": rule.get("dtype"),
                "family": family,
                "jurisdiction": jurisdiction,
                # grounding (genuine per-rule signals)
                "grounded": grounding["grounded"],
                "has_proof_atoms": grounding["has_proof_atoms"],
                "span_anchored": grounding["span_anchored"],
                "has_source_citation": grounding["has_source_citation"],
                "has_module_citation": grounding["has_module_citation"],
                # manifest provenance (per-file, inherited by its rules)
                "manifest_present": has_manifest,
                "manifest_signed": manifest_signed,
                "manifest_backed": pin_matches,
                # oracle coverage (SURFACE-level context, not per-rule proof)
                "surface_status": surface_status,
                "surface_oracle": surface_oracle,
                "surface_executable": surface_executable,
            }
            rules_out.append(record)

            r = surface_rollup[rollup_key]
            r["rules"] += 1
            if grounding["grounded"]:
                r["grounded"] += 1
            if pin_matches:
                r["manifest_backed"] += 1

    # ── surface-grain oracle KPI (the number the plan names) ──────────────
    all_surfaces = sorted(
        surfaces.values(), key=lambda s: (s["family"], s["jurisdiction"] or "")
    )
    surface_status_counts: dict[str, int] = defaultdict(int)
    for s in all_surfaces:
        surface_status_counts[s["status"]] += 1
    n_surfaces = len(all_surfaces)
    n_executable = sum(surface_status_counts.get(k, 0) for k in STRICT_EXECUTABLE)
    n_any_oracle = sum(surface_status_counts.get(k, 0) for k in ORACLE_STATUSES)

    total_rules = len(rules_out)

    def pct(num: int, den: int) -> float:
        return round(100.0 * num / den, 1) if den else 0.0

    grounded_rules = sum(1 for r in rules_out if r["grounded"])
    manifest_rules = sum(1 for r in rules_out if r["manifest_backed"])
    surface_oracle_rules = sum(1 for r in rules_out if r["surface_oracle"])
    surface_exec_rules = sum(1 for r in rules_out if r["surface_executable"])

    # By jurisdiction.
    by_jur: dict[str, dict] = defaultdict(
        lambda: {
            "rules": 0,
            "grounded": 0,
            "manifest_backed": 0,
            "surface_oracle": 0,
            "surface_executable": 0,
        }
    )
    for r in rules_out:
        j = r["jurisdiction"] or "unclassified"
        b = by_jur[j]
        b["rules"] += 1
        b["grounded"] += r["grounded"]
        b["manifest_backed"] += r["manifest_backed"]
        b["surface_oracle"] += r["surface_oracle"]
        b["surface_executable"] += r["surface_executable"]

    jurisdictions = []
    for j, b in sorted(by_jur.items(), key=lambda kv: -kv[1]["rules"]):
        jurisdictions.append(
            {
                "jurisdiction": j,
                "rules": b["rules"],
                "grounded": b["grounded"],
                "grounded_pct": pct(b["grounded"], b["rules"]),
                "manifest_backed": b["manifest_backed"],
                "manifest_backed_pct": pct(b["manifest_backed"], b["rules"]),
                "surface_oracle": b["surface_oracle"],
                "surface_oracle_pct": pct(b["surface_oracle"], b["rules"]),
                "surface_executable": b["surface_executable"],
                "surface_executable_pct": pct(b["surface_executable"], b["rules"]),
            }
        )

    # By program family (national roll-up across jurisdictions).
    by_family: dict[str, dict] = defaultdict(
        lambda: {"rules": 0, "grounded": 0, "manifest_backed": 0, "surface_oracle": 0}
    )
    for r in rules_out:
        f = r["family"] or "unclassified"
        b = by_family[f]
        b["rules"] += 1
        b["grounded"] += r["grounded"]
        b["manifest_backed"] += r["manifest_backed"]
        b["surface_oracle"] += r["surface_oracle"]
    families = [
        {
            "family": f,
            "rules": b["rules"],
            "grounded_pct": pct(b["grounded"], b["rules"]),
            "manifest_backed_pct": pct(b["manifest_backed"], b["rules"]),
            "surface_oracle_pct": pct(b["surface_oracle"], b["rules"]),
        }
        for f, b in sorted(by_family.items(), key=lambda kv: -kv[1]["rules"])
    ]

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    provenance = {
        "generated_at": generated_at,
        "rulespec_ref": ref,
        "rulespec_commit": commit,
        "coverage_overview_sha256": hashlib.sha256(
            args.coverage.read_bytes()
        ).hexdigest(),
        "generator": "scripts/rule_verification.py",
    }

    summary = {
        "_comment": (
            "KPI for Phase-A item A7. Generated by scripts/rule_verification.py "
            "from a pinned rulespec-us ref joined against "
            "coverage_overview.json. Grounding and manifest provenance are true "
            "per-rule signals. Oracle coverage is reported at the SURFACE grain "
            "(the number the plan tracks: executable surfaces / total surfaces); "
            "the per-rule surface_oracle_pct is a lower-bound context signal "
            "('this rule's program surface is exercised by a live comparison'), "
            "NOT a claim that each rule is individually verified."
        ),
        "provenance": provenance,
        "rules": {
            "total": total_rules,
            "grounded": grounded_rules,
            "grounded_pct": pct(grounded_rules, total_rules),
            "manifest_backed": manifest_rules,
            "manifest_backed_pct": pct(manifest_rules, total_rules),
            "on_oracle_surface": surface_oracle_rules,
            "on_oracle_surface_pct": pct(surface_oracle_rules, total_rules),
            "on_executable_surface": surface_exec_rules,
            "on_executable_surface_pct": pct(surface_exec_rules, total_rules),
        },
        "surfaces": {
            "total": n_surfaces,
            "executable": n_executable,
            "executable_pct": pct(n_executable, n_surfaces),
            "any_oracle": n_any_oracle,
            "any_oracle_pct": pct(n_any_oracle, n_surfaces),
            "coverage_only": surface_status_counts.get("coverageOnly", 0),
            "by_status": dict(sorted(surface_status_counts.items())),
        },
        "by_jurisdiction": jurisdictions,
        "by_family": families,
        "unclassified_files": len(unclassified_files),
    }

    full = {
        "_comment": (
            "Per-rule verification join generated by "
            "scripts/rule_verification.py. Each rule row carries genuine "
            "per-rule grounding + manifest-provenance flags and a SURFACE-level "
            "oracle-coverage flag (surface_oracle / surface_executable) sourced "
            "from coverage_overview.json. surface_oracle means the rule's "
            "program surface is exercised by a live comparison; it is a lower "
            "bound on verification, not a per-rule proof. See "
            "rule_verification_summary.json for the tracked KPI."
        ),
        "provenance": provenance,
        "summary": summary["rules"] | {"surfaces": summary["surfaces"]},
        "surface_rollup": [
            {
                "family": fam,
                "jurisdiction": jur,
                "status": (surfaces.get((fam, jur)) or {}).get(
                    "status", "coverageOnly" if fam else None
                ),
                "rules": v["rules"],
                "grounded": v["grounded"],
                "manifest_backed": v["manifest_backed"],
            }
            for (fam, jur), v in sorted(
                surface_rollup.items(),
                key=lambda kv: (kv[0][0] or "~", kv[0][1] or ""),
            )
        ],
        "unclassified_files": sorted(unclassified_files),
        "rules": rules_out,
    }

    OUT_FULL.write_text(json.dumps(full, indent=1) + "\n")
    OUT_SUMMARY.write_text(json.dumps(summary, indent=1) + "\n")

    # ── console report (mirrors sibling scripts' style) ───────────────────
    print(f"rulespec-us @ {ref} ({commit[:12]})")
    print(f"  {total_rules} rules across {len(rule_files)} files")
    print(
        f"  grounded:        {grounded_rules:6} ({summary['rules']['grounded_pct']}%)"
    )
    print(
        f"  manifest-backed: {manifest_rules:6} "
        f"({summary['rules']['manifest_backed_pct']}%)"
    )
    print(
        f"  surfaces:        {n_executable}/{n_surfaces} executable "
        f"({summary['surfaces']['executable_pct']}%), "
        f"{n_any_oracle}/{n_surfaces} any-oracle "
        f"({summary['surfaces']['any_oracle_pct']}%)"
    )
    print(
        f"  rules on an oracle surface: {surface_oracle_rules} "
        f"({summary['rules']['on_oracle_surface_pct']}%) "
        "[surface-level lower bound, not per-rule proof]"
    )
    if unclassified_files:
        print(f"  unclassified files: {len(unclassified_files)}")
    print(f"wrote {OUT_FULL.relative_to(REPO_ROOT)}")
    print(f"wrote {OUT_SUMMARY.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
