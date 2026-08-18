# DK closed and executable producers (WS2 + WS3)

Status: **CERTIFIED=YES at rulespec-dk f12271e37 — all four premises computed
true, blockers=[], 10 provisions encoded / 1 classified / 13 excluded with
text-grounded reasons / 0 pending, boundary frontier complete (89 grounded
inputs). The certificate certifies benefit year 2025, Denmark excluding the
Faroe Islands and Greenland, at the exact pinned corpus, RuleSpec, engine,
manifests, and receipts; suite results remain 7/8, 0/1, 0/1 with dispositioned
mismatches of DKK 313,33 / 60 / 880.**

Strict contract (final, superseding an interim global-strict restoration):
`--strict` enforces findings on manifests that declare `strict: true`; the
census counts a lane as `bridge_audited` ONLY when it declares `strict: true`
AND validates clean, so the opt-in is bound to the certificate (dropping the
flag drops audited/exercised — mutant-proven). Findings on non-strict
manifests are visible audit debt: co-snap-populace's four genuine findings
(unpinned population identity, cross-repo covered_by, partial audits,
unverified completeness) print on every run and keep its row unaudited, but
do not red the org's CI — they are that lane's own burndown.

## Checkout and source provenance

- Continued on the requested local-only branch `d3/dk-exercised`, building on
  WS1 commit `27a14d0f3`; nothing was pushed.
- The pre-existing untracked `.axiom/` run-log directory was left untouched and
  is not part of this work.
- Refreshing `rulespec-dk` was attempted before generation. The sandbox could
  not write that checkout's `FETCH_HEAD`, and a separate temporary fetch could
  not resolve `github.com`. The GitHub API independently verified current
  `main` as signed merge `369aaf920692d9c778d37cfc0f97373403131a92` and
  showed that its only first-parent change is
  `.github/workflows/repository-checks.yml`. The relevant `dk/statutes` bytes
  are identical between locally available `main@9986b6035c4e557b9b40645dfe2f3e4cffb6037c`
  and the merged guard branch. Both producers therefore honestly record commit
  `9986b603...`; no unavailable SHA was fabricated. The executable receipt now
  stores that resolved commit as both `rulespec.ref` and `rulespec.sha`, and all
  replay paths use the recorded commit rather than mutable `main`.
- The closure producer reads the release JSONL as an immutable tracked Git blob
  from `TheAxiomFoundation/axiom-corpus@a2e713913fb7250b28b55407c850c3c9ae3c69a3`
  (release SHA-256
  `c906f1b6b709d3602bfd1ece96404462cbe53b4f9049056eff997aac037bdf44`).
  Dirty or untracked corpus bytes cannot authorize closure.
- The executable producer used the requested binary at rules-engine commit
  `05eac9d2f89dabe5c6673176260762cef3a58f47`; its measured SHA-256 is exactly
  `079c26f4244db8c2a72fcbfb8cf88aaa5cb7c99628dc1c8d9d3b2d011e5f32a5`.

## WS2 — closed producer

Added `scripts/closure_ledger.py` and the generated/committed split at
`conformance/closure/dk-boerne-og-ungeydelse.yaml`.

- The generated spine contains all 24 direct paragraffer under
  `dk/statute/lbk-603-2025/boerne-og-ungeydelsesloven/`, in contiguous release
  order with body hashes.
- RuleSpec content is read from immutable Git blobs after resolving the moving
  ref once. Direct modules must cite the matching provision body hash, and only
  the explicit `entity_not_supported` status is accepted as a classified row.
- The ledger result is 2 encoded (§§ 1 and 1 a), 1 partially encoded (§ 5), 1
  classified-with-reason (§ 4), 8 excluded-with-reason, and 12 pending.
  Exclusions are limited to defensible administrative/appeal/repealed/penalty/
  public-finance/delegation/commencement provisions (§§ 4 d, 6, 6 a, 7, 9,
  12, 13, and 14); substantive provisions were not relabeled to force closure.
- The producer parses the selected modules rather than hand-listing inputs. It
  finds 11 qualified `#input` slots representing 9 logical inputs. All are
  grounded, and the 5 uncaptured frontier inputs name personskatteloven §§ 7,
  14, and 20, pensionsbeskatningsloven § 16, and Danmarks Statistik CPI.
- `frontier.complete=true` and non-encoded reasons are complete, but
  `partially-encoded=1` and `pending=12`; therefore the producer correctly
  computes `closed=false`.
- Artifact SHA-256:
  `2b0dc668fd560100b027685e294b80818e155f33c30c61ec3f883927c7f45dd7`.

The closure mutants cover a dropped ledger row, a hidden pending row, a
removed frontier input/grounding decision, coordinated generated-spine
truncation, dirty and untracked corpus releases, stale/missing module source
hashes, an unknown classification status, mutable-ref races, coordinated
proof-atom hiding, missing proof validation, fake atom paths, and fabricated
corpus excerpts.

## WS3 — executable producer

Added `scripts/executable_reproduction.py` and
`conformance/executable/dk-boerne-og-ungeydelse.json`.

- Both composed programs compile through `AxiomRulesRunner`'s canonical
  `compile-composed` contract from an archived exact RuleSpec Git tree.
- Compiled artifacts reproduce deterministically at:
  - single-recipient pipeline:
    `cbe3bdfaf2d7a735c11cbe22d4bcb04065ee698325421c372a46eb1b4ff50a49`;
  - couple pipeline:
    `6e9c9e6b4ca8e2d6dfed5795671bc5c54ec5d83156048d7dc9b2aee02d2dfae4`.
- The producer reconstructs the committed 8 + 1 + 1 case inputs, including the
  report's exact floating tails and the couple's two committed earner bridge
  overlays, runs all ten cases, and uses exact JSON numeric equality.
  All 10 reproduce, including `11497.333333333334`; `executable=true`.
- This receipt claims the ten requested comparison cases only. It does not
  overclaim separate golden companion fixtures mentioned in the design note.
- Artifact SHA-256:
  `0cb850b895d57fc29aaf290dd937a662798f529459130f70eb8cfaf3a360d1e9`.

The executable mutants coherently tamper with a committed value, reject mutable
RuleSpec refs, and prove that `--check` replays the recorded commit before
turning red. Certification mutants additionally prove that a forged
compiled-artifact hash cannot pass the opt-in full producer-verification gate.

## Certification wiring and result

`scripts/certify.py` now preserves the US-CO attested path while giving DK two
producer-backed premises. Its ordinary CI path hermetically validates each
committed artifact and its in-repo report/config inputs. The explicit
`--verify-producers` integration gate additionally requires closure to
re-derive from the corpus and RuleSpec Git blobs and executable to recompile
and replay with the pinned engine before producing the same certificate bytes.
Both evidence rows carry the committed artifact path, SHA-256, and
`verification: producer_artifact_validation`; the full checks remain explicit
integration gates rather than an unportable claim in the receipt.

The regenerated DK certificate reports:

| premise | mode | value |
|---|---|---:|
| conformant | computed | true |
| exercised | computed | true |
| closed | computed | false |
| executable | computed | true |

Consequently `certified.value=false` and `certified.state=no`. This is the
intended honest result: every required premise is now offerable and computed,
but closure is not yet true. The generic rule text was updated accordingly;
US-CO remains `state=unavailable` on its unchanged attested closed/executable
path.

## Verification

- Closure producer full `--check`: **up to date**, `closed=false`, 2 encoded,
  1 partially encoded, 12 pending, frontier complete.
- Executable producer full `--check`: **10/10 exact JSON numeric equality**,
  `executable=true`; a live temporary-clone check also passed after `main` was
  moved away from the receipt's recorded commit.
- Exercise census, scoreboard, ordinary hermetic certificate checks, and
  `certify.py --check --verify-producers`: **all exit 0**. Global manifest
  `--strict` intentionally exits 1 on the four genuine CO findings; all three
  DK manifests independently validate with zero errors and findings.
- Focused certification, manifest, closure, and executable mutants:
  **69 passed** after the final review cycle.
- Required DK/disposition selector: **108 passed, 2,531 deselected**.
- `ruff check .`: **all checks passed**.
- Newly affected closure/executable files were Ruff-formatted; `certify.py`
  retains the repository's pre-existing formatting outside edited sections to
  avoid unrelated churn.
- Independent reviews found and drove fixes for corpus working-tree trust,
  RuleSpec ref races, stale source hashes, arbitrary classification statuses,
  shape-only integration verification, and accidental coupling of ordinary CI
  to an arm64 macOS engine. The post-fix producer reviews are clean; final
  integrated review is recorded before commit.

## Audit fix addendum — 2026-08-15

This addendum supersedes the original WS2/WS3 counts, hashes, replay semantics,
and launch status above.

- Status strings no longer promote attested registry blocks. With both producer
  configs removed, attested `closed` and `executable` blocks carrying
  `{status: computed, value: true}` still emit `mode=attested`, and
  `certified.state=unavailable`.
- Bridge bindings can target named records. The couple manifest declares the
  two income-basis inputs as bridged only for `earner` and as explicit constant
  zero for `non_earner`; suite mutations to `777` produce findings. Aggregate
  constants are also checked across every record.
- Every non-synthetic population requires `pin_required: true` plus a typed,
  non-empty revision and full lowercase SHA-256 identity. The coordinated
  `populace-us` / `pin_required: false` / no-identity mutant reds, as do boolean
  pseudo-identities.
- All three DK manifests distinguish logical and execution periods. For the
  2023 witness those are `2023` and `2025-06-01`; the validator binds the latter
  to `euromod-synthetic-compare`'s actual `runner.parameters.period` and rejects
  dashboard or `year` fallbacks.
- Corpus-root composed proof atoms now join the closure spine. Four validated
  § 5 atoms make it `partially-encoded`, cite the couple module, and reduce
  pending from 13 to 12 without changing `closed=false`. Atoms require
  `proof_validation.required=true`, a real version formula path, and an excerpt
  present in the pinned provision body.
- The executable receipt records `ref=sha=9986b6035c4e557b9b40645dfe2f3e4cffb6037c`.
  Generation may resolve a branch once, but validation, CLI checks, and full
  certification replay the recorded commit.
- Global `--strict` again returns nonzero for any finding, regardless of a
  manifest's `strict` metadata. Its current failure is honest: CO lacks a
  report-bound population identity, has three partial mixed-kind bindings, has
  unverified completeness, and cites one cross-repository evidence path.
- Executable comparison language now says “exact JSON numeric equality.” The
  former byte-oriented wording is gone from tracked files.

Regenerated artifact SHA-256s:

- closure: `2b0dc668fd560100b027685e294b80818e155f33c30c61ec3f883927c7f45dd7`;
- executable: `0cb850b895d57fc29aaf290dd937a662798f529459130f70eb8cfaf3a360d1e9`;
- exercise census: `8d948559364a150808312087527289e02d52320740078912fda887814e4f45d5`;
- DK certificate: `af40d0c3f19a53f65f6247f80fefe8ef097ca5259bad10cfd9e8bdcffd30519f`;
- CO certificate, refreshed only for the census hash:
  `58b257b719f3cd2cdad0cee8f485fea958a0279c2f125b6e555912e19e617d30`.

The DK premise table remains:

| premise | mode | value |
|---|---|---:|
| conformant | computed | true |
| exercised | computed | true |
| closed | computed | false |
| executable | computed | true |

The remaining repository-wide launch blocker is CO recertification. Its
historical report dropped the population identity sidecar and does not contain
the complete submitted input catalog, so those findings cannot be safely
backfilled from current committed evidence.
