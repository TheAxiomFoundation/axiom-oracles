# C1 design — full-schedule tariff conformance

Status: proposed for coordinator adjudication; no build work is authorized by this note.

## Decision summary

C1 will add a new full-schedule comparison lane rather than broaden the five-line `us-tariff-panel` witness in place. The witness remains a small, independently reviewable identity and regression suite. The new lane will consume the Yale Budget Lab legal-date panel as its sole expected-value source, evaluate the 100 generated chapter compositions that constitute the RuleSpec bulk path, compare exact statutory authority components, and classify every mismatch through a compact signature-to-class ledger. `conformant=true` is permitted only when every compared unit either matches or belongs to one reviewed class, no Axiom-attributed open mismatch remains, all extraction/bridge/reconciliation gates pass, and every excluded reference slot has zero live exposure.

The literal Cartesian universe is too large for an initial routinely reproducible certificate run. The best available measured dimensions are about 20,206 rated HTS-10 lines (the Yale/stage-1 schedule count; 2026 statistical revisions may change this slightly), 240 countries, and approximately nine Yale legal-date validity intervals intersecting 2026-02-15 through 2026-08-01. That is about 43,644,960 `(line, country, interval)` cells and at most 87,289,920 endpoint probes. C1 therefore proposes an oracle-defined, Yale-only rate-trajectory stratification, described below. The extraction leg must report the exact full and selected counts; these estimates are not certificate facts.

## Universe and reference extract

### Oracle-defined spine

The supervised extractor will read `/Users/maxghenis/TheAxiomFoundation/_tariff-yale/data/timeseries/rate_timeseries.rds` at the reviewed Yale commit and in its default legal-date mode. It will select the panel's own spine columns (`hts10`, Census `country`, `revision`, `valid_from`, `valid_until`) and the complete upstream `statutory_*` column set. No RuleSpec line list, compiled artifact, B1.6 support file, incidence table, import weight, or engine output may determine whether a reference row exists or what its expected value is.

The rated-line universe is the set of HTS-10 lines present in Yale's panel with a valid statutory rate vector during the window, including zero-rate vectors when Yale retains the line as a rated schedule line. The country universe is the exact Census-country set in Yale's panel. The extractor will fail on missing/non-finite/negative rates, duplicate keys, interval gaps or overlaps, unequal country sets by line, unclassified new `statutory_*` columns, or an unbridged Census country. Provenance will pin the Yale commit, RDS SHA-256, legal-date build invocation, complete schema, full-universe counts, selected-universe counts, country bridge SHA-256, extract SHA-256, and extraction timestamp.

### Window and endpoint clipping

The temporal domain is the closed interval 2026-02-15 through 2026-08-01, matching the encoded B1.6 domain. For each Yale `(line, country, validity interval)` row that intersects the domain, the covered interval is:

`[max(valid_from, 2026-02-15), min(valid_until, 2026-08-01)]`.

Both inclusive endpoints are probes; a one-day clipped interval produces one probe. Intervals wholly outside the window are not certificate units. The extract records original and clipped bounds so the runner cannot silently extend Yale values or the encoded program beyond their domains. Expected Yale values are constant within each Yale validity interval, while probing both ends detects RuleSpec boundaries that fall inside a Yale interval.

The currently visible Yale revision calendar implies about nine intersecting intervals (with boundaries around 2026-02-24, 04-06, 04-23, 04-29, 05-01, 06-08, 07-01, and 07-21), but the extractor—not this note—owns the authoritative count.

### Principled stratification

An exhaustive first run would be about 43.6 million cells / 87.3 million probes, well beyond the requested approximately five-million-cell operating envelope and substantially larger than B1.6 r3. C1 will preserve the complete oracle universe in a manifest but evaluate a deterministic equivalence quotient:

1. For each HTS-10 line, construct each country's **Yale statutory trajectory signature**: the ordered clipped intervals plus the exact vector of every `statutory_*` value at each interval.
2. Partition that line's 240 countries by identical trajectory signature.
3. Select one country per `(line, Yale trajectory signature)` class using a pinned SHA-256 ordering over `(line, signature, Census country)`, not a convenient or manually chosen country.
4. Add a deterministic marginal-coverage repair set, still selected only from Yale spine facts, until every Yale country and every rated line appears at least once. Record the representative-to-covered-country mapping and class cardinality in the extract.
5. Probe both endpoints of every clipped interval for every selected representative.

This is not value-weighting and does not favor high-import, matching, or RuleSpec-covered cells. It retains every distinct expected statutory trajectory for every line; rare positive authority exposures form their own classes automatically. Hash rotation prevents the modal country in every class from always being the representative, and the marginal gate ensures all 240 countries are exercised somewhere. The selection cannot inspect Axiom values, RuleSpec flags, membership tables, or mismatch status.

The expected selected size is hundreds of thousands of line-country trajectories and approximately one to three million interval cells because most countries share a small number of statutory trajectories on a given line. The extractor must publish the measured number before engine execution. If the quotient exceeds five million interval cells, C1 stops for re-adjudication; there will be no second-stage convenience sample. The certificate will disclose both the complete Cartesian universe and the evaluated quotient and will never describe the quotient as literal all-country evaluation.

This stratification is unbiased with respect to reference outcomes and mismatch discovery conditional on the Yale trajectory: every distinct Yale expected behavior survives. It does not prove that Axiom behaves identically for two countries Yale groups together. That limitation is explicit; a later exhaustive shard run can discharge it without changing expected values or disposition semantics.

## Comparison contract

### Bulk program and inputs

The Axiom side is the 100 generated chapter compositions under `us/policies/cbp/us-tariff-schedule/generated/chNN/chNN.yaml`, compiled with absolute source/output paths using the pinned engine at `/Users/maxghenis/TheAxiomFoundation/axiom-rules-engine-pinned/target/release/axiom-rules-engine` and:

`AXIOM_RULESPEC_REPO_ROOTS=/Users/maxghenis/TheAxiomFoundation/_b1wt`.

Compilation and execution receipts pin the RuleSpec commit containing merge `96d5e7c1`, engine binary SHA-256, each source and compiled-artifact SHA-256, absolute paths, environment allowlist, batch sizes, and output hashes. The five-line `us-tariff-duty/composition` remains an independent witness gate; it is not substituted for the bulk compositions.

Each case supplies Yale's HTS-10 line, bridged ISO-2 origin, entry date, and neutral statutory-entry facts. Membership-semantic inputs are produced by `tools/b16_entry_flags.py` from the RuleSpec incidence tables: China §301 lists 1/2/3 and 4A, §232 aluminum and steel, §201 CSPV, §122 unconditional exemption, and §232-covered status, plus the exact beer line-D path. Brazil §301, forced-labor §301, the 2024 China action, and solar remain false where the merged tool has no entry-preparable incidence source. Conditional GN6 utilization, Chapter 98 partial-value shares, transit status, preference claims, and other entry facts are not inferred from Yale statutory rates.

`b16_entry_flags.py` is shared with the implementation in the relevant sense: it is RuleSpec-owned implementation input preparation, derived from RuleSpec incidence tables. That is acceptable only on the **actual/input side**. The flags are analogous to `hts_number` or `country_of_origin`; they must never select, modify, fill, or disposition Yale expected values. The report will preserve each supplied flag so reviewers can audit which implementation path was exercised. A flag-tool or incidence-table defect remains Axiom-attributed unless a reviewed legal-vintage/class receipt proves a defined comparability difference.

### Authority slots

The runner will compare rates, not weighted constructs or effective/utilization-adjusted Yale totals. The proposed exact mapping is:

| Comparison slot | Yale expected side | Bulk Axiom actual side |
|---|---|---|
| Base | `statutory_base_rate` | `mfn_ad_valorem_rate` |
| IEEPA | `statutory_rate_ieepa_recip + statutory_rate_ieepa_fent` | `ieepa_component_rate` |
| §122 | `statutory_rate_s122` | `section_122_component_rate` |
| §201 | `statutory_rate_section_201` | `section_201_component_rate` |
| §232 metals | `statutory_rate_232` | `section_232_aluminum_component_rate + section_232_steel_component_rate` |
| China §301 | `statutory_rate_301` | `china_section_301_component_rate` (list123/list4A membership inputs, including any component behavior supported by the bulk module) |
| Brazil §301 | `statutory_rate_s301br` | `brazil_section_301_component_rate` |
| Forced-labor §301 | `statutory_rate_s301fl` | `forced_labor_section_301_component_rate` |
| §338 | `statutory_rate_s338` | `section_338_component_rate` |
| China §301 content-split | `statutory_rate_301_cs` | no counterpart; excluded only while the live-exposure tripwire is zero |
| Other | `statutory_rate_other` | no counterpart; excluded only while the live-exposure tripwire is zero |
| Statutory total | sum of **all** Yale `statutory_*` columns | sum of the compared Axiom statutory components, cross-checked against `schedule_statutory_stack` after documenting that output's exact membership |

The §232 slot intentionally names its scope difference: Yale's single `statutory_rate_232` is an all-§232-family column, while Axiom currently compares only encoded steel and aluminum. Yale's autos, light trucks and parts, copper, semiconductors, medium/heavy-duty vehicles and buses, and wood/timber programs are not silently treated as metal-component errors. Pharma activates after this certificate window and therefore has zero live window exposure, but remains in the scope disclosure.

The extractor's complete statutory-column allowlist is a hard schema gate. If Yale adds a statutory authority, generation fails until the slot is mapped or explicitly excluded with a zero-exposure tripwire. Stored Yale `base_rate`, `rate_*`, `total_rate`, `total_additional`, import weights, metal shares, and utilization fields are not expected values for this certificate.

All component and total comparisons use absolute tolerance `1e-12`, with no relative tolerance and no rounding before grading. The report separately asserts that the Axiom total equals its component sum and the Yale total equals the extracted statutory-column sum within the same tolerance. Engine errors, missing outputs, duplicate case IDs, or non-finite outputs are unexplained failures, never dispositions.

## Dispositions by class

Dispositions will be signature-grouped, not line-grouped. A mismatch signature consists of authority slot, exact expected/actual delta, relevant supplied-flag vector, Yale revision/interval regime, origin regime, and a compact line-incidence signature. The report retains every member case ID in a sidecar or lossless compressed selector, while `dispositions/<new-suite>.yaml` contains approximately dozens of reviewed class entries. A conservation gate requires every mismatched unit to map to exactly one disposition and forbids stale selectors, overlaps, or wildcard absorption of a new signature.

Expected initial classes, subject to what the run actually reveals, are:

- **Rev-15/current-incidence versus versioned Yale vintage**: per-authority §301 and §232 signatures where the RuleSpec incidence tables encode a later/current list while Yale carries the legal-date revision. Evidence: both Yale revision receipt and the exact HTS note/instrument vintage used by the incidence generator. This class must be bounded by revision and action; it cannot be a generic date-difference bucket.
- **9802 partial-value treatment**: §122 (and any live §301/§232 counterpart) where a boolean membership input cannot express the dutiable value portion. Evidence: the controlling Chapter 98/§122 instrument, the Yale row and scaler behavior, and a flag showing that the Axiom partial-value input was unavailable rather than guessed.
- **GN6 conditional utilization**: §122 civil-aircraft lines for which Yale applies its utilization/eligibility treatment but C1 supplies no claimed-entry fact. Evidence: GN6/note 2(aa) vintage plus the Yale condition column receipt. This is an input-comparability class, not an invitation to import Yale utilization into Axiom.
- **Four entry-preparation gaps deliberately fed false**: Brazil §301, forced-labor §301, 2024 China §301 action, and solar. Each is a separate authority/instrument class with a nonzero-exposure receipt and an Axiom-attributed scope disclosure. They may be explained for `conformant` under the suite's declared comparison semantics, but remain open encoding/input-preparation gaps for closure and certification.
- **Non-metal §232 family scope**: Yale all-§232 positives for autos/light trucks/parts, copper, semiconductors, MHD/buses, and wood/timber with zero Axiom steel+aluminum value. Evidence: Yale authority registry/policy parameters plus the governing instrument and the explicit Axiom output inventory. Families and effective-date regimes remain separate signatures even if rates coincide.
- **§201 vintage/stale proxy**: Yale's continued 14.5% solar safeguard proxy after the staged statutory table ended versus Axiom's grounded zero, including the already-held Yale methodology defect. Evidence: Proclamation 10339 staged table/expiry and Yale source receipt. A distinct genuine Axiom solar-input gap, if live, must not be merged into this upstream-reference class.
- **Yale defect #34 — 9802 §122 sequencing**: only the exact Yale-zero/Axiom-positive partial-value pattern demonstrated by the filed issue and source lines. It remains upstream-attributed and separately countable from the general missing-partial-value-input class.
- **Yale defect #35 — 9031.49.70 phantom GN6**: exact code, applicable dates, and Yale-positive/external-note-absent signature only. It cannot cover other GN6 differences.
- **Column 2 / GN3(b)**: base-rate differences for origins where Yale reads only the HTS column-1 general field while the bulk schedule applies the statutory Column 2 rule. Evidence: Yale parser source and the applicable HTS general note. This held methodology class remains explicitly disclosed.
- **Preference/special-column entry semantics**, if live: claimed-entry facts cannot be inferred merely from country; any Yale column-1-general versus Axiom preference behavior must be separated from Column 2 and backed by the actual supplied preference flags.
- **§122 entry-fact classes**: USMCA/CAFTA free-entry status, in-transit treatment, potash, humanitarian/informational/personal-use, Chapter 98 appropriateness, and §232 partial-value overlap are separate only when the neutral C1 inputs make the two systems not comparable. Each needs the relevant instrument subdivision and a receipt of the exact input default. A broad `missing entry facts` disposition is forbidden.
- **Pure legal-date boundary differences**: narrowly bounded endpoint signatures where Yale and RuleSpec encode different effective dates. Each must cite the instrument and both date encodings; no generic timing disposition.

Totals are dispositioned by the ordered set of component-class signatures that exactly explains the total delta. They do not receive free-standing `total differs` waivers. New rates, deltas, flag vectors, revisions, or authority combinations produce unmatched signatures and fail the zero-unexplained gate until reviewed.

`known_not_comparable` and excluded-with-reason are fail-closed states. For every excluded Yale output column, the report computes live `column_exposure` over the complete extracted full universe and the evaluated quotient. Any nonzero, missing, or non-finite exposure changes the scoreboard status to invalid and blocks `conformant`, following the enforced #452 pattern. The same rule applies if a presently post-window family becomes live after a window change. No exclusion may rely only on a prose assertion that a column is dormant.

Amendment A7 makes generated base disposition a mandatory reference-side
pre-pass. General or column-2 `ad_valorem`/`free` cells retain the full query
surface. `specific`, `compound`, `component`, `conditional`, and `empty` cells
mark base and total `known_not_comparable` with
`non_ad_valorem_base:<disposition>` before shard planning; independent
authority components remain comparable. A component whose generated formula
actually depends on `mfn_ad_valorem_rate` is separately excluded with a formula
receipt. This is never an Axiom-attributed disposition and can never absorb an
engine error. The certificate reports the value-free cell count and quotient
share and names the components-only scope explicitly. Chapters 99a/99b use the
same structural treatment when their deferred-output contract supplies no flat
column-2 rate.

## Cost, caching, and reruns

B1.6 r3 compiled 100/100 chapters with three workers and evaluated 386,202 weighted support rows over eight program intervals; its G5 alone performed 6,179,232 comparisons, and the campaign describes the full run in hours. C1's stratified target of roughly one to three million interval cells and up to twice as many endpoint probes is therefore expected to take hours, potentially an overnight supervised run. The exhaustive 43.6-million-cell universe would likely take days and is not the routine v1 path.

The build will separate immutable stages:

1. **Reference cache** keyed only by Yale commit, RDS hash, extractor version, window, and country-bridge hash. Loading the RDS is itself expensive (the existing extractor documents roughly 200 seconds and very high RSS), so the compact full-universe manifest, selected statutory extract, trajectory-class map, and exposure ledger are content-addressed.
2. **Flag cache** keyed by RuleSpec commit, `b16_entry_flags.py` hash, incidence-table manifest hashes, selected `(HTS-10, ISO-2)` pairs, and window. It contains inputs only and cannot enter the expected-value cache key or payload.
3. **Compile cache** keyed by engine hash, RuleSpec commit, absolute module path, source closure hash, and `AXIOM_RULESPEC_REPO_ROOTS`. All 100 artifact hashes are receipted; a source-closure change invalidates only affected chapters when dependency evidence permits, otherwise all chapters recompile.
4. **Evaluation shards** by chapter and deterministic case batch, keyed by reference-extract hash, flag-cache hash, compiled-artifact hash, engine hash, output schema, and batch boundaries. Atomic writes permit resume after interruption. A rerun never reuses a shard whose full key differs.
5. **Comparison/disposition stage** keyed by immutable evaluation and expected extracts. Disposition edits rerun classification and scoreboard generation without rerunning the engine, while still conserving every unit.

Incremental developer runs may select chapters, signatures, or failed shards, but they are diagnostic only. A certificate refresh requires a complete selected-universe manifest, all 100 chapter receipts (including chapters with no selected rated line, explicitly zero-counted), deterministic replay of at least one nonempty shard per changed artifact, and recomputation of full-universe excluded-column exposure.

## Gates and journal semantics

`ops/C1-LOG.md` will record `P(pass)` for each gate, with a receipt path and measured counts. The build gate set is:

- D0 design adjudicated.
- R1 Yale pin/build/provenance and reviewer-independent extraction.
- R2 full-spine integrity, temporal clipping, complete statutory schema, and bridge closure.
- R3 deterministic stratification, every line/country marginal covered, every trajectory class represented, and measured size within the adjudicated cap.
- A1 absolute-path compilation of all 100 generated chapter programs with pinned engine/environment and deterministic artifact replay.
- A2 flag-tool/input-feed receipts, including explicit false and unavailable entry facts; no implementation-derived data on the expected side.
- C1 per-authority exact comparison and both-side component-total reconciliation.
- C2 lossless signature generation and one-to-one mismatch conservation.
- D1 reviewed class dispositions, exact receipt/vintage evidence, zero unexplained, and zero Axiom-attributed open units under the conformance contract.
- X1 excluded-column and `known_not_comparable` live-exposure tripwires over both full and selected universes.
- W1 five-line witness identity/superset replay and no regression of the existing conformant witness suite.
- N1 negative tests/mutants proving that changed expected values, unclassified statutory columns, dropped countries/lines, stale or overlapping dispositions, a newly live excluded slot, altered flags, and endpoint timing mutations fail closed.
- S1 conformance scoreboard regeneration from the committed full-schedule report with `conformant=true` computed rather than authored.

No gate is marked pass from intention. Until the coordinator approves this design and the build produces receipts, each build gate remains pending.

## Meaning of `conformant=true`

For this lane, `conformant=true` would mean:

- at the pinned Yale and RuleSpec commits and pinned engine binary;
- for the Yale-defined rated schedule, country panel, and legal-date intervals intersecting 2026-02-15 through 2026-08-01;
- on the deterministic Yale-trajectory representative quotient, with every rated line, every country, and every distinct Yale statutory trajectory represented;
- with the declared neutral/unavailable entry facts and RuleSpec-derived membership inputs;
- the generated 100-chapter bulk program's exact statutory authority rates and total have zero unexplained mismatches, zero Axiom-attributed open mismatches under this comparison contract, complete lossless reviewed class dispositions, successful reconciliation, and no live excluded-slot exposure.

It would **not** mean literal evaluation of all roughly 43.6 million line-country-interval cells unless a later exhaustive receipt says so. It would not prove equal Axiom behavior among countries that share a Yale trajectory but were not selected for a particular line. It would not validate Yale's effective/utilization-weighted rates, import-weighted aggregates, collections, AVEs, or economic estimates. It would not infer transaction facts such as partial value, GN6 utilization, preference eligibility/claim, transit, Chapter 98 appropriateness, or free-entry status. It would not assert that Yale is legally correct where a reviewed upstream-reference disposition exists. It would not mean that non-metal §232 or the four false-fed action families are encoded, nor that the program is `closed`; those gaps must remain visible in certificate scope/closure disclosures. It would not cover dates before 2026-02-15 or after 2026-08-01, later Yale revisions, later RuleSpec commits, another engine binary, postal/de-minimis machinery, specific-rate duties not represented as comparable ad-valorem statutory slots, or transaction-level customs valuation.

Accordingly, the certificate label should say **full-schedule bulk-path conformance on a Yale-defined trajectory quotient**, not unqualified exhaustive schedule conformance. The complete-universe manifest and quotient mapping make a later all-cell shard expansion monotone: it can strengthen the claim without changing the oracle, expected values, slot mapping, or disposition bar.
