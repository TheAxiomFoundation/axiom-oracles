# Tariff evidence continuation handoff

[Draft PR #532](https://github.com/TheAxiomFoundation/axiom-oracles/pull/532)
contains the preserved milestone and continuation on
`sprint/tariff-evidence-continuation-20260907`. The worktree is
`/Users/maxghenis/TheAxiomFoundation/_worktrees/tariff-evidence-continuation-20260907`.
Verified live main `82d342793d939b3bb11e9a2d50d3fb0b3bc57622` is integrated.
The original clean milestone `a7d2bf13af1b64fa20695e7347e933c76f5efe2c` and its
branch/artifacts remain unchanged.

**Bounded evidence is complete for all 21 original gaps; legal closure is not.**
The continuation genuinely adds 15 source-linked scopes to the original six:

| Continuation receipt | New scopes | Real cases | Returned outputs | Outcome limit |
| --- | ---: | ---: | ---: | --- |
| `note52-transit-usmca.json` | 2 | 230 | 690 | 20 first-minute safe-harbor counterexamples |
| `hts-identity.json` | 4 | 63 | 189 | Canonical controls match; nine raw aliases differ |
| `china-action.json` | 2 | 36 | 36 | Four actual-adapter counterexamples |
| `temporal-boundaries.json` | 2 | 43 | 43 | Two activation counterexamples; CSPV post-expiry only |
| `china-lists.json` | 2 | 18 | 18 | One duplicate China beer charge |
| `column2-resolution.json` | 1 | 41 | 29 | 12 native errors; no legal resolved rates validated |
| `primary-metals.json` | 2 | 28 | 44 | Three UK metal-qualification counterexamples |
| **Continuation total** | **15** | **459** | **1,049** | **30 legal counterexample cases across seven scopes** |

Across the 21 scopes, 12 have no legal counterexample under their bounded
contracts, seven have counterexamples, one is post-expiry-only, and one is
diagnostic-only. **All 58 actual-entry groundings remain uncaptured; fully
admitted scopes remain zero.** Cases are synthetic/diagnostic projections, not
actual customs transactions. Component rates are not total duty estimates.

## Source evidence and reproducibility

Live USITC Rev15 and GPO PDFs are committed with authoritative URLs, actual
retrieval metadata, sanitized HTTP records and hashes. The Chapter 99 bytes
exactly match the original frozen PDF. The actual original Ed25519 ingest
signature now verifies with the canonical pinned corpus verifier and the
repository's actual public trust root. This closes that original authentication
blocker only; new raw source captures are unsigned and no GPO PDF signature
verification is claimed. See `boundary-evidence/live-sources/receipt.json`.

Every changed-scope producer's `--check` executed the real pinned Axiom Rust
engine and reproduced its exact receipt. **46 targeted continuation tests
pass:** 36 source/receipt tests and 10 combined replay tamper/native-outcome
tests. The earlier milestone's 351 passing targeted tests remain a separate
historical result. Full repository CI was not rerun or claimed green.

The distinct standalone `tariff-continuation-replay.tar.gz` is **45,356,596
bytes**, containing 78 files. Eight fresh pinned compilations match the receipt
hashes. Independent extraction and Python `-I -S` replay reproduced **843 cases,
1,817 returned outputs and 12 native missing-input errors**, including the
unchanged original 384 cases/768 outputs. This proves reproducibility of known
counterexamples, not their legal correctness. Requires macOS arm64/Python 3.10+.
No network, project environment, site packages or campaign cache is needed.

Archive SHA-256:
`4b913f987afb7db5910dbddb62f623049047d284dc2bee8669ee6bae83f65eff`.
Verify this trusted archive hash before extraction/executing its verifier.
Manifest trust anchor:
`f4e9257e0e121ebbc0e5cc47adc3c443aa4f9bdd5994d30620253fb6f42c99aa`.
The exact command and limits are in [the blocker handoff](CONTINUATION-BLOCKERS.md).
The committed `continuation-replay-manifest.json` records every packaged hash.
Original replay archive SHA remains
`953cdff08d2ad068ef5e6914c683c73ad01ce5ccdd6acf6046cfe1907e1af016`.

## Preserved state and open gates

The final preservation audit verifies all 27 original dirty files, their exact
status/binary diff, all 23 original lane artifacts, the clean original milestone,
and clean RuleSpec head `4f591c4267063094cc6da9d590872ea982940b81`. CAFTA 17,404,
steel 114, residual 5,733 and selector 216,111,132-unit proof bytes are unchanged.
The steel proof retains its input-comparability scope. **Zero campaign rows
were rescanned.**

Current main changes comparator/report semantics relative to the historical
proof. Its source-change admission gate correctly expires: the canonical tariff
certificate remains **conformant=false, exercised/executable=true, closed=false,
certified=false**. The current-base conflict was resolved with the canonical
certificate producer; both inherited tariff census rows reproduce and the
other 225 rows match refreshed main. Do not repin or discard frozen proofs to
remove this hold. See `continuation-integration-hold.json` and the source/file/
line findings in [CONTINUATION-BLOCKERS.md](CONTINUATION-BLOCKERS.md).

The draft head uses `[skip ci]` to avoid launching remote jobs. GitHub reported
zero workflow runs for the verified pushed head; required checks remain pending.
No PR merge, activation or release occurred. Final Fable review is pending for
root to arrange through existing capacity. The prior review failed before
execution; no continuation account probe, retry, reset or overflow was launched.
Max's existing publication/admission conditions remain required.

Next: root can arrange one bounded Fable review of the exact final draft head.
Then use the source/file/line findings for authorized timestamp, membership,
composition and metal-provenance repairs, with meaningful targeted replay.
Column 2 must stop until valid-vintage transaction/resolver evidence exists;
CSPV active-period claims need a suitable vintage program and quota/source
chain. Actual-entry grounding and historical-proof admission require separate
real evidence/authority. No unsupported source, signature or certificate may
substitute for those gates.

Durable lane artifacts are in
`/Users/maxghenis/capacity-sprint-20260907/tariff`: the new and old replay
archives, incremental Git bundles, source captures, original dirty snapshot,
validation/preservation logs, draft PR body/live verification, prepared Fable
brief, artifact manifests and `continuation-result.md`. The detailed final
report is also retained as `continuation-handoff.md` in case the runner replaces
the last-message output. Both no-reset controls remain preserved; their block
has no automatic expiry.
