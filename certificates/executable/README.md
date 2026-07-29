# Executable receipts

This directory is the fail-closed trust root for the program certificate's
`executable` premise. A receipt is computed evidence only when its exact bytes
are authenticated by the committed Sigstore bundle and every pinned value is
re-derived. A JSON document by itself is never evidence.

## Trust roots

- `engine-releases.json` pins released engine tags, tag commits, archive names,
  and full archive SHA-256 values.
- `us-co-snap/manifest.json` pins the published program-artifact release,
  release-manifest hash, artifact hash, golden request and output-binding
  bytes, receipt and bundle paths, workflow identity, immutable repository ID,
  and the Sigstore trusted-root hash.
- `sigstore-public-good-trusted-root.jsonl` is the public-good Sigstore root
  used for offline verification. It was taken from the Sigstore TUF
  `trusted_root.json` target on 2026-07-29, serialized as one JSONL record, and
  is byte-pinned by the executable manifest. Root rotation is a separately
  reviewed trust-root change.
- `workflow-allowlist.json` names exact workflow commit SHAs authorized under
  the separately governed producer protocol. It does not authenticate a
  receipt; the verified signing certificate must carry the same digest.
- `us-co-snap/receipt.json` and
  `us-co-snap/receipt.sigstore.json` are the inseparable output pair. If either
  file is absent or invalid, `executable` is false.

## Producer boundary

`.github/workflows/executable-receipt.yml` has two jobs:

1. `produce` has no repository, OIDC, or attestation permission. It anonymously
   fetches the exact main commit, downloads the pinned released engine archive
   and published artifact, verifies their release manifests and hashes, runs
   the golden request through the released binary's public `run-compiled`
   command, compares exact output types and values, and emits the unsigned
   receipt.
2. `sign` receives only that completed receipt. It runs no repository or engine
   code, re-checks the receipt's run fields, signs its exact bytes with GitHub's
   short-lived Sigstore identity, and uploads both the receipt and bundle as
   artifact `executable-receipt-us-co-snap`.

The receipt schema is `axiom_oracles.executable_receipt.v1`:

- `program`
- `engine`: repository, release, semantic version, target, asset, archive
  SHA-256
- `artifact`: repository, release, name, content SHA-256, published-manifest
  SHA-256
- `golden`: case name, input path, raw input SHA-256, parsed inputs, exact
  normalized outputs
- `commands`: exact argv, exit code, and the engine command's stdin SHA-256
- `timestamp`: UTC RFC 3339
- `workflow`: repository and immutable repository ID, workflow path and
  commit SHA, source SHA, run ID and attempt, event, and ref

`scripts/certify.py` validates the strict JSON schemas and hashes, invokes
`gh attestation verify` offline against the committed bundle and trusted root,
and checks authenticated certificate fields for repository ID, workflow
identity/digest, source ref/digest, event, run ID/attempt, hosted runner, and a
transparency timestamp. It then re-checks the certificate-owned
`478 / 226 / holds` golden expectations.

## Maintainer handoff

The initial workflow PR deliberately leaves the allowlist empty and commits no
fabricated receipt. The workflow file itself must first pass the required
cross-family signing/CI review and maintainer approval, then land unchanged on
`main`.

After it lands:

1. Dispatch `Executable receipt` from `main` and record its run ID.
2. Download the final evidence artifact without editing either file:

   ```bash
   gh run download RUN_ID \
     --repo TheAxiomFoundation/axiom-oracles \
     --name executable-receipt-us-co-snap \
     --dir /tmp/executable-receipt-us-co-snap
   ```

3. Verify before copying. `WORKFLOW_SHA` and `SOURCE_SHA` below come from the
   downloaded receipt:

   ```bash
   gh attestation verify \
     /tmp/executable-receipt-us-co-snap/receipt.json \
     --repo TheAxiomFoundation/axiom-oracles \
     --bundle /tmp/executable-receipt-us-co-snap/receipt.sigstore.json \
     --custom-trusted-root \
       certificates/executable/sigstore-public-good-trusted-root.jsonl \
     --predicate-type https://slsa.dev/provenance/v1 \
     --cert-identity \
       https://github.com/TheAxiomFoundation/axiom-oracles/.github/workflows/executable-receipt.yml@refs/heads/main \
     --signer-workflow \
       TheAxiomFoundation/axiom-oracles/.github/workflows/executable-receipt.yml \
     --signer-digest "$WORKFLOW_SHA" \
     --source-ref refs/heads/main \
     --source-digest "$SOURCE_SHA" \
     --deny-self-hosted-runners \
     --format json
   ```

4. Compare the receipt's repository, workflow, source SHA, event, ref, run ID,
   and attempt with `gh run view RUN_ID` and the run URL. Copy the two files
   byte-for-byte to their declared paths; never hand-edit them.
5. Through the separately governed approval, add only the authenticated
   `workflow.sha` to `workflow-allowlist.json`.
6. Regenerate and check:

   ```bash
   uv run python scripts/certify.py
   uv run python scripts/certify.py --check
   uv run pytest -q \
     tests/test_executable_receipt_validation.py \
     tests/test_executable_receipt_producer.py \
     tests/test_certify_executable.py
   ```

Until the receipt, bundle, and allowlist entry are all committed, certification
remains computed-false. No maintainer sets the verdict field.
