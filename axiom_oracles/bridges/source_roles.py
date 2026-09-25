"""Pin PolicyEngine's tax-unit roles and filing status to the Populace build's own.

A Populace US artifact records who heads each tax unit and how it files:

- ``person.tax_unit_role_input`` -- ``HEAD``, ``SPOUSE`` or ``DEPENDENT``;
- ``tax_unit.filing_status_input`` -- a PolicyEngine ``FilingStatus`` name
  (``SINGLE``, ``JOINT``, ``SEPARATE``, ``HEAD_OF_HOUSEHOLD``,
  ``SURVIVING_SPOUSE``).

policyengine-us (checked at 1.752.2, 1.764.6 and 2.2.1) has no variable that
reads either column, so the engine drops them on load and derives the roles
from ages instead: ``is_tax_unit_head`` is the oldest non-child and
``is_tax_unit_spouse`` the next oldest. On the certified
``populace-us-2024-spm-20260915`` build that rule turns 1,161 source
dependents into spouses (making those returns joint), gives 13,217 tax units a
different or missing head, and leaves 252 units -- almost all a lone minor --
with no head at all. Every comparison that reads roles or filing status from
the population simulation inherits that error on both sides.

The fix mirrors PolicyEngine/policyengine-taxsim#1216 (``source_roles`` /
``pin_source_roles`` in ``scripts/convert_h5_to_taxsim.py``): read the build's
columns and make PolicyEngine use them. Two entry points:

- :func:`attach_source_roles` (preferred) writes ``is_tax_unit_head``,
  ``is_tax_unit_spouse``, ``is_tax_unit_dependent`` and ``filing_status`` into
  the dataset's own entity tables *before* a ``Microsimulation`` is built.
  policyengine-us extends a single-year dataset to every projection year and
  ``set_input``\\ s each variable column at each year, so the pin covers 2024,
  2026, 2027 and month periods alike, and survives ``sim.subsample()``.
- :func:`pin_source_roles` is the simulation-level fallback for a
  ``Microsimulation`` built from a path. It ``set_input``\\ s every data year and
  refuses to run once a role variable has been calculated, because
  ``set_input`` after a calculation leaves dependent values cached and stale.

A dataset without the columns (the variable-centric legacy eCPS and NYC files,
UK artifacts, test doubles) is left untouched. A dataset whose columns are
present but incomplete or contradictory raises :class:`SourceRoleError` rather
than being half-pinned: the pre-certified ``f0af251`` pin, for example, has no
``filing_status_input`` for 10,384 tax units.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROLE_COLUMN = "tax_unit_role_input"
FILING_STATUS_COLUMN = "filing_status_input"
PERSON_TAX_UNIT_COLUMN = "person_tax_unit_id"

#: Source role -> the PolicyEngine boolean it sets.
ROLE_VARIABLES: dict[str, str] = {
    "HEAD": "is_tax_unit_head",
    "SPOUSE": "is_tax_unit_spouse",
    "DEPENDENT": "is_tax_unit_dependent",
}
FILING_STATUS_VARIABLE = "filing_status"
#: PolicyEngine-US ``FilingStatus`` enum names the source column may hold.
FILING_STATUSES = frozenset(
    {"SINGLE", "JOINT", "SEPARATE", "HEAD_OF_HOUSEHOLD", "SURVIVING_SPOUSE"}
)
PINNED_VARIABLES = (*ROLE_VARIABLES.values(), FILING_STATUS_VARIABLE)
#: Variables PolicyEngine derives from the pinned ones. If any already holds a
#: value when :func:`pin_source_roles` runs, the pin would leave it stale.
DERIVED_ROLE_VARIABLES = (
    "is_tax_unit_head_or_spouse",
    "tax_unit_is_joint",
    "tax_unit_dependents",
)

#: Opt-out switch, for reproducing reports generated before the pin existed.
#: Any of ``0``/``false``/``no``/``off`` disables the pin; unset means enabled.
SOURCE_ROLES_ENV = "AXIOM_POPULACE_SOURCE_ROLES"
#: Provenance label recorded when the pin is applied.
SOURCE_ROLES_LABEL = f"{ROLE_COLUMN}+{FILING_STATUS_COLUMN}"


class SourceRoleError(ValueError):
    """The build carries role columns, but they cannot be pinned as they are."""


@dataclass(frozen=True)
class SourceRoles:
    """The build's roles, keyed by id so any row order or subset can align.

    ``person_role`` maps ``person_id`` to ``HEAD``/``SPOUSE``/``DEPENDENT``;
    ``tax_unit_filing_status`` maps ``tax_unit_id`` to a ``FilingStatus`` name.
    Both are pandas Series.
    """

    person_role: Any
    tax_unit_filing_status: Any

    @property
    def person_count(self) -> int:
        return len(self.person_role)

    @property
    def tax_unit_count(self) -> int:
        return len(self.tax_unit_filing_status)


def source_roles_enabled() -> bool:
    """Return False only when :data:`SOURCE_ROLES_ENV` explicitly disables it."""
    value = (os.environ.get(SOURCE_ROLES_ENV) or "").strip().lower()
    return value not in {"0", "false", "no", "off"}


def read_source_roles(source: Any) -> SourceRoles | None:
    """Read and validate the build's roles, or return None when it has none.

    ``source`` is a dataset exposing ``person`` and ``tax_unit`` DataFrames
    (directly or under ``.data``), or a path to an entity-table H5. Returns
    None -- meaning "nothing to pin" -- when there are no entity tables (a
    variable-centric H5, a test double) or either column is absent. Raises
    :class:`SourceRoleError` when the columns exist but a value is missing or
    unknown, a tax unit does not have exactly one HEAD, a unit has more than
    one SPOUSE, a JOINT unit has no SPOUSE, or a non-JOINT unit has one.
    """
    tables = _entity_tables(source)
    if tables is None:
        return None
    person, tax_unit = tables
    if (
        ROLE_COLUMN not in person.columns
        or FILING_STATUS_COLUMN not in tax_unit.columns
    ):
        return None

    import pandas as pd

    role = _decoded(person[ROLE_COLUMN])
    status = _decoded(tax_unit[FILING_STATUS_COLUMN])
    _require_known(role, ROLE_COLUMN, frozenset(ROLE_VARIABLES))
    _require_known(status, FILING_STATUS_COLUMN, FILING_STATUSES)
    for frame, column in (
        (person, "person_id"),
        (person, PERSON_TAX_UNIT_COLUMN),
        (tax_unit, "tax_unit_id"),
    ):
        if column not in frame.columns:
            raise SourceRoleError(f"Cannot align source roles without {column!r}.")
    person_ids = person["person_id"].to_numpy()
    tax_unit_ids = tax_unit["tax_unit_id"].to_numpy()
    if len(set(person_ids)) != len(person_ids) or len(set(tax_unit_ids)) != len(
        tax_unit_ids
    ):
        raise SourceRoleError("person_id and tax_unit_id must be unique.")

    members = person[PERSON_TAX_UNIT_COLUMN].to_numpy()
    heads = pd.Series(role.to_numpy() == "HEAD").groupby(members).sum()
    spouses = pd.Series(role.to_numpy() == "SPOUSE").groupby(members).sum()
    heads = heads.reindex(tax_unit_ids, fill_value=0)
    spouses = spouses.reindex(tax_unit_ids, fill_value=0)
    _require_units(heads != 1, tax_unit_ids, "does not have exactly one HEAD")
    _require_units(spouses > 1, tax_unit_ids, "has more than one SPOUSE")
    joint = status.to_numpy() == "JOINT"
    has_spouse = spouses.to_numpy() == 1
    _require_units(joint & ~has_spouse, tax_unit_ids, "files JOINT without a SPOUSE")
    _require_units(
        ~joint & has_spouse, tax_unit_ids, "has a SPOUSE but does not file JOINT"
    )
    orphans = set(members) - set(tax_unit_ids)
    if orphans:
        raise SourceRoleError(
            f"{len(orphans)} person_tax_unit_id value(s) name no tax unit, "
            f"e.g. {sorted(orphans)[:5]}."
        )

    return SourceRoles(
        person_role=pd.Series(role.to_numpy(dtype=str), index=person_ids),
        tax_unit_filing_status=pd.Series(
            status.to_numpy(dtype=str), index=tax_unit_ids
        ),
    )


def attach_source_roles(dataset: Any) -> SourceRoles | None:
    """Write the build's roles into ``dataset``'s entity tables, in place.

    Adds boolean ``is_tax_unit_head``/``is_tax_unit_spouse``/
    ``is_tax_unit_dependent`` columns to the person table and a
    ``filing_status`` name column to the tax-unit table. Call it before
    ``Microsimulation(dataset=dataset)``. Idempotent. Returns the roles pinned,
    or None when the dataset has none (it is then left untouched).
    """
    roles = read_source_roles(dataset)
    if roles is None:
        return None
    person, tax_unit = _entity_tables(dataset)
    role = roles.person_role.reindex(person["person_id"].to_numpy()).to_numpy()
    for name, variable in ROLE_VARIABLES.items():
        person[variable] = role == name
    tax_unit[FILING_STATUS_VARIABLE] = roles.tax_unit_filing_status.reindex(
        tax_unit["tax_unit_id"].to_numpy()
    ).to_numpy(dtype=object)
    return roles


def pin_source_roles(
    sim: Any,
    roles: SourceRoles | None,
    *,
    periods: Iterable[Any] | None = None,
) -> tuple[str, ...]:
    """``set_input`` the build's roles on an existing simulation.

    ``periods`` defaults to every year at which the simulation holds data (the
    known periods of ``household_weight``): a pin at the data year alone does
    not reach 2026, where PolicyEngine would run its age-based formula again.
    Raises :class:`SourceRoleError` when a pinned or derived role variable has
    already been calculated at a target period, or when the roles do not cover
    every simulated person and tax unit. Returns the periods pinned; a None
    ``roles`` pins nothing.
    """
    if roles is None:
        return ()
    targets = (
        [str(period) for period in periods] if periods is not None else _data_years(sim)
    )
    import numpy as np

    for period in targets:
        for variable in (*PINNED_VARIABLES, *DERIVED_ROLE_VARIABLES):
            if period in {str(known) for known in _known_periods(sim, variable)}:
                raise SourceRoleError(
                    f"{variable} already holds a value at {period}; pin source "
                    "roles before calculating anything that depends on them."
                )
        person_ids = np.asarray(sim.calculate("person_id", period).values)
        tax_unit_ids = np.asarray(sim.calculate("tax_unit_id", period).values)
        role = roles.person_role.reindex(person_ids)
        status = roles.tax_unit_filing_status.reindex(tax_unit_ids)
        if role.isna().any() or status.isna().any():
            raise SourceRoleError(
                f"Source roles do not cover every simulated person and tax unit "
                f"at {period}."
            )
        role_values = role.to_numpy(dtype=str)
        for name, variable in ROLE_VARIABLES.items():
            sim.set_input(variable, period, role_values == name)
        sim.set_input(FILING_STATUS_VARIABLE, period, status.to_numpy(dtype=str))
    return tuple(targets)


def _entity_tables(source: Any) -> tuple[Any, Any] | None:
    if source is None:
        return None
    if isinstance(source, (str, Path)):
        return _h5_entity_tables(Path(source))
    person = _table(source, "person")
    tax_unit = _table(source, "tax_unit")
    if person is None or tax_unit is None:
        return None
    return person, tax_unit


def _table(dataset: Any, name: str) -> Any:
    import pandas as pd

    for holder in (dataset, _safe_getattr(dataset, "data")):
        table = _safe_getattr(holder, name)
        if isinstance(table, pd.DataFrame):
            return table
    return None


def _safe_getattr(obj: Any, name: str) -> Any:
    # A policyengine-core Dataset raises TypeError (not AttributeError) for an
    # unknown table name once a simulation has been subsampled.
    if obj is None:
        return None
    try:
        return getattr(obj, name, None)
    except (AttributeError, TypeError, KeyError):
        return None


def _h5_entity_tables(path: Path) -> tuple[Any, Any] | None:
    if path.suffix != ".h5" or not path.is_file():
        return None
    import pandas as pd

    with pd.HDFStore(path, mode="r") as store:
        if not {"/person", "/tax_unit"} <= set(store.keys()):
            return None  # variable-centric H5 (legacy eCPS, NYC.h5)
        return store["person"], store["tax_unit"]


def _decoded(series: Any) -> Any:
    return series.map(
        lambda value: value.decode() if isinstance(value, bytes) else value
    )


def _require_known(values: Any, column: str, allowed: frozenset[str]) -> None:
    missing = int(values.isna().sum())
    unknown = sorted({str(v) for v in values.dropna().unique()} - allowed)
    if missing or unknown:
        raise SourceRoleError(
            f"{column} cannot be pinned: {missing} missing value(s)"
            + (f", unknown value(s) {unknown}" if unknown else "")
            + f". Set {SOURCE_ROLES_ENV}=0 to load without source roles."
        )


def _require_units(mask: Any, tax_unit_ids: Any, problem: str) -> None:
    import numpy as np

    bad = np.asarray(mask, dtype=bool)
    if bad.any():
        examples = [int(v) for v in np.asarray(tax_unit_ids)[bad][:5]]
        raise SourceRoleError(
            f"{int(bad.sum())} tax unit(s) {problem}, e.g. tax_unit_id {examples}."
        )


def _known_periods(sim: Any, variable: str) -> list[Any]:
    try:
        return list(sim.get_known_periods(variable))
    except Exception:  # noqa: BLE001 - a variable the model lacks has no periods
        return []


def _data_years(sim: Any) -> list[str]:
    years = {
        str(period)
        for period in _known_periods(sim, "household_weight")
        if str(getattr(period, "unit", "year")).lower().endswith("year")
    }
    if not years:
        default = getattr(sim, "default_calculation_period", None)
        if default is None:
            raise SourceRoleError(
                "Cannot tell which years the simulation holds; pass periods=."
            )
        years = {str(default)}
    return sorted(years)
