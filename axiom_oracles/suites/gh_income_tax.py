"""Ghana income-tax and personal-relief oracle suites (GHAMOD).

Two synthetic per-case suites compare rulespec-gh modules against GHAMOD, the
SOUTHMOD tax-benefit model for Ghana, run on the EUROMOD engine (SOUTHMOD A4.0,
country GH, system GH_2025):

* ``gh-income-tax-rate-schedule`` compares the Axiom
  ``resident_individual_income_tax`` (Act 1111 First Schedule rate bands over
  ``chargeable_income``) against GHAMOD ``tin_s`` on a band-boundary/interior
  income sweep.
* ``gh-personal-reliefs`` compares the Axiom Fifth Schedule personal-relief
  outputs (Act 896 s51/Fifth Schedule as amended by Act 1007) against GHAMOD's
  per-relief ``tinta0X_s`` outputs, one relief branch per case, plus caps and a
  combined multi-relief household.

Law equivalence (validation year 2026 vs GHAMOD GH_2025): the encoded Act 1111
rate bands are effective 2024 and the Act 1007 relief amounts effective 2020,
and neither changed for 2025 or 2026, so GHAMOD's GH_2024 and GH_2025 systems
apply the identical schedule and relief amounts the Axiom modules validate for
2026. GH_2025 is the comparison system.

GHAMOD input convention: the bundled Ghana dataset (gh_2017_a8, GLSS-based) is
2017 vintage, and GH_2025 uprates monetary inputs to 2025 by an employment-
income index of GH_UPRATE_2017_TO_2025 (probed live). Each euromod input row
pre-divides the intended gross by that index so the engine prices the intended
nominal amount, and the comparison additionally bridges Axiom's income base on
the engine's own post-uprating ``yem`` / ``il_tintb3`` so both engines price the
identical base regardless of the exact index (the ``euromod_to_axiom_input_bridge``
convention shared with the UK/BE suites).

License discipline: the bundle is referenced only by env var / path
(``EUROMOD_MODEL_ROOT``); no SOUTHMOD model XML, dataset row, or DRD text is
committed. Expected values recorded here are values GHAMOD itself produced.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity

RATE_MODULE = (
    "gh:statutes/act-1111/income-tax-amendment-no2-2023/"
    "first-schedule-rates-of-income-tax-for-individuals"
)
RELIEFS_MODULE = "gh:statutes/act-896/income-tax-2015/fifth-schedule"
EUROMOD_TO_AXIOM_INPUT_BRIDGE = "euromod_to_axiom_input_bridge"

# Ghanaian year of assessment 2026 (the rulespec-gh validation year). GHAMOD
# resolves its policy year from the system name (GH_2025); the case period only
# drives the Axiom side, and the Act 1111 bands / Act 1007 reliefs are frozen
# across 2024-2026, so 2025 and 2026 read identical amounts.
GH_PERIOD = "2026"

# Employment-income uprating index applied by GHAMOD GH_2025 to the 2017-vintage
# gh_2017_a8 dataset, probed live (input yem 1000 -> engine yem 3590.0946591…).
# Rows pre-divide by this so the engine prices the intended nominal gross; the
# post-uprating bridge keeps parity exact even if a future release re-indexes.
GH_UPRATE_2017_TO_2025 = 3.5900946591291687

GH_SCOPE = {"type": "country", "geoid": "GH"}
GH_METADATA = {
    "locale": "GH",
    "scope": GH_SCOPE,
    "axiom_entity": "Person",
    "axiom_entity_id": "head",
}

# Single formal-sector employee earner base used to give relief cases a positive
# tax base (reliefs are allocated only to formal-sector taxpayers with a
# positive base); the flat relief amounts do not depend on its level, and the
# disability relief (25% of the post-relief base) is bridged so its base is
# priced by the engine.
_RELIEF_EARNER_BASE = 100_000.0


def _em_monthly(annual: float) -> float:
    """Pre-divided monthly euromod input so uprating restores ``annual``."""
    return (annual / GH_UPRATE_2017_TO_2025) / 12.0


def _rate_input(name: str) -> str:
    return f"{RATE_MODULE}#{name}"


def _relief_input(name: str) -> str:
    return f"{RELIEFS_MODULE}#{name}"


# ---------------------------------------------------------------------------
# Rate schedule
# ---------------------------------------------------------------------------

# Band-boundary and interior income sweep (nominal GHS). Cumulative band upper
# bounds are 5,880 / 7,200 / 8,760 / 46,760 / 238,760 / 605,000; rates
# 0/5/10/17.5/25/30/35%. All incomes at or below 605,000 exercise bands the two
# engines share exactly; 700,000 exercises the Act 1111 35% top band, which
# GHAMOD's tin_gh SchedCalc does not wire (see gh-income-tax-rate-schedule
# disposition), so it is the one documented divergence.
_RATE_INCOME_GRID: tuple[tuple[str, float], ...] = (
    ("5k-below-threshold", 5_000.0),
    ("5880-nil-band-top", 5_880.0),
    ("7200-5pct-band-top", 7_200.0),
    ("8760-10pct-band-top", 8_760.0),
    ("10k-17p5-interior", 10_000.0),
    ("46760-17p5-band-top", 46_760.0),
    ("50k-25pct-interior", 50_000.0),
    ("238760-25pct-band-top", 238_760.0),
    ("250k-30pct-interior", 250_000.0),
    ("605000-30pct-band-top", 605_000.0),
    ("700k-35pct-band", 700_000.0),
)


def gh_income_tax_rate_schedule_cases() -> list[Case]:
    """Single formal-sector employee income-tax cases for the GHAMOD tin_s oracle."""
    return [
        _rate_schedule_case(f"gh-rate-{label}", income)
        for label, income in _RATE_INCOME_GRID
    ]


def _rate_schedule_case(case_id: str, annual_income: float) -> Case:
    chargeable_income = _rate_input("chargeable_income")
    return Case(
        case_id=case_id,
        period=GH_PERIOD,
        metadata={
            **GH_METADATA,
            "scenario": "single-formal-employee-rate-schedule",
            "yearly_earned_income": annual_income,
            # Placeholder; the post-uprating euromod yem overwrites it via the
            # bridge so both engines price the identical schedule base.
            "axiom_inputs": {chargeable_income: annual_income},
            "euromod_inputs": [_gh_formal_earner(101, annual_income)],
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {"yem": [chargeable_income]},
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 35,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.YEARLY_EARNED_INCOME: annual_income,
                },
            ),
        ),
        outputs=(Concepts.GH_RESIDENT_INCOME_TAX,),
    )


# ---------------------------------------------------------------------------
# Personal reliefs
# ---------------------------------------------------------------------------


def gh_personal_reliefs_cases() -> list[Case]:
    """Fifth Schedule personal-relief cases for the GHAMOD tinta0X_s oracles."""
    return [
        _old_age_relief_case(),
        _disability_relief_case(),
        # expected GHAMOD tinta05_s: 2 -> 1,200; 4 -> 1,800 (capped at 3 x 600)
        _child_education_relief_case("gh-relief-child-education-2", 2),
        _child_education_relief_case("gh-relief-child-education-4-cap", 4),
        # expected GHAMOD tinta06_s: 1 -> 1,000; 3 -> 2,000 (capped at 2 x 1,000)
        _aged_dependant_relief_case("gh-relief-aged-dependant-1", 1),
        _aged_dependant_relief_case("gh-relief-aged-dependant-3-cap", 3),
        _dependant_spouse_relief_case(),
        _combined_reliefs_case(),
    ]
    # The Act 896 para 1(f) training relief (Axiom ``training_personal_relief``,
    # min(cost, 2,000)) has no live case: GHAMOD's tinta04 is switched off and
    # emits no ``tinta04_s`` output column at all (a missing column, not a zero),
    # so there is nothing to compare against. It is a documented oracle gap
    # (axiom_oracles/data/ghamod_issues.json; the concept stays mapped but
    # unused in concept_mappings.yaml), and the Axiom branch is exercised by the
    # rulespec-gh module's companion tests.


def _reliefs_base_inputs() -> dict[str, float | bool]:
    """All Fifth Schedule inputs zero/false; branch cases override their own."""
    return {
        _relief_input("has_dependant_spouse"): False,
        _relief_input("dependant_child_count"): 0,
        _relief_input("has_disability"): False,
        _relief_input("assessable_business_or_employment_income"): 0.0,
        _relief_input("age"): 40,
        _relief_input("sponsored_children_in_education_count"): 0,
        _relief_input("aged_dependant_relative_count"): 0,
        _relief_input("has_undergone_skills_update_training"): False,
        _relief_input("skills_update_training_cost"): 0.0,
    }


def _reliefs_case(
    case_id: str,
    *,
    scenario: str,
    axiom_overrides: dict[str, float | bool],
    euromod_rows: list[dict[str, float | int]],
    outputs: tuple[str, ...],
    bridge: dict[str, list[str]] | None = None,
    entities: tuple[Entity, ...] | None = None,
) -> Case:
    axiom_inputs = _reliefs_base_inputs()
    axiom_inputs.update(axiom_overrides)
    metadata: dict[str, object] = {
        **GH_METADATA,
        "scenario": scenario,
        "axiom_inputs": axiom_inputs,
        "euromod_inputs": euromod_rows,
    }
    if bridge is not None:
        metadata[EUROMOD_TO_AXIOM_INPUT_BRIDGE] = bridge
    return Case(
        case_id=case_id,
        period=GH_PERIOD,
        metadata=metadata,
        entities=entities
        or (
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 40,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.YEARLY_EARNED_INCOME: _RELIEF_EARNER_BASE,
                },
            ),
        ),
        outputs=outputs,
    )


def _old_age_relief_case() -> Case:
    # Working elderly: 60+ with earnings. GHAMOD tinta03 = 1,500 (dag>=60 &
    # yem!=0); Axiom old_age_personal_relief = 1,500 (age>=60). Flat, no bridge.
    return _reliefs_case(
        "gh-relief-old-age",
        scenario="working-elderly-old-age-relief",
        axiom_overrides={_relief_input("age"): 65},
        euromod_rows=[_gh_formal_earner(101, _RELIEF_EARNER_BASE, dag=65)],
        outputs=(Concepts.GH_OLD_AGE_RELIEF,),
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 65,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                    Concepts.YEARLY_EARNED_INCOME: _RELIEF_EARNER_BASE,
                },
            ),
        ),
    )


def _disability_relief_case() -> Case:
    # Disabled worker. GHAMOD tinta07 = 25% of il_tintb3 (the base after the
    # other reliefs; here the only relief, so = the post-uprating gross). Axiom
    # disability_personal_relief = 25% of assessable_business_or_employment_income,
    # bridged on the engine's il_tintb3 so both take 25% of the identical base.
    assessable = _relief_input("assessable_business_or_employment_income")
    return _reliefs_case(
        "gh-relief-disability",
        scenario="disabled-worker-disability-relief",
        axiom_overrides={
            _relief_input("has_disability"): True,
            assessable: _RELIEF_EARNER_BASE,
        },
        euromod_rows=[_gh_formal_earner(101, _RELIEF_EARNER_BASE, ddi=1)],
        outputs=(Concepts.GH_DISABILITY_RELIEF,),
        bridge={"il_tintb3": [assessable]},
    )


def _child_education_relief_case(case_id: str, children: int) -> Case:
    # Sponsored children in education. GHAMOD tinta05 = 600 per eligible child
    # (dag<=18, in education deh!=-1, no earnings), capped at 3 (UpLim 3*600);
    # Axiom child_education_personal_relief = 600 * min(count, 3). Flat.
    rows = [_gh_formal_earner(101, _RELIEF_EARNER_BASE)]
    rows.extend(
        _gh_child_in_education(101 + i + 1, father_id=101, age=12 - i)
        for i in range(children)
    )
    return _reliefs_case(
        case_id,
        scenario="sponsored-children-education-relief",
        axiom_overrides={
            _relief_input("sponsored_children_in_education_count"): children
        },
        euromod_rows=rows,
        outputs=(Concepts.GH_CHILD_EDUCATION_RELIEF,),
    )


def _aged_dependant_relief_case(case_id: str, relatives: int) -> Case:
    # Aged (60+, non-earning) dependent relatives in the household. GHAMOD
    # tinta06 = 1,000 per eligible, capped at 2 (UpLim 2*1000); Axiom
    # aged_dependant_relative_personal_relief = 1,000 * min(count, 2). Flat.
    rows = [_gh_formal_earner(101, _RELIEF_EARNER_BASE)]
    rows.extend(_gh_aged_dependant(101 + i + 1, age=68 + i) for i in range(relatives))
    return _reliefs_case(
        case_id,
        scenario="aged-dependant-relative-relief",
        axiom_overrides={_relief_input("aged_dependant_relative_count"): relatives},
        euromod_rows=rows,
        outputs=(Concepts.GH_AGED_DEPENDANT_RELATIVE_RELIEF,),
    )


def _dependant_spouse_relief_case() -> Case:
    # Married worker with a non-earning dependent spouse. GHAMOD tinta01 = 1,200
    # (IsWithPartner & partner income 0); Axiom
    # dependant_spouse_or_children_personal_relief = 1,200 (has_dependant_spouse).
    # (GHAMOD splits Act 896 para 1(a) into tinta01 spouse and tinta02 lone
    # parent; tinta02 does not fire for synthetic lone-parent households — a
    # documented oracle behaviour recorded in ghamod_issues.json — so the spouse
    # limb is the parity case for this Axiom output.)
    return _reliefs_case(
        "gh-relief-dependant-spouse",
        scenario="married-worker-dependent-spouse-relief",
        axiom_overrides={_relief_input("has_dependant_spouse"): True},
        euromod_rows=_gh_married_earner_with_dependent_spouse(),
        outputs=(Concepts.GH_DEPENDANT_SPOUSE_OR_CHILDREN_RELIEF,),
    )


def _combined_reliefs_case() -> Case:
    # One household triggering three flat reliefs at once: dependent spouse
    # (tinta01=1,200), two children in education (tinta05=1,200) and one aged
    # dependant (tinta06=1,000). All are flat and non-interacting, so each Axiom
    # branch equals its GHAMOD counterpart; the case catches any cross-branch
    # allocation error.
    rows = [
        _gh_formal_earner(101, _RELIEF_EARNER_BASE, dms=2, idpartner=105),
        _gh_child_in_education(102, father_id=101, mother_id=105, age=12),
        _gh_child_in_education(103, father_id=101, mother_id=105, age=9),
        _gh_aged_dependant(104, age=70),
        _gh_dependent_spouse(105, partner_id=101),
    ]
    return _reliefs_case(
        "gh-relief-combined",
        scenario="combined-multi-relief-household",
        axiom_overrides={
            _relief_input("has_dependant_spouse"): True,
            _relief_input("sponsored_children_in_education_count"): 2,
            _relief_input("aged_dependant_relative_count"): 1,
        },
        euromod_rows=rows,
        outputs=(
            Concepts.GH_DEPENDANT_SPOUSE_OR_CHILDREN_RELIEF,
            Concepts.GH_CHILD_EDUCATION_RELIEF,
            Concepts.GH_AGED_DEPENDANT_RELATIVE_RELIEF,
        ),
    )


# ---------------------------------------------------------------------------
# EUROMOD input-row builders (GHAMOD schema: single person per row)
# ---------------------------------------------------------------------------


def _gh_base_row(idhh: int, idperson: int) -> dict[str, float | int]:
    return {
        "idhh": idhh,
        "idperson": idperson,
        "idpartner": 0,
        "idmother": 0,
        "idfather": 0,
        "dwt": 1.0,
        "dag": 40,
        "dgn": 1,
        "dms": 1,
        "dhh": 0,
        "les": 0,
        "lfo": 0,
        "ddi": 0,
        "deh": 0,
        "yem": 0.0,
        "yem00": 0.0,
    }


def _gh_formal_earner(
    idperson: int,
    annual_income: float,
    *,
    dag: int = 40,
    dgn: int = 1,
    dms: int = 1,
    ddi: int = 0,
    idpartner: int = 0,
) -> dict[str, float | int]:
    """A formal-sector (lfo=1) employee household head."""
    monthly = _em_monthly(annual_income)
    row = _gh_base_row(1, idperson)
    row.update(
        {
            "dag": dag,
            "dgn": dgn,
            "dms": dms,
            "dhh": 1,
            "les": 3,
            "lfo": 1,
            "ddi": ddi,
            "idpartner": idpartner,
            "yem": monthly,
            "yem00": monthly,
        }
    )
    return row


def _gh_child_in_education(
    idperson: int,
    *,
    father_id: int = 0,
    mother_id: int = 0,
    age: int = 10,
) -> dict[str, float | int]:
    """A dependent child (dag<=18) in education (deh set), no earnings."""
    row = _gh_base_row(1, idperson)
    row.update(
        {
            "dag": age,
            "dgn": idperson % 2,
            "les": 6,  # in education
            "deh": 2,  # education defined (deh != -1)
            "idfather": father_id,
            "idmother": mother_id,
        }
    )
    return row


def _gh_aged_dependant(idperson: int, *, age: int = 68) -> dict[str, float | int]:
    """A 60+ non-earning dependent relative in the household."""
    row = _gh_base_row(1, idperson)
    row.update({"dag": age, "dgn": idperson % 2, "les": 0})
    return row


def _gh_dependent_spouse(idperson: int, *, partner_id: int) -> dict[str, float | int]:
    """A married, non-earning spouse (opposite gender to the head)."""
    row = _gh_base_row(1, idperson)
    row.update({"dag": 38, "dgn": 0, "dms": 2, "idpartner": partner_id})
    return row


def _gh_married_earner_with_dependent_spouse() -> list[dict[str, float | int]]:
    return [
        _gh_formal_earner(101, _RELIEF_EARNER_BASE, dms=2, idpartner=102),
        _gh_dependent_spouse(102, partner_id=101),
    ]
