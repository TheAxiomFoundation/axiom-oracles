# Source-bound tariff blockers and repair handoff

The continuation adds **15 scopes** beyond the preserved six-scope milestone.
All **21 original gaps** now have bounded source/runtime receipts: 12 without
legal counterexamples under their test contracts, seven with counterexamples,
one post-expiry-only and one diagnostic-only. **All 58 actual-entry groundings
remain uncaptured; zero scopes are fully admitted.** This is evidence coverage,
not closure or legal certification.

RuleSpec findings below refer to immutable commit
`4f591c4267063094cc6da9d590872ea982940b81`. Paths beginning `us/` are in
`TheAxiomFoundation/rulespec-us`. No RuleSpec or adapter was changed. Repairs
must follow the Foundation's supervised encoder/composition workflow and retain
the original proof generation. This sprint authorizes no release or activation.

## Reproducible legal counterexamples

| Scope / cases | Primary source and pinned code | Exact result and required next step |
| --- | --- | --- |
| Loading/transit safe harbor / 20 | [USITC Chapter 99, PDF page 648](https://hts.usitc.gov/reststop/file?release=2026HTSRev15&filename=Chapter%2099#page=648), heading 9903.05.85; [Federal Register action](https://www.govinfo.gov/content/pkg/FR-2026-07-28/pdf/2026-15181.pdf). [Witness line 3698](https://github.com/TheAxiomFoundation/rulespec-us/blob/4f591c4267063094cc6da9d590872ea982940b81/us/policies/cbp/us-tariff-duty/composition.yaml#L3698); [generated ch95 line 3490](https://github.com/TheAxiomFoundation/rulespec-us/blob/4f591c4267063094cc6da9d590872ea982940b81/us/policies/cbp/us-tariff-schedule/generated/ch95/ch95.yaml#L3490). | The source-qualified safe harbor ends July 28 at 00:01 Eastern. At 00:00:00 and 00:00:59, the Day program already returns false. Covered-origin examples charge 10% instead of 0%; US negative-origin examples retain zero duty but lose the predicate. Define a timestamp qualification contract and repair the supervised encoding/composition; do not erase the first-minute cases. |
| China 2024 action and solar / 4 across two scopes | [USITC Chapter 99, PDF pages 513 and 685–686](https://hts.usitc.gov/reststop/file?release=2026HTSRev15&filename=Chapter%2099#page=513), note 31(b)/(c), 9903.91.01/.02; [2024 USTR action, PDF pages 21 and 24](https://www.govinfo.gov/content/pkg/FR-2024-09-18/pdf/2024-21217.pdf#page=21). [Actual adapter lines 385–386](https://github.com/TheAxiomFoundation/rulespec-us/blob/4f591c4267063094cc6da9d590872ea982940b81/tools/b16_entry_flags.py#L385). | Adapter hardcodes both flags false. China aluminum 7601.10.30 and solar 8541.42.00 return zero instead of 25%/50% in generated modules; source-declared membership paths match. Implement complete source-bound membership and heading-specific rate/exclusion contracts. One broad 2024-action Boolean cannot by itself distinguish every action rate family. |
| Section 122 exemption/activation / 2 | [Proclamation 11012, PDF page 5, paragraph 7](https://www.govinfo.gov/content/pkg/FR-2026-02-25/pdf/2026-03824.pdf#page=5); [generated ch95 line 2822](https://github.com/TheAxiomFoundation/rulespec-us/blob/4f591c4267063094cc6da9d590872ea982940b81/us/policies/cbp/us-tariff-schedule/generated/ch95/ch95.yaml#L2822). | At February 24, 2026 00:00:00/00:00:59 Eastern, the program charges 10% before the source's 00:01 activation. Define/encode minute-accurate activation. Independently resolve the end-minute tension between the proclamation's July 24 00:01 wording and Rev15's close-of-July-23 compiler note; no end-minute outcome is asserted here. |
| China list123, sampled on list3 / 1 | [USITC Chapter 99, PDF pages 273, 287 and 672](https://hts.usitc.gov/reststop/file?release=2026HTSRev15&filename=Chapter%2099#page=287), note 20(f), heading 9903.88.03; [generated ch22 lines 3243 and 3246](https://github.com/TheAxiomFoundation/rulespec-us/blob/4f591c4267063094cc6da9d590872ea982940b81/us/policies/cbp/us-tariff-schedule/generated/ch22/ch22.yaml#L3243). | China beer 2203.00.00 charges 50% instead of 25% because list123 and the line-D term both add 25%. Witness and actual membership adapter behave as recorded. Repair the generated composition's overlapping charge, then replay the receipt and relevant negative controls. The batch does not exhaust list1/list2 or exclusions. |
| Primary aluminum and steel / 3 across two scopes | [USITC Chapter 99, PDF pages 241 and 668](https://hts.usitc.gov/reststop/file?release=2026HTSRev15&filename=Chapter%2099#page=241), note 16(d), headings 9903.82.02/.04. [Witness line 3195](https://github.com/TheAxiomFoundation/rulespec-us/blob/4f591c4267063094cc6da9d590872ea982940b81/us/policies/cbp/us-tariff-duty/composition.yaml#L3195), [ch76 line 3037](https://github.com/TheAxiomFoundation/rulespec-us/blob/4f591c4267063094cc6da9d590872ea982940b81/us/policies/cbp/us-tariff-schedule/generated/ch76/ch76.yaml#L3037), [ch72 line 3678](https://github.com/TheAxiomFoundation/rulespec-us/blob/4f591c4267063094cc6da9d590872ea982940b81/us/policies/cbp/us-tariff-schedule/generated/ch72/ch72.yaml#L3678). | UK treatment requires at least 95% qualifying UK metal under note 16(d), as well as UK origin. Both aluminum paths charge 25% with stipulated 94% instead of 50%; generated steel charges 50% at stipulated 95% instead of 25%. Add source-bound smelting/casting or melting/pouring provenance and the threshold qualification. These stipulated provenance facts are absent from the runtime input contract; they are not actual-entry evidence. |

All **30 counterexample cases** are retained in each receipt's
`known_mismatches`, with full requests, native responses, traces and expected
source values. Rates above are the queried components, not total effective
customs duties. Replaying the existing responses proves reproducibility of the
finding; it does not repair the rule or establish legal correctness.

## Other precise limits

- **Non-ad-valorem Column 2:** 41 real diagnostic calls return 29 outputs and
  12 native missing-input errors. The pinned engine rejects absent
  `resolved_non_ad_valorem_column2_rate` rather than substituting zero.
  [Generated ch99a, line 2117](https://github.com/TheAxiomFoundation/rulespec-us/blob/4f591c4267063094cc6da9d590872ea982940b81/us/policies/cbp/us-tariff-schedule/generated/ch99a/ch99a.yaml#L2117)
  is the MFN resolution consumer. [General Note 3, PDF page 4](https://hts.usitc.gov/reststop/file?release=2026HTSRev15&filename=General%20Note%203#page=4)
  supplies the four Column 2 origins. The selected Chapter 99 rows are expressly
  historical/expired: 9901.00.50 before 2012; 9902.01.01/9902.09.43 through 2020.
  The 2026 calls are interface diagnostics. **Zero legal resolved rates are
  validated.** Stop until there is valid-vintage classification, applicable
  underlying duty, quantities/units/customs value and an authorized real
  resolver receipt bound to those facts. Numeric sentinels are not duty rates.
- **Section 201 CSPV:** all 20 cases are after the safeguard's February 6, 2026
  expiry. The composition begins February 15. [Proclamation 10339, PDF page 5](https://www.govinfo.gov/content/pkg/FR-2022-02-09/pdf/2022-02906.pdf#page=5)
  and Rev15 Chapter 99 bind that limit. An authorized vintage program, complete
  source chain and quota facts are needed for active-period claims. No active
  rate/quota/classification coverage is inferred from zero post-expiry outputs.
- **HTS identity:** nine raw aliases differ at the direct witness interface,
  which compares canonical dotted text ([witness line 707](https://github.com/TheAxiomFoundation/rulespec-us/blob/4f591c4267063094cc6da9d590872ea982940b81/us/policies/cbp/us-tariff-duty/composition.yaml#L707)).
  The actual adapter's canonicalization and tested generated integer-key
  lookups match. Specify normalization at the caller boundary; these nine
  alias differences are separate from the 30 legal counterexamples.
- **USMCA and the six original exceptions:** tested Boolean facts are
  stipulated. General Note 11(b), claims, CBP determinations and transaction
  documentation still require source-linked entry evidence. Country of origin
  alone does not establish USMCA qualification.
- **Untested source families and transactions:** the original 13 partial or
  pending source families, subordinate-instrument census and typed law-derived
  dependencies remain separate closure work. The 21 bounded receipts do not
  resolve all 58 input groundings or certify an import transaction.

## Current-base and review gates

Current-base integration is held separately from these source findings.
`axiom_oracles/comparison/comparator.py:61` now validates result populations and
requested outputs; `axiom_oracles/comparison/report.py:133` validates submitted
cases before accumulation. These are real semantic changes relative to the
historical causal proof. The source-change admission gate correctly expires.
The canonical merged tariff certificate is **conformant=false,
exercised/executable=true, closed=false, certified=false**. See
[the exact digest/receipt references](continuation-integration-hold.json).

Do not mechanically repin the four historical proofs to current code, revert
main, or rerun the 216,111,132-unit selector campaign just to remove the hold.
The admission owner must choose explicit historical evaluator pinning or a
justified targeted reproduction and apply every existing gate. Tests asserting
the preserved milestone's conformant=true are not evidence of green CI on this
merged branch. This sprint reports targeted passing tests only.

Final Fable review remains required. The sole prior dispatch failed before
review because the nested sandbox could not access the actual account token.
Root can arrange one bounded review through existing authorized capacity; no
review pass, account retry, reset or overflow is claimed. Launch runbook Gates
2–3 still require Max's prebrief/contact and explicit publication authorization.
No fabricated signature, certificate, activation or release is permitted.

## Exact bounded reproduction

From this oracles worktree, with the existing environment, pinned engine,
RuleSpec and corpus checkouts, run a selected producer as needed:

```sh
python -m scripts.build_us_tariff_note52_boundary_evidence --check
python -m scripts.build_us_tariff_identity_evidence --check
python -m scripts.build_us_tariff_china_action_evidence --check
python -m scripts.build_us_tariff_temporal_evidence --check
python -m scripts.build_us_tariff_china_list_evidence --check
python -m scripts.build_us_tariff_column2_evidence --check
python -m scripts.build_us_tariff_metal_evidence --check
```

Each was already run successfully for this evidence generation. These commands
execute the real pinned Axiom engine and reproduce counterexamples as recorded.
They do not run the huge selector scan. The source receipt and corresponding
`*-sources` directories retain authoritative URLs, retrieval times, sanitized
HTTP records, PDF bytes and SHA-256 values. Original Chapter 99 signature
verification is recorded in `live-sources/receipt.json`; the other new captures
are unsigned. No newly created ingest signature is claimed.

The separate combined archive is `tariff-continuation-replay.tar.gz`,
45,356,596 bytes, SHA-256
`4b913f987afb7db5910dbddb62f623049047d284dc2bee8669ee6bae83f65eff`.
Verify that trusted archive hash before extraction/executing its verifier.
After safe extraction, independently replay with no project or site packages:

```sh
python3 -I -S verify.py --verify-bundle . --manifest-sha256 \
  f4e9257e0e121ebbc0e5cc47adc3c443aa4f9bdd5994d30620253fb6f42c99aa
```

Requires macOS arm64 and Python 3.10+. It reproduces **843 cases / 1,817 outputs
and 12 native errors**, including the unchanged original 384/768. The archive
contains the actual executable, compiled programs, source evidence and full
receipts. It does not independently rerun Ed25519 verification, PDF extraction,
actual adapter producers or source recompilation; those are separately recorded
producer validations. Root YAMLs/scripts are included for inspection, not a
claim that every source import is bundled. No network or campaign cache is
needed for the compiled replay. The original archive remains unchanged.
