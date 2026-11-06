#!/usr/bin/env python3
"""Open a draft PR from validated updater data; never execute candidate code."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.update_policyengine_defaults import validate_proposal  # noqa: E402

MANIFEST = Path("data/policyengine_defaults.json")
LOCK = Path("requirements/policyengine-defaults.txt")
REPORT = Path("docs/generated/policyengine-defaults-update.md")
ALLOWED_PATHS = (MANIFEST, LOCK, REPORT)
BRANCH_PREFIX = "automation/policyengine-us-"
REPOSITORY = "TheAxiomFoundation/axiom-oracles"
_PIN = re.compile(r"([a-zA-Z0-9][a-zA-Z0-9._-]*)==([0-9][a-zA-Z0-9.!+_-]*)")
_HASH = re.compile(r"--hash=sha256:[0-9a-f]{64}")


def run(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=check)


def read_artifact(path: Path, limit: int) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError(
            f"missing, non-regular, or oversized proposal file: {path.name}"
        )
    return path.read_bytes()


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate proposal field: {key}")
        result[key] = value
    return result


def validate_lock(raw: bytes, proposal: dict) -> str:
    """Accept only hashed exact PyPI requirements, never install flags or URLs."""
    if hashlib.sha256(raw).hexdigest() != proposal["candidate_lock_sha256"]:
        raise ValueError(
            "candidate-requirements.txt does not match its recorded SHA-256"
        )
    text = raw.decode("utf-8")
    packages = {}
    current = None
    hashed = False
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removesuffix("\\").rstrip()
        pin = _PIN.fullmatch(line)
        if pin:
            if current is not None and not hashed:
                raise ValueError(f"lock requirement has no SHA-256: {current}")
            current = pin[1].lower().replace("_", "-").replace(".", "-")
            if current in packages:
                raise ValueError(f"duplicate lock requirement: {current}")
            packages[current] = pin[2]
            hashed = False
        elif current is not None and _HASH.fullmatch(line):
            hashed = True
        else:
            raise ValueError(
                "lock permits only exact name==version pins and SHA-256 hashes"
            )
    if current is None or not hashed:
        raise ValueError("lock must contain hashed package requirements")
    for name, version in proposal["candidate"]["packages"].items():
        if packages.get(name) != version:
            raise ValueError(
                f"candidate lock disagrees with the proposed {name} version"
            )
    return text


def render_report(proposal: dict) -> str:
    """Render a review summary from validated JSON, not artifact Markdown."""
    lines = [
        "# Proposed PolicyEngine US default update",
        "",
        f"Probe status: **{proposal['status']}**.",
        "",
        "| Package | Reviewed default | Candidate |",
        "| --- | --- | --- |",
    ]
    for name, version in proposal["candidate"]["packages"].items():
        lines.append(
            f"| {name} | {proposal['baseline']['packages'][name]} | {version} |"
        )
    lines.extend(
        [
            "",
            "This proposal changes the generic default environment only. Explicit historical",
            "suite versions remain unchanged. Expected outputs, dispositions, and published",
            "comparison reports are not rewritten. This PR requires human review and merge.",
            "",
            f"Base commit: `{proposal['base_commit']}`.",
            f"Fixture SHA-256: `{proposal['fixture_sha256']}`.",
            f"Candidate lock SHA-256: `{proposal['candidate_lock_sha256']}`.",
            "",
            "## Comparison evidence",
            "",
            "```json",
            json.dumps(
                {
                    key: proposal[key]
                    for key in (
                        "baseline_result",
                        "candidate_result",
                        "changes",
                        "limitations",
                    )
                },
                indent=2,
                ensure_ascii=True,
            ).replace("`", "\\u0060"),
            "```",
            "",
            "The bounded probe does not establish parity for every default-consuming suite.",
            "Review the changed amounts and run affected comparisons before merging.",
        ]
    )
    return "\n".join(lines) + "\n"


def publish(proposal_dir: Path, *, repo_dir: Path = ROOT) -> str | None:
    proposal = validate_proposal(
        json.loads(
            read_artifact(proposal_dir / "proposal.json", 262144),
            object_pairs_hook=unique_object,
        )
    )
    if proposal["status"] not in {"passed", "needs-review"}:
        print(f"No update PR: probe status is {proposal['status']}.")
        return None
    if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
        raise ValueError(f"publisher requires GITHUB_REPOSITORY={REPOSITORY}")
    default_branch = os.environ.get("DEFAULT_BRANCH", "")
    if (
        not default_branch
        or os.environ.get("GITHUB_REF") != f"refs/heads/{default_branch}"
    ):
        raise ValueError("publication is restricted to the repository default branch")
    head = run("git", "rev-parse", "HEAD", cwd=repo_dir).stdout.strip()
    if head != proposal["base_commit"] or head != os.environ.get("GITHUB_SHA"):
        raise ValueError("proposal base does not match the trusted workflow checkout")
    if run("git", "status", "--porcelain", cwd=repo_dir).stdout.strip():
        raise ValueError("publication requires a clean trusted checkout")
    current = json.loads((repo_dir / MANIFEST).read_text())
    if current != proposal["baseline"]:
        raise ValueError("reviewed defaults changed since this proposal was measured")
    lock = validate_lock(
        read_artifact(proposal_dir / "candidate-requirements.txt", 2097152), proposal
    )
    prs = json.loads(
        run(
            "gh",
            "pr",
            "list",
            "--repo",
            REPOSITORY,
            "--state",
            "open",
            "--limit",
            "1000",
            "--json",
            "headRefName,url",
            cwd=repo_dir,
        ).stdout
    )
    existing = next(
        (p for p in prs if p["headRefName"].startswith(BRANCH_PREFIX)), None
    )
    if existing:
        print(f"An update PR already awaits review: {existing['url']}")
        return None
    version = proposal["candidate"]["packages"]["policyengine-us"]
    if not re.fullmatch(r"(?:[0-9]+!)?[0-9]+(?:\.[0-9]+)*(?:\.post[0-9]+)?", version):
        raise ValueError("automation branch requires a canonical stable model version")
    branch = BRANCH_PREFIX + version
    found = run(
        "git",
        "ls-remote",
        "--exit-code",
        "--heads",
        "origin",
        f"refs/heads/{branch}",
        cwd=repo_dir,
        check=False,
    )
    if found.returncode == 0:
        print(f"Branch {branch} already exists; leaving it untouched.")
        return None
    if found.returncode != 2:
        raise ValueError("could not check whether the automation branch already exists")
    report = render_report(proposal)
    run("git", "checkout", "-b", branch, cwd=repo_dir)
    for path, content in (
        (MANIFEST, json.dumps(proposal["candidate"], indent=2) + "\n"),
        (LOCK, lock),
        (REPORT, report),
    ):
        (repo_dir / path).parent.mkdir(parents=True, exist_ok=True)
        (repo_dir / path).write_text(content)
    run("git", "add", "--", *(str(p) for p in ALLOWED_PATHS), cwd=repo_dir)
    staged = set(
        run("git", "diff", "--cached", "--name-only", cwd=repo_dir).stdout.splitlines()
    )
    if not staged or not staged <= {str(p) for p in ALLOWED_PATHS}:
        raise ValueError("publication diff contains files outside the update allowlist")
    run(
        "git",
        "-c",
        "user.name=github-actions[bot]",
        "-c",
        "user.email=41898282+github-actions[bot]@users.noreply.github.com",
        "commit",
        "-m",
        f"Propose PolicyEngine US {version} defaults",
        cwd=repo_dir,
    )
    # Creating the ref is atomic: a concurrently created branch is refused,
    # rather than becoming a fast-forward target of our push.
    run(
        "gh",
        "api",
        "--method",
        "POST",
        f"repos/{REPOSITORY}/git/refs",
        "-f",
        f"ref=refs/heads/{branch}",
        "-f",
        f"sha={head}",
        cwd=repo_dir,
    )
    run("gh", "auth", "setup-git", cwd=repo_dir)
    run("git", "push", "origin", f"HEAD:refs/heads/{branch}", cwd=repo_dir)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md") as body:
        body.write(report)
        body.flush()
        url = run(
            "gh",
            "pr",
            "create",
            "--repo",
            REPOSITORY,
            "--draft",
            "--base",
            default_branch,
            "--head",
            branch,
            "--title",
            f"Propose PolicyEngine US {version} defaults",
            "--body-file",
            body.name,
            cwd=repo_dir,
        ).stdout.strip()
    print(url)
    return url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        publish(args.proposal_dir)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        detail = (
            exc.stderr.strip()
            if isinstance(exc, subprocess.CalledProcessError)
            else str(exc)
        )
        print(
            f"PolicyEngine update publication failed: {detail[:2000]}", file=sys.stderr
        )
        print(
            "If GitHub refuses PR creation, enable Actions to create pull requests in repository settings.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
