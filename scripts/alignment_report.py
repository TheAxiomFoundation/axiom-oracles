#!/usr/bin/env python3
"""Report-only oracle alignment for a candidate rulespec-us change.

Prints and writes a JSON report with the reach of the change (which
``programs/**.yaml`` files have a compared output that depends on it), the
comparison suites expected to cover it, and one status. It gates nothing: the
exit code is 0 for every completed derivation and 2 when the derivation
failed (``status: error``).

Two ways to name the two trees:

    # two existing checkouts, each a directory named rulespec-us
    scripts/alignment_report.py --base-root B/rulespec-us --candidate-root C/rulespec-us

    # one repository and two revisions; clones are made under --work-dir
    scripts/alignment_report.py --rulespec-repo ~/rulespec-us --base main --candidate pr-head

The changed files are always derived from the two commits. ``--changed`` is a
cross-check: the listed files must be exactly that set, or the run is an
error. Both trees must be clean, complete git checkouts.

``--execute`` runs each runnable expected suite on both trees through
``scripts/run_comparison.py --require-live``. ``--reports-dir`` reads
already-produced reports from ``<dir>/{base,candidate}/<suite>.json`` instead;
``<dir>/manifest.json`` must bind them to this registry commit and these two
rulespec-us commits (see docs/alignment-report.md).
Without either, a change with a runnable expected suite reports
``reference_not_executed``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axiom_oracles.alignment import (  # noqa: E402
    AlignmentError,
    AlignmentInputs,
    CompileCache,
    ComposeEngineCompiler,
    ReportsDirExecutor,
    RunComparisonExecutor,
    build_report,
    exit_code,
    git_dirty,
    git_head,
    materialize_checkout,
    sha256_file,
    temporary_work_dir,
)


class FixtureCompiler:
    """Read compiled artifacts from ``<dir>/<side>/<program path>.json``.

    For synthetic fixtures and for artifacts compiled elsewhere; the report's
    toolchain block records that the programs were not compiled in this run.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)

    def compile(self, program, side: str):
        path = self.directory / side / program.origin / f"{program.relpath}.json"
        try:
            return json.loads(path.read_text())
        except FileNotFoundError as exc:
            raise AlignmentError(
                "program_compile_failed", f"no compiled artifact for {program.key} ({side})"
            ) from exc
        except (OSError, ValueError) as exc:
            raise AlignmentError(
                "program_compile_failed", f"artifact for {program.key} ({side}): {exc}"
            ) from exc


def compose_identity(binary: Path) -> dict[str, str | None]:
    """What identifies an ``axiom-compose`` install: the launcher's bytes do
    not change with the package, so the installed package is named too."""
    identity: dict[str, str | None] = {"launcher_sha256": sha256_file(binary)}
    venv = binary.resolve().parent.parent if binary.exists() else None
    if venv is None:
        return identity
    source = git_head(venv.parent)
    if source is not None:
        identity["source_commit"] = source
        identity["source_dirty"] = str(git_dirty(venv.parent))
    records = sorted(venv.glob("lib/python*/site-packages/axiom_compose*.dist-info/RECORD"))
    if records:
        identity["dist_record_sha256"] = sha256_file(records[0])
    return identity


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base-root", type=Path, help="rulespec-us tree at the base commit")
    parser.add_argument(
        "--candidate-root", type=Path, help="rulespec-us tree at the candidate commit"
    )
    parser.add_argument("--rulespec-repo", type=Path, help="rulespec-us repository to clone from")
    parser.add_argument("--base", help="base revision (with --rulespec-repo)")
    parser.add_argument("--candidate", help="candidate revision (with --rulespec-repo)")
    parser.add_argument(
        "--changed",
        action="append",
        default=None,
        metavar="PATH",
        help=(
            "changed file relative to the rulespec root; repeatable. The list is "
            "checked against the tree diff and must equal it"
        ),
    )
    parser.add_argument(
        "--registry-root",
        type=Path,
        default=REPO_ROOT,
        help="axiom-oracles checkout whose suite registry is read (default: this one)",
    )
    parser.add_argument(
        "--compose-binary",
        type=Path,
        default=Path(os.path.expanduser("~/axiom-compose/.venv/bin/axiom-compose")),
    )
    parser.add_argument(
        "--engine-binary",
        type=Path,
        default=Path(
            os.path.expanduser("~/axiom-rules-engine/target/release/axiom-rules-engine")
        ),
    )
    parser.add_argument(
        "--compiled-dir",
        type=Path,
        help="read compiled artifacts from this directory instead of compiling",
    )
    parser.add_argument(
        "--no-registry-programs",
        action="store_true",
        help="compile only the rulespec tree's programs, not this repository's programs/",
    )
    parser.add_argument("--execute", action="store_true", help="run the runnable expected suites")
    parser.add_argument("--reports-dir", type=Path, help="read suite reports instead of running")
    parser.add_argument("--work-dir", type=Path, help="scratch directory (default: a temp dir)")
    parser.add_argument("--keep-work-dir", action="store_true")
    parser.add_argument(
        "--cache-dir",
        type=Path,
        help="keep compiled artifacts here, keyed by the bytes of their inputs and the toolchain",
    )
    parser.add_argument(
        "--recompile-all",
        action="store_true",
        help="compile every program on both sides; reuse nothing",
    )
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    parser.add_argument("--compile-timeout", type=float, default=600.0)
    parser.add_argument("--suite-timeout", type=float, default=3600.0)
    parser.add_argument("--output", type=Path, help="write the JSON report here")
    parser.add_argument("--quiet", action="store_true", help="do not print the report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    started = time.monotonic()
    if args.execute and args.reports_dir:
        print("--execute and --reports-dir are exclusive", file=sys.stderr)
        return 2
    by_roots = args.base_root is not None and args.candidate_root is not None
    by_revisions = bool(args.rulespec_repo and args.base and args.candidate)
    if by_roots == by_revisions:
        print(
            "give either --base-root and --candidate-root, or --rulespec-repo "
            "with --base and --candidate",
            file=sys.stderr,
        )
        return 2

    created_work_dir = args.work_dir is None
    work_dir = temporary_work_dir() if created_work_dir else args.work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    setup_error: AlignmentError | None = None
    base_root = candidate_root = work_dir
    try:
        if by_revisions:
            base_root = work_dir / "base" / "rulespec-us"
            candidate_root = work_dir / "candidate" / "rulespec-us"
            materialize_checkout(args.rulespec_repo, args.base, base_root)
            materialize_checkout(args.rulespec_repo, args.candidate, candidate_root)
        else:
            base_root = args.base_root.resolve()
            candidate_root = args.candidate_root.resolve()
    except AlignmentError as exc:
        setup_error = exc

    if args.compiled_dir is not None:
        compiler = FixtureCompiler(args.compiled_dir)
        toolchain = {"compiler": "precompiled_artifacts"}
    else:
        compiler = ComposeEngineCompiler(
            roots={"base": base_root, "candidate": candidate_root},
            compose_binary=args.compose_binary,
            engine_binary=args.engine_binary,
            work_dir=work_dir,
            timeout=args.compile_timeout,
            cwd=args.registry_root,
        )
        toolchain = {
            "compiler": "axiom-compose+axiom-rules-engine",
            "compose": compose_identity(args.compose_binary),
            "engine_binary_sha256": sha256_file(args.engine_binary),
        }

    executor = None
    if args.reports_dir is not None:
        executor = ReportsDirExecutor(args.reports_dir)
        toolchain["suite_reports"] = "supplied"
    elif args.execute:
        executor = RunComparisonExecutor(
            registry_root=args.registry_root,
            homes={"base": base_root.parent, "candidate": candidate_root.parent},
            output_dir=work_dir / "suite-runs",
            timeout=args.suite_timeout,
        )
        toolchain["suite_reports"] = "scripts/run_comparison.py --require-live"

    # An artifact kept across reports is only as good as the name of the
    # toolchain that made it. An axiom-compose installed from a source tree
    # with uncommitted changes has no such name, so nothing is kept.
    cache_dir = args.cache_dir
    compose = toolchain.get("compose")
    if cache_dir is not None and isinstance(compose, dict):
        if compose.get("source_commit"):
            named = compose.get("source_dirty") == "False"
        else:
            named = bool(compose.get("dist_record_sha256"))
        if not named:
            cache_dir = None
            toolchain["cache"] = "disabled: the axiom-compose install has no stable identity"
    inputs = AlignmentInputs(
        base_root=base_root,
        candidate_root=candidate_root,
        registry_root=args.registry_root,
        compiler=compiler,
        changed=args.changed,
        executor=executor,
        include_registry_programs=not args.no_registry_programs,
        jobs=args.jobs,
        reuse_unchanged_programs=not args.recompile_all,
        cache=CompileCache(
            cache_dir,
            salt=json.dumps(
                {k: v for k, v in toolchain.items() if k != "suite_reports"}, sort_keys=True
            ),
        ),
        toolchain=toolchain,
    )
    if setup_error is None and isinstance(compiler, ComposeEngineCompiler):
        try:
            compiler.prepare()
        except AlignmentError as exc:
            setup_error = exc
    if setup_error is not None:
        report = {
            "schema": "axiom_oracles.alignment_report.v1",
            "report_only": True,
            "status": "error",
            "error": {"cause": setup_error.cause, "detail": setup_error.detail},
        }
    else:
        report = build_report(inputs)
    if isinstance(compiler, ComposeEngineCompiler):
        compiler.close()
    report["runtime_seconds"] = round(time.monotonic() - started, 1)

    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    if not args.quiet:
        sys.stdout.write(text)
    if created_work_dir and not args.keep_work_dir:
        shutil.rmtree(work_dir, ignore_errors=True)
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
