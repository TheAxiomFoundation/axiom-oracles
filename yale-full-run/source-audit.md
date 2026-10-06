# Source audit for Yale campaign A/B

This is a read-only source audit, not a full-campaign measurement. Paths below are
relative to `yale-full-run/B/rulespec-us/` unless prefixed `oracles:`, which means
`yale-full-run/B/oracles/`. The audit read the required organization rules first.
No RuleSpec, ledger, cache, external checkout, or external service was modified.

## Observed implementation difference

`git diff --numstat 96d5e7c1e6309dc205b7320bbddaae8dd5d410df c62645022a8b2fcb5f9e6afdc2def2c8d68c2baf -- us/policies/cbp/ tools/generate_schedule_compositions.py`
returned no output (exit 0). The tariff chapter compositions and their generator
are unchanged between A and B. The behavior change comes from the input helper:

- A `tools/b16_entry_flags.py:107–108` hardcodes both Brazil/note-52 flags false.
- B `tools/b16_entry_flags.py:115–126,142–144,187–192` derives each flag as the
  complement of its unconditional exemption tables and existing aluminum/steel
  membership. B adds `note50-brazil-exemptions.yaml` and
  `note52-reciprocal-exemptions.yaml` to the helper's table inputs.
- The existing generator consumes these flags at
  `tools/generate_schedule_compositions.py:115–120`. For example, CH79's generated
  Brazil rule consumes the flag at `us/policies/cbp/us-tariff-schedule/generated/ch79/ch79.yaml:3040`;
  note 52 consumes its flag and applies origin/tier/floor logic at `:3197–3207`.
  Scope alone therefore cannot quantify note-52 rate agreement.
- B's `.axiom/toolchain.toml:2–4` pins the August-23 Canada-338 union corpus release,
  replacing A's older commit-based toolchain tuple. That pin is a provenance
  change; it is not itself evidence of engine evaluation or source verification.

The helper treats Rev-15 membership as a codified-state table, not historical
vintages. `tools/generate_incidence_tables.py:25–46` expressly states the
August-3 codified date is after the campaign window, and
`tools/b16_entry_flags.py:34–45` unions all table versions without dates. B keeps
exact ten-digit atoms exact (`tools/b16_entry_flags.py:49–80`); widening those to
eight digits would change the source interpretation rather than repair the flag.

## What the 5,034 figure actually records

The unsigned receipt
`.axiom/encoding-receipts/2026-09-20-note50-note52-incidence-lane.json:494–566`
labels its earlier re-census diagnostic and confounded, explicitly says it did
not rerun the campaign, and records the following. These are numbers read from
that receipt, not newly measured A/B campaign outputs:

| Receipt population | Units | Interpretation retained by receipt v5 |
|---|---:|---|
| Prior Brazil family reproduced | 93,198 | Old published family population |
| Brazil flags now in scope | 93,192 | Input scope change; not a closure count |
| Brazil still out of scope | 6 | HTS10 `9403999020` |
| Brazil opposite direction, total | 5,034 | Yale zero and B input now in scope |
| Exact-ten-digit atom siblings | 120 | Precision join only; statutory authority takes precedence |
| GN6 conditional list | 144 | Conditional-list membership, not proof of exempt entry |
| Pharmaceutical conditional list | 84 | Conditional-list membership, not proof of exempt entry |
| Residual bucket E | 4,686 | Unattributed; earlier non-metal-232 causal claim withdrawn |
| Note-52 opposite direction | 133,444 | Unattributed upper bound; no country-tier engine evaluation |

The receipt withdraws every quantified note-52 causal attribution at `:563–566`.
Do not substitute these numbers for the current comparison. In particular the
120 sibling units cannot all be labeled reference defects: the current ruling
assigns 24 of the historical 120 to statutory Note-50/52 exclusions, leaving 96
reference-defect units (`oracles:reference/us-tariff-schedule/campaign-dispositions.yaml:377–390`).

One input sample was executed locally:

```sh
/Users/maxghenis/TheAxiomFoundation/axiom-oracles/.venv/bin/python yale-full-run/B/rulespec-us/tools/b16_entry_flags.py 9403999000 9403999020 BR
```

Exit 0; output included `s232_steel_derivative_april=true`,
`entry_is_section_232_covered=true`, `entry_is_brazil_301_listed=false`, and
`entry_is_forced_labor_301_listed=false`. The exact table atom and source excerpt
are at `us/policies/usitc/us-tariff-incidence/generated/note16-232-steel.yaml:3386,3449`.
This explains the helper's zero scope on that line. A vintage/input-comparability
explanation for a remaining Yale-positive mismatch is plausible, but requires
the actual Yale interval/revision/source join; this audit does not declare it
proved. Existing vintage selectors apply to `section_232`, not negative Brazil
or note-52 components.

## Remaining source gaps and smallest grounded repairs

Counts must come from the separate current run. The following causes are visible
in source even where the campaign has not yet measured their population.

| Gap | Concrete cause | Smallest repair consistent with the ruling |
|---|---|---|
| Unconsumed copper/other annex and sector-heading exclusions, Notes 50(a)(vi)/52(f) | `tools/b16_entry_flags.py:142–144,164–176` limits coverage to steel/aluminum. `tools/generate_incidence_tables.py:85–122` emits no membership production for the sector-heading limbs. `us/policies/usitc/us-tariff-duty/overlays/section-301/forced-labor-metals-9903-05-90.yaml:10` defines an unused Asset-level rule, while `us/policies/cbp/us-tariff-duty/composition.yaml:688–689` imports only two other section-301 overlays. | Encode grounded per-article incidence for all named sectors/annexes and consume it in both scope flags/compositions. Do not call a rate cell an entry membership rule. Existing ledger `section232-annex-*`/`section232-heading-*` classes remain Axiom-attributed (`oracles:.../campaign-dispositions.yaml:245–288,333–376`). |
| CAFTA-DR Note 52(i) | `.../overlays/section-301/forced-labor-costa-rica-9903-05-33.yaml:36` references `article_described_in_heading_9903_05_95` as an input; no rule defines it and composition imports none of these country overlays. `tools/generate_incidence_tables.py:286–305` records absent GN29(d)(v) scope and duty-free claim implementation. | Encode GN29 scope plus an actual entry claim/eligibility fact and wire the relief. Origin and textile membership alone do not prove relief. The ruling retains the historical 17,404 units as open; do not silently flip neutral campaign claims (`oracles:.../output-semantics-ruling.md:145–158`, ledger `:57–80`). |
| Note 52(j) country-specific lists | UK `.../overlays/section-301/forced-labor-uk-9903-05-81.yaml:36`, EU and other overlays name unconsumed `article_described_*` inputs. `tools/generate_incidence_tables.py:291–305` names thirteen limbs; no corresponding definitions exist. | Encode the thirteen grounded country/article list tests and consume them. Then join residual signatures to the applicable country/list/source; do not assign a causal share from scope flags alone. |
| Prose-qualified articles treated as unconditional exemptions | `tools/b16_entry_flags.py:115–126` includes all a(iii)/c membership; `tools/generate_incidence_tables.py:216–221,325–330` discloses three Brazil line occurrences and seven note-52 line occurrences requiring religious-use or sowing facts. | Add the qualifying entry facts and apply the exemptions only when those facts hold. Under neutral non-exempt panel facts, membership alone must not exempt. Whether these cause a Yale mismatch is unmeasured here. |
| Note 52(k) equivalent rates on non-ad-valorem base lines | The panel floor subtracts `mfn_ad_valorem_rate` (`.../composition.yaml:3638–3645`); `tools/generate_incidence_tables.py:306–315` records both missing AVE branches, including properly claimed Korean column-1 Special. | Supply the statutory duty/customs-value equivalent and relevant claim facts before comparing floor branches. Keep unavailable entry inputs explicit. This is also an input-comparability issue in a components-only panel; no new selector is justified without an exact receipt. |
| Missing Brazil transaction-level relief and both notes' reduced 9802 duty bases | Brazil has only the panel component (`tools/generate_schedule_compositions.py:79–91,115`); note-52 entry relief is present at `.../composition.yaml:3796–3802`, but neither note applies the reduced bases disclosed in `tools/generate_incidence_tables.py:188–208`. | Add Brazil's entry-level exemption rule (including its July-22 transit fact), and encode the four 9802 reduced bases for both notes. These are wider entry-model gaps; neutral non-exempt campaign facts do not by themselves establish them as certificate mismatch units. |

The organization rules require RuleSpec semantic repairs through the supervised
encoder (`axiom-encode encode <corpus citation> --backend codex --apply`), with
repair rounds/compose exceptions as stated there. No semantic fix was attempted
in this audit.

GN6/pharmaceutical utilization shares and Chapter-98 static zeros need separate
treatment. The current ruling fixes statutory non-exempt semantics
(`oracles:.../output-semantics-ruling.md:5–20`) and assigns bounded receipted Yale
proxy behavior to reference classes (`:92–106,124–135`). The bridge holds entry
claims, USMCA, transit, donations and baggage false
(`oracles:axiom_oracles/bridges/manifests/us-tariff-schedule.yaml:49–66`). Thus
missing utilization/proper-claim facts are not a reason to blanket-zero those
panel components. Positive statutory sector exclusions override those
reference labels, as the ruling explicitly requires.

## Honest v2 artifact regeneration requirements

The current campaign is stricter than changing a schema string:

1. `oracles:scripts/us_tariff_schedule_campaign.py:1843–1893` reads the actual
   comparison artifact, hashes it, computes mismatch signatures and enforces
   every preview selector's exact old population before writing a receipt.
   A/B changes can legitimately expire this historical population contract.
2. The v2 receipt records the input hashes, observed population, class census and
   sidecar hash (`:1962–1981`). `report` validates that handoff (`:2007`). Neither
   old v1 artifacts nor an override-based diagnostic receipt are substitutes.
3. Current `computed_conformant` (`:1992–1993`) is only the S1 condition
   `unexplained == 0 and engine_errors == 0`. Open classes are listed separately
   (`:2021–2046`). Max's goal additionally requires **zero Axiom-attributed-open
   units**. Report both conditions; do not use S1 alone as proof of success.
4. To publish honestly after encoding fixes, rerun all required stages against
   the desired bound RuleSpec/helper/engine/Yale inputs. Rebuild the legal-scope
   preview receipts and selector population contracts from the newly measured
   signatures through their producer, with source authority and exact joins.
   Preserve unexplained residuals and open statutory gaps. Then run classify,
   report and the certificate-generation/check path and commit the bound v2
   artifacts together. This audit did not edit the ledger or invent selectors.

## Commands and observed output

The audit ran `cat /Users/maxghenis/TheAxiomFoundation/CLAUDE.md` first (exit 0),
then read the previous lane's `yale-1383-run/RESULT.md` (exit 0). Source reads used:

```sh
git -C /Users/maxghenis/TheAxiomFoundation/rulespec-us show --stat --oneline c62645022a8b2fcb5f9e6afdc2def2c8d68c2baf
git -C /Users/maxghenis/TheAxiomFoundation/rulespec-us diff --stat 96d5e7c1e6309dc205b7320bbddaae8dd5d410df c62645022a8b2fcb5f9e6afdc2def2c8d68c2baf
git -C /Users/maxghenis/TheAxiomFoundation/rulespec-us diff --numstat 96d5e7c1e6309dc205b7320bbddaae8dd5d410df c62645022a8b2fcb5f9e6afdc2def2c8d68c2baf -- us/policies/cbp/ tools/generate_schedule_compositions.py
git -C /Users/maxghenis/TheAxiomFoundation/rulespec-us show c62645022a8b2fcb5f9e6afdc2def2c8d68c2baf:tools/b16_entry_flags.py
git -C /Users/maxghenis/TheAxiomFoundation/rulespec-us show c62645022a8b2fcb5f9e6afdc2def2c8d68c2baf:.axiom/encoding-receipts/2026-09-20-note50-note52-incidence-lane.json
git -C /Users/maxghenis/TheAxiomFoundation/axiom-oracles show origin/main:reference/us-tariff-schedule/output-semantics-ruling.md
git -C /Users/maxghenis/TheAxiomFoundation/axiom-oracles show origin/main:reference/us-tariff-schedule/campaign-dispositions.yaml
git -C /Users/maxghenis/TheAxiomFoundation/axiom-oracles show origin/main:scripts/us_tariff_schedule_campaign.py
rg -n --glob '*.yaml' --glob '!*.test.yaml' -- '^- name: article_described|^  - name: article_described' yale-full-run/B/rulespec-us/us/policies
rg -n 'article_described|forced-labor-metals|section-301/' yale-full-run/B/rulespec-us/us/policies/cbp/us-tariff-duty/composition.yaml
```

Observed outputs: candidate tip adds its 644-line receipt; whole A/B diff is 34
files, 88,447 insertions, 62,582 deletions; CBP/generator semantic diff is empty;
the definition search has no matches (exit 1); composition search reports only
the Brazil and presidential-action overlay imports at lines 688–689 (exit 0).
The file/line extracts cited above were read using `git show ... | nl -ba | sed`
and, once checkouts existed, `nl -ba ... | sed` / scoped `rg -n` reads.

One discovery guess, `git show ...:tools/generate_us_tariff_schedule.py`, failed
with `fatal: path ... does not exist`; the actual generator read afterward was
`tools/generate_schedule_compositions.py`. The live helper sample above passed.
No test suite or engine evaluation was run by this source-audit subtask; those
belong to the parent campaign run. No API call, push, PR, comment or merge ran.

## Follow-up: exact current producer chain and continuation

The following commands are a **source-derived continuation recipe**, not commands
executed by this audit. They assume the assigned workspace setup and retained
stage receipts. Use the corresponding A paths for baseline.

```sh
RUN=/Users/maxghenis/.subfleet/worktrees/20260923-140123-yale-campaign-full-v2/yale-full-run
PY=/Users/maxghenis/TheAxiomFoundation/axiom-oracles/.venv/bin/python
ENGINE=/Users/maxghenis/TheAxiomFoundation/_tariff-parity/axiom-rules-engine/target/release/axiom-rules-engine
export AXIOM_TARIFF_C1_CACHE="$RUN/B/cache"
export RULESPEC_US_CHECKOUT="$RUN/B/rulespec-us"
export AXIOM_RULESPEC_REPO_ROOTS="$RUN/B"
cd "$RUN/B/oracles"
"$PY" scripts/us_tariff_schedule_campaign.py evaluate --rulespec-root "$RUN/B/rulespec-us" --engine-binary "$ENGINE" --workers 3 --resume
"$PY" scripts/us_tariff_schedule_campaign.py compare
"$PY" scripts/us_tariff_schedule_campaign.py classify
"$PY" scripts/us_tariff_schedule_campaign.py report
"$PY" scripts/us_tariff_schedule_campaign.py witness-replay
"$PY" scripts/certify.py --program us/tariff-duty
"$PY" scripts/certify.py --program us/tariff-duty --check
```

Run stages sequentially and stop promotion at a failed stage. In particular, a
failed classify leaves the old classification file in place; running certificate
generation against the unchanged old detail would not certify the new run.
The recipe is not a claim that unchanged current code can reach its last stage.

Preserve the existing input-contract receipt when resuming: campaign `:2143`
adds stage runtime to its bytes, and `_shard_key` at `:730–734` hashes the whole
receipt. Re-running that stage changes all shard keys. The evaluator preserves
old manifest entries (`:825–843`); the comparator rejects duplicate chapters
(`:852–858`) and requires the full declared chapter set (`:903–907`). A retained
set of 100 hash-valid shards and the corresponding existing contract is the
correct continuation point.

Upstream assets and their actual producer paths:

| Asset | Current producer and prerequisites |
|---|---|
| `selected-intervals.csv.gz`, `quotient-receipt.json`, `full-exposure.json`, `trajectory-class-map.csv.gz`, `integrity-receipt.json`, `provenance.json` | `Rscript scripts/extract_us_tariff_schedule.R <oracles-root> <yale-root>`; extractor `:4–20` reads Yale `data/timeseries/rate_timeseries.rds`; `:46–51` needs the panel Census/ISO bridge and schedule additions; `:59–80` reads `origin-regimes.json`; `:90–106` writes the artifacts. This extraction is not one of the Python campaign's stage choices. For the pinned comparison these committed artifacts can be reused; regeneration must reproduce their pinned source/hash inputs. |
| Routing and compiled input contract | Python campaign `prepass` and `input-contract`; input-contract compiles 100 local chapter modules and receipts the helper at `:295–358`. |
| Projection receipt | Python campaign `projection`; dispatch at `:2111–2117`. |
| Full evaluation manifest and external shard bodies | Python campaign `evaluate`; `:817–849`. Each shard path/hash must resolve; comparison accepts only the complete chapter set. |
| Preview line-set/population receipt | `python scripts/build_us_tariff_preview_disposition_receipt.py --yale-root <pinned-yale-root>`; add `--check` for byte verification. Its actual inputs are the five `preview-1311` receipts/compressed mismatch artifacts and selected intervals (`:44–66`), plus pinned Yale source joins (`:539–542`). This is a historical-preview producer, not a general current-run classifier. |
| Detail report | `compare`, then `classify`, then `report`; report additionally reads quotient, routing and full exposure (`:1996–2008`). |
| Witness replay | `witness-replay` reads `dashboard/public/data/axiom-yale-us-tariff-panel.json`, invokes `scripts/run_comparison.py us-tariff-panel`, checks the same raw comparison surface, restores the original dashboard bytes, and writes `witness-replay-execute-receipt.json` (`:2067–2094`). It does not write the schedule report or directly regenerate the certificate's executable receipt. |
| Program certificate | `scripts/certify.py --program us/tariff-duty`; input is the schedule detail plus `conformance/exercise-census.json`, `conformance/closure/us-tariff-duty.yaml` and `conformance/executable/us-tariff-witness.json` (`certify.py:67,184–210,2167–2192,2476–2481`). Output is `certificates/us-tariff-duty.json` (`:2724–2725,2790–2793`). |

The certificate independently derives the stronger requested conformance
condition. `scripts/certify.py:464` rederives S1, `:489–539` reconciles and sums
open classes against the class census/scope, and `:540` requires S1, zero open
units and no report defects. `:2384` uses that clean reference leg for the
conformant premise. Its final `certified=yes` additionally needs exercised,
closed and executable computed premises and no blockers (`:2617–2629`). An
honestly regenerated certificate can therefore still be `certified=no`; the
task's zero-unexplained/zero-open goal does not by itself establish all four
premises.

Current fresh-artifact blockers visible in source:

1. The preview producer hardcodes the historical compressed-artifact hashes
   (`build_us_tariff_preview_disposition_receipt.py:60–66`), each selector's
   expected unit count (`:69–88`) and the 244,188 open-unit preview census
   (`:118–119`). It enforces these at `:747–769`. Its CLI has no current-comparison
   input option (`:496–505`). Rerunning it unchanged cannot accommodate B's
   closed metal exclusions. A grounded new population receipt and deliberate
   producer/contract update are required; merely rewriting its counts would
   not supply the missing legal-scope proof.
2. The campaign also pins the preview input hashes and source producer bytes
   (`campaign.py:55–71,1040–1085`) and checks all selector unit/signature counts
   and signature-population digests (`:1222–1250`). The actual mismatch must
   remain reported if those fail. No bootstrap option bypasses these checks in
   the campaign classify/report CLI.
3. The current executable producer is pinned to A. In
   `scripts/tariff_executable_reproduction.py:49`, the reviewed ref is
   `96d5e7c1...`; `:394–398` explicitly rejects any other ref. A supported command
   for the current A artifact is
   `python scripts/tariff_executable_reproduction.py --rulespec-root <A-rulespec-root> --rulespec-ref 96d5e7c1e6309dc205b7320bbddaae8dd5d410df --engine-binary <engine>`
   (add `--check` to verify/replay). Passing B does not rebind it. The producer
   explicitly retains `executable=false` for incomplete promised-output
   coverage (`:93–115,635–648`); the schedule campaign alone does not update that
   producer contract.
4. Closure has a separate pinned-source contract. Its supported command is
   `python scripts/us_tariff_closure.py --generate --corpus-root <corpus-repo> --corpus-ref bef19f24206a9de4ef29d9ba2b5924f3cc6a00c6 --rulespec-root <A-rulespec-root> --rulespec-ref 96d5e7c1e6309dc205b7320bbddaae8dd5d410df --engine-binary <engine>`;
   replace `--generate` with `--check` to reproduce and verify. The artifact,
   refs and scope counts are pinned at `:44–66`; validation requires its exact
   expected RuleSpec facts at `:1560–1564`. B adds incidence modules, so passing
   its ref without reviewing/updating these producer expectations is not a
   supported rebind. Both closure/executable must agree on the chosen RuleSpec
   commit and program set (`certify.py:2520–2594`).

The current `scripts/exercise_census.py` supports generation and `--check`
(`:751–754`) for `conformance/exercise-census.json`; it is an additional
certificate evidence producer, not a Python schedule campaign stage. The
schedule bridge's committed exercise receipt and current traces also need
honest rebinding when the evaluated input surface changes. This audit did not
regenerate any of these independent producers.

## Follow-up: corpus pin versus engine compilation

`git -C /Users/maxghenis/TheAxiomFoundation/_tariff-parity/axiom-rules-engine rev-parse HEAD`
returned `ffd8213271947b0189a9dd61a055c1e0e78908a0`. A diff against HEAD for
`src/main.rs`, `src/compile.rs`, and `src/rulespec.rs` returned no changed paths.
These source observations explain why compilation does not require a located
copy of the candidate's August-23 corpus release:

- CLI `src/main.rs:39–66` dispatches `compile --program ... --output ...` to
  `compile_program_file_to_json`.
- `src/compile.rs:750–757` calls `CompiledProgramArtifact::from_rulespec_file`;
  `:170–182` loads the local YAML path and calls the RuleSpec file loader.
- `src/rulespec.rs:760–802` reads local module text, validates metadata shape,
  resolves local imports recursively and merges them. The module metadata is
  documented as descriptive/inert (`:206–210`). Its source SHA validation only
  checks 64 hexadecimal characters (`:230–248`); it does not obtain corpus text
  and compare its content hash.
- A scoped source search for `toolchain.toml`, `axiom_corpus_release`,
  `corpus_release`, `reqwest`, or HTTP URLs found only two schema identifier URLs
  in `src/schema.rs`, and no release resolver or network client in `src/`.

Thus the observed compile success verifies executable local module/import/input
structure under this binary. It does **not** verify that B's corpus release is
locally installed, remotely reachable, or hash-correct. The `.axiom/toolchain.toml`
release tuple is not consumed by this compile path. This is narrower than a
claim about separate encoder/source-validation tooling. The recorded source
checkout and binary hash also do not establish that the binary was built from
that source; the executable receipt itself limits its identity claim to the
tested binary hash (`tariff_executable_reproduction.py:121–145`).

Follow-up commands actually run were read-only `git ls-files`, scoped `rg -n`,
`nl -ba ... | sed -n ...`, the engine `git rev-parse` and `git diff --name-only`
above. Two discovery guesses did not exist: `scripts/build_program_certificates.py`
and engine `src/program.rs`; their grouped `rg` calls exited 2. Correct producer
paths were then read as documented above. No regeneration, check command,
remote corpus lookup, API call or engine execution ran in this follow-up.
