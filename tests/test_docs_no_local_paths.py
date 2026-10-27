"""Tracked docs never publish a contributor's home-directory path.

Invariants:

1. No line of a git-tracked ``docs/**/*.md`` file or the root ``README.md``
   holds a macOS (``/Users/<name>``) or Linux (``/home/<name>``) home path.
   Docs name a repo-relative path (``data/corpus``) or a placeholder
   (``<policyengine-uk checkout>``) instead.
2. The scanner reports every ``/Users/<name>`` or ``/home/<name>``, plain or
   with JSON-escaped ``\\/`` separators, on its own line and column, except
   where it is not a home path:
   - continuing the path, query or fragment of a URL of any scheme but
     ``file:`` (``https://host/Users/<name>``, ``https://[::1]/home/<name>``,
     ``https://host/#/home/<name>``, escaped ``https:\\/\\/host\\/home\\/<name>``).
     A URL ends at whitespace, ``|``, ``;``, a quote or backtick, ``<``, ``>``,
     or an unbalanced ``)`` or ``]``. Inside one, a candidate continues it
     only after a letter, a digit, ``- . _ ~ / # ] ) % \\`` or ``=``, so one
     after ``&`` starts a new word (``curl https://host&&/Users/<name>``). A
     query value (after ``=``) continues it only as a ``/home/...`` route of
     a remote host (``?next=/home/dashboard``): ``/Users/<name>`` names a
     macOS home (``?q=/Users/<name>``), and a loopback host's query names a
     local file (``http://localhost:8000/view?file=/home/<name>``);
   - continuing a relative path: the candidate follows a path segment
     (letters, digits, ``.``, ``_``, ``-``) that either follows the same
     separator (``/opt/x/home/<name>``, ``$ROOT/x/home/<name>``) or starts a
     token, after the line start, whitespace, a quote or backtick, or one of
     ``( { < > = : , | *`` (``data/home/<name>``, ``./home/<name>``,
     ``--root=data/home/<name>``). Nothing else roots a path, because the
     scanner cannot tell a root from a prefix such as a color code
     (``${RED}/Users/<name>`` prints a home path). An expansion, format field
     or escape sequence (``$ROOT/``, ``${ROOT}/``, ``$(pwd)/``, ``{root}/``,
     ``%s/``, ``\\033[1;34m/``), a tilde (``~/Users/<name>``), an HTML tag
     (``<code>/Users/<name>``), an option flag (``-I/Users/...``),
     underscores (``_/Users/..._``) and a bare ``/`` before an escaped path
     (``sed 's/X/\\/Users\\/<name>/'``) are not roots, so those are reported;
   - naming no one: ``/Users/`` alone, ``/Users/<you>/``, ``/Users/$USER/``,
     ``/Users/.../``.
   ``file:`` URLs are scanned whatever their case, host or extra slashes
   (``FILE:///Users/...``, ``file://localhost//Users/...``). Percent-encoded
   text and Windows paths are outside this contract.

Failures name ``file:line:column`` only, so the CI log does not republish the
path.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parents[1]

_CANDIDATE = re.compile(
    r"\\?/(?P<root>Users|home)\\?/(?P<name>[^\s/\\<>`'\"()\[\]{}$%*|,;:=&]+)"
)
_URL_START = re.compile(r"\b(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*):\\?/\\?/")
_URL_END = frozenset("<>\"'`|;")
# A candidate right after one of these (or a letter or digit) continues a URL's path.
_URL_PATH_CHARS = frozenset("-._~/#])%\\")
_LOOPBACK_HOST = re.compile(
    r"(?i)(?:[^@]*@)?(?:localhost|[\w-]+(?:\.[\w-]+)*\.localhost|127(?:\.\d{1,3}){3}"
    r"|0\.0\.0\.0|\[::1\])(?::\d*)?"
)
_FILE_URL_PREFIX = re.compile(r"(?i)\bfile:\\?/\\?/[^/\\\s]*(?:\\?/)*\Z")
_OPTION_FLAG = re.compile(r"-{1,2}[A-Za-z][\w-]*")
# A relative path's first segment follows the line start, whitespace or one of these.
_TOKEN_STARTS = frozenset("\"'`({<>=:,|*")


def tracked_docs(root: Path) -> list[str]:
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--", "docs", "README.md"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8")
    return sorted(path for path in listed.split("\0") if path.endswith(".md"))


def _url_spans(line: str) -> list[tuple[int, int, bool]]:
    """``[start, end)`` of each non-``file:`` URL, and whether its host is loopback.

    Brackets nest, as in ``[::1]``.
    """
    spans: list[tuple[int, int, bool]] = []
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
        host = re.split(r"[/\\?#]", line[match.end() : end], maxsplit=1)[0]
        spans.append((match.start(), end, bool(_LOOPBACK_HOST.fullmatch(host))))
    return spans


def _continues_url(
    line: str, candidate: re.Match[str], urls: list[tuple[int, int, bool]]
) -> bool:
    start = candidate.start()
    before = line[start - 1] if start else ""
    for url_start, url_end, loopback in urls:
        if url_start < start < url_end:
            if before == "=":
                return candidate["root"] == "home" and not loopback
            return before.isalnum() or before in _URL_PATH_CHARS
    return False


def _is_path_segment_char(char: str) -> bool:
    return char.isalnum() or char in "._-"


def _starts_home_path(line: str, start: int) -> bool:
    if _FILE_URL_PREFIX.search(line, 0, start):
        return True
    separator = "\\/" if line.startswith("\\", start) else "/"
    slashes = start
    while line.endswith(separator, 0, slashes):
        slashes -= len(separator)
    if separator == "\\/" and line.endswith("/", 0, slashes):
        return True
    segment_start = slashes
    while segment_start and _is_path_segment_char(line[segment_start - 1]):
        segment_start -= 1
    segment = line[segment_start:slashes]
    if not segment:
        return True
    if line.endswith(separator, 0, segment_start):
        return False
    before = line[segment_start - 1] if segment_start else " "
    starts_token = before.isspace() or before in _TOKEN_STARTS
    if not starts_token or _OPTION_FLAG.fullmatch(segment):
        return True
    return not any(char.isalnum() for char in segment) and bool(segment.strip("."))


def home_path_hits(text: str) -> list[tuple[int, int]]:
    """``(line, column)`` of each home path, both 1-based, lines split on ``\\n``."""
    hits = []
    for number, line in enumerate(text.split("\n"), start=1):
        urls = _url_spans(line)
        for match in _CANDIDATE.finditer(line):
            if (
                any(char.isalnum() for char in match["name"])
                and not _continues_url(line, match, urls)
                and _starts_home_path(line, match.start())
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
        "FILE:///Users/jane/repo and file://localhost/Users/jane/repo",
        "file:/Users/jane/repo and file://localhost//Users/jane/repo",
        "(checked out at /home/runner/work/repo)",
        "/Users/jane",
        "cd /home/jane",
        "| /home/jane | checkout |",
        "|/home/jane|",
        "|[site](https://example.org)|/home/jane|",
        "curl https://example.org;/Users/jane/repo/bin/tool",
        "curl https://example.org&&/Users/jane/repo/bin/tool",
        "curl https://example.org&/Users/jane/repo/bin/tool",
        "http://localhost:8000/view?file=/Users/jane/report.html",
        "http://127.0.0.1:8888/tree?path=/home/jane/nb.ipynb",
        "https://example.org/search?q=/Users/jane",
        "_/Users/jane/checkout_ and */home/jane/x*",
        "~~/Users/jane/repo~~",
        "~/Users/jane/repo~ and cd ~/home/jane",
        "<code>/Users/jane/repo</code>",
        'printf "%s\\n" "${RED}/Users/jane/repo${RESET}"',
        'print(f"{red}/Users/jane/repo{reset}")',
        '"$(tput bold)/Users/jane/repo$(tput sgr0)"',
        'printf "\\033[1;34m/home/jane/repo\\033[0m" and \x1b[1m/home/jane\x1b[0m',
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
        "[Sign in](https://example.org/login?next=/home/dashboard)",
        '{"url":"https:\\/\\/example.org\\/login?a=1&next=\\/home\\/dashboard"}',
        "see (https://example.org/Users/jane) for the route",
        "[site](https://example.org/Users/jane) and <https://example.org/home/jane/>",
        "--base <axiom-corpus checkout>/data/corpus",
        "--source-dir <download dir>",
        "default `~/.axiom/corpus-cache`",
        "/Users/<you>/axiom-corpus and /Users/$USER/axiom-corpus",
        "/Users/%USER%/axiom-corpus and /Users/.../axiom-corpus and /Users/*/x",
        "data/home/jane/ and /homepage/jane/ and example.com/Users/jane",
        "/opt/app/home/jane/ and ./home/jane and ../home/jane/ and data//home/jane",
        '{"path": "data\\/home\\/jane\\/x"} and \\/opt\\/app\\/home\\/jane',
        "$PWD/data/home/jane and ${ROOT}/x/Users/jane and {run_id}/x/home/jane",
        "--root=data/home/jane and **data/home/jane** and <code>data/home/jane</code>",
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
    *["", " ", "`", '"', "'", "(", "[", "|", "=", ":", "*", "_", "~", "~~", "@"],
    *["+", "^", "#", "<code>", "<br>", "{", "}", "${", "$("],
    *["-I", "--root=", "file://", "FILE://", "file://localhost"],
    *["file://localhost/", "file:"],
    *["|[site](https://example.org)|", "curl https://example.org;"],
    *["curl https://example.org&&", "curl https://example.org&"],
    *["http://localhost:8000/view?file=", "sed 's/X/"],
]
# Shell expansions, format fields and terminal escapes that can prefix an absolute path.
_PREFIXES = st.one_of(
    st.from_regex(r"\$[A-Za-z_][A-Za-z0-9_]{0,9}", fullmatch=True),
    st.from_regex(r"\$\{[A-Za-z_][A-Za-z0-9_]{0,9}\}", fullmatch=True),
    st.from_regex(r"\$\([a-z][a-z -]{0,12}\)", fullmatch=True),
    st.from_regex(r"\{[a-z_][a-z0-9_]{0,9}\}", fullmatch=True),
    st.from_regex(r"%[0-9]{0,2}[sd]", fullmatch=True),
    st.from_regex(r"(\x1b|\\033|\\e|\\x1b)\[[0-9;]{0,6}m", fullmatch=True),
)


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
    slash = "\\/" if escaped else "/"
    path = f"{slash}{root}{slash}{name}{rest.replace('/', slash)}"
    text = "\n".join([*before, f"{lead}{path} {tail}"])
    assert home_path_hits(text) == [(len(before) + 1, len(lead) + 1)]


_DNS_HOSTS = st.from_regex(
    r"[a-z0-9]([a-z0-9-]{0,10}[a-z0-9])?(\.[a-z0-9]{1,10})+", fullmatch=True
).filter(
    lambda host: (
        not host.startswith(("127.", "0.0.0.0", "localhost"))
        and not host.endswith(".localhost")
    )
)
_LOOPBACK_HOSTS = [
    *["localhost", "localhost:8000", "app.localhost", "127.0.0.1:8888"],
    *["0.0.0.0:5000", "[::1]:8000"],
]
_URL_WRAPS = st.sampled_from(
    ["{}", "[site]({})", "<{}>", "({}) and", "| {} |", '{{"url":"{}"}}']
)


@settings(max_examples=300, deadline=None)
@given(
    scheme=st.sampled_from(["http", "https", "HTTPS", "ftp", "ssh"]),
    host=st.one_of(
        _DNS_HOSTS, st.sampled_from(["[::1]", "[2001:db8::1]", "localhost:8080"])
    ),
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
    scheme=st.sampled_from(["http", "https", "HTTP"]),
    host=st.one_of(_DNS_HOSTS, st.sampled_from(_LOOPBACK_HOSTS)),
    query=st.from_regex(
        r"/[a-z]{0,8}\?([a-z]{1,6}=[a-z0-9]{0,4}&)?[a-z_]{1,8}=", fullmatch=True
    ),
    root=st.sampled_from(["Users", "home"]),
    name=_NAMES,
    escaped=st.booleans(),
    wrap=_URL_WRAPS,
)
def test_query_value_is_reported_unless_a_remote_home_route(
    scheme: str, host: str, query: str, root: str, name: str, escaped: bool, wrap: str
) -> None:
    url = f"{scheme}://{host}{query}/{root}/{name}"
    if escaped:
        url = url.replace("/", "\\/")
    reported = root == "Users" or host in _LOOPBACK_HOSTS
    assert bool(home_path_hits(wrap.format(url))) is reported


_RELATIVE_LEADS = [
    *["see ", "/opt/", "./", "../", "data/", "`", "(", '"', "--root=", "| "],
    *["**", "<code>", "$ROOT/", "${ROOT}/", "$(pwd)/", "{root}/", "~/"],
]


@settings(max_examples=300, deadline=None)
@given(
    lead=st.sampled_from(_RELATIVE_LEADS),
    segment=st.from_regex(r"[A-Za-z0-9][A-Za-z0-9.-]{0,15}", fullmatch=True),
    root=st.sampled_from(["Users", "home"]),
    name=_NAMES,
    escaped=st.booleans(),
)
def test_relative_path_is_not_reported(
    lead: str, segment: str, root: str, name: str, escaped: bool
) -> None:
    text = f"{lead}{segment}/{root}/{name}/x"
    if escaped:
        text = text.replace("/", "\\/")
    assert home_path_hits(text) == []
