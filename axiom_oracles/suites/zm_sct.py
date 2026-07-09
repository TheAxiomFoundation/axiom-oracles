"""Zambia Social Cash Transfer oracle suite (MicroZAMOD ``bsa_s``).

``zm-sct`` compares the rulespec-zm SCT standing transfer values (the
MCDSS Ministerial Statement: K200 per month per household, doubled to
K400 for a household with a member with severe disability) against
MicroZAMOD ``bsa_s`` on the **ZM_2024** system, whose amounts equal the
standing scheme exactly (probed: 200/month base, 400/month severe
disability for a 65-plus zero-asset household).

Finding 6 disposition (rulespec-zm#1, probed live): the ZM_2025 system
pays 400/month base and 600/month severe-disability (probed 4,800 and
7,200 per year) - annualizing the time-bounded drought measures (the
12-month K200 top-up and the Drought Emergency Cash Transfer, both
ending June 2025 per the 2025 Budget Address) or anticipating the 2026
budget's permanent structure; the standing 2025 scheme remains
200/400, and even in the drought window the severe-disability amount
is double-the-base (800 with the top-up), not base-plus-200.

Eligibility: MicroZAMOD gates bsa on categorical criteria (65-plus,
severe disability, female head with dependent children, child-headed)
AND a community-based proxy-means livelihood score with urban/rural
cutoffs whose coefficients are survey-calibrated by the model team
(the MicroZAMOD country report cites the ZRA/MCDSS harmonized
targeting methodology, not a published instrument). The suite cases
use a 65-plus zero-asset urban household, which the proxy score
qualifies deterministically (probed scaled score 99.06 < 460), so no
random draw or score bridge is needed; the encoded module takes
eligibility as an input per the Ghana LEAP convention.

License discipline as elsewhere: the SOUTHMOD bundle is referenced by
path only; expected values are values MicroZAMOD itself produced; no
bundle content is committed.
"""

from __future__ import annotations

from ..core.case import Case, Concepts, Entity
from .zm_core import ZM_METADATA, ZM_PERIOD_2024, _zm_base_row

SCT_MODULE = "zm:policies/mcdss-sct/ministerial-statement-transfer-values"


def _sct_household(idperson: int, severe_disability: int) -> dict[str, float | int]:
    row = _zm_base_row(1, idperson)
    row.update({"dag": 65, "dgn": 0, "ddi01": severe_disability})
    return row


def zm_sct_cases() -> list[Case]:
    """Sixty-five-plus zero-asset household SCT cases for the bsa_s oracle."""
    return [
        _sct_case("zm-sct-standing-base", severe_disability=0),
        _sct_case("zm-sct-severe-disability-double", severe_disability=1),
    ]


def _sct_case(case_id: str, *, severe_disability: int) -> Case:
    beneficiary_input = f"{SCT_MODULE}#input.sct_beneficiary_household"
    disability_input = f"{SCT_MODULE}#input.severe_disability_member"
    return Case(
        case_id=case_id,
        period=ZM_PERIOD_2024,
        metadata={
            **ZM_METADATA,
            "scenario": "sct-standing-transfer-values",
            "axiom_inputs": {
                beneficiary_input: 1,
                disability_input: severe_disability,
            },
            "euromod_inputs": [_sct_household(101, severe_disability)],
        },
        entities=(
            Entity(
                entity_id="head",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: 65,
                    Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
                },
            ),
        ),
        outputs=(Concepts.ZM_SCT_MONTHLY_TRANSFER,),
    )
