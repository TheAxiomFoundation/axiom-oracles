"""Tracked docs never publish a contributor's home-directory path.

Invariants:

1. No line of a git-tracked ``docs/**/*.md`` file or the root ``README.md``
   holds a macOS (``/Users/<name>``) or Linux (``/home/<name>``) home path.
   Docs name a repo-relative path (``data/corpus``) or a placeholder
   (``<policyengine-uk checkout>``) instead.
2. The scanner reports every ``/Users/<name>`` or ``/home/<name>``, plain or
   with JSON-escaped ``\\/`` separators, on its own line and column, with
   three exceptions:
   - it continues the path or fragment of a web URL (``http``, ``https``,
     ``ftp``, ``ftps``): it follows a letter, a digit or one of
     ``- . _ ~ / # ] ) % \\`` and comes before the URL's ``?``
     (``https://host/Users/<name>``, ``https://[::1]/home/<name>``,
     ``https://host/#/home/<name>``, escaped ``https:\\/\\/host\\/home\\/<name>``).
     A URL ends at whitespace, ``|``, ``;``, a quote or backtick, ``<``, ``>``,
     or an unbalanced ``)`` or ``]``. A query value is free text, so it is
     scanned like any other;
   - the path in front of it keeps it below a filesystem root. The segments
     in front (letters, digits, ``.``, ``_``, ``-``, joined by the same
     separator) resolve as in ``posixpath.normpath``, and at least one must
     remain (``/opt/x/home/<name>``, ``$ROOT/x/home/<name>``). A path starting
     with ``.`` or ``..`` is relative and always qualifies
     (``./home/<name>``). A first segment with no separator in front may be a
     prefix (``${RED}``, ``196m``), and a URL's authority (``file://host``) is
     not a directory, so neither counts. So ``/opt/../home/<name>``,
     ``/./home/<name>``, ``data/home/<name>`` and
     ``file://localhost/Users/<name>`` are reported;
   - it names no one: ``/Users/`` alone, ``/Users/<you>/``, ``/Users/$USER/``,
     ``/Users/.../``.
   Anything else glued to the front of a candidate may be a prefix rather than
   a root, so it does not exempt it: ``${RED}/Users/<name>``,
   ``\\033[38:5:196m/Users/<name>``, ``-I/Users/<name>``, ``~/Users/<name>``,
   ``sed 's/X/\\/Users\\/<name>/'``. Percent-encoded text and Windows paths are
   outside this contract.
3. A line that holds ``docs-home-path: allow`` is skipped, and only that line.
   It marks text that is not a home path, such as a web route in a query
   (``?next=/home/dashboard``) or a relative ``data/home/<name>``, in an HTML
   comment (``<!-- docs-home-path: allow -->``) or a code comment.

Failures name ``file:line:column`` only, so the CI log does not republish the
path.
"""

from __future__ import annotations

import posixpath
import re
import subprocess
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOW_MARKER = "docs-home-path: allow"

_CANDIDATE = re.compile(
    r"\\?/(?:Users|home)\\?/(?P<name>[^\s/\\<>`'\"()\[\]{}$%*|,;:=&]+)"
)
_WEB_URL_START = re.compile(r"(?i)\b(?:https?|ftps?):\\?/\\?/")
_URL_END = frozenset("<>\"'`|;")
# A candidate right after one of these (or a letter or digit) continues a URL's path.
_URL_PATH_CHARS = frozenset("-._~/#])%\\")
# A URL scheme, so a segment after it and exactly two separators is an authority.
_SCHEME_COLON = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:\Z")


def tracked_docs(root: Path) -> list[str]:
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--", "docs", "README.md"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8")
    return sorted(path for path in listed.split("\0") if path.endswith(".md"))


def _web_url_paths(line: str) -> list[tuple[int, int]]:
    """``[start, end)`` of each web URL up to its query; brackets nest, as in ``[::1]``."""
    spans: list[tuple[int, int]] = []
    for match in _WEB_URL_START.finditer(line):
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
        query = line.find("?", match.end(), end)
        spans.append((match.start(), end if query < 0 else query))
    return spans


def _continues_web_url(line: str, start: int, paths: list[tuple[int, int]]) -> bool:
    before = line[start - 1] if start else ""
    return (before.isalnum() or before in _URL_PATH_CHARS) and any(
        url_start < start < path_end for url_start, path_end in paths
    )


def _is_path_segment_char(char: str) -> bool:
    return char.isalnum() or char in "._-"


def _path_before(line: str, start: int) -> tuple[list[str], bool]:
    """The segments of the path in front of a candidate, and whether it is absolute.

    A path is absolute when a separator starts it. A URL's authority
    (``file://host``) is left out, and what follows it is absolute.
    """
    separator = "\\/" if line.startswith("\\", start) else "/"
    pos = start
    while line.endswith(separator, 0, pos):
        pos -= len(separator)
    segments: list[str] = []
    while True:
        segment_start = pos
        while segment_start and _is_path_segment_char(line[segment_start - 1]):
            segment_start -= 1
        if segment_start == pos:
            return segments[::-1], True
        segments.append(line[segment_start:pos])
        pos = segment_start
        while line.endswith(separator, 0, pos):
            pos -= len(separator)
        if pos == segment_start:
            return segments[::-1], False
        if segment_start - pos == 2 * len(separator) and _SCHEME_COLON.search(
            line, 0, pos
        ):
            segments.pop()
            return segments[::-1], True


def _continues_relative_path(line: str, start: int) -> bool:
    """Whether the path in front of a candidate keeps it below a filesystem root.

    The segments resolve as in ``posixpath.normpath``: ``.`` drops out and ``..``
    removes the segment before it. A first segment with no separator in front may
    be a prefix rather than a root (``${RED}``, ``196m``), so it is dropped,
    unless it is ``.`` or ``..``, which only start a relative path.
    """
    segments, absolute = _path_before(line, start)
    if not absolute:
        if segments[0] in (".", ".."):
            return True
        segments = segments[1:]
    resolved: list[str] = []
    for segment in segments:
        if segment == "..":
            resolved = resolved[:-1]
        elif segment != ".":
            resolved.append(segment)
    return bool(resolved)


def home_path_hits(text: str) -> list[tuple[int, int]]:
    """``(line, column)`` of each home path, both 1-based, lines split on ``\\n``."""
    hits = []
    for number, line in enumerate(text.split("\n"), start=1):
        if ALLOW_MARKER in line:
            continue
        paths = _web_url_paths(line)
        for match in _CANDIDATE.finditer(line):
            start = match.start()
            if (
                any(char.isalnum() for char in match["name"])
                and not _continues_web_url(line, start, paths)
                and not _continues_relative_path(line, start)
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
        "placeholder such as <checkout> or <download dir>. If the text is not a "
        f"home path, add <!-- {ALLOW_MARKER} --> to its line:\n" + "\n".join(offenders)
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
        "file:/Users/jane/repo and file://localhost//Users/jane/repo",
        "ssh://host/home/jane/repo.git and vscode://file/Users/jane/repo/x.py",
        "(checked out at /home/runner/work/repo)",
        "/Users/jane",
        "cd /home/jane",
        "| /home/jane | checkout |",
        "|/home/jane|",
        "|[site](https://example.org)|/home/jane|",
        "curl https://example.org;/Users/jane/repo/bin/tool",
        "curl https://example.org&&/Users/jane/repo/bin/tool",
        "curl https://example.org&/Users/jane/repo/bin/tool",
        "curl https://example.org$(/Users/jane/repo/bin/sign-token)",
        "http://localhost:8000/view?file=/Users/jane/report.html",
        "http://localhost:8000/view?file=/./home/jane/report.html",
        "/opt/../home/jane and /./Users/jane and data/../x/../../home/jane",
        "http://[0:0:0:0:0:0:0:1]:8000/view?file=/home/jane/report.html",
        "https://example.org/search?q=/Users/jane",
        "https://example.org/validate?source=file:///home/jane/report.html",
        '{"u":"http:\\/\\/localhost\\/v?f=FILE:\\/\\/\\/Users\\/jane\\/r"}',
        "_/Users/jane/checkout_ and */home/jane/x*",
        "~~/Users/jane/repo~~",
        "~/Users/jane/repo~ and cd ~/home/jane",
        "<code>/Users/jane/repo</code>",
        'printf "%s\\n" "${RED}/Users/jane/repo${RESET}"',
        'print(f"{red}/Users/jane/repo{reset}")',
        '"$(tput bold)/Users/jane/repo$(tput sgr0)"',
        'printf "\\033[38:5:196m/home/jane/repo\\033[0m" and \x1b[1;34m/home/jane\x1b[0m',
        'printf "%s/Users/jane/repo"',
        "$HOME/Users/jane and $PWD/home/jane and ${ROOT}/home/jane and {root}/home/jane",
        "cc @/Users/jane/options.rsp",
        "+/Users/jane/repo in a diff and ^/home/jane/ in a regex",
        "cc -I/Users/jane/checkout/include main.c",
        "tar -C/Users/jane/repo -tf archive.tar",
        '{"path": "\\/Users\\/jane\\/repo"}',
        "sed 's/CHECKOUT/\\/Users\\/jane\\/repo/g' config.json",
        '{"file": "file:\\/\\/\\/Users\\/jane\\/repo"}',
        "/Users/Jane Doe/repo and /home/Jane Doe/repo",
        "/Users/jöran/repo",
    ],
)
def test_home_path_is_reported(line: str) -> None:
    # Every form on the line is reported, not just one of them.
    assert len(home_path_hits(line)) == len(
        re.findall(r"\\?/(?:Users|home)\\?/", line)
    ), line


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
        '{"url":"https:\\/\\/example.org\\/#\\/home\\/jane\\/profile"}',
        "see (https://example.org/Users/jane) for the route",
        "[site](https://example.org/Users/jane) and <https://example.org/home/jane/>",
        "--base <axiom-corpus checkout>/data/corpus",
        "--source-dir <download dir>",
        "default `~/.axiom/corpus-cache`",
        "/Users/<you>/axiom-corpus and /Users/$USER/axiom-corpus",
        "/Users/%USER%/axiom-corpus and /Users/.../axiom-corpus and /Users/*/x",
        "/homepage/jane/ and /opt/app/home/jane/ and ./home/jane and ../home/jane/",
        "[./home/jane](./home/jane) and (../Users/jane) and data//x/home/jane",
        "/opt/x/./home/jane and ../x/../../Users/jane and data/x/../y/home/jane",
        '{"path": "data\\/x\\/home\\/jane"} and \\/opt\\/app\\/home\\/jane',
        "$PWD/data/home/jane and ${ROOT}/x/Users/jane and {run_id}/x/home/jane",
        "https://example.org/x?path=/opt/home/jane and smb://server/share/Users/jane",
        "file:///opt/home/jane/repo and file://server/share/Users/jane",
    ],
)
def test_non_path_is_not_reported(line: str) -> None:
    assert not home_path_hits(line), line


@pytest.mark.parametrize(
    "line",
    [
        "[Sign in](https://example.org/login?next=/home/dashboard)",
        '{"url":"https:\\/\\/example.org\\/login?next=\\/Users\\/Index"}',
        "[data/home/jane/report.json](data/home/jane/report.json)",
        "grep '^data/home/jane/' inventory.txt and +data/home/jane/report.json",
    ],
)
def test_allow_marker_clears_text_that_is_not_a_home_path(line: str) -> None:
    assert home_path_hits(line)
    assert not home_path_hits(f"{line} <!-- {ALLOW_MARKER} -->")
    assert not home_path_hits(f"{line}  # {ALLOW_MARKER}")


_NAMES = st.from_regex(r"[A-Za-z0-9][A-Za-z0-9._-]{0,19}", fullmatch=True)
# Filler holds no slash, so it can neither start nor extend a path or a URL.
_FILLER = st.text(
    alphabet=st.characters(blacklist_characters="/\n", blacklist_categories=("Cs",)),
    max_size=40,
)
_LEADS = [
    *["", " ", "`", '"', "'", "(", "[", "|", "=", ":", "*", "_", "~", "~~", "@"],
    *["+", "^", "#", "<code>", "<br>", "{", "}", "${", "$("],
    *["-I", "--root=", "file://", "FILE://", "file://localhost"],
    *["file://localhost/", "file:", "ssh://host", "vscode://file"],
    *["|[site](https://example.org)|", "curl https://example.org;"],
    *["curl https://example.org&&", "curl https://example.org&"],
    *["http://localhost:8000/view?file=", "https://example.org/?q=", "sed 's/X/"],
]
# Shell expansions, format fields and terminal escapes that can prefix an absolute path.
_PREFIXES = st.one_of(
    st.from_regex(r"\$[A-Za-z_][A-Za-z0-9_]{0,9}", fullmatch=True),
    st.from_regex(r"\$\{[A-Za-z_][A-Za-z0-9_]{0,9}\}", fullmatch=True),
    st.from_regex(r"\$\([a-z][a-z -]{0,12}\)", fullmatch=True),
    st.from_regex(r"\{[a-z_][a-z0-9_]{0,9}\}", fullmatch=True),
    st.from_regex(r"%[0-9]{0,2}[sd]", fullmatch=True),
    st.from_regex(r"(\x1b|\\033|\\e|\\x1b)\[[0-9;:]{0,8}m", fullmatch=True),
)


def _home_path(root: str, name: str, rest: str, escaped: bool) -> str:
    slash = "\\/" if escaped else "/"
    return f"{slash}{root}{slash}{name}{rest.replace('/', slash)}"


@settings(max_examples=300, deadline=None)
@given(
    root=st.sampled_from(["Users", "home"]),
    name=_NAMES,
    lead=st.one_of(st.sampled_from(_LEADS), _PREFIXES),
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
    # Inside a sed replacement only an escaped path is valid sed.
    assume(escaped or not lead.startswith("sed "))
    assume(
        ALLOW_MARKER not in tail and all(ALLOW_MARKER not in line for line in before)
    )
    text = "\n".join([*before, f"{lead}{_home_path(root, name, rest, escaped)} {tail}"])
    assert home_path_hits(text) == [(len(before) + 1, len(lead) + 1)]


@settings(max_examples=300, deadline=None)
@given(
    lead=st.one_of(st.sampled_from(_LEADS), _PREFIXES),
    root=st.sampled_from(["Users", "home"]),
    name=_NAMES,
    escaped=st.booleans(),
    marker=st.sampled_from([f"<!-- {ALLOW_MARKER} --> ", f"# {ALLOW_MARKER} "]),
    marked_first=st.booleans(),
)
def test_allow_marker_skips_only_its_own_line(
    lead: str, root: str, name: str, escaped: bool, marker: str, marked_first: bool
) -> None:
    assume(escaped or not lead.startswith("sed "))
    line = f"{lead}{_home_path(root, name, '', escaped)}"
    lines = [marker + line, line] if marked_first else [line, line + " " + marker]
    unmarked = 2 if marked_first else 1
    assert home_path_hits("\n".join(lines)) == [(unmarked, len(lead) + 1)]


_DNS_HOSTS = st.from_regex(
    r"[a-z0-9]([a-z0-9-]{0,10}[a-z0-9])?(\.[a-z0-9]{1,10})+", fullmatch=True
)
_URL_HOSTS = st.one_of(
    _DNS_HOSTS,
    st.sampled_from(["[::1]", "[2001:db8::1]", "[0:0:0:0:0:0:0:1]", "localhost:8080"]),
)
_URL_WRAPS = st.sampled_from(
    ["{}", "[site]({})", "<{}>", "({}) and", "| {} |", '{{"url":"{}"}}']
)


@settings(max_examples=300, deadline=None)
@given(
    scheme=st.sampled_from(["http", "https", "HTTPS", "ftp", "ftps"]),
    host=_URL_HOSTS,
    between=st.sampled_from(["", "/", "/#", "/app", "/wiki/Home_(film)"]),
    root=st.sampled_from(["Users", "home"]),
    name=_NAMES,
    escaped=st.booleans(),
    wrap=_URL_WRAPS,
)
def test_web_url_path_is_not_reported(
    scheme: str, host: str, between: str, root: str, name: str, escaped: bool, wrap: str
) -> None:
    url = f"{scheme}://{host}{between}/{root}/{name}/"
    if escaped:
        url = url.replace("/", "\\/")
    assert home_path_hits(wrap.format(url)) == []


@settings(max_examples=300, deadline=None)
@given(
    scheme=st.sampled_from(["http", "https", "HTTPS", "ftp"]),
    host=_URL_HOSTS,
    query=st.from_regex(
        r"/[a-z]{0,8}\?([a-z]{1,6}=[a-z0-9]{0,4}&)?[a-z_]{1,8}=", fullmatch=True
    ),
    file_url=st.sampled_from(["", "file://", "FILE://localhost"]),
    root=st.sampled_from(["Users", "home"]),
    name=_NAMES,
    escaped=st.booleans(),
    wrap=_URL_WRAPS,
)
def test_query_value_is_reported(
    scheme: str,
    host: str,
    query: str,
    file_url: str,
    root: str,
    name: str,
    escaped: bool,
    wrap: str,
) -> None:
    url = f"{scheme}://{host}{query}{file_url}/{root}/{name}"
    if escaped:
        url = url.replace("/", "\\/")
    assert len(home_path_hits(wrap.format(url))) == 1


_WORDS = st.from_regex(r"[A-Za-z0-9_-][A-Za-z0-9._-]{0,7}", fullmatch=True).filter(
    lambda word: word not in ("Users", "home")
)


@settings(max_examples=500, deadline=None)
@given(
    lead=st.sampled_from(
        ["", " ", "=", "(", '"', "|", "~", "${X}", "file://", "https://h/?p="]
    ),
    first=st.one_of(st.sampled_from(["", ".", ".."]), _WORDS),
    segments=st.lists(st.one_of(st.sampled_from([".", ".."]), _WORDS), max_size=5),
    root=st.sampled_from(["Users", "home"]),
    name=_NAMES,
    escaped=st.booleans(),
)
def test_path_is_reported_exactly_when_it_resolves_to_a_root(
    lead: str, first: str, segments: list[str], root: str, name: str, escaped: bool
) -> None:
    # A dot right after ``file://`` would be the URL's authority, not a relative start.
    assume(not (lead == "file://" and first in (".", "..")))
    text = (
        lead
        + first
        + "".join(f"/{segment}" for segment in segments)
        + f"/{root}/{name}"
    )
    if escaped:
        text = text.replace("/", "\\/")
    # Differential oracle: the path in front of the candidate, as posixpath resolves
    # it, with a glued first segment treated as a possible prefix.
    at_root = posixpath.normpath("/" + "/".join(segments)) == "/"
    assert bool(home_path_hits(text)) is (first not in (".", "..") and at_root)
