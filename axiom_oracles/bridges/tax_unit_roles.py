"""The Populace constructor's tax-unit roles, in every PolicyEngine-US simulation over it.

The certified Populace US artifact ships the tax units its constructor built,
with each member's role in the person column ``tax_unit_role_input``
(``HEAD`` / ``SPOUSE`` / ``DEPENDENT``). PolicyEngine-US before 2.34.0 has no
variable of that name, so its loader drops the column and the role variables
rank members by age instead. In PolicyEngine-US 1.764.6:

- ``is_tax_unit_head``: ``person.get_rank(tax_unit, -age, ~is_child) == 0``,
  the oldest member who is not a child;
- ``is_tax_unit_spouse``: the next-oldest such member, unless the unit is
  separated.

On the pinned artifact that age ranking makes 1,056 adults the constructor
marks ``DEPENDENT`` a filer, and files their units as joint returns
(axiom-oracles#633). Filing status, the dependents, every credit and the
bridge's own filers all follow those role flags.

PolicyEngine/policyengine-us#9617 (first released in 2.34.0) adds
``tax_unit_role_input`` and makes ``is_tax_unit_head`` / ``is_tax_unit_spouse``
use it when every member of the unit has a role.
:func:`apply_source_tax_unit_roles` gives a simulation that rule whatever
PolicyEngine-US is installed:

- a PolicyEngine-US with a ``tax_unit_role_input`` variable reads the column
  itself (:data:`ROLES_NATIVE`);
- an older one gets the same roles as ``is_tax_unit_head`` /
  ``is_tax_unit_spouse`` inputs (:data:`ROLES_INPUTS`).

It then checks the simulation's role flags against the constructor's roles,
and raises :class:`SourceTaxUnitRoleError` if any differ. Everything that reads
the flags therefore describes the constructor's unit:

- PolicyEngine's own outputs: filing status, dependents, credits, the
  Medicaid MAGI household;
- the tax bridge's filers and person contexts;
- the Populace Case loader's relations;
- the state-tax campaign's filers.

Filing status itself is never supplied. PolicyEngine computes it from the
roles (decision d318, which #9617 follows), and the artifact's
``filing_status_input`` column is not read.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

#: The Populace person column holding each member's constructor role.
ROLE_COLUMN = "tax_unit_role_input"
#: The PolicyEngine-US role flags the constructor's roles decide.
ROLE_FLAGS = ("is_tax_unit_head", "is_tax_unit_spouse")
SUPPLIED_ROLES = frozenset({"HEAD", "SPOUSE", "DEPENDENT"})
#: Values that mean "no role supplied": an empty cell, or the enum default of
#: PolicyEngine-US's ``tax_unit_role_input``.
UNSUPPLIED_ROLES = frozenset({"", "UNSPECIFIED"})

ROLES_ABSENT = "absent"
ROLES_NATIVE = "native"
ROLES_INPUTS = "inputs"


class SourceTaxUnitRoleError(ValueError):
    """The constructor's roles are malformed, or a simulation does not follow them."""


def normalize_role(value: Any) -> str:
    """``tax_unit_role_input`` as an upper-case string; unsupplied is ``""``."""
    if isinstance(value, bytes):
        value = value.decode()
    if value is None or (isinstance(value, float) and value != value):  # NaN
        return ""
    name = getattr(value, "name", None)
    role = str(name if isinstance(name, str) else value).strip().upper()
    if role.startswith("TAXUNITROLE."):
        role = role.removeprefix("TAXUNITROLE.")
    return "" if role in UNSUPPLIED_ROLES else role


def source_tax_unit_roles(person_table: Any) -> dict[int, str] | None:
    """The constructor's role for every member of a unit whose roles are supplied.

    Returns ``None`` when the table has no ``tax_unit_role_input`` column. A
    unit whose members all lack a role is left out, so PolicyEngine's own rule
    decides it. The rules are PolicyEngine-US's ``tax_unit_roles_supplied``
    (#9617): a unit that supplies roles for only some members, or that does
    not name exactly one ``HEAD`` and at most one ``SPOUSE``, is an error, not
    a silent fallback.
    """
    if person_table is None or ROLE_COLUMN not in getattr(person_table, "columns", ()):
        return None
    missing = {"person_id", "person_tax_unit_id"} - set(person_table.columns)
    if missing:
        raise SourceTaxUnitRoleError(
            f"Populace person table has {ROLE_COLUMN} but lacks "
            + ", ".join(sorted(missing))
        )
    members: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for person_id, tax_unit_id, value in zip(
        person_table["person_id"],
        person_table["person_tax_unit_id"],
        person_table[ROLE_COLUMN],
        strict=True,
    ):
        role = normalize_role(value)
        if role and role not in SUPPLIED_ROLES:
            raise SourceTaxUnitRoleError(
                f"person_id {int(person_id)} has unknown {ROLE_COLUMN} {value!r}"
            )
        members[int(tax_unit_id)].append((int(person_id), role))

    roles: dict[int, str] = {}
    for tax_unit_id, unit in members.items():
        supplied = [role for _, role in unit if role]
        if not supplied:
            continue
        if len(supplied) != len(unit):
            raise SourceTaxUnitRoleError(
                f"tax_unit_id {tax_unit_id} supplies {ROLE_COLUMN} for "
                f"{len(supplied)} of its {len(unit)} members; supply a role "
                "for every member of a tax unit, or for none"
            )
        heads = supplied.count("HEAD")
        spouses = supplied.count("SPOUSE")
        if heads != 1 or spouses > 1:
            raise SourceTaxUnitRoleError(
                f"tax_unit_id {tax_unit_id} has {heads} HEAD and {spouses} "
                f"SPOUSE {ROLE_COLUMN} rows; a unit needs exactly one HEAD and "
                "at most one SPOUSE"
            )
        roles.update(unit)
    return roles


def role_years(*, data_year: int, year: int) -> tuple[int, ...]:
    """The years whose role flags are set as inputs: the data year through the
    comparison year, plus one year either side, for formulas that read the
    previous or the next year."""
    first, last = sorted((int(data_year), int(year)))
    return tuple(range(first - 1, last + 2))


def policyengine_reads_role_input(sim: Any) -> bool:
    """Whether the installed PolicyEngine-US has #9617's ``tax_unit_role_input``."""
    system = getattr(sim, "tax_benefit_system", None)
    variables = getattr(system, "variables", None) or {}
    return ROLE_COLUMN in variables


def apply_source_tax_unit_roles(
    sim: Any,
    person_table: Any,
    *,
    data_year: int,
    year: int,
) -> str:
    """Make ``sim``'s role flags the constructor's roles, then verify them.

    ``data_year`` is the year the dataset's inputs belong to and ``year`` the
    year being compared. Returns:

    - :data:`ROLES_ABSENT` when ``person_table`` carries no supplied roles;
    - :data:`ROLES_NATIVE` when PolicyEngine-US reads them itself;
    - :data:`ROLES_INPUTS` when they were set as ``is_tax_unit_head`` /
      ``is_tax_unit_spouse`` inputs for each of :func:`role_years`.

    Members of units without supplied roles keep PolicyEngine's own flags.
    The flags are verified for every year from ``data_year`` to ``year``.

    Call it before anything that depends on the roles is calculated, and after
    any ``subsample``, because subsampling rebuilds the simulation.
    """
    roles = source_tax_unit_roles(person_table)
    if not roles:
        return ROLES_ABSENT
    import numpy as np

    person_ids = _person_ids(sim, data_year)
    # Roles are matched by person_id. A simulation person missing from the
    # table (a loader that renumbered people) would otherwise read as having
    # no supplied role and keep PolicyEngine's age ranking unnoticed.
    table_ids = {int(value) for value in person_table["person_id"]}
    unknown = [pid for pid in person_ids if pid not in table_ids]
    if unknown:
        raise SourceTaxUnitRoleError(
            f"{len(unknown)} simulation people are not in the Populace person "
            f"table (person_id {', '.join(str(pid) for pid in unknown[:5])}), "
            "so their roles cannot be matched"
        )
    supplied = np.array([pid in roles for pid in person_ids], dtype=bool)
    source = {
        flag: np.array([roles.get(pid) == role for pid in person_ids], dtype=bool)
        for flag, role in zip(ROLE_FLAGS, ("HEAD", "SPOUSE"), strict=True)
    }
    native = policyengine_reads_role_input(sim)
    if not native:
        for input_year in role_years(data_year=data_year, year=year):
            if supplied.all():
                values = source
            else:
                # Read both of PolicyEngine's flags before setting either:
                # its spouse formula reads the head flag.
                computed = {
                    flag: _bool_array(sim.calculate(flag, input_year))
                    for flag in ROLE_FLAGS
                }
                values = {
                    flag: np.where(supplied, source[flag], computed[flag])
                    for flag in ROLE_FLAGS
                }
            for flag in ROLE_FLAGS:
                sim.set_input(flag, input_year, values[flag])
    first, last = sorted((int(data_year), int(year)))
    verify_source_tax_unit_roles(
        sim,
        person_ids=person_ids,
        supplied=supplied,
        source=source,
        years=tuple(range(first, last + 1)),
    )
    return ROLES_NATIVE if native else ROLES_INPUTS


def verify_source_tax_unit_roles(
    sim: Any,
    *,
    person_ids: list[int],
    supplied: Any,
    source: dict[str, Any],
    years: tuple[int, ...],
) -> None:
    """Raise unless ``sim``'s role flags equal the supplied roles in ``years``."""
    import numpy as np

    for year in years:
        for flag in ROLE_FLAGS:
            values = _bool_array(sim.calculate(flag, year))
            if len(values) != len(person_ids):
                raise SourceTaxUnitRoleError(
                    f"PolicyEngine {flag} returned {len(values)} rows for "
                    f"{len(person_ids)} people in {year}"
                )
            wrong = np.flatnonzero(supplied & (values != source[flag]))
            if len(wrong):
                examples = ", ".join(str(person_ids[i]) for i in wrong[:5])
                raise SourceTaxUnitRoleError(
                    f"PolicyEngine {flag} differs from the Populace "
                    f"{ROLE_COLUMN} for {len(wrong)} people in {year} "
                    f"(person_id {examples})"
                )


def populace_us_microsimulation(dataset: Any, *, data_year: int, year: int) -> Any:
    """A PolicyEngine-US ``Microsimulation`` over ``dataset`` that follows the
    constructor's tax-unit roles (:func:`apply_source_tax_unit_roles`)."""
    from policyengine_us import Microsimulation

    sim = Microsimulation(dataset=dataset)
    apply_source_tax_unit_roles(
        sim, dataset_person_table(dataset), data_year=data_year, year=year
    )
    return sim


def dataset_person_table(dataset: Any) -> Any:
    """``dataset``'s person table, or ``None`` when it exposes none."""
    table = getattr(dataset, "person", None)
    if table is None and hasattr(dataset, "data"):
        table = getattr(dataset.data, "person", None)
    return table


def dataset_year(dataset: Any, default: int) -> int:
    """The year a PolicyEngine dataset's inputs belong to."""
    value = getattr(dataset, "time_period", None)
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return int(default)


def _person_ids(sim: Any, year: int) -> list[int]:
    import numpy as np

    return [int(value) for value in np.asarray(sim.calculate("person_id", year))]


def _bool_array(values: Any) -> Any:
    import numpy as np

    raw = values.values if hasattr(values, "values") else values
    return np.asarray(raw).astype(bool)
