"""Typed errors for the GETTSIM oracle adapter.

GETTSIM's own failure modes are asymmetric, which is exactly why the adapter
raises its own typed errors instead of leaking framework exceptions:

- An **unknown target** raises a plain ``ValueError`` from GETTSIM ("The
  following targets have no corresponding function"). The adapter wraps it in
  :class:`GettsimTargetError`.
- An **unknown input path** is *silently ignored* by GETTSIM — a mistyped
  input column simply does nothing and the run returns a value computed from
  the default template, with no warning. The adapter therefore validates every
  case-supplied input path against the discovered template *before* running and
  raises :class:`GettsimInputError` — this is the guard that turns a typo from a
  silent wrong number into a loud failure.
"""

from __future__ import annotations


class GettsimAdapterError(Exception):
    """Base class for every GETTSIM adapter error."""


class GettsimNotInstalledError(GettsimAdapterError, RuntimeError):
    """Raised when the optional ``gettsim`` dependency is not importable."""


class GettsimInputError(GettsimAdapterError, KeyError):
    """Raised when a case supplies an input path GETTSIM does not define.

    GETTSIM ignores unrecognised input columns without complaint, so the
    adapter validates paths against the policy-date input template and raises
    this instead of returning a silently-defaulted result.
    """

    def __str__(self) -> str:  # KeyError repr adds quotes; keep the message plain
        return self.args[0] if self.args else self.__class__.__name__


class GettsimTargetError(GettsimAdapterError, KeyError):
    """Raised when a requested ``tt_target`` does not exist at the policy date."""

    def __str__(self) -> str:
        return self.args[0] if self.args else self.__class__.__name__
