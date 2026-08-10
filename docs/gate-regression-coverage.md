# Certification gate regression-coverage audit

Date: 2026-08-09  
Branch: `autogo/gate-regression-coverage`  
Base: `origin/main@a365aac2`  
Evidence-validator object: `origin/evidence-validator@33a182ee`

## Verdict

This was a defensive correctness and completeness audit. No gate implementation
was changed. The audit adds selective mutants only in
`tests/test_gate_regression_coverage.py`.

Before this audit, none of the six reviewed gate surfaces had complete
requirement-level regression coverage. After it, all 198 requirement families
below have an executable trace: a passing rejection/control or a strict xfail
that names the implementation or documentation gap. The suite has **46 strict
xfail cases across 38 distinct gap families**. An XPASS is intentionally a
failure so a closed gap cannot disappear silently.

The most consequential gaps are:

1. `certify.py` can treat registry text saying `status: computed` as a real
   producer and reach `certified: yes` when the other mocked premises are clean.
2. The current-main certificate does not bind the complete exercise identity
   chain: census report path/SHA, canonical bridge-manifest selection, and the
   manifest path/SHA promised by the manifest itself.
3. Empty pinned closure denominators produce `closed: true`.

## Coverage counts

“Partial” means an existing test exercised part of a requirement family but
could remain green if another documented branch were deleted. “Traced” counts
both passing tests and strict xfails; xfail is coverage of a known gap, not a
claim that the implementation conforms.

| Gate | Requirement families | Pre-audit full | Pre-audit partial | Pre-audit no selective test | Post-audit traced | Xfail families | Xfail cases |
|---|---:|---:|---:|---:|---:|---:|---:|
| `scripts/certify.py` | 32 | 5 | 10 | 17 | 32 | 15 | 19 |
| `scripts/exercise_census.py` | 21 | 3 | 0 | 18 | 21 | 4 | 5 |
| `scripts/validate_bridge_manifests.py` | 25 | 4 | 0 | 21 | 25 | 4 | 4 |
| `scripts/closure_universe.py` | 40 | 14 | 0 | 26 | 40 | 5 | 5 |
| `scripts/merge_closure_classifications.py` | 23 | 0 | 0 | 23 | 23 | 6 | 9 |
| `origin/evidence-validator:axiom_oracles/evidence.py` | 57 | 29 | 0 | 28 | 57 | 4 | 4 |
| **Total** | **198** | **55** | **10** | **133** | **198** | **38** | **46** |

`MAN-25` and `CERT-32` exercise the same cross-gate identity gap. That shared
family is counted once under `certify.py`, so the total reports unique gap
families rather than summing the per-gate column.

## Method and scope

Requirements came only from the six named module docstrings and diagnostics,
`closure/README.md`, the bridge-manifest preamble, evidence-branch review/result
documents, and the cached PR descriptions in merge commits for PRs #375, #379,
and #400. A search of current-main `docs/` found no additional normative lists
for these gates. Branch-only evidence code and tests were read with `git show`;
the new tests do the same and skip only when the reviewed Git object is absent.

The evidence module explicitly says engine identity and policy-output coverage
belong to a separate execution-attestation layer. Those concerns are therefore
not invented here as evidence-validator requirements. Likewise, PR #400's
newer contract makes `closure_universe.py --generate` the sole ratchet writer;
the merger's contrary docstring remains a documentation-conflict xfail, not a
recommendation to restore two writers.

Each row below is one requirement family. Parameter IDs are shown when the
individual branch matters. `EV:` prefixes a test that exists only on
`origin/evidence-validator`; unprefixed nodes are in the current worktree.
`CM` abbreviates `tests/test_certification_mutants.py`, `GR` abbreviates
`tests/test_gate_regression_coverage.py`, and `EV-CM`/`EV-CEN` abbreviate the
evidence branch's certification/census test modules.

## Traceability table

### `scripts/certify.py`

| ID | Requirement / source | Regression test(s) | Result |
|---|---|---|---|
| CERT-01 | One deterministic output per program registry entry (PR #375). | `GR::test_certificate_output_names_are_a_bijection_with_program_registry` | PASS |
| CERT-02 | Computed claims cite exact artifact paths and SHA-256. | `GR::test_certificate_computed_evidence_carries_exact_artifact_digests` | PASS |
| CERT-03 | Attested claims are SHA-pinned external receipts. | `GR::test_certificate_attested_receipt_requires_sha_pin` | **XFAIL** |
| CERT-04 | `oracle_type` is exactly reference or reality. | `GR::test_certificate_unknown_oracle_type_is_a_defect` | **XFAIL** |
| CERT-05 | Reference disagreements gate conformance; reality disagreements remain visible leads. | `GR::test_certificate_reference_and_reality_oracle_semantics` | PASS |
| CERT-06 | Missing/malformed/nonmapping reports become defects, not exceptions. | `EV-CM::test_missing_or_malformed_report_surfaces_a_leg_defect`; `EV-CM::test_malformed_nested_report_shapes_surface_leg_defects`; `GR::test_certificate_report_read_and_shape_failures_are_leg_defects` | **XFAIL on main** |
| CERT-07 | Report suite matches the registry suite or declared alias. | `CM::test_mislabeled_report_is_a_defect`; `GR::test_certificate_declared_alias_can_bind_report_identity` | PASS |
| CERT-08 | Every count is a nonnegative integer. | Two existing invalid-count mutants; `GR::test_certificate_count_rejects_non_integer_types`; `GR::test_certificate_count_rejects_integral_float` | **XFAIL for integral float** |
| CERT-09 | Zero comparisons is defective. | `CM::test_zero_work_report_is_a_defect` | PASS |
| CERT-10 | Positive comparisons require well-formed committed case evidence. | `CM::test_counts_without_any_case_evidence_are_a_defect`; `CM::test_junk_case_rows_are_not_evidence`; `GR::test_certificate_rejects_malformed_chunk_as_per_case_evidence` | **XFAIL for malformed chunk** |
| CERT-11 | Matches plus mismatches equals comparisons. | `GR::test_certificate_rejects_nonconserving_summary_counts` | PASS |
| CERT-12 | Every supported engine-error shape independently blocks. | `CM::test_errors_under_errors_by_engine_are_counted`; `GR::test_certificate_rejects_each_engine_error_shape_independently` | PASS |
| CERT-13 | Weighted mismatch is numeric, finite, nonnegative, and consistent with raw count. | Three weighted-mass tests across `CM` and `GR` | PASS |
| CERT-14 | Disposition citation is an existing regular repository-relative file. | Existing missing/absolute mutants; `GR::test_certificate_rejects_traversing_disposition_path`; `GR::test_certificate_disposition_citation_must_be_a_regular_relative_file` | **XFAIL for directory/non-string** |
| CERT-15 | Disposition document is readable, schema-valid, nonempty, and suite-bound. | Existing foreign/unreadable mutants; `EV-CM::test_same_suite_empty_dispositions_document_cannot_authorize`; `GR::test_certificate_same_suite_empty_dispositions_cannot_authorize` | **XFAIL on main** |
| CERT-16 | Only defined disposition kinds are accepted. | `GR::test_certificate_rejects_undefined_or_nonconserving_disposition_counts[kind]` | PASS |
| CERT-17 | Disposition counts conserve against mismatch count. | Same node, `[under-count\|over-count]` | PASS |
| CERT-18 | Both unexplained-count copies are typed and agree in every shape. | `CM::test_foreign_dispositions_file_cannot_explain_this_suite`; `GR::test_certificate_validates_unexplained_count_even_with_empty_counts` | **XFAIL for empty counts** |
| CERT-19 | With no disposition machinery, every mismatch is unexplained. | `GR::test_certificate_without_disposition_machinery_leaves_mismatches_unexplained` | PASS |
| CERT-20 | Inline classifications without a cited file are always defective. | `GR::test_certificate_inline_classifications_without_file_are_always_defective` | **XFAIL** |
| CERT-21 | Slim mismatch aggregates need stored rows or real chunks. | `GR::test_certificate_rejects_unstored_slim_mismatch_aggregate`; `GR::test_certificate_empty_chunk_directory_does_not_make_slim_report_auditable` | **XFAIL for empty directory** |
| CERT-22 | Open `axiom_encoding_gap` keeps a leg unclean. | `GR::test_certificate_axiom_encoding_gap_keeps_leg_unclean` | PASS |
| CERT-23 | Exercise requires a census row and committed evidence fields. | `GR::test_certificate_exercise_requires_row_evidence_and_clean_bridge[missing-row\|no-fields]` | PASS |
| CERT-24 | Exercise evidence is bound and materially varied, not constant/unbound. | `GR::test_certificate_exercise_requires_bound_material_variation`; `EV-CM::test_certificate_leg_requires_bound_reconciled_execution_evidence` | **XFAIL on main** |
| CERT-25 | Exercise requires a strict-clean bridge audit. | `GR::test_certificate_exercise_requires_row_evidence_and_clean_bridge[bridge-debt]` | PASS |
| CERT-26 | Multiple reports claiming one suite are an ambiguity defect. | `CM::test_contested_reports_are_a_certificate_defect` | PASS |
| CERT-27 | Census report path and SHA equal the registry report identity. | `EV-CM::test_census_report_path_and_sha_must_match_the_registry`; `GR::test_certificate_census_report_identity_must_match_registry[path\|sha]` | **XFAIL on main** |
| CERT-28 | Registry suites require bound/reconciled execution evidence; reference needs full semantics. | Two evidence-branch certificate mutants; `GR::test_certificate_exercise_requires_bound_material_variation` | **XFAIL on main** |
| CERT-29 | Conformance requires at least one clean reference leg. | `GR::test_certificate_conformance_requires_a_clean_reference_leg` | PASS |
| CERT-30 | Certification needs all true computed premises and zero defects; status text cannot self-authorize. | Existing premise/mode tests; `GR::test_certificate_computed_premises_require_real_producers`; `GR::test_certificate_reality_axiom_gap_violates_zero_open_defects` | **XFAIL** |
| CERT-31 | `--check` rejects missing, drifted, and stray certificates. | `GR::test_certificate_check_rejects_missing_drifted_and_stray_outputs` | PASS |
| CERT-32 | Certificate cites exact bridge-manifest path/SHA used by census. | `GR::test_certificate_cites_exact_bridge_manifest_identity` | **XFAIL** |

### `scripts/exercise_census.py`

| ID | Requirement / source | Regression test(s) | Result |
|---|---|---|---|
| CENSUS-01 | Every committed suite remains visible, including zero-evidence suites. | `GR::test_census_enumerates_zero_evidence_and_contested_reports` | PASS |
| CENSUS-02 | Malformed reports/chunks remain visible debt, never silently disappear. | `GR::test_census_malformed_committed_evidence_remains_visible[report\|chunk]` | **XFAIL** |
| CENSUS-03 | Duplicate report claims are recorded as contested. | `GR::test_census_enumerates_zero_evidence_and_contested_reports` | PASS |
| CENSUS-04 | Chunks eclipse illustrative inline cases and record the eclipse count. | `GR::test_census_extracts_compact_fields_concepts_states_and_exact_identities` | PASS |
| CENSUS-05 | Compact `i[{n,v}]` yields field distinctness. | Same node | PASS |
| CENSUS-06 | Compact `v[{c,l,x}]` yields concept distinctness. | Same node | PASS |
| CENSUS-07 | Inline v1 scope includes scalar metadata only. | `GR::test_census_inline_scope_keeps_scalar_stage_evidence_only` | PASS |
| CENSUS-08 | Numerically equal JSON values coalesce, including signed zero. | `CM::test_numeric_canonicalization_collapses_equal_values` | PASS |
| CENSUS-09 | Large exact numerics do not collapse. | `CM::test_long_exact_integers_do_not_merge` | PASS |
| CENSUS-10 | Nonfinite tokens remain distinct and do not crash. | `CM::test_nonfinite_values_stay_distinct_from_numbers` | PASS |
| CENSUS-11 | Multiple observed values are `varied`. | Compact extraction node | PASS |
| CENSUS-12 | `constant` means one value present across every case. | `GR::test_census_constant_requires_value_present_in_every_case` | **XFAIL** |
| CENSUS-13 | Cases/varied/constant totals match the selected corpus. | Compact extraction node | PASS |
| CENSUS-14 | Row records exact measured report path and byte SHA. | Compact extraction node | PASS |
| CENSUS-15 | Chunk manifest records exact repository path and byte SHA. | Compact extraction node; `GR::test_census_chunk_manifest_hashes_exact_bytes` | **XFAIL for CRLF bytes** |
| CENSUS-16 | Bridged dimensions come from manifests and apply to aliases. | `GR::test_census_bridge_manifest_aliases_and_no_manifest_state` | PASS |
| CENSUS-17 | No manifest means unaudited, not “nothing bridged.” | Same node | PASS |
| CENSUS-18 | `bridge_audited` means no validator errors/findings/collisions. | `GR::test_census_bridge_audit_uses_errors_findings_and_global_collisions` | PASS |
| CENSUS-19 | Report/index/chunk binding is path-safe and explicitly bound/unbound. | Evidence-branch census tests; `GR::test_census_row_states_report_chunk_index_binding` | **XFAIL on main** |
| CENSUS-20 | Census caps reconciliation at cardinality; unbound/legacy evidence remains visible. | Evidence-branch census tests; two `GR::test_evidence_branch_census_*` nodes | PASS |
| CENSUS-21 | Check, Markdown, and missing-PyYAML modes have explicit behavior. | Three `GR::test_census_*` CLI/render/dependency nodes | PASS |

### `scripts/validate_bridge_manifests.py`

| ID | Requirement / source | Regression test(s) | Result |
|---|---|---|---|
| MAN-01 | Manifest set is nonempty. | `GR::test_bridge_manifest_cli_rejects_empty_manifest_set` | PASS |
| MAN-02 | YAML root is a mapping. | `GR::test_bridge_manifest_root_must_be_a_mapping` | **XFAIL** |
| MAN-03 | Schema is exactly v1. | `GR::test_bridge_manifest_requires_exact_schema_and_top_level_fields[schema]` | PASS |
| MAN-04 | Suite/program/bindings/population/oracle are required. | Same node, required-field cases | PASS |
| MAN-05 | Aliases, when present, is a list. | `CM::test_scalar_aliases_are_rejected` | PASS |
| MAN-06 | Bindings is a nonempty list. | `GR::test_bridge_manifest_bindings_are_a_nonempty_list` | PASS |
| MAN-07 | Each binding is a mapping. | `GR::test_bridge_manifest_binding_shape_kind_audit_and_name[mapping]` | PASS |
| MAN-08 | Kind is mapped/projected/bridged/constant. | Same node, `[kind]` | PASS |
| MAN-09 | Audit is read/partial and partial is visible debt. | Same node `[audit]`; `GR::test_bridge_manifest_partial_and_unverified_completeness_are_findings` | PASS |
| MAN-10 | Binding names input(s), group, or bridged dimension. | Binding-shape node `[name]` | PASS |
| MAN-11 | `inputs` is an array, not scalar. | `GR::test_bridge_manifest_inputs_must_be_an_array` | **XFAIL** |
| MAN-12 | Input names are unique across bindings. | `GR::test_bridge_manifest_rejects_duplicate_input_bindings` | PASS |
| MAN-13 | Bridged `covered_by` is a nonempty list. | `GR::test_bridge_manifest_bridged_covered_by_is_a_nonempty_list[missing\|empty\|scalar]` | PASS |
| MAN-14 | At least one `covered_by` ref resolves locally; others are findings. | Existing covered-by mutant; `GR::test_bridge_manifest_covered_by_requires_a_checkable_reference_and_reports_debt` | PASS |
| MAN-15 | Ghost/absolute/traversal/placeholder refs cannot satisfy coverage. | Two existing covered-by mutants | PASS |
| MAN-16 | Bridged binding requires source and mechanism. | `GR::test_bridge_manifest_kind_specific_fields_are_required[bridged]` | PASS |
| MAN-17 | Mapped/projected binding requires source/source function. | Same node `[mapped\|projected]` | PASS |
| MAN-18 | Constant binding requires reason/note/source function. | Same node `[constant]` | PASS |
| MAN-19 | Suite or alias resolves to one unambiguous committed report. | `GR::test_bridge_manifest_report_can_be_found_through_alias`; `GR::test_bridge_manifest_rejects_multiple_reports_for_one_suite` | **XFAIL for contest** |
| MAN-20 | Required population pin has exact revision plus valid SHA. | `GR::test_bridge_manifest_population_pin_requires_revision_and_valid_sha` | **XFAIL** |
| MAN-21 | Completeness cannot self-assert without catalog; pending stays visible. | Existing self-assertion mutant; partial/unverified node | PASS |
| MAN-22 | Suite/alias namespace is globally unique. | `GR::test_bridge_manifest_global_suite_and_alias_collisions_are_errors` | PASS |
| MAN-23 | Errors always fail; findings fail only under strict and are always printed. | `GR::test_bridge_manifest_cli_error_and_finding_exit_policy` | PASS |
| MAN-24 | Census bridge state derives from manifests, aliases, findings, and collisions. | Two census/manifest composition nodes | PASS |
| MAN-25 | Certificate cites exact manifest path/SHA. | `GR::test_certificate_cites_exact_bridge_manifest_identity` | **XFAIL shared with CERT-32** |

### `scripts/closure_universe.py`

| ID | Documented requirement | Regression test node | Result |
|---|---|---|---|
| CLO-01 | Scope is `us-co/snap` with exactly three declared roots, snapshots, citation roots, and module prefixes. | `test_closure_scope_declares_exact_program_roots_and_module_prefixes` | PASS |
| CLO-02 | Every nonblank JSONL row is in the denominator; source kind never filters it. | `test_closure_source_loader_keeps_every_nonblank_row_kind` | PASS |
| CLO-03 | Source rows are readable JSON objects with nonempty, in-root, unique citations and string/normalized headings. | `test_closure_source_rows_fail_closed_on_shape_identity_and_heading`; `test_closure_missing_or_null_source_heading_becomes_empty_string` | PASS |
| CLO-04 | `provenance.yaml` exists as schema-v1 mapping with a list of mapping snapshots. | `test_closure_provenance_validates_schema_snapshots_metadata_and_exact_bytes[missing\|root-map\|schema\|snapshot-list\|snapshot-map]` | PASS |
| CLO-05 | Snapshot filenames are unique and cover every source plus the RuleSpec tree. | Same node, `[duplicate\|required-files]` | PASS |
| CLO-06 | Snapshots carry nonempty repository, ref, and extraction metadata. | Same node, `[metadata]` | PASS |
| CLO-07 | Reproducible provenance requires each upstream `source_path`. | `test_closure_snapshot_provenance_requires_source_path` | **XFAIL** |
| CLO-08 | Snapshot paths are safe, relative, and resolve to committed required files. | Provenance node `[safe-path\|required-files]`; source-row node `[missing]` | PASS |
| CLO-09 | Snapshot SHA is lowercase 64-hex and equals exact file bytes. | Provenance node `[sha-format\|sha-drift]` | PASS |
| CLO-10 | The pinned RuleSpec inventory is duplicate-free. | `test_closure_pinned_tree_is_duplicate_free` | PASS |
| CLO-11 | The v1 join derives one exact citation candidate and tests exact pinned-tree membership. | `tests/test_closure_mutants.py::test_generated_baseline_passes_check`; `::test_pin_update_rederives_an_ordinary_encoded_row` | PASS |
| CLO-12 | A descendant module does not encode its parent provision. | `tests/test_closure_mutants.py::test_descendant_module_does_not_encode_its_parent` | PASS |
| CLO-13 | Malformed/nonmapping universe YAML and summary JSON fail closed. | `test_closure_artifact_loaders_reject_malformed_or_nonmapping_roots` | PASS |
| CLO-14 | Each universe has exact schema, program, and root identity. | `test_closure_universe_artifact_validates_identity_provenance_and_ratchet[schema\|program\|root]` | PASS |
| CLO-15 | Universe provenance has every source/RuleSpec identity field and valid digests. | Same node, `[provenance\|provenance-sha]` | PASS |
| CLO-16 | Ratchet metadata is a mapping with provenance-bound pin and nonnegative ceiling. | Same node, `[ratchet\|ratchet-pin\|pending-max]` | PASS |
| CLO-17 | `provisions` is a list of mappings with unique citations and string headings/notes. | `test_closure_provisions_are_a_list_with_unique_citations`; `test_closure_provision_shape_status_and_contradiction_invariants[mapping\|citation\|heading\|note]` | PASS |
| CLO-18 | Status is exactly encoded/excluded/pending; contradictory status fields fail. | Provision-invariant node `[status\|pending-contradiction\|encoded-contradiction\|excluded-contradiction]` | PASS |
| CLO-19 | Encoded rows have nonempty, duplicate-free safe production-YAML path lists. | Provision-invariant node `[encoded-empty\|encoded-duplicate]`; `test_closure_named_modules_must_be_safe_production_yaml_paths` | PASS |
| CLO-20 | Every `encoded_by` module exists in the pinned tree. | `tests/test_closure_mutants.py::test_ghost_encoded_by_fails` | PASS |
| CLO-21 | Exclusions require nonempty reason/basis and no `encoded_by`. | `tests/test_closure_mutants.py::test_excluded_without_basis_fails`; provision-invariant node `[excluded-reason\|excluded-contradiction]` | PASS |
| CLO-22 | Exclusion taxonomy is closed; `operationalized_by` is safe, present, and spacing-tolerant. | `tests/test_closure_mutants.py::test_taxonomy_violating_reason_fails`; `::test_operationalized_by_tolerates_yaml_spacing_but_not_unsafe_paths` | PASS |
| CLO-23 | Exclusion basis is grounded in the pinned provision text. | `test_closure_exclusion_basis_must_be_grounded_in_pinned_source_text` | **XFAIL** |
| CLO-24 | Partial coverage stays pending, states missing outputs, survives, and is required with `join_found_module`. | `tests/test_closure_mutants.py::test_partial_coverage_survives_regeneration_and_requires_a_statement`; `test_closure_join_found_module_requires_partial_coverage_statement` | PASS |
| CLO-25 | Partial coverage binds to a present joined module that actually declares the deferred output. | `test_closure_partial_coverage_requires_present_joined_deferred_module` | **XFAIL** |
| CLO-26 | Ordinary status is regenerated from exact current pins; a disappeared join demotes. | `tests/test_closure_mutants.py::test_pin_update_rederives_an_ordinary_encoded_row`; `::test_descendant_module_does_not_encode_its_parent` | PASS |
| CLO-27 | Regeneration preserves valid reviews/notes but refreshes generated headings. | `tests/test_closure_mutants.py::test_corrected_encoded_by_survives_regeneration`; `::test_partial_coverage_survives_regeneration_and_requires_a_statement`; `test_closure_note_survives_while_heading_refreshes_from_pinned_source` | PASS |
| CLO-28 | Missing/extra committed citations relative to the pinned denominator are fatal drift. | `tests/test_closure_mutants.py::test_citation_drift_fails` | PASS |
| CLO-29 | Summary has exact schema/program and a unique, complete root inventory. | `test_closure_summary_validates_identity_inventory_counts_and_pins[schema\|program\|roots-list\|duplicate-root\|root-inventory]` | PASS |
| CLO-30 | Summary totals/status/reason/pin/ceiling values are typed, nonnegative, and conserving. | Same node, `[total-type\|status-type\|conservation\|reason-count\|pin\|pending]` | PASS |
| CLO-31 | Generated summary reports exact live counts, reasons, pins, and ceilings. | `test_closure_summary_counts_reasons_and_closed_are_exact`; `test_closure_published_universe_counts_match_reviewed_result` | PASS |
| CLO-32 | `closed` is true only when every root has zero pending rows. | `test_closure_summary_counts_reasons_and_closed_are_exact` | PASS |
| CLO-33 | A vacuous zero-row pinned denominator cannot certify closure. | `test_closure_empty_pinned_denominator_cannot_be_closed` | **XFAIL** |
| CLO-34 | Generate writes exactly three universes plus summary, deterministically. | `test_closure_generate_writes_exact_artifact_set_deterministically` | PASS |
| CLO-35 | Check is read-only and rejects missing/stale artifacts. | `test_closure_check_is_read_only_and_rejects_missing_or_stale_artifacts`; existing baseline check | PASS |
| CLO-36 | Universe/summary ratchet copies must both exist and agree; v1 migration is cross-bound. | `tests/test_closure_mutants.py::test_pending_regression_cannot_raise_only_universe_ceiling`; `test_closure_v1_ratchet_migration_requires_both_matching_copies` | PASS |
| CLO-37 | Full Git history supplies an immutable floor; coordinated/simplified history cannot erase it; shallow clones fail. | Three history mutants in `tests/test_closure_mutants.py`; `test_closure_rejects_shallow_checkout_for_history_ratchet` | PASS |
| CLO-38 | With unchanged pins, pending may otherwise only fall and metadata cannot forge reset. | `tests/test_closure_mutants.py::test_pending_regression_fails_when_provenance_is_unchanged`; reset/forge mutants | PASS |
| CLO-39 | Content-pin changes start a baseline; descriptive repo/ref edits do not. | `test_closure_source_pin_change_starts_new_ratchet_baseline`; `test_closure_ratchet_fingerprint_ignores_descriptive_provenance_text` | PASS |
| CLO-40 | A rise is allowed only for newly reopened, individually disclosed corrections; old disclosure cannot mask another rise. | `test_closure_pending_rise_exceeding_disclosures_is_rejected`; `test_closure_existing_disclosure_cannot_mask_unrelated_pending_rise`; existing disclosure mutant | **XFAIL** |

### `scripts/merge_closure_classifications.py`

| ID | Documented requirement | Regression test node | Result |
|---|---|---|---|
| MRG-01 | Inputs accept a list root or mapping under `rows`/`provisions`. | `test_merge_closure_accepts_list_rows_and_provisions_roots` | PASS |
| MRG-02 | Nonmapping/citation-less rows are rejected, never silently dropped. | `test_merge_closure_rejects_rows_it_cannot_ingest` | **XFAIL** |
| MRG-03 | Duplicate classifications are errors and write nothing. | `test_merge_closure_rejects_duplicate_classification_without_writing` | PASS |
| MRG-04 | Citation absent from every universe is an error. | `test_merge_closure_refusals_return_nonzero_and_write_nothing[absent-citation]` | PASS |
| MRG-05 | Unknown status is rejected. | Same node, `[unknown-status]` | PASS |
| MRG-06 | A pending provision may be reviewed as excluded. | `test_merge_closure_successful_actions_write_reviewed_fields_and_preserve_header[exclude]` | PASS |
| MRG-07 | Exclusion requires a reason. | Refusal node `[exclusion-reason]` | PASS |
| MRG-08 | Exclusion requires a basis. | Refusal node `[exclusion-basis]` | PASS |
| MRG-09 | Fixed reasons use the closed taxonomy. | Refusal node `[taxonomy]` | PASS |
| MRG-10 | `operationalized_by` is normalized and names a pinned-tree module. | Refusal node `[operationalized]`; successful `[exclude]` | PASS |
| MRG-11 | Exclusion basis is grounded in the provision text. | `test_merge_closure_exclusion_basis_is_grounded_in_provision_text` | **XFAIL** |
| MRG-12 | Encoded→pending downgrade requires a statement of deferred outputs. | Refusal node `[downgrade-note]`; successful `[downgrade]` | PASS |
| MRG-13 | Downgrade agrees with actual module `deferred_outputs`. | `test_merge_closure_downgrade_requires_actual_deferred_outputs` | **XFAIL** |
| MRG-14 | Pending row may receive a normalized note without status change. | Successful node `[pending-note]` | PASS |
| MRG-15 | Reviewer may correct `encoded_by`. | Successful node `[encode]` | PASS |
| MRG-16 | Corrected `encoded_by` is nonempty, duplicate-free, and path-safe. | `test_merge_closure_rejects_invalid_encoded_by` | **XFAIL** |
| MRG-17 | Every corrected path exists in the pinned tree. | Refusal node `[encoded-path]` | PASS |
| MRG-18 | Converting excluded→encoded clears contradictory reason/basis. | `test_merge_closure_encoded_correction_removes_exclusion_fields` | **XFAIL** |
| MRG-19 | A merge never raises pending above the committed ceiling. | Refusal node `[pending-rise]` | PASS |
| MRG-20 | The older docstring says a successful merge lowers `pending_max`. | `test_merge_closure_lowers_pending_max_as_docstring_promises` | **XFAIL** — stale-doc conflict; PR #400 assigns the write to generate |
| MRG-21 | `--dry-run` validates but writes nothing. | `test_merge_closure_dry_run_writes_nothing` | PASS |
| MRG-22 | Refusals are atomic; success preserves generated headers. | Refusal node; successful-actions node | PASS |
| MRG-23 | Cross-gate: modules admitted from tree bytes agree with provenance or closure check rejects them. | `test_merge_then_closure_rejects_module_from_unpinned_tree_bytes` | PASS |

### `origin/evidence-validator:axiom_oracles/evidence.py`

| ID | Documented requirement family | Regression witness | Result |
|---|---|---|---|
| EVD-01 | JSON is standards-compliant; nonfinite constants/overflow fail. | `EV-CM::test_nonstandard_nonfinite_json_is_malformed_evidence`; `::test_json_parser_rejects_constants_and_overflowed_floats` | PASS |
| EVD-02 | Report identity is canonical path plus SHA of exact bytes. | `EV-CM::test_index_report_sha_must_match_exact_report_bytes`; `GR::test_evidence_build_index_recomputes_binding_and_preserves_legacy_metadata` | PASS |
| EVD-03 | Suite is one safe, nontraversing path component. | Existing unsafe-suite tests; `GR::test_evidence_suite_name_is_one_safe_path_component` | PASS |
| EVD-04 | Evidence report/chunk values are immutable. | `GR::test_evidence_defects_are_partitioned_ordered_and_results_immutable` | PASS |
| EVD-05 | Content/binding defects stay separate and ordered; valid/clean agree. | Same node | PASS |
| EVD-06 | Missing, malformed, or unreadable report/chunk/index becomes a defect. | Existing malformed tests; `GR::test_evidence_unreadable_artifacts_surface_defects[report\|chunk\|index]` | PASS |
| EVD-07 | Report root is an object. | `GR::test_evidence_report_count_case_and_chunk_shape_mutants[report-object]` | PASS |
| EVD-08 | Report summary is an object. | `EV-CM::test_malformed_nested_report_shapes_surface_leg_defects` | PASS |
| EVD-09 | All summary counts are required strict nonnegative integers. | Report/count mutant `[count-missing\|count-type]` | PASS |
| EVD-10 | Summary counts conserve. | Report/count mutant `[counts-conserve]` | PASS |
| EVD-11 | Inline cases is an array; chunks are arrays or objects with cases arrays; each case row is an object. | Existing nested-shape test; report/count `[chunk-envelope]`; `GR::test_evidence_chunk_object_cases_envelope_is_accepted`; `GR::test_evidence_each_inline_and_compact_case_row_must_be_an_object` | PASS |
| EVD-12 | `case_count` is strict and equals every parsed inline/chunk row. | Report/count `[case-count-type\|case-count-drift]` | PASS |
| EVD-13 | Zero committed cases is an explicit defect; metadata cannot substitute. | Existing dummy-metadata mutant; `GR::test_evidence_zero_cases_is_an_explicit_execution_evidence_defect` | PASS |
| EVD-14 | IDs are nonempty string/int, bool/other types fail, and `1` collides with `"1"`. | Compact mutant `[id-type\|id-empty\|id-normalization]` | PASS |
| EVD-15 | IDs are unique within and across inline/chunk sources. | Existing duplicate-ID mutant; compact mutant `[cross-source-id]` | PASS |
| EVD-16 | Compact rows require `r`, `h`, and `m`. | Compact mutant `[r-missing\|h-missing\|m-missing]` | PASS |
| EVD-17 | `r` is finite numeric/null and within 0–100. | Existing bounded-rate mutant; compact mutant `[r-type]` | PASS |
| EVD-18 | `h` is an object. | Compact mutant `[h-type]` | PASS |
| EVD-19 | `m` is an array of concept/left/right rows; optional disposition is nonempty. | Existing malformed-row mutant; compact mutant `[m-row\|m-values\|disposition]` | PASS |
| EVD-20 | Optional `i` is an array of nonempty-name/present-value rows. | Compact mutant `[i-type\|i-row\|i-value\|i-name]` | PASS |
| EVD-21 | Optional `v` is an array of nonempty-concept/present-side rows. | Existing concept-name mutant; compact mutant `[v-type\|v-row\|v-values]` | PASS |
| EVD-22 | Compared values may be arbitrary standards-compliant JSON. | `GR::test_evidence_compared_values_may_be_arbitrary_json` | PASS |
| EVD-23 | Per-case concepts neither repeat nor overlap match/mismatch sets. | `EV-CM::test_duplicate_and_overlapping_case_concepts_are_rejected` | PASS |
| EVD-24 | Compact mismatch `d` is required, equals `x-l`, and is null for nonnumeric sides. | Existing `d-drift`; compact mutant `[delta-missing\|delta-nonnumeric\|delta-null]` | PASS |
| EVD-25 | With verdicts, `r` equals derived agreement; endpoints are exact. | Existing `r`/endpoint/partial mutants; compact mutant `[rate-null]` | PASS |
| EVD-26 | Verdict-free cardinality rows use `r=null` because agreement is unmeasured. | `GR::test_evidence_cardinality_only_case_requires_unmeasured_rate` | **XFAIL** |
| EVD-27 | Every chunk is parsed; later malformed/unreadable chunks remain visible. | Existing later-chunk mutant; unreadable `[chunk]` | PASS |
| EVD-28 | Full means every parsed case has a complete canonical verdict projection. | `EV-CM::test_full_and_cardinality_reconciliation_are_stated_honestly` | PASS |
| EVD-29 | Cardinality is verdict-free chunks and recomputes raw chunk row count. | Existing honest-state test; `GR::test_evidence_cardinality_recomputes_chunk_row_count` | PASS |
| EVD-30 | Cardinality label itself requires every counted row to be well formed. | `GR::test_evidence_cardinality_label_requires_well_formed_rows` | **XFAIL** |
| EVD-31 | Partial verdict/malformed evidence cannot fall back to cardinality. | Existing partial/malformed mutants | PASS |
| EVD-32 | Explicit `v: []` is meaningful full evidence with zero matches. | Existing honest-state test | PASS |
| EVD-33 | Inline complete matches/mismatches arrays support full reconciliation. | `EV-CM::test_skipped_inline_v1_corpus_is_preserved` | PASS |
| EVD-34 | PR description says inline matched/match booleans support full reconciliation. | `GR::test_evidence_inline_boolean_case_supports_documented_full_reconciliation` | **XFAIL documentation conflict** |
| EVD-35 | Full independently recomputes all three summary counts. | `GR::test_evidence_full_reconciliation_recomputes_each_summary_count[comparison\|matches\|mismatches]` | PASS |
| EVD-36 | Concepts is an array with object rows and unique nonempty IDs. | Semantic mutant `[concepts-type\|concept-row\|concept-id\|concept-duplicate]` | PASS |
| EVD-37 | Each concept declares a nonempty comparison name. | Semantic mutant `[comparison]` | PASS |
| EVD-38 | Comparison kind is amount/eligibility; unknown kinds fail closed. | `GR::test_evidence_unknown_comparison_kind_fails_closed` | **XFAIL** |
| EVD-39 | Both tolerances are present, finite, and nonnegative. | Semantic mutant `[tolerance-missing\|tolerance-invalid]` | PASS |
| EVD-40 | Verdict has a rule and match/mismatch placement follows tolerance semantics. | Semantic mutant `[verdict-rule\|match-placement\|mismatch-placement]` | PASS |
| EVD-41 | Aggregates is an array of unique, nonempty-concept object rows. | Semantic mutant `[aggregates-type\|aggregate-row\|aggregate-concept\|aggregate-duplicate]` | PASS |
| EVD-42 | Aggregate counts/aliases are strict, feasible, internally consistent. | Semantic mutant `[aggregate-count\|aggregate-impossible\|aggregate-alias]` | PASS |
| EVD-43 | Aggregate/stored concept sets and per-concept counts agree both ways. | Semantic mutant `[aggregate-extra\|aggregate-missing\|aggregate-drift]` | PASS |
| EVD-44 | Report mismatches is an array of unique keyed object rows with both sides. | Semantic mutant `[mismatches-type\|mismatch-row\|mismatch-concept\|mismatch-values\|mismatch-duplicate]` | PASS |
| EVD-45 | Report/stored mismatch keys agree exactly both ways. | Semantic mutant `[mismatch-extra\|mismatch-missing]` | PASS |
| EVD-46 | Report/stored mismatch values reconcile under declared semantics. | Existing foreign-value mutant; semantic `[mismatch-values]` | PASS |
| EVD-47 | Report/compact disposition markers agree both ways. | Existing marker-agreement mutant; semantic `[report-disposition]` | PASS |
| EVD-48 | Disposition counts are strict object counts reproducing report markers. | Semantic mutant `[disposition-counts\|disposition-count-type\|disposition-count-drift]` | PASS |
| EVD-49 | Amount weighted sums derive from stored values. | `EV-CM::test_matched_amount_values_must_reconcile_with_aggregate_sums` | PASS |
| EVD-50 | Eligibility positive weights derive from stored values. | `EV-CM::test_matched_eligibility_values_must_reconcile_with_positive_weights` | PASS |
| EVD-51 | Aggregate values are finite and reconcile at documented six-decimal/four-ULP precision. | Semantic `[aggregate-value]`; `GR::test_evidence_numeric_representation_tolerance_boundary_is_pinned` | PASS |
| EVD-52 | Value aggregates require finite reproducible unit comparison weight. | Existing weight-omission mutant; semantic `[weight-type\|weight-drift]` | PASS |
| EVD-53 | Full evidence has a domain-separated, order-independent verdict commitment bound by index. | Existing permutation test; `GR::test_evidence_case_verdict_commitment_is_row_order_independent`; index `[verdict-sha]` | PASS |
| EVD-54 | Missing/legacy/malformed/unreadable/nonobject/wrong-schema index is unbound, nonfatal. | Existing census test; index `[malformed\|object\|schema]`; legacy census node | PASS |
| EVD-55 | Index suite/report path/report SHA identify exact validated report. | Existing foreign/stale tests; index `[suite\|report-sha]` | PASS |
| EVD-56 | Descriptor list has valid unique name/SHA/count, exact set/bytes/cardinality, and strict totals. | `GR::test_evidence_chunk_index_shape_identity_set_and_cardinality_mutants` descriptor/set/count cases | PASS |
| EVD-57 | Index build refuses inconsistency, recomputes authority, preserves legacy metadata, sorts, and supports census/certificate consumers. | Five `GR::test_evidence_build_*`/binding/branch consumer nodes | PASS |

## Already-complete coverage

No whole gate was complete before this audit. The short true list of clusters
that already had selective coverage is:

- census numeric canonicalization, including signed zero, exact large integers,
  and non-finite separation;
- certificate zero-work and mislabeled-report rejection, contested-report
  blocking, and disagreement between the two unexplained-count copies;
- closure's exact descendant-resistant join, referenced-module tree membership,
  exclusion taxonomy, ordinary RuleSpec-pin demotion, corrected-path
  preservation, citation drift, and the core cross-copy/history ratchet defenses;
- evidence strict non-finite JSON parsing, core full/cardinality distinction,
  report/index byte identity, duplicate/overlapping concepts, disposition-marker
  agreement, and case/value semantic association.

After this audit, traceability coverage is complete: every row below names a
test. Implementation correctness is not complete because the strict xfails
remain.

## Xfail gaps ranked by consequence

Ranks are consequence-first; ties favor cross-gate substitution risks. “Cases”
is the number of pytest instances behind the family.

| Rank | Severity | Strict-xfail node | Cases | Consequence |
|---:|---|---|---:|---|
| 1 | Critical | `test_certificate_computed_premises_require_real_producers` | 1 | Registry text can self-authorize “computed” and reach a false positive certificate. |
| 2 | Critical | `test_certificate_census_report_identity_must_match_registry` | 2 | Certificate can inherit exercise measurements from different report bytes. |
| 3 | Critical | `test_certificate_cites_exact_bridge_manifest_identity` | 1 | Certificate does not bind the experiment-design manifest that justifies bridge audit state. |
| 4 | Critical | `test_closure_empty_pinned_denominator_cannot_be_closed` | 1 | Empty/truncated denominators can vacuously emit `closed: true`. |
| 5 | High | `test_certificate_unknown_oracle_type_is_a_defect` | 1 | Misspelling drops a dirty suite from both oracle legs. |
| 6 | High | `test_certificate_reality_axiom_gap_violates_zero_open_defects` | 1 | An admitted Axiom defect can remain only a nonblocking reality lead. |
| 7 | High | `test_certificate_exercise_requires_bound_material_variation` | 1 | Zero-case, constant, unbound evidence can satisfy `exercised`. |
| 8 | High | `test_evidence_unknown_comparison_kind_fails_closed` | 1 | A comparison typo silently receives eligibility truthiness semantics. |
| 9 | High | `test_census_malformed_committed_evidence_remains_visible` | 2 | Invalid committed reports/chunks silently disappear from the census. |
| 10 | High | `test_certificate_rejects_malformed_chunk_as_per_case_evidence` | 1 | Any chunk-shaped filename can satisfy the per-case evidence predicate. |
| 11 | High | `test_certificate_same_suite_empty_dispositions_cannot_authorize` | 1 | Suite-only/empty disposition document can authorize aggregate classifications. |
| 12 | High | `test_bridge_manifest_rejects_multiple_reports_for_one_suite` | 1 | First sorted report silently becomes canonical across manifest/census/certificate gates. |
| 13 | High | `test_certificate_attested_receipt_requires_sha_pin` | 1 | “SHA-pinned” attestation contract does not require a digest. |
| 14 | High | `test_closure_exclusion_basis_must_be_grounded_in_pinned_source_text` | 1 | Arbitrary prose can remove substantive provisions from pending debt. |
| 15 | High | `test_closure_partial_coverage_requires_present_joined_deferred_module` | 1 | A disclosure is not bound to the module/output it claims is deferred. |
| 16 | High | `test_merge_closure_downgrade_requires_actual_deferred_outputs` | 1 | Merger accepts encoded→pending downgrade without reading module content. |
| 17 | High | `test_merge_closure_exclusion_basis_is_grounded_in_provision_text` | 1 | Merger independently accepts arbitrary exclusion prose. |
| 18 | High | `test_bridge_manifest_population_pin_requires_revision_and_valid_sha` | 1 | One malformed token satisfies the promised revision-plus-digest identity. |
| 19 | High | `test_merge_closure_rejects_invalid_encoded_by` | 3 | Empty, duplicate, or unsafe corrections can be written as encoded. |
| 20 | High | `test_merge_closure_rejects_rows_it_cannot_ingest` | 2 | Malformed classification rows are silently dropped. |
| 21 | High | `test_closure_existing_disclosure_cannot_mask_unrelated_pending_rise` | 1 | Old disclosure can authorize an unrelated reopening under the ratchet. |
| 22 | High | `test_census_row_states_report_chunk_index_binding` | 1 | Current main census omits report/chunk binding and reconciliation state. |
| 23 | Medium | `test_certificate_report_read_and_shape_failures_are_leg_defects` | 3 | Bad report shape can crash the gate instead of producing a stable defect. |
| 24 | Medium | `test_certificate_inline_classifications_without_file_are_always_defective` | 1 | Equal inline counts evade the promised unvalidated-classification defect. |
| 25 | Medium | `test_certificate_disposition_citation_must_be_a_regular_relative_file` | 2 | Directory/non-string citations can raise rather than fail diagnostically. |
| 26 | Medium | `test_certificate_validates_unexplained_count_even_with_empty_counts` | 1 | Malformed unexplained count is skipped on an empty counts map. |
| 27 | Medium | `test_certificate_empty_chunk_directory_does_not_make_slim_report_auditable` | 1 | Empty directory bypasses slim-report auditability. |
| 28 | Medium | `test_merge_closure_encoded_correction_removes_exclusion_fields` | 1 | Encoded correction retains contradictory exclusion reason/basis. |
| 29 | Medium | `test_census_constant_requires_value_present_in_every_case` | 1 | Sparse presence is mislabeled constant across the corpus. |
| 30 | Medium | `test_evidence_cardinality_only_case_requires_unmeasured_rate` | 1 | Verdict-free evidence may claim measured 100% agreement. |
| 31 | Medium | `test_evidence_cardinality_label_requires_well_formed_rows` | 1 | Malformed rows can retain the stronger cardinality label (although validity is false). |
| 32 | Medium | `test_bridge_manifest_inputs_must_be_an_array` | 1 | Scalar input is iterated character-by-character and evades typed duplicate checks. |
| 33 | Medium | `test_bridge_manifest_root_must_be_a_mapping` | 1 | Nonmapping YAML raises before a stable schema finding. |
| 34 | Medium | `test_census_chunk_manifest_hashes_exact_bytes` | 1 | Text decoding normalizes CRLF before hashing the evidence. |
| 35 | Medium | `test_closure_snapshot_provenance_requires_source_path` | 1 | Recorded extraction path is not required, weakening reproduction metadata. |
| 36 | Low | `test_certificate_count_rejects_integral_float` | 1 | Code accepts `1.0` despite the integer-only prose contract. |
| 37 | Documentation | `test_evidence_inline_boolean_case_supports_documented_full_reconciliation` | 1 | PR result and current stricter module contract disagree; one must be corrected. |
| 38 | Documentation | `test_merge_closure_lowers_pending_max_as_docstring_promises` | 1 | Docstring contradicts PR #400 and implementation about the sole ratchet writer. |

## Verification

Run from the audit branch with `.venv/bin/python`:

| Command | Result |
|---|---|
| `pytest -q tests/test_gate_regression_coverage.py` | **275 passed, 46 xfailed** |
| `pytest -q tests/test_certification_mutants.py tests/test_closure_mutants.py tests/test_gate_regression_coverage.py` | **315 passed, 46 xfailed** |
| `scripts/certify.py --check` | PASS — certificates up to date |
| `scripts/exercise_census.py --check` | PASS — census up to date |
| `scripts/validate_bridge_manifests.py` | PASS — 0 errors; 4 printed findings/debts |
| `scripts/closure_universe.py --check` | PASS — 3 roots, 1,156 provisions, 290 pending, `closed=false` |
| Full `pytest -q` | 2,790 passed, 35 skipped, 46 xfailed; one environment failure |

The sole full-suite failure was
`tests/test_dashboard_loader.py::test_loader_equivalence`: `npx esbuild`
attempted to fetch from npm and failed DNS with `ENOTFOUND` in the
network-restricted environment. It is unrelated to these Python-only tests;
the focused suite above includes every changed test and both named legacy
mutant suites.
