"""Zambia Social Cash Transfer oracle suite (MicroZAMOD ``bsa_s``).

``zm-sct`` compares the rulespec-zm SCT standing transfer values (the
MCDSS Ministerial Statement: K200 per month per household, doubled to
K400 for a household with a member with severe disability) against
MicroZAMOD ``bsa_s`` on the **ZM_2024** system, whose amounts equal the
standing scheme (observed in the live run: 200 per month base, 400 per
month with severe disability). The module is Month-period, so the
comparison turns the adapter's x12 output annualization off and
compares monthly amounts.

Finding 6 (rulespec-zm#1; a ledger entry in
``axiom_oracles/data/microzamod_issues.json``, outside the grid):
ZM_2025 pays 400 per month base and 600 per month with severe
disability (re-probed on 2026-10-04 on the same households), where the
captured Ministerial Statement gives 200/400. The July explanation,
that ZM_2025 annualizes time-bounded 2025 drought measures (a K200
top-up and a Drought Emergency Cash Transfer said to end in June 2025)
or anticipates a later permanent structure, rests on the 2025 Budget
Address, which is not in the captured corpus; it is unverified.

Eligibility: the encoded module takes SCT eligibility and the
severe-disability flag as inputs (the Ghana LEAP convention), so the
cases set them directly. On the model side both cases use a 65-plus
household with no other income or assets, which MicroZAMOD treats as
eligible (probed: both households receive ``bsa_s`` on ZM_2024 and
ZM_2025). A household the model did not treat as eligible would return
0 and mismatch, so the live run checks this too.

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
