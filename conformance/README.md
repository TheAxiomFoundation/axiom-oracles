# Oracle conformance harness

This directory measures one thing with an auditable predicate rather than a
vibe: **for a given oracle, is Axiom in full parity with it?** "Full parity"
(CONFORMANT) means every policy the oracle *simulates* is either covered by an
Axiom comparison suite that matches, or excluded for a declared reason — with
zero unexplained mismatches and zero open Axiom-attributed gaps. Every residual
difference on a covered suite must be tied to a known issue in the **oracle**,
not in Axiom.

## What success looks like (the predicate)

For each jurisdiction the scoreboard evaluates, exactly:

```
conformant  ⇔  covered == in_scope
                AND unexplained_total == 0
                AND axiom_attributed_open == 0
```

* **`in_scope`** — the policies the oracle simulates that we hold Axiom to. Every
  other simulated policy is *excluded with a required reason* (see below), so
  "all programs" accounting stays honest: an excluded-with-reason policy is
  neither covered nor silently dropped — it is counted and shown.
* **`covered`** — an in-scope policy whose named suite has a **live committed
  comparison report with a returned same-case pair** for a registered output
  (see below). A suite named in the
  universe with no report is in scope and *not* covered; so is one whose report
  did not run. Coverage is evidence, not intent.
* **`unexplained_total`** — mismatches on covered suites with no explanatory
  disposition (from each report's `summary.dispositioned.unexplained_count`, or
  the raw `mismatch_count` for an undispositioned v2 report).
* **`axiom_attributed_open`** — the residual that is *Axiom's* to fix: disposition
  rows classed `axiom_encoding_gap`, plus mismatches whose disposition links an
  **open** `rulespec-*` issue. Upstream engine gaps and bridge artifacts are
  explained and do **not** block conformance.

The point of the split: a suite can be at 42% raw agreement and still be
conformant *for that policy* when every one of its residuals is a documented
upstream (oracle) behaviour — which is exactly the UK Universal Credit lane
today (raw 42%, explained 100%, unexplained 0, axiom-attributed 0).

## Execution attestation — a covered output needs a real comparison

The predicate reads a report's mismatch signals. Nothing in it used to ask
whether the report was the product of a run, and a report that ran *nothing*
has no mismatches: the graceful-skip artifact `run_comparison.py` emits when a
EUROMOD runtime is unavailable (`case_count: 0`, empty comparisons, one skip
error) scored as zero-unexplained, zero-Axiom-attributed — **conformant**
(axiom-oracles#355). Coverage was decided by suite-name registration, never by
evidence the named suite compared the outputs the universe registers.

Every candidate report is now attested against the universe's declared oracle
(`axiom_oracles/conformance/attestation.py`), in two layers:

1. **Execution — never waivable.** Strictly positive cases *and* comparisons;
   zero errors at every level the schema records them (`errors[]`,
   `summary.error_count`, `summary.errors_by_engine`, per-case
   `left_errors`/`right_errors`); Axiom **and** the universe's declared oracle
   both party to the comparison, and not the same engine twice; a recorded
   oracle identity (`provenance.oracle`) that does not contradict the universe's
   *model* identity — a `UK_2026` run cannot attest a `BE_2025` universe, and
   policyengine-uk evidence cannot attest a policyengine-us claim, though both
   write the same engine name. A runner execution stamp is optional; when
   present its execution claim, output bindings and counts must agree with the
   report body. A stamp cannot claim more than the artifact shows.
   A report failing any of these covers
   nothing: the policy scores **uncovered**, with the reason on the drill-down
   row, rather than covered-with-zero-unexplained.
2. **Output binding.** At least one of the universe row's registered
   `output_vars` must have a returned value from **both Axiom and the declared
   oracle in the same real case and actual comparison**. Each engine's binding
   to that registered output must be unambiguous: every applicable recorded
   output declaration must agree, and a retained ledger must identify the
   output of its actual comparison. The shared
   `observed_output_value` predicate requires a finite, non-null numeric value
   or an authoritative declared type, with no missing, error or skipped
   evidence contradicting that case and output. The valid case identities are
   intersected across engines: values returned in different cases cannot pair.
   Zero and `False` remain observations.
   A suite that ran cleanly against some other surface does not attest the
   policy it is registered under.

Runner stamps, grid engine-to-variable declarations, concept mappings and FIIT's
`SURFACE_OUTPUTS` identify candidate output names. Every candidate must pass the
same paired-value predicate. Counts, declarations, variable lists, metadata,
schema fields and a stamp alone cannot prove observation. Historical unstamped
reports can cover when their recorded values satisfy that predicate; never add
stamps to historical artifacts to restore coverage. Native Comparator and FIIT reports retain
per-case, per-output returned values in `observed_outputs`; scalar case values
can supply evidence when their binding is unambiguous. Summed concept or Yale
slot values do not prove individual component outputs, even when both engines
retain each member's returned value. A component requires its own scored
comparison identity and retained verdict and residual. FIIT retains its raw
returned oracle values and their Axiom counterpart separately from arithmetic
projections, so converting a missing value to zero cannot create coverage.
Native FIIT diagnostic outputs bind only to their explicitly recorded native
targets or per-output ledger; a grouped concept cannot promote an intermediate
value into a final policy output.

`attestation_waivers.yaml` preserves historical migration metadata for legacy
reports that could not show their output binding. It is **hand-authored and
shrink-only**: each approved entry is pinned to its suite, reason and complete
legacy artifact's SHA-256. All bootstrap entries are now retired; the empty
approval floor in `axiom_oracles/conformance/waivers.py` rejects their return
as well as new entries and suite/reason changes. The attestation check audits these
records and rejects stale entries; `--prune` only removes them. This metadata
never authorizes coverage: the scoreboard requires a valid same-case pair for
every covered policy and has no waiver bypass. The recorded reasons distinguish
what the run compared from what the artifact failed to record:

| Reason | Meaning |
| --- | --- |
| `compared_surface_differs` | The report records every surface it compared and none is a registered output — the suite ran against a different surface (e.g. a state grid comparing PolicyEngine's `*_before_refundable_credits` where the row registers the final `*_income_tax`). |
| `oracle_variable_not_recorded` | The artifact does not record which oracle variable each compared concept was bound to, so the binding cannot be verified either way. A rerun must retain unambiguous output bindings and same-case returned values from both engines. |

Migration history cannot supply a missing same-case pair or resolve an
ambiguous registered output. The published
`covered_with_waived_output_attestation` compatibility field remains visible at
zero; the current waiver file has no entries.

### Oracle release drift — measured, not blocking

The identity check blocks on the oracle's *model* (system, country, package) but
only **records** a different *release*. Reports legitimately lag a universe
re-pin: a PolicyEngine bump lands long before every population suite is rerun,
and retracting coverage backed by millions of real comparisons because the
universe moved would be the wrong trade. So each covered row carries
`oracle_release_drift` (the release its report actually recorded) and the
jurisdiction carries `covered_with_oracle_release_drift`.

The generated scoreboard and detail record the current drift counts and each
report's release. The claim a badge makes is "Axiom conforms to *this* oracle at
*this* release", so closing that gap means rerunning those suites at the pinned
release (or re-pinning the universe to what the evidence actually covers).
Making drift blocking is that scope decision, not a code change.

The previous reviewed head `3becffa7c` reported BE 22 and US-PE 28 covered
policies. The round-11 reviewed head `4f51296fb` then reported zero covered
policies in every jurisdiction because it required literal execution stamps.
Those are historical implementation baselines; `origin/main` is the primary
publication baseline (114/226 covered at the start of this review). The current
same-case rule was introduced at `5bf01dde2` with 53/226 covered, and later
rounds retain that total. The new guards reject synthetic attack reports that are not inputs to
these public coverage counts:

| Jurisdiction | Covered on `origin/main` | Covered after round-12 fixes |
| --- | --- | --- |
| BE | 23/23 | 10/23 |
| DK | 1/22 | 1/22 |
| UK | 21/21 | 6/21 |
| UK-PE | 23/23 | 13/23 |
| US-PE | 36/127 | 15/127 |
| Yale tariff | 10/10 | 8/10 |

Conformant jurisdictions fall from four on `origin/main` to zero after these
fixes. The generated scoreboard and detail files record the evidence for each
policy. Suite registrations and ratchet floors are regenerated from the reports
that pass; all policies remain in scope. A rerun restores missing coverage only by
recording valid paired values for the actual registered output, followed by
deliberate suite re-registration and artifact regeneration.

### Custom-producer recovery

An absent stamp alone no longer prevents a genuine custom run from covering.
The following producer paths differ in the returned evidence they retain:

| Producer | Recorded evidence and required recovery |
| --- | --- |
| UK EFRS (`_adapt_uk_efrs_to_v2`, `bridges/efrs_uk.py`) | The adapter records native Axiom/PolicyEngine output bindings and per-engine values for retained mismatch and divergence cases, preserving missing values and stop flags. The native producer excludes stopped or errored results from comparisons and retains their markers in an aggregate error ledger before display filtering, including cases omitted from displayed mismatches; the adapter preserves that ledger. Direct PolicyEngine outputs retain missing/nonfinite values rather than converting them to zero. The native report still drops matched case values; recovering a policy with only matching cases requires a per-output ledger written during `compare_outputs`, with stable entity IDs, both returned values and their direct native targets. `pe_expression` values such as the pre-takeup UC award have no final-output binding; run and retain the actual registered final output instead. |
| UK VAT (`generate_uk_vat.py`) | No stamp migration is needed: `build_report` already records each real `case_id`, returned `axiom`/`policyengine` values, and the explicit `VAT_OUTPUT`/`vat` engine bindings. A clean rerun can restore the registered `vat` output using those pairs. |
| Federal grids (`generate_federal_tax_liability.py`) | No stamp migration is needed for an unambiguous scored binding: `_build_report` already retains same-case returned scalars, named PolicyEngine components and the Axiom/PolicyEngine engine bindings. A comparison that sums oracle variables needs separately scored per-output comparisons, with their real Axiom counterparts and retained verdicts and residuals, for any registered component being claimed; `axiom_diagnostics` and bridge outputs are not final-output evidence. |
| State grids (`generate_state_income_tax_liability.py`) | The report retains same-case Axiom, PolicyEngine and TAXSIM scalar comparisons with named oracle targets. Many grids compare `*_before_refundable_credits` while the universe registers final `*_income_tax`; restoring those policies requires executing the final boundary and retaining its Axiom and PolicyEngine pair. Record the exact Axiom output URI instead of only `_MODULE[state]`, identify the Axiom/PolicyEngine pair roles explicitly in case rows or write a separate report for that pair, and retain per-engine output bindings and missing/error evidence for each pair. |
| Yale panel (`generate_us_tariff_panel.py`) | Single-column authority slots can use their recorded `expected`/`axiom` pairs with unambiguous slot bindings. Multi-column sums cannot cover constituent columns. Restoring their registered outputs requires retaining each real panel unit's source-column value and a separately executed Axiom counterpart, together with the exact column/output binding and independently scored verdict and residual. Keep the family aggregation for presentation, but retain the unit identity and comparison ledger; never split or copy a summed slot value into its component columns. |

The broader matched-case EFRS, final-boundary state and per-column Yale
migrations are documented here rather than inferred from counts or added to
historical artifacts. They require native producer changes and a genuine rerun
before those missing pairs can restore coverage.

## The pieces

| File / dir | What it is | Generated by |
| --- | --- | --- |
| `<jur>.yaml` | Per-oracle **universe**: schema `axiom_oracles.conformance.v1`. Header = oracle identity (`model_release/system`); one row per simulated policy with `{id, oracle_policy_name, output_vars, in_scope, exclusion_reason?, suite?, note?}`. | `scripts/generate_conformance_universe.py` |
| `scoreboard.json` | Per-jurisdiction headline + the exact predicate verdict. Mirrored to `dashboard/public/data/conformance_scoreboard.json`. | `scripts/conformance_scoreboard.py` |
| `detail/<jur>.json` | Per-policy drill-down (covered/uncovered/excluded, raw + explained rates). Mirrored to `dashboard/public/data/conformance_detail_<jur>.json`. | `scripts/conformance_scoreboard.py` |
| `history/<jur>/<YYYY-MM-DD>.json` | Dated scoreboard snapshots — the burn-down source of truth (survives rebases). | `scripts/conformance_scoreboard.py --snapshot` |
| `ratchet.yaml` | Monotonic floors/ceilings: `covered` may only rise; `unexplained`/`axiom_attributed_open`/`bridge_artifacts` may only fall. | `scripts/conformance_ratchet.py` |
| `attestation_waivers.yaml` | Schema `axiom_oracles.attestation_waivers.v1`. Historical migration metadata pinned to approved suites, reasons and complete legacy artifact SHA-256 values. It never authorizes coverage. HAND-AUTHORED and shrink-only; `--prune` only removes. | `scripts/conformance_attestation.py --prune` |
| `pe-axiom-standard.yaml` | PolicyEngine-attributed mismatch explanations without their Axiom side, grandfathered at the standard's introduction (the list may only shrink); `open_max`, the attributions without a companion test (it may only fall, except by the increment of a recorded raise); and the `debt_raises` log (it only grows). Monotonic against every committed version, merge-safe. See `dispositions/README.md`. | `scripts/pe_axiom_standard.py` |
| `compositions/<jur>.yaml` | Schema `axiom_oracles.compositions.v2`. Per covered suite: the runnable Axiom **program** the harness composes (RuleSpec import-set + repo-relative files), query entity, flat and record-targeted supplied inputs, relation tuples, and engine→input bridges — so the covered verdict is reproducible outside the harness. | `scripts/generate_conformance_compositions.py` |

`dashboard/public/data/conformance_burndown.json` is built from the dated
snapshots by `scripts/conformance_burndown.py`. The affected-rerun workflow
regenerates the dispositions merge (and its EUROMOD-BE coverage rollup),
appends the daily snapshot, and regenerates the scoreboard, detail, and
burn-down atomically with every report refresh it commits
(`scripts/commit_refreshed_report.sh`), so these derived artifacts can never
lag a bot-pushed report. The ratchet is the exception: it is never re-pinned
by the bot — advance it deliberately with `uv run
scripts/conformance_ratchet.py` after a genuine improvement.

## Execution-evidence validation

Comparison reports are aggregate views; committed case chunks are their
execution evidence. A versioned `cases/<suite>/index.json` binds each chunk's
name, SHA-256, and row count to the exact report path and SHA-256. A missing or
legacy index is recorded as `binding: unbound`: it remains visible in the
exercise census, but it cannot make a reference leg clean.

Validation deliberately has two cost tiers:

* `scripts/exercise_census.py` reuses its census-wide chunk pass to check
  cardinality and index binding for every registered report. It does not run a
  second structural/verdict scan across the full corpus.
* `scripts/certify.py` calls `axiom_oracles.evidence.validate_suite_evidence`
  only for the small set of suites named in its `PROGRAMS` registry. That
  strict path parses every row, checks IDs and compact shapes, rejects
  duplicates, and reconciles summary counts as `full`, `cardinality`, or
  `none`.

`full` means stored per-case verdicts reproduce all three summary counts.
`cardinality` means verdict-free chunk rows reproduce only
`comparison_count` (while the summary counts still conserve). `none` states
that the stored shape cannot support either claim. This report/chunk binding is
separate from execution attestation, which identifies engines and output
surfaces.

For a migrated suite, the comparison producer writes fresh chunks while it
still holds the full case corpus, then binds the slim report to those exact
bytes. The generic index generator may create the initial v1 index or verify an
idempotent one; it refuses to rebind changed v1 report/chunk identities because
aggregate counts alone cannot prove that replacement chunks came from the same
execution.

## Universe facts are generated, not hand-invented

The policy list and each policy's output variables come from parsing the
oracle's own model spine — **never from memory**:

* **UKMOD / EUROMOD** (`EuromodUniverseBackend`) parses
  `XMLParam/Countries/<CC>/<CC>.xml` for one system's policy list and, per
  policy, the output variables its functions write. It cross-checks each output
  against `VARCONFIG.xml` (the model's variable registry): a bare `*_s` output
  present in VARCONFIG is a **queryable** comparison surface; an `i_`-prefixed
  local or a non-registry name is **internal only** — recorded as evidence for
  an `unobservable_boundary` or `technical` classification.
* **PolicyEngine** (`PolicyEngineUniverseBackend`) enumerates PolicyEngine-UK's
  *simulated* surface from a pinned `policyengine-uk` checkout — the PE analogue
  of the EUROMOD policy list. It instantiates the checkout's
  `CountryTaxBenefitSystem` (variable registry only, no microdata/engine run) and,
  for each **program** in a declared spine (`PE_UK_PROGRAM_SPINE` — the fiscal
  instruments PE-UK models, one row per program), reads from code which of the
  program's bound output variables carry a `formula`. It classifies each into the
  four PE-UK simulation kinds the coverage matrix documents (rules-simulated /
  rate-from-frozen-input / reported-ceiling / pure-input) by inspecting the
  formula body: pure-input and reported-ceiling passthroughs map to
  `input_carrying` exclusions with per-row notes; rate-from-category rows are
  in-scope with a `rate_only` comparability note. The header pins the exact
  `policyengine-uk` version from the checkout's `pyproject.toml`. Backs the
  committed `uk-pe` universe (a distinct oracle from the UKMOD-backed `uk`).
* **PolicyEngine-US** uses the same `PolicyEngineUniverseBackend` with
  `PE_US_PROGRAM_SPINE` and `include_adds_subtracts=True`. PE-US is far larger, so
  the spine follows a deterministic rule biased to PE-US's own module tree
  (`policyengine_us/variables/gov`): one row per program instrument at the
  granularity of the household-facing output variable PE computes — federal income
  tax decomposed into its component surfaces + each credit in
  `gov.irs.credits.refundable`/`non_refundable`; payroll & SECA; each member of the
  `gov.household.household_benefits` parameter list + the `household_health_benefits`
  expansion (SNAP, SSI, Medicaid, ACA PTC …); and **per-state** rows for each
  `<state>_income_tax` (44 states) and each `STATE_TANF_VARIABLES` member (51 state
  cash-assistance programs). The per-state/national split is the rule following PE's
  tree, not a coverage choice: SNAP/SSI are single national variables (one row);
  income tax and TANF are per-state variables (per-state rows). Because PE-US
  composes many aggregates from an `adds`/`subtracts` variable list rather than a
  `def formula`, the backend treats those as computed rules surfaces; only genuine
  reported passthroughs (`social_security`, `unemployment_compensation`, …) are
  excluded `input_carrying` (the reform-only `basic_income` lever is `technical`).
  The header pins `policyengine-us` from the checkout's `pyproject.toml`, or the
  installed distribution metadata for a pip-installed tree. Backs the committed
  `us-pe` universe.

The generator overwrites the **facts** (`output_vars`, `oracle_policy_type`,
`internal_only_vars`) and **preserves the decisions** (`in_scope`,
`exclusion_reason`, `suite`, `note`) already committed in the file — exactly
like the affected-map generator. CI regenerates the facts and fails if the
committed universe drifts from the model (see gates), so a new or removed oracle
policy cannot silently disappear from the accounting.

## Exclusion reasons (required when out of scope)

A policy the oracle simulates but that we do not hold Axiom to must carry exactly
one reason:

| Reason | When |
| --- | --- |
| `input_carrying` | The "policy" only initialises/carries input variables (EUROMOD `InitVars` style), computing no instrument. |
| `technical` | Engine scaffolding — uprating, constants, income-list/assessment-unit defs, output framing, RNG, poverty line, indirect-tax imputation. |
| `takeup_adjustment` | Models benefit *take-up* (a stochastic behavioural draw) Axiom deliberately does not encode — e.g. UKMOD `BTA_uk`. |
| `not_a_policy` | A container/def block, or a module fully deactivated in the target system (all functions `n/a` → no output), so nothing is simulated. |
| `unobservable_boundary` | The oracle simulates the policy AND writes its outputs, but the comparison boundary depends on engine-internal variables absent from VARCONFIG — only the final output is queryable, so any non-degenerate comparison is impossible and the degenerate one vacuous. Requires a `note`. Canonical cases: UKMOD `bmu_s` (simplified national Council Tax Reduction), and the UKMOD TCO indirect-tax extension (`tco_calcbase`/`tco_calcadjusted`, whose consumption-tax bases are non-`_s` non-registry variables). |
| `extension_not_available` | The oracle *would* simulate the policy as a real instrument, but the compute content is not in the public release — the body is definitional only (no `OutputVar`) because the required extension/add-on and its microdata prerequisite are absent. Distinct from `technical` (genuine scaffolding) and `unobservable_boundary` (where the policy DOES compute). Requires a `note`. Canonical case: EUROMOD BE `tco_be` indirect tax (axiom-oracles#144). |
| `oracle_dataset_lacks_input` | The oracle DOES simulate the policy and its output IS observable (a queryable `_s` surface), but the input that *activates* it is absent from the public dataset's schema, so under the registration-free setup the policy never triggers and the only achievable comparison is vacuous (0 == 0). Distinct from `unobservable_boundary` (policy computes, but the comparison *boundary* is engine-internal) and `extension_not_available` (the compute content itself is absent). Requires a `note` naming the absent input and the probe evidence pointer. Canonical case: EUROMOD BE `bfapl_be` parental-leave allowance — encoded in rulespec-be#86 (RD 29.10.1997 / RD 02.01.1991) but the `lpb` parental-leave-months input is absent from the BE HHoT demo schema, so `bfapl_s` stays 0 for every synthetic case (probe lineage: axiom-oracles#150/#158/#160). |
| `oracle_models_repealed_law` | The oracle retains a policy whose governing law was repealed before the validation period, so Axiom has no current-law instrument to compare. Requires a `note` recording the repeal citation and probe evidence pointer. |
| `oracle_models_nonstatutory_amount` | The oracle computes a monetary value whose amount is discretionary, administratively imputed, or an in-kind service equivalent rather than a formula, rate, or cap fixed by statute or regulation. Distinct from a repealed statutory instrument. Requires a `note` naming the governing instrument and explaining why the modeled amount is non-statutory. |

### Comparability of an in-scope surface

Not every "simulated" policy is comparable to the same depth. The UK PolicyEngine
coverage matrix (`docs/uk-coverage-matrix.md`) shows the oracle's variable tree
has more than one kind of simulated output, so an in-scope row carries a
`comparability` qualifier (default `full`):

| `comparability` | Meaning |
| --- | --- |
| `full` | The oracle computes entitlement/liability from parameters and circumstances (a rules engine, or a EUROMOD `BenCalc` pipeline). Full statutory comparison. |
| `rate_only` | The oracle applies a parameterised rate table but the award category/eligibility is a frozen input (PE-UK PIP/DLA/AA `*_category`). Comparable on rate reforms, not eligibility rules. |
| `ceiling_only` | The oracle reads a `*_reported` input amount and applies only a capital/tariff screen or flat multiply, never computing the maximum from statute (PE-UK `jsa_income`/`esa_income`/`sda`). |

The UKMOD/EUROMOD universes are all `full` (they compare complete statutory
outputs); the committed `uk-pe` universe sets `rate_only` for the PE-UK
rate-from-category kinds (PIP/DLA, and the hybrid Carer's Allowance / Carer
Support Payment amount surfaces), while pure-input and reported-ceiling
passthroughs are excluded `input_carrying` rather than carried as in-scope
`ceiling_only` rows.

## Adopting a new jurisdiction

1. **Wire the backend config.** Add an entry to `JURISDICTIONS` in
   `scripts/generate_conformance_universe.py`: the model identity
   (`model`/`release`/`system`/`country`), the backend, the env var(s) that
   locate the model checkout, and a default path. Set `implemented: True`.
2. **Generate the universe facts.** With the model checkout present:
   ```bash
   uv run scripts/generate_conformance_universe.py <jur>
   ```
   Every policy appears with a proposed default scope. A queryable policy starts
   as the honest `in_scope: true, suite: null` uncovered state, while an
   unqueryable non-definition starts as `unobservable_boundary` and requires a
   reviewed note. Either way, the new row remains visible rather than passing
   as covered.
3. **Author the scope decisions.** For each row set `in_scope` and either the
   covering `suite` (for a policy an Axiom suite compares) or an
   `exclusion_reason` (+ the reason-specific `note` required above). Ground each
   decision in the model's own per-policy `Comment` and switch state — both in
   the XML — cross-checked against any coverage matrix. Re-run the generator; it
   preserves your decisions and refreshes the facts.
4. **Score, ratchet, snapshot.**
   ```bash
   uv run scripts/conformance_scoreboard.py --snapshot
   uv run scripts/conformance_ratchet.py --init      # first time only
   uv run scripts/conformance_burndown.py
   ```
5. The dashboard card appears automatically for any region with a scoreboard
   row.

## How ratchets move

Ratchets make progress irreversible. `covered_min` may only rise;
`unexplained_max`, `axiom_attributed_open_max` and `bridge_artifacts_max` may
only fall. CI (`conformance_ratchet.py --check`) recomputes the live scoreboard
and fails, naming the exact invariant, if any regressed:

* You **encode a new suite** that covers a policy → `covered` rises → re-pin:
  ```bash
  uv run scripts/conformance_ratchet.py
  ```
  (tightens the floor to the new, better number; never loosens it).
* A change **adds a mismatch** with no disposition → `unexplained` rises → CI
  fails. Fix the encoding, or add a schema-validated disposition classifying the
  residual (`dispositions/<suite>.yaml`).
* A change **introduces an Axiom encoding gap** (a disposition classed
  `axiom_encoding_gap`, or a linked open rulespec issue) → `axiom_attributed_open`
  rises → CI fails until the encoding is fixed.
* A change **classes more mismatches as `bridge_artifact`** → CI fails. This kind
  is *explained* by definition — "the comparison harness fed the engines
  different inputs; not an engine or encoding defect"
  (`dispositions/README.md`) — so growth in it is invisible to the predicate,
  which is exactly why it is ratcheted. Confirm each new row really is a
  different-inputs artifact rather than an encoding or scope gap wearing that
  label. Normal re-pinning cannot raise this ceiling: it retains
  `min(previous_ceiling, current_count)`, and `--init` preserves existing rows.
  Repair the bridge or reduce its residuals until the count is at or below the
  pinned ceiling, then tighten the ratchet and verify it:
  ```bash
  uv run scripts/conformance_ratchet.py
  uv run scripts/conformance_ratchet.py --check
  ```
  There is no supported ceiling-raising exception in this script. Accepting
  genuine growth would require a separate, explicitly reviewed change to the
  ratchet policy and baseline; a normal re-pin cannot accept it.

The denominator (`policies_in_scope`) is recorded, not ratcheted: when the oracle
model legitimately adds an in-scope policy, coverage is read against the new base.

## Recorded program compositions

A covered row names a *suite*, but the suite name alone does not say which
runnable Axiom program produced the covered comparison report. For the
EUROMOD-synthetic lane that program is assembled implicitly at run time:
`_run_euromod_synthetic_compare` invokes `cli compare euromod axiom --suite <name>`
with **no `--axiom-program`**, and the runner derives the RuleSpec import-set
from the `module#name` prefixes of the suite's output concepts
(`rulespec_imports_for_concepts`), compiles a generated program that imports
those modules, and resolves them against `AXIOM_RULESPEC_REPO_ROOTS`. Nothing
consumable recorded that program, so the verdict could not be reproduced outside
the harness and a population run could not reuse the identical program without
re-deriving it.

`conformance/compositions/<jur>.yaml` records it. For every covered suite it
captures the exact program the harness composes — the same import-set the CLI
builds, its repo-relative files in the rulespec checkout, the query entity, flat
supplied-input boundaries, record-targeted supplied inputs, relation tuples, and
the engine→input **bridge**, including record targets and numeric transforms.
It is generated from the suites, never hand-authored:

```bash
uv run scripts/generate_conformance_compositions.py be          # write
uv run scripts/generate_conformance_compositions.py --all --check # CI: fail on drift
```

Because the record is derived by the same `rulespec_imports_for_concepts` the
runner uses, the `--check` gate and `tests/test_conformance.py`
(`test_recorded_imports_match_the_cli_runner_derivation`) tie it to the real run
path — it cannot describe a program the harness would not compile.

**Most BE compositions are a single top-level module** (it transitively imports
its own stages); only `be-worker-ssc` spans two (`employee_contributions` +
`work_bonus`, its three outputs). `be-marital-quotient` likewise imports the
single top-level `couple_pit_oracle_pipeline`, but its suite now supplies two
related `Person` records beneath the queried `TaxUnit`: EUROMOD `yem` and
`yemeq_s` bridge to spouse A's worker inputs, spouse B carries zero worker
amounts, and live composition derivation retains both role facts and spouse→tax-unit
relations. Under Max's ruling d1081 (2026-10-08), its covering registration and
committed composition are retracted until a real rerun retains valid Axiom and
EUROMOD values for a registered `tintb_be` output in the same case and actual
comparison; the suite remains available for that rerun. Its published
dispositions predate the repaired rulespec-be#118
pipeline. The historical baseline was 0/3 matches; the current committed report
records 3/3 matches against `tin_s`, which still does not provide the registered
`tintb_be` comparison. Retained disposition metadata describes the earlier
mismatches; a supervised worktree validation is not itself a
disposition-retirement event.

### CLI convenience

`compare euromod axiom --suite <name>` (no `--axiom-program`) already composes
the program from the suite's concepts. When `AXIOM_RULESPEC_ROOT` names a
rulespec checkout — one repo (`…/rulespec-be`) or the workspace holding the
`rulespec-<country>` checkouts — the runner resolves the modules against it, and
the compare command echoes the resolved composition (its modules, files, and
entity) so the run is reproducible. Passing `--axiom-program` still overrides
everything; suites with no record (US / UK-PE lanes) fall through unchanged.

## CI gates

Wired in `.github/workflows/ci.yml`, following the repo's existing gate patterns:

* **Universe drift** — regenerate == committed (no-op clean when the model
  checkout is absent; the committed universe stands alone).
* **Composition drift** — regenerate == committed (derived from the suites, so
  it always bites: a covered suite whose program composition changed must
  refresh `conformance/compositions/<jur>.yaml`).
* **Execution attestation** — every covered policy's report shows a real run
  against the declared oracle with a returned same-case pair for a registered
  output. All historical waiver entries are retired and cannot return or
  bypass the scoreboard's paired-output requirement.
* **Scoreboard freshness** — regenerated scoreboard + detail == committed copies.
* **Ratchets** — no monotonic invariant regressed.
* **Burn-down freshness** — regenerated series == committed.

Every gate has negative tests in `tests/test_conformance.py` proving it can fail.

The scoreboard/detail are derived from the committed comparison reports, so
anything that refreshes a report must regenerate them in the same change or the
freshness gate reds main. Interactive PRs do this by hand; the automated
**affected-rerun** bot does it per matrix leg via
`scripts/commit_refreshed_report.sh` (see `comparisons/README.md` →
*Affected-comparison map + rerun*, and the behavioral tests in
`tests/test_commit_refreshed_report.py`). Both trace back to the
2026-07-14 incident (#282), where four income-tax report refreshes redded main
for every open PR until the scoreboard was regenerated manually.
