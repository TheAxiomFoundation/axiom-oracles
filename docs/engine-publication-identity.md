# Published engine identity

Every new or edited Axiom-bearing dashboard report must contain
`provenance.engine.commit` as a full 40-character hexadecimal source commit
and `provenance.engine.binary_sha256` as a 64-character hexadecimal digest of
the executable that ran. `axiom_oracles.engine_publication` supplies the shared
validator; `scripts/check_engine_identity.py --check` runs it in CI and in both
publication gates after the existing re-emission guard and again after derived
regeneration, so the final bytes are checked. The generic publisher's
`VERIFY_DERIVED_REFRESH` check-only route applies the same validator.
Validation never supplies identity
from the publishing machine.

Build the intended engine in a clean checkout at its full source commit. The
build helper verifies the checkout before and after the build, removes stale
output, and writes `<binary>.provenance.json` binding that commit to the
resulting executable's SHA-256:

```sh
python -m axiom_oracles.engine_identity build \
  --repo /path/to/axiom-rules-engine \
  --binary /path/to/axiom-rules-engine/target/release/axiom-rules-engine \
  -- cargo build --release --locked --bin axiom-rules-engine -j 4
python -m axiom_oracles.engine_identity inspect \
  /path/to/axiom-rules-engine/target/release/axiom-rules-engine \
  --expect-commit 32bc1c124724ebbb2187a196a3b228cfb2a14721
```

Existing matching axiom-encode `.provenance.json` receipts are also accepted.
Cache the sidecar with the executable. Every invocation hashes the resolved
executable before and after execution, including cache hits; absent or stale
sidecars retain the actual binary digest and leave the source commit unresolved.
These local build attestations protect against accidental drift and are not
signed statements.

The comparison runner supplies a private `AXIOM_ENGINE_RECEIPT_OUTPUT` journal
to generator subprocesses. The engine adapter writes its receipt after each
verified invocation, so wrappers that omit raw engine evidence can still return
execution identity to the parent. Journal writers lock a sibling `.lock` file,
write atomically, and reject different commits or binary digests within one run.
The parent compares this evidence with any selected binary and removes the
temporary journal and lock after stamping the report. Without that environment
variable the adapter writes no execution journal.

At migration baseline `68ebb9cd7a4270ae9d7ad06b53a5e6680536468c`, all **266**
top-level Axiom-bearing reports fail this canonical-field requirement. Some
already carry identity in older fields or nested campaign runtime provenance;
those fields are not the new canonical block. No historical report is rewritten
by this migration. Run `python scripts/check_engine_identity.py --strict` to
measure the unresolved count without exemptions (a failing exit status is
expected until these reports have been rerun).

`conformance/legacy-engine-identity.json` freezes those 266 report paths with
the SHA-256 of each complete published file. The exception applies only while
both the path and bytes match. New files, copied files at another path, and
any edit to an existing file require the new identity. The list may only
shrink: validation compares it with every committed ancestor version, so an
entry cannot be added, have its digest changed, or be restored by a revert
after removal. CI checks out full history for this ratchet.

A copied report keeps the engine block describing the original results. The
re-emission guard restores an existing published report before identity
validation, preserving its bytes and any historical exception. A first-time
copy with unresolved identity is rejected. Rerunning reports against the
target engine, and removing the corresponding historical exceptions, is a
separate migration step.
