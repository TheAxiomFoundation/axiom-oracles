# Executable producer final report

## Outcome

The executable premise now has a fail-closed computed producer and consumer.
No receipt or Sigstore bundle is fabricated in this branch, and the initial
workflow allowlist is empty, so the committed `us-co-snap` certificate remains
honestly red until the governed workflow lands and produces authenticated
evidence.

The implementation is standalone from the parked evidence-validator branches
#378 and #379. It adds one new workflow and does not modify any existing
workflow, toolchain file, dependency pin, or CODEOWNERS.

## Design

The new `Executable receipt` workflow has two capability-separated jobs:

1. `produce` has `permissions: {}`. It anonymously fetches the exact public
   source SHA, downloads the pinned released `axiom-rules-engine` archive,
   verifies the archive checksum and engine version, downloads the published
   program-artifact manifest and artifact, verifies both content hashes, and
   invokes the released binary's public `run-compiled` command with the
   committed golden request. The producer accepts no engine, artifact,
   manifest, or repository override.
2. `sign` is the only job with `id-token: write` and `attestations: write`. It
   receives only the completed receipt, runs no repository or engine code,
   re-checks the receipt's immutable GitHub run fields, attests the exact
   receipt bytes, and retains the receipt and Sigstore bundle together.

The certifier reads only the committed output paths. It verifies the bundle
offline with `gh attestation verify`, a byte-pinned public-good Sigstore root,
the exact workflow identity, signer digest, source digest/ref, hosted-runner
restriction, and repository identity. It then independently checks the
verified certificate fields, receipt subject digest, transparency timestamp,
release/checksum membership, published artifact hashes, exact command records,
golden input bytes, strict output JSON types, and pinned values. An allowlisted
workflow SHA without that authenticated bundle cannot pass.

The pinned execution is:

- engine release: `v0.1.1`
- target: `x86_64-unknown-linux-gnu`
- engine archive SHA-256:
  `09bacb1b22805bfb5f9303ac53c79189e8ff3c7866e653c2f3a12b9dbb07b400`
- artifact release: `program-artifacts-59a10dab866e`
- artifact SHA-256:
  `ed76001985e5d5bdcec6b3d3d3f820b0af40f106892a4ad7d8d8eb6eb1940220`
- expected outputs: `478`, `226`, and `holds`

## Receipt schema

The receipt schema identifier is
`axiom_oracles.executable_receipt.v1`. Its top-level fields are:

- `schema`
- `program`
- `engine`: repository, release, tag commit, semantic version, target, asset
  name, distribution-manifest hash, checksum-file hash, and archive SHA-256
- `artifact`: repository, release, published-manifest name and SHA-256,
  artifact name, and artifact SHA-256
- `golden`: case name, request path and raw SHA-256, parsed inputs, expected
  output-binding path and raw SHA-256, and exact typed outputs
- `commands`: every stranger-path argv vector, exit code, and the engine
  command's stdin SHA-256
- `timestamp`: UTC RFC 3339 producer time
- `workflow`: repository, immutable repository ID, workflow path and SHA,
  source SHA, run ID, run attempt, event, and ref

The separate `receipt.sigstore.json` bundle is mandatory evidence. The receipt
JSON alone is never sufficient.

## Fail-closed and mutant coverage

Constructed mutants reject:

- a wrong or unreleased engine checksum
- an engine, artifact, or manifest supplied through a producer escape hatch
- output values or JSON types that differ from the golden bindings
- missing, copied, malformed, or inconsistent workflow provenance
- a hand-authored allowlisted receipt with no valid bundle
- a receipt changed after signing
- a wrong repository, repository ID, workflow identity/SHA/ref, source
  digest/ref, event, run ID/attempt, hosted-runner identity, timestamp, or
  signed subject digest
- a mutated trusted root, duplicate JSON keys, malformed verifier output, or a
  parsed-object attempt to bypass exact-byte authentication

Three independent adversarial/integration reviews found no viable receipt,
bundle, certificate, workflow-boundary, or certifier-integration bypass.

## Validation

- Focused executable producer/validator/certifier suite: **84 passed**.
- Full repository suite: **2,387 passed, 70 skipped, 1 failed**. The sole
  failure was
  `tests/test_dashboard_loader.py::test_loader_equivalence`: this fresh
  worktree has no `node_modules`, and `npx esbuild` attempted a blocked npm DNS
  lookup. Running the test's exact bundle-and-compare sequence with the
  already-cached esbuild binary returned `EQUIVALENT: true` and zero legacy
  leftovers.
- `scripts/certify.py --check`: certificates up to date.
- `scripts/exercise_census.py --check`: exercise census up to date.
- `actionlint` on the new workflow: passed.
- Ruff, targeted Python compilation, and `git diff --check`: passed.
- Wheel and sdist builds with the cached Hatchling build environment: passed.
  The validator module is packaged, but its default trust assets and certifier
  are intentionally repository-local rather than a standalone wheel API.

## Maintainer handoff

The workflow PR must receive the required cross-family signing/CI agreement
and maintainer approval before merge. After the exact workflow lands on
`main`, a maintainer must:

1. dispatch a fresh `Executable receipt` run on `main`;
2. download the final `executable-receipt-us-co-snap` artifact;
3. perform the documented offline verification and compare the authenticated
   run metadata;
4. copy the receipt and bundle byte-for-byte to their declared paths;
5. through the separate governance step, allowlist only the authenticated
   `workflow.sha`;
6. regenerate and check the certificate, then let the certified-nodes
   critical path consume the computed result.

The ops parity fixture's `_provenance` prose predates repairs already present
in its actual bytes; those bytes and the published release produce the pinned
green tuple. Cleaning up that upstream prose is useful but is not a trust input
or a blocker for this producer.

## Publication

The requested local work is committed in the fresh worktree on
`autogo/executable-producer-rebuild`, intended for remote ref
`autogo/executable-producer`. Both `git fetch origin main` and the exact
non-force push failed because this environment could not resolve
`github.com`. The GitHub connector confirmed that the requested remote branch
does not already exist, but its blob/tree write endpoint rejected both
publication attempts before creating any Git object or branch. Therefore no
draft PR was created.

A maintainer with GitHub network access can publish the exact committed state
from this worktree with:

```bash
git push -u origin HEAD:refs/heads/autogo/executable-producer
gh pr create \
  --repo TheAxiomFoundation/axiom-oracles \
  --base main \
  --head autogo/executable-producer \
  --draft \
  --title \
    "Executable producer: sign-only CI receipt for the autogo harness" \
  --body \
    "Adds the computed executable-receipt producer and fail-closed consumer on the certified-nodes critical path. The new signing/CI workflow requires cross-family agreement and maintainer approval before landing."
```
