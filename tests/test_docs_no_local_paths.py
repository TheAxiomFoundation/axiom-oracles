"""Tracked Markdown never publishes a contributor's home-directory path.

Invariants:

1. No line of a git-tracked ``*.md`` file holds a macOS (``/Users/<name>``) or
   Linux (``/home/<name>``) home path. Markdown names a repo-relative path
   (``data/corpus``) or a placeholder (``<policyengine-uk checkout>``) instead.
2. The scanner reports every ``/Users/<name>`` or ``/home/<name>`` on its own
   line and column. A separator is a ``/`` behind any number of backslashes:
   plain, JSON-escaped (``\\/``) or escaped twice (``\\\\/``), in any mix. The
   home segment may repeat its separator or hold ``.`` (``/Users//<name>``,
   ``/home/./<name>``). There are three exceptions:
   - it continues the path or fragment of a web URL (``http``, ``https``,
     ``ftp``, ``ftps``) on a remote host: it follows a letter, a digit or one
     of ``- . _ ~ / # ] ) % \\`` and comes before the URL's ``?``
     (``https://host/Users/<name>``, ``https://[2001:db8::1]/home/<name>``,
     ``https://host/#/home/<name>``, escaped ``https:\\/\\/host\\/home\\/<name>``).
     A URL ends at whitespace, ``|``, ``;``, a quote or backtick, ``<``, ``>``,
     or an unbalanced ``)`` or ``]``. A query value is free text, so it is
     scanned like any other. A local host (``localhost``, ``*.localhost``,
     ``127.0.0.0/8`` or ``0.0.0.0/8`` in any IPv4 spelling, ``[::1]``, ``[::]``
     or their IPv4-mapped forms) may serve its own files
     (``http://localhost:5173/@fs/Users/<name>``), so its path is scanned too;
   - the path in front of it keeps it below a filesystem root. The segments
     in front (letters, digits, ``.``, ``_``, ``-``, joined by separators)
     resolve as in ``posixpath.normpath``, and at least one must remain (``/opt/x/home/<name>``, ``$ROOT/x/home/<name>``) that is not
     a home mount: ``/System/Volumes/Data`` (macOS) for either root,
     ``/Volumes/<volume>`` (macOS) and ``/host_mnt`` (Docker Desktop) for
     ``Users``, ``/var`` (Fedora Atomic) and ``/usr`` (FreeBSD) for ``home``.
     A path starting with ``.`` or ``..`` is relative and always qualifies
     (``./home/<name>``). A first segment with no separator in front may be a
     prefix (``${RED}``, ``196m``), and an authority after two leading
     separators (``file://host``, protocol-relative or UNC ``//host``) is not
     a directory, so neither counts. After a segment, a run of
     separators that changes escape level starts a new path at the root, as
     sed's delimiter does in ``s/X/\\/Users\\/<name>/``. So ``/opt/../home/<name>``,
     ``/./home/<name>``, ``data/home/<name>``, ``/var/home/<name>`` and
     ``file://localhost/Users/<name>``, ``//server/Users/<name>`` are reported;
   - it names no one: ``/Users/`` alone, ``/Users/<you>/``, ``/Users/$USER/``,
     ``/Users/.../``.
   Anything else glued to the front of a candidate may be a prefix rather than
   a root, so it does not exempt it: ``${RED}/Users/<name>``,
   ``\\033[38:5:196m/Users/<name>``, ``-I/Users/<name>``, ``~/Users/<name>``.
   Percent-encoded, ``\\u002F`` and ``&#47;`` text, Windows homes
   (``C:\\Users``, ``/mnt/c/Users``) and lowercase ``/users/``, a common web
   route (``api/users/123``), are outside this contract.
3. A line that ends with the exact token ``docs-home-path: allow``, closed by
   ``-->``, by ``*/`` or by nothing, is skipped, and only that line. Put it at
   the end of the line: ``<!-- docs-home-path: allow -->`` after prose, a
   table row or a link, and ``# docs-home-path: allow`` in a shell or YAML
   block. A line that starts with ``<!--`` opens an HTML block and stops
   rendering Markdown. The marker is for text that is not a home path: a
   schemeless URL (``www.kancare.ks.gov/home/showpublisheddocument/4880``), a
   web route in a query (``?next=/home/dashboard``) or on a local server
   (``http://localhost:3000/home/dashboard``), or a relative
   ``data/home/<name>``.

Failures name ``file:line:column`` only, so the CI log does not republish the
path.
"""

from __future__ import annotations

import ipaddress
import posixpath
import re
import subprocess
import time
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOW_MARKER = "docs-home-path: allow"

# The marker counts only as the last token on its line, closed by an HTML or C
# comment or by nothing (a ``#`` or ``//`` comment).
_ALLOW = re.compile(r"\bdocs-home-path: allow(?:\s*(?:-->|\*/))?\s*\Z")
# A slash behind any number of backslashes. It never starts inside a run of
# backslashes, so a run is read once.
_SEPARATOR = r"(?<!\\)\\*+/"
_CANDIDATE = re.compile(
    rf"{_SEPARATOR}(?P<root>Users|home)(?:{_SEPARATOR}(?:\.(?={_SEPARATOR}))?)+"
    r"(?P<name>[^\s/\\<>`'\"()\[\]{}$%*|,;:=&]+)"
)
_WEB_URL_START = re.compile(rf"(?i)\b(?:https?|ftps?):{_SEPARATOR}{_SEPARATOR}")
_PATH_ITEM = re.compile(rf"(?P<separators>(?:{_SEPARATOR})+)|[\w.-]+")
_SPELLED_SEPARATOR = re.compile(r"\\*/")
_URL_END = frozenset("<>\"'`|;")
# A candidate right after one of these (or a letter or digit) continues a URL's path.
_URL_PATH_CHARS = frozenset("-._~/#])%\\")
_AUTHORITY = re.compile(r"[^/\\?#]*")
# One part of an IPv4 address as a browser reads it: hexadecimal, octal or decimal.
_IPV4_PART = re.compile(r"0x[0-9a-f]*|0[0-7]*|[1-9][0-9]*")
_ROOTS = frozenset({"Users", "home"})
# Directories that hold homes below another root; ``None`` stands for any one segment.
_HOME_MOUNTS: tuple[tuple[tuple[str | None, ...], frozenset[str]], ...] = (
    (("System", "Volumes", "Data"), _ROOTS),  # the macOS data volume
    (("Volumes", None), frozenset({"Users"})),  # another macOS volume
    (("host_mnt",), frozenset({"Users"})),  # Docker Desktop's view of macOS
    (("var",), frozenset({"home"})),  # Fedora Atomic
    (("usr",), frozenset({"home"})),  # FreeBSD
)


def tracked_docs(root: Path) -> list[str]:
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.md"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8")
    return sorted(path for path in listed.split("\0") if path.endswith(".md"))


def _ipv4_first_octet(host: str) -> int | None:
    """The first octet of an IPv4 host in any form a browser reads (``127.1``, ``0x7f.0.0.1``)."""
    parts = host.split(".")
    if len(parts) > 4 or not all(_IPV4_PART.fullmatch(part) for part in parts):
        return None
    values = [
        int(part[2:] or "0", 16)
        if part[1:2] == "x"
        else int(part, 8 if part[0] == "0" else 10)
        for part in parts
    ]
    *leading, last = values
    if any(value > 255 for value in leading) or last >= 256 ** (5 - len(values)):
        return None
    return leading[0] if leading else last >> 24


def _is_local_host(authority: str) -> bool:
    """Whether a URL's authority names this machine, whose server may serve its own files."""
    host = authority.rpartition("@")[2].lower()
    if host.startswith("["):
        try:
            address = ipaddress.IPv6Address(
                host[1:].partition("]")[0].partition("%")[0]
            )
        except ValueError:
            return False
        if address.ipv4_mapped is not None:
            return address.ipv4_mapped.packed[0] in (0, 127)
        return address.is_loopback or address.is_unspecified
    host = host.partition(":")[0].removesuffix(".")
    return (
        host == "localhost"
        or host.endswith(".localhost")
        or _ipv4_first_octet(host) in (0, 127)
    )


def _web_url_paths(line: str) -> list[tuple[int, int]]:
    """``[start, end)`` of each remote web URL up to its query; brackets nest, as in ``[::1]``."""
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
        if _is_local_host(_AUTHORITY.match(line, match.end(), end)[0]):
            continue
        query = line.find("?", match.end(), end)
        spans.append((match.start(), end if query < 0 else query))
    return spans


def _continues_web_url(line: str, start: int, paths: list[tuple[int, int]]) -> bool:
    before = line[start - 1] if start else ""
    return (before.isalnum() or before in _URL_PATH_CHARS) and any(
        url_start < start < path_end for url_start, path_end in paths
    )


def _roots_not_mounted(resolved: list[str]) -> frozenset[str]:
    """The roots that a resolved path keeps below a filesystem root: none at ``/``."""
    if not resolved:
        return frozenset()
    roots = _ROOTS
    for mount, homes in _HOME_MOUNTS:
        if len(mount) == len(resolved) and all(
            part in (None, segment)
            for part, segment in zip(mount, resolved, strict=True)
        ):
            roots -= homes
    return roots


def _roots_below_a_directory(line: str) -> dict[int, frozenset[str]]:
    """For each position in a run of separators, the roots (``Users``, ``home``)
    that the path in front of it keeps below a filesystem root.

    One pass resolves every path on the line as ``posixpath.normpath`` would:
    ``.`` drops out and ``..`` removes the segment before it. A path that starts
    with separators is absolute, and when exactly two start it, the authority
    after them (``scheme://host``, ``//host``) is left out.
    A first segment with no separator in front may be a prefix rather than a root
    (``${RED}``, ``196m``), so it is dropped, unless it is ``.`` or ``..``, which
    make the whole path relative. After a segment, separators that change escape
    level (sed's ``s/X/\\/Users``) start a new path at the root.
    """
    below: dict[int, frozenset[str]] = {}
    path_end = -1
    for item in _PATH_ITEM.finditer(line):
        if item.start() != path_end:
            resolved: list[str] = []
            first, relative, authority = True, False, False
        path_end = item.end()
        separators = item["separators"]
        if separators is None:
            segment = item[0]
            if first:
                relative = segment in (".", "..")
            elif authority:
                authority = False
            elif segment == "..":
                del resolved[-1:]
            elif segment != ".":
                resolved.append(segment)
        else:
            if first:
                authority = separators.count("/") == 2
            elif len(set(_SPELLED_SEPARATOR.findall(separators))) > 1:
                resolved, relative = [], False
            roots = _ROOTS if relative else _roots_not_mounted(resolved)
            below.update(dict.fromkeys(range(item.start(), item.end()), roots))
        first = False
    return below


def home_path_hits(text: str) -> list[tuple[int, int]]:
    """``(line, column)`` of each home path, both 1-based, lines split on ``\\n``."""
    hits = []
    for number, line in enumerate(text.split("\n"), start=1):
        if ALLOW_MARKER in line and _ALLOW.search(line):
            continue
        candidates = [
            match
            for match in _CANDIDATE.finditer(line)
            if any(char.isalnum() for char in match["name"])
        ]
        if not candidates:
            continue
        paths = _web_url_paths(line)
        below = _roots_below_a_directory(line)
        for match in candidates:
            start = match.start()
            if not _continues_web_url(line, start, paths) and match[
                "root"
            ] not in below.get(start, ()):
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
        "Markdown carries absolute home-directory paths; use a repo-relative path or a "
        "placeholder such as <checkout> or <download dir>. If the text is not a home path "
        "(a schemeless URL such as host.gov/home/..., a route such as ?next=/home/...), end "
        f"its line with <!-- {ALLOW_MARKER} -->, or with # {ALLOW_MARKER} in a shell or "
        "YAML block:\n" + "\n".join(offenders)
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
        "http://[0::1]:8000/view?file=/home/jane and http://localhost.:8000/v?f=/Users/jane",
        "http://[::ffff:127.0.0.1]/v?f=/home/jane",
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
        'printf "\\033[38:2::255:0:0m/Users/jane/repo\\033[0m"',
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
        # The home segment spelled with a repeated separator or a ``.`` segment.
        "--base /Users//jane/axiom-corpus and cd /home//jane",
        "ls /Users/./jane/repo and /home/.//jane and /Users/.\\/jane",
        '{"path": "\\/Users\\/\\/jane\\/repo"}',
        # Escaped twice: JSON inside JSON, or a Markdown-escaped backslash.
        '"{\\"path\\": \\"\\\\/Users\\\\/jane\\\\/repo\\"}"',
        "sed 's/X/\\\\/Users\\\\/jane/'",
        # Escape levels mixed within one path decode alike; sed's delimiter restarts it.
        "/.\\/Users/jane and \\/./home/jane and \\\\/.\\/Users/jane",
        "file:/\\/host\\/home\\/jane and file:\\//host/home/jane",
        "sed 's/opt/\\/home\\/jane/' and sed 's/opt/\\\\/home\\\\/jane/'",
        # A protocol-relative or UNC path names a home on its server.
        "//server/Users/jane/repo and (//host/home/jane)",
        # Home mounts below another root.
        "/System/Volumes/Data/Users/jane/repo and /System/Volumes/Data/home/jane",
        "/Volumes/Backup/Users/jane/repo and /host_mnt/Users/jane/repo",
        "/var/home/jane/repo and /usr/home/jane/repo and file:///var/home/jane",
        # A local server may serve its own files.
        "http://localhost:5173/@fs/Users/jane/repo/src/main.ts",
        "http://localhost:8000/Users/jane/report.html and http://127.1/home/jane",
        "http://[::1]:8000/home/jane and http://0.0.0.0:8000/Users/jane",
        "https://[::1]/home/jane/profile and http://app.localhost/Users/jane",
        # A marker that is not the last token on its line does not count.
        "/Users/jane/repo <!-- docs-home-path: allowed -->",
        "<!-- docs-home-path: allow --> /Users/jane/repo",
    ],
)
def test_home_path_is_reported(line: str) -> None:
    # Every form on the line is reported, not just one of them.
    assert len(home_path_hits(line)) == len(
        re.findall(r"\\*/(?:Users|home)\\*/", line)
    ), line


@pytest.mark.parametrize(
    "line",
    [
        "the provisions carry no `file:` URL or `/Users/` path",
        "https://example.com/Users/jane/profile",
        "https://example.org/home/jane/",
        "https://[2001:db8::1]/Users/jane/profile",
        "https://example.org/#/home/jane/profile",
        "https://example.org//Users/jane/profile",
        "https://en.wikipedia.org/wiki/Home_(film)/home/jane",
        '{"url":"https:\\/\\/example.org\\/#\\/home\\/jane\\/profile"}',
        '"{\\"url\\":\\"https:\\\\/\\\\/example.org\\\\/home\\\\/jane\\"}"',
        "see (https://example.org/Users/jane) for the route",
        "[site](https://example.org/Users/jane) and <https://example.org/home/jane/>",
        "https://example.org./Users/jane and https://localhost.example.org/home/jane",
        "--base <axiom-corpus checkout>/data/corpus",
        "--source-dir <download dir>",
        "default `~/.axiom/corpus-cache`",
        "/Users/<you>/axiom-corpus and /Users/$USER/axiom-corpus",
        "/Users/%USER%/axiom-corpus and /Users/.../axiom-corpus and /Users/*/x",
        "/Users/../srv/x and /home/./../srv/x",
        "/homepage/jane/ and /opt/app/home/jane/ and ./home/jane and ../home/jane/",
        "[./home/jane](./home/jane) and (../Users/jane) and data//x/home/jane",
        "/opt/x/./home/jane and ../x/../../Users/jane and data/x/../y/home/jane",
        "/opt\\/home\\/jane and \\/opt/home/jane and file:////host/home/jane",
        '{"path": "data\\/x\\/home\\/jane"} and \\/opt\\/app\\/home\\/jane',
        '"{\\"path\\": \\"\\\\/opt\\\\/home\\\\/jane\\"}"',
        "$PWD/data/home/jane and ${ROOT}/x/Users/jane and {run_id}/x/home/jane",
        "https://example.org/x?path=/opt/home/jane and smb://server/share/Users/jane",
        "file:///opt/home/jane/repo and file://server/share/Users/jane",
        "/var/Users/jane and /usr/Users/jane and /host_mnt/home/jane and /Volumes/x/home/jane",
        "/var/lib/home/jane and /System/Volumes/Data/opt/home/jane and /Volumes/home/jane",
        "http://localhost:8000/app/home/jane and http://127.0.0.1/srv/Users/jane",
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
        "Source: www.kancare.ks.gov/home/showpublisheddocument/4880/639165970250",
        "| us-va | childcare.virginia.gov/home/showpublisheddocument/65775 | PRESENT |",
        "[finances.wallonie.be/home/fiscalite](https://finances.wallonie.be/home/fiscalite)",
        "[Dashboard](http://localhost:3000/home/dashboard)",
    ],
)
def test_allow_marker_clears_text_that_is_not_a_home_path(line: str) -> None:
    assert home_path_hits(line)
    for marker in [
        f"<!-- {ALLOW_MARKER} -->",
        f"# {ALLOW_MARKER}",
        f"/* {ALLOW_MARKER} */",
    ]:
        assert not home_path_hits(f"{line} {marker}  "), marker


@pytest.mark.parametrize(
    "line",
    [
        f"<!-- {ALLOW_MARKER} --> [Sign in](https://example.org/login?next=/home/dashboard)",
        f"`{ALLOW_MARKER}` [Sign in](https://example.org/login?next=/home/dashboard)",
        f"[Sign in](https://example.org/login?next=/home/dashboard) <!-- {ALLOW_MARKER} --> |",
        "[Sign in](https://example.org/login?next=/home/dashboard) <!-- docs-home-path: allowed -->",
        "[Sign in](https://example.org/login?next=/home/dashboard) <!-- Docs-Home-Path: Allow -->",
    ],
)
def test_allow_marker_counts_only_as_the_last_token_on_its_line(line: str) -> None:
    assert home_path_hits(line)


def test_scan_is_linear_in_a_long_token() -> None:
    # 20,000 glued candidates, then one path whose 20,000 ``a/..`` pairs resolve to ``/``.
    glued = "/home/x" * 20_000
    line = f"{glued} /" + "a/../" * 20_000 + "home/jane"
    began = time.perf_counter()
    assert home_path_hits(line) == [(1, 1), (1, len(line) - len("/home/jane") + 1)]
    assert time.perf_counter() - began < 10


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
    *["/System/Volumes/Data", "http://localhost:5173/@fs", "http://[::1]"],
]
# Shell expansions, format fields and terminal escapes that can prefix an absolute path.
_PREFIXES = st.one_of(
    st.from_regex(r"\$[A-Za-z_][A-Za-z0-9_]{0,9}", fullmatch=True),
    st.from_regex(r"\$\{[A-Za-z_][A-Za-z0-9_]{0,9}\}", fullmatch=True),
    st.from_regex(r"\$\([a-z][a-z -]{0,12}\)", fullmatch=True),
    st.from_regex(r"\{[a-z_][a-z0-9_]{0,9}\}", fullmatch=True),
    st.from_regex(r"%[0-9]{0,2}[sd]", fullmatch=True),
    st.from_regex(r"(\x1b|\\033|\\e|\\x1b)\[[0-9;:]{0,16}m", fullmatch=True),
)
# Escape levels: plain, JSON-escaped, escaped twice.
_ESCAPES = st.sampled_from(["", "\\", "\\\\"])
# How the home segment may reach the name: a separator, repeated, or through ``.``.
_HOME_JOINS = st.sampled_from(["/", "//", "/./"])


def _home_path(root: str, name: str, rest: str, escape: str, join: str = "/") -> str:
    slash = escape + "/"
    return f"{slash}{root}{join.replace('/', slash)}{name}{rest.replace('/', slash)}"


@settings(max_examples=300, deadline=None)
@given(
    root=st.sampled_from(["Users", "home"]),
    name=_NAMES,
    lead=st.one_of(st.sampled_from(_LEADS), _PREFIXES),
    escape=_ESCAPES,
    join=_HOME_JOINS,
    before=st.lists(_FILLER, max_size=5),
    rest=st.sampled_from(["", "/repo"]),
    tail=_FILLER,
)
def test_any_home_path_is_reported_on_its_line(
    root: str,
    name: str,
    lead: str,
    escape: str,
    join: str,
    before: list[str],
    rest: str,
    tail: str,
) -> None:
    # Inside a sed replacement only an escaped path is valid sed.
    assume(escape or not lead.startswith("sed "))
    assume(
        ALLOW_MARKER not in tail and all(ALLOW_MARKER not in line for line in before)
    )
    text = "\n".join(
        [*before, f"{lead}{_home_path(root, name, rest, escape, join)} {tail}"]
    )
    assert home_path_hits(text) == [(len(before) + 1, len(lead) + 1)]


@settings(max_examples=300, deadline=None)
@given(
    lead=st.one_of(st.sampled_from(_LEADS), _PREFIXES),
    root=st.sampled_from(["Users", "home"]),
    name=_NAMES,
    escape=_ESCAPES,
    marker=st.sampled_from(
        [
            f"<!-- {ALLOW_MARKER} -->",
            f"# {ALLOW_MARKER}",
            f"// {ALLOW_MARKER}",
            f"/* {ALLOW_MARKER} */",
        ]
    ),
    marked_first=st.booleans(),
)
def test_allow_marker_skips_only_its_own_line(
    lead: str, root: str, name: str, escape: str, marker: str, marked_first: bool
) -> None:
    assume(escape or not lead.startswith("sed "))
    line = f"{lead}{_home_path(root, name, '', escape)}"
    marked = f"{line} {marker}"
    lines = [marked, line] if marked_first else [line, marked]
    unmarked = 2 if marked_first else 1
    assert home_path_hits("\n".join(lines)) == [(unmarked, len(lead) + 1)]


# Remote hosts only: a top-level label of letters is neither an IPv4 part nor ``localhost``.
_DNS_HOSTS = st.from_regex(
    r"[a-z0-9]([a-z0-9-]{0,10}[a-z0-9])?(\.[a-z0-9]{1,10})*\.[a-z]{2,8}", fullmatch=True
)
_REMOTE_HOSTS = st.one_of(
    _DNS_HOSTS,
    st.sampled_from(
        ["[2001:db8::1]", "93.184.215.14:443", "example.org:8080", "u@example.org"]
    ),
)
_LOCAL_HOSTS = st.sampled_from(
    [
        *[
            "localhost",
            "LOCALHOST:5173",
            "app.localhost",
            "localhost.",
            "u@localhost:80",
        ],
        *["127.0.0.1:8000", "127.1", "0x7f.0.0.1", "2130706433", "0.0.0.0:8000"],
        *[
            "[::1]",
            "[0:0:0:0:0:0:0:1]:8080",
            "[::]",
            "[::ffff:127.0.0.1]",
            "[::1%25lo0]",
        ],
    ]
)
_URL_WRAPS = st.sampled_from(
    ["{}", "[site]({})", "<{}>", "({}) and", "| {} |", '{{"url":"{}"}}']
)


@settings(max_examples=300, deadline=None)
@given(
    scheme=st.sampled_from(["http", "https", "HTTPS", "ftp", "ftps"]),
    host=_REMOTE_HOSTS,
    between=st.sampled_from(["", "/", "/#", "/app", "/wiki/Home_(film)"]),
    root=st.sampled_from(["Users", "home"]),
    name=_NAMES,
    escape=_ESCAPES,
    wrap=_URL_WRAPS,
)
def test_web_url_path_is_not_reported(
    scheme: str, host: str, between: str, root: str, name: str, escape: str, wrap: str
) -> None:
    url = f"{scheme}://{host}{between}/{root}/{name}/".replace("/", escape + "/")
    assert home_path_hits(wrap.format(url)) == []


@settings(max_examples=300, deadline=None)
@given(
    scheme=st.sampled_from(["http", "https", "HTTPS", "ftp"]),
    host=_LOCAL_HOSTS,
    between=st.sampled_from(
        ["", "/@fs", "/:x", "/a/..", "/app", "/@fs/srv", "/a/b/.."]
    ),
    root=st.sampled_from(["Users", "home"]),
    name=_NAMES,
    escape=_ESCAPES,
    wrap=_URL_WRAPS,
)
def test_local_url_path_is_scanned_like_a_file_path(
    scheme: str, host: str, between: str, root: str, name: str, escape: str, wrap: str
) -> None:
    url = f"{scheme}://{host}{between}/{root}/{name}/".replace("/", escape + "/")
    at_root = between in ("", "/@fs", "/:x", "/a/..")
    assert len(home_path_hits(wrap.format(url))) == at_root


@settings(max_examples=300, deadline=None)
@given(
    scheme=st.sampled_from(["http", "https", "HTTPS", "ftp"]),
    host=st.one_of(_REMOTE_HOSTS, _LOCAL_HOSTS),
    query=st.from_regex(
        r"/[a-z]{0,8}\?([a-z]{1,6}=[a-z0-9]{0,4}&)?[a-z_]{1,8}=", fullmatch=True
    ),
    file_url=st.sampled_from(["", "file://", "FILE://localhost"]),
    root=st.sampled_from(["Users", "home"]),
    name=_NAMES,
    escape=_ESCAPES,
    wrap=_URL_WRAPS,
)
def test_query_value_is_reported(
    scheme: str,
    host: str,
    query: str,
    file_url: str,
    root: str,
    name: str,
    escape: str,
    wrap: str,
) -> None:
    url = f"{scheme}://{host}{query}{file_url}/{root}/{name}".replace("/", escape + "/")
    assert len(home_path_hits(wrap.format(url))) == 1


_WORDS = st.from_regex(r"[A-Za-z0-9_-][A-Za-z0-9._-]{0,7}", fullmatch=True).filter(
    lambda word: word not in ("Users", "home")
)
_MOUNT_WORDS = st.sampled_from(["System", "Volumes", "Data", "host_mnt", "var", "usr"])


def _is_home_mount(path: str, root: str) -> bool:
    if root == "Users":
        return (
            path in ("/System/Volumes/Data", "/host_mnt")
            or posixpath.dirname(path) == "/Volumes"
        )
    return path in ("/System/Volumes/Data", "/var", "/usr")


@settings(max_examples=500, deadline=None)
@given(
    lead=st.sampled_from(
        ["", " ", "=", "(", '"', "|", "~", "${X}", "file://", "https://h/?p="]
    ),
    lead_escape=_ESCAPES,
    first=st.one_of(st.sampled_from(["", ".", ".."]), _WORDS),
    segments=st.lists(
        st.tuples(
            _ESCAPES, st.one_of(st.sampled_from([".", ".."]), _MOUNT_WORDS, _WORDS)
        ),
        max_size=5,
    ),
    root_escape=_ESCAPES,
    root=st.sampled_from(["Users", "home"]),
    join=_HOME_JOINS,
    name=_NAMES,
)
def test_path_is_reported_exactly_when_it_resolves_to_a_root(
    lead: str,
    lead_escape: str,
    first: str,
    segments: list[tuple[str, str]],
    root_escape: str,
    root: str,
    join: str,
    name: str,
) -> None:
    # A dot right after ``file://`` would be the URL's authority, not a relative start.
    assume(not (lead == "file://" and first in (".", "..")))
    # Each separator in front of the candidate has its own escape level.
    text = (
        lead.replace("/", lead_escape + "/")
        + first
        + "".join(f"{escape}/{segment}" for escape, segment in segments)
        + f"{root_escape}/{root}{join}{name}"
    )
    # Differential oracle: the path in front of the candidate, as posixpath resolves
    # it once its first segment or authority is dropped (it may be a prefix), sits
    # at the root or at a home mount.
    in_front = posixpath.normpath("/" + "/".join(segment for _, segment in segments))
    at_root = in_front == "/" or _is_home_mount(in_front, root)
    assert bool(home_path_hits(text)) is (first not in (".", "..") and at_root)


@settings(max_examples=300, deadline=None)
@given(
    segments=st.lists(
        st.one_of(st.sampled_from([".", ".."]), _MOUNT_WORDS, _WORDS), max_size=4
    ),
    group=st.lists(_ESCAPES, min_size=2, max_size=3).filter(
        lambda group: len(set(group)) > 1
    ),
    root=st.sampled_from(["Users", "home"]),
    name=_NAMES,
)
def test_separators_that_change_escape_level_restart_the_path(
    segments: list[str], group: list[str], root: str, name: str
) -> None:
    # As in ``sed 's/X/\\/Users\\/<name>/'``: the delimiter's plain slash ends the pattern.
    text = "s/X" + "".join(f"/{segment}" for segment in segments)
    text += "".join(f"{escape}/" for escape in group) + f"{root}/{name}"
    assert len(home_path_hits(text)) == 1
