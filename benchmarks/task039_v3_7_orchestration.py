"""Thin Task39 V3-7 orchestration and explicit worker.

The numerical builders remain in ``src`` and the reviewed Task37b setup and
recovery remain the only ordinary production path.  Historical candidate
routes are research-only; the explicit h5 qualification route is a narrow
case opt-in.  This module only sequences the identity audit, side-action
microbenchmarks, and exact-side oracle.  The parent entry point delegates
process-tree sampling to Task38's launcher; the ``--worker`` entry point
performs one authenticated MPI8 diagnostic and never creates a global direct
factor.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
from types import SimpleNamespace
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

from benchmarks.run_task037b_hybrid_iterative import (
    build_frozen_m10_setup,
    collective_heap_cleanup,
    FrozenM10LinearSolve,
    recover_frozen_m10,
    release_frozen_m10_objects,
    run_frozen_m10_physics,
)
from benchmarks.task039_hybrid_direct_identity import (
    compare_v3_7_hybrid_candidate_to_direct,
    compare_v3_7_hybrid_candidate_to_full3d,
    load_task039_direct_solution_inventory,
)
from benchmarks.task039_v4_selected_mode_packet import (
    Task039V4SelectedModeMmapContext,
    consume_task039_v4_selected_mode_packet,
)
from benchmarks.canonical_vector_artifacts import (
    read_canonical_packet_shard,
)
from benchmarks.task039_v3_side_oracle import (
    audit_hybrid_operator_identity,
    build_research_independent_hybrid_reference,
    build_research_explicit_side_components,
    _build_research_explicit_side_components,
    rebuild_hybrid_augmented_vector,
    run_exact_side_lu_oracle,
    TASK039_CASE_QUALIFICATION_SCOPE,
    TASK039_V4_H4_CASE_QUALIFICATION_SCOPE,
)
from src.common.config_3d import ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
from src.coupling.hybrid_internal_modes import build_single_hybrid_interface_mode_owner
from src.coupling.hybrid_internal_modes import build_streamed_projection_only
from src.coupling.hybrid_streamed_sources import StreamedPhysicalModalSourceProvider
from src.modes.stable_propagation import scalar_cg_discrete_traction_beta
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.io.input_validation import (
    load_and_resolve,
    simulation_config_3d_from_normalized,
    task039_dynamic_external_mode_inventory,
)
from src.io.execution_plan import ExecutionPlan
from src.runners.task039_hybrid_iterative import (
    make_task039_hybrid_iterative_profile,
)
from src.solvers.hybrid_fem_modal_augmented_direct import (
    HybridAugmentedLayout,
    internal_modal_rhs_correction,
)
from src.solvers.hybrid_fem_modal_iterative import (
    create_hybrid_assembled_block_action,
)
from src.solvers.hybrid_fem_modal_block_ldu import (
    HybridBlockLduIterativeConfig,
    create_research_exact_side_lu_block_ldu_preconditioner,
    solve_hybrid_block_ldu_iterative,
)
from src.solvers.common_3d_solve import _petsc_matrix_stats
from src.solvers.hybrid_local_dtn_action import (
    assemble_hybrid_local_dtn_action_system,
    create_hybrid_local_dtn_action_components,
)
from src.solvers.hcurl_canonical_vector_dolfinx import (
    extract_canonical_active_trace_packets,
    reconstruct_canonical_active_trace_vec,
)
from src.solvers.hybrid_layer_block import (
    audit_layer_block_action,
    build_fixed_two_layer_supernode_action,
    build_layer_block_operator,
    build_layer_sweep_action,
    build_real_layer_labels,
    audit_supernode_factor_paths,
    minimum_layer_labels,
    relative_matvec_residual,
    run_v10_right_preconditioned_fgmres_checkpoints,
)
from src.solvers.hybrid_side_response_packet import (
    V10_SIDE_RESPONSE_PACKET_COLUMNS,
    V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS,
    V10_SIDE_RESPONSE_PACKET_EXACT_RESIDUAL_LIMIT,
    V10_SIDE_RESPONSE_PACKET_PRODUCER_LIMIT_GIB,
    V10_SIDE_RESPONSE_PACKET_CONSUMER_LIMIT_GIB,
    V10_SIDE_RESPONSE_PACKET_PAYLOAD_LIMIT_GIB,
    V10_SIDE_RESPONSE_PACKET_PROJECTED_WALL_LIMIT_SECONDS,
    V10_SIDE_RESPONSE_PACKET_FULL_SCHEMA,
    V10_SIDE_RESPONSE_PACKET_FULL_METHOD,
    V10_SIDE_RESPONSE_PACKET_COMPRESSION_SCHEMA,
    V10_SIDE_RESPONSE_PACKET_COMPRESSION_METHOD,
    V10_SIDE_RESPONSE_PACKET_FULL_HOLDOUT_COLUMNS,
    V11_BOTTOM_RESPONSE_SAMPLE_INDICES,
    ExactSideResponsePacket,
    audit_bottom_response_packet_algebra,
    OwnerRowResponsePacketWriter,
    compress_owner_row_response_packet,
    load_exact_side_response_packet,
    load_full_side_response_packet,
    projected_response_payload_bytes,
    projected_response_wall_seconds,
    validate_exact_side_response_reports,
    write_exact_side_response_packet,
)
from src.solvers.hybrid_local_dtn_woodbury import (
    HybridLocalDtnWoodburyOracle,
    HybridLocalDtnWoodburyFixedAction,
    HybridLocalDtnWoodburyFixedBudgetKrylovAction,
    MUMPS_BLR_V5_H4_PROFILE,
    MUMPS_BLR_V5_H4_1E3_PROFILE,
    create_research_exact_side_lu_action,
    mumps_blr_v5_h4_controls,
)

from src.solvers.hybrid_petrov_galerkin import (
    FixedLinearOwnerRowPetrovCorrectionAction,
)
from src.solvers.hybrid_petrov_sources import (
    V6_PORT_MODAL_CHECKPOINTS,
    build_v6_discrete_gradient_source_provider,
    build_v6_factor_free_source_vector,
    build_v6_owner_row_basis_checkpoint,
    v6_port_modal_training_schedule,
    v6_single_interface_modal_provider,
)
from src.solvers.hybrid_streamed_petrov import (
    V7_STREAMED_PETROV_BATCH_SIZE,
    V7_STREAMED_PETROV_CHECKPOINTS,
    load_streamed_owner_row_basis_packet,
    run_streamed_owner_row_basis_producer,
    run_streamed_owner_row_petrov_consumer,
)
from src.solvers.hybrid_side_subspace_correction import (
    build_fixed_side_error_subspace_correction_action,
)
from src.solvers.hybrid_whole_endcap_fixed_smoother import (
    build_hybrid_whole_endcap_fixed_smoother_action,
)


TASK039_V4_H4_QUALIFICATION_METHOD = "task039_v4_h4_exact_side_case_qualification"
V3_7_PROFILE_ID = "task039.v3_7.hybrid_iterative.p6-h5.v1"
V3_7_MAX_IT = 4000
V3_7_ORACLE_MAX_IT = 100
V3_7_RHS_TOLERANCE = 1.0e-10
V3_7_MATRIX_REPEAT_TOLERANCE = V3_7_RHS_TOLERANCE
V3_7_RESIDUAL_TOLERANCE = 5.0e-9
V3_8_CANDIDATE_B_BUDGETS = (8, 16, 32)
V3_8_CANDIDATE_B_MEDIAN_LIMIT = 0.1
V3_8_CANDIDATE_B_WORST_LIMIT = 0.3
V3_8_CANDIDATE_C_MEDIAN_LIMIT = 0.1
V3_8_CANDIDATE_C_WORST_LIMIT = 0.3
V3_8_CANDIDATE_E_MEDIAN_LIMIT = 0.1
V3_8_CANDIDATE_E_WORST_LIMIT = 0.3
V3_8_CANDIDATE_E_TRAINING_SEEDS = (809, 811, 821, 823, 827, 829, 839, 853)
V3_8_CANDIDATE_D_CLASSIFICATION = (
    "USER_AUTHORIZED_EXPERIMENTAL_HYBRIDIZED_DIRECT_SIDE_CANDIDATE_D"
)
V3_8_CANDIDATE_D_QUALIFIED_CLASSIFICATION = (
    "TASK039_V3_CASE_QUALIFIED_EXPLICIT_OPT_IN_HYBRID_ITERATIVE_EXACT_SIDE_PASS"
)
V3_8_CANDIDATE_D_QUALIFIED_METHOD = "hybrid_iterative_exact_side_case_qualification"
V3_8_CANDIDATE_D_QUALIFICATION_SCOPE = TASK039_CASE_QUALIFICATION_SCOPE
V3_7_WARNING_GIB = 170.0
V3_7_CRITICAL_GIB = 195.0
V3_7_ABSOLUTE_HARD_BYTES = 224_000_000_000
V3_7_POLL_SECONDS = 0.25
V3_7_DIRECT_RUN_ROOT = Path(
    "results/task039_5nm_v3_1deg_s5_hybrid_direct_m480/"
    "task039_v3_hybrid_direct_p6h5_m480_mpi8__hybrid_direct__mpi8__M480/"
    "20260815T111156.797076Z"
)
V3_7_DIRECT_PRODUCER_SHA = "5bfab734a9ca053b69fa1f3f20d907aacbf8b07f"
V3_7_FULL3D_RUN_ROOT = Path(
    "results/task039_5nm_v3_1deg_s5_full3d/"
    "task039_v3_3d_p6h5_full3d_direct_mpi8__full3d_direct__mpi8__Mna/"
    "20260815T055152.423656Z"
)
V3_7_WATCHDOG_AUTH_FLAG = "--launched-by-task038-watchdog"
V5_H4_SETUP_ONLY_MARKERS = (
    "bottom_F_ready",
    "bottom_factor_setup_begin",
    "bottom_factor_ready",
    "bottom_woodbury_ready",
    "bottom_construction_cleanup",
    "top_F_ready",
    "top_factor_setup_begin",
    "top_factor_ready",
    "top_woodbury_ready",
    "top_construction_cleanup",
    "both_side_actions_ready",
    "modal_schur_build_begin",
    "modal_schur_ready",
    "outer_ksp_setup_ready",
    "all_setup_objects_cleanup",
)
V5_H4_SAMPLED_COLUMN_CONTRACT_PATH = Path(
    "benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/"
    "task039_v5_v4_h4_modal_schur_sampled_columns_v1.json"
)
V5_H4_BLR_SIDE_PROFILE_ID = "task039.v5.h4.mumps_blr.side_component.v1"
V5_H4_BLR_SIDE_METHOD = "task039_v5_h4_mumps_blr_side_component"
V5_H4_BLR_PROFILE_CHOICES = (
    MUMPS_BLR_V5_H4_PROFILE,
    MUMPS_BLR_V5_H4_1E3_PROFILE,
)
V5_H4_BLR_SIDE_SETUP_PEAK_LIMIT_GIB = 59.7638938904
V5_H4_BLR_RHS_SPECS = (
    ("physical_side_rhs", "system_rhs", None),
    ("modal_traction_positive", "positive_traction", 761),
    ("modal_traction_negative", "negative_traction", 763),
    ("external_dtn_coupling", "C", 769),
    ("fixed_random_repeat_0", "random", 773),
    ("fixed_random_repeat_1", "random", 779),
)
V5_H4_FIXED_BUDGET_SIDE_PROFILE_ID = (
    "task039.v5.h4.fixed_budget.bottom_side_component.v1"
)
V5_H4_FIXED_BUDGET_SIDE_METHOD = "task039_v5_h4_fixed_budget_bottom_component"
V5_H4_FIXED_BUDGET = 32
V5_H4_FIXED_BUDGET_EXACT_SPOOL_ROOT = Path(
    "results/task039_v5_h4_mumps_blr_side_component_mpi8_7e5d9b57_1e3/numerical_output"
)
V6_H4_POST_COMPACTION_PROFILE_ID = (
    "task039.v6.h4.post_compaction.exact_side_setup_only.v1"
)
V6_H4_POST_COMPACTION_METHOD = "task039_v6_h4_post_compaction_setup_only"
V6_H4_SETUP_THRESHOLD_GIB = 42.019652939
V6_H4_SETUP_THRESHOLD_BYTES = 45118258790
V6_H4_OUTER_READY_THRESHOLD_GIB = 35.0
V6_H4_EXACT_SPOOL_ROOT = V5_H4_FIXED_BUDGET_EXACT_SPOOL_ROOT
V7_H4_EXACT_SIDE_LIMIT_PROFILE_ID = "task039.v7.h4.exact_side.limit_setup_only.v1"
V7_H4_EXACT_SIDE_LIMIT_METHOD = "task039_v7_h4_exact_side_limit_setup_only"
V7_H4_EXACT_SIDE_LIMIT_GIB = 84.039305878
V7_H4_EXACT_SIDE_LIMIT_HARD_STOP_BYTES = 90236517581
V7_H4_EXACT_SIDE_LIMIT_SCHEMA = "task039.v7-h4-exact-side-limit-setup-only.v1"
V7_H4_EXACT_SPOOL_ROOT = V5_H4_FIXED_BUDGET_EXACT_SPOOL_ROOT
V7_H4_EXACT_SIDE_FULL_FORMAL_PROFILE_ID = "task039.v7.h4.exact_side.full_formal.v1"
V7_H4_EXACT_SIDE_FULL_FORMAL_METHOD = "task039_v7_h4_exact_side_full_formal"
V7_H4_EXACT_SIDE_FULL_FORMAL_SCHEMA = "task039.v7-h4-exact-side-full-formal.v1"
V7_H4_EXACT_SIDE_FULL_FORMAL_HARD_STOP_BYTES = 100262797312
V7_H4_EXACT_SIDE_FULL_FORMAL_DEFAULT_TIMEOUT_SECONDS = 21600
V7_H4_EXACT_SIDE_FULL_FORMAL_EXTENSION_TIMEOUT_SECONDS = 28800
V6_H4_PORT_MODAL_BOTTOM_PROFILE_ID = "task039.v6.h4.port_modal.bottom_component.v1"
V6_H4_PORT_MODAL_BOTTOM_METHOD = "task039_v6_h4_port_modal_bottom_component"
V6_H4_PORT_MODAL_BOTTOM_CONSTRUCTION_LIMIT_GIB = 22.0
V6_H4_PORT_MODAL_BOTTOM_RETAINED_LIMIT_GIB = 16.0
V6_H4_PORT_MODAL_BOTTOM_HARD_STOP_BYTES = 23622320128
V7_STREAMED_PETROV_PROFILE_ID = "task039.v7.streamed.bottom_basis_producer.v1"
V7_STREAMED_PETROV_METHOD = "task039_v7_streamed_bottom_basis_producer"
V7_STREAMED_PETROV_SCHEMA = "task039.v7.streamed.bottom_basis_producer.v1"
V7_STREAMED_PETROV_HARD_STOP_BYTES = 100262797312
V7_STREAMED_PETROV_MINIMUM_LIMIT_GIB = 93.377006531
V7_STREAMED_PETROV_ROBUST_LIMIT_GIB = 88.708156204
V7_STREAMED_PETROV_SOURCE_SCHEDULE_IDENTITY = (
    "task039.v7.streamed.packet_left_surface_dual.v1"
)
V7_STREAMED_PETROV_CONSUMER_PROFILE_ID = "task039.v7.streamed.bottom_petrov_consumer.v1"
V7_STREAMED_PETROV_CONSUMER_METHOD = "task039_v7_streamed_bottom_petrov_consumer"
V7_STREAMED_PETROV_CONSUMER_SCHEMA = "task039.v7.streamed.bottom_petrov_consumer.v1"
V7_STREAMED_PETROV_CONSUMER_HARD_STOP_BYTES = V7_H4_EXACT_SIDE_LIMIT_HARD_STOP_BYTES
V7_STREAMED_PETROV_CONSUMER_SETUP_LIMIT_GIB = V7_H4_EXACT_SIDE_LIMIT_GIB
V8_H4_LAYER_BLOCK_PROFILE_ID = "task039.v8.h4.layer_block_reconstruction.v1"
V8_H4_LAYER_BLOCK_METHOD = "task039_v8_h4_layer_block_reconstruction"
V8_H4_LAYER_BLOCK_SCHEMA = "task039.v8.h4.layer_block_reconstruction.v1"
V8_H4_LAYER_BLOCK_HARD_STOP_BYTES = V3_7_ABSOLUTE_HARD_BYTES
V8_H4_LAYER_SWEEP_PROFILE_ID = "task039.v8.h4.layer_sweep.bottom_component.v1"
V8_H4_LAYER_SWEEP_METHOD = "task039_v8_h4_layer_sweep_bottom"
V8_H4_LAYER_SWEEP_SCHEMA = "task039.v8.h4.layer_sweep.bottom_component.v1"
V8_H4_LAYER_SWEEP_HARD_STOP_BYTES = 45 * 2**30
V8_H4_LAYER_SWEEP_CONSTRUCTION_LIMIT_GIB = 45.0
V8_H4_LAYER_SWEEP_RETAINED_LIMIT_GIB = 30.0
V9_H4_BARE_F_SIDE_PROFILE_ID = "task039.v9.h4.bare_f_full_side.diagnostic.v1"
V9_H4_BARE_F_SIDE_METHOD = "task039_v9_h4_bare_f_full_side_diagnostic"
V9_H4_BARE_F_SIDE_SCHEMA = "task039.v9.h4.bare_f_full_side.diagnostic.v1"
V9_H4_BARE_F_SIDE_HARD_STOP_BYTES = 45 * 2**30
V9_H4_BARE_F_SIDE_CONSTRUCTION_LIMIT_GIB = 45.0
V9_H4_BARE_F_SIDE_RETAINED_LIMIT_GIB = 30.0
V9_H4_LAYER_SUPERNODE_BOTTOM_FLAG = "--v9-h4-layer-supernode-bottom"
V9_H4_LAYER_SUPERNODE_EXACT_SPOOL_ROOT_FLAG = "--v9-h4-layer-supernode-exact-spool-root"
V9_H4_LAYER_SUPERNODE_PROFILE_ID = "task039.v9.h4.layer_supernode.bottom.v1"
V9_H4_LAYER_SUPERNODE_METHOD = "task039_v9_h4_layer_supernode_bottom"
V9_H4_LAYER_SUPERNODE_SCHEMA = "task039.v9.h4.layer_supernode.bottom.v1"
V9_H4_LAYER_SUPERNODE_HARD_STOP_BYTES = 45 * 2**30
V9_H4_LAYER_SUPERNODE_CONSTRUCTION_LIMIT_GIB = 45.0
V9_H4_LAYER_SUPERNODE_RETAINED_LIMIT_GIB = 30.0
V10_H4_SUPERNODE_FACTOR_INTEGRITY_FLAG = "--v10-h4-supernode-factor-integrity"
V10_H4_SUPERNODE_FACTOR_INTEGRITY_EXACT_SPOOL_ROOT_FLAG = (
    "--v10-h4-supernode-factor-integrity-exact-spool-root"
)
V10_H4_SUPERNODE_FACTOR_INTEGRITY_PROFILE_ID = (
    "task039.v10.h4.supernode.factor_integrity.v1"
)
V10_H4_SUPERNODE_FACTOR_INTEGRITY_METHOD = "task039_v10_h4_supernode_factor_integrity"
V10_H4_SUPERNODE_FACTOR_INTEGRITY_SCHEMA = (
    "task039.v10.h4.supernode.factor_integrity.v1"
)
V10_H4_SUPERNODE_FACTOR_INTEGRITY_HARD_STOP_BYTES = 45 * 2**30
V10_H4_SUPERNODE_FACTOR_INTEGRITY_CONSTRUCTION_LIMIT_GIB = 45.0
V10_H4_SN2_J_ONLY_FLAG = "--v10-h4-sn2-j-only"
V10_H4_SN2_J_ONLY_EXACT_SPOOL_ROOT_FLAG = "--v10-h4-sn2-j-only-exact-spool-root"
V10_H4_SN2_J_ONLY_PROFILE_ID = "task039.v10.h4.sn2_j_only.v1"
V10_H4_SN2_J_ONLY_METHOD = "task039_v10_h4_sn2_j_only"
V10_H4_SN2_J_ONLY_SCHEMA = "task039.v10.h4.sn2_j_only.v1"
V10_H4_SN2_J_ONLY_HARD_STOP_BYTES = 45 * 2**30
V10_H4_SN2_J_ONLY_CONSTRUCTION_LIMIT_GIB = 45.0
V10_H4_SN2_J_ONLY_RETAINED_LIMIT_GIB = 30.0
V10_H4_SN2_J_ONLY_RESIDUAL_LIMIT = 50.7689715097
V10_H4_J1_INNER_FGMRES_FLAG = "--v10-h4-j1-inner-fgmres"
V10_H4_J1_INNER_FGMRES_EXACT_SPOOL_ROOT_FLAG = (
    "--v10-h4-j1-inner-fgmres-exact-spool-root"
)
V10_H4_J1_INNER_FGMRES_PROFILE_ID = "task039.v10.h4.j1_inner_fgmres.v1"
V10_H4_J1_INNER_FGMRES_METHOD = "task039_v10_h4_j1_inner_fgmres"
V10_H4_J1_INNER_FGMRES_SCHEMA = "task039.v10.h4.j1_inner_fgmres.v1"
V10_H4_J1_INNER_FGMRES_HARD_STOP_BYTES = 45 * 2**30
V10_H4_J1_INNER_FGMRES_CONSTRUCTION_LIMIT_GIB = 45.0
V10_H4_J1_INNER_FGMRES_RETAINED_LIMIT_GIB = 30.0
V10_H4_SIDE_RESPONSE_PACKET_PILOT_FLAG = "--v10-h4-side-response-packet-pilot"
V10_H4_SIDE_RESPONSE_PACKET_PILOT_EXACT_SPOOL_ROOT_FLAG = (
    "--v10-h4-side-response-packet-pilot-exact-spool-root"
)
V10_H4_SIDE_RESPONSE_PACKET_PILOT_OUTPUT_ROOT_FLAG = (
    "--v10-h4-side-response-packet-pilot-output-root"
)
V10_H4_SIDE_RESPONSE_PACKET_PILOT_PROFILE_ID = (
    "task039.v10.h4.side_response_packet.pilot.v1"
)
V10_H4_SIDE_RESPONSE_PACKET_PILOT_METHOD = "task039_v10_h4_side_response_packet_pilot"
V10_H4_SIDE_RESPONSE_PACKET_PILOT_SCHEMA = (
    "task039.v10.h4.side_response_packet.pilot.v1"
)
V10_H4_SIDE_RESPONSE_PACKET_PILOT_HARD_STOP_BYTES = 60 * 2**30
V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_FLAG = "--v10-h4-side-response-packet-consumer"
V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_MANIFEST_FLAG = (
    "--v10-h4-side-response-packet-consumer-manifest"
)
V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_MANIFEST_SHA256_FLAG = (
    "--v10-h4-side-response-packet-consumer-manifest-sha256"
)
V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_PROFILE_ID = (
    "task039.v10.h4.side_response_packet.consumer.v1"
)
V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_METHOD = (
    "task039_v10_h4_side_response_packet_consumer"
)
V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_SCHEMA = (
    "task039.v10.h4.side_response_packet.consumer.v1"
)
V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_HARD_STOP_BYTES = 30 * 2**30
V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_PROFILE_ID = (
    "task039.v10.h4.side_response_packet.full_producer.v1"
)
V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_METHOD = (
    "task039_v10_h4_side_response_packet_full_producer"
)
V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_SCHEMA = V10_SIDE_RESPONSE_PACKET_FULL_SCHEMA
V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_FLAG = (
    "--v10-h4-side-response-packet-full-producer"
)
V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_OUTPUT_ROOT_FLAG = (
    "--v10-h4-side-response-packet-full-producer-output-root"
)
V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_EXACT_SPOOL_ROOT_FLAG = (
    "--v10-h4-side-response-packet-full-producer-exact-spool-root"
)
V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_HARD_STOP_BYTES = 60 * 2**30
V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_PROFILE_ID = (
    "task039.v10.h4.side_response_packet.compression.v1"
)
V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_METHOD = (
    V10_SIDE_RESPONSE_PACKET_COMPRESSION_METHOD
)
V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_SCHEMA = (
    V10_SIDE_RESPONSE_PACKET_COMPRESSION_SCHEMA
)
V10_SIDE_RESPONSE_PACKET_FROZEN_HOLDOUT_MANIFEST_SHA256 = (
    "2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067"
)
V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_FLAG = (
    "--v10-h4-side-response-packet-compression"
)
V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_MANIFEST_FLAG = (
    "--v10-h4-side-response-packet-compression-manifest"
)
V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_MANIFEST_SHA256_FLAG = (
    "--v10-h4-side-response-packet-compression-manifest-sha256"
)
V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_PRODUCER_SOURCE_SHA_FLAG = (
    "--v10-h4-side-response-packet-compression-producer-source-sha"
)
V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_HARD_STOP_BYTES = 30 * 2**30
V11_BOTTOM_PACKET_ALGEBRA_PROFILE_ID = "task039.v11.h4.bottom_packet_algebra.v1"
V11_BOTTOM_PACKET_ALGEBRA_SCHEMA = "task039.v11.h4.bottom_packet_algebra.v1"
V11_BOTTOM_PACKET_ALGEBRA_METHOD = "task039_v11_h4_bottom_packet_algebra"
V11_BOTTOM_PACKET_ALGEBRA_HARD_STOP_BYTES = 45 * 2**30
V11_BOTTOM_PACKET_ALGEBRA_FLAG = "--v11-h4-bottom-packet-algebra"
V11_BOTTOM_PACKET_ALGEBRA_EXACT_SPOOL_ROOT_FLAG = (
    "--v11-h4-bottom-packet-algebra-exact-spool-root"
)
V11_BOTTOM_PACKET_ALGEBRA_PACKET_MANIFEST_FLAG = (
    "--v11-h4-bottom-packet-algebra-packet-manifest"
)
V11_BOTTOM_PACKET_ALGEBRA_PACKET_MANIFEST_SHA256_FLAG = (
    "--v11-h4-bottom-packet-algebra-packet-manifest-sha256"
)
V11_BOTTOM_PACKET_ALGEBRA_PRODUCER_DIAGNOSTIC_FLAG = (
    "--v11-h4-bottom-packet-algebra-producer-diagnostic"
)
V11_RESPONSE_PACKET_MANIFEST_SHA256 = (
    "1f4e8acaf278bde0d0d14a2a096335049ee988cdbc1b406bca4197918ff64a0e"
)
V11_RESPONSE_PACKET_PRODUCER_SOURCE_SHA = "dbc5e9bfdf9ad0520881caa168c7a27316d50f10"
V11_RESPONSE_PACKET_INPUT_SHA256 = (
    "4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811"
)
V11_RESPONSE_PACKET_PHYSICAL_MODEL_SHA256 = (
    "8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c"
)
V11_RESPONSE_PACKET_SELECTED_MANIFEST_SHA256 = (
    "2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067"
)
V11_RESPONSE_PACKET_DIAGNOSTIC_SHA256 = (
    "184ae4bd2d4c5721131d1b735c07ee745c18df1b2cdce87fcb4b4c9d1d527830"
)
V11_SELECTED_PACKET_IDENTITY_SHA256 = (
    "cfd5704b48bff980fa2d819f4deee9a59bb9a3db39bc24a70c53f42f067d39e9"
)
V11_V7_FULL_FORMAL_ROOT = "results/task039_v7_h4_exact_side_full_formal_mpi8_9e31ecf1"
V11_V7_MODAL_Q_RELATIVE = "m10_own_grid_EH_modal_q.npz"
V11_V7_ACTIVE_TRACE_MANIFEST_RELATIVE = (
    "task037b_m10_bottom_active_trace_canonical_manifest.json"
)
V11_V7_ACTIVE_TRACE_MANIFEST_SHA256 = (
    "fae8e3654e5f21ac81f23080de6f1763e99bb2b12ba28d0ddd1814d24e01d765"
)
V11_V7_MODAL_Q_SHA256 = (
    "7107e54e47498d7b493076dee3bbab0fc94e06db76f20e67e254fbeb46a8a8c2"
)
V11_V7_MODAL_AMPLITUDES_SHA256 = (
    "c386d3f97180de5879006209091a3e2743709857065d3aa4dfffd320f6962ce4"
)
V10_SIDE_RESPONSE_PACKET_FROZEN_SELECTED_COLUMNS = (
    0,
    1,
    240,
    267,
    479,
    480,
    481,
    720,
    746,
    959,
)
V9_FROZEN_HOLDOUT_PRODUCER_SHA = "7e5d9b57a10b1093f0cb062eaf7bc12797c47e1f"
V9_FROZEN_HOLDOUT_CATALOG_SHA256 = (
    "a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384"
)
V7_STREAMED_LEFT_DUAL_ORACLE = {
    "positive": {
        "relative_error": 900.298368548294,
        "finite": True,
        "tolerance": 1.0e-12,
        "equivalent": False,
        "alpha": [867.9431664084565, 242.7894121011002],
        "aligned_residual": 2.4117285472279123e-16,
        "vector_equal": False,
        "direction_equivalent": True,
        "fixture_scope": "tiny_fixture_oracle_only",
    },
    "negative": {
        "relative_error": 900.298368548294,
        "finite": True,
        "tolerance": 1.0e-12,
        "equivalent": False,
        "alpha": [867.9431664084565, 242.7894121011002],
        "aligned_residual": 2.4117285472279123e-16,
        "vector_equal": False,
        "direction_equivalent": True,
        "fixture_scope": "tiny_fixture_oracle_only",
    },
}


def _v7_streamed_basis_provenance(schedule_sha256: str) -> dict[str, Any]:
    return {
        "source_schedule_identity": V7_STREAMED_PETROV_SOURCE_SCHEDULE_IDENTITY,
        "schedule_sha256": str(schedule_sha256),
        "training_holdout_disjoint": True,
        "training_reads_holdout_files": False,
        "exact_spool_opened": False,
        "holdout_opened": False,
        "consumer_qep_calls": 0,
        "batch_size": V7_STREAMED_PETROV_BATCH_SIZE,
        "left_dual_authority": "packet_left_surface_dual",
        "left_dual_oracle": deepcopy(V7_STREAMED_LEFT_DUAL_ORACLE),
        "left_dual_oracle_fixture_scope": "tiny_fixture_oracle_only",
    }


V6_PORT_MODAL_HOLDOUT_LABELS = (
    "physical_side_rhs",
    "modal_traction_positive",
    "modal_traction_negative",
    "external_dtn_coupling",
    "fixed_random_repeat_0",
    "fixed_random_repeat_1",
)
V6_PORT_MODAL_PREFERRED_LABELS = frozenset(
    {
        "modal_traction_positive",
        "modal_traction_negative",
        "external_dtn_coupling",
    }
)


def _v6_port_modal_holdout_gate(
    reports: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Apply the frozen V6 port-modal holdout numerical contract."""

    expected_labels = set(V6_PORT_MODAL_HOLDOUT_LABELS)
    if len(reports) != len(V6_PORT_MODAL_HOLDOUT_LABELS):
        raise ValueError("V6 holdout report count is not the frozen six")
    labels = [report.get("label") for report in reports]
    if any(not isinstance(label, str) for label in labels):
        raise ValueError("V6 holdout reports must carry string labels")
    if len(set(labels)) != len(labels) or set(labels) != expected_labels:
        raise ValueError("V6 holdout labels are not the frozen unique six")
    physical_label = "physical_side_rhs"
    for report in reports:
        if not isinstance(report.get("degenerate_uninformative"), bool):
            raise ValueError("V6 holdout reports lack degeneracy metadata")
        if report["label"] != physical_label and report["degenerate_uninformative"]:
            raise ValueError("Only physical_side_rhs may be degenerate")

    mandatory = [
        report
        for report in reports
        if not (
            report["label"] == physical_label and report["degenerate_uninformative"]
        )
    ]
    finite_pass = all(report.get("finite") is True for report in reports)
    repeat_pass = all(
        report.get("repeat_relative_error") is not None
        and report["repeat_relative_error"] <= 1.0e-10
        for report in reports
    )
    linearity_pass = all(
        report.get("linearity_relative_error") is not None
        and report["linearity_relative_error"] <= 1.0e-10
        for report in reports
    )
    residual_pass = bool(
        mandatory
        and all(
            report.get("true_residual_relative") is not None
            and report["true_residual_relative"] <= 1.0e-2
            for report in mandatory
        )
    )
    preferred = [
        report
        for report in mandatory
        if report["label"] in V6_PORT_MODAL_PREFERRED_LABELS
    ]
    preferred_pass = bool(
        len(preferred) == len(V6_PORT_MODAL_PREFERRED_LABELS)
        and all(
            report.get("true_residual_relative") is not None
            and report["true_residual_relative"] <= 1.0e-3
            for report in preferred
        )
    )
    policy = {
        "finite_pass": bool(finite_pass),
        "repeat_pass": bool(repeat_pass),
        "linearity_pass": bool(linearity_pass),
        "true_residual_pass": bool(residual_pass),
        "true_residual_limit": 1.0e-2,
        "preferred_residual_max": max(
            (report.get("true_residual_relative") for report in preferred),
            default=None,
        ),
        "preferred_residual_limit": 1.0e-3,
        "preferred_residual_pass": bool(preferred_pass),
        "preferred_residual_is_diagnostic": False,
        "mandatory_labels": [report["label"] for report in mandatory],
        "degenerate_labels": [
            report["label"] for report in reports if report["degenerate_uninformative"]
        ],
        "pass": bool(
            finite_pass
            and repeat_pass
            and linearity_pass
            and residual_pass
            and preferred_pass
        ),
    }
    return policy


def _validate_v5_h4_blr_profile(profile: str) -> str:
    if profile not in V5_H4_BLR_PROFILE_CHOICES:
        raise ValueError(f"Unsupported V5 h4 BLR profile: {profile}")
    return profile


def _load_v5_h4_sampled_column_contract(
    path: str | Path = V5_H4_SAMPLED_COLUMN_CONTRACT_PATH,
) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    packet = payload.get("packet")
    contract = payload.get("contract")
    if not isinstance(packet, Mapping) or not isinstance(contract, Mapping):
        raise ValueError("V5 sampled modal contract has an invalid shape.")
    if (
        packet.get("mode_count_per_direction") != 480
        or contract.get("mode_count_per_direction") != 480
    ):
        raise ValueError("V5 sampled modal contract is not fixed to M=480.")
    columns = [int(column) for column in contract.get("columns", ())]
    roles = contract.get("roles")
    if not columns or not isinstance(roles, Mapping):
        raise ValueError("V5 sampled modal contract has no frozen columns/roles.")
    expected_role_keys = {str(column) for column in columns}
    if set(roles) != expected_role_keys:
        raise ValueError(
            "V5 sampled modal roles must cover exactly the frozen columns."
        )
    canonical = {
        "columns": columns,
        "mode_count_per_direction": 480,
        "roles": {str(column): list(roles[str(column)]) for column in columns},
    }
    actual_sha = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if contract.get("sha256") != actual_sha:
        raise ValueError("V5 sampled modal contract hash is invalid.")
    manifest = Path(str(packet["manifest"]))
    if not manifest.is_file() or hashlib.sha256(
        manifest.read_bytes()
    ).hexdigest() != packet.get("manifest_sha256"):
        raise ValueError("V5 sampled modal contract packet manifest is not hash-bound.")
    policy = {
        "columns": columns,
        "roles": {str(column): list(roles[str(column)]) for column in columns},
        "sha256": actual_sha,
        "manifest_sha256": packet["manifest_sha256"],
        "identity_sha256": packet.get("identity_sha256"),
        "path": str(Path(path)),
    }
    return policy


def v10_side_response_packet_pilot_schedule(
    path: str | Path = V5_H4_SAMPLED_COLUMN_CONTRACT_PATH,
) -> tuple[dict[str, Any], ...]:
    """Return the fixed, non-overlapping sixteen-column V10-6 pilot schedule."""

    contract = _load_v5_h4_sampled_column_contract(path)
    selected_columns = [int(column) for column in contract["columns"]]
    if tuple(selected_columns) != V10_SIDE_RESPONSE_PACKET_FROZEN_SELECTED_COLUMNS:
        raise ValueError("V10-6 selected modal columns do not match the frozen tuple")
    schedule = [
        {
            "label": f"selected_modal_{column}",
            "kind": "selected_modal",
            "column": int(column),
            "role": list(contract["roles"][str(column)]),
        }
        for column in selected_columns
    ]
    schedule.extend(
        {
            "label": label,
            "kind": "holdout",
            "spool_label": spool_label,
            "role": role,
        }
        for label, spool_label, role in (
            (
                "holdout_modal_traction_positive",
                "modal_traction_positive",
                "modal_positive",
            ),
            (
                "holdout_modal_traction_negative",
                "modal_traction_negative",
                "modal_negative",
            ),
            (
                "holdout_external_dtn_coupling",
                "external_dtn_coupling",
                "external",
            ),
        )
    )
    schedule.extend(
        {
            "label": f"holdout_fixed_random_{index}",
            "kind": "deterministic_random",
            "spool_label": f"fixed_random_repeat_{index}",
            "role": "random",
        }
        for index in range(2)
    )
    replacement_column = next(
        column for column in range(960) if column not in set(selected_columns)
    )
    schedule.append(
        {
            "label": "physical_zero_replacement_modal",
            "kind": "physical_zero_replacement",
            "column": int(replacement_column),
            "role": "physical_zero_replaced_by_extra_modal",
            "replacement_reason": "physical_side_rhs_is_frozen_zero",
        }
    )
    if (
        len(schedule) != V10_SIDE_RESPONSE_PACKET_COLUMNS
        or len({item["label"] for item in schedule}) != V10_SIDE_RESPONSE_PACKET_COLUMNS
    ):
        raise ValueError("V10-6 pilot schedule is not exactly sixteen unique columns")
    return tuple(schedule)


def v10_side_response_packet_full_schedule(
    path: str | Path = V5_H4_SAMPLED_COLUMN_CONTRACT_PATH,
) -> tuple[dict[str, Any], ...]:
    """Return the fixed 960-modal plus frozen physical-validation schedule."""

    contract = _load_v5_h4_sampled_column_contract(path)
    selected = {
        int(column): list(contract["roles"][str(column)])
        for column in contract["columns"]
    }
    if tuple(sorted(selected)) != tuple(V10_SIDE_RESPONSE_PACKET_FULL_HOLDOUT_COLUMNS):
        raise ValueError("full response schedule selected columns drifted")
    schedule = []
    for column in range(960):
        schedule.append(
            {
                "label": f"modal_response_{column}",
                "kind": "selected_modal" if column in selected else "training_modal",
                "column": column,
                "role": selected.get(column, "training_modal"),
            }
        )
    schedule.append(
        {
            "label": "physical_side_rhs",
            "kind": "physical_side_rhs",
            "column": 960,
            "role": "physical_zero_validation",
            "training_excluded": True,
        }
    )
    if len(schedule) != V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS:
        raise ValueError("full response schedule must contain 961 columns")
    return tuple(schedule)


def _v10_side_response_resolved_provenance(
    resolved_payload: Mapping[str, Any],
) -> tuple[str, str]:
    provenance = resolved_payload.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("V10-6 requires resolved provenance metadata")
    values: list[str] = []
    for field_name in ("input_sha256", "physical_model_sha256"):
        value = provenance.get(field_name)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdefABCDEF" for character in value)
        ):
            raise ValueError(f"V10-6 requires a 64-hex provenance {field_name}")
        values.append(value)
    return values[0], values[1]


def _keys(inventory: Mapping[str, Any]) -> set[tuple[str, int, int, str]]:
    result: set[tuple[str, int, int, str]] = set()
    for item in inventory.get("keys", ()):
        if isinstance(item, Mapping):
            result.add(
                (
                    str(item["side"]),
                    int(item["m"]),
                    int(item["n"]),
                    str(item["polarization"]),
                )
            )
    return result


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, complex):
        return [_json_safe(value.real), _json_safe(value.imag)]
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (bool, int, float, str)) or value is None:
        return value
    raise TypeError(f"unsupported V3-7 record value: {type(value).__name__}")


def v3_7_profile_from_resolved(
    resolved_payload: Mapping[str, Any],
) -> Any:
    """Derive the V3 profile from the official 1-degree resolved payload."""

    validate_v3_7_resolved_identity(resolved_payload)
    incidence = resolved_payload["incidence"]
    base = make_task039_hybrid_iterative_profile(480, 8, mesh_target_nm=5.0)
    return replace(
        base,
        profile_id=V3_7_PROFILE_ID,
        record_schema="task039.v3_7.hybrid-iterative-online.v1",
        qualification_schema="task039.v3_7.hybrid-iterative-qualification.v1",
        wavelength_nm=float(incidence["wavelength_nm"]),
        incident_grazing_deg=float(incidence["grazing_angle_deg"]),
        incident_phi_deg=float(incidence["azimuth_deg"]),
        polarization_kind=str(incidence["polarization"]).lower(),
        h_nm=5.0,
        modal_h_nm=5.0,
        requested_modes=480,
        candidate_modes=960,
        max_it=V3_7_MAX_IT,
        rtol=V3_7_RESIDUAL_TOLERANCE,
        assembly_backend=ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
        side_residual_correction_steps=2,
    )


def validate_v3_7_resolved_identity(payload: Mapping[str, Any]) -> None:
    """Reject a near-match before any setup or numerical object is created."""

    if payload.get("dimension") != 3:
        raise ValueError("V3-7 requires dimension=3")
    if payload.get("model_id") != "task039_5nm_v3_1deg_s5_hybrid_direct_m480":
        raise ValueError("V3-7 requires the official 1-degree h5 direct model_id")
    incidence = payload.get("incidence")
    discretization = payload.get("discretization")
    boundary = payload.get("boundary")
    method = payload.get("method")
    execution = payload.get("execution")
    if not all(
        isinstance(item, Mapping)
        for item in (incidence, discretization, boundary, method, execution)
    ):
        raise ValueError("V3-7 resolved identity sections are incomplete")
    expected = (
        (incidence["wavelength_nm"], 5.0),
        (incidence["grazing_angle_deg"], 1.0),
        (incidence["azimuth_deg"], 0.0),
        (incidence["polarization"], "s"),
        (discretization["nedelec_degree"], 6),
        (discretization["visualization_degree"], 6),
        (discretization["mesh_target_nm"], 5.0),
        (method["kind"], "hybrid_direct"),
        (method["requested_modes_per_direction"], 480),
        (method["propagation_model"], "full3d_uniform_cg"),
        (method["traction_model"], "full3d_one_cell_exact_schur"),
        (boundary["vertical_boundary"], "dtn_port"),
        (boundary["dtn_order_policy"], "auto_propagating"),
        (boundary["dtn_assembly"], "auxiliary"),
        (boundary["use_pml"], False),
        (execution["mpi_size"], 8),
    )
    if any(actual != value for actual, value in expected):
        raise ValueError("V3-7 official physical/discrete identity is not exact")


def v3_7_watchdog_policy(
    payload: Mapping[str, Any],
    *,
    poll_interval_seconds: float = V3_7_POLL_SECONDS,
    v6_h4_post_compaction_setup_only: bool = False,
    v7_h4_exact_side_limit_setup_only: bool = False,
    v7_h4_exact_side_full_formal: bool = False,
    v6_h4_port_modal_bottom_only: bool = False,
    v7_h4_streamed_bottom_producer: bool = False,
    v7_h4_streamed_bottom_consumer: bool = False,
    v8_h4_layer_block_reconstruction: bool = False,
    v8_h4_layer_sweep_bottom: bool = False,
    v9_h4_bare_f_side: bool = False,
    v9_h4_layer_supernode_bottom: bool = False,
    v10_h4_supernode_factor_integrity: bool = False,
    v10_h4_sn2_j_only: bool = False,
    v10_h4_j1_inner_fgmres: bool = False,
    v10_h4_side_response_packet_pilot: bool = False,
    v10_h4_side_response_packet_pilot_exact_spool_root: str | Path | None = None,
    v10_h4_side_response_packet_pilot_output_root: str | Path | None = None,
    v10_h4_side_response_packet_consumer: bool = False,
    v10_h4_side_response_packet_consumer_manifest: str | Path | None = None,
    v10_h4_side_response_packet_consumer_manifest_sha256: str | None = None,
    v10_h4_side_response_packet_full_producer: bool = False,
    v10_h4_side_response_packet_compression: bool = False,
    v11_h4_bottom_packet_algebra: bool = False,
) -> dict[str, Any]:
    """Return the byte-authoritative policy; 195 GiB is telemetry only."""

    execution = payload.get("execution")
    if not isinstance(execution, Mapping):
        raise ValueError("V3-7 watchdog policy requires execution")
    if execution.get("warning_memory_gib") != V3_7_WARNING_GIB:
        raise ValueError("V3-7 warning threshold must be 170 GiB")
    if execution.get("terminate_memory_gib") != V3_7_CRITICAL_GIB:
        raise ValueError("V3-7 195 GiB field must remain the critical checkpoint")
    if execution.get("absolute_terminate_memory_bytes") != V3_7_ABSOLUTE_HARD_BYTES:
        raise ValueError("V3-7 absolute hard stop must be 224000000000 bytes")
    if execution.get("require_zero_swap") is not True:
        raise ValueError("V3-7 requires zero swap")
    if not np.isfinite(float(poll_interval_seconds)) or poll_interval_seconds > 0.25:
        raise ValueError("V3-7 watchdog polling must be <=0.25 seconds")
    if v7_h4_exact_side_full_formal:
        absolute_bytes = V7_H4_EXACT_SIDE_FULL_FORMAL_HARD_STOP_BYTES
    elif v7_h4_exact_side_limit_setup_only:
        absolute_bytes = V7_H4_EXACT_SIDE_LIMIT_HARD_STOP_BYTES
    elif v6_h4_post_compaction_setup_only:
        absolute_bytes = V6_H4_SETUP_THRESHOLD_BYTES
    elif v6_h4_port_modal_bottom_only:
        absolute_bytes = V6_H4_PORT_MODAL_BOTTOM_HARD_STOP_BYTES
    elif v7_h4_streamed_bottom_producer:
        absolute_bytes = V7_STREAMED_PETROV_HARD_STOP_BYTES
    elif v7_h4_streamed_bottom_consumer:
        absolute_bytes = V7_STREAMED_PETROV_CONSUMER_HARD_STOP_BYTES
    elif v8_h4_layer_sweep_bottom:
        absolute_bytes = V8_H4_LAYER_SWEEP_HARD_STOP_BYTES
    elif v9_h4_bare_f_side:
        absolute_bytes = V9_H4_BARE_F_SIDE_HARD_STOP_BYTES
    elif v9_h4_layer_supernode_bottom:
        absolute_bytes = V9_H4_LAYER_SUPERNODE_HARD_STOP_BYTES
    elif v10_h4_supernode_factor_integrity:
        absolute_bytes = V10_H4_SUPERNODE_FACTOR_INTEGRITY_HARD_STOP_BYTES
    elif v10_h4_sn2_j_only:
        absolute_bytes = V10_H4_SN2_J_ONLY_HARD_STOP_BYTES
    elif v10_h4_j1_inner_fgmres:
        absolute_bytes = V10_H4_J1_INNER_FGMRES_HARD_STOP_BYTES
    elif v10_h4_side_response_packet_pilot:
        absolute_bytes = V10_H4_SIDE_RESPONSE_PACKET_PILOT_HARD_STOP_BYTES
    elif v10_h4_side_response_packet_consumer:
        absolute_bytes = V10_SIDE_RESPONSE_PACKET_CONSUMER_LIMIT_GIB * 2**30
    elif v10_h4_side_response_packet_full_producer:
        absolute_bytes = V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_HARD_STOP_BYTES
    elif v10_h4_side_response_packet_compression:
        absolute_bytes = V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_HARD_STOP_BYTES
    elif v11_h4_bottom_packet_algebra:
        absolute_bytes = V11_BOTTOM_PACKET_ALGEBRA_HARD_STOP_BYTES
    else:
        absolute_bytes = V3_7_ABSOLUTE_HARD_BYTES
    if v7_h4_exact_side_full_formal:
        profile_name = "v7_h4_exact_side_full_formal"
    elif v7_h4_exact_side_limit_setup_only:
        profile_name = "v7_h4_exact_side_limit_setup_only"
    elif v6_h4_post_compaction_setup_only:
        profile_name = "v6_h4_post_compaction_setup_only"
    elif v6_h4_port_modal_bottom_only:
        profile_name = "v6_h4_port_modal_bottom_only"
    elif v7_h4_streamed_bottom_producer:
        profile_name = "v7_h4_streamed_bottom_producer"
    elif v7_h4_streamed_bottom_consumer:
        profile_name = "v7_h4_streamed_bottom_consumer"
    elif v8_h4_layer_block_reconstruction:
        profile_name = "v8_h4_layer_block_reconstruction"
    elif v8_h4_layer_sweep_bottom:
        profile_name = "v8_h4_layer_sweep_bottom"
    elif v9_h4_bare_f_side:
        profile_name = "v9_h4_bare_f_side"
    elif v9_h4_layer_supernode_bottom:
        profile_name = "v9_h4_layer_supernode_bottom"
    elif v10_h4_supernode_factor_integrity:
        profile_name = "v10_h4_supernode_factor_integrity"
    elif v10_h4_sn2_j_only:
        profile_name = "v10_h4_sn2_j_only"
    elif v10_h4_j1_inner_fgmres:
        profile_name = "v10_h4_j1_inner_fgmres"
    elif v10_h4_side_response_packet_pilot:
        profile_name = "v10_h4_side_response_packet_pilot"
    elif v10_h4_side_response_packet_consumer:
        profile_name = "v10_h4_side_response_packet_consumer"
    elif v10_h4_side_response_packet_full_producer:
        profile_name = V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_PROFILE_ID
    elif v10_h4_side_response_packet_compression:
        profile_name = V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_PROFILE_ID
    elif v11_h4_bottom_packet_algebra:
        profile_name = V11_BOTTOM_PACKET_ALGEBRA_PROFILE_ID
    else:
        profile_name = "v3_7_default"
    policy = {
        "warning_memory_gib": V3_7_WARNING_GIB,
        "critical_memory_gib": V3_7_CRITICAL_GIB,
        "critical_action": "record_checkpoint_only",
        "absolute_terminate_memory_bytes": absolute_bytes,
        "absolute_hard_stop_action": "terminate_complete_process_tree",
        "require_zero_swap": True,
        "poll_interval_seconds": float(poll_interval_seconds),
        "hard_stop_gib": absolute_bytes / 2**30,
        "profile": profile_name,
    }
    if v7_h4_exact_side_full_formal:
        policy["timeout_policy"] = {
            "default_seconds": V7_H4_EXACT_SIDE_FULL_FORMAL_DEFAULT_TIMEOUT_SECONDS,
            "conditional_extension_seconds": V7_H4_EXACT_SIDE_FULL_FORMAL_EXTENSION_TIMEOUT_SECONDS,
            "extension_requires_outer_and_decreasing_residual": True,
            "automatic_extension": False,
        }
    return policy


def load_v3_7_official_payload(input_path: str | Path) -> dict[str, Any]:
    """Resolve the official dat without dispatching a worker."""

    specification = load_and_resolve(input_path)
    payload = specification.as_jsonable()
    validate_v3_7_resolved_identity(payload)
    return payload


def build_v3_7_execution_plan(
    input_path: str | Path,
    run_directory: str | Path,
    *,
    source_sha: str,
    python_executable: str | Path | None = None,
    mpiexec_command: str | None = None,
    candidate_b_only: bool = False,
    candidate_c_only: bool = False,
    candidate_d_only: bool = False,
    candidate_d_qualified: bool = False,
    candidate_e_side_only: bool = False,
    v5_h4_setup_only: bool = False,
    v5_h4_blr_side_only: bool = False,
    v5_h4_fixed_budget_bottom_only: bool = False,
    v5_h4_fixed_budget_exact_spool_root: str | Path | None = None,
    v6_h4_post_compaction_setup_only: bool = False,
    v6_h4_exact_spool_root: str | Path | None = None,
    v7_h4_exact_side_limit_setup_only: bool = False,
    v7_h4_exact_side_exact_spool_root: str | Path | None = None,
    v7_h4_exact_side_full_formal: bool = False,
    v6_h4_port_modal_bottom_only: bool = False,
    v6_h4_port_modal_exact_spool_root: str | Path | None = None,
    v7_h4_streamed_bottom_producer: bool = False,
    v7_h4_streamed_bottom_consumer: bool = False,
    v7_h4_streamed_bottom_consumer_basis_manifest: str | Path | None = None,
    v7_h4_streamed_bottom_consumer_basis_manifest_sha256: str | None = None,
    v7_h4_streamed_bottom_consumer_exact_spool_root: str | Path | None = None,
    v8_h4_layer_block_reconstruction: bool = False,
    v8_h4_layer_sweep_bottom: bool = False,
    v9_h4_bare_f_side: bool = False,
    v9_h4_bare_f_side_exact_spool_root: str | Path | None = None,
    v9_h4_layer_supernode_bottom: bool = False,
    v9_h4_layer_supernode_exact_spool_root: str | Path | None = None,
    v10_h4_supernode_factor_integrity: bool = False,
    v10_h4_supernode_factor_integrity_exact_spool_root: str | Path | None = None,
    v10_h4_sn2_j_only: bool = False,
    v10_h4_sn2_j_only_exact_spool_root: str | Path | None = None,
    v10_h4_j1_inner_fgmres: bool = False,
    v10_h4_j1_inner_fgmres_exact_spool_root: str | Path | None = None,
    v10_h4_side_response_packet_pilot: bool = False,
    v10_h4_side_response_packet_pilot_exact_spool_root: str | Path | None = None,
    v10_h4_side_response_packet_pilot_output_root: str | Path | None = None,
    v10_h4_side_response_packet_consumer: bool = False,
    v10_h4_side_response_packet_consumer_manifest: str | Path | None = None,
    v10_h4_side_response_packet_consumer_manifest_sha256: str | None = None,
    v10_h4_side_response_packet_full_producer: bool = False,
    v10_h4_side_response_packet_full_producer_exact_spool_root: str
    | Path
    | None = None,
    v10_h4_side_response_packet_full_producer_output_root: str | Path | None = None,
    v10_h4_side_response_packet_compression: bool = False,
    v10_h4_side_response_packet_compression_manifest: str | Path | None = None,
    v10_h4_side_response_packet_compression_manifest_sha256: str | None = None,
    v10_h4_side_response_packet_compression_producer_source_sha: str | None = None,
    v11_h4_bottom_packet_algebra: bool = False,
    v11_h4_bottom_packet_algebra_exact_spool_root: str | Path | None = None,
    v11_h4_bottom_packet_algebra_packet_manifest: str | Path | None = None,
    v11_h4_bottom_packet_algebra_packet_manifest_sha256: str | None = None,
    v11_h4_bottom_packet_algebra_producer_diagnostic: str | Path | None = None,
    v8_h4_layer_sweep_exact_spool_root: str | Path | None = None,
    v5_h4_blr_profile: str = MUMPS_BLR_V5_H4_PROFILE,
    selected_mode_packet_manifest: str | Path | None = None,
    selected_mode_packet_identity: str | Path | None = None,
    selected_mode_packet_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """Describe the opt-in worker command consumed by the existing watchdog."""

    if (
        v5_h4_setup_only
        or v5_h4_blr_side_only
        or v5_h4_fixed_budget_bottom_only
        or v6_h4_post_compaction_setup_only
        or v7_h4_exact_side_limit_setup_only
        or v7_h4_exact_side_full_formal
        or v6_h4_port_modal_bottom_only
        or v7_h4_streamed_bottom_producer
        or v7_h4_streamed_bottom_consumer
        or v8_h4_layer_block_reconstruction
        or v8_h4_layer_sweep_bottom
        or v9_h4_bare_f_side
        or v9_h4_layer_supernode_bottom
        or v10_h4_supernode_factor_integrity
        or v10_h4_sn2_j_only
        or v10_h4_j1_inner_fgmres
        or v10_h4_side_response_packet_full_producer
        or v10_h4_side_response_packet_compression
        or v10_h4_side_response_packet_pilot
        or v10_h4_side_response_packet_consumer
        or v11_h4_bottom_packet_algebra
    ):
        specification = load_and_resolve(input_path)
        from benchmarks.task039_v4_h4_hybrid_direct import (
            validate_v4_h4_specification,
        )

        validate_v4_h4_specification(specification)
        if specification.method.get("kind") != "hybrid_iterative":
            raise ValueError("V5 h4 setup-only requires hybrid_iterative")
        payload = specification.as_jsonable()
    else:
        payload = load_v3_7_official_payload(input_path)
    if v5_h4_blr_side_only:
        v5_h4_blr_profile = _validate_v5_h4_blr_profile(v5_h4_blr_profile)
    policy = v3_7_watchdog_policy(
        payload,
        v6_h4_post_compaction_setup_only=v6_h4_post_compaction_setup_only,
        v7_h4_exact_side_limit_setup_only=v7_h4_exact_side_limit_setup_only,
        v7_h4_exact_side_full_formal=v7_h4_exact_side_full_formal,
        v6_h4_port_modal_bottom_only=v6_h4_port_modal_bottom_only,
        v7_h4_streamed_bottom_producer=v7_h4_streamed_bottom_producer,
        v7_h4_streamed_bottom_consumer=v7_h4_streamed_bottom_consumer,
        v8_h4_layer_block_reconstruction=v8_h4_layer_block_reconstruction,
        v8_h4_layer_sweep_bottom=v8_h4_layer_sweep_bottom,
        v9_h4_bare_f_side=v9_h4_bare_f_side,
        v9_h4_layer_supernode_bottom=v9_h4_layer_supernode_bottom,
        v10_h4_supernode_factor_integrity=v10_h4_supernode_factor_integrity,
        v10_h4_sn2_j_only=v10_h4_sn2_j_only,
        v10_h4_j1_inner_fgmres=v10_h4_j1_inner_fgmres,
        v10_h4_side_response_packet_pilot=v10_h4_side_response_packet_pilot,
        v10_h4_side_response_packet_consumer=v10_h4_side_response_packet_consumer,
        v10_h4_side_response_packet_full_producer=v10_h4_side_response_packet_full_producer,
        v10_h4_side_response_packet_compression=v10_h4_side_response_packet_compression,
        v11_h4_bottom_packet_algebra=v11_h4_bottom_packet_algebra,
    )
    if (
        sum(
            (
                bool(candidate_b_only),
                bool(candidate_c_only),
                bool(candidate_d_only),
                bool(candidate_d_qualified),
                bool(candidate_e_side_only),
                bool(v5_h4_setup_only),
                bool(v5_h4_blr_side_only),
                bool(v5_h4_fixed_budget_bottom_only),
                bool(v6_h4_post_compaction_setup_only),
                bool(v7_h4_exact_side_limit_setup_only),
                bool(v7_h4_exact_side_full_formal),
                bool(v6_h4_port_modal_bottom_only),
                bool(v7_h4_streamed_bottom_producer),
                bool(v7_h4_streamed_bottom_consumer),
                bool(v8_h4_layer_block_reconstruction),
                bool(v8_h4_layer_sweep_bottom),
                bool(v9_h4_bare_f_side),
                bool(v9_h4_layer_supernode_bottom),
                bool(v10_h4_supernode_factor_integrity),
                bool(v10_h4_sn2_j_only),
                bool(v10_h4_j1_inner_fgmres),
                bool(v10_h4_side_response_packet_pilot),
                bool(v10_h4_side_response_packet_consumer),
                bool(v10_h4_side_response_packet_full_producer),
                bool(v10_h4_side_response_packet_compression),
                bool(v11_h4_bottom_packet_algebra),
            )
        )
        > 1
    ):
        raise ValueError(
            "Candidate routes, V5 h4 setup-only, BLR, and fixed-budget routes are exclusive"
        )
    executable = str(Path(os.path.abspath(python_executable or sys.executable)))
    mpiexec = mpiexec_command or shutil.which("mpiexec") or "mpiexec"
    argv = [
        str(mpiexec),
        "-n",
        "8",
        executable,
        "-m",
        "benchmarks.task039_v3_7_orchestration",
        "--worker",
        "--input",
        str(Path(input_path).resolve()),
        "--run-directory",
        str(Path(run_directory).resolve()),
        "--source-sha",
        source_sha,
        V3_7_WATCHDOG_AUTH_FLAG,
    ]
    if candidate_b_only:
        argv.append("--candidate-b-only")
    if candidate_c_only:
        argv.append("--candidate-c-only")
    if candidate_d_only:
        argv.append("--candidate-d-only")
    if candidate_d_qualified:
        argv.append("--candidate-d-qualified")
    if candidate_e_side_only:
        argv.append("--candidate-e-side-only")
    if (
        v5_h4_setup_only
        or v5_h4_blr_side_only
        or v5_h4_fixed_budget_bottom_only
        or v6_h4_post_compaction_setup_only
        or v7_h4_exact_side_limit_setup_only
        or v7_h4_exact_side_full_formal
        or v6_h4_port_modal_bottom_only
        or v7_h4_streamed_bottom_producer
        or v7_h4_streamed_bottom_consumer
        or v8_h4_layer_block_reconstruction
        or v8_h4_layer_sweep_bottom
        or v9_h4_bare_f_side
        or v9_h4_layer_supernode_bottom
        or v10_h4_supernode_factor_integrity
        or v10_h4_sn2_j_only
        or v10_h4_j1_inner_fgmres
        or v10_h4_side_response_packet_compression
        or v11_h4_bottom_packet_algebra
    ):
        if (
            not v8_h4_layer_block_reconstruction
            and not v9_h4_bare_f_side
            and not v9_h4_layer_supernode_bottom
            and not v10_h4_supernode_factor_integrity
            and not v10_h4_sn2_j_only
            and not v10_h4_j1_inner_fgmres
            and not v10_h4_side_response_packet_full_producer
            and not v10_h4_side_response_packet_compression
            and not v11_h4_bottom_packet_algebra
            and not all(
                (
                    selected_mode_packet_manifest,
                    selected_mode_packet_identity,
                    selected_mode_packet_manifest_sha256,
                )
            )
        ):
            raise ValueError("V5 h4 setup-only requires the shared packet arguments")
        if v7_h4_exact_side_full_formal:
            component_flag = "--v7-h4-exact-side-full-formal"
        elif v7_h4_exact_side_limit_setup_only:
            component_flag = "--v7-h4-exact-side-limit-setup-only"
        elif v6_h4_post_compaction_setup_only:
            component_flag = "--v6-h4-post-compaction-setup-only"
        elif v6_h4_port_modal_bottom_only:
            component_flag = "--v6-h4-port-modal-bottom-component"
        elif v7_h4_streamed_bottom_producer:
            component_flag = "--v7-h4-streamed-bottom-producer"
        elif v7_h4_streamed_bottom_consumer:
            component_flag = "--v7-h4-streamed-bottom-consumer"
        elif v8_h4_layer_block_reconstruction:
            component_flag = "--v8-h4-layer-block-reconstruction"
        elif v8_h4_layer_sweep_bottom:
            component_flag = "--v8-h4-layer-sweep-bottom"
        elif v9_h4_bare_f_side:
            component_flag = "--v9-h4-bare-f-full-side-diagnostic"
        elif v9_h4_layer_supernode_bottom:
            component_flag = V9_H4_LAYER_SUPERNODE_BOTTOM_FLAG
        elif v10_h4_supernode_factor_integrity:
            component_flag = V10_H4_SUPERNODE_FACTOR_INTEGRITY_FLAG
        elif v10_h4_sn2_j_only:
            component_flag = V10_H4_SN2_J_ONLY_FLAG
        elif v10_h4_j1_inner_fgmres:
            component_flag = V10_H4_J1_INNER_FGMRES_FLAG
        elif v10_h4_side_response_packet_full_producer:
            component_flag = V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_FLAG
        elif v10_h4_side_response_packet_compression:
            component_flag = V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_FLAG
        elif v11_h4_bottom_packet_algebra:
            component_flag = V11_BOTTOM_PACKET_ALGEBRA_FLAG
        elif v10_h4_side_response_packet_pilot:
            component_flag = V10_H4_SIDE_RESPONSE_PACKET_PILOT_FLAG
        elif v10_h4_side_response_packet_consumer:
            component_flag = V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_FLAG
        elif v5_h4_setup_only:
            component_flag = "--v5-h4-setup-only"
        elif v5_h4_blr_side_only:
            component_flag = "--v5-h4-blr-side-component"
        else:
            component_flag = "--v5-h4-fixed-budget-bottom-component"
        argv.append(component_flag)
        if (
            not v8_h4_layer_block_reconstruction
            and not v9_h4_bare_f_side
            and not v9_h4_layer_supernode_bottom
            and not v10_h4_supernode_factor_integrity
            and not v10_h4_sn2_j_only
            and not v10_h4_j1_inner_fgmres
            and not v10_h4_side_response_packet_pilot
            and not v10_h4_side_response_packet_consumer
            and not v10_h4_side_response_packet_full_producer
            and not v10_h4_side_response_packet_compression
            and not v11_h4_bottom_packet_algebra
        ):
            argv.extend(
                [
                    "--selected-mode-packet-manifest",
                    str(Path(selected_mode_packet_manifest).resolve()),
                    "--selected-mode-packet-identity",
                    str(Path(selected_mode_packet_identity).resolve()),
                    "--selected-mode-packet-manifest-sha256",
                    str(selected_mode_packet_manifest_sha256),
                ]
            )
        if v5_h4_blr_side_only and v5_h4_blr_profile != MUMPS_BLR_V5_H4_PROFILE:
            argv.extend(["--v5-h4-blr-profile", v5_h4_blr_profile])
        if v7_h4_exact_side_full_formal or v7_h4_exact_side_limit_setup_only:
            if v7_h4_exact_side_exact_spool_root is None:
                raise ValueError("V7 exact-side route requires the exact spool root")
            argv.extend(
                [
                    "--v7-h4-exact-side-exact-spool-root",
                    str(Path(v7_h4_exact_side_exact_spool_root).resolve()),
                ]
            )
        elif v6_h4_post_compaction_setup_only:
            if v6_h4_exact_spool_root is None:
                raise ValueError("V6 setup requires the exact spool root")
            argv.extend(
                [
                    "--v6-h4-exact-spool-root",
                    str(Path(v6_h4_exact_spool_root).resolve()),
                ]
            )
        elif v6_h4_port_modal_bottom_only:
            if v6_h4_port_modal_exact_spool_root is None:
                raise ValueError("V6 port-modal route requires the exact spool root")
            argv.extend(
                [
                    "--v6-h4-port-modal-exact-spool-root",
                    str(Path(v6_h4_port_modal_exact_spool_root).resolve()),
                ]
            )
        elif v5_h4_fixed_budget_bottom_only:
            if v5_h4_fixed_budget_exact_spool_root is None:
                raise ValueError("Fixed-budget route requires the exact spool root")
            argv.extend(
                [
                    "--v5-h4-fixed-budget-exact-spool-root",
                    str(Path(v5_h4_fixed_budget_exact_spool_root).resolve()),
                ]
            )
        elif v7_h4_streamed_bottom_consumer:
            if not all(
                (
                    v7_h4_streamed_bottom_consumer_basis_manifest,
                    v7_h4_streamed_bottom_consumer_basis_manifest_sha256,
                    v7_h4_streamed_bottom_consumer_exact_spool_root,
                )
            ):
                raise ValueError(
                    "V7 streamed consumer requires basis manifest, hash, and exact spool"
                )
            argv.extend(
                [
                    "--v7-h4-streamed-bottom-consumer-basis-manifest",
                    str(Path(v7_h4_streamed_bottom_consumer_basis_manifest).resolve()),
                    "--v7-h4-streamed-bottom-consumer-basis-manifest-sha256",
                    str(v7_h4_streamed_bottom_consumer_basis_manifest_sha256),
                    "--v7-h4-streamed-bottom-consumer-exact-spool-root",
                    str(
                        Path(v7_h4_streamed_bottom_consumer_exact_spool_root).resolve()
                    ),
                ]
            )
        elif v8_h4_layer_sweep_bottom:
            if v8_h4_layer_sweep_exact_spool_root is None:
                raise ValueError("V8 layer sweep route requires the exact spool root")
            argv.extend(
                [
                    "--v8-h4-layer-sweep-exact-spool-root",
                    str(Path(v8_h4_layer_sweep_exact_spool_root).resolve()),
                ]
            )
        elif v9_h4_bare_f_side:
            if v9_h4_bare_f_side_exact_spool_root is None:
                raise ValueError("V9 bare-F route requires the exact spool root")
            argv.extend(
                [
                    "--v9-h4-bare-f-full-side-exact-spool-root",
                    str(Path(v9_h4_bare_f_side_exact_spool_root).resolve()),
                ]
            )
        elif v9_h4_layer_supernode_bottom:
            if v9_h4_layer_supernode_exact_spool_root is None:
                raise ValueError("V9-2 route requires the exact spool root")
            argv.extend(
                [
                    V9_H4_LAYER_SUPERNODE_EXACT_SPOOL_ROOT_FLAG,
                    str(Path(v9_h4_layer_supernode_exact_spool_root).resolve()),
                ]
            )
        elif v10_h4_supernode_factor_integrity:
            if v10_h4_supernode_factor_integrity_exact_spool_root is None:
                raise ValueError("V10 forensic route requires the exact spool root")
            argv.extend(
                [
                    V10_H4_SUPERNODE_FACTOR_INTEGRITY_EXACT_SPOOL_ROOT_FLAG,
                    str(
                        Path(
                            v10_h4_supernode_factor_integrity_exact_spool_root
                        ).resolve()
                    ),
                ]
            )
        elif v10_h4_sn2_j_only:
            if v10_h4_sn2_j_only_exact_spool_root is None:
                raise ValueError("V10 SN2-J-only route requires the exact spool root")
            argv.extend(
                [
                    V10_H4_SN2_J_ONLY_EXACT_SPOOL_ROOT_FLAG,
                    str(Path(v10_h4_sn2_j_only_exact_spool_root).resolve()),
                ]
            )
        elif v10_h4_j1_inner_fgmres:
            if v10_h4_j1_inner_fgmres_exact_spool_root is None:
                raise ValueError("V10-4 route requires the exact spool root")
            argv.extend(
                [
                    V10_H4_J1_INNER_FGMRES_EXACT_SPOOL_ROOT_FLAG,
                    str(Path(v10_h4_j1_inner_fgmres_exact_spool_root).resolve()),
                ]
            )
        elif v10_h4_side_response_packet_pilot:
            if (
                v10_h4_side_response_packet_pilot_exact_spool_root is None
                or v10_h4_side_response_packet_pilot_output_root is None
            ):
                raise ValueError("V10-6 producer requires exact spool and output roots")
            argv.extend(
                [
                    V10_H4_SIDE_RESPONSE_PACKET_PILOT_EXACT_SPOOL_ROOT_FLAG,
                    str(
                        Path(
                            v10_h4_side_response_packet_pilot_exact_spool_root
                        ).resolve()
                    ),
                    V10_H4_SIDE_RESPONSE_PACKET_PILOT_OUTPUT_ROOT_FLAG,
                    str(Path(v10_h4_side_response_packet_pilot_output_root).resolve()),
                ]
            )
        elif v10_h4_side_response_packet_consumer:
            if (
                v10_h4_side_response_packet_consumer_manifest is None
                or v10_h4_side_response_packet_consumer_manifest_sha256 is None
            ):
                raise ValueError("V10-6 consumer requires manifest and hash")
            argv.extend(
                [
                    V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_MANIFEST_FLAG,
                    str(Path(v10_h4_side_response_packet_consumer_manifest).resolve()),
                    V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_MANIFEST_SHA256_FLAG,
                    str(v10_h4_side_response_packet_consumer_manifest_sha256),
                ]
            )
        elif v10_h4_side_response_packet_full_producer:
            if (
                v10_h4_side_response_packet_full_producer_exact_spool_root is None
                or v10_h4_side_response_packet_full_producer_output_root is None
            ):
                raise ValueError(
                    "V10-6 full producer requires exact spool and output roots"
                )
            argv.extend(
                [
                    V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_EXACT_SPOOL_ROOT_FLAG,
                    str(
                        Path(
                            v10_h4_side_response_packet_full_producer_exact_spool_root
                        ).resolve()
                    ),
                    V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_OUTPUT_ROOT_FLAG,
                    str(
                        Path(
                            v10_h4_side_response_packet_full_producer_output_root
                        ).resolve()
                    ),
                ]
            )
        elif v10_h4_side_response_packet_compression:
            if (
                v10_h4_side_response_packet_compression_manifest is None
                or v10_h4_side_response_packet_compression_manifest_sha256 is None
                or v10_h4_side_response_packet_compression_producer_source_sha is None
            ):
                raise ValueError(
                    "V10-6 compression requires manifest, hash, and producer source SHA"
                )
            argv.extend(
                [
                    V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_MANIFEST_FLAG,
                    str(
                        Path(v10_h4_side_response_packet_compression_manifest).resolve()
                    ),
                    V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_MANIFEST_SHA256_FLAG,
                    str(v10_h4_side_response_packet_compression_manifest_sha256),
                    V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_PRODUCER_SOURCE_SHA_FLAG,
                    str(v10_h4_side_response_packet_compression_producer_source_sha),
                ]
            )
        elif v11_h4_bottom_packet_algebra:
            if not all(
                (
                    selected_mode_packet_manifest,
                    selected_mode_packet_manifest_sha256,
                    v11_h4_bottom_packet_algebra_exact_spool_root,
                    v11_h4_bottom_packet_algebra_packet_manifest,
                    v11_h4_bottom_packet_algebra_packet_manifest_sha256,
                    v11_h4_bottom_packet_algebra_producer_diagnostic,
                )
            ):
                raise ValueError("V11 bottom algebra route requires frozen artifacts")
            argv.extend(
                [
                    "--selected-mode-packet-manifest",
                    str(Path(selected_mode_packet_manifest).resolve()),
                    "--selected-mode-packet-manifest-sha256",
                    str(selected_mode_packet_manifest_sha256),
                    V11_BOTTOM_PACKET_ALGEBRA_EXACT_SPOOL_ROOT_FLAG,
                    str(Path(v11_h4_bottom_packet_algebra_exact_spool_root).resolve()),
                    V11_BOTTOM_PACKET_ALGEBRA_PACKET_MANIFEST_FLAG,
                    str(Path(v11_h4_bottom_packet_algebra_packet_manifest).resolve()),
                    V11_BOTTOM_PACKET_ALGEBRA_PACKET_MANIFEST_SHA256_FLAG,
                    str(v11_h4_bottom_packet_algebra_packet_manifest_sha256),
                    V11_BOTTOM_PACKET_ALGEBRA_PRODUCER_DIAGNOSTIC_FLAG,
                    str(
                        Path(v11_h4_bottom_packet_algebra_producer_diagnostic).resolve()
                    ),
                ]
            )
    if v7_h4_exact_side_full_formal:
        method = V7_H4_EXACT_SIDE_FULL_FORMAL_METHOD
    elif v7_h4_exact_side_limit_setup_only:
        method = V7_H4_EXACT_SIDE_LIMIT_METHOD
    elif v6_h4_post_compaction_setup_only:
        method = V6_H4_POST_COMPACTION_METHOD
    elif v6_h4_port_modal_bottom_only:
        method = V6_H4_PORT_MODAL_BOTTOM_METHOD
    elif v7_h4_streamed_bottom_producer:
        method = V7_STREAMED_PETROV_METHOD
    elif v7_h4_streamed_bottom_consumer:
        method = V7_STREAMED_PETROV_CONSUMER_METHOD
    elif v8_h4_layer_block_reconstruction:
        method = V8_H4_LAYER_BLOCK_METHOD
    elif v8_h4_layer_sweep_bottom:
        method = V8_H4_LAYER_SWEEP_METHOD
    elif v9_h4_bare_f_side:
        method = V9_H4_BARE_F_SIDE_METHOD
    elif v9_h4_layer_supernode_bottom:
        method = V9_H4_LAYER_SUPERNODE_METHOD
    elif v10_h4_supernode_factor_integrity:
        method = V10_H4_SUPERNODE_FACTOR_INTEGRITY_METHOD
    elif v10_h4_sn2_j_only:
        method = V10_H4_SN2_J_ONLY_METHOD
    elif v10_h4_j1_inner_fgmres:
        method = V10_H4_J1_INNER_FGMRES_METHOD
    elif v10_h4_side_response_packet_full_producer:
        method = V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_METHOD
    elif v10_h4_side_response_packet_compression:
        method = V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_METHOD
    elif v11_h4_bottom_packet_algebra:
        method = V11_BOTTOM_PACKET_ALGEBRA_METHOD
    elif v10_h4_side_response_packet_pilot:
        method = V10_H4_SIDE_RESPONSE_PACKET_PILOT_METHOD
    elif v10_h4_side_response_packet_consumer:
        method = V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_METHOD
    elif v5_h4_setup_only:
        method = "task039_v5_h4_exact_side_setup_only"
    elif v5_h4_blr_side_only:
        method = V5_H4_BLR_SIDE_METHOD
    elif v5_h4_fixed_budget_bottom_only:
        method = V5_H4_FIXED_BUDGET_SIDE_METHOD
    elif candidate_d_qualified:
        method = V3_8_CANDIDATE_D_QUALIFIED_METHOD
    elif candidate_d_only:
        method = V3_8_CANDIDATE_D_CLASSIFICATION
    elif candidate_e_side_only:
        method = "hybrid_iterative_candidate_e_side_only"
    elif candidate_c_only:
        method = "hybrid_iterative_candidate_c1_only"
    elif candidate_b_only:
        method = "hybrid_iterative_candidate_b_only"
    else:
        method = "hybrid_iterative_v3_7_diagnostic"
    if v7_h4_exact_side_full_formal:
        profile_id = V7_H4_EXACT_SIDE_FULL_FORMAL_PROFILE_ID
    elif v7_h4_exact_side_limit_setup_only:
        profile_id = V7_H4_EXACT_SIDE_LIMIT_PROFILE_ID
    elif v6_h4_post_compaction_setup_only:
        profile_id = V6_H4_POST_COMPACTION_PROFILE_ID
    elif v6_h4_port_modal_bottom_only:
        profile_id = V6_H4_PORT_MODAL_BOTTOM_PROFILE_ID
    elif v7_h4_streamed_bottom_producer:
        profile_id = V7_STREAMED_PETROV_PROFILE_ID
    elif v7_h4_streamed_bottom_consumer:
        profile_id = V7_STREAMED_PETROV_CONSUMER_PROFILE_ID
    elif v8_h4_layer_block_reconstruction:
        profile_id = V8_H4_LAYER_BLOCK_PROFILE_ID
    elif v8_h4_layer_sweep_bottom:
        profile_id = V8_H4_LAYER_SWEEP_PROFILE_ID
    elif v9_h4_bare_f_side:
        profile_id = V9_H4_BARE_F_SIDE_PROFILE_ID
    elif v9_h4_layer_supernode_bottom:
        profile_id = V9_H4_LAYER_SUPERNODE_PROFILE_ID
    elif v10_h4_supernode_factor_integrity:
        profile_id = V10_H4_SUPERNODE_FACTOR_INTEGRITY_PROFILE_ID
    elif v10_h4_sn2_j_only:
        profile_id = V10_H4_SN2_J_ONLY_PROFILE_ID
    elif v10_h4_j1_inner_fgmres:
        profile_id = V10_H4_J1_INNER_FGMRES_PROFILE_ID
    elif v10_h4_side_response_packet_full_producer:
        profile_id = V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_PROFILE_ID
    elif v10_h4_side_response_packet_compression:
        profile_id = V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_PROFILE_ID
    elif v11_h4_bottom_packet_algebra:
        profile_id = V11_BOTTOM_PACKET_ALGEBRA_PROFILE_ID
    elif v10_h4_side_response_packet_pilot:
        profile_id = V10_H4_SIDE_RESPONSE_PACKET_PILOT_PROFILE_ID
    elif v10_h4_side_response_packet_consumer:
        profile_id = V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_PROFILE_ID
    elif v5_h4_setup_only:
        profile_id = "task039.v5.h4.exact-side.setup-only.v1"
    elif v5_h4_blr_side_only:
        profile_id = V5_H4_BLR_SIDE_PROFILE_ID
    elif v5_h4_fixed_budget_bottom_only:
        profile_id = V5_H4_FIXED_BUDGET_SIDE_PROFILE_ID
    else:
        profile_id = V3_7_PROFILE_ID
    if (
        v7_h4_exact_side_limit_setup_only or v7_h4_exact_side_full_formal
    ) and v7_h4_exact_side_exact_spool_root is not None:
        exact_spool_root = str(Path(v7_h4_exact_side_exact_spool_root).resolve())
    elif v6_h4_post_compaction_setup_only and v6_h4_exact_spool_root is not None:
        exact_spool_root = str(Path(v6_h4_exact_spool_root).resolve())
    elif v6_h4_port_modal_bottom_only and v6_h4_port_modal_exact_spool_root is not None:
        exact_spool_root = str(Path(v6_h4_port_modal_exact_spool_root).resolve())
    elif (
        v5_h4_fixed_budget_bottom_only
        and v5_h4_fixed_budget_exact_spool_root is not None
    ):
        exact_spool_root = str(Path(v5_h4_fixed_budget_exact_spool_root).resolve())
    elif (
        v7_h4_streamed_bottom_consumer
        and v7_h4_streamed_bottom_consumer_exact_spool_root is not None
    ):
        exact_spool_root = str(
            Path(v7_h4_streamed_bottom_consumer_exact_spool_root).resolve()
        )
    elif v8_h4_layer_sweep_bottom and v8_h4_layer_sweep_exact_spool_root is not None:
        exact_spool_root = str(Path(v8_h4_layer_sweep_exact_spool_root).resolve())
    elif v9_h4_bare_f_side and v9_h4_bare_f_side_exact_spool_root is not None:
        exact_spool_root = str(Path(v9_h4_bare_f_side_exact_spool_root).resolve())
    elif (
        v9_h4_layer_supernode_bottom
        and v9_h4_layer_supernode_exact_spool_root is not None
    ):
        exact_spool_root = str(Path(v9_h4_layer_supernode_exact_spool_root).resolve())
    elif (
        v10_h4_supernode_factor_integrity
        and v10_h4_supernode_factor_integrity_exact_spool_root is not None
    ):
        exact_spool_root = str(
            Path(v10_h4_supernode_factor_integrity_exact_spool_root).resolve()
        )
    elif v10_h4_sn2_j_only and v10_h4_sn2_j_only_exact_spool_root is not None:
        exact_spool_root = str(Path(v10_h4_sn2_j_only_exact_spool_root).resolve())
    elif v10_h4_j1_inner_fgmres and v10_h4_j1_inner_fgmres_exact_spool_root is not None:
        exact_spool_root = str(Path(v10_h4_j1_inner_fgmres_exact_spool_root).resolve())
    elif (
        v10_h4_side_response_packet_pilot
        and v10_h4_side_response_packet_pilot_exact_spool_root is not None
    ):
        exact_spool_root = str(
            Path(v10_h4_side_response_packet_pilot_exact_spool_root).resolve()
        )
    elif (
        v10_h4_side_response_packet_full_producer
        and v10_h4_side_response_packet_full_producer_exact_spool_root is not None
    ):
        exact_spool_root = str(
            Path(v10_h4_side_response_packet_full_producer_exact_spool_root).resolve()
        )
    elif (
        v11_h4_bottom_packet_algebra
        and v11_h4_bottom_packet_algebra_exact_spool_root is not None
    ):
        exact_spool_root = str(
            Path(v11_h4_bottom_packet_algebra_exact_spool_root).resolve()
        )
    else:
        exact_spool_root = None
    return {
        "argv": argv,
        "shell": False,
        "launcher": "src.runners.task038_launcher",
        "watchdog": policy,
        "worker_contract": {
            "mpi_size": 8,
            "profile_id": profile_id,
            "method": method,
            "fixed_budget": (
                V5_H4_FIXED_BUDGET if v5_h4_fixed_budget_bottom_only else None
            ),
            "exact_spool_root": exact_spool_root,
            "basis_manifest": (
                None
                if v7_h4_streamed_bottom_consumer_basis_manifest is None
                else str(Path(v7_h4_streamed_bottom_consumer_basis_manifest).resolve())
            ),
            "basis_manifest_sha256": v7_h4_streamed_bottom_consumer_basis_manifest_sha256,
            "response_packet_output_root": (
                None
                if v10_h4_side_response_packet_pilot_output_root is None
                else str(Path(v10_h4_side_response_packet_pilot_output_root).resolve())
            ),
            "response_packet_manifest": (
                None
                if v10_h4_side_response_packet_consumer_manifest is None
                else str(Path(v10_h4_side_response_packet_consumer_manifest).resolve())
            ),
            "response_packet_manifest_sha256": v10_h4_side_response_packet_consumer_manifest_sha256,
            "response_packet_full_producer_output_root": (
                None
                if v10_h4_side_response_packet_full_producer_output_root is None
                else str(
                    Path(
                        v10_h4_side_response_packet_full_producer_output_root
                    ).resolve()
                )
            ),
            "response_packet_full_producer_exact_spool_root": (
                None
                if v10_h4_side_response_packet_full_producer_exact_spool_root is None
                else str(
                    Path(
                        v10_h4_side_response_packet_full_producer_exact_spool_root
                    ).resolve()
                )
            ),
            "response_packet_compression_manifest": (
                None
                if v10_h4_side_response_packet_compression_manifest is None
                else str(
                    Path(v10_h4_side_response_packet_compression_manifest).resolve()
                )
            ),
            "response_packet_compression_manifest_sha256": (
                v10_h4_side_response_packet_compression_manifest_sha256
            ),
            "response_packet_compression_producer_source_sha": (
                v10_h4_side_response_packet_compression_producer_source_sha
            ),
            "absolute_terminate_memory_bytes": policy[
                "absolute_terminate_memory_bytes"
            ],
            "mumps_blr_profile": (v5_h4_blr_profile if v5_h4_blr_side_only else None),
            "hard_stop_authority": "process_tree_rss_bytes",
            "critical_checkpoint_only": True,
            "swap_policy": "immediate_complete_process_tree_termination",
        },
    }


def v3_7_execution_dry_run(
    input_path: str | Path,
    run_directory: str | Path,
    *,
    source_sha: str,
    python_executable: str | Path | None = None,
    candidate_b_only: bool = False,
    candidate_c_only: bool = False,
    candidate_d_only: bool = False,
    candidate_d_qualified: bool = False,
    candidate_e_side_only: bool = False,
    v5_h4_setup_only: bool = False,
    v5_h4_blr_side_only: bool = False,
    v5_h4_fixed_budget_bottom_only: bool = False,
    v5_h4_fixed_budget_exact_spool_root: str | Path | None = None,
    v6_h4_post_compaction_setup_only: bool = False,
    v6_h4_exact_spool_root: str | Path | None = None,
    v7_h4_exact_side_limit_setup_only: bool = False,
    v7_h4_exact_side_exact_spool_root: str | Path | None = None,
    v6_h4_port_modal_bottom_only: bool = False,
    v6_h4_port_modal_exact_spool_root: str | Path | None = None,
    v7_h4_exact_side_full_formal: bool = False,
    v7_h4_streamed_bottom_producer: bool = False,
    v7_h4_streamed_bottom_consumer: bool = False,
    v7_h4_streamed_bottom_consumer_basis_manifest: str | Path | None = None,
    v7_h4_streamed_bottom_consumer_basis_manifest_sha256: str | None = None,
    v7_h4_streamed_bottom_consumer_exact_spool_root: str | Path | None = None,
    v8_h4_layer_block_reconstruction: bool = False,
    v8_h4_layer_sweep_bottom: bool = False,
    v9_h4_bare_f_side: bool = False,
    v9_h4_bare_f_side_exact_spool_root: str | Path | None = None,
    v9_h4_layer_supernode_bottom: bool = False,
    v9_h4_layer_supernode_exact_spool_root: str | Path | None = None,
    v10_h4_supernode_factor_integrity: bool = False,
    v10_h4_supernode_factor_integrity_exact_spool_root: str | Path | None = None,
    v10_h4_sn2_j_only: bool = False,
    v10_h4_sn2_j_only_exact_spool_root: str | Path | None = None,
    v10_h4_j1_inner_fgmres: bool = False,
    v10_h4_j1_inner_fgmres_exact_spool_root: str | Path | None = None,
    v10_h4_side_response_packet_pilot: bool = False,
    v10_h4_side_response_packet_pilot_exact_spool_root: str | Path | None = None,
    v10_h4_side_response_packet_pilot_output_root: str | Path | None = None,
    v10_h4_side_response_packet_consumer: bool = False,
    v10_h4_side_response_packet_consumer_manifest: str | Path | None = None,
    v10_h4_side_response_packet_consumer_manifest_sha256: str | None = None,
    v10_h4_side_response_packet_full_producer: bool = False,
    v10_h4_side_response_packet_full_producer_exact_spool_root: str
    | Path
    | None = None,
    v10_h4_side_response_packet_full_producer_output_root: str | Path | None = None,
    v10_h4_side_response_packet_compression: bool = False,
    v10_h4_side_response_packet_compression_manifest: str | Path | None = None,
    v10_h4_side_response_packet_compression_manifest_sha256: str | None = None,
    v10_h4_side_response_packet_compression_producer_source_sha: str | None = None,
    v11_h4_bottom_packet_algebra: bool = False,
    v11_h4_bottom_packet_algebra_exact_spool_root: str | Path | None = None,
    v11_h4_bottom_packet_algebra_packet_manifest: str | Path | None = None,
    v11_h4_bottom_packet_algebra_packet_manifest_sha256: str | None = None,
    v11_h4_bottom_packet_algebra_producer_diagnostic: str | Path | None = None,
    v8_h4_layer_sweep_exact_spool_root: str | Path | None = None,
    v5_h4_blr_profile: str = MUMPS_BLR_V5_H4_PROFILE,
    selected_mode_packet_manifest: str | Path | None = None,
    selected_mode_packet_identity: str | Path | None = None,
    selected_mode_packet_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """Return the non-mutating pre-heavy command and watchdog contract."""

    plan = build_v3_7_execution_plan(
        input_path,
        run_directory,
        source_sha=source_sha,
        python_executable=python_executable,
        candidate_b_only=candidate_b_only,
        candidate_c_only=candidate_c_only,
        candidate_d_only=candidate_d_only,
        candidate_d_qualified=candidate_d_qualified,
        candidate_e_side_only=candidate_e_side_only,
        v5_h4_setup_only=v5_h4_setup_only,
        v5_h4_blr_side_only=v5_h4_blr_side_only,
        v5_h4_fixed_budget_bottom_only=v5_h4_fixed_budget_bottom_only,
        v5_h4_fixed_budget_exact_spool_root=v5_h4_fixed_budget_exact_spool_root,
        v6_h4_post_compaction_setup_only=v6_h4_post_compaction_setup_only,
        v6_h4_exact_spool_root=v6_h4_exact_spool_root,
        v7_h4_exact_side_limit_setup_only=v7_h4_exact_side_limit_setup_only,
        v7_h4_exact_side_exact_spool_root=v7_h4_exact_side_exact_spool_root,
        v6_h4_port_modal_bottom_only=v6_h4_port_modal_bottom_only,
        v6_h4_port_modal_exact_spool_root=v6_h4_port_modal_exact_spool_root,
        v7_h4_exact_side_full_formal=v7_h4_exact_side_full_formal,
        v7_h4_streamed_bottom_producer=v7_h4_streamed_bottom_producer,
        v7_h4_streamed_bottom_consumer=v7_h4_streamed_bottom_consumer,
        v7_h4_streamed_bottom_consumer_basis_manifest=(
            v7_h4_streamed_bottom_consumer_basis_manifest
        ),
        v7_h4_streamed_bottom_consumer_basis_manifest_sha256=(
            v7_h4_streamed_bottom_consumer_basis_manifest_sha256
        ),
        v7_h4_streamed_bottom_consumer_exact_spool_root=(
            v7_h4_streamed_bottom_consumer_exact_spool_root
        ),
        v8_h4_layer_block_reconstruction=v8_h4_layer_block_reconstruction,
        v8_h4_layer_sweep_bottom=v8_h4_layer_sweep_bottom,
        v9_h4_bare_f_side=v9_h4_bare_f_side,
        v9_h4_bare_f_side_exact_spool_root=v9_h4_bare_f_side_exact_spool_root,
        v9_h4_layer_supernode_bottom=v9_h4_layer_supernode_bottom,
        v9_h4_layer_supernode_exact_spool_root=(v9_h4_layer_supernode_exact_spool_root),
        v10_h4_supernode_factor_integrity=v10_h4_supernode_factor_integrity,
        v10_h4_supernode_factor_integrity_exact_spool_root=(
            v10_h4_supernode_factor_integrity_exact_spool_root
        ),
        v10_h4_sn2_j_only=v10_h4_sn2_j_only,
        v10_h4_sn2_j_only_exact_spool_root=v10_h4_sn2_j_only_exact_spool_root,
        v10_h4_j1_inner_fgmres=v10_h4_j1_inner_fgmres,
        v10_h4_j1_inner_fgmres_exact_spool_root=(
            v10_h4_j1_inner_fgmres_exact_spool_root
        ),
        v10_h4_side_response_packet_pilot=v10_h4_side_response_packet_pilot,
        v10_h4_side_response_packet_pilot_exact_spool_root=(
            v10_h4_side_response_packet_pilot_exact_spool_root
        ),
        v10_h4_side_response_packet_pilot_output_root=(
            v10_h4_side_response_packet_pilot_output_root
        ),
        v10_h4_side_response_packet_consumer=v10_h4_side_response_packet_consumer,
        v10_h4_side_response_packet_consumer_manifest=(
            v10_h4_side_response_packet_consumer_manifest
        ),
        v10_h4_side_response_packet_consumer_manifest_sha256=(
            v10_h4_side_response_packet_consumer_manifest_sha256
        ),
        v10_h4_side_response_packet_full_producer=v10_h4_side_response_packet_full_producer,
        v10_h4_side_response_packet_full_producer_exact_spool_root=(
            v10_h4_side_response_packet_full_producer_exact_spool_root
        ),
        v10_h4_side_response_packet_full_producer_output_root=(
            v10_h4_side_response_packet_full_producer_output_root
        ),
        v10_h4_side_response_packet_compression=v10_h4_side_response_packet_compression,
        v10_h4_side_response_packet_compression_manifest=(
            v10_h4_side_response_packet_compression_manifest
        ),
        v10_h4_side_response_packet_compression_manifest_sha256=(
            v10_h4_side_response_packet_compression_manifest_sha256
        ),
        v10_h4_side_response_packet_compression_producer_source_sha=(
            v10_h4_side_response_packet_compression_producer_source_sha
        ),
        v11_h4_bottom_packet_algebra=v11_h4_bottom_packet_algebra,
        v11_h4_bottom_packet_algebra_exact_spool_root=(
            v11_h4_bottom_packet_algebra_exact_spool_root
        ),
        v11_h4_bottom_packet_algebra_packet_manifest=(
            v11_h4_bottom_packet_algebra_packet_manifest
        ),
        v11_h4_bottom_packet_algebra_packet_manifest_sha256=(
            v11_h4_bottom_packet_algebra_packet_manifest_sha256
        ),
        v11_h4_bottom_packet_algebra_producer_diagnostic=(
            v11_h4_bottom_packet_algebra_producer_diagnostic
        ),
        v8_h4_layer_sweep_exact_spool_root=v8_h4_layer_sweep_exact_spool_root,
        v5_h4_blr_profile=v5_h4_blr_profile,
        selected_mode_packet_manifest=selected_mode_packet_manifest,
        selected_mode_packet_identity=selected_mode_packet_identity,
        selected_mode_packet_manifest_sha256=selected_mode_packet_manifest_sha256,
    )
    argv = plan["argv"]
    if argv[1:3] != ["-n", "8"] or plan["watchdog"]["critical_action"] != (
        "record_checkpoint_only"
    ):
        raise ValueError("V3-7 execution plan is not the fixed MPI8 watchdog contract")
    return plan


def launch_v3_7_with_task038_watchdog(
    input_path: str | Path,
    run_directory: str | Path,
    *,
    source_sha: str,
    python_executable: str | Path | None = None,
    mpiexec_command: str | None = None,
    popen_factory: Callable[..., Any] | None = None,
    sample_factory: Callable[[int], dict[str, Any]] | None = None,
    terminate_factory: Callable[[Any], dict[str, Any]] | None = None,
    candidate_b_only: bool = False,
    candidate_c_only: bool = False,
    candidate_d_only: bool = False,
    candidate_d_qualified: bool = False,
    candidate_e_side_only: bool = False,
    v5_h4_setup_only: bool = False,
    v5_h4_blr_side_only: bool = False,
    v5_h4_fixed_budget_bottom_only: bool = False,
    v5_h4_fixed_budget_exact_spool_root: str | Path | None = None,
    v6_h4_post_compaction_setup_only: bool = False,
    v6_h4_exact_spool_root: str | Path | None = None,
    v7_h4_exact_side_limit_setup_only: bool = False,
    v7_h4_exact_side_exact_spool_root: str | Path | None = None,
    v6_h4_port_modal_bottom_only: bool = False,
    v6_h4_port_modal_exact_spool_root: str | Path | None = None,
    v7_h4_exact_side_full_formal: bool = False,
    v7_h4_streamed_bottom_producer: bool = False,
    v7_h4_streamed_bottom_consumer: bool = False,
    v7_h4_streamed_bottom_consumer_basis_manifest: str | Path | None = None,
    v7_h4_streamed_bottom_consumer_basis_manifest_sha256: str | None = None,
    v7_h4_streamed_bottom_consumer_exact_spool_root: str | Path | None = None,
    v8_h4_layer_block_reconstruction: bool = False,
    v8_h4_layer_sweep_bottom: bool = False,
    v9_h4_bare_f_side: bool = False,
    v9_h4_bare_f_side_exact_spool_root: str | Path | None = None,
    v9_h4_layer_supernode_bottom: bool = False,
    v9_h4_layer_supernode_exact_spool_root: str | Path | None = None,
    v10_h4_supernode_factor_integrity: bool = False,
    v10_h4_supernode_factor_integrity_exact_spool_root: str | Path | None = None,
    v10_h4_sn2_j_only: bool = False,
    v10_h4_sn2_j_only_exact_spool_root: str | Path | None = None,
    v10_h4_j1_inner_fgmres: bool = False,
    v10_h4_j1_inner_fgmres_exact_spool_root: str | Path | None = None,
    v10_h4_side_response_packet_pilot: bool = False,
    v10_h4_side_response_packet_pilot_exact_spool_root: str | Path | None = None,
    v10_h4_side_response_packet_pilot_output_root: str | Path | None = None,
    v10_h4_side_response_packet_consumer: bool = False,
    v10_h4_side_response_packet_consumer_manifest: str | Path | None = None,
    v10_h4_side_response_packet_consumer_manifest_sha256: str | None = None,
    v8_h4_layer_sweep_exact_spool_root: str | Path | None = None,
    v5_h4_blr_profile: str = MUMPS_BLR_V5_H4_PROFILE,
    selected_mode_packet_manifest: str | Path | None = None,
    selected_mode_packet_identity: str | Path | None = None,
    selected_mode_packet_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """Run the opt-in child through Task38's existing process-tree watchdog."""

    if (
        v5_h4_setup_only
        or v5_h4_blr_side_only
        or v5_h4_fixed_budget_bottom_only
        or v6_h4_post_compaction_setup_only
        or v7_h4_exact_side_limit_setup_only
        or v7_h4_exact_side_full_formal
        or v6_h4_port_modal_bottom_only
        or v7_h4_streamed_bottom_producer
        or v7_h4_streamed_bottom_consumer
        or v8_h4_layer_block_reconstruction
        or v8_h4_layer_sweep_bottom
        or v9_h4_bare_f_side
        or v10_h4_supernode_factor_integrity
        or v10_h4_sn2_j_only
    ):
        specification = load_and_resolve(input_path)
        from benchmarks.task039_v4_h4_hybrid_direct import (
            validate_v4_h4_specification,
        )

        validate_v4_h4_specification(specification)
        payload = specification.as_jsonable()
    else:
        payload = load_v3_7_official_payload(input_path)
    if (
        not v5_h4_setup_only
        and not v5_h4_blr_side_only
        and not v5_h4_fixed_budget_bottom_only
        and not v6_h4_post_compaction_setup_only
        and not v7_h4_exact_side_limit_setup_only
        and not v7_h4_exact_side_full_formal
        and not v6_h4_port_modal_bottom_only
        and not v7_h4_streamed_bottom_producer
        and not v7_h4_streamed_bottom_consumer
        and not v8_h4_layer_block_reconstruction
        and not v8_h4_layer_sweep_bottom
        and not v9_h4_bare_f_side
        and not v9_h4_layer_supernode_bottom
        and not v10_h4_supernode_factor_integrity
        and not v10_h4_sn2_j_only
        and not v10_h4_j1_inner_fgmres
        and not V3_7_DIRECT_RUN_ROOT.is_dir()
    ):
        raise ValueError("V3-7 direct producer inventory is unavailable")
    if (
        not v5_h4_blr_side_only
        and not v5_h4_fixed_budget_bottom_only
        and not v6_h4_post_compaction_setup_only
        and not v7_h4_exact_side_limit_setup_only
        and not v7_h4_exact_side_full_formal
        and not v6_h4_port_modal_bottom_only
        and not v7_h4_streamed_bottom_producer
        and not v7_h4_streamed_bottom_consumer
        and not v8_h4_layer_block_reconstruction
        and not v8_h4_layer_sweep_bottom
        and not v9_h4_layer_supernode_bottom
        and not v10_h4_supernode_factor_integrity
        and not v10_h4_sn2_j_only
        and not v10_h4_j1_inner_fgmres
        and not callable(compare_v3_7_hybrid_candidate_to_direct)
    ):
        raise ValueError("V3-7 integrated checker entry point is unavailable")
    if len(source_sha) != 40 or any(
        character not in "0123456789abcdef" for character in source_sha.lower()
    ):
        raise ValueError("V3-7 source_sha must be a full hexadecimal commit SHA")
    if (
        not v5_h4_setup_only
        and not v5_h4_blr_side_only
        and not v5_h4_fixed_budget_bottom_only
        and not v6_h4_post_compaction_setup_only
        and not v7_h4_exact_side_limit_setup_only
        and not v7_h4_exact_side_full_formal
        and not v6_h4_port_modal_bottom_only
        and not v7_h4_streamed_bottom_producer
        and not v8_h4_layer_block_reconstruction
        and not v9_h4_bare_f_side
        and not v9_h4_layer_supernode_bottom
        and not v10_h4_supernode_factor_integrity
        and not v10_h4_sn2_j_only
        and not v10_h4_j1_inner_fgmres
        and not candidate_d_only
        and not candidate_d_qualified
    ):
        load_v3_7_direct_inventory(payload, V3_7_DIRECT_RUN_ROOT)
    specification = load_and_resolve(input_path)
    plan_payload = build_v3_7_execution_plan(
        input_path,
        run_directory,
        source_sha=source_sha,
        python_executable=python_executable,
        mpiexec_command=mpiexec_command,
        candidate_b_only=candidate_b_only,
        candidate_c_only=candidate_c_only,
        candidate_d_only=candidate_d_only,
        candidate_d_qualified=candidate_d_qualified,
        candidate_e_side_only=candidate_e_side_only,
        v5_h4_setup_only=v5_h4_setup_only,
        v5_h4_blr_side_only=v5_h4_blr_side_only,
        v5_h4_fixed_budget_bottom_only=v5_h4_fixed_budget_bottom_only,
        v5_h4_fixed_budget_exact_spool_root=v5_h4_fixed_budget_exact_spool_root,
        v6_h4_post_compaction_setup_only=v6_h4_post_compaction_setup_only,
        v6_h4_exact_spool_root=v6_h4_exact_spool_root,
        v7_h4_exact_side_limit_setup_only=v7_h4_exact_side_limit_setup_only,
        v7_h4_exact_side_exact_spool_root=v7_h4_exact_side_exact_spool_root,
        v6_h4_port_modal_bottom_only=v6_h4_port_modal_bottom_only,
        v6_h4_port_modal_exact_spool_root=v6_h4_port_modal_exact_spool_root,
        v7_h4_exact_side_full_formal=v7_h4_exact_side_full_formal,
        v7_h4_streamed_bottom_producer=v7_h4_streamed_bottom_producer,
        v7_h4_streamed_bottom_consumer=v7_h4_streamed_bottom_consumer,
        v7_h4_streamed_bottom_consumer_basis_manifest=(
            v7_h4_streamed_bottom_consumer_basis_manifest
        ),
        v7_h4_streamed_bottom_consumer_basis_manifest_sha256=(
            v7_h4_streamed_bottom_consumer_basis_manifest_sha256
        ),
        v7_h4_streamed_bottom_consumer_exact_spool_root=(
            v7_h4_streamed_bottom_consumer_exact_spool_root
        ),
        v8_h4_layer_block_reconstruction=v8_h4_layer_block_reconstruction,
        v8_h4_layer_sweep_bottom=v8_h4_layer_sweep_bottom,
        v9_h4_bare_f_side=v9_h4_bare_f_side,
        v9_h4_bare_f_side_exact_spool_root=v9_h4_bare_f_side_exact_spool_root,
        v9_h4_layer_supernode_bottom=v9_h4_layer_supernode_bottom,
        v9_h4_layer_supernode_exact_spool_root=(v9_h4_layer_supernode_exact_spool_root),
        v10_h4_supernode_factor_integrity=v10_h4_supernode_factor_integrity,
        v10_h4_supernode_factor_integrity_exact_spool_root=(
            v10_h4_supernode_factor_integrity_exact_spool_root
        ),
        v10_h4_sn2_j_only=v10_h4_sn2_j_only,
        v10_h4_sn2_j_only_exact_spool_root=v10_h4_sn2_j_only_exact_spool_root,
        v10_h4_j1_inner_fgmres=v10_h4_j1_inner_fgmres,
        v10_h4_j1_inner_fgmres_exact_spool_root=(
            v10_h4_j1_inner_fgmres_exact_spool_root
        ),
        v10_h4_side_response_packet_pilot=v10_h4_side_response_packet_pilot,
        v10_h4_side_response_packet_pilot_exact_spool_root=(
            v10_h4_side_response_packet_pilot_exact_spool_root
        ),
        v10_h4_side_response_packet_pilot_output_root=(
            v10_h4_side_response_packet_pilot_output_root
        ),
        v10_h4_side_response_packet_consumer=v10_h4_side_response_packet_consumer,
        v10_h4_side_response_packet_consumer_manifest=(
            v10_h4_side_response_packet_consumer_manifest
        ),
        v10_h4_side_response_packet_consumer_manifest_sha256=(
            v10_h4_side_response_packet_consumer_manifest_sha256
        ),
        v8_h4_layer_sweep_exact_spool_root=v8_h4_layer_sweep_exact_spool_root,
        v5_h4_blr_profile=v5_h4_blr_profile,
        selected_mode_packet_manifest=selected_mode_packet_manifest,
        selected_mode_packet_identity=selected_mode_packet_identity,
        selected_mode_packet_manifest_sha256=selected_mode_packet_manifest_sha256,
    )
    run_dir = Path(run_directory).resolve()
    if run_dir.exists():
        raise ValueError(f"V3-7 run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    from src.runners.task038_launcher import (
        _run_worker,
        _write_bootstrap,
    )
    from benchmarks.watchdog_process_control import terminate_process_tree
    from benchmarks.task034_wsl_resources import resource_authority_sample

    start_time = datetime.now(timezone.utc).isoformat()
    manifest, _ = _write_bootstrap(
        specification,
        run_dir,
        source_sha=source_sha,
        adapter_identity="task039.v3_7_orchestration",
        start_time=start_time,
    )
    executable = Path(os.path.abspath(python_executable or sys.executable))
    argv = tuple(plan_payload["argv"])
    plan = ExecutionPlan(
        argv=argv,
        shell=False,
        executable=executable,
        worker_module="benchmarks.task039_v3_7_orchestration",
        method=plan_payload["worker_contract"]["method"],
        mpi_size=8,
        requested_modes=480,
        physical_model_sha256=specification.physical_model_sha256,
        input_sha256=specification.input_sha256,
        source_sha=source_sha,
        adapter_identity="task039.v3_7_orchestration",
        adapter_available=True,
        contract_probe=False,
        task039_trace_audit=False,
        expected_output_directory=run_dir,
        expected_resolved_config=run_dir / "resolved_config.json",
        expected_manifest=run_dir / "run_manifest.json",
    )
    result = _run_worker(
        plan,
        specification,
        run_dir,
        popen_factory=popen_factory or subprocess.Popen,
        sample_factory=sample_factory or resource_authority_sample,
        terminate_factory=terminate_factory or terminate_process_tree,
        monotonic=time.monotonic,
        sleep=time.sleep,
        poll_interval=V3_7_POLL_SECONDS,
    )
    manifest.update(
        {
            "end_time": datetime.now(timezone.utc).isoformat(),
            "exit_status": result["exit_status"],
            "result_classification": result["result_classification"],
            "status": "finished",
        }
    )
    summary = {
        "status": "finished",
        "run_id": manifest["run_id"],
        "output_directory": str(run_dir),
        "numerical_output_directory": str(run_dir / "numerical_output"),
        **result,
    }
    (run_dir / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (run_dir / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"run_directory": str(run_dir), **result}


def _load_modal_amplitudes(inventory: Mapping[str, Any]) -> np.ndarray:
    artifact = inventory.get("payload", {}).get("artifact", {})
    path = Path(str(artifact.get("path", ""))).resolve()
    descriptor = inventory.get("payload", {}).get("arrays", {}).get("modal_amplitudes")
    if not path.is_file() or not isinstance(descriptor, Mapping):
        raise ValueError("direct modal amplitude artifact is not hash-bound")
    with np.load(path, allow_pickle=False) as archive:
        values = np.asarray(archive["modal_amplitudes"], dtype=np.complex128).copy()
    digest = hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest()
    if (
        descriptor.get("shape") != list(values.shape)
        or descriptor.get("dtype") != str(values.dtype)
        or descriptor.get("sha256") != digest
        or not np.isfinite(values).all()
    ):
        raise ValueError("direct modal amplitude identity is not exact")
    return values


def load_v3_7_direct_inventory(
    resolved_payload: Mapping[str, Any],
    direct_run_dir: str | Path,
    *,
    producer_source_sha: str = V3_7_DIRECT_PRODUCER_SHA,
) -> tuple[dict[str, Any], np.ndarray]:
    """Load the reviewed direct producer and verify its physical inventory."""

    physical_sha = resolved_payload.get("provenance", {}).get("physical_model_sha256")
    inventory = load_task039_direct_solution_inventory(
        direct_run_dir,
        expected_source_sha=producer_source_sha,
        expected_physical_model_sha256=physical_sha,
    )
    manifest_path = Path(str(direct_run_dir)).resolve() / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("model_id") != "task039_5nm_v3_1deg_s5_hybrid_direct_m480"
        or manifest.get("method") != "hybrid_direct"
        or manifest.get("mpi_size") != 8
    ):
        raise ValueError(
            "direct producer identity is not the fixed V3-7 h5/M480/MPI8 run"
        )
    expected = task039_dynamic_external_mode_inventory(resolved_payload)
    observed = manifest.get("external_mode_inventory")
    if not isinstance(observed, Mapping) or _keys(observed) != _keys(expected):
        raise ValueError("direct producer external mode keys do not match consumer")
    if int(inventory.get("verified_shard_count", 0)) != 32:
        raise ValueError("direct producer canonical inventory must verify 32 shards")
    modal = _load_modal_amplitudes(inventory)
    if modal.shape != (960,):
        raise ValueError("direct modal amplitude count must be 960")
    return {
        "producer_source_sha": producer_source_sha,
        "consumer_source_sha": None,
        "physical_model_sha256": physical_sha,
        "model_id": manifest["model_id"],
        "requested_modes": 480,
        "mpi_size": 8,
        "external_keys_exact": True,
        "verified_shard_count": int(inventory["verified_shard_count"]),
        "inventory": inventory,
    }, modal


def deterministic_global_index_vectors(
    layout: Any, *, seeds: tuple[int, ...] = (739, 743, 751)
) -> dict[str, PETSc.Vec]:
    """Create deterministic vectors from each rank's global ownership range."""

    vectors: dict[str, PETSc.Vec] = {}
    for seed in seeds:
        vector = layout.create_vector()
        first, last = (int(value) for value in vector.getOwnershipRange())
        index = np.arange(first, last, dtype=np.float64)
        vector.getArray()[:] = np.asarray(
            np.sin(index * 0.001 + seed) + 1j * np.cos(index * 0.0007 - seed),
            dtype=PETSc.ScalarType,
        )
        vector.assemble()
        vectors[f"global_index_seed_{seed}"] = vector
    return vectors


def _isolated_vector(layout: Any, block: str) -> PETSc.Vec:
    if block not in {"bottom", "top", "modal"}:
        raise ValueError("isolated block must be bottom, top, or modal")
    vector = layout.create_vector()
    values = np.arange(
        int(vector.getOwnershipRange()[0]),
        int(vector.getOwnershipRange()[1]),
        dtype=np.float64,
    )
    vector.getArray()[:] = 0.0
    target = getattr(layout, f"local_{block}_slice")
    vector.getArray()[target] = np.asarray(
        0.25 + np.sin(values[target] * 0.002), dtype=PETSc.ScalarType
    )
    vector.assemble()
    return vector


def _side_vector_identity(vector: PETSc.Vec, source: str) -> dict[str, Any]:
    values = np.ascontiguousarray(vector.getArray(readonly=True))
    comm = vector.getComm().tompi4py()
    ownership = [int(value) for value in vector.getOwnershipRange()]
    rank_records = comm.allgather(
        {
            "ownership_range": ownership,
            "local_sha256": hashlib.sha256(values.tobytes()).hexdigest(),
        }
    )
    global_sha = hashlib.sha256(
        json.dumps(rank_records, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "source": source,
        "global_size": int(vector.getSize()),
        "ownership_range": ownership,
        "dtype": str(values.dtype),
        "local_sha256": rank_records[comm.rank]["local_sha256"],
        "global_sha256": global_sha,
        "source_norm": float(vector.norm()),
    }


def _write_v5_blr_reference_spool(
    root: Path,
    side: str,
    label: str,
    vector: PETSc.Vec,
    role: str,
    source_identity: Mapping[str, Any],
) -> dict[str, Any]:
    values = np.ascontiguousarray(vector.getArray(readonly=True)).copy()
    comm = vector.getComm().tompi4py()
    rank = int(comm.rank)
    directory = root / "v5_blr_reference_spool" / f"rank{rank:04d}"
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{side}_{label}_{role}"
    array_path = directory / f"{stem}.npy"
    metadata_path = directory / f"{stem}.json"
    np.save(array_path, values, allow_pickle=False)
    record = {
        "side": side,
        "label": label,
        "role": role,
        "source_identity": _json_safe(source_identity),
        "ownership_range": [int(value) for value in vector.getOwnershipRange()],
        "global_size": int(vector.getSize()),
        "local_size": int(vector.getLocalSize()),
        "dtype": str(values.dtype),
        "array_path": str(array_path),
        "array_sha256": hashlib.sha256(values.tobytes()).hexdigest(),
        "metadata_path": str(metadata_path),
    }
    metadata_bytes = json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    record["metadata_payload_sha256_excluding_self"] = hashlib.sha256(
        metadata_bytes
    ).hexdigest()
    metadata_path.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )
    return record


def _load_v5_blr_reference_spool(
    record: Mapping[str, Any], template: PETSc.Vec
) -> PETSc.Vec:
    array_path = Path(str(record["array_path"]))
    metadata_path = Path(str(record["metadata_path"]))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if (
        metadata.get("side") != record.get("side")
        or metadata.get("label") != record.get("label")
        or metadata.get("role") != record.get("role")
    ):
        raise ValueError("BLR reference spool metadata identity mismatch")
    metadata_hash = metadata.pop("metadata_payload_sha256_excluding_self", None)
    metadata_payload = json.dumps(
        metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    if (
        not isinstance(metadata_hash, str)
        or hashlib.sha256(metadata_payload).hexdigest() != metadata_hash
    ):
        raise ValueError("BLR reference spool metadata payload hash mismatch")
    values = np.asarray(np.load(array_path, allow_pickle=False))
    expected_range = [int(value) for value in template.getOwnershipRange()]
    if (
        values.shape != (int(template.getLocalSize()),)
        or record.get("ownership_range") != expected_range
        or int(record.get("global_size", -1)) != int(template.getSize())
        or str(record.get("dtype")) != str(values.dtype)
        or hashlib.sha256(values.tobytes()).hexdigest() != record.get("array_sha256")
    ):
        raise ValueError("BLR reference spool array contract mismatch")
    target = template.duplicate()
    target.getArray()[:] = values
    target.assemble()
    return target


def _load_v5_fixed_budget_spool_records(
    root: str | Path,
    comm: MPI.Intracomm,
    *,
    packet_identity: Mapping[str, Any],
    manifest_sha256: str,
) -> dict[str, dict[str, Any]]:
    """Read the six frozen bottom probe descriptors for this MPI rank."""

    rank_directory = (
        Path(root).resolve() / "v5_blr_reference_spool" / f"rank{comm.rank:04d}"
    )
    records: dict[str, dict[str, Any]] = {}
    for label, kind, seed in V5_H4_BLR_RHS_SPECS:
        artifacts: dict[str, Any] = {}
        for role in ("rhs", "exact_output"):
            metadata_path = rank_directory / f"bottom_{label}_{role}.json"
            if not metadata_path.is_file():
                raise ValueError(
                    f"Missing fixed-budget spool metadata: {metadata_path}"
                )
            record = json.loads(metadata_path.read_text(encoding="utf-8"))
            source_identity = record.get("source_identity")
            packet_wrapper = (
                source_identity.get("packet_identity")
                if isinstance(source_identity, Mapping)
                else None
            )
            source_packet = (
                packet_wrapper.get("packet_identity")
                if isinstance(packet_wrapper, Mapping)
                else None
            )
            source_manifest = (
                packet_wrapper.get("manifest_sha256")
                if isinstance(packet_wrapper, Mapping)
                else None
            )
            if (
                record.get("side") != "bottom"
                or record.get("label") != label
                or record.get("role") != role
                or source_packet != dict(packet_identity)
                or source_manifest != manifest_sha256
            ):
                raise ValueError(
                    f"Fixed-budget spool identity mismatch: {metadata_path}"
                )
            artifacts[role] = record
        records[label] = {
            "label": label,
            "kind": kind,
            "seed": seed,
            "rhs": artifacts["rhs"],
            "exact_output": artifacts["exact_output"],
        }
    return records


def _validate_v5_fixed_budget_packet_manifest(
    manifest_path: str | Path,
    packet_identity: Mapping[str, Any],
    manifest_sha256: str,
    *,
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    """Validate only packet identity for the side-only fixed-budget path."""

    path = Path(manifest_path).resolve()
    if not path.is_file():
        raise ValueError(f"Fixed-budget packet manifest is missing: {path}")
    actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual_sha256 != manifest_sha256:
        raise ValueError("Fixed-budget packet manifest hash mismatch")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (
        manifest.get("rank_count") != int(comm.size)
        or manifest.get("consumer_qep_required") is not False
        or manifest.get("qep_workspace_persisted") is not False
        or manifest.get("identity") != dict(packet_identity)
    ):
        raise ValueError("Fixed-budget packet identity contract mismatch")
    return {
        "manifest": str(path),
        "manifest_sha256": actual_sha256,
        "identity": _json_safe(dict(packet_identity)),
        "consumer_qep_calls": 0,
        "consumer_qep_required": False,
        "arrays_hydrated": False,
    }


def _build_v5_h4_fixed_budget_bottom_side_setup(
    *,
    cfg: Any,
    profile: Any,
    comm: MPI.Intracomm,
    detail_stage_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> Any:
    """Build only the matrix-free bottom action carrier for V5 fixed budget."""

    system = assemble_hybrid_local_dtn_action_system(
        cfg,
        "bottom",
        bottom_interface_z_nm=profile.bottom_interface_nm,
        top_interface_z_nm=profile.top_interface_nm,
        comm=comm,
        log=None,
    )
    if detail_stage_callback is not None:
        detail_stage_callback(
            "v5_fixed_budget_bottom_side_system_ready",
            {
                "side": "bottom",
                "global_F_materialized": False,
                "no_new_explicit_component_matrix": True,
                "packet_arrays_hydrated": False,
            },
        )
    return SimpleNamespace(bottom=system, side_only=True)


def run_v8_h4_layer_block_reconstruction_component(
    cfg: Any,
    *,
    profile: Any,
    comm: MPI.Intracomm,
    marker_callback: Callable[[str, Mapping[str, Any]], None],
    side_system_builder: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Audit the real bottom and top explicit ``F`` graphs sequentially.

    This route deliberately materializes only one side's research explicit
    matrices at a time.  The layer operator borrows ``F``; component and
    action ownership is released before the next side is assembled.
    """

    sides: dict[str, Any] = {}
    for side in ("bottom", "top"):
        system = None
        components = None
        operator = None
        completed = False
        try:
            marker_callback(
                f"v8_layer_block_{side}_construction_begin",
                {
                    "side": side,
                    "selected_mode_packet_opened": False,
                    "holdout_opened": False,
                    "exact_spool_opened": False,
                    "qep_count": 0,
                    "factor_count": 0,
                    "outer_ksp_count": 0,
                },
            )
            if side_system_builder is None:
                system = assemble_hybrid_local_dtn_action_system(
                    cfg,
                    side,
                    bottom_interface_z_nm=profile.bottom_interface_nm,
                    top_interface_z_nm=profile.top_interface_nm,
                    comm=comm,
                    log=None,
                )
            else:
                system = side_system_builder(
                    side=side,
                    cfg=cfg,
                    profile=profile,
                    comm=comm,
                )
            components = _build_research_explicit_side_components(system)
            labels, mapping_metadata = build_real_layer_labels(components.F, system)
            layer_count = len(mapping_metadata["z_layer_boundaries"]) - 1
            if layer_count != 6:
                raise ValueError(
                    f"V8 layer-block route requires exactly six layers, got {layer_count}"
                )
            operator = build_layer_block_operator(
                components.F,
                labels,
                layer_count=layer_count,
                mapping_metadata=mapping_metadata,
            )
            ready_diagnostics = deepcopy(operator.diagnostics)
            marker_callback(
                f"v8_layer_block_{side}_operator_ready",
                {
                    "side": side,
                    "diagnostics": ready_diagnostics,
                    "factor_count": 0,
                    "qep_count": 0,
                    "outer_ksp_count": 0,
                    "system_borrowed": True,
                },
            )
            action_audit = audit_layer_block_action(components.F, operator)
            action_gate = {
                "action_finite": bool(
                    all(report["finite"] for report in action_audit["vectors"])
                ),
                "action_relative_error_pass": bool(
                    all(
                        report["relative_error"] <= 1.0e-12
                        for report in action_audit["vectors"]
                    )
                ),
                "row_coverage_exact": bool(ready_diagnostics["row_coverage_exact"]),
                "nnz_partition_exact": bool(
                    ready_diagnostics["nnz_partition"]["partition_exact"]
                ),
                "long_range_zero": bool(ready_diagnostics["long_range_nnz"] == 0),
                "half_bandwidth_one": bool(
                    ready_diagnostics["block_half_bandwidth"] == 1
                ),
                "repeat_pass": bool(action_audit["repeat_relative_error"] <= 1.0e-13),
                "linearity_pass": bool(
                    action_audit["linearity_relative_error"] <= 1.0e-13
                ),
            }
            operator.destroy()
            operator_diagnostics = deepcopy(operator.diagnostics)
            operator = None
            released = _destroy_v5_side_components(components)
            system_a = getattr(system, "A", None)
            if system_a is None:
                system_probe = {"status": "not_available"}
            else:
                size = tuple(int(value) for value in system_a.getSize())
                ownership = tuple(int(value) for value in system_a.getOwnershipRange())
                system_probe = {
                    "status": "measured",
                    "global_size": list(size),
                    "ownership_range": list(ownership),
                }
            destroy_called = False
            if hasattr(system, "destroy"):
                system.destroy()
                destroy_called = True
            cleanup = collective_heap_cleanup(comm)
            side_gate = {
                **action_gate,
                "operator_destroy_marker_completed": bool(
                    operator_diagnostics.get("destroy_marker") == "completed"
                ),
                "component_release_pass": bool(
                    all(released.get(name) is True for name in ("H", "C", "F", "D"))
                ),
                "collective_cleanup_pass": bool(
                    cleanup.get("collective_call_completed") is True
                ),
                "system_a_probe_measured": bool(
                    system_probe.get("status") == "measured"
                ),
                "factor_counts_zero": bool(
                    operator_diagnostics.get("factor_count") == 0
                ),
                "qep_count_zero": bool(operator_diagnostics.get("qep_count") == 0),
                "outer_ksp_count_zero": bool(
                    operator_diagnostics.get("outer_ksp_count") == 0
                ),
                "system_destroy_called": destroy_called,
            }
            side_gate["pass"] = bool(all(side_gate.values()))
            marker_callback(
                f"v8_layer_block_{side}_destroy",
                {
                    "side": side,
                    "operator_destroyed": True,
                    "component_release": released,
                    "collective_cleanup": cleanup,
                    "borrowed_system_probe_after_components": system_probe,
                    "system_destroy_called": destroy_called,
                    "factor_count": 0,
                    "qep_count": 0,
                    "outer_ksp_count": 0,
                },
            )
            sides[side] = {
                "operator_diagnostics": operator_diagnostics,
                "action_audit": action_audit,
                "gate": side_gate,
                "lifecycle": {
                    "operator_destroyed": True,
                    "component_release": released,
                    "collective_cleanup": cleanup,
                    "borrowed_system_probe_after_components": system_probe,
                    "destroy_called": destroy_called,
                },
            }
            completed = True
        finally:
            if not completed:
                if operator is not None:
                    operator.destroy()
                if components is not None:
                    _destroy_v5_side_components(components)
                if system is not None and hasattr(system, "destroy"):
                    system.destroy()
                collective_heap_cleanup(comm)

    sides_present_exact = set(sides) == {"bottom", "top"}
    return {
        "schema": V8_H4_LAYER_BLOCK_SCHEMA,
        "method": V8_H4_LAYER_BLOCK_METHOD,
        "profile_id": V8_H4_LAYER_BLOCK_PROFILE_ID,
        "status": (
            "component_completed"
            if sides_present_exact
            and all(side.get("gate", {}).get("pass") for side in sides.values())
            else "component_gate_failed"
        ),
        "sides": sides,
        "gate": {
            "sides_present_exact": sides_present_exact,
            "bottom_pass": bool(sides.get("bottom", {}).get("gate", {}).get("pass")),
            "top_pass": bool(sides.get("top", {}).get("gate", {}).get("pass")),
            "overall_pass": bool(
                sides_present_exact
                and all(side.get("gate", {}).get("pass") for side in sides.values())
            ),
        },
        "factor_inventory": {
            "base_factor_count": 0,
            "exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
        },
        "selected_mode_packet_opened": False,
        "holdout_opened": False,
        "exact_spool_opened": False,
        "qep_count": 0,
        "modal_schur": "not_run",
        "outer_ksp": "not_run",
        "recovery": "not_run",
        "field": "not_run",
        "RTA": "not_run",
        "telemetry": {
            "process_tree_samples": {
                "path": "numerical_output/process_tree_samples.jsonl",
                "writer": "parent_task038_launcher",
            },
            "memory_stages": {
                "path": "numerical_output/memory_stages.jsonl",
                "writer": "parent_task038_launcher_marker_alignment",
            },
            "memory_stage_markers": {
                "path": "numerical_output/memory_stage_markers.raw.jsonl",
                "writer": "v3_7_worker",
            },
            "memory_object_ledger": {
                "path": "numerical_output/memory_object_ledger.json",
                "status": "finalized_in_worker_finalizer",
            },
            "gate_contract": {
                "action_relative_error": 1.0e-12,
                "repeat_relative_error": 1.0e-13,
                "linearity_relative_error": 1.0e-13,
                "swap_required": 0,
                "no_factor_qep_outer": True,
            },
        },
    }


def _v9_frozen_holdout_identity(
    exact_spool_root: str | Path, comm: MPI.Intracomm
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """Read the frozen holdout identity without opening a selected packet."""

    metadata_path = (
        Path(exact_spool_root).resolve()
        / "v5_blr_reference_spool"
        / "rank0000"
        / "bottom_modal_traction_positive_rhs.json"
    )
    record = json.loads(metadata_path.read_text(encoding="utf-8"))
    source_identity = record.get("source_identity")
    wrapper = (
        source_identity.get("packet_identity")
        if isinstance(source_identity, Mapping)
        else None
    )
    packet_identity = (
        wrapper.get("packet_identity") if isinstance(wrapper, Mapping) else None
    )
    manifest_sha256 = (
        wrapper.get("manifest_sha256") if isinstance(wrapper, Mapping) else None
    )
    producer_source_sha = (
        wrapper.get("source_sha") if isinstance(wrapper, Mapping) else None
    )
    if not isinstance(packet_identity, Mapping) or not isinstance(manifest_sha256, str):
        raise ValueError("V9 frozen holdout identity is missing from exact spool")
    identity = dict(packet_identity)
    identity_states = comm.allgather(identity)
    manifest_states = comm.allgather(manifest_sha256)
    if any(candidate != identity for candidate in identity_states) or any(
        candidate != manifest_sha256 for candidate in manifest_states
    ):
        raise ValueError("V9 frozen holdout identity differs across ranks")
    catalog_authority = {
        "catalog_sha256": V9_FROZEN_HOLDOUT_CATALOG_SHA256,
        "inherited_expected_catalog_sha256": V9_FROZEN_HOLDOUT_CATALOG_SHA256,
        "catalog_status": "inherited_expected_not_recomputed",
        "producer_source_sha": producer_source_sha,
        "producer_rank_count": 8,
        "label_count": 6,
        "response_artifact_count": 96,
        "catalog_method": (
            "sha256 of sorted relative path, byte count, and file SHA256 rows"
        ),
    }
    if producer_source_sha != V9_FROZEN_HOLDOUT_PRODUCER_SHA:
        raise ValueError(
            "V9 frozen holdout producer source SHA does not match the inherited "
            f"authority: {producer_source_sha!r}"
        )
    return identity, manifest_sha256, catalog_authority


def run_v9_h4_bare_f_side_diagnostic(
    cfg: Any,
    *,
    profile: Any,
    comm: MPI.Intracomm,
    marker_callback: Callable[[str, Mapping[str, Any]], None],
    exact_spool_root: str | Path,
    side_system_builder: Callable[..., Any] | None = None,
    holdout_identity: Mapping[str, Any] | None = None,
    holdout_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """Re-evaluate only J1/F1 with bare-F and full-side residuals.

    The six factor set is built once from the real bottom ``F``.  Each method
    gets a transient dynamic Woodbury action, then that action is destroyed
    before the next method.  ``r_F`` is measured with the explicit research
    ``F`` and ``r_A`` with the real matrix-free ``system.A``; reference output
    remains an independent cross-check only.
    """

    system = None
    components = None
    sweep = None
    spool = None
    holdout_catalog_authority: dict[str, Any] = {
        "catalog_sha256": V9_FROZEN_HOLDOUT_CATALOG_SHA256,
        "inherited_expected_catalog_sha256": V9_FROZEN_HOLDOUT_CATALOG_SHA256,
        "catalog_status": "inherited_expected_not_recomputed",
        "producer_source_sha": None,
        "producer_rank_count": 8,
        "label_count": 6,
        "response_artifact_count": 96,
        "catalog_method": (
            "sha256 of sorted relative path, byte count, and file SHA256 rows"
        ),
    }
    method_records: dict[str, dict[str, Any]] = {}
    component_matrix_inventory: dict[str, Any] = {}
    method_woodbury_inventory: dict[str, Any] = {}
    completed = False
    factor_diagnostics_after_cleanup: dict[str, Any] = {"status": "not_run"}

    class _SweepMethodView:
        factor_only_storage = True

        def __init__(self, action: Any, method: str) -> None:
            self.action = action
            self.method = method

        def solve(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
            self.action.apply_checkpoint(self.method, source, target)

    class _ProbeActionView:
        def __init__(self, action: Any, operator: PETSc.Mat) -> None:
            self.action = action
            self.operator = operator
            self.apply_count = 0

        def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
            self.apply_count += 1
            self.action.apply(source, target)

    marker_callback(
        "v9_bare_f_side_construction_begin",
        {
            "side": "bottom",
            "construction_peak_limit_gib": V9_H4_BARE_F_SIDE_CONSTRUCTION_LIMIT_GIB,
            "retained_peak_limit_gib": V9_H4_BARE_F_SIDE_RETAINED_LIMIT_GIB,
            "selected_mode_packet_opened": False,
            "qep_count": 0,
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
        },
    )
    try:
        if side_system_builder is None:
            system = assemble_hybrid_local_dtn_action_system(
                cfg,
                "bottom",
                bottom_interface_z_nm=profile.bottom_interface_nm,
                top_interface_z_nm=profile.top_interface_nm,
                comm=comm,
                log=None,
            )
        else:
            system = side_system_builder(
                side="bottom", cfg=cfg, profile=profile, comm=comm
            )
        components = _build_research_explicit_side_components(system)
        labels, mapping_metadata = build_real_layer_labels(components.F, system)
        layer_count = len(mapping_metadata["z_layer_boundaries"]) - 1
        if layer_count != 6:
            raise ValueError(
                f"V9 bare-F route requires exactly six layers, got {layer_count}"
            )
        sweep = build_layer_sweep_action(
            components.F,
            labels,
            layer_count=layer_count,
            method="J1",
            fine_action=components.F.mult,
        )
        del labels, mapping_metadata
        marker_callback(
            "v9_bare_f_side_factors_ready",
            {
                "layer_factor_count": sweep.diagnostics["layer_factor_count"],
                "same_factor_set_for_methods": True,
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
            },
        )
        if holdout_identity is None or holdout_manifest_sha256 is None:
            (
                holdout_identity,
                holdout_manifest_sha256,
                holdout_catalog_authority,
            ) = _v9_frozen_holdout_identity(exact_spool_root, comm)
        spool = _load_v5_fixed_budget_spool_shards(
            exact_spool_root,
            comm,
            packet_identity=holdout_identity,
            manifest_sha256=holdout_manifest_sha256,
        )
        marker_callback(
            "v9_bare_f_side_holdout_ready",
            {
                "holdout_opened": True,
                "exact_spool_opened": True,
                "selected_mode_packet_opened": False,
                "holdout_labels": list(spool),
            },
        )
        component_matrix_inventory = _v5_side_matrix_inventory(components)

        for method in ("J1", "F1"):
            before = sweep.diagnostics
            marker_callback(
                f"v9_bare_f_side_{method}_woodbury_begin",
                {"method": method, "layer_factor_count": 6},
            )
            method_view = _SweepMethodView(sweep, method)
            woodbury = None
            reports: list[dict[str, Any]] = []
            woodbury_diagnostics: dict[str, Any] = {"status": "not_available"}
            started = time.perf_counter()
            try:
                woodbury = HybridLocalDtnWoodburyOracle(
                    method_view,
                    components,
                    base_identity=f"v9_bare_f_{method}_dynamic_woodbury",
                    compact_storage=False,
                )
                setup_seconds = time.perf_counter() - started
                marker_callback(
                    f"v9_bare_f_side_{method}_woodbury_ready",
                    {
                        "method": method,
                        "setup_seconds": setup_seconds,
                        "woodbury": woodbury.diagnostics,
                    },
                )
                holdout_started = time.perf_counter()
                for label, artifact in spool.items():
                    template = rhs = reference = bare_solution = None
                    try:
                        template = system.A.createVecLeft()
                        rhs = _load_v5_blr_reference_spool_remapped(
                            artifact["rhs"], template
                        )
                        reference = _load_v5_blr_reference_spool_remapped(
                            artifact["exact_output"], template
                        )
                        bare_solution = components.F.createVecLeft()
                        method_view.solve(rhs, bare_solution)
                        bare_residual = relative_matvec_residual(
                            components.F, rhs, bare_solution
                        )
                        probe_action = _ProbeActionView(woodbury, system.A)
                        report, _ = _v5_blr_probe(
                            probe_action,
                            system,
                            rhs,
                            dict(artifact["rhs"]["probe_metadata"]),
                            reference,
                            repeat=True,
                            linearity=True,
                        )
                        full_residual = report["true_residual_relative"]
                        ratio = (
                            None
                            if bare_residual == 0.0
                            else float(full_residual) / float(bare_residual)
                        )
                        report.update(
                            {
                                "r_F": bare_residual,
                                "r_A": full_residual,
                                "r_A_over_r_F": ratio,
                                "reference_is_cross_check_only": True,
                                "mandatory": not (
                                    label == "physical_side_rhs"
                                    and bool(report["degenerate_uninformative"])
                                ),
                                "degenerate": bool(report["degenerate_uninformative"]),
                                "mandatory_gate_eligible": not (
                                    label == "physical_side_rhs"
                                    and bool(report["degenerate_uninformative"])
                                ),
                                "bare_F_residual_matvec_count": 1,
                                "side_inverse_apply_count": probe_action.apply_count,
                                "A_side_true_residual_matvec_count": 1,
                            }
                        )
                        reports.append(report)
                    finally:
                        if bare_solution is not None:
                            bare_solution.destroy()
                        if reference is not None:
                            reference.destroy()
                        if rhs is not None:
                            rhs.destroy()
                        if template is not None:
                            template.destroy()
                holdout_seconds = time.perf_counter() - holdout_started
                gate = _v6_port_modal_holdout_gate(reports)
                woodbury_diagnostics = deepcopy(woodbury.diagnostics)
                method_woodbury_inventory[method] = woodbury_diagnostics
            finally:
                if woodbury is not None:
                    woodbury.destroy()
            cleanup = collective_heap_cleanup(comm)
            marker_callback(
                f"v9_bare_f_side_{method}_cleanup",
                {
                    "method": method,
                    "woodbury_destroyed": True,
                    "collective_cleanup": cleanup,
                },
            )
            after = sweep.diagnostics
            layer_delta = [
                int(after_value - before_value)
                for after_value, before_value in zip(
                    after["layer_solve_count"], before["layer_solve_count"]
                )
            ]
            method_records[method] = {
                "method": method,
                "reports": reports,
                "gate": gate,
                "woodbury": woodbury_diagnostics,
                "r_F_definition": "||b-F M_F b||/||b||",
                "r_A_definition": "||b-A_side M_A b||/||b||",
                "bare_F_residual_matvec_count": int(
                    sum(report["bare_F_residual_matvec_count"] for report in reports)
                ),
                "side_inverse_apply_count": int(
                    sum(report["side_inverse_apply_count"] for report in reports)
                ),
                "A_side_true_residual_matvec_count": int(
                    sum(
                        report["A_side_true_residual_matvec_count"]
                        for report in reports
                    )
                ),
                "layer_solve_count_delta": layer_delta,
                "layer_solve_count_total": int(sum(layer_delta)),
                "fine_action_count": int(
                    after["fine_action_count"] - before["fine_action_count"]
                ),
                "fb_sweep_count": int(
                    after["fb_sweep_count"] - before["fb_sweep_count"]
                ),
                "setup_seconds": setup_seconds,
                "holdout_seconds": holdout_seconds,
                "K_rank": woodbury_diagnostics.get("K_rank"),
                "K_condition_number": woodbury_diagnostics.get("K_condition_number"),
                "method_cleanup": cleanup,
                "same_factor_set": True,
                "fb_methods_not_run": ["FB1", "FB2", "FB4"],
            }
            marker_callback(
                f"v9_bare_f_side_{method}_complete",
                {
                    "method": method,
                    "gate": gate,
                    "setup_seconds": setup_seconds,
                    "holdout_seconds": holdout_seconds,
                    "K_rank": woodbury_diagnostics.get("K_rank"),
                    "K_condition_number": woodbury_diagnostics.get(
                        "K_condition_number"
                    ),
                },
            )

        marker_callback(
            "v9_bare_f_side_construction_end",
            {
                "methods_evaluated": ["J1", "F1"],
                "same_factor_set": True,
                "fb_methods_not_run": ["FB1", "FB2", "FB4"],
                "resource_gate": "pending_parent_process_tree_samples",
            },
        )
        marker_callback(
            "v9_bare_f_side_retained_apply_state_not_run",
            {
                "reason": "diagnostic_route_has_no_preferred_retained_action",
                "retained_peak_limit_gib": V9_H4_BARE_F_SIDE_RETAINED_LIMIT_GIB,
            },
        )
        spool_released = spool is not None
        spool = None
        if sweep is not None:
            sweep.destroy()
            factor_diagnostics_after_cleanup = deepcopy(sweep.diagnostics)
        released = _destroy_v5_side_components(components)
        system_probe = {
            "status": "not_available",
            "global_size": None,
            "ownership_range": None,
        }
        if getattr(system, "A", None) is not None:
            system_probe = {
                "status": "measured",
                "global_size": list(map(int, system.A.getSize())),
                "ownership_range": list(map(int, system.A.getOwnershipRange())),
            }
        system_destroy_called = False
        if hasattr(system, "destroy"):
            system.destroy()
            system_destroy_called = True
        cleanup = collective_heap_cleanup(comm)
        marker_callback(
            "v9_bare_f_side_retained_state_release",
            {
                "system_destroy_called": system_destroy_called,
                "factor_count_after_cleanup": 0,
                "sweep_destroyed": True,
                "spool_released": spool_released,
                "collective_cleanup": cleanup,
            },
        )
        method_gate_pass = all(
            record["gate"].get("pass") is True for record in method_records.values()
        )
        gate = {
            "methods": method_records,
            "methods_evaluated": ["J1", "F1"],
            "fb_methods_not_run": ["FB1", "FB2", "FB4"],
            "numerical_holdout_gate_pass": method_gate_pass,
            "resource_gate": "pending_parent_process_tree_samples",
            "resource_gate_limits_gib": {
                "construction": V9_H4_BARE_F_SIDE_CONSTRUCTION_LIMIT_GIB,
                "retained": V9_H4_BARE_F_SIDE_RETAINED_LIMIT_GIB,
            },
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
            "pass": None,
        }
        completed = True
        return {
            "schema": V9_H4_BARE_F_SIDE_SCHEMA,
            "method": V9_H4_BARE_F_SIDE_METHOD,
            "profile_id": V9_H4_BARE_F_SIDE_PROFILE_ID,
            "status": "component_diagnostic_completed",
            "side": "bottom",
            "method_records": method_records,
            "gate": gate,
            "factor_inventory": {
                "layer_factor_count_ready": 6,
                "layer_factor_count_after_cleanup": 0,
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
                "component_matrix_inventory": component_matrix_inventory,
                "woodbury_by_method": method_woodbury_inventory,
            },
            "holdout_provenance": {
                "packet_identity": holdout_identity,
                "manifest_sha256": holdout_manifest_sha256,
                "catalog_authority": holdout_catalog_authority,
            },
            "selected_mode_packet_opened": False,
            "holdout_opened": True,
            "exact_spool_opened": True,
            "qep_count": 0,
            "modal_schur": "not_run",
            "outer_ksp": "not_run",
            "recovery": "not_run",
            "field": "not_run",
            "lifecycle": {
                "components": released,
                "system_probe": system_probe,
                "collective_cleanup": cleanup,
                "woodbury_destroyed_between_methods": True,
                "factor_count_ready": 6,
                "factor_count_after_cleanup": 0,
                "sweep_diagnostics_after_cleanup": factor_diagnostics_after_cleanup,
                "spool_released": spool_released,
            },
            "telemetry": {
                "process_tree_samples": {
                    "path": "numerical_output/process_tree_samples.jsonl",
                    "writer": "parent_task038_launcher",
                },
                "memory_stages": {
                    "path": "numerical_output/memory_stages.jsonl",
                    "writer": "parent_task038_launcher_marker_alignment",
                },
                "memory_stage_markers": {
                    "path": "numerical_output/memory_stage_markers.raw.jsonl",
                    "writer": "v3_7_worker",
                },
                "memory_object_ledger": {
                    "path": "numerical_output/memory_object_ledger.json",
                    "status": "finalized_in_worker_finalizer",
                },
                "gate_contract": {
                    "construction_peak_limit_gib": V9_H4_BARE_F_SIDE_CONSTRUCTION_LIMIT_GIB,
                    "retained_peak_limit_gib": V9_H4_BARE_F_SIDE_RETAINED_LIMIT_GIB,
                    "swap_required": 0,
                    "selected_mode_packet_opened": False,
                    "full_side_exact_factor_count": 0,
                    "global_direct_factor_count": 0,
                    "nested_ksp_count": 0,
                },
            },
        }
    finally:
        if not completed:
            if spool is not None:
                spool = None
            if sweep is not None:
                sweep.destroy()
            if components is not None:
                _destroy_v5_side_components(components)
            if system is not None and hasattr(system, "destroy"):
                system.destroy()
            collective_heap_cleanup(comm)


def run_v8_h4_layer_sweep_bottom_component(
    cfg: Any,
    *,
    profile: Any,
    comm: MPI.Intracomm,
    marker_callback: Callable[[str, Mapping[str, Any]], None],
    exact_spool_root: str | Path,
    packet_identity: Mapping[str, Any],
    packet_manifest_sha256: str,
    side_system_builder: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Audit one bottom layer action with the frozen dynamic Woodbury probes."""

    system = None
    components = None
    sweep = None
    spool = None
    completed = False
    method_records: dict[str, dict[str, Any]] = {}
    first_passing_method: str | None = None
    preferred_woodbury = None
    preferred_woodbury_diagnostics: dict[str, Any] = {"status": "not_run"}
    retained_probe: dict[str, Any] | None = None
    sweep_destroyed = False
    sweep_diagnostics_after_cleanup: dict[str, Any] = {"status": "not_run"}

    class _SweepMethodView:
        factor_only_storage = True

        def __init__(self, action: Any, method: str) -> None:
            self.action = action
            self.method = method

        def solve(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
            self.action.apply_checkpoint(self.method, source, target)

    class _ProbeActionView:
        def __init__(self, action: Any, operator: PETSc.Mat) -> None:
            self.action = action
            self.operator = operator

        def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
            self.action.apply(source, target)

    marker_callback(
        "v8_layer_sweep_bottom_construction_begin",
        {
            "construction_peak_limit_gib": V8_H4_LAYER_SWEEP_CONSTRUCTION_LIMIT_GIB,
            "retained_peak_limit_gib": V8_H4_LAYER_SWEEP_RETAINED_LIMIT_GIB,
            "side": "bottom",
            "selected_mode_packet_opened": False,
            "holdout_opened": False,
            "exact_spool_opened": False,
            "qep_count": 0,
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
        },
    )
    try:
        if side_system_builder is None:
            system = assemble_hybrid_local_dtn_action_system(
                cfg,
                "bottom",
                bottom_interface_z_nm=profile.bottom_interface_nm,
                top_interface_z_nm=profile.top_interface_nm,
                comm=comm,
                log=None,
            )
        else:
            system = side_system_builder(
                side="bottom", cfg=cfg, profile=profile, comm=comm
            )
        components = _build_research_explicit_side_components(system)
        labels, mapping_metadata = build_real_layer_labels(components.F, system)
        layer_count = len(mapping_metadata["z_layer_boundaries"]) - 1
        if layer_count != 6:
            raise ValueError(
                f"V8 layer sweep route requires exactly six layers, got {layer_count}"
            )
        sweep = build_layer_sweep_action(
            components.F,
            labels,
            layer_count=layer_count,
            method="FB1",
            fine_action=components.F.mult,
        )
        del labels, mapping_metadata
        marker_callback(
            "v8_layer_sweep_bottom_factors_ready",
            {
                "layer_factor_count": sweep.diagnostics["layer_factor_count"],
                "factor_only_storage": sweep.factor_only_storage,
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
            },
        )
        spool = _load_v5_fixed_budget_spool_shards(
            exact_spool_root,
            comm,
            packet_identity=packet_identity,
            manifest_sha256=packet_manifest_sha256,
        )
        marker_callback(
            "v8_layer_sweep_bottom_holdout_ready",
            {
                "holdout_opened": True,
                "exact_spool_opened": True,
                "holdout_labels": list(spool),
                "selected_mode_packet_opened": False,
            },
        )

        for method in ("J1", "F1", "FB1", "FB2", "FB4"):
            before = sweep.diagnostics
            marker_callback(
                f"v8_layer_sweep_bottom_{method}_woodbury_begin",
                {"method": method, "layer_factor_count": 6},
            )
            method_view = _SweepMethodView(sweep, method)
            woodbury = None
            reports: list[dict[str, Any]] = []
            woodbury_diagnostics: dict[str, Any] = {"status": "not_available"}
            try:
                woodbury = HybridLocalDtnWoodburyOracle(
                    method_view,
                    components,
                    base_identity=f"v8_layer_sweep_{method}_dynamic_woodbury",
                    compact_storage=False,
                )
                marker_callback(
                    f"v8_layer_sweep_bottom_{method}_woodbury_ready",
                    {"method": method, "woodbury": woodbury.diagnostics},
                )
                for label, artifact in spool.items():
                    template = rhs = reference = None
                    try:
                        template = system.A.createVecLeft()
                        rhs = _load_v5_blr_reference_spool_remapped(
                            artifact["rhs"], template
                        )
                        reference = _load_v5_blr_reference_spool_remapped(
                            artifact["exact_output"], template
                        )
                        report, _ = _v5_blr_probe(
                            _ProbeActionView(woodbury, system.A),
                            system,
                            rhs,
                            dict(artifact["rhs"]["probe_metadata"]),
                            reference,
                            repeat=True,
                            linearity=True,
                        )
                        reports.append(report)
                    finally:
                        if reference is not None:
                            reference.destroy()
                        if rhs is not None:
                            rhs.destroy()
                        if template is not None:
                            template.destroy()
                gate = _v6_port_modal_holdout_gate(reports)
                woodbury_diagnostics = deepcopy(woodbury.diagnostics)
            finally:
                if woodbury is not None:
                    woodbury.destroy()
            method_cleanup = collective_heap_cleanup(comm)
            marker_callback(
                f"v8_layer_sweep_bottom_{method}_cleanup",
                {
                    "method": method,
                    "woodbury_destroyed": True,
                    "collective_cleanup": method_cleanup,
                },
            )
            after = sweep.diagnostics
            layer_solve_delta = [
                int(after_count - before_count)
                for after_count, before_count in zip(
                    after["layer_solve_count"], before["layer_solve_count"]
                )
            ]
            method_record = {
                "method": method,
                "reports": reports,
                "gate": gate,
                "woodbury": woodbury_diagnostics,
                "apply_wall_seconds": woodbury_diagnostics.get(
                    "apply_seconds", "not_available"
                ),
                "layer_solve_count_delta": layer_solve_delta,
                "layer_solve_count_total": int(sum(layer_solve_delta)),
                "fine_action_count": int(
                    after["fine_action_count"] - before["fine_action_count"]
                ),
                "fb_sweep_count": int(
                    after["fb_sweep_count"] - before["fb_sweep_count"]
                ),
                "single_sweep_build_count": 1,
                "same_factor_set": True,
                "method_cleanup": method_cleanup,
            }
            method_records[method] = method_record
            if first_passing_method is None and gate["pass"]:
                first_passing_method = method
            marker_callback(
                f"v8_layer_sweep_bottom_{method}_complete",
                {"method": method, "gate": gate, "woodbury": woodbury_diagnostics},
            )

        if first_passing_method is not None:
            preferred_view = _SweepMethodView(sweep, first_passing_method)
            preferred_woodbury = HybridLocalDtnWoodburyOracle(
                preferred_view,
                components,
                base_identity=(
                    f"v8_layer_sweep_{first_passing_method}_"
                    "preferred_dynamic_woodbury_rehydration"
                ),
                compact_storage=False,
            )
            preferred_ready_diagnostics = deepcopy(preferred_woodbury.diagnostics)
            marker_callback(
                "v8_layer_sweep_bottom_construction_end",
                {
                    "methods_evaluated": list(method_records),
                    "first_passing_method": first_passing_method,
                    "woodbury_destroyed_between_methods": True,
                    "preferred_woodbury_rehydrated": True,
                    "construction_temporaries_released": True,
                    "resource_gate": "pending_parent_process_tree_samples",
                },
            )
            marker_callback(
                "v8_layer_sweep_bottom_retained_apply_state_ready",
                {
                    "first_passing_method": first_passing_method,
                    "preferred_action_rehydration": True,
                    "same_layer_factor_instance": True,
                    "preferred_woodbury": preferred_ready_diagnostics,
                    "explicit_F_released": False,
                    "retained_explicit_F": True,
                    "D_retained": True,
                    "retained_W": True,
                    "D_i_released": True,
                    "construction_temporaries_released": True,
                    "retained_apply_state_valid": True,
                    "retained_peak_limit_gib": V8_H4_LAYER_SWEEP_RETAINED_LIMIT_GIB,
                    "resource_gate": "pending_parent_process_tree_samples",
                },
            )
            first_label, first_artifact = next(iter(spool.items()))
            template = rhs = reference = None
            try:
                template = system.A.createVecLeft()
                rhs = _load_v5_blr_reference_spool_remapped(
                    first_artifact["rhs"], template
                )
                reference = _load_v5_blr_reference_spool_remapped(
                    first_artifact["exact_output"], template
                )
                retained_probe, _ = _v5_blr_probe(
                    _ProbeActionView(preferred_woodbury, system.A),
                    system,
                    rhs,
                    dict(first_artifact["rhs"]["probe_metadata"]),
                    reference,
                    repeat=True,
                    linearity=True,
                )
                retained_probe["label"] = first_label
                preferred_woodbury_diagnostics = deepcopy(
                    preferred_woodbury.diagnostics
                )
            finally:
                if reference is not None:
                    reference.destroy()
                if rhs is not None:
                    rhs.destroy()
                if template is not None:
                    template.destroy()
        else:
            marker_callback(
                "v8_layer_sweep_bottom_construction_end",
                {
                    "methods_evaluated": list(method_records),
                    "first_passing_method": None,
                    "woodbury_destroyed_between_methods": True,
                    "preferred_woodbury_rehydrated": False,
                    "construction_temporaries_released": True,
                    "resource_gate": "not_run_numerical_gate_failed",
                },
            )
            marker_callback(
                "v8_layer_sweep_bottom_retained_apply_state_not_run",
                {
                    "first_passing_method": None,
                    "preferred_action_rehydration": False,
                    "same_layer_factor_instance": True,
                    "explicit_F_released": False,
                    "retained_explicit_F": False,
                    "D_i_released": True,
                    "construction_temporaries_released": True,
                    "retained_peak_limit_gib": V8_H4_LAYER_SWEEP_RETAINED_LIMIT_GIB,
                    "resource_gate": "not_run_numerical_gate_failed",
                },
            )
        spool_released = spool is not None
        spool = None
        preferred_woodbury_destroyed = preferred_woodbury is not None
        if preferred_woodbury is not None:
            preferred_woodbury.destroy()
            preferred_woodbury = None
        released = _destroy_v5_side_components(components)
        system_probe = {
            "status": "not_available",
            "global_size": None,
            "ownership_range": None,
        }
        if getattr(system, "A", None) is not None:
            system_probe = {
                "status": "measured",
                "global_size": list(map(int, system.A.getSize())),
                "ownership_range": list(map(int, system.A.getOwnershipRange())),
            }
        system_destroy_called = False
        if hasattr(system, "destroy"):
            system.destroy()
            system_destroy_called = True
        if sweep is not None:
            sweep.destroy()
            sweep_destroyed = True
            sweep_diagnostics_after_cleanup = deepcopy(sweep.diagnostics)
        cleanup = collective_heap_cleanup(comm)
        marker_callback(
            "v8_layer_sweep_bottom_retained_state_release",
            {
                "preferred_woodbury_destroyed": preferred_woodbury_destroyed,
                "retained_probe": retained_probe,
                "system_destroy_called": system_destroy_called,
                "factor_count_after_cleanup": int(
                    sweep_diagnostics_after_cleanup.get("layer_factor_count", 0)
                ),
                "sweep_destroyed": sweep_destroyed,
                "spool_released": spool_released,
                "collective_cleanup": cleanup,
            },
        )
        numerical_holdout_gate_pass = first_passing_method is not None
        gate = {
            "methods": method_records,
            "first_passing_method": first_passing_method,
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
            "numerical_holdout_gate_pass": numerical_holdout_gate_pass,
            "resource_gate": "pending_parent_process_tree_samples",
            "resource_gate_limits_gib": {
                "construction": V8_H4_LAYER_SWEEP_CONSTRUCTION_LIMIT_GIB,
                "retained": V8_H4_LAYER_SWEEP_RETAINED_LIMIT_GIB,
            },
            "qualification_status": "pending_parent_process_tree_samples",
            "pass": None,
        }
        completed = True
        return {
            "schema": V8_H4_LAYER_SWEEP_SCHEMA,
            "method": V8_H4_LAYER_SWEEP_METHOD,
            "profile_id": V8_H4_LAYER_SWEEP_PROFILE_ID,
            "status": (
                "component_numerical_pass_resource_pending"
                if numerical_holdout_gate_pass
                else "component_numerical_failed"
            ),
            "side": "bottom",
            "method_records": method_records,
            "gate": gate,
            "factor_inventory": {
                "layer_factor_count": 6,
                "layer_factor_count_ready": 6,
                "layer_factor_count_after_cleanup": 0,
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
            },
            "selected_mode_packet_opened": False,
            "holdout_opened": True,
            "exact_spool_opened": True,
            "qep_count": 0,
            "modal_schur": "not_run",
            "outer_ksp": "not_run",
            "recovery": "not_run",
            "field": "not_run",
            "RTA": "not_run",
            "lifecycle": {
                "components": released,
                "system_probe": system_probe,
                "collective_cleanup": cleanup,
                "woodbury_destroyed_between_methods": True,
                "preferred_woodbury": preferred_woodbury_diagnostics,
                "retained_probe": retained_probe,
                "factor_count_ready": 6,
                "factor_count_after_cleanup": 0,
                "factor_inventory_ready": 6,
                "factor_inventory_after_cleanup": 0,
                "sweep_destroyed": sweep_destroyed,
                "sweep_diagnostics_after_cleanup": sweep_diagnostics_after_cleanup,
                "spool_released": spool_released,
            },
            "telemetry": {
                "process_tree_samples": {
                    "path": "numerical_output/process_tree_samples.jsonl",
                    "writer": "parent_task038_launcher",
                },
                "memory_stages": {
                    "path": "numerical_output/memory_stages.jsonl",
                    "writer": "parent_task038_launcher_marker_alignment",
                },
                "memory_stage_markers": {
                    "path": "numerical_output/memory_stage_markers.raw.jsonl",
                    "writer": "v3_7_worker",
                },
                "memory_object_ledger": {
                    "path": "numerical_output/memory_object_ledger.json",
                    "status": "finalized_in_worker_finalizer",
                },
                "gate_contract": {
                    "construction_peak_limit_gib": V8_H4_LAYER_SWEEP_CONSTRUCTION_LIMIT_GIB,
                    "retained_peak_limit_gib": V8_H4_LAYER_SWEEP_RETAINED_LIMIT_GIB,
                    "swap_required": 0,
                    "full_side_exact_factor_count": 0,
                    "global_direct_factor_count": 0,
                    "nested_ksp_count": 0,
                },
            },
        }
    finally:
        if not completed:
            if preferred_woodbury is not None:
                preferred_woodbury.destroy()
            if components is not None:
                _destroy_v5_side_components(components)
            if system is not None and hasattr(system, "destroy"):
                system.destroy()
            if sweep is not None:
                sweep.destroy()
            collective_heap_cleanup(comm)


def _v10_sn2_j_advancement_gate(
    reports: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Evaluate the strict V10 SN2-J advancement contract."""

    expected = set(V6_PORT_MODAL_HOLDOUT_LABELS)
    labels = [report.get("label") for report in reports]
    if len(labels) != len(expected) or set(labels) != expected:
        raise ValueError("V10 SN2-J requires the frozen unique six holdout labels")
    if len(set(labels)) != len(labels):
        raise ValueError("V10 SN2-J holdout labels are not unique")
    physical_label = "physical_side_rhs"
    for report in reports:
        if not isinstance(report.get("degenerate_uninformative"), bool):
            raise ValueError("V10 SN2-J reports lack degeneracy metadata")
        if report["label"] != physical_label and report["degenerate_uninformative"]:
            raise ValueError("Only physical_side_rhs may be degenerate")

    physical = [report for report in reports if report["label"] == physical_label]
    if len(physical) != 1:
        raise ValueError("V10 SN2-J requires exactly one physical_side_rhs report")
    physical_degenerate = physical[0]["degenerate_uninformative"] is True
    mandatory = [
        report
        for report in reports
        if not (
            report["label"] == physical_label and report["degenerate_uninformative"]
        )
    ]
    if physical_degenerate:
        solution_norm = physical[0].get("solution_norm")
        zero_output_pass = bool(
            isinstance(solution_norm, (int, float))
            and np.isfinite(float(solution_norm))
            and float(solution_norm) <= 1.0e-13
            and physical[0].get("zero_output_pass") is True
        )
        zero_output_status = "measured_pass" if zero_output_pass else "failed"
    else:
        zero_output_pass = True
        zero_output_status = "not_applicable"
    expected_mandatory_count = len(reports) - (1 if physical_degenerate else 0)
    finite_pass = all(report.get("finite") is True for report in reports)
    repeat_values = [report.get("repeat_relative_error") for report in reports]
    linearity_values = [report.get("linearity_relative_error") for report in reports]
    repeat_pass = bool(
        all(
            value is not None and np.isfinite(float(value)) and float(value) <= 1.0e-10
            for value in repeat_values
        )
    )
    linearity_pass = bool(
        all(
            value is not None and np.isfinite(float(value)) and float(value) <= 1.0e-10
            for value in linearity_values
        )
    )
    residual_values = [report.get("r_F") for report in mandatory]
    residual_finite_pass = bool(
        len(mandatory) == expected_mandatory_count
        and expected_mandatory_count > 0
        and all(
            value is not None and np.isfinite(float(value)) for value in residual_values
        )
    )
    worst_residual = (
        max(float(value) for value in residual_values) if residual_finite_pass else None
    )
    residual_pass_1e2 = bool(
        residual_finite_pass
        and all(float(value) <= 1.0e-2 for value in residual_values)
    )
    preferred_labels = {
        "modal_traction_positive",
        "modal_traction_negative",
        "external_dtn_coupling",
    }
    preferred = [report for report in mandatory if report["label"] in preferred_labels]
    preferred_values = [report.get("r_F") for report in preferred]
    preferred_pass_1e3 = bool(
        len(preferred) == 3
        and all(
            value is not None and np.isfinite(float(value)) and float(value) <= 1.0e-3
            for value in preferred_values
        )
    )
    preferred_finite_values = [
        float(value)
        for value in preferred_values
        if isinstance(value, (int, float)) and np.isfinite(float(value))
    ]
    preferred_residual_max = (
        max(preferred_finite_values) if preferred_finite_values else None
    )
    numerical_gate_pass = bool(
        finite_pass
        and zero_output_pass
        and repeat_pass
        and linearity_pass
        and residual_finite_pass
        and worst_residual is not None
        and worst_residual < V10_H4_SN2_J_ONLY_RESIDUAL_LIMIT
    )
    return {
        "finite_pass": finite_pass,
        "zero_output_pass": zero_output_pass,
        "zero_output_status": zero_output_status,
        "repeat_pass": repeat_pass,
        "linearity_pass": linearity_pass,
        "residual_finite_pass": residual_finite_pass,
        "residual_pass_1e2": residual_pass_1e2,
        "residual_limit_1e2": 1.0e-2,
        "preferred_residual_max": preferred_residual_max,
        "preferred_residual_pass_1e3": preferred_pass_1e3,
        "preferred_residual_limit_1e3": 1.0e-3,
        "worst_mandatory_r_F": worst_residual,
        "worst_mandatory_r_F_limit": V10_H4_SN2_J_ONLY_RESIDUAL_LIMIT,
        "mandatory_labels": [report["label"] for report in mandatory],
        "degenerate_labels": [
            report["label"] for report in reports if report["degenerate_uninformative"]
        ],
        "numerical_gate_pass": numerical_gate_pass,
        "numerical_stability_gate_pass": numerical_gate_pass,
        "pass": numerical_gate_pass,
    }


def _v9_layer_supernode_stability_gate(
    reports: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Select a stable SN2 candidate without making residual a hard stop."""

    expected_labels = set(V6_PORT_MODAL_HOLDOUT_LABELS)
    labels = [report.get("label") for report in reports]
    if len(labels) != len(expected_labels) or set(labels) != expected_labels:
        raise ValueError("V9-2 requires the frozen unique six holdout labels")
    if len(set(labels)) != len(labels):
        raise ValueError("V9-2 holdout labels are not unique")
    physical = "physical_side_rhs"
    for report in reports:
        if not isinstance(report.get("degenerate_uninformative"), bool):
            raise ValueError("V9-2 holdout reports lack degeneracy metadata")
        if report["label"] != physical and report["degenerate_uninformative"]:
            raise ValueError("Only physical_side_rhs may be degenerate")
    mandatory = [
        report
        for report in reports
        if not (report["label"] == physical and report["degenerate_uninformative"])
    ]
    residual_values = [
        report.get("r_F", report.get("true_residual_relative")) for report in mandatory
    ]
    residual_finite_pass = bool(
        residual_values
        and all(value is not None and np.isfinite(value) for value in residual_values)
    )
    finite_pass = all(report.get("finite") is True for report in reports)
    repeat_pass = all(
        report.get("repeat_relative_error") is not None
        and report["repeat_relative_error"] <= 1.0e-10
        for report in reports
    )
    linearity_pass = all(
        report.get("linearity_relative_error") is not None
        and report["linearity_relative_error"] <= 1.0e-10
        for report in reports
    )
    worst_residual = (
        max(float(value) for value in residual_values) if residual_finite_pass else None
    )
    residual_pass = bool(
        residual_finite_pass
        and all(float(value) <= 1.0e-2 for value in residual_values)
    )
    stable = bool(
        finite_pass and residual_finite_pass and repeat_pass and linearity_pass
    )
    return {
        "finite_pass": bool(finite_pass),
        "repeat_pass": bool(repeat_pass),
        "linearity_pass": bool(linearity_pass),
        "residual_finite_pass": bool(residual_finite_pass),
        "residual_pass": bool(residual_pass),
        "residual_limit": 1.0e-2,
        "worst_mandatory_r_F": worst_residual,
        "mandatory_labels": [report["label"] for report in mandatory],
        "degenerate_labels": [
            report["label"] for report in reports if report["degenerate_uninformative"]
        ],
        "numerical_stability_gate_pass": stable,
        "pass": stable,
    }


def run_v9_h4_layer_supernode_bottom_component(
    cfg: Any,
    *,
    profile: Any,
    comm: MPI.Intracomm,
    marker_callback: Callable[[str, Mapping[str, Any]], None],
    exact_spool_root: str | Path,
    source_sha: str,
    side_system_builder: Callable[..., Any] | None = None,
    holdout_loader: Callable[..., Any] | None = None,
    holdout_runner: Callable[..., list[dict[str, Any]]] | None = None,
    retained_runner: Callable[..., Mapping[str, Any]] | None = None,
    method_names: tuple[str, ...] = ("SN2-J", "SN2-SGS"),
    gate_evaluator: Callable[[list[Mapping[str, Any]]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the V9-2 bottom SN2 candidate contract without a full solve.

    The default path uses the frozen exact-response spool and the real sparse
    side ``F``.  ``holdout_runner`` and ``retained_runner`` are narrow test
    seams only; they let lifecycle tests avoid opening h4 artifacts while
    exercising the same route and ownership order.
    """

    system = None
    components = None
    action = None
    spool: dict[str, Any] = {}
    spool_released = False
    preferred_method: str | None = None
    method_records: dict[str, dict[str, Any]] = {}
    retained_probe: Mapping[str, Any] | None = None
    completed = False

    class _SupernodeProbeView:
        def __init__(self, candidate: Any, method: str, operator: Any) -> None:
            self.candidate = candidate
            self.method = method
            self.operator = operator

        def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
            self.candidate.apply_checkpoint(self.method, source, target)

    marker_callback(
        "v9_layer_supernode_bottom_construction_begin",
        {
            "construction_peak_limit_gib": V9_H4_LAYER_SUPERNODE_CONSTRUCTION_LIMIT_GIB,
            "retained_peak_limit_gib": V9_H4_LAYER_SUPERNODE_RETAINED_LIMIT_GIB,
            "selected_mode_packet_opened": False,
            "exact_spool_opened": False,
            "qep_count": 0,
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
        },
    )
    try:
        if side_system_builder is None:
            system = assemble_hybrid_local_dtn_action_system(
                cfg,
                "bottom",
                bottom_interface_z_nm=profile.bottom_interface_nm,
                top_interface_z_nm=profile.top_interface_nm,
                comm=comm,
                log=None,
            )
        else:
            system = side_system_builder(
                side="bottom", cfg=cfg, profile=profile, comm=comm
            )
        components = _build_research_explicit_side_components(system)
        labels, mapping_metadata = build_real_layer_labels(components.F, system)
        layer_count = len(mapping_metadata["z_layer_boundaries"]) - 1
        if layer_count != 6:
            raise ValueError(
                f"V9-2 supernode route requires exactly six layers, got {layer_count}"
            )
        action = build_fixed_two_layer_supernode_action(
            components.F,
            labels,
            layer_count=layer_count,
            lifecycle_callback=marker_callback,
        )
        del labels, mapping_metadata
        marker_callback(
            "v9_layer_supernode_bottom_factors_ready",
            {
                "factor_count": action.diagnostics["factor_count_ready"],
                "factor_set_build_count": action.diagnostics["factor_set_build_count"],
                "supernode_row_coverage_exact": action.diagnostics[
                    "supernode_row_coverage_exact"
                ],
                "cross_lower_block_count": action.diagnostics[
                    "cross_lower_block_count"
                ],
                "cross_upper_block_count": action.diagnostics[
                    "cross_upper_block_count"
                ],
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
            },
        )

        if holdout_loader is None:
            identity, manifest_sha256, catalog = _v9_frozen_holdout_identity(
                exact_spool_root, comm
            )
            spool = _load_v5_fixed_budget_spool_shards(
                exact_spool_root,
                comm,
                packet_identity=identity,
                manifest_sha256=manifest_sha256,
            )
            holdout_provenance = {
                "identity": identity,
                "manifest_sha256": manifest_sha256,
                "catalog_authority": catalog,
            }
        else:
            loaded = holdout_loader(exact_spool_root, comm)
            spool, holdout_provenance = loaded
        marker_callback(
            "v9_layer_supernode_bottom_holdout_ready",
            {
                "exact_spool_opened": True,
                "selected_mode_packet_opened": False,
                "holdout_labels": list(spool),
            },
        )

        def default_runner(method: str) -> list[dict[str, Any]]:
            view = _SupernodeProbeView(action, method, components.F)
            bare_f_system = SimpleNamespace(A=components.F)
            reports: list[dict[str, Any]] = []
            for label, artifact in spool.items():
                template = rhs = retained = None
                try:
                    template = components.F.createVecLeft()
                    rhs = _load_v5_blr_reference_spool_remapped(
                        artifact["rhs"], template
                    )
                    report, retained = _v5_blr_probe(
                        view,
                        bare_f_system,
                        rhs,
                        dict(artifact["rhs"]["probe_metadata"]),
                        None,
                        repeat=True,
                        linearity=True,
                        retain_output=True,
                    )
                    report["label"] = label
                    report["r_F"] = report["true_residual_relative"]
                    reports.append(report)
                finally:
                    if retained is not None:
                        retained.destroy()
                    if rhs is not None:
                        rhs.destroy()
                    if template is not None:
                        template.destroy()
            return reports

        def default_retained_runner(method: str) -> dict[str, Any]:
            view = _SupernodeProbeView(action, method, components.F)
            bare_f_system = SimpleNamespace(A=components.F)
            for label, artifact in spool.items():
                metadata = dict(artifact["rhs"]["probe_metadata"])
                if metadata.get("degenerate_uninformative"):
                    continue
                template = rhs = None
                try:
                    template = components.F.createVecLeft()
                    rhs = _load_v5_blr_reference_spool_remapped(
                        artifact["rhs"], template
                    )
                    report, _ = _v5_blr_probe(
                        view,
                        bare_f_system,
                        rhs,
                        metadata,
                        None,
                        repeat=True,
                        linearity=True,
                    )
                    return {
                        "status": "measured",
                        "label": label,
                        "operator": "components.F",
                        "reference_used": False,
                        "r_F": report["true_residual_relative"],
                        "finite": report["finite"],
                        "repeat_relative_error": report["repeat_relative_error"],
                        "linearity_relative_error": report["linearity_relative_error"],
                    }
                finally:
                    if rhs is not None:
                        rhs.destroy()
                    if template is not None:
                        template.destroy()
            raise ValueError("V9-2 retained probe requires a nondegenerate RHS")

        for method in method_names:
            marker_callback(
                f"v9_layer_supernode_bottom_{method}_begin",
                {"method": method, "factor_count": 3},
            )
            reports = (
                holdout_runner(
                    method=method,
                    action=action,
                    system=system,
                    components=components,
                    spool=spool,
                )
                if holdout_runner is not None
                else default_runner(method)
            )
            gate = (
                gate_evaluator(reports)
                if gate_evaluator is not None
                else _v9_layer_supernode_stability_gate(reports)
            )
            method_records[method] = {
                "method": method,
                "reports": reports,
                "gate": gate,
                "factor_set_build_count": 1,
                "factor_count": 3,
            }
            marker_callback(
                f"v9_layer_supernode_bottom_{method}_cleanup",
                {
                    "method": method,
                    "factor_count": 3,
                    "method_temporaries_released": True,
                    "factors_retained_for_next_method": True,
                },
            )
            marker_callback(
                f"v9_layer_supernode_bottom_{method}_complete",
                {"method": method, "gate": gate},
            )

        stable_methods = [
            method
            for method, record in method_records.items()
            if record["gate"]["numerical_stability_gate_pass"]
        ]
        if stable_methods:
            preferred_method = min(
                stable_methods,
                key=lambda method: method_records[method]["gate"][
                    "worst_mandatory_r_F"
                ],
            )
        marker_callback(
            "v9_layer_supernode_bottom_construction_end",
            {
                "methods_evaluated": list(method_records),
                "preferred_method": preferred_method,
                "factor_count": 3,
                "construction_temporaries_released": True,
                "resource_gate": "pending_parent_process_tree_samples",
            },
        )

        if preferred_method is not None:
            marker_callback(
                "v9_layer_supernode_bottom_retained_apply_state_ready",
                {
                    "preferred_method": preferred_method,
                    "factor_count": 3,
                    "preferred_action_rehydration": False,
                    "retained_peak_limit_gib": V9_H4_LAYER_SUPERNODE_RETAINED_LIMIT_GIB,
                    "retained_apply_state_valid": True,
                    "resource_gate": "pending_parent_process_tree_samples",
                },
            )
            if retained_runner is None:
                retained_probe = default_retained_runner(preferred_method)
            else:
                retained_probe = retained_runner(
                    method=preferred_method,
                    action=action,
                    system=system,
                    components=components,
                    spool=spool,
                )
            marker_callback(
                "v9_layer_supernode_bottom_retained_apply",
                {
                    "preferred_method": preferred_method,
                    "retained_probe": retained_probe,
                    "factor_count": 3,
                },
            )
        else:
            marker_callback(
                "v9_layer_supernode_bottom_retained_apply_state_not_run",
                {
                    "preferred_method": None,
                    "factor_count": 3,
                    "reason": "no_stable_candidate",
                    "resource_gate": "not_run_no_stable_candidate",
                },
            )
        spool_released = True
        spool = {}
        if action is not None:
            action.destroy()
        factor_diagnostics_after_cleanup = action.diagnostics if action else {}
        released = _destroy_v5_side_components(components)
        system_probe = {
            "status": "measured",
            "global_size": list(map(int, system.A.getSize())),
            "ownership_range": list(map(int, system.A.getOwnershipRange())),
        }
        system.destroy()
        cleanup = collective_heap_cleanup(comm)
        marker_callback(
            "v9_layer_supernode_bottom_retained_state_release",
            {
                "preferred_method": preferred_method,
                "retained_probe": retained_probe,
                "factor_count_after_cleanup": factor_diagnostics_after_cleanup.get(
                    "factor_count_after_cleanup", 0
                ),
                "components_released": released,
                "system_probe": system_probe,
                "collective_cleanup": cleanup,
            },
        )
        completed = True
        stable_pass = preferred_method is not None
        telemetry = {
            "process_tree_samples": {
                "path": "numerical_output/process_tree_samples.jsonl",
                "writer": "parent_task038_launcher",
                "status": "expected_from_parent_launcher",
            },
            "memory_stages": {
                "path": "numerical_output/memory_stages.jsonl",
                "writer": "parent_task038_launcher_marker_alignment",
                "status": "expected_from_parent_launcher",
            },
            "memory_stage_markers": {
                "path": "numerical_output/memory_stage_markers.raw.jsonl",
                "writer": "v3_7_worker",
                "status": "measured_worker_marker_stream",
            },
            "memory_object_ledger": {
                "path": "numerical_output/memory_object_ledger.json",
                "schema": "task039.v3-7-memory-object-ledger.v1",
                "status": "finalized_in_worker_finalizer",
            },
            "gate_contract": {
                "construction_peak_limit_gib": (
                    V9_H4_LAYER_SUPERNODE_CONSTRUCTION_LIMIT_GIB
                ),
                "retained_peak_limit_gib": (V9_H4_LAYER_SUPERNODE_RETAINED_LIMIT_GIB),
                "factor_count_ready": 3,
                "factor_count_after_cleanup": 0,
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
                "selected_mode_packet_opened": False,
                "qep_count": 0,
                "residual_1e2": "record_only",
                "resource_gate": "pending_parent_process_tree_samples",
            },
        }
        return {
            "schema": V9_H4_LAYER_SUPERNODE_SCHEMA,
            "method": V9_H4_LAYER_SUPERNODE_METHOD,
            "profile_id": V9_H4_LAYER_SUPERNODE_PROFILE_ID,
            "status": (
                "component_stable_preferred_resource_pending"
                if stable_pass
                else "component_stability_failed"
            ),
            "source_sha": source_sha,
            "method_records": method_records,
            "preferred_method": preferred_method,
            "gate": {
                "numerical_stability_gate_pass": stable_pass,
                "residual_1e2_is_record_only": True,
                "resource_gate": "pending_parent_process_tree_samples",
                "construction_limit_gib": V9_H4_LAYER_SUPERNODE_CONSTRUCTION_LIMIT_GIB,
                "retained_limit_gib": V9_H4_LAYER_SUPERNODE_RETAINED_LIMIT_GIB,
                "pass": None,
            },
            "factor_inventory": {
                "factor_count_ready": 3,
                "factor_count_after_cleanup": 0,
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
            },
            "selected_mode_packet_opened": False,
            "holdout_opened": True,
            "exact_spool_opened": True,
            "holdout_provenance": holdout_provenance,
            "qep_count": 0,
            "outer_ksp": "not_run",
            "recovery": "not_run",
            "field": "not_run",
            "lifecycle": {
                "components": released,
                "system_probe": system_probe,
                "collective_cleanup": cleanup,
                "spool_released": spool_released,
                "factor_diagnostics_after_cleanup": factor_diagnostics_after_cleanup,
                "retained_probe": retained_probe,
            },
            "telemetry": telemetry,
        }
    finally:
        if not completed:
            if action is not None:
                action.destroy()
            if components is not None:
                _destroy_v5_side_components(components)
            if system is not None and hasattr(system, "destroy"):
                system.destroy()
            collective_heap_cleanup(comm)


def run_v10_h4_supernode_factor_integrity(
    cfg: Any,
    *,
    profile: Any,
    comm: MPI.Intracomm,
    marker_callback: Callable[[str, Mapping[str, Any]], None],
    exact_spool_root: str | Path,
    source_sha: str,
    side_system_builder: Callable[..., Any] | None = None,
    holdout_loader: Callable[..., Any] | None = None,
    forensic_runner: Callable[..., Mapping[str, Any]] | None = None,
    boundary_runner: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the V10 sequential factor-integrity forensic.

    Only one supernode matrix/factor path is resident at a time.  The two
    path comparison and all residual arithmetic live in the reusable solver
    helper; this function owns the h4 identity, RHS assembly, markers, and
    cleanup order.  ``forensic_runner`` and ``boundary_runner`` are narrow
    fake-worker seams for lifecycle tests and are not part of the CLI.
    """

    system = None
    components = None
    labels = None
    group_is: list[PETSc.IS] = []
    spool: Mapping[str, Any] = {}
    group_reports: list[dict[str, Any]] = []
    boundary_report: Mapping[str, Any] = {
        "status": "not_run",
        "pass": False,
    }
    lifecycle: list[str] = []
    completed = False

    def emit(stage: str, detail: Mapping[str, Any] | None = None) -> None:
        lifecycle.append(stage)
        marker_callback(stage, {} if detail is None else detail)

    emit(
        "v10_layer_supernode_bottom_construction_begin",
        {
            "construction_peak_limit_gib": (
                V10_H4_SUPERNODE_FACTOR_INTEGRITY_CONSTRUCTION_LIMIT_GIB
            ),
            "retained_state": "not_run",
            "selected_mode_packet_opened": False,
            "exact_spool_opened": False,
            "qep_count": 0,
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
            "sgs_executed": False,
        },
    )
    try:
        if side_system_builder is None:
            system = assemble_hybrid_local_dtn_action_system(
                cfg,
                "bottom",
                bottom_interface_z_nm=profile.bottom_interface_nm,
                top_interface_z_nm=profile.top_interface_nm,
                comm=comm,
                log=None,
            )
        else:
            system = side_system_builder(
                side="bottom", cfg=cfg, profile=profile, comm=comm
            )
        components = _build_research_explicit_side_components(system)
        labels, mapping_metadata = build_real_layer_labels(components.F, system)
        if len(mapping_metadata["z_layer_boundaries"]) - 1 != 6:
            raise ValueError("V10 forensic requires exactly six layers")
        row_start, row_end = map(int, components.F.getOwnershipRange())
        for first, second in ((0, 1), (2, 3), (4, 5)):
            local_ids = (
                np.flatnonzero(
                    np.isin(labels[row_start:row_end], (first, second))
                ).astype(PETSc.IntType)
                + row_start
            )
            group_is.append(
                PETSc.IS().createGeneral(local_ids, comm=components.F.getComm())
            )
        if holdout_loader is None:
            identity, manifest_sha256, catalog = _v9_frozen_holdout_identity(
                exact_spool_root, comm
            )
            spool = _load_v5_fixed_budget_spool_shards(
                exact_spool_root,
                comm,
                packet_identity=identity,
                manifest_sha256=manifest_sha256,
            )
            holdout_provenance = {
                "identity": identity,
                "manifest_sha256": manifest_sha256,
                "catalog_authority": catalog,
            }
        else:
            loaded = holdout_loader(exact_spool_root, comm)
            spool, holdout_provenance = loaded
        emit(
            "v10_layer_supernode_bottom_holdout_ready",
            {
                "exact_spool_opened": True,
                "selected_mode_packet_opened": False,
                "rhs_types": [
                    "zero_rhs",
                    "deterministic_random",
                    "modal_traction_positive",
                    "external_dtn_coupling",
                ],
            },
        )

        def make_rhs_vectors(
            group: int, group_matrix: PETSc.Mat, group_index: PETSc.IS
        ) -> dict[str, PETSc.Vec]:
            rhs: dict[str, PETSc.Vec] = {}
            zero = group_matrix.createVecRight()
            zero.set(0.0)
            rhs["zero_rhs"] = zero
            random = zero.duplicate()
            random.set(0.0)
            start, stop = map(int, random.getOwnershipRange())
            indices = np.arange(start, stop, dtype=np.float64)
            random.getArray()[:] = np.asarray(
                np.sin(indices * 0.001 + 739 + group)
                + 1j * np.cos(indices * 0.0007 - 743 - group),
                dtype=PETSc.ScalarType,
            )
            norm = float(random.norm())
            if norm:
                random.scale(1.0 / norm)
            random.assemble()
            rhs["deterministic_random"] = random

            def load_restricted(label: str) -> PETSc.Vec:
                artifact = spool.get(label)
                if not isinstance(artifact, Mapping):
                    raise ValueError(f"V10 frozen RHS is missing {label}")
                parent_template = components.F.createVecLeft()
                parent_rhs = None
                group_rhs = group_matrix.createVecRight()
                positions = PETSc.IS().createStride(
                    int(group_rhs.getLocalSize()),
                    first=int(group_rhs.getOwnershipRange()[0]),
                    step=1,
                    comm=components.F.getComm(),
                )
                scatter = None
                try:
                    group_rhs.set(0.0)
                    parent_rhs = _load_v5_blr_reference_spool_remapped(
                        artifact["rhs"], parent_template
                    )
                    scatter = PETSc.Scatter().create(
                        parent_rhs, group_index, group_rhs, positions
                    )
                    scatter.scatter(
                        parent_rhs,
                        group_rhs,
                        addv=PETSc.InsertMode.INSERT_VALUES,
                        mode=PETSc.ScatterMode.FORWARD,
                    )
                    return group_rhs
                except Exception:
                    group_rhs.destroy()
                    raise
                finally:
                    if scatter is not None:
                        scatter.destroy()
                    positions.destroy()
                    if parent_rhs is not None:
                        parent_rhs.destroy()
                    parent_template.destroy()

            rhs["modal_traction_positive"] = load_restricted("modal_traction_positive")
            rhs["external_dtn_coupling"] = load_restricted("external_dtn_coupling")
            return rhs

        for group, (first, second) in enumerate(((0, 1), (2, 3), (4, 5))):
            emit(
                f"v10_layer_supernode_bottom_B{group}_factor_forensic_path_begin",
                {"group": group, "layers": [first, second]},
            )
            group_matrix = components.F.createSubMatrix(
                group_is[group], group_is[group]
            )
            rhs_vectors = None
            try:
                rhs_vectors = make_rhs_vectors(group, group_matrix, group_is[group])
                if forensic_runner is None:
                    report = audit_supernode_factor_paths(
                        group_matrix,
                        rhs_vectors,
                        lifecycle_callback=(
                            lambda event, detail, group=group: emit(
                                f"v10_layer_supernode_bottom_B{group}_{event}",
                                detail,
                            )
                        ),
                    )
                else:
                    report = dict(
                        forensic_runner(
                            group=group,
                            layers=(first, second),
                            matrix=group_matrix,
                            rhs_vectors=rhs_vectors,
                            components=components,
                        )
                    )
                report["group"] = group
                report["layers"] = [first, second]
                group_reports.append(report)
            finally:
                if rhs_vectors is not None:
                    for vector in rhs_vectors.values():
                        vector.set(0.0)
                        vector.destroy()
                group_matrix.destroy()
            emit(
                f"v10_layer_supernode_bottom_B{group}_factor_forensic_path_cleanup",
                {"group": group, "factor_count_after_cleanup": 0},
            )

        paths_pass = all(
            report.get("paths", {}).get("A_conventional_ksp", {}).get("path_pass")
            is True
            and report.get("paths", {})
            .get("B_factor_only_detached", {})
            .get("path_pass")
            is True
            for report in group_reports
        )
        if paths_pass:
            emit("v10_layer_supernode_bottom_sn2_j_boundary_begin")
            if boundary_runner is None:
                boundary_action = build_fixed_two_layer_supernode_action(
                    components.F,
                    labels,
                    layer_count=6,
                )
                source = components.F.createVecRight()
                target = source.duplicate()
                roundtrip = source.duplicate()
                one_group = source.duplicate()
                three_group = source.duplicate()
                local_start, local_stop = map(int, source.getOwnershipRange())
                local_labels = labels[local_start:local_stop]
                indices = np.arange(local_start, local_stop, dtype=np.float64)
                source.set(0.0)
                source.getArray()[:] = np.asarray(
                    np.sin(indices * 0.001 + 761) + 1j * np.cos(indices * 0.0007 - 763),
                    dtype=PETSc.ScalarType,
                )
                source.assemble()
                zero_result: dict[str, Any]
                one_result: dict[str, Any]
                three_result: dict[str, Any]
                target.set(0.0)
                try:
                    roundtrip.set(0.0)
                    for workspace in boundary_action._workspaces:
                        workspace.rhs.set(0.0)
                        workspace.scatter.scatter(
                            source,
                            workspace.rhs,
                            addv=PETSc.InsertMode.INSERT_VALUES,
                            mode=PETSc.ScatterMode.FORWARD,
                        )
                        workspace.scatter.scatter(
                            workspace.rhs,
                            roundtrip,
                            addv=PETSc.InsertMode.ADD_VALUES,
                            mode=PETSc.ScatterMode.REVERSE,
                        )
                    roundtrip.axpy(PETSc.ScalarType(-1.0), source)
                    roundtrip_error = float(roundtrip.norm()) / max(
                        float(source.norm()), 1.0e-30
                    )
                    source.set(0.0)
                    boundary_action.apply_checkpoint("SN2-J", source, target)
                    zero_norm = float(target.norm())
                    zero_result = {
                        "finite": bool(np.isfinite(zero_norm)),
                        "output_norm": zero_norm,
                        "pass": bool(np.isfinite(zero_norm) and zero_norm <= 1.0e-13),
                    }
                    one_group.set(0.0)
                    one_group.getArray()[:] = np.asarray(
                        np.where(
                            (local_labels == 0) | (local_labels == 1),
                            0.25 + np.sin(indices * 0.002),
                            0.0,
                        ),
                        dtype=PETSc.ScalarType,
                    )
                    one_group.assemble()
                    target.set(0.0)
                    boundary_action.apply_checkpoint("SN2-J", one_group, target)
                    one_norm = float(target.norm())
                    one_result = {
                        "finite": bool(np.isfinite(one_norm)),
                        "output_norm": one_norm,
                        "pass": bool(np.isfinite(one_norm)),
                    }
                    three_group.set(0.0)
                    three_group.getArray()[:] = np.asarray(
                        np.sin(indices * 0.001 + 769)
                        + 1j * np.cos(indices * 0.0007 - 773),
                        dtype=PETSc.ScalarType,
                    )
                    three_group.assemble()
                    source.set(0.0)
                    target.set(0.0)
                    boundary_action.apply_checkpoint("SN2-J", three_group, target)
                    three_norm = float(target.norm())
                    three_result = {
                        "finite": bool(np.isfinite(three_norm)),
                        "output_norm": three_norm,
                        "pass": bool(np.isfinite(three_norm)),
                    }
                    boundary_cases = (
                        ("SN2-J_zero_rhs", zero_result),
                        ("SN2-J_one_group_rhs", one_result),
                        ("SN2-J_three_group_rhs", three_result),
                    )
                    first_nonfinite_stage = next(
                        (
                            stage
                            for stage, result in boundary_cases
                            if not result["finite"]
                        ),
                        None,
                    )
                    for stage, result in boundary_cases:
                        result["first_nonfinite_stage"] = (
                            stage if not result["finite"] else None
                        )
                    boundary_report = {
                        "status": "measured",
                        "pass": bool(
                            np.isfinite(roundtrip_error)
                            and roundtrip_error <= 1.0e-12
                            and zero_result["pass"]
                            and one_result["pass"]
                            and three_result["pass"]
                            and first_nonfinite_stage is None
                        ),
                        "method": "SN2-J",
                        "sgs_executed": False,
                        "scatter_pass": bool(
                            np.isfinite(roundtrip_error) and roundtrip_error <= 1.0e-12
                        ),
                        "action_pass": bool(
                            zero_result["pass"]
                            and one_result["pass"]
                            and three_result["pass"]
                        ),
                        "parent_group_parent_roundtrip_relative_error": roundtrip_error,
                        "first_nonfinite_stage": first_nonfinite_stage,
                        "zero_rhs": zero_result,
                        "one_group_rhs": one_result,
                        "three_group_rhs": three_result,
                    }
                finally:
                    roundtrip.set(0.0)
                    one_group.set(0.0)
                    three_group.set(0.0)
                    source.set(0.0)
                    target.set(0.0)
                    roundtrip.destroy()
                    one_group.destroy()
                    three_group.destroy()
                    source.destroy()
                    target.destroy()
                    boundary_action.destroy()
            else:
                boundary_report = dict(boundary_runner(components=components))
            emit(
                "v10_layer_supernode_bottom_sn2_j_boundary_end",
                dict(boundary_report),
            )
        classification = (
            "SUPERNODE_FACTOR_INTEGRITY_PASS"
            if paths_pass and boundary_report.get("pass") is True
            else "SUPERNODE_PRINCIPAL_BLOCK_UNSTABLE"
        )
        all_a_pass = all(
            report.get("paths", {}).get("A_conventional_ksp", {}).get("path_pass")
            is True
            for report in group_reports
        )
        all_b_pass = all(
            report.get("paths", {}).get("B_factor_only_detached", {}).get("path_pass")
            is True
            for report in group_reports
        )
        scatter_pass = boundary_report.get("scatter_pass") is True
        if not all_a_pass and not all_b_pass:
            classification = "SUPERNODE_PRINCIPAL_BLOCK_UNSTABLE"
        elif all_a_pass and not all_b_pass:
            classification = "FACTOR_ONLY_DETACH_IMPLEMENTATION_FAILURE"
        elif all_a_pass and all_b_pass and not scatter_pass:
            classification = "SUPERNODE_SCATTER_LAYOUT_FAILURE"
        elif all_a_pass and all_b_pass and not boundary_report.get("action_pass"):
            classification = "SUPERNODE_ACTION_WORKSPACE_FAILURE"
        emit(
            "v10_layer_supernode_bottom_construction_end",
            {
                "classification": classification,
                "numerical_gate_pass": classification
                == "SUPERNODE_FACTOR_INTEGRITY_PASS",
                "resource_gate": "pending_parent_process_tree_samples",
                "retained_state": "not_run",
            },
        )
        emit(
            "v10_layer_supernode_bottom_retained_not_run",
            {"reason": "V10 forensic has no retained candidate"},
        )
        completed = True
        return {
            "schema": V10_H4_SUPERNODE_FACTOR_INTEGRITY_SCHEMA,
            "method": V10_H4_SUPERNODE_FACTOR_INTEGRITY_METHOD,
            "profile_id": V10_H4_SUPERNODE_FACTOR_INTEGRITY_PROFILE_ID,
            "status": "component_forensic_completed",
            "source_sha": source_sha,
            "group_records": group_reports,
            "boundary": boundary_report,
            "classification": classification,
            "gate": {
                "numerical_gate_pass": classification
                == "SUPERNODE_FACTOR_INTEGRITY_PASS",
                "resource_gate": "pending_parent_process_tree_samples",
                "retained_state": "not_run",
                "first_nonfinite_stage": (
                    boundary_report.get("first_nonfinite_stage")
                    or next(
                        (
                            report.get("first_nonfinite_stage")
                            for report in group_reports
                            if report.get("first_nonfinite_stage") is not None
                        ),
                        None,
                    )
                ),
            },
            "factor_inventory": {
                "factor_count_ready": 0,
                "factor_count_after_cleanup": 0,
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
            },
            "selected_mode_packet_opened": False,
            "exact_spool_opened": True,
            "qep_count": 0,
            "sgs_executed": False,
            "holdout_provenance": holdout_provenance,
            "lifecycle": {
                "event_order": lifecycle,
                "retained_state": "not_run",
                "components_released": "released_in_finalizer",
                "system_released": "destroy_called_in_finalizer",
            },
            "telemetry": {
                "process_tree_samples": {
                    "path": "numerical_output/process_tree_samples.jsonl",
                    "status": "expected_from_parent_launcher",
                },
                "memory_stages": {
                    "path": "numerical_output/memory_stages.jsonl",
                    "status": "expected_from_parent_launcher",
                },
                "memory_stage_markers": {
                    "path": "numerical_output/memory_stage_markers.raw.jsonl",
                    "status": "measured_worker_marker_stream",
                },
                "memory_object_ledger": {
                    "path": "numerical_output/memory_object_ledger.json",
                    "status": "finalized_in_worker_finalizer",
                },
                "gate_contract": {
                    "construction_peak_limit_gib": (
                        V10_H4_SUPERNODE_FACTOR_INTEGRITY_CONSTRUCTION_LIMIT_GIB
                    ),
                    "retained_state": "not_run",
                    "swap_required": 0,
                    "full_side_exact_factor_count": 0,
                    "global_direct_factor_count": 0,
                    "nested_ksp_count": 0,
                    "sgs_executed": False,
                },
            },
        }
    finally:
        if not completed:
            for group_index in range(len(group_is) - 1, -1, -1):
                group_is[group_index].destroy()
            if components is not None:
                _destroy_v5_side_components(components)
            if system is not None and hasattr(system, "destroy"):
                system.destroy()
            collective_heap_cleanup(comm)
        else:
            for group_index in range(len(group_is) - 1, -1, -1):
                group_is[group_index].destroy()
            released = _destroy_v5_side_components(components)
            if system is not None and hasattr(system, "destroy"):
                system.destroy()
            collective_heap_cleanup(comm)
            marker_callback(
                "v10_layer_supernode_bottom_cleanup",
                {
                    "components_released": released,
                    "system_destroy_called": True,
                    "factor_count_after_cleanup": 0,
                    "collective_cleanup": "completed",
                },
            )


def run_v10_h4_sn2_j_only(
    cfg: Any,
    *,
    profile: Any,
    comm: MPI.Intracomm,
    marker_callback: Callable[[str, Mapping[str, Any]], None],
    exact_spool_root: str | Path,
    source_sha: str,
    side_system_builder: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Run the explicit V10 SN2-J-only research route.

    The existing V9 lifecycle is reused with one fixed method name.  The
    wrapper changes only the route identity, holdout gate and marker prefix;
    it never calls the SGS method and never changes the V9 default path.
    """

    marker_map = {
        "construction_begin": "construction_begin",
        "factors_ready": "factors_ready",
        "holdout_ready": "holdout_ready",
        "SN2-J_begin": "SN2-J_begin",
        "SN2-J_cleanup": "SN2-J_cleanup",
        "SN2-J_complete": "SN2-J_complete",
        "construction_end": "construction_end",
        "retained_apply_state_ready": "retained_apply_state_ready",
        "retained_apply": "retained_apply",
        "retained_apply_state_not_run": "retained_apply_state_not_run",
        "retained_state_release": "retained_state_release",
    }

    def emit(marker: str, detail: Mapping[str, Any]) -> None:
        prefix = "v9_layer_supernode_bottom_"
        if marker.startswith(prefix):
            suffix = marker[len(prefix) :]
            marker = marker_map.get(suffix, suffix)
            marker = f"v10_sn2_j_bottom_{marker}"
        marker_callback(marker, {"v10_route": True, **dict(detail)})

    class _ProbeActionView:
        def __init__(self, candidate: Any, operator: Any) -> None:
            self.candidate = candidate
            self.operator = operator
            self.apply_count = 0

        def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
            self.candidate.apply_checkpoint("SN2-J", source, target)
            self.apply_count += 1

    retained_input: dict[str, Any] = {
        "label": None,
        "rhs": None,
    }

    def holdout_runner(
        *,
        method: str,
        action: Any,
        system: Any,
        components: Any,
        spool: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        if method != "SN2-J":
            raise ValueError("V10 SN2-J-only route received a non-J method")
        view = _ProbeActionView(action, components.F)
        bare_f_system = SimpleNamespace(A=components.F)
        reports: list[dict[str, Any]] = []
        for label, artifact in spool.items():
            template = rhs = None
            try:
                template = components.F.createVecLeft()
                rhs = _load_v5_blr_reference_spool_remapped(artifact["rhs"], template)
                report, _ = _v5_blr_probe(
                    view,
                    bare_f_system,
                    rhs,
                    dict(artifact["rhs"]["probe_metadata"]),
                    None,
                    repeat=True,
                    linearity=True,
                )
                report["label"] = label
                report["r_F"] = report["true_residual_relative"]
                report["mandatory"] = not (
                    label == "physical_side_rhs"
                    and bool(report["degenerate_uninformative"])
                )
                solution_norm = float(report["output"]["source_norm"])
                report["solution_norm"] = solution_norm
                report["zero_output_pass"] = bool(
                    not report["degenerate_uninformative"]
                    or (np.isfinite(solution_norm) and solution_norm <= 1.0e-13)
                )
                reports.append(report)
            finally:
                if rhs is not None:
                    rhs.destroy()
                if template is not None:
                    template.destroy()
        for label, artifact in spool.items():
            metadata = dict(artifact["rhs"]["probe_metadata"])
            if metadata.get("degenerate_uninformative"):
                continue
            template = None
            try:
                template = components.F.createVecLeft()
                retained_input["rhs"] = _load_v5_blr_reference_spool_remapped(
                    artifact["rhs"], template
                )
                retained_input["label"] = label
            finally:
                if template is not None:
                    template.destroy()
            break
        spool.clear()
        collective_heap_cleanup(comm)
        return reports

    def retained_runner(
        *,
        method: str,
        action: Any,
        system: Any,
        components: Any,
        spool: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if method != "SN2-J":
            raise ValueError("V10 retained route received a non-J method")
        rhs = retained_input.pop("rhs", None)
        label = retained_input.pop("label", None)
        if rhs is None or label is None:
            raise ValueError("V10 SN2-J retained probe requires a prepared RHS")
        view = _ProbeActionView(action, components.F)
        target = None
        try:
            target = components.F.createVecLeft()
            target.set(0.0)
            view.apply(rhs, target)
            output_norm = float(target.norm())
            residual = _v5_blr_true_residual(
                SimpleNamespace(A=components.F), rhs, target
            )
            return {
                "status": "measured",
                "label": label,
                "operator": "components.F",
                "reference_used": False,
                "apply_count": view.apply_count,
                "r_F": residual,
                "finite": bool(
                    np.isfinite(output_norm)
                    and residual is not None
                    and np.isfinite(residual)
                ),
                "solution_norm": output_norm,
                "repeat": "not_run",
                "linearity": "not_run",
            }
        finally:
            if target is not None:
                target.destroy()
            rhs.destroy()

    try:
        v9_result = run_v9_h4_layer_supernode_bottom_component(
            cfg,
            profile=profile,
            comm=comm,
            marker_callback=emit,
            exact_spool_root=exact_spool_root,
            source_sha=source_sha,
            side_system_builder=side_system_builder,
            holdout_runner=holdout_runner,
            retained_runner=retained_runner,
            method_names=("SN2-J",),
            gate_evaluator=_v10_sn2_j_advancement_gate,
        )
    finally:
        orphan_rhs = retained_input.get("rhs")
        if orphan_rhs is not None:
            orphan_rhs.destroy()
            retained_input["rhs"] = None
    method_record = v9_result["method_records"].get("SN2-J", {})
    holdout_gate = method_record.get("gate", {})
    numerical_pass = holdout_gate.get("numerical_gate_pass") is True
    preferred = v9_result.get("preferred_method")
    retained = v9_result.get("lifecycle", {}).get("retained_probe")
    if not numerical_pass:
        preferred = None
        retained = None
    lifecycle = dict(v9_result.get("lifecycle", {}))
    lifecycle.update(
        {
            "retained_state": "measured" if retained is not None else "not_run",
            "sgs_executed": False,
            "factor_count_ready": 3,
            "factor_count_after_cleanup": 0,
        }
    )
    return {
        "schema": V10_H4_SN2_J_ONLY_SCHEMA,
        "method": V10_H4_SN2_J_ONLY_METHOD,
        "profile_id": V10_H4_SN2_J_ONLY_PROFILE_ID,
        "status": (
            "component_sn2_j_stable_resource_pending"
            if numerical_pass
            else "component_sn2_j_numerical_failed"
        ),
        "source_sha": source_sha,
        "method_records": {"SN2-J": method_record},
        "preferred_method": preferred,
        "gate": {
            "numerical_gate_pass": numerical_pass,
            "numerical_stability_gate_pass": numerical_pass,
            "finite_pass": holdout_gate.get("finite_pass"),
            "zero_output_pass": holdout_gate.get("zero_output_pass"),
            "zero_output_status": holdout_gate.get("zero_output_status"),
            "repeat_pass": holdout_gate.get("repeat_pass"),
            "linearity_pass": holdout_gate.get("linearity_pass"),
            "residual_pass_1e2": holdout_gate.get("residual_pass_1e2"),
            "preferred_residual_max": holdout_gate.get("preferred_residual_max"),
            "preferred_residual_pass_1e3": holdout_gate.get(
                "preferred_residual_pass_1e3"
            ),
            "worst_mandatory_bare_f_residual": holdout_gate.get("worst_mandatory_r_F"),
            "worst_mandatory_bare_f_residual_limit": (V10_H4_SN2_J_ONLY_RESIDUAL_LIMIT),
            "construction_limit_gib": V10_H4_SN2_J_ONLY_CONSTRUCTION_LIMIT_GIB,
            "retained_limit_gib": V10_H4_SN2_J_ONLY_RETAINED_LIMIT_GIB,
            "resource_gate": "pending_parent_process_tree_samples",
            "retained_state": "measured" if retained is not None else "not_run",
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
            "sgs_executed": False,
            "selected_mode_packet_opened": False,
            "qep_count": 0,
        },
        "factor_inventory": {
            "factor_count_ready": 3,
            "factor_count_after_cleanup": 0,
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
        },
        "selected_mode_packet_opened": False,
        "holdout_opened": True,
        "exact_spool_opened": True,
        "qep_count": 0,
        "sgs_executed": False,
        "retained_probe": retained,
        "lifecycle": lifecycle,
        "telemetry": {
            "process_tree_samples": {
                "path": "numerical_output/process_tree_samples.jsonl",
                "writer": "parent_task038_launcher",
            },
            "memory_stages": {
                "path": "numerical_output/memory_stages.jsonl",
                "writer": "parent_task038_launcher_marker_alignment",
            },
            "memory_stage_markers": {
                "path": "numerical_output/memory_stage_markers.raw.jsonl",
                "writer": "v3_7_worker",
            },
            "memory_object_ledger": {
                "path": "numerical_output/memory_object_ledger.json",
                "status": "finalized_in_worker_finalizer",
            },
            "gate_contract": {
                "construction_peak_limit_gib": V10_H4_SN2_J_ONLY_CONSTRUCTION_LIMIT_GIB,
                "retained_peak_limit_gib": V10_H4_SN2_J_ONLY_RETAINED_LIMIT_GIB,
                "swap_required": 0,
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
                "sgs_executed": False,
            },
        },
    }


def _v10_j1_inner_fgmres_aggregate_gate(
    mandatory_records: list[Mapping[str, Any]],
    physical_zero_map: Mapping[str, Any],
) -> dict[str, Any]:
    """Aggregate V10-4 from one uniform checkpoint, not mixed final solves."""

    preferred_labels = {
        "modal_traction_positive",
        "modal_traction_negative",
        "external_dtn_coupling",
    }
    gate_by_checkpoint: dict[str, dict[str, Any]] = {}
    worst_by_iteration: dict[str, float | None] = {}
    for iteration in (4, 8, 16, 32):
        rows: dict[str, float | None] = {}
        missing_labels: list[str] = []
        nonfinite_labels: list[str] = []
        breakdown_labels: list[str] = []
        for record in mandatory_records:
            label = str(record["label"])
            row = record.get("checkpoints", {}).get(str(iteration))
            value = (
                row.get("explicit_true_residual") if isinstance(row, Mapping) else None
            )
            rows[label] = (
                float(value)
                if isinstance(value, (int, float)) and np.isfinite(float(value))
                else None
            )
            if not isinstance(row, Mapping):
                missing_labels.append(label)
            elif rows[label] is None or row.get("finite") is not True:
                nonfinite_labels.append(label)
            if record.get("ksp_breakdown") is not False:
                breakdown_labels.append(label)
        finite_values = [value for value in rows.values() if value is not None]
        preferred_values = [
            value
            for label, value in rows.items()
            if label in preferred_labels and value is not None
        ]
        worst = max(finite_values) if len(finite_values) == 5 else None
        preferred_max = max(preferred_values) if len(preferred_values) == 3 else None
        complete = bool(
            not missing_labels
            and not nonfinite_labels
            and not breakdown_labels
            and worst is not None
            and preferred_max is not None
        )
        gate_by_checkpoint[str(iteration)] = {
            "complete": complete,
            "pass": bool(complete and worst <= 1.0e-2 and preferred_max <= 1.0e-3),
            "values": rows,
            "worst_mandatory_true_residual": worst,
            "preferred_residual_max": preferred_max,
            "mandatory_limit": 1.0e-2,
            "preferred_limit": 1.0e-3,
            "missing_labels": missing_labels,
            "nonfinite_labels": nonfinite_labels,
            "breakdown_labels": breakdown_labels,
        }
        worst_by_iteration[str(iteration)] = worst

    preferred_inner_budget_value = next(
        (
            iteration
            for iteration in (4, 8, 16, 32)
            if gate_by_checkpoint[str(iteration)]["complete"]
            and gate_by_checkpoint[str(iteration)]["pass"]
        ),
        None,
    )
    preferred_checkpoint_pass = preferred_inner_budget_value is not None
    preferred_inner_budget = (
        preferred_inner_budget_value if preferred_checkpoint_pass else "not_applicable"
    )
    final_values = [
        record.get("final_independent_true_residual") for record in mandatory_records
    ]
    finite_final = [
        float(value)
        for value in final_values
        if isinstance(value, (int, float)) and np.isfinite(float(value))
    ]
    worst_final = max(finite_final) if len(finite_final) == 5 else None
    preferred_final_values = [
        record.get("final_independent_true_residual")
        for record in mandatory_records
        if record["label"] in preferred_labels
    ]
    preferred_finite = [
        float(value)
        for value in preferred_final_values
        if isinstance(value, (int, float)) and np.isfinite(float(value))
    ]
    preferred_residual_max = (
        max(preferred_finite) if len(preferred_finite) == 3 else None
    )
    all_checkpoint_finite = all(
        isinstance(row, Mapping)
        and row.get("finite") is True
        and isinstance(row.get("explicit_true_residual"), (int, float))
        and np.isfinite(float(row["explicit_true_residual"]))
        for record in mandatory_records
        for row in record.get("checkpoints", {}).values()
    )
    all_ksp_breakdown_false = all(
        record.get("ksp_breakdown") is False for record in mandatory_records
    )
    all_final_residuals_consistent = all(
        record.get("final_residual_consistent") is True for record in mandatory_records
    )
    all_final_finite = len(finite_final) == 5
    no_nonfinite = bool(
        all_checkpoint_finite
        and all_final_finite
        and all(
            record.get("first_nonfinite_stage") is None for record in mandatory_records
        )
    )
    finite16 = gate_by_checkpoint["16"]["complete"]
    global_trend_pass = bool(
        gate_by_checkpoint["4"]["complete"]
        and gate_by_checkpoint["8"]["complete"]
        and gate_by_checkpoint["16"]["complete"]
        and worst_by_iteration["4"] is not None
        and worst_by_iteration["8"] is not None
        and worst_by_iteration["16"] is not None
        and worst_by_iteration["16"] < worst_by_iteration["8"]
        and worst_by_iteration["16"] <= 0.5 * worst_by_iteration["4"]
        and all_ksp_breakdown_false
        and all(
            record.get("first_nonfinite_stage") is None for record in mandatory_records
        )
    )
    any_unexpected_continuation = bool(
        any(record.get("continued_to_32") is True for record in mandatory_records)
        and not global_trend_pass
    )
    numerical_gate_pass = bool(
        physical_zero_map.get("zero_map_pass") is True
        and preferred_checkpoint_pass
        and not any_unexpected_continuation
        and no_nonfinite
        and all_ksp_breakdown_false
        and all_final_residuals_consistent
    )
    classification = (
        "J1_INNER_FGMRES_SIDE_GATE_PASS"
        if numerical_gate_pass
        else "J1_INNER_FGMRES_NUMERICAL_LIMIT_NOT_REACHED_BY_32"
    )
    return {
        "gate_by_checkpoint": gate_by_checkpoint,
        "preferred_inner_budget": preferred_inner_budget,
        "preferred_checkpoint_pass": preferred_checkpoint_pass,
        "worst_by_iteration": worst_by_iteration,
        "finite16": finite16,
        "global_trend_pass": global_trend_pass,
        "any_unexpected_continuation": any_unexpected_continuation,
        "conditional32_not_authorized": not global_trend_pass,
        "conditional_32_authorized": bool(
            all(record.get("continued_to_32") is True for record in mandatory_records)
            and global_trend_pass
        ),
        "numerical_gate_pass": numerical_gate_pass,
        "classification": classification,
        "all_checkpoint_finite": all_checkpoint_finite,
        "all_ksp_breakdown_false": all_ksp_breakdown_false,
        "all_final_residuals_consistent": all_final_residuals_consistent,
        "all_final_finite": all_final_finite,
        "no_nonfinite": no_nonfinite,
        "worst_final": worst_final,
        "preferred_residual_max": preferred_residual_max,
    }


def run_v10_h4_j1_inner_fgmres(
    cfg: Any,
    *,
    profile: Any,
    comm: MPI.Intracomm,
    marker_callback: Callable[[str, Mapping[str, Any]], None],
    exact_spool_root: str | Path,
    source_sha: str,
    side_system_builder: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Run the V10-4 bottom J1-preconditioned FGMRES diagnostic.

    The layer action is borrowed as a right preconditioner only.  The true
    residuals are always computed with the matrix-free ``system.A``.  Each
    mandatory RHS owns one zero-initialized KSP solve; the helper may stop that
    same solve at 16 or let it continue to 32 after its local online trend
    check.  The parent launcher remains authoritative for resource intervals.
    """

    system = None
    components = None
    sweep = None
    spool: dict[str, Any] | None = None
    payload: dict[str, Any] | None = None
    ready_sweep_diagnostics: dict[str, Any] = {}
    after_sweep_diagnostics: dict[str, Any] = {}
    cleanup_detail: dict[str, Any] = {}
    component_release_before_krylov: Any = "not_run"
    method_records: dict[str, dict[str, Any]] = {}
    holdout_provenance: dict[str, Any] = {}
    marker_callback(
        "v10_j1_inner_fgmres_bottom_construction_begin",
        {
            "construction_peak_limit_gib": V10_H4_J1_INNER_FGMRES_CONSTRUCTION_LIMIT_GIB,
            "retained_peak_limit_gib": V10_H4_J1_INNER_FGMRES_RETAINED_LIMIT_GIB,
            "selected_mode_packet_opened": False,
            "sgs_executed": False,
            "qep_count": 0,
        },
    )
    try:
        if side_system_builder is None:
            system = assemble_hybrid_local_dtn_action_system(
                cfg,
                "bottom",
                bottom_interface_z_nm=profile.bottom_interface_nm,
                top_interface_z_nm=profile.top_interface_nm,
                comm=comm,
                log=None,
            )
        else:
            system = side_system_builder(
                side="bottom", cfg=cfg, profile=profile, comm=comm
            )
        components = _build_research_explicit_side_components(system)
        labels, mapping_metadata = build_real_layer_labels(components.F, system)
        layer_count = len(mapping_metadata["z_layer_boundaries"]) - 1
        if layer_count != 6:
            raise ValueError(f"V10-4 requires exactly six layers, got {layer_count}")
        sweep = build_layer_sweep_action(
            components.F,
            labels,
            layer_count=layer_count,
            method="J1",
            fine_action=None,
        )
        del labels, mapping_metadata
        marker_callback(
            "v10_j1_inner_fgmres_bottom_factors_ready",
            {
                "layer_factor_count": 6,
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
                "fixed_preconditioner": "J1_layer_action",
            },
        )
        ready_sweep_diagnostics = deepcopy(sweep.diagnostics)
        component_release_before_krylov = _destroy_v5_side_components(components)
        cleanup_detail["components_released_before_krylov"] = (
            component_release_before_krylov
        )
        components = None
        collective_heap_cleanup(comm)
        marker_callback(
            "v10_j1_inner_fgmres_bottom_construction_end",
            {
                "layer_factor_count": 6,
                "explicit_f_c_d_h_released_before_krylov": True,
                "component_release": component_release_before_krylov,
                "system_A_retained": True,
                "construction_complete": True,
            },
        )
        identity, manifest_sha256, catalog = _v9_frozen_holdout_identity(
            exact_spool_root, comm
        )
        spool = _load_v5_fixed_budget_spool_shards(
            exact_spool_root,
            comm,
            packet_identity=identity,
            manifest_sha256=manifest_sha256,
        )
        holdout_provenance = {
            "identity": identity,
            "manifest_sha256": manifest_sha256,
            "catalog_authority": catalog,
        }
        physical_zero_map = {
            "label": "physical_side_rhs",
            "mandatory": False,
            "degenerate": True,
            "status": "degenerate_zero_map_checked",
            "zero_map_limit": 1.0e-13,
            "zero_map_pass": False,
            "output_norm": None,
            "output_finite": False,
            "first_nonfinite_stage": None,
        }
        zero_source = None
        zero_output = None
        try:
            zero_source = system.A.createVecRight()
            zero_output = system.A.createVecLeft()
            zero_source.set(0.0)
            zero_output.set(0.0)
            sweep.apply(zero_source, zero_output)
            output_norm = float(zero_output.norm())
            output_finite = bool(np.isfinite(output_norm))
            physical_zero_map.update(
                {
                    "output_norm": output_norm if output_finite else None,
                    "output_finite": output_finite,
                    "zero_map_pass": bool(output_finite and output_norm <= 1.0e-13),
                    "first_nonfinite_stage": (
                        None if output_finite else "J1_zero_map_output"
                    ),
                }
            )
        finally:
            if zero_source is not None:
                zero_source.set(0.0)
                zero_source.destroy()
            if zero_output is not None:
                zero_output.set(0.0)
                zero_output.destroy()
        method_records["physical_side_rhs"] = physical_zero_map
        marker_callback(
            "v10_j1_inner_fgmres_bottom_retained_apply_state_ready",
            {
                "fixed_preconditioner": "J1_layer_action",
                "retained_state": "measured_by_subsequent_ksp_applies",
                "layer_factor_count": 6,
            },
        )
        marker_callback(
            "v10_j1_inner_fgmres_bottom_holdout_ready",
            {
                "holdout_labels": list(spool),
                "holdout_opened": True,
                "exact_spool_opened": True,
                "selected_mode_packet_opened": False,
            },
        )
        for label, artifact in spool.items():
            if label == "physical_side_rhs":
                continue
            template = None
            rhs = None
            rhs_result: dict[str, Any] | None = None
            marker_callback(
                f"v10_j1_inner_fgmres_bottom_{label}_begin",
                {"label": label, "zero_initial_guess": True},
            )
            try:
                template = system.A.createVecLeft()
                rhs = _load_v5_blr_reference_spool_remapped(artifact["rhs"], template)
                rhs_result = run_v10_right_preconditioned_fgmres_checkpoints(
                    system.A,
                    rhs,
                    sweep,
                    label=label,
                    resource_gate=lambda: True,
                    checkpoint_callback=(
                        lambda row, label=label: marker_callback(
                            f"v10_j1_inner_fgmres_bottom_{label}_checkpoint_{row['iteration']}",
                            row,
                        )
                    ),
                )
                rhs_result.update(
                    {
                        "mandatory": True,
                        "degenerate": False,
                        "r_A_definition": "||b-A_side x||/||b||",
                        "resource_gate_source": "parent_watchdog_pending",
                    }
                )
                final_iteration = max(
                    int(iteration) for iteration in rhs_result["checkpoints"]
                )
                checkpoint_final = rhs_result["checkpoints"][str(final_iteration)][
                    "explicit_true_residual"
                ]
                rhs_result["final_residual_consistent"] = bool(
                    np.isfinite(float(rhs_result["final_independent_true_residual"]))
                    and np.isfinite(float(checkpoint_final))
                    and abs(
                        float(rhs_result["final_independent_true_residual"])
                        - float(checkpoint_final)
                    )
                    <= 1.0e-12
                )
                method_records[label] = rhs_result
            finally:
                if rhs is not None:
                    rhs.set(0.0)
                    rhs.destroy()
                if template is not None:
                    template.destroy()
                marker_callback(
                    f"v10_j1_inner_fgmres_bottom_{label}_end",
                    {
                        "label": label,
                        "iterations": (
                            None if rhs_result is None else rhs_result.get("iterations")
                        ),
                        "first_nonfinite_stage": (
                            None
                            if rhs_result is None
                            else rhs_result.get("first_nonfinite_stage")
                        ),
                    },
                )
        mandatory_records = [
            record
            for record in method_records.values()
            if record.get("mandatory") is True
        ]
        if len(mandatory_records) != 5:
            raise ValueError("V10-4 requires exactly five mandatory RHS records")
        aggregate = _v10_j1_inner_fgmres_aggregate_gate(
            mandatory_records, physical_zero_map
        )
        gate_by_checkpoint = aggregate["gate_by_checkpoint"]
        preferred_inner_budget = aggregate["preferred_inner_budget"]
        worst_by_iteration = aggregate["worst_by_iteration"]
        finite16 = aggregate["finite16"]
        global_trend_pass = aggregate["global_trend_pass"]
        conditional32_not_authorized = aggregate["conditional32_not_authorized"]
        numerical_gate_pass = aggregate["numerical_gate_pass"]
        classification = aggregate["classification"]
        all_checkpoint_finite = aggregate["all_checkpoint_finite"]
        all_ksp_breakdown_false = aggregate["all_ksp_breakdown_false"]
        all_final_residuals_consistent = aggregate["all_final_residuals_consistent"]
        worst_final = aggregate["worst_final"]
        preferred_residual_max = aggregate["preferred_residual_max"]
        actual_max_iteration = max(
            int(record.get("iterations", 0)) for record in mandatory_records
        )
        payload = {
            "schema": V10_H4_J1_INNER_FGMRES_SCHEMA,
            "method": V10_H4_J1_INNER_FGMRES_METHOD,
            "profile_id": V10_H4_J1_INNER_FGMRES_PROFILE_ID,
            "status": "component_fgmres_completed",
            "source_sha": source_sha,
            "method_records": method_records,
            "mandatory_labels": [record["label"] for record in mandatory_records],
            "degenerate_labels": ["physical_side_rhs"],
            "global_trend": {
                "worst_true_residual_by_iteration": worst_by_iteration,
                "gate_by_checkpoint": gate_by_checkpoint,
                "preferred_inner_budget": preferred_inner_budget,
                "all_rhs_finite_through_16": finite16,
                "physical_zero_map_pass": physical_zero_map["zero_map_pass"],
                "global_worst_trend_pass": global_trend_pass,
                "actual_max_iteration": actual_max_iteration,
                "conditional32_not_authorized": conditional32_not_authorized,
                "conditional_32_authorized": aggregate["conditional_32_authorized"],
                "policy": (
                    "per_rhs_online_authorization_due_to_sequential_PETSc_KSP; "
                    "not equivalent to preknown_global_worst synchronized scheduling"
                ),
            },
            "gate": {
                "numerical_gate_pass": numerical_gate_pass,
                "physical_zero_map_pass": physical_zero_map["zero_map_pass"],
                "classification": classification,
                "all_checkpoint_finite": all_checkpoint_finite,
                "all_ksp_breakdown_false": all_ksp_breakdown_false,
                "all_final_residuals_consistent": all_final_residuals_consistent,
                "all_final_finite": aggregate["all_final_finite"],
                "no_nonfinite": aggregate["no_nonfinite"],
                "uniform_checkpoint_pass": aggregate["preferred_checkpoint_pass"],
                "worst_final_true_residual": worst_final,
                "true_residual_limit": 1.0e-2,
                "preferred_residual_max": preferred_residual_max,
                "preferred_residual_limit": 1.0e-3,
                "gate_by_checkpoint": gate_by_checkpoint,
                "preferred_inner_budget": preferred_inner_budget,
                "resource_gate": "pending_parent_process_tree_samples",
            },
            "factor_inventory": {
                "layer_factor_count_ready": ready_sweep_diagnostics.get(
                    "layer_factor_count", "not_available"
                ),
                "layer_factor_count_after_cleanup": "pending_cleanup",
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
                "side_fgmres_ksp_count": 5,
                "pc_nested_ksp_count": 0,
            },
            "selected_mode_packet_opened": False,
            "exact_spool_opened": True,
            "qep_count": 0,
            "sgs_executed": False,
            "top": "not_run",
            "both_side": "not_run",
            "full_formal": "not_run",
            "lane_c_activation": not numerical_gate_pass,
            "next_lane": "v10-5_pending" if numerical_gate_pass else "lane_c_review",
            "explicit_components_released_before_krylov": True,
            "component_release_before_krylov": component_release_before_krylov,
            "holdout_provenance": holdout_provenance,
            "lifecycle": {
                "retained_state": "pending_cleanup",
                "layer_factor_count_ready": ready_sweep_diagnostics.get(
                    "layer_factor_count", "not_available"
                ),
                "layer_factor_count_after_cleanup": "pending_cleanup",
                "components_released": "pending_cleanup",
                "system_released": "pending_cleanup",
            },
            "telemetry": {
                "process_tree_samples": {
                    "path": "numerical_output/process_tree_samples.jsonl",
                    "writer": "parent_task038_launcher",
                },
                "memory_stages": {
                    "path": "numerical_output/memory_stages.jsonl",
                    "writer": "parent_task038_launcher_marker_alignment",
                },
                "memory_stage_markers": {
                    "path": "numerical_output/memory_stage_markers.raw.jsonl",
                    "writer": "v3_7_worker",
                },
                "memory_object_ledger": {
                    "path": "numerical_output/memory_object_ledger.json",
                    "status": "finalized_in_worker_finalizer",
                },
                "gate_contract": {
                    "construction_peak_limit_gib": V10_H4_J1_INNER_FGMRES_CONSTRUCTION_LIMIT_GIB,
                    "retained_peak_limit_gib": V10_H4_J1_INNER_FGMRES_RETAINED_LIMIT_GIB,
                    "swap_required": 0,
                    "full_side_exact_factor_count": 0,
                    "global_direct_factor_count": 0,
                    "nested_ksp_count": 0,
                    "sgs_executed": False,
                },
            },
        }
        return payload
    finally:
        if spool is not None:
            spool.clear()
        if sweep is not None:
            sweep.destroy()
            after_sweep_diagnostics = deepcopy(sweep.diagnostics)
        if components is not None:
            cleanup_detail["components_released"] = _destroy_v5_side_components(
                components
            )
        if system is not None and hasattr(system, "destroy"):
            system.destroy()
            cleanup_detail["system_destroy_called"] = True
        else:
            cleanup_detail["system_destroy_called"] = False
        cleanup_detail["sweep_destroyed"] = bool(
            after_sweep_diagnostics.get("destroyed") is True
            or after_sweep_diagnostics.get("layer_factor_count", 0) == 0
        )
        collective_heap_cleanup(comm)
        cleanup_detail["collective_cleanup"] = "completed"
        marker_callback(
            "v10_j1_inner_fgmres_bottom_retained_state_release",
            {
                "retained_apply_state_released": True,
                "layer_factor_count_ready": ready_sweep_diagnostics.get(
                    "layer_factor_count", "not_available"
                ),
                "layer_factor_count_after_cleanup": after_sweep_diagnostics.get(
                    "layer_factor_count", 0
                ),
                **cleanup_detail,
            },
        )
        if payload is not None:
            payload["factor_inventory"]["layer_factor_count_after_cleanup"] = (
                after_sweep_diagnostics.get("layer_factor_count", 0)
            )
            payload["lifecycle"].update(
                {
                    "retained_state": "released_after_five_rhs",
                    "layer_factor_count_after_cleanup": after_sweep_diagnostics.get(
                        "layer_factor_count", 0
                    ),
                    "components_released": cleanup_detail.get(
                        "components_released_before_krylov", "not_available"
                    ),
                    "system_released": cleanup_detail.get(
                        "system_destroy_called", False
                    ),
                    "collective_cleanup": "completed",
                }
            )


def _v10_side_response_apply_column(
    action: Any,
    system: Any,
    rhs: PETSc.Vec,
    *,
    label: str,
    metadata: Mapping[str, Any],
    marker_callback: Callable[[str, Mapping[str, Any]], None],
) -> tuple[dict[str, Any], np.ndarray]:
    started = time.perf_counter()
    target = system.A.createVecLeft()
    target.set(0.0)
    try:
        action.apply(rhs, target)
        rhs_norm = float(rhs.norm())
        output_norm = float(target.norm())
        degenerate_uninformative = bool(np.isfinite(rhs_norm) and rhs_norm <= 1.0e-13)
        residual = _v5_blr_true_residual(system, rhs, target)
        local_values = np.asarray(
            target.getArray(readonly=True), dtype=np.complex128
        ).copy()
        comm = target.getComm().tompi4py()
        finite = bool(
            comm.allreduce(
                bool(np.isfinite(local_values).all() and np.isfinite(residual)),
                op=MPI.LAND,
            )
        )
        report = {
            **dict(metadata),
            "label": str(label),
            "finite": finite,
            "true_residual_relative": (
                float(residual) if np.isfinite(residual) else None
            ),
            "rhs_norm": rhs_norm,
            "output_norm": output_norm,
            "degenerate_uninformative": degenerate_uninformative,
            "zero_map_pass": bool(
                degenerate_uninformative
                and np.isfinite(output_norm)
                and output_norm <= 1.0e-13
            ),
            "wall_seconds": float(time.perf_counter() - started),
            "action_apply_count": int(action.diagnostics.get("apply_count", 0)),
            "exact_residual_limit": V10_SIDE_RESPONSE_PACKET_EXACT_RESIDUAL_LIMIT,
        }
        marker_callback(
            f"v10_side_response_packet_{label}_end",
            {
                "label": str(label),
                "finite": finite,
                "true_residual_relative": report["true_residual_relative"],
                "wall_seconds": report["wall_seconds"],
            },
        )
        return report, local_values
    finally:
        target.set(0.0)
        target.destroy()


def run_v10_h4_side_response_packet_pilot(
    cfg: Any,
    *,
    profile: Any,
    comm: MPI.Intracomm,
    marker_callback: Callable[[str, Mapping[str, Any]], None],
    exact_spool_root: str | Path,
    source_sha: str,
    output_root: str | Path,
    selected_mode_packet_manifest: str | Path,
    selected_mode_packet_identity: Mapping[str, Any],
    selected_mode_packet_manifest_sha256: str,
    input_sha256: str,
    physical_model_sha256: str,
    side_system_builder: Callable[..., Any] | None = None,
    response_action_builder: Callable[..., Any] | None = None,
    full_response: bool = False,
) -> dict[str, Any]:
    """Produce the fixed exact-side response pilot or full packet.

    Pilot mode writes sixteen fixed columns; full mode streams 960 modal
    columns plus the physical-zero validation column.  Both are producer-only
    phases with one selected-mode mmap context and one exact side action; the
    consumer is the separate ``run_v10_h4_side_response_packet_consumer``
    entry point.
    """

    system = None
    components = None
    action = None
    packet_context = None
    modal_provider = None
    spaces = None
    response_values: np.ndarray | None = None
    response_writer: OwnerRowResponsePacketWriter | None = None
    reports: list[dict[str, Any]] = []
    packet_result: dict[str, Any] | None = None
    result_payload: dict[str, Any] | None = None
    factor_ready = 0
    factor_after_cleanup: Any = "not_available"
    components_release_before_columns: dict[str, bool] = {}
    explicit_components_released_before_columns = False
    producer_started = time.perf_counter()
    setup_wall_seconds = 0.0
    route_profile_id = (
        V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_PROFILE_ID
        if full_response
        else V10_H4_SIDE_RESPONSE_PACKET_PILOT_PROFILE_ID
    )
    route_schema = (
        V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_SCHEMA
        if full_response
        else V10_H4_SIDE_RESPONSE_PACKET_PILOT_SCHEMA
    )
    route_method = (
        V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_METHOD
        if full_response
        else V10_H4_SIDE_RESPONSE_PACKET_PILOT_METHOD
    )
    producer_marker_prefix = (
        "v10_side_response_packet_full_producer"
        if full_response
        else "v10_side_response_packet_bottom_producer"
    )
    marker_callback(
        f"{producer_marker_prefix}_begin",
        {
            "schema": route_schema,
            "method": route_method,
            "profile_id": route_profile_id,
            "full_response": bool(full_response),
            "producer_limit_gib": V10_SIDE_RESPONSE_PACKET_PRODUCER_LIMIT_GIB,
            "consumer_limit_gib": V10_SIDE_RESPONSE_PACKET_CONSUMER_LIMIT_GIB,
            "payload_limit_gib": V10_SIDE_RESPONSE_PACKET_PAYLOAD_LIMIT_GIB,
            "selected_mode_packet_opened": True,
            "qep_count": 0,
        },
    )
    try:
        schedule = (
            v10_side_response_packet_full_schedule()
            if full_response
            else v10_side_response_packet_pilot_schedule()
        )
        if side_system_builder is None:
            system = assemble_hybrid_local_dtn_action_system(
                cfg,
                "bottom",
                bottom_interface_z_nm=profile.bottom_interface_nm,
                top_interface_z_nm=profile.top_interface_nm,
                comm=comm,
                log=None,
            )
        else:
            system = side_system_builder(
                side="bottom", cfg=cfg, profile=profile, comm=comm
            )
        components = _build_research_explicit_side_components(system)
        if response_action_builder is None:
            action = create_research_exact_side_lu_action(
                components.F,
                components,
                qualification_scope=route_profile_id,
                explicit_opt_in=True,
                factor_only_storage=True,
            )
        else:
            action = response_action_builder(
                system=system, components=components, comm=comm
            )
        factor_ready = 1
        marker_callback(
            f"{producer_marker_prefix}_factor_ready",
            {
                "exact_side_factor_count_ready": factor_ready,
                "exact_side_factor_count_after_cleanup": "pending_producer_exit",
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
            },
        )
        components_release_before_columns = _destroy_v5_side_components(
            components, retain_d=True
        )
        explicit_components_released_before_columns = all(
            components_release_before_columns.get(name, False)
            for name in ("F", "C", "H")
        )
        if not explicit_components_released_before_columns:
            raise RuntimeError(
                "V10-6 producer could not release explicit F/C/H before columns"
            )
        action_borrowed_matrices_marked = False
        if explicit_components_released_before_columns:
            action.woodbury.mark_borrowed_matrices_released()
            action_borrowed_matrices_marked = True
        marker_callback(
            f"{producer_marker_prefix}_explicit_components_released",
            {
                "released": components_release_before_columns,
                "action_borrowed_matrices_marked": action_borrowed_matrices_marked,
                "D_retained": bool(
                    components_release_before_columns.get("D_retained", False)
                ),
                "explicit_components_released_before_columns": (
                    explicit_components_released_before_columns
                ),
            },
        )
        packet_context = Task039V4SelectedModeMmapContext(
            Path(selected_mode_packet_manifest),
            identity=selected_mode_packet_identity,
            expected_manifest_sha256=selected_mode_packet_manifest_sha256,
            comm=comm,
        )
        cross_section = build_matching_cross_section(system.cfg, "stage4_xy")
        spaces = build_cross_section_spaces(
            cross_section, transverse_degree=int(system.cfg.nedelec_degree)
        )
        modal_provider = StreamedPhysicalModalSourceProvider(system, spaces)
        spool_identity, spool_manifest_sha, catalog = _v9_frozen_holdout_identity(
            exact_spool_root, comm
        )
        spool_records = _load_v5_fixed_budget_spool_shards(
            exact_spool_root,
            comm,
            packet_identity=spool_identity,
            manifest_sha256=spool_manifest_sha,
        )
        if full_response:
            response_writer = OwnerRowResponsePacketWriter(
                output_root,
                global_rows=int(system.A.getSize()[0]),
                ownership_range=tuple(
                    int(value) for value in system.A.getOwnershipRange()
                ),
                column_records=list(schedule),
                source_sha=source_sha,
                input_sha256=input_sha256,
                physical_model_sha256=physical_model_sha256,
                comm=comm,
                schema=V10_SIDE_RESPONSE_PACKET_FULL_SCHEMA,
                method=V10_SIDE_RESPONSE_PACKET_FULL_METHOD,
                zero_column_index=960,
                holdout_column_indices=V10_SIDE_RESPONSE_PACKET_FULL_HOLDOUT_COLUMNS,
                identity={
                    "selected_mode_packet_manifest_sha256": selected_mode_packet_manifest_sha256,
                    "exact_spool_manifest_sha256": spool_manifest_sha,
                    "factor_identity": {
                        "side": "bottom",
                        "action": "research_exact_side_lu",
                        "factor_only_storage": True,
                        "qualification_scope": route_profile_id,
                        "profile_id": route_profile_id,
                    },
                },
            )
        else:
            response_values = np.empty(
                (int(system.A.getLocalSize()[0]), V10_SIDE_RESPONSE_PACKET_COLUMNS),
                dtype=np.complex128,
                order="F",
            )
        setup_wall_seconds = float(time.perf_counter() - producer_started)
        column_records: list[dict[str, Any]] = []
        for column_index, item in enumerate(schedule):
            label = str(item["label"])
            marker_callback(
                f"v10_side_response_packet_{label}_begin",
                {"label": label, "column_index": column_index},
            )
            rhs = None
            template = None
            try:
                if item["kind"] in {
                    "selected_modal",
                    "physical_zero_replacement",
                    "training_modal",
                }:
                    selected_column = int(item["column"])
                    branch = "positive" if selected_column < 480 else "negative"
                    mode_index = (
                        selected_column
                        if branch == "positive"
                        else selected_column - 480
                    )
                    pair = packet_context.mode_pair(branch, mode_index)
                    rhs, source_metadata = modal_provider(
                        system,
                        pair,
                        branch=branch,
                        role="right",
                        family=(
                            "positive_modal_traction"
                            if branch == "positive"
                            else "negative_modal_traction"
                        ),
                    )
                elif item["kind"] in {"holdout", "deterministic_random"}:
                    spool_label = str(item["spool_label"])
                    artifact = spool_records[spool_label]
                    template = system.A.createVecLeft()
                    rhs = _load_v5_blr_reference_spool_remapped(
                        artifact["rhs"], template
                    )
                    source_metadata = {
                        "source": "frozen_exact_spool_rhs",
                        "spool_label": spool_label,
                        "spool_catalog_sha256": catalog["catalog_sha256"],
                    }
                else:
                    artifact = spool_records["physical_side_rhs"]
                    template = system.A.createVecLeft()
                    rhs = _load_v5_blr_reference_spool_remapped(
                        artifact["rhs"], template
                    )
                    source_metadata = {
                        "source": "frozen_physical_side_rhs",
                        "spool_label": "physical_side_rhs",
                        "spool_catalog_sha256": catalog["catalog_sha256"],
                        "degenerate_uninformative": True,
                    }
                report, local_values = _v10_side_response_apply_column(
                    action,
                    system,
                    rhs,
                    label=label,
                    metadata={
                        **dict(source_metadata),
                        "column_index": column_index,
                        "schedule_kind": item["kind"],
                    },
                    marker_callback=marker_callback,
                )
                reports.append(report)
                if response_writer is not None:
                    response_writer.write_column(column_index, local_values)
                else:
                    response_values[:, column_index] = local_values
                column_records.append(
                    {
                        **dict(item),
                        "column_index": column_index,
                        "finite": report["finite"],
                        "true_residual_relative": report["true_residual_relative"],
                        "rhs_norm": report["rhs_norm"],
                        "output_norm": report["output_norm"],
                        "degenerate_uninformative": report["degenerate_uninformative"],
                        "wall_seconds": report["wall_seconds"],
                    }
                )
            finally:
                if rhs is not None:
                    rhs.set(0.0)
                    rhs.destroy()
                if template is not None:
                    template.destroy()
        pilot_solve_wall_seconds = sum(
            float(report["wall_seconds"]) for report in reports
        )
        solve_only_projected_wall = (
            pilot_solve_wall_seconds
            if full_response
            else projected_response_wall_seconds(pilot_solve_wall_seconds)
        )
        projected_wall = (
            setup_wall_seconds + pilot_solve_wall_seconds
            if full_response
            else setup_wall_seconds
            + (pilot_solve_wall_seconds / len(reports))
            * V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS
        )
        projected_payload = projected_response_payload_bytes(
            int(system.A.getSize()[0]), V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS
        )
        if not full_response:
            report_gate = validate_exact_side_response_reports(reports)
        else:
            response_reports = [
                report for report in reports if report["label"] != "physical_side_rhs"
            ]
            zero_reports = [
                report for report in reports if report["label"] == "physical_side_rhs"
            ]
            zero_report = zero_reports[0] if len(zero_reports) == 1 else None
            finite_pass = len(response_reports) == 960 and all(
                bool(report.get("finite")) for report in response_reports
            )
            residual_pass = all(
                report.get("true_residual_relative") is not None
                and float(report["true_residual_relative"])
                <= V10_SIDE_RESPONSE_PACKET_EXACT_RESIDUAL_LIMIT
                for report in response_reports
            )
            wall_finite = all(
                np.isfinite(float(report.get("wall_seconds", np.nan)))
                for report in reports
            )
            zero_map_pass = bool(
                zero_report is not None
                and zero_report.get("degenerate_uninformative") is True
                and zero_report.get("rhs_norm") is not None
                and np.isfinite(float(zero_report["rhs_norm"]))
                and float(zero_report["rhs_norm"]) <= 1.0e-13
                and zero_report.get("zero_map_pass") is True
            )
            report_gate = {
                "complete": len(reports) == V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS,
                "nonzero_modal_column_count": len(response_reports),
                "training_column_count": 960
                - len(V10_SIDE_RESPONSE_PACKET_FULL_HOLDOUT_COLUMNS),
                "holdout_column_count": len(
                    V10_SIDE_RESPONSE_PACKET_FULL_HOLDOUT_COLUMNS
                ),
                "finite": bool(finite_pass),
                "residual_pass": bool(residual_pass),
                "wall_finite": bool(wall_finite),
                "zero_map_pass": zero_map_pass,
                "zero_rhs_norm": (
                    None if zero_report is None else zero_report.get("rhs_norm")
                ),
                "zero_output_norm": (
                    None if zero_report is None else zero_report.get("output_norm")
                ),
                "pass": bool(
                    len(response_reports) == 960
                    and finite_pass
                    and residual_pass
                    and wall_finite
                    and zero_map_pass
                ),
                "residual_limit": V10_SIDE_RESPONSE_PACKET_EXACT_RESIDUAL_LIMIT,
            }
        report_gate.update(
            {
                "pilot_solve_wall_seconds": pilot_solve_wall_seconds,
                "setup_wall_seconds": setup_wall_seconds,
                "solve_only_projected_full_packet_wall_seconds": solve_only_projected_wall,
                "projected_full_packet_wall_seconds": projected_wall,
                "projected_full_packet_wall_limit_seconds": V10_SIDE_RESPONSE_PACKET_PROJECTED_WALL_LIMIT_SECONDS,
                "projected_payload_bytes": projected_payload,
                "projected_payload_limit_bytes": int(
                    V10_SIDE_RESPONSE_PACKET_PAYLOAD_LIMIT_GIB * 2**30
                ),
                "projected_payload_pass": bool(
                    projected_payload
                    <= V10_SIDE_RESPONSE_PACKET_PAYLOAD_LIMIT_GIB * 2**30
                ),
                "projected_wall_pass": bool(
                    projected_wall
                    <= V10_SIDE_RESPONSE_PACKET_PROJECTED_WALL_LIMIT_SECONDS
                ),
            }
        )
        if full_response:
            measured_full_packet_total_wall = (
                setup_wall_seconds + pilot_solve_wall_seconds
            )
            report_gate.update(
                {
                    "measured_full_packet_setup_wall_seconds": setup_wall_seconds,
                    "measured_full_packet_solve_wall_seconds": pilot_solve_wall_seconds,
                    "measured_full_packet_total_wall_seconds": measured_full_packet_total_wall,
                    "measured_full_packet_wall_limit_seconds": V10_SIDE_RESPONSE_PACKET_PROJECTED_WALL_LIMIT_SECONDS,
                    "measured_full_packet_wall_pass": bool(
                        measured_full_packet_total_wall
                        <= V10_SIDE_RESPONSE_PACKET_PROJECTED_WALL_LIMIT_SECONDS
                    ),
                }
            )
        eligibility_key = (
            "full_packet_eligibility_pass"
            if full_response
            else "pilot_eligibility_pass"
        )
        report_gate[eligibility_key] = bool(
            report_gate["pass"]
            and report_gate["projected_payload_pass"]
            and (
                report_gate["measured_full_packet_wall_pass"]
                if full_response
                else report_gate["projected_wall_pass"]
            )
        )
        if response_writer is not None:
            response_writer.column_records = [dict(item) for item in column_records]
            packet_result = response_writer.finalize()
        else:
            packet_result = write_exact_side_response_packet(
                output_root,
                response_values,
                global_rows=int(system.A.getSize()[0]),
                ownership_range=tuple(
                    int(value) for value in system.A.getOwnershipRange()
                ),
                column_records=column_records,
                source_sha=source_sha,
                input_sha256=input_sha256,
                physical_model_sha256=physical_model_sha256,
                comm=comm,
            )
        marker_callback(
            f"{producer_marker_prefix}_packet_written",
            {
                **packet_result,
                "report_gate": report_gate,
                "projected_full_packet_wall_seconds": projected_wall,
                "solve_only_projected_full_packet_wall_seconds": solve_only_projected_wall,
                "measured_full_packet_setup_wall_seconds": (
                    setup_wall_seconds if full_response else None
                ),
                "measured_full_packet_solve_wall_seconds": (
                    pilot_solve_wall_seconds if full_response else None
                ),
                "measured_full_packet_total_wall_seconds": (
                    setup_wall_seconds + pilot_solve_wall_seconds
                    if full_response
                    else None
                ),
                "projected_payload_bytes": projected_payload,
            },
        )
        result_payload = {
            "schema": route_schema,
            "method": route_method,
            "profile_id": route_profile_id,
            "status": "producer_completed"
            if report_gate[eligibility_key]
            else "producer_gate_failed",
            "source_sha": source_sha,
            "input_sha256": input_sha256,
            "physical_model_sha256": physical_model_sha256,
            "column_records": reports,
            "column_count": len(reports),
            "report_gate": report_gate,
            "pilot_eligibility_pass": (
                report_gate.get("pilot_eligibility_pass") if not full_response else None
            ),
            "full_packet_eligibility_pass": (
                report_gate.get("full_packet_eligibility_pass")
                if full_response
                else None
            ),
            "packet": packet_result,
            "holdout_provenance": {
                "producer_source_sha": catalog["producer_source_sha"],
                "catalog": catalog,
                "manifest_sha256": spool_manifest_sha,
            },
            "factor_inventory": {
                "factor_count_ready": factor_ready,
                "exact_side_factor_count_ready": factor_ready,
                "exact_side_factor_count_after_cleanup": factor_after_cleanup,
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
            },
            "component_release_before_columns": dict(components_release_before_columns),
            "explicit_components_released_before_columns": (
                explicit_components_released_before_columns
            ),
            "selected_mode_packet_opened": True,
            "exact_spool_opened": True,
            "physical_zero_validation": (
                next(
                    report
                    for report in reports
                    if report["label"] == "physical_side_rhs"
                )
                if full_response
                else None
            ),
            "qep_count": 0,
            "top": "not_run",
            "full_formal": "not_run",
            "research_only": True,
            "projected_payload_bytes": projected_payload,
            "projected_payload_limit_gib": V10_SIDE_RESPONSE_PACKET_PAYLOAD_LIMIT_GIB,
            "projected_full_packet_wall_limit_seconds": V10_SIDE_RESPONSE_PACKET_PROJECTED_WALL_LIMIT_SECONDS,
            "measured_full_packet_setup_wall_seconds": (
                setup_wall_seconds if full_response else None
            ),
            "measured_full_packet_solve_wall_seconds": (
                pilot_solve_wall_seconds if full_response else None
            ),
            "measured_full_packet_total_wall_seconds": (
                setup_wall_seconds + pilot_solve_wall_seconds if full_response else None
            ),
        }
    finally:
        if response_values is not None:
            response_values.fill(0.0)
        if response_writer is not None:
            response_writer.close()
        if modal_provider is not None:
            modal_provider.destroy()
        if packet_context is not None:
            packet_context.release()
        if action is not None:
            action.destroy()
            diagnostics = action.diagnostics
            factor_after_cleanup = diagnostics.get(
                "exact_factor_count", diagnostics.get("direct_factor_count", 0)
            )
        if components is not None:
            _destroy_v5_side_components(components)
        if system is not None and hasattr(system, "destroy"):
            system.destroy()
        collective_heap_cleanup(comm)
        marker_callback(
            f"{producer_marker_prefix}_cleanup",
            {
                "factor_count_ready": factor_ready,
                "factor_count_after_cleanup": factor_after_cleanup,
                "selected_mode_packet_released": packet_context is None
                or packet_context.diagnostics.get("released") is True,
                "qep_count": 0,
            },
        )
        if result_payload is not None:
            result_payload["factor_inventory"][
                "exact_side_factor_count_after_cleanup"
            ] = factor_after_cleanup
            result_payload["factor_inventory"]["factor_count_after_cleanup"] = (
                factor_after_cleanup
            )
            result_payload["lifecycle"] = {
                "producer_factor_count_ready": factor_ready,
                "producer_factor_count_after_cleanup": factor_after_cleanup,
                "component_release_before_columns": dict(
                    components_release_before_columns
                ),
                "explicit_components_released_before_columns": (
                    explicit_components_released_before_columns
                ),
                "producer_cleanup_completed": True,
            }
    if result_payload is None:
        raise RuntimeError("V10-6 producer returned without a result")
    return result_payload


def run_v10_h4_side_response_packet_compression(
    *,
    manifest_path: str | Path,
    manifest_sha256: str,
    source_sha: str,
    expected_producer_source_sha: str,
    input_sha256: str,
    physical_model_sha256: str,
    comm: MPI.Intracomm,
    marker_callback: Callable[[str, Mapping[str, Any]], None],
) -> dict[str, Any]:
    """Run the separate mmap-only TSQR/SVD compression consumer."""

    if not expected_producer_source_sha:
        raise ValueError("V10 compression requires an expected producer source SHA")

    compression_started = time.perf_counter()
    marker_callback(
        "v10_side_response_packet_compression_begin",
        {
            "schema": V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_SCHEMA,
            "method": V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_METHOD,
            "consumer_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
            "selected_mode_packet_opened": False,
            "exact_spool_opened": False,
            "system_assembled": False,
            "qep_count": 0,
            "sgs_executed": False,
        },
    )
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    shards = list(manifest.get("shards", ()))
    shard = next(item for item in shards if int(item.get("rank", -1)) == int(comm.rank))
    ownership = tuple(int(value) for value in shard["ownership_range"])
    packet = load_full_side_response_packet(
        manifest_path,
        expected_manifest_sha256=manifest_sha256,
        expected_provenance={
            "source_sha": expected_producer_source_sha,
            "input_sha256": input_sha256,
            "physical_model_sha256": physical_model_sha256,
            **{
                key: value
                for key, value in manifest.get("provenance", {}).items()
                if key not in {"source_sha", "input_sha256", "physical_model_sha256"}
            },
        },
        global_rows=int(manifest["global_rows"]),
        ownership_range=ownership,
        comm=comm,
    )
    marker_callback(
        "v10_side_response_packet_compression_loaded",
        {
            **packet.diagnostics,
            "wall_seconds": time.perf_counter() - compression_started,
        },
    )
    try:
        compression = compress_owner_row_response_packet(
            packet,
            comm=comm,
            training_column_indices=tuple(
                int(value) for value in manifest["training_column_indices"]
            ),
            holdout_column_indices=tuple(
                int(value) for value in manifest["holdout_column_indices"]
            ),
            zero_column_index=int(manifest["zero_column_index"]),
        )
        result = {
            "schema": V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_SCHEMA,
            "method": V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_METHOD,
            "status": "compression_completed",
            "source_sha": source_sha,
            "checker_source_sha": source_sha,
            "producer_source_sha": expected_producer_source_sha,
            "manifest_sha256": manifest_sha256,
            "compression": compression,
            "wall_seconds": time.perf_counter() - compression_started,
            "packet": dict(packet.diagnostics),
            "factor_inventory": {
                "consumer_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
            },
            "selected_mode_packet_opened": False,
            "exact_spool_opened": False,
            "system_assembled": False,
            "qep_count": 0,
            "sgs_executed": False,
            "research_only": True,
        }
    finally:
        packet.destroy()
        released = dict(packet.diagnostics)
        marker_callback(
            "v10_side_response_packet_compression_released",
            {**released, "wall_seconds": time.perf_counter() - compression_started},
        )
    result["packet"] = dict(packet.diagnostics)
    result["lifecycle"] = {
        "packet_released": bool(result["packet"].get("released")),
        "consumer_factor_count_after_cleanup": 0,
        "system_assembled": False,
        "compression_completed": True,
    }
    return result


V10_H4_SIDE_RESPONSE_PACKET_FULL_RECHECK_SCHEMA = (
    "task039.v10.h4.exact_side_response_packet.full.recheck.v1"
)


def _v10_sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def recheck_v10_h4_full_side_response_packet(
    raw_root: str | Path,
    packet_root: str | Path,
    *,
    expected_producer_source_sha: str,
    checker_source_sha: str,
    expected_peak_process_tree_rss_bytes: int = 54497624064,
) -> dict[str, Any]:
    """Recompute the full-packet producer gates without trusting its status."""

    raw_root = Path(raw_root)
    packet_root = Path(packet_root)
    diagnostic_path = raw_root / "numerical_output" / "v3_v7_diagnostic.json"
    summary_path = raw_root / "run_summary.json"
    manifest_path = packet_root / "manifest.json"
    diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    provenance = manifest.get("provenance", {})
    checks: dict[str, bool] = {}

    checks["schema_method"] = bool(
        diagnostic.get("schema") == V10_SIDE_RESPONSE_PACKET_FULL_SCHEMA
        and diagnostic.get("method") == V10_SIDE_RESPONSE_PACKET_FULL_METHOD
        and manifest.get("schema") == V10_SIDE_RESPONSE_PACKET_FULL_SCHEMA
        and manifest.get("method") == V10_SIDE_RESPONSE_PACKET_FULL_METHOD
    )
    checks["producer_source_sha"] = bool(
        diagnostic.get("source_sha") == expected_producer_source_sha
        and provenance.get("source_sha") == expected_producer_source_sha
    )
    input_sha256 = diagnostic.get("input_sha256")
    physical_model_sha256 = diagnostic.get("physical_model_sha256")
    checks["input_physical_identity"] = bool(
        isinstance(input_sha256, str)
        and len(input_sha256) == 64
        and isinstance(physical_model_sha256, str)
        and len(physical_model_sha256) == 64
        and provenance.get("input_sha256") == input_sha256
        and provenance.get("physical_model_sha256") == physical_model_sha256
    )
    root_tokens = {}
    for name in ("source_sha", "input_sha256", "physical_model_sha256"):
        token_path = raw_root / f"{name}.txt"
        root_tokens[name] = (
            token_path.read_text(encoding="utf-8").strip()
            if token_path.is_file()
            else None
        )
    checks["root_identity_files"] = bool(
        root_tokens["source_sha"] == expected_producer_source_sha
        and root_tokens["input_sha256"] == input_sha256
        and root_tokens["physical_model_sha256"] == physical_model_sha256
    )
    holdout = diagnostic.get("holdout_provenance", {})
    checks["frozen_spool_identity"] = bool(
        holdout.get("producer_source_sha") == V9_FROZEN_HOLDOUT_PRODUCER_SHA
        and holdout.get("catalog", {}).get("catalog_sha256")
        == V9_FROZEN_HOLDOUT_CATALOG_SHA256
        and provenance.get("exact_spool_manifest_sha256")
        == V10_SIDE_RESPONSE_PACKET_FROZEN_HOLDOUT_MANIFEST_SHA256
        and provenance.get("selected_mode_packet_manifest_sha256")
        == V10_SIDE_RESPONSE_PACKET_FROZEN_HOLDOUT_MANIFEST_SHA256
        and holdout.get("manifest_sha256")
        == V10_SIDE_RESPONSE_PACKET_FROZEN_HOLDOUT_MANIFEST_SHA256
    )
    checks["factor_identity"] = bool(
        provenance.get("factor_identity")
        == {
            "side": "bottom",
            "action": "research_exact_side_lu",
            "factor_only_storage": True,
            "qualification_scope": "task039.v10.h4.side_response_packet.full_producer.v1",
            "profile_id": "task039.v10.h4.side_response_packet.full_producer.v1",
        }
    )

    column_records = list(diagnostic.get("column_records", ()))
    nonzero_records = [
        record for record in column_records if int(record.get("column_index", -1)) < 960
    ]
    zero_records = [
        record
        for record in column_records
        if record.get("label") == "physical_side_rhs"
    ]
    residuals = [
        float(record["true_residual_relative"])
        for record in nonzero_records
        if record.get("true_residual_relative") is not None
    ]
    checks["960_modal_residuals"] = bool(
        len(column_records) == V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS
        and len(nonzero_records) == 960
        and len(residuals) == 960
        and all(
            bool(record.get("finite"))
            and np.isfinite(float(record["true_residual_relative"]))
            and float(record["true_residual_relative"])
            <= V10_SIDE_RESPONSE_PACKET_EXACT_RESIDUAL_LIMIT
            for record in nonzero_records
        )
    )
    checks["physical_zero"] = bool(
        len(zero_records) == 1
        and bool(zero_records[0].get("finite"))
        and float(zero_records[0].get("rhs_norm", float("inf"))) <= 1.0e-13
        and float(zero_records[0].get("output_norm", float("inf"))) <= 1.0e-13
        and bool(zero_records[0].get("zero_map_pass"))
    )

    training = tuple(
        int(value) for value in manifest.get("training_column_indices", ())
    )
    holdout_columns = tuple(
        int(value) for value in manifest.get("holdout_column_indices", ())
    )
    expected_holdout = V10_SIDE_RESPONSE_PACKET_FULL_HOLDOUT_COLUMNS
    checks["column_partition"] = bool(
        manifest.get("column_count") == V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS
        and training
        == tuple(value for value in range(960) if value not in expected_holdout)
        and holdout_columns == expected_holdout
        and sorted(training + holdout_columns) == list(range(960))
        and len(set(training).intersection(holdout_columns)) == 0
        and int(manifest.get("zero_column_index", -1)) == 960
        and manifest.get("training_column_count") == 950
        and manifest.get("holdout_column_count") == 10
    )

    shards = sorted(manifest.get("shards", ()), key=lambda item: int(item["rank"]))
    cursor = 0
    shard_hashes_verified = True
    shard_shapes_verified = True
    for rank, shard in enumerate(shards):
        start, end = (int(value) for value in shard["ownership_range"])
        shard_path = packet_root / str(shard["path"])
        cursor_ok = (
            int(shard.get("rank", -1)) == rank and start == cursor and end > start
        )
        cursor = end
        if not shard_path.is_file():
            shard_hashes_verified = False
            shard_shapes_verified = False
            continue
        shard_hashes_verified &= _v10_sha256_file(shard_path) == shard.get(
            "file_sha256"
        )
        values = np.load(shard_path, mmap_mode="r", allow_pickle=False)
        shard_shapes_verified &= bool(
            cursor_ok
            and tuple(values.shape)
            == (end - start, V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS)
            and str(values.dtype) == "complex128"
            and tuple(shard.get("shape", ())) == tuple(values.shape)
        )
    checks["shards_hash_shape_dtype"] = bool(
        len(shards) == 8
        and cursor == int(manifest.get("global_rows", -1))
        and cursor == 132300
        and shard_hashes_verified
        and shard_shapes_verified
    )
    checks["manifest_hash"] = _v10_sha256_file(manifest_path) == diagnostic.get(
        "packet", {}
    ).get("manifest_sha256")

    factor_inventory = diagnostic.get("factor_inventory", {})
    lifecycle = diagnostic.get("lifecycle", {})
    checks["factor_lifecycle"] = bool(
        factor_inventory.get("exact_side_factor_count_ready") == 1
        and factor_inventory.get("exact_side_factor_count_after_cleanup") == 0
        and factor_inventory.get("global_direct_factor_count") == 0
        and factor_inventory.get("nested_ksp_count") == 0
        and lifecycle.get("producer_cleanup_completed") is True
    )
    marker_path = raw_root / "numerical_output" / "memory_stage_markers.raw.jsonl"
    cleanup_markers = []
    if marker_path.is_file():
        for line in marker_path.read_text(encoding="utf-8").splitlines():
            marker = json.loads(line)
            if marker.get("stage") == "v10_side_response_packet_full_producer_cleanup":
                cleanup_markers.append(marker)
    cleanup_detail = (
        cleanup_markers[0].get("detail", {}) if len(cleanup_markers) == 1 else {}
    )
    checks["packet_release"] = bool(
        int(summary.get("exit_status", -1)) == 0
        and lifecycle.get("producer_cleanup_completed") is True
        and manifest_path.is_file()
        and len(cleanup_markers) == 1
        and cleanup_detail.get("selected_mode_packet_released") is True
        and cleanup_detail.get("factor_count_after_cleanup") == 0
        and cleanup_detail.get("qep_count") == 0
    )

    report_gate = diagnostic.get("report_gate", {})
    setup_wall = float(
        report_gate.get("measured_full_packet_setup_wall_seconds", float("nan"))
    )
    solve_wall = float(
        report_gate.get("measured_full_packet_solve_wall_seconds", float("nan"))
    )
    total_wall = float(
        report_gate.get("measured_full_packet_total_wall_seconds", float("nan"))
    )
    projected_payload = (
        int(manifest.get("global_rows", 0))
        * int(manifest.get("column_count", 0))
        * np.dtype(np.complex128).itemsize
    )
    checks["wall_payload"] = bool(
        np.isfinite(setup_wall)
        and np.isfinite(solve_wall)
        and np.isfinite(total_wall)
        and total_wall <= V10_SIDE_RESPONSE_PACKET_PROJECTED_WALL_LIMIT_SECONDS
        and projected_payload <= int(V10_SIDE_RESPONSE_PACKET_PAYLOAD_LIMIT_GIB * 2**30)
        and int(diagnostic.get("projected_payload_bytes", -1)) == projected_payload
    )
    resource = summary.get("resource_authority", {}).get(
        "v10_h4_side_response_packet_full_producer_telemetry", {}
    )
    interval = resource.get("construction_interval_summary", {})
    peak_bytes = int(interval.get("peak_process_tree_rss_bytes", -1))
    swap_bytes = int(resource.get("overall_peak_swap_bytes", -1))
    checks["resource"] = bool(
        peak_bytes == int(expected_peak_process_tree_rss_bytes)
        and peak_bytes <= 60 * 2**30
        and swap_bytes == 0
        and resource.get("zero_swap_observed") is True
    )

    passed = all(checks.values())
    return {
        "schema": V10_H4_SIDE_RESPONSE_PACKET_FULL_RECHECK_SCHEMA,
        "method": V10_SIDE_RESPONSE_PACKET_FULL_METHOD,
        "producer_source_sha": expected_producer_source_sha,
        "checker_source_sha": checker_source_sha,
        "raw_root": str(raw_root),
        "packet_root": str(packet_root),
        "raw_diagnostic_sha256": _v10_sha256_file(diagnostic_path),
        "packet_manifest_sha256": _v10_sha256_file(manifest_path),
        "parent_run_summary_status": summary.get("status"),
        "parent_worker_record_status": resource.get("worker_record_status"),
        "parent_worker_record_contract_reason": resource.get(
            "worker_record_contract_reason"
        ),
        "cleanup_marker_sha256": (
            _v10_sha256_file(marker_path) if marker_path.is_file() else None
        ),
        "checks": checks,
        "gate": {
            "finite": checks["960_modal_residuals"] and checks["physical_zero"],
            "max_true_residual_relative": max(residuals) if residuals else None,
            "residual_limit": V10_SIDE_RESPONSE_PACKET_EXACT_RESIDUAL_LIMIT,
            "setup_wall_seconds": setup_wall,
            "solve_wall_seconds": solve_wall,
            "total_wall_seconds": total_wall,
            "projected_payload_bytes": projected_payload,
            "peak_process_tree_rss_bytes": peak_bytes,
            "swap_bytes": swap_bytes,
            "pass": passed,
        },
        "classification": (
            "FULL_SIDE_RESPONSE_PACKET_RECHECK_PASS"
            if passed
            else "FULL_SIDE_RESPONSE_PACKET_RECHECK_FAILED"
        ),
    }


def run_v10_h4_side_response_packet_consumer(
    *,
    manifest_path: str | Path,
    manifest_sha256: str,
    source_sha: str,
    input_sha256: str,
    physical_model_sha256: str,
    global_rows: int,
    ownership_range: tuple[int, int],
    comm: MPI.Intracomm,
    marker_callback: Callable[[str, Mapping[str, Any]], None],
) -> dict[str, Any]:
    """Load the pilot packet in a separate consumer phase with no factor."""

    marker_callback(
        "v10_side_response_packet_consumer_begin",
        {
            "schema": V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_SCHEMA,
            "method": V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_METHOD,
            "consumer_factor_count": 0,
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
            "selected_mode_packet_opened": False,
            "qep_count": 0,
            "sgs_executed": False,
        },
    )
    packet = load_exact_side_response_packet(
        manifest_path,
        expected_manifest_sha256=manifest_sha256,
        expected_provenance={
            "source_sha": source_sha,
            "input_sha256": input_sha256,
            "physical_model_sha256": physical_model_sha256,
        },
        global_rows=global_rows,
        ownership_range=ownership_range,
        comm=comm,
    )
    marker_callback(
        "v10_side_response_packet_consumer_loaded",
        packet.diagnostics,
    )
    packet.destroy()
    diagnostics = dict(packet.diagnostics)
    marker_callback(
        "v10_side_response_packet_consumer_released",
        diagnostics,
    )
    return {
        "schema": V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_SCHEMA,
        "method": V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_METHOD,
        "status": "consumer_completed",
        "packet": diagnostics,
        "factor_inventory": {
            "consumer_factor_count": 0,
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
        },
        "selected_mode_packet_opened": False,
        "qep_count": 0,
        "sgs_executed": False,
    }


def _v11_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _v11_load_modal_amplitudes(
    path: Path, *, expected_file_sha256: str, expected_array_sha256: str
) -> np.ndarray:
    if _v11_sha256(path) != expected_file_sha256:
        raise ValueError("V11 modal amplitude artifact hash mismatch")
    with np.load(path, allow_pickle=False) as modal_npz:
        amplitudes = np.array(
            modal_npz["modal_amplitudes"], dtype=np.complex128, copy=True
        )
    if amplitudes.shape != (960,):
        raise ValueError("V11 modal amplitude authority must contain 960 values")
    if (
        hashlib.sha256(np.ascontiguousarray(amplitudes).tobytes(order="C")).hexdigest()
        != expected_array_sha256
    ):
        raise ValueError("V11 modal amplitude array hash mismatch")
    return amplitudes


def _v11_identity_records(
    raw_records: Sequence[Mapping[str, Any]], context: Any, cfg: Any
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    actual = sorted(
        (dict(record) for record in raw_records), key=lambda x: int(x["column_index"])
    )
    if len(actual) != 961 or [int(item["column_index"]) for item in actual] != list(
        range(961)
    ):
        raise ValueError("V11 raw column_records must cover columns 0..960")
    schedule = {
        int(item["column"]): item for item in v10_side_response_packet_full_schedule()
    }
    expected: list[dict[str, Any]] = []
    enriched: list[dict[str, Any]] = []
    for column, record in enumerate(actual):
        if column == 960:
            expected.append(
                {
                    "column_index": 960,
                    "label": "physical_side_rhs",
                    "source": "frozen_physical_side_rhs",
                    "family": None,
                    "branch": None,
                    "mode_index": None,
                    "raw_beta": None,
                    "discrete_beta": None,
                    "mode_key": None,
                    "schedule_kind": "physical_side_rhs",
                }
            )
            enriched.append(record)
            continue
        branch = "positive" if column < 480 else "negative"
        mode_index = column if branch == "positive" else column - 480
        pair = context.mode_pair(branch, mode_index)
        beta = complex(pair["beta"])
        discrete = scalar_cg_discrete_traction_beta(
            beta,
            degree=int(cfg.nedelec_degree),
            h_nm=float(cfg.mesh_target_size),
            direction="forward" if branch == "positive" else "backward",
        )
        expected_record = {
            "column_index": column,
            "label": str(schedule[column]["label"]),
            "source": "streamed_modal_traction_column",
            "family": f"{branch}_modal_traction",
            "branch": branch,
            "mode_index": mode_index,
            "raw_beta": [beta.real, beta.imag],
            "discrete_beta": [discrete.real, discrete.imag],
            "mode_key": pair["mode_key"],
            "schedule_kind": str(schedule[column]["kind"]),
        }
        if "mode_key" in record and record["mode_key"] != pair["mode_key"]:
            raise ValueError(f"V11 selected mode key mismatch at column {column}")
        record["mode_key"] = pair["mode_key"]
        expected.append(expected_record)
        enriched.append(record)
    return enriched, expected


def _v11_packet_value_map(packets: Sequence[tuple[Any, complex]]) -> dict[Any, complex]:
    result: dict[Any, complex] = {}
    for key, value in packets:
        if key in result:
            raise ValueError("V11 canonical packet contains a duplicate key")
        result[key] = complex(value)
    return result


def _v11_trace_values_in_order(
    packets: Sequence[tuple[Any, complex]],
    trace_keys: Sequence[Any],
    comm: MPI.Intracomm,
) -> np.ndarray:
    local_ok = True
    values_by_key: dict[Any, complex] = {}
    try:
        values_by_key = _v11_packet_value_map(packets)
        local_ok = bool(set(values_by_key) == set(trace_keys))
    except (TypeError, ValueError):
        local_ok = False
    if not bool(comm.allreduce(local_ok, op=MPI.LAND)):
        raise ValueError("V11 extracted trace key set does not match frozen V7 trace")
    return np.asarray([values_by_key[key] for key in trace_keys], dtype=np.complex128)


def _v11_read_active_trace_owner_remap(
    path: Path,
    expected_sha256: str,
    expected_local_keys: Sequence[Any],
    comm: MPI.Intracomm,
) -> tuple[dict[str, Any], dict[Any, complex]]:
    """Read V7 trace shards one at a time and retain only fresh-owner keys."""

    manifest: dict[str, Any] = {}
    values: dict[Any, complex] = {}
    local_keys = set(expected_local_keys)

    def collective_stage(ok: bool, error: str | None, stage: str) -> None:
        if bool(comm.allreduce(bool(ok), op=MPI.LAND)):
            return
        errors = comm.allgather(error)
        first_error = next((item for item in errors if item), "unknown error")
        raise ValueError(f"V11 active-trace {stage} failed: {first_error}")

    manifest_error: str | None = None
    try:
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != expected_sha256:
            raise ValueError("V11 active-trace manifest hash mismatch")
        manifest = json.loads(payload.decode("utf-8"))
        shards = list(manifest.get("per_rank_shards", ()))
        if (
            manifest.get("schema_version") != "task037.canonical-vector-manifest.v1"
            or int(manifest.get("mpi_size", -1)) != comm.size
            or len(shards) != comm.size
        ):
            raise ValueError("V11 active-trace manifest ownership is invalid")
        descriptors = sorted(shards, key=lambda item: int(item["rank"]))
        if [int(item["rank"]) for item in descriptors] != list(range(comm.size)):
            raise ValueError("V11 active-trace manifest ranks are not unique")
        if len(local_keys) != len(expected_local_keys):
            raise ValueError("V11 fresh active-trace keys contain a duplicate")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        manifest_error = str(error)
    collective_stage(manifest_error is None, manifest_error, "manifest")

    for descriptor in descriptors:
        shard_map: dict[Any, complex] = {}
        shard_error: str | None = None
        try:
            shard_packets = read_canonical_packet_shard(
                path.parent / str(descriptor["filename"]),
                str(descriptor["file_sha256"]),
            )
            shard_map = _v11_packet_value_map(shard_packets)
            del shard_packets
        except (
            OSError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            shard_error = str(error)
        collective_stage(
            shard_error is None,
            shard_error,
            f"shard rank {int(descriptor['rank'])} read",
        )
        shard_keys = tuple(shard_map)
        local_match = np.asarray(
            [int(key in local_keys) for key in shard_keys], dtype=np.int32
        )
        global_match = np.empty_like(local_match)
        if len(local_match):
            comm.Allreduce(local_match, global_match, op=MPI.SUM)
        bad = np.flatnonzero(global_match != 1)
        match_error = None
        if len(bad):
            index = int(bad[0])
            kind = "extra" if int(global_match[index]) == 0 else "owner overlap"
            match_error = (
                f"{kind} key {shard_keys[index]!r} "
                f"(owner count {int(global_match[index])})"
            )
        collective_stage(match_error is None, match_error, "shard ownership")
        retention_error: str | None = None
        for key, value in shard_map.items():
            if key in local_keys:
                if key in values:
                    retention_error = f"duplicate owner key {key!r}"
                    break
                values[key] = value
        collective_stage(retention_error is None, retention_error, "shard retention")
        del shard_map, shard_keys, local_match, global_match
    missing = sorted(local_keys.difference(values), key=repr)
    missing_error = None if not missing else f"missing key {missing[0]!r}"
    collective_stage(missing_error is None, missing_error, "owner coverage")
    return manifest, values


def _v11_release_partial_authority(owned: dict[str, Any]) -> dict[str, Any]:
    released: dict[str, bool] = {}
    not_created: list[str] = []
    for name, method in (
        ("provider", "destroy"),
        ("context", "release"),
        ("projection", "destroy"),
        ("owner", "destroy"),
        ("bundle", "destroy"),
    ):
        if name not in owned:
            not_created.append(name)
            continue
        value = owned.get(name)
        if value is not None:
            getattr(value, method)()
            owned[name] = None
            released[name] = True
        else:
            released[name] = False
    spool = owned.get("spool")
    if spool is not None:
        spool.clear()
        owned["spool"] = None
        released["spool"] = True
    else:
        released["spool"] = False
    return {
        "released_objects": released,
        "not_created": not_created,
        "all_owned_released": all(value is None for value in owned.values()),
    }


def _v11_prepare_bottom_authority(
    system: Any,
    packet: ExactSideResponsePacket,
    *,
    cfg: Any,
    comm: MPI.Intracomm,
    response_manifest: Path,
    producer_diagnostic: Path,
    selected_manifest: Path,
    selected_manifest_sha256: str,
    exact_spool_root: Path,
    marker_callback: Callable[..., None] | None = None,
    v7_root: Path = Path(V11_V7_FULL_FORMAL_ROOT),
) -> dict[str, Any]:
    owned: dict[str, Any] = {}
    try:
        return _v11_prepare_bottom_authority_inner(
            system,
            packet,
            cfg=cfg,
            comm=comm,
            response_manifest=response_manifest,
            producer_diagnostic=producer_diagnostic,
            selected_manifest=selected_manifest,
            selected_manifest_sha256=selected_manifest_sha256,
            exact_spool_root=exact_spool_root,
            marker_callback=marker_callback,
            v7_root=v7_root,
            owned=owned,
        )
    except Exception:
        _v11_release_partial_authority(owned)
        raise


def _v11_prepare_bottom_authority_inner(
    system: Any,
    packet: ExactSideResponsePacket,
    *,
    cfg: Any,
    comm: MPI.Intracomm,
    response_manifest: Path,
    producer_diagnostic: Path,
    selected_manifest: Path,
    selected_manifest_sha256: str,
    exact_spool_root: Path,
    marker_callback: Callable[..., None] | None,
    v7_root: Path = Path(V11_V7_FULL_FORMAL_ROOT),
    owned: dict[str, Any],
) -> dict[str, Any]:
    """Bind the Task39 V7/V10 artifacts to one fresh action-only system."""

    def mark(stage: str, **detail: Any) -> None:
        if marker_callback is not None:
            marker_callback(stage, **detail)

    if _v11_sha256(response_manifest) != V11_RESPONSE_PACKET_MANIFEST_SHA256:
        raise ValueError("V11 response manifest hash is not frozen")
    if _v11_sha256(producer_diagnostic) != V11_RESPONSE_PACKET_DIAGNOSTIC_SHA256:
        raise ValueError("V11 producer diagnostic hash is not frozen")
    selected_payload = json.loads(selected_manifest.read_text(encoding="utf-8"))
    if _v11_sha256(selected_manifest) != selected_manifest_sha256:
        raise ValueError("V11 selected packet manifest hash mismatch")
    if selected_manifest_sha256 != V11_RESPONSE_PACKET_SELECTED_MANIFEST_SHA256:
        raise ValueError("V11 selected packet manifest is not frozen")
    if (
        str(selected_payload.get("identity_sha256"))
        != V11_SELECTED_PACKET_IDENTITY_SHA256
    ):
        raise ValueError("V11 selected packet identity hash mismatch")
    identity_path = selected_manifest.with_name("identity.json")
    if (
        _v11_sha256(identity_path)
        != "b3bb870fe6fa17cb262b6161f7317cc1950944755c9270d4628dd5c79e950690"
    ):
        raise ValueError("V11 selected packet identity artifact hash mismatch")
    selected_identity = json.loads(identity_path.read_text(encoding="utf-8"))
    context = Task039V4SelectedModeMmapContext(
        selected_manifest,
        identity=selected_identity,
        expected_manifest_sha256=selected_manifest_sha256,
        comm=comm,
    )
    owned["context"] = context
    raw = json.loads(producer_diagnostic.read_text(encoding="utf-8"))
    actual_records, expected_records = _v11_identity_records(
        raw.get("column_records", ()), context, cfg
    )
    response_provenance = {
        "exact_spool_manifest_sha256": V11_RESPONSE_PACKET_SELECTED_MANIFEST_SHA256,
        "factor_identity": {
            "action": "research_exact_side_lu",
            "factor_only_storage": True,
            "profile_id": "task039.v10.h4.side_response_packet.full_producer.v1",
            "qualification_scope": "task039.v10.h4.side_response_packet.full_producer.v1",
            "side": "bottom",
        },
        "input_sha256": V11_RESPONSE_PACKET_INPUT_SHA256,
        "physical_model_sha256": V11_RESPONSE_PACKET_PHYSICAL_MODEL_SHA256,
        "selected_mode_packet_manifest_sha256": V11_RESPONSE_PACKET_SELECTED_MANIFEST_SHA256,
        "source_sha": V11_RESPONSE_PACKET_PRODUCER_SOURCE_SHA,
    }
    trace_manifest = v7_root / V11_V7_ACTIVE_TRACE_MANIFEST_RELATIVE
    modal_path = v7_root / V11_V7_MODAL_Q_RELATIVE
    amplitudes = _v11_load_modal_amplitudes(
        modal_path,
        expected_file_sha256=V11_V7_MODAL_Q_SHA256,
        expected_array_sha256=V11_V7_MODAL_AMPLITUDES_SHA256,
    )
    cross_section = build_matching_cross_section(system.cfg, "stage4_xy")
    spaces = build_cross_section_spaces(
        cross_section, transverse_degree=int(system.cfg.nedelec_degree)
    )
    mark(
        "v11_h4_bottom_packet_algebra_projection_begin",
        mode_count=V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS // 2,
        full_mode_vectors_retained=False,
        traction_matrices_created=False,
    )
    projection = build_streamed_projection_only(
        system,
        spaces,
        context.mode_pair,
        mode_count=V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS // 2,
        canonical_trace_family_sha256=selected_payload.get("selection_sha256"),
    )
    owned["projection"] = projection
    d_matrix = projection.projection
    mark(
        "v11_h4_bottom_packet_algebra_projection_ready",
        **dict(projection.audit),
    )
    provider = StreamedPhysicalModalSourceProvider(system, spaces)
    owned["provider"] = provider
    sources: dict[int, np.ndarray] = {}
    for column in V11_BOTTOM_RESPONSE_SAMPLE_INDICES:
        branch = "positive" if column < 480 else "negative"
        pair = context.mode_pair(
            branch, column if branch == "positive" else column - 480
        )
        vec, _metadata = provider(
            system,
            pair,
            branch=branch,
            role="right",
            family=f"{branch}_modal_traction",
        )
        sources[column] = np.array(
            vec.getArray(readonly=True), dtype=np.complex128, copy=True
        )
        vec.destroy()
    mark(
        "v11_h4_bottom_packet_algebra_source_ready",
        sampled_source_count=len(sources),
        selected_context_released=False,
    )
    selected_temporaries_released: dict[str, bool] = {}
    for name, method in (("provider", "destroy"), ("context", "release")):
        value = owned.get(name)
        if value is not None:
            getattr(value, method)()
            owned[name] = None
            selected_temporaries_released[name] = True
        else:
            selected_temporaries_released[name] = False
    mark(
        "v11_h4_bottom_packet_algebra_selected_temporaries_released",
        **selected_temporaries_released,
    )
    spool_identity, spool_manifest_sha, _catalog = _v9_frozen_holdout_identity(
        exact_spool_root, comm
    )
    if spool_manifest_sha != V11_RESPONSE_PACKET_SELECTED_MANIFEST_SHA256:
        raise ValueError("V11 exact-spool manifest identity is not frozen")
    physical_vec = system.b.copy()
    physical_rhs = np.array(
        physical_vec.getArray(readonly=True), dtype=np.complex128, copy=True
    )
    physical_vec.destroy()
    condensed = system.static_condensation.condensed
    zero_active = condensed.create_active_vector()
    zero_active.set(0.0)
    zero_active.assemble()
    try:
        zero_packets, _zero_audit = extract_canonical_active_trace_packets(
            condensed, system.V, system.floquet_data, zero_active
        )
        expected_local_keys = tuple(_v11_packet_value_map(zero_packets))
    finally:
        zero_active.destroy()
    _trace_meta, trace_values = _v11_read_active_trace_owner_remap(
        trace_manifest,
        V11_V7_ACTIVE_TRACE_MANIFEST_SHA256,
        expected_local_keys,
        comm,
    )
    active_v7 = reconstruct_canonical_active_trace_vec(
        condensed,
        system.V,
        system.floquet_data,
        trace_values,
    )
    try:
        trace_keys = tuple(sorted(trace_values, key=repr))
        roundtrip_packets, _roundtrip_audit = extract_canonical_active_trace_packets(
            condensed, system.V, system.floquet_data, active_v7
        )
        roundtrip_values = _v11_trace_values_in_order(
            roundtrip_packets, trace_keys, comm
        )
        frozen_values = np.asarray(
            [trace_values[key] for key in trace_keys], dtype=np.complex128
        )
        local_delta = roundtrip_values - frozen_values
        roundtrip_max = float(
            comm.allreduce(
                float(np.max(np.abs(local_delta))) if len(local_delta) else 0.0,
                op=MPI.MAX,
            )
        )
        local_num = float(np.vdot(local_delta, local_delta).real)
        local_den = float(np.vdot(frozen_values, frozen_values).real)
        roundtrip_relative = float(
            np.sqrt(max(float(comm.allreduce(local_num, op=MPI.SUM)), 0.0))
            / max(
                np.sqrt(max(float(comm.allreduce(local_den, op=MPI.SUM)), 0.0)),
                1.0e-30,
            )
        )
        if roundtrip_max > 5.0e-12 or roundtrip_relative > 5.0e-12:
            raise ValueError("V11 active-trace canonical round-trip failed")
        mark(
            "v11_h4_bottom_packet_algebra_v7_active_trace_ready",
            local_key_count=len(trace_keys),
            roundtrip_max_error=roundtrip_max,
            roundtrip_relative_error=roundtrip_relative,
        )
        d_target = d_matrix.createVecLeft()
        try:
            d_matrix.mult(active_v7, d_target)
            v7_schur = -np.array(
                d_target.getArray(readonly=True),
                dtype=np.complex128,
                copy=True,
            )
        finally:
            d_target.destroy()
    finally:
        active_v7.destroy()
    v7_trace = np.asarray(
        [trace_values[key] for key in trace_keys], dtype=np.complex128
    )

    def _local_vec(values: np.ndarray) -> PETSc.Vec:
        vec = system.A.createVecRight()
        vec.set(0.0)
        vec.getArray()[:] = np.asarray(values, dtype=PETSc.ScalarType)
        vec.assemble()
        return vec

    def block_action(values: np.ndarray) -> np.ndarray:
        source = _local_vec(values)
        target = system.A.createVecLeft()
        target.set(0.0)
        try:
            system.A.mult(source, target)
            return np.array(
                target.getArray(readonly=True), dtype=np.complex128, copy=True
            )
        finally:
            target.destroy()
            source.destroy()

    def schur_action(values: np.ndarray) -> np.ndarray:
        source = _local_vec(values)
        target = d_matrix.createVecLeft()
        target.set(0.0)
        try:
            d_matrix.mult(source, target)
            return np.array(
                target.getArray(readonly=True), dtype=np.complex128, copy=True
            )
        finally:
            target.destroy()
            source.destroy()

    def trace_action(values: np.ndarray) -> np.ndarray:
        active = _local_vec(values)
        try:
            packets, _audit = extract_canonical_active_trace_packets(
                system.static_condensation.condensed,
                system.V,
                system.floquet_data,
                active,
            )
            return _v11_trace_values_in_order(packets, trace_keys, comm)
        finally:
            active.destroy()

    def release() -> dict[str, Any]:
        released = _v11_release_partial_authority(owned)
        released["selected_temporaries_released"] = dict(selected_temporaries_released)
        return released

    system_evidence = {
        "observed": True,
        "source": "system.A/static_condensation/streamed projection-only D",
        "mat": {
            "type": str(system.A.getType()),
            "size": [int(value) for value in system.A.getSize()],
            "ownership_ranges": comm.allgather(
                list(map(int, system.A.getOwnershipRange()))
            ),
            "matrix_free": bool(getattr(system, "inventory", {}).get("matrix_free")),
        },
    }
    direct_factor_count = int(
        getattr(system, "inventory", {}).get("direct_factor_count", -1)
    )
    direct_factor_ok = bool(comm.allreduce(direct_factor_count == 0, op=MPI.LAND))
    if not direct_factor_ok:
        raise ValueError("V11 action-only system has an unexpected direct factor")
    inventory_evidence = {
        "observed": True,
        "source": "fresh action-only object lifecycle; no factor/KSP/QEP objects created",
        "ready": {"factor_count": direct_factor_count, "ksp_count": 0, "qep_count": 0},
        "ksp_qep_not_created": True,
    }
    return {
        "actual_source_records": actual_records,
        "expected_identity_records": expected_records,
        "expected_provenance": {
            "manifest": response_provenance,
            "provider": {
                "implementation": "src.coupling.hybrid_streamed_sources:StreamedPhysicalModalSourceProvider._entries_to_vec",
                "scale": -1.0,
                "selected_mode_packet_manifest_sha256": V11_RESPONSE_PACKET_SELECTED_MANIFEST_SHA256,
                "producer_source_sha": V11_RESPONSE_PACKET_PRODUCER_SOURCE_SHA,
            },
            "selected_packet_authority": {
                "manifest_sha256": selected_manifest_sha256,
                "identity_sha256": selected_payload["identity_sha256"],
            },
        },
        "source_columns": sources,
        "exact_spool_provenance": {
            "root": str(exact_spool_root),
            "manifest_sha256": spool_manifest_sha,
            "identity": spool_identity,
            "arrays_loaded": False,
        },
        "v7_schur_authority": {
            "value": v7_schur,
            "source_path": str(trace_manifest),
            "source_sha256": V11_V7_ACTIVE_TRACE_MANIFEST_SHA256,
            "derivation": "-D_b*u_v7",
            "D_identity": (
                f"streamed_projection_only:{d_matrix.getType()}:{d_matrix.getSize()}"
            ),
            "active_trace_roundtrip": {
                "pass": True,
                "max_error": roundtrip_max,
                "relative_error": roundtrip_relative,
            },
            "modal_amplitudes_path": str(modal_path),
            "modal_amplitudes_sha256": V11_V7_MODAL_AMPLITUDES_SHA256,
        },
        "v7_modal_amplitudes": amplitudes,
        "v7_bottom_trace": v7_trace,
        "physical_rhs": physical_rhs,
        "block_action": block_action,
        "schur_action": schur_action,
        "trace_action": trace_action,
        "inventory_evidence": inventory_evidence,
        "system_evidence": system_evidence,
        "lifecycle": {
            "selected_temporaries_released": dict(selected_temporaries_released),
            "full_fe_loaded": False,
            "spool_arrays_loaded": False,
        },
        "release": release,
    }


def run_v11_h4_bottom_packet_algebra(
    cfg: Any,
    *,
    profile: Any,
    comm: MPI.Intracomm,
    marker_callback: Callable[..., None],
    packet_manifest: str | Path,
    packet_manifest_sha256: str,
    selected_mode_packet_manifest: str | Path,
    selected_mode_packet_manifest_sha256: str,
    producer_diagnostic_path: str | Path,
    exact_spool_root: str | Path,
    side_system_builder: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Run the explicit Task39 V11 bottom packet algebra audit."""
    system = None
    prepared = None
    packet = None
    result: dict[str, Any] | None = None
    cleanup_detail: dict[str, Any] = {}
    packet_destroyed_by_checker = False
    lifecycle: list[str] = []
    prepared_lifecycle: dict[str, Any] | None = None

    def emit(stage: str, **detail: Any) -> None:
        lifecycle.append(stage)
        marker_callback(stage, detail)

    emit(
        "v11_h4_bottom_packet_algebra_construction_begin",
        profile_id=V11_BOTTOM_PACKET_ALGEBRA_PROFILE_ID,
        schema=V11_BOTTOM_PACKET_ALGEBRA_SCHEMA,
        method=V11_BOTTOM_PACKET_ALGEBRA_METHOD,
    )
    try:
        system = (
            side_system_builder(side="bottom", cfg=cfg, profile=profile, comm=comm)
            if side_system_builder is not None
            else assemble_hybrid_local_dtn_action_system(
                cfg,
                "bottom",
                bottom_interface_z_nm=profile.bottom_interface_nm,
                top_interface_z_nm=profile.top_interface_nm,
                comm=comm,
                log=None,
            )
        )
        emit(
            "v11_h4_bottom_packet_algebra_system_ready",
            matrix_free=getattr(system, "inventory", {}).get("matrix_free"),
            direct_factor_count=getattr(system, "inventory", {}).get(
                "direct_factor_count", "not_available"
            ),
        )
        ownership = tuple(int(value) for value in system.A.getOwnershipRange())
        packet = load_full_side_response_packet(
            packet_manifest,
            expected_manifest_sha256=packet_manifest_sha256,
            expected_provenance={
                "exact_spool_manifest_sha256": V11_RESPONSE_PACKET_SELECTED_MANIFEST_SHA256,
                "factor_identity": {
                    "action": "research_exact_side_lu",
                    "factor_only_storage": True,
                    "profile_id": "task039.v10.h4.side_response_packet.full_producer.v1",
                    "qualification_scope": "task039.v10.h4.side_response_packet.full_producer.v1",
                    "side": "bottom",
                },
                "input_sha256": V11_RESPONSE_PACKET_INPUT_SHA256,
                "physical_model_sha256": V11_RESPONSE_PACKET_PHYSICAL_MODEL_SHA256,
                "selected_mode_packet_manifest_sha256": V11_RESPONSE_PACKET_SELECTED_MANIFEST_SHA256,
                "source_sha": V11_RESPONSE_PACKET_PRODUCER_SOURCE_SHA,
            },
            global_rows=int(system.A.getSize()[0]),
            ownership_range=ownership,
            comm=comm,
        )
        emit(
            "v11_h4_bottom_packet_algebra_packet_ready",
            global_rows=int(system.A.getSize()[0]),
            selected_mode_packet_opened=True,
        )
        prepared = _v11_prepare_bottom_authority(
            system,
            packet,
            cfg=cfg,
            comm=comm,
            response_manifest=Path(packet_manifest),
            producer_diagnostic=Path(producer_diagnostic_path),
            selected_manifest=Path(selected_mode_packet_manifest),
            selected_manifest_sha256=selected_mode_packet_manifest_sha256,
            exact_spool_root=Path(exact_spool_root),
            marker_callback=emit,
        )
        emit(
            "v11_h4_bottom_packet_algebra_authority_ready",
            factor_count_ready=prepared["inventory_evidence"]["ready"]["factor_count"],
        )
        try:
            result = audit_bottom_response_packet_algebra(
                packet,
                actual_source_records=prepared["actual_source_records"],
                expected_identity_records=prepared["expected_identity_records"],
                expected_provenance=prepared["expected_provenance"],
                source_columns=prepared["source_columns"],
                v7_schur_authority=prepared["v7_schur_authority"],
                v7_modal_amplitudes=prepared["v7_modal_amplitudes"],
                v7_bottom_trace=prepared["v7_bottom_trace"],
                physical_rhs=prepared["physical_rhs"],
                block_action=prepared["block_action"],
                schur_action=prepared["schur_action"],
                trace_action=prepared["trace_action"],
                inventory_evidence=prepared["inventory_evidence"],
                system_evidence=prepared["system_evidence"],
                comm=comm,
            )
        finally:
            packet_destroyed_by_checker = True
            packet = None
    finally:
        authority_release = None
        if prepared is not None:
            prepared_lifecycle = dict(prepared.get("lifecycle", {}))
            authority_release = prepared["release"]()
            prepared = None
        packet_destroyed_by_runner = False
        if packet is not None:
            packet.destroy()
            packet = None
            packet_destroyed_by_runner = True
        pre_destroy_inventory: dict[str, Any] = {}
        system_destroy_called = False
        if system is not None:
            inventory = getattr(system, "inventory", {})
            pre_destroy_inventory = {
                "direct_factor_count": inventory.get(
                    "direct_factor_count", "not_available"
                ),
                "observed_pre_destroy_zero": inventory.get("direct_factor_count") == 0,
            }
            system.destroy()
            system = None
            system_destroy_called = True
        collective_heap_cleanup(comm)
        cleanup_detail = {
            "authority_release": authority_release,
            "packet_destroy_called": bool(
                packet_destroyed_by_runner or packet_destroyed_by_checker
            ),
            "system_destroy_called": system_destroy_called,
            "system_released": system is None,
            "pre_destroy_inventory": pre_destroy_inventory,
            "observed_pre_destroy_zero": bool(
                pre_destroy_inventory.get("observed_pre_destroy_zero", False)
            ),
            "factor_count_after_cleanup": "not_observable_after_system_destroy",
        }
        emit("v11_h4_bottom_packet_algebra_cleanup", **cleanup_detail)
    if result is not None:
        result.update(
            {
                "profile": V11_BOTTOM_PACKET_ALGEBRA_PROFILE_ID,
                "lifecycle": lifecycle,
                "authority_lifecycle": prepared_lifecycle,
                "cleanup": cleanup_detail,
                "pde_solve": "not_run",
            }
        )
    return result


def _v7_streamed_packet_pair(
    item: Mapping[str, Any], context: Any
) -> tuple[dict[str, Any], str]:
    """Resolve one frozen modal pair without constructing a solver object."""

    right_modal = item["right_family"] in {
        "positive_modal_traction",
        "negative_modal_traction",
    }
    left_modal = item["left_family"] in {
        "positive_modal_dual",
        "negative_modal_dual",
    }
    if right_modal and left_modal:
        right_family = str(item["right_family"])
        left_family = str(item["left_family"])
        right_branch = "positive" if right_family.startswith("positive") else "negative"
        left_branch = "positive" if left_family.startswith("positive") else "negative"
        right_column = int(item["right_selector"]["column"])
        left_column = int(item["left_selector"]["column"])
        if right_branch != left_branch or right_column != left_column:
            raise ValueError(
                "V7 streamed modal source pair has inconsistent branch/column"
            )
        return context.mode_pair(right_branch, right_column), right_branch
    if right_modal:
        family = str(item["right_family"])
        branch = "positive" if family.startswith("positive") else "negative"
        return context.mode_pair(branch, int(item["right_selector"]["column"])), branch
    if left_modal:
        family = str(item["left_family"])
        branch = "positive" if family.startswith("positive") else "negative"
        return context.mode_pair(branch, int(item["left_selector"]["column"])), branch
    return {}, ""


def run_v7_h4_streamed_bottom_basis_producer(
    setup: Any,
    *,
    comm: MPI.Intracomm,
    marker_callback: Callable[[str, Mapping[str, Any]], None],
    packet_manifest: str | Path,
    packet_identity: Mapping[str, Any],
    packet_manifest_sha256: str,
    output_directory: str | Path,
) -> dict[str, Any]:
    """Produce one bottom-only streamed owner-row basis packet.

    This route deliberately owns no base action, H inverse, exact response,
    holdout spool, QEP, or outer solver.  ``system.blocks`` is the borrowed
    action-only C/D carrier; the selected-mode context retains four mmap arrays
    and copies only the current mode pair.
    """

    if not getattr(setup, "side_only", False) or not hasattr(setup, "bottom"):
        raise ValueError("V7 streamed producer requires a bottom-only setup carrier")
    system = setup.bottom
    packet_context = None
    modal_provider = None
    gradient_provider = None
    schedule = v6_port_modal_training_schedule(
        mode_count=480, external_count=296, source_count=512
    )
    schedule_sha256 = hashlib.sha256(
        json.dumps(schedule, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    provenance = {
        "source_schedule_identity": V7_STREAMED_PETROV_SOURCE_SCHEDULE_IDENTITY,
        "schedule_sha256": schedule_sha256,
        "training_holdout_disjoint": True,
        "training_reads_holdout_files": False,
        "exact_spool_opened": False,
        "holdout_opened": False,
        "consumer_qep_calls": 0,
        "batch_size": V7_STREAMED_PETROV_BATCH_SIZE,
        "left_dual_authority": "packet_left_surface_dual",
        "left_dual_oracle": deepcopy(V7_STREAMED_LEFT_DUAL_ORACLE),
        "left_dual_oracle_fixture_scope": "tiny_fixture_oracle_only",
    }
    marker_callback(
        "v7_streamed_bottom_producer_begin",
        {
            "profile": V7_STREAMED_PETROV_PROFILE_ID,
            "source_schedule_identity": V7_STREAMED_PETROV_SOURCE_SCHEDULE_IDENTITY,
            "schedule_checkpoints": list(V7_STREAMED_PETROV_CHECKPOINTS),
            "schedule_count": len(schedule),
            "batch_size": V7_STREAMED_PETROV_BATCH_SIZE,
            "holdout_opened": False,
            "exact_spool_opened": False,
            "consumer_qep_calls": 0,
            "global_basis_materialized": False,
            "source_columns_retained": False,
            "exact_factor_count": 0,
            "global_direct_factor_count": 0,
        },
    )

    def _owned_values(vector: PETSc.Vec) -> np.ndarray:
        expected_range = tuple(int(value) for value in system.A.getOwnershipRange())
        if tuple(int(value) for value in vector.getOwnershipRange()) != expected_range:
            raise ValueError("V7 streamed source ownership differs from bottom A")
        return np.array(vector.getArray(readonly=True), dtype=np.complex128, copy=True)

    def _source_builder(
        item: Mapping[str, Any], context: Any
    ) -> tuple[np.ndarray, np.ndarray, Mapping[str, Any]]:
        pair, branch = _v7_streamed_packet_pair(item, context)
        right_vec = None
        left_vec = None
        right_metadata: Mapping[str, Any] = {}
        left_metadata: Mapping[str, Any] = {}
        try:
            right_family = str(item["right_family"])
            if right_family in {
                "positive_modal_traction",
                "negative_modal_traction",
            }:
                right_vec, right_metadata = modal_provider(
                    system,
                    pair,
                    branch=branch,
                    role="right",
                    family=right_family,
                )
            else:
                right_vec, right_metadata = build_v6_factor_free_source_vector(
                    system,
                    system.blocks,
                    dict(item),
                    role="right",
                    modal_provider=None,
                    near_null_provider=gradient_provider,
                )

            left_family = str(item["left_family"])
            if left_family in {"positive_modal_dual", "negative_modal_dual"}:
                left_vec, left_metadata = modal_provider(
                    system,
                    pair,
                    branch=branch,
                    role="left",
                    family="packet_left_surface_dual",
                )
            else:
                left_vec, left_metadata = build_v6_factor_free_source_vector(
                    system,
                    system.blocks,
                    dict(item),
                    role="left",
                    modal_provider=None,
                    near_null_provider=gradient_provider,
                )
            source_identity = {
                "schedule_identity": V7_STREAMED_PETROV_SOURCE_SCHEDULE_IDENTITY,
                "index": int(item["index"]),
                "right_family": right_family,
                "left_family": left_family,
                "right_metadata": _json_safe(dict(right_metadata)),
                "left_metadata": _json_safe(dict(left_metadata)),
                "packet_branch": branch or None,
                "packet_mode_index": (int(pair["index"]) if pair else None),
            }
            return _owned_values(right_vec), _owned_values(left_vec), source_identity
        finally:
            if left_vec is not None:
                left_vec.destroy()
            if right_vec is not None:
                right_vec.destroy()

    try:
        packet_context = Task039V4SelectedModeMmapContext(
            Path(packet_manifest),
            identity=packet_identity,
            expected_manifest_sha256=packet_manifest_sha256,
            comm=comm,
        )
        marker_callback(
            "v7_streamed_bottom_packet_context_ready",
            {"packet_context": packet_context.diagnostics},
        )
        cross_section = build_matching_cross_section(system.cfg, "stage4_xy")
        spaces = build_cross_section_spaces(
            cross_section, transverse_degree=int(system.cfg.nedelec_degree)
        )
        modal_provider = StreamedPhysicalModalSourceProvider(system, spaces)
        gradient_provider = build_v6_discrete_gradient_source_provider(
            system=system,
            spaces=spaces,
            surface_source_assembler=modal_provider.assemble_surface_source,
        )
        marker_callback(
            "v7_streamed_bottom_source_providers_ready",
            {
                "modal_provider": modal_provider.diagnostics,
                "gradient_provider": {
                    "setup_count": gradient_provider.setup_count,
                    "apply_count": gradient_provider.apply_count,
                    "family": "cross_section_discrete_gradient_potential",
                },
                "system_operator_identity": "system.A",
                "external_carrier": "system.blocks.C_D",
                "explicit_components_created": False,
                "base_action_created": False,
                "exact_factor_count": 0,
                "global_direct_factor_count": 0,
            },
        )
        result = run_streamed_owner_row_basis_producer(
            packet_context,
            schedule,
            _source_builder,
            output_directory=output_directory,
            global_rows=int(system.A.getSize()[0]),
            ownership_range=tuple(int(value) for value in system.A.getOwnershipRange()),
            schedule_sha256=schedule_sha256,
            provenance=provenance,
            comm=comm,
        )
        marker_callback(
            "v7_streamed_bottom_basis_packet_written",
            {
                "manifest": result.get("manifest"),
                "manifest_sha256": result.get("manifest_sha256"),
                "prefix_checkpoints": result.get("prefix_checkpoints"),
                "producer_diagnostics": result.get("producer_diagnostics"),
                "source_columns_retained": False,
                "global_basis_materialized": False,
            },
        )
        result.update(
            {
                "schema": V7_STREAMED_PETROV_SCHEMA,
                "status": "producer_completed",
                "component_candidate": True,
                "research_only": True,
                "general_production": False,
                "profile": V7_STREAMED_PETROV_PROFILE_ID,
                "source_schedule_identity": V7_STREAMED_PETROV_SOURCE_SCHEDULE_IDENTITY,
                "schedule": {
                    "count": len(schedule),
                    "checkpoints": list(V7_STREAMED_PETROV_CHECKPOINTS),
                    "sha256": schedule_sha256,
                    "batch_size": V7_STREAMED_PETROV_BATCH_SIZE,
                },
                "provenance": provenance,
                "packet_context": packet_context.diagnostics,
                "holdout": {
                    "opened": False,
                    "exact_spool_opened": False,
                    "consumer_qep_calls": 0,
                },
                "resource": {
                    "minimum_limit_gib": V7_STREAMED_PETROV_MINIMUM_LIMIT_GIB,
                    "robust_limit_gib": V7_STREAMED_PETROV_ROBUST_LIMIT_GIB,
                    "authority": "parent_process_tree_samples",
                    "pass": None,
                },
                "factor_inventory": {
                    "base_factor_count": 0,
                    "exact_factor_count": 0,
                    "global_direct_factor_count": 0,
                    "nested_ksp": 0,
                },
                "top": "not_run_by_bottom_producer_contract",
                "consumer": "not_run",
                "outer": "not_run",
                "recovery": "not_run",
                "field": "not_run",
                "RTA": "not_run",
                "telemetry": {
                    "process_tree_samples": {
                        "path": "numerical_output/process_tree_samples.jsonl",
                        "writer": "parent_task038_launcher",
                        "status": "expected_from_parent_launcher",
                    },
                    "memory_stages": {
                        "path": "numerical_output/memory_stages.jsonl",
                        "writer": "parent_task038_launcher_marker_alignment",
                        "status": "expected_from_parent_launcher",
                    },
                    "memory_stage_markers": {
                        "path": "numerical_output/memory_stage_markers.raw.jsonl",
                        "writer": "v3_7_worker",
                        "status": "measured_worker_marker_stream",
                    },
                    "memory_object_ledger": {
                        "path": "numerical_output/memory_object_ledger.json",
                        "schema": "task039.memory-object-ledger.v1",
                        "status": "finalized_in_worker_finalizer",
                    },
                },
            }
        )
        return result
    finally:
        if gradient_provider is not None:
            gradient_provider.destroy()
        if modal_provider is not None:
            modal_provider.destroy()
        if packet_context is not None and not packet_context.diagnostics.get(
            "released", False
        ):
            packet_context.release()
        marker_callback(
            "v7_streamed_bottom_producer_released",
            {
                "packet_context_released": bool(
                    packet_context is None or packet_context.diagnostics["released"]
                ),
                "source_columns_retained": False,
                "holdout_opened": False,
                "exact_spool_opened": False,
                "consumer_qep_calls": 0,
            },
        )


def run_v7_h4_streamed_bottom_petrov_consumer(
    setup: Any,
    *,
    comm: MPI.Intracomm,
    marker_callback: Callable[[str, Mapping[str, Any]], None],
    basis_manifest: str | Path,
    basis_manifest_sha256: str,
    exact_spool_root: str | Path,
    packet_identity: Mapping[str, Any],
    packet_manifest_sha256: str,
) -> dict[str, Any]:
    """Evaluate one streamed basis packet through the frozen bottom ladder."""

    if not getattr(setup, "side_only", False) or not hasattr(setup, "bottom"):
        raise ValueError("V7 streamed consumer requires a bottom-only setup carrier")
    system = setup.bottom
    components = None
    base_action = None
    fixed_action = None
    basis_packet = None
    spool = None
    result: dict[str, Any] | None = None
    schedule = v6_port_modal_training_schedule(
        mode_count=480, external_count=296, source_count=512
    )
    schedule_sha256 = hashlib.sha256(
        json.dumps(schedule, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    expected_provenance = _v7_streamed_basis_provenance(schedule_sha256)
    base_diagnostics: dict[str, Any] = {}

    marker_callback(
        "v7_streamed_bottom_consumer_setup_begin",
        {
            "profile": V7_STREAMED_PETROV_CONSUMER_PROFILE_ID,
            "setup_peak_limit_gib": V7_STREAMED_PETROV_CONSUMER_SETUP_LIMIT_GIB,
            "basis_manifest": str(Path(basis_manifest).resolve()),
            "basis_manifest_sha256": basis_manifest_sha256,
            "exact_spool_root": str(Path(exact_spool_root).resolve()),
            "holdout_opened": False,
            "consumer_qep_calls": 0,
            "required_nested_ksp_count": 0,
            "required_exact_factor_count": 0,
            "required_global_direct_factor_count": 0,
        },
    )

    try:
        components = create_hybrid_local_dtn_action_components(system)
        base_action = build_hybrid_whole_endcap_fixed_smoother_action(
            system, ilu_levels=0
        )
        fixed_action = HybridLocalDtnWoodburyFixedAction(
            base_action,
            components,
            base_identity="whole_endcap_ilu0_woodbury_fixed_action",
            ilu_levels=0,
        )
        base_diagnostics = dict(fixed_action.diagnostics)
        if (
            base_diagnostics.get("nested_ksp_count") != 0
            or base_diagnostics.get("exact_factor_count") != 0
            or base_diagnostics.get("global_direct_factor_count") != 0
        ):
            raise ValueError(
                "V7 streamed consumer fixed action violates factor-free inventory"
            )
        target_ownership_range = tuple(
            int(value) for value in system.A.getOwnershipRange()
        )
        target_ownership_ranges = comm.allgather(list(target_ownership_range))
        target_global_rows = int(system.A.getSize()[0])
        marker_callback(
            "v7_streamed_bottom_consumer_base_ready",
            {
                "operator_identity": "system.A",
                "base_action": base_diagnostics,
                "nested_ksp_count": base_diagnostics.get("nested_ksp_count"),
                "exact_factor_count": base_diagnostics.get("exact_factor_count"),
                "global_direct_factor_count": base_diagnostics.get(
                    "global_direct_factor_count"
                ),
                "target_global_rows": target_global_rows,
                "target_ownership_range": list(target_ownership_range),
                "target_ownership_ranges": target_ownership_ranges,
                "fixed_linear": True,
            },
        )
        basis_packet = load_streamed_owner_row_basis_packet(
            basis_manifest,
            expected_manifest_sha256=basis_manifest_sha256,
            expected_schedule_sha256=schedule_sha256,
            expected_provenance=expected_provenance,
            ownership_range=target_ownership_range,
            global_size=target_global_rows,
            comm=comm,
        )
        marker_callback(
            "v7_streamed_bottom_consumer_basis_mmap_ready",
            {
                "packet": basis_packet.diagnostics,
                "prefix_checkpoints": list(V7_STREAMED_PETROV_CHECKPOINTS),
                "global_basis_materialized": False,
            },
        )
        spool = _load_v5_fixed_budget_spool_shards(
            exact_spool_root,
            comm,
            packet_identity=packet_identity,
            manifest_sha256=packet_manifest_sha256,
        )
        marker_callback(
            "v7_streamed_bottom_consumer_holdout_ready",
            {
                "holdout_opened": True,
                "exact_spool_opened": True,
                "holdout_labels": list(spool),
                "consumer_qep_calls": 0,
            },
        )

        def holdout_evaluator(action: Any, checkpoint: int) -> dict[str, Any]:
            reports: list[dict[str, Any]] = []
            for label, artifact in spool.items():
                template = rhs = reference = None
                try:
                    template = system.A.createVecLeft()
                    rhs = _load_v5_blr_reference_spool_remapped(
                        artifact["rhs"], template
                    )
                    reference = _load_v5_blr_reference_spool_remapped(
                        artifact["exact_output"], template
                    )
                    report, _ = _v5_blr_probe(
                        action,
                        system,
                        rhs,
                        dict(artifact["rhs"]["probe_metadata"]),
                        reference,
                        repeat=True,
                        linearity=True,
                    )
                    reports.append(report)
                finally:
                    if reference is not None:
                        reference.destroy()
                    if rhs is not None:
                        rhs.destroy()
                    if template is not None:
                        template.destroy()
            gate = _v6_port_modal_holdout_gate(reports)
            return {
                "reports": reports,
                "gate": gate,
                "gate_pass": bool(gate["pass"]),
            }

        def checkpoint_callback(
            event: str, checkpoint: int, detail: Mapping[str, Any]
        ) -> None:
            suffix = {
                "setup_begin": "begin",
                "setup_end": "setup_end",
                "holdout_end": "end",
            }[event]
            marker_callback(
                f"v7_streamed_bottom_consumer_checkpoint_{checkpoint}_{suffix}",
                {"checkpoint": int(checkpoint), **dict(detail)},
            )

        ladder = run_streamed_owner_row_petrov_consumer(
            basis_packet,
            system.A,
            fixed_action,
            holdout_evaluator=holdout_evaluator,
            checkpoint_callback=checkpoint_callback,
            factor_inventory=base_diagnostics,
            condition_limit=1.0e12,
        )
        numerical_pass = ladder["first_passing_checkpoint"] is not None
        result = {
            "schema": V7_STREAMED_PETROV_CONSUMER_SCHEMA,
            "status": "consumer_completed",
            "component_candidate": True,
            "research_only": True,
            "general_production": False,
            "profile": V7_STREAMED_PETROV_CONSUMER_PROFILE_ID,
            "operator_identity": "system.A",
            "schedule": {
                "count": len(schedule),
                "checkpoints": list(V7_STREAMED_PETROV_CHECKPOINTS),
                "sha256": schedule_sha256,
                "batch_size": V7_STREAMED_PETROV_BATCH_SIZE,
            },
            "packet": {
                "basis_manifest": str(Path(basis_manifest).resolve()),
                "basis_manifest_sha256": basis_manifest_sha256,
                "basis_packet_schema": basis_packet.manifest.get("schema"),
                "basis_mmap_retained_until_cleanup": True,
                "training_holdout_disjoint": True,
                "holdout_exact_spool_opened_after_basis_load": True,
                "consumer_qep_calls": 0,
            },
            "exact_spool_root": str(Path(exact_spool_root).resolve()),
            "base_action": base_diagnostics,
            "rank_ladder": ladder,
            "checkpoints": ladder["reports"],
            "first_passing_checkpoint": ladder["first_passing_checkpoint"],
            "gates": {
                "numerical_pass": numerical_pass,
                "finite": "per_checkpoint_gate",
                "repeat_limit": 1.0e-10,
                "linearity_limit": 1.0e-10,
                "mandatory_true_residual_limit": 1.0e-2,
                "preferred_true_residual_limit": 1.0e-3,
                "coarse_e_condition_limit": 1.0e12,
                "exact_factor_count": ladder.get("exact_factor_count"),
                "global_direct_factor_count": ladder.get("global_direct_factor_count"),
                "nested_ksp_count": ladder.get("nested_ksp_count"),
                "factor_inventory_verified": ladder.get("factor_inventory_verified"),
                "resource_pass": None,
                "setup_peak_limit_gib": V7_STREAMED_PETROV_CONSUMER_SETUP_LIMIT_GIB,
                "swap_pass": None,
                "resource_authority": "parent_process_tree_samples",
            },
            "factor_inventory": ladder["factor_inventory"],
            "top": "not_run_by_bottom_consumer_contract",
            "outer": "not_run",
            "recovery": "not_run",
            "field": "not_run",
            "RTA": "not_run",
            "telemetry": {
                "process_tree_samples": {
                    "path": "numerical_output/process_tree_samples.jsonl",
                    "writer": "parent_task038_launcher",
                },
                "memory_stages": {
                    "path": "numerical_output/memory_stages.jsonl",
                    "writer": "parent_task038_launcher_marker_alignment",
                },
                "memory_stage_markers": {
                    "path": "numerical_output/memory_stage_markers.raw.jsonl",
                    "writer": "v3_7_worker",
                },
                "memory_object_ledger": {
                    "path": "numerical_output/memory_object_ledger.json",
                    "status": "finalized_in_worker_finalizer",
                },
            },
        }
        return result
    finally:
        packet_release = None
        if basis_packet is not None:
            packet_before = basis_packet.diagnostics
            basis_packet.destroy()
            packet_release = {
                "before": packet_before,
                "after": basis_packet.diagnostics,
            }
            marker_callback(
                "v7_streamed_bottom_consumer_basis_mmap_released",
                packet_release,
            )
        spool = None
        marker_callback(
            "v7_streamed_bottom_consumer_holdout_released",
            {"arrays_retained": False, "vectors_retained": False},
        )
        fixed_diagnostics = None
        if fixed_action is not None:
            fixed_action.destroy()
            fixed_diagnostics = dict(fixed_action.diagnostics)
        components_destroyed = False
        if components is not None:
            components.destroy()
            components_destroyed = bool(getattr(components, "_destroyed", False))
        base_after_destroy = None
        if base_action is not None:
            base_action.destroy()
            base_after_destroy = dict(base_action.diagnostics)
        cleanup = collective_heap_cleanup(comm)
        marker_callback(
            "v7_streamed_bottom_consumer_setup_end",
            {
                "basis_packet_release": packet_release,
                "fixed_action": fixed_diagnostics,
                "components_destroyed": components_destroyed,
                "base_action": base_after_destroy,
                "collective_cleanup": cleanup,
                "exact_factor_count": (
                    None
                    if fixed_diagnostics is None
                    else fixed_diagnostics.get("exact_factor_count")
                ),
                "global_direct_factor_count": (
                    None
                    if fixed_diagnostics is None
                    else fixed_diagnostics.get("global_direct_factor_count")
                ),
                "nested_ksp_count": (
                    None
                    if fixed_diagnostics is None
                    else fixed_diagnostics.get("nested_ksp_count")
                ),
            },
        )
        if result is not None:
            result["lifecycle"] = {
                "basis_packet": packet_release,
                "components_destroyed": components_destroyed,
                "fixed_action": fixed_diagnostics,
                "base_action": base_after_destroy,
                "collective_cleanup": cleanup,
                "packet_mmap_released": bool(
                    packet_release is not None
                    and packet_release["after"].get("mmap_released") is True
                ),
            }


def _load_v5_fixed_budget_spool_shards(
    root: str | Path,
    comm: MPI.Intracomm,
    *,
    packet_identity: Mapping[str, Any],
    manifest_sha256: str,
) -> dict[str, dict[str, Any]]:
    """Validate producer shards and return descriptors for ownership remapping.

    Legacy exact-output metadata contains only ``label``.  RHS/exact pairing
    is therefore established by the shared label, role, packet identity,
    per-role contiguous ownership coverage, and each array's own hash.
    """

    spool_root = Path(root).resolve() / "v5_blr_reference_spool"
    descriptors: dict[str, dict[str, list[dict[str, Any]]]] | None = None
    probe_metadata_by_label: dict[str, dict[str, Any]] = {}
    exact_output_metadata_by_label: dict[str, dict[str, Any]] = {}
    structure_error: str | None = None
    try:
        descriptors = {
            label: {"rhs": [], "exact_output": []}
            for label, _kind, _seed in V5_H4_BLR_RHS_SPECS
        }
        for source_rank in range(int(comm.size)):
            rank_directory = spool_root / f"rank{source_rank:04d}"
            if not rank_directory.is_dir():
                raise ValueError(
                    f"Missing fixed-budget spool rank directory: {rank_directory}"
                )
            for label, _kind, _seed in V5_H4_BLR_RHS_SPECS:
                for role in ("rhs", "exact_output"):
                    metadata_path = rank_directory / f"bottom_{label}_{role}.json"
                    record = json.loads(metadata_path.read_text(encoding="utf-8"))
                    source_identity = record.get("source_identity")
                    packet_wrapper = (
                        source_identity.get("packet_identity")
                        if isinstance(source_identity, Mapping)
                        else None
                    )
                    source_packet = (
                        packet_wrapper.get("packet_identity")
                        if isinstance(packet_wrapper, Mapping)
                        else None
                    )
                    source_manifest = (
                        packet_wrapper.get("manifest_sha256")
                        if isinstance(packet_wrapper, Mapping)
                        else None
                    )
                    if (
                        record.get("side") != "bottom"
                        or record.get("label") != label
                        or record.get("role") != role
                        or source_packet != dict(packet_identity)
                        or source_manifest != manifest_sha256
                    ):
                        raise ValueError(
                            f"Fixed-budget spool identity mismatch: {metadata_path}"
                        )
                    metadata_hash = record.get("metadata_payload_sha256_excluding_self")
                    metadata_payload = dict(record)
                    metadata_payload.pop("metadata_payload_sha256_excluding_self", None)
                    if (
                        not isinstance(metadata_hash, str)
                        or hashlib.sha256(
                            json.dumps(
                                metadata_payload,
                                sort_keys=True,
                                separators=(",", ":"),
                                ensure_ascii=False,
                            ).encode()
                        ).hexdigest()
                        != metadata_hash
                    ):
                        raise ValueError(
                            f"Fixed-budget spool metadata hash mismatch: {metadata_path}"
                        )
                    ownership = record.get("ownership_range")
                    if (
                        not isinstance(ownership, list)
                        or len(ownership) != 2
                        or int(ownership[1]) <= int(ownership[0])
                        or int(record.get("local_size", -1))
                        != int(ownership[1]) - int(ownership[0])
                        or str(record.get("dtype")) != "complex128"
                        or int(record.get("global_size", -1)) <= 0
                    ):
                        raise ValueError(
                            f"Fixed-budget spool descriptor shape mismatch: {metadata_path}"
                        )
                    array_path = Path(str(record["array_path"])).resolve()
                    record = {
                        **record,
                        "array_path": str(array_path),
                        "metadata_path": str(metadata_path.resolve()),
                        "source_rank": source_rank,
                    }
                    descriptors[label][role].append(record)
        for label in descriptors:
            spec_kind, spec_seed = next(
                (kind, seed)
                for current_label, kind, seed in V5_H4_BLR_RHS_SPECS
                if current_label == label
            )
            probe_metadata: dict[str, Any] | None = None
            for role in ("rhs", "exact_output"):
                shards = sorted(
                    descriptors[label][role], key=lambda item: item["source_rank"]
                )
                for shard in shards:
                    candidate_metadata = shard.get("source_identity", {}).get(
                        "probe_metadata"
                    )
                    if (
                        not isinstance(candidate_metadata, Mapping)
                        or candidate_metadata.get("label") != label
                    ):
                        raise ValueError("Fixed-budget spool probe metadata mismatch")
                    if role == "exact_output":
                        if dict(candidate_metadata) != {"label": label}:
                            raise ValueError(
                                "Fixed-budget exact-output legacy metadata mismatch"
                            )
                        exact_output_metadata_by_label[label] = dict(candidate_metadata)
                    if role == "rhs":
                        expected_degenerate = label == "physical_side_rhs"
                        if (
                            candidate_metadata.get("degenerate_uninformative")
                            is not expected_degenerate
                        ):
                            raise ValueError(
                                "Fixed-budget spool degenerate probe metadata mismatch"
                            )
                        if (
                            spec_seed is not None
                            and candidate_metadata.get("seed") != spec_seed
                        ):
                            raise ValueError(
                                "Fixed-budget spool probe seed metadata mismatch"
                            )
                        identity = candidate_metadata.get("identity")
                        if not isinstance(identity, Mapping):
                            raise ValueError(
                                "Fixed-budget spool probe identity metadata is missing"
                            )
                        canonical_metadata = dict(candidate_metadata)
                        canonical_identity = dict(identity)
                        canonical_identity.pop("local_sha256", None)
                        canonical_identity.pop("ownership_range", None)
                        canonical_metadata["identity"] = canonical_identity
                        canonical_metadata["kind"] = spec_kind
                        canonical_metadata["seed"] = spec_seed
                        if probe_metadata is None:
                            probe_metadata = canonical_metadata
                        elif canonical_metadata != probe_metadata:
                            raise ValueError(
                                "Fixed-budget spool probe metadata differs by shard"
                            )
                ranges = [tuple(map(int, item["ownership_range"])) for item in shards]
                global_sizes = {int(item["global_size"]) for item in shards}
                if len(global_sizes) != 1 or not ranges or ranges[0][0] != 0:
                    raise ValueError("Fixed-budget spool ownership coverage mismatch")
                previous_end = 0
                for start, end in ranges:
                    if start != previous_end:
                        raise ValueError(
                            "Fixed-budget spool ownership has a gap or overlap"
                        )
                    previous_end = end
                if previous_end != next(iter(global_sizes)):
                    raise ValueError(
                        "Fixed-budget spool ownership does not cover global size"
                    )
                descriptors[label][role] = shards
            if probe_metadata is None:
                raise ValueError("Fixed-budget spool RHS probe metadata is missing")
            probe_metadata_by_label[label] = probe_metadata
    except Exception as exc:
        structure_error = f"{type(exc).__name__}: {exc}"

    structure_states = comm.allgather(structure_error)
    if any(state is not None for state in structure_states):
        raise ValueError(
            "Fixed-budget spool shard validation failed: "
            + next(state for state in structure_states if state is not None)
        )
    assert descriptors is not None

    local_error: str | None = None
    try:
        for label in descriptors:
            for role in ("rhs", "exact_output"):
                record = descriptors[label][role][comm.rank]
                values = np.load(
                    record["array_path"], allow_pickle=False, mmap_mode="r"
                )
                if (
                    values.shape != (int(record["local_size"]),)
                    or str(values.dtype) != "complex128"
                    or hashlib.sha256(values.tobytes()).hexdigest()
                    != record.get("array_sha256")
                ):
                    raise ValueError(
                        f"Fixed-budget spool array hash/shape mismatch: {record['array_path']}"
                    )
                del values
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"
    array_states = comm.allgather(local_error)
    if any(state is not None for state in array_states):
        raise ValueError(
            "Fixed-budget spool shard array validation failed: "
            + next(state for state in array_states if state is not None)
        )

    return {
        label: {
            "label": label,
            "kind": kind,
            "seed": seed,
            "rhs": {
                "shards": descriptors[label]["rhs"],
                "probe_metadata": probe_metadata_by_label[label],
            },
            "exact_output": {
                "shards": descriptors[label]["exact_output"],
                "probe_metadata": exact_output_metadata_by_label[label],
            },
        }
        for label, kind, seed in V5_H4_BLR_RHS_SPECS
    }


def _load_v5_blr_reference_spool_remapped(
    record: Mapping[str, Any], template: PETSc.Vec
) -> PETSc.Vec:
    """Load source shards into the current template ownership without replication."""

    shards = record.get("shards")
    if not isinstance(shards, list) or not shards:
        raise ValueError("Fixed-budget spool remap requires shard descriptors")
    target_start, target_end = map(int, template.getOwnershipRange())
    global_size = int(template.getSize())
    if target_start < 0 or target_end > global_size or target_start >= target_end:
        raise ValueError("Fixed-budget target Vec ownership is invalid")
    target = template.duplicate()
    local_values = target.getArray()
    filled = np.zeros(local_values.size, dtype=bool)
    for shard in shards:
        source_start, source_end = map(int, shard["ownership_range"])
        overlap_start = max(target_start, source_start)
        overlap_end = min(target_end, source_end)
        if overlap_start >= overlap_end:
            continue
        values = np.load(shard["array_path"], allow_pickle=False, mmap_mode="r")
        if (
            values.shape != (int(shard["local_size"]),)
            or str(values.dtype) != "complex128"
        ):
            del values
            target.destroy()
            raise ValueError("Fixed-budget remap source array shape/dtype mismatch")
        target_slice = slice(overlap_start - target_start, overlap_end - target_start)
        source_slice = slice(overlap_start - source_start, overlap_end - source_start)
        local_values[target_slice] = values[source_slice]
        filled[target_slice] = True
        del values
    if not bool(np.all(filled)):
        target.destroy()
        raise ValueError("Fixed-budget remap did not cover target ownership")
    target.assemble()
    return target


def _short_side_ksp_residual(
    system: Any, rhs: PETSc.Vec, *, max_it: int, source: str
) -> tuple[PETSc.Vec, dict[str, Any]]:
    """Create one explicit ``rhs - A * x`` residual for a side probe."""

    rhs_norm = float(rhs.norm())
    if not np.isfinite(rhs_norm) or rhs_norm <= 1.0e-30:
        raise ValueError("side-KSP probe RHS must be finite and nonzero")
    ksp = PETSc.KSP().create(system.A.getComm())
    solution = system.A.createVecRight()
    residual = system.A.createVecLeft()
    applied = system.A.createVecLeft()
    try:
        ksp.setOperators(system.A)
        ksp.setType("gmres")
        ksp.getPC().setType("none")
        ksp.setInitialGuessNonzero(False)
        ksp.setTolerances(rtol=1.0e-14, atol=0.0, max_it=max_it)
        ksp.solve(rhs, solution)
        iterations = int(ksp.getIterationNumber())
        reason = int(ksp.getConvergedReason())
        if iterations <= 0:
            raise RuntimeError("side GMRES produced no residual iteration")
        expected_nonconverged = int(PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT)
        if reason == 0 or (reason < 0 and reason != expected_nonconverged):
            raise RuntimeError(
                f"side GMRES returned an unexpected failure reason: {reason}"
            )
        system.A.mult(solution, applied)
        rhs.copy(residual)
        residual.axpy(PETSc.ScalarType(-1.0), applied)
        solution_norm = float(solution.norm())
        residual_norm = float(residual.norm())
        if not np.isfinite(solution_norm) or not np.isfinite(residual_norm):
            raise RuntimeError("side GMRES produced a non-finite solution/residual")
        return residual, {
            "source": source,
            "max_it": int(max_it),
            "rhs_source": source,
            "rhs_norm": rhs_norm,
            "solution_norm": solution_norm,
            "explicit_residual_norm": residual_norm,
            "explicit_residual_relative": residual_norm / rhs_norm,
            "residual_source": "explicit_b_minus_Ax",
            "ksp_iterations": iterations,
            "ksp_reason": reason,
            "expected_nonconverged_reason": expected_nonconverged,
        }
    finally:
        applied.destroy()
        solution.destroy()
        ksp.destroy()


def _side_survey_vectors(
    system: Any,
    side: str,
    supplied: Mapping[str, PETSc.Vec] | None,
) -> tuple[dict[str, PETSc.Vec], list[PETSc.Vec], dict[str, Any]]:
    vectors: dict[str, PETSc.Vec] = {"physical_side_rhs": system.b.copy()}
    owned = [vectors["physical_side_rhs"]]
    metadata: dict[str, Any] = {}
    if supplied is not None:
        for label, vector in supplied.items():
            vectors[label] = vector.copy()
            owned.append(vectors[label])
    first, last = (int(value) for value in system.b.getOwnershipRange())
    index = np.arange(first, last, dtype=np.float64)
    for seed in (739, 743, 751, 757):
        vector = system.b.copy()
        vector.getArray()[:] = np.asarray(
            np.sin(index * 0.001 + seed) + 1j * np.cos(index * 0.0007 - seed),
            dtype=PETSc.ScalarType,
        )
        vector.assemble()
        label = f"global_index_seed_{seed}"
        vectors[label] = vector
        owned.append(vector)
    for max_it in (1, 3):
        label = f"early_krylov_residual_it{max_it}"
        probe = vectors["global_index_seed_739"]
        krylov, krylov_meta = _short_side_ksp_residual(
            system,
            probe,
            max_it=max_it,
            source=f"side_unpreconditioned_gmres_it{max_it}",
        )
        krylov_meta["probe_source"] = "global_index_seed_739"
        krylov_meta["probe_identity"] = _side_vector_identity(
            probe, "global_index_seed_739"
        )
        vectors[label] = krylov
        owned.append(krylov)
        metadata[label] = krylov_meta
    metadata["side"] = side
    return vectors, owned, metadata


def _side_correction_probe(
    system: Any,
    action: Any,
    pass_count: int,
    vectors: Mapping[str, PETSc.Vec],
    vector_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    reports: dict[str, Any] = {}
    rho_values: list[float] = []
    for label, source in vectors.items():
        target = system.A.createVecLeft()
        residual = system.A.createVecLeft()
        try:
            action.apply(source, target)
            system.A.mult(target, residual)
            residual.axpy(PETSc.ScalarType(-1.0), source)
            source_norm = float(source.norm())
            residual_norm = float(residual.norm())
            finite = bool(np.isfinite(source_norm) and np.isfinite(residual_norm))
            if source_norm <= 1.0e-30 and finite:
                reports[label] = {
                    "rho": None,
                    "denominator": "max(norm(side_rhs_or_probe),1e-30)",
                    "finite": True,
                    "informative": False,
                    "status": "degenerate_uninformative",
                    "source_norm": source_norm,
                    "residual_norm": residual_norm,
                    "vector": _side_vector_identity(source, label),
                }
            else:
                rho = residual_norm / source_norm if finite else float("nan")
                if np.isfinite(rho):
                    rho_values.append(rho)
                reports[label] = {
                    "rho": float(rho) if np.isfinite(rho) else None,
                    "denominator": "max(norm(side_rhs_or_probe),1e-30)",
                    "finite": bool(np.isfinite(rho)),
                    "informative": bool(np.isfinite(rho)),
                    "status": "measured" if np.isfinite(rho) else "nonfinite",
                    "source_norm": source_norm,
                    "residual_norm": residual_norm,
                    "vector": _side_vector_identity(source, label),
                }
        finally:
            residual.destroy()
            target.destroy()
    complete = len(reports) == len(vectors) and all(
        item["finite"] for item in reports.values()
    )
    informative_labels = [
        label for label, item in reports.items() if item["informative"]
    ]
    excluded_labels = [
        label for label, item in reports.items() if not item["informative"]
    ]
    return {
        "pass": complete,
        "correction_passes": int(pass_count),
        "vectors": reports,
        "vector_inventory": {
            "count": len(reports),
            "sources": sorted(reports),
            "informative_labels": informative_labels,
            "excluded_labels": excluded_labels,
            "informative_count": len(informative_labels),
            "excluded_count": len(excluded_labels),
            "metadata": dict(vector_metadata),
        },
        "rho_summary": {
            "median": float(np.median(rho_values)) if rho_values else None,
            "worst": float(max(rho_values)) if rho_values else None,
            "candidate_A_pass": bool(
                rho_values
                and float(np.median(rho_values)) <= 0.2
                and float(max(rho_values)) <= 0.5
            ),
        },
    }


def _candidate_b_side_probe(
    system: Any,
    action: Any,
    budget: int,
    vectors: Mapping[str, PETSc.Vec],
    vector_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Measure Candidate-B true residuals and retain per-apply KSP facts."""

    reports: dict[str, Any] = {}
    rho_values: list[float] = []
    for label, source in vectors.items():
        target = system.A.createVecLeft()
        residual = system.A.createVecLeft()
        try:
            source_norm = float(source.norm())
            if not np.isfinite(source_norm):
                error = ValueError(
                    f"Candidate-B probe source norm is non-finite: label={label}"
                )
                error.finite_audit = {
                    "stage": "candidate_b_probe_source_norm",
                    "vector": label,
                    "finite": False,
                    "source_norm": source_norm,
                }
                raise error
            if source_norm <= 1.0e-30:
                reports[label] = {
                    "source": label,
                    "vector": _side_vector_identity(source, label),
                    "source_norm": source_norm,
                    "residual_norm": None,
                    "finite": True,
                    "rho": None,
                    "informative": False,
                    "status": "degenerate_uninformative",
                }
                continue
            action.apply(source, target)
            system.A.mult(target, residual)
            residual.axpy(PETSc.ScalarType(-1.0), source)
            residual_norm = float(residual.norm())
            finite = bool(np.isfinite(source_norm) and np.isfinite(residual_norm))
            action_diagnostics = dict(action.diagnostics)
            apply_diagnostics = {
                key: action_diagnostics.get(key)
                for key in (
                    "requested_budget",
                    "last_inner_iterations",
                    "last_converged_reason",
                    "apply_count",
                    "last_apply_seconds",
                    "total_inner_iterations",
                    "total_apply_seconds",
                )
            }
            item = {
                "source": label,
                "vector": _side_vector_identity(source, label),
                "source_norm": source_norm,
                "residual_norm": residual_norm,
                "finite": finite,
                "apply": apply_diagnostics,
            }
            rho = residual_norm / source_norm if finite else float("nan")
            if np.isfinite(rho):
                rho_values.append(float(rho))
            item.update(
                {
                    "rho": float(rho) if np.isfinite(rho) else None,
                    "informative": bool(np.isfinite(rho)),
                    "status": "measured" if np.isfinite(rho) else "nonfinite",
                }
            )
            reports[label] = item
        finally:
            residual.destroy()
            target.destroy()
    informative_labels = [
        label for label, item in reports.items() if item["informative"]
    ]
    excluded_labels = [
        label for label, item in reports.items() if not item["informative"]
    ]
    median = float(np.median(rho_values)) if rho_values else None
    worst = float(max(rho_values)) if rho_values else None
    complete = len(reports) == len(vectors) and all(
        item["finite"] for item in reports.values()
    )
    return {
        "status": "measured",
        "pass": complete,
        "budget": int(budget),
        "vectors": reports,
        "vector_inventory": {
            "count": len(reports),
            "informative_labels": informative_labels,
            "excluded_labels": excluded_labels,
            "informative_count": len(informative_labels),
            "excluded_count": len(excluded_labels),
            "metadata": dict(vector_metadata),
        },
        "rho_summary": {
            "median": median,
            "worst": worst,
            "median_limit": V3_8_CANDIDATE_B_MEDIAN_LIMIT,
            "worst_limit": V3_8_CANDIDATE_B_WORST_LIMIT,
            "candidate_B_pass": bool(
                complete
                and rho_values
                and median is not None
                and worst is not None
                and median <= V3_8_CANDIDATE_B_MEDIAN_LIMIT
                and worst <= V3_8_CANDIDATE_B_WORST_LIMIT
            ),
        },
    }


def _run_v3_8_candidate_b_budget(
    budget: int,
    side_systems: Mapping[str, Any],
    fixed_actions: Mapping[str, Any],
    survey_vectors: Mapping[str, Mapping[str, PETSc.Vec]],
    vector_metadata: Mapping[str, Mapping[str, Any]],
    *,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run one budget with at most one live Krylov wrapper at a time."""

    side_reports: dict[str, Any] = {}
    factor_inventory: dict[str, Any] = {}
    for side in ("bottom", "top"):
        action = None
        _emit_marker(
            marker_callback,
            f"candidate_b_budget_{budget}_{side}_begin",
            budget=budget,
            side=side,
        )
        try:
            action = HybridLocalDtnWoodburyFixedBudgetKrylovAction(
                side_systems[side].A,
                fixed_actions[side],
                budget=budget,
            )
            _emit_marker(
                marker_callback,
                f"candidate_b_budget_{budget}_{side}_ready",
                budget=budget,
                side=side,
                wrappers_live=1,
            )
            side_reports[side] = _candidate_b_side_probe(
                side_systems[side],
                action,
                budget,
                survey_vectors[side],
                vector_metadata[side],
            )
            action_diagnostics = action.diagnostics
            base_diagnostics = action.right_preconditioner.diagnostics
            factor_inventory[side] = {
                "base_factor_count": base_diagnostics["base_factor_count"],
                "direct_factor_count": action_diagnostics["direct_factor_count"],
                "global_hybrid_direct_factor_count": action_diagnostics[
                    "global_hybrid_direct_factor_count"
                ],
                "right_preconditioner_identity": action_diagnostics[
                    "right_preconditioner_identity"
                ],
            }
        except Exception as error:
            error.candidate_b_progress = {
                "budget": int(budget),
                "side": side,
            }
            raise
        finally:
            if action is not None:
                action.destroy()
            _emit_marker(
                marker_callback,
                f"candidate_b_budget_{budget}_{side}_end",
                budget=budget,
                side=side,
                wrappers_live=0,
            )
    return {
        "budget": int(budget),
        "bottom": side_reports["bottom"],
        "top": side_reports["top"],
        "pass": bool(
            side_reports["bottom"]["rho_summary"]["candidate_B_pass"]
            and side_reports["top"]["rho_summary"]["candidate_B_pass"]
        ),
        "factor_inventory": factor_inventory,
        "max_live_wrapper_count": 1,
    }


def run_v3_8_candidate_b_budget_sequence(
    side_systems: Mapping[str, Any],
    fixed_actions: Mapping[str, Any],
    survey_vectors: Mapping[str, Mapping[str, PETSc.Vec]],
    vector_metadata: Mapping[str, Mapping[str, Any]],
    *,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run the smallest budget that passes both side Gates."""

    reports: list[dict[str, Any]] = []
    for budget in V3_8_CANDIDATE_B_BUDGETS:
        report = _run_v3_8_candidate_b_budget(
            budget,
            side_systems,
            fixed_actions,
            survey_vectors,
            vector_metadata,
            marker_callback=marker_callback,
        )
        reports.append(report)
        if report["pass"]:
            break
    selected = next((item["budget"] for item in reports if item["pass"] is True), None)

    def simultaneous_total(field: str) -> int:
        return max(
            sum(int(side[field]) for side in item["factor_inventory"].values())
            for item in reports
        )

    return {
        "status": "measured",
        "pass": selected is not None,
        "selected_budget": selected,
        "budgets_run": [item["budget"] for item in reports],
        "budget_reports": reports,
        "gate": {
            "median_limit": V3_8_CANDIDATE_B_MEDIAN_LIMIT,
            "worst_limit": V3_8_CANDIDATE_B_WORST_LIMIT,
            "formula": "rho=norm(b-Ax)/max(norm(b),1e-30)",
        },
        "factor_inventory": {
            "per_budget": [item["factor_inventory"] for item in reports],
            "simultaneous_total_base_factor_count": simultaneous_total(
                "base_factor_count"
            ),
            "simultaneous_total_direct_factor_count": simultaneous_total(
                "direct_factor_count"
            ),
            "simultaneous_total_global_hybrid_direct_factor_count": simultaneous_total(
                "global_hybrid_direct_factor_count"
            ),
        },
    }


def run_task039_v3_7_side_correction_survey(
    setup: Any,
    *,
    side_vectors: Mapping[str, Mapping[str, PETSc.Vec]] | None = None,
    stage_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Survey 1/2/4/8 wrappers while retaining one pair at a time."""

    _emit_marker(
        marker_callback,
        "side_fixed_components_setup_begin",
    )
    components = {
        "bottom": create_hybrid_local_dtn_action_components(setup.bottom),
        "top": create_hybrid_local_dtn_action_components(setup.top),
    }
    fixed = {
        "bottom": build_hybrid_whole_endcap_fixed_smoother_action(setup.bottom),
        "top": build_hybrid_whole_endcap_fixed_smoother_action(setup.top),
    }
    _emit_marker(
        marker_callback,
        "side_fixed_components_setup_end",
    )

    try:
        survey_vectors: dict[str, dict[str, PETSc.Vec]] = {}
        owned_vectors: list[PETSc.Vec] = []
        vector_metadata: dict[str, dict[str, Any]] = {}
        for side, system in (("bottom", setup.bottom), ("top", setup.top)):
            supplied = side_vectors.get(side) if side_vectors is not None else None
            survey_vectors[side], owned, vector_metadata[side] = _side_survey_vectors(
                system, side, supplied
            )
            owned_vectors.extend(owned)
        reports: list[dict[str, Any]] = []
        for pass_count in (1, 2, 4, 8):
            _emit_marker(
                marker_callback,
                f"side_correction_{pass_count}_begin",
                correction_passes=pass_count,
            )
            actions = {
                "bottom": HybridLocalDtnWoodburyFixedAction(
                    fixed["bottom"],
                    components["bottom"],
                    residual_operator=(setup.bottom.A if pass_count > 1 else None),
                    residual_correction_steps=pass_count,
                ),
                "top": HybridLocalDtnWoodburyFixedAction(
                    fixed["top"],
                    components["top"],
                    residual_operator=(setup.top.A if pass_count > 1 else None),
                    residual_correction_steps=pass_count,
                ),
            }
            _emit_marker(
                marker_callback,
                f"side_correction_{pass_count}_ready",
                correction_passes=pass_count,
                wrappers_live=2,
            )
            try:
                side_reports = {
                    side: _side_correction_probe(
                        setup.bottom if side == "bottom" else setup.top,
                        action,
                        pass_count,
                        survey_vectors[side],
                        vector_metadata[side],
                    )
                    for side, action in actions.items()
                }
                reports.append(
                    {
                        "correction_passes": pass_count,
                        "bottom": side_reports["bottom"],
                        "top": side_reports["top"],
                        "pass": bool(
                            side_reports["bottom"]["pass"]
                            and side_reports["top"]["pass"]
                        ),
                        "wrappers_live": 2,
                    }
                )
            finally:
                actions["top"].destroy()
                actions["bottom"].destroy()
                _emit_marker(
                    marker_callback,
                    f"side_correction_{pass_count}_end",
                    correction_passes=pass_count,
                    wrappers_live=0,
                )
        return {
            "status": "measured",
            "pass": bool(all(item["pass"] for item in reports)),
            "pass_counts": [item["correction_passes"] for item in reports],
            "sequential": True,
            "max_live_wrapper_count": 2,
            "passes": reports,
        }
    finally:
        for vector in locals().get("owned_vectors", ()):
            vector.destroy()
        fixed["top"].destroy()
        fixed["bottom"].destroy()
        components["top"].destroy()
        components["bottom"].destroy()
        _emit_marker(
            marker_callback,
            "side_survey_cleanup_end",
        )


def run_v3_7_recovery_runner(
    setup: Any,
    layout: Any,
    snapshot: PETSc.Vec,
    run_directory: Path,
    producer: Mapping[str, Any],
    *,
    run_integrated_checker: bool = True,
) -> dict[str, Any]:
    """Run existing recovery/physics and the reviewed integrated checker."""

    bottom_solution, top_solution, modal_solution = layout.split(
        snapshot,
        setup.bottom.b,
        setup.top.b,
    )
    linear = FrozenM10LinearSolve(
        result=SimpleNamespace(destroy=lambda: None),
        layout=layout,
        bottom_solution=bottom_solution,
        top_solution=top_solution,
        modal_solution=modal_solution,
        linear_pass=True,
        inventory={"source": "v3_7_exact_side_oracle_snapshot"},
        timings={},
        release={"pass": True},
    )
    detail_callback = producer.get("_stage_callback")
    recovery_stage_callback = (
        None
        if detail_callback is None
        else lambda stage: _emit_marker(
            detail_callback, stage, source="recovery_physics"
        )
    )
    recovery = recover_frozen_m10(
        setup,
        linear,
        stage_callback=recovery_stage_callback,
    )
    try:
        physics = run_frozen_m10_physics(
            setup,
            recovery,
            run_directory,
            setup.bottom.local_mesh.mesh.comm,
            stage_callback=recovery_stage_callback,
        )
        _write_v3_7_candidate_authority(
            run_directory,
            physics,
            producer,
            setup.bottom.local_mesh.mesh.comm,
        )
        if run_integrated_checker:
            integrated_checker = (
                check_v3_7_integrated_physics(
                    run_directory,
                    producer.get(
                        "_hybrid_direct_authority_run_directory", V3_7_DIRECT_RUN_ROOT
                    ),
                    producer.get(
                        "_full3d_authority_run_directory", V3_7_FULL3D_RUN_ROOT
                    ),
                )
                if setup.bottom.local_mesh.mesh.comm.rank == 0
                else None
            )
            integrated_checker = setup.bottom.local_mesh.mesh.comm.bcast(
                integrated_checker, root=0
            )
        else:
            integrated_checker = {
                "status": "not_available",
                "pass": False,
                "role": "full3d_secondary_not_run",
            }
        integrated_pass = (
            not run_integrated_checker or integrated_checker.get("pass") is True
        )
        return {
            "pass": bool(
                physics.physics_pass and recovery.recovery_pass and integrated_pass
            ),
            "producer_source_sha": producer.get("producer_source_sha"),
            "recovery_pass": bool(recovery.recovery_pass),
            "physics_pass": bool(physics.physics_pass),
            "integrated_checker": integrated_checker,
        }
    finally:
        recovery.destroy()


def _write_v3_7_candidate_authority(
    run_directory: Path,
    physics: Any,
    producer: Mapping[str, Any],
    comm: MPI.Intracomm,
) -> Path:
    """Persist the small raw projection consumed by the independent checker."""

    if physics.own_grid is None:
        raise RuntimeError("V3-7 candidate physics did not produce its grid payload")
    orders = list(physics.external_orders)
    keys = [
        {
            "side": row["side"],
            "m": int(row["m"]),
            "n": int(row["n"]),
            "polarization": row["polarization"],
        }
        for row in orders
    ]
    projection = physics.interface_e_projection
    projection_value = float(projection["combined_relative_residual"])
    authority = {
        "schema": "task039.v3-7-hybrid-authority.v1",
        "status": "measured_candidate_physics",
        "model_id": producer.get(
            "consumer_model_id", "task039_5nm_v3_1deg_s5_hybrid_iterative_m480"
        ),
        "source_sha": producer.get("consumer_source_sha"),
        "physical_model_sha256": producer["physical_model_sha256"],
        "mpi_size": 8,
        "requested_modes": 480,
        "inventory_count": len(keys),
        "external_mode_inventory": {"keys": keys},
        "external_orders": orders,
        "observables": {
            "R_total": physics.energy["R"],
            "T_total": physics.energy["T"],
            "A_balance": physics.energy["A"],
            "A_volume": physics.energy["A_volume"],
        },
        "closure": physics.energy["closure"],
        "traction": {
            side: {"relative_residual": physics.traction[side]["relative_dual"]}
            for side in ("bottom", "top")
        },
        "interface_projection": projection_value,
        "grid_payload": dict(physics.own_grid),
    }
    qualification_scope = producer.get("qualification_scope")
    if qualification_scope == TASK039_V4_H4_CASE_QUALIFICATION_SCOPE:
        authority["qualification_scope"] = qualification_scope
        authority["qualification_method"] = producer.get("qualification_method")
        authority["canonical"] = dict(physics.canonical)
    path = run_directory / "numerical_output" / "v3_7_hybrid_authority.json"
    if comm.rank == 0:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(_json_safe(authority), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    comm.barrier()
    return path


def check_v3_7_integrated_physics(
    hybrid_run_directory: str | Path,
    direct_run_directory: str | Path,
    full3d_run_directory: str | Path | None = None,
) -> dict[str, Any]:
    """Check candidate physics against Hybrid-direct; Full3D is secondary."""

    candidate = Path(hybrid_run_directory)
    if not (candidate / "numerical_output" / "v3_7_hybrid_authority.json").is_file():
        return {
            "status": "not_available",
            "pass": False,
            "reason": "candidate authority record is not persisted",
        }
    direct = Path(direct_run_directory)
    if not direct.is_dir():
        return {
            "status": "not_available",
            "pass": False,
            "reason": "fixed Hybrid-direct authority is not available",
        }
    try:
        result = compare_v3_7_hybrid_candidate_to_direct(candidate, direct)
    except Exception as exc:
        return {
            "status": "checker_error",
            "pass": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    secondary: dict[str, Any] | None = {
        "status": "not_available",
        "pass": False,
        "role": "full3d_secondary_not_run",
    }
    if full3d_run_directory is not None:
        full3d = Path(full3d_run_directory)
        if full3d.is_dir():
            try:
                secondary = {
                    "status": "measured",
                    "gate": compare_v3_7_hybrid_candidate_to_full3d(candidate, full3d),
                }
            except Exception as exc:
                secondary = {
                    "status": "checker_error",
                    "pass": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "role": "secondary_only_not_hybrid_authority",
                }
    return {
        "status": "measured",
        "pass": bool(result.get("pass") is True),
        "classification": result.get("classification"),
        "authority": "fixed_1deg_hybrid_direct",
        "gate": result,
        "full3d_secondary": secondary,
    }


def _default_rhs(setup: Any, layout: Any) -> PETSc.Vec:
    return layout.pack(
        setup.bottom.b,
        setup.top.b,
        internal_modal_rhs_correction(setup.coupling),
    )


def _destroy(value: Any) -> None:
    if value is not None and hasattr(value, "destroy"):
        value.destroy()


def _relative_error(actual: PETSc.Vec, expected: PETSc.Vec) -> float:
    difference = actual.duplicate()
    actual.copy(difference)
    difference.axpy(PETSc.ScalarType(-1.0), expected)
    try:
        return float(difference.norm()) / max(float(expected.norm()), 1.0e-30)
    finally:
        difference.destroy()


def _v3_7_cleanup_callback(
    comm: MPI.Intracomm,
    callback: Callable[[], Mapping[str, Any]] | None,
) -> Callable[[], Mapping[str, Any]]:
    """Use the repository collective heap cleanup for the formal worker."""

    return callback if callback is not None else lambda: collective_heap_cleanup(comm)


def _emit_marker(
    callback: Callable[[str, Mapping[str, Any]], None] | None,
    marker: str,
    **detail: Any,
) -> None:
    if callback is not None:
        callback(marker, detail)


def _v5_side_matrix_inventory(side: Any) -> dict[str, Any]:
    return {
        name: _petsc_matrix_stats(getattr(side, name), assemble=False)
        for name in ("F", "C", "D", "H")
    }


def _v6_layer_graph_from_csr(
    row_ptr: np.ndarray,
    column_indices: np.ndarray,
    row_layers: np.ndarray,
    column_layers: np.ndarray,
    *,
    layer_count: int,
) -> dict[str, Any]:
    """Count F-layer couplings from a real row-layer map and local CSR."""

    row_ptr = np.asarray(row_ptr, dtype=np.int64)
    column_indices = np.asarray(column_indices, dtype=np.int64)
    row_layers = np.asarray(row_layers, dtype=np.int64)
    column_layers = np.asarray(column_layers, dtype=np.int64)
    if row_ptr.ndim != 1 or len(row_ptr) != len(row_layers) + 1:
        raise ValueError("V6 layer graph CSR row pointer shape is invalid")
    if row_ptr[0] != 0 or row_ptr[-1] != len(column_indices):
        raise ValueError("V6 layer graph CSR row pointer does not close")
    if len(column_layers) == 0 or np.any(column_layers < 0):
        raise ValueError("V6 layer graph has unmapped column layers")
    if np.any(row_layers < 0) or np.any(row_layers >= layer_count):
        raise ValueError("V6 layer graph has unmapped row layers")
    layer_rows = np.bincount(row_layers, minlength=layer_count).astype(np.int64)
    layer_nnz = np.zeros(layer_count, dtype=np.int64)
    layer_pair_nnz = np.zeros((layer_count, layer_count), dtype=np.int64)
    same = adjacent = long_range = 0
    half_bandwidth = 0
    for local_row, row_layer in enumerate(row_layers):
        columns = column_indices[row_ptr[local_row] : row_ptr[local_row + 1]]
        if np.any(columns < 0) or np.any(columns >= len(column_layers)):
            raise ValueError("V6 layer graph CSR column is outside global rows")
        deltas = np.abs(column_layers[columns] - row_layer)
        layer_nnz[row_layer] += len(columns)
        np.add.at(layer_pair_nnz[row_layer], column_layers[columns], 1)
        same += int(np.count_nonzero(deltas == 0))
        adjacent += int(np.count_nonzero(deltas == 1))
        long_range += int(np.count_nonzero(deltas > 1))
        if len(deltas):
            half_bandwidth = max(half_bandwidth, int(np.max(deltas)))
    total = int(len(column_indices))
    return {
        "status": "measured",
        "metric_space": "F_owned_CSR_nonzero_count",
        "layer_count": int(layer_count),
        "rows_by_layer": [int(value) for value in layer_rows],
        "nnz_by_layer": [int(value) for value in layer_nnz],
        "layer_pair_nnz": layer_pair_nnz.tolist(),
        "nnz_total": total,
        "same_layer_nnz": int(same),
        "adjacent_layer_nnz": int(adjacent),
        "long_range_nnz": int(long_range),
        "same_layer_fraction": float(same / total) if total else None,
        "adjacent_layer_fraction": float(adjacent / total) if total else None,
        "long_range_fraction": float(long_range / total) if total else None,
        "block_half_bandwidth": int(half_bandwidth),
    }


def _v6_global_minimum_layer_labels(
    local_labels: np.ndarray, global_rows: int, comm: MPI.Intracomm
) -> np.ndarray:
    """Compatibility wrapper over the shared distributed label reduction."""

    return minimum_layer_labels(local_labels, global_rows, comm)


def _v6_reduce_layer_graph(
    local: Mapping[str, Any], comm: MPI.Intracomm, *, global_rows: int
) -> dict[str, Any]:
    """Reduce local CSR graph counts to one deterministic global audit."""

    layer_count = int(local["layer_count"])
    rows = np.asarray(local["rows_by_layer"], dtype=np.int64)
    nnz = np.asarray(local["nnz_by_layer"], dtype=np.int64)
    pairs = np.asarray(local["layer_pair_nnz"], dtype=np.int64)
    classes = np.asarray(
        [
            local["same_layer_nnz"],
            local["adjacent_layer_nnz"],
            local["long_range_nnz"],
        ],
        dtype=np.int64,
    )
    if rows.shape != (layer_count,) or nnz.shape != (layer_count,):
        raise ValueError("V6 layer graph marginal shape is invalid")
    if pairs.shape != (layer_count, layer_count):
        raise ValueError("V6 layer graph pair matrix shape is invalid")
    rows = np.asarray(comm.allreduce(rows, op=MPI.SUM))
    nnz = np.asarray(comm.allreduce(nnz, op=MPI.SUM))
    pairs = np.asarray(comm.allreduce(pairs, op=MPI.SUM))
    classes = np.asarray(comm.allreduce(classes, op=MPI.SUM))
    bandwidth = int(comm.allreduce(int(local["block_half_bandwidth"]), op=MPI.MAX))
    total = int(np.sum(pairs))
    return {
        "status": "measured",
        "metric_space": "F_owned_CSR_nonzero_count",
        "rows_global": int(global_rows),
        "nnz_global": total,
        "nnz_total": total,
        "layer_count": layer_count,
        "rows_by_layer": [int(value) for value in rows],
        "nnz_by_layer": [int(value) for value in nnz],
        "layer_pair_nnz": pairs.tolist(),
        "same_layer_nnz": int(classes[0]),
        "adjacent_layer_nnz": int(classes[1]),
        "long_range_nnz": int(classes[2]),
        "same_layer_fraction": float(classes[0] / total) if total else None,
        "adjacent_layer_fraction": float(classes[1] / total) if total else None,
        "long_range_fraction": float(classes[2] / total) if total else None,
        "block_half_bandwidth": bandwidth,
    }


def _v6_layer_graph_audit(matrix: PETSc.Mat, system: Any) -> dict[str, Any]:
    """Audit F using assembly-time owned-cell/trace ownership metadata.

    A trace row shared by multiple cells is assigned to the smallest incident
    z-layer index.  This is a deterministic bookkeeping rule, not a physical
    claim; ``owned_cell_recovery_maps`` and
    ``trace_constraints.expansion_by_original`` plus cell geometry provide the
    mapping.
    """

    global_layers, mapping_metadata = build_real_layer_labels(matrix, system)
    global_rows = int(matrix.getSize()[0])
    comm = matrix.getComm().tompi4py()
    row_start, row_end = map(int, matrix.getOwnershipRange())
    row_ptr, columns, _values = matrix.getValuesCSR()
    local_layers = global_layers[row_start:row_end]
    audit = _v6_layer_graph_from_csr(
        row_ptr,
        columns,
        local_layers,
        global_layers,
        layer_count=len(mapping_metadata["z_layer_boundaries"]) - 1,
    )
    reduced = _v6_reduce_layer_graph(audit, comm, global_rows=global_rows)
    audit.update(
        {
            **reduced,
            **mapping_metadata,
            "temporary_global_row_layer_tags_released": True,
        }
    )
    del global_layers, row_ptr, columns, _values
    return audit


def _destroy_v5_side_components(
    side: Any,
    *,
    retain_d: bool = False,
) -> dict[str, bool]:
    released: dict[str, bool] = {}
    for name in ("H", "C", "F"):
        matrix = getattr(side, name, None)
        released[name] = matrix is None
        if matrix is not None:
            matrix.destroy()
            setattr(side, name, None)
            released[name] = True
    matrix = getattr(side, "D", None)
    released["D"] = matrix is None
    if not retain_d and matrix is not None:
        matrix.destroy()
        setattr(side, "D", None)
        released["D"] = True
    released["D_retained"] = bool(retain_d and matrix is not None)
    return released


def _v5_blr_rhs_vector(
    spec: tuple[str, str, int | None],
    system: Any,
    coupling_side: Any,
    components: Any,
) -> tuple[PETSc.Vec, dict[str, Any]]:
    label, kind, seed = spec
    if kind == "system_rhs":
        vector = components.F.createVecLeft()
        system.b.copy(vector)
        metadata = {"source": "system.b"}
    elif kind == "random":
        vector = components.F.createVecRight()
        first, last = (int(value) for value in vector.getOwnershipRange())
        indices = np.arange(first, last, dtype=np.float64)
        vector.getArray()[:] = np.asarray(
            np.sin(indices * 0.001 + int(seed))
            + 1j * np.cos(indices * 0.0007 - int(seed)),
            dtype=PETSc.ScalarType,
        )
        vector.assemble()
        metadata = {"source": "fixed_owner_range_formula", "seed": int(seed)}
    else:
        matrix = components.C if kind == "C" else getattr(coupling_side, kind)
        ncols = int(matrix.getSize()[1])
        column = int(seed) % ncols
        basis = matrix.createVecRight()
        vector = matrix.createVecLeft()
        basis.set(0.0)
        first, last = (int(value) for value in basis.getOwnershipRange())
        if first <= column < last:
            basis.getArray()[column - first] = PETSc.ScalarType(1.0)
        basis.assemble()
        matrix.mult(basis, vector)
        basis.destroy()
        metadata = {
            "source": kind,
            "seed": int(seed),
            "resolved_column": column,
            "column_count": ncols,
        }
    metadata.update(
        {
            "label": label,
            "identity": _side_vector_identity(vector, metadata["source"]),
            "degenerate_uninformative": bool(float(vector.norm()) <= 1.0e-30),
        }
    )
    return vector, metadata


def _v5_blr_prefreeze_external_rhs(
    spec: tuple[str, str, int | None],
    system: Any,
    components: Any,
) -> tuple[PETSc.Vec, dict[str, Any]]:
    """Freeze the one C-column probe before the action takes C ownership."""

    if spec[1] != "C":
        raise ValueError("Only the external DtN probe may be pre-frozen")
    if getattr(components, "C", None) is None:
        raise RuntimeError(
            "External DtN probe requires components.C before action creation"
        )
    vector, metadata = _v5_blr_rhs_vector(spec, system, components, components)
    metadata = dict(metadata)
    metadata["kind"] = spec[1]
    metadata["source"] = "pre_action_components.C"
    metadata["prefrozen_before_action_ownership_transfer"] = True
    metadata["identity"] = _side_vector_identity(vector, metadata["source"])
    return vector, metadata


def _v5_blr_true_residual(
    system: Any,
    rhs: PETSc.Vec,
    solution: PETSc.Vec,
) -> float | None:
    applied = system.A.createVecLeft()
    try:
        system.A.mult(solution, applied)
        applied.axpy(PETSc.ScalarType(-1.0), rhs)
        return float(applied.norm()) / max(float(rhs.norm()), 1.0e-30)
    finally:
        applied.destroy()


def _v5_blr_probe(
    action: Any,
    system: Any,
    rhs: PETSc.Vec,
    metadata: Mapping[str, Any],
    reference_vector: PETSc.Vec | None = None,
    *,
    repeat: bool = False,
    linearity: bool = False,
    retain_output: bool = False,
) -> tuple[dict[str, Any], PETSc.Vec | None]:
    target = action.operator.createVecLeft()
    repeat_target = action.operator.createVecLeft() if repeat else None
    scaled = rhs.duplicate()
    scaled_target = action.operator.createVecLeft() if linearity else None
    expected = target.duplicate() if linearity else None
    try:
        action.apply(rhs, target)
        if repeat_target is not None:
            action.apply(rhs, repeat_target)
        if scaled_target is not None:
            rhs.copy(scaled)
            scaled.scale(PETSc.ScalarType(2.0))
            action.apply(scaled, scaled_target)
            target.copy(expected)
            expected.scale(PETSc.ScalarType(2.0))
        repeat_error = (
            None if repeat_target is None else _relative_error(repeat_target, target)
        )
        linearity_error = (
            None if scaled_target is None else _relative_error(scaled_target, expected)
        )
        residual = _v5_blr_true_residual(system, rhs, target)
        reference_error = (
            None
            if reference_vector is None
            else _relative_error(target, reference_vector)
        )
        local_values = np.asarray(target.getArray(readonly=True), dtype=np.complex128)
        comm = target.getComm().tompi4py()
        finite = bool(
            comm.allreduce(
                bool(
                    np.isfinite(local_values).all()
                    and (repeat_error is None or np.isfinite(repeat_error))
                    and (linearity_error is None or np.isfinite(linearity_error))
                    and (residual is None or np.isfinite(residual))
                    and (reference_error is None or np.isfinite(reference_error))
                ),
                op=MPI.LAND,
            )
        )
        retained = target.duplicate() if retain_output else None
        if retained is not None:
            target.copy(retained)
        return (
            {
                **dict(metadata),
                "output": _side_vector_identity(target, "action_output"),
                "reference_relative_error": reference_error,
                "true_residual_relative": residual,
                "repeat_relative_error": repeat_error,
                "linearity_relative_error": linearity_error,
                "finite": finite,
            },
            retained,
        )
    finally:
        if expected is not None:
            expected.destroy()
        if scaled_target is not None:
            scaled_target.destroy()
        scaled.destroy()
        if repeat_target is not None:
            repeat_target.destroy()
        target.destroy()


def _v5_blr_destroy_side(
    action: Any, components: Any, comm: MPI.Intracomm
) -> dict[str, Any]:
    action.destroy()
    diagnostics = action.diagnostics
    released = _destroy_v5_side_components(components)
    cleanup = collective_heap_cleanup(comm)
    return {
        "action": diagnostics,
        "components": released,
        "collective_cleanup": cleanup,
        "factor_count_after_cleanup": {
            "exact": int(diagnostics.get("exact_factor_count", 0)),
            "compressed": int(diagnostics.get("compressed_factor_count", 0)),
            "global": int(diagnostics.get("global_direct_factor_count", 0)),
        },
    }


def run_v5_h4_mumps_blr_side_component(
    setup: Any,
    *,
    comm: MPI.Intracomm,
    marker_callback: Callable[[str, Mapping[str, Any]], None],
    run_directory: str | Path,
    source_identity: Mapping[str, Any],
    compressed_factor_profile: str = MUMPS_BLR_V5_H4_PROFILE,
) -> dict[str, Any]:
    """Run the fixed research-only exact-reference/BLR side component."""

    compressed_factor_profile = _validate_v5_h4_blr_profile(compressed_factor_profile)
    side_reports: dict[str, Any] = {}
    all_reports: list[dict[str, Any]] = []
    contract = {
        "profile": V5_H4_BLR_SIDE_PROFILE_ID,
        "mumps_blr_profile": compressed_factor_profile,
        "mumps_controls": mumps_blr_v5_h4_controls(compressed_factor_profile),
        "streaming_batch_size": 8,
        "rhs_specs": [
            {"label": label, "kind": kind, "seed": seed}
            for label, kind, seed in V5_H4_BLR_RHS_SPECS
        ],
    }
    contract["sha256"] = hashlib.sha256(
        json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    reference_root = Path(run_directory).resolve() / "numerical_output"
    for side, system in (("bottom", setup.bottom), ("top", setup.top)):
        coupling_side = getattr(setup.coupling, side)
        _emit_marker(marker_callback, f"v5_blr_exact_reference_{side}_begin")
        exact_components = None
        exact_action = None
        prefrozen_external_rhs = None
        exact_probe_reports: list[dict[str, Any]] = []
        exact_artifacts: dict[str, dict[str, Any]] = {}
        exact_diagnostics: dict[str, Any] = {}
        exact_cleanup: dict[str, Any] = {}
        try:
            exact_components = _build_research_explicit_side_components(system)
            prefrozen_external_rhs = _v5_blr_prefreeze_external_rhs(
                V5_H4_BLR_RHS_SPECS[3], system, exact_components
            )
            exact_action = create_research_exact_side_lu_action(
                exact_components.F,
                exact_components,
                qualification_scope=V5_H4_BLR_SIDE_PROFILE_ID,
                explicit_opt_in=True,
                factor_only_storage=True,
                streaming_w_batch_size=8,
            )
            exact_diagnostics = exact_action.diagnostics
            _emit_marker(
                marker_callback,
                f"v5_blr_exact_reference_{side}_ready",
                diagnostics=exact_diagnostics,
            )
            for spec in V5_H4_BLR_RHS_SPECS:
                if spec[1] == "C":
                    if prefrozen_external_rhs is None:
                        raise RuntimeError("External DtN probe was not pre-frozen")
                    rhs, metadata = prefrozen_external_rhs
                    prefrozen_external_rhs = None
                else:
                    rhs, metadata = _v5_blr_rhs_vector(
                        spec, system, coupling_side, exact_components
                    )
                retained = None
                try:
                    report, retained = _v5_blr_probe(
                        exact_action,
                        system,
                        rhs,
                        metadata,
                        retain_output=True,
                    )
                    if retained is None:
                        raise RuntimeError("Exact reference output was not retained")
                    rhs_artifact = _write_v5_blr_reference_spool(
                        reference_root,
                        side,
                        report["label"],
                        rhs,
                        "rhs",
                        {
                            "artifact_role": "rhs",
                            "probe_metadata": metadata,
                            "vector_identity": metadata["identity"],
                            "packet_identity": source_identity,
                        },
                    )
                    output_artifact = _write_v5_blr_reference_spool(
                        reference_root,
                        side,
                        report["label"],
                        retained,
                        "exact_output",
                        {
                            "artifact_role": "exact_output",
                            "probe_metadata": {"label": report["label"]},
                            "vector_identity": report["output"],
                            "packet_identity": source_identity,
                        },
                    )
                    artifact = {"rhs": rhs_artifact, "exact_output": output_artifact}
                    report["reference_artifact"] = artifact
                    exact_artifacts[report["label"]] = artifact
                    exact_probe_reports.append(report)
                finally:
                    rhs.destroy()
                    if retained is not None:
                        retained.destroy()
            released = _destroy_v5_side_components(exact_components, retain_d=True)
            if all(released[name] for name in ("F", "C", "H")):
                exact_action.woodbury.mark_borrowed_matrices_released()
            exact_diagnostics = exact_action.diagnostics
            _emit_marker(
                marker_callback,
                f"v5_blr_exact_reference_{side}_components_cleanup",
                released=released,
                cleanup=collective_heap_cleanup(comm),
            )
        finally:
            if prefrozen_external_rhs is not None:
                prefrozen_external_rhs[0].destroy()
            if exact_action is not None:
                exact_cleanup = _v5_blr_destroy_side(
                    exact_action, exact_components, comm
                )
            elif exact_components is not None:
                exact_cleanup = {
                    "status": "not_created",
                    "components": _destroy_v5_side_components(exact_components),
                    "collective_cleanup": collective_heap_cleanup(comm),
                }
            exact_diagnostics = exact_cleanup.get("action", exact_diagnostics)
            _emit_marker(
                marker_callback,
                f"v5_blr_exact_reference_{side}_cleanup",
                cleanup=exact_cleanup,
            )

        exact_factor_counts = exact_cleanup.get("factor_count_after_cleanup")
        if not isinstance(exact_factor_counts, Mapping) or any(
            exact_factor_counts.get(name) != 0
            for name in ("exact", "compressed", "global")
        ):
            raise RuntimeError(
                f"Exact {side} reference cleanup did not release all factors"
            )

        _emit_marker(
            marker_callback,
            f"v5_blr_candidate_{side}_setup_begin",
            candidate_online_exact_factor_count=0,
            candidate_online_compressed_factor_count=0,
            expected_profile=compressed_factor_profile,
            reference_outputs_retained=False,
            reference_artifact_count=len(exact_artifacts),
            reference_artifact_root=str(reference_root / "v5_blr_reference_spool"),
        )
        components = _build_research_explicit_side_components(system)
        action = None
        candidate_reports: list[dict[str, Any]] = []
        candidate_diagnostics: dict[str, Any] = {}
        candidate_setup_diagnostics: dict[str, Any] = {}
        candidate_cleanup: dict[str, Any] = {}
        try:

            def lifecycle(event: str, detail: Mapping[str, Any]) -> None:
                _emit_marker(
                    marker_callback,
                    f"v5_blr_candidate_{side}_{event}",
                    **dict(detail),
                )

            action = create_research_exact_side_lu_action(
                components.F,
                components,
                qualification_scope=V5_H4_BLR_SIDE_PROFILE_ID,
                explicit_opt_in=True,
                factor_only_storage=True,
                compressed_factor_profile=compressed_factor_profile,
                streaming_w_batch_size=8,
                lifecycle_callback=lifecycle,
            )
            candidate_setup_diagnostics = action.diagnostics
            _emit_marker(
                marker_callback,
                f"v5_blr_candidate_{side}_ready",
                diagnostics=candidate_setup_diagnostics,
                candidate_online_factor_identity={
                    "exact": 0,
                    "compressed": 1,
                    "direct": 1,
                    "global": 0,
                },
            )
            released = _destroy_v5_side_components(components, retain_d=True)
            if all(released[name] for name in ("F", "C", "H")):
                action.woodbury.mark_borrowed_matrices_released()
            candidate_diagnostics = action.diagnostics
            _emit_marker(
                marker_callback,
                f"v5_blr_candidate_{side}_setup_end",
                released=released,
                cleanup=collective_heap_cleanup(comm),
                action_diagnostics=candidate_diagnostics,
                candidate_process_tree_peak_gib={
                    "status": "pending_parent_resource_gate",
                    "value": None,
                    "limit": V5_H4_BLR_SIDE_SETUP_PEAK_LIMIT_GIB,
                },
            )
            for spec in V5_H4_BLR_RHS_SPECS:
                label = spec[0]
                artifacts = exact_artifacts[label]
                template = None
                rhs = None
                reference = None
                try:
                    template = action.operator.createVecLeft()
                    rhs = _load_v5_blr_reference_spool(artifacts["rhs"], template)
                    reference = _load_v5_blr_reference_spool(
                        artifacts["exact_output"], template
                    )
                    metadata = dict(
                        artifacts["rhs"]["source_identity"]["probe_metadata"]
                    )
                    report, _retained = _v5_blr_probe(
                        action,
                        system,
                        rhs,
                        metadata,
                        reference,
                        repeat=True,
                        linearity=metadata["label"] == "fixed_random_repeat_0",
                    )
                    report["reference_artifact"] = artifacts
                    candidate_reports.append(report)
                    all_reports.append(report)
                finally:
                    if template is not None:
                        template.destroy()
                    if rhs is not None:
                        rhs.destroy()
                    if reference is not None:
                        reference.destroy()
        finally:
            if action is not None:
                candidate_cleanup = _v5_blr_destroy_side(action, components, comm)
                candidate_diagnostics = candidate_cleanup.get(
                    "action", candidate_diagnostics
                )
            else:
                candidate_cleanup = {
                    "status": "not_created",
                    "components": _destroy_v5_side_components(components),
                    "collective_cleanup": collective_heap_cleanup(comm),
                }
            _emit_marker(
                marker_callback,
                f"v5_blr_candidate_{side}_cleanup",
                cleanup=candidate_cleanup,
            )
        side_reports[side] = {
            "exact": {
                "probes": exact_probe_reports,
                "diagnostics": exact_diagnostics,
                "cleanup": exact_cleanup,
                "reference_artifacts": exact_artifacts,
            },
            "candidate": {
                "probes": candidate_reports,
                "diagnostics": candidate_diagnostics,
                "setup_diagnostics": candidate_setup_diagnostics,
                "cleanup": candidate_cleanup,
            },
        }
    if any(
        report["degenerate_uninformative"]
        for report in all_reports
        if report["label"] != "physical_side_rhs"
    ):
        raise RuntimeError("Mandatory BLR side probe is degenerate")
    mandatory_reports = [
        report for report in all_reports if not report["degenerate_uninformative"]
    ]
    finite_reports = mandatory_reports
    if any(report["true_residual_relative"] is None for report in finite_reports):
        raise RuntimeError("Mandatory BLR side probe has no true residual")
    residuals = [report["true_residual_relative"] for report in finite_reports]
    repeats = [
        report["repeat_relative_error"]
        for report in finite_reports
        if report["repeat_relative_error"] is not None
    ]
    linearity = [
        report["linearity_relative_error"]
        for report in finite_reports
        if report["linearity_relative_error"] is not None
    ]
    reference_errors = [
        report["reference_relative_error"]
        for report in finite_reports
        if report["reference_relative_error"] is not None
    ]
    finite_pass = bool(all(report["finite"] for report in all_reports))
    true_residual_pass = bool(
        mandatory_reports
        and all(
            report["true_residual_relative"] is not None
            and report["true_residual_relative"] <= 1.0e-2
            for report in mandatory_reports
        )
    )
    repeat_pass = bool(
        mandatory_reports
        and all(
            report["repeat_relative_error"] is not None
            and report["repeat_relative_error"] <= 1.0e-10
            for report in mandatory_reports
        )
    )
    linearity_reports = [
        report
        for report in mandatory_reports
        if report["label"] == "fixed_random_repeat_0"
    ]
    linearity_pass = bool(
        linearity_reports
        and all(
            report["linearity_relative_error"] is not None
            and report["linearity_relative_error"] <= 1.0e-10
            for report in linearity_reports
        )
    )
    factor_identity_pass = all(
        report["candidate"].get("setup_diagnostics", {}).get("exact_factor_count") == 0
        and report["candidate"]
        .get("setup_diagnostics", {})
        .get("compressed_factor_count")
        == 1
        and report["candidate"].get("setup_diagnostics", {}).get("direct_factor_count")
        == 1
        and report["candidate"]
        .get("setup_diagnostics", {})
        .get("global_direct_factor_count", 0)
        == 0
        and report["candidate"]
        .get("setup_diagnostics", {})
        .get("mumps_controls_verified")
        is True
        for report in side_reports.values()
    )
    factor_cleanup_pass = all(
        all(
            value == 0
            for value in report["candidate"]["cleanup"]
            .get("factor_count_after_cleanup", {})
            .values()
        )
        for report in side_reports.values()
    )
    numerical_components_pass = bool(
        finite_pass
        and true_residual_pass
        and repeat_pass
        and linearity_pass
        and factor_identity_pass
        and factor_cleanup_pass
    )
    return {
        "schema": "task039.v5-h4-mumps-blr-side-component.v1",
        "status": "component_completed",
        "component_candidate": True,
        "research_only": True,
        "general_production": False,
        "profile": V5_H4_BLR_SIDE_PROFILE_ID,
        "mumps_blr_profile": compressed_factor_profile,
        "mumps_controls": mumps_blr_v5_h4_controls(compressed_factor_profile),
        "packet_identity": _json_safe(source_identity.get("packet_identity")),
        "packet_manifest_sha256": source_identity.get("manifest_sha256"),
        "rhs_contract": contract,
        "sides": side_reports,
        "gates": {
            "finite": finite_pass,
            "finite_pass": finite_pass,
            "reference_relative_error_max": max(reference_errors, default=None),
            "true_residual_relative_max": max(residuals, default=None),
            "true_residual_relative_limit": 1.0e-2,
            "true_residual_pass": true_residual_pass,
            "repeat_relative_error_max": max(repeats, default=None),
            "repeat_relative_error_limit": 1.0e-10,
            "repeat_pass": repeat_pass,
            "linearity_relative_error_max": max(linearity, default=None),
            "linearity_relative_error_limit": 1.0e-10,
            "linearity_pass": linearity_pass,
            "factor_identity_pass": factor_identity_pass,
            "factor_cleanup_pass": factor_cleanup_pass,
            "numerical_components_pass": numerical_components_pass,
            "numerical_pass": numerical_components_pass,
            "resource_pass": None,
            "advancement_pass": None,
            "candidate_side_setup_peak": {
                "status": "pending_parent_resource_gate",
                "value": None,
                "limit": V5_H4_BLR_SIDE_SETUP_PEAK_LIMIT_GIB,
                "pass": None,
            },
            "candidate_online_exact_factor_count": 0,
            "candidate_online_compressed_factor_count": 1,
            "candidate_online_global_direct_factor_count": 0,
            "cleanup_factor_counts": {
                side: report["candidate"]["cleanup"]["factor_count_after_cleanup"]
                for side, report in side_reports.items()
            },
            "resource_gate_pending": True,
            "resource_authority": "parent_task038_closed_marker_interval",
        },
        "setup": "side_component_only",
        "outer": "not_run",
        "recovery": "not_run",
        "field": "not_run",
        "RTA": "not_run",
        "qualification": "not_run",
        "telemetry": {
            "process_tree_samples": {
                "path": "numerical_output/process_tree_samples.jsonl",
                "writer": "parent_task038_launcher",
                "status": "expected_from_parent_launcher",
            },
            "memory_stages": {
                "path": "numerical_output/memory_stages.jsonl",
                "writer": "parent_task038_launcher_marker_alignment",
                "status": "expected_from_parent_launcher",
            },
            "memory_stage_markers": {
                "path": "numerical_output/memory_stage_markers.raw.jsonl",
                "writer": "v3_7_worker",
                "status": "measured_worker_marker_stream",
            },
            "memory_object_ledger": {
                "path": "numerical_output/memory_object_ledger.json",
                "status": "finalized_in_worker_finalizer",
            },
        },
    }


def run_v5_h4_fixed_budget_bottom_component(
    setup: Any,
    *,
    comm: MPI.Intracomm,
    marker_callback: Callable[[str, Mapping[str, Any]], None],
    exact_spool_root: str | Path,
    packet_identity: Mapping[str, Any],
    packet_manifest_sha256: str,
) -> dict[str, Any]:
    """Run the single frozen bottom-side fixed-budget research component."""

    spool = _load_v5_fixed_budget_spool_shards(
        exact_spool_root,
        comm,
        packet_identity=packet_identity,
        manifest_sha256=packet_manifest_sha256,
    )
    system = setup.bottom
    components = None
    base_action = None
    fixed_action = None
    krylov_action = None
    candidate_setup: dict[str, Any] = {}
    candidate_reports: list[dict[str, Any]] = []
    cleanup: dict[str, Any] = {}
    component_inventory = getattr(system, "inventory", None)
    if not isinstance(component_inventory, Mapping):
        raise RuntimeError("Fixed-budget route requires side inventory")
    if component_inventory.get("global_F_materialized") is not False:
        raise RuntimeError("Fixed-budget route requires matrix-free side inventory")
    _emit_marker(
        marker_callback,
        "v5_fixed_budget_reference_spool_validated",
        side="bottom",
        labels=list(spool),
        exact_factor_count=0,
        global_direct_factor_count=0,
    )
    _emit_marker(
        marker_callback,
        "v5_fixed_budget_candidate_bottom_setup_begin",
        fixed_budget=V5_H4_FIXED_BUDGET,
        exact_factor_count=0,
        global_direct_factor_count=0,
        candidate_online_factor_count_initial=0,
        reference_outputs_retained=False,
    )
    try:
        components = create_hybrid_local_dtn_action_components(system)
        base_action = build_hybrid_whole_endcap_fixed_smoother_action(
            system, ilu_levels=0
        )
        _emit_marker(
            marker_callback,
            "v5_fixed_budget_candidate_bottom_base_ready",
            diagnostics=base_action.diagnostics,
            exact_factor_count=0,
            global_direct_factor_count=0,
        )
        fixed_action = HybridLocalDtnWoodburyFixedAction(
            base_action,
            components,
            base_identity="whole_endcap_ilu0_woodbury_fixed_action",
            ilu_levels=0,
        )
        _emit_marker(
            marker_callback,
            "v5_fixed_budget_candidate_bottom_woodbury_ready",
            diagnostics=fixed_action.diagnostics,
            exact_factor_count=0,
            global_direct_factor_count=0,
        )
        krylov_action = HybridLocalDtnWoodburyFixedBudgetKrylovAction(
            system.A,
            fixed_action,
            budget=V5_H4_FIXED_BUDGET,
        )
        candidate_setup = {
            "fixed_budget": V5_H4_FIXED_BUDGET,
            "ksp": krylov_action.diagnostics,
            "woodbury": fixed_action.diagnostics,
            "base": base_action.diagnostics,
            "exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "base_factor_count": int(fixed_action.diagnostics["base_factor_count"]),
            "inventory": {
                **_json_safe(dict(component_inventory)),
                "global_F_materialized": False,
                "no_new_explicit_component_matrix": True,
            },
        }
        _emit_marker(
            marker_callback,
            "v5_fixed_budget_candidate_bottom_fixed_budget_ready",
            diagnostics=candidate_setup,
        )
        _emit_marker(
            marker_callback,
            "v5_fixed_budget_candidate_bottom_setup_end",
            diagnostics=candidate_setup,
            fixed_budget=V5_H4_FIXED_BUDGET,
            resource_gate="pending_parent_closed_interval",
        )
        _emit_marker(
            marker_callback,
            "v5_fixed_budget_candidate_bottom_online_begin",
            fixed_budget=V5_H4_FIXED_BUDGET,
            resource_gate="evidence_only_not_advancement_gate",
        )
        for label, artifact in spool.items():
            _emit_marker(
                marker_callback,
                f"v5_fixed_budget_probe_{label}_begin",
                side="bottom",
                fixed_budget=V5_H4_FIXED_BUDGET,
            )
            template = rhs = reference = None
            try:
                template = system.A.createVecLeft()
                rhs = _load_v5_blr_reference_spool_remapped(artifact["rhs"], template)
                reference = _load_v5_blr_reference_spool_remapped(
                    artifact["exact_output"], template
                )
                metadata = dict(artifact["rhs"]["probe_metadata"])
                report, _ = _v5_blr_probe(
                    krylov_action,
                    system,
                    rhs,
                    metadata,
                    reference,
                    repeat=True,
                    linearity=label == "fixed_random_repeat_0",
                )
                report["reference_artifact"] = {
                    "rhs": artifact["rhs"],
                    "exact_output": artifact["exact_output"],
                }
                candidate_reports.append(report)
                _emit_marker(
                    marker_callback,
                    f"v5_fixed_budget_probe_{label}_end",
                    report=report,
                    action_diagnostics=krylov_action.diagnostics,
                )
            finally:
                if template is not None:
                    template.destroy()
                if rhs is not None:
                    rhs.destroy()
                if reference is not None:
                    reference.destroy()
        _emit_marker(
            marker_callback,
            "v5_fixed_budget_candidate_bottom_online_end",
            fixed_budget=V5_H4_FIXED_BUDGET,
            probe_count=len(candidate_reports),
            resource_gate="evidence_only_not_advancement_gate",
        )
    finally:
        if krylov_action is not None:
            krylov_action.destroy()
        krylov_diagnostics = (
            None if krylov_action is None else krylov_action.diagnostics
        )
        if fixed_action is not None:
            fixed_action.destroy()
        fixed_diagnostics = None if fixed_action is None else fixed_action.diagnostics
        if base_action is not None:
            base_action.destroy()
        base_diagnostics = None if base_action is None else base_action.diagnostics
        if components is not None:
            components.destroy()
            component_release = {
                "carrier_destroyed": bool(getattr(components, "_destroyed", False)),
                "scratch_released": bool(getattr(components, "_destroyed", False)),
                "borrowed_matrices_destroyed": False,
                "borrowed_matrices_retained_by_setup": {
                    name: True for name in ("F", "C", "D", "H")
                },
                "global_F_materialized": False,
                "no_new_explicit_component_matrix": True,
            }
        else:
            component_release = {
                "carrier_destroyed": False,
                "scratch_released": False,
                "borrowed_matrices_destroyed": False,
                "borrowed_matrices_retained_by_setup": {
                    name: False for name in ("F", "C", "D", "H")
                },
                "global_F_materialized": False,
                "no_new_explicit_component_matrix": True,
            }
        collective_cleanup = collective_heap_cleanup(comm)
        cleanup = {
            "ksp": krylov_diagnostics,
            "woodbury": fixed_diagnostics,
            "base": base_diagnostics,
            "components": component_release,
            "collective_cleanup": collective_cleanup,
            "factor_count_after_cleanup": {
                "exact": 0,
                "global": 0,
                "base": (
                    None
                    if not isinstance(
                        (base_diagnostics or {}).get("lifecycle"), Mapping
                    )
                    else (base_diagnostics or {})["lifecycle"].get(
                        "factor_count_after_destroy"
                    )
                ),
            },
        }
        _emit_marker(
            marker_callback,
            "v5_fixed_budget_candidate_bottom_cleanup",
            cleanup=cleanup,
            exact_factor_count=0,
            global_direct_factor_count=0,
        )

    if any(
        not isinstance(report.get("degenerate_uninformative"), bool)
        for report in candidate_reports
    ):
        raise RuntimeError(
            "Fixed-budget probe metadata missing degenerate_uninformative"
        )
    degenerate_labels = [
        report["label"]
        for report in candidate_reports
        if report["degenerate_uninformative"] is True
    ]
    mandatory_labels = [
        report["label"]
        for report in candidate_reports
        if report["degenerate_uninformative"] is False
    ]
    mandatory = [
        report
        for report in candidate_reports
        if report["degenerate_uninformative"] is False
    ]
    finite_pass = bool(
        len(candidate_reports) == len(V5_H4_BLR_RHS_SPECS)
        and all(report.get("finite") is True for report in candidate_reports)
    )
    true_residual_pass = bool(
        mandatory
        and all(
            report.get("true_residual_relative") is not None
            and report["true_residual_relative"] <= 1.0e-2
            for report in mandatory
        )
    )
    repeat_pass = bool(
        mandatory
        and all(
            report.get("repeat_relative_error") is not None
            and report["repeat_relative_error"] <= 1.0e-10
            for report in mandatory
        )
    )
    random_linearity = [
        report for report in mandatory if report["label"] == "fixed_random_repeat_0"
    ]
    linearity_pass = bool(
        random_linearity
        and all(
            report.get("linearity_relative_error") is not None
            and report["linearity_relative_error"] <= 1.0e-10
            for report in random_linearity
        )
    )
    setup_ksp = candidate_setup.get("ksp", {})
    factor_identity_pass = bool(
        candidate_setup.get("fixed_budget") == V5_H4_FIXED_BUDGET
        and candidate_setup.get("exact_factor_count") == 0
        and candidate_setup.get("global_direct_factor_count") == 0
        and setup_ksp.get("direct_factor_count") == 0
        and setup_ksp.get("global_hybrid_direct_factor_count") == 0
        and candidate_setup.get("base_factor_count") == 1
    )
    factor_cleanup_pass = bool(
        cleanup.get("factor_count_after_cleanup", {}).get("exact") == 0
        and cleanup.get("factor_count_after_cleanup", {}).get("global") == 0
        and cleanup.get("factor_count_after_cleanup", {}).get("base") == 0
        and cleanup.get("components", {}).get("carrier_destroyed") is True
        and cleanup.get("components", {}).get("scratch_released") is True
        and cleanup.get("components", {}).get("borrowed_matrices_destroyed") is False
        and all(
            cleanup.get("components", {})
            .get("borrowed_matrices_retained_by_setup", {})
            .get(name)
            is True
            for name in ("F", "C", "D", "H")
        )
    )
    numerical_components_pass = bool(
        finite_pass
        and true_residual_pass
        and repeat_pass
        and factor_identity_pass
        and factor_cleanup_pass
    )
    return {
        "schema": "task039.v5-h4-fixed-budget-bottom-component.v1",
        "status": "component_completed",
        "component_candidate": True,
        "research_only": True,
        "general_production": False,
        "profile": V5_H4_FIXED_BUDGET_SIDE_PROFILE_ID,
        "fixed_budget": V5_H4_FIXED_BUDGET,
        "packet_identity": _json_safe(packet_identity),
        "packet_manifest_sha256": packet_manifest_sha256,
        "component_inventory": candidate_setup.get("inventory"),
        "exact_spool_root": str(Path(exact_spool_root).resolve()),
        "mandatory_labels": mandatory_labels,
        "degenerate_labels": degenerate_labels,
        "rhs_contract": [
            {"label": label, "kind": kind, "seed": seed}
            for label, kind, seed in V5_H4_BLR_RHS_SPECS
        ],
        "sides": {
            "bottom": {
                "candidate": {
                    "probes": candidate_reports,
                    "setup": candidate_setup,
                    "cleanup": cleanup,
                }
            },
            "top": "not_run_by_bottom_first_contract",
        },
        "gates": {
            "finite_pass": finite_pass,
            "true_residual_pass": true_residual_pass,
            "true_residual_limit": 1.0e-2,
            "repeat_pass": repeat_pass,
            "repeat_limit": 1.0e-10,
            "linearity_pass": linearity_pass,
            "linearity_gate": (
                "not_applicable_diagnostic_only; future outer must use FGMRES"
            ),
            "linearity_limit": 1.0e-10,
            "factor_identity_pass": factor_identity_pass,
            "factor_cleanup_pass": factor_cleanup_pass,
            "numerical_components_pass": numerical_components_pass,
            "numerical_pass": numerical_components_pass,
            "resource_pass": None,
            "advancement_pass": None,
            "candidate_side_setup_peak": {
                "status": "pending_parent_resource_gate",
                "value": None,
                "limit": V5_H4_BLR_SIDE_SETUP_PEAK_LIMIT_GIB,
                "pass": None,
            },
            "resource_gate_pending": True,
            "resource_authority": "parent_task038_closed_marker_interval",
        },
        "setup": "bottom_side_component_only",
        "outer": "not_run",
        "recovery": "not_run",
        "field": "not_run",
        "RTA": "not_run",
        "qualification": "not_run",
        "telemetry": {
            "process_tree_samples": {
                "path": "numerical_output/process_tree_samples.jsonl",
                "status": "expected_from_parent_launcher",
            },
            "memory_stages": {
                "path": "numerical_output/memory_stages.jsonl",
                "status": "expected_from_parent_launcher",
            },
            "memory_stage_markers": {
                "path": "numerical_output/memory_stage_markers.raw.jsonl",
                "status": "measured_worker_marker_stream",
            },
            "memory_object_ledger": {
                "path": "numerical_output/memory_object_ledger.json",
                "status": "finalized_in_worker_finalizer",
            },
        },
    }


def run_v6_h4_port_modal_bottom_component(
    setup: Any,
    *,
    comm: MPI.Intracomm,
    marker_callback: Callable[[str, Mapping[str, Any]], None],
    exact_spool_root: str | Path,
    packet_manifest: str | Path,
    packet_identity: Mapping[str, Any],
    packet_manifest_sha256: str,
) -> dict[str, Any]:
    """Run the explicit bottom-only factor-free Petrov component."""

    if not getattr(setup, "side_only", False) or not hasattr(setup, "bottom"):
        raise ValueError("V6 port-modal route requires a bottom-only setup carrier")
    system = setup.bottom
    components = None
    base_action = None
    fixed_action = None
    owner = None
    packet_bundle = None
    modal_provider = None
    gradient_provider = None
    petrov_action = None
    z_basis = None
    y_basis = None
    spool = None
    z_columns: list[np.ndarray] = []
    y_columns: list[np.ndarray] = []
    checkpoints: list[dict[str, Any]] = []
    holdout_spool_loaded = False
    right_source_hash = hashlib.sha256()
    left_source_hash = hashlib.sha256()
    z_source_hash = hashlib.sha256()
    right_source_bytes = 0
    left_source_bytes = 0
    z_source_bytes = 0
    schedule = v6_port_modal_training_schedule(
        mode_count=480, external_count=296, source_count=512
    )
    schedule_sha256 = hashlib.sha256(
        json.dumps(schedule, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    def training_value_digest() -> list[dict[str, Any]]:
        row_first, row_last = (int(value) for value in system.A.getOwnershipRange())
        return comm.allgather(
            {
                "ownership_range": [row_first, row_last],
                "right_source_sha256": right_source_hash.hexdigest(),
                "left_source_sha256": left_source_hash.hexdigest(),
                "z_source_sha256": z_source_hash.hexdigest(),
                "right_source_bytes": int(right_source_bytes),
                "left_source_bytes": int(left_source_bytes),
                "z_source_bytes": int(z_source_bytes),
            }
        )

    def release_checkpoint() -> None:
        nonlocal petrov_action, z_basis, y_basis
        if petrov_action is not None:
            petrov_action.destroy()
            petrov_action = None
        z_basis = None
        y_basis = None

    _emit_marker(
        marker_callback,
        "v6_port_modal_bottom_construction_begin",
        profile=V6_H4_PORT_MODAL_BOTTOM_PROFILE_ID,
        construction_peak_limit_gib=V6_H4_PORT_MODAL_BOTTOM_CONSTRUCTION_LIMIT_GIB,
        retained_peak_limit_gib=V6_H4_PORT_MODAL_BOTTOM_RETAINED_LIMIT_GIB,
        exact_factor_count=0,
        global_direct_factor_count=0,
    )
    try:
        components = create_hybrid_local_dtn_action_components(system)
        base_action = build_hybrid_whole_endcap_fixed_smoother_action(
            system, ilu_levels=0
        )
        fixed_action = HybridLocalDtnWoodburyFixedAction(
            base_action,
            components,
            base_identity="whole_endcap_ilu0_woodbury_fixed_action",
            ilu_levels=0,
        )
        base_diagnostics = dict(fixed_action.diagnostics)
        woodbury_diagnostics = dict(base_diagnostics["woodbury"])
        woodbury_n_aux = int(woodbury_diagnostics["n_aux"])
        woodbury_aux_shape = [int(value) for value in components.H.getSize()]
        if woodbury_aux_shape != [woodbury_n_aux, woodbury_n_aux]:
            raise ValueError(
                "V6 Woodbury auxiliary shape disagrees with diagnostics n_aux"
            )
        base_diagnostics.update(
            {
                "fixed_linear": True,
                "nested_ksp": False,
                "woodbury_auxiliary_count": woodbury_n_aux,
                "woodbury_auxiliary_shape": woodbury_aux_shape,
            }
        )
        if (
            base_diagnostics.get("operator_identity")
            != "whole_endcap_ilu0_woodbury_fixed_action"
            or base_diagnostics.get("residual_correction_steps") != 1
            or base_diagnostics.get("local_direct_factor_count") != 0
            or base_diagnostics.get("global_hybrid_direct_factor_count") != 0
            or base_diagnostics.get("base_factor_count") != 1
        ):
            raise ValueError("V6 base action is not fixed ILU0 plus DtN Woodbury")
        _emit_marker(
            marker_callback,
            "v6_port_modal_bottom_fixed_woodbury_ready",
            diagnostics=base_diagnostics,
            nested_ksp=False,
            exact_factor_count=0,
            global_direct_factor_count=0,
            woodbury_auxiliary_count=woodbury_n_aux,
            woodbury_auxiliary_shape=woodbury_aux_shape,
            fixed_linear=True,
        )

        packet_bundle = consume_task039_v4_selected_mode_packet(
            Path(packet_manifest),
            identity=packet_identity,
            expected_manifest_sha256=packet_manifest_sha256,
            consumer_kind="iterative",
            comm=comm,
        )
        packet_diagnostics = dict(packet_bundle.packet_consumer_diagnostics)
        _emit_marker(
            marker_callback,
            "v6_port_modal_bottom_packet_full_ephemeral_ready",
            packet=packet_diagnostics,
            vectors_before_destroy=packet_diagnostics.get(
                "vector_count_before_destroy"
            ),
            full_ephemeral_hydration=True,
            left_vectors_hydrated=True,
        )
        cross_section = build_matching_cross_section(system.cfg, "stage4_xy")
        spaces = build_cross_section_spaces(
            cross_section, transverse_degree=int(system.cfg.nedelec_degree)
        )
        owner = build_single_hybrid_interface_mode_owner(
            system,
            spaces,
            packet_bundle.positive_basis,
            packet_bundle.negative_basis,
        )
        packet_bundle.destroy()
        packet_diagnostics = dict(packet_bundle.packet_consumer_diagnostics)
        packet_bundle = None
        _emit_marker(
            marker_callback,
            "v6_port_modal_bottom_packet_full_ephemeral_released",
            packet_vectors_released=(
                packet_diagnostics.get("vector_count_after_destroy") == 0
            ),
            packet_mmap_released=packet_diagnostics.get("packet_mmap_released"),
            vector_count_after_destroy=packet_diagnostics.get(
                "vector_count_after_destroy"
            ),
        )
        modal_provider = v6_single_interface_modal_provider(owner)
        gradient_provider = build_v6_discrete_gradient_source_provider(owner)
        _emit_marker(
            marker_callback,
            "v6_port_modal_bottom_source_owner_ready",
            owner_audit=owner.audit,
            system_operator_identity="system.A",
            global_F_materialized=system.inventory.get("global_F_materialized"),
            exact_factor_count=0,
            global_direct_factor_count=0,
        )

        for schedule_item in schedule:
            right_source = left_source = z_source = None
            try:
                right_source, _right_metadata = build_v6_factor_free_source_vector(
                    system,
                    components,
                    schedule_item,
                    role="right",
                    modal_provider=modal_provider,
                    near_null_provider=gradient_provider,
                )
                z_source = system.A.createVecLeft()
                fixed_action.apply(right_source, z_source)
                left_source, _left_metadata = build_v6_factor_free_source_vector(
                    system,
                    components,
                    schedule_item,
                    role="left",
                    modal_provider=modal_provider,
                    near_null_provider=gradient_provider,
                )
                right_values = np.ascontiguousarray(
                    right_source.getArray(readonly=True), dtype=np.complex128
                )
                left_values = np.ascontiguousarray(
                    left_source.getArray(readonly=True), dtype=np.complex128
                )
                z_values = np.ascontiguousarray(
                    z_source.getArray(readonly=True), dtype=np.complex128
                )
                z_columns.append(z_values.copy())
                y_columns.append(left_values.copy())
                right_source_hash.update(right_values.tobytes())
                left_source_hash.update(left_values.tobytes())
                z_source_hash.update(z_values.tobytes())
                right_source_bytes += int(right_values.nbytes)
                left_source_bytes += int(left_values.nbytes)
                z_source_bytes += int(z_values.nbytes)
            finally:
                if left_source is not None:
                    left_source.destroy()
                if z_source is not None:
                    z_source.destroy()
                if right_source is not None:
                    right_source.destroy()

            checkpoint = int(schedule_item["index"]) + 1
            if checkpoint not in V6_PORT_MODAL_CHECKPOINTS:
                continue
            z_candidates = np.column_stack(z_columns)
            y_candidates = np.column_stack(y_columns)
            z_basis, y_basis, basis_diagnostics = build_v6_owner_row_basis_checkpoint(
                z_candidates, y_candidates, checkpoint, comm=comm
            )
            _emit_marker(
                marker_callback,
                f"v6_port_modal_bottom_basis_sealed_{checkpoint}",
                checkpoint=checkpoint,
                schedule_sha256=schedule_sha256,
                training_value_digest=training_value_digest(),
                basis_diagnostics=basis_diagnostics,
                exact_spool_opened=False,
            )
            spool_loaded_this_checkpoint = False
            if spool is None:
                spool = _load_v5_fixed_budget_spool_shards(
                    exact_spool_root,
                    comm,
                    packet_identity=packet_identity,
                    manifest_sha256=packet_manifest_sha256,
                )
                holdout_spool_loaded = True
                spool_loaded_this_checkpoint = True
            petrov_action = FixedLinearOwnerRowPetrovCorrectionAction(
                fixed_action,
                system.A,
                z_basis,
                y_basis,
                factor_inventory={
                    "exact_factor_count": 0,
                    "global_direct_factor_count": 0,
                },
            )
            del z_candidates, y_candidates
            z_basis = None
            y_basis = None
            reports = []
            for label, artifact in spool.items():
                template = rhs = reference = None
                try:
                    template = system.A.createVecLeft()
                    rhs = _load_v5_blr_reference_spool_remapped(
                        artifact["rhs"], template
                    )
                    reference = _load_v5_blr_reference_spool_remapped(
                        artifact["exact_output"], template
                    )
                    report, _ = _v5_blr_probe(
                        petrov_action,
                        system,
                        rhs,
                        dict(artifact["rhs"]["probe_metadata"]),
                        reference,
                        repeat=True,
                        linearity=True,
                    )
                    reports.append(report)
                finally:
                    if reference is not None:
                        reference.destroy()
                    if rhs is not None:
                        rhs.destroy()
                    if template is not None:
                        template.destroy()
            checkpoint_record = {
                "checkpoint": checkpoint,
                "basis": basis_diagnostics,
                "petrov": petrov_action.diagnostics,
                "training_value_digest": training_value_digest(),
                "reports": reports,
                "gate": _v6_port_modal_holdout_gate(reports),
            }
            spool = None
            _emit_marker(
                marker_callback,
                "v6_port_modal_bottom_holdout_spool_released",
                checkpoint=checkpoint,
                descriptor_reference_released=True,
                arrays_retained=False,
            )
            checkpoints.append(checkpoint_record)
            _emit_marker(
                marker_callback,
                f"v6_port_modal_bottom_checkpoint_{checkpoint}_complete",
                checkpoint=checkpoint,
                gate=checkpoint_record["gate"],
                action_diagnostics=petrov_action.diagnostics,
                exact_spool_opened=spool_loaded_this_checkpoint,
            )
            if checkpoint_record["gate"]["pass"]:
                if gradient_provider is not None:
                    gradient_provider.destroy()
                    gradient_provider = None
                if owner is not None:
                    owner.destroy()
                    owner = None
                modal_provider = None
                z_columns.clear()
                y_columns.clear()
                retained_cleanup = collective_heap_cleanup(comm)
                _emit_marker(
                    marker_callback,
                    "v6_port_modal_bottom_first_passing_checkpoint",
                    checkpoint=checkpoint,
                )
                _emit_marker(
                    marker_callback,
                    "v6_port_modal_bottom_retained_apply_state_ready",
                    checkpoint=checkpoint,
                    retained_peak_limit_gib=V6_H4_PORT_MODAL_BOTTOM_RETAINED_LIMIT_GIB,
                    action_diagnostics=petrov_action.diagnostics,
                    temporary_training_columns_released=True,
                    collective_cleanup=retained_cleanup,
                    resource_gate="pending_parent_process_tree_samples",
                )
                break
            release_checkpoint()

        if not checkpoints:
            raise RuntimeError("V6 port-modal route did not reach checkpoint 64")
        final = checkpoints[-1]
        numerical_pass = bool(final["gate"]["pass"])
        _emit_marker(
            marker_callback,
            "v6_port_modal_bottom_construction_end",
            checkpoint=final["checkpoint"],
            numerical_pass=numerical_pass,
            construction_peak_limit_gib=V6_H4_PORT_MODAL_BOTTOM_CONSTRUCTION_LIMIT_GIB,
            retained_peak_limit_gib=V6_H4_PORT_MODAL_BOTTOM_RETAINED_LIMIT_GIB,
            resource_gate="pending_parent_process_tree_samples",
        )
        return {
            "schema": "task039.v6-h4-port-modal-bottom-component.v1",
            "status": "component_completed" if numerical_pass else "component_failed",
            "component_candidate": True,
            "research_only": True,
            "general_production": False,
            "profile": V6_H4_PORT_MODAL_BOTTOM_PROFILE_ID,
            "schedule": {
                "count": len(schedule),
                "checkpoints": list(V6_PORT_MODAL_CHECKPOINTS),
                "sha256": schedule_sha256,
                "training_value_digest": training_value_digest(),
                "spool_opened_after_basis_seal": holdout_spool_loaded,
            },
            "packet": {
                "manifest": str(Path(packet_manifest).resolve()),
                "manifest_sha256": packet_manifest_sha256,
                "identity": _json_safe(packet_identity),
                "consumer_qep_calls": 0,
                "full_ephemeral_hydration": True,
                "left_vectors_hydrated": True,
                "vectors_before_destroy": packet_diagnostics.get(
                    "vector_count_before_destroy"
                ),
                "arrays_retained_after_owner": False,
            },
            "exact_spool_root": str(Path(exact_spool_root).resolve()),
            "base_action": base_diagnostics,
            "checkpoints": checkpoints,
            "final_checkpoint": final["checkpoint"],
            "gates": {
                **dict(final["gate"]),
                "numerical_pass": numerical_pass,
                "resource_pass": None,
                "construction_resource_pass": None,
                "retained_resource_pass": None,
                "resource_authority": "parent_process_tree_marker_samples",
            },
            "factor_inventory": {
                "exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "base_factor_count": 1,
                "nested_ksp": False,
            },
            "top": "not_run_by_bottom_only_contract",
            "outer": "not_run",
            "recovery": "not_run",
            "field": "not_run",
            "RTA": "not_run",
            "telemetry": {
                "process_tree_samples": "expected_from_parent_launcher",
                "construction_peak_limit_gib": V6_H4_PORT_MODAL_BOTTOM_CONSTRUCTION_LIMIT_GIB,
                "retained_peak_limit_gib": V6_H4_PORT_MODAL_BOTTOM_RETAINED_LIMIT_GIB,
                "swap": "parent_measured",
            },
        }
    finally:
        release_checkpoint()
        spool = None
        if gradient_provider is not None:
            gradient_provider.destroy()
        if owner is not None:
            owner.destroy()
        if packet_bundle is not None:
            packet_bundle.destroy()
        fixed_diagnostics = None
        if fixed_action is not None:
            fixed_action.destroy()
            fixed_diagnostics = dict(fixed_action.diagnostics)
        if components is not None:
            components.destroy()
        if base_action is not None:
            base_action.destroy()
            _emit_marker(
                marker_callback,
                "v6_port_modal_bottom_cleanup",
                fixed_action_diagnostics=fixed_diagnostics,
                base_factor_count_after_destroy=base_action.diagnostics.get(
                    "lifecycle", {}
                ).get("factor_count_after_destroy"),
                exact_factor_count=0,
                global_direct_factor_count=0,
            )
        collective_heap_cleanup(comm)


def _run_v7_h4_exact_side_full_formal(
    setup: Any,
    layout: HybridAugmentedLayout,
    *,
    operator: PETSc.Mat,
    context: Any,
    comm: MPI.Intracomm,
    marker_callback: Callable[[str, Mapping[str, Any]], None],
    recovery_runner: Callable[
        [Any, Any, Any, Path, Mapping[str, Any]], Mapping[str, Any]
    ],
    producer: Mapping[str, Any],
    run_directory: str | Path,
    release_before_recovery: Callable[[], Mapping[str, Any]],
) -> dict[str, Any]:
    """Run the explicit V7 outer solve, then the existing recovery authority."""

    rhs = _default_rhs(setup, layout)
    iterative = None
    retained_solution = None
    try:
        _emit_marker(
            marker_callback,
            "outer_solve_begin",
            source="solve_hybrid_block_ldu_iterative",
            ksp_type="gmres",
            restart=10,
            max_it=V3_7_MAX_IT,
            threshold=V3_7_RESIDUAL_TOLERANCE,
            fixed_preconditioner=True,
            nested_ksp=False,
        )
        iterative = solve_hybrid_block_ldu_iterative(
            operator,
            rhs,
            context,
            config=HybridBlockLduIterativeConfig(
                restart=10,
                max_it=V3_7_MAX_IT,
                threshold=V3_7_RESIDUAL_TOLERANCE,
                ksp_type="gmres",
                fixed_preconditioner=True,
            ),
            progress_callback=lambda row: _emit_marker(
                marker_callback,
                "outer_solve_progress",
                source="solve_hybrid_block_ldu_iterative",
                **dict(row),
            ),
        )
        retained_solution = iterative.solution.duplicate()
        iterative.solution.copy(retained_solution)
        _emit_marker(
            marker_callback,
            "solution_snapshot_created",
            source="v7_full_formal_outer_solution",
        )
        postsolve = dict(iterative.postsolve_audit)
        solve_report = {
            "status": "completed" if postsolve.get("pass") is True else "failed",
            "pass": bool(postsolve.get("pass") is True),
            "ksp_type": postsolve.get("ksp_type", "gmres"),
            "restart": int(postsolve.get("restart", 10)),
            "max_it": V3_7_MAX_IT,
            "threshold": V3_7_RESIDUAL_TOLERANCE,
            "converged_reason": int(iterative.converged_reason),
            "iterations": int(iterative.iterations),
            "postsolve": postsolve,
            "block_relative_residuals": dict(iterative.block_relative_residuals),
            "timing": dict(iterative.timing),
            "inventory": dict(iterative.inventory),
        }
        _emit_marker(
            marker_callback,
            "outer_solve_ready",
            source="solve_hybrid_block_ldu_iterative",
            solve_report=solve_report,
        )
        iterative.destroy()
        iterative = None
        release = dict(release_before_recovery())
        release_pass = bool(
            release.get("factor_cleanup_pass") is True
            and release.get("actions_destroyed") is True
            and release.get("component_cleanup_pass") is True
            and isinstance(release.get("collective_heap_cleanup"), Mapping)
            and release["collective_heap_cleanup"].get("collective_call_completed")
            is True
            and all(
                int(value) == 0
                for value in release.get("factor_count_after_cleanup", {}).values()
            )
        )
        release["pass"] = release_pass
        _emit_marker(
            marker_callback,
            "outer_solve_objects_cleanup",
            source="v7_full_formal_release_before_recovery",
            release=release,
            factor_count_after_cleanup=release.get("factor_count_after_cleanup"),
        )
        if not solve_report["pass"]:
            return {
                "status": "full_formal_outer_failure",
                "solve": solve_report,
                "recovery": "not_run",
                "release_before_recovery": release,
            }
        if not release_pass:
            return {
                "status": "full_formal_lifecycle_failure",
                "solve": solve_report,
                "recovery": "not_run",
                "release_before_recovery": release,
            }
        _emit_marker(
            marker_callback,
            "recovery_physics_begin",
            source="run_v3_7_recovery_runner",
        )
        recovery = dict(
            recovery_runner(
                setup,
                layout,
                retained_solution,
                Path(run_directory).resolve(),
                producer,
            )
        )
        _emit_marker(
            marker_callback,
            "recovery_physics_end",
            source="run_v3_7_recovery_runner",
            recovery=recovery,
        )
        return {
            "status": (
                "full_formal_completed"
                if recovery.get("pass") is True
                else "full_formal_recovery_failure"
            ),
            "solve": solve_report,
            "recovery": recovery,
            "release_before_recovery": release,
            "authority_path": str(
                Path(run_directory).resolve()
                / "numerical_output"
                / "v3_7_hybrid_authority.json"
            ),
        }
    finally:
        if iterative is not None:
            iterative.destroy()
        if retained_solution is not None:
            retained_solution.destroy()
            _emit_marker(
                marker_callback,
                "solution_snapshot_destroyed",
                source="v7_full_formal_finalizer",
            )
        rhs.destroy()


def run_v5_h4_exact_side_setup_only(
    setup: Any,
    layout: HybridAugmentedLayout,
    *,
    comm: MPI.Intracomm,
    marker_callback: Callable[[str, Mapping[str, Any]], None],
    qualification_scope: str = TASK039_V4_H4_CASE_QUALIFICATION_SCOPE,
    sampled_column_contract: Mapping[str, Any] | None = None,
    streaming_w_batch_size: int | None = None,
    v6_profile: bool = False,
    exact_spool_root: str | Path | None = None,
    packet_identity: Mapping[str, Any] | None = None,
    packet_manifest_sha256: str | None = None,
    full_formal_runner: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the reviewed h4 exact-side stack, then stop before any solve."""

    components: dict[str, Any] = {}
    actions: dict[str, Any] = {}
    context = None
    operator = None
    operator_context = None
    ksp = None
    completed = False
    result: dict[str, Any] | None = None
    internal_cleanup: dict[str, Any] = {"status": "not_run"}
    outer_ready_factor_counts: dict[str, int] = {}
    layer_graph: dict[str, Any] = {}
    spool_validation: dict[str, Any] | None = None
    full_formal_result: dict[str, Any] | None = None
    try:
        if v6_profile:
            if streaming_w_batch_size is not None:
                raise ValueError("V6 post-compaction setup is frozen to retained-W")
            if (
                not exact_spool_root
                or not packet_identity
                or not packet_manifest_sha256
            ):
                raise ValueError(
                    "V6 setup requires the authenticated exact-response spool"
                )
            spool_records = _load_v5_fixed_budget_spool_shards(
                exact_spool_root,
                comm,
                packet_identity=packet_identity,
                manifest_sha256=packet_manifest_sha256,
            )
            spool_validation = {
                "status": "measured",
                "root": str(Path(exact_spool_root).resolve()),
                "labels": list(spool_records),
                "artifact_count": 2 * len(spool_records) * int(comm.size),
                "array_hashes_verified": True,
                "transient_hash_read": True,
                "arrays_retained": False,
                "identity_bound": True,
            }
        sampled_column_contract = (
            _load_v5_h4_sampled_column_contract()
            if sampled_column_contract is None
            else dict(sampled_column_contract)
        )
        post_coupling_cleanup = collective_heap_cleanup(comm)
        for side, system in (("bottom", setup.bottom), ("top", setup.top)):
            side_components = _build_research_explicit_side_components(system)
            components[side] = side_components
            if v6_profile:
                layer_graph[side] = _v6_layer_graph_audit(side_components.F, system)
            _emit_marker(
                marker_callback,
                f"{side}_F_ready",
                source="research_explicit_side_components",
                matrices=_v5_side_matrix_inventory(side_components),
                retained_through_woodbury_build=True,
                original_F_retained_for_modal_schur=False,
                post_coupling_cleanup=post_coupling_cleanup,
                layer_graph=layer_graph.get(side) if v6_profile else None,
            )

            def lifecycle(event: str, detail: Mapping[str, Any], *, _side=side):
                _emit_marker(
                    marker_callback,
                    f"{_side}_{event}",
                    source="ResearchExactFactorInverse",
                    **dict(detail),
                )

            actions[side] = create_research_exact_side_lu_action(
                side_components.F,
                side_components,
                qualification_scope=qualification_scope,
                explicit_opt_in=True,
                factor_only_storage=True,
                streaming_w_batch_size=streaming_w_batch_size,
                lifecycle_callback=lifecycle,
            )
            _emit_marker(
                marker_callback,
                f"{side}_woodbury_ready",
                source="HybridLocalDtnWoodburyOracle",
                diagnostics=actions[side].diagnostics,
            )
            released = _destroy_v5_side_components(side_components, retain_d=True)
            if all(released[name] for name in ("H", "C", "F")):
                actions[side].woodbury.mark_borrowed_matrices_released()
            cleanup = collective_heap_cleanup(comm)
            woodbury_diagnostics = actions[side].diagnostics["woodbury"]
            streaming = bool(woodbury_diagnostics.get("streaming_w_storage"))
            component_release = dict(released)
            released_objects = {
                "F": bool(woodbury_diagnostics.get("F_H_matrices_released", False)),
                "H": bool(woodbury_diagnostics.get("F_H_matrices_released", False)),
            }
            if streaming:
                component_release.update(
                    {
                        "C": False,
                        "C_original_carrier_handle_transferred": True,
                    }
                )
                released_objects.update(
                    {
                        "C_original_carrier_handle_transferred": True,
                        "C_action_resident": bool(
                            woodbury_diagnostics.get("C_action_resident")
                        ),
                        "C_action_owned": bool(
                            woodbury_diagnostics.get("C_action_owned")
                        ),
                        "C_matrix_released": bool(
                            woodbury_diagnostics.get("C_action_released")
                        ),
                    }
                )
            else:
                released_objects["C"] = bool(released["C"])
            _emit_marker(
                marker_callback,
                f"{side}_construction_cleanup",
                source="collective_heap_cleanup",
                cleanup=cleanup,
                component_release=component_release,
                action_diagnostics=actions[side].diagnostics,
                retained_objects={
                    "side_action": True,
                    "factor_matrix": True,
                    "D": bool(released["D_retained"]),
                    "W": bool(
                        actions[side].diagnostics["woodbury"].get("W_resident", True)
                    ),
                    "C_action": bool(
                        woodbury_diagnostics.get("C_action_resident", False)
                        and woodbury_diagnostics.get("C_action_owned", False)
                    ),
                },
                released_objects=released_objects,
            )

        _emit_marker(
            marker_callback,
            "both_side_actions_ready",
            actions={side: action.diagnostics for side, action in actions.items()},
            global_direct_factor_count=0,
            factor_count_at_outer_ready={
                side: int(action.diagnostics.get("direct_factor_count", 0))
                for side, action in actions.items()
            },
        )
        _emit_marker(
            marker_callback,
            "modal_schur_build_begin",
            source="create_research_exact_side_lu_block_ldu_preconditioner",
            coupling_matrices={
                side: {
                    name: _petsc_matrix_stats(
                        getattr(getattr(setup.coupling, side), name),
                        assemble=False,
                    )
                    for name in ("projection", "positive_traction", "negative_traction")
                }
                for side in ("bottom", "top")
            },
        )
        context = create_research_exact_side_lu_block_ldu_preconditioner(
            layout,
            setup.bottom,
            setup.top,
            setup.coupling,
            actions["bottom"],
            actions["top"],
            qualification_scope=qualification_scope,
            explicit_opt_in=True,
            sampled_columns=sampled_column_contract["columns"],
            sampled_column_roles=sampled_column_contract["roles"],
            sampled_column_contract_sha256=sampled_column_contract["sha256"],
        )
        _emit_marker(
            marker_callback,
            "modal_schur_ready",
            source="create_research_exact_side_lu_block_ldu_preconditioner",
            inventory=context.inventory,
        )
        operator, operator_context = create_hybrid_assembled_block_action(
            setup.bottom, setup.top, setup.coupling
        )
        ksp = PETSc.KSP().create(comm)
        ksp.setOperators(operator)
        ksp.setType(PETSc.KSP.Type.GMRES)
        ksp.setGMRESRestart(10)
        ksp.setPCSide(PETSc.PC.Side.RIGHT)
        pc = ksp.getPC()
        pc.setType(PETSc.PC.Type.PYTHON)
        pc.setPythonContext(context)
        ksp.setUp()
        outer_ready_factor_counts = {
            side: int(action.diagnostics.get("direct_factor_count", 0))
            for side, action in actions.items()
        }
        outer_ksp_report = {
            "type": str(ksp.getType()),
            "restart": 10,
            "ksp_profile": "v5_exact_side_fixed_pc_gmres10",
            "set_up": True,
            "solve_called": False,
            "krylov_vectors": "not_allocated_before_solve",
            "factor_count_at_outer_ready": dict(outer_ready_factor_counts),
        }
        outer_context_inventory = deepcopy(context.inventory)
        _emit_marker(
            marker_callback,
            "outer_ksp_setup_ready",
            source="PETSc.KSP.setUp",
            ksp_type=str(ksp.getType()),
            restart=10,
            ksp_profile="v5_exact_side_fixed_pc_gmres10",
            solve_called=False,
            krylov_vectors={"status": "not_allocated_before_solve"},
            preconditioner_inventory=context.inventory,
            factor_count_at_outer_ready=outer_ready_factor_counts,
        )
        if full_formal_runner is not None:
            ksp.destroy()
            ksp = None
            _emit_marker(
                marker_callback,
                "outer_setup_probe_ksp_released",
                source="v7_full_formal_setup_probe",
                ksp_destroyed=True,
                formal_ksp_profile="gmres_restart10",
            )

            def release_before_recovery() -> Mapping[str, Any]:
                nonlocal context, operator_context, operator
                if context is not None and not bool(
                    getattr(context, "_destroyed", False)
                ):
                    context.destroy()
                context = None
                if operator_context is not None:
                    operator_context.destroy()
                    operator_context = None
                if operator is not None:
                    operator.destroy()
                    operator = None
                for action in actions.values():
                    action.destroy()
                component_cleanup = {
                    side: _destroy_v5_side_components(side_components)
                    for side, side_components in components.items()
                }
                cleanup = collective_heap_cleanup(comm)
                factor_counts = {
                    side: int(action.diagnostics.get("direct_factor_count", 0))
                    for side, action in actions.items()
                }
                return {
                    "factor_count_after_cleanup": factor_counts,
                    "factor_cleanup_pass": bool(
                        factor_counts
                        and all(count == 0 for count in factor_counts.values())
                    ),
                    "actions_destroyed": all(
                        bool(action.diagnostics.get("destroyed"))
                        for action in actions.values()
                    ),
                    "component_cleanup": component_cleanup,
                    "component_cleanup_pass": bool(
                        component_cleanup
                        and all(
                            all(
                                values.get(name) is True
                                for name in ("H", "C", "F", "D")
                            )
                            for values in component_cleanup.values()
                        )
                    ),
                    "collective_heap_cleanup": cleanup,
                }

            full_formal_result = dict(
                full_formal_runner(
                    setup=setup,
                    layout=layout,
                    operator=operator,
                    context=context,
                    comm=comm,
                    marker_callback=marker_callback,
                    release_before_recovery=release_before_recovery,
                )
            )
        completed = True
        result = {
            "schema": (
                "task039.v6-h4-post-compaction-setup-only.v1"
                if v6_profile
                else "task039.v5-h4-exact-side-setup-only.v1"
            ),
            "status": (
                "setup_only_completed"
                if full_formal_result is None
                else str(full_formal_result.get("status"))
            ),
            "qualification_scope": qualification_scope,
            "sampled_column_contract": sampled_column_contract,
            "markers": list(V5_H4_SETUP_ONLY_MARKERS),
            "solve": (
                "not_run"
                if full_formal_result is None
                else full_formal_result.get("solve", "not_run")
            ),
            "recovery": (
                "not_run"
                if full_formal_result is None
                else full_formal_result.get("recovery", "not_run")
            ),
            "field_export": "not_run",
            "side_actions": {
                side: action.diagnostics for side, action in actions.items()
            },
            "modal_schur": outer_context_inventory.get("modal_schur"),
            "outer_ksp": outer_ksp_report,
            "full_formal": full_formal_result,
            "telemetry": {
                "process_tree_samples": {
                    "path": "numerical_output/process_tree_samples.jsonl",
                    "writer": "parent_task038_launcher",
                    "status": "expected_from_parent_launcher",
                },
                "memory_stages": {
                    "path": "numerical_output/memory_stages.jsonl",
                    "writer": "parent_task038_launcher_marker_alignment",
                    "status": "expected_from_parent_launcher",
                },
                "memory_stage_markers": {
                    "path": "numerical_output/memory_stage_markers.raw.jsonl",
                    "writer": "v3_7_worker",
                    "status": "measured_worker_marker_stream",
                },
                "memory_object_ledger": {
                    "path": "numerical_output/memory_object_ledger.json",
                    "schema": "task039.v3-7-memory-object-ledger.v1",
                    "status": "finalized_in_worker_finalizer",
                },
            },
        }
        if v6_profile:
            result["v6_profile"] = {
                "profile_id": V6_H4_POST_COMPACTION_PROFILE_ID,
                "streaming_w_storage": False,
                "setup_peak_limit_gib": V6_H4_SETUP_THRESHOLD_GIB,
                "outer_ready_peak_limit_gib": V6_H4_OUTER_READY_THRESHOLD_GIB,
                "layer_graph": layer_graph,
                "exact_response_spool": spool_validation,
                "resource_gate": {
                    "process_tree_peak_gib": "pending_parent_sample_alignment",
                    "outer_ready_peak_gib": "pending_parent_sample_alignment",
                    "swap": "pending_parent_sample_alignment",
                    "pass": None,
                },
                "factor_count_at_outer_ready": outer_ready_factor_counts,
                "factor_count_after_final_cleanup": "pending_finalizer",
                "packet_qep_refs_released": "pending_finalizer",
            }
        return result
    finally:
        if ksp is not None:
            ksp.destroy()
        if context is not None:
            context.destroy()
        if operator_context is not None:
            operator_context.destroy()
        if operator is not None:
            operator.destroy()
        side_cleanup: dict[str, Any] = {}
        for side in ("top", "bottom"):
            action = actions.get(side)
            if action is not None:
                action.destroy()
            side_components = components.get(side)
            if side_components is not None:
                side_cleanup[side] = _destroy_v5_side_components(side_components)
        cleanup = collective_heap_cleanup(comm)
        factor_counts = {
            side: int(action.diagnostics.get("direct_factor_count", 0))
            for side, action in actions.items()
        }
        action_destroyed = all(
            bool(action.diagnostics.get("destroyed")) for action in actions.values()
        )
        internal_cleanup = {
            "source": "setup_only_internal_finally",
            "cleanup": cleanup,
            "factor_count_after_cleanup": factor_counts,
            "side_component_cleanup": side_cleanup,
            "exact_side_objects_destroyed": bool(
                completed
                and action_destroyed
                and all(count == 0 for count in factor_counts.values())
                and all(
                    all(values[name] for name in ("H", "C", "F", "D"))
                    for values in side_cleanup.values()
                )
            ),
            "completed": completed,
            "factor_count_at_outer_ready": dict(outer_ready_factor_counts),
        }
        if result is not None:
            result["setup_only_internal_cleanup"] = internal_cleanup


def _v3_7_object_ledger() -> dict[str, Any]:
    names = (
        "setup",
        "qep_matrices",
        "selected_basis",
        "one_cell_factor",
        "lift_columns",
        "apply_columns",
        "bottom_projection",
        "top_projection",
        "independent_reference",
        "side_base_ilu",
        "correction_wrappers",
        "candidate_d_explicit_components",
        "exact_side_action",
        "exact_side_factors",
        "solution_snapshot",
        "recovery_physics",
    )
    return {
        "schema": "task039.v3-7-memory-object-ledger.v1",
        "status": "in_progress",
        "capacity_semantics": "known capacities only; unknown is not_available",
        "objects": {
            name: {
                "created": False,
                "completed": False,
                "destroyed": False,
                "status": "not_available",
                "capacity_bytes": "not_available",
                "classification": "lifecycle_marker",
            }
            for name in names
        },
        "events": [],
    }


def _write_v3_7_object_ledger(
    path: Path,
    ledger: Mapping[str, Any],
    comm: MPI.Intracomm,
    *,
    synchronize: bool = True,
) -> None:
    if comm.rank == 0:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(_json_safe(dict(ledger)), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    if synchronize:
        comm.barrier()


def _write_v3_7_identity_checkpoint(
    run_directory: Path,
    *,
    source_sha: str,
    producer: Mapping[str, Any],
    identity: Mapping[str, Any],
    comm: MPI.Intracomm,
) -> Path:
    """Persist the completed identity audit before the next stage can fail."""

    path = run_directory / "numerical_output" / "v3_7_identity_checkpoint.json"
    checkpoint = {
        "schema": "task039.v3-7-identity-checkpoint.v1",
        "source_sha": source_sha,
        "physical_identity": {
            "producer_source_sha": producer.get("producer_source_sha"),
            "physical_model_sha256": producer.get("physical_model_sha256"),
            "model_id": producer.get("model_id"),
            "requested_modes": producer.get("requested_modes"),
            "mpi_size": producer.get("mpi_size"),
            "external_keys_exact": producer.get("external_keys_exact"),
        },
        "pass": bool(identity.get("pass") is True),
        "relative_limit": V3_7_RHS_TOLERANCE,
        "vector_count": identity.get("vector_count"),
        "vectors": identity.get("vectors", {}),
        "rhs_equality": identity.get("rhs_equality", {}),
        "coupling_isolation": identity.get("coupling_isolation", {}),
        "direct_solution_residual": identity.get("direct_solution_residual"),
    }
    if comm.rank == 0:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(_json_safe(checkpoint), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    comm.barrier()
    return path


def _write_v3_7_side_survey_checkpoint(
    run_directory: Path,
    *,
    source_sha: str,
    producer: Mapping[str, Any],
    correction: Mapping[str, Any],
    comm: MPI.Intracomm,
) -> Path:
    """Persist the completed side survey before exact-oracle construction."""

    path = run_directory / "numerical_output" / "v3_7_side_survey_checkpoint.json"
    passes = []
    for item in correction.get("passes", ()):
        side_reports = {}
        for side in ("bottom", "top"):
            report = item.get(side, {})
            inventory = report.get("vector_inventory", {})
            summary = report.get("rho_summary", {})
            side_reports[side] = {
                "informative_labels": list(inventory.get("informative_labels", ())),
                "excluded_labels": list(inventory.get("excluded_labels", ())),
                "informative_count": inventory.get("informative_count"),
                "excluded_count": inventory.get("excluded_count"),
                "median": summary.get("median"),
                "worst": summary.get("worst"),
                "candidate_A_pass": summary.get("candidate_A_pass"),
            }
        passes.append(
            {
                "correction_passes": item.get("correction_passes"),
                "pass": item.get("pass"),
                **side_reports,
            }
        )
    checkpoint = {
        "schema": "task039.v3-7-side-survey-checkpoint.v1",
        "source_sha": source_sha,
        "physical_identity": {
            "producer_source_sha": producer.get("producer_source_sha"),
            "consumer_source_sha": producer.get("consumer_source_sha"),
            "physical_model_sha256": producer.get("physical_model_sha256"),
            "model_id": producer.get("model_id"),
            "requested_modes": producer.get("requested_modes"),
            "mpi_size": producer.get("mpi_size"),
            "external_keys_exact": producer.get("external_keys_exact"),
        },
        "survey_status": correction.get("status"),
        "survey_pass": correction.get("pass"),
        "passes": passes,
    }
    if comm.rank == 0:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(_json_safe(checkpoint), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    comm.barrier()
    return path


def _write_v3_8_candidate_b_checkpoint(
    run_directory: Path,
    *,
    source_sha: str,
    resolved_payload: Mapping[str, Any],
    producer: Mapping[str, Any],
    report: Mapping[str, Any],
    comm: MPI.Intracomm,
) -> Path:
    """Persist the compact Candidate-B budget evidence before teardown."""

    provenance = resolved_payload["provenance"]
    inventory = producer["inventory"]
    resolved_config_path = run_directory / "resolved_config.json"
    resolved_config_sha = hashlib.sha256(resolved_config_path.read_bytes()).hexdigest()
    checkpoint = {
        "schema": "task039.v3-8-candidate-b-checkpoint.v1",
        "source_sha": source_sha,
        "physical_identity": {
            "consumer_input_sha256": provenance["input_sha256"],
            "consumer_resolved_config_sha256": resolved_config_sha,
            "consumer_physical_model_sha256": provenance["physical_model_sha256"],
            "producer_source_sha": inventory["source_sha"],
            "producer_input_sha256": inventory["input_sha256"],
            "producer_resolved_config_sha256": inventory["resolved_config_sha256"],
            "producer_physical_model_sha256": inventory["physical_model_sha256"],
            "direct_payload_sha256": inventory["payload"]["artifact"]["sha256"],
            "verified_shard_count": inventory["verified_shard_count"],
            "model_id": producer["model_id"],
            "requested_modes": producer["requested_modes"],
            "mpi_size": producer["mpi_size"],
            "external_keys_exact": producer["external_keys_exact"],
        },
        "status": report.get("status"),
        "pass": report.get("pass"),
        "selected_budget": report.get("selected_budget"),
        "budgets_run": report.get("budgets_run", []),
        "gate": report.get("gate", {}),
        "factor_inventory": report.get("factor_inventory", {}),
        "budget_reports": report.get("budget_reports", []),
    }
    if report.get("failure") is not None:
        checkpoint["failure"] = report["failure"]
    path = run_directory / "numerical_output" / "v3_8_candidate_b_checkpoint.json"
    if comm.rank == 0:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(_json_safe(checkpoint), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    comm.barrier()
    return path


def _write_v3_8_candidate_b_failure_checkpoint(
    run_directory: Path,
    *,
    source_sha: str,
    resolved_payload: Mapping[str, Any],
    producer: Mapping[str, Any],
    error: Exception,
    comm: MPI.Intracomm,
) -> Path:
    progress = getattr(error, "candidate_b_progress", {})
    finite_audit = getattr(error, "finite_audit", None)
    report = {
        "status": "candidate_b_implementation_failure",
        "pass": None,
        "selected_budget": None,
        "budgets_run": [],
        "gate": {
            "median_limit": V3_8_CANDIDATE_B_MEDIAN_LIMIT,
            "worst_limit": V3_8_CANDIDATE_B_WORST_LIMIT,
            "formula": "rho=norm(b-Ax)/max(norm(b),1e-30)",
        },
        "factor_inventory": {
            "per_budget": [],
            "simultaneous_total_base_factor_count": "not_available",
            "simultaneous_total_direct_factor_count": "not_available",
            "simultaneous_total_global_hybrid_direct_factor_count": "not_available",
        },
        "budget_reports": [],
        "failure": {
            "type": type(error).__name__,
            "message": str(error),
            "attempted_budget": progress.get("budget", "not_available"),
            "attempted_side": progress.get("side", "not_available"),
            "finite_audit": finite_audit or "not_available",
            "unmeasured": [
                "candidate_b_gate",
                "rho",
                "median",
                "worst",
                "factor_inventory",
                "remaining_budgets",
            ],
        },
    }
    return _write_v3_8_candidate_b_checkpoint(
        run_directory,
        source_sha=source_sha,
        resolved_payload=resolved_payload,
        producer=producer,
        report=report,
        comm=comm,
    )


def _write_v3_8_candidate_c_checkpoint(
    run_directory: Path,
    *,
    source_sha: str,
    resolved_payload: Mapping[str, Any],
    producer: Mapping[str, Any],
    report: Mapping[str, Any],
    comm: MPI.Intracomm,
) -> Path:
    """Persist the independent C1 one-pass ILU(1) side evidence."""

    provenance = resolved_payload["provenance"]
    inventory = producer["inventory"]
    resolved_config_sha = hashlib.sha256(
        (run_directory / "resolved_config.json").read_bytes()
    ).hexdigest()
    checkpoint = {
        "schema": "task039.v3-8-candidate-c1-checkpoint.v1",
        "candidate": "C1",
        "sequence": "whole_endcap_ilu1_dynamic_dtn_woodbury_one_pass",
        "source_sha": source_sha,
        "physical_identity": {
            "consumer_input_sha256": provenance["input_sha256"],
            "consumer_resolved_config_sha256": resolved_config_sha,
            "consumer_physical_model_sha256": provenance["physical_model_sha256"],
            "producer_source_sha": inventory["source_sha"],
            "producer_input_sha256": inventory["input_sha256"],
            "producer_resolved_config_sha256": inventory["resolved_config_sha256"],
            "producer_physical_model_sha256": inventory["physical_model_sha256"],
            "direct_payload_sha256": inventory["payload"]["artifact"]["sha256"],
            "verified_shard_count": inventory["verified_shard_count"],
            "model_id": producer["model_id"],
            "requested_modes": producer["requested_modes"],
            "mpi_size": producer["mpi_size"],
            "external_keys_exact": producer["external_keys_exact"],
        },
        "status": report.get("status"),
        "pass": report.get("pass"),
        "gate": report.get("gate", {}),
        "side_reports": report.get("side_reports", {}),
        "factor_inventory": report.get("factor_inventory", {}),
        "direct_solution": report.get("direct_solution", {}),
    }
    if report.get("failure") is not None:
        checkpoint["failure"] = report["failure"]
    path = run_directory / "numerical_output" / "v3_8_candidate_c1_checkpoint.json"
    if comm.rank == 0:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(_json_safe(checkpoint), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    comm.barrier()
    return path


def _write_v3_8_candidate_c_failure_checkpoint(
    run_directory: Path,
    *,
    source_sha: str,
    resolved_payload: Mapping[str, Any],
    producer: Mapping[str, Any],
    error: Exception,
    comm: MPI.Intracomm,
) -> Path:
    progress = getattr(error, "candidate_c_progress", {})
    report = {
        "status": "candidate_c1_implementation_failure",
        "pass": None,
        "gate": {
            "median_limit": V3_8_CANDIDATE_C_MEDIAN_LIMIT,
            "worst_limit": V3_8_CANDIDATE_C_WORST_LIMIT,
            "classification": "review_derived_conservative_production_side_gate",
            "formula": "rho=norm(b-Ax)/max(norm(b),1e-30)",
        },
        "side_reports": {},
        "factor_inventory": {},
        "failure": {
            "type": type(error).__name__,
            "message": str(error),
            "attempted_side": progress.get("side", "not_available"),
            "unmeasured": ["side_reports", "rho", "factor_inventory"],
        },
    }
    return _write_v3_8_candidate_c_checkpoint(
        run_directory,
        source_sha=source_sha,
        resolved_payload=resolved_payload,
        producer=producer,
        report=report,
        comm=comm,
    )


def _candidate_c_side_gate(report: Mapping[str, Any]) -> bool:
    summary = report["rho_summary"]
    return bool(
        report.get("pass") is True
        and summary.get("median") is not None
        and summary.get("worst") is not None
        and summary["median"] <= V3_8_CANDIDATE_C_MEDIAN_LIMIT
        and summary["worst"] <= V3_8_CANDIDATE_C_WORST_LIMIT
    )


def _candidate_c_cleanup_fields(
    fixed_diagnostics: Mapping[str, Any], base_diagnostics: Mapping[str, Any]
) -> dict[str, Any]:
    lifecycle = base_diagnostics["lifecycle"]
    return {
        "fixed_destroyed": fixed_diagnostics["destroyed"],
        "base_destroyed": base_diagnostics["destroyed"],
        "base_factor_count_after_destroy": lifecycle["factor_count_after_destroy"],
        "base_factors_released": lifecycle["factors_released"],
    }


def _candidate_e_side_gate(report: Mapping[str, Any]) -> bool:
    summary = report["rho_summary"]
    return bool(
        report.get("pass") is True
        and summary.get("median") is not None
        and summary.get("worst") is not None
        and summary["median"] <= V3_8_CANDIDATE_E_MEDIAN_LIMIT
        and summary["worst"] <= V3_8_CANDIDATE_E_WORST_LIMIT
    )


def _candidate_e_training_vectors(
    system: Any,
) -> tuple[list[PETSc.Vec], list[dict[str, Any]]]:
    vectors: list[PETSc.Vec] = []
    identities: list[dict[str, Any]] = []
    for seed in V3_8_CANDIDATE_E_TRAINING_SEEDS:
        vector = system.A.createVecRight()
        first, last = (int(value) for value in vector.getOwnershipRange())
        index = np.arange(first, last, dtype=np.float64)
        vector.getArray()[:] = np.asarray(
            np.sin(index * 0.001 + seed) + 1j * np.cos(index * 0.0007 - seed),
            dtype=PETSc.ScalarType,
        )
        vector.assemble()
        vectors.append(vector)
        identities.append(_side_vector_identity(vector, f"candidate_e_training_{seed}"))
    return vectors, identities


def _write_v3_8_candidate_e_checkpoint(
    run_directory: Path,
    *,
    source_sha: str,
    resolved_payload: Mapping[str, Any],
    producer: Mapping[str, Any],
    report: Mapping[str, Any],
    comm: MPI.Intracomm,
) -> Path:
    provenance = resolved_payload["provenance"]
    inventory = producer["inventory"]
    resolved_config_sha = hashlib.sha256(
        (run_directory / "resolved_config.json").read_bytes()
    ).hexdigest()
    checkpoint = {
        "schema": "task039.v3-8-candidate-e-side-only.v1",
        "candidate": "E",
        "status": report.get("status"),
        "pass": report.get("pass"),
        "source_identity": {
            "consumer_source_sha": source_sha,
            "producer_source_sha": inventory["source_sha"],
            "consumer_input_sha256": provenance["input_sha256"],
            "consumer_resolved_config_sha256": resolved_config_sha,
            "consumer_physical_model_sha256": provenance["physical_model_sha256"],
            "producer_input_sha256": inventory["input_sha256"],
            "producer_resolved_config_sha256": inventory["resolved_config_sha256"],
            "producer_physical_model_sha256": inventory["physical_model_sha256"],
            "direct_payload_sha256": inventory["payload"]["artifact"]["sha256"],
            "verified_shard_count": inventory["verified_shard_count"],
            "model_id": producer["model_id"],
            "requested_modes": producer["requested_modes"],
            "mpi_size": producer["mpi_size"],
            "external_keys_exact": producer["external_keys_exact"],
        },
        "training": report.get("training", {}),
        "validation": report.get("side_reports", {}),
        "gate": report.get("gate", {}),
        "factor_inventory": report.get("factor_inventory", {}),
        "direct_solution": report.get("direct_solution", {}),
    }
    if report.get("failure") is not None:
        checkpoint["failure"] = report["failure"]
    path = run_directory / "numerical_output" / "v3_8_candidate_e_side_checkpoint.json"
    if comm.rank == 0:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(_json_safe(checkpoint), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    comm.barrier()
    return path


def _run_v3_8_candidate_e_side_campaign(
    setup: Any,
    layout: Any,
    rhs: PETSc.Vec,
    *,
    resolved_payload: Mapping[str, Any],
    producer: Mapping[str, Any],
    modal_amplitudes: np.ndarray,
    run_directory: Path,
    source_sha: str,
    comm: MPI.Intracomm,
    survey_side_vectors: dict[str, dict[str, PETSc.Vec]],
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> tuple[dict[str, Any], Path]:
    """Measure Candidate E on both condensed side operators only."""

    production_operator, production_context = create_hybrid_assembled_block_action(
        setup.bottom, setup.top, setup.coupling
    )
    x_star = None
    direct_residual = None
    components: dict[str, Any] = {}
    base_actions: dict[str, Any] = {}
    fixed_actions: dict[str, Any] = {}
    correction_actions: dict[str, Any] = {}
    training: dict[str, Any] = {}
    vector_metadata: dict[str, dict[str, Any]] = {}
    factor_inventory: dict[str, Any] = {}
    side_reports: dict[str, Any] = {}
    current_side = "not_started"
    direct_residual_norm = None
    failure: Exception | None = None

    try:
        _emit_marker(marker_callback, "candidate_e_direct_payload_begin")
        x_star, mapping = rebuild_hybrid_augmented_vector(
            producer["inventory"],
            setup.bottom,
            setup.top,
            layout,
            modal_amplitudes,
        )
        direct_residual = production_operator.createVecLeft()
        production_operator.mult(x_star, direct_residual)
        direct_residual.scale(PETSc.ScalarType(-1.0))
        direct_residual.axpy(PETSc.ScalarType(1.0), rhs)
        direct_residual_norm = float(direct_residual.norm())
        _emit_marker(
            marker_callback,
            "candidate_e_direct_payload_end",
            mapping_status=mapping.get("mapping_status"),
            direct_residual_norm=direct_residual_norm,
        )
        for side, system, block_slice in (
            ("bottom", setup.bottom, layout.local_bottom_slice),
            ("top", setup.top, layout.local_top_slice),
        ):
            side_residual = system.A.createVecLeft()
            try:
                values = side_residual.getArray()
                source_values = direct_residual.getArray(readonly=True)[block_slice]
                if values.size != source_values.size:
                    raise ValueError(
                        f"{side} direct residual ownership does not match layout"
                    )
                values[:] = source_values
                side_residual.assemble()
                vectors, _owned, metadata = _side_survey_vectors(
                    system,
                    side,
                    {"direct_solution_side_residual": side_residual},
                )
                survey_side_vectors[side] = vectors
                vector_metadata[side] = metadata
            finally:
                side_residual.destroy()

        _emit_marker(marker_callback, "candidate_e_side_fixed_setup_begin")
        for side, system in (("bottom", setup.bottom), ("top", setup.top)):
            components[side] = create_hybrid_local_dtn_action_components(system)
            base_actions[side] = build_hybrid_whole_endcap_fixed_smoother_action(system)
            fixed_actions[side] = HybridLocalDtnWoodburyFixedAction(
                base_actions[side], components[side], residual_correction_steps=1
            )
        _emit_marker(
            marker_callback,
            "candidate_e_side_fixed_setup_end",
            components_live=2,
            base_actions_live=2,
            fixed_actions_live=2,
            correction_steps=1,
        )

        for side, system in (("bottom", setup.bottom), ("top", setup.top)):
            current_side = side
            _emit_marker(marker_callback, "candidate_e_training_begin", side=side)
            seeds, identities = _candidate_e_training_vectors(system)
            try:
                correction_actions[side] = (
                    build_fixed_side_error_subspace_correction_action(
                        system.A, fixed_actions[side], seeds
                    )
                )
                diagnostics = correction_actions[side].diagnostics
                training[side] = {
                    "seed_ids": list(V3_8_CANDIDATE_E_TRAINING_SEEDS),
                    "seed_identities": identities,
                    "seed_count": diagnostics["seed_count"],
                    "layers_completed": diagnostics["layers_completed"],
                    "seed_block_is_layer_one": diagnostics["seed_block_is_layer_one"],
                    "rank": diagnostics["rank"],
                    "rank_cap": diagnostics["rank_cap"],
                    "R_shape": diagnostics["R_shape"],
                    "R_condition_number": diagnostics["R_condition_number"],
                    "qr_reconstruction_relative_error": diagnostics[
                        "qr_reconstruction_relative_error"
                    ],
                    "q_orthogonality_error": diagnostics["q_orthogonality_error"],
                    "setup_seconds": diagnostics["setup_seconds"],
                    "setup_operator_apply_count": diagnostics[
                        "setup_operator_apply_count"
                    ],
                    "setup_base_apply_count": diagnostics["setup_base_apply_count"],
                }
            finally:
                for seed in seeds:
                    seed.destroy()
            _emit_marker(
                marker_callback,
                "candidate_e_training_end",
                side=side,
                rank=training[side]["rank"],
            )
        _emit_marker(
            marker_callback,
            "candidate_e_correction_actions_ready",
            live=2,
        )

        for side, system in (("bottom", setup.bottom), ("top", setup.top)):
            current_side = side
            _emit_marker(marker_callback, f"candidate_e_side_{side}_begin", side=side)
            side_report = _side_correction_probe(
                system,
                correction_actions[side],
                1,
                survey_side_vectors[side],
                vector_metadata[side],
            )
            summary = side_report["rho_summary"]
            summary.pop("candidate_A_pass", None)
            summary["median_limit"] = V3_8_CANDIDATE_E_MEDIAN_LIMIT
            summary["worst_limit"] = V3_8_CANDIDATE_E_WORST_LIMIT
            summary["candidate_E_pass"] = _candidate_e_side_gate(side_report)
            side_reports[side] = side_report
            e_diagnostics = correction_actions[side].diagnostics
            fixed_diagnostics = fixed_actions[side].diagnostics
            base_diagnostics = fixed_diagnostics["base_diagnostics"]
            factor_inventory[side] = {
                "base_identity": fixed_diagnostics["base_identity"],
                "operator_identity": e_diagnostics["operator_identity"],
                "base_factor_count": e_diagnostics["base_ilu_factor_count"],
                "nested_ksp_created": e_diagnostics["base_nested_ksp_created"],
                "local_direct_factor_count": e_diagnostics["direct_factor_count"],
                "global_hybrid_direct_factor_count": e_diagnostics[
                    "global_hybrid_direct_factor_count"
                ],
                "factor_rows": base_diagnostics["factor_rows"],
                "source_matrix_nnz": base_diagnostics["source_matrix_nnz"],
                "factor_nnz": base_diagnostics["factor_nnz"],
                "factor_csr_payload_estimate_bytes": base_diagnostics[
                    "factor_csr_payload_estimate_bytes"
                ],
                "base_setup_seconds": base_diagnostics["setup_seconds"],
                "base_apply_count": base_diagnostics["apply_count"],
                "correction_setup_seconds": e_diagnostics["setup_seconds"],
                "correction_apply_count": e_diagnostics["apply_count"],
                "fixed_destroyed": False,
                "base_destroyed": False,
                "correction_destroyed": False,
            }
            _emit_marker(
                marker_callback,
                f"candidate_e_side_{side}_end",
                side=side,
                candidate_E_pass=summary["candidate_E_pass"],
            )
    except Exception as error:
        error.candidate_e_progress = {"side": current_side}
        failure = error
    finally:
        for side in ("top", "bottom"):
            if side in correction_actions:
                correction_actions[side].destroy()
                if side in factor_inventory:
                    factor_inventory[side]["correction_destroyed"] = True
            if side in fixed_actions:
                fixed_actions[side].destroy()
                if side in factor_inventory:
                    factor_inventory[side]["fixed_destroyed"] = True
            if side in base_actions:
                base_actions[side].destroy()
                if side in factor_inventory:
                    base_diagnostics = base_actions[side].diagnostics
                    lifecycle = base_diagnostics["lifecycle"]
                    factor_inventory[side].update(
                        {
                            "base_destroyed": True,
                            "base_factor_count_after_destroy": lifecycle[
                                "factor_count_after_destroy"
                            ],
                            "factors_released": lifecycle["factors_released"],
                        }
                    )
            if side in components:
                components[side].destroy()
        _emit_marker(marker_callback, "candidate_e_side_fixed_cleanup_end")
        _destroy(direct_residual)
        _destroy(x_star)
        production_context.destroy()
        production_operator.destroy()

    if failure is not None:
        report = {
            "status": "candidate_e_implementation_failure",
            "pass": None,
            "gate": {
                "median_limit": V3_8_CANDIDATE_E_MEDIAN_LIMIT,
                "worst_limit": V3_8_CANDIDATE_E_WORST_LIMIT,
                "formula": "rho=norm(b-Ax)/max(norm(b),1e-30)",
            },
            "training": training,
            "side_reports": side_reports,
            "factor_inventory": factor_inventory,
            "failure": {
                "type": type(failure).__name__,
                "message": str(failure),
                "attempted_side": getattr(failure, "candidate_e_progress", {}).get(
                    "side", "not_available"
                ),
                "unmeasured": ["candidate_E_gate", "remaining_side_reports"],
            },
        }
        _write_v3_8_candidate_e_checkpoint(
            run_directory,
            source_sha=source_sha,
            resolved_payload=resolved_payload,
            producer=producer,
            report=report,
            comm=comm,
        )
        raise failure

    report = {
        "status": "measured",
        "pass": bool(
            side_reports["bottom"]["rho_summary"]["candidate_E_pass"]
            and side_reports["top"]["rho_summary"]["candidate_E_pass"]
        ),
        "gate": {
            "median_limit": V3_8_CANDIDATE_E_MEDIAN_LIMIT,
            "worst_limit": V3_8_CANDIDATE_E_WORST_LIMIT,
            "formula": "rho=norm(b-Ax)/max(norm(b),1e-30)",
        },
        "training": training,
        "side_reports": side_reports,
        "factor_inventory": {
            "per_side": factor_inventory,
            "simultaneous_total_base_factor_count": sum(
                int(item["base_factor_count"]) for item in factor_inventory.values()
            ),
            "simultaneous_total_local_direct_factor_count": sum(
                int(item["local_direct_factor_count"])
                for item in factor_inventory.values()
            ),
            "simultaneous_total_global_hybrid_direct_factor_count": sum(
                int(item["global_hybrid_direct_factor_count"])
                for item in factor_inventory.values()
            ),
        },
        "direct_solution": {
            "mapping": mapping,
            "residual_norm": direct_residual_norm,
            "source": "hash-bound direct payload reconstructed on current layout",
        },
    }
    checkpoint = _write_v3_8_candidate_e_checkpoint(
        run_directory,
        source_sha=source_sha,
        resolved_payload=resolved_payload,
        producer=producer,
        report=report,
        comm=comm,
    )
    return report, checkpoint


def _run_v3_8_candidate_b_campaign(
    setup: Any,
    layout: Any,
    rhs: PETSc.Vec,
    *,
    resolved_payload: Mapping[str, Any],
    producer: Mapping[str, Any],
    modal_amplitudes: np.ndarray,
    run_directory: Path,
    source_sha: str,
    comm: MPI.Intracomm,
    survey_side_vectors: dict[str, dict[str, PETSc.Vec]],
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> tuple[dict[str, Any], Path]:
    """Run only Candidate B after common setup and before V3-7 identity."""

    production_operator, production_context = create_hybrid_assembled_block_action(
        setup.bottom, setup.top, setup.coupling
    )
    x_star = None
    direct_residual = None
    components: dict[str, Any] = {}
    base_actions: dict[str, Any] = {}
    fixed_actions: dict[str, Any] = {}
    vector_metadata: dict[str, dict[str, Any]] = {}
    try:
        _emit_marker(marker_callback, "candidate_b_direct_payload_begin")
        x_star, mapping = rebuild_hybrid_augmented_vector(
            producer["inventory"],
            setup.bottom,
            setup.top,
            layout,
            modal_amplitudes,
        )
        direct_residual = production_operator.createVecLeft()
        production_operator.mult(x_star, direct_residual)
        direct_residual.scale(PETSc.ScalarType(-1.0))
        direct_residual.axpy(PETSc.ScalarType(1.0), rhs)
        _emit_marker(
            marker_callback,
            "candidate_b_direct_payload_end",
            mapping_status=mapping.get("mapping_status"),
            direct_residual_norm=float(direct_residual.norm()),
        )
        for side, system, block_slice in (
            ("bottom", setup.bottom, layout.local_bottom_slice),
            ("top", setup.top, layout.local_top_slice),
        ):
            side_residual = system.A.createVecLeft()
            try:
                values = side_residual.getArray()
                source_values = direct_residual.getArray(readonly=True)[block_slice]
                if values.size != source_values.size:
                    raise ValueError(
                        f"{side} direct residual ownership does not match layout"
                    )
                values[:] = source_values
                side_residual.assemble()
                vectors, _owned, metadata = _side_survey_vectors(
                    system,
                    side,
                    {"direct_solution_side_residual": side_residual},
                )
                survey_side_vectors[side] = vectors
                vector_metadata[side] = metadata
            finally:
                side_residual.destroy()
        _emit_marker(marker_callback, "candidate_b_side_fixed_setup_begin")
        components = {
            "bottom": create_hybrid_local_dtn_action_components(setup.bottom),
            "top": create_hybrid_local_dtn_action_components(setup.top),
        }
        base_actions = {
            "bottom": build_hybrid_whole_endcap_fixed_smoother_action(setup.bottom),
            "top": build_hybrid_whole_endcap_fixed_smoother_action(setup.top),
        }
        for side in ("bottom", "top"):
            fixed_actions[side] = HybridLocalDtnWoodburyFixedAction(
                base_actions[side],
                components[side],
                residual_correction_steps=1,
            )
        _emit_marker(
            marker_callback,
            "candidate_b_side_fixed_setup_end",
            components_live=2,
            base_actions_live=2,
            fixed_actions_live=2,
        )
        try:
            report = run_v3_8_candidate_b_budget_sequence(
                {"bottom": setup.bottom, "top": setup.top},
                fixed_actions,
                {
                    "bottom": survey_side_vectors["bottom"],
                    "top": survey_side_vectors["top"],
                },
                vector_metadata,
                marker_callback=marker_callback,
            )
        except Exception as error:
            checkpoint = _write_v3_8_candidate_b_failure_checkpoint(
                run_directory,
                source_sha=source_sha,
                resolved_payload=resolved_payload,
                producer=producer,
                error=error,
                comm=comm,
            )
            _emit_marker(
                marker_callback,
                "candidate_b_failure_checkpoint",
                path=str(checkpoint),
                failure_type=type(error).__name__,
            )
            raise
        checkpoint = _write_v3_8_candidate_b_checkpoint(
            run_directory,
            source_sha=source_sha,
            resolved_payload=resolved_payload,
            producer=producer,
            report=report,
            comm=comm,
        )
        report["direct_solution"] = {
            "mapping": mapping,
            "residual_norm": float(direct_residual.norm()),
            "source": "hash-bound direct payload reconstructed on current layout",
        }
        return report, checkpoint
    finally:
        for side in ("top", "bottom"):
            if side in fixed_actions:
                fixed_actions[side].destroy()
            if side in base_actions:
                base_actions[side].destroy()
            if side in components:
                components[side].destroy()
        _emit_marker(marker_callback, "candidate_b_side_fixed_cleanup_end")
        _destroy(direct_residual)
        _destroy(x_star)
        production_context.destroy()
        production_operator.destroy()


def _run_v3_8_candidate_c_campaign(
    setup: Any,
    layout: Any,
    rhs: PETSc.Vec,
    *,
    resolved_payload: Mapping[str, Any],
    producer: Mapping[str, Any],
    modal_amplitudes: np.ndarray,
    run_directory: Path,
    source_sha: str,
    comm: MPI.Intracomm,
    survey_side_vectors: dict[str, dict[str, PETSc.Vec]],
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> tuple[dict[str, Any], Path]:
    """Run only C1: ILU(1) plus the existing one-pass Woodbury action."""

    production_operator, production_context = create_hybrid_assembled_block_action(
        setup.bottom, setup.top, setup.coupling
    )
    x_star = None
    direct_residual = None
    components: dict[str, Any] = {}
    base_actions: dict[str, Any] = {}
    fixed_actions: dict[str, Any] = {}
    vector_metadata: dict[str, dict[str, Any]] = {}
    report: dict[str, Any] | None = None
    failure: Exception | None = None
    current_side = "not_started"
    try:
        _emit_marker(marker_callback, "candidate_c_direct_payload_begin")
        x_star, mapping = rebuild_hybrid_augmented_vector(
            producer["inventory"],
            setup.bottom,
            setup.top,
            layout,
            modal_amplitudes,
        )
        direct_residual = production_operator.createVecLeft()
        production_operator.mult(x_star, direct_residual)
        direct_residual.scale(PETSc.ScalarType(-1.0))
        direct_residual.axpy(PETSc.ScalarType(1.0), rhs)
        _emit_marker(
            marker_callback,
            "candidate_c_direct_payload_end",
            mapping_status=mapping.get("mapping_status"),
            direct_residual_norm=float(direct_residual.norm()),
        )
        for side, system, block_slice in (
            ("bottom", setup.bottom, layout.local_bottom_slice),
            ("top", setup.top, layout.local_top_slice),
        ):
            side_residual = system.A.createVecLeft()
            try:
                values = side_residual.getArray()
                source_values = direct_residual.getArray(readonly=True)[block_slice]
                if values.size != source_values.size:
                    raise ValueError(
                        f"{side} direct residual ownership does not match layout"
                    )
                values[:] = source_values
                side_residual.assemble()
                vectors, _owned, metadata = _side_survey_vectors(
                    system,
                    side,
                    {"direct_solution_side_residual": side_residual},
                )
                survey_side_vectors[side] = vectors
                vector_metadata[side] = metadata
            finally:
                side_residual.destroy()

        _emit_marker(marker_callback, "candidate_c_side_fixed_setup_begin")
        for side, system in (("bottom", setup.bottom), ("top", setup.top)):
            components[side] = create_hybrid_local_dtn_action_components(system)
            base_actions[side] = build_hybrid_whole_endcap_fixed_smoother_action(
                system, ilu_levels=1
            )
        for side in ("bottom", "top"):
            fixed_actions[side] = HybridLocalDtnWoodburyFixedAction(
                base_actions[side],
                components[side],
                base_identity="whole_endcap_ilu1_fixed_smoother",
                operator_identity="whole_endcap_ilu1_woodbury_fixed_action",
                ilu_levels=1,
                residual_correction_steps=1,
            )
        _emit_marker(
            marker_callback,
            "candidate_c_side_fixed_setup_end",
            components_live=2,
            base_actions_live=2,
            fixed_actions_live=2,
            ilu_levels=1,
        )

        side_reports: dict[str, Any] = {}
        factor_inventory: dict[str, Any] = {}
        for side in ("bottom", "top"):
            current_side = side
            _emit_marker(
                marker_callback,
                f"candidate_c_side_{side}_begin",
                side=side,
                correction_passes=1,
            )
            side_report = _side_correction_probe(
                setup.bottom if side == "bottom" else setup.top,
                fixed_actions[side],
                1,
                survey_side_vectors[side],
                vector_metadata[side],
            )
            summary = side_report["rho_summary"]
            summary["median_limit"] = V3_8_CANDIDATE_C_MEDIAN_LIMIT
            summary["worst_limit"] = V3_8_CANDIDATE_C_WORST_LIMIT
            summary["candidate_C_pass"] = _candidate_c_side_gate(side_report)
            side_reports[side] = side_report
            action_diagnostics = fixed_actions[side].diagnostics
            base_diagnostics = action_diagnostics["base_diagnostics"]
            smoother_diagnostics = base_diagnostics["smoother"]
            woodbury_diagnostics = action_diagnostics["woodbury"]
            factor_inventory[side] = {
                "base_identity": action_diagnostics["base_identity"],
                "operator_identity": action_diagnostics["operator_identity"],
                "ilu_levels": action_diagnostics["ilu_levels"],
                "factor_rows": base_diagnostics["factor_rows"],
                "source_matrix_nnz": base_diagnostics["source_matrix_nnz"],
                "factor_nnz": base_diagnostics["factor_nnz"],
                "factor_csr_payload_estimate_bytes": base_diagnostics[
                    "factor_csr_payload_estimate_bytes"
                ],
                "base_setup_seconds": base_diagnostics["setup_seconds"],
                "base_apply_seconds": smoother_diagnostics["one_level_mean_apply_s"],
                "base_apply_count": base_diagnostics["apply_count"],
                "woodbury_setup_seconds": woodbury_diagnostics["setup_seconds"],
                "woodbury_apply_seconds": woodbury_diagnostics["apply_seconds"],
                "woodbury_apply_count": woodbury_diagnostics["apply_count"],
                "base_factor_count": action_diagnostics["base_factor_count"],
                "direct_factor_count": action_diagnostics["local_direct_factor_count"],
                "global_hybrid_direct_factor_count": action_diagnostics[
                    "global_hybrid_direct_factor_count"
                ],
                "fixed_destroyed": False,
                "base_destroyed": False,
                "base_factor_count_after_destroy": None,
            }
            _emit_marker(
                marker_callback,
                f"candidate_c_side_{side}_end",
                side=side,
                candidate_C_pass=summary["candidate_C_pass"],
            )
        report = {
            "status": "measured",
            "pass": bool(
                side_reports["bottom"]["rho_summary"]["candidate_C_pass"]
                and side_reports["top"]["rho_summary"]["candidate_C_pass"]
            ),
            "gate": {
                "median_limit": V3_8_CANDIDATE_C_MEDIAN_LIMIT,
                "worst_limit": V3_8_CANDIDATE_C_WORST_LIMIT,
                "classification": ("review_derived_conservative_production_side_gate"),
                "formula": "rho=norm(b-Ax)/max(norm(b),1e-30)",
            },
            "side_reports": side_reports,
            "factor_inventory": {
                "per_side": factor_inventory,
                "simultaneous_total_base_factor_count": sum(
                    int(item["base_factor_count"]) for item in factor_inventory.values()
                ),
                "simultaneous_total_direct_factor_count": sum(
                    int(item["direct_factor_count"])
                    for item in factor_inventory.values()
                ),
                "simultaneous_total_global_hybrid_direct_factor_count": sum(
                    int(item["global_hybrid_direct_factor_count"])
                    for item in factor_inventory.values()
                ),
            },
            "direct_solution": {
                "mapping": mapping,
                "residual_norm": float(direct_residual.norm()),
                "source": "hash-bound direct payload reconstructed on current layout",
            },
        }
    except Exception as error:
        error.candidate_c_progress = {"side": current_side}
        failure = error
    finally:
        for side in ("top", "bottom"):
            if side in fixed_actions:
                fixed_actions[side].destroy()
            if side in base_actions:
                base_actions[side].destroy()
            if side in components:
                components[side].destroy()
            if report is not None and side in factor_inventory:
                factor_inventory[side].update(
                    _candidate_c_cleanup_fields(
                        fixed_actions[side].diagnostics,
                        base_actions[side].diagnostics,
                    )
                )
        _emit_marker(marker_callback, "candidate_c_side_fixed_cleanup_end")
        _destroy(direct_residual)
        _destroy(x_star)
        production_context.destroy()
        production_operator.destroy()

    if failure is not None:
        _write_v3_8_candidate_c_failure_checkpoint(
            run_directory,
            source_sha=source_sha,
            resolved_payload=resolved_payload,
            producer=producer,
            error=failure,
            comm=comm,
        )
        raise failure
    assert report is not None
    checkpoint = _write_v3_8_candidate_c_checkpoint(
        run_directory,
        source_sha=source_sha,
        resolved_payload=resolved_payload,
        producer=producer,
        report=report,
        comm=comm,
    )
    return report, checkpoint


def _candidate_d_producer_metadata(
    resolved_payload: Mapping[str, Any],
    source_sha: str,
    marker_callback: Callable[[str, Mapping[str, Any]], None],
) -> dict[str, Any]:
    provenance = resolved_payload["provenance"]
    inventory = resolved_payload["derived"]["external_mode_inventory"]
    return {
        "producer_source_sha": V3_7_DIRECT_PRODUCER_SHA,
        "consumer_source_sha": source_sha,
        "physical_model_sha256": provenance["physical_model_sha256"],
        "model_id": resolved_payload["model_id"],
        "requested_modes": 480,
        "mpi_size": 8,
        "external_keys_exact": len(inventory["keys"]) == 600,
        "direct_reference_payload_loaded": False,
        "_stage_callback": marker_callback,
    }


def _write_v3_8_candidate_d_checkpoint(
    run_directory: Path,
    *,
    source_sha: str,
    resolved_payload: Mapping[str, Any],
    producer: Mapping[str, Any],
    oracle: Mapping[str, Any],
    recovery: Mapping[str, Any] | None,
    cleanup: Mapping[str, Any],
    comm: MPI.Intracomm,
    classification: str = V3_8_CANDIDATE_D_CLASSIFICATION,
    qualification: Mapping[str, Any] | None = None,
    status: str = "measured",
) -> Path:
    provenance = resolved_payload["provenance"]
    resolved_config = run_directory / "resolved_config.json"
    resolved_config_sha = hashlib.sha256(resolved_config.read_bytes()).hexdigest()
    recovery_pass = bool(isinstance(recovery, Mapping) and recovery.get("pass") is True)
    oracle_pass = bool(oracle.get("pass") is True)
    cleanup_pass = bool(cleanup.get("pass") is True)
    checkpoint = {
        "schema": (
            "task039.v3-8-candidate-d-qualified-checkpoint.v1"
            if qualification is not None
            else "task039.v3-8-candidate-d-checkpoint.v1"
        ),
        "status": status,
        "candidate": "D",
        "classification": classification,
        "pass": bool(oracle_pass and cleanup_pass and recovery_pass),
        "source_identity": {
            "consumer_source_sha": source_sha,
            "producer_source_sha": producer["producer_source_sha"],
            "consumer_input_sha256": provenance["input_sha256"],
            "consumer_resolved_config_sha256": resolved_config_sha,
            "consumer_physical_model_sha256": provenance["physical_model_sha256"],
            "model_id": producer["model_id"],
            "requested_modes": producer["requested_modes"],
            "mpi_size": producer["mpi_size"],
            "external_keys_exact": producer["external_keys_exact"],
        },
        "direct_reference_payload_loaded": False,
        "identity_reference_materialization": "not_run",
        "exact_side_components_materialized": True,
        "oracle": dict(oracle),
        "recovery": dict(recovery) if isinstance(recovery, Mapping) else "not_run",
        "release_contract": {
            "exact_side_cleanup_before_recovery": bool(cleanup.get("pass") is True),
            "cleanup": dict(cleanup),
            "global_hybrid_direct_factor_count": oracle.get("inventory", {}).get(
                "global_hybrid_direct_factor_count"
            ),
            "bottom_direct_factor_count": oracle.get("inventory", {}).get(
                "bottom_direct_factor_count"
            ),
            "top_direct_factor_count": oracle.get("inventory", {}).get(
                "top_direct_factor_count"
            ),
        },
    }
    if qualification is not None:
        checkpoint["qualification"] = dict(qualification)
    path = run_directory / "numerical_output" / "v3_8_candidate_d_checkpoint.json"
    if comm.rank == 0:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(_json_safe(checkpoint), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    comm.barrier()
    return path


def _run_v3_8_candidate_d_campaign(
    setup: Any,
    layout: Any,
    rhs: PETSc.Vec,
    *,
    resolved_payload: Mapping[str, Any],
    producer: Mapping[str, Any],
    run_directory: Path,
    source_sha: str,
    comm: MPI.Intracomm,
    marker_callback: Callable[[str, Mapping[str, Any]], None],
    oracle_runner: Callable[..., Mapping[str, Any]],
    recovery_runner: Callable[
        [Any, Any, Any, Path, Mapping[str, Any]], Mapping[str, Any]
    ]
    | None,
    case_qualified: bool = False,
    qualification_scope: str = V3_8_CANDIDATE_D_QUALIFICATION_SCOPE,
    qualification_method: str = V3_8_CANDIDATE_D_QUALIFIED_METHOD,
    qualification_target: str = V3_8_CANDIDATE_D_QUALIFIED_CLASSIFICATION,
) -> tuple[dict[str, Any], Path]:
    """Run the explicit online Candidate-D side-factor path without direct payloads."""

    snapshot = None
    components = None
    oracle_report = None
    recovery_result = None
    _emit_marker(
        marker_callback,
        "candidate_d_online_begin",
        direct_reference_payload_loaded=False,
        identity_reference_materialization=False,
        global_direct_factor_count=0,
    )

    def consume_solution(solution: PETSc.Vec, _oracle: Mapping[str, Any]) -> None:
        nonlocal snapshot
        snapshot = solution.duplicate()
        solution.copy(snapshot)
        _emit_marker(
            marker_callback,
            "solution_snapshot_created",
            source="candidate_d_exact_side_oracle",
        )

    try:
        components = build_research_explicit_side_components(setup.bottom, setup.top)
        _emit_marker(
            marker_callback,
            "candidate_d_explicit_components_ready",
            materialized_components="F/C/D/H",
            global_reference_operator=False,
            direct_reference_payload_loaded=False,
        )
        _emit_marker(marker_callback, "exact_side_oracle_begin", candidate="D")
        oracle_kwargs = {
            "reference": None,
            "explicit_components": components,
            "max_it": V3_7_MAX_IT,
            "restart": 90,
            "threshold": V3_7_RESIDUAL_TOLERANCE,
            "matrix_repeat_tolerance": V3_7_MATRIX_REPEAT_TOLERANCE,
            "solution_consumer": consume_solution,
        }
        if case_qualified:
            oracle_kwargs.update(
                {
                    "qualification_scope": qualification_scope,
                    "explicit_opt_in": True,
                }
            )
        oracle_report = dict(
            oracle_runner(
                layout, setup.bottom, setup.top, setup.coupling, rhs, **oracle_kwargs
            )
        )
        _emit_marker(
            marker_callback,
            "exact_side_oracle_end",
            candidate="D",
            numerical_pass=oracle_report.get("numerical_pass"),
            inventory_pass=oracle_report.get("inventory_pass"),
            lifecycle=oracle_report.get("lifecycle", {}),
        )
        lifecycle = oracle_report.get("lifecycle", {})
        factor_cleanup_pass = bool(
            lifecycle.get("bottom_action_destroyed") is True
            and lifecycle.get("top_action_destroyed") is True
            and lifecycle.get("bottom_direct_factor_count_after_cleanup") == 0
            and lifecycle.get("top_direct_factor_count_after_cleanup") == 0
            and lifecycle.get("explicit_components_destroyed_by_oracle") is False
        )
        components.destroy()
        components_released = components.destroyed
        components = None
        collective_cleanup = collective_heap_cleanup(comm)
        collective_cleanup_completed = bool(
            collective_cleanup.get("collective_call_completed") is True
        )
        _emit_marker(
            marker_callback,
            "candidate_d_explicit_components_destroyed",
            factors_released=factor_cleanup_pass,
            components_released=components_released,
        )
        _emit_marker(
            marker_callback,
            "candidate_d_collective_heap_cleanup",
            **dict(collective_cleanup),
        )
        cleanup = {
            "pass": bool(
                factor_cleanup_pass
                and components_released
                and collective_cleanup_completed
            ),
            "factor_cleanup_pass": factor_cleanup_pass,
            "bottom_direct_factor_count_after_cleanup": lifecycle.get(
                "bottom_direct_factor_count_after_cleanup"
            ),
            "top_direct_factor_count_after_cleanup": lifecycle.get(
                "top_direct_factor_count_after_cleanup"
            ),
            "explicit_components_released": components_released,
            "collective_heap_cleanup": dict(collective_cleanup),
            "collective_cleanup_completed": collective_cleanup_completed,
        }
        if cleanup["pass"] is not True:
            raise ValueError(f"Candidate-D exact-side cleanup failed: {cleanup}")
        if oracle_report.get("pass") is True:
            if recovery_runner is None:
                raise ValueError(
                    "Candidate-D recovery_runner is required after oracle pass"
                )
            if snapshot is None:
                raise ValueError(
                    "Candidate-D oracle pass did not produce a solution snapshot"
                )
            _emit_marker(marker_callback, "recovery_physics_begin", candidate="D")
            recovery_result = dict(
                recovery_runner(
                    setup,
                    layout,
                    snapshot,
                    run_directory,
                    producer,
                )
            )
            _emit_marker(
                marker_callback,
                "recovery_physics_end",
                candidate="D",
                **{"pass": recovery_result.get("pass")},
            )
        if snapshot is not None:
            snapshot.destroy()
            snapshot = None
            _emit_marker(marker_callback, "solution_snapshot_destroyed", candidate="D")
        report = {
            "status": "attempted" if case_qualified else "measured",
            "classification": (
                qualification_method
                if case_qualified
                else V3_8_CANDIDATE_D_CLASSIFICATION
            ),
            "pass": bool(
                oracle_report.get("pass") is True
                and cleanup.get("pass") is True
                and isinstance(recovery_result, Mapping)
                and recovery_result.get("pass") is True
            ),
            "direct_reference_payload_loaded": False,
            "identity_reference_materialization": "not_run",
            "exact_side_components_materialized": True,
            "exact_side_components_released_before_recovery": True,
            "oracle": oracle_report,
            "cleanup": cleanup,
            "recovery": recovery_result if recovery_result is not None else "not_run",
        }
        qualification = None
        if case_qualified:
            side_actions = oracle_report["side_action_diagnostics"]
            qualification = {
                "qualification_scope": qualification_scope,
                "explicit_opt_in": True,
                "case_qualification_opt_in": True,
                "case_qualification_attempt": True,
                "general_production": False,
                "ordinary_default": False,
                "ordinary_default_changed": False,
                "classification": qualification_method,
                "qualification_target": qualification_target,
                "final_qualification_status": "pending_parent_resource_gate",
                "status": "attempted",
                "local_direct_factor_count": {
                    side: side_actions[side]["direct_factor_count"]
                    for side in ("bottom", "top")
                },
                "global_hybrid_direct_factor_count": oracle_report["inventory"][
                    "global_hybrid_direct_factor_count"
                ],
                "nested_iterative_ksp_count": oracle_report[
                    "nested_iterative_ksp_count"
                ],
                "local_direct_preonly_ksp_count": oracle_report[
                    "local_direct_preonly_ksp_count"
                ],
                "cleanup_local_direct_factor_count": {
                    "bottom": lifecycle["bottom_direct_factor_count_after_cleanup"],
                    "top": lifecycle["top_direct_factor_count_after_cleanup"],
                },
            }
            report["qualification"] = qualification
        checkpoint = _write_v3_8_candidate_d_checkpoint(
            run_directory,
            source_sha=source_sha,
            resolved_payload=resolved_payload,
            producer=producer,
            oracle=oracle_report,
            recovery=recovery_result,
            cleanup=cleanup,
            comm=comm,
            classification=report["classification"],
            qualification=qualification,
            status=report["status"],
        )
        return report, checkpoint
    except Exception:
        if components is not None:
            components.destroy()
        if snapshot is not None:
            snapshot.destroy()
        raise


def _record_v3_7_marker(
    ledger: dict[str, Any], marker: str, detail: Mapping[str, Any]
) -> None:
    """Record only lifecycle facts represented by an actual marker."""

    ledger["events"].append(
        {
            "marker": marker,
            "detail_keys": sorted(str(key) for key in detail),
        }
    )
    objects = ledger["objects"]

    def mark(name: str, *, created=False, completed=False, destroyed=False) -> None:
        item = objects[name]
        if created:
            item["created"] = True
            item["status"] = "measured"
        if completed:
            item["completed"] = True
        if destroyed:
            item["destroyed"] = True

    if marker == "identity_reference_materialization_end":
        mark("independent_reference", created=True, completed=True)
    elif marker == "borrowed_reference_cleanup_end":
        mark("independent_reference", destroyed=True)
    elif marker in {
        "side_fixed_components_setup_end",
        "candidate_b_side_fixed_setup_end",
        "candidate_c_side_fixed_setup_end",
        "candidate_e_side_fixed_setup_end",
    }:
        mark("side_base_ilu", created=True, completed=True)
        if marker == "candidate_c_side_fixed_setup_end":
            mark("correction_wrappers", created=True, completed=True)
    elif marker == "candidate_e_correction_actions_ready":
        mark("correction_wrappers", created=True, completed=True)
    elif marker.startswith("side_correction_") and marker.endswith("_ready"):
        mark("correction_wrappers", created=True, completed=True)
    elif marker.startswith("side_correction_") and marker.endswith("_end"):
        mark("correction_wrappers", destroyed=True)
    elif marker.startswith("candidate_b_budget_") and marker.endswith("_ready"):
        mark("correction_wrappers", created=True, completed=True)
    elif marker.startswith("candidate_b_budget_") and marker.endswith("_end"):
        mark("correction_wrappers", destroyed=True)
    elif marker in {
        "side_survey_cleanup_end",
        "candidate_b_side_fixed_cleanup_end",
        "candidate_c_side_fixed_cleanup_end",
        "candidate_e_side_fixed_cleanup_end",
    }:
        if objects["side_base_ilu"]["created"]:
            mark("side_base_ilu", destroyed=True)
        if marker in {
            "candidate_c_side_fixed_cleanup_end",
            "candidate_e_side_fixed_cleanup_end",
        }:
            if objects["correction_wrappers"]["created"]:
                mark("correction_wrappers", destroyed=True)
    elif marker == "exact_side_oracle_begin":
        mark("exact_side_action", created=True)
    elif marker == "exact_side_oracle_end":
        mark("exact_side_action", completed=True, destroyed=True)
        lifecycle = detail.get("lifecycle", {})
        if (
            lifecycle.get("bottom_direct_factor_count_after_cleanup") == 0
            and lifecycle.get("top_direct_factor_count_after_cleanup") == 0
        ):
            mark("exact_side_factors", created=True, completed=True, destroyed=True)
    elif marker == "candidate_d_explicit_components_ready":
        mark("candidate_d_explicit_components", created=True, completed=True)
    elif marker == "candidate_d_explicit_components_destroyed":
        mark("candidate_d_explicit_components", destroyed=True)
    elif marker == "solution_snapshot_created":
        mark("solution_snapshot", created=True, completed=True)
    elif marker == "solution_snapshot_destroyed":
        mark("solution_snapshot", destroyed=True)
    elif marker == "recovery_physics_begin":
        mark("recovery_physics", created=True)
    elif marker == "recovery_physics_end":
        mark("recovery_physics", completed=True, destroyed=True)

    if marker in {"qep_matrices_ready", "qep_matrices_complete"}:
        mark("qep_matrices", created=True, completed=True)
    elif marker in {
        "modal_qep_temporaries_released",
        "selected_biorthogonal_bases_released",
        "final_cleanup",
    }:
        mark("qep_matrices", destroyed=True)
        if marker != "final_cleanup":
            mark("selected_basis", destroyed=True)
    if marker == "selected_biorthogonal_bases_ready":
        mark("selected_basis", created=True, completed=True)
    if marker == "one_cell_factor_ready":
        mark("one_cell_factor", created=True, completed=True)
    elif marker == "one_cell_factor_destroyed":
        mark("one_cell_factor", destroyed=True)
        for name in (
            "lift_columns",
            "apply_columns",
            "bottom_projection",
            "top_projection",
        ):
            if objects[name]["created"]:
                mark(name, destroyed=True)

    for token, name in (
        ("lift_columns", "lift_columns"),
        ("apply_columns", "apply_columns"),
        ("bottom_projection", "bottom_projection"),
        ("top_projection", "top_projection"),
    ):
        if token in marker:
            mark(name, created=True)
            if marker.endswith(("_end", "_complete", "_ready")):
                mark(name, completed=True)


def run_v3_7_stage_sequence(
    *,
    identity_stage: Callable[[], Mapping[str, Any]],
    correction_stage: Callable[[], Mapping[str, Any]],
    oracle_stage: Callable[
        [Callable[[Any, Mapping[str, Any]], None]], Mapping[str, Any]
    ],
    snapshotter: Callable[[Any], Any] | None = None,
    recovery_runner: Callable[[Any], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Enforce identity -> side survey -> oracle and handoff ordering."""

    identity = dict(identity_stage())
    if identity.get("pass") is not True:
        return {
            "status": "controlled_stop_identity_failure",
            "identity": identity,
            "correction": {"status": "not_run"},
            "oracle": {"status": "not_run"},
            "solution_handoff": "not_run",
        }
    correction = dict(correction_stage())
    if correction.get("pass", True) is not True:
        return {
            "status": "controlled_stop_side_correction_failure",
            "identity": identity,
            "correction": correction,
            "oracle": {"status": "not_run"},
            "solution_handoff": "not_run",
        }
    snapshot_holder: dict[str, Any] = {}

    def consume(solution: Any, report: Mapping[str, Any]) -> None:
        if snapshotter is None:
            snapshot_holder["snapshot"] = None
            return
        snapshot_holder["snapshot"] = snapshotter(solution)
        snapshot_holder["source"] = "oracle_result.solution_duplicate"
        snapshot_holder["oracle_pass"] = bool(report.get("pass"))

    oracle = dict(oracle_stage(consume))
    handoff = "not_run"
    recovery_result: Mapping[str, Any] | None = None
    if oracle.get("pass") is True and "snapshot" in snapshot_holder:
        if recovery_runner is not None:
            recovery_result = recovery_runner(snapshot_holder["snapshot"])
            if not isinstance(recovery_result, Mapping):
                handoff = "recovery_result_invalid"
            elif recovery_result.get("pass") is True:
                handoff = "recovery_after_oracle_cleanup"
            else:
                handoff = "recovery_or_physics_failed"
        else:
            handoff = "snapshot_created_no_recovery_requested"
    elif oracle.get("pass") is not True:
        handoff = "not_run_oracle_failed"
    status = "oracle_failed"
    if oracle.get("pass") is True:
        if recovery_runner is None:
            status = "recovery_callback_required"
        elif (
            isinstance(recovery_result, Mapping) and recovery_result.get("pass") is True
        ):
            status = "completed"
        else:
            status = "oracle_linear_pass_physics_fail"
    return {
        "status": status,
        "identity": identity,
        "correction": correction,
        "oracle": oracle,
        "recovery": recovery_result,
        "solution_handoff": handoff,
    }


def run_task039_v3_7_diagnostic(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    source_sha: str,
    direct_run_dir: str | Path = V3_7_DIRECT_RUN_ROOT,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
    setup_builder: Callable[..., Any] = build_frozen_m10_setup,
    side_system_builder: Callable[..., Any] | None = None,
    inventory_loader: Callable[
        ..., tuple[dict[str, Any], np.ndarray]
    ] = load_v3_7_direct_inventory,
    reference_builder: Callable[..., Any] = build_research_independent_hybrid_reference,
    identity_runner: Callable[..., Mapping[str, Any]] = audit_hybrid_operator_identity,
    correction_runner: Callable[..., Mapping[str, Any]] | None = None,
    oracle_runner: Callable[..., Mapping[str, Any]] = run_exact_side_lu_oracle,
    stage_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
    post_destroy_cleanup: Callable[[], Mapping[str, Any]] | None = None,
    recovery_runner: Callable[
        [Any, Any, Any, Path, Mapping[str, Any]], Mapping[str, Any]
    ]
    | None = None,
    profile_override: Any | None = None,
    producer_metadata: Mapping[str, Any] | None = None,
    qualification_scope: str = V3_8_CANDIDATE_D_QUALIFICATION_SCOPE,
    qualification_method: str = V3_8_CANDIDATE_D_QUALIFIED_METHOD,
    qualification_target: str = V3_8_CANDIDATE_D_QUALIFIED_CLASSIFICATION,
    record_path: str | Path | None = None,
    candidate_b_only: bool = False,
    candidate_c_only: bool = False,
    candidate_d_only: bool = False,
    candidate_d_qualified: bool = False,
    candidate_e_side_only: bool = False,
    v5_h4_setup_only: bool = False,
    v5_h4_blr_side_only: bool = False,
    v5_h4_fixed_budget_bottom_only: bool = False,
    v5_h4_fixed_budget_exact_spool_root: str | Path | None = None,
    v6_h4_post_compaction_setup_only: bool = False,
    v6_h4_exact_spool_root: str | Path | None = None,
    v7_h4_exact_side_limit_setup_only: bool = False,
    v7_h4_exact_side_exact_spool_root: str | Path | None = None,
    v7_h4_exact_side_full_formal: bool = False,
    v6_h4_port_modal_bottom_only: bool = False,
    v6_h4_port_modal_exact_spool_root: str | Path | None = None,
    v7_h4_streamed_bottom_producer: bool = False,
    v7_h4_streamed_bottom_consumer: bool = False,
    v7_h4_streamed_bottom_consumer_basis_manifest: str | Path | None = None,
    v7_h4_streamed_bottom_consumer_basis_manifest_sha256: str | None = None,
    v7_h4_streamed_bottom_consumer_exact_spool_root: str | Path | None = None,
    v8_h4_layer_block_reconstruction: bool = False,
    v8_h4_layer_sweep_bottom: bool = False,
    v9_h4_bare_f_side: bool = False,
    v9_h4_bare_f_side_exact_spool_root: str | Path | None = None,
    v9_h4_layer_supernode_bottom: bool = False,
    v9_h4_layer_supernode_exact_spool_root: str | Path | None = None,
    v10_h4_supernode_factor_integrity: bool = False,
    v10_h4_supernode_factor_integrity_exact_spool_root: str | Path | None = None,
    v10_h4_sn2_j_only: bool = False,
    v10_h4_sn2_j_only_exact_spool_root: str | Path | None = None,
    v10_h4_j1_inner_fgmres: bool = False,
    v10_h4_j1_inner_fgmres_exact_spool_root: str | Path | None = None,
    v10_h4_side_response_packet_pilot: bool = False,
    v10_h4_side_response_packet_pilot_exact_spool_root: str | Path | None = None,
    v10_h4_side_response_packet_pilot_output_root: str | Path | None = None,
    v10_h4_side_response_packet_consumer: bool = False,
    v10_h4_side_response_packet_consumer_manifest: str | Path | None = None,
    v10_h4_side_response_packet_consumer_manifest_sha256: str | None = None,
    v10_h4_side_response_packet_full_producer: bool = False,
    v10_h4_side_response_packet_full_producer_exact_spool_root: str
    | Path
    | None = None,
    v10_h4_side_response_packet_full_producer_output_root: str | Path | None = None,
    v10_h4_side_response_packet_compression: bool = False,
    v10_h4_side_response_packet_compression_manifest: str | Path | None = None,
    v10_h4_side_response_packet_compression_manifest_sha256: str | None = None,
    v10_h4_side_response_packet_compression_producer_source_sha: str | None = None,
    v11_h4_bottom_packet_algebra: bool = False,
    v11_h4_bottom_packet_algebra_exact_spool_root: str | Path | None = None,
    v11_h4_bottom_packet_algebra_packet_manifest: str | Path | None = None,
    v11_h4_bottom_packet_algebra_packet_manifest_sha256: str | None = None,
    v11_h4_bottom_packet_algebra_producer_diagnostic: str | Path | None = None,
    v8_h4_layer_sweep_exact_spool_root: str | Path | None = None,
    v5_h4_blr_profile: str = MUMPS_BLR_V5_H4_PROFILE,
    selected_mode_packet_manifest: str | Path | None = None,
    selected_mode_packet_identity: Mapping[str, Any] | None = None,
    selected_mode_packet_manifest_sha256: str | None = None,
    v5_sampled_column_contract: Mapping[str, Any] | None = None,
    v5_streaming_w_batch_size: int | None = None,
) -> dict[str, Any]:
    """Prepare the V3-7 campaign or an explicit research candidate branch."""

    v7_h4_full_formal = bool(v7_h4_exact_side_full_formal)
    setup = None
    reference_holder: dict[str, Any] = {}
    survey_side_vectors: dict[str, dict[str, PETSc.Vec]] = {}
    marker_path = (
        Path(run_directory).resolve()
        / "numerical_output"
        / "memory_stage_markers.raw.jsonl"
    )
    marker_started = time.perf_counter()
    marker_stream = None
    object_ledger_path = (
        Path(run_directory).resolve() / "numerical_output" / "memory_object_ledger.json"
    )
    object_ledger = _v3_7_object_ledger()
    normal_return = False
    exception_raised = False
    result: dict[str, Any] | None = None
    profile = None
    watchdog = None
    producer = None
    modal_amplitudes = None
    cfg = None
    modal_cfg = None
    side_checkpoint_path: Path | None = None
    if comm.rank == 0:
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_stream = marker_path.open("a", encoding="utf-8")
    _write_v3_7_object_ledger(object_ledger_path, object_ledger, comm)

    def marker_callback(marker: str, detail: Mapping[str, Any]) -> None:
        if comm.rank == 0:
            _record_v3_7_marker(object_ledger, marker, detail)
            _write_v3_7_object_ledger(
                object_ledger_path,
                object_ledger,
                comm,
                synchronize=False,
            )
        if marker_stream is None:
            return
        marker_stream.write(
            json.dumps(
                _json_safe(
                    {
                        "schema": "task039.v3-7-detail-marker.v1",
                        "stage": marker,
                        "marker": marker,
                        "elapsed_seconds": time.perf_counter() - marker_started,
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "worker_elapsed_seconds": time.perf_counter() - marker_started,
                        "elapsed_origin": "v3_7_worker_perf_counter_start",
                        "detail": {"v3_7_marker": marker, **dict(detail)},
                    }
                ),
                ensure_ascii=False,
            )
            + "\n"
        )
        marker_stream.flush()

    def combined_detail_callback(stage: str, detail: Mapping[str, Any]) -> None:
        if stage_callback is not None:
            stage_callback(stage, detail)
        marker_callback(stage, {"source": "setup_detail_callback", **dict(detail)})

    def attach_v10_finalizer_ledger(route_result: dict[str, Any]) -> None:
        route_result["telemetry"] = {
            "memory_object_ledger": {
                "path": "numerical_output/memory_object_ledger.json",
                "schema": "task039.v3-7-memory-object-ledger.v1",
                "status": "finalized_in_worker_finalizer",
            }
        }

    try:
        _emit_marker(marker_callback, "diagnostic_entry")
        if v5_h4_blr_side_only:
            v5_h4_blr_profile = _validate_v5_h4_blr_profile(v5_h4_blr_profile)
        profile = None
        if not (
            v5_h4_setup_only
            or v5_h4_blr_side_only
            or v5_h4_fixed_budget_bottom_only
            or v6_h4_post_compaction_setup_only
            or v7_h4_exact_side_limit_setup_only
            or v7_h4_full_formal
            or v6_h4_port_modal_bottom_only
            or v7_h4_streamed_bottom_producer
            or v7_h4_streamed_bottom_consumer
            or v8_h4_layer_block_reconstruction
            or v8_h4_layer_sweep_bottom
            or v9_h4_bare_f_side
            or v9_h4_layer_supernode_bottom
            or v10_h4_supernode_factor_integrity
            or v10_h4_sn2_j_only
            or v10_h4_j1_inner_fgmres
            or v10_h4_side_response_packet_pilot
            or v10_h4_side_response_packet_consumer
            or v10_h4_side_response_packet_full_producer
            or v10_h4_side_response_packet_compression
            or v11_h4_bottom_packet_algebra
        ):
            profile = (
                profile_override
                if profile_override is not None
                else v3_7_profile_from_resolved(resolved_payload)
            )
        if (
            v5_h4_setup_only
            or v5_h4_blr_side_only
            or v5_h4_fixed_budget_bottom_only
            or v6_h4_post_compaction_setup_only
            or v7_h4_exact_side_limit_setup_only
            or v7_h4_full_formal
            or v6_h4_port_modal_bottom_only
            or v7_h4_streamed_bottom_producer
            or v7_h4_streamed_bottom_consumer
            or v8_h4_layer_block_reconstruction
            or v8_h4_layer_sweep_bottom
            or v9_h4_bare_f_side
            or v9_h4_layer_supernode_bottom
            or v10_h4_supernode_factor_integrity
            or v10_h4_sn2_j_only
            or v10_h4_j1_inner_fgmres
            or v10_h4_side_response_packet_pilot
            or v10_h4_side_response_packet_consumer
            or v10_h4_side_response_packet_full_producer
            or v10_h4_side_response_packet_compression
            or v11_h4_bottom_packet_algebra
        ):
            incidence = resolved_payload["incidence"]
            if v7_h4_full_formal:
                route_profile_id = V7_H4_EXACT_SIDE_FULL_FORMAL_PROFILE_ID
                route_schema = V7_H4_EXACT_SIDE_FULL_FORMAL_SCHEMA
            elif v7_h4_exact_side_limit_setup_only:
                route_profile_id = V7_H4_EXACT_SIDE_LIMIT_PROFILE_ID
                route_schema = V7_H4_EXACT_SIDE_LIMIT_SCHEMA
            elif v6_h4_post_compaction_setup_only:
                route_profile_id = V6_H4_POST_COMPACTION_PROFILE_ID
                route_schema = V6_H4_POST_COMPACTION_PROFILE_ID
            elif v6_h4_port_modal_bottom_only:
                route_profile_id = V6_H4_PORT_MODAL_BOTTOM_PROFILE_ID
                route_schema = V6_H4_PORT_MODAL_BOTTOM_PROFILE_ID
            elif v7_h4_streamed_bottom_producer:
                route_profile_id = V7_STREAMED_PETROV_PROFILE_ID
                route_schema = V7_STREAMED_PETROV_SCHEMA
            elif v7_h4_streamed_bottom_consumer:
                route_profile_id = V7_STREAMED_PETROV_CONSUMER_PROFILE_ID
                route_schema = V7_STREAMED_PETROV_CONSUMER_SCHEMA
            elif v8_h4_layer_block_reconstruction:
                route_profile_id = V8_H4_LAYER_BLOCK_PROFILE_ID
                route_schema = V8_H4_LAYER_BLOCK_SCHEMA
            elif v8_h4_layer_sweep_bottom:
                route_profile_id = V8_H4_LAYER_SWEEP_PROFILE_ID
                route_schema = V8_H4_LAYER_SWEEP_SCHEMA
            elif v9_h4_bare_f_side:
                route_profile_id = V9_H4_BARE_F_SIDE_PROFILE_ID
                route_schema = V9_H4_BARE_F_SIDE_SCHEMA
            elif v9_h4_layer_supernode_bottom:
                route_profile_id = V9_H4_LAYER_SUPERNODE_PROFILE_ID
                route_schema = V9_H4_LAYER_SUPERNODE_SCHEMA
            elif v10_h4_supernode_factor_integrity:
                route_profile_id = V10_H4_SUPERNODE_FACTOR_INTEGRITY_PROFILE_ID
                route_schema = V10_H4_SUPERNODE_FACTOR_INTEGRITY_SCHEMA
            elif v10_h4_sn2_j_only:
                route_profile_id = V10_H4_SN2_J_ONLY_PROFILE_ID
                route_schema = V10_H4_SN2_J_ONLY_SCHEMA
            elif v10_h4_j1_inner_fgmres:
                route_profile_id = V10_H4_J1_INNER_FGMRES_PROFILE_ID
                route_schema = V10_H4_J1_INNER_FGMRES_SCHEMA
            elif v10_h4_side_response_packet_pilot:
                route_profile_id = V10_H4_SIDE_RESPONSE_PACKET_PILOT_PROFILE_ID
                route_schema = V10_H4_SIDE_RESPONSE_PACKET_PILOT_SCHEMA
            elif v10_h4_side_response_packet_consumer:
                route_profile_id = V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_PROFILE_ID
                route_schema = V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_SCHEMA
            elif v10_h4_side_response_packet_full_producer:
                route_profile_id = V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_PROFILE_ID
                route_schema = V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_SCHEMA
            elif v10_h4_side_response_packet_compression:
                route_profile_id = V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_PROFILE_ID
                route_schema = V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_SCHEMA
            elif v11_h4_bottom_packet_algebra:
                route_profile_id = V11_BOTTOM_PACKET_ALGEBRA_PROFILE_ID
                route_schema = V11_BOTTOM_PACKET_ALGEBRA_SCHEMA
            elif v5_h4_blr_side_only:
                route_profile_id = V5_H4_BLR_SIDE_PROFILE_ID
                route_schema = V5_H4_BLR_SIDE_PROFILE_ID
            elif v5_h4_setup_only:
                route_profile_id = "task039.v5.h4.exact-side.setup-only.v1"
                route_schema = route_profile_id
            else:
                route_profile_id = V5_H4_FIXED_BUDGET_SIDE_PROFILE_ID
                route_schema = route_profile_id
            profile = replace(
                make_task039_hybrid_iterative_profile(480, 8, mesh_target_nm=4.0),
                profile_id=route_profile_id,
                record_schema=route_schema,
                qualification_schema=route_schema,
                wavelength_nm=float(incidence["wavelength_nm"]),
                incident_grazing_deg=float(incidence["grazing_angle_deg"]),
                incident_phi_deg=float(incidence["azimuth_deg"]),
                polarization_kind=str(incidence["polarization"]).lower(),
                h_nm=4.0,
                modal_h_nm=4.0,
            )
        _emit_marker(
            marker_callback,
            "profile_ready",
            profile_id=profile.profile_id,
            mumps_blr_profile=(v5_h4_blr_profile if v5_h4_blr_side_only else None),
        )
        watchdog = v3_7_watchdog_policy(
            resolved_payload,
            v6_h4_post_compaction_setup_only=v6_h4_post_compaction_setup_only,
            v7_h4_exact_side_limit_setup_only=v7_h4_exact_side_limit_setup_only,
            v7_h4_exact_side_full_formal=v7_h4_full_formal,
            v6_h4_port_modal_bottom_only=v6_h4_port_modal_bottom_only,
            v7_h4_streamed_bottom_producer=v7_h4_streamed_bottom_producer,
            v7_h4_streamed_bottom_consumer=v7_h4_streamed_bottom_consumer,
            v8_h4_layer_block_reconstruction=v8_h4_layer_block_reconstruction,
            v8_h4_layer_sweep_bottom=v8_h4_layer_sweep_bottom,
            v9_h4_bare_f_side=v9_h4_bare_f_side,
            v9_h4_layer_supernode_bottom=v9_h4_layer_supernode_bottom,
            v10_h4_supernode_factor_integrity=v10_h4_supernode_factor_integrity,
            v10_h4_sn2_j_only=v10_h4_sn2_j_only,
            v10_h4_j1_inner_fgmres=v10_h4_j1_inner_fgmres,
            v10_h4_side_response_packet_pilot=v10_h4_side_response_packet_pilot,
            v10_h4_side_response_packet_consumer=v10_h4_side_response_packet_consumer,
            v10_h4_side_response_packet_full_producer=v10_h4_side_response_packet_full_producer,
            v10_h4_side_response_packet_compression=v10_h4_side_response_packet_compression,
            v11_h4_bottom_packet_algebra=v11_h4_bottom_packet_algebra,
        )
        _emit_marker(
            marker_callback,
            "watchdog_ready",
            absolute_terminate_memory_bytes=watchdog["absolute_terminate_memory_bytes"],
        )
        if (
            recovery_runner is None
            and not candidate_b_only
            and not candidate_c_only
            and not candidate_d_only
            and not candidate_d_qualified
            and not candidate_e_side_only
            and not v5_h4_setup_only
            and not v5_h4_blr_side_only
            and not v5_h4_fixed_budget_bottom_only
            and not v6_h4_post_compaction_setup_only
            and not v7_h4_exact_side_limit_setup_only
            and not v6_h4_port_modal_bottom_only
            and not v7_h4_streamed_bottom_producer
            and not v7_h4_streamed_bottom_consumer
            and not v8_h4_layer_block_reconstruction
            and not v8_h4_layer_sweep_bottom
            and not v9_h4_bare_f_side
            and not v9_h4_layer_supernode_bottom
            and not v10_h4_supernode_factor_integrity
            and not v10_h4_sn2_j_only
            and not v10_h4_j1_inner_fgmres
            and not v10_h4_side_response_packet_pilot
            and not v10_h4_side_response_packet_consumer
            and not v10_h4_side_response_packet_full_producer
            and not v10_h4_side_response_packet_compression
            and not v11_h4_bottom_packet_algebra
        ):
            raise ValueError(
                "V3-7 requires an injected recovery_runner(setup, layout, snapshot, "
                "run_dir, producer)"
            )
        if (
            v5_h4_setup_only
            or v6_h4_post_compaction_setup_only
            or v7_h4_exact_side_limit_setup_only
            or v7_h4_full_formal
        ):
            if (
                selected_mode_packet_manifest is None
                or selected_mode_packet_identity is None
                or selected_mode_packet_manifest_sha256 is None
            ):
                raise ValueError("V5 h4 setup-only requires the shared packet identity")
            if v6_h4_post_compaction_setup_only and v6_h4_exact_spool_root is None:
                raise ValueError("V6 setup requires the exact-response spool root")
            if (
                v7_h4_exact_side_limit_setup_only
                and v7_h4_exact_side_exact_spool_root is None
            ):
                raise ValueError("V7 setup requires the exact-response spool root")
            if v7_h4_full_formal and v7_h4_exact_side_exact_spool_root is None:
                raise ValueError(
                    "V7 full formal requires the exact-response spool root"
                )
            producer = {
                "producer_source_sha": selected_mode_packet_identity.get("source_sha"),
                "physical_model_sha256": selected_mode_packet_identity.get(
                    "physical_sha256"
                ),
                "model_id": selected_mode_packet_identity.get("model_id"),
                "requested_modes": 480,
                "mpi_size": 8,
                "external_keys_exact": True,
                "selected_mode_packet": True,
                "v6_post_compaction": bool(v6_h4_post_compaction_setup_only),
                "v7_exact_side_limit_setup": bool(v7_h4_exact_side_limit_setup_only),
                "v7_exact_side_full_formal": bool(v7_h4_full_formal),
            }
            if v7_h4_full_formal:
                producer.update(
                    {
                        "consumer_source_sha": source_sha,
                        "consumer_model_id": resolved_payload["model_id"],
                        "qualification_scope": TASK039_V4_H4_CASE_QUALIFICATION_SCOPE,
                        "qualification_method": TASK039_V4_H4_QUALIFICATION_METHOD,
                        "direct_reference_payload_loaded": False,
                        "_hybrid_direct_authority_run_directory": Path(
                            "results/task039_v4_h4_hybrid_direct_formal_mpi8_icntl14_1515f095"
                        ),
                        "_full3d_authority_run_directory": None,
                    }
                )
            modal_amplitudes = None
        elif v10_h4_side_response_packet_compression:
            if (
                v10_h4_side_response_packet_compression_manifest is None
                or v10_h4_side_response_packet_compression_manifest_sha256 is None
                or v10_h4_side_response_packet_compression_producer_source_sha is None
            ):
                raise ValueError(
                    "V10 compression requires packet manifest, hash, and producer source SHA"
                )
            v10_input_sha256, v10_physical_model_sha256 = (
                _v10_side_response_resolved_provenance(resolved_payload)
            )
            producer = {
                "producer_source_sha": (
                    v10_h4_side_response_packet_compression_producer_source_sha
                ),
                "consumer_source_sha": source_sha,
                "input_sha256": v10_input_sha256,
                "physical_model_sha256": v10_physical_model_sha256,
                "model_id": resolved_payload.get("model_id"),
                "requested_modes": 480,
                "mpi_size": 8,
                "selected_mode_packet_opened": False,
                "holdout_opened": False,
                "exact_spool_opened": False,
                "qep_count": 0,
                "sgs_executed": False,
                "consumer_factor_count": 0,
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
                "component_candidate": True,
                "research_only": True,
                "response_packet_manifest": str(
                    Path(v10_h4_side_response_packet_compression_manifest).resolve()
                ),
                "response_packet_manifest_sha256": (
                    v10_h4_side_response_packet_compression_manifest_sha256
                ),
            }
            modal_amplitudes = None
        elif v11_h4_bottom_packet_algebra:
            if not all(
                (
                    v11_h4_bottom_packet_algebra_exact_spool_root,
                    v11_h4_bottom_packet_algebra_packet_manifest,
                    v11_h4_bottom_packet_algebra_packet_manifest_sha256,
                    v11_h4_bottom_packet_algebra_producer_diagnostic,
                )
            ):
                raise ValueError("V11 bottom algebra requires frozen artifact paths")
            producer = {
                "producer_source_sha": V11_RESPONSE_PACKET_PRODUCER_SOURCE_SHA,
                "consumer_source_sha": source_sha,
                "component_candidate": True,
                "research_only": True,
                "pde_solve": "not_run",
            }
            modal_amplitudes = None
        elif v8_h4_layer_sweep_bottom:
            if (
                selected_mode_packet_manifest is None
                or selected_mode_packet_identity is None
                or selected_mode_packet_manifest_sha256 is None
                or v8_h4_layer_sweep_exact_spool_root is None
            ):
                raise ValueError(
                    "V8 layer sweep requires packet identity and exact spool"
                )
            producer = {
                "producer_source_sha": selected_mode_packet_identity.get("source_sha"),
                "physical_model_sha256": selected_mode_packet_identity.get(
                    "physical_sha256"
                ),
                "model_id": selected_mode_packet_identity.get("model_id"),
                "requested_modes": 480,
                "mpi_size": 8,
                "external_keys_exact": True,
                "selected_mode_packet": False,
                "selected_mode_packet_opened": False,
                "holdout_opened": True,
                "exact_spool_opened": True,
                "direct_reference_payload_loaded": False,
                "consumer_qep_calls": 0,
                "exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
                "layer_factor_count": 6,
                "component_candidate": True,
                "research_only": True,
                "exact_spool_root": str(
                    Path(v8_h4_layer_sweep_exact_spool_root).resolve()
                ),
            }
            modal_amplitudes = None
        elif v10_h4_sn2_j_only:
            if v10_h4_sn2_j_only_exact_spool_root is None:
                raise ValueError("V10 SN2-J-only route requires the exact spool root")
            producer = {
                "producer_source_sha": None,
                "consumer_source_sha": source_sha,
                "physical_model_sha256": resolved_payload.get("physical_model_sha256"),
                "model_id": resolved_payload.get("model_id"),
                "requested_modes": 480,
                "mpi_size": 8,
                "selected_mode_packet": False,
                "selected_mode_packet_opened": False,
                "holdout_opened": True,
                "exact_spool_opened": True,
                "direct_reference_payload_loaded": False,
                "qep_count": 0,
                "sgs_executed": False,
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
                "supernode_factor_count": 3,
                "component_candidate": True,
                "research_only": True,
                "exact_spool_root": str(
                    Path(v10_h4_sn2_j_only_exact_spool_root).resolve()
                ),
            }
            modal_amplitudes = None
        elif v10_h4_j1_inner_fgmres:
            if v10_h4_j1_inner_fgmres_exact_spool_root is None:
                raise ValueError("V10-4 route requires the exact spool root")
            producer = {
                "producer_source_sha": None,
                "consumer_source_sha": source_sha,
                "physical_model_sha256": resolved_payload.get("physical_model_sha256"),
                "model_id": resolved_payload.get("model_id"),
                "requested_modes": 480,
                "mpi_size": 8,
                "selected_mode_packet": False,
                "selected_mode_packet_opened": False,
                "holdout_opened": True,
                "exact_spool_opened": True,
                "direct_reference_payload_loaded": False,
                "qep_count": 0,
                "sgs_executed": False,
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
                "layer_factor_count": 6,
                "side_fgmres_ksp_count": 5,
                "component_candidate": True,
                "research_only": True,
                "exact_spool_root": str(
                    Path(v10_h4_j1_inner_fgmres_exact_spool_root).resolve()
                ),
            }
            modal_amplitudes = None
        elif v10_h4_side_response_packet_full_producer:
            if (
                v10_h4_side_response_packet_full_producer_exact_spool_root is None
                or v10_h4_side_response_packet_full_producer_output_root is None
                or selected_mode_packet_manifest is None
                or selected_mode_packet_identity is None
                or selected_mode_packet_manifest_sha256 is None
            ):
                raise ValueError(
                    "V10 full producer requires selected packet, exact spool, and output"
                )
            v10_input_sha256, v10_physical_model_sha256 = (
                _v10_side_response_resolved_provenance(resolved_payload)
            )
            producer = {
                "producer_source_sha": selected_mode_packet_identity.get("source_sha"),
                "consumer_source_sha": source_sha,
                "input_sha256": v10_input_sha256,
                "physical_model_sha256": v10_physical_model_sha256,
                "model_id": resolved_payload.get("model_id"),
                "requested_modes": 480,
                "mpi_size": 8,
                "selected_mode_packet_opened": True,
                "holdout_opened": True,
                "exact_spool_opened": True,
                "qep_count": 0,
                "sgs_executed": False,
                "exact_side_factor_count_ready": 1,
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
                "component_candidate": True,
                "research_only": True,
                "full_response_packet": True,
                "exact_spool_root": str(
                    Path(
                        v10_h4_side_response_packet_full_producer_exact_spool_root
                    ).resolve()
                ),
                "response_packet_output_root": str(
                    Path(
                        v10_h4_side_response_packet_full_producer_output_root
                    ).resolve()
                ),
            }
            modal_amplitudes = None
        elif v10_h4_side_response_packet_pilot:
            if (
                v10_h4_side_response_packet_pilot_exact_spool_root is None
                or v10_h4_side_response_packet_pilot_output_root is None
                or selected_mode_packet_manifest is None
                or selected_mode_packet_identity is None
                or selected_mode_packet_manifest_sha256 is None
            ):
                raise ValueError(
                    "V10-6 producer requires selected packet, exact spool, and output"
                )
            v10_input_sha256, v10_physical_model_sha256 = (
                _v10_side_response_resolved_provenance(resolved_payload)
            )
            producer = {
                "producer_source_sha": selected_mode_packet_identity.get("source_sha"),
                "consumer_source_sha": source_sha,
                "input_sha256": v10_input_sha256,
                "physical_model_sha256": v10_physical_model_sha256,
                "model_id": resolved_payload.get("model_id"),
                "requested_modes": 480,
                "mpi_size": 8,
                "selected_mode_packet_opened": True,
                "holdout_opened": True,
                "exact_spool_opened": True,
                "qep_count": 0,
                "sgs_executed": False,
                "exact_side_factor_count_ready": 1,
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
                "component_candidate": True,
                "research_only": True,
                "exact_spool_root": str(
                    Path(v10_h4_side_response_packet_pilot_exact_spool_root).resolve()
                ),
                "response_packet_output_root": str(
                    Path(v10_h4_side_response_packet_pilot_output_root).resolve()
                ),
            }
            modal_amplitudes = None
        elif v10_h4_side_response_packet_consumer:
            if (
                v10_h4_side_response_packet_consumer_manifest is None
                or v10_h4_side_response_packet_consumer_manifest_sha256 is None
            ):
                raise ValueError("V10-6 consumer requires packet manifest and hash")
            v10_input_sha256, v10_physical_model_sha256 = (
                _v10_side_response_resolved_provenance(resolved_payload)
            )
            producer = {
                "producer_source_sha": None,
                "consumer_source_sha": source_sha,
                "input_sha256": v10_input_sha256,
                "physical_model_sha256": v10_physical_model_sha256,
                "model_id": resolved_payload.get("model_id"),
                "requested_modes": 480,
                "mpi_size": 8,
                "selected_mode_packet_opened": False,
                "holdout_opened": False,
                "exact_spool_opened": False,
                "qep_count": 0,
                "sgs_executed": False,
                "consumer_factor_count": 0,
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
                "component_candidate": True,
                "research_only": True,
                "response_packet_manifest": str(
                    Path(v10_h4_side_response_packet_consumer_manifest).resolve()
                ),
                "response_packet_manifest_sha256": v10_h4_side_response_packet_consumer_manifest_sha256,
            }
            modal_amplitudes = None
        elif v9_h4_bare_f_side:
            if v9_h4_bare_f_side_exact_spool_root is None:
                raise ValueError("V9 bare-F route requires the exact spool root")
            producer = {
                "producer_source_sha": None,
                "consumer_source_sha": source_sha,
                "physical_model_sha256": resolved_payload.get("physical_model_sha256"),
                "model_id": resolved_payload.get("model_id"),
                "requested_modes": 480,
                "mpi_size": 8,
                "selected_mode_packet_opened": False,
                "holdout_opened": False,
                "exact_spool_opened": False,
                "direct_reference_payload_loaded": False,
                "consumer_qep_calls": 0,
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
                "component_candidate": True,
                "research_only": True,
                "exact_spool_root": str(
                    Path(v9_h4_bare_f_side_exact_spool_root).resolve()
                ),
            }
            modal_amplitudes = None
        elif v9_h4_layer_supernode_bottom:
            if v9_h4_layer_supernode_exact_spool_root is None:
                raise ValueError("V9-2 supernode route requires the exact spool root")
            producer = {
                "producer_source_sha": None,
                "consumer_source_sha": source_sha,
                "physical_model_sha256": resolved_payload.get("physical_model_sha256"),
                "model_id": resolved_payload.get("model_id"),
                "requested_modes": 480,
                "mpi_size": 8,
                "selected_mode_packet_opened": False,
                "holdout_opened": True,
                "exact_spool_opened": True,
                "direct_reference_payload_loaded": False,
                "selected_mode_packet": False,
                "qep_count": 0,
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
                "supernode_factor_count": 3,
                "component_candidate": True,
                "research_only": True,
                "exact_spool_root": str(
                    Path(v9_h4_layer_supernode_exact_spool_root).resolve()
                ),
            }
            modal_amplitudes = None
        elif v10_h4_supernode_factor_integrity:
            if v10_h4_supernode_factor_integrity_exact_spool_root is None:
                raise ValueError("V10 forensic route requires the exact spool root")
            producer = {
                "producer_source_sha": None,
                "consumer_source_sha": source_sha,
                "physical_model_sha256": resolved_payload.get("physical_model_sha256"),
                "model_id": resolved_payload.get("model_id"),
                "requested_modes": 480,
                "mpi_size": 8,
                "selected_mode_packet": False,
                "selected_mode_packet_opened": False,
                "holdout_opened": True,
                "exact_spool_opened": True,
                "direct_reference_payload_loaded": False,
                "qep_count": 0,
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
                "sgs_executed": False,
                "component_candidate": True,
                "research_only": True,
                "exact_spool_root": str(
                    Path(v10_h4_supernode_factor_integrity_exact_spool_root).resolve()
                ),
            }
            modal_amplitudes = None
        elif v8_h4_layer_block_reconstruction:
            producer = {
                "producer_source_sha": source_sha,
                "physical_model_sha256": resolved_payload.get("physical_model_sha256"),
                "model_id": resolved_payload.get("model_id"),
                "requested_modes": 480,
                "mpi_size": 8,
                "external_keys_exact": True,
                "selected_mode_packet": False,
                "selected_mode_packet_opened": False,
                "holdout_opened": False,
                "exact_spool_opened": False,
                "direct_reference_payload_loaded": False,
                "consumer_qep_calls": 0,
                "exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
                "research_only": True,
                "component_candidate": True,
            }
            modal_amplitudes = None
        elif v7_h4_streamed_bottom_producer:
            if (
                selected_mode_packet_manifest is None
                or selected_mode_packet_identity is None
                or selected_mode_packet_manifest_sha256 is None
            ):
                raise ValueError(
                    "V7 streamed producer requires the shared packet identity"
                )
            producer = {
                "producer_source_sha": selected_mode_packet_identity.get("source_sha"),
                "physical_model_sha256": selected_mode_packet_identity.get(
                    "physical_sha256"
                ),
                "model_id": selected_mode_packet_identity.get("model_id"),
                "requested_modes": 480,
                "mpi_size": 8,
                "external_keys_exact": True,
                "selected_mode_packet": True,
                "consumer_qep_calls": 0,
                "packet_arrays_hydrated": False,
                "exact_spool_opened": False,
                "holdout_opened": False,
                "direct_reference_payload_loaded": False,
                "component_candidate": True,
                "research_only": True,
                "general_production": False,
                "source_schedule_identity": V7_STREAMED_PETROV_SOURCE_SCHEDULE_IDENTITY,
                "batch_size": V7_STREAMED_PETROV_BATCH_SIZE,
                "exact_factor_count": 0,
                "global_direct_factor_count": 0,
            }
            modal_amplitudes = None
        elif v7_h4_streamed_bottom_consumer:
            if not all(
                (
                    selected_mode_packet_manifest,
                    selected_mode_packet_identity,
                    selected_mode_packet_manifest_sha256,
                    v7_h4_streamed_bottom_consumer_basis_manifest,
                    v7_h4_streamed_bottom_consumer_basis_manifest_sha256,
                    v7_h4_streamed_bottom_consumer_exact_spool_root,
                )
            ):
                raise ValueError(
                    "V7 streamed consumer requires packet, basis, and exact spool"
                )
            producer = {
                "producer_source_sha": selected_mode_packet_identity.get("source_sha"),
                "physical_model_sha256": selected_mode_packet_identity.get(
                    "physical_sha256"
                ),
                "model_id": selected_mode_packet_identity.get("model_id"),
                "requested_modes": 480,
                "mpi_size": 8,
                "external_keys_exact": True,
                "selected_mode_packet": False,
                "basis_packet_manifest": str(
                    Path(v7_h4_streamed_bottom_consumer_basis_manifest).resolve()
                ),
                "basis_packet_manifest_sha256": (
                    v7_h4_streamed_bottom_consumer_basis_manifest_sha256
                ),
                "consumer_qep_calls": 0,
                "packet_arrays_hydrated": False,
                "direct_reference_payload_loaded": False,
                "exact_spool_opened": False,
                "holdout_opened": False,
                "component_candidate": True,
                "research_only": True,
                "general_production": False,
                "source_schedule_identity": V7_STREAMED_PETROV_SOURCE_SCHEDULE_IDENTITY,
                "batch_size": V7_STREAMED_PETROV_BATCH_SIZE,
                "exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
                "exact_spool_root": str(
                    Path(v7_h4_streamed_bottom_consumer_exact_spool_root).resolve()
                ),
            }
            modal_amplitudes = None
        elif v6_h4_port_modal_bottom_only:
            if (
                selected_mode_packet_manifest is None
                or selected_mode_packet_identity is None
                or selected_mode_packet_manifest_sha256 is None
                or v6_h4_port_modal_exact_spool_root is None
            ):
                raise ValueError(
                    "V6 port-modal component requires packet identity and exact spool"
                )
            producer = {
                "producer_source_sha": selected_mode_packet_identity.get("source_sha"),
                "physical_model_sha256": selected_mode_packet_identity.get(
                    "physical_sha256"
                ),
                "model_id": selected_mode_packet_identity.get("model_id"),
                "requested_modes": 480,
                "mpi_size": 8,
                "external_keys_exact": True,
                "selected_mode_packet": True,
                "consumer_qep_calls": 0,
                "packet_arrays_hydrated": False,
                "direct_reference_payload_loaded": False,
                "component_candidate": True,
                "research_only": True,
                "exact_spool_root": str(Path(v6_h4_port_modal_exact_spool_root)),
            }
            modal_amplitudes = None
        elif v5_h4_blr_side_only:
            if (
                selected_mode_packet_manifest is None
                or selected_mode_packet_identity is None
                or selected_mode_packet_manifest_sha256 is None
            ):
                raise ValueError(
                    "V5 h4 BLR side component requires the shared packet identity"
                )
            producer = {
                "producer_source_sha": selected_mode_packet_identity.get("source_sha"),
                "physical_model_sha256": selected_mode_packet_identity.get(
                    "physical_sha256"
                ),
                "model_id": selected_mode_packet_identity.get("model_id"),
                "requested_modes": 480,
                "mpi_size": 8,
                "external_keys_exact": True,
                "selected_mode_packet": True,
                "consumer_qep_calls": 0,
                "component_candidate": True,
            }
            modal_amplitudes = None
        elif v5_h4_fixed_budget_bottom_only:
            if (
                selected_mode_packet_manifest is None
                or selected_mode_packet_identity is None
                or selected_mode_packet_manifest_sha256 is None
                or v5_h4_fixed_budget_exact_spool_root is None
            ):
                raise ValueError(
                    "V5 fixed-budget component requires packet identity and exact spool"
                )
            producer = {
                "producer_source_sha": selected_mode_packet_identity.get("source_sha"),
                "physical_model_sha256": selected_mode_packet_identity.get(
                    "physical_sha256"
                ),
                "model_id": selected_mode_packet_identity.get("model_id"),
                "requested_modes": 480,
                "mpi_size": 8,
                "external_keys_exact": True,
                "selected_mode_packet": True,
                "consumer_qep_calls": 0,
                "component_candidate": True,
                "fixed_budget": V5_H4_FIXED_BUDGET,
                "exact_spool_root": str(Path(v5_h4_fixed_budget_exact_spool_root)),
            }
            modal_amplitudes = None
        elif candidate_d_only or candidate_d_qualified:
            producer = _candidate_d_producer_metadata(
                resolved_payload, source_sha, marker_callback
            )
            if producer_metadata is not None:
                producer.update(dict(producer_metadata))
            modal_amplitudes = None
        else:
            producer, modal_amplitudes = inventory_loader(
                resolved_payload,
                direct_run_dir,
            )
            producer["consumer_source_sha"] = source_sha
        _emit_marker(
            marker_callback,
            "inventory_ready",
            producer_source_sha=producer.get("producer_source_sha"),
            direct_reference_payload_loaded=bool(
                producer.get("direct_reference_payload_loaded", True)
            ),
        )
        if v10_h4_side_response_packet_compression:
            v10_input_sha256, v10_physical_model_sha256 = (
                _v10_side_response_resolved_provenance(resolved_payload)
            )
            result = run_v10_h4_side_response_packet_compression(
                manifest_path=v10_h4_side_response_packet_compression_manifest,
                manifest_sha256=v10_h4_side_response_packet_compression_manifest_sha256,
                source_sha=source_sha,
                expected_producer_source_sha=(
                    v10_h4_side_response_packet_compression_producer_source_sha
                ),
                input_sha256=v10_input_sha256,
                physical_model_sha256=v10_physical_model_sha256,
                comm=comm,
                marker_callback=marker_callback,
            )
            attach_v10_finalizer_ledger(result)
            result["run_directory"] = str(Path(run_directory).resolve())
            normal_return = result.get("status") == "compression_completed"
            return result
        cfg = simulation_config_3d_from_normalized(resolved_payload)
        modal_cfg = deepcopy(cfg)
        _emit_marker(marker_callback, "config_ready")
        producer["_stage_callback"] = marker_callback
        _emit_marker(marker_callback, "setup_begin")
        if v10_h4_supernode_factor_integrity:
            result = run_v10_h4_supernode_factor_integrity(
                cfg,
                profile=profile,
                comm=comm,
                marker_callback=marker_callback,
                exact_spool_root=v10_h4_supernode_factor_integrity_exact_spool_root,
                source_sha=source_sha,
                side_system_builder=side_system_builder,
            )
            result["source_sha"] = source_sha
            result["consumer_source_sha"] = source_sha
            result["run_directory"] = str(Path(run_directory).resolve())
            normal_return = result.get("status") == "component_forensic_completed"
            return result
        if v10_h4_sn2_j_only:
            result = run_v10_h4_sn2_j_only(
                cfg,
                profile=profile,
                comm=comm,
                marker_callback=marker_callback,
                exact_spool_root=v10_h4_sn2_j_only_exact_spool_root,
                source_sha=source_sha,
                side_system_builder=side_system_builder,
            )
            result["source_sha"] = source_sha
            result["consumer_source_sha"] = source_sha
            result["run_directory"] = str(Path(run_directory).resolve())
            normal_return = result.get("status") == (
                "component_sn2_j_stable_resource_pending"
            )
            return result
        if v10_h4_j1_inner_fgmres:
            result = run_v10_h4_j1_inner_fgmres(
                cfg,
                profile=profile,
                comm=comm,
                marker_callback=marker_callback,
                exact_spool_root=v10_h4_j1_inner_fgmres_exact_spool_root,
                source_sha=source_sha,
                side_system_builder=side_system_builder,
            )
            result["source_sha"] = source_sha
            result["consumer_source_sha"] = source_sha
            result["run_directory"] = str(Path(run_directory).resolve())
            normal_return = result.get("status") == "component_fgmres_completed"
            return result
        if v11_h4_bottom_packet_algebra:
            result = run_v11_h4_bottom_packet_algebra(
                cfg,
                profile=profile,
                comm=comm,
                marker_callback=marker_callback,
                packet_manifest=v11_h4_bottom_packet_algebra_packet_manifest,
                packet_manifest_sha256=(
                    v11_h4_bottom_packet_algebra_packet_manifest_sha256
                ),
                selected_mode_packet_manifest=selected_mode_packet_manifest,
                selected_mode_packet_manifest_sha256=selected_mode_packet_manifest_sha256,
                producer_diagnostic_path=v11_h4_bottom_packet_algebra_producer_diagnostic,
                exact_spool_root=v11_h4_bottom_packet_algebra_exact_spool_root,
                side_system_builder=side_system_builder,
            )
            result["source_sha"] = source_sha
            result["schema"] = V11_BOTTOM_PACKET_ALGEBRA_SCHEMA
            result["checker_method"] = result.get("method")
            result["method"] = V11_BOTTOM_PACKET_ALGEBRA_METHOD
            result["run_directory"] = str(Path(run_directory).resolve())
            result["status"] = (
                "component_v11_bottom_packet_algebra_completed"
                if result.get("gate", {}).get("pass") is True
                else "component_v11_bottom_packet_algebra_failed"
            )
            attach_v10_finalizer_ledger(result)
            normal_return = result["status"] == (
                "component_v11_bottom_packet_algebra_completed"
            )
            return result
        if v10_h4_side_response_packet_full_producer:
            v10_input_sha256, v10_physical_model_sha256 = (
                _v10_side_response_resolved_provenance(resolved_payload)
            )
            result = run_v10_h4_side_response_packet_pilot(
                cfg,
                profile=profile,
                comm=comm,
                marker_callback=marker_callback,
                exact_spool_root=(
                    v10_h4_side_response_packet_full_producer_exact_spool_root
                ),
                source_sha=source_sha,
                output_root=v10_h4_side_response_packet_full_producer_output_root,
                selected_mode_packet_manifest=selected_mode_packet_manifest,
                selected_mode_packet_identity=selected_mode_packet_identity,
                selected_mode_packet_manifest_sha256=selected_mode_packet_manifest_sha256,
                input_sha256=v10_input_sha256,
                physical_model_sha256=v10_physical_model_sha256,
                side_system_builder=side_system_builder,
                full_response=True,
            )
            attach_v10_finalizer_ledger(result)
            result["source_sha"] = source_sha
            result["run_directory"] = str(Path(run_directory).resolve())
            normal_return = result.get("status") == "producer_completed"
            return result
        if v10_h4_side_response_packet_pilot:
            v10_input_sha256, v10_physical_model_sha256 = (
                _v10_side_response_resolved_provenance(resolved_payload)
            )
            result = run_v10_h4_side_response_packet_pilot(
                cfg,
                profile=profile,
                comm=comm,
                marker_callback=marker_callback,
                exact_spool_root=v10_h4_side_response_packet_pilot_exact_spool_root,
                source_sha=source_sha,
                output_root=v10_h4_side_response_packet_pilot_output_root,
                selected_mode_packet_manifest=selected_mode_packet_manifest,
                selected_mode_packet_identity=selected_mode_packet_identity,
                selected_mode_packet_manifest_sha256=selected_mode_packet_manifest_sha256,
                input_sha256=v10_input_sha256,
                physical_model_sha256=v10_physical_model_sha256,
                side_system_builder=side_system_builder,
            )
            attach_v10_finalizer_ledger(result)
            result["source_sha"] = source_sha
            result["run_directory"] = str(Path(run_directory).resolve())
            normal_return = result.get("status") == "producer_completed"
            return result
        if v10_h4_side_response_packet_consumer:
            v10_input_sha256, v10_physical_model_sha256 = (
                _v10_side_response_resolved_provenance(resolved_payload)
            )
            manifest_path = Path(v10_h4_side_response_packet_consumer_manifest)
            manifest_bytes = manifest_path.read_bytes()
            if hashlib.sha256(manifest_bytes).hexdigest() != str(
                v10_h4_side_response_packet_consumer_manifest_sha256
            ):
                raise ValueError("V10-6 consumer manifest hash mismatch")
            packet_manifest = json.loads(manifest_bytes.decode("utf-8"))
            shard = next(
                (
                    item
                    for item in packet_manifest.get("shards", ())
                    if int(item.get("rank", -1)) == int(comm.rank)
                ),
                None,
            )
            if not isinstance(shard, Mapping):
                raise ValueError("V10-6 consumer manifest has no rank shard")
            result = run_v10_h4_side_response_packet_consumer(
                manifest_path=manifest_path,
                manifest_sha256=v10_h4_side_response_packet_consumer_manifest_sha256,
                source_sha=source_sha,
                input_sha256=v10_input_sha256,
                physical_model_sha256=v10_physical_model_sha256,
                global_rows=int(packet_manifest["global_rows"]),
                ownership_range=tuple(int(value) for value in shard["ownership_range"]),
                comm=comm,
                marker_callback=marker_callback,
            )
            attach_v10_finalizer_ledger(result)
            result["source_sha"] = source_sha
            result["run_directory"] = str(Path(run_directory).resolve())
            normal_return = result.get("status") == "consumer_completed"
            return result
        if v9_h4_layer_supernode_bottom:
            result = run_v9_h4_layer_supernode_bottom_component(
                cfg,
                profile=profile,
                comm=comm,
                marker_callback=marker_callback,
                exact_spool_root=v9_h4_layer_supernode_exact_spool_root,
                source_sha=source_sha,
                side_system_builder=side_system_builder,
            )
            result["source_sha"] = source_sha
            result["consumer_source_sha"] = source_sha
            result["run_directory"] = str(Path(run_directory).resolve())
            normal_return = result.get("status") == (
                "component_stable_preferred_resource_pending"
            )
            return result
        if v9_h4_bare_f_side:
            result = run_v9_h4_bare_f_side_diagnostic(
                cfg,
                profile=profile,
                comm=comm,
                marker_callback=marker_callback,
                exact_spool_root=v9_h4_bare_f_side_exact_spool_root,
                side_system_builder=side_system_builder,
            )
            result["source_sha"] = source_sha
            result["consumer_source_sha"] = source_sha
            result["producer_source_sha"] = result["holdout_provenance"][
                "catalog_authority"
            ]["producer_source_sha"]
            result["run_directory"] = str(Path(run_directory).resolve())
            normal_return = result.get("status") == "component_diagnostic_completed"
            return result
        if v8_h4_layer_sweep_bottom:
            result = run_v8_h4_layer_sweep_bottom_component(
                cfg,
                profile=profile,
                comm=comm,
                marker_callback=marker_callback,
                exact_spool_root=v8_h4_layer_sweep_exact_spool_root,
                packet_identity=selected_mode_packet_identity,
                packet_manifest_sha256=selected_mode_packet_manifest_sha256,
                side_system_builder=side_system_builder,
            )
            result["source_sha"] = source_sha
            result["run_directory"] = str(Path(run_directory).resolve())
            normal_return = result.get("status") == (
                "component_numerical_pass_resource_pending"
            )
            return result
        if v8_h4_layer_block_reconstruction:
            result = run_v8_h4_layer_block_reconstruction_component(
                cfg,
                profile=profile,
                comm=comm,
                marker_callback=marker_callback,
                side_system_builder=side_system_builder,
            )
            result["source_sha"] = source_sha
            result["run_directory"] = str(Path(run_directory).resolve())
            normal_return = result.get("status") == "component_completed"
            return result
        if v5_h4_fixed_budget_bottom_only:
            packet_contract = _validate_v5_fixed_budget_packet_manifest(
                selected_mode_packet_manifest,
                selected_mode_packet_identity,
                selected_mode_packet_manifest_sha256,
                comm=comm,
            )
            builder = (
                side_system_builder
                if side_system_builder is not None
                else _build_v5_h4_fixed_budget_bottom_side_setup
            )
            setup = builder(
                cfg=cfg,
                profile=profile,
                comm=comm,
                detail_stage_callback=combined_detail_callback,
            )
            if not getattr(setup, "side_only", False) or not hasattr(setup, "bottom"):
                raise ValueError(
                    "Fixed-budget side builder did not return a bottom-only carrier"
                )
            object_ledger["objects"]["setup"]["created"] = True
            object_ledger["objects"]["setup"]["status"] = "measured"
            result = run_v5_h4_fixed_budget_bottom_component(
                setup,
                comm=comm,
                marker_callback=marker_callback,
                exact_spool_root=v5_h4_fixed_budget_exact_spool_root,
                packet_identity=selected_mode_packet_identity,
                packet_manifest_sha256=selected_mode_packet_manifest_sha256,
            )
            result["source_sha"] = source_sha
            result["run_directory"] = str(Path(run_directory).resolve())
            result["packet"] = {
                **packet_contract,
                "manifest": str(selected_mode_packet_manifest),
            }
            normal_return = True
            return result

        if v6_h4_port_modal_bottom_only:
            packet_contract = _validate_v5_fixed_budget_packet_manifest(
                selected_mode_packet_manifest,
                selected_mode_packet_identity,
                selected_mode_packet_manifest_sha256,
                comm=comm,
            )
            builder = (
                side_system_builder
                if side_system_builder is not None
                else _build_v5_h4_fixed_budget_bottom_side_setup
            )
            setup = builder(
                cfg=cfg,
                profile=profile,
                comm=comm,
                detail_stage_callback=combined_detail_callback,
            )
            if not getattr(setup, "side_only", False) or not hasattr(setup, "bottom"):
                raise ValueError(
                    "V6 port-modal builder did not return a bottom-only carrier"
                )
            object_ledger["objects"]["setup"]["created"] = True
            object_ledger["objects"]["setup"]["status"] = "measured"
            result = run_v6_h4_port_modal_bottom_component(
                setup,
                comm=comm,
                marker_callback=marker_callback,
                exact_spool_root=v6_h4_port_modal_exact_spool_root,
                packet_manifest=selected_mode_packet_manifest,
                packet_identity=selected_mode_packet_identity,
                packet_manifest_sha256=selected_mode_packet_manifest_sha256,
            )
            result["source_sha"] = source_sha
            result["run_directory"] = str(Path(run_directory).resolve())
            result["packet"] = {
                **packet_contract,
                "manifest": str(selected_mode_packet_manifest),
            }
            normal_return = True
            return result

        if v7_h4_streamed_bottom_consumer:
            packet_contract = _validate_v5_fixed_budget_packet_manifest(
                selected_mode_packet_manifest,
                selected_mode_packet_identity,
                selected_mode_packet_manifest_sha256,
                comm=comm,
            )
            builder = (
                side_system_builder
                if side_system_builder is not None
                else _build_v5_h4_fixed_budget_bottom_side_setup
            )
            setup = builder(
                cfg=cfg,
                profile=profile,
                comm=comm,
                detail_stage_callback=combined_detail_callback,
            )
            if not getattr(setup, "side_only", False) or not hasattr(setup, "bottom"):
                raise ValueError(
                    "V7 streamed consumer builder did not return a bottom-only carrier"
                )
            object_ledger["objects"]["setup"]["created"] = True
            object_ledger["objects"]["setup"]["status"] = "measured"
            result = run_v7_h4_streamed_bottom_petrov_consumer(
                setup,
                comm=comm,
                marker_callback=marker_callback,
                basis_manifest=v7_h4_streamed_bottom_consumer_basis_manifest,
                basis_manifest_sha256=(
                    v7_h4_streamed_bottom_consumer_basis_manifest_sha256
                ),
                exact_spool_root=v7_h4_streamed_bottom_consumer_exact_spool_root,
                packet_identity=selected_mode_packet_identity,
                packet_manifest_sha256=selected_mode_packet_manifest_sha256,
            )
            result["source_sha"] = source_sha
            result["run_directory"] = str(Path(run_directory).resolve())
            result["selected_mode_packet"] = {
                **packet_contract,
                "manifest": str(selected_mode_packet_manifest),
            }
            normal_return = True
            return result

        if v7_h4_streamed_bottom_producer:
            packet_contract = _validate_v5_fixed_budget_packet_manifest(
                selected_mode_packet_manifest,
                selected_mode_packet_identity,
                selected_mode_packet_manifest_sha256,
                comm=comm,
            )
            builder = (
                side_system_builder
                if side_system_builder is not None
                else _build_v5_h4_fixed_budget_bottom_side_setup
            )
            setup = builder(
                cfg=cfg,
                profile=profile,
                comm=comm,
                detail_stage_callback=combined_detail_callback,
            )
            if not getattr(setup, "side_only", False) or not hasattr(setup, "bottom"):
                raise ValueError(
                    "V7 streamed producer builder did not return a bottom-only carrier"
                )
            object_ledger["objects"]["setup"]["created"] = True
            object_ledger["objects"]["setup"]["status"] = "measured"
            result = run_v7_h4_streamed_bottom_basis_producer(
                setup,
                comm=comm,
                marker_callback=marker_callback,
                packet_manifest=selected_mode_packet_manifest,
                packet_identity=selected_mode_packet_identity,
                packet_manifest_sha256=selected_mode_packet_manifest_sha256,
                output_directory=(
                    Path(run_directory).resolve()
                    / "numerical_output"
                    / "streamed_basis_packet"
                ),
            )
            result["source_sha"] = source_sha
            result["run_directory"] = str(Path(run_directory).resolve())
            result["packet"] = {
                **packet_contract,
                "manifest": str(selected_mode_packet_manifest),
            }
            normal_return = True
            return result

        setup_kwargs = {
            "comm": comm,
            "profile": profile,
            "exact_one_cell_work_dir": (
                Path(run_directory).resolve() / "numerical_output" / "exact_one_cell"
            ),
            "cfg_override": cfg,
            "modal_cfg_override": modal_cfg,
            "detail_stage_callback": combined_detail_callback,
            "post_destroy_cleanup": _v3_7_cleanup_callback(comm, post_destroy_cleanup),
        }
        if selected_mode_packet_manifest is not None:
            setup_kwargs.update(
                {
                    "selected_mode_packet_manifest": Path(
                        selected_mode_packet_manifest
                    ),
                    "selected_mode_packet_identity": selected_mode_packet_identity,
                    "selected_mode_packet_manifest_sha256": selected_mode_packet_manifest_sha256,
                }
            )
        setup = setup_builder(**setup_kwargs)
        object_ledger["objects"]["setup"]["created"] = True
        object_ledger["objects"]["setup"]["status"] = "measured"
        layout = HybridAugmentedLayout.build(
            setup.bottom,
            setup.top,
            setup.coupling.internal_unknown_count,
        )
        if (
            v5_h4_setup_only
            or v6_h4_post_compaction_setup_only
            or v7_h4_exact_side_limit_setup_only
            or v7_h4_full_formal
        ):
            full_formal_runner = None
            if v7_h4_full_formal:
                if recovery_runner is None:
                    raise ValueError(
                        "V7 full formal requires the existing recovery_runner"
                    )

                def full_formal_runner(**kwargs):
                    return _run_v7_h4_exact_side_full_formal(
                        recovery_runner=recovery_runner,
                        producer=producer,
                        run_directory=run_directory,
                        **kwargs,
                    )

            result = run_v5_h4_exact_side_setup_only(
                setup,
                layout,
                comm=comm,
                marker_callback=marker_callback,
                sampled_column_contract=v5_sampled_column_contract,
                streaming_w_batch_size=v5_streaming_w_batch_size,
                v6_profile=(
                    v6_h4_post_compaction_setup_only
                    or v7_h4_exact_side_limit_setup_only
                    or v7_h4_full_formal
                ),
                exact_spool_root=(
                    v7_h4_exact_side_exact_spool_root
                    if (v7_h4_exact_side_limit_setup_only or v7_h4_full_formal)
                    else v6_h4_exact_spool_root
                ),
                packet_identity=selected_mode_packet_identity,
                packet_manifest_sha256=selected_mode_packet_manifest_sha256,
                full_formal_runner=full_formal_runner,
            )
            if v7_h4_exact_side_limit_setup_only or v7_h4_full_formal:
                result["schema"] = V7_H4_EXACT_SIDE_LIMIT_SCHEMA
                result["v7_profile"] = result.pop("v6_profile")
                result["v7_profile"].update(
                    {
                        "profile_id": (
                            V7_H4_EXACT_SIDE_FULL_FORMAL_PROFILE_ID
                            if v7_h4_full_formal
                            else V7_H4_EXACT_SIDE_LIMIT_PROFILE_ID
                        ),
                        "schema": (
                            V7_H4_EXACT_SIDE_FULL_FORMAL_SCHEMA
                            if v7_h4_full_formal
                            else V7_H4_EXACT_SIDE_LIMIT_SCHEMA
                        ),
                        "setup_peak_limit_gib": V7_H4_EXACT_SIDE_LIMIT_GIB,
                        "outer_ready_peak_limit_gib": V7_H4_EXACT_SIDE_LIMIT_GIB,
                        "advancement_line_gib": V7_H4_EXACT_SIDE_LIMIT_GIB,
                        "legacy_v6_setup_line_gib": V6_H4_SETUP_THRESHOLD_GIB,
                        "full_formal": bool(v7_h4_full_formal),
                        "matched_direct_hard_stop_bytes": (
                            V7_H4_EXACT_SIDE_FULL_FORMAL_HARD_STOP_BYTES
                            if v7_h4_full_formal
                            else None
                        ),
                        "setup_only": not v7_h4_full_formal,
                        "default_timeout_seconds": (
                            V7_H4_EXACT_SIDE_FULL_FORMAL_DEFAULT_TIMEOUT_SECONDS
                            if v7_h4_full_formal
                            else None
                        ),
                        "conditional_extension_timeout_seconds": (
                            V7_H4_EXACT_SIDE_FULL_FORMAL_EXTENSION_TIMEOUT_SECONDS
                            if v7_h4_full_formal
                            else None
                        ),
                    }
                )
            if v7_h4_full_formal:
                full_report = result.get("full_formal", {})
                result["schema"] = V7_H4_EXACT_SIDE_FULL_FORMAL_SCHEMA
                result["v7_profile"]["schema"] = V7_H4_EXACT_SIDE_FULL_FORMAL_SCHEMA
                result["outer_setup_probe"] = dict(result["outer_ksp"])
                result["outer_ksp"] = {
                    **dict(result["outer_ksp"]),
                    "solve_called": True,
                    "type": full_report.get("solve", {}).get("ksp_type", "gmres"),
                    "restart": full_report.get("solve", {}).get("restart", 10),
                    "formal_solve": full_report.get("solve", {}),
                }
                result["field_export"] = (
                    "completed"
                    if isinstance(result.get("recovery"), Mapping)
                    and result["recovery"].get("physics_pass") is True
                    else "not_run"
                )
            result["source_sha"] = source_sha
            result["run_directory"] = str(Path(run_directory).resolve())
            normal_return = True
            return result
        if v5_h4_blr_side_only:
            result = run_v5_h4_mumps_blr_side_component(
                setup,
                comm=comm,
                marker_callback=marker_callback,
                run_directory=run_directory,
                source_identity={
                    "source_sha": source_sha,
                    "packet_identity": selected_mode_packet_identity,
                    "manifest_sha256": selected_mode_packet_manifest_sha256,
                },
                compressed_factor_profile=v5_h4_blr_profile,
            )
            result["source_sha"] = source_sha
            result["run_directory"] = str(Path(run_directory).resolve())
            result["packet"] = {
                "manifest": str(selected_mode_packet_manifest),
                "identity": _json_safe(selected_mode_packet_identity),
                "manifest_sha256": selected_mode_packet_manifest_sha256,
                "consumer_qep_calls": 0,
            }
            normal_return = True
            return result
        rhs = _default_rhs(setup, layout)

        if (
            sum(
                (
                    bool(candidate_b_only),
                    bool(candidate_c_only),
                    bool(candidate_d_only),
                    bool(candidate_d_qualified),
                    bool(candidate_e_side_only),
                )
            )
            > 1
        ):
            raise ValueError(
                "Candidate-B-only, Candidate-C-only, Candidate-D-only, Candidate-D-qualified, Candidate-E-side-only, and V5 h4 setup-only routes are exclusive"
            )

        if candidate_b_only:
            candidate_report, candidate_checkpoint = _run_v3_8_candidate_b_campaign(
                setup,
                layout,
                rhs,
                resolved_payload=resolved_payload,
                producer=producer,
                modal_amplitudes=modal_amplitudes,
                run_directory=Path(run_directory).resolve(),
                source_sha=source_sha,
                comm=comm,
                survey_side_vectors=survey_side_vectors,
                marker_callback=marker_callback,
            )
            consumer_provenance = resolved_payload["provenance"]
            consumer_resolved_config_sha = hashlib.sha256(
                (Path(run_directory).resolve() / "resolved_config.json").read_bytes()
            ).hexdigest()
            direct_inventory = producer["inventory"]
            result = {
                "schema": "task039.v3-8-candidate-b-only.v1",
                "status": "completed",
                "source_identity": {
                    "consumer_source_sha": source_sha,
                    "producer_source_sha": direct_inventory["source_sha"],
                    "consumer_input_sha256": consumer_provenance["input_sha256"],
                    "consumer_resolved_config_sha256": consumer_resolved_config_sha,
                    "consumer_physical_model_sha256": consumer_provenance[
                        "physical_model_sha256"
                    ],
                    "producer_input_sha256": direct_inventory["input_sha256"],
                    "producer_resolved_config_sha256": direct_inventory[
                        "resolved_config_sha256"
                    ],
                    "producer_physical_model_sha256": direct_inventory[
                        "physical_model_sha256"
                    ],
                    "direct_payload_sha256": direct_inventory["payload"]["artifact"][
                        "sha256"
                    ],
                    "model_id": producer["model_id"],
                    "requested_modes": producer["requested_modes"],
                    "mpi_size": producer["mpi_size"],
                    "external_keys_exact": producer["external_keys_exact"],
                },
                "profile": {
                    "profile_id": profile.profile_id,
                    "incident_grazing_deg": profile.incident_grazing_deg,
                    "incident_phi_deg": profile.incident_phi_deg,
                    "polarization": profile.polarization_kind,
                    "h_nm": profile.h_nm,
                    "requested_modes": profile.requested_modes,
                    "candidate_modes": profile.candidate_modes,
                    "max_it": profile.max_it,
                },
                "watchdog": watchdog,
                "candidate_b": candidate_report,
                "telemetry": {
                    "process_tree_samples": {
                        "path": "numerical_output/process_tree_samples.jsonl",
                        "writer": "parent_task038_launcher",
                        "status": "expected_from_parent_launcher",
                    },
                    "memory_stages": {
                        "path": "numerical_output/memory_stages.jsonl",
                        "writer": "parent_task038_launcher_marker_alignment",
                        "status": "expected_from_parent_launcher",
                    },
                    "memory_stage_markers": {
                        "path": "numerical_output/memory_stage_markers.raw.jsonl",
                        "writer": "v3_7_worker",
                        "status": "measured_worker_marker_stream",
                    },
                    "memory_object_ledger": {
                        "path": "numerical_output/memory_object_ledger.json",
                        "schema": object_ledger["schema"],
                        "status": "finalized_in_worker_finalizer",
                    },
                    "candidate_b_checkpoint": {
                        "path": str(
                            candidate_checkpoint.relative_to(
                                Path(run_directory).resolve()
                            )
                        ),
                        "status": "written_after_budget_sequence",
                    },
                    "stage_callback_connected": stage_callback is not None,
                },
                "formal_run": {
                    "status": "measured_candidate_b_only",
                    "classification": "measured_candidate_b_only",
                    "identity_reference": "not_run_by_candidate_b_contract",
                    "oracle": "not_run_by_candidate_b_contract",
                    "recovery": "not_run_by_candidate_b_contract",
                },
                "run_directory": str(Path(run_directory).resolve()),
            }
            normal_return = True
            return result

        if candidate_c_only:
            candidate_report, candidate_checkpoint = _run_v3_8_candidate_c_campaign(
                setup,
                layout,
                rhs,
                resolved_payload=resolved_payload,
                producer=producer,
                modal_amplitudes=modal_amplitudes,
                run_directory=Path(run_directory).resolve(),
                source_sha=source_sha,
                comm=comm,
                survey_side_vectors=survey_side_vectors,
                marker_callback=marker_callback,
            )
            result = {
                "schema": "task039.v3-8-candidate-c1-only.v1",
                "status": "completed",
                "watchdog": watchdog,
                "candidate_c": candidate_report,
                "checkpoint": str(
                    candidate_checkpoint.relative_to(Path(run_directory).resolve())
                ),
                "telemetry": {
                    "process_tree_samples": "numerical_output/process_tree_samples.jsonl",
                    "memory_stages": "numerical_output/memory_stages.jsonl",
                    "memory_stage_markers": "numerical_output/memory_stage_markers.raw.jsonl",
                    "memory_object_ledger": {
                        "path": "numerical_output/memory_object_ledger.json",
                        "schema": object_ledger["schema"],
                        "status": "finalized_in_worker_finalizer",
                    },
                },
                "formal_run": {
                    "status": "measured_candidate_c1_only",
                    "classification": "measured_candidate_c1_only",
                    "identity_reference": "not_run_by_candidate_c1_contract",
                    "oracle": "not_run_by_candidate_c1_contract",
                    "recovery": "not_run_by_candidate_c1_contract",
                },
                "run_directory": str(Path(run_directory).resolve()),
            }
            normal_return = True
            return result

        if candidate_d_only or candidate_d_qualified:
            candidate_report, candidate_checkpoint = _run_v3_8_candidate_d_campaign(
                setup,
                layout,
                rhs,
                resolved_payload=resolved_payload,
                producer=producer,
                run_directory=Path(run_directory).resolve(),
                source_sha=source_sha,
                comm=comm,
                marker_callback=marker_callback,
                oracle_runner=oracle_runner,
                recovery_runner=recovery_runner,
                case_qualified=candidate_d_qualified,
                qualification_scope=qualification_scope,
                qualification_method=qualification_method,
                qualification_target=qualification_target,
            )
            result = {
                "schema": (
                    "task039.v3-8-candidate-d-qualified.v1"
                    if candidate_d_qualified
                    else "task039.v3-8-candidate-d-only.v1"
                ),
                "status": "completed",
                "classification": candidate_report["classification"],
                "candidate_d": candidate_report,
                "checkpoint": str(
                    candidate_checkpoint.relative_to(Path(run_directory).resolve())
                ),
                "direct_reference_payload_loaded": False,
                "watchdog": watchdog,
                "telemetry": {
                    "process_tree_samples": {
                        "path": "numerical_output/process_tree_samples.jsonl",
                        "writer": "parent_task038_launcher",
                        "status": "expected_from_parent_launcher",
                    },
                    "memory_stages": {
                        "path": "numerical_output/memory_stages.jsonl",
                        "writer": "parent_task038_launcher_marker_alignment",
                        "status": "expected_from_parent_launcher",
                    },
                    "memory_stage_markers": {
                        "path": "numerical_output/memory_stage_markers.raw.jsonl",
                        "writer": "v3_7_worker",
                        "status": "measured_worker_marker_stream",
                    },
                    "memory_object_ledger": {
                        "path": "numerical_output/memory_object_ledger.json",
                        "schema": object_ledger["schema"],
                        "status": "finalized_in_worker_finalizer",
                    },
                },
                "formal_run": {
                    "status": (
                        "attempted_candidate_d_qualified"
                        if candidate_d_qualified
                        else "measured_candidate_d_only"
                    ),
                    "classification": candidate_report["classification"],
                    "direct_reference_payload_loaded": False,
                },
                "run_directory": str(Path(run_directory).resolve()),
            }
            if candidate_d_qualified:
                result["qualification"] = candidate_report["qualification"]
                result["formal_run"] = {
                    "status": "attempted_candidate_d_qualified",
                    "classification": qualification_method,
                    "qualification_target": qualification_target,
                    "direct_reference_payload_loaded": False,
                    "qualification_scope": qualification_scope,
                    "explicit_opt_in": True,
                    "ordinary_default_changed": False,
                }
            normal_return = True
            return result

        if candidate_e_side_only:
            candidate_report, candidate_checkpoint = (
                _run_v3_8_candidate_e_side_campaign(
                    setup,
                    layout,
                    rhs,
                    resolved_payload=resolved_payload,
                    producer=producer,
                    modal_amplitudes=modal_amplitudes,
                    run_directory=Path(run_directory).resolve(),
                    source_sha=source_sha,
                    comm=comm,
                    survey_side_vectors=survey_side_vectors,
                    marker_callback=marker_callback,
                )
            )
            result = {
                "schema": "task039.v3-8-candidate-e-side-only.v1",
                "status": "completed",
                "candidate_e": candidate_report,
                "checkpoint": str(
                    candidate_checkpoint.relative_to(Path(run_directory).resolve())
                ),
                "direct_reference_payload_loaded": True,
                "watchdog": watchdog,
                "telemetry": {
                    "process_tree_samples": "numerical_output/process_tree_samples.jsonl",
                    "memory_stages": "numerical_output/memory_stages.jsonl",
                    "memory_stage_markers": "numerical_output/memory_stage_markers.raw.jsonl",
                    "memory_object_ledger": {
                        "path": "numerical_output/memory_object_ledger.json",
                        "schema": object_ledger["schema"],
                        "status": "finalized_in_worker_finalizer",
                    },
                },
                "formal_run": {
                    "status": "measured_candidate_e_side_only",
                    "classification": "measured_candidate_e_side_only",
                    "identity_reference": "not_run_by_candidate_e_contract",
                    "oracle": "not_run_by_candidate_e_contract",
                    "recovery": "not_run_by_candidate_e_contract",
                },
                "run_directory": str(Path(run_directory).resolve()),
            }
            normal_return = True
            return result

        def identity_stage() -> Mapping[str, Any]:
            production_operator, production_context = (
                create_hybrid_assembled_block_action(
                    setup.bottom, setup.top, setup.coupling
                )
            )
            vectors: dict[str, PETSc.Vec] = {}
            isolated: dict[str, PETSc.Vec] = {}
            reference_rhs = None
            x_star = None
            try:
                reference = reference_holder.get("reference")
                if reference is None:
                    _emit_marker(
                        marker_callback,
                        "identity_reference_materialization_begin",
                    )
                    reference = reference_builder(
                        setup.bottom, setup.top, setup.coupling
                    )
                    reference_holder["reference"] = reference
                    _emit_marker(
                        marker_callback,
                        "identity_reference_materialization_end",
                    )
                reference_rhs = layout.pack(
                    reference.bottom.b,
                    reference.top.b,
                    internal_modal_rhs_correction(setup.coupling),
                )
                vectors.update(deterministic_global_index_vectors(layout))
                vectors["physical_rhs"] = rhs
                x_star = rebuild_hybrid_augmented_vector(
                    producer["inventory"],
                    setup.bottom,
                    setup.top,
                    layout,
                    modal_amplitudes,
                )[0]
                vectors["direct_solution_x_star"] = x_star
                direct_residual = production_operator.createVecLeft()
                production_operator.mult(x_star, direct_residual)
                direct_residual.scale(PETSc.ScalarType(-1.0))
                direct_residual.axpy(PETSc.ScalarType(1.0), rhs)
                vectors["direct_solution_derived_residual"] = direct_residual
                for side, system, block_slice in (
                    ("bottom", setup.bottom, layout.local_bottom_slice),
                    ("top", setup.top, layout.local_top_slice),
                ):
                    side_residual = system.A.createVecLeft()
                    side_values = side_residual.getArray()
                    global_values = direct_residual.getArray(readonly=True)[block_slice]
                    if side_values.size != global_values.size:
                        side_residual.destroy()
                        raise ValueError(
                            f"{side} direct residual ownership does not match layout"
                        )
                    side_values[:] = global_values
                    side_residual.assemble()
                    survey_side_vectors.setdefault(side, {})[
                        "direct_solution_side_residual"
                    ] = side_residual
                for block in ("bottom", "top", "modal"):
                    isolated[f"{block}_only"] = _isolated_vector(layout, block)
                result = dict(
                    identity_runner(
                        reference.operator,
                        production_operator,
                        layout,
                        vectors,
                        rhs_pairs={"physical_rhs": (rhs, reference_rhs)},
                        isolated_vectors=isolated,
                        relative_limit=V3_7_RHS_TOLERANCE,
                    )
                )
                result["direct_solution_residual"] = {
                    "relative_error": float(direct_residual.norm())
                    / max(float(rhs.norm()), 1.0e-30),
                    "denominator": "max(norm(physical_rhs),1e-30)",
                    "source": "canonical direct payload reconstructed on current layout",
                }
                identity_checkpoint = _write_v3_7_identity_checkpoint(
                    Path(run_directory).resolve(),
                    source_sha=source_sha,
                    producer=producer,
                    identity=result,
                    comm=comm,
                )
                _emit_marker(
                    marker_callback,
                    "identity_audit_complete",
                    path=str(
                        identity_checkpoint.relative_to(Path(run_directory).resolve())
                    ),
                    **{"pass": bool(result.get("pass") is True)},
                )
                return result
            finally:
                for vector in isolated.values():
                    _destroy(vector)
                for label, vector in vectors.items():
                    if vector is not rhs and vector is not x_star:
                        _destroy(vector)
                _destroy(x_star)
                _destroy(reference_rhs)
                production_context.destroy()
                production_operator.destroy()

        def correction_stage() -> Mapping[str, Any]:
            nonlocal side_checkpoint_path
            if correction_runner is not None:
                correction = correction_runner(setup, stage_callback=stage_callback)
            else:
                correction = run_task039_v3_7_side_correction_survey(
                    setup,
                    side_vectors=survey_side_vectors,
                    stage_callback=stage_callback,
                    marker_callback=marker_callback,
                )
            side_checkpoint_path = _write_v3_7_side_survey_checkpoint(
                Path(run_directory).resolve(),
                source_sha=source_sha,
                producer=producer,
                correction=correction,
                comm=comm,
            )
            return correction

        def oracle_stage(
            consumer: Callable[[Any, Mapping[str, Any]], None],
        ) -> Mapping[str, Any]:
            _emit_marker(
                marker_callback,
                "exact_side_oracle_begin",
            )
            report = dict(
                oracle_runner(
                    layout,
                    setup.bottom,
                    setup.top,
                    setup.coupling,
                    rhs,
                    reference=reference_holder["reference"],
                    max_it=V3_7_ORACLE_MAX_IT,
                    restart=90,
                    threshold=V3_7_RESIDUAL_TOLERANCE,
                    matrix_repeat_tolerance=V3_7_MATRIX_REPEAT_TOLERANCE,
                    solution_consumer=consumer,
                )
            )
            _emit_marker(
                marker_callback,
                "exact_side_oracle_end",
                numerical_pass=report.get("numerical_pass"),
                inventory_pass=report.get("inventory_pass"),
            )
            borrowed_reference = reference_holder.pop("reference")
            borrowed_reference.destroy()
            _emit_marker(
                marker_callback,
                "borrowed_reference_cleanup_end",
            )
            report["borrowed_reference_cleanup"] = {
                "destroyed_by_caller": True,
                "before_recovery_consumer": True,
            }
            return report

        snapshot: dict[str, Any] = {}

        def snapshotter(solution: Any) -> Any:
            duplicate = solution.duplicate()
            solution.copy(duplicate)
            snapshot["vector"] = duplicate
            _emit_marker(marker_callback, "solution_snapshot_created")
            return duplicate

        def recovery_consumer(snapshot: PETSc.Vec) -> Mapping[str, Any]:
            _emit_marker(marker_callback, "recovery_physics_begin")
            report = recovery_runner(
                setup,
                layout,
                snapshot,
                Path(run_directory).resolve(),
                producer,
            )
            _emit_marker(marker_callback, "recovery_physics_end")
            return report

        sequence = run_v3_7_stage_sequence(
            identity_stage=identity_stage,
            correction_stage=correction_stage,
            oracle_stage=oracle_stage,
            snapshotter=snapshotter,
            recovery_runner=recovery_consumer,
        )
        oracle_lifecycle = sequence.get("oracle", {}).get("lifecycle", {})
        oracle_inventory = sequence.get("oracle", {}).get("inventory", {})
        if oracle_lifecycle:
            action = object_ledger["objects"]["exact_side_action"]
            action.update(
                {
                    "created": True,
                    "completed": True,
                    "destroyed": bool(
                        oracle_lifecycle.get("bottom_action_destroyed")
                        and oracle_lifecycle.get("top_action_destroyed")
                    ),
                    "status": "measured",
                }
            )
            if (
                oracle_inventory.get("bottom_direct_factor_count") == 1
                and oracle_inventory.get("top_direct_factor_count") == 1
            ):
                object_ledger["objects"]["exact_side_factors"].update(
                    {
                        "created": True,
                        "completed": True,
                        "destroyed": bool(
                            oracle_lifecycle.get("bottom_action_destroyed")
                            and oracle_lifecycle.get("top_action_destroyed")
                        ),
                        "status": "measured",
                    }
                )
        if "vector" in snapshot:
            object_ledger["objects"]["solution_snapshot"]["created"] = True
        if "vector" in snapshot:
            _destroy(snapshot["vector"])
            object_ledger["objects"]["solution_snapshot"]["destroyed"] = True
            _emit_marker(marker_callback, "solution_snapshot_destroyed")
        result = {
            "schema": "task039.v3_7-thin-orchestration.v1",
            "status": sequence["status"],
            "source_identity": {
                "consumer_source_sha": source_sha,
                "producer_source_sha": producer["producer_source_sha"],
                "physical_model_sha256": producer["physical_model_sha256"],
                "model_id": producer["model_id"],
                "requested_modes": producer["requested_modes"],
                "mpi_size": producer["mpi_size"],
                "external_keys_exact": producer["external_keys_exact"],
            },
            "profile": {
                "profile_id": profile.profile_id,
                "incident_grazing_deg": profile.incident_grazing_deg,
                "incident_phi_deg": profile.incident_phi_deg,
                "h_nm": profile.h_nm,
                "requested_modes": profile.requested_modes,
                "candidate_modes": profile.candidate_modes,
                "max_it": profile.max_it,
                "oracle_max_it": V3_7_ORACLE_MAX_IT,
                "matrix_repeat_tolerance": V3_7_MATRIX_REPEAT_TOLERANCE,
            },
            "qep_basis_audit": getattr(setup, "qep_audit", {}),
            "watchdog": watchdog,
            "telemetry": {
                "process_tree_samples": {
                    "path": "numerical_output/process_tree_samples.jsonl",
                    "writer": "parent_task038_launcher",
                    "status": "expected_from_parent_launcher",
                },
                "memory_stages": {
                    "path": "numerical_output/memory_stages.jsonl",
                    "writer": "parent_task038_launcher_marker_alignment",
                    "status": "expected_from_parent_launcher",
                },
                "memory_stage_markers": {
                    "path": "numerical_output/memory_stage_markers.raw.jsonl",
                    "writer": "v3_7_worker",
                    "status": "measured_worker_marker_stream",
                },
                "memory_object_ledger": {
                    "path": "numerical_output/memory_object_ledger.json",
                    "schema": object_ledger["schema"],
                    "status": "finalized_in_worker_finalizer",
                },
                "side_survey_checkpoint": {
                    "path": (
                        str(
                            side_checkpoint_path.relative_to(
                                Path(run_directory).resolve()
                            )
                        )
                        if side_checkpoint_path is not None
                        else "not_available"
                    ),
                    "status": (
                        "written_before_oracle"
                        if side_checkpoint_path is not None
                        else "not_available"
                    ),
                },
                "stage_callback_connected": stage_callback is not None,
            },
            "sequence": sequence,
            "formal_run": {
                "status": sequence["status"],
                "classification": "measured_v3_7_diagnostic",
            },
            "run_directory": str(Path(run_directory).resolve()),
        }
        normal_return = sequence["status"] == "completed"
        return result
    finally:
        _destroy(rhs) if "rhs" in locals() else None
        for side_vectors in survey_side_vectors.values():
            for vector in side_vectors.values():
                vector.destroy()
        if reference_holder.get("reference") is not None:
            reference_holder["reference"].destroy()
            if object_ledger["objects"]["independent_reference"]["created"]:
                object_ledger["objects"]["independent_reference"]["destroyed"] = True
        try:
            if setup is not None:
                if (
                    v5_h4_fixed_budget_bottom_only
                    or v6_h4_port_modal_bottom_only
                    or v7_h4_streamed_bottom_producer
                    or v7_h4_streamed_bottom_consumer
                ) and getattr(setup, "side_only", False):
                    side_system = setup.bottom
                    destroy_called = False
                    try:
                        if not bool(getattr(side_system, "_destroyed", False)):
                            side_system.destroy()
                        destroy_called = True
                    finally:
                        side_cleanup = collective_heap_cleanup(comm)
                    setup_release = {
                        "order": ["bottom"],
                        "checks": {
                            "bottom_destroy_call_completed": destroy_called,
                            "cleanup_collective_call_completed": bool(
                                side_cleanup["collective_call_completed"]
                            ),
                        },
                        "cleanup": side_cleanup,
                        "pass": bool(
                            destroy_called and side_cleanup["collective_call_completed"]
                        ),
                    }
                    factor_counts = None
                    if isinstance(result, Mapping):
                        bottom_result = result.get("sides", {}).get("bottom", {})
                        candidate_result = (
                            bottom_result.get("candidate", {})
                            if isinstance(bottom_result, Mapping)
                            else {}
                        )
                        cleanup_result = (
                            candidate_result.get("cleanup", {})
                            if isinstance(candidate_result, Mapping)
                            else {}
                        )
                        if isinstance(cleanup_result, Mapping):
                            factor_counts = cleanup_result.get(
                                "factor_count_after_cleanup"
                            )
                        if factor_counts is None and v7_h4_streamed_bottom_consumer:
                            factor_counts = result.get("factor_inventory")
                    marker_callback(
                        (
                            "v6_port_modal_bottom_side_setup_cleanup"
                            if v6_h4_port_modal_bottom_only
                            else (
                                "v7_streamed_bottom_consumer_side_setup_cleanup"
                                if v7_h4_streamed_bottom_consumer
                                else (
                                    "v7_streamed_bottom_producer_side_setup_cleanup"
                                    if v7_h4_streamed_bottom_producer
                                    else "v5_fixed_budget_bottom_side_setup_cleanup"
                                )
                            )
                        ),
                        {
                            "source": "side_only_finalizer",
                            "side": "bottom",
                            "bottom_destroyed": bool(destroy_called),
                            "collective_cleanup_completed": bool(
                                side_cleanup["collective_call_completed"]
                            ),
                            "factor_count_after_cleanup": factor_counts,
                            "completed": bool(setup_release["pass"]),
                        },
                    )
                else:
                    setup_release = release_frozen_m10_objects(setup, None, comm)
                object_ledger["objects"]["setup"]["destroyed"] = True
                object_ledger["objects"]["setup"]["completed"] = True
                if (
                    v5_h4_setup_only
                    or v6_h4_post_compaction_setup_only
                    or v7_h4_exact_side_limit_setup_only
                    or v7_h4_full_formal
                ):
                    internal = (
                        result.get("setup_only_internal_cleanup", {})
                        if result is not None
                        else {}
                    )
                    marker_callback(
                        "all_setup_objects_cleanup",
                        {
                            "source": "release_frozen_m10_objects",
                            "setup_destroyed": True,
                            "factor_count_after_cleanup": internal.get(
                                "factor_count_after_cleanup", {}
                            ),
                            "setup_release": setup_release,
                            "internal_cleanup": internal,
                            "completed": bool(
                                result is not None
                                and result.get("status")
                                in {
                                    "setup_only_completed",
                                    "full_formal_completed",
                                }
                            ),
                        },
                    )
                    comm.barrier()
                    time.sleep(0.30)
                    comm.barrier()
        except Exception:
            exception_raised = True
            raise
        finally:
            if marker_stream is not None:
                marker_stream.close()
            if exception_raised:
                object_ledger["status"] = "exception"
            elif normal_return:
                object_ledger["status"] = "completed"
            elif result is not None:
                object_ledger["status"] = "controlled_stop"
            else:
                object_ledger["status"] = "exception"
            if (
                v5_h4_setup_only
                or v6_h4_post_compaction_setup_only
                or v7_h4_exact_side_limit_setup_only
                or v7_h4_full_formal
            ) and result is not None:
                internal = result.get("setup_only_internal_cleanup", {})
                side_actions = result.get("side_actions", {})
                factor_counts = internal.get("factor_count_after_cleanup", {})
                cleanup_pass = bool(
                    internal.get("exact_side_objects_destroyed")
                    and side_actions
                    and all(int(count) == 0 for count in factor_counts.values())
                )
                details = {
                    "factor_only_storage": all(
                        bool(item.get("factor_only_storage"))
                        for item in side_actions.values()
                    ),
                    "lifecycle_pass": cleanup_pass,
                    "factor_count_after_cleanup": factor_counts,
                    "side_component_cleanup": internal.get(
                        "side_component_cleanup", {}
                    ),
                    "outer_ready_factor_counts": internal.get(
                        "factor_count_at_outer_ready", {}
                    ),
                }
                for name in ("exact_side_action", "exact_side_factors"):
                    object_ledger["objects"][name].update(
                        {
                            "created": bool(side_actions),
                            "completed": result.get("status")
                            in {"setup_only_completed", "full_formal_completed"},
                            "destroyed": cleanup_pass,
                            "status": "measured" if cleanup_pass else "incomplete",
                            "lifecycle_pass": cleanup_pass,
                            "details": details,
                        }
                    )
                if (
                    v6_h4_post_compaction_setup_only
                    or v7_h4_exact_side_limit_setup_only
                    or v7_h4_full_formal
                ):
                    qep_release = getattr(setup, "qep_release", {})
                    packet_refs_released = bool(
                        qep_release.get("packet_mmap_released") is True
                        and qep_release.get("packet_references_released") is True
                    )
                    for name in ("qep_matrices", "selected_basis"):
                        created = bool(object_ledger["objects"][name].get("created"))
                        object_ledger["objects"][name].update(
                            {
                                "created": created,
                                "completed": bool(
                                    object_ledger["objects"][name].get("completed")
                                ),
                                "released": packet_refs_released,
                                "destroyed": packet_refs_released,
                                "status": (
                                    "measured" if packet_refs_released else "incomplete"
                                ),
                                "details": {
                                    "source": "FrozenM10Setup.qep_release",
                                    "qep_release": qep_release,
                                },
                            }
                        )
                    profile_key = (
                        "v7_profile"
                        if v7_h4_exact_side_limit_setup_only or v7_h4_full_formal
                        else "v6_profile"
                    )
                    result.setdefault(profile_key, {})[
                        "factor_count_after_final_cleanup"
                    ] = factor_counts
                    result[profile_key]["packet_qep_refs_released"] = (
                        packet_refs_released
                    )
            for item in object_ledger["objects"].values():
                if item["created"] and item["status"] == "not_available":
                    item["status"] = "measured"
                elif item["status"] == "not_available":
                    item["status"] = "not_available"
            _write_v3_7_object_ledger(object_ledger_path, object_ledger, comm)
            if result is not None:
                ledger_digest = hashlib.sha256(
                    object_ledger_path.read_bytes()
                ).hexdigest()
                result["telemetry"]["memory_object_ledger"].update(
                    {
                        "status": object_ledger["status"],
                        "sha256": ledger_digest,
                    }
                )
                if record_path is not None and comm.rank == 0:
                    path = Path(record_path)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
                    temporary.write_text(
                        json.dumps(_json_safe(result), ensure_ascii=False, indent=2)
                        + "\n",
                        encoding="utf-8",
                    )
                    temporary.replace(path)
                if record_path is not None:
                    comm.barrier()


def _write_v3_7_worker_traceback(run_directory: str | Path) -> Path:
    """Persist the current worker exception traceback beside raw output."""

    path = (
        Path(run_directory).resolve()
        / "numerical_output"
        / f"worker_traceback_rank{MPI.COMM_WORLD.rank:04d}.txt"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(traceback.format_exc(), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--launched-by-task038-watchdog", action="store_true")
    parser.add_argument("--candidate-b-only", action="store_true")
    parser.add_argument("--candidate-c-only", action="store_true")
    parser.add_argument("--candidate-d-only", action="store_true")
    parser.add_argument("--candidate-d-qualified", action="store_true")
    parser.add_argument("--candidate-e-side-only", action="store_true")
    parser.add_argument("--v5-h4-setup-only", action="store_true")
    parser.add_argument("--v6-h4-post-compaction-setup-only", action="store_true")
    parser.add_argument("--v6-h4-exact-spool-root")
    parser.add_argument("--v7-h4-exact-side-limit-setup-only", action="store_true")
    parser.add_argument("--v7-h4-exact-side-exact-spool-root")
    parser.add_argument("--v7-h4-exact-side-full-formal", action="store_true")
    parser.add_argument("--v6-h4-port-modal-bottom-component", action="store_true")
    parser.add_argument("--v6-h4-port-modal-exact-spool-root")
    parser.add_argument("--v7-h4-streamed-bottom-producer", action="store_true")
    parser.add_argument("--v7-h4-streamed-bottom-consumer", action="store_true")
    parser.add_argument("--v8-h4-layer-block-reconstruction", action="store_true")
    parser.add_argument("--v7-h4-streamed-bottom-consumer-basis-manifest")
    parser.add_argument("--v7-h4-streamed-bottom-consumer-basis-manifest-sha256")
    parser.add_argument("--v7-h4-streamed-bottom-consumer-exact-spool-root")
    parser.add_argument("--v5-h4-blr-side-component", action="store_true")
    parser.add_argument("--v5-h4-fixed-budget-bottom-component", action="store_true")
    parser.add_argument("--v5-h4-fixed-budget-exact-spool-root")
    parser.add_argument("--v8-h4-layer-sweep-bottom", action="store_true")
    parser.add_argument("--v8-h4-layer-sweep-exact-spool-root")
    parser.add_argument(
        "--v9-h4-bare-f-full-side-diagnostic",
        dest="v9_h4_bare_f_side",
        action="store_true",
    )
    parser.add_argument(
        "--v9-h4-bare-f-full-side-exact-spool-root",
        dest="v9_h4_bare_f_side_exact_spool_root",
    )
    parser.add_argument(V9_H4_LAYER_SUPERNODE_BOTTOM_FLAG, action="store_true")
    parser.add_argument(V9_H4_LAYER_SUPERNODE_EXACT_SPOOL_ROOT_FLAG)
    parser.add_argument(V10_H4_SUPERNODE_FACTOR_INTEGRITY_FLAG, action="store_true")
    parser.add_argument(V10_H4_SUPERNODE_FACTOR_INTEGRITY_EXACT_SPOOL_ROOT_FLAG)
    parser.add_argument(V10_H4_SN2_J_ONLY_FLAG, action="store_true")
    parser.add_argument(V10_H4_SN2_J_ONLY_EXACT_SPOOL_ROOT_FLAG)
    parser.add_argument(V10_H4_J1_INNER_FGMRES_FLAG, action="store_true")
    parser.add_argument(V10_H4_J1_INNER_FGMRES_EXACT_SPOOL_ROOT_FLAG)
    parser.add_argument(V10_H4_SIDE_RESPONSE_PACKET_PILOT_FLAG, action="store_true")
    parser.add_argument(V10_H4_SIDE_RESPONSE_PACKET_PILOT_EXACT_SPOOL_ROOT_FLAG)
    parser.add_argument(V10_H4_SIDE_RESPONSE_PACKET_PILOT_OUTPUT_ROOT_FLAG)
    parser.add_argument(V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_FLAG, action="store_true")
    parser.add_argument(V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_MANIFEST_FLAG)
    parser.add_argument(V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_MANIFEST_SHA256_FLAG)
    parser.add_argument(
        V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_FLAG, action="store_true"
    )
    parser.add_argument(V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_EXACT_SPOOL_ROOT_FLAG)
    parser.add_argument(V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_OUTPUT_ROOT_FLAG)
    parser.add_argument(
        V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_FLAG, action="store_true"
    )
    parser.add_argument(V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_MANIFEST_FLAG)
    parser.add_argument(V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_MANIFEST_SHA256_FLAG)
    parser.add_argument(
        V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_PRODUCER_SOURCE_SHA_FLAG
    )
    parser.add_argument(V11_BOTTOM_PACKET_ALGEBRA_FLAG, action="store_true")
    parser.add_argument(V11_BOTTOM_PACKET_ALGEBRA_EXACT_SPOOL_ROOT_FLAG)
    parser.add_argument(V11_BOTTOM_PACKET_ALGEBRA_PACKET_MANIFEST_FLAG)
    parser.add_argument(V11_BOTTOM_PACKET_ALGEBRA_PACKET_MANIFEST_SHA256_FLAG)
    parser.add_argument(V11_BOTTOM_PACKET_ALGEBRA_PRODUCER_DIAGNOSTIC_FLAG)
    parser.add_argument(
        "--v5-h4-blr-profile",
        choices=V5_H4_BLR_PROFILE_CHOICES,
        default=MUMPS_BLR_V5_H4_PROFILE,
    )
    parser.add_argument("--selected-mode-packet-manifest")
    parser.add_argument("--selected-mode-packet-identity")
    parser.add_argument("--selected-mode-packet-manifest-sha256")
    parser.add_argument("--input", required=True, dest="input_path")
    parser.add_argument("--run-directory", required=True)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args(argv)
    component_route = any(
        (
            args.v5_h4_setup_only,
            args.v6_h4_post_compaction_setup_only,
            args.v7_h4_exact_side_limit_setup_only,
            args.v7_h4_exact_side_full_formal,
            args.v6_h4_port_modal_bottom_component,
            args.v7_h4_streamed_bottom_producer,
            args.v7_h4_streamed_bottom_consumer,
            args.v8_h4_layer_block_reconstruction,
            args.v8_h4_layer_sweep_bottom,
            args.v9_h4_bare_f_side,
            args.v9_h4_layer_supernode_bottom,
            args.v10_h4_supernode_factor_integrity,
            args.v10_h4_sn2_j_only,
            args.v10_h4_j1_inner_fgmres,
            args.v10_h4_side_response_packet_pilot,
            args.v10_h4_side_response_packet_consumer,
            args.v10_h4_side_response_packet_full_producer,
            args.v10_h4_side_response_packet_compression,
            args.v11_h4_bottom_packet_algebra,
            args.v5_h4_blr_side_component,
            args.v5_h4_fixed_budget_bottom_component,
        )
    )
    if args.worker == args.dry_run:
        parser.error("choose exactly one of --worker or --dry-run")
    if (
        sum(
            (
                bool(args.candidate_b_only),
                bool(args.candidate_c_only),
                bool(args.candidate_d_only),
                bool(args.candidate_d_qualified),
                bool(args.candidate_e_side_only),
                bool(args.v5_h4_setup_only),
                bool(args.v6_h4_post_compaction_setup_only),
                bool(args.v7_h4_exact_side_limit_setup_only),
                bool(args.v7_h4_exact_side_full_formal),
                bool(args.v6_h4_port_modal_bottom_component),
                bool(args.v7_h4_streamed_bottom_producer),
                bool(args.v7_h4_streamed_bottom_consumer),
                bool(args.v8_h4_layer_block_reconstruction),
                bool(args.v8_h4_layer_sweep_bottom),
                bool(args.v9_h4_bare_f_side),
                bool(args.v9_h4_layer_supernode_bottom),
                bool(args.v10_h4_supernode_factor_integrity),
                bool(args.v10_h4_sn2_j_only),
                bool(args.v10_h4_j1_inner_fgmres),
                bool(args.v10_h4_side_response_packet_pilot),
                bool(args.v10_h4_side_response_packet_consumer),
                bool(args.v10_h4_side_response_packet_full_producer),
                bool(args.v10_h4_side_response_packet_compression),
                bool(args.v11_h4_bottom_packet_algebra),
                bool(args.v5_h4_blr_side_component),
                bool(args.v5_h4_fixed_budget_bottom_component),
            )
        )
        > 1
    ):
        parser.error(
            "candidate routes and V5 h4 component routes are mutually exclusive"
        )
    if args.dry_run:
        plan = v3_7_execution_dry_run(
            args.input_path,
            args.run_directory,
            source_sha=args.source_sha,
            candidate_b_only=args.candidate_b_only,
            candidate_c_only=args.candidate_c_only,
            candidate_d_only=args.candidate_d_only,
            candidate_d_qualified=args.candidate_d_qualified,
            candidate_e_side_only=args.candidate_e_side_only,
            v5_h4_setup_only=args.v5_h4_setup_only,
            v6_h4_post_compaction_setup_only=args.v6_h4_post_compaction_setup_only,
            v6_h4_exact_spool_root=args.v6_h4_exact_spool_root,
            v7_h4_exact_side_limit_setup_only=(args.v7_h4_exact_side_limit_setup_only),
            v7_h4_exact_side_exact_spool_root=(args.v7_h4_exact_side_exact_spool_root),
            v7_h4_exact_side_full_formal=args.v7_h4_exact_side_full_formal,
            v6_h4_port_modal_bottom_only=args.v6_h4_port_modal_bottom_component,
            v6_h4_port_modal_exact_spool_root=(args.v6_h4_port_modal_exact_spool_root),
            v7_h4_streamed_bottom_producer=args.v7_h4_streamed_bottom_producer,
            v7_h4_streamed_bottom_consumer=args.v7_h4_streamed_bottom_consumer,
            v8_h4_layer_block_reconstruction=args.v8_h4_layer_block_reconstruction,
            v8_h4_layer_sweep_bottom=args.v8_h4_layer_sweep_bottom,
            v9_h4_bare_f_side=args.v9_h4_bare_f_side,
            v9_h4_bare_f_side_exact_spool_root=(
                args.v9_h4_bare_f_side_exact_spool_root
            ),
            v9_h4_layer_supernode_bottom=args.v9_h4_layer_supernode_bottom,
            v9_h4_layer_supernode_exact_spool_root=(
                args.v9_h4_layer_supernode_exact_spool_root
            ),
            v10_h4_supernode_factor_integrity=args.v10_h4_supernode_factor_integrity,
            v10_h4_supernode_factor_integrity_exact_spool_root=(
                args.v10_h4_supernode_factor_integrity_exact_spool_root
            ),
            v10_h4_sn2_j_only=args.v10_h4_sn2_j_only,
            v10_h4_sn2_j_only_exact_spool_root=(
                args.v10_h4_sn2_j_only_exact_spool_root
            ),
            v10_h4_j1_inner_fgmres=args.v10_h4_j1_inner_fgmres,
            v10_h4_j1_inner_fgmres_exact_spool_root=(
                args.v10_h4_j1_inner_fgmres_exact_spool_root
            ),
            v10_h4_side_response_packet_pilot=args.v10_h4_side_response_packet_pilot,
            v10_h4_side_response_packet_pilot_exact_spool_root=(
                args.v10_h4_side_response_packet_pilot_exact_spool_root
            ),
            v10_h4_side_response_packet_pilot_output_root=(
                args.v10_h4_side_response_packet_pilot_output_root
            ),
            v10_h4_side_response_packet_consumer=args.v10_h4_side_response_packet_consumer,
            v10_h4_side_response_packet_consumer_manifest=(
                args.v10_h4_side_response_packet_consumer_manifest
            ),
            v10_h4_side_response_packet_consumer_manifest_sha256=(
                args.v10_h4_side_response_packet_consumer_manifest_sha256
            ),
            v10_h4_side_response_packet_full_producer=(
                args.v10_h4_side_response_packet_full_producer
            ),
            v10_h4_side_response_packet_full_producer_exact_spool_root=(
                args.v10_h4_side_response_packet_full_producer_exact_spool_root
            ),
            v10_h4_side_response_packet_full_producer_output_root=(
                args.v10_h4_side_response_packet_full_producer_output_root
            ),
            v10_h4_side_response_packet_compression=(
                args.v10_h4_side_response_packet_compression
            ),
            v10_h4_side_response_packet_compression_manifest=(
                args.v10_h4_side_response_packet_compression_manifest
            ),
            v10_h4_side_response_packet_compression_manifest_sha256=(
                args.v10_h4_side_response_packet_compression_manifest_sha256
            ),
            v10_h4_side_response_packet_compression_producer_source_sha=(
                args.v10_h4_side_response_packet_compression_producer_source_sha
            ),
            v11_h4_bottom_packet_algebra=args.v11_h4_bottom_packet_algebra,
            v11_h4_bottom_packet_algebra_exact_spool_root=(
                args.v11_h4_bottom_packet_algebra_exact_spool_root
            ),
            v11_h4_bottom_packet_algebra_packet_manifest=(
                args.v11_h4_bottom_packet_algebra_packet_manifest
            ),
            v11_h4_bottom_packet_algebra_packet_manifest_sha256=(
                args.v11_h4_bottom_packet_algebra_packet_manifest_sha256
            ),
            v11_h4_bottom_packet_algebra_producer_diagnostic=(
                args.v11_h4_bottom_packet_algebra_producer_diagnostic
            ),
            v8_h4_layer_sweep_exact_spool_root=(
                args.v8_h4_layer_sweep_exact_spool_root
            ),
            v7_h4_streamed_bottom_consumer_basis_manifest=(
                args.v7_h4_streamed_bottom_consumer_basis_manifest
            ),
            v7_h4_streamed_bottom_consumer_basis_manifest_sha256=(
                args.v7_h4_streamed_bottom_consumer_basis_manifest_sha256
            ),
            v7_h4_streamed_bottom_consumer_exact_spool_root=(
                args.v7_h4_streamed_bottom_consumer_exact_spool_root
            ),
            v5_h4_blr_side_only=args.v5_h4_blr_side_component,
            v5_h4_fixed_budget_bottom_only=args.v5_h4_fixed_budget_bottom_component,
            v5_h4_fixed_budget_exact_spool_root=(
                args.v5_h4_fixed_budget_exact_spool_root
            ),
            v5_h4_blr_profile=args.v5_h4_blr_profile,
            selected_mode_packet_manifest=args.selected_mode_packet_manifest,
            selected_mode_packet_identity=(
                args.selected_mode_packet_identity
                if (
                    args.v5_h4_setup_only
                    or args.v6_h4_post_compaction_setup_only
                    or args.v7_h4_exact_side_limit_setup_only
                    or args.v7_h4_exact_side_full_formal
                    or args.v6_h4_port_modal_bottom_component
                    or args.v7_h4_streamed_bottom_producer
                    or args.v7_h4_streamed_bottom_consumer
                    or args.v8_h4_layer_sweep_bottom
                    or args.v10_h4_j1_inner_fgmres
                    or args.v10_h4_side_response_packet_pilot
                    or args.v10_h4_side_response_packet_full_producer
                    or args.v5_h4_blr_side_component
                    or args.v5_h4_fixed_budget_bottom_component
                )
                else None
            ),
            selected_mode_packet_manifest_sha256=(
                args.selected_mode_packet_manifest_sha256
                if (
                    args.v5_h4_setup_only
                    or args.v6_h4_post_compaction_setup_only
                    or args.v7_h4_exact_side_limit_setup_only
                    or args.v7_h4_exact_side_full_formal
                    or args.v6_h4_port_modal_bottom_component
                    or args.v7_h4_streamed_bottom_producer
                    or args.v7_h4_streamed_bottom_consumer
                    or args.v8_h4_layer_sweep_bottom
                    or args.v10_h4_j1_inner_fgmres
                    or args.v10_h4_side_response_packet_pilot
                    or args.v10_h4_side_response_packet_full_producer
                    or args.v11_h4_bottom_packet_algebra
                    or args.v5_h4_blr_side_component
                    or args.v5_h4_fixed_budget_bottom_component
                )
                else None
            ),
        )
        print(json.dumps(_json_safe(plan), ensure_ascii=False, sort_keys=True))
        return 0
    if not args.launched_by_task038_watchdog:
        print(
            "V3-7 worker requires --launched-by-task038-watchdog",
            file=sys.stderr,
        )
        return 2
    if MPI.COMM_WORLD.size != 8:
        print(
            f"V3-7 worker requires MPI8, got MPI{MPI.COMM_WORLD.size}",
            file=sys.stderr,
        )
        return 2
    try:
        if component_route:
            specification = load_and_resolve(args.input_path)
            payload = specification.as_jsonable()
            from benchmarks.task039_v4_h4_hybrid_direct import (
                validate_v4_h4_specification,
            )

            validate_v4_h4_specification(specification)
            if specification.method.get("kind") != "hybrid_iterative":
                raise ValueError("V5 h4 component requires hybrid_iterative")
            packet_identity = (
                None
                if (
                    args.v8_h4_layer_block_reconstruction
                    or args.v9_h4_bare_f_side
                    or args.v9_h4_layer_supernode_bottom
                    or args.v10_h4_supernode_factor_integrity
                    or args.v10_h4_sn2_j_only
                    or args.v10_h4_j1_inner_fgmres
                    or args.v10_h4_side_response_packet_consumer
                    or args.v10_h4_side_response_packet_compression
                    or args.v11_h4_bottom_packet_algebra
                )
                else json.loads(
                    Path(args.selected_mode_packet_identity).read_text(encoding="utf-8")
                )
            )
        else:
            payload = load_v3_7_official_payload(args.input_path)
            packet_identity = None
        result = run_task039_v3_7_diagnostic(
            payload,
            args.run_directory,
            source_sha=args.source_sha,
            direct_run_dir=V3_7_DIRECT_RUN_ROOT,
            recovery_runner=(
                None
                if (
                    args.candidate_b_only
                    or args.candidate_c_only
                    or args.candidate_e_side_only
                    or (component_route and not args.v7_h4_exact_side_full_formal)
                )
                else run_v3_7_recovery_runner
            ),
            candidate_b_only=args.candidate_b_only,
            candidate_c_only=args.candidate_c_only,
            candidate_d_only=args.candidate_d_only,
            candidate_d_qualified=args.candidate_d_qualified,
            candidate_e_side_only=args.candidate_e_side_only,
            v5_h4_setup_only=args.v5_h4_setup_only,
            v6_h4_post_compaction_setup_only=args.v6_h4_post_compaction_setup_only,
            v6_h4_exact_spool_root=args.v6_h4_exact_spool_root,
            v7_h4_exact_side_limit_setup_only=(args.v7_h4_exact_side_limit_setup_only),
            v7_h4_exact_side_exact_spool_root=(args.v7_h4_exact_side_exact_spool_root),
            v7_h4_exact_side_full_formal=args.v7_h4_exact_side_full_formal,
            v6_h4_port_modal_bottom_only=args.v6_h4_port_modal_bottom_component,
            v6_h4_port_modal_exact_spool_root=(args.v6_h4_port_modal_exact_spool_root),
            v7_h4_streamed_bottom_producer=args.v7_h4_streamed_bottom_producer,
            v7_h4_streamed_bottom_consumer=args.v7_h4_streamed_bottom_consumer,
            v7_h4_streamed_bottom_consumer_basis_manifest=(
                args.v7_h4_streamed_bottom_consumer_basis_manifest
            ),
            v7_h4_streamed_bottom_consumer_basis_manifest_sha256=(
                args.v7_h4_streamed_bottom_consumer_basis_manifest_sha256
            ),
            v7_h4_streamed_bottom_consumer_exact_spool_root=(
                args.v7_h4_streamed_bottom_consumer_exact_spool_root
            ),
            v8_h4_layer_block_reconstruction=args.v8_h4_layer_block_reconstruction,
            v8_h4_layer_sweep_bottom=args.v8_h4_layer_sweep_bottom,
            v8_h4_layer_sweep_exact_spool_root=(
                args.v8_h4_layer_sweep_exact_spool_root
            ),
            v9_h4_bare_f_side=args.v9_h4_bare_f_side,
            v9_h4_bare_f_side_exact_spool_root=(
                args.v9_h4_bare_f_side_exact_spool_root
            ),
            v9_h4_layer_supernode_bottom=args.v9_h4_layer_supernode_bottom,
            v9_h4_layer_supernode_exact_spool_root=(
                args.v9_h4_layer_supernode_exact_spool_root
            ),
            v10_h4_supernode_factor_integrity=args.v10_h4_supernode_factor_integrity,
            v10_h4_supernode_factor_integrity_exact_spool_root=(
                args.v10_h4_supernode_factor_integrity_exact_spool_root
            ),
            v10_h4_sn2_j_only=args.v10_h4_sn2_j_only,
            v10_h4_sn2_j_only_exact_spool_root=(
                args.v10_h4_sn2_j_only_exact_spool_root
            ),
            v10_h4_j1_inner_fgmres=args.v10_h4_j1_inner_fgmres,
            v10_h4_j1_inner_fgmres_exact_spool_root=(
                args.v10_h4_j1_inner_fgmres_exact_spool_root
            ),
            v10_h4_side_response_packet_pilot=args.v10_h4_side_response_packet_pilot,
            v10_h4_side_response_packet_pilot_exact_spool_root=(
                args.v10_h4_side_response_packet_pilot_exact_spool_root
            ),
            v10_h4_side_response_packet_pilot_output_root=(
                args.v10_h4_side_response_packet_pilot_output_root
            ),
            v10_h4_side_response_packet_consumer=args.v10_h4_side_response_packet_consumer,
            v10_h4_side_response_packet_consumer_manifest=(
                args.v10_h4_side_response_packet_consumer_manifest
            ),
            v10_h4_side_response_packet_consumer_manifest_sha256=(
                args.v10_h4_side_response_packet_consumer_manifest_sha256
            ),
            v10_h4_side_response_packet_full_producer=(
                args.v10_h4_side_response_packet_full_producer
            ),
            v10_h4_side_response_packet_full_producer_exact_spool_root=(
                args.v10_h4_side_response_packet_full_producer_exact_spool_root
            ),
            v10_h4_side_response_packet_full_producer_output_root=(
                args.v10_h4_side_response_packet_full_producer_output_root
            ),
            v10_h4_side_response_packet_compression=(
                args.v10_h4_side_response_packet_compression
            ),
            v10_h4_side_response_packet_compression_manifest=(
                args.v10_h4_side_response_packet_compression_manifest
            ),
            v10_h4_side_response_packet_compression_manifest_sha256=(
                args.v10_h4_side_response_packet_compression_manifest_sha256
            ),
            v10_h4_side_response_packet_compression_producer_source_sha=(
                args.v10_h4_side_response_packet_compression_producer_source_sha
            ),
            v11_h4_bottom_packet_algebra=args.v11_h4_bottom_packet_algebra,
            v11_h4_bottom_packet_algebra_exact_spool_root=(
                args.v11_h4_bottom_packet_algebra_exact_spool_root
            ),
            v11_h4_bottom_packet_algebra_packet_manifest=(
                args.v11_h4_bottom_packet_algebra_packet_manifest
            ),
            v11_h4_bottom_packet_algebra_packet_manifest_sha256=(
                args.v11_h4_bottom_packet_algebra_packet_manifest_sha256
            ),
            v11_h4_bottom_packet_algebra_producer_diagnostic=(
                args.v11_h4_bottom_packet_algebra_producer_diagnostic
            ),
            v5_h4_blr_side_only=args.v5_h4_blr_side_component,
            v5_h4_fixed_budget_bottom_only=args.v5_h4_fixed_budget_bottom_component,
            v5_h4_fixed_budget_exact_spool_root=(
                args.v5_h4_fixed_budget_exact_spool_root
            ),
            v5_h4_blr_profile=args.v5_h4_blr_profile,
            selected_mode_packet_manifest=(
                args.selected_mode_packet_manifest if component_route else None
            ),
            selected_mode_packet_identity=packet_identity,
            selected_mode_packet_manifest_sha256=(
                args.selected_mode_packet_manifest_sha256 if component_route else None
            ),
            record_path=(
                Path(args.run_directory).resolve()
                / "numerical_output"
                / "v3_v7_diagnostic.json"
            ),
        )
    except Exception as exc:
        traceback_path = _write_v3_7_worker_traceback(args.run_directory)
        traceback_text = traceback.format_exc()
        print(
            f"V3-7 worker failed before completion: {type(exc).__name__}: {exc}\n"
            f"Full traceback: {traceback_path}\n{traceback_text}",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(_json_safe(result), ensure_ascii=False, sort_keys=True))
    return (
        0
        if result.get("status")
        in {
            "completed",
            "setup_only_completed",
            "component_completed",
            "component_stable_preferred_resource_pending",
            "component_numerical_pass_resource_pending",
            "producer_completed",
            "consumer_completed",
            "full_formal_completed",
            "component_forensic_completed",
            "component_sn2_j_stable_resource_pending",
            "component_fgmres_completed",
            "compression_completed",
            "component_v11_bottom_packet_algebra_completed",
        }
        else 3
    )


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "V3_7_ABSOLUTE_HARD_BYTES",
    "V3_7_DIRECT_PRODUCER_SHA",
    "V3_7_DIRECT_RUN_ROOT",
    "V3_7_MAX_IT",
    "V3_7_MATRIX_REPEAT_TOLERANCE",
    "V3_7_PROFILE_ID",
    "V3_8_CANDIDATE_B_BUDGETS",
    "V3_8_CANDIDATE_B_MEDIAN_LIMIT",
    "V3_8_CANDIDATE_B_WORST_LIMIT",
    "V3_8_CANDIDATE_C_MEDIAN_LIMIT",
    "V3_8_CANDIDATE_C_WORST_LIMIT",
    "V3_8_CANDIDATE_E_MEDIAN_LIMIT",
    "V3_8_CANDIDATE_E_WORST_LIMIT",
    "V3_8_CANDIDATE_E_TRAINING_SEEDS",
    "V3_8_CANDIDATE_D_CLASSIFICATION",
    "V3_8_CANDIDATE_D_QUALIFIED_CLASSIFICATION",
    "V3_8_CANDIDATE_D_QUALIFIED_METHOD",
    "V3_8_CANDIDATE_D_QUALIFICATION_SCOPE",
    "V5_H4_BLR_SIDE_METHOD",
    "V5_H4_BLR_SIDE_PROFILE_ID",
    "run_v5_h4_mumps_blr_side_component",
    "V5_H4_FIXED_BUDGET_SIDE_METHOD",
    "V5_H4_FIXED_BUDGET_SIDE_PROFILE_ID",
    "V5_H4_FIXED_BUDGET",
    "run_v5_h4_fixed_budget_bottom_component",
    "V6_H4_PORT_MODAL_BOTTOM_PROFILE_ID",
    "V6_H4_PORT_MODAL_BOTTOM_METHOD",
    "V6_H4_PORT_MODAL_BOTTOM_HARD_STOP_BYTES",
    "run_v6_h4_port_modal_bottom_component",
    "V7_H4_EXACT_SIDE_LIMIT_PROFILE_ID",
    "V7_H4_EXACT_SIDE_LIMIT_METHOD",
    "V7_H4_EXACT_SIDE_LIMIT_SCHEMA",
    "V7_H4_EXACT_SIDE_LIMIT_HARD_STOP_BYTES",
    "V7_H4_EXACT_SPOOL_ROOT",
    "V7_STREAMED_PETROV_METHOD",
    "V7_STREAMED_PETROV_CONSUMER_METHOD",
    "V7_STREAMED_PETROV_PROFILE_ID",
    "V7_STREAMED_PETROV_CONSUMER_PROFILE_ID",
    "V7_STREAMED_PETROV_HARD_STOP_BYTES",
    "V7_STREAMED_PETROV_CONSUMER_HARD_STOP_BYTES",
    "run_v7_h4_streamed_bottom_basis_producer",
    "run_v7_h4_streamed_bottom_petrov_consumer",
    "V8_H4_LAYER_BLOCK_PROFILE_ID",
    "V8_H4_LAYER_BLOCK_METHOD",
    "V8_H4_LAYER_BLOCK_SCHEMA",
    "V8_H4_LAYER_BLOCK_HARD_STOP_BYTES",
    "run_v8_h4_layer_block_reconstruction_component",
    "V8_H4_LAYER_SWEEP_PROFILE_ID",
    "V8_H4_LAYER_SWEEP_METHOD",
    "V8_H4_LAYER_SWEEP_SCHEMA",
    "V8_H4_LAYER_SWEEP_HARD_STOP_BYTES",
    "run_v8_h4_layer_sweep_bottom_component",
    "V9_H4_BARE_F_SIDE_PROFILE_ID",
    "V9_H4_BARE_F_SIDE_METHOD",
    "V9_H4_BARE_F_SIDE_SCHEMA",
    "V9_H4_BARE_F_SIDE_HARD_STOP_BYTES",
    "V9_H4_LAYER_SUPERNODE_BOTTOM_FLAG",
    "V9_H4_LAYER_SUPERNODE_EXACT_SPOOL_ROOT_FLAG",
    "V9_H4_LAYER_SUPERNODE_PROFILE_ID",
    "V9_H4_LAYER_SUPERNODE_METHOD",
    "V9_H4_LAYER_SUPERNODE_SCHEMA",
    "V9_H4_LAYER_SUPERNODE_HARD_STOP_BYTES",
    "run_v9_h4_layer_supernode_bottom_component",
    "V10_H4_SUPERNODE_FACTOR_INTEGRITY_FLAG",
    "V10_H4_SUPERNODE_FACTOR_INTEGRITY_EXACT_SPOOL_ROOT_FLAG",
    "V10_H4_SUPERNODE_FACTOR_INTEGRITY_PROFILE_ID",
    "V10_H4_SUPERNODE_FACTOR_INTEGRITY_METHOD",
    "V10_H4_SUPERNODE_FACTOR_INTEGRITY_SCHEMA",
    "V10_H4_SUPERNODE_FACTOR_INTEGRITY_HARD_STOP_BYTES",
    "run_v10_h4_supernode_factor_integrity",
    "V10_H4_SN2_J_ONLY_FLAG",
    "V10_H4_SN2_J_ONLY_EXACT_SPOOL_ROOT_FLAG",
    "V10_H4_SN2_J_ONLY_PROFILE_ID",
    "V10_H4_SN2_J_ONLY_METHOD",
    "V10_H4_SN2_J_ONLY_SCHEMA",
    "V10_H4_SN2_J_ONLY_HARD_STOP_BYTES",
    "run_v10_h4_sn2_j_only",
    "V10_H4_J1_INNER_FGMRES_FLAG",
    "V10_H4_J1_INNER_FGMRES_EXACT_SPOOL_ROOT_FLAG",
    "V10_H4_J1_INNER_FGMRES_PROFILE_ID",
    "V10_H4_J1_INNER_FGMRES_METHOD",
    "V10_H4_J1_INNER_FGMRES_SCHEMA",
    "V10_H4_J1_INNER_FGMRES_HARD_STOP_BYTES",
    "run_v10_h4_j1_inner_fgmres",
    "V10_H4_SIDE_RESPONSE_PACKET_PILOT_FLAG",
    "V10_H4_SIDE_RESPONSE_PACKET_PILOT_EXACT_SPOOL_ROOT_FLAG",
    "V10_H4_SIDE_RESPONSE_PACKET_PILOT_OUTPUT_ROOT_FLAG",
    "V10_H4_SIDE_RESPONSE_PACKET_PILOT_PROFILE_ID",
    "V10_H4_SIDE_RESPONSE_PACKET_PILOT_METHOD",
    "V10_H4_SIDE_RESPONSE_PACKET_PILOT_SCHEMA",
    "V10_H4_SIDE_RESPONSE_PACKET_PILOT_HARD_STOP_BYTES",
    "V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_FLAG",
    "V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_MANIFEST_FLAG",
    "V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_MANIFEST_SHA256_FLAG",
    "V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_PROFILE_ID",
    "V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_METHOD",
    "V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_SCHEMA",
    "V10_H4_SIDE_RESPONSE_PACKET_CONSUMER_HARD_STOP_BYTES",
    "V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_FLAG",
    "V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_EXACT_SPOOL_ROOT_FLAG",
    "V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_OUTPUT_ROOT_FLAG",
    "V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_PROFILE_ID",
    "V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_METHOD",
    "V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_SCHEMA",
    "V10_H4_SIDE_RESPONSE_PACKET_FULL_PRODUCER_HARD_STOP_BYTES",
    "V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_FLAG",
    "V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_MANIFEST_FLAG",
    "V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_MANIFEST_SHA256_FLAG",
    "V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_PRODUCER_SOURCE_SHA_FLAG",
    "V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_PROFILE_ID",
    "V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_METHOD",
    "V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_SCHEMA",
    "V10_SIDE_RESPONSE_PACKET_FROZEN_HOLDOUT_MANIFEST_SHA256",
    "V10_H4_SIDE_RESPONSE_PACKET_FULL_RECHECK_SCHEMA",
    "V10_H4_SIDE_RESPONSE_PACKET_COMPRESSION_HARD_STOP_BYTES",
    "V10_SIDE_RESPONSE_PACKET_FROZEN_SELECTED_COLUMNS",
    "v10_side_response_packet_pilot_schedule",
    "_v10_side_response_resolved_provenance",
    "run_v10_h4_side_response_packet_pilot",
    "run_v10_h4_side_response_packet_consumer",
    "run_v10_h4_side_response_packet_compression",
    "V11_BOTTOM_PACKET_ALGEBRA_FLAG",
    "V11_BOTTOM_PACKET_ALGEBRA_EXACT_SPOOL_ROOT_FLAG",
    "V11_BOTTOM_PACKET_ALGEBRA_PACKET_MANIFEST_FLAG",
    "V11_BOTTOM_PACKET_ALGEBRA_PACKET_MANIFEST_SHA256_FLAG",
    "V11_BOTTOM_PACKET_ALGEBRA_PRODUCER_DIAGNOSTIC_FLAG",
    "V11_BOTTOM_PACKET_ALGEBRA_PROFILE_ID",
    "V11_BOTTOM_PACKET_ALGEBRA_METHOD",
    "V11_BOTTOM_PACKET_ALGEBRA_SCHEMA",
    "V11_V7_MODAL_AMPLITUDES_SHA256",
    "run_v11_h4_bottom_packet_algebra",
    "recheck_v10_h4_full_side_response_packet",
    "run_v9_h4_bare_f_side_diagnostic",
    "build_v3_7_execution_plan",
    "check_v3_7_integrated_physics",
    "compare_v3_7_hybrid_candidate_to_direct",
    "deterministic_global_index_vectors",
    "load_v3_7_direct_inventory",
    "load_v3_7_official_payload",
    "run_task039_v3_7_side_correction_survey",
    "run_task039_v3_7_diagnostic",
    "run_v3_8_candidate_b_budget_sequence",
    "_run_v3_8_candidate_d_campaign",
    "_run_v3_8_candidate_e_side_campaign",
    "run_v3_7_recovery_runner",
    "run_v3_7_stage_sequence",
    "v3_7_execution_dry_run",
    "launch_v3_7_with_task038_watchdog",
    "v3_7_profile_from_resolved",
    "v3_7_watchdog_policy",
    "validate_v3_7_resolved_identity",
]
