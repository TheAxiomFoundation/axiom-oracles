"""Tracked docs never publish a contributor's home-directory path.

Invariants:

1. No line of a git-tracked ``docs/**/*.md`` file or the root ``README.md``
   holds a macOS (``/Users/<name>``) or Linux (``/home/<name>``) home path.
   Docs name a repo-relative path (``data/corpus``) or a placeholder
   (``<policyengine-uk checkout>``) instead.
2. The scanner reports every such path, on its own line and column, when the
   path starts its token: at the start of a line or after a space or
   punctuation (quotes, backticks, brackets, ``|``, ``=``, ``:``, ``*``,
   ``_``), after option flags (``-I/Users/...``, ``-C/Users/...``), with JSON-escaped
   separators (``\\/Users\\/...``), and in ``file:///Users/...`` URLs.
3. It ignores the same text inside other URLs (``https://host/Users/...``,
   ``https://[::1]/home/...``, ``https://host/#/home/...``), in relative paths
   (``data/home/jane/``, ``example.com/Users/jane``), the bare word
   ``/Users/``, and placeholder names (``/Users/<you>/``, ``/Users/$USER/``,
   ``/Users/.../``).

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

# Any scheme but file:, so a file:///Users/... URL is still scanned.
_URL = re.compile(r"\b(?!file:)[A-Za-z][A-Za-z0-9+.-]*://[^\s<>\"'`]*")
_HOME_PATH = re.compile(
    r"\\?/(?:Users|home)\\?/(?P<name>[^\s/\\<>`'\"()\[\]{}$%*|,;:=]+)"
)
# Characters that end the token in front of a path. A path whose token holds
# nothing before it, only slashes (file:///), or an option flag is absolute.
_DELIMITERS = frozenset("`'\"()[]{}<>|,;:=*_!?&")
_OPTION_FLAG = re.compile(r"-{1,2}[A-Za-z][\w-]*")


def tracked_docs(root: Path) -> list[str]:
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--", "docs", "README.md"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8")
    return sorted(path for path in listed.split("\0") if path.endswith(".md"))


def _starts_absolute_path(line: str, start: int) -> bool:
    token_start = start
    while token_start and not (
        line[token_start - 1].isspace() or line[token_start - 1] in _DELIMITERS
    ):
        token_start -= 1
    prefix = line[token_start:start]
    return not prefix.strip("/") or _OPTION_FLAG.fullmatch(prefix) is not None


def home_path_hits(text: str) -> list[tuple[int, int]]:
    """``(line, column)`` of each home path, both 1-based, lines split on ``\\n``."""
    hits = []
    for number, line in enumerate(text.split("\n"), start=1):
        # Blank URLs out at equal length, so columns still index the line.
        masked = _URL.sub(lambda url: " " * len(url.group()), line)
        for match in _HOME_PATH.finditer(masked):
            if any(char.isalnum() for char in match["name"]) and _starts_absolute_path(
                masked, match.start()
            ):
                hits.append((number, match.start() + 1))
    return hits


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
        "PYTHONPATH=src:/Users/jane/lib",
        "the HTML at file:///Users/jane/staging/page.html",
        "(checked out at /home/runner/work/repo)",
        "/Users/jane",
        "cd /home/jane",
        "| /home/jane | checkout |",
        "|/home/jane|",
        "_/Users/jane/checkout_ and */home/jane/x*",
        "cc -I/Users/jane/checkout/include main.c",
        "tar -C/Users/jane/repo -tf archive.tar",
        '{"path": "\\/Users\\/jane\\/repo"}',
        "/Users/Jane Doe/repo and /home/Jane Doe/repo",
        "/Users/jöran/repo",
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
        "https://[2001:db8::1]/Users/jane/profile",
        "https://[::1]/home/jane/profile",
        "https://example.org/#/home/jane/profile",
        "https://example.org//Users/jane/profile",
        "see (https://example.org/Users/jane) for the route",
        "--base <axiom-corpus checkout>/data/corpus",
        "--source-dir <download dir>",
        "default `~/.axiom/corpus-cache`",
        "/Users/<you>/axiom-corpus and /Users/$USER/axiom-corpus",
        "/Users/%USER%/axiom-corpus and /Users/.../axiom-corpus and /Users/*/x",
        "data/home/jane/ and /homepage/jane/ and example.com/Users/jane",
        "../home/jane/ and $HOME/Users/jane",
    ],
)
def test_non_path_is_not_reported(line: str) -> None:
    assert not home_path_hits(line), line


_NAMES = st.from_regex(r"[A-Za-z0-9][A-Za-z0-9._-]{0,19}", fullmatch=True)
# Filler holds no slash, so it can neither start nor extend a path or a URL.
_FILLER = st.text(
    alphabet=st.characters(blacklist_characters="/\n", blacklist_categories=("Cs",)),
    max_size=40,
)
_LEADS = [
    "",
    " ",
    "`",
    '"',
    "'",
    "(",
    "[",
    "|",
    "=",
    ":",
    "*",
    "_",
    "file://",
    "-I",
    "--root=",
]


@given(
    root=st.sampled_from(["Users", "home"]),
    name=_NAMES,
    lead=st.sampled_from(_LEADS),
    escaped=st.booleans(),
    before=st.lists(_FILLER, max_size=5),
    rest=st.sampled_from(["", "/repo"]),
    tail=_FILLER,
)
def test_any_home_path_is_reported_on_its_line(
    root: str,
    name: str,
    lead: str,
    escaped: bool,
    before: list[str],
    rest: str,
    tail: str,
) -> None:
    slash = "\\/" if escaped else "/"
    path = f"{slash}{root}{slash}{name}{rest.replace('/', slash)}"
    text = "\n".join([*before, f"{lead}{path} {tail}"])
    assert home_path_hits(text) == [(len(before) + 1, len(lead) + 1)]


_HOSTS = st.one_of(
    st.from_regex(
        r"[a-z0-9]([a-z0-9-]{0,10}[a-z0-9])?(\.[a-z0-9]{1,10})+", fullmatch=True
    ),
    st.sampled_from(["[::1]", "[2001:db8::1]", "localhost:8080"]),
)


@given(
    scheme=st.sampled_from(["http", "https", "ftp", "ssh"]),
    host=_HOSTS,
    between=st.sampled_from(["", "/", "/#", "/app"]),
    root=st.sampled_from(["Users", "home"]),
    name=_NAMES,
)
def test_web_url_path_is_not_reported(
    scheme: str, host: str, between: str, root: str, name: str
) -> None:
    assert home_path_hits(f"{scheme}://{host}{between}/{root}/{name}/") == []


@given(
    segment=st.from_regex(r"[A-Za-z0-9][A-Za-z0-9.-]{0,15}", fullmatch=True),
    root=st.sampled_from(["Users", "home"]),
    name=_NAMES,
)
def test_relative_path_is_not_reported(segment: str, root: str, name: str) -> None:
    assert home_path_hits(f"see {segment}/{root}/{name}/x") == []
