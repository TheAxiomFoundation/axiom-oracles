# DK closed and executable producers (WS2 + WS3)

Status: **SHIP-READY — all four DK certificate premises are now computed:
`conformant=true`, `exercised=true`, `closed=false`, and `executable=true`.
The truthful final result is `certified.state=no` because 13 substantive
paragraffer remain pending; it is no longer `unavailable`.**

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
  and the merged guard branch. Both producers therefore honestly record the
  locally reproducible `main` commit `9986b603...`; no unavailable SHA was
  fabricated.
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
- The ledger result is 2 encoded (§§ 1 and 1 a), 1
  classified-with-reason (§ 4), 8 excluded-with-reason, and 13 pending.
  Exclusions are limited to defensible administrative/appeal/repealed/penalty/
  public-finance/delegation/commencement provisions (§§ 4 d, 6, 6 a, 7, 9,
  12, 13, and 14); substantive provisions were not relabeled to force closure.
- The producer parses the selected modules rather than hand-listing inputs. It
  finds 11 qualified `#input` slots representing 9 logical inputs. All are
  grounded, and the 5 uncaptured frontier inputs name personskatteloven §§ 7,
  14, and 20, pensionsbeskatningsloven § 16, and Danmarks Statistik CPI.
- `frontier.complete=true` and non-encoded reasons are complete, but
  `pending=13`; therefore the producer correctly computes `closed=false`.
- Artifact SHA-256:
  `2f996c63efd92a84a1666b044910a050dca5f5ce7598fef6f83d08c44a021514`.

The closure mutants cover a dropped ledger row, a hidden pending row, a
removed frontier input/grounding decision, coordinated generated-spine
truncation, dirty and untracked corpus releases, stale/missing module source
hashes, an unknown classification status, and mutable-ref races.

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
  overlays, runs all ten cases, and compares JSON numeric values exactly.
  All 10 reproduce, including `11497.333333333334`; `executable=true`.
- This receipt claims the ten requested comparison cases only. It does not
  overclaim separate golden companion fixtures mentioned in the design note.
- Artifact SHA-256:
  `9c9f89911030f08f30fc6e9793e6dce7f45281eabd2811950f19141bd374d818`.

The executable mutant coherently tampers with a committed value and proves
that `--check` reruns before turning red. Certification mutants additionally
prove that a forged compiled-artifact hash cannot pass the opt-in full
producer-verification gate.

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

- Closure producer full `--check`: **up to date**, `closed=false`, 13 pending,
  frontier complete.
- Executable producer full `--check`: **10/10 exact**, `executable=true`.
- Exercise census, strict bridge manifests, dispositions, ordinary hermetic
  certificate checks, and `certify.py --check --verify-producers`: **all exit
  0**. An empty-`HOME` regression test proves the ordinary certificate check
  does not depend on sibling checkouts or the macOS engine. The strict bridge
  command still prints the four pre-existing non-strict CO findings and
  reports zero findings for all three strict DK manifests.
- Closure mutants: **14 passed**.
- Executable mutants: **3 passed**.
- Full-verification certificate mutants plus the hermetic-CI regression:
  **3 passed**.
- Required DK/disposition selector: **107 passed, 2,513 deselected**.
- `ruff check .`: **all checks passed**.
- `ruff format --check` on the six producer/test Python files: **all
  formatted**. (`certify.py` retains the repository's pre-existing formatting
  outside the edited sections to avoid unrelated churn.)
- Independent reviews found and drove fixes for corpus working-tree trust,
  RuleSpec ref races, stale source hashes, arbitrary classification statuses,
  shape-only integration verification, and accidental coupling of ordinary CI
  to an arm64 macOS engine. The post-fix producer reviews are clean; final
  integrated review is recorded before commit.
