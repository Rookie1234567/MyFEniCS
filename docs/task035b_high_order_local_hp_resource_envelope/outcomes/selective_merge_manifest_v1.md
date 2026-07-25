# Task035b file-level selective merge manifest v1

- base SHA: `5002636852ffb67b4711443da70eb536c303e34e`
- source branch: `codex/20260723-task35b-high-order-local-hp-resource-envelope`
- diff/untracked paths classified: `403`
- rule: CSV is the machine-readable authority; every changed path is listed exactly once.
- safety: rows whose reason says surgery/sanitize may not be copied wholesale; the integration branch must contain the reviewed successor blob and the manifest must be regenerated there.

## 分类统计

| dependency_group | files |
|---|---:|
| `production_core` | 35 |
| `research_api_opt_in` | 21 |
| `reusable_benchmark` | 14 |
| `compact_evidence` | 28 |
| `project_docs` | 51 |
| `do_not_merge` | 254 |

## 文件级明细

| path | dependency_group | ordinary default | merge order | reason |
|---|---|---|---|---|
| `.gitignore` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `AGENTS.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/README.md` | `reusable_benchmark` | `no` | `70` | compact benchmark contract/checker; rewrite stale commands or phase-A assumptions before migration |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/config.json` | `reusable_benchmark` | `no` | `70` | compact benchmark contract/checker; rewrite stale commands or phase-A assumptions before migration |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/expected.json` | `reusable_benchmark` | `no` | `70` | compact benchmark contract/checker; rewrite stale commands or phase-A assumptions before migration |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_common_mesh_grazing_1_5_10_p4_p5_h50_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_combined_adaptive_tetra_p2_p3_h50_cycle2_canonical_contiguous_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_combined_adaptive_tetra_p2_p3_h50_theta0p5_0p5_0p15_cycle3_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_combined_adaptive_tetra_p3_p4_h50_cycle2_canonical_contiguous_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_multigoal_normalized_tetra_p4_p5_h37p5_theta0p7_cycle1_full_periodic_closure_mpi8.json` | `compact_evidence` | `no` | `80` | minimal hash-bound authority record selected by Review V3 |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_r_adaptive_tetra_p2_p3_h50_cycle1_mpi2.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_r_adaptive_tetra_p2_p3_h50_cycle2_canonical_contiguous_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_r_adaptive_tetra_p3_p4_h50_cycle1_canonical_connectivity_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_r_adaptive_tetra_p3_p4_h50_cycle1_canonical_connectivity_repeat_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_r_adaptive_tetra_p3_p4_h50_cycle1_canonical_contiguous_balanced_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_r_adaptive_tetra_p3_p4_h50_cycle1_canonical_contiguous_balanced_repeat_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_r_adaptive_tetra_p3_p4_h50_cycle1_canonical_contiguous_floquet_robust_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_r_adaptive_tetra_p3_p4_h50_cycle1_canonical_contiguous_incoming_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_r_adaptive_tetra_p3_p4_h50_cycle1_canonical_contiguous_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_r_adaptive_tetra_p3_p4_h50_cycle1_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_r_adaptive_tetra_p3_p4_h50_cycle1_repeat_current_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_r_adaptive_tetra_p3_p4_h50_cycle1_scotch_seed0_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_r_adaptive_tetra_p3_p4_h50_cycle1_scotch_seed0_repeat_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_r_adaptive_tetra_p3_p4_h50_cycle2_minimal_periodic_closure_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_r_adaptive_tetra_p3_p4_h50_cycle2_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_r_adaptive_tetra_p3_p4_h50_cycle2_tie_stable_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_r_adaptive_tetra_p3_p4_h50_cycle3_minimal_periodic_closure_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_r_adaptive_tetra_p3_p4_h50_theta0p3_cycle1_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_r_adaptive_tetra_p3_p4_h50_theta0p5_0p15_cycle2_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_r_adaptive_tetra_p4_p5_h37p5_theta0p7_cycle1_full_periodic_closure_mpi8.json` | `compact_evidence` | `no` | `80` | minimal hash-bound authority record selected by Review V3 |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_r_adaptive_tetra_p4_p5_h50_cycle1_full_periodic_closure_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_r_adaptive_tetra_p4_p5_h50_cycle2_minimal_periodic_closure_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_r_adaptive_tetra_p4_p5_h50_theta0p4_cycle1_full_periodic_closure_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_r_adaptive_tetra_p4_p5_h50_theta0p7_cycle1_full_periodic_closure_mpi8.json` | `compact_evidence` | `no` | `80` | minimal hash-bound authority record selected by Review V3 |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_dwr_r_adaptive_watchdog_compaction_failure.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_global_r5_p2_p3_h10_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_global_r5_tetra_p2_p3_h50_mpi2.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_hp_budget_theta0p3_tetra_p5_p6_h50_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_hp_budget_theta0p3_tetra_p5_p6_h50_mpi8_recovered.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_hp_budget_theta0p4_tetra_p5_p6_h50_mpi8.json` | `compact_evidence` | `no` | `80` | minimal hash-bound authority record selected by Review V3 |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_r5_adaptive_tetra_p2_p3_h50_cycle1_mpi2.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_r5_adaptive_tetra_p2_p3_h50_cycle2_deterministic_mpi2.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_r5_adaptive_tetra_p2_p3_h50_cycle2_reference_gate_mpi2.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_uniform_tetra_level1_p2_p3_mpi2.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_uniform_tetra_level1_p3_p4_mpi2.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_uniform_tetra_level1_p3_p4_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_uniform_tetra_level1_p4_p5_mpi8.json` | `compact_evidence` | `no` | `80` | minimal hash-bound authority record selected by Review V3 |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/actual_uniform_tetra_level2_p2_p3_mpi2.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/base_manifest.json` | `compact_evidence` | `no` | `80` | minimal hash-bound authority record selected by Review V3 |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/fixture_summary.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/high_order_full_regression_classifier_failure.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/phase_a_regression_failure.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/phase_b_regression_failure.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/phase_b_regression_recovery.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/phase_c_low_cost_entry.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/phase_cd_mpi1.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/phase_cd_mpi2.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/phase_cd_mpi2_initial_volume_measurement_failure.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/phase_cd_mpi_identity.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/real_fe_mpi1.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/real_fe_mpi2.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/real_fe_mpi_identity.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/094_hcurl_goal_oriented_adaptivity/test_command.txt` | `reusable_benchmark` | `no` | `70` | compact benchmark contract/checker; rewrite stale commands or phase-A assumptions before migration |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/README.md` | `reusable_benchmark` | `no` | `70` | compact benchmark contract/checker; rewrite stale commands or phase-A assumptions before migration |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/config.json` | `reusable_benchmark` | `no` | `70` | compact benchmark contract/checker; rewrite stale commands or phase-A assumptions before migration |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/actual_sequential_h_vs_p_competition_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/channel_phase_dispersion_diagnostic_v1.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/channel_response_matrix_directionality_v1.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/compact_authority_v1.json` | `compact_evidence` | `no` | `80` | minimal hash-bound authority record selected by Review V3 |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/condensed_iterative_failed_output_caveat_v1.json` | `compact_evidence` | `no` | `80` | compact controlled-negative/capability evidence; documentation authority only |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/condensed_trace_iterative_capability_gate.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/dtn_port_phase_authority_v1.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h13_directional_z_mpi8.json` | `compact_evidence` | `no` | `80` | minimal hash-bound authority record selected by Review V3 |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h13_top2_phase_redistribution_mpi8_v1.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h14_directional_z_mpi8.json` | `compact_evidence` | `no` | `80` | minimal hash-bound authority record selected by Review V3 |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h14_exact_reverse_h13_top2_mpi8_v1.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h14_r5_slab_bisect_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h15_channel_adjoints_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h15_channel_adjoints_verification_v2_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h15_directional_x_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h15_dtn_evanescent_buffer1_scaled_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h15_dtn_q31_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h15_mpi8.json` | `compact_evidence` | `no` | `80` | minimal hash-bound authority record selected by Review V3 |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h15_tensor_dedup_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h15_tensor_dedup_preallocation_mpi8.json` | `compact_evidence` | `no` | `80` | minimal hash-bound authority record selected by Review V3 |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_trace_h15_evanescent_buffer1_preflight_controlled_stop.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p1_p6_h10_p6_assembly_time_condensed_independent_mpi8.json` | `compact_evidence` | `no` | `80` | minimal hash-bound authority record selected by Review V3 |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p1_p6_h10_p6_assembly_time_condensed_independent_released_without_heap_trim_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p1_p6_h10_p6_assembly_time_condensed_independent_retained_postprocess_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p4_p5_h10_assembly_time_condensed_independent_mpi8.json` | `compact_evidence` | `no` | `80` | minimal hash-bound authority record selected by Review V3 |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p4_p5_h10_mpi8.json` | `compact_evidence` | `no` | `80` | minimal hash-bound authority record selected by Review V3 |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p4_p5_h15_directional_y_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p5_p6_h10_assembly_time_condensed_independent_mpi8.json` | `compact_evidence` | `no` | `80` | minimal hash-bound authority record selected by Review V3 |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p5_p6_h10_mpi8.json` | `compact_evidence` | `no` | `80` | minimal hash-bound authority record selected by Review V3 |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p5_p6_h10_p6_condensed_independent_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p5_p6_h10_p6_condensed_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p5_p6_h10_projection_signals_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p5_p6_h14_assembly_time_condensed_independent_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p5_p6_h15_assembly_time_condensed_independent_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p6_h15_vs_h10_same_error_audit.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_p6_h14_trace_discriminator.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h13_canonical_orientation_symbolic_numeric_cold_warm_mpi8_v1.json` | `compact_evidence` | `no` | `80` | minimal hash-bound authority record selected by Review V3 |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_canonical_orientation_symbolic_numeric_cold_warm_mpi8_v1.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_canonical_orientation_symbolic_numeric_cold_warm_mpi8_v2.json` | `compact_evidence` | `no` | `80` | minimal hash-bound authority record selected by Review V3 |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_condensed_cache_cold_warm_mpi8_v1.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_condensed_cache_deterministic_cold_warm_mpi8_v3.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_condensed_cache_partition_drift_controlled_negative_v2.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_condensed_cache_rank_independent_cold_warm_mpi8_v2.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_condensed_cache_rank_partition_controlled_negative_v1.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_direct_cold_mpi8_parent_record_writer_infrastructure_negative_v1.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_direct_mpi1_2_4_8_resource_floor_v1.json` | `compact_evidence` | `no` | `80` | minimal hash-bound authority record selected by Review V3 |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_factor_free_iterative_mpi8_v1.json` | `compact_evidence` | `no` | `80` | compact controlled-negative/capability evidence; documentation authority only |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_memory_floor_factor_inventory_ledger_v2.json` | `compact_evidence` | `no` | `80` | minimal hash-bound authority record selected by Review V3 |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_physical_slab_dtn_and_trace_harmonic_iterative_capability_v2.json` | `do_not_merge` | `no` | `never` | failed condensed iterative profile; retain only compact negative evidence |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_physical_slab_dtn_and_trace_harmonic_iterative_capability_v3.json` | `do_not_merge` | `no` | `never` | failed condensed iterative profile; retain only compact negative evidence |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_physical_slab_dtn_and_trace_harmonic_iterative_capability_v3_stage4_recertification.json` | `do_not_merge` | `no` | `never` | failed condensed iterative profile; retain only compact negative evidence |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_physical_slab_dtn_iterative_capability_v1.json` | `do_not_merge` | `no` | `never` | failed condensed iterative profile; retain only compact negative evidence |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_physical_slab_dtn_iterative_formal_screen_mpi8_v2.json` | `compact_evidence` | `no` | `80` | compact controlled-negative/capability evidence; documentation authority only |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_solve_thread_memory_semantics_audit_v1.json` | `compact_evidence` | `no` | `80` | minimal hash-bound authority record selected by Review V3 |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/inverse_trace_interior_budget_exchange_preflight.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/manufactured_rayleigh_port_authority_v1.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/missing_p6_trace_complement_preflight_v1.json` | `do_not_merge` | `no` | `never` | production selective-trace capability is not closed and is explicitly excluded |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/missing_p6_trace_complement_preflight_v2.json` | `do_not_merge` | `no` | `never` | production selective-trace capability is not closed and is explicitly excluded |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/p7_h10_capability_resource_gate.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/physical_selective_trace_execution_capability_v2.json` | `compact_evidence` | `no` | `80` | compact controlled-negative/capability evidence; documentation authority only |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/physical_trace_lane_capability_gate.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/regionwise_p4trace_p6interior_h10_mpi8.json` | `do_not_merge` | `no` | `never` | regionwise/non-exact-sequence local-p capability is not qualified |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/regionwise_p5trace_p4low_p6high_n62_h10_mpi8.json` | `do_not_merge` | `no` | `never` | regionwise/non-exact-sequence local-p capability is not qualified |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/regionwise_p5trace_p4low_p6high_n62_h10_mpi8_postprocess_failure.json` | `do_not_merge` | `no` | `never` | regionwise/non-exact-sequence local-p capability is not qualified |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/regionwise_p5trace_p4low_p6high_n62_h10_mpi8_wrong_control_preflight_failure.json` | `do_not_merge` | `no` | `never` | regionwise/non-exact-sequence local-p capability is not qualified |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/regionwise_p_exact_sequence_structural_audit.json` | `do_not_merge` | `no` | `never` | regionwise/non-exact-sequence local-p capability is not qualified |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/same_mesh_hexa_p4_p5_goal_dwr_h10_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/same_mesh_p4_p5_p6_multigoal_hp_classifier_v2.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/same_mesh_p4_p5_p6_multigoal_hp_classifier_v3.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/same_mesh_p4_p5_p6_r5_hp_classifier_mpi8.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/significant_channel_reference_v1.json` | `compact_evidence` | `no` | `80` | minimal hash-bound authority record selected by Review V3 |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/task035b_successor_bindings.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/y_only_global_p5_directional_control_comparison_v1.json` | `do_not_merge` | `no` | `never` | duplicate or superseded raw research record; compact authority selected separately |
| `benchmarks/cases/095_high_order_local_hp_resource_envelope/test_command.txt` | `reusable_benchmark` | `no` | `70` | compact benchmark contract/checker; rewrite stale commands or phase-A assumptions before migration |
| `benchmarks/check_case095_compact_evidence.py` | `reusable_benchmark` | `no` | `70` | compact benchmark contract/checker; rewrite stale commands or phase-A assumptions before migration |
| `benchmarks/check_development_model_registry.py` | `reusable_benchmark` | `no` | `70` | reusable checker, resource telemetry, or contract test |
| `benchmarks/check_selective_merge_manifest.py` | `do_not_merge` | `no` | `never` | not in the reviewed file-level allowlist or requires an extracted successor |
| `benchmarks/run_direct_memory_forensics.py` | `reusable_benchmark` | `no` | `70` | reusable checker, resource telemetry, or contract test |
| `benchmarks/run_task035_actual_r5.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `benchmarks/run_task035b_condensed_iterative.py` | `do_not_merge` | `no` | `never` | failed condensed iterative profile; retain only compact negative evidence |
| `benchmarks/run_task035b_direct_setup_profile.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `benchmarks/task034_numerical_blob_checker.py` | `reusable_benchmark` | `no` | `70` | reusable checker, resource telemetry, or contract test |
| `benchmarks/task035_case094.py` | `reusable_benchmark` | `no` | `70` | compact benchmark contract/checker; rewrite stale commands or phase-A assumptions before migration |
| `benchmarks/task035_component_fixtures.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `benchmarks/task035_estimator_fixtures.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `benchmarks/task035_low_cost_bakeoff.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `benchmarks/task035_mesh_backend_bakeoff.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `benchmarks/task035_phase_cd.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `benchmarks/task035_real_fe_fixtures.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `benchmarks/task035_target_artifact_bakeoff.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `benchmarks/task035b_channel_phase_dispersion.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `benchmarks/task035b_channel_response_matrix.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `benchmarks/task035b_condensed_iterative_capability_gate.py` | `do_not_merge` | `no` | `never` | failed condensed iterative profile; retain only compact negative evidence |
| `benchmarks/task035b_dtn_port_phase_authority.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `benchmarks/task035b_fixed_trace_port_preflight.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `benchmarks/task035b_global_p6_h14_trace_discriminator.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `benchmarks/task035b_hp_classifier.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `benchmarks/task035b_hp_competition.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `benchmarks/task035b_inverse_budget_exchange_preflight.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `benchmarks/task035b_manufactured_rayleigh_port_authority.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `benchmarks/task035b_missing_p6_trace_preflight.py` | `do_not_merge` | `no` | `never` | production selective-trace capability is not closed and is explicitly excluded |
| `benchmarks/task035b_multigoal_hp_classifier.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `benchmarks/task035b_p7_capability_resource_gate.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `benchmarks/task035b_physical_trace_lane_capability_gate.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `benchmarks/task035b_regionwise_space_audit.py` | `do_not_merge` | `no` | `never` | regionwise/non-exact-sequence local-p capability is not qualified |
| `benchmarks/task035b_same_error.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `benchmarks/task035b_significant_channel_reference.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `benchmarks/task035b_y_directional_control.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `conftest.py` | `do_not_merge` | `no` | `never` | not in the reviewed file-level allowlist or requires an extracted successor |
| `docs/AGENTS.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/COMSOL_direct_solver_report.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/README.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/capability_matrix.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/development_model_registry.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/development_progress.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/project_service_requirements_phase1_scope.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/solver_guide.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035_hcurl_goal_oriented_adaptivity/AGENTS.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035_hcurl_goal_oriented_adaptivity/README.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035_hcurl_goal_oriented_adaptivity/outcomes/environment_and_base.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035_hcurl_goal_oriented_adaptivity/outcomes/estimator_definitions.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035_hcurl_goal_oriented_adaptivity/outcomes/fixture_matrix.csv` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035_hcurl_goal_oriented_adaptivity/outcomes/fixture_matrix.json` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035_hcurl_goal_oriented_adaptivity/outcomes/summary.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035_hcurl_goal_oriented_adaptivity/outcomes/test_summary.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035_hcurl_goal_oriented_adaptivity/response_v1.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035_hcurl_goal_oriented_adaptivity/response_v2.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035_hcurl_goal_oriented_adaptivity/response_v3.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035_hcurl_goal_oriented_adaptivity/response_v4.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035_hcurl_goal_oriented_adaptivity/response_v5.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035_hcurl_goal_oriented_adaptivity/review_report_v1.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035_hcurl_goal_oriented_adaptivity/review_report_v2.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035_hcurl_goal_oriented_adaptivity/review_report_v3.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035_hcurl_goal_oriented_adaptivity/review_report_v4.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035_hcurl_goal_oriented_adaptivity/review_report_v5.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035_hcurl_goal_oriented_adaptivity/review_report_v6.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035b_high_order_local_hp_resource_envelope/README.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035b_high_order_local_hp_resource_envelope/outcomes/all_candidates.csv` | `compact_evidence` | `no` | `80` | minimal hash-bound authority record selected by Review V3 |
| `docs/task035b_high_order_local_hp_resource_envelope/outcomes/all_candidates.json` | `compact_evidence` | `no` | `80` | minimal hash-bound authority record selected by Review V3 |
| `docs/task035b_high_order_local_hp_resource_envelope/outcomes/high_p_memory_anatomy.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035b_high_order_local_hp_resource_envelope/outcomes/irregular_geometry_transfer.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035b_high_order_local_hp_resource_envelope/outcomes/local_hp_capability.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035b_high_order_local_hp_resource_envelope/outcomes/negative_results.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035b_high_order_local_hp_resource_envelope/outcomes/reference_and_resource_target.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035b_high_order_local_hp_resource_envelope/outcomes/regular_geometry_compression.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035b_high_order_local_hp_resource_envelope/outcomes/resource_projection_0p7nm.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035b_high_order_local_hp_resource_envelope/outcomes/selective_merge_manifest_v1.csv` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035b_high_order_local_hp_resource_envelope/outcomes/selective_merge_manifest_v1.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035b_high_order_local_hp_resource_envelope/outcomes/significant_channel_convergence.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035b_high_order_local_hp_resource_envelope/outcomes/summary.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035b_high_order_local_hp_resource_envelope/outcomes/test_summary.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035b_high_order_local_hp_resource_envelope/response_v1.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035b_high_order_local_hp_resource_envelope/response_v2.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035b_high_order_local_hp_resource_envelope/response_v3.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035b_high_order_local_hp_resource_envelope/review_report_v1.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035b_high_order_local_hp_resource_envelope/review_report_v2.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035b_high_order_local_hp_resource_envelope/review_report_v3.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035b_high_order_local_hp_resource_envelope/task.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `docs/task035b_high_order_local_hp_resource_envelope/task_scope_addendum_v1.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `notes/quick_start/stage4_3d_block_grating_usage_guide.md` | `project_docs` | `no` | `80` | governance, task history, outcomes, registry, or selective-merge documentation |
| `scripts/activate_myfenics_wsl.sh` | `production_core` | `no` | `30` | qualified high-order Floquet/static-condensation production dependency |
| `src/adaptivity/__init__.py` | `research_api_opt_in` | `no` | `50` | accepted reusable Task035 tetra/DWR research infrastructure; explicit opt-in only |
| `src/adaptivity/actual_physical_discrete_gradient_authority.py` | `do_not_merge` | `no` | `never` | not in the reviewed file-level allowlist or requires an extracted successor |
| `src/adaptivity/cell_indicator_snapshot.py` | `research_api_opt_in` | `no` | `50` | accepted reusable Task035 tetra/DWR research infrastructure; explicit opt-in only |
| `src/adaptivity/channel_phase_dispersion.py` | `do_not_merge` | `no` | `never` | not in the reviewed file-level allowlist or requires an extracted successor |
| `src/adaptivity/channel_response_matrix.py` | `do_not_merge` | `no` | `never` | not in the reviewed file-level allowlist or requires an extracted successor |
| `src/adaptivity/complement_schur_channel_dwr.py` | `do_not_merge` | `no` | `never` | not in the reviewed file-level allowlist or requires an extracted successor |
| `src/adaptivity/dtn_goal_adjoint.py` | `research_api_opt_in` | `no` | `50` | accepted reusable Task035 tetra/DWR research infrastructure; explicit opt-in only |
| `src/adaptivity/dtn_port_phase_authority.py` | `do_not_merge` | `no` | `never` | not in the reviewed file-level allowlist or requires an extracted successor |
| `src/adaptivity/fast_custom_element_ufl.py` | `production_core` | `no` | `30` | qualified high-order Floquet/static-condensation production dependency |
| `src/adaptivity/fixed_trace_element_cache.py` | `production_core` | `no` | `30` | qualified high-order Floquet/static-condensation production dependency |
| `src/adaptivity/fixed_trace_goal_entity_localization.py` | `do_not_merge` | `no` | `never` | not in the reviewed file-level allowlist or requires an extracted successor |
| `src/adaptivity/formal_h14_live_capture_bridge.py` | `do_not_merge` | `no` | `never` | not in the reviewed file-level allowlist or requires an extracted successor |
| `src/adaptivity/global_two_level_r5.py` | `research_api_opt_in` | `no` | `50` | accepted reusable Task035 tetra/DWR research infrastructure; explicit opt-in only |
| `src/adaptivity/goal_weighted_two_level.py` | `research_api_opt_in` | `no` | `50` | accepted reusable Task035 tetra/DWR research infrastructure; explicit opt-in only |
| `src/adaptivity/h13_signed_z_shape_selector.py` | `do_not_merge` | `no` | `never` | not in the reviewed file-level allowlist or requires an extracted successor |
| `src/adaptivity/hcurl_regionwise_p.py` | `do_not_merge` | `no` | `never` | regionwise/non-exact-sequence local-p capability is not qualified |
| `src/adaptivity/high_order_resource_audit.py` | `research_api_opt_in` | `no` | `50` | accepted reusable Task035 tetra/DWR research infrastructure; explicit opt-in only |
| `src/adaptivity/high_order_same_error.py` | `research_api_opt_in` | `no` | `50` | accepted reusable Task035 tetra/DWR research infrastructure; explicit opt-in only |
| `src/adaptivity/hp_smoothness_classifier.py` | `research_api_opt_in` | `no` | `50` | accepted reusable Task035 tetra/DWR research infrastructure; explicit opt-in only |
| `src/adaptivity/inverse_trace_interior_budget_audit.py` | `do_not_merge` | `no` | `never` | not in the reviewed file-level allowlist or requires an extracted successor |
| `src/adaptivity/missing_p6_trace_sensitivity.py` | `do_not_merge` | `no` | `never` | production selective-trace capability is not closed and is explicitly excluded |
| `src/adaptivity/multigoal_hp_classifier.py` | `research_api_opt_in` | `no` | `50` | accepted reusable Task035 tetra/DWR research infrastructure; explicit opt-in only |
| `src/adaptivity/p6_trace_complement_qualification.py` | `do_not_merge` | `no` | `never` | not in the reviewed file-level allowlist or requires an extracted successor |
| `src/adaptivity/periodic_tetra_refinement.py` | `research_api_opt_in` | `no` | `50` | accepted reusable Task035 tetra/DWR research infrastructure; explicit opt-in only |
| `src/adaptivity/physical_channel_dwr_trace_selection.py` | `do_not_merge` | `no` | `never` | production selective-trace capability is not closed and is explicitly excluded |
| `src/adaptivity/physical_missing_p6_action_only_complement.py` | `do_not_merge` | `no` | `never` | production selective-trace capability is not closed and is explicitly excluded |
| `src/adaptivity/selective_p6_trace_exact_sequence.py` | `do_not_merge` | `no` | `never` | production selective-trace capability is not closed and is explicitly excluded |
| `src/adaptivity/selective_p6_trace_orbits.py` | `do_not_merge` | `no` | `never` | production selective-trace capability is not closed and is explicitly excluded |
| `src/adaptivity/significant_channel_reference.py` | `do_not_merge` | `no` | `never` | not in the reviewed file-level allowlist or requires an extracted successor |
| `src/adaptivity/target_common_mesh_angle_sweep.py` | `do_not_merge` | `no` | `never` | not in the reviewed file-level allowlist or requires an extracted successor |
| `src/adaptivity/target_dwr_adaptive_cycles.py` | `research_api_opt_in` | `no` | `50` | accepted reusable Task035 tetra/DWR research infrastructure; explicit opt-in only |
| `src/adaptivity/target_fixed_trace_candidate.py` | `do_not_merge` | `no` | `never` | not in the reviewed file-level allowlist or requires an extracted successor |
| `src/adaptivity/target_r5_adaptive_cycles.py` | `research_api_opt_in` | `no` | `50` | accepted reusable Task035 tetra/DWR research infrastructure; explicit opt-in only |
| `src/adaptivity/target_regionwise_p_candidate.py` | `do_not_merge` | `no` | `never` | regionwise/non-exact-sequence local-p capability is not qualified |
| `src/adaptivity/target_uniform_tetra_control.py` | `research_api_opt_in` | `no` | `50` | accepted reusable Task035 tetra/DWR research infrastructure; explicit opt-in only |
| `src/common/config_3d.py` | `production_core` | `no` | `20` | production capability candidate; current blob requires surgery to remove prohibited research imports before migration |
| `src/common/modes_3d.py` | `do_not_merge` | `no` | `never` | not in the reviewed file-level allowlist or requires an extracted successor |
| `src/constraints/floquet_3d.py` | `production_core` | `no` | `30` | qualified high-order Floquet/static-condensation production dependency |
| `src/constraints/floquet_3d_high_order.py` | `production_core` | `no` | `30` | qualified high-order Floquet/static-condensation production dependency |
| `src/constraints/high_order_floquet_trace.py` | `production_core` | `no` | `30` | production capability candidate; current blob requires surgery to remove prohibited research imports before migration |
| `src/constraints/selective_p6_trace_3d.py` | `do_not_merge` | `no` | `never` | production selective-trace capability is not closed and is explicitly excluded |
| `src/constraints/selective_p6_trace_expansion.py` | `do_not_merge` | `no` | `never` | production selective-trace capability is not closed and is explicitly excluded |
| `src/constraints/selective_p6_trace_mesh_catalog.py` | `do_not_merge` | `no` | `never` | production selective-trace capability is not closed and is explicitly excluded |
| `src/geometry/mesh_builder_3d.py` | `production_core` | `no` | `30` | production capability candidate; current blob requires surgery to remove prohibited research imports before migration |
| `src/geometry/research_axis_profiles.py` | `do_not_merge` | `no` | `never` | irregular geometry or frozen research geometry profile is out of scope |
| `src/geometry/tetra_mesh_audit.py` | `research_api_opt_in` | `no` | `50` | accepted reusable Task035 tetra/DWR research infrastructure; explicit opt-in only |
| `src/main.py` | `production_core` | `no` | `20` | qualified high-order Floquet/static-condensation production dependency |
| `src/runners/run_3d_cases.py` | `production_core` | `no` | `20` | qualified high-order Floquet/static-condensation production dependency |
| `src/solvers/common_3d_case_flow.py` | `production_core` | `no` | `40` | qualified high-order Floquet/static-condensation production dependency |
| `src/solvers/common_3d_solve.py` | `production_core` | `no` | `40` | production capability candidate; current blob requires surgery to remove prohibited research imports before migration |
| `src/solvers/common_3d_utils.py` | `production_core` | `no` | `40` | qualified high-order Floquet/static-condensation production dependency |
| `src/solvers/condensed_iterative_profiles.py` | `do_not_merge` | `no` | `never` | failed condensed iterative profile; retain only compact negative evidence |
| `src/solvers/condensed_physical_slab_partition.py` | `do_not_merge` | `no` | `never` | not in the reviewed file-level allowlist or requires an extracted successor |
| `src/solvers/condensed_trace_harmonic_partition.py` | `do_not_merge` | `no` | `never` | failed condensed iterative profile; retain only compact negative evidence |
| `src/solvers/condensed_trace_harmonic_pc.py` | `do_not_merge` | `no` | `never` | failed condensed iterative profile; retain only compact negative evidence |
| `src/solvers/dtn_port_3d.py` | `production_core` | `no` | `40` | production capability candidate; current blob requires surgery to remove prohibited research imports before migration |
| `src/solvers/dtn_surface_vector_cache.py` | `production_core` | `no` | `40` | qualified high-order Floquet/static-condensation production dependency |
| `src/solvers/hcurl_affine_isotropic_tensor.py` | `production_core` | `no` | `40` | qualified high-order Floquet/static-condensation production dependency |
| `src/solvers/hcurl_assembly_time_condensation.py` | `production_core` | `no` | `40` | qualified high-order Floquet/static-condensation production dependency |
| `src/solvers/hcurl_cell_static_condensation.py` | `production_core` | `no` | `40` | qualified high-order Floquet/static-condensation production dependency |
| `src/solvers/manufactured_rayleigh_port_authority.py` | `do_not_merge` | `no` | `never` | not in the reviewed file-level allowlist or requires an extracted successor |
| `src/solvers/mpc_form_action.py` | `production_core` | `no` | `40` | qualified high-order Floquet/static-condensation production dependency |
| `src/solvers/selective_p6_trace_matrix_free.py` | `do_not_merge` | `no` | `never` | production selective-trace capability is not closed and is explicitly excluded |
| `src/solvers/solve_maxwell_3d_stage_4b_block_grating.py` | `production_core` | `no` | `40` | qualified high-order Floquet/static-condensation production dependency |
| `src/test/test_100_task035_actual_r5_record.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_101_task035_periodic_tetra_pipeline.py` | `research_api_opt_in` | `no` | `50` | accepted reusable Task035 tetra/DWR research infrastructure; explicit opt-in only |
| `src/test/test_102_task035_tetra_r5_record.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_103_task035_periodic_tetra_refinement.py` | `research_api_opt_in` | `no` | `50` | accepted reusable Task035 tetra/DWR research infrastructure; explicit opt-in only |
| `src/test/test_104_task035_adaptive_watchdog_contract.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_105_task035_adaptive_success_record.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_106_task035_uniform_control_contract.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_107_task035_uniform_control_record.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_108_task035_actual_dtn_adjoint.py` | `research_api_opt_in` | `no` | `50` | accepted reusable Task035 tetra/DWR research infrastructure; explicit opt-in only |
| `src/test/test_109_task035_goal_weighted_two_level.py` | `research_api_opt_in` | `no` | `50` | accepted reusable Task035 tetra/DWR research infrastructure; explicit opt-in only |
| `src/test/test_110_task035_common_mesh_angle_sweep.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_111_task035_hp_smoothness_classifier.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_112_task035_review_v5_records.py` | `research_api_opt_in` | `no` | `50` | accepted reusable Task035 tetra/DWR research infrastructure; explicit opt-in only |
| `src/test/test_113_task035b_high_order_resource_audit.py` | `research_api_opt_in` | `no` | `50` | accepted reusable Task035 tetra/DWR research infrastructure; explicit opt-in only |
| `src/test/test_114_task035b_cell_static_condensation.py` | `production_core` | `no` | `60` | production regression candidate; sanitize research-only cases before file-level migration |
| `src/test/test_115_task035b_assembly_time_condensation.py` | `production_core` | `no` | `60` | production regression candidate; sanitize research-only cases before file-level migration |
| `src/test/test_116_task035b_regionwise_p.py` | `do_not_merge` | `no` | `never` | regionwise/non-exact-sequence local-p capability is not qualified |
| `src/test/test_117_task035b_same_error.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_118_task035b_channel_reference.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_119_task035b_channel_adjoint.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_120_task035b_dtn_port_phase_authority.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_121_task035b_fixed_trace_goal_entity_localization.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_122_task035b_missing_p6_trace_sensitivity.py` | `do_not_merge` | `no` | `never` | production selective-trace capability is not closed and is explicitly excluded |
| `src/test/test_123_task035b_p7_capability_resource_gate.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_124_task035b_missing_p6_trace_preflight.py` | `do_not_merge` | `no` | `never` | production selective-trace capability is not closed and is explicitly excluded |
| `src/test/test_125_task035b_y_directional_control.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_126_task035b_evanescent_port_scaling.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_127_task035b_manufactured_rayleigh_port_authority.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_128_task035b_channel_response_matrix.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_129_task035b_condensed_iterative_runner.py` | `do_not_merge` | `no` | `never` | failed condensed iterative profile; retain only compact negative evidence |
| `src/test/test_129_task035b_global_p6_h14_trace_discriminator.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_130_task035b_inverse_budget_exchange_preflight.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_131_task035b_channel_phase_dispersion.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_132_task035b_physical_trace_lane_capability_gate.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_133_task035b_condensed_iterative_capability_gate.py` | `do_not_merge` | `no` | `never` | failed condensed iterative profile; retain only compact negative evidence |
| `src/test/test_133_task035b_fast_custom_element_ufl.py` | `production_core` | `no` | `60` | production regression candidate; sanitize research-only cases before file-level migration |
| `src/test/test_134_task035b_selective_p6_trace_orbits.py` | `do_not_merge` | `no` | `never` | production selective-trace capability is not closed and is explicitly excluded |
| `src/test/test_135_task035b_direct_setup_profile_runner.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_135_task035b_persistent_condensed_class_cache.py` | `production_core` | `no` | `60` | production regression candidate; sanitize research-only cases before file-level migration |
| `src/test/test_136_task035b_h13_signed_z_shape_selector.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_136_task035b_p6_trace_complement_qualification.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_137_task035b_floquet_trace_entity_identity.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_138_task035b_complement_schur_channel_dwr.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_139_task035b_review_v2_resource_records.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_140_task035b_selective_p6_trace_exact_sequence.py` | `do_not_merge` | `no` | `never` | production selective-trace capability is not closed and is explicitly excluded |
| `src/test/test_141_task035b_selective_p6_trace_mpi_plan.py` | `do_not_merge` | `no` | `never` | production selective-trace capability is not closed and is explicitly excluded |
| `src/test/test_142_task035b_selective_trace_expansion.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_143_task035b_selective_trace_mesh_catalog.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_144_task035b_solve_thread_memory_audit.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_145_task035b_h13_top_phase_profile.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_146_task035b_factor_free_profile_v2.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_147_task035b_actual_selective_trace_expansion.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_148_task035b_h13_top_phase_runner_contract.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_149_task035b_h13_top_phase_evidence.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_14_stage4_dtn_modes.py` | `do_not_merge` | `no` | `never` | not in the reviewed file-level allowlist or requires an extracted successor |
| `src/test/test_150_task035b_memory_floor_factor_inventory.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_152_task035b_dtn_surface_vector_cache.py` | `production_core` | `no` | `60` | production regression candidate; sanitize research-only cases before file-level migration |
| `src/test/test_153_task035b_physical_channel_dwr_trace_selection.py` | `do_not_merge` | `no` | `never` | production selective-trace capability is not closed and is explicitly excluded |
| `src/test/test_154_task035b_physical_slab_dtn_profile.py` | `do_not_merge` | `no` | `never` | failed condensed iterative profile; retain only compact negative evidence |
| `src/test/test_155_task035b_action_only_missing_p6_complement.py` | `do_not_merge` | `no` | `never` | production selective-trace capability is not closed and is explicitly excluded |
| `src/test/test_156_task035b_deterministic_structured_partition.py` | `production_core` | `no` | `60` | production regression candidate; sanitize research-only cases before file-level migration |
| `src/test/test_157_task035b_actual_physical_discrete_gradient_authority.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_158_task035b_generalized_primal_recovery.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_159_task035b_condensed_trace_harmonic_pc.py` | `do_not_merge` | `no` | `never` | failed condensed iterative profile; retain only compact negative evidence |
| `src/test/test_15_stage4_hexa_mesh_spacing.py` | `production_core` | `no` | `60` | production regression candidate; sanitize research-only cases before file-level migration |
| `src/test/test_160_task035b_fixed_trace_element_cache.py` | `production_core` | `no` | `60` | production regression candidate; sanitize research-only cases before file-level migration |
| `src/test/test_161_task035b_trace_harmonic_profile_gate.py` | `do_not_merge` | `no` | `never` | failed condensed iterative profile; retain only compact negative evidence |
| `src/test/test_162_task035b_formal_h14_live_capture_bridge.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_163_task035b_canonical_orientation_condensation.py` | `production_core` | `no` | `60` | production regression candidate; sanitize research-only cases before file-level migration |
| `src/test/test_164_task035b_canonical_orientation_profile_wiring.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_165_task035b_live_full_p6_local_schur_capture.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_166_task035b_direct_profile_formal_gates.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_167_task035b_live_full_p6_dtn_wiring.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_168_task035b_petsc_factor_event_timing.py` | `production_core` | `no` | `60` | production regression candidate; sanitize research-only cases before file-level migration |
| `src/test/test_169_task035b_h14_exact_reverse_z_candidate.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_170_task035b_trace_harmonic_partition_builder.py` | `do_not_merge` | `no` | `never` | failed condensed iterative profile; retain only compact negative evidence |
| `src/test/test_171_task035b_actual_selective_trace_stage4_wiring.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_172_task035b_selective_p6_trace_matrix_free.py` | `do_not_merge` | `no` | `never` | production selective-trace capability is not closed and is explicitly excluded |
| `src/test/test_173_task035b_h13_direct_setup_profile.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_174_task035b_stage4_pre_release_capture.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_175_task035b_h13_setup_pair_record.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_176_task035b_physical_selective_execution_capability_record.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_177_task035b_response_v3_records.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_178_task035b_public_assembly_backend.py` | `production_core` | `no` | `60` | production regression candidate; sanitize research-only cases before file-level migration |
| `src/test/test_17_3d_high_order_floquet_trace.py` | `production_core` | `no` | `60` | production regression candidate; sanitize research-only cases before file-level migration |
| `src/test/test_23_physical_slab_two_level.py` | `do_not_merge` | `no` | `never` | not in the reviewed file-level allowlist or requires an extracted successor |
| `src/test/test_26_documentation_contract.py` | `do_not_merge` | `no` | `never` | not in the reviewed file-level allowlist or requires an extracted successor |
| `src/test/test_28_direct_memory_telemetry.py` | `production_core` | `no` | `60` | production regression candidate; sanitize research-only cases before file-level migration |
| `src/test/test_43_task033_high_order_entity_transform.py` | `production_core` | `no` | `60` | production regression candidate; sanitize research-only cases before file-level migration |
| `src/test/test_46_task033_high_order_floquet_topology.py` | `production_core` | `no` | `60` | production regression candidate; sanitize research-only cases before file-level migration |
| `src/test/test_73_task034_hardening.py` | `do_not_merge` | `no` | `never` | not in the reviewed file-level allowlist or requires an extracted successor |
| `src/test/test_87_task035_phase_a.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_88_task035_estimator_fixtures.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_89_task035_real_fe_fixtures.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_90_task035_real_fe_records.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_91_task035_real_fe_provenance.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_92_task035_low_cost_bakeoff.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_93_task035_target_artifact_bakeoff.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_94_task035_component_fixtures.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_95_task035_mesh_backend_bakeoff.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_96_task035_phase_cd_closeout.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_97_task035_phase_cd_records.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_98_task035_actual_global_r5.py` | `research_api_opt_in` | `no` | `50` | accepted reusable Task035 tetra/DWR research infrastructure; explicit opt-in only |
| `src/test/test_99_task035_actual_r5_watchdog.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/test/test_case095_compact_evidence_contract.py` | `reusable_benchmark` | `no` | `70` | compact benchmark contract/checker; rewrite stale commands or phase-A assumptions before migration |
| `src/test/test_development_model_registry_contract.py` | `reusable_benchmark` | `no` | `70` | reusable checker, resource telemetry, or contract test |
| `src/test/test_task035b_selective_merge_manifest_contract.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/validation/task035_component_fixtures.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/validation/task035_hcurl_estimator_fixtures.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/validation/task035_low_cost_bakeoff.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/validation/task035_mesh_backend_bakeoff.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/validation/task035_real_fe_fixtures.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |
| `src/validation/task035_target_artifact_bakeoff.py` | `do_not_merge` | `no` | `never` | task-numbered research runner/test is not a production interface |

## 合并次序与 fresh evidence

1. 抽取 fixed-trace/cache 与 tetra helper，去除 regionwise/non-exact-sequence 依赖。
2. 接入单一 assembly backend 配置，ordinary default 固定为 `standard_full`。
3. 迁移高阶 Floquet、orientation 与 static-condensation algebra。
4. 净化 DtN/common flow，删除 selective-trace 和 failed-iterative import closure。
5. 先跑 pure/serial/MPI tests，再跑 ordinary Full3D、static-condensed MPI2/MPI8、Task032/033 Hybrid fresh anchors。
6. Case094/095 checker、registry、文档合同和 full pytest 全部通过后才允许合入 master。

明确不提升为 production：selective trace、三个失败 condensed iterative profiles、regionwise/non-exact-sequence local-p、不规则几何、tetra static condensation 和 mixed-cell mesh。
