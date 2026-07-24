# Nonstatutory amount exclusions — DONE

Completed on branch `fed-parity/federal-grid-suites`.

- Exactly seven approved PolicyEngine-US dollar rows are excluded as
  `oracle_models_nonstatutory_amount`, with exact 1.767.3 imputation paths and
  separately comparable eligibility surfaces in every note.
- 25D, 30D, and 25E remain in scope and uncovered.
- Final us-pe conformance is 35/127 covered (27.5591%), with 21 excluded, 92
  uncovered, zero unexplained, and zero Axiom-attributed open.
- The ratchet retained `covered_min: 35` and both zero ceilings while recording
  `policies_in_scope: 127`.
- The required 2026-07-24 UTC snapshots and all derived artifacts are current.
- All check gates, Ruff, full pytest (1,693 passed / 33 skipped), and the fresh
  sdist/wheel build pass.
- Verified implementation commit:
  `9e1a4c81031bd50d9b65dfceeb2e3dd275d0aa65`.

The complete final report, seven notes, ratchet analysis, gate outputs, and
commit list are in
[`schema-nonstatutory-SUMMARY.md`](./schema-nonstatutory-SUMMARY.md).
