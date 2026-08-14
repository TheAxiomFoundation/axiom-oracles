"""Denmark child and youth benefit suite for the EUROMOD ``bfachnm_s`` oracle.

The børne- og ungeydelse (child and youth benefit) is a non-means-tested family
transfer whose age-banded base amount (børneydelse under 15, ungeydelse 15-17)
is reduced by a § 1 a income taper. This suite runs a single-parent, one-child
grid against the JRC EUROMOD release's Danish system (EUROMOD_RELEASES_J2.0+,
system DK_2025, dataset DK_training_data) and grades the composed Axiom pipeline
``single_recipient_annual_child_youth_benefit`` against EUROMOD's ``bfachnm_s``.
Seven cases keep the known EUROMOD gaps inert and match raw; an eighth witness
activates the missing § 1 a, stk. 4-5 pension-contribution gross-up and is
classified as an upstream engine gap (ec-jrc #20).

The separate ``dk_child_youth_benefit_2023_cases`` suite activates ec-jrc #19:
the one-off 2023 statutory increase is 660 kr., while EUROMOD DK_2023 carries a
600 kr. constant. Its low-income age-5 case isolates that 60 kr. parameter gap.

Household composition is expressed as explicit EUROMOD input rows so the
dependent-child linkage the allocation depends on is exact: EUROMOD allocates
``bfachnm_s`` to the dependent child row (``Allocate share_between IsDepChild``),
so each case carries one responsible adult and one child that links to the head
through ``idmother`` and carries the dependent-child code ``dec``. Monetary case
facts are annual (the Axiom concept convention); the DK dataset is monthly, so
``yem`` is supplied monthly (annual / 12) and the monthly ``bfachnm_s`` output is
annualised by the adapter (x12).

Single-recipient by design. EUROMOD implements a pre-2022 spousal income test in
the taper for DK_2022-DK_2025 (filed upstream as ec-jrc #18,
``euromod_issues.json`` euromod-dk-2025-bfachnm-pre2022-spousal-taper), and the
Axiom pipeline models the single-recipient § 1 a taper only (the § 1 a couple
apportionment is future work). The graded grid is therefore restricted to
single-parent households, where the two sides implement the same mechanism and
the spousal-test divergence cannot arise. Couple semantics are deliberately
excluded from the graded surface.

Verified EUROMOD conventions (executed against EUROMOD_RELEASES_J2.0+, DK_2025):

- The child/youth benefit column is ``bfachnm_s`` (policy ``bfachnm_dk``),
  computed from the DK_2025 constants 21168 / 16764 / 13188 (age <=2 / 3-6 />6),
  the § 20-regulated bundfradrag 917000, and the 2 pct. taper rate. It is
  monthly and the adapter annualises it. The base amounts reproduce the official
  2025 Skattestyrelsen satser, which the Axiom side also reproduces from the
  2011-niveau bases and a percentage_change_rounded_to_one_decimal_place of 0.285.

- The engine's § 7-basis income concept ``tintbto_s`` equals 0.92 x ``yem`` on
  this dataset (no uprating; AM-bidrag 8%). The suite bridges the engine's own
  ``tintbto_s`` into the composed module's
  ``personskatteloven_section_7_income_basis`` inputs via
  ``EUROMOD_TO_AXIOM_INPUT_BRIDGE`` so the Axiom taper runs on EUROMOD's own
  income base rather than a re-projected one. Both outputs are annual, so the
  bridge applies no divisor (verified: the bridged value is the annual
  0.92 x yem the engine reports).

- The EUROMOD input rows pin every income/benefit/expense column to 0 and set the
  demographics explicitly (the adapter's worker zero-fills the full DK schema and
  overlays these rows), so the head's ``tintbto_s`` is exactly 0.92 x yem and
  ``bfachnm_s`` is exactly the model entitlement (verified per inert case in the
  regenerate run: 21168 / 16764 / 13188 / 13188 at yem 300000 for ages
  1 / 5 / 10 / 16, then 16704 / 11184 / 0 for age 5 at yem 1000000 / 1300000 /
  2000000). The pension witness records 60000 kr. of true qualifying
  contributions in case metadata and supplies them only to Axiom because the
  EUROMOD DK input schema exposes no value that ``bfachnm_dk`` reads for the
  statutory deduction. EUROMOD therefore remains at 11184 while Axiom pays
  13184. Expected outputs are only ever the executed values from the regenerate
  run.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity


DK_SCOPE = {"type": "country", "geoid": "DK"}
DK_METADATA = {
    "locale": "DK",
    "scope": DK_SCOPE,
    "axiom_entity": "Person",
    "axiom_entity_id": "recipient",
}

# The composed child/youth benefit pipeline (rulespec-dk). Its single-recipient
# annual output and its Person-level inputs are addressed under this module id.
CYB_MODULE = "dk:statutes/composed/boerne-og-ungeydelse-pipeline"
P1_MODULE = "dk:statutes/lbk-603-2025/boerne-og-ungeydelsesloven/paragraf-1"
P1A_MODULE = "dk:statutes/lbk-603-2025/boerne-og-ungeydelsesloven/paragraf-1-a"

EUROMOD_TO_AXIOM_INPUT_BRIDGE = "euromod_to_axiom_input_bridge"

# The consumer-price-index change since 2009 that reproduces the official 2025
# satser exactly (16992 x 1.246 -> round/12 -> 21168, etc.), and the § 1 a, stk. 3
# § 20-regulated bundfradrag for 2025 (917000 kr.), supplied because
# personskatteloven is not yet a captured dk corpus scope.
_DK_CPI_2025 = 0.285
_DK_CURRENT_YEAR_ALLOWANCE_2025 = 917_000
# The official 2023 CPI change and § 20-regulated bundfradrag. The one-case
# 2023 suite is below this threshold, but supplying the period-correct value
# keeps the composed identity complete.
_DK_CPI_2023 = 0.156
_DK_CURRENT_YEAR_ALLOWANCE_2023 = 852_600
# Pinned to the pensionsbeskatningslovens § 16, stk. 1 grundbeløb order. The
# 2025 witness contributes 60000 kr.; every other case contributes zero.
_DK_PENSION_CONTRIBUTION_CAP = 61_200

# EUROMOD DK demographic codes.
_LES_INACTIVE = 7  # head labour status carried by the DK training adults
_LES_CHILD = 0
_DMS_SINGLE = 1
_DEC_DEPENDENT_CHILD = 1
_LOC = 5
_AMRTN_OWNER = 1
_DRGUR = 1

# Single-parent one-child grid: four ages at a below-threshold income crossing
# the four age bands, then age 5 across an income sweep that straddles and
# exhausts the § 1 a taper (tintbto = 0.92 x yem: 920000 / 1196000 / 1840000
# against the 917000 bundfradrag).
_GRID: tuple[tuple[int, float], ...] = (
    (1, 300_000.0),
    (5, 300_000.0),
    (10, 300_000.0),
    (16, 300_000.0),
    (5, 1_000_000.0),
    (5, 1_300_000.0),
    (5, 2_000_000.0),
)


def dk_child_youth_benefit_cases() -> list[Case]:
    """Single-parent child/youth benefit cases for the EUROMOD DK_2025 oracle."""

    inert_cases = [
        _child_youth_benefit_case(child_age=age, head_annual_income=income)
        for age, income in _GRID
    ]
    pension_witness = _child_youth_benefit_case(
        child_age=5,
        head_annual_income=1_300_000.0,
        qualifying_pension_contributions=60_000.0,
    )
    return [*inert_cases, pension_witness]


def dk_child_youth_benefit_2023_cases() -> list[Case]:
    """One case isolating EUROMOD DK_2023's 600-vs-660 supplement gap."""

    return [
        _child_youth_benefit_case(
            child_age=5,
            head_annual_income=300_000.0,
            case_id_prefix="dk-child-youth-benefit-2023",
            period="2023",
            scenario="single-parent-child-youth-benefit-2023-supplement",
            cpi_change=_DK_CPI_2023,
            payment_year_has_additional_statutory_increase=True,
            current_year_income_reduction_allowance=(_DK_CURRENT_YEAR_ALLOWANCE_2023),
        )
    ]


def _child_youth_benefit_case(
    *,
    child_age: int,
    head_annual_income: float,
    case_id_prefix: str = "dk-child-youth-benefit",
    period: str = "2025",
    scenario: str = "single-parent-child-youth-benefit",
    cpi_change: float = _DK_CPI_2025,
    payment_year_has_additional_statutory_increase: bool = False,
    current_year_income_reduction_allowance: float = (_DK_CURRENT_YEAR_ALLOWANCE_2025),
    qualifying_pension_contributions: float = 0.0,
) -> Case:
    contribution_suffix = (
        f"-pension{int(qualifying_pension_contributions)}"
        if qualifying_pension_contributions
        else ""
    )
    contribution_metadata = (
        {"qualifying_pension_contributions": (qualifying_pension_contributions)}
        if qualifying_pension_contributions
        else {}
    )
    return Case(
        case_id=(
            f"{case_id_prefix}-age{child_age}"
            f"-yem{int(head_annual_income)}{contribution_suffix}"
        ),
        period=period,
        metadata={
            **DK_METADATA,
            "scenario": scenario,
            "child_age": child_age,
            "head_annual_earnings": head_annual_income,
            **contribution_metadata,
            "axiom_inputs": _axiom_inputs(
                child_age,
                cpi_change=cpi_change,
                payment_year_has_additional_statutory_increase=(
                    payment_year_has_additional_statutory_increase
                ),
                current_year_income_reduction_allowance=(
                    current_year_income_reduction_allowance
                ),
                qualifying_pension_contributions=(qualifying_pension_contributions),
            ),
            "euromod_inputs": [
                _adult_row(idperson=101, annual_income=head_annual_income),
                _child_row(idperson=102, age=child_age, mother_id=101),
            ],
            # Bridge the engine's own § 7-basis income (annual 0.92 x yem, its
            # tintbto_s) into the composed module's two § 7-basis inputs (the
            # full-year and § 14-recalculated slots receive the same value; the
            # part-year flag is False in every case). Both sides are annual, so
            # no divisor is applied; the Axiom taper then runs on EUROMOD's
            # income base with the period-correct supplied bundfradrag.
            EUROMOD_TO_AXIOM_INPUT_BRIDGE: {
                "tintbto_s": {
                    "inputs": [
                        _p1a_input("personskatteloven_section_7_income_basis"),
                        _p1a_input(
                            "personskatteloven_section_7_income_basis_after_section_14_recalculation"
                        ),
                    ]
                },
            },
        },
        entities=_entities(child_age=child_age, head_annual_income=head_annual_income),
        outputs=(Concepts.DK_CHILD_YOUTH_BENEFIT,),
    )


def _axiom_inputs(
    child_age: int,
    *,
    cpi_change: float = _DK_CPI_2025,
    payment_year_has_additional_statutory_increase: bool = False,
    current_year_income_reduction_allowance: float = (_DK_CURRENT_YEAR_ALLOWANCE_2025),
    qualifying_pension_contributions: float = 0.0,
) -> dict[str, float | bool | int]:
    return {
        _p1_input("child_age_years"): child_age,
        _p1_input("percentage_change_rounded_to_one_decimal_place"): cpi_change,
        _p1_input("payment_year_has_additional_statutory_increase"): (
            payment_year_has_additional_statutory_increase
        ),
        _p1a_input(
            "total_contributions_to_qualifying_pension_accounts"
        ): qualifying_pension_contributions,
        _p1a_input(
            "pension_contribution_limit_under_pensionsbeskatningsloven_section_16"
        ): _DK_PENSION_CONTRIBUTION_CAP,
        _p1a_input("person_only_taxable_part_of_year"): False,
        _cyb_input("current_year_income_reduction_allowance"): (
            current_year_income_reduction_allowance
        ),
    }


def _cyb_input(name: str) -> str:
    return f"{CYB_MODULE}#input.{name}"


def _p1_input(name: str) -> str:
    # Input slots resolve under their DECLARING module in the hard-cut
    # engine's compiled program (the legacy compile aliased them under the
    # composed module id; that aliasing is gone).
    return f"{P1_MODULE}#input.{name}"


def _p1a_input(name: str) -> str:
    return f"{P1A_MODULE}#input.{name}"


def _entities(*, child_age: int, head_annual_income: float) -> tuple[Entity, ...]:
    """Concept-keyed entities mirroring the explicit EUROMOD rows.

    Both engine sides are driven by explicit inputs (the EUROMOD ``euromod_inputs``
    rows and the Axiom ``axiom_inputs`` / bridge), so these entities only describe
    the single-parent family the case models; neither runner projects them.
    """

    return (
        Entity(
            entity_id="recipient",
            kind="person",
            facts={
                Concepts.PERSON_AGE: 35,
                Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                Concepts.YEARLY_EARNED_INCOME: head_annual_income,
            },
        ),
        Entity(
            entity_id="child",
            kind="person",
            facts={
                Concepts.PERSON_AGE: child_age,
                Concepts.HOUSEHOLD_RELATION: "Child",
            },
        ),
    )


def _adult_row(*, idperson: int, annual_income: float) -> dict[str, float | int]:
    """The single responsible adult: single, head, earning ``annual_income``.

    Every income/benefit/expense column stays 0 (the worker zero-fills the DK
    schema); only demographics and monthly ``yem`` are set, so ``tintbto_s`` is
    exactly 0.92 x ``yem`` and no imputed income leaks through labour-status
    fields.
    """

    return {
        "idperson": idperson,
        "idpartner": 0,
        "idmother": 0,
        "idfather": 0,
        "dag": 35,
        "dgn": 0,
        "dms": _DMS_SINGLE,
        "dhr": 1,
        "dec": 0,
        "les": _LES_INACTIVE,
        "lhw": 0,
        "liwmy": 0,
        "liwwh": 0,
        "loc": _LOC,
        "amrtn": _AMRTN_OWNER,
        "drgur": _DRGUR,
        "dwt": 1_000.0,
        "ddi": 0,
        "yem": annual_income / 12.0,
    }


def _child_row(*, idperson: int, age: int, mother_id: int) -> dict[str, float | int]:
    """The dependent child EUROMOD allocates ``bfachnm_s`` to (IsDepChild)."""

    return {
        "idperson": idperson,
        "idpartner": 0,
        "idmother": mother_id,
        "idfather": 0,
        "dag": age,
        "dgn": 1,
        "dms": _DMS_SINGLE,
        "dhr": 0,
        "dec": _DEC_DEPENDENT_CHILD,
        "les": _LES_CHILD,
        "lhw": 0,
        "liwmy": 0,
        "liwwh": 0,
        "loc": _LOC,
        "amrtn": _AMRTN_OWNER,
        "drgur": _DRGUR,
        "dwt": 1_000.0,
        "ddi": 0,
        "yem": 0.0,
    }
