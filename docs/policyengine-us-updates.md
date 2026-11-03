# Weekly PolicyEngine US update proposals

`policyengine-us-updates.yml` checks for a newer stable US model every Tuesday
at 08:23 UTC. It can also be dispatched manually from the default branch.
This complements PR #657's recovery of existing artifacts: the availability
check preserves old versions; this workflow proposes a newer default stack.

"Stable" means a PEP 440 final or post release, excluding pre-release,
development, and local versions. PyPI's file-level `yanked` flag must be false
for an eligible wheel. The probe chooses the highest eligible US release once,
selects a final wrapper release, and lets uv resolve compatible core/SPM and
transitive dependencies. It then removes yanked-file hashes from the resolved
lock for every dependency and installs the probe with `--require-hashes`.
These metadata checks do not establish model correctness.
The classification uses [`packaging.version.Version`](https://packaging.pypa.io/en/stable/version.html)
and [PyPI's file metadata](https://docs.pypi.org/api/json/); a final-version
label and an unyanked file are release-selection criteria, not test results.

`data/policyengine_defaults.json` records the wrapper, US model, core, and SPM
calculator used by generic in-repository comparisons. Suites with explicit
historical versions keep their existing environments and companion pins.
The orchestrator's optional `policyengine` extra remains a separate environment.
The default manifest initially preserves all existing versions. This workflow
does not migrate historical suites or remove their wrapper dependency.

The probe resolves a compatible candidate, records its package versions and
hashed requirements, and runs the reviewed default and candidate against the
same bounded cases. It retains `proposal.json`, `report.md`, and
`candidate-requirements.txt` as a run artifact. A failed resolution or execution
produces diagnostic evidence and opens no update PR. No available update also
opens no PR.
Finite singleton/batch differences already present in the baseline are retained
as explicit review evidence; they force `needs-review`. Missing outputs, failed
batch execution, ordering errors, and candidate singleton/batch disagreement
still prevent publication. This lets an update propose a working candidate even
when the historical baseline has a documented numerical inconsistency.

A completed probe can create a **draft** PR, including when its measured
amounts change and need review. The PR changes only the default manifest,
`requirements/policyengine-defaults.txt`, and a generated evidence summary under
`docs/generated/`. It never adjusts expected outputs, dispositions, historical
pins, or published comparison reports, and never enables auto-merge. The
bounded cases do not establish agreement for every suite that uses the default;
review amount changes and run affected comparisons before merging.

The evidence compares the same frozen synthetic inputs under two PolicyEngine
versions, not PolicyEngine against Axiom. It tests household calculations and
real Case batches against singleton Case calls. It uses the generic runner's
existing local-data certification override and supplies no population dataset;
it makes no dataset-certification or population-parity claim.

After an update is accepted, generic default runners consume the committed
requirements file to freeze its resolved versions. Future probes reuse that
same reviewed lock for the baseline. `uv run --with-requirements` does not
itself enforce artifact hashes; the isolated probe's `uv pip sync
--require-hashes` verifies the candidate artifacts. PR #657's verified artifact
recovery remains responsible for pruned historical files.

Candidate packages run in a read-only job without publication credentials.
The publisher starts from a fresh checkout of the same trusted commit and
accepts only validated JSON plus exact, hashed package requirements. It does
not execute downloaded artifact code or candidate dependencies. Existing open
automation PRs and existing version branches are left untouched, so weekly
runs do not overwrite review work.

Publication requires the repository setting that lets GitHub Actions create
pull requests. PRs created with `GITHUB_TOKEN` may require a maintainer to
approve their workflow runs. The retained proposal and run log remain
available if publication fails; no personal access token is required by this
workflow.
