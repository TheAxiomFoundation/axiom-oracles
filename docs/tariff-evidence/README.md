# Frozen US tariff boundary evidence

This directory documents a bounded historical evidence snapshot preserved on
the current Axiom Oracles codebase. It is evidence about a frozen Axiom
RuleSpec/runtime pair; it is not the current tariff certificate, does not amend
the live closure ledger, and does not authorize release.

## Frozen contract

- RuleSpec: `4f591c4267063094cc6da9d590872ea982940b81`
- Corpus: `cc18c703741425a3ebf994a2975cae158bd305d1`
- Axiom engine source: `ffd8213271947b0189a9dd61a055c1e0e78908a0`
- Axiom engine SHA-256: `674ca6e70afdccb59c3d6847933bc24b4590105e49db54790f2dcd0bdbbe32d7`
- Repository base used to author this uncommitted package:
  `c7cd2346ef540801d2c89780420be77dc0654ff9`
- Canonical historical input inventory: 58 reachable inputs, all with named
  scopes and all still lacking actual-entry grounding
- Evidence coverage: 21 of those 58 scopes

The snapshot module at `scripts/us_tariff_evidence_snapshot.py` owns these
historical pins, the canonical 58-input inventory, compiled-dependency
traversal, and the generated `frontier-inventory.json`. It does not import the
live closure module or expose certification authority.

## Reproduced result

The combined offline replay executes the real pinned Axiom engine for 843
queries covering 453 distinct entity IDs. It reproduces 831 successful result
rows, 1,817 returned output bindings, and 12 intentional native missing-input
errors. The receipts record 30 source/runtime mismatch records covering 19
unique scenarios, plus nine raw HTS identity differences. The 21
covered scopes divide into 12 with no mismatch detected by their bounded
checks, seven with known source/runtime mismatches, one post-expiry-only scope,
and one diagnostic-contract-only scope. These per-scope execution counts are
non-additive because several scopes share the same receipt. Zero scopes are
fully grounded or admitted.

Expected values are source-linked reviewed transcriptions. They are not
machine-derived or independently derived from the PDFs. The portable verifier
proves exact recorded native outcomes only; it does not recompute source
expectations, adapter relations, mismatch classifications, or legal meaning.
The engine source commit and executable hash are independently pinned; this
package does not claim a reproducible-build proof connecting those two pins.

Raw PDFs, normalized HTTP metadata, the original signed corpus ingest, and its
public verification key are under
`reference/us-tariff-schedule/boundary-evidence/`. Every generated receipt
binds its producer bytes. The combined replay manifest binds all receipts,
runtime helpers, compiled artifacts, RuleSpec modules, raw captures, and the
pinned engine.

## Reproduction

Configure the external frozen repositories and engine without relying on a
developer-specific checkout path:

```text
export AXIOM_TARIFF_EVIDENCE_CORPUS_ROOT=/path/to/axiom-corpus
export AXIOM_TARIFF_EVIDENCE_RULESPEC_ROOT=/path/to/rulespec-us
export AXIOM_TARIFF_EVIDENCE_ENGINE_ROOT=/path/to/axiom-rules-engine
```

The roots must contain the pinned Git objects above. By default the executable
is read from `$AXIOM_TARIFF_EVIDENCE_ENGINE_ROOT/target/release/axiom-rules-engine`;
`AXIOM_TARIFF_EVIDENCE_ENGINE_BINARY` may select another path whose SHA-256
matches the frozen binary pin. Regenerate receipts in dependency order, then
run each command again with `--check`:

```text
uv run python scripts/us_tariff_live_source_evidence.py --write
uv run python scripts/build_us_tariff_boundary_evidence.py
uv run python scripts/build_us_tariff_note52_boundary_evidence.py
uv run python scripts/build_us_tariff_identity_evidence.py
uv run python scripts/build_us_tariff_china_action_evidence.py
uv run python scripts/build_us_tariff_temporal_evidence.py
uv run python scripts/build_us_tariff_china_list_evidence.py
uv run python scripts/build_us_tariff_column2_evidence.py
uv run python scripts/build_us_tariff_metal_evidence.py
uv run python scripts/us_tariff_evidence_snapshot.py
```

The two replay builders write deterministic archives to a caller-selected
path and write their trusted receipt separately. Extract an archive into an
empty directory and pass the committed receipt's
`verification.manifest_sha256` to `--verify-bundle`; verification requires no
network access.

## Current-base separation

This frozen 58-input contract must not be relabeled as, or arithmetically
compared with, a current live frontier. Read live counts and status only from
the certificate pinned to the revision being reviewed. Current certificate,
closure, exercise census, campaign, and publication artifacts are
intentionally untouched by this package.
