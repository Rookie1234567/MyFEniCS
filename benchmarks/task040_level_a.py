"""Thin Task040 Level-A runner over the reviewed PETSc transmission carrier."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.run_task037b_hybrid_iterative import collective_heap_cleanup
from benchmarks.task034_wsl_resources import (
    resource_authority_sample,
    wsl_memory_snapshot,
)
from benchmarks.task039_v3_7_orchestration import (
    _load_v5_blr_reference_spool_remapped,
    _load_v5_fixed_budget_spool_shards,
    _v9_frozen_holdout_identity,
)
from benchmarks.task039_v3_side_oracle import _build_research_explicit_side_components
from benchmarks.task039_v4_selected_mode_packet import (
    stream_task039_v4_selected_mode_columns,
)
from benchmarks.task040_v6_2_interface_schur import (
    V6_2_INTERFACE_JOINT_COUNT,
    V6_2_INTERFACE_LOWER_COUNT,
    V6_2_INTERFACE_SCHUR_FLAG,
    V6_2_INTERFACE_SCHUR_METHOD,
    V6_2_INTERFACE_SCHUR_PROFILE_ID,
    V6_2_INTERFACE_SCHUR_SCHEMA,
    V6_2_INTERFACE_UPPER_COUNT,
    V7_IDENTITY_HARD_SECONDS,
    V7_IDENTITY_TARGET_SECONDS,
    V7_MOVING_PML_FULL_STATE_FLAG,
    V7_MOVING_PML_FULL_STATE_METHOD,
    V7_MOVING_PML_FULL_STATE_PROFILE_ID,
    V7_MOVING_PML_FULL_STATE_SCHEMA,
    V7_PREFERRED_MEMORY_BYTES,
    V7_SCALE_NORMALIZED_IDENTITY_FLAG,
    V7_SCALE_NORMALIZED_IDENTITY_FORMAL_SCHEMA,
    V7_SCALE_NORMALIZED_IDENTITY_METHOD,
    V7_SCALE_NORMALIZED_IDENTITY_PROFILE_ID,
    V8_ADAPTIVE_HARD_STOP_BYTES,
    V8_ADAPTIVE_ONE_APPLY_TARGET_SECONDS,
    V8_ADAPTIVE_PREFERRED_MEMORY_BYTES,
    V8_ADAPTIVE_SCHWARZ_ONLY_FLAG,
    V8_ADAPTIVE_SCHWARZ_ONLY_METHOD,
    V8_ADAPTIVE_SCHWARZ_ONLY_PROFILE_ID,
    V8_ADAPTIVE_SCHWARZ_ONLY_SCHEMA,
    V8_ADAPTIVE_SETUP_TARGET_SECONDS,
    V8_ADAPTIVE_STAGE_B1_ONLY_FLAG,
    V8_ADAPTIVE_STAGE_B1_ONLY_METHOD,
    V8_ADAPTIVE_STAGE_B1_ONLY_PROFILE_ID,
    V8_ADAPTIVE_STAGE_B1_ONLY_SCHEMA,
    V8_ADAPTIVE_STAGE_BC_ONLY_FLAG,
    V8_ADAPTIVE_STAGE_BC_ONLY_METHOD,
    V8_ADAPTIVE_STAGE_BC_ONLY_PROFILE_ID,
    V8_ADAPTIVE_STAGE_BC_ONLY_SCHEMA,
    V8_ADAPTIVE_TIMEOUT_SECONDS,
    V8_FULL_SPECTRUM_CHECKPOINTS,
    V8_FULL_SPECTRUM_MIN_AVAILABLE_BYTES,
    V8_FULL_SPECTRUM_ONE_APPLY_TARGET_SECONDS,
    V8_FULL_SPECTRUM_ONLY_FLAG,
    V8_FULL_SPECTRUM_ONLY_METHOD,
    V8_FULL_SPECTRUM_ONLY_PROFILE_ID,
    V8_FULL_SPECTRUM_ONLY_SCHEMA,
    V8_FULL_SPECTRUM_PREFERRED_MEMORY_BYTES,
    V8_FULL_SPECTRUM_SETUP_TARGET_SECONDS,
    V8_FULL_SPECTRUM_SOURCES,
    V8_FULL_SPECTRUM_TIMEOUT_SECONDS,
    V8_FULL_SPECTRUM_TRANSFORM_TARGET_SECONDS,
    V9_C0_COLUMNS_PER_PATCH,
    V9_C0_EXPLICIT_COARSE_ONLY_FLAG,
    V9_C0_EXPLICIT_COARSE_ONLY_METHOD,
    V9_C0_EXPLICIT_COARSE_ONLY_PROFILE_ID,
    V9_C0_EXPLICIT_COARSE_ONLY_SCHEMA,
    V9_C0_HARD_STOP_BYTES,
    V9_C0_MARKER_SEQUENCE,
    V9_C0_MIN_AVAILABLE_BYTES,
    V9_C0_ONE_APPLY_TARGET_SECONDS,
    V9_C0_PATCH_COUNT,
    V9_C0_PREFERRED_MEMORY_BYTES,
    V9_C0_SETUP_TARGET_SECONDS,
    V9_C0_SOURCES,
    V9_C0_TIMEOUT_SECONDS,
    V9_C0_TOTAL_COARSE_DOF,
    V9_C0_WARNING_MEMORY_BYTES,
    V9_SOURCE_BRIDGE_ONLY_FLAG,
    V9_SOURCE_BRIDGE_ONLY_METHOD,
    V9_SOURCE_BRIDGE_ONLY_PROFILE_ID,
    V9_SOURCE_BRIDGE_ONLY_SCHEMA,
    V9_SOURCE_BRIDGE_ONLY_SOURCES,
    build_v6_2_exact_qualification_plan,
)
from src.common.modes_3d import outgoing_port_modes_3d
from src.coupling.hybrid_internal_modes import (
    _ReusableInterfaceLifter,
    _trace_from_streamed_local_values,
)
from src.io.input_validation import (
    load_and_resolve,
    simulation_config_3d_from_normalized,
)
from src.io.resolved_config import resolved_config_sha256
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.runners.task039_hybrid_iterative import make_task039_hybrid_iterative_profile
from src.solvers.floquet_background_hcurl_s3_pilot import (
    S3B_CANDIDATE_R64_LIMIT,
    S3B_CANDIDATE_R256_LIMIT,
    S3B_EXPECTED_ACTIVE_ROWS,
    S3B_EXPECTED_MODE_COUNT,
    S3B_EXPECTED_ROWS_PER_MODE,
    S3B_EXTERNAL_SOURCE_COLUMN,
    S3B_EXTERNAL_SOURCE_LABEL,
    S3B_EXTERNAL_SOURCE_SEED,
    S3B_EXTERNAL_SOURCE_SIGN,
    S3B_FGMRES_INITIAL_MAX_IT,
    S3B_FGMRES_RESTART,
    S3B_FIVE_SOURCE_MAX_IT,
    S3B_FIVE_SOURCE_RESIDUAL_LIMIT,
    S3B_FIVE_SOURCE_STRICT_RESIDUAL_LIMIT,
    S3B_MAX_LOCAL_ROWS,
    S3B_MPI_SIZE,
    S3B_RSS_HARD_BYTES,
    S3B_SWAP_LIMIT_BYTES,
    S3B_WALL_CAP_SECONDS,
)
from src.solvers.hybrid_bare_f_authority import (
    V5_BARE_F_METHOD,
    V5_BARE_F_SCHEMA,
    V5_BARE_F_SOURCE_LABELS,
    assemble_current_bare_f_authority_system,
    build_current_bare_f_rhs,
    build_current_gamma_layout,
    build_v5_operator_semantics_audit,
    canonical_layout_tokens,
    compact_gamma_values_for_vector,
    run_current_bare_f_authority,
)
from src.solvers.hybrid_bare_f_external_lor_pilot import (
    V9_E_LOR_BARE_F_EXTERNAL_IMPLEMENTATION_FAILURE,
    V9_E_LOR_BARE_F_EXTERNAL_MARKER_SEQUENCE,
    V9_E_LOR_BARE_F_EXTERNAL_NUMERICAL_NO_SIGNAL,
    V9_E_LOR_BARE_F_EXTERNAL_ONLY_FLAG,
    V9_E_LOR_BARE_F_EXTERNAL_ONLY_HARD_STOP_BYTES,
    V9_E_LOR_BARE_F_EXTERNAL_ONLY_INPUT,
    V9_E_LOR_BARE_F_EXTERNAL_ONLY_METHOD,
    V9_E_LOR_BARE_F_EXTERNAL_ONLY_MPI_SIZE,
    V9_E_LOR_BARE_F_EXTERNAL_ONLY_PROFILE_ID,
    V9_E_LOR_BARE_F_EXTERNAL_ONLY_SCHEMA,
    V9_E_LOR_BARE_F_EXTERNAL_ONLY_TIMEOUT_SECONDS,
    V9_E_LOR_BARE_F_EXTERNAL_POSITIVE,
    V9_E_LOR_BARE_F_EXTERNAL_RESOURCE_UNAVAILABLE,
)
from src.solvers.hybrid_exact_authority_compat import (
    V4_CANONICAL_SOURCE_BINDING_REASON,
    V4_CANONICAL_SOURCE_BINDING_UNAVAILABLE,
    V4_EXACT_AUTHORITY_FAILURE,
    V4_EXACT_AUTHORITY_LABELS,
    canonical_binding_failure_audit,
    inspect_canonical_source_authority,
)
from src.solvers.hybrid_interface_basis import (
    build_artificial_gamma_column,
    build_group_basis_columns,
    build_lower_fourier_trace_columns,
    build_mass_dual_from_active_vec,
    canonical_external_mode_metadata_sha256,
    canonical_mode_keys_sha256,
    canonical_selected_packet_beta_sha256,
    collect_streamed_trace_basis,
)
from src.solvers.hybrid_interface_fgmres import (
    audit_v3_full_side_one_apply,
    run_v3_full_span_right_fgmres_batch,
)
from src.solvers.hybrid_interface_packet import (
    PacketGroup,
    canonical_key_sha256,
    finalize_manifest,
    load_packet_shard,
    load_small_matrix,
    recover_owner_local_y_from_packet_v,
    redistribute_packet_group_rows,
    transfer_right_basis_to_packet_gram,
    write_group_shard,
)
from src.solvers.hybrid_interface_packet_dolfinx import (
    CanonicalOwnerLocalBasis,
    audit_owner_local_basis_round_trip,
    build_dolfinx_plane_gamma_layout,
    build_gamma_canonical_layout,
    canonicalize_owner_local_basis_in_place,
    reconstruct_owner_local_basis,
)
from src.solvers.hybrid_interface_petsc_coupled import (
    build_petsc_coupled_full_side_action,
)
from src.solvers.hybrid_interface_run_b import (
    build_v1_3_projected_transmission,
    build_v2_packet_projected_transmission,
)
from src.solvers.hybrid_interface_schur import (
    build_distributed_petrov_action,
    build_petsc_interface_schur_oracle,
)
from src.solvers.hybrid_layer_block import (
    run_v1_1_right_preconditioned_fgmres_batch,
)
from src.solvers.hybrid_local_dtn_action import assemble_hybrid_local_dtn_action_system
from src.solvers.hybrid_route_c import (
    ROUTE_C_CHECKPOINTS,
    ROUTE_C_LABELS,
    run_route_c_online_fgmres,
)
from src.solvers.hybrid_side_impedance import (
    TASK040_LEVEL_A_SOURCE_LABELS,
    _petsc_matrix_hash,
    assemble_reduced_artificial_interface_tangential_mass,
    audit_artificial_z_interface_support,
    audit_petsc_level_a_one_apply,
    build_level_a_cell_recovery_group_rows,
    build_level_a_oracle,
)

TASK040_LEVEL_A_METHOD = "task040_level_a_bare_f_transmission"
TASK040_LEVEL_A_SCHEMA = "task040.level_a.bare_f_transmission.v1"
TASK040_LEVEL_A_PROFILE_ID = "task040.level_a.h4.bottom.v1"
TASK040_LEVEL_A_HARD_STOP_BYTES = 45 * 2**30
TASK040_LEVEL_A_TIMEOUT_SECONDS = 21600
TASK040_LEVEL_A_MPI_SIZE = 8
TASK040_LEVEL_A_THREADS = 1
TASK040_LEVEL_A_SEQUENCE = (0, 1, 2, 2, 1, 0)
TASK040_LEVEL_A_BETA_AUTHORITY = (
    "src.solvers.dtn_port_3d::_zero_order_local_robin_forms"
)
TASK040_V1_1_SCALAR_KRYLOV_FLAG = "--v1-1-scalar-krylov"
TASK040_V1_1_METHOD = "task040_v1_1_scalar_krylov"
TASK040_V1_1_SCHEMA = "task040.v1_1.scalar_krylov.v1"
TASK040_V1_1_PROFILE_ID = "task040.v1_1.h4.bottom.scalar_krylov.v1"
TASK040_V1_2_INTERFACE_SCHUR_FLAG = "--v1-2-interface-schur"
TASK040_V1_2_METHOD = "task040_v1_2_interface_schur"
TASK040_V1_2_SCHEMA = "task040.v1_2.interface_schur.v1"
TASK040_V1_2_PROFILE_ID = "task040.v1_2.h4.run_b.v1"
TASK040_V1_2_PROBE_MANIFEST = (
    "benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/"
    "task040_v1_2_probe_manifest_v1.json"
)
TASK040_V1_2_PROBE_MANIFEST_SHA256 = (
    "7a03b2cf80fe5081d1fe1248b9d4c79f3ef4e955a8014e905c2f2ca82797baad"
)
TASK040_V1_2_INPUT_SHA256 = (
    "4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811"
)
TASK040_V1_2_PHYSICAL_MODEL_SHA256 = (
    "8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c"
)
TASK040_V1_2_SELECTED_MANIFEST_SHA256 = (
    "2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067"
)
TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256 = (
    "a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384"
)
TASK040_V1_2_LOWER_RESOLVED_MODE_METADATA_SHA256 = (
    "dde523dc62c73f7bd50953958fde42d42d0cfd5756c16329b16915e13c4742da"
)
TASK040_V1_2_LOWER_LEGACY_BETA_METADATA_SHA256 = (
    "a58a3c6bc335bb5ae7f6b929a7abce4c193dedb27b115f17304091afb353318c"
)
TASK040_V2_INTERFACE_PACKET_PRODUCER_FLAG = "--v2-interface-packet-producer"
TASK040_V2_INTERFACE_PACKET_METHOD = "task040_v2_interface_packet_producer"
TASK040_V2_INTERFACE_PACKET_SCHEMA = "task040.v2.interface_packet_producer.v1"
TASK040_V2_INTERFACE_PACKET_PROFILE_ID = "task040.v2.a1.interface_packet_producer.v1"
TASK040_V2_INTERFACE_PACKET_PREFERRED_BYTES = 45 * 2**30
TASK040_V2_INTERFACE_PACKET_HARD_STOP_BYTES = 55 * 2**30
TASK040_V2_INTERFACE_PACKET_CONSUMER_FLAG = "--v2-interface-packet-consumer"
TASK040_V2_INTERFACE_PACKET_CONSUMER_METHOD = "task040_v2_interface_packet_consumer"
TASK040_V2_INTERFACE_PACKET_CONSUMER_SCHEMA = "task040.v2.interface_packet_consumer.v1"
TASK040_V2_INTERFACE_PACKET_CONSUMER_PROFILE_ID = (
    "task040.v2.b2.interface_packet_consumer.v1"
)
TASK040_V2_INTERFACE_PACKET_MANIFEST_SHA256 = (
    "19de50f3cdb32766bf6f13fc55c9ac498b21a9a00ddc261768d7d55b7c9da8b0"
)
TASK040_V3_2_COUPLED_INTERFACE_FLAG = "--v3-2-coupled-interface"
TASK040_V3_2_COUPLED_INTERFACE_METHOD = "task040_v3_2_coupled_interface"
TASK040_V3_2_COUPLED_INTERFACE_SCHEMA = "task040.v3_2.coupled_interface.v1"
TASK040_V3_2_COUPLED_INTERFACE_PROFILE_ID = "task040.v3_2.h4.coupled_interface.v1"
TASK040_V3_2_AUGMENTED_PACKET_MANIFEST_SHA256 = (
    "f480189663ef293ec4f809818e322186d75a205f725a3aa35dc12c2d24aad209"
)
TASK040_V3_2_TRUE_JOINT_CONTENT_SHA256 = (
    "ed7c973c92ff4704a687c9d61032930bb458076e552892c988990cf893e6e035"
)
TASK040_V3_2_PRODUCER_SOURCE_SHA = "fa1720d8f137de81023cd45d6a43262d386e6521"
TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_FLAG = "--v4-exact-authority-compatibility"
TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_METHOD = (
    "task040_v4_exact_authority_compatibility"
)
TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_SCHEMA = (
    "task040.v4.exact_authority_compatibility.v1"
)
TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_PROFILE_ID = (
    "task040.v4.h4.exact_authority_compatibility.v1"
)
TASK040_V4_FROZEN_BRANCH = "codex/20260822-task40-hybrid-side-factor-pc"
TASK040_V4_FROZEN_AUTHORITY_SOURCE_SHA = "112ac4913a531ae5c5aab941ac88f005a95b9dc4"
TASK040_V5_FRESH_BARE_F_AUTHORITY_FLAG = "--v5-fresh-bare-f-authority"
TASK040_V5_FRESH_BARE_F_AUTHORITY_METHOD = V5_BARE_F_METHOD
TASK040_V5_FRESH_BARE_F_AUTHORITY_SCHEMA = V5_BARE_F_SCHEMA
TASK040_V5_FRESH_BARE_F_AUTHORITY_PROFILE_ID = (
    "task040.v5.h4.current_layout_bare_f_authority.v1"
)
TASK040_V5_FRESH_BARE_F_PREFERRED_BYTES = 55 * 2**30
TASK040_V5_FRESH_BARE_F_WARNING_BYTES = 58 * 2**30
TASK040_V5_FRESH_BARE_F_HARD_STOP_BYTES = 64 * 2**30
TASK040_V5_FRESH_BARE_F_MIN_AVAILABLE_BYTES = 90 * 2**30
TASK040_V5_FRESH_BARE_F_MIN_DISK_BYTES = 20 * 2**30
TASK040_V5_ROUTE_C_FLAG = "--v5-route-c"
TASK040_V5_ROUTE_C_METHOD = "task040_v5_route_c_online_long_fgmres"
TASK040_V5_ROUTE_C_SCHEMA = "task040.v5.route_c.online_long_fgmres.v1"
TASK040_V5_ROUTE_C_PROFILE_ID = "task040.v5.h4.route_c.online_long_fgmres.v1"
TASK040_V5_ROUTE_C_HARD_STOP_BYTES = 45 * 2**30
TASK040_V5_ROUTE_C_HEADROOM_BYTES = 4 * 2**30
TASK040_V5_ROUTE_C_MIN_AVAILABLE_BYTES = (
    TASK040_V5_ROUTE_C_HARD_STOP_BYTES + TASK040_V5_ROUTE_C_HEADROOM_BYTES
)
TASK040_V5_ROUTE_C_MIN_DISK_BYTES = 20 * 2**30
TASK040_V5_ROUTE_C_RESOURCE_BLOCKED = "ROUTE_C_RESOURCE_BLOCKED"
TASK040_V6_2_INTERFACE_SCHUR_FLAG = V6_2_INTERFACE_SCHUR_FLAG
TASK040_V6_2_INTERFACE_SCHUR_METHOD = V6_2_INTERFACE_SCHUR_METHOD
TASK040_V6_2_INTERFACE_SCHUR_SCHEMA = V6_2_INTERFACE_SCHUR_SCHEMA
TASK040_V6_2_INTERFACE_SCHUR_PROFILE_ID = V6_2_INTERFACE_SCHUR_PROFILE_ID
TASK040_V6_2_INTERFACE_LOWER_COUNT = V6_2_INTERFACE_LOWER_COUNT
TASK040_V6_2_INTERFACE_UPPER_COUNT = V6_2_INTERFACE_UPPER_COUNT
TASK040_V6_2_INTERFACE_JOINT_COUNT = V6_2_INTERFACE_JOINT_COUNT
TASK040_V5_REQUIRED_THREAD_ENV = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "BLIS_NUM_THREADS",
)
V9_SOURCE_PACKET_ROOT_OPTION = "--v9-source-packet-root"
V9_SOURCE_PACKET_MANIFEST_SHA256_OPTION = "--v9-source-packet-manifest-sha256"
V9_E_S3_J1_BASELINE_ONLY_FLAG = "--v9-e-s3-j1-baseline-only"
V9_E_S3_STRUCTURED_B1_ONLY_FLAG = "--v9-e-s3-structured-b1-only"
V9_E_S3_J1_BASELINE_MANIFEST_OPTION = "--v9-e-s3-j1-baseline-manifest"
V9_E_S3_J1_BASELINE_MANIFEST_SHA256_OPTION = (
    "--v9-e-s3-j1-baseline-manifest-sha256"
)
V9_E_S3_J1_BASELINE_SCHEMA = "task040.v9_e.s3b_j1_baseline_formal.v1"
V9_E_S3_J1_BASELINE_METHOD = "task040_v9_e_s3b_j1_baseline_formal"
V9_E_S3_J1_BASELINE_PROFILE_ID = "task040.v9_e.s3b.j1_baseline.v1"
V9_E_S3_B1_SCHEMA = "task040.v9_e.s3b_b1_external_core.v1"
V9_E_S3_B1_METHOD = "task040_v9_e_s3b_b1_external_core"
V9_E_S3_B1_PROFILE_ID = "task040.v9_e.s3b.b1_external_core.v1"
V9_E_S3_INPUT_RELATIVE_PATH = (
    "input/official/task039/5nm_p6h10_hybrid_iterative_m120_candidate_mpi8.dat"
)
V9_E_S3_INPUT_SHA256 = (
    "3fa567d482ba45495fe9d097ba16946c330b0ba208fc8c4c5e47b7fcd6315161"
)
V9_E_S3_MARKER_SEQUENCE = (
    "s3b_j1_system_begin",
    "s3b_j1_system_ready",
    "s3b_j1_source_ready",
    "s3b_j1_f_materialize_begin",
    "s3b_j1_f_materialize_ready",
    "s3b_j1_f_destroyed",
    "s3b_j1_action_ready",
    "s3b_j1_one_apply_begin",
    "s3b_j1_one_apply_end",
    "s3b_j1_fgmres_setup",
    "s3b_j1_r8",
    "s3b_j1_r16",
    "s3b_j1_r32",
    "s3b_j1_r64",
    "s3b_j1_solve_end",
    "s3b_j1_cleanup_complete",
)
V9_E_S3_B1_MARKER_SEQUENCE = (
    "s3b_b1_baseline_validated",
    "s3b_b1_context_ready",
    "s3b_b1_source_ready",
    "s3b_b1_one_apply_begin",
    "s3b_b1_one_apply_end",
    "s3b_b1_fgmres_setup",
    "s3b_b1_r8",
    "s3b_b1_r16",
    "s3b_b1_r32",
    "s3b_b1_r64",
    "s3b_b1_solve_end",
    "s3b_b1_initial_gate",
    "s3b_b1_source_factory_ready",
    "s3b_b1_cleanup_begin",
    "s3b_b1_cleanup_complete",
)
V9_E_LOR_L2_ONLY_FLAG = "--v9-e-lor-l2-only"

V9_E_LOR_L2_ONLY_METHOD = "task040_v9_e_lor_l2_only"
V9_E_LOR_L2_ONLY_SCHEMA = "task040.v9_e.lor_l2_only.v1"
V9_E_LOR_L2_ONLY_PROFILE_ID = "task040.v9_e.lor.l2_only.v1"
V9_E_LOR_L2_ONLY_HARD_STOP_BYTES = 45 * 2**30
V9_E_LOR_L2_ONLY_TIMEOUT_SECONDS = 21600
V9_E_LOR_L2_MARKER_SEQUENCE = (
    "v9_e_lor_l2_preflight",
    "v9_e_lor_l2_mesh_ready",
    "v9_e_lor_l2_space_ready",
    "v9_e_lor_l2_floquet_ready",
    "v9_e_lor_l2_positive_form_ready",
    "v9_e_lor_l2_condensed_ready",
    "v9_e_lor_l2_action_ready",
    "v9_e_lor_l2_bridge_begin",
    "v9_e_lor_l2_bridge_ready",
    "v9_e_lor_l2_service_ready",
    "v9_e_lor_l2_rhs_ready",
    "v9_e_lor_l2_solve_begin",
    "v9_e_lor_l2_checkpoint",
    "v9_e_lor_l2_solve_end",
    "v9_e_lor_l2_explicit_residual",
    "v9_e_lor_l2_cleanup_complete",
)
V9_E_LOR_L2_ALLOWED_INPUTS = (
    "input/official/task039/5nm_p6h10_full3d_direct_mpi8.dat",
    "input/official/task039/5nm_p6h5_full3d_direct_mpi8.dat",
)

__all__ = (
    "TASK040_LEVEL_A_METHOD",
    "TASK040_LEVEL_A_SCHEMA",
    "TASK040_LEVEL_A_PROFILE_ID",
    "TASK040_LEVEL_A_HARD_STOP_BYTES",
    "TASK040_LEVEL_A_SEQUENCE",
    "TASK040_V1_1_SCALAR_KRYLOV_FLAG",
    "TASK040_V1_1_METHOD",
    "TASK040_V1_1_SCHEMA",
    "TASK040_V1_1_PROFILE_ID",
    "TASK040_V1_2_INTERFACE_SCHUR_FLAG",
    "TASK040_V1_2_METHOD",
    "TASK040_V1_2_SCHEMA",
    "TASK040_V1_2_PROFILE_ID",
    "TASK040_V2_INTERFACE_PACKET_PRODUCER_FLAG",
    "TASK040_V2_INTERFACE_PACKET_METHOD",
    "TASK040_V2_INTERFACE_PACKET_SCHEMA",
    "TASK040_V2_INTERFACE_PACKET_PROFILE_ID",
    "TASK040_V2_INTERFACE_PACKET_PREFERRED_BYTES",
    "TASK040_V2_INTERFACE_PACKET_HARD_STOP_BYTES",
    "TASK040_V2_INTERFACE_PACKET_CONSUMER_FLAG",
    "TASK040_V2_INTERFACE_PACKET_CONSUMER_METHOD",
    "TASK040_V2_INTERFACE_PACKET_CONSUMER_SCHEMA",
    "TASK040_V2_INTERFACE_PACKET_CONSUMER_PROFILE_ID",
    "TASK040_V2_INTERFACE_PACKET_MANIFEST_SHA256",
    "TASK040_V3_2_COUPLED_INTERFACE_FLAG",
    "TASK040_V3_2_COUPLED_INTERFACE_METHOD",
    "TASK040_V3_2_COUPLED_INTERFACE_SCHEMA",
    "TASK040_V3_2_COUPLED_INTERFACE_PROFILE_ID",
    "TASK040_V3_2_AUGMENTED_PACKET_MANIFEST_SHA256",
    "TASK040_V3_2_TRUE_JOINT_CONTENT_SHA256",
    "TASK040_V3_2_PRODUCER_SOURCE_SHA",
    "TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_FLAG",
    "TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_METHOD",
    "TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_SCHEMA",
    "TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_PROFILE_ID",
    "TASK040_V4_FROZEN_BRANCH",
    "TASK040_V4_FROZEN_AUTHORITY_SOURCE_SHA",
    "TASK040_V5_FRESH_BARE_F_AUTHORITY_FLAG",
    "TASK040_V5_FRESH_BARE_F_AUTHORITY_METHOD",
    "TASK040_V5_FRESH_BARE_F_AUTHORITY_SCHEMA",
    "TASK040_V5_FRESH_BARE_F_AUTHORITY_PROFILE_ID",
    "TASK040_V5_ROUTE_C_FLAG",
    "TASK040_V5_ROUTE_C_METHOD",
    "TASK040_V5_ROUTE_C_SCHEMA",
    "TASK040_V5_ROUTE_C_PROFILE_ID",
    "TASK040_V5_ROUTE_C_RESOURCE_BLOCKED",
    "TASK040_V6_2_INTERFACE_SCHUR_FLAG",
    "TASK040_V6_2_INTERFACE_SCHUR_METHOD",
    "TASK040_V6_2_INTERFACE_SCHUR_SCHEMA",
    "TASK040_V6_2_INTERFACE_SCHUR_PROFILE_ID",
    "TASK040_V6_2_INTERFACE_LOWER_COUNT",
    "TASK040_V6_2_INTERFACE_UPPER_COUNT",
    "TASK040_V6_2_INTERFACE_JOINT_COUNT",
    "TASK040_V5_REQUIRED_THREAD_ENV",
    "V9_C0_COLUMNS_PER_PATCH",
    "V9_C0_EXPLICIT_COARSE_ONLY_FLAG",
    "V9_C0_EXPLICIT_COARSE_ONLY_METHOD",
    "V9_C0_EXPLICIT_COARSE_ONLY_PROFILE_ID",
    "V9_C0_EXPLICIT_COARSE_ONLY_SCHEMA",
    "V9_C0_HARD_STOP_BYTES",
    "V9_C0_MARKER_SEQUENCE",
    "V9_C0_MIN_AVAILABLE_BYTES",
    "V9_C0_ONE_APPLY_TARGET_SECONDS",
    "V9_C0_PATCH_COUNT",
    "V9_C0_PREFERRED_MEMORY_BYTES",
    "V9_C0_SETUP_TARGET_SECONDS",
    "V9_C0_SOURCES",
    "V9_C0_TIMEOUT_SECONDS",
    "V9_C0_TOTAL_COARSE_DOF",
    "V9_C0_WARNING_MEMORY_BYTES",
    "V9_SOURCE_BRIDGE_ONLY_FLAG",
    "V9_SOURCE_BRIDGE_ONLY_METHOD",
    "V9_SOURCE_BRIDGE_ONLY_PROFILE_ID",
    "V9_SOURCE_BRIDGE_ONLY_SCHEMA",
    "V9_SOURCE_BRIDGE_ONLY_SOURCES",
    "V9_SOURCE_PACKET_ROOT_OPTION",
    "V9_SOURCE_PACKET_MANIFEST_SHA256_OPTION",
    "V9_E_S3_J1_BASELINE_ONLY_FLAG",
    "V9_E_S3_STRUCTURED_B1_ONLY_FLAG",
    "V9_E_S3_J1_BASELINE_MANIFEST_OPTION",
    "V9_E_S3_J1_BASELINE_MANIFEST_SHA256_OPTION",
    "V9_E_S3_J1_BASELINE_SCHEMA",
    "V9_E_S3_J1_BASELINE_METHOD",
    "V9_E_S3_J1_BASELINE_PROFILE_ID",
    "V9_E_S3_B1_SCHEMA",
    "V9_E_S3_B1_METHOD",
    "V9_E_S3_B1_PROFILE_ID",
    "V9_E_S3_INPUT_RELATIVE_PATH",
    "V9_E_S3_INPUT_SHA256",
    "V9_E_S3_MARKER_SEQUENCE",
    "V9_E_S3_B1_MARKER_SEQUENCE",
    "V9_E_LOR_L2_ONLY_FLAG",
    "V9_E_LOR_L2_ONLY_METHOD",
    "V9_E_LOR_L2_ONLY_SCHEMA",
    "V9_E_LOR_L2_ONLY_PROFILE_ID",
    "V9_E_LOR_L2_ONLY_HARD_STOP_BYTES",
    "V9_E_LOR_L2_ONLY_TIMEOUT_SECONDS",
    "V9_E_LOR_L2_MARKER_SEQUENCE",
    "V9_E_LOR_L2_ALLOWED_INPUTS",
    "V9_E_LOR_BARE_F_EXTERNAL_ONLY_FLAG",
    "V9_E_LOR_BARE_F_EXTERNAL_ONLY_METHOD",
    "V9_E_LOR_BARE_F_EXTERNAL_ONLY_SCHEMA",
    "V9_E_LOR_BARE_F_EXTERNAL_ONLY_PROFILE_ID",
    "V9_E_LOR_BARE_F_EXTERNAL_ONLY_HARD_STOP_BYTES",
    "V9_E_LOR_BARE_F_EXTERNAL_ONLY_TIMEOUT_SECONDS",
    "V9_E_LOR_BARE_F_EXTERNAL_ONLY_INPUT",
    "V9_E_LOR_BARE_F_EXTERNAL_ONLY_MPI_SIZE",
    "V9_E_LOR_BARE_F_EXTERNAL_MARKER_SEQUENCE",
    "V9_E_LOR_BARE_F_EXTERNAL_POSITIVE",
    "V9_E_LOR_BARE_F_EXTERNAL_NUMERICAL_NO_SIGNAL",
    "V9_E_LOR_BARE_F_EXTERNAL_IMPLEMENTATION_FAILURE",
    "V9_E_LOR_BARE_F_EXTERNAL_RESOURCE_UNAVAILABLE",
    "TASK040_V1_2_PROBE_MANIFEST",
    "TASK040_V1_2_PROBE_MANIFEST_SHA256",
    "TASK040_V1_2_INPUT_SHA256",
    "TASK040_V1_2_PHYSICAL_MODEL_SHA256",
    "TASK040_V1_2_SELECTED_MANIFEST_SHA256",
    "TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256",
    "TASK040_V1_2_LOWER_RESOLVED_MODE_METADATA_SHA256",
    "TASK040_V1_2_LOWER_LEGACY_BETA_METADATA_SHA256",
    "build_task040_level_a_plan",
    "level_a_bottom_beta",
    "run_task040_level_a",
)


def level_a_bottom_beta(cfg: Any) -> complex:
    """Use the frozen bottom Robin beta authority, with no parameter scan."""

    return complex(cfg.k0) * complex(cfg.substrate_index)


def _v1_2_identity_pass(
    *,
    identity_observed: Mapping[str, Any],
    frozen_identity: Mapping[str, Any],
    manifest: Mapping[str, Any],
    exact_identities: Mapping[str, Any],
) -> bool:
    """Check the frozen Run-B identity before constructing V1-3 factors."""

    return bool(
        identity_observed["input_sha256"] == frozen_identity["input_sha256"]
        and identity_observed["physical_model_sha256"]
        == frozen_identity["physical_model_sha256"]
        and identity_observed["selected_identity_physical_sha256"]
        == frozen_identity["physical_model_sha256"]
        and identity_observed["selected_manifest_sha256"]
        == frozen_identity["selected_manifest_sha256"]
        and identity_observed["selected_identity_sha256"]
        == frozen_identity["selected_identity_sha256"]
        and identity_observed["selected_selection_sha256"]
        == frozen_identity["selected_selection_sha256"]
        and identity_observed["resolved_config_sha256"]
        == frozen_identity["exact_spool_resolved_config_sha256"]
        and identity_observed["spool_catalog_sha256"]
        == TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256
        and identity_observed["upper_mode_key_sha256"]
        == manifest["upper_selected_packet_basis"]["positive_mode_keys_sha256"]
        and identity_observed["upper_beta_sha256"]
        == manifest["upper_selected_packet_basis"]["positive_beta_sha256"]
        and identity_observed["lower_mode_key_sha256"]
        == manifest["lower_fourier_floquet_basis"]["canonical_key_list_sha256"]
        and identity_observed["lower_resolved_mode_metadata_sha256"]
        == TASK040_V1_2_LOWER_RESOLVED_MODE_METADATA_SHA256
        and identity_observed["lower_resolved_mode_metadata_sha256"]
        != identity_observed["lower_legacy_beta_metadata_sha256"]
        and identity_observed["exact_output_identity_sha256"] == exact_identities
    )


def build_task040_level_a_plan(
    *,
    input_path: str | Path,
    exact_spool_root: str | Path,
    run_directory: str | Path,
    source_sha: str,
    scalar_krylov: bool = False,
    interface_schur: bool = False,
    packet_producer: bool = False,
    packet_consumer: bool = False,
    coupled_interface: bool = False,
    v4_exact_authority_compatibility: bool = False,
    v5_fresh_bare_f_authority: bool = False,
    v5_route_c: bool = False,
    v6_2_interface_schur: bool = False,
    v7_scale_normalized_identity: bool = False,
    v7_moving_pml_full_state: bool = False,
    v8_full_spectrum_only: bool = False,
    v8_adaptive_schwarz_only: bool = False,
    v8_adaptive_stage_b1_only: bool = False,
    v8_adaptive_stage_bc_only: bool = False,
    v9_source_bridge_only: bool = False,
    v9_c0_explicit_coarse_only: bool = False,
    v9_e_lor_l2_only: bool = False,
    v9_e_lor_bare_f_external_only: bool = False,
    v9_e_s3_j1_baseline_only: bool = False,
    v9_e_s3_structured_b1_only: bool = False,
    v9_e_s3_j1_baseline_manifest: str | Path | None = None,
    v9_e_s3_j1_baseline_manifest_sha256: str | None = None,
    v9_source_packet_root: str | Path | None = None,
    v9_source_packet_manifest_sha256: str | None = None,
    interface_packet_root: str | Path | None = None,
) -> dict[str, Any]:
    """Build a dry-run contract without creating a result directory."""

    source_sha = str(source_sha)
    if len(source_sha) != 40 or any(
        character not in "0123456789abcdef" for character in source_sha
    ):
        raise ValueError(
            "Task040 source_sha must be a 40-character lowercase hex SHA"
        )
    run_directory = Path(run_directory).resolve()
    if run_directory.exists():
        raise ValueError(f"Task040 run directory already exists: {run_directory}")
    if (v9_source_packet_root is None) != (
        v9_source_packet_manifest_sha256 is None
    ):
        raise ValueError(
            "V9 corrected packet root and manifest SHA must be supplied together"
        )
    if v9_source_packet_root is not None and not v8_full_spectrum_only:
        raise ValueError(
            "V9 corrected packet parameters require --v8-full-spectrum-only"
        )
    if v9_source_packet_manifest_sha256 is not None and (
        len(str(v9_source_packet_manifest_sha256)) != 64
        or any(
            character not in "0123456789abcdef"
            for character in str(v9_source_packet_manifest_sha256)
        )
    ):
        raise ValueError("V9 source packet manifest SHA must be lowercase SHA256")
    s3_route = bool(v9_e_s3_j1_baseline_only or v9_e_s3_structured_b1_only)
    if (v9_e_s3_j1_baseline_manifest is None) != (
        v9_e_s3_j1_baseline_manifest_sha256 is None
    ):
        raise ValueError(
            "V9-E S3 J1 baseline manifest path and SHA must be supplied together"
        )
    if v9_e_s3_j1_baseline_manifest is not None and not v9_e_s3_structured_b1_only:
        raise ValueError(
            "V9-E S3 J1 baseline manifest parameters are candidate-only"
        )
    if v9_e_s3_structured_b1_only and v9_e_s3_j1_baseline_manifest is None:
        raise ValueError(
            "V9-E S3 structured B1 candidate requires the J1 baseline manifest"
        )
    if v9_e_s3_j1_baseline_manifest_sha256 is not None and (
        len(str(v9_e_s3_j1_baseline_manifest_sha256)) != 64
        or any(
            character not in "0123456789abcdef"
            for character in str(v9_e_s3_j1_baseline_manifest_sha256)
        )
    ):
        raise ValueError(
            "V9-E S3 J1 baseline manifest SHA must be lowercase SHA256"
        )
    expected_s3_input = (
        Path(__file__).resolve().parents[1] / V9_E_S3_INPUT_RELATIVE_PATH
    ).resolve()
    if s3_route and Path(input_path).resolve() != expected_s3_input:
        raise ValueError(
            "V9-E S3 routes require the frozen Task039 MPI8 input path: "
            f"{expected_s3_input}"
        )
    expected_l2_inputs = {
        (Path(__file__).resolve().parents[1] / relative).resolve()
        for relative in V9_E_LOR_L2_ALLOWED_INPUTS
    }
    if v9_e_lor_l2_only and Path(input_path).resolve() not in expected_l2_inputs:
        raise ValueError(
            "V9-E L2 requires one of the frozen Task039 h10/h5 inputs"
        )
    expected_bare_f_external_input = (
        Path(__file__).resolve().parents[1] / V9_E_LOR_BARE_F_EXTERNAL_ONLY_INPUT
    ).resolve()
    if (
        v9_e_lor_bare_f_external_only
        and Path(input_path).resolve() != expected_bare_f_external_input
    ):
        raise ValueError(
            "V9-E bare-F external pilot requires the frozen h10 input"
        )
    plan = {
        "schema": TASK040_LEVEL_A_SCHEMA,
        "method": TASK040_LEVEL_A_METHOD,
        "profile": TASK040_LEVEL_A_PROFILE_ID,
        "source_sha": source_sha,
        "input": str(Path(input_path).resolve()),
        "exact_spool_root": str(Path(exact_spool_root).resolve()),
        "run_directory": str(run_directory),
        "mpi_size": TASK040_LEVEL_A_MPI_SIZE,
        "threads": TASK040_LEVEL_A_THREADS,
        "timeout_seconds": TASK040_LEVEL_A_TIMEOUT_SECONDS,
        "absolute_terminate_memory_bytes": TASK040_LEVEL_A_HARD_STOP_BYTES,
        "swap_limit_bytes": 0,
        "oracle_only": True,
        "scalable_candidate": False,
        "forbidden": [
            "global_direct_factor",
            "qep",
            "outer_ksp",
            "recovery",
            "top",
            "full_hybrid",
            "response_packet",
        ],
    }
    if (
        sum(
            bool(value)
            for value in (
                scalar_krylov,
                interface_schur,
                packet_producer,
                packet_consumer,
                coupled_interface,
                v4_exact_authority_compatibility,
                v5_fresh_bare_f_authority,
                v5_route_c,
                v6_2_interface_schur,
                v7_scale_normalized_identity,
                v7_moving_pml_full_state,
                v8_full_spectrum_only,
                v8_adaptive_schwarz_only,
                v8_adaptive_stage_b1_only,
                v8_adaptive_stage_bc_only,
                v9_source_bridge_only,
                v9_c0_explicit_coarse_only,
                v9_e_lor_l2_only,
                v9_e_lor_bare_f_external_only,
                v9_e_s3_j1_baseline_only,
                v9_e_s3_structured_b1_only,
            )
        )
        > 1
    ):
        raise ValueError("Task040 research routes are mutually exclusive")
    if scalar_krylov:
        plan.update(
            {
                "schema": TASK040_V1_1_SCHEMA,
                "method": TASK040_V1_1_METHOD,
                "profile": TASK040_V1_1_PROFILE_ID,
                "scalar_krylov": True,
                "research_only": True,
            }
        )
    if interface_schur:
        plan.update(
            {
                "schema": TASK040_V1_2_SCHEMA,
                "method": TASK040_V1_2_METHOD,
                "profile": TASK040_V1_2_PROFILE_ID,
                "interface_schur": True,
                "research_only": True,
                "probe_manifest": TASK040_V1_2_PROBE_MANIFEST,
                "probe_manifest_sha256": TASK040_V1_2_PROBE_MANIFEST_SHA256,
                "expected_input_sha256": TASK040_V1_2_INPUT_SHA256,
                "expected_physical_model_sha256": (TASK040_V1_2_PHYSICAL_MODEL_SHA256),
                "expected_selected_manifest_sha256": (
                    TASK040_V1_2_SELECTED_MANIFEST_SHA256
                ),
                "expected_exact_spool_catalog_sha256": (
                    TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256
                ),
                # Keep these frozen aliases for the established dry-run
                # contract; runtime observations are recorded separately.
                "selected_manifest_sha256": TASK040_V1_2_SELECTED_MANIFEST_SHA256,
                "exact_spool_catalog_sha256": (TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256),
                "v1_3_conditional": True,
            }
        )
    if packet_producer:
        plan.update(
            {
                "schema": TASK040_V2_INTERFACE_PACKET_SCHEMA,
                "method": TASK040_V2_INTERFACE_PACKET_METHOD,
                "profile": TASK040_V2_INTERFACE_PACKET_PROFILE_ID,
                "packet_producer": True,
                "research_only": True,
                "pde_solve": "not_run",
                "qep_calls": 0,
                "v1_3_conditional": False,
                "absolute_terminate_memory_bytes": (
                    TASK040_V2_INTERFACE_PACKET_HARD_STOP_BYTES
                ),
                "preferred_memory_bytes": TASK040_V2_INTERFACE_PACKET_PREFERRED_BYTES,
                "packet_root": str(run_directory / "interface_packet"),
                "forbidden": [
                    "v1_3_projected_transmission",
                    "fgmres",
                    "qep",
                    "pde_solve",
                    "global_direct_factor",
                    "full_side_factor",
                ],
                "packet_complete_required": True,
            }
        )
    if packet_consumer:
        if interface_packet_root is None:
            raise ValueError("V2 packet consumer requires interface_packet_root")
        plan.update(
            {
                "schema": TASK040_V2_INTERFACE_PACKET_CONSUMER_SCHEMA,
                "method": TASK040_V2_INTERFACE_PACKET_CONSUMER_METHOD,
                "profile": TASK040_V2_INTERFACE_PACKET_CONSUMER_PROFILE_ID,
                "packet_consumer": True,
                "research_only": True,
                "oracle_only": True,
                "scalable_candidate": False,
                "pde_solve": "not_run",
                "qep_calls": 0,
                "absolute_terminate_memory_bytes": TASK040_LEVEL_A_HARD_STOP_BYTES,
                "interface_packet_root": str(Path(interface_packet_root).resolve()),
                "packet_manifest_sha256": TASK040_V2_INTERFACE_PACKET_MANIFEST_SHA256,
                "forbidden": [
                    "qep",
                    "exact_interface_oracle",
                    "outer_ksp",
                    "recovery",
                    "top",
                    "full_hybrid",
                    "response_packet",
                    "exact_output_vector_load",
                    "global_direct_factor",
                    "full_side_factor",
                    "pde_solve",
                ],
                "packet_complete_required": True,
            }
        )
    if coupled_interface:
        if interface_packet_root is None:
            raise ValueError("V3-2 coupled consumer requires interface_packet_root")
        plan.update(
            {
                "schema": TASK040_V3_2_COUPLED_INTERFACE_SCHEMA,
                "method": TASK040_V3_2_COUPLED_INTERFACE_METHOD,
                "profile": TASK040_V3_2_COUPLED_INTERFACE_PROFILE_ID,
                "coupled_interface": True,
                "packet_dependent": True,
                "research_only": True,
                "oracle_only": True,
                "scalable_candidate": False,
                "pde_solve": "not_run",
                "qep_calls": 0,
                "absolute_terminate_memory_bytes": TASK040_LEVEL_A_HARD_STOP_BYTES,
                "interface_packet_root": str(Path(interface_packet_root).resolve()),
                "interface_packet_manifest_sha256": (
                    TASK040_V3_2_AUGMENTED_PACKET_MANIFEST_SHA256
                ),
                "true_joint_content_sha256": TASK040_V3_2_TRUE_JOINT_CONTENT_SHA256,
                "forbidden": [
                    "qep",
                    "exact_interface_oracle",
                    "exact_output_vector_load",
                    "recovery",
                    "top",
                    "full_hybrid",
                    "response_packet",
                    "global_hybrid_outer_ksp",
                    "full_side_factor",
                    "pde_solve",
                    "v3_3_bounded_rank",
                    "v3_4_packet_independent",
                ],
                "packet_complete_required": True,
            }
        )
    if v4_exact_authority_compatibility:
        plan.update(
            {
                "schema": TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_SCHEMA,
                "method": TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_METHOD,
                "profile": TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_PROFILE_ID,
                "v4_exact_authority_compatibility": True,
                "research_only": True,
                "oracle_only": True,
                "scalable_candidate": False,
                "bare_f_compatibility": "not_run_by_identity_gate",
                "read_only_exact_outputs": True,
                "expected_exact_output_labels": list(V4_EXACT_AUTHORITY_LABELS),
                "expected_exact_output_count": len(V4_EXACT_AUTHORITY_LABELS),
                "exact_output_vectors_loaded": 0,
                "pde_solve": "not_run",
                "qep_calls": 0,
                "forbidden": [
                    "global_direct_factor",
                    "outer_ksp",
                    "recovery",
                    "top",
                    "full_hybrid",
                    "response_packet",
                    "interface_mass",
                    "group_factor",
                    "coarse_factor",
                    "packet",
                    "qep",
                    "pde_solve",
                    "full_side_factor",
                    "projection",
                    "lift",
                ],
            }
        )
    if v5_fresh_bare_f_authority:
        plan.update(
            {
                "schema": TASK040_V5_FRESH_BARE_F_AUTHORITY_SCHEMA,
                "method": TASK040_V5_FRESH_BARE_F_AUTHORITY_METHOD,
                "profile": TASK040_V5_FRESH_BARE_F_AUTHORITY_PROFILE_ID,
                "v5_fresh_bare_f_authority": True,
                "research_only": True,
                "oracle_only": True,
                "scalable_candidate": False,
                "fresh_current_layout": True,
                "source_labels": list(V5_BARE_F_SOURCE_LABELS),
                "absolute_terminate_memory_bytes": (
                    TASK040_V5_FRESH_BARE_F_HARD_STOP_BYTES
                ),
                "preferred_memory_bytes": TASK040_V5_FRESH_BARE_F_PREFERRED_BYTES,
                "warning_memory_bytes": TASK040_V5_FRESH_BARE_F_WARNING_BYTES,
                "minimum_mem_available_bytes": TASK040_V5_FRESH_BARE_F_MIN_AVAILABLE_BYTES,
                "minimum_disk_free_bytes": TASK040_V5_FRESH_BARE_F_MIN_DISK_BYTES,
                "qep_calls": 0,
                "pde_solve": "not_run",
                "external_dtn_coupling": "rhs_only_minimal_surface_objects",
                "factor_lifecycle": (
                    "one_source_side_one_cell_factor_then_one_full_side_bare_f_factor_"
                    "1_to_0_each_no_overlap"
                ),
                "forbidden": [
                    "research_exact_side_lu_action",
                    "woodbury_inverse",
                    "physical_dtn_operator",
                    "explicit_C_matrix",
                    "explicit_D_matrix",
                    "explicit_H_matrix",
                    "outer_ksp",
                    "qep",
                    "interface_mass",
                    "group_factor",
                    "physical_A_side_factor",
                    "full_hybrid",
                    "pde_solve",
                    "raw_global_row_remap",
                ],
            }
        )
    if v5_route_c:
        plan.update(
            {
                "schema": TASK040_V5_ROUTE_C_SCHEMA,
                "method": TASK040_V5_ROUTE_C_METHOD,
                "profile": TASK040_V5_ROUTE_C_PROFILE_ID,
                "v5_route_c": True,
                "route_c_only": True,
                "research_only": True,
                "oracle_only": False,
                "scalable_candidate": False,
                "fresh_current_layout": True,
                "source_labels": list(ROUTE_C_LABELS),
                "restart": 32,
                "checkpoints": list(ROUTE_C_CHECKPOINTS),
                "conditional_checkpoint": 256,
                "max_harmonic_ritz_directions_per_restart": 8,
                "exact_output_vectors_loaded": 0,
                "exact_packet_required": False,
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "absolute_terminate_memory_bytes": TASK040_V5_ROUTE_C_HARD_STOP_BYTES,
                "minimum_mem_available_bytes": TASK040_V5_ROUTE_C_MIN_AVAILABLE_BYTES,
                "minimum_disk_free_bytes": TASK040_V5_ROUTE_C_MIN_DISK_BYTES,
                "swap_limit_bytes": 0,
                "timeout_seconds": TASK040_LEVEL_A_TIMEOUT_SECONDS,
                "resource_classification": "route_c_resource_preflight",
                "resource_policy": {
                    "hard_stop_bytes": TASK040_V5_ROUTE_C_HARD_STOP_BYTES,
                    "minimum_available_bytes": TASK040_V5_ROUTE_C_MIN_AVAILABLE_BYTES,
                    "required_headroom_bytes": TASK040_V5_ROUTE_C_HEADROOM_BYTES,
                    "minimum_disk_free_bytes": TASK040_V5_ROUTE_C_MIN_DISK_BYTES,
                    "swap_limit_bytes": 0,
                    "timeout_seconds": TASK040_LEVEL_A_TIMEOUT_SECONDS,
                },
                "qep_calls": 0,
                "pde_solve": "not_run",
                "factor_lifecycle": "three_group_diagnostic_factors_3_to_0",
                "forbidden": [
                    "full_side_exact_factor",
                    "global_direct_factor",
                    "exact_output_vector_load",
                    "exact_packet_dependency",
                    "physical_dtn_operator",
                    "research_exact_side_lu_action",
                    "woodbury_inverse",
                    "qep",
                    "top",
                    "full_hybrid",
                    "pde_solve",
                    "response_packet",
                ],
            }
        )
    if v6_2_interface_schur:
        plan.update(
            {
                "schema": TASK040_V6_2_INTERFACE_SCHUR_SCHEMA,
                "method": TASK040_V6_2_INTERFACE_SCHUR_METHOD,
                "profile": TASK040_V6_2_INTERFACE_SCHUR_PROFILE_ID,
                "v6_2_interface_schur": True,
                "research_only": True,
                "oracle_only": True,
                "scalable_candidate": False,
                "fresh_current_layout": True,
                "gamma_lower_count": TASK040_V6_2_INTERFACE_LOWER_COUNT,
                "gamma_upper_count": TASK040_V6_2_INTERFACE_UPPER_COUNT,
                "gamma_joint_count": TASK040_V6_2_INTERFACE_JOINT_COUNT,
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "qep_calls": 0,
                "pde_solve": (
                    "exact_interface_fgmres_with_full_bare_f_residual_run"
                ),
                "factor_lifecycle": "three_group_mechanism_oracle_3_to_0",
                "same_process_exact_lifecycle": True,
                "v6_2_identity_only": False,
                "numeric_allgather": False,
                "fe_numeric_allgather": False,
                "full_interface_replica_per_rank": False,
                "root_metadata_gather": True,
                "support_metadata_replicated": True,
                "canonical_block_transforms_applied": False,
                "value_basis": "current_raw_active_coefficients",
                "transform_required_for": "V6-3_full_spectrum_trace_authority",
                "absolute_terminate_memory_bytes": TASK040_LEVEL_A_HARD_STOP_BYTES,
                "minimum_mem_available_bytes": (
                    TASK040_LEVEL_A_HARD_STOP_BYTES + 4 * 2**30
                ),
                "minimum_disk_free_bytes": 20 * 2**30,
                "swap_limit_bytes": 0,
                "timeout_seconds": TASK040_LEVEL_A_TIMEOUT_SECONDS,
                "watchdog_hard_stop_bytes": TASK040_LEVEL_A_HARD_STOP_BYTES,
                "exact_qualification_plan": build_v6_2_exact_qualification_plan(),
                "forbidden": [
                    "full_side_factor",
                    "global_direct_factor",
                    "dense_15120_schur",
                    "global_numeric_allgather",
                    "full_interface_replica_per_rank",
                    "qep",
                    "old_bool_recovery_mask",
                    "raw_global_row_remap",
                ],
            }
        )
    if v8_full_spectrum_only:
        plan.update(
            {
                "schema": V8_FULL_SPECTRUM_ONLY_SCHEMA,
                "method": V8_FULL_SPECTRUM_ONLY_METHOD,
                "profile": V8_FULL_SPECTRUM_ONLY_PROFILE_ID,
                "v8_full_spectrum_only": True,
                "research_only": True,
                "oracle_only": True,
                "scalable_candidate": False,
                "pde_solve": "full_spectrum_five_source_screen",
                "exact_qualification": (
                    "intentional_not_run_by_v8_direct_mainline"
                ),
                "full_spectrum_continuation": "required",
                "source_order": list(V8_FULL_SPECTRUM_SOURCES),
                "mandatory_checkpoints": list(V8_FULL_SPECTRUM_CHECKPOINTS),
                "conditional_checkpoints": [128],
                "fixed_configuration": {
                    "restart": 32,
                    "zero_initial_guess": True,
                    "pml_profile": "not_used",
                    "selected_operator": "D0_lower_memory",
                },
                "minimum_mem_available_bytes": V8_FULL_SPECTRUM_MIN_AVAILABLE_BYTES,
                "preferred_memory_bytes": V8_FULL_SPECTRUM_PREFERRED_MEMORY_BYTES,
                "absolute_terminate_memory_bytes": TASK040_LEVEL_A_HARD_STOP_BYTES,
                "watchdog_hard_stop_bytes": TASK040_LEVEL_A_HARD_STOP_BYTES,
                "swap_limit_bytes": 0,
                "timeout_seconds": V8_FULL_SPECTRUM_TIMEOUT_SECONDS,
                "setup_target_seconds": V8_FULL_SPECTRUM_SETUP_TARGET_SECONDS,
                "transform_target_seconds": V8_FULL_SPECTRUM_TRANSFORM_TARGET_SECONDS,
                "one_apply_target_seconds": V8_FULL_SPECTRUM_ONE_APPLY_TARGET_SECONDS,
                "numeric_allgather": False,
                "full_interface_replica_per_rank": False,
                "root_metadata_gather": True,
                "metadata_only_descriptor_gather": True,
                "exact_output_packet_publication": False,
                "three_scale_identity": False,
                "d0_d1_comparison": False,
                "conditional_authorized": {"conditional_128": "v8_r64_inconclusive_only"},
                "forbidden": [
                    "v7_scale_normalized_identity_metrics",
                    "v7_identity_checker_bundle",
                    "d0_d1_comparison",
                    "refinement",
                    "partition",
                    "exact_output_packet_publication",
                    "moving_pml",
                    "threshold_relaxation",
                    "parameter_scan",
                    "qep",
                    "physical_dtn",
                    "full_side_factor",
                ],
            }
        )
        if v9_source_packet_root is not None:
            plan.update(
                {
                    "v9_corrected_source_packet": True,
                    "v9_source_packet_root": str(
                        Path(v9_source_packet_root).resolve()
                    ),
                    "v9_source_packet_manifest_sha256": str(
                        v9_source_packet_manifest_sha256
                    ),
                    "source_adapter": "v9_hash_bound_canonical_packet",
                    "v9_source_markers": [
                        "v9_full_spectrum_source_packet_validated",
                        "v9_full_spectrum_external_owner_vector_ready",
                        "v9_full_spectrum_random0_owner_vector_ready",
                    ],
                }
            )
    if v8_adaptive_schwarz_only:
        plan.update(
            {
                "schema": V8_ADAPTIVE_SCHWARZ_ONLY_SCHEMA,
                "method": V8_ADAPTIVE_SCHWARZ_ONLY_METHOD,
                "profile": V8_ADAPTIVE_SCHWARZ_ONLY_PROFILE_ID,
                "v8_adaptive_schwarz_only": True,
                "research_only": True,
                "oracle_only": False,
                "scalable_candidate": False,
                "pde_solve": "adaptive_impedance_stage_a_one_apply",
                "source_order": ["external_dtn_coupling"],
                "mandatory_checkpoints": ["one_apply"],
                "conditional_checkpoints": [],
                "fixed_configuration": {
                    "mass_source": "actual_hcurl_ufcx_exterior_facet_provider",
                    "quadrature_degree": "2*cfg.nedelec_degree",
                    "beta": "level_a_bottom_beta(cfg)",
                    "one_apply": True,
                    "fgmres": False,
                    "gamma_canonical_interface": False,
                },
                "preferred_memory_bytes": V8_ADAPTIVE_PREFERRED_MEMORY_BYTES,
                "absolute_terminate_memory_bytes": V8_ADAPTIVE_HARD_STOP_BYTES,
                "watchdog_hard_stop_bytes": V8_ADAPTIVE_HARD_STOP_BYTES,
                "swap_limit_bytes": 0,
                "timeout_seconds": V8_ADAPTIVE_TIMEOUT_SECONDS,
                "setup_target_seconds": V8_ADAPTIVE_SETUP_TARGET_SECONDS,
                "one_apply_target_seconds": V8_ADAPTIVE_ONE_APPLY_TARGET_SECONDS,
                "numeric_allgather": False,
                "full_interface_replica_per_rank": False,
                "formal_adjudication": False,
                "stage_a_gate": {
                    "rows_max": "<=1024",
                    "patch_ratio_median": "<=0.5",
                    "patch_ratio_p90": "<=0.9",
                    "pou_error": "<=1e-12",
                    "setup_seconds": "<=3600",
                    "one_apply_seconds": "<=1200",
                    "resource": "watchdog_35GiB_preferred_45GiB_hard_swap0",
                },
                "marker_sequence": [
                    "v8_adaptive_preflight",
                    "v8_adaptive_system_ready",
                    "v8_adaptive_factor_ready",
                    "v8_adaptive_external_one_apply_begin",
                    "v8_adaptive_external_one_apply_end",
                    "v8_adaptive_checkpoint",
                    "v8_adaptive_cleanup_complete",
                ],
                "forbidden": [
                    "gamma",
                    "canonical_interface",
                    "full_interface",
                    "group_factors",
                    "fgmres",
                    "stage_b_c",
                    "moving_pml",
                    "full_spectrum",
                    "parameter_scan",
                ],
            }
        )
    if v8_adaptive_stage_b1_only:
        plan.update(
            {
                "schema": V8_ADAPTIVE_STAGE_B1_ONLY_SCHEMA,
                "method": V8_ADAPTIVE_STAGE_B1_ONLY_METHOD,
                "profile": V8_ADAPTIVE_STAGE_B1_ONLY_PROFILE_ID,
                "v8_adaptive_stage_b1_only": True,
                "research_only": True,
                "oracle_only": False,
                "pde_solve": "symbolic_identity_and_memory_preflight_only",
                "source_order": [],
                "mandatory_checkpoints": [],
                "conditional_checkpoints": [],
                "fixed_configuration": {
                    "operation": "symbolic_identity_and_memory_preflight_only"
                },
                "absolute_terminate_memory_bytes": V8_ADAPTIVE_HARD_STOP_BYTES,
                "watchdog_hard_stop_bytes": V8_ADAPTIVE_HARD_STOP_BYTES,
                "timeout_seconds": V8_ADAPTIVE_TIMEOUT_SECONDS,
                "setup_target_seconds": V8_ADAPTIVE_SETUP_TARGET_SECONDS,
                "one_apply_target_seconds": None,
                "numeric_allgather": False,
                "full_interface_replica_per_rank": False,
                "formal_adjudication": False,
                "marker_sequence": [
                    "v8_adaptive_stage_b1_preflight",
                    "v8_adaptive_stage_b1_system_ready",
                    "v8_adaptive_stage_b1_factor_ready",
                    "v8_adaptive_stage_b1_begin",
                    "v8_adaptive_stage_b1_end",
                    "v8_adaptive_stage_b1_cleanup_complete",
                ],
                "forbidden": [
                    "source_build",
                    "one_apply",
                    "P",
                    "P_H",
                    "FP",
                    "Ac",
                    "fgmres",
                    "gamma",
                    "group_factors",
                ],
            }
        )
    if v8_adaptive_stage_bc_only:
        plan.update(
            {
                "schema": V8_ADAPTIVE_STAGE_BC_ONLY_SCHEMA,
                "method": V8_ADAPTIVE_STAGE_BC_ONLY_METHOD,
                "profile": V8_ADAPTIVE_STAGE_BC_ONLY_PROFILE_ID,
                "v8_adaptive_stage_bc_only": True,
                "research_only": True,
                "oracle_only": False,
                "scalable_candidate": False,
                "pde_solve": "adaptive_impedance_stage_bc_two_source_screen",
                "source_order": [
                    "external_dtn_coupling",
                    "fixed_random_repeat_0",
                ],
                "planned_source_order": [
                    "external_dtn_coupling",
                    "fixed_random_repeat_0",
                    "modal_traction_positive",
                    "modal_traction_negative",
                    "fixed_random_repeat_1",
                ],
                "mandatory_checkpoints": [16, 32, 64],
                "conditional_checkpoints": [],
                "fixed_configuration": {
                    "mass_source": "actual_hcurl_ufcx_exterior_facet_provider",
                    "quadrature_degree": "2*cfg.nedelec_degree",
                    "beta": "level_a_bottom_beta(cfg)",
                    "outer": "right_FGMRES_restart32_zero_guess_max64",
                    "sources_extend_after_positive": True,
                },
                "absolute_terminate_memory_bytes": V8_ADAPTIVE_HARD_STOP_BYTES,
                "watchdog_hard_stop_bytes": V8_ADAPTIVE_HARD_STOP_BYTES,
                "swap_limit_bytes": 0,
                "timeout_seconds": V8_ADAPTIVE_TIMEOUT_SECONDS,
                "setup_target_seconds": None,
                "one_apply_target_seconds": None,
                "numeric_allgather": False,
                "full_interface_replica_per_rank": False,
                "formal_adjudication": False,
                "marker_sequence": [
                    "v8_adaptive_stage_bc_preflight",
                    "v8_adaptive_stage_bc_system_ready",
                    "v8_adaptive_stage_bc_gamma_rhs_ready",
                    "v8_adaptive_stage_bc_factor_ready",
                    "v8_adaptive_stage_bc_harmonic_columns_ready",
                    "v8_adaptive_stage_bc_memory_preflight",
                    "v8_adaptive_stage_bc_coarse_ready",
                    "v8_adaptive_stage_bc_solve_begin",
                    "v8_adaptive_stage_bc_checkpoint",
                    "v8_adaptive_stage_bc_solve_end",
                    "v8_adaptive_stage_bc_classification",
                    "v8_adaptive_stage_bc_cleanup_complete",
                ],
                "forbidden": [
                    "three_scale_identity",
                    "d0_d1_comparison",
                    "refinement",
                    "partition",
                    "moving_pml",
                    "qep",
                    "physical_dtn",
                    "full_side_factor",
                    "source_before_memory_gate",
                    "full_basis_replica_per_rank",
                    "dense_global_coarse_factor",
                    "direct_global_coarse_factor",
                ],
            }
        )
    if v9_source_bridge_only:
        plan.update(
            {
                "schema": V9_SOURCE_BRIDGE_ONLY_SCHEMA,
                "method": V9_SOURCE_BRIDGE_ONLY_METHOD,
                "profile": V9_SOURCE_BRIDGE_ONLY_PROFILE_ID,
                "v9_source_bridge_only": True,
                "research_only": True,
                "oracle_only": False,
                "scalable_candidate": False,
                "pde_solve": "source_canonical_bridge_identity_preflight_only",
                "source_order": list(V9_SOURCE_BRIDGE_ONLY_SOURCES),
                "planned_source_order": list(V9_SOURCE_BRIDGE_ONLY_SOURCES),
                "mandatory_checkpoints": [],
                "conditional_checkpoints": [],
                "fixed_configuration": {
                    "source_builder": "build_current_bare_f_rhs",
                    "current_physical_canonical_keys": True,
                    "numeric_allgather": False,
                    "full_numeric_replica": False,
                },
                "absolute_terminate_memory_bytes": V8_ADAPTIVE_HARD_STOP_BYTES,
                "watchdog_hard_stop_bytes": V8_ADAPTIVE_HARD_STOP_BYTES,
                "swap_limit_bytes": 0,
                "timeout_seconds": V8_ADAPTIVE_TIMEOUT_SECONDS,
                "setup_target_seconds": None,
                "one_apply_target_seconds": None,
                "formal_adjudication": False,
                "marker_sequence": [
                    "v9_source_bridge_preflight",
                    "v9_source_bridge_system_ready",
                    "v9_source_bridge_source_ready",
                    "v9_source_bridge_packet_written",
                    "v9_source_bridge_cleanup_complete",
                ],
                "forbidden": [
                    "v7_research_route",
                    "v8_research_route",
                    "full_side_factor",
                    "group_factors",
                    "interface_schur",
                    "schur_transform",
                    "qep",
                    "physical_dtn",
                    "outer_fgmres",
                    "source_before_current_key_validation",
                ],
            }
        )
    if v9_c0_explicit_coarse_only:
        plan.update(
            {
                "schema": V9_C0_EXPLICIT_COARSE_ONLY_SCHEMA,
                "method": V9_C0_EXPLICIT_COARSE_ONLY_METHOD,
                "profile": V9_C0_EXPLICIT_COARSE_ONLY_PROFILE_ID,
                "v9_c0_explicit_coarse_only": True,
                "research_only": True,
                "oracle_only": True,
                "scalable_candidate": False,
                "pde_solve": "explicit_coarse_one_rhs_oracle",
                "source_order": list(V9_C0_SOURCES),
                "planned_source_order": list(V9_C0_SOURCES),
                "mandatory_checkpoints": [],
                "conditional_checkpoints": [8],
                "fixed_configuration": {
                    "source_builder": "build_current_bare_f_rhs",
                    "source_only": "external_dtn_coupling",
                    "patch_count": V9_C0_PATCH_COUNT,
                    "columns_per_patch": V9_C0_COLUMNS_PER_PATCH,
                    "total_coarse_dof": V9_C0_TOTAL_COARSE_DOF,
                    "composite_apply": "local_to_coarse_to_local_exactly_once",
                    "outer": (
                        "intermediate_only_right_FGMRES_restart32_"
                        "zero_guess_max8_checkpoint8"
                    ),
                },
                "minimum_mem_available_bytes": V9_C0_MIN_AVAILABLE_BYTES,
                "preferred_memory_bytes": V9_C0_PREFERRED_MEMORY_BYTES,
                "warning_memory_bytes": V9_C0_WARNING_MEMORY_BYTES,
                "absolute_terminate_memory_bytes": V9_C0_HARD_STOP_BYTES,
                "watchdog_hard_stop_bytes": V9_C0_HARD_STOP_BYTES,
                "swap_limit_bytes": 0,
                "timeout_seconds": V9_C0_TIMEOUT_SECONDS,
                "setup_target_seconds": V9_C0_SETUP_TARGET_SECONDS,
                "one_apply_target_seconds": V9_C0_ONE_APPLY_TARGET_SECONDS,
                "numeric_allgather": False,
                "full_interface_replica_per_rank": False,
                "formal_adjudication": False,
                "marker_sequence": list(V9_C0_MARKER_SEQUENCE),
                "next_required_stage": {
                    "positive": "V9_C1_MATRIX_FREE_GALERKIN_COARSE",
                    "resource_unavailable": (
                        "V9_C1_MATRIX_FREE_GALERKIN_COARSE"
                    ),
                    "no_signal": "V9_E_STRUCTURED_BACKGROUND_FIXED_LOR",
                },
                "forbidden": [
                    "second_source",
                    "five_source_screen",
                    "top_side",
                    "full_hybrid",
                    "parameter_scan",
                    "retry",
                    "global_direct_factor",
                    "coarse_direct_factor",
                    "qep",
                    "official_rt_a",
                ],
            }
        )
    if v9_e_lor_l2_only:
        plan.update(
            {
                "route": "V9_E_LOR_L2",
                "schema": V9_E_LOR_L2_ONLY_SCHEMA,
                "method": V9_E_LOR_L2_ONLY_METHOD,
                "profile": V9_E_LOR_L2_ONLY_PROFILE_ID,
                "v9_e_lor_l2_only": True,
                "research_only": True,
                "oracle_only": False,
                "scalable_candidate": False,
                "pde_solve": "action_only_fixed_lor_screen",
                "source_order": [],
                "planned_source_order": [],
                "fixed_configuration": {
                    "research_form": "curlcurl_plus_mass",
                    "mass_coefficient": 1.0,
                    "additional_absorbing_shift": 0.0,
                    "physical_dtn_used": False,
                    "operator": "action_only_static_condensed",
                    "fgmres": {
                        "type": "right_fgmres",
                        "restart": 64,
                        "max_it": 256,
                        "rtol": 1.0e-8,
                        "atol": 0.0,
                        "norm": "unpreconditioned",
                    },
                },
                "input_expected": {
                    "relative_paths": list(V9_E_LOR_L2_ALLOWED_INPUTS),
                    "binding": "exact_path_only",
                },
                "factor_inventory": {
                    "owner_local_bounded": True,
                    "max_local_rows": 432,
                    "max_local_rows_limit": 1024,
                    "global_direct_factor_count": 0,
                    "global_coarse_factor_count": 0,
                },
                "absolute_terminate_memory_bytes": V9_E_LOR_L2_ONLY_HARD_STOP_BYTES,
                "watchdog_hard_stop_bytes": V9_E_LOR_L2_ONLY_HARD_STOP_BYTES,
                "swap_limit_bytes": 0,
                "timeout_seconds": V9_E_LOR_L2_ONLY_TIMEOUT_SECONDS,
                "watchdog_required": True,
                "bottom_route_only_required": True,
                "formal_adjudication": False,
                "marker_sequence": list(V9_E_LOR_L2_MARKER_SEQUENCE),
                "numeric_allgather": False,
                "full_basis_replication": False,
                "forbidden": [
                    "physical_dtn",
                    "physical_variational_solve",
                    "global_high_order_aij",
                    "global_lor_matrix",
                    "global_factor",
                    "parameter_scan",
                    "retry",
                    "official_rta",
                ],
            }
        )
    if v9_e_lor_bare_f_external_only:
        plan.update(
            {
                "route": "V9_E_LOR_BARE_F_EXTERNAL",
                "schema": V9_E_LOR_BARE_F_EXTERNAL_ONLY_SCHEMA,
                "method": V9_E_LOR_BARE_F_EXTERNAL_ONLY_METHOD,
                "profile": V9_E_LOR_BARE_F_EXTERNAL_ONLY_PROFILE_ID,
                "v9_e_lor_bare_f_external_only": True,
                "research_only": True,
                "oracle_only": False,
                "scalable_candidate": False,
                "pde_solve": "physical_current_bottom_bare_f_external_one_source",
                "source_order": ["external_dtn_coupling"],
                "planned_source_order": ["external_dtn_coupling"],
                "fixed_configuration": {
                    "bottom_operator": "physical_current_bare_f_matshell",
                    "pc_operator": "fixed_positive_lor_trace_preconditioner",
                    "pc_binding": "preconditioner_only",
                    "pc_curl_coefficient": [1.0, 0.0],
                    "pc_mass_coefficient": [1.0, 0.0],
                    "physical_dtn_used": False,
                    "additional_absorbing_shift": 0.0,
                    "source_only": "external_dtn_coupling",
                    "fgmres": {
                        "type": "right_fgmres",
                        "restart": 64,
                        "max_it": 256,
                        "rtol": 1.0e-8,
                        "atol": 0.0,
                        "explicit_residual_gate": 1.0e-3,
                        "general_record_gate": 1.0e-2,
                    },
                },
                "input_expected": {
                    "relative_path": V9_E_LOR_BARE_F_EXTERNAL_ONLY_INPUT,
                    "binding": "exact_path_only",
                },
                "factor_inventory": {
                    "owner_local_bounded": True,
                    "max_local_rows": 432,
                    "max_local_rows_limit": 1024,
                    "global_direct_factor_count": 0,
                    "global_coarse_factor_count": 0,
                    "global_full_side_factor_count": 0,
                    "global_full_cross_factor_count": 0,
                },
                "absolute_terminate_memory_bytes": (
                    V9_E_LOR_BARE_F_EXTERNAL_ONLY_HARD_STOP_BYTES
                ),
                "watchdog_hard_stop_bytes": (
                    V9_E_LOR_BARE_F_EXTERNAL_ONLY_HARD_STOP_BYTES
                ),
                "swap_limit_bytes": 0,
                "timeout_seconds": V9_E_LOR_BARE_F_EXTERNAL_ONLY_TIMEOUT_SECONDS,
                "watchdog_required": True,
                "bottom_route_only_required": True,
                "formal_adjudication": False,
                "marker_sequence": list(V9_E_LOR_BARE_F_EXTERNAL_MARKER_SEQUENCE),
                "numeric_allgather": False,
                "full_basis_replication": False,
                "global_F": False,
                "global_AIJ": False,
                "global_factor": False,
                "official_rta": {"status": "not_run"},
                "forbidden": [
                    "physical_dtn_matrix",
                    "global_high_order_aij",
                    "global_factor",
                    "global_coarse_factor",
                    "full_cross_section_factor",
                    "parameter_scan",
                    "retry",
                    "five_source",
                    "top",
                    "hybrid",
                    "official_rta",
                ],
            }
        )
    if v9_e_s3_j1_baseline_only:
        plan.update(
            {
                "route": "V9_E_S3B",
                "schema": V9_E_S3_J1_BASELINE_SCHEMA,
                "method": V9_E_S3_J1_BASELINE_METHOD,
                "profile": V9_E_S3_J1_BASELINE_PROFILE_ID,
                "v9_e_s3_j1_baseline_only": True,
                "research_only": True,
                "oracle_only": True,
                "scalable_candidate": False,
                "pde_solve": "bottom_j1_baseline_formal",
                "source_order": [S3B_EXTERNAL_SOURCE_LABEL],
                "planned_source_order": [S3B_EXTERNAL_SOURCE_LABEL],
                "mandatory_checkpoints": [8, 16, 32, 64],
                "conditional_checkpoints": [],
                "fixed_configuration": {
                    "side": "bottom",
                    "bottom_operator": "bare_F",
                    "active_rows": S3B_EXPECTED_ACTIVE_ROWS,
                    "operator_identity": "system.fine_action",
                    "source_label": S3B_EXTERNAL_SOURCE_LABEL,
                    "source_seed": S3B_EXTERNAL_SOURCE_SEED,
                    "source_column": S3B_EXTERNAL_SOURCE_COLUMN,
                    "source_sign": S3B_EXTERNAL_SOURCE_SIGN,
                    "fgmres_restart": S3B_FGMRES_RESTART,
                    "fgmres_initial_max_it": S3B_FGMRES_INITIAL_MAX_IT,
                    "external_one_apply_before_fgmres": True,
                    "full_A_used": False,
                    "qep_calls": 0,
                },
                "input_expected": {
                    "relative_path": V9_E_S3_INPUT_RELATIVE_PATH,
                    "sha256": V9_E_S3_INPUT_SHA256,
                },
                "factor_inventory": {
                    "j1_layer_factor_count_ready": 6,
                    "full_cross_section_factor_count_ready": 6,
                    "factor_count_after_cleanup": 0,
                    "full_side_factor_count": 0,
                    "global_direct_factor_count": 0,
                },
                "absolute_terminate_memory_bytes": S3B_RSS_HARD_BYTES,
                "watchdog_hard_stop_bytes": S3B_RSS_HARD_BYTES,
                "watchdog_required": True,
                "bottom_route_only_required": True,
                "swap_limit_bytes": S3B_SWAP_LIMIT_BYTES,
                "timeout_seconds": S3B_WALL_CAP_SECONDS,
                "formal_adjudication": True,
                "marker_sequence": list(V9_E_S3_MARKER_SEQUENCE),
                "forbidden": [
                    "group_factors",
                    "schur_transform",
                    "full_side_factor",
                    "full_hybrid",
                    "full_hybrid_outer_fgmres",
                    "qep",
                    "physical_dtn",
                    "candidate_sources",
                    "global_direct_factor",
                ],
            }
        )
    if v9_e_s3_structured_b1_only:
        baseline_manifest_path = Path(v9_e_s3_j1_baseline_manifest).resolve()
        plan.update(
            {
                "route": "V9_E_S3B",
                "schema": V9_E_S3_B1_SCHEMA,
                "method": V9_E_S3_B1_METHOD,
                "profile": V9_E_S3_B1_PROFILE_ID,
                "v9_e_s3_structured_b1_only": True,
                "research_only": True,
                "oracle_only": False,
                "scalable_candidate": False,
                "pde_solve": "bottom_structured_background_b1_formal",
                "source_order": list(V5_BARE_F_SOURCE_LABELS),
                "planned_source_order": list(V5_BARE_F_SOURCE_LABELS),
                "mandatory_checkpoints": [8, 16, 32, 64],
                "conditional_checkpoints": [256],
                "fixed_configuration": {
                    "side": "bottom",
                    "bottom_operator": "bare_F",
                    "active_rows": S3B_EXPECTED_ACTIVE_ROWS,
                    "operator_identity": "target_system.fine_action",
                    "source_order": list(V5_BARE_F_SOURCE_LABELS),
                    "fgmres_restart": S3B_FGMRES_RESTART,
                    "fgmres_initial_max_it": S3B_FGMRES_INITIAL_MAX_IT,
                    "fgmres_conditional_total_it": 256,
                    "external_one_apply_before_fgmres": True,
                    "five_source_one_apply": (
                        "conditional_per_source_after_external_positive"
                    ),
                    "source_factory": "S3CurrentLayoutSourceFactory",
                    "source_work_directory": "<run_directory>/s3_source_work",
                    "selected_mode_provider": "_v5_selected_mode_provider",
                    "background_material": "17/50 grating + 33/50 air principal sqrt",
                    "additional_absorbing_shift": 0.0,
                    "exact_physical_fft": False,
                },
                "input_expected": {
                    "relative_path": V9_E_S3_INPUT_RELATIVE_PATH,
                    "sha256": V9_E_S3_INPUT_SHA256,
                },
                "baseline_manifest": {
                    "path": str(baseline_manifest_path),
                    "sha256": str(v9_e_s3_j1_baseline_manifest_sha256),
                },
                "factor_inventory": {
                    "owner_local_bounded_factor_count": S3B_EXPECTED_MODE_COUNT,
                    "owner_local_bounded_factor_count_ready": S3B_EXPECTED_MODE_COUNT,
                    "max_local_rows": S3B_EXPECTED_ROWS_PER_MODE,
                    "max_local_rows_limit": S3B_MAX_LOCAL_ROWS,
                    "full_side_factor_count": 0,
                    "full_cross_section_factor_count": 0,
                    "global_direct_factor_count": 0,
                    "global_coarse_factor_count": 0,
                },
                "absolute_terminate_memory_bytes": S3B_RSS_HARD_BYTES,
                "watchdog_hard_stop_bytes": S3B_RSS_HARD_BYTES,
                "watchdog_required": True,
                "bottom_route_only_required": True,
                "swap_limit_bytes": S3B_SWAP_LIMIT_BYTES,
                "timeout_seconds": S3B_WALL_CAP_SECONDS,
                "formal_adjudication": True,
                "marker_sequence": list(V9_E_S3_B1_MARKER_SEQUENCE),
                "structure_gate": {
                    "phase_model": "topological_orbit_dft_approximation",
                    "fe_sized_topology_coordinate_metadata_allgather": True,
                    "production": False,
                },
                "gate": {
                    "initial_r64_limit": S3B_CANDIDATE_R64_LIMIT,
                    "required_j1_improvement": 4.0,
                    "conditional_r256_limit": S3B_CANDIDATE_R256_LIMIT,
                    "five_source_residual_limit": S3B_FIVE_SOURCE_RESIDUAL_LIMIT,
                    "modal_external_residual_limit": S3B_FIVE_SOURCE_STRICT_RESIDUAL_LIMIT,
                    "max_iterations": S3B_FIVE_SOURCE_MAX_IT,
                },
                "forbidden": [
                    "group_factors",
                    "schur_transform",
                    "full_side_factor",
                    "full_cross_section_factor",
                    "global_direct_factor",
                    "full_basis_replication",
                    "raw_petsc_row_fft",
                    "parameter_scan",
                    "symbol_scan",
                    "ordinary_defaults",
                ],
            }
        )
    if v7_scale_normalized_identity:
        plan.update(
            {
                "schema": V7_SCALE_NORMALIZED_IDENTITY_FORMAL_SCHEMA,
                "method": V7_SCALE_NORMALIZED_IDENTITY_METHOD,
                "profile": V7_SCALE_NORMALIZED_IDENTITY_PROFILE_ID,
                "v7_scale_normalized_identity": True,
                "research_only": True,
                "oracle_only": True,
                "scalable_candidate": False,
                "continuation_required": True,
                "continuation_ready": False,
                "system_created": False,
                "pde_solve": "full_spectrum_continuation_required",
                "formal_adjudication": False,
                "exact_qualification": (
                    "intentional_not_run_by_v7_direct_mainline"
                ),
                "full_spectrum_continuation": "required",
                "identity_target_seconds": V7_IDENTITY_TARGET_SECONDS,
                "identity_hard_seconds": V7_IDENTITY_HARD_SECONDS,
                "preferred_memory_bytes": V7_PREFERRED_MEMORY_BYTES,
                "absolute_terminate_memory_bytes": TASK040_LEVEL_A_HARD_STOP_BYTES,
                "watchdog_hard_stop_bytes": TASK040_LEVEL_A_HARD_STOP_BYTES,
                "swap_limit_bytes": 0,
                "timeout_seconds": TASK040_LEVEL_A_TIMEOUT_SECONDS,
                "numeric_allgather": False,
                "fe_numeric_allgather": False,
                "full_interface_replica_per_rank": False,
                "root_metadata_gather": True,
                "metadata_only_descriptor_gather": True,
                "conditional_authorized": {
                    "refinement": "one_evidence_driven_refinement",
                    "separator_closure": "one_evidence_driven_separator_closure",
                },
                "forbidden": [
                    "threshold_relaxation",
                    "refinement_count_or_parameter_scan",
                    "repeated_separator_closure",
                    "mumps_parameter_scan",
                    "raw_petsc_row_fft",
                    "qep",
                    "full_side_factor",
                ],
            }
        )
    if v7_moving_pml_full_state:
        plan.update(
            {
                "schema": V7_MOVING_PML_FULL_STATE_SCHEMA,
                "method": V7_MOVING_PML_FULL_STATE_METHOD,
                "profile": V7_MOVING_PML_FULL_STATE_PROFILE_ID,
                "v7_moving_pml_full_state": True,
                "research_only": True,
                "oracle_only": True,
                "scalable_candidate": False,
                "pde_solve": "moving_pml_full_state_screen",
                "exact_qualification": (
                    "intentional_not_run_by_v7_moving_pml_mainline"
                ),
                "full_spectrum_continuation": "not_run_by_moving_pml_route",
                "source_order": [
                    "modal_traction_positive",
                    "modal_traction_negative",
                    "external_dtn_coupling",
                    "fixed_random_repeat_0",
                    "fixed_random_repeat_1",
                ],
                "mandatory_checkpoints": [8, 16, 32, 64],
                "conditional_checkpoints": [128],
                "fixed_configuration": {
                    "restart": 32,
                    "zero_initial_guess": True,
                    "pml_profile": "quadratic",
                    "integrated_attenuation": 6.0,
                    "z_collar_layers": 2,
                    "sweep": [0, 1, 2, 2, 1, 0],
                },
                "preferred_memory_bytes": 35 * 2**30,
                "absolute_terminate_memory_bytes": TASK040_LEVEL_A_HARD_STOP_BYTES,
                "watchdog_hard_stop_bytes": TASK040_LEVEL_A_HARD_STOP_BYTES,
                "swap_limit_bytes": 0,
                "timeout_seconds": TASK040_LEVEL_A_TIMEOUT_SECONDS,
                "numeric_allgather": False,
                "full_interface_replica_per_rank": False,
                "forbidden": [
                    "threshold_relaxation",
                    "pml_parameter_scan",
                    "ilu_or_extended_factor",
                    "full_side_factor",
                    "qep",
                ],
            }
        )
    return plan


def _worker_current_resource(
    comm: MPI.Intracomm,
    hard_limit_bytes: int = TASK040_LEVEL_A_HARD_STOP_BYTES,
) -> dict[str, Any]:
    authority = resource_authority_sample(os.getpid(), include_smaps=False)
    process_tree = authority["process_tree"]
    job_cgroup = authority["job_cgroup"]
    has_cgroup = bool(job_cgroup["dedicated_job_cgroup"])
    local_cgroup_memory = int(job_cgroup["memory_current_bytes"] or 0)
    local_cgroup_swap = int(job_cgroup["swap_current_bytes"] or 0)
    process_rss_sum = int(comm.allreduce(int(process_tree["rss_bytes"]), op=MPI.SUM))
    process_swap_sum = int(comm.allreduce(int(process_tree["swap_bytes"]), op=MPI.SUM))
    has_cgroup_any = bool(comm.allreduce(has_cgroup, op=MPI.LOR))
    cgroup_memory_max = int(comm.allreduce(local_cgroup_memory, op=MPI.MAX))
    cgroup_swap_max = int(comm.allreduce(local_cgroup_swap, op=MPI.MAX))
    rss_bytes = max(process_rss_sum, cgroup_memory_max if has_cgroup_any else 0)
    swap_bytes = max(process_swap_sum, cgroup_swap_max if has_cgroup_any else 0)
    readable = bool(
        process_tree["all_status_readable"]
        and (
            not has_cgroup
            or (
                job_cgroup["memory_current_bytes"] is not None
                and job_cgroup["swap_current_bytes"] is not None
            )
        )
    )
    readable = bool(comm.allreduce(readable, op=MPI.LAND))
    return {
        "rss_bytes": rss_bytes,
        "swap_bytes": swap_bytes,
        "process_tree_rss_sum_bytes": process_rss_sum,
        "process_tree_swap_sum_bytes": process_swap_sum,
        "dedicated_cgroup_memory_current_max_bytes": (
            cgroup_memory_max if has_cgroup_any else None
        ),
        "dedicated_cgroup_swap_current_max_bytes": (
            cgroup_swap_max if has_cgroup_any else None
        ),
        "authority_semantics": (
            "max(sum(all-rank process-tree RSS), max(dedicated cgroup memory.current)); "
            "swap uses the same sum/max rule"
        ),
        "all_status_readable": readable,
        "source": "worker_process_tree_and_dedicated_cgroup",
        "pass": bool(
            readable and rss_bytes < int(hard_limit_bytes) and swap_bytes == 0
        ),
        "hard_limit_bytes": int(hard_limit_bytes),
    }


def _v5_bare_f_resource_preflight(
    comm: MPI.Intracomm,
    run_directory: str | Path,
    *,
    hard_stop_bytes: int = TASK040_V5_FRESH_BARE_F_HARD_STOP_BYTES,
) -> dict[str, Any]:
    """Check V5 producer headroom before any mesh or PETSc matrix is built."""

    memory = wsl_memory_snapshot()
    available = memory.get("mem_available_bytes")
    disk = shutil.disk_usage(Path(run_directory).resolve().parent)
    current = _worker_current_resource(
        comm,
        hard_limit_bytes=hard_stop_bytes,
    )
    local = {
        "mem_available_bytes": available,
        "disk_free_bytes": int(disk.free),
        "swap_bytes": int(current["swap_bytes"]),
        "all_status_readable": bool(current["all_status_readable"]),
        "pass": bool(
            isinstance(available, int)
            and available >= TASK040_V5_FRESH_BARE_F_MIN_AVAILABLE_BYTES
            and int(disk.free) >= TASK040_V5_FRESH_BARE_F_MIN_DISK_BYTES
            and int(current["swap_bytes"]) == 0
            and bool(current["all_status_readable"])
        ),
    }
    states = comm.allgather(local)
    passed = bool(comm.allreduce(bool(local["pass"]), op=MPI.LAND))
    return {
        "status": "pass" if passed else "not_run_by_resource_preflight",
        "pass": passed,
        "minimum_mem_available_bytes": TASK040_V5_FRESH_BARE_F_MIN_AVAILABLE_BYTES,
        "minimum_disk_free_bytes": TASK040_V5_FRESH_BARE_F_MIN_DISK_BYTES,
        "hard_stop_bytes": int(hard_stop_bytes),
        "ranks": states,
        "current_worker_resource": current,
    }


def _route_c_resource_preflight(
    comm: MPI.Intracomm,
    run_directory: str | Path,
    *,
    hard_stop_bytes: int = TASK040_V5_ROUTE_C_HARD_STOP_BYTES,
) -> dict[str, Any]:
    """Check Route C headroom without the fresh-producer 90 GiB requirement."""

    memory = wsl_memory_snapshot()
    available = memory.get("mem_available_bytes")
    disk = shutil.disk_usage(Path(run_directory).resolve().parent)
    current = _worker_current_resource(
        comm,
        hard_limit_bytes=hard_stop_bytes,
    )
    minimum_available = int(hard_stop_bytes) + TASK040_V5_ROUTE_C_HEADROOM_BYTES
    local = {
        "mem_available_bytes": available,
        "disk_free_bytes": int(disk.free),
        "swap_bytes": int(current["swap_bytes"]),
        "all_status_readable": bool(current["all_status_readable"]),
        "pass": bool(
            isinstance(available, int)
            and available >= minimum_available
            and int(disk.free) >= TASK040_V5_ROUTE_C_MIN_DISK_BYTES
            and int(current["swap_bytes"]) == 0
            and bool(current["all_status_readable"])
            and bool(current["pass"])
        ),
    }
    states = comm.allgather(local)
    passed = bool(comm.allreduce(bool(local["pass"]), op=MPI.LAND))
    return {
        "route": "C",
        "status": "pass" if passed else "not_run_by_resource_preflight",
        "pass": passed,
        "resource_classification": (
            "route_c_headroom_pass" if passed else "route_c_resource_blocked"
        ),
        "minimum_mem_available_bytes": minimum_available,
        "required_headroom_bytes": TASK040_V5_ROUTE_C_HEADROOM_BYTES,
        "minimum_disk_free_bytes": TASK040_V5_ROUTE_C_MIN_DISK_BYTES,
        "hard_stop_bytes": int(hard_stop_bytes),
        "swap_limit_bytes": 0,
        "timeout_seconds": TASK040_LEVEL_A_TIMEOUT_SECONDS,
        "ranks": states,
        "current_worker_resource": current,
    }


def _route_c_wall_observation(
    *,
    formal_elapsed_seconds: float,
    krylov_elapsed_seconds: float,
    last_krylov_elapsed_seconds: float | None,
    observation_index: int,
    budget_seconds: float = TASK040_LEVEL_A_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Build conservative wall-budget evidence for conditional checkpoint 256."""

    interval = (
        float(krylov_elapsed_seconds)
        if last_krylov_elapsed_seconds is None
        else float(krylov_elapsed_seconds) - float(last_krylov_elapsed_seconds)
    )
    predicted_remaining = interval * (3 if int(observation_index) == 0 else 1)
    remaining = float(budget_seconds) - float(formal_elapsed_seconds)
    predicted_total = float(formal_elapsed_seconds) + predicted_remaining
    passed = bool(
        np.isfinite(interval)
        and interval >= 0.0
        and np.isfinite(remaining)
        and remaining > 0.0
        and np.isfinite(predicted_total)
        and predicted_total <= float(budget_seconds)
    )
    return {
        "budget_seconds": float(budget_seconds),
        "elapsed_seconds": float(formal_elapsed_seconds),
        "formal_start_elapsed_seconds": float(formal_elapsed_seconds),
        "krylov_elapsed_seconds": float(krylov_elapsed_seconds),
        "interval_since_previous_128_seconds": float(interval),
        "predicted_remaining_seconds": float(predicted_remaining),
        "remaining_seconds": max(remaining, 0.0),
        "predicted_total_seconds": float(predicted_total),
        "observation_index": int(observation_index),
        "formula": (
            "predicted_total=formal_elapsed + interval * "
            "(3 if first_128_observation else 1)"
        ),
        "pass": passed,
    }


def _v9_e_lor_bare_f_external_authority_preflight(
    *,
    comm: MPI.Intracomm,
    input_path: str | Path,
    input_sha256: str,
    physical_model_sha256: str,
    source_sha: str,
    watchdog_enabled: bool,
    bottom_route_only: bool,
) -> dict[str, Any]:
    """Bind the h10 external modes to the tracked current-input authority."""

    root = Path(__file__).resolve().parents[1]
    authority_path = root / (
        "benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/"
        "task039_t2_a0_preflight_v1.json"
    )
    expected_input = (
        root / V9_E_LOR_BARE_F_EXTERNAL_ONLY_INPUT
    ).resolve()
    expected_input_sha256 = (
        "e8b60ba70daa2074c21603d463790a28c881d35d7bd17b2b8315fef0318007b6"
    )
    expected_physical_sha256 = (
        "db52c70d667caa726e2b2e04b646402415a377fa7bbcef42c87ffc816b9b2a7a"
    )
    expected_authority_file_sha256 = (
        "f006fb572cda96a2a25011c80b80d9c9d1efca4d6ed7e48b9b8cb05e72b53862"
    )
    expected_inventory_sha256 = (
        "296c9e74d0a15c0dd2671e54fa7de2709c5f19f0c9f8665ffc4d35d740d4faea"
    )
    expected_bottom_key_sha256 = (
        "73de8b84329b526b5b4237cdfb5885c5281a23c9374737d6a40b74b7c7611f35"
    )
    expected_bottom_metadata_sha256 = (
        "7b9850e6e3ec168f6f7d3d84423d2d82689d076af56b555d36272ab82a89601a"
    )
    expected_bottom_beta_sha256 = (
        "e9948555ffb6a36104aee664ee34768c1a9458cc748e60b8b4eb4b6cb3e45118"
    )
    expected_resolved_sha256 = (
        "a35bb4e35088a33ecd59161bf41307c092cae4a11dba30e8336026833bc40c3e"
    )
    checks: dict[str, bool] = {}
    failures: list[str] = []

    def check(name: str, value: bool) -> None:
        checks[name] = bool(value)
        if not value:
            failures.append(name)

    observed: dict[str, Any] = {
        "input_path": str(Path(input_path).resolve()),
        "input_sha256": str(input_sha256),
        "physical_model_sha256": str(physical_model_sha256),
        "source_sha": str(source_sha),
    }
    external_mode_authority: dict[str, Any] | None = None
    try:
        authority_bytes = authority_path.read_bytes()
        authority_file_sha256 = hashlib.sha256(authority_bytes).hexdigest()
        authority_payload = json.loads(authority_bytes)
        frozen = authority_payload["inventory_authority"]
        frozen_inventory = frozen["external_mode_inventory"]
        check(
            "authority_file_sha256",
            authority_file_sha256 == expected_authority_file_sha256,
        )
        check(
            "inventory_canonical_sha256",
            str(frozen["canonical_sha256"]) == expected_inventory_sha256,
        )
        spec = load_and_resolve(input_path)
        current_inventory = spec.as_jsonable()["derived"][
            "external_mode_inventory"
        ]
        actual_input_sha256 = hashlib.sha256(
            Path(input_path).resolve().read_bytes()
        ).hexdigest()
        resolved_sha256 = resolved_config_sha256(spec)
        observed.update(
            {
                "authority_file_sha256": authority_file_sha256,
                "current_input_sha256": actual_input_sha256,
                "current_physical_model_sha256": str(spec.physical_model_sha256),
                "resolved_config_sha256": resolved_sha256,
                "authority_path": str(authority_path),
            }
        )
        check("input_path", Path(input_path).resolve() == expected_input)
        check(
            "input_sha256",
            actual_input_sha256 == str(input_sha256) == expected_input_sha256,
        )
        check(
            "physical_model_sha256",
            str(spec.physical_model_sha256)
            == str(physical_model_sha256)
            == expected_physical_sha256,
        )
        check("external_mode_inventory_exact", current_inventory == frozen_inventory)
        check(
            "inventory_source_path",
            str(frozen["source_path"])
            == V9_E_LOR_BARE_F_EXTERNAL_ONLY_INPUT,
        )
        check("resolved_config_sha256", resolved_sha256 == expected_resolved_sha256)
        keys = tuple(frozen_inventory["keys"])
        modes = tuple(frozen_inventory["modes"])
        bottom_keys = tuple(key for key in keys if str(key["side"]) == "bottom")
        bottom_modes = tuple(mode for mode in modes if str(mode["side"]) == "bottom")
        key_tokens = tuple(
            (
                int(key["m"]),
                int(key["n"]),
                str(key["polarization"]),
                str(key["side"]),
            )
            for key in keys
        )
        bottom_key_sha256 = canonical_mode_keys_sha256(bottom_keys)
        bottom_metadata_sha256 = canonical_external_mode_metadata_sha256(
            bottom_modes
        )
        bottom_beta_sha256 = canonical_selected_packet_beta_sha256(
            [mode["beta"] for mode in bottom_modes]
        )
        check(
            "full_count",
            len(keys) == len(modes) == int(frozen_inventory["count"]) == 604,
        )
        check("bottom_count", len(bottom_keys) == len(bottom_modes) == 300)
        check("unique_physical_keys", len(set(key_tokens)) == len(key_tokens))
        check("bottom_key_sha256", bottom_key_sha256 == expected_bottom_key_sha256)
        check(
            "bottom_metadata_sha256",
            bottom_metadata_sha256 == expected_bottom_metadata_sha256,
        )
        check("bottom_beta_sha256", bottom_beta_sha256 == expected_bottom_beta_sha256)
        check("mpi_size", int(comm.size) == V9_E_LOR_BARE_F_EXTERNAL_ONLY_MPI_SIZE)
        check("watchdog_enabled", bool(watchdog_enabled))
        check("bottom_route_only", bool(bottom_route_only))
        external_mode_authority = {
            "count": len(bottom_keys),
            "canonical_keys": list(bottom_keys),
            "beta_metadata": list(bottom_modes),
            "canonical_key_list_sha256": bottom_key_sha256,
            "resolved_mode_metadata_sha256": bottom_metadata_sha256,
            "legacy_beta_metadata_sha256": expected_bottom_beta_sha256,
            "legacy_beta_metadata_sha256_expected": expected_bottom_beta_sha256,
            "legacy_beta_metadata_schema": "canonical_json_bottom_beta_pairs",
            "resolved_config_sha256": resolved_sha256,
            "index177_key": bottom_keys[177],
            "authority_file_path": str(authority_path),
            "authority_file_sha256": authority_file_sha256,
            "inventory_canonical_sha256": expected_inventory_sha256,
            "source_path": str(frozen["source_path"]),
            "full_count": len(keys),
            "bottom_count": len(bottom_keys),
        }
    except (KeyError, OSError, TypeError, ValueError) as exc:
        failures.append(f"metadata_exception:{type(exc).__name__}")
        observed["exception"] = f"{type(exc).__name__}: {exc}"
    passed = not failures
    return {
        "status": "pass" if passed else "identity_fail",
        "pass": passed,
        "checks": checks,
        "failures": failures,
        "observed": observed,
        "expected": {
            "authority_file_sha256": expected_authority_file_sha256,
            "inventory_canonical_sha256": expected_inventory_sha256,
            "input_sha256": expected_input_sha256,
            "physical_model_sha256": expected_physical_sha256,
            "resolved_config_sha256": expected_resolved_sha256,
            "bottom_key_sha256": expected_bottom_key_sha256,
            "bottom_metadata_sha256": expected_bottom_metadata_sha256,
            "bottom_beta_sha256": expected_bottom_beta_sha256,
            "full_count": 604,
            "bottom_count": 300,
            "legacy_beta_metadata_schema": "canonical_json_bottom_beta_pairs",
        },
        "external_mode_authority": (
            external_mode_authority if passed else None
        ),
    }


def _v5_runtime_environment_preflight(
    comm: MPI.Intracomm,
    *,
    watchdog_enabled: bool,
    bottom_route_only: bool,
) -> dict[str, Any]:
    """Record and gate the actual V5 worker runtime, not its plan claims."""

    executable = str(sys.executable)
    resolved_executable = str(Path(sys.executable).resolve())
    qualified_activation = os.environ.get("MYFENICS_NATIVE_COMPLEX_ENV") == "1"
    thread_environment = {
        name: os.environ.get(name) for name in TASK040_V5_REQUIRED_THREAD_ENV
    }
    thread_values_are_one = all(
        value == "1" for value in thread_environment.values()
    )
    scalar_dtype = np.dtype(PETSc.ScalarType)
    int_dtype = np.dtype(PETSc.IntType)
    repository_root = Path(__file__).resolve().parents[1]
    executable_is_qualified = False
    try:
        Path(executable).absolute().relative_to(repository_root / ".venv")
        executable_is_qualified = True
    except ValueError:
        executable_is_qualified = False
    local = {
        "comm_size": int(comm.size),
        "petsc_scalar_type": str(scalar_dtype),
        "petsc_int_type": str(int_dtype),
        "qualified_activation": qualified_activation,
        "sys_executable": executable,
        "resolved_executable": resolved_executable,
        "executable_is_repository_venv": executable_is_qualified,
        "thread_environment": thread_environment,
        "threads_per_rank": 1 if thread_values_are_one else None,
        "process_tree_watchdog_enabled": bool(watchdog_enabled),
        "bottom_route_only": bool(bottom_route_only),
    }
    checks = {
        "mpi_size": local["comm_size"] == TASK040_LEVEL_A_MPI_SIZE,
        "petsc_scalar_complex128": scalar_dtype == np.dtype(np.complex128),
        "petsc_int_type_recorded": bool(str(int_dtype)),
        "qualified_activation": qualified_activation,
        "repository_venv_executable": executable_is_qualified,
        "threads_one": thread_values_are_one,
        "process_tree_watchdog_enabled": bool(watchdog_enabled),
        "bottom_route_only": bool(bottom_route_only),
    }
    local["checks"] = checks
    local["pass"] = all(checks.values())
    states = comm.allgather(local)
    passed = bool(comm.allreduce(bool(local["pass"]), op=MPI.LAND))
    collective_checks = {
        name: all(bool(state.get("checks", {}).get(name)) for state in states)
        for name in checks
    }
    return {
        "status": "pass" if passed else "not_run_by_resource_preflight",
        "pass": passed,
        "checks": collective_checks,
        "expected": {
            "mpi_size": TASK040_LEVEL_A_MPI_SIZE,
            "petsc_scalar_type": "complex128",
            "qualified_activation": True,
            "threads_per_rank": 1,
            "process_tree_watchdog_enabled": True,
            "bottom_route_only": True,
        },
        "ranks": states,
    }


def _v5_authority_identity_preflight(
    *,
    comm: MPI.Intracomm,
    input_path: str | Path | None,
    input_sha256: str,
    physical_model_sha256: str,
    source_sha: str,
    watchdog_enabled: bool,
    bottom_route_only: bool,
) -> dict[str, Any]:
    """Bind the fresh producer to the frozen source and metadata identities.

    This is deliberately metadata-only.  It reads the tracked probe manifest,
    selected-packet metadata, resolved configuration bytes, and the official
    input bytes; it never opens a frozen numerical ``.npy`` array.
    """

    root = Path(__file__).resolve().parents[1]
    checks: dict[str, bool] = {}
    failures: list[str] = []

    def check(name: str, value: bool) -> None:
        checks[name] = bool(value)
        if not value:
            failures.append(name)

    observed: dict[str, Any] = {
        "input_sha256": str(input_sha256),
        "physical_model_sha256": str(physical_model_sha256),
        "source_sha": str(source_sha),
        "input_path": None if input_path is None else str(Path(input_path)),
    }
    external_mode_authority: dict[str, Any] | None = None
    expected = {
        "input_sha256": TASK040_V1_2_INPUT_SHA256,
        "physical_model_sha256": TASK040_V1_2_PHYSICAL_MODEL_SHA256,
        "selected_manifest_sha256": TASK040_V1_2_SELECTED_MANIFEST_SHA256,
        "resolved_config_sha256": None,
        "probe_manifest_sha256": TASK040_V1_2_PROBE_MANIFEST_SHA256,
        "branch": TASK040_V4_FROZEN_BRANCH,
        "upstream_ref": f"origin/{TASK040_V4_FROZEN_BRANCH}",
        "upstream_sha": str(source_sha),
        "ahead_count": 0,
        "behind_count": 0,
    }
    try:
        probe_path, probe_manifest = _v1_2_load_manifest()
        probe_identity = probe_manifest["identity"]
        probe_sha256 = hashlib.sha256(probe_path.read_bytes()).hexdigest()
        observed["probe_manifest_sha256"] = probe_sha256
        check(
            "probe_manifest_sha256",
            probe_sha256 == TASK040_V1_2_PROBE_MANIFEST_SHA256,
        )

        selected_path = root / str(probe_identity["selected_manifest"])
        selected_payload = json.loads(selected_path.read_bytes())
        selected_sha256 = hashlib.sha256(selected_path.read_bytes()).hexdigest()
        selected_identity = selected_path.with_name("identity.json")
        selected_identity_payload = json.loads(selected_identity.read_bytes())
        selected_identity_sha256 = hashlib.sha256(
            json.dumps(
                selected_identity_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        observed.update(
            {
                "selected_manifest_sha256": selected_sha256,
                "selected_identity_sha256": selected_identity_sha256,
                "selected_manifest_path": str(selected_path),
            }
        )
        expected["selected_identity_sha256"] = str(
            probe_identity["selected_identity_sha256"]
        )
        check(
            "selected_manifest_sha256",
            selected_sha256
            == str(probe_identity["selected_manifest_sha256"])
            == TASK040_V1_2_SELECTED_MANIFEST_SHA256,
        )
        check(
            "selected_identity_sha256",
            selected_identity_sha256
            == str(probe_identity["selected_identity_sha256"])
            == str(selected_payload["identity_sha256"]),
        )

        resolved_path = root / str(
            probe_manifest["lower_fourier_floquet_basis"]["authority_path"]
        )
        resolved_bytes = resolved_path.read_bytes()
        resolved_sha256 = hashlib.sha256(resolved_bytes).hexdigest()
        resolved_payload = json.loads(resolved_bytes)
        resolved_inventory = resolved_payload["derived"]["external_mode_inventory"]
        bottom_keys = tuple(
            key for key in resolved_inventory["keys"] if str(key["side"]) == "bottom"
        )
        bottom_metadata = tuple(
            mode
            for mode in resolved_inventory["modes"]
            if str(mode["side"]) == "bottom"
        )
        lower_authority = probe_manifest["lower_fourier_floquet_basis"]
        external_mode_authority = {
            "count": int(lower_authority["count"]),
            "canonical_keys": bottom_keys,
            "beta_metadata": bottom_metadata,
            "canonical_key_list_sha256": str(
                lower_authority["canonical_key_list_sha256"]
            ),
            "resolved_mode_metadata_sha256": canonical_external_mode_metadata_sha256(
                bottom_metadata
            ),
            "legacy_beta_metadata_sha256": str(
                lower_authority["beta_metadata_sha256"]
            ),
            "legacy_beta_metadata_sha256_expected": (
                TASK040_V1_2_LOWER_LEGACY_BETA_METADATA_SHA256
            ),
            "resolved_config_sha256": resolved_sha256,
            "index177_key": bottom_keys[177] if len(bottom_keys) > 177 else None,
        }
        observed.update(
            {
                "resolved_config_sha256": resolved_sha256,
                "resolved_config_path": str(resolved_path),
                "external_mode_count": len(bottom_keys),
                "external_mode_key_list_sha256": canonical_mode_keys_sha256(
                    bottom_keys
                ),
                "external_mode_resolved_mode_metadata_sha256": (
                    canonical_external_mode_metadata_sha256(bottom_metadata)
                ),
                "external_mode_legacy_beta_metadata_sha256": str(
                    lower_authority["beta_metadata_sha256"]
                ),
                "external_mode_index177_key": external_mode_authority["index177_key"],
            }
        )
        expected["resolved_config_sha256"] = str(
            probe_identity["exact_spool_resolved_config_sha256"]
        )
        check(
            "resolved_config_sha256",
            resolved_sha256
            == str(probe_identity["exact_spool_resolved_config_sha256"]),
        )
        check(
            "external_mode_count",
            len(bottom_keys) == int(lower_authority["count"]) == 296,
        )
        check(
            "external_mode_key_list_sha256",
            observed["external_mode_key_list_sha256"]
            == str(lower_authority["canonical_key_list_sha256"])
            == "046afb0b3d3531f728dc958c1b0c8a321ffa51fb8a0e6ecf6834d462d5ab37e5",
        )
        check(
            "external_mode_resolved_mode_metadata_sha256",
            observed["external_mode_resolved_mode_metadata_sha256"]
            == str(external_mode_authority["resolved_mode_metadata_sha256"])
            == TASK040_V1_2_LOWER_RESOLVED_MODE_METADATA_SHA256,
        )
        check(
            "external_mode_legacy_beta_metadata_sha256",
            observed["external_mode_legacy_beta_metadata_sha256"]
            == str(external_mode_authority["legacy_beta_metadata_sha256"])
            == str(external_mode_authority["legacy_beta_metadata_sha256_expected"])
            == TASK040_V1_2_LOWER_LEGACY_BETA_METADATA_SHA256,
        )
        check(
            "external_mode_resolved_authority_sha256",
            resolved_sha256
            == str(lower_authority["authority_sha256"])
            == "f965c38abea08bee0ff83a6603e336ca4823deb932af7064aed3c571f8f63883",
        )
        check("external_mode_index177_present", len(bottom_keys) > 177)

        if input_path is None:
            check("input_path_present", False)
        else:
            actual_input_sha256 = hashlib.sha256(
                Path(input_path).read_bytes()
            ).hexdigest()
            observed["input_file_sha256"] = actual_input_sha256
            check("input_file_sha256", actual_input_sha256 == str(input_sha256))
        check(
            "input_sha256_frozen",
            str(input_sha256) == TASK040_V1_2_INPUT_SHA256,
        )
        check(
            "physical_model_sha256_frozen",
            str(physical_model_sha256) == TASK040_V1_2_PHYSICAL_MODEL_SHA256,
        )
        check(
            "probe_input_sha256",
            str(probe_identity["input_sha256"]) == TASK040_V1_2_INPUT_SHA256,
        )
        check(
            "probe_physical_model_sha256",
            str(probe_identity["physical_model_sha256"])
            == TASK040_V1_2_PHYSICAL_MODEL_SHA256,
        )
        check(
            "selected_payload_physical_sha256",
            str(selected_payload["identity"]["physical_sha256"])
            == TASK040_V1_2_PHYSICAL_MODEL_SHA256,
        )
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        failures.append(f"metadata_exception:{type(exc).__name__}")
        observed["exception"] = f"{type(exc).__name__}: {exc}"

    actual_head: str | None = None
    actual_branch: str | None = None
    upstream_ref: str | None = None
    upstream_sha: str | None = None
    ahead_count: int | None = None
    behind_count: int | None = None
    dirty: str | None = None
    try:

        def git_output(arguments: list[str]) -> str:
            return subprocess.run(
                arguments,
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

        actual_head = git_output(["git", "rev-parse", "HEAD"])
        actual_branch = git_output(["git", "symbolic-ref", "--short", "HEAD"])
        upstream_ref = git_output(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"]
        )
        upstream_sha = git_output(["git", "rev-parse", "@{upstream}"])
        ahead_behind = git_output(
            ["git", "rev-list", "--left-right", "--count", "HEAD...@{upstream}"]
        ).split()
        if len(ahead_behind) != 2:
            raise ValueError("git ahead/behind output is not a pair")
        ahead_count, behind_count = map(int, ahead_behind)
        dirty = git_output(["git", "status", "--porcelain", "--untracked-files=all"])
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        failures.append(f"git_identity_exception:{type(exc).__name__}")
        observed["git_exception"] = f"{type(exc).__name__}: {exc}"
    observed.update(
        {
            "committed_source_sha": actual_head,
            "branch": actual_branch,
            "upstream_ref": upstream_ref,
            "upstream_sha": upstream_sha,
            "ahead_count": ahead_count,
            "behind_count": behind_count,
            "worktree_porcelain": dirty,
        }
    )
    expected_upstream_ref = str(expected["upstream_ref"])
    check("committed_source_sha", actual_head == str(source_sha))
    check("branch_exact", actual_branch == TASK040_V4_FROZEN_BRANCH)
    check("upstream_ref_exact", upstream_ref == expected_upstream_ref)
    check("upstream_sha", upstream_sha == str(source_sha))
    check("ahead_count_zero", ahead_count == 0)
    check("behind_count_zero", behind_count == 0)
    check("ahead_behind_zero", ahead_count == 0 and behind_count == 0)
    check("worktree_clean", dirty == "")

    operator_semantics_audit = build_v5_operator_semantics_audit(
        source_sha=source_sha,
        provenance={"observed": observed, "expected": expected, "checks": checks},
    )
    check(
        "modal_source_identity",
        bool(operator_semantics_audit["modal_source_identity"]["pass"]),
    )
    runtime_preflight = _v5_runtime_environment_preflight(
        comm,
        watchdog_enabled=watchdog_enabled,
        bottom_route_only=bottom_route_only,
    )
    for name, value in runtime_preflight["checks"].items():
        check(f"runtime_{name}", bool(value))

    return {
        "status": "pass" if not failures else "identity_fail",
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "observed": observed,
        "expected": expected,
        "operator_semantics_audit": operator_semantics_audit,
        "external_mode_authority": external_mode_authority,
        "runtime_preflight": runtime_preflight,
        "authority": {
            "probe_manifest": str(probe_path)
            if "probe_path" in locals()
            else str(root / TASK040_V1_2_PROBE_MANIFEST),
            "selected_manifest": observed.get("selected_manifest_path"),
            "resolved_config": observed.get("resolved_config_path"),
        },
    }


def _v5_write_operator_semantics_audit(
    comm: MPI.Intracomm,
    run_directory: str | Path,
    audit: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Persist the compact semantics audit before any PETSc system build."""

    if not isinstance(audit, Mapping):
        return None
    run_root = Path(run_directory)
    path = run_root / "operator_semantics_audit.json"
    if comm.rank == 0:
        run_root.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError(f"V5 operator audit already exists: {path}")
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(
            json.dumps(dict(audit), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
        file_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    else:
        file_sha256 = None
    file_sha256 = comm.bcast(file_sha256, root=0)
    return {
        "path": str(path.relative_to(run_root)),
        "sha256": str(file_sha256),
        "content_sha256": str(audit.get("record_sha256", "")),
    }


def _emit(
    callback: Callable[[str, Mapping[str, Any]], None] | None,
    stage: str,
    **detail: Any,
) -> None:
    if callback is not None:
        callback(stage, detail)


def _forward_v5_marker(
    callback: Callable[[str, Mapping[str, Any]], None] | None,
    event_stage: str,
    detail: Mapping[str, Any],
) -> None:
    """Forward V5 marker detail without colliding with the event stage key."""

    payload = dict(detail)
    if "stage" in payload:
        payload["identity_stage"] = payload.pop("stage")
    _emit(callback, event_stage, **payload)


def _v2_collective_stage_error(
    comm: MPI.Intracomm,
    stage: str,
    local_error: str | None,
) -> None:
    """Propagate one V2 packet-stage error before another collective."""

    errors = comm.allgather(local_error)
    first = next(
        ((rank, error) for rank, error in enumerate(errors) if error is not None),
        None,
    )
    if first is not None:
        rank, error = first
        raise ValueError(
            f"V2 packet stage {stage} failed on first failing rank {rank}: {error}"
        )


def _v2_group_marker(
    callback: Callable[[str, Mapping[str, Any]], None] | None,
    stage: str,
    *,
    group: int,
    layout: Any,
    span_size: int | None,
    comm: MPI.Intracomm,
    started: float | None = None,
    **detail: Any,
) -> None:
    """Emit one V2 group marker with a cross-rank maximum elapsed time."""

    marker_detail = {
        "group": int(group),
        "local_rows": int(layout.audit["local_row_count"]),
        "local_blocks": int(len(layout.blocks)),
        "span_size": None if span_size is None else int(span_size),
    }
    if started is not None:
        marker_detail["cross_rank_max_elapsed_seconds"] = float(
            comm.allreduce(time.perf_counter() - started, op=MPI.MAX)
        )
    _emit(callback, stage, **marker_detail, **detail)


def _file_marker_callback(
    stages_path: str | Path | None,
    markers_path: str | Path | None,
    *,
    enabled: bool,
) -> Callable[[str, Mapping[str, Any]], None] | None:
    if not enabled or stages_path is None or markers_path is None:
        return None
    stages_path = Path(stages_path)
    markers_path = Path(markers_path)
    stages_path.parent.mkdir(parents=True, exist_ok=True)
    markers_path.parent.mkdir(parents=True, exist_ok=True)

    def record(stage: str, detail: Mapping[str, Any]) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        status = "running" if stage.endswith("_begin") else "complete"
        stage_record = {
            "timestamp_utc": timestamp,
            "stage": stage,
            "status": status,
            **dict(detail),
        }
        marker_record = {
            "timestamp_utc": timestamp,
            "stage": stage,
            "detail": dict(detail),
        }
        with stages_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(stage_record, sort_keys=True) + "\n")
        with markers_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(marker_record, sort_keys=True) + "\n")

    return record


def _load_s3_j1_baseline_manifest(
    comm: MPI.Intracomm,
    manifest_path: str | Path,
) -> tuple[Any, str, str]:
    """Read the candidate's direct baseline JSON once and broadcast its hash."""

    payload: dict[str, Any] | None = None
    if int(comm.rank) == 0:
        try:
            path = Path(manifest_path).resolve()
            raw = path.read_bytes()
            observed_sha256 = hashlib.sha256(raw).hexdigest()
            manifest = json.loads(raw.decode("utf-8"))
            payload = {
                "manifest": manifest,
                "observed_sha256": observed_sha256,
                "resolved_path": str(path),
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001 - broadcast the root read failure
            payload = {
                "manifest": None,
                "observed_sha256": None,
                "resolved_path": None,
                "error": f"{type(exc).__name__}: {exc}",
            }
    payload = comm.bcast(payload, root=0)
    if payload is None or payload.get("error") is not None:
        detail = "missing root payload" if payload is None else payload.get("error")
        raise ValueError(f"V9-E S3 J1 baseline manifest read failed: {detail}")
    return (
        payload["manifest"],
        str(payload["observed_sha256"]),
        str(payload["resolved_path"]),
    )


def _s3_fixed_input_identity(
    comm: MPI.Intracomm,
    input_path: str | Path,
) -> tuple[str, str]:
    """Resolve, read, and hash the frozen S3 input collectively."""

    payload: dict[str, Any] | None = None
    if int(comm.rank) == 0:
        try:
            resolved_path = Path(input_path).resolve()
            raw = resolved_path.read_bytes()
            payload = {
                "resolved_path": str(resolved_path),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001 - broadcast the root read failure
            payload = {
                "resolved_path": None,
                "sha256": None,
                "error": f"{type(exc).__name__}: {exc}",
            }
    payload = comm.bcast(payload, root=0)
    if payload is None or payload.get("error") is not None:
        detail = "missing root payload" if payload is None else payload.get("error")
        raise ValueError(f"V9-E S3 fixed input identity failed: {detail}")
    return str(payload["resolved_path"]), str(payload["sha256"])


def _destroy_explicit_components(components: Any) -> bool:
    destroyed = True
    for name in ("H", "D", "C", "F"):
        matrix = getattr(components, name, None)
        if matrix is not None:
            matrix.destroy()
            setattr(components, name, None)
        destroyed = destroyed and getattr(components, name, None) is None
    return bool(destroyed)


def _route_c_atomic_npy(path: Path, values: np.ndarray) -> str:
    """Persist one owner-local Route C basis vector and return its file hash."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("wb") as stream:
        np.save(stream, np.ascontiguousarray(values), allow_pickle=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _route_c_json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _route_c_json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_route_c_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_route_c_json_safe(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _route_c_json_safe(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"Route C value is not JSON-safe: {type(value)!r}")


def _route_c_atomic_json(path: Path, payload: Mapping[str, Any]) -> str:
    """Write one Route C metadata artifact atomically and return its file hash."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    encoded = json.dumps(
        _route_c_json_safe(payload),
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    with temporary.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _route_c_local_vec_sha256(vector: PETSc.Vec) -> str:
    values = np.asarray(vector.getArray(readonly=True), dtype=np.complex128)
    return hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest()


def _route_c_global_digest(comm: MPI.Intracomm, local_digest: str) -> str:
    digests = comm.gather(str(local_digest), root=0)
    if comm.rank == 0:
        value = hashlib.sha256("\n".join(digests).encode("ascii")).hexdigest()
    else:
        value = None
    return str(comm.bcast(value, root=0))


def _route_c_source_definition_sha256(
    label: str,
    metadata: Mapping[str, Any],
) -> str:
    """Hash only rank-independent source semantics, not a shard/repeat."""

    semantic = {
        key: value
        for key, value in metadata.items()
        if key not in {"rhs_generation", "source_build_count"}
    }
    semantic["label"] = str(label)
    encoded = json.dumps(
        _route_c_json_safe(semantic),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _route_c_collective_stage_error(
    comm: MPI.Intracomm,
    stage: str,
    local_error: Exception | None,
) -> None:
    payload = None
    if local_error is not None:
        payload = {
            "rank": int(comm.rank),
            "type": type(local_error).__name__,
            "message": str(local_error),
        }
    failures = comm.allgather(payload)
    first = next((item for item in failures if item is not None), None)
    if first is not None:
        raise RuntimeError(
            f"Route C {stage} failed on rank {first['rank']}: "
            f"{first['type']}: {first['message']}"
        )


def _route_c_stop_result(
    *,
    status: str,
    classification: str,
    source_sha: str,
    input_sha256: str,
    physical_model_sha256: str,
    identity_preflight: Mapping[str, Any],
    resource_preflight: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": TASK040_V5_ROUTE_C_SCHEMA,
        "method": TASK040_V5_ROUTE_C_METHOD,
        "profile": TASK040_V5_ROUTE_C_PROFILE_ID,
        "status": status,
        "classification": classification,
        "source_sha": str(source_sha),
        "input_sha256": str(input_sha256),
        "physical_model_sha256": str(physical_model_sha256),
        "identity_preflight": _route_c_json_safe(identity_preflight),
        "resource_preflight": (
            None
            if resource_preflight is None
            else _route_c_json_safe(resource_preflight)
        ),
        "system_created": False,
        "rhs_vectors_loaded": 0,
        "exact_output_vectors_loaded": 0,
        "full_side_exact_factor_count": 0,
        "qep_calls": 0,
        "pde_solve": "not_run",
        "outer_ksp": "not_run",
        "downstream": {
            "projection": "not_run_by_route_c_preflight",
            "lift": "not_run_by_route_c_preflight",
            "response": "not_run_by_route_c_preflight",
            "full_hybrid": "not_run_by_route_c_preflight",
        },
    }


def _route_c_observed_qep_calls(inventory: Mapping[str, Any]) -> int:
    """Require a real post-assembly QEP count before Route C continues."""

    if "qep_calls" not in inventory:
        raise RuntimeError("Route C assembly inventory omitted observed qep_calls")
    observed = inventory["qep_calls"]
    if isinstance(observed, bool) or not isinstance(observed, (int, np.integer)):
        raise RuntimeError(f"Route C assembly qep_calls is not an integer: {observed!r}")
    observed = int(observed)
    if observed != 0:
        raise RuntimeError(f"Route C assembly observed qep_calls={observed}")
    return observed


def _route_c_observed_external_contract(
    inventory: Mapping[str, Any],
    matrix_objects: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the observed minimal external RHS construction inventory."""

    expected = {
        "minimal_external_coupling_objects_constructed": 1,
        "minimal_external_surface_component_count": 2,
        "minimal_external_coupling_construction_call_count": 2,
        "minimal_external_component_instances_total": 4,
        "minimal_external_peak_live_components": 2,
        "minimal_external_coupling_kind_count": 1,
    }
    observed = {name: inventory.get(name) for name in expected}
    checks = {name: observed[name] == value for name, value in expected.items()}
    observed_matrix_objects = {
        name: matrix_objects.get(name) for name in ("C", "D", "H")
    }
    checks["c_d_h_zero"] = observed_matrix_objects == {"C": 0, "D": 0, "H": 0}
    if not all(checks.values()):
        raise RuntimeError(
            "Route C minimal external RHS inventory failed: "
            f"observed={observed!r}, matrix_objects={observed_matrix_objects!r}, "
            f"checks={checks!r}"
        )
    return {
        "status": "observed_minimal_rhs_only",
        "path": "minimal_surface_rhs_only",
        "observed": {**observed, "matrix_objects": observed_matrix_objects},
        "expected": {**expected, "matrix_objects": {"C": 0, "D": 0, "H": 0}},
        "checks": checks,
        "pass": True,
        "full_C_materialized": False,
        "D_materialized": False,
        "H_materialized": False,
        "physical_dtn_operator_constructed": False,
        "woodbury_inverse_constructed": False,
    }


def _route_c_observed_group_factor_lifecycle(
    factor_ready: Mapping[str, Any],
    factor_after: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the observed three-group PC lifecycle before recording it."""

    ready_count = int(factor_ready.get("factor_count_ready", -1))
    after_count = int(factor_after.get("factor_count_after_cleanup", -1))
    if ready_count != 3 or after_count != 0:
        raise RuntimeError(
            "Route C group-factor lifecycle is not the observed 3-to-0 sequence: "
            f"ready={factor_ready!r}, after={factor_after!r}"
        )
    if factor_after.get("destroyed") is not True:
        raise RuntimeError("Route C group-factor owner was not observed destroyed")
    if factor_after.get("action_destroyed") is not True:
        raise RuntimeError("Route C group-factor action was not observed destroyed")
    return {
        "ready": dict(factor_ready),
        "after": dict(factor_after),
        "construction_count": ready_count,
        "destruction_count": ready_count,
        "simultaneous_factor_count_max": ready_count,
        "pc_setup_count": 1,
        "continuous_source_solve_count": 2,
    }


def _route_c_all_rank_artifact_index(
    *,
    rank_count: int,
    source_records_by_rank: Sequence[Any],
    gamma_layouts_by_rank: Sequence[Any],
    canonical_active_layouts_by_rank: Sequence[Any],
    interface_trace_artifacts_by_rank: Sequence[Any],
    basis_artifacts_by_rank: Sequence[Any],
) -> list[dict[str, Any]]:
    """Build a strict rank-indexed manifest for every Route C artifact family."""

    families = {
        "source_records": source_records_by_rank,
        "gamma_layouts": gamma_layouts_by_rank,
        "canonical_active_layout": canonical_active_layouts_by_rank,
        "interface_trace_artifacts": interface_trace_artifacts_by_rank,
        "basis_artifacts": basis_artifacts_by_rank,
    }
    expected_count = int(rank_count)
    if expected_count <= 0:
        raise ValueError("Route C artifact index needs a positive rank count")
    if any(not isinstance(items, Sequence) for items in families.values()):
        raise ValueError("Route C artifact families must be gathered sequences")
    if any(len(items) != expected_count for items in families.values()):
        raise ValueError(
            "Route C artifact family does not contain one entry per MPI rank"
        )
    return [
        {
            "rank": rank,
            **{
                name: families[name][rank]
                for name in families
            },
        }
        for rank in range(expected_count)
    ]


def _run_v5_route_c(
    *,
    cfg: Any,
    profile: Any,
    comm: MPI.Intracomm,
    exact_spool_root: str | Path,
    run_directory: str | Path,
    source_sha: str,
    input_path: str | Path,
    input_sha256: str,
    physical_model_sha256: str,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None,
    resource_callback: Callable[[], Mapping[str, Any]] | None,
    watchdog_enabled: bool,
    bottom_route_only: bool,
) -> dict[str, Any]:
    """Run the metadata-preflighted, no-full-side-factor Route C screen."""

    formal_started = time.perf_counter()
    output_root = Path(run_directory).resolve()
    frozen_root = Path(exact_spool_root).resolve()
    try:
        output_root.relative_to(frozen_root)
    except ValueError:
        pass
    else:
        raise ValueError("Route C output must not be below the frozen exact spool")
    if not output_root.is_absolute():
        raise ValueError("Route C output root must be absolute after resolution")

    identity_preflight = _v5_authority_identity_preflight(
        comm=comm,
        input_path=input_path,
        input_sha256=str(input_sha256),
        physical_model_sha256=str(physical_model_sha256),
        source_sha=str(source_sha),
        watchdog_enabled=watchdog_enabled,
        bottom_route_only=bottom_route_only,
    )
    audit_file = _v5_write_operator_semantics_audit(
        comm,
        output_root,
        identity_preflight.get("operator_semantics_audit"),
    )
    identity_preflight = {
        **identity_preflight,
        "operator_semantics_audit_file": audit_file,
    }
    if not identity_preflight["pass"]:
        return _route_c_stop_result(
            status="not_run_by_identity_preflight",
            classification="FRESH_BARE_F_AUTHORITY_IDENTITY_FAIL",
            source_sha=source_sha,
            input_sha256=input_sha256,
            physical_model_sha256=physical_model_sha256,
            identity_preflight=identity_preflight,
        )

    resource_preflight = _route_c_resource_preflight(
        comm,
        output_root,
        hard_stop_bytes=TASK040_V5_ROUTE_C_HARD_STOP_BYTES,
    )
    _emit(
        marker_callback,
        "v5_route_c_resource_preflight",
        status=resource_preflight["status"],
        classification=resource_preflight["resource_classification"],
        hard_stop_bytes=resource_preflight["hard_stop_bytes"],
        minimum_mem_available_bytes=resource_preflight[
            "minimum_mem_available_bytes"
        ],
        minimum_disk_free_bytes=resource_preflight["minimum_disk_free_bytes"],
        swap_limit_bytes=resource_preflight["swap_limit_bytes"],
        timeout_seconds=resource_preflight["timeout_seconds"],
        **{"pass": resource_preflight["pass"]},
    )
    if not resource_preflight["pass"]:
        return _route_c_stop_result(
            status="not_run_by_resource_preflight",
            classification=TASK040_V5_ROUTE_C_RESOURCE_BLOCKED,
            source_sha=source_sha,
            input_sha256=input_sha256,
            physical_model_sha256=physical_model_sha256,
            identity_preflight=identity_preflight,
            resource_preflight=resource_preflight,
        )

    if comm.rank == 0:
        output_root.mkdir(parents=True, exist_ok=True)
    comm.barrier()
    rank_root = output_root / f"rank{int(comm.rank):04d}"
    rank_root.mkdir(parents=True, exist_ok=False)
    comm.barrier()

    system = None
    action = None
    owner = None
    masses: list[Any] = []
    rhs_by_label: dict[str, PETSc.Vec] = {}
    source_records: dict[str, dict[str, Any]] = {}
    trace_artifacts: dict[str, list[dict[str, Any]]] = {
        label: [] for label in ROUTE_C_LABELS
    }
    basis_artifacts: list[dict[str, Any]] = []
    cleanup: dict[str, Any] = {}
    try:
        system = assemble_current_bare_f_authority_system(
            cfg,
            side="bottom",
            bottom_interface_z_nm=profile.bottom_interface_nm,
            top_interface_z_nm=profile.top_interface_nm,
            source_work_directory=output_root / "route_c_source",
            selected_mode_provider=None,
            external_mode_authority=identity_preflight["external_mode_authority"],
            external_mode_current_resolved_config_sha256=str(
                identity_preflight["observed"]["resolved_config_sha256"]
            ),
            comm=comm,
        )
        inventory = system.construction_inventory
        matrix_objects = dict(system.dtn_objects_constructed)
        observed_qep_calls = _route_c_observed_qep_calls(inventory)
        if any(int(matrix_objects.get(name, 0)) != 0 for name in ("C", "D", "H")):
            raise RuntimeError("Route C current bare-F assembly constructed C/D/H")
        if any(
            bool(inventory.get(name))
            for name in (
                "physical_dtn_operator_constructed",
                "woodbury_inverse_constructed",
                "research_exact_side_lu_action_called",
            )
        ):
            raise RuntimeError("Route C assembly entered a forbidden side operator path")
        _emit(
            marker_callback,
            "v5_route_c_system_ready",
            side="bottom",
            bare_f_rows=int(system.active_rows),
            factored_operator="explicit_current_bare_F",
            matrix_objects=matrix_objects,
            qep_calls=observed_qep_calls,
            physical_dtn_operator_constructed=False,
            woodbury_inverse_constructed=False,
            research_exact_side_lu_action_called=False,
        )

        tokens, key_set_sha256, layout_audit = canonical_layout_tokens(system)
        layout_record = {
            "schema": "task040.v5.route_c.current_active_layout.v1",
            "rank": int(comm.rank),
            "mpi_size": int(comm.size),
            "global_size": int(system.F.getSize()[0]),
            "local_size": len(tokens),
            "ownership_range": list(map(int, system.F.getOwnershipRange())),
            "canonical_key_set_sha256": str(key_set_sha256),
            "canonical_keys": list(tokens),
            "audit": _route_c_json_safe(layout_audit),
            "raw_global_row_remap": False,
        }
        layout_path = rank_root / "canonical_active_layout.json"
        layout_sha256 = _route_c_atomic_json(layout_path, layout_record)
        layout_ownership_range = list(map(int, system.F.getOwnershipRange()))

        z_values = system.local_mesh.z_values
        gamma_layouts = {
            "lower": build_current_gamma_layout(
                system,
                name="Gamma_L",
                plane_z_nm=float(z_values[2]),
                plane_cell_side="lower",
                frozen_z_index=2,
            ),
            "upper": build_current_gamma_layout(
                system,
                name="Gamma_U",
                plane_z_nm=float(z_values[4]),
                plane_cell_side="upper",
                frozen_z_index=4,
            ),
        }
        gamma_layout_records: dict[str, dict[str, Any]] = {}
        for component, layout in gamma_layouts.items():
            gamma_name = "Gamma_L" if component == "lower" else "Gamma_U"
            gamma_path = rank_root / f"{gamma_name.lower()}_layout.json"
            gamma_payload = {
                "schema": "task040.v5.route_c.gamma_layout.v1",
                "gamma": gamma_name,
                "rank": int(comm.rank),
                "mpi_size": int(comm.size),
                "gamma_rows_local": [int(row) for row in layout.gamma_rows_local],
                "canonical_keys": list(layout.canonical_keys),
                "canonical_key_order_sha256": layout.audit[
                    "canonical_key_order_sha256"
                ],
                "plane_identity": _route_c_json_safe(layout.plane_identity),
                "audit": _route_c_json_safe(layout.audit),
                "canonical_active_layout_sha256": layout_sha256,
                "raw_global_row_remap": False,
            }
            gamma_sha256 = _route_c_atomic_json(gamma_path, gamma_payload)
            gamma_layout_records[component] = {
                "name": gamma_name,
                "path": str(gamma_path.relative_to(output_root)),
                "sha256": gamma_sha256,
                "canonical_key_order_sha256": str(
                    layout.audit["canonical_key_order_sha256"]
                ),
                "local_row_count": len(layout.gamma_rows_local),
                "plane_z_nm": float(z_values[2 if component == "lower" else 4]),
            }
        _emit(
            marker_callback,
            "v5_route_c_interface_projection_ready",
            gamma_layouts=gamma_layout_records,
            canonical_active_layout_sha256=layout_sha256,
            replicated=False,
        )

        supports = []
        for interface in (float(z_values[2]), float(z_values[4])):
            supports.append(
                audit_artificial_z_interface_support(
                    system.V,
                    system.static_condensation.condensed,
                    interface,
                )
            )
            masses.append(
                assemble_reduced_artificial_interface_tangential_mass(
                    system.V,
                    system.static_condensation.condensed,
                    supports[-1],
                    bare_operator=system.F,
                )
            )
        group_rows, group_audit = build_level_a_cell_recovery_group_rows(
            system, system.F, supports
        )
        beta = level_a_bottom_beta(cfg)
        action, owner, oracle_diagnostics = build_level_a_oracle(
            bare_f=system.F,
            group_rows=group_rows,
            interface_masses=masses,
            beta=beta,
            group_audit=group_audit,
        )
        _emit(
            marker_callback,
            "v5_route_c_pc_ready",
            factor_lifecycle=owner.diagnostics,
            bare_f_operator_hash=_petsc_matrix_hash(system.F),
            qep_calls=0,
            full_side_exact_factor_count=0,
        )
        if owner.diagnostics.get("factor_count_ready") != 3:
            raise RuntimeError("Route C did not observe three diagnostic group factors")

        bare_f_operator_hash = _petsc_matrix_hash(system.F)
        source_provenance = {
            key: identity_preflight["observed"].get(key)
            for key in (
                "input_sha256",
                "physical_model_sha256",
                "selected_manifest_sha256",
                "selected_identity_sha256",
                "resolved_config_sha256",
                "probe_manifest_sha256",
                "source_sha",
            )
        }
        rhs_id_to_label: dict[int, str] = {}
        for label in ROUTE_C_LABELS:
            first_rhs, first_metadata = build_current_bare_f_rhs(system, label)
            rhs_by_label[label] = first_rhs
            rhs_id_to_label[id(first_rhs)] = label
            first_local_sha = _route_c_local_vec_sha256(first_rhs)
            first_global_sha = _route_c_global_digest(comm, first_local_sha)
            rhs_path = rank_root / "rhs" / f"{label}.npy"
            rhs_array = np.asarray(first_rhs.getArray(readonly=True), dtype=np.complex128)
            rhs_file_sha = _route_c_atomic_npy(rhs_path, rhs_array)
            repeat_rhs = None
            try:
                repeat_rhs, repeat_metadata = build_current_bare_f_rhs(system, label)
                difference = repeat_rhs.copy()
                try:
                    difference.axpy(PETSc.ScalarType(-1.0), first_rhs)
                    relative = float(difference.norm()) / max(
                        float(first_rhs.norm()), 1.0e-30
                    )
                finally:
                    difference.destroy()
                repeat_local_sha = _route_c_local_vec_sha256(repeat_rhs)
                repeat_global_sha = _route_c_global_digest(comm, repeat_local_sha)
                source_definition_sha256 = _route_c_source_definition_sha256(
                    label, first_metadata
                )
                repeat_source_definition_sha256 = _route_c_source_definition_sha256(
                    label, repeat_metadata
                )
                source_error = None
                if (
                    not np.isfinite(relative)
                    or relative > 1.0e-12
                    or source_definition_sha256 != repeat_source_definition_sha256
                ):
                    source_error = RuntimeError(
                        f"Route C RHS repeat identity failed for {label}"
                    )
                _route_c_collective_stage_error(comm, f"rhs_repeat:{label}", source_error)
            finally:
                if repeat_rhs is not None:
                    repeat_rhs.destroy()
            source_definition_sha256 = _route_c_source_definition_sha256(
                label, first_metadata
            )
            source_hashes = comm.allgather(source_definition_sha256)
            if len(set(source_hashes)) != 1:
                raise RuntimeError(f"Route C source definition differs by rank: {label}")
            source_records[label] = {
                "label": label,
                "source_definition_sha256": source_definition_sha256,
                "source_metadata": _route_c_json_safe(dict(first_metadata)),
                "source_provenance": source_provenance,
                "rhs": {
                    "path": str(rhs_path.relative_to(output_root)),
                    "file_sha256": rhs_file_sha,
                    "local_array_sha256": first_local_sha,
                    "global_array_sha256": first_global_sha,
                    "dtype": "complex128",
                    "global_size": int(first_rhs.getSize()),
                    "ownership_range": list(map(int, first_rhs.getOwnershipRange())),
                },
                "rhs_repeat": {
                    "relative_difference": float(relative),
                    "threshold": 1.0e-12,
                    "pass": True,
                    "local_array_sha256": repeat_local_sha,
                    "global_array_sha256": repeat_global_sha,
                    "source_definition_sha256": repeat_source_definition_sha256,
                },
                "bare_f_operator_hash": bare_f_operator_hash,
                "canonical_key_set_sha256": str(key_set_sha256),
                "canonical_active_layout_sha256": layout_sha256,
                "raw_global_row_remap": False,
            }
        external_dtn_contract = _route_c_observed_external_contract(
            inventory,
            system.dtn_objects_constructed,
        )
        _emit(
            marker_callback,
            "v5_route_c_source_ready",
            labels=list(ROUTE_C_LABELS),
            rhs_vectors_loaded=len(rhs_by_label),
            exact_output_vectors_loaded=0,
            external_dtn_coupling=external_dtn_contract,
        )

        trace_layouts = gamma_layouts

        def write_gamma_shard(
            vector: PETSc.Vec,
            component: str,
            path: Path,
            *,
            direction_space: str,
            shard: Mapping[str, Any] | None = None,
        ) -> dict[str, Any]:
            layout = trace_layouts[component]
            if shard is None:
                shard = compact_gamma_values_for_vector(vector, layout)
            values = np.asarray(shard["values"], dtype=np.complex128)
            return {
                "path": str(path.relative_to(output_root)),
                "sha256": _route_c_atomic_npy(path, values),
                "direction_space": direction_space,
                "local_size": int(len(values)),
                "canonical_active_layout_sha256": layout_sha256,
                "gamma_layout_path": gamma_layout_records[component]["path"],
                "gamma_layout_sha256": gamma_layout_records[component]["sha256"],
                "canonical_key_order_sha256": gamma_layout_records[component][
                    "canonical_key_order_sha256"
                ],
                "owner_local": True,
                "replicated": False,
            }

        def interface_residual(
            residual: PETSc.Vec,
            rhs: PETSc.Vec,
            iteration: int,
        ) -> Mapping[str, Any]:
            label = rhs_id_to_label.get(id(rhs), "unknown")
            if label not in source_records:
                raise ValueError("Route C residual callback received unknown RHS")
            artifacts: dict[str, Any] = {}
            local_norm_sq: dict[str, float] = {}
            for component in ("lower", "upper"):
                trace_path = (
                    rank_root
                    / "interface_traces"
                    / label
                    / f"iteration{int(iteration):04d}_{component}.npy"
                )
                shard = compact_gamma_values_for_vector(
                    residual, trace_layouts[component]
                )
                values = np.asarray(shard["values"], dtype=np.complex128)
                local_norm_sq[component] = float(np.vdot(values, values).real)
                artifact = write_gamma_shard(
                    residual,
                    component,
                    trace_path,
                    direction_space="residual_solution_interface_trace",
                    shard=shard,
                )
                artifact.update(
                    {
                        "norm": float(
                            np.sqrt(
                                max(
                                    comm.allreduce(
                                        local_norm_sq[component], op=MPI.SUM
                                    ),
                                    0.0,
                                )
                            )
                        ),
                        "source_definition_sha256": source_records[label][
                            "source_definition_sha256"
                        ],
                        "bare_f_operator_hash": bare_f_operator_hash,
                        "canonical_key_set_sha256": str(key_set_sha256),
                        "source_provenance": source_provenance,
                    }
                )
                artifacts[component] = artifact
            joint_norm = float(
                np.sqrt(
                    max(
                        comm.allreduce(
                            local_norm_sq["lower"] + local_norm_sq["upper"],
                            op=MPI.SUM,
                        ),
                        0.0,
                    )
                )
            )
            artifacts["joint"] = {
                "kind": "derived_scalar_only",
                "norm": joint_norm,
                "derived_from": ["lower", "upper"],
                "stored": False,
                "source_definition_sha256": source_records[label][
                    "source_definition_sha256"
                ],
                "bare_f_operator_hash": bare_f_operator_hash,
                "canonical_key_set_sha256": str(key_set_sha256),
            }
            trace_artifacts[label].append(
                {"iteration": int(iteration), "components": artifacts}
            )
            return {
                "lower": artifacts["lower"]["norm"],
                "upper": artifacts["upper"]["norm"],
                "joint": artifacts["joint"]["norm"],
                "iteration": int(iteration),
                "source": "current_gamma_canonical_trace",
                "joint_derived_from": ["lower", "upper"],
            }

        def interface_direction(
            label: str,
            restart: int,
            direction_index: int,
            residual_direction: PETSc.Vec,
            response_direction: PETSc.Vec,
            _metadata: Mapping[str, Any],
        ) -> Mapping[str, Any]:
            response_shards: dict[str, dict[str, Any]] = {}
            response_trace: dict[str, dict[str, Any]] = {}
            residual_trace: dict[str, dict[str, Any]] = {}
            for component in ("lower", "upper"):
                response_path = (
                    rank_root
                    / "interface_direction_traces"
                    / label
                    / f"restart{int(restart):04d}_direction{int(direction_index):02d}"
                    f"_response_{component}.npy"
                )
                residual_path = response_path.with_name(
                    response_path.name.replace("_response_", "_residual_")
                )
                response_shard = compact_gamma_values_for_vector(
                    response_direction, trace_layouts[component]
                )
                residual_shard = compact_gamma_values_for_vector(
                    residual_direction, trace_layouts[component]
                )
                response_trace[component] = write_gamma_shard(
                    response_direction,
                    component,
                    response_path,
                    direction_space="preconditioned_response_direction_Z_y",
                    shard=response_shard,
                )
                residual_trace[component] = write_gamma_shard(
                    residual_direction,
                    component,
                    residual_path,
                    direction_space="residual_space_V_y",
                    shard=residual_shard,
                )
                response_shards[component] = {
                    "values": np.asarray(
                        response_shard["values"], dtype=np.complex128
                    ).copy(),
                    "canonical_positions": np.asarray(
                        response_shard["canonical_positions"], dtype=np.int64
                    ).copy(),
                    "canonical_key_order_sha256": gamma_layout_records[component][
                        "canonical_key_order_sha256"
                    ],
                }

            return {
                "lower": response_shards["lower"],
                "upper": response_shards["upper"],
                "audit": {
                    "status": "pass",
                    "projection_kind": "compact_owner_local_canonical_gamma_trace",
                    "source_direction": "preconditioned_response_direction_Z_y",
                    "replicated": False,
                    "canonical_active_layout_sha256": layout_sha256,
                    "gamma_layout_sha256": {
                        component: gamma_layout_records[component]["sha256"]
                        for component in ("lower", "upper")
                    },
                    "canonical_interface_trace": response_trace,
                    "residual_interface_trace": residual_trace,
                    "joint_derived": {
                        "source_components": ["lower", "upper"],
                        "storage": "scalar_inner_product_and_norm_only",
                    },
                    "source_definition_sha256": source_records[label][
                        "source_definition_sha256"
                    ],
                    "bare_f_operator_hash": bare_f_operator_hash,
                    "canonical_key_set_sha256": str(key_set_sha256),
                    "source_provenance": source_provenance,
                },
            }

        def persist_basis(
            label: str,
            restart: int,
            direction_index: int,
            residual_direction: PETSc.Vec,
            response_direction: PETSc.Vec,
            _metadata: Mapping[str, Any],
        ) -> Mapping[str, Any]:
            base = (
                rank_root
                / "route_c_basis"
                / label
                / f"restart{int(restart):04d}_direction{int(direction_index):02d}"
            )
            residual_path = base.with_name(base.name + "_residual.npy")
            response_path = base.with_name(base.name + "_response.npy")
            residual_sha = _route_c_atomic_npy(
                residual_path,
                np.asarray(
                    residual_direction.getArray(readonly=True), dtype=np.complex128
                ),
            )
            response_sha = _route_c_atomic_npy(
                response_path,
                np.asarray(
                    response_direction.getArray(readonly=True), dtype=np.complex128
                ),
            )
            projection_audit = dict(
                dict(_metadata["interface_direction_projection"])["audit"]
            )
            start, end = map(int, residual_direction.getOwnershipRange())
            record = {
                "status": "pass",
                "label": label,
                "restart": int(restart),
                "direction_index": int(direction_index),
                "owner_local": True,
                "replicated": False,
                "source_definition_sha256": source_records[label][
                    "source_definition_sha256"
                ],
                "bare_f_operator_hash": bare_f_operator_hash,
                "canonical_key_set_sha256": str(key_set_sha256),
                "canonical_active_layout_sha256": layout_sha256,
                "source_provenance": source_provenance,
                "direction_mapping": dict(_metadata["direction_mapping"]),
                "canonical_interface_trace": {
                    "direction_space": "preconditioned_response_direction_Z_y",
                    "components": projection_audit["canonical_interface_trace"],
                },
                "residual_interface_trace": {
                    "direction_space": "residual_space_V_y",
                    "components": projection_audit["residual_interface_trace"],
                },
                "residual_direction": {
                    "kind": "residual_space_V_y",
                    "path": str(residual_path.relative_to(output_root)),
                    "sha256": residual_sha,
                    "local_size": int(end - start),
                    "ownership_range": [start, end],
                },
                "preconditioned_response_direction": {
                    "kind": "response_space_Z_y",
                    "path": str(response_path.relative_to(output_root)),
                    "sha256": response_sha,
                    "local_size": int(response_direction.getLocalSize()),
                    "ownership_range": list(
                        map(int, response_direction.getOwnershipRange())
                    ),
                },
            }
            basis_artifacts.append(record)
            return record

        krylov_started = time.perf_counter()
        route_resource_observation_count = 0
        last_krylov_observation: float | None = None

        def route_resource_callback() -> Mapping[str, Any]:
            nonlocal route_resource_observation_count, last_krylov_observation
            if resource_callback is None:
                return {
                    "status": "not_provided",
                    "pass": False,
                    "rss_bytes": None,
                    "swap_bytes": None,
                    "wall_controlled": False,
                    "wall_observation": {
                        "budget_seconds": float(TASK040_LEVEL_A_TIMEOUT_SECONDS),
                        "elapsed_seconds": None,
                        "remaining_seconds": None,
                        "krylov_elapsed_seconds": None,
                        "predicted_remaining_seconds": None,
                        "predicted_total_seconds": None,
                        "pass": False,
                    },
                }
            observed = dict(resource_callback())
            now = time.perf_counter()
            formal_elapsed = float(now - formal_started)
            krylov_elapsed = float(now - krylov_started)
            source_index = int(route_resource_observation_count)
            wall_observation = _route_c_wall_observation(
                formal_elapsed_seconds=formal_elapsed,
                krylov_elapsed_seconds=krylov_elapsed,
                last_krylov_elapsed_seconds=last_krylov_observation,
                observation_index=source_index,
            )
            wall_observation.update(
                {
                    "source_label_at_128": ROUTE_C_LABELS[
                        min(source_index, len(ROUTE_C_LABELS) - 1)
                    ],
                    "source_observation_index": source_index,
                    "setup_to_128_elapsed_seconds": krylov_elapsed,
                }
            )
            observed["wall_observation"] = wall_observation
            observed["wall_controlled"] = bool(wall_observation["pass"])
            last_krylov_observation = krylov_elapsed
            route_resource_observation_count += 1
            return observed

        route_result = run_route_c_online_fgmres(
            system.F,
            rhs_by_label,
            right_preconditioner=action,
            resource_callback=route_resource_callback,
            interface_residual_callback=interface_residual,
            interface_direction_callback=interface_direction,
            checkpoint_callback=lambda row: _emit(
                marker_callback,
                "v5_route_c_checkpoint",
                **dict(row),
            ),
            basis_callback=persist_basis,
        )
        route_gate = route_result["direction_audit_gate"]
        if not route_gate["pass"]:
            raise RuntimeError("Route C interface/basis persistence audit did not pass")

        factor_ready = owner.diagnostics
        owner.destroy()
        factor_after = owner.diagnostics
        owner = None
        action = None
        _emit(
            marker_callback,
            "v5_route_c_pc_destroyed",
            factor_ready=factor_ready,
            factor_after=factor_after,
            no_overlap=True,
        )
        cleanup["group_factor_lifecycle"] = _route_c_observed_group_factor_lifecycle(
            factor_ready,
            factor_after,
        )
        cleanup["rhs_vectors_destroyed"] = len(rhs_by_label)
        for vector in rhs_by_label.values():
            vector.destroy()
        rhs_by_label.clear()
        for mass in masses:
            mass.destroy()
        masses.clear()
        system.destroy()
        system = None
        cleanup["collective_heap"] = collective_heap_cleanup(comm)
        cleanup["basis_artifact_count_local"] = len(basis_artifacts)
        _emit(marker_callback, "v5_route_c_cleanup", **cleanup)
        basis_by_rank = comm.gather(basis_artifacts, root=0)
        source_by_rank = comm.gather(source_records, root=0)
        trace_by_rank = comm.gather(trace_artifacts, root=0)
        gamma_layouts_by_rank = comm.gather(gamma_layout_records, root=0)
        active_layout_by_rank = comm.gather(
            {
                "path": str(layout_path.relative_to(output_root)),
                "sha256": layout_sha256,
                "canonical_key_set_sha256": str(key_set_sha256),
                "local_key_count": len(tokens),
                "ownership_range": layout_ownership_range,
            },
            root=0,
        )
        artifact_index_by_rank = (
            _route_c_all_rank_artifact_index(
                rank_count=comm.size,
                source_records_by_rank=source_by_rank,
                gamma_layouts_by_rank=gamma_layouts_by_rank,
                canonical_active_layouts_by_rank=active_layout_by_rank,
                interface_trace_artifacts_by_rank=trace_by_rank,
                basis_artifacts_by_rank=basis_by_rank,
            )
            if comm.rank == 0
            else None
        )
        result = {
            "schema": TASK040_V5_ROUTE_C_SCHEMA,
            "method": TASK040_V5_ROUTE_C_METHOD,
            "profile": TASK040_V5_ROUTE_C_PROFILE_ID,
            "status": "completed_route_c_screen",
            "classification": route_result["signal"]["classification"],
            "source_sha": str(source_sha),
            "input_sha256": str(input_sha256),
            "physical_model_sha256": str(physical_model_sha256),
            "identity_preflight": identity_preflight,
            "resource_preflight": resource_preflight,
            "operator_semantics_audit": identity_preflight.get(
                "operator_semantics_audit_file"
            ),
            "system_created": True,
            "system_inventory": _route_c_json_safe(inventory),
            "source_records_by_rank": source_by_rank if comm.rank == 0 else None,
            "rhs_vectors_loaded": len(ROUTE_C_LABELS),
            "exact_output_vectors_loaded": 0,
            "exact_output_vectors_consumed": 0,
            "full_side_exact_factor_count": 0,
            "qep_calls": observed_qep_calls,
            "pde_solve": "not_run",
            "outer_ksp": "not_run",
            "factored_operator": "explicit_current_bare_F",
            "bare_f_operator_hash": bare_f_operator_hash,
            "external_dtn_coupling": _route_c_json_safe(external_dtn_contract),
            "gamma_layouts_by_rank": (
                gamma_layouts_by_rank if comm.rank == 0 else None
            ),
            "canonical_active_layouts_by_rank": (
                active_layout_by_rank if comm.rank == 0 else None
            ),
            "group_pc": {
                "oracle_diagnostics": _route_c_json_safe(oracle_diagnostics),
                "factor_lifecycle": cleanup["group_factor_lifecycle"],
            },
            "interface_trace_artifacts_by_rank": (
                trace_by_rank if comm.rank == 0 else None
            ),
            "basis_artifacts_by_rank": basis_by_rank if comm.rank == 0 else None,
            "artifact_index_by_rank": artifact_index_by_rank,
            "route_c": route_result,
            "cleanup": cleanup,
            "downstream": {
                "level_b": "not_run_by_route_c_screen",
                "full_hybrid": "not_run_by_route_c_screen",
                "h3": "not_run_by_route_c_screen",
            },
            "research_only": True,
        }
        if comm.rank == 0:
            _route_c_atomic_json(output_root / "route_c_manifest.json", result)
        comm.barrier()
        return _route_c_json_safe(result)
    finally:
        if owner is not None:
            owner.destroy()
            owner = None
            action = None
        elif action is not None:
            action.destroy()
            action = None
        for vector in rhs_by_label.values():
            vector.destroy()
        for mass in masses:
            mass.destroy()
        if system is not None:
            system.destroy()


def _v1_2_complex(value: Any) -> complex:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return complex(float(value[0]), float(value[1]))
    return complex(value)


def _v1_2_mode_key(mode: Any) -> dict[str, Any]:
    return {
        "m": int(mode.m),
        "n": int(mode.n),
        "polarization": str(mode.polarization),
        "side": str(mode.side),
    }


def _v1_2_load_manifest() -> tuple[Path, dict[str, Any]]:
    root = Path(__file__).resolve().parents[1]
    path = root / TASK040_V1_2_PROBE_MANIFEST
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != TASK040_V1_2_PROBE_MANIFEST_SHA256:
        raise ValueError("Task040 V1-2 probe manifest hash mismatch")
    return path, json.loads(payload)


def _v5_selected_mode_provider(
    comm: MPI.Intracomm,
) -> Callable[[str, int], Mapping[str, Any]]:
    """Return the runner-owned, hash-bound one-column selected-mode reader."""

    _probe_path, probe_manifest = _v1_2_load_manifest()
    identity = probe_manifest["identity"]
    root = Path(__file__).resolve().parents[1]
    manifest_path = root / identity["selected_manifest"]
    selected_identity = json.loads(
        manifest_path.with_name("identity.json").read_text(encoding="utf-8")
    )
    selected_manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if selected_manifest_sha256 != TASK040_V1_2_SELECTED_MANIFEST_SHA256:
        raise ValueError("V5 selected-mode manifest hash is not frozen")

    def provide(branch: str, index: int) -> Mapping[str, Any]:
        captured: dict[str, Any] = {}

        def capture(
            returned_index: int,
            right_local: np.ndarray,
            left_local: np.ndarray,
            packet_info: Mapping[str, Any],
        ) -> None:
            if int(returned_index) != int(index):
                raise RuntimeError("selected-mode provider returned the wrong index")
            captured.update(
                {
                    "right_local": np.asarray(right_local, dtype=np.complex128).copy(),
                    "left_local": np.asarray(left_local, dtype=np.complex128).copy(),
                    **dict(packet_info),
                }
            )

        stream_task039_v4_selected_mode_columns(
            manifest_path,
            identity=selected_identity,
            expected_manifest_sha256=selected_manifest_sha256,
            branch=str(branch),
            indices=(int(index),),
            callback=capture,
            comm=comm,
        )
        if not captured:
            raise RuntimeError("selected-mode provider captured no packet column")
        captured.update(
            {
                "manifest_path": str(manifest_path),
                "manifest_sha256": selected_manifest_sha256,
                "identity_sha256": str(
                    hashlib.sha256(
                        json.dumps(
                            selected_identity,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ).hexdigest()
                ),
            }
        )
        return captured

    return provide


def _v1_2_lower_mode_count(resolved_modes: Mapping[str, Any]) -> int:
    """Read the resolved inventory's per-side bottom mode count."""

    return int(resolved_modes["counts"]["per_side"]["bottom"])


def _v1_2_validate_spool_identity(
    *, selected_manifest_sha256: str, catalog: Mapping[str, Any]
) -> str:
    """Validate selected-spool manifest and catalog identities separately."""

    if selected_manifest_sha256 != TASK040_V1_2_SELECTED_MANIFEST_SHA256:
        raise ValueError("V1-2 selected spool manifest is not frozen")
    catalog_sha256 = str(catalog["catalog_sha256"])
    if catalog_sha256 != TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256:
        raise ValueError("V1-2 exact spool catalog is not frozen")
    return catalog_sha256


def _v1_2_local_interface_rows(
    condensed: Any,
    support: Mapping[str, Any],
    gamma_rows_local: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    constraints = condensed.trace_constraints
    owned_original = {int(value) for value in constraints.owned_active_original_dofs}
    original_to_active = {
        int(key): int(value) for key, value in constraints.original_to_active.items()
    }
    by_active: dict[int, int] = {}
    for original in support["raw_support"]:
        original = int(original)
        if original in owned_original:
            if original not in original_to_active:
                raise ValueError("V1-2 artificial support lacks active identity")
            active = original_to_active[original]
            if active in by_active:
                raise ValueError("V1-2 local support has duplicate active rows")
            by_active[active] = original
    gamma = np.asarray(gamma_rows_local, dtype=PETSc.IntType)
    if set(by_active) != {int(value) for value in gamma}:
        raise ValueError("V1-2 local raw/active support does not match Gamma rows")
    plane_original = np.asarray(
        [by_active[int(value)] for value in gamma], dtype=PETSc.IntType
    )
    return plane_original, gamma.copy()


def _v1_2_build_lower_basis(
    *,
    cfg: Any,
    system: Any,
    spaces: Any,
    condensed: Any,
    support: Mapping[str, Any],
    gamma_rows_local: np.ndarray,
    interface_z: float,
    authority: Mapping[str, Any],
) -> dict[str, Any]:
    modes = [mode for mode in outgoing_port_modes_3d(cfg) if mode.side == "bottom"]
    expected_keys = tuple(authority["keys"])
    expected_metadata = tuple(authority["modes"])
    if len(modes) != int(authority["count"]):
        raise ValueError("V1-2 lower mode count differs from resolved authority")
    mode_by_token = {
        json.dumps(_v1_2_mode_key(mode), sort_keys=True, separators=(",", ":")): mode
        for mode in modes
    }
    if len(mode_by_token) != len(modes):
        raise ValueError("V1-2 lower mode keys are duplicated")
    plane_original, gamma = _v1_2_local_interface_rows(
        condensed, support, gamma_rows_local
    )
    lifter = _ReusableInterfaceLifter(
        system,
        target_space=system.V,
        interface_z_nm=interface_z,
        plane_cell_side="lower",
    )
    xy = np.asarray(spaces.transverse.mesh.geometry.x, dtype=np.float64)[:, :2]

    def trace_to_gamma(_values: np.ndarray, info: Mapping[str, Any]) -> np.ndarray:
        token = json.dumps(
            {
                "m": int(info["m"]),
                "n": int(info["n"]),
                "polarization": str(info["polarization"]),
                "side": str(info["side"]),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        mode = mode_by_token.get(token)
        if mode is None:
            raise ValueError("V1-2 lower Fourier mode is absent from authority")
        trace = fem.Function(spaces.transverse)
        e_vector = np.asarray(mode.e_vector[:2], dtype=np.complex128)
        alpha = complex(mode.alpha)
        transverse_beta = complex(mode.k_vector[2])

        def values(points: np.ndarray) -> np.ndarray:
            phase = np.exp(
                1j
                * (
                    alpha * points[0]
                    + complex(mode.gamma) * points[1]
                    + transverse_beta * interface_z
                )
            )
            return np.vstack((phase * e_vector[0], phase * e_vector[1]))

        try:
            trace.interpolate(values)
            trace.x.scatter_forward()
            return build_artificial_gamma_column(
                trace,
                system=system,
                condensed=condensed,
                interface_z_nm=interface_z,
                plane_cell_side="lower",
                plane_original_dofs=plane_original,
                gamma_rows_local=gamma,
                lifter=lifter,
            )
        finally:
            del trace

    result = build_lower_fourier_trace_columns(
        modes,
        xy,
        interface_z,
        expected_count=int(authority["count"]),
        expected_keys=expected_keys,
        expected_key_sha256=str(authority["canonical_key_list_sha256"]),
        expected_metadata=expected_metadata,
        expected_metadata_sha256=canonical_external_mode_metadata_sha256(
            expected_metadata
        ),
        frozen_manifest_beta_metadata_sha256=str(authority["beta_metadata_sha256"]),
        trace_to_gamma=trace_to_gamma,
    )
    result["left"] = np.asarray(result["values"], dtype=np.complex128).copy()
    result["resolved_mode_metadata_sha256"] = canonical_external_mode_metadata_sha256(
        expected_metadata
    )
    result["legacy_manifest_beta_metadata_sha256"] = str(
        authority["beta_metadata_sha256"]
    )
    return result


def _v1_2_build_upper_basis(
    *,
    system: Any,
    spaces: Any,
    condensed: Any,
    support: Mapping[str, Any],
    gamma_rows_local: np.ndarray,
    interface_z: float,
    selected_manifest: Path,
    selected_identity: Mapping[str, Any],
    selected_payload: Mapping[str, Any],
    expected_mode_key_sha256: str,
    expected_beta_sha256: str,
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    selection = selected_payload["selection"]["positive"]
    expected_keys = tuple(selection["mode_keys"])
    expected_betas = tuple(_v1_2_complex(value) for value in selection["beta"])
    plane_original, gamma = _v1_2_local_interface_rows(
        condensed, support, gamma_rows_local
    )
    lifter = _ReusableInterfaceLifter(
        system,
        target_space=system.V,
        interface_z_nm=interface_z,
        plane_cell_side="upper",
    )

    def trace_from_values(
        values: np.ndarray, info: Mapping[str, Any], role: str
    ) -> np.ndarray:
        trace = _trace_from_streamed_local_values(
            values,
            spaces,
            info["ownership_range"],
            name=f"task040_v1_2_upper_{role}",
        )
        try:
            return build_artificial_gamma_column(
                trace,
                system=system,
                condensed=condensed,
                interface_z_nm=interface_z,
                plane_cell_side="upper",
                plane_original_dofs=plane_original,
                gamma_rows_local=gamma,
                lifter=lifter,
            )
        finally:
            del trace

    def stream(callback: Callable[..., None]) -> Mapping[str, Any]:
        return stream_task039_v4_selected_mode_columns(
            selected_manifest,
            identity=selected_identity,
            expected_manifest_sha256=TASK040_V1_2_SELECTED_MANIFEST_SHA256,
            branch="positive",
            indices=tuple(range(int(selected_payload["mode_count"]))),
            callback=callback,
            comm=comm,
        )

    result = collect_streamed_trace_basis(
        stream,
        indices=tuple(range(int(selected_payload["mode_count"]))),
        trace_from_values=trace_from_values,
        expected_mode_keys=expected_keys,
        expected_mode_key_sha256=str(expected_mode_key_sha256),
        expected_betas=expected_betas,
        expected_selected_packet_beta_sha256=str(expected_beta_sha256),
    )
    return result


def _v1_2_scalar_gamma_apply(
    *,
    condensed: Any,
    group: int,
    gamma_rows: np.ndarray,
    masses: Sequence[Any],
    beta: complex,
) -> Callable[[PETSc.Vec, PETSc.Vec], None]:
    mass_indices = (0,) if int(group) == 0 else (1,) if int(group) == 2 else (0, 1)
    q = -1j * complex(beta)

    def apply(source: PETSc.Vec, target: PETSc.Vec) -> None:
        active = condensed.create_active_vector()
        image = active.duplicate()
        try:
            first, last = map(int, active.getOwnershipRange())
            rows = np.asarray(gamma_rows, dtype=np.int64)
            if len(rows) and (int(rows.min()) < first or int(rows.max()) >= last):
                raise ValueError("V1-2 Gamma rows do not match active ownership")
            active.set(0.0)
            if len(rows):
                active.array[rows - first] = source.array
            active.assemble()
            target.set(0.0)
            for index in mass_indices:
                image.set(0.0)
                masses[index].matrix.mult(active, image)
                if len(rows):
                    target.array[:] += q * image.array[rows - first]
            target.assemble()
        finally:
            image.destroy()
            active.destroy()

    return apply


def _v1_2_restrict_exact_probes(
    *,
    spool: Mapping[str, Any],
    labels: Sequence[str],
    expected_identities: Mapping[str, str],
    template_matrix: PETSc.Mat,
    lower_rows: np.ndarray,
    upper_rows: np.ndarray,
) -> tuple[dict[str, dict[str, np.ndarray]], dict[str, str]]:
    result: dict[str, dict[str, np.ndarray]] = {}
    observed_output_ids: dict[str, str] = {}
    for label in labels:
        shards = spool[label]["exact_output"]["shards"]
        observed_identities = []
        for shard in shards:
            identity = shard.get("source_identity", {}).get("vector_identity", {})
            observed = identity.get("global_sha256")
            if not isinstance(observed, str):
                raise ValueError(
                    f"V1-2 exact-output vector identity is missing for {label}"
                )
            observed_identities.append(observed)
        if (
            not observed_identities
            or len(set(observed_identities)) != 1
            or observed_identities[0] != expected_identities[label]
        ):
            raise ValueError(
                f"V1-2 exact-output identity mismatch across ranks for {label}"
            )
        observed_output_ids[label] = observed_identities[0]
        template = template_matrix.createVecLeft()
        vector = None
        try:
            vector = _load_v5_blr_reference_spool_remapped(
                spool[label]["exact_output"], template
            )
            first, last = map(int, vector.getOwnershipRange())
            for rows in (lower_rows, upper_rows):
                if len(rows) and (int(rows.min()) < first or int(rows.max()) >= last):
                    raise ValueError("V1-2 exact-output rows are not locally owned")
            result[label] = {
                "lower": np.asarray(
                    vector.array[lower_rows - first], dtype=np.complex128
                ).copy(),
                "upper": np.asarray(
                    vector.array[upper_rows - first], dtype=np.complex128
                ).copy(),
            }
        finally:
            template.destroy()
            if vector is not None:
                vector.destroy()
    return result, observed_output_ids


def _v1_2_group_probe_values(
    group_rows: np.ndarray,
    lower_rows: np.ndarray,
    lower_values: np.ndarray,
    upper_rows: np.ndarray,
    upper_values: np.ndarray,
) -> np.ndarray:
    lower_map = {int(row): value for row, value in zip(lower_rows, lower_values)}
    upper_map = {int(row): value for row, value in zip(upper_rows, upper_values)}
    values = np.empty(len(group_rows), dtype=np.complex128)
    for index, row in enumerate(group_rows):
        if int(row) in lower_map:
            values[index] = lower_map[int(row)]
        elif int(row) in upper_map:
            values[index] = upper_map[int(row)]
        else:
            raise ValueError("V1-2 group Gamma row is not in either interface")
    return values


def _v1_2_relative_error(left: PETSc.Vec, right: PETSc.Vec) -> float:
    difference = left.duplicate()
    try:
        left.copy(difference)
        difference.axpy(PETSc.ScalarType(-1.0), right)
        return float(difference.norm()) / max(float(right.norm()), 1.0e-30)
    finally:
        difference.destroy()


def _v1_2_probe_actions(
    *,
    labels: Sequence[str],
    traces: Mapping[str, Mapping[str, np.ndarray]],
    oracle: Any,
    petrov_actions: Sequence[Any],
    scalar_apply: Sequence[Callable[[PETSc.Vec, PETSc.Vec], None]],
    gamma_rows: Sequence[np.ndarray],
) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for label in labels:
        for group in range(3):
            source = oracle.create_group_gamma_vector(group)
            scalar_target = source.duplicate()
            exact_target = source.duplicate()
            projected_target = source.duplicate()
            try:
                values = _v1_2_group_probe_values(
                    gamma_rows[group],
                    gamma_rows[0],
                    traces[label]["lower"],
                    gamma_rows[2],
                    traces[label]["upper"],
                )
                source.array[:] = values
                source.assemble()
                scalar_apply[group](source, scalar_target)
                oracle.apply_directed_neighbor(group, source, exact_target)
                petrov_actions[group].apply(source, projected_target)
                reports.append(
                    {
                        "label": label,
                        "kind": "physical",
                        "group": group,
                        "scalar_exact_relative": _v1_2_relative_error(
                            scalar_target, exact_target
                        ),
                        "projected_exact_relative": _v1_2_relative_error(
                            projected_target, exact_target
                        ),
                        "scalar_norm": float(scalar_target.norm()),
                        "exact_norm": float(exact_target.norm()),
                        "projected_norm": float(projected_target.norm()),
                        "contractions": _v1_2_vec_contractions(
                            source, scalar_target, exact_target, projected_target
                        ),
                    }
                )
            finally:
                projected_target.destroy()
                exact_target.destroy()
                scalar_target.destroy()
                source.destroy()
    return reports


def _v1_2_complex_pairs(values: np.ndarray) -> list[list[float]]:
    return [
        [float(complex(value).real), float(complex(value).imag)]
        for value in np.asarray(values, dtype=np.complex128).reshape(-1)
    ]


def _v1_2_scalar_pair(value: Any) -> list[float]:
    value = complex(value)
    return [float(value.real), float(value.imag)]


def _v1_2_matrix_pairs(value: np.ndarray) -> list[list[list[float]]]:
    matrix = np.asarray(value, dtype=np.complex128)
    if matrix.ndim != 2:
        raise ValueError("V1-2 contraction must be a matrix")
    return [[_v1_2_scalar_pair(item) for item in row] for row in matrix]


def _v1_2_json_finite(value: Any) -> bool:
    try:
        return bool(np.isfinite(np.asarray(value, dtype=np.float64)).all())
    except (TypeError, ValueError):
        return False


def _v1_2_vec_contractions(
    source: PETSc.Vec,
    scalar: PETSc.Vec,
    exact: PETSc.Vec,
    projected: PETSc.Vec,
) -> dict[str, list[float]]:
    """Record only distributed Vec dot products, never FE-sized values."""

    return {
        "source_h_source": _v1_2_scalar_pair(source.dot(source)),
        "scalar_h_scalar": _v1_2_scalar_pair(scalar.dot(scalar)),
        "exact_h_exact": _v1_2_scalar_pair(exact.dot(exact)),
        "projected_h_projected": _v1_2_scalar_pair(projected.dot(projected)),
        "scalar_h_exact": _v1_2_scalar_pair(scalar.dot(exact)),
        "projected_h_exact": _v1_2_scalar_pair(projected.dot(exact)),
    }


def _v1_2_probe_coefficients(seed: int, count: int) -> np.ndarray:
    if int(count) <= 0:
        raise ValueError("V1-2 probe basis must be non-empty")
    indices = np.arange(int(count), dtype=np.int64)
    phase = ((int(seed) + 1) * (indices + 1)) % 104729
    return np.exp(2j * np.pi * phase / 104729.0).astype(np.complex128)


def _v1_2_seed_interface_active_row(
    seed: int, interface_rows_global: Sequence[int]
) -> int:
    rows = tuple(int(row) for row in interface_rows_global)
    if not rows:
        raise ValueError("V1-2 interface seed has no Gamma rows")
    return rows[int(seed) % len(rows)]


def _v1_2_global_interface_row_identity(
    oracle: Any, comm: MPI.Intracomm
) -> dict[str, dict[str, Any]]:
    identity: dict[str, dict[str, Any]] = {}
    for interface, group in (("lower", 0), ("upper", 2)):
        local_rows = oracle.group_gamma_rows_local(group)
        global_rows = tuple(
            int(row) for part in comm.allgather(local_rows.tolist()) for row in part
        )
        array = np.asarray(global_rows, dtype=np.int64)
        identity[interface] = {
            "global_rows": list(global_rows),
            "size": int(array.size),
            "sha256": hashlib.sha256(array.tobytes()).hexdigest(),
        }
    return identity


def _v1_2_interface_probes(
    *,
    manifest: Mapping[str, Any],
    oracle: Any,
    petrov_actions: Sequence[Any],
    scalar_apply: Sequence[Callable[[PETSc.Vec, PETSc.Vec], None]],
    z_group: Sequence[np.ndarray],
    comm: MPI.Intracomm,
) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    seed_groups = manifest["fixed_probe_seeds"]
    for interface, (group, seed_key) in enumerate(((0, "lower"), (2, "upper"))):
        basis = np.asarray(z_group[group], dtype=np.complex128)
        for probe_kind, seeds in (
            ("modal_combination", seed_groups["modal_combinations"][seed_key]),
            ("complement", seed_groups["complements"][seed_key]),
        ):
            for seed in seeds:
                source_values = np.zeros(basis.shape[0], dtype=np.complex128)
                if probe_kind == "modal_combination":
                    source_values[:] = basis @ _v1_2_probe_coefficients(
                        int(seed), basis.shape[1]
                    )
                else:
                    first, last = petrov_actions[group].ownership_range
                    packed_row = int(seed) % int(petrov_actions[group].global_rows)
                    if first <= packed_row < last:
                        source_values[packed_row - first] = 1.0
                source = petrov_actions[group].synthesize_owner_rows(source_values)
                scalar_target = source.duplicate()
                exact_target = source.duplicate()
                projected_target = source.duplicate()
                try:
                    y_before = petrov_actions[group].project_owner_rows(source)
                    if probe_kind == "complement":
                        factors = petrov_actions[group].projected_woodbury_factors()
                        local_coefficients = np.asarray(
                            factors["V"].conj().T
                            @ np.asarray(source.array, dtype=np.complex128),
                            dtype=np.complex128,
                        )
                        coefficients = np.empty_like(local_coefficients)
                        comm.Allreduce(local_coefficients, coefficients, op=MPI.SUM)
                        projected_values = source_values - basis @ coefficients
                        source.destroy()
                        source = petrov_actions[group].synthesize_owner_rows(
                            projected_values
                        )
                        norm = float(source.norm())
                        if norm <= 1.0e-30:
                            raise ValueError("V1-2 complement projection is zero")
                        source.scale(PETSc.ScalarType(1.0 / norm))
                        y_after = petrov_actions[group].project_owner_rows(source)
                    else:
                        y_after = y_before
                    scalar_apply[group](source, scalar_target)
                    oracle.apply_directed_neighbor(group, source, exact_target)
                    petrov_actions[group].apply(source, projected_target)
                    reports.append(
                        {
                            "interface": interface,
                            "group": group,
                            "kind": probe_kind,
                            "label": f"{seed_key}_{probe_kind}_{int(seed)}",
                            "seed": int(seed),
                            "scalar_exact_relative": _v1_2_relative_error(
                                scalar_target, exact_target
                            ),
                            "projected_exact_relative": _v1_2_relative_error(
                                projected_target, exact_target
                            ),
                            "YH_before_projection": _v1_2_complex_pairs(y_before),
                            "YH_after_projection": _v1_2_complex_pairs(y_after),
                            "complement_orthogonality_relative": (
                                float(np.linalg.norm(y_after))
                                / max(float(np.linalg.norm(y_before)), 1.0e-30)
                                if probe_kind == "complement"
                                else None
                            ),
                            "contractions": _v1_2_vec_contractions(
                                source,
                                scalar_target,
                                exact_target,
                                projected_target,
                            ),
                            "finite": bool(
                                np.isfinite(source.array).all()
                                and np.isfinite(scalar_target.array).all()
                                and np.isfinite(exact_target.array).all()
                                and np.isfinite(projected_target.array).all()
                            ),
                        }
                    )
                finally:
                    projected_target.destroy()
                    exact_target.destroy()
                    scalar_target.destroy()
                    source.destroy()
    return reports


def _v1_2_middle_cross_interface_samples(
    *,
    manifest: Mapping[str, Any],
    oracle: Any,
    petrov_actions: Sequence[Any],
    z_group: Sequence[np.ndarray],
    comm: MPI.Intracomm,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Sample the retained middle Schur, separately from the neighbor map."""

    seed_groups = manifest["fixed_probe_seeds"]
    group = 1
    basis = np.asarray(z_group[group], dtype=np.complex128)
    lower_count = int(np.asarray(z_group[0]).shape[1])
    middle_rows = oracle.group_gamma_rows_local(group)
    lower_rows = set(map(int, oracle.group_gamma_rows_local(0)))
    upper_rows = set(map(int, oracle.group_gamma_rows_local(2)))
    interface_identity = _v1_2_global_interface_row_identity(oracle, comm)
    interface_rows_global = {
        interface: tuple(identity["global_rows"])
        for interface, identity in interface_identity.items()
    }
    reports: list[dict[str, Any]] = []
    for interface, column_slice, seed_key in (
        ("lower", slice(0, lower_count), "lower"),
        ("upper", slice(lower_count, None), "upper"),
    ):
        interface_basis = basis[:, column_slice]
        for probe_kind, seeds in (
            ("modal_combination", seed_groups["modal_combinations"][seed_key]),
            ("complement", seed_groups["complements"][seed_key]),
        ):
            for seed in seeds:
                source_values = np.zeros(basis.shape[0], dtype=np.complex128)
                if probe_kind == "modal_combination":
                    source_values[:] = interface_basis @ _v1_2_probe_coefficients(
                        int(seed), interface_basis.shape[1]
                    )
                else:
                    active_row = _v1_2_seed_interface_active_row(
                        int(seed), interface_rows_global[seed_key]
                    )
                    local_matches = np.asarray(
                        [int(row) == active_row for row in middle_rows],
                        dtype=np.int32,
                    )
                    if int(comm.allreduce(int(local_matches.sum()), op=MPI.SUM)) != 1:
                        raise ValueError(
                            "V1-2 middle complement seed has no unique owner"
                        )
                    source_values[local_matches.astype(bool)] = 1.0
                    factors = petrov_actions[group].projected_woodbury_factors()
                    local_coefficients = np.asarray(
                        factors["V"].conj().T
                        @ np.asarray(source_values, dtype=np.complex128),
                        dtype=np.complex128,
                    )
                    coefficients = np.empty_like(local_coefficients)
                    comm.Allreduce(local_coefficients, coefficients, op=MPI.SUM)
                    source_values = source_values - basis @ coefficients
                source = petrov_actions[group].synthesize_owner_rows(source_values)
                target = oracle.create_group_gamma_vector(group)
                try:
                    if probe_kind == "complement":
                        norm = float(source.norm())
                        if norm <= 1.0e-30:
                            raise ValueError("V1-2 middle complement is zero")
                        source.scale(PETSc.ScalarType(1.0 / norm))
                    oracle.apply_group(group, source, target)
                    source_h_source = _v1_2_scalar_pair(source.dot(source))
                    target_values = np.asarray(target.array, dtype=np.complex128)
                    if interface == "lower":
                        same_mask = np.asarray(
                            [int(row) in lower_rows for row in middle_rows],
                            dtype=bool,
                        )
                        cross_mask = np.asarray(
                            [int(row) in upper_rows for row in middle_rows],
                            dtype=bool,
                        )
                    else:
                        same_mask = np.asarray(
                            [int(row) in upper_rows for row in middle_rows],
                            dtype=bool,
                        )
                        cross_mask = np.asarray(
                            [int(row) in lower_rows for row in middle_rows],
                            dtype=bool,
                        )
                    if np.any(same_mask & cross_mask):
                        raise ValueError("middle Gamma interface masks overlap")
                    if not np.all(same_mask | cross_mask):
                        raise ValueError(
                            "middle Gamma row is not in either interface support"
                        )
                    same_local = float(
                        np.real(
                            np.vdot(target_values[same_mask], target_values[same_mask])
                        )
                    )
                    cross_local = float(
                        np.real(
                            np.vdot(
                                target_values[cross_mask],
                                target_values[cross_mask],
                            )
                        )
                    )
                    same_squared = float(comm.allreduce(same_local, op=MPI.SUM))
                    cross_squared = float(comm.allreduce(cross_local, op=MPI.SUM))
                    total_squared = same_squared + cross_squared
                    same_interface_norm = math.sqrt(max(same_squared, 0.0))
                    cross_interface_norm = math.sqrt(max(cross_squared, 0.0))
                    total_norm = math.sqrt(max(total_squared, 0.0))
                    middle_h_middle = _v1_2_scalar_pair(target.dot(target))
                    source_h_middle = _v1_2_scalar_pair(source.dot(target))
                    identity = interface_identity[seed_key]
                    seed_identity = {}
                    if probe_kind == "complement":
                        interface_row_index = int(seed) % int(identity["size"])
                        seed_identity = {
                            "selected_active_row": int(
                                identity["global_rows"][interface_row_index]
                            ),
                            "interface_row_index": interface_row_index,
                            "interface_size": int(identity["size"]),
                            "interface_rows_global_order_sha256": identity["sha256"],
                        }
                    reports.append(
                        {
                            "label": f"middle_{seed_key}_{probe_kind}_{int(seed)}",
                            "interface": interface,
                            "group": group,
                            "source_group": group,
                            "kind": probe_kind,
                            "seed": int(seed),
                            "response": "middle_group1_schur",
                            "direction": "apply_group",
                            **seed_identity,
                            "contractions": {
                                "source_h_source": source_h_source,
                                "middle_h_middle": middle_h_middle,
                                "source_h_middle": source_h_middle,
                            },
                            "source_norm": float(source.norm()),
                            "middle_norm": total_norm,
                            "same_interface_norm": same_interface_norm,
                            "cross_interface_norm": cross_interface_norm,
                            "total_norm": total_norm,
                            "partition_disjoint": True,
                            "partition_complete": True,
                            "cross_to_total": (
                                cross_interface_norm / total_norm
                                if total_norm > 0.0
                                else 0.0
                            ),
                            "finite": bool(
                                np.isfinite(source.array).all()
                                and np.isfinite(target.array).all()
                            ),
                        }
                    )
                finally:
                    target.destroy()
                    source.destroy()
    return reports, interface_identity


def _v2_build_packet_layouts(
    *,
    system: Any,
    condensed: Any,
    supports: Sequence[Mapping[str, Any]],
    gamma_rows: Sequence[np.ndarray],
    lower_z: float,
    upper_z: float,
    comm: MPI.Intracomm,
) -> tuple[Any, Any, Any]:
    """Build the three owner-local canonical packet layouts."""

    lower_original, _ = _v1_2_local_interface_rows(
        condensed, supports[0], gamma_rows[0]
    )
    upper_original, _ = _v1_2_local_interface_rows(
        condensed, supports[1], gamma_rows[2]
    )
    lower_layout = build_dolfinx_plane_gamma_layout(
        function_space=system.V,
        condensed=condensed,
        floquet_data=getattr(system, "floquet_data", None),
        interface_z_nm=lower_z,
        plane_cell_side="lower",
        plane_original_dofs=lower_original,
        gamma_rows_local=gamma_rows[0],
        plane_identity={"route": "v2_interface_packet", "group": "group0"},
    )
    upper_layout = build_dolfinx_plane_gamma_layout(
        function_space=system.V,
        condensed=condensed,
        floquet_data=getattr(system, "floquet_data", None),
        interface_z_nm=upper_z,
        plane_cell_side="upper",
        plane_original_dofs=upper_original,
        gamma_rows_local=gamma_rows[2],
        plane_identity={"route": "v2_interface_packet", "group": "group2"},
    )
    middle_blocks = tuple(
        placement.block
        for layout in (lower_layout, upper_layout)
        for placement in layout.blocks
    )
    middle_layout = build_gamma_canonical_layout(
        middle_blocks,
        gamma_rows[1],
        plane_identity={
            "route": "v2_interface_packet",
            "group": "group1",
            "planes": ["lower", "upper"],
            "interface_z_nm": [lower_z, upper_z],
            "phase_convention": "stored_raw=phase*E*canonical",
        },
        comm=comm,
    )
    return lower_layout, middle_layout, upper_layout


def _v2_prepare_packet_shards(
    *,
    packet_root: str | Path,
    petrov_actions: Sequence[Any],
    packet_layouts: Sequence[Any],
    petrov_diagnostics: Sequence[Mapping[str, Any]],
    identity_observed: Mapping[str, Any],
    z_shapes: Sequence[Sequence[int]],
    source_sha: str,
    input_sha256: str,
    physical_model_sha256: str,
    selected_manifest_sha256: str,
    spool_catalog_sha256: str,
    probe_manifest_sha256: str,
    lower_metadata: Mapping[str, Any],
    upper_metadata: Mapping[str, Any],
    physical_probe_reports: Sequence[Mapping[str, Any]],
    interface_probe_reports: Sequence[Mapping[str, Any]],
    middle_cross_interface_reports: Sequence[Mapping[str, Any]],
    middle_cross_interface_identity: Mapping[str, Any],
    middle_group_schur: Mapping[str, Any],
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    """Detach one Petrov action at a time and write its owner-local shard."""

    descriptors: list[dict[str, Any]] = []
    small_matrices: dict[str, np.ndarray] = {}
    lower_span, middle_span, upper_span = (
        int(z_shapes[group][1]) for group in range(3)
    )
    if middle_span != lower_span + upper_span:
        raise ValueError("projected middle Schur spans do not form lower plus upper")
    middle_projected = np.asarray(middle_group_schur["projected"], dtype=np.complex128)
    if (
        middle_projected.shape != (middle_span, middle_span)
        or not np.isfinite(middle_projected).all()
    ):
        raise ValueError(
            "projected middle group Schur has the wrong shape or finite values"
        )
    lower_error: float | None = None
    upper_error: float | None = None
    for group, action in enumerate(petrov_actions):
        ownership_range = tuple(int(value) for value in action.ownership_range)
        factors = action.detach_projected_woodbury_factors()
        values_u = factors["U"]
        values_v = factors["V"]
        canonical = canonicalize_owner_local_basis_in_place(
            packet_layouts[group], values_u, values_v
        )
        descriptors.append(
            write_group_shard(
                packet_root,
                PacketGroup(f"group{group}", canonical.keys, canonical.U, canonical.V),
                comm=comm,
                ownership_range=ownership_range,
            )
        )
        if comm.rank == 0:
            small_matrices.update(
                {
                    f"gram_group{group}": np.asarray(factors["G"]),
                    f"projected_scalar_group{group}": np.asarray(
                        factors["projected_scalar"]
                    ),
                    f"projected_exact_group{group}": np.asarray(
                        factors["projected_exact"]
                    ),
                }
            )
        if group == 0:
            reference = middle_projected[:lower_span, :lower_span]
            lower_error = float(
                np.linalg.norm(factors["projected_exact"] - reference)
                / max(np.linalg.norm(reference), np.finfo(float).tiny)
            )
        elif group == 2:
            reference = middle_projected[lower_span:middle_span, lower_span:middle_span]
            upper_error = float(
                np.linalg.norm(factors["projected_exact"] - reference)
                / max(np.linalg.norm(reference), np.finfo(float).tiny)
            )
        if group == 2 and (
            lower_error is None
            or upper_error is None
            or lower_error > 1.0e-12
            or upper_error > 1.0e-12
        ):
            raise ValueError(
                "projected middle Schur diagonal blocks do not match group exact"
            )
        del canonical, values_u, values_v, factors
    middle_metadata = {
        key: value for key, value in middle_group_schur.items() if key != "projected"
    }
    middle_metadata.update(
        {
            "schema": "task040.v3.middle_group_schur_projection.v1",
            "storage": "packet_small_matrices",
            "matrix_name": "projected_middle_group_schur",
            "lower_identity_relative_error": lower_error,
            "upper_identity_relative_error": upper_error,
            "cross_blocks": {
                "LU_frobenius_norm": float(
                    np.linalg.norm(
                        middle_projected[:lower_span, lower_span:middle_span], ord="fro"
                    )
                ),
                "UL_frobenius_norm": float(
                    np.linalg.norm(
                        middle_projected[lower_span:middle_span, :lower_span], ord="fro"
                    )
                ),
                "LU_relative_frobenius_norm": float(
                    np.linalg.norm(
                        middle_projected[:lower_span, lower_span:middle_span], ord="fro"
                    )
                    / max(
                        np.linalg.norm(middle_projected, ord="fro"),
                        np.finfo(float).tiny,
                    )
                ),
                "UL_relative_frobenius_norm": float(
                    np.linalg.norm(
                        middle_projected[lower_span:middle_span, :lower_span], ord="fro"
                    )
                    / max(
                        np.linalg.norm(middle_projected, ord="fro"),
                        np.finfo(float).tiny,
                    )
                ),
            },
            "joint_exact_definition": (
                "projected_middle_group_schur + projected_exact_group1"
            ),
        }
    )
    if comm.rank == 0:
        small_matrices["projected_middle_group_schur"] = middle_projected
    return {
        "descriptors": descriptors,
        "small_matrices": small_matrices if comm.rank == 0 else None,
        "provenance": {
            "schema": "task040.v2.interface_packet_producer.v1",
            "source_sha": str(source_sha),
            "input_sha256": str(input_sha256),
            "physical_model_sha256": str(physical_model_sha256),
            "selected_manifest_sha256": str(selected_manifest_sha256),
            "exact_spool_catalog_sha256": str(spool_catalog_sha256),
            "probe_manifest_sha256": str(probe_manifest_sha256),
            "qep_calls": 0,
            "pde_solve": "not_run",
            "v1_3_built": False,
        },
        "diagnostics": {
            "group_order": ["group0", "group1", "group2"],
            "groups": [
                {
                    "group": group,
                    "span_size": int(z_shapes[group][1]),
                    "gamma_layout": {
                        **dict(packet_layouts[group].audit),
                        **(
                            {
                                "global_size": int(
                                    middle_cross_interface_identity[interface]["size"]
                                ),
                                "gamma_rows_global_order_sha256": (
                                    middle_cross_interface_identity[interface]["sha256"]
                                ),
                            }
                            if (
                                interface := (
                                    "lower"
                                    if group == 0
                                    else "upper"
                                    if group == 2
                                    else None
                                )
                            )
                            is not None
                            else {}
                        ),
                    },
                    "petrov": dict(petrov_diagnostics[group]),
                }
                for group in range(3)
            ],
            "identity_observed": dict(identity_observed),
            "probe_manifest_sha256": identity_observed["probe_manifest_sha256"],
            "input_sha256": identity_observed["input_sha256"],
            "physical_model_sha256": identity_observed["physical_model_sha256"],
            "selected_manifest_sha256": identity_observed["selected_manifest_sha256"],
            "lower": {
                "mode_count": int(lower_metadata["mode_count"]),
                "mode_key_sha256": lower_metadata["mode_key_sha256"],
                "legacy_beta_metadata_sha256": lower_metadata[
                    "legacy_manifest_beta_metadata_sha256"
                ],
                "resolved_mode_metadata_sha256": lower_metadata[
                    "resolved_mode_metadata_sha256"
                ],
            },
            "upper": {
                "mode_count": int(len(upper_metadata["mode_keys"])),
                "mode_key_sha256": upper_metadata["mode_key_sha256"],
                "beta_sha256": upper_metadata["selected_packet_beta_sha256"],
                "branch_authority": upper_metadata["branch_authority"],
                "qep_calls": int(upper_metadata["qep_calls"]),
            },
            "exact_output_identity_sha256": dict(
                identity_observed["exact_output_identity_sha256"]
            ),
            "incoming_neighbor_map": {
                "map": "block_diagonal_neighbor_transmission",
                "response": "apply_directed_neighbor",
                "probe_count": len(interface_probe_reports),
            },
            "probes": list(physical_probe_reports) + list(interface_probe_reports),
            "lower_resolved_mode_metadata_sha256": lower_metadata[
                "resolved_mode_metadata_sha256"
            ],
            "upper_mode_key_sha256": upper_metadata["mode_key_sha256"],
            "upper_beta_sha256": upper_metadata["selected_packet_beta_sha256"],
            "basis_global_replicated": False,
            "fe_numeric_allgather": False,
            "physical_probe_reports": list(physical_probe_reports),
            "interface_probe_reports": list(interface_probe_reports),
            "middle_cross_interface_sampled_response": list(
                middle_cross_interface_reports
            ),
            "middle_cross_interface_identity": dict(middle_cross_interface_identity),
            "projected_matrix_names": {
                f"group{group}": {
                    "gram": f"gram_group{group}",
                    "scalar": f"projected_scalar_group{group}",
                    "exact": f"projected_exact_group{group}",
                }
                for group in range(3)
            },
            "additional_projected_matrices": {
                "projected_middle_group_schur": middle_metadata,
            },
            "factor_inventory": {
                "ready": 3,
                "after": 0,
                "simultaneous_max": 3,
                "full_side": 0,
                "global_direct": 0,
                "nested_ksp": 0,
            },
        },
        "expected_group_counts": {
            f"group{group}": int(packet_layouts[group].audit["global_row_count"])
            for group in range(3)
        },
    }


def _v2_finalize_packet(
    *,
    packet_root: str | Path,
    pending: Mapping[str, Any],
    exact_ready: Mapping[str, Any],
    exact_after: Mapping[str, Any],
    v1_2_gate: Mapping[str, Any],
    diagnostics: Mapping[str, Any],
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    packet_diagnostics = {
        **dict(pending["diagnostics"]),
        **dict(diagnostics),
        "v1_2_gate": dict(v1_2_gate),
        "factor_lifecycle": {
            "exact_oracle_ready": dict(exact_ready),
            "exact_oracle_after_cleanup": dict(exact_after),
            "factor_count_ready": int(exact_ready["factor_count_ready"]),
            "factor_count_after_cleanup": int(
                exact_after["factor_count_after_cleanup"]
            ),
            "simultaneous_factor_count_max": int(exact_ready["factor_count_ready"]),
        },
        "packet_complete": True,
    }
    return finalize_manifest(
        packet_root,
        list(pending["descriptors"]),
        provenance=dict(pending["provenance"]),
        group_names=("group0", "group1", "group2"),
        expected_group_counts=dict(pending["expected_group_counts"]),
        small_matrices=pending["small_matrices"],
        diagnostics=packet_diagnostics,
        comm=comm,
    )


def _run_v1_2_interface_schur(
    *,
    cfg: Any,
    system: Any,
    bare_f: PETSc.Mat,
    source_sha: str,
    input_sha256: str,
    physical_model_sha256: str,
    group_rows: Sequence[np.ndarray],
    group_audit: dict[str, Any],
    supports: Sequence[Mapping[str, Any]],
    masses: Sequence[Any],
    exact_spool_root: str | Path,
    beta: complex,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None,
    resource_callback: Callable[[], Mapping[str, Any]] | None,
    producer_mode: bool = False,
    packet_root: str | Path | None = None,
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    manifest_path, manifest = _v1_2_load_manifest()
    identity = manifest["identity"]
    selected_manifest = (
        Path(__file__).resolve().parents[1] / identity["selected_manifest"]
    )
    selected_manifest_sha256 = hashlib.sha256(
        selected_manifest.read_bytes()
    ).hexdigest()
    selected_payload = json.loads(selected_manifest.read_text(encoding="utf-8"))
    selected_identity_path = selected_manifest.with_name("identity.json")
    selected_identity = json.loads(selected_identity_path.read_text(encoding="utf-8"))
    if selected_payload.get("identity_sha256") != identity["selected_identity_sha256"]:
        raise ValueError("V1-2 selected identity SHA differs from frozen manifest")
    if (
        selected_payload.get("selection_sha256")
        != identity["selected_selection_sha256"]
    ):
        raise ValueError("V1-2 selected selection SHA differs from frozen manifest")
    resolved_path = Path(exact_spool_root).resolve().parent / "resolved_config.json"
    resolved = json.loads(resolved_path.read_text(encoding="utf-8"))
    resolved_modes = resolved["derived"]["external_mode_inventory"]
    lower_authority = {
        **resolved_modes,
        "keys": tuple(
            key for key in resolved_modes["keys"] if str(key["side"]) == "bottom"
        ),
        "modes": tuple(
            mode for mode in resolved_modes["modes"] if str(mode["side"]) == "bottom"
        ),
        "count": _v1_2_lower_mode_count(resolved_modes),
        "canonical_key_list_sha256": manifest["lower_fourier_floquet_basis"][
            "canonical_key_list_sha256"
        ],
        "beta_metadata_sha256": manifest["lower_fourier_floquet_basis"][
            "beta_metadata_sha256"
        ],
    }
    if _v1_2_build_hash := manifest["identity"]["exact_spool_resolved_config_sha256"]:
        if hashlib.sha256(resolved_path.read_bytes()).hexdigest() != _v1_2_build_hash:
            raise ValueError("V1-2 resolved lower-mode authority hash mismatch")
    cross_section = build_matching_cross_section(system.cfg, "stage4_xy", comm=comm)
    spaces = build_cross_section_spaces(
        cross_section, transverse_degree=int(system.cfg.nedelec_degree)
    )
    condensed = system.static_condensation.condensed
    oracle = None
    petrov_actions: list[Any] = []
    projected_action = None
    projected_owner = None
    owner_transferred = False
    exact_after: dict[str, Any] | None = None
    packet_layouts: tuple[Any, Any, Any] | None = None
    packet_pending: dict[str, Any] | None = None
    packet_manifest: dict[str, Any] | None = None
    middle_group_schur: dict[str, Any] | None = None
    middle_group_schur_metadata: dict[str, Any] | None = None
    source_vectors: dict[str, PETSc.Vec] = {}
    try:
        oracle = build_petsc_interface_schur_oracle(bare_f, group_rows, supports)
        gamma_rows = tuple(oracle.group_gamma_rows_local(group) for group in range(3))
        lower = _v1_2_build_lower_basis(
            cfg=cfg,
            system=system,
            spaces=spaces,
            condensed=condensed,
            support=supports[0],
            gamma_rows_local=gamma_rows[0],
            interface_z=float(manifest["interfaces"]["lower"]["z"]),
            authority=lower_authority,
        )
        upper = _v1_2_build_upper_basis(
            system=system,
            spaces=spaces,
            condensed=condensed,
            support=supports[1],
            gamma_rows_local=gamma_rows[2],
            interface_z=float(manifest["interfaces"]["upper"]["z"]),
            selected_manifest=selected_manifest,
            selected_identity=selected_identity,
            selected_payload=selected_payload,
            expected_mode_key_sha256=manifest["upper_selected_packet_basis"][
                "positive_mode_keys_sha256"
            ],
            expected_beta_sha256=manifest["upper_selected_packet_basis"][
                "positive_beta_sha256"
            ],
            comm=comm,
        )
        lower_y_audit: dict[str, Any] = {}
        upper_y_audit: dict[str, Any] = {}
        lower_y = build_mass_dual_from_active_vec(
            masses[0], condensed, gamma_rows[0], lower["left"], lower_y_audit
        )
        upper_y = build_mass_dual_from_active_vec(
            masses[1], condensed, gamma_rows[2], upper["left"], upper_y_audit
        )
        z_group = tuple(
            build_group_basis_columns(
                group,
                gamma_rows[group],
                gamma_rows[0],
                lower["values"],
                gamma_rows[2],
                upper["right"],
            )
            for group in range(3)
        )
        y_group = tuple(
            build_group_basis_columns(
                group,
                gamma_rows[group],
                gamma_rows[0],
                lower_y,
                gamma_rows[2],
                upper_y,
            )
            for group in range(3)
        )
        scalar_apply = tuple(
            _v1_2_scalar_gamma_apply(
                condensed=condensed,
                group=group,
                gamma_rows=gamma_rows[group],
                masses=masses,
                beta=beta,
            )
            for group in range(3)
        )
        for group in range(3):
            layout = oracle.create_group_gamma_vector(group)
            try:
                petrov_actions.append(
                    build_distributed_petrov_action(
                        layout,
                        scalar_apply[group],
                        lambda source, target, group=group: (
                            oracle.apply_directed_neighbor(group, source, target)
                        ),
                        z_group[group],
                        y_group[group],
                        local_row_ids=gamma_rows[group],
                    )
                )
            finally:
                layout.destroy()
        spool_identity, spool_manifest_sha, catalog = _v9_frozen_holdout_identity(
            exact_spool_root, comm
        )
        spool_catalog_sha256 = _v1_2_validate_spool_identity(
            selected_manifest_sha256=spool_manifest_sha, catalog=catalog
        )
        spool = _load_v5_fixed_budget_spool_shards(
            exact_spool_root,
            comm,
            packet_identity=spool_identity,
            manifest_sha256=spool_manifest_sha,
        )
        labels = tuple(manifest["physical_probes"]["labels"])
        exact_identities = manifest["physical_probes"]["exact_output_identity_sha256"]
        traces, observed_exact_ids = _v1_2_restrict_exact_probes(
            spool=spool,
            labels=labels,
            expected_identities=exact_identities,
            template_matrix=bare_f,
            lower_rows=gamma_rows[0],
            upper_rows=gamma_rows[2],
        )
        probe_reports = _v1_2_probe_actions(
            labels=labels,
            traces=traces,
            oracle=oracle,
            petrov_actions=petrov_actions,
            scalar_apply=scalar_apply,
            gamma_rows=gamma_rows,
        )
        interface_probe_reports = _v1_2_interface_probes(
            manifest=manifest,
            oracle=oracle,
            petrov_actions=petrov_actions,
            scalar_apply=scalar_apply,
            z_group=z_group,
            comm=comm,
        )
        (
            middle_cross_interface_reports,
            middle_cross_interface_identity,
        ) = _v1_2_middle_cross_interface_samples(
            manifest=manifest,
            oracle=oracle,
            petrov_actions=petrov_actions,
            z_group=z_group,
            comm=comm,
        )
        if producer_mode:
            middle_group_schur = petrov_actions[1].project_additional_action(
                lambda source, target: oracle.apply_group(1, source, target),
                name="projected_middle_group_schur",
                semantic="Y1^H [oracle.apply_group(1)] Z1",
            )
        exact_ready = oracle.diagnostics
        petrov_diagnostics = [action.diagnostics for action in petrov_actions]
        petrov_contractions = None
        if not producer_mode:
            petrov_contractions = [
                {
                    name: _v1_2_matrix_pairs(value)
                    for name, value in action.projected_contractions.items()
                    if name in {"gram", "scalar", "exact"}
                }
                for action in petrov_actions
            ]
        if producer_mode:
            if packet_root is None:
                raise ValueError("V2 producer requires a worker packet root")
            packet_layouts = _v2_build_packet_layouts(
                system=system,
                condensed=condensed,
                supports=supports,
                gamma_rows=gamma_rows,
                lower_z=float(manifest["interfaces"]["lower"]["z"]),
                upper_z=float(manifest["interfaces"]["upper"]["z"]),
                comm=comm,
            )
        if producer_mode:
            assert packet_layouts is not None
            group_layouts = [dict(layout.audit) for layout in packet_layouts]
        else:
            group_layouts = [
                {
                    **oracle.group_gamma_layout(group),
                    "basis_global_replicated": False,
                    "fe_numeric_allgather": False,
                }
                for group in range(3)
            ]
        identity_observed = {
            "probe_manifest_sha256": hashlib.sha256(
                manifest_path.read_bytes()
            ).hexdigest(),
            "input_sha256": str(input_sha256),
            "physical_model_sha256": str(physical_model_sha256),
            "selected_manifest_sha256": selected_manifest_sha256,
            "selected_identity_sha256": selected_payload.get("identity_sha256"),
            "selected_selection_sha256": selected_payload.get("selection_sha256"),
            "selected_identity_physical_sha256": selected_identity.get(
                "physical_sha256"
            ),
            "resolved_config_sha256": hashlib.sha256(
                resolved_path.read_bytes()
            ).hexdigest(),
            "spool_catalog_sha256": spool_catalog_sha256,
            "exact_output_identity_sha256": dict(observed_exact_ids),
            "upper_mode_key_sha256": upper["mode_key_sha256"],
            "upper_beta_sha256": upper["selected_packet_beta_sha256"],
            "lower_mode_key_sha256": lower["mode_key_sha256"],
            "lower_resolved_mode_metadata_sha256": lower[
                "resolved_mode_metadata_sha256"
            ],
            "lower_legacy_beta_metadata_sha256": lower[
                "legacy_manifest_beta_metadata_sha256"
            ],
        }
        identity_pass = _v1_2_identity_pass(
            identity_observed=identity_observed,
            frozen_identity=identity,
            manifest=manifest,
            exact_identities=exact_identities,
        )
        resource_observed = (
            dict(resource_callback()) if resource_callback is not None else None
        )
        resource_pass = bool(
            resource_observed is not None
            and resource_observed.get("all_status_readable") is True
            and int(resource_observed.get("rss_bytes", -1))
            < (
                TASK040_V2_INTERFACE_PACKET_HARD_STOP_BYTES
                if producer_mode
                else TASK040_LEVEL_A_HARD_STOP_BYTES
            )
            and int(resource_observed.get("swap_bytes", -1)) == 0
        )
        preferred_resource_pass = bool(
            resource_observed is not None
            and resource_observed.get("all_status_readable") is True
            and int(resource_observed.get("rss_bytes", -1))
            <= TASK040_V2_INTERFACE_PACKET_PREFERRED_BYTES
            and int(resource_observed.get("swap_bytes", -1)) == 0
        )
        condition_pass = all(
            np.isfinite(float(petrov_diagnostics[group]["gram"]["condition"]))
            and float(petrov_diagnostics[group]["gram"]["condition"]) <= 1.0e12
            for group in range(3)
        )
        v1_2_gate = {
            "identity_pass": identity_pass,
            "projection_pass": all(
                all(np.isfinite(values).all() for values in matrix)
                for matrix in (lower["values"], upper["right"], upper["left"])
            ),
            "finite_pass": all(
                np.isfinite(report["projected_exact_relative"])
                and all(
                    _v1_2_json_finite(value)
                    for value in report["contractions"].values()
                )
                for report in probe_reports
            )
            and all(report["finite"] for report in interface_probe_reports)
            and all(report["finite"] for report in middle_cross_interface_reports),
            "gram_pass": all(
                petrov_diagnostics[group]["gram"]["rank"]
                == petrov_diagnostics[group]["small_replicated_shapes"]["gram"][0]
                for group in range(3)
            ),
            "complement_pass": all(
                report["kind"] != "complement"
                or report["complement_orthogonality_relative"] <= 1.0e-8
                for report in interface_probe_reports
            ),
            "factor_pass": exact_ready.get("factor_count_ready") == 3,
            "lifecycle_pass": False,
            "resource_pass": resource_pass,
            "middle_cross_interface_pass": bool(
                len(middle_cross_interface_reports) == 8
                and all(
                    report["finite"]
                    and report["source_norm"] > 0.0
                    and report["middle_norm"] > 0.0
                    for report in middle_cross_interface_reports
                )
            ),
        }
        if producer_mode:
            v1_2_gate["condition_pass"] = condition_pass
            v1_2_gate["preferred_resource_pass"] = preferred_resource_pass
            z_shapes = tuple(
                tuple(int(value) for value in matrix.shape) for matrix in z_group
            )
            y_shapes = tuple(
                tuple(int(value) for value in matrix.shape) for matrix in y_group
            )
            for key in ("values", "left"):
                lower.pop(key, None)
            for key in ("right", "left"):
                upper.pop(key, None)
            del spool, traces, scalar_apply, z_group, y_group, lower_y, upper_y
            if not all(
                bool(value)
                for name, value in v1_2_gate.items()
                if name
                not in {"factor_pass", "lifecycle_pass", "preferred_resource_pass"}
            ):
                raise RuntimeError(
                    "V2 producer stopped before packet export: V1-2 probe Gate failed"
                )
            assert packet_layouts is not None
            packet_pending = _v2_prepare_packet_shards(
                packet_root=packet_root,
                petrov_actions=petrov_actions,
                packet_layouts=packet_layouts,
                petrov_diagnostics=petrov_diagnostics,
                identity_observed=identity_observed,
                z_shapes=z_shapes,
                source_sha=source_sha,
                input_sha256=input_sha256,
                physical_model_sha256=physical_model_sha256,
                selected_manifest_sha256=selected_manifest_sha256,
                spool_catalog_sha256=spool_catalog_sha256,
                probe_manifest_sha256=identity_observed["probe_manifest_sha256"],
                lower_metadata=lower,
                upper_metadata=upper,
                physical_probe_reports=probe_reports,
                interface_probe_reports=interface_probe_reports,
                middle_cross_interface_reports=middle_cross_interface_reports,
                middle_cross_interface_identity=middle_cross_interface_identity,
                middle_group_schur=middle_group_schur,
                comm=comm,
            )
            middle_group_schur_metadata = dict(
                packet_pending["diagnostics"]["additional_projected_matrices"][
                    "projected_middle_group_schur"
                ]
            )
            packet_layouts = None
            middle_group_schur = None
        _emit(
            marker_callback,
            "v1_2_exact_oracle_ready",
            factor_count_ready=exact_ready["factor_count_ready"],
            group_count=3,
            lower_mode_count=int(lower["mode_count"]),
            upper_mode_count=int(selected_payload["mode_count"]),
        )
        oracle.destroy()
        exact_after = oracle.diagnostics
        oracle = None
        v1_2_gate["factor_pass"] = bool(
            exact_ready.get("factor_count_ready") == 3
            and exact_after.get("factor_count_after_cleanup") == 0
            and exact_after.get("destroyed") is True
        )
        v1_2_gate["lifecycle_pass"] = bool(
            exact_ready.get("factor_count_ready") == 3
            and exact_after.get("factor_count_after_cleanup") == 0
        )
        v1_2_gate["pass"] = all(
            bool(value)
            for name, value in v1_2_gate.items()
            if name != "preferred_resource_pass"
        )
        _emit(
            marker_callback,
            "v1_2_exact_oracle_released",
            factor_count_after_cleanup=exact_after["factor_count_after_cleanup"],
        )
        if producer_mode:
            if not v1_2_gate["pass"]:
                raise RuntimeError(
                    "V2 producer exact factor lifecycle did not close 3->0"
                )
            assert packet_pending is not None
            packet_manifest = _v2_finalize_packet(
                packet_root=packet_root,
                pending=packet_pending,
                exact_ready=exact_ready,
                exact_after=exact_after,
                v1_2_gate=v1_2_gate,
                diagnostics={
                    "identity_observed": identity_observed,
                    "middle_cross_interface_sampled_response": (
                        middle_cross_interface_reports
                    ),
                    "middle_cross_interface_identity": middle_cross_interface_identity,
                },
                comm=comm,
            )
            projected_diagnostics = {"v1_3_not_run": "producer_route_disables_v1_3"}
        elif v1_2_gate["pass"]:
            projected_action, projected_owner, projected_diagnostics = (
                build_v1_3_projected_transmission(
                    bare_f=bare_f,
                    group_rows=list(group_rows),
                    interface_masses=list(masses),
                    beta=beta,
                    group_audit=group_audit,
                    petrov_actions=petrov_actions,
                )
            )
            _emit(
                marker_callback,
                "v1_3_projected_ready",
                **dict(projected_diagnostics),
            )
        else:
            projected_diagnostics = {"v1_3_not_run": "v1_2_gate_failed"}
        projected_ready = (
            projected_owner.diagnostics if projected_owner is not None else None
        )
        projected_audit = None
        projected_screen = None
        projected_inventory = None
        if projected_action is not None and projected_owner is not None:
            for label in TASK040_LEVEL_A_SOURCE_LABELS:
                template = bare_f.createVecLeft()
                try:
                    source_vectors[label] = _load_v5_blr_reference_spool_remapped(
                        spool[label]["rhs"], template
                    )
                finally:
                    template.destroy()
            projected_inventory = {
                "observed": True,
                "factor_count_ready": int(projected_ready["factor_count_ready"]),
                "cross_section_factor_count_ready": int(
                    projected_ready["factor_count_ready"]
                ),
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
                "oracle_only": True,
                "scalable_candidate": False,
            }
            if projected_inventory["factor_count_ready"] != 3:
                raise RuntimeError("V1-3 scalar factor inventory is not exactly three")
            projected_audit = audit_petsc_level_a_one_apply(
                projected_action,
                bare_f,
                source_vectors,
                projected_inventory,
                collect_scalar_contractions=True,
            )
            projected_screen = run_v1_1_right_preconditioned_fgmres_batch(
                bare_f,
                {
                    label: source_vectors[label]
                    for label in TASK040_LEVEL_A_SOURCE_LABELS[1:]
                },
                projected_action,
                labels=TASK040_LEVEL_A_SOURCE_LABELS[1:],
                resource_callback=resource_callback,
                stop_on_frozen_gate=True,
                checkpoint_callback=lambda row: _emit(
                    marker_callback, "v1_3_fgmres_checkpoint", **dict(row)
                ),
            )
            for vector in source_vectors.values():
                vector.destroy()
            source_vectors.clear()
        for action in petrov_actions:
            action.destroy()
        petrov_actions.clear()
        route_result = {
            "result": {
                "schema": (
                    TASK040_V2_INTERFACE_PACKET_SCHEMA
                    if producer_mode
                    else TASK040_V1_2_SCHEMA
                ),
                "method": (
                    TASK040_V2_INTERFACE_PACKET_METHOD
                    if producer_mode
                    else TASK040_V1_2_METHOD
                ),
                "profile": (
                    TASK040_V2_INTERFACE_PACKET_PROFILE_ID
                    if producer_mode
                    else TASK040_V1_2_PROFILE_ID
                ),
                "source_sha": str(source_sha),
                "input_sha256": str(input_sha256),
                "physical_model_sha256": str(physical_model_sha256),
                "selected_manifest_sha256": selected_manifest_sha256,
                "exact_spool_catalog_sha256": spool_catalog_sha256,
                "sequence": list(TASK040_LEVEL_A_SEQUENCE),
                "beta": {
                    "formula": "cfg.k0 * complex(cfg.substrate_index)",
                    "value": [float(beta.real), float(beta.imag)],
                    "q": [float((-1j * beta).real), float((-1j * beta).imag)],
                    "authority": TASK040_LEVEL_A_BETA_AUTHORITY,
                },
                "interface_schur_raw": {
                    "basis_global_replicated": False,
                    "fe_numeric_allgather": False,
                    "probe_manifest_sha256": identity_observed["probe_manifest_sha256"],
                    "lower": {
                        "mode_count": int(lower["mode_count"]),
                        "mode_key_sha256": lower["mode_key_sha256"],
                        "legacy_beta_metadata_sha256": lower[
                            "legacy_manifest_beta_metadata_sha256"
                        ],
                        "resolved_mode_metadata_sha256": lower[
                            "resolved_mode_metadata_sha256"
                        ],
                    },
                    "upper": {
                        "mode_count": int(upper["mode_keys"].__len__()),
                        "mode_key_sha256": upper["mode_key_sha256"],
                        "beta_sha256": upper["selected_packet_beta_sha256"],
                        "branch_authority": upper["branch_authority"],
                        "qep_calls": upper["qep_calls"],
                    },
                    "exact_output_identity_sha256": dict(observed_exact_ids),
                    "exact_output_metadata_hash_validation": True,
                    "spool_catalog_sha256": spool_catalog_sha256,
                    "spool_catalog": catalog,
                    "groups": [
                        {
                            "group": group,
                            "span_size": int(
                                z_shapes[group][1]
                                if producer_mode
                                else z_group[group].shape[1]
                            ),
                            "gamma_layout": group_layouts[group],
                            "z_shape_local": list(
                                z_shapes[group]
                                if producer_mode
                                else z_group[group].shape
                            ),
                            "y_shape_local": list(
                                y_shapes[group]
                                if producer_mode
                                else y_group[group].shape
                            ),
                            "petrov": petrov_diagnostics[group],
                            "projected_contractions": (
                                petrov_contractions[group]
                                if petrov_contractions is not None
                                else {
                                    "storage": "packet_small_matrices",
                                    "gram": f"gram_group{group}",
                                    "scalar": f"projected_scalar_group{group}",
                                    "exact": f"projected_exact_group{group}",
                                }
                            ),
                        }
                        for group in range(3)
                    ],
                    "physical_probes": probe_reports,
                    "incoming_neighbor_map": {
                        "map": "block_diagonal_neighbor_transmission",
                        "response": "apply_directed_neighbor",
                        "probe_count": len(interface_probe_reports),
                    },
                    "interface_probes": interface_probe_reports,
                    "middle_cross_interface_sampled_response": (
                        middle_cross_interface_reports
                    ),
                    "middle_cross_interface_identity": (
                        middle_cross_interface_identity
                    ),
                    "probes": probe_reports + interface_probe_reports,
                    "exact_oracle": exact_ready,
                    "exact_oracle_after_cleanup": exact_after,
                    "factor_inventory": {
                        "ready": exact_ready.get("factor_count_ready"),
                        "after": exact_after.get("factor_count_after_cleanup"),
                        "simultaneous_max": exact_ready.get("factor_count_ready"),
                        "full_side": exact_ready.get("full_side_exact_factor_count", 0),
                        "global_direct": exact_ready.get(
                            "global_direct_factor_count", 0
                        ),
                        "nested_ksp": exact_ready.get("nested_ksp_count", 0),
                    },
                    "lifecycle": {
                        "exact_factor_count_ready": exact_ready.get(
                            "factor_count_ready"
                        ),
                        "exact_factor_count_after_cleanup": exact_after.get(
                            "factor_count_after_cleanup"
                        ),
                        "simultaneous_factor_count_max": exact_ready.get(
                            "factor_count_ready"
                        ),
                    },
                    "v1_2_gate": v1_2_gate,
                    "identity_observed": identity_observed,
                    "resource_observed": resource_observed,
                    "v1_3_conditional": projected_diagnostics,
                    "v1_3_factor_inventory": projected_inventory
                    if projected_action is not None
                    else None,
                    "v1_3_one_apply": projected_audit,
                    "v1_3_screen": projected_screen,
                },
                "source_loading": {
                    "rhs_vectors_loaded": len(TASK040_LEVEL_A_SOURCE_LABELS)
                    if projected_action is not None
                    else 0,
                    "exact_output_vectors_loaded": len(labels),
                    "exact_output_metadata_hash_validation_only": False,
                },
                "pde_solve": "not_run",
                "top": "not_run",
                "scalable_candidate": False,
            },
            "action": projected_action,
            "owner": projected_owner,
        }
        if producer_mode:
            route_result["result"]["interface_schur_raw"].update(
                {
                    "packet": packet_manifest,
                    "producer_route": True,
                    "additional_projected_matrices": {
                        "projected_middle_group_schur": middle_group_schur_metadata,
                    },
                }
            )
        owner_transferred = True
        return route_result
    finally:
        for vector in source_vectors.values():
            vector.destroy()
        for action in reversed(petrov_actions):
            action.destroy()
        if not owner_transferred:
            if projected_owner is not None:
                projected_owner.destroy()
                projected_owner = None
                projected_action = None
            elif projected_action is not None:
                projected_action.destroy()
                projected_action = None
        if oracle is not None:
            oracle.destroy()
        del spaces, cross_section


def _v2_packet_provenance(
    manifest: Mapping[str, Any],
    *,
    input_sha256: str,
    physical_model_sha256: str,
) -> dict[str, Any]:
    """Validate the producer identity without constructing its FEM objects."""

    provenance = manifest.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("V2 packet manifest has no producer provenance")
    expected = {
        "schema": TASK040_V2_INTERFACE_PACKET_SCHEMA,
        "input_sha256": str(input_sha256),
        "physical_model_sha256": str(physical_model_sha256),
        "selected_manifest_sha256": TASK040_V1_2_SELECTED_MANIFEST_SHA256,
        "exact_spool_catalog_sha256": TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256,
        "probe_manifest_sha256": TASK040_V1_2_PROBE_MANIFEST_SHA256,
        "qep_calls": 0,
        "pde_solve": "not_run",
        "v1_3_built": False,
    }
    if any(provenance.get(key) != value for key, value in expected.items()):
        raise ValueError("V2 packet producer provenance is not frozen")
    producer_source = provenance.get("source_sha")
    if (
        not isinstance(producer_source, str)
        or len(producer_source) != 40
        or any(character not in "0123456789abcdef" for character in producer_source)
    ):
        raise ValueError("V2 packet producer source SHA is invalid")
    return dict(provenance)


def _v2_packet_gamma_rows(
    supports: Sequence[Mapping[str, Any]],
    group_rows: Sequence[np.ndarray],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Select packet Gamma rows from the current owner-local group order."""

    lower = {int(row) for row in supports[0]["active_support"]}
    upper = {int(row) for row in supports[1]["active_support"]}
    if lower.intersection(upper):
        raise ValueError("V2 packet lower/upper Gamma supports overlap")
    expected = (lower, lower | upper, upper)
    result: list[np.ndarray] = []
    for group, rows in enumerate(group_rows):
        ordered = np.asarray(
            [int(row) for row in rows if int(row) in expected[group]],
            dtype=PETSc.IntType,
        )
        result.append(ordered)
    return result[0], result[1], result[2]


def _v3_packet_provenance(
    manifest: Mapping[str, Any],
    *,
    input_sha256: str,
    physical_model_sha256: str,
) -> dict[str, Any]:
    """Validate the immutable augmented V3-1 packet authority."""

    provenance = manifest.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("V3-2 augmented packet has no provenance")
    expected = {
        "schema": TASK040_V2_INTERFACE_PACKET_SCHEMA,
        "input_sha256": str(input_sha256),
        "physical_model_sha256": str(physical_model_sha256),
        "selected_manifest_sha256": TASK040_V1_2_SELECTED_MANIFEST_SHA256,
        "exact_spool_catalog_sha256": TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256,
        "probe_manifest_sha256": TASK040_V1_2_PROBE_MANIFEST_SHA256,
        "qep_calls": 0,
        "pde_solve": "not_run",
        "v1_3_built": False,
    }
    if any(provenance.get(key) != value for key, value in expected.items()):
        raise ValueError("V3-2 augmented packet provenance is not frozen")
    source = provenance.get("source_sha")
    if source != TASK040_V3_2_PRODUCER_SOURCE_SHA:
        raise ValueError("V3-2 augmented packet producer source is not frozen")
    return dict(provenance)


def _v4_spool_metadata_identity(
    spool: Mapping[str, Mapping[str, Any]],
    labels: Sequence[str],
    expected_ids: Mapping[str, str],
    *,
    expected_mpi_size: int,
) -> dict[str, Any]:
    observed: dict[str, str | None] = {}
    checks: dict[str, bool] = {}
    shard_counts: dict[str, int] = {}
    expected_mpi_size = int(expected_mpi_size)
    for label in labels:
        shards = spool.get(label, {}).get("exact_output", {}).get("shards", ())
        if not isinstance(shards, Sequence) or isinstance(shards, (str, bytes)):
            shards = ()
        identities = tuple(
            shard.get("source_identity", {})
            .get("vector_identity", {})
            .get("global_sha256")
            if isinstance(shard, Mapping)
            else None
            for shard in shards
        )
        shard_counts[label] = len(identities)
        value = identities[0] if identities and len(set(identities)) == 1 else None
        observed[label] = value
        checks[label] = bool(
            len(identities) == expected_mpi_size
            and value is not None
            and value == expected_ids[label]
        )
    return {
        "expected": dict(expected_ids),
        "expected_mpi_size": expected_mpi_size,
        "observed": observed,
        "shard_counts": shard_counts,
        "checks": checks,
        "pass": all(checks.values()),
        "array_hash_validation_only": True,
        "numeric_vectors_constructed": False,
        "values_retained": False,
    }


def _v4_spool_producer_source_identity(
    spool: Mapping[str, Mapping[str, Any]],
    labels: Sequence[str],
    *,
    expected_source_sha: str,
    expected_mpi_size: int,
) -> dict[str, Any]:
    per_entry: dict[str, dict[str, Any]] = {}
    observed: set[str] = set()
    expected_source_sha = str(expected_source_sha)
    expected_mpi_size = int(expected_mpi_size)
    for label in labels:
        for role in ("rhs", "exact_output"):
            role_record = spool.get(label, {}).get(role, {})
            shards = role_record.get("shards", ())
            if not isinstance(shards, Sequence) or isinstance(shards, (str, bytes)):
                shards = ()
            values: list[str | None] = []
            for shard in shards:
                source_identity = (
                    shard.get("source_identity") if isinstance(shard, Mapping) else None
                )
                packet_wrapper = (
                    source_identity.get("packet_identity")
                    if isinstance(source_identity, Mapping)
                    else None
                )
                value = (
                    packet_wrapper.get("source_sha")
                    if isinstance(packet_wrapper, Mapping)
                    else None
                )
                values.append(value if isinstance(value, str) else None)
                if isinstance(value, str):
                    observed.add(value)
            valid_values = [
                value
                for value in values
                if isinstance(value, str)
                and len(value) == 40
                and all(character in "0123456789abcdef" for character in value)
            ]
            shard_count = len(values)
            valid_source_sha_count = len(valid_values)
            expected_match_count = sum(value == expected_source_sha for value in values)
            per_entry[f"{label}:{role}"] = {
                "expected_mpi_size": expected_mpi_size,
                "shard_count": shard_count,
                "valid_source_sha_count": valid_source_sha_count,
                "expected_match_count": expected_match_count,
                "observed_source_shas": sorted(
                    {value for value in values if isinstance(value, str)}
                ),
                "check": bool(
                    shard_count == expected_mpi_size
                    and valid_source_sha_count == expected_mpi_size
                    and expected_match_count == expected_mpi_size
                    and all(value == expected_source_sha for value in values)
                ),
            }
    overall_pass = bool(
        len(per_entry) == 2 * len(tuple(labels))
        and all(item["check"] for item in per_entry.values())
    )
    return {
        "expected_source_sha": expected_source_sha,
        "expected_mpi_size": expected_mpi_size,
        "observed_source_sha": next(iter(observed)) if len(observed) == 1 else None,
        "observed_source_shas": sorted(observed),
        "per_label_role": per_entry,
        "pass": overall_pass,
    }


def _v4_identity_stop_result(
    *,
    source_sha: str,
    input_sha256: str,
    physical_model_sha256: str,
    identity: Mapping[str, Any],
    source_binding: Mapping[str, Any],
    labels: Sequence[str],
    resource_samples: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    audit = canonical_binding_failure_audit(
        identity=identity,
        source_binding=source_binding,
        labels=labels,
    )
    samples = dict(resource_samples or {})
    resource_authority = {
        "status": "not_run_by_identity_gate",
        "sample_count": len(samples),
        "all_status_readable": None,
        "swap_authority_readable": None,
        "swap_zero_authoritative": None,
    }
    audit["resource_authority"] = resource_authority
    factor_inventory = audit["factor_inventory"]
    failure_code = str(
        source_binding.get("failure_code", V4_CANONICAL_SOURCE_BINDING_UNAVAILABLE)
    )
    failure_reason = str(
        source_binding.get("reason", V4_CANONICAL_SOURCE_BINDING_REASON)
    )
    return {
        "action": None,
        "owner": None,
        "result": {
            "schema": TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_SCHEMA,
            "method": TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_METHOD,
            "profile": TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_PROFILE_ID,
            "source_sha": str(source_sha),
            "input_sha256": str(input_sha256),
            "physical_model_sha256": str(physical_model_sha256),
            "identity_observed": dict(identity),
            "identity_pass": False,
            "identity_failure_code": failure_code,
            "identity_failure_reason": failure_reason,
            "exact_authority": audit,
            "numerical_gate_pass": None,
            "residual_status": "not_run_by_identity_gate",
            "gate_pass": False,
            "classification": V4_EXACT_AUTHORITY_FAILURE,
            "source_loading": {
                "labels": list(labels),
                "rhs_vectors_loaded": 0,
                "exact_output_vectors_loaded": 0,
                "exact_output_metadata_hash_validation_only": True,
                "array_hash_validation_only": True,
                "numeric_vectors_constructed": False,
                "values_retained": False,
                "raw_global_row_remap_used": False,
                "canonical_reconstruction": "not_run_by_identity_gate",
            },
            "resource_samples": samples,
            "resource_authority": resource_authority,
            "factor_inventory": factor_inventory,
            "qep_calls": 0,
            "pde_solve": "not_run",
            "projection": "not_run_by_gate",
            "lift": "not_run_by_gate",
            "not_run_by_gate": dict(audit["downstream"]),
            "construction": {
                "system_created": False,
                "explicit_bare_f_created": False,
                "interface_masses_built": False,
                "qep_called": False,
                "pde_solved": False,
            },
        },
    }


def _v4_source_authority_preflight(
    *,
    exact_spool_root: str | Path,
    source_sha: str,
    input_sha256: str,
    physical_model_sha256: str,
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    """Validate source-row metadata before constructing the PDE system."""

    manifest_path, manifest = _v1_2_load_manifest()
    identity = manifest["identity"]
    labels = tuple(manifest["physical_probes"]["labels"])
    if labels != V4_EXACT_AUTHORITY_LABELS:
        raise ValueError("V4 exact authority manifest labels are not frozen")
    selected_manifest = (
        Path(__file__).resolve().parents[1] / identity["selected_manifest"]
    )
    selected_manifest_sha256 = hashlib.sha256(
        selected_manifest.read_bytes()
    ).hexdigest()
    resolved_path = Path(exact_spool_root).resolve().parent / "resolved_config.json"
    resolved_sha256 = hashlib.sha256(resolved_path.read_bytes()).hexdigest()
    packet_identity, packet_manifest_sha256, catalog = _v9_frozen_holdout_identity(
        exact_spool_root, comm
    )
    spool_catalog_sha256 = _v1_2_validate_spool_identity(
        selected_manifest_sha256=packet_manifest_sha256,
        catalog=catalog,
    )
    spool = _load_v5_fixed_budget_spool_shards(
        exact_spool_root,
        comm,
        packet_identity=packet_identity,
        manifest_sha256=packet_manifest_sha256,
    )
    source_binding = inspect_canonical_source_authority(spool, labels=labels)
    source_binding.update(
        {
            "array_hash_validation_only": True,
            "numeric_vectors_constructed": False,
            "values_retained": False,
            "raw_npy_mmap_hash_read": True,
        }
    )
    expected_ids = dict(manifest["physical_probes"]["exact_output_identity_sha256"])
    output_identity = _v4_spool_metadata_identity(
        spool,
        labels,
        expected_ids,
        expected_mpi_size=int(identity["mpi_size"]),
    )
    producer_identity = _v4_spool_producer_source_identity(
        spool,
        labels,
        expected_source_sha=str(identity["exact_spool_source_sha"]),
        expected_mpi_size=int(identity["mpi_size"]),
    )
    identity_checks = {
        "input_sha256": {
            "observed": str(input_sha256),
            "expected": str(identity["input_sha256"]),
            "pass": str(input_sha256) == str(identity["input_sha256"]),
        },
        "physical_model_sha256": {
            "observed": str(physical_model_sha256),
            "expected": str(identity["physical_model_sha256"]),
            "pass": str(physical_model_sha256)
            == str(identity["physical_model_sha256"]),
        },
        "frozen_branch": {
            "observed": manifest["freeze"]["branch"],
            "expected": TASK040_V4_FROZEN_BRANCH,
            "pass": manifest["freeze"]["branch"] == TASK040_V4_FROZEN_BRANCH,
        },
        "freeze_source": {
            "observed": manifest["freeze"]["source_sha_at_freeze"],
            "expected": TASK040_V4_FROZEN_AUTHORITY_SOURCE_SHA,
            "pass": manifest["freeze"]["source_sha_at_freeze"]
            == TASK040_V4_FROZEN_AUTHORITY_SOURCE_SHA,
        },
        "selected_manifest": {
            "observed_sha256": selected_manifest_sha256,
            "expected_sha256": identity["selected_manifest_sha256"],
            "frozen_sha256": TASK040_V1_2_SELECTED_MANIFEST_SHA256,
            "pass": bool(
                selected_manifest_sha256
                == identity["selected_manifest_sha256"]
                == TASK040_V1_2_SELECTED_MANIFEST_SHA256
            ),
        },
        "resolved_config": {
            "observed_sha256": resolved_sha256,
            "expected_sha256": identity["exact_spool_resolved_config_sha256"],
            "pass": resolved_sha256 == identity["exact_spool_resolved_config_sha256"],
        },
        "packet_manifest": {
            "observed_sha256": str(packet_manifest_sha256),
            "expected_sha256": str(identity["selected_manifest_sha256"]),
            "pass": str(packet_manifest_sha256)
            == str(identity["selected_manifest_sha256"]),
        },
        "spool_catalog": {
            "observed_sha256": str(spool_catalog_sha256),
            "expected_sha256": str(identity["exact_spool_catalog_sha256"]),
            "frozen_sha256": TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256,
            "pass": bool(
                str(spool_catalog_sha256)
                == str(identity["exact_spool_catalog_sha256"])
                == TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256
            ),
        },
        "spool_producer_source": producer_identity,
        "exact_output_metadata": output_identity,
        "canonical_source_binding": source_binding,
    }
    identity_failures = [
        name for name, check in identity_checks.items() if check.get("pass") is not True
    ]
    identity_observed = {
        "source_sha": str(source_sha),
        "current_source_sha": str(source_sha),
        "spool_producer_source_sha": producer_identity["observed_source_sha"],
        "spool_producer_source_identity": producer_identity,
        "input_sha256": str(input_sha256),
        "physical_model_sha256": str(physical_model_sha256),
        "frozen_branch": manifest["freeze"]["branch"],
        "task040_manifest_freeze_source_sha": manifest["freeze"][
            "source_sha_at_freeze"
        ],
        "probe_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "selected_manifest_sha256": selected_manifest_sha256,
        "spool_packet_manifest_sha256": str(packet_manifest_sha256),
        "resolved_config_sha256": resolved_sha256,
        "spool_catalog_sha256": spool_catalog_sha256,
        "identity_checks": identity_checks,
        "identity_failures": identity_failures,
        "identity_checks_pass": not identity_failures,
        "packet_identity": dict(packet_identity),
        "labels": list(labels),
        "exact_output_metadata_identity": output_identity,
        "source_canonical_authority": source_binding,
        "source_ownership": {
            label: {
                role: source_binding["entries"]
                .get(label, {})
                .get(role, {})
                .get("ownership_ranges", [])
                for role in ("rhs", "exact_output")
            }
            for label in labels
        },
        "probe_authority": dict(manifest["physical_probes"]["probe_identities"]),
        "system_inventory": {
            "system_created": False,
            "explicit_bare_f_created": False,
        },
    }
    if source_binding["bridge_qualified"]:
        raise RuntimeError(
            "V4 canonical bridge reports qualified without an implemented loader"
        )
    return _v4_identity_stop_result(
        source_sha=source_sha,
        input_sha256=input_sha256,
        physical_model_sha256=physical_model_sha256,
        identity=identity_observed,
        source_binding=source_binding,
        labels=labels,
    )


def _v3_matrix_hash(matrix: np.ndarray) -> str:
    return hashlib.sha256(
        np.ascontiguousarray(np.asarray(matrix, dtype=np.complex128)).tobytes()
    ).hexdigest()


def _v3_validate_joint_matrix(
    middle: np.ndarray, legacy_group1: np.ndarray
) -> tuple[np.ndarray, dict[str, Any]]:
    middle = np.asarray(middle)
    legacy_group1 = np.asarray(legacy_group1)
    if (
        middle.dtype != np.dtype(np.complex128)
        or legacy_group1.dtype != np.dtype(np.complex128)
        or middle.shape != (776, 776)
        or legacy_group1.shape != (776, 776)
    ):
        raise ValueError("V3-2 augmented matrices must be complex128 776x776")
    if not np.isfinite(middle).all() or not np.isfinite(legacy_group1).all():
        raise ValueError("V3-2 augmented matrices are nonfinite")
    joint = middle + legacy_group1
    singular_values = np.linalg.svd(joint, compute_uv=False)
    rank = int(np.linalg.matrix_rank(joint))
    condition = float(singular_values[0] / singular_values[-1])
    blocks = {
        "LL": joint[:296, :296],
        "LU": joint[:296, 296:],
        "UL": joint[296:, :296],
        "UU": joint[296:, 296:],
    }
    block_diagnostics = {
        name: {
            "shape": list(block.shape),
            "norm": float(np.linalg.norm(block)),
            "rank": int(np.linalg.matrix_rank(block)),
            "sha256": _v3_matrix_hash(block),
        }
        for name, block in blocks.items()
    }
    if any(value["norm"] <= 0.0 for value in block_diagnostics.values()):
        raise ValueError("V3-2 augmented joint matrix has an empty block")
    if rank != 776 or not np.isfinite(condition) or condition > 1.0e12:
        raise ValueError("V3-2 augmented joint matrix rank/condition Gate failed")
    observed = {
        "shape": [776, 776],
        "rank": rank,
        "condition": condition,
        "sigma_max": float(singular_values[0]),
        "sigma_min": float(singular_values[-1]),
        "content_sha256": _v3_matrix_hash(joint),
        "blocks": block_diagnostics,
        "legacy_group1_semantic": "blockdiag(S0,S2)",
        "joint_semantic": "projected_middle_group_schur + legacy projected_exact_group1",
    }
    if observed["content_sha256"] != TASK040_V3_2_TRUE_JOINT_CONTENT_SHA256:
        raise ValueError("V3-2 augmented joint content hash mismatch")
    return joint, observed


def _run_v3_2_coupled_interface_consumer(
    *,
    cfg: Any,
    system: Any,
    bare_f: PETSc.Mat,
    source_sha: str,
    input_sha256: str,
    physical_model_sha256: str,
    group_rows: Sequence[np.ndarray],
    group_audit: Mapping[str, Any],
    supports: Sequence[Mapping[str, Any]],
    masses: Sequence[Any],
    exact_spool_root: str | Path,
    beta: complex,
    packet_root: str | Path,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None,
    resource_callback: Callable[[], Mapping[str, Any]] | None,
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    """Hydrate the augmented packet into the full-side PETSc carrier."""

    packet_layouts: tuple[Any, Any, Any] | None = None
    source_vectors: dict[str, PETSc.Vec] = {}
    action: Any | None = None
    owner_transferred = False
    raw_basis: Any | None = None
    canonical_basis: CanonicalOwnerLocalBasis | None = None
    lower: dict[str, Any] | None = None
    upper: dict[str, Any] | None = None
    local_y: np.ndarray | None = None
    local_z: np.ndarray | None = None
    layout_summary: dict[str, Any] | None = None
    packet_gram_sha256: str | None = None
    bare_f_hash_before = _petsc_matrix_hash(bare_f)
    try:
        _, probe_manifest = _v1_2_load_manifest()
        identity = probe_manifest["identity"]
        selected_manifest = (
            Path(__file__).resolve().parents[1] / identity["selected_manifest"]
        )
        selected_sha = hashlib.sha256(selected_manifest.read_bytes()).hexdigest()
        if selected_sha != TASK040_V1_2_SELECTED_MANIFEST_SHA256:
            raise ValueError("V3-2 selected mode manifest hash mismatch")
        selected_payload = json.loads(selected_manifest.read_text(encoding="utf-8"))
        selected_identity = json.loads(
            selected_manifest.with_name("identity.json").read_text(encoding="utf-8")
        )
        if (
            selected_payload.get("identity_sha256")
            != identity["selected_identity_sha256"]
        ):
            raise ValueError("V3-2 selected identity mismatch")
        if (
            selected_payload.get("selection_sha256")
            != identity["selected_selection_sha256"]
        ):
            raise ValueError("V3-2 selected selection mismatch")
        resolved_path = Path(exact_spool_root).resolve().parent / "resolved_config.json"
        resolved = json.loads(resolved_path.read_text(encoding="utf-8"))
        resolved_modes = resolved["derived"]["external_mode_inventory"]
        lower_authority = {
            **resolved_modes,
            "keys": tuple(
                key for key in resolved_modes["keys"] if str(key["side"]) == "bottom"
            ),
            "modes": tuple(
                mode
                for mode in resolved_modes["modes"]
                if str(mode["side"]) == "bottom"
            ),
            "count": _v1_2_lower_mode_count(resolved_modes),
            "canonical_key_list_sha256": probe_manifest["lower_fourier_floquet_basis"][
                "canonical_key_list_sha256"
            ],
            "beta_metadata_sha256": probe_manifest["lower_fourier_floquet_basis"][
                "beta_metadata_sha256"
            ],
        }
        if (
            hashlib.sha256(resolved_path.read_bytes()).hexdigest()
            != identity["exact_spool_resolved_config_sha256"]
        ):
            raise ValueError("V3-2 lower resolved mode authority hash mismatch")

        z_values = system.local_mesh.z_values
        packet_gamma_rows = _v2_packet_gamma_rows(supports, group_rows)
        packet_layouts = _v2_build_packet_layouts(
            system=system,
            condensed=system.static_condensation.condensed,
            supports=supports,
            gamma_rows=packet_gamma_rows,
            lower_z=float(z_values[2]),
            upper_z=float(z_values[4]),
            comm=comm,
        )
        layout = packet_layouts[1]
        layout_summary = {
            "audit": dict(layout.audit),
            "local_row_count": int(len(layout.gamma_rows_local)),
            "global_row_count": int(layout.audit["global_row_count"]),
            "canonical_key_order_sha256": canonical_key_sha256(layout.canonical_keys),
        }
        _emit(
            marker_callback,
            "v3_packet_group_load_begin",
            group=1,
            local_rows=len(layout.gamma_rows_local),
            span_size=776,
        )
        loaded = load_packet_shard(
            packet_root,
            groups=("group1",),
            expected_manifest_sha256=TASK040_V3_2_AUGMENTED_PACKET_MANIFEST_SHA256,
            comm=comm,
        )
        manifest = loaded["manifest"]
        provenance = _v3_packet_provenance(
            manifest,
            input_sha256=input_sha256,
            physical_model_sha256=physical_model_sha256,
        )
        if (
            manifest.get("basis_global_replicated") is not False
            or manifest.get("fe_numeric_allgather") is not False
        ):
            raise ValueError("V3-2 packet numeric replication flags are invalid")
        if int(manifest["groups"]["group1"]["global_count"]) != int(
            layout.audit["global_row_count"]
        ):
            raise ValueError("V3-2 packet group1 Gamma count differs from fresh layout")
        middle = load_small_matrix(packet_root, "projected_middle_group_schur")
        legacy_group1 = load_small_matrix(packet_root, "projected_exact_group1")
        gram = load_small_matrix(packet_root, "gram_group1")
        packet_gram_sha256 = _v3_matrix_hash(gram)
        joint, joint_diagnostics = _v3_validate_joint_matrix(middle, legacy_group1)
        if gram.shape != (776, 776) or not np.isfinite(gram).all():
            raise ValueError("V3-2 packet group1 Gram is invalid")
        _emit(
            marker_callback,
            "v3_packet_group_load_ready",
            group=1,
            local_rows=len(layout.gamma_rows_local),
            span_size=776,
            manifest_sha256=loaded["manifest_sha256"],
        )

        packet_group = loaded["groups"]["group1"]
        redistributed, redistribution_audit = redistribute_packet_group_rows(
            packet_group, layout.canonical_keys, comm=comm
        )
        _emit(
            marker_callback,
            "v3_packet_owner_redistribute_ready",
            group=1,
            **redistribution_audit,
        )
        canonical_basis = CanonicalOwnerLocalBasis(
            redistributed.keys, redistributed.U, redistributed.V
        )
        raw_basis = reconstruct_owner_local_basis(
            layout,
            canonical_basis.keys,
            canonical_basis.U,
            canonical_basis.V,
        )
        remap_audit = audit_owner_local_basis_round_trip(
            layout, raw_basis.U, raw_basis.V, canonical_basis
        )
        collective_remap_error = float(
            comm.allreduce(float(remap_audit["max_relative_error"]), op=MPI.MAX)
        )
        if not remap_audit["pass"] or collective_remap_error > 1.0e-12:
            raise ValueError("V3-2 packet canonical remap Gate failed")
        _emit(
            marker_callback,
            "v3_packet_roundtrip_ready",
            group=1,
            max_relative_error=collective_remap_error,
        )

        local_v = raw_basis.V
        local_y = recover_owner_local_y_from_packet_v(local_v, gram)
        del local_v, raw_basis, canonical_basis, redistributed, packet_group, loaded
        raw_basis = None
        canonical_basis = None

        cross_section = build_matching_cross_section(cfg, "stage4_xy", comm=comm)
        spaces = build_cross_section_spaces(
            cross_section, transverse_degree=int(cfg.nedelec_degree)
        )
        condensed = system.static_condensation.condensed
        lower = _v1_2_build_lower_basis(
            cfg=cfg,
            system=system,
            spaces=spaces,
            condensed=condensed,
            support=supports[0],
            gamma_rows_local=packet_gamma_rows[0],
            interface_z=float(z_values[2]),
            authority=lower_authority,
        )
        upper = _v1_2_build_upper_basis(
            system=system,
            spaces=spaces,
            condensed=condensed,
            support=supports[1],
            gamma_rows_local=packet_gamma_rows[2],
            interface_z=float(z_values[4]),
            selected_manifest=selected_manifest,
            selected_identity=selected_identity,
            selected_payload=selected_payload,
            expected_mode_key_sha256=probe_manifest["upper_selected_packet_basis"][
                "positive_mode_keys_sha256"
            ],
            expected_beta_sha256=probe_manifest["upper_selected_packet_basis"][
                "positive_beta_sha256"
            ],
            comm=comm,
        )
        local_z = build_group_basis_columns(
            1,
            packet_gamma_rows[1],
            packet_gamma_rows[0],
            lower["values"],
            packet_gamma_rows[2],
            upper["right"],
        )
        if (
            local_y.shape != local_z.shape
            or not np.isfinite(local_y).all()
            or not np.isfinite(local_z).all()
        ):
            raise ValueError("V3-2 reconstructed owner-local Z/Y shape is invalid")
        lower_span = int(lower["left"].shape[1])
        upper_span = int(upper["left"].shape[1])
        local_gram = local_y.conj().T @ local_z
        cross_gram = np.empty_like(local_gram)
        comm.Allreduce(local_gram, cross_gram, op=MPI.SUM)
        local_z, transfer_diagnostics = transfer_right_basis_to_packet_gram(
            gram,
            cross_gram,
            local_z,
            lower_span=lower_span,
            upper_span=upper_span,
        )
        gram_relative_error = float(transfer_diagnostics["post_gram_relative_error"])
        gram_block_relative_errors = dict(
            transfer_diagnostics["post_block_relative_errors"]
        )
        observed_gram_sha256 = str(transfer_diagnostics["post_gram_sha256"])
        y_authority = str(transfer_diagnostics["y_authority"])
        _emit(
            marker_callback,
            "v3_z_y_gram_audit",
            cross_gram=transfer_diagnostics["cross_gram"],
            right_transfer=transfer_diagnostics["right_transfer"],
            gram_relative_error=gram_relative_error,
            gram_block_relative_errors=gram_block_relative_errors,
            packet_gram_sha256=packet_gram_sha256,
            recomputed_gram_sha256=observed_gram_sha256,
            y_authority=y_authority,
            z_authority=transfer_diagnostics["z_authority"],
        )
        if not np.isfinite(gram_relative_error) or gram_relative_error > 1.0e-10:
            raise ValueError(
                "V3-2 packet-dual right-transfer Gram differs from packet Gram: "
                f"relative={gram_relative_error!r}, "
                f"blocks={gram_block_relative_errors!r}, "
                f"packet_sha={packet_gram_sha256}, observed_sha={observed_gram_sha256}, "
                f"y_authority={y_authority}"
            )
        _emit(
            marker_callback,
            "v3_z_y_reconstruct_ready",
            local_rows=int(local_z.shape[0]),
            span_size=776,
            gram_relative_error=gram_relative_error,
            gram_sha256=observed_gram_sha256,
            gram_block_relative_errors=gram_block_relative_errors,
            y_authority=y_authority,
            z_authority=transfer_diagnostics["z_authority"],
            right_transfer=transfer_diagnostics,
        )
        del lower, upper, spaces, cross_section, middle, legacy_group1, gram
        lower = None
        upper = None
        packet_layouts = None

        action = build_petsc_coupled_full_side_action(
            bare_f=bare_f,
            group_rows=group_rows,
            lower_support=packet_gamma_rows[0],
            upper_support=packet_gamma_rows[2],
            gamma_rows_local=packet_gamma_rows[1],
            local_z=local_z,
            local_y=local_y,
            joint_matrix=joint,
            factor_solver_type="mumps",
        )
        del local_z, local_y, joint
        local_z = None
        local_y = None
        ready_diagnostics = dict(action.diagnostics)
        factor_inventory = {
            "cross_section_group_factor_count": ready_diagnostics[
                "cross_section_group_factor_count"
            ],
            "exact_interface_schur_oracle_object_count": 0,
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "reduced_dense_factor_count": ready_diagnostics[
                "reduced_dense_factor_count"
            ],
            "nested_ksp_count": 0,
            "packet_dependent": True,
            "pass": bool(
                ready_diagnostics["cross_section_group_factor_count"] == 3
                and ready_diagnostics["reduced_dense_factor_count"] == 1
                and ready_diagnostics["exact_interface_schur_oracle_object_count"] == 0
                and ready_diagnostics["full_side_exact_factor_count"] == 0
                and ready_diagnostics["global_direct_factor_count"] == 0
                and ready_diagnostics.get("nested_ksp_count", 0) == 0
            ),
        }
        if not factor_inventory["pass"]:
            raise RuntimeError("V3-2 carrier factor inventory is invalid")
        packet_identity, selected_manifest_sha, catalog = _v9_frozen_holdout_identity(
            exact_spool_root, comm
        )
        catalog_sha = _v1_2_validate_spool_identity(
            selected_manifest_sha256=selected_manifest_sha, catalog=catalog
        )
        spool = _load_v5_fixed_budget_spool_shards(
            exact_spool_root,
            comm,
            packet_identity=packet_identity,
            manifest_sha256=selected_manifest_sha,
        )
        for label in TASK040_LEVEL_A_SOURCE_LABELS:
            template = bare_f.createVecLeft()
            try:
                source_vectors[label] = _load_v5_blr_reference_spool_remapped(
                    spool[label]["rhs"], template
                )
            finally:
                template.destroy()
        del spool
        scalar_labels = tuple(TASK040_LEVEL_A_SOURCE_LABELS[1:])
        zero_output = bare_f.createVecLeft()
        try:
            physical_source = source_vectors[TASK040_LEVEL_A_SOURCE_LABELS[0]]
            action.apply(physical_source, zero_output)
            physical_source_norm = float(physical_source.norm())
            physical_output_norm = float(zero_output.norm())
            zero_map = {
                "label": TASK040_LEVEL_A_SOURCE_LABELS[0],
                "source_norm": physical_source_norm,
                "output_norm": physical_output_norm,
                "physical_zero": bool(
                    np.isfinite(physical_source_norm)
                    and np.isfinite(physical_output_norm)
                    and physical_source_norm <= 1.0e-13
                    and physical_output_norm <= 1.0e-13
                ),
                "finite": bool(
                    np.isfinite(physical_source_norm)
                    and np.isfinite(physical_output_norm)
                ),
            }
        finally:
            zero_output.destroy()
        one_apply = audit_v3_full_side_one_apply(
            action,
            bare_f,
            {label: source_vectors[label] for label in scalar_labels},
            labels=scalar_labels,
            factor_inventory=factor_inventory,
        )
        one_apply["physical_zero_report"] = zero_map
        one_apply["physical_zero_pass"] = zero_map["physical_zero"] is True
        one_apply["source_reports_finite"] = all(
            report.get("finite") is True for report in one_apply["reports"]
        )
        coarse_history = action.diagnostics["coarse_residual_history"]
        one_apply["coarse_residual_finite"] = bool(coarse_history) and all(
            row.get("finite") is True for row in coarse_history
        )
        one_apply["action_identity_pass"] = bool(
            one_apply["zero_map_pass"] is True
            and one_apply["physical_zero_pass"] is True
            and one_apply["source_reports_finite"] is True
            and one_apply["repeat_pass"] is True
            and one_apply["linearity_pass"] is True
            and one_apply["factor_inventory_pass"] is True
            and one_apply["coarse_residual_finite"] is True
        )
        if not one_apply["action_identity_pass"]:
            raise RuntimeError("V3-2 one-apply action identity Gate failed")
        screen = run_v3_full_span_right_fgmres_batch(
            bare_f,
            {label: source_vectors[label] for label in scalar_labels},
            action,
            labels=scalar_labels,
            resource_callback=resource_callback,
            checkpoint_callback=lambda row: _emit(
                marker_callback, "v3_fgmres_checkpoint", **dict(row)
            ),
        )
        _emit(
            marker_callback,
            "v3_coupled_screen_complete",
            first_preferred_checkpoint=screen["first_preferred_checkpoint"],
            conditional_32_authorized=screen["conditional_32_authorized"],
            conditional_64_authorized=screen["conditional_64_authorized"],
        )
        bare_f_hash_after = _petsc_matrix_hash(bare_f)
        if bare_f_hash_after != bare_f_hash_before:
            raise RuntimeError("V3-2 bare F changed during coupled screen")
        result = {
            "schema": TASK040_V3_2_COUPLED_INTERFACE_SCHEMA,
            "method": TASK040_V3_2_COUPLED_INTERFACE_METHOD,
            "profile": TASK040_V3_2_COUPLED_INTERFACE_PROFILE_ID,
            "source_sha": str(source_sha),
            "input_sha256": str(input_sha256),
            "physical_model_sha256": str(physical_model_sha256),
            "packet_manifest_sha256": TASK040_V3_2_AUGMENTED_PACKET_MANIFEST_SHA256,
            "packet_producer_source_sha": provenance["source_sha"],
            "true_joint_content_sha256": TASK040_V3_2_TRUE_JOINT_CONTENT_SHA256,
            "selected_manifest_sha256": selected_manifest_sha,
            "exact_spool_catalog_sha256": catalog_sha,
            "rhs_vectors_loaded": len(TASK040_LEVEL_A_SOURCE_LABELS),
            "exact_output_vectors_loaded": 0,
            "pde_solve": "not_run",
            "qep_calls": 0,
            "coupled_interface_raw": {
                "packet_dependent": True,
                "producer_source_sha": provenance["source_sha"],
                "packet_manifest_sha256": TASK040_V3_2_AUGMENTED_PACKET_MANIFEST_SHA256,
                "joint": joint_diagnostics,
                "group_audit": dict(group_audit),
                "interface_masses": [dict(mass.audit) for mass in masses],
                "beta": {
                    "formula": "cfg.k0 * complex(cfg.substrate_index)",
                    "value": [float(beta.real), float(beta.imag)],
                    "q": [float((-1j * beta).real), float((-1j * beta).imag)],
                    "authority": TASK040_LEVEL_A_BETA_AUTHORITY,
                },
                "bare_f_identity": {
                    "before": bare_f_hash_before,
                    "after": bare_f_hash_after,
                    "unchanged": True,
                },
                "group1_remap": {
                    "audit": remap_audit,
                    "collective_max_relative_error": collective_remap_error,
                },
                "z_reconstruction": {
                    "source": "frozen_lower_fourier_and_upper_selected_authority",
                    "qep_calls": 0,
                    "lower_mode_key_sha256": probe_manifest[
                        "lower_fourier_floquet_basis"
                    ]["canonical_key_list_sha256"],
                    "lower_beta_sha256": lower_authority["beta_metadata_sha256"],
                    "upper_mode_key_sha256": probe_manifest[
                        "upper_selected_packet_basis"
                    ]["positive_mode_keys_sha256"],
                    "upper_beta_sha256": probe_manifest["upper_selected_packet_basis"][
                        "positive_beta_sha256"
                    ],
                    "gram_relative_error": gram_relative_error,
                    "packet_gram_sha256": packet_gram_sha256,
                    "recomputed_gram_sha256": observed_gram_sha256,
                    "gram_block_relative_errors": gram_block_relative_errors,
                    "y_authority": y_authority,
                    "z_authority": transfer_diagnostics["z_authority"],
                    "right_transfer": transfer_diagnostics,
                    "layout_summary": layout_summary,
                },
                "one_apply": one_apply,
                "fgmres_screen": screen,
                "factor_inventory": factor_inventory,
                "lifecycle": {
                    "factor_count_ready": 3,
                    "reduced_dense_factor_count_ready": 1,
                    "exact_interface_schur_oracle_object_count": 0,
                    "full_side_exact_factor_count": 0,
                    "global_direct_factor_count": 0,
                    "nested_ksp_count": 0,
                    "action_destroyed": False,
                    "factor_destroyed": False,
                },
                "basis_global_replicated": False,
                "fe_numeric_allgather": False,
                "forbidden_routes": [
                    "exact_interface_oracle",
                    "exact_output_vector_load",
                    "qep",
                    "pde_solve",
                    "recovery",
                    "top",
                    "full_hybrid",
                    "response_packet",
                    "global_hybrid_outer_ksp",
                    "full_side_factor",
                ],
            },
        }
        owner_transferred = True
        return {"action": None, "owner": action, "result": result}
    finally:
        for vector in source_vectors.values():
            vector.destroy()
        if not owner_transferred and action is not None:
            action.destroy()
        if raw_basis is not None:
            del raw_basis
        if canonical_basis is not None:
            del canonical_basis
        if lower is not None:
            del lower
        if upper is not None:
            del upper
        if local_y is not None:
            del local_y
        if local_z is not None:
            del local_z
        packet_layouts = None


def _run_v2_packet_consumer(
    *,
    system: Any,
    bare_f: PETSc.Mat,
    source_sha: str,
    input_sha256: str,
    physical_model_sha256: str,
    group_rows: Sequence[np.ndarray],
    group_audit: Mapping[str, Any],
    supports: Sequence[Mapping[str, Any]],
    masses: Sequence[Any],
    exact_spool_root: str | Path,
    beta: complex,
    packet_root: str | Path,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None,
    resource_callback: Callable[[], Mapping[str, Any]] | None,
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    """Hydrate one reviewed packet into the existing Level-A projected sweep."""

    packet_layouts: tuple[Any, Any, Any] | None = None
    gamma_factors: list[dict[str, np.ndarray]] = []
    source_vectors: dict[str, PETSc.Vec] = {}
    action: Any | None = None
    owner: Any | None = None
    owner_transferred = False
    remap_reports: list[dict[str, Any]] = []
    manifest: dict[str, Any] | None = None
    provenance: dict[str, Any] | None = None
    packet_manifest_sha256: str | None = None
    try:
        z_values = system.local_mesh.z_values
        packet_gamma_rows = _v2_packet_gamma_rows(supports, group_rows)
        packet_layouts = _v2_build_packet_layouts(
            system=system,
            condensed=system.static_condensation.condensed,
            supports=supports,
            gamma_rows=packet_gamma_rows,
            lower_z=float(z_values[2]),
            upper_z=float(z_values[4]),
            comm=comm,
        )
        manifest_group_diagnostics = None
        for group in range(3):
            name = f"group{group}"
            layout = packet_layouts[group]
            load_started = time.perf_counter()
            _v2_group_marker(
                marker_callback,
                "packet_group_load_begin",
                group=group,
                layout=layout,
                span_size=None,
                comm=comm,
            )
            loaded = load_packet_shard(
                packet_root,
                groups=(name,),
                expected_manifest_sha256=(TASK040_V2_INTERFACE_PACKET_MANIFEST_SHA256),
                comm=comm,
            )
            packet_group: PacketGroup | None = None
            group_descriptor: Mapping[str, Any] | None = None
            group_diagnostic: Mapping[str, Any] | None = None
            expected_count = -1
            span_size: int | None = None
            local_error: str | None = None
            try:
                if manifest is None:
                    manifest = loaded["manifest"]
                    packet_manifest_sha256 = str(loaded["manifest_sha256"])
                    provenance = _v2_packet_provenance(
                        manifest,
                        input_sha256=input_sha256,
                        physical_model_sha256=physical_model_sha256,
                    )
                    diagnostics_groups = manifest.get("diagnostics", {}).get("groups")
                    if (
                        not isinstance(diagnostics_groups, list)
                        or len(diagnostics_groups) != 3
                    ):
                        raise ValueError(
                            "V2 packet diagnostics have no three group records"
                        )
                    manifest_group_diagnostics = tuple(diagnostics_groups)
                packet_group = loaded["groups"].get(name)
                if packet_group is None:
                    raise ValueError(f"V2 packet did not load {name}")
                group_descriptor = manifest["groups"].get(name)
                group_diagnostic = manifest_group_diagnostics[group]
                expected_count = int(group_descriptor["global_count"])
                if int(layout.audit["global_row_count"]) != expected_count:
                    raise ValueError(
                        f"V2 packet {name} Gamma count differs from current layout"
                    )
                span_size = int(packet_group.U.shape[1])
                if int(group_diagnostic.get("span_size", span_size)) != span_size:
                    raise ValueError(
                        f"V2 packet {name} span size differs from manifest"
                    )
            except Exception as exc:
                local_error = f"{type(exc).__name__}: {exc}"
            _v2_collective_stage_error(comm, "packet_group_descriptor", local_error)
            assert packet_group is not None
            assert group_descriptor is not None
            assert group_diagnostic is not None
            assert span_size is not None
            _v2_group_marker(
                marker_callback,
                "packet_group_load_ready",
                group=group,
                layout=layout,
                span_size=span_size,
                comm=comm,
                started=load_started,
                global_row_count=expected_count,
            )

            redistribution_started = time.perf_counter()
            _v2_group_marker(
                marker_callback,
                "packet_group_owner_redistribute_begin",
                group=group,
                layout=layout,
                span_size=span_size,
                comm=comm,
                source_local_rows=int(packet_group.U.shape[0]),
                target_local_rows=len(layout.canonical_keys),
            )
            try:
                redistributed_group, redistribution_audit = (
                    redistribute_packet_group_rows(
                        packet_group,
                        layout.canonical_keys,
                        comm=comm,
                    )
                )
            except Exception as exc:
                raise RuntimeError(
                    f"V2 packet stage packet_group_owner_redistribute failed: {exc}"
                ) from exc
            redistribution_marker = dict(redistribution_audit)
            redistribution_marker.pop("span_size", None)
            _v2_group_marker(
                marker_callback,
                "packet_group_owner_redistribute_ready",
                group=group,
                layout=layout,
                span_size=span_size,
                comm=comm,
                started=redistribution_started,
                **redistribution_marker,
            )
            del packet_group, loaded

            reconstruct_started = time.perf_counter()
            _v2_group_marker(
                marker_callback,
                "packet_group_reconstruct_begin",
                group=group,
                layout=layout,
                span_size=span_size,
                comm=comm,
            )
            canonical_basis: CanonicalOwnerLocalBasis | None = None
            raw_basis: Any | None = None
            local_error = None
            try:
                canonical_basis = CanonicalOwnerLocalBasis(
                    tuple(redistributed_group.keys),
                    redistributed_group.U,
                    redistributed_group.V,
                )
                raw_basis = reconstruct_owner_local_basis(
                    layout,
                    canonical_basis.keys,
                    canonical_basis.U,
                    canonical_basis.V,
                )
            except Exception as exc:
                local_error = f"{type(exc).__name__}: {exc}"
            _v2_collective_stage_error(comm, "packet_group_reconstruct", local_error)
            assert canonical_basis is not None
            assert raw_basis is not None
            _v2_group_marker(
                marker_callback,
                "packet_group_reconstruct_ready",
                group=group,
                layout=layout,
                span_size=span_size,
                comm=comm,
                started=reconstruct_started,
            )

            audit_started = time.perf_counter()
            _v2_group_marker(
                marker_callback,
                "packet_group_roundtrip_audit_begin",
                group=group,
                layout=layout,
                span_size=span_size,
                comm=comm,
            )
            audit: dict[str, Any] | None = None
            local_error = None
            try:
                audit = audit_owner_local_basis_round_trip(
                    layout,
                    raw_basis.U,
                    raw_basis.V,
                    canonical_basis,
                )
            except Exception as exc:
                local_error = f"{type(exc).__name__}: {exc}"
            _v2_collective_stage_error(
                comm, "packet_group_roundtrip_audit", local_error
            )
            assert audit is not None
            global_error = float(
                comm.allreduce(float(audit["max_relative_error"]), op=MPI.MAX)
            )
            _v2_group_marker(
                marker_callback,
                "packet_group_roundtrip_audit_ready",
                group=group,
                layout=layout,
                span_size=span_size,
                comm=comm,
                started=audit_started,
                collective_max_relative_error=global_error,
            )
            local_error = None
            if not bool(audit["pass"]) or global_error > 1.0e-12:
                local_error = (
                    f"{name} canonical remap exceeds tolerance ({global_error:.17g})"
                )
            _v2_collective_stage_error(
                comm, "packet_group_collective_remap", local_error
            )
            remap_reports.append(
                {
                    "group": group,
                    "global_row_count": expected_count,
                    "span_size": span_size,
                    "local_row_count": int(layout.audit["local_row_count"]),
                    "local": audit,
                    "owner_redistribution": redistribution_audit,
                    "collective_max_relative_error": global_error,
                    "pass": bool(audit["pass"] and global_error <= 1.0e-12),
                }
            )
            gamma_factors.append({"U": raw_basis.U, "V": raw_basis.V})
            _v2_group_marker(
                marker_callback,
                "packet_group_collective_remap_ready",
                group=group,
                layout=layout,
                span_size=span_size,
                comm=comm,
                collective_max_relative_error=global_error,
            )
            del raw_basis, canonical_basis, redistributed_group

        if manifest is None or provenance is None:
            raise RuntimeError("V2 packet did not provide a manifest")
        if (
            manifest.get("basis_global_replicated") is not False
            or manifest.get("fe_numeric_allgather") is not False
        ):
            raise ValueError("V2 packet numeric replication flags are invalid")
        if packet_manifest_sha256 is None:
            raise RuntimeError("V2 packet manifest SHA was not observed")
        packet_layouts = None
        _emit(marker_callback, "projected_setup_begin", group_count=3)
        action, owner, projected_diagnostics = build_v2_packet_projected_transmission(
            bare_f=bare_f,
            group_rows=list(group_rows),
            interface_masses=list(masses),
            beta=beta,
            group_audit=dict(group_audit),
            gamma_rows=list(packet_gamma_rows),
            gamma_factors=gamma_factors,
        )
        projected_required = {
            "projected_factor_count_ready": 3,
            "exact_interface_oracle_factor_count": 0,
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
            "oracle_only": True,
            "scalable_candidate": False,
            "fe_numeric_allgather": False,
        }
        if any(
            projected_diagnostics.get(key) != value
            for key, value in projected_required.items()
        ):
            raise RuntimeError("V2 consumer projected diagnostics failed")
        _emit(
            marker_callback,
            "projected_setup_ready",
            factor_count_ready=projected_diagnostics["projected_factor_count_ready"],
        )
        gamma_factors.clear()
        ready_owner = dict(owner.diagnostics)
        factor_inventory = {
            "observed": True,
            "factor_count_ready": int(ready_owner.get("factor_count_ready", -1)),
            "cross_section_factor_count_ready": int(
                ready_owner.get("factor_count_ready", -1)
            ),
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
            "exact_interface_oracle_factor_count": 0,
            "oracle_only": True,
            "scalable_candidate": False,
        }
        if factor_inventory["factor_count_ready"] != 3:
            raise RuntimeError("V2 consumer projected factor inventory is not three")

        packet_identity, selected_manifest_sha, catalog = _v9_frozen_holdout_identity(
            exact_spool_root, comm
        )
        catalog_sha = _v1_2_validate_spool_identity(
            selected_manifest_sha256=selected_manifest_sha,
            catalog=catalog,
        )
        spool = _load_v5_fixed_budget_spool_shards(
            exact_spool_root,
            comm,
            packet_identity=packet_identity,
            manifest_sha256=selected_manifest_sha,
        )
        for label in TASK040_LEVEL_A_SOURCE_LABELS:
            template = bare_f.createVecLeft()
            try:
                source_vectors[label] = _load_v5_blr_reference_spool_remapped(
                    spool[label]["rhs"], template
                )
            finally:
                template.destroy()
        del spool
        _emit(
            marker_callback,
            "source_ready",
            labels=list(TASK040_LEVEL_A_SOURCE_LABELS),
            rhs_vectors_loaded=len(TASK040_LEVEL_A_SOURCE_LABELS),
            exact_output_vectors_loaded=0,
            exact_output_metadata_hash_validation_only=True,
        )
        one_apply = audit_petsc_level_a_one_apply(
            action,
            bare_f,
            source_vectors,
            factor_inventory,
            collect_scalar_contractions=True,
        )
        one_apply_gate = one_apply["gate"]
        implementation_subset_pass = all(
            (
                one_apply_gate.get("finite_pass") is True,
                one_apply_gate.get("zero_map_pass") is True,
                one_apply_gate.get("action_identity_pass") is True,
                one_apply_gate.get("repeat_pass") is True,
                one_apply_gate.get("linearity_pass") is True,
                one_apply_gate.get("factor_inventory_pass") is True,
            )
        )
        if not implementation_subset_pass:
            raise RuntimeError(
                "V2 consumer one-apply implementation subset failed: "
                f"{one_apply_gate!r}"
            )
        one_apply_gate["v2_implementation_subset_pass"] = True
        scalar_labels = tuple(TASK040_LEVEL_A_SOURCE_LABELS[1:])
        screen = run_v1_1_right_preconditioned_fgmres_batch(
            bare_f,
            {label: source_vectors[label] for label in scalar_labels},
            action,
            labels=scalar_labels,
            resource_callback=resource_callback,
            stop_on_frozen_gate=True,
            checkpoint_callback=lambda row: _emit(
                marker_callback, "v2_consumer_fgmres_checkpoint", **dict(row)
            ),
        )
        first_preferred_checkpoint = None
        phase = screen["phase1"]
        for checkpoint in ("4", "8", "16"):
            values = [
                phase[label]["checkpoints"]
                .get(checkpoint, {})
                .get("true_residual_relative")
                for label in scalar_labels
            ]
            if (
                values
                and all(
                    isinstance(value, (int, float))
                    and np.isfinite(float(value))
                    and float(value) <= 1.0e-2
                    for value in values
                )
                and all(float(value) <= 1.0e-3 for value in values[:3])
            ):
                first_preferred_checkpoint = int(checkpoint)
                break
        if first_preferred_checkpoint is None and screen["phase2"]:
            values = [
                screen["phase2"][label]["checkpoints"]
                .get("32", {})
                .get("true_residual_relative")
                for label in scalar_labels
            ]
            if (
                values
                and all(
                    isinstance(value, (int, float))
                    and np.isfinite(float(value))
                    and float(value) <= 1.0e-2
                    for value in values
                )
                and all(float(value) <= 1.0e-3 for value in values[:3])
            ):
                first_preferred_checkpoint = 32
        _emit(
            marker_callback,
            "level_a_audit_complete",
            first_preferred_checkpoint=first_preferred_checkpoint,
            factor_count_ready=factor_inventory["factor_count_ready"],
        )
        result = {
            "schema": TASK040_V2_INTERFACE_PACKET_CONSUMER_SCHEMA,
            "method": TASK040_V2_INTERFACE_PACKET_CONSUMER_METHOD,
            "profile": TASK040_V2_INTERFACE_PACKET_CONSUMER_PROFILE_ID,
            "source_sha": str(source_sha),
            "input_sha256": str(input_sha256),
            "physical_model_sha256": str(physical_model_sha256),
            "selected_manifest_sha256": selected_manifest_sha,
            "exact_spool_catalog_sha256": catalog_sha,
            "rhs_vectors_loaded": len(TASK040_LEVEL_A_SOURCE_LABELS),
            "packet_manifest_sha256": packet_manifest_sha256,
            "packet_producer_source_sha": provenance["source_sha"],
            "pde_solve": "not_run",
            "qep_calls": 0,
            "exact_output_vectors_loaded": 0,
            "interface_packet_raw": {
                "packet_consumer": True,
                "producer_source_sha": provenance["source_sha"],
                "packet_manifest_sha256": packet_manifest_sha256,
                "packet_provenance": provenance,
                "basis_global_replicated": False,
                "fe_numeric_allgather": False,
                "groups": remap_reports,
                "remap_pass": all(item["pass"] for item in remap_reports),
                "factor_inventory": factor_inventory,
                "one_apply": one_apply,
                "fgmres_screen": screen,
                "first_preferred_checkpoint": first_preferred_checkpoint,
                "lifecycle": {
                    "factor_count_ready": 3,
                    "exact_interface_oracle_factor_count": 0,
                    "simultaneous_factor_count_max": 3,
                },
                "source_loading": {
                    "labels": list(TASK040_LEVEL_A_SOURCE_LABELS),
                    "rhs_vectors_loaded": len(TASK040_LEVEL_A_SOURCE_LABELS),
                    "exact_output_vectors_loaded": 0,
                    "exact_output_metadata_hash_validation_only": True,
                },
                "forbidden_routes": [
                    "exact_interface_oracle",
                    "qep",
                    "pde_solve",
                    "outer_ksp",
                    "recovery",
                    "top",
                    "full_hybrid",
                    "response_packet",
                    "exact_output_vector_load",
                    "global_direct_factor",
                    "full_side_factor",
                ],
                "projected_diagnostics": dict(projected_diagnostics),
            },
        }
        owner_transferred = True
        return {"action": action, "owner": owner, "result": result}
    finally:
        for vector in source_vectors.values():
            vector.destroy()
        if not owner_transferred:
            if owner is not None:
                owner.destroy()
            elif action is not None:
                action.destroy()
        packet_layouts = None
        gamma_factors.clear()


def run_task040_level_a(
    cfg: Any,
    profile: Any,
    *,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
    exact_spool_root: str | Path,
    run_directory: str | Path | None = None,
    source_sha: str,
    input_path: str | Path | None = None,
    input_sha256: str | None = None,
    physical_model_sha256: str | None = None,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
    side_system_builder: Callable[..., Any] | None = None,
    scalar_krylov: bool = False,
    interface_schur: bool = False,
    packet_producer: bool = False,
    packet_consumer: bool = False,
    coupled_interface: bool = False,
    v4_exact_authority_compatibility: bool = False,
    v5_fresh_bare_f_authority: bool = False,
    v5_route_c: bool = False,
    v6_2_interface_schur: bool = False,
    v7_scale_normalized_identity: bool = False,
    v7_moving_pml_full_state: bool = False,
    v8_full_spectrum_only: bool = False,
    v8_adaptive_schwarz_only: bool = False,
    v8_adaptive_stage_b1_only: bool = False,
    v8_adaptive_stage_bc_only: bool = False,
    v9_source_bridge_only: bool = False,
    v9_c0_explicit_coarse_only: bool = False,
    v9_e_lor_l2_only: bool = False,
    v9_e_lor_bare_f_external_only: bool = False,
    v9_e_s3_j1_baseline_only: bool = False,
    v9_e_s3_structured_b1_only: bool = False,
    v9_e_s3_j1_baseline_manifest: str | Path | None = None,
    v9_e_s3_j1_baseline_manifest_sha256: str | None = None,
    v9_source_packet_root: str | Path | None = None,
    v9_source_packet_manifest_sha256: str | None = None,
    packet_root: str | Path | None = None,
    resource_callback: Callable[[], Mapping[str, Any]] | None = None,
    watchdog_enabled: bool = False,
    bottom_route_only: bool = False,
    watchdog_hard_stop_bytes: int | None = None,
    v7_continuation: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the six-source Level-A audit; all numerical work stays in src."""

    if (
        sum(
            bool(value)
            for value in (
                scalar_krylov,
                interface_schur,
                packet_producer,
                packet_consumer,
                coupled_interface,
                v4_exact_authority_compatibility,
                v5_fresh_bare_f_authority,
                v5_route_c,
                v6_2_interface_schur,
                v7_scale_normalized_identity,
                v7_moving_pml_full_state,
                v8_full_spectrum_only,
                v8_adaptive_schwarz_only,
                v8_adaptive_stage_b1_only,
                v8_adaptive_stage_bc_only,
                v9_source_bridge_only,
                v9_c0_explicit_coarse_only,
                v9_e_lor_l2_only,
                v9_e_lor_bare_f_external_only,
                v9_e_s3_j1_baseline_only,
                v9_e_s3_structured_b1_only,
            )
        )
        > 1
    ):
        raise ValueError("Task040 research routes are mutually exclusive")
    if v5_fresh_bare_f_authority:
        if run_directory is None:
            raise ValueError("V5 fresh authority requires a separate run_directory")
        if Path(run_directory).resolve() == Path(exact_spool_root).resolve():
            raise ValueError("V5 run_directory must not be the frozen exact spool root")
        if input_path is None:
            raise ValueError("V5 fresh authority requires the official input_path")
    if v5_route_c:
        if run_directory is None:
            raise ValueError("Route C requires a separate run_directory")
        if Path(run_directory).resolve() == Path(exact_spool_root).resolve():
            raise ValueError("Route C run_directory must not be the frozen exact spool root")
        if input_path is None:
            raise ValueError("Route C requires the official input_path")
    if v6_2_interface_schur:
        if run_directory is None:
            raise ValueError("V6-2 interface Schur requires a separate run_directory")
        if Path(run_directory).resolve() == Path(exact_spool_root).resolve():
            raise ValueError("V6-2 run_directory must not be the frozen exact spool root")
        if input_path is None:
            raise ValueError("V6-2 interface Schur requires the official input_path")
    if v7_scale_normalized_identity:
        if run_directory is None:
            raise ValueError(
                "V7 scale-normalized identity requires a separate run_directory"
            )
        if Path(run_directory).resolve() == Path(exact_spool_root).resolve():
            raise ValueError(
                "V7 run_directory must not be the frozen exact spool root"
            )
        if input_path is None:
            raise ValueError(
                "V7 scale-normalized identity requires the official input_path"
            )
    if v7_moving_pml_full_state:
        if run_directory is None:
            raise ValueError(
                "V7 moving-PML full-state screen requires a separate run_directory"
            )
        if Path(run_directory).resolve() == Path(exact_spool_root).resolve():
            raise ValueError(
                "V7 moving-PML run_directory must not be the frozen exact spool root"
            )
        if input_path is None:
            raise ValueError(
                "V7 moving-PML full-state screen requires the official input_path"
            )
    if v8_full_spectrum_only:
        if run_directory is None:
            raise ValueError("V8 full-spectrum route requires a separate run_directory")
        if Path(run_directory).resolve() == Path(exact_spool_root).resolve():
            raise ValueError("V8 run_directory must not be the frozen exact spool root")
        if input_path is None:
            raise ValueError("V8 full-spectrum route requires the official input_path")
    if (
        v8_adaptive_schwarz_only
        or v8_adaptive_stage_b1_only
        or v8_adaptive_stage_bc_only
        or v9_source_bridge_only
        or v9_c0_explicit_coarse_only
    ):
        if run_directory is None:
            raise ValueError("V8 adaptive route requires a separate run_directory")
        if Path(run_directory).resolve() == Path(exact_spool_root).resolve():
            raise ValueError("V8 adaptive run_directory must not be the frozen exact spool root")
        if input_path is None:
            raise ValueError("V8 adaptive route requires the official input_path")
    if v9_e_lor_l2_only:
        if run_directory is None:
            raise ValueError("V9-E L2 route requires a separate run_directory")
        if Path(run_directory).resolve() == Path(exact_spool_root).resolve():
            raise ValueError("V9-E L2 run_directory must not be the exact spool root")
        if input_path is None:
            raise ValueError("V9-E L2 route requires the official input_path")
        expected_l2_inputs = {
            (Path(__file__).resolve().parents[1] / relative).resolve()
            for relative in V9_E_LOR_L2_ALLOWED_INPUTS
        }
        if Path(input_path).resolve() not in expected_l2_inputs:
            raise ValueError("V9-E L2 route requires the frozen h10 or h5 input")
        if int(comm.size) != TASK040_LEVEL_A_MPI_SIZE:
            raise ValueError(
                f"V9-E L2 route requires MPI size {TASK040_LEVEL_A_MPI_SIZE}"
            )
        if not watchdog_enabled:
            raise ValueError("V9-E L2 route requires watchdog_enabled=true")
        if not bottom_route_only:
            raise ValueError("V9-E L2 route requires bottom_route_only=true")
        if watchdog_hard_stop_bytes != V9_E_LOR_L2_ONLY_HARD_STOP_BYTES:
            raise ValueError("V9-E L2 route requires watchdog hard stop 45 GiB")
        if not callable(resource_callback):
            raise TypeError("V9-E L2 route requires a callable resource_callback")
    if v9_e_lor_bare_f_external_only:
        if run_directory is None:
            raise ValueError(
                "V9-E bare-F external route requires a separate run_directory"
            )
        if Path(run_directory).resolve() == Path(exact_spool_root).resolve():
            raise ValueError(
                "V9-E bare-F external run_directory must not be the exact spool root"
            )
        if input_path is None:
            raise ValueError(
                "V9-E bare-F external route requires the official input_path"
            )
        expected_bare_f_input = (
            Path(__file__).resolve().parents[1]
            / V9_E_LOR_BARE_F_EXTERNAL_ONLY_INPUT
        ).resolve()
        if Path(input_path).resolve() != expected_bare_f_input:
            raise ValueError(
                "V9-E bare-F external route requires the frozen h10 input"
            )
        if int(comm.size) != V9_E_LOR_BARE_F_EXTERNAL_ONLY_MPI_SIZE:
            raise ValueError(
                "V9-E bare-F external route requires MPI8"
            )
        if not watchdog_enabled:
            raise ValueError(
                "V9-E bare-F external route requires watchdog_enabled=true"
            )
        if not bottom_route_only:
            raise ValueError(
                "V9-E bare-F external route requires bottom_route_only=true"
            )
        if (
            watchdog_hard_stop_bytes
            != V9_E_LOR_BARE_F_EXTERNAL_ONLY_HARD_STOP_BYTES
        ):
            raise ValueError(
                "V9-E bare-F external route requires watchdog hard stop 45 GiB"
            )
        if not callable(resource_callback):
            raise TypeError(
                "V9-E bare-F external route requires a callable resource_callback"
            )
    s3_route = bool(v9_e_s3_j1_baseline_only or v9_e_s3_structured_b1_only)
    if (v9_e_s3_j1_baseline_manifest is None) != (
        v9_e_s3_j1_baseline_manifest_sha256 is None
    ):
        raise ValueError(
            "V9-E S3 J1 baseline manifest path and SHA must be supplied together"
        )
    if v9_e_s3_j1_baseline_manifest is not None and not v9_e_s3_structured_b1_only:
        raise ValueError(
            "V9-E S3 J1 baseline manifest parameters are candidate-only"
        )
    if v9_e_s3_structured_b1_only and v9_e_s3_j1_baseline_manifest is None:
        raise ValueError(
            "V9-E S3 structured B1 candidate requires the J1 baseline manifest"
        )
    if v9_e_s3_j1_baseline_manifest_sha256 is not None and (
        len(str(v9_e_s3_j1_baseline_manifest_sha256)) != 64
        or any(
            character not in "0123456789abcdef"
            for character in str(v9_e_s3_j1_baseline_manifest_sha256)
        )
    ):
        raise ValueError(
            "V9-E S3 J1 baseline manifest SHA must be lowercase SHA256"
        )
    s3_resolved_input_path: str | None = None
    if s3_route:
        if run_directory is None:
            raise ValueError("V9-E S3 route requires a separate run_directory")
        if Path(run_directory).resolve() == Path(exact_spool_root).resolve():
            raise ValueError("V9-E S3 run_directory must not be the exact spool root")
        if input_path is None:
            raise ValueError("V9-E S3 route requires the frozen official input_path")
        if int(comm.size) != S3B_MPI_SIZE:
            raise ValueError(
                f"V9-E S3 route requires MPI size {S3B_MPI_SIZE}, got {comm.size}"
            )
        s3_resolved_input_path, actual_input_sha256 = _s3_fixed_input_identity(
            comm,
            input_path,
        )
        expected_input = (
            Path(__file__).resolve().parents[1] / V9_E_S3_INPUT_RELATIVE_PATH
        ).resolve()
        if s3_resolved_input_path != str(expected_input):
            raise ValueError(
                "V9-E S3 route input path mismatch: "
                f"expected {expected_input}, got {s3_resolved_input_path}"
            )
        if str(input_sha256) != V9_E_S3_INPUT_SHA256:
            raise ValueError(
                "V9-E S3 route input SHA256 mismatch: "
                f"expected {V9_E_S3_INPUT_SHA256}, got {input_sha256}"
            )
        if actual_input_sha256 != V9_E_S3_INPUT_SHA256:
            raise ValueError(
                "V9-E S3 route raw input SHA256 mismatch: "
                f"expected {V9_E_S3_INPUT_SHA256}, got {actual_input_sha256}"
            )
        if actual_input_sha256 != str(input_sha256):
            raise ValueError(
                "V9-E S3 route raw input SHA256 differs from supplied input_sha256"
            )
        if not watchdog_enabled:
            raise ValueError("V9-E S3 route requires watchdog_enabled=true")
        if not bottom_route_only:
            raise ValueError("V9-E S3 route requires bottom_route_only=true")
        if watchdog_hard_stop_bytes != S3B_RSS_HARD_BYTES:
            raise ValueError(
                "V9-E S3 route requires watchdog_hard_stop_bytes=45 GiB"
            )
        if not callable(resource_callback):
            raise TypeError("V9-E S3 route requires a callable resource_callback")
    if (
        interface_schur
        or packet_producer
        or packet_consumer
        or coupled_interface
        or v4_exact_authority_compatibility
        or v5_fresh_bare_f_authority
        or v5_route_c
        or v6_2_interface_schur
        or v7_scale_normalized_identity
        or v7_moving_pml_full_state
        or v8_full_spectrum_only
        or v8_adaptive_schwarz_only
        or v8_adaptive_stage_b1_only
        or v8_adaptive_stage_bc_only
        or v9_source_bridge_only
        or v9_c0_explicit_coarse_only
        or v9_e_lor_l2_only
        or v9_e_lor_bare_f_external_only
        or v9_e_s3_j1_baseline_only
        or v9_e_s3_structured_b1_only
    ):
        if (packet_consumer or coupled_interface) and packet_root is None:
            raise ValueError("Task040 packet consumer requires packet_root")
        for name, value in (
            ("input_sha256", input_sha256),
            ("physical_model_sha256", physical_model_sha256),
        ):
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise ValueError(f"Task040 V1-2 requires a real 64-character {name}")
    system = None
    components = None
    action = None
    owner = None
    source_vectors: dict[str, PETSc.Vec] = {}
    supports: list[dict[str, Any]] = []
    masses: list[Any] = []
    result: dict[str, Any] | None = None
    cleanup: dict[str, Any] = {}
    _emit(
        marker_callback,
        "construction_begin",
        method=(
            TASK040_V2_INTERFACE_PACKET_METHOD
            if packet_producer
            else TASK040_V3_2_COUPLED_INTERFACE_METHOD
            if coupled_interface
            else TASK040_V2_INTERFACE_PACKET_CONSUMER_METHOD
            if packet_consumer
            else TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_METHOD
            if v4_exact_authority_compatibility
            else TASK040_V5_FRESH_BARE_F_AUTHORITY_METHOD
            if v5_fresh_bare_f_authority
            else TASK040_V5_ROUTE_C_METHOD
            if v5_route_c
            else V7_SCALE_NORMALIZED_IDENTITY_METHOD
            if v7_scale_normalized_identity
            else V7_MOVING_PML_FULL_STATE_METHOD
            if v7_moving_pml_full_state
            else V9_C0_EXPLICIT_COARSE_ONLY_METHOD
            if v9_c0_explicit_coarse_only
            else V9_E_LOR_BARE_F_EXTERNAL_ONLY_METHOD
            if v9_e_lor_bare_f_external_only
            else V9_E_LOR_L2_ONLY_METHOD
            if v9_e_lor_l2_only
            else V9_E_S3_B1_METHOD
            if v9_e_s3_structured_b1_only
            else V9_E_S3_J1_BASELINE_METHOD
            if v9_e_s3_j1_baseline_only
            else V8_FULL_SPECTRUM_ONLY_METHOD
            if v8_full_spectrum_only
            else TASK040_V6_2_INTERFACE_SCHUR_METHOD
            if v6_2_interface_schur
            else TASK040_V1_2_METHOD
            if interface_schur
            else TASK040_LEVEL_A_METHOD
        ),
    )
    if v4_exact_authority_compatibility:
        preflight = _v4_source_authority_preflight(
            exact_spool_root=exact_spool_root,
            source_sha=source_sha,
            input_sha256=str(input_sha256),
            physical_model_sha256=str(physical_model_sha256),
            comm=comm,
        )
        _emit(
            marker_callback,
            "v4_identity_stop",
            failure_code=preflight["result"]["identity_failure_code"],
            residual_status="not_run_by_identity_gate",
            system_created=False,
            array_hash_validation_only=True,
            numeric_vectors_constructed=False,
            values_retained=False,
        )
        return preflight["result"]
    if v5_fresh_bare_f_authority:
        identity_preflight = _v5_authority_identity_preflight(
            comm=comm,
            input_path=input_path,
            input_sha256=str(input_sha256),
            physical_model_sha256=str(physical_model_sha256),
            source_sha=source_sha,
            watchdog_enabled=watchdog_enabled,
            bottom_route_only=bottom_route_only,
        )
        identity_preflight["operator_semantics_audit_file"] = (
            _v5_write_operator_semantics_audit(
                comm,
                run_directory,
                identity_preflight.get("operator_semantics_audit"),
            )
        )
        if not identity_preflight["pass"]:
            runtime_failures = [
                failure
                for failure in identity_preflight["failures"]
                if str(failure).startswith("runtime_")
            ]
            runtime_preflight_failed = bool(runtime_failures)
            stop_status = (
                "not_run_by_resource_preflight"
                if runtime_preflight_failed
                else "not_run_by_identity_preflight"
            )
            stop_classification = (
                "FRESH_BARE_F_AUTHORITY_RESOURCE_BLOCKED"
                if runtime_preflight_failed
                else "FRESH_BARE_F_AUTHORITY_IDENTITY_FAIL"
            )
            _emit(
                marker_callback,
                "v5_runtime_preflight_stop"
                if runtime_preflight_failed
                else "v5_identity_preflight_stop",
                identity_status=identity_preflight["status"],
                identity_failures=identity_preflight["failures"],
                runtime_failures=runtime_failures,
                system_created=False,
                qep_calls=0,
            )
            return {
                "schema": TASK040_V5_FRESH_BARE_F_AUTHORITY_SCHEMA,
                "method": TASK040_V5_FRESH_BARE_F_AUTHORITY_METHOD,
                "profile": TASK040_V5_FRESH_BARE_F_AUTHORITY_PROFILE_ID,
                "status": stop_status,
                "classification": stop_classification,
                "source_sha": str(source_sha),
                "input_sha256": str(input_sha256),
                "physical_model_sha256": str(physical_model_sha256),
                "identity_preflight": identity_preflight,
                "runtime_preflight": identity_preflight.get("runtime_preflight"),
                "preflight_failure_category": (
                    "runtime_environment" if runtime_preflight_failed else None
                ),
                "system_created": False,
                "rhs_vectors_loaded": 0,
                "exact_output_vectors_loaded": 0,
                "factor_lifecycle": {
                    "factor_count_before_solve": 0,
                    "factor_count_after_cleanup": 0,
                },
                "external_dtn_coupling": {
                    "status": stop_status,
                    "matrix_objects_constructed": None,
                },
                "qep_calls": 0,
                "pde_solve": "not_run",
                "outer_ksp": "not_run",
            }
        resource_preflight = _v5_bare_f_resource_preflight(
            comm,
            run_directory,
        )
        if not resource_preflight["pass"]:
            rank_resource = resource_preflight["ranks"][comm.rank]
            _emit(
                marker_callback,
                "v5_resource_preflight_stop",
                resource_status=resource_preflight["status"],
                mem_available_bytes=rank_resource["mem_available_bytes"],
                disk_free_bytes=rank_resource["disk_free_bytes"],
                swap_bytes=rank_resource["swap_bytes"],
                system_created=False,
                qep_calls=0,
            )
            return {
                "schema": TASK040_V5_FRESH_BARE_F_AUTHORITY_SCHEMA,
                "method": TASK040_V5_FRESH_BARE_F_AUTHORITY_METHOD,
                "profile": TASK040_V5_FRESH_BARE_F_AUTHORITY_PROFILE_ID,
                "status": "not_run_by_resource_preflight",
                "classification": "FRESH_BARE_F_AUTHORITY_RESOURCE_BLOCKED",
                "source_sha": str(source_sha),
                "input_sha256": str(input_sha256),
                "physical_model_sha256": str(physical_model_sha256),
                "resource_preflight": resource_preflight,
                "system_created": False,
                "rhs_vectors_loaded": 0,
                "exact_output_vectors_loaded": 0,
                "factor_lifecycle": {
                    "factor_count_before_solve": 0,
                    "factor_count_after_cleanup": 0,
                },
                "external_dtn_coupling": {
                    "status": "not_run_by_resource_preflight",
                    "matrix_objects_constructed": None,
                },
                "qep_calls": 0,
                "pde_solve": "not_run",
                "outer_ksp": "not_run",
            }
        current_resolved_config_sha256 = identity_preflight.get("observed", {}).get(
            "resolved_config_sha256"
        )
        if current_resolved_config_sha256 is None:
            current_resolved_config_sha256 = identity_preflight.get(
                "external_mode_authority", {}
            ).get("resolved_config_sha256")
        result = run_current_bare_f_authority(
            cfg,
            profile,
            run_directory=run_directory,
            source_sha=source_sha,
            provenance=identity_preflight,
            input_sha256=str(input_sha256),
            physical_model_sha256=str(physical_model_sha256),
            selected_mode_provider=_v5_selected_mode_provider(comm),
            external_mode_authority=identity_preflight["external_mode_authority"],
            external_mode_current_resolved_config_sha256=(
                None
                if current_resolved_config_sha256 is None
                else str(current_resolved_config_sha256)
            ),
            marker_callback=(
                lambda stage, detail: _forward_v5_marker(marker_callback, stage, detail)
            ),
            comm=comm,
        )
        result["resource_preflight"] = resource_preflight
        return result
    if v5_route_c:
        return _run_v5_route_c(
            cfg=cfg,
            profile=profile,
            comm=comm,
            exact_spool_root=exact_spool_root,
            run_directory=run_directory,
            source_sha=source_sha,
            input_path=input_path,
            input_sha256=str(input_sha256),
            physical_model_sha256=str(physical_model_sha256),
            marker_callback=marker_callback,
            resource_callback=resource_callback,
            watchdog_enabled=watchdog_enabled,
            bottom_route_only=bottom_route_only,
        )
    if v9_e_s3_j1_baseline_only:
        from src.solvers.floquet_background_hcurl_s3_formal import (
            run_s3_j1_baseline_formal,
        )

        return run_s3_j1_baseline_formal(
            cfg,
            profile,
            comm=comm,
            source_sha=source_sha,
            input_path=str(s3_resolved_input_path),
            input_sha256=str(input_sha256),
            physical_model_sha256=str(physical_model_sha256),
            marker_callback=marker_callback,
            resource_callback=resource_callback,
        )
    if v9_e_s3_structured_b1_only:
        from src.solvers.floquet_background_hcurl_s3_formal import (
            _run_s3_b1_candidate_external_core,
            validate_s3_j1_baseline_manifest,
        )

        (
            baseline_manifest,
            observed_manifest_sha256,
            baseline_path,
        ) = _load_s3_j1_baseline_manifest(
            comm,
            v9_e_s3_j1_baseline_manifest,
        )
        validated_baseline = validate_s3_j1_baseline_manifest(
            baseline_manifest,
            str(v9_e_s3_j1_baseline_manifest_sha256),
            observed_manifest_sha256,
            source_sha=str(source_sha),
            input_path=str(s3_resolved_input_path),
            input_sha256=str(input_sha256),
            physical_model_sha256=str(physical_model_sha256),
        )
        result = _run_s3_b1_candidate_external_core(
            cfg,
            profile,
            comm=comm,
            source_sha=source_sha,
            input_path=str(s3_resolved_input_path),
            input_sha256=str(input_sha256),
            physical_model_sha256=str(physical_model_sha256),
            validated_baseline=validated_baseline,
            marker_callback=marker_callback,
            resource_callback=resource_callback,
            source_work_directory=Path(run_directory) / "s3_source_work",
            selected_mode_provider=_v5_selected_mode_provider(comm),
        )
        result["baseline_manifest_binding"] = {
            "path": str(baseline_path),
            "expected_sha256": str(v9_e_s3_j1_baseline_manifest_sha256),
            "observed_sha256": observed_manifest_sha256,
        }
        return result
    if v9_e_lor_bare_f_external_only:
        from src.solvers.hybrid_bare_f_external_lor_pilot import (
            run_v9_e_lor_bare_f_external_only,
        )

        identity_preflight = _v9_e_lor_bare_f_external_authority_preflight(
            comm=comm,
            input_path=input_path,
            input_sha256=str(input_sha256),
            physical_model_sha256=str(physical_model_sha256),
            source_sha=str(source_sha),
            watchdog_enabled=watchdog_enabled,
            bottom_route_only=bottom_route_only,
        )
        if identity_preflight.get("pass") is not True:
            return {
                "schema": V9_E_LOR_BARE_F_EXTERNAL_ONLY_SCHEMA,
                "method": V9_E_LOR_BARE_F_EXTERNAL_ONLY_METHOD,
                "profile_id": V9_E_LOR_BARE_F_EXTERNAL_ONLY_PROFILE_ID,
                "status": V9_E_LOR_BARE_F_EXTERNAL_IMPLEMENTATION_FAILURE,
                "classification": V9_E_LOR_BARE_F_EXTERNAL_IMPLEMENTATION_FAILURE,
                "identity_preflight": identity_preflight,
                "preflight_failures": list(identity_preflight.get("failures", [])),
                "system_created": False,
                "official_rta": {"status": "not_run"},
            }
        external_mode_authority = identity_preflight.get("external_mode_authority")
        observed = identity_preflight.get("observed", {})
        current_resolved_config_sha256 = observed.get("resolved_config_sha256")
        if current_resolved_config_sha256 is None:
            if not isinstance(external_mode_authority, Mapping):
                raise RuntimeError(
                    "bare-F identity preflight returned no authority mapping"
                )
            current_resolved_config_sha256 = external_mode_authority.get(
                "resolved_config_sha256"
            )
        if external_mode_authority is None or current_resolved_config_sha256 is None:
            raise RuntimeError(
                "bare-F identity preflight returned incomplete external authority"
            )
        return run_v9_e_lor_bare_f_external_only(
            cfg=cfg,
            profile=profile,
            comm=comm,
            input_path=input_path,
            run_directory=run_directory,
            source_sha=str(source_sha),
            input_sha256=str(input_sha256),
            physical_model_sha256=str(physical_model_sha256),
            external_mode_authority=external_mode_authority,
            external_mode_current_resolved_config_sha256=str(
                current_resolved_config_sha256
            ),
            marker_callback=marker_callback,
            resource_callback=resource_callback,
            watchdog_enabled=watchdog_enabled,
            bottom_route_only=bottom_route_only,
            watchdog_hard_stop_bytes=watchdog_hard_stop_bytes,
        )
    if v9_e_lor_l2_only:
        from src.solvers.hcurl_fixed_lor_positive_screen import (
            run_v9_e_lor_l2_only,
        )

        return run_v9_e_lor_l2_only(
            cfg=cfg,
            comm=comm,
            input_path=input_path,
            run_directory=run_directory,
            source_sha=str(source_sha),
            input_sha256=str(input_sha256),
            physical_model_sha256=str(physical_model_sha256),
            marker_callback=marker_callback,
            resource_callback=resource_callback,
            watchdog_enabled=watchdog_enabled,
            bottom_route_only=bottom_route_only,
            watchdog_hard_stop_bytes=watchdog_hard_stop_bytes,
        )
    if v9_c0_explicit_coarse_only:
        from benchmarks.task040_v6_2_interface_schur import run_v6_2_interface_schur

        return run_v6_2_interface_schur(
            cfg=cfg,
            profile=profile,
            comm=comm,
            exact_spool_root=exact_spool_root,
            run_directory=run_directory,
            source_sha=source_sha,
            input_path=input_path,
            input_sha256=str(input_sha256),
            physical_model_sha256=str(physical_model_sha256),
            marker_callback=marker_callback,
            watchdog_enabled=watchdog_enabled,
            bottom_route_only=bottom_route_only,
            hard_stop_bytes=V9_C0_HARD_STOP_BYTES,
            watchdog_hard_stop_bytes=watchdog_hard_stop_bytes,
            resource_callback=resource_callback,
            v9_c0_explicit_coarse_only=True,
        )
    if v9_source_bridge_only:
        from benchmarks.task040_v6_2_interface_schur import run_v6_2_interface_schur

        return run_v6_2_interface_schur(
            cfg=cfg,
            profile=profile,
            comm=comm,
            exact_spool_root=exact_spool_root,
            run_directory=run_directory,
            source_sha=source_sha,
            input_path=input_path,
            input_sha256=str(input_sha256),
            physical_model_sha256=str(physical_model_sha256),
            marker_callback=marker_callback,
            watchdog_enabled=watchdog_enabled,
            bottom_route_only=bottom_route_only,
            hard_stop_bytes=TASK040_LEVEL_A_HARD_STOP_BYTES,
            watchdog_hard_stop_bytes=watchdog_hard_stop_bytes,
            resource_callback=resource_callback,
            v9_source_bridge_only=True,
        )
    if (
        v8_adaptive_schwarz_only
        or v8_adaptive_stage_b1_only
        or v8_adaptive_stage_bc_only
    ):
        from benchmarks.task040_v6_2_interface_schur import run_v6_2_interface_schur

        return run_v6_2_interface_schur(
            cfg=cfg,
            profile=profile,
            comm=comm,
            exact_spool_root=exact_spool_root,
            run_directory=run_directory,
            source_sha=source_sha,
            input_path=input_path,
            input_sha256=str(input_sha256),
            physical_model_sha256=str(physical_model_sha256),
            marker_callback=marker_callback,
            watchdog_enabled=watchdog_enabled,
            bottom_route_only=bottom_route_only,
            hard_stop_bytes=TASK040_LEVEL_A_HARD_STOP_BYTES,
            watchdog_hard_stop_bytes=watchdog_hard_stop_bytes,
            resource_callback=resource_callback,
            v8_adaptive_schwarz_only=v8_adaptive_schwarz_only,
            v8_adaptive_stage_b1_only=v8_adaptive_stage_b1_only,
            v8_adaptive_stage_bc_only=v8_adaptive_stage_bc_only,
            v9_source_bridge_only=v9_source_bridge_only,
        )
    if v8_full_spectrum_only:
        from benchmarks.task040_v6_2_interface_schur import run_v6_2_interface_schur

        return run_v6_2_interface_schur(
            cfg=cfg,
            profile=profile,
            comm=comm,
            exact_spool_root=exact_spool_root,
            run_directory=run_directory,
            source_sha=source_sha,
            input_path=input_path,
            input_sha256=str(input_sha256),
            physical_model_sha256=str(physical_model_sha256),
            marker_callback=marker_callback,
            watchdog_enabled=watchdog_enabled,
            bottom_route_only=bottom_route_only,
            hard_stop_bytes=TASK040_LEVEL_A_HARD_STOP_BYTES,
            watchdog_hard_stop_bytes=watchdog_hard_stop_bytes,
            resource_callback=resource_callback,
            v8_full_spectrum_only=True,
            v9_source_packet_root=v9_source_packet_root,
            v9_source_packet_manifest_sha256=v9_source_packet_manifest_sha256,
        )
    if v7_moving_pml_full_state:
        from benchmarks.task040_v6_2_interface_schur import (
            run_v6_2_interface_schur,
        )

        return run_v6_2_interface_schur(
            cfg=cfg,
            profile=profile,
            comm=comm,
            exact_spool_root=exact_spool_root,
            run_directory=run_directory,
            source_sha=source_sha,
            input_path=input_path,
            input_sha256=str(input_sha256),
            physical_model_sha256=str(physical_model_sha256),
            marker_callback=marker_callback,
            watchdog_enabled=watchdog_enabled,
            bottom_route_only=bottom_route_only,
            hard_stop_bytes=TASK040_LEVEL_A_HARD_STOP_BYTES,
            watchdog_hard_stop_bytes=watchdog_hard_stop_bytes,
            resource_callback=resource_callback,
            v7_moving_pml_full_state=True,
        )
    if v7_scale_normalized_identity:
        from benchmarks.task040_v6_2_interface_schur import (
            run_v6_2_interface_schur,
        )

        return run_v6_2_interface_schur(
            cfg=cfg,
            profile=profile,
            comm=comm,
            exact_spool_root=exact_spool_root,
            run_directory=run_directory,
            source_sha=source_sha,
            input_path=input_path,
            input_sha256=str(input_sha256),
            physical_model_sha256=str(physical_model_sha256),
            marker_callback=marker_callback,
            watchdog_enabled=watchdog_enabled,
            bottom_route_only=bottom_route_only,
            hard_stop_bytes=TASK040_LEVEL_A_HARD_STOP_BYTES,
            watchdog_hard_stop_bytes=watchdog_hard_stop_bytes,
            resource_callback=resource_callback,
            v7_scale_normalized_identity=True,
            v7_continuation=v7_continuation,
        )
    if v6_2_interface_schur:
        from benchmarks.task040_v6_2_interface_schur import (
            run_v6_2_interface_schur,
        )

        return run_v6_2_interface_schur(
            cfg=cfg,
            profile=profile,
            comm=comm,
            exact_spool_root=exact_spool_root,
            run_directory=run_directory,
            source_sha=source_sha,
            input_path=input_path,
            input_sha256=str(input_sha256),
            physical_model_sha256=str(physical_model_sha256),
            marker_callback=marker_callback,
            watchdog_enabled=watchdog_enabled,
            bottom_route_only=bottom_route_only,
            hard_stop_bytes=TASK040_LEVEL_A_HARD_STOP_BYTES,
            watchdog_hard_stop_bytes=watchdog_hard_stop_bytes,
            resource_callback=resource_callback,
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
        system_inventory = dict(system.inventory)
        system_inventory_ok = (
            system_inventory.get("direct_factor_count") == 0
            and system_inventory.get("global_A_materialized") is False
        )
        if not bool(comm.allreduce(system_inventory_ok, op=MPI.LAND)):
            raise RuntimeError(
                "Task040 system inventory is not factor-free/action-only: "
                f"{system_inventory!r}"
            )
        _emit(
            marker_callback,
            "system_ready",
            matrix_free=bool(system_inventory.get("matrix_free")),
            direct_factor_count=system_inventory.get("direct_factor_count"),
            global_A_materialized=system_inventory.get("global_A_materialized"),
        )
        components = _build_research_explicit_side_components(system)
        bare_f = components.F
        z_values = system.local_mesh.z_values
        interface_z = (float(z_values[2]), float(z_values[4]))
        for index, interface in enumerate(interface_z):
            _emit(marker_callback, "interface_mass_begin", interface=index, z=interface)
            support = audit_artificial_z_interface_support(
                system.V,
                system.static_condensation.condensed,
                interface,
            )
            supports.append(support)
            masses.append(
                assemble_reduced_artificial_interface_tangential_mass(
                    system.V,
                    system.static_condensation.condensed,
                    support,
                    bare_operator=bare_f,
                )
            )
            _emit(
                marker_callback,
                "interface_mass_ready",
                interface=index,
                support=masses[-1].audit,
            )

        group_rows, group_audit = build_level_a_cell_recovery_group_rows(
            system, bare_f, supports
        )
        beta = level_a_bottom_beta(cfg)
        _emit(
            marker_callback,
            "projection_begin",
            beta=[beta.real, beta.imag],
            q=[(-1j * beta).real, (-1j * beta).imag],
        )
        if coupled_interface:
            route = _run_v3_2_coupled_interface_consumer(
                cfg=cfg,
                system=system,
                bare_f=bare_f,
                source_sha=source_sha,
                input_sha256=str(input_sha256),
                physical_model_sha256=str(physical_model_sha256),
                group_rows=group_rows,
                group_audit=group_audit,
                supports=supports,
                masses=masses,
                exact_spool_root=exact_spool_root,
                beta=beta,
                packet_root=packet_root,
                marker_callback=marker_callback,
                resource_callback=resource_callback,
                comm=comm,
            )
            action = route["action"]
            owner = route["owner"]
            result = route["result"]
            return result
        if packet_consumer:
            route = _run_v2_packet_consumer(
                system=system,
                bare_f=bare_f,
                source_sha=source_sha,
                input_sha256=str(input_sha256),
                physical_model_sha256=str(physical_model_sha256),
                group_rows=group_rows,
                group_audit=group_audit,
                supports=supports,
                masses=masses,
                exact_spool_root=exact_spool_root,
                beta=beta,
                packet_root=packet_root,
                marker_callback=marker_callback,
                resource_callback=resource_callback,
                comm=comm,
            )
            action = route["action"]
            owner = route["owner"]
            result = route["result"]
            return result
        if interface_schur or packet_producer:
            route = _run_v1_2_interface_schur(
                cfg=cfg,
                system=system,
                bare_f=bare_f,
                source_sha=source_sha,
                input_sha256=str(input_sha256),
                physical_model_sha256=str(physical_model_sha256),
                group_rows=group_rows,
                group_audit=group_audit,
                supports=supports,
                masses=masses,
                exact_spool_root=exact_spool_root,
                beta=beta,
                marker_callback=marker_callback,
                resource_callback=resource_callback,
                producer_mode=packet_producer,
                packet_root=packet_root,
                comm=comm,
            )
            action = route["action"]
            owner = route["owner"]
            result = route["result"]
            return result
        action, owner, oracle_diagnostics = build_level_a_oracle(
            bare_f=bare_f,
            group_rows=group_rows,
            interface_masses=masses,
            beta=beta,
            group_audit=group_audit,
        )
        _emit(
            marker_callback,
            "projection_ready",
            group_audit=group_audit,
            restriction_prolongation_error=oracle_diagnostics[
                "restriction_prolongation_error"
            ],
        )

        packet_identity, manifest_sha, catalog = _v9_frozen_holdout_identity(
            exact_spool_root, comm
        )
        spool = _load_v5_fixed_budget_spool_shards(
            exact_spool_root,
            comm,
            packet_identity=packet_identity,
            manifest_sha256=manifest_sha,
        )
        for label in TASK040_LEVEL_A_SOURCE_LABELS:
            template = bare_f.createVecLeft()
            try:
                source_vectors[label] = _load_v5_blr_reference_spool_remapped(
                    spool[label]["rhs"], template
                )
            finally:
                template.destroy()
        _emit(
            marker_callback,
            "source_ready",
            labels=list(TASK040_LEVEL_A_SOURCE_LABELS),
            source_identity={
                label: spool[label]["rhs"]["probe_metadata"]
                for label in TASK040_LEVEL_A_SOURCE_LABELS
            },
            rhs_vectors_loaded=len(TASK040_LEVEL_A_SOURCE_LABELS),
            exact_outputs_used=False,
            exact_output_vectors_loaded=0,
            exact_output_metadata_hash_validation_only=True,
        )
        required_factor_counts = {
            "cross_section_factor_count_ready": 3,
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
        }
        if any(
            oracle_diagnostics.get(key) != value
            for key, value in required_factor_counts.items()
        ):
            raise RuntimeError(
                "Task040 factor inventory failed: "
                f"{required_factor_counts!r} vs {oracle_diagnostics!r}"
            )
        factor_inventory = {
            "observed": True,
            **required_factor_counts,
            "factor_count_ready": oracle_diagnostics[
                "cross_section_factor_count_ready"
            ],
            "system_direct_factor_count_observed": system_inventory[
                "direct_factor_count"
            ],
            "system_global_A_materialized_observed": system_inventory[
                "global_A_materialized"
            ],
            "oracle_only": True,
            "scalable_candidate": False,
        }
        action_result = audit_petsc_level_a_one_apply(
            action,
            bare_f,
            source_vectors,
            factor_inventory,
            collect_scalar_contractions=scalar_krylov,
        )
        scalar_screen = None
        if scalar_krylov:
            scalar_labels = tuple(TASK040_LEVEL_A_SOURCE_LABELS[1:])
            scalar_screen = run_v1_1_right_preconditioned_fgmres_batch(
                bare_f,
                {label: source_vectors[label] for label in scalar_labels},
                action,
                labels=scalar_labels,
                resource_callback=resource_callback,
                checkpoint_callback=lambda row: _emit(
                    marker_callback, "v1_1_fgmres_checkpoint", **dict(row)
                ),
            )
            _emit(
                marker_callback,
                "v1_1_scalar_screen_complete",
                conditional_32_authorized=scalar_screen["conditional_32_authorized"],
                ksp_setup_count=scalar_screen["ksp_setup_count"],
                ksp_destroy_count=scalar_screen["ksp_destroy_count"],
                right_pc_apply_count=scalar_screen["right_pc_apply_count"],
            )
        _emit(
            marker_callback,
            "level_a_audit_complete",
            source_rho={
                report["label"]: report["true_residual_relative"]
                for report in action_result["reports"]
            },
            worst_mandatory_rho=action_result["gate"]["worst_mandatory_rho"],
            preferred_rho_pass=action_result["gate"]["preferred_rho_pass"],
            gate_pass=action_result["gate"]["pass"],
            factor_inventory=factor_inventory,
        )
        result = {
            "schema": TASK040_V1_1_SCHEMA if scalar_krylov else TASK040_LEVEL_A_SCHEMA,
            "method": TASK040_V1_1_METHOD if scalar_krylov else TASK040_LEVEL_A_METHOD,
            "profile": TASK040_V1_1_PROFILE_ID
            if scalar_krylov
            else TASK040_LEVEL_A_PROFILE_ID,
            "source_sha": str(source_sha),
            "beta": {
                "formula": "cfg.k0 * complex(cfg.substrate_index)",
                "value": [beta.real, beta.imag],
                "q": [(-1j * beta).real, (-1j * beta).imag],
                "authority": TASK040_LEVEL_A_BETA_AUTHORITY,
            },
            "sequence": list(TASK040_LEVEL_A_SEQUENCE),
            "input_identity": catalog,
            "packet_identity": packet_identity,
            "spool_manifest_sha256": manifest_sha,
            "rhs_vectors_loaded": len(TASK040_LEVEL_A_SOURCE_LABELS),
            "exact_output_vectors_loaded": 0,
            "exact_output_metadata_hash_validation_only": True,
            "interface_masses": [mass.audit for mass in masses],
            "oracle": oracle_diagnostics,
            "factor_inventory": factor_inventory,
            "action": action_result,
            "source_loading": {
                "labels": list(TASK040_LEVEL_A_SOURCE_LABELS),
                "rhs_vectors_loaded": len(TASK040_LEVEL_A_SOURCE_LABELS),
                "exact_output_vectors_loaded": 0,
                "exact_output_metadata_hash_validation_only": True,
            },
            "pde_solve": "not_run",
            "top": "not_run",
            "scalable_candidate": False,
        }
        if scalar_krylov:
            result["scalar_krylov"] = True
            result["scalar_screen"] = scalar_screen
    finally:
        for vector in source_vectors.values():
            vector.destroy()
        if owner is not None:
            ready_owner = owner.diagnostics
            owner.destroy()
            cleanup["factor_owner"] = {
                "ready": ready_owner,
                "after": owner.diagnostics,
            }
            owner = None
            action = None
        elif action is not None:
            action.destroy()
            action = None
        for mass in masses:
            mass.destroy()
        if components is not None:
            cleanup["components_destroyed"] = _destroy_explicit_components(components)
        if system is not None:
            system.destroy()
        cleanup["collective_heap"] = collective_heap_cleanup(comm)
        _emit(marker_callback, "cleanup", **cleanup)
        if result is not None:
            result["cleanup"] = cleanup
            if (
                interface_schur
                or packet_producer
                or packet_consumer
                or coupled_interface
            ):
                raw = result.get(
                    "interface_schur_raw"
                    if not packet_consumer and not coupled_interface
                    else "coupled_interface_raw"
                    if coupled_interface
                    else "interface_packet_raw"
                )
                if isinstance(raw, dict):
                    lifecycle = raw.setdefault("lifecycle", {})
                    lifecycle["worker_cleanup"] = cleanup
                    factor_owner = cleanup.get("factor_owner")
                    after_owner = (
                        factor_owner.get("after", {})
                        if isinstance(factor_owner, dict)
                        else {}
                    )
                    lifecycle["action_destroyed"] = action is None
                    lifecycle["factor_destroyed"] = bool(
                        not factor_owner or after_owner.get("destroyed") is True
                    )
                    if packet_consumer or coupled_interface:
                        lifecycle["factor_count_after_cleanup"] = after_owner.get(
                            "factor_count_after_cleanup"
                        )
                        lifecycle["projected_inverse_count_after_cleanup"] = (
                            after_owner.get("auxiliary_owner_count")
                            if packet_consumer
                            else after_owner.get("reduced_dense_factor_count")
                        )
                        if coupled_interface:
                            lifecycle["reduced_dense_factor_count_after_cleanup"] = (
                                after_owner.get("reduced_dense_factor_count")
                            )
    if result is None:
        raise RuntimeError("Task040 Level-A did not produce a result")
    return result


def _load_cfg(input_path: str | Path) -> tuple[Any, Any, str, str]:
    spec = load_and_resolve(input_path)
    cfg = simulation_config_3d_from_normalized(spec.as_jsonable())
    profile = make_task039_hybrid_iterative_profile(480, 8, mesh_target_nm=4.0)
    return cfg, profile, spec.input_sha256, spec.physical_model_sha256


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--input", required=True)
    parser.add_argument("--exact-spool-root", required=True)
    parser.add_argument("--run-directory", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument(TASK040_V1_1_SCALAR_KRYLOV_FLAG, action="store_true")
    parser.add_argument(TASK040_V1_2_INTERFACE_SCHUR_FLAG, action="store_true")
    parser.add_argument(TASK040_V2_INTERFACE_PACKET_PRODUCER_FLAG, action="store_true")
    parser.add_argument(TASK040_V2_INTERFACE_PACKET_CONSUMER_FLAG, action="store_true")
    parser.add_argument(TASK040_V3_2_COUPLED_INTERFACE_FLAG, action="store_true")
    parser.add_argument(
        TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_FLAG, action="store_true"
    )
    parser.add_argument(TASK040_V5_FRESH_BARE_F_AUTHORITY_FLAG, action="store_true")
    parser.add_argument(TASK040_V5_ROUTE_C_FLAG, action="store_true")
    parser.add_argument(TASK040_V6_2_INTERFACE_SCHUR_FLAG, action="store_true")
    parser.add_argument(V7_SCALE_NORMALIZED_IDENTITY_FLAG, action="store_true")
    parser.add_argument(V7_MOVING_PML_FULL_STATE_FLAG, action="store_true")
    parser.add_argument(V8_FULL_SPECTRUM_ONLY_FLAG, action="store_true")
    parser.add_argument(V8_ADAPTIVE_SCHWARZ_ONLY_FLAG, action="store_true")
    parser.add_argument(V8_ADAPTIVE_STAGE_B1_ONLY_FLAG, action="store_true")
    parser.add_argument(V8_ADAPTIVE_STAGE_BC_ONLY_FLAG, action="store_true")
    parser.add_argument(V9_SOURCE_BRIDGE_ONLY_FLAG, action="store_true")
    parser.add_argument(V9_C0_EXPLICIT_COARSE_ONLY_FLAG, action="store_true")
    parser.add_argument(V9_E_LOR_L2_ONLY_FLAG, action="store_true")
    parser.add_argument(
        V9_E_LOR_BARE_F_EXTERNAL_ONLY_FLAG, action="store_true"
    )
    parser.add_argument(V9_E_S3_J1_BASELINE_ONLY_FLAG, action="store_true")
    parser.add_argument(V9_E_S3_STRUCTURED_B1_ONLY_FLAG, action="store_true")
    parser.add_argument(V9_E_S3_J1_BASELINE_MANIFEST_OPTION)
    parser.add_argument(V9_E_S3_J1_BASELINE_MANIFEST_SHA256_OPTION)
    parser.add_argument(V9_SOURCE_PACKET_ROOT_OPTION)
    parser.add_argument(V9_SOURCE_PACKET_MANIFEST_SHA256_OPTION)
    parser.add_argument("--interface-packet-root")
    parser.add_argument("--memory-stages")
    parser.add_argument("--memory-markers")
    parser.add_argument("--watchdog-enabled", action="store_true")
    parser.add_argument("--bottom-route-only", action="store_true")
    parser.add_argument("--watchdog-hard-stop-bytes", type=int)
    args = parser.parse_args(argv)
    plan = build_task040_level_a_plan(
        input_path=args.input,
        exact_spool_root=args.exact_spool_root,
        run_directory=args.run_directory,
        source_sha=args.source_sha,
        scalar_krylov=args.v1_1_scalar_krylov,
        interface_schur=args.v1_2_interface_schur,
        packet_producer=args.v2_interface_packet_producer,
        packet_consumer=args.v2_interface_packet_consumer,
        coupled_interface=args.v3_2_coupled_interface,
        v4_exact_authority_compatibility=args.v4_exact_authority_compatibility,
        v5_fresh_bare_f_authority=args.v5_fresh_bare_f_authority,
        v5_route_c=args.v5_route_c,
        v6_2_interface_schur=args.v6_2_interface_schur,
        v7_scale_normalized_identity=args.v7_scale_normalized_identity,
        v7_moving_pml_full_state=args.v7_moving_pml_full_state,
        v8_full_spectrum_only=args.v8_full_spectrum_only,
        v8_adaptive_schwarz_only=args.v8_adaptive_schwarz_only,
        v8_adaptive_stage_b1_only=args.v8_adaptive_stage_b1_only,
        v8_adaptive_stage_bc_only=args.v8_adaptive_stage_bc_only,
        v9_source_bridge_only=args.v9_source_bridge_only,
        v9_c0_explicit_coarse_only=args.v9_c0_explicit_coarse_only,
        v9_e_lor_l2_only=args.v9_e_lor_l2_only,
        v9_e_lor_bare_f_external_only=args.v9_e_lor_bare_f_external_only,
        v9_e_s3_j1_baseline_only=args.v9_e_s3_j1_baseline_only,
        v9_e_s3_structured_b1_only=args.v9_e_s3_structured_b1_only,
        v9_e_s3_j1_baseline_manifest=args.v9_e_s3_j1_baseline_manifest,
        v9_e_s3_j1_baseline_manifest_sha256=(
            args.v9_e_s3_j1_baseline_manifest_sha256
        ),
        v9_source_packet_root=args.v9_source_packet_root,
        v9_source_packet_manifest_sha256=args.v9_source_packet_manifest_sha256,
        interface_packet_root=args.interface_packet_root,
    )
    _synchronize_after_plan(MPI.COMM_WORLD)
    if args.dry_run:
        if MPI.COMM_WORLD.rank == 0:
            print(json.dumps(plan, sort_keys=True))
        return 0
    cfg, profile, input_sha256, physical_model_sha256 = _load_cfg(args.input)
    marker_callback = _file_marker_callback(
        args.memory_stages,
        args.memory_markers,
        enabled=MPI.COMM_WORLD.rank == 0,
    )
    v7_continuation = None
    if args.v7_scale_normalized_identity:
        from src.solvers.hybrid_full_spectrum_screen import (
            run_v7_full_spectrum_continuation,
        )

        v7_continuation = run_v7_full_spectrum_continuation
    result = run_task040_level_a(
        cfg,
        profile,
        exact_spool_root=args.exact_spool_root,
        run_directory=args.run_directory,
        source_sha=args.source_sha,
        input_path=args.input,
        input_sha256=input_sha256,
        physical_model_sha256=physical_model_sha256,
        marker_callback=marker_callback,
        scalar_krylov=args.v1_1_scalar_krylov,
        interface_schur=args.v1_2_interface_schur,
        packet_producer=args.v2_interface_packet_producer,
        packet_consumer=args.v2_interface_packet_consumer,
        coupled_interface=args.v3_2_coupled_interface,
        v4_exact_authority_compatibility=args.v4_exact_authority_compatibility,
        v5_fresh_bare_f_authority=args.v5_fresh_bare_f_authority,
        v5_route_c=args.v5_route_c,
        v6_2_interface_schur=args.v6_2_interface_schur,
        v7_scale_normalized_identity=args.v7_scale_normalized_identity,
        v7_moving_pml_full_state=args.v7_moving_pml_full_state,
        v8_full_spectrum_only=args.v8_full_spectrum_only,
        v8_adaptive_schwarz_only=args.v8_adaptive_schwarz_only,
        v8_adaptive_stage_b1_only=args.v8_adaptive_stage_b1_only,
        v8_adaptive_stage_bc_only=args.v8_adaptive_stage_bc_only,
        v9_source_bridge_only=args.v9_source_bridge_only,
        v9_c0_explicit_coarse_only=args.v9_c0_explicit_coarse_only,
        v9_e_lor_l2_only=args.v9_e_lor_l2_only,
        v9_e_lor_bare_f_external_only=args.v9_e_lor_bare_f_external_only,
        v9_e_s3_j1_baseline_only=args.v9_e_s3_j1_baseline_only,
        v9_e_s3_structured_b1_only=args.v9_e_s3_structured_b1_only,
        v9_e_s3_j1_baseline_manifest=args.v9_e_s3_j1_baseline_manifest,
        v9_e_s3_j1_baseline_manifest_sha256=(
            args.v9_e_s3_j1_baseline_manifest_sha256
        ),
        v9_source_packet_root=args.v9_source_packet_root,
        v9_source_packet_manifest_sha256=args.v9_source_packet_manifest_sha256,
        resource_callback=(
            lambda: (
                _worker_current_resource(
                    MPI.COMM_WORLD,
                    hard_limit_bytes=(
                        TASK040_V2_INTERFACE_PACKET_HARD_STOP_BYTES
                        if args.v2_interface_packet_producer
                        else TASK040_V5_FRESH_BARE_F_HARD_STOP_BYTES
                        if args.v5_fresh_bare_f_authority
                        else TASK040_V5_ROUTE_C_HARD_STOP_BYTES
                        if args.v5_route_c
                        else V9_C0_HARD_STOP_BYTES
                        if args.v9_c0_explicit_coarse_only
                        else V9_E_LOR_L2_ONLY_HARD_STOP_BYTES
                        if args.v9_e_lor_l2_only
                        else V9_E_LOR_BARE_F_EXTERNAL_ONLY_HARD_STOP_BYTES
                        if args.v9_e_lor_bare_f_external_only
                        else S3B_RSS_HARD_BYTES
                        if args.v9_e_s3_j1_baseline_only
                        or args.v9_e_s3_structured_b1_only
                        else V8_ADAPTIVE_HARD_STOP_BYTES
                        if args.v8_adaptive_schwarz_only
                        or args.v8_adaptive_stage_b1_only
                        or args.v8_adaptive_stage_bc_only
                        or args.v9_source_bridge_only
                        else TASK040_LEVEL_A_HARD_STOP_BYTES
                    ),
                )
                if (
                    args.v1_1_scalar_krylov
                    or args.v1_2_interface_schur
                    or args.v2_interface_packet_producer
                    or args.v2_interface_packet_consumer
                    or args.v3_2_coupled_interface
                    or args.v4_exact_authority_compatibility
                    or args.v5_fresh_bare_f_authority
                    or args.v5_route_c
                    or args.v6_2_interface_schur
                    or args.v7_scale_normalized_identity
                    or args.v7_moving_pml_full_state
                    or args.v8_full_spectrum_only
                    or args.v8_adaptive_schwarz_only
                    or args.v8_adaptive_stage_b1_only
                    or args.v8_adaptive_stage_bc_only
                    or args.v9_source_bridge_only
                    or args.v9_c0_explicit_coarse_only
                    or args.v9_e_lor_l2_only
                    or args.v9_e_lor_bare_f_external_only
                    or args.v9_e_s3_j1_baseline_only
                    or args.v9_e_s3_structured_b1_only
                )
                else None
            )
        ),
        packet_root=(
            Path(args.run_directory) / "interface_packet"
            if args.v2_interface_packet_producer
            else args.interface_packet_root
            if args.v2_interface_packet_consumer or args.v3_2_coupled_interface
            else None
        ),
        watchdog_enabled=args.watchdog_enabled,
        bottom_route_only=args.bottom_route_only,
        watchdog_hard_stop_bytes=(
            args.watchdog_hard_stop_bytes
            if args.v6_2_interface_schur
            or args.v7_scale_normalized_identity
            or args.v7_moving_pml_full_state
            or args.v8_full_spectrum_only
            or args.v8_adaptive_schwarz_only
            or args.v8_adaptive_stage_b1_only
            or args.v8_adaptive_stage_bc_only
            or args.v9_source_bridge_only
            or args.v9_c0_explicit_coarse_only
            or args.v9_e_lor_l2_only
            or args.v9_e_lor_bare_f_external_only
            or args.v9_e_s3_j1_baseline_only
            or args.v9_e_s3_structured_b1_only
            else None
        ),
        v7_continuation=v7_continuation,
    )
    if MPI.COMM_WORLD.rank == 0:
        run_directory = Path(args.run_directory)
        run_directory.mkdir(parents=True, exist_ok=True)
        summary_path = run_directory / "run_summary.json"
        if summary_path.exists():
            raise FileExistsError(f"Task040 run summary already exists: {summary_path}")
        summary_path.write_text(
            json.dumps(result, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0


def _synchronize_after_plan(comm: MPI.Intracomm) -> None:
    comm.Barrier()


if __name__ == "__main__":
    raise SystemExit(main())
