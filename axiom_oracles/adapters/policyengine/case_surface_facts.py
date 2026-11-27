"""Person facts that PolicyEngine prices on the comparison's own Case surface.

The PolicyEngine leg of a household comparison does not read the population
microdata. It rebuilds each household from the Case facts
(``PolicyEngineRunner._build_situation_from_cases``) and computes from that.
Some SNAP inputs are PolicyEngine *formulas* over that surface rather than
facts on it. The SNAP excess medical deduction is one: PolicyEngine sums the
person variable ``snap_allowable_medical_expenses`` (YEAR, USD; it adds
``medical_expense_health_insurance_premiums`` and ``other_medical_expenses``)
over members that pass ``is_usda_elderly`` or ``is_usda_disabled``. On a
populace Case surface the premium term is PolicyEngine's modeled Medicare
Part B premium net of Medicare Savings Program coverage; the Case carries no
other medical expense.

Loading the same variable from the population microsimulation would hand
Axiom a different amount: the microsimulation also counts the populace
``other_medical_expenses`` and non-Medicare premiums, which the Case does not
carry and the PolicyEngine leg never sees. For the comparison to price the
same household on both sides, this module evaluates the variables on the
exact situation the PolicyEngine leg builds and attaches the results to each
person as Case facts. The Axiom projection then reads them through
``axiom_oracles/data/populace_input_mapping.yaml``.

The PolicyEngine leg does not read these facts, so attaching them never
changes a PolicyEngine result. The CLI attaches them only when the compiled
Axiom program reads one of them (see ``program_reads_case_surface_facts``),
so a program that does not bind them projects exactly as before.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any

from ...core.case import Case, Concepts, Entity


#: Case fact -> PolicyEngine person variable(s) evaluated at the case year.
#: A tuple means "true when any of these booleans is true".
CASE_SURFACE_PERSON_FACTS: Mapping[str, tuple[str, ...]] = {
    Concepts.SNAP_ALLOWABLE_MEDICAL_EXPENSES: ("snap_allowable_medical_expenses",),
    Concepts.USDA_ELDERLY_OR_DISABLED: ("is_usda_elderly", "is_usda_disabled"),
}

_BOOLEAN_FACTS = frozenset({Concepts.USDA_ELDERLY_OR_DISABLED})

SimulationFactory = Callable[[dict], Any]


def attach_policyengine_case_surface_facts(
    cases: Sequence[Case],
    *,
    policyengine_variables: Sequence[str] | None = None,
    simulation_factory: SimulationFactory | None = None,
) -> list[Case]:
    """Return ``cases`` with :data:`CASE_SURFACE_PERSON_FACTS` on each person.

    ``policyengine_variables`` are the PolicyEngine outputs the comparison
    requests; they select the same geography inputs the PolicyEngine leg's
    situation gets. ``simulation_factory`` builds a simulation from a
    situation dict (tests pass a fake; the default is policyengine-us's
    ``Simulation``).
    """
    from .runner import PolicyEngineRunner, _policyengine_us_simulation

    cases = list(cases)
    if not cases:
        return cases
    periods = {str(case.period) for case in cases}
    if len(periods) != 1:
        raise RuntimeError(
            "PolicyEngine case-surface facts need one period per batch; "
            f"got {sorted(periods)}"
        )
    year = int(next(iter(periods)).split("-", 1)[0])
    variables = list(policyengine_variables) if policyengine_variables else None
    situation = PolicyEngineRunner()._build_situation_from_cases(
        cases, variables=variables
    )
    simulation = (simulation_factory or _policyengine_us_simulation)(situation)
    person_ids = [str(item) for item in simulation.populations["person"].ids]

    values_by_fact: dict[str, list[Any]] = {}
    for concept, pe_variables in CASE_SURFACE_PERSON_FACTS.items():
        columns = [
            [_scalar(value) for value in simulation.calculate(variable, year)]
            for variable in pe_variables
        ]
        for variable, column in zip(pe_variables, columns, strict=True):
            if len(column) != len(person_ids):
                raise RuntimeError(
                    f"PolicyEngine returned {len(column)} values for "
                    f"{variable!r}, but the situation has {len(person_ids)} people"
                )
        if concept in _BOOLEAN_FACTS:
            values_by_fact[concept] = [
                any(bool(column[index]) for column in columns)
                for index in range(len(person_ids))
            ]
        else:
            values_by_fact[concept] = [
                round(sum(float(column[index]) for column in columns), 2)
                for index in range(len(person_ids))
            ]

    index_by_person = {person_id: index for index, person_id in enumerate(person_ids)}
    attached: list[Case] = []
    for case_index, case in enumerate(cases):
        prefix = f"case_{case_index}"
        entities: list[Entity] = []
        for person_index, entity in enumerate(case.entities):
            if entity.kind != "person":
                entities.append(entity)
                continue
            situation_id = f"{prefix}__{entity.entity_id or f'person_{person_index}'}"
            index = index_by_person.get(situation_id)
            if index is None:
                raise RuntimeError(
                    f"PolicyEngine situation has no person {situation_id!r} "
                    f"for case {case.case_id!r}"
                )
            facts = dict(entity.facts)
            for concept, values in values_by_fact.items():
                facts[concept] = values[index]
            entities.append(replace(entity, facts=facts))
        attached.append(replace(case, entities=tuple(entities)))
    return attached


def program_reads_case_surface_facts(facts_read: set[str]) -> bool:
    """True when a program's projection reads any case-surface fact."""
    return bool(facts_read & set(CASE_SURFACE_PERSON_FACTS))


def _scalar(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    return value
