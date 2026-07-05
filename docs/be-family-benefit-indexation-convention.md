# Belgium family-benefit indexation convention

This note fixes the convention for encoding Belgium regional family-benefit
amounts across the BE lane, so statutory-base modules and applied-current
modules stop disagreeing silently. It was written to resolve
[axiom-oracles#114](https://github.com/TheAxiomFoundation/axiom-oracles/issues/114),
where the Wallonia child-benefit residual quoted `68.39 / 31.09 EUR/month`
against a provision (Walloon decree Article 13) whose statutory text carries
`55 / 25 EUR/month`. Both numbers are correct; they are the same Article 13
concept at two indexation states, encoded in two different modules.

## The two surfaces

Regional family-benefit decrees enact a **statutory base amount**. The amount
actually paid in a given year is that base **indexed** to the pivot index in
force. The BE lane keeps these as two separate RuleSpec surfaces:

| Surface | Example rule | Value | Module | Grounding |
| --- | --- | ---: | --- | --- |
| Statutory base (unindexed) | `wallonia_family_benefits_social_low_income_monthly_amount` | 55 | `rulespec-be` `be-wal/statutes/family_benefits/amounts.yaml` | Walloon decree of 8 February 2018, Article 13 §1 item 1 (corpus `be-wal/statute/decret/2018/02/08/2018201006/article/13`, body: "55 euros") |
| Applied 2025 (indexed) | `belgium_child_benefit_wallonia_article_13_2025_low_income_monthly_social_supplement` | 68.39 | `rulespec-be` `be/statutes/family_benefits/child_benefit_base_2025.yaml` | AVIQ consolidated amount table 1 February 2025 (corpus `be-wal/guidance/aviq/family-benefits/amount-scale-2025-02/page-4`, body: "Revenus < 1er plafond 68,39 EUR") |

The two differ by indexation (about 1.24x). The AVIQ table discloses the index
it is pinned to on page 1: "Rattache a l'indice-pivot 130,67 (base 2013 =
100)".

## Convention

Encode both surfaces, and make the relationship explicit in each:

1. **Statutory-base modules** carry the raw enacted amount with a proof atom
   citing the decree article whose body contains that amount. The module and
   the amount rules must disclose that these are unindexed base values and name
   the applied module that carries the current indexed value.
2. **Applied-current modules** carry the indexed value with (a) the index date
   in the rule `source` (e.g. "from 1 February 2025 at pivot index 130.67"),
   (b) a proof atom citing the official amount schedule (AVIQ / Iriscare /
   GPedia) whose body contains the indexed value verbatim, and (c) a reciprocal
   reference to the statutory-base module and its raw value.

This is the general rule already followed by the applied 2025 surfaces
(`child_benefit_base_2025.yaml`) and the Flemish `birth_allowance.yaml`. Prefer
the indexed value with its index date and an official-schedule proof atom
whenever an applied surface is needed; keep the statutory base as its own
module for provenance, the way `be/statutes/property_tax/cadastral_income_indexation.yaml`
keeps the CIR 1992 Article 518 base and the annual coefficient separate.

Do **not** silently place an indexed value under a rule named or sourced only
to the statutory article, and do **not** leave a statutory-base amount looking
like the applied value. If the indexed value is not published in any corpus
provision body, stop and file a corpus defect (the corpus#205 DG class) rather
than fabricate it.

## Why not fold indexation into one module

The decree does not publish the coefficient that takes 55 to 68.39 for a given
year; the applied amount comes from the administrator's official schedule, not
from a decree-stated multiplier. Encoding the applied value directly from the
schedule (convention b) is what the corpus grounds. A derived
base x coefficient path (convention a) would need a decree- or law-sourced
coefficient atom that the Walloon family-benefit corpus does not currently
carry, so it is not used here.

## Oracle record

The Wallonia residual in
`axiom_oracles/data/euromod_issues.json`
(`euromod-be-2025-wallonia-pre-2020-child-benefit-supplement-cumulation`) and
the `known_causes.json` entry name the applied 2025 indexed amounts (68.39 and
31.09 EUR/month) and their AVIQ source, and record the statutory base (55 and
25 EUR/month) and its module, so the quoted magnitude ties unambiguously to the
rule it comes from. The residual arithmetic reconciles under the indexed
reading: 820.68 = 68.39 x 12 and 373.08 = 31.09 x 12.
