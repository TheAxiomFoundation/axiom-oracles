"""Published 2026 federal amounts that more than one tax projection reads.

An amount lives here when two projections, or two slots of the Axiom oracle
bridge, read it, so the legs of one Case cannot disagree about it. Each
constant quotes the publication that sets it.
"""

from __future__ import annotations

#: SSA, "Cost-of-Living Increase and Other Determinations for 2026",
#: 90 FR 49047 (Nov. 3, 2025), FR Doc. 2025-19763: "The OASDI contribution and
#: benefit base is $184,500 for remuneration paid in 2026 and self-employment
#: income earned in tax years beginning in 2026."
OASDI_CONTRIBUTION_AND_BENEFIT_BASE_2026 = 184_500

#: Rev. Proc. 2025-32, section 4.31: "For taxable years beginning in 2026, in
#: determining a taxpayer's excess business loss, the amount under
#: § 461(l)(3)(A)(ii)(II) is $256,000 ($512,000 for joint returns)."
EXCESS_BUSINESS_LOSS_THRESHOLD_2026 = 256_000
EXCESS_BUSINESS_LOSS_THRESHOLD_JOINT_2026 = 512_000

#: Rev. Proc. 2025-32, section 4.23: "For taxable years beginning in 2026, the
#: exemption amount referred to in § 152(d)(1)(B) is $5,300." Section
#: 152(d)(1)(B) is the qualifying-relative test: gross income "less than the
#: exemption amount".
QUALIFYING_RELATIVE_GROSS_INCOME_LIMIT_2026 = 5_300
