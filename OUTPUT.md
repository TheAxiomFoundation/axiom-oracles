# WIC citation-label final report

## Outcome

Implemented option (a): the public WIC eligibility concept is now
`us:programs/wic#eligible`, rather than the statute-shaped
`us:statutes/42/1786#wic_eligible`.

That is the honest label while 42 USC 1786 is absent from axiom-corpus. The
engine address remains a separate concern: `targets.axiom` now names the real
current RuleSpec output
`us:policies/usda/wic/eligibility_pipeline#wic_eligible`. PolicyEngine remains
`is_wic_eligible`, and ACCESS NYC remains `S2R022`.

The impact trace confirmed that `ProgramMapping.standard` is the canonical
selection/report label, while engine runners and comparisons project it through
the per-engine targets. `Concepts.WIC_ELIGIBLE` has no direct call sites, and no
tracked comparison report contains the old WIC ID. The only tracked generated
consumer was `dashboard/public/data/programs.json`; its WIC row now reports the
real RuleSpec pipeline and its federal coverage.

One pre-existing limitation remains: the default CLI composition helper infers
RuleSpec imports from canonical concept labels. It was already unable to run
WIC because no `42/1786` RuleSpec module exists; the normal mapped output lookup
now resolves correctly through `targets.axiom`. Generalizing the import planner
to use mapped module targets would be a separate, wider composition change.

## Verification

- Focused regression:
  `.venv/bin/python -m pytest tests/test_case_schema.py -k wic_program_label -q`
  → 1 passed, 46 deselected.
- Isolated dashboard generation using the WIC mapping and current
  `rulespec-us` WIC module reproduced the committed WIC row exactly.
- Dashboard overview check remained current at 215 bundled reports.
- No comparison suite was run or regenerated.

The byte-level proof started from implementation parent `14eeb9c0` and applied
only the declared WIC substitutions to each production file. The transformed
bytes exactly equalled the working files:

- `axiom_oracles/core/case.py`:
  `728d74d8092641c11e1c775c8214573ca6bc531acb6b2518aec06b614644fb5a`
- `axiom_oracles/config/concept_mappings.yaml`:
  `7b143530e33d85f559f97056f8fc3055cdfb928f7e9a614a87db99296d7ddfa9`
- `dashboard/public/data/programs.json`:
  `d7ba510cb1d8a8896305ad619d9b40d059cfce0007520f92de78183561b66fd4`

An independent structural check found every non-WIC dashboard row
byte-equivalent after canonical JSON parsing, and every WIC field other than
the declared label/address/coverage fields equal. Thus no numeric or null
value changed. Git also found no byte changes under `comparisons/`,
`dashboard/public/data/axiom-*.json`, `dashboard/public/data/cases/`,
`dispositions/`, or `conformance/`.

The PR #406 `uv run` command was attempted first, but its launcher exited before
test collection because this sandbox cannot write the uv cache. The one actual
full suite run was then performed with the existing environment and frozen:

`.venv/bin/python -m pytest tests/ -q`

Result: **2,096 passed, 59 skipped, 6 failed in 647.36 seconds**.

Five failures are bridge-contract checks that auto-selected the sibling
`rulespec-us` worktree at detached `c3e1c3ad`, behind its `origin/main`
`ecb057ef`. The affected California, Illinois, New York, and Ohio modules (plus
the Illinois fixture) all changed between those commits; two failures were in
Illinois. The sixth failure is `tests/test_dashboard_loader.py`, where `npx`
attempted to obtain absent local `esbuild` and DNS to `registry.npmjs.org` is
blocked. None of those test files or bridge mappings changed here, and no
failure concerns WIC. Per the freeze instruction, the suite was not rerun.

## Citation-path sweep

The scoped census of `axiom_oracles/core/case.py` and
`axiom_oracles/config/concept_mappings.yaml` found 30 occurrences, 24 distinct
full statute/regulation IDs, and 19 distinct provision prefixes. Every
inventory and provision record was checked against axiom-corpus `origin/main`
at `db12795577c5809009168982cf8a72fb58440620`.

After this WIC patch and the SNAP relabels owned by open PR #406, the complete
remaining non-resolving set is:

- `us:statutes/26/3111/a#employer_oasdi_excise_tax`
- `us:statutes/26/3111/b#hospital_insurance_employer_tax`
- `us-ma/regulation/106-cmr/364/360/block-1`
- `us-ma/regulation/106-cmr/365/030/block-1`
- `us-ma/regulation/106-cmr/366/140/block-1`

For the 3111 pair, the corpus contains the parent section but not the cited
subsection leaves. The Massachusetts trio is outside the two scoped concept
files and remains in its separate validation lane. These are the two
already-separated work groups identified by the prior audit.

Because this branch is based directly on `origin/main` while PR #406 is still
open, its raw tree also still contains the two SNAP 2014(o)/(u) IDs. They are
not a missed result of this sweep: PR #406 owns their relabeling. The five paths
above are the complete expected remainder after combining the two patches.

## Publication

- Branch: `z1-wic-citation`
- Implementation commit: `579228c0`
- Draft PR: pending
