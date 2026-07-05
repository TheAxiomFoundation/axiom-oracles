"""Family Child Benefit suite for the UKMOD ``bch_s`` oracle.

Where ``uk_worker`` runs single-employee tax/NIC cases, Child Benefit is a
non-means-tested family transfer: the enhanced rate for the only or eldest
child plus the other rate for each subsequent child, paid weekly and reported
annually. This suite builds a hypothetical single-parent household grid — one,
two, and three children crossed with an earner-income sweep that straddles the
High Income Child Benefit Charge taper — and runs it against CeMPA's UKMOD
Child Benefit on the registration-free public model (UKMOD_PUBLIC_B2026.03,
system UK_2026, dataset training_data).

Household composition is expressed as explicit UKMOD ``euromod_inputs`` rows so
the benefit-unit linkage the entitlement depends on is exact: the responsible
adult carries ``dhr``; the children link to the mother through ``idmother`` and
carry the in-education labour status (``les``) and dependent-child education
code (``dec``). Monetary case facts are annual (the Axiom concept convention);
UKMOD's demo dataset is monthly, so employment income is divided by twelve while
the monthly Child Benefit output is annualised by the adapter.

Verified UKMOD conventions (executed against UKMOD_PUBLIC_B2026.03, UK_2026):

- The simulated Child Benefit column is ``bch_s`` (UKMOD policy ``bch_uk``,
  "BEN: Child Benefit"), computed from ``$CBFirst``/``$CBOther`` for the first
  and subsequent children. It is monthly and the adapter annualises it. Verified
  gross amounts (one child £1,410.46, two £2,343.82, three £3,277.18) are the
  same SI 2006/965 weekly rates (£27.05 enhanced, £17.90 other) annualised over
  UKMOD's 52.14-week convention; the composed Axiom pipeline uses 52 benefit
  weeks (£1,406.60 / £2,337.40 / £3,268.20), a systematic ~0.27% weeks-per-year
  convention residual absorbed by the concept's 0.3% relative tolerance (all 12
  cases match). Dividing UKMOD's gross by 52.14 and Axiom's by 52 both recover
  the same statutory weekly rates, confirming the residual is a convention
  difference and not an encoding gap.

- The High Income Child Benefit Charge is a separate UKMOD benefit-side policy
  ``bchrd_uk`` ("BEN: Reduce child benefit (from 2013)"), not part of income
  tax. It computes ``bchrd_s = ((adjusted_net_income - $ITCBthresh) / 200) x 1%
  x bch_s``, capped at ``bch_s``, and nets ``bchrd_s`` back into ``bch_s``. For
  UK_2026 the threshold is £60,000 with full clawback at £80,000 (verified: a
  one-child family at £70,000 has exactly 50% clawed back; at £80,000 the whole
  entitlement is clawed back). The charge is not encoded on the Axiom side (its
  ITEPA 2003 s.681B-H provisions are not in the corpus, rulespec-uk#75), so the
  comparison bridges to UKMOD's pre-charge Child Benefit: the concept's euromod
  target is the list ``[bch_s, bchrd_s]``, whose sum reconstructs the gross
  entitlement (invariant to income: £1,410.46 for one child at every income
  point, split between a paid ``bch_s`` and a clawed-back ``bchrd_s``).

- Unlike the means-tested benefits (Universal Credit, Housing Benefit, Income
  Support, tax credits), Child Benefit does NOT consume UKMOD's stochastic
  take-up draw ``i_rand_tu``: the ``bch_uk`` policy has no take-up gate, so the
  benefit take-up correction (policies ``BTA_uk``/``random_uk``) cannot zero a
  hypothetical family's Child Benefit. This suite still requests the take-up
  policy switch overrides on every case, and it was verified against the model
  that toggling them leaves ``bch_s`` and ``bchrd_s`` unchanged for every case
  in the grid (recorded in ``axiom_oracles/data/euromod_issues.json``,
  ``ukmod-cb-bch-no-takeup-gate``). Expected outputs are only ever the executed
  values from the regenerate run.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity


UK_SCOPE = {"type": "country", "geoid": "UK"}
UK_CB_METADATA = {
    "locale": "UK",
    "scope": UK_SCOPE,
    "axiom_entity": "Family",
    "axiom_entity_id": "benefit_unit",
}

# The composed Child Benefit pilot pipeline (rulespec-uk). Its annual
# entitlement output is ``uk_cb_pilot_annual_entitlement`` and its Family-level
# input is the supplied child count.
CB_MODULE = "uk:statutes/child_benefit/pilot_child_benefit_oracle_pipeline"

# The composed pilot pipeline is effective from the 2026-27 tax year, where the
# Child Benefit weekly rates are imported from the SI 2006/965 rate module. The
# 2025-26 and 2026-27 rates are the same, so UKMOD UK_2025 and UK_2026 return
# the same gross entitlement here.
UK_CB_PERIOD = "2026"

# EUROMOD codes.
_DCT = 15
_DRGN = 2
_LES_EMPLOYED = 3
_LES_CHILD = 6
_DMS_SINGLE = 1
_DEC_CHILD = 2

# UKMOD's take-up correction. Child Benefit does not consume the take-up draw
# (verified no-op), but the suite requests these overrides so the intent to
# compare the statutory entitlement is explicit and recorded on every case,
# matching the household Universal Credit suite.
_TAKEUP_OVERRIDES = (("BTA_uk", False), ("random_uk", False))

# Single-parent child grid crossed with an income sweep. £20,000 is below the
# £60,000 HICBC threshold (no clawback); £70,000 sits mid-taper (half clawed
# back); £80,000 is the full-clawback point; £90,000 is past it. The gross
# entitlement (bch_s + bchrd_s) is invariant across the income sweep, so the
# sweep exercises the charge boundary while the child count exercises the
# enhanced/other rate composition.
_CHILD_COUNTS: tuple[int, ...] = (1, 2, 3)
_INCOME_GRID: tuple[tuple[str, float], ...] = (
    ("20k", 20_000.0),
    ("70k", 70_000.0),
    ("80k", 80_000.0),
    ("90k", 90_000.0),
)


def uk_child_benefit_cases() -> list[Case]:
    """Single-parent Child Benefit cases for the UKMOD UK_2026 oracle."""

    return [
        _child_benefit_case(
            f"uk-child-benefit-{children}c-{label}",
            children=children,
            annual_income=income,
        )
        for children in _CHILD_COUNTS
        for label, income in _INCOME_GRID
    ]


def _child_benefit_case(
    case_id: str,
    *,
    children: int,
    annual_income: float,
) -> Case:
    rows = _euromod_household_rows(children=children, head_annual_income=annual_income)
    return Case(
        case_id=case_id,
        period=UK_CB_PERIOD,
        metadata={
            **UK_CB_METADATA,
            "scenario": "single-parent-child-benefit",
            "children": children,
            "head_annual_earnings": annual_income,
            "axiom_inputs": {
                _cb_input("uk_cb_pilot_supplied_number_of_children"): children,
            },
            "euromod_inputs": rows,
            "euromod_policy_switch_overrides": [list(pair) for pair in _TAKEUP_OVERRIDES],
        },
        entities=_entities(children=children, head_annual_income=annual_income),
        outputs=(Concepts.UK_CHILD_BENEFIT_ENTITLEMENT,),
    )


def _cb_input(name: str) -> str:
    return f"{CB_MODULE}#input.{name}"


def _entities(*, children: int, head_annual_income: float) -> tuple[Entity, ...]:
    """Concept-keyed entities mirroring the explicit UKMOD rows.

    The suite drives UKMOD from the explicit ``euromod_inputs`` rows; these
    entities describe the same single-parent family in Axiom concepts so the
    rulespec-uk side projects the identical benefit unit.
    """

    people: list[Entity] = [
        Entity(
            entity_id="head",
            kind="person",
            facts={
                Concepts.PERSON_AGE: 35,
                Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                Concepts.YEARLY_EARNED_INCOME: head_annual_income,
            },
        )
    ]
    for index in range(children):
        people.append(
            Entity(
                entity_id=f"child{index + 1}",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: _child_age(index),
                    Concepts.HOUSEHOLD_RELATION: "Child",
                },
            )
        )
    return tuple(people)


def _euromod_household_rows(
    *, children: int, head_annual_income: float
) -> list[dict[str, float | int]]:
    head_id = 101
    rows: list[dict[str, float | int]] = [
        _adult_row(idperson=head_id, annual_income=head_annual_income),
    ]
    for index in range(children):
        rows.append(
            _child_row(idperson=103 + index, age=_child_age(index), mother_id=head_id)
        )
    return rows


def _adult_row(*, idperson: int, annual_income: float) -> dict[str, float | int]:
    employed = annual_income > 0
    return {
        "idhh": 1,
        "idperson": idperson,
        "idpartner": 0,
        "idmother": 0,
        "idfather": 0,
        "idmotherbio": 0,
        "idfatherbio": 0,
        "drgn1": _DRGN,
        "dct": _DCT,
        "dwt": 1_000.0,
        "dag": 35,
        "dgn": 1,
        "dms": _DMS_SINGLE,
        "dhr": 1,
        "dec": 0,
        "ddi": 0,
        "les": _LES_EMPLOYED if employed else 0,
        "lhw": 40 if employed else 0,
        "loc": 5,
        "amrtn": 1,
        "yem": annual_income / 12.0,
        "yse": 0.0,
        "yiy": 0.0,
        "poa": 0.0,
        "xhcrt": 0.0,
        "afc": 0.0,
    }


def _child_row(
    *, idperson: int, age: int, mother_id: int
) -> dict[str, float | int]:
    return {
        "idhh": 1,
        "idperson": idperson,
        "idpartner": 0,
        "idmother": mother_id,
        "idfather": 0,
        "idmotherbio": mother_id,
        "idfatherbio": 0,
        "drgn1": _DRGN,
        "dct": _DCT,
        "dwt": 1_000.0,
        "dag": age,
        "dgn": 1,
        "dms": _DMS_SINGLE,
        "dhr": 0,
        "dec": _DEC_CHILD,
        "ddi": 0,
        "les": _LES_CHILD,
        "lhw": 0,
        "loc": 5,
        "amrtn": 1,
        "yem": 0.0,
        "yse": 0.0,
        "yiy": 0.0,
        "poa": 0.0,
        "xhcrt": 0.0,
        "afc": 0.0,
    }


def _child_age(index: int) -> int:
    """Descending child ages so the eldest anchors the enhanced rate; all are
    under 16 so every child is a qualifying young person for Child Benefit."""

    return (10, 7, 4, 2)[index] if index < 4 else 1
