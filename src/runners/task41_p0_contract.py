"""Fixed Task41 P0 source, input, runtime, resource, and deadline contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping, Sequence

from src.runners.task40_v10_campaign import FixedCampaignWindow, _utc_ns
from src.runners.workflow_timebase import clock_sample

TASK41_P0_CONTRACT_SCHEMA = "task41.p0.execution_contract.v1"
TASK41_P0_WINDOW_SCHEMA = "task41.p0.execution_window.v1"
TASK41_P0_AUTH_SCHEMA = "task41.p0.closeout_checker_authorization.v1"
TASK41_BRANCH = "task41extra_phi90_p50x50_g17x20"
TASK41_MODEL_ID = "task41extra_phi90_p50x50_g17x20"
TASK41_RUN_ID = "task41extra_g13_p6_phi90_direct_a1"
TASK41_A2_RUN_ID = "task41extra_g13_p6_phi90_iterative_a2"
TASK41_B0_RUN_ID = "task41extra_b0_p6_phi90_07nm_iterative"
TASK41_P0_CHECKER_KIND_BY_CASE = {
    "A1": "task41_p0_independent_full_a6_checker",
    "A2": "task41_p0_a2_independent_p6_iterative_checker",
    "B0": "task41_p0_b0_independent_iterative_checker",
}
TASK41_CONTROLLER_RELATIVE = Path(
    "benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_controller"
)
TASK41_A2_CONTROLLER_RELATIVE = Path(
    "benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_a2_controller"
)
TASK41_WINDOW_RELATIVE = Path(
    "benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_controller/execution_window.json"
)
TASK41_A2_WINDOW_RELATIVE = Path(
    "benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_a2_controller/execution_window.json"
)
TASK41_INPUT_RELATIVE = Path(
    "input/task41extra_phi90_p50x50_g17x20/g13_p6_direct_a1.dat"
)
TASK41_A2_INPUT_RELATIVE = Path(
    "input/task41extra_phi90_p50x50_g17x20/g13_p6_iterative_a2.dat"
)
TASK41_A1_COMPARISON_BINDING_SCHEMA = "task41.p0.a1_comparison_binding.v1"
TASK41_A2_Q_CSR_REUSE_SCHEMA_V1 = "task41.p0.a2_q_csr_reuse.v1"
TASK41_A2_Q_CSR_REUSE_SCHEMA = "task41.p0.a2_q_csr_reuse.v2"
TASK41_A1_COMPARISON_BINDING_RELATIVE = (
    TASK41_A2_CONTROLLER_RELATIVE / "a1_comparison_binding.json"
)
TASK41_A1_SERVICE_RELATIVE = Path(
    "benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_a1"
)
TASK41_A2_SERVICE_RELATIVE = Path(
    "benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_a2"
)
TASK41_B0_CONTROLLER_RELATIVE = Path(
    "benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_b0_controller"
)
TASK41_B0_WINDOW_RELATIVE = (
    TASK41_B0_CONTROLLER_RELATIVE / "execution_window.json"
)
TASK41_B0_INPUT_RELATIVE = Path(
    "input/task41extra_phi90_p50x50_g17x20/b0_p6_07nm_iterative.dat"
)
TASK41_B0_PRECONDITIONER = "task41extra_b0_p6_phi90_07nm_y_orbit_reference_v1"
TASK41_B0_COMPARISON_GROUP = "task41extra_phi90_p50x50_g17x20_b0_07nm"
TASK41_B0_SERVICE_RELATIVE = Path(
    "benchmarks/artifacts/task41extra_phi90_p50x50_g17x20/p0_b0"
)
TASK41_B0_SAVED_SURFACE_DONOR_RELATIVE = Path(
    "results/task41extra_phi90_p50x50_g17x20/"
    "task41extra_b0_p6_phi90_07nm_iterative__full3d_iterative__mpi1__Mna/"
    "20261017T103223.933995Z/task41_b0_target_surface_checkpoint/global"
)
TASK41_B0_SAVED_SURFACE_DONOR = {
    "schema": "task41.p0.b0.saved_surface_donor.v1",
    "require_existing": True,
    "root_relative_path": str(TASK41_B0_SAVED_SURFACE_DONOR_RELATIVE),
    "binary_name": "carrier_surface_functionals.bin",
    "checkpoint_name": "carrier_surface_functionals.bin.checkpoint.json",
    "manifest_name": "carrier_surface_functionals.bin.manifest.json",
    "producer": {
        "source_sha": "c52d0d3c0ec6b46c52c3bcf464ee53164308f1c5",
        "input_sha256": "a0c45d0475bd2b41d2d19589831086468a62f39fdca5b74734b62751df1485c1",
        "physical_model_sha256": "0e272beec0cbbd946d62220f1947f60e11e61411b1fec32e62a9979ec922145d",
        "execution_contract_sha256": "5657d456d67f2b9e3b94aa19a0666a1b011dece6e7b6c7043eb929b45d711f5d",
        "campaign_window_sha256": "87dd4ec560a208122e9959987a392bf878162793c61582877969206686d922e6",
        "producer_identity_sha256": "c89c2c5b06d6b8d727d5ea59e3b4ccad9ecf2ff1627f2a13c60f200eee66cf28",
        "ordered_mode_manifest_sha256": "80527cc4770abe0bc47db20c8d1f0ae8e13b75b5e090498f78cbfa75c120d0e0",
    },
    "committed": {
        "mode_count": 64120,
        "bytes": 363791051840,
        "checkpoint_sha256": "66ec8f305382060c044822459d50aa6d323d85bcdfffd531b46ff5d74e43e57a",
        "manifest_sha256": "46cd5e3cecf2c0dac694bdbba1fef91eae10642e878a487fc63e216ddcc1f142",
        "prefix_sha256": "2595b9518e2422bfadbc2f1a6640e619d60501525b07bda48a068a8ec478a10e",
    },
    "source_equivalence_bridge": {
        "schema": "task41.p0.b0.saved_surface_source_equivalence.v1",
        "producer_source_sha": "c52d0d3c0ec6b46c52c3bcf464ee53164308f1c5",
        "unchanged_math_source_paths": [
            "src/solvers/dtn_boundary_phase_gauge.py",
            "src/solvers/dtn_port_3d.py",
            "src/solvers/dtn_boundary_plane_qualification.py",
            "src/solvers/fresh_c1_manifest_identity.py",
            "src/common/modes_3d.py",
            "src/common/config_3d.py",
            "src/solvers/task40_v22_operator_probe.py",
            "src/solvers/task40_v25_selected_q0.py",
            "src/solvers/directional_boundary.py",
        ],
        "execution_only_source_paths": [
            "src/solvers/fullspace_dtn_action.py",
            "src/solvers/fullspace_same_mesh_hcurl_pmg_physical.py",
        ],
        "math_fields_still_require_exact_current_mesh_mpc_basix_config_abi_mode_h_match": True,
    },
}
# The exact B0 preparation start is unknown. This earlier A2 documentation
# commit is used as a conservative lower-bound T0, so its UTC interval is
# charged without claiming that B0 was frozen at that commit. The live
# monotonic/boottime clocks were not sampled then.
TASK41_B0_T0_UTC = "2026-10-17T05:43:44Z"
TASK41_B0_T0_SOURCE_SHA = "0bf0dc38eab2cf61ca9feb5115323f78c68e6576"
TASK41_B0_T0_BASIS = {
    "kind": "conservative_earlier_source_commit_utc_lower_bound",
    "source_sha": TASK41_B0_T0_SOURCE_SHA,
    "source_commit_utc": TASK41_B0_T0_UTC,
    "pre_anchor_monotonic_elapsed": "UNKNOWN",
    "pre_anchor_boottime_elapsed": "UNKNOWN",
}
TASK41_B0_BOOTSTRAP_TREATMENT = (
    "Exact B0 preparation start is unknown; charge anchor.utc_ns minus the earlier "
    "A2 documentation commit used as conservative lower-bound T0 once as UTC bootstrap; "
    "this does not claim B0 was frozen at that commit; "
    "pre-anchor monotonic and boottime elapsed are unknown; subsequent intervals "
    "use CampaignAccount checked UTC/monotonic accounting. Do not add the 11.9 s "
    "inventory wall duration a second time."
)
TASK41_B0_V3_WINDOW_RELATIVE = TASK41_B0_CONTROLLER_RELATIVE / "execution_window_v3_24h.json"
TASK41_B0_V3_AUTH_RELATIVE = TASK41_B0_CONTROLLER_RELATIVE / "v3_24h_authorization.json"
TASK41_B0_PARENT_WINDOW_SHA256 = "87dd4ec560a208122e9959987a392bf878162793c61582877969206686d922e6"
TASK41_B0_V3_WINDOW_SHA256 = "68e6d8dfcccc9dee98bc161730957dc76f70a9e2dea2ee78455b66c9d8b37c38"
TASK41_B0_V3_TOTAL_SECONDS = 86_400.0
TASK41_B0_V3_NUMERICAL_SECONDS = 85_200.0
TASK41_B0_V6_WINDOW_RELATIVE = TASK41_B0_CONTROLLER_RELATIVE / "execution_window_v6_24h.json"
TASK41_B0_V6_AUTH_RELATIVE = TASK41_B0_CONTROLLER_RELATIVE / "v6_24h_authorization.json"
TASK41_B0_V6_AUTH_LEGACY_SCHEMA = "task41.b0.v6.user_continuation_authorization.v1"
TASK41_B0_V6_AUTH_SCHEMA = "task41.b0.v6.user_continuation_authorization.v2"
TASK41_B0_V6_AUTHORIZATION = "user_explicit_v6_24h_20261020"
TASK41_B0_V6_TOTAL_SECONDS = 86_400.0
TASK41_B0_V6_NUMERICAL_SECONDS = 85_200.0
TASK41_B0_V6_PREPARATION_T0_KIND = "user_approved_v6_preparation_start"
TASK41_B0_V6_PREPARATION_BOOTSTRAP_TREATMENT = (
    "preparation_start_to_anchor_utc_elapsed_charged; "
    "pre_anchor_monotonic_and_boottime_unknown"
)
TASK41_B0_V6_WINDOW_SHA256 = "ea6b38c3bc791ace068c75188a562023cae197f7016f110b0b86970891c46c8d"
TASK41_B0_V9_WINDOW_RELATIVE = TASK41_B0_CONTROLLER_RELATIVE / "execution_window_v9_24h.json"
TASK41_B0_V9_AUTH_RELATIVE = TASK41_B0_CONTROLLER_RELATIVE / "v9_24h_authorization.json"
TASK41_B0_V9_AUTH_SCHEMA = "task41.b0.v9.user_continuation_authorization.v1"
TASK41_B0_V9_AUTHORIZATION = "user_explicit_v9_24h_20261021"
TASK41_B0_V9_TOTAL_SECONDS = 86_400.0
TASK41_B0_V9_NUMERICAL_SECONDS = 85_200.0
TASK41_B0_V9_PREPARATION_T0_KIND = "user_approved_v9_preparation_start"
TASK41_B0_V9_PREPARATION_BOOTSTRAP_TREATMENT = (
    "preparation_start_to_anchor_utc_elapsed_charged; "
    "pre_anchor_monotonic_and_boottime_unknown"
)
TASK41_B0_SAVED_DIAGNOSTICS_WINDOW_RELATIVE = (
    TASK41_B0_CONTROLLER_RELATIVE / "execution_window_saved_diagnostics_6h.json"
)
TASK41_B0_SAVED_DIAGNOSTICS_AUTH_RELATIVE = (
    TASK41_B0_CONTROLLER_RELATIVE / "saved_diagnostics_6h_authorization.json"
)
TASK41_B0_SAVED_DIAGNOSTICS_AUTH_SCHEMA = "task41.b0.saved_diagnostics_window_authorization.v1"
TASK41_B0_SAVED_DIAGNOSTICS_AUTHORIZATION = "user_explicit_saved_diagnostics_6h"
TASK41_B0_SAVED_DIAGNOSTICS_TOTAL_SECONDS = 21_600.0
TASK41_B0_SAVED_DIAGNOSTICS_NUMERICAL_SECONDS = 20_400.0
TASK41_B0_SAVED_DIAGNOSTICS_NEW_EVIDENCE_LIMIT_BYTES = 512 * 1024**2
TASK41_B0_SAVED_DIAGNOSTICS_SCOPE = {
    "kind": "saved_diagnostics_only",
    "actions": [
        "v9_failed_terminal_audit",
        "v6_v9_saved_y_g_comparison",
        "selected_incident_replay",
    ],
    "max_new_incident_cells": 8,
    "max_ffcx_reference_cells": 1,
    "new_evidence_limit_bytes": TASK41_B0_SAVED_DIAGNOSTICS_NEW_EVIDENCE_LIMIT_BYTES,
    "cumulative_raw_artifact_limit_bytes": 16 * 1024**3,
    "free_space_floor_bytes": 2 * 1024**3,
    "full_owner": False,
    "carrier_replay": False,
    "full_q_scan": False,
}
TASK41_B0_V12_CANDIDATE_REPLAY_INSTANCE = "v12_two_cell_candidate_replay"
TASK41_B0_V12_CANDIDATE_REPLAY_WINDOW_RELATIVE = (
    TASK41_B0_CONTROLLER_RELATIVE
    / "execution_window_saved_diagnostics_v12_two_cell_candidate_replay_6h.json"
)
TASK41_B0_V12_CANDIDATE_REPLAY_AUTH_RELATIVE = (
    TASK41_B0_CONTROLLER_RELATIVE
    / "saved_diagnostics_v12_two_cell_candidate_replay_authorization.json"
)
TASK41_B0_V12_CANDIDATE_REPLAY_ACCOUNTING_RELATIVE = (
    TASK41_B0_CONTROLLER_RELATIVE
    / "campaign_accounting_v12_two_cell_candidate_replay_6h.jsonl"
)
TASK41_B0_V12_CANDIDATE_REPLAY_SCOPE = {
    "kind": "saved_diagnostics_candidate_replay_only",
    "actions": ["selected_incident_replay"],
    "max_new_incident_cells": 2,
    "max_ffcx_reference_cells": 0,
    "new_evidence_limit_bytes": TASK41_B0_SAVED_DIAGNOSTICS_NEW_EVIDENCE_LIMIT_BYTES,
    "cumulative_raw_artifact_limit_bytes": 16 * 1024**3,
    "free_space_floor_bytes": 2 * 1024**3,
    "full_owner": False,
    "carrier_replay": False,
    "full_q_scan": False,
}
TASK41_B0_V14_SAVED_RHS_CANDIDATE_INSTANCE = "v14_same_lu_rhs_candidate_6h"
TASK41_B0_V14_SAVED_RHS_CANDIDATE_WINDOW_RELATIVE = (
    TASK41_B0_CONTROLLER_RELATIVE / "execution_window_v14_same_lu_rhs_candidate_6h.json"
)
TASK41_B0_V14_SAVED_RHS_CANDIDATE_AUTH_RELATIVE = (
    TASK41_B0_CONTROLLER_RELATIVE / "saved_diagnostics_v14_same_lu_rhs_candidate_authorization.json"
)
TASK41_B0_V14_SAVED_RHS_CANDIDATE_ACCOUNTING_RELATIVE = (
    TASK41_B0_CONTROLLER_RELATIVE / "campaign_accounting_v14_same_lu_rhs_candidate_6h.jsonl"
)
TASK41_B0_V14_RHS_REFINEMENT_STRATEGY = (
    "same_lu_binary64_products_real_imag_fsum"
)
TASK41_B0_V14_SAVED_RHS_CANDIDATE_SCOPE = {
    "kind": "saved_diagnostics_same_lu_rhs_candidate_staged",
    "actions": ["selected_incident_replay"],
    "initial_screen": {
        "selected_cells": [360, 446],
        "columns": [0, 1],
        "states": ["j0", "j3"],
        "right_hand_sides_per_cell": 2,
        "refinement": "same_lu_binary64_products_real_imag_fsum",
        "refinement_max_steps": 2,
        "max_getrs_total": 12,
        "independent_gate": {
            "all_450_internal_rows": True,
            "residuals_nonworsening_and_credible_decline_for_all_four_rhs": True,
            "actual_returned_minus_Jz_verified": True,
            "both_candidate_d_columns_improve_beyond_wide_evaluation_resolution": True,
            "production_order_y_g_d_replayed": True,
            "noise_covers_change_means_inconclusive": True,
        },
        "gate_for_conditional_stage": "initial_screen_independent_check_pass",
    },
    "conditional_star_coverage": {
        "enabled_only_after": "initial_screen_independent_check_pass",
        "star_cells": [23352, 23493],
        "both_columns_and_original_cell_rhs_mpc_input": True,
        "existing_representative_key_set": "eight_original_keys_with_complete_saved_candidate_K_J_LU_mapping_and_b_i",
        "deduplication": "two_star_cells_union_eight_original_representative_keys_by_frozen_actual_key_identity",
        "max_unique_keys": 12,
        "minimum_coverage": ["two_actual_material_tags", "two_actual_directions"],
        "tag_and_direction_source": "hash_bound_per_key_metadata_not_name_inference",
        "max_total_getrs_per_nonzero_rhs_per_key": 3,
        "max_correction_getrs_per_nonzero_rhs_per_key": 2,
        "j0_j3_share_key_factorization_and_existing_rhs_identity": True,
        "compute_once_per_unique_key_per_rhs": True,
        "preserve_historical_charges": True,
        "missing_saved_K_J_LU_mapping_or_b_i": "enumerate_exact_missing_field_and_use; never_substitute_reference_LU",
    },
    "max_ffcx_reference_cells": 0,
    "new_evidence_limit_bytes": 16 * 1024**2,
    "single_package_limit_bytes": 512 * 1024**2,
    "cumulative_raw_artifact_limit_bytes": 16 * 1024**3,
    "free_space_floor_bytes": 2 * 1024**3,
    "full_owner": False,
    "carrier_replay": False,
    "full_q_scan": False,
}

TASK41_B0_V9_INTERNAL_RHS_STRATEGY = "same_lu_rhs_solve"
TASK41_B0_V9_VOLUME_DONOR_RUN_RELATIVE = Path(
    "results/task41extra_phi90_p50x50_g17x20"
    "/task41extra_b0_p6_phi90_07nm_iterative__full3d_iterative__mpi1__Mna"
    "/20261019T053402.514018Z"
)
TASK41_B0_V15_FULL_ACCEPTANCE_INSTANCE = "v15_full_two_column_acceptance_36h"
TASK41_B0_V15_FULL_ACCEPTANCE_WINDOW_RELATIVE = (
    TASK41_B0_CONTROLLER_RELATIVE / "execution_window_v15_full_two_column_acceptance_36h.json"
)
TASK41_B0_V15_FULL_ACCEPTANCE_AUTH_RELATIVE = (
    TASK41_B0_CONTROLLER_RELATIVE / "full_acceptance_v15_user_authorization.json"
)
TASK41_B0_V15_FULL_ACCEPTANCE_ACCOUNTING_RELATIVE = (
    TASK41_B0_CONTROLLER_RELATIVE / "campaign_accounting_v15_full_two_column_acceptance_36h.jsonl"
)
TASK41_B0_V15_FULL_ACCEPTANCE_TOTAL_SECONDS = 129_600.0
TASK41_B0_V15_FULL_ACCEPTANCE_NUMERICAL_SECONDS = 128_400.0
TASK41_B0_V15_FULL_ACCEPTANCE_NEW_RAW_BYTES = 1_900_000_000
TASK41_B0_V15_FULL_ACCEPTANCE_SINGLE_ARTIFACT_BYTES = 512 * 1024**2
TASK41_B0_V15_FULL_ACCEPTANCE_NON_RAW_RESERVE_BYTES = 256 * 1024**2
TASK41_B0_V15_POST_V7_RAW_EVIDENCE_ROOTS = [
    "task41_b0_v8_selected_star_35fd1bbf_20261021T072801Z_attempt1",
    "task41_b0_v8_saved_checker_3ce1a158_20261021T092516Z_attempt4",
    "task41_p0_saved_diagnostics_6h",
    "task41extra_b0_p6_phi90_07nm_iterative__full3d_iterative__mpi1__Mna/20261022T052401.200732Z",
]
TASK41_B0_V15_FULL_ACCEPTANCE_SCOPE = {
    "kind": "full_two_column_action_recovery_acceptance_only",
    "actions": ["full_two_column_action_recovery_and_independent_terminal_audit"],
    "columns": [0, 1],
    "internal_rhs_strategy": TASK41_B0_V9_INTERNAL_RHS_STRATEGY,
    "refinement_strategy": TASK41_B0_V14_RHS_REFINEMENT_STRATEGY,
    "refinement_max_steps": 2,
    "full_owner": True,
    "max_full_owner_builds": 1,
    "owner_quota_scope": "fixed_window_across_attempts",
    "actual_k_lu_identity_required": True,
    "independent_terminal_audit_required": True,
    "success_exit": "acceptance_only",
    "new_evidence_limit_bytes": TASK41_B0_V15_FULL_ACCEPTANCE_NEW_RAW_BYTES,
    "single_package_limit_bytes": TASK41_B0_V15_FULL_ACCEPTANCE_SINGLE_ARTIFACT_BYTES,
    "non_raw_output_reserve_bytes": TASK41_B0_V15_FULL_ACCEPTANCE_NON_RAW_RESERVE_BYTES,
    "cumulative_raw_artifact_limit_bytes": 16 * 1024**3,
    "raw_artifact_accounting": "frozen_v6_v7_donor_prefix_plus_explicit_post_v7_roots_by_inode_v1",
    "raw_artifact_roots": TASK41_B0_V15_POST_V7_RAW_EVIDENCE_ROOTS,
    "monitoring_log_accounting": "measured_separately_from_raw_npy_cap_and_included_in_free_space_gate",
    "free_space_floor_bytes": 2 * 1024**3,
    "carrier_replay": False,
    "full_q_scan": False,
}
TASK41_B0_V16_SAVED_VECTOR_INSTANCE = "v16_saved_vector_distribution_6h"
TASK41_B0_V16_SAVED_VECTOR_WINDOW_RELATIVE = (
    TASK41_B0_CONTROLLER_RELATIVE / "execution_window_v16_saved_vector_distribution_6h.json"
)
TASK41_B0_V16_SAVED_VECTOR_AUTH_RELATIVE = (
    TASK41_B0_CONTROLLER_RELATIVE / "saved_diagnostics_v16_saved_vector_distribution_authorization.json"
)
TASK41_B0_V16_SAVED_VECTOR_ACCOUNTING_RELATIVE = (
    TASK41_B0_CONTROLLER_RELATIVE / "campaign_accounting_v16_saved_vector_distribution_6h.jsonl"
)
TASK41_B0_V16_SAVED_VECTOR_NEW_EVIDENCE_BYTES = 128 * 1024**2
TASK41_B0_V16_SAVED_VECTOR_SCOPE = {
    "kind": "saved_vector_diagnostics_only",
    "actions": [
        "saved_vector_distribution",
        "saved_star_terminal_binding",
        "max_row_metadata_inventory",
    ],
    "columns": [0, 1],
    "max_new_incident_cells": 0,
    "max_ffcx_reference_cells": 0,
    "new_evidence_limit_bytes": TASK41_B0_V16_SAVED_VECTOR_NEW_EVIDENCE_BYTES,
    "cumulative_raw_artifact_limit_bytes": 16 * 1024**3,
    "free_space_floor_bytes": 2 * 1024**3,
    "full_owner": False,
    "factor_or_lu": False,
    "getrs": 0,
    "native_fe_action": False,
    "carrier_replay": False,
    "full_q_scan": False,
    "official_result": False,
}

TASK41_B0_V17_SELECTED_TWO_CELL_INSTANCE = "v17_selected_two_cell_replay_6h"
TASK41_B0_V17_SELECTED_TWO_CELL_WINDOW_RELATIVE = (
    TASK41_B0_CONTROLLER_RELATIVE / "execution_window_v17_selected_two_cell_replay_6h.json"
)
TASK41_B0_V17_SELECTED_TWO_CELL_AUTH_RELATIVE = (
    TASK41_B0_CONTROLLER_RELATIVE / "saved_diagnostics_v17_selected_two_cell_replay_authorization.json"
)
TASK41_B0_V17_SELECTED_TWO_CELL_ACCOUNTING_RELATIVE = (
    TASK41_B0_CONTROLLER_RELATIVE / "campaign_accounting_v17_selected_two_cell_replay_6h.jsonl"
)
TASK41_B0_V17_SAVED_VECTOR_MANIFEST_RELATIVE = Path(
    "results/task41extra_phi90_p50x50_g17x20/task41_p0_saved_diagnostics_6h/"
    "3d22e02f713c4a68c79759b2c5cb7cbcec693b7b3277ad98b529838008e38beb/"
    "saved_vector_distribution/attempt05.service/task41_p0_v16_metadata_bound_manifest.json"
)
TASK41_B0_V17_SAVED_VECTOR_MANIFEST_SHA256 = (
    "3fae0774772550faf173444e9c5aedd608212b430957ae591ffdb31daabeb215"
)
TASK41_B0_V17_SELECTED_TWO_CELL_NEW_EVIDENCE_BYTES = 128 * 1024**2
TASK41_B0_V17_SELECTED_TWO_CELL_SCOPE = {
    "kind": "saved_diagnostics_v17_selected_two_cell_replay_only",
    "actions": ["selected_incident_replay", "signed_two_cell_identity_diagnostic"],
    "selected_active_row": 1_622_464,
    "selected_original_row": 5_218_672,
    "incident_cells": [7873, 8014],
    "columns": [0, 1],
    "max_new_incident_cells": 2,
    "max_ffcx_reference_cells": 0,
    "max_candidate_builds": 2,
    "max_candidate_lu_factorizations": 2,
    "max_matrix_rhs_getrs": 6,
    "internal_rhs_count": 4,
    "internal_rhs_refinement": "same_lu_binary64_products_real_imag_fsum",
    "internal_rhs_refinement_max_steps": 2,
    "internal_rhs_getrs_max_total": 12,
    "new_evidence_limit_bytes": TASK41_B0_V17_SELECTED_TWO_CELL_NEW_EVIDENCE_BYTES,
    "cumulative_raw_artifact_limit_bytes": 16 * 1024**3,
    "free_space_floor_bytes": 2 * 1024**3,
    "full_owner": False,
    "carrier_replay": False,
    "full_q_scan": False,
    "official_result": False,
}

TASK41_B0_V18_SAVED_JZ_INSTANCE = "v18_saved_jz_candidate_6h"
TASK41_B0_V18_SAVED_JZ_WINDOW_RELATIVE = (
    TASK41_B0_CONTROLLER_RELATIVE / "execution_window_v18_saved_jz_candidate_6h.json"
)
TASK41_B0_V18_SAVED_JZ_AUTH_RELATIVE = (
    TASK41_B0_CONTROLLER_RELATIVE / "saved_diagnostics_v18_saved_jz_candidate_authorization.json"
)
TASK41_B0_V18_SAVED_JZ_ACCOUNTING_RELATIVE = (
    TASK41_B0_CONTROLLER_RELATIVE / "campaign_accounting_v18_saved_jz_candidate_6h.jsonl"
)
TASK41_B0_V17_PRIOR_SERVICE_RECEIPT_RELATIVE = Path(
    "results/task41extra_phi90_p50x50_g17x20/task41_p0_saved_diagnostics_6h/"
    "7d12b524c385f3d211579a5b49772f36b4e0f1198e9364a49a0afc2733dbbc54/"
    "selected_incident_replay/attempt07.service/task41_p0_service_receipt.json"
)
TASK41_B0_V17_PRIOR_SERVICE_RECEIPT_SHA256 = (
    "d5c6f842fa55c1ac4f58dba23dce39d61dfe805d4f7844606b291f71139aa5d6"
)
TASK41_B0_V17_PRIOR_CONTRACT_RELATIVE = (
    TASK41_B0_CONTROLLER_RELATIVE
    / "execution_contract_source_17df17b39379001cf2bd368f05ed1da9118762ac"
    "_v17_selected_two_cell_replay_6h.json"
)
TASK41_B0_V17_PRIOR_CONTRACT_SHA256 = (
    "5ca97c97ab0c19d495a0f223c8fd39ce709b65a1723af054cd7fec103334c0e5"
)
TASK41_B0_V17_PRIOR_SOURCE_SHA = "17df17b39379001cf2bd368f05ed1da9118762ac"
TASK41_B0_V17_PRIOR_WINDOW_SHA256 = (
    "7d12b524c385f3d211579a5b49772f36b4e0f1198e9364a49a0afc2733dbbc54"
)
TASK41_P0_V17_SELECTED_TWO_CELL_WORKER_REPORT_RELATIVE = Path(
    "results/task41extra_phi90_p50x50_g17x20/task41_p0_saved_diagnostics_6h/"
    "7d12b524c385f3d211579a5b49772f36b4e0f1198e9364a49a0afc2733dbbc54/"
    "selected_incident_replay/attempt04/task41_p0_v17_selected_two_cell_worker.json"
)
TASK41_P0_V17_SELECTED_TWO_CELL_WORKER_REPORT_SHA256 = (
    "4e6fce6680a0bb304ed0370542f8b5c6003d39940d94ff3e54f19322aeb1709b"
)
TASK41_B0_V18_SAVED_JZ_NEW_EVIDENCE_BYTES = 16 * 1024**2
TASK41_B0_V18_SAVED_JZ_SCOPE = {
    "kind": "saved_jz_evaluation_candidate_only",
    "actions": ["saved_complete_jz_candidate", "independent_saved_jz_check"],
    "source_stars": ["v17_cells_7873_8014", "v14_cells_360_446", "v14_cells_23352_23493"],
    "columns": [0, 1],
    "complete_jz_inputs_max": 16,
    "new_evidence_limit_bytes": TASK41_B0_V18_SAVED_JZ_NEW_EVIDENCE_BYTES,
    "cumulative_raw_artifact_limit_bytes": 16 * 1024**3,
    "free_space_floor_bytes": 2 * 1024**3,
    "planned_working_set_max_bytes": 4 * 1024**3,
    "full_owner": False,
    "factor_or_lu": False,
    "getrs": 0,
    "native_fe_action": False,
    "integration": False,
    "carrier_replay": False,
    "full_q_scan": False,
    "official_result": False,
}

TASK41_COMPARISON_GROUP = "task41extra_phi90_p50x50_g17x20_g13_a1a2"
TASK41_TOTAL_SECONDS = 172_800.0
TASK41_NUMERICAL_SECONDS = 171_600.0
TASK41_CLOSEOUT_SECONDS = 1_200.0
TASK41_TASK_MEMORY_MAX_BYTES = 1_649_267_441_664
TASK41_HOST_RESERVE_BYTES = 68_719_476_736


class Task41ContractError(ValueError):
    """The fixed Task41 P0 execution contract is incomplete or inconsistent."""


def _task41_saved_diagnostics_instance(instance: str | None = None) -> dict[str, Any]:
    if instance is None:
        return {
            "instance": None,
            "window_relative": TASK41_B0_SAVED_DIAGNOSTICS_WINDOW_RELATIVE,
            "authorization_relative": TASK41_B0_SAVED_DIAGNOSTICS_AUTH_RELATIVE,
            "accounting_relative": (
                TASK41_B0_CONTROLLER_RELATIVE / "campaign_accounting_saved_diagnostics_6h.jsonl"
            ),
            "scope": TASK41_B0_SAVED_DIAGNOSTICS_SCOPE,
            "authorization": TASK41_B0_SAVED_DIAGNOSTICS_AUTHORIZATION,
            "prior_window_relative": TASK41_B0_V9_WINDOW_RELATIVE,
            "prior_ledger_relative": (
                TASK41_B0_CONTROLLER_RELATIVE / "campaign_accounting_v9_24h.jsonl"
            ),
            "t0_basis": "user_approved_saved_diagnostics_6h",
            "total_seconds": TASK41_B0_SAVED_DIAGNOSTICS_TOTAL_SECONDS,
            "numerical_seconds": TASK41_B0_SAVED_DIAGNOSTICS_NUMERICAL_SECONDS,
        }
    if instance == TASK41_B0_V12_CANDIDATE_REPLAY_INSTANCE:
        return {
            "instance": instance,
            "window_relative": TASK41_B0_V12_CANDIDATE_REPLAY_WINDOW_RELATIVE,
            "authorization_relative": TASK41_B0_V12_CANDIDATE_REPLAY_AUTH_RELATIVE,
            "accounting_relative": TASK41_B0_V12_CANDIDATE_REPLAY_ACCOUNTING_RELATIVE,
            "scope": TASK41_B0_V12_CANDIDATE_REPLAY_SCOPE,
            "authorization": "user_explicit_v12_two_cell_candidate_replay_6h",
            "prior_window_relative": TASK41_B0_SAVED_DIAGNOSTICS_WINDOW_RELATIVE,
            "prior_ledger_relative": (
                TASK41_B0_CONTROLLER_RELATIVE / "campaign_accounting_saved_diagnostics_6h.jsonl"
            ),
            "t0_basis": "user_approved_v12_two_cell_candidate_replay_6h",
            "total_seconds": TASK41_B0_SAVED_DIAGNOSTICS_TOTAL_SECONDS,
            "numerical_seconds": TASK41_B0_SAVED_DIAGNOSTICS_NUMERICAL_SECONDS,
        }
    if instance == TASK41_B0_V14_SAVED_RHS_CANDIDATE_INSTANCE:
        return {
            "instance": instance,
            "window_relative": TASK41_B0_V14_SAVED_RHS_CANDIDATE_WINDOW_RELATIVE,
            "authorization_relative": TASK41_B0_V14_SAVED_RHS_CANDIDATE_AUTH_RELATIVE,
            "accounting_relative": TASK41_B0_V14_SAVED_RHS_CANDIDATE_ACCOUNTING_RELATIVE,
            "scope": TASK41_B0_V14_SAVED_RHS_CANDIDATE_SCOPE,
            "authorization": "user_explicit_v14_same_lu_saved_candidate_6h",
            "prior_window_relative": TASK41_B0_V12_CANDIDATE_REPLAY_WINDOW_RELATIVE,
            "prior_ledger_relative": TASK41_B0_V12_CANDIDATE_REPLAY_ACCOUNTING_RELATIVE,
            "t0_basis": "user_approved_v14_same_lu_saved_candidate_6h",
            "requires_preexisting_user_authorization": True,
            "total_seconds": TASK41_B0_SAVED_DIAGNOSTICS_TOTAL_SECONDS,
            "numerical_seconds": TASK41_B0_SAVED_DIAGNOSTICS_NUMERICAL_SECONDS,
        }
    if instance == TASK41_B0_V15_FULL_ACCEPTANCE_INSTANCE:
        return {
            "instance": instance,
            "window_relative": TASK41_B0_V15_FULL_ACCEPTANCE_WINDOW_RELATIVE,
            "authorization_relative": TASK41_B0_V15_FULL_ACCEPTANCE_AUTH_RELATIVE,
            "accounting_relative": TASK41_B0_V15_FULL_ACCEPTANCE_ACCOUNTING_RELATIVE,
            "scope": TASK41_B0_V15_FULL_ACCEPTANCE_SCOPE,
            "authorization": "user_explicit_v15_full_two_column_acceptance_36h",
            "prior_window_relative": TASK41_B0_V14_SAVED_RHS_CANDIDATE_WINDOW_RELATIVE,
            "prior_ledger_relative": TASK41_B0_V14_SAVED_RHS_CANDIDATE_ACCOUNTING_RELATIVE,
            "t0_basis": "user_approved_v15_full_two_column_acceptance_36h",
            "requires_preexisting_user_authorization": True,
            "total_seconds": TASK41_B0_V15_FULL_ACCEPTANCE_TOTAL_SECONDS,
            "numerical_seconds": TASK41_B0_V15_FULL_ACCEPTANCE_NUMERICAL_SECONDS,
        }
    if instance == TASK41_B0_V16_SAVED_VECTOR_INSTANCE:
        return {
            "instance": instance,
            "window_relative": TASK41_B0_V16_SAVED_VECTOR_WINDOW_RELATIVE,
            "authorization_relative": TASK41_B0_V16_SAVED_VECTOR_AUTH_RELATIVE,
            "accounting_relative": TASK41_B0_V16_SAVED_VECTOR_ACCOUNTING_RELATIVE,
            "scope": TASK41_B0_V16_SAVED_VECTOR_SCOPE,
            "authorization": "user_explicit_v16_saved_vector_distribution_6h",
            "prior_window_relative": TASK41_B0_V15_FULL_ACCEPTANCE_WINDOW_RELATIVE,
            "prior_ledger_relative": TASK41_B0_V15_FULL_ACCEPTANCE_ACCOUNTING_RELATIVE,
            "t0_basis": "user_approved_v16_saved_vector_distribution_6h",
            "requires_preexisting_user_authorization": True,
            "total_seconds": 21_600.0,
            "numerical_seconds": 20_400.0,
        }
    if instance == TASK41_B0_V17_SELECTED_TWO_CELL_INSTANCE:
        return {
            "instance": instance,
            "window_relative": TASK41_B0_V17_SELECTED_TWO_CELL_WINDOW_RELATIVE,
            "authorization_relative": TASK41_B0_V17_SELECTED_TWO_CELL_AUTH_RELATIVE,
            "accounting_relative": TASK41_B0_V17_SELECTED_TWO_CELL_ACCOUNTING_RELATIVE,
            "scope": TASK41_B0_V17_SELECTED_TWO_CELL_SCOPE,
            "authorization": "user_explicit_v17_selected_two_cell_replay_6h",
            "prior_window_relative": TASK41_B0_V16_SAVED_VECTOR_WINDOW_RELATIVE,
            "prior_ledger_relative": TASK41_B0_V16_SAVED_VECTOR_ACCOUNTING_RELATIVE,
            "t0_basis": "user_approved_v17_selected_two_cell_replay_6h",
            "requires_preexisting_user_authorization": True,
            "total_seconds": 21_600.0,
            "numerical_seconds": 20_400.0,
        }
    if instance == TASK41_B0_V18_SAVED_JZ_INSTANCE:
        return {
            "instance": instance,
            "window_relative": TASK41_B0_V18_SAVED_JZ_WINDOW_RELATIVE,
            "authorization_relative": TASK41_B0_V18_SAVED_JZ_AUTH_RELATIVE,
            "accounting_relative": TASK41_B0_V18_SAVED_JZ_ACCOUNTING_RELATIVE,
            "scope": TASK41_B0_V18_SAVED_JZ_SCOPE,
            "authorization": "user_explicit_v18_saved_jz_candidate_6h",
            "prior_window_relative": TASK41_B0_V17_SELECTED_TWO_CELL_WINDOW_RELATIVE,
            "prior_ledger_relative": TASK41_B0_V17_SELECTED_TWO_CELL_ACCOUNTING_RELATIVE,
            "t0_basis": "user_approved_v18_saved_jz_candidate_6h",
            "requires_preexisting_user_authorization": True,
            "total_seconds": 21_600.0,
            "numerical_seconds": 20_400.0,
        }
    raise Task41ContractError(f"unknown saved-diagnostics instance: {instance!r}")


def _task41_p0_service_command(
    *,
    case_input: str,
    contract_path: str,
    saved_diagnostics_enabled: bool,
    saved_diagnostics_instance: str | None,
    v17_output_directory: str | None = None,
    v18_output_directory: str | None = None,
) -> list[str] | None:
    if not saved_diagnostics_enabled and saved_diagnostics_instance is not None:
        raise Task41ContractError("named saved-diagnostics command requires its named instance mode")
    if saved_diagnostics_enabled and saved_diagnostics_instance not in {
        TASK41_B0_V15_FULL_ACCEPTANCE_INSTANCE,
        TASK41_B0_V17_SELECTED_TWO_CELL_INSTANCE,
        TASK41_B0_V18_SAVED_JZ_INSTANCE,
    }:
        return None
    command = [
        "bash",
        "scripts/run_case_in_user_service.sh",
        case_input,
        "--task41-p0-execution-contract",
        contract_path,
    ]
    if saved_diagnostics_instance == TASK41_B0_V17_SELECTED_TWO_CELL_INSTANCE:
        if v17_output_directory is None:
            raise Task41ContractError("V17 service command requires its numbered output directory")
        command.extend(
            [
                "--task41-p0-b0-v17-selected-two-cell-replay",
                "--v16-manifest",
                str(TASK41_B0_V17_SAVED_VECTOR_MANIFEST_RELATIVE),
                "--v16-manifest-sha256",
                TASK41_B0_V17_SAVED_VECTOR_MANIFEST_SHA256,
                "--output-dir",
                v17_output_directory,
            ]
        )
    elif saved_diagnostics_instance == TASK41_B0_V18_SAVED_JZ_INSTANCE:
        if v18_output_directory is None:
            raise Task41ContractError("V18 service command requires its numbered output directory")
        command.extend([
            "--task41-p0-b0-v18-saved-jz-candidate",
            "--v18-output-directory",
            v18_output_directory,
        ])
    elif saved_diagnostics_instance == TASK41_B0_V15_FULL_ACCEPTANCE_INSTANCE:
        command.append("--task41-p0-b0-v15-full-acceptance")
    return command


def _task41_saved_diagnostics_instance_for_path(
    root: Path, path: Path
) -> dict[str, Any] | None:
    resolved = Path(path).resolve()
    for instance in (
        None,
        TASK41_B0_V12_CANDIDATE_REPLAY_INSTANCE,
        TASK41_B0_V14_SAVED_RHS_CANDIDATE_INSTANCE,
        TASK41_B0_V15_FULL_ACCEPTANCE_INSTANCE,
        TASK41_B0_V16_SAVED_VECTOR_INSTANCE,
        TASK41_B0_V17_SELECTED_TWO_CELL_INSTANCE,
        TASK41_B0_V18_SAVED_JZ_INSTANCE,
    ):
        config = _task41_saved_diagnostics_instance(instance)
        if resolved == (root / config["window_relative"]).resolve():
            return config
    return None


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


_TASK41_V9_PARENT_LEDGER_HASH_CACHE: dict[
    Path, tuple[tuple[int, int, int, int, int], str]
] = {}


def _task41_v9_parent_ledger_sha256(path: Path) -> str:
    """Hash the preserved 31.5 MB V6 ledger once per unchanged file identity."""

    resolved = path.resolve(strict=True)
    stat = resolved.stat()
    identity = (
        int(stat.st_dev),
        int(stat.st_ino),
        int(stat.st_size),
        int(stat.st_mtime_ns),
        int(stat.st_ctime_ns),
    )
    cached = _TASK41_V9_PARENT_LEDGER_HASH_CACHE.get(resolved)
    if cached is not None and cached[0] == identity:
        return cached[1]
    digest = sha256_file(resolved)
    _TASK41_V9_PARENT_LEDGER_HASH_CACHE[resolved] = (identity, digest)
    return digest


def _sha256_file_streamed(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def task41_b0_saved_surface_source_equivalence(
    *, current_root: str | Path | None = None,
) -> dict[str, Any]:
    """Check unchanged numerical dependencies and report the narrow consumer bridge."""
    root = Path(current_root or Path(__file__).resolve().parents[2]).resolve()
    bridge = TASK41_B0_SAVED_SURFACE_DONOR["source_equivalence_bridge"]
    producer_sha = str(bridge["producer_source_sha"])
    unchanged = {}
    bridged = {}
    for relative in bridge["unchanged_math_source_paths"]:
        current_path = (root / relative).resolve()
        if not current_path.is_file() or not current_path.is_relative_to(root):
            raise Task41ContractError("Task41 B0 saved-carrier math dependency is missing or escaped")
        old = subprocess.run(
            ["git", "show", f"{producer_sha}:{relative}"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
        old_sha = hashlib.sha256(old).hexdigest()
        current_sha = _sha256_file_streamed(current_path)
        if current_sha != old_sha:
            raise Task41ContractError(
                f"Task41 B0 saved-carrier numerical dependency changed: {relative}"
            )
        unchanged[relative] = {"producer_sha256": old_sha, "consumer_sha256": current_sha}
    for relative in bridge["execution_only_source_paths"]:
        current_path = (root / relative).resolve()
        if not current_path.is_file() or not current_path.is_relative_to(root):
            raise Task41ContractError("Task41 B0 consumer bridge source is missing or escaped")
        old = subprocess.run(
            ["git", "show", f"{producer_sha}:{relative}"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
        bridged[relative] = {
            "producer_sha256": hashlib.sha256(old).hexdigest(),
            "consumer_sha256": _sha256_file_streamed(current_path),
            "change_class": "read_only_donor_and_action_wiring",
            "numerical_kernel_equivalence": "verified by exact math-source hashes and fresh discrete identity gate",
        }
    return {
        "schema": bridge["schema"],
        "producer_source_sha": producer_sha,
        "unchanged_math_source_files": unchanged,
        "execution_only_source_files": bridged,
        "numerical_identity_fields_required": [
            "mesh", "cell_dofmap_sha256", "orientation", "basix_coefficients",
            "MPC", "config_sha256", "ABI", "ordered modes", "normalization H",
        ],
    }


def verify_task41_b0_saved_surface_donor(
    binding: Mapping[str, Any],
    *,
    current_root: str | Path | None = None,
    verify_source_equivalence: bool = True,
) -> dict[str, Any]:
    """Fail closed unless the exact accepted producer checkpoint is present."""
    root = Path(current_root or Path(__file__).resolve().parents[2]).resolve()
    if dict(binding) != TASK41_B0_SAVED_SURFACE_DONOR:
        raise Task41ContractError("Task41 B0 saved surface donor differs from the registered producer")
    donor_root = _resolve(root, str(binding["root_relative_path"]), "saved surface donor root")
    if not donor_root.is_relative_to(root / "results"):
        raise Task41ContractError("Task41 B0 saved surface donor escaped ignored results")
    binary = donor_root / str(binding["binary_name"])
    checkpoint_path = donor_root / str(binding["checkpoint_name"])
    manifest_path = donor_root / str(binding["manifest_name"])
    if not all(path.is_file() for path in (binary, checkpoint_path, manifest_path)):
        raise Task41ContractError("Task41 B0 require-existing saved surface donor is incomplete")
    committed = binding["committed"]
    producer = binding["producer"]
    if binary.stat().st_size != committed["bytes"]:
        raise Task41ContractError("Task41 B0 saved surface donor size differs from its committed prefix")
    checkpoint_sha = _sha256_file_streamed(checkpoint_path)
    manifest_sha = _sha256_file_streamed(manifest_path)
    if (
        checkpoint_sha != committed["checkpoint_sha256"]
        or manifest_sha != committed["manifest_sha256"]
    ):
        raise Task41ContractError("Task41 B0 saved surface donor metadata hash differs")
    try:
        checkpoint = json.loads(checkpoint_path.read_text(encoding="ascii"))
        with manifest_path.open("r", encoding="ascii") as stream:
            manifest = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise Task41ContractError("Task41 B0 saved surface donor metadata is unreadable") from exc
    identity = manifest.get("identity") if isinstance(manifest, dict) else None
    if not isinstance(identity, dict) or not isinstance(checkpoint, dict):
        raise Task41ContractError("Task41 B0 saved surface donor metadata is malformed")
    identity_sha = hashlib.sha256(
        json.dumps(
            identity, ensure_ascii=True, allow_nan=False,
            separators=(",", ":"), sort_keys=True,
        ).encode("ascii")
    ).hexdigest()
    if (
        manifest.get("identity_sha256") != producer["producer_identity_sha256"]
        or identity_sha != producer["producer_identity_sha256"]
        or identity.get("source_sha") != producer["source_sha"]
        or identity.get("input_sha256") != producer["input_sha256"]
        or identity.get("staged_input_sha256") != producer["input_sha256"]
        or identity.get("campaign_window_sha256") != producer["campaign_window_sha256"]
        or identity.get("execution_contract_sha256") != producer["execution_contract_sha256"]
        or identity.get("surface_scope") != "global"
        or identity.get("twist_index") is not None
        or identity.get("phase_gauge") != "boundary_plane"
        or identity.get("ordered_mode_manifest_sha256") != producer["ordered_mode_manifest_sha256"]
        or identity.get("mode_count") != committed["mode_count"]
        or not isinstance(identity.get("mesh_mpc_orientation"), Mapping)
        or manifest.get("schema") != "task40extra.v33_resumable_surface_functionals.v1"
        or len(manifest.get("mode_keys", ())) != committed["mode_count"]
        or len(manifest.get("mode_identities", ())) != committed["mode_count"]
        or len(manifest.get("normalization_h", ())) != committed["mode_count"]
        or checkpoint.get("identity_sha256") != producer["producer_identity_sha256"]
        or checkpoint.get("manifest_sha256") != committed["manifest_sha256"]
        or checkpoint.get("expected_mode_count") != committed["mode_count"]
        or checkpoint.get("committed_mode_count") != committed["mode_count"]
        or checkpoint.get("committed_bytes") != committed["bytes"]
        or checkpoint.get("committed_prefix_sha256") != committed["prefix_sha256"]
    ):
        raise Task41ContractError("Task41 B0 saved surface donor producer identity/checkpoint differs")
    source_equivalence = (
        task41_b0_saved_surface_source_equivalence(current_root=root)
        if verify_source_equivalence
        else None
    )
    return {
        "status": "REQUIRE_EXISTING_METADATA_BOUND_PREFIX_PENDING_FULL_VALIDATION",
        "root": str(donor_root),
        "binary_size_bytes": int(binary.stat().st_size),
        "checkpoint_sha256": checkpoint_sha,
        "manifest_sha256": manifest_sha,
        "producer_identity_sha256": identity_sha,
        "ordered_mode_manifest_sha256": identity["ordered_mode_manifest_sha256"],
        "source_equivalence": source_equivalence,
    }





def _task41_a2_q_csr_selector_entry(
    root: Path,
    manifest_raw_path: str | Path,
    *,
    expected_input_sha256: str,
    consumer_execution_identity: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Bind one exact Task41 q/twist CSR and its new consumer authorization."""
    from src.geometry.task41_phi90_profile import TASK41_G13_A2_PRECONDITIONER
    from src.solvers.task40_v10_p6_periodic_profile import TASK41_G13_A2_P6_PROFILE
    from src.solvers.task40_v30_qualified_q_csr import (
        V30_Q_CSR_MANIFEST_SCHEMA,
        V30_Q_CSR_NATIVE_SCHEMA,
        make_v31_q_csr_import_authorization,
    )

    manifest_path = _resolve(root, str(manifest_raw_path), "A2 q CSR manifest path")
    if not manifest_path.is_file() or not manifest_path.is_relative_to(root):
        raise Task41ContractError("Task41 A2 q manifest must be a repository artifact")
    manifest_sha = sha256_file(manifest_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise Task41ContractError("Task41 A2 q manifest is invalid JSON") from exc
    operator = manifest.get("operator_identity") if isinstance(manifest, dict) else None
    q = manifest.get("q_index") if isinstance(manifest, dict) else None
    twist = manifest.get("twist_index") if isinstance(manifest, dict) else None
    expected_twist = (
        q % TASK41_G13_A2_P6_PROFILE.replication_count
        if type(q) is int and 0 <= q < TASK41_G13_A2_P6_PROFILE.q_count
        else None
    )
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != V30_Q_CSR_MANIFEST_SCHEMA
        or manifest.get("status") != "COMPLETE_CSR"
        or type(q) is not int
        or expected_twist is None
        or type(twist) is not int
        or twist != expected_twist
        or manifest.get("profile") != TASK41_G13_A2_PRECONDITIONER
        or not isinstance(operator, Mapping)
        or operator.get("scientific_input_sha256") != expected_input_sha256
        or manifest_path.name
        != f"task40_v30_q{q}_twist{expected_twist}_csr_manifest.json"
    ):
        raise Task41ContractError(
            "Task41 A2 saved receipt must match this DAT/profile's exact q-to-twist CSR map"
        )
    qualification_path = manifest_path.with_name(
        f"task40_v30_q{q}_twist{expected_twist}_native_qualification.json"
    )
    if not qualification_path.is_file() or not qualification_path.resolve().is_relative_to(root):
        raise Task41ContractError(f"Task41 A2 q{q} native qualification is missing")
    qualification_sha = sha256_file(qualification_path)
    try:
        qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise Task41ContractError("Task41 A2 native qualification is invalid JSON") from exc
    if (
        not isinstance(qualification, dict)
        or qualification.get("schema") != V30_Q_CSR_NATIVE_SCHEMA
        or qualification.get("status") != "PASS"
        or qualification.get("q_index") != q
        or qualification.get("twist_index") != expected_twist
        or qualification.get("csr_manifest_sha256") != manifest_sha
    ):
        raise Task41ContractError(f"Task41 A2 q{q} native qualification does not bind its manifest")
    artifacts = manifest.get("csr_artifacts")
    if not isinstance(artifacts, Mapping):
        raise Task41ContractError(f"Task41 A2 q{q} manifest omits its CSR arrays")
    authorization_artifacts = {}
    for name in ("data", "indices", "indptr"):
        record = artifacts.get(name)
        if not isinstance(record, Mapping):
            raise Task41ContractError(f"Task41 A2 q{q} manifest omits CSR {name}")
        raw = Path(str(record.get("path", "")))
        path = (raw if raw.is_absolute() else manifest_path.parent / raw).resolve(strict=False)
        if not path.is_relative_to(root):
            raise Task41ContractError(f"Task41 A2 q{q} CSR {name} escaped the repository")
        authorization_artifacts[name] = {
            "path": str(path),
            "bytes": record.get("bytes"),
            "sha256": record.get("sha256"),
        }
    entry = {
        "q_index": q,
        "twist_index": expected_twist,
        "profile": TASK41_G13_A2_PRECONDITIONER,
        "shape": manifest.get("shape"),
        "operator_identity": operator,
        "matrix_source_identity": manifest.get("matrix_source_identity"),
        "execution_identity": manifest.get("execution_identity"),
        "csr_manifest": {"path": str(manifest_path), "sha256": manifest_sha},
        "native_qualification": {
            "path": str(qualification_path.resolve()),
            "sha256": qualification_sha,
            "status": "PASS",
        },
        "manifest_status": "COMPLETE_CSR",
        "qualification_status": "PASS",
        "manifest_sha256": manifest_sha,
        "native_qualification_sha256": qualification_sha,
    }
    authorization = make_v31_q_csr_import_authorization(
        q_index=q,
        twist_index=expected_twist,
        profile=TASK41_G13_A2_PRECONDITIONER,
        operator_identity=operator,
        matrix_source_identity=manifest.get("matrix_source_identity", {}),
        producer_identity=manifest.get("producer_identity", {}),
        producer_execution_identity=manifest.get("execution_identity", {}),
        native_execution_identity=qualification.get("execution_identity", {}),
        csr_manifest_sha256=manifest_sha,
        native_qualification_sha256=qualification_sha,
        csr_artifacts=authorization_artifacts,
        consumer_execution_identity=consumer_execution_identity,
    )
    return entry, authorization


def _prepare_task41_a2_q_csr_reuse(
    root: Path,
    manifest_paths: Sequence[str | Path],
    *,
    source_sha: str,
    window_sha256: str,
    expected_input_sha256: str,
) -> dict[str, Any]:
    from src.geometry.task41_phi90_profile import TASK41_G13_A2_PRECONDITIONER
    from src.solvers.task40_v10_p6_periodic_profile import TASK41_G13_A2_P6_PROFILE
    from src.solvers.task40_v30_qualified_q_csr import V30_Q_CSR_SELECTOR_SCHEMA

    q_indices = list(range(TASK41_G13_A2_P6_PROFILE.q_count))
    twist_indices_by_q = {
        str(q): q % TASK41_G13_A2_P6_PROFILE.replication_count for q in q_indices
    }
    if isinstance(manifest_paths, (str, bytes)) or len(manifest_paths) != len(q_indices):
        raise Task41ContractError("Task41 A2 q reuse requires one manifest for each of q=0..9")
    consumer = {"source_sha": source_sha, "window_sha256": window_sha256}
    entries, authorizations = [], {}
    for raw_path in manifest_paths:
        entry, authorization = _task41_a2_q_csr_selector_entry(
            root,
            raw_path,
            expected_input_sha256=expected_input_sha256,
            consumer_execution_identity=consumer,
        )
        q = int(entry["q_index"])
        if str(q) in authorizations:
            raise Task41ContractError("Task41 A2 q reuse repeats a manifest")
        entries.append(entry)
        authorizations[str(q)] = authorization
    entries.sort(key=lambda row: row["q_index"])
    if [row["q_index"] for row in entries] != q_indices or any(
        row["twist_index"] != twist_indices_by_q[str(row["q_index"])]
        for row in entries
    ):
        raise Task41ContractError("Task41 A2 q reuse must bind the exact ten-q twist map")
    selector = {
        "schema": V30_Q_CSR_SELECTOR_SCHEMA,
        "profile": TASK41_G13_A2_PRECONDITIONER,
        "q_csr_entries": entries,
    }
    selector_path = (
        root / TASK41_A2_CONTROLLER_RELATIVE
        / f"q_csr_reuse_selector_source_{source_sha}.json"
    )
    if not _write_json_no_replace(selector_path, selector):
        try:
            saved = json.loads(selector_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise Task41ContractError("existing Task41 A2 q selector cannot be reopened") from exc
        if saved != selector:
            raise Task41ContractError("existing Task41 A2 q selector differs from this binding")
    bindings = [
        {"q_index": row["q_index"], **row["csr_manifest"]} for row in entries
    ]
    return {
        "schema": TASK41_A2_Q_CSR_REUSE_SCHEMA,
        "q_indices": q_indices,
        "twist_indices_by_q": twist_indices_by_q,
        "profile": TASK41_G13_A2_PRECONDITIONER,
        "manifest_bindings": bindings,
        "selector_path": selector_path.relative_to(root).as_posix(),
        "selector_sha256": sha256_file(selector_path),
        "consumer_import_authorizations": authorizations,
    }


def _validate_task41_a2_q_csr_reuse(
    root: Path,
    reuse: Any,
    *,
    source_sha: str,
    window_sha256: str,
    expected_input_sha256: str,
) -> None:
    from src.geometry.task41_phi90_profile import TASK41_G13_A2_PRECONDITIONER
    from src.solvers.task40_v10_p6_periodic_profile import TASK41_G13_A2_P6_PROFILE
    from src.solvers.task40_v30_qualified_q_csr import V30_Q_CSR_SELECTOR_SCHEMA

    if not isinstance(reuse, Mapping):
        raise Task41ContractError("Task41 A2 q reuse contract is malformed")
    schema = reuse.get("schema")
    if schema == TASK41_A2_Q_CSR_REUSE_SCHEMA_V1:
        q_indices = [0, 5]
        twist_indices_by_q = {"0": 0, "5": 0}
        required_keys = {
            "schema", "q_indices", "twist_index", "profile", "manifest_bindings",
            "selector_path", "selector_sha256", "consumer_import_authorizations",
        }
        if reuse.get("twist_index") != 0:
            raise Task41ContractError("Task41 A2 v1 q reuse must be q0/q5 at twist zero")
        legacy_v1 = True
    elif schema == TASK41_A2_Q_CSR_REUSE_SCHEMA:
        q_indices = list(range(TASK41_G13_A2_P6_PROFILE.q_count))
        twist_indices_by_q = {
            str(q): q % TASK41_G13_A2_P6_PROFILE.replication_count for q in q_indices
        }
        required_keys = {
            "schema", "q_indices", "twist_indices_by_q", "profile", "manifest_bindings",
            "selector_path", "selector_sha256", "consumer_import_authorizations",
        }
        legacy_v1 = False
    else:
        raise Task41ContractError("Task41 A2 q reuse contract has an unsupported schema")
    if (
        set(reuse) != required_keys
        or reuse.get("q_indices") != q_indices
        or (
            not legacy_v1
            and reuse.get("twist_indices_by_q") != twist_indices_by_q
        )
        or reuse.get("profile") != TASK41_G13_A2_PRECONDITIONER
        or not _is_sha256(reuse.get("selector_sha256"))
    ):
        raise Task41ContractError("Task41 A2 q reuse contract is malformed")
    selector_path = _resolve(root, reuse["selector_path"], "A2 q reuse selector path")
    expected_path = (
        root / TASK41_A2_CONTROLLER_RELATIVE
        / f"q_csr_reuse_selector_source_{source_sha}.json"
    ).resolve()
    if selector_path != expected_path or not selector_path.is_file() or sha256_file(selector_path) != reuse["selector_sha256"]:
        raise Task41ContractError("Task41 A2 q reuse selector path or hash changed")
    selector = json.loads(selector_path.read_text(encoding="utf-8"))
    entries = selector.get("q_csr_entries") if isinstance(selector, Mapping) else None
    bindings = reuse.get("manifest_bindings")
    authorizations = reuse.get("consumer_import_authorizations")
    if (
        not isinstance(selector, Mapping)
        or selector.get("schema") != V30_Q_CSR_SELECTOR_SCHEMA
        or selector.get("profile") != TASK41_G13_A2_PRECONDITIONER
        or not isinstance(entries, list)
        or len(entries) != len(q_indices)
        or any(not isinstance(row, Mapping) for row in entries)
        or [row.get("q_index") for row in entries] != q_indices
        or not isinstance(bindings, list)
        or len(bindings) != len(q_indices)
        or any(not isinstance(row, Mapping) for row in bindings)
        or not isinstance(authorizations, Mapping)
        or set(authorizations) != {str(q) for q in q_indices}
    ):
        raise Task41ContractError("Task41 A2 q reuse selector or manifest bindings are incomplete")
    expected_consumer = {"source_sha": source_sha, "window_sha256": window_sha256}
    sorted_bindings = sorted(bindings, key=lambda row: row.get("q_index"))
    for q, entry, binding in zip(q_indices, entries, sorted_bindings):
        twist = twist_indices_by_q[str(q)]
        auth = authorizations[str(q)]
        manifest_ref = entry.get("csr_manifest")
        entry_profile_ok = (
            entry.get("profile") == TASK41_G13_A2_PRECONDITIONER
            if not legacy_v1
            else entry.get("profile") in (None, TASK41_G13_A2_PRECONDITIONER)
        )
        if (
            not isinstance(manifest_ref, Mapping)
            or binding.get("q_index") != q
            or binding.get("path") != manifest_ref.get("path")
            or binding.get("sha256") != manifest_ref.get("sha256")
            or not _is_sha256(binding.get("sha256"))
            or entry.get("twist_index") != twist
            or not entry_profile_ok
            or not isinstance(auth, Mapping)
            or auth.get("q_index") != q
            or auth.get("twist_index") != twist
            or auth.get("profile") != TASK41_G13_A2_PRECONDITIONER
            or auth.get("consumer_execution_identity") != expected_consumer
            or auth.get("csr_manifest_sha256") != binding.get("sha256")
        ):
            raise Task41ContractError(f"Task41 A2 q{q} reuse binding is not source-bound")
        manifest_path = _resolve(root, str(binding["path"]), f"A2 q{q} manifest path")
        if not manifest_path.is_file() or not manifest_path.is_relative_to(root) or sha256_file(manifest_path) != binding["sha256"]:
            raise Task41ContractError(f"Task41 A2 q{q} manifest hash changed")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        operator = manifest.get("operator_identity") if isinstance(manifest, Mapping) else None
        if (
            not isinstance(manifest, Mapping)
            or manifest.get("q_index") != q
            or manifest.get("twist_index") != twist
            or manifest.get("profile") != TASK41_G13_A2_PRECONDITIONER
            or not isinstance(operator, Mapping)
            or operator.get("scientific_input_sha256") != expected_input_sha256
        ):
            raise Task41ContractError(f"Task41 A2 q{q} manifest no longer matches this DAT/profile")

def _utc_text_from_ns(value: int) -> str:
    seconds, nanoseconds = divmod(int(value), 1_000_000_000)
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(seconds)) + (
        f".{nanoseconds:09d}Z"
    )


def _write_json_no_replace(path: Path, payload: Mapping[str, Any]) -> bool:
    """Atomically create one JSON file without ever replacing an existing record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            return False
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return True
    finally:
        temporary.unlink(missing_ok=True)


def _resolve(root: Path, raw: Any, label: str) -> Path:
    if not isinstance(raw, str) or not raw or "\n" in raw:
        raise Task41ContractError(f"{label} must be a nonempty path")
    path = Path(raw)
    return (path if path.is_absolute() else root / path).resolve()


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _is_task41_b0_saved_diagnostics_contract(
    contract: Mapping[str, Any], root: Path
) -> bool:
    case = contract.get("case")
    source = contract.get("source")
    window = contract.get("window")
    if (
        contract.get("task_id") != TASK41_MODEL_ID
        or not isinstance(case, Mapping)
        or case.get("model_id") != TASK41_MODEL_ID
        or case.get("run_id") != TASK41_B0_RUN_ID
        or not isinstance(source, Mapping)
        or not re.fullmatch(r"[0-9a-f]{40}", str(source.get("sha", "")))
        or not isinstance(window, Mapping)
        or not re.fullmatch(r"[0-9a-f]{40}", str(window.get("entry_source_sha", "")))
        or not re.fullmatch(r"[0-9a-f]{64}", str(window.get("authorization_sha256", "")))
    ):
        return False
    try:
        window_path = _resolve(root, window.get("path"), "window.path")
    except Task41ContractError:
        return False
    config = _task41_saved_diagnostics_instance_for_path(root, window_path)
    return bool(
        config is not None
        and contract.get("execution_scope") == config["scope"]
        and window.get("scope") == config["scope"]
    )


def _saved_output_consumer_source_sha(
    contract: Mapping[str, Any], root: Path, *, allow_current_source: bool = False
) -> str:
    head = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "branch", "--show-current")
    status = _git(root, "status", "--porcelain", "--untracked-files=normal")
    source_matches = head == contract.get("source", {}).get("sha")
    if (
        source_matches != allow_current_source
        or branch != contract.get("branch")
        or status
    ):
        identity_rule = "the current contracted source" if allow_current_source else "a distinct consumer head"
        raise Task41ContractError(
            f"saved-output audit requires {identity_rule} on the clean contracted branch"
        )
    return head


def _task41_case(case_id: str) -> dict[str, Any]:
    if case_id == "A1":
        return {
            "case_id": "A1",
            "run_id": TASK41_RUN_ID,
            "input_relative": TASK41_INPUT_RELATIVE,
            "controller_relative": TASK41_CONTROLLER_RELATIVE,
            "window_relative": TASK41_WINDOW_RELATIVE,
            "method": "full3d_direct",
            "service_relative": TASK41_A1_SERVICE_RELATIVE,
        }
    if case_id == "A2":
        from src.geometry.task41_phi90_profile import (
            TASK41_G13_A2_PRECONDITIONER,
            TASK41_COMPARISON_GROUP,
        )

        return {
            "case_id": "A2",
            "run_id": TASK41_A2_RUN_ID,
            "input_relative": TASK41_A2_INPUT_RELATIVE,
            "controller_relative": TASK41_A2_CONTROLLER_RELATIVE,
            "window_relative": TASK41_A2_WINDOW_RELATIVE,
            "method": "full3d_iterative",
            "service_relative": TASK41_A2_SERVICE_RELATIVE,
            "profile_identity": TASK41_G13_A2_PRECONDITIONER,
            "comparison_group": TASK41_COMPARISON_GROUP,
            "solver_stage": "TASK41_A2",
        }
    if case_id == "B0":
        return {
            "case_id": "B0",
            "run_id": TASK41_B0_RUN_ID,
            "input_relative": TASK41_B0_INPUT_RELATIVE,
            "controller_relative": TASK41_B0_CONTROLLER_RELATIVE,
            "window_relative": TASK41_B0_WINDOW_RELATIVE,
            "method": "full3d_iterative",
            "service_relative": TASK41_B0_SERVICE_RELATIVE,
            "profile_identity": TASK41_B0_PRECONDITIONER,
            "comparison_group": TASK41_B0_COMPARISON_GROUP,
            "solver_stage": "TASK41_B0",
        }
    raise Task41ContractError("Task41 P0 case id must be A1, A2, or B0")


def task41_case_id_for_run_id(run_id: str) -> str:
    if run_id == TASK41_RUN_ID:
        return "A1"
    if run_id == TASK41_A2_RUN_ID:
        return "A2"
    if run_id == TASK41_B0_RUN_ID:
        return "B0"
    raise Task41ContractError("Task41 run id is not registered for P0")


def task41_p0_checker_kind_for_case(case_id: str) -> str:
    """Return the independently audited checker identity for a P0 case."""
    try:
        return TASK41_P0_CHECKER_KIND_BY_CASE[case_id]
    except KeyError as exc:
        raise Task41ContractError("Task41 checker case id is not registered for P0") from exc


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _checked_binding_file(
    root: Path,
    record: Any,
    label: str,
    *,
    within: Path,
) -> Path:
    if not isinstance(record, Mapping):
        raise Task41ContractError(f"A1 comparison binding {label} record is missing")
    path = _resolve(root, record.get("path"), f"A1 binding {label}.path")
    if not path.is_relative_to(within):
        raise Task41ContractError(f"A1 comparison binding {label} escaped its registered tree")
    if (
        type(record.get("bytes")) is not int
        or record["bytes"] <= 0
        or not _is_sha256(record.get("sha256"))
        or not path.is_file()
        or path.stat().st_size != record["bytes"]
        or sha256_file(path) != record["sha256"]
    ):
        raise Task41ContractError(f"A1 comparison binding {label} file identity changed")
    return path


def require_task41_a1_comparison_binding(
    path: str | Path | None = None,
    *,
    expected_sha256: str | None = None,
    current_root: str | Path | None = None,
) -> tuple[dict[str, Any], str]:
    """Reopen the immutable, checker-PASS A1 evidence used by the A2 case."""
    root = Path(current_root or Path(__file__).resolve().parents[2]).resolve()
    binding_path = _resolve(
        root,
        str(path or TASK41_A1_COMPARISON_BINDING_RELATIVE),
        "A1 comparison binding path",
    )
    if binding_path != (root / TASK41_A1_COMPARISON_BINDING_RELATIVE).resolve():
        raise Task41ContractError("A1 comparison binding is outside the registered A2 controller")
    raw = binding_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise Task41ContractError("A1 comparison binding SHA-256 differs from the A2 contract")
    binding = json.loads(raw)
    if not isinstance(binding, dict) or binding.get("schema") != TASK41_A1_COMPARISON_BINDING_SCHEMA:
        raise Task41ContractError("A1 comparison binding schema is invalid")
    if (
        binding.get("status") != "PASS"
        or binding.get("task_id") != TASK41_MODEL_ID
        or binding.get("comparison_group") != TASK41_COMPARISON_GROUP
    ):
        raise Task41ContractError("A1 comparison binding does not identify a passed Task41 comparison")
    a1 = binding.get("a1")
    if not isinstance(a1, Mapping):
        raise Task41ContractError("A1 comparison binding has no A1 identity")
    source_sha = a1.get("source_sha")
    if (
        a1.get("run_id") != TASK41_RUN_ID
        or a1.get("model_id") != TASK41_MODEL_ID
        or a1.get("method") != "full3d_direct"
        or a1.get("mpi_size") != 1
        or not isinstance(source_sha, str)
        or re.fullmatch(r"[0-9a-f]{40}", source_sha) is None
        or a1.get("input_path") != str(TASK41_INPUT_RELATIVE)
        or not _is_sha256(a1.get("input_sha256"))
        or not _is_sha256(a1.get("physical_model_sha256"))
        or not _is_sha256(a1.get("resolved_config_sha256"))
    ):
        raise Task41ContractError("A1 comparison binding has an invalid run/input/physics identity")
    input_path = (root / TASK41_INPUT_RELATIVE).resolve()
    if not input_path.is_file() or sha256_file(input_path) != a1["input_sha256"]:
        raise Task41ContractError("A1 comparison binding does not match the registered A1 DAT")

    run_root = _resolve(root, a1.get("run_root"), "A1 binding run_root")
    registered_results = (root / "results" / TASK41_MODEL_ID).resolve()
    if not run_root.is_relative_to(registered_results) or not run_root.is_dir():
        raise Task41ContractError("A1 comparison run root is missing or outside Task41 results")
    manifest_path = _checked_binding_file(
        root, a1.get("run_manifest"), "run_manifest", within=run_root
    )
    summary_path = _checked_binding_file(
        root, a1.get("numerical_summary"), "numerical_summary", within=run_root
    )
    resolved_path = _checked_binding_file(
        root, a1.get("resolved_config"), "resolved_config", within=run_root
    )
    if (
        manifest_path != run_root / "run_manifest.json"
        or summary_path != run_root / "numerical_output" / "run_summary.json"
        or resolved_path != run_root / "resolved_config.json"
        or sha256_file(resolved_path) != a1["resolved_config_sha256"]
    ):
        raise Task41ContractError("A1 comparison run manifest/config paths are inconsistent")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    numerical = json.loads(summary_path.read_text(encoding="utf-8"))
    for key, expected in {
        "model_id": TASK41_MODEL_ID,
        "run_id": TASK41_RUN_ID,
        "method": "full3d_direct",
        "mpi_size": 1,
        "source_sha": source_sha,
        "input_sha256": a1["input_sha256"],
        "physical_model_sha256": a1["physical_model_sha256"],
        "resolved_config_sha256": a1["resolved_config_sha256"],
    }.items():
        if manifest.get(key) != expected:
            raise Task41ContractError(f"A1 run manifest {key} differs from its comparison binding")
    if numerical.get("official_result") is not True or numerical.get("case_status") != "completed":
        raise Task41ContractError("A1 numerical summary is not an official completed result")

    checker_dir = (
        root / _task41_case("A1")["service_relative"] / f"service_source_{source_sha}"
    ).resolve()
    checker_path = _checked_binding_file(
        root, a1.get("required_checker"), "required_checker", within=checker_dir
    )
    if checker_path != checker_dir / "task41_p0_checker_result.json":
        raise Task41ContractError("A1 required checker path is not the registered checker receipt")
    checker = json.loads(checker_path.read_text(encoding="utf-8"))
    if (
        a1["required_checker"].get("schema") != "task41.p0.direct_checker.v1"
        or checker.get("schema") != "task41.p0.direct_checker.v1"
        or checker.get("status") != "PASS"
        or checker.get("checker_passed") is not True
        or checker.get("full_pass") is not True
        or checker.get("official_result") is not True
        or checker.get("run_id") != TASK41_RUN_ID
        or checker.get("source_sha") != source_sha
        or checker.get("input_sha256") != a1["input_sha256"]
        or checker.get("physical_model_sha256") != a1["physical_model_sha256"]
        or checker.get("resolved_config_sha256") != a1["resolved_config_sha256"]
    ):
        raise Task41ContractError("A1 required checker is not a matching PASS receipt")

    discrete = a1.get("discrete_identity")
    if not isinstance(discrete, Mapping):
        raise Task41ContractError("A1 comparison binding omits discrete FE/mode identity")
    if (
        not _is_sha256(discrete.get("mesh_sha256"))
        or not _is_sha256(discrete.get("mode_manifest_sha256"))
        or not _is_sha256(discrete.get("ordered_mode_key_sha256"))
        or discrete.get("mode_count") != 168
        or discrete.get("full_fe_rows") != 934764
    ):
        raise Task41ContractError("A1 comparison binding has an invalid mesh/mode/FE identity")
    map_status = discrete.get("mpc_map_status")
    map_sha = discrete.get("mpc_map_sha256")
    comparison_ready = discrete.get("same_discrete_comparison_ready")
    if map_status == "PASS":
        if not _is_sha256(map_sha) or comparison_ready is not True:
            raise Task41ContractError("A1 MPC map identity status is internally inconsistent")
    elif map_status == "NOT_RECORDED":
        if map_sha is not None or comparison_ready is not False:
            raise Task41ContractError("A1 missing MPC map identity must remain explicitly unqualified")
    else:
        raise Task41ContractError("A1 MPC map identity must be PASS or explicitly NOT_RECORDED")
    abi = a1.get("abi_identity")
    if (
        not isinstance(abi, Mapping)
        or abi.get("scalar_type") != "complex128"
        or abi.get("int_type") != "int32"
        or abi.get("mpi_size") != 1
    ):
        raise Task41ContractError("A1 comparison binding does not identify the qualified numerical ABI")

    artifacts = a1.get("comparison_artifacts")
    required_artifacts = {
        "full_solution",
        "native_a6_residual",
        "airbox_fields",
        "full3d_samples_archive",
        "full3d_samples_metadata",
        "modal_amplitudes",
        "port_power_metrics",
        "volume_absorption",
        "diffraction_orders",
        "mesh_h5",
        "mesh_xdmf",
    }
    if not isinstance(artifacts, Mapping) or not required_artifacts.issubset(artifacts):
        raise Task41ContractError("A1 comparison binding omits required field/mode/power artifacts")
    checked_artifacts = {}
    for name in sorted(required_artifacts):
        artifact_path = _checked_binding_file(
            root, artifacts[name], f"comparison_artifacts.{name}", within=run_root
        )
        checked_artifacts[name] = {
            "path": str(artifact_path.relative_to(root)),
            "bytes": artifacts[name]["bytes"],
            "sha256": artifacts[name]["sha256"],
        }
    field_record = artifacts["full_solution"]
    if field_record.get("array_key") != "recovered_field" or field_record.get("rank") != 0:
        raise Task41ContractError("A1 full FE field binding must select rank-0 recovered_field")
    return binding, digest


def contract_relative_path(
    source_sha: str,
    case_id: str = "A1",
    *,
    saved_diagnostics_instance: str | None = None,
) -> Path:
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise Task41ContractError("Task41 source SHA is invalid")
    case = _task41_case(case_id)
    suffix_by_instance = {
        None: "",
        TASK41_B0_V12_CANDIDATE_REPLAY_INSTANCE: f"_{TASK41_B0_V12_CANDIDATE_REPLAY_INSTANCE}",
        TASK41_B0_V14_SAVED_RHS_CANDIDATE_INSTANCE: f"_{TASK41_B0_V14_SAVED_RHS_CANDIDATE_INSTANCE}",
        TASK41_B0_V15_FULL_ACCEPTANCE_INSTANCE: f"_{TASK41_B0_V15_FULL_ACCEPTANCE_INSTANCE}",
        TASK41_B0_V16_SAVED_VECTOR_INSTANCE: f"_{TASK41_B0_V16_SAVED_VECTOR_INSTANCE}",
        TASK41_B0_V17_SELECTED_TWO_CELL_INSTANCE: f"_{TASK41_B0_V17_SELECTED_TWO_CELL_INSTANCE}",
        TASK41_B0_V18_SAVED_JZ_INSTANCE: f"_{TASK41_B0_V18_SAVED_JZ_INSTANCE}",
    }
    if saved_diagnostics_instance not in suffix_by_instance:
        raise Task41ContractError("unknown saved-diagnostics contract filename instance")
    suffix = suffix_by_instance[saved_diagnostics_instance]
    return case["controller_relative"] / f"execution_contract_source_{source_sha}{suffix}.json"


TASK41_V15_RETRY_AUTH_RELATIVE = (
    TASK41_B0_CONTROLLER_RELATIVE / "v15_one_additional_build_authorization.json"
)


TASK41_V15_TIME_CONTINUATION_AUTH_RELATIVE = (
    TASK41_B0_CONTROLLER_RELATIVE / "v15_time_prediction_continuation_authorization.json"
)


def task41_v15_owner_claim_authority(
    *, root: Path, accounting_path: Path, window_path: Path,
    window_sha256: str, retry_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve the original claim or one explicitly approved JIT-failure retry.

    The original window and claim remain immutable. A fixed second claim path
    prevents another attempt name from granting an additional construction.
    """
    root = root.resolve()
    original = accounting_path.resolve().with_name(
        accounting_path.name + ".v15_full_owner_claim.json"
    )
    result = {"claim_path": str(original), "full_owner_build_count": 1,
              "retry_authorization": None}
    if retry_binding is None:
        return result
    if not isinstance(retry_binding, Mapping):
        raise Task41ContractError("V15 additional-build authorization path/hash differs")
    bound_path = _resolve(root, retry_binding.get("path"), "retry authorization")
    continuation = bound_path == (root / TASK41_V15_TIME_CONTINUATION_AUTH_RELATIVE).resolve()
    sequence = 2 if continuation else 1
    auth_path = (root / (TASK41_V15_TIME_CONTINUATION_AUTH_RELATIVE
                        if continuation else TASK41_V15_RETRY_AUTH_RELATIVE)).resolve()
    predecessor = (original.with_name(original.name + ".authorized_retry_1.json")
                   if continuation else original)
    if (not isinstance(retry_binding, Mapping)
            or set(retry_binding) != {"path", "sha256"}
            or _resolve(root, retry_binding["path"], "retry authorization") != auth_path
            or sha256_file(auth_path) != retry_binding["sha256"]):
        raise Task41ContractError("V15 additional-build authorization path/hash differs")
    auth = json.loads(auth_path.read_text())
    if (auth.get("schema") != "task41.v15.one_additional_build_authorization.v1"
            or auth.get("user_decision") != "APPROVED"
            or auth.get("additional_builds") != 1
            or auth.get("retry_sequence") != sequence
            or auth.get("success_exit") != "acceptance_only"
            or auth.get("fixed_window_unchanged") is not True
            or _resolve(root, auth.get("window_path"), "retry window") != window_path.resolve()
            or auth.get("window_sha256") != window_sha256
            or sha256_file(window_path) != window_sha256
            or _resolve(root, auth.get("previous_claim_path"), "previous claim") != predecessor
            or sha256_file(predecessor) != auth.get("previous_claim_sha256")):
        raise Task41ContractError("V15 additional-build authorization does not bind the old claim/window")
    _utc_ns(auth.get("approved_utc"))
    if continuation and auth.get("time_prediction_policy") != "observe_only_fixed_cutoff":
        raise Task41ContractError("V15 continuation needs explicit forecast-only authorization")
    old = json.loads(predecessor.read_text())
    failed_run = _resolve(root, auth.get("failed_run_directory"), "failed run")
    summary_path = failed_run / "task40_v10_p6_candidate_summary.json"
    if (not failed_run.is_relative_to(root / "results" / TASK41_MODEL_ID)
            or sha256_file(summary_path) != auth.get("failed_summary_sha256")
            or old.get("status") != "BUILD_STARTED"
            or old.get("full_owner_build_count") != sequence
            or old.get("window_sha256") != window_sha256
            or Path(old.get("output_directory", "")).resolve() != failed_run):
        raise Task41ContractError("V15 retry predecessor claim/run identity differs")
    failed = json.loads(summary_path.read_text())
    cleanup = failed.get("v15_cleanup", {})
    if (failed.get("source_sha") != old.get("source_sha")
            or failed.get("status") != "FAILED"
            or failed.get("error", {}).get("message")
            != ("cannot access local variable 'V14ResourceStop' where it is not associated with a value"
                if continuation else "compiled FFCx module hash differs from frozen V6 profile")
            or cleanup.get("completed") is not True
            or cleanup.get("passed") is not True or cleanup.get("errors") != []):
        raise Task41ContractError("V15 retry requires the preserved cleaned JIT-identity failure")
    result.update({
        "claim_path": str(original.with_name(original.name + f".authorized_retry_{sequence}.json")),
        "full_owner_build_count": sequence + 1,
        "time_prediction_policy": ("observe_only_fixed_cutoff" if continuation else "enforce"),
        "retry_authorization": dict(retry_binding),
    })
    return result


def require_task41_p0_contract(
    path: str | Path,
    *,
    expected_sha256: str | None = None,
    current_root: str | Path | None = None,
    require_clean_source: bool = False,
    check_current_source: bool = False,
    case_id: str | None = None,
) -> tuple[dict[str, Any], str]:
    root = Path(current_root or Path(__file__).resolve().parents[2]).resolve()
    contract_path = _resolve(root, str(path), "contract path")
    try:
        relative = contract_path.relative_to(root)
    except ValueError as exc:
        raise Task41ContractError("Task41 contract escaped the repository") from exc
    if case_id is None:
        if relative.parent == TASK41_A2_CONTROLLER_RELATIVE:
            case_id = "A2"
        elif relative.parent == TASK41_B0_CONTROLLER_RELATIVE:
            case_id = "B0"
        elif relative.parent == TASK41_CONTROLLER_RELATIVE:
            case_id = "A1"
        else:
            raise Task41ContractError("Task41 contract is outside a registered P0 controller directory")
    case_spec = _task41_case(case_id)
    if relative.parent != case_spec["controller_relative"] or not re.fullmatch(
        r"execution_contract_source_[0-9a-f]{40}(?:_v12_two_cell_candidate_replay|_v14_same_lu_rhs_candidate_6h|_v15_full_two_column_acceptance_36h|_v16_saved_vector_distribution_6h|_v17_selected_two_cell_replay_6h|_v18_saved_jz_candidate_6h)?\.json",
        relative.name,
    ):
        raise Task41ContractError("Task41 contract is not in the registered P0 controller directory")
    raw = contract_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise Task41ContractError("Task41 contract SHA-256 differs from the launch binding")
    contract = json.loads(raw)
    if not isinstance(contract, dict) or contract.get("schema") != TASK41_P0_CONTRACT_SCHEMA:
        raise Task41ContractError("Task41 P0 execution contract schema is invalid")
    if contract.get("task_id") != TASK41_MODEL_ID or contract.get("branch") != TASK41_BRANCH:
        raise Task41ContractError("Task41 contract task or branch identity differs")
    source = contract.get("source")
    case = contract.get("case")
    runtime = contract.get("runtime")
    window = contract.get("window")
    resources = contract.get("resources")
    time_limits = contract.get("time")
    evidence = contract.get("evidence")
    if not all(
        isinstance(item, dict)
        for item in (source, case, runtime, window, resources, time_limits, evidence)
    ):
        raise Task41ContractError("Task41 contract sections must be JSON objects")
    if not re.fullmatch(r"[0-9a-f]{40}", str(source.get("sha", ""))):
        raise Task41ContractError("Task41 contract source SHA is invalid")
    contract_window_path = _resolve(root, window.get("path"), "window.path")
    saved_config_for_name = (
        _task41_saved_diagnostics_instance_for_path(root, contract_window_path)
        if case_id == "B0"
        else None
    )
    expected_relative = contract_relative_path(
        str(source["sha"]),
        case_id,
        saved_diagnostics_instance=(
            saved_config_for_name["instance"] if saved_config_for_name else None
        ),
    )
    if relative != expected_relative:
        raise Task41ContractError("Task41 contract filename is not bound to its source SHA")
    if check_current_source:
        if _git(root, "rev-parse", "HEAD") != source["sha"]:
            raise Task41ContractError("Task41 source HEAD differs from the fixed contract")
        if _git(root, "branch", "--show-current") != TASK41_BRANCH:
            raise Task41ContractError("Task41 current branch differs from the fixed contract")
    if require_clean_source and _git(
        root, "status", "--porcelain", "--untracked-files=normal"
    ):
        raise Task41ContractError("Task41 formal execution requires a clean frozen source tree")

    input_path = _resolve(root, case.get("input_path"), "Task41 DAT path")
    if (
        input_path != (root / case_spec["input_relative"]).resolve()
        or not input_path.is_file()
        or sha256_file(input_path) != case.get("input_sha256")
        or case.get("model_id") != TASK41_MODEL_ID
        or case.get("run_id") != case_spec["run_id"]
        or not re.fullmatch(r"[0-9a-f]{64}", str(case.get("physical_model_sha256", "")))
        or not re.fullmatch(r"[0-9a-f]{64}", str(case.get("resolved_config_sha256", "")))
        or case.get("method") != case_spec["method"]
        or case.get("mpi_size") != 1
    ):
        raise Task41ContractError("Task41 contract does not bind its registered P0 input")
    if case_id == "B0":
        from src.geometry.task41_phi90_profile import (
            TASK41_B0_GEOMETRY_IDENTITY,
        )

        if (
            case.get("profile_identity") != case_spec["profile_identity"]
            or case.get("solver_stage") != case_spec["solver_stage"]
            or case.get("comparison_group") != case_spec["comparison_group"]
            or case.get("geometry_identity") != TASK41_B0_GEOMETRY_IDENTITY
        ):
            raise Task41ContractError("Task41 B0 contract profile or physical identity differs")
        preparation = contract.get("preparation")
        if (
            not isinstance(preparation, Mapping)
            or preparation.get("existing_surface_donor")
            != TASK41_B0_SAVED_SURFACE_DONOR
        ):
            raise Task41ContractError(
                "Task41 B0 contract must bind the exact require-existing saved surface donor"
            )
    elif contract.get("preparation") is not None:
        raise Task41ContractError("saved B0 surface donor binding is available only to Task41 B0")

    for key in ("runtime_prefix", "abi_receipt_path", "jit_cache"):
        if not _resolve(root, runtime.get(key), f"runtime.{key}").exists():
            raise Task41ContractError(f"Task41 runtime.{key} does not exist")
    runtime_prefix = _resolve(root, runtime["runtime_prefix"], "runtime.runtime_prefix")
    if not (runtime_prefix / "bin" / "python").is_file() or not os.access(
        runtime_prefix / "bin" / "python", os.X_OK
    ):
        raise Task41ContractError("Task41 runtime prefix has no executable bin/python")
    abi_path = _resolve(root, runtime["abi_receipt_path"], "runtime.abi_receipt_path")
    if sha256_file(abi_path) != runtime.get("abi_receipt_sha256"):
        raise Task41ContractError("Task41 ABI receipt hash differs from the contract")
    if runtime.get("mpi_ranks") != 1 or runtime.get("math_threads") != 1:
        raise Task41ContractError("Task41 runtime must be MPI1 with one math thread")
    if runtime.get("profile") != "native_linux":
        raise Task41ContractError("formal Task41 P0 execution requires the registered native_linux runtime")
    numerical_strategy = contract.get("numerical_strategy")
    is_v9_contract = (
        case_id == "B0"
        and _resolve(root, window.get("path"), "window.path")
        == (root / TASK41_B0_V9_WINDOW_RELATIVE).resolve()
    )
    saved_diagnostics_config = (
        _task41_saved_diagnostics_instance_for_path(
            root, _resolve(root, window.get("path"), "window.path")
        )
        if case_id == "B0"
        else None
    )
    is_saved_diagnostics_contract = saved_diagnostics_config is not None
    is_v14_rhs_candidate_contract = bool(
        is_saved_diagnostics_contract
        and saved_diagnostics_config["instance"]
        == TASK41_B0_V14_SAVED_RHS_CANDIDATE_INSTANCE
    )
    is_v15_full_acceptance_contract = bool(
        is_saved_diagnostics_contract
        and saved_diagnostics_config["instance"]
        == TASK41_B0_V15_FULL_ACCEPTANCE_INSTANCE
    )
    is_v17_selected_two_cell_contract = bool(
        is_saved_diagnostics_contract
        and saved_diagnostics_config["instance"]
        == TASK41_B0_V17_SELECTED_TWO_CELL_INSTANCE
    )
    is_v18_saved_jz_contract = bool(
        is_saved_diagnostics_contract
        and saved_diagnostics_config["instance"] == TASK41_B0_V18_SAVED_JZ_INSTANCE
    )
    expected_same_lu_strategy = {
        "schema": "task41.p0.b0.internal_rhs_strategy.v1",
        "internal_rhs_strategy": TASK41_B0_V9_INTERNAL_RHS_STRATEGY,
    }
    expected_v14_refined_strategy = {
        "schema": "task41.p0.b0.internal_rhs_strategy.v2",
        "internal_rhs_strategy": TASK41_B0_V9_INTERNAL_RHS_STRATEGY,
        "refinement_strategy": TASK41_B0_V14_RHS_REFINEMENT_STRATEGY,
        "refinement_max_steps": 2,
    }
    expected_v18_jz_strategy = {
        "schema": "task41.p0.b0.internal_rhs_strategy.v3",
        "internal_rhs_strategy": TASK41_B0_V9_INTERNAL_RHS_STRATEGY,
        "refinement_strategy": TASK41_B0_V14_RHS_REFINEMENT_STRATEGY,
        "refinement_max_steps": 2,
        "jz_evaluation_strategy": "binary64_real_imag_fsum",
    }
    if contract.get("full_owner_retry_authorization") is not None:
        if not is_v15_full_acceptance_contract:
            raise Task41ContractError("additional-build authorization is V15-only")
        task41_v15_owner_claim_authority(
            root=root,
            accounting_path=root / TASK41_B0_V15_FULL_ACCEPTANCE_ACCOUNTING_RELATIVE,
            window_path=contract_window_path, window_sha256=window["sha256"],
            retry_binding=contract["full_owner_retry_authorization"],
        )
    if is_v18_saved_jz_contract:
        if numerical_strategy != expected_v18_jz_strategy:
            raise Task41ContractError(
                "Task41 V18 scope requires the exact same-LU refinement and opt-in Jz evaluator identity"
            )
    elif is_v15_full_acceptance_contract or is_v17_selected_two_cell_contract:
        if numerical_strategy != expected_v14_refined_strategy:
            raise Task41ContractError(
                "Task41 V15/V17 scope requires the exact same-LU binary64/fsum refinement-v2 strategy"
            )
    elif is_v14_rhs_candidate_contract:
        if numerical_strategy not in (
            expected_same_lu_strategy,
            expected_v14_refined_strategy,
        ):
            raise Task41ContractError(
                "Task41 V14 consumer must retain its exact v1 historical binding or use the explicit v2 refined binding"
            )
    elif is_v9_contract or is_saved_diagnostics_contract:
        if numerical_strategy != expected_same_lu_strategy:
            raise Task41ContractError(
                "Task41 V9/saved-diagnostics contract must explicitly bind same_lu_rhs_solve"
            )
    elif numerical_strategy is not None and numerical_strategy != {
        "schema": "task41.p0.b0.internal_rhs_strategy.v1",
        "internal_rhs_strategy": "stored_T",
    }:
        raise Task41ContractError("non-V9 Task41 contracts must retain the stored_T default")
    window_path, total_seconds, numerical_seconds, _continuation = task41_window_spec(contract, root)
    if is_saved_diagnostics_contract:
        assert saved_diagnostics_config is not None
        if contract.get("execution_scope") != saved_diagnostics_config["scope"]:
            raise Task41ContractError(
                "six-hour B0 contract does not carry the exact saved-diagnostics-only scope"
            )
        authorization, authorization_sha = _task41_saved_diagnostics_authorization(
            root, instance=saved_diagnostics_config["instance"]
        )
        expected_preparation_identity = {
            "saved_diagnostics_prior_window_path": authorization["prior_window_path"],
            "saved_diagnostics_prior_window_sha256": authorization["prior_window_sha256"],
            "saved_diagnostics_prior_ledger_path": authorization["prior_ledger_path"],
            "saved_diagnostics_prior_ledger_sha256": authorization["prior_ledger_sha256"],
        }
        preparation = contract.get("preparation")
        if (
            not isinstance(preparation, Mapping)
            or any(preparation.get(key) != value for key, value in expected_preparation_identity.items())
            or window.get("authorization_sha256") != authorization_sha
            or window.get("scope") != saved_diagnostics_config["scope"]
        ):
            raise Task41ContractError(
                "six-hour B0 contract does not preserve its authorization and prior window/ledger identity"
            )
    elif contract.get("execution_scope") is not None:
        raise Task41ContractError(
            "saved-diagnostics execution scope cannot be attached to a full Task41 worker contract"
        )
    if not re.fullmatch(r"[0-9a-f]{64}", str(window.get("sha256", ""))):
        raise Task41ContractError("Task41 fixed window SHA-256 is invalid")
    if (
        resources.get("task_memory_max_bytes") != TASK41_TASK_MEMORY_MAX_BYTES
        or resources.get("host_reserve_bytes") != TASK41_HOST_RESERVE_BYTES
        or resources.get("memory_swap_max_bytes") != 0
    ):
        raise Task41ContractError("Task41 resource limits differ from the task ceiling")
    if (
        time_limits.get("total_seconds") != total_seconds
        or time_limits.get("numerical_seconds") != numerical_seconds
        or time_limits.get("closeout_seconds") != TASK41_CLOSEOUT_SECONDS
    ):
        raise Task41ContractError("Task41 contract time limits differ from the fixed P0 window")
    task41_raw_artifact_limit_bytes(contract)
    service_directory = _resolve(root, evidence.get("service_directory"), "evidence.service_directory")
    expected_service_directory = (
        root / case_spec["service_relative"] / f"service_source_{source['sha']}"
    ).resolve()
    if service_directory != expected_service_directory:
        raise Task41ContractError("Task41 service evidence directory differs from the registered case")
    comparison = contract.get("comparison")
    if case_id == "A2":
        if not isinstance(comparison, Mapping):
            raise Task41ContractError("Task41 A2 contract omits its immutable A1 comparison binding")
        binding_path = _resolve(root, comparison.get("a1_binding_path"), "comparison.a1_binding_path")
        if binding_path != (root / TASK41_A1_COMPARISON_BINDING_RELATIVE).resolve():
            raise Task41ContractError("Task41 A2 contract uses an unregistered A1 comparison binding path")
        binding, binding_digest = require_task41_a1_comparison_binding(
            binding_path,
            expected_sha256=comparison.get("a1_binding_sha256"),
            current_root=root,
        )
        if binding["a1"]["physical_model_sha256"] != case["physical_model_sha256"]:
            raise Task41ContractError("A1 and A2 comparison binding have different physical models")
        if comparison.get("same_discrete_comparison_ready") is not binding["a1"][
            "discrete_identity"
        ].get("same_discrete_comparison_ready"):
            raise Task41ContractError("Task41 A2 comparison readiness differs from the bound A1 evidence")
        if comparison.get("a1_binding_sha256") != binding_digest:
            raise Task41ContractError("Task41 A2 comparison binding hash changed")
    elif comparison is not None:
        raise Task41ContractError("A1 contract must not carry an A1/A2 comparison binding")
    q_csr_reuse = contract.get("q_csr_reuse")
    if q_csr_reuse is not None:
        if case_id != "A2":
            raise Task41ContractError("only Task41 A2 may bind saved q CSR reuse")
        _validate_task41_a2_q_csr_reuse(
            root,
            q_csr_reuse,
            source_sha=str(source["sha"]),
            window_sha256=str(window.get("sha256", "")),
            expected_input_sha256=str(case.get("input_sha256", "")),
        )
    if case_id == "B0":
        if q_csr_reuse is not None:
            raise Task41ContractError("Task41 B0 cannot mix a saved surface donor with q CSR reuse")
    return contract, digest


def task41_window_spec(contract: Mapping[str, Any], root: Path) -> tuple[Path, float, float, bool]:
    case = _task41_case(task41_case_id_for_run_id(str(contract.get("case", {}).get("run_id", ""))))
    window_info = contract.get("window", {})
    path = _resolve(root, window_info.get("path"), "window.path")
    if case["case_id"] == "B0" and path == (root / TASK41_B0_V3_WINDOW_RELATIVE).resolve():
        return path, TASK41_B0_V3_TOTAL_SECONDS, TASK41_B0_V3_NUMERICAL_SECONDS, True
    if case["case_id"] == "B0" and path == (root / TASK41_B0_V6_WINDOW_RELATIVE).resolve():
        authorization, authorization_sha = _task41_v6_authorization(root)
        parent_path = str(TASK41_B0_V3_WINDOW_RELATIVE)
        parent_sha = TASK41_B0_V3_WINDOW_SHA256
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise Task41ContractError("Task41 V6 fixed window is missing or invalid") from exc
        if (
            not isinstance(payload, Mapping)
            or payload.get("continuation_authorization_sha256") != authorization_sha
            or payload.get("parent_window_path") != parent_path
            or payload.get("parent_window_sha256") != parent_sha
            or window_info.get("continuation_authorization_sha256") != authorization_sha
            or window_info.get("parent_window_path") != parent_path
            or window_info.get("parent_window_sha256") != parent_sha
            or payload.get("source_sha") != authorization["source_at_entry"]
            or window_info.get("entry_source_sha") != authorization["source_at_entry"]
        ):
            raise Task41ContractError("Task41 V6 contract is not bound to its approved V3 parent and authorization")
        return path, TASK41_B0_V6_TOTAL_SECONDS, TASK41_B0_V6_NUMERICAL_SECONDS, True
    if case["case_id"] == "B0" and path == (root / TASK41_B0_V9_WINDOW_RELATIVE).resolve():
        authorization, authorization_sha = _task41_v9_authorization(root)
        parent_path = str(TASK41_B0_V6_WINDOW_RELATIVE)
        parent_sha = TASK41_B0_V6_WINDOW_SHA256
        parent_cost_path = str(authorization["parent_cost_ledger_path"])
        parent_cost_sha = str(authorization["parent_cost_ledger_sha256"])
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise Task41ContractError("Task41 V9 fixed window is missing or invalid") from exc
        expected_identity = {
            "continuation_authorization_sha256": authorization_sha,
            "parent_window_path": parent_path,
            "parent_window_sha256": parent_sha,
            "parent_cost_ledger_path": parent_cost_path,
            "parent_cost_ledger_sha256": parent_cost_sha,
        }
        if (
            not isinstance(payload, Mapping)
            or any(payload.get(key) != value for key, value in expected_identity.items())
            or any(window_info.get(key) != value for key, value in expected_identity.items())
            or _resolve(root, payload.get("accounting_path"), "V9 accounting path")
            != (root / TASK41_B0_CONTROLLER_RELATIVE / "campaign_accounting_v9_24h.jsonl").resolve()
            or payload.get("source_sha") != authorization["source_at_entry"]
            or window_info.get("entry_source_sha") != authorization["source_at_entry"]
        ):
            raise Task41ContractError(
                "Task41 V9 contract is not bound to its approved source, V6 parent, and cost ledger"
            )
        return path, TASK41_B0_V9_TOTAL_SECONDS, TASK41_B0_V9_NUMERICAL_SECONDS, True
    saved_diagnostics_config = (
        _task41_saved_diagnostics_instance_for_path(root, path)
        if case["case_id"] == "B0"
        else None
    )
    if saved_diagnostics_config is not None:
        authorization, authorization_sha = _task41_saved_diagnostics_authorization(
            root, instance=saved_diagnostics_config["instance"]
        )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise Task41ContractError("saved-diagnostics fixed window is missing or invalid") from exc
        expected_scope = saved_diagnostics_config["scope"]
        if (
            not isinstance(payload, Mapping)
            or payload.get("authorization_sha256") != authorization_sha
            or payload.get("scope") != expected_scope
            or payload.get("source_sha") != authorization["source_at_entry"]
            or window_info.get("authorization_sha256") != authorization_sha
            or window_info.get("scope") != expected_scope
            or window_info.get("entry_source_sha") != authorization["source_at_entry"]
            or payload.get("total_seconds") != saved_diagnostics_config["total_seconds"]
            or payload.get("numerical_seconds") != saved_diagnostics_config["numerical_seconds"]
            or payload.get("closeout_seconds") != TASK41_CLOSEOUT_SECONDS
            or payload.get("prior_window_path") != authorization["prior_window_path"]
            or payload.get("prior_window_sha256") != authorization["prior_window_sha256"]
            or payload.get("prior_ledger_path") != authorization["prior_ledger_path"]
            or payload.get("prior_ledger_sha256") != authorization["prior_ledger_sha256"]
            or window_info.get("prior_window_path") != authorization["prior_window_path"]
            or window_info.get("prior_window_sha256") != authorization["prior_window_sha256"]
            or window_info.get("prior_ledger_path") != authorization["prior_ledger_path"]
            or window_info.get("prior_ledger_sha256") != authorization["prior_ledger_sha256"]
            or payload.get("t0_basis") != {"kind": saved_diagnostics_config["t0_basis"]}
            or _resolve(root, payload.get("accounting_path"), "saved-diagnostics accounting path")
            != (root / saved_diagnostics_config["accounting_relative"]).resolve()
        ):
            raise Task41ContractError(
                "saved-diagnostics window is not bound to its explicit authorization and scope"
            )
        return (
            path,
            saved_diagnostics_config["total_seconds"],
            saved_diagnostics_config["numerical_seconds"],
            True,
        )
    if path != (root / case["window_relative"]).resolve():
        raise Task41ContractError("Task41 fixed window path is not registered")
    return path, TASK41_TOTAL_SECONDS, TASK41_NUMERICAL_SECONDS, False


def _task41_v3_authorization(root: Path) -> tuple[dict[str, Any], str]:
    path = root / TASK41_B0_V3_AUTH_RELATIVE
    raw = path.read_bytes()
    payload = json.loads(raw)
    parent = root / TASK41_B0_WINDOW_RELATIVE
    if (
        payload.get("schema") != "task41.b0.v3.user_continuation_authorization.v1"
        or payload.get("authorization") != "user_explicit_24h_20261019"
        or payload.get("total_seconds") != TASK41_B0_V3_TOTAL_SECONDS
        or payload.get("numerical_seconds") != TASK41_B0_V3_NUMERICAL_SECONDS
        or payload.get("closeout_seconds") != TASK41_CLOSEOUT_SECONDS
        or payload.get("pre_anchor_preparation_charge_seconds") != 180
        or payload.get("old_service_inactive_and_descendants_absent") is not True
        or payload.get("parent_window_path") != str(TASK41_B0_WINDOW_RELATIVE)
        or payload.get("parent_window_sha256") != TASK41_B0_PARENT_WINDOW_SHA256
        or sha256_file(parent) != TASK41_B0_PARENT_WINDOW_SHA256
        or not re.fullmatch(r"[0-9a-f]{40}", str(payload.get("source_at_entry", "")))
        or not isinstance(payload.get("anchor"), dict)
        or set(payload["anchor"]) != {"monotonic", "boottime", "utc_ns", "boot_id"}
    ):
        raise Task41ContractError("Task41 V3 continuation authorization or preserved parent changed")
    return payload, hashlib.sha256(raw).hexdigest()


def _task41_v6_authorization(root: Path) -> tuple[dict[str, Any], str]:
    path = root / TASK41_B0_V6_AUTH_RELATIVE
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise Task41ContractError("Task41 V6 continuation requires an explicit authorization receipt") from exc
    common_fields = {
        "schema", "authorization", "source_at_entry", "parent_window_path",
        "parent_window_sha256", "total_seconds", "numerical_seconds",
        "closeout_seconds",
    }
    if not isinstance(payload, dict):
        raise Task41ContractError("Task41 V6 authorization or preserved V3 parent identity changed")
    schema = payload.get("schema")
    if schema == TASK41_B0_V6_AUTH_LEGACY_SCHEMA:
        expected_fields = common_fields
    elif schema == TASK41_B0_V6_AUTH_SCHEMA:
        expected_fields = common_fields | {"preparation_started_utc"}
    else:
        raise Task41ContractError("Task41 V6 authorization schema is not supported")
    if set(payload) != expected_fields:
        raise Task41ContractError("Task41 V6 authorization fields are incomplete or unexpected")
    if schema == TASK41_B0_V6_AUTH_SCHEMA:
        preparation_started_utc = payload.get("preparation_started_utc")
        try:
            preparation_started_ns = _utc_ns(preparation_started_utc)
        except (TypeError, ValueError) as exc:
            raise Task41ContractError(
                "Task41 V6 preparation start must be a canonical UTC timestamp"
            ) from exc
        if preparation_started_utc != _utc_text_from_ns(preparation_started_ns):
            raise Task41ContractError(
                "Task41 V6 preparation start must be a canonical UTC timestamp"
            )
    parent_path = root / TASK41_B0_V3_WINDOW_RELATIVE
    if (
        payload.get("authorization") != TASK41_B0_V6_AUTHORIZATION
        or payload.get("total_seconds") != TASK41_B0_V6_TOTAL_SECONDS
        or payload.get("numerical_seconds") != TASK41_B0_V6_NUMERICAL_SECONDS
        or payload.get("closeout_seconds") != TASK41_CLOSEOUT_SECONDS
        or payload.get("parent_window_path") != str(TASK41_B0_V3_WINDOW_RELATIVE)
        or payload.get("parent_window_sha256") != TASK41_B0_V3_WINDOW_SHA256
        or not re.fullmatch(r"[0-9a-f]{40}", str(payload.get("source_at_entry", "")))
        or not parent_path.is_file()
        or sha256_file(parent_path) != TASK41_B0_V3_WINDOW_SHA256
    ):
        raise Task41ContractError("Task41 V6 authorization or preserved V3 parent identity changed")
    return payload, hashlib.sha256(raw).hexdigest()


def _task41_v9_authorization(root: Path) -> tuple[dict[str, Any], str]:
    """Require a new explicit V9 window approval bound to all V6 costs."""

    path = root / TASK41_B0_V9_AUTH_RELATIVE
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise Task41ContractError(
            "Task41 V9 continuation requires a new explicit user authorization receipt"
        ) from exc
    expected_fields = {
        "schema",
        "authorization",
        "source_at_entry",
        "parent_window_path",
        "parent_window_sha256",
        "parent_cost_ledger_path",
        "parent_cost_ledger_sha256",
        "total_seconds",
        "numerical_seconds",
        "closeout_seconds",
        "preparation_started_utc",
    }
    if not isinstance(payload, dict) or set(payload) != expected_fields:
        raise Task41ContractError("Task41 V9 authorization fields are incomplete or unexpected")
    try:
        preparation_started_ns = _utc_ns(payload.get("preparation_started_utc"))
    except (TypeError, ValueError) as exc:
        raise Task41ContractError(
            "Task41 V9 preparation start must be a canonical UTC timestamp"
        ) from exc
    if payload.get("preparation_started_utc") != _utc_text_from_ns(preparation_started_ns):
        raise Task41ContractError(
            "Task41 V9 preparation start must be a canonical UTC timestamp"
        )

    parent_window_path = root / TASK41_B0_V6_WINDOW_RELATIVE
    try:
        parent_window_raw = parent_window_path.read_bytes()
        parent_window = json.loads(parent_window_raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise Task41ContractError("Task41 V9 requires the preserved V6 parent window") from exc
    if hashlib.sha256(parent_window_raw).hexdigest() != TASK41_B0_V6_WINDOW_SHA256:
        raise Task41ContractError("Task41 V9 preserved V6 parent window hash changed")
    if not isinstance(parent_window, Mapping):
        raise Task41ContractError("Task41 V9 preserved V6 parent window is malformed")
    expected_cost_path = _resolve(root, parent_window.get("accounting_path"), "V6 accounting path")
    controller_root = (root / TASK41_B0_CONTROLLER_RELATIVE).resolve()
    expected_cost_relative = (
        TASK41_B0_V6_WINDOW_RELATIVE.parent / "campaign_accounting_v6_24h.jsonl"
    )
    if (
        expected_cost_path != (root / expected_cost_relative).resolve()
        or not expected_cost_path.is_relative_to(controller_root)
    ):
        raise Task41ContractError("Task41 V6 cost ledger escaped its controller artifact directory")
    try:
        expected_cost_sha = _task41_v9_parent_ledger_sha256(expected_cost_path)
    except OSError as exc:
        raise Task41ContractError("Task41 V9 requires the complete V6 cost ledger") from exc
    if (
        payload.get("schema") != TASK41_B0_V9_AUTH_SCHEMA
        or payload.get("authorization") != TASK41_B0_V9_AUTHORIZATION
        or not re.fullmatch(r"[0-9a-f]{40}", str(payload.get("source_at_entry", "")))
        or payload.get("parent_window_path") != str(TASK41_B0_V6_WINDOW_RELATIVE)
        or payload.get("parent_window_sha256") != TASK41_B0_V6_WINDOW_SHA256
        or payload.get("parent_cost_ledger_path") != str(expected_cost_relative)
        or payload.get("parent_cost_ledger_sha256") != expected_cost_sha
        or payload.get("total_seconds") != TASK41_B0_V9_TOTAL_SECONDS
        or payload.get("numerical_seconds") != TASK41_B0_V9_NUMERICAL_SECONDS
        or payload.get("closeout_seconds") != TASK41_CLOSEOUT_SECONDS
    ):
        raise Task41ContractError(
            "Task41 V9 authorization or preserved V6 window/cost identity changed"
        )
    normalized = dict(payload)
    normalized["parent_cost_ledger_path"] = str(expected_cost_relative)
    return normalized, hashlib.sha256(raw).hexdigest()


def _task41_saved_diagnostics_authorization(
    root: Path, *, instance: str | None = None
) -> tuple[dict[str, Any], str]:
    """Validate one explicit saved-diagnostics authorization instance."""
    config = _task41_saved_diagnostics_instance(instance)
    path = root / config["authorization_relative"]
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise Task41ContractError(
            "saved-diagnostics window requires its explicit authorization record"
        ) from exc
    expected_fields = {
        "schema", "authorization", "source_at_entry", "preparation_started_utc",
        "total_seconds", "numerical_seconds", "closeout_seconds", "scope",
        "prior_window_path", "prior_window_sha256", "prior_ledger_path",
        "prior_ledger_sha256",
    }
    prior_window_path = root / config["prior_window_relative"]
    prior_ledger_path = root / config["prior_ledger_relative"]
    try:
        prior_window_raw = prior_window_path.read_bytes()
        prior_window = json.loads(prior_window_raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise Task41ContractError("saved-diagnostics authorization requires its frozen parent window") from exc
    prior_window_sha = hashlib.sha256(prior_window_raw).hexdigest()
    prior_ledger_sha = sha256_file(prior_ledger_path) if prior_ledger_path.is_file() else None
    if (
        not isinstance(payload, dict)
        or set(payload) != expected_fields
        or payload.get("schema") != TASK41_B0_SAVED_DIAGNOSTICS_AUTH_SCHEMA
        or payload.get("authorization") != config["authorization"]
        or not re.fullmatch(r"[0-9a-f]{40}", str(payload.get("source_at_entry", "")))
        or payload.get("total_seconds") != config["total_seconds"]
        or payload.get("numerical_seconds") != config["numerical_seconds"]
        or payload.get("closeout_seconds") != TASK41_CLOSEOUT_SECONDS
        or payload.get("scope") != config["scope"]
        or not isinstance(prior_window, Mapping)
        or payload.get("prior_window_path") != str(config["prior_window_relative"])
        or payload.get("prior_window_sha256") != prior_window_sha
        or payload.get("prior_ledger_path")
        != str(config["prior_ledger_relative"])
        or payload.get("prior_ledger_sha256") != prior_ledger_sha
        or _resolve(root, prior_window.get("accounting_path"), "prior V9 accounting path")
        != prior_ledger_path.resolve()
    ):
        raise Task41ContractError("saved-diagnostics authorization identity, time, or scope changed")
    try:
        preparation_started_ns = _utc_ns(payload.get("preparation_started_utc"))
    except (TypeError, ValueError) as exc:
        raise Task41ContractError(
            "saved-diagnostics preparation start must be a canonical UTC timestamp"
        ) from exc
    if payload.get("preparation_started_utc") != _utc_text_from_ns(preparation_started_ns):
        raise Task41ContractError(
            "saved-diagnostics preparation start must be a canonical UTC timestamp"
        )
    return payload, hashlib.sha256(raw).hexdigest()


def load_task41_p0_fixed_window(
    contract: Mapping[str, Any], *, current_root: str | Path | None = None,
    require_current_boot: bool = True,
) -> FixedCampaignWindow:
    root = Path(current_root or Path(__file__).resolve().parents[2]).resolve()
    case_spec = _task41_case(
        task41_case_id_for_run_id(str(contract.get("case", {}).get("run_id", "")))
    )
    window_info = contract["window"]
    path, total_seconds, numerical_seconds, continuation = task41_window_spec(contract, root)
    is_v3_continuation = case_spec["case_id"] == "B0" and path == (root / TASK41_B0_V3_WINDOW_RELATIVE).resolve()
    is_v6_continuation = case_spec["case_id"] == "B0" and path == (root / TASK41_B0_V6_WINDOW_RELATIVE).resolve()
    is_v9_continuation = case_spec["case_id"] == "B0" and path == (root / TASK41_B0_V9_WINDOW_RELATIVE).resolve()
    saved_diagnostics_config = (
        _task41_saved_diagnostics_instance_for_path(root, path)
        if case_spec["case_id"] == "B0"
        else None
    )
    is_saved_diagnostics_continuation = saved_diagnostics_config is not None
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != window_info["sha256"]:
        raise Task41ContractError("Task41 fixed execution window hash changed")
    payload = json.loads(raw)
    expected_fields = {
        "schema", "task_id", "source_sha", "t0_utc", "numerical_deadline_utc",
        "deadline_utc", "total_seconds", "numerical_seconds", "closeout_seconds",
        "anchor", "accounting_path",
    }
    is_b0 = case_spec["case_id"] == "B0"
    if is_b0:
        expected_fields |= {
            "t0_basis",
            "bootstrap_utc_elapsed_seconds",
            "bootstrap_boottime_elapsed_seconds",
            "bootstrap_time_treatment",
        }
    if is_v3_continuation:
        expected_fields |= {"continuation_authorization_sha256", "parent_window_sha256"}
    if is_v6_continuation:
        expected_fields |= {
            "continuation_authorization_sha256", "parent_window_path", "parent_window_sha256"
        }
    if is_v9_continuation:
        expected_fields |= {
            "continuation_authorization_sha256",
            "parent_window_path",
            "parent_window_sha256",
            "parent_cost_ledger_path",
            "parent_cost_ledger_sha256",
        }
    if is_saved_diagnostics_continuation:
        expected_fields |= {
            "authorization_sha256", "scope", "prior_window_path",
            "prior_window_sha256", "prior_ledger_path", "prior_ledger_sha256",
        }
    if not isinstance(payload, dict) or set(payload) != expected_fields:
        raise Task41ContractError("Task41 fixed execution window has an open or incomplete schema")
    if (
        payload.get("schema") != TASK41_P0_WINDOW_SCHEMA
        or payload.get("task_id") != TASK41_MODEL_ID
        or payload.get("source_sha") != window_info.get("entry_source_sha")
        or not re.fullmatch(r"[0-9a-f]{40}", str(window_info.get("entry_source_sha", "")))
        or payload.get("total_seconds") != total_seconds
        or payload.get("numerical_seconds") != numerical_seconds
        or payload.get("closeout_seconds") != TASK41_CLOSEOUT_SECONDS
    ):
        raise Task41ContractError("Task41 execution window identity or time limits changed")
    anchor = payload.get("anchor")
    if not isinstance(anchor, dict) or set(anchor) != {
        "monotonic", "boottime", "utc_ns", "boot_id"
    }:
        raise Task41ContractError("Task41 execution window clock anchor is incomplete")
    try:
        t0_ns = _utc_ns(payload["t0_utc"])
        numerical_deadline_ns = _utc_ns(payload["numerical_deadline_utc"])
        deadline_ns = _utc_ns(payload["deadline_utc"])
    except ValueError as exc:
        raise Task41ContractError(f"Task41 execution window UTC value is invalid: {exc}") from exc
    if (
        (anchor["utc_ns"] < t0_ns if is_b0 else anchor["utc_ns"] != t0_ns)
        or numerical_deadline_ns != t0_ns + int(numerical_seconds * 1e9)
        or deadline_ns != t0_ns + int(total_seconds * 1e9)
        or not isinstance(anchor["boot_id"], str)
        or not anchor["boot_id"]
    ):
        raise Task41ContractError("Task41 execution window timestamps are inconsistent")
    bootstrap_seconds = 0.0
    if is_v3_continuation:
        authorization, authorization_sha = _task41_v3_authorization(root)
        expected_t0_ns = int(authorization["anchor"]["utc_ns"]) - 180_000_000_000
        if (
            t0_ns != expected_t0_ns
            or anchor != authorization["anchor"]
            or payload["source_sha"] != authorization["source_at_entry"]
            or payload["continuation_authorization_sha256"] != authorization_sha
            or payload["parent_window_sha256"] != TASK41_B0_PARENT_WINDOW_SHA256
            or payload.get("t0_basis") != {"kind": "user_approved_v3_24h_continuation"}
            or payload.get("bootstrap_utc_elapsed_seconds") != 180
            or payload.get("bootstrap_boottime_elapsed_seconds") is not None
            or payload.get("bootstrap_time_treatment") != "conservative_pre_anchor_preparation_charge_not_measured"
        ):
            raise Task41ContractError("Task41 V3 continuation clock or authorization changed")
        bootstrap_seconds = 180.0
    elif is_v6_continuation:
        authorization, authorization_sha = _task41_v6_authorization(root)
        preparation_started_utc = authorization.get("preparation_started_utc")
        if preparation_started_utc is None:
            expected_t0_ns = int(anchor["utc_ns"])
            expected_bootstrap_seconds = 0.0
            expected_t0_basis = {"kind": "user_approved_v6_24h_continuation"}
            expected_bootstrap_treatment = "new_approved_window_anchor_is_t0"
        else:
            expected_t0_ns = _utc_ns(preparation_started_utc)
            expected_bootstrap_seconds = (
                int(anchor["utc_ns"]) - expected_t0_ns
            ) / 1e9
            expected_t0_basis = {"kind": TASK41_B0_V6_PREPARATION_T0_KIND}
            expected_bootstrap_treatment = TASK41_B0_V6_PREPARATION_BOOTSTRAP_TREATMENT
        recorded_bootstrap = payload.get("bootstrap_utc_elapsed_seconds")
        if (
            t0_ns != expected_t0_ns
            or expected_bootstrap_seconds < 0
            or payload["source_sha"] != authorization["source_at_entry"]
            or payload["continuation_authorization_sha256"] != authorization_sha
            or payload.get("parent_window_path") != str(TASK41_B0_V3_WINDOW_RELATIVE)
            or payload.get("parent_window_sha256") != TASK41_B0_V3_WINDOW_SHA256
            or payload.get("t0_basis") != expected_t0_basis
            or not isinstance(recorded_bootstrap, (int, float))
            or isinstance(recorded_bootstrap, bool)
            or abs(float(recorded_bootstrap) - expected_bootstrap_seconds) > 1e-6
            or payload.get("bootstrap_boottime_elapsed_seconds") is not None
            or payload.get("bootstrap_time_treatment") != expected_bootstrap_treatment
        ):
            raise Task41ContractError("Task41 V6 window clock, approval, or V3 parent changed")
        bootstrap_seconds = expected_bootstrap_seconds
    elif is_v9_continuation:
        authorization, authorization_sha = _task41_v9_authorization(root)
        expected_t0_ns = _utc_ns(authorization["preparation_started_utc"])
        expected_bootstrap_seconds = (int(anchor["utc_ns"]) - expected_t0_ns) / 1e9
        if (
            expected_bootstrap_seconds < 0
            or t0_ns != expected_t0_ns
            or payload["source_sha"] != authorization["source_at_entry"]
            or payload.get("continuation_authorization_sha256") != authorization_sha
            or payload.get("parent_window_path") != str(TASK41_B0_V6_WINDOW_RELATIVE)
            or payload.get("parent_window_sha256") != TASK41_B0_V6_WINDOW_SHA256
            or payload.get("parent_cost_ledger_path")
            != authorization["parent_cost_ledger_path"]
            or payload.get("parent_cost_ledger_sha256")
            != authorization["parent_cost_ledger_sha256"]
            or payload.get("t0_basis")
            != {"kind": TASK41_B0_V9_PREPARATION_T0_KIND}
            or not isinstance(payload.get("bootstrap_utc_elapsed_seconds"), (int, float))
            or isinstance(payload.get("bootstrap_utc_elapsed_seconds"), bool)
            or abs(
                float(payload["bootstrap_utc_elapsed_seconds"])
                - expected_bootstrap_seconds
            ) > 1e-6
            or payload.get("bootstrap_boottime_elapsed_seconds") is not None
            or payload.get("bootstrap_time_treatment")
            != TASK41_B0_V9_PREPARATION_BOOTSTRAP_TREATMENT
            or _resolve(root, payload.get("accounting_path"), "V9 accounting path")
            != (root / TASK41_B0_CONTROLLER_RELATIVE / "campaign_accounting_v9_24h.jsonl").resolve()
        ):
            raise Task41ContractError(
                "Task41 V9 window clock, approval, parent costs, or new ledger changed"
            )
        bootstrap_seconds = expected_bootstrap_seconds
        bootstrap_seconds = expected_bootstrap_seconds
    elif is_saved_diagnostics_continuation:
        assert saved_diagnostics_config is not None
        authorization, authorization_sha = _task41_saved_diagnostics_authorization(
            root, instance=saved_diagnostics_config["instance"]
        )
        expected_t0_ns = _utc_ns(authorization["preparation_started_utc"])
        expected_bootstrap_seconds = (int(anchor["utc_ns"]) - expected_t0_ns) / 1e9
        recorded_bootstrap = payload.get("bootstrap_utc_elapsed_seconds")
        if (
            expected_bootstrap_seconds < 0
            or t0_ns != expected_t0_ns
            or payload.get("source_sha") != authorization["source_at_entry"]
            or payload.get("authorization_sha256") != authorization_sha
            or window_info.get("authorization_sha256") != authorization_sha
            or payload.get("scope") != saved_diagnostics_config["scope"]
            or window_info.get("scope") != saved_diagnostics_config["scope"]
            or payload.get("prior_window_path") != authorization["prior_window_path"]
            or payload.get("prior_window_sha256") != authorization["prior_window_sha256"]
            or payload.get("prior_ledger_path") != authorization["prior_ledger_path"]
            or payload.get("prior_ledger_sha256") != authorization["prior_ledger_sha256"]
            or window_info.get("prior_window_path") != authorization["prior_window_path"]
            or window_info.get("prior_window_sha256") != authorization["prior_window_sha256"]
            or window_info.get("prior_ledger_path") != authorization["prior_ledger_path"]
            or window_info.get("prior_ledger_sha256") != authorization["prior_ledger_sha256"]
            or payload.get("t0_basis") != {"kind": saved_diagnostics_config["t0_basis"]}
            or not isinstance(recorded_bootstrap, (int, float))
            or isinstance(recorded_bootstrap, bool)
            or abs(float(recorded_bootstrap) - expected_bootstrap_seconds) > 1e-6
            or payload.get("bootstrap_boottime_elapsed_seconds") is not None
            or payload.get("bootstrap_time_treatment")
            != "preparation_start_to_anchor_utc_elapsed_charged; pre_anchor_monotonic_and_boottime_unknown"
            or _resolve(root, payload.get("accounting_path"), "saved-diagnostics accounting path")
            != (root / saved_diagnostics_config["accounting_relative"]).resolve()
        ):
            raise Task41ContractError(
                "saved-diagnostics window clock, approval, scope, or accounting path changed"
            )
        bootstrap_seconds = expected_bootstrap_seconds
    elif is_b0:
        expected_t0_ns = _utc_ns(TASK41_B0_T0_UTC)
        bootstrap_utc = (int(anchor["utc_ns"]) - expected_t0_ns) / 1e9
        if (
            # The writer formats nanoseconds as ``...44.000000000Z`` while
            # the fixed basis constant is ``...44Z``. Compare parsed instants,
            # not their equivalent text spellings.
            t0_ns != expected_t0_ns
            or payload.get("t0_basis") != TASK41_B0_T0_BASIS
            or payload.get("bootstrap_boottime_elapsed_seconds") is not None
            or not isinstance(payload.get("bootstrap_utc_elapsed_seconds"), (int, float))
            or isinstance(payload.get("bootstrap_utc_elapsed_seconds"), bool)
            or abs(float(payload["bootstrap_utc_elapsed_seconds"]) - bootstrap_utc) > 1e-6
            or payload.get("bootstrap_time_treatment") != TASK41_B0_BOOTSTRAP_TREATMENT
        ):
            raise Task41ContractError("Task41 B0 fixed T0 basis or UTC bootstrap debit changed")
        bootstrap_seconds = bootstrap_utc
    if require_current_boot:
        current = clock_sample(include_boot_id=True)
        if current["boot_id"] != anchor["boot_id"]:
            raise Task41ContractError("Task41 execution window belongs to another boot")
        if current["utc_ns"] >= deadline_ns:
            raise Task41ContractError("Task41 fixed execution window has expired")
    accounting_path = _resolve(root, payload["accounting_path"], "accounting_path")
    if not accounting_path.is_relative_to(root / "benchmarks/artifacts/task41extra_phi90_p50x50_g17x20"):
        raise Task41ContractError("Task41 accounting ledger escaped its artifact directory")
    return FixedCampaignWindow(
        path=path,
        sha256=digest,
        payload=payload,
        anchor=anchor,
        t0_utc_ns=t0_ns,
        deadline_utc_ns=deadline_ns,
        total_seconds=total_seconds,
        bootstrap_seconds=bootstrap_seconds,
        closeout_seconds=TASK41_CLOSEOUT_SECONDS,
    )


def _task41_window_for_contract(
    root: Path, case_id: str = "A1", *, b0_v3_continuation: bool = False,
    b0_v6_continuation: bool = False, b0_v9_continuation: bool = False,
    b0_saved_diagnostics_6h: bool = False,
    b0_saved_diagnostics_instance: str | None = None,
) -> tuple[FixedCampaignWindow, str, dict[str, Any]]:
    case_spec = _task41_case(case_id)
    saved_instance = (
        b0_saved_diagnostics_instance
        if b0_saved_diagnostics_instance is not None
        else None
    )
    saved_enabled = b0_saved_diagnostics_6h or saved_instance is not None
    if sum((b0_v3_continuation, b0_v6_continuation, b0_v9_continuation,
            saved_enabled)) > 1:
        raise Task41ContractError("Task41 B0 continuation window routes are mutually exclusive")
    saved_config = _task41_saved_diagnostics_instance(saved_instance) if saved_enabled else None
    relative = (
        saved_config["window_relative"] if saved_config is not None
        else TASK41_B0_V9_WINDOW_RELATIVE if b0_v9_continuation
        else TASK41_B0_V6_WINDOW_RELATIVE if b0_v6_continuation
        else TASK41_B0_V3_WINDOW_RELATIVE if b0_v3_continuation
        else case_spec["window_relative"]
    )
    path = (root / relative).resolve()
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise Task41ContractError("Task41 fixed execution window is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise Task41ContractError("Task41 fixed execution window must be a JSON object")
    entry_source = payload.get("source_sha")
    continuation_identity: dict[str, Any] = {}
    if b0_v6_continuation:
        continuation_identity = {
            "continuation_authorization_sha256": payload.get("continuation_authorization_sha256"),
            "parent_window_path": payload.get("parent_window_path"),
            "parent_window_sha256": payload.get("parent_window_sha256"),
        }
    elif b0_v9_continuation:
        continuation_identity = {
            "continuation_authorization_sha256": payload.get("continuation_authorization_sha256"),
            "parent_window_path": payload.get("parent_window_path"),
            "parent_window_sha256": payload.get("parent_window_sha256"),
            "parent_cost_ledger_path": payload.get("parent_cost_ledger_path"),
            "parent_cost_ledger_sha256": payload.get("parent_cost_ledger_sha256"),
        }
    elif saved_config is not None:
        authorization, authorization_sha = _task41_saved_diagnostics_authorization(
            root, instance=saved_config["instance"]
        )
        continuation_identity = {
            "authorization_sha256": authorization_sha,
            "scope": saved_config["scope"],
            "prior_window_path": authorization["prior_window_path"],
            "prior_window_sha256": authorization["prior_window_sha256"],
            "prior_ledger_path": authorization["prior_ledger_path"],
            "prior_ledger_sha256": authorization["prior_ledger_sha256"],
        }
    window_contract = {
        "case": {"run_id": case_spec["run_id"]},
        "source": {"sha": entry_source},
        "window": {
            "path": str(relative),
            "sha256": digest,
            "entry_source_sha": entry_source,
            **continuation_identity,
        },
    }
    window = load_task41_p0_fixed_window(
        window_contract, current_root=root, require_current_boot=True
    )
    return window, digest, payload


def _check_task41_native_receipt(
    abi_receipt_path: Path, runtime_prefix: Path
) -> str:
    try:
        receipt = json.loads(abi_receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Task41ContractError(f"Task41 ABI receipt cannot be read: {exc}") from exc
    petsc = receipt.get("PETSc") if isinstance(receipt, dict) else None
    mpi = receipt.get("MPI") if isinstance(receipt, dict) else None
    if (
        not isinstance(receipt, dict)
        or receipt.get("status") != "IMPORT_SCALAR_MPI_API_PASS_NO_FE_ACTION"
        or receipt.get("runtime_profile") != "native_linux"
        or Path(str(receipt.get("prefix", ""))).resolve() != runtime_prefix.resolve()
        or not isinstance(petsc, dict)
        or petsc.get("scalar_dtype") != "complex128"
        or petsc.get("int_dtype") != "int32"
        or not isinstance(mpi, dict)
        or mpi.get("size") != 1
        or mpi.get("rank") != 0
    ):
        raise Task41ContractError(
            "Task41 ABI receipt must bind native_linux, complex128/int32, and MPI1"
        )
    return hashlib.sha256(abi_receipt_path.read_bytes()).hexdigest()


def task41_raw_artifact_limit_bytes(contract: Mapping[str, Any]) -> int:
    """Keep old contracts at 8 GiB; only the approved B0 evidence override is 16 GiB."""
    policy = contract.get("evidence", {}).get("raw_disk_policy")
    if policy is None:
        return 8 << 30
    expected = {
        "scope": "task41_b0_v3_recovery_evidence",
        "raw_artifact_limit_bytes": 16 << 30,
        "free_space_floor_bytes": 2 << 30,
        "authorization": "user_20261019_16gib_evidence_only",
    }
    execution_scope = contract.get("execution_scope")
    if execution_scope == TASK41_B0_V16_SAVED_VECTOR_SCOPE:
        expected["new_evidence_limit_bytes"] = TASK41_B0_V16_SAVED_VECTOR_NEW_EVIDENCE_BYTES
    elif execution_scope == TASK41_B0_V17_SELECTED_TWO_CELL_SCOPE:
        expected["new_evidence_limit_bytes"] = (
            TASK41_B0_V17_SELECTED_TWO_CELL_NEW_EVIDENCE_BYTES
        )
    elif execution_scope == TASK41_B0_V18_SAVED_JZ_SCOPE:
        expected["new_evidence_limit_bytes"] = TASK41_B0_V18_SAVED_JZ_NEW_EVIDENCE_BYTES
    elif execution_scope in (
        TASK41_B0_SAVED_DIAGNOSTICS_SCOPE,
        TASK41_B0_V12_CANDIDATE_REPLAY_SCOPE,
        TASK41_B0_V14_SAVED_RHS_CANDIDATE_SCOPE,
    ):
        expected["new_evidence_limit_bytes"] = TASK41_B0_SAVED_DIAGNOSTICS_NEW_EVIDENCE_LIMIT_BYTES
    elif execution_scope == TASK41_B0_V15_FULL_ACCEPTANCE_SCOPE:
        expected.update(
            {
                "new_evidence_limit_bytes": TASK41_B0_V15_FULL_ACCEPTANCE_NEW_RAW_BYTES,
                "single_package_limit_bytes": TASK41_B0_V15_FULL_ACCEPTANCE_SINGLE_ARTIFACT_BYTES,
                "non_raw_output_reserve_bytes": TASK41_B0_V15_FULL_ACCEPTANCE_NON_RAW_RESERVE_BYTES,
                "raw_artifact_accounting": TASK41_B0_V15_FULL_ACCEPTANCE_SCOPE[
                    "raw_artifact_accounting"
                ],
                "monitoring_log_accounting": TASK41_B0_V15_FULL_ACCEPTANCE_SCOPE[
                    "monitoring_log_accounting"
                ],
                "raw_artifact_roots": TASK41_B0_V15_POST_V7_RAW_EVIDENCE_ROOTS,
                "success_exit": TASK41_B0_V15_FULL_ACCEPTANCE_SCOPE["success_exit"],
            }
        )
    if contract.get("case", {}).get("run_id") != TASK41_B0_RUN_ID or policy != expected:
        raise Task41ContractError("Task41 raw evidence policy differs from the authorized B0 override")
    return 16 << 30


def verify_task41_v15_frozen_jit_cache(jit_cache: str | Path) -> dict[str, Any]:
    """Read-only preflight of the already-qualified V6 cache, before FE/claim.

    A matching form signature does not authorize a newly compiled binary.
    Keep the evaluator's original C/metadata/module checks unchanged.
    """
    from src.solvers.task41_actual_qmetric_blocked_gram import (
        EXPECTED_C_SOURCE_SHA256, EXPECTED_C_CACHE_SHA256,
        EXPECTED_UFCX_MODULE_SHA256,
    )
    cache = Path(jit_cache).resolve(strict=True)
    directory = cache / "fenics"
    stem = "libffcx_forms_2f92c03a20c09db3cb8f0382bec2294daa94ab16"
    modules = list(directory.glob(stem + ".*.so"))
    if len(modules) != 1:
        raise Task41ContractError("V15 JIT cache lacks the unique frozen V6 module; no compile fallback")
    records = []
    for role, path, expected in (
        ("c_source", directory / (stem + ".c"), EXPECTED_C_SOURCE_SHA256),
        ("compile_metadata", directory / (stem + ".c.cached"), EXPECTED_C_CACHE_SHA256),
        ("module", modules[0], EXPECTED_UFCX_MODULE_SHA256),
    ):
        if not path.is_file() or not path.resolve().is_relative_to(cache):
            raise Task41ContractError(f"V15 frozen JIT {role} is absent or outside selected cache")
        actual = sha256_file(path)
        if actual != expected:
            raise Task41ContractError(
                f"V15 frozen JIT {role} hash differs: {path}; expected={expected}; actual={actual}"
            )
        records.append({"role": role, "path": str(path.resolve()),
                        "bytes": path.stat().st_size, "sha256": actual})
    return {"schema": "task41.v15.frozen_jit_preflight.v1", "jit_cache": str(cache),
            "qualified_existing_files": records, "compile_attempted": False}


def prepare_task41_p0(
    *,
    runtime_prefix: str | Path,
    abi_receipt: str | Path,
    jit_cache: str | Path,
    current_root: str | Path | None = None,
    case_id: str = "A1",
    a2_q_csr_manifests: Sequence[str | Path] | None = None,
    b0_v3_continuation: bool = False,
    b0_v6_continuation: bool = False,
    b0_v9_continuation: bool = False,
    b0_saved_diagnostics_6h: bool = False,
    b0_saved_diagnostics_instance: str | None = None,
) -> dict[str, Any]:
    """Register or reuse the one fixed P0 window, then write a source-bound contract.

    On first use the T0 record is durably created before runtime and input validation.
    Later calls reuse its exact bytes, including when the current source has changed.
    """
    root = Path(current_root or Path(__file__).resolve().parents[2]).resolve()
    case_spec = _task41_case(case_id)
    source_sha = _git(root, "rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise Task41ContractError("Task41 current HEAD is not a full Git SHA")
    if _git(root, "branch", "--show-current") != TASK41_BRANCH:
        raise Task41ContractError("Task41 P0 prepare requires the registered execution branch")
    if _git(root, "status", "--porcelain", "--untracked-files=normal"):
        raise Task41ContractError("Task41 P0 prepare requires a clean frozen source tree")

    if b0_v3_continuation and case_id != "B0":
        raise Task41ContractError("V3 continuation applies only to the authorized B0 case")
    if b0_v6_continuation and case_id != "B0":
        raise Task41ContractError("V6 continuation applies only to the authorized B0 case")
    if b0_v9_continuation and case_id != "B0":
        raise Task41ContractError("V9 continuation applies only to the authorized B0 case")
    if b0_saved_diagnostics_6h and b0_saved_diagnostics_instance is not None:
        raise Task41ContractError("choose either the legacy saved-diagnostics route or one named instance")
    saved_diagnostics_instance = b0_saved_diagnostics_instance
    saved_diagnostics_enabled = (
        b0_saved_diagnostics_6h or saved_diagnostics_instance is not None
    )
    saved_diagnostics_config = (
        _task41_saved_diagnostics_instance(saved_diagnostics_instance)
        if saved_diagnostics_enabled
        else None
    )
    if saved_diagnostics_enabled and case_id != "B0":
        raise Task41ContractError("saved-diagnostics six-hour window applies only to B0")
    if sum((b0_v3_continuation, b0_v6_continuation, b0_v9_continuation,
            saved_diagnostics_enabled)) > 1:
        raise Task41ContractError("B0 continuation routes are mutually exclusive")
    window_relative = (
        saved_diagnostics_config["window_relative"] if saved_diagnostics_config is not None
        else TASK41_B0_V9_WINDOW_RELATIVE if b0_v9_continuation
        else TASK41_B0_V6_WINDOW_RELATIVE if b0_v6_continuation
        else TASK41_B0_V3_WINDOW_RELATIVE if b0_v3_continuation
        else case_spec["window_relative"]
    )
    window_path = (root / window_relative).resolve()
    v6_authorization = None
    v6_authorization_sha = None
    v9_authorization = None
    v9_authorization_sha = None
    if b0_v6_continuation:
        v6_authorization, v6_authorization_sha = _task41_v6_authorization(root)
        if not window_path.exists() and v6_authorization["source_at_entry"] != source_sha:
            raise Task41ContractError("Task41 V6 approval receipt does not bind the frozen source SHA")
    if b0_v9_continuation:
        v9_authorization, v9_authorization_sha = _task41_v9_authorization(root)
        if not window_path.exists() and v9_authorization["source_at_entry"] != source_sha:
            raise Task41ContractError("Task41 V9 approval receipt does not bind the frozen source SHA")
    saved_diagnostics_authorization = None
    saved_diagnostics_authorization_sha = None
    if saved_diagnostics_config is not None:
        saved_auth_path = root / saved_diagnostics_config["authorization_relative"]
        if not saved_auth_path.exists():
            if saved_diagnostics_config.get("requires_preexisting_user_authorization"):
                route_name = (
                    "V15 full-acceptance"
                    if saved_diagnostics_instance == TASK41_B0_V15_FULL_ACCEPTANCE_INSTANCE
                    else "V16 saved-vector diagnostics"
                    if saved_diagnostics_instance == TASK41_B0_V16_SAVED_VECTOR_INSTANCE
                    else "V17 selected two-cell replay"
                    if saved_diagnostics_instance == TASK41_B0_V17_SELECTED_TWO_CELL_INSTANCE
                    else "V18 saved Jz candidate"
                    if saved_diagnostics_instance == TASK41_B0_V18_SAVED_JZ_INSTANCE
                    else "V14 saved-candidate"
                )
                raise Task41ContractError(
                    f"{route_name} prepare requires an existing explicit user authorization; "
                    "no authorization, T0, window, or accounting file was created"
                )
            prior_window_path = root / saved_diagnostics_config["prior_window_relative"]
            try:
                prior_window_raw = prior_window_path.read_bytes()
                prior_window_payload = json.loads(prior_window_raw)
            except (OSError, json.JSONDecodeError) as exc:
                raise Task41ContractError(
                    "saved-diagnostics preparation requires its existing frozen parent window"
                ) from exc
            prior_ledger_path = root / saved_diagnostics_config["prior_ledger_relative"]
            if (
                not isinstance(prior_window_payload, Mapping)
                or _resolve(root, prior_window_payload.get("accounting_path"), "prior accounting path")
                != prior_ledger_path.resolve()
            ):
                raise Task41ContractError(
                    "saved-diagnostics preparation found an unexpected prior accounting path"
                )
            preparation_sample = clock_sample(include_boot_id=True)
            authorization_payload = {
                "schema": TASK41_B0_SAVED_DIAGNOSTICS_AUTH_SCHEMA,
                "authorization": saved_diagnostics_config["authorization"],
                "source_at_entry": source_sha,
                "preparation_started_utc": _utc_text_from_ns(
                    int(preparation_sample["utc_ns"])
                ),
                "total_seconds": saved_diagnostics_config["total_seconds"],
                "numerical_seconds": saved_diagnostics_config["numerical_seconds"],
                "closeout_seconds": TASK41_CLOSEOUT_SECONDS,
                "scope": saved_diagnostics_config["scope"],
                "prior_window_path": str(saved_diagnostics_config["prior_window_relative"]),
                "prior_window_sha256": hashlib.sha256(prior_window_raw).hexdigest(),
                "prior_ledger_path": str(saved_diagnostics_config["prior_ledger_relative"]),
                "prior_ledger_sha256": (
                    sha256_file(prior_ledger_path) if prior_ledger_path.is_file() else None
                ),
            }
            if not _write_json_no_replace(saved_auth_path, authorization_payload):
                raise Task41ContractError(
                    "saved-diagnostics authorization was concurrently created; inspect it before retrying"
                )
        saved_diagnostics_authorization, saved_diagnostics_authorization_sha = (
            _task41_saved_diagnostics_authorization(
                root, instance=saved_diagnostics_instance
            )
        )
        if not window_path.exists() and saved_diagnostics_authorization["source_at_entry"] != source_sha:
            raise Task41ContractError(
                "saved-diagnostics authorization does not bind the frozen source SHA"
            )
    if saved_diagnostics_config is not None and not window_path.exists():
        assert saved_diagnostics_authorization is not None
        assert saved_diagnostics_authorization_sha is not None
        anchor = clock_sample(include_boot_id=True)
        t0_ns = _utc_ns(saved_diagnostics_authorization["preparation_started_utc"])
        if int(anchor["utc_ns"]) < t0_ns:
            raise Task41ContractError(
                "saved-diagnostics preparation start is later than its clock anchor"
            )
        bootstrap_seconds = (int(anchor["utc_ns"]) - t0_ns) / 1e9
        saved_diagnostics_payload = {
            "schema": TASK41_P0_WINDOW_SCHEMA,
            "task_id": TASK41_MODEL_ID,
            "source_sha": saved_diagnostics_authorization["source_at_entry"],
            "t0_utc": _utc_text_from_ns(t0_ns),
            "numerical_deadline_utc": _utc_text_from_ns(
                t0_ns + int(saved_diagnostics_config["numerical_seconds"] * 1e9)
            ),
            "deadline_utc": _utc_text_from_ns(
                t0_ns + int(saved_diagnostics_config["total_seconds"] * 1e9)
            ),
            "total_seconds": saved_diagnostics_config["total_seconds"],
            "numerical_seconds": saved_diagnostics_config["numerical_seconds"],
            "closeout_seconds": TASK41_CLOSEOUT_SECONDS,
            "anchor": anchor,
            "accounting_path": str(
                (
                root / saved_diagnostics_config["accounting_relative"]
                ).resolve()
            ),
            "t0_basis": {"kind": saved_diagnostics_config["t0_basis"]},
            "bootstrap_utc_elapsed_seconds": bootstrap_seconds,
            "bootstrap_boottime_elapsed_seconds": None,
            "bootstrap_time_treatment": (
                "preparation_start_to_anchor_utc_elapsed_charged; "
                "pre_anchor_monotonic_and_boottime_unknown"
            ),
            "authorization_sha256": saved_diagnostics_authorization_sha,
            "scope": saved_diagnostics_config["scope"],
            "prior_window_path": saved_diagnostics_authorization["prior_window_path"],
            "prior_window_sha256": saved_diagnostics_authorization["prior_window_sha256"],
            "prior_ledger_path": saved_diagnostics_authorization["prior_ledger_path"],
            "prior_ledger_sha256": saved_diagnostics_authorization["prior_ledger_sha256"],
        }
        _write_json_no_replace(window_path, saved_diagnostics_payload)
    if b0_v3_continuation and not window_path.exists():
        authorization, authorization_sha = _task41_v3_authorization(root)
        anchor = authorization["anchor"]
        t0_ns = int(anchor["utc_ns"]) - 180_000_000_000
        continuation_payload = {
            "schema": TASK41_P0_WINDOW_SCHEMA,
            "task_id": TASK41_MODEL_ID,
            "source_sha": authorization["source_at_entry"],
            "t0_utc": _utc_text_from_ns(t0_ns),
            "numerical_deadline_utc": _utc_text_from_ns(t0_ns + int(TASK41_B0_V3_NUMERICAL_SECONDS * 1e9)),
            "deadline_utc": _utc_text_from_ns(t0_ns + int(TASK41_B0_V3_TOTAL_SECONDS * 1e9)),
            "total_seconds": TASK41_B0_V3_TOTAL_SECONDS,
            "numerical_seconds": TASK41_B0_V3_NUMERICAL_SECONDS,
            "closeout_seconds": TASK41_CLOSEOUT_SECONDS,
            "anchor": anchor,
            "accounting_path": str((root / TASK41_B0_CONTROLLER_RELATIVE / "campaign_accounting_v3_24h.jsonl").resolve()),
            "t0_basis": {"kind": "user_approved_v3_24h_continuation"},
            "bootstrap_utc_elapsed_seconds": 180,
            "bootstrap_boottime_elapsed_seconds": None,
            "bootstrap_time_treatment": "conservative_pre_anchor_preparation_charge_not_measured",
            "continuation_authorization_sha256": authorization_sha,
            "parent_window_sha256": TASK41_B0_PARENT_WINDOW_SHA256,
        }
        _write_json_no_replace(window_path, continuation_payload)
    if b0_v6_continuation and not window_path.exists():
        assert v6_authorization is not None and v6_authorization_sha is not None
        anchor = clock_sample(include_boot_id=True)
        preparation_started_utc = v6_authorization.get("preparation_started_utc")
        if preparation_started_utc is None:
            t0_ns = int(anchor["utc_ns"])
            bootstrap_seconds = 0.0
            t0_basis = {"kind": "user_approved_v6_24h_continuation"}
            bootstrap_treatment = "new_approved_window_anchor_is_t0"
        else:
            t0_ns = _utc_ns(preparation_started_utc)
            if int(anchor["utc_ns"]) < t0_ns:
                raise Task41ContractError(
                    "Task41 V6 preparation start is later than the current clock anchor"
                )
            bootstrap_seconds = (int(anchor["utc_ns"]) - t0_ns) / 1e9
            t0_basis = {"kind": TASK41_B0_V6_PREPARATION_T0_KIND}
            bootstrap_treatment = TASK41_B0_V6_PREPARATION_BOOTSTRAP_TREATMENT
        v6_payload = {
            "schema": TASK41_P0_WINDOW_SCHEMA,
            "task_id": TASK41_MODEL_ID,
            "source_sha": v6_authorization["source_at_entry"],
            "t0_utc": _utc_text_from_ns(t0_ns),
            "numerical_deadline_utc": _utc_text_from_ns(
                t0_ns + int(TASK41_B0_V6_NUMERICAL_SECONDS * 1e9)
            ),
            "deadline_utc": _utc_text_from_ns(
                t0_ns + int(TASK41_B0_V6_TOTAL_SECONDS * 1e9)
            ),
            "total_seconds": TASK41_B0_V6_TOTAL_SECONDS,
            "numerical_seconds": TASK41_B0_V6_NUMERICAL_SECONDS,
            "closeout_seconds": TASK41_CLOSEOUT_SECONDS,
            "anchor": anchor,
            "accounting_path": str(
                (root / TASK41_B0_CONTROLLER_RELATIVE / "campaign_accounting_v6_24h.jsonl").resolve()
            ),
            "t0_basis": t0_basis,
            "bootstrap_utc_elapsed_seconds": bootstrap_seconds,
            "bootstrap_boottime_elapsed_seconds": None,
            "bootstrap_time_treatment": bootstrap_treatment,
            "continuation_authorization_sha256": v6_authorization_sha,
            "parent_window_path": str(TASK41_B0_V3_WINDOW_RELATIVE),
            "parent_window_sha256": TASK41_B0_V3_WINDOW_SHA256,
        }
        _write_json_no_replace(window_path, v6_payload)
    if b0_v9_continuation and not window_path.exists():
        assert v9_authorization is not None and v9_authorization_sha is not None
        anchor = clock_sample(include_boot_id=True)
        t0_ns = _utc_ns(v9_authorization["preparation_started_utc"])
        if int(anchor["utc_ns"]) < t0_ns:
            raise Task41ContractError(
                "Task41 V9 preparation start is later than the current clock anchor"
            )
        bootstrap_seconds = (int(anchor["utc_ns"]) - t0_ns) / 1e9
        v9_payload = {
            "schema": TASK41_P0_WINDOW_SCHEMA,
            "task_id": TASK41_MODEL_ID,
            "source_sha": v9_authorization["source_at_entry"],
            "t0_utc": _utc_text_from_ns(t0_ns),
            "numerical_deadline_utc": _utc_text_from_ns(
                t0_ns + int(TASK41_B0_V9_NUMERICAL_SECONDS * 1e9)
            ),
            "deadline_utc": _utc_text_from_ns(
                t0_ns + int(TASK41_B0_V9_TOTAL_SECONDS * 1e9)
            ),
            "total_seconds": TASK41_B0_V9_TOTAL_SECONDS,
            "numerical_seconds": TASK41_B0_V9_NUMERICAL_SECONDS,
            "closeout_seconds": TASK41_CLOSEOUT_SECONDS,
            "anchor": anchor,
            "accounting_path": str(
                (root / TASK41_B0_CONTROLLER_RELATIVE / "campaign_accounting_v9_24h.jsonl").resolve()
            ),
            "t0_basis": {"kind": TASK41_B0_V9_PREPARATION_T0_KIND},
            "bootstrap_utc_elapsed_seconds": bootstrap_seconds,
            "bootstrap_boottime_elapsed_seconds": None,
            "bootstrap_time_treatment": TASK41_B0_V9_PREPARATION_BOOTSTRAP_TREATMENT,
            "continuation_authorization_sha256": v9_authorization_sha,
            "parent_window_path": str(TASK41_B0_V6_WINDOW_RELATIVE),
            "parent_window_sha256": TASK41_B0_V6_WINDOW_SHA256,
            "parent_cost_ledger_path": v9_authorization["parent_cost_ledger_path"],
            "parent_cost_ledger_sha256": v9_authorization[
                "parent_cost_ledger_sha256"
            ],
        }
        _write_json_no_replace(window_path, v9_payload)
    if not window_path.exists():
        anchor = clock_sample(include_boot_id=True)
        t0_ns = (
            _utc_ns(TASK41_B0_T0_UTC)
            if case_id == "B0"
            else int(anchor["utc_ns"])
        )
        if int(anchor["utc_ns"]) < t0_ns:
            raise Task41ContractError("Task41 B0 first clock anchor precedes its fixed T0 basis")
        window_payload = {
            "schema": TASK41_P0_WINDOW_SCHEMA,
            "task_id": TASK41_MODEL_ID,
            "source_sha": source_sha,
            "t0_utc": _utc_text_from_ns(t0_ns),
            "numerical_deadline_utc": _utc_text_from_ns(
                t0_ns + int(TASK41_NUMERICAL_SECONDS * 1_000_000_000)
            ),
            "deadline_utc": _utc_text_from_ns(
                t0_ns + int(TASK41_TOTAL_SECONDS * 1_000_000_000)
            ),
            "total_seconds": TASK41_TOTAL_SECONDS,
            "numerical_seconds": TASK41_NUMERICAL_SECONDS,
            "closeout_seconds": TASK41_CLOSEOUT_SECONDS,
            "anchor": anchor,
            "accounting_path": str(
                (root / case_spec["controller_relative"] / "campaign_accounting_v10.jsonl").resolve()
            ),
        }
        if case_id == "B0":
            window_payload.update(
                {
                    "t0_basis": TASK41_B0_T0_BASIS,
                    "bootstrap_utc_elapsed_seconds": (
                        int(anchor["utc_ns"]) - t0_ns
                    )
                    / 1e9,
                    "bootstrap_boottime_elapsed_seconds": None,
                    "bootstrap_time_treatment": TASK41_B0_BOOTSTRAP_TREATMENT,
                }
            )
        _write_json_no_replace(window_path, window_payload)

    window, window_sha, window_payload = _task41_window_for_contract(
        root, case_id, b0_v3_continuation=b0_v3_continuation,
        b0_v6_continuation=b0_v6_continuation,
        b0_v9_continuation=b0_v9_continuation,
        b0_saved_diagnostics_6h=(
            saved_diagnostics_enabled and saved_diagnostics_instance is None
        ),
        b0_saved_diagnostics_instance=saved_diagnostics_instance,
    )

    runtime_path = _resolve(root, str(runtime_prefix), "runtime_prefix")
    abi_path = _resolve(root, str(abi_receipt), "abi_receipt")
    jit_path = _resolve(root, str(jit_cache), "jit_cache")
    python_path = runtime_path / "bin" / "python"
    if not runtime_path.is_dir() or not python_path.is_file() or not os.access(python_path, os.X_OK):
        raise Task41ContractError("Task41 native runtime prefix must contain executable bin/python")
    if not abi_path.is_file() or not jit_path.is_dir():
        raise Task41ContractError("Task41 ABI receipt or JIT cache path is missing")
    abi_sha = _check_task41_native_receipt(abi_path, runtime_path)
    frozen_jit_preflight = (
        verify_task41_v15_frozen_jit_cache(jit_path)
        if saved_diagnostics_instance == TASK41_B0_V15_FULL_ACCEPTANCE_INSTANCE
        else None
    )

    input_path = (root / case_spec["input_relative"]).resolve()
    try:
        from src.geometry.task41_phi90_profile import task41_payload_errors
        from src.io.execution_plan import resolved_config_bytes
        from src.io.input_validation import load_and_resolve

        specification = load_and_resolve(input_path)
        payload_errors = task41_payload_errors(specification.as_jsonable())
    except (OSError, ValueError, RuntimeError) as exc:
        raise Task41ContractError(f"Task41 registered DAT could not be resolved: {exc}") from exc
    if payload_errors:
        raise Task41ContractError(
            "Task41 registered DAT failed its native physics/profile gate: "
            + "; ".join(payload_errors)
        )
    resolved_sha = hashlib.sha256(resolved_config_bytes(specification)).hexdigest()
    case = {
        "input_path": str(case_spec["input_relative"]),
        "input_sha256": specification.input_sha256,
        "model_id": specification.identity.get("model_id"),
        "run_id": specification.identity.get("run_id"),
        "physical_model_sha256": specification.physical_model_sha256,
        "resolved_config_sha256": resolved_sha,
        "method": specification.method.get("kind"),
        "mpi_size": specification.execution.get("mpi_size"),
    }
    if case_id == "B0":
        from src.geometry.task41_phi90_profile import TASK41_B0_GEOMETRY_IDENTITY

        case.update(
            {
                "profile_identity": case_spec["profile_identity"],
                "solver_stage": case_spec["solver_stage"],
                "comparison_group": case_spec["comparison_group"],
                "geometry_identity": TASK41_B0_GEOMETRY_IDENTITY,
            }
        )
    validate_task41_specification(specification, input_path, {"case": case}, current_root=root)

    comparison = None
    if case_id == "A2":
        binding_path = (root / TASK41_A1_COMPARISON_BINDING_RELATIVE).resolve()
        binding, binding_sha256 = require_task41_a1_comparison_binding(
            binding_path, current_root=root
        )
        if binding["a1"]["physical_model_sha256"] != case["physical_model_sha256"]:
            raise Task41ContractError("A1 and A2 comparison binding have different physical models")
        comparison = {
            "a1_binding_path": str(TASK41_A1_COMPARISON_BINDING_RELATIVE),
            "a1_binding_sha256": binding_sha256,
            "same_discrete_comparison_ready": binding["a1"][
                "discrete_identity"
            ]["same_discrete_comparison_ready"],
        }

    q_csr_reuse = None
    if case_id == "A2":
        if a2_q_csr_manifests is None:
            raise Task41ContractError(
                "Task41 A2 contract preparation requires all ten saved q CSR/native manifests"
            )
        q_csr_reuse = _prepare_task41_a2_q_csr_reuse(
            root,
            a2_q_csr_manifests,
            source_sha=source_sha,
            window_sha256=window_sha,
            expected_input_sha256=case["input_sha256"],
        )
    elif a2_q_csr_manifests is not None:
        raise Task41ContractError("saved q CSR reuse is available only for Task41 A2")

    saved_surface_donor = None
    if case_id == "B0":
        saved_surface_donor = TASK41_B0_SAVED_SURFACE_DONOR
        verify_task41_b0_saved_surface_donor(
            saved_surface_donor,
            current_root=root,
            verify_source_equivalence=True,
        )

    if _git(root, "rev-parse", "HEAD") != source_sha or _git(
        root, "branch", "--show-current"
    ) != TASK41_BRANCH or _git(root, "status", "--porcelain", "--untracked-files=normal"):
        raise Task41ContractError("Task41 source changed while the P0 contract was being prepared")

    window_binding = {
        "path": str(window_relative),
        "sha256": window_sha,
        "entry_source_sha": window_payload["source_sha"],
    }
    if b0_v6_continuation:
        window_binding.update(
            {
                "continuation_authorization_sha256": v6_authorization_sha,
                "parent_window_path": str(TASK41_B0_V3_WINDOW_RELATIVE),
                "parent_window_sha256": TASK41_B0_V3_WINDOW_SHA256,
            }
        )
    elif b0_v9_continuation:
        assert v9_authorization is not None and v9_authorization_sha is not None
        window_binding.update(
            {
                "continuation_authorization_sha256": v9_authorization_sha,
                "parent_window_path": str(TASK41_B0_V6_WINDOW_RELATIVE),
                "parent_window_sha256": TASK41_B0_V6_WINDOW_SHA256,
                "parent_cost_ledger_path": v9_authorization[
                    "parent_cost_ledger_path"
                ],
                "parent_cost_ledger_sha256": v9_authorization[
                    "parent_cost_ledger_sha256"
                ],
            }
        )
    elif saved_diagnostics_config is not None:
        assert saved_diagnostics_authorization is not None
        assert saved_diagnostics_authorization_sha is not None
        window_binding.update(
            {
                "authorization_sha256": saved_diagnostics_authorization_sha,
                "scope": saved_diagnostics_config["scope"],
                "prior_window_path": saved_diagnostics_authorization["prior_window_path"],
                "prior_window_sha256": saved_diagnostics_authorization["prior_window_sha256"],
                "prior_ledger_path": saved_diagnostics_authorization["prior_ledger_path"],
                "prior_ledger_sha256": saved_diagnostics_authorization["prior_ledger_sha256"],
            }
        )

    contract_path = root / contract_relative_path(
        source_sha,
        case_id,
        saved_diagnostics_instance=(
            saved_diagnostics_instance
            if saved_diagnostics_instance is not None
            else None
        ),
    )
    if contract_path.exists():
        raise Task41ContractError("a Task41 contract already exists for this source SHA")
    service_directory = case_spec["service_relative"] / f"service_source_{source_sha}"
    contract = {
        "schema": TASK41_P0_CONTRACT_SCHEMA,
        "task_id": TASK41_MODEL_ID,
        "branch": TASK41_BRANCH,
        "source": {"sha": source_sha},
        "case": case,
        "runtime": {
            "profile": "native_linux",
            "runtime_prefix": str(runtime_path),
            "abi_receipt_path": str(abi_path),
            "abi_receipt_sha256": abi_sha,
            "jit_cache": str(jit_path),
            "mpi_ranks": 1,
            "math_threads": 1,
        },
        "window": window_binding,
        "resources": {
            "task_memory_max_bytes": TASK41_TASK_MEMORY_MAX_BYTES,
            "host_reserve_bytes": TASK41_HOST_RESERVE_BYTES,
            "memory_swap_max_bytes": 0,
        },
        "time": {
            "total_seconds": window.total_seconds,
            "numerical_seconds": window.total_seconds - window.closeout_seconds,
            "closeout_seconds": window.closeout_seconds,
        },
        "evidence": {"service_directory": str(service_directory)},
    }
    if case_id == "B0":
        contract["evidence"]["raw_disk_policy"] = {
            "scope": "task41_b0_v3_recovery_evidence",
            "raw_artifact_limit_bytes": 16 << 30,
            "free_space_floor_bytes": 2 << 30,
            "authorization": "user_20261019_16gib_evidence_only",
        }
        if saved_diagnostics_config is not None:
            contract["evidence"]["raw_disk_policy"]["new_evidence_limit_bytes"] = (
                int(saved_diagnostics_config["scope"]["new_evidence_limit_bytes"])
            )
            if saved_diagnostics_instance == TASK41_B0_V15_FULL_ACCEPTANCE_INSTANCE:
                contract["evidence"]["raw_disk_policy"].update(
                    {
                        "single_package_limit_bytes": TASK41_B0_V15_FULL_ACCEPTANCE_SINGLE_ARTIFACT_BYTES,
                        "non_raw_output_reserve_bytes": TASK41_B0_V15_FULL_ACCEPTANCE_NON_RAW_RESERVE_BYTES,
                        "raw_artifact_accounting": TASK41_B0_V15_FULL_ACCEPTANCE_SCOPE[
                            "raw_artifact_accounting"
                        ],
                        "monitoring_log_accounting": TASK41_B0_V15_FULL_ACCEPTANCE_SCOPE[
                            "monitoring_log_accounting"
                        ],
                        "raw_artifact_roots": list(
                            TASK41_B0_V15_POST_V7_RAW_EVIDENCE_ROOTS
                        ),
                        "success_exit": TASK41_B0_V15_FULL_ACCEPTANCE_SCOPE[
                            "success_exit"
                        ],
                    }
                )
    if b0_v9_continuation or saved_diagnostics_config is not None:
        contract["numerical_strategy"] = {
            "schema": "task41.p0.b0.internal_rhs_strategy.v1",
            "internal_rhs_strategy": TASK41_B0_V9_INTERNAL_RHS_STRATEGY,
        }
        if (
            saved_diagnostics_config is not None
            and saved_diagnostics_config["instance"]
            in {
                TASK41_B0_V14_SAVED_RHS_CANDIDATE_INSTANCE,
                TASK41_B0_V15_FULL_ACCEPTANCE_INSTANCE,
                TASK41_B0_V17_SELECTED_TWO_CELL_INSTANCE,
            }
        ):
            contract["numerical_strategy"].update(
                {
                    "schema": "task41.p0.b0.internal_rhs_strategy.v2",
                    "refinement_strategy": TASK41_B0_V14_RHS_REFINEMENT_STRATEGY,
                    "refinement_max_steps": 2,
                }
            )
        if saved_diagnostics_config["instance"] == TASK41_B0_V18_SAVED_JZ_INSTANCE:
            contract["numerical_strategy"] = {
                "schema": "task41.p0.b0.internal_rhs_strategy.v3",
                "internal_rhs_strategy": TASK41_B0_V9_INTERNAL_RHS_STRATEGY,
                "refinement_strategy": TASK41_B0_V14_RHS_REFINEMENT_STRATEGY,
                "refinement_max_steps": 2,
                "jz_evaluation_strategy": "binary64_real_imag_fsum",
            }
    if comparison is not None:
        contract["comparison"] = comparison
    if q_csr_reuse is not None:
        contract["q_csr_reuse"] = q_csr_reuse
    if saved_surface_donor is not None:
        contract["preparation"] = {
            "existing_surface_donor": saved_surface_donor,
        }
    if saved_diagnostics_config is not None:
        contract["execution_scope"] = saved_diagnostics_config["scope"]
        contract["preparation"] = {
            **(contract.get("preparation") or {}),
            "saved_diagnostics_prior_window_path": saved_diagnostics_authorization[
                "prior_window_path"
            ],
            "saved_diagnostics_prior_window_sha256": saved_diagnostics_authorization[
                "prior_window_sha256"
            ],
            "saved_diagnostics_prior_ledger_path": saved_diagnostics_authorization[
                "prior_ledger_path"
            ],
            "saved_diagnostics_prior_ledger_sha256": saved_diagnostics_authorization[
                "prior_ledger_sha256"
            ],
        }
    if frozen_jit_preflight is not None:
        contract["preparation"]["frozen_jit_preflight"] = frozen_jit_preflight
    retry_relative = (TASK41_V15_TIME_CONTINUATION_AUTH_RELATIVE
                      if (root / TASK41_V15_TIME_CONTINUATION_AUTH_RELATIVE).exists()
                      else TASK41_V15_RETRY_AUTH_RELATIVE)
    retry_auth_path = root / retry_relative
    if saved_diagnostics_instance == TASK41_B0_V15_FULL_ACCEPTANCE_INSTANCE and retry_auth_path.exists():
        retry_binding = {"path": str(retry_relative),
                         "sha256": sha256_file(retry_auth_path)}
        task41_v15_owner_claim_authority(
            root=root, accounting_path=Path(window_payload["accounting_path"]),
            window_path=window_path, window_sha256=window_sha,
            retry_binding=retry_binding,
        )
        contract["full_owner_retry_authorization"] = retry_binding
    if not _write_json_no_replace(contract_path, contract):
        raise Task41ContractError("a Task41 contract was concurrently created for this source SHA")
    contract_sha = sha256_file(contract_path)
    return {
        "case_id": case_id,
        "contract_path": str(contract_path.relative_to(root)),
        "contract_sha256": contract_sha,
        "window_path": str(window_path.relative_to(root)),
        "window_sha256": window_sha,
        "window_t0_utc": window_payload["t0_utc"],
        "window_entry_source_sha": window_payload["source_sha"],
        "contract_source_sha": source_sha,
        "resolved_config_sha256": resolved_sha,
        "a1_comparison_binding_sha256": (
            comparison["a1_binding_sha256"] if comparison is not None else None
        ),
        "same_discrete_comparison_ready": (
            comparison["same_discrete_comparison_ready"] if comparison is not None else None
        ),
        "service_command": _task41_p0_service_command(
            case_input=str(case_spec["input_relative"]),
            contract_path=str(contract_path.relative_to(root)),
            saved_diagnostics_enabled=saved_diagnostics_enabled,
            saved_diagnostics_instance=saved_diagnostics_instance,
            v17_output_directory=(
                str(
                    root / "results" / TASK41_MODEL_ID
                    / "task41_p0_saved_diagnostics_6h" / window_sha
                    / "selected_incident_replay" / "attempt01"
                )
                if saved_diagnostics_instance == TASK41_B0_V17_SELECTED_TWO_CELL_INSTANCE
                else None
            ),
            v18_output_directory=(
                str(
                    root / "results" / TASK41_MODEL_ID
                    / "task41_p0_saved_diagnostics_6h" / window_sha
                    / "selected_incident_replay" / "attempt01"
                )
                if saved_diagnostics_instance == TASK41_B0_V18_SAVED_JZ_INSTANCE
                else None
            ),
        ),
        "saved_diagnostics_output_root": (
            str(
                (root / "results" / TASK41_MODEL_ID
                 / "task41_p0_saved_diagnostics_6h" / window_sha).relative_to(root)
            )
            if saved_diagnostics_enabled and saved_diagnostics_instance != TASK41_B0_V15_FULL_ACCEPTANCE_INSTANCE
            else None
        ),
        "saved_surface_donor": saved_surface_donor,
    }


def validate_task41_specification(
    specification: Any, input_path: str | Path, contract: Mapping[str, Any],
    *, current_root: str | Path | None = None,
) -> None:
    root = Path(current_root or Path(__file__).resolve().parents[2]).resolve()
    case = contract["case"]
    actual_input = Path(input_path).resolve()
    expected_input = _resolve(root, case["input_path"], "case.input_path")
    from src.io.execution_plan import resolved_config_bytes

    resolved_sha = hashlib.sha256(resolved_config_bytes(specification)).hexdigest()
    if (
        actual_input != expected_input
        or sha256_file(actual_input) != case["input_sha256"]
        or specification.identity.get("model_id") != case["model_id"]
        or specification.identity.get("run_id") != case["run_id"]
        or specification.method.get("kind") != case["method"]
        or specification.execution.get("mpi_size") != case["mpi_size"]
        or specification.physical_model_sha256 != case["physical_model_sha256"]
        or resolved_sha != case["resolved_config_sha256"]
    ):
        raise Task41ContractError("resolved Task41 input differs from the frozen P0 contract")
    if case.get("run_id") == TASK41_B0_RUN_ID:
        from src.geometry.task41_phi90_profile import TASK41_B0_GEOMETRY_IDENTITY

        payload = specification.as_jsonable()
        profile = payload.get("derived", {}).get("physical_intermediate_profile", {})
        if (
            case.get("profile_identity") != TASK41_B0_PRECONDITIONER
            or case.get("solver_stage") != "TASK41_B0"
            or case.get("comparison_group") != TASK41_B0_COMPARISON_GROUP
            or case.get("geometry_identity") != TASK41_B0_GEOMETRY_IDENTITY
            or profile.get("identity") != TASK41_B0_PRECONDITIONER
            or case.get("comparison") is not None
        ):
            raise Task41ContractError(
                "resolved Task41 B0 input differs from its registered profile or has a comparison binding"
            )


def launcher_values(
    contract_path: str | Path,
    *,
    current_root: str | Path | None = None,
    saved_output_continuation: bool = False,
) -> list[str]:
    root = Path(current_root or Path(__file__).resolve().parents[2]).resolve()
    contract, digest = require_task41_p0_contract(
        contract_path,
        current_root=root,
        check_current_source=not saved_output_continuation,
        require_clean_source=True,
    )
    if saved_output_continuation:
        _saved_output_consumer_source_sha(
            contract,
            root,
            allow_current_source=_is_task41_b0_saved_diagnostics_contract(contract, root),
        )
    window = load_task41_p0_fixed_window(contract, current_root=root, require_current_boot=True)
    runtime = contract["runtime"]
    resources = contract["resources"]
    case = contract["case"]
    return [
        str(root),
        str(_resolve(root, runtime["runtime_prefix"], "runtime_prefix")),
        str(_resolve(root, runtime["abi_receipt_path"], "abi_receipt_path")),
        str(_resolve(root, runtime["jit_cache"], "jit_cache")),
        digest,
        str(window.path),
        window.sha256,
        str(resources["task_memory_max_bytes"]),
        str(resources["host_reserve_bytes"]),
        str(resources["memory_swap_max_bytes"]),
        str(_resolve(root, case["input_path"], "case.input_path")),
        str(contract["source"]["sha"]),
    ]


def qualified_activation_identity(environment: Mapping[str, str]) -> str | None:
    if environment.get("TASK41_P0_STRICT_EXECUTION") != "1":
        return None
    root = Path(__file__).resolve().parents[2]
    contract_path = environment.get("TASK41_P0_CONTRACT_PATH")
    contract_sha = environment.get("TASK41_P0_CONTRACT_SHA256")
    try:
        continuation = environment.get("TASK41_P0_SAVED_OUTPUT_CONTINUATION") == "1"
        checker_only_flag = environment.get("TASK41_P0_SAVED_OUTPUT_CHECKER_ONLY")
        checker_only = checker_only_flag == "1"
        b0_audit_flag = environment.get("TASK41_P0_SAVED_B0_EVIDENCE_AUDIT")
        b0_audit = b0_audit_flag == "1"
        v9_screen_flag = environment.get("TASK41_P0_B0_V9_SAVED_STAR_SCREEN")
        v9_screen = v9_screen_flag == "1"
        if environment.get("TASK41_P0_SAVED_OUTPUT_CONTINUATION") not in {None, "1"}:
            return None
        if checker_only_flag not in {None, "1"} or (checker_only and not continuation):
            return None
        if b0_audit_flag not in {None, "1"} or (b0_audit and (not continuation or checker_only)):
            return None
        if v9_screen_flag not in {None, "1"} or (
            v9_screen and (not continuation or checker_only or b0_audit)
        ):
            return None
        if not continuation and environment.get("TASK41_P0_CONSUMER_SOURCE_SHA") is not None:
            return None
        contract, digest = require_task41_p0_contract(
            contract_path or "",
            expected_sha256=contract_sha,
            current_root=root,
            check_current_source=(not continuation or b0_audit or v9_screen),
            require_clean_source=True,
        )
        if continuation:
            saved_diagnostics_scope = _is_task41_b0_saved_diagnostics_contract(contract, root)
            current_source_sha = _saved_output_consumer_source_sha(
                contract,
                root,
                allow_current_source=(b0_audit or v9_screen or saved_diagnostics_scope),
            )
            consumer_sha = environment.get("TASK41_P0_CONSUMER_SOURCE_SHA", "")
            if b0_audit:
                try:
                    if (
                        task41_case_id_for_run_id(str(contract["case"].get("run_id", ""))) != "B0"
                        or consumer_sha != current_source_sha
                        or environment.get("TASK41_P0_CHECKER_SOURCE_SHA") != current_source_sha
                    ):
                        return None
                except (KeyError, Task41ContractError):
                    return None
            if checker_only:
                checker_sha = environment.get("TASK41_P0_CHECKER_SOURCE_SHA")
                snapshot_path = Path(environment.get("TASK41_P0_CHECKER_INPUT_PATH", ""))
                snapshot_sha256 = environment.get("TASK41_P0_CHECKER_INPUT_SHA256", "")
                result_path = Path(environment.get("TASK41_P0_CHECKER_RESULT_PATH", ""))
                results_root = (
                    root / "results" / str(contract["case"]["model_id"])
                ).resolve()
                if (
                    checker_sha != current_source_sha
                    or not re.fullmatch(r"[0-9a-f]{40}", str(consumer_sha))
                    or consumer_sha == contract["source"]["sha"]
                    or not re.fullmatch(r"[0-9a-f]{64}", snapshot_sha256)
                    or not snapshot_path.is_absolute()
                    or snapshot_path.name != "task41_p0_saved_output_checker_input.json"
                    or not snapshot_path.is_relative_to(results_root)
                    or not snapshot_path.is_file()
                    or sha256_file(snapshot_path) != snapshot_sha256
                    or not result_path.is_absolute()
                    or result_path.name != "task41_p0_saved_output_checker_result.json"
                    or not result_path.is_relative_to(results_root)
                    or result_path.parent == snapshot_path.parent
                ):
                    return None
                snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
                if not isinstance(snapshot, Mapping):
                    return None
                producer = snapshot.get("producer")
                consumer = snapshot.get("consumer")
                if (
                    snapshot.get("schema") != "task41.p0.saved_output_continuation.v1"
                    or snapshot.get("status") != "OUTPUTS_READY"
                    or not isinstance(producer, Mapping)
                    or not isinstance(consumer, Mapping)
                    or producer.get("source_sha") != contract["source"]["sha"]
                    or consumer.get("source_sha") != consumer_sha
                    or Path(str(consumer.get("run_directory", ""))).resolve()
                    != snapshot_path.parent
                    or Path(str(producer.get("run_directory", ""))).resolve().is_relative_to(
                        snapshot_path.parent
                    )
                ):
                    return None
                ancestry = subprocess.run(
                    ["git", "merge-base", "--is-ancestor", consumer_sha, current_source_sha],
                    cwd=root,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if ancestry.returncode != 0:
                    return None
            elif v9_screen:
                case = contract.get("case")
                source = contract.get("source")
                if not isinstance(case, Mapping) or not isinstance(source, Mapping):
                    return None
                model_id = case.get("model_id")
                source_sha = source.get("sha")
                checker_sha = environment.get("TASK41_P0_CHECKER_SOURCE_SHA")
                report_raw = environment.get("TASK41_P0_B0_V9_V8_REPORT_PATH", "")
                report_sha256 = environment.get("TASK41_P0_B0_V9_V8_REPORT_SHA256", "")
                checker_raw = environment.get("TASK41_P0_B0_V9_V8_CHECKER_RESULT_PATH", "")
                checker_sha256 = environment.get(
                    "TASK41_P0_B0_V9_V8_CHECKER_RESULT_SHA256", ""
                )
                result_raw = environment.get("TASK41_P0_B0_V9_RESULT_PATH", "")
                if (
                    not isinstance(model_id, str)
                    or not model_id
                    or not isinstance(source_sha, str)
                    or not re.fullmatch(r"[0-9a-f]{40}", source_sha)
                    or task41_case_id_for_run_id(str(case.get("run_id", ""))) != "B0"
                    or consumer_sha != current_source_sha
                    or consumer_sha != source_sha
                    or checker_sha != current_source_sha
                    or environment.get("TASK41_P0_EXPECTED_SOURCE_SHA") != source_sha
                    or not isinstance(report_sha256, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", report_sha256)
                    or not isinstance(checker_sha256, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", checker_sha256)
                    or not report_raw
                    or not checker_raw
                    or not result_raw
                    or not Path(report_raw).is_absolute()
                    or not Path(checker_raw).is_absolute()
                    or not Path(result_raw).is_absolute()
                ):
                    return None
                results_root = (root / "results" / model_id).resolve()
                report_path = Path(report_raw).resolve()
                checker_result_path = Path(checker_raw).resolve()
                result_path = Path(result_raw).resolve()
                if (
                    report_path.name != "task41_p0_v8_selected_trace_star_audit.json"
                    or checker_result_path.name != "task41_p0_b0_saved_evidence_audit.json"
                    or result_path.name != "task41_p0_b0_v9_saved_star_screen.json"
                    or report_path == checker_result_path
                    or not report_path.is_relative_to(results_root)
                    or not checker_result_path.is_relative_to(results_root)
                    or not result_path.parent.is_relative_to(results_root)
                    or result_path.parent.exists()
                    or result_path.exists()
                    or not report_path.is_file()
                    or not checker_result_path.is_file()
                    or sha256_file(report_path) != report_sha256
                    or sha256_file(checker_result_path) != checker_sha256
                ):
                    return None
            elif consumer_sha != current_source_sha:
                return None
        runtime = _resolve(root, contract["runtime"]["runtime_prefix"], "runtime_prefix")
        if (
            digest != contract_sha
            or environment.get("_MYFENICS_CLOUD_QUALIFIED_ACTIVATION") != "1"
            or environment.get("_MYFENICS_CLOUD_RUNTIME_PROFILE") != "native_linux"
            or environment.get("_MYFENICS_CLOUD_ABI_MANIFEST_SHA256")
            != contract["runtime"]["abi_receipt_sha256"]
            or not Path(sys.executable).resolve().is_relative_to(runtime)
            or environment.get("TASK41_P0_EXPECTED_SOURCE_SHA")
            != contract["source"]["sha"]
        ):
            return None
        return f"task41_p0_native_complex:{contract['runtime']['abi_receipt_sha256']}"
    except (OSError, ValueError, RuntimeError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--launcher-values", action="store_true")
    mode.add_argument("--prepare", action="store_true")
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--saved-output-continuation", action="store_true")
    parser.add_argument("--runtime-prefix", type=Path)
    parser.add_argument("--abi-receipt", type=Path)
    parser.add_argument("--jit-cache", type=Path)
    parser.add_argument("--b0-v3-continuation", action="store_true")
    parser.add_argument("--b0-v6-continuation", action="store_true")
    parser.add_argument("--b0-v9-continuation", action="store_true")
    parser.add_argument("--b0-saved-diagnostics-6h", action="store_true")
    parser.add_argument(
        "--b0-saved-diagnostics-instance",
        choices=(
            TASK41_B0_V12_CANDIDATE_REPLAY_INSTANCE,
            TASK41_B0_V14_SAVED_RHS_CANDIDATE_INSTANCE,
            TASK41_B0_V15_FULL_ACCEPTANCE_INSTANCE,
            TASK41_B0_V16_SAVED_VECTOR_INSTANCE,
            TASK41_B0_V17_SELECTED_TWO_CELL_INSTANCE,
            TASK41_B0_V18_SAVED_JZ_INSTANCE,
        ),
    )
    parser.add_argument("--case", choices=("A1", "A2", "B0"), default="A1")
    parser.add_argument("--a2-q-csr-manifest", action="append", type=Path)
    args = parser.parse_args(argv)
    if args.launcher_values:
        if args.contract is None:
            parser.error("--launcher-values requires --contract")
        for value in launcher_values(
            args.contract,
            saved_output_continuation=args.saved_output_continuation,
        ):
            print(value)
        return 0
    if args.prepare:
        missing = [
            name
            for name in ("runtime_prefix", "abi_receipt", "jit_cache")
            if getattr(args, name) is None
        ]
        if missing:
            parser.error("--prepare requires --runtime-prefix, --abi-receipt, and --jit-cache")
        result = prepare_task41_p0(
            runtime_prefix=args.runtime_prefix,
            abi_receipt=args.abi_receipt,
            jit_cache=args.jit_cache,
            case_id=args.case,
            a2_q_csr_manifests=args.a2_q_csr_manifest,
            b0_v3_continuation=args.b0_v3_continuation,
            b0_v6_continuation=args.b0_v6_continuation,
            b0_v9_continuation=args.b0_v9_continuation,
            b0_saved_diagnostics_6h=args.b0_saved_diagnostics_6h,
            b0_saved_diagnostics_instance=args.b0_saved_diagnostics_instance,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
