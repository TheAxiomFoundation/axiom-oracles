"""Germany 2025 Kindergeld child-eligibility grid (§ 63 with § 32 EStG).

The canonical worker grid (``de_worker.py``) fixes its children at ages 7 and
10, so the age, education and working-hours conditions of § 32 Abs. 3–5 EStG
are never exercised against the oracles. This grid varies exactly those
conditions on a single-parent West household earning EUR 4,000 nominal per
month, one threshold per case:

* age 17 (§ 32 Abs. 3: unconditional until the completed 18th year);
* age 18 in training / not in training (§ 32 Abs. 4 Satz 1 Nr. 2 Buchst. a);
* age 24 in training (last month under 25) and age 25 in training (limit);
* age 22 in training working 20 h / 25 h a week (§ 32 Abs. 4 Satz 2–3, the
  20-hour rule — GETTSIM applies it to every child in training, the statute
  only after a first training or degree is completed; see the playbook);
* one eligible and one ineligible child together.

What the oracles cannot express is deliberately not in this grid: the
job-seeking ground for 18–20-year-olds (§ 32 Abs. 4 Satz 1 Nr. 1), the
disability ground (Nr. 3), foster children, the § 62 residence-title
conditions, § 64 priority and § 65 exclusions. Those rest on statute-bound
proof atoms in rulespec-de, not on an oracle.

GETTSIM 1.2.1 inputs: ``kindergeld__in_ausbildung`` and ``arbeitsstunden_w`` on
the child, ``kindergeld__p_id_empfänger`` via ``kindergeld_recipients``. Its
rule ``kindergeld.ist_leistungsbegründendes_kind`` is ``alter < 18 or (alter <
25 and in_ausbildung and arbeitsstunden_w <= 20)``. EUROMOD DE_2025 receives
the child as ``les = 6`` / ``dec = 1`` when in training, ``les = 1`` / ``dec = 0``
otherwise, and ``lhw``/``liwwh`` for the working child.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.case import Case, Concepts, Entity
from .de_worker import (
    DE_INPUT_UPRATING_FACTOR,
    DE_SCOPE,
    DE_WORKER_PERIOD,
    _euromod_person,
)

#: The dual-oracle comparison compares the household amount only: EUROMOD has
#: no per-child eligibility output. The qualifying-child concept is read from
#: GETTSIM through DE_KINDERGELD_GETTSIM_TARGETS (live anchors) and attaches to
#: the Axiom leg once rulespec-de encodes §§ 63/32.
DE_KINDERGELD_ELIGIBILITY_OUTPUTS = (Concepts.DE_KINDERGELD_MONTHLY,)

#: GETTSIM targets for this grid: the household amount, the recipient's claim
#: count, and the per-child eligibility judgement (read per person; the
#: comparison reduces the first two with SUM).
DE_KINDERGELD_GETTSIM_TARGETS = {
    "kindergeld": {
        "betrag_m": "kindergeld.betrag_m",
        "anzahl_ansprüche": "kindergeld.anzahl_ansprüche",
        "ist_leistungsbegründendes_kind": "kindergeld.ist_leistungsbegründendes_kind",
    },
}

_PARENT_MONTHLY_EARNINGS = 4000.0
_PARENT_AGE = 45


@dataclass(frozen=True)
class _Child:
    birth_year: int
    in_training: bool
    weekly_hours: float

    @property
    def age(self) -> int:
        return int(DE_WORKER_PERIOD) - self.birth_year


def de_kindergeld_eligibility_cases() -> list[Case]:
    """The 2025 child-eligibility grid, one § 32 threshold per case."""

    grid: list[tuple[str, str, tuple[_Child, ...]]] = [
        ("child-17", "minor-child", (_Child(2008, False, 0.0),)),
        ("child-18-training", "adult-child-in-training", (_Child(2007, True, 0.0),)),
        ("child-18-no-training", "adult-child-not-in-training", (_Child(2007, False, 0.0),)),
        ("child-24-training", "adult-child-in-training-last-year", (_Child(2001, True, 0.0),)),
        ("child-25-training", "adult-child-in-training-over-limit", (_Child(2000, True, 0.0),)),
        ("child-22-training-20h", "adult-child-in-training-working-20h", (_Child(2003, True, 20.0),)),
        ("child-22-training-25h", "adult-child-in-training-working-25h", (_Child(2003, True, 25.0),)),
        (
            "children-17-and-25",
            "one-eligible-one-ineligible-child",
            (_Child(2008, False, 0.0), _Child(2000, True, 0.0)),
        ),
    ]
    return [_case(case_id, scenario, children) for case_id, scenario, children in grid]


def _case(case_id: str, scenario: str, children: tuple[_Child, ...]) -> Case:
    person_ids = tuple(101 + index for index in range(1 + len(children)))
    parent_id = person_ids[0]

    euromod_rows = [
        _euromod_person(
            parent_id,
            age=_PARENT_AGE,
            monthly=_PARENT_MONTHLY_EARNINGS,
            sex=2,
        )
    ]
    entities = [
        Entity(
            entity_id="head",
            kind="person",
            facts={
                Concepts.PERSON_AGE: _PARENT_AGE,
                Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                Concepts.YEARLY_EARNED_INCOME: _PARENT_MONTHLY_EARNINGS * 12,
            },
        )
    ]
    gettsim_persons: list[dict[str, object]] = [
        {
            "einnahmen__bruttolohn_m": _PARENT_MONTHLY_EARNINGS * DE_INPUT_UPRATING_FACTOR,
            "alter": _PARENT_AGE,
            "sozialversicherung__pflege__beitrag__hat_kinder": True,
            "familie__alleinerziehend": True,
        }
    ]

    for index, child in enumerate(children, start=1):
        euromod_row = _euromod_person(person_ids[index], age=child.age, mother=parent_id)
        # EUROMOD reads the child's status from the labour-status and
        # in-education codes; the worker helper only knows "under 16".
        euromod_row["les"] = 6 if child.in_training else 1
        euromod_row["dec"] = 1 if child.in_training else 0
        if child.weekly_hours:
            euromod_row["lhw"] = child.weekly_hours
            euromod_row["liwwh"] = child.weekly_hours
        euromod_rows.append(euromod_row)
        entities.append(
            Entity(
                entity_id=f"child{index}",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: child.age,
                    Concepts.HOUSEHOLD_RELATION: "Child",
                    Concepts.YEARLY_EARNED_INCOME: 0.0,
                },
            )
        )
        gettsim_person: dict[str, object] = {
            "geburtsjahr": child.birth_year,
            "kindergeld__in_ausbildung": child.in_training,
        }
        if child.weekly_hours:
            gettsim_person["arbeitsstunden_w"] = child.weekly_hours
        gettsim_persons.append(gettsim_person)

    child_indices = range(1, 1 + len(children))
    gettsim_case = {
        "persons": gettsim_persons,
        "parents": {index: [0, None] for index in child_indices},
        "kindergeld_recipients": {index: 0 for index in child_indices},
    }
    return Case(
        case_id=case_id,
        period=DE_WORKER_PERIOD,
        metadata={
            "locale": "DE",
            "scope": DE_SCOPE,
            "scenario": scenario,
            "yearly_earned_income": _PARENT_MONTHLY_EARNINGS * 12,
            "nominal_monthly_earnings": [_PARENT_MONTHLY_EARNINGS],
            "region": "west",
            "joint_assessment": False,
            "children": [
                {
                    "birth_year": child.birth_year,
                    "age": child.age,
                    "in_training": child.in_training,
                    "weekly_hours": child.weekly_hours,
                }
                for child in children
            ],
            "euromod_inputs": euromod_rows,
            "gettsim_case": gettsim_case,
        },
        entities=tuple(entities),
        outputs=DE_KINDERGELD_ELIGIBILITY_OUTPUTS,
    )
