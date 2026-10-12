# Alabama TY2025 reference bundle

Saved observations for 1,155 Alabama eCPS households, `taxsimid` 88052–89206.
The manifest binds the exact supplied input bytes, release provenance, engine
versions and flags. The largest source CSV is about 1.14 MB; no LFS is used.

| File | Role |
|---|---|
| `households.csv` | Original TAXSIM-format household inputs, state 1, TY2025 |
| `engine_outputs_state1.csv` | Primary PolicyEngine/TAXSIM release observations, one row per source and household |
| `engine_outputs_state0.csv` | Earlier state-0 observations for federal/SALT diagnostics |
| `pe_intermediates.csv` | Separate PolicyEngine replay exposing Alabama and federal components |
| `ground_truth_fixtures.yaml` | Official document extracts, including page references and source caveats |
| `manifest.json` | SHA-256 and size of every other bundle file; full upstream release provenance |

Run `uv run --extra dev python scripts/generate_al_income_tax_2025.py` from the repository
root to verify the hashes and generate the comparison. The two Axiom federal
feed variants await `us-al/policies/income_tax/2025_resident_liability.yaml` in
rulespec-us. Encoding is blocked on signing decision d270; the narrow corpus
union is tracked in axiom-corpus#746. Pending Axiom amounts are unavailable.

The primary state-1 release is `full-ecps-comparison-run-35859275514`, associated
with pe-taxsim PR #1204 at `7d75045`. Its recorded execution commit is
`2b69146bfb2e16f83e1c021d72c4258d67872190`; these are distinct provenance fields.
The state-0 diagnostic release is `full-ecps-comparison-run-35633580408`. Both
record PolicyEngine-US 2.6.17, `assume_w2_wages=true`, native SALT, and the TAXSIM
binary identity retained in the manifest. The full release files were checked
against their recorded output hashes when this bundle was assembled. Only
these small Alabama slices are committed here.

The PE intermediate file is a replay, not a replacement for the released
liability observations. Saved AGI, taxable income and liability differ from
the release by at most $4, $8 and $0.50 respectively; the source review traced
these differences to float32 adapter/serialization rounding. The generator
retains the saved values and exposes the drift. TAXSIM `v33` semantics remain
unverified; taxable-income residuals are not direct federal-deduction amounts.
Any formula fitted to TAXSIM outputs is an `observed_behavior_fit`, not law.

Federal input amounts follow the booklet p31 worksheet. TAXSIM does not
report Form 1040 line 22; `fiitax` must not replace it. Missing form-line
amounts remain unavailable. PE's saved total American Opportunity Credit is
not independently a direct observation of refundable Form 1040 line 29.

Module availability enables compilation, but these saved feeds still lack
line 22, refundable AOTC, refundable adoption, and Schedule 3 line 13a. Until
verified amounts are supplied, the compiled lane reports `unavailable_input`.
A refreshed engine-output CSV may include columns named by the crosswalk
(for example `form_1040_line_22`) with a corresponding `<field>_status` column
equal to `verified_form_line`. Update the manifest and provenance with that
evidence; the generator will pass those amounts to the adapter automatically.
The RuleSpec input/output names remain a proposed contract until encoding lands.

Fixtures preserve the supplied YAML bytes, including printed-source caveats.
Every fixture includes `document` and `page`. The sole unpaginated statutory
fixture, `retirement_exemption_parameters`, uses `page: null` and identifies
`us-al/statute/40-18-19` by `scope: "(a)(13)"`. The standard-deduction chart's
printed MFJ overlap is flagged in `std_03`; the inferred correction is not
silently substituted for the printed interval. These extracts are evidence,
not Python implementations of Alabama tax law.

The signed source corpus is `us-rulespec-2026-09-14-wave4-r2-union`, content
SHA-256 `528f596ac8c9e4b0f99d43489425a1e901b9b0ac84cece411560acd9a62fe30f`.
This identity is supplied provenance; this saved-output lane does not perform
corpus signature verification. Refreshing the bundle requires reviewing the
new bytes and updating their manifest hashes together.
