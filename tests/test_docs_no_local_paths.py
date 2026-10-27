"""Tracked docs never publish a contributor's home-directory path.

Invariants:

1. No line of a git-tracked ``docs/**/*.md`` file or the root ``README.md``
   holds a macOS (``/Users/<name>``) or Linux (``/home/<name>/``) home path.
   Docs name a repo-relative path (``data/corpus``) or a placeholder
   (``<policyengine-uk checkout>``) instead.
2. The scanner reports every such path, on its own line number, wherever it
   starts a path: after a space, quote, backtick, parenthesis or ``=``, and in
   ``file:///Users/...`` URLs. It ignores the same text inside a web URL
   (``https://host/Users/...``), the bare word ``/Users/``, and placeholder
   names (``/Users/<you>/``, ``/Users/$USER/``).

Failures name ``file:line:column`` only, so the CI log does not republish the
path.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parents[1]

# A path starts where the preceding character cannot continue a URL host or a
# word, so `example.com/Users/x` is not a path and `file:///Users/x` is.
_NAME = r"[^\s/<>`'\"()\[\]{}$*]+"
HOME_PATH = re.compile(rf"(?<![\w.-])/(?:Users/{_NAME}|home/{_NAME}/)")


def tracked_docs(root: Path) -> list[str]:
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--", "docs", "README.md"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8")
    return sorted(path for path in listed.split("\0") if path.endswith(".md"))


def home_path_hits(text: str) -> list[tuple[int, int]]:
    """``(line, column)`` of each home path, both 1-based, lines split on ``\\n``."""
    return [
        (number, match.start() + 1)
        for number, line in enumerate(text.split("\n"), start=1)
        for match in HOME_PATH.finditer(line)
    ]


def test_tracked_docs_have_no_home_paths() -> None:
    docs = tracked_docs(REPO_ROOT)
    assert "README.md" in docs
    offenders = [
        f"{path}:{line}:{column}"
        for path in docs
        for line, column in home_path_hits(
            (REPO_ROOT / path).read_text(encoding="utf-8", errors="replace")
        )
    ]
    assert not offenders, (
        "Docs carry absolute home-directory paths; use a repo-relative path or a "
        "placeholder such as <checkout> or <download dir>:\n" + "\n".join(offenders)
    )


@pytest.mark.parametrize(
    "line",
    [
        "--base /Users/jane/axiom-oracles/data \\",
        "worktree `/Users/jane.doe/worktrees/w5`",
        'base = Path("/Users/jane/axiom-corpus/data/corpus")',
        "B=/Users/jane/axiom-corpus/data/corpus",
        "the HTML at file:///Users/jane/staging/page.html",
        "(checked out at /home/runner/work/repo)",
        "/Users/jane",
    ],
)
def test_home_path_is_reported(line: str) -> None:
    assert home_path_hits(line), line


@pytest.mark.parametrize(
    "line",
    [
        "the provisions carry no `file:` URL or `/Users/` path",
        "https://example.com/Users/jane/profile",
        "https://example.org/home/jane/",
        "--base <axiom-corpus checkout>/data/corpus",
        "--source-dir <download dir>",
        "default `~/.axiom/corpus-cache`",
        "/Users/<you>/axiom-corpus and /Users/$USER/axiom-corpus",
        "data/home/jane/ and /homepage/jane/",
    ],
)
def test_non_path_is_not_reported(line: str) -> None:
    assert not home_path_hits(line), line


_NAMES = st.from_regex(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,19}", fullmatch=True)
# Filler holds no slash, so it can neither start nor extend a path.
_FILLER = st.text(
    alphabet=st.characters(blacklist_characters="/\n", blacklist_categories=("Cs",)),
    max_size=40,
)


@given(
    root=st.sampled_from(["Users", "home"]),
    name=_NAMES,
    lead=st.sampled_from(["", " ", "`", '"', "'", "(", "=", "file://"]),
    before=st.lists(_FILLER, max_size=5),
    tail=_FILLER,
)
def test_any_home_path_is_reported_on_its_line(
    root: str, name: str, lead: str, before: list[str], tail: str
) -> None:
    text = "\n".join([*before, f"{lead}/{root}/{name}/repo{tail}"])
    assert home_path_hits(text) == [(len(before) + 1, len(lead) + 1)]


@given(
    host=st.from_regex(
        r"[a-z0-9]([a-z0-9-]{0,10}[a-z0-9])?(\.[a-z0-9]{1,10})+", fullmatch=True
    ),
    root=st.sampled_from(["Users", "home"]),
    name=_NAMES,
)
def test_web_url_path_is_not_reported(host: str, root: str, name: str) -> None:
    assert home_path_hits(f"https://{host}/{root}/{name}/") == []
