# SNAP concept-citation relabeling — final report

## Status

The relabeling, verification, tests, corpus audit, and ops provenance-pin update
are complete and committed locally. Remote publication could not be completed
from this environment: both authorized non-force Git pushes fail with
`Could not resolve host: github.com`. A read-only GitHub connector search
confirms that `fix/snap-concept-citations` is not present remotely and no PR
exists for it; the connector's attempted Git-data write was cancelled. Nothing
was merged.

## Independent no-number verification

Before committing the already-applied change, I independently enumerated all
112 affected tracked files. For each file I read its committed pre-change blob,
performed exactly these two byte substitutions in memory, and compared the
result byte-for-byte with the working file:

- `us:statutes/7/2014/u#snap_benefit` → `us:programs/snap#benefit`
- `us:statutes/7/2014/o#snap_eligible` → `us:programs/snap#eligible`

All 112 comparisons matched. As a separate check, I normalized both the old
and new IDs to common sentinels and compared the complete before/after bytes;
again, all 112 matched with zero anomalies. Therefore no other byte—including
any numeric value—moved in the applied relabeling.

The change covers 8,024 distinct physical lines. Those lines contain 63,826
literal substitutions (32,560 benefit and 31,266 eligibility); many report
rows are minified onto single lines.

The test suite subsequently exposed 13 stale `overview.json` source-byte
counts because each new ID is nine bytes shorter. I regenerated that overview
metadata only and verified its non-`sources` content stayed equal. These are
file-integrity byte counts, not comparison or model values. No conformance or
comparison suite was run.

## Test outcome

The requested command was run through an offline, writable mirror of the
machine's existing uv cache:

```bash
uv run --with pytest --with pandas python -m pytest tests/ -q
```

The first run had 1,996 passed, 59 skipped, and 3 failed. The
rename-caused refreshed-report no-op failure was traced to the 13 byte-count
metadata fields above and fixed without executing a comparison.

The final full run had **1,997 passed, 59 skipped, and 2 failed**. Both remaining
failures reproduce on `origin/main`:

- `test_oh_2026_exact_mappings_match_the_rulespec_output_set`: the local
  rulespec-us checkout lacks four expected `*_source_hold_applies` outputs.
- `test_loader_equivalence`: `npx esbuild` cannot reach npm
  (`ENOTFOUND registry.npmjs.org`).

No unrelated failure was changed.

## Further citation audit

I audited all statutory/regulatory concept IDs in
`axiom_oracles/core/case.py` and
`axiom_oracles/config/concept_mappings.yaml` against both corpus commits pinned
by the committed SNAP reports, then checked current corpus `origin/main`.
Across 26 occurrences (22 IDs, 17 provision prefixes), 10 prefixes resolve
exactly and 6 payroll prefixes resolve through exact parent-section rows.

One further citation does not resolve:

- `us:statutes/42/1786#wic_eligible`
  - `axiom_oracles/core/case.py:116`
  - `axiom_oracles/config/concept_mappings.yaml:2143`
  - `axiom_oracles/config/concept_mappings.yaml:2149`

It is absent at both operational corpus pins and current corpus `origin/main`.
It was reported only and left unchanged as requested.

## Ops provenance pin

All three post-relabeling report hashes were recomputed directly:

| Report | sha256 | Result |
|---|---|---|
| `axiom-policyengine-co-snap-ecps.json` | `4be1a737a517ef65719c336395bfa458b1ee298c2b4816e628400af6a9224219` | changed |
| `axiom-snapqc-co-snap.json` | `bc2cd881116c0d2a67ee2a587fbd4c850975fb784f8e93338df60801c4235385` | unchanged |
| `axiom-policyengine-fiit-ecps.json` | `7caca46fc19e19609ca04d319d9e73d832da13d67901dc325329430d9043f51d` | unchanged |

Only the first file contains the relabeled concept. The update to
`launch-readiness/PUBLISHED-NUMBERS-PIN.md` records all three recomputed values,
the new source commit, the new concept label, and that this was a citation-only
change with no numeric change or suite re-run. Its published-number tables are
unchanged. The separate ops worktree commit is `7b507d2`.

## Publication links and blocker

- axiom-oracles branch (not yet published):
  <https://github.com/TheAxiomFoundation/axiom-oracles/tree/fix/snap-concept-citations>
- axiom-oracles PR: not created, so no truthful PR URL exists. Once the branch
  is pushed, the creation page is
  <https://github.com/TheAxiomFoundation/axiom-oracles/compare/main...fix/snap-concept-citations?expand=1>.
- ops existing PR #7:
  <https://github.com/TheAxiomFoundation/ops/pull/7>
- ops branch:
  <https://github.com/TheAxiomFoundation/ops/tree/launch/provenance-pin>

The ready ops worktree is
`/private/tmp/ops-provenance-pin.Pkye5e/worktree`. Publication requires only
normal non-force pushes once GitHub DNS/connectivity is available; the axiom PR
should reference #401, describe the pure relabeling and unchanged model
numbers, and note that the launch freeze in ops PR #7 prohibited comparison
suite re-runs.
