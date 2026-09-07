# Tariff evidence sprint handoff — September 7, 2026

Bounded evidence/reproducibility work is complete on
`sprint/tariff-evidence-20260907`, isolated at
`/Users/maxghenis/TheAxiomFoundation/_worktrees/tariff-evidence-20260907`.
The implementation checkpoint is `10972f34dd6e884f0f9645dfc9445751d3e31ed3`.
**Closed and certified remain false. Final Fable review remains pending.**

## Delivered

- Preserved the exact unfinished frontier rebuild on a reviewable branch.
  All 27 original dirty files, original status and binary diff remain identical;
  the original checkout and clean RuleSpec head `4f591c4267063094cc6da9d590872ea982940b81`
  were not modified. The original CAFTA 17,404-unit, steel 114-unit, residual
  5,733-unit and selector 216,111,132-comparison-unit proof bytes are unchanged.
- Inventoried the frontier: the prior rebuild already repaired all 21 missing
  descriptions, giving 58/58 named scopes. All 58 actual-entry groundings remain
  uncaptured. Captured source-linked evidence for six of those repaired scopes:
  donation, informational materials, accompanied baggage, Chapter 98 claim,
  CBP agreement and the 9802 carve-out. The other 15 have explicit requirements
  in [the evidence handoff](README.md).
- Bound the archived authoritative USITC Rev-15 Chapter 99 PDF, pages 176 and
  598, to exact corpus records and hashes. Executed real pinned Axiom Rust
  compile/run-compiled for all 64 Boolean combinations, China/Hong Kong/France,
  two compositions, exactly February 16, 2026: **384 synthetic cases and 768
  outputs matched**, including 28 positive-rate cases. No actual-entry legal
  eligibility or historical-vintage completeness is inferred.
- Fixed the regular-file compiler portability failure and repaired 39 stale
  ledger hashes plus three classification input hashes. Preserved immutable
  original audited baselines, all classifications, sidecar bindings and
  population accumulators. A mandatory metadata-only gate proves the exact
  transformation. Canonical tariff certificate and census now reproduce:
  conformant/exercised/executable true; closed/certified false. Other 226 census
  suite rows are unchanged. **Zero new campaign rows were scanned.**
- Recovered and committed the exact missing 10,088,070-byte historical artifact.
  All 202 proof file bindings are present: **190 small-file hashes match; 12
  large files are present without rehashing**. Prior large-file verification
  was preserved, not renewed.
- Built a standalone 15,577,166-byte offline replay archive containing sources,
  compiled programs, requests, complete expected responses and the pinned real
  executable. It reproduced all 768 outputs with Python isolated mode, site
  packages disabled and no project imports. Requires macOS arm64/Python 3.10+.

## Validation and artifacts

[Validation receipt](validation.json) records **351 passing tests across six
separate targeted groups**, 101 real compilation checks, canonical certificate/
census reproduction and preservation checks. The existing executable receipt
also reproduced its ten recorded witness values. This is not a claim that a
full repository test suite or the huge campaign was rerun.

Key committed artifacts:

- [Source-linked runtime receipt](../../reference/us-tariff-schedule/boundary-evidence/note2-exceptions.json)
- [Frontier inventory](../../reference/us-tariff-schedule/boundary-evidence/frontier-inventory.json)
  and [reproduction inventory](../../reference/us-tariff-schedule/boundary-evidence/reproducibility-inventory.json)
- [Metadata rebind receipt](../../reference/us-tariff-schedule/publication-metadata-rebind.json)
  and [regenerated tariff certificate](../../certificates/us-tariff-duty.json)
- [Offline replay manifest](../../reference/us-tariff-schedule/boundary-evidence/offline-replay-manifest.json)

Durable lane artifacts are at `/Users/maxghenis/capacity-sprint-20260907/tariff`:
`tariff-boundary-replay.tar.gz`, `tariff-evidence.git.bundle`, the original dirty
snapshot, recovered historical file, source page renders, test logs, review
brief/failure and final preservation audit. The Git bundle is incremental from
original head `83908413e68f551f83c61fbbd891409a567bf5ee`; retain that prerequisite.

Offline archive SHA-256:
`953cdff08d2ad068ef5e6914c683c73ad01ce5ccdd6acf6046cfe1907e1af016`.
After extraction, use the separately committed manifest trust anchor:

```sh
python3 verify.py --verify-bundle . --manifest-sha256 \
  ffaba0ea667d0562ceada755678eb12dd654a71c3e2152d8efe700756e6c8ad5
```

## Commits

- `5673d70e8` — preserve the exact unfinished rebuild and start PROGRESS.md.
- `6df4a2d9c` — regular temporary compiler artifact portability.
- `e29386fd2` — six source-linked exception scopes and real runtime evidence.
- `50571577e` — frontier/reproduction/downstream gap inventories.
- `6d608bba3` — preserve audited measurements through exact metadata rebind.
- `2b8f28b6d` — standalone offline replay and tamper checks.
- `10972f34d` — restore the original historical reproduction artifact.

## Blockers, risks and next action

One bounded read-only Subfleet Fable review was attempted:
`20260907-172639-tariff-evidence-fable`. It failed before review, exit 5:
`no keychain token for max.ghenis@gmail.com (claude-quota-max.ghenis@gmail.com)`.
No review pass is claimed. Retry this prepared review through an authorized
existing subscription lane once token access is available, then fix actionable
file/line findings. Review must cover the final branch, including the offline
bundle and historical recovery added after the failed dispatch.

GitHub fetch failed with `Could not resolve host: github.com`. Current upstream
integration and a draft PR remain blocked; cached origin/main is not presented
as a verified live base. Once network access returns, fetch and safely reconcile
main, reproduce the narrow gates, and prepare the draft PR. No push, merge,
publication or messages to people occurred.

The original ingest signature is preserved and applied-file hashes match, but
trusted-key signature verification remains open: the corpus Actions variable
`AXIOM_CORPUS_INGEST_PUBLIC_KEY` is unavailable in this environment. No key was
substituted. The 15 remaining repaired scopes, 13 partial/pending source
families, subordinate-instrument census, typed law-derived dependencies and
real-entry transaction evidence remain separate closure work. See the explicit
scope table in README.md; source snapshots cannot certify those facts.

Final Fable review and existing release conditions remain mandatory. Launch
runbook Gates 2–3 still require Max's prebrief/contact and explicit publication
go. This sprint does not satisfy or bypass them. No reset, overflow, credits,
new paid API or remote compute jobs were used; `auto_reset.enabled=false` and
`no-reset.json` remain preserved, with no automatic expiry.
