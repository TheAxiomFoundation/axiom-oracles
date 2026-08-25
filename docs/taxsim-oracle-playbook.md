# TAXSIM Oracle Playbook

How the NBER TAXSIM-35 oracle is wired into axiom-oracles as a first-class
oracle, where it is authoritative, and how to extend its coverage. The
mechanics of the comparison path (shared input row, state-code conversion,
law-year support) live in [policyengine-taxsim.md](policyengine-taxsim.md);
this page is the standing recipe and the standing *judgment*.

Every TAXSIM lane grades **Axiom** against TAXSIM. Oracle-vs-oracle
comparisons (PolicyEngine vs TAXSIM) are diagnostic tooling for triage
sessions, not published lanes — an agreement rate that does not bear on
Axiom's correctness does not go on the dashboard.

## Identity

Every TAXSIM number is produced by the Fortran binary bundled in the pinned
`policyengine-taxsim` release. `axiom_oracles/adapters/taxsim/taxsim_pins.json`
is the **single source of truth** for that identity (release version, PyPI
artifact hashes, per-binary SHA-256). Runtime code resolves the version via
`axiom_oracles.adapters.taxsim.pins.pinned_version()`; the only versioned
literal allowed in the repo is `pyproject.toml`'s dependency declaration, and
`tests/test_taxsim_pin.py::test_no_divergent_version_literals` enforces both
rules (the #266 incident — a stale literal silently regenerating four suites
at the wrong law year — is why).

## Where TAXSIM is graded

| Lane | Population | Concepts | Column |
| --- | --- | --- | --- |
| `co-state-income-tax-taxsim` | CO Populace slice | CO state liability | `siitax` |
| `co-tax-intersection-taxsim` | CO Populace slice | 9 federal + CO state | per mapping |
| `fiit-taxsim-ecps` | national Populace | std deduction, EITC, FICA | per mapping |

The national federal lane is scoped to itemization-*independent* concepts.
Smoke-verified 2026-08-23: liability, taxable income, tax before credits,
and AMT pull in the oracle-bridge's generated state-income-tax leg for the
SALT/itemization choice, and that leg implements Colorado only —
`_prepare_cases_for_engines` filters those concepts to CO households, so a
national sample prepares zero cases. Growing the state bridge beyond
Colorado is the unlock for a national liability lane; until then the CO
intersection suite carries those concepts. CTC/CDCC are excluded from the
national lane on signal grounds (the 2026 binary's child-credit gap makes
every child row a known NBER artifact).
| State grids (~39 suites) | 12-case synthetic grids | per-state liability concept | per mapping |
| Populace campaign | national Populace, 43 jurisdictions | per-state output concept | per mapping, or skipped |

**The graded output column is always resolved from
`axiom_oracles/config/concept_mappings.yaml`**, never hardcoded:

- Final-liability concepts map `siitax` (state) / `fiitax` (federal).
- Pre-credit schedule concepts map **`staxbc`** — state tax before credits.
  Verified against the pinned binary: `staxbc − v40 (total credits) =
  siitax`. This is what upgraded UT and KY from "supplemental" to exact
  peers and gave AL, GA, AR, MS, and DE their first TAXSIM legs.
- A concept with **no** `taxsim` mapping is **skipped, never guessed**. The
  populace runner records these in `taxsim_skipped_states`. As of 2026-08-23
  the only skip is CA (Behavioral Health Services Tax — no truthful TAXSIM
  surface exists; do not map it). CT/DC/KS/MN/OH were probe-verified and
  mapped to `staxbc` the same day; the probe notes live on their mapping
  entries.

## Standing: where TAXSIM is authoritative vs advisory

**Authoritative** (a disagreement is presumptively an Axiom-side or
PolicyEngine-side issue):

- Federal core at 2026: OBBBA rate schedule, standard deduction, AGI
  (`v10`), taxable income, tax before credits, childless EITC, FICA/SECA
  (`tfica`).
- State flat-rate cores (e.g. CO's taxable × 4.40%).

**Advisory** (a disagreement is presumptively a TAXSIM-side vintage or model
gap; disposition it, do not chase the Axiom encoding):

- Any child-credit machinery at law year 2026: the pinned binary's CTC
  collapses to the $500 ODC path; ACTC, CDCC, and EITC-with-children return
  zero. These rows enroll in the standing NBER-gap disposition classes.
- State modules with extrapolated or un-enacted parameters (KY 4.0% vs
  enacted 3.5%, NC 4.25% vs 3.99%, GA 5.19% vs 4.99%; fractional-dollar
  parameter extrapolations in the `idtl=2` detail).
- NIIT bookkeeping against the composed Axiom program while
  axiom-encode#1213 keeps §1411 out of the composition (TAXSIM `fiitax`
  includes it; the residual equals TAXSIM's own `niit` column).
- Units where a **dependent** carries non-wage income: TAXSIM-35 has no
  dependent-income input, so the shared projection sums non-wage columns
  over head+spouse only, while the Axiom/PolicyEngine side computes the
  full tax-unit value. The one-sided AGI gap equals the dependents'
  unearned income; it is a projection-surface limitation (all lanes,
  ECPS and populace alike), not an oracle disagreement.

## Extending coverage

1. **New state, final-liability concept**: add `taxsim: siitax` to the
   concept's mapping entry. The grid generator and populace leg pick it up
   automatically.
2. **New state, pre-credit concept**: verify `staxbc` semantics for that
   state against the pinned binary first (one probe case:
   `staxbc − v40 = siitax` must hold and the credit split must match the
   concept boundary), then add `taxsim: staxbc` with a comment recording the
   probe.
3. **Component concepts** (state AGI `v32`, state taxable income `v36`,
   state EITC `v39`, state CTC `sctc`, …): the binary already returns all 54
   columns at `idtl=2`; what's missing are Axiom-side concepts to grade them
   against. When a state pipeline grows a reviewed intermediate output, map
   it — do not invent a concept for the column's sake. The same applies to
   federal `qbid` and `v17` (itemized deductions allowed): unmapped until an
   Axiom concept exists.
4. **Law year**: `TAXSIM_MAX_YEAR` (adapter) and the pinned release cap
   modeled law at 2026. When Axiom moves to 2027 before NBER does, the
   TAXSIM lanes stay pinned at their last supported year and their suites'
   `period` must NOT silently advance — bump the pin (a new
   `taxsim_pins.json`, full identity refresh, and re-baselined dispositions)
   or freeze the lane.

## Persistence discipline

TAXSIM suites persist **every** mismatch row in the committed dashboard copy
(`dashboard.max_mismatches` in the suite YAML — see
`co-tax-intersection-taxsim`'s 4,000-row cap and issue #439 for why: 438
unexplained rows were once physically untriageable behind the default
1,000-row cap). If a TAXSIM suite's mismatch count approaches its cap, raise
the cap in the same change that regenerates the suite.
