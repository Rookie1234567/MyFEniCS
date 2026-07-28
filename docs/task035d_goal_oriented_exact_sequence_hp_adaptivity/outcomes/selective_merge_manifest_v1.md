# Task035d Selective Merge Manifest V1

## 1. Identity and decision

```text
source_branch = codex/20260726-task35d-goal-oriented-exact-sequence-hp-adaptivity
pre_closeout_head = 5af47e7ef7711bc39eeb248742a05f8ba0bf4169
integration_base = origin/master@9c2160d41382026352908d692ad479dc4508424d
registry_backfill = origin/chatgpt/20260726-development-model-registry-backfill@1b98cd9df2b145528673303af3c41d7ade508df5
manifest_rows = 214
include = 119
exclude_keep_source_branch = 95
overall_merge = forbidden
fresh_task035d_pde = not_required_if_files_are_exactly_migrated
```

The containing closeout commit is the source authority for integration. Research-only and do-not-merge files remain reachable on the Task035d branch; they are not deleted.

## 2. Category summary

| category | files | migration decision |
|---|---:|---|
| `production_core` | 23 | `include` |
| `research_api_opt_in` | 6 | `include` |
| `reusable_runner_watchdog` | 2 | `include` |
| `checker_benchmark` | 45 | `include` |
| `compact_evidence_docs` | 43 | `include` |
| `research_only` | 44 | `exclude_keep_source_branch` |
| `do_not_merge` | 51 | `exclude_keep_source_branch` |

## 3. Dependency order and PDE rule

1. Three-way registry backfill and Markdown contracts.
2. Variable-p/exact-sequence core.
3. Local-h/hanging/Floquet core.
4. Stage4/DtN explicit-opt-in integration.
5. Hybrid collective bug fix as an isolated change.
6. Research adjoint/DWR APIs.
7. Reusable runner/watchdog, checkers, tests, compact evidence, and docs.

Exact file migration does not change the reviewed numerical blob, so the Task035d heavy PDE is not rerun. Any conflict resolution that changes a local tensor, active expansion, hanging/Floquet graph, DtN, static condensation, recovery, or official postprocess triggers the minimum formal anchor required by Review V1.

## 4. File-level manifest

| path | status | category | action | dependency group | tests | fresh PDE |
|---|---|---|---|---|---|---|
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/README.md` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/analyze_bounded_single_seed_top_air_hp_selection.py` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/analyze_hp_factorial_bridge.py` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/analyze_outer_top_hp_selection.py` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/check_local_h_attempt2_authority.py` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/check_local_h_production_authority.py` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/config.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/expected.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_bounded_single_seed_top_air_hp_preflight.py` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_legacy_seeded_plans.py` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_local_h_attempt1_authority.py` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_local_h_attempt2_authority.py` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_local_h_production_authority.py` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_physics_guard_recovery.py` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_reference_authority.py` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_selective_face_selection_compact.py` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/bounded_single_root_top_air_lane_closure_v1.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/bounded_single_seed_top_air_hp_preflight_v1.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/bounded_single_seed_top_air_hp_selection_v2.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/combined_hp_interior_mpi1_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/combined_hp_interior_mpi1_v2.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/combined_hp_interior_mpi2_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/combined_hp_interior_mpi2_v2.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/combined_hp_interior_mpi8_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/combined_hp_interior_mpi8_v2.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/combined_hp_interior_mpi_identity_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/combined_hp_interior_mpi_identity_v2.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/compact_authority_v1.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/h15_grating_top_selective_p6_faces_plan_v1.json` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/h15_left_grating_top_closure_p5fine_compact_checker_evidence_failure_v1.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/h15_left_grating_top_closure_p5fine_mpi8_candidate_check_v1.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/h15_left_grating_top_closure_p5fine_mpi8_controlled_negative_compact_v1.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/h15_left_grating_top_closure_p5fine_plan_v1.json` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/h15_outer_top_periodic_p5fine_plan_v1.json` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/h15_symmetric_top_air_remote_p5_interior_mpi8_candidate_check_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/h15_symmetric_top_air_remote_p5_interior_mpi8_candidate_check_v2.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/h15_symmetric_top_air_remote_p5_interior_mpi8_residual_controlled_negative_v1.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/h15_symmetric_top_air_remote_p5_interior_plan_v1.json` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/h15_top_air_local_h_field_probe_evidence_failure_v1.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/h15_top_air_local_h_mpi8_controlled_negative_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/h15_top_air_local_h_nested_p_mpi8_controlled_negative_v2.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/h15_top_air_local_h_plan_v1.json` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/h15_top_air_nested_p_dwr_mpi8_checker_v2.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/h15_top_air_nested_p_pair_authority_v1.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/h15_top_air_remote_p5_interior_bridge_mpi8_candidate_check_v1.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/h15_top_air_remote_p5_interior_bridge_plan_v1.json` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/h15_top_air_selective_p6_face_component_mpi2_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/h15_top_air_selective_p6_face_component_mpi8_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/hp_factorial_bridge_attribution_v1.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/hp_factorial_bridge_mpi1_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/hp_factorial_bridge_mpi2_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/hp_factorial_bridge_mpi8_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/hp_factorial_bridge_mpi_identity_v1.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/left_grating_top_closure_p5fine_mpi1_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/left_grating_top_closure_p5fine_mpi2_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/left_grating_top_closure_p5fine_mpi8_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/left_grating_top_closure_p5fine_mpi_identity_v1.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/legacy_multigoal_seed_v1.json` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/legacy_seeded_plan_authority_mpi1_v1.json` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/legacy_seeded_plan_authority_mpi2_v1.json` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/legacy_seeded_plan_authority_mpi8_v1.json` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/local_h_attempt1_mpi1_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/local_h_attempt1_mpi2_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/local_h_attempt1_mpi8_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/local_h_attempt1_mpi_identity_v1.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/local_h_attempt2_mpi1_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/local_h_attempt2_mpi1_v2.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/local_h_attempt2_mpi1_v3.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/local_h_attempt2_mpi2_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/local_h_attempt2_mpi2_v2.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/local_h_attempt2_mpi2_v3.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/local_h_attempt2_mpi8_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/local_h_attempt2_mpi8_v2.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/local_h_attempt2_mpi8_v3.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/local_h_attempt2_mpi_identity_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/local_h_attempt2_mpi_identity_v2.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/local_h_attempt2_mpi_identity_v2_checker_fix1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/local_h_attempt2_mpi_identity_v3.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/local_h_production_mpi1_v3_integration.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/local_h_production_mpi1_v3_owner_gate_fix1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/local_h_production_mpi2_v3_integration_controlled_failure.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/local_h_production_mpi2_v3_owner_gate_fix1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/local_h_production_mpi8_v3_owner_gate_fix1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/local_h_production_mpi_identity_v3_owner_gate_fix1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/local_h_production_mpi_identity_v3_owner_gate_fix2.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/mixed_p5_p6_h100_component_mpi1_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/mixed_p5_p6_h100_component_mpi2_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/mpi2_fixture_authority_v1.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/outer_top_periodic_p5fine_mpi1_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/outer_top_periodic_p5fine_mpi1_v2.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/outer_top_periodic_p5fine_mpi2_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/outer_top_periodic_p5fine_mpi2_v2.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/outer_top_periodic_p5fine_mpi8_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/outer_top_periodic_p5fine_selection_v1.json` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/outer_top_periodic_p5fine_superseded_controlled_stop_v2.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/outer_top_periodic_p5fine_writer_race_controlled_failure_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/p6_h100_variable_p_component_anchor_v2.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/p6_h100_variable_p_live_observer_mpi2_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/physics_guard_plan_authority_mpi1_v1.json` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/physics_guard_plan_authority_mpi2_v1.json` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/physics_guard_plan_authority_mpi8_v1.json` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/reference_active_space_authority_v1.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/selective_face_selection_compact_v1.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/selective_p6_face_mpi1_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/selective_p6_face_mpi2_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/selective_p6_face_mpi8_v1.json` | `A` | `do_not_merge` | `exclude_keep_source_branch` | `superseded_or_redundant_record` | not migrated | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/selective_p6_face_mpi_identity_v1.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/sidewall_z0_guard_h10_cell_degree_plan_v1.json` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/sidewall_z0_guard_h10_mpi8_controlled_negative_v1.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/t15_h10_cell_degree_plan_v1.json` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/t25_h10_cell_degree_plan_v1.json` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/t30_h10_cell_degree_plan_v1.json` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/t30_h10_mpi8_controlled_negative_v1.json` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/records/t30_regional_probe_error_localization_v1.json` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/test_command.txt` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `benchmarks/check_development_model_registry.py` | `M` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `benchmarks/run_direct_memory_forensics.py` | `M` | `reusable_runner_watchdog` | `include` | `runner_watchdog_telemetry` | 28,68,193 | no |
| `benchmarks/run_task033_full3d_watchdog.py` | `M` | `reusable_runner_watchdog` | `include` | `runner_watchdog_telemetry` | 28,68,193 | no |
| `benchmarks/task035d_case097_checker.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `benchmarks/task035d_case097_gates.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `benchmarks/task035d_nested_p_dwr_checker.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `benchmarks/task035d_nested_p_snapshot_gate.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `benchmarks/task035d_selective_face_case097_gates.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `benchmarks/task035d_selective_face_complement.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `benchmarks/task035d_selective_face_dwr_checker.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `benchmarks/task035d_selective_face_snapshot_gate.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `docs/development_model_registry.md` | `M` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `docs/task035d_goal_oriented_exact_sequence_hp_adaptivity/README.md` | `M` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `docs/task035d_goal_oriented_exact_sequence_hp_adaptivity/outcomes/selective_merge_manifest_v1.csv` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `docs/task035d_goal_oriented_exact_sequence_hp_adaptivity/outcomes/selective_merge_manifest_v1.md` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `docs/task035d_goal_oriented_exact_sequence_hp_adaptivity/outcomes/summary.md` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `docs/task035d_goal_oriented_exact_sequence_hp_adaptivity/outcomes/test_summary.md` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `docs/task035d_goal_oriented_exact_sequence_hp_adaptivity/response_v1.md` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `docs/task035d_goal_oriented_exact_sequence_hp_adaptivity/review_report_v1.md` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `docs/task035d_goal_oriented_exact_sequence_hp_adaptivity/task.md` | `M` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `docs/task035e_reference_blind_multilevel_hp_adaptivity/README.md` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `docs/task035e_reference_blind_multilevel_hp_adaptivity/task.md` | `A` | `compact_evidence_docs` | `include` | `compact_evidence_and_docs` | documentation, registry, JSON, Case097 compact contracts | no |
| `src/adaptivity/dtn_goal_adjoint.py` | `M` | `research_api_opt_in` | `include` | `adjoint_dwr_research_api` | 204-213 | no; qualify when first used as a formal selector |
| `src/adaptivity/dyadic_hexa_broken_mesh.py` | `A` | `production_core` | `include` | `local_h_hanging_floquet_core` | 196-201,203; MPI8 representative | no if exact blob; yes if graph/tensor/recovery conflict changes |
| `src/adaptivity/dyadic_hexa_refinement.py` | `A` | `production_core` | `include` | `local_h_hanging_floquet_core` | 196-201,203; MPI8 representative | no if exact blob; yes if graph/tensor/recovery conflict changes |
| `src/adaptivity/exact_sequence_variable_p.py` | `A` | `production_core` | `include` | `variable_p_exact_sequence_core` | 178,183-190,192; MPI8 representative | no if exact blob; yes if expansion/tensor/recovery conflict changes |
| `src/adaptivity/hcurl_broken_cell_trace.py` | `A` | `production_core` | `include` | `local_h_hanging_floquet_core` | 196-201,203; MPI8 representative | no if exact blob; yes if graph/tensor/recovery conflict changes |
| `src/adaptivity/hcurl_broken_trace_graph.py` | `A` | `production_core` | `include` | `local_h_hanging_floquet_core` | 196-201,203; MPI8 representative | no if exact blob; yes if graph/tensor/recovery conflict changes |
| `src/adaptivity/hcurl_hanging_trace.py` | `A` | `production_core` | `include` | `local_h_hanging_floquet_core` | 196-201,203; MPI8 representative | no if exact blob; yes if graph/tensor/recovery conflict changes |
| `src/adaptivity/hcurl_trace_constraint_graph.py` | `A` | `production_core` | `include` | `variable_p_exact_sequence_core` | 178,183-190,192; MPI8 representative | no if exact blob; yes if expansion/tensor/recovery conflict changes |
| `src/adaptivity/high_order_same_error.py` | `M` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/adaptivity/legacy_seeded_variable_p.py` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `src/adaptivity/nested_p_dwr.py` | `A` | `research_api_opt_in` | `include` | `adjoint_dwr_research_api` | 204-213 | no; qualify when first used as a formal selector |
| `src/adaptivity/physics_guard_variable_p.py` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `src/adaptivity/selective_face_complement.py` | `A` | `research_api_opt_in` | `include` | `adjoint_dwr_research_api` | 204-213 | no; qualify when first used as a formal selector |
| `src/adaptivity/selective_face_root_transfer.py` | `A` | `research_api_opt_in` | `include` | `adjoint_dwr_research_api` | 204-213 | no; qualify when first used as a formal selector |
| `src/adaptivity/stage4_local_h.py` | `A` | `production_core` | `include` | `local_h_hanging_floquet_core` | 196-201,203; MPI8 representative | no if exact blob; yes if graph/tensor/recovery conflict changes |
| `src/adaptivity/variable_p_degree_plan.py` | `A` | `production_core` | `include` | `variable_p_exact_sequence_core` | 178,183-190,192; MPI8 representative | no if exact blob; yes if expansion/tensor/recovery conflict changes |
| `src/adaptivity/variable_p_entity_map.py` | `A` | `production_core` | `include` | `variable_p_exact_sequence_core` | 178,183-190,192; MPI8 representative | no if exact blob; yes if expansion/tensor/recovery conflict changes |
| `src/adaptivity/variable_p_nested_dwr.py` | `A` | `research_api_opt_in` | `include` | `adjoint_dwr_research_api` | 204-213 | no; qualify when first used as a formal selector |
| `src/adaptivity/variable_p_periodic_orbits.py` | `A` | `production_core` | `include` | `variable_p_exact_sequence_core` | 178,183-190,192; MPI8 representative | no if exact blob; yes if expansion/tensor/recovery conflict changes |
| `src/adaptivity/variable_p_selective_face_dwr.py` | `A` | `research_api_opt_in` | `include` | `adjoint_dwr_research_api` | 204-213 | no; qualify when first used as a formal selector |
| `src/adaptivity/variable_p_transfer.py` | `A` | `production_core` | `include` | `variable_p_exact_sequence_core` | 178,183-190,192; MPI8 representative | no if exact blob; yes if expansion/tensor/recovery conflict changes |
| `src/common/config_3d.py` | `M` | `production_core` | `include` | `stage4_dtn_integration` | 178,190,192-194; Case094-097 checkers | no if exact blob; yes if DtN/postprocess conflict changes |
| `src/geometry/mesh_builder_3d.py` | `M` | `production_core` | `include` | `stage4_dtn_integration` | 178,190,192-194; Case094-097 checkers | no if exact blob; yes if DtN/postprocess conflict changes |
| `src/main.py` | `M` | `production_core` | `include` | `stage4_dtn_integration` | 178,190,192-194; Case094-097 checkers | no if exact blob; yes if DtN/postprocess conflict changes |
| `src/runners/run_3d_cases.py` | `M` | `production_core` | `include` | `stage4_dtn_integration` | 178,190,192-194; Case094-097 checkers | no if exact blob; yes if DtN/postprocess conflict changes |
| `src/solvers/common_3d_case_flow.py` | `M` | `production_core` | `include` | `stage4_dtn_integration` | 178,190,192-194; Case094-097 checkers | no if exact blob; yes if DtN/postprocess conflict changes |
| `src/solvers/dtn_port_3d.py` | `M` | `production_core` | `include` | `stage4_dtn_integration` | 178,190,192-194; Case094-097 checkers | no if exact blob; yes if DtN/postprocess conflict changes |
| `src/solvers/hcurl_variable_p_assembly.py` | `A` | `production_core` | `include` | `variable_p_exact_sequence_core` | 178,183-190,192; MPI8 representative | no if exact blob; yes if expansion/tensor/recovery conflict changes |
| `src/solvers/hcurl_variable_p_local.py` | `A` | `production_core` | `include` | `variable_p_exact_sequence_core` | 178,183-190,192; MPI8 representative | no if exact blob; yes if expansion/tensor/recovery conflict changes |
| `src/solvers/hcurl_variable_p_reduction.py` | `A` | `production_core` | `include` | `variable_p_exact_sequence_core` | 178,183-190,192; MPI8 representative | no if exact blob; yes if expansion/tensor/recovery conflict changes |
| `src/solvers/hybrid_local_dtn.py` | `M` | `production_core` | `include` | `hybrid_collective_bugfix` | Task032/033/035b Hybrid targeted | no; historical Hybrid PDE remains bound to original SHA |
| `src/solvers/solve_maxwell_3d_stage_4b_block_grating.py` | `M` | `production_core` | `include` | `stage4_dtn_integration` | 178,190,192-194; Case094-097 checkers | no if exact blob; yes if DtN/postprocess conflict changes |
| `src/test/test_178_task035b_public_assembly_backend.py` | `M` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_183_development_model_registry_markdown.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_183_task035d_reference_active_space.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_184_task035d_global_entity_numbering.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_185_task035d_variable_p_petsc_assembly.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_186_task035d_variable_p_transfer.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_187_task035d_variable_p_compiled_kernel.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_188_task035d_variable_p_degree_plan.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_189_task035d_variable_p_reduction.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_190_task035d_variable_p_stage4_smoke.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_191_task035d_legacy_seeded_selector.py` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `src/test/test_192_task035d_mixed_variable_p_stage4.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_193_task035d_case097_runner_gates.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_194_task035d_case097_checker.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_195_task035d_physics_guard_selector.py` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `src/test/test_196_task035d_dyadic_hexa_local_h.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_197_task035d_hanging_trace.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_198_task035d_broken_dyadic_hexa.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_199_task035d_trace_constraint_graph.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_200_task035d_broken_trace_graph.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_201_task035d_broken_cell_trace.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_202_task035d_factorial_bridge.py` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `src/test/test_202_task035d_local_h_attempt2_authority.py` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `src/test/test_203_task035d_stage4_local_h.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_204_task035d_variable_p_adjoint_recovery.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_205_task035d_unit_channel_adjoint_basis.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_206_task035d_variable_p_live_observer.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_207_task035d_nested_p_dwr.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_208_task035d_variable_p_nested_dwr_live.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_209_task035d_nested_p_runner.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_210_task035d_nested_p_dwr_checker.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_211_task035d_selective_face_complement.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_212_task035d_selective_face_root_transfer.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_213_task035d_selective_face_snapshot.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_214_task035d_selective_face_candidate.py` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `src/test/test_215_task035d_selective_face_runner_checker.py` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `src/test/test_216_task035d_outer_top_hp_candidate.py` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `src/test/test_217_task035d_authority_binding.py` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `src/test/test_218_task035d_left_grating_top_hp_candidate.py` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `src/test/test_26_documentation_contract.py` | `M` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_28_direct_memory_telemetry.py` | `M` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_68_task033_full3d_watchdog.py` | `M` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_case097_compact_evidence_contract.py` | `A` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |
| `src/test/test_case097_local_h_attempt1_contract.py` | `A` | `research_only` | `exclude_keep_source_branch` | `candidate_specific_research_history` | historical branch receipts | not applicable |
| `src/test/test_development_model_registry_contract.py` | `M` | `checker_benchmark` | `include` | `checker_and_contract_tests` | self + focused/full repository suite | no unless official postprocess algorithm changes |

## 5. Diff-check contract

The CSV is authoritative for automation. Integration must compare its `include` paths exactly against the final `master...integration` diff; zero missing, zero extra, and zero research-only/do-not-merge paths are allowed.
