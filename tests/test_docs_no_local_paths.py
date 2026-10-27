"""Tracked docs never publish a contributor's home-directory path.

Invariants:

1. No line of a git-tracked ``docs/**/*.md`` file or the root ``README.md``
   holds a macOS (``/Users/<name>``) or Linux (``/home/<name>``) home path.
   Docs name a repo-relative path (``data/corpus``) or a placeholder
   (``<policyengine-uk checkout>``) instead.
2. The scanner reports every ``/Users/<name>`` or ``/home/<name>`` (also with
   JSON-escaped ``\\/`` separators) on its own line and column, except where
   it is not a home path:
   - inside a URL of any scheme but ``file:``. A URL ends at whitespace,
     ``|``, ``;``, a quote or backtick, ``<`` or ``>``, or an unbalanced ``)``
     or ``]``, so ``[site](https://host)|/home/<name>`` is still reported;
   - continuing a relative path: the text in front of it, back to the previous
     space or punctuation, is a path segment (``data/home/<name>``,
     ``host/Users/<name>``, ``/opt/x/home/<name>``, ``./home/<name>``). An
     option flag (``-I/Users/...``) or underscores (``_/Users/..._``) there
     are not segments, so those are reported;
   - naming no one: ``/Users/`` alone, ``/Users/<you>/``, ``/Users/$USER/``,
     ``/Users/.../``.
   ``file:`` URLs are scanned whatever their case or host
   (``FILE:///Users/...``, ``file://localhost/Users/...``).
   Percent-encoded separators (``%2FUsers%2F``) and Windows paths are outside
   this contract.

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

_CANDIDATE = re.compile(
    r"\\?/(?:Users|home)\\?/(?P<name>[^\s/\\<>`'\"()\[\]{}$%*|,;:=]+)"
)
_URL_START = re.compile(r"\b(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*)://")
_URL_END = frozenset("<>\"'`|;")
_FILE_URL_AUTHORITY = re.compile(r"(?i)\bfile://[^/\s]*\Z")
_OPTION_FLAG = re.compile(r"-{1,2}[A-Za-z][\w-]*")


def tracked_docs(root: Path) -> list[str]:
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--", "docs", "README.md"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8")
    return sorted(path for path in listed.split("\0") if path.endswith(".md"))


def _url_spans(line: str) -> list[tuple[int, int]]:
    """``[start, end)`` of each non-``file:`` URL; brackets nest, as in ``[::1]``."""
    spans: list[tuple[int, int]] = []
    for match in _URL_START.finditer(line):
        if match["scheme"].lower() == "file" or (
            spans and match.start() < spans[-1][1]
        ):
            continue
        end, depth = match.end(), 0
        while end < len(line):
            char = line[end]
            if char.isspace() or char in _URL_END:
                break
            if char in "([":
                depth += 1
            elif char in ")]":
                if not depth:
                    break
                depth -= 1
            end += 1
        spans.append((match.start(), end))
    return spans


def _is_path_segment_char(char: str) -> bool:
    return char.isalnum() or char in "._-"


def _starts_home_path(line: str, start: int) -> bool:
    if _FILE_URL_AUTHORITY.search(line, 0, start):
        return True
    slashes = start
    while slashes and line[slashes - 1] == "/":
        slashes -= 1
    segment_start = slashes
    while segment_start and _is_path_segment_char(line[segment_start - 1]):
        segment_start -= 1
    segment = line[segment_start:slashes]
    if not segment:
        return True
    if slashes < start or (segment_start and line[segment_start - 1] in "/\\"):
        return False
    if _OPTION_FLAG.fullmatch(segment):
        return True
    return not any(char.isalnum() for char in segment) and bool(segment.strip("."))


def home_path_hits(text: str) -> list[tuple[int, int]]:
    """``(line, column)`` of each home path, both 1-based, lines split on ``\\n``."""
    hits = []
    for number, line in enumerate(text.split("\n"), start=1):
        urls = _url_spans(line)
        for match in _CANDIDATE.finditer(line):
            start = match.start()
            if (
                any(char.isalnum() for char in match["name"])
                and not any(url_start <= start < url_end for url_start, url_end in urls)
                and _starts_home_path(line, start)
            ):
                hits.append((number, start + 1))
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
        "FILE:///Users/jane/repo and file://localhost/Users/jane/repo",
        "file:/Users/jane/repo",
        "(checked out at /home/runner/work/repo)",
        "/Users/jane",
        "cd /home/jane",
        "| /home/jane | checkout |",
        "|/home/jane|",
        "|[site](https://example.org)|/home/jane|",
        "curl https://example.org;/Users/jane/repo/bin/tool",
        "_/Users/jane/checkout_ and */home/jane/x*",
        "~~/Users/jane/repo~~",
        "cc @/Users/jane/options.rsp",
        "+/Users/jane/repo in a diff and ^/home/jane/ in a regex",
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
        "https://en.wikipedia.org/wiki/Home_(film)/home/jane",
        "see (https://example.org/Users/jane) for the route",
        "[site](https://example.org/Users/jane) and <https://example.org/home/jane/>",
        "--base <axiom-corpus checkout>/data/corpus",
        "--source-dir <download dir>",
        "default `~/.axiom/corpus-cache`",
        "/Users/<you>/axiom-corpus and /Users/$USER/axiom-corpus",
        "/Users/%USER%/axiom-corpus and /Users/.../axiom-corpus and /Users/*/x",
        "data/home/jane/ and /homepage/jane/ and example.com/Users/jane",
        "/opt/app/home/jane/ and ./home/jane and ../home/jane/ and $HOME/Users/jane",
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
    *[
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
        "~~",
        "@",
        "+",
        "^",
        "#",
    ],
    *["-I", "--root=", "file://", "FILE://", "file://localhost", "file:"],
    *["|[site](https://example.org)|", "curl https://example.org;"],
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
    scheme=st.sampled_from(["http", "https", "HTTPS", "ftp", "ssh"]),
    host=_HOSTS,
    between=st.sampled_from(["", "/", "/#", "/app", "/wiki/Home_(film)"]),
    root=st.sampled_from(["Users", "home"]),
    name=_NAMES,
    wrap=st.sampled_from(["{}", "[site]({})", "<{}>", "({}) and", "| {} |"]),
)
def test_web_url_path_is_not_reported(
    scheme: str, host: str, between: str, root: str, name: str, wrap: str
) -> None:
    url = f"{scheme}://{host}{between}/{root}/{name}/"
    assert home_path_hits(wrap.format(url)) == []


@given(
    lead=st.sampled_from(["see ", "/opt/", "./", "../", "data/", "`"]),
    segment=st.from_regex(r"[A-Za-z0-9][A-Za-z0-9.-]{0,15}", fullmatch=True),
    root=st.sampled_from(["Users", "home"]),
    name=_NAMES,
)
def test_relative_path_is_not_reported(
    lead: str, segment: str, root: str, name: str
) -> None:
    assert home_path_hits(f"{lead}{segment}/{root}/{name}/x") == []
