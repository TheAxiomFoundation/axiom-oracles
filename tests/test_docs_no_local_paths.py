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
     scanned like any other. A remote host has at most 255 characters as
     written. It is a name of letters, digits, ``_``, ``-`` and ``.`` (a
     domain name or an IPv4 address) or a bracketed IPv6 address without a
     zone, and a port of ASCII digits may follow it. It is not a local host:
     ``localhost``, ``*.localhost``, ``127.0.0.0/8`` or ``0.0.0.0/8`` in any
     IPv4 spelling, ``[::1]``, ``[::]`` or their IPv4-mapped forms. A name is
     read after Unicode compatibility normalization, with an ideographic full
     stop as ``.``, so fullwidth ``localhost`` is local. A Hangul filler is
     not a letter here, because a browser drops it from a host. A local host may
     serve its own files (``http://localhost:5173/@fs/Users/<name>``), and
     any other text in the host's place (``https://e.org~~/Users/<name>``, a
     strikethrough, ``https://example.org:hello/Users/<name>``) names no web
     server, so both paths are scanned too. A host is judged by its name
     alone, so a LAN address, a ``.local`` name, a name that resolves to
     loopback and a tunnel all count as remote;
   - the path in front of it keeps it below a filesystem root. The segments
     in front (letters, digits, ``.``, ``_``, ``-``, joined by separators)
     resolve as in ``posixpath.normpath``, and at least one must remain
     (``/opt/x/home/<name>``, ``$ROOT/x/home/<name>``) that is not a home
     mount: ``/System/Volumes/Data`` (macOS) for either root,
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
   Candidates may overlap: in ``/Volumes/home/Users/<name>``, both
   ``/home/Users`` and ``/Users/<name>`` are checked.
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
   schemeless URL (``www.kancare.ks.gov/home/showpublisheddocument/4880``) or
   a protocol-relative one (``//cdn.example.org/home/app.js``), a web route in
   a query (``?next=/home/dashboard``) or on a local server
   (``http://localhost:3000/home/dashboard``), a relative
   ``data/home/<name>``, or macOS's shared folder (``/Users/Shared``).
4. A line is scanned in time linear in its length, however many URLs,
   brackets, separators or candidates it holds. Only a host of at most 255
   characters is normalized, so this holds where Unicode normalization is
   not linear (Python 3.14.0).
5. Failures name ``file:line:column`` only, so the CI log does not republish
   the path.
"""

from __future__ import annotations

import ipaddress
import posixpath
import re
import subprocess
import time
import unicodedata
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
# Candidates may overlap (``/Volumes/home/Users/<name>``), so each is matched in a lookahead.
_CANDIDATE = re.compile(
    rf"(?={_SEPARATOR}(?P<root>Users|home)(?:{_SEPARATOR}(?:\.(?={_SEPARATOR}))?)+"
    r"(?P<name>[^\s/\\<>`'\"()\[\]{}$%*|,;:=&]+))"
)
_WEB_URL_START = re.compile(rf"(?i)\b(?:https?|ftps?):{_SEPARATOR}{_SEPARATOR}")
_PATH_ITEM = re.compile(rf"(?P<separators>(?:{_SEPARATOR})+)|[\w.-]+")
_SPELLED_SEPARATOR = re.compile(r"\\*/")
_URL_END = frozenset("<>\"'`|;")
# A candidate right after one of these (or a letter or digit) continues a URL's path.
_URL_PATH_CHARS = frozenset("-._~/#])%\\")
_AUTHORITY = re.compile(r"[^/\\?#]*")
# A host, then an optional port of ASCII digits.
_HOST_AND_PORT = re.compile(r"(\[[^\]]*\]|[^:\[\]]*)(?::[0-9]*)?")
# Letters and digits but the two Hangul fillers left after normalization: they are the only
# default-ignorable characters that are letters, and a browser drops them from a host.
_NAME = re.compile(r"(?:[^\W\u115f\u1160]|[.-])+")
# No DNS name is longer. The bound also keeps normalization linear across a line where
# normalizing a run of combining marks is quadratic (Python 3.14.0).
_MAX_HOST = 255
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
    # Leading zeros and ``0x`` carry no value, and more than 11 digits exceed 2**32 in any base.
    digits = [part.lstrip("0x") for part in parts]
    if any(len(digit) > 11 for digit in digits):
        return None
    values = [
        int(digit or "0", 16 if part[1:2] == "x" else 8 if part[0] == "0" else 10)
        for part, digit in zip(parts, digits, strict=True)
    ]
    *leading, last = values
    if any(value > 255 for value in leading) or last >= 256 ** (5 - len(values)):
        return None
    return leading[0] if leading else last >> 24


def _is_remote_host(authority: str) -> bool:
    """Whether a URL's authority names another machine: a domain name or an IP address that
    is not this machine's, whose server may serve its own files, then an optional port."""
    split = _HOST_AND_PORT.fullmatch(authority.rpartition("@")[2])
    if split is None or len(split[1]) > _MAX_HOST:
        return False
    host = split[1]
    if host.startswith("["):
        if "%" in host:  # a zone ID, which a URL cannot carry
            return False
        try:
            address = ipaddress.IPv6Address(host[1:-1])
        except ValueError:
            return False
        if address.ipv4_mapped is not None:
            return address.ipv4_mapped.packed[0] not in (0, 127)
        return not (address.is_loopback or address.is_unspecified)
    host = (
        unicodedata.normalize("NFKC", host)
        .lower()
        .replace("\u3002", ".")
        .removesuffix(".")
    )
    return (
        _NAME.fullmatch(host) is not None
        and host != "localhost"
        and not host.endswith(".localhost")
        and _ipv4_first_octet(host) not in (0, 127)
    )


def _url_ends(line: str) -> list[int]:
    """Where a URL read from each position ends: at whitespace, ``|``, ``;``, a quote or
    backtick, ``<``, ``>``, or a ``)`` or ``]`` that closes no bracket opened after the start.

    One pass from the right: from an open bracket, the URL runs to its matching close
    bracket and then on as it would from just past that bracket, so brackets nest
    (``[::1]``) and every position costs one step.
    """
    ends = [len(line)] * (len(line) + 1)
    for index in range(len(line) - 1, -1, -1):
        char = line[index]
        if char.isspace() or char in _URL_END or char in ")]":
            ends[index] = index
        elif char in "([":
            close = ends[index + 1]
            ends[index] = (
                ends[close + 1] if close < len(line) and line[close] in ")]" else close
            )
        else:
            ends[index] = ends[index + 1]
    return ends


def _web_url_paths(line: str) -> bytearray:
    """``1`` at each position past the start of a remote web URL and before its query or end."""
    inside = bytearray(len(line))
    starts = list(_WEB_URL_START.finditer(line))
    if not starts:
        return inside
    ends = _url_ends(line)
    query = marked = -1
    for match in starts:
        end = ends[match.end()]
        if not _is_remote_host(_AUTHORITY.match(line, match.end(), end)[0]):
            continue
        # URLs glued without whitespace share their end, so each position is marked once.
        if query < match.end():
            query = line.find("?", match.end())
            query = len(line) if query < 0 else query
        low, high = max(match.start() + 1, marked), min(end, query)
        if low < high:
            inside[low:high] = b"\1" * (high - low)
            marked = high
    return inside


def _continues_web_url(line: str, start: int, paths: bytearray) -> bool:
    before = line[start - 1] if start else ""
    return (before.isalnum() or before in _URL_PATH_CHARS) and bool(paths[start])


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
        # Text in a host's place names no web server.
        "~~https://e.org~~/Users/jane~~ and https://[zz]/home/jane and https:///home/jane",
        "https://[2001:db8::1]~~/Users/jane and https://example.org:hello/Users/jane",
        "https://[2001:db8::1%25eth0]/home/jane and https://"
        + "a" * 256
        + "/home/jane",
        # A host of 5,000 digits is longer than any domain name.
        "http://" + "1" * 5_000 + "/home/jane",
        # Overlapping candidates: a volume named for a root.
        "/Volumes/home/Users/jane/repo and /Volumes/Users/Users/jane/repo",
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
        "https://example.org:8080/Users/jane and https://[2001:DB8::1]:443/home/jane",
        "https://" + "a" * 251 + ".org/home/jane",
        "https://b\u00fccher.example/home/jane and https://ex_1.example.org/Users/jane",
        # A host is judged by its name, so a LAN address or a ``.local`` name counts as remote.
        "http://192.168.1.20:5173/@fs/Users/jane and http://mac.local/Users/jane",
        # A host of 250 digits is too long for an IPv4 address.
        "http://" + "1" * 250 + "/home/jane",
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
        '<script src="//cdn.example.org/home/app.js"></script>',
        "data/var/home/jane/report.json",
        "/Users/Shared/Relocated Items and /System/Volumes/Data/Users/Shared",
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


@pytest.mark.parametrize(
    ("line", "hits"),
    [
        # 20,000 glued candidates, then one path whose 20,000 ``a/..`` pairs resolve to ``/``.
        (
            "/home/x" * 20_000 + " /" + "a/../" * 20_000 + "home/jane",
            [(1, 1), (1, 240_002)],
        ),
        # 20,000 web URLs glued together, each running to the end of the line.
        ("http://a/" * 20_000 + " /home/jane", [(1, 180_002)]),
        # 20,000 web URLs, each followed by a candidate.
        (
            "https://a.b x/home/y " * 20_000,
            [(1, 14 + 21 * index) for index in range(20_000)],
        ),
        # One web URL holding 20,000 open brackets.
        ("http://a/" + "(" * 20_000 + " /home/jane", [(1, 20_011)]),
        # 20,000 overlapping candidates, then a home on a volume named for a root.
        ("/x" + "/home" * 20_000 + " /Volumes/home/Users/jane", [(1, 100_017)]),
    ],
    ids=[
        "glued-candidates",
        "glued-urls",
        "urls-and-candidates",
        "url-brackets",
        "overlap",
    ],
)
def test_scan_is_linear_in_line_length(line: str, hits: list[tuple[int, int]]) -> None:
    began = time.perf_counter()
    assert home_path_hits(line) == hits
    # A quadratic scan of these lines takes hours; a linear one takes well under a second.
    assert time.perf_counter() - began < 60


_MARKS = "\u0315\u0300"


@pytest.mark.parametrize(
    ("line", "normalized", "hits"),
    [
        # A host of 40,000 combining marks is longer than any domain name.
        ("http://a" + _MARKS * 20_000 + "/home/jane", [], [(1, 40_009)]),
        # 2,000 hosts of 254 combining marks, each followed by a candidate. Marks are not
        # letters, so no host is a name and every candidate is reported.
        (
            ("http://a" + _MARKS * 127 + "/home/jane ") * 2_000,
            ["a" + _MARKS * 127] * 2_000,
            [(1, 263 + 273 * index) for index in range(2_000)],
        ),
        # 2,000 remote hosts of 255 characters, each followed by a candidate.
        (
            ("https://" + "a" * 251 + ".org/home/jane ") * 2_000,
            ["a" * 251 + ".org"] * 2_000,
            [],
        ),
        # Only a name is normalized: not 40,000 marks in the userinfo, nor a port of 40,000
        # digits, nor anything around a bracketed address.
        ("http://" + _MARKS * 20_000 + "@a/home/jane", ["a"], []),
        ("http://a:" + "0" * 40_000 + "/home/jane", ["a"], []),
        ("http://" + _MARKS * 20_000 + "@[2001:db8::1]/home/jane", [], []),
        ("http://[2001:db8::1]:" + "0" * 40_000 + "/home/jane", [], []),
    ],
    ids=[
        *["long-host-of-marks", "hosts-of-marks", "longest-hosts", "userinfo", "port"],
        *["bracketed-userinfo", "bracketed-port"],
    ],
)
def test_each_host_is_normalized_once_and_at_most_255_characters(
    monkeypatch: pytest.MonkeyPatch,
    line: str,
    normalized: list[str],
    hits: list[tuple[int, int]],
) -> None:
    # Normalizing a run of combining marks takes quadratic time on Python 3.14.0, so
    # invariant 4 rests on this bound, which a timing on a later runtime cannot see.
    normalize, inputs = unicodedata.normalize, []

    def recording_normalize(form: str, text: str) -> str:
        inputs.append(text)
        return normalize(form, text)

    monkeypatch.setattr(unicodedata, "normalize", recording_normalize)
    assert home_path_hits(line) == hits
    assert inputs == normalized
    assert all(len(text) <= 255 for text in inputs)


def _fullwidth(text: str) -> str:
    return "".join(chr(ord(char) + 0xFEE0) for char in text)


@pytest.mark.parametrize(
    "host",
    [
        _fullwidth("localhost"),
        _fullwidth("LOCALHOST") + ":5173",
        _fullwidth("127.0.0.1"),
        "127\u30020\u30020\u30021",
        "app\uff0elocalhost",
    ],
)
def test_local_host_is_read_after_unicode_normalization(host: str) -> None:
    assert home_path_hits(f"http://{host}/home/jane") == [
        (1, len(f"http://{host}") + 1)
    ]


@pytest.mark.parametrize(
    ("authority", "remote"),
    [
        *[("example.org", True), ("example.org:8080", True), ("example.org:", True)],
        *[
            ("u:p@example.org", True),
            ("93.184.215.14", True),
            ("b\u00fccher.example", True),
        ],
        *[("[2001:db8::1]", True), ("[2001:DB8::1]:443", True), ("a" * 255, True)],
        *[
            ("example.org:hello", False),
            ("example.org:\uff18\uff10", False),
            ("e.org~~", False),
        ],
        *[("[2001:db8::1]~~", False), ("[2001:db8::1%25eth0]", False), ("[zz]", False)],
        *[("", False), ("a" * 256, False), ("1" * 256, False), ("a[b]", False)],
        *[("localhost:5173", False), ("[::1]:8000", False), ("[2001:db8::1]:", True)],
        *[
            ("[::1]", False),
            ("[::ffff:127.0.0.1]", False),
            ("127.1", False),
            ("0x7f.1", False),
        ],
        *[
            ("127.0.0.\u115f1", False),
            ("local\u1160host", False),
            ("\u3164example.org", False),
        ],
        *[("example.org\uffa0", False), ("\uc608\uc2dc.example", True)],
    ],
)
def test_remote_host_is_a_name_or_address_then_a_port_of_digits(
    authority: str, remote: bool
) -> None:
    assert _is_remote_host(authority) is remote


@pytest.mark.parametrize(
    ("host", "local"),
    [
        ("0x" + "0" * 240 + "7f.1", True),
        ("0" * 240 + "177.1", True),
        ("1" * 250, False),
        ("0x1" + "0" * 8, False),
    ],
)
def test_ipv4_host_of_many_digits_is_read(host: str, local: bool) -> None:
    assert len(home_path_hits(f"http://{host}/home/jane")) == local


def _walk_url_end(line: str, start: int) -> int:
    """Where a URL read from ``start`` ends, one character at a time: the walk ``_url_ends``
    replaces."""
    end, depth = start, 0
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
    return end


@settings(max_examples=1000, deadline=None)
@given(line=st.text(alphabet='a/?([ ])|;<"', max_size=60))
def test_url_ends_agree_with_a_walk_from_each_position(line: str) -> None:
    assert _url_ends(line) == [
        _walk_url_end(line, start) for start in range(len(line) + 1)
    ]


_URL_PIECES = st.sampled_from(
    [
        *[
            "http://",
            "HTTPS://",
            "ftp:\\/\\/",
            "https:/\\/",
            "a",
            "a.b",
            "localhost",
            "127.1",
        ],
        *[
            "[::1]",
            "[2001:db8::1]",
            "e.org~~",
            "/",
            "\\/",
            "?",
            "#",
            " ",
            "(",
            ")",
            "[",
            "]",
        ],
        *["|", "x", "/home/", "u@"],
    ]
)


@settings(max_examples=1000, deadline=None)
@given(line=st.lists(_URL_PIECES, max_size=24).map("".join))
def test_web_url_paths_agree_with_one_url_at_a_time(line: str) -> None:
    # Differential oracle: each remote URL's span, walked on its own, as before the
    # single pass.
    spans = []
    for match in _WEB_URL_START.finditer(line):
        end = _walk_url_end(line, match.end())
        if _is_remote_host(_AUTHORITY.match(line, match.end(), end)[0]):
            query = line.find("?", match.end(), end)
            spans.append((match.start(), end if query < 0 else query))
    expected = [
        any(start < index < end for start, end in spans) for index in range(len(line))
    ]
    assert [bool(flag) for flag in _web_url_paths(line)] == expected


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


# Remote hosts only: a top-level label of letters is neither an IPv4 part nor ``localhost``,
# and at most ten labels keep a host under 255 characters.
_DNS_HOSTS = st.from_regex(
    r"[a-z0-9]([a-z0-9-]{0,10}[a-z0-9])?(\.[a-z0-9]{1,10}){0,8}\.[a-z]{2,8}",
    fullmatch=True,
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


_WORDS = st.from_regex(r"[A-Za-z0-9_-][A-Za-z0-9._-]{0,7}", fullmatch=True)
# Mount words, and the roots themselves, which may name a volume or a directory.
_MOUNT_WORDS = st.sampled_from(
    ["System", "Volumes", "Data", "host_mnt", "var", "usr", "Users", "home"]
)


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
    candidate = f"{root_escape}/{root}{join}{name}"
    text = (
        lead.replace("/", lead_escape + "/")
        + first
        + "".join(f"{escape}/{segment}" for escape, segment in segments)
        + candidate
    )
    # Differential oracle: the path in front of the candidate, as posixpath resolves
    # it once its first segment or authority is dropped (it may be a prefix), sits
    # at the root or at a home mount. A segment in front may itself be a root and
    # start a candidate of its own, so only the last candidate's column is checked.
    in_front = posixpath.normpath("/" + "/".join(segment for _, segment in segments))
    at_root = in_front == "/" or _is_home_mount(in_front, root)
    reported = (1, len(text) - len(candidate) + 1) in home_path_hits(text)
    assert reported is (first not in (".", "..") and at_root)


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
    candidate = f"{group[-1]}/{root}/{name}"
    text = "s/X" + "".join(f"/{segment}" for segment in segments)
    text += "".join(f"{escape}/" for escape in group[:-1]) + candidate
    assert (1, len(text) - len(candidate) + 1) in home_path_hits(text)
