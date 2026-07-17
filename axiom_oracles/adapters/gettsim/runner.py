"""Per-case GETTSIM oracle runner (Germany dual-oracle lane).

GETTSIM — the German Taxes and Transfers SIMulator (IZA and an academic
consortium) — is the second, independent German comparison oracle alongside
EUROMOD. It is pure Python with an explicit policy DAG, date-parameterised, and
free of take-up randomness, so it is fast and deterministic: the complement to
the EUROMOD engine path in the dual-oracle lane (rulespec-de#1).

The runner takes a :class:`GettsimCase` (hypothetical German household) plus a
``tt_targets`` tree (nested, with string leaves naming output columns), and:

1. discovers the *full* input template for the policy date
   (``MainTarget.templates.input_data_dtypes.tree``) — the reliable route,
   because per-target templates miss transitive dependencies;
2. defaults every column and overlays the case (see :mod:`.case`);
3. validates the case's input paths (GETTSIM ignores unknown inputs silently)
   and the requested targets (GETTSIM raises on unknown targets);
4. runs GETTSIM and returns a flat ``{output_name: [value per person]}`` dict in
   ``p_id`` order, with the exact ``gettsim`` version recorded in the result.

GETTSIM is an optional heavy dependency: it is imported lazily, so importing
this module (and running the pure projection tests) never requires it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from ...core.results import Value
from .case import GettsimCase, ProjectedInputs, flatten_tree, project_case
from .errors import (
    GettsimAdapterError,
    GettsimInputError,
    GettsimNotInstalledError,
    GettsimTargetError,
)

#: The Germany lane's validation policy date — rules in force 30 June 2025,
#: aligned to the EUROMOD ``DE_2025`` snapshot.
LANE_POLICY_DATE = "2025-06-30"


@dataclass(frozen=True)
class GettsimRunResult:
    """A version-pinned GETTSIM run.

    ``values`` maps each requested output column to a per-person list in
    ``p_id`` order (person ``i`` is ``values[name][i]``). The GETTSIM version
    and policy date are recorded so a comparison row is reproducible.
    """

    values: dict[str, list[Value]]
    gettsim_version: str
    policy_date_str: str
    rounding: bool

    def scalar(self, name: str) -> Value:
        """The single value of ``name`` for a one-person household.

        Raises:
            GettsimAdapterError: If the household has more than one person (the
                reduction to a household scalar is variable-specific and is left
                to the comparison suite).
        """
        column = self.values[name]
        if len(column) != 1:
            raise GettsimAdapterError(
                f"{name!r} has {len(column)} per-person values; scalar() is only "
                f"defined for one-person households — index the list instead."
            )
        return column[0]


def _gettsim() -> Any:
    """Import GETTSIM lazily, or raise a clear typed error."""
    try:
        import gettsim
    except ImportError as exc:  # pragma: no cover - exercised via the guard test
        raise GettsimNotInstalledError(
            "GETTSIM is not installed. Install the adapter's extra: "
            "uv pip install -e '.[gettsim]' (or 'uv pip install gettsim')."
        ) from exc
    return gettsim


def gettsim_version() -> str:
    """The installed ``gettsim.__version__`` (raises if GETTSIM is absent)."""
    return str(getattr(_gettsim(), "__version__", "unknown"))


class GettsimRunner:
    """Run hypothetical German households through GETTSIM as an oracle.

    Args:
        policy_date_str: The policy date GETTSIM parameterises the tax-benefit
            system to. Defaults to the lane date :data:`LANE_POLICY_DATE`
            (2025-06-30).
        rounding: Whether GETTSIM applies statutory rounding (the model default;
            keep ``True`` for statute-exact amounts).
    """

    name = "gettsim"

    def __init__(
        self,
        *,
        policy_date_str: str = LANE_POLICY_DATE,
        rounding: bool = True,
    ) -> None:
        self.policy_date_str = policy_date_str
        self.rounding = rounding

    # -- metadata ---------------------------------------------------------

    @property
    def gettsim_version(self) -> str:
        return gettsim_version()

    def run_metadata(self) -> dict[str, Any]:
        """Reproducibility metadata for a run (engine, version, date, rounding)."""
        return {
            "engine": self.name,
            "gettsim_version": self.gettsim_version,
            "policy_date_str": self.policy_date_str,
            "rounding": self.rounding,
        }

    def input_template(self) -> dict[str, Any]:
        """The nested input-dtype template for this policy date (cached)."""
        return _input_template_tree(self.policy_date_str, self.rounding)

    def flat_input_template(self) -> dict[tuple[str, ...], Any]:
        """The template flattened to ``{path_tuple: dtype}``."""
        return flatten_tree(self.input_template())

    # -- running ----------------------------------------------------------

    def compute(
        self,
        case: GettsimCase | Mapping[str, Any],
        targets: Mapping[str, Any],
    ) -> dict[str, list[Value]]:
        """Run one case and return ``{output_name: [value per person]}``.

        Args:
            case: A :class:`GettsimCase` (or a mapping accepted by
                :meth:`GettsimCase.from_mapping`).
            targets: A nested ``tt_targets`` tree whose string leaves name the
                output columns, e.g.
                ``{"sozialversicherung": {"kranken": {"beitrag":
                {"betrag_versicherter_m": "health_ee_m"}}}}``.

        Raises:
            GettsimInputError: A case input path is unknown at the policy date.
            GettsimTargetError: A requested target does not exist at the policy
                date.
            GettsimNotInstalledError: GETTSIM is not importable.
        """
        return self.run_case(case, targets).values

    def run_case(
        self,
        case: GettsimCase | Mapping[str, Any],
        targets: Mapping[str, Any],
    ) -> GettsimRunResult:
        """Run one case and return a version-pinned :class:`GettsimRunResult`."""
        # Validate targets and normalise the case first — both are pure and fail
        # fast without importing the heavy optional dependency.
        target_leaves = _target_leaves(targets)
        if not isinstance(case, GettsimCase):
            case = GettsimCase.from_mapping(case)

        gettsim = _gettsim()
        projected = project_case(case, self.flat_input_template())
        frame = self._data_frame(projected)

        values = self._run_gettsim(gettsim, frame, projected, targets, target_leaves)
        return GettsimRunResult(
            values=values,
            gettsim_version=str(getattr(gettsim, "__version__", "unknown")),
            policy_date_str=self.policy_date_str,
            rounding=self.rounding,
        )

    def _run_gettsim(
        self,
        gettsim: Any,
        frame: Any,
        projected: ProjectedInputs,
        targets: Mapping[str, Any],
        target_leaves: Sequence[str],
    ) -> dict[str, list[Value]]:
        from gettsim import InputData, MainTarget, TTTargets, main

        try:
            result = main(
                main_target=MainTarget.results.df_with_mapper,
                policy_date_str=self.policy_date_str,
                input_data=InputData.df_and_mapper(df=frame, mapper=projected.mapper),
                tt_targets=TTTargets(tree=dict(targets)),
                rounding=self.rounding,
            )
        except ValueError as exc:
            message = str(exc)
            if "no corresponding function" in message or "no corresponding" in message:
                raise GettsimTargetError(
                    f"unknown GETTSIM target(s) at policy date "
                    f"{self.policy_date_str}: {message}"
                ) from exc
            if "data columns are missing" in message:
                # Should not happen with the full template; surface loudly if it
                # ever does rather than returning a partial result.
                raise GettsimInputError(
                    f"GETTSIM reported missing input columns (unexpected with the "
                    f"full template): {message}"
                ) from exc
            raise GettsimAdapterError(
                f"GETTSIM run failed at policy date {self.policy_date_str}: "
                f"{message}"
            ) from exc

        return {
            leaf: [_coerce(v) for v in result[leaf].tolist()]
            for leaf in target_leaves
        }

    @staticmethod
    def _data_frame(projected: ProjectedInputs) -> Any:
        import pandas as pd

        return pd.DataFrame(projected.data)


def _target_leaves(targets: Mapping[str, Any]) -> list[str]:
    """The string leaves of a ``tt_targets`` tree, in order, deduplicated.

    ``None`` leaves (GETTSIM's "unnamed result column") are rejected: an oracle
    needs every output named so it can be read back and compared.
    """
    leaves: list[str] = []
    for path, leaf in flatten_tree(targets).items():
        if not isinstance(leaf, str) or not leaf:
            raise GettsimTargetError(
                f"tt_target at {'__'.join(path)!r} must have a non-empty string "
                f"leaf naming its output column (got {leaf!r})."
            )
        if leaf not in leaves:
            leaves.append(leaf)
    if not leaves:
        raise GettsimTargetError("no tt_targets requested (empty targets tree)")
    return leaves


def _coerce(value: Any) -> Value:
    """Coerce a NumPy/pandas scalar to a plain Python bool/int/float."""
    if isinstance(value, bool):
        return value
    item = value.item() if hasattr(value, "item") else value
    if isinstance(item, bool):
        return item
    if isinstance(item, int):
        return int(item)
    if isinstance(item, float):
        return float(item)
    return item


@lru_cache(maxsize=None)
def _input_template_tree(policy_date_str: str, rounding: bool) -> dict[str, Any]:
    """Discover and cache the full input-dtype template for a policy date."""
    from gettsim import MainTarget, main

    return main(
        main_target=MainTarget.templates.input_data_dtypes.tree,
        policy_date_str=policy_date_str,
        rounding=rounding,
    )
