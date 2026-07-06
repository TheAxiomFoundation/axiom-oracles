from __future__ import annotations

from ..core.case import Case, Concepts
from .be_worker import BE_METADATA


ROUTING_MODULE = "be:statutes/education/study_allowance_routing"

FLANDERS_REGION = 2
WALLONIA_REGION = 3

# EUROMOD BE_2025 region-of-residence codes (drgn1).
DRGN1_FLANDERS = 2
DRGN1_WALLONIA = 3

# EUROMOD BE_2025 current-education-level codes (dec).
DEC_HIGHER_EDUCATION = 6
DEC_SECONDARY_EDUCATION = 3

# EUROMOD BE_2025 labour-status code (les) for a student.
LES_STUDENT = 6


def be_study_allowance_cases() -> list[Case]:
    """Belgium study-allowance (bed_s) cases for the EUROMOD BE_2025 oracle.

    Each case pins the ``be:statutes/education/study_allowance_routing``
    module's supplied region and community amounts to the value the EUROMOD
    BE_2025 anchors verified for that household, so the axiom routing output
    (``belgium_study_allowance_annual_amount``) should equal the EUROMOD
    ``bed_s`` value exactly. Study allowances are a Community competence, so
    only the Flanders and Wallonia routes are deterministic on hypothetical
    data; Brussels applies a random ninety-ten split and a non-take-up
    correction gated on ``Run_Cond !IsUsedDatabase``, which never fires for
    synthetic households (see ``study_allowance_routing.yaml``), so Brussels
    is out of scope for this suite.
    """

    return [
        _flanders_higher_education_full_case(),
        _flanders_higher_education_intermediate_case(),
        _flanders_secondary_full_case(),
        _wallonia_higher_education_case(),
        _flanders_higher_education_above_threshold_case(),
        _wallonia_above_threshold_case(),
    ]


def _flanders_higher_education_intermediate_case() -> Case:
    """Flanders higher-ed student in the intermediate income band: prorated.

    Deterministic single-household EUROMOD anchor (BE_2025, parent monthly
    yem 3000, post-uprate yem_sum 37981): bed_s = 2092.30 (a partial Flemish
    higher-education grant on the intermediate income band between the minimum
    and maximum thresholds).
    """

    return Case(
        case_id="be-study-allowance-flanders-higher-education-intermediate",
        period="2025",
        metadata={
            **BE_METADATA,
            "scenario": "flanders-higher-education-intermediate-band",
            "axiom_inputs": _routing_axiom_inputs(
                region=FLANDERS_REGION,
                supplied_flemish_amount=2092.30,
                supplied_french_community_amount=0,
            ),
            "euromod_inputs": _euromod_household_inputs(
                region=DRGN1_FLANDERS,
                student_dec=DEC_HIGHER_EDUCATION,
                parent_monthly_yem=3000,
                id_base=100,
            ),
        },
        outputs=(Concepts.BE_STUDY_ALLOWANCE,),
    )


def _flanders_higher_education_full_case() -> Case:
    """Flanders, low-income dependent higher-ed student: full Flemish amount.

    Verified EUROMOD anchor (BE_2025, synthetic household, parent monthly
    yem 500, post-uprate yem_sum 6330): bed_s = 3046.30.
    """

    return Case(
        case_id="be-study-allowance-flanders-higher-education-full",
        period="2025",
        metadata={
            **BE_METADATA,
            "scenario": "flanders-higher-education-low-income-full-amount",
            "axiom_inputs": _routing_axiom_inputs(
                region=FLANDERS_REGION,
                supplied_flemish_amount=3046.30,
                supplied_french_community_amount=0,
            ),
            "euromod_inputs": _euromod_household_inputs(
                region=DRGN1_FLANDERS,
                student_dec=DEC_HIGHER_EDUCATION,
                parent_monthly_yem=500,
                id_base=200,
            ),
        },
        outputs=(Concepts.BE_STUDY_ALLOWANCE,),
    )


def _flanders_secondary_full_case() -> Case:
    """Flanders, low-income dependent secondary student: full base amount.

    Deterministic single-household EUROMOD anchor (BE_2025, parent monthly
    yem 500, post-uprate yem_sum 6330): bed_s = 1139.56 (the secondary base
    external full amount).
    """

    return Case(
        case_id="be-study-allowance-flanders-secondary-full",
        period="2025",
        metadata={
            **BE_METADATA,
            "scenario": "flanders-secondary-full-amount",
            "axiom_inputs": _routing_axiom_inputs(
                region=FLANDERS_REGION,
                supplied_flemish_amount=1139.56,
                supplied_french_community_amount=0,
            ),
            "euromod_inputs": _euromod_household_inputs(
                region=DRGN1_FLANDERS,
                student_dec=DEC_SECONDARY_EDUCATION,
                parent_monthly_yem=500,
                id_base=300,
            ),
        },
        outputs=(Concepts.BE_STUDY_ALLOWANCE,),
    )


def _wallonia_higher_education_case() -> Case:
    """Wallonia, low-income dependent higher-ed student: FWB allocation.

    Deterministic single-household EUROMOD anchor (BE_2025, parent monthly
    yem 200, post-uprate yem_sum 2532): bed_s = 869.21 (the French-Community
    factor-K prorated higher-education amount).
    """

    return Case(
        case_id="be-study-allowance-wallonia-higher-education",
        period="2025",
        metadata={
            **BE_METADATA,
            "scenario": "wallonia-higher-education-nonzero",
            "axiom_inputs": _routing_axiom_inputs(
                region=WALLONIA_REGION,
                supplied_flemish_amount=0,
                supplied_french_community_amount=869.21,
            ),
            "euromod_inputs": _euromod_household_inputs(
                region=DRGN1_WALLONIA,
                student_dec=DEC_HIGHER_EDUCATION,
                parent_monthly_yem=200,
                id_base=400,
            ),
        },
        outputs=(Concepts.BE_STUDY_ALLOWANCE,),
    )


def _flanders_higher_education_above_threshold_case() -> Case:
    """Flanders, higher-ed student above the Flemish income threshold: zero.

    Deterministic single-household EUROMOD anchor (BE_2025, parent monthly
    yem 5000, post-uprate yem_sum 63301): bed_s = 0 (household income above the
    maximum Flemish income threshold).
    """

    return Case(
        case_id="be-study-allowance-flanders-higher-education-above-threshold",
        period="2025",
        metadata={
            **BE_METADATA,
            "scenario": "flanders-higher-education-above-income-threshold",
            "axiom_inputs": _routing_axiom_inputs(
                region=FLANDERS_REGION,
                supplied_flemish_amount=0,
                supplied_french_community_amount=0,
            ),
            "euromod_inputs": _euromod_household_inputs(
                region=DRGN1_FLANDERS,
                student_dec=DEC_HIGHER_EDUCATION,
                parent_monthly_yem=5000,
                id_base=500,
            ),
        },
        outputs=(Concepts.BE_STUDY_ALLOWANCE,),
    )


def _wallonia_above_threshold_case() -> Case:
    """Wallonia, higher-ed student above the FWB threshold: zero.

    Deterministic single-household EUROMOD anchor (BE_2025, parent monthly
    yem 4000, post-uprate yem_sum 50641): bed_s = 0 (household income above the
    maximum French-Community income ceiling).
    """

    return Case(
        case_id="be-study-allowance-wallonia-above-threshold",
        period="2025",
        metadata={
            **BE_METADATA,
            "scenario": "wallonia-above-income-threshold",
            "axiom_inputs": _routing_axiom_inputs(
                region=WALLONIA_REGION,
                supplied_flemish_amount=0,
                supplied_french_community_amount=0,
            ),
            "euromod_inputs": _euromod_household_inputs(
                region=DRGN1_WALLONIA,
                student_dec=DEC_HIGHER_EDUCATION,
                parent_monthly_yem=4000,
                id_base=600,
            ),
        },
        outputs=(Concepts.BE_STUDY_ALLOWANCE,),
    )


def _routing_axiom_inputs(
    *,
    region: int,
    supplied_flemish_amount: float,
    supplied_french_community_amount: float,
) -> dict[str, float | int]:
    return {
        _routing_input("belgium_study_allowance_region"): region,
        _routing_input(
            "belgium_study_allowance_supplied_flemish_amount"
        ): supplied_flemish_amount,
        _routing_input(
            "belgium_study_allowance_supplied_french_community_amount"
        ): supplied_french_community_amount,
    }


def _euromod_household_inputs(
    *,
    region: int,
    student_dec: int,
    parent_monthly_yem: float,
    id_base: int,
) -> list[dict[str, float | int]]:
    """Father + mother + dependent student child, EUROMOD BE input rows.

    Income is the MONTHLY convention the ``euromod_inputs`` escape hatch
    passes through verbatim (no adapter-side annualization): the father's
    monthly ``yem`` reproduces the verified EUROMOD BE_2025 ``bed_s`` anchor
    for this household composition.

    ``id_base`` gives each case a disjoint ``idperson`` block. EUROMOD's
    family-relation resolution (``idmother``/``idfather``/``idpartner``) keys
    on ``idperson`` values that must be unique across every row in a run;
    reusing the same ids across cases corrupts results when more than one case
    shares a EUROMOD subprocess call. The comparison additionally runs one case
    per subprocess (``--comparison-batch-size 1``) so the suite is robust
    either way.
    """

    father_id = id_base + 1
    mother_id = id_base + 2
    student_id = id_base + 3
    return [
        {
            "idperson": father_id,
            "idpartner": mother_id,
            "idmother": 0,
            "idfather": 0,
            "dag": 48,
            "dgn": 1,
            "dms": 2,
            "dcu": 0,
            "ddi": 0,
            "dec": 0,
            "drgn1": region,
            "les": 3,
            "yem": parent_monthly_yem,
        },
        {
            "idperson": mother_id,
            "idpartner": father_id,
            "idmother": 0,
            "idfather": 0,
            "dag": 48,
            "dgn": 2,
            "dms": 2,
            "dcu": 0,
            "ddi": 0,
            "dec": 0,
            "drgn1": region,
            "les": 3,
            "yem": 0,
        },
        {
            "idperson": student_id,
            "idpartner": 0,
            "idmother": mother_id,
            "idfather": father_id,
            "dag": 20,
            "dgn": 1,
            "dms": 1,
            "dcu": 0,
            "ddi": 0,
            "dec": student_dec,
            "drgn1": region,
            "les": LES_STUDENT,
            "yem": 0,
        },
    ]


def _routing_input(name: str) -> str:
    return f"{ROUTING_MODULE}#input.{name}"
