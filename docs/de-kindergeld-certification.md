# DE Kindergeld amount-subgraph certification lane

The committed certificate is intentionally pending. Its computed blockers are
the two Axiom comparison legs, the signed RuleSpec-DE EStG section 66 artifact,
and the pinned release-binary replay receipt. The clean historical
EUROMOD-to-GETTSIM aggregate is a source-source conservation crosscheck; it is
not per-case oracle evidence and cannot satisfy either Axiom leg.

## Landing the evidence bundle

The reviewed RuleSpec-DE pin lives in both registered leg configs:

- `comparisons/de-worker-dual-oracle-axiom-euromod.yaml`;
- `comparisons/de-worker-dual-oracle-axiom-gettsim.yaml`.

The `rulespec_upstream_sha` and `rulespec_upstream_tree` fields must move
together in a visible change. The same commit/tree is mirrored in the
executable manifest and checked for exact equality by tests. Moving
RuleSpec-DE `main` by itself does not move this lane: after EStG 66 lands, bump
the reviewed pin, regenerate the pending records, and run the live producer
below. Until then, both pair records say exactly `pending:
module-not-on-main`; that state never counts as conformance.

The signing/oracle lane produces every mutually dependent artifact in one run:

```sh
python scripts/de_executable.py --run \
  --engine-archive /path/to/axiom-rules-engine-x86_64-unknown-linux-gnu.tar.xz \
  --rulespec-root /path/to/rulespec-de \
  --signing-public-key /path/to/apply-public-key \
  --euromod-model-root /path/to/EUROMOD_RELEASES_J2.0+ \
  --euromod-python /path/to/euromod/python
```

Run this command on the provisioned x86_64 Linux oracle host: the pinned Axiom
release asset is `x86_64-unknown-linux-gnu`, and the same host must have the
EUROMOD J2.0+ model/Python environment plus the locked GETTSIM 1.2.1 extra.
For ordinary engine development, discover the local binary with
`axiom-locate engine` or use the sibling `axiom-rules-engine` checkout. The
certificate producer deliberately requires the published release archive,
because its exact SHA-256 and version output are part of the replay receipt.

This path executes EUROMOD and GETTSIM directly over the canonical thirteen
households; it has no report-reemission branch. It separately extracts the
digest-pinned released Axiom engine, verifies the EStG section 66 apply
manifest's Ed25519 signature and exact module bytes, and executes the amount
root. It then writes:

- `comparisons/de-worker-dual-oracle/axiom-euromod.json`;
- `comparisons/de-worker-dual-oracle/axiom-gettsim.json`;
- `comparisons/de-worker-dual-oracle/unified-record.json`;
- `conformance/executable/de-kindergeld-signed-rulespec.json`;
- `conformance/executable/de-kindergeld-replay-receipt.json`; and
- `conformance/executable/de-kindergeld-status.json`.

Each comparison left value is bound to the stored live-oracle execution row.
Each comparison right value is the actual Axiom amount-root output multiplied
by the canonical suite's computed child count. The historical 765 EUR sum is
checked only after those rows exist. Ordinary verification reruns the embedded
released-engine archive and fails closed on any leg, rulespec, receipt, or
cross-leg inconsistency.

Every JSON output is replaced atomically. If a host interruption lands only a
prefix of the six-file bundle, rerunning the command rebuilds the canonical
source population without trusting those replaceable files and repairs the
bundle; ordinary status regeneration remains fail-closed in the meantime.

After the bundle lands, run `scripts/commit_refreshed_report.sh` (or the same
derived regeneration/check sequence in CI). The refresh chain rederives the
unified record, executable status, DE census, and certificates; there is no
manual certificate-status edit.

## Claim labels

Stored EUROMOD/GETTSIM result rows and external engine release identities are
attested observations because ordinary refresh does not rerun those licensed
or optional engines. Their row digests and comparison verdicts are computed.
Axiom results, fresh released-binary replay, hashes, signature verification,
variation, and citation-path resolution are computed. The rulespec checkout
commit is attested metadata and is not part of the computed signature premise
because the signed v5 apply manifest does not cover it. No artifact in this
pending lane is labeled certified.

## Certified is an honest no (2026-08-20 ruling)

Three premises compute true — conformant (both live Axiom pair legs, 26/26),
exercised (13-household variation), executable (signed EStG 66 replayed in
pinned release v0.2.2) — but the certificate computes `certified: no`,
because `closed` is false under the central completeness requirement
(oracles#491, per Max's 2026-08-20 ruling): a closure claim must disposition
every subordinate instrument the official registry links to the act, and a
law-derived quantity can never be a case-supplied leaf.

The DE closure currently declares no subordinate-instrument frontier, and its
four boundary inputs are law-derived:

- **Instrument frontier**: the DA-KG (BZSt Dienstanweisung zum Kindergeld)
  layer and the EStG/BKGG interplay are undispositioned. Pattern to follow:
  the dk lane's `scripts/refresh_instrument_graph.py` + `closure_ledger.py`
  schema v2 (ELI-graph snapshot → bijective, text-grounded dispositions →
  semantic-sha binding).
- **Law-derived leaves**: `claimant_entitlement` (EStG 62),
  `qualifying_child_count` (EStG 63), `recipient_priority` (EStG 64), and
  `substitute_child_benefit_exclusion` (EStG 65) are currently
  excluded-with-reason case inputs. Each is a quantity the corpus defines how
  to compute, so under the dependency-closure definition
  (`d3/certified-definition`) each must be encoded; only observable acts may
  remain leaves.

Working both lists to completion — then rerunning the closure, census, and
certify chain — is the path back to a certified claim. No certified claim is
announced anywhere without Max's explicit clear.
