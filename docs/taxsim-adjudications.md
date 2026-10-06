# TAXSIM emulator adjudications

The registry in `adjudications/taxsim-emulator.yaml` records reviewed questions
separately from the numerical mismatch ledger. Its schema is
`axiom_oracles.adjudications.v1`. An `evidence_ready` record may support a
bound explanation; an issue title, a census classification, an engine output,
or an unverified source link cannot.

## Records and proof atoms

Every record has `id`, `question`, `jurisdiction` (US or a USPS code),
`law_years`, `engines`, `verdict`, `attribution`, `status`, `issues`,
`proof_atoms`, and `notes`. Unknown years are an empty list and cannot be
evidence ready. The supported verdicts are `taxsim_wrong`,
`policyengine_wrong`, `both_wrong`, `convention`, `input_ambiguity`, and `open`.
Attributions are respectively `taxsim`, `policyengine`, `two_sided`,
`convention`, `input`, and an explicitly reviewed attribution for open cases.
Statuses are `evidence_ready`, `pending_evidence`, and `open`.

The validator reopens and verifies every atom, including atoms on pending
and open records. Pending status permits incomplete support for a verdict;
it never permits a broken hash or fabricated quotation. Non-open verdicts
need at least one verified atom. Readiness requires the appropriate support:
an own-engine error acknowledgment or applicable legal evidence for an engine
error, and a maintainer or official-document statement establishing a
convention for `convention` or `input_ambiguity`. Both-wrong needs support
for both engines. Verbatim text establishes what a source says; reviewers
remain responsible for whether that text supports the question and scope.

| Atom kind | Required evidence |
| --- | --- |
| `corpus_quote` | Repository, full commit, tracked JSONL path and blob SHA-256; exact citation, provision heading, verbatim body excerpt, applies-to description and law years. |
| `corpus_absence` | Same pinned corpus identity and citation; SHA-256 of the entire provision body and a nonempty list of absent terms. Every term is checked case-insensitively against the complete body. |
| `year_change` | `before` and `after` corpus quotes for different law years; `changed_text` exactly equals the computed unified diff of the complete provision bodies. |
| `document_quote` | Official HTTPS URL, retrieval date, repository snapshot path and SHA-256, and a verbatim excerpt. `establishes_convention: true` records the reviewer's explicit support decision. |
| `maintainer_statement` | Engine, GitHub comment URL, author, date, at most 60 quoted words, snapshot path and SHA-256. Snapshot fields are exactly `url`, `author`, `createdAt`, `body`; identity and date must match. The comment must belong to a listed issue (GitHub issue/PR URL aliases are equivalent). `acknowledges_error` and `establishes_convention` are reviewed assertions, never inferred from keywords. |

No atom kind accepts engine outputs. Snapshots preserve only the needed
comments, not entire issues. A PR body is not a comment snapshot. A generic
“corrected” reply is not automatically an engine-error admission: it can
refer to a TaxAct input, a hand calculation, or the question itself.

Maintainers are configured in `adjudications/maintainers.yaml`: TAXSIM has
`feenberg`; PolicyEngine has `DTrim99`, `MaxGhenis`, `PavelMakarchuk`,
`anth-volk`, `eqberkovich`, `noman404`, and `sgerson2`. The PolicyEngine list
uses authors of merged pe-taxsim PRs; the configuration records merged-PR
provenance. Membership authenticates a statement's engine ownership, not
the legal correctness of everything the author writes.

## Evidence rules mapped to checks

| Evidence rule | Enforcement |
| --- | --- |
| Mechanically extract operative text | `git show <commit>:<path>` reads a tracked corpus blob, checks its SHA-256, resolves the exact citation, and tests literal excerpt containment. Official document excerpts must occur in a hashed snapshot. |
| Negative and year-change claims | Complete provision body digest plus absence tests; or independently verified before/after sources plus a recomputed full-body diff. A current-law capture date does not establish a historical law year. |
| Outputs are hypotheses | Closed atom vocabulary has no output kind. Report arithmetic selects and binds affected observations; it cannot decide who is right. |
| External test expectations | Integrity tests use temporary pinned source fixtures and independent snapshot text. Migration tests explicitly assert the change in coverage, without promoting report amounts to legal expectations. |
| Verify scope | Provision heading equality, applies-to text, explicit year metadata, record jurisdiction/year/attribution, and matching selected ledger rows. The meaning of applies-to text and acknowledgment flags still requires human review. |
| Re-read after drafting | Every check reloads each snapshot and immutable Git blob. CI checks a sparse corpus checkout at the pinned commit before disposition application and dashboard-note export. |

The initial corpus pin is
`f1916d73b568616cbd0b4c3c26a92796835188d9`, verified as an ancestor of
axiom-corpus `origin/main`. Its needed path is
`data/corpus/provisions/us/statute/2026-07-13-recovery-r2026-07-15-self-contained-r2026-07-17-dedup.jsonl`.
The §1411 provision has heading “Imposition of tax”, source date
2026-07-13, and publication `Online@119-100`. Those fields do not establish
the provision's text in 2021–2025. Its excerpts are verified, but the NIIT
adjudication remains pending until historical applicability is proved.

## Adding or revising a record

1. Read the issue and all comments, including later withdrawals and corrections.
   Identify the precise question and actual years; control years and payment
   years do not automatically become affected law years.
2. Extract only admissible proof. Capture the necessary comment fields or
   official document text, calculate the byte digest, and select a verbatim
   excerpt. For corpus evidence discover tracked paths with `axiom-locate
   corpus-file` or `git ls-files`; pin a mainline commit and hash its Git blob.
3. Verify headings, applicability, and negative/year-change requirements.
   Explain remaining gaps in `notes`. Do not turn an allegation into a
   verdict just because the census proposed a disposition.
4. Update the curated import decisions and regenerate with
   `scripts/import_taxsim_adjudications.py --census <census-directory>`.
   Special migrated evidence is retained in the generator's curated source.
   The external census is read only and is not required by CI.
5. Set `AXIOM_CORPUS_ROOT` to the pinned checkout and run
   `uv run scripts/check_adjudications.py --check`. Re-read the cited text
   after drafting; inspect what it actually proves before marking ready.
6. Reference the ready ID from a ledger entry, regenerate through
   `scripts/build_taxsim_emulator_dispositions.py`, bind it, apply the
   dispositions, and regenerate `scripts/export_taxsim_dashboard_notes.py`.

## PR4 migration

AddMed (`pe-taxsim-1225`), rebate timing (`pe-taxsim-1068`, also citing #716),
and the isolated Louisiana omission (`pe-taxsim-1222`) retain explained
coverage through verified maintainer statements. The NIIT S-corp record
(`pe-taxsim-1053`) contains the two NBER input descriptions and the pinned
§1411 quotations, but remains pending for historical applicability.
The state-zero probe (`pe-taxsim-1249`) remains open because the reviewed
merged PR has no qualifying maintainer comment; its only issue comment is
from `vercel[bot]`.

| Year | NIIT rows moved to unexplained | Explained after migration | Unexplained after migration |
| --- | ---: | ---: | ---: |
| 2021 | 1,511 | 15,411 | 39,189 |
| 2022 | 1,330 | 15,593 | 31,555 |
| 2023 | 1,491 | 4,893 | 34,208 |
| 2024 | 1,499 | 2,934 | 31,734 |
| 2025 | 1,391 | 2,691 | 31,933 |
| Probe | 1 | 0 | 2 |

This removes 7,223 comparison rows from explained coverage. Raw outputs,
match counts, population membership and engine bindings are preserved.
Unexplained entries retain numerical observations with their limited scope.

## Dashboard export

`reports/taxsim-emulator/dashboard-notes.json` is generated deterministically
by `scripts/export_taxsim_dashboard_notes.py` and checked with `--check`.
For each state/year it includes ready records, neutral descriptions,
verdicts, attribution, issue links, and bound explaining entries with counts
computed from complete reports. Counts are comparison mismatch rows, not
unique households. A ready but unbound record has zero affected rows and no
ledger entries; it claims no benchmark coverage. Pending/open records cannot
become known-difference explanations. The export does not edit pe-taxsim's
`STATE_TAX_NOTES`; that consumer belongs to the separate step-6 PR.

## Import summary

All 485 rule-level/convention candidates were reviewed, including the 111
with a proposed non-unexplained disposition. Keeping the other questions
as open records makes the candidate review auditable. The source census is
a discovery inventory; it supplies no evidentiary weight. TaxAct-only claims
remain open because the verdict vocabulary concerns TAXSIM and PolicyEngine.

<!-- BEGIN IMPORT SUMMARY -->

Reviewed **485 candidate issues and 1,052 comments**. All **111** proposed non-unexplained census candidates are retained. The registry has **490 records**, including jurisdiction splits and the separate state-zero probe; **239 are evidence_ready**.

| Dimension | Value | Records |
|---|---|---:|
| status | `evidence_ready` | 239 |
| status | `open` | 165 |
| status | `pending_evidence` | 86 |
| verdict | `convention` | 81 |
| verdict | `input_ambiguity` | 33 |
| verdict | `open` | 165 |
| verdict | `policyengine_wrong` | 157 |
| verdict | `taxsim_wrong` | 54 |
| attribution | `convention` | 81 |
| attribution | `input` | 33 |
| attribution | `policyengine` | 157 |
| attribution | `taxsim` | 54 |
| attribution | `two_sided` | 165 |
| jurisdiction | `AK` | 1 |
| jurisdiction | `AL` | 5 |
| jurisdiction | `AR` | 16 |
| jurisdiction | `AZ` | 12 |
| jurisdiction | `CA` | 15 |
| jurisdiction | `CO` | 16 |
| jurisdiction | `CT` | 10 |
| jurisdiction | `DC` | 13 |
| jurisdiction | `DE` | 16 |
| jurisdiction | `GA` | 9 |
| jurisdiction | `HI` | 7 |
| jurisdiction | `IA` | 14 |
| jurisdiction | `ID` | 5 |
| jurisdiction | `IL` | 4 |
| jurisdiction | `IN` | 1 |
| jurisdiction | `KS` | 6 |
| jurisdiction | `KY` | 8 |
| jurisdiction | `LA` | 4 |
| jurisdiction | `MA` | 8 |
| jurisdiction | `MD` | 20 |
| jurisdiction | `ME` | 14 |
| jurisdiction | `MI` | 13 |
| jurisdiction | `MN` | 13 |
| jurisdiction | `MO` | 8 |
| jurisdiction | `MS` | 8 |
| jurisdiction | `MT` | 16 |
| jurisdiction | `ND` | 2 |
| jurisdiction | `NE` | 12 |
| jurisdiction | `NJ` | 22 |
| jurisdiction | `NM` | 17 |
| jurisdiction | `NY` | 10 |
| jurisdiction | `OH` | 7 |
| jurisdiction | `OK` | 20 |
| jurisdiction | `OR` | 6 |
| jurisdiction | `PA` | 6 |
| jurisdiction | `RI` | 3 |
| jurisdiction | `SC` | 8 |
| jurisdiction | `US` | 61 |
| jurisdiction | `UT` | 4 |
| jurisdiction | `VA` | 13 |
| jurisdiction | `VT` | 14 |
| jurisdiction | `WA` | 12 |
| jurisdiction | `WI` | 7 |
| jurisdiction | `WV` | 4 |

<!-- END IMPORT SUMMARY -->

## Evidence-ready records and atoms

The following generated inventory names every ready record and its atoms.
The registry carries the exact quotes, dates, authors and snapshot hashes.
All initially ready records qualify through maintainer statements. Their
readiness records an authenticated acknowledgment or convention, rather than
an independent historical-law determination. The imported corpus quotations
remain on the pending NIIT record.

<!-- BEGIN READY RECORDS -->

| Record | Scope | Verdict | Verified atoms |
|---|---|---|---|
| `pe-taxsim-60` | NM 2021 | `convention` | [maintainer_statement (PavelMakarchuk, 2024-11-01)](https://github.com/PolicyEngine/policyengine-taxsim/issues/60#issuecomment-2452057466) |
| `pe-taxsim-99` | IL 2023 | `convention` | [maintainer_statement (PavelMakarchuk, 2024-11-14)](https://github.com/PolicyEngine/policyengine-taxsim/issues/99#issuecomment-2475344297) |
| `pe-taxsim-100` | CA 2023 | `convention` | [maintainer_statement (PavelMakarchuk, 2025-04-29)](https://github.com/PolicyEngine/policyengine-taxsim/issues/100#issuecomment-2839245676) |
| `pe-taxsim-114` | DE 2022 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2024-11-21)](https://github.com/PolicyEngine/policyengine-taxsim/issues/114#issuecomment-2489965401) |
| `pe-taxsim-151` | OK 2023 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-03-06)](https://github.com/PolicyEngine/policyengine-taxsim/issues/151#issuecomment-2703653794) |
| `pe-taxsim-195` | VT 2022 | `convention` | [maintainer_statement (PavelMakarchuk, 2025-01-20)](https://github.com/PolicyEngine/policyengine-taxsim/issues/195#issuecomment-2603360795) |
| `pe-taxsim-202` | SC 2021 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-02-25)](https://github.com/PolicyEngine/policyengine-taxsim/issues/202#issuecomment-2682074402) |
| `pe-taxsim-216` | MT 2023 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-02-11)](https://github.com/PolicyEngine/policyengine-taxsim/issues/216#issuecomment-2651280052) |
| `pe-taxsim-225` | AL 2023 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-03-06)](https://github.com/PolicyEngine/policyengine-taxsim/issues/225#issuecomment-2703784107) |
| `pe-taxsim-249` | LA 2021 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-02-28)](https://github.com/PolicyEngine/policyengine-taxsim/issues/249#issuecomment-2690753361) |
| `pe-taxsim-253` | NY 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-04-28)](https://github.com/PolicyEngine/policyengine-taxsim/issues/253#issuecomment-2836691661) |
| `pe-taxsim-257` | OK 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-04-08)](https://github.com/PolicyEngine/policyengine-taxsim/issues/257#issuecomment-2787634082) |
| `pe-taxsim-260` | ID 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-03-17)](https://github.com/PolicyEngine/policyengine-taxsim/issues/260#issuecomment-2731097196) |
| `pe-taxsim-293` | DE 2023 | `convention` | [maintainer_statement (feenberg, 2025-04-02)](https://github.com/PolicyEngine/policyengine-taxsim/issues/293#issuecomment-2773741969) |
| `pe-taxsim-307` | IA 2021 | `convention` | [maintainer_statement (PavelMakarchuk, 2026-07-02)](https://github.com/PolicyEngine/policyengine-taxsim/issues/307#issuecomment-4862314288) |
| `pe-taxsim-309` | VT 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-09-03)](https://github.com/PolicyEngine/policyengine-taxsim/issues/309#issuecomment-3251154817) |
| `pe-taxsim-310` | SC 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-09-05)](https://github.com/PolicyEngine/policyengine-taxsim/issues/310#issuecomment-3259440295) |
| `pe-taxsim-323` | CT 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-06-05)](https://github.com/PolicyEngine/policyengine-taxsim/issues/323#issuecomment-2946309098) |
| `pe-taxsim-346` | AL 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-07-16)](https://github.com/PolicyEngine/policyengine-taxsim/issues/346#issuecomment-3078741667) |
| `pe-taxsim-347` | NE 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-06-30)](https://github.com/PolicyEngine/policyengine-taxsim/issues/347#issuecomment-3019392918) |
| `pe-taxsim-352` | RI 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-06-30)](https://github.com/PolicyEngine/policyengine-taxsim/issues/352#issuecomment-3019082076) |
| `pe-taxsim-353` | UT 2024 | `input_ambiguity` | [maintainer_statement (feenberg, 2025-07-22)](https://github.com/PolicyEngine/policyengine-taxsim/issues/353#issuecomment-3104637574) |
| `pe-taxsim-354` | MT 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-06-24)](https://github.com/PolicyEngine/policyengine-taxsim/issues/354#issuecomment-2998651607) |
| `pe-taxsim-358` | CA 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-06-30)](https://github.com/PolicyEngine/policyengine-taxsim/issues/358#issuecomment-3018510993) |
| `pe-taxsim-360` | MS 2024 | `convention` | [maintainer_statement (feenberg, 2025-06-30)](https://github.com/PolicyEngine/policyengine-taxsim/issues/360#issuecomment-3020139522) |
| `pe-taxsim-364` | DC 2024 | `convention` | [maintainer_statement (PavelMakarchuk, 2025-06-30)](https://github.com/PolicyEngine/policyengine-taxsim/issues/364#issuecomment-3018394972) |
| `pe-taxsim-366` | CO 2024 | `convention` | [maintainer_statement (PavelMakarchuk, 2025-07-01)](https://github.com/PolicyEngine/policyengine-taxsim/issues/366#issuecomment-3023819364) |
| `pe-taxsim-384` | US 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-07-05)](https://github.com/PolicyEngine/policyengine-taxsim/issues/384#issuecomment-4887283378) |
| `pe-taxsim-395` | NM 2024 | `convention` | [maintainer_statement (feenberg, 2025-08-06)](https://github.com/PolicyEngine/policyengine-taxsim/issues/395#issuecomment-3159677342) |
| `pe-taxsim-409` | NM 2021 | `convention` | [maintainer_statement (PavelMakarchuk, 2025-08-21)](https://github.com/PolicyEngine/policyengine-taxsim/issues/409#issuecomment-3211623707) |
| `pe-taxsim-417` | US 2021 | `input_ambiguity` | [maintainer_statement (feenberg, 2025-08-21)](https://github.com/PolicyEngine/policyengine-taxsim/issues/417#issuecomment-3212054507) |
| `pe-taxsim-419` | OK 2024 | `taxsim_wrong` | [maintainer_statement (feenberg, 2025-08-22)](https://github.com/PolicyEngine/policyengine-taxsim/issues/419#issuecomment-3214610360) |
| `pe-taxsim-426` | MA 2024 | `convention` | [maintainer_statement (PavelMakarchuk, 2025-09-16)](https://github.com/PolicyEngine/policyengine-taxsim/issues/426#issuecomment-3300130275) |
| `pe-taxsim-435` | US 2021 | `taxsim_wrong` | [maintainer_statement (feenberg, 2025-08-27)](https://github.com/PolicyEngine/policyengine-taxsim/issues/435#issuecomment-3229364922) |
| `pe-taxsim-473` | AZ 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-12-15)](https://github.com/PolicyEngine/policyengine-taxsim/issues/473#issuecomment-3656398393) |
| `pe-taxsim-490` | MI 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-09-09)](https://github.com/PolicyEngine/policyengine-taxsim/issues/490#issuecomment-3272595657) |
| `pe-taxsim-511` | NM 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-09-17)](https://github.com/PolicyEngine/policyengine-taxsim/issues/511#issuecomment-3304081962) |
| `pe-taxsim-512` | MT 2021 | `convention` | [maintainer_statement (feenberg, 2025-09-19)](https://github.com/PolicyEngine/policyengine-taxsim/issues/512#issuecomment-3312190048) |
| `pe-taxsim-529` | ID 2020 | `convention` | [maintainer_statement (PavelMakarchuk, 2025-09-27)](https://github.com/PolicyEngine/policyengine-taxsim/issues/529#issuecomment-3341964127) |
| `pe-taxsim-538` | US 2024 | `taxsim_wrong` | [maintainer_statement (feenberg, 2025-09-27)](https://github.com/PolicyEngine/policyengine-taxsim/issues/538#issuecomment-3341865828) |
| `pe-taxsim-560` | OK 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-12-14)](https://github.com/PolicyEngine/policyengine-taxsim/issues/560#issuecomment-3652321942) |
| `pe-taxsim-567` | KS 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-10-20)](https://github.com/PolicyEngine/policyengine-taxsim/issues/567#issuecomment-3421106616) |
| `pe-taxsim-568` | ME 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-12-15)](https://github.com/PolicyEngine/policyengine-taxsim/issues/568#issuecomment-3656294319) |
| `pe-taxsim-576` | HI 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-11-04)](https://github.com/PolicyEngine/policyengine-taxsim/issues/576#issuecomment-3486055443) |
| `pe-taxsim-584` | PA 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-10-13)](https://github.com/PolicyEngine/policyengine-taxsim/issues/584#issuecomment-3399297525) |
| `pe-taxsim-585` | IA 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-12-14)](https://github.com/PolicyEngine/policyengine-taxsim/issues/585#issuecomment-3652377905) |
| `pe-taxsim-586` | HI 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-11-11)](https://github.com/PolicyEngine/policyengine-taxsim/issues/586#issuecomment-3517311598) |
| `pe-taxsim-588` | GA 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-10-20)](https://github.com/PolicyEngine/policyengine-taxsim/issues/588#issuecomment-3420902464) |
| `pe-taxsim-590` | SC 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-10-20)](https://github.com/PolicyEngine/policyengine-taxsim/issues/590#issuecomment-3420867121) |
| `pe-taxsim-592` | MT 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-12-14)](https://github.com/PolicyEngine/policyengine-taxsim/issues/592#issuecomment-3651938004) |
| `pe-taxsim-593` | MN 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-10-20)](https://github.com/PolicyEngine/policyengine-taxsim/issues/593#issuecomment-3420754354) |
| `pe-taxsim-594` | MN 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-12-15)](https://github.com/PolicyEngine/policyengine-taxsim/issues/594#issuecomment-3652723249) |
| `pe-taxsim-597` | NJ 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-10-23)](https://github.com/PolicyEngine/policyengine-taxsim/issues/597#issuecomment-3435820966) |
| `pe-taxsim-603` | WI 2024 | `taxsim_wrong` | [maintainer_statement (feenberg, 2025-11-05)](https://github.com/PolicyEngine/policyengine-taxsim/issues/603#issuecomment-3491795796) |
| `pe-taxsim-605` | IA 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-12-14)](https://github.com/PolicyEngine/policyengine-taxsim/issues/605#issuecomment-3652382365) |
| `pe-taxsim-608` | MD 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-12-15)](https://github.com/PolicyEngine/policyengine-taxsim/issues/608#issuecomment-3652711439) |
| `pe-taxsim-609` | OH 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-11-04)](https://github.com/PolicyEngine/policyengine-taxsim/issues/609#issuecomment-3485216364) |
| `pe-taxsim-611` | NJ 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-11-11)](https://github.com/PolicyEngine/policyengine-taxsim/issues/611#issuecomment-3517077304) |
| `pe-taxsim-612` | VA 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-11-04)](https://github.com/PolicyEngine/policyengine-taxsim/issues/612#issuecomment-3484140116) |
| `pe-taxsim-613` | IA 2024 | `input_ambiguity` | [maintainer_statement (PavelMakarchuk, 2025-12-14)](https://github.com/PolicyEngine/policyengine-taxsim/issues/613#issuecomment-3651430500) |
| `pe-taxsim-614` | NY 2024 | `input_ambiguity` | [maintainer_statement (PavelMakarchuk, 2025-12-03)](https://github.com/PolicyEngine/policyengine-taxsim/issues/614#issuecomment-3605700446) |
| `pe-taxsim-615` | MA 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-12-14)](https://github.com/PolicyEngine/policyengine-taxsim/issues/615#issuecomment-3651387042) |
| `pe-taxsim-617` | MS 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-12-14)](https://github.com/PolicyEngine/policyengine-taxsim/issues/617#issuecomment-3651315876) |
| `pe-taxsim-632` | OK 2024 | `input_ambiguity` | [maintainer_statement (feenberg, 2025-12-03)](https://github.com/PolicyEngine/policyengine-taxsim/issues/632#issuecomment-3607447643) |
| `pe-taxsim-633` | IA 2024 | `convention` | [maintainer_statement (feenberg, 2025-11-30)](https://github.com/PolicyEngine/policyengine-taxsim/issues/633#issuecomment-3592737214) |
| `pe-taxsim-643` | NY 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-11-28)](https://github.com/PolicyEngine/policyengine-taxsim/issues/643#issuecomment-3589318651) |
| `pe-taxsim-649` | AR 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-12-12)](https://github.com/PolicyEngine/policyengine-taxsim/issues/649#issuecomment-3646809584) |
| `pe-taxsim-655` | VT 2024 | `convention` | [maintainer_statement (PavelMakarchuk, 2026-06-01)](https://github.com/PolicyEngine/policyengine-taxsim/issues/655#issuecomment-4593792427) |
| `pe-taxsim-671` | CT 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-12-19)](https://github.com/PolicyEngine/policyengine-taxsim/issues/671#issuecomment-3676585199) |
| `pe-taxsim-673` | NJ 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2025-12-19)](https://github.com/PolicyEngine/policyengine-taxsim/issues/673#issuecomment-3675595574) |
| `pe-taxsim-675` | WI 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-02-16)](https://github.com/PolicyEngine/policyengine-taxsim/issues/675#issuecomment-3905926070) |
| `pe-taxsim-676` | NE 2024 | `convention` | [maintainer_statement (feenberg, 2026-02-16)](https://github.com/PolicyEngine/policyengine-taxsim/issues/676#issuecomment-3908056058) |
| `pe-taxsim-680` | MD 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-02-16)](https://github.com/PolicyEngine/policyengine-taxsim/issues/680#issuecomment-3906230315) |
| `pe-taxsim-686` | DC 2024 | `convention` | [maintainer_statement (feenberg, 2026-05-14)](https://github.com/PolicyEngine/policyengine-taxsim/issues/686#issuecomment-4453532692) |
| `pe-taxsim-688` | MN 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-02-15)](https://github.com/PolicyEngine/policyengine-taxsim/issues/688#issuecomment-3905528496) |
| `pe-taxsim-712` | US 2021 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-02-23)](https://github.com/PolicyEngine/policyengine-taxsim/issues/712#issuecomment-3946836918) |
| `pe-taxsim-714` | US 2020, 2021, 2022 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-03-01)](https://github.com/PolicyEngine/policyengine-taxsim/issues/714#issuecomment-3980791342) |
| `pe-taxsim-716` | GA 2023, 2024, 2025 | `convention` | [maintainer_statement (feenberg, 2026-03-01)](https://github.com/PolicyEngine/policyengine-taxsim/issues/716#issuecomment-3980290481) |
| `pe-taxsim-717` | CA 2024 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-03-01)](https://github.com/PolicyEngine/policyengine-taxsim/issues/717#issuecomment-3980222880) |
| `pe-taxsim-718` | VA 2024, 2025 | `convention` | [maintainer_statement (feenberg, 2026-04-08)](https://github.com/PolicyEngine/policyengine-taxsim/issues/718#issuecomment-4209916831) |
| `pe-taxsim-720` | US 2024 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-03-01)](https://github.com/PolicyEngine/policyengine-taxsim/issues/720#issuecomment-3980951457) |
| `pe-taxsim-745` | DE 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-03-25)](https://github.com/PolicyEngine/policyengine-taxsim/issues/745#issuecomment-4130261512) |
| `pe-taxsim-748` | IA 2024 | `convention` | [maintainer_statement (PavelMakarchuk, 2026-03-25)](https://github.com/PolicyEngine/policyengine-taxsim/issues/748#issuecomment-4130188114) |
| `pe-taxsim-751` | DC 2024 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-04-07)](https://github.com/PolicyEngine/policyengine-taxsim/issues/751#issuecomment-4200831949) |
| `pe-taxsim-752` | MA 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-03-25)](https://github.com/PolicyEngine/policyengine-taxsim/issues/752#issuecomment-4130218559) |
| `pe-taxsim-753` | NM 2024 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-03-25)](https://github.com/PolicyEngine/policyengine-taxsim/issues/753#issuecomment-4128299802) |
| `pe-taxsim-762` | US 2025 | `convention` | [maintainer_statement (PavelMakarchuk, 2026-06-01)](https://github.com/PolicyEngine/policyengine-taxsim/issues/762#issuecomment-4589653568) |
| `pe-taxsim-765` | NJ 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-03-18)](https://github.com/PolicyEngine/policyengine-taxsim/issues/765#issuecomment-4082251065) |
| `pe-taxsim-766` | MN 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-03-18)](https://github.com/PolicyEngine/policyengine-taxsim/issues/766#issuecomment-4082449462) |
| `pe-taxsim-771` | MO 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-03-17)](https://github.com/PolicyEngine/policyengine-taxsim/issues/771#issuecomment-4078429011) |
| `pe-taxsim-782` | SC 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-03-25)](https://github.com/PolicyEngine/policyengine-taxsim/issues/782#issuecomment-4122656494) |
| `pe-taxsim-794` | US 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-03-29)](https://github.com/PolicyEngine/policyengine-taxsim/issues/794#issuecomment-4150830888) |
| `pe-taxsim-797` | ID 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-03-30)](https://github.com/PolicyEngine/policyengine-taxsim/issues/797#issuecomment-4151624755) |
| `pe-taxsim-798` | VT 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-03-30)](https://github.com/PolicyEngine/policyengine-taxsim/issues/798#issuecomment-4151560991) |
| `pe-taxsim-801` | MN 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-04-06)](https://github.com/PolicyEngine/policyengine-taxsim/issues/801#issuecomment-4194131817) |
| `pe-taxsim-806` | CA 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-04-06)](https://github.com/PolicyEngine/policyengine-taxsim/issues/806#issuecomment-4192902992) |
| `pe-taxsim-808` | CA 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-04-06)](https://github.com/PolicyEngine/policyengine-taxsim/issues/808#issuecomment-4192764832) |
| `pe-taxsim-809` | CA 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-04-06)](https://github.com/PolicyEngine/policyengine-taxsim/issues/809#issuecomment-4193589282) |
| `pe-taxsim-810` | DC 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-04-06)](https://github.com/PolicyEngine/policyengine-taxsim/issues/810#issuecomment-4193581465) |
| `pe-taxsim-813` | ME 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-04-06)](https://github.com/PolicyEngine/policyengine-taxsim/issues/813#issuecomment-4193627853) |
| `pe-taxsim-821` | CA 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-04-08)](https://github.com/PolicyEngine/policyengine-taxsim/issues/821#issuecomment-4210421816) |
| `pe-taxsim-829` | OH 2021 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-04-17)](https://github.com/PolicyEngine/policyengine-taxsim/issues/829#issuecomment-4269855723) |
| `pe-taxsim-830` | MD 2020, 2021, 2022, 2023 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-04-17)](https://github.com/PolicyEngine/policyengine-taxsim/issues/830#issuecomment-4271071536) |
| `pe-taxsim-835` | OK 2025 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-04-21)](https://github.com/PolicyEngine/policyengine-taxsim/issues/835#issuecomment-4288862810) |
| `pe-taxsim-851` | DC 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-05-14)](https://github.com/PolicyEngine/policyengine-taxsim/issues/851#issuecomment-4446568212) |
| `pe-taxsim-854` | LA 2025 | `convention` | [maintainer_statement (feenberg, 2026-05-12)](https://github.com/PolicyEngine/policyengine-taxsim/issues/854#issuecomment-4432619684) |
| `pe-taxsim-860` | MI 2025 | `convention` | [maintainer_statement (feenberg, 2026-06-01)](https://github.com/PolicyEngine/policyengine-taxsim/issues/860#issuecomment-4593532458) |
| `pe-taxsim-862` | MT 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-05-13)](https://github.com/PolicyEngine/policyengine-taxsim/issues/862#issuecomment-4446109954) |
| `pe-taxsim-863` | NE 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-05-25)](https://github.com/PolicyEngine/policyengine-taxsim/issues/863#issuecomment-4537724085) |
| `pe-taxsim-865` | NJ 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-07-02)](https://github.com/PolicyEngine/policyengine-taxsim/issues/865#issuecomment-4862331903) |
| `pe-taxsim-867` | OK 2025 | `convention` | [maintainer_statement (feenberg, 2026-05-12)](https://github.com/PolicyEngine/policyengine-taxsim/issues/867#issuecomment-4432261193) |
| `pe-taxsim-868` | RI 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-05-12)](https://github.com/PolicyEngine/policyengine-taxsim/issues/868#issuecomment-4434563214) |
| `pe-taxsim-869` | VT 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-04-30)](https://github.com/PolicyEngine/policyengine-taxsim/issues/869#issuecomment-4354608877) |
| `pe-taxsim-876` | CA 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-05-12)](https://github.com/PolicyEngine/policyengine-taxsim/issues/876#issuecomment-4428743882) |
| `pe-taxsim-879` | OK 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-05-07)](https://github.com/PolicyEngine/policyengine-taxsim/issues/879#issuecomment-4394014463) |
| `pe-taxsim-883` | ME 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-05-12)](https://github.com/PolicyEngine/policyengine-taxsim/issues/883#issuecomment-4434630599) |
| `pe-taxsim-884` | MI 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-05-07)](https://github.com/PolicyEngine/policyengine-taxsim/issues/884#issuecomment-4394139724) |
| `pe-taxsim-885` | SC 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-05-25)](https://github.com/PolicyEngine/policyengine-taxsim/issues/885#issuecomment-4537645008) |
| `pe-taxsim-894` | CA 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-05-12)](https://github.com/PolicyEngine/policyengine-taxsim/issues/894#issuecomment-4433954904) |
| `pe-taxsim-896` | VT 2025 | `convention` | [maintainer_statement (PavelMakarchuk, 2026-05-12)](https://github.com/PolicyEngine/policyengine-taxsim/issues/896#issuecomment-4433739024) |
| `pe-taxsim-904` | NJ 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-05-19)](https://github.com/PolicyEngine/policyengine-taxsim/issues/904#issuecomment-4483412266) |
| `pe-taxsim-905` | MT 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-05-25)](https://github.com/PolicyEngine/policyengine-taxsim/issues/905#issuecomment-4537445574) |
| `pe-taxsim-907` | NM 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-05-18)](https://github.com/PolicyEngine/policyengine-taxsim/issues/907#issuecomment-4479750849) |
| `pe-taxsim-916` | DE 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-07-02)](https://github.com/PolicyEngine/policyengine-taxsim/issues/916#issuecomment-4862365584) |
| `pe-taxsim-917` | MD 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-05-25)](https://github.com/PolicyEngine/policyengine-taxsim/issues/917#issuecomment-4536557548) |
| `pe-taxsim-920` | WV 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-05-29)](https://github.com/PolicyEngine/policyengine-taxsim/issues/920#issuecomment-4579862667) |
| `pe-taxsim-921` | KY 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-05-25)](https://github.com/PolicyEngine/policyengine-taxsim/issues/921#issuecomment-4535155442) |
| `pe-taxsim-937` | MT 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-07-02)](https://github.com/PolicyEngine/policyengine-taxsim/issues/937#issuecomment-4862291968) |
| `pe-taxsim-947` | UT 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-06-02)](https://github.com/PolicyEngine/policyengine-taxsim/issues/947#issuecomment-4597753209) |
| `pe-taxsim-964` | OK 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-07-02)](https://github.com/PolicyEngine/policyengine-taxsim/issues/964#issuecomment-4862297685) |
| `pe-taxsim-968` | MN 2025 | `convention` | [maintainer_statement (PavelMakarchuk, 2026-08-23)](https://github.com/PolicyEngine/policyengine-taxsim/issues/968#issuecomment-5388015439) |
| `pe-taxsim-969` | NY 2025 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-07-30)](https://github.com/PolicyEngine/policyengine-taxsim/issues/969#issuecomment-5135269188) |
| `pe-taxsim-970` | MD 2025 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-07-06)](https://github.com/PolicyEngine/policyengine-taxsim/issues/970#issuecomment-4893541643) |
| `pe-taxsim-974` | NY 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-07-02)](https://github.com/PolicyEngine/policyengine-taxsim/issues/974#issuecomment-4862412730) |
| `pe-taxsim-978` | OK 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-06-16)](https://github.com/PolicyEngine/policyengine-taxsim/issues/978#issuecomment-4714511403) |
| `pe-taxsim-981` | OH 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-06-16)](https://github.com/PolicyEngine/policyengine-taxsim/issues/981#issuecomment-4714511563) |
| `pe-taxsim-982` | OH 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-06-16)](https://github.com/PolicyEngine/policyengine-taxsim/issues/982#issuecomment-4714511685) |
| `pe-taxsim-986` | WA 2025 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-06-18)](https://github.com/PolicyEngine/policyengine-taxsim/issues/986#issuecomment-4743193673) |
| `pe-taxsim-991` | RI 2025 | `convention` | [maintainer_statement (feenberg, 2026-06-16)](https://github.com/PolicyEngine/policyengine-taxsim/issues/991#issuecomment-4720287901) |
| `pe-taxsim-1002` | VT 2025 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-06-23)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1002#issuecomment-4779773384) |
| `pe-taxsim-1004` | US 2025 | `convention` | [maintainer_statement (feenberg, 2026-06-25)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1004#issuecomment-4799801660) |
| `pe-taxsim-1014` | HI 2024 | `convention` | [maintainer_statement (feenberg, 2026-06-24)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1014#issuecomment-4792177714) |
| `pe-taxsim-1015` | MN 2021, 2022 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-07-30)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1015#issuecomment-5135316535) |
| `pe-taxsim-1017` | OH 2025 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-06-24)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1017#issuecomment-4790033034) |
| `pe-taxsim-1025` | AZ 2025 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-07-01)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1025#issuecomment-4858859656) |
| `pe-taxsim-1027` | GA 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-07-01)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1027#issuecomment-4855222730) |
| `pe-taxsim-1030` | WV 2025 | `input_ambiguity` | [maintainer_statement (PavelMakarchuk, 2026-06-29)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1030#issuecomment-4837751621) |
| `pe-taxsim-1034` | WA 2025 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-07-02)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1034#issuecomment-4866455754) |
| `pe-taxsim-1035` | US 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-07-01)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1035#issuecomment-4854917214) |
| `pe-taxsim-1041` | DC 2021 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-07-07)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1041#issuecomment-4909635624) |
| `pe-taxsim-1050` | MI 2021 | `convention` | [maintainer_statement (feenberg, 2026-07-06)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1050#issuecomment-4898193198) |
| `pe-taxsim-1056` | ME 2025 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-07-06)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1056#issuecomment-4894361450) |
| `pe-taxsim-1057` | AZ 2025 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-07-30)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1057#issuecomment-5134516688) |
| `pe-taxsim-1057-mo` | MO 2025 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-07-30)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1057#issuecomment-5134516688) |
| `pe-taxsim-1063` | MD 2024 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-07-06)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1063#issuecomment-4895833341) |
| `pe-taxsim-1067` | US 2022, 2023 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-07-30)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1067#issuecomment-5135851276) |
| `pe-taxsim-1068` | US 2021, 2022, 2023, 2024, 2025 | `convention` | [maintainer_statement (feenberg, 2026-07-06)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1068#issuecomment-4897009628); [maintainer_statement (PavelMakarchuk, 2026-07-06)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1068#issuecomment-4896784506); [maintainer_statement (PavelMakarchuk, 2026-07-06)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1068#issuecomment-4897543635); [maintainer_statement (feenberg, 2026-03-01)](https://github.com/PolicyEngine/policyengine-taxsim/issues/716#issuecomment-3980290481) |
| `pe-taxsim-1071` | OR 2021, 2023, 2025 | `convention` | [maintainer_statement (PavelMakarchuk, 2026-07-07)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1071#issuecomment-4908175317) |
| `pe-taxsim-1075` | ME 2021, 2022 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-07-31)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1075#issuecomment-5143199928) |
| `pe-taxsim-1075-hi` | HI 2021, 2022 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-07-31)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1075#issuecomment-5143199928) |
| `pe-taxsim-1075-il` | IL 2021, 2022 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-07-31)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1075#issuecomment-5143199928) |
| `pe-taxsim-1075-in` | IN 2021, 2022 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-07-31)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1075#issuecomment-5143199928) |
| `pe-taxsim-1076` | KY 2025 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-07-13)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1076#issuecomment-4958690775) |
| `pe-taxsim-1077` | CT 2021 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-07-13)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1077#issuecomment-4958673642) |
| `pe-taxsim-1078` | MT 2021 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-07-13)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1078#issuecomment-4958690927) |
| `pe-taxsim-1079` | NM 2021, 2022, 2023 | `convention` | [maintainer_statement (PavelMakarchuk, 2026-07-13)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1079#issuecomment-4958502490) |
| `pe-taxsim-1080` | ME 2021, 2022 | `convention` | [maintainer_statement (PavelMakarchuk, 2026-07-13)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1080#issuecomment-4958502634) |
| `pe-taxsim-1081` | CO 2021, 2022 | `convention` | [maintainer_statement (PavelMakarchuk, 2026-07-13)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1081#issuecomment-4958502789) |
| `pe-taxsim-1082` | CO 2021, 2022 | `convention` | [maintainer_statement (PavelMakarchuk, 2026-07-13)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1082#issuecomment-4958502921) |
| `pe-taxsim-1083` | OK 2021 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-07-13)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1083#issuecomment-4958673834) |
| `pe-taxsim-1084` | MA 2021 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-07-14)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1084#issuecomment-4969874679) |
| `pe-taxsim-1086` | ID 2021 | `input_ambiguity` | [maintainer_statement (PavelMakarchuk, 2026-07-14)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1086#issuecomment-4972346783) |
| `pe-taxsim-1087` | HI 2021, 2022 | `convention` | [maintainer_statement (PavelMakarchuk, 2026-07-14)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1087#issuecomment-4972346561) |
| `pe-taxsim-1088` | KY 2021 | `input_ambiguity` | [maintainer_statement (feenberg, 2026-07-14)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1088#issuecomment-4974106061) |
| `pe-taxsim-1089` | VA 2021 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-07-15)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1089#issuecomment-4983069520) |
| `pe-taxsim-1094` | MT 2021 | `input_ambiguity` | [maintainer_statement (PavelMakarchuk, 2026-07-15)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1094#issuecomment-4984989317) |
| `pe-taxsim-1097` | DE 2021 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-07-16)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1097#issuecomment-4994571740) |
| `pe-taxsim-1098` | AZ 2021 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-07-16)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1098#issuecomment-4994571502) |
| `pe-taxsim-1099` | WA 2021 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-07-16)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1099#issuecomment-4993797955) |
| `pe-taxsim-1100` | WI 2021 | `convention` | [maintainer_statement (feenberg, 2026-07-19)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1100#issuecomment-5016908795) |
| `pe-taxsim-1102` | AZ 2021 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-07-20)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1102#issuecomment-5025098441) |
| `pe-taxsim-1104` | MO 2021 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-07-20)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1104#issuecomment-5023633595) |
| `pe-taxsim-1105` | AZ 2021 | `convention` | [maintainer_statement (PavelMakarchuk, 2026-07-22)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1105#issuecomment-5041349549) |
| `pe-taxsim-1106` | MA 2021 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-07-22)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1106#issuecomment-5041354980) |
| `pe-taxsim-1108` | IA 2021 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-07-23)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1108#issuecomment-5053880078) |
| `pe-taxsim-1109` | DC 2021 | `input_ambiguity` | [maintainer_statement (DTrim99, 2026-07-27)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1109#issuecomment-5091791708) |
| `pe-taxsim-1110` | IA 2021 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-07-27)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1110#issuecomment-5092192618) |
| `pe-taxsim-1111` | IA 2021 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-07-27)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1111#issuecomment-5095810093) |
| `pe-taxsim-1113` | DE 2021 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-07-27)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1113#issuecomment-5096752624) |
| `pe-taxsim-1115` | KS 2021 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-07-29)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1115#issuecomment-5119766950) |
| `pe-taxsim-1116` | ME 2021 | `convention` | [maintainer_statement (feenberg, 2026-08-03)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1116#issuecomment-5168097204) |
| `pe-taxsim-1117` | MI 2021 | `input_ambiguity` | [maintainer_statement (DTrim99, 2026-08-03)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1117#issuecomment-5167851533) |
| `pe-taxsim-1118` | PA 2021 | `convention` | [maintainer_statement (feenberg, 2026-08-04)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1118#issuecomment-5181043696) |
| `pe-taxsim-1121` | MT 2021 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-08-03)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1121#issuecomment-5169823358) |
| `pe-taxsim-1122` | MT 2021 | `policyengine_wrong` | [maintainer_statement (PavelMakarchuk, 2026-08-18)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1122#issuecomment-5334984545) |
| `pe-taxsim-1123` | ME 2022 | `convention` | [maintainer_statement (feenberg, 2026-08-23)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1123#issuecomment-5388091942) |
| `pe-taxsim-1127` | CT 2022 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-08-12)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1127#issuecomment-5271914652) |
| `pe-taxsim-1129` | IA 2022 | `convention` | [maintainer_statement (DTrim99, 2026-08-11)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1129#issuecomment-5258468461) |
| `pe-taxsim-1131` | VT 2022 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-08-13)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1131#issuecomment-5281881382) |
| `pe-taxsim-1133` | MD 2022 | `convention` | [maintainer_statement (DTrim99, 2026-08-14)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1133#issuecomment-5296329084) |
| `pe-taxsim-1134` | CT 2022 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-08-14)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1134#issuecomment-5299240438) |
| `pe-taxsim-1135` | NY 2022 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-08-17)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1135#issuecomment-5319172078) |
| `pe-taxsim-1137` | AR 2022 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-08-18)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1137#issuecomment-5328847982) |
| `pe-taxsim-1142` | CT 2022 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-08-19)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1142#issuecomment-5345374255) |
| `pe-taxsim-1143` | AR 2022 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-08-20)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1143#issuecomment-5356728748) |
| `pe-taxsim-1144` | WI 2022 | `input_ambiguity` | [maintainer_statement (DTrim99, 2026-08-21)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1144#issuecomment-5375438059) |
| `pe-taxsim-1146` | DE 2022 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-08-24)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1146#issuecomment-5397468305) |
| `pe-taxsim-1148` | KY 2022 | `convention` | [maintainer_statement (DTrim99, 2026-08-24)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1148#issuecomment-5399967070) |
| `pe-taxsim-1149` | KY 2022 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-08-24)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1149#issuecomment-5400459272) |
| `pe-taxsim-1155` | WA 2023 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-08-26)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1155#issuecomment-5430418750) |
| `pe-taxsim-1157` | AR 2023 | `input_ambiguity` | [maintainer_statement (DTrim99, 2026-08-26)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1157#issuecomment-5432457007) |
| `pe-taxsim-1161` | CA 2023 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-08-31)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1161#issuecomment-5479712649) |
| `pe-taxsim-1163` | DE 2023 | `convention` | [maintainer_statement (DTrim99, 2026-09-01)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1163#issuecomment-5499654784) |
| `pe-taxsim-1165` | PA 2023 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-09-03)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1165#issuecomment-5527333149) |
| `pe-taxsim-1166` | WA 2023 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-09-04)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1166#issuecomment-5542127178) |
| `pe-taxsim-1167` | OK 2023 | `convention` | [maintainer_statement (DTrim99, 2026-09-04)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1167#issuecomment-5543988854) |
| `pe-taxsim-1168` | OH 2023 | `convention` | [maintainer_statement (feenberg, 2026-09-09)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1168#issuecomment-5607006497) |
| `pe-taxsim-1169` | MT 2023 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-09-09)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1169#issuecomment-5606882563) |
| `pe-taxsim-1172` | IL 2021 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-09-08)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1172#issuecomment-5590556851) |
| `pe-taxsim-1173` | MN 2024 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-09-09)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1173#issuecomment-5606180462) |
| `pe-taxsim-1174` | OR 2024, 2025 | `convention` | [maintainer_statement (feenberg, 2026-09-14)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1174#issuecomment-5665589163) |
| `pe-taxsim-1179` | AR 2021 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-09-11)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1179#issuecomment-5638224684) |
| `pe-taxsim-1181` | KS 2021 | `input_ambiguity` | [maintainer_statement (DTrim99, 2026-09-14)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1181#issuecomment-5670183008) |
| `pe-taxsim-1184` | AL 2021 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-09-15)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1184#issuecomment-5687272825) |
| `pe-taxsim-1187` | NE 2021 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-09-16)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1187#issuecomment-5703771312) |
| `pe-taxsim-1188` | DE 2021, 2022 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-09-17)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1188#issuecomment-5717421515) |
| `pe-taxsim-1189` | MT 2021 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-09-18)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1189#issuecomment-5731397232) |
| `pe-taxsim-1193` | IL 2021 | `policyengine_wrong` | [maintainer_statement (DTrim99, 2026-09-21)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1193#issuecomment-5764344054) |
| `pe-taxsim-1194` | DE 2021 | `convention` | [maintainer_statement (DTrim99, 2026-09-21)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1194#issuecomment-5764721306) |
| `pe-taxsim-1200` | MN 2024 | `convention` | [maintainer_statement (DTrim99, 2026-09-22)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1200#issuecomment-5782214094) |
| `pe-taxsim-1201` | GA 2024 | `input_ambiguity` | [maintainer_statement (DTrim99, 2026-09-23)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1201#issuecomment-5803196813) |
| `pe-taxsim-1202` | GA 2024 | `convention` | [maintainer_statement (DTrim99, 2026-09-23)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1202#issuecomment-5803078342) |
| `pe-taxsim-1222` | LA 2025 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-09-25)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1222#issuecomment-5833721957) |
| `pe-taxsim-1225` | US 2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-09-24)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1225#issuecomment-5820033668) |
| `pe-taxsim-1226` | US 2022 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-09-24)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1226#issuecomment-5823307696) |
| `pe-taxsim-1228` | US 2022 | `convention` | [maintainer_statement (feenberg, 2026-09-24)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1228#issuecomment-5823470756) |
| `pe-taxsim-1230` | MD 2021 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-09-24)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1230#issuecomment-5821109548) |
| `pe-taxsim-1231` | MT 2024 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-09-24)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1231#issuecomment-5823161603) |
| `pe-taxsim-1233` | VA 2024 | `taxsim_wrong` | [maintainer_statement (feenberg, 2026-09-24)](https://github.com/PolicyEngine/policyengine-taxsim/issues/1233#issuecomment-5823072001) |

<!-- END READY RECORDS -->
