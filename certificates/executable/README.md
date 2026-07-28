# Executable receipts

This directory is the fail-closed trust root for the program certificate's
`executable` premise.

- `engine-releases.json` pins released engine tags, tag commits, assets, and
  full archive SHA-256 values.
- `us-co-snap/manifest.json` pins the published program-artifact release,
  artifact hash, golden request bytes, output bindings, and receipt path.
- `workflow-allowlist.json` names workflow commit SHAs authorized under the
  separately governed producer protocol.
- `us-co-snap/receipt.json` is generated only by
  `.github/workflows/executable-receipt.yml`. Its absence or rejection makes
  `executable` false.

The initial workflow PR deliberately leaves the allowlist empty and does not
carry a fabricated receipt. After the governed workflow lands on `main`, a
maintainer dispatches it there. Following the separate cross-family approval,
the maintainer mechanically commits the downloaded, attested JSON artifact at
the declared receipt path and allowlists the receipt's exact
`github.workflow_sha`. `scripts/certify.py --check` then independently re-checks
the release checksum membership, artifact and fixture pins, exact golden
values, command exits, and workflow provenance. Until both files are committed,
the executable verdict remains false.
