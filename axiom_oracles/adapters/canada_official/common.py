from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests


DEFAULT_TIMEOUT_SECONDS = 30
USER_AGENT = "axiom-oracles/0.2 Canada official calculator comparison"


@dataclass(frozen=True)
class OfficialArtifact:
    url: str
    sha256: str
    fetched_at: str
    version: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "url": self.url,
            "sha256": self.sha256,
            "fetched_at": self.fetched_at,
            "version": self.version,
        }


def new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "Accept-Language": "en-CA,en;q=0.9",
            "User-Agent": USER_AGENT,
        }
    )
    return session


def artifact_from_response(
    response: requests.Response,
    *,
    version: str | None = None,
) -> OfficialArtifact:
    return OfficialArtifact(
        url=response.url,
        sha256=hashlib.sha256(response.content).hexdigest(),
        fetched_at=datetime.now(timezone.utc).isoformat(),
        version=version,
    )


def cra_json(response: requests.Response) -> Any:
    """Decode CRA JSON responses after their Angular XSSI guard prefix."""

    response.raise_for_status()
    body = response.text
    if body.startswith(")]}'"):
        body = body.split("\n", 1)[1] if "\n" in body else ""
    if not body.strip():
        return None
    return response.json() if body == response.text else __import__("json").loads(body)
