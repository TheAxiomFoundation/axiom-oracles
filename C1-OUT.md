# Brief C1 — corpus gap scan, spine ledger, and capture-gap closure

The requested ops destination is outside this worktree's writable roots, so this
report uses the authorized fallback `C1-OUT.md`. No `PROGRESS.md` file was
changed, and no push or pull request was made.

## Outcome

C1 adopts and fully ledgers the 174-root DE-precedent scope, but it does **not**
authorize the encode track yet. The pinned corpus scan found 54 missing provision
texts, and the adopted spine has 117 pending rows. The bulk-XML replay found 301
authoritative empowering-Act edges, all already represented in the instrument
graph; therefore the actual pending-disposition merge was an honest zero-row
no-op and 136 capture rows remain open.

Implementation commit: `2e27a2fd2b549894c2cf5081ea728cb3a8b6e335`.
This report and the V3 attestation that names that implementation commit are a
follow-up documentation commit; its delivery HEAD is reported in the final
handoff because a commit cannot contain its own SHA.

## 1. Corpus gap scan

Artifact: `closure/nz/corpus-gap-scan.json`

- Schema: `axiom_oracles.nz_corpus_gap_scan.v1`.
- Signed release: `nz-rulespec-2026-07-25`.
- Release content SHA-256:
  `fec362b985739f27910f0e950fc03e298528a42cdff6f694b19c9ed0850c8405`.
- Corpus commit: `2d077803ee17f921c30014b9e98ae9ee3b612512`.
- Audited source denominator: 229 law-derived rows, 77 distinct
  `derivation_instrument` expressions, and 18 bearing instruments.
- Normalized ledger: 287 provision rows across 26 instruments; 233 are in the
  pinned release and 54 are missing, across 13 instruments.
- Artifact SHA-256:
  `aa36a599b6a7a2a09784f7cc4a1ebea69e19c5c54c597fe203c2c06f6c9735e8`.

Each JSON ledger row contains exactly the requested public columns
`provision`, `in_release`, and `source_url`; separately keyed metadata preserves
the normalized citation path and coverage basis.

### Per-instrument ingest counts

| Instrument | Rows | In release | Missing |
|---|---:|---:|---:|
| Accident Compensation (Earners' Levy) Regulations 2025 | 3 | 3 | 0 |
| Accident Compensation Act 2001 | 13 | 13 | 0 |
| DET 26/01 | 1 | 0 | 1 |
| DET 26/02 | 1 | 0 | 1 |
| DET 26/03 | 1 | 0 | 1 |
| Goods and Services Tax Act 1985 | 3 | 3 | 0 |
| IS 26/12 | 1 | 0 | 1 |
| IS 26/12 FS 1 | 1 | 0 | 1 |
| Income Tax Act 2007 | 72 | 71 | 1 |
| Inland Revenue — Deductions from salary and wages | 1 | 1 | 0 |
| Legislation Act 2019 | 2 | 0 | 2 |
| Public and Community Housing Management Act 1992 | 1 | 1 | 0 |
| Social Assistance Legislation (Accommodation Supplement and Income-related Rent) Amendment Act 2025 | 13 | 13 | 0 |
| Social Security (Modernisation) Amendment Act 2026 | 41 | 0 | 41 |
| Social Security (Rates of Benefits and Allowances) Order 2026 | 1 | 1 | 0 |
| Social Security Act 2018 | 60 | 60 | 0 |
| Social Security Regulations 2018 | 7 | 7 | 0 |
| Student Allowances Regulations 1998 | 30 | 30 | 0 |
| TRA 005/21 [2023] NZTRA 1 (CSUM 23/04) | 1 | 0 | 1 |
| Tax Administration Act 1994 | 24 | 24 | 0 |
| Tax Information Bulletin Vol 37 No 5 — Clarifying IETC eligibility | 1 | 0 | 1 |
| Tax Information Bulletin Vol 37 No 7 — Budget 2025 WFF commentary | 1 | 0 | 1 |
| Taxation (Annual Rates 2025–26, Compliance Simplification, and Remedial Measures) Act 2026 commentary | 1 | 0 | 1 |
| Taxation (Annual Rates for 2024–25, Emergency Response, and Remedial Measures) Act 2025 | 1 | 0 | 1 |
| Taxation (Annual Rates for 2025–26, Compliance Simplification, and Remedial Measures) Act 2026 | 2 | 2 | 0 |
| Taxation (Budget Measures) Act 2025 | 4 | 4 | 0 |
| **Total** | **287** | **233** | **54** |

### Priority cones

| Priority cone | Rows | In release | Missing | Result |
|---|---:|---:|---:|---|
| ACC earnings-definition instruments | 19 | 19 | 0 | zero gap |
| Individual income tax | 4 | 4 | 0 | zero gap |
| IETC, including ITA LC 13, YD 1, and HR 8 | 47 | 37 | 10 | ingest required |
| Winter Energy Payment, including SSA ss 72–74 and rates | 47 | 6 | 41 | ingest required |
| Demographics | 12 | 12 | 0 | zero gap; birth-register dates are external observations |

“Schedule 2 student definitions” is normalized to the `full-time student`
definition consumed by `jobseeker_full_time_student`; the distinct `student
allowance` definition is not named by that dependency leaf. Closed ranges are
expanded inclusively, subsections map to their parent corpus row, and a
null-body structural root counts as present only when a non-empty descendant is
present.

### Corpus-ingest worklist

The JSON artifact lists every missing provision. Grouped official-source
worklist:

| Priority | Instrument | Missing | Official source |
|---:|---|---:|---|
| 3 | DET 26/01 | 1 | [IRD determination](https://www.taxtechnical.ird.govt.nz/determinations/emergency-events/2026/det-26-01) |
| 3 | DET 26/02 | 1 | [IRD determination](https://www.taxtechnical.ird.govt.nz/determinations/emergency-events/2026/det-26-02) |
| 3 | DET 26/03 | 1 | [IRD determination](https://www.taxtechnical.ird.govt.nz/determinations/emergency-events/2026/det-26-03) |
| 3 | IS 26/12 | 1 | [IRD interpretation statement](https://www.taxtechnical.ird.govt.nz/interpretation-statements/2026/is-26-12) |
| 3 | IS 26/12 FS 1 | 1 | [IRD fact sheet](https://www.taxtechnical.ird.govt.nz/fact-sheets/2026/is-26-12-fs-1) |
| 3 | Legislation Act 2019 | 2 | [NZ Legislation](https://www.legislation.govt.nz/act/public/2019/58/en/latest/) |
| 3 | TRA 005/21 [2023] NZTRA 1 (CSUM 23/04) | 1 | [IRD case summary](https://www.taxtechnical.ird.govt.nz/case-summaries/2023/csum-23-04) |
| 3 | TIB Vol 37 No 5 | 1 | [IRD TIB PDF](https://www.taxtechnical.ird.govt.nz/-/media/project/ir/tt/pdfs/tib/volume-37---2025/tib-vol37-no5.pdf) |
| 3 | Taxation (Annual Rates for 2024–25, Emergency Response, and Remedial Measures) Act 2025 | 1 | [NZ Legislation](https://www.legislation.govt.nz/act/public/2025/9/en/latest/) |
| 4 | Social Security (Modernisation) Amendment Act 2026 | 41 | [NZ Legislation](https://www.legislation.govt.nz/act/public/2026/27/en/latest/) |
| 6 | Income Tax Act 2007 (MB 14 empty-body row) | 1 | [NZ Legislation](https://www.legislation.govt.nz/act/public/2007/97/en/latest/) |
| 6 | TIB Vol 37 No 7 | 1 | [IRD TIB PDF](https://www.taxtechnical.ird.govt.nz/-/media/project/ir/tt/pdfs/tib/volume-37---2025/tib-vol37-no7.pdf) |
| 6 | 2026 Act commentary | 1 | [IRD commentary PDF](https://www.taxtechnical.ird.govt.nz/-/media/project/ir/tp/publications/2026/compliance-simplification-bill-act-commentary.pdf) |

Regime rule 7 therefore keeps encoding gated until this 54-row ingest worklist
is closed or each row receives an adjudicated alternative disposition.

## 2. Adopted spine ledger

Artifact: `closure/nz/spine-ledger.json`

C1 adopts the **174-root dependency subgraph lower bound** as the working
scope. This follows the explicit scoped-root shape in DE pull request #485,
merge `e77c93099`: `closure/de/source.json` declares program `root_nodes` and
`evidence_roots` with `resolution=self_and_descendants`, while the DE
certificate selects the amount subgraph. The precedent is cited only for that
explicit scope convention; its later-corrected law-derived boundary treatment
is not adopted.

The scope decision is final for this working ledger
(`scope_adjudication_pending=false`) but remains a disclosed lower bound that a
later adjudication can widen without changing row/hash conventions.

| Instrument | Total | Encoded | Classified | Excluded | Pending |
|---|---:|---:|---:|---:|---:|
| Accident Compensation Act 2001 | 13 | 0 | 0 | 0 | 13 |
| Income Tax Act 2007 | 60 | 40 | 0 | 0 | 20 |
| Public and Community Housing Management Act 1992 | 1 | 0 | 0 | 0 | 1 |
| Tax Administration Act 1994 | 1 | 0 | 0 | 0 | 1 |
| Social Security Act 2018 | 55 | 9 | 0 | 0 | 46 |
| Taxation (Annual Rates for 2024–25, Emergency Response, and Remedial Measures) Act 2025 | 1 | 0 | 0 | 0 | 1 |
| Taxation (Annual Rates for 2025–26, Compliance Simplification, and Remedial Measures) Act 2026 | 2 | 2 | 0 | 0 | 0 |
| Student Allowances Regulations 1998 | 30 | 0 | 0 | 0 | 30 |
| Social Security Regulations 2018 | 7 | 3 | 0 | 0 | 4 |
| Accident Compensation (Earners' Levy) Regulations 2025 | 3 | 2 | 0 | 0 | 1 |
| Social Security (Rates of Benefits and Allowances) Order 2026 | 1 | 1 | 0 | 0 | 0 |
| **Adopted scope** | **174** | **57** | **0** | **0** | **117** |

There are zero silent rows. Each row records its status, exact citation path,
source receipt, and SHA-256 of the rendered legal body. The body-hash ledger is
complete. Source partition: 173 roots from signed release
`nz-rulespec-2026-07-25`, plus one official-web-only root:
[2025 No 9 s 105](https://www.legislation.govt.nz/act/public/2025/0009/latest/LMS1000039.html).
The retained exact `<prov>` excerpt and receipt are
`closure/nz/sources/taxation-2025-s105.xml` and
`closure/nz/sources/taxation-2025-s105-receipt.json`.

- Rowset SHA-256:
  `4a39579f3c8176fa36bc21fa3aa87627cc3598dc3e2febac7fe9fb3e22b86166`.
- Ledger artifact SHA-256:
  `afb21ae1b9afd4b18dafe3cf22f86e2a71e79ae0d1e729f650b1edbdffa46bae`.
- Official excerpt SHA-256:
  `5b36778d3438b72b7ee6ee6f9bebbf1c380dc6f70676b28829e508a1507647dc`.

The conservative whole-governing-Act alternative is recorded but **not
adopted**: 4,707 rows = 57 encoded + 4,650 pending (zero classified or
excluded). Its governing-Acts-only component is 4,635 rows = 49 encoded +
4,586 pending. It can replace the working denominator without reworking the
ledger format.

## 3. PCO bulk-XML reverse index

Artifact: `closure/nz/pco-empowering-act-reverse-index.json`

The producer replayed the retained official New Zealand Legislation API v0
snapshot `2026-06-16-pco-latest`, originally enumerated through
[`/v0/works/`](https://api.legislation.govt.nz/docs/) and downloaded through
the official per-work XML endpoint. It scanned only normalized `<pursuant>`
text for an exact target-Act title; ordinary body/title mentions are not edges.

- Snapshot manifest SHA-256:
  `a3e0116306a7818b98f9b3a5505b8df10a50e5f0fa16dcef8efc6e60a868bb4c`.
- 11,260 works discovered; 11,259 official XML files downloaded and scanned.
- One failed work, `secondary-legislation_pco-drafted_2001_007`, did not match
  any target Act and does not affect the exact edge count.
- Reverse-index artifact SHA-256:
  `8d442be59f586dbe46b987bcd319423c0b083e82c699077b040ab25bb80f11b4`.

| Empowering Act | Listing rows | Exact XML edges | Already in graph | Newly resolved / merged pending | Remaining |
|---|---:|---:|---:|---:|---:|
| Income Tax Act 2007 | 202 | 109 | 109 | 0 | 93 |
| Social Security Act 2018 | 99 | 66 | 66 | 0 | 33 |
| Accident Compensation Act 2001 | 136 | 126 | 126 | 0 | 10 |
| **Total** | **437** | **301** | **301** | **0** | **136** |

The producer emits full merge-ready `pending_disposition_rows` owned by B2 for
any genuinely new edge. This replay produced none, so rewriting the instrument
graph or dispositions would have invented a change. The graph merge is
therefore an exact zero-row no-op.

Documented limits:

- The live API requires `X-Api-Key`, and no key was available; the retained
  official snapshot was used. The documented works endpoint has no
  empowering-Act reverse filter.
- The official [XML documentation](https://www.legislation.govt.nz/learn-more/legislation-data/xml-data/)
  and [site-scope documentation](https://www.legislation.govt.nz/howitworks.aspx)
  explain that agency-drafted material can be outside the PCO XML set or be
  supplied in varying HTML/PDF formats.
- The official data-catalogue page and an API-announcement path presented
  automated-access/JavaScript verification walls. Those paths were stopped;
  no wall was bypassed.
- No predecessor-to-successor Act inference was made without an authoritative
  continuation/savings rule. A future multi-target `<pursuant>` match also
  fails closed because the graph currently has one scalar Act owner.
- The forbidden client-rendered Act tabs and all human-verification flows were
  not used.

## 4. Integration and certificate values

The new spine ledger is byte-bound into `closure/nz/summary.json`; the closure
producer validates the exact 174-row set, rowset hash, statuses, source
partition, and conservative alternative. The seven certificates were
regenerated. The honest result is open because 117 adopted-scope provisions
are pending:

| Certificate | Closed | Closed status | Certified |
|---|---|---|---|
| `nz/acc-earners-levy` | false | `computed_open` | false / `no` |
| `nz/accommodation-supplement` | false | `computed_open` | false / `no` |
| `nz/income-tax` | false | `computed_open` | false / `no` |
| `nz/independent-earner-tax-credit` | false | `computed_open` | false / `no` |
| `nz/main-benefits` | false | `computed_open` | false / `no` |
| `nz/winter-energy-payment` | false | `computed_open` | false / `no` |
| `nz/working-for-families` | false | `computed_open` | false / `no` |

## 5. Gate receipts

- Ten producer `--check` modes: pass (the original seven NZ modes plus corpus
  scan, spine ledger, and PCO reverse index).
- `scripts/certify.py --check`: pass, certificates up to date.
- Full `tests/test_certification_mutants.py`: **259 passed**, including the
  coordinated dropped-spine-row mutant and exact-byte restoration guard.
- New producer tests: **5 passed**.
- Existing NZ instrument-frontier mutant file: **17 passed**.
- Simulated NZ refresh:
  `SIMULATE_DERIVED_REFRESH=1 ... nz-treasury-incomeexplorer nz-certified` —
  pass, including all downstream staleness checks and the unexplained ratchet.
- Cross-jurisdiction identity: against the branch's frozen `origin/main`
  merge base `9a8274b4303b512876b56453622f3cdca3f91725`, the derived-tree diff contains
  13 paths, all NZ-scoped; **zero non-NZ derived paths differ**. The live
  `origin/main` tip advanced during this lane through independent affected
  reruns, so the merge-base comparison is the stable branch identity gate.
- `ruff check`, Python compile checks, and `git diff --check`: pass.
- `scripts/nz_v3_audit_report.py --check`: pass after binding implementation
  commit `2e27a2fd2b549894c2cf5081ea728cb3a8b6e335`.

On Darwin arm64, DE-only gates first verified the committed Linux ELF hash and
then replayed with an arm64 binary built from the exact pinned v0.2.2 source.
The temporary adapter was removed before commit. The optional hermetic
`test_commit_refreshed_report.py` fixture forcibly replaces `PYTHONPATH`, so it
cannot load that local adapter; its observed failures stop at DE executable
rederivation. The required real-tree simulated refresh passes with the verified
adapter.
